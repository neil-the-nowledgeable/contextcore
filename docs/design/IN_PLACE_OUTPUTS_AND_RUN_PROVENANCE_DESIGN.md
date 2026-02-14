# ContextCore In-Place Outputs + Run Provenance Design

**Version:** 1.0.0  
**Created:** 2026-02-14  
**Scope:** `contextcore manifest init`, `contextcore manifest export`, `contextcore generate`

---

## Intent

Apply the same operational pattern now used in `startd8 plan-ingestion` to ContextCore:

1. Prefer stable, in-place output paths by default (avoid version-sprawl files).
2. Emit a per-run provenance artifact that records exactly what inputs were read and what outputs were written.

This design is additive and low-disruption: existing artifacts remain, while a new run-level lineage file improves trust and debugging.

---

## Why this is the simplest safe path

- Keeps existing command boundaries intact (`init` -> `export` -> downstream).
- Reuses current atomic write and deterministic quality profile patterns.
- Adds provenance as a side artifact instead of changing existing schemas.
- Preserves current output contracts while improving freshness and traceability.

---

## Design Principles

1. **Stable canonical paths first:** default to writing/updating known output files in-place.
2. **Explicit override allowed:** users can still choose alternate paths when needed.
3. **Non-destructive writes:** atomic writes with backup for mutable docs/artifacts.
4. **Lineage by default in strict workflows:** every run can be audited without log scraping.
5. **No external dependencies:** provenance is filesystem-based (path, mtime, checksum).

---

## Proposed behavior by command

## 1) `contextcore manifest init`

### Current role

Creates (or scaffolds) `.contextcore.yaml`.

### Proposed addition

- Add optional write strategy semantics:
  - default `update_existing` when target manifest path exists,
  - fallback create if no file exists.
- Emit `init-run-provenance.json` next to the generated/updated manifest (or in configured output dir), including:
  - run metadata (run_id, timestamps, command version),
  - source inputs used by `init` or `init-from-plan` (plan docs, requirements docs, discovered metadata inputs),
  - written outputs (`.contextcore.yaml`, optional support files),
  - checksum and mtime fingerprints.

### Notes

- `init-from-plan` should include inferred-field evidence in provenance (which sections contributed to which manifest fields).

---

## 2) `contextcore manifest export`

### Current role

Transforms `.contextcore.yaml` into contract artifacts (`artifact-manifest`, `project-context`, `onboarding-metadata`, validation report, optional quality report/provenance).

### Proposed addition

- Keep canonical output filenames stable and in-place by default:
  - `{project}-artifact-manifest.(yaml|json)`
  - `{project}-projectcontext.(yaml|json)`
  - `onboarding-metadata.json`
  - `validation-report.json`
  - optional `export-quality-report.json`
- Add `run-provenance.json` as a first-class run artifact (complementary to existing optional `provenance.json`):
  - full input list with fingerprinting:
    - `.contextcore.yaml`
    - quality policy files (for example `.contextcore-quality.yaml`)
    - mapping files (for example `--task-mapping`)
    - scanned paths used by `--scan-existing` and allowlist decisions,
  - output list with fingerprinting for every written artifact,
  - quality gate summary (strict mode decisions, coverage metrics, schema/version pin checks),
  - route/handoff references for downstream consumption.

### Notes

- Keep current `provenance.json` behavior for backward compatibility.
- `run-provenance.json` is the consolidated execution lineage document for operators and CI.

---

## 3) `contextcore generate`

### Current role

Generates concrete artifacts from manifest/context inputs.

### Proposed addition

- Default in-place update behavior for generated targets (especially in strict-quality mode).
- Emit `run-provenance.json` at generation output root, including:
  - generation inputs (manifest, export artifacts, config/policy),
  - generated outputs (file-level path/mtime/sha256),
  - quality profile used (`strict-quality`, deterministic options, min-coverage gates if applicable),
  - links to upstream provenance files (`export` provenance, onboarding metadata).

---

## Cross-command contract

All ContextCore run-provenance artifacts should share a consistent schema envelope:

1. `run_id`, `workflow_or_command`, `version`, `started_at`, `completed_at`
2. `config_snapshot` (selected reproducibility keys)
3. `inputs[]` entries:
   - `path`, `exists`, `mtime`, `sha256`, optional `role`
4. `outputs[]` entries:
   - `path`, `exists`, `mtime`, `sha256`, optional `role`
5. `quality_summary` (where applicable)
6. `artifact_references` (links to validation/quality/onboarding artifacts)

This keeps machine consumption straightforward across commands.

---

## CLI/UX proposal (minimal)

Apply uniformly where meaningful:

- `--document-write-strategy update_existing|new_output` (default `update_existing`)
- command-specific explicit output path override where applicable
- `--emit-run-provenance / --no-emit-run-provenance`
  - recommended default: enabled in strict-quality mode, optional otherwise

---

## Rollout plan

### Phase 1 (low risk)

1. Add write-strategy + explicit path handling to commands that directly write mutable docs.
2. Emit `run-provenance.json` with filesystem fingerprints.
3. Keep all existing outputs and flags unchanged.

### Phase 2 (quality hardening)

1. Freshness warnings when source input is newer than prior run provenance.
2. Optional CI checks that require provenance and validate input/output consistency.

### Phase 3 (pipeline integration)

1. Link ContextCore run provenance into StartD8 preflight and handoff checks.
2. Correlate with A2A/OTel spans for full pipeline observability.

---

## Risks and mitigations

1. **Risk:** accidental overwrite concerns  
   **Mitigation:** atomic writes + backup, explicit `new_output` escape hatch.

2. **Risk:** confusion between old and new provenance files  
   **Mitigation:** document roles clearly (`provenance.json` legacy/command-specific vs `run-provenance.json` run lineage).

3. **Risk:** minor runtime overhead from hashing  
   **Mitigation:** scoped to touched files and local filesystem only.

---

## Acceptance criteria

1. Re-running `init`, `export`, or `generate` does not create unnecessary variant files by default.
2. Each run emits a provenance artifact sufficient to reconstruct input/output lineage.
3. Strict-quality runs can be audited from artifacts alone (without terminal logs).
4. Existing command output contracts remain backward compatible.

---

## Related references

- `docs/design/MANIFEST_EXPORT_REQUIREMENTS.md`
- `docs/design/contextcore-a2a-comms-design.md`
- `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md`
- `startd8-sdk/docs/PLAN_INGESTION_IN_PLACE_PROVENANCE_REQUIREMENTS.md`
