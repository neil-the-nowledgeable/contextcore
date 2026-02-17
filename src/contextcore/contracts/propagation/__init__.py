"""
Context propagation contracts — Layer 1 of defense-in-depth.

Provides a contract system for declaring, validating, and tracking context
field propagation across workflow phase boundaries.  Treats context
propagation like a type system for workflow pipelines.

Public API::

    from contextcore.contracts.propagation import (
        # Schema models
        ContextContract,
        EvaluationSpec,
        FieldSpec,
        PhaseContract,
        PropagationChainSpec,
        ChainEndpoint,
        QualitySpec,
        # Loader
        ContractLoader,
        # Validator
        BoundaryValidator,
        ContractValidationResult,
        FieldValidationResult,
        QualityViolation,
        # Tracker
        EvaluationResult,
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
    EvaluationSpec,
    FieldSpec,
    PhaseContract,
    PhaseEntryContract,
    PhaseExitContract,
    PropagationChainSpec,
    QualitySpec,
)
from contextcore.contracts.propagation.tracker import (
    EvaluationResult,
    FieldProvenance,
    PropagationChainResult,
    PropagationTracker,
)
from contextcore.contracts.propagation.validator import (
    BoundaryValidator,
    ContractValidationResult,
    FieldValidationResult,
    QualityViolation,
)

__all__ = [
    # Schema
    "ContextContract",
    "EvaluationSpec",
    "FieldSpec",
    "PhaseContract",
    "PhaseEntryContract",
    "PhaseExitContract",
    "PropagationChainSpec",
    "ChainEndpoint",
    "QualitySpec",
    # Loader
    "ContractLoader",
    # Validator
    "BoundaryValidator",
    "ContractValidationResult",
    "FieldValidationResult",
    "QualityViolation",
    # Tracker
    "EvaluationResult",
    "PropagationTracker",
    "PropagationChainResult",
    "FieldProvenance",
    # OTel
    "emit_boundary_result",
    "emit_chain_result",
    "emit_propagation_summary",
]
