# Requirements: Capability Delivery Pipeline

**Status:** Draft
**Date:** 2026-02-16
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (pipeline evolution)
**Predecessor:** Export Pipeline Analysis Guide (`docs/guides/EXPORT_PIPELINE_ANALYSIS_GUIDE.md`)
**Pipeline version:** 2.0 (Capability Delivery Pipeline)

---

## Problem Statement

The existing export pipeline (v1) starts at `manifest init` and treats
everything before init as untracked manual work. Two commands that produce
valuable upstream context --- `contextcore create` (project identity) and
`contextcore polish` (plan quality checks) --- exist but their outputs are
invisible to downstream stages because they were not wired into the pipeline's
artifact inventory system.

This creates three problems:

1. **Broken provenance chain.** Pre-pipeline decisions (project identity,
   business criticality, plan quality status) are not recorded in
   `run-provenance.json`, so downstream consumers cannot verify what was
   established before export.

2. **Duplicate derivation.** Plan-ingestion and artisan agents re-derive
   project context and quality status that `create` and `polish` already
   computed, wasting tokens and introducing inconsistency risk.

3. **No quality gate before init.** A plan document can enter the pipeline
   with structural deficiencies (missing overview, objectives, requirements)
   that cause downstream rework. Polish checks exist but are not enforced.

The Capability Delivery Pipeline (v2.0) extends the existing 7-step export
pipeline with pre-pipeline stages, a unified provenance chain, and
forward-compatible inventory accumulation. The full end-to-end pipeline spans
two codebases: **ContextCore** (stages 0–4: metadata, quality, and contract
generation) and **startd8-sdk** (stages 5–7: plan ingestion, contractor
execution, and artifact delivery via the artisan or prime contractor workflows).

---

## Scope

### In scope

- Formalizing `create`, `polish`, and `fix` as pre-pipeline stages with inventory output
- Provenance accumulation across all stages (create -> polish -> fix -> init -> export)
- A shell script (`run-cap-delivery.sh`) that orchestrates the ContextCore half of the
  pipeline (stages 0–4) for a plan + requirements pair
- A shell script (`run-cap-delivery-stages5-7.sh`) in startd8-sdk that orchestrates
  plan ingestion, contractor execution, and finalize (stages 5–7)
- A shell script (`run-cap-delivery-e2e.sh`) that chains both halves into a single
  end-to-end invocation (stages 0–7)
- Forward compatibility: export must preserve pre-pipeline inventory entries
- Clear documentation of the handoff contract between ContextCore and startd8-sdk

### Out of scope

- Changes to startd8-sdk plan-ingestion or contractor workflow internals
- Changes to A2A governance gate logic (Gate 1, Gate 2, Gate 3)
- New CLI commands in either codebase (orchestration uses existing commands and scripts)

---

## Pipeline Stages — Full End-to-End

The Capability Delivery Pipeline spans two codebases. Stages 0–4 run in
**ContextCore** (orchestrated by `run-cap-delivery.sh`). Stages 5–7 run in
**startd8-sdk** (invoked separately after the handoff).

```text
                         ContextCore (run-cap-delivery.sh)
  ┌──────────────────────────────────────────────────────────────────────────────────┐
  │                                                                                  │
  │  Stage 0       Stage 1     Stage 1.5   Stage 2          Stage 3     Stage 4      │
  │  CREATE        POLISH      FIX         INIT-FROM-PLAN   VALIDATE    EXPORT       │
  │  project ctx   plan quality auto-remedy manifest boot    schema chk  artifact ctr │
  │  ───────────  ──────────  ──────────  ──────────────── ──────────  ──────────── │
  │  project-     polish-     *.fixed.md  .contextcore.yaml (pass/fail) artifact-    │
  │  context.yaml report.json fix-report  plan-analysis.json            manifest     │
  │                           .json       init-from-plan-               onboarding-  │
  │                                       report.json                   metadata.json│
  │                                                                     run-prov.json│
  │      ╰──────────── run-provenance.json accumulates across stages ──────────╯     │
  │                                                                                  │
  └───────────────────────────────────┬──────────────────────────────────────────────┘
                                      │
                    Handoff artifacts: │  artifact-manifest.yaml
                                      │  onboarding-metadata.json
                                      │  run-provenance.json
                                      │
  ┌───────────────────────────────────▼──────────────────────────────────────────────┐
  │                                                                                  │
  │                          startd8-sdk                                              │
  │                                                                                  │
  │  Stage 5              Stage 6                          Stage 7                   │
  │  GATE 1 +             CONTRACTOR EXECUTION             GATE 3                    │
  │  PLAN INGESTION       (Artisan or Prime Contractor)    FINALIZE                  │
  │  ────────────────     ─────────────────────────────    ──────────────             │
  │  a2a-check-pipeline   complexity ≤ 40 → Prime Ctr     per-artifact verify        │
  │  parse/assess/         complexity > 40 → Artisan       provenance chain check    │
  │  transform/refine     ┌─────────────────────────┐     finalize report            │
  │  ──── Gate 2 ────     │ Artisan: plan → scaffold │                               │
  │  a2a-diagnose         │ → design → implement →   │                               │
  │  (Three Questions)    │ test → review → finalize  │                               │
  │                       │                           │                               │
  │                       │ Prime Ctr: feature-by-    │                               │
  │                       │ feature integration       │                               │
  │                       └─────────────────────────┘                                │
  │                                                                                  │
  └──────────────────────────────────────────────────────────────────────────────────┘
```

> **Note:** Stage 1.5 (FIX) was added after the initial pipeline design.
> See [REQ_FIX_STAGE.md](REQ_FIX_STAGE.md) for the full fix-stage requirements.

### Handoff contract (Stage 4 → Stage 5)

The export artifacts serve as the handoff contract between ContextCore and
startd8-sdk. Key files consumed by plan ingestion and contractor execution:

| Artifact | Consumed by | Key fields |
|----------|------------|------------|
| `artifact-manifest.yaml` | Plan ingestion (PARSE), Artisan (PLAN/DESIGN) | coverage gaps, derivation rules, dependency graph |
| `onboarding-metadata.json` | Plan ingestion (ASSESS), Artisan (IMPLEMENT) | parameter sources, output contracts, calibration hints |
| `run-provenance.json` | Gate 1 (checksum chain), Gate 3 (provenance verify) | source checksum, artifact inventory |

### Complexity-based routing (Stage 6)

Plan ingestion's TRANSFORM phase scores 7 complexity dimensions (0–100) and
routes to the appropriate contractor:

- **Complexity ≤ 40** → **Prime Contractor** — sequential feature-by-feature integration
- **Complexity > 40** → **Artisan Workflow** — structured 7-phase orchestration
  (plan → scaffold → design → implement → test → review → finalize)

The `force_route` config can override automatic routing.

### Defense-in-depth gates

| Gate | Location | Command | Purpose |
|------|----------|---------|---------|
| Gate 1 | After export, before plan ingestion | `contextcore contract a2a-check-pipeline` | 6 structural integrity checks (checksums, provenance, gap parity) |
| Gate 2 | After plan ingestion, before contractor | `contextcore contract a2a-diagnose` | Three Questions diagnostic (stops at first failure) |
| Gate 3 | After contractor execution | Finalize verification | Per-artifact checksums, provenance chain, status rollup |

---

## Requirements

### REQ-CDP-001: Create stage produces inventory entry

**Priority:** P1

When `contextcore create` is invoked with `--output-dir`, it MUST:

1. Write `project-context.yaml` containing the ProjectContext resource
2. Register an inventory entry with `artifact_id="create.project_context"`
   in `run-provenance.json` via `extend_inventory()`
3. Declare consumers: `contextcore.manifest.export`, `startd8.workflow.plan_ingestion`

**Acceptance criteria:**
- `run-provenance.json` exists after create with version `2.0.0`
- `artifact_inventory` contains exactly one entry with stage `create`

---

### REQ-CDP-002: Polish stage produces inventory entry

**Priority:** P1

When `contextcore polish` is invoked with `--output-dir`, it MUST:

1. Write `polish-report.json` containing check results (same schema as `--format json`)
2. Register an inventory entry with `artifact_id="polish.polish_report"`
   in `run-provenance.json` via `extend_inventory()`
3. Declare consumers: `startd8.workflow.plan_ingestion`, `artisan.review`

**Acceptance criteria:**
- `polish-report.json` exists after polish
- `run-provenance.json` has version `2.0.0` with polish entry appended
- If create ran first, both entries are present (accumulation)

---

### REQ-CDP-003: Polish strict mode gates pipeline

**Priority:** P1

When `contextcore polish --strict` is used in the pipeline, a non-zero exit
code MUST halt the pipeline before init-from-plan. The pipeline script MUST
check the exit code and abort with a clear message identifying which checks
failed.

**Acceptance criteria:**
- Pipeline script checks polish exit code
- Non-zero exit produces message listing failed checks
- User can bypass with `--skip-polish` flag on the pipeline script

---

### REQ-CDP-004: Init-from-plan consumes plan and requirements

**Priority:** P1

The pipeline MUST invoke `contextcore manifest init-from-plan` with:

1. `--plan` pointing to the plan document
2. `--requirements` pointing to each requirements document
3. `--output` targeting the pipeline output directory
4. `--force` to allow re-runs without manual cleanup

**Acceptance criteria:**
- `.contextcore.yaml` is written to the output directory
- `init-from-plan-report.json` is written alongside it
- `init-run-provenance.json` is written

---

### REQ-CDP-005: Validate gates pipeline before export

**Priority:** P1

The pipeline MUST invoke `contextcore manifest validate` with `--strict` on the
generated manifest. A non-zero exit code MUST halt the pipeline before export.

**Acceptance criteria:**
- Pipeline checks validate exit code
- Non-zero exit produces clear message
- User can bypass with `--skip-validate` flag

---

### REQ-CDP-006: Export preserves pre-pipeline inventory (forward compatibility)

**Priority:** P1 (critical)

When `contextcore manifest export` writes `run-provenance.json`, it MUST:

1. Read any existing `run-provenance.json` in the output directory
2. Extract pre-pipeline `artifact_inventory` entries
3. Merge them into the export payload (export entries win on `artifact_id` collision)
4. Write the merged result

This ensures that create and polish inventory entries survive the export write.

**Acceptance criteria:**
- After create -> polish -> export, `run-provenance.json` contains entries from
  all three stages
- Export's own entries take precedence on `artifact_id` collision
- Malformed pre-existing JSON is silently ignored (export does not fail)

---

### REQ-CDP-007: Export writes to same output directory as pre-pipeline

**Priority:** P2

The pipeline script MUST use a single output directory for all stages so that
`run-provenance.json` accumulates naturally. The directory layout after a
complete run:

```
{output-dir}/
  project-context.yaml          # from create
  polish-report.json            # from polish
  {plan-stem}.fixed.md          # from fix (remediated plan)
  fix-report.json               # from fix (actions taken)
  plan-analysis.json            # from analyze-plan
  .contextcore.yaml             # from init-from-plan
  {project}-artifact-manifest.yaml  # from export
  {project}-projectcontext.yaml     # from export
  onboarding-metadata.json      # from export
  validation-report.json        # from export
  run-provenance.json           # accumulated: create + polish + fix + export entries
  init-run-provenance.json      # from init-from-plan (separate file, no collision)
```

**Acceptance criteria:**
- All files coexist in one directory
- No file from an earlier stage is overwritten by a later stage
  (except `run-provenance.json` which is intentionally accumulated)

---

### REQ-CDP-008: Pipeline script orchestrates ContextCore stages (0–4)

**Priority:** P1

A shell script (`run-cap-delivery.sh`) MUST orchestrate the ContextCore half of
the pipeline (stages 0–4). The startd8-sdk stages (5–7) are invoked separately
after the handoff artifacts are produced.

The script MUST orchestrate:

1. **Preflight**: Verify ContextCore is installed, plan file exists, requirements files exist
2. **Stage 0 (CREATE)**: `contextcore create --output-dir`
3. **Stage 1 (POLISH)**: `contextcore polish --strict --output-dir` (gating)
4. **Stage 1.5 (FIX)**: `contextcore fix PLAN --polish-report --output-dir` (skippable)
5. **Stage 2a (ANALYZE)**: `contextcore manifest analyze-plan --plan --requirements --output`
6. **Stage 2b (INIT)**: `contextcore manifest init-from-plan --plan --requirements --plan-analysis --output`
7. **Stage 3 (VALIDATE)**: `contextcore manifest validate --path`
8. **Stage 4 (EXPORT)**: `contextcore manifest export --emit-provenance --emit-run-provenance`
9. **Summary**: Print inventory entry count, stage breakdown, file listing, and exit status

When fix runs, downstream stages (analyze, init, export) use the remediated plan
(`*.fixed.md`) instead of the original. When `--skip-fix` is set, the original
plan passes through unchanged.

**Acceptance criteria:**
- Script exits non-zero if any gating stage fails
- Script prints clear progress for each stage
- Script accepts `--plan`, `--requirements`, `--output-dir`, `--project`, `--name` arguments
- Script accepts `--skip-polish`, `--skip-fix`, and `--skip-validate` bypass flags
- Script accepts `--no-strict-quality` pass-through for export

---

### REQ-CDP-009: Pipeline produces provenance summary

**Priority:** P2

After all stages complete, the pipeline script MUST print a summary showing:

1. Number of inventory entries in `run-provenance.json`
2. Stage breakdown (how many entries per stage)
3. Total files written
4. Exit status of each gating step

**Acceptance criteria:**
- Summary is printed to stdout
- Summary is parseable by a human operator

---

### REQ-CDP-010: Backward compatibility with export-only usage

**Priority:** P1

When `contextcore manifest export` is run WITHOUT prior create/polish
(no pre-existing `run-provenance.json`), behavior MUST be identical to the
existing export pipeline. The forward-compatibility merge is a no-op when
there are no pre-pipeline entries.

**Acceptance criteria:**
- Export without pre-pipeline provenance produces the same output as before
- No new required flags or configuration
- Existing export tests continue to pass

---

### REQ-CDP-011: Delivery script orchestrates startd8-sdk stages (5–7)

**Priority:** P1

A shell script (`run-cap-delivery-stages5-7.sh`) in the **startd8-sdk** repository
MUST orchestrate stages 5–7, consuming the handoff artifacts produced by
`run-cap-delivery.sh` (stages 0–4).

```
Usage: run-cap-delivery-stages5-7.sh --export-dir DIR --project-root DIR \
         [--force-route artisan|prime] [--cost-budget USD] \
         [--task-filter TASK_IDS] [--dry-run] \
         [--lead-agent SPEC] [--drafter-agent SPEC]
```

**Stage sequence:**

1. **Preflight** — verify startd8-sdk installed, export-dir contains handoff
   artifacts (`artifact-manifest.yaml` or `*-artifact-manifest.yaml`,
   `onboarding-metadata.json`, `run-provenance.json`), project-root exists
2. **Gate 1** — `contextcore contract a2a-check-pipeline EXPORT_DIR --fail-on-unhealthy`
   (gating; halt on failure)
3. **Stage 5: PLAN INGESTION** — invoke `PlanIngestionWorkflow` via runner script
   with `plan_path` from export dir, `output_dir` for ingestion artifacts,
   optional `force_route` override
4. **Gate 2** — `contextcore contract a2a-diagnose EXPORT_DIR --ingestion-dir INGESTION_DIR --fail-on-issue`
   (gating; halt on failure)
5. **Stage 6: CONTRACTOR EXECUTION** — route based on plan ingestion's
   complexity assessment:
   - **Artisan route**: `python3 scripts/run_artisan_workflow.py --seed SEED --project-root DIR --output-dir DIR --cost-budget USD`
   - **Prime route**: `python3 scripts/run_artisan_contractor.py --max-cost USD`
   Pass through `--task-filter`, `--lead-agent`, `--drafter-agent`, `--dry-run`
   if provided
6. **Gate 3** — `contextcore contract a2a-diagnose EXPORT_DIR --ingestion-dir INGESTION_DIR --artisan-dir CONTRACTOR_DIR --fail-on-issue`
   (gating; halt on failure)
7. **Summary** — print route taken (artisan/prime), task count, cost summary,
   gate outcomes, artifact listing

**Key behaviors:**
- `--export-dir` points to the output of `run-cap-delivery.sh` (stages 0–4)
- `--project-root` is the target project where artifacts are generated
- `--force-route` overrides complexity-based routing (default: auto)
- `--cost-budget` sets USD limit for contractor execution (default: 25.00)
- `--dry-run` passes through to plan ingestion and contractor (no LLM calls, no writes)
- Reads the complexity route from plan ingestion output to determine contractor
- Exit code 0 only when all gates pass and contractor succeeds

**Acceptance criteria:**
- Script exits non-zero if any gate fails
- Script correctly routes to artisan or prime based on complexity score
- Script accepts `--force-route` to override routing
- Script prints gate outcomes and cost summary
- Script works with output from `run-cap-delivery.sh` without modification

---

### REQ-CDP-012: End-to-end delivery script chains both halves

**Priority:** P2

A shell script (`run-cap-delivery-e2e.sh`) MUST chain the ContextCore half
(stages 0–4) and the startd8-sdk half (stages 5–7) into a single invocation.

```
Usage: run-cap-delivery-e2e.sh --plan PATH --requirements PATH [--requirements PATH ...] \
         --output-dir DIR --project ID --name NAME --project-root DIR \
         [--skip-polish] [--skip-fix] [--skip-validate] [--no-strict-quality] \
         [--force-route artisan|prime] [--cost-budget USD] \
         [--task-filter TASK_IDS] [--dry-run] \
         [--lead-agent SPEC] [--drafter-agent SPEC]
```

**Behavior:**

1. Invoke `run-cap-delivery.sh` with stages 0–4 arguments
2. On success, invoke `run-cap-delivery-stages5-7.sh` with `--export-dir`
   pointing to the output directory from step 1
3. Print a unified summary covering all stages (0–7)

**Key behaviors:**
- Flags for stages 0–4 (`--skip-polish`, `--skip-fix`, `--skip-validate`,
  `--no-strict-quality`) pass through to `run-cap-delivery.sh`
- Flags for stages 5–7 (`--force-route`, `--cost-budget`, `--task-filter`,
  `--lead-agent`, `--drafter-agent`) pass through to `run-cap-delivery-stages5-7.sh`
- `--dry-run` passes through to both halves
- If stages 0–4 fail, stages 5–7 are not attempted
- Exit code 0 only when both halves succeed

**Location:** This script lives in the **ContextCore** repository (since it
is the entry point for the full pipeline), but requires startd8-sdk to be
installed for stages 5–7.

**Acceptance criteria:**
- Full pipeline runs from plan document to generated artifacts in one command
- Failure in any stage halts the pipeline with a clear error
- Unified summary shows all gate outcomes across both halves
- Works when both ContextCore and startd8-sdk are installed

---

## Non-Functional Requirements

### NFR-CDP-001: No LLM calls in pre-pipeline stages

Create and polish MUST NOT make LLM API calls. They are deterministic,
regex/schema-based checks. Only init-from-plan and export may invoke LLMs
(init-from-plan for inference, export for enrichment if configured).

### NFR-CDP-002: Idempotent re-runs

Running the pipeline script twice with the same inputs MUST produce
functionally equivalent output. `extend_inventory` deduplicates by
`artifact_id`, and `--force` on init-from-plan allows overwrites.

### NFR-CDP-003: Stage isolation

Each stage MUST be independently runnable. The pipeline script is a
convenience orchestrator; individual `contextcore` commands remain
usable standalone.

---

## Verification Plan

| Req | Verification method |
|-----|-------------------|
| REQ-CDP-001 | Unit test: `test_create_inventory.py::test_creates_inventory_entry` |
| REQ-CDP-002 | Unit test: `test_polish_inventory.py::test_creates_inventory_entry` |
| REQ-CDP-003 | Integration test: run pipeline with failing plan, assert exit != 0 |
| REQ-CDP-004 | Integration test: run pipeline, assert `.contextcore.yaml` exists |
| REQ-CDP-005 | Integration test: run pipeline, assert validate is invoked |
| REQ-CDP-006 | Unit test: `test_artifact_inventory.py::TestExtendInventory` + merge test |
| REQ-CDP-007 | Integration test: all files in single output dir after full run |
| REQ-CDP-008 | Integration test: run `run-cap-delivery.sh` end-to-end |
| REQ-CDP-009 | Integration test: pipeline stdout contains inventory summary |
| REQ-CDP-010 | Existing export tests pass without modification |
| REQ-CDP-011 | Integration test: run `run-cap-delivery-stages5-7.sh` with export dir from stages 0–4 |
| REQ-CDP-012 | Integration test: run `run-cap-delivery-e2e.sh` end-to-end on a plan + requirements pair |
| NFR-CDP-001 | Code review: no LLM imports in create/polish paths |
| NFR-CDP-002 | Integration test: run pipeline twice, compare output |
| NFR-CDP-003 | Unit tests: each command works standalone |
