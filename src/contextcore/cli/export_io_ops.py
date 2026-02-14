"""I/O and rendering helpers for `contextcore manifest export`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import click
import yaml


def parse_existing_artifacts(existing: tuple[str, ...]) -> tuple[dict[str, str], list[str]]:
    parsed: dict[str, str] = {}
    warnings: list[str] = []
    for item in existing:
        if ":" in item:
            artifact_id, artifact_path = item.split(":", 1)
            parsed[artifact_id] = artifact_path
        else:
            warnings.append(f"⚠ Invalid --existing format: {item} (expected 'id:path')")
    return parsed, warnings


def scan_existing_artifacts(scan_path: Path) -> dict[str, str]:
    """Scan a directory for existing observability artifacts."""
    existing: dict[str, str] = {}
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
            stem = file_path.stem
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
            service_id = service_name.replace("-", "_")
            artifact_id = f"{service_id}-{artifact_type.replace('_', '-')}"
            existing[artifact_id] = str(file_path)

    return existing


def load_artifact_task_mapping(task_mapping: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
    if not task_mapping:
        return None, None
    try:
        mapping = json.loads(Path(task_mapping).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"⚠ Could not load task mapping from {task_mapping}: {exc}"
    if not isinstance(mapping, dict):
        return None, None
    return mapping, None


def validate_required_task_mapping(
    strict_quality: bool,
    artifact_manifest: Any,
    artifact_task_mapping: Optional[dict],
) -> Optional[list[str]]:
    if not strict_quality:
        return None
    if artifact_task_mapping is None:
        return ["✗ Strict quality requires a valid task mapping JSON."]
    required_ids = sorted(
        a.id
        for a in artifact_manifest.artifacts
        if getattr(a.priority, "value", str(a.priority)) == "required"
    )
    missing_required = [aid for aid in required_ids if aid not in artifact_task_mapping]
    if missing_required:
        return [
            "✗ Strict quality requires 100% task mapping coverage for required artifacts.",
            f"  Missing required mappings: {', '.join(missing_required)}",
        ]
    return None


def render_artifact_content(artifact_manifest: Any, output_format: str) -> str:
    if output_format == "yaml":
        return yaml.dump(artifact_manifest.to_dict(), default_flow_style=False, sort_keys=False)
    return json.dumps(artifact_manifest.to_dict(), indent=2)


def build_export_quality_report(
    path: str,
    strict_quality: bool,
    deterministic_output: bool,
    min_coverage: Optional[float],
    profile: Dict[str, Any],
    policy_file: Optional[str],
    validation_report: Dict[str, Any],
) -> Dict[str, Any]:
    from datetime import datetime as dt

    return {
        "version": "1.0.0",
        "schema": "contextcore.io/export-quality-report/v1",
        "generated_at": dt.now().isoformat(),
        "strict_quality": strict_quality,
        "deterministic_output": deterministic_output,
        "policy_file": policy_file,
        "policy_effective": {
            "coverage_threshold_env": profile["environment"],
            "min_coverage": min_coverage,
            "scan_path_allowlist": profile["allowlist"],
        },
        "gates": {
            "manifest_validation_passed": True,
            "required_task_mapping_complete": True,
            "schema_pins_passed": True,
            "coverage_meets_minimum": validation_report.get("coverage", {}).get("meets_minimum", True),
        },
        "coverage": validation_report.get("coverage", {}),
        "diagnostics": validation_report.get("diagnostics", []),
    }


def print_coverage_summary(artifact_manifest: Any) -> None:
    coverage = artifact_manifest.coverage
    click.echo("\n  Coverage Summary:")
    click.echo(f"    Overall: {coverage.overall_coverage:.1f}%")
    click.echo(f"    Required: {coverage.total_required}")
    click.echo(f"    Existing: {coverage.total_existing}")

    if coverage.by_type:
        click.echo("\n  Missing by Type:")
        for artifact_type, count in coverage.by_type.items():
            click.echo(f"    - {artifact_type}: {count}")

    gaps = artifact_manifest.get_gaps()
    if gaps:
        click.echo(f"\n  Top Gaps ({len(gaps)} total):")
        for gap in gaps[:5]:
            click.echo(f"    - [{gap.priority.value}] {gap.id}: {gap.name}")
        if len(gaps) > 5:
            click.echo(f"    ... and {len(gaps) - 5} more")


def enforce_min_coverage(min_coverage: Optional[float], artifact_manifest: Any) -> Optional[str]:
    if min_coverage is None:
        return None
    coverage_pct = artifact_manifest.coverage.overall_coverage
    if coverage_pct < min_coverage:
        return f"✗ Coverage {coverage_pct:.1f}% is below minimum {min_coverage}%"
    return None


def preview_export(
    crd_filename: str,
    crd_yaml: str,
    artifact_filename: str,
    artifact_content: str,
    provenance: Any,
    emit_onboarding: bool,
    onboarding_metadata: Dict[str, Any],
    validation_report: Dict[str, Any],
    emit_quality_report: bool,
    quality_report: Dict[str, Any],
    artifact_manifest: Any,
) -> None:
    click.echo("=== DRY RUN - Export Preview ===\n")
    click.echo(f"--- {crd_filename} ---")
    click.echo(crd_yaml[:500] + "..." if len(crd_yaml) > 500 else crd_yaml)
    click.echo(f"\n--- {artifact_filename} ---")
    click.echo(artifact_content[:1000] + "..." if len(artifact_content) > 1000 else artifact_content)
    if provenance:
        click.echo("\n--- Provenance ---")
        prov_dict = provenance.model_dump(by_alias=True, exclude_none=True, mode="json")
        click.echo(json.dumps(prov_dict, indent=2, default=str)[:800] + "...")
    if emit_onboarding:
        click.echo("\n--- Onboarding Metadata (preview) ---")
        click.echo(json.dumps(onboarding_metadata, indent=2, default=str)[:600] + "...")
    click.echo("\n--- Validation Report (preview) ---")
    click.echo(json.dumps(validation_report, indent=2, default=str)[:600] + "...")
    click.echo("\n=== End Preview ===")
    print_coverage_summary(artifact_manifest)
    if emit_quality_report:
        click.echo("\n--- Export Quality Report (preview) ---")
        click.echo(json.dumps(quality_report, indent=2, default=str)[:700] + "...")


def write_export_outputs(
    output_path: Path,
    crd_filename: str,
    crd_yaml: str,
    artifact_filename: str,
    artifact_content: str,
    emit_provenance: bool,
    provenance: Any,
    emit_onboarding: bool,
    onboarding_metadata: Dict[str, Any],
    validation_report: Dict[str, Any],
    emit_quality_report: bool,
    quality_report: Dict[str, Any],
    output_files: list[str],
) -> Dict[str, Optional[str]]:
    (output_path / crd_filename).write_text(crd_yaml, encoding="utf-8")
    (output_path / artifact_filename).write_text(artifact_content, encoding="utf-8")

    provenance_file: Optional[str] = None
    if emit_provenance and provenance:
        from contextcore.utils.provenance import write_provenance_file

        provenance_file = write_provenance_file(provenance, str(output_path), format="json")
        output_files.append("provenance.json")

    onboarding_file: Optional[str] = None
    if emit_onboarding:
        onboarding_path = output_path / "onboarding-metadata.json"
        onboarding_path.write_text(json.dumps(onboarding_metadata, indent=2, default=str), encoding="utf-8")
        onboarding_file = str(onboarding_path)
        output_files.append("onboarding-metadata.json")

    validation_path = output_path / "validation-report.json"
    validation_path.write_text(json.dumps(validation_report, indent=2, default=str), encoding="utf-8")
    output_files.append("validation-report.json")

    quality_path: Optional[str] = None
    if emit_quality_report:
        qp = output_path / "export-quality-report.json"
        qp.write_text(json.dumps(quality_report, indent=2, default=str), encoding="utf-8")
        quality_path = str(qp)
        output_files.append("export-quality-report.json")

    return {
        "provenance_file": provenance_file,
        "onboarding_file": onboarding_file,
        "quality_path": quality_path,
    }


def print_export_success(
    output_path: Path,
    crd_filename: str,
    artifact_filename: str,
    provenance_file: Optional[str],
    onboarding_file: Optional[str],
    quality_path: Optional[str],
    artifact_manifest: Any,
    provenance: Any,
) -> None:
    click.echo(f"✓ Exported ContextCore artifacts to {output_path}/")
    click.echo(f"  1. {crd_filename} - Kubernetes CRD (do NOT apply directly)")
    click.echo(f"  2. {artifact_filename} - Artifact Manifest (for Wayfinder)")
    if provenance_file:
        click.echo("  3. provenance.json - Full provenance audit trail")
    if onboarding_file:
        click.echo("  4. onboarding-metadata.json - Programmatic onboarding metadata")
    click.echo("  5. validation-report.json - Export-time validation diagnostics")
    if quality_path:
        click.echo("  6. export-quality-report.json - Strict-quality gate summary")

    print_coverage_summary(artifact_manifest)

    if provenance:
        click.echo("\n  Provenance:")
        if provenance.git:
            git = provenance.git
            dirty_marker = " (dirty)" if git.is_dirty else ""
            commit = git.commit_sha[:8] if git.commit_sha else "unknown"
            click.echo(f"    Git: {git.branch}@{commit}{dirty_marker}")
        if provenance.source_checksum:
            click.echo(f"    Source checksum: {provenance.source_checksum[:16]}...")
        else:
            click.echo("    Source checksum: not computed")
        if provenance.duration_ms:
            click.echo(f"    Duration: {provenance.duration_ms}ms")

    click.echo("\nNext steps:")
    click.echo("  1. Review the artifact manifest for accuracy")
    if not provenance_file:
        click.echo("  2. (Recommended) Re-run with --emit-provenance for checksum chain integrity")
    click.echo(f"  {'2' if provenance_file else '3'}. Run: contextcore contract a2a-check-pipeline {output_path}  (Gate 1: pipeline integrity)")
    click.echo(f"  {'3' if provenance_file else '4'}. Pass both files to your Wayfinder implementation (startd8 workflow run plan-ingestion)")
    click.echo(f"  {'4' if provenance_file else '5'}. Run: contextcore contract a2a-diagnose  (Gate 2: Three Questions diagnostic)")
    click.echo(f"  {'5' if provenance_file else '6'}. Re-run with --scan-existing to update coverage after artifact generation")
