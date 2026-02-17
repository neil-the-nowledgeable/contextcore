"""
OTel span event emission helpers for data lineage tracking.

Follows the ``_add_span_event()`` pattern from ``propagation/otel.py``.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.lineage.otel import (
        emit_transformation,
        emit_audit_result,
        emit_audit_summary,
    )

    emit_transformation("domain", record)
    emit_audit_result(audit_result)
    emit_audit_summary(audit_summary)
"""

from __future__ import annotations

import logging

from contextcore.contracts.lineage.auditor import LineageAuditResult, LineageAuditSummary
from contextcore.contracts.lineage.tracker import TransformationRecord
from contextcore.contracts.types import LineageStatus

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


def emit_transformation(field: str, record: TransformationRecord) -> None:
    """Emit a span event when a transformation is recorded.

    Event name: ``lineage.stage.recorded``
    """
    attrs: dict[str, str | int | float | bool] = {
        "lineage.field": field,
        "lineage.phase": record.phase,
        "lineage.operation": record.operation.value,
        "lineage.input_hash": record.input_hash,
        "lineage.output_hash": record.output_hash,
        "lineage.timestamp": record.timestamp,
    }

    logger.debug(
        "Lineage stage recorded: field=%s phase=%s op=%s",
        field,
        record.phase,
        record.operation.value,
    )

    _add_span_event("lineage.stage.recorded", attrs)


def emit_audit_result(result: LineageAuditResult) -> None:
    """Emit a span event for a lineage chain audit result.

    Event name: ``lineage.chain.{status}`` where status is the
    ``LineageStatus`` value (verified, mutation_detected, chain_broken,
    incomplete).
    """
    event_name = f"lineage.chain.{result.status.value}"

    attrs: dict[str, str | int | float | bool] = {
        "lineage.chain_id": result.chain_id,
        "lineage.status": result.status.value,
        "lineage.expected_stages": result.expected_stages,
        "lineage.actual_stages": result.actual_stages,
        "lineage.broken_links": len(result.broken_links),
        "lineage.mutations": len(result.mutations),
        "lineage.message": result.message,
    }

    if result.status != LineageStatus.VERIFIED:
        logger.warning(
            "Lineage chain %s: %s — %s",
            result.chain_id,
            result.status.value,
            result.message,
        )
    else:
        logger.debug("Lineage chain %s: verified", result.chain_id)

    _add_span_event(event_name, attrs)


def emit_audit_summary(result: LineageAuditSummary) -> None:
    """Emit a summary span event for all lineage chain audits.

    Event name: ``lineage.audit.complete``
    """
    completeness_pct = round(
        result.verified_count / max(result.total_chains, 1) * 100, 1
    )

    attrs: dict[str, str | int | float | bool] = {
        "lineage.total_chains": result.total_chains,
        "lineage.verified_count": result.verified_count,
        "lineage.broken_count": result.broken_count,
        "lineage.passed": result.passed,
        "lineage.completeness_pct": completeness_pct,
    }

    log_fn = logger.info if result.passed else logger.warning
    log_fn(
        "Lineage audit complete: %d/%d verified (%.1f%%), %d broken",
        result.verified_count,
        result.total_chains,
        completeness_pct,
        result.broken_count,
    )

    _add_span_event("lineage.audit.complete", attrs)
