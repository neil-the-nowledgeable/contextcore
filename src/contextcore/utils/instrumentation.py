"""Instrumentation hints derivation from OTel conventions and pipeline artifacts.

Derives per-service instrumentation hints (expected metrics, trace spans, SDK
coordinates, dependencies) from the service communication graph, artifact
manifest semantic conventions, and transport protocol → OTel semantic convention
mappings.

Implements REQ-ICD-100 through REQ-ICD-105.

Used by: ``build_onboarding_metadata()`` in ``onboarding.py``
Consumed by: startd8-sdk TODO Scanner (REQ-TCW-100) and Completion Planner (REQ-TCW-200)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from contextcore.models.artifact_manifest import ArtifactManifest

logger = logging.getLogger(__name__)

# ── OTel semantic convention metrics by transport protocol (REQ-ICD-100) ──
_GRPC_CONVENTION_METRICS = [
    {"name": "rpc.server.duration", "type": "histogram", "source": "otel_semconv:grpc"},
    {"name": "rpc.server.request.size", "type": "histogram", "source": "otel_semconv:grpc"},
    {"name": "rpc.server.response.size", "type": "histogram", "source": "otel_semconv:grpc"},
    {"name": "rpc.server.requests_per_rpc", "type": "histogram", "source": "otel_semconv:grpc"},
]

_HTTP_CONVENTION_METRICS = [
    {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"},
    {"name": "http.server.request.body.size", "type": "histogram", "source": "otel_semconv:http"},
    {"name": "http.server.response.body.size", "type": "histogram", "source": "otel_semconv:http"},
]

_PROTOCOL_METRICS = {
    "grpc": _GRPC_CONVENTION_METRICS,
    "http": _HTTP_CONVENTION_METRICS,
    "grpc-web": _HTTP_CONVENTION_METRICS,
}

# ── Trace span attributes by transport protocol (REQ-ICD-101) ────────────
_GRPC_SPAN_ATTRIBUTES = ["rpc.system", "rpc.service", "rpc.method"]
_HTTP_SPAN_ATTRIBUTES = ["http.method", "http.route", "http.status_code"]

# ── OTel SDK mapping by language (REQ-ICD-102) ──────────────────────────
_OTEL_SDK_MAP: Dict[str, Dict[str, Any]] = {
    "python": {
        "sdk": "opentelemetry-sdk",
        "exporter": "opentelemetry-exporter-otlp",
        "interceptors": {
            "grpc": "opentelemetry-instrumentation-grpc",
            "http": "opentelemetry-instrumentation-flask",
        },
    },
    "java": {
        "sdk": "io.opentelemetry:opentelemetry-sdk",
        "exporter": "io.opentelemetry:opentelemetry-exporter-otlp",
        "interceptors": {
            "grpc": "io.grpc:grpc-opentelemetry",
            "http": "io.opentelemetry.instrumentation:opentelemetry-spring-boot-starter",
        },
    },
    "go": {
        "sdk": "go.opentelemetry.io/otel",
        "exporter": "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc",
        "interceptors": {
            "grpc": "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc",
            "http": "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp",
        },
    },
    "nodejs": {
        "sdk": "@opentelemetry/sdk-node",
        "exporter": "@opentelemetry/exporter-trace-otlp-grpc",
        "interceptors": {
            "grpc": "@opentelemetry/instrumentation-grpc",
            "http": "@opentelemetry/instrumentation-http",
        },
    },
    "dotnet": {
        "sdk": "OpenTelemetry",
        "exporter": "OpenTelemetry.Exporter.OpenTelemetryProtocol",
        "interceptors": {
            "grpc": "OpenTelemetry.Instrumentation.GrpcNetClient",
            "http": "OpenTelemetry.Instrumentation.AspNetCore",
        },
    },
}


# ── Database client library detection (REQ-ICD-105) ──────────────────
_DATABASE_IMPORT_PATTERNS: Dict[str, str] = {
    "Npgsql": "postgresql",
    "psycopg2": "postgresql",
    "asyncpg": "postgresql",
    "pg": "postgresql",
    "postgres": "postgresql",
    "AlloyDB": "postgresql",  # AlloyDB uses pg wire protocol
    "Spanner": "spanner",
    "SpannerConnection": "spanner",
    "MySql": "mysql",
    "mysql": "mysql",
    "pymysql": "mysql",
    "Redis": "redis",
    "StackExchange.Redis": "redis",
    "redis": "redis",
    "Sqlite": "sqlite",
    "sqlite3": "sqlite",
    "System.Data.SQLite": "sqlite",
}


def _detect_databases_from_imports(imports: List[str]) -> List[str]:
    """Detect database types from a service's import list (REQ-ICD-105).

    Scans each import string for known database client library keywords.
    Returns a list of detected database types (may contain duplicates
    from different imports matching the same type — preserves provenance).
    """
    detected: List[str] = []
    for imp in imports:
        for keyword, db_type in _DATABASE_IMPORT_PATTERNS.items():
            if keyword in imp and db_type not in detected:
                detected.append(db_type)
    return detected


def _convention_metrics_for_protocol(protocol: str) -> List[Dict[str, Any]]:
    """Return OTel semantic convention metrics for a transport protocol."""
    return [dict(m) for m in _PROTOCOL_METRICS.get(protocol, _HTTP_CONVENTION_METRICS)]


def _manifest_declared_metrics(
    artifact_manifest: ArtifactManifest,
) -> List[Dict[str, Any]]:
    """Extract metrics declared in semantic_conventions.metrics from the manifest."""
    if not artifact_manifest.semantic_conventions:
        return []
    metrics_by_source = artifact_manifest.semantic_conventions.metrics
    if not metrics_by_source:
        return []
    result = []
    for source, names in metrics_by_source.items():
        for name in names:
            result.append({
                "name": name,
                "source": f"semantic_conventions.metrics:{source}",
            })
    return result


def _derive_traces(
    comm_graph: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Derive trace span requirements per service from the communication graph."""
    if not comm_graph:
        return {}

    traces: Dict[str, Dict[str, Any]] = {}
    services = comm_graph.get("services", {})

    for svc_name, svc_data in services.items():
        protocol = svc_data.get("protocol", "http")
        required_spans: List[Dict[str, Any]] = []

        if protocol == "grpc":
            required_spans.append({
                "span_name": "{grpc_service}/{grpc_method}",
                "attributes": _GRPC_SPAN_ATTRIBUTES,
                "source": f"service_communication_graph:{svc_name}",
            })
            for rpc_call in svc_data.get("rpc_calls", []):
                target = rpc_call.get("target_service", "unknown")
                method = rpc_call.get("method", "unknown")
                required_spans.append({
                    "span_name": f"{target}/{method}",
                    "attributes": _GRPC_SPAN_ATTRIBUTES,
                    "source": f"service_communication_graph:{svc_name}:rpc_call",
                })
        else:
            required_spans.append({
                "span_name": "{http_method} {http_route}",
                "attributes": _HTTP_SPAN_ATTRIBUTES,
                "source": f"service_communication_graph:{svc_name}",
            })

        traces[svc_name] = {
            "required": required_spans,
            "propagation": "W3C",
        }

    return traces


def _resolve_sdk(
    language: Optional[str],
    transport: str,
) -> Optional[Dict[str, str]]:
    """Resolve OTel SDK coordinates for a language + transport combination."""
    if not language or language not in _OTEL_SDK_MAP:
        return None
    entry = _OTEL_SDK_MAP[language]
    interceptor = entry["interceptors"].get(transport, entry["interceptors"].get("http"))
    return {
        "package": entry["sdk"],
        "interceptor": interceptor,
        "exporter": entry["exporter"],
    }


def _resolve_dependencies(
    language: Optional[str],
    transport: str,
) -> List[Dict[str, str]]:
    """Resolve dependency addition list for a language + transport."""
    sdk = _resolve_sdk(language, transport)
    if not sdk:
        return []
    return [
        {"package": sdk["package"], "version": "latest_stable"},
        {"package": sdk["interceptor"], "version": "latest_stable"},
        {"package": sdk["exporter"], "version": "latest_stable"},
    ]


def derive_instrumentation_hints(
    artifact_manifest: ArtifactManifest,
    service_communication_graph: Optional[Dict[str, Any]],
    service_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Derive per-service instrumentation hints from pipeline artifacts.

    Composes:
    - Convention-based metrics from protocol → OTel semantic conventions
    - Manifest-declared metrics from semantic_conventions.metrics
    - Trace span requirements from the communication graph
    - SDK coordinates from detected language + transport protocol
    - Dependency addition list

    Args:
        artifact_manifest: The generated artifact manifest.
        service_communication_graph: Communication graph from init-from-plan.
        service_metadata: Per-service metadata dict.

    Returns:
        Dict keyed by service name, each value an instrumentation hints dict.
    """
    # Traces from communication graph
    traces_by_service = _derive_traces(service_communication_graph)

    # Manifest-declared metrics (project-wide, not per-service)
    manifest_metrics = _manifest_declared_metrics(artifact_manifest)

    # Collect all known service names
    all_services: set = set()
    if service_communication_graph:
        all_services.update(service_communication_graph.get("services", {}).keys())
    if service_metadata:
        all_services.update(service_metadata.keys())

    if not all_services:
        return {}

    hints: Dict[str, Dict[str, Any]] = {}

    for svc_name in sorted(all_services):
        svc_graph = (service_communication_graph or {}).get("services", {}).get(svc_name, {})
        svc_meta = (service_metadata or {}).get(svc_name, {})

        transport = svc_graph.get("protocol") or svc_meta.get("transport_protocol", "http")
        language = svc_graph.get("language")

        # Convention-based metrics from protocol
        convention_metrics = _convention_metrics_for_protocol(transport)

        # SDK resolution
        sdk = _resolve_sdk(language, transport)
        deps = _resolve_dependencies(language, transport)

        # Traces
        traces_spec = traces_by_service.get(svc_name, {"required": [], "propagation": "W3C"})

        # Database detection from imports (REQ-ICD-105)
        svc_imports = svc_graph.get("imports", [])
        detected_dbs = _detect_databases_from_imports(svc_imports)

        hint: Dict[str, Any] = {
            "service_id": svc_name,
            "transport": transport,
            "detected_databases": detected_dbs,
            "metrics": {
                "convention_based": convention_metrics,
                "manifest_declared": manifest_metrics,
            },
            "traces": traces_spec,
            "logging": {
                "trace_context_fields": [],
                "_note": "Populated by startd8-sdk after code generation, not by ContextCore",
            },
            "dependencies": {
                "add": deps,
            },
        }

        if language:
            hint["language"] = language
        if sdk:
            hint["metrics"]["sdk"] = sdk
            hint["traces"]["sdk"] = sdk

        hints[svc_name] = hint

    return hints
