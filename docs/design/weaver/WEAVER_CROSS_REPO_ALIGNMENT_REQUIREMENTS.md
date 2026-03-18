# Weaver Cross-Repo Alignment Requirements

**Date:** 2026-02-28
**Status:** Draft (updated to reflect Layers 1–7, 11-gate pipeline (10 standard + 1 conditional), and REQ-EFE cross-repo contract)
**Companion to:** `WEAVER_REGISTRY_REQUIREMENTS.md`
**Repos in scope:** ContextCore, Wayfinder, StartD8 SDK

---

## 1. Problem Statement

Three repositories produce and consume ContextCore-compatible OTel task state files. Each has evolved independently, creating schema drift that no automated validation catches.

| Repo | Role | Evidence |
|------|------|----------|
| **ContextCore** | Canonical producer (StateManager, TaskTracker) + schema owner | `src/contextcore/state.py`, `contracts/types.py` |
| **StartD8 SDK** | Secondary producer (task_tracking_emitter) + consumer (ContextCoreTaskSource) | `workflows/builtin/task_tracking_emitter.py`, `integrations/contextcore.py` |
| **Wayfinder** | Consumer (scripts, dashboards, progress tracker skill) | `scripts/load_tasks_to_tempo.py`, Grafana dashboards |

The WEAVER_REGISTRY_REQUIREMENTS.md plan addresses ContextCore's internal drift (prose vs. Python enums) but does not account for:

1. **Cross-repo producers** — StartD8's `task_tracking_emitter.py` writes state files with attributes not in the registry plan
2. **Cross-repo consumers** — `ContextCoreTaskSource._load_task_from_file()` in StartD8 reads attributes defensively but has no schema contract
3. **Wayfinder's parallel semconv prose** — `docs/skill-semantic-conventions.md` (70+ attributes) duplicates ContextCore conventions without referencing a shared schema
4. **ATTRIBUTE_MAPPINGS fragmentation** — `otel_genai.py` contains 2-3 overlapping mapping dicts

**Since 2026-02-11:** ContextCore now has 7 contract domain layers (Layers 1–7) with 12 new enums in `contracts/types.py`, the pipeline has expanded from 6 to 10 integrity gates, and the `RequirementLevel` enum formally defines `opt_in` semantics (addresses R2-S7, R3-F7, R1-F8 reviewer feedback). The Edit-First Enforcement (REQ-EFE) feature established the first formally specified cross-repo contract pattern.

---

## 2. Identified Gaps

### 2.1 Attribute Name Drift Between Producers

| Attribute | ContextCore (tracker.py) | StartD8 Emitter | Registry Plan (4.1) | Risk |
|-----------|-------------------------|-----------------|---------------------|------|
| `task.blocked_by` | Defined | Not used | Defined | Consumer confusion |
| `task.depends_on` | Not defined | Used | Not defined | Emitter writes, registry ignores |
| `task.prompt` | Not defined | Used | Not defined | Useful but unformalized |
| `task.feature_id` | Not defined | Used | Not defined | Hierarchy link, no spec |
| `task.target_files` | Not defined | Used | Not defined | Code generation context |
| `task.estimated_loc` | Not defined | Used | Not defined | Sizing heuristic |

**Impact:** `ContextCoreTaskSource` reads whatever is in `attributes` — it won't reject unknown keys, but Grafana dashboards, recording rules, and the progress tracker skill only query attributes they know about. Emitter-only attributes are invisible downstream unless consumers are updated.

### 2.2 Enum Drift

| Enum | types.py (canonical) | Handoff module | Docs (prose) | Registry Plan |
|------|---------------------|----------------|-------------|---------------|
| HandoffStatus | 6 members | 9 members (+input_required, cancelled, rejected) | 9 members | 6 members |
| InsightType | 4 members | 4 members | 4 members | 4 members |

**Impact:** `types.py` is the declared source of truth, but the handoff module and docs disagree on HandoffStatus cardinality. The Weaver registry plan inherits the types.py values (6), leaving 3 runtime values unrepresented.

### 2.3 ATTRIBUTE_MAPPINGS Fragmentation

`otel_genai.py` contains multiple `ATTRIBUTE_MAPPINGS` dicts:

| Dict Location | Keys | Notes |
|---------------|------|-------|
| Top-level (lines ~17-30) | 8 mappings (agent, insight) | Primary |
| Earlier block (lines ~24-50) | 5 mappings (context, handoff) | Overlapping, different scope |
| TOOL_ATTRIBUTES | 1 constant | Correct but separate |

**Impact:** Adding a new deprecated attribute requires updating the right dict. No test validates completeness. The Weaver registry's `deprecated:` fields should be the single source for this mapping.

### 2.4 Wayfinder Parallel Specification

Wayfinder's `docs/skill-semantic-conventions.md` defines 70+ attributes covering:
- `skill.*`, `capability.*` namespaces (Wayfinder-specific)
- `agent.*`, `gen_ai.*` namespaces (duplicates ContextCore conventions)
- `task.*`, `project.*`, `sprint.*` (duplicates ContextCore conventions)

This prose document has no machine-readable counterpart and no cross-reference to ContextCore's `contracts/types.py` or the planned Weaver registry.

**Impact:** Wayfinder could introduce attributes that shadow or conflict with ContextCore conventions. No CI catches this.

### 2.5 No Cross-Repo CI Validation

| Validation | ContextCore | StartD8 SDK | Wayfinder |
|------------|-------------|-------------|-----------|
| Python enum consistency | Not automated | N/A | N/A |
| State file schema check | Not automated | Not automated | Not automated |
| Attribute name allowlist | Not automated | Not automated | Not automated |
| ATTRIBUTE_MAPPINGS completeness | Not automated | N/A | N/A |
| Weaver `registry check` | Not started | N/A | N/A |

### 2.6 Contract Domain Layers Not Reflected in Cross-Repo Schema

ContextCore now has 7 contract domain layers with 12 new enums:

| Layer | Domain | Enums | Cross-Repo Impact |
|-------|--------|-------|-------------------|
| 1 | Propagation | PropagationStatus (4), ChainStatus (3), EvaluationPolicy (4) | Propagation status affects handoff completeness reporting |
| 2 | Schema Compat | CompatibilityLevel (3) | Consumer schema validation checks |
| 3 | Semconv | RequirementLevel (3) | Defines `opt_in` semantics for cross-repo attributes |
| 4 | Boundary | EnforcementMode (3) | Pipeline phase enforcement mode |
| 5 | Capability | CapabilityChainStatus (4) | Capability attenuation across handoffs |
| 6 | Budget | BudgetType (5), OverflowPolicy (3), BudgetHealth (3) | SLO budget allocation for cross-repo pipelines |
| 7 | Lineage | TransformOp (6), LineageStatus (4) | Data transformation tracking across repos |

**Impact:** These 12 enums exist in ContextCore's `contracts/types.py` but are not referenced by any cross-repo schema or registry. StartD8 SDK has no awareness of Layer 1–7 types, meaning propagation status, capability chain, and budget health data emitted by ContextCore are invisible to cross-repo consumers.

### 2.7 Pipeline Gate Count Drift

Documents and CLI help text reference "6 integrity checks" for `a2a-check-pipeline`, but `PipelineChecker` now runs **10 gates**:

| Gate | Check | Added |
|------|-------|-------|
| 1 | Structural integrity | Original |
| 2 | Checksum chain | Original |
| 3 | Provenance cross-check | Original |
| 4 | Mapping completeness | Original |
| 5 | Gap parity | Original |
| 6 | Design calibration | Original |
| 7 | Parameter resolvability | 2026-02 |
| 8 | Artifact inventory | 2026-02 |
| 9 | Service metadata | 2026-02 |
| 10 | Edit-first coverage (REQ-EFE-013) | 2026-02 |
| 11 | Min-coverage enforcement (`--min-coverage` flag) | 2026-02 |

**Note:** Gate 11 (`_check_min_coverage`) is **conditional** — it only runs when the `--min-coverage` CLI flag is provided. The standard pipeline runs 10 gates; the 11th is an optional enforcement gate.

**Impact:** Cross-repo consumers that reference the gate count (e.g., CI scripts, documentation) may expect only 6 gates. Gates 7–10 (parameter resolvability, artifact inventory, service metadata, edit-first coverage) may affect cross-repo consumers. Gate 11 only applies when explicitly requested via CLI.

### 2.8 Edit-First Enforcement as Cross-Repo Contract

REQ-EFE (see `docs/design/requirements/REQ_EDIT_FIRST_ENFORCEMENT.md`) defines the first formally specified cross-repo contract:

- **Producer (ContextCore):** Publishes `edit_min_pct` thresholds per artifact type in `expected_output_contracts`, announces via `schema_features` containing `"edit_first_enforcement"`
- **Consumer (StartD8 SDK):** Enforces size regression gate (Gate 5) in `ImplementPhaseHandler` when `schema_features` includes `"edit_first_enforcement"`
- **Contract negotiation:** `schema_features` field is a new mechanism for feature-detecting cross-repo capabilities

**Impact:** This pattern (`schema_features` → producer publishes thresholds → consumer enforces gate) is the template for future cross-repo contracts but no existing REQ covers it generically.

### 2.9 Content Verification Gates

4 new content-level checks were added to the FINALIZE_VERIFY phase (`content_verification.py`):

| Gate | Check | Cross-Repo Dependency |
|------|-------|-----------------------|
| Placeholder scan | Regex scan for leftover placeholder tokens | None |
| Schema field verification | Cross-check proto field names against source | References `protobuf_schema` ArtifactType |
| Import consistency | Imports vs dependency manifest | References `python_requirements` ArtifactType |
| Protocol coherence | Transport protocol vs file indicators | References `TransportProtocol` from `service_metadata.py` |

**Impact:** Protocol coherence references `TransportProtocol` from `models/service_metadata.py` — a new cross-repo dependency. Services declaring `grpc` transport but using HTTP client libraries will be flagged.

---

## 3. Requirements

### REQ-1: Registry Must Cover Cross-Repo Attributes

The Weaver registry MUST include all attributes written by any producer, not just ContextCore's internal set.

**Acceptance criteria:**
- Registry `task.yaml` includes `task.prompt`, `task.feature_id`, `task.target_files`, `task.estimated_loc` as `opt_in` attributes
- Registry defines `task.depends_on` (structural dependencies, `opt_in`) and `task.blocked_by` (runtime blockers, `required`) as distinct attributes with documented semantics
- All attributes written by `task_tracking_emitter.py` are present in the registry

### REQ-2: Emitter Alignment

The StartD8 `task_tracking_emitter.py` MUST use attribute names from the Weaver registry.

**Acceptance criteria:**
- Emitter uses `task.depends_on` for structural dependencies and MUST NOT repurpose `task.blocked_by` for that meaning
- All emitter attributes pass `weaver registry check` when validated against the registry
- State files produced by the emitter are loadable by both `ContextCoreTaskSource` and `StateManager.load_span()`

### REQ-3: ATTRIBUTE_MAPPINGS Consolidation

The `otel_genai.py` dual-emit layer MUST have a single canonical `ATTRIBUTE_MAPPINGS` dict.

**Acceptance criteria:**
- One dict, no duplicates, no overlapping keys across multiple dicts
- Dict entries match `deprecated:` → replacement pairs in the Weaver registry
- Unit test validates dict completeness against registry YAML (Phase 1: manual; Phase 3: automated)

### REQ-4: HandoffStatus Enum Reconciliation

The HandoffStatus enum MUST have a single cardinality across all sources.

**Acceptance criteria:**
- `types.py` HandoffStatus has the canonical set (decide: 6 or 9 members)
- `handoff.py` runtime values are a subset of the enum
- `docs/semantic-conventions.md` matches the enum
- Weaver registry `handoff.yaml` matches the enum

### REQ-5: Wayfinder References ContextCore Registry

Wayfinder MUST NOT duplicate ContextCore semantic conventions in prose.

**Acceptance criteria:**
- `docs/skill-semantic-conventions.md` references ContextCore's registry for `task.*`, `project.*`, `sprint.*`, `agent.*` namespaces
- Wayfinder-specific namespaces (`skill.*`, `capability.*`) remain documented in Wayfinder; registry extension work is deferred
- No conflicting attribute definitions between the two repos

### REQ-6: Cross-Repo Schema Validation

At least one CI check MUST validate that state files conform to the registry.

**Acceptance criteria:**
- Validation schema is a JSON Schema artifact generated from registry YAML via a documented, versioned script in ContextCore
- StartD8 emitter tests validate output against a pinned version of that schema artifact
- ContextCore StateManager tests validate output against the same pinned schema artifact
- Schema artifact version and SpanState `schema_version` (currently `2`) are both tracked in repository manifests/CI config

### REQ-7: Emitter↔StateManager Format Parity

State files from `task_tracking_emitter.py` MUST be loadable by ContextCore's `StateManager.load_span()` and vice versa.

**Acceptance criteria:**
- Emitter output includes all fields required by `SpanState.from_dict()`: `task_id`, `span_name`, `trace_id`, `span_id`, `start_time`, `attributes`, `events`, `schema_version`, `project_id`
- `StateManager.load_span()` tolerates `opt_in` attributes it doesn't know about
- Round-trip test: emitter → StateManager.load_span() → StateManager.save_span() → semantic equivalence (ignore JSON key order, compare timestamps at millisecond precision, treat absent optional fields as equivalent to null/default)

### REQ-8: Telemetry Schema Change Notification

When OTel metric names, span names, or attribute schemas change in any producer repo, a ContextCore task MUST be emitted to notify downstream consumers (dashboards, recording rules, alert definitions, consumer scripts) so they can be updated before the change causes silent data loss.

**Motivation (real incident, 2026-02-12):**
The StartD8 SDK defines OTel metrics (e.g., `startd8.cost.total`, unit=USD). The OTel Collector's Prometheus exporter applies naming conventions that transform metric names at the wire level (e.g., `startd8.cost.total` → `startd8_cost_USD_total`). Grafana dashboards querying the original names (`startd8_cost_total`) silently showed no data. No automated notification was issued. The root cause was discovered only through manual investigation.

**Scope:** This requirement applies to all three forms of telemetry schema drift that can break consumers:
1. **Metric name changes** — renaming, adding/removing unit suffixes, changing instrument types (Counter → Histogram)
2. **Span name changes** — renaming spans that Tempo/TraceQL queries reference (e.g., `agent.generate` → `workflow.artisan-*`)
3. **Attribute schema changes** — renaming, removing, or retyping span/metric attributes used in dashboard filters or recording rules

**Acceptance criteria:**

1. **Change detection**: A CI check or pre-commit hook in each producer repo detects when OTel metric definitions, span names, or resource attributes are added, renamed, or removed. Detection compares the current state of instrumentation code against a baseline manifest.

2. **Schema manifest**: Each producer repo maintains a machine-readable telemetry schema manifest (`telemetry-schema.yaml`) listing all emitted metrics (name, unit, instrument type, labels), spans (name, attributes), and resource attributes. This manifest is the baseline for change detection.

3. **ContextCore task emission on schema change**: When the CI check detects a schema change, it MUST emit a ContextCore task as a proper project-scoped state file (via `task_tracking_emitter` or equivalent). The state file MUST be **SpanState v2 compliant** and associated with the **source repo's ContextCore project** (read from `.contextcore.yaml` in the repo root) so it is routable to downstream consumers via the existing `StateManager` / `ContextCoreTaskSource` pipeline.

   **SpanState v2 required fields** (top-level):
   - `task_id`: Prefixed with `SCHEMA-{repo}-` for uniqueness (e.g., `SCHEMA-startd8-sdk-001`)
   - `span_name`: `contextcore.task.task` (follows TaskTracker convention: `contextcore.task.{task_type}`)
   - `trace_id`: 32-char hex, generated per CI run (groups all schema-change notifications in one trace)
   - `span_id`: 16-char hex, unique per notification
   - `parent_span_id`: `null` (top-level task, no parent epic)
   - `start_time`: ISO 8601 timestamp
   - `status`: `"UNSET"` (not `"OK"` — task is not yet resolved)
   - `status_description`: `null`
   - `events`: At least one `task.created` event with `percent_complete: 0` (zero-point initialization)
   - `schema_version`: `2` (must match `_SCHEMA_VERSION` from `task_tracking_emitter.py`)
   - `project_id`: From `.contextcore.yaml`

   **Required attributes** (in `attributes` dict):
   - `task.id`: Same as top-level `task_id`
   - `task.title`: Human-readable summary (e.g., "Metric wire name changed: startd8_cost_total → startd8_cost_USD_total")
   - `task.type`: `"task"` (standard enum value — use `task.labels` for the `telemetry-schema-update` classifier)
   - `task.status`: `"todo"` (standard enum: `backlog|todo|in_progress|in_review|blocked|done|cancelled`)
   - `task.priority`: `"high"` (schema changes that break dashboards are high priority)
   - `task.percent_complete`: `0` (enables per-task progress gauge in Grafana)
   - `task.labels`: `["telemetry-schema-update", "dashboard-alignment"]` (filterable classifier)
   - `project.id`: From `.contextcore.yaml`
   - `project.name`: From `.contextcore.yaml`
   - `sprint.id`: From `.contextcore.yaml` or `"unscheduled"`

   **Schema-change-specific attributes** (extensions — valid because SpanState attributes are `Dict[str, Any]` with no allowlist):
   - `task.source_repo`: The repo where the change originated
   - `task.affected_metrics` / `task.affected_spans` / `task.affected_attributes`: List of changed telemetry identifiers
   - `task.change_type`: `added` | `renamed` | `removed` | `type_changed`
   - `task.downstream_consumers`: List of known consumer repos/dashboards that reference the changed identifiers

   **Creation event** (in `events` list — required by time-series-progress-tracker zero-point pattern):
   ```json
   {"name": "task.created", "timestamp": "...", "attributes": {"percent_complete": 0, "task_type": "task", "task_priority": "high", "message": "Schema change detected: ..."}}
   ```

   The emitted state file MUST be installable to `~/.contextcore/state/{project_id}/` and loadable by `StateManager.load_span()`, just like any other ContextCore task. This ensures the schema-change notification participates in the same observability pipeline as feature tasks — visible in Grafana dashboards, queryable via Tempo, and trackable by the `/time-series-progress-tracker` skill.

4. **Consumer notification via project routing**: ContextCore's task runner (or a Weaver-integrated CI step) MUST surface the emitted task to maintainers of downstream consumer **projects**. This requires extending the existing `ContextCoreTaskSource` (which currently scans only a single project directory) to support **multi-project upstream scanning**:

   **New `.contextcore.yaml` field** (in each consumer repo):
   ```yaml
   # wayfinder/.contextcore.yaml
   project_id: wayfinder
   upstream_projects:
     - startd8-sdk       # scan ~/.contextcore/state/startd8-sdk/ for schema-change tasks
     - contextcore        # scan ~/.contextcore/state/contextcore/
   ```

   **Discovery flow**:
   ```
   Consumer CI → ContextCoreTaskSource(project="wayfinder", upstream_projects=["startd8-sdk", "contextcore"])
     → Scans ~/.contextcore/state/wayfinder/          (own tasks)
     → Scans ~/.contextcore/state/startd8-sdk/         (upstream schema-change tasks)
     → Scans ~/.contextcore/state/contextcore/         (upstream schema-change tasks)
     → Filters by task.labels containing "telemetry-schema-update"
     → Reports matching tasks with downstream_consumers referencing "wayfinder"
   ```

   **Note**: `ContextCoreTaskSource` currently only accepts a single `project` parameter. This AC requires either extending it to accept `upstream_projects`, or implementing a thin wrapper that iterates over multiple StateManagers. This is a **new capability** not yet implemented in either ContextCore or StartD8 SDK.

5. **Dashboard-as-code validation**: Grafana dashboard JSON (checked into repos or managed via provisioning) MUST be validated against the producer's telemetry schema manifest. A dashboard that references a metric or span name not present in any producer's manifest generates a warning (non-blocking) or error (blocking, configurable).

**Implementation staging decision:**
- **REQ-8 MVP (in-scope for this plan):** AC1-AC3 (change detection, telemetry manifest maintenance, and SpanState v2 task emission)
- **REQ-8 Follow-up (deferred):** AC4-AC5 (multi-project upstream scanning and dashboard-as-code validation wiring)

**Example flow:**
```
1. SDK developer changes metric unit: startd8.cost.total (unit=USD)
   → Prometheus exporter emits: startd8_cost_USD_total (was startd8_cost_total)

2. CI detects schema diff: metric "startd8.cost.total" changed (unit suffix affects wire name)

3. ContextCore state file emitted (project-scoped, SpanState v2 compliant):
   {
     "task_id": "SCHEMA-startd8-sdk-001",
     "span_name": "contextcore.task.task",
     "trace_id": "a1b2c3d4e5f6a7b8a1b2c3d4e5f6a7b8",
     "span_id": "d1e2f3a4b5c6d7e8",
     "parent_span_id": null,
     "start_time": "2026-02-12T14:30:00+00:00",
     "end_time": null,
     "status": "UNSET",
     "status_description": null,
     "attributes": {
       "task.id": "SCHEMA-startd8-sdk-001",
       "task.title": "Metric wire name changed: startd8_cost_total → startd8_cost_USD_total",
       "task.type": "task",
       "task.status": "todo",
       "task.priority": "high",
       "task.percent_complete": 0,
       "task.labels": ["telemetry-schema-update", "dashboard-alignment"],
       "task.source_repo": "startd8-sdk",
       "task.affected_metrics": ["startd8.cost.total"],
       "task.change_type": "renamed",
       "task.downstream_consumers": ["wayfinder:dashboards/startd8-sdk-overview.json"],
       "project.id": "startd8-sdk",
       "project.name": "StartD8 SDK",
       "sprint.id": "unscheduled"
     },
     "events": [
       {
         "name": "task.created",
         "timestamp": "2026-02-12T14:30:00+00:00",
         "attributes": {
           "percent_complete": 0,
           "task_type": "task",
           "task_priority": "high",
           "message": "Schema change detected: metric startd8.cost.total wire name changed"
         }
       }
     ],
     "schema_version": 2,
     "project_id": "startd8-sdk"
   }
   → Installed to ~/.contextcore/state/startd8-sdk/SCHEMA-startd8-sdk-001.json

4. Wayfinder CI run: ContextCoreTaskSource scans state dirs for upstream projects,
   discovers the telemetry-schema-update task, scans its own dashboard JSON for
   references to "startd8_cost_total", finds stale reference, fails or warns
```

**Non-goals:**
- Automatically patching dashboards (that requires human judgment on query semantics)
- Catching changes in third-party exporters' naming conventions (e.g., Alloy's `otelcol.exporter.prometheus` adding `_total` suffixes) — those are configuration-level, not schema-level

### REQ-9: Edit-First Enforcement Cross-Repo Contract

ContextCore manifests with `"edit_first_enforcement"` in `schema_features` MUST include `edit_min_pct` for all `EXPECTED_OUTPUT_CONTRACTS` entries. Consumer repos (startd8-sdk) MUST enforce the size regression gate when `schema_features` includes `"edit_first_enforcement"`.

**Acceptance criteria:**
- All 19 artifact types in `EXPECTED_OUTPUT_CONTRACTS` have `edit_min_pct` thresholds (integer, range 0–100) — **already implemented** (REQ-EFE-010)
- startd8-sdk `ImplementPhaseHandler` applies Gate 5 size regression check when `schema_features` includes `"edit_first_enforcement"` — **already implemented** (REQ-EFE-020)
- Rejection telemetry emits `edit_first.size_regression` span event with `edit_first.artifact_type`, `edit_first.input_size`, `edit_first.output_size`, `edit_first.ratio`, `edit_first.threshold`, `edit_first.action` — **already implemented** (REQ-EFE-022)
- `schema_features` list in onboarding metadata includes `"edit_first_enforcement"` — **already implemented** (REQ-EFE-012)
- Pipeline checker gate 10 validates `edit_min_pct` presence and range (0–100) with NaN guard — **already implemented** (REQ-EFE-013)
- Cross-repo contract is documented in `docs/design/requirements/REQ_EDIT_FIRST_ENFORCEMENT.md`

### REQ-10: Contract Domain Layer Registry Coverage

The Weaver registry MUST include attribute groups for all 7 contract domain layers. Layer-specific enums MUST be cross-checked against `contracts/types.py`.

**Acceptance criteria:**
- Registry includes `propagation.*` (6 attrs, PropagationStatus + ChainStatus + EvaluationPolicy enums)
- Registry includes `schema_compat.*` (3 attrs, CompatibilityLevel enum)
- Registry includes `semconv.*` (3 attrs, RequirementLevel enum)
- Registry includes `boundary.*` (3 attrs, EnforcementMode enum)
- Registry includes `capability.*` (3 attrs, CapabilityChainStatus enum)
- Registry includes `budget.*` (6 attrs, BudgetType + OverflowPolicy + BudgetHealth enums)
- Registry includes `lineage.*` (4 attrs, TransformOp + LineageStatus enums)
- All 12 layer-specific enums in registry YAML match Python definitions in `contracts/types.py`
- Registry includes `service_metadata.*` with `TransportProtocol` enum (grpc, http, grpc-web)

### REQ-11: Pipeline Gate Manifest

Each producer repo MUST document the gates it runs and their blocking behavior in a machine-readable format.

**Acceptance criteria:**
- ContextCore publishes a gate manifest listing all 11 gates (10 standard + 1 conditional) with: gate number, name, blocking status, severity (ERROR/WARNING), phase, and conditional flag
- Gate manifest is machine-readable (YAML or JSON)
- Consumer repos can detect when upstream adds new gates (gate count in manifest vs. expected)
- Gate manifest is versioned alongside the registry

---

## 4. Out of Scope

- Modifying ContextCore's runtime dual-emit behavior (registry documents, doesn't change runtime)
- Upstream OTel semconv contribution (that's a separate track in `docs/otel-semconv-wg-proposal.md`)
- Replacing `contracts/types.py` with generated code from Weaver (Python remains canonical)
- Wayfinder's `skill.*` / `capability.*` namespaces (Wayfinder-specific, can be a registry extension later)
- Contract domain layer runtime behavior (Layers 1–7 are internal to ContextCore; registry documents types only)
- Edit-first threshold tuning (thresholds are ContextCore's decision; consumer must respect published values)

---

## 5. Dependencies

| Dependency | Source | Status |
|------------|--------|--------|
| WEAVER_REGISTRY_REQUIREMENTS.md Phase 1 | ContextCore | Not started |
| OTel Weaver binary (v0.21.2+, V2 schema, registry dependencies, MCP) | open-telemetry/weaver | Available (pinnable) |
| `task_tracking_emitter.py` | StartD8 SDK | Merged (commit 0d91ce8) |
| `ContextCoreTaskSource` | StartD8 SDK | Production |
| `StateManager` + `SpanState` v2 | ContextCore | Production |
| `telemetry-schema.yaml` per producer repo (REQ-8) | All 3 repos | Not started |
| `upstream_projects` in `.contextcore.yaml` (REQ-8) | Consumer repos (Wayfinder, StartD8) | Not started |
| `ContextCoreTaskSource` multi-project scanning (REQ-8) | ContextCore or StartD8 SDK | Not started |
| Dashboard-as-code provisioning in Wayfinder (REQ-8) | Wayfinder | Partial (dashboards exist, not yet validated against schema) |
| REQ-EFE edit-first enforcement (REQ-9) | ContextCore + StartD8 SDK | **Implemented** (producer: commit `164b7e3`; consumer: commit `dddb9c5`) |
| Content verification gates (REQ-9 related) | ContextCore | **Implemented** (`content_verification.py`) |
| PipelineChecker 11 gates (10 standard + 1 conditional) (REQ-11) | ContextCore | **Implemented** (`pipeline_checker.py`) |
| `RequirementLevel` enum (addresses `opt_in` definition gap) | ContextCore | **Implemented** (`contracts/types.py`) |
| `ServiceMetadataEntry` / `TransportProtocol` model | ContextCore | **Implemented** (`models/service_metadata.py`) |
| Registry dependency chain mechanism (v0.17.0) | OTel Weaver | Available — enables cross-repo schema sharing |
| `imports` section for selective OTel semconv import (v0.15.3) | OTel Weaver | Available |
| `weaver registry infer` for emitter validation | OTel Weaver | **Unreleased** — could auto-validate cross-repo emitters against registry |

---

## 6. Success Metrics

1. `weaver registry check --registry semconv/` passes with zero errors in ContextCore CI
2. All state files from both producers (ContextCore StateManager, StartD8 task_tracking_emitter) validate against the registry schema
3. Zero attribute name drift between producers (enforced by CI)
4. Single ATTRIBUTE_MAPPINGS dict in `otel_genai.py`
5. HandoffStatus cardinality identical across types.py, handoff.py, docs, and registry
6. Zero silent dashboard breakages from telemetry schema changes — every metric/span rename generates a ContextCore notification task within the same CI run
7. Edit-first enforcement thresholds validated in both producer (ContextCore export) and consumer (StartD8 implement phase) CI
8. Pipeline gate count is consistent between documentation, gate manifest, and `PipelineChecker` implementation (currently 10 standard + 1 conditional)

---

## 7. Weaver Upstream Alignment for Cross-Repo

Weaver's evolution from v0.15 to v0.21.2 addresses several reviewer concerns:

| Reviewer Concern | Weaver Feature (new) | Resolution |
|-----------------|---------------------|------------|
| R2-S2, R3-F2: Schema distribution mechanism | Registry dependency chains (v0.17.0) | Consumer repos declare ContextCore registry as dependency; Weaver fetches versioned archive |
| R1-S6, R2-S1: Schema format unspecified | V2 schema (v0.19–v0.20) | Concrete format with `file_format: definition/2` |
| R1-F8, R2-S7: `opt_in` undefined | `RequirementLevel` enum + Weaver V2 requirement_level field | Both Python and YAML now formally define opt_in |
| R1-S1, R2-S3: Schema versioning policy | `schema_url` in manifest + semver support | Registry manifest supports explicit version pinning |
| R2-S4, R2-F3: Deprecation lifecycle | Structured deprecation on enum members (v0.19) | `deprecated.since`, `deprecated.note`, `deprecated.renamed_to` |
| R2-S5, R1-F7: Consumer-side validation | `weaver registry live-check` (v0.20) | Validates emitted OTLP against registry in real-time |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

(No areas have reached the threshold of 3 accepted suggestions yet.)

### Areas Needing Further Review

- **Architecture**: 0/3 suggestions accepted (need 3 more)
- **Interfaces**: 1/3 suggestions accepted (R1-F8; need 2 more)
- **Data**: 0/3 suggestions accepted (need 3 more)
- **Risks**: 0/3 suggestions accepted (need 3 more)
- **Validation**: 1/3 suggestions accepted (R1-F5; need 2 more)
- **Ops**: 0/3 suggestions accepted (need 3 more)
- **Security**: 0/3 suggestions accepted (need 3 more)

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F5 | [Validation] Fix Success Metric #2 producer count | Multiple reviewers | Updated Section 6 metric #2 from "all 3 producers" to "both producers (ContextCore StateManager, StartD8 task_tracking_emitter)". | 2026-02-28 |
| R1-F8 | [Interfaces] Define `opt_in` semantics explicitly | Multiple reviewers | `RequirementLevel` enum and cross-repo docs now define producer/consumer behavior for `opt_in` fields. | 2026-02-28 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R3

- **Reviewer**: codex (gpt-5)
- **Date**: 2026-03-01 03:19:51 UTC
- **Scope**: Strict dual-document protocol cleanup and unresolved requirements quality gaps

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Architecture | high | Rewrite REQ-1 AC2 to require both `task.depends_on` and `task.blocked_by` with distinct semantics. | Current wording forces a false canonical-name choice that conflicts with the plan design. | Section 3, REQ-1 acceptance criteria | Confirm REQ-1 no longer requires removing or aliasing one of the two attributes. |
| R3-F2 | Validation | high | Keep REQ-7 round-trip acceptance criterion semantic (not literal diff) and align any test docs to the same rules. | Literal diff is brittle for key ordering, timestamp precision, and optional-field normalization. | Section 3, REQ-7 acceptance criteria | Ensure rules specify key-order tolerance, timestamp precision, and null/default handling. |
| R3-F3 | Interfaces | high | Keep REQ-5 scoped to shared namespaces and explicitly defer `skill.*`/`capability.*` registry extension work. | REQ-5 and Out-of-Scope must remain non-contradictory for implementers. | Section 3, REQ-5 acceptance criteria + Section 4 | Verify REQ-5 AC2 matches Section 4 out-of-scope language exactly. |
| R3-F4 | Data | high | Make REQ-6 schema derivation concrete: one JSON Schema artifact generated by one versioned script. | "Schema derived from registry" without format/tooling invites incompatible validators across repos. | Section 3, REQ-6 acceptance criteria | Verify schema format, generator location, and version pinning are explicitly testable. |
| R3-F5 | Ops | high | Split REQ-8 execution into staged delivery (MVP AC1-AC3 now, AC4-AC5 follow-up) with explicit phase ownership in the plan. | REQ-8 currently combines CI change detection, routing changes, and dashboard validation with different implementation horizons. | Section 3, REQ-8 (staging note) + plan mapping table | Confirm plan maps MVP work to active phase and deferred items to follow-up phase. |
| R3-F6 | Risks | medium | Add explicit ownership for REQ-8 AC1-AC5 by repo/team to reduce cross-repo execution risk. | Cross-repo requirements without owner assignment are high risk for partial delivery. | Section 5 dependencies (owner column or owner notes) | Verify every REQ-8 acceptance criterion names an owning repo/team. |
