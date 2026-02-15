"""Tests for pre-flight OTel span event emission helpers."""

from unittest.mock import MagicMock, patch

import pytest

from contextcore.contracts.preflight.checker import (
    PhaseGraphIssue,
    PreflightResult,
    PreflightViolation,
)
from contextcore.contracts.preflight.otel import (
    emit_preflight_result,
    emit_preflight_violation,
)
from contextcore.contracts.types import ConstraintSeverity


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
    with patch("contextcore.contracts.preflight.otel._HAS_OTEL", True), \
         patch("contextcore.contracts.preflight.otel.otel_trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        yield mock_span


# ---------------------------------------------------------------------------
# emit_preflight_result
# ---------------------------------------------------------------------------


class TestEmitPreflightResult:
    def test_passed_result_emits_correct_event(self, mock_otel):
        """A passed result emits 'context.preflight.result' with correct attrs."""
        result = PreflightResult(
            passed=True,
            phases_checked=3,
            fields_checked=7,
        )
        emit_preflight_result(result)
        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.preflight.result"
        attrs = call_args.kwargs["attributes"]
        assert attrs["preflight.passed"] is True
        assert attrs["preflight.phases_checked"] == 3
        assert attrs["preflight.fields_checked"] == 7
        assert attrs["preflight.critical_count"] == 0
        assert attrs["preflight.warning_count"] == 0
        assert attrs["preflight.advisory_count"] == 0
        assert attrs["preflight.graph_issues"] == 0

    def test_failed_result_includes_violation_counts(self, mock_otel):
        """A failed result includes correct critical/warning/advisory counts."""
        violations = [
            PreflightViolation(
                check_type="field_readiness",
                phase="implement",
                field="tasks",
                severity=ConstraintSeverity.BLOCKING,
                message="Field 'tasks' required by phase 'implement' is not ready",
            ),
            PreflightViolation(
                check_type="field_readiness",
                phase="implement",
                field="design_results",
                severity=ConstraintSeverity.BLOCKING,
                message="Field 'design_results' required by phase 'implement' is not ready",
            ),
            PreflightViolation(
                check_type="seed_enrichment",
                phase="plan",
                field="domain",
                severity=ConstraintSeverity.WARNING,
                message="Enrichment field 'domain' has default/missing value",
            ),
            PreflightViolation(
                check_type="phase_graph",
                phase="test",
                field="artifacts",
                severity=ConstraintSeverity.ADVISORY,
                message="Phase 'test' produces 'artifacts' but no phase requires it",
            ),
        ]
        result = PreflightResult(
            passed=False,
            violations=violations,
            phases_checked=4,
            fields_checked=10,
        )
        emit_preflight_result(result)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["preflight.passed"] is False
        assert attrs["preflight.critical_count"] == 2
        assert attrs["preflight.warning_count"] == 1
        assert attrs["preflight.advisory_count"] == 1

    def test_zero_violations_result(self, mock_otel):
        """A result with no violations at all emits zeroed counts."""
        result = PreflightResult(
            passed=True,
            violations=[],
            phases_checked=2,
            fields_checked=5,
        )
        emit_preflight_result(result)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["preflight.critical_count"] == 0
        assert attrs["preflight.warning_count"] == 0
        assert attrs["preflight.advisory_count"] == 0
        assert attrs["preflight.graph_issues"] == 0

    def test_result_with_graph_issues_includes_count(self, mock_otel):
        """A result with phase graph issues includes the graph_issues count."""
        graph_issues = [
            PhaseGraphIssue(
                issue_type="dangling_read",
                phase="implement",
                field="tasks",
                message="Phase 'implement' requires 'tasks' but no earlier phase produces it",
            ),
            PhaseGraphIssue(
                issue_type="dead_write",
                phase="plan",
                field="notes",
                message="Phase 'plan' produces 'notes' but no phase requires it",
            ),
        ]
        result = PreflightResult(
            passed=True,
            violations=[],
            phase_graph_issues=graph_issues,
            phases_checked=3,
            fields_checked=4,
        )
        emit_preflight_result(result)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["preflight.graph_issues"] == 2

    def test_no_otel_does_not_crash(self):
        """When OTel is not available, emit_preflight_result should not crash."""
        with patch("contextcore.contracts.preflight.otel._HAS_OTEL", False):
            result = PreflightResult(
                passed=True,
                phases_checked=1,
                fields_checked=2,
            )
            emit_preflight_result(result)  # Should not raise


# ---------------------------------------------------------------------------
# emit_preflight_violation
# ---------------------------------------------------------------------------


class TestEmitPreflightViolation:
    def test_emits_correct_event_and_attrs(self, mock_otel):
        """Emits 'context.preflight.violation' with correct attributes."""
        violation = PreflightViolation(
            check_type="seed_enrichment",
            phase="plan",
            field="domain",
            severity=ConstraintSeverity.WARNING,
            message="Enrichment field 'domain' has default/missing value",
        )
        emit_preflight_violation(violation)
        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.preflight.violation"
        attrs = call_args.kwargs["attributes"]
        assert attrs["preflight.check_type"] == "seed_enrichment"
        assert attrs["preflight.phase"] == "plan"
        assert attrs["preflight.field"] == "domain"
        assert attrs["preflight.severity"] == "warning"
        assert attrs["preflight.message"] == "Enrichment field 'domain' has default/missing value"

    def test_field_readiness_violation_has_correct_check_type(self, mock_otel):
        """A field readiness violation has check_type 'field_readiness'."""
        violation = PreflightViolation(
            check_type="field_readiness",
            phase="implement",
            field="tasks",
            severity=ConstraintSeverity.BLOCKING,
            message="Field 'tasks' required by phase 'implement' is not ready",
        )
        emit_preflight_violation(violation)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["preflight.check_type"] == "field_readiness"
        assert attrs["preflight.severity"] == "blocking"
        assert attrs["preflight.field"] == "tasks"

    def test_no_otel_does_not_crash(self):
        """When OTel is not available, emit_preflight_violation should not crash."""
        with patch("contextcore.contracts.preflight.otel._HAS_OTEL", False):
            violation = PreflightViolation(
                check_type="phase_graph",
                phase="test",
                field="artifacts",
                severity=ConstraintSeverity.ADVISORY,
                message="Phase 'test' produces 'artifacts' but no phase requires it",
            )
            emit_preflight_violation(violation)  # Should not raise
