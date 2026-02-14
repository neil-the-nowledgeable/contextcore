# Manifest Export Troubleshooting Guide

Common issues when using `contextcore manifest export` and the onboarding pipeline.

## Checksum Mismatch

### Symptom

- Downstream validation fails: "artifact_manifest_checksum does not match"
- Plan ingestion reports integrity mismatch

### Causes

1. **Files modified after export** — The artifact manifest or project context was edited after export. Checksums are computed at export time.
2. **Different encoding** — File was re-saved with different line endings (CRLF vs LF) or BOM.
3. **Stale onboarding metadata** — `onboarding-metadata.json` is from a prior export; artifact manifest was regenerated.

### Resolution

1. Re-run export to regenerate all files and checksums:
   ```bash
   contextcore manifest export -p .contextcore.yaml -o ./output
   ```
2. Ensure no edits to generated files between export and consumption.
3. If using `--scan-existing`, run from the same working directory so paths are consistent.

---

## Plan vs Context Mismatch

### Symptom

- Plan describes "77 artifacts (7 × 11 services)" but context files show 6 artifacts
- Artifact types in plan don't match manifest

### Cause

The plan document may be generic (e.g., Online Boutique example) while the context files are project-specific (e.g., wayfinder-core with 6 artifacts). This is expected when using a template plan with project-specific context.

### Resolution

1. **Document the mismatch** — Note in the plan or seed that it's a template; actual artifact count comes from the manifest.
2. **Use project-specific plans** — Generate plans from the actual `.contextcore.yaml` and artifact manifest.
3. **Merge onboarding metadata** — When plan ingestion runs, ensure it merges `onboarding-metadata.json` (artifact_types, output_path_conventions) into the seed so the plan aligns with context.

---

## Validation Failed Before Export

### Symptom

```
✗ Manifest validation failed before export:
  ✗ Tactic T-001 is blocked but missing blocked_reason
```

### Cause

Pre-flight validation runs before export. The manifest has schema or semantic errors.

### Resolution

1. Run validation explicitly:
   ```bash
   contextcore manifest validate --path .contextcore.yaml --strict
   ```
2. Fix reported errors (e.g., add `blocked_reason` to blocked tactics).
3. Re-run export.

---

## Coverage Below Minimum

### Symptom

```
✗ Coverage 0.0% is below minimum 80.0%
```

### Cause

`--min-coverage 80` was used but not enough artifacts exist yet.

### Resolution

1. **Lower threshold** — Use `--min-coverage 0` or omit for development.
2. **Scan existing** — Point to directory with generated artifacts:
   ```bash
   contextcore manifest export -p .contextcore.yaml -o ./output \
     --scan-existing ./grafana/provisioning/dashboards/
   ```
3. **Generate artifacts** — Run your Wayfinder implementation to create the missing artifacts, then re-export with `--scan-existing`.

---

## Relative vs Absolute Paths

### Symptom

- Seed or handoff fails when run from a different directory
- Paths in provenance or onboarding reference absolute paths

### Resolution

- **artifact_manifest_path** and **project_context_path** in onboarding are relative (from output dir).
- **provenance.sourcePath** may be absolute for audit; consumers should resolve relative to project root when needed.
- When building seeds or handoffs, use paths relative to project root for portability.

---

## Post-Generation Validation (Future)

When `contextcore manifest generate` exists, artifacts will be validated against `schema_url` per type. If validation fails:

1. Check the `schema_url` in onboarding metadata for the artifact type.
2. Ensure generated output conforms to the referenced schema (e.g., Grafana dashboard JSON, PrometheusRule CRD).
3. Report validation errors; the generator may need to fix template output.

---

## Related Documentation

- [ARTIFACT_MANIFEST_CONTRACT](./ARTIFACT_MANIFEST_CONTRACT.md)
- [ONBOARDING_METADATA_SCHEMA](./ONBOARDING_METADATA_SCHEMA.md)
- [MANIFEST_ONBOARDING_GUIDE](./MANIFEST_ONBOARDING_GUIDE.md)
