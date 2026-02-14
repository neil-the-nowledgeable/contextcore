# Framework Comparison Notes: ContextCore vs Agent/LLM Frameworks

Implementation-oriented comparison for **execution governance + observability** positioning. ContextCore does not duplicate runtime orchestration—it observes and governs it.

---

## 1. OpenAI Agents SDK / Assistants-Style Stacks

*OpenAI Agents SDK, Responses API, Assistants API v2, LangGraph, AutoGen, CrewAI, etc.*

### Strengths vs ContextCore

- **Built-in tracing**: Native trace spans for tool calls, handoffs, and LLM steps; ContextCore must instrument from outside
- **Conversation state**: First-class thread/conversation persistence; ContextCore has session_id but no built-in state compaction
- **Handoff primitives**: SDK-level `handoff` between agents with typed inputs/outputs; ContextCore's HandoffManager is storage-backed, not runtime-integrated
- **Tool execution visibility**: Tool name, args, result in trace; maps cleanly to `gen_ai.tool.*` attributes
- **Eval/trace grading**: Built-in evaluation hooks; ContextCore has no eval integration

### Weaknesses vs ContextCore

- **Vendor lock-in**: OpenAI-centric; ContextCore is OTLP/vendor-agnostic
- **No business context**: Traces lack `project.id`, `business.criticality`, `epic`; no ProjectContext linkage
- **No human guidance**: No `guidance.*` or `agentGuidance`; agents can't read constraints from CRD/manifest
- **No cross-session insight persistence**: Decisions/lessons don't persist beyond conversation; ContextCore's InsightEmitter/Querier enables memory
- **No artifact correlation**: No linking to commits, PRs, CI; ContextCore derives status from artifacts

### What to Model in ContextCore (Without Duplicating Orchestration)

- **`gen_ai.tool.name` → `handoff.capability_id` mapping**: When an Assistants-style stack invokes a tool that delegates to another agent, emit a handoff span with `gen_ai.tool.name` as capability_id for correlation
- **Conversation/session as span parent**: Emit a parent span per conversation with `gen_ai.conversation.id`; child spans (tool calls, handoffs) link to it
- **Trace grading as insight**: When eval/trace grading runs, emit `insight.type=analysis` with `insight.confidence` from grade; link to trace via `insight.evidence[].type=trace`
- **Routine/chain as task span**: Model deterministic routines (e.g., "classify → route → execute") as a single task span with child spans per step; enables TraceQL `{ task.type = "routine" }`

### Quick Wins (1–2 Weeks)

- Add `gen_ai.conversation.id` to InsightEmitter/HandoffManager spans when caller provides it; document the integration pattern for Assistants SDK users
- Create a small **integration snippet** (10–20 lines) that wraps OpenAI Agents SDK trace callbacks to emit ContextCore spans with `project.id` and `agent.id`; publish in `examples/`
- Add `insight.evidence[].type=eval_grade` and document how to emit insights from trace grading hooks

### All-Upside / Low-Downside Actions (Immediate)

- Extend `gen_ai.*` dual-emit to include `gen_ai.conversation.id` when available (already partially mapped; ensure HandoffManager accepts it)
- Add `project.id` and `business.criticality` to integration snippet so any Assistants user can drop-in and get business context in traces
- Document in `docs/agent-communication-protocol.md`: "Integrating with OpenAI Agents SDK" section with copy-paste callback example

---

## 2. DSPy

*Declarative LLM programming with signatures, modules, optimizers, and metrics.*

### Strengths vs ContextCore

- **Signature semantics**: Input/output roles (e.g., `question` → `answer`) are explicit; ContextCore has no equivalent for "what this step consumes/produces"
- **Optimizer traceability**: BootstrapRS, MIPROv2 produce improved prompts; no built-in way to record "prompt version X outperformed Y" in ContextCore
- **Metric-driven tuning**: Validation metrics drive optimization; ContextCore has no metric-for-prompt-quality story
- **Module composition**: Reusable DSPy modules with clear boundaries; ContextCore spans are flat by default (hierarchy exists but not module semantics)

### Weaknesses vs ContextCore

- **No observability backend**: DSPy runs locally; no OTLP, no Tempo/Loki, no dashboards
- **No cross-run persistence**: Optimizer runs don't persist to a queryable store; ContextCore spans persist in Tempo
- **No business/governance layer**: No ProjectContext, no guidance, no handoff; pure prompt engineering
- **No artifact correlation**: No link to commits, PRs, or project tasks

### What to Model in ContextCore (Without Duplicating Orchestration)

- **Signature as span attributes**: When a DSPy module runs, emit `dspy.signature` (or `gen_ai.operation.name`) with input/output field names; enables "which signatures are slowest" queries
- **Optimizer run as task span**: Model each optimizer run (BootstrapRS, MIPROv2) as a task span with `task.type=optimization`; child spans per trial; store `optimizer.name`, `metric.before`, `metric.after` as attributes
- **Prompt version in evidence**: Add `insight.evidence[].type=prompt_version` with `ref` = prompt hash or version ID; link decisions to specific prompt iterations
- **Metric snapshot as span event**: Emit `metric.recorded` event with `metric.name`, `metric.value` when DSPy validator runs; enables derivation of "prompt quality over time" via Loki/Mimir

### Quick Wins (1–2 Weeks)

- Define `task.type=optimization` in semantic conventions; add `optimizer.name`, `metric.before`, `metric.after` attribute spec
- Create **DSPy telemetry hook** (or callback) that emits a span per `dspy.Module.__call__` with signature name and duration; ~30 lines, drop-in for DSPy users
- Add `insight.evidence[].type=prompt_version` to agent-semantic-conventions; document pattern for emitting insights when prompts change

### All-Upside / Low-Downside Actions (Immediate)

- Add `gen_ai.operation.name` = signature/module name to any span when caller provides it (already supported via custom attributes; document the pattern)
- Add `task.type=optimization` to allowed task types in models/tracker; no runtime change, enables future DSPy integration
- One-paragraph "DSPy integration" in `docs/agent-communication-protocol.md` with the callback pattern

---

## 3. Guidance / Outlines / Instructor (Grouped)

*Constrained generation, structured output, Pydantic extraction.*

### Strengths vs ContextCore

- **Output schema as contract**: Pydantic/JSON schema defines expected shape; ContextCore has no "expected output schema" in spans
- **Validation failure as signal**: Instructor retries on validation failure; that retry loop is invisible to ContextCore
- **Constraint type visibility**: Guidance uses regex/grammar/select; Outlines uses JSON schema; none of this appears in telemetry
- **Single-call efficiency**: Guidance/Outlines often replace multi-step prompting; ContextCore sees one span, not the "avoided" chain—no way to attribute cost savings

### Weaknesses vs ContextCore

- **No cross-call context**: Each call is isolated; no project, session, or guidance linkage
- **No insight persistence**: Structured output is consumed and discarded; no `insight.type=decision` when extracting a decision
- **No governance**: No constraints from ProjectContext; agents can't read `agentGuidance` before calling Instructor
- **Retry invisibility**: Validation retries are internal; ContextCore sees only final success/failure, not retry count or failure reason

### What to Model in ContextCore (Without Duplicating Orchestration)

- **Response model as span attribute**: Emit `gen_ai.response.schema` or `structured_output.model` = Pydantic model name when using Instructor; enables "which models fail validation most" queries
- **Validation retry as span event**: When Instructor/Outlines retries, emit `validation.retry` event with `retry.count`, `validation.error`; derive retry-rate metric via Loki
- **Constraint type in attributes**: For Guidance/Outlines, emit `constraint.type` = `regex`|`json_schema`|`grammar`|`pydantic`; helps correlate structure with latency
- **Extracted decision as insight**: When structured output represents a decision (e.g., `ClassificationResult`), optionally emit `insight.type=decision` with `insight.summary` from the result; bridges extraction to ContextCore memory

### Quick Wins (1–2 Weeks)

- Add `validation.retry` span event spec to agent-semantic-conventions; document that Instructor/Outlines integrators should emit it on retry
- Create **Instructor middleware** (or wrapper) that: (1) sets `gen_ai.response.schema` from `response_model.__name__`, (2) emits `validation.retry` on retry, (3) accepts `project.id`/`agent.session_id` for context; ~40 lines
- Add `insight.evidence[].type=structured_output` for linking insights to specific extraction runs

### All-Upside / Low-Downside Actions (Immediate)

- Add `gen_ai.response.schema` (or equivalent) to OTel GenAI compatibility layer when `response_model` is provided; Instructor's `instructor.from_provider()` can pass it through
- Document in semantic conventions: "Structured output frameworks (Instructor, Outlines, Guidance): emit `validation.retry` on retry, `gen_ai.response.schema` for model name"
- Add `constraint.type` as optional attribute in conventions; no code change, enables future Guidance/Outlines instrumentation

---

## Summary: Non-Duplicative Positioning

| Framework                    | ContextCore Adds                                 | ContextCore Does NOT Build                    |
|-----------------------------|---------------------------------------------------|-----------------------------------------------|
| OpenAI Agents/Assistants    | Business context, guidance, cross-session memory  | Conversation state, tool runtime, handoffs    |
| DSPy                        | Observability backend, optimizer traceability     | Signatures, optimizers, metrics                |
| Guidance/Outlines/Instructor| Governance, validation visibility, decisions      | Constrained generation, retry logic, schemas   |

**Principle**: ContextCore observes and governs. Frameworks run; ContextCore records, correlates, and constrains.
