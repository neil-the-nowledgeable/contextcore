# Standards Alignment

ContextCore's alignment with observability and agent communication standards.

---

## Standards Overview

| Standard | Organization | Focus | ContextCore Status |
|----------|--------------|-------|-------------------|
| [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/) | CNCF | Telemetry attribute naming | Aligned + Extensions |
| [OTel GenAI Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | CNCF | LLM/AI observability | Dual-emit migration |
| [OWASP Agent Observability Standard](https://aos.owasp.org/) | OWASP | Agent trace events | Partial alignment |
| [A2A Protocol](https://a2a-protocol.org) | Google | Agent-to-agent communication | Implemented |
| [Model Context Protocol](https://modelcontextprotocol.io/) | Anthropic | Tool/resource access | Not implemented |

---

## OWASP Agent Observability Standard (AOS)

### AOS Event Categories

The AOS defines four primary event categories for agent observability:

1. **Execution Steps** — Core agent flow tracking
2. **Decision Events** — Guardian agent decisions
3. **Protocol Events** — Inter-system communication
4. **System Events** — Health and diagnostics

---

## AOS Event Mapping

### Execution Step Events

#### `steps/message`

Captures message exchanges between user and agent.

| AOS Attribute | ContextCore Equivalent | Location |
|---------------|----------------------|----------|
| `sender.role` | `message.role` | `core/message.py` |
| `content` | `message.content` | `core/message.py` |
| `reasoning` | `insight.rationale` | `agent/insights.py` |
| `citations` | `insight.evidence[]` | `agent/insights.py` |

**ContextCore Implementation:**
```python
# Message handling in A2A adapter
class Message:
    role: str           # "user" | "agent" | "system"
    content: str
    metadata: dict      # Additional context
```

**Span Attributes Emitted:**
- `message.role`
- `message.content_length`
- `message.turn_id`
- `agent.session_id` → `gen_ai.conversation.id`

---

#### `steps/agentTrigger`

Records autonomous agent activation from external events.

| AOS Attribute | ContextCore Equivalent | Location |
|---------------|----------------------|----------|
| `trigger.type` | `guidance.type` | `agent/guidance.py` |
| `trigger.source` | `guidance.source` | — |
| `trigger.payload` | `guidance.content` | — |

**ContextCore Implementation:**

ContextCore uses the Guidance system for human-directed triggers. Autonomous triggers (webhooks, scheduled) are partially supported:

```python
class GuidanceType(str, Enum):
    FOCUS = "focus"         # Direct attention
    CONSTRAINT = "constraint"  # Limit behavior
    PREFERENCE = "preference"  # Suggest approach
    QUESTION = "question"      # Request info
    CONTEXT = "context"        # Provide background
    # AUTONOMOUS = "autonomous"  # TODO: Add for AOS alignment
```

**Gap:** No explicit `trigger.type = "autonomous"` flag.

---

#### `steps/toolCallRequest`

Traces tool execution requests before invocation.

| AOS Attribute | ContextCore Equivalent | Location |
|---------------|----------------------|----------|
| `tool.id` | `handoff.capability_id` → `gen_ai.tool.name` | `agent/handoff.py` |
| `execution.id` | `handoff.id` → `gen_ai.tool.call.id` | `agent/handoff.py` |
| `inputs` | `handoff.inputs` → `gen_ai.tool.call.arguments` | `agent/handoff.py` |
| `reasoning` | `handoff.task` (natural language) | `agent/handoff.py` |

**ContextCore Implementation:**
```python
@dataclass
class Handoff:
    id: str
    capability_id: str      # Tool/capability being invoked
    task: str               # Natural language description
    inputs: dict            # Typed inputs
    expected_output: ExpectedOutput  # Size constraints
    priority: HandoffPriority
```

**Span Attributes Emitted:**
- `handoff.id`
- `handoff.capability_id` → `gen_ai.tool.name`
- `handoff.from_agent`
- `handoff.to_agent`
- `handoff.priority`

**SpanKind:** `PRODUCER`

---

#### `steps/toolCallResult`

Captures tool execution outcomes.

| AOS Attribute | ContextCore Equivalent | Location |
|---------------|----------------------|----------|
| `execution.id` | `handoff.id` | `agent/handoff.py` |
| `success` | `handoff.status == COMPLETED` | `agent/handoff.py` |
| `result` | `result_trace_id` (reference to result span) | `agent/handoff.py` |
| `error` | `handoff.status == FAILED` + reason | `agent/handoff.py` |

**ContextCore Implementation:**
```python
class HandoffStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"      # Success
    FAILED = "failed"            # Error
    TIMEOUT = "timeout"
    INPUT_REQUIRED = "input_required"  # A2A-aligned
    CANCELLED = "cancelled"
    REJECTED = "rejected"
```

**Span Events:**
- `handoff.accepted`
- `handoff.completed`
- `handoff.failed`

---

#### `steps/memoryContextRetrieval`

Records when agents retrieve stored context.

| AOS Attribute | ContextCore Equivalent | Location |
|---------------|----------------------|----------|
| `retrieved` | Query results | `agent/insights.py` |
| `reasoning` | Query parameters | `InsightQuerier` |

**ContextCore Implementation:**
```python
class InsightQuerier:
    def query(
        self,
        project_id: str,
        insight_type: InsightType | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Insight]:
        """Query insights from Tempo via TraceQL."""
```

**Span Attributes Emitted:**
- `insight.query.project_id`
- `insight.query.type`
- `insight.query.limit`
- `insight.query.result_count`

**Extension:** ContextCore stores insights as OTel spans, enabling TraceQL queries:
```
{ span.insight.type = "decision" && span.insight.confidence > 0.8 }
```

---

#### `steps/memoryStore`

Tracks information persistence to memory.

| AOS Attribute | ContextCore Equivalent | Location |
|---------------|----------------------|----------|
| `content` | `insight.summary` | `agent/insights.py` |
| `reasoning` | `insight.rationale` | `agent/insights.py` |

**ContextCore Implementation:**
```python
class InsightEmitter:
    def emit(
        self,
        insight_type: InsightType,
        summary: str,
        confidence: float,
        rationale: str | None = None,
        evidence: list[Evidence] | None = None,
        audience: InsightAudience = InsightAudience.BOTH,
        applies_to: list[str] | None = None,
        expires_at: datetime | None = None,
        supersedes: str | None = None,
    ) -> str:
        """Emit insight as OTel span."""
```

**Span Attributes Emitted:**
- `insight.id`
- `insight.type` — `analysis|recommendation|decision|question|blocker|discovery|risk|progress|lesson`
- `insight.summary`
- `insight.confidence`
- `insight.rationale`
- `insight.audience` — `agent|human|both`
- `insight.evidence` (JSON)
- `insight.applies_to`
- `insight.expires_at`
- `insight.supersedes`

**Extension:** ContextCore adds:
- **Confidence scoring** for memory reliability
- **Expiration** for stale memory cleanup
- **Supersedes** for memory versioning
- **Audience** to distinguish agent-only vs human-readable memories

---

#### `steps/knowledgeRetrieval`

Monitors knowledge base and RAG queries.

| AOS Attribute | ContextCore Equivalent | Location |
|---------------|----------------------|----------|
| `query` | Query string | `knowledge/emitter.py` |
| `keywords` | `capability.triggers` | `skill/models.py` |
| `documents` | Retrieved capabilities | `skill/querier.py` |

**ContextCore Implementation:**
```python
class SkillCapabilityQuerier:
    def query_by_trigger(
        self,
        trigger: str,
        category: CapabilityCategory | None = None,
        token_budget: int | None = None,
    ) -> list[SkillCapability]:
        """Query capabilities by trigger keywords."""
```

**Span Attributes Emitted:**
- `capability.query.trigger`
- `capability.query.category`
- `capability.query.budget`
- `capability.query.result_count`

**Extension:** ContextCore treats knowledge as **capabilities** with:
- Token budgets for context window management
- Confidence scores from usage
- Trigger keywords for routing

---

### Decision Events

AOS defines Guardian decisions with three outcomes: Allow, Deny, Modify.

| AOS Decision | ContextCore Equivalent | Implementation |
|--------------|----------------------|----------------|
| `Allow` | `insight.type = "decision"` + positive outcome | `InsightEmitter` |
| `Deny` | `insight.type = "decision"` + blocking rationale | `InsightEmitter` |
| `Modify` | `insight.type = "recommendation"` | `InsightEmitter` |

**ContextCore Implementation:**

ContextCore models guardian-like decisions through the Insight system:

```python
class InsightType(str, Enum):
    ANALYSIS = "analysis"
    RECOMMENDATION = "recommendation"  # Suggests modification
    DECISION = "decision"              # Allow/Deny equivalent
    QUESTION = "question"
    BLOCKER = "blocker"                # Explicit deny with reason
    DISCOVERY = "discovery"
    RISK = "risk"
    PROGRESS = "progress"
    LESSON = "lesson"
```

**Gap:** No structured `decision.outcome` enum (Allow/Deny/Modify). Currently uses:
- `insight.type = "decision"` for allow/deny
- `insight.type = "blocker"` for explicit deny
- `insight.type = "recommendation"` for modify suggestions

**Proposed Extension:**
```python
class DecisionOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    MODIFY = "modify"

# Add to insight attributes
insight.decision.outcome = DecisionOutcome.DENY
insight.decision.reason_code = "rate_limit_exceeded"
insight.decision.modified_request = {...}  # For MODIFY
```

---

### Protocol Events

#### `protocols/A2A`

Agent-to-agent communication per A2A protocol standard.

| AOS Attribute | ContextCore Equivalent | Location |
|---------------|----------------------|----------|
| JSON-RPC payload | Full request/response | `agent/a2a_client.py` |
| Method | `handoff.capability_id` | `agent/handoff.py` |
| Params | `handoff.inputs` | `agent/handoff.py` |

**ContextCore Implementation:**

Full A2A protocol stack:

```
src/contextcore/agent/
├── a2a_client.py          # JSON-RPC 2.0 client
├── a2a_server.py          # A2A endpoint handler
├── a2a_adapter.py         # Protocol adapter
├── a2a_messagehandler.py  # Message routing
└── a2a_package.py         # Package definitions
```

```python
# a2a_client.py
class A2AClient:
    def _request(self, method: str, params: dict | None = None) -> dict:
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._next_request_id(),
        }
```

**Span Attributes Emitted:**
- `a2a.method`
- `a2a.request_id`
- `a2a.target_agent`
- `a2a.response_time_ms`

---

#### `protocols/MCP`

Model Context Protocol interactions.

| AOS Attribute | ContextCore Equivalent | Status |
|---------------|----------------------|--------|
| MCP request/response | — | **Not implemented** |

**Gap:** ContextCore does not currently emit MCP-specific telemetry.

**Proposed Implementation:**
```python
# Future: src/contextcore/protocols/mcp.py
class MCPTelemetry:
    def emit_tool_list(self, tools: list[Tool]) -> None:
        """Emit MCP tools/list response."""

    def emit_tool_call(self, tool: str, arguments: dict) -> None:
        """Emit MCP tools/call request."""

    def emit_resource_read(self, uri: str) -> None:
        """Emit MCP resources/read."""
```

---

### System Events

#### `ping`

Health check events.

| AOS Attribute | ContextCore Equivalent | Location |
|---------------|----------------------|----------|
| `timestamp` | Check timestamp | `install/verifier.py` |
| `timeout` | Check timeout | — |
| `status` | `requirement.status` | `install/verifier.py` |
| `version` | Package version | — |

**ContextCore Implementation:**

Installation verifier emits health-like checks:

```python
# Span attributes
contextcore.install.requirement.id
contextcore.install.requirement.status  # passed|failed|skipped|error
contextcore.install.requirement.duration_ms
contextcore.install.completeness  # 0-100%
```

**Gap:** No dedicated `ping` event type. Health is modeled through installation verification.

---

## Alignment Summary

### Fully Aligned

| AOS Event | ContextCore Coverage |
|-----------|---------------------|
| `steps/toolCallRequest` | `handoff.*` with PRODUCER spans |
| `steps/toolCallResult` | `handoff.status` + result spans |
| `steps/memoryStore` | `InsightEmitter` with extended attributes |
| `steps/memoryContextRetrieval` | `InsightQuerier` with TraceQL |
| `protocols/A2A` | Full A2A client/server implementation |

### Partially Aligned

| AOS Event | Gap | Effort |
|-----------|-----|--------|
| `steps/message` | Message spans exist but attributes differ | Low |
| `steps/agentTrigger` | No `trigger.type = "autonomous"` | Low |
| `steps/knowledgeRetrieval` | Modeled as capability queries | Low |
| Decision Events | No Allow/Deny/Modify enum | Low |
| `ping` | Health via installation verifier | Low |

### Not Implemented

| AOS Event | Gap | Effort |
|-----------|-----|--------|
| `protocols/MCP` | No MCP telemetry | Medium |

---

## ContextCore Extensions Beyond AOS

ContextCore extends AOS with capabilities not in the standard:

### 1. Project Context Layer

```
project.id      — Business project identifier
task.id         — Work item being executed
sprint.id       — Iteration context
```

Connects agent actions to business outcomes.

### 2. Confidence and Expiration

```
insight.confidence   — Reliability score (0.0-1.0)
insight.expires_at   — Memory staleness
insight.supersedes   — Version chain
```

Enables queryable, versioned memory.

### 3. Audience Targeting

```
insight.audience = "agent" | "human" | "both"
```

Distinguishes machine-readable vs human-readable memories.

### 4. Lesson Learning

```
lesson.id
lesson.category      — testing, architecture, security, etc.
lesson.applies_to    — File/module patterns
lesson.is_global     — Cross-project applicability
```

Persistent learning across sessions and projects.

### 5. Value Alignment

```
value.type           — direct, indirect, ripple
value.persona        — Target audience
value.channel        — Distribution method
value.pain_point     — Problem solved
value.benefit_metric — Quantified outcome
```

Connects agent capabilities to business value.

---

## Roadmap

### Phase 1: AOS Alignment (Low Effort)

- [ ] Add `trigger.type` to Guidance system
- [ ] Add `DecisionOutcome` enum to Insight
- [ ] Emit `steps/message` events with AOS attributes
- [ ] Add structured reason codes to decisions

### Phase 2: MCP Telemetry (Medium Effort)

- [ ] Create `protocols/mcp.py` telemetry emitter
- [ ] Emit `protocols/MCP` events for tool/resource access
- [ ] Map MCP tools to ContextCore capabilities

### Phase 3: AOS Contribution

- [ ] Propose `insight.*` extensions for memory events
- [ ] Propose `project.*` context for StepContext
- [ ] Propose `lesson.*` events for agent learning
- [ ] Submit implementation examples

---

## References

- [OWASP AOS Specification](https://aos.owasp.org/spec/)
- [AOS Trace Events](https://aos.owasp.org/spec/trace/events/)
- [A2A Protocol](https://a2a-protocol.org)
- [OTel GenAI Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [ContextCore Semantic Conventions](./semantic-conventions.md)
- [ContextCore Agent Conventions](./agent-semantic-conventions.md)
- [OTel GenAI Migration Guide](./OTEL_GENAI_MIGRATION_GUIDE.md)

---

*Created: 2026-01-27*
