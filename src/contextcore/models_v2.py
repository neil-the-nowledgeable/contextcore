"""
Pydantic models for ProjectContext CRD v2 agent sections.

These models provide Python type safety and validation for the agent-related
sections of the ProjectContext v2 CRD:
- agentGuidance: Human-to-agent direction
- agentSessions: Agent session tracking
- agentInsights: Agent insight summaries
- handoffQueue: Agent-to-agent handoffs
- personalization: Audience-specific presentation

Usage:
    from contextcore.models_v2 import AgentGuidanceSpec, AgentSessionSpec

    guidance = AgentGuidanceSpec(
        focus=FocusSpec(areas=["performance", "security"]),
        constraints=[ConstraintSpec(id="no-auth", rule="No auth changes")],
    )
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from contextcore.contracts.types import (
    AgentType,
    ConstraintSeverity,
    HandoffStatus,
    InsightType,
    Priority,
    QuestionStatus,
    SessionStatus,
)


# =============================================================================
# Agent Guidance Models (agentGuidance section)
# =============================================================================


class FocusSpec(BaseModel):
    """Current priority areas for agent attention."""

    areas: List[str] = Field(
        default_factory=list,
        description="Priority focus areas (e.g., 'performance optimization')",
    )
    reason: Optional[str] = Field(None, description="Why these areas are prioritized")
    until: Optional[datetime] = Field(None, description="When this focus expires")

    model_config = {"populate_by_name": True}


class ConstraintSpec(BaseModel):
    """What agents must NOT do."""

    id: str = Field(..., description="Constraint identifier")
    rule: str = Field(..., description="The constraint (e.g., 'no breaking API changes')")
    scope: Optional[str] = Field(None, description="Scope pattern (e.g., 'src/auth/**')")
    severity: ConstraintSeverity = Field(
        default=ConstraintSeverity.BLOCKING,
        description="Constraint severity level",
    )
    reason: Optional[str] = Field(None, description="Why this constraint exists")

    model_config = {"populate_by_name": True}


class PreferenceSpec(BaseModel):
    """Preferred approaches (not mandatory)."""

    id: Optional[str] = Field(None, description="Preference identifier")
    preference: Optional[str] = Field(None, description="The preferred approach")
    reason: Optional[str] = Field(None, description="Why this is preferred")

    model_config = {"populate_by_name": True}


class QuestionSpec(BaseModel):
    """Questions for agents to answer."""

    id: str = Field(..., description="Question identifier")
    question: str = Field(..., description="The question text")
    priority: Priority = Field(
        default=Priority.MEDIUM,
        description="Question priority",
    )
    context: Optional[str] = Field(None, description="Additional context")
    status: QuestionStatus = Field(
        default=QuestionStatus.OPEN,
        description="Question status",
    )

    model_config = {"populate_by_name": True}


class ContextItemSpec(BaseModel):
    """Background information for agents."""

    topic: Optional[str] = Field(None, description="Context topic")
    content: Optional[str] = Field(None, description="Context content")
    source: Optional[str] = Field(None, description="Source URL")

    model_config = {"populate_by_name": True}


class AgentGuidanceSpec(BaseModel):
    """
    Human-to-agent guidance specification.

    Persists across agent sessions to provide consistent direction.
    """

    focus: Optional[FocusSpec] = Field(
        None,
        description="Current priority areas for agent attention",
    )
    constraints: List[ConstraintSpec] = Field(
        default_factory=list,
        description="What agents must NOT do",
    )
    preferences: List[PreferenceSpec] = Field(
        default_factory=list,
        description="Preferred approaches (not mandatory)",
    )
    questions: List[QuestionSpec] = Field(
        default_factory=list,
        description="Questions for agents to answer",
    )
    context: List[ContextItemSpec] = Field(
        default_factory=list,
        description="Background information for agents",
    )

    model_config = {"populate_by_name": True}

    def get_blocking_constraints(self) -> List[ConstraintSpec]:
        """Return only blocking constraints."""
        return [c for c in self.constraints if c.severity == ConstraintSeverity.BLOCKING]

    def get_open_questions(self) -> List[QuestionSpec]:
        """Return only open questions."""
        return [q for q in self.questions if q.status == QuestionStatus.OPEN]

    def get_critical_questions(self) -> List[QuestionSpec]:
        """Return critical priority questions."""
        return [q for q in self.questions if q.priority == Priority.CRITICAL]


# =============================================================================
# Agent Session Models (agentSessions section)
# =============================================================================


class AgentSessionSpec(BaseModel):
    """Agent session tracking."""

    session_id: str = Field(..., alias="sessionId", description="Unique session identifier")
    agent_id: str = Field(..., alias="agentId", description="Agent identifier")
    agent_type: AgentType = Field(
        default=AgentType.CODE_ASSISTANT,
        alias="agentType",
        description="Agent type classification",
    )
    started_at: datetime = Field(..., alias="startedAt", description="Session start time")
    ended_at: Optional[datetime] = Field(
        None,
        alias="endedAt",
        description="Session end time",
    )
    status: SessionStatus = Field(
        default=SessionStatus.ACTIVE,
        description="Session status",
    )
    capabilities_used: List[str] = Field(
        default_factory=list,
        alias="capabilitiesUsed",
        description="Capabilities used in session",
    )
    insight_count: int = Field(
        default=0,
        alias="insightCount",
        description="Number of insights generated",
    )
    tasks_completed: List[str] = Field(
        default_factory=list,
        alias="tasksCompleted",
        description="Task IDs completed in this session",
    )

    model_config = {"populate_by_name": True}

    def is_active(self) -> bool:
        """Check if session is currently active."""
        return self.status == SessionStatus.ACTIVE


# =============================================================================
# Agent Insights Models (agentInsights section)
# =============================================================================


class InsightSummarySpec(BaseModel):
    """Summary of a high-confidence insight."""

    id: str = Field(..., description="Insight identifier")
    type: InsightType = Field(..., description="Insight type")
    summary: str = Field(..., description="Insight summary")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    timestamp: datetime = Field(..., description="When insight was generated")
    trace_id: Optional[str] = Field(
        None,
        alias="traceId",
        description="Tempo trace ID for full insight",
    )

    model_config = {"populate_by_name": True}


class UnresolvedBlockerSpec(BaseModel):
    """Blocker needing human attention."""

    id: str = Field(..., description="Blocker identifier")
    summary: str = Field(..., description="Blocker summary")
    created_at: datetime = Field(..., alias="createdAt", description="When blocker was created")
    trace_id: Optional[str] = Field(
        None,
        alias="traceId",
        description="Tempo trace ID",
    )

    model_config = {"populate_by_name": True}


class InsightsByTypeSpec(BaseModel):
    """Count of insights by type."""

    decisions: int = Field(default=0)
    recommendations: int = Field(default=0)
    blockers: int = Field(default=0)
    discoveries: int = Field(default=0)

    model_config = {"populate_by_name": True}

    def total(self) -> int:
        """Return total insight count."""
        return self.decisions + self.recommendations + self.blockers + self.discoveries


class AgentInsightsSpec(BaseModel):
    """
    Summary of agent insights.

    Full detail is queryable via TraceQL in Tempo.
    """

    last_updated: Optional[datetime] = Field(
        None,
        alias="lastUpdated",
        description="When insights were last updated",
    )
    total_count: int = Field(
        default=0,
        alias="totalCount",
        description="Total insight count",
    )
    by_type: InsightsByTypeSpec = Field(
        default_factory=InsightsByTypeSpec,
        alias="byType",
        description="Insights by type",
    )
    recent_high_confidence: List[InsightSummarySpec] = Field(
        default_factory=list,
        alias="recentHighConfidence",
        description="Recent insights with confidence > 0.9",
    )
    unresolved_blockers: List[UnresolvedBlockerSpec] = Field(
        default_factory=list,
        alias="unresolvedBlockers",
        description="Blockers needing human attention",
    )

    model_config = {"populate_by_name": True}

    def has_unresolved_blockers(self) -> bool:
        """Check if there are unresolved blockers."""
        return len(self.unresolved_blockers) > 0


# =============================================================================
# Handoff Queue Models (handoffQueue section)
# =============================================================================


class HandoffSpec(BaseModel):
    """Agent-to-agent task delegation."""

    id: str = Field(..., description="Handoff identifier")
    from_agent: str = Field(..., alias="fromAgent", description="Delegating agent")
    to_agent: str = Field(..., alias="toAgent", description="Receiving agent")
    capability_id: str = Field(
        ...,
        alias="capabilityId",
        description="Required capability",
    )
    task: str = Field(..., description="Task description")
    priority: Priority = Field(
        default=Priority.MEDIUM,
        description="Handoff priority",
    )
    status: HandoffStatus = Field(
        default=HandoffStatus.PENDING,
        description="Handoff status",
    )
    created_at: Optional[datetime] = Field(
        None,
        alias="createdAt",
        description="When handoff was created",
    )
    timeout_ms: int = Field(
        default=300000,
        alias="timeoutMs",
        description="Timeout in milliseconds",
    )
    result_trace_id: Optional[str] = Field(
        None,
        alias="resultTraceId",
        description="Trace ID containing handoff result",
    )

    model_config = {"populate_by_name": True}

    def is_pending(self) -> bool:
        """Check if handoff is still pending."""
        return self.status in [HandoffStatus.PENDING, HandoffStatus.ACCEPTED, HandoffStatus.IN_PROGRESS]

    def is_complete(self) -> bool:
        """Check if handoff is finished (success or failure)."""
        return self.status in [HandoffStatus.COMPLETED, HandoffStatus.FAILED, HandoffStatus.TIMEOUT]


# =============================================================================
# Personalization Models (personalization section)
# =============================================================================


class AlertThreshold(str):
    """Alert threshold levels for executives."""

    CRITICAL_ONLY = "critical_only"
    CRITICAL_HIGH = "critical_high"
    ALL = "all"


class PreferredFormat(str):
    """Preferred detail format for developers."""

    DETAILED = "detailed"
    STANDARD = "standard"
    MINIMAL = "minimal"


class QueryBackend(str):
    """Preferred query backend for agents."""

    TEMPO = "tempo"
    LOKI = "loki"
    K8S_API = "k8s_api"


class ExecutivePersonalizationSpec(BaseModel):
    """Personalization for executive audience."""

    dashboard_id: Optional[str] = Field(None, alias="dashboardId")
    summary_fields: List[str] = Field(default_factory=list, alias="summaryFields")
    alert_threshold: Optional[str] = Field(None, alias="alertThreshold")

    model_config = {"populate_by_name": True}


class ManagerPersonalizationSpec(BaseModel):
    """Personalization for manager audience."""

    dashboard_id: Optional[str] = Field(None, alias="dashboardId")
    reporting_cadence: Optional[str] = Field(None, alias="reportingCadence")

    model_config = {"populate_by_name": True}


class DeveloperPersonalizationSpec(BaseModel):
    """Personalization for developer audience."""

    dashboard_id: Optional[str] = Field(None, alias="dashboardId")
    preferred_format: Optional[str] = Field(None, alias="preferredFormat")

    model_config = {"populate_by_name": True}


class AgentPersonalizationSpec(BaseModel):
    """Personalization for agent audience."""

    preferred_query_backend: Optional[str] = Field(None, alias="preferredQueryBackend")
    max_context_tokens: Optional[int] = Field(
        None,
        alias="maxContextTokens",
        description="Token budget hint for agents",
    )

    model_config = {"populate_by_name": True}


class PersonalizationSpec(BaseModel):
    """
    Audience-specific presentation hints.

    Different audiences see different views of the same data.
    """

    executive: Optional[ExecutivePersonalizationSpec] = None
    manager: Optional[ManagerPersonalizationSpec] = None
    developer: Optional[DeveloperPersonalizationSpec] = None
    agent: Optional[AgentPersonalizationSpec] = None

    model_config = {"populate_by_name": True}


# =============================================================================
# Combined Agent Status (for CRD status section)
# =============================================================================


class AgentStatusSpec(BaseModel):
    """Agent communication status in CRD status section."""

    active_sessions: int = Field(default=0, alias="activeSessions")
    last_session_ended_at: Optional[datetime] = Field(None, alias="lastSessionEndedAt")
    pending_handoffs: int = Field(default=0, alias="pendingHandoffs")
    unresolved_blockers: int = Field(default=0, alias="unresolvedBlockers")
    insights_last_24h: int = Field(default=0, alias="insightsLast24h")

    model_config = {"populate_by_name": True}
