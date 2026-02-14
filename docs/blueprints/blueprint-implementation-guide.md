# ContextCore Implementation Guide

> **Phase 1 Deliverable**: Step-by-step implementation guide for Project Management Observability Blueprint.

---

## Prerequisites

Before implementing ContextCore, ensure you have:

- [ ] Kubernetes cluster (1.20+) or local Docker environment
- [ ] OTLP-compatible backend (Tempo, Jaeger, or cloud equivalent)
- [ ] Metrics backend (Mimir, Prometheus, or cloud equivalent)
- [ ] Grafana (8.0+) for dashboards
- [ ] Python 3.9+ for SDK usage

---

## Implementation Phases

### Phase A: Local Development Setup (Day 1)

#### Step A.1: Deploy Observability Stack

```bash
# Clone ContextCore repository
git clone https://github.com/contextcore/contextcore.git
cd contextcore

# Start local observability stack
docker-compose up -d

# Verify services are running
docker-compose ps
# Expected: grafana, tempo, mimir, loki, alloy all "Up"
```

**Verification**:
- Grafana: http://localhost:3000 (admin/admin)
- Tempo: http://localhost:3200/ready
- Mimir: http://localhost:9009/ready

#### Step A.2: Install ContextCore SDK

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install ContextCore
pip3 install -e ".[dev]"

# Verify installation
contextcore --version
```

#### Step A.3: Test Basic Task Tracking

```bash
# Start a test task
contextcore task start \
  --id TEST-001 \
  --title "Test task tracking" \
  --type task

# Update status
contextcore task update --id TEST-001 --status in_progress

# Complete the task
contextcore task complete --id TEST-001
```

**Verification**:
1. Open Grafana → Explore → Tempo
2. Query: `{ task.id = "TEST-001" }`
3. You should see a span with status change events

---

### Phase B: Project Context Configuration (Day 2-3)

#### Step B.1: Create Project Context File

Create `.contextcore.yaml` in your project root:

```yaml
# .contextcore.yaml
project:
  id: "my-project"
  name: "My Project"
  epic: "EPIC-001"
  description: "Description of what this project does"

business:
  criticality: high        # critical | high | medium | low
  owner: "my-team"
  value: "Describe the business value"
  costCenter: "engineering"

requirements:
  availability: "99.9%"
  latencyP99: "500ms"
  latencyP50: "100ms"
  dataRetention: "30 days"

risks:
  - risk: "External API dependency may timeout"
    priority: P2
    mitigation: "Implement circuit breaker pattern"
    scope:
      - "src/api/external_client.py"

  - risk: "Database connection pool exhaustion"
    priority: P1
    mitigation: "Add connection pool monitoring and alerts"
    scope:
      - "src/db/connection.py"

design:
  adr: "docs/adr/001-architecture.md"
  doc: "docs/DESIGN.md"
  apiContract: "docs/api/openapi.yaml"

designDecisions:
  - decision: "Use PostgreSQL for persistent storage"
    confidence: 0.95
    rationale: "Team expertise, ACID compliance needed"

  - decision: "Event-driven architecture for async processing"
    confidence: 0.85
    rationale: "Decouples components, enables retry"
```

#### Step B.2: Validate Configuration

```bash
# Validate the configuration file
contextcore config validate

# View resolved configuration
contextcore config show
```

#### Step B.3: Initialize Tracking from Config

```python
# src/tracking.py
from contextcore import TaskTracker
from contextcore.config import load_project_context

# Load from .contextcore.yaml
context = load_project_context()

# Initialize tracker with project context
tracker = TaskTracker(
    project_id=context.project.id,
    business_criticality=context.business.criticality
)
```

---

### Phase C: Task Lifecycle Integration (Week 1)

#### Step C.1: Integrate with Issue Tracker

Choose your integration pattern:

**Option A: Webhook-based (Recommended for Jira/GitHub)**

```python
# src/webhooks/issue_handler.py
from contextcore import TaskTracker

tracker = TaskTracker(project_id="my-project")

def handle_issue_created(payload: dict):
    """Handle issue.created webhook from Jira/GitHub."""
    tracker.start_task(
        task_id=payload["issue"]["key"],
        title=payload["issue"]["summary"],
        task_type=map_issue_type(payload["issue"]["type"]),
        labels=payload["issue"].get("labels", [])
    )

def handle_issue_updated(payload: dict):
    """Handle issue.updated webhook."""
    if "status" in payload.get("changelog", {}).get("items", []):
        new_status = payload["changelog"]["items"][0]["toString"]
        tracker.update_status(
            task_id=payload["issue"]["key"],
            status=map_status(new_status)
        )

def handle_issue_resolved(payload: dict):
    """Handle issue resolution."""
    tracker.complete_task(task_id=payload["issue"]["key"])
```

**Option B: Polling-based (For systems without webhooks)**

```python
# src/sync/issue_poller.py
from contextcore import TaskTracker
from datetime import datetime, timedelta

tracker = TaskTracker(project_id="my-project")

def sync_issues(since: datetime = None):
    """Poll issue tracker and sync changes."""
    since = since or datetime.now() - timedelta(hours=1)

    issues = jira_client.search(f"updated >= '{since}'")

    for issue in issues:
        if issue.created >= since:
            tracker.start_task(
                task_id=issue.key,
                title=issue.summary,
                task_type=map_type(issue.type)
            )

        # Sync status if changed
        current_status = tracker.get_status(issue.key)
        if current_status != map_status(issue.status):
            tracker.update_status(issue.key, map_status(issue.status))
```

#### Step C.2: Configure Status Mapping

```python
# src/config/status_mapping.py

JIRA_STATUS_MAP = {
    "To Do": "todo",
    "In Progress": "in_progress",
    "In Review": "in_review",
    "Blocked": "blocked",
    "Done": "done",
    "Closed": "done",
    "Won't Do": "cancelled"
}

GITHUB_STATUS_MAP = {
    "open": "todo",
    "closed": "done"
}

def map_status(external_status: str, source: str = "jira") -> str:
    """Map external status to ContextCore status."""
    mapping = JIRA_STATUS_MAP if source == "jira" else GITHUB_STATUS_MAP
    return mapping.get(external_status, "todo")
```

#### Step C.3: Test End-to-End Flow

```bash
# Create a task via CLI
contextcore task start --id IMPL-001 --title "Implement webhook handler"

# Simulate status changes
contextcore task update --id IMPL-001 --status in_progress
sleep 2
contextcore task update --id IMPL-001 --status in_review
sleep 2
contextcore task complete --id IMPL-001

# Verify in Tempo
# Query: { project.id = "my-project" && task.id = "IMPL-001" }
```

---

### Phase D: Agent Integration (Week 2)

#### Step D.1: Configure Agent Insight Emission

```python
# src/agent/insights.py
from contextcore.agent import InsightEmitter

def create_emitter(agent_id: str, session_id: str) -> InsightEmitter:
    """Create an insight emitter for an agent session."""
    return InsightEmitter(
        project_id="my-project",
        agent_id=agent_id,
        session_id=session_id
    )

# Usage in agent code
emitter = create_emitter("claude", "session-123")

# Emit a decision
emitter.emit_decision(
    summary="Selected FastAPI over Flask for API framework",
    confidence=0.88,
    rationale="Better async support, automatic OpenAPI generation",
    context={"file": "src/api/main.py"}
)

# Emit a lesson learned
emitter.emit_lesson(
    summary="Always use dependency injection for database connections",
    category="architecture",
    applies_to=["src/db/", "src/api/routes/"]
)
```

#### Step D.2: Configure Agent Guidance Reading

```python
# src/agent/guidance.py
from contextcore.agent import GuidanceReader, InsightQuerier

def get_project_context(project_id: str) -> dict:
    """Get full project context for agent consumption."""
    reader = GuidanceReader(project_id=project_id)
    querier = InsightQuerier()

    return {
        "constraints": reader.get_active_constraints(),
        "open_questions": reader.get_open_questions(),
        "recent_decisions": querier.query(
            project_id=project_id,
            insight_type="decision",
            time_range="7d"
        ),
        "lessons_learned": querier.query(
            project_id=project_id,
            insight_type="lesson",
            time_range="30d"
        )
    }
```

#### Step D.3: Add Agent Context to System Prompts

```python
# Example: Integrating with Claude Code hooks
# .claude/hooks/prompt-start.py

from contextcore.agent import GuidanceReader, InsightQuerier

def get_agent_context() -> str:
    """Generate context block for agent system prompt."""
    reader = GuidanceReader(project_id="my-project")
    querier = InsightQuerier()

    constraints = reader.get_active_constraints()
    decisions = querier.query(insight_type="decision", time_range="7d")

    context = "## Project Context\n\n"

    if constraints:
        context += "### Active Constraints\n"
        for c in constraints:
            context += f"- {c.summary}\n"

    if decisions:
        context += "\n### Recent Decisions\n"
        for d in decisions:
            context += f"- {d.summary} (confidence: {d.confidence})\n"

    return context
```

---

### Phase E: Dashboard Provisioning (Week 2-3)

#### Step E.1: Provision Built-in Dashboards

```bash
# Auto-detect Grafana and provision dashboards
contextcore dashboards provision

# Or specify Grafana URL explicitly
contextcore dashboards provision --grafana-url http://localhost:3000

# Preview without applying
contextcore dashboards provision --dry-run
```

#### Step E.2: Verify Dashboard Access

1. Open Grafana → Dashboards
2. Find "ContextCore" folder
3. Open "Project Portfolio Overview"
4. Open "Project Details"

#### Step E.3: Configure Dashboard Variables

In Grafana, edit dashboard variables:

**Project Portfolio Overview**:
- `$project`: Label values from `task_count_by_status{}`
- `$time_range`: Default to "Last 30 days"

**Project Details**:
- `$project`: Selected project ID
- `$sprint`: Label values from `sprint_velocity{project_id="$project"}`

#### Step E.4: Customize Dashboards (Optional)

```bash
# Export current dashboard
contextcore dashboards export --name "Project Portfolio Overview" > portfolio.json

# Edit portfolio.json as needed...

# Import modified dashboard
contextcore dashboards import --file portfolio.json
```

---

### Phase F: Production Deployment (Week 3-4)

#### Step F.1: Deploy ProjectContext CRD (Kubernetes)

```bash
# Apply CRD definition
kubectl apply -f crds/projectcontext.yaml

# Create your project context
kubectl apply -f - <<EOF
apiVersion: contextcore.io/v1
kind: ProjectContext
metadata:
  name: my-project
  namespace: default
spec:
  project:
    id: "my-project"
    epic: "EPIC-001"
  business:
    criticality: high
    owner: my-team
  requirements:
    availability: "99.9"
    latencyP99: "500ms"
  observability:
    traceSampling: 0.5
    alertChannels:
      - my-team-oncall
EOF
```

#### Step F.2: Deploy ContextCore Controller

```bash
# Via Helm
helm repo add contextcore https://contextcore.github.io/charts
helm install contextcore contextcore/contextcore \
  --namespace contextcore-system \
  --create-namespace \
  --set grafana.url=http://grafana.monitoring:3000

# Verify controller is running
kubectl get pods -n contextcore-system
```

#### Step F.3: Configure OTLP Export

```yaml
# In your application deployment
env:
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://tempo.monitoring:4317"
  - name: OTEL_SERVICE_NAME
    value: "my-service"
  - name: CONTEXTCORE_PROJECT_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.labels['contextcore.io/project']
```

#### Step F.4: Verify Production Setup

```bash
# Check controller logs
kubectl logs -n contextcore-system deploy/contextcore-controller

# Verify CRD is being watched
kubectl get projectcontexts -A

# Check derived resources
kubectl get prometheusrules -l contextcore.io/managed=true
```

---

## Verification Checklist

### Local Development
- [ ] Docker Compose stack running
- [ ] SDK installed and CLI working
- [ ] Test task visible in Tempo
- [ ] `.contextcore.yaml` validated

### Task Tracking
- [ ] Tasks created from issue tracker
- [ ] Status updates flowing as events
- [ ] Task completion ending spans
- [ ] Parent-child hierarchy working

### Agent Integration
- [ ] InsightEmitter configured
- [ ] Decisions queryable in Tempo
- [ ] GuidanceReader returning constraints
- [ ] Agent context in system prompts

### Dashboards
- [ ] Portfolio Overview showing projects
- [ ] Project Details with sprint data
- [ ] Drill-down links working
- [ ] Variables populated

### Production
- [ ] ProjectContext CRD applied
- [ ] Controller running
- [ ] OTLP export configured
- [ ] Derived resources created

---

## Troubleshooting

### No spans appearing in Tempo

```bash
# Check OTLP endpoint is reachable
curl -v http://localhost:4317

# Verify SDK is exporting
OTEL_LOG_LEVEL=debug contextcore task start --id DEBUG-001 --title "Debug"

# Check Tempo ingester
curl http://localhost:3200/ready
```

### Dashboard shows no data

```bash
# Verify data source configuration in Grafana
# Settings → Data Sources → Tempo → Test

# Check metric labels match queries
curl 'http://localhost:9009/prometheus/api/v1/label/__name__/values' | grep task

# Verify time range includes your data
```

### Agent insights not persisting

```python
# Enable debug logging
import logging
logging.getLogger("contextcore.agent").setLevel(logging.DEBUG)

# Verify emitter configuration
emitter = InsightEmitter(project_id="test", agent_id="debug")
emitter.emit_decision("Test decision", confidence=0.9)
# Check logs for export confirmation
```

---

## Next Steps

After completing this implementation guide:

1. **Customize for your workflow**: Adapt status mappings, add custom attributes
2. **Extend dashboards**: Add team-specific panels and alerts
3. **Integrate more sources**: Connect CI/CD, code review, deployment events
4. **Scale horizontally**: Add more projects, configure cross-project views

See [Blueprint Reference Architecture](blueprint-reference-architecture.md) for architectural context and [Reusable Patterns](blueprint-reusable-patterns.md) for patterns to apply in other domains.
