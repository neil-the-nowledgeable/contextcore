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
    atomic_write_with_backup,
)
from contextcore.cli.analyze_plan_ops import analyze_plan
from contextcore.cli.init_from_plan_ops import (
    build_v2_manifest_template,
    enrich_template_from_capability_index,
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


@manifest.command()
@click.option(
    "--path",
    "-p",
    required=True,
    type=click.Path(exists=True),
    help="Path to the manifest file",
)
@click.option(
    "--interactive",
    is_flag=True,
    help="Prompt for each open question interactively",
)
@click.option(
    "--answers",
    type=click.Path(exists=True),
    help="YAML/JSON file with pre-resolved answers (question_id -> answer)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report issues without writing changes",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def fix(path: str, interactive: bool, answers: str, dry_run: bool, output_format: str):
    """
    Fix resolvable issues in a context manifest.

    Currently fixes:
    - Open questions (status=open) by setting status=answered

    Two modes:
    - --interactive: prompts for each open question
    - --answers FILE: batch mode using a YAML/JSON answers file

    Without either flag, reports fixable issues and exits.

    Example:
        contextcore manifest fix --path .contextcore.yaml --answers answers.yaml
        contextcore manifest fix --path .contextcore.yaml --interactive
        contextcore manifest fix --path .contextcore.yaml --dry-run
    """
    from contextcore.cli.manifest_fix_ops import (
        apply_manifest_fixes,
        detect_manifest_issues,
        resolve_questions_from_file,
        resolve_questions_interactive,
    )

    # 1. Detect issues
    report = detect_manifest_issues(path)

    if report.total_issues == 0:
        if output_format == "json":
            click.echo(json.dumps({"status": "nothing_to_fix", "path": path, "issues": 0}))
        else:
            click.echo(f"Nothing to fix: {path}")
        sys.exit(0)

    # 2. Report issues
    if output_format == "text":
        click.echo(f"Found {report.total_issues} fixable issue(s) in {path}")
        if report.open_questions:
            click.echo(f"\n  Open questions ({len(report.open_questions)}):")
            for q in report.open_questions:
                click.echo(f"    [{q['id']}] {q['question'][:60]}...")

    # 3. Resolve
    resolutions = []
    if interactive:
        resolutions = resolve_questions_interactive(report.open_questions)
    elif answers:
        resolutions, unmatched = resolve_questions_from_file(report.open_questions, answers)
        if unmatched and output_format == "text":
            click.echo(f"\n  Unmatched questions (no answer provided): {', '.join(unmatched)}")
    else:
        # Report-only mode
        if output_format == "json":
            click.echo(json.dumps({
                "status": "report_only",
                "path": path,
                "open_questions": report.open_questions,
                "total_issues": report.total_issues,
            }, indent=2))
        else:
            click.echo("\n  Use --interactive or --answers <file> to resolve.")
        sys.exit(0)

    if not resolutions:
        if output_format == "text":
            click.echo("\n  No resolutions provided. Nothing changed.")
        sys.exit(0)

    # 4. Apply
    result = apply_manifest_fixes(path, resolutions, dry_run=dry_run)

    # 5. Output results
    if output_format == "json":
        click.echo(json.dumps({
            "status": "dry_run" if dry_run else "applied",
            "path": path,
            "fixed": result.fixed_count,
            "skipped": result.skipped_count,
            "actions": result.actions,
        }, indent=2))
    else:
        if dry_run:
            click.echo(f"\n  [DRY RUN] Would fix {result.fixed_count} question(s)")
        else:
            click.echo(f"\n  Fixed {result.fixed_count} question(s)")
        if result.skipped_count > 0:
            click.echo(f"  Skipped {result.skipped_count} open question(s) (no answer provided)")
        for action in result.actions:
            click.echo(f"    {action['question_id']}: {action['old_status']} -> answered ({action['source']})")

    # 6. Post-fix validation (non-blocking)
    if not dry_run and result.fixed_count > 0:
        errors, warnings, _ = _validate_manifest(path, strict=False)
        if errors:
            if output_format == "text":
                click.echo(f"\n  Post-fix validation errors:")
                for e in errors:
                    click.echo(f"    {e}")
        elif output_format == "text":
            click.echo("  Post-fix validation: passed")


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
@click.option(
    "--document-write-strategy",
    type=click.Choice(["update_existing", "new_output"]),
    default="update_existing",
    help="Strategy for writing output documents (default: update_existing)",
)
def init(
    path: str,
    name: str,
    manifest_version: str,
    force: bool,
    validate_after_write: bool,
    document_write_strategy: str,
):
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
        enrich_template_from_capability_index(manifest_data)
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
    
    use_backup = (document_write_strategy == "update_existing")
    atomic_write_with_backup(path_obj, manifest_yaml, backup=use_backup)

    # Emit provenance
    from contextcore.utils.provenance import build_run_provenance_payload, write_provenance_file
    import shutil
    
    output_dir = path_obj.parent
    run_payload = build_run_provenance_payload(
        workflow_or_command="manifest init",
        inputs=[], 
        outputs=[str(path_obj.resolve())],
        config_snapshot={
            "name": name,
            "manifest_version": manifest_version,
            "force": force
        }
    )
    
    prov_path = output_dir / "init-run-provenance.json"
    if prov_path.exists() and use_backup:
        shutil.copy2(prov_path, prov_path.with_suffix(".json.bak"))
        
    write_provenance_file(run_payload, str(output_dir), filename="init-run-provenance.json")

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
    click.echo(f"  6. Run: startd8 workflow run plan-ingestion, then contextcore contract a2a-diagnose")


def _detect_context_propagation(requirements_text: str) -> Dict[str, Any]:
    """Detect context propagation patterns in requirements text.

    Returns a dict with ``detected`` (bool), ``matched_groups`` (list of
    signal-group names), and ``recommendation`` (str or None).

    Defense-in-depth: this runs at *create* time so the generated plan can
    include a self-validation scaffold.  ``polish`` performs the same
    detection at *review* time.
    """
    from contextcore.cli.polish import _PROPAGATION_SIGNALS, _PROPAGATION_DETECTION_THRESHOLD

    matched_groups: List[str] = []
    for group_name, patterns in _PROPAGATION_SIGNALS.items():
        for pattern in patterns:
            if re.search(pattern, requirements_text, re.IGNORECASE):
                matched_groups.append(group_name)
                break

    detected = len(matched_groups) >= _PROPAGATION_DETECTION_THRESHOLD
    recommendation = None
    if detected:
        recommendation = (
            "Requirements contain context propagation patterns "
            f"(signals: {', '.join(matched_groups)}). "
            "Consider adding a 'Self-Validating Gap Verification' section to "
            "the plan where each identified gap maps to a runtime integration "
            "check (SV-*) that fails before the fix and passes after."
        )
    return {
        "detected": detected,
        "matched_groups": matched_groups,
        "recommendation": recommendation,
    }


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
    propagation_detection = _detect_context_propagation(requirements_text)

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
        "defense_in_depth_layers": [
            {
                "id": "preflight",
                "name": "Pre-Flight Validation",
                "module": "contracts.preflight",
                "phase": "BEFORE",
                "blocking": True,
            },
            {
                "id": "runtime",
                "name": "Runtime Guards",
                "module": "contracts.runtime",
                "phase": "DURING",
                "blocking": True,
            },
            {
                "id": "postexec",
                "name": "Post-Execution Checks",
                "module": "contracts.postexec",
                "phase": "AFTER",
                "blocking": False,
            },
            {
                "id": "observability",
                "name": "Observability Contracts",
                "module": "contracts.observability",
                "phase": "CONTINUOUS",
                "blocking": False,
            },
            {
                "id": "regression",
                "name": "Regression Detection",
                "module": "contracts.regression",
                "phase": "CI_CD",
                "blocking": True,
            },
        ],
        "contract_domains": {
            "implemented": [
                {"id": "propagation", "module": "contracts.propagation", "description": "Context propagation chain validation"},
                {"id": "schema_compat", "module": "contracts.schema_compat", "description": "Schema compatibility checks"},
            ],
            "designed_not_implemented": [
                {"id": "semconv", "design_doc": "docs/design/requirements/REQ_CONCERN_*"},
                {"id": "ordering", "design_doc": "docs/design/requirements/REQ_CONCERN_*"},
                {"id": "capability", "design_doc": "docs/design/requirements/REQ_CONCERN_*"},
                {"id": "budget", "design_doc": "docs/design/requirements/REQ_CONCERN_*"},
                {"id": "lineage", "design_doc": "docs/design/requirements/REQ_CONCERN_*"},
            ],
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
                "P1: Prescriptive Over Descriptive — contracts declare what MUST happen, not what DID happen",
                "P2: Design Time Over Runtime — catch violations at declaration, not in production",
                "P3: Composable Enforcement — each layer operates independently, failures don't cascade",
                "P4: Observable by Default — every contract check emits OTel spans/events",
                "P5: Opt-In Complexity — start with propagation+schema, add lifecycle layers as needed",
                "P6: Three Questions Diagnostic Ordering — Q1 export, Q2 ingestion, Q3 execution",
            ],
            "reference": "docs/design/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md",
        },
        "context_propagation_detection": {
            "detected": propagation_detection["detected"],
            "matched_groups": propagation_detection["matched_groups"],
            "recommendation": propagation_detection["recommendation"],
            "suggested_lifecycle_layers": (
                ["preflight", "runtime", "postexec"]
                if propagation_detection["detected"]
                else []
            ),
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

    if propagation_detection["detected"]:
        click.echo(
            click.style(
                "\n  Context propagation pattern detected in requirements.",
                fg="cyan",
                bold=True,
            )
        )
        click.echo(
            f"  Signals: {', '.join(propagation_detection['matched_groups'])}"
        )
        click.echo(
            "  Recommendation: Add a 'Self-Validating Gap Verification' section to the plan."
        )
        click.echo(
            "  Each identified gap should map to a runtime integration check (SV-*) that"
        )
        click.echo(
            "  fails before the fix and passes after — the plan-as-its-own-test-harness pattern."
        )
        click.echo(
            "  Run `contextcore polish PLAN-draft.md` after editing to verify."
        )

    click.echo("\nNext steps:")
    click.echo("  1. Refine PLAN-draft.md with concrete requirement descriptions and acceptance criteria")
    if propagation_detection["detected"]:
        click.echo("  1b. Add self-validating gap verification section (context propagation detected)")
    click.echo("  2. Run: contextcore polish PLAN-draft.md --strict")
    click.echo("  3. Run: contextcore install init")
    click.echo("  4. Run: contextcore manifest export -p .contextcore.yaml -o ./out/export --emit-provenance")
    click.echo("  5. Run: contextcore contract a2a-check-pipeline ./out/export  (Gate 1 validation)")
    click.echo(f"  6. Run: startd8 workflow run plan-ingestion --config {startd8_config_path}")
    click.echo("  7. Run: contextcore contract a2a-diagnose ./out/export --ingestion-dir ./out/plan-ingestion  (Gate 2 validation)")


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
@click.option(
    "--document-write-strategy",
    type=click.Choice(["update_existing", "new_output"]),
    default="update_existing",
    help="Strategy for writing output documents (default: update_existing)",
)
@click.option(
    "--plan-analysis",
    "plan_analysis_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to plan-analysis.json from 'analyze-plan' stage (enriches inference)",
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
    document_write_strategy: str,
    plan_analysis_path: Optional[str],
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

    # Load plan analysis JSON if provided
    plan_analysis_data: Optional[Dict[str, Any]] = None
    if plan_analysis_path:
        plan_analysis_data = json.loads(Path(plan_analysis_path).read_text(encoding="utf-8"))
        click.echo(f"  Loaded plan analysis: {plan_analysis_path}")

    inference = infer_init_from_plan(
        manifest_data=manifest_data,
        plan_text=plan_text,
        requirements_text=req_text,
        project_root=project_root,
        emit_guidance_questions=emit_guidance_questions,
        plan_analysis=plan_analysis_data,
    )
    manifest_data = inference["manifest_data"]
    inference_warnings = list(inference["warnings"])

    # Preserve resolved questions from existing manifest (if overwriting)
    if output_path.exists() and force:
        try:
            existing = yaml.safe_load(output_path.read_text(encoding="utf-8")) or {}
            existing_questions = (existing.get("guidance") or {}).get("questions") or []
            resolved = {q["id"]: q for q in existing_questions if q.get("status") != "open"}
            if resolved:
                new_questions = (manifest_data.get("guidance") or {}).get("questions") or []
                for q in new_questions:
                    prev = resolved.pop(q["id"], None)
                    if prev:
                        q["status"] = prev["status"]
                        if "answer" in prev:
                            q["answer"] = prev["answer"]
                # Append resolved questions whose IDs no longer exist in the new set
                if resolved:
                    new_questions.extend(resolved.values())
                manifest_data.setdefault("guidance", {})["questions"] = new_questions
        except Exception:
            pass  # Best-effort; don't block regeneration

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

    use_backup = (document_write_strategy == "update_existing")

    if strict_quality and inference["core_inferred_count"] < 3:
        report["status"] = "failed_quality_gate"
        report["quality_gate_reason"] = (
            "Fewer than 3 core fields were inferred. "
            "Provide richer plan/requirements or use --no-strict-quality."
        )
        if not report_out:
            report_out = str(output_path.with_suffix(".init-from-plan-report.json"))
        atomic_write_with_backup(Path(report_out), json.dumps(report, indent=2), backup=use_backup)
        click.echo("✗ init-from-plan strict-quality gate failed", err=True)
        click.echo(f"  Report written: {report_out}", err=True)
        sys.exit(1)

    manifest_yaml = yaml.dump(manifest_data, default_flow_style=False, sort_keys=False)
    if dry_run:
        click.echo("=== DRY RUN - init-from-plan preview ===")
        click.echo(manifest_yaml[:1500] + ("..." if len(manifest_yaml) > 1500 else ""))
        report["status"] = "dry_run"
    else:
        atomic_write_with_backup(output_path, manifest_yaml, backup=use_backup)
        report["status"] = "written"
        if validate_after_write:
            errors, warnings, _ = _validate_manifest(str(output_path), strict=False)
            if errors:
                report["status"] = "validation_failed"
                report["validation_errors"] = errors
                if not report_out:
                    report_out = str(output_path.with_suffix(".init-from-plan-report.json"))
                atomic_write_with_backup(Path(report_out), json.dumps(report, indent=2), backup=use_backup)
                click.echo(f"✗ Generated manifest failed validation: {output}", err=True)
                for e in errors:
                    click.echo(f"  ✗ {e}", err=True)
                sys.exit(1)
            if warnings:
                report["validation_warnings"] = warnings

    if not report_out:
        report_out = str(output_path.with_suffix(".init-from-plan-report.json"))
    
    if not dry_run:
        atomic_write_with_backup(Path(report_out), json.dumps(report, indent=2), backup=use_backup)
    else:
        # For dry run just print or don't write report? 
        # Original code wrote report even in dry run? 
        # "Preview inferred output and report without writing files" says dry-run help.
        # But original code:
        # Path(report_out).write_text(...)
        # Wait, check original code below.
        pass

    if not dry_run:
        from contextcore.utils.provenance import build_run_provenance_payload, write_provenance_file
        import shutil
        
        prov_inputs = [str(Path(plan).resolve())]
        for r in requirements:
            prov_inputs.append(str(Path(r).resolve()))
        if project_root:
            prov_inputs.append(str(Path(project_root).resolve()))
            
        prov_outputs = [str(output_path.resolve()), str(Path(report_out).resolve())]
        
        run_payload = build_run_provenance_payload(
            workflow_or_command="manifest init-from-plan",
            inputs=prov_inputs,
            outputs=prov_outputs,
            quality_summary={
                "core_inferred_count": inference["core_inferred_count"],
                "downstream_readiness": inference.get("downstream_readiness", {}).get("verdict"),
                "strict_quality": strict_quality
            }
        )
        
        prov_dir = output_path.parent
        prov_path = prov_dir / "init-run-provenance.json"
        if prov_path.exists() and use_backup:
            shutil.copy2(prov_path, prov_path.with_suffix(".json.bak"))
            
        write_provenance_file(run_payload, str(prov_dir), filename="init-run-provenance.json")

    if dry_run:
        click.echo(f"✓ Dry run complete. Report preview: {report_out} (not written)")
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
        click.echo(f"    6. Run: startd8 workflow run plan-ingestion, then contextcore contract a2a-diagnose")


@manifest.command(name="analyze-plan")
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
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output path for plan-analysis.json (default: <output-dir>/plan-analysis.json)",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default=None,
    help="Output directory (default: same dir as plan)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview analysis output without writing files",
)
def analyze_plan_cmd(
    plan: str,
    requirements: tuple,
    output: Optional[str],
    output_dir: Optional[str],
    dry_run: bool,
):
    """
    Analyze a plan document with its requirements (Stage 1.5).

    Produces plan-analysis.json with structured metadata: requirement inventory,
    phase metadata, traceability matrix, dependency graph, and conflict detection.

    This output can be fed to ``init-from-plan --plan-analysis`` for richer inference.

    Example:
        contextcore manifest analyze-plan \\
          --plan docs/plans/PLAN.md \\
          --requirements docs/plans/REQS_A.md \\
          --requirements docs/plans/REQS_B.md

    Then:
        contextcore manifest init-from-plan \\
          --plan docs/plans/PLAN.md \\
          --requirements docs/plans/REQS_A.md \\
          --requirements docs/plans/REQS_B.md \\
          --plan-analysis plan-analysis.json
    """
    plan_path = Path(plan)
    plan_text = plan_path.read_text(encoding="utf-8")

    requirements_docs = []
    for req_path in requirements:
        req_text = Path(req_path).read_text(encoding="utf-8")
        requirements_docs.append({"path": str(req_path), "text": req_text})

    result = analyze_plan(
        plan_text=plan_text,
        plan_path=str(plan_path),
        requirements_docs=requirements_docs,
    )

    # Determine output path
    if output:
        out_path = Path(output)
    elif output_dir:
        out_path = Path(output_dir) / "plan-analysis.json"
    else:
        out_path = plan_path.parent / "plan-analysis.json"

    result_json = json.dumps(result, indent=2, default=str)

    if dry_run:
        click.echo("=== DRY RUN - analyze-plan preview ===\n")
        click.echo(result_json[:2000] + ("..." if len(result_json) > 2000 else ""))
        click.echo(f"\nWould write to: {out_path}")
        click.echo("\n=== End Preview ===")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result_json, encoding="utf-8")

    # Register in provenance inventory if available
    try:
        from contextcore.utils.provenance import extend_inventory
        extend_inventory(
            output_dir=str(out_path.parent),
            stage="analyze-plan",
            entries=[
                {
                    "artifact": str(out_path.name),
                    "path": str(out_path),
                    "type": "plan-analysis",
                }
            ],
        )
    except Exception:
        pass  # Non-fatal: provenance integration is optional

    stats = result["statistics"]
    click.echo(f"✓ Plan analysis written: {out_path}")
    click.echo(f"  Requirements: {stats['total_requirements']} IDs across {len(requirements_docs)} doc(s)")
    click.echo(f"  Phases: {stats['total_phases']}")
    click.echo(f"  Coverage: {stats['covered_requirements']}/{stats['total_requirements']} requirements traced ({stats['coverage_ratio']:.0%})")
    conflicts = result.get("conflict_report", {})
    overlapping = conflicts.get("overlapping_ids", {})
    if overlapping:
        click.echo(f"  Overlapping IDs: {len(overlapping)} (shared across docs)")
    click.echo(f"\n  Next: contextcore manifest init-from-plan --plan-analysis {out_path}")


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
    "--service-metadata",
    type=click.Path(exists=True),
    default=None,
    help="Path to JSON file with per-service metadata (transport_protocol, schema_contract, etc.).",
)
@click.option(
    "--emit-quality-report/--no-emit-quality-report",
    default=None,
    help="Write export-quality-report.json with strict-quality gate outcomes",
)
@click.option(
    "--verify",
    is_flag=True,
    help="Run a2a-check-pipeline (Gate 1) on output after export. "
    "Fails with non-zero exit if any blocking gate fails.",
)
@click.option(
    "--emit-tasks",
    is_flag=True,
    help="Emit OTel task spans for each artifact in coverage gaps. "
    "Creates epic/story/task hierarchy and records task_trace_id in onboarding metadata.",
)
@click.option(
    "--project-id",
    default=None,
    help="Override project ID for task tracking (defaults to manifest project ID).",
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
    help="Emit run-provenance.json with run-level lineage (default: policy-driven)",
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
    service_metadata: Optional[str],
    emit_quality_report: Optional[bool],
    verify: bool,
    emit_tasks: bool,
    project_id: Optional[str],
    document_write_strategy: str,
    emit_run_provenance: Optional[bool],
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
    - Required for A2A pipeline checker provenance-consistency gate (gate 3 of 6)
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

        (
            strict_quality,
            deterministic_output,
            emit_quality_report,
            emit_run_provenance,
            document_write_strategy,
        ) = resolve_export_quality_toggles(
            policy=policy,
            strict_quality=strict_quality,
            deterministic_output=deterministic_output,
            emit_quality_report=emit_quality_report,
            emit_run_provenance=emit_run_provenance,
            document_write_strategy=document_write_strategy,
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
            emit_run_provenance=bool(emit_run_provenance),
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
        emit_run_provenance = profile["emit_run_provenance"]

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
        # REQ-CAP-007: Try capability-derived metrics first, fall back to hardcoded.
        _beaver_metrics_fallback = {
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
        _extra_metrics = _beaver_metrics_fallback
        _cap_index_dir_for_metrics = Path(path).resolve().parent / "docs" / "capability-index"
        _cap_index_dir_for_metrics_str = (
            str(_cap_index_dir_for_metrics) if _cap_index_dir_for_metrics.is_dir() else None
        )
        if _cap_index_dir_for_metrics_str:
            try:
                from contextcore.utils.capability_index import (
                    load_capability_index,
                    discover_expansion_pack_metrics,
                )
                _cap_idx = load_capability_index(Path(_cap_index_dir_for_metrics_str))
                if not _cap_idx.is_empty:
                    _discovered = discover_expansion_pack_metrics(_cap_idx)
                    if _discovered:
                        _extra_metrics = _discovered
            except Exception:
                pass  # Fall back to hardcoded
        artifact_manifest = manifest.generate_artifact_manifest(
            source_path=str(path),
            existing_artifacts=existing_artifacts,
            extra_metrics=_extra_metrics,
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

        # Load service metadata if provided
        parsed_service_metadata = None
        if service_metadata:
            try:
                with open(service_metadata, encoding="utf-8") as _sm_fh:
                    parsed_service_metadata = json.load(_sm_fh)
            except (json.JSONDecodeError, OSError) as exc:
                click.echo(f"Error reading --service-metadata: {exc}", err=True)
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
                "emit_run_provenance": emit_run_provenance,
                "run_provenance_path": str(output_path / "run-provenance.json"),
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

        # Resolve capability index directory for export enrichment
        _cap_index_dir = Path(path).resolve().parent / "docs" / "capability-index"
        _cap_index_dir_str = str(_cap_index_dir) if _cap_index_dir.is_dir() else None

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
            capability_index_dir=_cap_index_dir_str,
            service_metadata=parsed_service_metadata,
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

        # Collect run inputs
        run_inputs = [str(Path(path).resolve())]
        if task_mapping:
            run_inputs.append(str(Path(task_mapping).resolve()))
        if scan_existing:
             run_inputs.append(str(Path(scan_existing).resolve()))
        if policy_file:
             run_inputs.append(str(policy_file))

        # Extract capability index version for provenance (REQ-CAP-009)
        _cap_idx_version = None
        _cap_ctx = onboarding_metadata.get("capability_context")
        if isinstance(_cap_ctx, dict):
            _cap_idx_version = _cap_ctx.get("index_version") or None

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
            run_provenance_inputs=run_inputs,
            document_write_strategy=document_write_strategy,
            emit_run_provenance=bool(emit_run_provenance),
            capability_index_version=_cap_idx_version,
        )
        print_export_success(
            output_path=output_path,
            crd_filename=crd_filename,
            artifact_filename=artifact_filename,
            provenance_file=file_results["provenance_file"],
            onboarding_file=file_results["onboarding_file"],
            quality_path=file_results["quality_path"],
            run_provenance_file=file_results.get("run_provenance_file"),
            artifact_manifest=artifact_manifest,
            provenance=provenance,
        )
        coverage_error = enforce_min_coverage(min_coverage, artifact_manifest)
        if coverage_error:
            click.echo(coverage_error, err=True)
            sys.exit(1)

        # --emit-tasks: create OTel task spans for coverage gaps
        if emit_tasks and not dry_run:
            click.echo("\n--- Emit Tasks: creating OTel task spans ---")
            try:
                from contextcore.cli.export_task_emitter import emit_export_tasks

                task_result = emit_export_tasks(
                    artifact_manifest=artifact_manifest,
                    onboarding_metadata=onboarding_metadata,
                    project_id=project_id,
                    dry_run=False,
                )

                if task_result.errors:
                    click.echo(f"⚠ Task emission completed with errors (best-effort):")
                    for err in task_result.errors:
                        click.echo(f"  - {err}")
                else:
                    click.echo(f"✓ Emitted {task_result.total_tasks_emitted} task spans")
                    click.echo(f"  Stories: {task_result.stories_emitted}")
                    click.echo(f"  Tasks by status: {task_result.tasks_by_status}")
                    click.echo(f"  Trace ID: {task_result.task_trace_id}")

                # Re-write onboarding metadata with task_trace_id if it was updated
                if task_result.task_trace_id and emit_onboarding:
                    onboarding_path = output_path / "onboarding-metadata.json"
                    onboarding_path.write_text(
                        json.dumps(onboarding_metadata, indent=2, default=str),
                        encoding="utf-8",
                    )
                    click.echo(f"  Updated onboarding-metadata.json with task_trace_id")
            except Exception as te:
                # Task emission failure does not fail the export (R7.2)
                click.echo(f"⚠ Task emission failed (non-blocking): {te}")

        # --verify: run Gate 1 (a2a-check-pipeline) on the export output
        if verify:
            click.echo("\n--- Verify: running a2a-check-pipeline (Gate 1) ---")
            try:
                from contextcore.contracts.a2a.pipeline_checker import PipelineChecker

                checker = PipelineChecker(str(output_path))
                report = checker.run()
                click.echo(report.to_text())

                if not report.is_healthy:
                    click.echo(
                        "✗ --verify failed: pipeline integrity check is UNHEALTHY",
                        err=True,
                    )
                    sys.exit(1)
                else:
                    click.echo("✓ --verify passed: pipeline integrity HEALTHY")
            except Exception as ve:
                click.echo(
                    f"✗ --verify error: {ve}",
                    err=True,
                )
                sys.exit(1)

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

