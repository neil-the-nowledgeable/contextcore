"""
Shared artifact output conventions used by onboarding and artifact validation.

Extracted to avoid circular imports: artifact_validator and onboarding both
consume these conventions without depending on each other.
"""

from typing import Dict

from contextcore.models.artifact_manifest import ArtifactType

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
    ArtifactType.CAPABILITY_INDEX.value: {
        "output_ext": ".yaml",
        "output_path": "docs/capability-index/contextcore.agent.yaml",
        "description": "Capability index manifest",
        "schema_url": "https://contextcore.io/schemas/capability-index/v1",
    },
    ArtifactType.AGENT_CARD.value: {
        "output_ext": ".json",
        "output_path": "docs/capability-index/agent-card.json",
        "description": "A2A agent card for capability discovery",
        "schema_url": "https://google.github.io/A2A/specification/",
    },
    ArtifactType.MCP_TOOLS.value: {
        "output_ext": ".json",
        "output_path": "docs/capability-index/mcp-tools.json",
        "description": "MCP tool definitions for LLM integration",
        "schema_url": "https://modelcontextprotocol.io/specification/",
    },
    ArtifactType.ONBOARDING_METADATA.value: {
        "output_ext": ".json",
        "output_path": "{output_dir}/onboarding-metadata.json",
        "description": "Programmatic onboarding metadata for plan ingestion",
        "schema_url": "https://contextcore.io/schemas/onboarding-metadata/v1",
    },
    ArtifactType.PROVENANCE.value: {
        "output_ext": ".json",
        "output_path": "{output_dir}/run-provenance.json",
        "description": "Export provenance chain linking inputs to outputs",
        "schema_url": "https://contextcore.io/schemas/provenance/v1",
    },
    ArtifactType.INGESTION_TRACEABILITY.value: {
        "output_ext": ".json",
        "output_path": "{output_dir}/ingestion-traceability.json",
        "description": "Requirements coverage and translation quality gate",
        "schema_url": "https://contextcore.io/schemas/ingestion-traceability/v1",
    },
    # Source artifacts (Mottainai Gap 15) — advisory path conventions
    ArtifactType.SOURCE_MODULE.value: {
        "output_ext": ".py",
        "output_path": "src/{target}.py",
        "description": "Source code module",
        "schema_url": "",
    },
    ArtifactType.DOCKERFILE.value: {
        "output_ext": "",
        "output_path": "Dockerfile",
        "description": "Container build specification",
        "schema_url": "https://docs.docker.com/reference/dockerfile/",
    },
    ArtifactType.DEPENDENCY_MANIFEST.value: {
        "output_ext": ".txt",
        "output_path": "requirements.txt",
        "description": "Dependency manifest (requirements, go.mod, package.json, etc.)",
        "schema_url": "",
    },
    ArtifactType.PROTO_CONTRACT.value: {
        "output_ext": ".proto",
        "output_path": "proto/{target}.proto",
        "description": "Protocol Buffers contract definition",
        "schema_url": "https://protobuf.dev/programming-guides/proto3/",
    },
}
