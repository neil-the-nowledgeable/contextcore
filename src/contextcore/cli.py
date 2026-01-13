"""
ContextCore CLI - Manage ProjectContext resources.

Commands:
    contextcore create     Create a new ProjectContext
    contextcore annotate   Annotate K8s resources with context
    contextcore generate   Generate observability artifacts
    contextcore sync       Sync from external project tools
    contextcore controller Run the controller locally
"""

import json
import sys
from typing import Optional

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


if __name__ == "__main__":
    main()
