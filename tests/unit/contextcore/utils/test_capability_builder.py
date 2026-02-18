"""Tests for contextcore.utils.capability_builder."""

import textwrap
from pathlib import Path
from typing import Dict, Any

import pytest
import yaml

from contextcore.utils.capability_builder import (
    BuildReport,
    build_capability_index,
    write_manifest,
    _bump_version,
    _get_existing_cap_ids,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _write_agent_yaml(index_dir: Path, content: str) -> Path:
    fp = index_dir / "contextcore.agent.yaml"
    fp.write_text(content, encoding="utf-8")
    return fp


def _make_project(tmp_path: Path, *, with_contracts: bool = True) -> Path:
    """Create a minimal project tree for builder tests."""
    project = tmp_path / "project"
    project.mkdir()

    # Capability index dir
    index_dir = project / "docs" / "capability-index"
    index_dir.mkdir(parents=True)

    # Minimal agent manifest
    _write_agent_yaml(index_dir, textwrap.dedent("""\
        manifest_id: contextcore.agent
        name: ContextCore Agent Capabilities
        version: "1.10.1"
        labels:
          domain: observability
        capabilities:
          - capability_id: contextcore.insight.emit
            category: action
            maturity: stable
            summary: Emit agent-generated insights
            triggers:
              - "emit insight"
          - capability_id: contextcore.task.track
            category: action
            maturity: stable
            summary: Track tasks as OTel spans
            triggers:
              - "track task"
    """))

    if with_contracts:
        # Create contract domains
        contracts = project / "src" / "contextcore" / "contracts"
        contracts.mkdir(parents=True)
        for domain in ["propagation", "schema_compat", "semconv", "ordering",
                        "capability", "budget", "lineage"]:
            d = contracts / domain
            d.mkdir()
            (d / "schema.py").write_text(f'"""Models for {domain}."""\n')
            (d / "loader.py").write_text("# loader\n")
            (d / "validator.py").write_text("# validator\n")
            (d / "otel.py").write_text("# otel\n")

        # A2A modules
        a2a = contracts / "a2a"
        a2a.mkdir()
        for m in ["models.py", "gates.py", "pipeline_checker.py",
                   "three_questions.py", "__init__.py"]:
            (a2a / m).write_text(f"# {m}\n")

    return project


def _write_principles(index_dir: Path) -> None:
    (index_dir / "_principles.yaml").write_text(textwrap.dedent("""\
        design_principles:
          - id: typed_over_prose
            principle: "Use typed schemas"
            rationale: "Eliminates ambiguity"
            anti_patterns:
              - "Regex parsing"
            applies_to:
              - contextcore.insight.emit
          - id: observable_contracts
            principle: "Contracts emit OTel"
            rationale: "Visibility"
            applies_to: []
    """), encoding="utf-8")


def _write_patterns(index_dir: Path) -> None:
    (index_dir / "_patterns.yaml").write_text(textwrap.dedent("""\
        patterns:
          - pattern_id: typed_handoff
            name: "Typed Handoff"
            summary: "Define contracts, produce typed output"
            capabilities:
              - contextcore.insight.emit
            anti_pattern: "String parsing"
    """), encoding="utf-8")


def _write_enrichments(index_dir: Path) -> None:
    (index_dir / "_trigger_enrichments.yaml").write_text(textwrap.dedent("""\
        trigger_enrichments:
          contextcore.insight.emit:
            - "pipeline insight"
            - "stage knowledge"
    """), encoding="utf-8")


# ── build_capability_index ────────────────────────────────────────────────


class TestBuildCapabilityIndex:
    def test_merges_scanned_capabilities(self, tmp_path: Path):
        project = _make_project(tmp_path)
        manifest, report = build_capability_index(project)

        # Should have original 2 + 7 contract + 6 A2A = 15
        cap_ids = {c["capability_id"] for c in manifest["capabilities"]}
        assert "contextcore.insight.emit" in cap_ids  # existing preserved
        assert "contextcore.contract.propagation" in cap_ids  # scanned added
        assert "contextcore.a2a.gate.diagnostic" in cap_ids  # A2A added
        assert len(report.added_capabilities) == 13

    def test_does_not_overwrite_existing(self, tmp_path: Path):
        project = _make_project(tmp_path)
        manifest, report = build_capability_index(project)

        # Original capabilities should be unchanged
        emit = next(
            c for c in manifest["capabilities"]
            if c["capability_id"] == "contextcore.insight.emit"
        )
        assert emit["category"] == "action"
        assert emit["maturity"] == "stable"
        assert "emit insight" in emit["triggers"]

    def test_version_bumped(self, tmp_path: Path):
        project = _make_project(tmp_path)
        manifest, report = build_capability_index(project)
        assert manifest["version"] == "1.11.0"
        assert report.original_version == "1.10.1"
        assert report.new_version == "1.11.0"

    def test_injects_principles(self, tmp_path: Path):
        project = _make_project(tmp_path)
        index_dir = project / "docs" / "capability-index"
        _write_principles(index_dir)

        manifest, report = build_capability_index(project)
        assert "design_principles" in manifest
        assert len(manifest["design_principles"]) == 2
        assert report.principles_added == 2

    def test_injects_patterns(self, tmp_path: Path):
        project = _make_project(tmp_path)
        index_dir = project / "docs" / "capability-index"
        _write_patterns(index_dir)

        manifest, report = build_capability_index(project)
        assert "patterns" in manifest
        assert len(manifest["patterns"]) == 1
        assert report.patterns_added == 1

    def test_enriches_triggers(self, tmp_path: Path):
        project = _make_project(tmp_path)
        index_dir = project / "docs" / "capability-index"
        _write_enrichments(index_dir)

        manifest, report = build_capability_index(project)
        emit = next(
            c for c in manifest["capabilities"]
            if c["capability_id"] == "contextcore.insight.emit"
        )
        assert "pipeline insight" in emit["triggers"]
        assert "stage knowledge" in emit["triggers"]
        assert "emit insight" in emit["triggers"]  # original preserved
        assert "contextcore.insight.emit" in report.triggers_enriched

    def test_no_duplicate_triggers(self, tmp_path: Path):
        project = _make_project(tmp_path)
        index_dir = project / "docs" / "capability-index"
        # Write enrichment with a trigger that already exists
        (index_dir / "_trigger_enrichments.yaml").write_text(textwrap.dedent("""\
            trigger_enrichments:
              contextcore.insight.emit:
                - "emit insight"
                - "new trigger"
        """), encoding="utf-8")

        manifest, _ = build_capability_index(project)
        emit = next(
            c for c in manifest["capabilities"]
            if c["capability_id"] == "contextcore.insight.emit"
        )
        trigger_counts = {}
        for t in emit["triggers"]:
            trigger_counts[t] = trigger_counts.get(t, 0) + 1
        assert trigger_counts.get("emit insight", 0) == 1

    def test_no_contracts_dir(self, tmp_path: Path):
        project = _make_project(tmp_path, with_contracts=False)
        manifest, report = build_capability_index(project)
        # Only original capabilities
        assert len(manifest["capabilities"]) == 2
        assert len(report.added_capabilities) == 0

    def test_no_existing_manifest(self, tmp_path: Path):
        project = tmp_path / "empty_project"
        project.mkdir()
        (project / "docs" / "capability-index").mkdir(parents=True)
        (project / "src" / "contextcore" / "contracts").mkdir(parents=True)

        manifest, report = build_capability_index(project)
        assert manifest["manifest_id"] == "contextcore.agent"
        assert "No existing manifest found" in report.notes[0]

    def test_idempotent_build(self, tmp_path: Path):
        """Running build twice doesn't duplicate capabilities."""
        project = _make_project(tmp_path)
        index_dir = project / "docs" / "capability-index"
        _write_principles(index_dir)
        _write_patterns(index_dir)

        manifest1, _ = build_capability_index(project)
        # Write result and build again
        write_manifest(manifest1, index_dir / "contextcore.agent.yaml")
        manifest2, report2 = build_capability_index(project)

        # No new capabilities should be added
        assert len(report2.added_capabilities) == 0
        assert len(manifest2["capabilities"]) == len(manifest1["capabilities"])

    def test_does_not_duplicate_principles(self, tmp_path: Path):
        """If principles already exist in manifest, don't re-inject."""
        project = _make_project(tmp_path)
        index_dir = project / "docs" / "capability-index"
        _write_principles(index_dir)

        manifest1, _ = build_capability_index(project)
        write_manifest(manifest1, index_dir / "contextcore.agent.yaml")
        manifest2, report2 = build_capability_index(project)

        assert report2.principles_added == 0
        assert len(manifest2["design_principles"]) == 2


# ── write_manifest ────────────────────────────────────────────────────────


class TestWriteManifest:
    def test_round_trip(self, tmp_path: Path):
        manifest = {
            "manifest_id": "test",
            "version": "1.0.0",
            "capabilities": [
                {"capability_id": "cap.a", "summary": "Test"},
            ],
        }
        out = tmp_path / "out.yaml"
        write_manifest(manifest, out)

        with open(out) as f:
            loaded = yaml.safe_load(f)
        assert loaded["manifest_id"] == "test"
        assert loaded["capabilities"][0]["capability_id"] == "cap.a"


# ── BuildReport ──────────────────────────────────────────────────────────


class TestBuildReport:
    def test_summary(self):
        report = BuildReport()
        report.original_version = "1.10.1"
        report.new_version = "1.11.0"
        report.original_capability_count = 27
        report.added_capabilities = ["cap.a", "cap.b"]
        report.principles_added = 9
        report.patterns_added = 6
        report.triggers_enriched = {"cap.x": ["t1", "t2"]}

        summary = report.summary()
        assert "1.10.1 -> 1.11.0" in summary
        assert "27 existing + 2 added = 29" in summary
        assert "9 added" in summary
        assert "6 added" in summary

    def test_total_capabilities(self):
        report = BuildReport()
        report.original_capability_count = 10
        report.added_capabilities = ["a", "b", "c"]
        assert report.total_capabilities == 13


# ── Helpers ──────────────────────────────────────────────────────────────


class TestBumpVersion:
    def test_minor_bump(self):
        assert _bump_version("1.10.1") == "1.11.0"

    def test_simple(self):
        assert _bump_version("1.0.0") == "1.1.0"

    def test_invalid(self):
        assert _bump_version("abc") == "abc"
