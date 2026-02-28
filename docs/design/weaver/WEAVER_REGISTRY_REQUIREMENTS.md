# OTel Weaver Registry Requirements

**Plan:** `WEAVER_CROSS_REPO_ALIGNMENT_PLAN.fixed.md`
**Supersedes:** `docs/plans/tranquil-baking-swing.md` (original plan, ~185 attrs — now outdated)
**Date:** 2026-02-28
**Status:** Phase 1 not started; enums and contract domains updated 2026-02-28
**Weaver target version:** v0.21.2+ (V2 schema support)

---

## 1. Problem Statement

ContextCore defines ~250+ semantic convention attributes across 24+ namespaces, maintained in three divergent sources:

| Source | Path | Role | Known Drift |
|--------|------|------|-------------|
| Markdown prose | `docs/semantic-conventions.md` (1920 lines) | Human documentation | Lists 9 `HandoffStatus` values |
| Python enums | `src/contextcore/contracts/types.py` (27 enums) | Canonical source of truth | Defines 6 `HandoffStatus` members |
| Python contracts | `src/contextcore/contracts/metrics.py` | Metric/label/event names | Some deprecated labels still referenced |
| Dual-emit mappings | `src/contextcore/compat/otel_genai.py` | `agent.*` -> `gen_ai.*` | Multiple `ATTRIBUTE_MAPPINGS` dicts |
| Contract domains | `src/contextcore/contracts/propagation/`, `contracts/schema_compat/`, etc. | 7 contract domain layers (Layers 1–7) | 12 new enums not yet in registry plan |

There is no machine-readable schema and no automated validation that emitted OTLP conforms to declared conventions.

**Note:** The `RequirementLevel` enum now formally defines `opt_in` semantics (see Section 3.21), addressing reviewer feedback from R2-S7, R3-F7, and R1-F8.

---

## 2. Goal

Formalize ContextCore's semantic conventions as an [OTel Weaver](https://github.com/open-telemetry/weaver)-compatible registry that provides:

1. **Single source of truth** — one schema for attributes, spans, events, and metrics
2. **Automated validation** — CI runs `weaver registry check` on every PR
3. **Drift detection** — Python enum values cross-checked against registry YAML
4. **Deprecation tracking** — machine-readable `deprecated:` fields for `agent.*` -> `gen_ai.*` migration
5. **Doc generation** (Phase 3) — replace hand-maintained `semantic-conventions.md`

---

## 2.5 Weaver Upstream Status

The registry targets **OTel Weaver v0.21.2+** and adopts the following format decisions based on upstream evolution from v0.15 through v0.21.2:

### Format Decisions

| Decision | Value | Rationale |
|----------|-------|-----------|
| Schema format | V2 (`file_format: definition/2`) | V2 supports `attribute_group` with public/internal visibility (v0.19+) |
| Manifest file | `manifest.yaml` | New default name (was `registry_manifest.yaml`) |
| Manifest field | `schema_url` | Replaces `registry_url` in newer Weaver versions |
| OTel semconv import | `imports:` section referencing `gen_ai.*` | v0.15.3 `imports` section avoids redefining upstream attributes |
| Registry dependency | `contextcore-semconv` → `otel-semconv` (v1.34.0) | v0.17.0 dependency chains (max depth 10) |
| Deprecation format | Structured: `deprecated.since`, `deprecated.note`, `deprecated.renamed_to` | v0.19.0 structured deprecation on enum members |

### Deprecated / Changed Weaver Features

| Feature | Status | Replacement |
|---------|--------|-------------|
| `weaver registry search` | Deprecated (v0.20.0) | Use generated docs or `weaver registry resolve` |
| `Violation` / `Advice` | Renamed (v0.20.0) | Now `PolicyFinding` — update CI workflow config |
| `registry_manifest.yaml` | Deprecated (unreleased) | Use `manifest.yaml` |
| `registry_url` field | Deprecated (unreleased) | Use `schema_url` |
| `version: '2'` format | Deprecated (unreleased) | Use `file_format: definition/2` |

### New Weaver Capabilities

| Feature | Version | Relevance |
|---------|---------|-----------|
| `weaver registry mcp` | v0.21.2 | MCP server for registry — enables agent-facing discovery of ContextCore attributes |
| `weaver serve` | v0.21.2 | REST API + web UI for registry queries |
| `weaver registry infer` | Unreleased | Infer registry from live OTLP — could auto-validate emitted telemetry against registry |
| `weaver registry live-check` | v0.20.0 | Validates emitted OTLP against registry in real-time |
| `weaver registry diff` | v0.20.0 | Compare current vs tagged release with V2 support |

---

## 3. Canonical Enums (Source of Truth)

The registry YAML **must** exactly match these Python enums from `contracts/types.py`:

### 3.1 TaskStatus (7 members)
```
backlog, todo, in_progress, in_review, blocked, done, cancelled
```

### 3.2 TaskType (7 members)
```
epic, story, task, subtask, bug, spike, incident
```

### 3.3 Priority (4 members)
```
critical, high, medium, low
```

### 3.4 HandoffStatus (6 members)
```
pending, accepted, in_progress, completed, failed, timeout
```

### 3.5 SessionStatus (3 members)
```
active, completed, abandoned
```

### 3.6 InsightType (4 members)
```
decision, recommendation, blocker, discovery
```

### 3.7 AgentType (4 members)
```
code_assistant, orchestrator, specialist, automation
```

### 3.8 BusinessValue (6 members)
```
revenue-primary, revenue-secondary, cost-reduction, compliance, enabler, internal
```

### 3.9 RiskType (6 members)
```
security, compliance, data-integrity, availability, financial, reputational
```

### 3.10 Criticality (4 members)
```
critical, high, medium, low
```

### 3.11 AlertPriority (4 members) — Cross-cutting
```
P1, P2, P3, P4
```
Maps to/from `Priority` via `Priority.from_alert_priority()` / `Priority.to_alert_priority()`.

### 3.12 DashboardPlacement (3 members) — Cross-cutting
```
featured, standard, archived
```

### 3.13 LogLevel (4 members) — Cross-cutting
```
debug, info, warn, error
```

### 3.14 ConstraintSeverity (3 members) — Cross-cutting
```
blocking, warning, advisory
```

### 3.15 QuestionStatus (3 members) — Cross-cutting
```
open, answered, deferred
```

### 3.16 PropagationStatus (4 members) — Layer 1
```
propagated, defaulted, partial, failed
```
Context propagation status at a workflow boundary.

### 3.17 ChainStatus (3 members) — Layer 1
```
intact, degraded, broken
```
End-to-end propagation chain status. `intact` = all waypoints + destination present, verification passes. `degraded` = source present but destination has default value. `broken` = source absent or verification fails.

### 3.18 CompatibilityLevel (3 members) — Layer 2
```
structural, semantic, behavioral
```
Schema compatibility check level.

### 3.19 EnforcementMode (3 members) — Layer 4
```
strict, permissive, audit
```
Runtime boundary enforcement mode. `strict` = blocking failures raise exception. `permissive` = failures logged but phase continues. `audit` = everything logged via OTel, nothing blocks.

### 3.20 EvaluationPolicy (4 members) — Layer 1
```
score_threshold, human_or_model, human_required, any_evaluator
```
Policy for evaluation-gated fields (REQ_CONCERN_13).

### 3.21 RequirementLevel (3 members) — Layer 3
```
required, recommended, opt_in
```
Requirement level for semantic conventions. `required` = attribute must be present. `recommended` = attribute should be present but absence is tolerated. `opt_in` = attribute is entirely optional; producers MAY emit, consumers MUST NOT require presence. This enum formally defines the `opt_in` semantics requested by reviewers (R2-S7, R3-F7, R1-F8).

### 3.22 CapabilityChainStatus (4 members) — Layer 5
```
intact, attenuated, escalation_blocked, broken
```
End-to-end capability propagation status. `attenuated` = capability was narrowed (valid). `escalation_blocked` = attempted escalation was blocked.

### 3.23 BudgetType (5 members) — Layer 6
```
latency_ms, cost_dollars, token_count, error_rate, custom
```

### 3.24 OverflowPolicy (3 members) — Layer 6
```
warn, block, redistribute
```
Policy when budget allocation is exceeded. `redistribute` = redistribute remaining budget from under-budget phases.

### 3.25 BudgetHealth (3 members) — Layer 6
```
within_budget, over_allocation, budget_exhausted
```

### 3.26 TransformOp (6 members) — Layer 7
```
passthrough, classify, transform, derive, aggregate, filter
```
Transformation operation type for data lineage tracking.

### 3.27 LineageStatus (4 members) — Layer 7
```
verified, mutation_detected, chain_broken, incomplete
```
Data lineage chain verification status. `mutation_detected` = unexpected hash change in a passthrough stage. `incomplete` = lineage exists but doesn't cover all declared stages.

---

## 4. Attribute Groups

### 4.1 task.* (17 attributes) — Phase 1

| Attribute | Type | Enum | Req Level | Source |
|-----------|------|------|-----------|--------|
| `task.id` | string | — | required | `LabelName.TASK_ID` |
| `task.type` | string | TaskType (7) | recommended | `LabelName.TASK_TYPE` |
| `task.status` | string | TaskStatus (7) | required | `LabelName.TASK_STATUS` |
| `task.priority` | string | Priority (4) | recommended | `LabelName.TASK_PRIORITY` |
| `task.assignee` | string | — | opt_in | `LabelName.TASK_ASSIGNEE` |
| `task.title` | string | — | opt_in | `LabelName.TASK_TITLE` |
| `task.story_points` | int | — | opt_in | `LabelName.TASK_STORY_POINTS` |
| `task.labels` | string[] | — | opt_in | — |
| `task.url` | string | — | opt_in | — |
| `task.due_date` | string | — | opt_in | — |
| `task.blocked_by` | string[] | — | opt_in | — |
| `task.parent_id` | string | — | recommended | `LabelName.TASK_PARENT_ID` |
| `task.percent_complete` | double | — | recommended | `LabelName.TASK_PERCENT_COMPLETE` |
| `task.subtask_count` | int | — | opt_in | — |
| `task.subtask_completed` | int | — | opt_in | — |
| `task.deliverable.count` | int | — | opt_in | — |
| `task.deliverable.verified` | int | — | opt_in | — |

### 4.2 project.* (5 attributes) — Phase 1

| Attribute | Type | Req Level | Source |
|-----------|------|-----------|--------|
| `project.id` | string | required | `LabelName.PROJECT_ID` |
| `project.name` | string | recommended | `LabelName.PROJECT` |
| `project.epic` | string | opt_in | `LabelName.EPIC` |
| `project.task` | string | opt_in | — |
| `project.trace_id` | string | opt_in | — |

### 4.3 sprint.* (7 attributes) — Phase 1

| Attribute | Type | Req Level | Source |
|-----------|------|-----------|--------|
| `sprint.id` | string | required | `LabelName.SPRINT_ID` |
| `sprint.name` | string | recommended | — |
| `sprint.goal` | string | opt_in | — |
| `sprint.start_date` | string | recommended | — |
| `sprint.end_date` | string | recommended | — |
| `sprint.planned_points` | int | opt_in | — |
| `sprint.completed_points` | int | opt_in | — |

### 4.4 agent.* (6 attributes, all deprecated) — Phase 1

| Attribute | Type | Deprecated → | Source |
|-----------|------|-------------|--------|
| `agent.id` | string | `gen_ai.agent.id` | `ATTRIBUTE_MAPPINGS` |
| `agent.type` | string | `gen_ai.agent.type` | `ATTRIBUTE_MAPPINGS` |
| `agent.session_id` | string | `gen_ai.conversation.id` | `ATTRIBUTE_MAPPINGS` |
| `agent.model` | string | `gen_ai.request.model` | — |
| `agent.name` | string | `gen_ai.agent.name` | — |
| `agent.version` | string | `gen_ai.agent.version` | — |

### 4.5 business.*, design.*, requirement.*, risk.* (16 attributes) — Phase 2

Source: `docs/semantic-conventions.md` sections on business context. Enum source: `BusinessValue`, `RiskType`, `Criticality`.

### 4.6 insight.*, evidence.* (15 attributes) — Phase 2

Enum source: `InsightType` (4 members). Source: `docs/agent-semantic-conventions.md`.

### 4.7 handoff.* (10 attributes) — Phase 2

Enum source: `HandoffStatus` (6 members). Dual-emit mappings in `otel_genai.py`:
- `handoff.capability_id` -> `gen_ai.tool.name`
- `handoff.inputs` -> `gen_ai.tool.call.arguments`
- `handoff.id` -> `gen_ai.tool.call.id`

### 4.8 guidance.* (7 attributes) — Phase 2

Source: `docs/semantic-conventions.md` guidance section.

### 4.9 contextcore.install.* (12 attributes) — Phase 2

Source: install verification span hierarchy.

### 4.10 gen_ai.code.* (16 attributes) — Phase 2

ContextCore extensions to the gen_ai namespace for code generation telemetry.

### 4.11 propagation.* (Layer 1) — Phase 2

Context propagation status attributes for workflow boundary tracking.

| Attribute | Type | Enum | Req Level | Source |
|-----------|------|------|-----------|--------|
| `propagation.status` | string | PropagationStatus (4) | required | `contracts/types.py` |
| `propagation.chain_status` | string | ChainStatus (3) | required | `contracts/types.py` |
| `propagation.field_count` | int | — | recommended | Propagation validator |
| `propagation.defaulted_count` | int | — | recommended | Propagation validator |
| `propagation.quality_metric` | double | — | recommended | Quality evaluator |
| `propagation.quality_threshold` | double | — | opt_in | Quality evaluator |

### 4.12 schema_compat.* (Layer 2) — Phase 2

Schema compatibility check attributes.

| Attribute | Type | Enum | Req Level | Source |
|-----------|------|------|-----------|--------|
| `schema_compat.level` | string | CompatibilityLevel (3) | required | `contracts/types.py` |
| `schema_compat.source_version` | string | — | recommended | Schema compat checker |
| `schema_compat.target_version` | string | — | recommended | Schema compat checker |

### 4.13 semconv.* (Layer 3) — Phase 2

Semantic convention enforcement attributes.

| Attribute | Type | Enum | Req Level | Source |
|-----------|------|------|-----------|--------|
| `semconv.requirement_level` | string | RequirementLevel (3) | required | `contracts/types.py` |
| `semconv.attribute_count` | int | — | recommended | Semconv validator |
| `semconv.violations` | int | — | recommended | Semconv validator |

### 4.14 boundary.* (Layer 4) — Phase 2

Runtime boundary enforcement attributes.

| Attribute | Type | Enum | Req Level | Source |
|-----------|------|------|-----------|--------|
| `boundary.enforcement_mode` | string | EnforcementMode (3) | required | `contracts/types.py` |
| `boundary.violations_count` | int | — | recommended | RuntimeBoundaryGuard |
| `boundary.phase` | string | — | recommended | Phase identifier |

### 4.15 capability.* (Layer 5) — Phase 2

Capability propagation chain attributes.

| Attribute | Type | Enum | Req Level | Source |
|-----------|------|------|-----------|--------|
| `capability.chain_status` | string | CapabilityChainStatus (4) | required | `contracts/types.py` |
| `capability.attenuations` | int | — | recommended | Capability validator |
| `capability.escalation_attempts` | int | — | opt_in | Capability validator |

### 4.16 budget.* (Layer 6) — Phase 2

SLO budget allocation and tracking attributes.

| Attribute | Type | Enum | Req Level | Source |
|-----------|------|------|-----------|--------|
| `budget.type` | string | BudgetType (5) | required | `contracts/types.py` |
| `budget.allocated` | double | — | required | Budget allocator |
| `budget.consumed` | double | — | required | Budget tracker |
| `budget.remaining` | double | — | recommended | Derived |
| `budget.health` | string | BudgetHealth (3) | required | `contracts/types.py` |
| `budget.overflow_policy` | string | OverflowPolicy (3) | recommended | `contracts/types.py` |

### 4.17 lineage.* (Layer 7) — Phase 2

Data lineage tracking attributes.

| Attribute | Type | Enum | Req Level | Source |
|-----------|------|------|-----------|--------|
| `lineage.status` | string | LineageStatus (4) | required | `contracts/types.py` |
| `lineage.transform_op` | string | TransformOp (6) | required | `contracts/types.py` |
| `lineage.stage_count` | int | — | recommended | Lineage tracker |
| `lineage.verified_stages` | int | — | recommended | Lineage verifier |

### 4.18 feature_flag.* (referenced) — Phase 2

OTel Feature Flag semantic convention attributes. Used for ContextCore configuration flag evaluation events.

| Attribute | Type | Req Level | Source |
|-----------|------|-----------|--------|
| `feature_flag.key` | string | required | `FeatureFlagAttribute.KEY` |
| `feature_flag.provider_name` | string | recommended | `FeatureFlagAttribute.PROVIDER_NAME` |
| `feature_flag.result.variant` | string | opt_in | `FeatureFlagAttribute.RESULT_VARIANT` |
| `feature_flag.result.value` | string | opt_in | `FeatureFlagAttribute.RESULT_VALUE` |

### 4.19 messaging.* (referenced) — Phase 2

OTel Messaging semantic convention attributes. Used for Rabbit/Fox alert webhook processing spans.

| Attribute | Type | Req Level | Source |
|-----------|------|-----------|--------|
| `messaging.system` | string | required | `MessagingAttribute.SYSTEM` |
| `messaging.destination.name` | string | required | `MessagingAttribute.DESTINATION_NAME` |
| `messaging.operation.type` | string | recommended | `MessagingAttribute.OPERATION_TYPE` |
| `messaging.message.id` | string | opt_in | `MessagingAttribute.MESSAGE_ID` |
| `messaging.message.body.size` | int | opt_in | `MessagingAttribute.MESSAGE_BODY_SIZE` |

### 4.20 cicd.pipeline.* (referenced) — Phase 2

OTel CI/CD pipeline attributes. Maps from ContextCore task attributes to CI/CD conventions.

| Attribute | Type | Req Level | Source |
|-----------|------|-----------|--------|
| `cicd.pipeline.name` | string | required | `CicdLabelName.PIPELINE_NAME` |
| `cicd.pipeline.run.id` | string | required | `CicdLabelName.PIPELINE_RUN_ID` |
| `cicd.pipeline.task.name` | string | recommended | `CicdLabelName.PIPELINE_TASK_NAME` |
| `cicd.pipeline.task.run.id` | string | opt_in | `CicdLabelName.PIPELINE_TASK_RUN_ID` |
| `cicd.pipeline.task.type` | string | opt_in | `CicdLabelName.PIPELINE_TASK_TYPE` |

---

## 5. Spans

### 5.1 contextcore.task (Phase 1)

| Field | Value |
|-------|-------|
| span_kind | internal |
| Required attributes | `task.id`, `task.status`, `project.id` |
| Recommended attributes | `task.type`, `task.priority`, `task.parent_id` |

### 5.2 contextcore.sprint (Phase 2)

| Field | Value |
|-------|-------|
| span_kind | internal |
| Required attributes | `sprint.id`, `project.id` |

### 5.3 contextcore.install.verify (Phase 2)

Span hierarchy for install verification.

### 5.4 handoff lifecycle spans (Phase 2)

Spans for handoff creation, acceptance, and completion.

---

## 6. Events

### 6.1 Task Events (Phase 1)

Source: `EventType` enum in `contracts/metrics.py`.

| Event Name | Body Attributes |
|------------|-----------------|
| `task.created` | task.id, task.type, project.id |
| `task.status_changed` | task.id, task.status (old + new) |
| `task.blocked` | task.id, task.blocked_by |
| `task.unblocked` | task.id |
| `task.completed` | task.id |
| `task.cancelled` | task.id |
| `task.assigned` | task.id, task.assignee |
| `task.commented` | task.id |
| `task.progress_updated` | task.id, task.percent_complete |
| `subtask.completed` | task.id, task.parent_id |

### 6.2 Sprint Events (Phase 2)

| Event Name | Body Attributes |
|------------|-----------------|
| `sprint.started` | sprint.id, project.id |
| `sprint.ended` | sprint.id, sprint.completed_points |

### 6.3 Agent Events (Phase 2)

| Event Name | Body Attributes |
|------------|-----------------|
| `agent.session_started` | gen_ai.agent.id, gen_ai.conversation.id |
| `agent.session_ended` | gen_ai.agent.id |
| `agent.insight_emitted` | insight.type, insight.value |
| `agent.handoff_created` | handoff.id, gen_ai.tool.name |
| `agent.handoff_completed` | handoff.id, handoff.status |

---

## 7. Metrics

### 7.1 Task Flow Metrics (Phase 2)

Source: `MetricName` enum in `contracts/metrics.py`.

| Metric | Instrument | Unit | Labels |
|--------|-----------|------|--------|
| `task.lead_time` | histogram | s | project.id, task.type |
| `task.cycle_time` | histogram | s | project.id, task.type |
| `task.blocked_time` | histogram | s | project.id |
| `task.wip` | gauge | {tasks} | project.id |
| `task.throughput` | counter | {tasks} | project.id |
| `task.story_points_completed` | counter | {points} | project.id |
| `task.count_by_status` | gauge | {tasks} | project.id, task.status |
| `task.count_by_type` | gauge | {tasks} | project.id, task.type |
| `sprint.velocity` | gauge | {points} | project.id, sprint.id |

### 7.2 Install Metrics (Phase 2)

| Metric | Instrument | Unit |
|--------|-----------|------|
| `contextcore.install.completeness` | gauge | 1 |
| `contextcore.install.requirement.status` | gauge | {requirements} |
| `contextcore.install.verification.duration` | histogram | s |

### 7.3 GenAI Metrics (Phase 2)

Source: `MetricName` enum in `contracts/metrics.py` (GenAI section). Bucket boundaries defined in `GENAI_TOKEN_USAGE_BUCKETS` and `GENAI_DURATION_BUCKETS`.

| Metric | Instrument | Unit | Buckets |
|--------|-----------|------|---------|
| `gen_ai.client.token.usage` | histogram | {tokens} | `[1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]` |
| `gen_ai.server.request.duration` | histogram | s | `[0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]` |
| `gen_ai.server.time_to_first_token` | histogram | s | Same as duration buckets |
| `gen_ai.server.time_per_output_token` | histogram | s | Same as duration buckets |

These follow [OTel GenAI Metrics semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/). ContextCore declares the contracts; contextcore-beaver (StartD8 SDK) records the actual values.

---

## 8. Referenced OTel Attributes (use `ref:`, do not redefine)

These attributes are defined upstream in OTel semantic conventions and referenced via `ref:` in the registry. With Weaver v0.15.3+ `imports` section, these can be imported by reference from the OTel semconv archive rather than redefined:

| Namespace | Attributes | OTel Semconv Version |
|-----------|-----------|---------------------|
| `gen_ai.*` | `gen_ai.system`, `gen_ai.request.model`, `gen_ai.agent.id`, `gen_ai.conversation.id`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments` | v1.34.0 |
| `service.*` | `service.name`, `service.namespace`, `service.version` | v1.34.0 |
| `k8s.*` | `k8s.namespace.name`, `k8s.deployment.name`, `k8s.pod.name` | v1.34.0 |
| `messaging.*` | `messaging.system`, `messaging.destination.name`, `messaging.operation.type`, `messaging.message.id`, `messaging.message.body.size` | v1.34.0 |
| `cicd.pipeline.*` | `cicd.pipeline.name`, `cicd.pipeline.run.id`, `cicd.pipeline.task.name`, `cicd.pipeline.task.run.id`, `cicd.pipeline.task.type` | v1.34.0 |
| `feature_flag.*` | `feature_flag.key`, `feature_flag.provider_name`, `feature_flag.result.variant`, `feature_flag.result.value` | v1.34.0 |

---

## 9. Deprecated Attributes

All `agent.*` attributes carry `deprecated:` fields. The dual-emit layer (`otel_genai.py`) supports three modes:

| Mode | Behavior | Env Var |
|------|----------|---------|
| `legacy` | Emit only `agent.*`, `insight.*`, `handoff.*` | `CONTEXTCORE_EMIT_MODE=legacy` |
| `dual` | Emit both old and `gen_ai.*` equivalents | `CONTEXTCORE_EMIT_MODE=dual` (default) |
| `otel` | Emit only `gen_ai.*` equivalents | `CONTEXTCORE_EMIT_MODE=otel` |

Full mapping from `ATTRIBUTE_MAPPINGS` (canonical dict in `otel_genai.py`):

| Legacy | gen_ai Equivalent |
|--------|------------------|
| `agent.id` | `gen_ai.agent.id` |
| `agent.type` | `gen_ai.agent.type` |
| `agent.session_id` | `gen_ai.conversation.id` |
| `context.id` | `gen_ai.request.id` |
| `context.model` | `gen_ai.request.model` |
| `handoff.capability_id` | `gen_ai.tool.name` |
| `handoff.inputs` | `gen_ai.tool.call.arguments` |
| `handoff.id` | `gen_ai.tool.call.id` |
| `insight.type` | `gen_ai.insight.type` |
| `insight.value` | `gen_ai.insight.value` |
| `insight.confidence` | `gen_ai.insight.confidence` |

**Note:** Use Weaver's structured deprecation format (v0.19+) on both attributes and enum members: `deprecated.since`, `deprecated.note`, `deprecated.renamed_to`. This provides machine-readable deprecation metadata beyond the flat `deprecated:` flag.

---

## 10. Directory Structure

```
semconv/
  manifest.yaml                     # Entry point: name, version, OTel dependency
                                    # Uses schema_url (not registry_url)
                                    # Declares imports for OTel semconv v1.34.0
  registry/                         # Attribute group definitions (file_format: definition/2)
    task.yaml                       # task.* (17 attrs)
    project.yaml                    # project.* (5 attrs)
    sprint.yaml                     # sprint.* (7 attrs)
    business.yaml                   # business.*, design.*, requirement.*, risk.* (16 attrs)
    agent.yaml                      # agent.* (6 attrs, all deprecated)
    insight.yaml                    # insight.*, evidence.* (15 attrs)
    handoff.yaml                    # handoff.* (10 attrs)
    guidance.yaml                   # guidance.* (7 attrs)
    install.yaml                    # contextcore.install.* (12 attrs)
    code_generation.yaml            # gen_ai.code.* (16 attrs)
    propagation.yaml                # propagation.* (Layer 1, 6 attrs)
    schema_compat.yaml              # schema_compat.* (Layer 2, 3 attrs)
    semconv_enforcement.yaml        # semconv.* (Layer 3, 3 attrs)
    boundary.yaml                   # boundary.* (Layer 4, 3 attrs)
    capability_chain.yaml           # capability.* (Layer 5, 3 attrs)
    budget.yaml                     # budget.* (Layer 6, 6 attrs)
    lineage.yaml                    # lineage.* (Layer 7, 4 attrs)
    service_metadata.yaml           # service_metadata.* (TransportProtocol enum)
  spans/
    task_spans.yaml                 # contextcore.task span
    sprint_span.yaml                # contextcore.sprint span
    install_span.yaml               # contextcore.install.verify hierarchy
    handoff_spans.yaml              # handoff lifecycle spans
  events/
    task_events.yaml                # 10 task lifecycle events
    agent_events.yaml               # 5 agent session/insight/handoff events
  metrics/
    task_metrics.yaml               # 9 task flow metrics
    install_metrics.yaml            # 3 install verification metrics
    genai_metrics.yaml              # 4 GenAI metrics (token usage, durations)
```

**Note:** All registry files use `file_format: definition/2` (V2 schema). The `manifest.yaml` includes an `imports:` section to reference OTel semconv `gen_ai.*` attributes rather than redefining them:

```yaml
# semconv/manifest.yaml (illustrative)
file_format: definition/2
schema_url: https://contextcore.io/semconv/v0.1.0
imports:
  - url: https://opentelemetry.io/schemas/1.34.0
    scope:
      - gen_ai.*
      - service.*
      - k8s.*
      - messaging.*
      - cicd.pipeline.*
      - feature_flag.*
```

---

## 11. Phased Delivery

### Phase 1: MVP Registry + CI

**Scope:** 4 attribute groups (task, project, sprint, agent), task spans, task events, CI validation.

**Weaver version:** Pin to v0.21.2+ (V2 schema support, `weaver registry check`, `weaver registry resolve`).

**Deliverables:**
- [ ] `semconv/manifest.yaml` (V2 format, `schema_url`, `imports` for OTel semconv v1.34.0)
- [ ] `semconv/registry/task.yaml` (17 attrs, 3 enums, `file_format: definition/2`)
- [ ] `semconv/registry/project.yaml` (5 attrs)
- [ ] `semconv/registry/sprint.yaml` (7 attrs)
- [ ] `semconv/registry/agent.yaml` (6 deprecated attrs, structured deprecation via v0.19+ format)
- [ ] `semconv/spans/task_spans.yaml`
- [ ] `semconv/events/task_events.yaml` (10 events)
- [ ] `.github/workflows/validate-semconv.yml` (uses `weaver registry check`, not deprecated `weaver registry search`)
- [ ] `Makefile` targets: `semconv-check`, `semconv-resolve`

**Acceptance criteria:**
- `weaver registry check --registry semconv/` passes with zero errors
- `weaver registry resolve --registry semconv/` succeeds
- CI workflow passes on PR (uses `PolicyFinding` terminology, not deprecated `Violation`/`Advice`)
- All enum values in YAML exactly match Python enums in `contracts/types.py`

### Phase 2: Full Attribute Coverage + Metrics

**Scope:** Remaining attributes including Layer 1–7 contract domain groups, all spans, all events, all metrics, service metadata.

**Deliverables:**
- [ ] `semconv/registry/business.yaml` (16 attrs)
- [ ] `semconv/registry/insight.yaml` (15 attrs)
- [ ] `semconv/registry/handoff.yaml` (10 attrs)
- [ ] `semconv/registry/guidance.yaml` (7 attrs)
- [ ] `semconv/registry/install.yaml` (12 attrs)
- [ ] `semconv/registry/code_generation.yaml` (16 attrs)
- [ ] `semconv/registry/propagation.yaml` (Layer 1, 6 attrs)
- [ ] `semconv/registry/schema_compat.yaml` (Layer 2, 3 attrs)
- [ ] `semconv/registry/semconv_enforcement.yaml` (Layer 3, 3 attrs)
- [ ] `semconv/registry/boundary.yaml` (Layer 4, 3 attrs)
- [ ] `semconv/registry/capability_chain.yaml` (Layer 5, 3 attrs)
- [ ] `semconv/registry/budget.yaml` (Layer 6, 6 attrs)
- [ ] `semconv/registry/lineage.yaml` (Layer 7, 4 attrs)
- [ ] `semconv/registry/service_metadata.yaml` (TransportProtocol: grpc, http, grpc-web)
- [ ] `semconv/spans/sprint_span.yaml`
- [ ] `semconv/spans/install_span.yaml`
- [ ] `semconv/spans/handoff_spans.yaml`
- [ ] `semconv/events/agent_events.yaml` (5 events)
- [ ] `semconv/metrics/task_metrics.yaml` (9 metrics)
- [ ] `semconv/metrics/install_metrics.yaml` (3 metrics)
- [ ] `semconv/metrics/genai_metrics.yaml` (4 GenAI metrics with bucket boundaries)

**Acceptance criteria:**
- `weaver registry check` passes with full coverage
- All enum values match Python contracts (27 enums total)
- All metric names match `MetricName` enum
- Layer 1–7 attribute groups cross-checked against `contracts/types.py`

### Phase 3: Live-Check, Diffing, Doc Generation, Agent Discovery

**Scope:** Runtime validation, schema diffing, generated documentation, MCP-based agent discovery.

**Deliverables:**
- [ ] `semconv-live-check` Makefile target (`weaver registry live-check` — validates emitted OTLP against registry, V2-compatible)
- [ ] `semconv-diff` Makefile target (compare current vs tagged release)
- [ ] `semconv/templates/markdown/` Jinja2 templates for doc generation
- [ ] Pre-commit hook for registry validation
- [ ] Python-to-YAML enum consistency verification script
- [ ] `weaver registry mcp` configuration for agent-facing registry access (optional)
- [ ] `weaver registry infer` validation against live telemetry (when released upstream)

**Acceptance criteria:**
- Generated docs equivalent to `docs/semantic-conventions.md`
- `ATTRIBUTE_MAPPINGS` in `otel_genai.py` matches deprecated->replacement pairs in registry
- Pre-commit hook blocks invalid registry changes
- (Optional) `weaver registry mcp` serves registry to ContextCore agents for self-discovery

---

## 12. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Weaver binary not in CI | HIGH | Pin to v0.21.2+ release; use `setup-weaver` GitHub Action. Weaver is now stable with V2 schema support. |
| V2 schema format still evolving | MEDIUM | `file_format: definition/2` is unreleased default but already functional in v0.20+. Pin to specific Weaver release to avoid surprises. |
| OTel semconv dependency fetch flaky | MEDIUM | Cache archive; add retry |
| `weaver registry search` deprecated | LOW | Removed from planned usage; use `weaver registry check` and generated docs instead |
| `gen_ai.code.*` conflicts with future OTel extensions | MEDIUM | Monitor OTel GenAI SIG; use Weaver v0.19+ structured deprecation format for clean migration if conflict arises; rename to `contextcore.code.*` if needed |
| Markdown docs drift during transition | LOW | Keep hand-maintained authoritative until Phase 3 replaces them |
| Python enum mismatch | HIGH | Phase 1 cross-checks explicitly (10 enums); Phase 2 adds 17 Layer 1–7 enums; Phase 3 automates |
| Expanded Phase 2 scope (7 new attribute groups) | MEDIUM | Layer 1–7 groups are well-defined in Python with 12 new enums. Registry YAML is mechanical translation. |
| `weaver registry mcp` availability | LOW | Optional Phase 3 deliverable; not on critical path. Agent discovery works without it. |

---

## 13. Non-Goals

- Replacing `contracts/types.py` or `contracts/metrics.py` — Python remains canonical; YAML mirrors it
- Modifying the dual-emit layer behavior — registry documents what exists, doesn't change runtime
- Upstream contribution to OTel semconv — this is a vendor extension registry, not a proposal
