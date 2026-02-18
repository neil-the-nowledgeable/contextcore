"""Tests for contextcore.utils.capability_index."""

import textwrap
from pathlib import Path

import pytest

from contextcore.utils.capability_index import (
    Benefit,
    Capability,
    CapabilityIndex,
    Pattern,
    Principle,
    clear_cache,
    discover_expansion_pack_metrics,
    load_capability_index,
    match_patterns,
    match_principles,
    match_triggers,
)


@pytest.fixture(autouse=True)
def _clear_cap_cache():
    """Ensure each test starts with a clean cache."""
    clear_cache()
    yield
    clear_cache()


# ── Minimal YAML fixtures ────────────────────────────────────────


def _write_agent_yaml(tmp_path: Path, extra: str = "") -> Path:
    """Write a minimal contextcore.agent.yaml and return the directory."""
    index_dir = tmp_path / "capability-index"
    index_dir.mkdir()
    base = textwrap.dedent("""\
        version: "1.10.1"
        capabilities:
          - capability_id: contextcore.insight.emit
            category: action
            maturity: stable
            summary: Emit agent-generated insights
            triggers:
              - "emit insight"
              - "record decision"
          - capability_id: contextcore.task.track
            category: action
            maturity: stable
            summary: Track tasks as OTel spans
            triggers:
              - "track task"
              - "task tracking"
    """)
    (index_dir / "contextcore.agent.yaml").write_text(
        base + extra, encoding="utf-8"
    )
    return index_dir


def _write_benefits_yaml(index_dir: Path) -> None:
    (index_dir / "contextcore.benefits.yaml").write_text(
        textwrap.dedent("""\
            version: "1.7.1"
            benefits:
              - benefit_id: BEN-001
                category: time_savings
                summary: Eliminate manual status reporting
        """),
        encoding="utf-8",
    )


PRINCIPLES_YAML = textwrap.dedent("""\
    design_principles:
      - id: typed_over_prose
        principle: All inter-agent data exchange uses typed schemas
        rationale: Prevents ambiguity
        anti_patterns:
          - Freeform JSON blobs
        applies_to:
          - contextcore.insight.emit
          - contextcore.task.track
      - id: prescriptive_over_descriptive
        principle: Declare what should happen and verify it did
        rationale: Proactive validation
        anti_patterns:
          - Post-hoc log analysis
        applies_to:
          - contextcore.task.track
      - id: observable_contracts
        principle: Every contract emits telemetry for its lifecycle
        rationale: Debugging requires visibility
        applies_to:
          - contextcore.contract.propagation
""")

PATTERNS_YAML = textwrap.dedent("""\
    patterns:
      - pattern_id: typed_handoff
        name: Typed Handoff
        summary: Agent-to-agent handoffs use typed contracts
        capabilities:
          - contextcore.insight.emit
          - contextcore.task.track
        anti_pattern: Freeform text handoffs
      - pattern_id: contract_validation
        name: Contract Validation
        summary: Validate contracts at pipeline boundaries
        capabilities:
          - contextcore.contract.propagation
""")


# ── load_capability_index ─────────────────────────────────────────


class TestLoadCapabilityIndex:
    def test_valid_directory(self, tmp_path: Path):
        index_dir = _write_agent_yaml(tmp_path)
        index = load_capability_index(index_dir)
        assert not index.is_empty
        assert index.version == "1.10.1"
        assert len(index.capabilities) == 2
        assert index.capabilities[0].capability_id == "contextcore.insight.emit"

    def test_empty_dir_returns_empty(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        index = load_capability_index(empty_dir)
        assert index.is_empty

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path):
        index = load_capability_index(tmp_path / "nonexistent")
        assert index.is_empty

    def test_no_principles_section(self, tmp_path: Path):
        """Pre-enhancement YAML without design_principles is handled."""
        index_dir = _write_agent_yaml(tmp_path)
        index = load_capability_index(index_dir)
        assert index.principles == []
        assert index.patterns == []
        assert len(index.capabilities) == 2

    def test_with_principles_and_patterns(self, tmp_path: Path):
        index_dir = _write_agent_yaml(
            tmp_path,
            extra=PRINCIPLES_YAML + PATTERNS_YAML,
        )
        index = load_capability_index(index_dir)
        assert len(index.principles) == 3
        assert len(index.patterns) == 2
        assert index.principles[0].id == "typed_over_prose"
        assert index.patterns[0].pattern_id == "typed_handoff"

    def test_caches_by_resolved_path(self, tmp_path: Path):
        index_dir = _write_agent_yaml(tmp_path)
        idx1 = load_capability_index(index_dir)
        idx2 = load_capability_index(index_dir)
        assert idx1 is idx2

    def test_clear_cache(self, tmp_path: Path):
        index_dir = _write_agent_yaml(tmp_path)
        idx1 = load_capability_index(index_dir)
        clear_cache()
        idx2 = load_capability_index(index_dir)
        assert idx1 is not idx2

    def test_loads_benefits(self, tmp_path: Path):
        index_dir = _write_agent_yaml(tmp_path)
        _write_benefits_yaml(index_dir)
        index = load_capability_index(index_dir)
        assert len(index.benefits) == 1
        assert index.benefits[0].benefit_id == "BEN-001"


# ── match_triggers ────────────────────────────────────────────────


class TestMatchTriggers:
    CAPS = [
        Capability(
            capability_id="cap.a",
            triggers=["emit insight", "record decision"],
        ),
        Capability(
            capability_id="cap.b",
            triggers=["track task"],
        ),
        Capability(
            capability_id="cap.c",
            triggers=["deploy artifact"],
        ),
    ]

    def test_found(self):
        result = match_triggers("I want to emit insight here", self.CAPS)
        assert len(result) == 1
        assert result[0].capability_id == "cap.a"

    def test_not_found(self):
        result = match_triggers("nothing relevant here", self.CAPS)
        assert result == []

    def test_case_insensitive(self):
        result = match_triggers("EMIT INSIGHT please", self.CAPS)
        assert len(result) == 1
        assert result[0].capability_id == "cap.a"

    def test_multiple_matches(self):
        result = match_triggers(
            "emit insight and track task", self.CAPS
        )
        assert len(result) == 2
        ids = {c.capability_id for c in result}
        assert ids == {"cap.a", "cap.b"}


# ── match_patterns ────────────────────────────────────────────────


class TestMatchPatterns:
    PATTERNS = [
        Pattern(
            pattern_id="pat.a",
            name="Pattern A",
            summary="Pattern A summary",
            capabilities=["cap.1", "cap.2"],
        ),
        Pattern(
            pattern_id="pat.b",
            name="Pattern B",
            summary="Pattern B summary",
            capabilities=["cap.3"],
        ),
    ]

    def test_overlapping(self):
        result = match_patterns(["cap.2"], self.PATTERNS)
        assert len(result) == 1
        assert result[0].pattern_id == "pat.a"

    def test_no_overlap(self):
        result = match_patterns(["cap.99"], self.PATTERNS)
        assert result == []


# ── match_principles ──────────────────────────────────────────────


class TestMatchPrinciples:
    PRINCIPLES = [
        Principle(
            id="prin.a",
            principle="Principle A",
            applies_to=["cap.1", "cap.2"],
        ),
        Principle(
            id="prin.b",
            principle="Principle B",
            applies_to=["cap.3"],
        ),
    ]

    def test_overlapping(self):
        result = match_principles(["cap.1"], self.PRINCIPLES)
        assert len(result) == 1
        assert result[0].id == "prin.a"

    def test_no_overlap(self):
        result = match_principles(["cap.99"], self.PRINCIPLES)
        assert result == []


# ── discover_expansion_pack_metrics ──────────────────────────────


class TestDiscoverExpansionPackMetrics:
    def test_no_expansion_caps(self):
        """Returns empty dict when no expansion pack capabilities exist."""
        index = CapabilityIndex(capabilities=[
            Capability(
                capability_id="contextcore.insight.emit",
                triggers=["emit insight"],
            ),
        ])
        result = discover_expansion_pack_metrics(index)
        assert result == {}

    def test_discovers_beaver_metrics(self):
        """Discovers beaver metrics from startd8 capabilities."""
        index = CapabilityIndex(capabilities=[
            Capability(
                capability_id="startd8.cost.track",
                triggers=["cost tracking", "token usage metric"],
            ),
            Capability(
                capability_id="startd8.session.monitor",
                triggers=["monitor sessions", "session metric"],
            ),
            Capability(
                capability_id="contextcore.insight.emit",
                triggers=["emit insight"],
            ),
        ])
        result = discover_expansion_pack_metrics(index)
        assert "beaver" in result
        assert len(result["beaver"]) >= 1

    def test_empty_index(self):
        """Returns empty dict for empty index."""
        index = CapabilityIndex()
        result = discover_expansion_pack_metrics(index)
        assert result == {}

    def test_no_metric_triggers(self):
        """Ignores expansion pack caps without metric-related triggers."""
        index = CapabilityIndex(capabilities=[
            Capability(
                capability_id="startd8.agent.run",
                triggers=["run agent", "execute task"],
            ),
        ])
        result = discover_expansion_pack_metrics(index)
        assert result == {}

    def test_contextcore_beaver_prefix(self):
        """Discovers metrics from contextcore.beaver.* prefix."""
        index = CapabilityIndex(capabilities=[
            Capability(
                capability_id="contextcore.beaver.cost",
                triggers=["cost metric"],
            ),
        ])
        result = discover_expansion_pack_metrics(index)
        assert "beaver" in result
        assert "contextcore_beaver_cost" in result["beaver"]

    def test_deduplicates_metric_names(self):
        """Same capability_id appears only once even with multiple metric triggers."""
        index = CapabilityIndex(capabilities=[
            Capability(
                capability_id="startd8.cost.track",
                triggers=["cost metric", "token metric", "usage tracking"],
            ),
        ])
        result = discover_expansion_pack_metrics(index)
        assert result["beaver"].count("startd8_cost_track") == 1
