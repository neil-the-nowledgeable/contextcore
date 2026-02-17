"""
OTel span event emission helpers for causal ordering validation.

Follows the ``_add_span_event()`` pattern from ``propagation/otel.py``.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.ordering.otel import (
        emit_ordering_result,
        emit_ordering_violation,
    )

    emit_ordering_result(validation_result)
    for check in validation_result.results:
        if not check.satisfied:
            emit_ordering_violation(check)
"""

from __future__ import annotations

import logging

from contextcore.contracts.ordering.validator import (
    OrderingCheckResult,
    OrderingValidationResult,
)

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


def emit_ordering_result(result: OrderingValidationResult) -> None:
    """Emit a span event summarising causal ordering validation.

    Event name: ``causal.ordering.complete``
    """
    attrs: dict[str, str | int | float | bool] = {
        "ordering.passed": result.passed,
        "ordering.total_checked": result.total_checked,
        "ordering.violations": result.violations,
    }

    if result.passed:
        logger.debug(
            "Ordering validation complete: %d/%d satisfied, %d violation(s)",
            result.total_checked - result.violations,
            result.total_checked,
            result.violations,
        )
    else:
        logger.warning(
            "Ordering validation FAILED: %d/%d violations (includes blocking)",
            result.violations,
            result.total_checked,
        )

    _add_span_event("causal.ordering.complete", attrs)


def emit_ordering_violation(check: OrderingCheckResult) -> None:
    """Emit a span event for a single ordering violation.

    Event name: ``causal.ordering.violation``

    Only call this for checks where ``satisfied is False``.
    """
    attrs: dict[str, str | int | float | bool] = {
        "ordering.before_phase": check.dependency.before.phase,
        "ordering.before_event": check.dependency.before.event,
        "ordering.after_phase": check.dependency.after.phase,
        "ordering.after_event": check.dependency.after.event,
        "ordering.severity": check.dependency.severity.value,
        "ordering.message": check.message,
    }

    if check.before_ts is not None:
        attrs["ordering.before_ts"] = check.before_ts
    if check.after_ts is not None:
        attrs["ordering.after_ts"] = check.after_ts

    logger.warning(
        "Ordering violation: %s.%s -> %s.%s [%s] %s",
        check.dependency.before.phase,
        check.dependency.before.event,
        check.dependency.after.phase,
        check.dependency.after.event,
        check.dependency.severity.value,
        check.message,
    )

    _add_span_event("causal.ordering.violation", attrs)
