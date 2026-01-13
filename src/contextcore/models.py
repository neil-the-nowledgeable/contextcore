"""
Pydantic models for ProjectContext CRD specification.

These models provide Python type safety and validation for the ProjectContext
custom resource, matching the OpenAPI schema defined in crds/projectcontext.yaml.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class Criticality(str, Enum):
    """Business criticality levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BusinessValue(str, Enum):
    """Business value classifications."""
    REVENUE_PRIMARY = "revenue-primary"
    REVENUE_SECONDARY = "revenue-secondary"
    COST_REDUCTION = "cost-reduction"
    COMPLIANCE = "compliance"
    ENABLER = "enabler"
    INTERNAL = "internal"


class RiskType(str, Enum):
    """Risk category types."""
    SECURITY = "security"
    COMPLIANCE = "compliance"
    DATA_INTEGRITY = "data-integrity"
    AVAILABILITY = "availability"
    FINANCIAL = "financial"
    REPUTATIONAL = "reputational"


class AlertPriority(str, Enum):
    """Alert priority levels."""
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class DashboardPlacement(str, Enum):
    """Dashboard visibility levels."""
    FEATURED = "featured"
    STANDARD = "standard"
    ARCHIVED = "archived"


class LogLevel(str, Enum):
    """Recommended log levels."""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class TargetKind(str, Enum):
    """Supported Kubernetes resource kinds."""
    DEPLOYMENT = "Deployment"
    STATEFULSET = "StatefulSet"
    DAEMONSET = "DaemonSet"
    SERVICE = "Service"
    INGRESS = "Ingress"
    CONFIGMAP = "ConfigMap"
    SECRET = "Secret"
    CRONJOB = "CronJob"
    JOB = "Job"


class ProjectSpec(BaseModel):
    """Project identification."""
    id: str = Field(..., description="Project identifier")
    epic: Optional[str] = Field(None, description="Epic ID")
    tasks: list[str] = Field(default_factory=list, description="Task IDs")
    trace_id: Optional[str] = Field(None, alias="traceId", description="OTel trace ID")


class DesignSpec(BaseModel):
    """Design artifact references."""
    doc: Optional[HttpUrl] = Field(None, description="Design document URL")
    adr: Optional[str] = Field(None, description="ADR identifier or URL")
    api_contract: Optional[HttpUrl] = Field(None, alias="apiContract", description="API spec URL")
    diagrams: list[HttpUrl] = Field(default_factory=list, description="Diagram URLs")


class BusinessSpec(BaseModel):
    """Business context."""
    criticality: Optional[Criticality] = Field(None, description="Business criticality")
    value: Optional[BusinessValue] = Field(None, description="Business value classification")
    owner: Optional[str] = Field(None, description="Owning team")
    cost_center: Optional[str] = Field(None, alias="costCenter", description="Cost center code")
    stakeholders: list[str] = Field(default_factory=list, description="Stakeholder contacts")


class RequirementsSpec(BaseModel):
    """SLO requirements for derivation."""
    availability: Optional[str] = Field(None, description="Target availability %")
    latency_p50: Optional[str] = Field(None, alias="latencyP50", description="Target P50 latency")
    latency_p99: Optional[str] = Field(None, alias="latencyP99", description="Target P99 latency")
    error_budget: Optional[str] = Field(None, alias="errorBudget", description="Error budget %")
    throughput: Optional[str] = Field(None, description="Target throughput")
    source: Optional[str] = Field(None, description="Requirements source")


class RiskSpec(BaseModel):
    """Risk signal for alert derivation."""
    type: RiskType = Field(..., description="Risk category")
    description: Optional[str] = Field(None, description="Risk description")
    priority: Optional[AlertPriority] = Field(None, description="Alert priority")
    mitigation: Optional[str] = Field(None, description="Mitigation reference")
    controls: list[str] = Field(default_factory=list, description="Controls in place")


class TargetSpec(BaseModel):
    """Target Kubernetes resource."""
    kind: TargetKind = Field(..., description="Resource kind")
    name: str = Field(..., description="Resource name")
    namespace: Optional[str] = Field(None, description="Resource namespace")


class ObservabilitySpec(BaseModel):
    """Observability strategy configuration."""
    trace_sampling: Optional[float] = Field(
        None, alias="traceSampling", ge=0, le=1, description="Trace sampling rate"
    )
    metrics_interval: Optional[str] = Field(
        None, alias="metricsInterval", description="Metrics scrape interval"
    )
    log_level: Optional[LogLevel] = Field(None, alias="logLevel", description="Log level")
    dashboard_placement: Optional[DashboardPlacement] = Field(
        None, alias="dashboardPlacement", description="Dashboard visibility"
    )
    alert_channels: list[str] = Field(
        default_factory=list, alias="alertChannels", description="Alert channels"
    )
    runbook: Optional[HttpUrl] = Field(None, description="Runbook URL")


class ProjectContextSpec(BaseModel):
    """Full ProjectContext specification."""
    project: ProjectSpec
    design: Optional[DesignSpec] = None
    business: Optional[BusinessSpec] = None
    requirements: Optional[RequirementsSpec] = None
    risks: list[RiskSpec] = Field(default_factory=list)
    targets: list[TargetSpec] = Field(..., min_length=1)
    observability: Optional[ObservabilitySpec] = None

    class Config:
        populate_by_name = True


class GeneratedArtifacts(BaseModel):
    """Status of generated observability artifacts."""
    service_monitor: Optional[str] = Field(None, alias="serviceMonitor")
    prometheus_rules: list[str] = Field(default_factory=list, alias="prometheusRules")
    dashboard: Optional[str] = None


class ProjectContextStatus(BaseModel):
    """ProjectContext status."""
    phase: str = "Pending"
    generated_artifacts: Optional[GeneratedArtifacts] = Field(None, alias="generatedArtifacts")
    annotated_resources: list[str] = Field(default_factory=list, alias="annotatedResources")
    last_sync_time: Optional[str] = Field(None, alias="lastSyncTime")


def derive_observability(spec: ProjectContextSpec) -> ObservabilitySpec:
    """
    Derive observability configuration from project context.

    This implements value-based observability derivation:
    - Critical services get 100% trace sampling, 10s metrics
    - Revenue-primary services get featured dashboards
    - Security risks get P1 alerts
    """
    obs = spec.observability or ObservabilitySpec()

    # Derive from criticality
    if spec.business and spec.business.criticality:
        if obs.trace_sampling is None:
            obs.trace_sampling = {
                Criticality.CRITICAL: 1.0,
                Criticality.HIGH: 0.5,
                Criticality.MEDIUM: 0.1,
                Criticality.LOW: 0.01,
            }.get(spec.business.criticality, 0.1)

        if obs.metrics_interval is None:
            obs.metrics_interval = {
                Criticality.CRITICAL: "10s",
                Criticality.HIGH: "30s",
                Criticality.MEDIUM: "60s",
                Criticality.LOW: "120s",
            }.get(spec.business.criticality, "60s")

    # Derive dashboard placement from business value
    if spec.business and spec.business.value:
        if obs.dashboard_placement is None:
            obs.dashboard_placement = {
                BusinessValue.REVENUE_PRIMARY: DashboardPlacement.FEATURED,
                BusinessValue.REVENUE_SECONDARY: DashboardPlacement.FEATURED,
                BusinessValue.COMPLIANCE: DashboardPlacement.FEATURED,
            }.get(spec.business.value, DashboardPlacement.STANDARD)

    return obs
