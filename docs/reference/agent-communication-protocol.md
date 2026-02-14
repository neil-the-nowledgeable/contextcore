# Agent Communication Protocol

Standard protocols for agent-to-agent, agent-to-human, and human-to-agent communication in ContextCore.

> **OTel GenAI Alignment (v2.0+)**: ContextCore is migrating to [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). By default, the SDK emits **both** legacy `agent.*` attributes and new `gen_ai.*` attributes. Control this with `CONTEXTCORE_EMIT_MODE` environment variable (`dual`|`legacy`|`otel`). See [Migration Guide](OTEL_GENAI_MIGRATION_GUIDE.md).

---

## Related: A2A Governance Layer

This document covers OTel-level agent communication protocols (insights, guidance, handoffs, personalization). For the **contract-first governance layer** that validates boundaries, enforces phase gates, and provides pipeline integrity checking, see:

- [A2A Communications Design](design/contextcore-a2a-comms-design.md) — architecture reference for contracts, gates, pipeline checker, Three Questions diagnostic
- [A2A Quickstart](A2A_QUICKSTART.md) — 5-minute getting started guide
- [A2A v1 Governance Policy](A2A_V1_GOVERNANCE_POLICY.md) — compliance requirements

The governance layer (`src/contextcore/contracts/a2a/`) provides:

| Module | Purpose | Relates to protocol |
|--------|---------|---------------------|
| `models.py` | Typed Pydantic v2 contracts (`TaskSpanContract`, `HandoffContract`, `ArtifactIntent`, `GateResult`) | Handoff Protocol (§3) |
| `boundary.py` | `validate_outbound()` / `validate_inbound()` at every trust boundary | Handoff Protocol (§3) |
| `gates.py` | Checksum chain, mapping completeness, gap parity gates | Phase transitions |
| `pipeline_checker.py` | 6-gate integrity check on real export output | Export pipeline validation |
| `three_questions.py` | Structured diagnostic: stop at first failing layer | Pipeline troubleshooting |
| `pilot.py` | PI-101-002 end-to-end trace simulation | Full-trace validation |
| `queries.py` | Pre-built TraceQL/LogQL queries for governance dashboard | Dashboard queries |

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
from contextcore.agent.insights import InsightEmitter

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

> **Migration Note**: Both query patterns work in dual-emit mode. Transition to `gen_ai.*` attributes before `CONTEXTCORE_EMIT_MODE=otel` becomes default in v3.0.

### Python SDK Query

```python
from contextcore.agent.insights import InsightQuerier

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

> **Governance integration**: All handoffs should be validated using `validate_outbound()` before sending and `validate_inbound()` before acceptance. The `HandoffContract` Pydantic model in `src/contextcore/contracts/a2a/models.py` provides typed validation, and `boundary.py` enforces schema compliance at every trust boundary. See [A2A Governance](design/contextcore-a2a-comms-design.md).

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
  status: enum                    # pending|accepted|in_progress|input_required|completed|failed|timeout|cancelled|rejected
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
from contextcore.agent.handoff import HandoffManager

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
from contextcore.agent.handoff import HandoffReceiver

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

## Protocol 4: Code Generation with Truncation Prevention

Specialized handoff protocol for code generation tasks with proactive truncation prevention.

### Problem: LLM Output Truncation

When Agent A requests code generation from Agent B, the generated code may be silently truncated due to LLM token limits. Standard validation happens **after** generation, when damage is already done.

**Reactive Flow (Anti-Pattern):**
```
Agent A → Request → Agent B → Generate → [TRUNCATION] → Integrate → Validate → FAIL
                                           ↑
                                      Too late!
```

**Proactive Flow (This Protocol):**
```
Agent A → Request → Agent B → Pre-flight → [TOO BIG] → Decompose → Generate Chunks → Verify → Complete
                                  ↓
                             [OK SIZE] → Generate → Verify → Complete
```

### Extended ExpectedOutput Schema

```yaml
expected_output:
  type: "code"
  fields: ["content", "exports", "imports"]

  # Size constraints (NEW in v2.1+)
  max_lines: 150              # Safe limit for most LLMs
  max_tokens: 500             # Token budget for output
  completeness_markers:       # Required markers that must be present
    - "FooBar"               # Class name that must exist
    - "__all__"              # Module exports list

  # Chunking support (NEW in v2.1+)
  allows_chunking: true       # Can response be split?
  chunk_correlation_id: null  # Parent ID for correlated chunks
```

### Pre-flight Validation Span

Before generation, the receiving agent emits a validation span:

```python
# Receiver-side pre-flight check
with tracer.start_as_current_span("code_generation.preflight") as span:
    estimated = estimate_output_size(handoff.task, handoff.inputs)

    span.set_attribute("gen_ai.code.estimated_lines", estimated.lines)
    span.set_attribute("gen_ai.code.estimated_tokens", estimated.tokens)
    span.set_attribute("gen_ai.code.max_lines_allowed", max_lines)

    if estimated.lines > max_lines:
        span.set_attribute("gen_ai.code.action", "decompose")
        span.add_event("preflight_decision", {
            "decision": "DECOMPOSE_REQUIRED",
            "reason": f"Estimated {estimated.lines} exceeds limit {max_lines}",
        })
        return decompose_and_generate(handoff)
    else:
        span.set_attribute("gen_ai.code.action", "generate")
        return generate_code(handoff)
```

### CodeGenerationHandoff SDK

```python
from contextcore.agent.code_generation import (
    CodeGenerationHandoff,
    CodeGenerationSpec,
)

# Requesting agent
handoff = CodeGenerationHandoff(project_id="myproject", agent_id="orchestrator")

result = handoff.request_code(
    to_agent="code-generator",
    spec=CodeGenerationSpec(
        target_file="src/mymodule.py",
        description="Implement FooBar class with methods x, y, z",
        max_lines=150,                    # Size constraint
        max_tokens=500,
        required_exports=["FooBar"],      # Completeness markers
        allows_decomposition=True,        # Allow chunking if needed
    )
)

if result.status == HandoffStatus.COMPLETED:
    # Code verified as complete
    print(f"Generated {result.line_count} lines")
elif result.decomposition_required:
    # Agent triggered decomposition
    print(f"Decomposed into {result.chunk_count} chunks")
```

### Receiving Agent: CodeGenerationCapability

```python
from contextcore.agent.code_generation import CodeGenerationCapability

capability = CodeGenerationCapability(
    generate_fn=my_llm_generation_function,
    estimate_fn=my_size_estimator,
)

for handoff in receiver.poll_handoffs(project_id="myproject"):
    if handoff.capability_id == "generate_code":
        try:
            result = capability.handle_handoff(handoff)
            # Result verified as complete (syntax valid, exports present)
            receiver.complete(handoff.id, project_id="myproject", result_trace_id=...)
        except CodeTruncatedError as e:
            # Verification failed - code was truncated
            receiver.fail(handoff.id, project_id="myproject", reason=str(e))
        except HandoffRejectedError as e:
            # Pre-flight rejected - size too large, chunking disabled
            receiver.fail(handoff.id, project_id="myproject", reason=str(e))
```

### Verification Span

After generation, verify completeness:

```python
with tracer.start_as_current_span("code_generation.verify") as span:
    issues = verify_completeness(content, required_exports)

    span.set_attribute("gen_ai.code.actual_lines", line_count)
    span.set_attribute("gen_ai.code.truncated", len(issues) > 0)
    span.set_attribute("gen_ai.code.verification_result",
                       "passed" if not issues else "failed_truncation")

    if issues:
        span.set_attribute("gen_ai.code.verification_issues", json.dumps(issues))
        raise CodeTruncatedError(issues)
```

### TraceQL Queries

```traceql
# Find truncated generations
{ span.gen_ai.code.truncated = true }
| select(resource.project.id, span.gen_ai.code.estimated_lines, span.gen_ai.code.actual_lines)

# Find handoffs that required decomposition
{ span.gen_ai.code.action = "decompose" }
| select(span.handoff.id, span.gen_ai.code.estimated_lines)

# Track verification failures
{ name = "code_generation.verify" && status = error }
| select(span.gen_ai.code.verification_issues)
```

### Span Flow

```
code_generation.request (Agent A - Producer)
├── gen_ai.code.target_file
├── gen_ai.code.max_lines
└── gen_ai.code.allows_decomposition

    code_generation.preflight (Agent B)
    ├── gen_ai.code.estimated_lines
    ├── gen_ai.code.action ("generate" | "decompose" | "reject")
    └── event: preflight_decision (if action != "generate")

    code_generation.generate (Agent B)
    ├── gen_ai.code.actual_lines
    └── gen_ai.code.tokens_used

    code_generation.verify (Agent B)
    ├── gen_ai.code.truncated
    ├── gen_ai.code.verification_result
    └── gen_ai.code.verification_issues (if failed)
```

### Anti-Patterns Prevented

| Anti-Pattern | How Prevented |
|--------------|---------------|
| **Warn-Then-Proceed** | Verification is BLOCKING, not advisory |
| **Generate-Complete-Module** | Pre-flight estimation triggers decomposition |
| **Post-Hoc Validation Only** | Pre-flight span emits BEFORE generation |
| **Silent Truncation** | `gen_ai.code.truncated` attribute always recorded |
| **Lost Context on Failure** | All decisions preserved in trace spans |

### Dashboard

The **Code Generation Health** dashboard (`contextcore-code-gen-health`) provides:

1. **Truncation Rate**: Should be < 1%
2. **Decomposition Decisions**: Distribution of generate/decompose/reject
3. **Size Estimation Accuracy**: Estimated vs actual lines
4. **Failed Verifications**: List of truncated generations with details

---

## Protocol 5: Human-to-Agent Guidance

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
from contextcore.agent.guidance import GuidanceReader

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
from contextcore.agent.guidance import GuidanceResponder

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

## Protocol 6: Personalized Presentation

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
from contextcore.agent.personalization import PersonalizedQuerier

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

## Protocol 7: A2A Protocol Interoperability

ContextCore handoffs are interoperable with the [A2A (Agent-to-Agent) Protocol](https://github.com/google/a2a-protocol) via bidirectional adapters.

### Architecture

```
External A2A Agent              ContextCore Agent
       │                              │
       │  JSON-RPC 2.0 / HTTP        │
       ├──────────────────────────────►│
       │                              │
       │        ┌─────────────────────┤
       │        │  TaskAdapter        │
       │        │  A2A Task ↔ Handoff │
       │        └─────────────────────┤
       │                              │
       │◄──────────────────────────────┤
       │                              │
```

### Components

| Component | Module | Purpose |
|-----------|--------|---------|
| `TaskAdapter` | `contextcore.agent.a2a_adapter` | Bidirectional A2A Task ↔ Handoff conversion |
| `A2AMessageHandler` | `contextcore.agent.a2a_messagehandler` | JSON-RPC 2.0 request routing |
| `A2AServer` | `contextcore.agent.a2a_server` | HTTP server (Flask/FastAPI) with discovery endpoints |
| `A2AClient` | `contextcore.agent.a2a_client` | Client for communicating with remote A2A agents |

### State Mapping

| ContextCore HandoffStatus | A2A TaskState | Direction |
|---------------------------|---------------|-----------|
| `pending` | `PENDING` | Both |
| `accepted` | `WORKING` | CC → A2A |
| `in_progress` | `WORKING` | Both |
| `input_required` | `INPUT_REQUIRED` | Both |
| `completed` | `COMPLETED` | Both |
| `failed` | `FAILED` | Both |
| `timeout` | `FAILED` | CC → A2A |
| `cancelled` | `CANCELLED` | Both |
| `rejected` | `REJECTED` | Both |

### A2A Server Example

```python
from contextcore.agent.a2a_server import create_a2a_server

server = create_a2a_server(
    agent_id="my-agent",
    agent_name="My Agent",
    base_url="http://localhost:8080",
    project_id="my-project",
)
server.run()  # Starts Flask server with:
# GET  /.well-known/agent.json     → Agent card discovery
# GET  /.well-known/contextcore.json → CC-specific metadata
# POST /a2a                         → JSON-RPC 2.0 handler
# GET  /health                      → Health check
```

### A2A Client Example

```python
from contextcore.agent.a2a_client import A2AClient
from contextcore.models.message import Message

with A2AClient("http://remote-agent:8080") as client:
    # Discover remote agent capabilities
    card = client.get_agent_card()
    print(f"Agent: {card.name}, capabilities: {card.capabilities}")

    # Send message and get task result
    result = client.send_text("Analyze checkout latency spike")
    print(f"Task: {result['taskId']}, status: {result['status']}")
```

### A2A Message Content Model

ContextCore uses a unified content model compatible with A2A message parts:

```python
from contextcore.models import Part, PartType, Message, MessageRole, Artifact

# Create a message with typed parts
msg = Message(
    role=MessageRole.USER,
    parts=[
        Part.text("Investigate this trace"),
        Part.trace("abc123def456"),
        Part.json_data({"threshold": 200, "metric": "p99_latency"}),
    ],
    agent_id="orchestrator",
)

# Serialize for A2A transport
a2a_dict = msg.to_a2a_dict()

# Create artifacts with trace correlation
artifact = Artifact.from_json(
    data={"root_cause": "N+1 query", "evidence": ["trace-xyz"]},
    trace_id="abc123def456",
)
```

### JSON-RPC Methods

| Method | Description | Maps To |
|--------|-------------|---------|
| `message.send` | Send message to agent | `HandoffsAPI.create()` |
| `tasks.get` | Get task status | `HandoffsAPI.get()` |
| `tasks.list` | List tasks | `HandoffsAPI.list()` |
| `tasks.cancel` | Cancel a task | `HandoffsAPI.cancel()` |
| `agent.getExtendedAgentCard` | Get agent card | `AgentCard.to_a2a_json()` |

### Input Request Protocol

When an A2A agent needs additional input during task execution:

```python
from contextcore.agent.input_request import InputRequest, InputType, InputOption

request = InputRequest(
    handoff_id="handoff-123",
    question="Which database should I investigate?",
    input_type=InputType.CHOICE,
    options=[
        InputOption(value="postgres", label="PostgreSQL Primary"),
        InputOption(value="redis", label="Redis Cache"),
    ],
    timeout_ms=60000,
)
# Handoff status transitions to INPUT_REQUIRED
# Resumes to IN_PROGRESS when response received
```

---

## Human-Readable Documentation (Below)

### Why These Protocols Matter

1. **Insight Emission**: Agents persist knowledge that survives sessions
2. **Insight Query**: Agents access other agents' discoveries without chat transcripts
3. **Handoff**: Structured delegation eliminates prose parsing
4. **Code Generation**: Proactive truncation prevention ensures complete output
5. **Guidance**: Human direction persists across sessions
6. **Personalization**: Same data serves all audiences appropriately
7. **A2A Interoperability**: ContextCore agents communicate with any A2A-compatible agent

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
