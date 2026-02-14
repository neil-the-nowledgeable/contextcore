# Semantic Kernel vs ContextCore

## Strengths and weaknesses (both)

### Semantic Kernel strengths (its realm: enterprise orchestration platform)
- Strong plugin/function abstraction and enterprise integration posture.
- Good multi-language story and structured orchestration patterns.
- Practical for organizations standardizing on Microsoft ecosystems.

### Semantic Kernel weaknesses (relative to governance)
- Governance semantics across multi-stage pipelines are not the main abstraction.
- Contract-first cross-agent boundary validation is not the default operating model.
- Project-level task-as-span visibility requires additional modeling.

### ContextCore strengths (its realm: governance + observability)
- Native task lifecycle observability via spans and events.
- Typed handoff and gate contracts for boundary correctness.
- Strong provenance/checksum orientation for execution integrity.

### ContextCore weaknesses (relative to runtime ergonomics)
- Less turnkey enterprise runtime abstractions than Semantic Kernel.
- Requires clearer integration templates for plugin-heavy ecosystems.

## What to model in ContextCore (without duplicating Semantic Kernel)
- Capability registry semantics (governance metadata only): capability id, owner, risk tier, required gates.
- Orchestrator-role span conventions (`agent.type=orchestrator`).
- Capability-level SLOs (handoff success, gate pass rates, mean time to unblock).

## Quick wins (1-2 weeks)
- Publish Semantic Kernel integration pattern doc.
- Add capability metadata conventions to semantic docs.
- Add orchestrator trace query pack (failed capabilities, retry hotspots).

## All-upside / low-downside actions (do now)
- Add capability registry as documentation + schema, not runtime dispatcher.
- Add orchestrator role conventions immediately.
- Keep execution runtime in Semantic Kernel; use ContextCore for control-plane evidence.

