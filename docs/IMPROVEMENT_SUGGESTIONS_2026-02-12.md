# ContextCore Improvement Suggestions

Suggestions to improve output quality and programmatic onboarding across the manifest export pipeline. See [ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md](./ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md) for the quality assessment that motivated these.

## Export Step (`contextcore manifest export`)

| # | Suggestion | Rationale |
|---|------------|-----------|
| 1 | **Onboarding metadata by default** | Make `--emit-onboarding` the default so plan ingestion always has context. Add `--no-onboarding` to opt out. |
| 2 | **Schema version in artifact manifest** | Add `schemaVersion` to metadata for compatibility checks. Consumers can validate before processing. |
| 3 | **Checksums in onboarding metadata** | Add `artifact_manifest_checksum` and `project_context_checksum` to onboarding-metadata.json for integrity validation. |
| 4 | **Artifact ID → task mapping** | When onboarding metadata is written for a known plan (e.g., manifest generate), include suggested task IDs (e.g., `wayfinder_core-dashboard` → `PI-019`, `PI-020`). |
| 5 | **Pre-flight validation** | Run manifest validation before export; fail early if manifest is invalid. |
| 6 | **Export: coverage threshold** | Add `--min-coverage` (e.g., 80%) and fail if coverage is below threshold. |

## Artifact Manifest

| # | Suggestion | Rationale |
|---|------------|-----------|
| 7 | **Parameter source documentation** | Per ARTIFACT_MANIFEST_CONTRACT R1-F1: For each artifact, document which parameters come from manifest vs CRD. |
| 8 | **Outdated detection rules** | Per R1-F2: Define how "outdated" is determined (e.g., checksum, version, timestamp). |
| 9 | **Schema URLs for validation** | Per R1-F3: Add `schema_url` or `validation_schema` per artifact type for post-generation validation. |
| 10 | **Example outputs** | Per R3-F3: Add `example_output_path` or `example_output` snippet per artifact type. |

## Cross-Project Consistency

| # | Suggestion | Rationale |
|---|------------|-----------|
| 11 | **Shared schema version** | Use a single version (e.g., `1.0.0`) for artifact manifest, onboarding metadata, and seed so consumers can branch on version. |
| 12 | **Provenance chain** | Propagate `source_checksum` from export → onboarding → ingestion → seed so the full chain is verifiable. |
| 13 | **Project ID everywhere** | Ensure `project_id` is set consistently in manifest, export, onboarding metadata, and seed. |
| 14 | **Relative paths** | Avoid absolute paths in seeds and handoffs; use paths relative to project root for portability. |

## Post-Generation (when `manifest generate` exists)

| # | Suggestion | Rationale |
|---|------------|-----------|
| 15 | **Post-generation validation** | After artifact generation, validate each artifact against the schema and report validation errors. |

## Documentation

| # | Suggestion | Rationale |
|---|------------|-----------|
| 16 | **Schema reference** | Document the full schema for `onboarding-metadata.json` in docs. |
| 17 | **Troubleshooting guide** | Add a doc for common issues (checksum mismatch, plan vs context mismatch). |

---

## Priority Order

| Priority | Items | Effort |
|----------|-------|--------|
| High | 1, 3, 5, 7 | 1–2 days |
| Medium | 2, 6, 8, 9, 11, 12 | 2–3 days |
| Low | 4, 10, 13, 14, 15, 16, 17 | 1–2 days |

## Related Repos

- **Wayfinder** — [docs/IMPROVEMENT_SUGGESTIONS_2026-02-12.md](../wayfinder/docs/IMPROVEMENT_SUGGESTIONS_2026-02-12.md) (plan ingestion scripts)
- **startd8-sdk** — [docs/IMPROVEMENT_SUGGESTIONS_2026-02-12.md](../startd8-sdk/docs/IMPROVEMENT_SUGGESTIONS_2026-02-12.md) (workflow implementations)
