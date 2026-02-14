# Guidance/Outlines/Instructor vs ContextCore

## Strengths and weaknesses (both)

### Guidance/Outlines/Instructor strengths (their realm: structured output reliability)
- Strong schema-constrained generation and typed output patterns.
- Practical for reducing malformed responses and parser failures.
- Useful for local reliability at individual call boundaries.

### Guidance/Outlines/Instructor weaknesses (relative to governance)
- Scope is usually single-call or local flow reliability, not end-to-end governance.
- No native project-level task/subtask execution model.
- Limited cross-agent provenance and lifecycle visibility by default.

### ContextCore strengths (its realm: governance + observability)
- End-to-end lifecycle governance across many calls/agents/stages.
- Explicit boundary contracts and gate decisions with trace evidence.
- Better suited for portfolio-level execution observability.

### ContextCore weaknesses (relative to constrained generation)
- Does not itself provide constrained decoding/runtime output control primitives.
- Depends on external runtimes/libraries for call-level generation constraints.

## What to model in ContextCore (without duplicating these libs)
- Validation-retry event conventions (`validation.retry_count`, `validation.failure_reason`).
- Response schema lineage fields (`gen_ai.response.schema`, `schema.version`).
- Gate semantics for "output structurally valid but operationally inadmissible."

## Quick wins (1-2 weeks)
- Add structured-output integration pattern doc.
- Add optional response-schema and validation-retry attributes.
- Add one query for repeated validation retries before successful handoff.

## All-upside / low-downside actions (do now)
- Keep constrained generation in these libraries; capture governance evidence in ContextCore.
- Add schema lineage attributes to existing semantic conventions.
- Emit `GateResult` when validation retries exceed policy thresholds.

