# Plan: Instrumentation Hints Derivation (Revised)

> **Date:** 2026-03-18
> **Status:** Active
> **Requirements:** [REQ_INSTRUMENTATION_CONTRACT_DERIVATION.md](../design/requirements/REQ_INSTRUMENTATION_CONTRACT_DERIVATION.md) (REQ-ICD-100–104, revised)
> **Scope:** ContextCore EXPORT stage — derive `instrumentation_hints` from OTel conventions, communication graph, and artifact manifest
> **Depends on:** Service communication graph (implemented 2026-03-16, commit `da85e34`)
> **Key revision:** Metrics derived from protocol→OTel semantic conventions (always available), NOT from PromQL parsing (data not in artifact parameters). See requirements Section 8 for revision rationale.

---

## Phase 1: Language Detection (REQ-ICD-104)

**File:** `src/contextcore/cli/init_from_plan_ops.py`

Add `_LANGUAGE_PATTERNS` dict and wire language detection into `_extract_service_communication_graph()`, piggybacking on existing per-section scanning. Store as `language` field in graph services dict.

**Tests:** Add to `tests/unit/contextcore/cli/test_service_graph_extraction.py` — 5 tests for Python/Java/Go detection, no-signal fallback, backward compat.

## Phase 2: Convention-Based Metrics + Manifest-Declared Metrics (REQ-ICD-100)

**File:** New `src/contextcore/utils/instrumentation.py`

Two metric sources:
1. **Convention-based:** Map protocol → OTel semantic convention metric names (gRPC → `rpc.server.duration` etc.; HTTP → `http.server.duration` etc.). Always available when communication graph exists.
2. **Manifest-declared:** Read `semantic_conventions.metrics` from artifact manifest (when populated).

No PromQL parsing (REQ-ICD-100a deferred to V2).

## Phase 3: Traces from Communication Graph (REQ-ICD-101)

**File:** Same `src/contextcore/utils/instrumentation.py`

Map services to trace span requirements: gRPC → server + client spans with `rpc.*` attributes. HTTP → server span with `http.*` attributes. W3C propagation default.

## Phase 4: SDK Resolution (REQ-ICD-102)

**File:** Same `src/contextcore/utils/instrumentation.py`

Static mapping table: 5 languages × (SDK + interceptor + exporter). Unknown language → omit section.

## Phase 5: Assembly + Emission (REQ-ICD-103)

**File:** `src/contextcore/utils/onboarding.py` (wiring only)

Compose per-service hints from Phases 2-4. Emit as `instrumentation_hints` in onboarding metadata. Target/service granularity bridging. Profile-agnostic.

**Tests:** New `tests/unit/contextcore/utils/test_instrumentation.py` — full suite.

---

## Dependency Graph

```
Phase 1 (language) ──→ Phase 4 (SDK) ──┐
Phase 2 (metrics)  ─────────────────────┤──→ Phase 5 (assembly)
Phase 3 (traces)   ─────────────────────┘
```
