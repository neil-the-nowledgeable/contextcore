# Blueprint: Project Management Observability

> **Domain**: Project Management
> **Template**: Rumelt-based (Diagnosis / Guiding Policies / Coherent Actions)
> **Status**: Draft
> **Reference Implementation**: [ContextCore Reference Architecture](reference-architecture-contextcore.md)

---

## Introduction

Project management telemetry and runtime observability have evolved as separate disciplines. Engineering teams track tasks in issue trackers, communicate status in meetings, and maintain project context in wikis — none of which are queryable by the same tools used to debug production incidents. The result is a gap between "what the team is building" and "what the system is doing."

This blueprint is for **platform engineering teams, project managers, and AI/ML teams** operating in environments where:

- Multiple projects run concurrently, each with different priorities and risk profiles
- Status reporting is manual and based on human estimates rather than artifact signals
- AI agents assist with development but lose context between sessions
- Observability infrastructure (trace stores, metrics backends, log aggregators) is already deployed

The achievable end state is **project management as telemetry**: task lifecycles stored as spans, project health derived from artifact metadata rather than manual reports, agent decisions persisted as queryable telemetry, and observability configuration driven by business context.

The business benefits are direct: elimination of manual status reporting, real-time visibility into blocked work, persistent context for AI agents across sessions, and observability investment that scales with business criticality.

---

## Summary

This blueprint delivers four capabilities:

**Task lifecycle as trace spans.** Tasks share the same structure as distributed trace spans — start time, end time, status, hierarchy, events. Storing tasks in trace infrastructure enables unified querying across project data and runtime telemetry, with time-series persistence and configurable retention.

**Status derived from artifacts.** Instead of asking engineers for status updates, derive task state from existing signals: commits, pull requests, CI results, and deployment events. This eliminates manual reporting while producing more accurate, real-time data.

**Agent insight persistence.** AI agent decisions, lessons learned, and unresolved questions are stored as spans, making them queryable across sessions and visible to both humans and other agents. This solves the context loss problem in agent-assisted development.

**Business-driven observability configuration.** Business metadata (criticality, SLO requirements, risk profile) propagates to technical configuration: sampling rates, alert thresholds, dashboard placement. Observability investment automatically scales with business importance.

---

## Diagnosis: Common Challenges

### Challenge 1: Fragmented Project Metadata

**Symptoms**:
- Project context scattered across issue trackers, wikis, chat tools, and tribal knowledge
- AI agents lack access to project requirements, risks, and design decisions
- No correlation between runtime errors and the tasks that introduced them

**Impact**:
- Engineers waste hours per week searching for project context
- Incidents take longer to resolve due to missing business context
- AI agents make recommendations without understanding project constraints

**Root Cause**: Project management systems and observability systems evolved separately, with no shared data model.

### Challenge 2: Manual Status Reporting

**Symptoms**:
- Weekly status meetings require manual data compilation
- Progress percentages are estimates, not measurements
- Blocked tasks discovered in meetings, not in real-time

**Impact**:
- Significant engineering time spent on status reporting
- Stale information drives decisions
- Blocked work remains unaddressed for days

**Root Cause**: Project status exists in human-readable formats (tickets, docs), not machine-queryable telemetry.

### Challenge 3: Human-Agent Information Asymmetry

**Symptoms**:
- AI agents can't access the same project context humans see in issue trackers and wikis
- Agent decisions and lessons learned disappear when sessions end
- No way for humans to guide agent behavior with project constraints

**Impact**:
- Agents repeat mistakes or contradict prior decisions
- Human guidance requires re-stating context every session
- No audit trail of agent reasoning

**Root Cause**: Agent communication lacks structured, persistent telemetry.

### Challenge 4: Business-Technical Disconnect

**Symptoms**:
- Observability configuration doesn't reflect business importance
- Critical services have same sampling rates as internal tools
- Alerts don't include business context for prioritization

**Impact**:
- Critical incidents under-sampled, making debugging harder
- On-call engineers lack business context for triage
- Executive dashboards require manual data export

**Root Cause**: No mechanism to propagate business metadata into observability configuration.

---

## Guiding Policies

### Policy 1: Model Tasks as Spans

**Challenges Addressed**: 1, 2

Tasks share the same structure as distributed trace spans:
- Start time, end time, duration
- Status (pending -> in_progress -> done)
- Hierarchy (epic -> story -> task -> subtask)
- Events (status changes, blocks, comments)

By storing tasks in trace infrastructure:
- Unified querying via TraceQL/PromQL/LogQL
- Time-series persistence with configurable retention
- Correlation with runtime spans via shared project identifiers

```
Traditional Approach              Tasks-as-Spans Approach
──────────────────────            ─────────────────────────
Issue tracker (tasks)             Trace store
   ↓ manual                         ├─ Epic Span
Spreadsheet (status)                │   ├─ Story Span
   ↓ manual                         │   │   ├─ Task Span
Dashboard (metrics)                  │   │   └─ Task Span
   ↓ separate                       │   └─ ...
Trace store (runtime)                └─ Queryable alongside runtime traces
                                  Same store → Same queries → Same dashboards
```

### Policy 2: Derive Status from Artifacts

**Challenges Addressed**: 2, 4

Instead of asking "What's the status?", derive it from existing signals:
- Commits linked to task IDs -> Work started
- PR merged -> Task complete
- CI failure -> Task blocked
- No activity in N days -> Stale detection

This eliminates manual reporting while providing more accurate, real-time data.

| Artifact Signal | Derived Status | Attributes Set |
|-----------------|----------------|----------------|
| Commit referencing task ID | `in_progress` | `task.last_commit_sha` |
| Pull request merged | `done` | `task.completed_at` |
| CI pipeline failure | `blocked` | `task.blocked_reason` |
| Review requested | `in_review` | `task.reviewer` |

### Policy 3: Store Agent Insights as Telemetry

**Challenges Addressed**: 3

AI agent decisions, lessons learned, and questions are valuable context that should persist beyond session boundaries. By storing them as spans:

- **Decisions**: Architectural choices with confidence scores
- **Lessons**: Patterns learned that apply to future work
- **Questions**: Unresolved items requiring human input
- **Handoffs**: Context for agent-to-agent or agent-to-human transitions

```yaml
# Agent insight stored as span attributes
agent.id: "agent-session-identifier"
agent.insight.type: "decision"
agent.insight.summary: "Selected event-driven architecture for checkout"
agent.insight.confidence: 0.92
agent.insight.applies_to: ["src/checkout/events.py"]
```

### Policy 4: Propagate Business Context to Observability Config

**Challenges Addressed**: 4

Business metadata should drive technical decisions:

| Business Input | Technical Output |
|----------------|------------------|
| `criticality: critical` | 100% trace sampling, P1 alert priority |
| `criticality: high` | 50% trace sampling, P2 alert priority |
| `criticality: medium` | 10% trace sampling, P3 alert priority |
| Latency P99 requirement | Alert threshold rule |
| P1 risk designation | Extended audit logging |

This ensures observability investment scales with business importance.

---

## Coherent Actions

### Action 1: Define a Structured Project Context Schema

**Policies Supported**: 1, 4

Create a machine-readable schema for project metadata that includes business context, requirements, risks, and design decisions. This schema becomes the source of truth from which observability configuration is derived.

The schema should capture at minimum:
- **Project identity**: ID, name, epic/initiative linkage
- **Business context**: Criticality, owner, cost center
- **Requirements**: Availability, latency, throughput targets
- **Risks**: Known risks with priorities and mitigations
- **Design decisions**: Architectural choices with confidence scores

In Kubernetes environments, a Custom Resource Definition (CRD) works well. In non-Kubernetes environments, a YAML configuration file, database record, or API response serves the same purpose. The key is that the schema is structured, versioned, and accessible to both humans and automated tooling.

### Action 2: Implement Task-as-Span Emission

**Policies Supported**: 1, 2

Build or adopt a task tracker that emits task lifecycle events as OpenTelemetry spans. Each task becomes a span with:

- Span name: task identifier
- Start/end times: task creation and completion
- Status: mapped to span status codes
- Parent span: for hierarchy (epic -> story -> task)
- Events: status transitions, blocks, comments

The tracker should emit via OTLP to any compatible backend (Tempo, Jaeger, Datadog APM, etc.). This enables querying task data with the same tools used for runtime telemetry.

### Action 3: Configure Agent Insight Persistence

**Policies Supported**: 3

Enable AI agents to persist decisions and lessons as spans. An insight emitter should accept:

- **Insight type**: decision, lesson, question, handoff
- **Summary**: Human-readable description
- **Confidence**: 0.0-1.0 score for decisions
- **Applies to**: File paths, modules, or components this insight relates to
- **Context**: Additional metadata for reproducibility

A complementary insight querier should allow agents (and humans) to retrieve prior insights by project, type, time range, or related file. This closes the context loss loop.

### Action 4: Provision Observability Dashboards

**Policies Supported**: 1, 4

Auto-provision dashboards that consume the semantic conventions defined by the task-as-span model. At minimum, two dashboard types:

1. **Portfolio Overview**: Cross-project health matrix, blocked task counts, velocity trends across projects
2. **Project Details**: Per-project sprint burndown, Kanban board, cycle time, blocker analysis

Dashboards should be provisioned idempotently on install and use the standard semantic conventions for all queries, ensuring they work with any backend that receives the OTLP data.

### Action 5: Derive Observability Config from Business Metadata

**Policies Supported**: 4

Implement a controller or automation that watches the project context schema and generates observability configuration:

- **Sampling rules**: Critical projects get 100% sampling
- **Alert rules**: SLO requirements become alert thresholds
- **Dashboard placement**: Business criticality determines visibility
- **Retention policies**: High-value projects get longer retention

This should be automated — when a project's criticality changes, observability configuration updates without manual intervention.

---

## Semantic Conventions

The following attribute namespaces support these patterns. Any implementation should define conventions for at least these domains:

| Namespace | Purpose | Example Attributes |
|-----------|---------|-------------------|
| `project.*` | Project identification | `project.id`, `project.epic` |
| `task.*` | Task tracking | `task.id`, `task.status`, `task.type` |
| `sprint.*` | Sprint tracking | `sprint.id`, `sprint.velocity` |
| `business.*` | Business context | `business.criticality`, `business.owner` |
| `requirement.*` | SLO requirements | `requirement.latency_p99` |
| `risk.*` | Risk tracking | `risk.type`, `risk.priority` |
| `agent.*` | Agent telemetry | `agent.id`, `agent.insight.type` |

Where applicable, align with existing OTel semantic conventions (e.g., `gen_ai.*` for agent telemetry).

---

## Reference Implementations

| Implementation | Environment | Status | Link |
|----------------|-------------|--------|------|
| **ContextCore** | Kubernetes (Kind), Grafana stack | Beta | [Reference Architecture](reference-architecture-contextcore.md) |

---

*This blueprint follows the Rumelt-based template (Diagnosis / Guiding Policies / Coherent Actions) from [OTel SIG End-User Blueprint Template](https://github.com/open-telemetry/sig-end-user/issues/235).*
