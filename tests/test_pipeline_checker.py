"""
Tests for the Pipeline Integrity Checker.

Verifies that the checker correctly runs all gate checks against real-format
export output (onboarding-metadata.json and provenance.json).
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path

import pytest

from contextcore.contracts.a2a.models import GateOutcome
from contextcore.contracts.a2a.pipeline_checker import (
    PipelineCheckReport,
    PipelineChecker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(content: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_fixture(tmp_path: Path, **overrides) -> Path:
    """
    Build a realistic export output directory with valid metadata.

    Returns the output directory path.
    """
    out_dir = tmp_path / "out" / "test-export"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Create source manifest
    source_content = textwrap.dedent("""\
        project:
          id: test-project
        targets:
          - name: checkout-api
    """)
    source_path = tmp_path / "source-manifest.yaml"
    source_path.write_text(source_content, encoding="utf-8")
    source_checksum = _sha256(source_content)

    # NOTE: The real export pipeline uses get_file_checksum() which reads raw
    # bytes. For file checksums, we use the raw file bytes, not string.
    source_file_checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()

    # Create artifact manifest
    manifest_content = textwrap.dedent("""\
        artifacts:
          - id: checkout_api-dashboard
            type: dashboard
            status: needed
          - id: checkout_api-prometheus-rules
            type: prometheus_rule
            status: needed
          - id: checkout_api-slo
            type: slo_definition
            status: needed
    """)
    manifest_path = out_dir / "test-project-artifact-manifest.yaml"
    manifest_path.write_text(manifest_content, encoding="utf-8")
    manifest_checksum = _sha256(manifest_content)

    # Create project context CRD
    crd_content = textwrap.dedent("""\
        apiVersion: contextcore.io/v1
        kind: ProjectContext
        metadata:
          name: test-project
        spec:
          project:
            id: test-project
    """)
    crd_path = out_dir / "test-project-projectcontext.yaml"
    crd_path.write_text(crd_content, encoding="utf-8")
    crd_checksum = _sha256(crd_content)

    # Build onboarding-metadata.json
    metadata = {
        "version": "1.0.0",
        "schema": "contextcore.io/onboarding-metadata/v1",
        "project_id": "test-project",
        "artifact_manifest_path": "test-project-artifact-manifest.yaml",
        "project_context_path": "test-project-projectcontext.yaml",
        "generated_at": "2026-02-13T12:00:00.000000",
        "artifact_types": {
            "dashboard": {"output_ext": ".json"},
            "prometheus_rule": {"output_ext": ".yaml"},
            "slo_definition": {"output_ext": ".yaml"},
        },
        "coverage": {
            "totalRequired": 3,
            "totalExisting": 0,
            "totalOutdated": 0,
            "overallCoverage": 0.0,
            "byTarget": [
                {
                    "target": "checkout-api",
                    "namespace": "default",
                    "requiredCount": 3,
                    "existingCount": 0,
                    "coveragePercent": 0.0,
                    "gaps": [
                        "checkout_api-dashboard",
                        "checkout_api-prometheus-rules",
                        "checkout_api-slo",
                    ],
                }
            ],
            "byType": {"dashboard": 1, "prometheus_rule": 1, "slo_definition": 1},
            "gaps": [
                "checkout_api-dashboard",
                "checkout_api-prometheus-rules",
                "checkout_api-slo",
            ],
        },
        "artifact_manifest_checksum": manifest_checksum,
        "project_context_checksum": crd_checksum,
        "source_checksum": source_file_checksum,
        "source_path_relative": "source-manifest.yaml",
        "file_ownership": {
            "grafana/dashboards/checkout-api-dashboard.json": {
                "artifact_ids": ["checkout_api-dashboard"],
                "artifact_types": ["dashboard"],
                "scope": "primary",
                "task_ids": [],
            },
            "prometheus/rules/checkout-api-prometheus-rules.yaml": {
                "artifact_ids": ["checkout_api-prometheus-rules"],
                "artifact_types": ["prometheus_rule"],
                "scope": "primary",
                "task_ids": [],
            },
            "slo/checkout-api-slo.yaml": {
                "artifact_ids": ["checkout_api-slo"],
                "artifact_types": ["slo_definition"],
                "scope": "primary",
                "task_ids": [],
            },
        },
    }

    # Apply overrides
    metadata.update(overrides)

    meta_path = out_dir / "onboarding-metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return out_dir


def _write_provenance(out_dir: Path, source_checksum: str, **overrides) -> None:
    """Write a matching provenance.json into the output directory."""
    provenance = {
        "generatedAt": "2026-02-13T12:00:00.000000",
        "durationMs": 42,
        "sourcePath": "/absolute/path/to/source-manifest.yaml",
        "sourceChecksum": source_checksum,
        "contextcoreVersion": "0.1.0",
        "pythonVersion": "3.14.2",
        "hostname": "test-host",
        "username": "testuser",
        "workingDirectory": "/test",
        "git": {
            "commitSha": "abc123",
            "branch": "main",
            "isDirty": False,
            "remoteUrl": "https://github.com/test/test.git",
        },
        "outputDirectory": str(out_dir),
        "outputFiles": [
            "test-project-projectcontext.yaml",
            "test-project-artifact-manifest.yaml",
        ],
    }
    provenance.update(overrides)
    prov_path = out_dir / "provenance.json"
    prov_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")


# ===========================================================================
# Tests — Structural integrity
# ===========================================================================


class TestStructuralIntegrity:
    """Test the structural integrity gate."""

    def test_valid_structure_passes(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        structural = report.gates[0]
        assert structural.gate_id.endswith("-structural-integrity")
        assert structural.result == GateOutcome.PASS

    def test_missing_required_field_fails(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        # Remove required field
        meta_path = out_dir / "onboarding-metadata.json"
        data = json.loads(meta_path.read_text())
        del data["source_checksum"]
        meta_path.write_text(json.dumps(data))

        checker = PipelineChecker(out_dir)
        report = checker.run()

        structural = report.gates[0]
        assert structural.result == GateOutcome.FAIL
        assert structural.blocking is True
        assert "source_checksum" in structural.reason

    def test_missing_coverage_gaps_field(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        meta_path = out_dir / "onboarding-metadata.json"
        data = json.loads(meta_path.read_text())
        del data["coverage"]["gaps"]
        meta_path.write_text(json.dumps(data))

        checker = PipelineChecker(out_dir)
        report = checker.run()

        structural = report.gates[0]
        assert structural.result == GateOutcome.FAIL
        assert "coverage.gaps" in structural.reason

    def test_invalid_schema_prefix_noted(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path, schema="invalid-schema/v1")
        checker = PipelineChecker(out_dir)
        report = checker.run()

        structural = report.gates[0]
        # Still passes (unexpected schema is evidence, not a failure)
        assert structural.result == GateOutcome.PASS


# ===========================================================================
# Tests — Checksum chain
# ===========================================================================


class TestChecksumChain:
    """Test the checksum chain verification gate."""

    def test_valid_checksums_pass(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        checksum_gate = report.gates[1]
        assert checksum_gate.gate_id.endswith("-checksum-chain")
        assert checksum_gate.result == GateOutcome.PASS

    def test_tampered_manifest_fails(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        # Tamper with the artifact manifest after metadata was written
        manifest_path = out_dir / "test-project-artifact-manifest.yaml"
        manifest_path.write_text("tampered content!", encoding="utf-8")

        checker = PipelineChecker(out_dir)
        report = checker.run()

        checksum_gate = report.gates[1]
        assert checksum_gate.result == GateOutcome.FAIL
        assert checksum_gate.blocking is True
        assert "artifact_manifest_checksum" in checksum_gate.reason

    def test_tampered_crd_fails(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        crd_path = out_dir / "test-project-projectcontext.yaml"
        crd_path.write_text("tampered crd!", encoding="utf-8")

        checker = PipelineChecker(out_dir)
        report = checker.run()

        checksum_gate = report.gates[1]
        assert checksum_gate.result == GateOutcome.FAIL
        assert "project_context_checksum" in checksum_gate.reason

    def test_missing_source_file_graceful(self, tmp_path: Path):
        """When source file doesn't exist, only verifiable checksums are checked."""
        out_dir = _write_fixture(tmp_path)

        # Remove source file
        source_path = tmp_path / "source-manifest.yaml"
        source_path.unlink()

        checker = PipelineChecker(out_dir)
        report = checker.run()

        checksum_gate = report.gates[1]
        # Should still pass — only manifest and crd are verifiable
        assert checksum_gate.result == GateOutcome.PASS


# ===========================================================================
# Tests — Provenance cross-check
# ===========================================================================


class TestProvenanceCrossCheck:
    """Test the provenance consistency gate."""

    def test_matching_provenance_passes(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        # Read back the stored source checksum
        meta = json.loads((out_dir / "onboarding-metadata.json").read_text())
        source_cs = meta["source_checksum"]
        _write_provenance(out_dir, source_checksum=source_cs)

        checker = PipelineChecker(out_dir)
        report = checker.run()

        prov_gate = next(g for g in report.gates if "provenance" in g.gate_id)
        assert prov_gate.result == GateOutcome.PASS

    def test_mismatched_source_checksum_fails(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        _write_provenance(out_dir, source_checksum="deadbeef" * 8)

        checker = PipelineChecker(out_dir)
        report = checker.run()

        prov_gate = next(g for g in report.gates if "provenance" in g.gate_id)
        assert prov_gate.result == GateOutcome.FAIL
        assert "source_checksum mismatch" in prov_gate.reason

    def test_missing_output_file_fails(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        meta = json.loads((out_dir / "onboarding-metadata.json").read_text())
        source_cs = meta["source_checksum"]
        _write_provenance(
            out_dir,
            source_checksum=source_cs,
            outputFiles=["test-project-projectcontext.yaml", "nonexistent-file.yaml"],
        )

        checker = PipelineChecker(out_dir)
        report = checker.run()

        prov_gate = next(g for g in report.gates if "provenance" in g.gate_id)
        assert prov_gate.result == GateOutcome.FAIL
        assert "missing output file" in prov_gate.reason

    def test_no_provenance_is_skipped(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert any("provenance-consistency" in s for s in report.skipped)


# ===========================================================================
# Tests — Mapping completeness
# ===========================================================================


class TestMappingCompleteness:
    """Test the mapping completeness gate."""

    def test_complete_mapping_passes(self, tmp_path: Path):
        out_dir = _write_fixture(
            tmp_path,
            artifact_task_mapping={
                "checkout_api-dashboard": "PI-019",
                "checkout_api-prometheus-rules": "PI-020",
                "checkout_api-slo": "PI-021",
            },
        )

        checker = PipelineChecker(out_dir)
        report = checker.run()

        mapping_gate = next(g for g in report.gates if "mapping" in g.gate_id)
        assert mapping_gate.result == GateOutcome.PASS

    def test_incomplete_mapping_fails(self, tmp_path: Path):
        out_dir = _write_fixture(
            tmp_path,
            artifact_task_mapping={
                "checkout_api-dashboard": "PI-019",
                # Missing: prometheus-rules and slo
            },
        )

        checker = PipelineChecker(out_dir)
        report = checker.run()

        mapping_gate = next(g for g in report.gates if "mapping" in g.gate_id)
        assert mapping_gate.result == GateOutcome.FAIL
        assert mapping_gate.blocking is True
        assert "2 artifact(s) unmapped" in mapping_gate.reason

    def test_no_mapping_is_skipped(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert any("mapping-completeness" in s for s in report.skipped)


# ===========================================================================
# Tests — Gap parity
# ===========================================================================


class TestGapParity:
    """Test the gap parity gate."""

    def test_full_parity_passes(self, tmp_path: Path):
        """When file_ownership covers all gaps, parity should pass."""
        out_dir = _write_fixture(tmp_path)

        checker = PipelineChecker(out_dir)
        report = checker.run()

        gap_gate = next(g for g in report.gates if "gap-parity" in g.gate_id)
        assert gap_gate.result == GateOutcome.PASS

    def test_missing_feature_fails(self, tmp_path: Path):
        """When file_ownership is missing an artifact, parity fails."""
        out_dir = _write_fixture(tmp_path)

        # Remove one artifact from file_ownership
        meta_path = out_dir / "onboarding-metadata.json"
        data = json.loads(meta_path.read_text())
        del data["file_ownership"]["slo/checkout-api-slo.yaml"]
        meta_path.write_text(json.dumps(data))

        checker = PipelineChecker(out_dir)
        report = checker.run()

        gap_gate = next(g for g in report.gates if "gap-parity" in g.gate_id)
        assert gap_gate.result == GateOutcome.FAIL
        assert "1 gap(s) have no matching feature" in gap_gate.reason

    def test_orphan_feature_fails(self, tmp_path: Path):
        """When file_ownership has extra artifacts not in gaps, parity fails."""
        out_dir = _write_fixture(tmp_path)

        # Add an extra artifact to file_ownership
        meta_path = out_dir / "onboarding-metadata.json"
        data = json.loads(meta_path.read_text())
        data["file_ownership"]["extra/orphan.yaml"] = {
            "artifact_ids": ["orphan-artifact"],
            "artifact_types": ["unknown"],
            "scope": "primary",
            "task_ids": [],
        }
        meta_path.write_text(json.dumps(data))

        checker = PipelineChecker(out_dir)
        report = checker.run()

        gap_gate = next(g for g in report.gates if "gap-parity" in g.gate_id)
        assert gap_gate.result == GateOutcome.FAIL
        assert "feature(s) have no matching gap" in gap_gate.reason


# ===========================================================================
# Tests — Design calibration
# ===========================================================================


class TestDesignCalibration:
    """Test the design calibration gate."""

    def _metadata_with_calibration(self) -> dict:
        """Return calibration hints matching the fixture's artifact types."""
        return {
            "design_calibration_hints": {
                "dashboard": {
                    "expected_depth": "comprehensive",
                    "expected_loc_range": ">150",
                    "red_flag": "Calibrated as 'brief'",
                },
                "prometheus_rule": {
                    "expected_depth": "standard",
                    "expected_loc_range": "51-150",
                    "red_flag": "Calibrated as 'brief'",
                },
                "slo_definition": {
                    "expected_depth": "standard",
                    "expected_loc_range": "51-150",
                    "red_flag": "Calibrated as 'comprehensive'",
                },
            }
        }

    def test_valid_calibration_passes(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path, **self._metadata_with_calibration())
        checker = PipelineChecker(out_dir)
        report = checker.run()

        cal_gate = next(g for g in report.gates if "calibration" in g.gate_id)
        assert cal_gate.result == GateOutcome.PASS

    def test_missing_calibration_for_type_fails(self, tmp_path: Path):
        overrides = self._metadata_with_calibration()
        # Remove one type — dashboard is in byType but not calibrated
        del overrides["design_calibration_hints"]["dashboard"]
        out_dir = _write_fixture(tmp_path, **overrides)

        checker = PipelineChecker(out_dir)
        report = checker.run()

        cal_gate = next(g for g in report.gates if "calibration" in g.gate_id)
        assert cal_gate.result == GateOutcome.FAIL
        assert "uncalibrated: dashboard" in cal_gate.reason

    def test_invalid_depth_fails(self, tmp_path: Path):
        overrides = self._metadata_with_calibration()
        overrides["design_calibration_hints"]["dashboard"]["expected_depth"] = "megadeth"
        out_dir = _write_fixture(tmp_path, **overrides)

        checker = PipelineChecker(out_dir)
        report = checker.run()

        cal_gate = next(g for g in report.gates if "calibration" in g.gate_id)
        assert cal_gate.result == GateOutcome.FAIL
        assert "invalid depth" in cal_gate.reason

    def test_calibration_not_blocking(self, tmp_path: Path):
        """Calibration issues are warnings, not hard blocks."""
        overrides = self._metadata_with_calibration()
        del overrides["design_calibration_hints"]["dashboard"]
        out_dir = _write_fixture(tmp_path, **overrides)

        checker = PipelineChecker(out_dir)
        report = checker.run()

        cal_gate = next(g for g in report.gates if "calibration" in g.gate_id)
        assert cal_gate.result == GateOutcome.FAIL
        assert cal_gate.blocking is False
        # Report should still be healthy (calibration is non-blocking)
        assert report.is_healthy is True

    def test_no_calibration_hints_skipped(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert any("design-calibration" in s for s in report.skipped)

    def test_loc_out_of_range_detection(self, tmp_path: Path):
        """Test the LOC range helper directly."""
        assert PipelineChecker._loc_out_of_range(200, ">150") is False
        assert PipelineChecker._loc_out_of_range(100, ">150") is True
        assert PipelineChecker._loc_out_of_range(150, ">150") is True
        assert PipelineChecker._loc_out_of_range(50, "<=50") is False
        assert PipelineChecker._loc_out_of_range(51, "<=50") is True
        assert PipelineChecker._loc_out_of_range(75, "51-150") is False
        assert PipelineChecker._loc_out_of_range(50, "51-150") is True
        assert PipelineChecker._loc_out_of_range(151, "51-150") is True
        assert PipelineChecker._loc_out_of_range(100, "") is False


# ===========================================================================
# Tests — Parameter resolvability
# ===========================================================================


class TestParameterResolvability:
    """Test the parameter resolvability gate."""

    def test_all_resolved_passes(self, tmp_path: Path):
        out_dir = _write_fixture(
            tmp_path,
            parameter_resolvability={
                "checkout_api-dashboard": {
                    "service_name": {
                        "status": "resolved",
                        "source_path": "spec.targets[0].name",
                    },
                    "criticality": {
                        "status": "resolved",
                        "source_path": "spec.business.criticality",
                    },
                },
            },
        )
        checker = PipelineChecker(out_dir)
        report = checker.run()

        param_gate = next(g for g in report.gates if "parameter-resolvability" in g.gate_id)
        assert param_gate.result == GateOutcome.PASS
        assert "2 parameter source(s) resolve" in param_gate.reason

    def test_unresolved_parameters_fails(self, tmp_path: Path):
        out_dir = _write_fixture(
            tmp_path,
            parameter_resolvability={
                "checkout_api-dashboard": {
                    "service_name": {
                        "status": "resolved",
                        "source_path": "spec.targets[0].name",
                    },
                    "latency_p99": {
                        "status": "unresolved",
                        "source_path": "spec.requirements.latencyP99",
                        "reason": "field is empty",
                    },
                },
            },
        )
        checker = PipelineChecker(out_dir)
        report = checker.run()

        param_gate = next(g for g in report.gates if "parameter-resolvability" in g.gate_id)
        assert param_gate.result == GateOutcome.FAIL
        assert "1/2" in param_gate.reason
        assert param_gate.blocking is False  # Warning, not blocking

    def test_no_resolvability_data_skipped(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert any("parameter-resolvability" in s for s in report.skipped)

    def test_unresolved_does_not_break_health(self, tmp_path: Path):
        """Parameter resolvability issues are warnings, not blocks."""
        out_dir = _write_fixture(
            tmp_path,
            parameter_resolvability={
                "checkout_api-dashboard": {
                    "latency_p99": {
                        "status": "unresolved",
                        "source_path": "spec.requirements.latencyP99",
                        "reason": "field is empty",
                    },
                },
            },
        )
        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert report.is_healthy is True  # Non-blocking


# ===========================================================================
# Tests — Min-coverage threshold
# ===========================================================================


class TestMinCoverage:
    """Test the --min-coverage threshold enforcement."""

    def test_coverage_meets_threshold_passes(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        # Set overallCoverage to 0.6
        meta_path = out_dir / "onboarding-metadata.json"
        data = json.loads(meta_path.read_text())
        data["coverage"]["overallCoverage"] = 0.6
        meta_path.write_text(json.dumps(data))

        checker = PipelineChecker(out_dir, min_coverage=0.5)
        report = checker.run()

        cov_gate = next(g for g in report.gates if "min-coverage" in g.gate_id)
        assert cov_gate.result == GateOutcome.PASS
        assert "60%" in cov_gate.reason

    def test_coverage_below_threshold_fails(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        # overallCoverage defaults to 0.0 in the fixture
        checker = PipelineChecker(out_dir, min_coverage=0.5)
        report = checker.run()

        cov_gate = next(g for g in report.gates if "min-coverage" in g.gate_id)
        assert cov_gate.result == GateOutcome.FAIL
        assert cov_gate.blocking is True
        assert "0%" in cov_gate.reason
        assert "50%" in cov_gate.reason

    def test_no_min_coverage_skips_gate(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)  # No min_coverage
        report = checker.run()

        assert not any("min-coverage" in g.gate_id for g in report.gates)

    def test_min_coverage_failure_makes_unhealthy(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir, min_coverage=0.5)
        report = checker.run()

        assert report.is_healthy is False


# ===========================================================================
# Tests — Report
# ===========================================================================


class TestPipelineCheckReport:
    """Test the report structure and output."""

    def test_healthy_report(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert report.is_healthy is True
        assert report.total_gates >= 3  # structural, checksum, gap-parity at minimum
        assert report.passed >= 3
        assert report.failed == 0

    def test_unhealthy_report(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)

        # Tamper to cause checksum failure
        manifest_path = out_dir / "test-project-artifact-manifest.yaml"
        manifest_path.write_text("tampered!")

        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert report.is_healthy is False
        assert report.failed >= 1
        assert len(report.blocking_failures) >= 1

    def test_to_text_output(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        text = report.to_text()
        assert "Pipeline Integrity: HEALTHY" in text
        assert "test-project" in text
        assert "PASS" in text

    def test_summary_dict(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        summary = report.summary()
        assert summary["is_healthy"] is True
        assert summary["project_id"] == "test-project"
        assert summary["total_gates"] >= 3
        assert isinstance(summary["gates"], list)
        assert all("gate_id" in g for g in summary["gates"])

    def test_write_json(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        json_path = tmp_path / "report.json"
        report.write_json(json_path)

        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["is_healthy"] is True
        assert data["project_id"] == "test-project"

    def test_warnings_for_zero_coverage(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert any("0%" in w for w in report.warnings)

    def test_warnings_for_no_task_mapping(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert any("artifact_task_mapping" in w for w in report.warnings)


# ===========================================================================
# Tests — File not found
# ===========================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_output_dir_raises(self, tmp_path: Path):
        checker = PipelineChecker(tmp_path / "nonexistent")
        with pytest.raises(FileNotFoundError, match="onboarding-metadata.json"):
            checker.run()

    def test_custom_task_and_trace_ids(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir, task_id="CUSTOM-001", trace_id="trace-abc")
        report = checker.run()

        for gate in report.gates:
            assert gate.task_id == "CUSTOM-001"
            assert gate.trace_id == "trace-abc"
            assert gate.gate_id.startswith("CUSTOM-001-")

    def test_empty_coverage_gaps(self, tmp_path: Path):
        """When there are no gaps, gap parity is skipped."""
        out_dir = _write_fixture(tmp_path)

        meta_path = out_dir / "onboarding-metadata.json"
        data = json.loads(meta_path.read_text())
        data["coverage"]["gaps"] = []
        meta_path.write_text(json.dumps(data))

        checker = PipelineChecker(out_dir)
        report = checker.run()

        assert any("gap-parity" in s for s in report.skipped)


# ===========================================================================
# Tests — Service metadata gate
# ===========================================================================


class TestServiceMetadataGate:
    """Test the service metadata validation gate (gate 9)."""

    def test_valid_service_metadata_passes(self, tmp_path: Path):
        out_dir = _write_fixture(
            tmp_path,
            service_metadata={
                "emailservice": {
                    "transport_protocol": "grpc",
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
        assert svc_gate.result == GateOutcome.PASS

    def test_missing_transport_protocol_fails(self, tmp_path: Path):
        out_dir = _write_fixture(
            tmp_path,
            service_metadata={
                "emailservice": {"schema_contract": "demo.proto"},
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

    def test_absent_service_metadata_warns(self, tmp_path: Path):
        out_dir = _write_fixture(tmp_path)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        # Should be a warning, not a gate
        assert any("service_metadata" in w for w in report.warnings)
        assert not any("service-metadata" in g.gate_id for g in report.gates)


# ===========================================================================
# Tests — Protocol calibration cross-check
# ===========================================================================


class TestProtocolCalibrationCrossCheck:
    """Test the protocol mismatch cross-check in the design calibration gate."""

    def _metadata_with_protocol_hints(self, protocol="grpc") -> dict:
        """Build calibration hints + service_metadata for cross-check testing."""
        return {
            "design_calibration_hints": {
                "dashboard": {
                    "expected_depth": "comprehensive",
                    "expected_loc_range": ">150",
                    "red_flag": "test",
                },
                f"dockerfile_emailservice": {
                    "expected_depth": "standard",
                    "expected_loc_range": "<=50",
                    "red_flag": "test",
                    "transport_protocol": protocol,
                },
                f"client_emailservice": {
                    "expected_depth": "standard",
                    "expected_loc_range": "51-300",
                    "red_flag": "test",
                    "transport_protocol": protocol,
                },
            },
            "service_metadata": {
                "emailservice": {
                    "transport_protocol": protocol,
                },
            },
        }

    def test_matching_protocol_passes(self, tmp_path: Path):
        overrides = self._metadata_with_protocol_hints("grpc")
        out_dir = _write_fixture(tmp_path, **overrides)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        cal_gate = next(g for g in report.gates if "calibration" in g.gate_id)
        # Should not have protocol mismatch issues
        assert not any(
            e.type == "protocol_calibration_mismatch"
            for e in (cal_gate.evidence or [])
        )

    def test_mismatched_protocol_detected(self, tmp_path: Path):
        overrides = self._metadata_with_protocol_hints("grpc")
        # Override service_metadata to declare HTTP while hints say gRPC
        overrides["service_metadata"]["emailservice"]["transport_protocol"] = "http"
        out_dir = _write_fixture(tmp_path, **overrides)
        checker = PipelineChecker(out_dir)
        report = checker.run()

        cal_gate = next(g for g in report.gates if "calibration" in g.gate_id)
        assert cal_gate.result == GateOutcome.FAIL
        assert any(
            e.type == "protocol_calibration_mismatch"
            for e in (cal_gate.evidence or [])
        )
