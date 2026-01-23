# ContextCore

### Spider (Asabikeshiinh) — *"Little net maker"*

**One system. Every audience. Always current.**

The first project management system built for human-agent parity.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-native-blueviolet)](https://opentelemetry.io/)
[![OTLP](https://img.shields.io/badge/OTLP-compatible-green)](https://opentelemetry.io/docs/specs/otlp/)

## What is ContextCore?

**ContextCore** is a unified communication layer where humans and AI agents share the same knowledge. Project metadata, agent insights, and operational context—all queryable, all persistent, all in your existing observability stack.

### The Problem

AI agents generate valuable insights during development—architectural decisions, root cause analyses, code recommendations. But that knowledge **dies when the session ends**:

- Can't query what agents discovered
- Other agents can't access it
- Every new session starts from zero

This is the **agent data silo**—and it joins the context gap we've always had between project management and operations.

### The Solution

ContextCore stores agent insights alongside project and operational data in your observability stack:

| Problem | ContextCore Solution |
|---------|---------------------|
| Agent insights in chat transcripts | Agent insights as OTel spans in Tempo |
| Can't query agent knowledge | TraceQL: `{ insight.type = "decision" }` |
| Repeat constraints every session | Set guidance once in CRD, all sessions respect it |
| Different formats for different audiences | Same data, personalized presentation |
| Developers manually update Jira | Status derived from commits, PRs, CI |
| PM tools disconnected from ops | Unified in observability stack |

## Key Benefits

### 1. Agent-to-Agent Communication

Agents emit insights as OpenTelemetry spans. Other agents query them. Knowledge persists.

```python
from contextcore.agent import InsightEmitter, InsightQuerier

# Claude emits a decision
emitter = InsightEmitter(project_id="checkout", agent_id="claude")
emitter.emit_decision("Selected event-driven architecture", confidence=0.92)

# GPT queries Claude's findings
querier = InsightQuerier()
decisions = querier.query(project_id="checkout", insight_type="decision")
```

### 2. Human-to-Agent Guidance

Set constraints, focus areas, and questions in a Kubernetes CRD. Persists across all agent sessions.

```yaml
agentGuidance:
  constraints:
    - id: no-auth-changes
      rule: "No authentication changes without approval"
      severity: blocking
  questions:
    - id: latency-cause
      question: "What's causing the checkout latency spike?"
      priority: critical
```

### 3. Query Over Markdown

Real-time queries instead of loading stale markdown files:

| Markdown Approach | ContextCore Approach |
|------------------|---------------------|
| Load entire DECISIONS.md (~5000 tokens) | Query exactly what's needed (~200 tokens) |
| Hope it's current | Real-time, streaming |
| No filtering | "Critical blockers only" |
| Full file or nothing | Temporal queries ("last 7 days") |

### 4. Personalized Presentation

Same underlying data, different views for each audience:

| Audience | View |
|----------|------|
| **Executive** | "Blockers resolved: 3" |
| **Developer** | "Root cause: N+1 query in payment_verify (trace: abc123)" |
| **Agent** | `insight_id: xyz, type: analysis, confidence: 0.95` |

### 5. Eliminate Developer Toil

**Stop asking developers to write status reports.** The information already exists:

| Artifact | Derived Status |
|----------|---------------|
| First commit on task | `todo` → `in_progress` |
| PR opened | `in_progress` → `in_review` |
| PR merged | `in_review` → `done` |
| CI failure | Task marked `at_risk` |
| No commits for 7 days | Stale task alert |

### 6. Business-Aware Observability

Auto-generate observability strategies from project context:

| Business Context | Generated Strategy |
|-----------------|-------------------|
| `criticality: critical` | 100% trace sampling, P1 alerts |
| `business.owner: commerce-team` | Alert routing to #commerce-oncall |
| `design.adr: ADR-015` | Runbook link in alert annotations |

## Differentiation: Not Another Tool

### Why Observability Infrastructure, Not a New Portal?

Tools like Backstage require adopting a **new system**. ContextCore takes a different approach:

| Dimension | Developer Portals | ContextCore |
|-----------|------------------|-------------|
| Infrastructure | New app to deploy | Uses existing observability stack |
| Database | New persistence layer | Tempo, Mimir, Loki (already running) |
| Authentication | Another login | Same Grafana access |
| Adoption | Migrate teams | Zero new tools |

**The insight**: Given the infrastructure required for large systems, it's more feasible to leverage existing observability tools than to shoe-horn operations into PM tools.

### The Natural Evolution

```
2010s: Logging     → "Centralize logs"        → ELK, Splunk
2015s: Metrics     → "Add time-series"        → Prometheus
2018s: Tracing     → "Trace across services"  → Jaeger
2019:  OTel        → "Unify with semantics"   → OpenTelemetry
2024+: ContextCore → "Extend to project mgmt" → Tasks as spans
```

## How It Works

### Tasks as Spans

Project tasks are modeled as OpenTelemetry spans:

```python
from contextcore import TaskTracker

tracker = TaskTracker(project="my-project")

# Start a task (creates span)
tracker.start_task(
    task_id="PROJ-123",
    title="Implement OAuth",
    task_type="story",
    priority="high",
)

# Status changes become span events
tracker.update_status("PROJ-123", "in_progress")

# Complete task (ends span)
tracker.complete_task("PROJ-123")
```

### Automatic Git Integration

```bash
# Install git hook for automatic commit linking
contextcore git hook --type post-commit

# Now commits automatically:
# - Link to referenced tasks (PROJ-123)
# - Update task status (first commit → in_progress)
# - Create span events for commits
```

### Structured Logging to Loki

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "event": "task.status_changed",
  "task_id": "PROJ-123",
  "from_status": "todo",
  "to_status": "in_progress",
  "project_id": "my-project"
}
```

### Derived Metrics

Query project health with PromQL:

```promql
# Work in progress
task_wip{project_id="my-project"}

# Cycle time histogram
histogram_quantile(0.95, task_cycle_time_bucket{project_id="my-project"})

# Blocked tasks
task_count_by_status{status="blocked", project_id="my-project"}
```

## Quick Start

### Install

```bash
# Install ContextCore SDK
pip install contextcore

# Apply CRD to Kubernetes
kubectl apply -f https://contextcore.io/crds/projectcontext-v2.yaml

# Provision dashboards to Grafana (auto-detects local Grafana)
contextcore dashboards provision
```

This installs the SDK, CRD, and provisions the **Project Portfolio Overview** and **Project Details** dashboards to your Grafana instance.

### For Humans: Track Tasks

```bash
# Start a task
contextcore task start --id PROJ-123 --title "Implement feature" --type story

# Update status
contextcore task update --id PROJ-123 --status in_progress

# Complete
contextcore task complete --id PROJ-123
```

### For Agents: Query and Emit Insights

```python
from contextcore.agent import InsightQuerier, InsightEmitter, GuidanceReader

# Query what other agents discovered
querier = InsightQuerier()
decisions = querier.query(project_id="my-project", insight_type="decision", time_range="7d")

# Check constraints before modifying files
reader = GuidanceReader(project_id="my-project")
constraints = reader.get_constraints_for_path("src/auth/")

# Emit your insights
emitter = InsightEmitter(project_id="my-project", agent_id="claude")
emitter.emit_decision("Selected async pattern", confidence=0.9)
```

### View in Grafana

Tasks and insights appear in Tempo, queryable via TraceQL:

```
# Find blocked tasks
{ task.status = "blocked" && task.type = "story" }

# Find agent decisions
{ insight.type = "decision" && insight.confidence > 0.9 }

# Find insights for a specific project
{ project.id = "checkout" && span.kind = "agent_insight" }
```

## Built-in Dashboards

ContextCore automatically provisions two Grafana dashboards on installation:

### Project Portfolio Overview

High-level view for executives and program managers:

| Panel | Description |
|-------|-------------|
| **KPI Stats** | Active projects, on-track count, at-risk count, blocked tasks |
| **Health Matrix** | Sortable table with traffic-light status per project |
| **Progress Gauges** | Visual grid of project completion percentages |
| **Velocity Trend** | Sprint-over-sprint comparison (planned vs actual) |
| **Blocked Tasks** | All blockers with duration and reason |
| **Activity Feed** | Live stream of task events across all projects |

### Project Details (Drill-down)

Deep-dive view for project managers and team leads:

| Panel | Description |
|-------|-------------|
| **Sprint Burndown** | Ideal vs actual story point burn |
| **Kanban Board** | Visual task board grouped by epic/story |
| **Work Breakdown** | Hierarchical epic → story → task tree with progress bars |
| **Blocker Analysis** | Full context on blocked items with impact analysis |
| **Team Workload** | Story points per assignee (capacity view) |
| **Cycle Time & Throughput** | Flow metrics for process improvement |
| **Timeline/Gantt** | Task spans over time with blocker annotations |
| **Activity Log** | Filterable event stream for the project |

### Dashboard Installation

Dashboards are automatically provisioned when ContextCore is installed:

```bash
# Install with dashboards (default)
contextcore install --with-dashboards

# Skip dashboard provisioning
contextcore install --skip-dashboards

# Provision dashboards to existing Grafana
contextcore dashboards provision --grafana-url http://localhost:3000
```

See [docs/dashboards/](docs/dashboards/) for full specifications.

## Vendor Agnostic

ContextCore is **not an observability backend**. It exports via OTLP to any compatible system:

**Open Source:**
- Jaeger, Zipkin (traces)
- Prometheus (metrics)
- Loki (logs)

**Commercial:**
- Datadog
- New Relic
- Honeycomb
- Dynatrace

**Reference Implementation:**
- Grafana + Tempo + Mimir + Loki (ships ready for local use)

```bash
# Configure any OTLP endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT="http://your-backend:4317"
```

## One System Serves All Audiences

| Stakeholder | What They See |
|-------------|---------------|
| **AI Agents** | Typed schemas, prior insights, guidance constraints |
| **Developers** | Technical detail, trace IDs, code references |
| **Project Managers** | Sprint burndown, WIP, blockers |
| **Leadership** | Portfolio health, agent utilization |
| **Operators** | Incident context, agent recommendations |

**Humans query Grafana. Agents query TraceQL. Same data. Same location.**

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SOURCES                                         │
│                                                                              │
│   Humans                          AI Agents                   Artifacts     │
│   ├─ Guidance (CRD)               ├─ Claude                   ├─ Commits    │
│   ├─ Constraints                  ├─ GPT                      ├─ PRs        │
│   └─ Questions                    └─ Custom                   └─ CI/CD      │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CONTEXTCORE SDK                                          │
│                                                                              │
│  For Humans                           For Agents                             │
│  ├─ TaskTracker (spans)               ├─ InsightEmitter                      │
│  ├─ TaskLogger (logs)                 ├─ InsightQuerier                      │
│  └─ Git Integration                   ├─ GuidanceReader                      │
│                                       └─ HandoffManager                      │
│                                                                              │
│  ProjectContext CRD v2 • Agent Semantic Conventions • Personalization       │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   │ OTLP
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     OBSERVABILITY STACK                                      │
│                                                                              │
│   Tempo (traces + insights) • Mimir (metrics) • Loki (logs)                 │
│   Grafana (humans) • TraceQL (agents) • Any OTLP backend                    │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  AUTO-PROVISIONED DASHBOARDS                                        │   │
│   │  ├─ Project Portfolio Overview (all projects, health matrix)        │   │
│   │  └─ Project Details (drill-down: burndown, kanban, blockers)        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CONSUMERS                                          │
│                                                                              │
│   Executives         Developers        Operators        AI Agents           │
│   └─ Portfolio       └─ Task Detail    └─ Alerts        └─ TraceQL          │
│      Dashboard          Dashboard                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

## CLI Reference

```bash
# Task tracking
contextcore task start --id PROJ-123 --title "Feature" --type story
contextcore task update --id PROJ-123 --status in_progress
contextcore task block --id PROJ-123 --reason "Waiting on API"
contextcore task complete --id PROJ-123

# Sprint tracking
contextcore sprint start --id sprint-3 --name "Sprint 3" --goal "Auth flow"
contextcore sprint end --id sprint-3 --points 21

# Git integration
contextcore git hook --type post-commit
contextcore git link --commit abc123 --message "feat: auth [PROJ-123]"
contextcore git test --message "fixes PROJ-456"

# Metrics
contextcore metrics summary --project my-project
contextcore metrics wip --project my-project
```

## Semantic Conventions

ContextCore extends OpenTelemetry semantic conventions:

| Namespace | Purpose | Examples |
|-----------|---------|----------|
| `task.*` | Project tasks | `task.id`, `task.status`, `task.type` |
| `sprint.*` | Sprint tracking | `sprint.id`, `sprint.goal` |
| `project.*` | Project metadata | `project.id`, `project.epic` |
| `business.*` | Business context | `business.criticality`, `business.owner` |
| `agent.*` | Agent identity | `agent.id`, `agent.session_id`, `agent.type` |
| `insight.*` | Agent insights | `insight.type`, `insight.confidence`, `insight.audience` |
| `guidance.*` | Human direction | `guidance.constraint_id`, `guidance.question_id` |
| `handoff.*` | Agent delegation | `handoff.from_agent`, `handoff.to_agent` |

See [docs/semantic-conventions.md](docs/semantic-conventions.md) and [docs/agent-semantic-conventions.md](docs/agent-semantic-conventions.md) for full reference.

## Ecosystem

ContextCore is part of a growing ecosystem of observability tools, each named after an animal with its Anishinaabe (Ojibwe) name honoring the indigenous peoples of Michigan and the Great Lakes region.

| Project | Animal | Anishinaabe | Purpose |
|---------|--------|-------------|---------|
| **ContextCore** | Spider | Asabikeshiinh | Core framework—weaving project artifacts into observability |
| **[contextcore-rabbit](https://github.com/contextcore/contextcore-rabbit)** | Rabbit | Waabooz | Core alert automation framework (formerly Hermes) |
| **[contextcore-fox](https://github.com/contextcore/contextcore-fox)** | Fox | Waagosh | ContextCore integration for alert automation |
| **[contextcore-coyote](https://github.com/contextcore/contextcore-coyote)** | Coyote | Wiisagi-ma'iingan | Multi-agent incident resolution pipeline |
| **[contextcore-beaver](https://github.com/contextcore/contextcore-beaver)** | Beaver | Amik | LLM provider abstraction (formerly startd8) |
| **[contextcore-squirrel](https://github.com/contextcore/contextcore-squirrel)** | Squirrel | Ajidamoo | Skills library for token-efficient agent discovery |

- [Naming Convention](docs/NAMING_CONVENTION.md) — Why we use animal names and Anishinaabe language
- [Expansion Packs](docs/EXPANSION_PACKS.md) — Registry of official expansion packs

## Documentation

- [CLAUDE.md](CLAUDE.md) — Technical documentation and design principles
- [docs/PROJECT_MANAGEMENT_VISION.md](docs/PROJECT_MANAGEMENT_VISION.md) — Full vision and goals
- [docs/semantic-conventions.md](docs/semantic-conventions.md) — Attribute reference
- [docs/agent-semantic-conventions.md](docs/agent-semantic-conventions.md) — Agent attribute reference
- [docs/agent-communication-protocol.md](docs/agent-communication-protocol.md) — Agent integration protocols
- [crds/projectcontext-v2.yaml](crds/projectcontext-v2.yaml) — CRD schema with agent guidance

### Dashboard Specifications

- [docs/dashboards/PROJECT_PORTFOLIO_OVERVIEW.md](docs/dashboards/PROJECT_PORTFOLIO_OVERVIEW.md) — Portfolio dashboard design
- [docs/dashboards/PROJECT_DETAILS.md](docs/dashboards/PROJECT_DETAILS.md) — Project drill-down dashboard design

## Requirements

- Python 3.11+
- Any OTLP-compatible backend (Grafana stack reference implementation included)

## Installation

```bash
# Core SDK
pip install contextcore

# Development
pip install contextcore[dev]
```

## License

MIT

---

**ContextCore** — The first project management system built for human-agent parity. Same metadata, same queries—for humans AND agents. One system. Every audience. Always current.
