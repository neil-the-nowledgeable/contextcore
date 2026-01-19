# ContextCore: Project Management as Observability

## Vision Statement

**ContextCore** is a project management observability framework and toolkit designed to facilitate the thoughtful integration of the business context generated during the **initiation, design, development, testing, and deployment** of a system with existing operational metadata.

Expressed in the language of OpenTelemetry:

> **The goal of ContextCore is to eliminate manual status reporting** to the extent possible through extrapolation of existing artifact metadata of your applications and systems, **regardless of the programming language, infrastructure, and runtime environments used**, and provide context for the generation of observability strategies based on system construction — and, in a similar fashion, eventually generate analytics and optimization strategies.

---

## Framework Goals

### 1. Eliminate Manual Status Reporting

The core insight: **artifact metadata already contains status information**. ContextCore extracts and correlates it:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AUTOMATIC STATUS EXTRAPOLATION                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   EXISTING ARTIFACT METADATA              DERIVED STATUS                    │
│   ──────────────────────────              ──────────────                    │
│                                                                              │
│   Git commit: "PROJ-123: add auth"    →   Task in_progress                 │
│   PR opened: "fixes PROJ-123"         →   Task in_review                   │
│   PR merged to main                   →   Task done                        │
│   CI build failed                     →   Task at_risk                     │
│   Deployment to production            →   Epic milestone reached           │
│   Runtime error rate > threshold      →   Link to owning task              │
│   No commits for 7 days               →   Task stale (alert)               │
│   Test coverage dropped               →   Quality risk signal              │
│                                                                              │
│   ═══════════════════════════════════════════════════════════════════════  │
│                                                                              │
│   Result: Project status is DERIVED, not manually reported                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. Language, Infrastructure, and Runtime Agnostic

Like OpenTelemetry, ContextCore works with **any** technology stack:

| Dimension | ContextCore Approach |
|-----------|---------------------|
| **Programming Language** | Extracts from git, CI, deployment (not code) |
| **Project Management Tool** | Adapters for Jira, GitHub, Linear, Notion, etc. |
| **Development Workflow** | Scrum, Kanban, custom — workflow-agnostic |
| **Infrastructure** | Cloud, on-prem, hybrid — platform-agnostic |
| **Observability Backend** | Any OTLP-compatible receiver |
| **CI/CD Pipeline** | GitHub Actions, GitLab CI, Jenkins, etc. |

### 3. Observability Strategy Generation

Use business context to **automatically derive** observability configurations:

| Business Context | Generated Observability Strategy |
|------------------|----------------------------------|
| `criticality: critical` | 100% trace sampling, 10s metrics, P1 alerts |
| `criticality: low` | 1% sampling, 120s metrics, P4 alerts |
| `business.value: revenue-primary` | Featured dashboard, SLO tracking |
| `requirements.latency_p99: 200ms` | Latency alert rule, SLI definition |
| `risks[].type: security` | Extended audit logging, anomaly detection |
| `design.adr: ADR-015` | Runbook link in alert annotations |

This eliminates the manual work of configuring observability for each service — the configuration is **derived from project context**.

### 4. Analytics and Optimization (Future)

The data model is designed to eventually support:

| Capability | Description |
|------------|-------------|
| **Forecasting** | Predict sprint completion based on velocity trends |
| **Anomaly Detection** | Identify unusual patterns in task flow |
| **Capacity Planning** | Correlate team allocation with throughput |
| **Risk Prediction** | Early warning for at-risk deliverables |
| **Bottleneck Analysis** | Identify workflow inefficiencies |

> **Note**: Optimization is out of scope for initial releases but is a key design principle. The telemetry data model supports these future capabilities.

---

## Technical Goals

### 5. OpenTelemetry-Native

ContextCore extends OpenTelemetry's proven patterns:

| OTel Concept | ContextCore Application |
|--------------|------------------------|
| Traces | Project/Epic lifecycles |
| Spans | Tasks with duration, status, hierarchy |
| Events | Status transitions, comments, blockers |
| Links | Dependencies, commit associations |
| Metrics | Velocity, WIP, cycle time, burndown |
| Logs | Audit trail of all changes |
| Resource Attributes | Project context on every signal |

### 6. Vendor and Tool Agnostic

**Open Source Backends:**
- Jaeger, Zipkin (traces)
- Prometheus (metrics)
- ClickHouse (analytics)

**Commercial Backends:**
- Datadog, New Relic, Honeycomb, Dynatrace, Splunk

**Reference Implementation:**
- Grafana + Tempo + Mimir + Loki (ships ready for local use)

> **Important**: ContextCore is NOT a backend. It is a **data model**, **SDK**, and **export protocol**. The Grafana stack is a reference implementation, not a required component.

### 7. Lifecycle Integration

Connect the full system lifecycle through unified telemetry:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LIFECYCLE INTEGRATION                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   INITIATION      DESIGN        DEVELOPMENT      TESTING       DEPLOYMENT   │
│   ──────────      ──────        ───────────      ───────       ──────────   │
│   • Epics         • ADRs        • Commits        • Test runs   • Releases   │
│   • Requirements  • API specs   • PRs            • Coverage    • Configs    │
│   • Estimates     • Diagrams    • Branches       • Results     • Rollouts   │
│   • Risk assess   • Prototypes  • Code reviews   • Perf tests  • Canaries   │
│                                                                              │
│         │              │              │              │              │        │
│         └──────────────┴──────────────┴──────────────┴──────────────┘        │
│                                       │                                      │
│                                       ▼                                      │
│                              CONTEXTCORE SDK                                │
│                          (extrapolation + correlation)                      │
│                                       │                                      │
│                                       ▼                                      │
│                               OTLP EXPORT                                   │
│                                       │                                      │
│                    ┌──────────────────┼──────────────────┐                  │
│                    ▼                  ▼                  ▼                  │
│            ┌─────────────┐    ┌─────────────┐    ┌─────────────┐           │
│            │  OPERATION  │    │OBSERVABILITY│    │OPTIMIZATION │           │
│            │   Context   │    │  Strategy   │    │  Strategy   │           │
│            │             │    │  Generation │    │ (future)    │           │
│            └─────────────┘    └─────────────┘    └─────────────┘           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Benefits

### Benefit 1: Eliminate the Project Management Data Silo

Traditional project management tools create a **data silo not designed for developers or development workflows**:

| PM Tool Problem | Impact | ContextCore Solution |
|-----------------|--------|---------------------|
| Separate system from dev tools | Context switching, low adoption | Lives in observability stack |
| Manual data entry required | Stale, incomplete data | Auto-populated from artifacts |
| Different query language | Can't correlate with ops data | Same PromQL/TraceQL/LogQL |
| Limited API/integration | Hard to automate | Native OTLP export |
| Designed for managers | Developers avoid it | Developer-native experience |

**Result**: Project data lives where developers already work — in their observability stack.

### Benefit 2: Eliminate Developer Toil Creating Status Reports

**Stop asking developers to write status reports.** The information already exists in their artifacts:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DEVELOPER TOIL ELIMINATION                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   TRADITIONAL TOIL                     CONTEXTCORE APPROACH                  │
│   ────────────────                     ────────────────────                  │
│                                                                              │
│   📝 Weekly status emails          →   Auto-generated from commits/PRs      │
│   📋 Manual Jira updates           →   Status derived from git activity     │
│   📊 Sprint retro data prep        →   Metrics computed from span data      │
│   💬 "What's the status?" pings    →   Self-service dashboards              │
│   🔄 Duplicate entry (git + Jira)  →   Single source of truth               │
│   📈 Velocity calculations         →   Real-time from completed spans       │
│   📑 Release notes compilation     →   Query tasks linked to deployment     │
│                                                                              │
│   ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│   Hours saved per developer per week: 2-4 hours                             │
│   Data quality improvement: Manual → Automated = Always current             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Benefit 3: Eliminate Dependence on Developer Status Reports

Project visibility should **not depend on developers remembering to update tickets**:

| Dependence Problem | Real-World Impact | ContextCore Solution |
|--------------------|-------------------|---------------------|
| Tickets "in progress" for weeks | False sense of activity | Activity-based staleness alerts |
| No updates until completion | Surprises at sprint end | Continuous signal from commits |
| Inconsistent update quality | Some devs detailed, some not | Uniform automated extrapolation |
| "Forgot to update the ticket" | Management blind spots | No manual updates required |
| Status varies by diligence | Unreliable project view | Same rules applied to all |
| Blocked tasks not marked | Hidden blockers | Inactivity detection |

**Result**: Project status is **derived from activity**, not **reported by developers**.

### Benefit 4: Business-Aware Observability Strategy Generation

Incorporate business metadata with operational metadata to **auto-generate observability strategies** for thoughtful incident response:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY STRATEGY GENERATION                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   BUSINESS CONTEXT                     GENERATED STRATEGY                    │
│   ────────────────                     ──────────────────                    │
│                                                                              │
│   criticality: critical            →   100% trace sampling                  │
│                                        10s metrics interval                 │
│                                        P1 alert priority                    │
│                                                                              │
│   business.value: revenue-primary  →   Featured dashboard placement         │
│                                        SLO tracking enabled                 │
│                                        Error budget alerting                │
│                                                                              │
│   business.owner: commerce-team    →   Alert routing to #commerce-oncall    │
│                                        Escalation to commerce-lead          │
│                                        PagerDuty integration                │
│                                                                              │
│   risks[].type: security           →   Extended audit logging               │
│                                        Anomaly detection enabled            │
│                                        Security team in alert chain         │
│                                                                              │
│   design.adr: ADR-015              →   Runbook link in alert annotations    │
│                                        Architecture context for responders  │
│                                                                              │
│   ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│   INCIDENT RESPONSE CONTEXT                                                  │
│   ─────────────────────────                                                  │
│                                                                              │
│   Alert: "High latency on checkout-service"                                 │
│   Context provided:                                                          │
│     • Business value: revenue-primary (this is critical!)                   │
│     • Owner: commerce-team (who to contact)                                 │
│     • Design doc: https://docs.internal/checkout (how it works)             │
│     • ADR: ADR-015 (why it's designed this way)                             │
│     • Dependencies: payment-service, inventory-service                      │
│     • Recent changes: PROJ-123 deployed 2 hours ago                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Benefit 5: Single Language for Project Operations and Project Management

**One system, one query language, integrated metadata** enables unified workflows:

#### For Developers
```
# Same tools for code AND project status
grafana → dashboards for runtime metrics AND sprint burndown
traceql → query production traces AND task hierarchies
promql  → alert on latency AND alert on blocked tasks
```

#### For Engineering Managers
```
# Real-time visibility without chasing updates
Dashboard: Team velocity, WIP, blocked tasks, cycle time
Alert: "3 tasks stale for >7 days in sprint-5"
Query: "Show all in-progress work for checkout-service"
```

#### For Leadership
```
# Executive portals from the same data source
Dashboard: Program health across all teams
Report: Quarterly delivery metrics (auto-generated)
View: Risk signals across portfolio
```

#### For Incident Response
```
# Full context during outages
Alert annotation: Owner, design doc, ADR, recent deployments
Trace link: Connect runtime error to originating task
Query: "What changed in the last 24 hours for this service?"
```

| Use Case | Traditional Approach | ContextCore Unified |
|----------|---------------------|---------------------|
| Status report | Export Jira → PowerPoint | Grafana dashboard snapshot |
| Sprint review | Manual metric calculation | Pre-built TraceQL queries |
| Leadership portal | Custom BI tool integration | Native Grafana dashboard |
| Incident context | Search Jira during outage | Context in alert annotations |
| Cross-team visibility | Request Jira project access | Shared observability platform |
| Historical analysis | Export limited Jira data | Full telemetry retention |
| Compliance audit | Manual report generation | Query audit trail |

---

## Differentiation: Why Observability Infrastructure

### The Core Argument

Given the infrastructure required to keep systems up and running — especially for large systems and applications — **it is more feasible to leverage existing operational observability infrastructure** for project management than to attempt to shoe-horn an operational perspective into project management tools or models.

ContextCore is the **natural evolution of OpenTelemetry and systems observability**.

### ContextCore vs. Developer Portals (Backstage, etc.)

Tools like **Backstage** thoughtfully and programmatically align development processes and systems. However, they require adopting a **new system**:

| Dimension | Developer Portals | ContextCore |
|-----------|------------------|-------------|
| **Philosophy** | New unified portal for developers | Unify view in existing infrastructure |
| **Data Strategy** | Aggregate data into new system | Leverage existing data where it lives |
| **Infrastructure** | New application to deploy and maintain | Uses observability stack you already run |
| **Persistence** | New database for portal data | Time-series DBs (Tempo, Mimir, Loki) |
| **Authentication** | Another login, session, context | Same Grafana access |
| **Adoption Cost** | Migrate teams to new portal | Zero new tools for developers |
| **Maintenance** | Another system to patch, upgrade | Maintained as part of observability |

### ContextCore vs. PM Tool Plugins

The alternative approach — adding operational data to PM tools — has fundamental limitations:

| Challenge | Why It Fails |
|-----------|--------------|
| **Data Model Mismatch** | PM tools designed for records, not time-series telemetry |
| **Query Limitations** | Jira Query Language ≠ PromQL/TraceQL expressiveness |
| **Scale** | PM databases not designed for metric/trace volume |
| **Real-time** | PM tools batch-oriented, not real-time streaming |
| **Developer Adoption** | Developers still avoid PM tools regardless of plugins |
| **Incident Response** | Still need to query separate system during outages |

### Why Grafana Serves All Audiences

Grafana is perfectly capable of serving **all stakeholders**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GRAFANA AS UNIVERSAL AUDIENCE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   STAKEHOLDER              USE CASE                    DASHBOARD TYPE       │
│   ───────────              ────────                    ──────────────       │
│                                                                              │
│   Developers           →   Debug, monitor code     →   Service dashboards  │
│   Designers            →   Track design tasks      →   Design sprint view  │
│   Testers              →   Test coverage, results  →   Quality metrics     │
│   Project Managers     →   Sprint progress, WIP    →   Kanban/burndown     │
│   Business Stakeholders→   Feature delivery        →   Roadmap progress    │
│   Operators            →   Incident response       →   Operational + context│
│   Leadership           →   Portfolio health        →   Executive summary   │
│   Auditors             →   Compliance evidence     →   Audit trail queries │
│                                                                              │
│   ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│   All from the SAME infrastructure:                                         │
│   • No new database          • No new application                          │
│   • No new login             • No new context switching                    │
│   • No new training          • No new maintenance burden                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Built-in Capabilities That Eliminate New Systems

| Need | Grafana Stack Capability |
|------|-------------------------|
| **Time-series persistence** | Tempo (traces), Mimir (metrics), Loki (logs) |
| **Flexible visualization** | Dashboards customizable for any audience |
| **Alerting** | Unified for operational AND project signals |
| **Access control** | Role-based dashboard and data visibility |
| **API access** | Programmatic access for custom integrations |
| **Exploration** | Ad-hoc queries without pre-built dashboards |
| **Correlation** | Link project spans to runtime traces |

### The Natural Evolution of Observability

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVOLUTION OF OBSERVABILITY                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ERA           INSIGHT                           TOOLS                     │
│   ───           ───────                           ─────                     │
│                                                                              │
│   2010s         "Centralize logs for search"      ELK, Splunk              │
│                                                                              │
│   2015s         "Add time-series metrics"         Prometheus, InfluxDB     │
│                                                                              │
│   2018s         "Trace requests across services"  Jaeger, Zipkin           │
│                                                                              │
│   2019          "Unify with standard semantics"   OpenTelemetry            │
│                                                                              │
│   2024+         "Extend to project management"    ContextCore              │
│                 → Tasks as spans                                            │
│                 → Business context as attributes                           │
│                 → Same infrastructure                                      │
│                 → Same query language                                      │
│                 → Natural evolution, not new system                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Integration Value Proposition

ContextCore seeks to **unify the view** for all stakeholders by:

1. **Leveraging existing data** — not requiring new data entry
2. **Thoughtful generation** — auto-generating project telemetry from artifacts
3. **Integration with existing systems** — not replacing them
4. **No new infrastructure** — using the observability stack that already exists

The value is realized through **thoughtful integration of project management data structures into existing systems**, enabling:

- **Reporting** from the same queries used for operational monitoring
- **Leadership portals** as Grafana dashboards, not separate BI tools
- **Incident context** available without switching systems
- **Historical analysis** with full telemetry retention
- **Cross-team visibility** through shared observability platform

---

## The Core Insight: Tasks ARE Telemetry

### Why OTel Patterns Are Perfect for Project Management

| OTel Concept | Project Management Equivalent |
|--------------|------------------------------|
| **Trace** | Project/Epic lifecycle (start → complete) |
| **Span** | Individual task (with duration, status, events) |
| **Span Events** | Status transitions, comments, assignments |
| **Span Links** | Task dependencies, blockers |
| **Metrics** | Velocity, WIP, cycle time, percent complete |
| **Logs** | Audit trail of every change |
| **Resource Attributes** | Project context on every signal |

Traditional PM tools treat tasks as records in a database. ContextCore treats tasks as **living telemetry** - observable, queryable, and connected to the systems they describe.

---

## The Three Pillars of Task Telemetry

### 1. Tasks as Spans (Tempo)

Every task is an OpenTelemetry span with:

```
┌─────────────────────────────────────────────────────────────────┐
│  TASK SPAN: story:PROJ-123                                       │
├─────────────────────────────────────────────────────────────────┤
│  Trace ID: abc123...  (links to epic span)                      │
│  Span ID: def456...                                              │
│  Parent: epic:EPIC-42                                            │
│                                                                  │
│  Attributes:                                                     │
│    task.id: PROJ-123                                             │
│    task.title: "Implement OAuth flow"                            │
│    task.type: story                                              │
│    task.status: in_progress                                      │
│    task.priority: high                                           │
│    task.assignee: alice                                          │
│    task.story_points: 5                                          │
│    task.percent_complete: 60                                     │
│    task.subtask_count: 5                                         │
│    task.subtask_completed: 3                                     │
│    sprint.id: sprint-3                                           │
│    project.id: auth-system                                       │
│                                                                  │
│  Events (timeline):                                              │
│    ├─ task.created           [2024-01-15 09:00]                 │
│    ├─ task.status_changed    [2024-01-15 10:30] todo→in_progress│
│    ├─ task.assigned          [2024-01-15 10:30] →alice          │
│    ├─ task.subtask_completed [2024-01-16 14:00] 1/5             │
│    ├─ task.subtask_completed [2024-01-17 11:00] 2/5             │
│    ├─ task.blocked           [2024-01-17 15:00] "API review"    │
│    ├─ task.commented         [2024-01-18 09:00] "Unblocked"     │
│    ├─ task.unblocked         [2024-01-18 09:00]                 │
│    ├─ task.subtask_completed [2024-01-18 16:00] 3/5             │
│    └─ ...                                                        │
│                                                                  │
│  Links:                                                          │
│    ├─ depends_on: task:PROJ-100 (API design)                    │
│    ├─ implements: commit:abc123 (feat: add oauth)               │
│    └─ implements: commit:def456 (fix: token refresh)            │
│                                                                  │
│  Start: 2024-01-15T09:00:00Z                                    │
│  End: (still open)                                               │
└─────────────────────────────────────────────────────────────────┘
```

**Why Tempo for Tasks:**
- Natural hierarchy (traces contain spans)
- Built-in duration tracking
- Event timeline for audit
- Links for relationships
- TraceQL for powerful queries

### 2. Tasks as Metrics (Mimir/Prometheus)

Every task emits metrics for real-time dashboards:

```promql
# Current state gauges
task_status{project="auth-system", status="in_progress"}  # Count by status
task_wip{project="auth-system", team="platform"}          # Work in progress
task_blocked{project="auth-system"}                        # Blocked count

# Progress tracking
task_percent_complete{task_id="PROJ-123"}                  # Individual task progress
epic_percent_complete{epic_id="EPIC-42"}                   # Epic rollup
sprint_percent_complete{sprint_id="sprint-3"}              # Sprint burndown

# Derived metrics (histograms)
task_lead_time_seconds{project="auth-system", type="story"}
task_cycle_time_seconds{project="auth-system", type="story"}
task_blocked_time_seconds{project="auth-system"}

# Counters
task_completed_total{project="auth-system", type="story"}
story_points_completed_total{project="auth-system", sprint="sprint-3"}
task_status_transitions_total{from="todo", to="in_progress"}

# Story point tracking
sprint_points_planned{sprint_id="sprint-3"}                # 34
sprint_points_completed{sprint_id="sprint-3"}              # 21
sprint_points_remaining{sprint_id="sprint-3"}              # 13
```

**Percent Complete Calculation:**

```python
# For tasks with subtasks
percent_complete = (subtasks_completed / subtasks_total) * 100

# For epics (aggregating stories)
percent_complete = (stories_completed / stories_total) * 100
# OR weighted by story points:
percent_complete = (story_points_completed / story_points_total) * 100

# For sprints
percent_complete = (sprint_points_completed / sprint_points_planned) * 100
```

**Why Mimir for Tasks:**
- Real-time gauges (current WIP, blocked count)
- Time-series for burndown/burnup charts
- Alerting on thresholds (WIP limit exceeded)
- Same query language devs already know
- Grafana-native visualization

### 3. Tasks as Logs (Loki)

Every status transition is a structured log entry:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "info",
  "event": "task.status_changed",
  "task_id": "PROJ-123",
  "task_title": "Implement OAuth flow",
  "task_type": "story",
  "project_id": "auth-system",
  "sprint_id": "sprint-3",
  "from_status": "todo",
  "to_status": "in_progress",
  "actor": "alice",
  "actor_type": "user",
  "trigger": "manual",
  "metadata": {
    "assignee": "alice",
    "story_points": 5
  }
}
```

**Log Events for Full Audit Trail:**

| Event | Description | Key Fields |
|-------|-------------|------------|
| `task.created` | New task added | title, type, assignee, points |
| `task.status_changed` | Status transition | from, to, actor, trigger |
| `task.assigned` | Assignment change | from_assignee, to_assignee, actor |
| `task.blocked` | Task blocked | reason, blocker_id, blocker_type |
| `task.unblocked` | Block removed | resolution, blocked_duration |
| `task.commented` | Comment added | author, text, mentions |
| `task.linked` | Dependency added | link_type, target_id |
| `task.points_changed` | Estimate updated | from_points, to_points, reason |
| `task.completed` | Task done | cycle_time, lead_time, points |
| `task.cancelled` | Task cancelled | reason, actor |
| `subtask.completed` | Subtask finished | parent_id, percent_complete |
| `commit.linked` | Code committed | commit_sha, task_id, author |
| `pr.linked` | PR associated | pr_number, task_id, status |

**Why Loki for Tasks:**
- Full audit trail (compliance, debugging)
- LogQL queries across all events
- Correlate with application logs
- Alert on patterns (task stuck > 7 days)
- Cheap, long-term storage

---

## Data Model Enhancements

### Enhanced TaskSpec

```python
class TaskSpec(BaseModel):
    """Enhanced task specification with progress tracking."""

    # Identity
    id: str
    title: str
    description: Optional[str] = None
    type: TaskType  # epic|story|task|subtask|bug|spike|incident

    # Hierarchy
    parent_id: Optional[str] = None  # Parent task/epic
    subtask_ids: List[str] = []      # Child tasks

    # Progress (NEW)
    percent_complete: float = 0.0    # 0-100, calculated or manual
    progress_type: ProgressType      # manual|subtask_based|point_based

    # Estimation
    story_points: Optional[int] = None
    time_estimate: Optional[str] = None  # ISO 8601 duration

    # Assignment
    assignee: Optional[str] = None
    team: Optional[str] = None

    # Status
    status: TaskStatus
    blocked_by: Optional[str] = None
    blocked_reason: Optional[str] = None

    # Time tracking
    due_date: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Integration
    external_url: Optional[str] = None  # Jira, GitHub, etc.
    commits: List[str] = []              # Linked commit SHAs
    pull_requests: List[str] = []        # Linked PR numbers

    # Classification
    priority: Priority
    labels: List[str] = []
    sprint_id: Optional[str] = None

    # Context
    project_id: str
    design_doc: Optional[str] = None
    adr: Optional[str] = None


class ProgressType(str, Enum):
    """How percent_complete is calculated."""
    MANUAL = "manual"              # User sets directly
    SUBTASK_BASED = "subtask"      # (completed_subtasks / total_subtasks) * 100
    POINT_BASED = "points"         # (completed_points / total_points) * 100
    CHECKLIST_BASED = "checklist"  # (checked_items / total_items) * 100
```

### Enhanced Sprint Model

```python
class SprintSpec(BaseModel):
    """Sprint specification with progress tracking."""

    id: str
    name: str
    goal: Optional[str] = None

    # Time bounds
    start_date: str
    end_date: str

    # Capacity
    planned_points: int
    team_capacity: Optional[int] = None  # Available person-days

    # Progress (calculated)
    completed_points: int = 0
    percent_complete: float = 0.0  # (completed_points / planned_points) * 100

    # Burndown data
    daily_remaining: List[DailyProgress] = []  # For burndown chart

    # Tasks
    task_ids: List[str] = []  # Tasks in this sprint

    # Velocity context
    velocity_baseline: Optional[float] = None  # Expected based on history


class DailyProgress(BaseModel):
    """Daily progress snapshot for burndown."""
    date: str
    points_remaining: int
    points_completed: int
    tasks_completed: int
    ideal_remaining: float  # Linear burndown target
```

---

## Git Commit Integration

### Automatic Task Status Updates

When code is committed with task references, ContextCore automatically:

1. **Detects task references** in commit messages
2. **Links commits to tasks** (span links)
3. **Updates task status** based on commit patterns
4. **Logs the integration event**

```
┌──────────────────────────────────────────────────────────────────┐
│                    GIT → CONTEXTCORE FLOW                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Developer commits:                                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ git commit -m "feat(auth): implement token refresh          │ │
│  │                                                              │ │
│  │ Implements PROJ-123                                          │ │
│  │ Part of EPIC-42"                                             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                          │                                        │
│                          ▼                                        │
│  Git Hook / Webhook → ContextCore CLI                            │
│                          │                                        │
│                          ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ contextcore git link                                         │ │
│  │   --commit abc123                                            │ │
│  │   --message "feat(auth): implement token refresh..."         │ │
│  │   --author "alice"                                           │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                          │                                        │
│                          ▼                                        │
│  Actions:                                                         │
│  1. Parse commit message for task references                     │
│  2. For each task found:                                         │
│     a. Add span link: task → commit                              │
│     b. If status == "todo" → update to "in_progress"             │
│     c. Add span event: "commit.linked"                           │
│     d. Emit log: task.commit_linked                              │
│     e. Update metric: task_commits_total                         │
│  3. For PRs: watch for merge → can trigger "done"                │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Commit Message Patterns

```python
# Patterns that link commits to tasks
TASK_PATTERNS = [
    r"(?:implements?|closes?|fixes?|refs?|relates?\s+to)\s+([A-Z]+-\d+)",
    r"([A-Z]+-\d+)",  # Any PROJ-123 pattern
    r"#(\d+)",        # GitHub issue numbers
]

# Patterns that indicate task completion
COMPLETION_PATTERNS = [
    r"(?:closes?|fixes?|resolves?)\s+([A-Z]+-\d+)",
]

# Status inference rules
STATUS_INFERENCE = {
    "first_commit": "in_progress",      # Any commit → start work
    "closes_pattern": "in_review",      # "Closes PROJ-123" → ready for review
    "pr_merged": "done",                # PR merge → complete
}
```

### Git Hook Integration

```bash
#!/bin/bash
# .git/hooks/post-commit

# Extract commit info
COMMIT_SHA=$(git rev-parse HEAD)
COMMIT_MSG=$(git log -1 --format=%B)
AUTHOR=$(git log -1 --format=%an)

# Send to ContextCore
contextcore git link \
  --commit "$COMMIT_SHA" \
  --message "$COMMIT_MSG" \
  --author "$AUTHOR" \
  --repo "$(basename $(git remote get-url origin) .git)"
```

---

## Interactive Dashboards

### Status Report as Grafana Dashboard

Traditional status reports are static documents. ContextCore makes them **live, queryable dashboards**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PROJECT STATUS DASHBOARD                                 │
│                     auth-system | Sprint 3                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  SPRINT HEALTH  │  │    VELOCITY     │  │   BURNDOWN      │             │
│  │                 │  │                 │  │                 │             │
│  │   62% Complete  │  │  21 pts/sprint  │  │ ████████░░░░░   │             │
│  │   ▲ On Track    │  │  ↑ 12% vs avg   │  │ 13 pts remain   │             │
│  │                 │  │                 │  │ 3 days left     │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  TASK STATUS BREAKDOWN                                               │   │
│  │  ████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │   │
│  │  Done: 8 │ In Progress: 4 │ In Review: 2 │ Blocked: 1 │ Todo: 5   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  BLOCKED TASKS (Action Required)                                     │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ ⚠ PROJ-145 "API rate limiting" blocked 3d                     │  │   │
│  │  │   Reason: Waiting on security review                          │  │   │
│  │  │   Owner: bob | Blocker: Security Team                         │  │   │
│  │  │   [View Task] [View Logs] [Escalate]                          │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  RECENT ACTIVITY (Live Log Stream)                                   │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │  10:32 alice completed PROJ-142 "Token validation" (5 pts)         │   │
│  │  10:15 bob pushed commit abc123 → PROJ-145                         │   │
│  │  09:45 carol moved PROJ-148 to "In Review"                         │   │
│  │  09:30 alice commented on PROJ-145: "Security review scheduled"    │   │
│  │  [Load More] [Filter by User] [Filter by Task]                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────┐  ┌──────────────────────────────────┐   │
│  │  CYCLE TIME (Last 30 Days)   │  │  TEAM WORKLOAD                    │   │
│  │                              │  │                                   │   │
│  │  Stories: 4.2 days avg       │  │  alice ████████░░ 4 tasks        │   │
│  │  Tasks: 1.8 days avg         │  │  bob   ██████░░░░ 3 tasks        │   │
│  │  Bugs: 0.5 days avg          │  │  carol ████░░░░░░ 2 tasks        │   │
│  │                              │  │                                   │   │
│  │  [See Histogram]             │  │  [Balance Workload]              │   │
│  └──────────────────────────────┘  └──────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  QUERY PANEL                                               [TraceQL] │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ { task.status = "blocked" && task.blocked_duration > 2d }     │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  │  [Run Query] [Save View] [Export]                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Dashboard Panel Types

| Panel | Data Source | Query Example |
|-------|-------------|---------------|
| Sprint Burndown | Mimir | `sprint_points_remaining{sprint="sprint-3"}` |
| Task Status Pie | Mimir | `sum by (status) (task_status{project="auth"})` |
| Blocked Tasks | Tempo | `{ task.status = "blocked" }` |
| Activity Stream | Loki | `{project="auth"} \| json \| event =~ "task.*"` |
| Cycle Time | Mimir | `histogram_quantile(0.95, task_cycle_time_seconds)` |
| Velocity Trend | Mimir | `sprint_velocity{project="auth"}[90d]` |

### Query Examples

**Find all blocked tasks older than 3 days:**
```logql
{project="auth-system"}
| json
| event = "task.blocked"
| duration > 3d
```

**Show task completion velocity by week:**
```promql
sum(increase(task_completed_total{project="auth-system"}[7d])) by (week)
```

**Trace a task's full lifecycle:**
```traceql
{ task.id = "PROJ-123" }
```

**Find tasks without commits (stale work):**
```logql
{project="auth-system"}
| json
| event = "task.status_changed"
| to_status = "in_progress"
| task_id !~ ".*" in (
    {project="auth-system"} | json | event = "commit.linked" | task_id
  )
```

---

## Why Developers Will Love This

### 1. No Context Switching

```
Traditional:
  IDE → Jira → Slack → IDE → Jira → Grafana → IDE

ContextCore:
  IDE → Grafana (everything is here)
```

### 2. Same Tools They Already Know

| Need | Traditional PM | ContextCore |
|------|----------------|-------------|
| Find blocked tasks | Jira filter | TraceQL query |
| Check sprint progress | Sprint board | Grafana dashboard |
| Debug slow task | Manual investigation | Correlate with traces |
| Alert on risk | Manual monitoring | PrometheusRule |
| Audit trail | Export to spreadsheet | Loki queries |

### 3. Code ↔ Task Connection

Every commit automatically links to tasks. No manual updates.

```
$ git log --oneline
abc123 feat(auth): implement refresh token [PROJ-123] ← auto-linked
def456 fix(auth): handle expired tokens [PROJ-123]
ghi789 test(auth): add token tests [PROJ-123]

$ contextcore task show PROJ-123
PROJ-123: Implement OAuth flow
Status: in_progress (3 commits linked)
Commits:
  - abc123 feat(auth): implement refresh token
  - def456 fix(auth): handle expired tokens
  - ghi789 test(auth): add token tests
```

### 4. Time-Series Superpowers

Things time-series gives us that traditional PM tools don't:

| Capability | Traditional PM | Time-Series |
|------------|----------------|-------------|
| Burndown | Snapshot at sprint end | Continuous, queryable |
| Cycle time | Manual calculation | Histogram, percentiles |
| Blocked time | "Task was blocked" | Exact duration, patterns |
| Velocity | Spreadsheet | Trend analysis, forecasting |
| Correlations | None | Task latency vs code complexity |
| Anomalies | Manual review | Automatic detection |
| Historical | Limited | Years of data, cheap storage |

### 5. Unified Incident Response

When production breaks:

```
Traditional:
  1. See alert in Grafana
  2. Find relevant traces
  3. Switch to Jira to find related tasks
  4. Switch to GitHub to find related PRs
  5. Switch back to Grafana

ContextCore:
  1. See alert in Grafana
  2. Click "Related Tasks" → see PROJ-123 implemented this
  3. Click "Related Commits" → see exactly what changed
  4. All in one place, correlated by trace ID
```

---

## Design Decisions

Decisions made to keep initial implementation simple and iterate:

### Progress Calculation
**Decision: Simple count method**
- Epic percent complete = `(completed_stories / total_stories) * 100`
- Sprint percent complete = `(completed_points / planned_points) * 100` (points already required for sprints)
- Rationale: Works without requiring story point estimates on all tasks; can add weighted option later

### Logging Granularity
**Decision: Status-changing events only**
- Log to Loki: `task.created`, `task.status_changed`, `task.blocked`, `task.unblocked`, `task.completed`, `task.cancelled`
- Skip: `task.commented`, `task.assigned` (unless they trigger status change)
- Rationale: Cleaner audit trail, lower storage costs; comments remain in span events for detailed trace view

### Git Integration
**Decision: Git hooks first, webhooks later**
- Phase 2: Client-side git hooks (`.git/hooks/post-commit`)
- Future phase: GitHub webhooks for CI/CD and team-wide coverage
- Rationale: No server component needed initially; hooks work immediately for local development

---

## Implementation Phases

### Phase 1: Core Telemetry (Current + Enhancements)

**Status: Complete**

- [x] Task spans with status tracking
- [x] Basic metrics (WIP, throughput)
- [x] State persistence framework
- [x] Percent complete tracking (simple count method)
- [x] Structured logging to Loki (status events only)
- [x] Connect tracker to state manager

### Phase 2: Git Integration (Git Hooks)

**Status: Complete**

- [x] Commit message parsing (PROJ-123, #123 patterns)
- [x] Git hook CLI command (`contextcore git link`)
- [x] Auto-status updates (first commit → in_progress, closes → in_review)
- [x] Git hook generator (`contextcore git hook`)

### Phase 2.5: Git Integration (Webhooks) - Future

- [ ] GitHub webhook endpoint
- [ ] PR tracking and merge detection
- [ ] CI/CD integration

### Phase 3: Interactive Dashboards

- [ ] Sprint dashboard template
- [ ] Project overview dashboard
- [ ] Team workload dashboard
- [ ] Query panel examples
- [ ] Alert rule templates

### Phase 4: External Sync

- [ ] Jira bidirectional sync
- [ ] GitHub Issues sync
- [ ] Linear sync
- [ ] Notion sync

### Phase 5: Intelligence

- [ ] Velocity forecasting
- [ ] Risk detection (scope creep, blocked patterns)
- [ ] Capacity planning
- [ ] Anomaly alerts

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  INPUTS                          CONTEXTCORE                    OUTPUTS     │
│  ──────                          ───────────                    ───────     │
│                                                                              │
│  ┌─────────┐                    ┌───────────────┐              ┌─────────┐ │
│  │   CLI   │───────────────────▶│               │──────────────▶│  Tempo  │ │
│  │ Commands│                    │               │   Spans       │ (Traces)│ │
│  └─────────┘                    │               │              └─────────┘ │
│                                 │               │                           │
│  ┌─────────┐                    │  TaskTracker  │              ┌─────────┐ │
│  │   Git   │───────────────────▶│       +       │──────────────▶│  Mimir  │ │
│  │  Hooks  │                    │  TaskMetrics  │   Metrics     │(Metrics)│ │
│  └─────────┘                    │       +       │              └─────────┘ │
│                                 │  TaskLogger   │                           │
│  ┌─────────┐                    │               │              ┌─────────┐ │
│  │  Jira   │───────────────────▶│               │──────────────▶│  Loki   │ │
│  │  Sync   │                    │               │   Logs        │ (Logs)  │ │
│  └─────────┘                    └───────────────┘              └─────────┘ │
│                                        │                                    │
│  ┌─────────┐                          │                        ┌─────────┐ │
│  │ GitHub  │──────────────────────────┘                        │ Grafana │ │
│  │  Sync   │                          State                    │Dashboard│ │
│  └─────────┘                          │                        └─────────┘ │
│                                        ▼                                    │
│                                 ┌───────────────┐                           │
│                                 │ StateManager  │                           │
│                                 │ (JSON files)  │                           │
│                                 └───────────────┘                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Success Metrics

How we'll know ContextCore is working:

| Metric | Target | Measurement |
|--------|--------|-------------|
| Context switches | -50% | Survey: tools used per task |
| Status report time | -80% | Time to generate weekly report |
| Task → Code traceability | 100% | % commits linked to tasks |
| Blocked task detection | < 1 day | Time to identify blockers |
| Cycle time visibility | Real-time | vs. calculated at sprint end |
| Developer satisfaction | > 4/5 | Survey: "I enjoy using this" |

---

## Appendix: Semantic Conventions

### Task Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `task.id` | string | Unique identifier |
| `task.type` | string | epic\|story\|task\|subtask\|bug\|spike\|incident |
| `task.title` | string | Human-readable title |
| `task.status` | string | backlog\|todo\|in_progress\|in_review\|blocked\|done\|cancelled |
| `task.priority` | string | critical\|high\|medium\|low |
| `task.assignee` | string | Assigned person |
| `task.team` | string | Assigned team |
| `task.story_points` | int | Effort estimate |
| `task.percent_complete` | float | 0-100 progress |
| `task.blocked_by` | string | Blocking task ID |
| `task.blocked_reason` | string | Why blocked |
| `task.due_date` | string | ISO 8601 date |
| `task.labels` | string[] | Tags |
| `task.external_url` | string | Link to external system |

### Sprint Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `sprint.id` | string | Sprint identifier |
| `sprint.name` | string | Sprint name |
| `sprint.goal` | string | Sprint goal |
| `sprint.start_date` | string | Start date |
| `sprint.end_date` | string | End date |
| `sprint.planned_points` | int | Planned capacity |
| `sprint.completed_points` | int | Completed so far |
| `sprint.percent_complete` | float | Progress percentage |

### Log Event Schema

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 timestamp |
| `level` | string | info\|warn\|error |
| `event` | string | Event type (task.created, etc.) |
| `task_id` | string | Task identifier |
| `project_id` | string | Project identifier |
| `sprint_id` | string | Sprint identifier |
| `actor` | string | Who triggered event |
| `actor_type` | string | user\|system\|integration |
| `trigger` | string | How event was triggered |
| `metadata` | object | Event-specific data |
