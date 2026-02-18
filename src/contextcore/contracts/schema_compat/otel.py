"""
OTel span event emission helpers for schema compatibility checks.

Follows the ``add_span_event()`` pattern from ``propagation/otel.py``.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.schema_compat.otel import (
        emit_compatibility_check,
        emit_compatibility_drift,
        emit_compatibility_breaking,
    )

    emit_compatibility_check(result)
    emit_compatibility_drift(result, "task.status", "unmapped_value", "...")
    emit_compatibility_breaking(evolution_result, change)
"""

from __future__ import annotations

import logging

from contextcore.contracts._otel_helpers import add_span_event
from contextcore.contracts.schema_compat.schema import (
    CompatibilityResult,
    EvolutionCheckResult,
)

logger = logging.getLogger(__name__)


def emit_compatibility_check(result: CompatibilityResult) -> None:
    """Emit a span event for a compatibility check result.

    Event name: ``schema.compatibility.check``
    """
    attrs: dict[str, str | int | float | bool] = {
        "schema.source_service": result.source_service,
        "schema.target_service": result.target_service,
        "schema.level": result.level.value,
        "schema.compatible": result.compatible,
        "schema.fields_checked": len(result.field_results),
        "schema.drift_count": len(result.drift_details),
        "schema.message": result.message,
    }

    if result.compatible:
        logger.debug(
            "Schema compat check: %s -> %s level=%s compatible=True",
            result.source_service,
            result.target_service,
            result.level.value,
        )
    else:
        logger.warning(
            "Schema compat check FAILED: %s -> %s level=%s drifts=%d",
            result.source_service,
            result.target_service,
            result.level.value,
            len(result.drift_details),
        )

    add_span_event("schema.compatibility.check", attrs)


def emit_compatibility_drift(
    result: CompatibilityResult,
    drift_field: str,
    drift_type: str,
    drift_detail: str,
) -> None:
    """Emit a span event for a specific compatibility drift.

    Event name: ``schema.compatibility.drift``
    """
    attrs: dict[str, str | int | float | bool] = {
        "schema.source_service": result.source_service,
        "schema.target_service": result.target_service,
        "schema.drift_type": drift_type,
        "schema.drift_field": drift_field,
        "schema.drift_detail": drift_detail,
        "schema.severity": result.severity.value,
    }

    logger.warning(
        "Schema drift: %s -> %s field=%s type=%s",
        result.source_service,
        result.target_service,
        drift_field,
        drift_type,
    )

    add_span_event("schema.compatibility.drift", attrs)


def emit_compatibility_breaking(
    result: EvolutionCheckResult,
    change: dict[str, str],
) -> None:
    """Emit a span event for a breaking schema evolution change.

    Event name: ``schema.compatibility.breaking``
    """
    attrs: dict[str, str | int | float | bool] = {
        "schema.service": result.service,
        "schema.old_version": result.old_version,
        "schema.new_version": result.new_version,
        "schema.change_type": change.get("type", ""),
        "schema.change_field": change.get("field", ""),
        "schema.policy": result.applicable_rule or "",
        "schema.message": result.message,
    }

    logger.warning(
        "Breaking schema change: service=%s %s -> %s change=%s field=%s",
        result.service,
        result.old_version,
        result.new_version,
        change.get("type", ""),
        change.get("field", ""),
    )

    add_span_event("schema.compatibility.breaking", attrs)
