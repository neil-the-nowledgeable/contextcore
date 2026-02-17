"""Tests for contextcore.cli.analyze_plan_ops (Stage 1.5 plan analysis)."""

from __future__ import annotations

import json

import pytest

from contextcore.cli.analyze_plan_ops import (
    _build_dependency_graph,
    _build_traceability_matrix,
    _detect_conflicts,
    _extract_phase_metadata,
    _extract_plan_header_metadata,
    _extract_requirement_ids,
    analyze_plan,
)


# ── Fixtures ──────────────────────────────────────────────────────

SAMPLE_PLAN = """\
# Weaver Cross-Repo Alignment — Implementation Plan

**Date:** 2026-02-11
**Requirements:** `WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md`
**Companion to:** `WEAVER_REGISTRY_REQUIREMENTS.md`

---

## Overview

Seven work packages across three repos.

## Phase 1: Bootstrap Weaver Registry (ContextCore)

**Satisfies:** WEAVER_REGISTRY_REQUIREMENTS.md Phase 1 + REQ-1
**Repo:** ContextCore
**Depends on:** Nothing (unblocked)

### 1.1 Create registry manifest

Some details here.

**Deliverables:** 7 files created, 2 files modified (Makefile, CI workflow)
**Validation:** `weaver registry check` passes with zero errors

## Phase 2: Consolidate ATTRIBUTE_MAPPINGS (ContextCore)

**Satisfies:** REQ-3
**Repo:** ContextCore
**Depends on:** Phase 1 (registry exists to validate against)

Details about consolidation.

**Deliverables:** 1 file modified (`otel_genai.py`), 1 file created (test)
**Validation:** Existing tests pass

## Phase 3: Align StartD8 Emitter (StartD8 SDK)

**Satisfies:** REQ-2, REQ-7
**Repo:** StartD8 SDK
**Depends on:** Phase 1 (attribute names finalized in registry)

**Deliverables:** 1 file modified (emitter), 1 file modified (tests)

## Phase 4: Reconcile HandoffStatus (ContextCore)

**Satisfies:** REQ-4
**Repo:** ContextCore
**Depends on:** Phase 1

**Deliverables:** 3 files modified

## Phase 5: Wayfinder Registry Reference (Wayfinder)

**Satisfies:** REQ-5
**Repo:** Wayfinder
**Depends on:** Phase 1

## Phase 6: Cross-Repo CI (ContextCore + StartD8 SDK)

**Satisfies:** REQ-6
**Repo:** Both
**Depends on:** Phases 1, 3

## Phase 7: Documentation Refresh

**Satisfies:** Cleanup
**Repos:** All three
**Depends on:** Phases 1-6
"""

SAMPLE_REQUIREMENTS_A = """\
# Weaver Cross-Repo Alignment Requirements

## REQ-1: Registry Must Cover Cross-Repo Attributes

Description of requirement 1.

## REQ-2: Emitter Alignment

StartD8 emitter must align.

## REQ-3: Consolidate ATTRIBUTE_MAPPINGS

Single canonical dict.

## REQ-4: Reconcile HandoffStatus

Expand to 9 members.
"""

SAMPLE_REQUIREMENTS_B = """\
# Weaver Registry Requirements

## REQ-5: Wayfinder Reference

Point to ContextCore registry.

## REQ-6: Cross-Repo CI

CI validation across repos.

## REQ-7: Emitter Schema Validation

Validate emitter output.

## REQ-8: Multi-Project Scanning

Cross-project discovery.
"""


# ── Requirement ID Extraction Tests ──────────────────────────────

class TestExtractRequirementIds:
    def test_basic_req_ids(self):
        text = "This addresses REQ-1, REQ-2, and REQ-3."
        ids = _extract_requirement_ids(text)
        assert len(ids) == 3
        assert ids[0]["id"] == "REQ-1"
        assert ids[1]["id"] == "REQ-2"
        assert ids[2]["id"] == "REQ-3"

    def test_fr_and_nfr_ids(self):
        text = "FR-001 is functional. NFR-002 is non-functional."
        ids = _extract_requirement_ids(text)
        id_values = [i["id"] for i in ids]
        assert "FR-001" in id_values
        assert "NFR-002" in id_values

    def test_mixed_case(self):
        text = "req-1 and Req-2 and REQ-3"
        ids = _extract_requirement_ids(text)
        id_values = [i["id"] for i in ids]
        assert "REQ-1" in id_values
        assert "REQ-2" in id_values
        assert "REQ-3" in id_values

    def test_deduplication(self):
        text = "REQ-1 appears here and REQ-1 appears again."
        ids = _extract_requirement_ids(text)
        assert len(ids) == 1

    def test_title_extraction(self):
        text = "## REQ-1: Registry Must Cover Cross-Repo Attributes"
        ids = _extract_requirement_ids(text)
        assert len(ids) == 1
        assert ids[0]["id"] == "REQ-1"
        assert "Registry" in ids[0]["title"]

    def test_empty_input(self):
        ids = _extract_requirement_ids("")
        assert ids == []

    def test_no_matches(self):
        ids = _extract_requirement_ids("No requirements here.")
        assert ids == []

    def test_hyphenated_ids(self):
        text = "REQ-CDP-001 and NFR-CDP-002 are referenced."
        ids = _extract_requirement_ids(text)
        id_values = [i["id"] for i in ids]
        assert "REQ-CDP-001" in id_values
        assert "NFR-CDP-002" in id_values


# ── Phase Metadata Extraction Tests ──────────────────────────────

class TestExtractPhaseMetadata:
    def test_extracts_all_phases(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        phases = _extract_phase_metadata(lines)
        assert len(phases) == 7

    def test_phase_ids_are_sequential(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        phases = _extract_phase_metadata(lines)
        for i, phase in enumerate(phases, start=1):
            assert phase["phase_id"] == f"phase-{i}"

    def test_satisfies_extraction(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        phases = _extract_phase_metadata(lines)
        # Phase 1 satisfies REQ-1
        assert "REQ-1" in phases[0]["satisfies"]
        # Phase 2 satisfies REQ-3
        assert "REQ-3" in phases[1]["satisfies"]
        # Phase 3 satisfies REQ-2 and REQ-7
        assert "REQ-2" in phases[2]["satisfies"]
        assert "REQ-7" in phases[2]["satisfies"]

    def test_depends_on_extraction(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        phases = _extract_phase_metadata(lines)
        # Phase 1 depends on nothing
        assert phases[0]["depends_on"] == "Nothing (unblocked)"
        # Phase 2 depends on Phase 1
        assert "Phase 1" in (phases[1]["depends_on"] or "")

    def test_repo_extraction(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        phases = _extract_phase_metadata(lines)
        assert phases[0]["repo"] == "ContextCore"
        assert phases[2]["repo"] == "StartD8 SDK"
        assert phases[4]["repo"] == "Wayfinder"

    def test_deliverables_extraction(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        phases = _extract_phase_metadata(lines)
        # Phase 1 has deliverables
        d = phases[0].get("deliverables")
        assert d is not None
        assert "7 files created" in d["summary"]

    def test_empty_plan(self):
        phases = _extract_phase_metadata([])
        assert phases == []


# ── Traceability Matrix Tests ────────────────────────────────────

class TestBuildTraceabilityMatrix:
    def test_basic_traceability(self):
        phases = [
            {"phase_id": "phase-1", "satisfies": ["REQ-1"], "heading": "Phase 1"},
            {"phase_id": "phase-2", "satisfies": ["REQ-3"], "heading": "Phase 2"},
        ]
        req_inv = {
            "reqs.md": {
                "source_path": "reqs.md",
                "ids": [{"id": "REQ-1", "title": ""}, {"id": "REQ-3", "title": ""}],
            }
        }
        matrix = _build_traceability_matrix(phases, req_inv)
        assert "REQ-1" in matrix
        assert "phase-1" in matrix["REQ-1"]
        assert "REQ-3" in matrix
        assert "phase-2" in matrix["REQ-3"]

    def test_uncovered_requirements(self):
        phases = [
            {"phase_id": "phase-1", "satisfies": ["REQ-1"], "heading": "Phase 1"},
        ]
        req_inv = {
            "reqs.md": {
                "source_path": "reqs.md",
                "ids": [
                    {"id": "REQ-1", "title": ""},
                    {"id": "REQ-2", "title": ""},
                ],
            }
        }
        matrix = _build_traceability_matrix(phases, req_inv)
        assert matrix["REQ-1"] == ["phase-1"]
        assert matrix["REQ-2"] == []  # uncovered

    def test_multiple_phases_per_requirement(self):
        phases = [
            {"phase_id": "phase-1", "satisfies": ["REQ-1"], "heading": "Phase 1"},
            {"phase_id": "phase-2", "satisfies": ["REQ-1"], "heading": "Phase 2"},
        ]
        req_inv = {
            "reqs.md": {
                "source_path": "reqs.md",
                "ids": [{"id": "REQ-1", "title": ""}],
            }
        }
        matrix = _build_traceability_matrix(phases, req_inv)
        assert matrix["REQ-1"] == ["phase-1", "phase-2"]


# ── Dependency Graph Tests ───────────────────────────────────────

class TestBuildDependencyGraph:
    def test_basic_dependencies(self):
        phases = [
            {"phase_id": "phase-1", "depends_on": "Nothing"},
            {"phase_id": "phase-2", "depends_on": "Phase 1"},
            {"phase_id": "phase-3", "depends_on": "Phase 1"},
        ]
        graph = _build_dependency_graph(phases)
        assert graph["phase-1"] == []
        assert graph["phase-2"] == ["phase-1"]
        assert graph["phase-3"] == ["phase-1"]

    def test_multiple_dependencies(self):
        phases = [
            {"phase_id": "phase-1", "depends_on": None},
            {"phase_id": "phase-2", "depends_on": None},
            {"phase_id": "phase-3", "depends_on": "Phases 1, 2"},
        ]
        graph = _build_dependency_graph(phases)
        assert "phase-1" in graph["phase-3"]
        assert "phase-2" in graph["phase-3"]

    def test_empty_phases(self):
        graph = _build_dependency_graph([])
        assert graph == {}


# ── Conflict Detection Tests ─────────────────────────────────────

class TestDetectConflicts:
    def test_no_overlaps(self):
        inv = {
            "doc_a.md": {"ids": [{"id": "REQ-1"}, {"id": "REQ-2"}]},
            "doc_b.md": {"ids": [{"id": "REQ-3"}, {"id": "REQ-4"}]},
        }
        conflicts = _detect_conflicts(inv)
        assert conflicts["overlapping_ids"] == {}

    def test_overlapping_ids(self):
        inv = {
            "doc_a.md": {"ids": [{"id": "REQ-1"}, {"id": "REQ-2"}]},
            "doc_b.md": {"ids": [{"id": "REQ-1"}, {"id": "REQ-3"}]},
        }
        conflicts = _detect_conflicts(inv)
        assert "REQ-1" in conflicts["overlapping_ids"]
        assert len(conflicts["overlapping_ids"]["REQ-1"]) == 2


# ── Plan Header Metadata Tests ───────────────────────────────────

class TestExtractPlanHeaderMetadata:
    def test_extracts_title(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        meta = _extract_plan_header_metadata(lines)
        assert "Weaver" in meta["title"]

    def test_extracts_date(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        meta = _extract_plan_header_metadata(lines)
        assert meta["date"] == "2026-02-11"

    def test_extracts_requirements(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        meta = _extract_plan_header_metadata(lines)
        assert len(meta["declared_requirements"]) >= 1
        assert "WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md" in meta["declared_requirements"][0]

    def test_extracts_companions(self):
        lines = [ln.strip() for ln in SAMPLE_PLAN.splitlines() if ln.strip()]
        meta = _extract_plan_header_metadata(lines)
        assert len(meta["declared_companions"]) >= 1
        assert "WEAVER_REGISTRY_REQUIREMENTS.md" in meta["declared_companions"][0]


# ── Full End-to-End Test ─────────────────────────────────────────

class TestAnalyzePlan:
    def test_full_analysis(self):
        result = analyze_plan(
            plan_text=SAMPLE_PLAN,
            plan_path="docs/plans/PLAN.md",
            requirements_docs=[
                {"path": "docs/plans/REQS_A.md", "text": SAMPLE_REQUIREMENTS_A},
                {"path": "docs/plans/REQS_B.md", "text": SAMPLE_REQUIREMENTS_B},
            ],
        )
        assert result["schema"] == "contextcore.io/plan-analysis/v1"
        assert result["plan_path"] == "docs/plans/PLAN.md"

        # Plan metadata
        meta = result["plan_metadata"]
        assert "Weaver" in meta["title"]

        # Requirement inventory
        inv = result["requirement_inventory"]
        assert "REQS_A.md" in inv
        assert "REQS_B.md" in inv
        assert len(inv["REQS_A.md"]["ids"]) == 4  # REQ-1 through REQ-4
        assert len(inv["REQS_B.md"]["ids"]) == 4  # REQ-5 through REQ-8

        # Phase metadata
        phases = result["phase_metadata"]
        assert len(phases) == 7

        # Traceability matrix
        trace = result["traceability_matrix"]
        assert "REQ-1" in trace
        assert len(trace["REQ-1"]) > 0  # At least one phase satisfies REQ-1

        # Dependency graph
        deps = result["dependency_graph"]
        assert "phase-1" in deps
        assert deps["phase-1"] == []  # unblocked

        # Statistics
        stats = result["statistics"]
        assert stats["total_requirements"] == 8
        assert stats["total_phases"] == 7
        assert stats["coverage_ratio"] > 0

    def test_empty_requirements(self):
        result = analyze_plan(
            plan_text=SAMPLE_PLAN,
            plan_path="plan.md",
            requirements_docs=[],
        )
        assert result["statistics"]["total_requirements"] == 0
        assert result["statistics"]["total_phases"] == 7

    def test_idempotency(self):
        """Running analyze-plan twice produces identical output (NFR-CDP-002)."""
        kwargs = dict(
            plan_text=SAMPLE_PLAN,
            plan_path="plan.md",
            requirements_docs=[
                {"path": "reqs_a.md", "text": SAMPLE_REQUIREMENTS_A},
            ],
        )
        r1 = analyze_plan(**kwargs)
        r2 = analyze_plan(**kwargs)
        # Compare everything except generated_at timestamp
        r1.pop("generated_at")
        r2.pop("generated_at")
        assert r1 == r2

    def test_schema_version_present(self):
        result = analyze_plan(
            plan_text="# Simple Plan\n\n## Phase 1: Something\n",
            plan_path="plan.md",
            requirements_docs=[],
        )
        assert result["schema"] == "contextcore.io/plan-analysis/v1"
