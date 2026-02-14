# A2A Gate Requirements

Purpose: define the behavioral requirements for `contextcore contract a2a-check-pipeline` (Gate 1) and `contextcore contract a2a-diagnose` (Gate 2) — the governance validation commands that ensure pipeline integrity at handoff boundaries.

This document is intentionally living guidance. Update it as the gate implementations evolve.

---

## Vision

The A2A governance gates enforce the defense-in-depth principle that each pipeline step must validate the output of the previous step before proceeding. Without these gates, a defect in export can cascade silently through plan ingestion and into contractor execution — producing incorrect artifacts that are expensive to debug.

Two commands implement the gates:

- **`a2a-check-pipeline`** (Gate 1): Runs after export, before plan ingestion. Validates structural integrity and internal consistency of the export output. This is the "building inspector checks the blueprint" step.
- **`a2a-diagnose`** (Gate 2): Runs after plan ingestion (and optionally after contractor execution). Asks three diagnostic questions to locate the root cause of pipeline issues. This is the "structured quality audit" step.

**Core principle**: Always start from the source. If the contract is incomplete (Q1), fixing translation (Q2) or execution (Q3) is wasted effort.

---

## Pipeline Placement

Steps 3 and 5 of the 7-step A2A governance-aware pipeline:

1. `contextcore install init` — infrastructure readiness
2. `contextcore manifest export` — produce contract
3. **`contextcore contract a2a-check-pipeline`** — Gate 1 (6 integrity checks)
4. `startd8 workflow run plan-ingestion` — translate contract to work items
5. **`contextcore contract a2a-diagnose`** — Gate 2 (Three Questions diagnostic)
6. Contractor execution — structured build
7. Finalize verification — Gate 3

Gate 1 validates the handoff from ContextCore to plan ingestion. Gate 2 validates the handoff from plan ingestion to contractor execution, and optionally validates the contractor output itself (Gate 3 scope).

---

## Gate 1: `a2a-check-pipeline`

### Purpose

Run structural integrity checks on a real export output directory. Reads `onboarding-metadata.json` (required) and `provenance.json` (optional) from the output directory.

### Functional Requirements

#### Gate Suite

The checker runs 6 gates in a fixed order. Gates 1–2 always run. Gates 3–6 are skipped when their input data is absent.

1. **Structural integrity**
   - Must verify that all required top-level fields exist in `onboarding-metadata.json`: `version`, `schema`, `project_id`, `generated_at`, `coverage`, `artifact_manifest_checksum`, `project_context_checksum`, `source_checksum`.
   - Must verify referenced files exist on disk (artifact manifest, project context CRD).
   - Must verify enrichment fields are present and well-formed: `derivation_rules`, `expected_output_contracts`, `file_ownership`.
   - **Outcome**: PASS if all required fields present and files exist. FAIL if any required field missing or file not found.

2. **Checksum chain**
   - Must recompute SHA-256 checksums of the artifact manifest and project context CRD files.
   - Must compare recomputed checksums against stored values in `onboarding-metadata.json`.
   - Must attempt to verify source checksum if `source_path_relative` is provided.
   - **Outcome**: PASS if all recomputed checksums match stored values. FAIL if any mismatch detected.

3. **Provenance consistency** (skipped if `provenance.json` absent)
   - Must cross-check source checksum between `onboarding-metadata.json` and `provenance.json`.
   - Must verify `project_id` consistency across both files.
   - Must verify timestamps are consistent (provenance timestamp ≤ onboarding timestamp).
   - **Outcome**: PASS if all cross-checks match. FAIL if any inconsistency. SKIPPED if no provenance file.

4. **Mapping completeness** (skipped if no `artifact_task_mapping` present)
   - Must verify every coverage gap has a corresponding entry in the task mapping.
   - Must report unmapped gaps.
   - **Outcome**: PASS if all gaps are mapped. FAIL if any gap lacks a mapping. SKIPPED if no task mapping.

5. **Gap parity** (skipped if no coverage data)
   - Must compare coverage gaps against known artifact IDs (from `file_ownership` or artifact manifest).
   - Must detect gaps that reference unknown artifacts and features that have no corresponding gap.
   - **Outcome**: PASS if gaps and features align. FAIL if mismatch detected.

6. **Design calibration** (skipped if no `design_calibration_hints` present)
   - Must verify `design_calibration_hints` covers all artifact types with gaps.
   - Must validate each hint has: `expected_depth` (brief/standard/comprehensive), `expected_loc_range`, `red_flag`.
   - Must cross-check against `expected_output_contracts` for `max_lines` consistency if both exist.
   - Must validate generated artifact sizes against expected ranges if artifacts exist on disk.
   - **Outcome**: PASS if hints are complete and consistent. FAIL if misaligned.

#### Report Structure

7. **Report output**
   - Must produce a structured report with: overall health status (healthy/degraded/unhealthy), per-gate outcomes, evidence items, recommendations.
   - Must support `text` and `json` output formats.
   - Must support writing the report to a JSON file via `--report`.

#### Exit Behavior

8. **Exit codes**
   - Default: Always exit 0 (report-only mode).
   - With `--fail-on-unhealthy`: Exit 1 if any blocking gate fails.
   - Gates that are skipped do not contribute to unhealthy status.

### CLI Surface

```
contextcore contract a2a-check-pipeline <output_dir>
  output_dir            (required)   Export output directory
  --task-id             (optional)   Task span ID for gate context
  --trace-id            (optional)   Trace ID for gate context
  --report / -r         (optional)   Write JSON report to file
  --format              (default: text)  Output format: text | json
  --fail-on-unhealthy   (flag)       Exit 1 if any blocking gate fails
```

### Non-Functional Requirements

- **Offline operation**: Must work without network access.
- **Read-only**: Must not modify any files in the output directory.
- **Determinism**: Same input must produce the same report.
- **Performance**: Must complete in under 2 seconds for typical export output.

---

## Gate 2: `a2a-diagnose`

### Purpose

Run the Three Questions diagnostic on a pipeline execution. Walks through questions in strict order, stopping at the first failure. This prevents wasting effort on downstream issues when the upstream contract is broken.

### Functional Requirements

#### Diagnostic Questions

The diagnostic asks three questions in order. Each question checks a different pipeline layer.

1. **Q1: Is the contract complete?** (Export layer)
   - Must run Gate 1 (`PipelineChecker`) as a sub-check.
   - Must verify coverage completeness: artifact manifest lists every required artifact.
   - Must verify derivation rules are populated with real (non-placeholder) values.
   - Must verify parameter schemas are complete.
   - Must verify enrichment fields are present.
   - **Pass criteria**: Gate 1 passes AND coverage/derivation/schema checks pass.
   - **On failure**: Stop. Recommend fixing export before proceeding.

2. **Q2: Was the contract faithfully translated?** (Plan Ingestion layer)
   - Requires `--ingestion-dir` to be provided. Skipped if absent.
   - Must verify plan ingestion output exists (seed files, configuration).
   - Must verify PARSE phase: every coverage gap was extracted as a feature.
   - Must verify ASSESS phase: complexity scores are present and reasonable.
   - Must verify TRANSFORM phase: routing decisions match complexity scores.
   - Must verify REFINE phase: architectural review evidence exists.
   - **Pass criteria**: All phase checks pass.
   - **On failure**: Stop. Recommend fixing plan ingestion before proceeding.

3. **Q3: Was the translated plan faithfully executed?** (Contractor layer)
   - Requires `--artisan-dir` to be provided. Skipped if absent.
   - Must verify contractor output directory exists.
   - Must verify generated artifact files exist.
   - Must verify finalize report exists (searches for `*finalize*report*.json`, `*execution*report*.json`, `workflow-execution-report.json`).
   - Must verify finalize report shows all tasks succeeded.
   - **Pass criteria**: Artifacts exist AND finalize report shows success.
   - **On failure**: Recommend investigating contractor execution issues.

#### Stop-at-First-Failure Behavior

4. **Sequential execution with early termination**
   - Must run questions in order: Q1 → Q2 → Q3.
   - Must stop at the first failing question.
   - Questions not reached must be reported as `not_reached` (not `skipped`).
   - Questions whose input data is missing must be reported as `skipped`.

#### Report Structure

5. **Diagnostic report**
   - Must produce a structured report with: per-question status (pass/fail/skipped/not_reached), per-check details, recommendations.
   - Must include a "start here" recommendation pointing to the first failing question.
   - Must support `text` and `json` output formats.
   - Must support writing the report to a JSON file via `--report`.

#### Exit Behavior

6. **Exit codes**
   - Default: Always exit 0 (report-only mode).
   - With `--fail-on-issue`: Exit 1 if any question fails.
   - Skipped questions do not contribute to failure.

### CLI Surface

```
contextcore contract a2a-diagnose <export_dir>
  export_dir            (required)   Export output directory
  --ingestion-dir       (optional)   Plan ingestion output directory (enables Q2)
  --artisan-dir         (optional)   Artisan workflow output directory (enables Q3)
  --trace-id            (optional)   Trace ID for gate context
  --report / -r         (optional)   Write JSON diagnostic report to file
  --format              (default: text)  Output format: text | json
  --fail-on-issue       (flag)       Exit 1 if any question fails
```

### Non-Functional Requirements

- **Offline operation**: Must work without network access.
- **Read-only**: Must not modify any files in any directory.
- **Determinism**: Same input must produce the same diagnostic.
- **Composability**: Q1 reuses Gate 1 (`PipelineChecker`) — must not duplicate that logic.
- **Performance**: Must complete in under 3 seconds for typical pipeline output.

---

## Invariants

These must hold true for all gate executions:

1. Gates never modify files. They are strictly read-only.
2. Skipped gates are clearly distinguished from failed gates in all output formats.
3. Q1 in `a2a-diagnose` produces the same Gate 1 results as running `a2a-check-pipeline` independently.
4. A pipeline where all 6 Gate 1 checks pass will always pass Q1 in `a2a-diagnose`.
5. If Q1 fails, Q2 and Q3 are reported as `not_reached` (not `pass` or `skipped`).

---

## Blocking vs Advisory Behavior

| Gate | Default | With fail flag |
|------|---------|----------------|
| Gate 1 (check-pipeline) | Advisory (exit 0, print report) | Blocking (`--fail-on-unhealthy` → exit 1) |
| Gate 2 (diagnose) | Advisory (exit 0, print report) | Blocking (`--fail-on-issue` → exit 1) |

CI/CD pipelines should use the fail flags to enforce gates. Interactive use defaults to advisory mode for exploration.

---

## Relationship to Other Commands

| Command | Relationship |
|---------|-------------|
| `manifest export` | Upstream — produces the output that gates validate |
| `manifest export --verify` (planned) | Inline invocation of Gate 1 within export |
| `a2a-check-pipeline` → `a2a-diagnose` | Gate 1 is a sub-check within Gate 2's Q1 |
| `a2a-pilot` | End-to-end simulation of all gates with synthetic data |
| `a2a-validate` | Schema-level validation of individual contract payloads (different scope) |
| `a2a-gate` | Low-level gate runner for individual gate types (building block) |

---

## Related Docs

- `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` — 7-step pipeline, defense-in-depth principles
- `docs/design/contextcore-a2a-comms-design.md` — A2A governance architecture
- `docs/A2A_CONTRACTS_DESIGN.md` — contract type definitions
- `docs/A2A_V1_GOVERNANCE_POLICY.md` — governance policy (schema versioning, gate requirements)
- `docs/A2A_QUICKSTART.md` — 5-minute quickstart
- `docs/MANIFEST_EXPORT_REQUIREMENTS.md` — export command requirements
- `src/contextcore/contracts/a2a/pipeline_checker.py` — Gate 1 implementation
- `src/contextcore/contracts/a2a/three_questions.py` — Gate 2 implementation
