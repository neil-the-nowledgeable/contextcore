"""
CLI commands for capability index management.

Commands:
    contextcore capability-index build     Build/update the capability index
    contextcore capability-index validate  Validate the current index
    contextcore capability-index diff      Show what would change
    contextcore capability-index extract   Extract capabilities from a project
"""

from __future__ import annotations

from pathlib import Path

import click


def _find_project_root() -> Path:
    """Find the project root by walking up from CWD looking for .contextcore.yaml."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".contextcore.yaml").is_file():
            return parent
        if (parent / "src" / "contextcore").is_dir():
            return parent
    return cwd


@click.group("capability-index")
def capability_index():
    """Manage the capability index (build, validate, diff)."""
    pass


@capability_index.command()
@click.option("--dry-run", is_flag=True, help="Show what would change without writing")
@click.option("--validate-only", is_flag=True, help="Only validate, don't build")
@click.option("--output", type=click.Path(), default=None, help="Output path (default: in-place)")
def build(dry_run: bool, validate_only: bool, output: str | None) -> None:
    """Build/update the capability index from source code and sidecars."""
    from contextcore.utils.capability_builder import build_capability_index, write_manifest
    from contextcore.utils.capability_validator import validate_manifest

    project_root = _find_project_root()
    index_dir = project_root / "docs" / "capability-index"

    if validate_only:
        click.echo("Running validation only...")
        _run_validate(project_root, strict=False)
        return

    manifest, report = build_capability_index(project_root, dry_run=dry_run)

    click.echo(report.summary())
    click.echo()

    # Validate
    val_report = validate_manifest(manifest)
    click.echo(val_report.summary())
    click.echo()

    if dry_run:
        click.echo("Dry run — no files written.")
        return

    if not val_report.passed:
        click.echo("Validation failed with errors. Use --dry-run to inspect.")
        raise SystemExit(1)

    out_path = Path(output) if output else index_dir / "contextcore.agent.yaml"
    write_manifest(manifest, out_path)
    click.echo(f"Written to {out_path}")


@capability_index.command()
@click.option("--strict", is_flag=True, help="Fail on warnings too")
def validate(strict: bool) -> None:
    """Validate the current capability index."""
    _run_validate(_find_project_root(), strict=strict)


def _run_validate(project_root: Path, *, strict: bool) -> None:
    """Shared validation logic."""
    from contextcore.utils.capability_validator import validate_manifest_file

    index_path = project_root / "docs" / "capability-index" / "contextcore.agent.yaml"
    if not index_path.is_file():
        click.echo(f"No capability index found at {index_path}")
        raise SystemExit(1)

    report = validate_manifest_file(index_path)
    click.echo(report.summary())

    if strict and not report.passed_strict:
        click.echo("\nStrict mode: warnings treated as errors.")
        raise SystemExit(1)
    elif not report.passed:
        click.echo("\nValidation failed.")
        raise SystemExit(1)
    else:
        click.echo("\nValidation passed.")


@capability_index.command()
def diff() -> None:
    """Show what building would change vs current index."""
    from contextcore.utils.capability_builder import build_capability_index
    from contextcore.utils.capability_index import load_capability_index

    project_root = _find_project_root()
    index_dir = project_root / "docs" / "capability-index"

    # Load current
    current = load_capability_index(index_dir)
    current_ids = {c.capability_id for c in current.capabilities}
    current_principle_ids = {p.id for p in current.principles}
    current_pattern_ids = {p.pattern_id for p in current.patterns}

    # Build new
    manifest, report = build_capability_index(project_root)

    # Compute diffs
    new_cap_ids = {
        c["capability_id"]
        for c in (manifest.get("capabilities") or [])
        if isinstance(c, dict)
    }
    new_principle_ids = {
        p["id"]
        for p in (manifest.get("design_principles") or [])
        if isinstance(p, dict)
    }
    new_pattern_ids = {
        p["pattern_id"]
        for p in (manifest.get("patterns") or [])
        if isinstance(p, dict)
    }

    added_caps = new_cap_ids - current_ids
    removed_caps = current_ids - new_cap_ids
    added_principles = new_principle_ids - current_principle_ids
    added_patterns = new_pattern_ids - current_pattern_ids

    click.echo(f"Version: {current.version} -> {manifest.get('version', '?')}")
    click.echo()

    if added_caps:
        click.echo(f"+ {len(added_caps)} capabilities added:")
        for cap_id in sorted(added_caps):
            click.echo(f"    + {cap_id}")

    if removed_caps:
        click.echo(f"- {len(removed_caps)} capabilities removed:")
        for cap_id in sorted(removed_caps):
            click.echo(f"    - {cap_id}")

    if added_principles:
        click.echo(f"+ {len(added_principles)} principles added:")
        for pid in sorted(added_principles):
            click.echo(f"    + {pid}")

    if added_patterns:
        click.echo(f"+ {len(added_patterns)} patterns added:")
        for pid in sorted(added_patterns):
            click.echo(f"    + {pid}")

    if report.triggers_enriched:
        enriched_count = sum(len(v) for v in report.triggers_enriched.values())
        click.echo(f"~ {enriched_count} triggers enriched across {len(report.triggers_enriched)} capabilities")

    if not (added_caps or removed_caps or added_principles or added_patterns or report.triggers_enriched):
        click.echo("No changes detected.")


# Default craft toolkit location
_CRAFT_TOOLS = Path.home() / "Documents" / "craft" / "capability-index" / "tools"


@capability_index.command()
@click.argument("project_path", type=click.Path(exists=True), default=".")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output directory (default: ./capability-index-output)")
@click.option("--project-name", default=None,
              help="Project name for the extraction (default: directory name)")
@click.option("--toolkit-path", type=click.Path(exists=True), default=None,
              help="Path to craft capability-index tools directory")
def extract(project_path: str, output: str | None, project_name: str | None,
            toolkit_path: str | None) -> None:
    """Extract capabilities from a project using the craft toolkit.

    Wraps the craft toolkit's extract_capabilities.py for general-purpose
    AST-based capability extraction from Python codebases.
    """
    import subprocess
    import sys

    project = Path(project_path).resolve()
    tools_dir = Path(toolkit_path) if toolkit_path else _CRAFT_TOOLS
    extract_script = tools_dir / "extract_capabilities.py"

    if not extract_script.is_file():
        click.echo(f"Extract tool not found at {extract_script}")
        click.echo("Install the craft capability-index toolkit or use --toolkit-path")
        raise SystemExit(1)

    out_dir = Path(output) if output else Path.cwd() / "capability-index-output"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(extract_script),
        str(project),
        "--output", str(out_dir),
    ]
    if project_name:
        cmd.extend(["--project-name", project_name])

    click.echo(f"Extracting capabilities from {project}...")
    click.echo(f"Output: {out_dir}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)

    if result.returncode != 0:
        click.echo(f"Extraction failed (exit code {result.returncode})")
        raise SystemExit(result.returncode)

    click.echo(f"Extraction complete. Output in {out_dir}")
