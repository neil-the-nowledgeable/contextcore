# AutoGen vs ContextCore

## Strengths and weaknesses (both)

### AutoGen strengths (its realm: multi-agent conversation runtime)
- Strong conversational multi-agent collaboration model.
- Good role-based delegation patterns for agent teams.
- Event-rich execution useful for runtime diagnostics.

### AutoGen weaknesses (relative to governance)
- Conversation flow can be clear at runtime but weakly standardized at cross-system boundaries.
- No native contract-first policy for handoff admissibility.
- Limited built-in provenance continuity across external pipeline stages.

### ContextCore strengths (its realm: governance + observability)
- Typed handoffs and gates make delegation decisions auditable.
- Task/subtask spans are operationally queryable across stages.
- Fail-fast gate semantics reduce late-stage surprises.

### ContextCore weaknesses (relative to runtime ergonomics)
- Less built-in conversational orchestration UX than AutoGen.
- Requires explicit contract adoption for full value.

## What to model in ContextCore (without duplicating AutoGen)
- Conversation lineage attributes: `conversation.turn_id`, `agent.role`.
- Standard mapping from AutoGen events -> `GateResult` taxonomy.
- Handoff reliability semantics (timeout/retry/dead-letter reason codes).

## Quick wins (1-2 weeks)
- Add AutoGen mapping guide: `docs/integrations/AUTOGEN_PATTERN.md`.
- Add required reason-code set for failed/blocked handoffs.
- Add trace queries for turn-to-turn blockers and failed delegation edges.

## All-upside / low-downside actions (do now)
- Add optional `agent.role` and `conversation.turn_id` attributes to conventions.
- Enforce schema validation on all handoff ingress/egress.
- Keep AutoGen runtime behavior unchanged; govern acceptance and progression only.

