# Onboarding Metadata Schema Reference

The `onboarding-metadata.json` file is produced by `contextcore manifest export` (onboarding is enabled by default; use `--no-onboarding` to omit). It provides programmatic context for plan ingestion workflows and artisan seed enrichment.

## Schema Version

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | Yes | Schema version (e.g., `1.0.0`). Aligns with artifact manifest `schemaVersion`. |
| `schema_version` | string | No | Additive schema compatibility marker for onboarding consumers. |
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

## Run Provenance Linkage

Onboarding metadata links to run-level provenance when available (via strict quality or explicit `--emit-run-provenance`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `run_provenance_file` | string | No | Relative path to `run-provenance.json` if emitted. |
| `run_id` | string | No | ID of the export run that generated this file. |
| `run_provenance_checksum` | string | No | Checksum of the run provenance file for tamper detection. |

The `run-provenance.json` artifact contains deeper lineage details:
- Exact CLI arguments and configuration snapshot
- Input file fingerprints (manifest, policy, task mapping)
- Output file fingerprints (before/after state)
- Execution environment details

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

## Enrichment Fields

These fields provide the deeper context that A2A governance gates validate and downstream consumers depend on. They are populated by `src/contextcore/utils/onboarding.py`.

| Field | Type | Required by A2A | Description |
|-------|------|-----------------|-------------|
| `derivation_rules` | object | Yes (design-calibration gate) | Per-artifact-type rules mapping business metadata (criticality, SLOs) to artifact parameters. Keys are artifact types (e.g., `dashboard`, `prometheus_rule`). Each value is a list of rule objects with `source_field`, `target_parameter`, and `transform`. |
| `expected_output_contracts` | object | Yes (gap-parity gate) | Per-artifact-type contracts defining expected depth (`brief`/`standard`/`comprehensive`), `max_lines`, `max_tokens`, `completeness_markers`, and `required_fields`. Used by artisan IMPLEMENT/TEST phases. |
| `artifact_dependency_graph` | object | Recommended | Maps artifact ID → list of dependent artifact IDs (e.g., SLO depends on PrometheusRule). Used for plan sequencing and parallel execution planning. |
| `resolved_artifact_parameters` | object | Recommended | Pre-resolved parameter values per artifact, ready for template substitution. Reduces LLM inference burden in artisan IMPLEMENT. |
| `open_questions` | object[] | Recommended | Unresolved questions from `guidance.questions` (status=`open`). Downstream consumers should surface these during design review. |
| `file_ownership` | object | Recommended | Maps resolved output file path → artifact ID. Used for post-generation validation and CI ownership checks. |
| `objectives` | object[] | No | Strategic objectives from `strategy.objectives`. Provides business context for contractor alignment during design phase. |

### Example: derivation_rules

```json
{
  "derivation_rules": {
    "dashboard": [
      {"source_field": "spec.business.criticality", "target_parameter": "dashboard_placement", "transform": "criticality_to_placement"},
      {"source_field": "spec.requirements.latencyP99", "target_parameter": "latency_threshold", "transform": "identity"}
    ],
    "prometheus_rule": [
      {"source_field": "spec.business.criticality", "target_parameter": "alert_severity", "transform": "criticality_to_severity"}
    ]
  }
}
```

### Example: expected_output_contracts

```json
{
  "expected_output_contracts": {
    "dashboard": {"expected_depth": "comprehensive", "max_lines": 500, "completeness_markers": ["panels", "templating", "annotations"]},
    "service_monitor": {"expected_depth": "brief", "max_lines": 30, "completeness_markers": ["endpoints", "selector"]}
  }
}
```

### Example: capability_context (REQ-CAP-005)

```json
{
  "capability_context": {
    "index_version": "1.10.1",
    "applicable_principles": [
      {
        "id": "typed_over_prose",
        "principle": "All inter-agent data exchange uses typed schemas..."
      }
    ],
    "applicable_patterns": [
      {
        "pattern_id": "contract_validation",
        "name": "Contract Validation (Defense-in-Depth)",
        "capabilities": ["contextcore.contract.propagation", "contextcore.contract.schema_compat"]
      }
    ],
    "matched_capabilities": ["contextcore.insight.emit", "contextcore.task.track"],
    "governance_gates": [
      "contextcore.a2a.gate.pipeline_integrity",
      "contextcore.a2a.gate.diagnostic"
    ]
  }
}
```

## Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `artifact_task_mapping` | object | Mapping of `artifact_id` → plan task ID (e.g., `wayfinder_core-dashboard` → `PI-019`). For known plans. |
| `capabilities` | object | Capability negotiation block. Includes `schema_features` and `optional_sections`. |
| `requirements_hints` | object[] | Optional requirements bridge for downstream ingestion. Each item includes `id`, `labels`, and optional `acceptance_anchors`/`source_references`. |
| `parameter_resolvability` | object | Machine-readable parameter resolution matrix per artifact and parameter. |
| `parameter_resolvability_summary` | object | Aggregate counts and unresolved reason breakdown for parameter resolvability. |
| `source_path_relative` | string | Source manifest path relative to project root (output_dir parent). For portability. |
| `semantic_conventions` | object | OTel attribute namespaces, metrics, query templates |
| `provenance` | object | Export provenance (when `--emit-provenance`) |
| `guidance` | object | Governance constraints and preferences |
| `guidance.design_principles` | object[] | Design principles from capability index applicable to this project's artifacts (REQ-CAP-006). Each entry has `id`, `principle`, and `anti_patterns`. |
| `capability_context` | object | Capability index references for downstream consumers (REQ-CAP-005). Includes applicable principles, patterns, matched capabilities, and governance gates. Present when `docs/capability-index/` exists. |
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

## A2A Governance Integration

The onboarding metadata is the primary input for A2A governance validation:

- **`contextcore contract a2a-check-pipeline`** reads onboarding metadata to validate enrichment field population, checksum chain integrity, and design calibration alignment
- **`contextcore contract a2a-diagnose`** uses onboarding metadata to answer "Is the contract complete?" (Q1)
- Enrichment fields (`derivation_rules`, `expected_output_contracts`, `artifact_dependency_graph`) are checked as part of Gate 1 validation

The checksum-chain gate uses checksums from onboarding-metadata.json (always present). For full 6/6 gate coverage, export with `--emit-provenance` (enables the provenance-consistency gate):

```bash
contextcore manifest export -p .contextcore.yaml -o ./output --emit-provenance
contextcore contract a2a-check-pipeline ./output
```

See `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` for the full 7-step pipeline and `docs/design/contextcore-a2a-comms-design.md` for A2A architecture.
