"""Tests for init-from-plan enrichments (Option 2 inline regex + Option 3 plan-analysis merge)."""

from __future__ import annotations

import pytest

from contextcore.cli.init_from_plan_ops import (
    build_v2_manifest_template,
    infer_init_from_plan,
)


# ── Fixtures ──────────────────────────────────────────────────────

PLAN_WITH_METADATA = """\
# Implementation Plan

**Date:** 2026-02-11
**Requirements:** `REQUIREMENTS.md`

## Phase 1: Bootstrap Registry (ContextCore)

**Satisfies:** REQ-1
**Repo:** ContextCore
**Depends on:** Nothing (unblocked)

Create the registry files.

**Deliverables:** 7 files created, 2 files modified
**Validation:** `weaver registry check` passes

## Phase 2: Consolidate Mappings (ContextCore)

**Satisfies:** REQ-3
**Repo:** ContextCore
**Depends on:** Phase 1 (registry exists)

Merge attribute dicts.

**Deliverables:** 1 file modified, 1 file created

## Phase 3: Align Emitter (StartD8 SDK)

**Satisfies:** REQ-2, REQ-7
**Repo:** StartD8 SDK
**Depends on:** Phase 1

Update emitter attributes.
"""

REQUIREMENTS_TEXT = """\
## REQ-1: Registry Must Cover Attributes
Description.

## REQ-2: Emitter Alignment
Description.

## REQ-3: Consolidate ATTRIBUTE_MAPPINGS
Description.
"""

PLAN_ANALYSIS_DATA = {
    "schema": "contextcore.io/plan-analysis/v1",
    "phase_metadata": [
        {
            "phase_id": "phase-1",
            "heading": "Phase 1: Bootstrap Registry (ContextCore)",
            "satisfies": ["REQ-1"],
            "depends_on": "Nothing (unblocked)",
            "repo": "ContextCore",
            "deliverables": {"summary": "7 files created, 2 files modified", "file_count": 9},
        },
        {
            "phase_id": "phase-2",
            "heading": "Phase 2: Consolidate Mappings (ContextCore)",
            "satisfies": ["REQ-3"],
            "depends_on": "Phase 1 (registry exists)",
            "repo": "ContextCore",
            "deliverables": {"summary": "1 file modified, 1 file created", "file_count": 2},
        },
        {
            "phase_id": "phase-3",
            "heading": "Phase 3: Align Emitter (StartD8 SDK)",
            "satisfies": ["REQ-2", "REQ-7"],
            "depends_on": "Phase 1",
            "repo": "StartD8 SDK",
            "deliverables": None,
        },
    ],
    "traceability_matrix": {
        "REQ-1": ["phase-1"],
        "REQ-2": ["phase-3"],
        "REQ-3": ["phase-2"],
        "REQ-7": ["phase-3"],
    },
}


# ── Helper ────────────────────────────────────────────────────────

def _run_inference(plan_text=PLAN_WITH_METADATA, req_text=REQUIREMENTS_TEXT,
                   plan_analysis=None):
    """Run infer_init_from_plan with defaults and return the result."""
    manifest_data = build_v2_manifest_template("test-project")
    return infer_init_from_plan(
        manifest_data=manifest_data,
        plan_text=plan_text,
        requirements_text=req_text,
        project_root=None,
        emit_guidance_questions=False,
        plan_analysis=plan_analysis,
    )


# ── Inline Regex Enrichment Tests (Option 2) ─────────────────────

class TestInlineSatisfiesExtraction:
    def test_satisfies_extracted(self):
        result = _run_inference()
        tactics = result["manifest_data"]["strategy"]["tactics"]
        # At least one tactic should have satisfies
        enriched = [t for t in tactics if t.get("satisfies")]
        assert len(enriched) > 0

    def test_satisfies_contains_req_ids(self):
        result = _run_inference()
        tactics = result["manifest_data"]["strategy"]["tactics"]
        # Phase 1 tactic should satisfy REQ-1
        phase1 = next((t for t in tactics if "Bootstrap" in t["description"]
                        or "Phase 1" in t["description"]), None)
        if phase1:
            assert "REQ-1" in phase1.get("satisfies", [])


class TestInlineDependsOnExtraction:
    def test_depends_on_extracted(self):
        result = _run_inference()
        tactics = result["manifest_data"]["strategy"]["tactics"]
        enriched = [t for t in tactics if t.get("dependsOn")]
        assert len(enriched) > 0

    def test_phase1_unblocked(self):
        result = _run_inference()
        tactics = result["manifest_data"]["strategy"]["tactics"]
        phase1 = next((t for t in tactics if "Bootstrap" in t["description"]
                        or "Phase 1" in t["description"]), None)
        if phase1:
            dep = phase1.get("dependsOn", "")
            assert "Nothing" in dep or dep is None or "unblocked" in dep.lower()


class TestInlineRepoExtraction:
    def test_repo_extracted(self):
        result = _run_inference()
        tactics = result["manifest_data"]["strategy"]["tactics"]
        enriched = [t for t in tactics if t.get("repo")]
        assert len(enriched) > 0

    def test_correct_repos(self):
        result = _run_inference()
        tactics = result["manifest_data"]["strategy"]["tactics"]
        for t in tactics:
            if "StartD8" in t["description"] or "Emitter" in t["description"]:
                if t.get("repo"):
                    assert "StartD8" in t["repo"]


class TestInlineDeliverablesExtraction:
    def test_deliverables_extracted(self):
        result = _run_inference()
        tactics = result["manifest_data"]["strategy"]["tactics"]
        enriched = [t for t in tactics if t.get("deliverables")]
        assert len(enriched) > 0

    def test_deliverables_have_summary(self):
        result = _run_inference()
        tactics = result["manifest_data"]["strategy"]["tactics"]
        for t in tactics:
            if t.get("deliverables"):
                assert "summary" in t["deliverables"]


# ── Requirement ID Extraction Tests ──────────────────────────────

class TestRequirementIdExtraction:
    def test_req_ids_inferred(self):
        result = _run_inference()
        inferences = result["inferences"]
        req_inf = next(
            (i for i in inferences if i["field_path"] == "requirement_ids"), None
        )
        assert req_inf is not None
        assert "REQ-1" in req_inf["value"]
        assert "REQ-2" in req_inf["value"]
        assert "REQ-3" in req_inf["value"]


# ── Plan Analysis Merge Tests (Option 3) ─────────────────────────

class TestPlanAnalysisMerge:
    def test_plan_analysis_enriches_tactics(self):
        result = _run_inference(plan_analysis=PLAN_ANALYSIS_DATA)
        tactics = result["manifest_data"]["strategy"]["tactics"]
        enriched = [t for t in tactics
                    if t.get("satisfies") or t.get("dependsOn") or t.get("repo")]
        assert len(enriched) > 0

    def test_plan_analysis_records_enrichment_inference(self):
        result = _run_inference(plan_analysis=PLAN_ANALYSIS_DATA)
        inferences = result["inferences"]
        enrichment_inf = [
            i for i in inferences
            if i["field_path"] == "strategy.tactics.enrichment"
        ]
        assert len(enrichment_inf) > 0
        assert enrichment_inf[0]["source"] == "plan_analysis:merge"


# ── Backward Compatibility Tests ─────────────────────────────────

class TestBackwardCompatibility:
    def test_no_plan_analysis_still_works(self):
        """Without plan_analysis, inline regex still populates enrichment fields."""
        result = _run_inference(plan_analysis=None)
        tactics = result["manifest_data"]["strategy"]["tactics"]
        assert len(tactics) > 0
        # Should still have basic tactic data
        for t in tactics:
            assert "id" in t
            assert "description" in t
            assert "status" in t

    def test_plain_plan_without_metadata(self):
        """A plan without Satisfies/Repo/Depends lines still produces tactics."""
        plain_plan = """\
# Simple Plan

## Phase 1: Do Something Important

This phase does something.

## Phase 2: Do Another Thing

This phase does another thing.
"""
        result = _run_inference(plan_text=plain_plan, req_text="")
        tactics = result["manifest_data"]["strategy"]["tactics"]
        assert len(tactics) >= 2

    def test_empty_plan_analysis_is_harmless(self):
        """Passing an empty plan_analysis dict doesn't crash."""
        result = _run_inference(plan_analysis={})
        tactics = result["manifest_data"]["strategy"]["tactics"]
        assert len(tactics) > 0

    def test_enrichment_inference_source_without_plan_analysis(self):
        """Without plan_analysis, enrichment source should be 'plan:phase_metadata_enrichment'."""
        result = _run_inference(plan_analysis=None)
        inferences = result["inferences"]
        enrichment_inf = [
            i for i in inferences
            if i["field_path"] == "strategy.tactics.enrichment"
        ]
        if enrichment_inf:
            assert enrichment_inf[0]["source"] == "plan:phase_metadata_enrichment"


# ── TacticV2 Model Compatibility Tests ───────────────────────────

class TestTacticV2Compatibility:
    def test_enriched_tactics_load_as_tacticv2(self):
        """Enriched tactic dicts should be loadable as TacticV2 models."""
        from contextcore.models.manifest_v2 import TacticV2

        result = _run_inference()
        tactics = result["manifest_data"]["strategy"]["tactics"]
        for tactic_dict in tactics:
            # TacticV2 should accept the new fields without error
            tactic = TacticV2(**tactic_dict)
            assert tactic.id.startswith("TAC-PLAN-")
            # Check enrichment fields are accessible
            if tactic_dict.get("satisfies"):
                assert len(tactic.satisfies) > 0
            if tactic_dict.get("repo"):
                assert tactic.repo is not None
