"""Tests for causal ordering contracts (Layer 4)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from contextcore.contracts.ordering.clock import CausalClock, CausalProvenance
from contextcore.contracts.ordering.loader import OrderingLoader
from contextcore.contracts.ordering.otel import emit_ordering_result, emit_ordering_violation
from contextcore.contracts.ordering.schema import (
    CausalDependency,
    CausalEndpoint,
    OrderingConstraintSpec,
)
from contextcore.contracts.ordering.validator import (
    CausalValidator,
    OrderingCheckResult,
    OrderingValidationResult,
)
from contextcore.contracts.types import ConstraintSeverity


MINIMAL_YAML = textwrap.dedent("""\
    schema_version: "0.1.0"
    contract_type: causal_ordering
    pipeline_id: test-pipeline
    dependencies:
      - before:
          phase: plan
          event: completed
        after:
          phase: design
          event: started
        severity: warning
""")


# ---------------------------------------------------------------------------
# Clock tests
# ---------------------------------------------------------------------------


class TestCausalClock:
    def test_initial_zero(self):
        assert CausalClock().current() == 0

    def test_tick_increments(self):
        c = CausalClock()
        assert c.tick() == 1
        assert c.tick() == 2

    def test_receive_merges(self):
        c = CausalClock()
        c.tick()  # 1
        assert c.receive(5) == 6  # max(1,5)+1

    def test_monotonicity(self):
        c = CausalClock()
        ts = [c.tick(), c.receive(100), c.tick(), c.receive(50), c.tick()]
        for i in range(1, len(ts)):
            assert ts[i] > ts[i - 1]


class TestCausalProvenance:
    def test_creation(self):
        p = CausalProvenance(phase="plan", event="started", logical_ts=1, wall_clock="t")
        assert p.phase == "plan"

    def test_to_dict(self):
        d = CausalProvenance(phase="p", event="e", logical_ts=1, wall_clock="w").to_dict()
        assert d["phase"] == "p"
        assert d["logical_ts"] == 1


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_valid_spec(self):
        s = OrderingConstraintSpec(
            schema_version="0.1.0",
            contract_type="causal_ordering",
            pipeline_id="test",
            dependencies=[],
        )
        assert s.pipeline_id == "test"

    def test_wrong_type_rejected(self):
        with pytest.raises(ValidationError):
            OrderingConstraintSpec(
                schema_version="0.1.0",
                contract_type="wrong",
                pipeline_id="test",
                dependencies=[],
            )

    def test_empty_phase_rejected(self):
        with pytest.raises(ValidationError):
            CausalEndpoint(phase="", event="done")


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    OrderingLoader.clear_cache()
    yield
    OrderingLoader.clear_cache()


class TestLoader:
    def test_load_from_string(self):
        s = OrderingLoader().load_from_string(MINIMAL_YAML)
        assert s.pipeline_id == "test-pipeline"
        assert len(s.dependencies) == 1

    def test_load_from_file(self, tmp_path: Path):
        f = tmp_path / "ordering.yaml"
        f.write_text(MINIMAL_YAML)
        assert OrderingLoader().load(f).pipeline_id == "test-pipeline"

    def test_caching(self, tmp_path: Path):
        f = tmp_path / "ordering.yaml"
        f.write_text(MINIMAL_YAML)
        loader = OrderingLoader()
        assert loader.load(f) is loader.load(f)

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            OrderingLoader().load(Path("/nonexistent.yaml"))


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


def _spec(*deps: CausalDependency) -> OrderingConstraintSpec:
    return OrderingConstraintSpec(
        schema_version="0.1.0",
        contract_type="causal_ordering",
        pipeline_id="test",
        dependencies=list(deps),
    )


def _dep(
    before_phase: str = "plan",
    before_event: str = "completed",
    after_phase: str = "design",
    after_event: str = "started",
    severity: ConstraintSeverity = ConstraintSeverity.WARNING,
) -> CausalDependency:
    return CausalDependency(
        before=CausalEndpoint(phase=before_phase, event=before_event),
        after=CausalEndpoint(phase=after_phase, event=after_event),
        severity=severity,
    )


class TestValidator:
    def test_satisfied(self):
        r = CausalValidator(_spec(_dep())).validate([
            CausalProvenance(phase="plan", event="completed", logical_ts=1, wall_clock="t"),
            CausalProvenance(phase="design", event="started", logical_ts=2, wall_clock="t"),
        ])
        assert r.passed is True
        assert r.violations == 0

    def test_reversed_blocking(self):
        r = CausalValidator(_spec(_dep(severity=ConstraintSeverity.BLOCKING))).validate([
            CausalProvenance(phase="design", event="started", logical_ts=1, wall_clock="t"),
            CausalProvenance(phase="plan", event="completed", logical_ts=2, wall_clock="t"),
        ])
        assert r.passed is False
        assert r.violations == 1

    def test_equal_timestamps_violation(self):
        r = CausalValidator(_spec(_dep(severity=ConstraintSeverity.BLOCKING))).validate([
            CausalProvenance(phase="plan", event="completed", logical_ts=5, wall_clock="t"),
            CausalProvenance(phase="design", event="started", logical_ts=5, wall_clock="t"),
        ])
        assert r.passed is False

    def test_warning_does_not_block(self):
        r = CausalValidator(_spec(_dep(severity=ConstraintSeverity.WARNING))).validate([
            CausalProvenance(phase="design", event="started", logical_ts=1, wall_clock="t"),
            CausalProvenance(phase="plan", event="completed", logical_ts=2, wall_clock="t"),
        ])
        assert r.passed is True
        assert r.violations == 1

    def test_missing_before_event(self):
        r = CausalValidator(_spec(_dep(severity=ConstraintSeverity.BLOCKING))).validate([
            CausalProvenance(phase="design", event="started", logical_ts=1, wall_clock="t"),
        ])
        assert r.passed is False

    def test_empty_log(self):
        r = CausalValidator(_spec(_dep(severity=ConstraintSeverity.BLOCKING))).validate([])
        assert r.passed is False

    def test_duplicate_uses_first(self):
        r = CausalValidator(_spec(_dep())).validate([
            CausalProvenance(phase="plan", event="completed", logical_ts=1, wall_clock="t"),
            CausalProvenance(phase="plan", event="completed", logical_ts=10, wall_clock="t"),
            CausalProvenance(phase="design", event="started", logical_ts=2, wall_clock="t"),
        ])
        assert r.passed is True
        assert r.results[0].before_ts == 1


# ---------------------------------------------------------------------------
# OTel tests
# ---------------------------------------------------------------------------


class TestOtel:
    def test_emit_ordering_result(self):
        span = MagicMock()
        span.is_recording.return_value = True
        with patch("contextcore.contracts.ordering.otel._HAS_OTEL", True), \
             patch("contextcore.contracts.ordering.otel.otel_trace") as mt:
            mt.get_current_span.return_value = span
            emit_ordering_result(OrderingValidationResult(passed=True, total_checked=2, violations=0))
            span.add_event.assert_called_once()

    def test_no_otel_no_crash(self):
        with patch("contextcore.contracts.ordering.otel._HAS_OTEL", False):
            emit_ordering_result(OrderingValidationResult(passed=True, total_checked=0, violations=0))
            emit_ordering_violation(OrderingCheckResult(
                dependency=_dep(), satisfied=False, before_ts=None, after_ts=None, message="test",
            ))
