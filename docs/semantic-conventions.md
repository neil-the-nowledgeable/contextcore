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

## Cardinality Guidelines

**Safe for metrics labels** (low cardinality):
- `business.criticality`
- `business.value`
- `business.owner`
- `risk.type`
- `risk.priority`

**Avoid in metrics labels** (high cardinality):
- `project.task` (many unique values)
- `project.trace_id` (unique per trace)
- `design.doc` (unique URLs)

Use these high-cardinality attributes in:
- Trace attributes (searchable)
- Log attributes (indexed)
- Alert annotations (contextual)
