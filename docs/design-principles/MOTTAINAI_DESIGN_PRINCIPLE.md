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

## Prime Contractor Audit (2026-02-17)

The prime route was wired as a symmetric consumer of plan-ingestion output (`prime-context-seed.json` → `run_prime_workflow.py` → `PrimeContractorWorkflow`). An audit of the implementation against the mottainai principle identified the following violations. Gaps 1–8 above are artisan-focused; Gaps 9–14 below are prime-specific.

### Gap 9: Seed `_enrichment` Data Discarded at Queue Boundary — Plan-Ingestion → Prime

`DomainPreflightWorkflow` enriches the seed with per-task `_enrichment` blocks (domain classification, prompt constraints, validation rules). `FeatureQueue.add_features_from_seed()` extracts only `task_id`, `title`, `description`, `target_files`, and `dependencies` — the `_enrichment` block is silently dropped. `PrimeContractorWorkflow` then re-computes enrichment at runtime via `DomainChecklist._get_domain_enrichment()`, which performs the same domain classification a second time.

**Waste**: Redundant domain classification. The enrichment was already computed and written to the seed; the prime workflow re-derives it because `FeatureSpec` has no field for it.

**Fix**: Add an optional `metadata: Dict[str, Any]` field to `FeatureSpec`. Have `add_features_from_seed()` forward `_enrichment` into metadata. Have `_generate_code()` check `feature.metadata.get("_enrichment")` before falling back to `DomainChecklist`.

### Gap 10: `onboarding` Metadata Not Injected into Code Generation Context

The prime seed carries `onboarding` data with `derivation_rules`, `resolved_artifact_parameters`, `expected_output_contracts`, and `semantic_conventions`. The `PrimeContractorWorkflow._generate_code()` method builds `gen_context` with only `feature_name`, `target_file`, and optionally `domain_constraints` — none of the onboarding fields are forwarded to the `LeadContractorCodeGenerator`.

**Waste**: The LLM must infer parameter values, derivation logic, and output structure from scratch. These were deterministically computed by ContextCore export and are sitting in the seed file.

**Fix**: In `run_prime_workflow.py`, load the seed's `onboarding` and `artifacts` sections. Forward relevant fields (`derivation_rules`, `resolved_artifact_parameters`) into the workflow or code generator context so they reach the prompt.

### Gap 11: No Architectural Context for Prime Route

Plan-ingestion computes `architectural_context` (project goals, shared modules, import conventions, dependency clusters) for the artisan route but sets it to `None` for the prime route. The prime `LeadContractorCodeGenerator` therefore has no awareness of cross-feature architectural patterns.

**Waste**: Each prime feature is generated in isolation without knowledge of shared modules, import conventions, or project goals. Features touching the same files may produce inconsistent patterns.

**Mitigation**: The prime workflow is designed for simpler projects (complexity ≤ 40), where cross-feature coordination is less critical. However, even for simple projects, forwarding `plan.goals` and `plan.mentioned_files` would provide cheap context at no LLM cost.

**Fix**: Compute a lightweight architectural summary (goals + mentioned files) for prime seeds. No LLM cost — this is purely deterministic extraction from the parsed plan.

### Gap 12: No Design Calibration for Prime Route

The artisan seed includes `design_calibration` (per-task depth tiers from `SizeEstimator`), which tells the DESIGN phase how much detail each task needs. The prime seed sets this to `None`. The prime workflow uses a flat `max_lines_per_feature=150` / `max_tokens_per_feature=500` limit for all tasks regardless of type.

**Waste**: A ServiceMonitor YAML (10 lines) gets the same token budget as a full Grafana dashboard JSON (500+ lines). The uniform limit either under-generates complex artifacts or wastes tokens on simple ones.

**Fix**: Compute lightweight per-task token budgets from estimated LOC (already available in `ParsedFeature.estimated_loc`). No LLM call needed — just arithmetic.

### Gap 13: REFINE Suggestions Not Forwarded to Code Generation

Same as Gap 5 but for the prime route. Plan-ingestion's REFINE phase produces architectural review suggestions that are written to the plan document appendix. The prime workflow never reads the plan document — it works exclusively from the seed's task list.

**Waste**: The full REFINE LLM call produces suggestions that do not reach the code generator. The generator may make decisions that the REFINE phase already flagged as problematic.

**Fix**: Extract structured REFINE suggestions into the seed (or a sidecar file) during EMIT. Forward per-task suggestions into the code generation context as advisory constraints.

### Gap 14: No Generation Result Caching in Prime Workflow

The artisan workflow saves per-task `generation_results` and `design_results` in `.startd8/state/` for resume. The `--resume` and `--force-implement` flags enable incremental re-runs. The prime workflow has no equivalent — re-running `run_prime_workflow.py` regenerates all non-complete features from scratch, even if a prior run produced valid code that failed only at the integration step.

**Waste**: If a feature generates successfully ($0.50 LLM cost) but fails integration checkpoint, the next retry regenerates the code rather than re-attempting integration with the existing generated files.

**Fix**: Check `FeatureSpec.generated_files` before calling `code_generator.generate()`. If generated files exist on disk and are non-empty, skip generation and go straight to integration. The `FeatureQueue` state already preserves `generated_files` and `status=GENERATED` across invocations.

### Gap 15: Source Artifact Types Not Registered — Export → DESIGN / IMPLEMENT

> **Status: PARTIALLY RESOLVED (2026-02-20)** — CID-018 source types registered in `ArtifactType` enum. See below.

The `ArtifactType` registry covers 14 types (8 observability, 4 onboarding, 2 integrity) but no source artifacts (Dockerfiles, requirements.in, proto schemas). The manifest declares these as tactic deliverables (TAC-PLAN-004) but the export cannot produce `design_calibration_hints`, `expected_output_contracts`, or `resolved_artifact_parameters` for unregistered types. The DESIGN phase re-derives Docker specifications from scratch. Additionally, four existing detection fragments (export `scan_existing_artifacts`, capability-index `_discovery_paths.yaml`, artifact inventory, SCAFFOLD `target_path.exists()`) each know something about existing assets but no signal flows end-to-end to prevent regeneration.

**Waste**: $1.43 and 21 minutes for 4 Dockerfile tasks in Run 1 artisan. The DESIGN phase produced 2,178 lines of design documents re-deriving base image selection, multi-stage patterns, SHA256 pinning, and environment variables that plan-ingestion had already computed in the artisan-context-seed.

**Fix**: Modular artifact type registry (`ArtifactTypeModule` ABC) with drop-in source modules under `artifact_types/source/`. Leverage capability-index `_discovery_paths.yaml` for actual filesystem scanning (currently metadata-only). End-to-end signal: discovery → `ArtifactStatus.EXISTS` → `skip_existing` task status → contractor skips generation for fresh existing files.

**Partial fix applied (2026-02-20)**: CID-018 amendment implemented — 5 source artifact types (dockerfile, python_requirements, protobuf_schema, editorconfig, ci_workflow) registered in `ArtifactType` enum with `SOURCE_TYPES` frozenset. All 4 onboarding dicts (parameter_sources, example_outputs, output_contracts, parameter_schema) and artifact conventions updated. Export scan patterns extended to discover source artifacts. Remaining: end-to-end `ArtifactStatus.EXISTS` → `skip_existing` flow for contractor generation bypass.

**Detail**: [GAP_15_EXPORT_ARTIFACT_TYPE_COVERAGE.md](~/Documents/Processes/cap-dev-pipe-test/GAP_15_EXPORT_ARTIFACT_TYPE_COVERAGE.md)

### Gap 16: `service_metadata` Never Auto-Derived — Export → DESIGN / IMPLEMENT

> **Status: RESOLVED (2026-02-20)** — Auto-derivation from manifest artifacts implemented.

When `--service-metadata` is not explicitly provided, downstream validators (AR-144, AR-147, AR-810) silently degrade to no-ops because `service_metadata` is `None`. This causes protocol mismatches (e.g., gRPC-vs-Flask defect DEV-R2-001) to go undetected. The information needed to derive service metadata already exists in the artifact manifest — PROTOBUF_SCHEMA artifacts indicate gRPC transport, and artifact parameters carry port hints.

**Waste**: Protocol mismatch defects discovered only at integration testing. Validators designed to catch these mismatches are silently skipped because the metadata they validate against is absent.

**Fix applied (2026-02-20)**: `_derive_service_metadata_from_manifest()` in `onboarding.py` scans `artifact_manifest.artifacts` for protocol indicators per target. PROTOBUF_SCHEMA artifacts trigger `transport_protocol: "grpc"` and `healthcheck_type: "grpc_health_probe"`; all other targets default to HTTP. Called automatically when `service_metadata is None` in `build_onboarding_metadata()`. Explicit `--service-metadata` CLI flag always takes precedence.

---

## Observed Failures — Artisan Run 1 Retry (2026-02-19)

The following violations were observed during a `--retry-incomplete` run against the Online Boutique Python artisan pipeline (17 tasks, 10 passed review, 7 failed). These are not hypothetical — they caused measurable waste in a real pipeline execution.

### Failure 1: `--retry-incomplete` Misidentified All 17 Tasks as Incomplete

**Violated rules**: 1 (Inventory before generating), 2 (Forward, don't regenerate)

**Root cause**: `run_artisan_workflow.py:472` globs for `workflow-result-*.json` (per-task result files) but the artisan produces a single batch `workflow-result.json` (no task-ID suffix). The glob matched nothing, so all 17 tasks — including the 10 that passed review with scores 82-95 — were classified as incomplete and queued for full regeneration.

**Observed waste**: The DESIGN phase ran fresh LLM calls for all 17 tasks instead of only the 7 failures. At ~$0.15/task, this wasted ~$1.50 on designs that already existed and were valid. 11 design documents were overwritten before the run was manually killed.

**Evidence**: Design doc timestamps showed 11 files rewritten at Feb 19 10:46-11:04 (all 17 were queued; process killed before completing). The 10 passing tasks had untouched generated source files from Feb 18.

**Fix applied**: `21548e4` — `--retry-incomplete` now falls back to the batch `workflow-result.json` and reads per-task review verdicts from `.startd8/state/review_results.json`. Tasks with `verdict: PASS` are skipped.

### Failure 2: Design Auto-Adopt Rejected Previously Adopted Designs

**Violated rule**: 2 (Forward, don't regenerate)

**Root cause**: The DESIGN three-way branch (`context_seed_handlers.py:1580`) checked `prior.get("status") == "designed"` but the design handoff also stores entries with `status == "adopted"` — designs that were themselves adopted from a prior run. These entries carry valid `design_document` content but were rejected by the status check and regenerated from scratch.

**Observed waste**: Of the 7 retry tasks, 3 (PI-009, PI-010, PI-011) had `status: "adopted"` in the handoff with valid design documents. All 3 were regenerated via fresh LLM calls instead of being adopted.

**Evidence**: `design-handoff.json` inspection:
```
PI-009: status=adopted, has_doc=True, cost=$0.4806  → regenerated
PI-010: status=adopted, has_doc=True, cost=$0.3365  → regenerated
PI-011: status=adopted, has_doc=True, cost=$0.3388  → regenerated
```

**Fix applied**: `21548e4` — Status check now accepts `status in ("designed", "adopted")`.

### Failure 3: Onboarding Data Not Bridged from Export to Seed (Gaps 1-7 Confirmed)

**Violated rules**: 2 (Forward, don't regenerate), 5 (Prefer deterministic over stochastic)

**Root cause**: Plan-ingestion's EMIT phase writes the artisan-context-seed without reading or forwarding the export's `onboarding-metadata.json`. The seed's `onboarding` section is empty. Additionally, all 17 tasks have `artifact_types_addressed: []`, so the DESIGN handler's per-artifact-type matching logic (lines 1096-1200) produces nothing even where injection code exists.

**Observed waste**: The DESIGN handler has complete injection logic for all 7 onboarding fields — `derivation_rules`, `resolved_parameters`, `output_contracts`, `refine_suggestions`, `plan_architecture`, `calibration_hints`, `open_questions`, `dependency_graph` — but every field was `None` at runtime. The DESIGN LLM re-derived all of these independently for each of the 17 tasks.

**Evidence**: Runtime inspection of the enriched seed:
```
onboarding keys: (empty)
task.artifact_types_addressed: [] (all 17 tasks)
```

While `onboarding-metadata.json` (same pipeline-output directory) contains:
```
derivation_rules:              7 entries
resolved_artifact_parameters:  8 entries
expected_output_contracts:     8 entries
design_calibration_hints:      8 entries
open_questions:                4 entries
artifact_dependency_graph:     4 entries
semantic_conventions:          4 entries
```

**Fix**: Not yet applied. Requires plan-ingestion to read `onboarding-metadata.json` from the export directory and inject it into the seed's `onboarding` field during EMIT. Also requires plan-ingestion to populate `artifact_types_addressed` per task based on target file patterns or manifest artifact-type mappings.

**Estimated cost of violation**: Across 17 tasks, the DESIGN phase spent $2.61 on LLM calls that re-derived parameter values, calibration hints, and architectural patterns that ContextCore had already computed deterministically. The quality cost is harder to quantify — DESIGN documents may contain parameter values inconsistent with the export's deterministic computations, breaking provenance integrity.

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
| 2026-02-17 | Prime Contractor audit: added Gaps 9–14 (seed enrichment discarded, onboarding not injected, no architectural context, no design calibration, REFINE suggestions not forwarded, no generation result caching) |
| 2026-02-18 | Gap 15: source artifact types not registered in export; modular artifact type registry proposed with end-to-end existing-asset detection (detail in separate doc) |
| 2026-02-19 | Added Observed Failures section: 3 violations from artisan Run 1 retry — batch result detection (fixed `21548e4`), adopted-status rejection (fixed `21548e4`), onboarding data not bridged from export to seed (Gaps 1-7 confirmed with evidence, not yet fixed) |
| 2026-02-20 | Gap 15 partially resolved: CID-018 source types (5) registered in ArtifactType enum with full onboarding dict coverage. Gap 16 resolved: auto-derive service_metadata from manifest artifacts |
