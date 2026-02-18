"""
Helpers for `contextcore manifest init-from-plan`.

Keeps CLI wiring in `manifest.py` thin by isolating template construction
and plan/requirements inference logic.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Readiness threshold configuration (REQ-CAP-004) ──────────────
# Externalized from hardcoded values. When the capability index is available,
# these defaults can be overridden by gate capability metadata.
# Source rationale: docs/design/requirements/REQ_CAPABILITY_AWARE_PIPELINE.md
_READINESS_THRESHOLDS: Dict[str, Any] = {
    "verdict_ready": 60,
    "verdict_needs_enrichment": 30,
    "gate_checksum_chain_min_reqs": 2,
    "gate_derivation_rules_min_reqs": 3,
}

# ── Plan structure metadata patterns (Option 2 enrichment) ──────────
_REQ_ID_PATTERN = re.compile(r'\b((?:REQ|FR|NFR)[-_][\w-]*\d+)\b', re.IGNORECASE)
_SATISFIES_PATTERN = re.compile(r'\*{0,2}Satisfies:?\*{0,2}\s*(.*)', re.IGNORECASE)
_DEPENDS_ON_PATTERN = re.compile(r'\*{0,2}Depends\s+on:?\*{0,2}\s*(.*)', re.IGNORECASE)
_REPO_PATTERN = re.compile(r'\*{0,2}Repos?:?\*{0,2}\s*(.*)', re.IGNORECASE)
_DELIVERABLES_PATTERN = re.compile(r'\*{0,2}Deliverables?:?\*{0,2}\s*(.*)', re.IGNORECASE)
_CHECKLIST_PATTERN = re.compile(r'-\s*\[([x ])\]\s*`?([^`\n]+)`?', re.IGNORECASE)
_VALIDATION_PATTERN = re.compile(r'\*{0,2}Validation:?\*{0,2}\s*(.*)', re.IGNORECASE)


def build_v2_manifest_template(name: str) -> Dict[str, Any]:
    """Build a baseline v2 manifest payload."""
    today = datetime.now().strftime("%Y-%m-%d")
    display_name = name.replace("-", " ").title()
    return {
        "apiVersion": "contextcore.io/v1alpha2",
        "kind": "ContextManifest",
        "metadata": {
            "name": name,
            "owners": [{"team": "engineering", "slack": "#alerts", "email": "team@example.com"}],
            "changelog": [
                {
                    "version": "2.0",
                    "date": today,
                    "author": "you",
                    "summary": f"Initial v2.0 manifest for {name}",
                    "changes": ["Initial v2.0 manifest"],
                }
            ],
            "links": {
                "repo": f"https://github.com/your-org/{name}",
                "docs": f"https://github.com/your-org/{name}/wiki",
                "dashboard": "http://localhost:3000/d/contextcore-portfolio",
            },
        },
        "spec": {
            "project": {
                "id": name,
                "name": display_name,
                "description": f"{display_name} service - update this description.",
            },
            "business": {
                "criticality": "medium",
                "owner": "engineering",
                "value": "enabler",
            },
            "requirements": {
                "availability": "99.9",
                "latencyP99": "500ms",
                "throughput": "100rps",
                "errorBudget": "0.1",
                "source": "contextcore-pipeline-innate",
            },
            "risks": [
                {
                    "type": "availability",
                    "description": "Example risk - update or remove",
                    "priority": "P3",
                    "mitigation": "Example mitigation",
                },
            ],
            "targets": [
                {
                    "kind": "Deployment",
                    "name": name,
                    "namespace": "default",
                },
            ],
            "observability": {
                "traceSampling": 1.0,
                "metricsInterval": "30s",
                "alertChannels": ["#alerts"],
                "logLevel": "info",
                "dashboardPlacement": "standard",
            },
        },
        "strategy": {
            "objectives": [
                {
                    "id": "OBJ-001",
                    "description": "Example objective - update with real business goal",
                    "keyResults": [
                        {
                            "metricKey": "availability",
                            "unit": "%",
                            "target": 99.9,
                            "targetOperator": "gte",
                            "window": "30d",
                        }
                    ],
                }
            ],
            "tactics": [
                {
                    "id": "TAC-001",
                    "description": "Example tactic - update with real action item",
                    "status": "planned",
                    "linkedObjectives": ["OBJ-001"],
                }
            ],
        },
        "guidance": {
            "focus": {
                "areas": ["reliability"],
                "reason": "Focus on core stability",
            },
            "constraints": [],
            "preferences": [],
            "questions": [
                {
                    "id": "Q-001",
                    "question": "What is the expected peak traffic pattern for this service?",
                    "status": "open",
                    "priority": "medium",
                },
            ],
        },
        "insights": [],
    }


def _find_capability_index_dir(project_root: Optional[str] = None) -> Path:
    """Locate the capability index directory relative to project root or CWD."""
    candidates = []
    if project_root:
        candidates.append(Path(project_root) / "docs" / "capability-index")
    candidates.append(Path.cwd() / "docs" / "capability-index")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    # Return the first candidate even if it doesn't exist (caller checks)
    return candidates[0]


def _load_gate_thresholds(project_root: Optional[str] = None) -> Dict[str, Any]:
    """Load readiness thresholds, optionally enriched from capability index.

    Falls back to _READINESS_THRESHOLDS defaults when the capability index
    is not available or doesn't contain gate threshold metadata.
    """
    thresholds = dict(_READINESS_THRESHOLDS)
    try:
        from contextcore.utils.capability_index import load_capability_index

        cap_index_dir = _find_capability_index_dir(project_root)
        cap_index = load_capability_index(cap_index_dir)
        if not cap_index.is_empty:
            # Look for gate capabilities that declare threshold metadata
            for cap in cap_index.capabilities:
                if cap.capability_id == "contextcore.a2a.gate.pipeline_integrity":
                    # If the capability has threshold hints in its summary or triggers,
                    # we could extract them. For now, the presence of the gate capability
                    # confirms the thresholds are aligned with the gate design.
                    break
    except Exception:
        pass
    return thresholds


def enrich_template_from_capability_index(
    manifest_data: Dict[str, Any],
    index_dir: Optional[Path] = None,
) -> None:
    """Enrich manifest template with capability index principles and patterns.

    Modifies *manifest_data* in-place.  No-op if the index is not available.
    Called by ``manifest init`` after building the template (REQ-CAP-002).
    """
    if index_dir is None:
        index_dir = _find_capability_index_dir()

    try:
        from contextcore.utils.capability_index import load_capability_index
    except ImportError:
        return

    try:
        index = load_capability_index(index_dir)
    except Exception:
        logger.debug("Capability index not available for init enrichment")
        return

    if index.is_empty:
        return

    guidance = manifest_data.setdefault("guidance", {})

    # Inject universally-applicable principles as advisory constraints
    target_principle_ids = {
        "typed_over_prose",
        "prescriptive_over_descriptive",
        "observable_contracts",
    }
    matching_principles = [p for p in index.principles if p.id in target_principle_ids]
    if matching_principles:
        constraints = guidance.get("constraints", []) or []
        for idx, prin in enumerate(matching_principles, start=1):
            constraints.append({
                "id": f"C-PRINCIPLE-{prin.id}",
                "rule": prin.principle,
                "severity": "advisory",
                "source": f"contextcore.agent.yaml#{prin.id}",
            })
        guidance["constraints"] = constraints

    # Inject top patterns as preferences
    target_pattern_ids = {"typed_handoff", "contract_validation"}
    matching_patterns = [p for p in index.patterns if p.pattern_id in target_pattern_ids]
    if matching_patterns:
        preferences = guidance.get("preferences", []) or []
        for idx, pat in enumerate(matching_patterns, start=1):
            preferences.append({
                "id": f"P-PATTERN-{pat.pattern_id}",
                "description": pat.summary,
                "source": f"contextcore.agent.yaml#{pat.pattern_id}",
            })
        guidance["preferences"] = preferences


# Valid risk types per contextcore.contracts.types.RiskType
_RISK_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "security": ["security", "auth", "credential", "encrypt", "vulnerability", "attack", "breach", "injection"],
    "compliance": ["compliance", "regulation", "audit", "gdpr", "hipaa", "pci", "sox", "legal"],
    "data-integrity": ["data integrity", "corruption", "data loss", "consistency", "backup", "replication"],
    "availability": ["availability", "uptime", "downtime", "outage", "failover", "disaster", "redundancy"],
    "financial": ["cost", "budget", "spending", "billing", "financial", "revenue"],
    "reputational": ["reputation", "customer trust", "brand", "public", "media"],
}


def _infer_risk_type(risk_text: str) -> str:
    """Infer the risk type from risk description text using keyword matching.

    Falls back to 'availability' when no keywords match.
    Valid types: security, compliance, data-integrity, availability, financial, reputational.
    """
    lowered = risk_text.lower()
    for risk_type, keywords in _RISK_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return risk_type
    return "availability"


def infer_init_from_plan(
    manifest_data: Dict[str, Any],
    plan_text: str,
    requirements_text: str,
    project_root: Optional[str],
    emit_guidance_questions: bool,
    plan_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Infer manifest fields from plan/requirements text."""
    text = "\n".join([plan_text, requirements_text])
    inferences: List[Dict[str, Any]] = []
    warnings: List[str] = []

    def add_inference(field_path: str, value: Any, source: str, confidence: float) -> None:
        inferences.append(
            {
                "field_path": field_path,
                "value": value,
                "source": source,
                "confidence": confidence,
            }
        )

    def is_metadata_line(line: str) -> bool:
        l = line.strip().lower()
        return (
            l.startswith("**date:")
            or l.startswith("**status:")
            or l.startswith("**scope:")
            or l.startswith("**requirements source:")
            or l in {"---", "___"}
        )

    plan_lines = [ln.strip() for ln in plan_text.splitlines() if ln.strip()]
    heading = next((ln[2:].strip() for ln in plan_lines if ln.startswith("# ")), None)

    desc = None
    for ln in plan_lines:
        if ln.startswith("#"):
            continue
        if is_metadata_line(ln):
            continue
        if len(ln) < 20:
            continue
        desc = ln
        break
    if heading and desc:
        description_value = f"{heading}. {desc[:220]}"
    elif heading:
        description_value = heading
    else:
        description_value = desc
    if description_value:
        manifest_data["spec"]["project"]["description"] = description_value[:300]
        add_inference(
            "spec.project.description",
            description_value[:300],
            "plan:heading_plus_first_meaningful_line",
            0.9,
        )

    lowered = text.lower()
    crit = None
    explicit_crit = re.search(
        r"(?:criticality|severity|priority)\s*[:\-]?\s*(critical|high|medium|low)",
        lowered,
    )
    if explicit_crit:
        crit = explicit_crit.group(1)
    elif re.search(r"\bp1\b|\bp0\b|\bsev-?1\b|\bcritical\b", lowered):
        crit = "high"
    elif re.search(r"\bp2\b|\bhigh\b", lowered):
        crit = "high"
    elif re.search(r"\bp3\b|\bmedium\b", lowered):
        crit = "medium"
    elif re.search(r"\bp4\b", lowered):
        crit = "low"
    if crit:
        manifest_data["spec"]["business"]["criticality"] = crit
        add_inference(
            "spec.business.criticality",
            crit,
            "plan+requirements:contextual_criticality_detection",
            0.82,
        )

    availability_match = re.search(
        r"(\d{2,3}(?:\.\d+)?)\s*%?\s*(?:availability|uptime|slo)",
        lowered,
    )
    if availability_match:
        availability = availability_match.group(1)
        manifest_data["spec"]["requirements"]["availability"] = availability
        add_inference("spec.requirements.availability", availability, "requirements:regex", 0.8)

    latency_match = re.search(
        r"(?:p99|99th|latency)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds)",
        lowered,
    )
    if latency_match:
        latency = f"{latency_match.group(1)}{latency_match.group(2)}"
        manifest_data["spec"]["requirements"]["latencyP99"] = latency
        add_inference("spec.requirements.latencyP99", latency, "requirements:regex", 0.75)

    throughput_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:rps|req/s|requests/s|qps)", lowered)
    if throughput_match:
        throughput = f"{throughput_match.group(1)}rps"
        manifest_data["spec"]["requirements"]["throughput"] = throughput
        add_inference("spec.requirements.throughput", throughput, "requirements:regex", 0.72)

    eb_match = re.search(r"error\s*budget[^0-9]{0,20}(\d+(?:\.\d+)?)\s*%?", lowered)
    if eb_match:
        error_budget = eb_match.group(1)
        manifest_data["spec"]["requirements"]["errorBudget"] = error_budget
        add_inference("spec.requirements.errorBudget", error_budget, "requirements:regex", 0.7)

    channels = sorted(set(re.findall(r"(#[-a-zA-Z0-9_]+)", text)))
    if channels:
        manifest_data["spec"]["observability"]["alertChannels"] = channels
        add_inference("spec.observability.alertChannels", channels, "plan+requirements:channel_extraction", 0.7)

    owner_match = re.search(r"(?:owner|team)[:\s]+([a-zA-Z0-9_-]+)", lowered)
    if owner_match:
        owner = owner_match.group(1)
        manifest_data["spec"]["business"]["owner"] = owner
        manifest_data["metadata"]["owners"][0]["team"] = owner
        add_inference("spec.business.owner", owner, "plan+requirements:regex", 0.65)

    if project_root:
        target_name = Path(project_root).name.replace("_", "-")
        manifest_data["spec"]["targets"][0]["name"] = target_name
        add_inference("spec.targets[0].name", target_name, "project_root:basename", 0.8)

    extracted_risks = [ln[:180] for ln in plan_lines if re.search(r"\b(risk|blocker)\b", ln.lower())]
    if extracted_risks:
        manifest_data["spec"]["risks"] = [
            {
                "type": _infer_risk_type(r),
                "description": r,
                "priority": "P2",
                "mitigation": "Define mitigation in implementation plan",
            }
            for r in extracted_risks[:3]
        ]
        add_inference("spec.risks", manifest_data["spec"]["risks"], "plan:risk_line_extraction", 0.65)

    guardrails = []
    for ln in plan_lines:
        l = ln.lower()
        if l.startswith("- do not ") or l.startswith("- keep "):
            guardrails.append(ln.lstrip("- ").strip())
    if guardrails:
        manifest_data["guidance"]["constraints"] = [
            {
                "id": f"C-PLAN-{idx+1:03d}",
                "rule": g,
                "severity": "blocking",
                "rationale": "Imported from implementation plan guardrails",
                "appliesTo": [],
            }
            for idx, g in enumerate(guardrails[:5])
        ]
        add_inference(
            "guidance.constraints",
            [c["id"] for c in manifest_data["guidance"]["constraints"]],
            "plan:guardrail_to_constraint",
            0.88,
        )

    goals = []
    in_goals = False
    in_execution_scope = False
    for ln in plan_lines:
        lowered_line = ln.lower()
        if lowered_line.startswith("### goals"):
            in_goals = True
            in_execution_scope = False
            continue
        if lowered_line.startswith("### execution scope"):
            in_execution_scope = True
            in_goals = False
            continue
        if (in_goals or in_execution_scope) and ln.startswith("### "):
            in_goals = False
            in_execution_scope = False
        if (in_goals or in_execution_scope) and ln.startswith("- "):
            goals.append(ln.lstrip("- ").strip())
    if goals:
        objectives = []
        for idx, goal in enumerate(goals[:3]):
            obj = {
                "id": f"OBJ-PLAN-{idx+1:03d}",
                "description": goal[:180],
                "keyResults": [
                    {
                        "metricKey": "availability",
                        "unit": "%",
                        "target": float(manifest_data["spec"]["requirements"].get("availability", "99.9")),
                        "targetOperator": "gte",
                        "window": "30d",
                    }
                ],
            }
            objectives.append(obj)
        manifest_data["strategy"]["objectives"] = objectives
        add_inference(
            "strategy.objectives",
            [o["id"] for o in objectives],
            "plan:goals_or_execution_scope_extraction",
            0.8,
        )

    # ── Requirement ID extraction (REQ-N, FR-N, NFR-N) ────────────
    all_req_ids = sorted(set(_REQ_ID_PATTERN.findall(text)))
    if all_req_ids:
        add_inference(
            "requirement_ids",
            all_req_ids,
            "plan+requirements:req_id_extraction",
            0.85,
        )

    # ── Tactics extraction with phase-accumulator (enriched) ────────
    tactics: List[Dict[str, Any]] = []
    obj_ids = [o["id"] for o in manifest_data["strategy"].get("objectives", [])]

    # Phase-accumulator: collect metadata lines between headings
    current_heading: Optional[str] = None
    current_meta: Dict[str, Any] = {}
    in_phases = False
    in_milestones = False
    in_action_items = False
    deliverable_lines: List[str] = []
    collecting_deliverables = False

    def _flush_tactic(heading_text: str, meta: Dict[str, Any]) -> None:
        """Flush accumulated heading + metadata into a tactic dict."""
        if len(heading_text) <= 10 or len(tactics) >= 15:
            return
        tac_id = f"TAC-PLAN-{len(tactics)+1:03d}"
        tactic: Dict[str, Any] = {
            "id": tac_id,
            "description": heading_text[:180],
            "status": "planned",
            "linkedObjectives": obj_ids[:1] if obj_ids else [],
        }
        # Enrichment fields from inline metadata
        if meta.get("satisfies"):
            tactic["satisfies"] = meta["satisfies"]
        if meta.get("depends_on"):
            tactic["dependsOn"] = meta["depends_on"]
        if meta.get("repo"):
            tactic["repo"] = meta["repo"]
        if meta.get("deliverables"):
            tactic["deliverables"] = meta["deliverables"]
        tactics.append(tactic)

    for ln in plan_lines:
        lowered_line = ln.lower()

        # Detect phase/milestone headings (## Phase N: ...)
        phase_match = re.match(r"^#{2,3}\s*(phase|milestone|action|step|task)\b", lowered_line)
        if phase_match:
            # Flush previous phase if any
            if current_heading is not None:
                if deliverable_lines:
                    current_meta["deliverables"] = {
                        "summary": "; ".join(deliverable_lines[:5]),
                        "file_count": len(deliverable_lines),
                    }
                _flush_tactic(current_heading, current_meta)

            heading_text = re.sub(r"^#{2,3}\s*", "", ln).strip()
            current_heading = heading_text
            current_meta = {}
            deliverable_lines = []
            collecting_deliverables = False
            in_phases = True
            in_milestones = False
            in_action_items = False
            continue

        # Collect metadata lines between headings
        if current_heading is not None and in_phases:
            # Satisfies:
            m = _SATISFIES_PATTERN.match(ln)
            if m:
                raw = m.group(1).strip()
                # Extract REQ-IDs from the Satisfies line
                ids = _REQ_ID_PATTERN.findall(raw)
                current_meta["satisfies"] = ids if ids else [raw]
                continue
            # Depends on:
            m = _DEPENDS_ON_PATTERN.match(ln)
            if m:
                current_meta["depends_on"] = m.group(1).strip()
                continue
            # Repo:
            m = _REPO_PATTERN.match(ln)
            if m:
                current_meta["repo"] = m.group(1).strip()
                continue
            # Deliverables: (start collecting)
            m = _DELIVERABLES_PATTERN.match(ln)
            if m:
                inline = m.group(1).strip()
                if inline:
                    deliverable_lines.append(inline)
                collecting_deliverables = True
                continue
            # Validation: (stop deliverable collection)
            m = _VALIDATION_PATTERN.match(ln)
            if m:
                collecting_deliverables = False
                continue
            # Checklist items under Deliverables
            if collecting_deliverables:
                cm = _CHECKLIST_PATTERN.match(ln)
                if cm:
                    deliverable_lines.append(cm.group(2).strip())
                    continue
                # A non-indented non-empty line that isn't a checklist ends collection
                if ln.strip() and not ln.startswith(" ") and not ln.startswith("-"):
                    collecting_deliverables = False

        # Other section headings (milestones, action items, deliverables sections)
        if lowered_line.startswith("### milestones"):
            in_milestones = True
            in_phases = False
            in_action_items = False
            continue
        if lowered_line.startswith("### action items") or lowered_line.startswith("### deliverables"):
            in_action_items = True
            in_phases = False
            in_milestones = False
            continue
        # Reset on new top-level heading
        if (in_phases or in_milestones or in_action_items) and ln.startswith("## "):
            # Flush current phase before resetting
            if current_heading is not None and in_phases:
                if deliverable_lines:
                    current_meta["deliverables"] = {
                        "summary": "; ".join(deliverable_lines[:5]),
                        "file_count": len(deliverable_lines),
                    }
                _flush_tactic(current_heading, current_meta)
                current_heading = None
                current_meta = {}
                deliverable_lines = []
                collecting_deliverables = False
            in_phases = False
            in_milestones = False
            in_action_items = False
        # Bullet items under milestones/action items
        if (in_milestones or in_action_items) and ln.startswith("- "):
            item_text = ln.lstrip("- ").strip()
            if len(item_text) > 10 and len(tactics) < 15:
                tac_id = f"TAC-PLAN-{len(tactics)+1:03d}"
                tactics.append({
                    "id": tac_id,
                    "description": item_text[:180],
                    "status": "planned",
                    "linkedObjectives": obj_ids[:1] if obj_ids else [],
                })

    # Flush final phase
    if current_heading is not None:
        if deliverable_lines:
            current_meta["deliverables"] = {
                "summary": "; ".join(deliverable_lines[:5]),
                "file_count": len(deliverable_lines),
            }
        _flush_tactic(current_heading, current_meta)

    # ── Merge plan_analysis data (Option 3 enrichment) ─────────────
    if plan_analysis and tactics:
        pa_phases = plan_analysis.get("phase_metadata", [])
        trace_matrix = plan_analysis.get("traceability_matrix", {})

        # Build a lookup by phase heading prefix for fuzzy matching
        for pa_phase in pa_phases:
            pa_heading = pa_phase.get("heading", "").lower()
            for tactic in tactics:
                tac_desc = tactic["description"].lower()
                # Match if the tactic description contains the phase heading or vice versa
                if pa_heading and (pa_heading in tac_desc or tac_desc in pa_heading):
                    # Higher-confidence data from plan_analysis overrides inline
                    if pa_phase.get("satisfies") and not tactic.get("satisfies"):
                        tactic["satisfies"] = pa_phase["satisfies"]
                    if pa_phase.get("depends_on") and not tactic.get("dependsOn"):
                        tactic["dependsOn"] = pa_phase["depends_on"]
                    if pa_phase.get("repo") and not tactic.get("repo"):
                        tactic["repo"] = pa_phase["repo"]
                    if pa_phase.get("deliverables") and not tactic.get("deliverables"):
                        tactic["deliverables"] = pa_phase["deliverables"]
                    break

    if tactics:
        manifest_data["strategy"]["tactics"] = tactics
        enriched_count = sum(
            1 for t in tactics
            if t.get("satisfies") or t.get("dependsOn") or t.get("repo") or t.get("deliverables")
        )
        add_inference(
            "strategy.tactics",
            [t["id"] for t in tactics],
            "plan:phase_milestone_extraction",
            0.7,
        )
        if enriched_count > 0:
            add_inference(
                "strategy.tactics.enrichment",
                {"enriched_count": enriched_count, "total": len(tactics)},
                "plan:phase_metadata_enrichment" if not plan_analysis else "plan_analysis:merge",
                0.8 if plan_analysis else 0.7,
            )

    if emit_guidance_questions:
        questions = [ln for ln in plan_lines if ln.endswith("?")]
        if questions:
            manifest_data["guidance"]["questions"] = [
                {
                    "id": f"Q-{idx+1:03d}",
                    "question": q[:220],
                    "status": "open",
                    "priority": "medium",
                }
                for idx, q in enumerate(questions[:5])
            ]
            add_inference(
                "guidance.questions",
                [q["id"] for q in manifest_data["guidance"]["questions"]],
                "plan:question_line_extraction",
                0.6,
            )

    # ── URL extraction for metadata.links ──────────────────────────
    url_pattern = re.compile(r"(https?://[^\s\)\]\>\"']+)")
    found_urls = url_pattern.findall(text)
    links_updated = False
    for url in found_urls:
        url_lower = url.lower()
        if "github.com" in url_lower or "gitlab.com" in url_lower or "bitbucket.org" in url_lower:
            manifest_data["metadata"]["links"]["repo"] = url
            links_updated = True
        elif "jira" in url_lower or "linear" in url_lower or "atlassian.net" in url_lower:
            manifest_data["metadata"]["links"]["tracker"] = url
            links_updated = True
        elif "wiki" in url_lower or "confluence" in url_lower or "notion" in url_lower:
            manifest_data["metadata"]["links"]["docs"] = url
            links_updated = True
        elif "grafana" in url_lower or "dashboard" in url_lower:
            manifest_data["metadata"]["links"]["dashboard"] = url
            links_updated = True
    if links_updated:
        add_inference(
            "metadata.links",
            manifest_data["metadata"]["links"],
            "plan+requirements:url_extraction",
            0.7,
        )

    # ── Capability index matching (REQ-CAP-003) ────────────────────
    matched_caps: List[str] = []
    try:
        from contextcore.utils.capability_index import (
            load_capability_index,
            match_triggers,
            match_patterns,
            match_principles,
        )
        cap_index_dir = _find_capability_index_dir(project_root)
        cap_index = load_capability_index(cap_index_dir)
        if not cap_index.is_empty:
            caps = match_triggers(text, cap_index.capabilities)
            matched_caps = [c.capability_id for c in caps]
            if matched_caps:
                matched_pats = match_patterns(matched_caps, cap_index.patterns)
                matched_prins = match_principles(matched_caps, cap_index.principles)

                # Inject matched principles as advisory constraints
                guidance = manifest_data.setdefault("guidance", {})
                if matched_prins:
                    constraints = guidance.get("constraints", []) or []
                    existing_ids = {c.get("id") for c in constraints}
                    for idx, prin in enumerate(matched_prins, start=1):
                        cid = f"C-CAP-{prin.id}"
                        if cid not in existing_ids:
                            constraints.append({
                                "id": cid,
                                "rule": prin.principle,
                                "severity": "advisory",
                                "source": f"contextcore.agent.yaml#{prin.id}",
                            })
                    guidance["constraints"] = constraints

                # Inject matched patterns as preferences
                if matched_pats:
                    preferences = guidance.get("preferences", []) or []
                    existing_ids = {p.get("id") for p in preferences}
                    for idx, pat in enumerate(matched_pats, start=1):
                        pid = f"P-CAP-{pat.pattern_id}"
                        if pid not in existing_ids:
                            preferences.append({
                                "id": pid,
                                "description": pat.summary,
                                "source": f"contextcore.agent.yaml#{pat.pattern_id}",
                            })
                    guidance["preferences"] = preferences

                # Record inferences
                for cap_id in matched_caps:
                    add_inference(
                        "capability_match",
                        cap_id,
                        "capability_index:trigger_match",
                        0.75,
                    )
    except Exception:
        logger.debug("Capability index not available, skipping matching")

    # ── Capability-aware question generation (REQ-CAP-008) ─────────
    if emit_guidance_questions and matched_caps is not None:
        _CAP_GAP_QUESTIONS = [
            {
                "prefix": "contextcore.contract.",
                "question": "Which context propagation contracts are needed for this project's boundary validation?",
            },
            {
                "prefix": "contextcore.a2a.",
                "question": "Will this project require A2A governance gates for pipeline exports?",
            },
            {
                "prefix": "contextcore.handoff.",
                "question": "Does this project involve agent-to-agent handoffs that need typed contracts?",
            },
        ]

        cap_questions: List[Dict[str, Any]] = []
        for gap_def in _CAP_GAP_QUESTIONS:
            prefix = gap_def["prefix"]
            has_match = any(c.startswith(prefix) for c in matched_caps)
            if not has_match:
                cap_questions.append(gap_def)

        if cap_questions:
            guidance = manifest_data.setdefault("guidance", {})
            existing_questions = guidance.get("questions", []) or []
            for idx, cq in enumerate(cap_questions[:3], start=1):
                existing_questions.append({
                    "id": f"Q-CAP-{idx}",
                    "question": cq["question"],
                    "status": "open",
                    "priority": "medium",
                    "source": "capability_gap_analysis",
                })
            guidance["questions"] = existing_questions
            add_inference(
                "guidance.questions.capability_gaps",
                [f"Q-CAP-{i}" for i in range(1, len(cap_questions[:3]) + 1)],
                "capability_index:gap_analysis",
                0.7,
            )

    core_inferred_fields = {
        item["field_path"] for item in inferences
        if item["field_path"] in {
            "spec.project.description",
            "spec.business.criticality",
            "spec.requirements.availability",
            "spec.targets[0].name",
            "spec.business.owner",
            "guidance.constraints",
            "strategy.objectives",
        }
    }
    if len(core_inferred_fields) < 3:
        warnings.append(
            "Low-confidence init-from-plan: fewer than 3 core fields were inferred from inputs."
        )

    # ── Downstream readiness assessment ──────────────────────────
    # Predict how well this manifest will perform in export and plan ingestion
    thresholds = _load_gate_thresholds(project_root)
    readiness_score = 0
    readiness_checks: List[Dict[str, Any]] = []

    # Check if requirements are populated (drives derivation rules)
    reqs = manifest_data.get("spec", {}).get("requirements", {})
    populated_reqs = [k for k, v in reqs.items() if v and str(v) not in ("", "0")]
    readiness_checks.append({
        "check": "requirements_populated",
        "status": "pass" if len(populated_reqs) >= 3 else "warn",
        "detail": f"{len(populated_reqs)}/4 requirement fields populated ({', '.join(populated_reqs)})",
    })
    readiness_score += min(len(populated_reqs), 4) * 5

    # Check if targets are defined (drives artifact generation)
    targets = manifest_data.get("spec", {}).get("targets", [])
    readiness_checks.append({
        "check": "targets_defined",
        "status": "pass" if targets else "fail",
        "detail": f"{len(targets)} target(s) defined",
    })
    readiness_score += 10 if targets else 0

    # Check if observability config is present (drives alert channels, sampling)
    obs = manifest_data.get("spec", {}).get("observability", {})
    has_channels = bool(obs.get("alertChannels"))
    readiness_checks.append({
        "check": "observability_configured",
        "status": "pass" if has_channels else "warn",
        "detail": f"alertChannels={'yes' if has_channels else 'empty'}, logLevel={obs.get('logLevel', 'unset')}",
    })
    readiness_score += 10 if has_channels else 0

    # Check if objectives exist (drives export objectives enrichment)
    objectives = manifest_data.get("strategy", {}).get("objectives", [])
    readiness_checks.append({
        "check": "objectives_defined",
        "status": "pass" if objectives else "warn",
        "detail": f"{len(objectives)} objective(s) defined",
    })
    readiness_score += 10 if objectives else 0

    # Check if guidance has constraints or questions (drives open_questions export)
    guidance = manifest_data.get("guidance", {})
    has_constraints = bool(guidance.get("constraints"))
    has_questions = bool(guidance.get("questions"))
    readiness_checks.append({
        "check": "guidance_populated",
        "status": "pass" if (has_constraints or has_questions) else "warn",
        "detail": f"constraints={len(guidance.get('constraints', []))}, questions={len(guidance.get('questions', []))}",
    })
    readiness_score += 10 if has_constraints else 0
    readiness_score += 5 if has_questions else 0

    # Check if risks are defined (drives runbook derivation)
    risks = manifest_data.get("spec", {}).get("risks", [])
    readiness_checks.append({
        "check": "risks_defined",
        "status": "pass" if risks else "warn",
        "detail": f"{len(risks)} risk(s) defined",
    })
    readiness_score += 10 if risks else 0

    # Check capability coverage (REQ-CAP-003)
    readiness_checks.append({
        "check": "capability_coverage",
        "status": "pass" if matched_caps else "warn",
        "detail": f"{len(matched_caps)} capabilities matched from index",
    })
    if matched_caps:
        readiness_score += 5

    # Estimate artifact coverage
    artifact_types = ["dashboard", "prometheus_rule", "loki_rule", "service_monitor",
                      "slo_definition", "notification_policy", "runbook"]
    estimated_artifacts = len(artifact_types) * len(targets) if targets else 0
    readiness_checks.append({
        "check": "estimated_artifact_coverage",
        "status": "pass" if estimated_artifacts > 0 else "warn",
        "detail": f"~{estimated_artifacts} artifacts ({len(artifact_types)} types x {len(targets)} targets)",
    })

    # ── Contract layer readiness (lifecycle + domains) ──────────
    text_lower = text.lower()
    lifecycle_layers = ["preflight"]  # always recommended
    if any(kw in text_lower for kw in ("context", "field", "metadata", "propagat")):
        lifecycle_layers.append("runtime")
        lifecycle_layers.append("postexec")
    if any(kw in text_lower for kw in ("monitor", "observ", "alert", "metric", "dashboard")):
        lifecycle_layers.append("observability")
    if any(kw in text_lower for kw in ("ci", "cd", "pipeline", "regression", "test")):
        lifecycle_layers.append("regression")

    contract_domains_detected = ["propagation", "schema_compat"]  # always present (implemented)

    downstream_readiness = {
        "score": min(readiness_score, 100),
        "verdict": (
            "ready" if readiness_score >= thresholds["verdict_ready"]
            else "needs_enrichment" if readiness_score >= thresholds["verdict_needs_enrichment"]
            else "insufficient"
        ),
        "checks": readiness_checks,
        "estimated_artifact_count": estimated_artifacts,
        "a2a_gate_readiness": {
            "checksum_chain": "ready" if len(populated_reqs) >= thresholds["gate_checksum_chain_min_reqs"] else "at_risk",
            "derivation_rules": "ready" if len(populated_reqs) >= thresholds["gate_derivation_rules_min_reqs"] else "at_risk",
            "design_calibration": "ready" if targets else "blocked",
            "gap_parity": "ready" if targets else "blocked",
        },
        "contract_layer_readiness": {
            "lifecycle_layers": lifecycle_layers,
            "contract_domains": contract_domains_detected,
        },
    }

    result: Dict[str, Any] = {
        "manifest_data": manifest_data,
        "inferences": inferences,
        "warnings": warnings,
        "core_inferred_count": len(core_inferred_fields),
        "downstream_readiness": downstream_readiness,
    }
    if matched_caps:
        result["matched_capabilities"] = matched_caps
    return result
