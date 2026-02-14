# LlamaIndex vs ContextCore

## Strengths and weaknesses (both)

### LlamaIndex strengths (its realm: data/RAG orchestration)
- Strong ingestion/indexing/retrieval abstractions.
- Excellent for data-to-LLM pipelines and retrieval quality work.
- Mature event patterns for retrieval-centric workflows.

### LlamaIndex weaknesses (relative to governance)
- Not primarily a project execution governance system.
- Cross-agent handoff policy and gate semantics are not core primitives.
- Artifact-as-task lifecycle visibility requires extra architecture.

### ContextCore strengths (its realm: governance + observability)
- Strong phase/task governance model across pipeline boundaries.
- Typed contracts make boundary behavior machine-checkable.
- Better suited to cross-stage execution auditability.

### ContextCore weaknesses (relative to data pipeline ergonomics)
- Fewer dedicated RAG ingestion/retrieval abstractions out of the box.
- Less built-in evaluation ergonomics for retrieval quality loops.

## What to model in ContextCore (without duplicating LlamaIndex)
- RAG governance taxonomy attributes: `rag.phase`, `rag.index_id`, `rag.retrieval_mode`.
- Retrieval quality gate semantics (`GateResult` on confidence/coverage thresholds).
- Evidence typing for retrieval artifacts (`evidence.type=retrieval_result`, `index_snapshot`).

## Quick wins (1-2 weeks)
- Add LlamaIndex integration pattern doc with phase mapping.
- Add retrieval-related optional semantic attributes.
- Add one gate bundle for RAG phase transitions.

## All-upside / low-downside actions (do now)
- Add RAG governance attributes as optional conventions.
- Emit gate outcomes for retrieval-to-generation transitions.
- Keep retrieval/runtime mechanics in LlamaIndex; govern boundaries in ContextCore.

