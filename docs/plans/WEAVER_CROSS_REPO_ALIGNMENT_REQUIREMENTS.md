# Weaver Cross-Repo Alignment Requirements

**Date:** 2026-02-11
**Status:** Draft
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

---

## 3. Requirements

### REQ-1: Registry Must Cover Cross-Repo Attributes

The Weaver registry MUST include all attributes written by any producer, not just ContextCore's internal set.

**Acceptance criteria:**
- Registry `task.yaml` includes `task.prompt`, `task.feature_id`, `task.target_files`, `task.estimated_loc` as `opt_in` attributes
- Registry resolves `task.depends_on` vs `task.blocked_by` naming — one canonical name, the other either removed or aliased
- All attributes written by `task_tracking_emitter.py` are present in the registry

### REQ-2: Emitter Alignment

The StartD8 `task_tracking_emitter.py` MUST use attribute names from the Weaver registry.

**Acceptance criteria:**
- Emitter uses `task.blocked_by` (not `task.depends_on`) if registry chooses that name, or vice versa
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
- Wayfinder-specific namespaces (`skill.*`, `capability.*`) are either added to ContextCore's registry or maintained in a Wayfinder-specific registry extension
- No conflicting attribute definitions between the two repos

### REQ-6: Cross-Repo Schema Validation

At least one CI check MUST validate that state files conform to the registry.

**Acceptance criteria:**
- StartD8 emitter tests validate output against a schema derived from the registry
- ContextCore StateManager tests validate output against the same schema
- Schema version (currently `2`) is tracked in the registry manifest

### REQ-7: Emitter↔StateManager Format Parity

State files from `task_tracking_emitter.py` MUST be loadable by ContextCore's `StateManager.load_span()` and vice versa.

**Acceptance criteria:**
- Emitter output includes all fields required by `SpanState.from_dict()`: `task_id`, `span_name`, `trace_id`, `span_id`, `start_time`, `attributes`, `events`, `schema_version`, `project_id`
- `StateManager.load_span()` tolerates `opt_in` attributes it doesn't know about
- Round-trip test: emitter → StateManager.load_span() → StateManager.save_span() → diff is empty

### REQ-8: Telemetry Schema Change Notification

When OTel metric names, span names, or attribute schemas change in any producer repo, a ContextCore task MUST be emitted to notify downstream consumers (dashboards, recording rules, alert definitions, consumer scripts) so they can be updated before the change causes silent data loss.

**Motivation (real incident, 2026-02-12):**
The StartD8 SDK defines OTel metrics (e.g., `startd8.cost.total`, unit=USD). The OTel Collector's Prometheus exporter applies naming conventions that transform metric names at the wire level (e.g., `startd8.cost.total` → `startd8_cost_USD_total`). Grafana dashboards querying the original names (`startd8_cost_total`) silently showed no data. No automated notification was issued. The root cause was discovered only through manual investigation.

**Scope:** This requirement applies to all three forms of telemetry schema drift that can break consumers:
1. **Metric name changes** — renaming, adding/removing unit suffixes, changing instrument types (Counter → Histogram)
2. **Span name changes** — renaming spans that Tempo/TraceQL queries reference (e.g., `agent.generate` → `workflow.artisan-*`)
3. **Attribute schema changes** — renaming, removing, or retyping span/metric attributes used in dashboard filters or recording rules

**Acceptance criteria:**

1. **Change detection**: A CI check or pre-commit hook in each producer repo detects when OTel metric definitions, span names, or resource attributes are added, renamed, or removed. Detection compares the current state of instrumentation code against a baseline manifest (see REQ-8a below).

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
   - Consumer repo's CI reads its `.contextcore.yaml` → `upstream_projects` list
   - For each upstream project, instantiates `StateManager(project=upstream_id)` and calls `get_active_spans()`
   - Filters for tasks with `task.labels` containing `"telemetry-schema-update"`
   - For each matching task, reads `task.affected_metrics` / `task.affected_spans` and scans the consumer repo's dashboard JSON for stale references
   - A warning or failing CI check alerts the consumer repo that its dashboards reference telemetry names changed upstream

   **Note**: `ContextCoreTaskSource` currently only accepts a single `project` parameter. This AC requires either extending it to accept `upstream_projects`, or implementing a thin wrapper that iterates over multiple StateManagers. This is a **new capability** not yet implemented in either ContextCore or StartD8 SDK.

5. **Dashboard-as-code validation**: Grafana dashboard JSON (checked into repos or managed via provisioning) MUST be validated against the producer's telemetry schema manifest. A dashboard that references a metric or span name not present in any producer's manifest generates a warning (non-blocking) or error (blocking, configurable).

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

---

## 4. Out of Scope

- Modifying ContextCore's runtime dual-emit behavior (registry documents, doesn't change runtime)
- Upstream OTel semconv contribution (that's a separate track in `docs/otel-semconv-wg-proposal.md`)
- Replacing `contracts/types.py` with generated code from Weaver (Python remains canonical)
- Wayfinder's `skill.*` / `capability.*` namespaces (Wayfinder-specific, can be a registry extension later)

---

## 5. Dependencies

| Dependency | Source | Status |
|------------|--------|--------|
| WEAVER_REGISTRY_REQUIREMENTS.md Phase 1 | ContextCore | Not started |
| OTel Weaver binary in CI | open-telemetry/weaver | Available (pinnable) |
| `task_tracking_emitter.py` | StartD8 SDK | Merged (commit 0d91ce8) |
| `ContextCoreTaskSource` | StartD8 SDK | Production |
| `StateManager` + `SpanState` v2 | ContextCore | Production |
| `telemetry-schema.yaml` per producer repo (REQ-8) | All 3 repos | Not started |
| `upstream_projects` in `.contextcore.yaml` (REQ-8) | Consumer repos (Wayfinder, StartD8) | Not started |
| `ContextCoreTaskSource` multi-project scanning (REQ-8) | ContextCore or StartD8 SDK | Not started |
| Dashboard-as-code provisioning in Wayfinder (REQ-8) | Wayfinder | Partial (dashboards exist, not yet validated against schema) |

---

## 6. Success Metrics

1. `weaver registry check --registry semconv/` passes with zero errors in ContextCore CI
2. All state files from all 3 producers validate against the registry schema
3. Zero attribute name drift between producers (enforced by CI)
4. Single ATTRIBUTE_MAPPINGS dict in `otel_genai.py`
5. HandoffStatus cardinality identical across types.py, handoff.py, docs, and registry
6. Zero silent dashboard breakages from telemetry schema changes — every metric/span rename generates a ContextCore notification task within the same CI run

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-14 21:25:35 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | completeness | critical | Add a requirement for schema versioning and migration strategy when the registry evolves (e.g., adding/removing attributes, changing enum cardinality). Currently REQ-6 mentions `schema_version: 2` but no requirement governs how version bumps propagate across repos or how older state files are handled. | Three independent repos consuming the same schema means version transitions are high-risk. Without a versioning contract, a registry change in ContextCore can silently break StartD8 and Wayfinder consumers. | New REQ-8 in Section 3, with acceptance criteria covering: version bump policy, backward-compatible vs. breaking change definitions, and minimum supported version window. | Verify that the requirement defines at least: (1) what constitutes a breaking change, (2) how consumers discover the current version, and (3) a deprecation timeline. |
| R1-S2 | ambiguity | high | REQ-1 states the registry "resolves `task.depends_on` vs `task.blocked_by`" but does not specify who decides, what the decision criteria are, or a deadline. This is an unresolved design decision masquerading as a requirement. | Requirements should be testable. "Resolve naming" is an action item, not a verifiable criterion. Leaving it open risks the requirement being perpetually unmet. | Refine REQ-1 acceptance criteria to either (a) pick a canonical name now and document the alias, or (b) add an explicit ADR action item with an owner and deadline in Section 5. | Confirm the acceptance criterion references a single canonical attribute name (not "one or the other"). |
| R1-S3 | completeness | high | No requirement addresses Wayfinder's consumer-side validation — `scripts/load_tasks_to_tempo.py` and Grafana dashboards are listed as consumers in Section 1 but have no acceptance criteria in any REQ. | Section 2.1 identifies that emitter-only attributes are "invisible downstream unless consumers are updated," yet no requirement ensures Wayfinder consumers are updated or validated. The gap analysis identifies the problem but the requirements don't close it. | Add acceptance criteria to REQ-5 or a new REQ covering Wayfinder consumer scripts and dashboard queries validating against the registry attribute list. | Check that at least one acceptance criterion references Wayfinder's `load_tasks_to_tempo.py` or dashboard JSON models. |
| R1-S4 | testability | high | REQ-7's round-trip test criterion ("diff is empty") is under-specified. It doesn't account for field ordering, timestamp precision, floating-point serialization, or optional fields that may be added/dropped during round-trip. | A naïve byte-level diff will produce false failures. Without specifying comparison semantics, implementations will either be too strict (fragile) or too loose (useless). | Refine REQ-7 final acceptance criterion to specify semantic equivalence (e.g., JSON-level key-value equality, tolerance for key ordering, handling of default/absent optional fields). | Review acceptance criterion for explicit comparison semantics; confirm it would not fail on key reordering alone. |
| R1-S5 | consistency | medium | Section 4 (Out of Scope) declares Wayfinder's `skill.*` / `capability.*` namespaces out of scope, but REQ-5 acceptance criteria state these namespaces should be "either added to ContextCore's registry or maintained in a Wayfinder-specific registry extension." These conflict — one says out of scope, the other requires a decision. | A reader cannot determine whether Wayfinder-specific namespaces need action or not. This will cause confusion during implementation. | Either remove the registry-extension language from REQ-5 and defer entirely, or remove the `skill.*`/`capability.*` bullet from Section 4 and keep REQ-5 as-is. Add a note explaining the chosen approach. | Verify Section 4 and REQ-5 do not contradict each other regarding `skill.*` / `capability.*` namespaces. |
| R1-S6 | feasibility | medium | REQ-6 requires "a schema derived from the registry" but no requirement specifies how registry YAML is transformed into a validatable schema (e.g., JSON Schema, Python dataclass, Weaver template). The mechanism is left entirely undefined. | Without specifying the schema derivation path, teams may implement incompatible validation approaches in each repo, defeating the purpose of a shared registry. | Add an acceptance criterion to REQ-6 (or a new REQ) specifying the schema format and the tool/process that generates it from registry YAML (e.g., Weaver codegen template producing JSON Schema). | Confirm the requirement names a concrete schema format and generation mechanism. |
| R1-S7 | traceability | medium | Requirements REQ-1 through REQ-7 are not traced back to specific gaps in Section 2. Some gaps (e.g., 2.3 ATTRIBUTE_MAPPINGS fragmentation, 2.5 No Cross-Repo CI) map obviously, but the mapping is implicit. | Explicit traceability ensures every identified gap has a corresponding requirement and no requirement is orphaned. This is especially important for a cross-repo document where different teams may own different gaps. | Add a traceability matrix (table) after Section 3 or in a new Section 3.1 mapping each Section 2.x gap to its covering REQ(s). | Verify every gap in Section 2 maps to at least one REQ, and every REQ maps to at least one gap. |
| R1-S8 | completeness | medium | No requirement assigns ownership or sequencing across repos. REQ-2 depends on REQ-1 (can't align emitter until registry is defined), and REQ-5 depends on REQ-1 completing. Section 5 lists dependencies but not implementation order or responsible teams. | Cross-repo work without clear ownership and ordering tends to stall. The document identifies three repos but never says who does what first. | Add a Section 5.1 or extend Section 5 with an implementation sequencing table: which REQs must complete before others, and which repo/team owns each. | Verify that a reader can determine the critical path and responsible party for each REQ without external context. |
| R1-S9 | testability | medium | Success Metric #2 ("All state files from all 3 producers validate against the registry schema") is not testable as stated — Wayfinder is listed as a consumer only (Section 1 table), not a producer. Either Wayfinder produces state files (undocumented) or the metric is wrong. | A success metric that references a non-existent producer cannot be measured. This undermines confidence in the metrics section. | Correct to "all 2 producers" (ContextCore, StartD8) or document Wayfinder's producer role if it exists. Also review Section 1 table for consistency. | Count producers in Section 1 and verify Success Metric #2 matches. |
| R1-S10 | completeness | low | The document does not specify how `opt_in` attributes (REQ-1) interact with the `ATTRIBUTE_MAPPINGS` deprecation layer (REQ-3). If an `opt_in` attribute is later deprecated, it would need a mapping entry, but the relationship between these two mechanisms is unspecified. | As the registry grows, the interaction between attribute stability levels (`opt_in`, `stable`, `deprecated`) and the dual-emit mapping layer will become a recurring source of confusion without a defined policy. | Add a note or acceptance criterion in REQ-3 clarifying that `ATTRIBUTE_MAPPINGS` entries are only required for `deprecated` → `stable` pairs, and that `opt_in` attributes do not participate in dual-emit. | Confirm the requirement explicitly states which stability levels require mapping entries. |

#### Review Round R2
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-14 21:26:21 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | ambiguity | critical | In REQ-6, specify the format of the "schema derived from the registry" (e.g., JSON Schema) and the mechanism for generating it. | The core requirement for cross-repo CI validation is not implementable without a concrete definition of the schema that will be used for validation. | Add a new acceptance criterion to REQ-6. | The chosen schema format is documented and a script to generate it from the Weaver registry YAML is checked into the ContextCore repository. |
| R2-S2 | feasibility | critical | Add a new requirement defining the distribution mechanism for the canonical registry and its derived schema across repositories. | Cross-repo CI validation (REQ-6) is not feasible unless consumer repositories (StartD8, Wayfinder) have a reliable, automated way to access the schema from the source repository (ContextCore). | Add a new requirement (e.g., REQ-8). | The chosen distribution method (e.g., publishing a versioned package, fetching a CI artifact) is implemented and used by CI jobs in all three repositories. |
| R2-S3 | completeness | high | Add a new requirement to define a semantic versioning policy for the registry and the derived schema. | The document mentions a single `schema_version` number, which is insufficient for managing breaking vs. non-breaking changes. A formal policy is needed for consumers to adapt safely to schema evolution. | Add a new requirement (e.g., REQ-9). | A versioning policy is documented in the registry's contribution guide, and the registry manifest is updated to use a semantic version number. |
| R2-S4 | completeness | high | Add a requirement to define and document the lifecycle for deprecated attributes, including migration timelines and removal criteria. | REQ-3 introduces the concept of deprecation but lacks a policy. Without a formal process, deprecated attributes will persist indefinitely, creating long-term maintenance overhead and schema clutter. | Add a new requirement (e.g., REQ-10). | A deprecation policy is documented. A new attribute is added to the registry as deprecated and a ticket is filed to track its removal according to the policy. |
| R2-S5 | feasibility | high | Expand REQ-5 to include an AC for auditing and updating key Wayfinder consumers (e.g., Grafana dashboards, `load_tasks_to_tempo.py`) to use the canonical attributes. | Aligning the prose specification is insufficient if the implemented consumers are not also updated. The user-facing impact of the drift problem will not be resolved without updating this downstream tooling. | Add a new acceptance criterion to REQ-5. | An audit of key Wayfinder consumers is performed, and tickets are created to track the work of migrating them to the canonical registry attributes. |
| R2-S6 | testability | medium | Specify where the cross-repo round-trip test from REQ-7's AC will be implemented and executed. | A cross-repo integration test has non-trivial dependency and infrastructure requirements. Defining its location and ownership clarifies implementation complexity and ensures the test is built and maintained. | Add a note or sub-bullet to the final acceptance criterion in REQ-7. | The test is implemented in the designated repository and runs successfully as part of its CI pipeline, pulling in the other repository's code/artifacts as a dependency. |
| R2-S7 | ambiguity | medium | In REQ-1, clarify the meaning and implications of marking an attribute as `opt_in`. | The term `opt_in` is not defined. It could mean "optional", "experimental", or have a specific technical meaning in the Weaver tool. This ambiguity could lead to incorrect implementation by producers or consumers. | Add a definition or footnote to REQ-1. | The term is defined in the document's glossary or inline. The registry implementation for these attributes aligns with the documented definition. |
| R2-S8 | ambiguity | medium | Make a firm architectural decision in REQ-5 on how to handle Wayfinder-specific namespaces instead of deferring it. | The current AC ("either added... or maintained...") creates uncertainty. A decisive approach, such as mandating a federated registry model, provides a clear path forward and prevents scope creep in the core registry. | Modify the second acceptance criterion of REQ-5 to be prescriptive. | The AC is updated to state that Wayfinder will maintain its own registry that extends the ContextCore registry. A proof-of-concept for this extension mechanism is created. |
| R2-S9 | testability | medium | Add an AC to REQ-1 requiring an automated test that fails if the StartD8 emitter produces attributes not defined in the registry. | The current AC ("All attributes... are present") relies on manual verification, which is brittle. An automated check is necessary to prevent future schema drift as the emitter's code evolves. | Add a new acceptance criterion to REQ-1. | A new CI job is created that generates state files using the emitter's test suite and validates their attributes against the canonical registry, failing on any mismatches. |
| R2-S10 | consistency | low | Refine the Success Metrics (Section 6) to be measurable outcomes rather than a restatement of completed requirements. | The current metrics verify that the work was done, not that the work delivered value. Outcome-based metrics (e.g., "Reduction in time to diagnose data pipeline errors") better justify the project and measure its true impact. | Modify Section 6. | The project team agrees on 2-3 measurable, outcome-based metrics (e.g., related to incident reduction, developer velocity, or data quality) before implementation begins. |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-14 21:29:22 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Change | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | ambiguity | critical | REQ-1 says "one canonical name, the other either removed or aliased" for `task.depends_on` vs `task.blocked_by`, but the implementation plan correctly identifies these as semantically distinct attributes (structural deps vs. runtime blockers). The requirement should be updated to reflect this. | The requirement forces a false dichotomy. The plan's decision to keep both is sound, but it technically violates REQ-1 as written. | Rewrite REQ-1 acceptance criteria bullet 2: "Registry defines `task.blocked_by` (runtime blockers, required) and `task.depends_on` (structural dependencies, opt_in) as distinct attributes with documented semantic distinction." | Verify the acceptance criterion no longer implies a choice between the two names. |
| R3-F2 | completeness | critical | No requirement specifies how the registry or schema is distributed to consumer repos. REQ-6 assumes cross-repo CI validation but the mechanism for schema access is undefined. | A requirement that implicitly depends on infrastructure that doesn't exist and isn't specified is not implementable. | Add REQ-8: "Registry Distribution — The canonical registry and any derived schema artifacts MUST be accessible to CI pipelines in all three repos via a documented, versioned mechanism." | Verify the requirement specifies at least one concrete distribution mechanism and its versioning approach. |
| R3-F3 | completeness | high | REQ-6 does not specify the schema format. "A schema derived from the registry" could mean JSON Schema, a Python validator, a YAML allowlist, or a Weaver template output. | Implementers cannot build to an unspecified format. Different teams may choose incompatible approaches. | Add acceptance criterion to REQ-6: "The validation schema is a JSON Schema document generated from registry YAML via a documented Weaver template or script, checked into the ContextCore repository." | Verify the acceptance criterion names a specific schema format and generation method. |
| R3-F4 | testability | high | REQ-7's "diff is empty" acceptance criterion is ambiguous about comparison semantics. JSON key ordering, timestamp precision, default value handling, and optional field presence/absence can all cause spurious diff failures. | Without specifying comparison semantics, the round-trip test will either be too strict (fragile, many false failures) or too loose (meaningless). | Rewrite REQ-7 final AC: "Round-trip test: emitter → StateManager.load_span() → StateManager.save_span() → semantic comparison (JSON key-value equality ignoring key order; absent optional fields treated as equivalent to null/default; timestamps compared at millisecond precision)." | Verify the AC specifies exact comparison rules that an implementer could code without further clarification. |
| R3-F5 | consistency | high | Success Metric #2 says "All state files from all 3 producers" but Section 1 identifies only 2 producers (ContextCore, StartD8). Wayfinder is consumer-only. | An unmeasurable success metric undermines the metrics section's credibility. | Change to "all 2 producers (ContextCore StateManager, StartD8 task_tracking_emitter)" or document Wayfinder's producer role if it exists. | Count producers in Section 1 table and verify Success Metric #2 matches. |
| R3-F6 | consistency | medium | REQ-5 AC says Wayfinder-specific namespaces should be "either added to ContextCore's registry or maintained in a Wayfinder-specific registry extension," but Section 4 (Out of Scope) explicitly excludes `skill.*` / `capability.*` namespaces. | A requirement cannot simultaneously require a decision and declare the subject out of scope. | Either (a) remove the registry-extension language from REQ-5 AC2 and add "Wayfinder-specific namespaces are deferred per Section 4," or (b) remove the `skill.*`/`capability.*` bullet from Section 4. | Verify Section 4 and REQ-5 do not contradict each other. |
| R3-F7 | completeness | medium | No requirement defines what `opt_in` means in the context of this registry. OTel semconv has specific stability levels (experimental, stable, deprecated) but `opt_in` is a requirement level (required, recommended, opt_in), and these are orthogonal. The requirements conflate them. | Implementers need to know whether `opt_in` means "experimental and subject to removal," "optional but stable," or something else. This affects producer and consumer behavior. | Add a definitions section or footnote in REQ-1 clarifying that `opt_in` follows OTel semconv requirement level semantics: producers MAY emit, consumers MUST tolerate absence. | Verify the term is defined with enough precision that an implementer knows the behavioral contract for opt_in attributes. |
| R3-F8 | completeness | medium | No requirement addresses deprecation lifecycle — how long deprecated attributes remain in the registry, when they're removed, and how consumers are notified of upcoming removals. REQ-3 references `deprecated:` fields but treats deprecation as a static property rather than a process. | Without a deprecation policy, deprecated attributes will accumulate indefinitely, and ATTRIBUTE_MAPPINGS will grow without bound. | Add REQ-9 or extend REQ-3: "Deprecated attributes MUST include a `deprecated.since` version and a `deprecated.removal_target` version. Attributes past their removal target MUST be removed in the next major registry version." | Verify the requirement specifies temporal bounds for deprecation, not just the existence of a deprecated flag. |

#### Review Round R2

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-14 21:30:11 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R2-F1 | completeness | high | Add a new requirement: "REQ-8: Schema Distribution Mechanism". The requirements mandate cross-repo validation (REQ-6) but do not mandate the necessary prerequisite: a reliable, automated way for consumer repos to obtain the schema to validate against. | A requirement for validation is not useful if the schema is inaccessible or must be manually copied between repos, as this undermines the entire goal of preventing drift. |
| R2-F2 | ambiguity | high | Refine REQ-5 to be more decisive about Wayfinder-specific namespaces. The current AC ("either added... or maintained...") combined with the "Out of Scope" section creates a contradiction. | The requirements should provide a clear architectural direction. A better AC would be: "Wayfinder-specific namespaces (`skill.*`, `capability.*`) MUST be maintained in a Wayfinder-specific registry that formally extends the ContextCore registry." This provides a clear, scalable path forward. |
| R2-F3 | completeness | medium | Add a new requirement: "REQ-9: Schema Evolution Policy". The document mentions a schema version but lacks any requirement for a formal policy on versioning, defining breaking changes, and managing a deprecation lifecycle. | Without a required policy, schema evolution will be ad-hoc, leading to unexpected breakages in consumer repositories when changes are made in ContextCore. |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-14 21:50:44 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Change | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | completeness | critical | Add REQ-8: Schema Distribution Mechanism. REQ-6 mandates cross-repo CI validation but no requirement specifies how consumer repos obtain the schema. This is a missing prerequisite requirement, not an implementation detail. | Without a distribution requirement, REQ-6's acceptance criteria ("StartD8 emitter tests validate output against a schema derived from the registry") is unimplementable — the schema lives in ContextCore but the tests run in StartD8. | Add REQ-8 with ACs: (1) Registry artifacts are published as a versioned, fetchable resource (package, release artifact, or submodule); (2) Consumer repos pin to a specific registry version in their CI config; (3) Version update is a deliberate, reviewable change (not auto-fetched from HEAD). | Verify that an implementer in StartD8 can determine from REQ-8 alone how to access a specific version of the registry in CI. |
| R1-F2 | completeness | critical | Add REQ-9: Schema Evolution Policy. No requirement governs version bump semantics, breaking change definitions, or deprecation lifecycle timelines. REQ-6 mentions `schema_version: 2` and REQ-3 mentions `deprecated:` fields, but these are static references with no process attached. | Three repos consuming the same schema without a versioning contract means any registry change is a potential uncoordinated breaking change. This is the highest-risk gap for long-term maintainability. | Add REQ-9 with ACs: (1) Registry uses semver; (2) Breaking changes defined (attribute removal, type change, enum member removal); (3) Non-breaking changes defined (new opt_in attribute, new enum member, documentation-only); (4) Deprecated attributes include `since` version and `removal_target` version; (5) Minimum 1 minor version between deprecation and removal. | Verify the requirement answers: "What version bump is required for adding an opt_in attribute? For removing a deprecated one?" |
| R1-F3 | ambiguity | high | REQ-1's acceptance criteria bullet 2 ("one canonical name, the other either removed or aliased") forces a false choice between `task.depends_on` and `task.blocked_by`, which have genuinely different semantics (structural dependency vs. runtime blocker). The plan correctly identifies this but technically violates the requirement as written. | A requirement that the correct implementation violates is a defective requirement. The plan's decision to keep both is sound, but the AC should be updated to reflect this rather than leaving an unresolvable tension. | Rewrite REQ-1 AC bullet 2: "Registry defines `task.blocked_by` (runtime blockers, required) and `task.depends_on` (structural dependencies, opt_in) as distinct attributes with documented semantic distinction. Emitters MUST use the semantically appropriate attribute." | Verify the AC no longer implies a choice between the two names and instead specifies both with distinct semantics. |
| R1-F4 | testability | high | REQ-7's final AC ("diff is empty") has no defined comparison semantics. JSON key ordering, floating-point serialization, timestamp precision, and optional field handling will all cause false failures or false passes depending on implementation. | An AC that produces different pass/fail results depending on how you implement comparison is not testable. Multiple prior reviewers (R1-S4/round1, R3-F4) flagged this. | Rewrite: "Round-trip test uses semantic comparison: JSON key-value equality ignoring key order; absent optional fields treated as equivalent to default values; timestamps compared at millisecond precision; string values compared exactly." | Verify the AC specifies comparison rules precise enough to implement without further clarification. |
| R1-F5 | consistency | high | Success Metric #2 references "all 3 producers" but Section 1's table identifies only 2 producers (ContextCore, StartD8). Wayfinder is consumer-only. | An unmeasurable success metric undermines the entire metrics section. This error has been flagged by multiple prior reviewers (R1-S9/round1, R3-F5) and should be corrected. | Change to "All state files from both producers (ContextCore StateManager, StartD8 task_tracking_emitter) validate against the registry schema." | Count producers in Section 1 and verify metric matches. |
| R1-F6 | consistency | medium | REQ-5 AC2 says Wayfinder-specific namespaces should be "either added to ContextCore's registry or maintained in a Wayfinder-specific registry extension," but Section 4 explicitly excludes `skill.*`/`capability.*`. These are contradictory. | Multiple prior reviewers (R1-S5/round1, R3-F6, R2-F2) flagged this. A requirement and an out-of-scope declaration cannot cover the same topic with different dispositions. | Rewrite REQ-5 AC2: "Wayfinder-specific namespaces (`skill.*`, `capability.*`) remain locally documented in Wayfinder. A future registry extension mechanism is deferred per Section 4." Remove ambiguity by aligning with the out-of-scope declaration. | Verify Section 4 and REQ-5 are consistent regarding `skill.*`/`capability.*` namespaces. |
| R1-F7 | completeness | medium | No requirement covers Wayfinder consumer-side updates. REQ-5 addresses Wayfinder's prose documentation but not its runtime consumers (`load_tasks_to_tempo.py`, Grafana dashboards), which are the actual user-facing manifestation of the drift problem. | Section 2.1 states "emitter-only attributes are invisible downstream unless consumers are updated," yet no requirement ensures those consumers are updated. The gap analysis identifies the problem but the requirements don't close it. | Add AC to REQ-5: "An audit of Wayfinder consumer code (`load_tasks_to_tempo.py`) and dashboard definitions is performed. Tickets are filed for attributes that should be surfaced but are not currently queried." | Verify at least one AC references a Wayfinder consumer artifact (script or dashboard). |
| R1-F8 | clarity | medium | REQ-1 uses `opt_in` as a requirement level but never defines it. OTel semconv distinguishes between stability levels (experimental, stable, deprecated) and requirement levels (required, recommended, opt_in). The requirements use `opt_in` without specifying which dimension it occupies or what behavioral contract it implies. | Implementers need to know: does `opt_in` mean "producers MAY emit, consumers MUST tolerate absence"? Or does it mean "experimental, may be removed"? These have very different implications for consumer code. | Add a definitions subsection in Section 3 or a footnote on REQ-1: "`opt_in` follows OTel semantic convention requirement level semantics: producers MAY emit the attribute; consumers MUST NOT require its presence. `opt_in` is orthogonal to stability — an `opt_in` attribute can be `stable`." | Verify the term is defined precisely enough for an implementer to know the producer and consumer behavioral contracts. |

#### Review Round R2

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-14 21:51:36 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R2-F1 | testability | high | Refine REQ-7's "diff is empty" acceptance criterion to require *semantic equivalence* instead. | A literal diff is brittle and will fail on non-functional changes like JSON key reordering or floating-point precision differences. The requirement should specify the comparison logic (e.g., key-value equality, timestamp tolerance) to be testable and robust. |
| R2-F2 | completeness | critical | Add a new requirement for a formal schema evolution and semantic versioning policy. | The requirements mention a `schema_version` but lack a policy for how it should be incremented. Without defining what constitutes a breaking change (major version bump) vs. a non-breaking change (minor/patch), consumers cannot safely adapt to schema evolution. |
| R2-F3 | completeness | high | Add a new requirement to define and document the lifecycle for deprecated attributes. | REQ-3 addresses consolidating mappings for deprecated attributes but doesn't require a policy for their eventual removal. This leads to indefinite support for old attributes, increasing schema complexity and maintenance burden over time. |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-14 21:55:05 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Change | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | completeness | critical | Add REQ-8: Schema Distribution Mechanism. No requirement specifies how consumer repos access the canonical registry. REQ-6 assumes cross-repo validation but the prerequisite infrastructure is unspecified. | Without distribution, cross-repo CI is unimplementable. This has been flagged by 4+ prior reviewers across rounds (R2-S2, R3-F2, R1-F1/prior, R2-F1) and represents the strongest consensus gap. | Add REQ-8: "The canonical registry MUST be available to consumer repos via a versioned, fetchable mechanism." ACs: (1) Published as versioned artifact (package, release asset, or tagged submodule); (2) Consumer repos pin to a specific version; (3) Version updates require explicit, reviewable changes. | Verify that an implementer in StartD8 can determine from REQ-8 how to access a specific registry version in CI without reading ContextCore HEAD. |
| R1-F2 | completeness | critical | Add REQ-9: Schema Evolution Policy. No requirement governs how schema versions are bumped, what constitutes breaking vs. non-breaking changes, or how deprecation timelines work. | Cross-repo schema without versioning policy = uncoordinated breaking changes. Flagged by 5+ prior reviewers (R1-S1/round1, R2-S3, R2-F3, R1-F2/prior, R2-F2/round2). Strongest consensus item across all review rounds. | Add REQ-9 with ACs: (1) Registry uses semver; (2) Breaking changes defined (removal, type change, enum removal); (3) Non-breaking defined (new opt_in, new enum member, docs); (4) Deprecated attrs include `since` and `removal_target` versions; (5) Minimum 1 minor version between deprecation and removal. | Verify the requirement answers: "What version bump for adding opt_in? For removing deprecated?" |
| R1-F3 | ambiguity | high | REQ-1 AC bullet 2 forces a false choice between `task.depends_on` and `task.blocked_by`. The plan correctly identifies these as semantically distinct. The requirement should be rewritten to reflect coexistence rather than requiring elimination of one. | A requirement that the correct implementation violates is defective. Prior reviewers R3-F1 and R1-F3/prior flagged this. The plan's analysis (Section 1.2 key decision) is sound but technically non-compliant with the requirement as written. | Rewrite REQ-1 AC bullet 2: "Registry defines `task.blocked_by` (runtime blockers) and `task.depends_on` (structural dependencies) as distinct attributes with documented semantic distinction. Each has appropriate requirement level." | Verify the AC no longer implies elimination of one name and instead specifies both with distinct semantics. |
| R1-F4 | testability | high | REQ-7's "diff is empty" AC is ambiguous about comparison semantics. JSON key ordering, timestamp precision, floating-point serialization, and default value handling can all cause false failures. | Flagged by 4+ prior reviewers (R1-S4/round1, R3-F4, R2-F1/round2, R1-F4/prior). An AC that produces different results depending on comparison implementation is not testable. | Rewrite: "Semantic equivalence: JSON key-value equality ignoring key order; absent optional fields equivalent to defaults; timestamps at millisecond precision; string values compared exactly." | Verify the AC specifies rules precise enough to implement the comparison function without further clarification. |
| R1-F5 | consistency | high | Success Metric #2 says "all 3 producers" but Section 1 identifies 2 producers. Wayfinder is consumer-only. | Factual error. Flagged by R1-S9/round1, R3-F5, R1-F5/prior. Trivial to fix but undermines metrics credibility if left. | Change to "both producers (ContextCore StateManager, StartD8 task_tracking_emitter)." | Count producers in Section 1 table; verify metric matches. |
| R1-F6 | consistency | medium | REQ-5 AC2 and Section 4 contradict each other on `skill.*`/`capability.*` namespaces. REQ-5 requires a decision; Section 4 declares them out of scope. | Flagged by R1-S5/round1, R3-F6, R1-F6/prior, R2-F2. Cannot simultaneously require action and declare out of scope. | Rewrite REQ-5 AC2: "Wayfinder-specific namespaces (`skill.*`, `capability.*`) remain locally documented in Wayfinder. A future registry extension mechanism is deferred per Section 4." | Verify Section 4 and REQ-5 are consistent. |
| R1-F7 | completeness | medium | No requirement covers updating Wayfinder's runtime consumers (`load_tasks_to_tempo.py`, Grafana dashboards). REQ-5 addresses prose alignment only. | Section 2.1 identifies the user-facing problem but requirements don't close it. Flagged by R1-S3/round1, R2-S5, R1-F7/prior. | Add AC to REQ-5: "Audit of Wayfinder consumer code and dashboard definitions performed; tickets filed for attributes that should be surfaced but are not currently queried." | Verify at least one AC references a Wayfinder consumer artifact. |
| R1-F8 | clarity | medium | REQ-1 uses `opt_in` without defining it. OTel semconv has distinct axes for stability (experimental/stable/deprecated) and requirement level (required/recommended/opt_in). The requirements conflate these. | Flagged by R2-S7, R3-F7, R1-F8/prior. Without definition, implementers cannot determine the behavioral contract for `opt_in` attributes. | Add definition: "`opt_in` follows OTel semantic convention requirement level: producers MAY emit; consumers MUST NOT require presence. Orthogonal to stability — an `opt_in` attribute can be `stable`." | Verify the term is defined with producer and consumer behavioral contracts. |
| R1-F9 | completeness | medium | REQ-6 does not specify the schema format or generation mechanism. "A schema derived from the registry" could be JSON Schema, Python validator, YAML allowlist, or Weaver template output. | Flagged by R1-S6/round1, R2-S1, R3-F3. Without specifying format and tooling, teams will implement incompatible validators. | Add AC to REQ-6: "Validation schema is a JSON Schema document generated from registry YAML via a documented script or Weaver template, checked into ContextCore." | Verify the AC names a concrete schema format and generation tool. |
| R1-F10 | completeness | medium | No requirement addresses the interaction between `opt_in` stability levels and `ATTRIBUTE_MAPPINGS`. If an `opt_in` attribute is later deprecated, it would need a mapping entry — but no policy governs this lifecycle. | As the registry grows, the interaction between requirement levels and the dual-emit layer becomes a recurring confusion source. Prior reviewer R1-S10/round1 flagged this. | Add AC to REQ-3: "`ATTRIBUTE_MAPPINGS` entries are required only for `deprecated` → replacement pairs. `opt_in` and `recommended` attributes do not participate in dual-emit." | Verify the requirement explicitly states which attribute categories require mapping entries. |

#### Review Round R2

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-14 21:55:56 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R2-F1 | ambiguity | critical | REQ-1 forces a false choice between `task.depends_on` and `task.blocked_by`, stating one must be canonical and the other removed or aliased. | The implementation plan correctly identifies that these attributes have distinct and valid semantics (structural vs. runtime dependency). The requirement is flawed because it forces a technically incorrect simplification, and the plan's sound decision technically violates it. The requirement should be updated to permit both attributes with clear definitions. |
| R2-F2 | completeness | critical | The document is missing a requirement for a Schema Evolution Policy, including semantic versioning, the definition of a breaking change, and a deprecation lifecycle. | REQ-6 mentions a static `schema_version: 2` but provides no process for managing change. For a schema shared across three repos, the lack of a required versioning and change management policy is the single biggest risk to the system's long-term stability and maintainability. |
| R2-F3 | consistency | high | REQ-5 and Section 4 (Out of Scope) are contradictory regarding Wayfinder-specific namespaces (`skill.*`, `capability.*`). | REQ-5's acceptance criteria mandates a decision on how to handle these namespaces (add to core registry or create an extension), while Section 4 explicitly declares them out of scope. A document cannot require an action on a topic it simultaneously deems out of scope. One of them must be changed to create a consistent directive. |
| R2-F4 | consistency | medium | Success Metric #2 ("All state files from all 3 producers validate...") is factually incorrect. | The problem statement in Section 1 clearly identifies only two producers (ContextCore, StartD8 SDK) and one consumer (Wayfinder). A success metric that relies on a non-existent third producer is unmeasurable and undermines the credibility of the metrics section. It should be corrected to "all 2 producers". |

