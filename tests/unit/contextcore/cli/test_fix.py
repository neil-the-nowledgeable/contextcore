"""Tests for contextcore fix — deterministic auto-remediation (Stage 1.5)."""

import json

import pytest
from click.testing import CliRunner

from contextcore.cli.fix import fix
from contextcore.cli.fix_ops import apply_fixes, FIXABLE_CHECK_IDS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "fix-out"


@pytest.fixture
def weaver_like_plan(tmp_path):
    """Overview with prose but no Objectives/Goals keywords;
    REQ-IDs in Satisfies lines but no FR section."""
    content = """\
# Weaver Cross-Repo Alignment Plan

## Overview

This plan establishes a unified schema alignment across all repositories
in the Wayfinder ecosystem. It will implement consistent field naming,
enable cross-repo discovery, and ensure backward compatibility.

## Phase 1: Schema Discovery

**Satisfies:** REQ-001, REQ-002
**Depends on:** None
**Repo:** contextcore

**Deliverables:**
- [ ] `src/schema.py` — Schema discovery module

**Validation:** Unit tests pass

## Phase 2: Field Alignment

**Satisfies:** FR-003, REQ-004
**Depends on:** Phase 1
**Repo:** contextcore

**Deliverables:**
- [ ] `src/alignment.py` — Alignment engine

**Validation:** Integration tests pass

## Risks

- Schema migration may break existing consumers

## Validation

- All repos pass cross-schema validation
"""
    f = tmp_path / "weaver-plan.md"
    f.write_text(content)
    return f


@pytest.fixture
def already_fixed_plan(tmp_path):
    """Has Objectives, Goals, and FR section (fix should be no-op)."""
    content = """\
# Already Fixed Plan

## Overview

**Objectives:** Implement unified schema alignment across repos.

**Goals:**
- Complete schema discovery
- Complete field alignment

## Functional Requirements

| ID | Source Phase |
|-----|-------------|
| REQ-001 | Phase 1: Schema Discovery |

## Phase 1: Schema Discovery

**Satisfies:** REQ-001
**Repo:** contextcore

**Deliverables:**
- [ ] `src/schema.py` — Schema module

**Validation:** Tests pass

## Risks

- Migration risk

## Validation

- All tests pass
"""
    f = tmp_path / "fixed-plan.md"
    f.write_text(content)
    return f


@pytest.fixture
def plan_needing_partial_fix(tmp_path):
    """Has Objectives but missing Goals and FR section."""
    content = """\
# Partial Plan

## Overview

**Objectives:** Build the alignment engine.

This plan will implement cross-repo field alignment.

## Phase 1: Core Work

**Satisfies:** REQ-010
**Repo:** contextcore

**Deliverables:**
- [ ] `src/core.py` — Core module

**Validation:** Tests pass

## Risks

- Scope risk

## Validation

- Integration tests
"""
    f = tmp_path / "partial-plan.md"
    f.write_text(content)
    return f


@pytest.fixture
def unfixable_plan(tmp_path):
    """Missing phases, risks, validation (all failures are not fixable)."""
    content = """\
# Bare Plan

## Overview

Just a bare overview with no structure.
"""
    f = tmp_path / "unfixable-plan.md"
    f.write_text(content)
    return f


def _get_polish_checks(plan_path):
    """Helper to run polish and return check dicts."""
    from contextcore.cli.polish import polish_file
    result = polish_file(plan_path)
    if result is None:
        return []
    return [
        {
            "check_id": c.check_id,
            "label": c.label,
            "status": c.status,
            "message": c.message,
            "detail": c.detail,
        }
        for c in result.checks
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFixOverviewObjectives:
    def test_fix_overview_objectives_extracts_from_prose(self, weaver_like_plan):
        """Objectives line inserted from intent verbs in Overview prose."""
        checks = _get_polish_checks(weaver_like_plan)
        content = weaver_like_plan.read_text()
        result = apply_fixes(content, checks, str(weaver_like_plan))

        obj_action = next(a for a in result.actions if a.check_id == "overview-objectives")
        assert obj_action.status == "fixed"
        assert obj_action.strategy == "extract_from_overview_prose"
        assert "**Objectives:**" in result.remediated_content


class TestFixOverviewGoals:
    def test_fix_overview_goals_synthesizes_from_phases(self, weaver_like_plan):
        """Goals block with bullets synthesized from phase headings."""
        checks = _get_polish_checks(weaver_like_plan)
        content = weaver_like_plan.read_text()
        result = apply_fixes(content, checks, str(weaver_like_plan))

        goals_action = next(a for a in result.actions if a.check_id == "overview-goals")
        assert goals_action.status == "fixed"
        assert goals_action.strategy == "synthesize_from_phases"
        assert "**Goals:**" in result.remediated_content
        assert "- Complete" in result.remediated_content


class TestFixRequirementsExist:
    def test_fix_requirements_exist_builds_table(self, weaver_like_plan):
        """FR table with REQ-IDs mapped to phases."""
        checks = _get_polish_checks(weaver_like_plan)
        content = weaver_like_plan.read_text()
        result = apply_fixes(content, checks, str(weaver_like_plan))

        req_action = next(a for a in result.actions if a.check_id == "requirements-exist")
        assert req_action.status == "fixed"
        assert req_action.strategy == "collect_req_ids_from_satisfies"
        assert "## Functional Requirements" in result.remediated_content
        assert "REQ-001" in result.remediated_content
        assert "FR-003" in result.remediated_content


class TestIdempotency:
    def test_fix_idempotent_on_already_fixed(self, already_fixed_plan):
        """No changes on a plan that already passes all fixable checks."""
        checks = _get_polish_checks(already_fixed_plan)
        content = already_fixed_plan.read_text()
        result = apply_fixes(content, checks, str(already_fixed_plan))

        assert result.fixed_count == 0
        assert result.remediated_content == result.original_content


class TestPartialFix:
    def test_partial_fix_applies_only_needed(self, plan_needing_partial_fix):
        """Fixed count matches actual failures (objectives passes, goals+FR fixed)."""
        checks = _get_polish_checks(plan_needing_partial_fix)
        content = plan_needing_partial_fix.read_text()
        result = apply_fixes(content, checks, str(plan_needing_partial_fix))

        obj_action = next(a for a in result.actions if a.check_id == "overview-objectives")
        assert obj_action.status == "not_applicable"  # already passes

        goals_action = next(a for a in result.actions if a.check_id == "overview-goals")
        assert goals_action.status == "fixed"

        req_action = next(a for a in result.actions if a.check_id == "requirements-exist")
        assert req_action.status == "fixed"


class TestUnfixableChecks:
    def test_unfixable_checks_skipped_with_reason(self, weaver_like_plan):
        """Skipped actions for unfixable checks have human-readable reasons."""
        checks = _get_polish_checks(weaver_like_plan)
        content = weaver_like_plan.read_text()
        result = apply_fixes(content, checks, str(weaver_like_plan))

        skipped = [a for a in result.actions if a.status == "skipped"]
        for action in skipped:
            assert action.reason is not None
            assert len(action.reason) > 10

    def test_not_applicable_for_passing_checks(self, already_fixed_plan):
        """Passing checks marked not_applicable."""
        checks = _get_polish_checks(already_fixed_plan)
        content = already_fixed_plan.read_text()
        result = apply_fixes(content, checks, str(already_fixed_plan))

        fixable_actions = [a for a in result.actions if a.check_id in FIXABLE_CHECK_IDS]
        for action in fixable_actions:
            assert action.status == "not_applicable"


class TestCLIFlags:
    def test_strict_exits_nonzero_when_fixable_remains(self, runner, unfixable_plan):
        """Exit 1 if a fixable check couldn't be fixed (overview missing = objectives can't fix)."""
        # The unfixable_plan has no Objectives keyword but also no intent verbs
        # Create a plan where objectives extraction specifically fails
        plan_path = unfixable_plan.parent / "strict-test.md"
        plan_path.write_text("""\
# Strict Test Plan

## Overview

Short.
""")
        result = runner.invoke(fix, [str(plan_path), "--strict"])
        # overview-objectives may be skipped (no intent verbs in short prose)
        # That's a fixable check that couldn't be fixed -> strict should exit 1
        assert result.exit_code == 1

    def test_dry_run_does_not_write_files(self, runner, weaver_like_plan, output_dir):
        """No remediated file written in dry-run mode."""
        result = runner.invoke(
            fix,
            [str(weaver_like_plan), "--output-dir", str(output_dir), "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert not output_dir.exists() or not (output_dir / "fix-report.json").exists()


class TestOutputArtifacts:
    def test_output_dir_writes_artifacts(self, runner, weaver_like_plan, output_dir):
        """fix-report.json + .fixed.md + inventory entry written."""
        result = runner.invoke(
            fix,
            [str(weaver_like_plan), "--output-dir", str(output_dir)],
        )
        assert result.exit_code == 0, result.output

        fixed_file = output_dir / "weaver-plan.fixed.md"
        assert fixed_file.exists()

        report_file = output_dir / "fix-report.json"
        assert report_file.exists()
        report = json.loads(report_file.read_text())
        assert "actions" in report
        assert "summary" in report
        assert report["summary"]["fixed"] > 0

    def test_inventory_entry_registered(self, runner, weaver_like_plan, output_dir):
        """fix.fix_report and fix.remediated_plan in provenance."""
        runner.invoke(
            fix,
            [str(weaver_like_plan), "--output-dir", str(output_dir)],
        )
        prov_file = output_dir / "run-provenance.json"
        assert prov_file.exists()

        payload = json.loads(prov_file.read_text())
        assert payload["version"] == "2.0.0"
        ids = [e["artifact_id"] for e in payload["artifact_inventory"]]
        assert "fix.fix_report" in ids
        assert "fix.remediated_plan" in ids


class TestPipelineTraceability:
    def test_pipeline_traceability_in_report(self, runner, weaver_like_plan, output_dir):
        """Report contains traceability section with pipeline stage traces."""
        runner.invoke(
            fix,
            [str(weaver_like_plan), "--output-dir", str(output_dir)],
        )
        report = json.loads((output_dir / "fix-report.json").read_text())
        assert "traceability" in report
        assert len(report["traceability"]) > 0

        for trace in report["traceability"]:
            assert "check_id" in trace
            assert "polish_detects" in trace
            assert "fix_remediates" in trace
            assert "init_extracts" in trace


class TestFixReportFormat:
    def test_fix_report_json_format(self, runner, weaver_like_plan, output_dir):
        """Report matches expected schema."""
        runner.invoke(
            fix,
            [str(weaver_like_plan), "--output-dir", str(output_dir)],
        )
        report = json.loads((output_dir / "fix-report.json").read_text())

        assert "source_file" in report
        assert isinstance(report["actions"], list)
        assert isinstance(report["summary"], dict)
        assert set(report["summary"].keys()) == {"fixed", "skipped", "not_applicable"}
        assert isinstance(report["traceability"], list)

        for action in report["actions"]:
            assert "check_id" in action
            assert "status" in action
            assert action["status"] in ("fixed", "skipped", "not_applicable")


class TestRemediatedPlanRepolish:
    def test_remediated_plan_passes_repolish(self, runner, weaver_like_plan, output_dir):
        """Running polish on .fixed.md produces 0 failures for fixable checks."""
        runner.invoke(
            fix,
            [str(weaver_like_plan), "--output-dir", str(output_dir)],
        )
        fixed_file = output_dir / "weaver-plan.fixed.md"
        assert fixed_file.exists()

        from contextcore.cli.polish import polish_file
        result = polish_file(fixed_file)
        assert result is not None

        fixable_failures = [
            c for c in result.checks
            if c.check_id in FIXABLE_CHECK_IDS and c.status == "failed"
        ]
        assert fixable_failures == [], (
            f"Fixable checks still failing after fix: "
            f"{[(c.check_id, c.message) for c in fixable_failures]}"
        )
