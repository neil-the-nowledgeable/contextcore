# Haystack vs ContextCore

## Strengths and weaknesses (both)

### Haystack strengths (its realm: production NLP/RAG pipelines)
- Strong pipeline composition for retrieval and QA workloads.
- Mature orientation to productionized search-style systems.
- Useful evaluation and component-level structure for data workflows.

### Haystack weaknesses (relative to governance)
- Pipeline control is strong, but cross-agent governance contracts are not the core focus.
- Task/subtask lifecycle observability is not the primary abstraction.
- Provenance continuity across non-Haystack stages needs added controls.

### ContextCore strengths (its realm: governance + observability)
- Cross-system execution governance with typed contracts.
- Task/subtask span hierarchy is strong for operational oversight.
- Better fit for policy-driven go/no-go decisions at stage boundaries.

### ContextCore weaknesses (relative to RAG pipeline ergonomics)
- Less built-in pipeline component ecosystem for retrieval-heavy apps.
- Requires integration patterns to map Haystack pipeline nodes to governance spans.

## What to model in ContextCore (without duplicating Haystack)
- Pipeline lineage attributes: `pipeline.id`, `pipeline.component`, `pipeline.step`.
- Component boundary `GateResult` semantics (input/output schema checks, quality thresholds).
- Topology evidence references (`evidence.type=pipeline_topology`).

## Quick wins (1-2 weeks)
- Add Haystack integration pattern doc.
- Add optional pipeline lineage attributes to conventions.
- Add pipeline component gate templates for pilot path.

## All-upside / low-downside actions (do now)
- Start with lineage attributes and gate emission only.
- Reuse existing contracts; avoid adding runtime pipeline engine logic.
- Add one canonical query for failing pipeline components by phase.

