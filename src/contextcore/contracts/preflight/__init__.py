"""
Pre-flight verification — Layer 3 of defense-in-depth.

Validates an initial context dict and phase execution order against a
``ContextContract`` before any workflow phase runs.  Catches field
readiness issues, seed enrichment gaps, and phase graph problems that
would silently degrade quality at runtime.

Public API::

    from contextcore.contracts.preflight import (
        # Checker
        PreflightChecker,
        # Result models
        PreflightResult,
        PreflightViolation,
        FieldReadinessDetail,
        PhaseGraphIssue,
        # OTel helpers
        emit_preflight_result,
        emit_preflight_violation,
    )
"""

from contextcore.contracts.preflight.checker import (
    FieldReadinessDetail,
    PhaseGraphIssue,
    PreflightChecker,
    PreflightResult,
    PreflightViolation,
)
from contextcore.contracts.preflight.otel import (
    emit_preflight_result,
    emit_preflight_violation,
)

__all__ = [
    # Checker
    "PreflightChecker",
    # Result models
    "PreflightResult",
    "PreflightViolation",
    "FieldReadinessDetail",
    "PhaseGraphIssue",
    # OTel
    "emit_preflight_result",
    "emit_preflight_violation",
]
