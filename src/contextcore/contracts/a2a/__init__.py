"""
A2A (Agent-to-Agent) contract models, validation, and enforcement.

This sub-package provides:
- Pydantic v2 models matching the JSON schemas in ``schemas/contracts/``
- JSON schema validation helpers with a standard error envelope
- Boundary enforcement (outbound/inbound handoff validation)
- Phase gate library with ``GateResult`` emission and blocking semantics

Usage:
    from contextcore.contracts.a2a import (
        # Models
        TaskSpanContract,
        HandoffContract,
        ArtifactIntent,
        GateResult,
        # Validation
        A2AValidator,
        ValidationError as A2AValidationError,
        # Boundary enforcement
        validate_outbound,
        validate_inbound,
        # Gates
        GateChecker,
        check_checksum_chain,
        check_mapping_completeness,
        check_gap_parity,
    )
"""

from contextcore.contracts.a2a.models import (
    TaskSpanContract,
    HandoffContract,
    ArtifactIntent,
    GateResult,
    Phase,
    SpanStatus,
    HandoffPriority,
    HandoffContractStatus,
    ArtifactIntentAction,
    PromotionReason,
    GateSeverity,
    GateOutcome,
)
from contextcore.contracts.a2a.validator import (
    A2AValidator,
    ValidationErrorEnvelope,
    validate_payload,
)
from contextcore.contracts.a2a.boundary import (
    validate_outbound,
    validate_inbound,
    BoundaryEnforcementError,
)
from contextcore.contracts.a2a.gates import (
    GateChecker,
    check_checksum_chain,
    check_mapping_completeness,
    check_gap_parity,
)
from contextcore.contracts.a2a.pilot import (
    PilotRunner,
    PilotSeed,
    PilotResult,
)
from contextcore.contracts.a2a.pipeline_checker import (
    PipelineChecker,
    PipelineCheckReport,
)
from contextcore.contracts.a2a.three_questions import (
    ThreeQuestionsDiagnostic,
    DiagnosticResult,
    QuestionStatus,
)
from contextcore.contracts.a2a.content_verification import (
    ContentVerifier,
    scan_placeholders,
    verify_schema_fields,
    verify_import_consistency,
    verify_protocol_coherence,
)
from contextcore.contracts.a2a.queries import A2AQueries

__all__ = [
    # Models
    "TaskSpanContract",
    "HandoffContract",
    "ArtifactIntent",
    "GateResult",
    "Phase",
    "SpanStatus",
    "HandoffPriority",
    "HandoffContractStatus",
    "ArtifactIntentAction",
    "PromotionReason",
    "GateSeverity",
    "GateOutcome",
    # Validation
    "A2AValidator",
    "ValidationErrorEnvelope",
    "validate_payload",
    # Boundary enforcement
    "validate_outbound",
    "validate_inbound",
    "BoundaryEnforcementError",
    # Gates
    "GateChecker",
    "check_checksum_chain",
    "check_mapping_completeness",
    "check_gap_parity",
    # Pilot
    "PilotRunner",
    "PilotSeed",
    "PilotResult",
    # Pipeline checker
    "PipelineChecker",
    "PipelineCheckReport",
    # Three Questions diagnostic
    "ThreeQuestionsDiagnostic",
    "DiagnosticResult",
    "QuestionStatus",
    # Content verification (Gate 3)
    "ContentVerifier",
    "scan_placeholders",
    "verify_schema_fields",
    "verify_import_consistency",
    "verify_protocol_coherence",
    # Queries
    "A2AQueries",
]
