"""
Context Manifest CLI commands.

Provides tooling for working with Context Manifests:
- validate: Validate a manifest against the schema
- distill-crd: Extract K8s CRD from a manifest
- migrate: Migrate from v1.1 to v2.0
- show: Display manifest contents in various formats

Usage:
    contextcore manifest validate --path .contextcore.yaml
    contextcore manifest distill-crd --path .contextcore.yaml --namespace prod
    contextcore manifest migrate --path .contextcore.yaml --output .contextcore-v2.yaml
    contextcore manifest show --path .contextcore.yaml --format json
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click
import yaml


@click.group()
def manifest():
    """Context Manifest management commands."""
    pass


@manifest.command()
@click.option(
    "--path",
    "-p",
    required=True,
    type=click.Path(exists=True),
    help="Path to the manifest file",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Fail on warnings (not just errors)",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def validate(path: str, strict: bool, output_format: str):
    """
    Validate a context manifest against the schema.

    Returns exit code 0 if valid, 1 if invalid.
    """
    from contextcore.models.manifest_loader import load_manifest, detect_manifest_version

    path_obj = Path(path)
    errors = []
    warnings = []
    manifest_version = "unknown"

    try:
        # First detect version
        raw_data = yaml.safe_load(path_obj.read_text(encoding="utf-8"))
        manifest_version = detect_manifest_version(raw_data)

        # Try to load (validation happens automatically)
        manifest = load_manifest(path)

        # Additional semantic validation
        if manifest_version == "v2":
            # v2-specific validations
            from contextcore.models.manifest_v2 import ContextManifestV2

            if isinstance(manifest, ContextManifestV2):
                # Check for blocked tactics without reason
                for tactic in manifest.strategy.tactics:
                    if tactic.status.value == "blocked" and not tactic.blocked_reason:
                        errors.append(
                            f"Tactic {tactic.id} is blocked but missing blocked_reason"
                        )

                # Warn about open questions
                open_questions = manifest.get_open_questions()
                if open_questions:
                    warnings.append(
                        f"Manifest has {len(open_questions)} open question(s)"
                    )

    except FileNotFoundError:
        errors.append(f"File not found: {path}")
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error: {e}")
    except ValueError as e:
        errors.append(f"Validation error: {e}")
    except Exception as e:
        errors.append(f"Unexpected error: {e}")

    # Determine result
    is_valid = len(errors) == 0 and (not strict or len(warnings) == 0)

    # Output
    if output_format == "json":
        result = {
            "valid": is_valid,
            "version": manifest_version,
            "path": str(path),
            "errors": errors,
            "warnings": warnings,
        }
        click.echo(json.dumps(result, indent=2))
    else:
        if is_valid:
            click.echo(f"✓ Valid {manifest_version} manifest: {path}")
            if warnings:
                for w in warnings:
                    click.echo(f"  ⚠ Warning: {w}")
        else:
            click.echo(f"✗ Invalid manifest: {path}")
            for e in errors:
                click.echo(f"  ✗ Error: {e}")
            for w in warnings:
                click.echo(f"  ⚠ Warning: {w}")

    sys.exit(0 if is_valid else 1)


@manifest.command(name="distill-crd")
@click.option(
    "--path",
    "-p",
    required=True,
    type=click.Path(exists=True),
    help="Path to the manifest file",
)
@click.option(
    "--namespace",
    "-n",
    default="default",
    help="Kubernetes namespace for the CRD",
)
@click.option(
    "--name",
    help="Override the resource name (defaults to manifest name)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (default: stdout)",
)
def distill_crd(path: str, namespace: str, name: Optional[str], output: Optional[str]):
    """
    Extract a Kubernetes CRD from a context manifest.

    The CRD contains only the operational `spec` section, suitable for
    applying to a Kubernetes cluster.
    """
    from contextcore.models.manifest_loader import load_manifest

    try:
        manifest = load_manifest(path)

        # Both v1.1 and v2 have distill_crd method
        crd = manifest.distill_crd(namespace=namespace, name=name)

        crd_yaml = yaml.dump(crd, default_flow_style=False, sort_keys=False)

        if output:
            Path(output).write_text(crd_yaml, encoding="utf-8")
            click.echo(f"✓ CRD written to {output}")
        else:
            click.echo(crd_yaml)

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@manifest.command()
@click.option(
    "--path",
    "-p",
    required=True,
    type=click.Path(exists=True),
    help="Path to the v1.1 manifest file",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (default: stdout)",
)
@click.option(
    "--in-place",
    "-i",
    is_flag=True,
    help="Overwrite the input file (creates backup)",
)
@click.option(
    "--note",
    help="Add a custom migration note to changelog",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview migration without writing",
)
def migrate(
    path: str,
    output: Optional[str],
    in_place: bool,
    note: Optional[str],
    dry_run: bool,
):
    """
    Migrate a v1.1 manifest to v2.0 format.

    This is a non-destructive migration that:
    - Flattens the strategy/tactic hierarchy
    - Adds the guidance section (empty by default)
    - Preserves all existing data
    - Appends a migration entry to the changelog
    """
    from contextcore.models.manifest_loader import load_manifest_v1
    from contextcore.models.manifest_migrate import migrate_v1_to_v2

    try:
        # Load v1.1 manifest
        v1 = load_manifest_v1(path)

        # Migrate to v2
        v2_dict = migrate_v1_to_v2(v1, migration_note=note)

        v2_yaml = yaml.dump(v2_dict, default_flow_style=False, sort_keys=False)

        if dry_run:
            click.echo("=== DRY RUN - Migration Preview ===\n")
            click.echo(v2_yaml)
            click.echo("\n=== End Preview ===")
            return

        if in_place:
            # Create backup
            backup_path = Path(path).with_suffix(".v1.yaml.bak")
            Path(backup_path).write_text(
                Path(path).read_text(encoding="utf-8"), encoding="utf-8"
            )
            click.echo(f"✓ Backup created: {backup_path}")

            # Overwrite
            Path(path).write_text(v2_yaml, encoding="utf-8")
            click.echo(f"✓ Migrated in-place: {path}")

        elif output:
            Path(output).write_text(v2_yaml, encoding="utf-8")
            click.echo(f"✓ Migrated to: {output}")

        else:
            click.echo(v2_yaml)

    except ValueError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@manifest.command()
@click.option(
    "--path",
    "-p",
    required=True,
    type=click.Path(exists=True),
    help="Path to the manifest file",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["yaml", "json", "summary"]),
    default="summary",
    help="Output format",
)
def show(path: str, output_format: str):
    """
    Display manifest contents in various formats.
    """
    from contextcore.models.manifest_loader import load_manifest, detect_manifest_version

    try:
        raw_data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        version = detect_manifest_version(raw_data)
        manifest = load_manifest(path)

        if output_format == "yaml":
            click.echo(yaml.dump(raw_data, default_flow_style=False, sort_keys=False))

        elif output_format == "json":
            click.echo(json.dumps(raw_data, indent=2))

        else:  # summary
            click.echo(f"Context Manifest: {path}")
            click.echo(f"  Version: {version}")

            if hasattr(manifest, "metadata") and manifest.metadata:
                click.echo(f"  Name: {manifest.metadata.name}")

            if version == "v2":
                from contextcore.models.manifest_v2 import ContextManifestV2

                if isinstance(manifest, ContextManifestV2):
                    click.echo(f"\n  Strategy:")
                    click.echo(f"    Objectives: {len(manifest.strategy.objectives)}")
                    click.echo(f"    Tactics: {len(manifest.strategy.tactics)}")

                    active = manifest.get_active_tactics()
                    click.echo(f"    Active Tactics: {len(active)}")

                    click.echo(f"\n  Guidance:")
                    click.echo(f"    Constraints: {len(manifest.guidance.constraints)}")
                    click.echo(f"    Preferences: {len(manifest.guidance.preferences)}")
                    click.echo(f"    Questions: {len(manifest.guidance.questions)}")

                    open_q = manifest.get_open_questions()
                    if open_q:
                        click.echo(f"    Open Questions: {len(open_q)}")
                        for q in open_q[:3]:  # Show first 3
                            click.echo(f"      - {q.id}: {q.question[:50]}...")

                    click.echo(f"\n  Insights: {len(manifest.insights)}")
            else:
                # v1.1 summary
                click.echo(f"\n  Objectives: {len(manifest.objectives)}")
                click.echo(f"  Strategies: {len(manifest.strategies)}")
                click.echo(f"  Insights: {len(manifest.insights)}")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@manifest.command()
@click.option(
    "--path",
    "-p",
    default=".contextcore.yaml",
    help="Output path for the new manifest",
)
@click.option(
    "--name",
    required=True,
    help="Project/manifest name",
)
@click.option(
    "--version",
    "manifest_version",
    type=click.Choice(["v1.1", "v2"]),
    default="v2",
    help="Manifest version to create",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing file",
)
def init(path: str, name: str, manifest_version: str, force: bool):
    """
    Initialize a new context manifest.

    Creates a starter manifest with example structure.
    """
    path_obj = Path(path)

    if path_obj.exists() and not force:
        click.echo(f"✗ File already exists: {path}")
        click.echo("  Use --force to overwrite")
        sys.exit(1)

    if manifest_version == "v2":
        manifest_data = {
            "apiVersion": "contextcore.io/v1alpha2",
            "kind": "ContextManifest",
            "metadata": {
                "name": name,
                "owners": [{"team": "engineering"}],
                "changelog": [
                    {
                        "version": "2.0",
                        "date": "2024-01-01",
                        "author": "you",
                        "changes": ["Initial v2.0 manifest"],
                    }
                ],
            },
            "spec": {
                "project": {
                    "id": name,
                    "name": name.replace("-", " ").title(),
                },
                "business": {
                    "criticality": "medium",
                    "owner": "engineering",
                },
            },
            "strategy": {
                "objectives": [
                    {
                        "id": "OBJ-001",
                        "description": "Example objective",
                        "keyResults": [
                            {
                                "metricKey": "availability",
                                "unit": "%",
                                "target": 99.9,
                            }
                        ],
                    }
                ],
                "tactics": [
                    {
                        "id": "TAC-001",
                        "description": "Example tactic",
                        "status": "planned",
                        "linkedObjectives": ["OBJ-001"],
                    }
                ],
            },
            "guidance": {
                "focus": {
                    "areas": ["reliability"],
                    "reason": "Focus on core stability",
                },
                "constraints": [],
                "preferences": [],
                "questions": [],
            },
            "insights": [],
        }
    else:
        # v1.1 template
        manifest_data = {
            "apiVersion": "contextcore.io/v1alpha1",
            "kind": "ContextManifest",
            "version": "1.1",
            "metadata": {
                "name": name,
                "owners": [{"team": "engineering"}],
                "changelog": [
                    {
                        "version": "1.1",
                        "date": "2024-01-01",
                        "author": "you",
                        "changes": ["Initial v1.1 manifest"],
                    }
                ],
            },
            "spec": {
                "project": {
                    "id": name,
                    "name": name.replace("-", " ").title(),
                },
                "business": {
                    "criticality": "medium",
                    "owner": "engineering",
                },
            },
            "objectives": [
                {
                    "id": "OBJ-001",
                    "description": "Example objective",
                    "metric": "availability",
                    "target": "99.9%",
                }
            ],
            "strategies": [],
            "insights": [],
        }

    manifest_yaml = yaml.dump(manifest_data, default_flow_style=False, sort_keys=False)
    path_obj.write_text(manifest_yaml, encoding="utf-8")

    click.echo(f"✓ Created {manifest_version} manifest: {path}")
    click.echo(f"  Name: {name}")
    click.echo("\nNext steps:")
    click.echo(f"  1. Edit {path} to add your project details")
    click.echo(f"  2. Run: contextcore manifest validate --path {path}")


@manifest.command()
@click.option(
    "--path",
    "-p",
    required=True,
    type=click.Path(exists=True),
    help="Path to the context manifest file",
)
@click.option(
    "--output-dir",
    "-o",
    default=".",
    type=click.Path(),
    help="Output directory for generated files",
)
@click.option(
    "--namespace",
    "-n",
    default="default",
    help="Kubernetes namespace for the CRD",
)
@click.option(
    "--existing",
    "-e",
    multiple=True,
    type=str,
    help="Existing artifact in format 'artifact_id:path' (can specify multiple)",
)
@click.option(
    "--scan-existing",
    type=click.Path(exists=True),
    help="Scan directory for existing artifacts to mark as existing",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Output format for artifact manifest",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview without writing files",
)
@click.option(
    "--emit-provenance",
    is_flag=True,
    help="Write a separate provenance.json file with full audit trail",
)
@click.option(
    "--embed-provenance",
    is_flag=True,
    help="Embed provenance metadata in the artifact manifest",
)
@click.pass_context
def export(
    ctx,
    path: str,
    output_dir: str,
    namespace: str,
    existing: tuple,
    scan_existing: Optional[str],
    output_format: str,
    dry_run: bool,
    emit_provenance: bool,
    embed_provenance: bool,
):
    """
    Export CRD and Artifact Manifest for Wayfinder implementations.

    This command generates two files:
    1. ProjectContext CRD (not applied, just YAML)
    2. Artifact Manifest (defines what observability artifacts are needed)

    The Artifact Manifest serves as the CONTRACT between ContextCore (which knows
    WHAT artifacts are needed) and Wayfinder (which knows HOW to create them).

    Provenance tracking:
    - Use --emit-provenance to write a separate provenance.json file
    - Use --embed-provenance to include provenance in the artifact manifest
    - Provenance includes: git context, timestamps, checksums, CLI args

    Example:
        contextcore manifest export -p .contextcore.yaml -o ./output
        contextcore manifest export -p .contextcore.yaml -o ./output --emit-provenance

    This creates:
        ./output/my-project-projectcontext.yaml
        ./output/my-project-artifact-manifest.yaml
        ./output/provenance.json (if --emit-provenance)
    """
    from datetime import datetime as dt

    from contextcore.models.manifest_loader import load_manifest, detect_manifest_version
    from contextcore.models.manifest_v2 import ContextManifestV2

    # Capture start time for duration tracking
    start_time = dt.now()

    try:
        # Load manifest
        raw_data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        version = detect_manifest_version(raw_data)
        manifest = load_manifest(path)

        # Require v2 for artifact manifest generation
        if not isinstance(manifest, ContextManifestV2):
            click.echo(f"✗ Artifact manifest generation requires v2 manifest", err=True)
            click.echo(f"  Current version: {version}", err=True)
            click.echo(f"  Run: contextcore manifest migrate -p {path}", err=True)
            sys.exit(1)

        # Parse existing artifacts
        existing_artifacts: dict = {}
        for item in existing:
            if ":" in item:
                artifact_id, artifact_path = item.split(":", 1)
                existing_artifacts[artifact_id] = artifact_path
            else:
                click.echo(f"⚠ Invalid --existing format: {item} (expected 'id:path')", err=True)

        # Scan existing directory if provided
        if scan_existing:
            scan_path = Path(scan_existing)
            click.echo(f"Scanning for existing artifacts in {scan_path}...")
            scanned = _scan_existing_artifacts(scan_path)
            existing_artifacts.update(scanned)
            click.echo(f"  Found {len(scanned)} existing artifacts")

        # Generate outputs
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        project_name = manifest.metadata.name

        # 1. Generate CRD
        crd = manifest.distill_crd(namespace=namespace)
        crd_filename = f"{project_name}-projectcontext.yaml"
        crd_yaml = yaml.dump(crd, default_flow_style=False, sort_keys=False)

        # 2. Generate Artifact Manifest
        # Implementation-specific metrics from expansion packs are injected
        # here at the CLI layer, keeping the core model standard-agnostic.
        _beaver_metrics = {
            "beaver": [
                "startd8_active_sessions",
                "startd8_requests_total",
                "startd8_tokens_total",
                "startd8_response_time_ms",
                "startd8_context_usage_ratio",
                "startd8_truncations_total",
                "startd8_cost_total",
            ],
        }
        artifact_manifest = manifest.generate_artifact_manifest(
            source_path=str(path),
            existing_artifacts=existing_artifacts,
            extra_metrics=_beaver_metrics,
        )

        # Capture provenance if requested
        output_files = [crd_filename]
        artifact_filename = f"{project_name}-artifact-manifest.{output_format}"
        output_files.append(artifact_filename)

        provenance = None
        if emit_provenance or embed_provenance:
            from contextcore.utils.provenance import capture_provenance

            # Capture CLI options for provenance
            cli_options = {
                "path": path,
                "output_dir": output_dir,
                "namespace": namespace,
                "existing": list(existing),
                "scan_existing": scan_existing,
                "format": output_format,
                "dry_run": dry_run,
                "emit_provenance": emit_provenance,
                "embed_provenance": embed_provenance,
            }

            provenance = capture_provenance(
                source_path=path,
                output_directory=str(output_path),
                output_files=output_files,
                cli_args=sys.argv,
                cli_options=cli_options,
                start_time=start_time,
            )

            if embed_provenance:
                artifact_manifest.metadata.provenance = provenance

        if output_format == "yaml":
            artifact_content = yaml.dump(
                artifact_manifest.to_dict(),
                default_flow_style=False,
                sort_keys=False,
            )
        else:
            artifact_content = json.dumps(artifact_manifest.to_dict(), indent=2)

        if dry_run:
            click.echo("=== DRY RUN - Export Preview ===\n")
            click.echo(f"--- {crd_filename} ---")
            click.echo(crd_yaml[:500] + "..." if len(crd_yaml) > 500 else crd_yaml)
            click.echo(f"\n--- {artifact_filename} ---")
            click.echo(
                artifact_content[:1000] + "..."
                if len(artifact_content) > 1000
                else artifact_content
            )
            if provenance:
                click.echo(f"\n--- Provenance ---")
                prov_dict = provenance.model_dump(by_alias=True, exclude_none=True, mode="json")
                click.echo(json.dumps(prov_dict, indent=2, default=str)[:800] + "...")
            click.echo("\n=== End Preview ===")
            _print_coverage_summary(artifact_manifest)
            return

        # Write files
        crd_path = output_path / crd_filename
        artifact_path_file = output_path / artifact_filename

        crd_path.write_text(crd_yaml, encoding="utf-8")
        artifact_path_file.write_text(artifact_content, encoding="utf-8")

        # Write provenance file if requested
        provenance_file = None
        if emit_provenance and provenance:
            from contextcore.utils.provenance import write_provenance_file

            provenance_file = write_provenance_file(
                provenance, str(output_path), format="json"
            )
            output_files.append("provenance.json")

        click.echo(f"✓ Exported ContextCore artifacts to {output_path}/")
        click.echo(f"  1. {crd_filename} - Kubernetes CRD (do NOT apply directly)")
        click.echo(f"  2. {artifact_filename} - Artifact Manifest (for Wayfinder)")
        if provenance_file:
            click.echo(f"  3. provenance.json - Full provenance audit trail")

        _print_coverage_summary(artifact_manifest)

        # Print provenance summary if captured
        if provenance:
            click.echo(f"\n  Provenance:")
            if provenance.git:
                git = provenance.git
                dirty_marker = " (dirty)" if git.is_dirty else ""
                click.echo(f"    Git: {git.branch}@{git.commit_sha[:8] if git.commit_sha else 'unknown'}{dirty_marker}")
            click.echo(f"    Source checksum: {provenance.source_checksum[:16]}..." if provenance.source_checksum else "    Source checksum: not computed")
            click.echo(f"    Duration: {provenance.duration_ms}ms" if provenance.duration_ms else "")

        click.echo(f"\nNext steps:")
        click.echo(f"  1. Review the artifact manifest for accuracy")
        click.echo(f"  2. Pass both files to your Wayfinder implementation")
        click.echo(f"  3. Wayfinder will generate the observability artifacts")
        click.echo(f"  4. Re-run with --scan-existing to update coverage")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _scan_existing_artifacts(scan_path: Path) -> dict:
    """
    Scan a directory for existing observability artifacts.

    Looks for patterns like:
    - *-dashboard.json
    - *-rules.yaml, *-prometheus-rules.yaml
    - *-slo.yaml, *-slo-definition.yaml
    - *-service-monitor.yaml
    - *-loki-rules.yaml
    - *-notification*.yaml
    - *-runbook.md
    """
    existing = {}

    patterns = [
        ("*-dashboard.json", "dashboard"),
        ("*-prometheus-rules.yaml", "prometheus_rule"),
        ("*-rules.yaml", "prometheus_rule"),
        ("*-slo.yaml", "slo_definition"),
        ("*-slo-definition.yaml", "slo_definition"),
        ("*-service-monitor.yaml", "service_monitor"),
        ("*-loki-rules.yaml", "loki_rule"),
        ("*-notification*.yaml", "notification_policy"),
        ("*-runbook.md", "runbook"),
    ]

    for pattern, artifact_type in patterns:
        for file_path in scan_path.rglob(pattern):
            # Extract service name from filename
            stem = file_path.stem
            # Remove artifact type suffix
            for suffix in [
                "-dashboard",
                "-prometheus-rules",
                "-rules",
                "-slo",
                "-slo-definition",
                "-service-monitor",
                "-loki-rules",
                "-notification",
                "-runbook",
            ]:
                if stem.endswith(suffix):
                    service_name = stem[: -len(suffix)]
                    break
            else:
                service_name = stem

            # Normalize service name
            service_id = service_name.replace("-", "_")
            artifact_id = f"{service_id}-{artifact_type.replace('_', '-')}"

            existing[artifact_id] = str(file_path)

    return existing


def _print_coverage_summary(artifact_manifest) -> None:
    """Print a formatted coverage summary."""
    coverage = artifact_manifest.coverage

    click.echo(f"\n  Coverage Summary:")
    click.echo(f"    Overall: {coverage.overall_coverage:.1f}%")
    click.echo(f"    Required: {coverage.total_required}")
    click.echo(f"    Existing: {coverage.total_existing}")

    if coverage.by_type:
        click.echo(f"\n  Missing by Type:")
        for artifact_type, count in coverage.by_type.items():
            click.echo(f"    - {artifact_type}: {count}")

    gaps = artifact_manifest.get_gaps()
    if gaps:
        click.echo(f"\n  Top Gaps ({len(gaps)} total):")
        for gap in gaps[:5]:
            click.echo(f"    - [{gap.priority.value}] {gap.id}: {gap.name}")
        if len(gaps) > 5:
            click.echo(f"    ... and {len(gaps) - 5} more")
