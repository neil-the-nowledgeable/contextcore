"""Tests for contextcore.contracts.regression.gate — Layer 7 regression gate."""

from __future__ import annotations

import pytest

from contextcore.contracts.observability.health import HealthScore
from contextcore.contracts.postexec.validator import PostExecutionReport
from contextcore.contracts.regression.drift import DriftChange, DriftReport
from contextcore.contracts.regression.gate import (
    DEFAULT_THRESHOLDS,
    GateCheck,
    GateResult,
    RegressionGate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report(
    *,
    passed: bool = True,
    completeness_pct: float = 100.0,
    chains_broken: int = 0,
    chains_total: int = 0,
    chains_intact: int = 0,
    chains_degraded: int = 0,
) -> PostExecutionReport:
    return PostExecutionReport(
        passed=passed,
        completeness_pct=completeness_pct,
        chains_broken=chains_broken,
        chains_total=chains_total,
        chains_intact=chains_intact,
        chains_degraded=chains_degraded,
    )


def _health(overall: float, **kwargs) -> HealthScore:
    return HealthScore(overall=overall, **kwargs)


def _drift(
    *,
    total_changes: int = 0,
    breaking_count: int = 0,
    non_breaking_count: int = 0,
    changes: list[DriftChange] | None = None,
) -> DriftReport:
    return DriftReport(
        changes=changes or [],
        total_changes=total_changes,
        breaking_count=breaking_count,
        non_breaking_count=non_breaking_count,
    )


def _breaking_change(description: str = "removed field X") -> DriftChange:
    return DriftChange(
        change_type="field_removed",
        phase="validate",
        field="project_id",
        direction="exit",
        breaking=True,
        description=description,
    )


# ---------------------------------------------------------------------------
# 1. No inputs -> passes with 0 checks
# ---------------------------------------------------------------------------


class TestNoInputs:
    def test_no_inputs_passes_with_zero_checks(self):
        gate = RegressionGate()
        result = gate.check()

        assert result.passed is True
        assert result.total_checks == 0
        assert result.failed_checks == 0
        assert result.checks == []


# ---------------------------------------------------------------------------
# 2-4. Completeness regression checks
# ---------------------------------------------------------------------------


class TestCompletenessRegression:
    def test_same_completeness_passes(self):
        gate = RegressionGate()
        result = gate.check(
            baseline_report=_report(completeness_pct=90.0),
            current_report=_report(completeness_pct=90.0),
        )

        completeness_checks = [
            c for c in result.checks if c.check_id == "completeness_regression"
        ]
        assert len(completeness_checks) == 1
        assert completeness_checks[0].passed is True
        assert completeness_checks[0].baseline_value == 90.0
        assert completeness_checks[0].current_value == 90.0

    def test_completeness_drop_within_threshold_passes(self):
        gate = RegressionGate()
        result = gate.check(
            baseline_report=_report(completeness_pct=90.0),
            current_report=_report(completeness_pct=86.0),
        )

        completeness_checks = [
            c for c in result.checks if c.check_id == "completeness_regression"
        ]
        assert len(completeness_checks) == 1
        assert completeness_checks[0].passed is True

    def test_completeness_drop_beyond_threshold_fails(self):
        gate = RegressionGate()
        result = gate.check(
            baseline_report=_report(completeness_pct=90.0),
            current_report=_report(completeness_pct=80.0),
        )

        completeness_checks = [
            c for c in result.checks if c.check_id == "completeness_regression"
        ]
        assert len(completeness_checks) == 1
        assert completeness_checks[0].passed is False
        assert "dropped by 10.0%" in completeness_checks[0].message


# ---------------------------------------------------------------------------
# 5-6. Health minimum checks
# ---------------------------------------------------------------------------


class TestHealthMinimum:
    def test_health_score_above_minimum_passes(self):
        gate = RegressionGate()
        result = gate.check(current_health=_health(85.0))

        health_min_checks = [
            c for c in result.checks if c.check_id == "health_minimum"
        ]
        assert len(health_min_checks) == 1
        assert health_min_checks[0].passed is True
        assert health_min_checks[0].current_value == 85.0

    def test_health_score_below_minimum_fails(self):
        gate = RegressionGate()
        result = gate.check(current_health=_health(50.0))

        health_min_checks = [
            c for c in result.checks if c.check_id == "health_minimum"
        ]
        assert len(health_min_checks) == 1
        assert health_min_checks[0].passed is False
        assert "below minimum" in health_min_checks[0].message


# ---------------------------------------------------------------------------
# 7-8. Health regression checks
# ---------------------------------------------------------------------------


class TestHealthRegression:
    def test_health_regression_within_threshold_passes(self):
        gate = RegressionGate()
        result = gate.check(
            baseline_health=_health(90.0),
            current_health=_health(86.0),
        )

        regression_checks = [
            c for c in result.checks if c.check_id == "health_regression"
        ]
        assert len(regression_checks) == 1
        assert regression_checks[0].passed is True
        assert regression_checks[0].baseline_value == 90.0
        assert regression_checks[0].current_value == 86.0

    def test_health_regression_beyond_threshold_fails(self):
        gate = RegressionGate()
        result = gate.check(
            baseline_health=_health(90.0),
            current_health=_health(80.0),
        )

        regression_checks = [
            c for c in result.checks if c.check_id == "health_regression"
        ]
        assert len(regression_checks) == 1
        assert regression_checks[0].passed is False
        assert "dropped by 10.0" in regression_checks[0].message


# ---------------------------------------------------------------------------
# 9-11. Contract drift checks
# ---------------------------------------------------------------------------


class TestContractDrift:
    def test_no_breaking_drift_passes(self):
        gate = RegressionGate()
        result = gate.check(
            drift_report=_drift(total_changes=3, non_breaking_count=3),
        )

        drift_checks = [
            c for c in result.checks if c.check_id == "contract_drift"
        ]
        assert len(drift_checks) == 1
        assert drift_checks[0].passed is True
        assert "No breaking drift" in drift_checks[0].message

    def test_breaking_drift_fails(self):
        gate = RegressionGate()
        change = _breaking_change("Removed field project_id from exit")
        result = gate.check(
            drift_report=_drift(
                total_changes=1,
                breaking_count=1,
                changes=[change],
            ),
        )

        drift_checks = [
            c for c in result.checks if c.check_id == "contract_drift"
        ]
        assert len(drift_checks) == 1
        assert drift_checks[0].passed is False
        assert "1 breaking contract changes" in drift_checks[0].message
        assert drift_checks[0].current_value == 1.0

    def test_breaking_drift_with_allow_flag_passes(self):
        gate = RegressionGate(allow_breaking_drift=True)
        change = _breaking_change("Removed field project_id from exit")
        result = gate.check(
            drift_report=_drift(
                total_changes=1,
                breaking_count=1,
                changes=[change],
            ),
        )

        drift_checks = [
            c for c in result.checks if c.check_id == "contract_drift"
        ]
        assert len(drift_checks) == 1
        assert drift_checks[0].passed is True


# ---------------------------------------------------------------------------
# 12-13. Blocking failures checks
# ---------------------------------------------------------------------------


class TestBlockingFailures:
    def test_no_broken_chain_increase_passes(self):
        gate = RegressionGate()
        result = gate.check(
            baseline_report=_report(chains_broken=2),
            current_report=_report(chains_broken=2),
        )

        blocking_checks = [
            c for c in result.checks if c.check_id == "blocking_failures"
        ]
        assert len(blocking_checks) == 1
        assert blocking_checks[0].passed is True
        assert blocking_checks[0].baseline_value == 2.0
        assert blocking_checks[0].current_value == 2.0

    def test_broken_chain_increase_fails(self):
        gate = RegressionGate()
        result = gate.check(
            baseline_report=_report(chains_broken=1),
            current_report=_report(chains_broken=3),
        )

        blocking_checks = [
            c for c in result.checks if c.check_id == "blocking_failures"
        ]
        assert len(blocking_checks) == 1
        assert blocking_checks[0].passed is False
        assert "increased by 2" in blocking_checks[0].message


# ---------------------------------------------------------------------------
# 14-16. Combined gate checks
# ---------------------------------------------------------------------------


class TestCombinedGate:
    def test_all_checks_pass_gate_passes(self):
        gate = RegressionGate()
        result = gate.check(
            baseline_report=_report(completeness_pct=95.0, chains_broken=0),
            current_report=_report(completeness_pct=93.0, chains_broken=0),
            drift_report=_drift(total_changes=2, non_breaking_count=2),
            baseline_health=_health(90.0),
            current_health=_health(88.0),
        )

        assert result.passed is True
        assert result.failed_checks == 0
        assert result.total_checks > 0

    def test_one_check_fails_gate_fails(self):
        gate = RegressionGate()
        result = gate.check(
            baseline_report=_report(completeness_pct=95.0, chains_broken=0),
            current_report=_report(completeness_pct=93.0, chains_broken=0),
            drift_report=_drift(total_changes=2, non_breaking_count=2),
            baseline_health=_health(90.0),
            current_health=_health(50.0),  # below 70.0 threshold
        )

        assert result.passed is False
        assert result.failed_checks >= 1

    def test_multiple_checks_fail_correct_counts(self):
        gate = RegressionGate()
        change = _breaking_change("Removed critical field")
        result = gate.check(
            baseline_report=_report(completeness_pct=95.0, chains_broken=0),
            current_report=_report(completeness_pct=50.0, chains_broken=5),
            drift_report=_drift(
                total_changes=1,
                breaking_count=1,
                changes=[change],
            ),
            baseline_health=_health(90.0),
            current_health=_health(40.0),
        )

        assert result.passed is False
        # Expecting failures on: completeness_regression, health_minimum,
        # health_regression, contract_drift, blocking_failures
        assert result.failed_checks >= 3
        assert result.total_checks == len(result.checks)
        assert result.failed_checks == len(result.failures)


# ---------------------------------------------------------------------------
# 17. Custom thresholds
# ---------------------------------------------------------------------------


class TestCustomThresholds:
    def test_custom_thresholds_override_defaults(self):
        # max_completeness_drop is also used for health regression threshold,
        # so set it high enough to cover both the completeness drop (15%)
        # and the health regression drop (25%).
        gate = RegressionGate(thresholds={
            "min_health_score": 50.0,
            "max_completeness_drop": 30.0,
            "max_blocking_failure_increase": 3,
        })

        # These would fail with defaults but pass with custom thresholds:
        # - completeness drops 15% (default max: 5%)
        # - health 55.0 (default min: 70.0)
        # - health regression 25 (default max: 5.0)
        # - blocking failures increase by 2 (default max: 0)
        result = gate.check(
            baseline_report=_report(completeness_pct=100.0, chains_broken=0),
            current_report=_report(completeness_pct=85.0, chains_broken=2),
            baseline_health=_health(80.0),
            current_health=_health(55.0),
        )

        assert result.passed is True
        assert result.failed_checks == 0


# ---------------------------------------------------------------------------
# 18. Only current_report provided (no baseline)
# ---------------------------------------------------------------------------


class TestPartialInputs:
    def test_only_current_report_checks_blocking_failures(self):
        gate = RegressionGate()
        result = gate.check(
            current_report=_report(chains_broken=0),
        )

        # completeness_regression is skipped (needs both baseline + current)
        completeness_checks = [
            c for c in result.checks if c.check_id == "completeness_regression"
        ]
        assert len(completeness_checks) == 0

        # blocking_failures uses baseline=0 when no baseline provided
        blocking_checks = [
            c for c in result.checks if c.check_id == "blocking_failures"
        ]
        assert len(blocking_checks) == 1
        assert blocking_checks[0].passed is True
        assert blocking_checks[0].baseline_value == 0.0

    def test_only_current_report_with_broken_chains_fails(self):
        gate = RegressionGate()
        result = gate.check(
            current_report=_report(chains_broken=3),
        )

        blocking_checks = [
            c for c in result.checks if c.check_id == "blocking_failures"
        ]
        assert len(blocking_checks) == 1
        assert blocking_checks[0].passed is False
        assert blocking_checks[0].baseline_value == 0.0
        assert blocking_checks[0].current_value == 3.0


# ---------------------------------------------------------------------------
# 19. GateResult.failures property
# ---------------------------------------------------------------------------


class TestGateResultFailures:
    def test_failures_property_returns_only_failed_checks(self):
        result = GateResult(
            passed=False,
            checks=[
                GateCheck(check_id="a", passed=True, message="ok"),
                GateCheck(check_id="b", passed=False, message="bad"),
                GateCheck(check_id="c", passed=True, message="ok"),
                GateCheck(check_id="d", passed=False, message="also bad"),
            ],
            total_checks=4,
            failed_checks=2,
        )

        failures = result.failures
        assert len(failures) == 2
        assert all(not f.passed for f in failures)
        assert {f.check_id for f in failures} == {"b", "d"}


# ---------------------------------------------------------------------------
# 20. GateResult.passed_checks_list property
# ---------------------------------------------------------------------------


class TestGateResultPassedChecksList:
    def test_passed_checks_list_returns_only_passed_checks(self):
        result = GateResult(
            passed=False,
            checks=[
                GateCheck(check_id="a", passed=True, message="ok"),
                GateCheck(check_id="b", passed=False, message="bad"),
                GateCheck(check_id="c", passed=True, message="ok"),
            ],
            total_checks=3,
            failed_checks=1,
        )

        passed_list = result.passed_checks_list
        assert len(passed_list) == 2
        assert all(p.passed for p in passed_list)
        assert {p.check_id for p in passed_list} == {"a", "c"}


# ---------------------------------------------------------------------------
# 21. GateCheck model fields
# ---------------------------------------------------------------------------


class TestGateCheckModel:
    def test_gate_check_default_values(self):
        check = GateCheck(check_id="test_check")
        assert check.check_id == "test_check"
        assert check.passed is True
        assert check.message == ""
        assert check.baseline_value is None
        assert check.current_value is None

    def test_gate_check_explicit_values(self):
        check = GateCheck(
            check_id="completeness_regression",
            passed=False,
            message="Completeness dropped",
            baseline_value=95.0,
            current_value=80.0,
        )
        assert check.check_id == "completeness_regression"
        assert check.passed is False
        assert check.message == "Completeness dropped"
        assert check.baseline_value == 95.0
        assert check.current_value == 80.0

    def test_gate_check_forbids_extra_fields(self):
        with pytest.raises(Exception):
            GateCheck(check_id="test", unknown_field="nope")


# ---------------------------------------------------------------------------
# 22. Zero-change drift report -> passes
# ---------------------------------------------------------------------------


class TestZeroChangeDrift:
    def test_zero_change_drift_report_passes(self):
        gate = RegressionGate()
        result = gate.check(
            drift_report=_drift(
                total_changes=0,
                breaking_count=0,
                non_breaking_count=0,
            ),
        )

        drift_checks = [
            c for c in result.checks if c.check_id == "contract_drift"
        ]
        assert len(drift_checks) == 1
        assert drift_checks[0].passed is True
        assert "No breaking drift" in drift_checks[0].message
        assert "0 non-breaking" in drift_checks[0].message
