# Gap Analysis: ContextCore vs OTel GenAI Semantic Conventions

**Date:** 2026-01-29 (Updated)
**Status:** Resolved
**Related Plan:** [OTEL_GENAI_ADOPTION_PLAN.md](OTEL_GENAI_ADOPTION_PLAN.md)

---

## 1. Executive Summary

ContextCore currently uses a custom `agent.*` namespace for agent telemetry. The OpenTelemetry community has recently stabilized the `gen_ai.*` namespace for Generative AI observability. To ensuring interoperability with the broader OTel ecosystem, ContextCore must align with these new conventions while preserving its unique project-management specific attributes.

This analysis identifies the gaps between ContextCore's current implementation and the OTel GenAI semantic conventions (v1.28.0+), proposing a migration path that maintains backward compatibility.

## 2. Attribute Comparison

### 2.1 Agent Identity

| ContextCore Attribute | OTel GenAI Attribute | Status | Resolution |
|-----------------------|----------------------|--------|------------|
| `agent.id`            | `gen_ai.agent.id`    | **Resolved** | Dual-emit via `ATTRIBUTE_MAPPINGS` in `otel_genai.py`. |
| `agent.name` (implicit)| `gen_ai.agent.name` | **Resolved** | Added as `agent_name` param on `InsightEmitter.__init__()`. Emits `gen_ai.agent.name`. |
| `agent.type`          | `gen_ai.agent.description` | **Resolved** | Added as `agent_description` param on `InsightEmitter.__init__()`. Emits `gen_ai.agent.description`. |
| `agent.version`       | - | **Keep** | No direct OTel equivalent. ContextCore-specific. |
| `agent.capabilities`  | - | **Keep** | ContextCore-specific. |

### 2.2 Session Management

| ContextCore Attribute | OTel GenAI Attribute | Status | Resolution |
|-----------------------|----------------------|--------|------------|
| `agent.session_id`    | `gen_ai.conversation.id` | **Resolved** | Dual-emit via `ATTRIBUTE_MAPPINGS`. |
| `agent.parent_session_id` | - | **Keep** | OTel uses span parentage. Explicit linkage retained for ContextCore. |

### 2.3 Operations & Models

| ContextCore Attribute | OTel GenAI Attribute | Status | Resolution |
|-----------------------|----------------------|--------|------------|
| -                     | `gen_ai.system`      | **Resolved** | Emitted by `InsightEmitter.emit()` and `HandoffManager` (provider param). |
| -                     | `gen_ai.request.model`| **Resolved** | Emitted by `InsightEmitter.emit()` and `HandoffManager` (model param). |
| -                     | `gen_ai.operation.name`| **Resolved** | Emitted on all insight and handoff spans. |
| -                     | `gen_ai.usage.input_tokens`| **Resolved** | Added as `input_tokens` param on `InsightEmitter.emit()`. |
| -                     | `gen_ai.usage.output_tokens`| **Resolved** | Added as `output_tokens` param on `InsightEmitter.emit()`. |
| -                     | `gen_ai.request.temperature`| **Resolved** | Added as `temperature` param on `InsightEmitter.emit()`. |
| -                     | `gen_ai.request.top_p`| **Resolved** | Added as `top_p` param on `InsightEmitter.emit()`. |
| -                     | `gen_ai.request.max_tokens`| **Resolved** | Added as `max_tokens` param on `InsightEmitter.emit()`. |
| -                     | `gen_ai.response.model`| **Resolved** | Added as `response_model` param on `InsightEmitter.emit()`. |
| -                     | `gen_ai.response.id`| **Resolved** | Added as `response_id` param on `InsightEmitter.emit()`. |
| -                     | `gen_ai.response.finish_reasons`| **Resolved** | Added as `finish_reasons` param on `InsightEmitter.emit()`. |

### 2.4 Handoffs & Tools

| ContextCore Attribute | OTel GenAI Attribute | Status | Resolution |
|-----------------------|----------------------|--------|------------|
| `handoff.capability_id`| `gen_ai.tool.name`  | **Resolved** | Emitted directly on handoff spans. |
| `handoff.inputs`      | `gen_ai.tool.call.arguments` | **Resolved** | Serialized as JSON on handoff spans. |
| `handoff.id`          | `gen_ai.tool.call.id` | **Resolved** | Emitted on handoff spans. |
| -                     | `gen_ai.tool.type` | **Resolved** | Set to `agent_handoff` on handoff spans. |
| -                     | `gen_ai.system` | **Resolved** | Added `provider` param to `HandoffManager.__init__()`. |
| -                     | `gen_ai.request.model` | **Resolved** | Added `model` param to `HandoffManager.__init__()`. |

## 3. Migration Strategy

### 3.1 Dual-Emit Compatibility Layer

To prevent breaking existing dashboards and queries, we will implement a **Dual-Emit Layer**.

**Mechanism:**
When the code emits `agent.id="claude"`, the layer will automatically emit:
- `agent.id="claude"` (Legacy)
- `gen_ai.agent.id="claude"` (New)

**Configuration:**
Environment variable `CONTEXTCORE_EMIT_MODE`:
- `dual` (Default): Emit both.
- `legacy`: Emit only old attributes.
- `otel`: Emit only new attributes (Target state).

### 3.2 Breaking Changes

1. **Session ID**: Moving from `agent.session_id` to `gen_ai.conversation.id` will break queries relying on the old field if they are not updated. The dual-emit layer mitigates this, but queries must eventually be migrated.
2. **Handoff Structure**: Aligning with tool conventions might change how handoff inputs are stored (e.g. JSON string vs object map).

## 4. Implementation Plan

See [OTEL_GENAI_ADOPTION_PLAN.md](OTEL_GENAI_ADOPTION_PLAN.md) for the execution breakdown.

1. **Gap Analysis** — Completed (this document)
2. **Dual-Emit Layer** — Completed (`otel_genai.py`, `CONTEXTCORE_EMIT_MODE` env var)
3. **Core Attribute Migration** — Completed (`agent.id` → `gen_ai.agent.id`, `session_id` → `gen_ai.conversation.id`)
4. **Operation & Model** — Completed (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.operation.name`)
5. **Tool/Handoff** — Completed (`gen_ai.tool.*` on handoff spans, provider/model on `HandoffManager`)
6. **Token Usage & Request/Response** — Completed (Phase 3: `gen_ai.usage.*`, `gen_ai.request.*`, `gen_ai.response.*`)
7. **Agent Metadata** — Completed (Phase 3: `gen_ai.agent.name`, `gen_ai.agent.description`)
8. **Documentation** — Completed (env var fix, semantic-conventions.md GenAI reference)

## 5. References

- [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [ContextCore Agent Semantic Conventions](agent-semantic-conventions.md)
