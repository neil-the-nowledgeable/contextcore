"""
Artifact Manifest Model - Defines required observability artifacts.

This model serves as the contract between ContextCore (which knows WHAT is needed)
and Wayfinder implementations (which CREATE the artifacts).

The artifact manifest is derived from:
1. ProjectContext CRD metadata (criticality, SLOs, targets)
2. Context Manifest strategy (objectives, tactics)
3. Business requirements (compliance, audit needs)

Usage:
    manifest = load_manifest_v2('.contextcore.yaml')
    artifact_manifest = manifest.generate_artifact_manifest()
    artifact_manifest.to_yaml('artifact-manifest.yaml')
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ArtifactType(str, Enum):
    """Types of observability artifacts that can be generated."""

    DASHBOARD = "dashboard"
    PROMETHEUS_RULE = "prometheus_rule"
    LOKI_RULE = "loki_rule"
    SLO_DEFINITION = "slo_definition"
    SERVICE_MONITOR = "service_monitor"
    NOTIFICATION_POLICY = "notification_policy"
    RUNBOOK = "runbook"
    ALERT_TEMPLATE = "alert_template"
    CAPABILITY_INDEX = "capability_index"


class ArtifactPriority(str, Enum):
    """Priority for artifact generation."""

    REQUIRED = "required"  # Must have for basic observability
    RECOMMENDED = "recommended"  # Should have for production
    OPTIONAL = "optional"  # Nice to have


class ArtifactStatus(str, Enum):
    """Status of an artifact in the coverage tracking."""

    NEEDED = "needed"  # Artifact should exist but doesn't
    EXISTS = "exists"  # Artifact exists (validated)
    OUTDATED = "outdated"  # Artifact exists but needs update
    SKIPPED = "skipped"  # Explicitly skipped (with reason)


class DerivationRule(BaseModel):
    """
    Documents how an artifact property is derived from source metadata.

    This creates an audit trail from business context to observability config.
    """

    property: str = Field(..., description="The artifact property being set")
    source_field: str = Field(
        ..., alias="sourceField", description="Source field in CRD/manifest"
    )
    transformation: str = Field(
        ..., description="How the value is transformed (e.g., 'critical → P1')"
    )
    rationale: Optional[str] = Field(
        None, description="Why this derivation makes sense"
    )

    model_config = ConfigDict(populate_by_name=True)


class ProjectContextExport(BaseModel):
    """Project-level context exported for template rendering."""

    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    owner: Optional[str] = Field(None, description="Business owner")
    cost_center: Optional[str] = Field(
        None, alias="costCenter", description="Cost center"
    )
    value: Optional[str] = Field(None, description="Business value statement")
    links: Dict[str, str] = Field(
        default_factory=dict, description="Related URLs (repo, wiki, dashboard)"
    )

    model_config = ConfigDict(populate_by_name=True)


class OwnerContact(BaseModel):
    """Team ownership and contact information for notification routing."""

    team: str = Field(..., description="Team name")
    slack: Optional[str] = Field(None, description="Slack channel")
    email: Optional[str] = Field(None, description="Email address")
    oncall: Optional[str] = Field(None, description="Oncall rotation name")

    model_config = ConfigDict(populate_by_name=True)


class GuidanceConstraintExport(BaseModel):
    """A constraint from the governance section affecting artifact generation."""

    id: str = Field(..., description="Constraint identifier")
    rule: str = Field(..., description="The constraint rule")
    severity: str = Field(..., description="blocking or warning")
    rationale: Optional[str] = Field(
        None, description="Why this constraint exists"
    )
    applies_to: List[str] = Field(
        default_factory=list,
        alias="appliesTo",
        description="Paths/scopes this applies to",
    )

    model_config = ConfigDict(populate_by_name=True)


class GuidancePreferenceExport(BaseModel):
    """A preference from governance section."""

    id: str = Field(..., description="Preference identifier")
    description: str = Field(..., description="Preference description")
    example: Optional[str] = Field(None, description="Example usage")

    model_config = ConfigDict(populate_by_name=True)


class GuidanceFocusExport(BaseModel):
    """Focus areas from governance section."""

    areas: List[str] = Field(
        default_factory=list, description="Priority focus areas"
    )
    reason: Optional[str] = Field(
        None, description="Why these are the focus areas"
    )

    model_config = ConfigDict(populate_by_name=True)


class GuidanceQuestionExport(BaseModel):
    """An open question from governance section for design decision surfacing."""

    id: str = Field(..., description="Question identifier")
    question: str = Field(..., description="The question text")
    status: str = Field(..., description="Question status (open, answered, dismissed)")
    priority: str = Field(..., description="Question priority (low, medium, high, critical)")
    answer: Optional[str] = Field(None, description="Agent's answer (when answered)")
    answered_by: Optional[str] = Field(
        None, alias="answeredBy", description="Agent ID that answered"
    )

    model_config = ConfigDict(populate_by_name=True)


class GuidanceExport(BaseModel):
    """Governance guidance exported for downstream artifact generation."""

    focus: Optional[GuidanceFocusExport] = Field(
        None, description="Current focus areas"
    )
    constraints: List[GuidanceConstraintExport] = Field(
        default_factory=list, description="Hard constraints"
    )
    preferences: List[GuidancePreferenceExport] = Field(
        default_factory=list, description="Soft preferences"
    )
    questions: List[GuidanceQuestionExport] = Field(
        default_factory=list, description="Open questions for design decisions"
    )

    model_config = ConfigDict(populate_by_name=True)


class KeyResultExport(BaseModel):
    """A key result with optional data source query for dashboard generation."""

    metric_key: str = Field(
        ..., alias="metricKey", description="Metric identifier"
    )
    unit: Optional[str] = Field(None, description="Unit of measurement")
    target: Any = Field(None, description="Target value")
    operator: Optional[str] = Field(
        None,
        alias="targetOperator",
        description="Comparison operator: 'gte' (≥), 'lte' (≤), or 'eq' (==)",
    )
    baseline: Any = Field(None, description="Baseline value")
    window: Optional[str] = Field(
        None, description="Time window (e.g., '30d', '7d')"
    )
    data_source: Optional[str] = Field(
        None,
        alias="dataSource",
        description="PromQL/LogQL/TraceQL query",
    )

    model_config = ConfigDict(populate_by_name=True)


class ObjectiveExport(BaseModel):
    """Strategic objective with key results for dashboard panel generation."""

    id: str = Field(..., description="Objective identifier")
    description: str = Field(..., description="Objective description")
    key_results: List[KeyResultExport] = Field(
        default_factory=list,
        alias="keyResults",
        description="Measurable key results",
    )

    model_config = ConfigDict(populate_by_name=True)


class SemanticConventionHints(BaseModel):
    """OTel semantic convention references for generated artifacts."""

    attribute_namespaces: List[str] = Field(
        default_factory=list,
        alias="attributeNamespaces",
        description="OTel attribute namespaces used (e.g., gen_ai.*, agent.*, io.contextcore.*)",
    )
    metrics: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Metric names by source (e.g., startd8: [startd8_active_sessions, ...])",
    )
    query_templates: Dict[str, str] = Field(
        default_factory=dict,
        alias="queryTemplates",
        description="Named query templates (TraceQL, LogQL, PromQL) for generated artifacts",
    )
    log_format: Optional[str] = Field(
        None,
        alias="logFormat",
        description="Expected log format (e.g., 'otel' for OTel log bridge, 'json' for structured)",
    )

    model_config = ConfigDict(populate_by_name=True)


class ArtifactSpec(BaseModel):
    """
    Specification for a single observability artifact to be generated.

    This is the "contract" that tells Wayfinder implementations exactly
    what to create.
    """

    id: str = Field(..., description="Unique artifact identifier")
    type: ArtifactType = Field(..., description="Type of artifact")
    name: str = Field(..., description="Human-readable name")
    target: str = Field(
        ..., description="Target service/deployment this artifact is for"
    )
    priority: ArtifactPriority = Field(
        default=ArtifactPriority.REQUIRED, description="Generation priority"
    )
    status: ArtifactStatus = Field(
        default=ArtifactStatus.NEEDED, description="Current status"
    )

    # Derivation metadata
    derived_from: List[DerivationRule] = Field(
        default_factory=list,
        alias="derivedFrom",
        description="How this artifact's config is derived from source metadata",
    )

    # Generation parameters (artifact-type specific)
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific generation parameters",
    )

    # Artifact dependency ordering
    depends_on: List[str] = Field(
        default_factory=list,
        alias="dependsOn",
        description="IDs of artifacts that must be generated before this one",
    )

    # Coverage tracking
    existing_path: Optional[str] = Field(
        None,
        alias="existingPath",
        description="Path to existing artifact if it exists",
    )
    last_validated: Optional[datetime] = Field(
        None,
        alias="lastValidated",
        description="When the existing artifact was last validated",
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        alias="validationErrors",
        description="Errors found during validation",
    )

    model_config = ConfigDict(populate_by_name=True)


class TargetCoverage(BaseModel):
    """Coverage summary for a single target (service/deployment)."""

    target: str = Field(..., description="Target name")
    namespace: str = Field(default="default", description="Kubernetes namespace")
    required_count: int = Field(
        default=0, alias="requiredCount", description="Number of required artifacts"
    )
    existing_count: int = Field(
        default=0, alias="existingCount", description="Number of existing artifacts"
    )
    coverage_percent: float = Field(
        default=0.0,
        alias="coveragePercent",
        description="Coverage percentage (existing/required * 100)",
    )
    gaps: List[str] = Field(
        default_factory=list, description="List of missing artifact IDs"
    )

    model_config = ConfigDict(populate_by_name=True)


class CoverageSummary(BaseModel):
    """Overall coverage summary across all targets."""

    total_required: int = Field(
        default=0, alias="totalRequired", description="Total required artifacts"
    )
    total_existing: int = Field(
        default=0, alias="totalExisting", description="Total existing artifacts"
    )
    total_outdated: int = Field(
        default=0, alias="totalOutdated", description="Total outdated artifacts"
    )
    overall_coverage: float = Field(
        default=0.0,
        alias="overallCoverage",
        description="Overall coverage percentage",
    )
    by_target: List[TargetCoverage] = Field(
        default_factory=list,
        alias="byTarget",
        description="Coverage breakdown by target",
    )
    by_type: Dict[str, int] = Field(
        default_factory=dict,
        alias="byType",
        description="Count of needed artifacts by type",
    )

    model_config = ConfigDict(populate_by_name=True)


class GitContext(BaseModel):
    """Git repository context for provenance tracking."""

    commit_sha: Optional[str] = Field(
        None, alias="commitSha", description="Git commit SHA of source file"
    )
    branch: Optional[str] = Field(None, description="Git branch name")
    is_dirty: Optional[bool] = Field(
        None, alias="isDirty", description="True if working directory has uncommitted changes"
    )
    remote_url: Optional[str] = Field(
        None, alias="remoteUrl", description="Git remote origin URL"
    )

    model_config = ConfigDict(populate_by_name=True)


class ExportProvenance(BaseModel):
    """
    Full provenance metadata for artifact manifest generation.
    
    Captures everything needed to understand:
    - WHO generated this (hostname, username)
    - WHEN it was generated (timestamp)
    - WHAT was used (source file, checksums, versions)
    - HOW it was generated (CLI args, environment)
    """

    # Timing
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        alias="generatedAt",
        description="When this manifest was generated (ISO 8601)",
    )
    duration_ms: Optional[int] = Field(
        None, alias="durationMs", description="Export duration in milliseconds"
    )

    # Source identification
    source_path: str = Field(
        ..., alias="sourcePath", description="Absolute path to source context manifest"
    )
    source_checksum: Optional[str] = Field(
        None, alias="sourceChecksum", description="SHA-256 checksum of source file"
    )

    # Version information
    contextcore_version: str = Field(
        default="2.0.0",
        alias="contextcoreVersion",
        description="ContextCore version that generated this",
    )
    python_version: Optional[str] = Field(
        None, alias="pythonVersion", description="Python version used"
    )

    # Environment
    hostname: Optional[str] = Field(None, description="Machine hostname")
    username: Optional[str] = Field(None, description="Username who ran the export")
    working_directory: Optional[str] = Field(
        None, alias="workingDirectory", description="Working directory during export"
    )

    # Git context
    git: Optional[GitContext] = Field(
        None, description="Git repository context for source file"
    )

    # CLI invocation
    cli_args: Optional[List[str]] = Field(
        None, alias="cliArgs", description="CLI arguments used for export"
    )
    cli_options: Optional[Dict[str, Any]] = Field(
        None, alias="cliOptions", description="Parsed CLI options"
    )

    # Output information
    output_directory: Optional[str] = Field(
        None, alias="outputDirectory", description="Directory where outputs were written"
    )
    output_files: Optional[List[str]] = Field(
        None, alias="outputFiles", description="List of files generated"
    )

    model_config = ConfigDict(populate_by_name=True)


# Shared schema version for artifact manifest, onboarding metadata, and seed
SCHEMA_VERSION = "1.0.0"


class ArtifactManifestMetadata(BaseModel):
    """Metadata for the artifact manifest."""

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        alias="schemaVersion",
        description="Schema version for compatibility checks (aligns with onboarding-metadata)",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        alias="generatedAt",
        description="When this manifest was generated",
    )
    generated_from: str = Field(
        ...,
        alias="generatedFrom",
        description="Source file this was generated from",
    )
    contextcore_version: str = Field(
        default="2.0.0",
        alias="contextcoreVersion",
        description="ContextCore version that generated this",
    )
    project_id: str = Field(..., alias="projectId", description="Project identifier")

    # Extended provenance (optional, populated when --emit-provenance is used)
    provenance: Optional[ExportProvenance] = Field(
        None, description="Full provenance metadata for audit trail"
    )

    model_config = ConfigDict(populate_by_name=True)


class ArtifactManifest(BaseModel):
    """
    The Artifact Manifest - contract for observability artifact generation.

    This file tells Wayfinder (or any ContextCore-compliant implementation):
    1. What artifacts are needed for this project
    2. How each artifact's config is derived from business metadata
    3. What already exists vs what's missing (coverage)

    The artifact manifest is the bridge between:
    - ContextCore (knows WHAT is needed based on business context)
    - Wayfinder (knows HOW to create the artifacts)
    """

    api_version: str = Field(
        default="contextcore.io/v1",
        alias="apiVersion",
        description="API version for this manifest",
    )
    kind: str = Field(
        default="ArtifactManifest", description="Resource kind"
    )
    metadata: ArtifactManifestMetadata = Field(
        ..., description="Manifest metadata"
    )

    # The actual artifact specifications
    artifacts: List[ArtifactSpec] = Field(
        default_factory=list,
        description="List of artifacts to be generated",
    )

    # Project context for template rendering
    project_context: Optional[ProjectContextExport] = Field(
        None,
        alias="projectContext",
        description="Project-level context for template rendering",
    )

    # Ownership and contact info
    owners: List[OwnerContact] = Field(
        default_factory=list,
        description="Team ownership and contact information",
    )

    # Governance guidance
    guidance: Optional[GuidanceExport] = Field(
        None,
        description="Governance guidance affecting artifact generation",
    )

    # Strategic objectives (for dashboard panel generation)
    objectives: List[ObjectiveExport] = Field(
        default_factory=list,
        description="Strategic objectives with key result queries",
    )

    # OTel semantic convention references
    semantic_conventions: Optional[SemanticConventionHints] = Field(
        None,
        alias="semanticConventions",
        description="OTel semantic convention hints for generated artifacts",
    )

    # Coverage tracking
    coverage: CoverageSummary = Field(
        default_factory=CoverageSummary,
        description="Coverage summary",
    )

    # Reference to source CRD
    crd_reference: Optional[str] = Field(
        None,
        alias="crdReference",
        description="Path to the generated ProjectContext CRD",
    )

    model_config = ConfigDict(populate_by_name=True)

    def to_yaml(self, path: str) -> None:
        """Write the artifact manifest to a YAML file."""
        import yaml

        data = self._serialize_for_yaml()

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def _serialize_for_yaml(self) -> Dict[str, Any]:
        """Serialize to a clean dict with string values (no Python objects)."""
        data = self.model_dump(by_alias=True, exclude_none=True, mode="json")
        return data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")

    def get_gaps(self) -> List[ArtifactSpec]:
        """Get list of artifacts that are needed but don't exist."""
        return [a for a in self.artifacts if a.status == ArtifactStatus.NEEDED]

    def get_by_target(self, target: str) -> List[ArtifactSpec]:
        """Get all artifacts for a specific target."""
        return [a for a in self.artifacts if a.target == target]

    def get_by_type(self, artifact_type: ArtifactType) -> List[ArtifactSpec]:
        """Get all artifacts of a specific type."""
        return [a for a in self.artifacts if a.type == artifact_type]

    def compute_coverage(self) -> CoverageSummary:
        """Recompute coverage summary from current artifacts."""
        # Count by status
        required = [
            a for a in self.artifacts if a.priority == ArtifactPriority.REQUIRED
        ]
        existing = [a for a in self.artifacts if a.status == ArtifactStatus.EXISTS]
        outdated = [a for a in self.artifacts if a.status == ArtifactStatus.OUTDATED]

        # Group by target
        targets: Dict[str, List[ArtifactSpec]] = {}
        for artifact in self.artifacts:
            if artifact.target not in targets:
                targets[artifact.target] = []
            targets[artifact.target].append(artifact)

        by_target = []
        for target, artifacts in targets.items():
            target_required = [
                a for a in artifacts if a.priority == ArtifactPriority.REQUIRED
            ]
            target_existing = [
                a for a in artifacts if a.status == ArtifactStatus.EXISTS
            ]
            target_gaps = [
                a.id
                for a in artifacts
                if a.status == ArtifactStatus.NEEDED
                and a.priority == ArtifactPriority.REQUIRED
            ]

            coverage_pct = (
                (len(target_existing) / len(target_required) * 100)
                if target_required
                else 100.0
            )

            by_target.append(
                TargetCoverage(
                    target=target,
                    required_count=len(target_required),
                    existing_count=len(target_existing),
                    coverage_percent=round(coverage_pct, 1),
                    gaps=target_gaps,
                )
            )

        # Count by type
        by_type: Dict[str, int] = {}
        for artifact in self.artifacts:
            if artifact.status == ArtifactStatus.NEEDED:
                type_name = artifact.type.value
                by_type[type_name] = by_type.get(type_name, 0) + 1

        overall = (
            (len(existing) / len(required) * 100) if required else 100.0
        )

        return CoverageSummary(
            total_required=len(required),
            total_existing=len(existing),
            total_outdated=len(outdated),
            overall_coverage=round(overall, 1),
            by_target=by_target,
            by_type=by_type,
        )
