# Runtime Selection Matrix: Platform Choices for ContextCore Users

Audience: teams already committed to ContextCore governance/observability deciding which runtime platform(s) to use.

## How to read this matrix

- **Interoperability effort**: effort to map runtime events/states into ContextCore contracts.
- **Governance fit**: how cleanly runtime behavior can be governed via ContextCore policies.
- **Observability hooks**: quality of runtime signals available to enrich ContextCore traces.
- **Vendor lock-in risk**: portability risk introduced by the runtime.
- **Migration cost**: cost for a ContextCore-based team to adopt this runtime.

---

## Matrix (ContextCore user lens)

|Runtime / Framework|Interoperability effort|Governance fit|Observability hooks|Vendor lock-in risk|Migration cost|ContextCore user guidance|
|---|---|---|---|---|---|---|
|**LangGraph**|Low|High|High|Low|Medium|Best default primary runtime for governance-first teams; aligns naturally with phase/gate control.|
|**AutoGen**|Medium|High|High|Medium|Medium|Strong secondary option for conversational multi-agent use cases with explicit handoff governance overlays.|
|**CrewAI**|Medium|Medium-High|Medium|Medium|Medium|Good for role-based workflows if guardrails are mapped to gate semantics early.|
|**Semantic Kernel**|Medium|High|Medium-High|Medium|Medium-High|Good enterprise choice when ecosystem alignment matters; keep ContextCore as neutral governance layer.|
|**LlamaIndex**|Medium|Medium|Medium-High|Low-Medium|Medium|Strong for RAG-heavy systems; pair with strict RAG phase gate policies in ContextCore.|
|**Haystack**|Medium|Medium|Medium|Low|Medium-High|Viable for pipeline-centric teams; requires clear component-to-span mapping templates.|
|**OpenAI Agents SDK**|Low-Medium|Medium|High|High|Low-Medium|Use selectively for speed; enforce strict contract normalization to preserve portability.|
|**DSPy**|Medium|Medium|Medium|Low-Medium|Medium|Use as optimization companion, not orchestration core; govern promotion decisions via ContextCore gates.|
|**Guidance / Outlines / Instructor**|Medium|Medium|Low-Medium|Low|Low|Use as constrained-output layer beneath ContextCore governance, not as runtime orchestrator.|

---

## Recommended strategy for ContextCore users

### Primary runtime baseline

- **LangGraph** as the default orchestration runtime for most governance-first workloads.

### Secondary specialized runtimes

- **AutoGen** for conversational multi-agent collaboration patterns.
- **LlamaIndex/Haystack** for retrieval-centric execution segments.
- **OpenAI Agents SDK** for selective platform acceleration where lock-in is acceptable.

### Companion (not replacement) tools

- **DSPy** for optimization loops.
- **Guidance/Outlines/Instructor** for structured output reliability at call boundaries.

---

## No-regret platform adoption rules for ContextCore teams

- Normalize all runtime boundaries into ContextCore contracts.
- Enforce gate decisions before phase transitions regardless of runtime.
- Keep runtime-specific fields out of core contracts; map them in adapters.
- Prioritize query/alert value before adding new telemetry fields.
- Keep ContextCore as control plane; never fork into runtime duplication.
