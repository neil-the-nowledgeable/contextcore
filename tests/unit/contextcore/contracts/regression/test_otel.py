"""Tests for OTel span event emission helpers for regression prevention (Layer 7)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from contextcore.contracts.regression.drift import DriftChange, DriftReport
from contextcore.contracts.regression.gate import GateCheck, GateResult
from contextcore.contracts.regression.otel import (
    emit_drift_report,
    emit_gate_check,
    emit_gate_result,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_span():
    """Create a mock OTel span that is recording."""
    span = MagicMock()
    span.is_recording.return_value = True
    return span


@pytest.fixture
def mock_otel(mock_span):
    """Patch OTel to return our mock span."""
    with patch("contextcore.contracts.regression.otel._HAS_OTEL", True), \
         patch("contextcore.contracts.regression.otel.otel_trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        yield mock_span


# ---------------------------------------------------------------------------
# emit_drift_report
# ---------------------------------------------------------------------------


class TestEmitDriftReport:
    def test_emits_correct_event_name(self, mock_otel):
        report = DriftReport(
            total_changes=0,
            breaking_count=0,
            non_breaking_count=0,
            old_pipeline_id="pipe-v1",
            new_pipeline_id="pipe-v2",
        )
        emit_drift_report(report)

        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.regression.drift"

    def test_attrs_include_all_fields(self, mock_otel):
        report = DriftReport(
            total_changes=3,
            breaking_count=1,
            non_breaking_count=2,
            old_pipeline_id="pipe-v1",
            new_pipeline_id="pipe-v2",
        )
        emit_drift_report(report)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["regression.drift.total_changes"] == 3
        assert attrs["regression.drift.breaking_count"] == 1
        assert attrs["regression.drift.non_breaking_count"] == 2
        assert attrs["regression.drift.has_breaking"] is True
        assert attrs["regression.drift.old_pipeline_id"] == "pipe-v1"
        assert attrs["regression.drift.new_pipeline_id"] == "pipe-v2"

    def test_with_breaking_changes(self, mock_otel):
        breaking_change = DriftChange(
            change_type="phase_removed",
            phase="validation",
            breaking=True,
            description="Phase 'validation' removed",
        )
        report = DriftReport(
            changes=[breaking_change],
            total_changes=1,
            breaking_count=1,
            non_breaking_count=0,
            old_pipeline_id="pipe-v1",
            new_pipeline_id="pipe-v2",
        )
        emit_drift_report(report)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["regression.drift.has_breaking"] is True
        assert attrs["regression.drift.breaking_count"] == 1

    def test_without_breaking_changes_has_breaking_false(self, mock_otel):
        report = DriftReport(
            total_changes=2,
            breaking_count=0,
            non_breaking_count=2,
            old_pipeline_id="pipe-v1",
            new_pipeline_id="pipe-v2",
        )
        emit_drift_report(report)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["regression.drift.has_breaking"] is False


# ---------------------------------------------------------------------------
# emit_gate_result
# ---------------------------------------------------------------------------


class TestEmitGateResult:
    def test_emits_correct_event_name(self, mock_otel):
        result = GateResult(
            passed=True,
            total_checks=3,
            failed_checks=0,
        )
        emit_gate_result(result)

        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.regression.gate"

    def test_attrs_include_all_fields(self, mock_otel):
        result = GateResult(
            passed=True,
            total_checks=5,
            failed_checks=0,
        )
        emit_gate_result(result)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["regression.gate.passed"] is True
        assert attrs["regression.gate.total_checks"] == 5
        assert attrs["regression.gate.failed_checks"] == 0

    def test_with_failed_gate(self, mock_otel):
        failed_check = GateCheck(
            check_id="completeness_regression",
            passed=False,
            message="Completeness dropped by 10%",
            baseline_value=90.0,
            current_value=80.0,
        )
        result = GateResult(
            passed=False,
            checks=[failed_check],
            total_checks=3,
            failed_checks=1,
        )
        emit_gate_result(result)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["regression.gate.passed"] is False
        assert attrs["regression.gate.total_checks"] == 3
        assert attrs["regression.gate.failed_checks"] == 1


# ---------------------------------------------------------------------------
# emit_gate_check
# ---------------------------------------------------------------------------


class TestEmitGateCheck:
    def test_emits_correct_event_name(self, mock_otel):
        check = GateCheck(
            check_id="health_minimum",
            passed=True,
            message="Health score OK: 85.0 >= 70.0",
        )
        emit_gate_check(check)

        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.regression.gate_check"

    def test_attrs_include_check_id_passed_message(self, mock_otel):
        check = GateCheck(
            check_id="contract_drift",
            passed=True,
            message="No breaking drift (2 non-breaking changes)",
        )
        emit_gate_check(check)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["regression.gate.check_id"] == "contract_drift"
        assert attrs["regression.gate.check_passed"] is True
        assert attrs["regression.gate.check_message"] == "No breaking drift (2 non-breaking changes)"

    def test_with_baseline_and_current_values(self, mock_otel):
        check = GateCheck(
            check_id="completeness_regression",
            passed=False,
            message="Completeness dropped by 10%",
            baseline_value=90.0,
            current_value=80.0,
        )
        emit_gate_check(check)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["regression.gate.check_id"] == "completeness_regression"
        assert attrs["regression.gate.check_passed"] is False
        assert attrs["regression.gate.baseline_value"] == 90.0
        assert attrs["regression.gate.current_value"] == 80.0

    def test_without_baseline_and_current_values_omits_keys(self, mock_otel):
        check = GateCheck(
            check_id="contract_drift",
            passed=True,
            message="No breaking drift",
        )
        emit_gate_check(check)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert "regression.gate.baseline_value" not in attrs
        assert "regression.gate.current_value" not in attrs


# ---------------------------------------------------------------------------
# No OTel available
# ---------------------------------------------------------------------------


class TestNoOtel:
    def test_no_otel_does_not_crash(self):
        """All emit functions degrade gracefully when OTel is not installed."""
        with patch("contextcore.contracts.regression.otel._HAS_OTEL", False):
            report = DriftReport(
                total_changes=1,
                breaking_count=1,
                non_breaking_count=0,
                old_pipeline_id="pipe-v1",
                new_pipeline_id="pipe-v2",
            )
            emit_drift_report(report)  # Should not raise

            result = GateResult(
                passed=False,
                total_checks=1,
                failed_checks=1,
            )
            emit_gate_result(result)  # Should not raise

            check = GateCheck(
                check_id="test_check",
                passed=False,
                message="Failure",
                baseline_value=100.0,
                current_value=50.0,
            )
            emit_gate_check(check)  # Should not raise
