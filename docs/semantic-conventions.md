# ContextCore Semantic Conventions

This document defines the semantic conventions for ContextCore attributes — **a vendor-agnostic extension of OpenTelemetry semantic conventions** for project management telemetry.

---

## Overview

### Purpose

ContextCore semantic conventions provide a **standard vocabulary** for project management telemetry. Like OpenTelemetry's semantic conventions for traces, metrics, and logs, these conventions ensure:

- **Portability**: Telemetry can be exported to any OTLP-compatible backend
- **Interoperability**: Tools from different vendors can understand the same attributes
- **Consistency**: Teams across organizations use the same terminology
- **Queryability**: Standard attribute names enable standard queries and dashboards

### Backend Compatibility

These conventions are designed to work with **any observability backend**:

| Backend Type | Examples | Notes |
|-------------|----------|-------|
| **Trace Stores** | Jaeger, Zipkin, Tempo, Datadog APM | Task spans stored as traces |
| **Metrics Stores** | Prometheus, Mimir, InfluxDB, Datadog Metrics | Derived metrics via OTLP |
| **Log Stores** | Loki, Elasticsearch, Splunk | Structured JSON logs |
| **All-in-One** | Grafana Cloud, Datadog, New Relic | Full telemetry stack |

### Prometheus/Mimir Export Conventions

When exporting OTel metrics to Prometheus or Mimir, the following transformations apply:

| OTel Convention | Prometheus Export | Notes |
|----------------|-------------------|-------|
| Metric names with dots | Converted to underscores | `task.count_by_status` → `task_count_by_status` |
| Label names with dots | **Preserved as-is** | `task.status` stays `task.status` |
| Label names with dots | **May need quoting** | Use `"task.status"` in PromQL |

**PromQL Query Examples:**

```promql
# Labels with dots require quoting in PromQL
task_count_by_status{project="myproject", "task.status"="in_progress"}

# Simple labels don't need quoting
task_count_by_status{project="myproject", phase="development"}
```

**Dashboard Variable Queries:**

```promql
# Query label values with dots
label_values(task_count_by_status{project="myproject"}, task_status)
```

> **Note**: Some OTLP-to-Prometheus exporters may convert dots to underscores in label names. Check your exporter configuration. ContextCore emits OTel semantic convention names with dots.

### Stability

| Status | Meaning |
|--------|---------|
| **Stable** | Attribute is finalized, will not change |
| **Experimental** | May change in future versions |
| **Deprecated** | Will be removed, use alternative |

> **Note**: All ContextCore conventions are currently **Experimental** as the project matures.

---

## OTel GenAI Alignment

ContextCore aligns with the [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) to ensure interoperability.

### Dual-Emit Compatibility

ContextCore currently emits both legacy attributes (`agent.*`) and new OTel attributes (`gen_ai.*`) to support migration. Control this behavior with the `CONTEXTCORE_EMIT_MODE` environment variable:

| Mode | Value | Behavior |
|------|-------|----------|
| **Dual** | `dual` | Emits both legacy and OTel attributes (default) |
| **Legacy** | `legacy` | Emits only `agent.*` attributes |
| **OTel** | `otel` | Emits only `gen_ai.*` attributes (target state) |

```bash
# Example: Enable OTel-only mode for testing
export CONTEXTCORE_EMIT_MODE=otel
```

See the [Migration Guide](OTEL_GENAI_MIGRATION_GUIDE.md) for details.

### Compat Module

The `contextcore.compat.otel_genai` module provides the dual-emit layer:

```python
from contextcore.compat.otel_genai import AttributeMapper, get_emit_mode, OtelEmitMode

# Check current mode
mode = get_emit_mode()  # Returns OtelEmitMode.DUAL by default

# Use mapper to transform attributes
mapper = AttributeMapper()
attrs = {"agent.id": "claude-code", "agent.session_id": "sess-123"}
mapped = mapper.map_attributes(attrs)
# In DUAL mode: {"agent.id": "claude-code", "agent.session_id": "sess-123",
#                "gen_ai.agent.id": "claude-code", "gen_ai.conversation.id": "sess-123"}
```

### Attribute Mapping

| ContextCore | OTel GenAI | Description |
|-------------|------------|-------------|
| `agent.id` | `gen_ai.agent.id` | Agent identifier |
| `agent.session_id` | `gen_ai.conversation.id` | Session/Thread ID |
| `handoff.capability_id` | `gen_ai.tool.name` | Tool/Capability name |
| - | `gen_ai.system` | Provider (e.g. `openai`) |
| - | `gen_ai.request.model` | Model (e.g. `gpt-4o`) |
| - | `gen_ai.operation.name` | Operation type (e.g. `task`, `insight.emit`) |

### GenAI Attributes Reference

All `gen_ai.*` attributes emitted by ContextCore, grouped by category.

#### Agent Identity

| Attribute | Type | Description | Set By |
|-----------|------|-------------|--------|
| `gen_ai.agent.id` | `string` | Agent identifier (mapped from `agent.id`) | `InsightEmitter`, `HandoffManager` |
| `gen_ai.agent.name` | `string` | Human-readable agent name | `InsightEmitter` (constructor) |
| `gen_ai.agent.description` | `string` | Agent description or role | `InsightEmitter` (constructor) |
| `gen_ai.conversation.id` | `string` | Session/conversation ID (mapped from `agent.session_id`) | `InsightEmitter` |

#### Provider & Model

| Attribute | Type | Description | Set By |
|-----------|------|-------------|--------|
| `gen_ai.system` | `string` | LLM provider (e.g. `openai`, `anthropic`) | `InsightEmitter`, `HandoffManager` |
| `gen_ai.request.model` | `string` | Model name used for the request (e.g. `gpt-4o`) | `InsightEmitter`, `HandoffManager` |
| `gen_ai.response.model` | `string` | Model that generated the response (may differ from request) | `InsightEmitter` |

#### Token Usage

| Attribute | Type | Description | Set By |
|-----------|------|-------------|--------|
| `gen_ai.usage.input_tokens` | `int` | Number of input/prompt tokens | `InsightEmitter` |
| `gen_ai.usage.output_tokens` | `int` | Number of output/completion tokens | `InsightEmitter` |

#### Request Parameters

| Attribute | Type | Description | Set By |
|-----------|------|-------------|--------|
| `gen_ai.request.temperature` | `float` | Sampling temperature | `InsightEmitter` |
| `gen_ai.request.top_p` | `float` | Top-p (nucleus) sampling parameter | `InsightEmitter` |
| `gen_ai.request.max_tokens` | `int` | Maximum tokens requested | `InsightEmitter` |

#### Response Metadata

| Attribute | Type | Description | Set By |
|-----------|------|-------------|--------|
| `gen_ai.response.id` | `string` | Unique response identifier | `InsightEmitter` |
| `gen_ai.response.finish_reasons` | `string[]` | Reasons the model stopped generating | `InsightEmitter` |

#### Operation

| Attribute | Type | Description | Set By |
|-----------|------|-------------|--------|
| `gen_ai.operation.name` | `string` | Operation type (e.g. `insight.emit`, `handoff.request`) | `InsightEmitter`, `HandoffManager` |

#### Tool (Handoff)

| Attribute | Type | Description | Set By |
|-----------|------|-------------|--------|
| `gen_ai.tool.name` | `string` | Capability/tool name | `HandoffManager` |
| `gen_ai.tool.type` | `string` | Tool type (`agent_handoff`) | `HandoffManager` |
| `gen_ai.tool.call.id` | `string` | Handoff/call identifier | `HandoffManager` |
| `gen_ai.tool.call.arguments` | `string` | Serialized JSON input arguments | `HandoffManager` |

---

## Code Generation Attributes (`gen_ai.code.*`)

These attributes track code generation tasks with proactive truncation prevention.

### Pre-flight Attributes (Estimation)

#### `gen_ai.code.estimated_lines`
- **Type**: `int`
- **Description**: Estimated number of lines for generated output
- **Example**: `150`

#### `gen_ai.code.estimated_tokens`
- **Type**: `int`
- **Description**: Estimated token count for generated output
- **Example**: `500`

#### `gen_ai.code.estimated_complexity`
- **Type**: `string`
- **Description**: Complexity level of the generation task
- **Allowed Values**: `low`, `medium`, `high`

#### `gen_ai.code.estimation_confidence`
- **Type**: `float`
- **Description**: Confidence in the size estimate (0.0 to 1.0)
- **Example**: `0.75`

#### `gen_ai.code.max_lines_allowed`
- **Type**: `int`
- **Description**: Maximum lines allowed by the handoff contract
- **Example**: `150`

#### `gen_ai.code.action`
- **Type**: `string`
- **Description**: Pre-flight decision action
- **Allowed Values**: `generate`, `decompose`, `reject`

### Generation Attributes

#### `gen_ai.code.target_file`
- **Type**: `string`
- **Description**: Target file path for generated code
- **Example**: `"src/mymodule.py"`

#### `gen_ai.code.actual_lines`
- **Type**: `int`
- **Description**: Actual number of lines generated
- **Example**: `142`

#### `gen_ai.code.tokens_used`
- **Type**: `int`
- **Description**: Actual tokens used in generation
- **Example**: `426`

### Verification Attributes

#### `gen_ai.code.truncated`
- **Type**: `boolean`
- **Description**: Whether the output was truncated
- **Example**: `false`

#### `gen_ai.code.verification_result`
- **Type**: `string`
- **Description**: Result of post-generation verification
- **Allowed Values**: `passed`, `failed_truncation`, `failed_syntax`, `failed_missing_exports`, `failed_incomplete`

#### `gen_ai.code.verification_issues`
- **Type**: `string` (JSON array)
- **Description**: List of issues found during verification
- **Example**: `["Missing required exports: {FooBar}", "Syntax error at line 42"]`

#### `gen_ai.code.exports_found`
- **Type**: `string` (JSON array)
- **Description**: Exports detected in generated code
- **Example**: `["FooBar", "baz_function"]`

### Chunking Attributes (Decomposition)

#### `gen_ai.code.chunk_index`
- **Type**: `int`
- **Description**: Index of the current chunk (0-based)
- **Example**: `0`

#### `gen_ai.code.chunk_total`
- **Type**: `int`
- **Description**: Total number of chunks
- **Example**: `3`

#### `gen_ai.code.parent_handoff`
- **Type**: `string`
- **Description**: Parent handoff ID for correlated chunks
- **Example**: `"handoff-abc123"`

### Feature Attributes (Prime Contractor)

#### `gen_ai.code.feature_name`
- **Type**: `string`
- **Description**: Name of the feature being generated
- **Example**: `"user_authentication"`

#### `gen_ai.code.file_count`
- **Type**: `int`
- **Description**: Number of files in the generation
- **Example**: `3`

### TraceQL Queries for Code Generation

**Find truncated generations:**
```traceql
{ span.gen_ai.code.truncated = true }
| select(
    resource.project.id,
    span.gen_ai.code.estimated_lines,
    span.gen_ai.code.actual_lines,
    span.handoff.capability_id
)
```

**Find handoffs that required decomposition:**
```traceql
{ span.gen_ai.code.action = "decompose" }
| select(
    span.handoff.id,
    span.gen_ai.code.estimated_lines,
    span.gen_ai.code.max_lines_allowed
)
```

**Track size estimation accuracy:**
```traceql
{ name = "code_generation.generate" }
| select(
    span.gen_ai.code.estimated_lines,
    span.gen_ai.code.actual_lines
)
```

**Failed verifications:**
```traceql
{ name = "code_generation.verify" && status = error }
| select(span.gen_ai.code.verification_issues)
```

---

## Where Attributes Appear

ContextCore attributes appear on:
- **Resource attributes**: Attached to all telemetry from a service
- **Span attributes**: On task spans and runtime spans when relevant
- **Log attributes**: In structured log records
- **Metric labels**: On metrics (where cardinality allows)

---

## OTel Standard Resource Attributes

ContextCore automatically includes standard OpenTelemetry resource attributes on all telemetry. These enable backend systems to identify the SDK, service, and runtime environment.

### Telemetry SDK Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `telemetry.sdk.name` | string | SDK name | `"opentelemetry"` |
| `telemetry.sdk.language` | string | SDK language | `"python"` |
| `telemetry.sdk.version` | string | SDK version | `"1.39.1"` |

### Service Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `service.name` | string | Service name | `"contextcore-tracker"` |
| `service.namespace` | string | Service namespace | `"contextcore"` |
| `service.version` | string | Service version | `"0.1.0"` |

### Host & Process Attributes

| Attribute | Type | Description | Example |
|-----------|------|-------------|---------|
| `host.name` | string | Hostname | `"my-laptop.local"` |
| `host.arch` | string | CPU architecture | `"arm64"`, `"x86_64"` |
| `os.type` | string | Operating system | `"darwin"`, `"linux"` |
| `os.version` | string | OS version | `"24.6.0"` |
| `process.pid` | int | Process ID | `12345` |
| `process.executable.path` | string | Python executable | `"/usr/bin/python3"` |
| `process.runtime.name` | string | Python implementation | `"CPython"` |
| `process.runtime.version` | string | Python version | `"3.11.5"` |

### Example Resource Output

```json
{
  "telemetry.sdk.name": "opentelemetry",
  "telemetry.sdk.language": "python",
  "telemetry.sdk.version": "1.39.1",
  "service.name": "contextcore-tracker",
  "service.namespace": "contextcore",
  "service.version": "0.1.0",
  "host.name": "my-laptop.local",
  "host.arch": "arm64",
  "os.type": "darwin",
  "os.version": "24.6.0",
  "process.pid": 12345,
  "deployment.environment.name": "production",
  "project.id": "my-project"
}
```

---

## Span Naming Conventions

ContextCore follows OTel span naming conventions:

- **Use dot separators**: `contextcore.task.story` not `task:PROJ-123`
- **Low cardinality names**: Type in name, ID in attributes
- **Namespace prefix**: `contextcore.*` for ContextCore spans

### Task Spans

| Span Name | Description | Key Attributes |
|-----------|-------------|----------------|
| `contextcore.task.epic` | Epic task span | `task.id`, `task.title` |
| `contextcore.task.story` | Story task span | `task.id`, `task.title`, `task.parent_id` |
| `contextcore.task.task` | Task span | `task.id`, `task.title` |
| `contextcore.task.subtask` | Subtask span | `task.id`, `task.parent_id` |
| `contextcore.task.bug` | Bug fix span | `task.id`, `task.title` |
| `contextcore.sprint` | Sprint span | `sprint.id`, `sprint.name` |

### TraceQL Queries

```traceql
# Find all story tasks (uses span name, not attribute)
{ name = "contextcore.task.story" }

# Find specific task by ID (attribute query)
{ name =~ "contextcore.task.*" && span.task.id = "PROJ-123" }

# Find all sprints
{ name = "contextcore.sprint" }
```

---

## Naming Conventions

### Namespace Prefixes

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

### Singular vs Plural

Use **singular form** for attribute values and enum members, **plural form** for collections and method names:

| Context | Form | Example |
|---------|------|---------|
| Attribute values | Singular | `insight_type="decision"` |
| Enum members | Singular | `InsightType.DECISION` |
| Collection variables | Plural | `decisions: List[InsightData]` |
| Query method names | Plural | `query_decisions()`, `list_blockers()` |
| Status fields | Singular | `task.status="in_progress"` |

**Correct examples:**
```python
# Attribute values - singular
insight = InsightData(insight_type="decision", ...)
task.update_status("in_progress")

# Collections - plural
recent_decisions = querier.query(insight_type="decision")
active_blockers = querier.list_blockers()
```

**Avoid:**
```python
# Wrong - plural in attribute value
insight = InsightData(insight_type="decisions", ...)  # DON'T

# Wrong - singular for collection
decision = querier.query(...)  # Should be: decisions = ...
```

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

## Deployment Environment (OTel Standard)

ContextCore supports the OTel semantic convention `deployment.environment.name` which is being stabilized for cross-vendor interoperability.

### `deployment.environment.name`
- **Type**: `string`
- **Description**: Name of the deployment environment (production, staging, development, etc.)
- **Example**: `"production"`, `"staging"`, `"development"`, `"test"`
- **Status**: Experimental (tracking OTel stabilization)

### Why This Matters

This attribute enables:
- **Alert Routing**: `deployment.environment.name == 'production'` → page on-call
- **Cost Attribution**: Map telemetry costs to FinOps categories (prod=COGS, dev=R&D)
- **Data Residency**: Route production PII to encrypted storage
- **Service Graph Differentiation**: Separate prod/staging traffic in Grafana topology

### Vendor Mapping

The attribute maps to vendor-specific reserved keys:

| Platform | Attribute Key | Notes |
|----------|--------------|-------|
| **Datadog** | `env` | Reserved tag, lowercase |
| **Splunk** | `deployment.environment` | Indexed dimension |
| **Grafana** | `deployment_environment` | Snake_case preferred |
| **New Relic** | `tags.Environment` | Key-value pair |

### Detection Sources

ContextCore detects `deployment.environment.name` from (in priority order):

1. **K8s Annotations**:
   - `contextcore.io/environment`
   - `contextcore.io/env`
   - `contextcore.io/deployment-environment`

2. **Environment Variables**:
   - `CONTEXTCORE_ENVIRONMENT`
   - `DEPLOYMENT_ENVIRONMENT`

### Example Usage

**K8s Pod Annotation:**
```yaml
metadata:
  annotations:
    contextcore.io/environment: "production"
```

**Environment Variable:**
```bash
export CONTEXTCORE_ENVIRONMENT=production
```

**In Resource Attributes:**
```json
{
  "deployment.environment.name": "production",
  "project.id": "checkout-service",
  "business.criticality": "critical"
}
```

---

## K8s Annotations

ContextCore uses annotations with the `contextcore.io/` prefix:

| Annotation | Maps To |
|------------|---------|
| `contextcore.io/environment` | `deployment.environment.name` |
| `contextcore.io/env` | `deployment.environment.name` |
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
  "deployment.environment.name": "production",

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

## Exception Span Attributes

When exceptions occur during task operations, ContextCore records them on the active span following the [OTel exception semantic conventions](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/).

The `span.record_exception()` API automatically adds:

| Attribute | Type | Description |
|-----------|------|-------------|
| `exception.type` | `string` | Fully-qualified exception class name |
| `exception.message` | `string` | Exception message string |
| `exception.stacktrace` | `string` | Full stack trace as a string |

Additionally, the span status is set to `ERROR` with a description of the form `"{ExceptionType}: {message}"`.

### When Exceptions Are Recorded

| Operation | Trigger | Example |
|-----------|---------|---------|
| State persistence | `_save_state()` fails (I/O error, serialization) | `OSError: disk full` |
| Task exception | `record_task_exception()` called by consumer | Application-specific errors |

### Example: Exception on a Task Span

```
Span: contextcore.task.story
  Status: ERROR ("OSError: disk full")
  Events:
    - name: "exception"
      attributes:
        exception.type: "OSError"
        exception.message: "disk full"
        exception.stacktrace: "Traceback (most recent call last):\n  ..."
```

### TraceQL Queries for Exceptions

```traceql
# Find all task spans with exceptions
{ rootServiceName = "contextcore" && status = error }

# Find specific exception types
{ span.exception.type = "TimeoutError" }

# Exceptions on story tasks
{ name = "contextcore.task.story" && status = error }
```

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

## OTel Log Data Model Compliance

ContextCore structured logs follow the [OTel Log Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) for interoperability with any OTel-compatible log backend.

### Standard Fields

Every log entry includes these OTel-standard fields:

| Field | Type | Description | Reference |
|-------|------|-------------|-----------|
| `timestamp` | `string` | ISO 8601 UTC timestamp | Human-readable form |
| `timestamp_unix_nano` | `int` | Nanoseconds since epoch | OTel standard timestamp |
| `severity_number` | `int` | Severity 1-24 per RFC 5424 mapping | [Severity Fields](https://opentelemetry.io/docs/specs/otel/logs/data-model/#severity-fields) |
| `severity_text` | `string` | Uppercase level (`INFO`, `WARN`, `ERROR`) | OTel standard |
| `body` | `string` | Log message (event name) | OTel standard |
| `trace_id` | `string` | 32-char hex trace ID | Log-to-trace correlation |
| `span_id` | `string` | 16-char hex span ID | Log-to-trace correlation |
| `trace_flags` | `int` | W3C trace flags (if set) | Sampling context |

### Severity Number Mapping

ContextCore maps log levels to OTel severity numbers (RFC 5424 aligned):

| Level | severity_number | severity_text |
|-------|----------------|---------------|
| trace | 1 | `TRACE` |
| debug | 5 | `DEBUG` |
| info | 9 | `INFO` |
| warn | 13 | `WARN` |
| error | 17 | `ERROR` |
| fatal | 21 | `FATAL` |

### Log-to-Trace Correlation

Every log entry includes `trace_id` and `span_id` for correlation with active traces. This enables jumping from a log entry in Loki directly to the corresponding trace in Tempo.

**Resolution priority:**
1. Explicit `trace_id`/`span_id` passed as keyword arguments
2. Active span from OpenTelemetry context (automatic)

### Example OTel-Compliant Log Entry

```json
{
  "timestamp": "2025-01-15T10:30:00.000000+00:00",
  "timestamp_unix_nano": 1736935800000000000,
  "severity_number": 9,
  "severity_text": "INFO",
  "body": "task.status_changed",
  "event": "task.status_changed",
  "service": "contextcore",
  "project_id": "my-project",
  "task_id": "PROJ-123",
  "from_status": "todo",
  "to_status": "in_progress",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "span_id": "b7ad6b7169203331"
}
```

### LogQL Queries Using OTel Fields

```logql
# Filter by severity (only warnings and errors)
{service="contextcore"} | json | severity_number >= 13

# Correlate logs with a specific trace
{service="contextcore"} | json | trace_id = "0af7651916cd43dd8448eb211c80319c"

# Error events with trace context for drill-down
{service="contextcore"} | json | severity_text = "ERROR"
| line_format "{{.body}} trace={{.trace_id}} span={{.span_id}}"
```

---

## Metrics from Logs

ContextCore supports deriving metrics directly from structured logs using Loki recording rules. This enables real-time progress tracking without requiring a separate metrics pipeline.

### Log Event: `task.progress_updated`

Emitted when task progress changes. Contains:

| Field | Type | Description |
|-------|------|-------------|
| `event` | `string` | `"task.progress_updated"` |
| `task_id` | `string` | Task identifier |
| `task_type` | `string` | Task type (epic, story, task, etc.) |
| `percent_complete` | `float` | Progress percentage (0-100) |
| `source` | `string` | How progress was determined: `manual`, `subtask`, `estimate` |
| `subtask_completed` | `int` | Completed subtasks (when source=subtask) |
| `subtask_count` | `int` | Total subtasks (when source=subtask) |
| `sprint_id` | `string` | Sprint identifier (optional) |
| `project_id` | `string` | Project identifier |

### Example Log Entry

```json
{
  "timestamp": "2025-01-15T10:30:00.000000+00:00",
  "timestamp_unix_nano": 1736935800000000000,
  "severity_number": 9,
  "severity_text": "INFO",
  "body": "task.progress_updated",
  "event": "task.progress_updated",
  "service": "contextcore",
  "project_id": "my-project",
  "task_id": "PROJ-123",
  "task_type": "story",
  "percent_complete": 60.0,
  "source": "subtask",
  "subtask_completed": 3,
  "subtask_count": 5,
  "sprint_id": "sprint-3",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "span_id": "b7ad6b7169203331"
}
```

### Recording Rule Naming Convention

Recording rules and alerts follow the [kubernetes-mixin](https://github.com/kubernetes-monitoring/kubernetes-mixin) naming conventions to ensure consistency with the broader Kubernetes/Prometheus ecosystem.

#### Recording Rule Names

**Pattern:** `<aggregation_level>:<base_metric>:<aggregation_function>`

- **`contextcore_`** prefix on base metric to avoid collisions with other systems
- Colons separate the three components (valid in Prometheus metric names)

**Aggregation levels:**

| Level | Description | Example Labels |
|-------|-------------|---------------|
| `project` | Per-project aggregation | `project_id` |
| `project_sprint` | Per-project and sprint | `project_id`, `sprint_id` |
| `project_task` | Per-project and task | `project_id`, `task_id` |

**Aggregation suffixes:**

| Suffix | Description |
|--------|-------------|
| `max_over_time5m` | Maximum value over 5-minute window |
| `avg` | Average across group |
| `count` | Count of matching series |
| `rate1h` | Per-second rate over 1-hour window |
| `last` | Most recent value |
| `count_by_status` | Count grouped by status |

**Recording rule name mapping:**

| Rule Name | Source | Description |
|-----------|--------|-------------|
| `project:contextcore_task_percent_complete:max_over_time5m` | Loki | Per-task progress, max over 5m |
| `project_sprint:contextcore_task_percent_complete:avg` | Derived | Average progress per sprint |
| `project_sprint:contextcore_task_completed:count` | Derived | Count of completed tasks per sprint |
| `project_task:contextcore_task_progress:rate1h` | Loki | Progress rate per task over 1h |
| `project:contextcore_task_count:count_by_status` | Loki | Task count grouped by status |
| `project_sprint:contextcore_sprint_planned_points:last` | Mimir | Planned points per sprint |

#### Alert Naming Convention

**Pattern:** `ContextCore[Resource][Issue]`

Parallels kubernetes-mixin's `Kube[Resource][Issue]` pattern.

**Severity taxonomy** (matching kubernetes-mixin):

| Severity | Meaning | Response |
|----------|---------|----------|
| `critical` | Service-affecting failure | Pages on-call immediately |
| `warning` | Degraded but functional | Next-business-day work queue |
| `info` | Informational | Troubleshooting enrichment |

**Defined alerts:**

| Alert | Severity | Description | Source Risk |
|-------|----------|-------------|------------|
| `ContextCoreExporterFailure` | critical | OTLP export errors detected | P1 — OTLP export blocks reporting |
| `ContextCoreSpanStateLoss` | critical | Span state persistence failure | P1 — Controller restart loses spans |
| `ContextCoreInsightLatencyHigh` | warning | Insight query P99 > 500ms | P2 — Insight queries exceed budget |
| `ContextCoreTaskStalled` | warning | Task stuck > 24h with no status change | P2 — Stalled tasks |

All alerts **must** include `annotations.runbook_url`.

### Loki Recording Rules

Generate metrics from `percent_complete` logs using Loki Ruler:

```yaml
# /etc/loki/rules/fake/contextcore-rules.yaml
groups:
  - name: contextcore_task_progress
    interval: 1m
    rules:
      # Task progress gauge - last reported percent_complete per task
      - record: "project:contextcore_task_percent_complete:max_over_time5m"
        expr: |
          max by (project_id, task_id, task_type, sprint_id) (
            max_over_time(
              {service="contextcore"}
              | json
              | event = "task.progress_updated"
              | unwrap percent_complete
              [5m]
            )
          )
        labels:
          source: loki

      # Average progress by sprint
      - record: "project_sprint:contextcore_task_percent_complete:avg"
        expr: |
          avg by (project_id, sprint_id) (
            project:contextcore_task_percent_complete:max_over_time5m{sprint_id!=""}
          )
        labels:
          source: derived

      # Count of completed tasks (100%)
      - record: "project_sprint:contextcore_task_completed:count"
        expr: |
          count by (project_id, sprint_id) (
            project:contextcore_task_percent_complete:max_over_time5m == 100
          )
        labels:
          source: derived

      # Task progress rate (change per hour)
      - record: "project_task:contextcore_task_progress:rate1h"
        expr: |
          sum by (project_id, task_id) (
            rate(
              {service="contextcore"}
              | json
              | event = "task.progress_updated"
              | unwrap percent_complete
              [1h]
            )
          )
        labels:
          source: loki

  - name: contextcore_task_status
    interval: 1m
    rules:
      # Task count grouped by status
      - record: "project:contextcore_task_count:count_by_status"
        expr: |
          count by (project_id, to_status) (
            last_over_time(
              {service="contextcore"}
              | json
              | event = "task.status_changed"
              [5m]
            )
          )
        labels:
          source: loki
```

### LogQL Queries for Dashboards

Query progress directly in Grafana without recording rules:

```logql
# Current progress for all tasks in a project
{service="contextcore", project_id="my-project"}
| json
| event = "task.progress_updated"
| line_format "{{.task_id}}: {{.percent_complete}}%"

# Progress events over time (for time-series visualization)
max_over_time(
  {service="contextcore"}
  | json
  | event = "task.progress_updated"
  | unwrap percent_complete
  [5m]
) by (task_id)

# Average sprint progress
avg(
  max by (task_id) (
    {service="contextcore", sprint_id="sprint-3"}
    | json
    | event = "task.progress_updated"
    | unwrap percent_complete
  )
)
```

### Benefits of Metrics from Logs

1. **Single data path**: Progress updates flow through logs to both storage and metrics
2. **Reduced infrastructure**: No separate metrics exporter needed for task progress
3. **Queryable context**: Full log context available alongside metrics
4. **Flexible aggregation**: Aggregate by any log field (task_type, sprint_id, etc.)
5. **Cost effective**: Leverage existing Loki infrastructure

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

---

## Exporter Configuration

ContextCore exports telemetry via OTLP. Configure the endpoint for your backend:

### Environment Variables

```bash
# Generic OTLP endpoint (works with any OTLP-compatible backend)
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"

# Optional: separate endpoints for traces, metrics, logs
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://tempo:4317"
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT="http://mimir:4317"
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT="http://loki:4317"
```

### Backend-Specific Examples

**Jaeger:**
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://jaeger-collector:4317"
```

**Grafana Cloud:**
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp-gateway-prod-us-central-0.grafana.net/otlp"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64-encoded-credentials>"
```

**Datadog:**
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
# Requires Datadog Agent with OTLP ingest enabled
```

**Honeycomb:**
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://api.honeycomb.io:443"
export OTEL_EXPORTER_OTLP_HEADERS="x-honeycomb-team=<API_KEY>"
```

**New Relic:**
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp.nr-data.net:4317"
export OTEL_EXPORTER_OTLP_HEADERS="api-key=<INGEST_LICENSE_KEY>"
```

### Reference Implementation (Local Development)

The Grafana stack reference implementation runs locally:

```bash
# Start local observability stack
docker-compose up -d  # Grafana, Tempo, Mimir, Loki, Alloy

# ContextCore defaults to localhost:4317
contextcore task start --id PROJ-123 --title "Test task"
```

---

## Query Examples by Backend

These semantic conventions enable consistent queries across backends:

**TraceQL (Tempo, Grafana Cloud):**
```
{ task.status = "blocked" && task.type = "story" }
```

**Jaeger:**
```
service=contextcore-tracker task.status=blocked
```

**PromQL (any Prometheus-compatible backend):**
```promql
sum by (task.status) (task_count_by_status{project_id="my-project"})
```

**LogQL (Loki):**
```logql
{service="contextcore"} | json | event="task.completed"
```

**Datadog:**
```
@task.status:blocked @task.type:story
```

The consistent attribute naming ensures dashboards and queries are portable across backends.

---

## Built-in Dashboards

ContextCore automatically provisions two Grafana dashboards on installation. These dashboards use the semantic conventions defined in this document.

### Project Portfolio Overview

High-level view showing all projects tracked by ContextCore:

| Panel | Primary Query | Conventions Used |
|-------|--------------|------------------|
| Active Projects | Count distinct `project.id` | `project.id` |
| Health Matrix | Aggregate by `project.id` with status | `project.id`, `task.status`, `task.percent_complete` |
| Progress Gauges | `task_percent_complete` by project | `task.percent_complete`, `task.type` |
| Velocity Trend | `sprint.completed_points` over time | `sprint.id`, `sprint.planned_points`, `sprint.completed_points` |
| Blocked Tasks | Filter `task.status = "blocked"` | `task.status`, `task.blocked_by`, `task.id` |
| Status Distribution | Group by `task.status` | `task.status`, `project.id` |

### Project Details (Drill-down)

Deep-dive view for a single project:

| Panel | Primary Query | Conventions Used |
|-------|--------------|------------------|
| Sprint Burndown | `sprint.planned_points` - completed | `sprint.id`, `task.story_points` |
| Kanban Board | Tasks grouped by `task.status` | `task.status`, `task.parent_id`, `task.type` |
| Work Breakdown | Hierarchical by `task.parent_id` | `task.parent_id`, `task.type`, `task.percent_complete` |
| Blocker Details | `task.status = "blocked"` with context | `task.blocked_by`, `task.id`, span events |
| Team Workload | Sum `task.story_points` by `task.assignee` | `task.assignee`, `task.story_points` |
| Cycle Time | `task.cycle_time` histogram | `task.lead_time`, `task.cycle_time` |
| Activity Log | Filter by `project.id` | All task event attributes |

### Dashboard Query Patterns

**TraceQL (Tempo) - Task Spans:**
```traceql
# All blocked stories in a project
{ project.id = "my-project" && task.status = "blocked" && task.type = "story" }

# Tasks with hierarchy
{ project.id = "my-project" && task.parent_id != "" }
| select(task.id, task.title, task.status, task.percent_complete, task.parent_id)
```

**LogQL (Loki) - Task Events:**
```logql
# Status changes for a project
{service="contextcore", project_id="my-project"}
| json
| event="task.status_changed"

# Progress updates (for metrics derivation)
{service="contextcore"}
| json
| event="task.progress_updated"
| unwrap percent_complete
```

**PromQL (Mimir) - Derived Metrics:**
```promql
# Average progress by project
avg by (project_id) (task_percent_complete{task_type=~"story|epic"})

# Work in progress count
count by (project_id) (task_status{status="in_progress"})

# Velocity trend
sum by (sprint_id) (increase(task_story_points_completed_total[7d]))
```

See [docs/dashboards/](dashboards/) for full dashboard specifications.

---

## Installation Verification Attributes

ContextCore tracks its own installation state using telemetry. This enables self-verification and ensures deployments are complete.

### `contextcore.install.*` Namespace

Installation verification attributes use the `contextcore.install.*` namespace.

### Requirement Attributes

#### `contextcore.install.requirement.id`
- **Type**: `string`
- **Description**: Unique identifier for the installation requirement
- **Example**: `"docker_compose"`, `"grafana_running"`, `"tempo_config"`

#### `contextcore.install.requirement.name`
- **Type**: `string`
- **Description**: Human-readable requirement name
- **Example**: `"Docker Compose Configuration"`, `"Grafana Running"`

#### `contextcore.install.requirement.category`
- **Type**: `string`
- **Description**: Requirement category
- **Allowed Values**: `configuration`, `infrastructure`, `tooling`, `observability`, `documentation`

#### `contextcore.install.requirement.status`
- **Type**: `string`
- **Description**: Result of requirement check
- **Allowed Values**: `passed`, `failed`, `skipped`, `error`

#### `contextcore.install.requirement.critical`
- **Type**: `boolean`
- **Description**: Whether the requirement is critical for installation completeness
- **Example**: `true`, `false`

#### `contextcore.install.requirement.duration_ms`
- **Type**: `float`
- **Description**: Time to check the requirement in milliseconds
- **Example**: `12.5`

### Summary Attributes

#### `contextcore.install.completeness`
- **Type**: `float`
- **Description**: Overall installation completeness percentage (0-100)
- **Example**: `85.5`

#### `contextcore.install.is_complete`
- **Type**: `boolean`
- **Description**: Whether all critical requirements are met
- **Example**: `true`

#### `contextcore.install.critical_met`
- **Type**: `int`
- **Description**: Number of critical requirements that passed
- **Example**: `15`

#### `contextcore.install.critical_total`
- **Type**: `int`
- **Description**: Total number of critical requirements
- **Example**: `18`

### Installation Metrics

**OTel to Prometheus name mapping**: The Alloy/Prometheus exporter adds unit suffixes.

| OTel Metric | Prometheus Metric | Type | Description | Labels |
|-------------|-------------------|------|-------------|--------|
| `contextcore.install.completeness` | `contextcore_install_completeness_percent` | Gauge | Overall completeness % | `installation_id` |
| `contextcore.install.requirement.status` | `contextcore_install_requirement_status_ratio` | Gauge | Per-requirement status (1=passed, 0=failed) | `requirement_id`, `requirement_name`, `category`, `critical` |
| `contextcore.install.category.completeness` | `contextcore_install_category_completeness_percent` | Gauge | Category completeness % | `installation_id`, `category` |
| `contextcore.install.critical.met` | `contextcore_install_critical_met_ratio` | Gauge | Critical requirements passed | `installation_id` |
| `contextcore.install.critical.total` | `contextcore_install_critical_total_ratio` | Gauge | Total critical requirements | `installation_id` |
| `contextcore.install.verification.duration` | `contextcore_install_verification_duration_milliseconds` | Histogram | Verification duration (ms) | `installation_id` |

### Installation Spans

Verification runs as a trace with child spans for each requirement check:

```
contextcore.install.verify (root span)
├── install.verify.docker_compose
├── install.verify.makefile
├── install.verify.tempo_config
├── install.verify.grafana_running
│   └── (depends_on: docker_compose, docker_available)
└── ... (one span per requirement)
```

#### Root Span Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `contextcore.install.total_requirements` | `int` | Total requirements checked |
| `contextcore.install.categories` | `string[]` | Categories checked |
| `contextcore.install.completeness` | `float` | Final completeness % |
| `contextcore.install.is_complete` | `boolean` | All critical met |
| `contextcore.install.critical_met` | `int` | Critical passed count |

#### Child Span Attributes

Each requirement check span includes:
- `contextcore.install.requirement.id`
- `contextcore.install.requirement.name`
- `contextcore.install.requirement.category`
- `contextcore.install.requirement.critical`
- `contextcore.install.requirement.status`
- `contextcore.install.requirement.duration_ms`

### Installation Requirements

ContextCore tracks these requirements organized by category:

#### Configuration
| ID | Name | Critical | Description |
|----|------|----------|-------------|
| `docker_compose` | Docker Compose Configuration | Yes | docker-compose.yaml exists |
| `makefile` | Makefile | Yes | Operational targets available |
| `tempo_config` | Tempo Configuration | Yes | tempo/tempo.yaml exists |
| `mimir_config` | Mimir Configuration | Yes | mimir/mimir.yaml exists |
| `loki_config` | Loki Configuration | Yes | loki/loki.yaml exists |
| `grafana_datasources_config` | Grafana Datasources | Yes | Auto-provisioning config |
| `grafana_dashboards_config` | Grafana Dashboards | No | Dashboard provisioning |

#### Tooling
| ID | Name | Critical | Description |
|----|------|----------|-------------|
| `cli_installed` | ContextCore CLI | Yes | contextcore command available |
| `ops_module` | Operations Module | Yes | contextcore.ops module |
| `install_module` | Installation Module | No | contextcore.install module |
| `docker_available` | Docker Available | Yes | Docker daemon running |
| `make_available` | Make Available | No | make command available |

#### Infrastructure
| ID | Name | Critical | Depends On |
|----|------|----------|------------|
| `grafana_running` | Grafana Running | Yes | docker_compose, docker_available |
| `tempo_running` | Tempo Running | Yes | docker_compose, docker_available, tempo_config |
| `mimir_running` | Mimir Running | Yes | docker_compose, docker_available, mimir_config |
| `loki_running` | Loki Running | Yes | docker_compose, docker_available, loki_config |
| `otlp_grpc` | OTLP gRPC Endpoint | Yes | tempo_running |
| `otlp_http` | OTLP HTTP Endpoint | Yes | tempo_running |
| `data_persistence` | Data Persistence | Yes | docker_compose |

#### Observability
| ID | Name | Critical | Depends On |
|----|------|----------|------------|
| `grafana_tempo_datasource` | Tempo Datasource | Yes | grafana_running |
| `grafana_mimir_datasource` | Mimir Datasource | Yes | grafana_running |
| `grafana_loki_datasource` | Loki Datasource | Yes | grafana_running |
| `grafana_dashboards` | Dashboards Provisioned | No | grafana_running |

#### Documentation
| ID | Name | Critical | Description |
|----|------|----------|-------------|
| `operational_resilience_doc` | Operational Resilience Guide | No | docs/OPERATIONAL_RESILIENCE.md |
| `operational_runbook` | Operational Runbook | No | docs/OPERATIONAL_RUNBOOK.md |

### TraceQL Queries for Installation

```traceql
# All installation verifications
{ name = "contextcore.install.verify" }

# Failed requirements only
{ name =~ "install.verify.*" && contextcore.install.requirement.status = "failed" }

# Critical failures
{ contextcore.install.requirement.critical = true && contextcore.install.requirement.status = "failed" }

# Infrastructure checks
{ contextcore.install.requirement.category = "infrastructure" }

# Verification history with completeness
{ name = "contextcore.install.verify" }
| select(contextcore.install.completeness, contextcore.install.critical_met)
```

### PromQL Queries for Installation

**Note**: OTel to Prometheus conversion adds unit suffixes:
- `%` -> `_percent`
- `1` (unitless) -> `_ratio`
- `ms` -> `_milliseconds`

```promql
# Overall installation completeness (note: _percent suffix)
contextcore_install_completeness_percent{installation_id="contextcore"}

# Failed requirements count (note: _ratio suffix)
count(contextcore_install_requirement_status_ratio == 0)

# Critical requirements status (note: _ratio suffix)
contextcore_install_critical_met_ratio / contextcore_install_critical_total_ratio * 100

# Category completeness (note: _percent suffix)
contextcore_install_category_completeness_percent{category="infrastructure"}

# Verification duration trend (note: _milliseconds suffix)
histogram_quantile(0.95, rate(contextcore_install_verification_duration_milliseconds_bucket[1h]))
```

### CLI Usage

```bash
# Full verification with telemetry
contextcore install verify

# Quick status check (no telemetry)
contextcore install status

# Check specific categories
contextcore install verify --category infrastructure --category tooling

# JSON output for automation
contextcore install verify --format json
```
