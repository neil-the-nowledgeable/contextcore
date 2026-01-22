# Agent Communication Protocol

Standard protocols for agent-to-agent, agent-to-human, and human-to-agent communication in ContextCore.

> **OTel GenAI Alignment (v2.0+)**: ContextCore is migrating to [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). By default, the SDK emits **both** legacy `agent.*` attributes and new `gen_ai.*` attributes. Control this with `CONTEXTCORE_OTEL_MODE` environment variable (`dual`|`legacy`|`otel`). See [Migration Guide](OTEL_GENAI_MIGRATION_GUIDE.md).

---

## Agent-to-Agent Communication (Machine-Readable)

### Protocol Summary

| Direction | Write Path | Read Path | Query Language |
|-----------|------------|-----------|----------------|
| Agent → Agent | OTel SDK → Tempo | TraceQL | `{ insight.type = "decision" }` |
| Agent → Human | OTel SDK → Tempo/Loki | Grafana | Dashboard queries |
| Human → Agent | kubectl / K8s API | Python SDK | `get_project_context()` |

### Token Budget

| Operation | Typical Tokens | Max Tokens |
|-----------|---------------|------------|
| Read guidance | ~200 | 500 |
| Query insights | ~100-500 | 1000 |
| Write insight | ~50 (emit) | N/A |
| Read full context | ~800 | 2000 |

---

## Protocol 1: Agent Insight Emission

Agents emit insights as OTel spans stored in Tempo.

### Schema

```yaml
insight_span:
  name: "insight.{type}"           # e.g., insight.decision
  kind: SPAN_KIND_INTERNAL

  attributes:
    # Required
    insight.id: string             # Unique identifier
    insight.type: enum             # decision|recommendation|blocker|discovery|...
    insight.summary: string        # 1-2 sentence summary
    insight.confidence: float      # 0.0-1.0
    insight.audience: enum         # agent|human|both

    # Context linking
    project.id: string             # Project this insight belongs to

    # Agent identity (dual-emit in v2.0+)
    agent.id: string               # Legacy: Agent that generated insight
    gen_ai.agent.id: string        # OTel GenAI: Same value as agent.id
    agent.session_id: string       # Legacy: Session context
    gen_ai.conversation.id: string # OTel GenAI: Same value as agent.session_id

    # OTel GenAI operation context (v2.0+)
    gen_ai.system: string          # e.g., "anthropic", "openai"
    gen_ai.operation.name: string  # e.g., "insight.emit"

    # Optional
    insight.rationale: string      # Why this insight
    insight.supersedes: string     # ID of replaced insight
    insight.expires_at: timestamp  # When insight becomes stale

  events:
    - name: "evidence.added"
      attributes:
        evidence.type: string      # trace|log_query|file|commit|...
        evidence.ref: string       # Reference to supporting data
        evidence.description: string

  links:
    - to: span_context             # Link to supporting trace
      attributes:
        link.relationship: "evidence"
```

> **Attribute Mapping**: In dual-emit mode (default), both `agent.id` and `gen_ai.agent.id` are set to the same value. This allows gradual migration of queries from legacy to OTel conventions.

### Example: Decision Insight

```python
from opentelemetry import trace
from contextcore.insights import InsightEmitter

emitter = InsightEmitter(
    project_id="checkout-service",
    agent_id="claude-code",
    session_id="session-abc123"
)

# Emit a decision insight
emitter.emit_decision(
    summary="Selected event-driven architecture for payment processing",
    confidence=0.92,
    audience="both",
    rationale="Lower coupling, better scaling, aligns with ADR-015",
    evidence=[
        {"type": "adr", "ref": "ADR-015-event-driven"},
        {"type": "trace", "ref": "trace-xyz", "description": "Current sync latency 200ms"}
    ]
)
```

---

## Protocol 2: Agent Insight Query

Agents query insights from other agents via TraceQL.

### Query Patterns

**Legacy attributes** (pre-v2.0):
```
# Recent decisions for this project
{ insight.type = "decision" && project.id = "checkout" } | select(insight.summary, insight.confidence)

# High-confidence recommendations
{ insight.type = "recommendation" && insight.confidence > 0.85 }

# Unresolved blockers
{ insight.type = "blocker" && insight.audience =~ "agent|both" }

# Insights from specific agent
{ agent.id = "o11y-specialist" && project.id = "checkout" }

# Recent insights (last 2 hours)
{ insight.type =~ "decision|recommendation" } | select(insight.summary) | rate() > 0
```

**OTel GenAI attributes** (v2.0+, recommended for new queries):
```
# Insights from specific agent (OTel GenAI)
{ span.gen_ai.agent.id = "o11y-specialist" && span.project.id = "checkout" }

# Filter by conversation/session (OTel GenAI)
{ span.gen_ai.conversation.id = "session-abc123" && span.insight.type = "decision" }

# Filter by AI system provider
{ span.gen_ai.system = "anthropic" && span.insight.type = "recommendation" }
```

> **Migration Note**: Both query patterns work in dual-emit mode. Transition to `gen_ai.*` attributes before `CONTEXTCORE_OTEL_MODE=otel` becomes default in v3.0.

### Python SDK Query

```python
from contextcore.insights import InsightQuerier

querier = InsightQuerier(tempo_url="http://localhost:3200")

# Query recent decisions
decisions = querier.query(
    project_id="checkout-service",
    insight_type="decision",
    min_confidence=0.8,
    time_range="24h",
    limit=10
)

for decision in decisions:
    print(f"{decision.summary} (confidence: {decision.confidence})")
    for evidence in decision.evidence:
        print(f"  - {evidence.type}: {evidence.ref}")
```

---

## Protocol 3: Agent-to-Agent Handoff

Structured task delegation between agents.

### Handoff Message Schema

```yaml
handoff_message:
  # Identity
  id: string                      # Unique handoff ID (maps to gen_ai.tool.call.id)
  from_agent: string              # Delegating agent
  to_agent: string                # Receiving agent (or capability ID)

  # Task specification
  capability_id: string           # Specific capability to invoke
  task: string                    # Natural language description
  inputs:                         # Typed inputs (matches capability schema)
    key: value

  # Expected response
  expected_output:
    type: string                  # Output type name
    fields: [string]              # Required fields in response

  # Constraints
  priority: enum                  # critical|high|normal|low
  timeout_ms: integer             # Max wait time

  # State
  status: enum                    # pending|accepted|in_progress|completed|failed|timeout
  created_at: timestamp
  result_trace_id: string         # Trace ID containing result
```

**OTel GenAI Mapping (v2.0+)**:

| Handoff Field | Legacy Attribute | OTel GenAI Attribute |
|---------------|------------------|---------------------|
| `id` | `handoff.id` | `gen_ai.tool.call.id` |
| `capability_id` | `handoff.capability_id` | `gen_ai.tool.name` |
| `inputs` | `handoff.inputs` | `gen_ai.tool.call.arguments` (JSON) |
| - | - | `gen_ai.tool.type` = `"agent_handoff"` |

### Handoff Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HANDOFF PROTOCOL FLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  AGENT A                       CONTEXTCORE                      AGENT B     │
│  ────────                      ───────────                      ────────    │
│                                                                              │
│  1. Create handoff ──────────► Write to ProjectContext                      │
│     (status: pending)          handoffQueue[]                               │
│                                                                              │
│                                     │                                        │
│                                     ▼                                        │
│                                                                              │
│                                Query handoffQueue ◄──────── 2. Poll/Watch   │
│                                for to_agent match                            │
│                                                                              │
│                                     │                                        │
│                                     ▼                                        │
│                                                                              │
│                                Update status ◄─────────── 3. Accept handoff │
│                                (accepted)                 (status: accepted) │
│                                                                              │
│                                     │                                        │
│                                     ▼                                        │
│                                                                              │
│                                                           4. Execute task   │
│                                                           Emit result span  │
│                                                                              │
│                                     │                                        │
│                                     ▼                                        │
│                                                                              │
│                                Update status ◄─────────── 5. Complete       │
│                                (completed)                (result_trace_id) │
│                                + result_trace_id                             │
│                                                                              │
│                                     │                                        │
│                                     ▼                                        │
│                                                                              │
│  6. Query result ────────────► Fetch from Tempo                             │
│     by trace_id                                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Python SDK: Handoff Creation

```python
from contextcore.handoff import HandoffManager

manager = HandoffManager(
    project_id="checkout-service",
    agent_id="orchestrator"
)

# Create handoff to o11y specialist
handoff_id = manager.create_handoff(
    to_agent="o11y",
    capability_id="investigate_error",
    task="Find root cause of checkout latency spike",
    inputs={
        "error_context": "P99 latency increased from 200ms to 800ms",
        "time_range": "2h",
        "app_name": "checkout-service"
    },
    expected_output={
        "type": "analysis_report",
        "fields": ["root_cause", "evidence", "recommended_fix"]
    },
    priority="high",
    timeout_ms=300000
)

# Wait for result (blocking)
result = manager.await_result(handoff_id, timeout_ms=300000)

if result.status == "completed":
    analysis = manager.get_result_from_trace(result.result_trace_id)
    print(f"Root cause: {analysis.root_cause}")
else:
    print(f"Handoff failed: {result.status}")
```

### Python SDK: Handoff Reception

```python
from contextcore.handoff import HandoffReceiver

receiver = HandoffReceiver(
    agent_id="o11y",
    capabilities=["investigate_error", "create_dashboard"]
)

# Watch for handoffs (non-blocking)
async for handoff in receiver.watch_handoffs():
    print(f"Received: {handoff.task}")

    # Accept the handoff
    receiver.accept(handoff.id)

    try:
        # Execute the capability
        result = await execute_capability(
            handoff.capability_id,
            handoff.inputs
        )

        # Complete with result
        receiver.complete(
            handoff.id,
            result=result,
            result_trace_id=result.trace_id
        )
    except Exception as e:
        receiver.fail(handoff.id, reason=str(e))
```

---

## Protocol 4: Human-to-Agent Guidance

Humans provide persistent direction via ProjectContext CRD.

### Guidance Schema (in ProjectContext)

```yaml
spec:
  agentGuidance:
    focus:
      areas:
        - "performance optimization"
        - "reduce checkout latency"
      reason: "Q1 performance target: P99 < 150ms"
      until: "2024-03-31T00:00:00Z"

    constraints:
      - id: "no-breaking-changes"
        rule: "Do not modify public API signatures"
        scope: "src/api/**"
        severity: blocking
        reason: "External clients depend on current API"

      - id: "auth-approval"
        rule: "Authentication changes require explicit approval"
        scope: "src/auth/**"
        severity: blocking
        reason: "Security-sensitive code"

    preferences:
      - id: "async-preferred"
        preference: "Prefer async patterns over sync when adding new code"
        reason: "Aligns with ADR-015 event-driven architecture"

    questions:
      - id: "q-latency-cause"
        question: "What is causing the P99 latency spike in checkout?"
        priority: critical
        context: "Latency increased from 200ms to 800ms yesterday"
        status: open

    context:
      - topic: "Recent architecture changes"
        content: "We migrated from sync to async in payment processing last week"
        source: "https://docs.internal/checkout-async-migration"
```

### Python SDK: Reading Guidance

```python
from contextcore.guidance import GuidanceReader

reader = GuidanceReader(project_id="checkout-service")

# Get current focus areas
focus = reader.get_focus()
print(f"Focus areas: {focus.areas}")
print(f"Reason: {focus.reason}")

# Check constraints before action
action_path = "src/api/checkout.py"
constraints = reader.get_constraints_for_path(action_path)
for constraint in constraints:
    if constraint.severity == "blocking":
        print(f"BLOCKED: {constraint.rule}")

# Get open questions
questions = reader.get_open_questions()
for q in questions:
    if q.priority == "critical":
        print(f"CRITICAL Q: {q.question}")

# Get context on a topic
context = reader.get_context("architecture")
print(f"Context: {context.content}")
```

### Python SDK: Answering Questions

```python
from contextcore.guidance import GuidanceResponder

responder = GuidanceResponder(
    project_id="checkout-service",
    agent_id="claude-code"
)

# Answer a question
responder.answer_question(
    question_id="q-latency-cause",
    answer="Root cause is N+1 database query in payment verification",
    confidence=0.95,
    evidence=[
        {"type": "trace", "ref": "trace-abc123"},
        {"type": "log_query", "ref": '{app="checkout"} |= "query_time"'}
    ]
)

# This also emits an insight span for the answer
```

---

## Protocol 5: Personalized Presentation

Same data, audience-appropriate views.

### Personalization Schema (in ProjectContext)

```yaml
spec:
  personalization:
    executive:
      dashboardId: "exec-checkout-overview"
      summaryFields: ["criticality", "value", "sloCompliance"]
      alertThreshold: critical_only

    manager:
      dashboardId: "pm-checkout-sprint"
      reportingCadence: "weekly"

    developer:
      dashboardId: "dev-checkout-detailed"
      preferredFormat: detailed

    agent:
      preferredQueryBackend: tempo
      maxContextTokens: 2000
```

### Audience-Aware Query

```python
from contextcore.personalization import PersonalizedQuerier

querier = PersonalizedQuerier(project_id="checkout-service")

# Get insights formatted for audience
executive_view = querier.get_insights(
    audience="executive",
    time_range="7d"
)
# Returns: High-level summary, counts, trends

developer_view = querier.get_insights(
    audience="developer",
    time_range="24h"
)
# Returns: Full technical detail, code references, traces

agent_view = querier.get_insights(
    audience="agent",
    time_range="2h"
)
# Returns: Typed YAML, minimal prose, direct references
```

---

## Human-Readable Documentation (Below)

### Why These Protocols Matter

1. **Insight Emission**: Agents persist knowledge that survives sessions
2. **Insight Query**: Agents access other agents' discoveries without chat transcripts
3. **Handoff**: Structured delegation eliminates prose parsing
4. **Guidance**: Human direction persists across sessions
5. **Personalization**: Same data serves all audiences appropriately

### Design Principles

1. **OTel-Native**: All agent communication uses OpenTelemetry primitives (spans, events, attributes)
2. **OTel GenAI Aligned**: Attributes follow [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) for ecosystem interoperability
3. **Query-First**: Data stored for query access, not document parsing
4. **Typed Schemas**: No natural language parsing for structured operations
5. **Audience-Aware**: Every piece of data knows its intended consumer
6. **Linked**: Insights link to evidence; handoffs link to results
7. **Dual-Emit Compatible**: SDK supports gradual migration from legacy to OTel GenAI conventions

### Anti-Patterns

| Don't | Why | Instead |
|-------|-----|---------|
| Store insights in chat only | Not queryable, session-scoped | Emit as OTel spans |
| Parse prose for handoffs | Unreliable, wastes tokens | Use typed handoff schema |
| Ignore guidance constraints | May violate human intent | Check constraints before action |
| Same format for all audiences | Wastes tokens, poor UX | Use personalization hints |
| Poll for handoffs | Inefficient | Watch/subscribe pattern |
