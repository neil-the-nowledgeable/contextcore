"""
ContextCore CLI - Manage ProjectContext resources and track tasks as spans.

Commands:
    contextcore create     Create a new ProjectContext
    contextcore annotate   Annotate K8s resources with context
    contextcore generate   Generate observability artifacts
    contextcore sync       Sync from external project tools
    contextcore controller Run the controller locally
    contextcore task       Track project tasks as OTel spans
"""

from __future__ import annotations

import json
import os
import sys
from typing import List, Optional

import click
import yaml


@click.group()
@click.version_option()
def main():
    """ContextCore - Unified metadata from project to operations."""
    pass


@main.command()
@click.option("--name", "-n", required=True, help="ProjectContext name")
@click.option("--namespace", default="default", help="K8s namespace")
@click.option("--project", "-p", required=True, help="Project identifier")
@click.option("--epic", help="Epic identifier")
@click.option("--task", multiple=True, help="Task identifiers (can specify multiple)")
@click.option(
    "--criticality",
    type=click.Choice(["critical", "high", "medium", "low"]),
    help="Business criticality",
)
@click.option(
    "--value",
    type=click.Choice(
        ["revenue-primary", "revenue-secondary", "cost-reduction", "compliance", "enabler"]
    ),
    help="Business value",
)
@click.option("--owner", help="Owning team")
@click.option("--design-doc", help="Design document URL")
@click.option("--adr", help="ADR identifier or URL")
@click.option("--target", multiple=True, help="Target resources (kind/name)")
@click.option("--output", "-o", type=click.Choice(["yaml", "json"]), default="yaml")
@click.option("--apply", is_flag=True, help="Apply to cluster (requires kubectl)")
def create(
    name: str,
    namespace: str,
    project: str,
    epic: Optional[str],
    task: tuple,
    criticality: Optional[str],
    value: Optional[str],
    owner: Optional[str],
    design_doc: Optional[str],
    adr: Optional[str],
    target: tuple,
    output: str,
    apply: bool,
):
    """Create a new ProjectContext resource."""
    # Build spec
    spec = {
        "project": {"id": project},
        "targets": [],
    }

    if epic:
        spec["project"]["epic"] = epic

    if task:
        spec["project"]["tasks"] = list(task)

    # Business context
    if criticality or value or owner:
        spec["business"] = {}
        if criticality:
            spec["business"]["criticality"] = criticality
        if value:
            spec["business"]["value"] = value
        if owner:
            spec["business"]["owner"] = owner

    # Design artifacts
    if design_doc or adr:
        spec["design"] = {}
        if design_doc:
            spec["design"]["doc"] = design_doc
        if adr:
            spec["design"]["adr"] = adr

    # Targets
    if target:
        for t in target:
            if "/" in t:
                kind, tname = t.split("/", 1)
                spec["targets"].append({"kind": kind, "name": tname})
            else:
                click.echo(f"Invalid target format: {t}. Use kind/name", err=True)
                sys.exit(1)
    else:
        # Default to a Deployment with the project name
        spec["targets"].append({"kind": "Deployment", "name": name})

    # Build full resource
    resource = {
        "apiVersion": "contextcore.io/v1",
        "kind": "ProjectContext",
        "metadata": {
            "name": name,
            "namespace": namespace,
        },
        "spec": spec,
    }

    # Output
    if output == "yaml":
        click.echo(yaml.dump(resource, default_flow_style=False))
    else:
        click.echo(json.dumps(resource, indent=2))

    # Apply if requested
    if apply:
        import subprocess

        yaml_content = yaml.dump(resource)
        result = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=yaml_content,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            click.echo(f"Error applying: {result.stderr}", err=True)
            sys.exit(1)
        click.echo(result.stdout)


@main.command()
@click.argument("resource")
@click.option("--context", "-c", required=True, help="ProjectContext name")
@click.option("--namespace", "-n", default="default", help="Namespace")
def annotate(resource: str, context: str, namespace: str):
    """Annotate a K8s resource with ProjectContext reference.

    RESOURCE should be in format kind/name, e.g., deployment/my-app
    """
    import subprocess

    if "/" not in resource:
        click.echo("Resource should be in format kind/name", err=True)
        sys.exit(1)

    # Apply annotation
    annotation = f"contextcore.io/projectcontext={context}"
    cmd = [
        "kubectl",
        "annotate",
        resource,
        annotation,
        "-n",
        namespace,
        "--overwrite",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"Error: {result.stderr}", err=True)
        sys.exit(1)

    click.echo(f"Annotated {resource} with {annotation}")


@main.command()
@click.option("--context", "-c", required=True, help="ProjectContext (namespace/name)")
@click.option("--output", "-o", default="./generated", help="Output directory")
@click.option("--service-monitor", is_flag=True, help="Generate ServiceMonitor")
@click.option("--prometheus-rule", is_flag=True, help="Generate PrometheusRule")
@click.option("--dashboard", is_flag=True, help="Generate Grafana dashboard")
@click.option("--all", "generate_all", is_flag=True, help="Generate all artifacts")
def generate(
    context: str,
    output: str,
    service_monitor: bool,
    prometheus_rule: bool,
    dashboard: bool,
    generate_all: bool,
):
    """Generate observability artifacts from ProjectContext."""
    import os
    import subprocess

    # Parse context
    if "/" in context:
        namespace, name = context.split("/", 1)
    else:
        namespace = "default"
        name = context

    # Get ProjectContext
    cmd = [
        "kubectl",
        "get",
        "projectcontext",
        name,
        "-n",
        namespace,
        "-o",
        "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"Error getting ProjectContext: {result.stderr}", err=True)
        sys.exit(1)

    pc = json.loads(result.stdout)
    spec = pc.get("spec", {})

    # Create output directory
    os.makedirs(output, exist_ok=True)

    if generate_all:
        service_monitor = prometheus_rule = dashboard = True

    generated = []

    if service_monitor:
        sm = _generate_service_monitor(name, namespace, spec)
        path = os.path.join(output, f"{name}-servicemonitor.yaml")
        with open(path, "w") as f:
            yaml.dump(sm, f)
        generated.append(path)

    if prometheus_rule:
        pr = _generate_prometheus_rule(name, namespace, spec)
        path = os.path.join(output, f"{name}-prometheusrule.yaml")
        with open(path, "w") as f:
            yaml.dump(pr, f)
        generated.append(path)

    if dashboard:
        db = _generate_dashboard(name, namespace, spec)
        path = os.path.join(output, f"{name}-dashboard.json")
        with open(path, "w") as f:
            json.dump(db, f, indent=2)
        generated.append(path)

    if generated:
        click.echo(f"Generated {len(generated)} artifacts in {output}/")
        for path in generated:
            click.echo(f"  - {path}")
    else:
        click.echo("No artifacts generated. Use --all or specific flags.")


def _generate_service_monitor(name: str, namespace: str, spec: dict) -> dict:
    """Generate ServiceMonitor from ProjectContext spec."""
    business = spec.get("business", {})
    criticality = business.get("criticality", "medium")

    interval = {
        "critical": "10s",
        "high": "30s",
        "medium": "60s",
        "low": "120s",
    }.get(criticality, "60s")

    targets = spec.get("targets", [])
    target_name = targets[0]["name"] if targets else name

    return {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "ServiceMonitor",
        "metadata": {
            "name": f"{name}-monitor",
            "namespace": namespace,
            "labels": {
                "contextcore.io/project": spec.get("project", {}).get("id", ""),
            },
        },
        "spec": {
            "selector": {
                "matchLabels": {
                    "app": target_name,
                },
            },
            "endpoints": [
                {
                    "port": "metrics",
                    "interval": interval,
                },
            ],
        },
    }


def _generate_prometheus_rule(name: str, namespace: str, spec: dict) -> dict:
    """Generate PrometheusRule from ProjectContext spec."""
    requirements = spec.get("requirements", {})
    design = spec.get("design", {})
    project = spec.get("project", {})

    rules = []

    # Latency alert from requirements
    latency_p99 = requirements.get("latencyP99")
    if latency_p99:
        # Parse latency (e.g., "200ms" -> 0.2)
        latency_seconds = float(latency_p99.replace("ms", "")) / 1000

        rules.append({
            "alert": f"{name.title().replace('-', '')}LatencyHigh",
            "expr": f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{service="{name}"}}[5m])) > {latency_seconds}',
            "for": "5m",
            "labels": {
                "severity": "critical",
                "project": project.get("id", ""),
            },
            "annotations": {
                "summary": f"High latency on {name}",
                "design_doc": design.get("doc", ""),
                "adr": design.get("adr", ""),
            },
        })

    # Availability alert
    availability = requirements.get("availability")
    if availability:
        error_rate = 100 - float(availability)

        rules.append({
            "alert": f"{name.title().replace('-', '')}ErrorRateHigh",
            "expr": f'rate(http_requests_total{{service="{name}", status=~"5.."}}[5m]) / rate(http_requests_total{{service="{name}"}}[5m]) > {error_rate / 100}',
            "for": "5m",
            "labels": {
                "severity": "critical",
                "project": project.get("id", ""),
            },
            "annotations": {
                "summary": f"High error rate on {name}",
                "design_doc": design.get("doc", ""),
            },
        })

    return {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "PrometheusRule",
        "metadata": {
            "name": f"{name}-slo",
            "namespace": namespace,
        },
        "spec": {
            "groups": [
                {
                    "name": f"{name}.slo",
                    "rules": rules,
                },
            ],
        },
    }


def _generate_dashboard(name: str, namespace: str, spec: dict) -> dict:
    """Generate Grafana dashboard JSON from ProjectContext spec."""
    project = spec.get("project", {})
    business = spec.get("business", {})
    design = spec.get("design", {})

    return {
        "title": f"{name} - {project.get('id', 'Unknown')}",
        "tags": [
            f"project:{project.get('id', '')}",
            f"criticality:{business.get('criticality', 'medium')}",
            "contextcore",
        ],
        "annotations": {
            "list": [
                {
                    "name": "Design Doc",
                    "iconColor": "blue",
                    "target": {"url": design.get("doc", "")},
                },
            ],
        },
        "links": [
            {
                "title": "Design Document",
                "url": design.get("doc", ""),
                "type": "link",
            },
            {
                "title": "ADR",
                "url": design.get("adr", ""),
                "type": "link",
            },
        ],
        "panels": [
            {
                "title": "Request Rate",
                "type": "timeseries",
                "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                "targets": [
                    {
                        "expr": f'rate(http_requests_total{{service="{name}"}}[5m])',
                        "legendFormat": "{{status}}",
                    },
                ],
            },
            {
                "title": "Latency P99",
                "type": "timeseries",
                "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
                "targets": [
                    {
                        "expr": f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{service="{name}"}}[5m]))',
                        "legendFormat": "P99",
                    },
                ],
            },
        ],
        "schemaVersion": 38,
        "version": 1,
    }


@main.group()
def sync():
    """Sync ProjectContext from external tools."""
    pass


@sync.command()
@click.option("--project", "-p", required=True, help="Jira project key")
@click.option("--namespace", "-n", default="default", help="Target K8s namespace")
@click.option("--url", envvar="JIRA_URL", help="Jira URL")
@click.option("--token", envvar="JIRA_TOKEN", help="Jira API token")
def jira(project: str, namespace: str, url: Optional[str], token: Optional[str]):
    """Sync ProjectContext from Jira project."""
    if not url or not token:
        click.echo("JIRA_URL and JIRA_TOKEN environment variables required", err=True)
        sys.exit(1)

    click.echo(f"Syncing from Jira project {project} to namespace {namespace}")
    click.echo("(Jira sync not yet implemented)")


@sync.command()
@click.option("--repo", "-r", required=True, help="GitHub repo (owner/name)")
@click.option("--namespace", "-n", default="default", help="Target K8s namespace")
@click.option("--token", envvar="GITHUB_TOKEN", help="GitHub token")
def github(repo: str, namespace: str, token: Optional[str]):
    """Sync ProjectContext from GitHub issues."""
    if not token:
        click.echo("GITHUB_TOKEN environment variable required", err=True)
        sys.exit(1)

    click.echo(f"Syncing from GitHub repo {repo} to namespace {namespace}")
    click.echo("(GitHub sync not yet implemented)")


@main.command()
@click.option("--kubeconfig", envvar="KUBECONFIG", help="Path to kubeconfig")
@click.option("--namespace", default="", help="Namespace to watch (empty for all)")
def controller(kubeconfig: Optional[str], namespace: str):
    """Run the ContextCore controller locally."""
    click.echo("Starting ContextCore controller...")
    click.echo(f"  kubeconfig: {kubeconfig or 'in-cluster'}")
    click.echo(f"  namespace: {namespace or 'all'}")
    click.echo("(Controller not yet implemented - use kopf run)")


# ============================================================================
# Task Tracking Commands (Tasks as Spans)
# ============================================================================

# Global tracker instance (lazy loaded)
_tracker = None


def _get_tracker(project: str):
    """Get or create tracker instance."""
    global _tracker
    if _tracker is None or _tracker.project != project:
        from contextcore.tracker import TaskTracker
        _tracker = TaskTracker(project=project)
    return _tracker


@main.group()
def task():
    """Track project tasks as OpenTelemetry spans.

    Tasks are modeled as spans with full lifecycle tracking:
    - start: Creates a span
    - update: Adds span events
    - block/unblock: Sets span status
    - complete: Ends the span

    View tasks in Grafana Tempo as trace hierarchies.
    """
    pass


@task.command("start")
@click.option("--id", "task_id", required=True, help="Task identifier (e.g., PROJ-123)")
@click.option("--title", "-t", required=True, help="Task title")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option(
    "--type",
    "task_type",
    type=click.Choice(["epic", "story", "task", "subtask", "bug", "spike", "incident"]),
    default="task",
    help="Task type",
)
@click.option(
    "--status",
    type=click.Choice(["backlog", "todo", "in_progress"]),
    default="todo",
    help="Initial status",
)
@click.option(
    "--priority",
    type=click.Choice(["critical", "high", "medium", "low"]),
    help="Priority level",
)
@click.option("--assignee", "-a", help="Person assigned")
@click.option("--points", type=int, help="Story points")
@click.option("--parent", help="Parent task ID (epic or story)")
@click.option("--depends-on", multiple=True, help="Task IDs this depends on")
@click.option("--label", multiple=True, help="Labels/tags")
@click.option("--url", help="External URL (Jira, GitHub, etc.)")
@click.option("--sprint", help="Sprint ID")
def task_start(
    task_id: str,
    title: str,
    project: str,
    task_type: str,
    status: str,
    priority: Optional[str],
    assignee: Optional[str],
    points: Optional[int],
    parent: Optional[str],
    depends_on: tuple,
    label: tuple,
    url: Optional[str],
    sprint: Optional[str],
):
    """Start a new task (creates a span).

    Example:
        contextcore task start --id PROJ-123 --title "Implement auth" --type story
    """
    tracker = _get_tracker(project)

    ctx = tracker.start_task(
        task_id=task_id,
        title=title,
        task_type=task_type,
        status=status,
        priority=priority,
        assignee=assignee,
        story_points=points,
        labels=list(label) if label else None,
        parent_id=parent,
        depends_on=list(depends_on) if depends_on else None,
        url=url,
        sprint_id=sprint,
    )

    click.echo(f"Started {task_type}: {task_id}")
    click.echo(f"  Title: {title}")
    click.echo(f"  Trace ID: {format(ctx.trace_id, '032x')}")
    if parent:
        click.echo(f"  Parent: {parent}")


@task.command("update")
@click.option("--id", "task_id", required=True, help="Task identifier")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option(
    "--status",
    type=click.Choice(["backlog", "todo", "in_progress", "in_review", "blocked", "done"]),
    help="New status",
)
@click.option("--assignee", "-a", help="Reassign to")
@click.option("--points", type=int, help="Update story points")
def task_update(
    task_id: str,
    project: str,
    status: Optional[str],
    assignee: Optional[str],
    points: Optional[int],
):
    """Update a task (adds span events).

    Example:
        contextcore task update --id PROJ-123 --status in_progress
    """
    tracker = _get_tracker(project)

    if status:
        tracker.update_status(task_id, status)
        click.echo(f"Task {task_id}: status → {status}")

    if assignee:
        tracker.assign_task(task_id, assignee)
        click.echo(f"Task {task_id}: assigned → {assignee}")


@task.command("block")
@click.option("--id", "task_id", required=True, help="Task identifier")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option("--reason", "-r", required=True, help="Why is it blocked?")
@click.option("--by", "blocked_by", help="Blocking task ID")
def task_block(task_id: str, project: str, reason: str, blocked_by: Optional[str]):
    """Mark task as blocked (adds event, sets ERROR status).

    Example:
        contextcore task block --id PROJ-123 --reason "Waiting on API design" --by PROJ-100
    """
    tracker = _get_tracker(project)
    tracker.block_task(task_id, reason=reason, blocked_by=blocked_by)
    click.echo(f"Task {task_id}: BLOCKED - {reason}")
    if blocked_by:
        click.echo(f"  Blocked by: {blocked_by}")


@task.command("unblock")
@click.option("--id", "task_id", required=True, help="Task identifier")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option(
    "--status",
    default="in_progress",
    help="Status after unblocking",
)
def task_unblock(task_id: str, project: str, status: str):
    """Remove blocker from task.

    Example:
        contextcore task unblock --id PROJ-123
    """
    tracker = _get_tracker(project)
    tracker.unblock_task(task_id, new_status=status)
    click.echo(f"Task {task_id}: unblocked → {status}")


@task.command("complete")
@click.option("--id", "task_id", required=True, help="Task identifier")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
def task_complete(task_id: str, project: str):
    """Complete a task (ends the span).

    Example:
        contextcore task complete --id PROJ-123
    """
    tracker = _get_tracker(project)
    tracker.complete_task(task_id)
    click.echo(f"Task {task_id}: COMPLETED")


@task.command("cancel")
@click.option("--id", "task_id", required=True, help="Task identifier")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option("--reason", "-r", help="Cancellation reason")
def task_cancel(task_id: str, project: str, reason: Optional[str]):
    """Cancel a task (ends span with cancelled status).

    Example:
        contextcore task cancel --id PROJ-123 --reason "No longer needed"
    """
    tracker = _get_tracker(project)
    tracker.cancel_task(task_id, reason=reason)
    click.echo(f"Task {task_id}: CANCELLED")
    if reason:
        click.echo(f"  Reason: {reason}")


@task.command("comment")
@click.option("--id", "task_id", required=True, help="Task identifier")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option("--author", "-a", default=lambda: os.environ.get("USER", "unknown"), help="Comment author")
@click.option("--text", "-t", required=True, help="Comment text")
def task_comment(task_id: str, project: str, author: str, text: str):
    """Add a comment to task (as span event).

    Example:
        contextcore task comment --id PROJ-123 --text "Updated the API contract"
    """
    tracker = _get_tracker(project)
    tracker.add_comment(task_id, author=author, text=text)
    click.echo(f"Task {task_id}: comment by {author}")


@task.command("list")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
def task_list(project: str):
    """List active (incomplete) tasks.

    Example:
        contextcore task list --project my-project
    """
    tracker = _get_tracker(project)
    active = tracker.get_active_tasks()

    if not active:
        click.echo("No active tasks")
        return

    click.echo(f"Active tasks in {project}:")
    for task_id in active:
        click.echo(f"  - {task_id}")


# ============================================================================
# Sprint Commands
# ============================================================================

@main.group()
def sprint():
    """Track sprints as parent spans."""
    pass


@sprint.command("start")
@click.option("--id", "sprint_id", required=True, help="Sprint identifier")
@click.option("--name", "-n", required=True, help="Sprint name")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option("--goal", "-g", help="Sprint goal")
@click.option("--start-date", help="Start date (ISO format)")
@click.option("--end-date", help="End date (ISO format)")
@click.option("--points", type=int, help="Planned story points")
def sprint_start(
    sprint_id: str,
    name: str,
    project: str,
    goal: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    points: Optional[int],
):
    """Start a new sprint.

    Example:
        contextcore sprint start --id sprint-3 --name "Sprint 3" --goal "Complete auth"
    """
    from contextcore.tracker import SprintTracker, TaskTracker

    tracker = _get_tracker(project)
    sprint_tracker = SprintTracker(tracker)

    ctx = sprint_tracker.start_sprint(
        sprint_id=sprint_id,
        name=name,
        goal=goal,
        start_date=start_date,
        end_date=end_date,
        planned_points=points,
    )

    click.echo(f"Started sprint: {sprint_id}")
    click.echo(f"  Name: {name}")
    if goal:
        click.echo(f"  Goal: {goal}")


@sprint.command("end")
@click.option("--id", "sprint_id", required=True, help="Sprint identifier")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option("--points", type=int, help="Completed story points")
@click.option("--notes", help="Retrospective notes")
def sprint_end(
    sprint_id: str,
    project: str,
    points: Optional[int],
    notes: Optional[str],
):
    """End a sprint.

    Example:
        contextcore sprint end --id sprint-3 --points 21
    """
    from contextcore.tracker import SprintTracker

    tracker = _get_tracker(project)
    sprint_tracker = SprintTracker(tracker)
    sprint_tracker.end_sprint(sprint_id, completed_points=points, notes=notes)

    click.echo(f"Ended sprint: {sprint_id}")
    if points:
        click.echo(f"  Completed points: {points}")


# ============================================================================
# Metrics Commands
# ============================================================================

@main.group()
def metrics():
    """View derived project metrics from task spans.

    Metrics include:
    - Lead time (creation to completion)
    - Cycle time (in_progress to completion)
    - Throughput (tasks completed per period)
    - WIP (work in progress count)
    - Velocity (story points per sprint)
    """
    pass


@metrics.command("summary")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option("--days", "-d", type=int, default=30, help="Days to analyze")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def metrics_summary(project: str, days: int, output_format: str):
    """Show summary metrics for a project.

    Example:
        contextcore metrics summary --project my-project --days 14
    """
    from contextcore.metrics import TaskMetrics

    metrics_collector = TaskMetrics(project=project)
    summary = metrics_collector.get_summary(days=days)

    if output_format == "json":
        click.echo(json.dumps(summary, indent=2))
    else:
        click.echo(f"Project Metrics: {project}")
        click.echo(f"  Period: last {days} days")
        click.echo()
        click.echo("Throughput:")
        click.echo(f"  Tasks completed: {summary['tasks_completed']}")
        click.echo(f"  Story points: {summary['story_points_completed']}")
        click.echo()
        click.echo("Current State:")
        click.echo(f"  Active tasks: {summary['tasks_active']}")
        click.echo(f"  Work in progress: {summary['wip']}")
        click.echo(f"  Blocked: {summary['blocked']}")
        click.echo()
        if summary['avg_lead_time_hours']:
            click.echo(f"Lead Time (avg): {summary['avg_lead_time_hours']:.1f} hours")
        if summary['avg_cycle_time_hours']:
            click.echo(f"Cycle Time (avg): {summary['avg_cycle_time_hours']:.1f} hours")

        if summary['status_breakdown']:
            click.echo()
            click.echo("Status Breakdown:")
            for status, count in summary['status_breakdown'].items():
                click.echo(f"  {status}: {count}")


@metrics.command("wip")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
def metrics_wip(project: str):
    """Show current work in progress.

    Example:
        contextcore metrics wip --project my-project
    """
    from contextcore.state import StateManager

    state = StateManager(project)
    active = state.get_active_spans()

    wip = []
    for task_id, span_state in active.items():
        if span_state.attributes.get("task.status") == "in_progress":
            wip.append({
                "id": task_id,
                "title": span_state.attributes.get("task.title", ""),
                "type": span_state.attributes.get("task.type", "task"),
                "assignee": span_state.attributes.get("task.assignee", "unassigned"),
            })

    if not wip:
        click.echo("No tasks in progress")
        return

    click.echo(f"Work in Progress ({len(wip)} tasks):")
    for task in wip:
        click.echo(f"  [{task['type']}] {task['id']}: {task['title']}")
        click.echo(f"           Assignee: {task['assignee']}")


@metrics.command("blocked")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
def metrics_blocked(project: str):
    """Show currently blocked tasks.

    Example:
        contextcore metrics blocked --project my-project
    """
    from contextcore.state import StateManager

    state = StateManager(project)
    active = state.get_active_spans()

    blocked = []
    for task_id, span_state in active.items():
        if span_state.attributes.get("task.status") == "blocked":
            # Find blocking reason from events
            reason = "Unknown reason"
            for event in reversed(span_state.events):
                if event.get("name") == "task.blocked":
                    reason = event.get("attributes", {}).get("reason", reason)
                    break

            blocked.append({
                "id": task_id,
                "title": span_state.attributes.get("task.title", ""),
                "reason": reason,
                "blocked_by": span_state.attributes.get("task.blocked_by"),
            })

    if not blocked:
        click.echo("No blocked tasks")
        return

    click.echo(f"Blocked Tasks ({len(blocked)}):")
    for task in blocked:
        click.echo(f"  {task['id']}: {task['title']}")
        click.echo(f"    Reason: {task['reason']}")
        if task['blocked_by']:
            click.echo(f"    Blocked by: {task['blocked_by']}")


@metrics.command("export")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option("--endpoint", envvar="OTEL_EXPORTER_OTLP_ENDPOINT", default="localhost:4317", help="OTLP endpoint")
@click.option("--interval", type=int, default=60, help="Export interval in seconds")
def metrics_export(project: str, endpoint: str, interval: int):
    """Start exporting metrics to OTLP endpoint.

    Runs continuously, exporting metrics at the specified interval.

    Example:
        contextcore metrics export --project my-project --endpoint localhost:4317
    """
    import signal
    import time
    from contextcore.metrics import TaskMetrics

    click.echo(f"Starting metrics export for {project}")
    click.echo(f"  Endpoint: {endpoint}")
    click.echo(f"  Interval: {interval}s")
    click.echo("Press Ctrl+C to stop")

    metrics_collector = TaskMetrics(
        project=project,
        export_interval_ms=interval * 1000,
    )

    def shutdown(signum, frame):
        click.echo("\nShutting down...")
        metrics_collector.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep running until interrupted
    while True:
        time.sleep(interval)


# ============================================================================
# Demo Commands (microservices-demo POC)
# ============================================================================

@main.group()
def demo():
    """Generate and load demo data using Google's microservices-demo.

    This command group provides tools to demonstrate ContextCore's value:

    \b
    1. Generate realistic 3-month project history as OTel spans
    2. Load generated spans to Tempo for visualization
    3. Set up a local kind cluster with the full observability stack

    The demo uses Google's Online Boutique (microservices-demo) as the
    target application, simulating development of all 11 microservices.
    """
    pass


@demo.command("generate")
@click.option("--project", "-p", default="online-boutique", help="Project identifier")
@click.option("--output", "-o", default="./demo_output", help="Output directory for spans")
@click.option("--months", "-m", type=int, default=3, help="Duration of project history (months)")
@click.option("--seed", type=int, help="Random seed for reproducibility")
@click.option("--format", "output_format", type=click.Choice(["json", "otlp"]), default="json", help="Output format")
@click.option("--endpoint", envvar="OTEL_EXPORTER_OTLP_ENDPOINT", help="OTLP endpoint (for otlp format)")
def demo_generate(
    project: str,
    output: str,
    months: int,
    seed: Optional[int],
    output_format: str,
    endpoint: Optional[str],
):
    """Generate demo project history for microservices-demo.

    Creates realistic task/sprint data for all 11 microservices as OTel spans.

    \b
    Examples:
        # Generate 3-month history to JSON
        contextcore demo generate --project online-boutique

        # Generate with fixed seed for reproducibility
        contextcore demo generate --seed 42

        # Generate and export directly to Tempo
        contextcore demo generate --format otlp --endpoint localhost:4317
    """
    from contextcore.demo import generate_demo_data

    click.echo(f"Generating {months}-month project history for {project}")
    click.echo(f"  Output: {output}")
    if seed:
        click.echo(f"  Seed: {seed}")

    stats = generate_demo_data(
        project=project,
        output_dir=output if output_format == "json" else None,
        duration_months=months,
        seed=seed,
    )

    click.echo()
    click.echo("Generation complete!")
    click.echo(f"  Services: {stats['services']}")
    click.echo(f"  Epics: {stats['epics']}")
    click.echo(f"  Stories: {stats['stories']}")
    click.echo(f"  Tasks: {stats['tasks']}")
    click.echo(f"  Blockers: {stats['blockers']}")
    click.echo(f"  Sprints: {stats['sprints']}")
    click.echo(f"  Total spans: {stats['total_spans']}")

    if output_format == "json" and "output_file" in stats:
        click.echo()
        click.echo(f"Spans saved to: {stats['output_file']}")
        click.echo()
        click.echo("To load into Tempo:")
        click.echo(f"  contextcore demo load --file {stats['output_file']} --endpoint localhost:4317")

    if output_format == "otlp":
        if not endpoint:
            click.echo("Error: --endpoint required for otlp format", err=True)
            sys.exit(1)

        from contextcore.demo import load_to_tempo

        click.echo()
        click.echo(f"Exporting to {endpoint}...")
        # Note: For direct OTLP export, we'd need to regenerate with OTLP exporter
        click.echo("(Direct OTLP export during generation not yet implemented)")
        click.echo("Use 'contextcore demo load' to load from JSON file")


@demo.command("load")
@click.option("--file", "-f", "spans_file", required=True, type=click.Path(exists=True), help="JSON spans file")
@click.option("--endpoint", "-e", envvar="OTEL_EXPORTER_OTLP_ENDPOINT", default="localhost:4317", help="OTLP endpoint")
@click.option("--insecure/--secure", default=True, help="Use insecure connection")
def demo_load(spans_file: str, endpoint: str, insecure: bool):
    """Load generated spans to Tempo via OTLP.

    \b
    Examples:
        contextcore demo load --file ./demo_output/demo_spans.json

        contextcore demo load --file ./demo_output/demo_spans.json --endpoint tempo.local:4317
    """
    from contextcore.demo import load_to_tempo

    click.echo(f"Loading spans from {spans_file}")
    click.echo(f"  Endpoint: {endpoint}")

    result = load_to_tempo(
        endpoint=endpoint,
        spans_file=spans_file,
        insecure=insecure,
    )

    if result["success"]:
        click.echo()
        click.echo(f"Successfully loaded {result['spans_exported']} spans to {endpoint}")
    else:
        click.echo()
        click.echo("Failed to load spans", err=True)
        sys.exit(1)


@demo.command("setup")
@click.option("--cluster-name", default="contextcore-demo", help="Kind cluster name")
@click.option("--skip-cluster", is_flag=True, help="Skip cluster creation (use existing)")
@click.option("--skip-observability", is_flag=True, help="Skip observability stack deployment")
@click.option("--skip-demo", is_flag=True, help="Skip microservices-demo deployment")
def demo_setup(cluster_name: str, skip_cluster: bool, skip_observability: bool, skip_demo: bool):
    """Set up local kind cluster with observability stack.

    Deploys:
    - Kind cluster
    - Grafana, Tempo, Mimir, Loki (via Alloy)
    - ContextCore CRD
    - microservices-demo with ProjectContext resources

    \b
    Examples:
        # Full setup
        contextcore demo setup

        # Skip cluster creation (use existing)
        contextcore demo setup --skip-cluster
    """
    import subprocess
    import shutil

    # Check prerequisites
    missing = []
    for cmd in ["kind", "kubectl", "helm"]:
        if not shutil.which(cmd):
            missing.append(cmd)

    if missing:
        click.echo(f"Missing required tools: {', '.join(missing)}", err=True)
        click.echo("Please install them before running setup.")
        sys.exit(1)

    click.echo("ContextCore Demo Setup")
    click.echo("=" * 40)

    # Step 1: Create kind cluster
    if not skip_cluster:
        click.echo()
        click.echo("[1/4] Creating kind cluster...")
        result = subprocess.run(
            ["kind", "get", "clusters"],
            capture_output=True,
            text=True,
        )
        if cluster_name in result.stdout.split():
            click.echo(f"  Cluster '{cluster_name}' already exists")
        else:
            result = subprocess.run(
                ["kind", "create", "cluster", "--name", cluster_name],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                click.echo(f"Error creating cluster: {result.stderr}", err=True)
                sys.exit(1)
            click.echo(f"  Created cluster: {cluster_name}")
    else:
        click.echo()
        click.echo("[1/4] Skipping cluster creation")

    # Step 2: Deploy observability stack
    if not skip_observability:
        click.echo()
        click.echo("[2/4] Deploying observability stack...")
        click.echo("  (Not yet implemented - manual Helm install required)")
        click.echo()
        click.echo("  Manual steps:")
        click.echo("    helm repo add grafana https://grafana.github.io/helm-charts")
        click.echo("    helm install grafana grafana/grafana -n observability --create-namespace")
        click.echo("    helm install tempo grafana/tempo -n observability")
    else:
        click.echo()
        click.echo("[2/4] Skipping observability deployment")

    # Step 3: Apply ContextCore CRD
    click.echo()
    click.echo("[3/4] Applying ContextCore CRD...")
    crd_path = os.path.join(os.path.dirname(__file__), "..", "..", "crds", "projectcontext.yaml")
    if os.path.exists(crd_path):
        result = subprocess.run(
            ["kubectl", "apply", "-f", crd_path],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            click.echo("  Applied ProjectContext CRD")
        else:
            click.echo(f"  Warning: {result.stderr}")
    else:
        click.echo("  CRD file not found - skipping")

    # Step 4: Deploy microservices-demo
    if not skip_demo:
        click.echo()
        click.echo("[4/4] Deploying microservices-demo...")
        click.echo("  (Not yet implemented)")
        click.echo()
        click.echo("  Manual steps:")
        click.echo("    kubectl create namespace online-boutique")
        click.echo("    kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/main/release/kubernetes-manifests.yaml -n online-boutique")
    else:
        click.echo()
        click.echo("[4/4] Skipping microservices-demo deployment")

    click.echo()
    click.echo("=" * 40)
    click.echo("Setup complete!")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Generate demo data:")
    click.echo("     contextcore demo generate")
    click.echo()
    click.echo("  2. Load spans to Tempo:")
    click.echo("     contextcore demo load --file ./demo_output/demo_spans.json")
    click.echo()
    click.echo("  3. Access Grafana:")
    click.echo("     kubectl port-forward svc/grafana 3000:80 -n observability")
    click.echo("     Open http://localhost:3000")


@demo.command("services")
def demo_services():
    """List all 11 microservices from Online Boutique.

    Shows service metadata used for ProjectContext generation.
    """
    from contextcore.demo import SERVICE_CONFIGS

    click.echo("Online Boutique Microservices")
    click.echo("=" * 60)
    click.echo()
    click.echo(f"{'Service':<25} {'Language':<10} {'Criticality':<10} {'Business Value'}")
    click.echo("-" * 60)

    for name, config in SERVICE_CONFIGS.items():
        click.echo(f"{name:<25} {config.language:<10} {config.criticality:<10} {config.business_value}")

    click.echo()
    click.echo(f"Total: {len(SERVICE_CONFIGS)} services")


if __name__ == "__main__":
    main()
