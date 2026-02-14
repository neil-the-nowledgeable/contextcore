# Project Plan: Task Tracking Emission During Export

**Date:** 2026-02-14
**Status:** Draft — for review and refinement
**Requirements:** [EXPORT_TASK_TRACKING_REQUIREMENTS.md](./EXPORT_TASK_TRACKING_REQUIREMENTS.md)
**Estimated Effort:** 5–7 development days across 4 phases

---

## Executive Summary

During `contextcore manifest export`, the system already computes a detailed description of every artifact that needs to be designed, developed, and tested — including dependency ordering, expected output contracts, derivation rules, and resolved parameters. This plan adds an opt-in `--emit-tasks` flag that simultaneously creates OTel task spans for each artifact, producing a single trace that represents the full work plan **before execution begins**.

This closes the loop between "declaring what needs to be built" (export) and "tracking the work" (TaskTracker) — using ContextCore's own infrastructure to eat its own dog food.

### Why This Matters

| Today | With `--emit-tasks` |
|-------|---------------------|
| Export writes static JSON files | Export also emits a queryable trace in Tempo |
| Plan ingestion and artisan create their own independent tracking | Downstream systems link back to the canonical task definitions |
| "What needs to be built?" requires reading JSON files | `{ span.task.type = "epic" && span.project.id = "X" }` in TraceQL |
| No pre-execution visibility into work scope | Full artifact generation plan visible as a trace before any work starts |
| Gate results (GateResult) float as standalone checks | Gate results attach as events to the task spans they validate |

---

## Architecture Overview

### Where This Fits in the Pipeline

```text
Step 2 (Export) — extended with opt-in task emission
┌──────────────────────────────────────────────────────────────────┐
│ contextcore manifest export --emit-tasks                        │
│                                                                  │
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │ Existing behavior   │    │ New: TaskEmitter     │             │
│  │ (unchanged)         │    │ (opt-in only)        │             │
│  │                     │    │                      │             │
│  │ 1. CRD YAML         │    │ 1. Epic span         │             │
│  │ 2. Artifact Manifest │    │ 2. Story spans       │             │
│  │ 3. Provenance JSON   │    │ 3. Task spans        │             │
│  │ 4. Onboarding Meta   │    │ 4. Events + Links    │             │
│  │    (+ task_trace_id) │◀───│ 5. task_trace_id     │             │
│  └─────────────────────┘    └─────────────────────┘             │
└──────────────────────────────────────────────────────────────────┘
```

### New Module: `ExportTaskEmitter`

A thin orchestration layer that wraps `TaskTracker` to emit a hierarchical trace from export data:

```text
src/contextcore/
├── export_tasks.py          # NEW — ExportTaskEmitter
├── tracker.py               # EXISTING — TaskTracker (used, not modified)
├── cli/
│   └── manifest.py          # MODIFIED — add --emit-tasks flag
└── utils/
    └── onboarding.py        # MODIFIED — add task_trace_id field
```

### Span Hierarchy

```text
Trace: export-{project_id}-{timestamp}
│
├── [epic] {project_id} Observability Artifact Generation
│   ├── attr: coverage.total_gaps=10, coverage.percent=42.8
│   │
│   ├── [story] Dashboard Artifacts (gap_count=2)
│   │   ├── [task] checkout_api-dashboard          (status=needed, depends_on=[checkout_api-prometheus-rules])
│   │   │   ├── event: task.created
│   │   │   ├── event: task.contract {derivation_rules: [...], expected_output: {...}}
│   │   │   └── link → checkout_api-prometheus-rules task span
│   │   └── [task] payment_svc-dashboard           (status=needed)
│   │       └── event: task.created
│   │
│   ├── [story] PrometheusRule Artifacts (gap_count=2)
│   │   ├── [task] checkout_api-prometheus-rules    (status=needed)
│   │   └── [task] payment_svc-prometheus-rules     (status=needed)
│   │
│   └── [story] ServiceMonitor Artifacts (gap_count=2, status=exists)
│       ├── [task] checkout_api-service-monitor     (status=exists, span.status=OK)
│       └── [task] payment_svc-service-monitor      (status=exists, span.status=OK)
│
└── onboarding-metadata.json receives task_trace_id for downstream correlation
```

---

## Phase Breakdown

### Phase 1: Core Emission Module (2–3 days)

**Goal:** Build `ExportTaskEmitter` and emit the epic → story → task hierarchy.

#### 1.1 Create `src/contextcore/export_tasks.py`

New module containing the `ExportTaskEmitter` class.

**Inputs it consumes (all already computed during export):**

| Input | Source | What It Provides |
|-------|--------|-----------------|
| `artifact_manifest` | `manifest.generate_artifact_manifest()` | Full list of artifacts with types, parameters, derivation rules, dependencies |
| `onboarding_metadata` | `build_onboarding_metadata()` | Coverage gaps, artifact dependency graph, expected output contracts, resolved parameters |
| `project_id` | `manifest.spec.project.id` or CLI `--project-id` | Task hierarchy root |

**Class API:**

```python
class ExportTaskEmitter:
    """Emit task tracking spans from export data."""

    def __init__(
        self,
        project_id: str,
        endpoint: Optional[str] = None,  # defaults to OTEL_EXPORTER_OTLP_ENDPOINT
        dry_run: bool = False,
    ):
        """Initialize with a TaskTracker instance."""

    def emit_from_export(
        self,
        artifact_manifest: ArtifactManifest,
        onboarding_metadata: dict,
    ) -> ExportTaskEmissionResult:
        """
        Emit the full task hierarchy from export data.

        Returns ExportTaskEmissionResult with:
          - trace_id: str (the epic span's trace ID for downstream correlation)
          - epic_span_id: str
          - story_count: int
          - task_count: int
          - tasks_needed: int
          - tasks_existing: int
          - dry_run_preview: Optional[dict] (if dry_run=True)
        """

    def _emit_epic(self, project_id, coverage_data) -> SpanContext:
        """Create the root epic span."""

    def _emit_stories(self, epic_context, artifacts_by_type) -> Dict[str, SpanContext]:
        """Create one story span per artifact type with gaps."""

    def _emit_tasks(self, story_contexts, artifacts, onboarding_metadata) -> List[SpanContext]:
        """Create task spans for each artifact, attach events and links."""
```

**Key design decisions:**

- Uses `TaskTracker.start_task()` and `TaskTracker.complete_task()` for each span
- Task spans for **needed** artifacts are started and immediately ended with status `UNSET` (open work item)
- Task spans for **existing** artifacts are started and ended with status `OK` (completed)
- Span events carry the contract data (derivation rules, expected output contracts)
- Span links connect dependent tasks (from `artifact_dependency_graph`)
- The `TaskTracker` is instantiated with a dedicated service name: `contextcore-export-tasks`

#### 1.2 Add `--emit-tasks` Flag to CLI

Modify `src/contextcore/cli/manifest.py`:

```python
@click.option(
    "--emit-tasks",
    is_flag=True,
    help="Emit OTel task tracking spans for each artifact (opt-in). "
         "Requires OTEL_EXPORTER_OTLP_ENDPOINT or --endpoint.",
)
@click.option(
    "--project-id",
    default=None,
    help="Override project ID for task tracking (defaults to manifest spec.project.id).",
)
```

Integration point in the `export()` function — **after** all 4 files are computed but **before** they are written, so the `task_trace_id` can be injected into `onboarding-metadata.json`:

```python
# After computing all export data...
if emit_tasks:
    emitter = ExportTaskEmitter(
        project_id=project_id or manifest.spec.project.id,
        dry_run=dry_run,
    )
    result = emitter.emit_from_export(artifact_manifest, onboarding_metadata)
    onboarding_metadata["task_trace_id"] = result.trace_id
    onboarding_metadata["task_emission_timestamp"] = result.timestamp
    click.echo(f"  ✓ Emitted {result.task_count} task spans (trace: {result.trace_id[:16]}...)")
```

#### 1.3 Add `task_trace_id` to Onboarding Metadata

Modify `src/contextcore/utils/onboarding.py` `build_onboarding_metadata()` to accept and include the optional `task_trace_id` field:

```python
# At end of build_onboarding_metadata()
if task_trace_id:
    result["task_trace_id"] = task_trace_id
    result["task_emission_timestamp"] = task_emission_timestamp
```

**Deliverables:**
- [ ] `src/contextcore/export_tasks.py` — `ExportTaskEmitter` class
- [ ] `ExportTaskEmissionResult` dataclass
- [ ] CLI `--emit-tasks` and `--project-id` flags
- [ ] `task_trace_id` field in onboarding metadata

---

### Phase 2: Contract Integration and Span Events (1–2 days)

**Goal:** Attach A2A contract data (derivation rules, expected output contracts, ArtifactIntent) to task spans as structured events.

#### 2.1 Span Events from Export Data

Each task span gets structured events carrying the contract information:

| Event Name | Attributes | Source |
|------------|-----------|--------|
| `task.created` | `source`, `artifact_type`, `target`, `priority` | Artifact manifest |
| `task.contract` | `derivation_rules` (JSON), `expected_output_contract` (JSON) | Onboarding metadata enrichments |
| `task.dependencies` | `depends_on` (list), `dependency_count` | Artifact dependency graph |
| `artifact.intent` | `artifact_id`, `intent` (create/validate), `parameter_sources` | ArtifactIntent contract model |

These use the existing `TaskTracker` event mechanism (`add_event()` on the span).

#### 2.2 Span Links for Dependencies

For each artifact with `depends_on` in the dependency graph, create OTel span links to the dependency task spans:

```python
# During _emit_tasks(), after all task spans are created:
for artifact_id, deps in dependency_graph.items():
    task_span = task_spans[artifact_id]
    for dep_id in deps:
        if dep_id in task_span_contexts:
            # Add link from this task to its dependency
            task_span.add_link(task_span_contexts[dep_id])
```

**Note:** OTel span links must be set at span creation time. The implementation creates tasks in dependency order (leaves first) so that link targets exist before dependents are created.

#### 2.3 ArtifactIntent Event Emission

For each needed artifact, emit an `ArtifactIntent` event using the existing A2A contract model:

```python
from contextcore.contracts.a2a.models import ArtifactIntentAction

intent_attrs = {
    "artifact.intent.action": ArtifactIntentAction.CREATE.value,
    "artifact.intent.artifact_type": artifact.type,
    "artifact.intent.parameter_sources": json.dumps(parameter_sources),
}
span.add_event("artifact.intent", attributes=intent_attrs)
```

**Deliverables:**
- [ ] `task.created`, `task.contract`, `task.dependencies` events on each span
- [ ] `artifact.intent` events using A2A contract schema
- [ ] Span links for dependency relationships
- [ ] Dependency-ordered emission (topological sort)

---

### Phase 3: Dry Run and Resilience (1 day)

**Goal:** Make `--emit-tasks` safe with dry-run preview, best-effort emission, and clear error messages.

#### 3.1 Dry Run Support

When `--emit-tasks` is used with `--dry-run`, instead of emitting spans, produce a JSON preview:

```json
{
  "dry_run": true,
  "would_emit": {
    "epic": {
      "task_id": "my-project-artifact-generation",
      "type": "epic",
      "coverage_percent": 42.8
    },
    "stories": [
      { "task_id": "my-project-dashboard-artifacts", "type": "story", "gap_count": 2 }
    ],
    "tasks": [
      {
        "task_id": "checkout_api-dashboard",
        "type": "task",
        "artifact_type": "dashboard",
        "status": "needed",
        "depends_on": ["checkout_api-prometheus-rules"],
        "expected_output": { "depth": "comprehensive", "max_lines": 500 }
      }
    ],
    "totals": { "spans": 15, "stories": 4, "tasks_needed": 10, "tasks_existing": 4 }
  }
}
```

This is written to `{output_dir}/task-emission-preview.json`.

#### 3.2 Best-Effort Emission

Task emission must not block or fail the export:

```python
try:
    result = emitter.emit_from_export(artifact_manifest, onboarding_metadata)
    onboarding_metadata["task_trace_id"] = result.trace_id
except Exception as e:
    click.echo(f"  ⚠ Task emission failed (export continues): {e}", err=True)
    # Export succeeds without task_trace_id
```

#### 3.3 Endpoint Validation

Before attempting emission, check if the OTLP endpoint is reachable (reuse `TaskTracker._check_endpoint_available()`):

```python
if not emitter.check_endpoint():
    click.echo("  ⚠ OTLP endpoint not reachable, skipping task emission", err=True)
    click.echo(f"    Set OTEL_EXPORTER_OTLP_ENDPOINT or use --endpoint", err=True)
```

**Deliverables:**
- [ ] Dry-run preview JSON output
- [ ] Best-effort error handling (export never fails due to task emission)
- [ ] Endpoint availability check with clear messaging

---

### Phase 4: Testing and Documentation (1–2 days)

**Goal:** Full test coverage and documentation updates.

#### 4.1 Unit Tests

New test file: `tests/test_export_tasks.py`

| Test | What It Validates |
|------|-------------------|
| `test_emit_epic_span` | Epic span created with correct project ID, coverage attributes |
| `test_emit_story_spans_per_type` | One story per artifact type with gaps, correct gap_count |
| `test_emit_task_spans_for_gaps` | Task spans for each coverage gap with artifact attributes |
| `test_emit_existing_artifacts_as_completed` | Existing artifacts get OK status spans |
| `test_task_span_events` | task.created, task.contract, task.dependencies events present |
| `test_task_span_links` | Span links for dependency relationships |
| `test_artifact_intent_events` | ArtifactIntent events with correct action |
| `test_dependency_ordered_emission` | Tasks emitted in topological order |
| `test_trace_id_in_onboarding_metadata` | task_trace_id written to onboarding-metadata.json |
| `test_dry_run_preview` | JSON preview written, no spans emitted |
| `test_emission_failure_does_not_fail_export` | Export completes even if emission throws |
| `test_endpoint_unreachable_graceful` | Warning message, export continues |
| `test_no_emit_without_flag` | Default behavior unchanged |
| `test_project_id_override` | --project-id overrides manifest value |
| `test_empty_coverage_gaps` | No task spans when all artifacts exist |

All tests use `InMemorySpanExporter` to capture and validate emitted spans without a live backend.

#### 4.2 Integration with Existing Test Suite

Update `tests/test_manifest_v2.py` to verify that `task_trace_id` appears in onboarding metadata when task emission is configured.

#### 4.3 Documentation Updates

| Document | Update |
|----------|--------|
| `CLAUDE.md` | Add `--emit-tasks` to CLI quick reference |
| `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` | Add section on task emission as optional Step 2 enhancement |
| `docs/design/contextcore-a2a-comms-design.md` | Reference task emission as the bridge between export and A2A governance |
| `docs/semantic-conventions.md` | Add task emission span attributes |
| `README.md` | Mention `--emit-tasks` in CLI usage section |

**Deliverables:**
- [ ] `tests/test_export_tasks.py` with 15+ tests
- [ ] Updated integration tests
- [ ] Documentation updates (5 files)

---

## Implementation Sequence

```text
Week 1
  Day 1-2:  Phase 1 — ExportTaskEmitter, CLI flag, onboarding metadata field
  Day 3:    Phase 2 — Contract events, span links, dependency ordering
  Day 4:    Phase 3 — Dry run, resilience, endpoint validation

Week 2
  Day 5-6:  Phase 4 — Tests, documentation, integration validation
  Day 7:    Buffer / review / refinement
```

---

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| OTel span links must be set at creation time, not after | High | Requires dependency-ordered emission | Use topological sort on dependency graph before emitting task spans |
| Large artifact count (>100 gaps) produces many spans | Medium | OTLP batch exporter could timeout | Batch spans using `BatchSpanProcessor` with tuned batch size; add span count warning at >50 |
| `TaskTracker` not designed for emit-then-close pattern | Medium | May need refactoring | `start_task()` + immediate `complete_task()` already works; verify with unit test |
| Downstream systems (plan ingestion, artisan) don't use `task_trace_id` yet | Low | No impact on this scope | Downstream consumption is a follow-up; correlation ID is available when they're ready |
| Span attribute limits exceeded by large expected_output_contracts | Medium | OTel truncates oversized attributes | Use events (not attributes) for large payloads; respect `get_span_limits()` |

---

## Success Criteria

| Criterion | How to Verify |
|-----------|---------------|
| `contextcore manifest export --emit-tasks` produces a trace in Tempo | Query: `{ span.task.type = "epic" && resource.service.name = "contextcore-export-tasks" }` |
| Trace shows epic → story → task hierarchy | Visual verification in Tempo trace view |
| Each task span has derivation rules and expected output contract | Inspect span events in Tempo |
| Dependency links visible in trace | Click through span links in Tempo UI |
| `task_trace_id` in onboarding-metadata.json | `jq .task_trace_id onboarding-metadata.json` |
| Default behavior unchanged | Run `export` without `--emit-tasks`, verify identical output |
| 15+ unit tests pass | `python3 -m pytest tests/test_export_tasks.py -v` |
| Dry run produces preview JSON | `export --emit-tasks --dry-run` writes `task-emission-preview.json` |

---

## Future Work (Out of Scope)

These are natural follow-ups but explicitly **not** part of this plan:

| Enhancement | Description | Prerequisite |
|-------------|-------------|--------------|
| **Downstream span resumption** | Plan ingestion and artisan update task span status via `task_trace_id` | This plan (task_trace_id available) |
| **Gate result attachment** | GateResult events attached to the task span they validate | This plan + downstream correlation |
| **Progress dashboard panel** | Grafana panel showing artifact generation progress from task spans | This plan (spans in Tempo) |
| **`contextcore task list --from-export`** | CLI to query and display exported task hierarchy from Tempo | This plan (spans queryable) |
| **Init-phase task emission** | `contextcore install init` also emits installation verification tasks as spans | This plan as pattern validation |
| **Default behavior** | Make `--emit-tasks` the default if OTLP endpoint is available | Adoption and stability of this feature |
| **Multi-export deduplication** | Detect and link repeated exports for the same project (not duplicate traces) | UUID or version-based dedup logic |

---

## Appendix A: How This Connects to A2A Governance

The A2A comms design defines four contract types. Task emission creates a bridge between export and governance:

| Contract Type | How Task Emission Uses It |
|---------------|--------------------------|
| **TaskSpanContract** | Each emitted task span conforms to TaskSpanContract schema (project_id, task_id, phase=EXPORT_CONTRACT, status, checksums) |
| **ArtifactIntent** | Each needed artifact gets an ArtifactIntent event (intent=create, artifact_type, parameter_sources) |
| **HandoffContract** | Not used at emission time — consumed when plan ingestion accepts the task_trace_id |
| **GateResult** | Not emitted at export time — attached by pipeline_checker and three_questions when validating the export |

The `Phase.EXPORT_CONTRACT` enum value already exists and is the correct phase for task emission spans.

---

## Appendix B: TraceQL Queries for Exported Tasks

Once task emission is live, these queries become available:

```
# All exported task hierarchies for a project
{ span.project.id = "checkout-api" && span.task.type = "epic" && resource.service.name = "contextcore-export-tasks" }

# All needed artifacts (coverage gaps)
{ span.project.id = "checkout-api" && span.task.type = "task" && span.task.status = "todo" }

# All dashboard artifacts
{ span.project.id = "checkout-api" && span.artifact.type = "dashboard" }

# Tasks with dependencies
{ span.project.id = "checkout-api" && span.artifact.depends_on != "" }

# Coverage summary (count by status)
{ span.project.id = "checkout-api" && span.task.type = "task" } | count() by (span.task.status)
```
