"""
OTel span event emission helpers for observability & alerting — Layer 6.

Follows the ``_add_span_event()`` pattern from ``propagation/otel.py``.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.observability.otel import (
        emit_alert_event,
        emit_alert_evaluation,
        emit_health_score,
    )

    emit_health_score(score)
    emit_alert_evaluation(result)
    for event in result.events:
        if event.firing:
            emit_alert_event(event)
"""

from __future__ import annotations

import logging

from contextcore.contracts.observability.alerts import (
    AlertEvaluationResult,
    AlertEvent,
)
from contextcore.contracts.observability.health import HealthScore

try:
    from opentelemetry import trace as otel_trace

    _HAS_OTEL = True
except ImportError:  # pragma: no cover
    _HAS_OTEL = False

logger = logging.getLogger(__name__)


def _add_span_event(name: str, attributes: dict[str, str | int | float | bool]) -> None:
    """Add an event to the current OTel span if available."""
    if not _HAS_OTEL:
        return
    span = otel_trace.get_current_span()
    if span and span.is_recording():
        span.add_event(name=name, attributes=attributes)


def emit_health_score(score: HealthScore) -> None:
    """Emit a span event with the propagation health score.

    Event name: ``context.observability.health``
    """
    attrs: dict[str, str | int | float | bool] = {
        "observability.health.overall": score.overall,
        "observability.health.completeness": score.completeness_score,
        "observability.health.boundary": score.boundary_score,
        "observability.health.preflight": score.preflight_score,
        "observability.health.discrepancy_penalty": score.discrepancy_penalty,
    }

    logger.info(
        "Propagation health score: %.1f/100",
        score.overall,
    )

    _add_span_event("context.observability.health", attrs)


def emit_alert_event(event: AlertEvent) -> None:
    """Emit a span event for a single alert.

    Event name: ``context.observability.alert``
    """
    attrs: dict[str, str | int | float | bool] = {
        "observability.alert.rule_id": event.rule_id,
        "observability.alert.firing": event.firing,
        "observability.alert.severity": event.severity.value,
        "observability.alert.metric": event.metric,
        "observability.alert.actual_value": event.actual_value,
        "observability.alert.threshold": event.threshold,
        "observability.alert.message": event.message,
    }

    if event.firing:
        log_fn = (
            logger.warning
            if event.severity.value == "blocking"
            else logger.info
        )
        log_fn(
            "Alert FIRING: [%s] %s — %s",
            event.severity.value,
            event.rule_id,
            event.message,
        )

    _add_span_event("context.observability.alert", attrs)


def emit_alert_evaluation(result: AlertEvaluationResult) -> None:
    """Emit a summary span event for the alert evaluation.

    Event name: ``context.observability.alert_evaluation``
    """
    attrs: dict[str, str | int | float | bool] = {
        "observability.alert.rules_evaluated": result.rules_evaluated,
        "observability.alert.alerts_firing": result.alerts_firing,
        "observability.alert.has_critical": len(result.critical_alerts) > 0,
        "observability.alert.critical_count": len(result.critical_alerts),
        "observability.alert.warning_count": len(result.warning_alerts),
    }

    if result.has_firing_alerts:
        logger.warning(
            "Alert evaluation: %d/%d firing (critical=%d, warning=%d)",
            result.alerts_firing,
            result.rules_evaluated,
            len(result.critical_alerts),
            len(result.warning_alerts),
        )
    else:
        logger.info(
            "Alert evaluation: 0/%d firing",
            result.rules_evaluated,
        )

    _add_span_event("context.observability.alert_evaluation", attrs)
