"""
Context Manifest v2.0 Models ("Active Control Plane").

This module defines the v2.0 schema for the Context Manifest, which transforms
the manifest from a "passive config file" into an "active control plane" where
humans and agents collaborate.

Key differences from v1.1:
- Explicit `strategy` section (consolidates objectives, strategies, tactics)
- New `guidance` section for agent governance (focus, constraints, questions)
- Structured for agent write-back (agents can answer questions, update status)
- apiVersion: contextcore.io/v1alpha2

Migration path:
- v1.1 manifests can be loaded and upgraded to v2 via manifest_migrate.py
- v2 is additive; v1.1 remains fully supported
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

# Reuse canonical enums from contracts/types.py
from contextcore.contracts.types import (
    ConstraintSeverity,
    Priority,
    QuestionStatus,
)

# Reuse v1.1 models where appropriate
from contextcore.models.core import ProjectContextSpec
from contextcore.models.manifest import (
    ArtifactReference,
    ChangelogEntry,
    Evidence,
    InsightSeverity,
    KeyResult,
    MetricUnit,
    Owner,
    StrategicHorizon,
    TacticStatus,
    TargetOperator,
)


# =============================================================================
# GOVERNANCE MODELS (New in v2.0)
# =============================================================================


class Focus(BaseModel):
    """
    Current priority focus areas for agents.

    Directs agent attention to specific aspects of the project.
    """

    areas: List[str] = Field(
        ..., min_length=1, description="Focus areas (e.g., ['reliability', 'performance'])"
    )
    reason: Optional[str] = Field(None, description="Why these areas are prioritized")
    until: Optional[str] = Field(
        None, description="When focus expires (ISO date or 'indefinite')"
    )


class Constraint(BaseModel):
    """
    A hard rule that agents must follow.

    Constraints are blocking by default; agents should not proceed if they
    would violate a constraint.
    """

    id: str = Field(..., description="Unique constraint ID (e.g., 'C-NO-AWS-SDK')")
    rule: str = Field(..., description="The constraint statement")
    severity: ConstraintSeverity = Field(
        ConstraintSeverity.BLOCKING, description="Constraint severity"
    )
    rationale: Optional[str] = Field(None, description="Why this constraint exists")
    applies_to: List[str] = Field(
        default_factory=list,
        alias="appliesTo",
        description="Files/modules this constraint applies to (empty = all)",
    )

    model_config = ConfigDict(populate_by_name=True)


class Preference(BaseModel):
    """
    A preferred pattern or style (non-blocking).

    Preferences guide agent behavior but don't block execution.
    """

    id: str = Field(..., description="Unique preference ID")
    description: str = Field(..., description="What is preferred")
    example: Optional[str] = Field(None, description="Example of preferred pattern")


class Question(BaseModel):
    """
    An open question for agents to answer.

    Questions enable humans to request specific information from agents,
    creating a feedback loop where agents can respond by updating the manifest.
    """

    id: str = Field(..., description="Unique question ID (e.g., 'Q-LATENCY-SPIKE')")
    question: str = Field(..., description="The question to answer")
    status: QuestionStatus = Field(QuestionStatus.OPEN, description="Question status")
    priority: Priority = Field(Priority.MEDIUM, description="Question priority")
    answer: Optional[str] = Field(None, description="Agent's answer (when status=answered)")
    answered_by: Optional[str] = Field(
        None, alias="answeredBy", description="Agent ID that answered"
    )
    answered_at: Optional[datetime] = Field(
        None, alias="answeredAt", description="When the question was answered"
    )

    model_config = ConfigDict(populate_by_name=True)


class AgentGuidanceSpec(BaseModel):
    """
    Directives for AI agents working on this project.

    The guidance section is the key v2.0 addition that enables "active control plane"
    semantics—agents read guidance, respect constraints, and answer questions.
    """

    focus: Optional[Focus] = Field(None, description="Current priority focus areas")
    constraints: List[Constraint] = Field(
        default_factory=list, description="Hard rules agents must follow"
    )
    preferences: List[Preference] = Field(
        default_factory=list, description="Preferred patterns/styles (non-blocking)"
    )
    questions: List[Question] = Field(
        default_factory=list, description="Open questions for agents to answer"
    )


# =============================================================================
# STRATEGY MODELS (Consolidated from v1.1)
# =============================================================================


class ObjectiveV2(BaseModel):
    """
    A high-level business objective (v2 format).

    Same as v1.1 Objective but without deprecated metric/target fields.
    """

    id: str = Field(..., description="Unique objective ID (e.g., OBJ-RELIABILITY)")
    description: str = Field(..., description="The objective statement")
    key_results: List[KeyResult] = Field(
        default_factory=list,
        alias="keyResults",
        description="Structured key results with metrics",
    )

    model_config = ConfigDict(populate_by_name=True)


class TacticV2(BaseModel):
    """
    A specific action or initiative (v2 format).

    Enhanced with linked_objectives for explicit cross-referencing.
    """

    id: str = Field(..., description="Unique tactic ID (e.g., TAC-KAFKA)")
    description: str = Field(..., description="What we are doing")
    status: TacticStatus = Field(TacticStatus.PLANNED, description="Execution status")
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

    # Cross-references
    linked_objectives: List[str] = Field(
        default_factory=list,
        alias="linkedObjectives",
        description="Objective IDs this tactic supports",
    )

    # Artifact linkage
    artifacts: List[ArtifactReference] = Field(
        default_factory=list, description="Linked artifacts (PRs, issues, deployments)"
    )

    # Plan structure enrichment (from init-from-plan analysis)
    satisfies: List[str] = Field(
        default_factory=list, description="Requirement IDs this tactic satisfies"
    )
    depends_on: Optional[str] = Field(
        None, alias="dependsOn", description="Phase/tactic dependency"
    )
    repo: Optional[str] = Field(
        None, description="Target repository for this tactic"
    )
    deliverables: Optional[Dict[str, Any]] = Field(
        None, description="Expected deliverables (summary, checklist, file_count)"
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_blocked_reason_required(self) -> "TacticV2":
        """Require blocked_reason when status is BLOCKED."""
        if self.status == TacticStatus.BLOCKED and not self.blocked_reason:
            raise ValueError(
                f"Tactic {self.id} has status=blocked but missing blocked_reason"
            )
        return self


class StrategySpec(BaseModel):
    """
    Strategy section consolidating objectives, strategies, and tactics.

    In v2, the hierarchy is flattened for easier querying while maintaining
    linkage via IDs (tactics link to objectives via linked_objectives).
    """

    objectives: List[ObjectiveV2] = Field(
        default_factory=list, description="Business objectives with key results"
    )
    tactics: List[TacticV2] = Field(
        default_factory=list, description="Tactics implementing objectives"
    )

    # Optional: keep strategy groupings for organizational purposes
    strategy_groups: List[Dict[str, Any]] = Field(
        default_factory=list,
        alias="strategyGroups",
        description="Optional strategy groupings (horizon, rationale)",
    )

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# INSIGHT MODEL (Enhanced from v1.1)
# =============================================================================


class InsightV2(BaseModel):
    """
    Derived knowledge or signal about the project (v2 format).

    Same as v1.1 Insight but with id required for tracking.
    """

    id: str = Field(..., description="Insight ID (e.g., INS-001)")
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


# =============================================================================
# MANIFEST STATE (New in v2.0)
# =============================================================================


class ManifestState(BaseModel):
    """
    Ephemeral state tracking for the manifest.

    Used for sync status, derived counters, and operational metadata.
    """

    last_sync_time: Optional[datetime] = Field(
        None, alias="lastSyncTime", description="Last sync with external systems"
    )
    sync_status: str = Field("unknown", alias="syncStatus", description="Sync status")
    objective_count: Optional[int] = Field(
        None, alias="objectiveCount", description="Derived count of objectives"
    )
    active_tactic_count: Optional[int] = Field(
        None, alias="activeTacticCount", description="Derived count of active tactics"
    )
    open_question_count: Optional[int] = Field(
        None, alias="openQuestionCount", description="Derived count of open questions"
    )

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# METADATA (Extended from v1.1)
# =============================================================================


class ManifestMetadataV2(BaseModel):
    """
    Metadata for the Context Manifest v2.

    Extended from v1.1 with additional fields for tracking.
    """

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


# =============================================================================
# CONTEXT MANIFEST V2 (ROOT MODEL)
# =============================================================================


class ContextManifestV2(BaseModel):
    """
    Context Manifest v2.0: The Active Control Plane.

    Synthesizes operational spec, strategic context, agent governance, and insights
    into a unified, collaborative manifest where humans and agents work together.

    Key sections:
    1. `spec` - Operational context (K8s CRD source, unchanged from v1.1)
    2. `strategy` - Strategic context (objectives, tactics)
    3. `guidance` - Agent governance (focus, constraints, questions)
    4. `insights` - Derived signals and observations
    5. `state` - Ephemeral sync/tracking state

    Migration:
    - Use `manifest_migrate.migrate_v1_to_v2()` to upgrade v1.1 manifests
    - v1.1 remains fully supported via `manifest_loader.load_manifest()`
    """

    # K8s-like identifiers
    api_version: str = Field(
        "contextcore.io/v1alpha2",
        alias="apiVersion",
        description="API version (v2 uses v1alpha2)",
    )
    kind: str = Field("ContextManifest", description="Resource kind")

    # Metadata
    metadata: ManifestMetadataV2 = Field(..., description="Manifest metadata")

    # 1. Operational Context (The "What" - Synced to K8s)
    spec: ProjectContextSpec = Field(..., description="Operational specification")

    # 2. Strategic Context (The "Why" - Roadmap & Execution)
    strategy: StrategySpec = Field(
        default_factory=StrategySpec, description="Objectives and tactics"
    )

    # 3. Governance Context (The "How" - Agent Directives)
    guidance: AgentGuidanceSpec = Field(
        default_factory=AgentGuidanceSpec, description="Agent governance directives"
    )

    # 4. Ephemeral Context (The "Now" - Insights & State)
    insights: List[InsightV2] = Field(
        default_factory=list, description="Derived insights"
    )
    state: Optional[ManifestState] = Field(
        None, description="Ephemeral sync/tracking state"
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_cross_references(self) -> "ContextManifestV2":
        """Validate that tactic -> objective references exist."""
        errors: List[str] = []

        objective_ids = {obj.id for obj in self.strategy.objectives}

        for tactic in self.strategy.tactics:
            for obj_ref in tactic.linked_objectives:
                if obj_ref not in objective_ids:
                    errors.append(
                        f"Tactic '{tactic.id}' references unknown objective: '{obj_ref}'"
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
        Uses mode="json" to ensure clean serialization without Python objects.
        """
        return {
            "apiVersion": "contextcore.io/v1",
            "kind": "ProjectContext",
            "metadata": {
                "name": name or self.metadata.name,
                "namespace": namespace,
            },
            "spec": self.spec.model_dump(by_alias=True, exclude_none=True, mode="json"),
        }

    def get_open_questions(self) -> List[Question]:
        """Get all questions with status=open."""
        return [q for q in self.guidance.questions if q.status == QuestionStatus.OPEN]

    def get_active_constraints(self) -> List[Constraint]:
        """Get all blocking constraints."""
        return [
            c for c in self.guidance.constraints
            if c.severity == ConstraintSeverity.BLOCKING
        ]

    def get_active_tactics(self) -> List[TacticV2]:
        """Get all tactics with active statuses."""
        return [
            t for t in self.strategy.tactics
            if t.status in TacticStatus.active_statuses()
        ]

    def compute_state(self) -> ManifestState:
        """Compute derived state counters."""
        return ManifestState(
            objective_count=len(self.strategy.objectives),
            active_tactic_count=len(self.get_active_tactics()),
            open_question_count=len(self.get_open_questions()),
        )

    def generate_artifact_manifest(
        self,
        *,
        source_path: str = ".contextcore.yaml",
        existing_artifacts: Optional[Dict[str, str]] = None,
        extra_metrics: Optional[Dict[str, List[str]]] = None,
    ) -> "ArtifactManifest":
        """
        Generate an Artifact Manifest that defines required observability artifacts.

        This is the key method that bridges ContextCore (knows WHAT is needed based on
        business context) and implementation suites (which CREATE the artifacts).

        The generated manifest includes:
        1. List of required artifacts per target (dashboards, rules, SLOs)
        2. Derivation rules showing how config is derived from business metadata
        3. Coverage tracking (what exists vs what's missing)

        Args:
            source_path: Path to the source manifest file (for tracking)
            existing_artifacts: Optional dict mapping artifact_id -> path for coverage
            extra_metrics: Optional dict of additional metric sets to include in
                semantic conventions (e.g., {"beaver": ["startd8_cost_total", ...]}).
                Allows implementations to inject their own metrics without coupling
                the ContextCore standard to specific expansion packs.

        Returns:
            ArtifactManifest: The artifact specification for consumers
        """
        from contextcore.models.artifact_manifest import (
            ArtifactManifest,
            ArtifactManifestMetadata,
            ArtifactPriority,
            ArtifactSpec,
            ArtifactStatus,
            ArtifactType,
            DerivationRule,
            GuidanceConstraintExport,
            GuidanceExport,
            GuidanceFocusExport,
            GuidancePreferenceExport,
            GuidanceQuestionExport,
            KeyResultExport,
            ObjectiveExport,
            OwnerContact,
            ProjectContextExport,
            SemanticConventionHints,
        )

        existing_artifacts = existing_artifacts or {}
        artifacts: List[ArtifactSpec] = []

        # Build project context for template rendering
        project_context = ProjectContextExport(
            name=self.metadata.name,
            description=getattr(self.spec.project, "description", None),
            owner=self.spec.business.owner if self.spec.business else None,
            cost_center=self.spec.business.cost_center if self.spec.business else None,
            value=(
                self.spec.business.value.value
                if self.spec.business and self.spec.business.value
                else None
            ),
            links=self.metadata.links or {},
        )

        # Build owner contact list
        owner_contacts = [
            OwnerContact(
                team=o.team,
                slack=getattr(o, "slack", None),
                email=getattr(o, "email", None),
                oncall=getattr(o, "oncall", None),
            )
            for o in self.metadata.owners
        ]

        # Build guidance export
        guidance_export = None
        if self.guidance:
            guidance_focus = None
            if self.guidance.focus:
                guidance_focus = GuidanceFocusExport(
                    areas=self.guidance.focus.areas,
                    reason=self.guidance.focus.reason,
                )
            guidance_export = GuidanceExport(
                focus=guidance_focus,
                constraints=[
                    GuidanceConstraintExport(
                        id=c.id,
                        rule=c.rule,
                        severity=c.severity.value if hasattr(c.severity, "value") else str(c.severity),
                        rationale=c.rationale,
                        applies_to=c.applies_to,
                    )
                    for c in self.guidance.constraints
                ],
                preferences=[
                    GuidancePreferenceExport(
                        id=p.id,
                        description=p.description,
                        example=p.example,
                    )
                    for p in self.guidance.preferences
                ],
                questions=[
                    GuidanceQuestionExport(
                        id=q.id,
                        question=q.question,
                        status=q.status.value if hasattr(q.status, "value") else str(q.status),
                        priority=q.priority.value if hasattr(q.priority, "value") else str(q.priority),
                        answer=q.answer,
                        answered_by=q.answered_by,
                    )
                    for q in self.guidance.questions
                ],
            )

        # Build objectives with key result queries
        objectives_export = [
            ObjectiveExport(
                id=obj.id,
                description=obj.description,
                key_results=[
                    KeyResultExport(
                        metric_key=kr.metric_key,
                        unit=kr.unit.value if hasattr(kr.unit, "value") else str(kr.unit) if kr.unit else None,
                        target=kr.target,
                        operator=kr.operator.value if kr.operator and hasattr(kr.operator, "value") else str(kr.operator) if kr.operator else None,
                        baseline=kr.baseline,
                        window=kr.window,
                        data_source=kr.data_source,
                    )
                    for kr in obj.key_results
                ],
            )
            for obj in self.strategy.objectives
        ]

        # Build OTel semantic convention hints
        # Only ContextCore standard metrics are included here.
        # Implementation-specific metrics (e.g., from expansion packs)
        # should be provided via the extra_metrics parameter.
        sem_metrics: Dict[str, List[str]] = {
            "contextcore": [
                "contextcore_task_progress",
                "contextcore_task_status",
                "contextcore_install_completeness_percent",
            ],
        }
        if extra_metrics:
            sem_metrics.update(extra_metrics)

        semantic_conventions = SemanticConventionHints(
            attribute_namespaces=[
                "gen_ai.*",
                "agent.*",
                "io.contextcore.*",
            ],
            metrics=sem_metrics,
            query_templates={
                "task_by_project": '{ span.io.contextcore.project.id = "$project" }',
                "agent_insights": '{ span.agent.insight.type = "$type" }',
                "gen_ai_operations": '{ span.gen_ai.operation.name = "$operation" }',
                "task_logs": '{job="contextcore"} | json | project_id="$project"',
                "task_metrics": 'contextcore_task_progress{project="$project"}',
            },
            log_format="otel",
        )

        # Get criticality and derive severity mapping
        criticality = (
            self.spec.business.criticality.value
            if self.spec.business and self.spec.business.criticality
            else "medium"
        )

        severity_map = {
            "critical": "P1",
            "high": "P2",
            "medium": "P3",
            "low": "P4",
        }
        alert_severity = severity_map.get(criticality.lower(), "P3")

        # Get requirements for SLO derivation
        requirements = self.spec.requirements

        # For each target, define the required artifacts
        for target in self.spec.targets:
            target_name = target.name
            target_id_prefix = target_name.replace("-", "_")

            # Pre-compute artifact IDs for dependency references
            sm_id = f"{target_id_prefix}-service-monitor"
            rules_id = f"{target_id_prefix}-prometheus-rules"
            notify_id = f"{target_id_prefix}-notification"

            # 1. Dashboard - Always required
            dashboard_id = f"{target_id_prefix}-dashboard"
            artifacts.append(
                ArtifactSpec(
                    id=dashboard_id,
                    type=ArtifactType.DASHBOARD,
                    name=f"{target_name} Service Dashboard",
                    target=target_name,
                    priority=ArtifactPriority.REQUIRED,
                    status=(
                        ArtifactStatus.EXISTS
                        if dashboard_id in existing_artifacts
                        else ArtifactStatus.NEEDED
                    ),
                    existing_path=existing_artifacts.get(dashboard_id),
                    derived_from=[
                        DerivationRule(
                            property="title",
                            source_field="spec.targets[].name",
                            transformation="'{name} Service Dashboard'",
                        ),
                        DerivationRule(
                            property="panels.availability",
                            source_field="spec.requirements.availability",
                            transformation=f"SLO threshold: {requirements.availability if requirements else 'N/A'}%",
                            rationale="Dashboard shows availability against SLO target",
                        ),
                    ],
                    parameters={
                        "criticality": criticality,
                        "dashboardPlacement": (
                            self.spec.observability.dashboard_placement
                            if self.spec.observability
                            else "standard"
                        ),
                        "datasources": ["Tempo", "Loki", "mimir"],
                        "risks": [
                            {
                                "type": r.type.value if hasattr(r.type, "value") else str(r.type),
                                "description": r.description,
                                "priority": r.priority.value if r.priority and hasattr(r.priority, "value") else str(r.priority) if r.priority else None,
                            }
                            for r in (self.spec.risks or [])
                        ],
                    },
                    depends_on=[],
                )
            )

            # 2. Prometheus Rules - Required for critical/high, recommended for others
            rules_priority = (
                ArtifactPriority.REQUIRED
                if criticality in ["critical", "high"]
                else ArtifactPriority.RECOMMENDED
            )
            artifacts.append(
                ArtifactSpec(
                    id=rules_id,
                    type=ArtifactType.PROMETHEUS_RULE,
                    name=f"{target_name} Alerting Rules",
                    target=target_name,
                    priority=rules_priority,
                    status=(
                        ArtifactStatus.EXISTS
                        if rules_id in existing_artifacts
                        else ArtifactStatus.NEEDED
                    ),
                    existing_path=existing_artifacts.get(rules_id),
                    derived_from=[
                        DerivationRule(
                            property="severity",
                            source_field="spec.business.criticality",
                            transformation=f"{criticality} → {alert_severity}",
                            rationale="Alert severity is derived from business criticality",
                        ),
                        DerivationRule(
                            property="threshold",
                            source_field="spec.requirements.availability",
                            transformation=f"Target: {requirements.availability if requirements else '99.9'}%",
                        ),
                    ],
                    parameters={
                        "alertSeverity": alert_severity,
                        "availabilityThreshold": (
                            requirements.availability if requirements else "99.9"
                        ),
                        "latencyThreshold": (
                            requirements.latency_p99 if requirements else "200ms"
                        ),
                        "latencyP50Threshold": (
                            requirements.latency_p50 if requirements else None
                        ),
                        "throughput": (
                            requirements.throughput if requirements else None
                        ),
                    },
                    depends_on=[sm_id],
                )
            )

            # 3. SLO Definition - Required for critical, recommended otherwise
            slo_id = f"{target_id_prefix}-slo"
            slo_priority = (
                ArtifactPriority.REQUIRED
                if criticality == "critical"
                else ArtifactPriority.RECOMMENDED
            )
            artifacts.append(
                ArtifactSpec(
                    id=slo_id,
                    type=ArtifactType.SLO_DEFINITION,
                    name=f"{target_name} SLO Definition",
                    target=target_name,
                    priority=slo_priority,
                    status=(
                        ArtifactStatus.EXISTS
                        if slo_id in existing_artifacts
                        else ArtifactStatus.NEEDED
                    ),
                    existing_path=existing_artifacts.get(slo_id),
                    derived_from=[
                        DerivationRule(
                            property="objective",
                            source_field="spec.requirements.availability",
                            transformation=f"Availability SLO: {requirements.availability if requirements else '99.9'}%",
                        ),
                        DerivationRule(
                            property="errorBudget",
                            source_field="spec.requirements.errorBudget",
                            transformation=f"Error budget: {requirements.error_budget if requirements else '0.1'}%",
                        ),
                    ],
                    parameters={
                        "availability": requirements.availability if requirements else "99.9",
                        "latencyP99": requirements.latency_p99 if requirements else "200ms",
                        "errorBudget": requirements.error_budget if requirements else "0.1",
                        "throughput": requirements.throughput if requirements else None,
                    },
                    depends_on=[sm_id],
                )
            )

            # 4. Service Monitor - Required for all
            artifacts.append(
                ArtifactSpec(
                    id=sm_id,
                    type=ArtifactType.SERVICE_MONITOR,
                    name=f"{target_name} Service Monitor",
                    target=target_name,
                    priority=ArtifactPriority.REQUIRED,
                    status=(
                        ArtifactStatus.EXISTS
                        if sm_id in existing_artifacts
                        else ArtifactStatus.NEEDED
                    ),
                    existing_path=existing_artifacts.get(sm_id),
                    derived_from=[
                        DerivationRule(
                            property="scrapeInterval",
                            source_field="spec.observability.metricsInterval",
                            transformation=(
                                f"Interval: {self.spec.observability.metrics_interval if self.spec.observability else '30s'}"
                            ),
                        ),
                    ],
                    parameters={
                        "metricsInterval": (
                            self.spec.observability.metrics_interval
                            if self.spec.observability
                            else "30s"
                        ),
                        "namespace": target.namespace,
                    },
                    depends_on=[],
                )
            )

            # 5. Loki Rules - Recommended for all
            loki_id = f"{target_id_prefix}-loki-rules"
            artifacts.append(
                ArtifactSpec(
                    id=loki_id,
                    type=ArtifactType.LOKI_RULE,
                    name=f"{target_name} Log Recording Rules",
                    target=target_name,
                    priority=ArtifactPriority.RECOMMENDED,
                    status=(
                        ArtifactStatus.EXISTS
                        if loki_id in existing_artifacts
                        else ArtifactStatus.NEEDED
                    ),
                    existing_path=existing_artifacts.get(loki_id),
                    derived_from=[
                        DerivationRule(
                            property="logSelectors",
                            source_field="spec.targets[].name",
                            transformation=f'{{job="{target_name}"}}',
                            rationale="Log selectors derived from service target name",
                        ),
                        DerivationRule(
                            property="logFormat",
                            source_field="spec.observability.logLevel",
                            transformation="otel",
                            rationale="Log format aligned with OTel log bridge conventions",
                        ),
                    ],
                    parameters={
                        "logSelectors": [f'{{app="{target_name}"}}'],
                        "recordingRules": [
                            f"{target_name}_error_rate_5m",
                            f"{target_name}_request_rate_5m",
                        ],
                        "labelExtractors": ["level", "status_code", "method", "path"],
                        "logFormat": "otel",
                    },
                    depends_on=[],
                )
            )

            # 6. Notification Policy - Required for critical/high
            notify_priority = (
                ArtifactPriority.REQUIRED
                if criticality in ["critical", "high"]
                else ArtifactPriority.RECOMMENDED
            )
            artifacts.append(
                ArtifactSpec(
                    id=notify_id,
                    type=ArtifactType.NOTIFICATION_POLICY,
                    name=f"{target_name} Notification Policy",
                    target=target_name,
                    priority=notify_priority,
                    status=(
                        ArtifactStatus.EXISTS
                        if notify_id in existing_artifacts
                        else ArtifactStatus.NEEDED
                    ),
                    existing_path=existing_artifacts.get(notify_id),
                    derived_from=[
                        DerivationRule(
                            property="channels",
                            source_field="spec.observability.alertChannels",
                            transformation=f"Channels: {self.spec.observability.alert_channels if self.spec.observability else []}",
                        ),
                    ],
                    parameters={
                        "alertChannels": (
                            self.spec.observability.alert_channels
                            if self.spec.observability
                            else []
                        ),
                        "owner": self.spec.business.owner if self.spec.business else None,
                        "owners": [
                            {
                                "team": o.team,
                                "slack": getattr(o, "slack", None),
                                "email": getattr(o, "email", None),
                                "oncall": getattr(o, "oncall", None),
                            }
                            for o in self.metadata.owners
                        ],
                    },
                    depends_on=[rules_id],
                )
            )

            # 7. Runbook - Required for critical
            runbook_id = f"{target_id_prefix}-runbook"
            runbook_priority = (
                ArtifactPriority.REQUIRED
                if criticality == "critical"
                else ArtifactPriority.OPTIONAL
            )
            artifacts.append(
                ArtifactSpec(
                    id=runbook_id,
                    type=ArtifactType.RUNBOOK,
                    name=f"{target_name} Incident Runbook",
                    target=target_name,
                    priority=runbook_priority,
                    status=(
                        ArtifactStatus.EXISTS
                        if runbook_id in existing_artifacts
                        else ArtifactStatus.NEEDED
                    ),
                    existing_path=existing_artifacts.get(runbook_id),
                    derived_from=[
                        DerivationRule(
                            property="risks",
                            source_field="spec.risks[]",
                            transformation=f"Risk count: {len(self.spec.risks) if self.spec.risks else 0}",
                            rationale="Runbook should address documented risks",
                        ),
                    ],
                    parameters={
                        "risks": [
                            {
                                "type": r.type.value if hasattr(r.type, "value") else str(r.type),
                                "description": r.description,
                                "priority": r.priority.value if r.priority and hasattr(r.priority, "value") else str(r.priority) if r.priority else None,
                                "mitigation": r.mitigation,
                            }
                            for r in (self.spec.risks or [])
                        ],
                        "escalationContacts": [
                            {
                                "team": o.team,
                                "slack": getattr(o, "slack", None),
                                "email": getattr(o, "email", None),
                                "oncall": getattr(o, "oncall", None),
                            }
                            for o in self.metadata.owners
                        ],
                    },
                    depends_on=[rules_id, notify_id],
                )
            )

        # ── Capability index (project-level, not per-target) ──────────
        cap_index_id = f"{self.spec.project.id.replace('-', '_')}-capability-index"
        artifacts.append(
            ArtifactSpec(
                id=cap_index_id,
                type=ArtifactType.CAPABILITY_INDEX,
                name=f"{self.spec.project.id} Capability Index",
                target=self.spec.project.id,
                priority=ArtifactPriority.RECOMMENDED,
                status=(
                    ArtifactStatus.EXISTS
                    if cap_index_id in existing_artifacts
                    else ArtifactStatus.NEEDED
                ),
                existing_path=existing_artifacts.get(cap_index_id),
                parameters={
                    "project_root": ".",
                    "index_dir": "docs/capability-index/",
                },
            )
        )

        # Create the manifest
        manifest = ArtifactManifest(
            metadata=ArtifactManifestMetadata(
                generated_from=source_path,
                project_id=self.spec.project.id,
            ),
            artifacts=artifacts,
            project_context=project_context,
            owners=owner_contacts,
            guidance=guidance_export,
            objectives=objectives_export,
            semantic_conventions=semantic_conventions,
            crd_reference=f"{self.metadata.name}-projectcontext.yaml",
        )

        # Compute coverage
        manifest.coverage = manifest.compute_coverage()

        return manifest
