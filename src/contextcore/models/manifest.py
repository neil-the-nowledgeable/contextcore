"""
Context Manifest Models (v1.1).

This module defines the schema for the "Context Manifest" (.contextcore.yaml),
which serves as the comprehensive source of truth for a project's business context,
strategies, and objectives.

This is a SUPERSET of the Kubernetes ProjectContext CRD.
- The CRD is for the cluster (operational policy).
- This Manifest is for the business (strategy, tactics, objectives).

Schema Improvements (v1.1):
- Added apiVersion, kind, metadata for K8s-like structure
- Added TacticStatus enum (aligned with TaskStatus)
- Added lifecycle fields to Tactic (dates, blocked_reason, progress)
- Added ID pattern validation (OBJ-, STRAT-, TAC-)
- Added structured KeyResult model for objectives
- Enhanced Insight model (id, severity, expiry, evidence)
- Added ArtifactReference model for artifact linkage
- Added Owner structured model
- Added cross-reference validation
- Added ManifestMetadata with changelog
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from contextcore.contracts.types import Priority
from contextcore.models.core import ProjectContextSpec


# =============================================================================
# ID PATTERNS (for cross-reference validation)
# =============================================================================

OBJECTIVE_ID_PATTERN = re.compile(r"^OBJ-[A-Z0-9-]+$")
STRATEGY_ID_PATTERN = re.compile(r"^STRAT-[A-Z0-9-]+$")
TACTIC_ID_PATTERN = re.compile(r"^TAC-[A-Z0-9-]+$")
INSIGHT_ID_PATTERN = re.compile(r"^INS-[A-Z0-9-]+$")


# =============================================================================
# ENUMS
# =============================================================================


class StrategicHorizon(str, Enum):
    """Time horizon for a strategy."""

    NOW = "now"  # Current focus (this quarter)
    NEXT = "next"  # Next up (next quarter)
    LATER = "later"  # Long term (12mo+)


class TacticStatus(str, Enum):
    """
    Execution status for tactics.

    Aligned with TaskStatus semantics for consistency across ContextCore.
    """

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELLED = "cancelled"

    @classmethod
    def active_statuses(cls) -> list["TacticStatus"]:
        """Return statuses that indicate active work."""
        return [cls.PLANNED, cls.IN_PROGRESS, cls.IN_REVIEW, cls.BLOCKED]

    @classmethod
    def terminal_statuses(cls) -> list["TacticStatus"]:
        """Return statuses that indicate work is finished."""
        return [cls.DONE, cls.CANCELLED]


class InsightSeverity(str, Enum):
    """Severity levels for insights (aligned with Priority)."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ArtifactType(str, Enum):
    """Types of external artifacts that can be linked."""

    ISSUE = "issue"
    PR = "pr"
    COMMIT = "commit"
    DEPLOYMENT = "deployment"
    DASHBOARD = "dashboard"
    RUNBOOK = "runbook"
    ADR = "adr"
    DOC = "doc"


class MetricUnit(str, Enum):
    """Valid units for metrics."""

    PERCENT = "%"
    MILLISECONDS = "ms"
    SECONDS = "s"
    RPS = "rps"
    RPM = "rpm"
    COUNT = "count"
    RATIO = "ratio"


class TargetOperator(str, Enum):
    """
    Comparison operator for metric targets.

    Clarifies whether a target is a minimum (gte), maximum (lte), or exact (eq).
    This removes ambiguity: availability targets are "≥", latency targets are "≤".
    """

    GTE = "gte"  # Greater than or equal (e.g., availability >= 99.9%)
    LTE = "lte"  # Less than or equal (e.g., latency <= 200ms)
    EQ = "eq"    # Exactly equal (e.g., error count == 0)


# =============================================================================
# SUPPORTING MODELS
# =============================================================================


class Owner(BaseModel):
    """Structured ownership information."""

    team: str = Field(..., description="Owning team name")
    slack: Optional[str] = Field(None, description="Slack channel (e.g., #checkout-dev)")
    email: Optional[str] = Field(None, description="Team email")
    oncall: Optional[str] = Field(None, description="On-call rotation reference")


class ChangelogEntry(BaseModel):
    """A single changelog entry for manifest evolution tracking."""

    date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    version: str = Field(..., description="Manifest version at this change")
    actor: Optional[str] = Field(None, description="Who made the change (human:name or agent:id)")
    summary: str = Field(..., description="Brief description of changes")


class ManifestMetadata(BaseModel):
    """Metadata for the Context Manifest (K8s-like structure)."""

    name: str = Field(..., description="Manifest/project name")
    owners: List[Owner] = Field(default_factory=list, description="Ownership information")
    changelog: List[ChangelogEntry] = Field(
        default_factory=list, description="Change history"
    )
    last_updated: Optional[datetime] = Field(
        None, alias="lastUpdated", description="Last modification timestamp"
    )
    links: Dict[str, str] = Field(
        default_factory=dict,
        description="Related links (e.g., repo, wiki, dashboard)",
    )

    model_config = ConfigDict(populate_by_name=True)


class ArtifactReference(BaseModel):
    """Reference to an external artifact (PR, issue, deployment, etc.)."""

    type: ArtifactType = Field(..., description="Artifact type")
    id: str = Field(..., description="Artifact identifier (e.g., 'PROJ-123', 'pr-456')")
    url: Optional[HttpUrl] = Field(None, description="Canonical URL to artifact")
    title: Optional[str] = Field(None, description="Human-readable title")


class Evidence(BaseModel):
    """Evidence supporting an insight."""

    type: str = Field(..., description="Evidence type (file, url, query, metric)")
    ref: str = Field(..., description="Reference (file path, URL, query string)")
    description: Optional[str] = Field(None, description="What this evidence shows")


class KeyResult(BaseModel):
    """
    Structured key result metric.

    Replaces free-form metric/target strings for machine-actionable metrics.

    The `operator` field clarifies target direction:
    - `gte`: Target is a minimum (e.g., availability >= 99.9%)
    - `lte`: Target is a maximum (e.g., latency <= 200ms)
    - `eq`: Target is exact (e.g., error count == 0)

    If omitted, the operator is inferred from metric_key (availability → gte, latency → lte).
    """

    metric_key: str = Field(
        ...,
        alias="metricKey",
        description="Canonical metric key (e.g., 'availability', 'latency.p99')",
    )
    unit: MetricUnit = Field(..., description="Metric unit")
    target: float = Field(..., description="Target value")
    operator: Optional[TargetOperator] = Field(
        None,
        alias="targetOperator",
        description="Comparison operator: 'gte' (≥), 'lte' (≤), or 'eq' (==). Inferred if omitted.",
    )
    baseline: Optional[float] = Field(None, description="Current/baseline value")
    window: Optional[str] = Field(None, description="Time window (e.g., '30d', '7d')")
    data_source: Optional[str] = Field(
        None,
        alias="dataSource",
        description="Query reference (PromQL, TraceQL, Grafana panel ID)",
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_metric_unit_consistency(self) -> "KeyResult":
        """Validate that metric key and unit are consistent."""
        # Availability should use percent
        if self.metric_key == "availability" and self.unit != MetricUnit.PERCENT:
            raise ValueError(
                f"Metric 'availability' should use '%' unit, got '{self.unit.value}'"
            )
        # Latency should use time units
        if self.metric_key.startswith("latency.") and self.unit not in (
            MetricUnit.MILLISECONDS,
            MetricUnit.SECONDS,
        ):
            raise ValueError(
                f"Latency metric should use 'ms' or 's', got '{self.unit.value}'"
            )
        return self

    def get_operator(self) -> TargetOperator:
        """
        Get the effective operator, inferring from metric_key if not explicitly set.

        Default inference rules:
        - availability, uptime, success_rate → gte (higher is better)
        - latency, duration, response_time → lte (lower is better)
        - error, failure → lte (lower is better)
        - All others → gte (assume higher is better)
        """
        if self.operator is not None:
            return self.operator

        key_lower = self.metric_key.lower()

        # Metrics where lower is better
        if any(
            pattern in key_lower
            for pattern in ("latency", "duration", "response_time", "error", "failure")
        ):
            return TargetOperator.LTE

        # Default: higher is better
        return TargetOperator.GTE

    def evaluate(self, actual: float) -> bool:
        """
        Evaluate whether the actual value meets the target.

        Returns True if the target is met, False otherwise.
        """
        op = self.get_operator()
        if op == TargetOperator.GTE:
            return actual >= self.target
        elif op == TargetOperator.LTE:
            return actual <= self.target
        else:  # EQ
            return actual == self.target


# =============================================================================
# CORE MANIFEST MODELS
# =============================================================================


class Objective(BaseModel):
    """A high-level business objective (what we want to achieve)."""

    id: str = Field(..., description="Unique objective ID (e.g., OBJ-RELIABILITY)")
    description: str = Field(..., description="The objective statement")

    # Legacy support (deprecated, use key_results)
    metric: Optional[str] = Field(
        None, description="[DEPRECATED] Key Result metric - use key_results instead"
    )
    target: Optional[str] = Field(
        None, description="[DEPRECATED] Target value - use key_results instead"
    )

    # New structured approach
    key_results: List[KeyResult] = Field(
        default_factory=list,
        alias="keyResults",
        description="Structured key results with metrics",
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        """Enforce OBJ-* pattern for objective IDs."""
        if not OBJECTIVE_ID_PATTERN.match(v):
            raise ValueError(
                f"Objective ID must match pattern OBJ-*, got '{v}'. "
                f"Examples: OBJ-RELIABILITY, OBJ-1, OBJ-Q4-2024"
            )
        return v


class Tactic(BaseModel):
    """A specific action or initiative to execute a strategy."""

    id: str = Field(..., description="Unique tactic ID (e.g., TAC-KAFKA)")
    description: str = Field(..., description="What we are doing")

    # Status with enum (replacing free-form string)
    status: TacticStatus = Field(
        TacticStatus.PLANNED, description="Execution status"
    )
    owner: Optional[str] = Field(None, description="Who is responsible")

    # Lifecycle fields
    start_date: Optional[datetime] = Field(
        None, alias="startDate", description="When work started"
    )
    due_date: Optional[datetime] = Field(
        None, alias="dueDate", description="Target completion date"
    )
    completed_date: Optional[datetime] = Field(
        None, alias="completedDate", description="Actual completion date"
    )
    blocked_reason: Optional[str] = Field(
        None, alias="blockedReason", description="Why blocked (required if status=blocked)"
    )
    progress: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Completion percentage (0-100)"
    )

    # Artifact linkage
    artifacts: List[ArtifactReference] = Field(
        default_factory=list, description="Linked artifacts (PRs, issues, deployments)"
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        """Enforce TAC-* pattern for tactic IDs."""
        if not TACTIC_ID_PATTERN.match(v):
            raise ValueError(
                f"Tactic ID must match pattern TAC-*, got '{v}'. "
                f"Examples: TAC-QUEUE, TAC-KAFKA, TAC-1"
            )
        return v

    @model_validator(mode="after")
    def validate_blocked_reason_required(self) -> "Tactic":
        """Require blocked_reason when status is BLOCKED."""
        if self.status == TacticStatus.BLOCKED and not self.blocked_reason:
            raise ValueError(
                f"Tactic {self.id} has status=blocked but missing blocked_reason"
            )
        return self

    @model_validator(mode="after")
    def validate_lifecycle_dates(self) -> "Tactic":
        """Validate date ordering and status consistency."""
        if self.completed_date and self.start_date:
            if self.completed_date < self.start_date:
                raise ValueError(
                    f"Tactic {self.id}: completed_date cannot be before start_date"
                )
        if self.status == TacticStatus.DONE and not self.completed_date:
            # Warning: DONE without completed_date (could be a soft warning)
            pass  # Allow for now, can be stricter later
        return self


class Strategy(BaseModel):
    """A strategic approach to achieving objectives."""

    id: str = Field(..., description="Strategy ID (e.g., STRAT-ASYNC)")
    horizon: StrategicHorizon = Field(
        StrategicHorizon.NOW, description="Time horizon"
    )
    description: str = Field(..., description="The strategic approach")
    rationale: str = Field(..., description="Why this strategy was chosen")
    tactics: List[Tactic] = Field(
        default_factory=list, description="Tactics implementing this strategy"
    )

    # Cross-references
    objective_refs: List[str] = Field(
        default_factory=list,
        alias="objectiveRefs",
        description="Objective IDs this strategy supports",
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        """Enforce STRAT-* pattern for strategy IDs."""
        if not STRATEGY_ID_PATTERN.match(v):
            raise ValueError(
                f"Strategy ID must match pattern STRAT-*, got '{v}'. "
                f"Examples: STRAT-ASYNC, STRAT-1"
            )
        return v


class Insight(BaseModel):
    """
    Derived knowledge or signal about the project.

    Enhanced with severity, expiry, and evidence for actionability.
    """

    # Optional ID (auto-generated if not provided)
    id: Optional[str] = Field(None, description="Insight ID (e.g., INS-001)")

    type: str = Field(
        ..., description="Type of insight (e.g., 'risk', 'pattern', 'opportunity')"
    )
    summary: str = Field(..., description="Summary of the insight")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    source: str = Field(
        ..., description="Source of this insight (e.g., 'scanner:dependency-check')"
    )

    # Enhanced fields
    severity: InsightSeverity = Field(
        InsightSeverity.MEDIUM, description="Severity/priority level"
    )
    observed_at: Optional[datetime] = Field(
        None, alias="observedAt", description="When the insight was observed"
    )
    expires_at: Optional[datetime] = Field(
        None, alias="expiresAt", description="When the insight becomes stale"
    )
    impact: Optional[str] = Field(None, description="Business/technical impact")
    evidence: List[Evidence] = Field(
        default_factory=list, description="Supporting evidence"
    )
    recommended_actions: List[str] = Field(
        default_factory=list,
        alias="recommendedActions",
        description="Suggested next steps",
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: Optional[str]) -> Optional[str]:
        """Enforce INS-* pattern if ID is provided."""
        if v and not INSIGHT_ID_PATTERN.match(v):
            raise ValueError(
                f"Insight ID must match pattern INS-*, got '{v}'. "
                f"Examples: INS-001, INS-DEP-RISK"
            )
        return v


# =============================================================================
# CONTEXT MANIFEST (ROOT MODEL)
# =============================================================================


class ContextManifest(BaseModel):
    """
    The Context Manifest (.contextcore.yaml).

    This is the portable source of truth that captures:
    1. Operational Context (spec) -> Maps to K8s CRD
    2. Strategic Context (objectives, strategies) -> Maps to PM tools / LLM Context
    3. Derived Context (insights) -> Maps to Knowledge Graph

    Schema v1.1 adds:
    - apiVersion/kind/metadata for K8s-like structure
    - Cross-reference validation
    - Structured metrics (KeyResult)
    - Lifecycle tracking for tactics
    - Artifact linkage
    """

    # K8s-like identifiers
    api_version: str = Field(
        "contextcore.io/v1alpha1",
        alias="apiVersion",
        description="API version for schema compatibility",
    )
    kind: str = Field("ContextManifest", description="Resource kind")

    # Metadata
    metadata: ManifestMetadata = Field(..., description="Manifest metadata")

    # Version (for backward compatibility, also in metadata.changelog)
    version: str = Field("1.1", description="Manifest schema version")

    # The operational spec (shared with K8s CRD)
    spec: ProjectContextSpec = Field(..., description="Operational specification")

    # Extended context (NOT in K8s CRD)
    objectives: List[Objective] = Field(
        default_factory=list, description="Business objectives"
    )
    strategies: List[Strategy] = Field(
        default_factory=list, description="Strategies and tactics"
    )
    insights: List[Insight] = Field(
        default_factory=list, description="Derived insights"
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_cross_references(self) -> "ContextManifest":
        """Validate that all referenced IDs exist."""
        errors: List[str] = []

        # Collect all valid IDs
        objective_ids: Set[str] = {obj.id for obj in self.objectives}
        strategy_ids: Set[str] = {strat.id for strat in self.strategies}
        tactic_ids: Set[str] = {
            tactic.id for strat in self.strategies for tactic in strat.tactics
        }

        # Validate strategy -> objective references
        for strat in self.strategies:
            for obj_ref in strat.objective_refs:
                if obj_ref not in objective_ids:
                    errors.append(
                        f"Strategy '{strat.id}' references unknown objective: '{obj_ref}'"
                    )

        # Validate risk -> strategy/tactic mitigation references
        if self.spec.risks:
            for risk in self.spec.risks:
                if risk.mitigation:
                    mitigation = risk.mitigation
                    # Check if it's a strategy or tactic ID
                    if mitigation.startswith("STRAT-"):
                        if mitigation not in strategy_ids:
                            errors.append(
                                f"Risk mitigation references unknown strategy: '{mitigation}'"
                            )
                    elif mitigation.startswith("TAC-"):
                        if mitigation not in tactic_ids:
                            errors.append(
                                f"Risk mitigation references unknown tactic: '{mitigation}'"
                            )

        if errors:
            raise ValueError(
                "Cross-reference validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        return self

    def distill_crd(
        self,
        *,
        namespace: str = "default",
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extract only the operational spec for Kubernetes CRD.

        Returns a dictionary suitable for K8s ProjectContext CRD YAML.
        """
        return {
            "apiVersion": "contextcore.io/v1",
            "kind": "ProjectContext",
            "metadata": {
                "name": name or self.metadata.name,
                "namespace": namespace,
            },
            "spec": self.spec.model_dump(by_alias=True, exclude_none=True),
        }

    def get_active_tactics(self) -> List[Tactic]:
        """Get all tactics with active statuses."""
        return [
            tactic
            for strat in self.strategies
            for tactic in strat.tactics
            if tactic.status in TacticStatus.active_statuses()
        ]

    def get_stale_insights(self, as_of: Optional[datetime] = None) -> List[Insight]:
        """Get insights that have expired."""
        check_time = as_of or datetime.now()
        return [
            insight
            for insight in self.insights
            if insight.expires_at and insight.expires_at < check_time
        ]


# =============================================================================
# BACKWARD COMPATIBILITY: Keep simple factory for v1.0 manifests
# =============================================================================


def create_manifest_v1(
    spec: ProjectContextSpec,
    objectives: Optional[List[Objective]] = None,
    strategies: Optional[List[Strategy]] = None,
    insights: Optional[List[Insight]] = None,
    name: str = "unnamed-project",
) -> ContextManifest:
    """
    Factory function for creating v1.0-style manifests.

    Provides backward compatibility for code that doesn't need full v1.1 features.
    """
    return ContextManifest(
        api_version="contextcore.io/v1alpha1",
        kind="ContextManifest",
        metadata=ManifestMetadata(name=name),
        version="1.0",
        spec=spec,
        objectives=objectives or [],
        strategies=strategies or [],
        insights=insights or [],
    )


# =============================================================================
# LOADING / BACKWARD-COMPATIBILITY HELPERS
# =============================================================================


def _looks_like_legacy_manifest(data: Dict[str, Any]) -> bool:
    """
    Heuristic: legacy manifests (v1.0) often omit apiVersion/kind/metadata and
    may have operational spec fields at the root.
    """
    if "metadata" in data or "apiVersion" in data or "kind" in data:
        return False
    # If it has strategy sections, it's likely intended as a manifest
    return any(k in data for k in ("spec", "objectives", "strategies", "insights", "version"))


def _extract_root_spec_if_present(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Support older docs/examples that placed ProjectContextSpec fields at the root:
      project/business/requirements/targets/observability/risks/design
    This keeps strategic sections (objectives/strategies/insights) at the root.
    """
    if "spec" in data:
        return data

    spec_keys = {"project", "design", "business", "requirements", "risks", "targets", "observability"}
    if not any(k in data for k in spec_keys):
        return data

    upgraded = dict(data)
    spec: Dict[str, Any] = {}
    for k in list(upgraded.keys()):
        if k in spec_keys:
            spec[k] = upgraded.pop(k)
    upgraded["spec"] = spec
    return upgraded


def _upgrade_legacy_manifest_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upgrade a legacy v1.0-style manifest dict to v1.1 shape in-memory by injecting:
    - apiVersion/kind
    - metadata.name (derived from spec.project.id when available)
    """
    upgraded = _extract_root_spec_if_present(data)
    upgraded = dict(upgraded)

    # Default identifiers
    upgraded.setdefault("apiVersion", "contextcore.io/v1alpha1")
    upgraded.setdefault("kind", "ContextManifest")

    # Create minimal metadata if missing
    if "metadata" not in upgraded or upgraded["metadata"] is None:
        name = "unnamed-project"
        spec = upgraded.get("spec") or {}
        project = spec.get("project") or {}
        if isinstance(project, dict):
            name = project.get("id") or name
        elif isinstance(project, str) and project.strip():
            name = project.strip()
        upgraded["metadata"] = {"name": name}

    return upgraded


def load_context_manifest(path: str | Path) -> ContextManifest:
    """
    Load a Context Manifest from YAML file with backward compatibility.

    - Accepts v1.1 manifests directly.
    - Upgrades v1.0-style manifests (missing apiVersion/kind/metadata) in-memory.
    - Supports legacy layouts where ProjectContextSpec fields were placed at the root.
    """
    p = Path(path).expanduser()
    raw = p.read_text(encoding="utf-8")
    # Local import to keep module import-time light
    import yaml

    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Manifest YAML must be a mapping/object, got: {type(data).__name__}")

    if _looks_like_legacy_manifest(data):
        data = _upgrade_legacy_manifest_dict(data)

    return ContextManifest(**data)
