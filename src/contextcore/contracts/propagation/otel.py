"""
OTel span event emission helpers for context propagation.

Log + optional OTel span event via the shared ``add_span_event()`` helper.
All functions degrade gracefully when OTel is not installed.

Usage::

    from contextcore.contracts.propagation.otel import (
        emit_boundary_result,
        emit_chain_result,
        emit_propagation_summary,
    )

    emit_boundary_result(validation_result)
    emit_chain_result(chain_result)
    emit_propagation_summary(chain_results)
"""

from __future__ import annotations

import logging

from contextcore.contracts._otel_helpers import add_span_event
from contextcore.contracts.propagation.tracker import PropagationChainResult
from contextcore.contracts.propagation.validator import ContractValidationResult
from contextcore.contracts.types import ChainStatus, PropagationStatus

logger = logging.getLogger(__name__)


def emit_boundary_result(result: ContractValidationResult) -> None:
    """Emit a span event for a boundary validation result.

    Event name: ``context.boundary.entry`` or ``context.boundary.exit``
    (or ``context.boundary.enrichment``).
    """
    event_name = f"context.boundary.{result.direction}"

    attrs: dict[str, str | int | float | bool] = {
        "context.phase": result.phase,
        "context.direction": result.direction,
        "context.passed": result.passed,
        "context.propagation_status": result.propagation_status.value,
        "context.blocking_count": len(result.blocking_failures),
        "context.warning_count": len(result.warnings),
    }

    # Include first 3 blocking field names for quick filtering
    for i, field_name in enumerate(result.blocking_failures[:3]):
        attrs[f"context.blocking.{i}"] = field_name

    if result.passed:
        logger.debug(
            "Boundary %s: phase=%s status=%s",
            result.direction,
            result.phase,
            result.propagation_status.value,
        )
    else:
        logger.warning(
            "Boundary %s FAILED: phase=%s blocking=%s",
            result.direction,
            result.phase,
            result.blocking_failures,
        )

    add_span_event(event_name, attrs)


def emit_chain_result(result: PropagationChainResult) -> None:
    """Emit a span event for a propagation chain check.

    Event name depends on status:
    - ``context.chain.validated`` (INTACT)
    - ``context.chain.degraded`` (DEGRADED)
    - ``context.chain.broken`` (BROKEN)
    """
    status_to_event = {
        ChainStatus.INTACT: "context.chain.validated",
        ChainStatus.DEGRADED: "context.chain.degraded",
        ChainStatus.BROKEN: "context.chain.broken",
    }
    event_name = status_to_event[result.status]

    attrs: dict[str, str | int | float | bool] = {
        "context.chain_id": result.chain_id,
        "context.chain_status": result.status.value,
        "context.source_present": result.source_present,
        "context.destination_present": result.destination_present,
        "context.message": result.message,
    }

    if result.status != ChainStatus.INTACT:
        logger.warning(
            "Chain %s: %s — %s",
            result.chain_id,
            result.status.value,
            result.message,
        )
    else:
        logger.debug("Chain %s: intact", result.chain_id)

    add_span_event(event_name, attrs)


def emit_propagation_summary(results: list[PropagationChainResult]) -> None:
    """Emit a summary span event for all propagation chains.

    Event name: ``context.propagation_summary``
    """
    total = len(results)
    intact = sum(1 for r in results if r.status == ChainStatus.INTACT)
    degraded = sum(1 for r in results if r.status == ChainStatus.DEGRADED)
    broken = sum(1 for r in results if r.status == ChainStatus.BROKEN)
    completeness_pct = round(intact / max(total, 1) * 100, 1)

    attrs: dict[str, str | int | float | bool] = {
        "context.total_chains": total,
        "context.intact": intact,
        "context.degraded": degraded,
        "context.broken": broken,
        "context.completeness_pct": completeness_pct,
    }

    log_fn = logger.info if broken == 0 else logger.warning
    log_fn(
        "Propagation summary: %d/%d intact (%.1f%%), %d degraded, %d broken",
        intact,
        total,
        completeness_pct,
        degraded,
        broken,
    )

    add_span_event("context.propagation_summary", attrs)
