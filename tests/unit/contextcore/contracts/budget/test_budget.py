"""Tests for SLO budget contracts (Layer 6)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from contextcore.contracts.budget.loader import BudgetLoader
from contextcore.contracts.budget.otel import emit_budget_check, emit_budget_summary
from contextcore.contracts.budget.schema import (
    BudgetPropagationSpec,
    BudgetSpec,
    PhaseAllocation,
)
from contextcore.contracts.budget.tracker import BudgetTracker
from contextcore.contracts.budget.validator import BudgetValidator
from contextcore.contracts.types import BudgetHealth, BudgetType, OverflowPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec() -> BudgetPropagationSpec:
    return BudgetPropagationSpec(
        schema_version="0.1.0",
        contract_type="budget_propagation",
        pipeline_id="test",
        budgets=[
            BudgetSpec(
                budget_id="latency",
                budget_type=BudgetType.LATENCY_MS,
                total=5000.0,
                allocations=[
                    PhaseAllocation(phase="plan", amount=1000.0),
                    PhaseAllocation(phase="design", amount=2000.0),
                    PhaseAllocation(phase="implement", amount=2000.0),
                ],
                overflow_policy=OverflowPolicy.WARN,
            ),
            BudgetSpec(
                budget_id="cost",
                budget_type=BudgetType.COST_DOLLARS,
                total=10.0,
                allocations=[
                    PhaseAllocation(phase="plan", amount=2.0),
                    PhaseAllocation(phase="design", amount=5.0),
                    PhaseAllocation(phase="implement", amount=3.0),
                ],
                overflow_policy=OverflowPolicy.BLOCK,
            ),
        ],
    )


MINIMAL_YAML = textwrap.dedent("""\
    schema_version: "0.1.0"
    contract_type: budget_propagation
    pipeline_id: test-pipeline
    budgets:
      - budget_id: latency
        budget_type: latency_ms
        total: 5000
        allocations:
          - phase: plan
            amount: 2000
          - phase: design
            amount: 3000
        overflow_policy: warn
""")


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_valid_spec(self):
        s = _make_spec()
        assert len(s.budgets) == 2
        assert s.budgets[0].budget_id == "latency"

    def test_phase_allocation(self):
        a = PhaseAllocation(phase="plan", amount=100.0)
        assert a.phase == "plan"
        assert a.amount == 100.0

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            PhaseAllocation(phase="plan", amount=-1.0)

    def test_wrong_type_rejected(self):
        with pytest.raises(ValidationError):
            BudgetPropagationSpec(
                schema_version="0.1.0",
                contract_type="wrong",
                pipeline_id="t",
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            BudgetSpec(
                budget_id="x",
                budget_type=BudgetType.LATENCY_MS,
                total=100.0,
                bogus="y",
            )


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    BudgetLoader.clear_cache()
    yield
    BudgetLoader.clear_cache()


class TestLoader:
    def test_load_from_string(self):
        s = BudgetLoader().load_from_string(MINIMAL_YAML)
        assert s.pipeline_id == "test-pipeline"
        assert len(s.budgets) == 1

    def test_load_from_file(self, tmp_path: Path):
        f = tmp_path / "budget.yaml"
        f.write_text(MINIMAL_YAML)
        s = BudgetLoader().load(f)
        assert s.pipeline_id == "test-pipeline"

    def test_caching(self, tmp_path: Path):
        f = tmp_path / "budget.yaml"
        f.write_text(MINIMAL_YAML)
        loader = BudgetLoader()
        assert loader.load(f) is loader.load(f)

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            BudgetLoader().load(Path("/nonexistent.yaml"))


# ---------------------------------------------------------------------------
# Tracker tests
# ---------------------------------------------------------------------------


class TestTracker:
    def test_record_and_get_consumed(self):
        t = BudgetTracker()
        ctx: dict = {}
        t.record(ctx, "latency", "plan", 500.0)
        assert t.get_consumed(ctx, "latency") == 500.0

    def test_record_accumulates(self):
        t = BudgetTracker()
        ctx: dict = {}
        t.record(ctx, "latency", "plan", 300.0)
        t.record(ctx, "latency", "plan", 200.0)
        assert t.get_consumed(ctx, "latency") == 500.0

    def test_get_phase_consumed(self):
        t = BudgetTracker()
        ctx: dict = {}
        t.record(ctx, "latency", "plan", 300.0)
        t.record(ctx, "latency", "design", 700.0)
        assert t.get_phase_consumed(ctx, "latency", "plan") == 300.0
        assert t.get_phase_consumed(ctx, "latency", "design") == 700.0

    def test_get_remaining(self):
        spec = _make_spec()
        t = BudgetTracker()
        ctx: dict = {}
        t.record(ctx, "latency", "plan", 300.0)
        remaining = t.get_remaining(spec, ctx, "latency")
        assert remaining == 4700.0  # 5000 - 300

    def test_unknown_budget_remaining(self):
        spec = _make_spec()
        t = BudgetTracker()
        assert t.get_remaining(spec, {}, "nonexistent") == 0.0


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


class TestValidator:
    def test_within_budget(self):
        spec = _make_spec()
        v = BudgetValidator(spec)
        ctx: dict = {}
        BudgetTracker().record(ctx, "latency", "plan", 800.0)
        r = v.check_phase("plan", ctx)
        assert r.passed is True
        plan_result = next(x for x in r.results if x.budget_id == "latency")
        assert plan_result.health == BudgetHealth.WITHIN_BUDGET

    def test_over_allocation(self):
        spec = _make_spec()
        v = BudgetValidator(spec)
        ctx: dict = {}
        BudgetTracker().record(ctx, "latency", "plan", 1500.0)
        r = v.check_phase("plan", ctx)
        plan_result = next(x for x in r.results if x.budget_id == "latency")
        assert plan_result.health == BudgetHealth.OVER_ALLOCATION

    def test_budget_exhausted(self):
        spec = _make_spec()
        v = BudgetValidator(spec)
        ctx: dict = {}
        t = BudgetTracker()
        t.record(ctx, "latency", "plan", 3000.0)
        t.record(ctx, "latency", "design", 2000.0)
        r = v.check_phase("plan", ctx)
        plan_result = next(x for x in r.results if x.budget_id == "latency")
        assert plan_result.health == BudgetHealth.BUDGET_EXHAUSTED
        assert r.passed is False

    def test_check_all(self):
        spec = _make_spec()
        v = BudgetValidator(spec)
        ctx: dict = {}
        BudgetTracker().record(ctx, "latency", "plan", 500.0)
        BudgetTracker().record(ctx, "cost", "plan", 1.0)
        s = v.check_all(ctx)
        assert s.total_budgets >= 2  # includes __total__ entries


# ---------------------------------------------------------------------------
# OTel tests
# ---------------------------------------------------------------------------


class TestOtel:
    def test_no_otel_no_crash(self):
        with patch("contextcore.contracts._otel_helpers.HAS_OTEL", False):
            emit_budget_check(MagicMock())
            emit_budget_summary(MagicMock())
