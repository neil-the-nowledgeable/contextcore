"""
Pydantic models for ProjectContext CRD specification.

These models provide Python type safety and validation for the ProjectContext
custom resource, matching the OpenAPI schema defined in crds/projectcontext.yaml.

Note: Core type enums (Criticality, BusinessValue, etc.) are imported from
contextcore.contracts.types which is the single source of truth.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

# Import core types from central location
from contextcore.contracts.types import (
    AlertPriority,
    BusinessValue,
    Criticality,
    DashboardPlacement,
    LogLevel,
    RiskType,
)
from contextcore.contracts.validators import (
    duration_validator,
    percentage_validator,
    throughput_validator,
)


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
    tasks: List[str] = Field(default_factory=list, description="Task IDs")
    trace_id: Optional[str] = Field(None, alias="traceId", description="OTel trace ID")


class DesignSpec(BaseModel):
    """Design artifact references."""
    doc: Optional[HttpUrl] = Field(None, description="Design document URL")
    adr: Optional[str] = Field(None, description="ADR identifier or URL")
    api_contract: Optional[HttpUrl] = Field(None, alias="apiContract", description="API spec URL")
    diagrams: List[HttpUrl] = Field(default_factory=list, description="Diagram URLs")


class BusinessSpec(BaseModel):
    """Business context."""
    criticality: Optional[Criticality] = Field(None, description="Business criticality")
    value: Optional[BusinessValue] = Field(None, description="Business value classification")
    owner: Optional[str] = Field(None, description="Owning team")
    cost_center: Optional[str] = Field(None, alias="costCenter", description="Cost center code")
    stakeholders: List[str] = Field(default_factory=list, description="Stakeholder contacts")


class RequirementsSpec(BaseModel):
    """SLO requirements for derivation."""
    availability: Optional[str] = Field(None, description="Target availability % (e.g., '99.95')")
    latency_p50: Optional[str] = Field(None, alias="latencyP50", description="Target P50 latency (e.g., '50ms')")
    latency_p99: Optional[str] = Field(None, alias="latencyP99", description="Target P99 latency (e.g., '200ms')")
    error_budget: Optional[str] = Field(None, alias="errorBudget", description="Error budget % (e.g., '0.05')")
    throughput: Optional[str] = Field(None, description="Target throughput (e.g., '1000rps')")
    source: Optional[str] = Field(None, description="Requirements source")

    model_config = ConfigDict(populate_by_name=True)

    # Validators for field formats
    _validate_availability = field_validator("availability", mode="before")(percentage_validator)
    _validate_error_budget = field_validator("error_budget", mode="before")(percentage_validator)
    _validate_latency_p50 = field_validator("latency_p50", mode="before")(duration_validator)
    _validate_latency_p99 = field_validator("latency_p99", mode="before")(duration_validator)
    _validate_throughput = field_validator("throughput", mode="before")(throughput_validator)


class RiskSpec(BaseModel):
    """Risk signal for alert derivation."""
    type: RiskType = Field(..., description="Risk category")
    description: Optional[str] = Field(None, description="Risk description")
    priority: Optional[AlertPriority] = Field(None, description="Alert priority")
    mitigation: Optional[str] = Field(None, description="Mitigation reference")
    controls: List[str] = Field(default_factory=list, description="Controls in place")


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
        None, alias="metricsInterval", description="Metrics scrape interval (e.g., '10s', '30s')"
    )
    log_level: Optional[LogLevel] = Field(None, alias="logLevel", description="Log level")
    dashboard_placement: Optional[DashboardPlacement] = Field(
        None, alias="dashboardPlacement", description="Dashboard visibility"
    )
    alert_channels: List[str] = Field(
        default_factory=list, alias="alertChannels", description="Alert channels"
    )
    runbook: Optional[HttpUrl] = Field(None, description="Runbook URL")

    model_config = ConfigDict(populate_by_name=True)

    # Validators for field formats
    _validate_metrics_interval = field_validator("metrics_interval", mode="before")(duration_validator)


class ProjectContextSpec(BaseModel):
    """Full ProjectContext specification."""
    project: ProjectSpec
    design: Optional[DesignSpec] = None
    business: Optional[BusinessSpec] = None
    requirements: Optional[RequirementsSpec] = None
    risks: List[RiskSpec] = Field(default_factory=list)
    targets: List[TargetSpec] = Field(..., min_length=1)
    observability: Optional[ObservabilitySpec] = None

    model_config = ConfigDict(populate_by_name=True)


class GeneratedArtifacts(BaseModel):
    """Status of generated observability artifacts."""
    service_monitor: Optional[str] = Field(None, alias="serviceMonitor")
    prometheus_rules: List[str] = Field(default_factory=list, alias="prometheusRules")
    dashboard: Optional[str] = None


class ProjectContextStatus(BaseModel):
    """ProjectContext status."""
    phase: str = "Pending"
    generated_artifacts: Optional[GeneratedArtifacts] = Field(None, alias="generatedArtifacts")
    annotated_resources: List[str] = Field(default_factory=list, alias="annotatedResources")
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
