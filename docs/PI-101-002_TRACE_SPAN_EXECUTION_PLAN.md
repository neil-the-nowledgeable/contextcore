# PI-101-002 Trace/Span Execution Plan

> **Status**: Implemented. The span model below is fully implemented in `src/contextcore/contracts/a2a/pilot.py` (21 tests). Run with `contextcore contract a2a-pilot`. See [A2A Communications Design](design/contextcore-a2a-comms-design.md) for the broader architecture.

Use ContextCore's native model (tasks as spans, subtasks as child spans) to execute file composition and assembly work with observable, testable handoffs.

---

## Why this directly addresses current pain

`PI-101-002` has absorbed significant time because failures are discovered late (often at assembly/finalization), while root causes usually originate earlier (seed quality, routing loss, stale checksums, missing mappings). Modeling design + development as a single trace with explicit child spans gives us:

- deterministic stage boundaries,
- visible handoff inputs/outputs,
- per-span acceptance criteria,
- and immediate detection of stale or incomplete context.

This aligns directly with the ContextCore approach: represent work as OTel traces/spans and derive status from real execution events.

---

## Trace Model For PI-101-002

Define one parent trace for the full feature, then execute each stage as a span with child spans for high-risk operations.

### Parent Trace

- **Trace ID / Task ID**: `PI-101-002`
- **Title**: `Fix file composition and assembly via observable handoffs`
- **Task Type**: `story`
- **Definition of done**:
  - all required artifacts are present and mapped,
  - no checksum/provenance breaks,
  - finalize status is `complete`,
  - test/review gates pass with zero critical failures.

---

## Span Breakdown (Design + Development)

| Span ID | Parent | Phase | Goal | Exit criteria |
| --- | --- | --- | --- | --- |
| `PI-101-002-S1` | `PI-101-002` | INIT_BASELINE | Establish trusted environment | `contextcore install init` completes; endpoint verified |
| `PI-101-002-S2` | `PI-101-002` | EXPORT_CONTRACT | Produce fresh contract artifacts | export succeeds; coverage threshold met; onboarding metadata present |
| `PI-101-002-S3` | `PI-101-002` | CONTRACT_INTEGRITY | Validate checksums/mappings/schema | `source_checksum` chain valid; task mapping complete; schema valid |
| `PI-101-002-S4` | `PI-101-002` | INGEST_PARSE_ASSESS | Ensure faithful translation and scoring | all gaps represented as features; score is plausible |
| `PI-101-002-S5` | `PI-101-002` | ROUTING_DECISION | Confirm correct path (Prime vs Artisan) | route justified; override documented if used |
| `PI-101-002-S6` | `PI-101-002` | ARTISAN_DESIGN | Produce design-handoff from enriched seed | design-handoff schema valid; task set complete |
| `PI-101-002-S7` | `PI-101-002` | ARTISAN_IMPLEMENT | Generate/compose artifacts | expected artifact set generated in correct paths |
| `PI-101-002-S8` | `PI-101-002` | TEST_VALIDATE | Run artifact validation gates | validation suite passes; no critical failures |
| `PI-101-002-S9` | `PI-101-002` | REVIEW_CALIBRATE | Multi-agent/human quality pass | review findings triaged; no blocking issues |
| `PI-101-002-S10` | `PI-101-002` | FINALIZE_VERIFY | Close trace with provenance proof | finalize `complete`; artifact checksums + rollup recorded |

---

## Child Spans For Known Failure Modes

Attach these under the related phase span to make root-cause location explicit.

| Child span | Under | Purpose |
| --- | --- | --- |
| `PI-101-002-S2-C1` | `S2` | Coverage check (`--min-coverage`, `--scan-existing`) |
| `PI-101-002-S3-C1` | `S3` | Artifact/task mapping completeness (`artifact_task_mapping`) |
| `PI-101-002-S3-C2` | `S3` | Checksum chain verification (`source_checksum` -> manifest checksums) |
| `PI-101-002-S4-C1` | `S4` | Gap-to-feature parity check (no dropped artifacts in PARSE/TRANSFORM) |
| `PI-101-002-S6-C1` | `S6` | `design-handoff.json` schema/version validation |
| `PI-101-002-S7-C1` | `S7` | Output path convention compliance |
| `PI-101-002-S10-C1` | `S10` | Final artifact set vs original gap set reconciliation |

---

## Required Span Attributes (minimum contract)

Use consistent attributes so queries and dashboards can detect drift automatically.

- `project.id=contextcore`
- `task.id` (span task ID, e.g., `PI-101-002-S4`)
- `task.parent_id`
- `task.phase` (INIT_BASELINE, EXPORT_CONTRACT, ...)
- `task.status` (not_started, in_progress, blocked, completed, failed)
- `input.source_checksum`
- `input.artifact_manifest_checksum`
- `input.project_context_checksum`
- `quality.coverage_percent`
- `quality.gap_count`
- `quality.feature_count`
- `routing.complexity_score`
- `routing.selected_path` (prime|artisan)
- `output.path_count`
- `output.artifact_count`
- `output.finalize_status`

For blocked spans, always set:

- `task.blocked_reason`
- `task.blocked_on_span_id` (if dependency block)
- `task.next_action`

---

## Execution Protocol (Operational)

1. Start parent trace `PI-101-002`.
2. Execute spans `S1` -> `S10` in order.
3. Do not start a downstream span until upstream exit criteria are true.
4. Emit events on every gate transition:
   - `gate.check.started`
   - `gate.check.passed`
   - `gate.check.failed`
   - `handoff.emitted`
   - `handoff.validated`
5. If any integrity child span fails (`S3-C1`, `S3-C2`, `S4-C1`), mark parent as `blocked` and stop execution.

---

## Draft Task Commands (ContextCore CLI)

Use this pattern to run `PI-101-002` as observable spans:

```bash
# Parent story
contextcore task start --id PI-101-002 --title "Fix file composition and assembly via observable handoffs" --type story

# Example phase span
contextcore task start --id PI-101-002-S1 --title "Init baseline" --type task
contextcore task update --id PI-101-002-S1 --status in_progress
contextcore task complete --id PI-101-002-S1

# Continue S2..S10 similarly, then close parent
contextcore task complete --id PI-101-002
```

If your current CLI supports parent linkage fields/options, include them so `S*` spans are explicit children of `PI-101-002`.

---

## How this prevents another PI-101-002 stall

- **Moves failure detection left**: catches stale or mismatched context at `S3/S4` instead of during finalize.
- **Separates design vs implementation risk**: `S6` must pass before `S7`.
- **Makes assembly measurable**: `output.artifact_count`, path compliance, and gap parity become queryable.
- **Improves recovery**: when blocked, one span owns the reason and next action; work no longer stalls in ambiguous "overall failed" states.

---

## Implementation

This span model is now fully implemented:

```bash
# Run the full PI-101-002 pilot trace
contextcore contract a2a-pilot

# Inject failures for testing
contextcore contract a2a-pilot --source-checksum sha256:STALE    # Blocks at S3
contextcore contract a2a-pilot --drop-feature gap-latency-panel  # Blocks at S4
contextcore contract a2a-pilot --test-failures 2                 # Blocks at S8
```

Implementation: `src/contextcore/contracts/a2a/pilot.py` with `PilotRunner`, `PilotSeed`, and `PilotResult`.

Post-pilot, the pipeline integrity checker (`a2a-check-pipeline`) and Three Questions diagnostic (`a2a-diagnose`) extend this model to validate real export output across the full 4-step pipeline.
