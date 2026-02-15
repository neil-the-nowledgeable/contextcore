"""
OTel span event emission helpers for runtime boundary checks — Layer 4.

Follows the ``_add_span_event()`` pattern from ``propagation/otel.py``.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.runtime.otel import (
        emit_phase_boundary,
        emit_workflow_summary,
    )

    emit_phase_boundary(record)
    emit_workflow_summary(summary)
"""

from __future__ import annotations

import logging

from contextcore.contracts.runtime.guard import (
    PhaseExecutionRecord,
    WorkflowRunSummary,
)
from contextcore.contracts.types import PropagationStatus

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


def emit_phase_boundary(record: PhaseExecutionRecord) -> None:
    """Emit a span event summarising boundary checks for a single phase.

    Event name: ``context.runtime.phase_boundary``
    """
    entry_passed = record.entry_result.passed if record.entry_result else True
    exit_passed = record.exit_result.passed if record.exit_result else True
    entry_status = (
        record.entry_result.propagation_status.value
        if record.entry_result
        else PropagationStatus.PROPAGATED.value
    )
    exit_status = (
        record.exit_result.propagation_status.value
        if record.exit_result
        else PropagationStatus.PROPAGATED.value
    )

    entry_blocking = (
        len(record.entry_result.blocking_failures) if record.entry_result else 0
    )
    exit_blocking = (
        len(record.exit_result.blocking_failures) if record.exit_result else 0
    )
    entry_warnings = (
        len(record.entry_result.warnings) if record.entry_result else 0
    )
    exit_warnings = (
        len(record.exit_result.warnings) if record.exit_result else 0
    )

    attrs: dict[str, str | int | float | bool] = {
        "runtime.phase": record.phase,
        "runtime.passed": record.passed,
        "runtime.entry.passed": entry_passed,
        "runtime.entry.status": entry_status,
        "runtime.entry.blocking_count": entry_blocking,
        "runtime.entry.warning_count": entry_warnings,
        "runtime.exit.passed": exit_passed,
        "runtime.exit.status": exit_status,
        "runtime.exit.blocking_count": exit_blocking,
        "runtime.exit.warning_count": exit_warnings,
        "runtime.propagation_status": record.propagation_status.value,
    }

    if record.passed:
        logger.debug(
            "Phase boundary: phase=%s status=%s",
            record.phase,
            record.propagation_status.value,
        )
    else:
        logger.warning(
            "Phase boundary FAILED: phase=%s entry_blocking=%d exit_blocking=%d",
            record.phase,
            entry_blocking,
            exit_blocking,
        )

    _add_span_event("context.runtime.phase_boundary", attrs)


def emit_workflow_summary(summary: WorkflowRunSummary) -> None:
    """Emit a span event summarising the entire workflow run.

    Event name: ``context.runtime.workflow_summary``
    """
    attrs: dict[str, str | int | float | bool] = {
        "runtime.mode": summary.mode.value,
        "runtime.total_phases": summary.total_phases,
        "runtime.passed_phases": summary.passed_phases,
        "runtime.failed_phases": summary.failed_phases,
        "runtime.total_fields_checked": summary.total_fields_checked,
        "runtime.total_blocking_failures": summary.total_blocking_failures,
        "runtime.total_warnings": summary.total_warnings,
        "runtime.total_defaults_applied": summary.total_defaults_applied,
        "runtime.overall_passed": summary.overall_passed,
        "runtime.overall_status": summary.overall_status.value,
    }

    if summary.overall_passed:
        logger.info(
            "Workflow summary: %d/%d phases passed, mode=%s, status=%s",
            summary.passed_phases,
            summary.total_phases,
            summary.mode.value,
            summary.overall_status.value,
        )
    else:
        logger.warning(
            "Workflow summary FAILED: %d/%d phases failed, "
            "blocking=%d, mode=%s",
            summary.failed_phases,
            summary.total_phases,
            summary.total_blocking_failures,
            summary.mode.value,
        )

    _add_span_event("context.runtime.workflow_summary", attrs)
