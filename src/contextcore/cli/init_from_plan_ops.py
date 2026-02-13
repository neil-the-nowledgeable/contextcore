"""
Helpers for `contextcore manifest init-from-plan`.

Keeps CLI wiring in `manifest.py` thin by isolating template construction
and plan/requirements inference logic.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


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
            "questions": [],
        },
        "insights": [],
    }


def infer_init_from_plan(
    manifest_data: Dict[str, Any],
    plan_text: str,
    requirements_text: str,
    project_root: Optional[str],
    emit_guidance_questions: bool,
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
                "type": "availability",
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
        manifest_data["strategy"]["objectives"] = [
            {
                "id": "OBJ-PLAN-001",
                "description": goals[0][:180],
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
        ]
        add_inference(
            "strategy.objectives[0].description",
            goals[0][:180],
            "plan:goals_or_execution_scope_extraction",
            0.8,
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

    core_inferred_fields = {
        item["field_path"] for item in inferences
        if item["field_path"] in {
            "spec.project.description",
            "spec.business.criticality",
            "spec.requirements.availability",
            "spec.targets[0].name",
            "spec.business.owner",
            "guidance.constraints",
            "strategy.objectives[0].description",
        }
    }
    if len(core_inferred_fields) < 3:
        warnings.append(
            "Low-confidence init-from-plan: fewer than 3 core fields were inferred from inputs."
        )

    return {
        "manifest_data": manifest_data,
        "inferences": inferences,
        "warnings": warnings,
        "core_inferred_count": len(core_inferred_fields),
    }
