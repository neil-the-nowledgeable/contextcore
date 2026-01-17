"""
Pydantic models for Skill Capability management.

These models define the schema for storing skill capabilities as OTel spans,
following the same patterns as ProjectContext and InsightEmitter.

Integrates with:
- Agent attribution (agent.id, agent.session_id)
- Insight system (discovery insights on queries)
- Handoff protocol (capability_id linking)
- Evidence model (unified with insights)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SkillType(str, Enum):
    """Skill classification by purpose."""
    UTILITY = "utility"           # General-purpose tools (llm-formatter, pdf)
    ORCHESTRATION = "orchestration"  # Coordinate other skills (ios-project-manager)
    SPECIALIST = "specialist"     # Domain expertise (o11y, database-administrator)
    AUTOMATION = "automation"     # Automated workflows (auto-fix, CI/CD)


class CapabilityCategory(str, Enum):
    """Capability classification by operation type."""
    TRANSFORM = "transform"   # Convert between formats
    GENERATE = "generate"     # Create new artifacts
    VALIDATE = "validate"     # Check correctness
    AUDIT = "audit"           # Analyze efficiency/quality
    QUERY = "query"           # Retrieve information
    ACTION = "action"         # Execute operations
    ANALYZE = "analyze"       # Deep investigation


class Audience(str, Enum):
    """Intended consumer of the capability (mirrors InsightAudience)."""
    AGENT = "agent"     # Optimized for machine consumption
    HUMAN = "human"     # Optimized for human readability
    BOTH = "both"       # Works for both audiences


class EvidenceType(str, Enum):
    """Type of evidence reference (unified with insight evidence)."""
    # File-based evidence
    FILE = "file"             # Path to file with full content
    SCHEMA = "schema"         # JSON/YAML schema definition
    TEMPLATE = "template"     # Invocation template
    PROTOCOL = "protocol"     # Protocol specification
    # Reference-based evidence (from insights)
    TRACE = "trace"           # Tempo trace ID
    LOG_QUERY = "log_query"   # Loki query
    METRIC_QUERY = "metric_query"  # PromQL query
    COMMIT = "commit"         # Git commit SHA
    PR = "pr"                 # Pull request reference
    ADR = "adr"               # Architecture Decision Record
    DOC = "doc"               # Documentation URL
    TASK = "task"             # Task/issue reference
    CAPABILITY = "capability" # Reference to another capability
    EXAMPLE = "example"       # Usage example


class Evidence(BaseModel):
    """
    Supporting data reference (unified with insight Evidence).

    Follows the summary+evidence pattern: spans contain compressed summaries,
    evidence links to full content that can be loaded on demand.

    Unified fields from both CapabilityEvidence and insight.Evidence:
    - type, ref, description: Common to both
    - query: From insights (e.g., TraceQL query that found this)
    - timestamp: From insights (when evidence was collected)
    - tokens: From capabilities (token cost of referenced content)
    """
    type: str = Field(..., description="Evidence type (see EvidenceType enum)")
    ref: str = Field(..., description="Reference identifier, path, or URL")
    description: Optional[str] = Field(None, description="Brief explanation")
    query: Optional[str] = Field(None, description="Query that produced this evidence")
    timestamp: Optional[datetime] = Field(None, description="When evidence was collected")
    tokens: Optional[int] = Field(None, description="Token cost of referenced content")


# Keep CapabilityEvidence as alias for backwards compatibility
CapabilityEvidence = Evidence


class CapabilityInput(BaseModel):
    """
    Input parameter schema for a capability.

    Follows JSON Schema-style definitions for agent parsing.
    """
    name: str = Field(..., description="Parameter name")
    type: str = Field(..., description="Type: string | integer | number | boolean | array | object | enum")
    required: bool = Field(default=False, description="Whether parameter is required")
    default: Optional[str] = Field(None, description="Default value")
    enum_values: Optional[List[str]] = Field(None, description="Allowed values for enum type")
    description: str = Field(..., description="Parameter description")
    items_type: Optional[str] = Field(None, description="Type of array items")


class CapabilityOutput(BaseModel):
    """
    Output schema for a capability.
    """
    name: str = Field(..., description="Output field name")
    type: str = Field(..., description="Output type")
    description: str = Field(..., description="Field description")


def derive_audience(interop_human: int, interop_agent: int) -> Audience:
    """
    Derive audience enum from interoperability scores.

    Rules:
    - interop_agent >= 4 and interop_human < 3 → agent
    - interop_human >= 4 and interop_agent < 3 → human
    - both >= 3 → both
    """
    if interop_agent >= 4 and interop_human < 3:
        return Audience.AGENT
    elif interop_human >= 4 and interop_agent < 3:
        return Audience.HUMAN
    else:
        return Audience.BOTH


class SkillCapability(BaseModel):
    """
    A skill capability stored as an OTel span.

    Capabilities are child spans of skill manifests, enabling:
    - TraceQL queries for capability discovery
    - Token-efficient agent-to-agent communication
    - Progressive disclosure (summary first, evidence on demand)
    - Integration with handoff protocol (capability_id linking)
    - Lifecycle tracking (invoked, succeeded, failed events)

    Example:
        capability = SkillCapability(
            skill_id="llm-formatter",
            capability_id="transform_document",
            capability_name="Transform Document",
            category=CapabilityCategory.TRANSFORM,
            summary="Converts prose to progressive-disclosure format. Applies 10 formatting patterns.",
            triggers=["convert", "format", "transform", "prose_to_yaml"],
            token_budget=400,
            confidence=0.95,
            evidence=[
                Evidence(type="schema", ref="agent/capabilities/transform.yaml", tokens=400),
                Evidence(type="template", ref="templates/capability-schema.yaml", tokens=300),
            ],
        )
    """

    # Skill Identity
    skill_id: str = Field(..., description="Parent skill identifier")
    skill_version: str = Field(default="2.0", description="Skill schema version")
    skill_type: Optional[SkillType] = Field(None, description="Skill classification")

    # Capability Identity
    capability_id: str = Field(..., description="Unique capability identifier (snake_case)")
    capability_name: str = Field(..., description="Human-readable name")
    category: CapabilityCategory = Field(..., description="Operation category")

    # Routing
    triggers: List[str] = Field(
        default_factory=list,
        description="Keywords for routing table (TraceQL queries)"
    )

    # Summary + Evidence Pattern
    summary: str = Field(
        ...,
        max_length=500,
        description="1-2 sentence compressed description"
    )
    evidence: List[Evidence] = Field(
        default_factory=list,
        description="References to full content"
    )

    # Token Budget
    token_budget: int = Field(
        ...,
        description="Estimated token cost of full capability content"
    )
    summary_tokens: int = Field(
        default=50,
        description="Token cost of summary only"
    )

    # Schema
    inputs: List[CapabilityInput] = Field(
        default_factory=list,
        description="Input parameters"
    )
    outputs: List[CapabilityOutput] = Field(
        default_factory=list,
        description="Output schema"
    )

    # Anti-Patterns
    anti_patterns: List[str] = Field(
        default_factory=list,
        description="What NOT to do"
    )

    # Interoperability Scores
    interop_human: int = Field(
        default=4,
        ge=1,
        le=5,
        description="Human readability score (1-5)"
    )
    interop_agent: int = Field(
        default=5,
        ge=1,
        le=5,
        description="Agent parseability score (1-5)"
    )

    # Audience (derived from interop scores, but can be set explicitly)
    audience: Optional[Audience] = Field(
        None,
        description="Intended consumer (derived from interop scores if not set)"
    )

    # Confidence and Reliability (mirrors insight.confidence)
    confidence: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0) based on documentation quality"
    )
    success_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Success rate from usage tracking (calculated)"
    )
    invocation_count: int = Field(
        default=0,
        description="Number of times this capability has been invoked"
    )

    # Timestamps (for staleness tracking)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When capability was first registered"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When capability was last updated"
    )
    expires_at: Optional[datetime] = Field(
        None,
        description="When capability becomes stale (optional)"
    )

    # Version Evolution (mirrors insight.supersedes)
    supersedes: Optional[str] = Field(
        None,
        description="ID of capability this replaces"
    )

    # Project Linkage
    project_refs: List[str] = Field(
        default_factory=list,
        description="Projects that use this capability"
    )

    def get_audience(self) -> Audience:
        """Get audience, deriving from scores if not explicitly set."""
        if self.audience:
            return self.audience
        return derive_audience(self.interop_human, self.interop_agent)

    class Config:
        use_enum_values = True


class QuickAction(BaseModel):
    """
    Pre-resolved common operation for fast access.

    Quick actions appear at the top of manifests, requiring
    minimal context to invoke (typically ~100 tokens).
    """
    name: str = Field(..., description="Action name (snake_case)")
    capability_id: str = Field(..., description="Target capability")
    description: str = Field(..., description="Brief description")
    default_inputs: Optional[dict[str, Any]] = Field(
        None,
        description="Pre-filled default inputs"
    )


class SkillManifest(BaseModel):
    """
    Skill manifest stored as a parent span.

    The manifest is the entry point for skill discovery,
    containing quick actions and capability references.
    Child spans contain individual capabilities.

    Example:
        manifest = SkillManifest(
            skill_id="llm-formatter",
            skill_type=SkillType.UTILITY,
            description="Format documents for optimal human-LLM interoperability",
            quick_actions=[
                QuickAction(name="format_skill", capability_id="transform_document"),
                QuickAction(name="check_format", capability_id="validate_format"),
            ],
            capability_refs=["transform_document", "generate_manifest", "validate_format", "audit_tokens"],
            manifest_tokens=150,
            total_tokens=1600,
        )
    """

    # Identity
    skill_id: str = Field(..., description="Unique skill identifier")
    skill_type: SkillType = Field(..., description="Skill classification")
    version: str = Field(default="2.0", description="Manifest schema version")
    description: str = Field(..., description="Brief skill description")

    # Quick Actions (Most common operations)
    quick_actions: List[QuickAction] = Field(
        default_factory=list,
        description="Pre-resolved common operations"
    )

    # Capability References (IDs only, not full content)
    capability_refs: List[str] = Field(
        default_factory=list,
        description="Capability IDs available in this skill"
    )

    # Constraints
    constraints: List[str] = Field(
        default_factory=list,
        description="Usage constraints or limitations"
    )

    # Token Budget
    manifest_tokens: int = Field(
        default=150,
        description="Token cost of manifest alone"
    )
    index_tokens: int = Field(
        default=200,
        description="Token cost of index"
    )
    total_tokens: int = Field(
        default=0,
        description="Sum of all capability tokens"
    )
    compressed_tokens: int = Field(
        default=0,
        description="Token cost after summary+evidence compression"
    )

    # Source Path (for parsing)
    source_path: Optional[str] = Field(
        None,
        description="Path to skill directory"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When skill was first registered"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When skill was last updated"
    )

    # Project Linkage
    project_refs: List[str] = Field(
        default_factory=list,
        description="Projects that use this skill"
    )

    class Config:
        use_enum_values = True
