"""
Schema evolution contracts — Layer 2 of defense-in-depth.

Provides cross-service schema compatibility checking: declares field
mappings, validates value translations, and tracks schema evolution
over time.

Public API::

    from contextcore.contracts.schema_compat import (
        # Schema models
        SchemaCompatibilitySpec,
        FieldMapping,
        SchemaEvolutionRule,
        SchemaVersion,
        CompatibilityResult,
        FieldCompatibilityDetail,
        EvolutionCheckResult,
        # Loader
        SchemaCompatLoader,
        # Checker
        CompatibilityChecker,
        # Evolution
        EvolutionTracker,
        # OTel helpers
        emit_compatibility_check,
        emit_compatibility_drift,
        emit_compatibility_breaking,
    )
"""

from contextcore.contracts.schema_compat.checker import CompatibilityChecker
from contextcore.contracts.schema_compat.evolution import EvolutionTracker
from contextcore.contracts.schema_compat.loader import SchemaCompatLoader
from contextcore.contracts.schema_compat.otel import (
    emit_compatibility_breaking,
    emit_compatibility_check,
    emit_compatibility_drift,
)
from contextcore.contracts.schema_compat.schema import (
    CompatibilityResult,
    EvolutionCheckResult,
    FieldCompatibilityDetail,
    FieldMapping,
    SchemaCompatibilitySpec,
    SchemaEvolutionRule,
    SchemaVersion,
)

__all__ = [
    # Schema
    "SchemaCompatibilitySpec",
    "FieldMapping",
    "SchemaEvolutionRule",
    "SchemaVersion",
    "CompatibilityResult",
    "FieldCompatibilityDetail",
    "EvolutionCheckResult",
    # Loader
    "SchemaCompatLoader",
    # Checker
    "CompatibilityChecker",
    # Evolution
    "EvolutionTracker",
    # OTel
    "emit_compatibility_check",
    "emit_compatibility_drift",
    "emit_compatibility_breaking",
]
