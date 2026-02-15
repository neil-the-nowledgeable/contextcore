"""Tests for OTel span event emission helpers for observability & alerting (Layer 6)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from contextcore.contracts.observability.alerts import (
    AlertEvaluationResult,
    AlertEvent,
)
from contextcore.contracts.observability.health import HealthScore
from contextcore.contracts.observability.otel import (
    emit_alert_evaluation,
    emit_alert_event,
    emit_health_score,
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
    with patch("contextcore.contracts.observability.otel._HAS_OTEL", True), \
         patch("contextcore.contracts.observability.otel.otel_trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        yield mock_span


# ---------------------------------------------------------------------------
# emit_health_score
# ---------------------------------------------------------------------------


class TestEmitHealthScore:
    def test_emits_correct_event_with_all_attrs(self, mock_otel):
        score = HealthScore(
            overall=85.0,
            completeness_score=100.0,
            boundary_score=80.0,
            preflight_score=100.0,
            discrepancy_penalty=0.0,
        )
        emit_health_score(score)

        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.observability.health"

    def test_attrs_include_all_five_scores(self, mock_otel):
        score = HealthScore(
            overall=72.5,
            completeness_score=90.0,
            boundary_score=60.0,
            preflight_score=100.0,
            discrepancy_penalty=25.0,
        )
        emit_health_score(score)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["observability.health.overall"] == 72.5
        assert attrs["observability.health.completeness"] == 90.0
        assert attrs["observability.health.boundary"] == 60.0
        assert attrs["observability.health.preflight"] == 100.0
        assert attrs["observability.health.discrepancy_penalty"] == 25.0

    def test_no_otel_does_not_crash(self):
        with patch("contextcore.contracts.observability.otel._HAS_OTEL", False):
            score = HealthScore(
                overall=85.0,
                completeness_score=100.0,
                boundary_score=80.0,
                preflight_score=100.0,
                discrepancy_penalty=0.0,
            )
            emit_health_score(score)  # Should not raise


# ---------------------------------------------------------------------------
# emit_alert_event
# ---------------------------------------------------------------------------


class TestEmitAlertEvent:
    def test_emits_correct_event_for_firing_alert(self, mock_otel):
        alert = AlertEvent(
            rule_id="test.rule",
            firing=True,
            severity=ConstraintSeverity.WARNING,
            metric="completeness_pct",
            actual_value=70.0,
            threshold=80.0,
            operator="lt",
            message="Completeness below threshold",
        )
        emit_alert_event(alert)

        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.observability.alert"

    def test_attrs_include_all_seven_fields(self, mock_otel):
        alert = AlertEvent(
            rule_id="test.rule",
            firing=True,
            severity=ConstraintSeverity.WARNING,
            metric="completeness_pct",
            actual_value=70.0,
            threshold=80.0,
            operator="lt",
            message="Completeness below threshold",
        )
        emit_alert_event(alert)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["observability.alert.rule_id"] == "test.rule"
        assert attrs["observability.alert.firing"] is True
        assert attrs["observability.alert.severity"] == "warning"
        assert attrs["observability.alert.metric"] == "completeness_pct"
        assert attrs["observability.alert.actual_value"] == 70.0
        assert attrs["observability.alert.threshold"] == 80.0
        assert attrs["observability.alert.message"] == "Completeness below threshold"

    def test_no_otel_does_not_crash(self):
        with patch("contextcore.contracts.observability.otel._HAS_OTEL", False):
            alert = AlertEvent(
                rule_id="test.rule",
                firing=True,
                severity=ConstraintSeverity.WARNING,
                metric="completeness_pct",
                actual_value=70.0,
                threshold=80.0,
                operator="lt",
                message="Completeness below threshold",
            )
            emit_alert_event(alert)  # Should not raise


# ---------------------------------------------------------------------------
# emit_alert_evaluation
# ---------------------------------------------------------------------------


class TestEmitAlertEvaluation:
    def test_emits_correct_event_for_clean_eval(self, mock_otel):
        eval_result = AlertEvaluationResult(
            events=[],
            rules_evaluated=5,
            alerts_firing=0,
        )
        emit_alert_evaluation(eval_result)

        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.observability.alert_evaluation"
        attrs = call_args.kwargs["attributes"]
        assert attrs["observability.alert.rules_evaluated"] == 5
        assert attrs["observability.alert.alerts_firing"] == 0
        assert attrs["observability.alert.has_critical"] is False
        assert attrs["observability.alert.critical_count"] == 0
        assert attrs["observability.alert.warning_count"] == 0

    def test_includes_correct_counts_for_firing_alerts(self, mock_otel):
        warning_alert = AlertEvent(
            rule_id="warn.rule",
            firing=True,
            severity=ConstraintSeverity.WARNING,
            metric="completeness_pct",
            actual_value=70.0,
            threshold=80.0,
            operator="lt",
            message="Warning alert",
        )
        critical_alert = AlertEvent(
            rule_id="crit.rule",
            firing=True,
            severity=ConstraintSeverity.BLOCKING,
            metric="blocking_failures",
            actual_value=3.0,
            threshold=0.0,
            operator="gt",
            message="Critical alert",
        )
        eval_result = AlertEvaluationResult(
            events=[warning_alert, critical_alert],
            rules_evaluated=5,
            alerts_firing=2,
        )
        emit_alert_evaluation(eval_result)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["observability.alert.rules_evaluated"] == 5
        assert attrs["observability.alert.alerts_firing"] == 2
        assert attrs["observability.alert.critical_count"] == 1
        assert attrs["observability.alert.warning_count"] == 1

    def test_has_critical_attr_set_correctly(self, mock_otel):
        critical_alert = AlertEvent(
            rule_id="crit.rule",
            firing=True,
            severity=ConstraintSeverity.BLOCKING,
            metric="blocking_failures",
            actual_value=1.0,
            threshold=0.0,
            operator="gt",
            message="Blocking failure",
        )
        eval_result = AlertEvaluationResult(
            events=[critical_alert],
            rules_evaluated=1,
            alerts_firing=1,
        )
        emit_alert_evaluation(eval_result)

        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["observability.alert.has_critical"] is True

    def test_no_otel_does_not_crash(self):
        with patch("contextcore.contracts.observability.otel._HAS_OTEL", False):
            eval_result = AlertEvaluationResult(
                events=[],
                rules_evaluated=5,
                alerts_firing=0,
            )
            emit_alert_evaluation(eval_result)  # Should not raise
