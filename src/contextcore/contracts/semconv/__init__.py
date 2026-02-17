"""
Semantic convention contracts --- Layer 3 of defense-in-depth.

Enforces canonical attribute naming across services.  Detects when
non-canonical names, unknown values, or conflicting aliases are used.

Public API::

    from contextcore.contracts.semconv import (
        # Schema models
        ConventionContract,
        AttributeConvention,
        EnumConvention,
        # Loader
        ConventionLoader,
        # Validator + result models
        ConventionValidator,
        AttributeValidationResult,
        ConventionValidationResult,
        # OTel helpers
        emit_convention_result,
        emit_alias_detected,
    )
"""

from contextcore.contracts.semconv.loader import ConventionLoader
from contextcore.contracts.semconv.otel import (
    emit_alias_detected,
    emit_convention_result,
)
from contextcore.contracts.semconv.schema import (
    AttributeConvention,
    ConventionContract,
    EnumConvention,
)
from contextcore.contracts.semconv.validator import (
    AttributeValidationResult,
    ConventionValidationResult,
    ConventionValidator,
)

__all__ = [
    # Schema
    "ConventionContract",
    "AttributeConvention",
    "EnumConvention",
    # Loader
    "ConventionLoader",
    # Validator
    "ConventionValidator",
    "AttributeValidationResult",
    "ConventionValidationResult",
    # OTel
    "emit_convention_result",
    "emit_alias_detected",
]
