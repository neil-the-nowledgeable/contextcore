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
}
