# Requirements: Contracts Gap Analysis — ContextCore

> **Status:** Assessment
> **Date:** 2026-03-16
> **Author:** Observability Team
> **Scope:** ContextCore's role in the cross-system contracts gap — what's built, what's essential, what's dormant
> **Method:** Static analysis of `contextcore.contracts` module and its consumers
> **Trigger:** `ContextCore Layer 5 validation unavailable: No module named 'contextcore.contracts'` warning in run-054
> **Companion docs:**
> - startd8-sdk: [REQ_CONTRACTS_CONSUMER_GAPS.md](~/Documents/dev/startd8-sdk/docs/design/kaizen/REQ_CONTRACTS_CONSUMER_GAPS.md)
> - cap-dev-pipe: [REQ_GOVERNANCE_GATE_GAPS.md](~/Documents/dev/cap-dev-pipe/design/REQ_GOVERNANCE_GATE_GAPS.md)

---

## 1. Context

ContextCore owns the `contextcore.contracts` module — **77 files (~17.8 KLOC)** organized into 13 contract domains implementing a "7-Layer defense-in-depth" pattern. Two downstream systems consume (or attempt to consume) this module:

- **startd8-sdk** — 8 integration points, all behind `try/except ImportError`
- **cap-dev-pipe** — 0 invocations (gates specified in requirements but never called)

This document covers ContextCore's responsibilities: what it provides, what's essential, and what's dormant.

---

## 2. Essential Components (Keep)

These are actively used by ContextCore's core pipeline and must be maintained:

| File | LOC | Consumers | Role |
|------|-----|-----------|------|
| `contracts/types.py` | 441 | `tracker.py`, `models_v2.py`, weaver | Single source of truth for `TaskStatus`, `TaskType`, `Priority` and 20+ enums |
| `contracts/timeouts.py` | 107 | `core.py`, `tracker.py`, `export_retry.py` | Centralized timeout constants (OTel, HTTP, K8s, subprocess) |
| `contracts/metrics.py` | 633 | `metrics.py` | `MetricName` enum, metric naming conventions |

**Total essential:** ~1.1 KLOC across 3 files.

---

## 3. A2A CLI Commands (Useful, Low Maintenance)

These are invoked only via explicit `contextcore contract` CLI commands. They work correctly but are never called automatically by any pipeline:

| Command | Implementation | What it does |
|---------|---------------|-------------|
| `a2a-check-pipeline DIR` | `contracts/a2a/pipeline_checker.py` | 6 integrity checks on export output |
| `a2a-diagnose DIR` | `contracts/a2a/three_questions.py` | Structured diagnostic framework |
| `a2a-validate CONTRACT payload.json` | `contracts/a2a/validator.py` | JSON schema validation |
| `a2a-gate GATE data.json` | `contracts/a2a/gates.py` | Phase gate checks |
| `a2a-pilot` | `contracts/a2a/pilot.py` | PI-101-002 trace simulation |
| `contract check` | `contracts/a2a/` | Contract drift detection |

**Total:** ~3 KLOC across ~10 files. Well-tested (660 LOC in `tests/test_a2a_contracts.py`).

**Gap:** cap-dev-pipe's REQ-CDP-INT-005 specifies `a2a-check-pipeline` and `a2a-diagnose` as mandatory pipeline gates, but neither `run-cap-delivery.sh` nor `run-plan-ingestion.sh` calls them. See [cap-dev-pipe companion doc](~/Documents/dev/cap-dev-pipe/design/REQ_GOVERNANCE_GATE_GAPS.md).

---

## 4. Dormant Layers (Decision Needed)

### GAP-CC-001: Layers 2-7 Defense-in-Depth Not Integrated

**Severity:** P4
**Scope:** ~12 KLOC across ~58 files

These layers have schema definitions, validators, trackers, loaders, and OTel emitters. None are invoked by any pipeline code, CLI command, or external system.

| Layer | Domain | Files | LOC (est.) | Any Consumer? |
|-------|--------|-------|------------|---------------|
| 1 | `propagation/` | 6 | ~1,500 | startd8-sdk artisan route only (not prime) |
| 2 | `schema_compat/` | 6 | ~800 | None |
| 3 | `semconv/` | 5 | ~700 | None |
| 4 | `ordering/` | 6 | ~800 | None |
| 5 | `capability/` | 6 | ~900 | startd8-sdk tries import, fails (namespace collision) |
| 6 | `budget/` | 6 | ~900 | None |
| 7 | `lineage/` | 6 | ~900 | None |
| - | `preflight/` | 3 | ~400 | None |
| - | `runtime/` | 3 | ~400 | None |
| - | `postexec/` | 3 | ~400 | None |
| - | `observability/` | 4 | ~500 | None |
| - | `regression/` | 4 | ~500 | None |

Additionally dormant in the core contracts:
- `validate.py :: ContractValidator` — exported in `__init__.py`, never called anywhere
- `queries.py :: PromQLBuilder, LogQLBuilder, TraceQLBuilder` — defined, never called

**Options:**

| Option | Effort | Trade-off |
|--------|--------|-----------|
| **A: Archive** to `contracts/_dormant/`, remove from `__init__.py` | Low | Preserves code, reduces import surface, signals intent |
| **B: Delete** | Low | Git history preserves it; cleanest signal |
| **C: Integrate incrementally** | High | Only justified if a consumer is identified |

---

### GAP-CC-002: Propagation Layer Consumer Mismatch

**Severity:** P3

The propagation layer (`contracts/propagation/`) is the most mature contract domain with real integration:
- `BoundaryValidator` and `ContractLoader` are called by startd8-sdk's `context_schema.py`
- `artisan-pipeline.contract.yaml` (722 lines) defines entry/exit requirements
- 7 test files validate boundary behavior

**The mismatch:** This integration only activates on the **artisan route**. All current pipeline runs use the **prime route**, which has no boundary validation. The propagation layer provides value to a route that isn't currently used.

**ContextCore's role:** The propagation layer itself is correct. The gap is in the consumer (startd8-sdk). See [startd8-sdk companion doc](~/Documents/dev/startd8-sdk/docs/design/kaizen/REQ_CONTRACTS_CONSUMER_GAPS.md).

---

## 5. Cross-References

| Document | Relationship |
|----------|-------------|
| [startd8-sdk: REQ_CONTRACTS_CONSUMER_GAPS.md](~/Documents/dev/startd8-sdk/docs/design/kaizen/REQ_CONTRACTS_CONSUMER_GAPS.md) | Gaps 2, 3, 5, 6 — namespace collision, prime route bypass, forward manifest bindings, dead imports |
| [cap-dev-pipe: REQ_GOVERNANCE_GATE_GAPS.md](~/Documents/dev/cap-dev-pipe/design/REQ_GOVERNANCE_GATE_GAPS.md) | Gap 1 — A2A governance gates not wired |
| [Cross-Cutting Context Loss Analysis](~/Documents/dev/startd8-sdk/docs/design/kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) | §6-7: Forward manifest contracts overhead |
| [Kaizen Seed Utilization Requirements](~/Documents/dev/startd8-sdk/docs/design/kaizen/KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md) | §1.3: Seed field consumption map |
| [Pipeline Requirements](~/Documents/dev/cap-dev-pipe/design/pipeline-requirements.md) | REQ-CDP-INT-005: A2A governance gates specification |
