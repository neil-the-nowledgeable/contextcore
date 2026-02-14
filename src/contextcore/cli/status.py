"""
ContextCore CLI — Status report generation (status compilation elimination).

Auto-generates project status reports from pipeline telemetry: gate results,
task progress, artifact coverage, blockers, and agent insights.

Phase (a): Aggregation — query and normalize data from Tempo, Loki, export files.
Phase (b): Generation — produce text, markdown, or JSON reports.

Usage::

    contextcore status report -p my-project
    contextcore status report -p my-project --format markdown --output status.md
    contextcore status summary -p my-project

See ``docs/design/STATUS_REPORT_REQUIREMENTS.md`` for full requirements.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models (Phase a: Aggregation)
# ---------------------------------------------------------------------------

@dataclass
class GateFailure:
    gate_id: str
    phase: str
    reason: str
    next_action: str
    severity: str


@dataclass
class PipelineHealth:
    gates_run: int = 0
    gates_passed: int = 0
    gates_failed: int = 0
    gates_skipped: int = 0
    last_run: str = ""
    overall_status: str = "unknown"  # healthy, degraded, unhealthy
    failures: List[GateFailure] = field(default_factory=list)


@dataclass
class TaskProgress:
    total: int = 0
    by_status: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)
    completion_percent: float = 0.0
    velocity: float = 0.0  # tasks/day rolling 7d
    blocked_count: int = 0


@dataclass
class CoverageStatus:
    total_required: int = 0
    total_existing: int = 0
    total_gaps: int = 0
    overall_percent: float = 0.0
    by_target: Dict[str, float] = field(default_factory=dict)
    by_type: Dict[str, float] = field(default_factory=dict)
    delta_from_previous: Optional[float] = None


@dataclass
class Blocker:
    id: str
    source: str  # gate, task, artifact, insight
    severity: str  # critical, high, medium, low
    summary: str
    recommendation: str
    since: str = ""


@dataclass
class StatusSummary:
    project_id: str = ""
    report_period: str = "7d"
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    pipeline_health: PipelineHealth = field(default_factory=PipelineHealth)
    task_progress: TaskProgress = field(default_factory=TaskProgress)
    coverage_status: CoverageStatus = field(default_factory=CoverageStatus)
    blockers: List[Blocker] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)
    agent_decisions: List[str] = field(default_factory=list)
    data_sources_available: List[str] = field(default_factory=list)
    data_sources_unavailable: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase (a): Aggregators
# ---------------------------------------------------------------------------

def _aggregate_coverage(export_dir: Optional[str]) -> CoverageStatus:
    """Aggregate coverage from the most recent export output."""
    status = CoverageStatus()

    if not export_dir:
        return status

    onboarding_path = Path(export_dir) / "onboarding-metadata.json"
    if not onboarding_path.exists():
        return status

    try:
        with open(onboarding_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        coverage = data.get("coverage", {})
        if isinstance(coverage, dict):
            status.total_required = coverage.get("totalRequired", 0)
            status.total_existing = coverage.get("totalExisting", 0)
            status.total_gaps = status.total_required - status.total_existing
            status.overall_percent = coverage.get("overallCoverage", 0.0)

            by_target = coverage.get("byTarget", {})
            if isinstance(by_target, dict):
                status.by_target = {
                    k: v.get("coverage", 0.0) if isinstance(v, dict) else float(v)
                    for k, v in by_target.items()
                }

            by_type = coverage.get("byType", {})
            if isinstance(by_type, dict):
                status.by_type = {
                    k: v.get("coverage", 0.0) if isinstance(v, dict) else float(v)
                    for k, v in by_type.items()
                }
    except (json.JSONDecodeError, OSError, KeyError) as e:
        logger.warning(f"Coverage aggregation error: {e}")

    return status


def _aggregate_pipeline_health(export_dir: Optional[str]) -> PipelineHealth:
    """Aggregate pipeline health from gate results."""
    health = PipelineHealth()

    if not export_dir:
        return health

    # Try to run the pipeline checker on the export output
    try:
        from contextcore.contracts.a2a.pipeline_checker import PipelineChecker

        checker = PipelineChecker(export_dir)
        report = checker.run()

        health.gates_run = report.total_gates
        health.gates_passed = report.passed
        health.gates_failed = report.failed
        health.gates_skipped = len(report.skipped)
        health.last_run = report.checked_at
        health.overall_status = "healthy" if report.is_healthy else "unhealthy"

        for gate in report.gates:
            if gate.result.value == "fail":
                health.failures.append(
                    GateFailure(
                        gate_id=gate.gate_id,
                        phase=gate.phase.value,
                        reason=gate.reason or "",
                        next_action=gate.next_action or "",
                        severity=gate.severity.value if hasattr(gate.severity, "value") else str(gate.severity),
                    )
                )
    except Exception as e:
        logger.warning(f"Pipeline health aggregation error: {e}")
        health.overall_status = "unknown"

    return health


def _aggregate_insights(
    project_id: str,
    time_range: str,
    tempo_url: Optional[str] = None,
    local_storage: Optional[str] = None,
) -> List[str]:
    """Aggregate recent high-confidence agent decisions."""
    decisions: List[str] = []
    try:
        from contextcore.agent import InsightQuerier

        querier = InsightQuerier(
            tempo_url=tempo_url or "http://localhost:3200",
            local_storage_path=local_storage,
        )
        insights = querier.query(
            project_id=project_id,
            insight_type="decision",
            min_confidence=0.8,
            time_range=time_range,
            limit=5,
        )
        decisions = [i.summary for i in insights]
    except Exception as e:
        logger.debug(f"Insight aggregation skipped: {e}")

    return decisions


def _identify_blockers(
    health: PipelineHealth,
    coverage: CoverageStatus,
) -> List[Blocker]:
    """Identify blockers from gate failures and coverage gaps."""
    blockers: List[Blocker] = []

    # Gate failures as blockers
    for failure in health.failures:
        blockers.append(
            Blocker(
                id=f"gate-{failure.gate_id}",
                source="gate",
                severity="critical" if failure.severity in ("critical", "error") else "high",
                summary=f"Gate {failure.gate_id} failed: {failure.reason}",
                recommendation=failure.next_action,
                since=health.last_run,
            )
        )

    # Coverage gaps as blockers (if coverage is below 50%)
    if coverage.total_required > 0 and coverage.overall_percent < 50.0:
        blockers.append(
            Blocker(
                id="coverage-low",
                source="artifact",
                severity="high",
                summary=f"Coverage is {coverage.overall_percent:.0f}% ({coverage.total_gaps} gaps of {coverage.total_required} required)",
                recommendation="Run contextcore manifest export and review coverage gaps.",
            )
        )

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    blockers.sort(key=lambda b: severity_order.get(b.severity, 4))

    return blockers


def _generate_highlights(summary: StatusSummary) -> List[str]:
    """Generate top highlights from aggregated data."""
    highlights: List[str] = []

    # Pipeline health
    h = summary.pipeline_health
    if h.gates_run > 0:
        highlights.append(
            f"Pipeline: {h.gates_passed}/{h.gates_run} gates passed ({h.overall_status})"
        )

    # Coverage
    c = summary.coverage_status
    if c.total_required > 0:
        highlights.append(
            f"Coverage: {c.overall_percent:.0f}% ({c.total_existing}/{c.total_required} artifacts)"
        )

    # Blockers
    if summary.blockers:
        crit = sum(1 for b in summary.blockers if b.severity == "critical")
        if crit > 0:
            highlights.append(f"Blockers: {crit} critical, {len(summary.blockers)} total")
        else:
            highlights.append(f"Blockers: {len(summary.blockers)} (none critical)")

    # Decisions
    if summary.agent_decisions:
        highlights.append(f"Agent decisions: {len(summary.agent_decisions)} recent high-confidence")

    return highlights


def build_status_summary(
    project_id: str,
    period: str = "7d",
    export_dir: Optional[str] = None,
    tempo_url: Optional[str] = None,
    local_storage: Optional[str] = None,
) -> StatusSummary:
    """Build a complete status summary from all available data sources."""
    summary = StatusSummary(project_id=project_id, report_period=period)

    # Coverage (from export files — offline)
    coverage = _aggregate_coverage(export_dir)
    summary.coverage_status = coverage
    if export_dir and Path(export_dir).exists():
        summary.data_sources_available.append("export_output")
    else:
        summary.data_sources_unavailable.append("export_output")

    # Pipeline health (from pipeline checker — offline)
    health = _aggregate_pipeline_health(export_dir)
    summary.pipeline_health = health
    if health.gates_run > 0:
        summary.data_sources_available.append("pipeline_checker")
    else:
        summary.data_sources_unavailable.append("pipeline_checker")

    # Agent insights
    decisions = _aggregate_insights(project_id, period, tempo_url, local_storage)
    summary.agent_decisions = decisions
    if decisions:
        summary.data_sources_available.append("agent_insights")

    # Blockers
    summary.blockers = _identify_blockers(health, coverage)

    # Highlights
    summary.highlights = _generate_highlights(summary)

    return summary


# ---------------------------------------------------------------------------
# Phase (b): Report generation
# ---------------------------------------------------------------------------

def render_text_report(summary: StatusSummary) -> str:
    """Render status summary as human-readable text."""
    lines: List[str] = []

    # Executive summary
    lines.append(f"Status Report: {summary.project_id}")
    lines.append(f"Period: {summary.report_period}  Generated: {summary.generated_at[:19]}")
    lines.append("=" * 60)

    # Highlights
    if summary.highlights:
        lines.append("")
        lines.append("Highlights:")
        for h in summary.highlights:
            lines.append(f"  - {h}")

    # Pipeline Health
    h = summary.pipeline_health
    if h.gates_run > 0:
        lines.append("")
        lines.append(f"Pipeline Health: {h.overall_status.upper()}")
        lines.append(f"  Gates: {h.gates_passed}/{h.gates_run} passed, {h.gates_failed} failed, {h.gates_skipped} skipped")
        if h.failures:
            lines.append("  Failures:")
            for f in h.failures:
                lines.append(f"    [{f.severity}] {f.gate_id}: {f.reason}")
                if f.next_action:
                    lines.append(f"      -> {f.next_action}")

    # Coverage
    c = summary.coverage_status
    if c.total_required > 0:
        lines.append("")
        lines.append(f"Artifact Coverage: {c.overall_percent:.0f}%")
        lines.append(f"  Required: {c.total_required}  Existing: {c.total_existing}  Gaps: {c.total_gaps}")
        if c.by_target:
            lines.append("  By target:")
            for t, pct in sorted(c.by_target.items()):
                lines.append(f"    {t}: {pct:.0f}%")

    # Blockers
    if summary.blockers:
        lines.append("")
        lines.append(f"Blockers ({len(summary.blockers)}):")
        for b in summary.blockers:
            icon = "!" if b.severity == "critical" else "*"
            lines.append(f"  {icon} [{b.severity}] {b.summary}")
            if b.recommendation:
                lines.append(f"    Fix: {b.recommendation}")

    # Agent decisions
    if summary.agent_decisions:
        lines.append("")
        lines.append("Recent Agent Decisions:")
        for d in summary.agent_decisions:
            lines.append(f"  - {d}")

    # Data sources
    if summary.data_sources_unavailable:
        lines.append("")
        lines.append(f"Note: some data sources unavailable: {', '.join(summary.data_sources_unavailable)}")

    lines.append("")
    lines.append("Generated by ContextCore")
    return "\n".join(lines)


def render_markdown_report(summary: StatusSummary) -> str:
    """Render status summary as Markdown."""
    lines: List[str] = []

    lines.append(f"# Status Report: {summary.project_id}")
    lines.append(f"")
    lines.append(f"**Period**: {summary.report_period} | **Generated**: {summary.generated_at[:19]}")
    lines.append("")

    # Highlights
    if summary.highlights:
        lines.append("## Highlights")
        lines.append("")
        for h in summary.highlights:
            lines.append(f"- {h}")
        lines.append("")

    # Pipeline Health
    h = summary.pipeline_health
    if h.gates_run > 0:
        status_icon = "✓" if h.overall_status == "healthy" else "✗"
        lines.append(f"## Pipeline Health: {status_icon} {h.overall_status.upper()}")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"| ------ | ----- |")
        lines.append(f"| Gates run | {h.gates_run} |")
        lines.append(f"| Passed | {h.gates_passed} |")
        lines.append(f"| Failed | {h.gates_failed} |")
        lines.append(f"| Skipped | {h.gates_skipped} |")
        lines.append("")

        if h.failures:
            lines.append("### Gate Failures")
            lines.append("")
            lines.append("| Gate | Phase | Severity | Reason |")
            lines.append("| ---- | ----- | -------- | ------ |")
            for f in h.failures:
                lines.append(f"| {f.gate_id} | {f.phase} | {f.severity} | {f.reason} |")
            lines.append("")

    # Coverage
    c = summary.coverage_status
    if c.total_required > 0:
        lines.append(f"## Artifact Coverage: {c.overall_percent:.0f}%")
        lines.append("")
        lines.append(f"- **Required**: {c.total_required}")
        lines.append(f"- **Existing**: {c.total_existing}")
        lines.append(f"- **Gaps**: {c.total_gaps}")
        lines.append("")

        if c.by_target:
            lines.append("### Coverage by Target")
            lines.append("")
            lines.append("| Target | Coverage |")
            lines.append("| ------ | -------- |")
            for t, pct in sorted(c.by_target.items()):
                lines.append(f"| {t} | {pct:.0f}% |")
            lines.append("")

    # Blockers
    if summary.blockers:
        lines.append(f"## Blockers ({len(summary.blockers)})")
        lines.append("")
        for b in summary.blockers:
            icon = "🔴" if b.severity == "critical" else "🟡"
            lines.append(f"- {icon} **[{b.severity}]** {b.summary}")
            if b.recommendation:
                lines.append(f"  - Fix: {b.recommendation}")
        lines.append("")

    # Agent decisions
    if summary.agent_decisions:
        lines.append("## Recent Agent Decisions")
        lines.append("")
        for d in summary.agent_decisions:
            lines.append(f"- {d}")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated by ContextCore at {summary.generated_at[:19]}*")
    return "\n".join(lines)


def render_json_report(summary: StatusSummary) -> str:
    """Render status summary as JSON."""
    data = {
        "project_id": summary.project_id,
        "report_period": summary.report_period,
        "generated_at": summary.generated_at,
        "pipeline_health": {
            "gates_run": summary.pipeline_health.gates_run,
            "gates_passed": summary.pipeline_health.gates_passed,
            "gates_failed": summary.pipeline_health.gates_failed,
            "gates_skipped": summary.pipeline_health.gates_skipped,
            "overall_status": summary.pipeline_health.overall_status,
            "failures": [
                {
                    "gate_id": f.gate_id,
                    "phase": f.phase,
                    "reason": f.reason,
                    "next_action": f.next_action,
                    "severity": f.severity,
                }
                for f in summary.pipeline_health.failures
            ],
        },
        "coverage_status": {
            "total_required": summary.coverage_status.total_required,
            "total_existing": summary.coverage_status.total_existing,
            "total_gaps": summary.coverage_status.total_gaps,
            "overall_percent": summary.coverage_status.overall_percent,
            "by_target": summary.coverage_status.by_target,
            "by_type": summary.coverage_status.by_type,
        },
        "blockers": [
            {
                "id": b.id,
                "source": b.source,
                "severity": b.severity,
                "summary": b.summary,
                "recommendation": b.recommendation,
            }
            for b in summary.blockers
        ],
        "highlights": summary.highlights,
        "agent_decisions": summary.agent_decisions,
        "data_sources": {
            "available": summary.data_sources_available,
            "unavailable": summary.data_sources_unavailable,
        },
    }
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
def status():
    """Auto-generated status reports from pipeline telemetry."""
    pass


@status.command("report")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", required=True, help="Project ID")
@click.option("--period", default="7d", help="Report period: 24h, 7d, 14d")
@click.option("--format", "-f", "output_format", type=click.Choice(["text", "markdown", "json"]), default="text")
@click.option("--output", "-o", type=click.Path(), help="Write report to file")
@click.option("--export-dir", type=click.Path(exists=True), help="Export output dir for coverage data")
@click.option("--tempo-url", envvar="TEMPO_URL", default=None, help="Tempo URL")
@click.option("--local-storage", envvar="CONTEXTCORE_LOCAL_STORAGE", help="Local insight storage path")
@click.option("--verbose", "-v", is_flag=True, help="Include detailed breakdowns")
def status_report(
    project: str,
    period: str,
    output_format: str,
    output: Optional[str],
    export_dir: Optional[str],
    tempo_url: Optional[str],
    local_storage: Optional[str],
    verbose: bool,
):
    """Generate a full status report from pipeline telemetry.

    Aggregates gate results, artifact coverage, blockers, and agent insights
    into a structured report. Replaces manual status compilation.

    Examples:
        contextcore status report -p my-project
        contextcore status report -p my-project --format markdown -o status.md
        contextcore status report -p my-project --export-dir ./out/export --format json
    """
    summary = build_status_summary(
        project_id=project,
        period=period,
        export_dir=export_dir,
        tempo_url=tempo_url,
        local_storage=local_storage,
    )

    if output_format == "markdown":
        report_text = render_markdown_report(summary)
    elif output_format == "json":
        report_text = render_json_report(summary)
    else:
        report_text = render_text_report(summary)

    if output:
        Path(output).write_text(report_text, encoding="utf-8")
        click.echo(f"✓ Status report written to {output}")
    else:
        click.echo(report_text)


@status.command("summary")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", required=True, help="Project ID")
@click.option("--period", default="24h", help="Report period")
@click.option("--export-dir", type=click.Path(exists=True), help="Export output dir")
def status_summary_cmd(
    project: str,
    period: str,
    export_dir: Optional[str],
):
    """Quick one-paragraph executive summary.

    Suitable for agent context windows and quick terminal checks.

    Example:
        contextcore status summary -p my-project
    """
    summary = build_status_summary(
        project_id=project,
        period=period,
        export_dir=export_dir,
    )

    # Build one-paragraph summary (<500 chars)
    parts: List[str] = [f"{project}:"]

    h = summary.pipeline_health
    if h.gates_run > 0:
        parts.append(f"pipeline {h.overall_status} ({h.gates_passed}/{h.gates_run} gates)")

    c = summary.coverage_status
    if c.total_required > 0:
        parts.append(f"coverage {c.overall_percent:.0f}% ({c.total_gaps} gaps)")

    if summary.blockers:
        crit = sum(1 for b in summary.blockers if b.severity == "critical")
        if crit:
            parts.append(f"{crit} critical blockers")
        else:
            parts.append(f"{len(summary.blockers)} blockers (none critical)")

    if summary.agent_decisions:
        parts.append(f"{len(summary.agent_decisions)} recent decisions")

    click.echo(" | ".join(parts))
