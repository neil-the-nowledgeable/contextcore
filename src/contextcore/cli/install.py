"""ContextCore CLI - Installation verification commands."""

import json
import os
import sys
from typing import Optional

import click


def _configure_otel_providers(endpoint: str) -> bool:
    """
    Configure global OTel providers with OTLP exporters.

    Must be called BEFORE importing verifier module to ensure
    metrics/traces are properly configured.

    Args:
        endpoint: OTLP endpoint (e.g., localhost:4317)

    Returns:
        True if configuration succeeded, False otherwise
    """
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

        # Create resource
        resource = Resource.create({
            "service.name": "contextcore-install",
            "service.namespace": "contextcore",
        })

        # Configure TracerProvider with OTLP exporter
        tracer_provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

        # Configure MeterProvider with OTLP exporter
        metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=5000,  # Export every 5 seconds
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        return True

    except Exception as e:
        click.echo(f"Warning: Failed to configure OTel: {e}", err=True)
        return False


def _flush_otel_providers() -> None:
    """Flush and shutdown OTel providers to ensure all telemetry is exported."""
    try:
        from opentelemetry import metrics, trace

        # Force flush and shutdown tracer provider
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, 'force_flush'):
            tracer_provider.force_flush(timeout_millis=10000)
        if hasattr(tracer_provider, 'shutdown'):
            tracer_provider.shutdown()

        # Force flush and shutdown meter provider
        meter_provider = metrics.get_meter_provider()
        if hasattr(meter_provider, 'force_flush'):
            meter_provider.force_flush(timeout_millis=10000)
        if hasattr(meter_provider, 'shutdown'):
            meter_provider.shutdown()

    except Exception:
        pass  # Best effort


def _flush_otel_metrics_only() -> None:
    """Force flush OTel meter provider without shutdown."""
    try:
        from opentelemetry import metrics

        meter_provider = metrics.get_meter_provider()
        if hasattr(meter_provider, 'force_flush'):
            meter_provider.force_flush(timeout_millis=5000)

    except Exception:
        pass  # Best effort


def _run_debug_verification(
    categories: Optional[list] = None,
    step_all: bool = False,
    no_telemetry: bool = False,
    endpoint: str = "localhost:4317",
    otel_configured: bool = False,
):
    """
    Run verification in debug mode with step-by-step checkpoints.

    Returns:
        VerificationResult if completed, None if aborted
    """
    from contextcore.install.verifier import InstallationVerifier
    from contextcore.install.debug_display import (
        display_debug_mode_start,
        display_debug_mode_complete,
        display_checkpoint,
        prompt_continue,
    )
    from contextcore.install.mimir_query import (
        check_mimir_available,
        verify_metric_emitted,
    )

    mimir_url = os.environ.get("MIMIR_URL", "http://localhost:9009")

    # Check Mimir availability
    mimir_available, mimir_msg = check_mimir_available(mimir_url)
    if not mimir_available:
        click.echo(click.style(f"Warning: {mimir_msg}", fg="yellow"))
        click.echo("Mimir verification will show N/A for all metrics.")
        click.echo()

    # Calculate total checkpoints for display
    from contextcore.install.requirements import (
        INSTALLATION_REQUIREMENTS,
        RequirementCategory,
    )

    requirements = INSTALLATION_REQUIREMENTS
    if categories:
        requirements = [r for r in requirements if r.category in categories]

    if step_all:
        total_checkpoints = len(requirements)
    else:
        category_count = len(set(r.category for r in requirements))
        total_checkpoints = category_count

    # Display introduction
    display_debug_mode_start(total_checkpoints, step_all)

    if otel_configured:
        click.echo(f"Telemetry export configured to {endpoint}")
        click.echo()

    # Create verifier
    verifier = InstallationVerifier(emit_telemetry=not no_telemetry)

    # Checkpoint callback
    def on_checkpoint(checkpoint):
        # Force flush metrics to ensure they're sent to Mimir
        if otel_configured:
            _flush_otel_metrics_only()
            # Give Mimir a moment to receive metrics
            import time
            time.sleep(1)

        # Query Mimir for verification
        mimir_results = []
        if mimir_available and checkpoint.emitted_metrics:
            for metric in checkpoint.emitted_metrics:
                result = verify_metric_emitted(
                    metric_name=metric.name,
                    expected_value=metric.value,
                    labels=metric.labels,
                    mimir_url=mimir_url,
                    max_retries=2,
                    retry_delay=0.5,
                )
                mimir_results.append(result)

        # Display checkpoint
        display_checkpoint(
            checkpoint,
            mimir_results=mimir_results if mimir_available else None,
            mimir_url=mimir_url,
        )

        # Prompt to continue
        return prompt_continue()

    # Run debug verification
    result = verifier.verify_debug(
        categories=categories,
        step_all=step_all,
        on_checkpoint=on_checkpoint,
    )

    # Display completion summary
    display_debug_mode_complete(
        passed=result.passed_requirements,
        total=result.total_requirements,
        completeness=result.completeness,
    )

    # Flush remaining telemetry
    if otel_configured:
        click.echo("Flushing remaining telemetry...")
        _flush_otel_providers()
        click.echo("Telemetry exported successfully")

    return result


@click.group()
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
    "--endpoint",
    "-e",
    envvar="OTEL_EXPORTER_OTLP_ENDPOINT",
    default="localhost:4317",
    help="OTLP endpoint for telemetry export",
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
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug mode with step-by-step verification and Mimir validation",
)
@click.option(
    "--step-all",
    is_flag=True,
    help="In debug mode, pause after each requirement (not just category)",
)
def install_verify(category, no_telemetry, endpoint, output_format, critical_only, debug, step_all):
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

        # With custom OTLP endpoint
        contextcore install verify --endpoint localhost:4317

        # Debug mode with per-category checkpoints (5 pauses)
        contextcore install verify --debug

        # Debug mode with per-requirement checkpoints (28 pauses)
        contextcore install verify --debug --step-all
    """
    # Configure OTel providers BEFORE importing verifier
    # This ensures metrics/traces use OTLP exporters
    otel_configured = False
    if not no_telemetry:
        otel_configured = _configure_otel_providers(endpoint)
        if otel_configured and not debug:
            click.echo(f"Telemetry export configured to {endpoint}")

    from contextcore.install import (
        RequirementCategory,
        verify_installation,
    )
    from contextcore.install.verifier import InstallationVerifier

    # Map category strings to enums
    categories = None
    if category:
        categories = [RequirementCategory(c) for c in category]

    # Debug mode
    if debug:
        result = _run_debug_verification(
            categories=categories,
            step_all=step_all,
            no_telemetry=no_telemetry,
            endpoint=endpoint,
            otel_configured=otel_configured,
        )
        # Debug mode handles its own output and exit
        if result is None:
            sys.exit(1)  # Aborted
        if not result.is_complete:
            sys.exit(1)
        return

    # Run normal verification
    result = verify_installation(
        categories=categories,
        emit_telemetry=not no_telemetry,
    )

    if output_format == "json":
        click.echo(json.dumps(result.to_dict(), indent=2))
        # Flush telemetry before exit
        if otel_configured:
            _flush_otel_providers()
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
            indicator = click.style("[PASS]", fg="green")
        elif req_result.status.value == "skipped":
            indicator = click.style("[SKIP]", fg="yellow")
        elif req_result.status.value == "error":
            indicator = click.style("[ERR]", fg="red")
        else:
            indicator = click.style("[FAIL]", fg="red")

        # Critical badge
        critical_badge = click.style(" [CRITICAL]", fg="red") if req.critical else ""

        click.echo(f"  {indicator} {req.name}{critical_badge}")

        # Show error details
        if req_result.error:
            click.echo(f"      {click.style(req_result.error, fg='red')}")

    click.echo()

    # Flush telemetry before exit
    if otel_configured:
        click.echo("Flushing telemetry...")
        _flush_otel_providers()
        click.echo("Telemetry exported successfully")

    # Exit code
    if not result.is_complete:
        click.echo(
            click.style(
                f"Installation incomplete: {result.critical_total - result.critical_met} critical requirements missing",
                fg="yellow",
            )
        )
        sys.exit(1)
    else:
        click.echo(click.style("Installation complete!", fg="green"))


@install.command("status")
def install_status():
    """Quick installation status check (no telemetry).

    Returns a simple status summary without emitting any telemetry.
    Useful for quick checks or CI/CD pipelines.
    """
    from contextcore.install import verify_installation

    result = verify_installation(emit_telemetry=False)

    if result.is_complete:
        click.echo(click.style("Complete", fg="green"))
        click.echo(f"   {result.passed_requirements}/{result.total_requirements} requirements met")
    else:
        click.echo(click.style("Incomplete", fg="red"))
        click.echo(f"   {result.critical_met}/{result.critical_total} critical requirements met")
        click.echo(f"   {result.passed_requirements}/{result.total_requirements} total requirements met")

    sys.exit(0 if result.is_complete else 1)


@install.command("init")
@click.option(
    "--endpoint",
    "-e",
    envvar="OTEL_EXPORTER_OTLP_ENDPOINT",
    default="localhost:4317",
    help="OTLP endpoint for telemetry export",
)
@click.option(
    "--skip-verify",
    is_flag=True,
    help="Skip verification and just show getting started info",
)
def install_init(endpoint, skip_verify):
    """Initialize ContextCore after installation.

    This command:
    1. Verifies the installation is complete
    2. Seeds initial metrics to the dashboard
    3. Shows helpful next steps

    Run this after 'make up' or 'docker-compose up' to populate
    the Installation Status dashboard with data.

    Examples:

        # Initialize with default endpoint
        contextcore install init

        # Initialize with custom OTLP endpoint
        contextcore install init --endpoint tempo:4317
    """
    import os

    grafana_url = os.environ.get("GRAFANA_URL", "http://localhost:3000")

    click.echo()
    click.echo(click.style("=== ContextCore Initialization ===", fg="cyan"))
    click.echo()

    if not skip_verify:
        # Configure OTel and run verification
        click.echo("Step 1: Running installation verification...")
        otel_configured = _configure_otel_providers(endpoint)

        if otel_configured:
            click.echo(f"   Telemetry export configured to {endpoint}")

        from contextcore.install import verify_installation

        result = verify_installation(emit_telemetry=otel_configured)

        # Show summary
        status_color = "green" if result.is_complete else "yellow"
        click.echo(f"   Status: {click.style('COMPLETE' if result.is_complete else 'INCOMPLETE', fg=status_color)}")
        click.echo(f"   Completeness: {result.completeness:.1f}%")
        click.echo(f"   Critical: {result.critical_met}/{result.critical_total}")

        if otel_configured:
            click.echo()
            click.echo("Step 2: Exporting metrics to Mimir...")
            _flush_otel_providers()
            click.echo(click.style("   Metrics exported successfully", fg="green"))

        if not result.is_complete:
            click.echo()
            click.echo(click.style("⚠️  Some requirements are not met:", fg="yellow"))
            for req_result in result.results:
                if not req_result.passed and req_result.requirement.critical:
                    click.echo(f"   - {req_result.requirement.name}")
            click.echo()
            click.echo("Run 'contextcore install verify' for details.")
    else:
        click.echo("Skipping verification (--skip-verify)")

    # Show next steps
    click.echo()
    click.echo(click.style("=== Getting Started ===", fg="cyan"))
    click.echo()
    click.echo("Dashboards:")
    click.echo(f"  Installation Status: {grafana_url}/d/contextcore-installation")
    click.echo(f"  Project Portfolio:   {grafana_url}/d/contextcore-portfolio")
    click.echo()
    click.echo("Quick Commands:")
    click.echo("  contextcore task start --id TASK-1 --title 'My First Task'")
    click.echo("  contextcore task update --id TASK-1 --status in_progress")
    click.echo("  contextcore task complete --id TASK-1")
    click.echo()
    click.echo("Pipeline Workflow (manifest lifecycle):")
    click.echo("  1. contextcore manifest init --name my-project")
    click.echo("  2. contextcore manifest validate --path .contextcore.yaml")
    click.echo("  3. contextcore manifest export -p .contextcore.yaml -o ./out/export --emit-provenance")
    click.echo("  4. contextcore contract a2a-check-pipeline ./out/export")
    click.echo("  5. startd8 workflow run plan-ingestion (or contextcore contract a2a-diagnose)")
    click.echo()
    click.echo("Documentation:")
    click.echo("  https://github.com/contextcore/contextcore#readme")
    click.echo()


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
