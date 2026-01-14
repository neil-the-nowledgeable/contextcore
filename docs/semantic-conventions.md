# ContextCore Semantic Conventions

This document defines the semantic conventions for ContextCore attributes, following OpenTelemetry naming patterns.

## Overview

ContextCore extends OpenTelemetry semantic conventions with project management context. These attributes appear on:
- **Resource attributes**: Attached to all telemetry from a service
- **Span attributes**: On specific spans when relevant
- **Log attributes**: In structured log records
- **Metric labels**: On Prometheus metrics (where cardinality allows)

## Naming Conventions

| Pattern | Example | Description |
|---------|---------|-------------|
| `project.*` | `project.id` | Project identification |
| `design.*` | `design.doc` | Design artifacts |
| `business.*` | `business.criticality` | Business context |
| `requirement.*` | `requirement.availability` | SLO requirements |
| `risk.*` | `risk.type` | Risk signals |
| `task.*` | `task.id` | Task tracking (tasks as spans) |
| `sprint.*` | `sprint.id` | Sprint tracking |
| `k8s.projectcontext.*` | `k8s.projectcontext.name` | K8s CRD context |

---

## Project Attributes

### `project.id`
- **Type**: `string`
- **Description**: Unique identifier for the project
- **Example**: `"commerce-platform"`, `"auth-service"`

### `project.epic`
- **Type**: `string`
- **Description**: Epic identifier this work relates to
- **Example**: `"EPIC-42"`, `"checkout-redesign"`

### `project.task`
- **Type**: `string`
- **Description**: Specific task identifier
- **Example**: `"TASK-789"`, `"JIRA-1234"`

### `project.trace_id`
- **Type**: `string`
- **Description**: OTel trace ID linking to project span (for task-as-span pattern)
- **Example**: `"abc123def456..."`

---

## Design Attributes

### `design.doc`
- **Type**: `string` (URL)
- **Description**: URL to the design document
- **Example**: `"https://docs.internal/checkout-redesign"`

### `design.adr`
- **Type**: `string`
- **Description**: Architecture Decision Record identifier or URL
- **Example**: `"ADR-015-event-driven-checkout"`, `"https://adrs.internal/015"`

### `design.api_contract`
- **Type**: `string` (URL)
- **Description**: OpenAPI or AsyncAPI specification URL
- **Example**: `"https://api.internal/checkout/v2/openapi.yaml"`

---

## Business Attributes

### `business.criticality`
- **Type**: `string`
- **Description**: Business criticality level
- **Allowed Values**: `critical`, `high`, `medium`, `low`
- **Usage**: Drives trace sampling, metrics interval, alert priority

### `business.value`
- **Type**: `string`
- **Description**: Business value classification
- **Allowed Values**:
  - `revenue-primary` - Direct revenue generation
  - `revenue-secondary` - Supports revenue generation
  - `cost-reduction` - Reduces operational costs
  - `compliance` - Required for compliance
  - `enabler` - Enables other capabilities
  - `internal` - Internal tooling

### `business.owner`
- **Type**: `string`
- **Description**: Owning team or individual
- **Example**: `"commerce-team"`, `"platform-sre"`

### `business.cost_center`
- **Type**: `string`
- **Description**: Cost center code for chargebacks
- **Example**: `"CC-4521"`

---

## Requirement Attributes

### `requirement.availability`
- **Type**: `string`
- **Description**: Target availability percentage
- **Example**: `"99.95"`, `"99.9"`

### `requirement.latency_p50`
- **Type**: `string`
- **Description**: Target P50 latency
- **Example**: `"50ms"`, `"100ms"`

### `requirement.latency_p99`
- **Type**: `string`
- **Description**: Target P99 latency
- **Example**: `"200ms"`, `"500ms"`

### `requirement.error_budget`
- **Type**: `string`
- **Description**: Error budget percentage
- **Example**: `"0.05"` (0.05% errors allowed)

### `requirement.throughput`
- **Type**: `string`
- **Description**: Target throughput
- **Example**: `"1000rps"`, `"10000rpm"`

### `requirement.source`
- **Type**: `string`
- **Description**: Where these requirements originated
- **Example**: `"product-requirements-doc"`, `"SLA-agreement"`

---

## Risk Attributes

### `risk.type`
- **Type**: `string`
- **Description**: Risk category
- **Allowed Values**:
  - `security` - Security vulnerabilities
  - `compliance` - Compliance violations
  - `data-integrity` - Data corruption/loss
  - `availability` - Service unavailability
  - `financial` - Financial impact
  - `reputational` - Brand damage

### `risk.priority`
- **Type**: `string`
- **Description**: Alert priority if risk materializes
- **Allowed Values**: `P1`, `P2`, `P3`, `P4`

### `risk.mitigation`
- **Type**: `string`
- **Description**: Mitigation strategy reference (usually ADR)
- **Example**: `"ADR-015"`, `"https://runbooks.internal/circuit-breaker"`

---

## Task Attributes (Tasks as Spans)

Tasks are modeled as OpenTelemetry spans. These attributes appear on task spans.

### `task.id`
- **Type**: `string`
- **Description**: Unique task identifier
- **Example**: `"PROJ-123"`, `"JIRA-456"`

### `task.type`
- **Type**: `string`
- **Description**: Task hierarchy type
- **Allowed Values**: `epic`, `story`, `task`, `subtask`, `bug`, `spike`, `incident`

### `task.title`
- **Type**: `string`
- **Description**: Task title/summary
- **Example**: `"Implement user authentication"`

### `task.status`
- **Type**: `string`
- **Description**: Current task status
- **Allowed Values**: `backlog`, `todo`, `in_progress`, `in_review`, `blocked`, `done`, `cancelled`

### `task.priority`
- **Type**: `string`
- **Description**: Task priority level
- **Allowed Values**: `critical`, `high`, `medium`, `low`

### `task.assignee`
- **Type**: `string`
- **Description**: Person assigned to the task
- **Example**: `"alice"`, `"bob@company.com"`

### `task.story_points`
- **Type**: `int`
- **Description**: Story point estimate
- **Example**: `5`, `8`, `13`

### `task.labels`
- **Type**: `string[]`
- **Description**: Task labels/tags
- **Example**: `["frontend", "auth", "security"]`

### `task.url`
- **Type**: `string` (URL)
- **Description**: Link to external system (Jira, GitHub, etc.)
- **Example**: `"https://jira.company.com/browse/PROJ-123"`

### `task.due_date`
- **Type**: `string` (ISO 8601)
- **Description**: Task due date
- **Example**: `"2024-02-15"`

### `task.blocked_by`
- **Type**: `string`
- **Description**: Task ID that is blocking this task
- **Example**: `"PROJ-100"`

---

## Sprint Attributes

Sprints are parent spans that contain task spans.

### `sprint.id`
- **Type**: `string`
- **Description**: Sprint identifier
- **Example**: `"sprint-3"`, `"2024-Q1-S2"`

### `sprint.name`
- **Type**: `string`
- **Description**: Sprint name
- **Example**: `"Sprint 3"`, `"January Week 2"`

### `sprint.goal`
- **Type**: `string`
- **Description**: Sprint goal
- **Example**: `"Complete user authentication flow"`

### `sprint.start_date`
- **Type**: `string` (ISO 8601)
- **Description**: Sprint start date
- **Example**: `"2024-01-15"`

### `sprint.end_date`
- **Type**: `string` (ISO 8601)
- **Description**: Sprint end date
- **Example**: `"2024-01-29"`

### `sprint.planned_points`
- **Type**: `int`
- **Description**: Planned story points for sprint
- **Example**: `34`

### `sprint.completed_points`
- **Type**: `int`
- **Description**: Actual story points completed
- **Example**: `28`

---

## Kubernetes Attributes

### `k8s.projectcontext.name`
- **Type**: `string`
- **Description**: ProjectContext CRD resource name
- **Example**: `"checkout-context"`

### `k8s.projectcontext.namespace`
- **Type**: `string`
- **Description**: Namespace of the ProjectContext
- **Example**: `"commerce"`

Standard K8s attributes are also included:
- `k8s.namespace.name`
- `k8s.deployment.name`
- `k8s.pod.name`

---

## K8s Annotations

ContextCore uses annotations with the `contextcore.io/` prefix:

| Annotation | Maps To |
|------------|---------|
| `contextcore.io/project` | `project.id` |
| `contextcore.io/epic` | `project.epic` |
| `contextcore.io/task` | `project.task` |
| `contextcore.io/design-doc` | `design.doc` |
| `contextcore.io/adr` | `design.adr` |
| `contextcore.io/criticality` | `business.criticality` |
| `contextcore.io/business-value` | `business.value` |
| `contextcore.io/owner` | `business.owner` |
| `contextcore.io/slo-availability` | `requirement.availability` |
| `contextcore.io/slo-latency-p99` | `requirement.latency_p99` |

---

## Value-Based Derivation Rules

| Input | Output |
|-------|--------|
| `business.criticality: critical` | `traceSampling: 1.0`, `metricsInterval: 10s` |
| `business.criticality: high` | `traceSampling: 0.5`, `metricsInterval: 30s` |
| `business.criticality: medium` | `traceSampling: 0.1`, `metricsInterval: 60s` |
| `business.criticality: low` | `traceSampling: 0.01`, `metricsInterval: 120s` |
| `business.value: revenue-primary` | `dashboardPlacement: featured` |
| `risk.type: security` + `risk.priority: P1` | Extended audit logging, anomaly detection |
| `requirement.latency_p99: 200ms` | PrometheusRule with latency alert |

---

## Example: Full Resource Attributes

```json
{
  "project.id": "commerce-platform",
  "project.epic": "EPIC-42",
  "project.task": "TASK-789",

  "design.doc": "https://docs.internal/checkout-redesign",
  "design.adr": "ADR-015-event-driven-checkout",

  "business.criticality": "critical",
  "business.value": "revenue-primary",
  "business.owner": "commerce-team",

  "requirement.availability": "99.95",
  "requirement.latency_p99": "200ms",

  "risk.type": "security",
  "risk.priority": "P1",

  "k8s.namespace.name": "commerce",
  "k8s.deployment.name": "checkout-service",
  "k8s.projectcontext.name": "checkout-context"
}
```

---

## Task Span Events

Task spans use events to track lifecycle changes:

| Event Name | Description | Attributes |
|------------|-------------|------------|
| `task.created` | Task was created | `task.title`, `task.type` |
| `task.status_changed` | Status transition | `from`, `to` |
| `task.blocked` | Task became blocked | `reason`, `blocker_id` |
| `task.unblocked` | Block removed | - |
| `task.assigned` | Assignee changed | `from`, `to` |
| `task.commented` | Comment added | `author`, `text` |
| `task.completed` | Task finished | - |
| `task.cancelled` | Task cancelled | `reason` |

---

## Derived Metrics

ContextCore derives these metrics from task spans:

| Metric | Type | Description |
|--------|------|-------------|
| `task.lead_time` | Histogram | Time from creation to completion (seconds) |
| `task.cycle_time` | Histogram | Time from in_progress to completion (seconds) |
| `task.blocked_time` | Histogram | Total time blocked (seconds) |
| `task.wip` | Gauge | Current work in progress count |
| `task.throughput` | Counter | Tasks completed |
| `task.story_points_completed` | Counter | Story points completed |
| `task.count_by_status` | Gauge | Task count by status |
| `task.count_by_type` | Gauge | Task count by type |
| `sprint.velocity` | Gauge | Story points per sprint |

---

## Cardinality Guidelines

**Safe for metrics labels** (low cardinality):
- `business.criticality`
- `business.value`
- `business.owner`
- `risk.type`
- `risk.priority`
- `task.type`
- `task.status`
- `task.priority`

**Avoid in metrics labels** (high cardinality):
- `project.task` (many unique values)
- `project.trace_id` (unique per trace)
- `design.doc` (unique URLs)
- `task.id` (unique per task)
- `task.assignee` (may have many values)

Use these high-cardinality attributes in:
- Trace attributes (searchable in Tempo)
- Log attributes (indexed in Loki)
- Alert annotations (contextual)
- Span attributes (queryable via TraceQL)
