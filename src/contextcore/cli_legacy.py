"""
ContextCore CLI - Manage ProjectContext resources and track tasks as spans.

Commands:
    contextcore create     Create a new ProjectContext
    contextcore annotate   Annotate K8s resources with context
    contextcore generate   Generate observability artifacts
    contextcore sync       Sync from external project tools
    contextcore controller Run the controller locally
    contextcore task       Track project tasks as OTel spans
    contextcore sprint     Track sprints as parent spans
    contextcore metrics    View derived project metrics
    contextcore git        Git integration for automatic task linking
    contextcore demo       Demo data generation (microservices-demo)
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


# ============================================================================
# Runbook Generation
# ============================================================================


def _get_project_context_spec(project: str, namespace: str = "default") -> Optional[dict]:
    """
    Fetch ProjectContext spec from Kubernetes cluster.

    Args:
        project: ProjectContext name or namespace/name
        namespace: Default namespace if not specified in project

    Returns:
        ProjectContext spec dict, or None if not found
    """
    import subprocess

    # Parse project identifier
    if "/" in project:
        namespace, name = project.split("/", 1)
    else:
        name = project

    cmd = [
        "kubectl", "get", "projectcontext", name,
        "-n", namespace, "-o", "json"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None

    pc = json.loads(result.stdout)
    return pc.get("spec", {})


@main.command()
@click.option("--project", "-p", required=True, help="ProjectContext name (or namespace/name)")
@click.option("--namespace", "-n", default="default", help="Kubernetes namespace")
@click.option("--output", "-o", type=click.Path(), help="Output file path (default: stdout)")
@click.option("--format", "output_format", default="markdown",
              type=click.Choice(["markdown"]), help="Output format")
@click.option("--from-file", type=click.Path(exists=True),
              help="Read spec from local YAML file instead of cluster")
def runbook(
    project: str,
    namespace: str,
    output: Optional[str],
    output_format: str,
    from_file: Optional[str],
):
    """Generate operational runbook from ProjectContext.

    Creates a Markdown runbook containing:
    - Service overview and business context
    - SLO definitions and alert thresholds
    - Known risks and mitigations
    - Kubernetes resource inspection commands
    - Common operational procedures
    - Escalation contacts

    Examples:
        contextcore runbook -p my-service
        contextcore runbook -p default/my-service -o runbook.md
        contextcore runbook -p my-service --from-file context.yaml
    """
    from contextcore.generators.runbook import generate_runbook

    # Get spec from file or cluster
    if from_file:
        with open(from_file) as f:
            data = yaml.safe_load(f)
        spec = data.get("spec", data)
        # Extract project_id from spec or filename
        project_info = spec.get("project", {})
        if isinstance(project_info, dict):
            project_id = project_info.get("id", project)
        else:
            project_id = project_info or project
    else:
        spec = _get_project_context_spec(project, namespace)
        if spec is None:
            click.echo(f"Error: ProjectContext '{project}' not found in namespace '{namespace}'", err=True)
            click.echo("Hint: Use --from-file to generate from a local YAML file", err=True)
            sys.exit(1)
        project_info = spec.get("project", {})
        if isinstance(project_info, dict):
            project_id = project_info.get("id", project)
        else:
            project_id = project_info or project

    # Generate runbook
    runbook_content = generate_runbook(project_id, spec, output_format)

    # Output
    if output:
        with open(output, "w") as f:
            f.write(runbook_content)
        click.echo(f"Runbook written to {output}")
    else:
        click.echo(runbook_content)


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
    """Run the ContextCore controller locally.

    The controller watches ProjectContext CRDs and generates:
    - ServiceMonitor for metrics scraping
    - PrometheusRule for recording/alerting rules
    - Grafana Dashboard ConfigMaps

    Requires: kopf, kubernetes, opentelemetry-exporter-otlp
    """
    import subprocess

    click.echo("Starting ContextCore controller...")
    click.echo(f"  kubeconfig: {kubeconfig or 'in-cluster'}")
    click.echo(f"  namespace: {namespace or 'all'}")

    # Build kopf command
    cmd = ["kopf", "run", "-m", "contextcore.operator", "--verbose"]

    if namespace:
        cmd.extend(["--namespace", namespace])

    click.echo(f"  Running: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        click.echo("Error: kopf not found. Install with: pip install kopf", err=True)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        click.echo(f"Controller exited with error: {e.returncode}", err=True)
        sys.exit(e.returncode)


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
# Git Integration Commands
# ============================================================================

import re

# Patterns for detecting task references in commit messages
TASK_PATTERNS = [
    r"(?:implements?|closes?|fixes?|refs?|resolves?|relates?\s+to)\s+([A-Z]+-\d+)",
    r"\b([A-Z]{2,10}-\d+)\b",  # Generic PROJ-123 pattern
    r"#(\d+)",  # GitHub issue numbers
]

# Patterns indicating task completion
COMPLETION_PATTERNS = [
    r"(?:closes?|fixes?|resolves?)\s+([A-Z]+-\d+)",
]


def parse_task_refs(message: str) -> List[str]:
    """Extract task IDs from a commit message."""
    task_ids = []
    for pattern in TASK_PATTERNS:
        matches = re.findall(pattern, message, re.IGNORECASE)
        task_ids.extend(matches)
    return list(set(task_ids))  # Deduplicate


def parse_completion_refs(message: str) -> List[str]:
    """Extract task IDs that should be marked complete."""
    task_ids = []
    for pattern in COMPLETION_PATTERNS:
        matches = re.findall(pattern, message, re.IGNORECASE)
        task_ids.extend(matches)
    return list(set(task_ids))


@main.group()
def git():
    """Git integration for automatic task linking.

    Parses commit messages for task references and:
    - Links commits to task spans
    - Auto-updates task status (first commit → in_progress)
    - Logs commit events

    Use with git hooks for automatic tracking.
    """
    pass


@git.command("link")
@click.option("--commit", "-c", "commit_sha", required=True, help="Commit SHA")
@click.option("--message", "-m", "commit_message", required=True, help="Commit message")
@click.option("--author", "-a", help="Commit author")
@click.option("--repo", "-r", help="Repository name")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option("--auto-status/--no-auto-status", default=True, help="Auto-update task status")
def git_link(
    commit_sha: str,
    commit_message: str,
    author: Optional[str],
    repo: Optional[str],
    project: str,
    auto_status: bool,
):
    """Link a commit to tasks found in its message.

    Parses the commit message for task references (PROJ-123, #123, etc.)
    and links the commit to those tasks.

    \b
    Examples:
        # Manual linking
        contextcore git link --commit abc123 --message "feat: implement auth [PROJ-123]"

        # From git hook
        contextcore git link \\
            --commit $(git rev-parse HEAD) \\
            --message "$(git log -1 --format=%B)" \\
            --author "$(git log -1 --format=%an)"
    """
    from contextcore.state import StateManager

    # Parse task references
    task_ids = parse_task_refs(commit_message)
    completion_ids = parse_completion_refs(commit_message)

    if not task_ids:
        click.echo("No task references found in commit message")
        return

    click.echo(f"Commit: {commit_sha[:8]}")
    click.echo(f"Tasks found: {', '.join(task_ids)}")

    tracker = _get_tracker(project)
    state_mgr = StateManager(project)
    active_tasks = state_mgr.get_active_spans()

    linked = []
    status_updated = []

    for task_id in task_ids:
        # Check if task exists in active spans
        if task_id not in active_tasks:
            click.echo(f"  {task_id}: not found (skipping)")
            continue

        span_state = active_tasks[task_id]
        current_status = span_state.attributes.get("task.status", "unknown")

        # Add commit link event
        state_mgr.add_event(task_id, "commit.linked", {
            "commit_sha": commit_sha,
            "commit_message": commit_message[:200],  # Truncate
            "author": author or "unknown",
            "repo": repo or "unknown",
        })
        linked.append(task_id)

        # Auto-update status if enabled
        if auto_status:
            # If task is in todo/backlog and this is first commit, move to in_progress
            if current_status in ("todo", "backlog"):
                tracker.update_status(task_id, "in_progress")
                status_updated.append((task_id, "in_progress"))

            # If commit message indicates completion, move to in_review
            if task_id in completion_ids and current_status == "in_progress":
                tracker.update_status(task_id, "in_review")
                status_updated.append((task_id, "in_review"))

    # Output summary
    if linked:
        click.echo()
        click.echo(f"Linked commit to {len(linked)} task(s):")
        for task_id in linked:
            click.echo(f"  ✓ {task_id}")

    if status_updated:
        click.echo()
        click.echo("Status updates:")
        for task_id, new_status in status_updated:
            click.echo(f"  {task_id} → {new_status}")


@git.command("hook")
@click.option("--type", "hook_type", type=click.Choice(["post-commit"]), default="post-commit")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="default", help="Project ID")
@click.option("--output", "-o", help="Output path (defaults to .git/hooks/<type>)")
def git_hook(hook_type: str, project: str, output: Optional[str]):
    """Generate a git hook script for automatic commit linking.

    \b
    Examples:
        # Generate and install post-commit hook
        contextcore git hook --type post-commit

        # Generate to stdout (don't install)
        contextcore git hook --output -

        # Generate for specific project
        contextcore git hook --project my-project
    """
    import stat

    hook_content = f'''#!/bin/bash
# ContextCore git hook - auto-link commits to tasks
# Generated by: contextcore git hook --type {hook_type}

# Extract commit info
COMMIT_SHA=$(git rev-parse HEAD)
COMMIT_MSG=$(git log -1 --format=%B)
AUTHOR=$(git log -1 --format=%an)
REPO=$(basename "$(git remote get-url origin 2>/dev/null || echo 'unknown')" .git)

# Link commit to tasks
contextcore git link \\
    --commit "$COMMIT_SHA" \\
    --message "$COMMIT_MSG" \\
    --author "$AUTHOR" \\
    --repo "$REPO" \\
    --project "{project}"
'''

    # Determine output path
    if output == "-":
        click.echo(hook_content)
        return

    if output:
        hook_path = output
    else:
        # Find .git directory
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            click.echo("Error: Not in a git repository", err=True)
            sys.exit(1)

        git_dir = result.stdout.strip()
        hooks_dir = os.path.join(git_dir, "hooks")
        os.makedirs(hooks_dir, exist_ok=True)
        hook_path = os.path.join(hooks_dir, hook_type)

    # Write hook
    with open(hook_path, "w") as f:
        f.write(hook_content)

    # Make executable
    os.chmod(hook_path, os.stat(hook_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    click.echo(f"Git hook installed: {hook_path}")
    click.echo()
    click.echo("The hook will automatically link commits to tasks found in messages.")
    click.echo("Task patterns recognized:")
    click.echo("  - PROJ-123 (any uppercase letters + dash + numbers)")
    click.echo("  - 'fixes PROJ-123', 'closes PROJ-123' → marks as in_review")
    click.echo("  - #123 (GitHub issue numbers)")


@git.command("test")
@click.option("--message", "-m", required=True, help="Commit message to test")
def git_test(message: str):
    """Test task pattern matching on a commit message.

    \b
    Examples:
        contextcore git test --message "feat: implement auth [PROJ-123]"
        contextcore git test --message "fixes PROJ-456: token refresh bug"
    """
    task_ids = parse_task_refs(message)
    completion_ids = parse_completion_refs(message)

    click.echo(f"Message: {message}")
    click.echo()

    if task_ids:
        click.echo(f"Task references found: {', '.join(task_ids)}")
    else:
        click.echo("No task references found")

    if completion_ids:
        click.echo(f"Completion triggers: {', '.join(completion_ids)}")
        click.echo("  (These tasks would be moved to 'in_review')")


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


# =============================================================================
# SKILL MANAGEMENT
# =============================================================================


@main.group()
def skill():
    """Manage skill capabilities as OTel spans.

    Skills are stored as hierarchical spans:
    - skill: Parent span (manifest)
    - capability: Child spans (individual capabilities)

    Enables TraceQL-based capability discovery and token-efficient
    agent-to-agent communication.

    Example:
        contextcore skill emit --path /path/to/llm-formatter
        contextcore skill query --trigger "format"
        contextcore skill list
    """
    pass


@skill.command("emit")
@click.option("--path", "-p", required=True, help="Path to skill directory")
@click.option("--endpoint", envvar="OTEL_EXPORTER_OTLP_ENDPOINT", default="localhost:4317", help="OTLP endpoint")
def skill_emit(path: str, endpoint: str):
    """Emit a skill's capabilities to Tempo.

    Parses MANIFEST.yaml and capability files, then emits:
    1. Skill manifest as parent span
    2. Each capability as child span

    The emitted spans can be queried via TraceQL for capability discovery.

    Example:
        contextcore skill emit --path /path/to/llm-formatter
    """
    from contextcore.skill import SkillParser, SkillCapabilityEmitter
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    # Configure OTel
    resource = Resource.create({
        "service.name": "contextcore-skills",
        "service.version": "1.0.0",
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    try:
        # Parse skill
        parser = SkillParser()
        manifest, capabilities = parser.parse_skill_directory(path)

        click.echo(f"Parsed skill: {manifest.skill_id}")
        click.echo(f"  Type: {manifest.skill_type}")
        click.echo(f"  Capabilities: {len(capabilities)}")
        click.echo(f"  Total tokens: {manifest.total_tokens}")
        click.echo(f"  Compressed tokens: {manifest.compressed_tokens}")
        click.echo()

        # Emit to Tempo
        emitter = SkillCapabilityEmitter()
        trace_id, span_ids = emitter.emit_skill_with_capabilities(manifest, capabilities)

        click.echo(f"Emitted to Tempo:")
        click.echo(f"  Trace ID: {trace_id}")
        click.echo(f"  Span count: {len(span_ids) + 1}")  # +1 for manifest span
        click.echo()

        # Force flush
        provider.force_flush()

        click.echo("Capabilities emitted:")
        for cap in capabilities:
            compression = ((cap.token_budget - cap.summary_tokens) / cap.token_budget * 100) if cap.token_budget > 0 else 0
            click.echo(f"  - {cap.capability_id}: {cap.token_budget} -> {cap.summary_tokens} tokens ({compression:.0f}% reduction)")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error emitting skill: {e}", err=True)
        sys.exit(1)


@skill.command("query")
@click.option("--trigger", "-t", help="Find by trigger keyword")
@click.option("--category", "-c", type=click.Choice(["transform", "generate", "validate", "audit", "query", "action", "analyze"]), help="Filter by category")
@click.option("--budget", "-b", type=int, help="Max token budget")
@click.option("--skill-id", "-s", help="Filter by skill ID")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.option("--time-range", default="24h", help="Time range (e.g., 1h, 24h, 7d)")
def skill_query(
    trigger: Optional[str],
    category: Optional[str],
    budget: Optional[int],
    skill_id: Optional[str],
    tempo_url: str,
    output_format: str,
    time_range: str,
):
    """Query capabilities from Tempo.

    Find capabilities using various filters:
    - trigger: Match against routing keywords
    - category: Filter by operation type
    - budget: Maximum token cost
    - skill-id: Specific skill only

    Example:
        contextcore skill query --trigger "format"
        contextcore skill query --category transform --budget 500
        contextcore skill query --skill-id llm-formatter
    """
    from contextcore.skill import SkillCapabilityQuerier, CapabilityCategory

    querier = SkillCapabilityQuerier(tempo_url=tempo_url)

    # Build query
    cat = CapabilityCategory(category) if category else None
    capabilities = querier.query(
        skill_id=skill_id,
        category=cat,
        trigger=trigger,
        max_tokens=budget,
        time_range=time_range,
    )

    if not capabilities:
        click.echo("No capabilities found matching criteria.")
        click.echo("Note: Ensure skills have been emitted and Tempo is accessible.")
        return

    if output_format == "json":
        data = [
            {
                "skill_id": c.skill_id,
                "capability_id": c.capability_id,
                "category": c.category,
                "summary": c.summary,
                "token_budget": c.token_budget,
                "triggers": c.triggers,
            }
            for c in capabilities
        ]
        click.echo(json.dumps(data, indent=2))

    elif output_format == "yaml":
        data = [
            {
                "skill_id": c.skill_id,
                "capability_id": c.capability_id,
                "category": c.category,
                "summary": c.summary,
                "token_budget": c.token_budget,
                "triggers": c.triggers,
            }
            for c in capabilities
        ]
        click.echo(yaml.dump(data, default_flow_style=False))

    else:  # table
        click.echo(f"Found {len(capabilities)} capabilities:")
        click.echo()
        click.echo(f"{'Skill':<20} {'Capability':<25} {'Category':<12} {'Tokens':<8} {'Summary'}")
        click.echo("-" * 100)
        for c in capabilities:
            summary = c.summary[:40] + "..." if len(c.summary) > 40 else c.summary
            click.echo(f"{c.skill_id:<20} {c.capability_id:<25} {c.category:<12} {c.token_budget:<8} {summary}")


@skill.command("list")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--time-range", default="24h", help="Time range")
def skill_list(tempo_url: str, time_range: str):
    """List all skills in Tempo.

    Shows skill manifests with capability counts and token budgets.

    Example:
        contextcore skill list
    """
    from contextcore.skill import SkillManifestQuerier

    querier = SkillManifestQuerier(tempo_url=tempo_url)
    skills = querier.list_skills(time_range=time_range)

    if not skills:
        click.echo("No skills found in Tempo.")
        click.echo("Use 'contextcore skill emit' to emit skills first.")
        return

    click.echo(f"Found {len(skills)} skills:")
    click.echo()
    click.echo(f"{'Skill ID':<25} {'Type':<15} {'Capabilities':<12} {'Total Tokens':<12} {'Compressed'}")
    click.echo("-" * 80)
    for s in skills:
        click.echo(f"{s.skill_id:<25} {s.skill_type:<15} {len(s.capability_refs):<12} {s.total_tokens:<12} {s.compressed_tokens}")


@skill.command("routing")
@click.option("--skill-id", "-s", required=True, help="Skill ID")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--format", "output_format", type=click.Choice(["table", "yaml"]), default="table", help="Output format")
def skill_routing(skill_id: str, tempo_url: str, output_format: str):
    """Get routing table for a skill.

    Shows trigger keyword -> capability mapping for O(1) lookups.

    Example:
        contextcore skill routing --skill-id llm-formatter
    """
    from contextcore.skill import SkillCapabilityQuerier

    querier = SkillCapabilityQuerier(tempo_url=tempo_url)
    routing = querier.get_routing_table(skill_id)

    if not routing:
        click.echo(f"No routing table found for skill: {skill_id}")
        return

    if output_format == "yaml":
        click.echo(yaml.dump(routing, default_flow_style=False))
    else:
        click.echo(f"Routing table for {skill_id}:")
        click.echo()
        click.echo(f"{'Trigger':<25} {'Capability'}")
        click.echo("-" * 50)
        for trigger, cap_id in sorted(routing.items()):
            click.echo(f"{trigger:<25} {cap_id}")


@skill.command("compress")
@click.option("--path", "-p", required=True, help="Path to skill directory")
@click.option("--target-tokens", "-t", type=int, default=25000, help="Target token budget")
@click.option("--output", "-o", help="Output directory (defaults to skill directory)")
@click.option("--dry-run", is_flag=True, help="Show what would be done without writing")
def skill_compress(path: str, target_tokens: int, output: Optional[str], dry_run: bool):
    """Analyze and suggest compression for a skill.

    Applies summary+evidence pattern to reduce token usage:
    1. Extract summaries from capability descriptions
    2. Calculate potential token savings
    3. Show compression recommendations

    Example:
        contextcore skill compress --path /path/to/dev-tour-guide --target-tokens 25000
    """
    from contextcore.skill import SkillParser

    parser = SkillParser(compress=True)

    try:
        manifest, capabilities = parser.parse_skill_directory(path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Calculate stats
    total_full = manifest.total_tokens
    total_compressed = manifest.compressed_tokens

    click.echo(f"Skill: {manifest.skill_id}")
    click.echo(f"Source: {path}")
    click.echo()
    click.echo("Token Analysis:")
    click.echo(f"  Current total: {total_full:,} tokens")
    click.echo(f"  After summary compression: {total_compressed:,} tokens")
    click.echo(f"  Potential reduction: {total_full - total_compressed:,} tokens ({(total_full - total_compressed) / total_full * 100:.1f}%)")
    click.echo(f"  Target: {target_tokens:,} tokens")
    click.echo()

    if total_compressed <= target_tokens:
        click.echo(f"SUCCESS: Compressed size ({total_compressed:,}) meets target ({target_tokens:,})")
    else:
        click.echo(f"WARNING: Compressed size ({total_compressed:,}) still exceeds target ({target_tokens:,})")
        click.echo("Consider:")
        click.echo("  - Splitting into multiple skills")
        click.echo("  - Moving detailed content to external files")
        click.echo("  - Using more aggressive summarization")

    click.echo()
    click.echo("Per-Capability Analysis:")
    click.echo(f"{'Capability':<30} {'Full':<10} {'Summary':<10} {'Reduction'}")
    click.echo("-" * 65)

    for cap in sorted(capabilities, key=lambda c: c.token_budget, reverse=True):
        reduction = (cap.token_budget - cap.summary_tokens) / cap.token_budget * 100 if cap.token_budget > 0 else 0
        click.echo(f"{cap.capability_id:<30} {cap.token_budget:<10} {cap.summary_tokens:<10} {reduction:.0f}%")

    if dry_run:
        click.echo()
        click.echo("(Dry run - no files written)")


# =============================================================================
# INSIGHT MANAGEMENT (Agent Memory)
# =============================================================================


@main.group()
def insight():
    """Emit and query agent insights (persistent memory).

    Insights are stored as OTel spans enabling:
    - Cross-session memory (decisions persist)
    - Agent-to-agent communication
    - Queryable knowledge base

    Example:
        contextcore insight emit --type decision --summary "Chose X over Y"
        contextcore insight query --type lesson --project contextcore
    """
    pass


@insight.command("emit")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="contextcore", help="Project ID")
@click.option("--agent", "-a", envvar="CONTEXTCORE_AGENT", default="claude", help="Agent ID")
@click.option(
    "--type", "insight_type",
    type=click.Choice(["decision", "recommendation", "lesson", "blocker", "discovery", "analysis", "risk", "progress"]),
    required=True,
    help="Insight type"
)
@click.option("--summary", "-s", required=True, help="Brief summary of the insight")
@click.option("--confidence", "-c", type=float, default=0.9, help="Confidence score (0.0-1.0)")
@click.option("--rationale", "-r", help="Reasoning behind the insight")
@click.option("--category", help="Category for lessons (e.g., testing, architecture)")
@click.option("--applies-to", multiple=True, help="File paths this applies to (can specify multiple)")
@click.option("--local-storage", envvar="CONTEXTCORE_LOCAL_STORAGE", help="Local storage path (for dev without Tempo)")
def insight_emit(
    project: str,
    agent: str,
    insight_type: str,
    summary: str,
    confidence: float,
    rationale: Optional[str],
    category: Optional[str],
    applies_to: tuple,
    local_storage: Optional[str],
):
    """Emit an insight for future sessions.

    Insights are stored as OTel spans in Tempo (and optionally local JSON).
    Future sessions can query these to maintain memory across conversations.

    \b
    Examples:
        # Emit a decision
        contextcore insight emit --type decision \\
            --summary "Selected event-driven architecture" \\
            --rationale "Lower coupling, better scalability"

        # Emit a lesson learned
        contextcore insight emit --type lesson \\
            --summary "Always mock OTLP exporter in unit tests" \\
            --category testing \\
            --applies-to "src/contextcore/tracker.py"

        # Development mode (save locally without Tempo)
        contextcore insight emit --type decision \\
            --summary "Using Pydantic for validation" \\
            --local-storage ~/.contextcore/insights
    """
    from contextcore.agent import InsightEmitter

    emitter = InsightEmitter(
        project_id=project,
        agent_id=agent,
        local_storage_path=local_storage,
    )

    # Map type string to method
    emit_methods = {
        "decision": emitter.emit_decision,
        "recommendation": emitter.emit_recommendation,
        "lesson": emitter.emit_lesson,
        "blocker": emitter.emit_blocker,
        "discovery": emitter.emit_discovery,
        "progress": emitter.emit_progress,
    }

    # Build kwargs
    kwargs = {"rationale": rationale} if rationale else {}

    if insight_type == "lesson":
        if not category:
            category = "general"
        insight = emitter.emit_lesson(
            summary=summary,
            category=category,
            confidence=confidence,
            applies_to=list(applies_to) if applies_to else None,
            **kwargs,
        )
    elif insight_type in emit_methods:
        insight = emit_methods[insight_type](
            summary=summary,
            confidence=confidence,
            **kwargs,
        )
    else:
        # Generic emit for types without specific methods
        from contextcore.agent.insights import InsightType
        insight = emitter.emit(
            InsightType(insight_type),
            summary=summary,
            confidence=confidence,
            applies_to=list(applies_to) if applies_to else None,
            category=category,
            **kwargs,
        )

    click.echo(f"Emitted {insight_type}: {insight.id}")
    click.echo(f"  Summary: {summary}")
    click.echo(f"  Confidence: {confidence}")
    click.echo(f"  Trace ID: {insight.trace_id}")
    if applies_to:
        click.echo(f"  Applies to: {', '.join(applies_to)}")
    if local_storage:
        click.echo(f"  Saved locally: {local_storage}/{project}_insights.json")


@insight.command("query")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", help="Filter by project")
@click.option("--agent", "-a", help="Filter by agent ID")
@click.option(
    "--type", "insight_type",
    type=click.Choice(["decision", "recommendation", "lesson", "blocker", "discovery", "analysis", "risk", "progress"]),
    help="Filter by insight type"
)
@click.option("--category", help="Filter by category (for lessons)")
@click.option("--applies-to", help="Filter by file path (partial match)")
@click.option("--min-confidence", type=float, help="Minimum confidence score")
@click.option("--time-range", "-t", default="30d", help="Time range (e.g., 1h, 24h, 7d, 30d)")
@click.option("--limit", "-l", type=int, default=20, help="Maximum results")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--local-storage", envvar="CONTEXTCORE_LOCAL_STORAGE", help="Local storage path (for dev without Tempo)")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
def insight_query(
    project: Optional[str],
    agent: Optional[str],
    insight_type: Optional[str],
    category: Optional[str],
    applies_to: Optional[str],
    min_confidence: Optional[float],
    time_range: str,
    limit: int,
    tempo_url: str,
    local_storage: Optional[str],
    output_format: str,
):
    """Query insights from Tempo or local storage.

    Retrieve insights emitted by agents in previous sessions.
    Useful for maintaining context across conversations.

    \b
    Examples:
        # Get recent decisions
        contextcore insight query --type decision --time-range 7d

        # Get lessons for a specific file
        contextcore insight query --type lesson --applies-to "src/contextcore/tracker.py"

        # Get all high-confidence insights
        contextcore insight query --min-confidence 0.9

        # Development mode (query local storage)
        contextcore insight query --type lesson --local-storage ~/.contextcore/insights
    """
    from contextcore.agent import InsightQuerier

    querier = InsightQuerier(
        tempo_url=tempo_url if not local_storage else None,
        local_storage_path=local_storage,
    )

    insights = querier.query(
        project_id=project,
        insight_type=insight_type,
        agent_id=agent,
        min_confidence=min_confidence,
        time_range=time_range,
        limit=limit,
        applies_to=applies_to,
        category=category,
    )

    if not insights:
        click.echo("No insights found matching criteria.")
        if not local_storage:
            click.echo("Note: Ensure Tempo is accessible or use --local-storage for development.")
        return

    if output_format == "json":
        data = [
            {
                "id": i.id,
                "type": i.type.value,
                "summary": i.summary,
                "confidence": i.confidence,
                "project_id": i.project_id,
                "agent_id": i.agent_id,
                "rationale": i.rationale,
                "applies_to": i.applies_to,
                "category": i.category,
                "trace_id": i.trace_id,
                "timestamp": i.timestamp.isoformat() if i.timestamp else None,
            }
            for i in insights
        ]
        click.echo(json.dumps(data, indent=2))

    elif output_format == "yaml":
        data = [
            {
                "id": i.id,
                "type": i.type.value,
                "summary": i.summary,
                "confidence": i.confidence,
                "project_id": i.project_id,
                "agent_id": i.agent_id,
                "rationale": i.rationale,
                "applies_to": i.applies_to,
                "category": i.category,
            }
            for i in insights
        ]
        click.echo(yaml.dump(data, default_flow_style=False))

    else:  # table
        click.echo(f"Found {len(insights)} insights:")
        click.echo()
        click.echo(f"{'Type':<12} {'Confidence':<10} {'Summary':<50} {'Agent'}")
        click.echo("-" * 90)
        for i in insights:
            summary = i.summary[:47] + "..." if len(i.summary) > 50 else i.summary
            click.echo(f"{i.type.value:<12} {i.confidence:<10.2f} {summary:<50} {i.agent_id}")


# =============================================================================
# KNOWLEDGE MANAGEMENT (Markdown Documents to Telemetry)
# =============================================================================


@main.group()
def knowledge():
    """Convert markdown knowledge documents (SKILL.md) to queryable telemetry.

    Parses markdown files and emits:
    - Skill manifest as parent span
    - Major sections as capability spans
    - Important subsections as additional capability spans

    Enables both TraceQL queries (agents) and Grafana dashboards (humans).

    Example:
        contextcore knowledge emit --path ~/.claude/skills/dev-tour-guide
        contextcore knowledge query --category infrastructure
    """
    pass


@knowledge.command("emit")
@click.option("--path", "-p", required=True, help="Path to skill directory or SKILL.md file")
@click.option("--skill-id", help="Override skill ID (default: directory name)")
@click.option("--endpoint", envvar="OTEL_EXPORTER_OTLP_ENDPOINT", default="localhost:4317", help="OTLP endpoint")
@click.option("--dry-run", is_flag=True, help="Preview without emitting")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
def knowledge_emit(
    path: str,
    skill_id: Optional[str],
    endpoint: str,
    dry_run: bool,
    output_format: str,
):
    """Parse markdown SKILL.md and emit as queryable capabilities.

    Uses hybrid extraction strategy:
    - All H2 sections become capabilities
    - Important H3 subsections also become capabilities

    \b
    Examples:
        # Emit dev-tour-guide
        contextcore knowledge emit --path ~/.claude/skills/dev-tour-guide

        # Preview what would be emitted
        contextcore knowledge emit --path ~/.claude/skills/dev-tour-guide --dry-run

        # Output as JSON for inspection
        contextcore knowledge emit --path ~/.claude/skills/dev-tour-guide --dry-run --format json
    """
    from pathlib import Path
    from contextcore.knowledge import MarkdownCapabilityParser, KnowledgeEmitter

    try:
        parser = MarkdownCapabilityParser(Path(path).expanduser())
        manifest, capabilities = parser.parse()

        if skill_id:
            manifest.skill_id = skill_id

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Parsed: {manifest.skill_id}")
    click.echo(f"  Source: {manifest.source_file}")
    click.echo(f"  Lines: {manifest.total_lines}")
    click.echo(f"  H2 Sections: {manifest.section_count}")
    click.echo(f"  Subsection Capabilities: {manifest.subsection_count}")
    click.echo(f"  Total Capabilities: {len(capabilities)}")
    click.echo()
    click.echo(f"Token Analysis:")
    click.echo(f"  Full content: {manifest.total_tokens:,} tokens")
    click.echo(f"  After compression: {manifest.compressed_tokens:,} tokens")
    compression = (manifest.total_tokens - manifest.compressed_tokens) / manifest.total_tokens * 100 if manifest.total_tokens > 0 else 0
    click.echo(f"  Compression: {compression:.1f}%")
    click.echo()

    if output_format == "json":
        data = [
            {
                "capability_id": c.capability_id,
                "name": c.capability_name,
                "knowledge_category": c.knowledge_category,
                "source_section": c.source_section,
                "source_subsection": c.source_subsection,
                "line_range": c.line_range,
                "summary": c.summary,
                "triggers": c.triggers[:10],  # Limit for display
                "token_budget": c.token_budget,
                "has_code": c.has_code,
                "has_tables": c.has_tables,
                "tools": c.tools,
                "ports": c.ports,
                "env_vars": c.env_vars[:5],  # Limit for display
            }
            for c in capabilities
        ]
        click.echo(json.dumps(data, indent=2))
        return

    elif output_format == "yaml":
        data = [
            {
                "capability_id": c.capability_id,
                "name": c.capability_name,
                "knowledge_category": c.knowledge_category,
                "source_section": c.source_section,
                "line_range": c.line_range,
                "summary": c.summary,
                "triggers": c.triggers[:10],
                "token_budget": c.token_budget,
            }
            for c in capabilities
        ]
        click.echo(yaml.dump(data, default_flow_style=False))
        return

    # Table format
    click.echo("Capabilities extracted:")
    click.echo()
    click.echo(f"{'ID':<35} {'Category':<15} {'Lines':<12} {'Tokens':<8} {'Code':<5} {'Tables'}")
    click.echo("-" * 90)

    for c in capabilities:
        has_code = "Yes" if c.has_code else ""
        has_tables = "Yes" if c.has_tables else ""
        click.echo(f"{c.capability_id:<35} {c.knowledge_category:<15} {c.line_range:<12} {c.token_budget:<8} {has_code:<5} {has_tables}")

    if dry_run:
        click.echo()
        click.echo("(Dry run - no spans emitted)")
        return

    # Emit to Tempo
    click.echo()
    click.echo(f"Emitting to {endpoint}...")

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    # Configure OTel
    resource = Resource.create({
        "service.name": "contextcore-knowledge",
        "service.version": "1.0.0",
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    try:
        emitter = KnowledgeEmitter(agent_id=manifest.skill_id)
        trace_id, span_ids = emitter.emit_knowledge_with_capabilities(manifest, capabilities)

        # Force flush
        provider.force_flush()

        click.echo()
        click.echo(f"Emitted {len(capabilities)} capabilities")
        click.echo(f"  Trace ID: {trace_id}")
        click.echo()
        click.echo("TraceQL queries:")
        click.echo(f"  All capabilities: {{ skill.id = \"{manifest.skill_id}\" && name =~ \"capability:.*\" }}")
        click.echo(f"  By category: {{ knowledge.category = \"infrastructure\" && skill.id = \"{manifest.skill_id}\" }}")

    except Exception as e:
        click.echo(f"Error emitting: {e}", err=True)
        sys.exit(1)


@knowledge.command("query")
@click.option("--skill-id", "-s", help="Filter by skill ID")
@click.option("--category", "-c", type=click.Choice(["infrastructure", "workflow", "sdk", "reference", "security", "configuration"]), help="Filter by knowledge category")
@click.option("--trigger", "-t", help="Find by trigger keyword")
@click.option("--has-code", is_flag=True, help="Only capabilities with code examples")
@click.option("--port", help="Find capabilities mentioning a specific port")
@click.option("--tool", help="Find capabilities mentioning a CLI tool")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--time-range", default="24h", help="Time range (e.g., 1h, 24h, 7d)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.option("--skip-rbac", is_flag=True, help="Skip RBAC filtering (requires admin role)")
def knowledge_query(
    skill_id: Optional[str],
    category: Optional[str],
    trigger: Optional[str],
    has_code: bool,
    port: Optional[str],
    tool: Optional[str],
    tempo_url: str,
    time_range: str,
    output_format: str,
    skip_rbac: bool,
):
    """Query knowledge capabilities from Tempo with RBAC filtering.

    Find knowledge documents using various filters. Results are filtered
    by your RBAC permissions - sensitive categories (e.g., security)
    require the security-reader role.

    \b
    Examples:
        # Find all infrastructure documentation
        contextcore knowledge query --category infrastructure

        # Find by trigger keyword
        contextcore knowledge query --trigger grafana

        # Find capabilities with code examples
        contextcore knowledge query --has-code

        # Find by port
        contextcore knowledge query --port 3000

        # Find by CLI tool
        contextcore knowledge query --tool "contextcore task"

        # Query security docs (requires security-reader role)
        contextcore knowledge query --category security
    """
    import requests
    from contextcore.rbac import (
        get_enforcer,
        PrincipalResolver,
        Resource,
        ResourceType,
        Action,
        PolicyDecision,
        AccessDeniedError,
    )
    from contextcore.knowledge.models import SENSITIVE_CATEGORIES, KnowledgeCategory

    # Resolve principal for RBAC
    principal = PrincipalResolver.from_cli_context()
    enforcer = get_enforcer()

    # If querying a specific sensitive category, check permission upfront
    if category and not skip_rbac:
        try:
            cat_enum = KnowledgeCategory(category)
            is_sensitive = cat_enum in SENSITIVE_CATEGORIES
        except ValueError:
            is_sensitive = False

        if is_sensitive:
            resource = Resource(
                resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                resource_id=category,
                sensitive=True,
            )
            decision = enforcer.check_access(
                principal.id,
                principal.principal_type,
                resource,
                Action.QUERY,
            )
            if decision.decision != PolicyDecision.ALLOW:
                click.echo(click.style(
                    f"Access denied: You don't have permission to query '{category}' knowledge.",
                    fg="red"
                ))
                click.echo(f"Reason: {decision.denial_reason}")
                click.echo(f"Hint: Request the 'security-reader' role to access security documentation.")
                sys.exit(1)

    # If skip_rbac is requested, verify admin role
    if skip_rbac:
        admin_resource = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="*",
            sensitive=True,
        )
        decision = enforcer.check_access(
            principal.id,
            principal.principal_type,
            admin_resource,
            Action.QUERY,
        )
        if decision.decision != PolicyDecision.ALLOW:
            click.echo(click.style(
                "Error: --skip-rbac requires admin role",
                fg="red"
            ))
            sys.exit(1)

    # Build TraceQL query
    conditions = ['name =~ "capability:.*"']

    if skill_id:
        conditions.append(f'skill.id = "{skill_id}"')
    if category:
        conditions.append(f'knowledge.category = "{category}"')
    if trigger:
        conditions.append(f'capability.triggers =~ ".*{trigger}.*"')
    if has_code:
        conditions.append('capability.has_code = true')
    if port:
        conditions.append(f'capability.ports =~ ".*{port}.*"')
    if tool:
        conditions.append(f'capability.tools =~ ".*{tool}.*"')

    query = "{ " + " && ".join(conditions) + " }"

    click.echo(f"TraceQL: {query}")
    click.echo()

    # Query Tempo
    try:
        response = requests.get(
            f"{tempo_url}/api/search",
            params={"q": query, "limit": 50},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        click.echo(f"Error querying Tempo: {e}", err=True)
        click.echo("Note: Ensure Tempo is accessible at the specified URL.")
        sys.exit(1)

    traces = data.get("traces", [])
    if not traces:
        click.echo("No capabilities found matching criteria.")
        return

    # RBAC filtering on results (when not querying a specific category)
    filtered_count = 0
    if not skip_rbac and not category:
        # Filter out sensitive capabilities the user can't access
        allowed_traces = []
        for t in traces:
            # Extract knowledge.category from span attributes if available
            span_set = t.get("spanSet", {}) or t.get("spanSets", [{}])[0] if t.get("spanSets") else {}
            spans = span_set.get("spans", []) if isinstance(span_set, dict) else []

            # Check if this trace contains sensitive content
            trace_category = None
            for span in spans:
                attrs = span.get("attributes", [])
                for attr in attrs:
                    if attr.get("key") == "knowledge.category":
                        trace_category = attr.get("value", {}).get("stringValue", "")
                        break

            # If we found a category, check permission
            if trace_category:
                try:
                    cat_enum = KnowledgeCategory(trace_category)
                    is_sensitive = cat_enum in SENSITIVE_CATEGORIES
                except ValueError:
                    is_sensitive = False

                if is_sensitive:
                    resource = Resource(
                        resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                        resource_id=trace_category,
                        sensitive=True,
                    )
                    decision = enforcer.check_access(
                        principal.id,
                        principal.principal_type,
                        resource,
                        Action.READ,
                    )
                    if decision.decision != PolicyDecision.ALLOW:
                        filtered_count += 1
                        continue

            allowed_traces.append(t)

        traces = allowed_traces

    if output_format == "json":
        result = {"traces": traces, "filtered_by_rbac": filtered_count}
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(f"Found {len(traces)} matching capabilities:")
    if filtered_count > 0:
        click.echo(click.style(
            f"  ({filtered_count} results filtered by RBAC permissions)",
            fg="yellow"
        ))
    click.echo()
    click.echo(f"{'Trace ID':<35} {'Service'}")
    click.echo("-" * 50)

    for t in traces:
        trace_id = t.get("traceID", "")
        root_service = t.get("rootServiceName", "")
        click.echo(f"{trace_id:<35} {root_service}")


@insight.command("lessons")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="contextcore", help="Project ID")
@click.option("--applies-to", help="Filter by file path (partial match)")
@click.option("--category", help="Filter by category")
@click.option("--time-range", "-t", default="30d", help="Time range")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--local-storage", envvar="CONTEXTCORE_LOCAL_STORAGE", help="Local storage path")
def insight_lessons(
    project: str,
    applies_to: Optional[str],
    category: Optional[str],
    time_range: str,
    tempo_url: str,
    local_storage: Optional[str],
):
    """List lessons learned for a project.

    Convenience command for querying LESSON type insights.

    \b
    Examples:
        # All lessons for the project
        contextcore insight lessons --project contextcore

        # Lessons for a specific file
        contextcore insight lessons --applies-to "src/contextcore/tracker.py"

        # Lessons in a specific category
        contextcore insight lessons --category testing
    """
    from contextcore.agent import InsightQuerier

    querier = InsightQuerier(
        tempo_url=tempo_url if not local_storage else None,
        local_storage_path=local_storage,
    )

    lessons = querier.get_lessons(
        project_id=project,
        applies_to=applies_to,
        category=category,
        time_range=time_range,
    )

    if not lessons:
        click.echo("No lessons found.")
        return

    click.echo(f"Lessons Learned ({len(lessons)} total):")
    click.echo()

    for i, lesson in enumerate(lessons, 1):
        click.echo(f"{i}. {lesson.summary}")
        if lesson.category:
            click.echo(f"   Category: {lesson.category}")
        if lesson.applies_to:
            click.echo(f"   Applies to: {', '.join(lesson.applies_to)}")
        click.echo(f"   Confidence: {lesson.confidence:.0%}")
        click.echo()


# =============================================================================
# RBAC Commands
# =============================================================================


@main.group()
def rbac():
    """Manage RBAC roles and permissions for ContextCore Tour Guide."""
    pass


@rbac.command("list-roles")
def rbac_list_roles():
    """List all available roles."""
    from contextcore.rbac import get_rbac_store, BUILT_IN_ROLE_IDS

    store = get_rbac_store()
    roles = store.list_roles()

    if not roles:
        click.echo("No roles found.")
        return

    click.echo("Available Roles:")
    click.echo()
    click.echo(f"{'ID':<20} {'Name':<25} {'Built-in':<10} Permissions")
    click.echo("-" * 80)

    for role in sorted(roles, key=lambda r: (not r.built_in, r.id)):
        builtin = "Yes" if role.id in BUILT_IN_ROLE_IDS else "No"
        perm_count = len(role.permissions)
        inherits = f" (inherits: {', '.join(role.inherits_from)})" if role.inherits_from else ""
        click.echo(f"{role.id:<20} {role.name:<25} {builtin:<10} {perm_count}{inherits}")


@rbac.command("show-role")
@click.argument("role_id")
def rbac_show_role(role_id: str):
    """Show details of a specific role."""
    from contextcore.rbac import get_rbac_store

    store = get_rbac_store()
    role = store.get_role(role_id)

    if not role:
        raise click.ClickException(f"Role not found: {role_id}")

    click.echo(f"Role: {role.name} ({role.id})")
    click.echo(f"Description: {role.description}")
    click.echo(f"Built-in: {'Yes' if role.built_in else 'No'}")

    if role.inherits_from:
        click.echo(f"Inherits from: {', '.join(role.inherits_from)}")

    if role.assignable_to:
        click.echo(f"Assignable to: {', '.join(role.assignable_to)}")

    click.echo()
    click.echo("Permissions:")
    for perm in role.permissions:
        sensitive = " [SENSITIVE]" if perm.resource.sensitive else ""
        actions = ", ".join(perm.actions)
        click.echo(f"  - {perm.id}: {perm.resource.resource_type}/{perm.resource.resource_id}")
        click.echo(f"    Actions: {actions}{sensitive}")


@rbac.command("grant")
@click.option("--principal", "-p", required=True, help="Principal ID")
@click.option(
    "--principal-type", "-t",
    type=click.Choice(["agent", "user", "team", "service_account"]),
    default="user",
    help="Type of principal"
)
@click.option("--role", "-r", required=True, help="Role ID to grant")
@click.option("--project-scope", help="Limit to specific project")
@click.option("--created-by", default="cli", help="Who is granting this role")
def rbac_grant(
    principal: str,
    principal_type: str,
    role: str,
    project_scope: Optional[str],
    created_by: str,
):
    """Grant a role to a principal."""
    from contextcore.rbac import (
        get_rbac_store,
        RoleBinding,
        PrincipalType,
    )
    import uuid

    store = get_rbac_store()

    # Verify role exists
    if not store.get_role(role):
        raise click.ClickException(f"Role not found: {role}")

    # Create binding
    binding_id = f"{principal}-{role}-{uuid.uuid4().hex[:8]}"
    binding = RoleBinding(
        id=binding_id,
        principal_id=principal,
        principal_type=PrincipalType(principal_type),
        role_id=role,
        project_scope=project_scope,
        created_by=created_by,
    )

    store.save_binding(binding)
    click.echo(f"Granted role '{role}' to {principal_type} '{principal}'")
    if project_scope:
        click.echo(f"  Scoped to project: {project_scope}")


@rbac.command("revoke")
@click.option("--principal", "-p", required=True, help="Principal ID")
@click.option("--role", "-r", required=True, help="Role ID to revoke")
def rbac_revoke(principal: str, role: str):
    """Revoke a role from a principal."""
    from contextcore.rbac import get_rbac_store

    store = get_rbac_store()
    bindings = store.list_bindings(principal_id=principal, role_id=role)

    if not bindings:
        raise click.ClickException(f"No binding found for {principal} with role {role}")

    for binding in bindings:
        store.delete_binding(binding.id)
        click.echo(f"Revoked role '{role}' from '{principal}' (binding: {binding.id})")


@rbac.command("list-bindings")
@click.option("--principal", "-p", help="Filter by principal ID")
@click.option("--role", "-r", help="Filter by role ID")
def rbac_list_bindings(principal: Optional[str], role: Optional[str]):
    """List role bindings."""
    from contextcore.rbac import get_rbac_store

    store = get_rbac_store()
    bindings = store.list_bindings(principal_id=principal, role_id=role)

    if not bindings:
        click.echo("No bindings found.")
        return

    click.echo("Role Bindings:")
    click.echo()
    click.echo(f"{'Principal':<25} {'Type':<15} {'Role':<20} {'Scope':<15}")
    click.echo("-" * 80)

    for b in bindings:
        scope = b.project_scope or "(all)"
        click.echo(f"{b.principal_id:<25} {b.principal_type:<15} {b.role_id:<20} {scope:<15}")


@rbac.command("check")
@click.option("--principal", "-p", required=True, help="Principal ID")
@click.option(
    "--principal-type", "-t",
    type=click.Choice(["agent", "user", "team", "service_account"]),
    default="user",
)
@click.option("--resource", "-r", required=True, help="Resource (type/id, e.g., knowledge_category/security)")
@click.option("--action", "-a", required=True, help="Action (read, write, query, emit)")
@click.option("--project-scope", help="Project scope")
def rbac_check(
    principal: str,
    principal_type: str,
    resource: str,
    action: str,
    project_scope: Optional[str],
):
    """Check if a principal has access to a resource."""
    from contextcore.rbac import (
        get_enforcer,
        Resource,
        ResourceType,
        Action,
        PrincipalType,
        PolicyDecision,
    )
    from contextcore.knowledge.models import KnowledgeCategory

    # Parse resource
    if "/" in resource:
        res_type, res_id = resource.split("/", 1)
    else:
        raise click.ClickException("Resource must be in format: type/id")

    # Determine if sensitive
    sensitive = (
        res_type == "knowledge_category" and
        res_id.lower() == "security"
    )

    resource_obj = Resource(
        resource_type=ResourceType(res_type),
        resource_id=res_id,
        sensitive=sensitive,
        project_scope=project_scope,
    )

    enforcer = get_enforcer()
    decision = enforcer.check_access(
        principal_id=principal,
        principal_type=PrincipalType(principal_type),
        resource=resource_obj,
        action=Action(action),
        project_scope=project_scope,
    )

    if decision.decision == PolicyDecision.ALLOW:
        click.echo(click.style("ALLOWED", fg="green"))
        click.echo(f"  Matched role: {decision.matched_role}")
        click.echo(f"  Matched permission: {decision.matched_permission}")
    else:
        click.echo(click.style("DENIED", fg="red"))
        click.echo(f"  Reason: {decision.denial_reason}")


@rbac.command("whoami")
def rbac_whoami():
    """Show the current principal identity."""
    from contextcore.rbac import PrincipalResolver

    principal = PrincipalResolver.from_cli_context()

    click.echo(f"Principal ID: {principal.id}")
    click.echo(f"Type: {principal.principal_type}")
    click.echo(f"Display Name: {principal.display_name}")

    if principal.agent_id:
        click.echo(f"Agent ID: {principal.agent_id}")
    if principal.email:
        click.echo(f"Email: {principal.email}")


# =============================================================================
# Value Command Group
# =============================================================================

@main.group()
def value():
    """Convert value-focused skill documents to queryable telemetry.

    Parses value-focused skills (like capability-value-promoter) and emits:
    - Value manifest as parent span
    - Value capabilities with persona, pain point, benefit attributes
    - Cross-links to technical capabilities

    TraceQL query examples:
        { value.persona = "developer" }
        { value.type = "direct" }
        { value.pain_point =~ ".*time.*" }
        { value.related_skills =~ ".*dev-tour-guide.*" }
    """
    pass


@value.command("emit")
@click.option("--path", "-p", required=True, help="Path to skill directory or SKILL.md file")
@click.option("--skill-id", help="Override skill ID (default: directory name)")
@click.option("--endpoint", envvar="OTEL_EXPORTER_OTLP_ENDPOINT", default="localhost:4317", help="OTLP endpoint")
@click.option("--dry-run", is_flag=True, help="Preview without emitting")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
def value_emit(
    path: str,
    skill_id: Optional[str],
    endpoint: str,
    dry_run: bool,
    output_format: str,
):
    """Parse and emit a value-focused skill as OTel spans.

    Example:
        contextcore value emit -p ~/.claude/skills/capability-value-promoter
        contextcore value emit -p ./value-skill/SKILL.md --dry-run
    """
    from pathlib import Path as PathLib
    from contextcore.value import ValueCapabilityParser, ValueEmitter

    skill_path = PathLib(path).expanduser()

    try:
        parser = ValueCapabilityParser(skill_path)
        manifest, capabilities = parser.parse()

        if skill_id:
            manifest.skill_id = skill_id

    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Parse error: {e}")

    if output_format == "json":
        output = {
            "manifest": manifest.model_dump(mode="json"),
            "capabilities": [c.model_dump(mode="json") for c in capabilities],
        }
        click.echo(json.dumps(output, indent=2))
        return

    if output_format == "yaml":
        output = {
            "manifest": manifest.model_dump(mode="json"),
            "capabilities": [c.model_dump(mode="json") for c in capabilities],
        }
        click.echo(yaml.dump(output, default_flow_style=False))
        return

    # Table output
    click.echo(click.style(f"\n=== Value Manifest: {manifest.skill_id} ===", fg="cyan", bold=True))
    click.echo(f"Source: {manifest.source_file}")
    click.echo(f"Total capabilities: {len(capabilities)}")
    click.echo(f"Personas covered: {', '.join(manifest.personas_covered)}")
    click.echo(f"Channels supported: {', '.join(manifest.channels_supported)}")
    if manifest.related_technical_skills:
        click.echo(f"Related skills: {', '.join(manifest.related_technical_skills)}")
    click.echo(f"Total tokens: {manifest.total_tokens}")
    click.echo(f"Compressed tokens: {manifest.compressed_tokens}")

    click.echo(click.style(f"\n=== Value Capabilities ({len(capabilities)}) ===", fg="cyan", bold=True))
    for cap in capabilities:
        click.echo(f"\n  {click.style(cap.capability_id, fg='green')}")
        click.echo(f"    Name: {cap.capability_name}")
        click.echo(f"    Category: {cap.knowledge_category}")
        click.echo(f"    Value type: {click.style(cap.value.value_type, fg='yellow')}")
        click.echo(f"    Personas: {', '.join(cap.value.personas)}")
        click.echo(f"    Pain point: {cap.value.pain_point[:80]}...")
        click.echo(f"    Benefit: {cap.value.benefit[:80]}...")
        click.echo(f"    Channels: {', '.join(cap.value.channels)}")
        if cap.value.time_savings:
            click.echo(f"    Time savings: {cap.value.time_savings}")
        if cap.related_skills:
            click.echo(f"    Related skills: {', '.join(cap.related_skills)}")

    if dry_run:
        click.echo(click.style("\n[DRY RUN] No spans emitted", fg="yellow"))
        return

    # Emit to Tempo
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider = TracerProvider()
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        emitter = ValueEmitter(agent_id=f"cli:{manifest.skill_id}")
        trace_id, span_ids = emitter.emit_value_with_capabilities(manifest, capabilities)

        click.echo(click.style(f"\nEmitted to {endpoint}", fg="green", bold=True))
        click.echo(f"  Trace ID: {trace_id}")
        click.echo(f"  Span count: {len(span_ids)}")

    except Exception as e:
        raise click.ClickException(f"Emit error: {e}")


@value.command("query")
@click.option("--skill-id", "-s", help="Filter by skill ID")
@click.option("--persona", "-p", type=click.Choice(["developer", "operator", "architect", "creator", "designer", "manager", "executive", "product", "security", "data", "any"]), help="Filter by persona")
@click.option("--value-type", "-v", type=click.Choice(["direct", "indirect", "ripple"]), help="Filter by value type")
@click.option("--channel", "-c", type=click.Choice(["slack", "email", "docs", "in_app", "social", "blog", "press", "video", "alert", "changelog", "meeting"]), help="Filter by channel")
@click.option("--pain-point", help="Search pain point text (partial match)")
@click.option("--benefit", help="Search benefit text (partial match)")
@click.option("--related-skill", help="Find capabilities related to a technical skill")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--time-range", default="24h", help="Time range (e.g., 1h, 24h, 7d)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
def value_query(
    skill_id: Optional[str],
    persona: Optional[str],
    value_type: Optional[str],
    channel: Optional[str],
    pain_point: Optional[str],
    benefit: Optional[str],
    related_skill: Optional[str],
    tempo_url: str,
    time_range: str,
    output_format: str,
):
    """Query value capabilities from Tempo.

    Examples:
        # Find capabilities for developers
        contextcore value query --persona developer

        # Find direct value with time savings
        contextcore value query --value-type direct

        # Find capabilities related to dev-tour-guide
        contextcore value query --related-skill dev-tour-guide

        # Find capabilities that mention "time" in pain point
        contextcore value query --pain-point time
    """
    import requests

    # Build TraceQL query
    conditions = ['name =~ "value_capability:.*"']

    if skill_id:
        conditions.append(f'skill.id = "{skill_id}"')
    if persona:
        conditions.append(f'value.persona = "{persona}"')
    if value_type:
        conditions.append(f'value.type = "{value_type}"')
    if channel:
        conditions.append(f'value.channels =~ ".*{channel}.*"')
    if pain_point:
        conditions.append(f'value.pain_point =~ ".*{pain_point}.*"')
    if benefit:
        conditions.append(f'value.benefit =~ ".*{benefit}.*"')
    if related_skill:
        conditions.append(f'value.related_skills =~ ".*{related_skill}.*"')

    traceql = "{ " + " && ".join(conditions) + " }"

    click.echo(click.style(f"TraceQL: {traceql}", fg="cyan"))

    # Parse time range
    time_map = {"h": 3600, "d": 86400, "w": 604800, "m": 2592000}
    time_unit = time_range[-1]
    time_value = int(time_range[:-1])
    seconds = time_value * time_map.get(time_unit, 3600)

    import time as time_module
    end_ns = int(time_module.time() * 1e9)
    start_ns = end_ns - (seconds * int(1e9))

    # Query Tempo
    url = f"{tempo_url}/api/search"
    params = {
        "q": traceql,
        "start": start_ns,
        "end": end_ns,
        "limit": 100,
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        raise click.ClickException(f"Query failed: {e}")

    traces = data.get("traces", [])

    if output_format == "json":
        click.echo(json.dumps(data, indent=2))
        return

    if not traces:
        click.echo(click.style("No matching value capabilities found", fg="yellow"))
        return

    click.echo(click.style(f"\nFound {len(traces)} trace(s)", fg="green", bold=True))

    # Extract spans from traces
    for trace in traces:
        trace_id = trace.get("traceID", "unknown")
        click.echo(f"\n{click.style('Trace:', fg='cyan')} {trace_id}")

        # Get trace details
        detail_url = f"{tempo_url}/api/traces/{trace_id}"
        try:
            detail_response = requests.get(detail_url, timeout=30)
            detail_response.raise_for_status()
            trace_data = detail_response.json()

            for batch in trace_data.get("batches", []):
                for span in batch.get("scopeSpans", []):
                    for s in span.get("spans", []):
                        name = s.get("name", "")
                        if not name.startswith("value_capability:"):
                            continue

                        attrs = {}
                        for attr in s.get("attributes", []):
                            key = attr.get("key", "")
                            val = attr.get("value", {})
                            # Extract value from OTLP attribute structure
                            if "stringValue" in val:
                                attrs[key] = val["stringValue"]
                            elif "intValue" in val:
                                attrs[key] = val["intValue"]
                            elif "doubleValue" in val:
                                attrs[key] = val["doubleValue"]
                            elif "boolValue" in val:
                                attrs[key] = val["boolValue"]

                        cap_id = attrs.get("capability.id", name.replace("value_capability:", ""))
                        click.echo(f"\n  {click.style(cap_id, fg='green')}")
                        click.echo(f"    Name: {attrs.get('capability.name', 'N/A')}")
                        click.echo(f"    Value type: {click.style(attrs.get('value.type', 'N/A'), fg='yellow')}")
                        click.echo(f"    Persona: {attrs.get('value.persona', 'N/A')}")
                        click.echo(f"    Pain point: {attrs.get('value.pain_point', 'N/A')[:80]}...")
                        click.echo(f"    Benefit: {attrs.get('value.benefit', 'N/A')[:80]}...")
                        if attrs.get("value.time_savings"):
                            click.echo(f"    Time savings: {attrs.get('value.time_savings')}")
                        if attrs.get("value.related_skills"):
                            click.echo(f"    Related skills: {attrs.get('value.related_skills')}")

        except requests.exceptions.RequestException as e:
            click.echo(click.style(f"    Error fetching trace details: {e}", fg="red"))


@value.command("list-personas")
def value_list_personas():
    """List available personas for value capability queries."""
    from contextcore.value.models import Persona

    click.echo(click.style("Available Personas:", fg="cyan", bold=True))
    for p in Persona:
        click.echo(f"  {click.style(p.value, fg='green')}")


@value.command("list-channels")
def value_list_channels():
    """List available channels for value capability queries."""
    from contextcore.value.models import Channel

    click.echo(click.style("Available Channels:", fg="cyan", bold=True))
    for c in Channel:
        click.echo(f"  {click.style(c.value, fg='green')}")


# =============================================================================
# Dashboard Commands
# =============================================================================


@main.group()
def dashboards():
    """Provision and manage Grafana dashboards.

    \b
    Commands:
        provision  Provision ContextCore dashboards to Grafana
        list       List provisioned dashboards
        delete     Delete ContextCore dashboards from Grafana
    """
    pass


@dashboards.command("provision")
@click.option(
    "--grafana-url",
    envvar="GRAFANA_URL",
    default="http://localhost:3000",
    help="Grafana base URL",
)
@click.option(
    "--api-key",
    envvar="GRAFANA_API_KEY",
    help="Grafana API key (or use GRAFANA_API_KEY env var)",
)
@click.option(
    "--username",
    envvar="GRAFANA_USERNAME",
    default="admin",
    help="Grafana username (if not using API key)",
)
@click.option(
    "--password",
    envvar="GRAFANA_PASSWORD",
    default="admin",
    help="Grafana password (if not using API key)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview without applying",
)
def dashboards_provision(
    grafana_url: str,
    api_key: Optional[str],
    username: str,
    password: str,
    dry_run: bool,
):
    """Provision ContextCore dashboards to Grafana.

    Provisions the following dashboards:
    - Project Portfolio Overview
    - Value Capabilities Dashboard

    \b
    Examples:
        # Auto-detect Grafana (localhost:3000)
        contextcore dashboards provision

        # Explicit Grafana URL with API key
        contextcore dashboards provision --grafana-url http://grafana.local:3000 --api-key $KEY

        # Preview without applying
        contextcore dashboards provision --dry-run
    """
    from contextcore.dashboards import DashboardProvisioner

    click.echo(click.style("ContextCore Dashboard Provisioning", fg="cyan", bold=True))
    click.echo()

    if dry_run:
        click.echo(click.style("DRY RUN MODE - No changes will be made", fg="yellow"))
        click.echo()

    click.echo(f"Grafana URL: {grafana_url}")
    click.echo(f"Auth: {'API Key' if api_key else 'Basic Auth'}")
    click.echo()

    provisioner = DashboardProvisioner(
        grafana_url=grafana_url,
        api_key=api_key,
        username=username,
        password=password,
    )

    results = provisioner.provision_all(dry_run=dry_run)

    click.echo(click.style("Results:", bold=True))
    success_count = 0
    for name, success, message in results:
        if success:
            click.echo(f"  {click.style('✓', fg='green')} {name}: {message}")
            success_count += 1
        else:
            click.echo(f"  {click.style('✗', fg='red')} {name}: {message}")

    click.echo()
    click.echo(f"Provisioned {success_count}/{len(results)} dashboards")


@dashboards.command("list")
@click.option(
    "--grafana-url",
    envvar="GRAFANA_URL",
    default="http://localhost:3000",
    help="Grafana base URL",
)
@click.option(
    "--api-key",
    envvar="GRAFANA_API_KEY",
    help="Grafana API key",
)
@click.option(
    "--username",
    envvar="GRAFANA_USERNAME",
    default="admin",
    help="Grafana username",
)
@click.option(
    "--password",
    envvar="GRAFANA_PASSWORD",
    default="admin",
    help="Grafana password",
)
def dashboards_list(
    grafana_url: str,
    api_key: Optional[str],
    username: str,
    password: str,
):
    """List ContextCore dashboards in Grafana.

    \b
    Examples:
        contextcore dashboards list
        contextcore dashboards list --grafana-url http://grafana.local:3000
    """
    from contextcore.dashboards import DashboardProvisioner

    provisioner = DashboardProvisioner(
        grafana_url=grafana_url,
        api_key=api_key,
        username=username,
        password=password,
    )

    dashboards_found = provisioner.list_provisioned()

    if not dashboards_found:
        click.echo("No ContextCore dashboards found in Grafana")
        click.echo()
        click.echo("Run 'contextcore dashboards provision' to create them")
        return

    click.echo(click.style("ContextCore Dashboards:", fg="cyan", bold=True))
    click.echo()

    for db in dashboards_found:
        click.echo(f"  {click.style(db.get('title', 'Unknown'), bold=True)}")
        click.echo(f"    UID: {db.get('uid', 'N/A')}")
        click.echo(f"    URL: {grafana_url}{db.get('url', '')}")
        click.echo()


@dashboards.command("delete")
@click.option(
    "--grafana-url",
    envvar="GRAFANA_URL",
    default="http://localhost:3000",
    help="Grafana base URL",
)
@click.option(
    "--api-key",
    envvar="GRAFANA_API_KEY",
    help="Grafana API key",
)
@click.option(
    "--username",
    envvar="GRAFANA_USERNAME",
    default="admin",
    help="Grafana username",
)
@click.option(
    "--password",
    envvar="GRAFANA_PASSWORD",
    default="admin",
    help="Grafana password",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)
def dashboards_delete(
    grafana_url: str,
    api_key: Optional[str],
    username: str,
    password: str,
    yes: bool,
):
    """Delete ContextCore dashboards from Grafana.

    \b
    Examples:
        contextcore dashboards delete
        contextcore dashboards delete --yes  # Skip confirmation
    """
    from contextcore.dashboards import DashboardProvisioner

    if not yes:
        if not click.confirm("Delete all ContextCore dashboards?"):
            click.echo("Cancelled")
            return

    provisioner = DashboardProvisioner(
        grafana_url=grafana_url,
        api_key=api_key,
        username=username,
        password=password,
    )

    results = provisioner.delete_all()

    click.echo(click.style("Deletion Results:", bold=True))
    for uid, success, message in results:
        if success:
            click.echo(f"  {click.style('✓', fg='green')} {uid}: {message}")
        else:
            click.echo(f"  {click.style('✗', fg='red')} {uid}: {message}")


# =============================================================================
# Operations Commands (ops)
# =============================================================================


@main.group()
def ops():
    """Operational commands for health, validation, and backup.

    \b
    Commands:
        doctor      Preflight system checks
        health      Component health status
        smoke-test  Full stack validation
        backup      Export state to backup
        restore     Restore from backup
        backups     List available backups
    """
    pass


@ops.command("doctor")
@click.option("--no-ports", is_flag=True, help="Skip port availability checks")
@click.option("--no-docker", is_flag=True, help="Skip Docker daemon check")
def ops_doctor(no_ports: bool, no_docker: bool):
    """Run preflight system checks.

    Validates system readiness before deployment:
    - Required tools (docker, python)
    - Docker daemon running
    - Port availability
    - Disk space
    - Data directories

    \b
    Examples:
        contextcore ops doctor
        contextcore ops doctor --no-ports
    """
    from contextcore.ops import doctor, DoctorResult
    from contextcore.ops.doctor import CheckStatus

    click.echo(click.style("=== Preflight Check ===", fg="cyan", bold=True))
    click.echo()

    result = doctor(
        check_ports=not no_ports,
        check_docker=not no_docker,
    )

    for check in result.checks:
        if check.status == CheckStatus.PASS:
            icon = click.style("✓", fg="green")
        elif check.status == CheckStatus.WARN:
            icon = click.style("⚠", fg="yellow")
        else:
            icon = click.style("✗", fg="red")

        click.echo(f"  {icon} {check.message}")
        if check.details:
            click.echo(f"      {check.details}")

    click.echo()
    if result.ready:
        click.echo(click.style("=== System Ready ===", fg="green", bold=True))
    else:
        click.echo(click.style(f"=== {result.failed} issue(s) found ===", fg="red", bold=True))
        sys.exit(1)


@ops.command("health")
def ops_health():
    """Show one-line health status per component.

    Checks health of:
    - Grafana
    - Tempo
    - Mimir
    - Loki
    - OTLP endpoints

    \b
    Examples:
        contextcore ops health
    """
    from contextcore.ops import health_check, HealthStatus

    click.echo(click.style("=== Component Health ===", fg="cyan", bold=True))

    result = health_check()

    for component in result.components:
        if component.status == HealthStatus.HEALTHY:
            icon = click.style("✓", fg="green")
            status = "Ready"
        elif component.status == HealthStatus.UNHEALTHY:
            icon = click.style("✗", fg="red")
            status = component.message
        else:
            icon = click.style("?", fg="yellow")
            status = component.message

        name = f"{component.name}:".ljust(14)
        click.echo(f"  {icon} {name} {status}")

    click.echo()
    if result.all_healthy:
        click.echo(click.style(f"All {len(result.components)} components healthy", fg="green"))
    else:
        click.echo(click.style(f"{result.unhealthy_count}/{len(result.components)} components unhealthy", fg="red"))


@ops.command("smoke-test")
def ops_smoke_test():
    """Validate entire stack is working after deployment.

    Runs comprehensive tests:
    1. Component health (Grafana, Tempo, Mimir, Loki)
    2. Grafana datasources configured
    3. Grafana dashboards provisioned
    4. ContextCore CLI available
    5. OTLP endpoint accessible

    \b
    Examples:
        contextcore ops smoke-test
    """
    from contextcore.ops import smoke_test
    from contextcore.ops.smoke_test import TestStatus

    click.echo(click.style("=== Smoke Test ===", fg="cyan", bold=True))
    click.echo()

    suite = smoke_test()

    for result in suite.results:
        if result.status == TestStatus.PASS:
            icon = click.style("✓", fg="green")
        elif result.status == TestStatus.FAIL:
            icon = click.style("✗", fg="red")
        else:
            icon = click.style("○", fg="yellow")

        click.echo(f"  {icon} {result.name}: {result.message}")
        if result.details:
            click.echo(f"      {result.details}")

    click.echo()
    click.echo(click.style(
        f"=== Smoke Test Complete: {suite.passed}/{len(suite.results)} passed ===",
        fg="green" if suite.all_passed else "red",
        bold=True,
    ))

    if not suite.all_passed:
        sys.exit(1)


@ops.command("backup")
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory for backup")
@click.option("--grafana-url", default="http://localhost:3000", help="Grafana URL")
@click.option("--grafana-user", default="admin", help="Grafana username")
@click.option("--grafana-password", default="admin", help="Grafana password")
def ops_backup(
    output_dir: Optional[str],
    grafana_url: str,
    grafana_user: str,
    grafana_password: str,
):
    """Export state to timestamped backup directory.

    Exports:
    - Grafana dashboards
    - Grafana datasources
    - Backup manifest

    \b
    Examples:
        contextcore ops backup
        contextcore ops backup --output-dir ./my-backups
    """
    from contextcore.ops import backup
    from pathlib import Path

    click.echo(click.style("=== Creating Backup ===", fg="cyan", bold=True))
    click.echo()

    result = backup(
        output_dir=Path(output_dir) if output_dir else None,
        grafana_url=grafana_url,
        grafana_auth=(grafana_user, grafana_password),
    )

    click.echo(f"Backup directory: {result.path}")
    click.echo(f"Dashboards: {result.manifest.dashboards_count}")
    click.echo(f"Datasources: {result.manifest.datasources_count}")

    if result.errors:
        click.echo()
        click.echo(click.style("Warnings:", fg="yellow"))
        for error in result.errors:
            click.echo(f"  - {error}")

    click.echo()
    if result.success:
        click.echo(click.style(f"Backup complete: {result.path}", fg="green", bold=True))
    else:
        click.echo(click.style("Backup completed with errors", fg="yellow", bold=True))


@ops.command("restore")
@click.argument("backup_path", type=click.Path(exists=True))
@click.option("--grafana-url", default="http://localhost:3000", help="Grafana URL")
@click.option("--grafana-user", default="admin", help="Grafana username")
@click.option("--grafana-password", default="admin", help="Grafana password")
def ops_restore(
    backup_path: str,
    grafana_url: str,
    grafana_user: str,
    grafana_password: str,
):
    """Restore from a backup directory.

    \b
    Examples:
        contextcore ops restore ./backups/20260117-143000
    """
    from contextcore.ops import restore
    from pathlib import Path

    click.echo(click.style("=== Restoring from Backup ===", fg="cyan", bold=True))
    click.echo()
    click.echo(f"Backup path: {backup_path}")
    click.echo()

    success, messages = restore(
        backup_path=Path(backup_path),
        grafana_url=grafana_url,
        grafana_auth=(grafana_user, grafana_password),
    )

    for msg in messages:
        if msg.startswith("Imported"):
            click.echo(click.style(f"  ✓ {msg}", fg="green"))
        else:
            click.echo(click.style(f"  ✗ {msg}", fg="red"))

    click.echo()
    if success:
        click.echo(click.style("Restore complete", fg="green", bold=True))
        click.echo("Run 'contextcore ops smoke-test' to verify")
    else:
        click.echo(click.style("Restore completed with errors", fg="yellow", bold=True))


@ops.command("backups")
@click.option("--dir", "-d", "base_dir", type=click.Path(), help="Backups directory")
def ops_list_backups(base_dir: Optional[str]):
    """List available backups.

    \b
    Examples:
        contextcore ops backups
        contextcore ops backups --dir ./my-backups
    """
    from contextcore.ops import list_backups
    from pathlib import Path

    backups = list_backups(Path(base_dir) if base_dir else None)

    if not backups:
        click.echo("No backups found")
        click.echo()
        click.echo("Create a backup with: contextcore ops backup")
        return

    click.echo(click.style("Available Backups:", fg="cyan", bold=True))
    click.echo()

    for path, manifest in backups:
        click.echo(f"  {click.style(str(path), bold=True)}")
        click.echo(f"    Created: {manifest.created_at}")
        click.echo(f"    Dashboards: {manifest.dashboards_count}")
        click.echo(f"    Datasources: {manifest.datasources_count}")
        click.echo()


# =============================================================================
# Install Command Group
# =============================================================================


@main.group()
def install():
    """Installation verification and status."""
    pass


@install.command("verify")
@click.option(
    "--category",
    "-c",
    multiple=True,
    type=click.Choice(
        ["configuration", "infrastructure", "tooling", "observability", "documentation"]
    ),
    help="Check specific categories only",
)
@click.option(
    "--no-telemetry",
    is_flag=True,
    help="Skip emitting telemetry",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
@click.option(
    "--critical-only",
    is_flag=True,
    help="Only show critical requirements",
)
def install_verify(category, no_telemetry, output_format, critical_only):
    """Verify ContextCore installation completeness.

    Checks all installation requirements and emits telemetry about the
    installation state. This enables ContextCore to track its own setup
    as observable data.

    Examples:

        # Full verification
        contextcore install verify

        # Check infrastructure only
        contextcore install verify --category infrastructure

        # JSON output for automation
        contextcore install verify --format json
    """
    from contextcore.install import (
        RequirementCategory,
        verify_installation,
    )

    # Map category strings to enums
    categories = None
    if category:
        categories = [RequirementCategory(c) for c in category]

    # Run verification
    result = verify_installation(
        categories=categories,
        emit_telemetry=not no_telemetry,
    )

    if output_format == "json":
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    # Table output
    click.echo()
    click.echo(click.style("=== ContextCore Installation Verification ===", fg="cyan"))
    click.echo()

    # Summary
    status_color = "green" if result.is_complete else "yellow"
    click.echo(
        f"Status: {click.style('COMPLETE' if result.is_complete else 'INCOMPLETE', fg=status_color, bold=True)}"
    )
    click.echo(f"Completeness: {result.completeness:.1f}%")
    click.echo(
        f"Critical: {result.critical_met}/{result.critical_total} "
        f"({result.critical_met / result.critical_total * 100:.0f}%)"
        if result.critical_total > 0
        else "Critical: N/A"
    )
    click.echo(f"Total: {result.passed_requirements}/{result.total_requirements}")
    click.echo(f"Duration: {result.duration_ms:.1f}ms")
    click.echo()

    # Category breakdown
    click.echo(click.style("By Category:", bold=True))
    for cat, cat_result in result.categories.items():
        cat_color = "green" if cat_result.completeness == 100 else "yellow"
        click.echo(
            f"  {cat.value:15} {click.style(f'{cat_result.completeness:5.1f}%', fg=cat_color)} "
            f"({cat_result.passed}/{cat_result.total})"
        )
    click.echo()

    # Requirements details
    click.echo(click.style("Requirements:", bold=True))

    for req_result in result.results:
        req = req_result.requirement

        # Skip non-critical if requested
        if critical_only and not req.critical:
            continue

        # Status indicator
        if req_result.status.value == "passed":
            indicator = click.style("✅", fg="green")
        elif req_result.status.value == "skipped":
            indicator = click.style("⏭️ ", fg="yellow")
        elif req_result.status.value == "error":
            indicator = click.style("💥", fg="red")
        else:
            indicator = click.style("❌", fg="red")

        # Critical badge
        critical_badge = click.style(" [CRITICAL]", fg="red") if req.critical else ""

        click.echo(f"  {indicator} {req.name}{critical_badge}")

        # Show error details
        if req_result.error:
            click.echo(f"      {click.style(req_result.error, fg='red')}")

    click.echo()

    # Exit code
    if not result.is_complete:
        click.echo(
            click.style(
                f"⚠️  Installation incomplete: {result.critical_total - result.critical_met} critical requirements missing",
                fg="yellow",
            )
        )
        sys.exit(1)
    else:
        click.echo(click.style("✅ Installation complete!", fg="green"))


@install.command("status")
def install_status():
    """Quick installation status check (no telemetry).

    Returns a simple status summary without emitting any telemetry.
    Useful for quick checks or CI/CD pipelines.
    """
    from contextcore.install import verify_installation

    result = verify_installation(emit_telemetry=False)

    if result.is_complete:
        click.echo(click.style("✅ Complete", fg="green"))
        click.echo(f"   {result.passed_requirements}/{result.total_requirements} requirements met")
    else:
        click.echo(click.style("❌ Incomplete", fg="red"))
        click.echo(f"   {result.critical_met}/{result.critical_total} critical requirements met")
        click.echo(f"   {result.passed_requirements}/{result.total_requirements} total requirements met")

    sys.exit(0 if result.is_complete else 1)


@install.command("list-requirements")
@click.option(
    "--category",
    "-c",
    type=click.Choice(
        ["configuration", "infrastructure", "tooling", "observability", "documentation"]
    ),
    help="Filter by category",
)
@click.option(
    "--critical-only",
    is_flag=True,
    help="Only show critical requirements",
)
def install_list_requirements(category, critical_only):
    """List all installation requirements.

    Shows the complete list of requirements that ContextCore checks
    during installation verification.
    """
    from contextcore.install import (
        INSTALLATION_REQUIREMENTS,
        RequirementCategory,
        get_requirements_by_category,
    )

    if category:
        requirements = get_requirements_by_category(RequirementCategory(category))
    else:
        requirements = INSTALLATION_REQUIREMENTS

    if critical_only:
        requirements = [r for r in requirements if r.critical]

    click.echo()
    click.echo(click.style("=== Installation Requirements ===", fg="cyan"))
    click.echo()

    current_category = None
    for req in requirements:
        # Category header
        if req.category != current_category:
            current_category = req.category
            click.echo(click.style(f"\n{current_category.value.upper()}", bold=True))

        # Requirement details
        critical_badge = click.style(" [CRITICAL]", fg="red") if req.critical else ""
        click.echo(f"  {req.id}{critical_badge}")
        click.echo(f"    {req.description}")

        if req.depends_on:
            deps = ", ".join(req.depends_on)
            click.echo(f"    Depends on: {deps}")

    click.echo()
    click.echo(f"Total: {len(requirements)} requirements")


if __name__ == "__main__":
    main()
