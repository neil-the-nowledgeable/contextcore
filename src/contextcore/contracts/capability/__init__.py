"""
Capability propagation contracts — Layer 5 of defense-in-depth.

Provides a contract system for declaring, validating, and tracking
capability propagation across workflow phase boundaries.  Enforces
the attenuation invariant: capabilities can only narrow, never widen.

Public API::

    from contextcore.contracts.capability import (
        # Schema models
        AttenuationSpec,
        CapabilityChainSpec,
        CapabilityContract,
        CapabilityDefinition,
        PhaseCapabilityContract,
        # Loader
        CapabilityLoader,
        # Validator
        CapabilityValidator,
        CapabilityValidationResult,
        # Tracker
        CapabilityTracker,
        CapabilityChainResult,
        CapabilityProvenance,
        # OTel helpers
        emit_capability_result,
        emit_capability_chain_result,
    )
"""

from contextcore.contracts.capability.loader import CapabilityLoader
from contextcore.contracts.capability.otel import (
    emit_capability_chain_result,
    emit_capability_result,
)
from contextcore.contracts.capability.schema import (
    AttenuationSpec,
    CapabilityChainSpec,
    CapabilityContract,
    CapabilityDefinition,
    PhaseCapabilityContract,
)
from contextcore.contracts.capability.tracker import (
    CapabilityChainResult,
    CapabilityProvenance,
    CapabilityTracker,
)
from contextcore.contracts.capability.validator import (
    CapabilityValidationResult,
    CapabilityValidator,
)

__all__ = [
    # Schema
    "AttenuationSpec",
    "CapabilityChainSpec",
    "CapabilityContract",
    "CapabilityDefinition",
    "PhaseCapabilityContract",
    # Loader
    "CapabilityLoader",
    # Validator
    "CapabilityValidator",
    "CapabilityValidationResult",
    # Tracker
    "CapabilityTracker",
    "CapabilityChainResult",
    "CapabilityProvenance",
    # OTel
    "emit_capability_result",
    "emit_capability_chain_result",
]
