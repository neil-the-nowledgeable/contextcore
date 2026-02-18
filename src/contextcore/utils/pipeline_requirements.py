"""
Pipeline-innate requirements for the ContextCore Capability Delivery Pipeline.

These requirements apply to ALL projects processed through the pipeline —
they are satisfied by artifact generation, not by plan features.  The export
step injects them as hints into onboarding-metadata.json, and the plan-ingestion
consumer auto-satisfies them without requiring plan-text matches.

Contract string: ``PIPELINE_INNATE_LABEL`` (``"pipeline-innate"``) appears in
the ``labels`` array of each hint and in the ``satisfied_by_artifact`` field.
Consumers check for this label to distinguish pipeline-innate hints from
project-specific (derivation-rule-based) hints.
"""

from typing import Any, Dict, List

PIPELINE_INNATE_LABEL = "pipeline-innate"

PIPELINE_INNATE_REQUIREMENTS: List[Dict[str, Any]] = [
    # ── Observability (REQ-CDP-OBS-001 … 007) ────────────────────────
    {
        "id": "REQ-CDP-OBS-001",
        "category": "observability",
        "summary": "Service Level Objectives — SLO definition artifact generated",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "observability"],
        "priority": "P1",
        "satisfied_by_artifact": "slo_definition",
        "acceptance_anchors": [
            "spec.requirements.availability",
            "spec.requirements.errorBudget",
        ],
    },
    {
        "id": "REQ-CDP-OBS-002",
        "category": "observability",
        "summary": "Service Dashboard — Grafana dashboard generated per target",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "observability"],
        "priority": "P1",
        "satisfied_by_artifact": "dashboard",
        "acceptance_anchors": [
            "spec.requirements.availability",
            "spec.requirements.latencyP99",
            "spec.requirements.throughput",
        ],
    },
    {
        "id": "REQ-CDP-OBS-003",
        "category": "observability",
        "summary": "Alerting Rules — Prometheus rules generated from criticality",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "observability"],
        "priority": "P1",
        "satisfied_by_artifact": "prometheus_rule",
        "acceptance_anchors": [
            "spec.requirements.availability",
            "spec.requirements.latencyP99",
            "spec.business.criticality",
        ],
    },
    {
        "id": "REQ-CDP-OBS-004",
        "category": "observability",
        "summary": "Service Monitor — metric scrape config generated per target",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "observability"],
        "priority": "P1",
        "satisfied_by_artifact": "service_monitor",
        "acceptance_anchors": [
            "spec.observability.metricsInterval",
            "spec.targets[].namespace",
        ],
    },
    {
        "id": "REQ-CDP-OBS-005",
        "category": "observability",
        "summary": "Notification Policy — alert routing with channels from manifest",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "observability"],
        "priority": "P1",
        "satisfied_by_artifact": "notification_policy",
        "acceptance_anchors": [
            "spec.observability.alertChannels",
            "metadata.owners",
        ],
    },
    {
        "id": "REQ-CDP-OBS-006",
        "category": "observability",
        "summary": "Log Recording Rules — Loki rules for error/request rate",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "observability"],
        "priority": "P2",
        "satisfied_by_artifact": "loki_rule",
        "acceptance_anchors": [
            "spec.targets[].name",
            "spec.observability.logLevel",
        ],
    },
    {
        "id": "REQ-CDP-OBS-007",
        "category": "observability",
        "summary": "Incident Runbook — runbook generated from documented risks",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "observability"],
        "priority": "P3",
        "satisfied_by_artifact": "runbook",
        "acceptance_anchors": [
            "spec.risks[]",
            "metadata.owners",
        ],
    },
    # ── Onboarding (REQ-CDP-ONB-001 … 004) ───────────────────────────
    {
        "id": "REQ-CDP-ONB-001",
        "category": "onboarding",
        "summary": "Capability Index — agent.yaml generated from source + API contracts",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "onboarding"],
        "priority": "P2",
        "satisfied_by_artifact": "capability_index",
        "acceptance_anchors": [
            "capability_id",
            "category",
            "maturity",
            "evidence",
        ],
    },
    {
        "id": "REQ-CDP-ONB-002",
        "category": "onboarding",
        "summary": "Agent Card — A2A agent-card.json generated from capability index",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "onboarding"],
        "priority": "P2",
        "satisfied_by_artifact": "agent_card",
        "acceptance_anchors": [
            "skills",
            "provider",
        ],
    },
    {
        "id": "REQ-CDP-ONB-003",
        "category": "onboarding",
        "summary": "MCP Tool Definitions — mcp-tools.json from capability index",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "onboarding"],
        "priority": "P3",
        "satisfied_by_artifact": "mcp_tools",
        "acceptance_anchors": [
            "inputSchema",
            "annotations",
        ],
    },
    {
        "id": "REQ-CDP-ONB-004",
        "category": "onboarding",
        "summary": "Onboarding Metadata — programmatic metadata exported at EXPORT stage",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "onboarding"],
        "priority": "P1",
        "satisfied_by_artifact": "onboarding_metadata",
        "acceptance_anchors": [
            "strategy.*",
            "spec.project.*",
        ],
    },
    # ── Pipeline Integrity (REQ-CDP-INT-001, 002) ─────────────────────
    {
        "id": "REQ-CDP-INT-001",
        "category": "pipeline-integrity",
        "summary": "Provenance Chain — checksums link inputs to outputs",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "integrity"],
        "priority": "P1",
        "satisfied_by_artifact": "provenance",
        "acceptance_anchors": [
            "provenance.json",
            "run-provenance.json",
            "source_checksum",
        ],
    },
    {
        "id": "REQ-CDP-INT-002",
        "category": "pipeline-integrity",
        "summary": "Translation Quality Gate — coverage computed and reported",
        "labels": [PIPELINE_INNATE_LABEL, "nfr", "integrity"],
        "priority": "P1",
        "satisfied_by_artifact": "ingestion-traceability",
        "acceptance_anchors": [
            "requirements_coverage_percent",
            "route_escalation",
        ],
    },
]


def get_pipeline_innate_hints() -> List[Dict[str, Any]]:
    """Return pipeline-innate requirements as hint dicts.

    The returned format matches the derivation-rule-based hints produced by
    ``build_onboarding_metadata`` so they can be appended to the same
    ``requirements_hints`` list.
    """
    return [
        {
            "id": req["id"],
            "labels": list(req["labels"]),
            "priority": req["priority"],
            "acceptance_anchors": list(req["acceptance_anchors"]),
            "satisfied_by_artifact": req["satisfied_by_artifact"],
        }
        for req in PIPELINE_INNATE_REQUIREMENTS
    ]


def is_pipeline_innate_hint(hint: Dict[str, Any]) -> bool:
    """Check whether a hint dict carries the pipeline-innate label."""
    labels = hint.get("labels")
    if isinstance(labels, list):
        return PIPELINE_INNATE_LABEL in labels
    return False
