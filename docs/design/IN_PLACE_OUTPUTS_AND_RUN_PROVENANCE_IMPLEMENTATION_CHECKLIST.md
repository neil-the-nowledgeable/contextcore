# ContextCore In-Place Outputs + Run Provenance Implementation Checklist

**Version:** 1.0.0  
**Created:** 2026-02-14  
**Companion design:** `docs/design/IN_PLACE_OUTPUTS_AND_RUN_PROVENANCE_DESIGN.md`

---

## Objective

Implement a low-risk, phased rollout for ContextCore so that:

1. output files are updated in stable in-place locations by default, and
2. each run emits a run-level provenance artifact with input/output lineage.

This checklist is scoped to current command entrypoints and helper modules:

- `src/contextcore/cli/manifest.py`
- `src/contextcore/cli/core.py`
- `src/contextcore/cli/export_io_ops.py`
- `src/contextcore/utils/provenance.py`

---

## Phase 0: Guardrails and schema

- [x] **Define run provenance schema envelope**
  - **File:** `src/contextcore/utils/provenance.py`
  - **Insertion point:** add new helper models/functions near `capture_provenance()` / `write_provenance_file()`.
  - **Action:**
    - Add a `build_run_provenance_payload(...)` helper (dict-based is acceptable initially).
    - Include fields: `run_id`, `workflow_or_command`, `version`, `started_at`, `completed_at`, `config_snapshot`, `inputs`, `outputs`, `quality_summary`, `artifact_references`.
  - **Acceptance:** payload shape is stable and reused across commands.

- [x] **Add file fingerprint helper**
  - **File:** `src/contextcore/utils/provenance.py`
  - **Insertion point:** near `get_file_checksum()`.
  - **Action:** implement helper returning `{path, exists, mtime, sha256}`.
  - **Acceptance:** missing files are tolerated (`exists=false`, null checksum/mtime).

---

## Phase 1: `manifest export` (highest leverage first)

### 1. CLI inputs and defaults

- [x] **Add write strategy options**
  - **File:** `src/contextcore/cli/manifest.py`
  - **Insertion point:** `@manifest.command()` `export(...)` options block.
  - **Action:**
    - Add `--document-write-strategy update_existing|new_output` (default `update_existing`).
    - Add optional explicit target-path overrides only where needed (keep minimal: primarily manifest/output root reuse).
  - **Acceptance:** default behavior preserves canonical filenames and avoids variant filenames.

### 2. Output path resolution

- [x] **Centralize export output resolution**
  - **File:** `src/contextcore/cli/export_io_ops.py`
  - **Insertion point:** before `write_export_outputs(...)`.
  - **Action:**
    - Add helper `resolve_export_output_paths(...)` that returns concrete canonical file paths for:
      - project context
      - artifact manifest
      - onboarding metadata
      - validation report
      - quality report
      - provenance artifacts
    - Keep current filenames unless explicit override is provided.
  - **Acceptance:** all writes route through this resolver.

### 3. Safe write behavior

- [x] **Switch export writes to atomic write with backup**
  - **File:** `src/contextcore/cli/export_io_ops.py`
  - **Insertion point:** inside `write_export_outputs(...)` where `Path.write_text(...)` is currently used.
  - **Action:** replace direct writes with atomic write helper (existing project helper or utility).
  - **Acceptance:** in-place updates are crash-safe and non-destructive.

### 4. Run provenance emission

- [x] **Emit `run-provenance.json` from export command**
  - **File:** `src/contextcore/cli/manifest.py`
  - **Insertion point:** after `file_results = write_export_outputs(...)` and before success print.
  - **Action:**
    - Build run provenance payload including:
      - input files: manifest, policy file, task mapping, scan directory references (as applicable),
      - output files written this run,
      - quality summary from validation/coverage.
    - Write `run-provenance.json` under `output_dir`.
  - **Acceptance:** successful export always produces run provenance when enabled by policy/flag.

- [x] **Expose path in user output**
  - **File:** `src/contextcore/cli/export_io_ops.py`
  - **Insertion point:** `print_export_success(...)`.
  - **Action:** print `run-provenance.json` location in success summary.
  - **Acceptance:** operator can locate lineage artifact immediately from CLI output.

---

## Phase 2: `manifest init` and `init-from-plan`

### 1. `manifest init` in-place strategy

- [x] **Add write strategy to `init`**
  - **File:** `src/contextcore/cli/manifest.py`
  - **Insertion point:** `init(...)` options and function args.
  - **Action:**
    - Add `--document-write-strategy update_existing|new_output` (default `update_existing`).
    - Keep `--force` semantics; strategy should not silently overwrite when policy forbids it.
  - **Acceptance:** existing `.contextcore.yaml` can be updated in place when intended.

### 2. `init` run provenance

- [x] **Emit `init-run-provenance.json`**
  - **File:** `src/contextcore/cli/manifest.py`
  - **Insertion point:** after successful write/validation in `init(...)`.
  - **Action:** capture inputs (template version, CLI opts), output file fingerprint, and timing.
  - **Acceptance:** each init run has a lineage artifact.

### 3. `init-from-plan` run provenance

- [x] **Emit provenance with inference evidence**
  - **File:** `src/contextcore/cli/manifest.py`
  - **Insertion point:** inside `init_from_plan(...)` around report writing.
  - **Action:**
    - Include plan + requirements fingerprints.
    - Include `inference` summary references (`core_inferred_count`, readiness verdict).
    - Include output manifest + report file fingerprints.
  - **Acceptance:** provenance proves which source docs fed inferred manifest fields.

---

## Phase 3: `generate`

### 1. Add strategy and provenance flags

- [x] **Extend `generate` CLI surface**
  - **File:** `src/contextcore/cli/core.py`
  - **Insertion point:** `generate(...)` option decorators.
  - **Action:**
    - Add `--document-write-strategy update_existing|new_output` (default `update_existing`).
    - Add `--emit-run-provenance/--no-emit-run-provenance` (default enabled in strict mode).
  - **Acceptance:** generation mode can be controlled consistently with export/init.

### 2. Refactor writes for safety and consistency

- [x] **Centralize artifact file target resolution**
  - **File:** `src/contextcore/cli/core.py`
  - **Insertion point:** just before artifact write blocks (`service_monitor`, `prometheus_rule`, `dashboard`).
  - **Action:** compute target paths once, then write atomically with backup.
  - **Acceptance:** reruns update canonical files, no accidental variant growth.

### 3. Emit generate run provenance

- [x] **Write `run-provenance.json` in output dir**
  - **File:** `src/contextcore/cli/core.py`
  - **Insertion point:** after generation report creation (`generation-report.json`) and before return.
  - **Action:**
    - Inputs: context identifier, fetched ProjectContext snapshot checksum (if serializable), strict flags.
    - Outputs: generated artifact files + generation report.
    - Quality summary: strict checks status.
  - **Acceptance:** downstream systems can tie generation artifacts to exact run inputs.

---

## Phase 4: Policy and defaults

- [x] **Add policy keys for run provenance behavior**
  - **File:** `.contextcore-quality.yaml` (repo root)
  - **Insertion point:** strict quality policy section.
  - **Action:** add policy toggles like:
    - `emit_run_provenance_default`
    - `document_write_strategy_default`
  - **Acceptance:** org-level defaults are centralized and CI-friendly.

- [x] **Strict-mode defaulting rule**
  - **File:** `src/contextcore/cli/manifest.py`, `src/contextcore/cli/core.py`
  - **Insertion point:** where strict profile toggles are currently resolved.
  - **Action:** in strict mode, force run provenance on unless explicitly disabled by policy exception.
  - **Acceptance:** production-quality runs always produce lineage evidence.

---

## Phase 5: Tests

## 1) Unit tests to add

- [ ] **Export output path resolution tests**
  - **Target file:** `tests/unit/test_manifest_export_in_place.py` (new)
  - **Coverage:** default update_existing, explicit override, fallback behavior.

- [ ] **Export run provenance payload tests**
  - **Target file:** `tests/unit/test_manifest_export_provenance.py` (new)
  - **Coverage:** required fields, fingerprint integrity, artifact references.

- [ ] **Init/init-from-plan provenance tests**
  - **Target file:** `tests/unit/test_manifest_init_provenance.py` (new)
  - **Coverage:** input doc fingerprints, manifest output fingerprint, strict validation path.

- [ ] **Generate in-place + provenance tests**
  - **Target file:** `tests/unit/test_generate_in_place_provenance.py` (new)
  - **Coverage:** canonical file updates, report + provenance presence, strict mode behavior.

## 2) Regression tests

- [ ] **Backward compatibility**
  - Existing expected output filenames must remain unchanged unless explicitly overridden.
- [ ] **No network dependency**
  - Provenance generation must pass in offline test environments.

---

## Phase 6: Documentation updates

- [ ] **Manifest export requirements update**
  - **File:** `docs/design/MANIFEST_EXPORT_REQUIREMENTS.md`
  - **Action:** add run-provenance functional requirements and CLI flags.

- [ ] **Onboarding metadata/schema docs**
  - **Files:** `docs/design/ONBOARDING_METADATA_SCHEMA.md`, `docs/design/VALIDATION_REPORT_SCHEMA.md`
  - **Action:** reference run provenance linkage fields (artifact references, source checksums).

- [ ] **Operational guide update**
  - **File:** `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md`
  - **Action:** add run provenance checks in gate/runbook steps.

---

## Cutover and validation runbook

- [ ] Run `contextcore manifest init` with default strategy; verify in-place behavior and `init-run-provenance.json`.
- [ ] Run `contextcore manifest init-from-plan` with requirements docs; verify provenance evidence and report linkage.
- [ ] Run `contextcore manifest export --strict-quality`; verify `run-provenance.json` and canonical outputs.
- [ ] Run `contextcore generate --strict-quality`; verify canonical artifact updates and `run-provenance.json`.
- [ ] Re-run commands after editing source inputs; confirm provenance reflects new checksums/mtimes.
- [ ] Validate downstream Gate 1/2 still pass with no contract regressions.

---

## Done criteria

- [ ] All three commands (`init`, `export`, `generate`) support stable in-place defaults.
- [ ] All three commands can emit run-level provenance with standardized schema envelope.
- [ ] Strict-quality runs produce lineage artifacts by default.
- [ ] Tests cover path resolution, provenance integrity, and backward compatibility.
