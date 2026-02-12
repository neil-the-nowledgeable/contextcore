"""
Onboarding metadata for programmatic artifact generation and plan ingestion.

Produces a JSON structure that:
- References artifact manifest and project context paths
- Documents artifact type schemas (parameters, output conventions)
- Includes coverage gaps for incremental generation
- Embeds semantic conventions for dashboard/panel generation
- Supports provenance chain from export to downstream workflows

Used by: contextcore manifest export --emit-onboarding
Consumed by: Plan ingestion workflows, artisan context seed enrichment
"""

from typing import Any, Dict, List, Optional

from contextcore.models.artifact_manifest import (
    ArtifactManifest,
    ArtifactType,
    ExportProvenance,
    SCHEMA_VERSION,
)
from contextcore.utils.provenance import get_content_checksum, get_file_checksum


# Default output path conventions and schema URLs per artifact type
# schema_url: Reference for post-generation validation (JSON schema, CRD spec, or docs)
ARTIFACT_OUTPUT_CONVENTIONS: Dict[str, Dict[str, str]] = {
    ArtifactType.DASHBOARD.value: {
        "output_ext": ".json",
        "output_path": "grafana/dashboards/{target}-dashboard.json",
        "description": "Grafana dashboard JSON",
        "schema_url": "https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/view-dashboard-json-model/",
    },
    ArtifactType.PROMETHEUS_RULE.value: {
        "output_ext": ".yaml",
        "output_path": "prometheus/rules/{target}-prometheus-rules.yaml",
        "description": "Prometheus alerting rules",
        "schema_url": "https://prometheus-operator.dev/docs/operator/api/#monitoring.coreos.com/v1.PrometheusRule",
    },
    ArtifactType.SLO_DEFINITION.value: {
        "output_ext": ".yaml",
        "output_path": "slo/{target}-slo.yaml",
        "description": "OpenSLO/Sloth SLO definition",
        "schema_url": "https://openslo.com/",
    },
    ArtifactType.SERVICE_MONITOR.value: {
        "output_ext": ".yaml",
        "output_path": "k8s/observability/{target}-service-monitor.yaml",
        "description": "Kubernetes ServiceMonitor",
        "schema_url": "https://prometheus-operator.dev/docs/operator/api/#monitoring.coreos.com/v1.ServiceMonitor",
    },
    ArtifactType.LOKI_RULE.value: {
        "output_ext": ".yaml",
        "output_path": "loki/rules/{target}-loki-rules.yaml",
        "description": "Loki recording/alerting rules",
        "schema_url": "https://grafana.com/docs/loki/latest/rules/",
    },
    ArtifactType.NOTIFICATION_POLICY.value: {
        "output_ext": ".yaml",
        "output_path": "alertmanager/{target}-notification.yaml",
        "description": "Alert routing and notification config",
        "schema_url": "https://prometheus.io/docs/alerting/latest/configuration/",
    },
    ArtifactType.RUNBOOK.value: {
        "output_ext": ".md",
        "output_path": "runbooks/{target}-runbook.md",
        "description": "Incident response runbook",
        "schema_url": "https://docs.github.com/en/contributing/writing-for-github-docs/creating-markdown-runbooks",
    },
    ArtifactType.ALERT_TEMPLATE.value: {
        "output_ext": ".yaml",
        "output_path": "alertmanager/templates/{target}-alert-template.yaml",
        "description": "Alert message template",
        "schema_url": "https://prometheus.io/docs/alerting/latest/configuration/",
    },
}


# Parameter keys per artifact type (for generator validation)
ARTIFACT_PARAMETER_SCHEMA: Dict[str, List[str]] = {
    ArtifactType.DASHBOARD.value: [
        "criticality",
        "dashboardPlacement",
        "datasources",
        "risks",
    ],
    ArtifactType.PROMETHEUS_RULE.value: [
        "alertSeverity",
        "availabilityThreshold",
        "latencyThreshold",
        "latencyP50Threshold",
        "throughput",
    ],
    ArtifactType.SLO_DEFINITION.value: [
        "availability",
        "latencyP99",
        "errorBudget",
        "throughput",
    ],
    ArtifactType.SERVICE_MONITOR.value: [
        "metricsInterval",
        "namespace",
    ],
    ArtifactType.LOKI_RULE.value: [
        "logSelectors",
        "recordingRules",
        "labelExtractors",
        "logFormat",
    ],
    ArtifactType.NOTIFICATION_POLICY.value: [
        "alertChannels",
        "owner",
        "owners",
    ],
    ArtifactType.RUNBOOK.value: [
        "risks",
        "escalationContacts",
    ],
    ArtifactType.ALERT_TEMPLATE.value: [
        "alertSeverity",
        "summaryTemplate",
        "descriptionTemplate",
    ],
}


def build_onboarding_metadata(
    artifact_manifest: ArtifactManifest,
    artifact_manifest_path: str,
    project_context_path: str,
    provenance: Optional[ExportProvenance] = None,
    *,
    artifact_manifest_content: Optional[str] = None,
    project_context_content: Optional[str] = None,
    source_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build onboarding metadata for programmatic artifact generation.

    Args:
        artifact_manifest: The generated artifact manifest
        artifact_manifest_path: Relative path to artifact manifest file
        project_context_path: Relative path to project context CRD file
        provenance: Optional export provenance for audit chain
        artifact_manifest_content: Optional content of artifact manifest for checksum
        project_context_content: Optional content of project context CRD for checksum
        source_path: Path to source context manifest (for source_checksum when provenance absent)

    Returns:
        Dict suitable for JSON serialization
    """
    # Extract coverage gaps (artifacts with status=needed)
    coverage_gaps: List[str] = [
        a.id for a in artifact_manifest.artifacts if a.status.value == "needed"
    ]

    # Build artifact type schema from conventions + parameter hints
    artifact_types: Dict[str, Dict[str, Any]] = {}
    for artifact in artifact_manifest.artifacts:
        art_type = artifact.type.value
        if art_type not in artifact_types:
            conventions = ARTIFACT_OUTPUT_CONVENTIONS.get(
                art_type,
                {"output_ext": ".yaml", "output_path": f"generated/{{target}}-{art_type}.yaml"},
            )
            param_keys = ARTIFACT_PARAMETER_SCHEMA.get(art_type, [])
            artifact_types[art_type] = {
                **conventions,
                "parameter_keys": param_keys,
            }

    # Build semantic conventions block
    semantic_conventions: Optional[Dict[str, Any]] = None
    if artifact_manifest.semantic_conventions:
        semantic_conventions = artifact_manifest.semantic_conventions.model_dump(
            by_alias=True, exclude_none=True, mode="json"
        )

    # Provenance (exclude large blobs, keep checksums/timestamps)
    provenance_dict: Optional[Dict[str, Any]] = None
    if provenance:
        provenance_dict = provenance.model_dump(
            by_alias=True, exclude_none=True, mode="json"
        )

    coverage_dict = artifact_manifest.coverage.model_dump(
        by_alias=True, exclude_none=True, mode="json"
    )
    coverage_dict["gaps"] = coverage_gaps

    result: Dict[str, Any] = {
        "version": SCHEMA_VERSION,
        "schema": "contextcore.io/onboarding-metadata/v1",
        "project_id": artifact_manifest.metadata.project_id,
        "artifact_manifest_path": artifact_manifest_path,
        "project_context_path": project_context_path,
        "crd_reference": artifact_manifest.crd_reference,
        "generated_at": artifact_manifest.metadata.generated_at.isoformat()
        if hasattr(artifact_manifest.metadata.generated_at, "isoformat")
        else str(artifact_manifest.metadata.generated_at),
        "artifact_types": artifact_types,
        "output_path_conventions": ARTIFACT_OUTPUT_CONVENTIONS,
        "parameter_schema": ARTIFACT_PARAMETER_SCHEMA,
        "coverage": coverage_dict,
        "semantic_conventions": semantic_conventions,
        "provenance": provenance_dict,
        "guidance": artifact_manifest.guidance.model_dump(
            by_alias=True, exclude_none=True, mode="json"
        )
        if artifact_manifest.guidance
        else None,
    }
    # Integrity checksums for validation downstream
    if artifact_manifest_content is not None:
        result["artifact_manifest_checksum"] = get_content_checksum(
            artifact_manifest_content
        )
    if project_context_content is not None:
        result["project_context_checksum"] = get_content_checksum(
            project_context_content
        )

    # Provenance chain: source_checksum enables verification from export → onboarding → seed
    if provenance and provenance.source_checksum:
        result["source_checksum"] = provenance.source_checksum
    elif source_path:
        source_checksum = get_file_checksum(source_path)
        if source_checksum:
            result["source_checksum"] = source_checksum

    return result
