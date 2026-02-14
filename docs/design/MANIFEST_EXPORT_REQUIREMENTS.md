# Manifest Export & Validate Requirements

Purpose: define the behavioral requirements for `contextcore manifest export` and `contextcore manifest validate` — the contract production and validation commands that form the core of the ContextCore pipeline.

This document is intentionally living guidance. Update it as the commands evolve.

---

## Vision

`manifest export` is the central command in the ContextCore pipeline. It reads a `.contextcore.yaml` manifest and produces the **artifact contract** — the declaration of what observability artifacts are needed, why, and with what parameters. Everything downstream (plan ingestion, contractor execution, quality gates) depends on the completeness and correctness of this output.

`manifest validate` is the prerequisite gate that ensures the manifest is structurally and semantically valid before export. Together they form a single "produce and validate the contract" phase.

**Core principle**: ContextCore knows WHAT artifacts are needed (derived from business metadata). It does not know HOW to create them. The export output is the contract between the "what" and the "how."

---

## Pipeline Placement

Steps 2–3 of the 7-step A2A governance-aware pipeline:

1. ~~`contextcore install init`~~ — infrastructure readiness (separate concern)
2. **`contextcore manifest export`** — produce contract + enrichment metadata
3. **`contextcore contract a2a-check-pipeline`** — Gate 1 validation (6 integrity checks)
4. `startd8 workflow run plan-ingestion` — parse, assess, route, refine, emit
5. `contextcore contract a2a-diagnose` — Gate 2 validation (Three Questions)
6. Contractor execution — structured build
7. Finalize verification — Gate 3

`manifest validate` is a prerequisite to step 2. It may be run independently or as part of export's pre-flight check (export always validates before proceeding).

### Proposed consolidation: `--verify` flag

Export should support a `--verify` flag that automatically runs Gate 1 (`a2a-check-pipeline`) on its own output directory after writing files. This chains steps 2 and 3 into a single invocation without human intervention, since there is no decision point between them on the happy path. The individual commands remain available for independent use.

---

## Manifest Validate

### Purpose

Validate a `.contextcore.yaml` manifest against the schema. Returns exit code 0 if valid, 1 if invalid.

### Functional Requirements

1. **Schema validation**
   - Must validate the manifest against the v2 JSON schema (or v1.1 for legacy manifests).
   - Must detect and report: missing required fields, invalid field types, unknown fields.
2. **Warning vs error distinction**
   - Must distinguish errors (invalid manifest) from warnings (valid but suboptimal).
   - Must support `--strict` mode that fails on warnings, not just errors.
3. **Output formats**
   - Must support `text` (human-readable) and `json` (machine-readable) output.
4. **Exit codes**
   - Exit 0: valid manifest (no errors).
   - Exit 1: invalid manifest (one or more errors).

### CLI Surface

```
contextcore manifest validate
  --path / -p       (required)   Path to the manifest file
  --strict           (flag)       Fail on warnings (not just errors)
  --format / -f      (default: text)  Output format: text | json
```

---

## Manifest Export

### Purpose

Read a `.contextcore.yaml` manifest and produce the full artifact contract package for downstream consumption by plan ingestion and contractor workflows.

### Functional Requirements

#### Input Processing

1. **Pre-flight validation**
   - Must validate the manifest before export. If validation fails, exit with error and do not produce partial output.
2. **Manifest version detection**
   - Must detect manifest version (v1.1 or v2) and process accordingly.
   - v2 is the primary supported format; v1.1 is accepted with reduced enrichment.
3. **Quality policy loading**
   - Must load quality policy from `.contextcore-quality.yaml` if present.
   - Quality toggles (`--strict-quality`, `--deterministic-output`, `--emit-quality-report`) may be set by policy file, CLI flags, or defaults.

#### Output Production

4. **ProjectContext CRD**
   - Must produce a Kubernetes CRD YAML file (`{project}-projectcontext.yaml`).
   - CRD is for reference only — it is NOT applied to a cluster by export.
   - Must include all `spec` fields from the manifest.
5. **Artifact Manifest**
   - Must produce an artifact manifest (`{project}-artifact-manifest.yaml` or `.json`).
   - Must declare every required observability artifact with: `id`, `type`, `name`, `target`, `priority`, `status`, `derivedFrom`, `parameters`.
   - Must compute coverage statistics: `totalRequired`, `totalExisting`, `totalOutdated`, `overallCoverage`, `byTarget`, `byType`.
   - Must support 8 artifact types: `dashboard`, `prometheus_rule`, `slo_definition`, `service_monitor`, `loki_rule`, `notification_policy`, `runbook`, `alert_template`.
6. **Onboarding metadata** (default: enabled)
   - Must produce `onboarding-metadata.json` with programmatic context for plan ingestion.
   - Must include: `project_id`, file references, integrity checksums, artifact type schemas, output path conventions, parameter schemas, coverage summary.
   - Must include enrichment fields: `derivation_rules`, `expected_output_contracts`, `artifact_dependency_graph`, `resolved_artifact_parameters`, `open_questions`, `file_ownership`, `objectives`.
   - Must be opt-out via `--no-onboarding`.
7. **Validation report**
   - Must always produce `validation-report.json` with export-time diagnostic results.
8. **Provenance** (opt-in)
   - When `--emit-provenance` is set, must produce `provenance.json` with: git context (branch, commit, dirty status), timestamps, source checksum, CLI arguments, duration.
   - When `--embed-provenance` is set, must embed provenance metadata in the artifact manifest itself.
   - Provenance is required for the provenance-consistency gate (gate 3 of 6 in `a2a-check-pipeline`).
9. **Quality report** (opt-in)
   - When `--emit-quality-report` is set, must produce `export-quality-report.json` with strict-quality gate outcomes.

#### Derivation Rules

10. **Business metadata derivation**
    - Must derive artifact parameters from business metadata using standard derivation rules:
      - `spec.business.criticality` → alert severity (critical→P1, high→P2, medium→P3, low→P4)
      - `spec.requirements.availability` → SLO objective
      - `spec.requirements.latencyP99` → latency threshold
      - `spec.observability.alertChannels` → notification routes
      - `spec.risks[]` → runbook sections
    - Must include `derivedFrom` entries in each artifact explaining the derivation chain.
11. **Priority assignment**
    - Must assign artifact priority (`required` or `recommended`) based on business criticality and artifact type.
    - Must follow the priority logic defined in the Artifact Manifest Contract.

#### Coverage Tracking

12. **Existing artifact scanning**
    - Must support `--scan-existing <dir>` to detect existing artifacts by filename pattern.
    - Must support `--existing <id:path>` for explicit artifact-to-path mapping.
    - Must set artifact status to `exists` when a matching file is found.
13. **Coverage computation**
    - Must compute per-target and per-type coverage percentages.
    - Must identify coverage gaps (artifacts with status `needed`).
14. **Minimum coverage enforcement**
    - When `--min-coverage <N>` is set, must fail if overall coverage is below the threshold.

#### Quality Safeguards

15. **Strict quality mode** (default: enabled)
    - Must validate that the manifest contains minimum required fields for meaningful export.
    - Must enforce deterministic artifact ordering when strict quality is active.
16. **Deterministic output**
    - Must produce byte-identical output for the same input when deterministic mode is active.
    - Artifact ordering, field ordering, and serialization must be stable.

#### Proposed: Verify Flag

17. **`--verify` flag** (proposed)
    - When set, must run `a2a-check-pipeline` on the output directory after all files are written.
    - Must report Gate 1 results inline in export output.
    - Must fail with non-zero exit code if any blocking gate fails (when combined with `--fail-on-unhealthy` behavior).
    - Must not run if `--dry-run` is set.
    - Individual `a2a-check-pipeline` command remains available for independent use.

### CLI Surface

```
contextcore manifest export
  --path / -p                (required)   Path to the context manifest file
  --output-dir / -o          (default: .)  Output directory
  --namespace / -n           (default: default)  K8s namespace for CRD
  --existing / -e            (multiple)   Existing artifact: 'artifact_id:path'
  --scan-existing            (optional)   Scan directory for existing artifacts
  --format / -f              (default: yaml)  Output format: yaml | json
  --dry-run                  (flag)       Preview without writing files
  --strict-quality           (default: enabled)  Strict quality safeguards
  --no-strict-quality                     Disable strict quality
  --deterministic-output     (default: enabled in strict)  Deterministic ordering
  --emit-provenance          (flag)       Write provenance.json
  --embed-provenance         (flag)       Embed provenance in artifact manifest
  --emit-onboarding          (default: enabled)  Write onboarding-metadata.json
  --no-onboarding                         Skip onboarding metadata
  --min-coverage             (optional)   Fail if coverage below threshold
  --task-mapping             (optional)   JSON file mapping artifact IDs to task IDs
  --emit-quality-report      (optional)   Write export-quality-report.json
  --verify                   (flag, proposed)  Run Gate 1 after export
```

### Output Files

| File | Condition | Description |
|------|-----------|-------------|
| `{project}-projectcontext.yaml` | Always | Kubernetes CRD (reference only) |
| `{project}-artifact-manifest.yaml` | Always | Artifact contract |
| `onboarding-metadata.json` | Default (opt-out: `--no-onboarding`) | Programmatic onboarding + enrichment |
| `validation-report.json` | Always | Export-time diagnostics |
| `provenance.json` | `--emit-provenance` | Full audit trail |
| `export-quality-report.json` | `--emit-quality-report` | Quality gate outcomes |

---

## Non-Functional Requirements

1. **Offline operation**: Export and validate must work without network access. No calls to Tempo, Loki, Mimir, Grafana, or any external service.
2. **Determinism**: Same manifest input must produce identical output (when deterministic mode is active).
3. **Fail-fast**: Invalid manifest → exit immediately with clear error. Never produce partial output from an invalid source.
4. **Auditability**: Every derived value must be traceable to a source field via `derivedFrom`. Provenance must capture full context when requested.
5. **Idempotency**: Running export multiple times with the same input and options must produce the same files.
6. **Performance**: Export should complete in under 5 seconds for manifests with up to 20 targets.
7. **Backward compatibility**: v1.1 manifests must be accepted. v2 is the primary format.
8. **Portability**: All file paths in output must be relative to the output directory.

---

## Invariants

These must hold true for every export run:

1. `onboarding-metadata.json`.`project_id` == artifact manifest `.metadata.projectId`
2. Every artifact in the manifest has a non-empty `derivedFrom` list.
3. Coverage percentages are mathematically consistent: `overallCoverage == totalExisting / totalRequired * 100`.
4. If `--emit-provenance` is set, `provenance.json`.`source_checksum` matches the SHA-256 of the input manifest file.
5. If `--min-coverage` is set and coverage is below the threshold, exit code is non-zero.
6. Validation report is always written, even on partial failure.

---

## Downstream Success Criteria

1. `a2a-check-pipeline` can run all 6 gates on export output without errors.
2. Plan ingestion can parse `onboarding-metadata.json` and route artifacts by complexity.
3. Contractor workflows receive pre-resolved parameters that do not require re-derivation.
4. Coverage re-scan after artifact generation correctly updates statuses from `needed` to `exists`.

---

## Relationship to Other Commands

| Command | Relationship |
|---------|-------------|
| `manifest validate` | Prerequisite — export always validates first |
| `manifest init` / `init-from-plan` | Upstream — produces the manifest that export reads |
| `manifest create` | Parallel — produces plan artifacts and startd8 config; reads the same manifest |
| `a2a-check-pipeline` | Downstream — validates export output (proposed: inline via `--verify`) |
| `generate` | Legacy ancestor — produces artifacts directly from K8s CRD; export produces the contract instead |

---

## Related Docs

- `docs/ARTIFACT_MANIFEST_CONTRACT.md` — artifact manifest schema and derivation rules
- `docs/ONBOARDING_METADATA_SCHEMA.md` — onboarding metadata field reference
- `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` — 7-step pipeline operational reference
- `docs/design/contextcore-a2a-comms-design.md` — A2A governance architecture
- `docs/MANIFEST_EXPORT_TROUBLESHOOTING.md` — common issues and diagnostics
- `plans/EXPORT_ENRICHMENT_PLAN.md` — enrichment field implementation plan
- `docs/MANIFEST_CREATE_REQUIREMENTS.md` — manifest create requirements
- `plans/init-from-plan/INIT_FROM_PLAN_HIGH_LEVEL_REQUIREMENTS.md` — init-from-plan requirements
