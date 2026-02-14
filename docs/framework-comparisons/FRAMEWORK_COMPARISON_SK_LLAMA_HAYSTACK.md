# Framework Comparison: Semantic Kernel, LlamaIndex, Haystack vs ContextCore

Implementation-oriented comparison for execution governance and observability. ContextCore focuses on **governance + observability**; these frameworks focus on **runtime orchestration**. Recommendations avoid duplicating orchestration.

---

## Semantic Kernel

### 1. Strengths vs ContextCore

- **Plugin registry model**: Declarative plugin/capability registration with semantic descriptions; kernel discovers capabilities at runtime.
- **Multi-language support**: C#, Python, Java—ContextCore is Python-only.
- **Enterprise-ready**: Microsoft-backed, v1.0+, security filters, telemetry hooks.
- **Built-in OTel**: Logging, metrics, traces; aligns with OTel GenAI conventions.
- **Orchestrator pattern**: Central orchestrator + specialized agent plugins with clear aggregation semantics.

### 2. Weaknesses vs ContextCore

- **No project/task model**: No tasks-as-spans; no project health, SLO, or business context.
- **No agent insights**: No persistent queryable store for decisions/lessons.
- **No handoff contracts**: Tool calls are ad-hoc; no schema-validated, versioned handoffs.
- **No phase gates**: No explicit gate semantics (pass/fail, severity, next action).
- **Vendor coupling**: Microsoft ecosystem; ContextCore is OTLP/vendor-agnostic.

### 3. What to Model in ContextCore (inspired by SK)

| Model | Description |
|-------|-------------|
| **Plugin capability manifest** | Extend `skill` manifest with `capability_id` + semantic description; emit as span attributes for TraceQL discovery. |
| **Orchestrator span type** | Add `agent.type = "orchestrator"` semantics; emit parent span when delegating to sub-agents. |
| **Capability routing table** | Publish skill→capability routing as OTel resource attributes; enable O(1) lookup without runtime SK. |

### 4. Quick Wins (1–2 weeks)

- Add `skill.capability.description` attribute to existing skill emit; align with SK’s semantic plugin descriptions.
- Document TraceQL patterns for discovering capabilities by agent (e.g., `{ agent.id = "X" && name =~ "skill:.*" }`).
- Add `agent.type = "orchestrator"` to semantic conventions; emit when handoff spans are created by a parent agent.

### 5. All-Upside / Low-Downside Actions

- [ ] **Publish capability registry schema**: Add `docs/capability-registry-schema.md` describing how skill manifests map to TraceQL-queryable spans; no runtime SK dependency.
- [ ] **Emit `capability_id` on handoff spans**: Already present; ensure it’s in `gen_ai.tool.name` mapping for OTel GenAI compatibility.
- [ ] **Add orchestrator example**: Add `examples/04_orchestrator_handoff.py` showing parent span → child handoff spans with `agent.type` propagation.

---

## LlamaIndex

### 1. Strengths vs ContextCore

- **RAG-specific observability**: Events for indexing, retrieval, embedding, LLM; one-click OTel/Langfuse.
- **Event-driven workflow**: Steps, events, workflow class; clear lifecycle for RAG pipelines.
- **Instrumentation module**: `set_global_handler()` for minimal-config observability.
- **Rich event taxonomy**: QueryStartEvent, RetrievalStartEvent, EmbeddingStartEvent, LLMChatStartEvent, etc.
- **OpenInference**: Community standard for LLM instrumentation; ContextCore can align.

### 2. Weaknesses vs ContextCore

- **No project/task model**: No tasks-as-spans; no project health or SLO derivation.
- **No agent insights**: No persistent decisions/lessons; no guidance or handoff contracts.
- **RAG-centric**: Optimized for retrieval and indexing; not for project governance or artifact tracking.
- **Callback-based**: Legacy handlers; instrumentation module is newer; ContextCore uses spans-first.
- **No business context**: No criticality, ownership, or SLO propagation in observability.

### 3. What to Model in ContextCore (inspired by LlamaIndex)

| Model | Description |
|-------|-------------|
| **RAG pipeline phases** | Treat indexing/retrieval/embedding as distinct phases; emit as span attributes (`phase = "index"` / `"retrieve"` / `"embed"`) for governance. |
| **Event taxonomy** | Add `event.type` to span events for common AI operations (e.g., `retrieval_start`, `query_start`); enables TraceQL without LlamaIndex. |
| **Instrumentation contract** | Document how external frameworks (LlamaIndex, LangChain) can emit ContextCore-compatible spans via OTel or custom handlers. |

### 4. Quick Wins (1–2 weeks)

- Add `phase` attribute to span events: `index`, `retrieve`, `embed`, `query` for RAG-style pipelines.
- Add `docs/INTEGRATION_LLAMAINDEX.md`: One-page guide for LlamaIndex + ContextCore (OTel handler → Tempo spans).
- Extend `insight.type` with `retrieval` or `query` for RAG-style agent insights when applicable.

### 5. All-Upside / Low-Downside Actions

- [ ] **Publish integration contract**: Add `docs/INTEGRATION_CONTRACT.md` for frameworks that want to emit ContextCore-compatible spans (required attributes, event types).
- [ ] **Add `event.type` to semantic conventions**: Document `retrieval_start`, `query_start`, `embedding_start` as optional event types.
- [ ] **Emit `phase` on task spans**: When task type is RAG-related, add `phase` attribute; no schema change.

---

## Haystack

### 1. Strengths vs ContextCore

- **Pipeline graph model**: Directed multigraphs; branching, loops, typed data flow.
- **Component I/O validation**: Typed inputs/outputs before pipeline execution.
- **Document/Answer data classes**: Structured data flow through pipelines.
- **LoggingTracer**: Built-in tracing for prototyping without backend.
- **Langfuse/OpenInference**: Integrations for tracing; Haystack auto-detects OTel config.

### 2. Weaknesses vs ContextCore

- **No project/task model**: No tasks-as-spans; no project health or SLO derivation.
- **No agent insights**: No persistent decisions/lessons; no guidance or handoff contracts.
- **Pipeline-centric**: Optimized for document processing; not for project governance.
- **Content tracing opt-in**: `HAYSTACK_CONTENT_TRACING_ENABLED` required; ContextCore is span-first by default.
- **No business context**: No criticality, ownership, or SLO propagation.

### 3. What to Model in ContextCore (inspired by Haystack)

| Model | Description |
|-------|-------------|
| **Pipeline graph topology** | Emit `pipeline.component` and `pipeline.edge` as span attributes for multi-step flows; enables TraceQL for branching/loop detection. |
| **Component I/O schema** | Add optional `handoff.input_schema` / `handoff.output_schema` to HandoffContract; validate at boundaries without Haystack runtime. |
| **Include-outputs pattern** | Add `span.include_outputs_from`-style attribute for governance spans that reference which components produced outputs. |

### 4. Quick Wins (1–2 weeks)

- Add `pipeline.component` attribute to handoff spans when delegating to a pipeline step; enables TraceQL for pipeline topology.
- Add optional `input_schema` / `output_schema` to `HandoffContract` (Pydantic); validate at handoff without runtime Haystack.
- Add `docs/INTEGRATION_HAYSTACK.md`: One-page guide for Haystack + ContextCore (LangfuseConnector or OTel → Tempo).

### 5. All-Upside / Low-Downside Actions

- [ ] **Add `pipeline.component` to semantic conventions**: Optional attribute for handoffs that represent pipeline steps.
- [ ] **Document HandoffContract schema validation**: Add `input_schema` / `output_schema` as optional JSON Schema refs; validate in `handoff.create()`.
- [ ] **Add pipeline topology example**: Document TraceQL for `{ pipeline.component = "retriever" }` or `{ handoff.capability_id = "retrieve" }` patterns.

---

## Summary: Non-Duplicative Actions

| Action | Framework | Effort |
|--------|-----------|--------|
| Publish capability registry schema | SK | 1 day |
| Add `agent.type = "orchestrator"` to conventions | SK | 1 day |
| Add `event.type` / `phase` to conventions | LlamaIndex | 1 day |
| Publish integration contract | LlamaIndex | 2 days |
| Add `pipeline.component` to conventions | Haystack | 1 day |
| Add `input_schema` / `output_schema` to HandoffContract | Haystack | 2 days |

**Do not** build: plugin runtime, RAG pipeline, or document pipeline orchestration. ContextCore stays governance + observability.
