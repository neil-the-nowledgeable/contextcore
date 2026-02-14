"""
Pydantic v2 models for A2A contract schemas.

Each model mirrors its corresponding JSON schema in ``schemas/contracts/``.
All models enforce ``schema_version = "v1"`` and reject unknown top-level fields
(``model_config = ConfigDict(extra="forbid")``).

The JSON schemas remain the normative definition; these models provide
Python-native construction, serialization, and in-process validation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared enums (aligned with JSON schema enum constraints)
# ---------------------------------------------------------------------------


class Phase(str, Enum):
    """Execution phases used by TaskSpanContract and GateResult."""

    INIT_BASELINE = "INIT_BASELINE"
    EXPORT_CONTRACT = "EXPORT_CONTRACT"
    CONTRACT_INTEGRITY = "CONTRACT_INTEGRITY"
    INGEST_PARSE_ASSESS = "INGEST_PARSE_ASSESS"
    ROUTING_DECISION = "ROUTING_DECISION"
    ARTISAN_DESIGN = "ARTISAN_DESIGN"
    ARTISAN_IMPLEMENT = "ARTISAN_IMPLEMENT"
    TEST_VALIDATE = "TEST_VALIDATE"
    REVIEW_CALIBRATE = "REVIEW_CALIBRATE"
    FINALIZE_VERIFY = "FINALIZE_VERIFY"
    OTHER = "OTHER"


class SpanStatus(str, Enum):
    """Status values for a task span."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class HandoffPriority(str, Enum):
    """Priority levels for a handoff."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class HandoffContractStatus(str, Enum):
    """Lifecycle status of a handoff contract."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ArtifactIntentAction(str, Enum):
    """Intent action for an artifact."""

    CREATE = "create"
    UPDATE = "update"
    VALIDATE = "validate"
    DEPRECATE = "deprecate"


class PromotionReason(str, Enum):
    """Reason for promoting an artifact requirement to a task."""

    LIFECYCLE = "lifecycle"
    DEPENDENCY = "dependency"
    RISK = "risk"
    OWNERSHIP = "ownership"
    TRACEABILITY = "traceability"
    NONE = "none"


class GateOutcome(str, Enum):
    """Result of a gate check."""

    PASS = "pass"
    FAIL = "fail"


class GateSeverity(str, Enum):
    """Severity level of a gate result."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Nested sub-models
# ---------------------------------------------------------------------------


class Checksums(BaseModel):
    """Checksum fields for provenance tracking."""

    model_config = ConfigDict(extra="forbid")

    source_checksum: Optional[str] = Field(None, min_length=1)
    artifact_manifest_checksum: Optional[str] = Field(None, min_length=1)
    project_context_checksum: Optional[str] = Field(None, min_length=1)


class SpanMetrics(BaseModel):
    """Quality/complexity counters attached to a task span."""

    model_config = ConfigDict(extra="forbid")

    gap_count: Optional[int] = Field(None, ge=0)
    feature_count: Optional[int] = Field(None, ge=0)
    complexity_score: Optional[float] = Field(None, ge=0, le=100)
    artifact_count: Optional[int] = Field(None, ge=0)


class ExpectedOutput(BaseModel):
    """Expected output descriptor for a handoff contract."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1)
    schema_ref: Optional[str] = Field(None, min_length=1)


class OutputConvention(BaseModel):
    """Output path/extension conventions for an artifact intent."""

    model_config = ConfigDict(extra="forbid")

    output_path: Optional[str] = Field(None, min_length=1)
    output_ext: Optional[str] = Field(None, min_length=1)


class EvidenceItem(BaseModel):
    """A single piece of evidence attached to a gate result."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1)
    ref: str = Field(..., min_length=1)
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level contract models
# ---------------------------------------------------------------------------

_V1 = "v1"


class TaskSpanContract(BaseModel):
    """
    Typed contract for a task/subtask represented as a trace span.

    Mirrors ``schemas/contracts/task-span-contract.schema.json``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(_V1, pattern=r"^v1$")
    project_id: str = Field(..., min_length=1)
    trace_id: Optional[str] = Field(None, min_length=1)
    span_id: Optional[str] = Field(None, min_length=1)
    task_id: str = Field(..., min_length=1)
    parent_task_id: Optional[str] = Field(None, min_length=1)
    phase: Phase
    status: SpanStatus
    acceptance_criteria: Optional[list[str]] = None
    checksums: Optional[Checksums] = None
    metrics: Optional[SpanMetrics] = None
    blocked_reason: Optional[str] = Field(None, min_length=1)
    blocked_on_span_id: Optional[str] = Field(None, min_length=1)
    next_action: Optional[str] = Field(None, min_length=1)
    timestamp: Optional[datetime] = None


class HandoffContract(BaseModel):
    """
    Typed contract for agent-to-agent delegation.

    Mirrors ``schemas/contracts/handoff-contract.schema.json``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(_V1, pattern=r"^v1$")
    handoff_id: str = Field(..., min_length=1)
    project_id: Optional[str] = Field(None, min_length=1)
    trace_id: Optional[str] = Field(None, min_length=1)
    parent_task_id: Optional[str] = Field(None, min_length=1)
    from_agent: str = Field(..., min_length=1)
    to_agent: str = Field(..., min_length=1)
    capability_id: str = Field(..., min_length=1)
    priority: HandoffPriority = HandoffPriority.NORMAL
    inputs: dict[str, Any] = Field(...)
    expected_output: ExpectedOutput
    status: HandoffContractStatus = HandoffContractStatus.PENDING
    result_trace_id: Optional[str] = Field(None, min_length=1)
    error: Optional[str] = Field(None, min_length=1)
    created_at: Optional[datetime] = None
    deadline: Optional[datetime] = None


class ArtifactIntent(BaseModel):
    """
    Typed declaration of an artifact requirement before generation.

    Mirrors ``schemas/contracts/artifact-intent.schema.json``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(_V1, pattern=r"^v1$")
    artifact_id: str = Field(..., min_length=1)
    artifact_type: str = Field(..., min_length=1)
    intent: ArtifactIntentAction
    owner: str = Field(..., min_length=1)
    task_id: Optional[str] = Field(None, min_length=1)
    promoted_to_task: bool = False
    promotion_reason: PromotionReason = PromotionReason.NONE
    parameter_sources: dict[str, Any] = Field(..., min_length=1)
    output_convention: Optional[OutputConvention] = None
    semantic_conventions: Optional[dict[str, Any]] = None
    acceptance_criteria: Optional[list[str]] = None


class GateResult(BaseModel):
    """
    Typed outcome for a quality/integrity gate between workflow phases.

    Mirrors ``schemas/contracts/gate-result.schema.json``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(_V1, pattern=r"^v1$")
    gate_id: str = Field(..., min_length=1)
    trace_id: Optional[str] = Field(None, min_length=1)
    task_id: Optional[str] = Field(None, min_length=1)
    phase: Phase
    result: GateOutcome
    severity: GateSeverity
    reason: Optional[str] = Field(None, min_length=1)
    next_action: Optional[str] = Field(None, min_length=1)
    blocking: bool = False
    evidence: Optional[list[EvidenceItem]] = None
    checked_at: datetime


# ---------------------------------------------------------------------------
# Contract type registry (for validator dispatch)
# ---------------------------------------------------------------------------

CONTRACT_TYPES = {
    "TaskSpanContract": TaskSpanContract,
    "HandoffContract": HandoffContract,
    "ArtifactIntent": ArtifactIntent,
    "GateResult": GateResult,
}

SCHEMA_FILES = {
    "TaskSpanContract": "task-span-contract.schema.json",
    "HandoffContract": "handoff-contract.schema.json",
    "ArtifactIntent": "artifact-intent.schema.json",
    "GateResult": "gate-result.schema.json",
}
