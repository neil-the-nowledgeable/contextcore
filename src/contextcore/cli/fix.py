"""
CLI command for ``contextcore fix`` — deterministic auto-remediation (Stage 1.5).

Applies safe, content-preserving fixes to plan documents that fail specific
polish checks.  Produces a remediated copy, a machine-readable fix report,
and registers both in the artifact inventory.

Usage::

    contextcore fix plan.md --output-dir output/
    contextcore fix plan.md --polish-report output/polish-report.json --dry-run
    contextcore fix plan.md --strict --format json
"""

import json as _json
from pathlib import Path
from typing import List, Optional

import click

from contextcore.cli.fix_ops import (
    FixResult,
    apply_fixes,
    FIXABLE_CHECK_IDS,
)
from contextcore.cli.polish import polish_file


def _run_polish_for_checks(target_path: Path) -> List[dict]:
    """Run polish on a file and return the check dicts."""
    result = polish_file(target_path)
    if result is None:
        return []
    return [
        {
            "check_id": c.check_id,
            "label": c.label,
            "status": c.status,
            "message": c.message,
            "detail": c.detail,
        }
        for c in result.checks
    ]


def _load_polish_report(report_path: Path, target_path: str) -> Optional[List[dict]]:
    """Load checks from a pre-computed polish-report.json.

    The report is a list of file entries; we find the one matching target_path.
    If not found, return checks from the first entry.
    """
    try:
        data = _json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError) as exc:
        raise click.ClickException(f"Cannot read polish report: {exc}")

    if not isinstance(data, list) or not data:
        raise click.ClickException("Polish report is empty or not a list.")

    # Try to find matching file entry
    target_str = str(target_path)
    for entry in data:
        if entry.get("file", "").endswith(Path(target_str).name):
            return entry.get("checks", [])

    # Fall back to first entry
    return data[0].get("checks", [])


def _build_report_payload(result: FixResult) -> dict:
    """Build the fix-report.json payload from a FixResult."""
    actions = []
    traceability = []
    for action in result.actions:
        action_dict = {
            "check_id": action.check_id,
            "status": action.status,
            "strategy": action.strategy,
            "diff_summary": action.diff_summary,
            "reason": action.reason,
        }
        actions.append(action_dict)
        if action.traceability:
            traceability.append({
                "check_id": action.check_id,
                **action.traceability,
            })

    return {
        "source_file": result.source_path,
        "actions": actions,
        "summary": {
            "fixed": result.fixed_count,
            "skipped": result.skipped_count,
            "not_applicable": result.not_applicable_count,
        },
        "traceability": traceability,
    }


def _render_text_report(result: FixResult):
    """Render human-readable fix report."""
    click.echo(click.style(f"\n  {result.source_path}", bold=True))
    click.echo(
        f"  {result.fixed_count} fixed, "
        f"{result.skipped_count} skipped, "
        f"{result.not_applicable_count} not applicable"
    )
    click.echo()

    for action in result.actions:
        if action.status == "fixed":
            icon = click.style("  FIX ", fg="green")
            click.echo(f"{icon} [{action.check_id}] {action.diff_summary}")
            if action.strategy:
                click.echo(f"          strategy: {action.strategy}")
        elif action.status == "skipped":
            icon = click.style("  SKIP", fg="yellow")
            click.echo(f"{icon} [{action.check_id}] {action.reason}")
        elif action.status == "not_applicable":
            icon = click.style("  N/A ", fg="blue")
            click.echo(f"{icon} [{action.check_id}] {action.reason}")

    click.echo()


@click.command()
@click.argument("target", type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.option(
    "--polish-report",
    type=click.Path(exists=True),
    default=None,
    help="Path to pre-computed polish-report.json (avoids re-running polish).",
)
@click.option("--strict", is_flag=True, help="Exit with non-zero code if any fixable check could not be fixed.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default=None,
    help="Write remediated file, fix-report.json, and register in artifact inventory.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview fixes without writing files.",
)
def fix(target, polish_report, strict, output_format, output_dir, dry_run):
    """[EXPERIMENTAL] Auto-remediate fixable polish check failures in a plan document."""

    target_path = Path(target)

    if target_path.suffix.lower() not in (".md", ".markdown"):
        raise click.ClickException(f"Expected a markdown file, got: {target_path.suffix}")

    content = target_path.read_text(encoding="utf-8")

    # Get polish checks (from report or by running polish)
    if polish_report:
        checks = _load_polish_report(Path(polish_report), str(target_path))
    else:
        checks = _run_polish_for_checks(target_path)

    if not checks:
        click.echo("No polish checks found. Nothing to fix.")
        return

    # Apply fixes
    result = apply_fixes(content, checks, str(target_path))

    # Render output
    if output_format == "json":
        report_payload = _build_report_payload(result)
        click.echo(_json.dumps(report_payload, indent=2))
    else:
        _render_text_report(result)
        if result.fixed_count == 0:
            click.echo(click.style("  No fixable issues found.", fg="green"))
        else:
            click.echo(
                click.style(
                    f"  Applied {result.fixed_count} fix(es).",
                    fg="green",
                )
            )

    # Write output artifacts
    if output_dir and not dry_run:
        from contextcore.utils.artifact_inventory import (
            build_inventory_entry,
            extend_inventory,
            PRE_PIPELINE_INVENTORY_ROLES,
        )

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Write remediated plan
        stem = target_path.stem
        fixed_filename = f"{stem}.fixed.md"
        fixed_file = out_path / fixed_filename
        fixed_file.write_text(result.remediated_content, encoding="utf-8")

        # Write fix report
        report_payload = _build_report_payload(result)
        report_file = out_path / "fix-report.json"
        report_file.write_text(
            _json.dumps(report_payload, indent=2) + "\n", encoding="utf-8"
        )

        # Register inventory entries
        entries = []

        fix_report_role = PRE_PIPELINE_INVENTORY_ROLES["fix_report"]
        entries.append(build_inventory_entry(
            role="fix_report",
            stage=fix_report_role["stage"],
            source_file="fix-report.json",
            produced_by="contextcore.fix",
            data=report_payload,
            description=fix_report_role["description"],
            consumers=fix_report_role["consumers"],
            consumption_hint=fix_report_role["consumption_hint"],
        ))

        remediated_role = PRE_PIPELINE_INVENTORY_ROLES["remediated_plan"]
        entries.append(build_inventory_entry(
            role="remediated_plan",
            stage=remediated_role["stage"],
            source_file=fixed_filename,
            produced_by="contextcore.fix",
            data=result.remediated_content,
            description=remediated_role["description"],
            consumers=remediated_role["consumers"],
            consumption_hint=remediated_role["consumption_hint"],
        ))

        extend_inventory(out_path, entries)

        click.echo(f"Wrote {fixed_filename} + fix-report.json + inventory to {out_path}")

    elif dry_run and result.fixed_count > 0:
        click.echo(click.style("  (dry-run: no files written)", fg="yellow"))

    # Strict mode: exit non-zero if any fixable check remains unfixed
    if strict:
        unfixed_fixable = [
            a for a in result.actions
            if a.check_id in FIXABLE_CHECK_IDS and a.status == "skipped"
        ]
        if unfixed_fixable:
            ids = ", ".join(a.check_id for a in unfixed_fixable)
            click.echo(
                click.style(f"  STRICT: fixable checks still failing: {ids}", fg="red"),
                err=True,
            )
            ctx = click.get_current_context()
            ctx.exit(1)
