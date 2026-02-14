# Requirements: Task Tracking Emission During Export

**Date:** 2026-02-14
**Status:** Draft — for review and refinement
**Scope:** Optional `--emit-tasks` flag on `contextcore manifest export` that creates OTel task spans for every artifact in coverage gaps, making pipeline work visible as traces before execution begins.

---

## 1. Problem Statement

The export process already computes everything needed to describe the work ahead:

- **What** artifacts need to be created (coverage gaps)
- **Why** each artifact exists (derivation rules: business criticality → alert severity)
- **How** they relate to each other (dependency graph)
- **What** a valid result looks like (expected output contracts: fields, max_lines, completeness markers)
- **What** concrete parameter values to use (resolved artifact parameters)
- **When** they should be built (dependency ordering)

But this information is written to static JSON files. The pipeline systems (plan ingestion, artisan) then re-create their own task tracking independently — if at all. The `TaskSpanContract` and `ArtifactIntent` models exist in the A2A governance layer, but they are populated *after* the fact, not at the moment the work is defined.

**The result:** The most detailed description of the work — the export — is disconnected from the observability infrastructure built to track that work.

### What This Means in Practice

1. **No pre-execution trace**: You can't query Tempo for "what needs to be built for project X?" before the artisan runs
2. **No unified timeline**: Export, plan ingestion, and artisan each track progress separately — no single trace spans the full lifecycle
3. **No gate-to-task linkage**: A2A gate results (GateResult) exist as standalone checks, not as events on the task spans they validate
4. **No dependency visualization**: The artifact dependency graph exists in onboarding-metadata.json but not as linked spans in Tempo
5. **No progress tracking before execution**: ContextCore's parent progress tracking (epic → story → task) can't work if the tasks don't exist as spans yet

---

## 2. Proposed Solution

Add an optional `--emit-tasks` flag to `contextcore manifest export` that, in addition to writing the 4 output files, emits OTel task spans representing the work to be done.

### Behavior

```bash
# Default: no change (backward compatible)
contextcore manifest export -p .contextcore.yaml -o ./output --emit-provenance

# New: also emit task tracking spans
contextcore manifest export -p .contextcore.yaml -o ./output --emit-provenance --emit-tasks

# With explicit project ID for task tracking
contextcore manifest export -p .contextcore.yaml -o ./output --emit-tasks --project-id my-project
```

### What Gets Emitted

For a project with 2 targets and 7 artifact types per target (14 artifacts total, 10 in coverage gaps):

```
Trace: export-{project_id}-{timestamp}
│
├── [epic] {project_id} Observability Artifact Generation
│   │
│   ├── [story] Dashboard Artifacts (2 tasks)
│   │   ├── [task] checkout_api-dashboard          status: needed
│   │   └── [task] payment_svc-dashboard           status: needed
│   │
│   ├── [story] PrometheusRule Artifacts (2 tasks)
│   │   ├── [task] checkout_api-prometheus-rules    status: needed
│   │   └── [task] payment_svc-prometheus-rules     status: needed
│   │
│   ├── [story] ServiceMonitor Artifacts (2 tasks)
│   │   ├── [task] checkout_api-service-monitor     status: needed
│   │   └── [task] payment_svc-service-monitor      status: needed
│   │
│   └── ... (loki_rule, slo_definition, notification_policy, runbook groups)
│
└── [events on each task span]
    ├── task.created { artifact_type, target, priority, status }
    ├── task.contract { derivation_rules, expected_output_contract }
    └── task.dependencies { depends_on: [...] }
```

---

## 3. Requirements

### R1: Task Hierarchy Emission

| ID | Requirement | Priority |
|----|------------|----------|
| R1.1 | Export emits an **epic span** for the overall artifact generation project | Must |
| R1.2 | Export emits **story spans** grouped by artifact type (one story per type with gaps) | Must |
| R1.3 | Export emits **task spans** for each artifact in `coverage.gaps` (status=needed) | Must |
| R1.4 | Task spans are children of their artifact-type story span | Must |
| R1.5 | Story spans are children of the epic span | Must |
| R1.6 | Existing artifacts (status=exists) are emitted as completed task spans | Should |
| R1.7 | Epic span includes overall coverage percentage as an attribute | Should |

### R2: Task Span Attributes

| ID | Requirement | Priority |
|----|------------|----------|
| R2.1 | Each task span includes `artifact.id`, `artifact.type`, `artifact.target`, `artifact.priority` | Must |
| R2.2 | Each task span includes `artifact.status` (needed, exists, outdated, skipped) | Must |
| R2.3 | Each task span includes resolved parameter values from `artifact.parameters` | Must |
| R2.4 | Each task span includes derivation rules from `artifact.derived_from` as a span event | Should |
| R2.5 | Each task span includes the `expected_output_contract` for its type (depth, max_lines, max_tokens, completeness_markers, fields) | Should |
| R2.6 | Task spans for needed artifacts have status `UNSET`; existing artifacts have status `OK` | Must |

### R3: Dependency Modeling

| ID | Requirement | Priority |
|----|------------|----------|
| R3.1 | Task spans include `depends_on` artifact IDs as span attributes | Must |
| R3.2 | Task spans include **span links** to their dependency task spans | Should |
| R3.3 | The dependency graph from `onboarding-metadata.json` is faithfully represented in the span topology | Must |

### R4: Integration with A2A Governance

| ID | Requirement | Priority |
|----|------------|----------|
| R4.1 | Emitted task spans use the `TaskSpanContract` schema from `contracts/a2a/models.py` | Must |
| R4.2 | Each artifact task includes an `ArtifactIntent` event with `intent=create` for needed artifacts | Should |
| R4.3 | The epic span's `trace_id` is recorded in `onboarding-metadata.json` as `task_trace_id` for downstream correlation | Must |
| R4.4 | Plan ingestion and artisan can **resume** task spans (update status, add events) rather than creating new ones | Should |
| R4.5 | Gate results (GateResult) can be attached as events to the relevant task span via `task_trace_id` | Should |

### R5: CLI and Configuration

| ID | Requirement | Priority |
|----|------------|----------|
| R5.1 | `--emit-tasks` is opt-in; default behavior is unchanged | Must |
| R5.2 | `--emit-tasks` requires an OTLP endpoint (uses `OTEL_EXPORTER_OTLP_ENDPOINT` or `--endpoint`) | Must |
| R5.3 | `--emit-tasks` works with `--dry-run` (previews what would be emitted without sending) | Should |
| R5.4 | Task emission uses the same `TaskTracker` infrastructure as `contextcore task start/update/complete` | Must |
| R5.5 | `--project-id` overrides the project ID used for task tracking (defaults to `spec.project.id` from manifest) | Should |

### R6: Observability and Querying

| ID | Requirement | Priority |
|----|------------|----------|
| R6.1 | Emitted tasks are queryable via TraceQL: `{ span.task.type = "story" && span.project.id = "my-project" }` | Must |
| R6.2 | The full artifact generation plan is visible as a single trace in Tempo's trace view | Must |
| R6.3 | Coverage progress (% of tasks completed) is derivable from task span statuses via Loki recording rules | Should |
| R6.4 | A Grafana dashboard panel can show the artifact generation plan as a task hierarchy | Nice to have |

### R7: Backward Compatibility and Safety

| ID | Requirement | Priority |
|----|------------|----------|
| R7.1 | All existing export behavior is unchanged when `--emit-tasks` is not used | Must |
| R7.2 | Task emission failure does not fail the export — spans are best-effort | Must |
| R7.3 | Repeated exports with `--emit-tasks` create new traces (not duplicates on the same trace) | Must |
| R7.4 | `--emit-tasks` adds `task_trace_id` and `task_emission_timestamp` to onboarding-metadata.json for downstream correlation | Must |

---

## 4. Non-Requirements (Explicit Exclusions)

| Exclusion | Rationale |
|-----------|-----------|
| Task spans do NOT trigger any pipeline execution | Export declares work; plan ingestion + artisan execute it |
| Task spans do NOT replace the 4 output files | Spans are supplementary observability, not a data transport |
| Task spans are NOT updated by the export process after initial emission | Downstream systems (plan ingestion, artisan) update the spans |
| This does NOT become the default behavior | Opt-in via `--emit-tasks` only |
| This does NOT require a running K8s cluster | Works with any OTLP endpoint (local Tempo, cloud backend, etc.) |

---

## 5. Data Flow

```
.contextcore.yaml
       │
       ▼
contextcore manifest export --emit-tasks
       │
       ├──▶ 4 output files (unchanged)
       │    ├── ProjectContext CRD
       │    ├── Artifact Manifest
       │    ├── Provenance JSON
       │    └── Onboarding Metadata (+ task_trace_id)
       │
       └──▶ OTel spans via OTLP
            │
            ├── Epic span: "Project Observability Artifacts"
            │     attributes: project_id, coverage_percent, total_gaps, total_artifacts
            │
            ├── Story spans (one per artifact type with gaps)
            │     attributes: artifact_type, gap_count, expected_depth
            │
            └── Task spans (one per artifact in coverage.gaps)
                  attributes: artifact_id, artifact_type, target, priority, status,
                              parameters.*, depends_on
                  events:
                    - task.created
                    - task.contract (derivation_rules, expected_output_contract)
                    - task.dependencies (depends_on artifact IDs)
                  links:
                    - dependency task spans (via depends_on)
```

### Downstream Correlation

```
Export emits task_trace_id in onboarding-metadata.json
                    │
                    ▼
Plan ingestion reads task_trace_id
    │
    ├── Maps artifacts → features, carries task_trace_id per feature
    ├── Updates task span status: needed → in_progress
    └── Emits ArtifactIntent events on task spans
                    │
                    ▼
Artisan workflow receives task_trace_id in seed
    │
    ├── DESIGN phase: adds design_calibration event to task span
    ├── IMPLEMENT phase: updates task span with generated file paths
    ├── TEST phase: adds test_result event to task span
    ├── REVIEW phase: adds review_result event to task span
    └── FINALIZE phase: completes task span (status → OK or ERROR)
                    │
                    ▼
Single trace in Tempo spans the full lifecycle:
    Export (task created) → Plan Ingestion (routed) → Artisan (designed → implemented → tested → finalized)
```

---

## 6. Semantic Conventions for Task Spans

Following existing ContextCore semantic conventions from `docs/semantic-conventions.md`:

### Epic Span Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `project.id` | string | Project identifier from manifest |
| `task.id` | string | Epic task ID (e.g., `{project_id}-artifact-generation`) |
| `task.type` | string | `epic` |
| `task.title` | string | `"{project_name} Observability Artifact Generation"` |
| `task.status` | string | `todo` (initial) |
| `coverage.total_required` | int | Total required artifacts |
| `coverage.total_existing` | int | Currently existing artifacts |
| `coverage.total_gaps` | int | Artifacts needing generation |
| `coverage.percent` | float | Overall coverage percentage |
| `export.source_checksum` | string | SHA-256 of source manifest |

### Story Span Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `task.id` | string | Story ID (e.g., `{project_id}-dashboard-artifacts`) |
| `task.type` | string | `story` |
| `task.parent_id` | string | Epic task ID |
| `artifact.type` | string | Artifact type (dashboard, prometheus_rule, etc.) |
| `artifact.gap_count` | int | Number of needed artifacts of this type |
| `expected_output.depth` | string | Expected depth from calibration hints |
| `expected_output.max_lines` | int | Max lines from expected output contract |

### Task Span Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `task.id` | string | Artifact ID (e.g., `checkout_api-dashboard`) |
| `task.type` | string | `task` |
| `task.parent_id` | string | Story task ID |
| `task.title` | string | Artifact name (e.g., "checkout-api Service Dashboard") |
| `task.status` | string | `todo` (needed) or `done` (exists) |
| `artifact.id` | string | Same as task.id |
| `artifact.type` | string | dashboard, prometheus_rule, etc. |
| `artifact.target` | string | Target service name |
| `artifact.priority` | string | required, recommended, optional |
| `artifact.depends_on` | string[] | Dependency artifact IDs |
| `artifact.parameters.*` | various | Resolved parameter values |

### Task Span Events

| Event | Attributes | When |
|-------|-----------|------|
| `task.created` | `source: "contextcore.manifest.export"`, `artifact_type`, `target` | On emission |
| `task.contract` | `derivation_rules` (JSON), `expected_output_contract` (JSON) | On emission |
| `task.dependencies` | `depends_on` (list), `dependency_count` | On emission, if depends_on non-empty |

---

## 7. Implementation Considerations

### Using Existing Infrastructure

| Component | Exists? | How It's Used |
|-----------|---------|---------------|
| `TaskTracker` | Yes | `start_task()`, `update_status()`, `complete_task()` with parent_id |
| `TaskLogger` | Yes | Structured log emission for metrics derivation |
| `TaskSpanContract` | Yes | A2A contract schema for task span attributes |
| `ArtifactIntent` | Yes | A2A contract for artifact work declaration |
| `OTLP exporter` | Yes | Configured via `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `coverage.gaps` | Yes | Computed during `generate_artifact_manifest()` |
| `artifact_dependency_graph` | Yes | Computed in `build_onboarding_metadata()` |
| `expected_output_contracts` | Yes | Computed in `build_onboarding_metadata()` |
| `derivation_rules` | Yes | Computed in `build_onboarding_metadata()` |
| `resolved_artifact_parameters` | Yes | Computed in `build_onboarding_metadata()` |

### Key Design Decision: Emit Then End

Task spans are emitted as **ended spans** with status `UNSET` (for needed artifacts) or `OK` (for existing artifacts). They are not long-running spans that stay open until the artisan completes.

**Rationale:** Long-running spans would require the export process to stay alive or persist span context across process boundaries. Instead, downstream systems create new child spans linked to the export task spans via `task_trace_id` and span links.

This matches the existing pattern in `emit_task_tracking_artifacts()` in plan ingestion — task state files with trace/span IDs that downstream systems reference.

### Span Context Propagation

The `task_trace_id` (trace ID of the epic span) is written to `onboarding-metadata.json`. Downstream systems use this to:

1. Create span links back to the original task definitions
2. Query the full artifact generation plan from Tempo
3. Correlate gate results with the tasks they validate

---

## 8. Open Questions

| # | Question | Options | Default |
|---|----------|---------|---------|
| Q1 | Should story grouping be by artifact type or by target? | (a) By type: "Dashboard Artifacts", (b) By target: "checkout-api Artifacts", (c) Both levels (epic → target → type → task) | (a) By type — matches how calibration and parameter schemas are organized |
| Q2 | Should existing artifacts (status=exists) get task spans? | (a) Yes, as completed spans — shows full picture, (b) No, only gaps — cleaner trace | (a) Yes — coverage is meaningless without the denominator |
| Q3 | Should `--emit-tasks` work without a live OTLP endpoint? | (a) Require endpoint, fail if unavailable, (b) Fall back to NDJSON file export, (c) Best-effort, warn if endpoint unreachable | (c) Best-effort |
| Q4 | Should task spans carry the full `expected_output_contract` as attributes or just a reference? | (a) Full contract as span event (richer but larger), (b) Reference to onboarding-metadata.json (lighter), (c) Key fields as attributes, full as event | (c) Hybrid |
