"""
OTel span event emission helpers for regression prevention — Layer 7.

Follows the ``_add_span_event()`` pattern from ``propagation/otel.py``.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.regression.otel import (
        emit_drift_report,
        emit_gate_result,
        emit_gate_check,
    )

    emit_drift_report(drift_report)
    emit_gate_result(gate_result)
    for check in gate_result.failures:
        emit_gate_check(check)
"""

from __future__ import annotations

import logging

from contextcore.contracts.regression.drift import DriftReport
from contextcore.contracts.regression.gate import GateCheck, GateResult

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


def emit_drift_report(report: DriftReport) -> None:
    """Emit a span event summarising contract drift detection.

    Event name: ``context.regression.drift``
    """
    attrs: dict[str, str | int | float | bool] = {
        "regression.drift.total_changes": report.total_changes,
        "regression.drift.breaking_count": report.breaking_count,
        "regression.drift.non_breaking_count": report.non_breaking_count,
        "regression.drift.has_breaking": report.has_breaking_changes,
        "regression.drift.old_pipeline_id": report.old_pipeline_id,
        "regression.drift.new_pipeline_id": report.new_pipeline_id,
    }

    if report.has_breaking_changes:
        logger.warning(
            "Contract drift: %d breaking changes between '%s' and '%s'",
            report.breaking_count,
            report.old_pipeline_id,
            report.new_pipeline_id,
        )
    elif report.total_changes > 0:
        logger.info(
            "Contract drift: %d non-breaking changes between '%s' and '%s'",
            report.total_changes,
            report.old_pipeline_id,
            report.new_pipeline_id,
        )

    _add_span_event("context.regression.drift", attrs)


def emit_gate_result(result: GateResult) -> None:
    """Emit a span event summarising the regression gate result.

    Event name: ``context.regression.gate``
    """
    attrs: dict[str, str | int | float | bool] = {
        "regression.gate.passed": result.passed,
        "regression.gate.total_checks": result.total_checks,
        "regression.gate.failed_checks": result.failed_checks,
    }

    if not result.passed:
        logger.warning(
            "Regression gate FAILED: %d/%d checks failed",
            result.failed_checks,
            result.total_checks,
        )
    else:
        logger.info(
            "Regression gate passed: %d checks OK",
            result.total_checks,
        )

    _add_span_event("context.regression.gate", attrs)


def emit_gate_check(check: GateCheck) -> None:
    """Emit a span event for a single gate check.

    Event name: ``context.regression.gate_check``
    """
    attrs: dict[str, str | int | float | bool] = {
        "regression.gate.check_id": check.check_id,
        "regression.gate.check_passed": check.passed,
        "regression.gate.check_message": check.message,
    }
    if check.baseline_value is not None:
        attrs["regression.gate.baseline_value"] = check.baseline_value
    if check.current_value is not None:
        attrs["regression.gate.current_value"] = check.current_value

    if not check.passed:
        logger.warning(
            "Gate check FAILED [%s]: %s",
            check.check_id,
            check.message,
        )

    _add_span_event("context.regression.gate_check", attrs)
