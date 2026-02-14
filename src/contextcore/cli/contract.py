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
@click.option("--project", "-p", default="contextcore", help="Project ID or path to ProjectContext YAML")
@click.option("--scope", type=click.Choice(["a2a", "openapi", "all"]), default="a2a",
              help="Drift scope: a2a (schema vs model), openapi (spec vs service), all")
@click.option("--schemas-dir", default="schemas/contracts/", help="Path to JSON schemas (a2a scope)")
@click.option("--output-dir", type=click.Path(exists=True), default=None,
              help="Scan actual output files for drift (a2a scope)")
@click.option("--service-url", "-s", help="Service URL (openapi scope)")
@click.option("--contract-url", "-c", help="OpenAPI spec URL/path (openapi scope)")
@click.option("--output", "-o", type=click.Path(), help="Output report file")
@click.option("--format", "-f", "output_format", type=click.Choice(["text", "json"]), default="text",
              help="Output format")
@click.option("--fail-on-drift", is_flag=True, help="Exit with error if critical drift detected")
@click.option("--namespace", "-n", default="default", help="Kubernetes namespace")
def contract_check_cmd(
    project: str,
    scope: str,
    schemas_dir: str,
    output_dir: Optional[str],
    service_url: Optional[str],
    contract_url: Optional[str],
    output: Optional[str],
    output_format: str,
    fail_on_drift: bool,
    namespace: str,
):
    """Check for contract drift (A2A schema drift or OpenAPI drift).

    A2A scope (default): Compares JSON schema files against Pydantic models
    and Python enums. Detects field mismatches, enum drift, and structural
    divergence. Runs entirely offline.

    OpenAPI scope: Compares OpenAPI specification against live service
    responses. Requires --service-url and --contract-url.

    Examples:
        # A2A schema drift (default, offline)
        contextcore contract check

        # A2A drift with output file scanning
        contextcore contract check --output-dir ./out/export

        # OpenAPI drift (requires network)
        contextcore contract check --scope openapi \\
            --service-url http://localhost:8080 \\
            --contract-url ./openapi.yaml

        # All drift checks
        contextcore contract check --scope all \\
            --service-url http://localhost:8080 \\
            --contract-url ./openapi.yaml
    """
    from contextcore.integrations.contract_drift import ContractDriftDetector

    # For openapi scope, resolve URLs from ProjectContext if not provided
    if scope in ("openapi", "all"):
        if not contract_url or not service_url:
            spec = _get_project_context_spec(project, namespace)
            if spec:
                if not contract_url:
                    design = spec.get("design", {})
                    contract_url = design.get("apiContract")
                if not service_url:
                    service_url = _derive_service_url(spec.get("targets", []))

        if scope == "openapi" and (not contract_url or not service_url):
            click.echo(
                "Error: OpenAPI scope requires --service-url and --contract-url "
                "(or a ProjectContext with design.apiContract and targets).",
                err=True,
            )
            sys.exit(1)

    click.echo(f"Checking contract drift (scope: {scope})...")
    if scope in ("a2a", "all"):
        click.echo(f"  Schemas: {schemas_dir}")
        if output_dir:
            click.echo(f"  Output:  {output_dir}")
    if scope in ("openapi", "all") and contract_url:
        click.echo(f"  Contract: {contract_url}")
        click.echo(f"  Service:  {service_url}")

    detector = ContractDriftDetector()
    report = detector.detect(
        project_id=project,
        contract_url=contract_url,
        service_url=service_url,
        schemas_dir=schemas_dir,
        output_dir=output_dir,
        scope=scope,
    )

    # Output report
    if output_format == "json":
        report_text = report.to_json()
    else:
        report_text = report.to_markdown()

    if output:
        with open(output, "w") as f:
            f.write(report_text)
        click.echo(f"\nReport written to {output}")
    else:
        click.echo("\n" + report_text)

    # Summary
    click.echo(f"\n{report.summary()}")

    if fail_on_drift and report.critical_issues:
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


@contract.command("a2a-pilot")
@click.option("--output", "-o", type=click.Path(), default="out/pilot-trace.json",
              help="Path to write trace evidence JSON (default: out/pilot-trace.json)")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text",
              help="Output format for summary")
@click.option("--fail-on-block", is_flag=True, help="Exit 1 if pilot is blocked")
@click.option("--source-checksum", default=None, help="Override source checksum (test mismatch)")
@click.option("--drop-feature", default=None, help="Drop a feature ID to test gap parity failure")
@click.option("--test-failures", type=int, default=0, help="Inject N critical test failures")
def a2a_pilot_cmd(
    output: str,
    output_format: str,
    fail_on_block: bool,
    source_checksum: Optional[str],
    drop_feature: Optional[str],
    test_failures: int,
):
    """Run the PI-101-002 pilot trace with full gate evidence.

    Executes all 10 phase spans (S1-S10) with gate checks at each boundary.
    Writes complete trace evidence to a JSON file.

    By default runs the happy path. Use options to inject failures:

    \b
    # Happy path
    contextcore contract a2a-pilot

    \b
    # Checksum mismatch (blocks at S3)
    contextcore contract a2a-pilot --source-checksum sha256:STALE

    \b
    # Gap parity failure (blocks at S4)
    contextcore contract a2a-pilot --drop-feature gap-latency-panel

    \b
    # Test failure (blocks at S8)
    contextcore contract a2a-pilot --test-failures 2
    """
    from contextcore.contracts.a2a.pilot import PilotRunner, PilotSeed

    seed = PilotSeed()

    # Apply overrides for failure injection
    if source_checksum:
        seed.source_checksum = source_checksum

    if drop_feature:
        seed.feature_ids = [f for f in seed.feature_ids if f != drop_feature]

    if test_failures > 0:
        seed.test_critical_failures = test_failures

    runner = PilotRunner(seed=seed)
    result = runner.execute()

    # Write evidence
    evidence_path = result.write_evidence(output)

    # Output summary
    summary = result.summary()

    if output_format == "json":
        click.echo(json.dumps(summary, indent=2))
    else:
        status_icon = "PASS" if result.is_success else "BLOCKED" if result.final_status == "blocked" else "FAIL"
        click.echo(f"\n{'='*60}")
        click.echo(f"  PI-101-002 Pilot: {status_icon}")
        click.echo(f"{'='*60}")
        click.echo(f"  Spans:  {summary['completed_spans']}/{summary['total_spans']} completed")
        click.echo(f"  Gates:  {summary['gates_passed']} passed, {summary['gates_failed']} failed")

        if summary["blocked_spans"]:
            click.echo(f"  Blocked: {', '.join(summary['blocked_spans'])}")

        if summary["errors"]:
            click.echo(f"  Errors: {len(summary['errors'])}")
            for err in summary["errors"]:
                click.echo(f"    - {err}")

        click.echo(f"\n  Evidence: {evidence_path}")
        click.echo()

    if fail_on_block and not result.is_success:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Pipeline integrity checker
# ---------------------------------------------------------------------------


@contract.command("a2a-check-pipeline")
@click.argument("output_dir", type=click.Path(exists=True))
@click.option("--task-id", default=None, help="Task span ID for gate context")
@click.option("--trace-id", default=None, help="Trace ID for gate context")
@click.option("--report", "-r", type=click.Path(), default=None,
              help="Write JSON report to this path")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text",
              help="Output format (default: text)")
@click.option("--fail-on-unhealthy", is_flag=True,
              help="Exit with code 1 if any blocking gate fails")
@click.option("--min-coverage", type=float, default=None,
              help="Minimum coverage threshold (0.0-1.0). Fails if below.")
def a2a_check_pipeline_cmd(
    output_dir: str,
    task_id: Optional[str],
    trace_id: Optional[str],
    report: Optional[str],
    output_format: str,
    fail_on_unhealthy: bool,
    min_coverage: Optional[float],
):
    """Run A2A governance checks on a real export output directory.

    Reads onboarding-metadata.json (and optionally provenance.json) from
    OUTPUT_DIR and runs the full gate suite:

    \b
    1. Structural integrity — required fields exist and are parseable
    2. Checksum chain — recompute and compare file hashes
    3. Provenance consistency — cross-check with provenance.json (skipped if absent)
    4. Mapping completeness — every target has corresponding artifacts
    5. Gap parity — coverage gaps match artifact features
    6. Design calibration — artifact depth tiers match type expectations
    7. Parameter resolvability — parameter_sources reference valid fields

    Gates 1-2 always run. Gate 3 is skipped without provenance.json.
    Gates 4-7 are skipped when their input data is absent.

    Use --min-coverage to enforce a minimum coverage threshold (e.g. 0.5 for 50%).

    Example:

    \b
        contextcore contract a2a-check-pipeline out/export

    \b
        contextcore contract a2a-check-pipeline out/export \\
            --fail-on-unhealthy --min-coverage 0.5 --report pipeline-report.json
    """
    from contextcore.contracts.a2a.pipeline_checker import PipelineChecker

    try:
        checker = PipelineChecker(
            output_dir, task_id=task_id, trace_id=trace_id,
            min_coverage=min_coverage,
        )
        result = checker.run()
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Write report if requested
    if report:
        result.write_json(report)
        click.echo(f"Report written to {report}")

    # Display output
    if output_format == "json":
        click.echo(json.dumps(result.summary(), indent=2, default=str))
    else:
        click.echo("")
        click.echo(result.to_text())

    if fail_on_unhealthy and not result.is_healthy:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Three Questions diagnostic
# ---------------------------------------------------------------------------


@contract.command("a2a-diagnose")
@click.argument("export_dir", type=click.Path(exists=True))
@click.option("--ingestion-dir", type=click.Path(), default=None,
              help="Path to plan ingestion output (enables Q2 checks)")
@click.option("--artisan-dir", type=click.Path(), default=None,
              help="Path to artisan workflow output (enables Q3 checks)")
@click.option("--trace-id", default=None, help="Trace ID for gate context")
@click.option("--report", "-r", type=click.Path(), default=None,
              help="Write JSON diagnostic report to this path")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text",
              help="Output format (default: text)")
@click.option("--fail-on-issue", is_flag=True,
              help="Exit with code 1 if any question fails")
def a2a_diagnose_cmd(
    export_dir: str,
    ingestion_dir: Optional[str],
    artisan_dir: Optional[str],
    trace_id: Optional[str],
    report: Optional[str],
    output_format: str,
    fail_on_issue: bool,
):
    """Run the Three Questions diagnostic on a pipeline execution.

    Walks through the structured diagnostic ordering from the Export Pipeline
    Analysis Guide:

    \b
    Q1: Is the contract complete? (Export layer)
    Q2: Was the contract faithfully translated? (Plan Ingestion)
    Q3: Was the translated plan faithfully executed? (Artisan)

    Stops at the first failing question — fixing downstream issues
    when the upstream contract is broken is wasted effort.

    Example:

    \b
        # Check export only
        contextcore contract a2a-diagnose out/enrichment-validation

    \b
        # Full pipeline diagnostic
        contextcore contract a2a-diagnose out/enrichment-validation \\
            --ingestion-dir out/plan-ingestion \\
            --artisan-dir out/artisan
    """
    from contextcore.contracts.a2a.three_questions import ThreeQuestionsDiagnostic

    try:
        diag = ThreeQuestionsDiagnostic(
            export_dir,
            ingestion_dir=ingestion_dir,
            artisan_dir=artisan_dir,
            trace_id=trace_id,
        )
        result = diag.run()
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Write report if requested
    if report:
        result.write_json(report)
        click.echo(f"Diagnostic report written to {report}")

    # Display output
    if output_format == "json":
        click.echo(json.dumps(result.summary(), indent=2, default=str))
    else:
        click.echo("")
        click.echo(result.to_text())

    if fail_on_issue and not result.all_passed:
        sys.exit(1)
