"""
Tests for the Three Questions diagnostic.

Verifies the structured diagnostic ordering (Q1 → Q2 → Q3) and the
"stop at first failure" behavior.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path

import pytest

from contextcore.contracts.a2a.three_questions import (
    DiagnosticResult,
    QuestionStatus,
    ThreeQuestionsDiagnostic,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_export_fixture(tmp_path: Path, **overrides) -> Path:
    """Build a realistic export output directory. Returns the output dir."""
    out_dir = tmp_path / "out" / "test-export"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Source manifest
    source_content = "project:\n  id: test-project\n"
    source_path = tmp_path / "source-manifest.yaml"
    source_path.write_text(source_content, encoding="utf-8")
    source_file_checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()

    # Artifact manifest
    manifest_content = textwrap.dedent("""\
        artifacts:
          - id: api-dashboard
            type: dashboard
            status: needed
          - id: api-rules
            type: prometheus_rule
            status: needed
    """)
    manifest_path = out_dir / "test-project-artifact-manifest.yaml"
    manifest_path.write_text(manifest_content, encoding="utf-8")
    manifest_checksum = _sha256(manifest_content)

    # Project context CRD
    crd_content = "apiVersion: contextcore.io/v1\nkind: ProjectContext\n"
    crd_path = out_dir / "test-project-projectcontext.yaml"
    crd_path.write_text(crd_content, encoding="utf-8")
    crd_checksum = _sha256(crd_content)

    metadata = {
        "version": "1.0.0",
        "schema": "contextcore.io/onboarding-metadata/v1",
        "project_id": "test-project",
        "artifact_manifest_path": "test-project-artifact-manifest.yaml",
        "project_context_path": "test-project-projectcontext.yaml",
        "generated_at": "2026-02-14T12:00:00.000000",
        "artifact_types": {
            "dashboard": {"output_ext": ".json", "parameter_keys": ["criticality"]},
            "prometheus_rule": {"output_ext": ".yaml", "parameter_keys": ["alertSeverity"]},
        },
        "parameter_schema": {
            "dashboard": ["criticality", "datasources"],
            "prometheus_rule": ["alertSeverity", "availabilityThreshold"],
        },
        "coverage": {
            "totalRequired": 2,
            "totalExisting": 0,
            "totalOutdated": 0,
            "overallCoverage": 0.0,
            "byTarget": [{
                "target": "api",
                "namespace": "default",
                "requiredCount": 2,
                "existingCount": 0,
                "coveragePercent": 0.0,
                "gaps": ["api-dashboard", "api-rules"],
            }],
            "byType": {"dashboard": 1, "prometheus_rule": 1},
            "gaps": ["api-dashboard", "api-rules"],
        },
        "artifact_manifest_checksum": manifest_checksum,
        "project_context_checksum": crd_checksum,
        "source_checksum": source_file_checksum,
        "source_path_relative": "source-manifest.yaml",
        "file_ownership": {
            "grafana/api-dashboard.json": {
                "artifact_ids": ["api-dashboard"],
                "artifact_types": ["dashboard"],
                "scope": "primary",
                "task_ids": [],
            },
            "prometheus/api-rules.yaml": {
                "artifact_ids": ["api-rules"],
                "artifact_types": ["prometheus_rule"],
                "scope": "primary",
                "task_ids": [],
            },
        },
    }
    metadata.update(overrides)
    (out_dir / "onboarding-metadata.json").write_text(json.dumps(metadata, indent=2))
    return out_dir


def _write_ingestion_dir(tmp_path: Path, *, with_result: bool = True) -> Path:
    """Create a plan ingestion output directory."""
    ing_dir = tmp_path / "out" / "plan-ingestion"
    ing_dir.mkdir(parents=True, exist_ok=True)

    if with_result:
        result = {
            "features": [
                {"id": "api-dashboard", "type": "dashboard"},
                {"id": "api-rules", "type": "prometheus_rule"},
            ],
            "complexity_score": 35,
            "route": "prime_contractor",
        }
        (ing_dir / "plan-result.json").write_text(json.dumps(result, indent=2))

    return ing_dir


def _write_artisan_dir(tmp_path: Path, *, with_finalize: bool = True) -> Path:
    """Create an artisan workflow output directory."""
    art_dir = tmp_path / "out" / "artisan"
    art_dir.mkdir(parents=True, exist_ok=True)

    # Design handoff
    design = {"schema_version": "v1", "enriched_seed_path": str(tmp_path / "out" / "test-export")}
    (art_dir / "design-handoff.json").write_text(json.dumps(design, indent=2))

    if with_finalize:
        finalize = {"tasks_total": 2, "tasks_succeeded": 2, "tasks_failed": 0}
        (art_dir / "finalize-report.json").write_text(json.dumps(finalize, indent=2))

    return art_dir


# ===========================================================================
# Tests — Q1: Is the contract complete?
# ===========================================================================


class TestQuestion1:
    """Test Q1 (Export layer) checks."""

    def test_healthy_export_passes_q1(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        q1 = result.questions[0]
        assert q1.number == 1
        assert q1.status == QuestionStatus.PASS
        assert any(c.name == "artifact-manifest-populated" for c in q1.checks)

    def test_missing_metadata_fails_q1(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        diag = ThreeQuestionsDiagnostic(empty_dir)
        with pytest.raises(FileNotFoundError):
            diag.run()

    def test_tampered_checksums_fail_q1(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)

        # Tamper artifact manifest
        (out_dir / "test-project-artifact-manifest.yaml").write_text("tampered!")

        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        q1 = result.questions[0]
        assert q1.status == QuestionStatus.FAIL
        assert "Q1" in result.start_here

    def test_missing_required_field_fails_q1(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)

        meta_path = out_dir / "onboarding-metadata.json"
        data = json.loads(meta_path.read_text())
        del data["source_checksum"]
        meta_path.write_text(json.dumps(data))

        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        q1 = result.questions[0]
        assert q1.status == QuestionStatus.FAIL

    def test_empty_manifest_fails_q1(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)

        meta_path = out_dir / "onboarding-metadata.json"
        data = json.loads(meta_path.read_text())
        data["coverage"]["totalRequired"] = 0
        meta_path.write_text(json.dumps(data))

        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        q1 = result.questions[0]
        assert q1.status == QuestionStatus.FAIL
        assert any("artifact-manifest-populated" in c.name and not c.passed for c in q1.checks)

    def test_parameter_schema_complete_check(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        q1 = result.questions[0]
        param_check = next((c for c in q1.checks if "parameter-schema" in c.name), None)
        assert param_check is not None
        assert param_check.passed is True

    def test_missing_parameter_schema_warns(self, tmp_path: Path):
        out_dir = _write_export_fixture(
            tmp_path,
            parameter_schema={"dashboard": ["criticality"]},  # Missing prometheus_rule
        )
        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        q1 = result.questions[0]
        param_check = next((c for c in q1.checks if "parameter-schema" in c.name), None)
        assert param_check is not None
        assert param_check.passed is False


# ===========================================================================
# Tests — Q2: Was the contract faithfully translated?
# ===========================================================================


class TestQuestion2:
    """Test Q2 (Plan Ingestion layer) checks."""

    def test_no_ingestion_dir_skips_q2(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        q2 = result.questions[1]
        assert q2.status == QuestionStatus.SKIPPED

    def test_valid_ingestion_passes_q2(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        ing_dir = _write_ingestion_dir(tmp_path)

        diag = ThreeQuestionsDiagnostic(out_dir, ingestion_dir=ing_dir)
        result = diag.run()

        q2 = result.questions[1]
        assert q2.status == QuestionStatus.PASS

    def test_nonexistent_ingestion_dir_fails_q2(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)

        diag = ThreeQuestionsDiagnostic(out_dir, ingestion_dir=tmp_path / "nonexistent")
        result = diag.run()

        q2 = result.questions[1]
        assert q2.status == QuestionStatus.FAIL
        assert "Q2" in result.start_here

    def test_parse_coverage_check(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        ing_dir = _write_ingestion_dir(tmp_path)

        diag = ThreeQuestionsDiagnostic(out_dir, ingestion_dir=ing_dir)
        result = diag.run()

        q2 = result.questions[1]
        parse_check = next((c for c in q2.checks if "parse-coverage" in c.name), None)
        assert parse_check is not None
        assert parse_check.passed is True

    def test_missing_parse_feature_detected(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        ing_dir = tmp_path / "out" / "plan-ingestion"
        ing_dir.mkdir(parents=True, exist_ok=True)

        # Result with only one feature extracted (should be two)
        result_data = {
            "features": [{"id": "api-dashboard", "type": "dashboard"}],
            "complexity_score": 25,
            "route": "prime_contractor",
        }
        (ing_dir / "plan-result.json").write_text(json.dumps(result_data))

        diag = ThreeQuestionsDiagnostic(out_dir, ingestion_dir=ing_dir)
        result = diag.run()

        q2 = result.questions[1]
        parse_check = next((c for c in q2.checks if "parse-coverage" in c.name), None)
        assert parse_check is not None
        assert parse_check.passed is False
        assert "api-rules" in parse_check.detail

    def test_routing_check_correct(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        ing_dir = _write_ingestion_dir(tmp_path)

        diag = ThreeQuestionsDiagnostic(out_dir, ingestion_dir=ing_dir)
        result = diag.run()

        q2 = result.questions[1]
        route_check = next((c for c in q2.checks if "routing" in c.name), None)
        assert route_check is not None
        assert route_check.passed is True


# ===========================================================================
# Tests — Q3: Was the translated plan faithfully executed?
# ===========================================================================


class TestQuestion3:
    """Test Q3 (Artisan layer) checks."""

    def test_no_artisan_dir_skips_q3(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        q3 = result.questions[2]
        assert q3.status == QuestionStatus.SKIPPED

    def test_valid_artisan_passes_q3(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        art_dir = _write_artisan_dir(tmp_path)

        diag = ThreeQuestionsDiagnostic(out_dir, artisan_dir=art_dir)
        result = diag.run()

        q3 = result.questions[2]
        assert q3.status == QuestionStatus.PASS

    def test_nonexistent_artisan_dir_fails_q3(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)

        diag = ThreeQuestionsDiagnostic(out_dir, artisan_dir=tmp_path / "nonexistent")
        result = diag.run()

        q3 = result.questions[2]
        assert q3.status == QuestionStatus.FAIL
        assert "Q3" in result.start_here

    def test_finalize_all_succeeded(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        art_dir = _write_artisan_dir(tmp_path)

        diag = ThreeQuestionsDiagnostic(out_dir, artisan_dir=art_dir)
        result = diag.run()

        q3 = result.questions[2]
        fin_check = next((c for c in q3.checks if "finalize" in c.name), None)
        assert fin_check is not None
        assert fin_check.passed is True

    def test_finalize_with_failures(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        art_dir = tmp_path / "out" / "artisan"
        art_dir.mkdir(parents=True, exist_ok=True)

        # Design handoff
        (art_dir / "design-handoff.json").write_text(json.dumps({"schema_version": "v1"}))

        # Finalize with failures
        finalize = {"tasks_total": 2, "tasks_succeeded": 1, "tasks_failed": 1}
        (art_dir / "finalize-report.json").write_text(json.dumps(finalize))

        diag = ThreeQuestionsDiagnostic(out_dir, artisan_dir=art_dir)
        result = diag.run()

        q3 = result.questions[2]
        fin_check = next((c for c in q3.checks if "finalize-all" in c.name), None)
        assert fin_check is not None
        assert fin_check.passed is False
        assert q3.status == QuestionStatus.FAIL


# ===========================================================================
# Tests — Stop-at-first-failure behavior
# ===========================================================================


class TestDiagnosticOrdering:
    """Test the core principle: stop at the first failure."""

    def test_q1_failure_blocks_q2_q3(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)

        # Tamper to cause Q1 failure
        (out_dir / "test-project-artifact-manifest.yaml").write_text("broken!")

        diag = ThreeQuestionsDiagnostic(
            out_dir,
            ingestion_dir=_write_ingestion_dir(tmp_path),
            artisan_dir=_write_artisan_dir(tmp_path),
        )
        result = diag.run()

        assert result.questions[0].status == QuestionStatus.FAIL
        assert result.questions[1].status == QuestionStatus.NOT_REACHED
        assert result.questions[2].status == QuestionStatus.NOT_REACHED
        assert "Q1" in result.start_here

    def test_q2_failure_blocks_q3(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)

        diag = ThreeQuestionsDiagnostic(
            out_dir,
            ingestion_dir=tmp_path / "nonexistent",
            artisan_dir=_write_artisan_dir(tmp_path),
        )
        result = diag.run()

        assert result.questions[0].status == QuestionStatus.PASS
        assert result.questions[1].status == QuestionStatus.FAIL
        assert result.questions[2].status == QuestionStatus.NOT_REACHED
        assert "Q2" in result.start_here

    def test_all_pass_full_pipeline(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)

        diag = ThreeQuestionsDiagnostic(
            out_dir,
            ingestion_dir=_write_ingestion_dir(tmp_path),
            artisan_dir=_write_artisan_dir(tmp_path),
        )
        result = diag.run()

        assert result.all_passed is True
        assert "All clear" in result.start_here


# ===========================================================================
# Tests — Report output
# ===========================================================================


class TestDiagnosticOutput:
    """Test output formatting and serialization."""

    def test_to_text_includes_all_questions(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        text = result.to_text()
        assert "Q1" in text
        assert "Q2" in text
        assert "Q3" in text
        assert "test-project" in text

    def test_summary_dict_structure(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        summary = result.summary()
        assert summary["project_id"] == "test-project"
        assert len(summary["questions"]) == 3
        for q in summary["questions"]:
            assert "number" in q
            assert "title" in q
            assert "status" in q
            assert "checks" in q

    def test_write_json(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        json_path = tmp_path / "diagnostic.json"
        result.write_json(json_path)

        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["project_id"] == "test-project"
        assert len(data["questions"]) == 3

    def test_unhealthy_text_shows_start_here(self, tmp_path: Path):
        out_dir = _write_export_fixture(tmp_path)
        (out_dir / "test-project-artifact-manifest.yaml").write_text("broken!")

        diag = ThreeQuestionsDiagnostic(out_dir)
        result = diag.run()

        text = result.to_text()
        assert "START HERE" in text
        assert "FAIL" in text
