# Runtime Selection Matrix: ContextCore Benefits for Platform Users

Audience: teams already using agent frameworks (LangGraph, AutoGen, CrewAI, etc.) and evaluating what ContextCore adds.

## How to read this matrix

- **Interoperability effort**: effort to connect your runtime to ContextCore contracts/spans.
- **Governance fit**: how strongly ContextCore improves execution control for that runtime.
- **Observability hooks**: how much runtime telemetry can be elevated into ContextCore operational visibility.
- **Vendor lock-in risk**: risk level in your runtime choice (ContextCore helps mitigate, but cannot remove all lock-in).
- **Migration cost**: cost to add ContextCore governance/observability to existing runtime usage.

---

## Matrix (benefit lens)

|Runtime / Framework|Interoperability effort|Governance fit|Observability hooks|Vendor lock-in risk|Migration cost|ContextCore benefit summary|
|---|---|---|---|---|---|---|
|**LangGraph**|Low|High|High|Low|Medium|Adds contract-validated boundaries, policy gates, and auditable task/subtask spans over graph execution.|
|**AutoGen**|Medium|High|High|Medium|Medium|Adds deterministic handoff governance and failure attribution across conversational multi-agent flows.|
|**CrewAI**|Medium|Medium-High|Medium|Medium|Medium|Adds explicit guardrail-to-gate semantics and operational traceability for role/task flows.|
|**Semantic Kernel**|Medium|High|Medium-High|Medium|Medium-High|Adds cross-stage governance standardization and runtime-agnostic policy evidence on top of enterprise orchestration.|
|**LlamaIndex**|Medium|Medium|Medium-High|Low-Medium|Medium|Adds execution governance across RAG phase boundaries, reducing late-stage failures from implicit handoffs.|
|**Haystack**|Medium|Medium|Medium|Low|Medium-High|Adds policy-driven progression and auditable lifecycle telemetry around pipeline components.|
|**OpenAI Agents SDK**|Low-Medium|Medium|High|High|Low-Medium|Adds portability discipline and control-plane evidence to a vendor-native runtime.|
|**DSPy**|Medium|Medium|Medium|Low-Medium|Medium|Adds governance around optimization promotion decisions and run-to-run audit evidence.|
|**Guidance / Outlines / Instructor**|Medium|Medium|Low-Medium|Low|Low|Adds project-level governance and trace lifecycle around call-level structured output reliability.|

---

## Key benefits ContextCore provides across all platforms

- **Execution governance**: typed handoffs, policy gates, deterministic pass/fail progression.
- **Operational observability**: task/subtask traces tied to real execution lifecycle.
- **Auditability**: provenance/checksum continuity and explicit decision evidence.
- **Interoperability**: contract-first boundaries reduce framework-specific coupling.
- **Controlled scaling**: artifact-as-task promotion rules prevent telemetry noise explosions.

---

## Best first targets for platform teams

- **Fastest value**: LangGraph, AutoGen, CrewAI (high governance uplift with moderate integration effort).
- **Highest lock-in mitigation value**: OpenAI Agents SDK integrations.
- **Highest RAG governance value**: LlamaIndex and Haystack pipelines.
