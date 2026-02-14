# OpenTelemetry Conventions & Standards Audit for ContextCore

> **Date**: 2026-02-03
> **OTel Specification Version**: v1.53.0
> **Semantic Conventions Version**: v1.39.0
> **OTLP Version**: v1.9.0

This document catalogs all applicable OpenTelemetry conventions, standards, and Special Interest Groups (SIGs), then assesses ContextCore's current compliance with each.

---

## Table of Contents

- [Part 1: All Applicable OTel Conventions & Standards](#part-1-all-applicable-otel-conventions--standards)
  - [1. Semantic Conventions](#1-semantic-conventions)
  - [2. Specification Standards](#2-specification-standards)
  - [3. Best Practices & Guidelines](#3-best-practices--guidelines)
  - [4. Special Interest Groups (SIGs)](#4-special-interest-groups-sigs)
  - [5. Compliance & Certification Programs](#5-compliance--certification-programs)
- [Part 2: ContextCore Compliance Assessment](#part-2-contextcore-compliance-assessment)
  - [6. What ContextCore Follows](#6-what-contextcore-follows)
  - [7. What ContextCore Does Not Follow](#7-what-contextcore-does-not-follow)
  - [8. Compliance Summary Matrix](#8-compliance-summary-matrix)
  - [9. Recommended Adoption Roadmap](#9-recommended-adoption-roadmap)

---

# Part 1: All Applicable OTel Conventions & Standards

## 1. Semantic Conventions

### 1.1 General Resource Conventions (Stable)

Standard resource attributes that identify the entity producing telemetry.

| Namespace | Key Attributes | Maturity |
|-----------|---------------|----------|
| `service.*` | `service.name`, `service.version`, `service.namespace`, `service.instance.id` | **Stable** |
| `telemetry.sdk.*` | `telemetry.sdk.name`, `telemetry.sdk.language`, `telemetry.sdk.version` | **Stable** |
| `host.*` | `host.name`, `host.arch`, `host.id`, `host.type`, `host.image.name` | **Stable** |
| `os.*` | `os.type`, `os.version`, `os.name`, `os.description` | **Stable** |
| `process.*` | `process.pid`, `process.executable.path`, `process.command_line`, `process.runtime.name`, `process.runtime.version` | **Stable** |
| `deployment.*` | `deployment.environment.name`, `deployment.id` | **Stable** |

**Relevance to ContextCore**: CRITICAL -- these identify every ContextCore service instance.

### 1.2 Kubernetes Resource Conventions (Stable)

| Namespace | Key Attributes | Maturity |
|-----------|---------------|----------|
| `k8s.pod.*` | `k8s.pod.name`, `k8s.pod.uid`, `k8s.pod.labels.*`, `k8s.pod.annotations.*` | **Stable** |
| `k8s.namespace.*` | `k8s.namespace.name` | **Stable** |
| `k8s.deployment.*` | `k8s.deployment.name`, `k8s.deployment.uid` | **Stable** |
| `k8s.node.*` | `k8s.node.name`, `k8s.node.uid` | **Stable** |
| `k8s.container.*` | `k8s.container.name`, `k8s.container.restart_count` | **Stable** |
| `k8s.cluster.*` | `k8s.cluster.name`, `k8s.cluster.uid` | **Stable** |
| `k8s.replicaset.*` | `k8s.replicaset.name`, `k8s.replicaset.uid` | **Stable** |

**Relevance to ContextCore**: HIGH -- ContextCore deploys as Kubernetes controller.

### 1.3 Cloud Provider Resource Conventions (Stable)

| Namespace | Key Attributes | Maturity |
|-----------|---------------|----------|
| `cloud.*` | `cloud.provider`, `cloud.account.id`, `cloud.region`, `cloud.availability_zone`, `cloud.platform`, `cloud.resource_id` | **Stable** |
| Provider-specific | AWS (`aws.*`), GCP (`gcp.*`), Azure (`azure.*`) | **Stable** |

**Relevance to ContextCore**: MEDIUM -- relevant when deployed to cloud environments.

### 1.4 Generative AI Conventions (Experimental)

The most directly relevant convention set for ContextCore's agent/LLM features.

#### GenAI Client Spans

| Attribute | Description | Maturity |
|-----------|-------------|----------|
| `gen_ai.operation.name` | Operation type: `chat`, `text_completion`, `embeddings`, `create_agent`, `invoke_agent`, `execute_tool` | **Experimental** |
| `gen_ai.system` | Provider system: `openai`, `anthropic`, `cohere`, etc. | **Experimental** |
| `gen_ai.request.model` | Model requested | **Experimental** |
| `gen_ai.response.model` | Model actually used | **Experimental** |
| `gen_ai.request.temperature` | Sampling temperature | **Experimental** |
| `gen_ai.request.max_tokens` | Maximum tokens requested | **Experimental** |
| `gen_ai.response.finish_reasons` | Reasons generation stopped | **Experimental** |
| `gen_ai.provider.name` | Provider name if different from system | **Experimental** |

#### GenAI Agent Spans

| Attribute | Description | Maturity |
|-----------|-------------|----------|
| `gen_ai.agent.id` | Unique agent identifier | **Experimental** |
| `gen_ai.agent.name` | Human-readable agent name | **Experimental** |
| `gen_ai.agent.description` | Agent purpose description | **Experimental** |
| `gen_ai.conversation.id` | Conversation/session identifier | **Experimental** |

#### GenAI Agent Operations

| Operation | Span Name Format | Span Kind |
|-----------|-----------------|-----------|
| `create_agent` | `create_agent {gen_ai.agent.name}` | `INTERNAL` |
| `invoke_agent` | `invoke_agent {gen_ai.agent.name}` | `CLIENT` (remote) or `INTERNAL` (in-process) |

#### GenAI Events

| Event | Description | Maturity |
|-------|-------------|----------|
| Input chat messages | User/system/assistant message content | **Experimental** |
| Output chat messages | Generated response content | **Experimental** |
| Evaluation events | Quality/safety evaluation results | **Experimental** |
| Reasoning content | Chain-of-thought reasoning | **Experimental** |

#### GenAI Metrics

| Metric | Type | Unit | Description |
|--------|------|------|-------------|
| `gen_ai.client.token.usage` | Histogram | `{token}` | Token usage per request (input/output) |
| `gen_ai.server.request.duration` | Histogram | `s` | Server-side request duration |
| `gen_ai.server.time_per_output_token` | Histogram | `s` | Decode phase latency per token |
| `gen_ai.server.time_to_first_token` | Histogram | `s` | Prefill + queue time |

#### GenAI Provider-Specific Extensions

| Provider | Conventions |
|----------|------------|
| OpenAI | Extended span attributes, tool call events |
| Azure AI Inference | Azure-specific resource attributes |
| AWS Bedrock | Bedrock-specific attributes |

**Relevance to ContextCore**: CRITICAL -- ContextCore's agent insights, dual-emit strategy, and LLM integration directly map here.

### 1.5 CI/CD Conventions (Experimental)

Directly parallels ContextCore's tasks-as-spans model.

| Signal | Key Attributes | Maturity |
|--------|---------------|----------|
| **Pipeline Spans** | `cicd.pipeline.name`, `cicd.pipeline.run.id`, `cicd.pipeline.task.name`, `cicd.pipeline.task.run.id`, `cicd.pipeline.task.type`, `cicd.pipeline.action.name` | **Experimental** |
| **CICD Resource** | `cicd.worker.id`, `cicd.worker.name`, `cicd.worker.url.full` | **Experimental** |
| **CICD Metrics** | Host, container, and runtime metrics per pipeline | **Experimental** |
| **CICD Logs** | Trace-correlated pipeline logs | **Experimental** |

| Span Pattern | Kind | Example |
|-------------|------|---------|
| Pipeline run | `SERVER` | Top-level span for entire pipeline |
| Task execution | `INTERNAL` | Individual task within pipeline |
| Span name | -- | `{action} {pipeline}` |

**Relevance to ContextCore**: HIGH -- structural parallel to `project.task` spans.

### 1.6 Exception/Error Conventions (Stable)

| Convention | Details | Maturity |
|-----------|---------|----------|
| Exception events | Event name: `exception`; attributes: `exception.type`, `exception.message`, `exception.stacktrace` | **Stable** |
| Error type | `error.type` attribute on spans | **Stable** |
| Recording errors | Span status set to `Error` with description | **Stable** |
| Handled errors | Gracefully handled errors SHOULD NOT be recorded as error status | **Stable** |
| Deduplication | Same exception SHOULD NOT be recorded more than once | **Stable** |

**Relevance to ContextCore**: HIGH -- task failures, agent errors, and blocked tasks.

### 1.7 HTTP Conventions (Stable)

| Signal | Key Attributes | Maturity |
|--------|---------------|----------|
| **HTTP Client Spans** | `http.request.method`, `url.full`, `server.address`, `server.port`, `http.response.status_code` | **Stable** |
| **HTTP Server Spans** | `http.request.method`, `http.route`, `url.scheme`, `http.response.status_code` | **Stable** |
| **HTTP Metrics** | `http.server.request.duration`, `http.server.active_requests`, `http.client.request.duration` | **Stable** |

**Relevance to ContextCore**: MEDIUM -- applicable if ContextCore exposes REST APIs or makes HTTP calls to Grafana/backends.

### 1.8 Database Conventions (Stable)

| Signal | Key Attributes | Maturity |
|--------|---------------|----------|
| **DB Spans** | `db.system.name`, `db.collection.name`, `db.operation.name`, `db.query.text`, `db.namespace` | **Stable** |
| **DB Metrics** | `db.client.operation.duration`, `db.client.connection.count` | **Stable** |

**Relevance to ContextCore**: LOW -- unless state persistence moves to a database.

### 1.9 Messaging Conventions (Stable)

| Signal | Key Attributes | Maturity |
|--------|---------------|----------|
| **Messaging Spans** | `messaging.system`, `messaging.destination.name`, `messaging.operation.type`, `messaging.message.id` | **Stable** |
| **Messaging Metrics** | `messaging.client.operation.duration`, `messaging.process.duration`, `messaging.client.published.messages` | **Stable** |

**Relevance to ContextCore**: MEDIUM -- relevant for Rabbit (alert webhook processing) and Coyote (multi-agent pipeline).

### 1.10 Feature Flag Conventions (Experimental)

| Signal | Key Attributes | Maturity |
|--------|---------------|----------|
| **Feature Flag Events** | `feature_flag.key`, `feature_flag.provider_name`, `feature_flag.result.variant`, `feature_flag.result.value` | **Experimental** |
| **Feature Flag Logs** | Same attributes as log record attributes | **Experimental** |

**Relevance to ContextCore**: MEDIUM -- `CONTEXTCORE_EMIT_MODE` (dual/legacy/otel) is a feature flag.

### 1.11 CloudEvents Conventions (Experimental)

| Signal | Key Attributes | Maturity |
|--------|---------------|----------|
| **CloudEvents Spans** | Follow messaging span structure; CloudEvents Distributed Tracing Extension for context propagation | **Experimental** |

**Relevance to ContextCore**: MEDIUM -- applicable to Rabbit/Fox alert webhook processing.

### 1.12 System/Process Metrics (Development)

| Category | Key Metrics | Maturity |
|----------|------------|----------|
| **CPU** | `system.cpu.time`, `system.cpu.utilization` | **Development** |
| **Memory** | `system.memory.usage`, `system.memory.limit` | **Development** |
| **Disk** | `system.disk.io`, `system.disk.operations` | **Development** |
| **Network** | `system.network.io`, `system.network.connections` | **Development** |
| **Process** | `process.cpu.time`, `process.memory.usage`, `process.thread.count` | **Development** |
| **Container** | `container.cpu.time`, `container.memory.usage` | **Development** |

**Relevance to ContextCore**: LOW-MEDIUM -- relevant for monitoring ContextCore's own infrastructure.

### 1.13 FaaS/Serverless Conventions (Development)

| Signal | Key Attributes | Maturity |
|--------|---------------|----------|
| **FaaS Spans** | `faas.trigger`, `faas.invocation_id`, `faas.cold_start` | **Development** |
| **FaaS Resource** | `faas.name`, `faas.version`, `faas.instance` | **Development** |

**Relevance to ContextCore**: LOW -- unless deployed as serverless functions.

### 1.14 RPC Conventions (Stabilizing)

| Signal | Key Attributes | Maturity |
|--------|---------------|----------|
| **RPC Spans** | `rpc.system`, `rpc.service`, `rpc.method` | **Stabilizing** |
| **gRPC Spans** | `rpc.grpc.status_code`, `rpc.grpc.request.metadata.*` | **Stabilizing** |

**Relevance to ContextCore**: MEDIUM -- OTLP uses gRPC; relevant for Collector interactions.

### 1.15 GraphQL, Object Store Conventions

| Convention | Maturity | Relevance |
|-----------|----------|-----------|
| GraphQL spans | **Experimental** | LOW |
| Object store spans (S3, GCS, etc.) | **Experimental** | LOW |

### 1.16 Attribute Naming Rules (Stable)

| Rule | Description |
|------|-------------|
| Namespace separation | Dots as delimiters (`gen_ai.agent.name`) |
| Allowed characters | Lowercase Latin, numeric, underscore, dot |
| Must start with | A letter |
| Must end with | Alphanumeric character |
| No consecutive delimiters | No `..`, `__`, or `._` |
| Reserved prefix | `otel.*` reserved for OpenTelemetry |
| Custom attributes | Prefix with domain or reverse domain (`com.acme.shopname`) |
| Semantic match | Always prefer existing conventions over custom attributes |
| Cardinality | Avoid high-cardinality values in metric attributes and span names |

---

## 2. Specification Standards

### 2.1 OTLP Protocol (v1.9.0)

| Aspect | Details |
|--------|---------|
| **Transport Protocols** | `grpc` (binary protobuf over HTTP/2), `http/protobuf` (binary protobuf over HTTP), `http/json` (JSON over HTTP) |
| **Default Ports** | gRPC: `4317`, HTTP: `4318` |
| **URL Paths (HTTP)** | `/v1/traces`, `/v1/metrics`, `/v1/logs`, `/v1development/profiles` |
| **Recommended Default** | `http/protobuf` (unless backward compat requires gRPC) |
| **Compression** | `none` and `gzip` MUST be supported |
| **Protobuf Maturity** | `common/*`, `resource/*`, `metrics/*`, `trace/*`, `logs/*` all **Stable**; `profiles/*` in **Development** |

### 2.2 Context Propagation

| Standard | Details | Maturity |
|----------|---------|----------|
| **W3C TraceContext** | `traceparent` and `tracestate` headers; default propagator | **Stable** |
| **W3C Baggage** | Key-value metadata propagated alongside context | **Stable** |
| **TextMapPropagator** | API with `Inject` and `Extract` operations | **Stable** |
| **Default Propagator** | Composite: W3C TraceContext + W3C Baggage | **Stable** |
| **Consistent Probability Sampling** | TraceState `rv` (randomness) and `th` (threshold) sub-keys | **Stable** (v1.0 milestone reached) |

### 2.3 Sampling Strategies

| Strategy | Details |
|----------|---------|
| **Head-Based** | Decision at span creation; built-in samplers: `AlwaysOn`, `AlwaysOff`, `ParentBased`, `TraceIdRatioBased` |
| **Tail-Based** | Decision after all spans complete; requires stateful Collector processor |
| **Consistent Probability** | Uses `rv` and `th` TraceState sub-keys for consistent sampling |
| **Hybrid** | Head-based probabilistic + tail-based for all errors |
| **Env Variable** | `OTEL_TRACES_SAMPLER` (default: `parentbased_always_on`), `OTEL_TRACES_SAMPLER_ARG` |

### 2.4 SDK Configuration Environment Variables

| Category | Key Variables |
|----------|--------------|
| **Core** | `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_SDK_DISABLED` |
| **Traces** | `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG`, `OTEL_TRACES_EXPORTER` |
| **Metrics** | `OTEL_METRICS_EXPORTER` |
| **Logs** | `OTEL_LOGS_EXPORTER` |
| **OTLP Exporter** | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_EXPORTER_OTLP_TIMEOUT`, `OTEL_EXPORTER_OTLP_COMPRESSION` |
| **Signal-Specific** | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL`, etc. |
| **Batch Span Processor** | `OTEL_BSP_SCHEDULE_DELAY` (5000ms), `OTEL_BSP_MAX_QUEUE_SIZE` (2048), `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` (512) |
| **Batch Log Processor** | `OTEL_BLRP_SCHEDULE_DELAY`, `OTEL_BLRP_MAX_QUEUE_SIZE`, `OTEL_BLRP_MAX_EXPORT_BATCH_SIZE` |
| **Attribute Limits** | `OTEL_ATTRIBUTE_COUNT_LIMIT` (128), `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` (unlimited), `OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT`, `OTEL_SPAN_EVENT_COUNT_LIMIT`, `OTEL_SPAN_LINK_COUNT_LIMIT` |
| **Declarative Config** | `OTEL_EXPERIMENTAL_CONFIG_FILE` (experimental; YAML-based) |
| **SemConv Migration** | `OTEL_SEMCONV_STABILITY_OPT_IN` (e.g., `http`, `database`, `gen_ai_latest_experimental`) |

### 2.5 Collector Architecture

| Component | Description |
|-----------|-------------|
| **Receivers** | How data enters (OTLP, Prometheus, etc.); minimum one required |
| **Processors** | Transform data: `batch`, `memory_limiter`, `attributes`, `filter`, `tail_sampling` |
| **Exporters** | Where data goes; supports multiple of same type; fan-out |
| **Extensions** | Additional capabilities (health check, pprof, zpages) |
| **Connectors** | Bridge pipelines; exporter for one, receiver for another |
| **Pipelines** | Per signal type: receivers -> processors -> exporters |

### 2.6 Instrumentation Approaches

| Approach | Description |
|----------|-------------|
| **Code-Based (Manual)** | Use OTel API/SDK directly; deeper domain-specific insight |
| **Zero-Code (Automatic)** | Agent-based/monkey-patching; covers library edges |
| **Combined** | Auto-instrumentation as base + manual for domain logic (recommended) |
| **K8s Operator** | Auto-injection via annotations; supports .NET, Java, Node.js, Python, Go |
| **Instrumentation Libraries** | Wrap popular frameworks with OTel instrumentation |
| **Native Instrumentation** | Built directly into libraries and frameworks |

### 2.7 Signal Maturity

| Signal | Maturity | Description |
|--------|----------|-------------|
| **Traces** | **Stable** | Distributed traces composed of spans |
| **Metrics** | **Stable** | Counters, histograms, gauges |
| **Logs** | **Stable** (Bridge API) | Log records; bridge from existing frameworks |
| **Baggage** | **Stable** | Key-value context propagation |
| **Profiles** | **Development** | Continuous profiling; pprof-extended data model |

---

## 3. Best Practices & Guidelines

### 3.1 Span Naming

| Rule | Details |
|------|---------|
| **Pattern** | `{verb} {object}` (e.g., `process payment`, `send invoice`) |
| **Low Cardinality** | Describe operation type, not instance; put IDs in attributes |
| **GenAI Pattern** | `{gen_ai.operation.name} {gen_ai.request.model}` |
| **CI/CD Pattern** | `{action} {pipeline}` |
| **Agent Pattern** | `invoke_agent {gen_ai.agent.name}` |
| **Hierarchical** | `auth.validate_token` for multi-component apps |

### 3.2 Status Code Usage

| Status | When to Use |
|--------|------------|
| **Unset** | Default; operation completed (success assumed) |
| **Error** | An error occurred; description MUST only be used with Error |
| **Ok** | Explicit final assertion of no error; NOT required for success |

### 3.3 Span Kind Selection

| Kind | Use For |
|------|---------|
| `CLIENT` | Outgoing synchronous remote calls |
| `SERVER` | Incoming synchronous remote calls |
| `INTERNAL` | Non-remote, in-process operations (default) |
| `PRODUCER` | Creating asynchronous jobs |
| `CONSUMER` | Processing asynchronous jobs |

### 3.4 Event Best Practices

| Guideline | Details |
|-----------|---------|
| Selective recording | Don't log everything as events |
| Small primitives | No big blobs; short strings and primitives only |
| RecordException | Specialized event for exceptions |
| Timestamp significance | If timestamp matters, use event; if not, use span attribute |

### 3.5 Link Usage

| Use Case | Description |
|----------|-------------|
| Fan-out/Fan-in | Aggregator links to upstream spans |
| Batch processing | Worker links to original trace contexts |
| Message queue hops | New trace per consumer, linked to producer trace |
| Context loss recovery | Link to partial context rather than faking parent |
| Preference | Add links at span creation (enables head sampling decisions) |

### 3.6 Metric Instrument Selection

| Instrument | Use For |
|-----------|---------|
| **Counter** | Monotonically increasing (total requests, errors) |
| **UpDownCounter** | Increases and decreases, additive (queue size, active connections) |
| **Gauge** | Non-additive point-in-time snapshot (CPU%, temperature) |
| **Histogram** | Distribution of values (latency, response size) |

Decision guide:
- Only goes up? --> Counter
- Goes up and down, values are additive? --> UpDownCounter
- Point-in-time snapshot, non-additive? --> Gauge
- Need percentiles or distribution? --> Histogram

---

## 4. Special Interest Groups (SIGs)

### 4.1 SIGs with Critical Relevance to ContextCore

| SIG | Focus | Why It Matters |
|-----|-------|---------------|
| **GenAI SIG** | Generative AI observability (LLM calls, agent spans, sessions) | ContextCore's agent insights, dual-emit strategy, and LLM integration directly map here. Meets Tuesdays 9:00 PT (general) and Mondays 9:00 PT (agents). |
| **Semantic Conventions SIG** | Standardize naming/attributes across all signals | Governs all ContextCore attribute naming (`task.*`, `agent.*`, `gen_ai.*`) |
| **Specification SIG** | Core OTel specification (API, SDK, OTLP) | Defines the foundation ContextCore builds on |
| **SIG Python** | Python SDK implementation | ContextCore's primary language |

### 4.2 SIGs with High Relevance

| SIG | Focus | Why It Matters |
|-----|-------|---------------|
| **CI/CD SIG** | CI/CD pipeline observability | Tasks-as-spans model parallels pipeline/task spans |
| **Collector SIG** | OTel Collector (receivers, processors, exporters) | ContextCore exports via OTLP to Collector |
| **Logging SIG** | Log bridge API, log-to-trace correlation | ContextCore emits structured logs to Loki |

### 4.3 SIGs with Medium Relevance

| SIG | Focus | Why It Matters |
|-----|-------|---------------|
| **Configuration SIG** | Declarative SDK configuration (YAML-based) | ContextCore uses `.contextcore.yaml` for config |
| **End User SIG** | Collect end-user feedback for SIG priorities | ContextCore is an OTel end-user |
| **OpAMP SIG** | Open Agent Management Protocol | Potential for managing ContextCore agents remotely |
| **SIG JavaScript** | JS/TS SDK implementation | VSCode extension is TypeScript |
| **Profiling SIG** | Profiling as 4th OTel signal | Future correlation with task execution spans |
| **Client Instrumentation / RUM SIG** | Client-side instrumentation | VSCode extension context |
| **Demo SIG** | Community demo applications | ContextCore has its own demo generator |

### 4.4 SIGs with Low Relevance

| SIG | Focus |
|-----|-------|
| SIG C++, .NET, Erlang/Elixir, Go, Java, PHP, Ruby, Rust, Swift | Language-specific SDKs not used by ContextCore |
| Mainframe SIG | Mainframe-specific (COBOL, PL/1) |
| Browser SIG | Browser-specific instrumentation |
| SIG Comms / Documentation | OTel website and documentation |

---

## 5. Compliance & Certification Programs

### 5.1 OpenTelemetry Certified Associate (OTCA)

| Aspect | Details |
|--------|---------|
| **Issuer** | CNCF / Linux Foundation Education |
| **Format** | Online, proctored, multiple-choice exam |
| **Domains** | Data Model, Composability, Configuration, Signals, SDK Pipelines, Context Propagation, Agents |
| **Target Audience** | Application Engineers, DevOps, SREs, Platform Engineers |

### 5.2 Specification Compliance Matrix

Located at `spec-compliance-matrix.md` in the `opentelemetry-specification` repo. Shows feature support per language SDK (`+` supported, `-` not supported, `N/A`, blank = unknown).

### 5.3 Compatibility Standards

| Standard | Description |
|----------|-------------|
| OpenCensus migration | Migration path from OpenCensus to OTel |
| OpenTracing shim | Backward compatibility layer |
| Prometheus / OpenMetrics | Bidirectional compatibility; remote write |
| Trace Context in non-OTLP Logs | Embedding trace context in log formats |

### 5.4 Development Lifecycle

| Stage | Description |
|-------|-------------|
| **Draft** | Under design; not yet in specification |
| **Experimental** | Released for beta testing; may change |
| **Stable** | Backward compatible; long-term support |
| **Deprecated** | Still stable but scheduled for removal |
| **Removed** | No longer in specification |

---

# Part 2: ContextCore Compliance Assessment

## 6. What ContextCore Follows

### 6.1 Span Creation & Naming -- COMPLIANT

| Practice | Status | Implementation |
|----------|--------|----------------|
| Dot-separated span names | **Yes** | `contextcore.task.story`, `contextcore.task.epic`, `contextcore.sprint` |
| Low-cardinality span names | **Yes** | IDs in attributes (`task.id`), not span names |
| `{service}:{operation}` pattern | **Yes** | `contextcore.task.<type>` pattern |
| OTel SDK for span creation | **Yes** | `opentelemetry.sdk.trace.TracerProvider`, `opentelemetry.trace.Tracer` |

**Files**: `src/contextcore/tracker.py`

### 6.2 Attribute Naming -- COMPLIANT

| Practice | Status | Implementation |
|----------|--------|----------------|
| Dot notation namespaces | **Yes** | `task.id`, `project.name`, `agent.session_id` |
| Lowercase alphanumeric + dots/underscores | **Yes** | All attributes follow this |
| No consecutive delimiters | **Yes** | No `..` or `__` found |
| High-cardinality values in attributes (not names) | **Yes** | Task IDs, assignees in attributes |

Custom namespaces defined:
- `task.*` (16 attributes): `task.id`, `task.type`, `task.status`, `task.priority`, `task.assignee`, `task.story_points`, `task.labels`, `task.url`, `task.due_date`, `task.blocked_by`, `task.percent_complete`, `task.subtask_count`, `task.subtask_completed`, `task.parent_id`, `task.title`
- `project.*` (2): `project.id`, `project.name`
- `sprint.*` (2): `sprint.id`, `sprint.name`
- `agent.*` (6): `agent.id`, `agent.type`, `agent.session_id`, `agent.version`, `agent.capabilities`, `agent.parent_session_id`
- `insight.*` (9): `insight.id`, `insight.type`, `insight.summary`, `insight.confidence`, `insight.audience`, `insight.rationale`, `insight.evidence`, `insight.supersedes`, `insight.expires_at`
- `handoff.*` (6): `handoff.id`, `handoff.capability_id`, `handoff.inputs`, `handoff.context_id`, `handoff.priority`, `handoff.status`
- `guidance.*` (5): `guidance.id`, `guidance.type`, `guidance.content`, `guidance.active`, `guidance.expires_at`

**Files**: `src/contextcore/tracker.py:64-84`, `src/contextcore/agent/insights.py`, `src/contextcore/compat/otel_genai.py`

### 6.3 Resource Detection -- COMPLIANT

| Standard Attribute | Emitted | Source |
|-------------------|---------|--------|
| `telemetry.sdk.name` | **Yes** (`"opentelemetry"`) | SDK default |
| `telemetry.sdk.language` | **Yes** (`"python"`) | SDK default |
| `telemetry.sdk.version` | **Yes** | SDK version |
| `service.name` | **Yes** (`"contextcore-tracker"`) | Custom detector |
| `service.namespace` | **Yes** (`"contextcore"`) | Custom detector |
| `service.version` | **Yes** | Package version |
| `host.name` | **Yes** | `socket.gethostname()` |
| `host.arch` | **Yes** | `platform.machine()` |
| `os.type` | **Yes** | `platform.system()` |
| `os.version` | **Yes** | `platform.release()` |
| `process.pid` | **Yes** | `os.getpid()` |
| `process.executable.path` | **Yes** | `sys.executable` |
| `process.runtime.name` | **Yes** | Python implementation |
| `process.runtime.version` | **Yes** | Python version |
| `k8s.pod.name` | **Yes** | HOSTNAME env var |
| `k8s.namespace.name` | **Yes** | ServiceAccount mount |
| `deployment.environment.name` | **Yes** | K8s annotations or env vars |

Custom `ProjectContextDetector` implements the `ResourceDetector` interface with timeout handling (3s connect, 5s read) for K8s API calls.

**Files**: `src/contextcore/detector.py`

### 6.4 Status Codes -- COMPLIANT

| Practice | Status | Implementation |
|----------|--------|----------------|
| OTel `StatusCode` enum | **Yes** | `StatusCode.OK`, `StatusCode.ERROR` |
| Error descriptions | **Yes** | `Status(StatusCode.ERROR, "Task blocked")` |
| `record_exception()` | **Yes** | Exception events with `exception.type`, `exception.message`, `exception.stacktrace` |

Task-to-status mapping:
- `todo`, `in_progress` --> `StatusCode.OK`
- `blocked` --> `StatusCode.ERROR` with description
- `done`, `cancelled` --> `StatusCode.OK`

**Files**: `src/contextcore/tracker.py`

### 6.5 Span Events -- COMPLIANT

| Event | Attributes | OTel Compliant |
|-------|-----------|----------------|
| `task.created` | `task.title`, `task.type` | Yes |
| `task.status_changed` | `from`, `to` | Yes |
| `task.blocked` | `reason`, `blocker_id` | Yes |
| `task.unblocked` | -- | Yes |
| `task.completed` | -- | Yes |
| `task.cancelled` | `reason` | Yes |
| `task.assigned` | `from`, `to` | Yes |
| `task.progress_updated` | `percent_complete`, `source` | Yes |
| `task.commented` | `author`, `text` | Yes |
| `sprint.started` | `name` | Yes |
| `sprint.ended` | `notes`, `completed_points` | Yes |

**Files**: `src/contextcore/tracker.py`

### 6.6 Structured Logging -- COMPLIANT

| Convention | Status | Implementation |
|-----------|--------|----------------|
| OTel severity mapping (RFC 5424) | **Yes** | trace=1, debug=5, info=9, warn=13, error=17, fatal=21 |
| `timestamp_unix_nano` | **Yes** | Nanoseconds since epoch |
| `severity_number` | **Yes** | Integer per OTel mapping |
| `severity_text` | **Yes** | Uppercase level |
| `body` | **Yes** | Event name |
| `trace_id` correlation | **Yes** | Hex-formatted from active span context |
| `span_id` correlation | **Yes** | Hex-formatted from active span context |
| Service name in logs | **Yes** | Included in log entry |

**Files**: `src/contextcore/logger.py`

### 6.7 OTLP Export -- COMPLIANT

| Practice | Status | Implementation |
|----------|--------|----------------|
| gRPC transport | **Yes** | `OTLPSpanExporter(endpoint=..., insecure=True)` |
| `BatchSpanProcessor` | **Yes** | Batch processing for traces |
| `PeriodicExportingMetricReader` | **Yes** | 60s interval for metrics |
| `OTEL_EXPORTER_OTLP_ENDPOINT` env var | **Yes** | Defaults to `localhost:4317` |
| Graceful shutdown | **Yes** | Force flush via `atexit` handler (5s timeout) |
| Pre-check endpoint | **Yes** | TCP connection test before configuring exporter |
| Fallback on failure | **Yes** | Console exporter when `CONTEXTCORE_FALLBACK_CONSOLE=1` |

**Files**: `src/contextcore/tracker.py:213-248`, `src/contextcore/metrics.py:170-207`

### 6.8 Metric Instruments -- COMPLIANT

| Metric | Instrument Type | Unit | OTel Correct |
|--------|----------------|------|-------------|
| `task.lead_time` | Histogram | seconds | Yes |
| `task.cycle_time` | Histogram | seconds | Yes |
| `task.blocked_time` | Histogram | seconds | Yes |
| `task.wip` | Observable Gauge | `{tasks}` | Yes |
| `task.throughput` | Counter | `{tasks}` | Yes |
| `task.count_by_status` | Observable Gauge | `{tasks}` | Yes |
| `task.count_by_type` | Observable Gauge | `{tasks}` | Yes |
| `task.story_points_completed` | Counter | `{points}` | Yes |

**Files**: `src/contextcore/metrics.py`, `src/contextcore/contracts/metrics.py`

### 6.9 GenAI Dual-Emit -- COMPLIANT

| Practice | Status | Implementation |
|----------|--------|----------------|
| `gen_ai.agent.id` | **Yes** | Mapped from `agent.id` |
| `gen_ai.agent.name` | **Yes** | Emitted in insights |
| `gen_ai.agent.description` | **Yes** | Emitted in insights |
| `gen_ai.conversation.id` | **Yes** | Mapped from `agent.session_id` |
| `gen_ai.tool.name` | **Yes** | Mapped from `handoff.capability_id` |
| `gen_ai.tool.call.arguments` | **Yes** | Mapped from `handoff.inputs` |
| Dual-emit mode | **Yes** | `CONTEXTCORE_EMIT_MODE` = `dual`, `legacy`, or `otel` |
| Backward compatibility | **Yes** | Both `agent.*` and `gen_ai.*` emitted in `dual` mode |
| Migration guide | **Yes** | `docs/OTEL_GENAI_MIGRATION_GUIDE.md` |

**Files**: `src/contextcore/compat/otel_genai.py`

### 6.10 Span Links for Dependencies -- COMPLIANT

| Practice | Status | Implementation |
|----------|--------|----------------|
| Links for task dependencies | **Yes** | `Link(span_context, attributes={"link.type": "depends_on"})` |
| Links at span creation | **Yes** | Passed via `start_span(..., links=links)` |
| Parent-child via context | **Yes** | `trace.set_span_in_context()` |

**Files**: `src/contextcore/tracker.py:382-389`

---

## 7. What ContextCore Does Not Follow

### 7.1 W3C Baggage -- NOT IMPLEMENTED

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| W3C Baggage propagation | No distributed context metadata across service boundaries | **Medium** |
| `BaggagePropagator` injection/extraction | Cannot pass project context (project ID, criticality) across service calls | **Medium** |

**Recommendation**: Implement Baggage for propagating `project.id` and `business.criticality` across agent boundaries. Security note: Baggage travels in HTTP headers and is visible in network traffic.

### 7.2 Explicit Sampling Configuration -- NOT IMPLEMENTED

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| `OTEL_TRACES_SAMPLER` configuration | Uses implicit full sampling (1.0) | **Medium** |
| No `Sampler` in `TracerProvider` setup | Cannot configure head-based sampling | **Medium** |
| No tail-based sampling config | Cannot selectively keep error traces | **Low** |
| `TraceIdRatioBased` sampler | Cannot reduce volume in production | **High** (at scale) |

**Recommendation**: Add configurable sampling via `OTEL_TRACES_SAMPLER` env var. Default to `parentbased_always_on` for dev, `TraceIdRatioBased` for production.

### 7.3 W3C TraceContext Extraction -- PARTIAL

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| Incoming `traceparent` header extraction | Cannot correlate with upstream services | **Medium** |
| `tracestate` handling | Cannot participate in distributed sampling | **Low** |

**Current state**: Log-to-trace correlation works (logs include `trace_id` and `span_id`), but incoming HTTP requests don't extract trace context. Only outbound OTLP includes context.

**Recommendation**: If ContextCore exposes any HTTP endpoints (API, webhook receivers), add `TraceContextTextMapPropagator` extraction.

### 7.4 GenAI Client Span Attributes -- PARTIAL

| Missing Attribute | Description | Priority |
|------------------|-------------|----------|
| `gen_ai.operation.name` | Operation type (`chat`, `invoke_agent`, etc.) | **High** |
| `gen_ai.system` | Provider system (`anthropic`, `openai`) | **High** |
| `gen_ai.request.model` | Model requested | **High** |
| `gen_ai.response.model` | Model actually used | **Medium** |
| `gen_ai.request.temperature` | Sampling temperature | **Low** |
| `gen_ai.request.max_tokens` | Maximum tokens requested | **Medium** |
| `gen_ai.response.finish_reasons` | Why generation stopped | **Medium** |

**Current state**: Agent identity attributes are mapped (`gen_ai.agent.id`, `gen_ai.agent.name`, `gen_ai.conversation.id`), but LLM request/response attributes are not emitted on task spans or insight spans.

**Recommendation**: When Beaver (LLM abstraction) is invoked, emit `gen_ai.system`, `gen_ai.request.model`, and `gen_ai.client.token.usage` on the corresponding spans.

### 7.5 GenAI Metrics -- NOT IMPLEMENTED

| Missing Metric | Description | Priority |
|---------------|-------------|----------|
| `gen_ai.client.token.usage` | Token usage histogram (input/output) | **High** |
| `gen_ai.server.request.duration` | LLM request duration | **Medium** |
| `gen_ai.server.time_per_output_token` | Decode phase latency | **Low** |
| `gen_ai.server.time_to_first_token` | Prefill + queue time | **Medium** |

**Recommendation**: Track token usage in Beaver (LLM abstraction layer) and emit as `gen_ai.client.token.usage` histogram with recommended bucket boundaries `[1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]`.

### 7.6 GenAI Events -- NOT IMPLEMENTED

| Missing Event | Description | Priority |
|--------------|-------------|----------|
| Input chat message events | Log user/system prompts on spans | **Medium** |
| Output chat message events | Log generated responses on spans | **Medium** |
| Evaluation events | Quality/safety evaluation results | **Low** |

**Recommendation**: Emit GenAI events on agent insight spans when `CONTEXTCORE_EMIT_MODE` is `otel` or `dual`.

### 7.7 GenAI Span Name Format -- NOT FOLLOWED

| Convention | Expected | Actual |
|-----------|----------|--------|
| GenAI span name | `{gen_ai.operation.name} {gen_ai.request.model}` | `insight.emit`, `handoff.create` |
| Agent span name | `invoke_agent {gen_ai.agent.name}` | Not using this pattern |

**Recommendation**: For spans that involve LLM operations, adopt the OTel GenAI span name format.

### 7.8 GenAI Span Kind -- NOT FOLLOWED

| Convention | Expected | Actual |
|-----------|----------|--------|
| Remote agent invocation | `CLIENT` | `INTERNAL` (default) |
| In-process agent operation | `INTERNAL` | `INTERNAL` (correct by accident) |

**Recommendation**: Set span kind to `CLIENT` when invoking remote agents/LLMs.

### 7.9 CI/CD Convention Alignment -- NOT ADOPTED

ContextCore's task-as-span model structurally parallels CI/CD conventions but uses different attribute names.

| CI/CD Convention | ContextCore Equivalent | Gap |
|-----------------|----------------------|-----|
| `cicd.pipeline.name` | `project.name` | Different namespace |
| `cicd.pipeline.run.id` | `sprint.id` | Different namespace |
| `cicd.pipeline.task.name` | `task.title` | Different namespace |
| `cicd.pipeline.task.run.id` | `task.id` | Different namespace |
| `cicd.pipeline.task.type` | `task.type` | Different namespace |
| Pipeline run span kind: `SERVER` | N/A | Not set |
| Task span kind: `INTERNAL` | Default | Correct by default |

**Recommendation**: Consider dual-emitting CI/CD attributes alongside `task.*` attributes, similar to the GenAI dual-emit strategy. This would allow CI/CD-aware tools to query ContextCore spans.

### 7.10 `service.instance.id` -- NOT SET

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| `service.instance.id` resource attribute | Cannot distinguish between multiple instances of the same service | **Low** |

**Recommendation**: Set to a UUID or pod name to distinguish instances.

### 7.11 `OTEL_SEMCONV_STABILITY_OPT_IN` -- NOT USED

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| `OTEL_SEMCONV_STABILITY_OPT_IN` env var | ContextCore uses custom `CONTEXTCORE_EMIT_MODE` instead of the standard mechanism | **Low** |

**Recommendation**: For GenAI conventions, support `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` in addition to `CONTEXTCORE_EMIT_MODE`.

### 7.12 Feature Flag Telemetry -- NOT IMPLEMENTED

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| Feature flag events for `CONTEXTCORE_EMIT_MODE` | Mode changes not tracked as telemetry events | **Low** |
| `feature_flag.key`, `feature_flag.result.variant` | Missing standardized feature flag recording | **Low** |

**Recommendation**: Emit feature flag evaluation events when `CONTEXTCORE_EMIT_MODE` is read.

### 7.13 HTTP/gRPC Transport Options -- PARTIAL

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| `http/protobuf` transport option | Only gRPC implemented; `http/protobuf` is the OTel recommended default | **Low** |
| `OTEL_EXPORTER_OTLP_PROTOCOL` env var | Cannot switch transport via standard config | **Medium** |
| `http/json` transport option | No human-readable transport for debugging | **Low** |

**Current state**: Only gRPC (`OTLPSpanExporter` from `opentelemetry.exporter.otlp.proto.grpc`) is used.

**Recommendation**: Support `OTEL_EXPORTER_OTLP_PROTOCOL` to allow switching between `grpc` and `http/protobuf`.

### 7.14 Batch Processor Configuration -- NOT CONFIGURABLE

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| `OTEL_BSP_SCHEDULE_DELAY` support | Cannot tune batch delay | **Low** |
| `OTEL_BSP_MAX_QUEUE_SIZE` support | Cannot tune queue size | **Low** |
| `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` support | Cannot tune batch size | **Low** |

**Current state**: Uses `BatchSpanProcessor` with defaults. The OTel Python SDK may respect these env vars automatically, but ContextCore doesn't document or explicitly configure them.

**Recommendation**: Document support for standard batch processor env vars.

### 7.15 Attribute Limits -- NOT CONFIGURED

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| `OTEL_ATTRIBUTE_COUNT_LIMIT` | No explicit limit on span attributes | **Low** |
| `OTEL_SPAN_EVENT_COUNT_LIMIT` | No limit on events per span | **Low** |
| `OTEL_SPAN_LINK_COUNT_LIMIT` | No limit on links per span | **Low** |

**Recommendation**: For long-running task spans with many status changes, consider configuring event count limits.

### 7.16 Messaging Conventions for Rabbit/Fox -- NOT IMPLEMENTED

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| `messaging.system` | Alert webhook system not identified | **Medium** (for Rabbit) |
| `messaging.destination.name` | Alert destination not tracked | **Medium** (for Rabbit) |
| `messaging.operation.type` | Webhook processing type not set | **Medium** (for Rabbit) |

**Recommendation**: When implementing Rabbit/Fox alert processing, adopt messaging semantic conventions for webhook handling.

### 7.17 Declarative SDK Configuration -- NOT IMPLEMENTED

| What's Missing | Impact | Priority |
|---------------|--------|----------|
| `OTEL_EXPERIMENTAL_CONFIG_FILE` support | Cannot configure SDK via YAML | **Low** |

**Note**: This is still experimental in OTel. Low priority but worth watching.

### 7.18 Custom Attribute Domain Prefix -- NOT FOLLOWED

| Convention | Expected | Actual |
|-----------|----------|--------|
| Custom attribute prefix | `io.contextcore.task.id` or `contextcore.task.id` | `task.id` |

**Recommendation**: OTel recommends prefixing custom attributes with a domain to avoid collisions. Consider `contextcore.task.id` instead of `task.id`. However, since `task.*` is unlikely to collide with any OTel semantic convention, this is low risk. The current naming is actually cleaner. If a `task.*` namespace ever enters OTel semconv, a migration path would be needed.

---

## 8. Compliance Summary Matrix

| Category | Status | Details |
|----------|--------|---------|
| **Span Creation** | FULL | OTel SDK, proper naming |
| **Attribute Naming** | FULL | Dot notation, namespaced, low-cardinality in names |
| **Resource Detection** | FULL | `ProjectContextDetector`, standard + custom attributes |
| **Status Codes** | FULL | `StatusCode` enum, exception recording |
| **Span Events** | FULL | Task lifecycle events with attributes |
| **Structured Logging** | FULL | JSON output, OTel severity mapping, trace correlation |
| **OTLP Export** | FULL | gRPC, BatchProcessor, PeriodicReader, graceful shutdown |
| **Metric Instruments** | FULL | Histograms, Gauges, Counters with correct types/units |
| **GenAI Agent Identity** | FULL | `gen_ai.agent.id/name/description`, `gen_ai.conversation.id` |
| **GenAI Dual-Emit** | FULL | Legacy + OTel attributes, configurable mode |
| **Span Links** | FULL | Task dependency links at span creation |
| **Exception Conventions** | FULL | `record_exception()` with standard attributes |
| **GenAI Client Spans** | PARTIAL | Missing `gen_ai.operation.name`, `gen_ai.system`, `gen_ai.request.model` |
| **GenAI Span Naming** | PARTIAL | Not using `{operation} {model}` format for LLM spans |
| **GenAI Span Kind** | PARTIAL | Remote agent calls not set to `CLIENT` |
| **Context Propagation** | PARTIAL | Log correlation works; no incoming TraceContext extraction |
| **OTLP Transport Config** | PARTIAL | gRPC only; no `OTEL_EXPORTER_OTLP_PROTOCOL` support |
| **GenAI Metrics** | NONE | No `gen_ai.client.token.usage` or server metrics |
| **GenAI Events** | NONE | No input/output chat message events |
| **W3C Baggage** | NONE | Not implemented |
| **Sampling Configuration** | NONE | Implicit full sampling, not configurable |
| **CI/CD Convention Alignment** | NONE | Structural parallel exists but different attribute names |
| **Feature Flag Telemetry** | NONE | Emit mode changes not tracked as OTel events |
| **Messaging Conventions** | NONE | Rabbit/Fox don't use messaging semconv |

---

## 9. Recommended Adoption Roadmap

### Phase 1: High-Value, Low-Effort Gaps

These can be adopted with minimal code changes and high standards compliance benefit.

1. **Add `gen_ai.operation.name` and `gen_ai.system`** to agent insight/handoff spans
2. **Add `gen_ai.request.model`** when Beaver invokes LLM providers
3. **Set span kind to `CLIENT`** for remote agent/LLM invocations
4. **Support `OTEL_EXPORTER_OTLP_PROTOCOL`** env var for transport selection
5. **Add `service.instance.id`** to resource attributes

### Phase 2: GenAI Metrics & Events

These require more implementation effort but bring ContextCore into full GenAI convention compliance.

6. **Implement `gen_ai.client.token.usage` histogram** in Beaver
7. **Implement `gen_ai.server.time_to_first_token`** for streaming responses
8. **Emit GenAI input/output events** on agent spans
9. **Adopt GenAI span name format** (`{operation} {model}`) for LLM spans

### Phase 3: Context Propagation & Sampling

These improve ContextCore's behavior in distributed environments.

10. **Implement W3C Baggage** for propagating project context
11. **Add configurable sampling** via `OTEL_TRACES_SAMPLER`
12. **Extract incoming W3C TraceContext** on HTTP endpoints
13. **Support `OTEL_SEMCONV_STABILITY_OPT_IN`** for standard migration control

### Phase 4: Extended Convention Alignment

These are lower priority but improve ecosystem interoperability.

14. **CI/CD dual-emit** -- emit `cicd.pipeline.task.*` alongside `task.*`
15. **Feature flag events** -- track `CONTEXTCORE_EMIT_MODE` changes
16. **Messaging conventions** -- adopt for Rabbit/Fox alert processing
17. **Attribute limits** -- configure for long-running task spans
18. **Document batch processor env vars** -- ensure standard config works

---

## References

### Official OTel Specifications
- [OpenTelemetry Specification v1.53.0](https://opentelemetry.io/docs/specs/otel/)
- [OTLP Specification v1.9.0](https://opentelemetry.io/docs/specs/otlp/)
- [Semantic Conventions v1.39.0](https://opentelemetry.io/docs/specs/semconv/)

### GenAI Conventions
- [GenAI Overview](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [GenAI Client Spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/)
- [GenAI Agent Spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)
- [GenAI Metrics](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/)
- [GenAI Events](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-events/)
- [OpenAI Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/openai/)

### CI/CD Conventions
- [CI/CD Spans](https://opentelemetry.io/docs/specs/semconv/cicd/cicd-spans/)
- [CI/CD Metrics](https://opentelemetry.io/docs/specs/semconv/cicd/cicd-metrics/)
- [CI/CD Logs](https://opentelemetry.io/docs/specs/semconv/cicd/cicd-logs/)

### Other Conventions
- [Resource Conventions](https://opentelemetry.io/docs/specs/semconv/resource/)
- [Exception Conventions](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/)
- [Error Recording](https://opentelemetry.io/docs/specs/semconv/general/recording-errors/)
- [Attribute Naming](https://opentelemetry.io/docs/specs/semconv/general/naming/)
- [Messaging Conventions](https://opentelemetry.io/docs/specs/semconv/messaging/)
- [Feature Flag Conventions](https://opentelemetry.io/docs/specs/semconv/feature-flags/feature-flags-events/)

### Best Practices
- [How to Name Your Spans](https://opentelemetry.io/blog/2025/how-to-name-your-spans/)
- [How to Name Your Span Attributes](https://opentelemetry.io/blog/2025/how-to-name-your-span-attributes/)
- [Sampling](https://opentelemetry.io/docs/concepts/sampling/)
- [Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [SDK Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/)

### Community
- [OpenTelemetry SIGs](https://opentelemetry.io/community/)
- [Semantic Conventions GitHub](https://github.com/open-telemetry/semantic-conventions)
- [Specification Compliance Matrix](https://github.com/open-telemetry/opentelemetry-specification/blob/main/spec-compliance-matrix.md)
- [OTCA Certification](https://training.linuxfoundation.org/certification/opentelemetry-certified-associate-otca/)

### ContextCore Documentation
- [ContextCore Semantic Conventions](docs/semantic-conventions.md)
- [Agent Semantic Conventions](docs/agent-semantic-conventions.md)
- [OTel GenAI Migration Guide](docs/OTEL_GENAI_MIGRATION_GUIDE.md)
- [OTel GenAI Gap Analysis](docs/OTEL_GENAI_GAP_ANALYSIS.md)
