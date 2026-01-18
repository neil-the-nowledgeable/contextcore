# Phase 1: Quick Wins Implementation Plan

**Estimated Effort**: Hours per feature
**Total Phase Duration**: 1-2 days
**Dependencies**: Existing operator.py, CLI infrastructure

---

## Overview

Phase 1 focuses on high-value, low-effort enhancements that leverage existing ProjectContext metadata with minimal code changes. These features enhance the operator's output and add new CLI commands.

---

## Feature 1.1: Alert Annotation Enrichment

**Effort**: 2-4 hours
**Files to Modify**: `src/contextcore/operator.py`

### Goal

Enrich generated PrometheusRule alerts with contextual information from ProjectContext, giving on-call engineers immediate access to architectural decisions, known risks, and runbooks.

### Implementation Steps

1. **Modify `generate_prometheus_rules()` function** (operator.py:273-373)

```python
def generate_prometheus_rules(
    name: str,
    namespace: str,
    spec: Dict[str, Any],
    labels: Dict[str, str],
) -> Dict[str, Any]:
    """Generate PrometheusRule with enriched annotations."""

    # Extract context for annotations
    project_id = spec.get("project", {}).get("id", name) if isinstance(spec.get("project"), dict) else spec.get("project", name)

    # Build enriched annotations
    base_annotations = {
        "summary": f"{{{{ $labels.service }}}} SLO violation",
        "description": f"Service {{{{ $labels.service }}}} (project {project_id}) requires attention",
    }

    # Add ADR reference if available
    design = spec.get("design", {})
    if design.get("adr"):
        base_annotations["architecture_decision"] = design["adr"]

    # Add runbook if available
    observability = spec.get("observability", {})
    if observability.get("runbook"):
        base_annotations["runbook_url"] = observability["runbook"]

    # Add business context
    business = spec.get("business", {})
    if business.get("owner"):
        base_annotations["owner"] = business["owner"]
    if business.get("criticality"):
        base_annotations["business_criticality"] = business["criticality"]

    # Add relevant risks as annotation
    risks = spec.get("risks", [])
    if risks:
        risk_summary = "; ".join([
            f"{r.get('type', 'unknown')}: {r.get('description', 'N/A')[:50]}"
            for r in risks[:3]  # Limit to top 3
        ])
        base_annotations["known_risks"] = risk_summary

    # Generate rules with enriched annotations
    # ... rest of existing implementation using base_annotations
```

2. **Add mitigation hints to alerts**

```python
def _get_mitigation_for_risk_type(risk_type: str) -> str:
    """Get default mitigation hint for risk type."""
    mitigations = {
        "availability": "Check pod health, recent deployments, upstream dependencies",
        "security": "Review access logs, check for unauthorized access patterns",
        "data-integrity": "Verify database consistency, check replication lag",
        "compliance": "Escalate to compliance team, preserve audit logs",
    }
    return mitigations.get(risk_type, "Review runbook for specific guidance")
```

### Acceptance Criteria

- [ ] Generated PrometheusRule includes `architecture_decision` annotation when `design.adr` is set
- [ ] Generated PrometheusRule includes `runbook_url` annotation when `observability.runbook` is set
- [ ] Generated PrometheusRule includes `owner` and `business_criticality` from business context
- [ ] Generated PrometheusRule includes `known_risks` summary from risks array
- [ ] Existing functionality unchanged for ProjectContexts without these fields

### Test Cases

```python
def test_alert_enrichment_with_adr():
    spec = {
        "project": {"id": "test-project"},
        "design": {"adr": "ADR-015"},
        "business": {"owner": "platform-team", "criticality": "critical"},
    }
    rules = generate_prometheus_rules("test", "default", spec, {})
    alert = rules["spec"]["groups"][1]["rules"][0]
    assert "architecture_decision" in alert["annotations"]
    assert alert["annotations"]["architecture_decision"] == "ADR-015"

def test_alert_enrichment_with_risks():
    spec = {
        "project": {"id": "test-project"},
        "risks": [
            {"type": "security", "description": "API key exposure risk"},
            {"type": "availability", "description": "Single point of failure"},
        ],
    }
    rules = generate_prometheus_rules("test", "default", spec, {})
    alert = rules["spec"]["groups"][1]["rules"][0]
    assert "known_risks" in alert["annotations"]
    assert "security" in alert["annotations"]["known_risks"]
```

---

## Feature 1.2: Cost Attribution Labels

**Effort**: 1-2 hours
**Files to Modify**: `src/contextcore/operator.py`

### Goal

Automatically apply cost attribution labels to all generated resources (ServiceMonitor, PrometheusRule, Dashboard ConfigMap) enabling cloud cost tracking by business unit.

### Implementation Steps

1. **Create cost label generator function**

```python
def generate_cost_labels(spec: Dict[str, Any]) -> Dict[str, str]:
    """Generate labels for cost attribution from business context."""
    labels = {}

    business = spec.get("business", {})

    if business.get("costCenter"):
        labels["cost-center"] = business["costCenter"]

    if business.get("owner"):
        labels["owner"] = business["owner"]

    if business.get("value"):
        labels["business-value"] = business["value"]

    if business.get("criticality"):
        labels["criticality"] = business["criticality"]

    # Add project reference
    project = spec.get("project", {})
    if isinstance(project, dict) and project.get("id"):
        labels["project-id"] = project["id"]
    elif isinstance(project, str):
        labels["project-id"] = project

    return labels
```

2. **Apply cost labels in each generator function**

```python
def generate_service_monitor(...) -> Dict[str, Any]:
    # ... existing code ...

    # Add cost labels
    cost_labels = generate_cost_labels(spec)
    metadata_labels.update(cost_labels)

    # ... rest of function
```

3. **Apply to all three generators**
   - `generate_service_monitor()` - line 215
   - `generate_prometheus_rules()` - line 273
   - `generate_grafana_dashboard()` - line 376

### Acceptance Criteria

- [ ] All generated resources include `cost-center` label when `business.costCenter` is set
- [ ] All generated resources include `owner` label when `business.owner` is set
- [ ] All generated resources include `business-value` label when `business.value` is set
- [ ] All generated resources include `criticality` label when `business.criticality` is set
- [ ] Labels are valid Kubernetes label values (sanitized if needed)

### Test Cases

```python
def test_cost_labels_applied_to_service_monitor():
    spec = {
        "project": {"id": "checkout"},
        "business": {
            "costCenter": "CC-1234",
            "owner": "commerce-team",
            "value": "revenue-primary",
            "criticality": "critical",
        },
    }
    sm = generate_service_monitor("test", "default", spec, {})
    labels = sm["metadata"]["labels"]
    assert labels["cost-center"] == "CC-1234"
    assert labels["owner"] == "commerce-team"
    assert labels["business-value"] == "revenue-primary"
    assert labels["criticality"] == "critical"
```

---

## Feature 1.3: Runbook Generation CLI

**Effort**: 3-4 hours
**Files to Create**: `src/contextcore/generators/runbook.py`
**Files to Modify**: `src/contextcore/cli.py`

### Goal

Add `contextcore generate runbook` command that produces a Markdown operational runbook from ProjectContext metadata.

### Implementation Steps

1. **Create runbook generator module**

```python
# src/contextcore/generators/runbook.py
"""Generate operational runbooks from ProjectContext."""

from typing import Optional
from datetime import datetime

def generate_runbook(
    project_id: str,
    spec: dict,
    output_format: str = "markdown"
) -> str:
    """Generate operational runbook from ProjectContext spec."""

    sections = []

    # Header
    sections.append(f"# {project_id} Operational Runbook")
    sections.append(f"\n_Generated: {datetime.now().isoformat()}_\n")
    sections.append("_Source: ProjectContext CRD_\n")

    # Service Overview
    sections.append("## Service Overview\n")
    sections.append(_generate_overview_section(spec))

    # SLOs
    if spec.get("requirements"):
        sections.append("## Service Level Objectives\n")
        sections.append(_generate_slo_section(spec["requirements"]))

    # Known Risks
    if spec.get("risks"):
        sections.append("## Known Risks & Mitigations\n")
        sections.append(_generate_risks_section(spec["risks"]))

    # Kubernetes Resources
    if spec.get("targets"):
        sections.append("## Kubernetes Resources\n")
        sections.append(_generate_resources_section(spec["targets"]))

    # Common Procedures
    sections.append("## Common Procedures\n")
    sections.append(_generate_procedures_section(spec))

    # Escalation
    sections.append("## Escalation\n")
    sections.append(_generate_escalation_section(spec))

    return "\n".join(sections)


def _generate_overview_section(spec: dict) -> str:
    """Generate service overview section."""
    project = spec.get("project", {})
    business = spec.get("business", {})

    lines = []
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")

    if isinstance(project, dict):
        lines.append(f"| Project ID | {project.get('id', 'N/A')} |")
        if project.get("epic"):
            lines.append(f"| Epic | {project['epic']} |")
    else:
        lines.append(f"| Project ID | {project} |")

    if business:
        lines.append(f"| Owner | {business.get('owner', 'N/A')} |")
        lines.append(f"| Criticality | {business.get('criticality', 'N/A')} |")
        lines.append(f"| Business Value | {business.get('value', 'N/A')} |")
        if business.get("costCenter"):
            lines.append(f"| Cost Center | {business['costCenter']} |")

    return "\n".join(lines) + "\n"


def _generate_slo_section(requirements: dict) -> str:
    """Generate SLO section."""
    lines = []
    lines.append("| Metric | Target | Alert Threshold |")
    lines.append("|--------|--------|-----------------|")

    if requirements.get("availability"):
        threshold = float(requirements["availability"]) - 0.1
        lines.append(f"| Availability | {requirements['availability']}% | < {threshold}% |")

    if requirements.get("latencyP50"):
        lines.append(f"| Latency P50 | {requirements['latencyP50']} | > 2x target |")

    if requirements.get("latencyP99"):
        lines.append(f"| Latency P99 | {requirements['latencyP99']} | > 1.5x target |")

    if requirements.get("errorBudget"):
        lines.append(f"| Error Budget | {requirements['errorBudget']}% monthly | Exhausted |")

    if requirements.get("throughput"):
        lines.append(f"| Throughput | {requirements['throughput']} | < 80% capacity |")

    return "\n".join(lines) + "\n"


def _generate_risks_section(risks: list) -> str:
    """Generate risks section."""
    lines = []
    lines.append("| Risk Type | Description | Priority | Mitigation |")
    lines.append("|-----------|-------------|----------|------------|")

    for risk in risks:
        lines.append(
            f"| {risk.get('type', 'N/A')} | "
            f"{risk.get('description', 'N/A')[:50]} | "
            f"{risk.get('priority', 'N/A')} | "
            f"{risk.get('mitigation', 'See runbook')[:30]} |"
        )

    return "\n".join(lines) + "\n"


def _generate_resources_section(targets: list) -> str:
    """Generate Kubernetes resources section."""
    lines = []
    lines.append("```bash")
    lines.append("# Check resource status")

    for target in targets:
        ns = target.get("namespace", "default")
        kind = target.get("kind", "").lower()
        name = target.get("name", "")
        lines.append(f"kubectl get {kind} {name} -n {ns}")

    lines.append("")
    lines.append("# View logs")
    if targets:
        first = targets[0]
        lines.append(f"kubectl logs -l app={first.get('name', 'app')} -n {first.get('namespace', 'default')} --tail=100")

    lines.append("```")
    return "\n".join(lines) + "\n"


def _generate_procedures_section(spec: dict) -> str:
    """Generate common procedures section."""
    targets = spec.get("targets", [])
    business = spec.get("business", {})

    lines = []

    # Restart procedure
    lines.append("### Restart Service\n")
    if targets:
        target = targets[0]
        ns = target.get("namespace", "default")
        kind = target.get("kind", "deployment").lower()
        name = target.get("name", "service")
        lines.append("```bash")
        lines.append(f"kubectl rollout restart {kind}/{name} -n {ns}")
        lines.append(f"kubectl rollout status {kind}/{name} -n {ns} --timeout=5m")
        lines.append("```\n")

    # Scale procedure for critical services
    if business.get("criticality") in ["critical", "high"]:
        lines.append("### Emergency Scale Up\n")
        lines.append("```bash")
        if targets:
            lines.append(f"kubectl scale deployment/{targets[0].get('name', 'service')} --replicas=5 -n {targets[0].get('namespace', 'default')}")
        lines.append("```")
        lines.append("\n**Note**: Scale back down after incident resolution.\n")

    # Debug procedure
    lines.append("### Debug Connectivity\n")
    lines.append("```bash")
    lines.append("# Check endpoints")
    if targets:
        for t in targets:
            if t.get("kind") == "Service":
                lines.append(f"kubectl get endpoints {t.get('name')} -n {t.get('namespace', 'default')}")
    lines.append("")
    lines.append("# Test from inside cluster")
    lines.append("kubectl run debug --rm -it --image=busybox -- sh")
    lines.append("```\n")

    return "\n".join(lines)


def _generate_escalation_section(spec: dict) -> str:
    """Generate escalation section."""
    business = spec.get("business", {})
    observability = spec.get("observability", {})

    lines = []

    lines.append(f"| Level | Contact | When |")
    lines.append(f"|-------|---------|------|")
    lines.append(f"| L1 | On-call engineer | Initial response |")

    if business.get("owner"):
        lines.append(f"| L2 | {business['owner']} | Unresolved after 30min |")

    lines.append(f"| L3 | Platform team | Infrastructure issues |")

    if business.get("stakeholders"):
        stakeholders = ", ".join(business["stakeholders"][:2])
        lines.append(f"| Exec | {stakeholders} | Customer impact |")

    lines.append("")

    if observability.get("runbook"):
        lines.append(f"**Detailed Runbook**: {observability['runbook']}\n")

    if observability.get("alertChannels"):
        channels = ", ".join(observability["alertChannels"])
        lines.append(f"**Alert Channels**: {channels}\n")

    return "\n".join(lines)
```

2. **Add CLI command**

```python
# In cli.py, add to generate group:

@generate.command("runbook")
@click.option("--project", "-p", required=True, help="Project ID")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--format", "output_format", default="markdown", type=click.Choice(["markdown", "html"]))
@click.pass_context
def generate_runbook_cmd(ctx, project: str, output: str, output_format: str):
    """Generate operational runbook from ProjectContext."""
    from contextcore.generators.runbook import generate_runbook

    # Fetch ProjectContext
    spec = get_project_context_spec(project)
    if not spec:
        click.echo(f"Error: ProjectContext '{project}' not found", err=True)
        raise SystemExit(1)

    runbook = generate_runbook(project, spec, output_format)

    if output:
        with open(output, "w") as f:
            f.write(runbook)
        click.echo(f"Runbook written to {output}")
    else:
        click.echo(runbook)
```

### Acceptance Criteria

- [ ] `contextcore generate runbook --project <id>` outputs Markdown to stdout
- [ ] `contextcore generate runbook --project <id> --output runbook.md` writes to file
- [ ] Runbook includes service overview from project and business specs
- [ ] Runbook includes SLO table from requirements
- [ ] Runbook includes risks table from risks array
- [ ] Runbook includes kubectl commands for all targets
- [ ] Runbook includes common procedures (restart, scale, debug)
- [ ] Runbook includes escalation contacts from stakeholders

### Test Cases

```python
def test_runbook_generation_minimal():
    spec = {"project": {"id": "test"}}
    runbook = generate_runbook("test", spec)
    assert "# test Operational Runbook" in runbook
    assert "## Service Overview" in runbook

def test_runbook_generation_full():
    spec = {
        "project": {"id": "checkout", "epic": "EPIC-42"},
        "business": {"owner": "commerce", "criticality": "critical"},
        "requirements": {"availability": "99.95", "latencyP99": "200ms"},
        "risks": [{"type": "security", "description": "API exposure", "priority": "P2"}],
        "targets": [{"kind": "Deployment", "name": "checkout-api", "namespace": "commerce"}],
    }
    runbook = generate_runbook("checkout", spec)
    assert "99.95%" in runbook
    assert "security" in runbook
    assert "kubectl get deployment checkout-api" in runbook
```

---

## Verification Checklist

After implementing all Phase 1 features:

- [ ] Run existing operator tests - all pass
- [ ] Deploy test ProjectContext with full spec
- [ ] Verify PrometheusRule has enriched annotations
- [ ] Verify ServiceMonitor has cost labels
- [ ] Verify Dashboard ConfigMap has cost labels
- [ ] Run `contextcore generate runbook` - produces valid Markdown
- [ ] Generated runbook renders correctly in Grafana/GitHub

---

## Quick Implementation Prompt

```
Implement ContextCore Phase 1 quick wins:

1. In operator.py, modify generate_prometheus_rules() to add annotations:
   - architecture_decision from design.adr
   - runbook_url from observability.runbook
   - owner and business_criticality from business.*
   - known_risks summary from risks[] (first 3)

2. Create generate_cost_labels(spec) function that extracts:
   - cost-center from business.costCenter
   - owner from business.owner
   - business-value from business.value
   - criticality from business.criticality
   Apply these labels in all three generator functions.

3. Create src/contextcore/generators/runbook.py with generate_runbook()
   that produces Markdown with sections: Overview, SLOs, Risks, Resources,
   Procedures, Escalation. Add CLI command `contextcore generate runbook`.

Reference: PHASE1_QUICK_WINS.md for detailed implementation steps.
```
