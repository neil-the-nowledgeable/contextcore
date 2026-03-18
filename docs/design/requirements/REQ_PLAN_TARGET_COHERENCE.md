# Requirements: Plan-Target Coherence Validation

**Status:** Draft
**Date:** 2026-02-20
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (pipeline integrity)
**Predecessor:** REQ_CAPABILITY_DELIVERY_PIPELINE.md (REQ-CDP-004, REQ-CDP-008)
**Companion:** Mottainai Design Principle (`docs/design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md`)
**Pipeline version:** 2.1

---

## Problem Statement

The Capability Delivery Pipeline accepts a plan document, requirements documents, and a `PROJECT_ROOT` as independent inputs. No pipeline stage validates that these inputs are mutually coherent — that the plan's scope matches where generated code will be written.

On 2026-02-20, a pipeline run was executed with:
- **Plan:** `~/Documents/dev/startd8-sdk/docs/prime/PRIME_EXECUTION_MODES_PLAN.md` (targets `src/startd8/contractors/`)
- **Requirements:** `~/Documents/dev/startd8-sdk/docs/prime/PRIME_EXECUTION_MODES_REQUIREMENTS.md`
- **PROJECT_ROOT:** `~/Documents/dev/online-boutique-python` (hardcoded default from `pipeline.env`)

The plan and requirements described modifications to the startd8-sdk. The PROJECT_ROOT pointed to an unrelated project. The pipeline proceeded without warning because:

1. **Stage 1 (POLISH)** validated plan document quality — it passed because the plan was well-structured. Polish is intentionally context-agnostic and receives no project root.
2. **Stage 1.5 (ANALYZE-PLAN)** performed structural analysis (phases, traceability, dependencies) — it passed because the plan's internal structure was sound. Analyze-plan receives no project root.
3. **Stage 2 (INIT-FROM-PLAN)** set `spec.targets[0].name` to `online-boutique-python` by blindly taking `Path(PROJECT_ROOT).name` — no validation that this target makes sense for the plan's content (`init_from_plan_ops.py` line 401-404).
4. **Stage 4 (EXPORT)** propagated the wrong target name into all downstream artifacts (validation-report, export-quality-report, onboarding-metadata).

The result: 19 tasks were generated correctly from the plan, but all code was written to the wrong project directory. Cost: $10.42 in LLM generation + manual recovery effort. The generated code was salvageable (moved to the correct location per Mottainai), but the pipeline metadata (provenance, manifest, validation reports) was contaminated.

### Root cause

`init-from-plan` receives `--project-root` and uses it to set the manifest's deployment target name. **No stage cross-validates that the plan's content is coherent with the project root.** The plan references `src/startd8/contractors/prime_contractor.py` — a path that does not exist under `online-boutique-python/`. This mismatch was detectable at pipeline time but no check existed.

### Why this matters beyond one incident

The pipeline is designed to serve multiple projects from the same process workspace. The `pipeline.env` file hardcodes a default `PROJECT_ROOT` for the most common case, but any run targeting a different project must override it. A human forgetting to override (or a script not exposing the override) causes silent misconfiguration. The cost scales with plan complexity — a 40-task Go run (Run 2) would waste ~$25 before the error became visible in generated output.

---

## Scope

### In scope

- Cross-validation of plan content against `PROJECT_ROOT` in the analyze-plan stage
- Cross-validation of requirements content against `PROJECT_ROOT`
- Warning/error reporting in `plan-analysis.json` for detected mismatches
- Pipeline orchestration script consumption of coherence warnings

### Out of scope

- Changes to polish (Stage 1) — polish remains context-agnostic by design
- Changes to the contractor stages (5-7) — the fix must catch mismatches before code generation
- Automatic correction of PROJECT_ROOT — the pipeline should report, not guess
- Git-based project detection (e.g., scanning for `.git` or `pyproject.toml`) — future enhancement

---

## Requirements

### REQ-PTC-001: Analyze-plan accepts project root

**Priority:** P1
**Source files:** `src/contextcore/cli/manifest.py` (analyze_plan_cmd), `src/contextcore/cli/analyze_plan_ops.py`

The `contextcore manifest analyze-plan` command MUST accept an optional `--project-root` parameter. When provided, the command MUST perform coherence checks (REQ-PTC-002 through REQ-PTC-005) and include results in the plan-analysis output.

**Acceptance criteria:**
- `--project-root` is accepted as an optional CLI parameter
- When omitted, coherence checks are skipped (no behavioral change to existing usage)
- When provided, the path MUST exist (validated by Click `exists=True`)

---

### REQ-PTC-002: Plan file path coherence check

**Priority:** P1
**Source files:** `src/contextcore/cli/analyze_plan_ops.py`

When `--project-root` is provided, analyze-plan MUST check whether the plan file's location is coherent with the project root.

**Signals checked:**
- Plan file lives under a directory whose name differs from the PROJECT_ROOT basename (e.g., plan under `startd8-sdk/` but PROJECT_ROOT is `online-boutique-python/`)

**Acceptance criteria:**
- If the plan's parent directory hierarchy does not contain the PROJECT_ROOT basename, emit a `warning` severity coherence finding
- Finding includes: plan path, PROJECT_ROOT path, detected parent directory name
- Finding is included in `plan-analysis.json` under a new `coherence_checks` section

---

### REQ-PTC-003: Plan content file-reference coherence check

**Priority:** P1 (this is the check that would have caught the incident)
**Source files:** `src/contextcore/cli/analyze_plan_ops.py`

When `--project-root` is provided, analyze-plan MUST extract file path references from the plan document and check whether they are plausible under PROJECT_ROOT.

**File path extraction:**
- Match patterns: `src/...`, `tests/...`, `scripts/...`, and any path-like string containing `/` with a recognized source extension (`.py`, `.go`, `.ts`, `.js`, `.java`, `.cs`, `.rs`)
- Match tactic deliverable summaries (already parsed by analyze-plan's phase metadata extraction)

**Coherence check:**
- For each extracted path prefix (e.g., `src/startd8/contractors/`), check if `PROJECT_ROOT/<prefix>` exists as a directory
- For each extracted file path, check if `PROJECT_ROOT/<file>` exists or if the parent directory exists

**Acceptance criteria:**
- If ≥1 extracted path prefix does not exist under PROJECT_ROOT, emit an `error` severity coherence finding
- Finding includes: the non-existent path, PROJECT_ROOT, and the plan line(s) where the path was referenced
- If all extracted paths are plausible, emit a `passed` coherence result
- If no file paths are extractable from the plan, emit an `info` result noting that coherence could not be verified

---

### REQ-PTC-004: Requirements file path coherence check

**Priority:** P2
**Source files:** `src/contextcore/cli/analyze_plan_ops.py`

When `--project-root` is provided, analyze-plan MUST check whether the requirements documents' locations are coherent with the project root, using the same logic as REQ-PTC-002 applied to each requirements file.

**Acceptance criteria:**
- If a requirements file lives under a directory hierarchy that does not contain the PROJECT_ROOT basename, emit a `warning` severity coherence finding
- Multiple requirements files are checked independently

---

### REQ-PTC-005: Requirements content source-file coherence check

**Priority:** P2
**Source files:** `src/contextcore/cli/analyze_plan_ops.py`

When `--project-root` is provided, analyze-plan MUST extract `Source files:` declarations from requirements documents and check whether the referenced paths exist under PROJECT_ROOT.

**Pattern:** Lines matching `**Source files:**` followed by comma-separated file paths (convention used in REQ-PEM-*, REQ-PC-* documents).

**Acceptance criteria:**
- If ≥1 declared source file path does not exist under PROJECT_ROOT, emit a `warning` severity coherence finding
- Finding includes: the non-existent path, the requirement ID that declared it

---

### REQ-PTC-006: Coherence results in plan-analysis.json

**Priority:** P1
**Source files:** `src/contextcore/cli/analyze_plan_ops.py`

The `plan-analysis.json` output MUST include a `coherence_checks` section when `--project-root` is provided.

**Schema:**
```json
{
  "coherence_checks": {
    "project_root": "/path/to/project",
    "status": "passed" | "warning" | "error",
    "checks": [
      {
        "check_id": "plan-file-location",
        "severity": "warning" | "error" | "info" | "passed",
        "message": "Human-readable description",
        "detail": {
          "plan_path": "...",
          "project_root": "...",
          "detected_hint": "..."
        }
      }
    ],
    "summary": {
      "total": 4,
      "passed": 2,
      "warnings": 1,
      "errors": 1
    }
  }
}
```

**Acceptance criteria:**
- `status` is the worst severity across all checks (`error` > `warning` > `passed`)
- Each check has a unique `check_id`, severity, message, and structured detail
- When `--project-root` is omitted, `coherence_checks` is absent from the output (not null, absent)

---

### REQ-PTC-007: Pipeline script consumes coherence results

**Priority:** P1
**Source files:** `run-cap-delivery.sh`, `run-atomic.sh`

The pipeline orchestration scripts MUST read `coherence_checks.status` from `plan-analysis.json` after Stage 1.5 completes. If status is `error`, the pipeline MUST halt before Stage 2 (init-from-plan) with a clear diagnostic message.

**Acceptance criteria:**
- `run-cap-delivery.sh` reads `plan-analysis.json` after analyze-plan
- If `coherence_checks.status == "error"`, pipeline halts with exit code 1
- Error message includes the specific failing check(s) and remediation guidance
- If `coherence_checks.status == "warning"`, pipeline logs the warnings but continues
- User can bypass with `--skip-analyze` (existing flag, which already skips Stage 1.5 entirely)

---

### REQ-PTC-008: Init-from-plan cross-validates target name

**Priority:** P2
**Source files:** `src/contextcore/cli/init_from_plan_ops.py`

When `--project-root` is provided and `plan-analysis.json` (via `--plan-analysis`) contains `coherence_checks`, `init-from-plan` MUST check the coherence status before setting `spec.targets[0].name`.

**Acceptance criteria:**
- If plan-analysis coherence status is `error`, init-from-plan emits a warning in the inference report noting the target name may be incorrect
- The warning is advisory — init-from-plan does not halt (Stage 1.5 is responsible for gating)
- If plan-analysis is not provided (standalone init-from-plan usage), no change in behavior

---

## Pipeline Flow After Implementation

```text
  Stage 1.5: ANALYZE-PLAN
    ├── Phase extraction (existing)
    ├── Traceability matrix (existing)
    ├── Dependency graph (existing)
    └── Coherence checks (NEW — REQ-PTC-001 through REQ-PTC-006)
         ├── Plan file location vs PROJECT_ROOT
         ├── Plan content file-refs vs PROJECT_ROOT
         ├── Requirements file location vs PROJECT_ROOT
         └── Requirements source-file declarations vs PROJECT_ROOT

  ↓ plan-analysis.json (with coherence_checks section)

  run-cap-delivery.sh reads coherence_checks.status (REQ-PTC-007)
    ├── error → HALT before Stage 2
    ├── warning → log and continue
    └── passed → continue

  Stage 2: INIT-FROM-PLAN
    └── Cross-validate target name (REQ-PTC-008, advisory)
```

---

## Incident That Motivated This Requirement

| Field | Value |
|-------|-------|
| Date | 2026-02-20 |
| Run | `pipeline-output/startd8-prime-execution-modes/run-002-20260220T1636` |
| Plan | `PRIME_EXECUTION_MODES_PLAN.md` (targets `src/startd8/contractors/`) |
| PROJECT_ROOT | `~/Documents/dev/online-boutique-python` (wrong — should have been `~/Documents/dev/startd8-sdk`) |
| Cost | $10.42 (19 tasks × artisan route) |
| Recovery | Files moved to `startd8-sdk/tmp/` per Mottainai principle |
| Checks that would have caught it | REQ-PTC-002 (plan under `startd8-sdk/docs/`), REQ-PTC-003 (`src/startd8/contractors/` does not exist under `online-boutique-python/`) |

---

## Testing

| Requirement | Test approach |
|-------------|---------------|
| REQ-PTC-001 | Unit test: `analyze-plan --project-root /valid/path` accepts parameter |
| REQ-PTC-002 | Unit test: plan under `project-a/` with `--project-root project-b/` produces warning |
| REQ-PTC-003 | Unit test: plan referencing `src/foo/bar.py` with `--project-root` lacking `src/foo/` produces error |
| REQ-PTC-004 | Unit test: requirements under `project-a/` with `--project-root project-b/` produces warning |
| REQ-PTC-005 | Unit test: requirements with `**Source files:** src/foo.py` and non-existent path produces warning |
| REQ-PTC-006 | Unit test: `plan-analysis.json` contains `coherence_checks` section with correct schema |
| REQ-PTC-007 | Integration test: pipeline halts when coherence status is `error` |
| REQ-PTC-008 | Unit test: init-from-plan logs advisory warning when coherence status is `error` |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-20 | Initial version: 8 requirements (REQ-PTC-001 through REQ-PTC-008) motivated by startd8-prime-execution-modes incident |
