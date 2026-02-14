"""ContextCore CLI - Core commands (create, annotate, generate, runbook, controller)."""

import json
import os
import shutil
import subprocess
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import click
import yaml

from contextcore.contracts.timeouts import SUBPROCESS_DEFAULT_TIMEOUT_S
from contextcore.cli.export_io_ops import atomic_write_with_backup
from contextcore.utils.provenance import build_run_provenance_payload, write_provenance_file
from ._generators import generate_service_monitor, generate_prometheus_rule, generate_dashboard


class SubprocessError(click.ClickException):
    """Rich error for subprocess failures with context."""

    def __init__(self, cmd: list, returncode: int, stdout: str, stderr: str, context: str = ""):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.context = context
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = []
        if self.context:
            parts.append(self.context)
        parts.append(f"Command: {' '.join(self.cmd)}")
        parts.append(f"Exit code: {self.returncode}")
        if self.stderr:
            parts.append(f"Error: {self.stderr.strip()}")
        if self.stdout and self.returncode != 0:
            parts.append(f"Output: {self.stdout.strip()}")
        return "\n".join(parts)


def _check_kubectl_available() -> None:
    """Check if kubectl is available in PATH."""
    if not shutil.which("kubectl"):
        raise click.ClickException(
            "kubectl not found in PATH.\n"
            "Install kubectl: https://kubernetes.io/docs/tasks/tools/\n"
            "Or set KUBECONFIG environment variable."
        )


def _run_kubectl(args: list, input_text: str = None, context: str = "") -> Tuple[str, str]:
    """
    Run kubectl command with consistent error handling.

    Args:
        args: kubectl arguments (e.g., ["get", "pods", "-n", "default"])
        input_text: Optional stdin input
        context: Description of what the command is doing (for error messages)

    Returns:
        Tuple of (stdout, stderr)

    Raises:
        SubprocessError: On non-zero exit code
        click.ClickException: If kubectl not found
    """
    _check_kubectl_available()

    cmd = ["kubectl"] + args
    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_DEFAULT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise click.ClickException(
            f"Command timed out after 30 seconds: {' '.join(cmd)}\n"
            f"Context: {context or 'Running kubectl'}"
        )
    except FileNotFoundError:
        raise click.ClickException(
            "kubectl not found. Install kubectl or ensure it's in your PATH."
        )

    if result.returncode != 0:
        raise SubprocessError(
            cmd=cmd,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            context=context,
        )

    return result.stdout, result.stderr


def _get_project_context_spec(project: str, namespace: str = "default") -> Optional[dict]:
    """Fetch ProjectContext spec from Kubernetes cluster."""
    if "/" in project:
        namespace, name = project.split("/", 1)
    else:
        name = project

    try:
        stdout, _ = _run_kubectl(
            ["get", "projectcontext", name, "-n", namespace, "-o", "json"],
            context=f"Fetching ProjectContext '{name}' from namespace '{namespace}'"
        )
        pc = json.loads(stdout)
        return pc.get("spec", {})
    except SubprocessError:
        return None


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


@click.command()
@click.option("--name", "-n", required=True, help="ProjectContext name")
@click.option("--namespace", default="default", help="K8s namespace")
@click.option("--project", "-p", required=True, help="Project identifier")
@click.option("--epic", help="Epic identifier")
@click.option("--task", multiple=True, help="Task identifiers (can specify multiple)")
@click.option("--criticality", type=click.Choice(["critical", "high", "medium", "low"]), help="Business criticality")
@click.option("--value", type=click.Choice(["revenue-primary", "revenue-secondary", "cost-reduction", "compliance", "enabler"]), help="Business value")
@click.option("--owner", help="Owning team")
@click.option("--design-doc", help="Design document URL")
@click.option("--adr", help="ADR identifier or URL")
@click.option("--target", multiple=True, help="Target resources (kind/name)")
@click.option("--output", "-o", type=click.Choice(["yaml", "json"]), default="yaml")
@click.option("--apply", is_flag=True, help="Apply to cluster (requires kubectl)")
def create(name: str, namespace: str, project: str, epic: Optional[str], task: tuple, criticality: Optional[str],
           value: Optional[str], owner: Optional[str], design_doc: Optional[str], adr: Optional[str],
           target: tuple, output: str, apply: bool):
    """Create a new ProjectContext resource."""
    spec = {"project": {"id": project}, "targets": []}

    if epic:
        spec["project"]["epic"] = epic
    if task:
        spec["project"]["tasks"] = list(task)

    if criticality or value or owner:
        spec["business"] = {}
        if criticality:
            spec["business"]["criticality"] = criticality
        if value:
            spec["business"]["value"] = value
        if owner:
            spec["business"]["owner"] = owner

    if design_doc or adr:
        spec["design"] = {}
        if design_doc:
            spec["design"]["doc"] = design_doc
        if adr:
            spec["design"]["adr"] = adr

    if target:
        for t in target:
            if "/" in t:
                kind, tname = t.split("/", 1)
                spec["targets"].append({"kind": kind, "name": tname})
            else:
                click.echo(f"Invalid target format: {t}. Use kind/name", err=True)
                sys.exit(1)
    else:
        spec["targets"].append({"kind": "Deployment", "name": name})

    resource = {
        "apiVersion": "contextcore.io/v1",
        "kind": "ProjectContext",
        "metadata": {"name": name, "namespace": namespace},
        "spec": spec,
    }

    if output == "yaml":
        click.echo(yaml.dump(resource, default_flow_style=False))
    else:
        click.echo(json.dumps(resource, indent=2))

    if apply:
        yaml_content = yaml.dump(resource)
        stdout, _ = _run_kubectl(
            ["apply", "-f", "-"],
            input_text=yaml_content,
            context=f"Applying ProjectContext '{name}' to namespace '{namespace}'"
        )
        click.echo(stdout)


@click.command()
@click.argument("resource")
@click.option("--context", "-c", required=True, help="ProjectContext name")
@click.option("--namespace", "-n", default="default", help="Namespace")
def annotate(resource: str, context: str, namespace: str):
    """Annotate a K8s resource with ProjectContext reference."""
    if "/" not in resource:
        raise click.ClickException(
            f"Resource should be in format kind/name (e.g., deployment/my-app)\n"
            f"Got: {resource}"
        )

    annotation = f"contextcore.io/projectcontext={context}"
    _run_kubectl(
        ["annotate", resource, annotation, "-n", namespace, "--overwrite"],
        context=f"Annotating {resource} in namespace '{namespace}' with ProjectContext '{context}'"
    )
    click.echo(f"Annotated {resource} with {annotation}")


@click.command()
@click.option("--context", "-c", required=True, help="ProjectContext (namespace/name)")
@click.option("--output", "-o", default="./generated", help="Output directory")
@click.option("--service-monitor", is_flag=True, help="Generate ServiceMonitor")
@click.option("--prometheus-rule", is_flag=True, help="Generate PrometheusRule")
@click.option("--dashboard", is_flag=True, help="Generate Grafana dashboard")
@click.option("--all", "generate_all", is_flag=True, help="Generate all artifacts")
@click.option(
    "--strict-quality/--no-strict-quality",
    default=True,
    help="Enable strict quality safeguards (default: enabled)",
)
@click.option(
    "--emit-report/--no-emit-report",
    default=True,
    help="Write generation-report.json with checksums (default: enabled)",
)
@click.option(
    "--write-legacy-aliases/--no-write-legacy-aliases",
    default=False,
    help="Also write legacy filenames for backward compatibility (default: disabled)",
)
@click.option(
    "--document-write-strategy",
    type=click.Choice(["update_existing", "new_output"]),
    default="update_existing",
    help="Strategy for writing output documents (default: update_existing)",
)
@click.option(
    "--emit-run-provenance/--no-emit-run-provenance",
    default=None,
    help="Emit run-provenance.json (default: enabled in strict mode)",
)
def generate(
    context: str,
    output: str,
    service_monitor: bool,
    prometheus_rule: bool,
    dashboard: bool,
    generate_all: bool,
    strict_quality: bool,
    emit_report: bool,
    write_legacy_aliases: bool,
    document_write_strategy: str,
    emit_run_provenance: Optional[bool],
):
    """Generate observability artifacts from ProjectContext."""
    if "/" in context:
        namespace, name = context.split("/", 1)
    else:
        namespace = "default"
        name = context

    stdout, _ = _run_kubectl(
        ["get", "projectcontext", name, "-n", namespace, "-o", "json"],
        context=f"Fetching ProjectContext '{name}' from namespace '{namespace}'"
    )

    pc = json.loads(stdout)
    spec = pc.get("spec", {})

    if strict_quality:
        # Basic contract checks to avoid low-quality/partial outputs.
        missing = []
        if not spec.get("targets"):
            missing.append("spec.targets")
        if not spec.get("business", {}).get("criticality"):
            missing.append("spec.business.criticality")
        if not spec.get("requirements", {}).get("availability"):
            missing.append("spec.requirements.availability")
        if missing:
            raise click.ClickException(
                "Strict quality checks failed. Missing required fields: "
                + ", ".join(missing)
                + ". Use --no-strict-quality to bypass."
            )

    os.makedirs(output, exist_ok=True)

    if not any([service_monitor, prometheus_rule, dashboard, generate_all]):
        click.echo("No specific artifact flags provided; defaulting to --all for complete output.")
        generate_all = True

    # Strict profile enforces checksum report generation.
    if strict_quality:
        emit_report = True
        if emit_run_provenance is None:
            emit_run_provenance = True
        if write_legacy_aliases:
            click.echo(
                "⚠ Strict quality mode disables legacy alias outputs; using canonical filenames only."
            )
            write_legacy_aliases = False

    if generate_all:
        service_monitor = prometheus_rule = dashboard = True

    generated = []
    legacy_written = []
    use_backup = (document_write_strategy == "update_existing")

    if service_monitor:
        sm = generate_service_monitor(name, namespace, spec)
        path = os.path.join(output, f"{name}-service-monitor.yaml")
        atomic_write_with_backup(Path(path), yaml.dump(sm, sort_keys=False), backup=use_backup)
        generated.append(path)
        if write_legacy_aliases:
            legacy_path = os.path.join(output, f"{name}-servicemonitor.yaml")
            atomic_write_with_backup(Path(legacy_path), yaml.dump(sm, sort_keys=False), backup=use_backup)
            legacy_written.append(legacy_path)

    if prometheus_rule:
        pr = generate_prometheus_rule(name, namespace, spec)
        path = os.path.join(output, f"{name}-prometheus-rules.yaml")
        atomic_write_with_backup(Path(path), yaml.dump(pr, sort_keys=False), backup=use_backup)
        generated.append(path)
        if write_legacy_aliases:
            legacy_path = os.path.join(output, f"{name}-prometheusrule.yaml")
            atomic_write_with_backup(Path(legacy_path), yaml.dump(pr, sort_keys=False), backup=use_backup)
            legacy_written.append(legacy_path)

    if dashboard:
        db = generate_dashboard(name, namespace, spec)
        path = os.path.join(output, f"{name}-dashboard.json")
        atomic_write_with_backup(Path(path), json.dumps(db, indent=2), backup=use_backup)
        generated.append(path)
        if write_legacy_aliases:
            # Dashboard doesn't have common legacy alias in scan logic, but maybe?
            # Original code didn't write legacy alias for dashboard.
            pass

    if generated:
        click.echo(f"Generated {len(generated)} artifacts in {output}/")
        for path in generated:
            click.echo(f"  - {path}")
        if legacy_written:
            click.echo(f"  Wrote {len(legacy_written)} legacy alias file(s) for compatibility")

        if emit_report:
            report = {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "context": context,
                "projectcontext_name": name,
                "namespace": namespace,
                "strict_quality": strict_quality,
                "output_dir": str(Path(output).resolve()),
                "artifacts": [],
                "legacy_aliases": legacy_written,
            }
            for path in generated:
                report["artifacts"].append(
                    {
                        "path": path,
                        "filename": os.path.basename(path),
                        "sha256": _file_sha256(path),
                    }
                )
            report_path = os.path.join(output, "generation-report.json")
            atomic_write_with_backup(Path(report_path), json.dumps(report, indent=2), backup=use_backup)
            click.echo(f"  - {report_path}")
            if strict_quality and len(report["artifacts"]) != len(generated):
                raise click.ClickException(
                    "Strict quality checks failed: generation-report.json is incomplete."
                )
        
        if emit_run_provenance:
            # Reuse report inputs if available, else construct
            prov_outputs = [str(Path(p).resolve()) for p in generated]
            if emit_report:
                prov_outputs.append(str(Path(report_path).resolve()))
            
            run_payload = build_run_provenance_payload(
                workflow_or_command="contextcore generate",
                inputs=[], # Input is K8s resource, no file path usually
                outputs=prov_outputs,
                config_snapshot={
                    "context": context,
                    "strict_quality": strict_quality,
                    "namespace": namespace
                }
            )
            
            prov_dir = Path(output)
            prov_path = prov_dir / "run-provenance.json"
            if prov_path.exists() and use_backup:
                shutil.copy2(prov_path, prov_path.with_suffix(".json.bak"))
                
            write_provenance_file(run_payload, str(prov_dir), filename="run-provenance.json")
            click.echo(f"  - {prov_path}")

    else:
        click.echo("No artifacts generated. Use --all or specific flags.")


@click.command()
@click.option("--project", "-p", required=True, help="ProjectContext name (or namespace/name)")
@click.option("--namespace", "-n", default="default", help="Kubernetes namespace")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--format", "output_format", default="markdown", type=click.Choice(["markdown"]))
@click.option("--from-file", type=click.Path(exists=True), help="Read spec from local YAML file")
def runbook(project: str, namespace: str, output: Optional[str], output_format: str, from_file: Optional[str]):
    """Generate operational runbook from ProjectContext."""
    from contextcore.generators.runbook import generate_runbook

    if from_file:
        with open(from_file) as f:
            data = yaml.safe_load(f)
        spec = data.get("spec", data)
        project_info = spec.get("project", {})
        if isinstance(project_info, dict):
            project_id = project_info.get("id", project)
        else:
            project_id = project_info or project
    else:
        spec = _get_project_context_spec(project, namespace)
        if spec is None:
            click.echo(f"Error: ProjectContext '{project}' not found in namespace '{namespace}'", err=True)
            sys.exit(1)
        project_info = spec.get("project", {})
        if isinstance(project_info, dict):
            project_id = project_info.get("id", project)
        else:
            project_id = project_info or project

    runbook_content = generate_runbook(project_id, spec, output_format)

    if output:
        with open(output, "w") as f:
            f.write(runbook_content)
        click.echo(f"Runbook written to {output}")
    else:
        click.echo(runbook_content)


@click.command()
@click.option("--kubeconfig", envvar="KUBECONFIG", help="Path to kubeconfig")
@click.option("--namespace", default="", help="Namespace to watch (empty for all)")
def controller(kubeconfig: Optional[str], namespace: str):
    """Run the ContextCore controller locally."""
    click.echo("Starting ContextCore controller...")
    click.echo(f"  kubeconfig: {kubeconfig or 'in-cluster'}")
    click.echo(f"  namespace: {namespace or 'all'}")

    # Check if kopf is available
    if not shutil.which("kopf"):
        raise click.ClickException(
            "kopf not found in PATH.\n"
            "Install with: pip install kopf\n"
            "Or ensure kopf is in your PATH."
        )

    cmd = ["kopf", "run", "-m", "contextcore.operator", "--verbose"]
    if namespace:
        cmd.extend(["--namespace", namespace])

    click.echo(f"  Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise click.ClickException(
                f"Controller exited with error.\n"
                f"Exit code: {result.returncode}\n"
                f"Command: {' '.join(cmd)}"
            )
    except FileNotFoundError:
        raise click.ClickException(
            "kopf executable not found.\n"
            "Install with: pip install kopf\n"
            "Or ensure kopf is accessible in your PATH."
        )
