"""ContextCore CLI - Contract drift detection and A2A contract validation commands."""

import json
import sys
from pathlib import Path
from typing import Optional

import click
import yaml

from contextcore.contracts.a2a.models import SCHEMA_FILES


def _get_project_context_spec(project: str, namespace: str = "default") -> Optional[dict]:
    """Fetch ProjectContext spec from Kubernetes cluster or local file."""
    import subprocess

    # Check if it's a file path
    if Path(project).exists():
        with open(project) as f:
            data = yaml.safe_load(f)
        return data.get("spec", data)

    # Try Kubernetes
    if "/" in project:
        namespace, name = project.split("/", 1)
    else:
        name = project

    cmd = ["kubectl", "get", "projectcontext", name, "-n", namespace, "-o", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None

    pc = json.loads(result.stdout)
    return pc.get("spec", {})


def _derive_service_url(targets: list) -> Optional[str]:
    """Derive service URL from ProjectContext targets."""
    for target in targets:
        if target.get("kind") == "Service":
            ns = target.get("namespace", "default")
            name = target.get("name", "service")
            port = target.get("port", 80)
            return f"http://{name}.{ns}.svc.cluster.local:{port}"

    # Fallback to first target
    if targets:
        name = targets[0].get("name", "service")
        ns = targets[0].get("namespace", "default")
        return f"http://{name}.{ns}.svc.cluster.local"

    return None


@click.group()
def contract():
    """API contract commands."""
    pass


@contract.command("check")
@click.option("--project", "-p", required=True, help="Project ID or path to ProjectContext YAML")
@click.option("--service-url", "-s", help="Service URL (auto-detect from targets if not provided)")
@click.option("--contract-url", "-c", help="OpenAPI spec URL/path (auto-detect from design.apiContract if not provided)")
@click.option("--output", "-o", type=click.Path(), help="Output report file")
@click.option("--fail-on-drift", is_flag=True, help="Exit with error if drift detected")
@click.option("--namespace", "-n", default="default", help="Kubernetes namespace")
def contract_check_cmd(
    project: str,
    service_url: Optional[str],
    contract_url: Optional[str],
    output: Optional[str],
    fail_on_drift: bool,
    namespace: str,
):
    """Check for API contract drift.

    Compares OpenAPI specification against live service responses to detect
    contract drift. Reports:
    - Missing endpoints (critical)
    - Schema mismatches (warning)
    - Unexpected properties (info)

    Example:
        contextcore contract check --project checkout-service \\
            --service-url http://localhost:8080 \\
            --contract-url ./openapi.yaml

    Or auto-detect from ProjectContext:
        contextcore contract check --project checkout-service
    """
    from contextcore.integrations.contract_drift import ContractDriftDetector

    spec = _get_project_context_spec(project, namespace)
    if not spec:
        click.echo(f"Error: ProjectContext '{project}' not found", err=True)
        sys.exit(1)

    # Get contract URL
    if not contract_url:
        design = spec.get("design", {})
        contract_url = design.get("apiContract")
        if not contract_url:
            click.echo("Error: No apiContract specified. Use --contract-url or set design.apiContract in ProjectContext", err=True)
            sys.exit(1)

    # Get service URL
    if not service_url:
        service_url = _derive_service_url(spec.get("targets", []))
        if not service_url:
            click.echo("Error: Could not derive service URL. Use --service-url or specify targets in ProjectContext", err=True)
            sys.exit(1)

    # Get project ID
    project_info = spec.get("project", {})
    if isinstance(project_info, dict):
        project_id = project_info.get("id", project)
    else:
        project_id = str(project_info) if project_info else project

    # Run drift detection
    click.echo(f"Checking contract drift...")
    click.echo(f"  Contract: {contract_url}")
    click.echo(f"  Service:  {service_url}")

    detector = ContractDriftDetector()
    report = detector.detect(project_id, contract_url, service_url)

    # Output report
    markdown = report.to_markdown()
    if output:
        with open(output, "w") as f:
            f.write(markdown)
        click.echo(f"\nReport written to {output}")
    else:
        click.echo("\n" + markdown)

    # Summary
    click.echo(f"\nEndpoints checked: {report.endpoints_checked}")
    click.echo(f"Endpoints passed:  {report.endpoints_passed}")
    click.echo(f"Issues found:      {len(report.issues)}")

    if report.critical_issues:
        click.echo(f"Critical issues:   {len(report.critical_issues)}")

    if fail_on_drift and report.has_drift:
        sys.exit(1)


# ---------------------------------------------------------------------------
# A2A contract validation commands
# ---------------------------------------------------------------------------

_VALID_CONTRACT_NAMES = sorted(SCHEMA_FILES.keys())


@contract.command("a2a-validate")
@click.argument("contract_name", type=click.Choice(_VALID_CONTRACT_NAMES))
@click.argument("payload_file", type=click.Path(exists=True))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text",
              help="Output format (default: text)")
@click.option("--fail-on-error", is_flag=True, help="Exit with error code 1 if validation fails")
def a2a_validate_cmd(
    contract_name: str,
    payload_file: str,
    output_format: str,
    fail_on_error: bool,
):
    """Validate a JSON payload against an A2A contract schema.

    CONTRACT_NAME is one of: TaskSpanContract, HandoffContract,
    ArtifactIntent, GateResult.

    PAYLOAD_FILE is a path to a JSON file containing the payload.

    Example:

        contextcore contract a2a-validate TaskSpanContract payload.json

        contextcore contract a2a-validate HandoffContract handoff.json --format json
    """
    from contextcore.contracts.a2a.validator import validate_payload

    with open(payload_file) as fh:
        try:
            payload = json.load(fh)
        except json.JSONDecodeError as exc:
            click.echo(f"Error: {payload_file} is not valid JSON — {exc}", err=True)
            sys.exit(1)

    report = validate_payload(contract_name, payload)

    if output_format == "json":
        out = {
            "contract_name": report.contract_name,
            "is_valid": report.is_valid,
            "errors": [e.to_dict() for e in report.errors],
        }
        click.echo(json.dumps(out, indent=2))
    else:
        if report.is_valid:
            click.echo(f"OK  {contract_name} validation passed ({payload_file})")
        else:
            click.echo(f"FAIL  {contract_name} validation failed ({payload_file})")
            for err in report.errors:
                click.echo(f"  [{err.error_code}] {err.failed_path}: {err.message}")
                click.echo(f"    -> {err.next_action}")

    if fail_on_error and not report.is_valid:
        sys.exit(1)


@contract.command("a2a-gate")
@click.argument("gate_type", type=click.Choice(["checksum", "mapping", "gap-parity"]))
@click.argument("data_file", type=click.Path(exists=True))
@click.option("--gate-id", required=True, help="Unique gate identifier")
@click.option("--task-id", required=True, help="Parent task span ID")
@click.option("--trace-id", default=None, help="Optional trace ID")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
@click.option("--fail-on-block", is_flag=True, help="Exit 1 if gate fails and is blocking")
def a2a_gate_cmd(
    gate_type: str,
    data_file: str,
    gate_id: str,
    task_id: str,
    trace_id: Optional[str],
    output_format: str,
    fail_on_block: bool,
):
    """Run an A2A phase gate check from a JSON data file.

    GATE_TYPE is one of: checksum, mapping, gap-parity.

    DATA_FILE is a JSON file with gate-specific keys:

    \b
    checksum:    {"expected": {...}, "actual": {...}}
    mapping:     {"artifact_ids": [...], "task_mapping": {...}}
    gap-parity:  {"gap_ids": [...], "feature_ids": [...]}

    Example:

        contextcore contract a2a-gate checksum data.json \\
            --gate-id PI-101-002-S3-C2 --task-id PI-101-002-S3
    """
    from contextcore.contracts.a2a.gates import (
        check_checksum_chain,
        check_gap_parity,
        check_mapping_completeness,
    )

    with open(data_file) as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            click.echo(f"Error: {data_file} is not valid JSON — {exc}", err=True)
            sys.exit(1)

    if gate_type == "checksum":
        result = check_checksum_chain(
            gate_id=gate_id,
            task_id=task_id,
            expected_checksums=data.get("expected", {}),
            actual_checksums=data.get("actual", {}),
            trace_id=trace_id,
        )
    elif gate_type == "mapping":
        result = check_mapping_completeness(
            gate_id=gate_id,
            task_id=task_id,
            artifact_ids=data.get("artifact_ids", []),
            task_mapping=data.get("task_mapping", {}),
            trace_id=trace_id,
        )
    elif gate_type == "gap-parity":
        result = check_gap_parity(
            gate_id=gate_id,
            task_id=task_id,
            gap_ids=data.get("gap_ids", []),
            feature_ids=data.get("feature_ids", []),
            trace_id=trace_id,
        )
    else:
        click.echo(f"Unknown gate type: {gate_type}", err=True)
        sys.exit(1)

    if output_format == "json":
        click.echo(result.model_dump_json(indent=2, exclude_none=True))
    else:
        status_icon = "PASS" if result.result.value == "pass" else "FAIL"
        blocking_tag = " [BLOCKING]" if result.blocking else ""
        click.echo(f"{status_icon}{blocking_tag}  {result.gate_id} ({result.phase.value})")
        click.echo(f"  Reason: {result.reason}")
        if result.next_action:
            click.echo(f"  Next:   {result.next_action}")
        if result.evidence:
            click.echo(f"  Evidence ({len(result.evidence)}):")
            for ev in result.evidence:
                click.echo(f"    - [{ev.type}] {ev.ref}: {ev.description or ''}")

    if fail_on_block and result.blocking and result.result.value == "fail":
        sys.exit(1)
