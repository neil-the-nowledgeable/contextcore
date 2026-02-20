"""
Tests for the service metadata model and pipeline checker gate.

Verifies ServiceMetadataEntry validation, TransportProtocol enum,
effective_healthcheck defaults, and the pipeline checker's
_check_service_metadata gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from contextcore.models.service_metadata import (
    ServiceMetadataEntry,
    TransportProtocol,
)


# ===========================================================================
# Tests — Model validation
# ===========================================================================


class TestServiceMetadataEntry:
    """Test the ServiceMetadataEntry Pydantic model."""

    def test_valid_grpc_service(self):
        entry = ServiceMetadataEntry(
            transport_protocol="grpc",
            schema_contract="demo.proto",
            base_image="python:3.12-slim",
            healthcheck_type="grpc_health_probe",
        )
        assert entry.transport_protocol == TransportProtocol.GRPC
        assert entry.schema_contract == "demo.proto"
        assert entry.base_image == "python:3.12-slim"

    def test_valid_http_service(self):
        entry = ServiceMetadataEntry(
            transport_protocol="http",
        )
        assert entry.transport_protocol == TransportProtocol.HTTP
        assert entry.schema_contract is None
        assert entry.base_image is None

    def test_valid_grpc_web_service(self):
        entry = ServiceMetadataEntry(
            transport_protocol="grpc-web",
            schema_contract="api.proto",
        )
        assert entry.transport_protocol == TransportProtocol.GRPC_WEB

    def test_invalid_protocol_rejected(self):
        with pytest.raises(ValidationError, match="transport_protocol"):
            ServiceMetadataEntry(transport_protocol="websocket")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            ServiceMetadataEntry(
                transport_protocol="grpc",
                unknown_field="value",
            )

    def test_transport_protocol_required(self):
        with pytest.raises(ValidationError):
            ServiceMetadataEntry()


class TestEffectiveHealthcheck:
    """Test the effective_healthcheck property."""

    def test_explicit_healthcheck(self):
        entry = ServiceMetadataEntry(
            transport_protocol="grpc",
            healthcheck_type="custom_probe",
        )
        assert entry.effective_healthcheck == "custom_probe"

    def test_grpc_default(self):
        entry = ServiceMetadataEntry(transport_protocol="grpc")
        assert entry.effective_healthcheck == "grpc_health_probe"

    def test_http_default(self):
        entry = ServiceMetadataEntry(transport_protocol="http")
        assert entry.effective_healthcheck == "http_get"

    def test_grpc_web_default(self):
        entry = ServiceMetadataEntry(transport_protocol="grpc-web")
        assert entry.effective_healthcheck == "http_get"


class TestTransportProtocol:
    """Test the TransportProtocol enum."""

    def test_enum_values(self):
        assert TransportProtocol.GRPC.value == "grpc"
        assert TransportProtocol.HTTP.value == "http"
        assert TransportProtocol.GRPC_WEB.value == "grpc-web"

    def test_string_comparison(self):
        assert TransportProtocol.GRPC == "grpc"
        assert TransportProtocol.HTTP == "http"


# ===========================================================================
# Tests — Pipeline checker gate (service_metadata)
# ===========================================================================

# These tests use the same fixture pattern as test_pipeline_checker.py
# but specifically target the _check_service_metadata gate.

def _write_metadata_with_svc(tmp_path: Path, service_metadata=None, **overrides) -> Path:
    """Write minimal onboarding-metadata.json with service_metadata."""
    import hashlib

    out_dir = tmp_path / "out" / "test-export"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Create required files
    source_content = "project:\n  id: test-svc-project\n"
    source_path = tmp_path / "source-manifest.yaml"
    source_path.write_text(source_content, encoding="utf-8")
    source_checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()

    manifest_content = "artifacts:\n  - id: test-artifact\n"
    manifest_path = out_dir / "test-svc-project-artifact-manifest.yaml"
    manifest_path.write_text(manifest_content, encoding="utf-8")
    manifest_checksum = hashlib.sha256(manifest_content.encode()).hexdigest()

    crd_content = "apiVersion: contextcore.io/v1\nkind: ProjectContext\n"
    crd_path = out_dir / "test-svc-project-projectcontext.yaml"
    crd_path.write_text(crd_content, encoding="utf-8")
    crd_checksum = hashlib.sha256(crd_content.encode()).hexdigest()

    metadata = {
        "version": "1.0.0",
        "schema": "contextcore.io/onboarding-metadata/v1",
        "project_id": "test-svc-project",
        "artifact_manifest_path": "test-svc-project-artifact-manifest.yaml",
        "project_context_path": "test-svc-project-projectcontext.yaml",
        "generated_at": "2026-02-19T12:00:00.000000",
        "artifact_types": {},
        "coverage": {
            "totalRequired": 0,
            "gaps": [],
            "overallCoverage": 1.0,
        },
        "artifact_manifest_checksum": manifest_checksum,
        "project_context_checksum": crd_checksum,
        "source_checksum": source_checksum,
        "source_path_relative": "source-manifest.yaml",
    }

    if service_metadata is not None:
        metadata["service_metadata"] = service_metadata

    metadata.update(overrides)

    meta_path = out_dir / "onboarding-metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return out_dir


class TestServiceMetadataGate:
    """Test the pipeline checker's _check_service_metadata gate."""

    def test_valid_service_metadata_passes(self, tmp_path: Path):
        from contextcore.contracts.a2a.pipeline_checker import PipelineChecker
        from contextcore.contracts.a2a.models import GateOutcome

        out_dir = _write_metadata_with_svc(
            tmp_path,
            service_metadata={
                "emailservice": {
                    "transport_protocol": "grpc",
                    "schema_contract": "demo.proto",
                },
                "frontend": {
                    "transport_protocol": "http",
                },
            },
        )

        checker = PipelineChecker(out_dir)
        report = checker.run()

        svc_gate = next(
            (g for g in report.gates if "service-metadata" in g.gate_id), None
        )
        assert svc_gate is not None
        assert svc_gate.result == GateOutcome.PASS

    def test_missing_transport_protocol_fails(self, tmp_path: Path):
        from contextcore.contracts.a2a.pipeline_checker import PipelineChecker
        from contextcore.contracts.a2a.models import GateOutcome

        out_dir = _write_metadata_with_svc(
            tmp_path,
            service_metadata={
                "emailservice": {
                    # Missing transport_protocol
                    "schema_contract": "demo.proto",
                },
            },
        )

        checker = PipelineChecker(out_dir)
        report = checker.run()

        svc_gate = next(
            (g for g in report.gates if "service-metadata" in g.gate_id), None
        )
        assert svc_gate is not None
        assert svc_gate.result == GateOutcome.FAIL
        assert svc_gate.blocking is True
        assert "missing transport_protocol" in svc_gate.reason

    def test_absent_service_metadata_warns(self, tmp_path: Path):
        from contextcore.contracts.a2a.pipeline_checker import PipelineChecker

        out_dir = _write_metadata_with_svc(tmp_path, service_metadata=None)

        checker = PipelineChecker(out_dir)
        report = checker.run()

        # Should be a warning, not a gate failure
        assert any("service_metadata" in w for w in report.warnings)
        # No service-metadata gate should be present
        assert not any("service-metadata" in g.gate_id for g in report.gates)

    def test_grpc_without_schema_contract_warns(self, tmp_path: Path):
        from contextcore.contracts.a2a.pipeline_checker import PipelineChecker
        from contextcore.contracts.a2a.models import GateOutcome

        out_dir = _write_metadata_with_svc(
            tmp_path,
            service_metadata={
                "emailservice": {
                    "transport_protocol": "grpc",
                    # Missing schema_contract — should be warning, not blocking
                },
            },
        )

        checker = PipelineChecker(out_dir)
        report = checker.run()

        svc_gate = next(
            (g for g in report.gates if "service-metadata" in g.gate_id), None
        )
        assert svc_gate is not None
        # Should pass (warning-only) since transport_protocol is present
        assert svc_gate.result == GateOutcome.PASS
        assert svc_gate.severity.value == "warning"
        assert any(
            "schema_contract" in e.description
            for e in (svc_gate.evidence or [])
        )
