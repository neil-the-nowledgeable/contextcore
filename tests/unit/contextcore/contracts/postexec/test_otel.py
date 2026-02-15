"""Tests for OTel span event emission helpers for post-execution validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from contextcore.contracts.postexec.otel import (
    emit_postexec_discrepancy,
    emit_postexec_report,
)
from contextcore.contracts.postexec.validator import (
    PostExecutionReport,
    RuntimeDiscrepancy,
)
from contextcore.contracts.propagation.validator import ContractValidationResult
from contextcore.contracts.types import PropagationStatus


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
    with patch("contextcore.contracts.postexec.otel._HAS_OTEL", True), \
         patch("contextcore.contracts.postexec.otel.otel_trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        yield mock_span


# ---------------------------------------------------------------------------
# emit_postexec_report
# ---------------------------------------------------------------------------


class TestEmitPostexecReport:
    def test_emits_correct_event_for_passing_report(self, mock_otel):
        report = PostExecutionReport(
            passed=True,
            chains_total=3,
            chains_intact=3,
            chains_degraded=0,
            chains_broken=0,
            completeness_pct=100.0,
        )
        emit_postexec_report(report)
        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.postexec.report"
        attrs = call_args.kwargs["attributes"]
        assert attrs["postexec.passed"] is True
        assert attrs["postexec.chains_total"] == 3
        assert attrs["postexec.chains_intact"] == 3
        assert attrs["postexec.chains_degraded"] == 0
        assert attrs["postexec.chains_broken"] == 0
        assert attrs["postexec.completeness_pct"] == 100.0
        assert attrs["postexec.discrepancy_count"] == 0

    def test_emits_correct_attrs_for_failing_report(self, mock_otel):
        report = PostExecutionReport(
            passed=False,
            chains_total=3,
            chains_intact=1,
            chains_degraded=1,
            chains_broken=1,
            completeness_pct=33.3,
        )
        emit_postexec_report(report)
        mock_otel.add_event.assert_called_once()
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["postexec.passed"] is False
        assert attrs["postexec.chains_total"] == 3
        assert attrs["postexec.chains_intact"] == 1
        assert attrs["postexec.chains_degraded"] == 1
        assert attrs["postexec.chains_broken"] == 1
        assert attrs["postexec.completeness_pct"] == 33.3
        assert attrs["postexec.discrepancy_count"] == 0

    def test_includes_final_exit_passed_attr(self, mock_otel):
        exit_result = ContractValidationResult(
            passed=True,
            phase="validate",
            direction="exit",
            propagation_status=PropagationStatus.PROPAGATED,
        )
        report = PostExecutionReport(
            passed=True,
            chains_total=3,
            chains_intact=3,
            chains_degraded=0,
            chains_broken=0,
            completeness_pct=100.0,
            final_exit_result=exit_result,
        )
        emit_postexec_report(report)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["postexec.final_exit_passed"] is True

    def test_no_otel_does_not_crash(self):
        with patch("contextcore.contracts.postexec.otel._HAS_OTEL", False):
            report = PostExecutionReport(
                passed=True,
                chains_total=3,
                chains_intact=3,
                chains_degraded=0,
                chains_broken=0,
                completeness_pct=100.0,
            )
            emit_postexec_report(report)  # Should not raise


# ---------------------------------------------------------------------------
# emit_postexec_discrepancy
# ---------------------------------------------------------------------------


class TestEmitPostexecDiscrepancy:
    def test_emits_correct_event_for_late_corruption(self, mock_otel):
        discrepancy = RuntimeDiscrepancy(
            phase="implement",
            discrepancy_type="late_corruption",
            message="Phase 'implement' passed runtime checks but chain is broken",
        )
        emit_postexec_discrepancy(discrepancy)
        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.postexec.discrepancy"
        attrs = call_args.kwargs["attributes"]
        assert attrs["postexec.discrepancy_type"] == "late_corruption"

    def test_emits_correct_attrs_for_late_healing(self, mock_otel):
        discrepancy = RuntimeDiscrepancy(
            phase="design",
            discrepancy_type="late_healing",
            message="Phase 'design' failed runtime checks but chains are now intact",
        )
        emit_postexec_discrepancy(discrepancy)
        mock_otel.add_event.assert_called_once()
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["postexec.discrepancy_type"] == "late_healing"

    def test_includes_phase_and_message_in_attrs(self, mock_otel):
        discrepancy = RuntimeDiscrepancy(
            phase="validate",
            discrepancy_type="late_corruption",
            message="Context corrupted after validation",
        )
        emit_postexec_discrepancy(discrepancy)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["postexec.phase"] == "validate"
        assert attrs["postexec.message"] == "Context corrupted after validation"
        assert attrs["postexec.discrepancy_type"] == "late_corruption"

    def test_no_otel_does_not_crash(self):
        with patch("contextcore.contracts.postexec.otel._HAS_OTEL", False):
            discrepancy = RuntimeDiscrepancy(
                phase="implement",
                discrepancy_type="late_corruption",
                message="Phase 'implement' passed runtime checks but chain is broken",
            )
            emit_postexec_discrepancy(discrepancy)  # Should not raise
