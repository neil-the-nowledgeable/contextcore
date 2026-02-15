"""
OTel span event emission helpers for pre-flight verification.

Follows the ``_add_span_event()`` pattern from ``propagation/otel.py``.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.preflight.otel import (
        emit_preflight_result,
        emit_preflight_violation,
    )

    emit_preflight_result(result)
    for v in result.critical_violations:
        emit_preflight_violation(v)
"""

from __future__ import annotations

import logging

from contextcore.contracts.preflight.checker import (
    PreflightResult,
    PreflightViolation,
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


def emit_preflight_result(result: PreflightResult) -> None:
    """Emit a span event summarising the pre-flight verification.

    Event name: ``context.preflight.result``
    """
    critical = len(result.critical_violations)
    warning = len(result.warnings)
    advisory = len(result.advisories)

    attrs: dict[str, str | int | float | bool] = {
        "preflight.passed": result.passed,
        "preflight.phases_checked": result.phases_checked,
        "preflight.fields_checked": result.fields_checked,
        "preflight.critical_count": critical,
        "preflight.warning_count": warning,
        "preflight.advisory_count": advisory,
        "preflight.graph_issues": len(result.phase_graph_issues),
    }

    if result.passed:
        logger.debug(
            "Pre-flight passed: phases=%d fields=%d warnings=%d",
            result.phases_checked,
            result.fields_checked,
            warning,
        )
    else:
        logger.warning(
            "Pre-flight FAILED: critical=%d warning=%d advisory=%d",
            critical,
            warning,
            advisory,
        )

    _add_span_event("context.preflight.result", attrs)


def emit_preflight_violation(violation: PreflightViolation) -> None:
    """Emit a span event for a single pre-flight violation.

    Event name: ``context.preflight.violation``
    """
    attrs: dict[str, str | int | float | bool] = {
        "preflight.check_type": violation.check_type,
        "preflight.phase": violation.phase,
        "preflight.field": violation.field or "",
        "preflight.severity": violation.severity.value,
        "preflight.message": violation.message,
    }

    log_fn = (
        logger.warning
        if violation.severity == "blocking"
        else logger.info
    )
    log_fn(
        "Pre-flight violation: [%s] %s — %s",
        violation.severity.value,
        violation.check_type,
        violation.message,
    )

    _add_span_event("context.preflight.violation", attrs)
