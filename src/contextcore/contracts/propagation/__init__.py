"""
Context propagation contracts — Layer 1 of defense-in-depth.

Provides a contract system for declaring, validating, and tracking context
field propagation across workflow phase boundaries.  Treats context
propagation like a type system for workflow pipelines.

Public API::

    from contextcore.contracts.propagation import (
        # Schema models
        ContextContract,
        FieldSpec,
        PhaseContract,
        PropagationChainSpec,
        ChainEndpoint,
        # Loader
        ContractLoader,
        # Validator
        BoundaryValidator,
        ContractValidationResult,
        FieldValidationResult,
        # Tracker
        PropagationTracker,
        PropagationChainResult,
        FieldProvenance,
        # OTel helpers
        emit_boundary_result,
        emit_chain_result,
        emit_propagation_summary,
    )
"""

from contextcore.contracts.propagation.loader import ContractLoader
from contextcore.contracts.propagation.otel import (
    emit_boundary_result,
    emit_chain_result,
    emit_propagation_summary,
)
from contextcore.contracts.propagation.schema import (
    ChainEndpoint,
    ContextContract,
    FieldSpec,
    PhaseContract,
    PhaseEntryContract,
    PhaseExitContract,
    PropagationChainSpec,
)
from contextcore.contracts.propagation.tracker import (
    FieldProvenance,
    PropagationChainResult,
    PropagationTracker,
)
from contextcore.contracts.propagation.validator import (
    BoundaryValidator,
    ContractValidationResult,
    FieldValidationResult,
)

__all__ = [
    # Schema
    "ContextContract",
    "FieldSpec",
    "PhaseContract",
    "PhaseEntryContract",
    "PhaseExitContract",
    "PropagationChainSpec",
    "ChainEndpoint",
    # Loader
    "ContractLoader",
    # Validator
    "BoundaryValidator",
    "ContractValidationResult",
    "FieldValidationResult",
    # Tracker
    "PropagationTracker",
    "PropagationChainResult",
    "FieldProvenance",
    # OTel
    "emit_boundary_result",
    "emit_chain_result",
    "emit_propagation_summary",
]
