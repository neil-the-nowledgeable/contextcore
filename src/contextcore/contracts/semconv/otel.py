"""
OTel span event emission helpers for semantic convention validation.

Follows the ``_add_span_event()`` pattern from ``propagation/otel.py``.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.semconv.otel import (
        emit_convention_result,
        emit_alias_detected,
    )

    emit_convention_result(result)
    emit_alias_detected("svc_name", "service.name")
"""

from __future__ import annotations

import logging

from contextcore.contracts._otel_helpers import add_span_event
from contextcore.contracts.semconv.validator import ConventionValidationResult

logger = logging.getLogger(__name__)


def emit_convention_result(result: ConventionValidationResult) -> None:
    """Emit a span event summarising the convention validation.

    Event name: ``convention.validation.complete``
    """
    attrs: dict[str, str | int | float | bool] = {
        "convention.passed": result.passed,
        "convention.total_checked": result.total_checked,
        "convention.violations": result.violations,
        "convention.aliases_resolved": result.aliases_resolved,
    }

    if result.passed:
        logger.debug(
            "Convention validation passed: checked=%d aliases=%d",
            result.total_checked,
            result.aliases_resolved,
        )
    else:
        logger.warning(
            "Convention validation FAILED: checked=%d violations=%d aliases=%d",
            result.total_checked,
            result.violations,
            result.aliases_resolved,
        )

    add_span_event("convention.validation.complete", attrs)


def emit_alias_detected(original: str, canonical: str) -> None:
    """Emit a span event for a single alias resolution.

    Event name: ``convention.alias.detected``
    """
    attrs: dict[str, str | int | float | bool] = {
        "convention.original_name": original,
        "convention.canonical_name": canonical,
    }

    logger.info(
        "Convention alias detected: '%s' -> '%s'",
        original,
        canonical,
    )

    add_span_event("convention.alias.detected", attrs)
