# Onboarding Metadata Schema Reference

The `onboarding-metadata.json` file is produced by `contextcore manifest export` (onboarding is enabled by default; use `--no-onboarding` to omit). It provides programmatic context for plan ingestion workflows and artisan seed enrichment.

## Schema Version

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | Yes | Schema version (e.g., `1.0.0`). Aligns with artifact manifest `schemaVersion`. |
| `schema` | string | Yes | Schema identifier: `contextcore.io/onboarding-metadata/v1` |

## Project Identity

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_id` | string | Yes | Project identifier. Must match `artifact_manifest.metadata.projectId` and be propagated to seed. |

## File References (relative paths)

All path fields use **relative paths** (from export output directory) for portability.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `artifact_manifest_path` | string | Yes | Path to artifact manifest (e.g., `my-project-artifact-manifest.yaml`) |
| `project_context_path` | string | Yes | Path to ProjectContext CRD (e.g., `my-project-projectcontext.yaml`) |
| `crd_reference` | string | No | Same as project_context_path when present |

## Integrity Checksums

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `artifact_manifest_checksum` | string | No | SHA-256 of artifact manifest content. Present when content is available. |
| `project_context_checksum` | string | No | SHA-256 of project context CRD content. Present when content is available. |
| `source_checksum` | string | No | SHA-256 of source `.contextcore.yaml`. From provenance or computed from source_path. |

## Artifact Type Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `artifact_types` | object | Yes | Per-type schema. Keys: artifact type (e.g., `dashboard`, `prometheus_rule`). |
| `output_path_conventions` | object | Yes | Default output path patterns per type. |
| `parameter_schema` | object | Yes | Parameter keys per artifact type. |

Each entry in `artifact_types`:

| Key | Type | Description |
|-----|------|-------------|
| `output_ext` | string | File extension (e.g., `.json`, `.yaml`) |
| `output_path` | string | Path template with `{target}` placeholder |
| `description` | string | Human-readable description |
| `schema_url` | string | URL for post-generation validation |
| `parameter_keys` | string[] | Expected parameter names |
| `parameter_sources` | object | Mapping of param → source (manifest/crd path) |
| `example_output_path` | string | Example output path |
| `example_snippet` | string | Example output snippet |

## Coverage

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `coverage` | object | Yes | Coverage summary |
| `coverage.gaps` | string[] | Yes | Artifact IDs with status `needed` |
| `coverage.totalRequired` | number | Yes | Total required artifacts |
| `coverage.totalExisting` | number | Yes | Artifacts with status `exists` |
| `coverage.overallCoverage` | number | Yes | Percentage (0–100) |

## Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `artifact_task_mapping` | object | Mapping of `artifact_id` → plan task ID (e.g., `wayfinder_core-dashboard` → `PI-019`). For known plans. |
| `source_path_relative` | string | Source manifest path relative to project root (output_dir parent). For portability. |
| `semantic_conventions` | object | OTel attribute namespaces, metrics, query templates |
| `provenance` | object | Export provenance (when `--emit-provenance`) |
| `guidance` | object | Governance constraints and preferences |
| `generated_at` | string | ISO 8601 timestamp |

## Example (minimal)

```json
{
  "version": "1.0.0",
  "schema": "contextcore.io/onboarding-metadata/v1",
  "project_id": "checkout-service",
  "artifact_manifest_path": "checkout-service-artifact-manifest.yaml",
  "project_context_path": "checkout-service-projectcontext.yaml",
  "generated_at": "2026-02-12T12:00:00",
  "artifact_types": { ... },
  "output_path_conventions": { ... },
  "parameter_schema": { ... },
  "coverage": { "gaps": [], "totalRequired": 12, "overallCoverage": 0 },
  "artifact_manifest_checksum": "abc123...",
  "project_context_checksum": "def456...",
  "source_checksum": "ghi789..."
}
```

## Project ID Consistency

Ensure `project_id` is set consistently across:
- Artifact manifest: `metadata.projectId`
- Onboarding metadata: `project_id`
- Seed (artisan-context-seed.json): propagate from onboarding or config
