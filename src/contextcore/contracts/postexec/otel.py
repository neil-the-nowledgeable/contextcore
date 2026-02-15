"""
OTel span event emission helpers for post-execution validation — Layer 5.

Follows the ``_add_span_event()`` pattern from ``propagation/otel.py``.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.postexec.otel import (
        emit_postexec_report,
        emit_postexec_discrepancy,
    )

    emit_postexec_report(report)
    for d in report.runtime_discrepancies:
        emit_postexec_discrepancy(d)
"""

from __future__ import annotations

import logging

from contextcore.contracts.postexec.validator import (
    PostExecutionReport,
    RuntimeDiscrepancy,
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


def emit_postexec_report(report: PostExecutionReport) -> None:
    """Emit a span event summarising the post-execution validation.

    Event name: ``context.postexec.report``
    """
    attrs: dict[str, str | int | float | bool] = {
        "postexec.passed": report.passed,
        "postexec.chains_total": report.chains_total,
        "postexec.chains_intact": report.chains_intact,
        "postexec.chains_degraded": report.chains_degraded,
        "postexec.chains_broken": report.chains_broken,
        "postexec.completeness_pct": report.completeness_pct,
        "postexec.discrepancy_count": len(report.runtime_discrepancies),
    }

    if report.final_exit_result is not None:
        attrs["postexec.final_exit_passed"] = report.final_exit_result.passed

    if report.passed:
        logger.info(
            "Post-execution passed: chains=%d/%d intact (%.1f%%), "
            "discrepancies=%d",
            report.chains_intact,
            report.chains_total,
            report.completeness_pct,
            len(report.runtime_discrepancies),
        )
    else:
        logger.warning(
            "Post-execution FAILED: chains=%d/%d intact, "
            "broken=%d, discrepancies=%d",
            report.chains_intact,
            report.chains_total,
            report.chains_broken,
            len(report.runtime_discrepancies),
        )

    _add_span_event("context.postexec.report", attrs)


def emit_postexec_discrepancy(discrepancy: RuntimeDiscrepancy) -> None:
    """Emit a span event for a single runtime discrepancy.

    Event name: ``context.postexec.discrepancy``
    """
    attrs: dict[str, str | int | float | bool] = {
        "postexec.phase": discrepancy.phase,
        "postexec.discrepancy_type": discrepancy.discrepancy_type,
        "postexec.message": discrepancy.message,
    }

    log_fn = (
        logger.warning
        if discrepancy.discrepancy_type == "late_corruption"
        else logger.info
    )
    log_fn(
        "Post-execution discrepancy: [%s] phase=%s — %s",
        discrepancy.discrepancy_type,
        discrepancy.phase,
        discrepancy.message,
    )

    _add_span_event("context.postexec.discrepancy", attrs)
