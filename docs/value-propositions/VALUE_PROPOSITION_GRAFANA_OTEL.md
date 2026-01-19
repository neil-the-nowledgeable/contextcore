# ContextCore: Value Propositions for Grafana & OpenTelemetry Users

> **Target Audience:** Grafana power users, OpenTelemetry advocates, and platform engineers who have invested in the Grafana observability stack.

---

## Executive Summary

ContextCore extends your existing Grafana + OpenTelemetry investment by treating project management tasks as OTel spans. No new infrastructure required—just more signal in the tools you already love.

**Core Insight:** Tasks share identical structure with distributed trace spans:
- `start_time`, `end_time` (duration)
- Status transitions (span events)
- Parent-child hierarchy (trace context)
- Dependencies (span links)
- Metadata (attributes)

---

## Capability Overview

```yaml
capability:
  id: contextcore
  name: "Project Observability Framework"
  technical_description: |
    Kubernetes CRD-based framework that models project management tasks as
    OpenTelemetry spans, storing them in Tempo, deriving metrics for Mimir/Prometheus,
    and visualizing in Grafana dashboards. Extends the OTel semantic conventions
    to project management domain.
```

---

## Target Personas

### Persona 1: The Grafana Power User

| Attribute | Description |
|-----------|-------------|
| **Title** | Grafana Dashboard Architect |
| **Characteristics** | 50+ dashboards, fluent in PromQL/LogQL/TraceQL, believes "if it's not on a dashboard, it doesn't exist" |
| **Pain Points** | Project status lives in Jira, not Grafana. Can't correlate deployments with work items. Sprint velocity is a spreadsheet. |
| **Desires** | Everything queryable in one place. Time-series for everything. Single pane of glass. |

### Persona 2: The OTel Advocate

| Attribute | Description |
|-----------|-------------|
| **Title** | OpenTelemetry Champion |
| **Characteristics** | Believes in vendor-neutral instrumentation, has implemented OTel across services, values semantic conventions |
| **Pain Points** | Project tools don't speak OTel. No semantic conventions for tasks. Can't link traces to work items. |
| **Desires** | OTel for everything. OTLP export for project data. Correlation between tasks and runtime. |

### Persona 3: The Platform Engineer

| Attribute | Description |
|-----------|-------------|
| **Title** | Internal Developer Platform Builder |
| **Characteristics** | Builds golden paths, manages K8s clusters, owns observability stack |
| **Pain Points** | Business criticality is tribal knowledge. Alert routing doesn't know project context. SLOs disconnected from requirements. |
| **Desires** | CRD-native project context. Auto-generated ServiceMonitors. Value-based observability derivation. |

---

## Value Propositions by Persona

### For Grafana Power Users

**Headline:** "Your Project Backlog, Native in Grafana"

| Before | After |
|--------|-------|
| Project status in Jira, system health in Grafana—two different worlds | Query tasks with TraceQL, visualize sprints alongside deployments |

**Key Benefits:**
- **Tasks as Traces in Tempo** — Every task is a span. Query with TraceQL: `{task.type="story" && task.status="blocked"}`
- **Metrics You Already Understand** — Lead time, cycle time, WIP as Prometheus metrics in Mimir
- **One Dashboard to Rule Them All** — Correlate "PROJ-123 completed" with the deployment that followed
- **Your Existing Stack, Extended** — No new databases. No new UIs. Just more data in tools you love.

**Proof Points:**
- Tasks stored in Tempo you already run
- Metrics exported to Mimir/Prometheus you already query
- Dashboards in Grafana you already use
- Zero new infrastructure required

---

### For OTel Advocates

**Headline:** "OpenTelemetry for Project Management"

| Before | After |
|--------|-------|
| OTel covers runtime. Project context lives in proprietary silos. | Tasks as spans. OTLP export. Semantic conventions for the project domain. |

**Key Benefits:**
- **True Semantic Conventions** — `task.id`, `task.type`, `task.status`, `task.story_points`, `sprint.id` following OTel naming patterns
- **OTLP Native** — Export via standard OTLP/gRPC to any compatible backend
- **Span Links for Correlation** — Link runtime traces to task spans with `get_task_link()`
- **Resource Detector Pattern** — ProjectContextDetector injects project attributes into ALL telemetry

**Proof Points:**
- Follows OTel Resource Detector pattern
- Span events for status transitions (just like span events for exceptions)
- Parent-child spans for epic→story→task hierarchy
- Vendor-neutral: works with any OTLP-compatible backend

---

### For Platform Engineers

**Headline:** "Kubernetes CRDs for Project Context"

| Before | After |
|--------|-------|
| Business criticality is tribal knowledge. Alert routing is guesswork. | ProjectContext CRD → auto-generated ServiceMonitors, PrometheusRules, dashboards |

**Key Benefits:**

- **CRD-Native Project Metadata**
  ```yaml
  apiVersion: contextcore.io/v1
  kind: ProjectContext
  spec:
    business:
      criticality: critical
      value: revenue-primary
    requirements:
      availability: "99.95"
      latencyP99: "200ms"
  ```

- **Value-Based Observability Derivation**
  - `criticality: critical` → 100% trace sampling
  - `latencyP99: 200ms` → PrometheusRule with latency alert
  - `value: revenue-primary` → featured dashboard placement

- **GitOps Compatible** — ProjectContext CRDs in your repo, managed by Flux/ArgoCD
- **Operator-Generated Artifacts** — ServiceMonitor, PrometheusRule, ConfigMap auto-created

**Proof Points:**
- kopf-based Kubernetes operator
- Generates Prometheus Operator CRs
- Integrates with existing Grafana provisioning
- Annotations link Deployments to ProjectContexts

---

## Messaging by Channel

### Taglines (10-15 words)

| Audience | Tagline |
|----------|---------|
| General | "Your project backlog as OpenTelemetry spans" |
| Grafana users | "Finally, project status native in Grafana" |
| OTel advocates | "Semantic conventions for the project management domain" |
| Platform engineers | "CRDs that generate your observability config" |

### One-Liners (25-40 words)

**For Grafana Users:**
> "ContextCore stores your project tasks as spans in Tempo, derives velocity metrics for Mimir, and gives you dashboards that correlate 'task completed' with 'deployment succeeded'—all in the Grafana you already run."

**For OTel Advocates:**
> "Finally, OpenTelemetry for project management. Tasks as spans with proper semantic conventions, OTLP export, Resource Detector pattern, and span links that connect your runtime traces to the work items that caused them."

**For Platform Engineers:**
> "A Kubernetes CRD that knows your project's business criticality, SLO requirements, and design docs—then generates the ServiceMonitors, PrometheusRules, and dashboards to match. GitOps-native project observability."

### Elevator Pitch (60 seconds)

> You've invested in Grafana, Tempo, Mimir, Loki. You can query any metric, trace any request, search any log. But when someone asks "what's the status of Project X?"—you alt-tab to Jira.
>
> ContextCore fixes that. It treats project tasks exactly like distributed trace spans—because they have the same structure. Start time, end time, status events, parent-child hierarchy, dependencies.
>
> Your tasks become spans in Tempo. Your sprint velocity becomes a time-series in Mimir. Your project dashboard sits next to your service dashboards in Grafana.
>
> No new infrastructure. No new query languages. Just more signal in the tools you already love.
>
> And for platform teams: it's a Kubernetes CRD. Define your project's business criticality and latency requirements, and ContextCore generates the ServiceMonitors and alert rules to match.

---

## Social Media Content

### LinkedIn Post

```
🎯 What if your project backlog was queryable with TraceQL?

We've been treating project tasks and distributed traces as separate worlds.
But they have identical structure:
• Start time, end time
• Status transitions
• Parent-child hierarchy
• Dependencies

ContextCore bridges them:
✅ Tasks as spans in Tempo
✅ Velocity metrics in Prometheus/Mimir
✅ Dashboards in Grafana
✅ Zero new infrastructure

Your Grafana investment just got more valuable.

#OpenTelemetry #Grafana #Observability #ProjectManagement
```

### Twitter/X Thread

```
🧵 Hot take: Your project backlog should be in Tempo, not Jira.

Here's why tasks ARE traces:

1/ Tasks have start_time and end_time.
   Spans have start_time and end_time.

2/ Tasks have status changes (todo→in_progress→done).
   Spans have events.

3/ Tasks have hierarchy (epic→story→task).
   Spans have parent-child relationships.

4/ Tasks have dependencies.
   Spans have links.

5/ So why store them differently?

ContextCore: Tasks as OTel spans.
- TraceQL for your backlog
- Sprint velocity in Prometheus
- Project dashboards in Grafana

Your existing stack. More signal. 🎯

github.com/contextcore/contextcore
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GRAFANA (localhost:3000)                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │ Project Portfolio│  │  Project Details │  │  Sprint Metrics  │          │
│  │    Overview      │  │    Dashboard     │  │    Dashboard     │          │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘          │
└───────────┼─────────────────────┼─────────────────────┼─────────────────────┘
            │                     │                     │
            ▼                     ▼                     ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│   TEMPO (3200)    │  │   MIMIR (9009)    │  │   LOKI (3100)     │
│                   │  │                   │  │                   │
│  Task Spans       │  │  Derived Metrics  │  │  Structured Logs  │
│  • task.id        │  │  • lead_time      │  │  • task events    │
│  • task.type      │  │  • cycle_time     │  │  • status changes │
│  • task.status    │  │  • wip_gauge      │  │  • blockers       │
│  • task.blocked   │  │  • velocity       │  │  • completions    │
│  Sprint Spans     │  │  • throughput     │  │                   │
│  • sprint.id      │  │                   │  │                   │
│  • sprint.goal    │  │                   │  │                   │
└─────────┬─────────┘  └─────────┬─────────┘  └─────────┬─────────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                          OTLP (localhost:4317)
                                 │
                    ┌────────────┴────────────┐
                    │      CONTEXTCORE        │
                    │                         │
                    │  TaskTracker            │
                    │  SprintTracker          │
                    │  TaskMetrics            │
                    │  TaskLogger             │
                    │                         │
                    │  "Tasks as Spans"       │
                    └─────────────────────────┘
                                 ▲
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
        ┌─────┴─────┐     ┌─────┴─────┐     ┌─────┴─────┐
        │    CLI    │     │  Python   │     │    K8s    │
        │           │     │    API    │     │  Operator │
        │contextcore│     │TaskTracker│     │ProjectCRD │
        │task start │     │.start()   │     │           │
        └───────────┘     └───────────┘     └───────────┘
```

---

## Before & After Comparison

| Aspect | Before ContextCore | After ContextCore |
|--------|-------------------|-------------------|
| **Task Storage** | Jira/Notion (proprietary) | Tempo (OTel spans) |
| **Query Language** | JQL, Notion formulas | TraceQL |
| **Velocity Metrics** | Spreadsheet, manual | Prometheus time-series |
| **Dashboards** | Separate tool (Jira dashboards) | Grafana (alongside system dashboards) |
| **Correlation** | "Trust me, PROJ-123 caused this deploy" | Span links connect task→runtime |
| **Business Context** | Tribal knowledge | ProjectContext CRD attributes |
| **Alert Routing** | Static routing rules | Derived from business.criticality |
| **SLO Generation** | Manual PrometheusRules | Auto-generated from requirements |

---

## Query Examples

### TraceQL (Tempo)

```
# All blocked stories
{task.type="story" && task.status="blocked"}

# Tasks for a specific project
{task.project="commerce" && task.status="in_progress"}

# Find sprints with high velocity
{name=~"sprint.*" && sprint.velocity > 20}

# Tasks blocked by external dependencies
{task.blocked_by != "" && task.blocked_reason=~".*API.*"}
```

### PromQL (Mimir/Prometheus)

```promql
# 95th percentile lead time over 7 days
histogram_quantile(0.95, sum(rate(task_lead_time_bucket[7d])) by (le, project))

# Current work in progress
task_wip{project="commerce", status="in_progress"}

# Sprint velocity trend
task_sprint_velocity{project="commerce"}

# Throughput (completed tasks per day)
increase(task_completed_total{project="commerce"}[1d])
```

### LogQL (Loki)

```logql
# All task status changes
{job="contextcore"} | json | event_type="task.status_changed"

# Blocked task events
{job="contextcore"} | json | event_type="task.blocked" | line_format "{{.task_id}}: {{.reason}}"

# Completions with story points
{job="contextcore"} | json | event_type="task.completed" | story_points > 0
```

---

## Call to Action

### For Grafana Power Users

**Try it in 5 minutes:**
```bash
pip install contextcore
contextcore task start --id TEST-1 --title "Test task" --type story
contextcore task complete --id TEST-1
```
Then query in Tempo: `{task.id="TEST-1"}`

Your task is now a span. Welcome to project observability.

### For OTel Advocates

**Explore the semantic conventions:**
- `task.id`, `task.type`, `task.status`, `task.story_points`
- `sprint.id`, `sprint.name`, `sprint.goal`
- `project.id`, `project.epic`

Check the [semantic conventions doc](../docs/semantic-conventions.md) and contribute what's missing.

### For Platform Engineers

**Deploy the CRD:**
```bash
kubectl apply -f crds/projectcontext.yaml
contextcore controller  # Run the operator
```
Define a ProjectContext, watch ServiceMonitors appear.

GitOps-native project observability for your platform.

---

## Value Summary

| Value Dimension | What You Get |
|-----------------|--------------|
| **Leverage Existing Investment** | Uses Tempo, Mimir, Loki, Grafana you already run |
| **Native Query Languages** | TraceQL for tasks, PromQL for velocity |
| **OTel Standards** | OTLP export, semantic conventions, Resource Detector |
| **Single Pane of Glass** | Project + system health in one Grafana |
| **Correlation** | Span links connect work items to runtime traces |
| **Automation** | CRD → ServiceMonitor, PrometheusRule, Dashboard |
| **Zero New Infrastructure** | No new databases, no new UIs |

---

## The Bottom Line

> **If you've invested in Grafana and OpenTelemetry, ContextCore makes that investment more valuable by bringing project management data into the same stack.**

Your project backlog deserves the same observability as your production systems.

---

*Generated with capability-value-promoter skill • Target: Grafana & OpenTelemetry users*
