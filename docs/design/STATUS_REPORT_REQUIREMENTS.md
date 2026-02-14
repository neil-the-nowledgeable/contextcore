# Status Report Generation Requirements

Purpose: define the behavioral requirements for auto-generated status reports from pipeline telemetry — the "status compilation elimination" capability that replaces manual status reporting with derived reports from existing observability data.

This document is intentionally living guidance. Update it as the implementation evolves.

---

## Vision

Every pipeline execution already produces structured telemetry: gate results with evidence, artifact progress with coverage percentages, blocked spans with reasons, and agent insights with confidence scores. Yet project status is still compiled manually — someone reads dashboards, summarizes progress, and writes a status update.

Status compilation elimination removes this manual step. It queries the same telemetry the dashboards display and generates a structured status report that answers the three questions every stakeholder asks:

1. **What's done?** (completed artifacts, passed gates, closed tasks)
2. **What's in progress?** (active tasks, running pipelines, pending gates)
3. **What's blocked?** (failed gates, missing dependencies, stale artifacts)

**Core principle**: If the data exists in the observability stack, the status report should be derived from it — not manually compiled from it.

**Dogfooding**: ContextCore's own telemetry becomes its status report — "ContextCore manages ContextCore."

---

## Pipeline Placement

Status report generation is a read-only operation that runs independently of the export pipeline. It queries data produced by all pipeline steps.

```text
Pipeline steps (write):
  Export → Gate 1 → Plan Ingestion → Gate 2 → Contractor → Gate 3

Status report (read):
  Queries telemetry from all steps ──→ Generates report
```

---

## Phase (a): Status Aggregation

### Purpose

Query and aggregate pipeline telemetry into a structured status summary. This is the data collection and normalization layer.

### Data Sources

| Source | Backend | What it provides |
|--------|---------|-----------------|
| Gate results | Tempo (spans) | Pass/fail status per gate, evidence, recommendations |
| Task spans | Tempo (spans) | Task status, artifact progress, blocked tasks |
| Agent insights | Tempo (spans) | Decisions, blockers, recommendations, lessons |
| Pipeline runs | Loki (structured logs) | Pipeline execution history, duration, outcomes |
| Coverage data | Export output (JSON) | Artifact coverage percentages, gap counts |
| Metric series | Mimir (Prometheus) | Time-series for velocity, throughput, lead time |

### Functional Requirements

#### Aggregation Queries

1. **Gate result aggregation**
   - Must query Tempo for recent gate results by project and time range.
   - Must aggregate: total gates run, passed, failed, skipped; failure breakdown by gate type.
   - Must use existing `A2AQueries` query builders from `contracts/a2a/queries.py`.

2. **Task progress aggregation**
   - Must query Tempo for task spans by project and time range.
   - Must aggregate: total tasks, by status (todo, in_progress, done, blocked), by type (epic, story, task).
   - Must compute: completion percentage, velocity (tasks completed per time period).

3. **Artifact coverage aggregation**
   - Must read the most recent export output (`onboarding-metadata.json`) for coverage data.
   - Must aggregate: total required, total existing, total gaps, coverage percentage by target and by type.
   - Must compare against previous export to compute coverage delta.

4. **Blocker identification**
   - Must identify blocked tasks with reasons.
   - Must identify failed gates with `next_action` recommendations.
   - Must identify stale artifacts (last modified > threshold).
   - Must prioritize blockers by severity (critical > high > medium > low).

5. **Agent insight summary**
   - Must query recent agent insights using `InsightQuerier`.
   - Must summarize: decision count, open blockers, key recommendations.
   - Must include high-confidence insights (≥0.8) in the report summary.

#### Aggregation Output

6. **Structured status object**
   - Must produce a `StatusSummary` dataclass with typed fields for all aggregated data.
   - Must include: project_id, report_period, generated_at, pipeline_health, task_progress, coverage_status, blockers, highlights.

### Data Models

```python
@dataclass
class PipelineHealth:
    gates_run: int
    gates_passed: int
    gates_failed: int
    gates_skipped: int
    last_run: str              # ISO timestamp
    overall_status: str        # "healthy", "degraded", "unhealthy"
    failures: list[GateFailure]

@dataclass
class GateFailure:
    gate_id: str
    phase: str
    reason: str
    next_action: str
    severity: str

@dataclass
class TaskProgress:
    total: int
    by_status: dict[str, int]  # {"todo": 5, "in_progress": 3, "done": 10, ...}
    by_type: dict[str, int]    # {"epic": 1, "story": 4, "task": 13}
    completion_percent: float
    velocity: float            # Tasks completed per day (rolling 7d)
    blocked_count: int

@dataclass
class CoverageStatus:
    total_required: int
    total_existing: int
    total_gaps: int
    overall_percent: float
    by_target: dict[str, float]
    by_type: dict[str, float]
    delta_from_previous: float | None  # Change since last export

@dataclass
class Blocker:
    id: str
    source: str              # "gate", "task", "artifact", "insight"
    severity: str            # "critical", "high", "medium", "low"
    summary: str
    recommendation: str
    since: str               # ISO timestamp

@dataclass
class StatusSummary:
    project_id: str
    report_period: str       # "24h", "7d", "sprint-3"
    generated_at: str
    pipeline_health: PipelineHealth
    task_progress: TaskProgress
    coverage_status: CoverageStatus
    blockers: list[Blocker]
    highlights: list[str]    # Top 3-5 notable items
    agent_decisions: list[str]  # Recent high-confidence decisions
```

---

## Phase (b): Report Generation

### Purpose

Transform a `StatusSummary` into human-readable and machine-readable report formats.

### Functional Requirements

#### Report Formats

7. **Text report**
   - Must produce a structured text report with sections: Summary, Pipeline Health, Task Progress, Coverage, Blockers, Highlights.
   - Must use clear headers, bullet points, and status indicators (✓, ✗, ⚠).
   - Must include a one-line executive summary at the top.

8. **Markdown report**
   - Must produce a Markdown document suitable for pasting into Slack, GitHub issues, or wiki pages.
   - Must include tables for quantitative data (coverage by target, task status counts).
   - Must include a "Generated by ContextCore" footer with timestamp.

9. **JSON report**
   - Must produce a JSON representation of the full `StatusSummary` for machine consumption.
   - Must be parseable by `jq` and other JSON tools.

10. **Slack-formatted report** (optional/future)
    - Should support Slack Block Kit format for direct posting to Slack channels.

#### Report Customization

11. **Time range**
    - Must support `--period` to specify the report window: "24h", "7d", "14d", "sprint" (derives from active sprint).
    - Default: "7d".

12. **Section filtering**
    - Must support `--sections` to include only specific report sections.
    - Available sections: `pipeline`, `tasks`, `coverage`, `blockers`, `highlights`, `insights`.
    - Default: all sections.

13. **Comparison mode**
    - Should support `--compare-previous` to include delta information (coverage change, new blockers, resolved blockers).
    - Requires access to a previous report or export output for comparison.

### CLI Surface

```
contextcore status report
  --project / -p        (required)     Project ID
  --period              (default: 7d)  Report period: 24h | 7d | 14d | sprint
  --format / -f         (default: text) Output format: text | markdown | json
  --output / -o         (optional)     Write report to file
  --sections            (optional)     Comma-separated sections to include
  --compare-previous    (flag)         Include delta from previous period
  --export-dir          (optional)     Path to export output for coverage data
  --verbose / -v        (flag)         Include detailed breakdowns
```

```
contextcore status summary
  --project / -p        (required)     Project ID
  --period              (default: 24h) Report period
```

The `status summary` command is a lightweight alias that produces a one-paragraph executive summary — suitable for quick checks and agent context windows.

---

## Non-Functional Requirements

1. **Graceful degradation**: If a data source is unavailable (Tempo down, no export output), the report should include available sections and note missing data — not fail entirely.
2. **Read-only**: Must not modify any telemetry, export files, or stored data.
3. **Offline partial support**: Coverage status can be computed from local export files without Tempo/Mimir. Task progress and gate results require Tempo.
4. **Performance**: Must generate a full report in under 10 seconds (Tempo query latency is the bottleneck).
5. **Idempotency**: Same inputs and time range must produce the same report.
6. **CI-friendly**: `--format json` enables programmatic consumption. Consider `--fail-on-blockers` for CI gates that fail if critical blockers exist.

---

## Invariants

1. The report always includes `generated_at` and `project_id` — even if all data sources are unavailable.
2. Blockers are always sorted by severity (critical first).
3. Coverage percentages are mathematically consistent with the source data.
4. If `--period sprint` is used and no active sprint is found, falls back to `--period 14d` with a warning.
5. The `status summary` command produces output that fits in 500 characters (suitable for agent context).

---

## Integration with Existing Infrastructure

| Component | How it's used |
|-----------|--------------|
| `A2AQueries` (`contracts/a2a/queries.py`) | TraceQL/LogQL query builders for gate results and pipeline spans |
| `InsightQuerier` (`agent/insights.py`) | Query agent insights for the report |
| `PipelineChecker` report methods | `summary()` and `to_text()` for gate result formatting |
| `TaskTracker` (`tracker.py`) | Not used directly — reads task spans from Tempo |
| Export output files | Reads `onboarding-metadata.json` for coverage data |
| Grafana dashboard queries | Reuses query patterns from the A2A governance dashboard |

---

## Relationship to Other Commands

| Command | Relationship |
|---------|-------------|
| `status report` / `status summary` | These commands (generate reports) |
| `manifest export` | Upstream — produces coverage data this reads |
| `contract a2a-check-pipeline` | Upstream — produces gate results this aggregates |
| `contract a2a-diagnose` | Upstream — produces diagnostic results this summarizes |
| `insight list` / `insight search` | Parallel — same insight data, different presentation |
| Grafana dashboards | Parallel — same data, visual vs. text interface |

---

## Related Docs

- `src/contextcore/contracts/a2a/queries.py` — TraceQL/LogQL query builders
- `src/contextcore/agent/insights.py` — InsightQuerier for agent insight aggregation
- `src/contextcore/contracts/a2a/pipeline_checker.py` — PipelineChecker report methods
- `docs/design/contextcore-a2a-comms-design.md` — A2A architecture (Extension 5)
- `docs/design/AGENT_INSIGHTS_CLI_REQUIREMENTS.md` — Related: insight querying commands
