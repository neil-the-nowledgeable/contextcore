"""
CLI commands for capability index management.

Commands:
    contextcore capability-index build         Build/update the capability index
    contextcore capability-index validate      Validate the current index
    contextcore capability-index diff          Show what would change
    contextcore capability-index extract       Extract capabilities from a project
    contextcore capability-index generate-mcp  Generate MCP tool definitions
    contextcore capability-index generate-a2a  Generate A2A Agent Card
    contextcore capability-index query         Query capabilities with filters
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


@capability_index.command()
@click.argument("project_path", type=click.Path(exists=True), default=".")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output directory (default: ./capability-index-output)")
@click.option("--project-name", default=None,
              help="Project name for the extraction (default: directory name)")
def extract(project_path: str, output: str | None, project_name: str | None) -> None:
    """Extract capabilities from a project via AST-based analysis.

    Analyzes Python source files and Markdown docs to discover CLI commands,
    classes, public functions, API endpoints, tests, and documentation sections.
    """
    from contextcore.utils.capability_extractor import run_extraction

    project = Path(project_path).resolve()
    out_dir = Path(output) if output else Path.cwd() / "capability-index-output"

    click.echo(f"Extracting capabilities from {project}...")
    click.echo(f"Output: {out_dir}")

    result = run_extraction(project, out_dir, project_name)

    click.echo(f"\n{'='*60}")
    click.echo(f"Extraction complete for: {result.project_name}")
    click.echo(f"{'='*60}")
    click.echo(f"  CLI commands:     {len(result.cli_commands):4d}")
    click.echo(f"  Classes:          {len(result.classes):4d}")
    click.echo(f"  Functions:        {len(result.functions):4d}")
    click.echo(f"  API endpoints:    {len(result.api_endpoints):4d}")
    click.echo(f"  Doc sections:     {len(result.doc_sections):4d}")
    click.echo(f"  Tests:            {len(result.tests):4d}")
    click.echo(f"  {'─'*28}")
    click.echo(f"  TOTAL:            {result.total_count():4d}")
    click.echo(f"\nOutputs in {out_dir}")


@capability_index.command("generate-mcp")
@click.argument("manifest_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output file (default: stdout)")
@click.option("--server-config", is_flag=True,
              help="Generate full MCP server config (not just tools)")
def generate_mcp(manifest_path: str, output: str | None, server_config: bool) -> None:
    """Generate MCP tool definitions from a capability manifest."""
    import json
    from contextcore.utils.capability_mcp_generator import generate_mcp_from_file

    result = generate_mcp_from_file(Path(manifest_path), server_config=server_config)
    json_output = json.dumps(result, indent=2)

    if output:
        Path(output).write_text(json_output)
        tool_count = result.get("tool_count", len(result.get("tools", [])))
        click.echo(f"Wrote {tool_count} tools to {output}")
    else:
        click.echo(json_output)


@capability_index.command("generate-a2a")
@click.argument("manifest_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output file (default: stdout)")
@click.option("--well-known", is_flag=True,
              help="Output in /.well-known/agent.json format")
def generate_a2a(manifest_path: str, output: str | None, well_known: bool) -> None:
    """Generate A2A Agent Card from a capability manifest."""
    import json
    from contextcore.utils.capability_a2a_generator import generate_a2a_from_file

    result = generate_a2a_from_file(Path(manifest_path), well_known=well_known)
    json_output = json.dumps(result, indent=2)

    if output:
        Path(output).write_text(json_output)
        click.echo(f"Wrote Agent Card to {output}")
    else:
        click.echo(json_output)


@capability_index.command()
@click.argument("index_path", type=click.Path(exists=True))
@click.option("--id", "capability_id", default=None,
              help="Filter by capability ID (exact or prefix)")
@click.option("--category", "-c", default=None,
              help="Filter by category")
@click.option("--maturity", "-m",
              type=click.Choice(["draft", "beta", "stable", "deprecated"]),
              default=None, help="Filter by maturity")
@click.option("--audience", "-a",
              type=click.Choice(["agent", "human", "gtm"]),
              default=None, help="Filter by audience")
@click.option("--trigger", "-t", default=None,
              help="Filter by trigger keyword")
@click.option("--min-confidence", type=float, default=None,
              help="Minimum confidence threshold (0.0-1.0)")
@click.option("--include-internal", is_flag=True,
              help="Include internal capabilities")
@click.option("--verbose", "-v", is_flag=True,
              help="Show detailed output")
@click.option("--json", "as_json", is_flag=True,
              help="Output as JSON")
def query(index_path: str, capability_id: str | None, category: str | None,
          maturity: str | None, audience: str | None, trigger: str | None,
          min_confidence: float | None, include_internal: bool,
          verbose: bool, as_json: bool) -> None:
    """Query capabilities from an index with filters."""
    import json as json_mod
    from contextcore.utils.capability_query import query_from_file, format_capability

    results = query_from_file(
        Path(index_path),
        capability_id=capability_id,
        category=category,
        maturity=maturity,
        audience=audience,
        trigger=trigger,
        min_confidence=min_confidence,
        include_internal=include_internal,
    )

    if as_json:
        click.echo(json_mod.dumps({"capabilities": results, "count": len(results)}, indent=2))
    elif not results:
        click.echo("No capabilities found matching filters")
    else:
        click.echo(f"Found {len(results)} capabilities:\n")
        for cap in results:
            click.echo(format_capability(cap, verbose=verbose))
            click.echo()
