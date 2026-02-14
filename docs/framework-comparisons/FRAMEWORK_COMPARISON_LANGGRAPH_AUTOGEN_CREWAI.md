# LangGraph, AutoGen, CrewAI vs ContextCore: Implementation-Oriented Comparison

Concise comparison for execution governance and observability. ContextCore focuses on **governance + observability**; these frameworks handle **runtime orchestration**. No duplication of orchestration logic.

---

## LangGraph

### 1) Strengths vs ContextCore

- **StateGraph + checkpointing**: Built-in persistence for long-running tasks; state snapshots at each node. ContextCore has span lifecycle but no native checkpoint semantics.
- **Conditional edges**: Runtime routing based on agent output; explicit branching. ContextCore gates are governance-only, not execution routing.
- **Cyclic graphs**: Supports reasoning loops (agent → tool → agent). ContextCore models phases linearly.
- **Parallel execution**: Multiple nodes can run concurrently with merge. ContextCore spans can nest but parallel semantics are implicit.
- **Streaming + debugging**: First-class streaming and debug tooling. ContextCore emits to OTLP; no built-in stream/debug UX.
- **LangChain ecosystem**: Broad integrations, tool wrappers, model providers. ContextCore is runtime-agnostic and has fewer turnkey integrations.

### 2) Weaknesses vs ContextCore

- **No contract-first boundaries**: Node transitions are implicit; no `HandoffContract` or `GateResult` at edges.
- **Shared state vs typed handoffs**: Centralized state object; no schema-validated delegation between agents.
- **No phase gates**: No deterministic pass/fail at boundaries; failures surface in app logic.
- **No provenance continuity**: Checksum/schema continuity across export → ingest → implement is not modeled.
- **Audit gap**: Cross-agent handoffs lack standardized, queryable evidence.

### 3) What to Model in ContextCore (Inspired by LangGraph, Non-Duplicative)

| Inspiration | ContextCore Addition | Rationale |
|-------------|----------------------|-----------|
| Checkpoint/state snapshot | `checkpoint_id` span attribute; optional `state_snapshot_hash` for integrity | Correlate spans with LangGraph checkpoints; enable "resume from span" traceability |
| Node/edge identity | `graph.node`, `graph.edge` span attributes | Query "which node failed" in TraceQL without rebuilding graph |
| Conditional edge outcome | `GateResult`-like event at each routing decision | Audit why execution took path A vs B; governance, not routing |
| Parallel branch merge | Span hierarchy: parent = merge point, children = parallel branches | Existing span model; document convention for LangGraph `add_edges` |

**Do not add**: Graph execution engine, state machine runtime, checkpoint storage.

### 4) Quick Wins (1–2 Weeks)

- Add semantic convention for `graph.node`, `graph.edge`, `graph.checkpoint_id` in `docs/semantic-conventions.md`.
- Publish `docs/integrations/LANGGRAPH_PATTERN.md`: emit `TaskSpanContract` at node entry, `GateResult` at conditional-edge decisions, nest child spans per node.
- Extend `TaskSpanContract` (or span attributes) with optional `checkpoint_id` for checkpoint correlation.

### 5) All-Upside / Low-Downside Actions (Do Immediately)

- Document LangGraph integration pattern in `LANGCHAIN_VS_CONTEXTCORE_A2A_GUIDE.md` (LangGraph is LangChain-adjacent).
- Add `contextcore.graph.checkpoint_id` and `contextcore.graph.node` to agent semantic conventions.
- No code changes required for core contracts; attribute additions only.

---

## AutoGen

### 1) Strengths vs ContextCore

- **Conversational multi-agent**: Turn-based agent chat; natural fit for human-in-the-loop. ContextCore is task-centric.
- **Event-driven (v0.4)**: Async, event-driven architecture; broader agentic scenarios. ContextCore handoffs are request-response oriented.
- **Built-in OTel support**: AutoGen v0.4 ships with OpenTelemetry. ContextCore can nest cleanly if conventions align.
- **AutoGen Studio**: No-code prototyping. ContextCore has no equivalent.
- **Cross-language**: Python + .NET. ContextCore is Python-first.
- **AgentChat + Core + Extensions**: Modular; pluggable components. ContextCore is SDK + contracts.

### 2) Weaknesses vs ContextCore

- **Conversation-centric vs task-centric**: Turns are not modeled as governed tasks; no `TaskSpanContract` at turn boundaries.
- **No HandoffContract**: Agent-to-agent messages lack schema validation and versioning.
- **No GateResult**: No typed pass/fail at boundaries; guardrails are app-level.
- **Event model is runtime**: Events drive execution; governance semantics (who, what, when, why) are not first-class.
- **No artifact-as-task policy**: Artifact promotion and traceability are ad hoc.

### 3) What to Model in ContextCore (Inspired by AutoGen, Non-Duplicative)

| Inspiration | ContextCore Addition | Rationale |
|-------------|----------------------|-----------|
| Agent role | `agent.role` span attribute (e.g. `assistant`, `user`, `code_executor`) | Query by role in TraceQL; governance visibility |
| Conversation turn | `conversation.turn_id` or `handoff.correlation_id` | Link HandoffContract to AutoGen turn for audit |
| Event types | Governance taxonomy: map AutoGen event types to ContextCore `insight.type` or span events | Only governance-relevant events; avoid noise |
| Human-in-the-loop | `HandoffStatus.INPUT_REQUIRED` (already exists) | Align with AutoGen human proxy pattern |

**Do not add**: Event bus, conversation runtime, AutoGen Studio equivalent.

### 4) Quick Wins (1–2 Weeks)

- Add `agent.role` and `conversation.turn_id` to semantic conventions.
- Write `docs/integrations/AUTOGEN_PATTERN.md`: emit `HandoffContract` when delegating to another agent; use `INPUT_REQUIRED` when human input needed; nest spans per agent turn.
- Verify OTel attribute nesting: ensure ContextCore spans/attributes do not conflict with AutoGen’s OTel schema.

### 5) All-Upside / Low-Downside Actions (Do Immediately)

- Audit AutoGen v0.4 OTel schema; document attribute overlap and namespacing in `docs/OTEL_GENAI_MIGRATION_GUIDE.md` or new `docs/integrations/OTEL_FRAMEWORK_ALIGNMENT.md`.
- Add `agent.role` to `docs/agent-semantic-conventions.md`.
- Extend `HandoffContract` docs to show AutoGen delegation pattern (optional `correlation_id` for turn linkage).

---

## CrewAI

### 1) Strengths vs ContextCore

- **Role-based agents**: Explicit roles (e.g. researcher, writer); clear responsibility. ContextCore has `agent_id` but not role semantics.
- **Crews + hierarchy**: Crew = team of agents; hierarchical/sequential execution. ContextCore spans nest but crew semantics are implicit.
- **Flows**: start/listen/router; state persistence; resumable. ContextCore has phases but no flow-step abstraction.
- **Guardrails**: Built-in guardrails. ContextCore has `GateResult`; CrewAI guardrails are runtime, not governance schema.
- **Enterprise integrations**: Slack, Gmail, Salesforce, etc. ContextCore has fewer prebuilt integrations.
- **Memory + knowledge bases**: Agent memory and RAG. ContextCore has insights; different use case.
- **Lightweight, LangChain-free**: 100% independent. ContextCore is also runtime-agnostic.

### 2) Weaknesses vs ContextCore

- **No contract schema**: No `HandoffContract`, `GateResult`, or `ArtifactIntent`; coordination is implicit.
- **Flows are runtime**: Flow steps are execution, not governance boundaries.
- **Crew hierarchy implicit**: Parent-child relationships exist but are not queryable as governance primitives.
- **No provenance/checksum**: Artifact continuity and integrity are not modeled.
- **Guardrails not auditable**: Pass/fail is internal; no `GateResult` for traceability.

### 3) What to Model in ContextCore (Inspired by CrewAI, Non-Duplicative)

| Inspiration | ContextCore Addition | Rationale |
|-------------|----------------------|-----------|
| Crew hierarchy | `crew.id`, `crew.role` span attributes; parent span = crew, children = agents | Query "which crew/role failed" in TraceQL |
| Flow steps | Map flow steps to `TaskSpanContract` phases; emit at step boundaries | Governance visibility without rebuilding flow runtime |
| Guardrail outcomes | Emit `GateResult` when CrewAI guardrail fires (pass/fail, reason) | Audit guardrail decisions; fail-fast visibility |
| Role | `agent.role` (align with AutoGen) | Consistent across frameworks |

**Do not add**: Flow runtime, crew orchestration, memory/knowledge systems.

### 4) Quick Wins (1–2 Weeks)

- Add `crew.id`, `crew.role`, `flow.step` to semantic conventions.
- Write `docs/integrations/CREWAI_PATTERN.md`: emit `TaskSpanContract` at flow step boundaries; emit `GateResult` when guardrails run; use span hierarchy for crew → agent.
- Add optional `crew_id` to `HandoffContract` for crew-scoped delegation.

### 5) All-Upside / Low-Downside Actions (Do Immediately)

- Add `crew.id`, `crew.role`, `flow.step` to `docs/agent-semantic-conventions.md`.
- Document CrewAI integration: "At each flow step boundary, emit TaskSpanContract; at each guardrail check, emit GateResult."
- No contract schema changes; attribute additions only.

---

## Summary: Non-Duplicative Recommendations

| Framework | Key ContextCore Additions | Avoid |
|-----------|---------------------------|-------|
| **LangGraph** | `graph.node`, `graph.edge`, `graph.checkpoint_id`; integration doc | Graph engine, checkpoint storage |
| **AutoGen** | `agent.role`, `conversation.turn_id`; OTel alignment doc | Event bus, conversation runtime |
| **CrewAI** | `crew.id`, `crew.role`, `flow.step`; integration doc | Flow runtime, crew orchestration |

**Unified quick win**: Single `docs/integrations/` directory with one pattern doc per framework, plus a shared `docs/agent-semantic-conventions.md` update that adds `agent.role`, `crew.id`, `crew.role`, `flow.step`, `graph.node`, `graph.edge`, `graph.checkpoint_id` in one pass.
