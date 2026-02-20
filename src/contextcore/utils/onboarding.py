"""
Onboarding metadata for programmatic artifact generation and plan ingestion.

Produces a JSON structure that:
- References artifact manifest and project context paths
- Documents artifact type schemas (parameters, output conventions)
- Includes coverage gaps for incremental generation
- Embeds semantic conventions for artifact generation (dashboards, alerts, etc.)
- Supports provenance chain from export to downstream workflows
- Covers all artifact categories: observability, onboarding, and integrity
  (see docs/reference/pipeline-requirements-onboarding.md)

Used by: contextcore manifest export --emit-onboarding
Consumed by: Plan ingestion workflows, artisan context seed enrichment
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from contextcore.models.artifact_manifest import (
    ArtifactManifest,
    ArtifactType,
    ExportProvenance,
    SCHEMA_VERSION,
)
from contextcore.utils.artifact_conventions import ARTIFACT_OUTPUT_CONVENTIONS
from contextcore.utils.provenance import get_content_checksum, get_file_checksum


# Parameter source: which params come from manifest vs CRD (per R1-F1)
# Keys: parameter name. Values: "manifest.spec.X" or "crd.spec.X" (CRD is distilled from manifest)
ARTIFACT_PARAMETER_SOURCES: Dict[str, Dict[str, str]] = {
    ArtifactType.DASHBOARD.value: {
        "criticality": "manifest.spec.business.criticality",
        "dashboardPlacement": "manifest.spec.observability.dashboardPlacement",
        "datasources": "manifest (template default)",
        "risks": "manifest.spec.risks[]",
    },
    ArtifactType.PROMETHEUS_RULE.value: {
        "alertSeverity": "manifest.spec.business.criticality (→ severity map)",
        "availabilityThreshold": "manifest.spec.requirements.availability",
        "latencyThreshold": "manifest.spec.requirements.latencyP99",
        "latencyP50Threshold": "manifest.spec.requirements.latencyP50",
        "throughput": "manifest.spec.requirements.throughput",
    },
    ArtifactType.SLO_DEFINITION.value: {
        "availability": "manifest.spec.requirements.availability",
        "latencyP99": "manifest.spec.requirements.latencyP99",
        "errorBudget": "manifest.spec.requirements.errorBudget",
        "throughput": "manifest.spec.requirements.throughput",
    },
    ArtifactType.SERVICE_MONITOR.value: {
        "metricsInterval": "manifest.spec.observability.metricsInterval",
        "namespace": "crd.spec.targets[].namespace or default",
    },
    ArtifactType.LOKI_RULE.value: {
        "logSelectors": "manifest (target-based)",
        "recordingRules": "manifest (template default)",
        "labelExtractors": "manifest (template default)",
        "logFormat": "manifest.spec.observability.logLevel",
    },
    ArtifactType.NOTIFICATION_POLICY.value: {
        "alertChannels": "manifest.spec.observability.alertChannels",
        "owner": "manifest.spec.business.owner",
        "owners": "manifest.metadata.owners",
    },
    ArtifactType.RUNBOOK.value: {
        "risks": "manifest.spec.risks[]",
        "escalationContacts": "manifest.metadata.owners",
    },
    ArtifactType.ALERT_TEMPLATE.value: {
        "alertSeverity": "manifest.spec.business.criticality",
        "summaryTemplate": "manifest (template default)",
        "descriptionTemplate": "manifest (template default)",
    },
    ArtifactType.CAPABILITY_INDEX.value: {
        "project_root": "manifest (auto-detected)",
        "index_dir": "docs/capability-index/",
    },
    ArtifactType.AGENT_CARD.value: {
        "capability_index_path": "docs/capability-index/contextcore.agent.yaml",
        "manifest_version": "manifest.metadata.schemaVersion",
    },
    ArtifactType.MCP_TOOLS.value: {
        "capability_index_path": "docs/capability-index/contextcore.agent.yaml",
        "manifest_version": "manifest.metadata.schemaVersion",
    },
    ArtifactType.ONBOARDING_METADATA.value: {
        "manifest_path": "manifest (export output path)",
        "project_context_path": "crd (export output path)",
        "export_dir": "manifest (--output flag)",
    },
    ArtifactType.PROVENANCE.value: {
        "source_checksum": "manifest (SHA-256 of source file)",
        "artifact_checksums": "manifest (SHA-256 of each exported artifact)",
    },
    ArtifactType.INGESTION_TRACEABILITY.value: {
        "requirements_mapping": "manifest (derivation rules → requirements)",
        "coverage_metrics": "manifest (coverage summary percentages)",
    },
    # Source artifact types (CID-018 / Mottainai Gap 15)
    ArtifactType.DOCKERFILE.value: {
        "base_image": "manifest.spec.targets + service_metadata",
        "exposed_ports": "manifest.spec.targets + service_metadata",
        "entrypoint": "manifest.spec.targets + service_metadata",
    },
    ArtifactType.PYTHON_REQUIREMENTS.value: {
        "packages": "manifest.spec.strategy.tactics",
        "constraints": "manifest.spec.strategy.tactics",
    },
    ArtifactType.PROTOBUF_SCHEMA.value: {
        "package": "manifest.spec.targets + service_metadata.schema_contract",
        "services": "manifest.spec.targets + service_metadata.schema_contract",
        "rpcs": "manifest.spec.targets + service_metadata.schema_contract",
    },
    ArtifactType.EDITORCONFIG.value: {
        "indent_style": "project conventions",
        "charset": "project conventions",
    },
    ArtifactType.CI_WORKFLOW.value: {
        "triggers": "manifest.spec.strategy.tactics",
        "jobs": "manifest.spec.strategy.tactics",
        "runtime": "manifest.spec.strategy.tactics",
    },
}

# Example output paths/snippets per artifact type (per R3-F3)
ARTIFACT_EXAMPLE_OUTPUTS: Dict[str, Dict[str, str]] = {
    ArtifactType.SERVICE_MONITOR.value: {
        "example_output_path": "k8s/observability/checkout-api-service-monitor.yaml",
        "example_snippet": "apiVersion: monitoring.coreos.com/v1\nkind: ServiceMonitor\nmetadata:\n  name: checkout-api\nspec:\n  selector:\n    matchLabels:\n      app: checkout-api\n  endpoints:\n    - port: metrics\n      interval: 30s",
    },
    ArtifactType.PROMETHEUS_RULE.value: {
        "example_output_path": "prometheus/rules/checkout-api-prometheus-rules.yaml",
        "example_snippet": "apiVersion: monitoring.coreos.com/v1\nkind: PrometheusRule\nmetadata:\n  name: checkout-api-alerts\nspec:\n  groups:\n    - name: availability\n      rules:\n        - alert: LowAvailability\n          expr: ...",
    },
    ArtifactType.DASHBOARD.value: {
        "example_output_path": "grafana/dashboards/checkout-api-dashboard.json",
        "example_snippet": '{"dashboard":{"title":"checkout-api Service Dashboard","panels":[]},"overwrite":true}',
    },
    ArtifactType.RUNBOOK.value: {
        "example_output_path": "runbooks/checkout-api-runbook.md",
        "example_snippet": "# checkout-api Incident Runbook\n\n## Overview\n\n## Risks\n\n## Escalation Contacts",
    },
    ArtifactType.SLO_DEFINITION.value: {
        "example_output_path": "slo/checkout-api-slo.yaml",
        "example_snippet": "apiVersion: openslo.github.io/v1\nkind: SLO\nmetadata:\n  name: checkout-api\nspec:\n  target: 99.5\n  timeWindow:\n    duration: 30d",
    },
    ArtifactType.LOKI_RULE.value: {
        "example_output_path": "loki/rules/checkout-api-loki-rules.yaml",
        "example_snippet": "groups:\n  - name: checkout-api\n    rules:\n      - alert: HighErrorRate\n        expr: ...",
    },
    ArtifactType.NOTIFICATION_POLICY.value: {
        "example_output_path": "alertmanager/checkout-api-notification.yaml",
        "example_snippet": "receivers:\n  - name: checkout-api-team\n    slack_configs:\n      - channel: '#alerts'",
    },
    ArtifactType.ALERT_TEMPLATE.value: {
        "example_output_path": "alertmanager/templates/checkout-api-alert-template.yaml",
        "example_snippet": "{{ define \"checkout-api.title\" }}{{ .GroupLabels.alertname }}{{ end }}",
    },
    ArtifactType.CAPABILITY_INDEX.value: {
        "example_output_path": "docs/capability-index/project-name.agent.yaml",
        "example_snippet": "manifest_id: project.agent\nname: Project Capabilities\nversion: '1.0.0'\ncapabilities:\n  - capability_id: project.feature.x\n    category: action\n    maturity: beta\n    summary: Feature X",
    },
    ArtifactType.AGENT_CARD.value: {
        "example_output_path": "docs/capability-index/agent-card.json",
        "example_snippet": '{"name":"contextcore","version":"1.0.0","skills":[{"id":"export","name":"Manifest Export"}],"provider":{"organization":"ContextCore"}}',
    },
    ArtifactType.MCP_TOOLS.value: {
        "example_output_path": "docs/capability-index/mcp-tools.json",
        "example_snippet": '{"tools":[{"name":"manifest_export","description":"Export artifact manifest","inputSchema":{"type":"object","properties":{"path":{"type":"string"}}}}]}',
    },
    ArtifactType.ONBOARDING_METADATA.value: {
        "example_output_path": "out/export/onboarding-metadata.json",
        "example_snippet": '{"schema":"contextcore.io/onboarding-metadata/v1","artifact_types":{"dashboard":{}},"parameter_sources":{"dashboard":{}}}',
    },
    ArtifactType.PROVENANCE.value: {
        "example_output_path": "out/export/run-provenance.json",
        "example_snippet": '{"source_checksum":"sha256:abc123","artifacts":["artifact-manifest.yaml","onboarding-metadata.json"]}',
    },
    ArtifactType.INGESTION_TRACEABILITY.value: {
        "example_output_path": "out/export/ingestion-traceability.json",
        "example_snippet": '{"requirements_coverage_percent":85.0,"satisfied":12,"total":14}',
    },
    # Source artifact types (CID-018 / Mottainai Gap 15)
    ArtifactType.DOCKERFILE.value: {
        "example_output_path": "Dockerfile",
        "example_snippet": "FROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install -r requirements.txt\nCOPY . .\nEXPOSE 8080\nUSER nonroot\nENTRYPOINT [\"python\", \"server.py\"]",
    },
    ArtifactType.PYTHON_REQUIREMENTS.value: {
        "example_output_path": "requirements.txt",
        "example_snippet": "# constraints\nflask>=3.0,<4.0\ngrpcio>=1.60\nopentelemetry-api>=1.20",
    },
    ArtifactType.PROTOBUF_SCHEMA.value: {
        "example_output_path": "proto/checkout.proto",
        "example_snippet": 'syntax = "proto3";\npackage hipstershop;\nservice CheckoutService {\n  rpc PlaceOrder (PlaceOrderRequest) returns (PlaceOrderResponse) {}\n}',
    },
    ArtifactType.EDITORCONFIG.value: {
        "example_output_path": ".editorconfig",
        "example_snippet": "root = true\n\n[*]\nindent_style = space\nindent_size = 4\ncharset = utf-8\ntrim_trailing_whitespace = true\ninsert_final_newline = true",
    },
    ArtifactType.CI_WORKFLOW.value: {
        "example_output_path": ".github/workflows/ci.yml",
        "example_snippet": "name: CI\non:\n  push:\n    branches: [main]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4",
    },
}

# Expected output contracts per artifact type (Guide §6 Principle 5 + ExpectedOutput pattern)
# Unifies calibration hints, size limits, required fields, and completeness markers
# into a single per-type contract that downstream consumers can validate against directly.
#
# Follows the ExpectedOutput pattern from src/contextcore/agent/handoff.py:
#   fields: required parameter keys (from ARTIFACT_PARAMETER_SCHEMA)
#   max_lines: size upper bound for proactive truncation prevention
#   max_tokens: approximate token budget (TOKENS_PER_LINE ≈ 3)
#   expected_depth: brief / standard / comprehensive
#   completeness_markers: structural markers that must be present in generated output
#   red_flag: calibration mismatch signal
EXPECTED_OUTPUT_CONTRACTS: Dict[str, Dict[str, Any]] = {
    ArtifactType.DASHBOARD.value: {
        "expected_depth": "comprehensive",
        "max_lines": 300,
        "max_tokens": 1500,
        "completeness_markers": ["panels", "templating", "title", "datasource"],
        "red_flag": "Calibrated as 'brief' — will produce a skeleton, not a usable dashboard",
    },
    ArtifactType.PROMETHEUS_RULE.value: {
        "expected_depth": "standard",
        "max_lines": 150,
        "max_tokens": 750,
        "completeness_markers": ["groups", "rules", "alert", "expr"],
        "red_flag": "Calibrated as 'brief' — likely to produce incomplete alert rules",
    },
    ArtifactType.SLO_DEFINITION.value: {
        "expected_depth": "standard",
        "max_lines": 150,
        "max_tokens": 750,
        "completeness_markers": ["target", "timeWindow", "indicator"],
        "red_flag": "Calibrated as 'comprehensive' — over-engineering for a simple spec",
    },
    ArtifactType.SERVICE_MONITOR.value: {
        "expected_depth": "brief",
        "max_lines": 50,
        "max_tokens": 250,
        "completeness_markers": ["selector", "endpoints", "interval"],
        "red_flag": "Calibrated as 'comprehensive' — over-engineering a simple YAML",
    },
    ArtifactType.LOKI_RULE.value: {
        "expected_depth": "standard",
        "max_lines": 150,
        "max_tokens": 750,
        "completeness_markers": ["groups", "rules", "expr"],
        "red_flag": "Calibrated as 'brief' — likely to produce incomplete recording rules",
    },
    ArtifactType.NOTIFICATION_POLICY.value: {
        "expected_depth": "standard",
        "max_lines": 150,
        "max_tokens": 750,
        "completeness_markers": ["receivers", "routes"],
        "red_flag": "Calibrated as 'comprehensive' — over-engineering a routing config",
    },
    ArtifactType.RUNBOOK.value: {
        "expected_depth": "standard-comprehensive",
        "max_lines": 300,
        "max_tokens": 1500,
        "completeness_markers": ["Overview", "Risks", "Escalation", "Procedures"],
        "red_flag": "Calibrated as 'brief' — runbook will lack incident procedures",
    },
    ArtifactType.ALERT_TEMPLATE.value: {
        "expected_depth": "standard",
        "max_lines": 150,
        "max_tokens": 750,
        "completeness_markers": ["define", "template"],
        "red_flag": "Calibrated as 'comprehensive' — over-engineering a template",
    },
    ArtifactType.CAPABILITY_INDEX.value: {
        "expected_depth": "comprehensive",
        "max_lines": 500,
        "max_tokens": 2500,
        "completeness_markers": ["capabilities", "version", "manifest_id"],
        "red_flag": "Calibrated as 'brief' — will produce an incomplete capability index",
    },
    ArtifactType.AGENT_CARD.value: {
        "expected_depth": "standard",
        "max_lines": 200,
        "max_tokens": 1000,
        "completeness_markers": ["skills", "name", "version"],
        "red_flag": "Calibrated as 'brief' — agent card will lack skill definitions",
    },
    ArtifactType.MCP_TOOLS.value: {
        "expected_depth": "comprehensive",
        "max_lines": 500,
        "max_tokens": 2500,
        "completeness_markers": ["tools", "inputSchema"],
        "red_flag": "Calibrated as 'brief' — MCP tools will lack input schemas",
    },
    ArtifactType.ONBOARDING_METADATA.value: {
        "expected_depth": "standard",
        "max_lines": 150,
        "max_tokens": 750,
        "completeness_markers": ["artifact_types", "parameter_sources"],
        "red_flag": "Calibrated as 'brief' — onboarding metadata will be incomplete",
    },
    ArtifactType.PROVENANCE.value: {
        "expected_depth": "brief",
        "max_lines": 50,
        "max_tokens": 250,
        "completeness_markers": ["source_checksum", "artifacts"],
        "red_flag": "Calibrated as 'comprehensive' — over-engineering a provenance record",
    },
    ArtifactType.INGESTION_TRACEABILITY.value: {
        "expected_depth": "brief",
        "max_lines": 50,
        "max_tokens": 250,
        "completeness_markers": ["requirements_coverage_percent"],
        "red_flag": "Calibrated as 'comprehensive' — over-engineering a traceability record",
    },
    # Source artifact types (CID-018 / Mottainai Gap 15)
    ArtifactType.DOCKERFILE.value: {
        "expected_depth": "standard",
        "max_lines": 50,
        "max_tokens": 250,
        "completeness_markers": ["FROM", "COPY", "EXPOSE", "ENTRYPOINT", "USER"],
        "red_flag": "Calibrated as 'comprehensive' — Dockerfile should be concise, not over-engineered",
    },
    ArtifactType.PYTHON_REQUIREMENTS.value: {
        "expected_depth": "brief",
        "max_lines": 30,
        "max_tokens": 150,
        "completeness_markers": ["# constraints"],
        "red_flag": "Calibrated as 'comprehensive' — requirements.txt should be a flat dependency list",
    },
    ArtifactType.PROTOBUF_SCHEMA.value: {
        "expected_depth": "standard",
        "max_lines": 150,
        "max_tokens": 750,
        "completeness_markers": ["syntax", "package", "service", "rpc"],
        "red_flag": "Calibrated as 'brief' — proto schema will lack service definitions",
    },
    ArtifactType.EDITORCONFIG.value: {
        "expected_depth": "brief",
        "max_lines": 20,
        "max_tokens": 100,
        "completeness_markers": ["root = true", "indent_style", "charset"],
        "red_flag": "Calibrated as 'comprehensive' — .editorconfig should be minimal",
    },
    ArtifactType.CI_WORKFLOW.value: {
        "expected_depth": "standard",
        "max_lines": 100,
        "max_tokens": 500,
        "completeness_markers": ["name:", "on:", "jobs:"],
        "red_flag": "Calibrated as 'brief' — CI workflow will lack job definitions",
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
    ArtifactType.CAPABILITY_INDEX.value: [
        "project_root",
        "index_dir",
    ],
    ArtifactType.AGENT_CARD.value: [
        "capability_index_path",
        "manifest_version",
    ],
    ArtifactType.MCP_TOOLS.value: [
        "capability_index_path",
        "manifest_version",
    ],
    ArtifactType.ONBOARDING_METADATA.value: [
        "manifest_path",
        "project_context_path",
        "export_dir",
    ],
    ArtifactType.PROVENANCE.value: [
        "source_checksum",
        "artifact_checksums",
    ],
    ArtifactType.INGESTION_TRACEABILITY.value: [
        "requirements_mapping",
        "coverage_metrics",
    ],
    # Source artifact types (CID-018 / Mottainai Gap 15)
    ArtifactType.DOCKERFILE.value: [
        "base_image",
        "exposed_ports",
        "entrypoint",
    ],
    ArtifactType.PYTHON_REQUIREMENTS.value: [
        "packages",
        "constraints",
    ],
    ArtifactType.PROTOBUF_SCHEMA.value: [
        "package",
        "services",
        "rpcs",
    ],
    ArtifactType.EDITORCONFIG.value: [
        "indent_style",
        "charset",
    ],
    ArtifactType.CI_WORKFLOW.value: [
        "triggers",
        "jobs",
        "runtime",
    ],
}


def _derive_service_metadata_from_manifest(
    artifact_manifest: ArtifactManifest,
) -> Optional[Dict[str, Any]]:
    """Auto-derive service_metadata from artifact manifest when not explicitly provided.

    Scans artifact_manifest.artifacts for protocol indicators per target:
    - PROTOBUF_SCHEMA artifact → grpc transport, grpc_health_probe healthcheck
    - Otherwise → http transport, http_get healthcheck (default)
    Also extracts port hints from artifact parameters.

    Returns:
        Dict[str, Dict] matching ServiceMetadataEntry schema, or None if no
        meaningful targets found.
    """
    targets: Dict[str, Dict[str, Any]] = {}

    for artifact in artifact_manifest.artifacts:
        target = artifact.target
        if not target:
            continue
        if target not in targets:
            targets[target] = {
                "transport_protocol": "http",
                "healthcheck_type": "http_get",
            }
        if artifact.type == ArtifactType.PROTOBUF_SCHEMA:
            targets[target]["transport_protocol"] = "grpc"
            targets[target]["healthcheck_type"] = "grpc_health_probe"
            # Capture schema_contract from parameters if available
            schema_path = (artifact.parameters or {}).get("schema_contract")
            if schema_path:
                targets[target]["schema_contract"] = schema_path
        # Extract port hints from artifact parameters
        port = (artifact.parameters or {}).get("port")
        if port and "port" not in targets[target]:
            targets[target]["port"] = port

    if not targets:
        return None
    return targets


def build_onboarding_metadata(
    artifact_manifest: ArtifactManifest,
    artifact_manifest_path: str,
    project_context_path: str,
    provenance: Optional[ExportProvenance] = None,
    *,
    artifact_manifest_content: Optional[str] = None,
    project_context_content: Optional[str] = None,
    source_path: Optional[str] = None,
    artifact_task_mapping: Optional[Dict[str, str]] = None,
    output_dir: Optional[str] = None,
    capability_index_dir: Optional[str] = None,
    service_metadata: Optional[Dict[str, Any]] = None,
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
        artifact_task_mapping: Optional mapping of artifact_id -> plan task ID (e.g., wayfinder_core-dashboard -> PI-019)
        output_dir: Optional output directory; when provided, source_path_relative is computed for portability
        service_metadata: Optional per-service metadata dict (service_name -> ServiceMetadataEntry-like dict)
            with transport_protocol, schema_contract, base_image, healthcheck_type

    Returns:
        Dict suitable for JSON serialization
    """
    # Auto-derive service_metadata from manifest if not explicitly provided (Gap 16)
    if service_metadata is None:
        service_metadata = _derive_service_metadata_from_manifest(artifact_manifest)

    # Extract coverage gaps (artifacts with status=needed)
    coverage_gaps: List[str] = [
        a.id for a in artifact_manifest.artifacts if a.status.value == "needed"
    ]

    # Build artifact type schema from conventions + parameter hints + sources + examples
    artifact_types: Dict[str, Dict[str, Any]] = {}
    for artifact in artifact_manifest.artifacts:
        art_type = artifact.type.value
        if art_type not in artifact_types:
            conventions = ARTIFACT_OUTPUT_CONVENTIONS.get(
                art_type,
                {"output_ext": ".yaml", "output_path": f"generated/{{target}}-{art_type}.yaml"},
            )
            param_keys = ARTIFACT_PARAMETER_SCHEMA.get(art_type, [])
            param_sources = ARTIFACT_PARAMETER_SOURCES.get(art_type, {})
            example_outputs = ARTIFACT_EXAMPLE_OUTPUTS.get(art_type, {})
            artifact_types[art_type] = {
                **conventions,
                "parameter_keys": param_keys,
                "parameter_sources": param_sources,
                **example_outputs,
            }

    # ── Derivation rules per artifact type (Guide §4 Phase 3) ──────────
    # Surfaces the derived_from rules so plan ingestion and artisan DESIGN
    # have the concrete business→artifact mappings without re-parsing the
    # full artifact manifest.
    derivation_rules: Dict[str, List[Dict[str, Any]]] = {}
    for artifact in artifact_manifest.artifacts:
        art_type = artifact.type.value
        if artifact.derived_from:
            if art_type not in derivation_rules:
                derivation_rules[art_type] = []
            for rule in artifact.derived_from:
                rule_dict = rule.model_dump(
                    by_alias=True, exclude_none=True, mode="json"
                )
                # Deduplicate: same property+sourceField across targets
                if rule_dict not in derivation_rules[art_type]:
                    derivation_rules[art_type].append(rule_dict)

    # ── Optional requirements bridge (generic, non-workflow-specific) ──
    # Derive requirement hints from derivation rules that source values from
    # manifest.spec.requirements.*. This keeps hints generic while enabling
    # deterministic downstream requirement mapping.
    requirements_hints: List[Dict[str, Any]] = []
    seen_requirement_ids: set[str] = set()
    for rules in derivation_rules.values():
        for rule in rules:
            source_field = rule.get("sourceField")
            if not isinstance(source_field, str):
                continue
            if "requirements." not in source_field:
                continue
            if "manifest.spec.requirements." in source_field:
                tail = source_field.split("manifest.spec.requirements.", 1)[1]
            elif "spec.requirements." in source_field:
                tail = source_field.split("spec.requirements.", 1)[1]
            else:
                tail = source_field.rsplit("requirements.", 1)[-1]
            if not tail:
                continue
            req_id = f"REQ-{tail.replace('.', '-').replace('_', '-').upper()}"
            if req_id in seen_requirement_ids:
                continue
            seen_requirement_ids.add(req_id)
            requirements_hints.append(
                {
                    "id": req_id,
                    "labels": ["nfr", "contextcore-export"],
                    "priority": "medium",
                    "acceptance_anchors": [source_field],
                }
            )

    # ── Pipeline-innate requirements (satisfied by artifact generation) ──
    from contextcore.utils.pipeline_requirements import get_pipeline_innate_hints

    for hint in get_pipeline_innate_hints():
        req_id = hint["id"]
        if req_id in seen_requirement_ids:
            continue
        seen_requirement_ids.add(req_id)
        requirements_hints.append(hint)

    # ── Strategic objectives for dashboard panel generation ──────────
    objectives_export: Optional[List[Dict[str, Any]]] = None
    if artifact_manifest.objectives:
        objectives_export = [
            obj.model_dump(by_alias=True, exclude_none=True, mode="json")
            for obj in artifact_manifest.objectives
        ]

    # ── Artifact dependency graph for generation ordering ──────────
    artifact_deps: Dict[str, List[str]] = {}
    for artifact in artifact_manifest.artifacts:
        if artifact.depends_on:
            artifact_deps[artifact.id] = list(artifact.depends_on)

    # ── Resolved parameters per artifact (concrete values) ──────────
    # Surfaces the actual computed parameter values so downstream consumers
    # don't re-derive from generic parameter_sources.
    resolved_params: Dict[str, Dict[str, Any]] = {}
    for artifact in artifact_manifest.artifacts:
        if artifact.parameters:
            params_dict = {
                k: v for k, v in artifact.parameters.items()
                if v is not None
            }
            if params_dict:
                resolved_params[artifact.id] = params_dict

    # ── Parameter resolvability matrix (machine-readable) ────────────
    # Tracks resolved/unresolved status per artifact + parameter so downstream
    # systems can gate deterministically without embedding ContextCore logic.
    parameter_resolvability: Dict[str, Dict[str, Dict[str, Any]]] = {}
    resolved_count = 0
    unresolved_count = 0
    for artifact in artifact_manifest.artifacts:
        aid = artifact.id
        art_type = artifact.type.value
        expected_params = ARTIFACT_PARAMETER_SCHEMA.get(art_type, [])
        source_map = ARTIFACT_PARAMETER_SOURCES.get(art_type, {})
        actual_params = artifact.parameters or {}

        if not expected_params:
            continue

        parameter_resolvability[aid] = {}
        for key in expected_params:
            source_path = source_map.get(key)
            if key in actual_params and actual_params.get(key) is not None:
                parameter_resolvability[aid][key] = {
                    "status": "resolved",
                    "source_path": source_path,
                }
                resolved_count += 1
                continue

            reason_code = (
                "source_mapping_missing"
                if source_path is None
                else "value_not_materialized"
            )
            reason = (
                "No source mapping exists for this parameter"
                if source_path is None
                else "Source mapping exists but no concrete value was produced"
            )
            parameter_resolvability[aid][key] = {
                "status": "unresolved",
                "source_path": source_path,
                "reason_code": reason_code,
                "reason": reason,
            }
            unresolved_count += 1

    # ── Open questions for design decision surfacing ──────────
    open_questions: Optional[List[Dict[str, Any]]] = None
    if artifact_manifest.guidance and hasattr(artifact_manifest.guidance, "questions"):
        open_qs = [
            q.model_dump(by_alias=True, exclude_none=True, mode="json")
            for q in (artifact_manifest.guidance.questions or [])
            if getattr(q, "status", "open") == "open"
        ]
        if open_qs:
            open_questions = open_qs

    # ── Expected output contracts (Guide §6 + ExpectedOutput pattern) ──
    # Unifies calibration hints, size limits, required fields, and
    # completeness markers into a single per-type contract.  Downstream
    # consumers (plan ingestion, artisan DESIGN/IMPLEMENT, coyote typed
    # stages) can validate generated artifacts against these directly.
    output_contracts: Dict[str, Dict[str, Any]] = {}
    for artifact in artifact_manifest.artifacts:
        art_type = artifact.type.value
        if art_type not in output_contracts and art_type in EXPECTED_OUTPUT_CONTRACTS:
            contract = dict(EXPECTED_OUTPUT_CONTRACTS[art_type])
            # Merge required fields from parameter schema
            contract["fields"] = ARTIFACT_PARAMETER_SCHEMA.get(art_type, [])
            output_contracts[art_type] = contract

    # ── Design calibration hints (Gate 6 requirement) ──────────────────
    # Derives calibration hints from expected_output_contracts for the
    # pipeline checker's design calibration gate (Gate 6). This transforms
    # the unified output contracts into the format expected by the gate.
    # Structure: {artifact_type: {expected_depth, expected_loc_range, red_flag}}
    design_calibration_hints: Dict[str, Dict[str, str]] = {}
    for art_type, contract in output_contracts.items():
        expected_depth = contract.get("expected_depth", "standard")
        max_lines = contract.get("max_lines", 150)
        red_flag = contract.get("red_flag", "")
        
        # Convert max_lines to expected_loc_range
        if max_lines <= 50:
            loc_range = "<=50"
        elif max_lines <= 150:
            loc_range = "51-150"
        elif max_lines <= 300:
            loc_range = "51-300"
        else:
            loc_range = ">150"
        
        design_calibration_hints[art_type] = {
            "expected_depth": expected_depth,
            "expected_loc_range": loc_range,
            "red_flag": red_flag,
        }

    # ── Service-specific calibration hints (REQ-PCG-032 req 6) ──────────
    # When service_metadata is provided, add per-service Dockerfile and
    # client calibration hints so downstream contractors know the expected
    # transport protocol and can detect mismatches.
    if service_metadata:
        for svc_name, svc_meta in service_metadata.items():
            if not isinstance(svc_meta, dict):
                continue
            tp = svc_meta.get("transport_protocol", "unknown")
            red_flag_hint = (
                f"Dockerfile uses HTTP health check for gRPC service"
                if tp == "grpc"
                else f"Dockerfile uses grpc_health_probe for HTTP service"
                if tp == "http"
                else ""
            )
            design_calibration_hints[f"dockerfile_{svc_name}"] = {
                "expected_depth": "standard",
                "expected_loc_range": "<=50",
                "red_flag": red_flag_hint,
                "transport_protocol": tp,
            }
            design_calibration_hints[f"client_{svc_name}"] = {
                "expected_depth": "standard",
                "expected_loc_range": "51-300",
                "red_flag": f"Client uses wrong transport (expected {tp})",
                "transport_protocol": tp,
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
        "schema_version": SCHEMA_VERSION,
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
        "capabilities": {
            "schema_features": [
                "integrity_checksums",
                "parameter_resolvability",
                "output_contracts",
                "design_calibration_hints",
                "file_ownership",
                "requirements_hints",
            ],
            "optional_sections": [
                "artifact_task_mapping",
                "open_questions",
                "objectives",
                "derivation_rules",
                "provenance",
                "requirements_hints",
                "service_metadata",
            ],
        },
    }

    # ── Enrichment fields (Export Enrichment Plan Changes 1-5 + Guide §6) ──
    if derivation_rules:
        result["derivation_rules"] = derivation_rules

    if objectives_export:
        result["objectives"] = objectives_export

    if artifact_deps:
        result["artifact_dependency_graph"] = artifact_deps

    if resolved_params:
        result["resolved_artifact_parameters"] = resolved_params

    if parameter_resolvability:
        result["parameter_resolvability"] = parameter_resolvability
        result["parameter_resolvability_summary"] = {
            "resolved": resolved_count,
            "unresolved": unresolved_count,
            "total": resolved_count + unresolved_count,
        }

    if open_questions:
        result["open_questions"] = open_questions

    if output_contracts:
        result["expected_output_contracts"] = output_contracts

    if design_calibration_hints:
        result["design_calibration_hints"] = design_calibration_hints

    if requirements_hints:
        result["requirements_hints"] = requirements_hints

    # ── Service metadata (REQ-PCG-024 req 7) ──────────────────────────
    if service_metadata:
        result["service_metadata"] = service_metadata

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

    # Artifact ID → task mapping for plan ingestion (when known plan is used)
    if artifact_task_mapping:
        result["artifact_task_mapping"] = artifact_task_mapping

    # ── File ownership mapping (defense-in-depth Principle 1) ─────────
    # Resolves output path templates to concrete file paths and records
    # which artifact(s) own each file.  Downstream consumers (plan
    # ingestion, artisan) use this to classify files as "primary"
    # (single owner) vs "shared" (multiple owners) at the contract level
    # — preventing the plan-design mismatch where a task lists a file in
    # target_files but the design doc says it belongs to another task.
    #
    # Structure:
    #   file_ownership[resolved_path] = {
    #       "artifact_ids": [list of artifact IDs that target this path],
    #       "artifact_types": [list of artifact types],
    #       "scope": "primary" | "shared",
    #       "task_ids": [mapped task IDs, if artifact_task_mapping provided],
    #   }
    file_ownership: Dict[str, Dict[str, Any]] = {}
    for artifact in artifact_manifest.artifacts:
        art_type = artifact.type.value
        conventions = ARTIFACT_OUTPUT_CONVENTIONS.get(art_type, {})
        output_template = conventions.get("output_path", "")
        if output_template and artifact.target:
            resolved_path = output_template.replace("{target}", artifact.target)
            if resolved_path not in file_ownership:
                file_ownership[resolved_path] = {
                    "artifact_ids": [],
                    "artifact_types": [],
                    "scope": "primary",
                    "task_ids": [],
                }
            entry = file_ownership[resolved_path]
            entry["artifact_ids"].append(artifact.id)
            if art_type not in entry["artifact_types"]:
                entry["artifact_types"].append(art_type)
            # Map to task ID if available
            if artifact_task_mapping and artifact.id in artifact_task_mapping:
                tid = artifact_task_mapping[artifact.id]
                if tid not in entry["task_ids"]:
                    entry["task_ids"].append(tid)

    # Mark shared files (owned by multiple artifacts)
    for path, entry in file_ownership.items():
        if len(entry["artifact_ids"]) > 1:
            entry["scope"] = "shared"

    if file_ownership:
        result["file_ownership"] = file_ownership

    # ── Capability context (REQ-CAP-005 + REQ-CAP-006) ──────────────
    if capability_index_dir:
        _logger = logging.getLogger(__name__)
        try:
            from contextcore.utils.capability_index import (
                load_capability_index,
                match_triggers,
                match_patterns,
                match_principles,
            )
            index = load_capability_index(Path(capability_index_dir))
            if not index.is_empty:
                # Match artifact types against capability triggers
                artifact_type_names = list(artifact_types.keys())
                artifact_text = " ".join(artifact_type_names)
                caps = match_triggers(artifact_text, index.capabilities)
                cap_ids = [c.capability_id for c in caps]

                # Always include governance gates
                gate_ids = [
                    "contextcore.a2a.gate.pipeline_integrity",
                    "contextcore.a2a.gate.diagnostic",
                ]

                all_ids = list(set(cap_ids + gate_ids))
                pats = match_patterns(all_ids, index.patterns)
                prins = match_principles(all_ids, index.principles)

                result["capability_context"] = {
                    "index_version": index.version,
                    "applicable_principles": [
                        {"id": p.id, "principle": p.principle}
                        for p in prins
                    ],
                    "applicable_patterns": [
                        {
                            "pattern_id": p.pattern_id,
                            "name": p.name,
                            "capabilities": p.capabilities,
                        }
                        for p in pats
                    ],
                    "matched_capabilities": cap_ids,
                    "governance_gates": gate_ids,
                }

                # Enrich guidance with design principles (REQ-CAP-006)
                if prins and result.get("guidance") is not None:
                    result["guidance"]["design_principles"] = [
                        {
                            "id": p.id,
                            "principle": p.principle,
                            "anti_patterns": p.anti_patterns,
                        }
                        for p in prins
                    ]
        except Exception:
            _logger.debug("Capability index not available for export enrichment")

    # Relative source path for portability (avoid absolute paths in seeds/handoffs)
    # Assumption: output_dir is a subdirectory of project root (e.g. out/ or ./output).
    # When output_dir is outside project (e.g. /tmp/export), relative_to may raise
    # ValueError; we fall back to source_path.
    if output_dir and source_path:
        try:
            out_resolved = Path(output_dir).resolve()
            project_root = out_resolved.parent
            src_resolved = Path(source_path).resolve()
            result["source_path_relative"] = str(src_resolved.relative_to(project_root))
        except ValueError:
            result["source_path_relative"] = source_path
        except OSError:
            result["source_path_relative"] = source_path

    return result


def build_validation_report(
    *,
    onboarding_metadata: Dict[str, Any],
    min_coverage: Optional[float] = None,
) -> Dict[str, Any]:
    """Build export-time validation report from onboarding metadata."""
    coverage = onboarding_metadata.get("coverage", {}) or {}
    overall = coverage.get("overallCoverage", coverage.get("overall_coverage", 0))
    try:
        overall_pct = float(overall)
    except (TypeError, ValueError):
        overall_pct = 0.0
    gaps = coverage.get("gaps", []) if isinstance(coverage, dict) else []
    gaps_list = [g for g in gaps if isinstance(g, str)]

    checksums = {
        "source_checksum": onboarding_metadata.get("source_checksum"),
        "artifact_manifest_checksum": onboarding_metadata.get("artifact_manifest_checksum"),
        "project_context_checksum": onboarding_metadata.get("project_context_checksum"),
    }
    has_checksum_chain = all(isinstance(v, str) and bool(v.strip()) for v in checksums.values())

    resolvability = onboarding_metadata.get("parameter_resolvability", {})
    unresolved_entries: List[Dict[str, Any]] = []
    if isinstance(resolvability, dict):
        for artifact_id, params in resolvability.items():
            if not isinstance(params, dict):
                continue
            for param_key, status_data in params.items():
                if not isinstance(status_data, dict):
                    continue
                if status_data.get("status") == "unresolved":
                    unresolved_entries.append(
                        {
                            "artifact_id": artifact_id,
                            "parameter": param_key,
                            "reason_code": status_data.get("reason_code"),
                            "reason": status_data.get("reason"),
                        }
                    )

    diagnostics: List[Dict[str, str]] = []
    if not has_checksum_chain:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "CHECKSUM_CHAIN_INCOMPLETE",
                "message": "One or more integrity checksums are missing",
            }
        )
    if min_coverage is not None and overall_pct < min_coverage:
        diagnostics.append(
            {
                "severity": "error",
                "code": "COVERAGE_BELOW_MINIMUM",
                "message": (
                    f"Coverage {overall_pct:.1f}% is below minimum {float(min_coverage):.1f}%"
                ),
            }
        )
    if unresolved_entries:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "UNRESOLVED_PARAMETERS",
                "message": f"{len(unresolved_entries)} artifact parameters are unresolved",
            }
        )

    return {
        "version": SCHEMA_VERSION,
        "schema_version": SCHEMA_VERSION,
        "schema": "contextcore.io/validation-report/v1",
        "generated_at": onboarding_metadata.get("generated_at"),
        "project_id": onboarding_metadata.get("project_id"),
        "checksums": checksums,
        "integrity": {
            "checksum_chain_complete": has_checksum_chain,
        },
        "coverage": {
            "overall_coverage_percent": overall_pct,
            "gap_count": len(gaps_list),
            "gaps": gaps_list,
            "minimum_required": min_coverage,
            "meets_minimum": (
                True if min_coverage is None else overall_pct >= float(min_coverage)
            ),
        },
        "resolvability": {
            "summary": onboarding_metadata.get("parameter_resolvability_summary"),
            "unresolved": unresolved_entries,
        },
        "capabilities": onboarding_metadata.get("capabilities", {}),
        "diagnostics": diagnostics,
    }
