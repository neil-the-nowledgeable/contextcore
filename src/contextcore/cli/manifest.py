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
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import yaml

from contextcore.cli.export_quality_ops import (
    apply_strict_quality_profile,
    evaluate_ci_policy,
    find_quality_policy_file,
    load_quality_policy,
    resolve_export_quality_toggles,
    validate_export_schema_pins,
    validate_manifest_api_pin,
)
from contextcore.cli.export_io_ops import (
    build_export_quality_report,
    enforce_min_coverage,
    load_artifact_task_mapping,
    parse_existing_artifacts,
    preview_export,
    print_export_success,
    render_artifact_content,
    scan_existing_artifacts,
    validate_required_task_mapping,
    write_export_outputs,
)
from contextcore.cli.init_from_plan_ops import (
    build_v2_manifest_template,
    infer_init_from_plan,
)


@click.group()
def manifest():
    """Context Manifest management commands."""
    pass


def _validate_manifest(path: str, strict: bool = False) -> tuple[list[str], list[str], str]:
    """
    Validate a context manifest. Returns (errors, warnings, manifest_version).
    """
    from contextcore.models.manifest_loader import load_manifest, detect_manifest_version

    path_obj = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    manifest_version = "unknown"

    try:
        raw_data = yaml.safe_load(path_obj.read_text(encoding="utf-8"))
        manifest_version = detect_manifest_version(raw_data)

        manifest = load_manifest(path)

        if manifest_version == "v2":
            from contextcore.models.manifest_v2 import ContextManifestV2

            if isinstance(manifest, ContextManifestV2):
                for tactic in manifest.strategy.tactics:
                    if tactic.status.value == "blocked" and not tactic.blocked_reason:
                        errors.append(
                            f"Tactic {tactic.id} is blocked but missing blocked_reason"
                        )

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

    return errors, warnings, manifest_version


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
    errors, warnings, manifest_version = _validate_manifest(path, strict=strict)
    is_valid = len(errors) == 0 and (not strict or len(warnings) == 0)

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
@click.option(
    "--validate/--no-validate",
    "validate_after_write",
    default=True,
    help="Validate the manifest after writing (default: enabled)",
)
def init(path: str, name: str, manifest_version: str, force: bool, validate_after_write: bool):
    """
    Initialize a new context manifest.

    Creates a starter manifest with example structure.
    """
    path_obj = Path(path)
    normalized_name = name.strip().lower().replace(" ", "-")
    if normalized_name != name:
        click.echo(f"⚠ Normalized manifest name: {name} -> {normalized_name}")
    name = normalized_name

    if path_obj.exists() and not force:
        click.echo(f"✗ File already exists: {path}")
        click.echo("  Use --force to overwrite")
        sys.exit(1)

    if manifest_version == "v2":
        manifest_data = build_v2_manifest_template(name)
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

    if validate_after_write:
        errors, warnings, _ = _validate_manifest(str(path_obj), strict=False)
        if errors:
            click.echo(f"✗ Created file failed validation: {path}", err=True)
            for e in errors:
                click.echo(f"  ✗ {e}", err=True)
            sys.exit(1)
        if warnings:
            click.echo(f"⚠ Validation warnings ({len(warnings)}):")
            for w in warnings:
                click.echo(f"  - {w}")
        click.echo("✓ Post-write validation passed")

    click.echo(f"✓ Created {manifest_version} manifest: {path}")
    click.echo(f"  Name: {name}")
    click.echo("\nNext steps:")
    click.echo(f"  1. Edit {path} to add your project details")
    click.echo(f"  2. Run: contextcore manifest validate --path {path}")
    click.echo(f"  3. Run: contextcore install init")
    click.echo(f"  4. Run: contextcore manifest export -p {path} -o ./out/export --emit-provenance")
    click.echo(f"  5. Run: contextcore contract a2a-check-pipeline ./out/export")
    click.echo(f"  6. Run: startd8 workflow run plan-ingestion (or contextcore contract a2a-diagnose)")


def _extract_requirement_ids(requirements_text: str) -> Dict[str, List[str]]:
    """Extract FR/NFR identifiers from requirement text."""
    found = re.findall(r"\b(FR-\d+|NFR-\d+)\b", requirements_text, flags=re.IGNORECASE)
    normalized = [rid.upper() for rid in found]
    fr_ids = sorted({rid for rid in normalized if rid.startswith("FR-")})
    nfr_ids = sorted({rid for rid in normalized if rid.startswith("NFR-")})
    return {"fr_ids": fr_ids, "nfr_ids": nfr_ids}


def _build_plan_draft_markdown(
    project_id: str,
    project_name: str,
    draft_plan_mode: str,
    manifest_path: str,
    requirements_paths: List[str],
    fr_ids: List[str],
    nfr_ids: List[str],
) -> str:
    fr_lines = "\n".join(f"- {rid}: [describe requirement]" for rid in fr_ids) or "- FR-001: [describe requirement]"
    nfr_lines = "\n".join(f"- {rid}: [describe requirement]" for rid in nfr_ids) or "- NFR-001: [describe requirement]"
    req_paths = "\n".join(f"- `{p}`" for p in requirements_paths) or "- (none provided)"

    mode_note = (
        "Template includes inferred requirement IDs from provided requirement files."
        if draft_plan_mode == "enriched"
        else "Template scaffold mode; fill requirement IDs and acceptance criteria manually."
    )

    return f"""# PLAN Draft: {project_name}

## 1. Overview
- Project ID: `{project_id}`
- Plan mode: `{draft_plan_mode}`
- Manifest path: `{manifest_path}`
- Note: {mode_note}

## 2. Goals and Outcomes
- [Goal 1]
- [Goal 2]

## 3. Scope and Assumptions
### In Scope
- [in-scope item]

### Out of Scope
- [out-of-scope item]

### Assumptions
- [assumption]

## 4. Requirements Inputs
{req_paths}

## 5. Functional Requirements (FR)
{fr_lines}

## 6. Non-Functional Requirements (NFR)
{nfr_lines}

## 7. Artifact Generation Plan

Each artifact type has derivation rules (business metadata → artifact config), expected output
contracts (depth, max_lines, completeness markers), and may have dependencies on other artifacts.

| Artifact Type | Expected Depth | Depends On | Notes |
|---------------|---------------|------------|-------|
| dashboard | comprehensive (>150 LOC) | prometheus_rule, slo_definition | Grafana JSON with panels, templating |
| prometheus_rule | standard (51-150 LOC) | service_monitor | Alert rules, recording rules |
| loki_rule | standard (51-150 LOC) | - | Log-based recording rules |
| service_monitor | brief (<=50 LOC) | - | K8s ServiceMonitor YAML |
| slo_definition | standard | - | SLO target + error budget |
| notification_policy | standard | prometheus_rule | Alert routing config |
| runbook | standard-comprehensive | prometheus_rule, dashboard | Incident procedures |

## 8. A2A Governance Gates

The export pipeline is validated by the A2A governance layer at every handoff boundary.

### Pre-Ingestion (Gate 1) — `contextcore contract a2a-check-pipeline`
- Structural integrity: all 4 export files present and valid
- Checksum chain: source → artifact manifest → CRD checksums verified
- Provenance consistency: git context and timestamps cross-checked
- Mapping completeness: every artifact has a task mapping entry
- Gap parity: coverage gaps match expected feature count
- Design calibration: expected depth per artifact type validated (warning only)

### Post-Ingestion (Gate 2) — `contextcore contract a2a-diagnose`
- Q1: Is the contract complete? (Export layer)
- Q2: Was the contract faithfully translated? (Plan Ingestion layer)
- Q3: Was the translated plan faithfully executed? (Artisan layer)

### Enrichment Fields (in onboarding-metadata.json)
- `derivation_rules`: business → artifact parameter mappings per type
- `expected_output_contracts`: depth, max_lines, completeness markers per type
- `artifact_dependency_graph`: adjacency list of artifact dependencies
- `resolved_artifact_parameters`: concrete parameter values per artifact
- `open_questions`: unresolved design decisions surfaced from guidance
- `file_ownership`: output path → artifact ID mapping for gap parity

## 9. Validation and Test Obligations
- [unit/integration tests]
- [schema validation checks]
- [acceptance criteria checks]
- A2A pipeline checker gate pass (Gate 1)
- Three Questions diagnostic pass (Gates 1-3)

## 10. Risks and Mitigations
- Risk: [describe]
  - Mitigation: [describe]

## 11. Execution Notes for Startd8
- Feed this plan to `startd8 workflow run plan-ingestion`.
- Keep ContextCore export artifacts available for ingestion preflight.
- Route expectation: Prime for simpler scope; Artisan for complex or low-quality translation.
- **Pre-ingestion**: Run `contextcore contract a2a-check-pipeline` on export output.
- **Post-ingestion**: Run `contextcore contract a2a-diagnose` with `--ingestion-dir`.
- **Export**: Always use `--emit-provenance` for checksum chain integrity.
"""


@manifest.command()
@click.option(
    "--project-id",
    required=True,
    help="Canonical project identifier used in create outputs",
)
@click.option(
    "--project-name",
    default=None,
    help="Display name for the plan draft (defaults to project-id title case)",
)
@click.option(
    "--manifest-path",
    default=".contextcore.yaml",
    help="Expected path for context manifest (used in emitted artifacts)",
)
@click.option(
    "--requirements-path",
    "requirements_paths",
    multiple=True,
    type=click.Path(exists=True),
    help="Requirements document path (repeatable)",
)
@click.option(
    "--output-dir",
    "-o",
    default="./out/create",
    type=click.Path(),
    help="Directory to write create artifacts",
)
@click.option(
    "--draft-plan-mode",
    type=click.Choice(["scaffold", "enriched"]),
    default="scaffold",
    help="Draft plan generation mode",
)
@click.option(
    "--interactive/--no-interactive",
    default=False,
    help="Reserved for guided prompt mode (currently deterministic outputs only)",
)
@click.option(
    "--complexity-threshold",
    type=int,
    default=40,
    help="Plan ingestion threshold: <= threshold routes to prime, else artisan",
)
@click.option(
    "--route-policy",
    type=click.Choice(["auto", "prime", "artisan"]),
    default="auto",
    help="Routing policy for downstream plan ingestion",
)
@click.option(
    "--low-quality-policy",
    type=click.Choice(["bias_artisan", "fail"]),
    default="bias_artisan",
    help="Action when translation quality is low in plan ingestion",
)
@click.option(
    "--min-export-coverage",
    type=float,
    default=70.0,
    help="Minimum export coverage threshold used in emitted gate policy",
)
@click.option(
    "--contextcore-export-dir",
    default="./out/export",
    help="Expected ContextCore export directory for plan ingestion preflight",
)
@click.option(
    "--emit-startd8-config/--no-emit-startd8-config",
    default=True,
    help="Emit startd8-plan-ingestion-config.json (default: enabled)",
)
@click.option(
    "--emit-wayfinder-config/--no-emit-wayfinder-config",
    default=False,
    help="Emit wayfinder-run-config.json",
)
@click.option(
    "--write-manifest-scaffold/--no-write-manifest-scaffold",
    default=False,
    help="Also write a v2 context manifest scaffold from create inputs",
)
@click.option(
    "--manifest-scaffold-path",
    default=".contextcore.yaml",
    help="Path for scaffold manifest when --write-manifest-scaffold is enabled",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing artifact files in output directory",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview create outputs without writing files",
)
def create(
    project_id: str,
    project_name: Optional[str],
    manifest_path: str,
    requirements_paths: tuple,
    output_dir: str,
    draft_plan_mode: str,
    interactive: bool,
    complexity_threshold: int,
    route_policy: str,
    low_quality_policy: str,
    min_export_coverage: float,
    contextcore_export_dir: str,
    emit_startd8_config: bool,
    emit_wayfinder_config: bool,
    write_manifest_scaffold: bool,
    manifest_scaffold_path: str,
    force: bool,
    dry_run: bool,
):
    """
    Create a planning and handoff artifact package for init/export/ingestion.

    This command does not generate code. It drafts plan and policy artifacts
    for the downstream startd8 plan-ingestion and contractor workflows.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    display_name = project_name or project_id.replace("-", " ").replace("_", " ").title()
    requirement_files = [str(Path(p)) for p in requirements_paths]
    requirements_text = "\n\n".join(
        Path(p).read_text(encoding="utf-8") for p in requirement_files
    ) if requirement_files else ""
    req_ids = _extract_requirement_ids(requirements_text)

    plan_filename = "PLAN-draft.md"
    create_spec_filename = "create-spec.json"
    gates_filename = "create-gates.json"
    startd8_config_filename = "startd8-plan-ingestion-config.json"
    wayfinder_config_filename = "wayfinder-run-config.json"

    plan_path = output_path / plan_filename
    create_spec_path = output_path / create_spec_filename
    gates_path = output_path / gates_filename
    startd8_config_path = output_path / startd8_config_filename
    wayfinder_config_path = output_path / wayfinder_config_filename
    manifest_scaffold = Path(manifest_scaffold_path)

    target_files = [plan_path, create_spec_path, gates_path]
    if emit_startd8_config:
        target_files.append(startd8_config_path)
    if emit_wayfinder_config:
        target_files.append(wayfinder_config_path)
    if write_manifest_scaffold:
        target_files.append(manifest_scaffold)

    if not force:
        existing = [str(p) for p in target_files if p.exists()]
        if existing and not dry_run:
            click.echo("✗ create would overwrite existing files:", err=True)
            for fp in existing:
                click.echo(f"  - {fp}", err=True)
            click.echo("  Re-run with --force to overwrite", err=True)
            sys.exit(1)

    plan_draft = _build_plan_draft_markdown(
        project_id=project_id,
        project_name=display_name,
        draft_plan_mode=draft_plan_mode,
        manifest_path=manifest_path,
        requirements_paths=requirement_files,
        fr_ids=req_ids["fr_ids"],
        nfr_ids=req_ids["nfr_ids"],
    )

    create_spec: Dict[str, Any] = {
        "schema": "contextcore.io/create-spec/v1",
        "generated_at": datetime.now().isoformat(),
        "project": {"id": project_id, "name": display_name},
        "inputs": {
            "manifest_path": manifest_path,
            "requirements_files": requirement_files,
            "draft_plan_mode": draft_plan_mode,
            "interactive_requested": interactive,
        },
        "requirements": {
            "functional_ids": req_ids["fr_ids"],
            "non_functional_ids": req_ids["nfr_ids"],
            "unresolved_notes": [
                "Fill requirement descriptions and acceptance criteria in PLAN-draft.md.",
            ],
        },
        "artifact_contract": {
            "required_types": [
                "dashboard",
                "prometheus_rule",
                "loki_rule",
                "service_monitor",
                "slo_definition",
                "notification_policy",
                "runbook",
            ],
            "recommended_types": [],
        },
        "routing_policy": {
            "complexity_threshold": complexity_threshold,
            "route_policy": route_policy,
            "low_quality_policy": low_quality_policy,
        },
        "handoff": {
            "plan_path": str(plan_path),
            "contextcore_export_dir_expected": contextcore_export_dir,
            "startd8_config_path": str(startd8_config_path) if emit_startd8_config else None,
        },
        "a2a_contracts": {
            "schema_version": "v1",
            "contract_types": [
                {"name": "TaskSpanContract", "usage": "Task/subtask lifecycle as trace spans"},
                {"name": "ArtifactIntent", "usage": "Artifact requirement declaration before generation"},
                {"name": "GateResult", "usage": "Phase boundary check outcomes at every gate"},
                {"name": "HandoffContract", "usage": "Agent-to-agent delegation at routing decisions"},
            ],
            "schemas_path": "schemas/contracts/",
        },
        "enrichment_fields": {
            "description": "Fields in onboarding-metadata.json that downstream consumers depend on",
            "required": [
                "derivation_rules",
                "expected_output_contracts",
                "artifact_dependency_graph",
                "resolved_artifact_parameters",
                "file_ownership",
            ],
            "recommended": [
                "open_questions",
                "objectives",
                "requirements_hints",
                "parameter_resolvability",
            ],
        },
        "defense_in_depth": {
            "principles": [
                "P1: Validate at the boundary, not just at the end",
                "P2: Treat each piece as potentially adversarial",
                "P3: Use checksums as circuit breakers",
                "P4: Fail loud, fail early, fail specific",
                "P5: Design calibration guards against over/under-engineering",
                "P6: Three Questions diagnostic ordering",
            ],
            "reference": "docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md §6",
        },
    }

    create_gates: Dict[str, Any] = {
        "schema": "contextcore.io/create-gates/v1",
        "generated_at": datetime.now().isoformat(),
        "gates": {
            "checksum_chain_required": True,
            "min_export_coverage": min_export_coverage,
            "block_on_unresolved_parameter_sources": True,
            "block_on_validation_diagnostics": True,
            "derivation_rules_populated": True,
            "expected_output_contracts_present": True,
            "dependency_graph_populated": True,
            "open_questions_surfaced": True,
        },
        "a2a_pipeline_checker": {
            "enabled": True,
            "command": "contextcore contract a2a-check-pipeline",
            "gates": [
                {"name": "structural-integrity", "phase": "EXPORT_CONTRACT", "blocking": True},
                {"name": "checksum-chain", "phase": "CONTRACT_INTEGRITY", "blocking": True},
                {"name": "provenance-consistency", "phase": "CONTRACT_INTEGRITY", "blocking": True},
                {"name": "mapping-completeness", "phase": "CONTRACT_INTEGRITY", "blocking": True},
                {"name": "gap-parity", "phase": "INGEST_PARSE_ASSESS", "blocking": True},
                {"name": "design-calibration", "phase": "ARTISAN_DESIGN", "blocking": False},
            ],
        },
        "a2a_diagnostic": {
            "enabled": True,
            "command": "contextcore contract a2a-diagnose",
            "stop_at_first_failure": True,
            "questions": [
                "Q1: Is the contract complete? (Export layer)",
                "Q2: Was the contract faithfully translated? (Plan Ingestion layer)",
                "Q3: Was the translated plan faithfully executed? (Artisan layer)",
            ],
        },
        "notes": [
            "These gates are intended for pre-ingestion validation.",
            "Use with contextcore manifest export outputs and plan-ingestion preflight checks.",
            "Run a2a-check-pipeline after export (Gate 1) and a2a-diagnose after ingestion (Gate 2).",
        ],
    }

    startd8_config: Dict[str, Any] = {
        "plan_path": str(plan_path),
        "output_dir": str(output_path),
        "complexity_threshold": complexity_threshold,
        "contextcore_export_dir": contextcore_export_dir,
        "requirements_files": requirement_files,
        "low_quality_policy": low_quality_policy,
        "min_export_coverage": min_export_coverage,
        "a2a_check_pipeline_gate": True,
        "enrichment_requirements": [
            "derivation_rules",
            "expected_output_contracts",
            "artifact_dependency_graph",
            "resolved_artifact_parameters",
            "file_ownership",
        ],
    }
    if route_policy in {"prime", "artisan"}:
        startd8_config["force_route"] = route_policy

    wayfinder_config: Dict[str, Any] = {
        "schema": "contextcore.io/wayfinder-create-config/v1",
        "project_id": project_id,
        "plan_path": str(plan_path),
        "create_spec_path": str(create_spec_path),
        "gates_path": str(gates_path),
        "contextcore_export_dir_expected": contextcore_export_dir,
    }

    manifest_scaffold_data = build_v2_manifest_template(project_id)
    manifest_scaffold_data["spec"]["project"]["name"] = display_name

    if dry_run:
        click.echo("=== DRY RUN - manifest create preview ===\n")
        click.echo(f"Project: {project_id}")
        click.echo(f"Output dir: {output_path}")
        click.echo(f"Draft mode: {draft_plan_mode}")
        if interactive:
            click.echo("Note: --interactive is reserved; command currently emits deterministic artifacts.")
        click.echo("\nFiles to emit:")
        for fp in target_files:
            click.echo(f"  - {fp}")
        click.echo("\nPLAN-draft.md preview:")
        click.echo(plan_draft[:1200] + ("..." if len(plan_draft) > 1200 else ""))
        click.echo("\ncreate-spec.json preview:")
        click.echo(json.dumps(create_spec, indent=2)[:1200] + "...")
        if write_manifest_scaffold:
            scaffold_yaml = yaml.dump(
                manifest_scaffold_data, default_flow_style=False, sort_keys=False
            )
            click.echo("\nmanifest scaffold preview:")
            click.echo(scaffold_yaml[:1000] + ("..." if len(scaffold_yaml) > 1000 else ""))
        click.echo("\n=== End Preview ===")
        return

    plan_path.write_text(plan_draft, encoding="utf-8")
    create_spec_path.write_text(json.dumps(create_spec, indent=2), encoding="utf-8")
    gates_path.write_text(json.dumps(create_gates, indent=2), encoding="utf-8")
    if emit_startd8_config:
        startd8_config_path.write_text(json.dumps(startd8_config, indent=2), encoding="utf-8")
    if emit_wayfinder_config:
        wayfinder_config_path.write_text(json.dumps(wayfinder_config, indent=2), encoding="utf-8")
    if write_manifest_scaffold:
        manifest_yaml = yaml.dump(
            manifest_scaffold_data, default_flow_style=False, sort_keys=False
        )
        manifest_scaffold.write_text(manifest_yaml, encoding="utf-8")

    click.echo(f"✓ Created manifest planning artifacts in {output_path}/")
    click.echo(f"  1. {plan_filename} - Draft plan for startd8 plan-ingestion")
    click.echo(f"  2. {create_spec_filename} - Requirements and routing contract")
    click.echo(f"  3. {gates_filename} - Pre-ingestion quality gates")
    if emit_startd8_config:
        click.echo(f"  4. {startd8_config_filename} - startd8 plan-ingestion config")
    if emit_wayfinder_config:
        click.echo(f"  5. {wayfinder_config_filename} - Optional wayfinder run config")
    if write_manifest_scaffold:
        click.echo(f"  6. {manifest_scaffold} - v2 context manifest scaffold")

    click.echo("\nNext steps:")
    click.echo("  1. Refine PLAN-draft.md with concrete requirement descriptions and acceptance criteria")
    click.echo("  2. Run: contextcore install init")
    click.echo("  3. Run: contextcore manifest export -p .contextcore.yaml -o ./out/export --emit-provenance")
    click.echo("  4. Run: contextcore contract a2a-check-pipeline ./out/export  (Gate 1 validation)")
    click.echo(f"  5. Run: startd8 workflow run plan-ingestion --config {startd8_config_path}")
    click.echo("  6. Run: contextcore contract a2a-diagnose ./out/export --ingestion-dir ./out/plan-ingestion  (Gate 2 validation)")


@manifest.command(name="init-from-plan")
@click.option(
    "--plan",
    required=True,
    type=click.Path(exists=True),
    help="Path to a plan document (markdown/text)",
)
@click.option(
    "--requirements",
    multiple=True,
    type=click.Path(exists=True),
    help="Path(s) to requirements documents (can specify multiple)",
)
@click.option(
    "--project-root",
    type=click.Path(exists=True),
    help="Project root path for contextual inference (target naming, repo context)",
)
@click.option(
    "--output",
    "-o",
    default=".contextcore.yaml",
    help="Output path for generated manifest",
)
@click.option(
    "--name",
    help="Override inferred manifest name (defaults to project root basename or output stem)",
)
@click.option(
    "--report-out",
    type=click.Path(),
    help="Path to write init-from-plan inference report JSON",
)
@click.option(
    "--strict-quality/--no-strict-quality",
    default=True,
    help="Require minimum inference quality (default: enabled)",
)
@click.option(
    "--emit-guidance-questions/--no-emit-guidance-questions",
    default=True,
    help="Extract plan questions into guidance.questions (default: enabled)",
)
@click.option(
    "--validate/--no-validate",
    "validate_after_write",
    default=True,
    help="Validate generated manifest after write (default: enabled)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing output file",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview inferred output and report without writing files",
)
def init_from_plan(
    plan: str,
    requirements: tuple,
    project_root: Optional[str],
    output: str,
    name: Optional[str],
    report_out: Optional[str],
    strict_quality: bool,
    emit_guidance_questions: bool,
    validate_after_write: bool,
    force: bool,
    dry_run: bool,
):
    """
    Initialize a v2 manifest from plan + requirements with programmatic inference.

    This is a scaffold command that translates plan/requirements text into
    structured .contextcore.yaml fields to reduce manual bootstrap work.
    """
    output_path = Path(output)
    if output_path.exists() and not force and not dry_run:
        click.echo(f"✗ File already exists: {output}", err=True)
        click.echo("  Use --force to overwrite", err=True)
        sys.exit(1)

    inferred_name = name
    if not inferred_name:
        if project_root:
            inferred_name = Path(project_root).name
        else:
            inferred_name = output_path.stem.replace(".contextcore", "")
    inferred_name = inferred_name.strip().lower().replace(" ", "-")

    manifest_data = build_v2_manifest_template(inferred_name)

    plan_text = Path(plan).read_text(encoding="utf-8")
    req_text = "\n\n".join(
        Path(req).read_text(encoding="utf-8") for req in requirements
    ) if requirements else ""

    inference = infer_init_from_plan(
        manifest_data=manifest_data,
        plan_text=plan_text,
        requirements_text=req_text,
        project_root=project_root,
        emit_guidance_questions=emit_guidance_questions,
    )
    manifest_data = inference["manifest_data"]
    inference_warnings = list(inference["warnings"])

    report = {
        "version": "1.1.0",
        "schema": "contextcore.io/init-from-plan-report/v1",
        "generated_at": datetime.now().isoformat(),
        "inputs": {
            "plan": plan,
            "requirements": list(requirements),
            "project_root": project_root,
        },
        "output_manifest": str(output_path),
        "strict_quality": strict_quality,
        "inferences": inference["inferences"],
        "core_inferred_count": inference["core_inferred_count"],
        "warnings": inference_warnings,
        "downstream_readiness": inference.get("downstream_readiness"),
    }

    if strict_quality and inference["core_inferred_count"] < 3:
        report["status"] = "failed_quality_gate"
        report["quality_gate_reason"] = (
            "Fewer than 3 core fields were inferred. "
            "Provide richer plan/requirements or use --no-strict-quality."
        )
        if not report_out:
            report_out = str(output_path.with_suffix(".init-from-plan-report.json"))
        Path(report_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        click.echo("✗ init-from-plan strict-quality gate failed", err=True)
        click.echo(f"  Report written: {report_out}", err=True)
        sys.exit(1)

    manifest_yaml = yaml.dump(manifest_data, default_flow_style=False, sort_keys=False)
    if dry_run:
        click.echo("=== DRY RUN - init-from-plan preview ===")
        click.echo(manifest_yaml[:1500] + ("..." if len(manifest_yaml) > 1500 else ""))
        report["status"] = "dry_run"
    else:
        output_path.write_text(manifest_yaml, encoding="utf-8")
        report["status"] = "written"
        if validate_after_write:
            errors, warnings, _ = _validate_manifest(str(output_path), strict=False)
            if errors:
                report["status"] = "validation_failed"
                report["validation_errors"] = errors
                if not report_out:
                    report_out = str(output_path.with_suffix(".init-from-plan-report.json"))
                Path(report_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
                click.echo(f"✗ Generated manifest failed validation: {output}", err=True)
                for e in errors:
                    click.echo(f"  ✗ {e}", err=True)
                sys.exit(1)
            if warnings:
                report["validation_warnings"] = warnings

    if not report_out:
        report_out = str(output_path.with_suffix(".init-from-plan-report.json"))
    Path(report_out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    if dry_run:
        click.echo(f"✓ Dry run complete. Report written: {report_out}")
    else:
        click.echo(f"✓ Created v2 manifest from plan: {output}")
        click.echo(f"  Name: {inferred_name}")
        click.echo(f"  Inferences: {len(inference['inferences'])}")
        click.echo(f"  Report: {report_out}")

    # Display downstream readiness assessment
    readiness = inference.get("downstream_readiness")
    if readiness:
        verdict = readiness["verdict"]
        score = readiness["score"]
        verdict_display = {
            "ready": "✓ ready",
            "needs_enrichment": "⚠ needs enrichment",
            "insufficient": "✗ insufficient",
        }.get(verdict, verdict)
        click.echo(f"\n  Downstream readiness: {verdict_display} (score: {score}/100)")
        a2a = readiness.get("a2a_gate_readiness", {})
        for gate_name, gate_status in a2a.items():
            icon = "✓" if gate_status == "ready" else "⚠" if gate_status == "at_risk" else "✗"
            click.echo(f"    {icon} {gate_name}: {gate_status}")
        click.echo(f"  Estimated artifacts: ~{readiness.get('estimated_artifact_count', 0)}")
        click.echo(f"\n  Next steps:")
        click.echo(f"    1. Edit {output} to refine inferred values")
        click.echo(f"    2. Run: contextcore manifest validate --path {output}")
        click.echo(f"    3. Run: contextcore install init")
        click.echo(f"    4. Run: contextcore manifest export -p {output} -o ./out/export --emit-provenance")
        click.echo(f"    5. Run: contextcore contract a2a-check-pipeline ./out/export")


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
    "--strict-quality/--no-strict-quality",
    default=None,
    help="Enable strict quality safeguards (default: enabled)",
)
@click.option(
    "--deterministic-output/--no-deterministic-output",
    default=None,
    help="Enable deterministic artifact ordering/serialization (default: enabled in strict quality profile)",
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
@click.option(
    "--emit-onboarding/--no-onboarding",
    "emit_onboarding",
    default=True,
    help="Write onboarding-metadata.json for plan ingestion (default: enabled). Use --no-onboarding to opt out.",
)
@click.option(
    "--min-coverage",
    type=float,
    default=None,
    help="Fail if overall coverage is below this percentage (e.g., 80). Omit to allow any coverage.",
)
@click.option(
    "--task-mapping",
    type=click.Path(exists=True),
    default=None,
    help="Path to JSON file mapping artifact IDs to task IDs (e.g., {\"checkout_api-dashboard\": \"PI-019\"}).",
)
@click.option(
    "--emit-quality-report/--no-emit-quality-report",
    default=None,
    help="Write export-quality-report.json with strict-quality gate outcomes",
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
    strict_quality: Optional[bool],
    deterministic_output: Optional[bool],
    emit_provenance: bool,
    embed_provenance: bool,
    emit_onboarding: bool,
    min_coverage: Optional[float],
    task_mapping: Optional[str],
    emit_quality_report: Optional[bool],
):
    """
    Export CRD and Artifact Manifest for Wayfinder implementations.

    This is Step 2 in the 7-step A2A governance-aware pipeline:
    init -> export -> a2a-check-pipeline (Gate 1) -> plan-ingestion ->
    a2a-diagnose (Gate 2) -> contractor execution -> finalize (Gate 3)

    This command generates two core files plus enrichment metadata:
    1. ProjectContext CRD (not applied, just YAML)
    2. Artifact Manifest (defines what observability artifacts are needed)

    The Artifact Manifest serves as the CONTRACT between ContextCore (which knows
    WHAT artifacts are needed) and Wayfinder (which knows HOW to create them).

    Provenance tracking (recommended for A2A governance):
    - Use --emit-provenance to write provenance.json with full audit trail
    - Required for A2A pipeline checker (Gate 1) checksum-chain validation
    - Provenance includes: git context, timestamps, checksums, CLI args

    Programmatic onboarding:
    - Onboarding metadata (onboarding-metadata.json) is written by default
    - Includes enrichment fields: derivation_rules, expected_output_contracts,
      artifact_dependency_graph, open_questions, file_ownership
    - Use --no-onboarding to opt out
    - Validation report (validation-report.json) is always written

    After export, run A2A governance validation:
        contextcore contract a2a-check-pipeline ./output   # Gate 1: 6 integrity checks
        contextcore contract a2a-diagnose ./output          # Gate 2: Three Questions

    Example:
        contextcore manifest export -p .contextcore.yaml -o ./output --emit-provenance
        contextcore manifest export -p .contextcore.yaml -o ./output --no-onboarding
        contextcore manifest export -p .contextcore.yaml -o ./output --dry-run

    This creates:
        ./output/my-project-projectcontext.yaml
        ./output/my-project-artifact-manifest.yaml
        ./output/provenance.json (if --emit-provenance — recommended)
        ./output/onboarding-metadata.json (default; use --no-onboarding to skip)
        ./output/validation-report.json (always)
    """
    from datetime import datetime as dt

    from contextcore.models.manifest_loader import load_manifest, detect_manifest_version
    from contextcore.models.manifest_v2 import ContextManifestV2

    # Capture start time for duration tracking
    start_time = dt.now()
    policy = load_quality_policy(path)

    try:
        # Pre-flight validation: fail early if manifest is invalid
        errors, warnings, _ = _validate_manifest(path, strict=False)
        if errors:
            click.echo(f"✗ Manifest validation failed before export:", err=True)
            for e in errors:
                click.echo(f"  ✗ {e}", err=True)
            sys.exit(1)

        strict_quality, deterministic_output, emit_quality_report = resolve_export_quality_toggles(
            policy=policy,
            strict_quality=strict_quality,
            deterministic_output=deterministic_output,
            emit_quality_report=emit_quality_report,
        )

        ci_violation = evaluate_ci_policy(strict_quality=strict_quality, policy=policy)
        if ci_violation:
            click.echo(ci_violation["headline"], err=True)
            click.echo(ci_violation["detail"], err=True)
            sys.exit(1)

        profile = apply_strict_quality_profile(
            strict_quality=strict_quality,
            policy=policy,
            min_coverage=min_coverage,
            task_mapping=task_mapping,
            scan_existing=scan_existing,
            emit_provenance=emit_provenance,
            embed_provenance=embed_provenance,
        )
        if not profile["ok"]:
            for line in profile["errors"]:
                click.echo(line, err=True)
            sys.exit(1)
        for warning in profile["warnings"]:
            click.echo(warning)
        min_coverage = profile["min_coverage"]
        emit_provenance = profile["emit_provenance"]
        embed_provenance = profile["embed_provenance"]

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

        schema_pin_error = validate_manifest_api_pin(
            strict_quality=strict_quality,
            policy=policy,
            raw_data=raw_data,
        )
        if schema_pin_error:
            click.echo(schema_pin_error, err=True)
            sys.exit(1)

        existing_artifacts, existing_warnings = parse_existing_artifacts(existing)
        for warning in existing_warnings:
            click.echo(warning, err=True)

        # Scan existing directory if provided
        if scan_existing:
            scan_path = Path(scan_existing)
            click.echo(f"Scanning for existing artifacts in {scan_path}...")
            scanned = scan_existing_artifacts(scan_path)
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
        if deterministic_output:
            artifact_manifest.artifacts = sorted(
                artifact_manifest.artifacts, key=lambda a: a.id
            )

        # Load task mapping if provided
        artifact_task_mapping, task_mapping_warning = load_artifact_task_mapping(task_mapping)
        if task_mapping_warning:
            click.echo(task_mapping_warning, err=True)
        mapping_errors = validate_required_task_mapping(
            strict_quality=strict_quality,
            artifact_manifest=artifact_manifest,
            artifact_task_mapping=artifact_task_mapping,
        )
        if mapping_errors:
            for line in mapping_errors:
                click.echo(line, err=True)
            sys.exit(1)

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
                "emit_onboarding": emit_onboarding,
                "min_coverage": min_coverage,
                "task_mapping": task_mapping,
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

        artifact_content = render_artifact_content(artifact_manifest, output_format)

        from contextcore.utils.onboarding import (
            build_onboarding_metadata,
            build_validation_report,
        )

        onboarding_metadata = build_onboarding_metadata(
            artifact_manifest=artifact_manifest,
            artifact_manifest_path=artifact_filename,
            project_context_path=crd_filename,
            provenance=provenance,
            artifact_manifest_content=artifact_content,
            project_context_content=crd_yaml,
            source_path=path,
            artifact_task_mapping=artifact_task_mapping,
            output_dir=str(output_path),
        )
        validation_report = build_validation_report(
            onboarding_metadata=onboarding_metadata,
            min_coverage=min_coverage,
        )
        generated_schema_error = validate_export_schema_pins(
            strict_quality=strict_quality,
            policy=policy,
            onboarding_metadata=onboarding_metadata,
            validation_report=validation_report,
        )
        if generated_schema_error:
            click.echo(generated_schema_error, err=True)
            sys.exit(1)

        policy_file = find_quality_policy_file(path)
        quality_report = build_export_quality_report(
            path=path,
            strict_quality=strict_quality,
            deterministic_output=deterministic_output,
            min_coverage=min_coverage,
            profile=profile,
            policy_file=str(policy_file) if policy_file else None,
            validation_report=validation_report,
        )

        if dry_run:
            preview_export(
                crd_filename=crd_filename,
                crd_yaml=crd_yaml,
                artifact_filename=artifact_filename,
                artifact_content=artifact_content,
                provenance=provenance,
                emit_onboarding=emit_onboarding,
                onboarding_metadata=onboarding_metadata,
                validation_report=validation_report,
                emit_quality_report=emit_quality_report,
                quality_report=quality_report,
                artifact_manifest=artifact_manifest,
            )
            coverage_error = enforce_min_coverage(min_coverage, artifact_manifest)
            if coverage_error:
                click.echo(coverage_error, err=True)
                sys.exit(1)
            return

        file_results = write_export_outputs(
            output_path=output_path,
            crd_filename=crd_filename,
            crd_yaml=crd_yaml,
            artifact_filename=artifact_filename,
            artifact_content=artifact_content,
            emit_provenance=emit_provenance,
            provenance=provenance,
            emit_onboarding=emit_onboarding,
            onboarding_metadata=onboarding_metadata,
            validation_report=validation_report,
            emit_quality_report=emit_quality_report,
            quality_report=quality_report,
            output_files=output_files,
        )
        print_export_success(
            output_path=output_path,
            crd_filename=crd_filename,
            artifact_filename=artifact_filename,
            provenance_file=file_results["provenance_file"],
            onboarding_file=file_results["onboarding_file"],
            quality_path=file_results["quality_path"],
            artifact_manifest=artifact_manifest,
            provenance=provenance,
        )
        coverage_error = enforce_min_coverage(min_coverage, artifact_manifest)
        if coverage_error:
            click.echo(coverage_error, err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

