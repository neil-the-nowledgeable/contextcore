"""Tests for instrumentation hints derivation (REQ-ICD-100–104)."""

from __future__ import annotations

import pytest

from contextcore.models.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestMetadata,
    ArtifactPriority,
    ArtifactSpec,
    ArtifactStatus,
    ArtifactType,
    CoverageSummary,
    SemanticConventionHints,
)
from contextcore.utils.instrumentation import (
    _convention_metrics_for_protocol,
    _derive_traces,
    _manifest_declared_metrics,
    _resolve_dependencies,
    _resolve_sdk,
    derive_instrumentation_hints,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_manifest(semconv_metrics=None) -> ArtifactManifest:
    semconv = None
    if semconv_metrics is not None:
        semconv = SemanticConventionHints(metrics=semconv_metrics)
    return ArtifactManifest(
        metadata=ArtifactManifestMetadata(
            generated_from="test.yaml",
            project_id="test-project",
        ),
        artifacts=[
            ArtifactSpec(
                id="test-dashboard",
                type=ArtifactType.DASHBOARD,
                name="Test Dashboard",
                target="test-svc",
                priority=ArtifactPriority.REQUIRED,
                status=ArtifactStatus.NEEDED,
            ),
        ],
        coverage=CoverageSummary(),
        semantic_conventions=semconv,
    )


SAMPLE_GRAPH = {
    "services": {
        "emailservice": {
            "imports": ["demo_pb2", "demo_pb2_grpc"],
            "rpc_calls": [],
            "protocol": "grpc",
            "language": "python",
        },
        "frontend": {
            "imports": ["demo_pb2"],
            "rpc_calls": [
                {"target_service": "productcatalogservice", "method": "ListProducts"},
                {"target_service": "emailservice", "method": "SendEmail"},
            ],
            "protocol": "http",
            "language": "go",
        },
    },
    "shared_modules": {},
    "proto_schemas": [],
}


# ---------------------------------------------------------------------------
# Phase 2: Convention-based metrics (REQ-ICD-100)
# ---------------------------------------------------------------------------

class TestConventionBasedMetrics:
    def test_grpc_produces_rpc_metrics(self):
        metrics = _convention_metrics_for_protocol("grpc")
        names = [m["name"] for m in metrics]
        assert "rpc.server.duration" in names
        assert "rpc.server.request.size" in names
        assert all(m["source"] == "otel_semconv:grpc" for m in metrics)

    def test_http_produces_http_metrics(self):
        metrics = _convention_metrics_for_protocol("http")
        names = [m["name"] for m in metrics]
        assert "http.server.duration" in names
        assert "http.server.request.body.size" in names

    def test_unknown_protocol_falls_back_to_http(self):
        metrics = _convention_metrics_for_protocol("websocket")
        names = [m["name"] for m in metrics]
        assert "http.server.duration" in names

    def test_grpc_web_uses_http_metrics(self):
        metrics = _convention_metrics_for_protocol("grpc-web")
        names = [m["name"] for m in metrics]
        assert "http.server.duration" in names

    def test_manifest_declared_metrics_from_semconv(self):
        manifest = _make_manifest(semconv_metrics={
            "startd8": ["startd8_active_sessions", "startd8_cost_usd"],
        })
        result = _manifest_declared_metrics(manifest)
        names = [m["name"] for m in result]
        assert "startd8_active_sessions" in names
        assert "startd8_cost_usd" in names
        assert all("semantic_conventions.metrics" in m["source"] for m in result)

    def test_manifest_declared_empty_when_no_semconv(self):
        manifest = _make_manifest()
        result = _manifest_declared_metrics(manifest)
        assert result == []


# ---------------------------------------------------------------------------
# Phase 3: Traces from communication graph (REQ-ICD-101)
# ---------------------------------------------------------------------------

class TestTracesDerivation:
    def test_grpc_service_gets_server_span(self):
        traces = _derive_traces(SAMPLE_GRAPH)
        email = traces["emailservice"]
        assert len(email["required"]) == 1  # server span only, no rpc_calls
        assert email["required"][0]["attributes"] == ["rpc.system", "rpc.service", "rpc.method"]
        assert email["propagation"] == "W3C"

    def test_grpc_with_rpc_calls_gets_client_spans(self):
        graph = {
            "services": {
                "recommender": {
                    "protocol": "grpc",
                    "rpc_calls": [
                        {"target_service": "catalog", "method": "ListProducts"},
                        {"target_service": "catalog", "method": "GetProduct"},
                    ],
                },
            },
        }
        traces = _derive_traces(graph)
        spans = traces["recommender"]["required"]
        assert len(spans) == 3  # 1 server + 2 client

    def test_http_service_gets_http_span(self):
        traces = _derive_traces(SAMPLE_GRAPH)
        frontend = traces["frontend"]
        assert frontend["required"][0]["attributes"] == ["http.method", "http.route", "http.status_code"]

    def test_empty_graph_returns_empty(self):
        assert _derive_traces(None) == {}
        assert _derive_traces({}) == {}
        assert _derive_traces({"services": {}}) == {}


# ---------------------------------------------------------------------------
# Phase 4: SDK resolution (REQ-ICD-102)
# ---------------------------------------------------------------------------

class TestSDKResolution:
    def test_python_grpc(self):
        sdk = _resolve_sdk("python", "grpc")
        assert sdk["package"] == "opentelemetry-sdk"
        assert sdk["interceptor"] == "opentelemetry-instrumentation-grpc"
        assert sdk["exporter"] == "opentelemetry-exporter-otlp"

    def test_java_grpc(self):
        sdk = _resolve_sdk("java", "grpc")
        assert "opentelemetry" in sdk["package"]
        assert "grpc" in sdk["interceptor"].lower()

    def test_go_http(self):
        sdk = _resolve_sdk("go", "http")
        assert "otelhttp" in sdk["interceptor"]

    def test_unknown_language_returns_none(self):
        assert _resolve_sdk("rust", "grpc") is None
        assert _resolve_sdk(None, "grpc") is None

    def test_dependencies_has_three_entries(self):
        deps = _resolve_dependencies("python", "grpc")
        assert len(deps) == 3
        assert all(d["version"] == "latest_stable" for d in deps)

    def test_dependencies_empty_for_unknown(self):
        assert _resolve_dependencies("rust", "grpc") == []


# ---------------------------------------------------------------------------
# Phase 5: Full assembly (REQ-ICD-103)
# ---------------------------------------------------------------------------

class TestDeriveInstrumentationHints:
    def test_full_assembly_with_graph(self):
        manifest = _make_manifest()
        hints = derive_instrumentation_hints(
            artifact_manifest=manifest,
            service_communication_graph=SAMPLE_GRAPH,
            service_metadata=None,
        )
        assert "emailservice" in hints
        assert "frontend" in hints

        email = hints["emailservice"]
        assert email["service_id"] == "emailservice"
        assert email["transport"] == "grpc"
        assert email["language"] == "python"
        assert len(email["metrics"]["convention_based"]) >= 3
        assert email["metrics"]["convention_based"][0]["name"] == "rpc.server.duration"
        assert email["traces"]["required"][0]["attributes"] == ["rpc.system", "rpc.service", "rpc.method"]
        assert email["metrics"]["sdk"]["package"] == "opentelemetry-sdk"
        assert len(email["dependencies"]["add"]) == 3

    def test_http_service_gets_http_metrics(self):
        manifest = _make_manifest()
        hints = derive_instrumentation_hints(
            artifact_manifest=manifest,
            service_communication_graph=SAMPLE_GRAPH,
            service_metadata=None,
        )
        frontend = hints["frontend"]
        assert frontend["transport"] == "http"
        metric_names = [m["name"] for m in frontend["metrics"]["convention_based"]]
        assert "http.server.duration" in metric_names

    def test_no_graph_no_metadata_returns_empty(self):
        manifest = _make_manifest()
        hints = derive_instrumentation_hints(
            artifact_manifest=manifest,
            service_communication_graph=None,
            service_metadata=None,
        )
        assert hints == {}

    def test_service_metadata_only(self):
        manifest = _make_manifest()
        hints = derive_instrumentation_hints(
            artifact_manifest=manifest,
            service_communication_graph=None,
            service_metadata={"myservice": {"transport_protocol": "grpc"}},
        )
        assert "myservice" in hints
        assert hints["myservice"]["transport"] == "grpc"

    def test_language_flows_to_sdk(self):
        manifest = _make_manifest()
        hints = derive_instrumentation_hints(
            artifact_manifest=manifest,
            service_communication_graph=SAMPLE_GRAPH,
            service_metadata=None,
        )
        assert hints["emailservice"]["metrics"]["sdk"]["interceptor"] == "opentelemetry-instrumentation-grpc"
        assert "sdk" in hints["frontend"]["metrics"]  # go SDK resolved

    def test_unknown_language_omits_sdk(self):
        graph = {
            "services": {
                "mystery": {"protocol": "http", "rpc_calls": []},
            },
        }
        manifest = _make_manifest()
        hints = derive_instrumentation_hints(
            artifact_manifest=manifest,
            service_communication_graph=graph,
            service_metadata=None,
        )
        assert "sdk" not in hints["mystery"]["metrics"]
        assert hints["mystery"]["dependencies"]["add"] == []

    def test_logging_explicitly_empty(self):
        manifest = _make_manifest()
        hints = derive_instrumentation_hints(
            artifact_manifest=manifest,
            service_communication_graph=SAMPLE_GRAPH,
            service_metadata=None,
        )
        assert hints["emailservice"]["logging"]["trace_context_fields"] == []
        assert "_note" in hints["emailservice"]["logging"]

    def test_manifest_declared_metrics_included(self):
        manifest = _make_manifest(semconv_metrics={
            "custom": ["my_custom_metric_total"],
        })
        hints = derive_instrumentation_hints(
            artifact_manifest=manifest,
            service_communication_graph=SAMPLE_GRAPH,
            service_metadata=None,
        )
        manifest_names = [m["name"] for m in hints["emailservice"]["metrics"]["manifest_declared"]]
        assert "my_custom_metric_total" in manifest_names

    def test_profile_agnostic_in_onboarding(self):
        """Instrumentation hints appear in onboarding output for all profiles."""
        from contextcore.utils.onboarding import build_onboarding_metadata

        manifest = _make_manifest()
        for profile in ("source", "full"):
            result = build_onboarding_metadata(
                artifact_manifest=manifest,
                artifact_manifest_path="test.yaml",
                project_context_path="test-crd.yaml",
                generation_profile=profile,
                service_communication_graph=SAMPLE_GRAPH,
            )
            assert "instrumentation_hints" in result, f"Missing for profile={profile}"
            assert "emailservice" in result["instrumentation_hints"]
