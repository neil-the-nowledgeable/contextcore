"""Tests for contextcore polish --output-dir inventory integration and pipeline readiness."""

import json

import pytest
from click.testing import CliRunner

from contextcore.cli.polish import polish, polish_file


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def plan_file(tmp_path):
    """A minimal plan that passes polish checks."""
    content = """\
# Test Plan

## Overview

**Objectives:** Test objectives here.

**Goals:**
- Goal 1

## Functional Requirements

- FR-001: Requirement

## Risks

- Risk 1

## Validation

- Test 1
"""
    f = tmp_path / "test-plan.md"
    f.write_text(content)
    return f


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "polish-out"


class TestPolishOutputDir:
    def test_writes_polish_report_json(self, runner, plan_file, output_dir):
        """--output-dir produces polish-report.json."""
        result = runner.invoke(
            polish,
            [str(plan_file), "--output-dir", str(output_dir)],
        )
        assert result.exit_code == 0, result.output
        report_file = output_dir / "polish-report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert "summary" in data[0]

    def test_creates_inventory_entry(self, runner, plan_file, output_dir):
        """--output-dir registers polish.polish_report in run-provenance.json."""
        result = runner.invoke(
            polish,
            [str(plan_file), "--output-dir", str(output_dir)],
        )
        assert result.exit_code == 0, result.output
        prov_file = output_dir / "run-provenance.json"
        assert prov_file.exists()
        payload = json.loads(prov_file.read_text())
        assert payload["version"] == "2.0.0"
        ids = [e["artifact_id"] for e in payload["artifact_inventory"]]
        assert "polish.polish_report" in ids

    def test_extend_accumulates_with_create(self, runner, plan_file, output_dir):
        """Polish extends inventory that create already wrote."""
        from contextcore.cli.core import create as create_cmd

        # Run create first
        runner.invoke(
            create_cmd,
            ["--name", "ctx", "--project", "proj", "--output-dir", str(output_dir)],
        )
        # Then polish into same dir
        result = runner.invoke(
            polish,
            [str(plan_file), "--output-dir", str(output_dir)],
        )
        assert result.exit_code == 0, result.output

        payload = json.loads((output_dir / "run-provenance.json").read_text())
        ids = [e["artifact_id"] for e in payload["artifact_inventory"]]
        assert "create.project_context" in ids
        assert "polish.polish_report" in ids
        assert len(ids) == 2

    def test_inventory_entry_has_correct_fields(self, runner, plan_file, output_dir):
        """Inventory entry has role, stage, consumers, etc."""
        runner.invoke(
            polish,
            [str(plan_file), "--output-dir", str(output_dir)],
        )
        payload = json.loads((output_dir / "run-provenance.json").read_text())
        entry = payload["artifact_inventory"][0]
        assert entry["role"] == "polish_report"
        assert entry["stage"] == "polish"
        assert entry["produced_by"] == "contextcore.polish"
        assert "artisan.review" in entry["consumers"]


# ---------------------------------------------------------------------------
# Pipeline readiness checks
# ---------------------------------------------------------------------------

@pytest.fixture
def plan_with_phases(tmp_path):
    """Full plan with phases, metadata, REQ-IDs, deliverables, validation."""
    content = """\
# Cross-Repo Alignment Plan

## Overview

**Objectives:** Align all repos.

**Goals:**
- Goal 1

## Functional Requirements

- FR-001: First requirement
- REQ-002: Second requirement

## Phase 1: Setup Infrastructure

**Satisfies:** REQ-002, FR-001
**Depends on:** None
**Repo:** contextcore

**Deliverables:**
- [ ] `src/setup.py` — Setup module

**Validation:** Unit tests pass, linting clean

## Phase 2: Core Implementation

**Satisfies:** FR-001
**Repo:** contextcore

**Deliverables:**
- [ ] `src/core.py` — Core module

**Validation:** Integration tests pass

## Risks

- Risk of scope creep

## Validation

- All unit tests pass
- Integration smoke test green
"""
    f = tmp_path / "plan-with-phases.md"
    f.write_text(content)
    return f


@pytest.fixture
def plan_without_phases(tmp_path):
    """Passes structure checks but has no phase headings."""
    content = """\
# Simple Plan

## Overview

**Objectives:** Build something.

**Goals:**
- Ship it

## Functional Requirements

- FR-001: A requirement

## Risks

- Might not work

## Validation

- Test it
"""
    f = tmp_path / "plan-no-phases.md"
    f.write_text(content)
    return f


@pytest.fixture
def plan_phases_no_metadata(tmp_path):
    """Has phase headings but no Satisfies/Repo/Deliverables lines."""
    content = """\
# Bare Phases Plan

## Overview

**Objectives:** Do things.

**Goals:**
- Finish

## Phase 1: First thing

Just some prose about what to do.

## Phase 2: Second thing

More prose here.

## Risks

- Something might go wrong

## Validation

- Check it
"""
    f = tmp_path / "plan-bare-phases.md"
    f.write_text(content)
    return f


class TestPipelineReadiness:
    """Tests for the 6 pipeline-* readiness checks."""

    def test_full_plan_passes_all_pipeline_checks(self, plan_with_phases):
        """All 6 pipeline checks pass on a well-formed plan."""
        result = polish_file(plan_with_phases)
        pipeline_checks = [c for c in result.checks if c.check_id.startswith("pipeline-")]
        assert len(pipeline_checks) == 6
        for c in pipeline_checks:
            assert c.status == "passed", f"{c.check_id} should pass, got {c.status}: {c.message}"

    def test_no_phases_fails_pipeline_phases_exist(self, plan_without_phases):
        """Missing phases are detected."""
        result = polish_file(plan_without_phases)
        chk = next(c for c in result.checks if c.check_id == "pipeline-phases-exist")
        assert chk.status == "failed"
        assert "No phase or milestone headings" in chk.message

    def test_no_phases_skips_dependent_checks(self, plan_without_phases):
        """Metadata, deliverables, and validation are skipped when no phases exist."""
        result = polish_file(plan_without_phases)
        dependent_ids = {
            "pipeline-phase-metadata",
            "pipeline-deliverables",
            "pipeline-validation-criteria",
        }
        for c in result.checks:
            if c.check_id in dependent_ids:
                assert c.status == "skipped", f"{c.check_id} should be skipped, got {c.status}"

    def test_phases_without_metadata_fails_metadata_check(self, plan_phases_no_metadata):
        """Phases without Satisfies/Repo lines are detected."""
        result = polish_file(plan_phases_no_metadata)
        chk = next(c for c in result.checks if c.check_id == "pipeline-phase-metadata")
        assert chk.status == "failed"
        assert "no Satisfies/Depends on/Repo metadata" in chk.message

    def test_phases_without_deliverables_fails(self, plan_phases_no_metadata):
        """Missing deliverables are detected when phases exist."""
        result = polish_file(plan_phases_no_metadata)
        chk = next(c for c in result.checks if c.check_id == "pipeline-deliverables")
        assert chk.status == "failed"
        assert "no **Deliverables:**" in chk.message

    def test_no_req_ids_fails(self, tmp_path):
        """Missing REQ-IDs are detected."""
        content = """\
# Plan Without IDs

## Overview

**Objectives:** Build.
**Goals:** Ship.

## Risks

- Risk

## Validation

- Test
"""
        f = tmp_path / "no-ids.md"
        f.write_text(content)
        result = polish_file(f)
        chk = next(c for c in result.checks if c.check_id == "pipeline-req-ids-found")
        assert chk.status == "failed"
        assert "No requirement identifiers" in chk.message

    def test_no_h1_title_fails(self, tmp_path):
        """Missing H1 title is detected."""
        content = """\
## Overview

**Objectives:** Build.
**Goals:** Ship.

## Functional Requirements

- FR-001: Requirement

## Risks

- Risk

## Validation

- Test
"""
        f = tmp_path / "no-h1.md"
        f.write_text(content)
        result = polish_file(f)
        chk = next(c for c in result.checks if c.check_id == "pipeline-plan-title")
        assert chk.status == "failed"
        assert "No H1 title" in chk.message

    def test_strict_exits_nonzero_on_pipeline_failure(self, runner, plan_without_phases):
        """--strict exits with code 1 when pipeline checks fail."""
        result = runner.invoke(
            polish,
            [str(plan_without_phases), "--strict"],
        )
        assert result.exit_code == 1

    def test_detail_messages_explain_pipeline_impact(self, plan_without_phases):
        """Detail messages include pipeline stage names and expected format."""
        result = polish_file(plan_without_phases)
        chk = next(c for c in result.checks if c.check_id == "pipeline-phases-exist")
        assert chk.detail is not None
        assert "analyze-plan" in chk.detail
        assert "init-from-plan" in chk.detail
        assert "EXPECTED FORMAT" in chk.detail

    def test_total_check_count_is_14(self, plan_with_phases):
        """8 original + 6 pipeline = 14 total checks."""
        result = polish_file(plan_with_phases)
        assert len(result.checks) == 14

    def test_milestone_heading_detected(self, tmp_path):
        """'## Milestone N:' is recognized as a phase heading."""
        content = """\
# Milestone Plan

## Overview

**Objectives:** Build.
**Goals:** Ship.

## Functional Requirements

- FR-001: Requirement

## Milestone 1: First Milestone

**Satisfies:** FR-001
**Deliverables:**
- [ ] `src/m1.py` — Module
**Validation:** Tests pass

## Risks

- Risk

## Validation

- Test
"""
        f = tmp_path / "milestone-plan.md"
        f.write_text(content)
        result = polish_file(f)
        chk = next(c for c in result.checks if c.check_id == "pipeline-phases-exist")
        assert chk.status == "passed"
        assert "1 phase/milestone heading" in chk.message
