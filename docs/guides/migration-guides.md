# Migration Guides

> **Phase 3 Deliverable**: Guides for organizations adopting ContextCore patterns.

---

## Overview

This document provides migration paths for organizations adopting ContextCore patterns. Each guide addresses a specific starting point and desired outcome.

---

## Migration Guide 1: From Manual Status Reporting to Tasks-as-Spans

### Starting Point

- Project tracking in Jira/GitHub/Linear (tickets, not telemetry)
- Manual status updates by engineers
- Weekly status meetings for progress updates
- Separate observability stack (Prometheus/Grafana/etc.)

### Target State

- Task lifecycle as OTel spans in Tempo
- Status derived from development artifacts
- Real-time dashboards replace status meetings
- Unified queries across project and runtime data

### Migration Steps

#### Step 1: Assess Current State (1 day)

**Inventory your project tracking:**

```bash
# Questions to answer:
# 1. What issue tracker(s) do you use?
# 2. What status workflow do tickets follow?
# 3. How are task IDs referenced in commits?
# 4. What observability stack do you have?
```

**Document your status workflow:**

```yaml
# Example Jira workflow
statuses:
  - name: "To Do"
    maps_to: "todo"
  - name: "In Progress"
    maps_to: "in_progress"
  - name: "Code Review"
    maps_to: "in_review"
  - name: "QA"
    maps_to: "in_review"
  - name: "Done"
    maps_to: "done"
  - name: "Blocked"
    maps_to: "blocked"
```

#### Step 2: Set Up Telemetry Backend (1-2 days)

**Option A: Add Tempo to existing Grafana stack**

```yaml
# docker-compose.yml addition
services:
  tempo:
    image: grafana/tempo:latest
    ports:
      - "3200:3200"   # Tempo API
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
    volumes:
      - ./tempo.yaml:/etc/tempo.yaml
    command: ["-config.file=/etc/tempo.yaml"]
```

**Option B: Use existing OTLP-compatible backend**

Any backend that accepts OTLP works:
- Jaeger (with OTLP receiver)
- Datadog (with OTLP ingest)
- Honeycomb
- New Relic
- Grafana Cloud

#### Step 3: Install ContextCore SDK (1 day)

```bash
pip install contextcore

# Or from source
git clone https://github.com/contextcore/contextcore
cd contextcore
pip install -e .
```

**Configure OTLP endpoint:**

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=task-tracker
```

**Test basic functionality:**

```bash
contextcore task start --id TEST-001 --title "Test task"
contextcore task update --id TEST-001 --status in_progress
contextcore task complete --id TEST-001

# Verify in Tempo
# Query: { task.id = "TEST-001" }
```

#### Step 4: Integrate with Issue Tracker (2-3 days)

**Jira Webhook Integration:**

```python
# webhook_handler.py
from flask import Flask, request
from contextcore import TaskTracker

app = Flask(__name__)
tracker = TaskTracker(project_id="my-project")

STATUS_MAP = {
    "To Do": "todo",
    "In Progress": "in_progress",
    "Code Review": "in_review",
    "Done": "done",
    "Blocked": "blocked",
}

@app.route('/webhooks/jira', methods=['POST'])
def handle_jira_webhook():
    payload = request.json
    event_type = payload.get('webhookEvent')

    if event_type == 'jira:issue_created':
        issue = payload['issue']
        tracker.start_task(
            task_id=issue['key'],
            title=issue['fields']['summary'],
            task_type=map_issue_type(issue['fields']['issuetype']['name']),
        )

    elif event_type == 'jira:issue_updated':
        issue = payload['issue']
        changelog = payload.get('changelog', {})

        for item in changelog.get('items', []):
            if item['field'] == 'status':
                new_status = STATUS_MAP.get(item['toString'], 'todo')
                tracker.update_status(issue['key'], new_status)

    return '', 200
```

**GitHub Integration:**

```yaml
# .github/workflows/task-sync.yml
name: Sync Tasks
on:
  issues:
    types: [opened, closed, reopened]
  pull_request:
    types: [opened, closed]

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install ContextCore
        run: pip install contextcore

      - name: Sync Issue
        if: github.event_name == 'issues'
        env:
          OTEL_EXPORTER_OTLP_ENDPOINT: ${{ secrets.OTLP_ENDPOINT }}
        run: |
          if [ "${{ github.event.action }}" == "opened" ]; then
            contextcore task start \
              --id "${{ github.event.issue.number }}" \
              --title "${{ github.event.issue.title }}"
          elif [ "${{ github.event.action }}" == "closed" ]; then
            contextcore task complete --id "${{ github.event.issue.number }}"
          fi
```

#### Step 5: Enable Artifact-Based Derivation (1-2 days)

**Git commit hook:**

```bash
#!/bin/bash
# .git/hooks/post-commit

COMMIT_MSG=$(git log -1 --pretty=%B)
TASK_IDS=$(echo "$COMMIT_MSG" | grep -oE '[A-Z]+-[0-9]+' | sort -u)

for TASK_ID in $TASK_IDS; do
  contextcore task update --id "$TASK_ID" --status in_progress \
    --event "commit:$(git rev-parse --short HEAD)"
done
```

**CI pipeline integration:**

```yaml
# In your CI config (GitHub Actions example)
- name: Update task on PR merge
  if: github.event.pull_request.merged == true
  run: |
    TASKS=$(echo "${{ github.event.pull_request.title }}" | grep -oE '[A-Z]+-[0-9]+')
    for TASK in $TASKS; do
      contextcore task complete --id "$TASK" --reason "PR merged"
    done
```

#### Step 6: Provision Dashboards (1 day)

```bash
# Auto-provision dashboards
contextcore dashboards provision --grafana-url http://localhost:3000

# Verify dashboards exist
contextcore dashboards list
```

**Add dashboard links to team channels:**

- Portfolio Overview: `http://grafana:3000/d/contextcore-portfolio`
- Project Details: `http://grafana:3000/d/contextcore-project`

#### Step 7: Validate and Iterate (1 week)

**Run parallel tracking:**

For 1-2 weeks, run both manual status updates and automated derivation:

```bash
# Compare derived status vs manual status
contextcore validate --project my-project --compare-with jira
```

**Measure improvement:**

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| Hours/week on status updates | | | -50% |
| Status accuracy | | | >90% |
| Time to detect blocked tasks | | | <1 hour |

#### Step 8: Deprecate Manual Process

Once validation passes:

1. Announce transition to automated status
2. Update team documentation
3. Replace status meetings with dashboard reviews
4. Remove manual status update reminders

### Rollback Plan

If issues arise:

```bash
# Disable webhook integration
# (Remove webhook from Jira/GitHub settings)

# Continue manual status updates as before

# Keep historical data in Tempo for analysis
```

---

## Migration Guide 2: Adding Agent Memory to Existing AI Workflow

### Starting Point

- AI agents (Claude, GPT) used for development assistance
- No persistence of agent decisions between sessions
- Agents repeatedly ask for same context
- No audit trail of AI-assisted changes

### Target State

- Agent insights stored as spans in Tempo
- Agents query prior context before acting
- Decisions persist across sessions
- Full audit trail for compliance

### Migration Steps

#### Step 1: Identify Agent Touchpoints (1 day)

**Inventory your agent usage:**

```yaml
agents:
  - name: "Claude Code"
    usage: "Development assistance, code generation"
    sessions_per_week: 50
    context_gathering_time: "5-10 min/session"

  - name: "GitHub Copilot"
    usage: "Code completion"
    sessions_per_week: 200
    insight_persistence: "none"
```

**Identify high-value insights to persist:**

- Architectural decisions
- Library/framework choices
- Testing patterns discovered
- Code style preferences
- Project-specific constraints

#### Step 2: Install Agent Module (1 day)

```bash
pip install contextcore[agent]

# Or just the agent components
pip install contextcore
```

**Test basic emission:**

```python
from contextcore.agent import InsightEmitter

emitter = InsightEmitter(
    project_id="my-project",
    agent_id="test-agent"
)

emitter.emit_decision(
    summary="Test decision",
    confidence=0.9,
    rationale="Testing the integration"
)
```

#### Step 3: Integrate with Agent Framework (2-3 days)

**Claude Code hooks integration:**

```python
# .claude/hooks/session_start.py
from contextcore.agent import InsightQuerier

def get_prior_context(project_id: str, working_files: list) -> str:
    """Load prior context at session start."""
    querier = InsightQuerier()

    decisions = querier.query(
        project_id=project_id,
        insight_type="decision",
        applies_to=working_files,
        time_range="30d"
    )

    lessons = querier.query(
        project_id=project_id,
        insight_type="lesson",
        time_range="90d"
    )

    context = "## Prior Context\n\n"

    if decisions:
        context += "### Recent Decisions\n"
        for d in decisions:
            context += f"- {d.summary} (confidence: {d.confidence})\n"

    if lessons:
        context += "\n### Lessons Learned\n"
        for l in lessons:
            context += f"- {l.summary}\n"

    return context
```

```python
# .claude/hooks/session_end.py
from contextcore.agent import InsightEmitter

def emit_session_insights(session_summary: dict):
    """Emit insights at session end."""
    emitter = InsightEmitter(
        project_id=session_summary['project_id'],
        agent_id="claude-code"
    )

    for decision in session_summary.get('decisions', []):
        emitter.emit_decision(**decision)

    for lesson in session_summary.get('lessons', []):
        emitter.emit_lesson(**lesson)
```

**LangChain integration:**

```python
from langchain.callbacks import BaseCallbackHandler
from contextcore.agent import InsightEmitter

class ContextCoreCallback(BaseCallbackHandler):
    def __init__(self, project_id: str, agent_id: str):
        self.emitter = InsightEmitter(project_id=project_id, agent_id=agent_id)

    def on_chain_end(self, outputs, **kwargs):
        # Extract decisions from chain output
        if 'decision' in outputs:
            self.emitter.emit_decision(
                summary=outputs['decision']['summary'],
                confidence=outputs['decision'].get('confidence', 0.8),
                rationale=outputs['decision'].get('rationale', '')
            )
```

#### Step 4: Create Query Integration (1 day)

**Add to agent system prompts:**

```python
def build_system_prompt(project_id: str, scope: list) -> str:
    querier = InsightQuerier()

    prior_context = querier.get_context_summary(
        project_id=project_id,
        applies_to=scope,
        include_decisions=True,
        include_lessons=True,
        include_open_questions=True
    )

    return f"""
You are an AI assistant working on {project_id}.

## Prior Context from Previous Sessions
{prior_context}

## Instructions
- Check prior decisions before making new architectural choices
- Apply lessons learned to similar situations
- Reference prior decisions when relevant
- Emit new decisions and lessons for future sessions
"""
```

#### Step 5: Implement Handoff Protocol (1 day)

**Session end handoff:**

```python
def end_session(emitter: InsightEmitter, session_summary: str, open_items: list):
    """Emit handoff when ending agent session."""
    emitter.emit_handoff(
        to_agent="human",  # or next agent
        context_summary=session_summary,
        open_items=open_items
    )
```

**Session start handoff check:**

```python
def check_pending_handoffs(querier: InsightQuerier, project_id: str) -> list:
    """Check for handoffs from previous sessions."""
    handoffs = querier.query(
        project_id=project_id,
        insight_type="handoff",
        to_agent="claude-code",  # or current agent
        time_range="7d"
    )
    return [h for h in handoffs if not h.acknowledged]
```

#### Step 6: Build Agent Dashboard (1 day)

**Metrics to track:**

```yaml
panels:
  - name: "Decisions This Week"
    query: 'count by (project.id) (agent.insight.type="decision")'

  - name: "Average Confidence"
    query: 'avg(agent.insight.confidence)'

  - name: "Open Questions"
    query: 'count(agent.insight.type="question" && !resolved)'

  - name: "Handoffs Pending"
    query: 'count(agent.insight.type="handoff" && !acknowledged)'
```

#### Step 7: Validate Value (1 week)

**Measure improvement:**

| Metric | Before | After |
|--------|--------|-------|
| Context gathering time/session | | |
| Repeated questions | | |
| Consistent decisions (same question → same answer) | | |
| Audit coverage | | |

---

## Migration Guide 3: From Spreadsheet Tracking to CRD-Based Context

### Starting Point

- Project metadata in spreadsheets or wikis
- Manual configuration of observability per service
- No single source of truth for project context
- Business metadata not available to observability

### Target State

- ProjectContext CRD as single source of truth
- Observability config derived from business metadata
- GitOps workflow for context changes
- Business context in all telemetry

### Migration Steps

#### Step 1: Extract Current Metadata (1-2 days)

**Audit existing sources:**

```bash
# Common places to check:
# - Confluence/Notion pages
# - README files
# - Service catalogs
# - Spreadsheets (owner, criticality, SLOs)
# - Runbooks
```

**Create metadata inventory:**

```yaml
# inventory.yaml
services:
  - name: checkout-service
    sources:
      confluence: "https://wiki/checkout-service"
      spreadsheet: "row 42 in services.xlsx"
      readme: "services/checkout/README.md"
    metadata:
      owner: "commerce-team"  # from spreadsheet
      criticality: "critical"  # from wiki
      latency_p99: "200ms"     # from runbook
```

#### Step 2: Define CRD Schema (1 day)

**Install CRD:**

```bash
kubectl apply -f https://raw.githubusercontent.com/contextcore/contextcore/main/crds/projectcontext.yaml
```

**Create first ProjectContext:**

```yaml
# contexts/checkout-service.yaml
apiVersion: contextcore.io/v1
kind: ProjectContext
metadata:
  name: checkout-service
  namespace: commerce
spec:
  project:
    id: "commerce-platform"
    epic: "EPIC-42"

  business:
    criticality: critical
    owner: commerce-team
    value: "Primary checkout flow, direct revenue impact"
    costCenter: "CC-4521"

  requirements:
    availability: "99.95"
    latencyP99: "200ms"
    throughput: "1000rps"

  risks:
    - risk: "Payment gateway timeout"
      priority: P1
      mitigation: "Circuit breaker with fallback"

  design:
    adr: "docs/adr/001-checkout-architecture.md"
    doc: "https://wiki/checkout-service"
```

#### Step 3: Migrate Services Incrementally (1 week)

**Migration order:**

1. Start with most critical services
2. Validate CRD before removing spreadsheet entry
3. Update service documentation to reference CRD

**Per-service checklist:**

```markdown
## Migration: [service-name]

- [ ] Create ProjectContext YAML
- [ ] Apply to cluster
- [ ] Verify controller reads context
- [ ] Update service README to reference CRD
- [ ] Remove spreadsheet entry
- [ ] Notify team
```

#### Step 4: Enable Derivation (2-3 days)

**Deploy ContextCore controller:**

```bash
helm install contextcore contextcore/contextcore \
  --namespace contextcore-system \
  --create-namespace
```

**Verify derived resources:**

```bash
# Check for generated PrometheusRules
kubectl get prometheusrules -l contextcore.io/managed=true

# Check for generated ConfigMaps (sampling config)
kubectl get configmaps -l contextcore.io/managed=true
```

#### Step 5: Deprecate Old Sources (ongoing)

**Create redirect notices:**

```markdown
# In old spreadsheet
⚠️ This spreadsheet is deprecated.
Service metadata is now managed via ProjectContext CRDs.
See: https://github.com/your-org/k8s-config/tree/main/contexts/
```

**Update runbooks:**

```markdown
# Before
Owner: See row 42 in services.xlsx

# After
Owner: `kubectl get projectcontext checkout-service -o jsonpath='{.spec.business.owner}'`
```

---

## Migration Checklist Summary

### Tasks-as-Spans Migration

- [ ] Assess current project tracking
- [ ] Set up Tempo or OTLP backend
- [ ] Install ContextCore SDK
- [ ] Configure issue tracker webhooks
- [ ] Enable artifact-based derivation
- [ ] Provision dashboards
- [ ] Run parallel validation
- [ ] Deprecate manual process

### Agent Memory Migration

- [ ] Identify agent touchpoints
- [ ] Install agent module
- [ ] Integrate with agent framework
- [ ] Create query integration
- [ ] Implement handoff protocol
- [ ] Build agent dashboard
- [ ] Validate value

### CRD-Based Context Migration

- [ ] Extract current metadata
- [ ] Define CRD schema
- [ ] Migrate services incrementally
- [ ] Enable derivation
- [ ] Deprecate old sources

---

## Support Resources

- **Documentation**: [ContextCore Docs](../docs/)
- **Examples**: [Example Code](../examples/)
- **Community**: [OTel End-User SIG](https://github.com/open-telemetry/community)
- **Issues**: [GitHub Issues](https://github.com/contextcore/contextcore/issues)
