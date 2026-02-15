"""Tests for OTel span event emission helpers for runtime boundary checks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from contextcore.contracts.propagation.validator import (
    ContractValidationResult,
    FieldValidationResult,
)
from contextcore.contracts.runtime.guard import (
    PhaseExecutionRecord,
    WorkflowRunSummary,
)
from contextcore.contracts.runtime.otel import (
    emit_phase_boundary,
    emit_workflow_summary,
)
from contextcore.contracts.types import (
    ConstraintSeverity,
    EnforcementMode,
    PropagationStatus,
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
    with patch("contextcore.contracts.runtime.otel._HAS_OTEL", True), \
         patch("contextcore.contracts.runtime.otel.otel_trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        yield mock_span


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_passing_result(phase: str = "plan", direction: str = "entry") -> ContractValidationResult:
    """Build a ContractValidationResult that passes."""
    return ContractValidationResult(
        passed=True,
        phase=phase,
        direction=direction,
        propagation_status=PropagationStatus.PROPAGATED,
    )


def _make_failing_result(
    phase: str = "plan",
    direction: str = "entry",
    blocking_failures: list[str] | None = None,
) -> ContractValidationResult:
    """Build a ContractValidationResult that fails."""
    return ContractValidationResult(
        passed=False,
        phase=phase,
        direction=direction,
        blocking_failures=blocking_failures or ["domain"],
        propagation_status=PropagationStatus.FAILED,
    )


# ---------------------------------------------------------------------------
# emit_phase_boundary
# ---------------------------------------------------------------------------


class TestEmitPhaseBoundary:
    def test_emits_correct_event_passing_record(self, mock_otel):
        """Passing record emits phase_boundary with all-green attributes."""
        entry_result = _make_passing_result(phase="implement", direction="entry")
        exit_result = _make_passing_result(phase="implement", direction="exit")
        record = PhaseExecutionRecord(
            phase="implement",
            entry_result=entry_result,
            exit_result=exit_result,
        )

        emit_phase_boundary(record)

        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.runtime.phase_boundary"

        attrs = call_args.kwargs["attributes"]
        assert attrs["runtime.phase"] == "implement"
        assert attrs["runtime.passed"] is True
        assert attrs["runtime.entry.passed"] is True
        assert attrs["runtime.entry.status"] == "propagated"
        assert attrs["runtime.entry.blocking_count"] == 0
        assert attrs["runtime.entry.warning_count"] == 0
        assert attrs["runtime.exit.passed"] is True
        assert attrs["runtime.exit.status"] == "propagated"
        assert attrs["runtime.exit.blocking_count"] == 0
        assert attrs["runtime.exit.warning_count"] == 0
        assert attrs["runtime.propagation_status"] == "propagated"

    def test_emits_correct_attrs_for_failing_entry(self, mock_otel):
        """Failing entry result populates blocking counts and failed status."""
        entry_result = _make_failing_result(
            phase="plan",
            direction="entry",
            blocking_failures=["domain", "project_id"],
        )
        record = PhaseExecutionRecord(
            phase="plan",
            entry_result=entry_result,
        )

        emit_phase_boundary(record)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["runtime.passed"] is False
        assert attrs["runtime.entry.passed"] is False
        assert attrs["runtime.entry.status"] == "failed"
        assert attrs["runtime.entry.blocking_count"] == 2
        # exit was None so defaults apply
        assert attrs["runtime.exit.passed"] is True
        assert attrs["runtime.exit.status"] == "propagated"
        assert attrs["runtime.exit.blocking_count"] == 0
        assert attrs["runtime.propagation_status"] == "failed"

    def test_handles_record_with_only_exit_result(self, mock_otel):
        """Record with entry=None and exit populated uses defaults for entry."""
        exit_result = _make_passing_result(phase="validate", direction="exit")
        record = PhaseExecutionRecord(
            phase="validate",
            exit_result=exit_result,
        )

        emit_phase_boundary(record)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["runtime.phase"] == "validate"
        assert attrs["runtime.passed"] is True
        # entry is None, defaults to passed/propagated
        assert attrs["runtime.entry.passed"] is True
        assert attrs["runtime.entry.status"] == "propagated"
        assert attrs["runtime.entry.blocking_count"] == 0
        assert attrs["runtime.entry.warning_count"] == 0
        # exit is populated
        assert attrs["runtime.exit.passed"] is True
        assert attrs["runtime.exit.status"] == "propagated"

    def test_no_otel_does_not_crash(self):
        """When _HAS_OTEL is False, emit_phase_boundary does nothing."""
        with patch("contextcore.contracts.runtime.otel._HAS_OTEL", False):
            record = PhaseExecutionRecord(
                phase="plan",
                entry_result=_make_passing_result(),
            )
            emit_phase_boundary(record)  # Should not raise


# ---------------------------------------------------------------------------
# emit_workflow_summary
# ---------------------------------------------------------------------------


class TestEmitWorkflowSummary:
    def test_emits_correct_event_passing_summary(self, mock_otel):
        """Passing workflow summary emits all expected attributes."""
        summary = WorkflowRunSummary(
            mode=EnforcementMode.STRICT,
            total_phases=3,
            passed_phases=3,
            failed_phases=0,
            total_fields_checked=12,
            total_blocking_failures=0,
            total_warnings=1,
            total_defaults_applied=1,
            overall_passed=True,
            overall_status=PropagationStatus.PROPAGATED,
        )

        emit_workflow_summary(summary)

        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.runtime.workflow_summary"

        attrs = call_args.kwargs["attributes"]
        assert attrs["runtime.total_phases"] == 3
        assert attrs["runtime.passed_phases"] == 3
        assert attrs["runtime.failed_phases"] == 0
        assert attrs["runtime.total_fields_checked"] == 12
        assert attrs["runtime.total_blocking_failures"] == 0
        assert attrs["runtime.total_warnings"] == 1
        assert attrs["runtime.total_defaults_applied"] == 1
        assert attrs["runtime.overall_passed"] is True
        assert attrs["runtime.overall_status"] == "propagated"

    def test_emits_correct_attrs_for_failing_summary(self, mock_otel):
        """Failing workflow summary populates failure counts and status."""
        summary = WorkflowRunSummary(
            mode=EnforcementMode.PERMISSIVE,
            total_phases=4,
            passed_phases=2,
            failed_phases=2,
            total_fields_checked=20,
            total_blocking_failures=3,
            total_warnings=5,
            total_defaults_applied=2,
            overall_passed=False,
            overall_status=PropagationStatus.FAILED,
        )

        emit_workflow_summary(summary)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["runtime.total_phases"] == 4
        assert attrs["runtime.passed_phases"] == 2
        assert attrs["runtime.failed_phases"] == 2
        assert attrs["runtime.total_blocking_failures"] == 3
        assert attrs["runtime.total_warnings"] == 5
        assert attrs["runtime.total_defaults_applied"] == 2
        assert attrs["runtime.overall_passed"] is False
        assert attrs["runtime.overall_status"] == "failed"

    def test_emits_mode_attribute_correctly(self, mock_otel):
        """Each enforcement mode value is correctly emitted as a string."""
        for mode in EnforcementMode:
            mock_otel.reset_mock()

            summary = WorkflowRunSummary(
                mode=mode,
                total_phases=1,
                passed_phases=1,
                failed_phases=0,
                overall_passed=True,
                overall_status=PropagationStatus.PROPAGATED,
            )

            emit_workflow_summary(summary)

            attrs = mock_otel.add_event.call_args.kwargs["attributes"]
            assert attrs["runtime.mode"] == mode.value

    def test_no_otel_does_not_crash(self):
        """When _HAS_OTEL is False, emit_workflow_summary does nothing."""
        with patch("contextcore.contracts.runtime.otel._HAS_OTEL", False):
            summary = WorkflowRunSummary(
                mode=EnforcementMode.AUDIT,
                total_phases=1,
                passed_phases=1,
                failed_phases=0,
                overall_passed=True,
                overall_status=PropagationStatus.PROPAGATED,
            )
            emit_workflow_summary(summary)  # Should not raise
