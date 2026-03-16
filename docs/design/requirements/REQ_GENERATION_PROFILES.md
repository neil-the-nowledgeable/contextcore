# Requirements: Generation Profiles

**Status:** Draft
**Date:** 2026-03-15
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (pipeline architecture)
**Predecessor:** [REQ_CROSS_CUTTING_CONTEXT_LOSS](REQ_CROSS_CUTTING_CONTEXT_LOSS.md)
**Companion:** [Cross-Cutting Context Loss Analysis](~/Documents/dev/startd8-sdk/docs/design/kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md)

---

## Problem Statement

ContextCore's export pipeline was built for a single use case: generating observability artifacts (dashboards, SLOs, prometheus rules) for a project. Every export produces the full observability artifact manifest and full onboarding metadata regardless of what downstream will actually generate.

When the capability delivery pipeline expanded to support source code generation, this created two problems:

1. **Overhead:** Source-code generation runs carry ~200KB of observability-domain metadata (derivation rules, artifact dependency graphs, parameter schemas for dashboard/SLO/rule types) that downstream never consumes. The seed is 1.3MB; only ~130KB (~10%) is essential for Prime Contractor code generation.

2. **Domain confusion:** The onboarding metadata auto-derives `service_metadata` from the artifact manifest, producing `transport_protocol: "http"` for gRPC-dominant projects because the manifest only contains observability artifacts. The pipeline conflates "what the project is" with "what observability artifacts the project needs."

### The Insight

ContextCore's value is **context** — understanding what a project is, what services it has, how they're connected, what matters. That context is the foundation. What you generate from it is a separate, configurable concern:

- **Run A:** Generate the source code for 17 Python microservices
- **Run B:** Generate the observability artifacts those microservices need
- **Run C:** Generate both (the current default, appropriate for greenfield observability-first projects)

The context is the constant; the generation profile is the variable.

### Sequencing

You can't generate good observability for a thing you haven't first generated well. Source code generation is the prerequisite; observability artifact generation is the follow-on. The pipeline should support this sequencing naturally, not force everything into a single pass.

---

## Design Principle

**Context is always rich. Output is selectively scoped.**

The `.contextcore.yaml` manifest and plan text should always capture full project context — services, interconnectedness, requirements, risks, SLOs. The export pipeline should then produce only the artifacts and metadata appropriate for a given generation profile.

This is analogous to how a Makefile has multiple targets (`make build`, `make test`, `make deploy`) but shares a single source tree.

---

## Requirements

### Profile Definition

#### REQ-GP-100: Generation Profile Parameter

`contextcore manifest export` SHALL accept a `--profile` parameter with the following values:

| Profile | Audience | What It Produces | When to Use |
|---------|----------|-----------------|-------------|
| `source` | Developer/machine | Source-code-relevant context only | Generating application code from a plan |
| `monitoring` | Machine | Automation rules (prometheus, loki, service_monitor) | Deploying machine-consumed monitoring rules only |
| `operator` | SRE | Monitoring + incident response + dashboards | SRE onboarding, operational dashboards with business context |
| `sponsor` | Business owner | Business health dashboards + SLO definitions | Business stakeholder visibility into application health |
| `practitioner` | Marketing/sales | Portal dashboards, orientation pages | Onboarding non-technical users to application observability |
| `observability` | All ops roles | All observability artifacts (monitoring + operator + stakeholder) | Full observability for an existing application |
| `full` | Everyone | Everything (current behavior) | Greenfield projects, observability-first workflows |

Default: `full` (backward compatible).

The audience dimension recognizes that artifacts serve different consumers along a spectrum:
**machine → operator → sponsor → practitioner**. An SRE needs business context embedded in runbooks and alerts (the jacket matters more than the tent stake). A sponsor needs business health dashboards. A marketing practitioner needs portal dashboards that function as content pages with zero assumed Grafana literacy.

Artifact types are organized into audience-aware subcategories:
- `MONITORING_TYPES`: prometheus_rule, loki_rule, service_monitor (machine-consumed)
- `OPERATOR_TYPES`: runbook, alert_template, notification_policy (incident response)
- `STAKEHOLDER_TYPES`: dashboard, slo_definition (multi-audience, controlled by `parameters.audience` and `parameters.dashboard_pattern`)

**CLI examples:**
```bash
# Generate source code for a microservices project
contextcore manifest export -p .contextcore.yaml -o ./out --profile source

# Generate monitoring rules only (machine automation)
contextcore manifest export -p .contextcore.yaml -o ./out --profile monitoring

# Generate SRE-focused artifacts (monitoring + runbooks + dashboards)
contextcore manifest export -p .contextcore.yaml -o ./out --profile operator

# Generate business health dashboards for stakeholders
contextcore manifest export -p .contextcore.yaml -o ./out --profile sponsor

# Generate portal/orientation dashboards for marketing team
contextcore manifest export -p .contextcore.yaml -o ./out --profile practitioner

# All observability artifacts
contextcore manifest export -p .contextcore.yaml -o ./out --profile observability

# Everything (default)
contextcore manifest export -p .contextcore.yaml -o ./out --profile full
contextcore manifest export -p .contextcore.yaml -o ./out  # same as --profile full
```

**Acceptance:** Each profile produces export output containing only artifact types for its audience. `--profile full` produces identical output to current behavior. Profiles compose from frozen sets: each includes `_ALWAYS_INCLUDED` (onboarding + integrity types) plus the audience-specific artifact types.

#### REQ-GP-101: Profile Recorded in Export Provenance

The `ExportProvenance` SHALL record which profile was used so downstream consumers know what to expect:

```json
{
  "generation_profile": "source",
  "profile_version": "1.0",
  "available_profiles": ["source", "observability", "full"]
}
```

**Rationale:** Plan ingestion and Prime Contractor need to know whether they're receiving source-scoped or full metadata to avoid searching for sections that were intentionally omitted.

---

### Artifact Manifest Scoping

#### REQ-GP-200: Artifact Manifest Filtered by Profile

`generate_artifact_manifest()` SHALL filter generated artifacts based on the active profile using the existing `ArtifactType` frozen sets:

| Profile | Included ArtifactType Sets | Excluded |
|---------|---------------------------|----------|
| `source` | `SOURCE_TYPES`, `INTEGRITY_TYPES` | `OBSERVABILITY_TYPES` |
| `observability` | `OBSERVABILITY_TYPES`, `ONBOARDING_TYPES`, `INTEGRITY_TYPES` | `SOURCE_TYPES` |
| `full` | All sets | None |

**Acceptance:** `--profile source` produces an artifact manifest with 0 observability-type artifacts. `--profile observability` produces a manifest with 0 source-type artifacts. `--profile full` produces the same manifest as today.

#### REQ-GP-201: Coverage Gaps Scoped to Profile

Coverage gap computation SHALL only count artifacts within the active profile's scope. A `source` profile run should not report missing dashboards as coverage gaps.

**Acceptance:** `--profile source` with no existing source artifacts reports 5 gaps (dockerfile, python_requirements, protobuf_schema, editorconfig, ci_workflow). It does not report missing dashboards or prometheus rules.

---

### Onboarding Metadata Scoping

#### REQ-GP-300: Profile-Scoped Onboarding Metadata

`build_onboarding_metadata()` SHALL accept a `profile` parameter and scope its output accordingly:

**`source` profile — includes:**
| Section | Rationale |
|---------|-----------|
| `service_metadata` | Transport protocol, schema contracts, healthchecks |
| `service_communication_graph` | Cross-service imports, RPCs, shared modules (REQ-CCL-104) |
| `file_ownership` | Which artifacts own which output files |
| `semantic_conventions` | OTel attribute namespaces for instrumentation |
| `source_checksum` | Provenance chain |
| `scope_boundaries` | What's in/out of scope |
| `guidance` | Constraints, preferences from manifest |
| `capability_context` | Matched capabilities, principles, patterns |
| `requirements_hints` | Extracted requirement IDs for traceability |

**`source` profile — omits:**
| Section | Reason for Omission |
|---------|-------------------|
| `artifact_types` (observability entries) | Not generating dashboards/SLOs/rules |
| `derivation_rules` | Observability artifact derivation logic |
| `artifact_dependency_graph` | Observability artifact ordering |
| `parameter_resolvability` (observability entries) | Observability parameter resolution |
| `design_calibration_hints` (observability entries) | Observability output calibration |
| `expected_output_contracts` (observability entries) | Observability output contracts |
| `coverage` (observability scope) | Not relevant to source generation |

**`observability` profile:** Current full behavior for observability sections. Omits source-specific sections.

**`full` profile:** Everything (current behavior).

**Acceptance:** `source` profile onboarding metadata is <50KB. `full` profile onboarding metadata is unchanged from current output. Omitted sections include `"_omitted": "profile=source"` marker for debuggability.

#### REQ-GP-301: Service Metadata Derived from Plan Text Under Source Profile

When `--profile source`, `service_metadata` SHALL be derived from plan text signals (section headings, import lists, proto references) rather than from the artifact manifest.

This supersedes the artifact-manifest-based derivation which incorrectly defaults to `transport_protocol: "http"` for gRPC projects.

**Acceptance:** A source-profile export for a project whose plan says `### F-002a: Email Service — gRPC Server` produces `service_metadata.emailservice.transport_protocol = "grpc"`.

---

### Downstream Compatibility

#### REQ-GP-400: Profile Indicator in Onboarding Schema

Onboarding metadata SHALL include a top-level `generation_profile` field:

```json
{
  "schema_version": "1.1.0",
  "schema": "contextcore.io/onboarding-metadata/v1",
  "generation_profile": "source",
  ...
}
```

**Rationale:** Downstream consumers (plan ingestion, Prime Contractor, artisan) need to branch behavior based on what's in the metadata. Checking for the presence/absence of individual sections is fragile; a profile indicator is explicit.

#### REQ-GP-401: Schema Version Bump

The onboarding metadata `schema_version` SHALL bump to `1.1.0` when generation profiles are introduced. Consumers using `1.0.0` will receive `full` profile output (backward compatible). Consumers reading `1.1.0` can check `generation_profile`.

#### REQ-GP-402: Cap-Dev-Pipe Profile Passthrough

The capability delivery pipeline SHALL accept a `--profile` flag and pass it through to `contextcore manifest export`. The pipeline's `pipeline.env` SHALL support a `GENERATION_PROFILE` variable defaulting to `full`.

**Acceptance:** `./run-pipeline.sh --profile source` produces source-scoped export artifacts.

---

### Profile Sequencing

#### REQ-GP-500: Observability Profile Reads Source Profile Output

When `--profile observability` is run, the export pipeline SHOULD detect prior `source` profile output in the same output directory and use it to enrich observability artifact generation:

- Service names from the source profile's `service_communication_graph` become targets for observability artifacts
- Transport protocols from source `service_metadata` inform healthcheck and monitoring artifact parameters
- Shared modules from the source communication graph inform trace context propagation requirements

**Rationale:** This enables the natural sequencing: run source first to establish what the project is, then run observability to generate how to observe it. The observability run benefits from the richer context the source run produced.

**Acceptance:** An observability-profile export in a directory containing prior source-profile output produces observability artifacts with per-service targets (not a single generic target) and correct transport protocols.

#### REQ-GP-501: No Implicit Dependency Between Profiles

Each profile MUST produce valid, self-contained output when run independently. REQ-GP-500 describes enrichment, not dependency. Running `--profile observability` without prior `--profile source` output SHALL produce the same output as current behavior.

**Acceptance:** `--profile observability` in an empty output directory produces identical output to current `--profile full` observability sections.

---

## Phasing

### Phase 1: Profile Flag + Artifact Manifest Filtering

| Requirement | File | Estimated Lines |
|-------------|------|----------------|
| REQ-GP-100 | `cli/manifest.py` | ~15 (CLI flag + validation) |
| REQ-GP-101 | `models/artifact_manifest.py` | ~10 (provenance field) |
| REQ-GP-200 | `models/manifest_v2.py` | ~20 (filter by frozen sets) |
| REQ-GP-201 | `utils/onboarding.py` | ~10 (scoped coverage) |

**Total:** ~55 lines. Delivers the core filtering without changing onboarding metadata shape.

### Phase 2: Onboarding Metadata Scoping

| Requirement | File | Estimated Lines |
|-------------|------|----------------|
| REQ-GP-300 | `utils/onboarding.py` | ~60 (conditional section emission) |
| REQ-GP-301 | `utils/onboarding.py` or `cli/init_from_plan_ops.py` | ~40 (plan-text-based service metadata) |
| REQ-GP-400 | `utils/onboarding.py` | ~5 (profile indicator) |
| REQ-GP-401 | `utils/onboarding.py` | ~5 (version bump) |

**Total:** ~110 lines. Delivers the onboarding metadata efficiency gain (~200KB → ~50KB for source profile).

### Phase 3: Sequencing + Pipeline Integration

| Requirement | File | Estimated Lines |
|-------------|------|----------------|
| REQ-GP-402 | cap-dev-pipe `pipeline.env` + `run-pipeline.sh` | ~15 |
| REQ-GP-500 | `cli/manifest.py` or `utils/onboarding.py` | ~40 (detect + read prior output) |
| REQ-GP-501 | Tests | ~30 (independence validation) |

**Total:** ~85 lines.

---

## Success Criteria

1. **Source-profile efficiency:** `--profile source` produces onboarding metadata <50KB (vs ~200KB for `full`)
2. **Correct transport detection:** Source-profile export derives `transport_protocol` from plan text, not artifact manifest
3. **Zero observability overhead:** Source-profile runs carry 0 observability artifact specs, 0 derivation rules, 0 observability parameter schemas
4. **Backward compatible:** `--profile full` (and no `--profile` flag) produce identical output to current behavior
5. **Natural sequencing:** Running `--profile source` then `--profile observability` produces richer observability artifacts than running `--profile observability` alone
6. **Pipeline integration:** cap-dev-pipe `--profile source` produces correct source-scoped export for plan ingestion

---

## Non-Goals

- Automatic profile selection (always explicit; default is `full`)
- Profile-specific validation rules (quality gates apply uniformly)
- New artifact types (this is about filtering existing types, not adding new ones)
- Runtime profile switching (profile is set at export time, fixed for the run)

---

## Relationship to Existing Work

| Document | Relationship |
|----------|-------------|
| [REQ_CROSS_CUTTING_CONTEXT_LOSS](REQ_CROSS_CUTTING_CONTEXT_LOSS.md) | Predecessor — identified onboarding bloat and domain mismatch. REQ-CCL-300 (project type discriminator) is superseded by generation profiles |
| [ArtifactType frozen sets](../../src/contextcore/models/artifact_manifest.py) | Foundation — `SOURCE_TYPES`, `OBSERVABILITY_TYPES`, `ONBOARDING_TYPES`, `INTEGRITY_TYPES` already exist |
| [Cross-Cutting Context Loss Analysis](~/Documents/dev/startd8-sdk/docs/design/kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) | Origin — §6 Seed Complexity Audit identified 90% overhead |
| [Service Interconnectedness Requirements](../SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md) | Companion — `service_communication_graph` is a key section retained under source profile |
| [Plan-Target Coherence](REQ_PLAN_TARGET_COHERENCE.md) | Related — coherence validation should respect profile scope |
