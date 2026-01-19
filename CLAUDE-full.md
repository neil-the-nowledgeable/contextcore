# CLAUDE.md

This file provides guidance to Claude Code for the ContextCore project.

## What is ContextCore?

**ContextCore** is an open source **project management observability framework and toolkit** — a natural extension of OpenTelemetry designed to facilitate the thoughtful integration of business context generated during the initiation, design, development, testing, and deployment of a system with existing operational metadata.

### Mission

Expressed in the language of OpenTelemetry:

> **The goal of ContextCore is to eliminate manual status reporting** to the extent possible through extrapolation of existing artifact metadata of your applications and systems, **regardless of the programming language, infrastructure, and runtime environments used**, and provide context for the generation of observability strategies based on system construction — and, in a similar fashion, eventually generate analytics and optimization strategies.

### What This Means

| OTel Goal | ContextCore Parallel |
|-----------|---------------------|
| Instrument any application | Track any project artifact |
| Language-agnostic | Tool-agnostic (Jira, GitHub, Linear, etc.) |
| Infrastructure-agnostic | Workflow-agnostic (Scrum, Kanban, custom) |
| Runtime-agnostic | Backend-agnostic (any OTLP receiver) |
| Eliminate vendor lock-in | Eliminate PM tool lock-in |
| Enable observability | Enable project observability |

### The Integration Challenge

Traditional approaches keep business context separate from operational data:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE LIFECYCLE INTEGRATION CHALLENGE                       │
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
│                            EXISTING ARTIFACT METADATA                        │
│                    (commits, PRs, CI results, deployments, etc.)            │
│                                       │                                      │
│                                       ▼                                      │
│                         CONTEXTCORE EXTRAPOLATION                           │
│                                       │                                      │
│                                       ▼                                      │
│                      AUTOMATIC STATUS + CONTEXT DERIVATION                  │
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

### Design Principles

1. **Telemetry-Native**: Project tasks are modeled as OpenTelemetry spans. Epics become traces. Status updates become events. The same patterns that work for distributed systems work for project management.

2. **Vendor-Agnostic**: Like OpenTelemetry itself, ContextCore works with any observability backend — Jaeger, Prometheus, Datadog, New Relic, or commercial offerings. **ContextCore is not a backend.**

3. **Tool-Agnostic**: Works with any project management tool (Jira, GitHub Issues, Linear, Notion) and any development workflow (Scrum, Kanban, custom).

4. **Language/Infrastructure/Runtime-Agnostic**: Extracts metadata from any codebase, CI/CD pipeline, or deployment target.

5. **Automatic Context Derivation**: Eliminate manual status reporting by extrapolating project health from existing artifact metadata — commits, PRs, test results, deployments.

6. **Observability Strategy Generation**: Use business context (criticality, requirements, risks) to automatically derive appropriate observability configurations (sampling rates, alert thresholds, dashboard placement).

7. **Lifecycle Continuity**: Connect initiation → design → development → testing → deployment → operation. The same context flows through the entire lifecycle.

8. **Future-Ready**: Data model supports eventual analytics and optimization strategies (ML-driven forecasting, anomaly detection, capacity planning).

### Key Benefits

#### 1. Eliminate the Project Management Data Silo

Traditional PM tools create a data silo **not designed for developers or development workflows**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BEFORE: DISCONNECTED SILOS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────┐                      ┌─────────────────┐              │
│   │  PM TOOL SILO   │                      │   DEV TOOLING   │              │
│   │  (Jira, etc.)   │                      │   (Git, CI/CD)  │              │
│   ├─────────────────┤                      ├─────────────────┤              │
│   │ • Not for devs  │    CONTEXT GAP       │ • No business   │              │
│   │ • Manual entry  │◄──────────────────►  │   context       │              │
│   │ • Stale data    │                      │ • No PM view    │              │
│   │ • Different UI  │                      │ • Different UI  │              │
│   └─────────────────┘                      └─────────────────┘              │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                    AFTER: UNIFIED OBSERVABILITY                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CONTEXTCORE + OBSERVABILITY STACK                 │   │
│   ├─────────────────────────────────────────────────────────────────────┤   │
│   │  • Developer-native (same tools they use for production)            │   │
│   │  • Auto-populated from existing artifacts                           │   │
│   │  • Real-time, always current                                        │   │
│   │  • Single pane of glass for dev + ops + PM                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 2. Eliminate Developer Toil

**Stop asking developers to write status reports.** ContextCore eliminates:

| Traditional Toil | ContextCore Approach |
|------------------|---------------------|
| Weekly status emails | Auto-generated from commit/PR activity |
| Manual ticket updates | Status derived from git activity |
| Sprint retrospective data gathering | Metrics computed from span data |
| "What's the status of X?" interruptions | Self-service dashboards |
| Duplicate data entry (git + Jira) | Single source of truth |

#### 3. Eliminate Dependence on Developer Status Reports

Project visibility should not depend on developers remembering to update tickets:

| Problem | ContextCore Solution |
|---------|---------------------|
| Tickets marked "in progress" for weeks | Activity-based staleness detection |
| No updates until completion | Continuous status from commits |
| Inconsistent update quality | Standardized, automated signals |
| "I forgot to update the ticket" | No manual updates required |
| Status varies by developer diligence | Uniform extrapolation for all |

#### 4. Business-Aware Observability Strategy Generation

Incorporate business metadata with operational metadata to **auto-generate observability strategies** that reflect:

| Business Context | Generated Strategy |
|------------------|-------------------|
| **Business Value** | Trace sampling, metrics granularity, dashboard placement |
| **Key Stakeholders** | Alert routing, escalation paths, notification channels |
| **Component Criticality** | SLO definitions, error budget tracking |
| **Sub-component Ownership** | Incident response routing, on-call assignment |
| **Risk Signals** | Anomaly detection sensitivity, audit logging |

This enables **thoughtful incident response** by ensuring alerts reach the right stakeholders with full business context — not just "service X is down" but "revenue-critical checkout service owned by commerce-team is down, design doc here, ADR here."

#### 5. Single Language for Project Operations and Project Management

**One system, one query language, integrated metadata:**

| Capability | Traditional (Multiple Systems) | ContextCore (Unified) |
|------------|-------------------------------|----------------------|
| **Status Reporting** | Export from Jira → slides | Query from Grafana |
| **Leadership Portals** | Custom BI dashboards | Native Grafana dashboards |
| **Developer View** | IDE + Jira + Slack | IDE + Grafana |
| **Incident Context** | Search Jira during outage | Context in alert annotations |
| **Sprint Metrics** | Manual calculation | TraceQL/PromQL queries |
| **Cross-team Visibility** | Request access to other Jira | Shared observability platform |
| **Historical Analysis** | Limited Jira exports | Full trace/metric retention |

Benefits of unified language:
- **Reporting**: Same queries for status reports, sprint reviews, executive dashboards
- **Leadership Portals**: Real-time project health without manual data aggregation
- **Developer Experience**: Stay in familiar observability tools
- **Incident Response**: Full project context available during incidents
- **Audit Trail**: Complete history in queryable format

### Differentiation: Why Observability Infrastructure, Not Another Tool

#### ContextCore vs. Backstage and Developer Portals

Tools like **Backstage** thoughtfully and programmatically align development processes and systems — but they require adopting a **new system**. ContextCore takes a fundamentally different approach:

| Approach | Backstage / Developer Portals | ContextCore |
|----------|------------------------------|-------------|
| **Philosophy** | New unified portal | Unify view in existing infrastructure |
| **Data Strategy** | Aggregate into new system | Leverage existing data where it lives |
| **Infrastructure** | New application to deploy/maintain | Uses existing observability stack |
| **Database** | Requires new persistence layer | Time-series DBs you already run |
| **Authentication** | Another login/session/context | Same Grafana access you have |
| **Adoption** | Migrate teams to new portal | Zero new tools for developers |

#### The Natural Evolution Argument

Given the infrastructure required to keep systems up and running — especially for large systems and applications — **it is more feasible to leverage existing operational observability infrastructure** for project management than to shoe-horn an operational perspective into project management tools.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TWO APPROACHES TO UNIFICATION                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   APPROACH A: Add Operations to PM Tools                                    │
│   ──────────────────────────────────────                                    │
│                                                                              │
│   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐                │
│   │   Jira      │ ───► │  + Plugins  │ ───► │  + More     │                │
│   │             │      │  + APIs     │      │    Plugins  │                │
│   └─────────────┘      └─────────────┘      └─────────────┘                │
│                                                                              │
│   Problems:                                                                  │
│   • PM tools not designed for time-series operational data                  │
│   • Metrics/traces don't fit PM data models                                 │
│   • Developers still avoid the PM tool                                      │
│   • Another system to query during incidents                                │
│                                                                              │
│   ─────────────────────────────────────────────────────────────────────────│
│                                                                              │
│   APPROACH B: Add PM to Observability (ContextCore)                         │
│   ─────────────────────────────────────────────────                         │
│                                                                              │
│   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐                │
│   │  Grafana    │ ───► │  + Project  │ ───► │  Unified    │                │
│   │  Tempo      │      │    Context  │      │  Platform   │                │
│   │  Mimir      │      │  + Task     │      │             │                │
│   │  (exists)   │      │    Spans    │      │  (no new    │                │
│   └─────────────┘      └─────────────┘      │   infra)    │                │
│                                              └─────────────┘                │
│   Benefits:                                                                  │
│   • Observability tools designed for time-series data                       │
│   • Tasks as spans fit naturally                                            │
│   • Developers already live here                                            │
│   • Single pane during incidents                                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Why Grafana Is the Right Audience

Grafana is perfectly capable of serving **all stakeholders** — developers, designers, testers, project managers, business stakeholders, operators, and leadership:

| Stakeholder | Grafana Capability |
|-------------|-------------------|
| **Developers** | Already use for debugging, monitoring |
| **Operators** | Primary incident response tool |
| **Project Managers** | Custom dashboards for sprint/epic views |
| **Leadership** | Executive summary dashboards |
| **Business Stakeholders** | Business metrics alongside project health |
| **Auditors** | Query-based compliance reports |

**Built-in capabilities that eliminate the need for another system:**
- **Time-series persistence**: Tempo, Mimir, Loki — no additional database
- **Flexible dashboards**: Customizable for any audience
- **Alerting**: Unified for operational AND project signals
- **Access control**: Role-based dashboard visibility
- **API**: Programmatic access for integrations

#### The Natural Evolution of OTel and Systems Observability

ContextCore is the **natural evolution** of OpenTelemetry and systems observability:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVOLUTION OF OBSERVABILITY                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   2010s: LOGGING                                                            │
│   ──────────────                                                            │
│   "Let's centralize logs so we can search them"                             │
│   → ELK Stack, Splunk                                                       │
│                                                                              │
│   2015s: METRICS                                                            │
│   ─────────────                                                             │
│   "Let's add time-series metrics for dashboards and alerts"                 │
│   → Prometheus, Graphite, InfluxDB                                          │
│                                                                              │
│   2018s: DISTRIBUTED TRACING                                                │
│   ─────────────────────────                                                 │
│   "Let's trace requests across services"                                    │
│   → Jaeger, Zipkin, OpenTracing                                             │
│                                                                              │
│   2019: OPENTELEMETRY                                                       │
│   ───────────────────                                                       │
│   "Let's unify traces, metrics, logs with standard semantics"               │
│   → OTel SDK, OTLP, Semantic Conventions                                    │
│                                                                              │
│   2024+: CONTEXTCORE                                                        │
│   ───────────────────                                                       │
│   "Let's extend OTel patterns to project management"                        │
│   → Tasks as spans, business context as attributes                          │
│   → Same infrastructure, same query language, same dashboards               │
│   → Natural evolution, not a new system                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**The insight**: Each evolution of observability extended what we could see and query. ContextCore extends observability to include **project context** — the "why" behind the systems we build and operate.

### What ContextCore Is NOT

ContextCore is **not** an observability backend. It is:
- A **data model** (semantic conventions for project telemetry)
- A **collection layer** (SDK and adapters for project management tools)
- An **export protocol** (OTLP for project signals)

ContextCore ships with a **reference implementation** using the Grafana stack (Tempo, Mimir, Loki) as a working example ready for local use — but this is just one possible backend configuration.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CONTEXTCORE ARCHITECTURE                             │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     PROJECT MANAGEMENT TOOLS                         │   │
│  │   Jira • GitHub Issues • Linear • Notion • Manual CLI               │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     CONTEXTCORE SDK                                  │   │
│  │                                                                      │   │
│  │  • Semantic Conventions (project.*, task.*, sprint.*)               │   │
│  │  • TaskTracker (tasks as spans)                                     │   │
│  │  • TaskLogger (structured logs)                                     │   │
│  │  • TaskMetrics (derived metrics)                                    │   │
│  │  • State persistence                                                │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│                                 │ OTLP (OpenTelemetry Protocol)            │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     ANY OTLP-COMPATIBLE BACKEND                      │   │
│  │                                                                      │   │
│  │   Open Source:           Commercial:          Reference Impl:       │   │
│  │   • Jaeger               • Datadog            • Grafana Tempo       │   │
│  │   • Prometheus           • New Relic          • Grafana Mimir       │   │
│  │   • Zipkin               • Honeycomb          • Grafana Loki        │   │
│  │   • ClickHouse           • Dynatrace          • Grafana dashboards  │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Core Problem

Design-time knowledge is isolated from runtime operations:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         THE CONTEXT GAP                                      │
│                                                                              │
│   Project Management          │         Kubernetes/Operations               │
│   ─────────────────           │         ─────────────────────               │
│   • Business value            │         • Deployment specs                  │
│   • Design documents          │         • Service configs                   │
│   • Requirements              │         • Resource limits                   │
│   • Risk assessments          │         • Observability setup               │
│   • Task tracking             │         • Alerting rules                    │
│                               │                                              │
│           ↓                   │                  ↓                          │
│    Lives in Jira/Notion       │           Lives in YAML/Helm               │
│    Disconnected               │           No business context              │
│                               │                                              │
│   "What's the business        │         "Why is this service               │
│    value of this service?"    │          important?"                        │
│           🤷                   │                 🤷                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

## The Solution: ContextCore CRD

A Kubernetes-native approach that carries project context alongside workloads:

```yaml
apiVersion: contextcore.io/v1
kind: ProjectContext
metadata:
  name: checkout-service
  namespace: commerce
spec:
  # Link to project artifacts
  project:
    id: "commerce-platform"
    epic: "EPIC-42"
    tasks: ["TASK-789", "TASK-790"]

  # Design documentation
  design:
    doc: "https://docs.internal/checkout-redesign"
    adr: "ADR-015-event-driven-checkout"
    apiContract: "https://api.internal/checkout/v2/openapi.yaml"

  # Business context
  business:
    criticality: critical      # critical|high|medium|low
    value: revenue-primary     # revenue-primary|cost-reduction|compliance|enabler
    owner: commerce-team
    costCenter: "CC-4521"

  # Requirements (for SLO derivation)
  requirements:
    availability: "99.95"
    latencyP99: "200ms"
    errorBudget: "0.05"

  # Risk signals (for alert derivation)
  risks:
    - type: security
      description: "Handles PII and payment data"
      priority: P1
    - type: availability
      description: "Revenue impact if down"
      mitigation: "ADR-015"

  # Target K8s resources
  targets:
    - kind: Deployment
      name: checkout-service
    - kind: Service
      name: checkout-api

  # Observability strategy (or derived from above)
  observability:
    traceSampling: 1.0
    metricsInterval: "10s"
    dashboardPlacement: featured
    alertChannels: ["commerce-oncall", "pagerduty-p1"]
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PROJECT LAYER                                   │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐               │
│   │   Jira    │  │  Notion   │  │  GitHub   │  │   ADRs    │               │
│   │  Issues   │  │   Docs    │  │  Issues   │  │           │               │
│   └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘               │
│         └──────────────┴───────┬──────┴──────────────┘                      │
│                                │ contextcore sync                           │
└────────────────────────────────┼────────────────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           KUBERNETES LAYER                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      ProjectContext CRD                               │  │
│  │   Single source of truth for project + operational context            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│         │                                                                    │
│         │ contextcore-controller                                            │
│         ▼                                                                    │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │  Resource  │  │  Service   │  │ Prometheus │  │  Grafana   │           │
│  │Annotations │  │  Monitor   │  │   Rule     │  │ Dashboard  │           │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘           │
│                                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                            │
│  │ Deployment │  │  Service   │  │ ConfigMap  │  (annotated with context)  │
│  └────────────┘  └────────────┘  └────────────┘                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ OTel Resource Detector
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OBSERVABILITY LAYER                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │   Traces   │  │  Metrics   │  │   Logs     │  │   Alerts   │           │
│  │+project.*  │  │+project.*  │  │+project.*  │  │ w/context  │           │
│  │+business.* │  │+business.* │  │+business.* │  │            │           │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘           │
│                                                                              │
│  Every signal carries: business.criticality, project.design_doc,            │
│  project.owner, requirement.*, risk.* - queryable, groupable, actionable   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Value Proposition

### 1. Value-Based Observability Derivation

The controller generates observability artifacts from project metadata:

| Project Signal | Generated Artifact |
|----------------|-------------------|
| `business.criticality: critical` | 100% trace sampling, 10s metrics, P1 alerts |
| `business.value: revenue-primary` | SLO definition, error budget tracking |
| `requirements.latencyP99: 200ms` | PrometheusRule with latency alert |
| `risks[].type: security` | Extended audit logging, anomaly detection |
| `design.adr` | Runbook link in alert annotations |

### 2. Context-Rich Telemetry

All runtime telemetry automatically includes project context:

```json
{
  "trace_id": "abc123",
  "span_name": "checkout.processPayment",
  "attributes": {
    "k8s.deployment.name": "checkout-service",
    "project.id": "commerce-platform",
    "project.task": "TASK-789",
    "business.criticality": "critical",
    "business.value": "revenue-primary",
    "design.doc": "https://docs.internal/checkout",
    "design.adr": "ADR-015"
  }
}
```

### 3. Incident Context at Your Fingertips

When alerts fire, responders get immediate context:

```yaml
# Alert annotation (auto-generated from ProjectContext)
annotations:
  summary: "High latency on checkout-service"
  design_doc: "https://docs.internal/checkout-redesign"
  adr: "ADR-015-event-driven-checkout"
  business_criticality: "critical"
  business_value: "revenue-primary"
  owner: "commerce-team"
  runbook: "https://runbooks.internal/checkout-latency"
```

### 4. Unified Lifecycle Tracking

Project tasks become spans linked to runtime telemetry:

```
Epic: "Checkout Redesign" (span)
  └── Story: "Implement async flow" (span)
        └── Task: "Add event queue" (span)
              └── Deployment: checkout-service (K8s + OTel)
                    └── Runtime spans: processPayment, validateCart
```

## Tasks as Spans: Project Tracking via OpenTelemetry

A core insight of ContextCore is that **tasks ARE spans**. Project tasks share the same structure as distributed trace spans:

| Task Property | Span Equivalent |
|---------------|-----------------|
| Created date | `start_time` |
| Completed date | `end_time` |
| Status (todo, in_progress, done) | Span status + events |
| Task ID, title, assignee | Span attributes |
| Epic → Story → Task hierarchy | Parent-child spans |
| Dependencies | Span links |
| Status changes, comments | Span events |

### Why Store Tasks as Spans?

1. **Unified Telemetry**: Tasks and runtime traces in the same system (Tempo)
2. **Natural Hierarchy**: Epics contain stories contain tasks (parent-child)
3. **Time-Series Native**: Lead time, cycle time computed from span duration
4. **Correlation**: Link task spans to implementation spans
5. **Query Power**: TraceQL queries across project and runtime data

### Task Lifecycle as Span Events

```
task:PROJ-123 (span)
├── start_time: 2024-01-15T09:00:00Z
├── attributes:
│   ├── task.id: "PROJ-123"
│   ├── task.type: "story"
│   ├── task.title: "Implement user auth"
│   ├── task.status: "done"
│   ├── task.priority: "high"
│   ├── task.assignee: "alice"
│   └── task.story_points: 5
├── events:
│   ├── task.created (09:00)
│   ├── task.status_changed: todo → in_progress (10:00)
│   ├── task.blocked: "Waiting on API design" (Day 2)
│   ├── task.unblocked (Day 3)
│   ├── task.commented: "Updated API contract" (Day 3)
│   └── task.completed (Day 4)
├── links:
│   └── depends_on: task:PROJ-100 (API design task)
└── end_time: 2024-01-18T17:00:00Z
```

### Derived Metrics

From task spans, ContextCore derives standard project management metrics:

| Metric | Calculation |
|--------|-------------|
| `task.lead_time` | `end_time - start_time` (histogram) |
| `task.cycle_time` | `end_time - first_in_progress_event` (histogram) |
| `task.blocked_time` | Sum of blocked periods (histogram) |
| `task.wip` | Count of in_progress tasks (gauge) |
| `task.throughput` | Completed tasks per period (counter) |
| `sprint.velocity` | Story points per sprint (gauge) |

### Programmatic Usage

```python
from contextcore import TaskTracker, SprintTracker

# Initialize tracker
tracker = TaskTracker(project="my-project")

# Track a sprint
sprint_tracker = SprintTracker(tracker)
sprint_tracker.start_sprint("sprint-3", name="Sprint 3", goal="Complete auth")

# Track tasks within sprint
tracker.start_task(
    task_id="PROJ-123",
    title="Implement OAuth flow",
    task_type="story",
    parent_id="EPIC-42",
    sprint_id="sprint-3",
    story_points=5,
)

# Update task status (adds span event)
tracker.update_status("PROJ-123", "in_progress")

# Block task (sets ERROR status on span)
tracker.block_task("PROJ-123", reason="Waiting on security review")

# Complete task (ends span)
tracker.complete_task("PROJ-123")

# End sprint
sprint_tracker.end_sprint("sprint-3", completed_points=21)
```

### Linking Runtime Traces to Tasks

Application code can link runtime spans to task spans:

```python
from contextcore import get_task_link
from opentelemetry import trace

# Get link to task span
task_link = get_task_link("PROJ-123", project="my-project")

# Create implementation span linked to task
tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("implement_oauth", links=[task_link]):
    # Implementation work...
    pass
```

This enables queries like: "Show me all runtime traces for task PROJ-123"

## Tech Stack

- **Language**: Python 3.9+
- **CRD Framework**: kopf (Kubernetes Operator Framework)
- **Telemetry**: OpenTelemetry SDK
- **Protocol**: OTLP to Grafana Alloy
- **Storage**: Tempo (traces), Mimir (metrics), Loki (logs)
- **Visualization**: Grafana

## Project Structure

```
ContextCore/
├── CLAUDE.md                    # This file
├── README.md                    # Public documentation
├── pyproject.toml               # Python package config
├── src/
│   └── contextcore/
│       ├── __init__.py
│       ├── models.py            # Pydantic models for CRD spec
│       ├── controller.py        # kopf-based K8s controller
│       ├── detector.py          # OTel Resource Detector
│       ├── tracker.py           # Task Tracker (tasks as spans)
│       ├── state.py             # Span state persistence
│       ├── metrics.py           # Derived project metrics
│       ├── generators/
│       │   ├── servicemonitor.py
│       │   ├── prometheusrule.py
│       │   ├── dashboard.py
│       │   └── annotations.py
│       ├── sync/
│       │   ├── jira.py          # Jira → ProjectContext sync
│       │   ├── github.py        # GitHub Issues → ProjectContext
│       │   └── notion.py        # Notion → ProjectContext
│       └── cli.py               # CLI interface
├── crds/
│   └── projectcontext.yaml      # CRD definition
├── helm/
│   └── contextcore/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── crd.yaml
│           ├── deployment.yaml
│           ├── rbac.yaml
│           └── configmap.yaml
├── dashboards/
│   └── contextcore-overview.json
├── docs/
│   ├── semantic-conventions.md
│   └── value-propositions.yaml
└── tests/
```

## Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Apply CRD to cluster
kubectl apply -f crds/projectcontext.yaml

# Run controller locally (development)
python -m contextcore controller --kubeconfig ~/.kube/config

# Create ProjectContext from CLI
contextcore create \
  --name checkout-context \
  --namespace commerce \
  --project commerce-platform \
  --criticality critical \
  --design-doc "https://docs.internal/checkout"

# Sync from Jira
contextcore sync jira \
  --project COMMERCE \
  --namespace commerce

# Generate observability artifacts
contextcore generate \
  --context commerce/checkout-context \
  --output ./generated/

# Annotate existing deployment
contextcore annotate deployment/checkout-service \
  --context checkout-context

# Task tracking (tasks as spans)
contextcore task start --id PROJ-123 --title "Implement auth" --type story
contextcore task update --id PROJ-123 --status in_progress
contextcore task block --id PROJ-123 --reason "Waiting on API"
contextcore task unblock --id PROJ-123
contextcore task complete --id PROJ-123
contextcore task list --project my-project

# Sprint tracking
contextcore sprint start --id sprint-3 --name "Sprint 3" --goal "Complete auth"
contextcore sprint end --id sprint-3 --points 21

# View metrics
contextcore metrics summary --project my-project --days 14
contextcore metrics wip --project my-project
contextcore metrics blocked --project my-project
contextcore metrics export --project my-project --endpoint localhost:4317
```

## Semantic Conventions

### Resource Attributes (on all telemetry)

```
# Project identity
project.id                    # Project identifier
project.epic                  # Epic ID
project.task                  # Current task ID

# Design artifacts
design.doc                    # URL to design document
design.adr                    # ADR identifier or URL
design.api_contract           # OpenAPI/AsyncAPI URL

# Business context
business.criticality          # critical|high|medium|low
business.value                # revenue-primary|cost-reduction|compliance|enabler
business.owner                # Owning team
business.cost_center          # Cost center code

# Requirements
requirement.availability      # Target availability %
requirement.latency_p99       # Target P99 latency
requirement.error_budget      # Error budget %

# Risk signals
risk.type                     # security|compliance|data-integrity|availability
risk.priority                 # P1|P2|P3|P4
risk.mitigation               # Mitigation ADR reference

# K8s context
k8s.projectcontext.name       # ProjectContext resource name
k8s.projectcontext.namespace  # ProjectContext namespace
```

## Development Phases

### Phase 1: CRD + Controller Foundation
- [ ] ProjectContext CRD schema
- [ ] kopf-based controller skeleton
- [ ] Resource annotation from ProjectContext
- [ ] OTel Resource Detector for context injection
- [ ] CLI for ProjectContext management

### Phase 2: Observability Derivation
- [ ] ServiceMonitor generation from criticality
- [ ] PrometheusRule generation from requirements
- [ ] Dashboard JSON generation
- [ ] Trace sampling configuration

### Phase 3: Project Tool Sync
- [ ] Jira sync adapter
- [ ] GitHub Issues sync adapter
- [ ] Notion sync adapter
- [ ] Bidirectional sync (runtime incidents → project tasks)

### Phase 4: Helm + Production
- [ ] Helm chart for controller deployment
- [ ] RBAC configuration
- [ ] High availability setup
- [ ] Documentation and examples

## Environment Variables

```bash
# Controller configuration
CONTEXTCORE_NAMESPACE=contextcore-system
CONTEXTCORE_LOG_LEVEL=info
KUBECONFIG=~/.kube/config

# OTel export
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=contextcore-controller

# Sync adapters
JIRA_URL=https://company.atlassian.net
JIRA_TOKEN=<token>
GITHUB_TOKEN=<token>
NOTION_TOKEN=<token>
```

## Key Design Decisions

### Why Kubernetes CRD?
- **Declarative**: Define desired state, controller reconciles
- **Native**: Works with existing K8s tooling (kubectl, GitOps)
- **Lifecycle**: Tied to cluster resources, not external systems
- **RBAC**: K8s-native access control
- **Audit**: K8s audit log captures all changes

### Why Not Just Annotations?
Annotations work for simple cases, but:
- No schema validation
- No controller reconciliation
- Scattered across resources
- Hard to query/aggregate
- No lifecycle management

ProjectContext CRD provides:
- Validated schema
- Single source of truth
- Controller-driven derivation
- Queryable via K8s API
- Proper lifecycle (create, update, delete)

### Why OTel Resource Detector?
Injecting context at the OTel level means:
- All signals (traces, metrics, logs) get context
- Works with any OTel-instrumented app
- No application code changes needed
- Context available in every query

## Integration Points

### With Existing Observability
ContextCore enhances, doesn't replace:
- **Grafana**: Dashboards grouped by business.value
- **Prometheus**: Alerts include project context
- **Tempo**: Traces filterable by project.id
- **Loki**: Logs queryable by business.criticality

### With GitOps
ProjectContext is just YAML:
- Store in Git alongside Helm charts
- Apply via ArgoCD/Flux
- Review context changes in PRs
- Version history of project metadata

### With Incident Management
When PagerDuty fires:
- Alert includes design_doc, adr, owner
- Responder has immediate context
- Post-incident can trace to originating task

## Must Do
- Use ProjectContext CRD as the source of truth
- Derive observability from project metadata
- Include context in all generated artifacts
- Validate schema strictly

## Must Avoid
- Duplicating context in multiple places
- Manual annotation of resources (use controller)
- Storing sensitive data in ProjectContext
- Over-generating artifacts (derive only what's needed)
