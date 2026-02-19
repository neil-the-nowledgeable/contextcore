# Pipeline Artifact Inventory Requirements

Purpose: define the behavioral requirements for extending `run-provenance.json` into a typed pipeline artifact inventory — a single document that tells each pipeline stage what reusable assets are available from earlier stages, where they live, and whether they are fresh.

This document is intentionally living guidance. Update it as the inventory mechanism evolves.

---

## Vision

The 7-step pipeline (init → export → Gate 1 → plan-ingestion → Gate 2 → contractor → Gate 3) produces artifacts at every stage. Today, each stage writes its outputs to disk, but downstream stages have no systematic way to discover what has already been produced. The result: downstream stages regenerate content that earlier stages already computed — a violation of the [Mottainai Design Principle](./MOTTAINAI_DESIGN_PRINCIPLE.md).

The pipeline artifact inventory solves this by extending the existing `run-provenance.json` with a typed `artifact_inventory` section. Each entry declares: what the artifact is (semantic role), where it lives (file path), who produced it (pipeline stage), whether it is fresh (checksum + timestamp), and what downstream stages should use it for (consumption hints).

**Core principle**: Every pipeline stage should be able to answer "what has already been computed that I can use?" by reading a single document.

---

## Pipeline Placement

The inventory is produced and extended across multiple pipeline stages:

1. `contextcore manifest export` — **creates** the inventory with export-stage artifacts
2. `contextcore contract a2a-check-pipeline` (Gate 1) — **validates** inventory integrity
3. `startd8 workflow run plan-ingestion` — **extends** the inventory with ingestion-stage artifacts
4. `contextcore contract a2a-diagnose` (Gate 2) — **validates** inventory completeness
5. Contractor execution — **consumes** the inventory to discover reusable assets; **extends** with contractor-stage artifacts
6. Finalize verification (Gate 3) — **validates** final inventory against expected outputs

The inventory file lives at `{output-dir}/run-provenance.json`, extending the existing schema with backward-compatible additions.

---

## Schema Evolution

### Current `run-provenance.json` Schema (v1.0.0)

The existing schema tracks:

```json
{
  "run_id": "uuid",
  "workflow_or_command": "manifest export",
  "version": "1.0.0",
  "inputs": [{"path": "...", "exists": true, "sha256": "..."}],
  "outputs": [{"path": "...", "exists": true, "sha256": "..."}],
  "quality_summary": {},
  "artifact_references": {}
}
```

This tracks WHAT files exist and their checksums, but not their semantic role, producing stage, or consumption guidance.

### Extended Schema (v2.0.0)

The extended schema adds `artifact_inventory` alongside the existing fields. All v1 fields are preserved — the extension is additive.

```json
{
  "version": "2.0.0",
  "run_id": "uuid",
  "workflow_or_command": "manifest export",
  "inputs": [],
  "outputs": [],
  "quality_summary": {},
  "artifact_references": {},
  "artifact_inventory": [
    {
      "artifact_id": "export.derivation_rules",
      "role": "derivation_rules",
      "description": "Business-to-parameter derivation rules per artifact type",
      "produced_by": "contextcore.manifest.export",
      "stage": "export",
      "source_file": "onboarding-metadata.json",
      "json_path": "$.derivation_rules",
      "sha256": "abc123...",
      "produced_at": "2026-02-14T17:13:48Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["plan-ingestion.assess", "artisan.design", "artisan.implement"],
      "consumption_hint": "Inject per-task derivation rules into FeatureContext.additional_context to avoid LLM re-derivation of business-to-parameter mappings"
    }
  ]
}
```

---

## Functional Requirements

### Inventory Data Model

1. **Artifact entry schema**
   - Each entry in `artifact_inventory` must include:

   | Field | Type | Required | Description |
   |-------|------|----------|-------------|
   | `artifact_id` | string | Yes | Unique identifier: `{stage}.{role}` (e.g., `export.derivation_rules`) |
   | `role` | string | Yes | Semantic role from the controlled vocabulary (see FR-2) |
   | `description` | string | Yes | Human-readable description of what this artifact contains |
   | `produced_by` | string | Yes | Fully qualified producer identifier (e.g., `contextcore.manifest.export`) |
   | `stage` | string | Yes | Pipeline stage: `export`, `gate1`, `ingestion`, `gate2`, `contractor`, `gate3` |
   | `source_file` | string | Yes | Relative path to the file containing this artifact |
   | `json_path` | string | No | JSONPath expression to the artifact within the source file (when the artifact is a sub-field of a larger document) |
   | `sha256` | string | Yes | SHA-256 checksum of the artifact content (full file if no json_path, or serialized sub-document if json_path is specified) |
   | `produced_at` | string (ISO-8601) | Yes | Timestamp when the artifact was produced |
   | `freshness` | object | No | Freshness indicator linking this artifact to its upstream source |
   | `consumers` | list[string] | Yes | Pipeline stages/phases that should use this artifact |
   | `consumption_hint` | string | No | Guidance for how the consumer should use this artifact |

2. **Controlled vocabulary for `role`**
   - The following roles are defined for the initial implementation. New roles may be added as more reuse opportunities are identified.

   | Role | Stage | Description |
   |------|-------|-------------|
   | `derivation_rules` | export | Business-to-parameter mapping rules per artifact type (all categories including source) |
   | `resolved_parameters` | export | Pre-resolved parameter values per artifact, ready for template substitution (all categories including source) |
   | `output_contracts` | export | Per-artifact-type expected depth, completeness markers, max lines/tokens (all categories including source) |
   | `dependency_graph` | export | Artifact-level dependency ordering |
   | `calibration_hints` | export | Per-artifact-type expected depth tier and LOC range (all categories including source) |
   | `open_questions` | export | Unresolved questions from manifest guidance |
   | `parameter_sources` | export | Per-artifact-type parameter origin mapping (all categories including source) |
   | `semantic_conventions` | export | Metric and label naming conventions |
   | `example_artifacts` | export | Example output per artifact type |
   | `coverage_gaps` | export | Artifact types needing generation (all categories including source) |
   | `existing_source_artifacts` | export | Pre-existing source artifacts detected via `scan_existing_artifacts()` with file paths and SHA-256 checksums |
   | `plan_document` | ingestion | Structured plan with architecture, risks, verification strategy |
   | `refine_suggestions` | ingestion | Architectural review suggestions from REFINE phase |
   | `design_calibration` | ingestion | Per-task depth tier, section list, max output tokens |
   | `task_decomposition` | ingestion | Per-task descriptions, file targets, complexity assessment |
   | `design_handoff` | contractor | Per-task design documents from DESIGN phase |
   | `implementation_results` | contractor | Per-task generated code from IMPLEMENT phase |

   **Source artifact coverage note:** The roles `derivation_rules`, `resolved_parameters`,
   `output_contracts`, `calibration_hints`, `parameter_sources`, and `coverage_gaps` must
   cover ALL registered artifact types — including source types (dockerfile,
   python_requirements, protobuf_schema, editorconfig, ci_workflow). When these roles
   contain only observability-type entries, downstream stages are forced to re-derive
   source artifact specifications via LLM — a violation of the Mottainai principle.
   See [GAP_15_EXPORT_ARTIFACT_TYPE_COVERAGE.md](~/Documents/Processes/cap-dev-pipe-test/GAP_15_EXPORT_ARTIFACT_TYPE_COVERAGE.md) for evidence ($1.43/run waste for Dockerfile tasks).

3. **Freshness model**
   - The `freshness` object must include:
     - `source_checksum`: SHA-256 of the upstream source that this artifact was derived from.
     - `source_file`: Path to the upstream source file.
   - An artifact is considered **fresh** when `source_checksum` matches the current checksum of the source file.
   - An artifact is considered **stale** when the checksums diverge.
   - Consumers must check freshness before using an artifact. Stale artifacts may be used with a logged warning, or rejected (depending on the consumer's policy).

### Production (Writing the Inventory)

4. **Export stage production**
   - `contextcore manifest export` must populate `artifact_inventory` with entries for all reusable artifacts it produces.
   - At minimum, the following roles must be registered: `derivation_rules`, `resolved_parameters`, `output_contracts`, `dependency_graph`, `calibration_hints`, `open_questions`, `parameter_sources`, `semantic_conventions`, `example_artifacts`, `coverage_gaps`, `existing_source_artifacts`.
   - Each entry must reference the `onboarding-metadata.json` file and include the `json_path` to the specific field.
   - Inventory entries for `derivation_rules`, `resolved_parameters`, `output_contracts`, `calibration_hints`, and `parameter_sources` must span ALL registered artifact types — including source types — not only observability types. This ensures downstream consumers (plan-ingestion, contractors) receive pre-resolved specifications for Dockerfiles, dependency manifests, and proto schemas.
   - When `scan_existing_artifacts()` detects pre-existing source artifacts, the `existing_source_artifacts` inventory entry must list them with file paths and SHA-256 checksums, enabling downstream stages to reference existing files in design prompts rather than generating from scratch.

5. **Plan-ingestion stage extension**
   - `startd8 workflow run plan-ingestion` must extend the inventory with entries for ingestion-stage artifacts.
   - At minimum: `plan_document`, `refine_suggestions`, `design_calibration`, `task_decomposition`.
   - The inventory file must be read, extended (not overwritten), and written back.
   - The `run_id` must be preserved from the export stage.
   - A new `ingestion_run_id` field may be added alongside the existing `run_id` to track the ingestion run separately.

6. **Contractor stage extension**
   - The artisan (or prime) contractor must extend the inventory with: `design_handoff`, `implementation_results`.
   - Same read-extend-write pattern as plan-ingestion.

7. **Atomic writes**
   - All inventory writes must be atomic (write to temp file, then rename) to avoid corruption from interrupted runs.

### Consumption (Reading the Inventory)

8. **Discovery protocol**
   - A consumer looking for a specific artifact role must:
     1. Load `run-provenance.json` from the output directory.
     2. Search `artifact_inventory` for entries matching the desired `role`.
     3. Check `freshness` to ensure the artifact is current.
     4. Load the artifact from `source_file` (optionally applying `json_path`).
   - If the inventory file is absent or the desired role is not registered, the consumer must fall back to its existing behavior (e.g., LLM generation) and log the fallback.

9. **Graceful degradation**
   - Inventory consumption must never be a hard requirement. If `run-provenance.json` is missing, malformed, or uses v1.0.0 schema (no `artifact_inventory`), the consumer must proceed without it.
   - The consumer must log: `"Mottainai: {role} not found in artifact inventory — falling back to LLM generation"` (or equivalent) so that missing inventory entries are visible in operational logs.

10. **Freshness checking**
    - Consumers should check `freshness.source_checksum` against the current source file before using an artifact.
    - When the artifact is stale, the consumer must log a warning and may either:
      - Use the stale artifact with a warning (default).
      - Reject it and fall back to regeneration (when `strict_freshness` is configured).

### Validation (Gate Integration)

11. **Gate 1 validation**
    - `a2a-check-pipeline` must validate that the inventory exists and that all export-stage roles are registered.
    - Must verify that `sha256` checksums in inventory entries match the actual file contents.
    - Must report missing inventory as a warning (not blocking, for backward compatibility).

12. **Gate 2 validation**
    - `a2a-diagnose` must check that ingestion-stage roles are registered in the inventory after plan-ingestion has run.
    - Must check freshness of export-stage artifacts (source_checksum vs. current manifest).

---

## Non-Functional Requirements

### Backward Compatibility

13. **Schema versioning**
    - The `version` field distinguishes v1 (no inventory) from v2+ (with inventory).
    - All v1 fields must be preserved. The `artifact_inventory` field is additive.
    - Consumers reading v1 files must not fail — they should log the absence and proceed.

14. **Incremental adoption**
    - Each pipeline stage can adopt inventory production and consumption independently.
    - The first consumer does not need to wait for all producers to be implemented.
    - Missing inventory entries degrade gracefully to existing behavior.

### Performance

15. **Inventory size**
    - The inventory is metadata-only (paths + checksums + hints), not the artifacts themselves.
    - Expected size: 10–30 entries × ~200 bytes each = negligible overhead on `run-provenance.json`.

16. **Read performance**
    - The inventory must be loadable in a single JSON parse. No separate files or lazy loading.

### Observability

17. **Logging**
    - Each inventory lookup (hit or miss) must be logged at DEBUG level.
    - Each fallback to LLM generation (when an inventory artifact could have been used) must be logged at WARNING level with the tag `mottainai.fallback`.
    - Each successful reuse must be logged at INFO level with the tag `mottainai.reuse`.

18. **Metrics (planned)**
    - When OTel is available, emit a counter metric `pipeline.artifact_inventory.lookup` with attributes:
      - `role`: the artifact role looked up
      - `outcome`: `hit`, `miss`, `stale`
    - This makes the reuse rate measurable over time.

---

## Implementation Priorities

The following ordering maximizes impact while respecting the incremental adoption requirement:

| Priority | Change | Impact | Effort |
|----------|--------|--------|--------|
| P0 | Export: register `derivation_rules`, `resolved_parameters`, `output_contracts` in inventory | Enables highest-value reuse in artisan DESIGN | Low — export already writes these to onboarding-metadata.json |
| P0 | Artisan DESIGN: consume `derivation_rules` + `resolved_parameters` from inventory | Eliminates redundant LLM parameter derivation | Medium — modify `_task_to_feature_context` to load from inventory |
| P1 | Export: register `dependency_graph`, `calibration_hints`, `open_questions` | Enables dependency and calibration reuse | Low |
| P1 | Plan-ingestion: register `plan_document`, `refine_suggestions`, `design_calibration` | Enables DESIGN to use REFINE output | Medium |
| P1 | Artisan DESIGN: consume `refine_suggestions` and `plan_document` | Eliminates the biggest waste (REFINE output discarded) | Medium |
| P2 | Gate 1 + Gate 2: validate inventory | Closes the governance loop | Low |
| P2 | Artisan DESIGN: consume `calibration_hints` to override LOC-based heuristic | Better depth calibration | Low |
| P3 | OTel metrics for reuse rate | Operational visibility | Low |

---

## Relationship to Other Requirements

| Document | Relationship |
|----------|-------------|
| [Mottainai Design Principle](./MOTTAINAI_DESIGN_PRINCIPLE.md) | The design principle this inventory mechanism enables — tracks what exists so downstream stages can find it |
| [Manifest Export Requirements](./MANIFEST_EXPORT_REQUIREMENTS.md) | FR-18 defines the current `run-provenance.json` schema; this document extends it |
| [A2A Gate Requirements](./A2A_GATE_REQUIREMENTS.md) | FR-11 and FR-12 add inventory validation to Gates 1 and 2 |
| [Export Pipeline Analysis Guide](../guides/EXPORT_PIPELINE_ANALYSIS_GUIDE.md) | The operational guide describing the pipeline where the inventory is produced and consumed |

---

## Appendix A: Example Inventory (Export Stage)

```json
{
  "version": "2.0.0",
  "run_id": "6dc25137-3dfc-4d0f-b1a6-da340def894b",
  "workflow_or_command": "manifest export",
  "inputs": [
    {"path": ".contextcore.yaml", "exists": true, "sha256": "a8111a9c..."}
  ],
  "outputs": [
    {"path": "onboarding-metadata.json", "exists": true, "sha256": "c133e931..."},
    {"path": "contextcore-coyote-artifact-manifest.yaml", "exists": true, "sha256": "f7831e62..."}
  ],
  "quality_summary": {"strict_quality": false, "coverage_meets_minimum": true},
  "artifact_references": {
    "onboarding_metadata_path": "onboarding-metadata.json"
  },
  "artifact_inventory": [
    {
      "artifact_id": "export.derivation_rules",
      "role": "derivation_rules",
      "description": "Business-to-parameter derivation rules per artifact type (e.g., criticality → alert severity)",
      "produced_by": "contextcore.manifest.export",
      "stage": "export",
      "source_file": "onboarding-metadata.json",
      "json_path": "$.derivation_rules",
      "sha256": "e4f2a1b9...",
      "produced_at": "2026-02-14T17:13:48Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["artisan.design", "artisan.implement"],
      "consumption_hint": "Inject per-task derivation rules into FeatureContext.additional_context. Keyed by artifact type."
    },
    {
      "artifact_id": "export.resolved_parameters",
      "role": "resolved_parameters",
      "description": "Pre-resolved parameter values per artifact, ready for template substitution",
      "produced_by": "contextcore.manifest.export",
      "stage": "export",
      "source_file": "onboarding-metadata.json",
      "json_path": "$.resolved_artifact_parameters",
      "sha256": "b7c3d2e8...",
      "produced_at": "2026-02-14T17:13:48Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["artisan.design", "artisan.implement"],
      "consumption_hint": "Use concrete values (e.g., alertSeverity: P2) instead of asking the LLM to derive them from manifest fields."
    },
    {
      "artifact_id": "export.output_contracts",
      "role": "output_contracts",
      "description": "Per-artifact-type expected depth, completeness markers, max lines/tokens, red flags",
      "produced_by": "contextcore.manifest.export",
      "stage": "export",
      "source_file": "onboarding-metadata.json",
      "json_path": "$.expected_output_contracts",
      "sha256": "d9a4f1c3...",
      "produced_at": "2026-02-14T17:13:48Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["artisan.design", "artisan.implement", "artisan.test"],
      "consumption_hint": "Use expected_depth to override LOC-based calibration. Use completeness_markers for post-generation validation."
    },
    {
      "artifact_id": "export.dependency_graph",
      "role": "dependency_graph",
      "description": "Artifact-level dependency graph (e.g., notification depends on prometheus_rule)",
      "produced_by": "contextcore.manifest.export",
      "stage": "export",
      "source_file": "onboarding-metadata.json",
      "json_path": "$.artifact_dependency_graph",
      "sha256": "a1b2c3d4...",
      "produced_at": "2026-02-14T17:13:48Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["ingestion.parse", "artisan.plan"],
      "consumption_hint": "Use for task ordering instead of LLM-inferred dependency edges."
    },
    {
      "artifact_id": "export.calibration_hints",
      "role": "calibration_hints",
      "description": "Per-artifact-type expected depth tier and LOC range",
      "produced_by": "contextcore.manifest.export",
      "stage": "export",
      "source_file": "onboarding-metadata.json",
      "json_path": "$.design_calibration_hints",
      "sha256": "f5e6d7c8...",
      "produced_at": "2026-02-14T17:13:48Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["ingestion.calibration", "artisan.design"],
      "consumption_hint": "Override LOC-based depth tier when artifact type has a known expected depth (e.g., dashboards are always comprehensive)."
    },
    {
      "artifact_id": "export.open_questions",
      "role": "open_questions",
      "description": "Unresolved questions from manifest guidance.questions",
      "produced_by": "contextcore.manifest.export",
      "stage": "export",
      "source_file": "onboarding-metadata.json",
      "json_path": "$.open_questions",
      "sha256": "c8d9e0f1...",
      "produced_at": "2026-02-14T17:13:48Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["artisan.design"],
      "consumption_hint": "Surface in design prompt so LLM does not make decisions that contradict unresolved questions."
    }
  ]
}
```

## Appendix B: Example Inventory After Plan-Ingestion Extension

After plan-ingestion runs, the same file gains additional entries:

```json
{
  "artifact_inventory": [
    "... (all export entries preserved) ...",
    {
      "artifact_id": "ingestion.plan_document",
      "role": "plan_document",
      "description": "Structured plan with architecture, risk register, phase breakdown, and verification strategy",
      "produced_by": "startd8.workflow.plan_ingestion",
      "stage": "ingestion",
      "source_file": "modular-pipeline-plan.md",
      "sha256": "1a2b3c4d...",
      "produced_at": "2026-02-14T18:05:12Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["artisan.design"],
      "consumption_hint": "Load architecture and risk sections as additional context for design prompt."
    },
    {
      "artifact_id": "ingestion.refine_suggestions",
      "role": "refine_suggestions",
      "description": "Architectural review suggestions from REFINE phase (S-prefix plan suggestions, F-prefix feature suggestions)",
      "produced_by": "startd8.workflow.plan_ingestion.refine",
      "stage": "ingestion",
      "source_file": "modular-pipeline-plan.md",
      "json_path": "Appendix C",
      "sha256": "5e6f7a8b...",
      "produced_at": "2026-02-14T18:05:12Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["artisan.design"],
      "consumption_hint": "Extract per-task suggestions and inject into FeatureContext. Eliminates redundant architectural review in DESIGN."
    },
    {
      "artifact_id": "ingestion.design_calibration",
      "role": "design_calibration",
      "description": "Per-task depth tier, calibrated section list, max output tokens",
      "produced_by": "startd8.workflow.plan_ingestion.emit",
      "stage": "ingestion",
      "source_file": "artisan-context-seed.json",
      "json_path": "$.design_calibration",
      "sha256": "9c0d1e2f...",
      "produced_at": "2026-02-14T18:05:12Z",
      "freshness": {
        "source_checksum": "a8111a9c...",
        "source_file": ".contextcore.yaml"
      },
      "consumers": ["artisan.design"],
      "consumption_hint": "Already consumed via seed. Listed for inventory completeness."
    }
  ]
}
```

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-16 | Initial version: schema extension, 16 artifact roles, production/consumption/validation requirements, implementation priorities |
| 2026-02-18 | Extended for source artifact types per Gap 15: added `existing_source_artifacts` role (17 total), added source artifact coverage note to FR-2, extended FR-4 to require source type coverage across inventory roles |
