# Manifest Export Troubleshooting Guide

Common issues when using `contextcore manifest export` and related tooling.

## Checksum Mismatch

**Symptom:** Downstream tooling reports `artifact_manifest_checksum` or `project_context_checksum` does not match the file content.

**Causes:**
- File was edited after export
- File was regenerated with different parameters
- Encoding or line-ending differences

**Resolution:**
1. Re-run export: `contextcore manifest export -p .contextcore.yaml -o ./output --emit-onboarding`
2. Verify no manual edits to generated files; use `--scan-existing` to mark existing artifacts
3. Ensure consistent encoding (UTF-8) and line endings (LF) if comparing across systems

---

## Plan vs Context Mismatch

**Symptom:** Plan document references "77 artifacts (7 × 11 services)" but the artifact manifest has only 6 artifacts for a single target.

**Explanation:** The plan is often generic (e.g., Online Boutique example) while the context files are project-specific (e.g., wayfinder with one target). This is expected.

**Resolution:**
1. If intentional: Document the mismatch in plan ingestion output (e.g., `plan_vs_context_note`)
2. If incorrect: Ensure the plan and `.contextcore.yaml` target the same project. Update the plan or manifest so they align.

---

## Missing Onboarding Metadata

**Symptom:** `onboarding-metadata.json` is not present in the output directory.

**Causes:**
- `--no-onboarding` was passed
- Export failed before writing onboarding metadata

**Resolution:**
1. Run without `--no-onboarding`: `contextcore manifest export -p .contextcore.yaml -o ./output`
2. Check for export errors; onboarding is written after artifact manifest and CRD
3. Verify write permissions on the output directory

---

## Coverage Below Minimum

**Symptom:** Export fails with "Coverage X% is below minimum Y%".

**Cause:** `--min-coverage` was set and current coverage is below the threshold.

**Resolution:**
1. Omit `--min-coverage` if you want to allow any coverage
2. Use `--scan-existing` to mark existing artifacts and increase coverage
3. Add artifacts: `--existing "artifact-id:path/to/file"` for each existing artifact

---

## Pre-flight Validation Failed

**Symptom:** Export aborts with "Manifest validation failed before export".

**Cause:** The context manifest has validation errors (schema, cross-references, blocked tactics without reason).

**Resolution:**
1. Run `contextcore manifest validate -p .contextcore.yaml` to see errors
2. Fix validation errors (e.g., add `blockedReason` for blocked tactics, fix cross-references)
3. Re-run export after validation passes

---

## Artifact Manifest Requires v2

**Symptom:** "Artifact manifest generation requires v2 manifest".

**Cause:** The manifest is v1.1; export only works with v2.

**Resolution:**
1. Migrate: `contextcore manifest migrate -p .contextcore.yaml --in-place`
2. Or create a new v2 manifest: `contextcore manifest init --name my-project --version v2`

---

## Provenance Not Captured

**Symptom:** `provenance` in onboarding-metadata.json is null; `source_checksum` is missing.

**Cause:** `--emit-provenance` was not used. Provenance is optional but **required for A2A governance gates**.

**Resolution:**
1. Use `--emit-provenance` to capture full provenance and `source_checksum`
2. `source_checksum` can still be populated from the source file when provenance is absent if `source_path` is available to the onboarding builder
3. **Note:** The `checksum-chain` gate uses checksums from `onboarding-metadata.json` and works without provenance. The `provenance-consistency` gate (1 of 6) is skipped without `--emit-provenance`. Use `--emit-provenance` for full 6/6 gate coverage

---

## Schema Version Mismatch

**Symptom:** Consumer expects `schemaVersion` or `version` 1.0.0 but gets a different value.

**Cause:** Version drift between ContextCore, artifact manifest, and onboarding metadata.

**Resolution:**
1. Upgrade ContextCore to a version that uses `SCHEMA_VERSION = "1.0.0"`
2. Check `metadata.schemaVersion` in artifact manifest and `version` in onboarding-metadata.json
3. Consumers should branch on version for compatibility

---

## A2A Pipeline Checker Fails (Gate 1)

**Symptom:** `contextcore contract a2a-check-pipeline` reports one or more gate failures.

**Individual gate failures:**

| Failed Gate | Likely Cause | Resolution |
|-------------|-------------|------------|
| `structural-integrity` | Missing export files (CRD, artifact manifest, onboarding metadata) | Re-run export; check output directory |
| `checksum-chain` | Stale export or missing provenance | Re-run with `--emit-provenance`; do not hand-edit exported files |
| `provenance-consistency` | Git metadata mismatch or export from dirty worktree | Commit changes before exporting; verify git state |
| `mapping-completeness` | Targets in manifest don't have corresponding artifacts | Check `spec.targets` — each target should produce artifacts |
| `gap-parity` | Coverage gaps don't match parsed feature count | Verify `--scan-existing` is used if artifacts already exist |
| `design-calibration` | Artifact depth tiers don't match type expectations | Check `expected_output_contracts` in onboarding metadata |

**General resolution:**
1. Read the `GateResult` output — it includes `failed_gate`, `reason`, and `next_action`
2. Fix the upstream issue (usually in the manifest or export flags)
3. Re-run export and re-run the checker

---

## A2A Three Questions Diagnostic Fails (Gate 2)

**Symptom:** `contextcore contract a2a-diagnose` stops at a failing question.

| Failing Question | What it means | Resolution |
|-----------------|---------------|------------|
| Q1: Contract not complete | Artifact manifest is missing required artifacts or enrichment fields | Re-run export with fully populated manifest; check `derivation_rules` and `expected_output_contracts` |
| Q2: Not faithfully translated | Plan ingestion dropped artifacts or routed incorrectly | Check plan ingestion output; verify all `coverage.gaps` appear as features |
| Q3: Not faithfully executed | Contractor failed to generate or finalize some artifacts | Check contractor logs and finalize report; re-run failed tasks |

**Key insight:** The diagnostic stops at the first failing question. If Q1 fails, don't investigate Q2 or Q3 — fix the export first.

---

## Missing Enrichment Fields

**Symptom:** A2A pipeline checker warns about missing enrichment fields; downstream consumers report incomplete context.

**Expected enrichment fields in onboarding-metadata.json:**

| Field | Source | Fix if missing |
|-------|--------|---------------|
| `derivation_rules` | Derived from manifest `spec.business.criticality` + `spec.requirements` | Ensure manifest has populated business and requirements sections |
| `expected_output_contracts` | Derived from artifact types and criticality | Ensure at least one target exists in manifest |
| `artifact_dependency_graph` | Derived from artifact type relationships | Normal for simple projects to have empty graph |
| `open_questions` | From `guidance.questions` with `status: open` | Add open questions to manifest or accept empty |
| `file_ownership` | From resolved artifact output paths | Ensure export has targets to derive paths from |

---

## Related

- [MANIFEST_ONBOARDING_GUIDE.md](./MANIFEST_ONBOARDING_GUIDE.md)
- [ONBOARDING_METADATA_SCHEMA.md](./ONBOARDING_METADATA_SCHEMA.md)
- [ARTIFACT_MANIFEST_CONTRACT.md](./ARTIFACT_MANIFEST_CONTRACT.md)
- [EXPORT_PIPELINE_ANALYSIS_GUIDE.md](./EXPORT_PIPELINE_ANALYSIS_GUIDE.md)
- [design/contextcore-a2a-comms-design.md](./design/contextcore-a2a-comms-design.md)
