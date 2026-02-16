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
pipeline with two pre-pipeline stages, a unified provenance chain, and
forward-compatible inventory accumulation.

---

## Scope

### In scope

- Formalizing `create` and `polish` as pre-pipeline stages with inventory output
- Provenance accumulation across all stages (create -> polish -> init -> export)
- A shell script that orchestrates the full pipeline for a plan + requirements pair
- Forward compatibility: export must preserve pre-pipeline inventory entries

### Out of scope

- Changes to plan-ingestion or artisan workflow consumption of inventory entries
- Changes to A2A governance gates (Gate 1, Gate 2, Gate 3)
- Automated remediation of polish failures (polish remains advisory unless `--strict`)

---

## Pipeline Stages

```text
Stage 0          Stage 1          Stage 2            Stage 3            Stage 4
CREATE           POLISH           INIT-FROM-PLAN     VALIDATE           EXPORT
project context  plan quality     manifest bootstrap schema check       artifact contract
────────────── ────────────── ────────────────── ────────────────  ──────────────────
project-        polish-          .contextcore.yaml  (pass/fail)        artifact-manifest
context.yaml    report.json      init-from-plan-                       projectcontext CRD
                                 report.json                           onboarding-metadata
                                                                       run-provenance.json
         ╰──────────── run-provenance.json accumulates across stages ──────────────╯
```

After Stage 4, the existing 7-step pipeline continues unchanged:
Gate 1 -> Plan Ingestion -> Gate 2 -> Contractor Execution -> Gate 3.

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
  .contextcore.yaml             # from init-from-plan
  {project}-artifact-manifest.yaml  # from export
  {project}-projectcontext.yaml     # from export
  onboarding-metadata.json      # from export
  validation-report.json        # from export
  run-provenance.json           # accumulated: create + polish + export entries
  init-run-provenance.json      # from init-from-plan (separate file, no collision)
```

**Acceptance criteria:**
- All files coexist in one directory
- No file from an earlier stage is overwritten by a later stage
  (except `run-provenance.json` which is intentionally accumulated)

---

### REQ-CDP-008: Pipeline script orchestrates all stages

**Priority:** P1

A shell script (`run-cap-delivery.sh`) MUST orchestrate:

1. **Preflight**: Verify ContextCore is installed, plan file exists, requirements files exist
2. **Stage 0 (CREATE)**: `contextcore create --output-dir`
3. **Stage 1 (POLISH)**: `contextcore polish --strict --output-dir` (gating)
4. **Stage 2 (INIT)**: `contextcore manifest init-from-plan --plan --requirements --output`
5. **Stage 3 (VALIDATE)**: `contextcore manifest validate --strict`
6. **Stage 4 (EXPORT)**: `contextcore manifest export --emit-provenance --emit-run-provenance`
7. **Summary**: Print inventory entry count, file listing, and exit status

**Acceptance criteria:**
- Script exits non-zero if any gating stage fails
- Script prints clear progress for each stage
- Script accepts `--plan`, `--requirements`, `--output-dir`, `--project`, `--name` arguments
- Script accepts `--skip-polish` and `--skip-validate` bypass flags

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
| NFR-CDP-001 | Code review: no LLM imports in create/polish paths |
| NFR-CDP-002 | Integration test: run pipeline twice, compare output |
| NFR-CDP-003 | Unit tests: each command works standalone |
