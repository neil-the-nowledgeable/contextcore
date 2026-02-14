# LangGraph vs ContextCore

## Strengths and weaknesses (both)

### LangGraph strengths (its realm: runtime orchestration)
- Strong state-machine/graph execution model for complex agent control flow.
- Durable checkpoints and resumability for long-running workflows.
- Clear node/edge semantics for branching and loops.

### LangGraph weaknesses (relative to governance)
- Handoff boundaries are usually implementation-specific, not contract-standardized.
- No built-in project-level task/subtask governance semantics.
- Provenance and policy gating require additional architecture.

### ContextCore strengths (its realm: governance + observability)
- Task/subtask lifecycle as spans with parent-child traceability.
- Typed contracts and phase gates for deterministic progression.
- Strong provenance/checksum-centric execution controls.

### ContextCore weaknesses (relative to runtime ergonomics)
- Less turnkey graph authoring ergonomics than LangGraph.
- Smaller runtime integration surface out of the box.

## What to model in ContextCore (without duplicating LangGraph)
- Graph lineage attributes: `graph.node`, `graph.edge`, `graph.checkpoint_id`.
- Gate policies at graph transition points (emit `GateResult` on edge decisions).
- Checkpoint governance metadata (who approved resume, under what policy).

## Quick wins (1-2 weeks)
- Add LangGraph interoperability conventions to `docs/agent-semantic-conventions.md`.
- Add integration guide: `docs/integrations/LANGGRAPH_PATTERN.md` (mapping node/edge -> task spans and gates).
- Add default gate checks for branch transitions (checksum/schema/gap parity).

## All-upside / low-downside actions (do now)
- Add graph lineage attributes as optional span fields.
- Document one canonical LangGraph -> ContextCore mapping example.
- Keep LangGraph runtime execution untouched; govern only boundaries and evidence.

