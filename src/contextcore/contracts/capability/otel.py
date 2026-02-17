"""
OTel span event emission helpers for capability propagation.

Follows the ``_add_span_event()`` pattern from
``contracts/propagation/otel.py`` — log + optional OTel span event.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.capability.otel import (
        emit_capability_result,
        emit_capability_chain_result,
    )

    emit_capability_result(validation_result)
    emit_capability_chain_result(chain_result)
"""

from __future__ import annotations

import logging

from contextcore.contracts.capability.tracker import CapabilityChainResult
from contextcore.contracts.capability.validator import CapabilityValidationResult
from contextcore.contracts.types import CapabilityChainStatus

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


def emit_capability_result(result: CapabilityValidationResult) -> None:
    """Emit a span event for a capability validation result.

    Event name: ``capability.boundary.entry`` or ``capability.boundary.exit``.
    """
    event_name = f"capability.boundary.{result.direction}"

    attrs: dict[str, str | int | float | bool] = {
        "capability.phase": result.phase,
        "capability.direction": result.direction,
        "capability.passed": result.passed,
        "capability.missing_count": len(result.missing_capabilities),
        "capability.escalation_count": len(result.escalation_attempts),
    }

    # Include first 3 missing capability names for quick filtering
    for i, cap_name in enumerate(result.missing_capabilities[:3]):
        attrs[f"capability.missing.{i}"] = cap_name

    # Include first 3 escalation names
    for i, cap_name in enumerate(result.escalation_attempts[:3]):
        attrs[f"capability.escalation.{i}"] = cap_name

    if result.passed:
        logger.debug(
            "Capability boundary %s: phase=%s passed",
            result.direction,
            result.phase,
        )
    else:
        logger.warning(
            "Capability boundary %s FAILED: phase=%s missing=%s escalations=%s",
            result.direction,
            result.phase,
            result.missing_capabilities,
            result.escalation_attempts,
        )

    _add_span_event(event_name, attrs)


def emit_capability_chain_result(result: CapabilityChainResult) -> None:
    """Emit a span event for a capability chain check.

    Event name depends on status:
    - ``capability.chain.intact`` (INTACT)
    - ``capability.chain.attenuated`` (ATTENUATED)
    - ``capability.chain.escalation_blocked`` (ESCALATION_BLOCKED)
    - ``capability.chain.broken`` (BROKEN)
    """
    status_to_event = {
        CapabilityChainStatus.INTACT: "capability.chain.intact",
        CapabilityChainStatus.ATTENUATED: "capability.chain.attenuated",
        CapabilityChainStatus.ESCALATION_BLOCKED: "capability.chain.escalation_blocked",
        CapabilityChainStatus.BROKEN: "capability.chain.broken",
    }
    event_name = status_to_event[result.status]

    attrs: dict[str, str | int | float | bool] = {
        "capability.chain_id": result.chain_id,
        "capability.chain_status": result.status.value,
        "capability.source_present": result.source_present,
        "capability.destination_present": result.destination_present,
        "capability.message": result.message,
    }

    if result.status not in (CapabilityChainStatus.INTACT, CapabilityChainStatus.ATTENUATED):
        logger.warning(
            "Capability chain %s: %s — %s",
            result.chain_id,
            result.status.value,
            result.message,
        )
    else:
        logger.debug(
            "Capability chain %s: %s",
            result.chain_id,
            result.status.value,
        )

    _add_span_event(event_name, attrs)
