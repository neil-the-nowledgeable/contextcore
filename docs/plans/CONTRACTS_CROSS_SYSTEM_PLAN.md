# Plan: Cross-System Contracts Gap Closure

> **Date:** 2026-03-16
> **Status:** Draft
> **Scope:** Coordinated work across ContextCore, startd8-sdk, and cap-dev-pipe to close contracts gaps
> **Origin:** [REQ_CONTRACTS_GAP_ANALYSIS.md](../design/requirements/REQ_CONTRACTS_GAP_ANALYSIS.md) (ContextCore), [REQ_CONTRACTS_CONSUMER_GAPS.md](~/Documents/dev/startd8-sdk/docs/design/kaizen/REQ_CONTRACTS_CONSUMER_GAPS.md) (startd8-sdk), [REQ_GOVERNANCE_GATE_GAPS.md](~/Documents/dev/cap-dev-pipe/design/REQ_GOVERNANCE_GATE_GAPS.md) (cap-dev-pipe)
> **Principle:** Close gaps in priority order. Each phase produces a measurable result verifiable by a pipeline run. No phase depends on a later phase.

---

## Current State

10 gaps across 3 systems. No contracts validation runs in any pipeline today.

```
ContextCore                    startd8-sdk                    cap-dev-pipe
───────────                    ───────────                    ────────────
77 files, 17.8 KLOC            8 try/except imports           0 gate invocations
~1.1K essential (types,        All silently fail               REQ-CDP-INT-005
 timeouts, metrics)            (namespace collision)           specifies 2 gates,
~3K A2A CLI (works,                                            neither wired
 never automated)              Forward manifest bindings
~12K dormant layers            return empty for most tasks
```

---

## Target State

```
ContextCore                    startd8-sdk                    cap-dev-pipe
───────────                    ───────────                    ────────────
Essential types retained       Namespace collision resolved    Gate 1 runs after export
Dormant layers archived        Dead imports removed            Gate 2 runs after ingestion
A2A CLI unchanged              Bindings derived from           Override escalation enforced
                               file_specs (not contracts)      Gate results in provenance
```

---

## Phase 1: Clean Up Dead Weight (No Cross-System Dependencies)

**Goal:** Remove accidental complexity. Each system works on its own code independently.

### 1A — ContextCore: Archive Dormant Layers

| Gap | Action | Effort |
|-----|--------|--------|
| GAP-CC-001 | Move Layers 2-7 to `contracts/_dormant/`. Remove from `__init__.py` exports. Keep `types.py`, `timeouts.py`, `metrics.py`, `a2a/`. | ~30 min |

**Verification:** `python3 -m pytest tests/ -x` passes. `from contextcore.contracts.types import TaskStatus` works. `from contextcore.contracts.budget import BudgetValidator` fails with ImportError (expected).

### 1B — startd8-sdk: Remove Dead Imports

| Gap | Action | Effort |
|-----|--------|--------|
| GAP-SDK-004 | Remove dead `HandoffContract`/`HandoffPriority`/`HandoffContractStatus`/`ExpectedOutput` imports from `handoff.py:62-75`. | ~5 min |

**Verification:** `python3 -m pytest tests/unit/test_handoff*.py -x` passes.

### 1C — startd8-sdk: Acknowledge Propagation as Artisan-Only

| Gap | Action | Effort |
|-----|--------|--------|
| GAP-SDK-002 | Add comment block in `context_strategy.py` at `PipelineContextStrategy` documenting that boundary validation is artisan-only by design. No code change. | ~5 min |

**Verification:** N/A (documentation only).

**Phase 1 result:** ~12 KLOC of dormant code archived. Dead imports removed. No behavioral changes. Each system can merge independently.

---

## Phase 2: Fix the Data Path (startd8-sdk → LLM Prompts)

**Goal:** Make the constraint injection mechanism produce useful output. This is the highest-impact gap (P2) — it directly affects code generation quality.

### 2A — startd8-sdk: Derive Bindings from file_specs Instead of Contracts

| Gap | Action | Effort |
|-----|--------|--------|
| GAP-SDK-003 | In `context_resolution.py` and/or `drafter.py`, replace `binding_constraints_for_task()` with a function that extracts import modules and base classes from `file_specs.elements[].bases` for the task's dependencies. | ~50 lines |

This directly addresses the proto import hallucination root cause identified in the [Cross-Cutting Context Loss Analysis](~/Documents/dev/startd8-sdk/docs/design/kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md).

**Complements:** The `service_communication_graph` work (REQ-SIG-200/201) provides the same information from a different source (plan text vs forward manifest). Both paths should converge — use whichever is available.

**Verification:** Re-run online-boutique pipeline (run-055). PI-004 and PI-007 generate `import demo_pb2` instead of hallucinated paths.

**Phase 2 result:** LLM prompts receive correct import context. Proto import hallucination eliminated for dependent tasks.

---

## Phase 3: Wire Governance Gates (cap-dev-pipe ← ContextCore CLI)

**Goal:** Make the A2A governance gates run automatically. Depends on ContextCore CLI being available (it already is in the pipeline environment).

### 3A — cap-dev-pipe: Wire Gate 1 After Stage 4

| Gap | Action | Effort |
|-----|--------|--------|
| GAP-CDP-001 | Add `contextcore contract a2a-check-pipeline "$OUTPUT_DIR"` call to `run-cap-delivery.sh` after Stage 4 success. Fail pipeline on non-zero exit. | ~10 lines |

### 3B — cap-dev-pipe: Wire Gate 2 After Stage 5

| Gap | Action | Effort |
|-----|--------|--------|
| GAP-CDP-002 | Add `contextcore contract a2a-diagnose "$OUTPUT_DIR"` call to `run-plan-ingestion.sh` after ingestion success. Fail pipeline on non-zero exit. | ~10 lines |

### 3C — cap-dev-pipe: Add Quality Override Escalation

| Gap | Action | Effort |
|-----|--------|--------|
| GAP-CDP-003 | When `--no-strict-quality` is active, Gate 1 outputs bypassed checks and prompts for confirmation (`read -p`) before proceeding to Gate 2. | ~15 lines |

### 3D — cap-dev-pipe: Persist Gate Results to Provenance

| Gap | Action | Effort |
|-----|--------|--------|
| GAP-CDP-004 | Append Gate 1 and Gate 2 JSON results to `run-provenance.json`. Update `run-metadata.json` with gate timestamps. | ~20 lines |

**Verification:** Run pipeline end-to-end. Confirm:
1. Gate 1 appears between Stage 4 and Stage 5 in output
2. Gate 2 appears between Stage 5 and Stage 6
3. `run-provenance.json` contains gate results
4. `contextcore contract a2a-pilot --source-checksum sha256:BAD` causes Gate 1 to fail and pipeline stops

**Phase 3 result:** Pipeline has automated quality gates matching REQ-CDP-INT-005 specification.

---

## Phase 4: Resolve Namespace Collision (Optional)

**Goal:** Eliminate the `No module named 'contextcore.contracts'` warning. This is P3 — low impact since all consumers have fallbacks, but it enables optional contract validation if desired.

### 4A — startd8-sdk: Resolve Namespace Package Collision

| Gap | Action | Effort |
|-----|--------|--------|
| GAP-SDK-001 | **Option A (minimal):** Add `pip3 install -e ~/Documents/dev/ContextCore` to startd8-sdk venv setup docs and Makefile. **Option B (permanent):** Move `src/contextcore/generators/` to `src/startd8/contextcore_generators/` and update imports. | A: ~5 min, B: ~30 min |

**Verification:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/.venv/bin/python3 -c "from contextcore.contracts.types import TaskStatus; print(TaskStatus.TODO)"` succeeds.

**Phase 4 result:** Warning eliminated. 8 integration points activate. Propagation boundary validation runs on artisan route.

---

## Dependency Graph

```
Phase 1A (ContextCore)  ──┐
Phase 1B (startd8-sdk)  ──┤── All independent, no dependencies
Phase 1C (startd8-sdk)  ──┘

Phase 2A (startd8-sdk)  ──── Independent (highest impact)

Phase 3A (cap-dev-pipe) ──┐
Phase 3B (cap-dev-pipe) ──┤── 3C depends on 3A
Phase 3C (cap-dev-pipe) ──┤── 3D depends on 3A + 3B
Phase 3D (cap-dev-pipe) ──┘

Phase 4A (startd8-sdk)  ──── Independent (optional)
```

**Phases 1, 2, 3, and 4 are independent of each other.** They can be executed in any order or in parallel. Within Phase 3, the sub-steps have a partial ordering (3C→3A, 3D→3A+3B).

---

## Effort Summary

| Phase | System | Lines Changed | Estimated Effort |
|-------|--------|---------------|-----------------|
| 1A | ContextCore | ~50 (moves + __init__ edit) | 30 min |
| 1B | startd8-sdk | ~15 (remove dead imports) | 5 min |
| 1C | startd8-sdk | ~5 (comment block) | 5 min |
| 2A | startd8-sdk | ~50 (file_specs binding derivation) | 1–2 hours |
| 3A | cap-dev-pipe | ~10 (Gate 1 shell) | 15 min |
| 3B | cap-dev-pipe | ~10 (Gate 2 shell) | 15 min |
| 3C | cap-dev-pipe | ~15 (override escalation) | 15 min |
| 3D | cap-dev-pipe | ~20 (provenance persistence) | 30 min |
| 4A | startd8-sdk | ~5–30 (namespace fix) | 5–30 min |
| **Total** | **3 systems** | **~180–210 lines** | **~3–5 hours** |

---

## Success Criteria

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | No `ContextCore Layer 5 validation unavailable` warning in pipeline runs | Run pipeline, grep logs (Phase 4) |
| 2 | PI-004 and PI-007 generate correct proto imports | Run online-boutique pipeline, inspect generated code (Phase 2) |
| 3 | Gate 1 and Gate 2 appear in pipeline output | Run pipeline end-to-end (Phase 3) |
| 4 | Pipeline stops on Gate 1 failure | Inject bad checksum, confirm pipeline halts (Phase 3) |
| 5 | `run-provenance.json` contains gate results | Inspect provenance after run (Phase 3) |
| 6 | `from contextcore.contracts.budget import BudgetValidator` raises ImportError | Verify dormant layers archived (Phase 1) |
| 7 | Existing test suites pass in all 3 systems | `pytest` in each repo (all phases) |

---

## What This Plan Does NOT Cover

- **Integrating dormant Layers 2-7** — archived, not deleted. If a consumer emerges, they can be restored from `contracts/_dormant/`.
- **Prime route boundary validation** — acknowledged as artisan-only (GAP-SDK-002). Prime has different validation needs.
- **Typed handoff contracts** — dead imports removed (GAP-SDK-004). REQ-CID P2 004-006 can re-add when needed.
- **Service communication graph consumption** (REQ-SIG-200/201) — covered by [separate plan](~/Documents/dev/startd8-sdk/docs/design/kaizen/SERVICE_COMMUNICATION_GRAPH_CONSUMPTION_REQUIREMENTS.md). Phase 2A complements it.
