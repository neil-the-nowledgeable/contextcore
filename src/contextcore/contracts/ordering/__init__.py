"""
Causal ordering contracts — Layer 4 of defense-in-depth.

Detects when events arrive in wrong order within pipeline phases.
Uses Lamport logical clocks to track happens-before relationships
and validates event sequences against declared dependency contracts.

Public API::

    from contextcore.contracts.ordering import (
        # Schema models
        CausalEndpoint,
        CausalDependency,
        OrderingConstraintSpec,
        # Clock
        CausalClock,
        CausalProvenance,
        # Validator
        CausalValidator,
        OrderingCheckResult,
        OrderingValidationResult,
        # Loader
        OrderingLoader,
        # OTel helpers
        emit_ordering_result,
        emit_ordering_violation,
    )
"""

from contextcore.contracts.ordering.clock import (
    CausalClock,
    CausalProvenance,
)
from contextcore.contracts.ordering.loader import OrderingLoader
from contextcore.contracts.ordering.otel import (
    emit_ordering_result,
    emit_ordering_violation,
)
from contextcore.contracts.ordering.schema import (
    CausalDependency,
    CausalEndpoint,
    OrderingConstraintSpec,
)
from contextcore.contracts.ordering.validator import (
    CausalValidator,
    OrderingCheckResult,
    OrderingValidationResult,
)

__all__ = [
    # Schema
    "CausalEndpoint",
    "CausalDependency",
    "OrderingConstraintSpec",
    # Clock
    "CausalClock",
    "CausalProvenance",
    # Validator
    "CausalValidator",
    "OrderingCheckResult",
    "OrderingValidationResult",
    # Loader
    "OrderingLoader",
    # OTel
    "emit_ordering_result",
    "emit_ordering_violation",
]
