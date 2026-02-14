# OTel Weaver Registry Requirements

**Plan:** `tranquil-baking-swing.md`
**Date:** 2026-02-11
**Status:** Phase 1 not started

---

## 1. Problem Statement

ContextCore defines ~185 semantic convention attributes across 17+ namespaces, maintained in three divergent sources:

| Source | Path | Role | Known Drift |
|--------|------|------|-------------|
| Markdown prose | `docs/semantic-conventions.md` (1920 lines) | Human documentation | Lists 9 `HandoffStatus` values |
| Python enums | `src/contextcore/contracts/types.py` | Canonical source of truth | Defines 6 `HandoffStatus` members |
| Python contracts | `src/contextcore/contracts/metrics.py` | Metric/label/event names | Some deprecated labels still referenced |
| Dual-emit mappings | `src/contextcore/compat/otel_genai.py` | `agent.*` -> `gen_ai.*` | Multiple `ATTRIBUTE_MAPPINGS` dicts |

There is no machine-readable schema and no automated validation that emitted OTLP conforms to declared conventions.

---

## 2. Goal

Formalize ContextCore's semantic conventions as an [OTel Weaver](https://github.com/open-telemetry/weaver)-compatible registry that provides:

1. **Single source of truth** — one schema for attributes, spans, events, and metrics
2. **Automated validation** — CI runs `weaver registry check` on every PR
3. **Drift detection** — Python enum values cross-checked against registry YAML
4. **Deprecation tracking** — machine-readable `deprecated:` fields for `agent.*` -> `gen_ai.*` migration
5. **Doc generation** (Phase 3) — replace hand-maintained `semantic-conventions.md`

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

---

## 8. Referenced OTel Attributes (use `ref:`, do not redefine)

These attributes are defined upstream in OTel semantic conventions and referenced via `ref:` in the registry:

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

Full mapping from `ATTRIBUTE_MAPPINGS`:

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

---

## 10. Directory Structure

```
semconv/
  registry_manifest.yaml            # Entry point: name, version, OTel dependency
  registry/                         # Attribute group definitions
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
```

---

## 11. Phased Delivery

### Phase 1: MVP Registry + CI

**Scope:** 4 attribute groups (task, project, sprint, agent), task spans, task events, CI validation.

**Deliverables:**
- [ ] `semconv/registry_manifest.yaml`
- [ ] `semconv/registry/task.yaml` (17 attrs, 3 enums)
- [ ] `semconv/registry/project.yaml` (5 attrs)
- [ ] `semconv/registry/sprint.yaml` (7 attrs)
- [ ] `semconv/registry/agent.yaml` (6 deprecated attrs)
- [ ] `semconv/spans/task_spans.yaml`
- [ ] `semconv/events/task_events.yaml` (10 events)
- [ ] `.github/workflows/validate-semconv.yml`
- [ ] `Makefile` targets: `semconv-check`, `semconv-resolve`

**Acceptance criteria:**
- `weaver registry check --registry semconv/` passes with zero errors
- `weaver registry resolve --registry semconv/` succeeds
- CI workflow passes on PR
- All enum values in YAML exactly match Python enums in `contracts/types.py`

### Phase 2: Full Attribute Coverage + Metrics

**Scope:** Remaining ~125 attributes, all spans, all events, all metrics.

**Deliverables:**
- [ ] `semconv/registry/business.yaml` (16 attrs)
- [ ] `semconv/registry/insight.yaml` (15 attrs)
- [ ] `semconv/registry/handoff.yaml` (10 attrs)
- [ ] `semconv/registry/guidance.yaml` (7 attrs)
- [ ] `semconv/registry/install.yaml` (12 attrs)
- [ ] `semconv/registry/code_generation.yaml` (16 attrs)
- [ ] `semconv/spans/sprint_span.yaml`
- [ ] `semconv/spans/install_span.yaml`
- [ ] `semconv/spans/handoff_spans.yaml`
- [ ] `semconv/events/agent_events.yaml` (5 events)
- [ ] `semconv/metrics/task_metrics.yaml` (9 metrics)
- [ ] `semconv/metrics/install_metrics.yaml` (3 metrics)

**Acceptance criteria:**
- `weaver registry check` passes with full coverage
- All enum values match Python contracts
- All metric names match `MetricName` enum

### Phase 3: Live-Check, Diffing, Doc Generation

**Scope:** Runtime validation, schema diffing, generated documentation.

**Deliverables:**
- [ ] `semconv-live-check` Makefile target (validate OTLP against registry)
- [ ] `semconv-diff` Makefile target (compare current vs tagged release)
- [ ] `semconv/templates/markdown/` Jinja2 templates for doc generation
- [ ] Pre-commit hook for registry validation
- [ ] Python-to-YAML enum consistency verification script

**Acceptance criteria:**
- Generated docs equivalent to `docs/semantic-conventions.md`
- `ATTRIBUTE_MAPPINGS` in `otel_genai.py` matches deprecated->replacement pairs in registry
- Pre-commit hook blocks invalid registry changes

---

## 12. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Weaver binary not in CI | HIGH | Pin release; use `setup-weaver` GitHub Action |
| OTel semconv dependency fetch flaky | MEDIUM | Cache archive; add retry |
| Registry format changes upstream | LOW | Pin to tagged OTel semconv v1.34.0 |
| `gen_ai.code.*` conflicts with future OTel extensions | MEDIUM | Monitor OTel GenAI SIG; rename to `contextcore.code.*` if needed |
| Markdown docs drift during transition | LOW | Keep hand-maintained authoritative until Phase 3 replaces them |
| Python enum mismatch | HIGH | Phase 1 cross-checks explicitly; Phase 3 automates |

---

## 13. Non-Goals

- Replacing `contracts/types.py` or `contracts/metrics.py` — Python remains canonical; YAML mirrors it
- Modifying the dual-emit layer behavior — registry documents what exists, doesn't change runtime
- Upstream contribution to OTel semconv — this is a vendor extension registry, not a proposal
