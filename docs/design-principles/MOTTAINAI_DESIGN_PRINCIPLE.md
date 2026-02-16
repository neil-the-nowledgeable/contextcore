# Mottainai Design Principle

Purpose: establish a cross-cutting design principle for the ContextCore + startd8-sdk pipeline — an aversion to wasteful regeneration of artifacts that earlier pipeline stages already produced.

This document is intentionally living guidance. Update it as new reuse opportunities are identified.

---

## The Principle

**Mottainai** (もったいない) — an expression of regret at the full value of something not being put to good use. In contemporary Japanese, mottainai is most commonly used to indicate that something is being discarded needlessly, or to express regret at such a fact.

Applied to the pipeline: **every artifact produced by an earlier stage carries invested computation, context, and deterministic correctness. Discarding it — or regenerating it via an expensive LLM call — when it could be passed forward is mottainai.**

---

## Why This Matters

The 7-step pipeline (init → export → Gate 1 → plan-ingestion → Gate 2 → contractor → Gate 3) produces rich artifacts at each stage. ContextCore export produces deterministic derivation rules, pre-resolved parameters, dependency graphs, and output contracts. Plan-ingestion produces architectural reviews, calibration hints, and structured task decompositions. These artifacts represent:

1. **Deterministic correctness** — ContextCore computes business-to-parameter mappings (e.g., "criticality high → alert severity P2") through explicit derivation rules. An LLM re-deriving the same mapping may produce a different answer.
2. **Invested LLM cost** — plan-ingestion's REFINE phase runs a full architectural review. If that review's suggestions never reach the DESIGN phase, the REFINE LLM call was wasted.
3. **Provenance integrity** — when the DESIGN phase independently re-derives parameters, the provenance chain breaks. The final artifact's parameter values can no longer be traced back to the export's deterministic computation.

---

## The Inventory Problem

The pipeline lacks a single artifact that answers: **"what has already been produced, and where is it?"** Each stage writes its outputs to disk, but downstream stages must know what exists, where it lives, and whether it is still fresh. Without an inventory:

- Downstream stages cannot discover reusable assets.
- Stale artifacts cannot be distinguished from fresh ones.
- The cost of regeneration is invisible — nobody knows what was wasted.

The `run-provenance.json` artifact (produced by export) already tracks input/output file fingerprints. The [Pipeline Artifact Inventory Requirements](./PIPELINE_ARTIFACT_INVENTORY_REQUIREMENTS.md) document extends this into a typed inventory that each pipeline stage can contribute to and consume from.

---

## Current Violations (Baseline)

The following are known mottainai violations as of this writing. Each represents an artifact produced by an earlier stage that a later stage either ignores or regenerates from scratch.

### Gap 1: `derivation_rules` — Export → DESIGN

ContextCore export computes deterministic business-to-parameter derivation rules (e.g., `spec.business.criticality` → alert severity P2). These rules are written to `onboarding-metadata.json` but never reach the artisan DESIGN phase. The DESIGN LLM independently re-derives the same mappings via inference.

**Waste**: Redundant LLM inference for a deterministic computation. Quality risk from inconsistent derivation.

### Gap 2: `resolved_artifact_parameters` — Export → DESIGN / IMPLEMENT

ContextCore export pre-resolves parameter values per artifact (e.g., `alertSeverity: P2`, `availabilityThreshold: 99.9%`). These concrete values are written to `onboarding-metadata.json` but never extracted into the seed or injected into DESIGN/IMPLEMENT prompts. The LLM must re-resolve them.

**Waste**: Redundant LLM parameter resolution. The values exist — they just are not forwarded.

### Gap 3: `expected_output_contracts` — Export → DESIGN / IMPLEMENT / TEST

ContextCore export produces per-artifact-type output contracts with `expected_depth`, `max_lines`, `max_tokens`, `completeness_markers`, and `red_flag` warnings. These are never consumed by any downstream stage.

**Waste**: The DESIGN phase uses LOC-based heuristics to guess depth tiers that the export already computed per artifact type. The TEST phase validates artifacts without knowing what completeness markers to check.

### Gap 4: `artifact_dependency_graph` — Export → Plan-Ingestion / IMPLEMENT

ContextCore export produces a deterministic artifact dependency graph (e.g., notification policy depends on prometheus rules). Plan-ingestion ignores this and uses an LLM to infer task dependencies.

**Waste**: Redundant LLM dependency inference for a deterministic graph.

### Gap 5: REFINE Suggestions — Plan-Ingestion → DESIGN

Plan-ingestion's REFINE phase runs an architectural review that produces structured suggestions (area, severity, rationale, validation approach). These are written into the plan document's Appendix C but never extracted into the seed. The artisan DESIGN phase never reads the plan document.

**Waste**: The entire REFINE LLM call produces output that does not reach DESIGN. The DESIGN LLM regenerates architectural decisions from scratch.

### Gap 6: `design_calibration_hints` — Export → Plan-Ingestion

ContextCore export produces per-artifact-type calibration hints (e.g., "dashboards should be comprehensive"). Plan-ingestion ignores these and computes its own depth tiers from LOC estimates, which are less domain-aware.

**Waste**: Artifact-type-aware calibration is overridden by a blunt LOC heuristic.

### Gap 7: `open_questions` — Export → DESIGN

ContextCore export surfaces unresolved questions from the manifest's `guidance.questions`. These never reach the DESIGN prompt.

**Waste**: DESIGN decisions are made without awareness of flagged uncertainties.

### Gap 8: TRANSFORM Plan Document — Plan-Ingestion → DESIGN

Plan-ingestion's TRANSFORM phase produces a structured plan document with architecture, risk register, and verification strategy sections. The artisan DESIGN phase never reads this document — it builds FeatureContext only from PARSE-level seed data.

**Waste**: Architecture and risk analysis regenerated from scratch.

---

## Application Rules

When designing new pipeline stages or modifying existing ones:

1. **Inventory before generating.** Before an LLM call that produces design decisions, parameter values, or architectural context, check the pipeline artifact inventory for existing assets that cover the same ground.

2. **Forward, don't regenerate.** If an earlier stage deterministically computed a value (derivation rules, resolved parameters, dependency ordering), pass it through to later stages rather than asking an LLM to re-derive it.

3. **Degrade gracefully.** If an earlier artifact is missing or stale, fall back to LLM generation — but log the fallback and the reason. The fallback is acceptable; silently ignoring available assets is not.

4. **Register what you produce.** Each stage that produces artifacts useful to downstream stages should register them in the pipeline artifact inventory with: semantic role, file path, freshness indicator (checksum + timestamp), and the stage that produced them.

5. **Prefer deterministic over stochastic.** When both a deterministic value (from export) and an LLM-generated value are available, prefer the deterministic one. The LLM value is useful as a fallback or validation signal, not as the primary source.

6. **Measure the gap.** When closing a mottainai violation, log the before/after cost. This makes the value of reuse visible and builds the case for future investment.

---

## Relationship to Other Requirements

| Document | Relationship |
|----------|-------------|
| [Pipeline Artifact Inventory Requirements](./PIPELINE_ARTIFACT_INVENTORY_REQUIREMENTS.md) | The inventory mechanism that enables mottainai — tracks what exists so downstream stages can find it |
| [Manifest Export Requirements](./MANIFEST_EXPORT_REQUIREMENTS.md) | Defines the export outputs that are the primary source of reusable artifacts |
| [A2A Gate Requirements](./A2A_GATE_REQUIREMENTS.md) | Gates validate artifact integrity at boundaries — mottainai adds the question "are we using what we validated?" |
| [Export Pipeline Analysis Guide](../guides/EXPORT_PIPELINE_ANALYSIS_GUIDE.md) | The operational guide that describes the 7-step pipeline where mottainai violations occur |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-16 | Initial version: principle statement, 8 known violations from pipeline analysis, application rules |
