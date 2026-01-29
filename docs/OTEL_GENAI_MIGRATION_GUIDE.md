# ContextCore OTel GenAI Migration Guide

**Version:** 2.0.0
**Date:** 2026-01-18

ContextCore is adopting the official [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) to ensure interoperability with the broader observability ecosystem. This guide helps you migrate from ContextCore-specific attributes to the new standard.

---

## Migration Strategy: Dual-Emit

To ensure a smooth transition, ContextCore introduces a **Dual-Emit Layer**. By default, the SDK emits **BOTH** the legacy `agent.*` attributes and the new `gen_ai.*` attributes.

You can control this behavior with the `CONTEXTCORE_EMIT_MODE` environment variable:

| Mode | Value | Behavior | Use Case |
|------|-------|----------|----------|
| **Dual** | `dual` | Emits both old and new attributes. (Default) | Transition period. Safe for existing dashboards. |
| **Legacy** | `legacy` | Emits only `agent.*` attributes. | Rollback if issues occur. |
| **OTel** | `otel` | Emits only `gen_ai.*` attributes. | Final state. Reduces data volume. |

### Example

**Python Code:**
```python
emitter.emit_decision(summary="Chose architecture", confidence=0.9)
```

**Emitted Attributes (Dual Mode):**
```json
{
  "agent.id": "claude-code",           // Legacy
  "gen_ai.agent.id": "claude-code",    // New OTel Standard
  
  "agent.session_id": "sess-123",      // Legacy
  "gen_ai.conversation.id": "sess-123", // New OTel Standard
  
  "insight.type": "decision"           // ContextCore extension (preserved)
}
```

---

## Attribute Mapping Reference

### Agent Identity

| Legacy Attribute | New OTel Attribute | Notes |
|------------------|-------------------|-------|
| `agent.id` | `gen_ai.agent.id` | Direct mapping. |
| (Implicit) | `gen_ai.agent.name` | Human-readable name. |
| `agent.session_id` | `gen_ai.conversation.id` | **Critical change.** Update session queries. |

### Operations & Models

| Legacy Attribute | New OTel Attribute | Notes |
|------------------|-------------------|-------|
| - | `gen_ai.system` | Provider name (e.g., `openai`, `anthropic`). |
| - | `gen_ai.request.model` | Model name (e.g., `gpt-4o`). |
| - | `gen_ai.operation.name` | Operation type (e.g., `insight.emit`, `task`). |

### Handoffs (Tool Calls)

| Legacy Attribute | New OTel Attribute | Notes |
|------------------|-------------------|-------|
| `handoff.capability_id` | `gen_ai.tool.name` | Maps handoff to tool execution. |
| `handoff.inputs` | `gen_ai.tool.call.arguments` | Serialized as JSON string. |
| `handoff.id` | `gen_ai.tool.call.id` | Unique call identifier. |
| - | `gen_ai.tool.type` | Set to `agent_handoff`. |

---

## Migrating Queries

You should begin updating your TraceQL and LogQL queries to use the new attributes.

### TraceQL Examples

**Old:**
```traceql
{ span.agent.id = "claude-code" }
```

**New:**
```traceql
{ span.gen_ai.agent.id = "claude-code" }
```

**Old:**
```traceql
{ span.handoff.capability_id = "investigate_error" }
```

**New:**
```traceql
{ span.gen_ai.tool.name = "investigate_error" }
```

### LogQL Examples

**Old:**
```logql
{agent_id="claude-code"}
```

**New:**
```logql
{gen_ai_agent_id="claude-code"}
```

---

## Deprecation Timeline

- **v2.0 (Current)**: Dual-emit enabled by default. `gen_ai.*` attributes introduced.
- **v2.1**: Warnings added when accessing legacy attributes in code.
- **v3.0**: `CONTEXTCORE_EMIT_MODE` defaults to `otel`. Legacy attributes removed.

We recommend switching `CONTEXTCORE_EMIT_MODE` to `otel` in your non-production environments to verify your dashboards and alerts are updated.
