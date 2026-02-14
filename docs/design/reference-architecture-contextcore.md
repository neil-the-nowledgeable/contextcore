# Reference Architecture: Project Management Observability at ContextCore

> **Blueprint**: [Project Management Observability](blueprint-project-management-observability.md)
> **Organization**: Force Multiplier Labs
> **Status**: Beta / Active Development

---

## Metadata

| Field | Value |
|-------|-------|
| **Organization** | Force Multiplier Labs (ContextCore project) |
| **Industry** | Developer tooling / Observability platforms |
| **Scale** | ~30 Python modules, 11 Grafana dashboards, 7 expansion packs, single-developer project |
| **Environment** | Kubernetes (Kind cluster on Docker Desktop), macOS development |
| **OTel Components Used** | Python SDK, OTLP gRPC exporter, custom resource detector |
| **Backend** | Grafana stack: Tempo (traces), Loki (logs), Mimir (metrics) |
| **Blueprint Implemented** | [Project Management Observability](blueprint-project-management-observability.md) |
| **Status** | Beta — dual-telemetry emission operational, 11 dashboards provisioned |

---

## 1. Summary

ContextCore is a project management observability framework that models project tasks as OpenTelemetry spans. It was built to solve a specific problem: the developer of ContextCore was spending more time compiling status updates than writing code, and AI coding agents (Claude Code) lost all project context between sessions.

By implementing the patterns from the [Project Management Observability blueprint](blueprint-project-management-observability.md), ContextCore now derives project health from artifact metadata, persists AI agent decisions as queryable spans, and provisions dashboards automatically — eliminating manual status reporting entirely.

The project dogfoods itself: ContextCore manages ContextCore.

### Target Audience

| Persona | Pain Point | Value Delivered |
|---------|------------|-----------------|
| **Platform Engineers** | "Every team uses different project tracking, making portfolio health invisible" | Single telemetry model for all project data |
| **Project Managers** | "I spend hours compiling status reports from multiple sources" | Automated dashboards derived from real activity |
| **AI/ML Teams** | "AI agents can't access project context or communicate decisions" | Structured telemetry for agent insights and guidance |
| **Observability Teams** | "Runtime telemetry and project data live in separate silos" | Unified query interface across Tempo/Mimir/Loki |
| **Engineering Leadership** | "No real-time visibility into portfolio health across teams" | Executive dashboards with drill-down to task level |

### Environment Scope

- **Infrastructure**: Kubernetes Kind cluster (`o11y-dev`) on Docker Desktop, single-node development
- **Telemetry backends**: Tempo (traces/spans), Loki (structured logs), Mimir (derived metrics)
- **Integration points**: Claude Code (AI agent), GitHub (source control), Grafana (dashboards)
- **Deployment**: Docker Compose for local dev, Kustomize for Kind cluster

---

## 2. Challenges Addressed

### Challenge 1: Context Loss Between AI Agent Sessions

**Symptoms**:
- Claude Code sessions started from scratch every time — no memory of prior architectural decisions
- Lessons learned during one session (e.g., "the merge function corrupts decorators") had to be rediscovered
- Agent guidance (constraints, preferences) required re-stating in every session

**Impact**:
- Repeated mistakes: the AST merge issue was rediscovered three times before being persisted
- Human time spent re-stating context instead of directing new work
- No audit trail of why architectural choices were made

**Root Cause**: AI agents communicate in ephemeral sessions with no persistent, queryable store for decisions and lessons.

### Challenge 2: Manual Status Reporting During Development

**Symptoms**:
- Phase task completion tracked manually in markdown files
- 11 tasks marked as "done" in tracking but expected deliverable sections not created
- No real-time visibility into which tasks were blocked or stale

**Impact**:
- Status reporting consumed development time on a single-developer project
- "Done" meant "task executed" not "deliverable produced" — a gap discovered only in retrospect
- Blocked tasks (e.g., waiting on AST merge fix) not surfaced until manually reviewed

**Root Cause**: Project status lived in human-readable formats (markdown, issue comments) with no machine-queryable representation.

### Challenge 3: Fragmented Project Metadata

**Symptoms**:
- Project context split across `.contextcore.yaml`, `CLAUDE.md`, `docs/`, and inline code comments
- Risk information in YAML, design decisions in ADR files, semantic conventions in markdown
- No single query could answer "what are the P1 risks for this project?"

**Impact**:
- Context-switching overhead when moving between concerns (coding vs. risk review vs. design)
- AI agents received partial context depending on which files were loaded
- New contributors had no structured onboarding path through the metadata

**Root Cause**: Project management metadata evolved organically across file formats without a unified schema or query interface.

### Challenge 4: Business Context Missing from Observability Config

**Symptoms**:
- All services had identical trace sampling rates regardless of criticality
- Alerts lacked business context (which team owns this? how critical is it?)
- Dashboard provisioning was manual and disconnected from project metadata

**Impact**:
- Critical path services under-observed during development
- On-call context required reading multiple files to understand severity
- Dashboard configuration drifted from project requirements

**Root Cause**: No mechanism to propagate business metadata (criticality, SLO targets, ownership) into observability infrastructure configuration.

---

## 3. Architecture

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ContextCore Architecture                     │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │ TaskTracker   │───▶│  OTLP Exporter   │───▶│     Tempo        │  │
│  │ (Python SDK)  │    │  (gRPC :4317)    │    │  (Trace Store)   │  │
│  │              │    └──────────────────┘    │  - Task spans    │  │
│  │ start_task() │                            │  - Agent insights│  │
│  │ update()     │    ┌──────────────────┐    │  - TraceQL       │  │
│  │ complete()   │    │                  │    └────────┬─────────┘  │
│  └──────────────┘    │                  │             │            │
│                      │                  │             ▼            │
│  ┌──────────────┐    │   Grafana (:3000)│    ┌──────────────────┐  │
│  │ TaskLogger   │    │                  │◀───│  Query Layer     │  │
│  │ (Structured) │    │  11 Dashboards   │    │  TraceQL/LogQL/  │  │
│  │              │    │  - Portfolio     │    │  PromQL          │  │
│  │ log_event()  │    │  - Sprint       │    └──────────────────┘  │
│  │ log_status() │    │  - Progress     │             ▲            │
│  └──────┬───────┘    │  - Operations   │             │            │
│         │            │  - Tasks        │    ┌──────────────────┐  │
│         ▼            │  - Fox Alerts   │    │     Mimir        │  │
│  ┌──────────────┐    │  - Beaver LLM   │    │  (Metrics Store) │  │
│  │ Loki Push API│    │  - Skills       │    │  Derived from    │  │
│  │ (HTTP :3100) │    │  - Installation │    │  Loki via        │  │
│  └──────┬───────┘    │  - Value        │    │  recording rules │  │
│         ▼            │  - Agent Trigger│    └──────────────────┘  │
│  ┌──────────────┐    └──────────────────┘             ▲            │
│  │    Loki      │                                     │            │
│  │ (Log Store)  │─────────────────────────────────────┘            │
│  │ - Events     │  recording rules derive metrics                  │
│  │ - Status     │                                                  │
│  └──────────────┘                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Components

| Component | Role | OTel Integration |
|-----------|------|-----------------|
| **TaskTracker** | Emits task lifecycle as spans | Python SDK, OTLP gRPC export to Tempo |
| **TaskLogger** | Emits structured log events | Loki push API with historical timestamps |
| **InsightEmitter** | Persists agent decisions/lessons as spans | Span attributes following `agent.*` conventions |
| **InsightQuerier** | Retrieves prior agent context | TraceQL queries against Tempo |
| **GuidanceReader** | Reads human constraints for agents | Queries active constraints from telemetry |
| **Resource Detector** | Attaches K8s metadata to all telemetry | Custom OTel resource detector |
| **Dashboard Provisioner** | Auto-provisions Grafana dashboards | Grafana HTTP API, idempotent |
| **Demo Generator** | Emits historical demo data | Dual-emit: spans to Tempo + logs to Loki |

### Data Flow

1. **Task events**: `TaskTracker.start_task()` creates a span via the OTel Python SDK. Status transitions emit span events. `complete_task()` ends the span. All spans export via OTLP gRPC to Tempo.

2. **Structured logs**: `TaskLogger.log_event()` emits structured JSON logs pushed to Loki via HTTP push API. Logs carry the same `project.id`, `task.id` attributes as spans for correlation.

3. **Metrics derivation**: Loki recording rules process structured logs into time-series metrics stored in Mimir. Metrics include task counts by status, velocity, cycle time. No metrics are directly emitted — all are derived.

4. **Querying**: Grafana dashboards query all three backends: TraceQL for task hierarchy and agent insights, LogQL for event streams, PromQL for derived metrics.

---

## 4. Semantic Conventions Used

### Standard OTel Conventions

| Attribute | Usage | Reference |
|-----------|-------|-----------|
| `service.name` | Set to `contextcore` for all telemetry | [Resource SemConv](https://opentelemetry.io/docs/specs/semconv/resource/#service) |
| `service.version` | Package version | Resource SemConv |
| `deployment.environment` | `development`, `staging`, `production` | Resource SemConv |

### Custom/Extended Conventions

| Namespace | Attribute | Type | Description |
|-----------|-----------|------|-------------|
| `project.*` | `project.id` | string | Unique project identifier |
| | `project.epic` | string | Parent epic/initiative |
| `task.*` | `task.id` | string | Unique task identifier (e.g., `PROJ-123`) |
| | `task.status` | string | Current status: `pending`, `in_progress`, `blocked`, `in_review`, `done` |
| | `task.type` | string | Task type: `epic`, `story`, `task`, `subtask`, `bug` |
| | `task.blocked_reason` | string | Why the task is blocked |
| | `task.percent_complete` | float | 0.0-100.0 completion percentage |
| `sprint.*` | `sprint.id` | string | Sprint identifier |
| | `sprint.velocity` | int | Story points completed |
| `business.*` | `business.criticality` | string | `critical`, `high`, `medium`, `low` |
| | `business.owner` | string | Owning team or individual |
| `requirement.*` | `requirement.latency_p99` | string | P99 latency SLO |
| | `requirement.availability` | string | Availability target (e.g., `99.9%`) |
| `risk.*` | `risk.type` | string | Risk category |
| | `risk.priority` | string | `P1`, `P2`, `P3`, `P4` |
| `agent.*` | `agent.id` | string | Agent session identifier |
| | `agent.insight.type` | string | `decision`, `lesson`, `question`, `handoff` |
| | `agent.insight.confidence` | float | 0.0-1.0 confidence score |
| | `agent.insight.summary` | string | Human-readable description |

### OTel GenAI Alignment

ContextCore is migrating to [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). During migration, dual-emit is controlled by `CONTEXTCORE_EMIT_MODE`:

| Mode | Behavior |
|------|----------|
| `dual` (default) | Emits both `agent.*` and `gen_ai.*` attributes |
| `legacy` | Emits only `agent.*` (rollback option) |
| `otel` | Emits only `gen_ai.*` (target state) |

---

## 5. Implementation

### Action 1: ProjectContext CRD

**Challenges Addressed**: 3, 4

A Kubernetes Custom Resource Definition serves as the single source of truth for project metadata.

```yaml
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
    value: revenue-primary
  requirements:
    availability: "99.95"
    latencyP99: "200ms"
  risks:
    - risk: "Payment gateway timeout"
      priority: P1
      mitigation: "Circuit breaker with fallback"
  design:
    adr: "docs/adr/001-event-driven-checkout.md"
```

For non-Kubernetes environments, ContextCore also supports `.contextcore.yaml` as a file-based project context that provides the same schema.

### Action 2: TaskTracker SDK

**Challenges Addressed**: 1, 2

The `TaskTracker` emits task lifecycle events as OTel spans.

```python
from contextcore import TaskTracker

tracker = TaskTracker(
    project_id="commerce-platform",
    otlp_endpoint="http://tempo:4317"
)

# Start a task (creates span)
tracker.start_task(
    task_id="PROJ-123",
    title="Implement checkout flow",
    task_type="story",
    parent_id="EPIC-42"
)

# Update status (adds span event)
tracker.update_status("PROJ-123", "in_progress")

# Complete task (ends span)
tracker.complete_task("PROJ-123")
```

### Action 3: Agent Insight Emission

**Challenges Addressed**: 1

The `InsightEmitter` persists AI agent decisions and lessons as queryable spans.

```python
from contextcore.agent import InsightEmitter

emitter = InsightEmitter(
    project_id="commerce-platform",
    agent_id="claude-checkout-session"
)

# Emit a decision
emitter.emit_decision(
    summary="Selected event-driven architecture for order processing",
    confidence=0.92,
    rationale="Decouples payment from fulfillment, enables retry",
    context={"file": "src/checkout/events.py"}
)

# Emit a lesson learned
emitter.emit_lesson(
    summary="Always mock payment gateway in integration tests",
    category="testing",
    applies_to=["src/checkout/tests/"]
)
```

The complementary `InsightQuerier` retrieves prior context:

```python
from contextcore.agent import InsightQuerier

querier = InsightQuerier()
decisions = querier.query(
    project_id="commerce-platform",
    insight_type="decision",
    time_range="30d"
)
```

### Action 4: Dual Telemetry Emission

**Challenges Addressed**: 2

The `HistoricalTaskTracker` and `HistoricalTaskLogger` emit both spans and structured logs, enabling full dashboard coverage.

- **Spans to Tempo**: Task hierarchy, timing, and TraceQL queries
- **Logs to Loki**: Event streams, status changes, and metrics derivation via recording rules
- **Metrics in Mimir**: Derived from Loki logs, not directly emitted

This dual-emit architecture was a key design decision — the portfolio dashboard requires data from both Tempo (hierarchy queries) and Loki (event stream queries), with Mimir providing time-series aggregations derived from Loki recording rules.

### Action 5: Dashboard Provisioning

**Challenges Addressed**: 2, 4

11 dashboards provisioned to Grafana via the provisioner API:

```bash
# Auto-provision all dashboards
contextcore dashboards provision --grafana-url http://localhost:3000

# Or via Helm
helm install contextcore contextcore/contextcore \
  --set grafana.url=http://grafana:3000 \
  --set dashboards.autoProvision=true
```

### Action 6: Business-Driven Configuration

**Challenges Addressed**: 4

The ContextCore controller watches `ProjectContext` resources and derives observability configuration:

```yaml
spec:
  business:
    criticality: critical
  observability:
    # Auto-derived from criticality if not specified
    traceSampling: 1.0      # 100% for critical
    metricsInterval: 10s    # Frequent for critical
    alertChannels:
      - commerce-oncall
```

---

## 6. Dashboards and Queries

### Key Queries

| Purpose | Language | Query |
|---------|----------|-------|
| Find all tasks for a project | TraceQL | `{ span.project.id = "contextcore" && span.task.id != "" }` |
| Find blocked tasks | TraceQL | `{ span.task.status = "blocked" }` |
| Agent decisions in last 30d | TraceQL | `{ span.agent.insight.type = "decision" && span.project.id = "contextcore" }` |
| Task status events | LogQL | `{job="contextcore"} \| json \| task_status != ""` |
| Task completion rate | PromQL | `rate(task_count_by_status{project="contextcore", "task.status"="done"}[1h])` |
| Installation completeness | PromQL | `contextcore_install_completeness_percent` |

### Dashboards

| Dashboard | Audience | Key Panels | Datasources |
|-----------|----------|------------|-------------|
| **Project Portfolio Overview** | Leadership, PMs | Cross-project health matrix, blocked tasks, velocity | Loki, Mimir |
| **Project Progress** | Engineering | Sprint burndown, task completion, cycle time | Tempo |
| **Sprint Metrics** | Scrum masters | Velocity, burndown, scope change | Tempo |
| **Project Operations** | Platform engineers | Operational health, error rates, SLO status | Tempo |
| **Installation Verification** | DevOps | Component health, verification results | Mimir |
| **Value Capabilities Explorer** | Product | Feature coverage, value metrics | Tempo |
| **Project Tasks** | Engineering | Task board, status transitions, hierarchy | Tempo |
| **Fox Alert Automation** | SRE/on-call | Alert processing, action dispatch, latency | Tempo, Loki, Mimir |
| **Lead Contractor Progress** | Dev leads | Code generation tracking, LLM cost | Tempo, Mimir |
| **Skills Browser** | Agents, devs | Available skills, usage patterns | Tempo |
| **Agent Trigger** | Automation | Trigger events, action results | Loki |

---

## 7. Results

### Quantitative Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Time spent on status reporting | ~3 hrs/week | 0 hrs/week | Eliminated |
| Agent context re-establishment | ~15 min/session | ~1 min (query prior insights) | 93% reduction |
| Dashboard provisioning | Manual per dashboard | Single command, idempotent | Automated |
| Dashboards provisioned | 0 | 11 (7 core + 4 expansion) | Full coverage |
| OTel SemConv alignment | 0% | 90%+ (dual-emit in progress) | Standards-aligned |

### Qualitative Results

- **Dogfooding validates the model**: Using ContextCore to manage ContextCore development surfaced real design issues (e.g., "execution != completion" gap where 11 tasks were marked done but deliverables weren't produced)
- **Agent persistence changes workflow**: Claude Code sessions that query prior decisions make meaningfully better architectural choices — the AST merge decision was informed by three prior sessions of lessons learned
- **Dual telemetry proved necessary**: Initial spans-only approach left the portfolio dashboard empty. Adding Loki logs enabled metrics derivation that made dashboards useful
- **Expansion pack ecosystem emerged organically**: The animal-naming convention (Spider, Rabbit, Fox, Coyote, Beaver, Squirrel) with Anishinaabe translations created a memorable, navigable component taxonomy

---

## 8. Lessons Learned

### What Worked Well

- **Tasks-as-spans mental model**: The structural similarity between tasks and spans (start, end, status, hierarchy, events) made the mapping intuitive. Engineers familiar with distributed tracing immediately understood the project management model.
- **CRD as source of truth**: Putting project metadata in a Kubernetes CRD meant it was versioned, auditable, and accessible to both humans and controllers.
- **Dual-emit migration strategy**: Emitting both `agent.*` and `gen_ai.*` attributes during the OTel GenAI migration allowed dashboard updates without breaking existing queries.
- **AST-based code merge**: Replacing text-based Python file merging with `ast.parse()`-based merging eliminated an entire class of code corruption bugs (P1 risk resolved).

### What We'd Do Differently

- **Start with dual telemetry from day one**: The spans-only initial approach required backfilling Loki emission later. The portfolio dashboard was empty until logs were added.
- **Explicit dependency manifests earlier**: The Beaver dashboard referenced a Grafana plugin (`yesoreyeram-infinity-datasource`) not configured in the cluster. Design-time dependencies should flow to deploy-time manifests from the start.
- **Single deployment source**: Running two deployment directories (DEV and TEST) targeting the same Kind cluster caused config drift and authentication confusion. Single source of truth from the beginning.
- **Deliverable validation, not just execution tracking**: Marking tasks "done" when the code ran successfully missed the fact that expected documents weren't created. Completion criteria should include deliverable verification.

### Surprises

- **Execution != Completion**: 11 phase tasks were marked "done" in Tempo, but the expected document sections were never created. This revealed a fundamental gap in task-based tracking — running successfully is not the same as producing the expected output.
- **Docker Desktop file sync unreliability**: Kind node file mounts via Docker Desktop don't reliably sync changes. Plugin code updates required manual `docker cp` to Kind nodes, even after pod restarts.
- **Text-based merge is fundamentally broken for Python**: The `merge_files_intelligently()` function seemed to work until it encountered decorators, multi-line strings, and class dependency ordering. String-based parsing cannot handle Python's structural complexity — AST parsing is the minimum viable approach.

---

## 9. Value by Role

| Role | Start Here | Quick Win | Full Value |
|------|------------|-----------|------------|
| **Platform Engineer** | Install ContextCore, provision dashboards | Portfolio dashboard shows project health | Automated config derivation from business metadata |
| **Project Manager** | View Project Progress dashboard | Real-time task status without status meetings | Velocity trends, cycle time analysis, blocker alerts |
| **AI/ML Engineer** | Configure InsightEmitter in agent | Agent decisions persist across sessions | Full context continuity, cross-agent handoffs |
| **On-Call Engineer** | Check Fox Alert Automation dashboard | Alerts include business context | Automated incident context enrichment |
| **Executive** | View Portfolio Overview | Cross-project health at a glance | Drill-down from portfolio to individual tasks |

---

## 10. Try It Yourself

### Prerequisites

- Docker Desktop with Kubernetes enabled (or Kind)
- Python 3.9+
- `pip3`, `make`

### Quick Start

```bash
# Clone the repository
git clone https://github.com/neil-the-nowledgable/contextcore.git
cd contextcore

# Install ContextCore
pip3 install -e ".[dev]"

# Full setup: start observability stack, wait for ready, seed metrics
make full-setup

# Or step by step:
make up              # Start Docker Compose stack (Grafana, Tempo, Loki, Mimir)
make wait-ready      # Wait for all services to be healthy
contextcore install init   # Verify installation + seed dashboard metrics
```

### Explore

1. **Portfolio Dashboard**: Open `http://localhost:3000/d/contextcore-portfolio` — cross-project health overview
2. **Installation Dashboard**: Open `http://localhost:3000/d/contextcore-installation` — verification status
3. **Query task spans**:
   ```
   { span.project.id = "contextcore" && span.task.id != "" }
   ```
4. **Generate demo data**:
   ```bash
   contextcore demo generate --project contextcore --days 30
   ```
5. **Check agent insights**:
   ```
   { span.agent.insight.type = "decision" }
   ```

### Cleanup

```bash
make down    # Stop Docker Compose stack
```

---

*This reference architecture implements the [Project Management Observability blueprint](blueprint-project-management-observability.md) following the [OTel Reference Architecture Template](https://github.com/open-telemetry/sig-end-user/issues/236).*
