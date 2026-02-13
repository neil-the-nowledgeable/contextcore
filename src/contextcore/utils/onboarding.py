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
    artifact_task_mapping: Optional[Dict[str, str]] = None,
    output_dir: Optional[str] = None,
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

    Returns:
        Dict suitable for JSON serialization
    """
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

    # ── Enrichment fields (Export Enrichment Plan Changes 1-5 + Guide §6) ──
    if derivation_rules:
        result["derivation_rules"] = derivation_rules

    if objectives_export:
        result["objectives"] = objectives_export

    if artifact_deps:
        result["artifact_dependency_graph"] = artifact_deps

    if resolved_params:
        result["resolved_artifact_parameters"] = resolved_params

    if open_questions:
        result["open_questions"] = open_questions

    if output_contracts:
        result["expected_output_contracts"] = output_contracts

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

    # Relative source path for portability (avoid absolute paths in seeds/handoffs)
    # Assumption: output_dir is a subdirectory of project root (e.g. out/ or ./output).
    # When output_dir is outside project (e.g. /tmp/export), relative_to may raise
    # ValueError; we fall back to source_path.
    if output_dir and source_path:
        try:
            from pathlib import Path
            out_resolved = Path(output_dir).resolve()
            project_root = out_resolved.parent
            src_resolved = Path(source_path).resolve()
            result["source_path_relative"] = str(src_resolved.relative_to(project_root))
        except ValueError:
            result["source_path_relative"] = source_path
        except OSError:
            result["source_path_relative"] = source_path

    return result
