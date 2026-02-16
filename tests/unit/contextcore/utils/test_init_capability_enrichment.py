"""Tests for capability index enrichment in init and init-from-plan."""

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from contextcore.utils.capability_index import clear_cache


@pytest.fixture(autouse=True)
def _clear_cap_cache():
    clear_cache()
    yield
    clear_cache()


def _make_index_dir(tmp_path: Path) -> Path:
    """Create a capability index directory with principles, patterns, capabilities."""
    index_dir = tmp_path / "docs" / "capability-index"
    index_dir.mkdir(parents=True)
    (index_dir / "contextcore.agent.yaml").write_text(
        textwrap.dedent("""\
            version: "1.10.1"
            capabilities:
              - capability_id: contextcore.insight.emit
                category: action
                maturity: stable
                summary: Emit agent insights
                triggers:
                  - "emit insight"
                  - "agent knowledge"
              - capability_id: contextcore.task.track
                category: action
                maturity: stable
                summary: Track tasks as spans
                triggers:
                  - "track task"
                  - "task tracking"
              - capability_id: contextcore.handoff.typed
                category: action
                maturity: stable
                summary: Typed agent handoffs
                triggers:
                  - "agent handoff"
                  - "multi-agent"
            design_principles:
              - id: typed_over_prose
                principle: All data exchange uses typed schemas
                rationale: Prevents ambiguity
                applies_to:
                  - contextcore.insight.emit
                  - contextcore.task.track
              - id: prescriptive_over_descriptive
                principle: Declare what should happen and verify
                applies_to:
                  - contextcore.task.track
              - id: observable_contracts
                principle: Every contract emits telemetry
                applies_to:
                  - contextcore.contract.propagation
            patterns:
              - pattern_id: typed_handoff
                name: Typed Handoff
                summary: Agent-to-agent handoffs use typed contracts
                capabilities:
                  - contextcore.handoff.typed
              - pattern_id: contract_validation
                name: Contract Validation
                summary: Validate contracts at boundaries
                capabilities:
                  - contextcore.contract.propagation
        """),
        encoding="utf-8",
    )
    return index_dir


# ── enrich_template_from_capability_index ─────────────────────────


class TestEnrichTemplate:
    def test_with_index(self, tmp_path: Path):
        from contextcore.cli.init_from_plan_ops import (
            build_v2_manifest_template,
            enrich_template_from_capability_index,
        )

        index_dir = _make_index_dir(tmp_path)
        manifest = build_v2_manifest_template("test-project")
        enrich_template_from_capability_index(manifest, index_dir=index_dir)

        constraints = manifest["guidance"]["constraints"]
        assert any(c["id"].startswith("C-PRINCIPLE-") for c in constraints)
        # Check that a principle rule was injected
        principle_constraints = [
            c for c in constraints if c["id"].startswith("C-PRINCIPLE-")
        ]
        assert len(principle_constraints) >= 1
        assert all(c["severity"] == "advisory" for c in principle_constraints)

    def test_with_patterns(self, tmp_path: Path):
        from contextcore.cli.init_from_plan_ops import (
            build_v2_manifest_template,
            enrich_template_from_capability_index,
        )

        index_dir = _make_index_dir(tmp_path)
        manifest = build_v2_manifest_template("test-project")
        enrich_template_from_capability_index(manifest, index_dir=index_dir)

        preferences = manifest["guidance"]["preferences"]
        pattern_prefs = [
            p for p in preferences if p["id"].startswith("P-PATTERN-")
        ]
        assert len(pattern_prefs) >= 1

    def test_without_index_unchanged(self, tmp_path: Path):
        from contextcore.cli.init_from_plan_ops import (
            build_v2_manifest_template,
            enrich_template_from_capability_index,
        )

        manifest = build_v2_manifest_template("test-project")
        original_constraints = list(manifest["guidance"]["constraints"])
        original_prefs = list(manifest["guidance"]["preferences"])

        enrich_template_from_capability_index(
            manifest, index_dir=tmp_path / "nonexistent"
        )

        assert manifest["guidance"]["constraints"] == original_constraints
        assert manifest["guidance"]["preferences"] == original_prefs


# ── infer_init_from_plan with capability matching ─────────────────


class TestInferCapabilityMatching:
    def test_matches_capabilities_from_plan(self, tmp_path: Path):
        from contextcore.cli.init_from_plan_ops import (
            build_v2_manifest_template,
            infer_init_from_plan,
        )

        _make_index_dir(tmp_path)
        manifest = build_v2_manifest_template("test-project")
        plan_text = "## Goals\n- Emit insight for each decision\n- Track task progress via spans\n"

        result = infer_init_from_plan(
            manifest_data=manifest,
            plan_text=plan_text,
            requirements_text="99.9% availability SLO",
            project_root=str(tmp_path),
            emit_guidance_questions=False,
        )

        assert "matched_capabilities" in result
        assert len(result["matched_capabilities"]) >= 1

    def test_records_capability_inferences(self, tmp_path: Path):
        from contextcore.cli.init_from_plan_ops import (
            build_v2_manifest_template,
            infer_init_from_plan,
        )

        _make_index_dir(tmp_path)
        manifest = build_v2_manifest_template("test-project")
        plan_text = "The system should emit insight for every agent decision."

        result = infer_init_from_plan(
            manifest_data=manifest,
            plan_text=plan_text,
            requirements_text="",
            project_root=str(tmp_path),
            emit_guidance_questions=False,
        )

        cap_inferences = [
            inf for inf in result["inferences"]
            if inf["field_path"] == "capability_match"
        ]
        assert len(cap_inferences) >= 1
        assert cap_inferences[0]["source"] == "capability_index:trigger_match"
        assert cap_inferences[0]["confidence"] == 0.75

    def test_readiness_includes_capability_check(self, tmp_path: Path):
        from contextcore.cli.init_from_plan_ops import (
            build_v2_manifest_template,
            infer_init_from_plan,
        )

        _make_index_dir(tmp_path)
        manifest = build_v2_manifest_template("test-project")
        plan_text = "Emit insight and track task progress."

        result = infer_init_from_plan(
            manifest_data=manifest,
            plan_text=plan_text,
            requirements_text="99.9% availability",
            project_root=str(tmp_path),
            emit_guidance_questions=False,
        )

        checks = result["downstream_readiness"]["checks"]
        cap_check = next(
            (c for c in checks if c["check"] == "capability_coverage"), None
        )
        assert cap_check is not None
        assert cap_check["status"] == "pass"

    def test_no_index_unchanged(self, tmp_path: Path):
        from contextcore.cli.init_from_plan_ops import (
            build_v2_manifest_template,
            infer_init_from_plan,
        )

        manifest = build_v2_manifest_template("test-project")
        plan_text = "## Goals\n- Build authentication system\n"

        result = infer_init_from_plan(
            manifest_data=manifest,
            plan_text=plan_text,
            requirements_text="",
            project_root=str(tmp_path / "nonexistent"),
            emit_guidance_questions=False,
        )

        # No matched capabilities when index doesn't exist
        assert "matched_capabilities" not in result

        # Readiness still has the check but status is warn
        checks = result["downstream_readiness"]["checks"]
        cap_check = next(
            (c for c in checks if c["check"] == "capability_coverage"), None
        )
        assert cap_check is not None
        assert cap_check["status"] == "warn"
