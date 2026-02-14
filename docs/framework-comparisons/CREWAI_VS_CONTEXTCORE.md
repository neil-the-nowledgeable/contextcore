# CrewAI vs ContextCore

## Strengths and weaknesses (both)

### CrewAI strengths (its realm: role/task workflow runtime)
- Simple role-driven model (agents, tasks, crews) that is easy to adopt.
- Practical for quickly organizing team-of-agents execution.
- Good fit for straightforward workflow delegation.

### CrewAI weaknesses (relative to governance)
- Crew/task runtime structure is not automatically a contract-governed control plane.
- Boundary validation and provenance controls require extra layering.
- Risk of implicit assumptions between steps without strict gate model.

### ContextCore strengths (its realm: governance + observability)
- Explicit task/subtask span hierarchy and lifecycle states.
- Contract-first handoffs with deterministic gate decisions.
- Provenance and quality signals are first-class.

### ContextCore weaknesses (relative to runtime ergonomics)
- Less opinionated runtime UX for crew/role choreography.
- Requires integration patterns to match CrewAI primitives.

## What to model in ContextCore (without duplicating CrewAI)
- Crew lineage attributes: `crew.id`, `crew.role`, `flow.step`.
- Guardrail-to-gate mapping (CrewAI guardrails emit `GateResult`).
- Role accountability policy on blocked spans (`blocked_on_role`, `next_action_owner`).

## Quick wins (1-2 weeks)
- Add CrewAI pattern doc: `docs/integrations/CREWAI_PATTERN.md`.
- Add optional crew/flow attributes to semantic conventions.
- Add blocked-role dashboard slice for pilot traces.

## All-upside / low-downside actions (do now)
- Add crew lineage attributes as optional conventions (no schema breaking changes).
- Require gate emission at guardrail checkpoints.
- Avoid building Crew-style runtime features in ContextCore.

