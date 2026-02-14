"""Quality policy helpers for `contextcore manifest export`."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

QUALITY_POLICY_FILENAME = ".contextcore-quality.yaml"
DEFAULT_SCAN_ALLOWLIST = [
    "grafana/dashboards",
    "prometheus/rules",
    "k8s/observability",
    "loki/rules",
    "runbooks",
    "alertmanager",
]


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def find_quality_policy_file(manifest_path: str) -> Optional[Path]:
    env_path = os.getenv("CONTEXTCORE_QUALITY_POLICY")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    manifest_abs = Path(manifest_path).resolve()
    for parent in [manifest_abs.parent, *manifest_abs.parents]:
        candidate = parent / QUALITY_POLICY_FILENAME
        if candidate.exists():
            return candidate
    return None


def load_quality_policy(manifest_path: str) -> Dict[str, Any]:
    policy: Dict[str, Any] = {
        "strict_quality_default": True,
        "forbid_no_strict_quality_in_ci": True,
        "ci_bootstrap_env_var": "CONTEXTCORE_BOOTSTRAP_JOB",
        "coverage_thresholds_by_env": {
            "dev": 60.0,
            "staging": 80.0,
            "prod": 90.0,
        },
        "default_environment": "dev",
        "scan_path_allowlist": DEFAULT_SCAN_ALLOWLIST,
        "schema_pins": {
            "manifest_api_version": "contextcore.io/v1alpha2",
            "onboarding_schema": "contextcore.io/onboarding-metadata/v1",
            "validation_schema": "contextcore.io/validation-report/v1",
            "schema_version": "1.0.0",
        },
        "emit_quality_report_default": True,
        "deterministic_output_default": True,
        "emit_run_provenance_default": True,
        "document_write_strategy_default": "update_existing",
    }

    policy_file = find_quality_policy_file(manifest_path)
    if not policy_file:
        return policy
    try:
        loaded = yaml.safe_load(policy_file.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            return _deep_merge_dict(policy, loaded)
    except Exception:
        # Keep defaults if loading fails.
        pass
    return policy


def resolve_export_quality_toggles(
    policy: Dict[str, Any],
    strict_quality: Optional[bool],
    deterministic_output: Optional[bool],
    emit_quality_report: Optional[bool],
    emit_run_provenance: Optional[bool] = None,
    document_write_strategy: str = None,
) -> tuple[bool, bool, bool, bool, str]:
    strict = bool(policy.get("strict_quality_default", True)) if strict_quality is None else strict_quality
    deterministic = (
        bool(policy.get("deterministic_output_default", True))
        if deterministic_output is None
        else deterministic_output
    )
    quality_report = (
        bool(policy.get("emit_quality_report_default", True))
        if emit_quality_report is None
        else emit_quality_report
    )
    
    # Run provenance defaults to policy value if not provided, or True if not in policy
    # but forced by strict quality below
    run_provenance_default = policy.get("emit_run_provenance_default", True)
    run_provenance = (
        bool(run_provenance_default) 
        if emit_run_provenance is None 
        else emit_run_provenance
    )
    
    write_strategy = (
        str(policy.get("document_write_strategy_default", "update_existing"))
        if document_write_strategy is None
        else document_write_strategy
    )
    
    return strict, deterministic, quality_report, run_provenance, write_strategy



def evaluate_ci_policy(strict_quality: bool, policy: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if strict_quality or os.getenv("CI", "").lower() not in ("1", "true", "yes"):
        return None
    if not bool(policy.get("forbid_no_strict_quality_in_ci", True)):
        return None
    bootstrap_var = str(policy.get("ci_bootstrap_env_var", "CONTEXTCORE_BOOTSTRAP_JOB"))
    is_bootstrap = os.getenv(bootstrap_var, "").lower() in ("1", "true", "yes")
    if is_bootstrap:
        return None
    return {
        "headline": "✗ CI policy forbids --no-strict-quality unless bootstrap job is explicitly tagged.",
        "detail": f"  Set {bootstrap_var}=true for bootstrap jobs or remove --no-strict-quality.",
    }


def apply_strict_quality_profile(
    strict_quality: bool,
    policy: Dict[str, Any],
    min_coverage: Optional[float],
    task_mapping: Optional[str],
    scan_existing: Optional[str],
    emit_provenance: bool,
    embed_provenance: bool,
    emit_run_provenance: bool = False,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": True,
        "errors": [],
        "warnings": [],
        "min_coverage": min_coverage,
        "emit_provenance": emit_provenance,
        "embed_provenance": embed_provenance,
        "emit_run_provenance": emit_run_provenance,
        "environment": os.getenv(
            "CONTEXTCORE_ENV",
            str(policy.get("default_environment", "dev")),
        ).lower(),
        "allowlist": [str(p) for p in policy.get("scan_path_allowlist", DEFAULT_SCAN_ALLOWLIST)],
    }
    if not strict_quality:
        return result

    thresholds = policy.get("coverage_thresholds_by_env", {})
    default_min_coverage = float(thresholds.get(result["environment"], 80.0))
    if result["min_coverage"] is None:
        result["min_coverage"] = default_min_coverage
    elif result["min_coverage"] < default_min_coverage:
        result["ok"] = False
        result["errors"] = [
            f"✗ Strict quality requires min coverage >= {default_min_coverage:.1f} "
            f"for env '{result['environment']}' (got {result['min_coverage']})",
            "  Use --no-strict-quality to override this safeguard.",
        ]
        return result

    if not task_mapping:
        result["ok"] = False
        result["errors"] = [
            "✗ Strict quality requires --task-mapping for artifact traceability.",
            "  Use --no-strict-quality to bypass (not recommended).",
        ]
        return result

    if not scan_existing:
        result["ok"] = False
        result["errors"] = [
            "✗ Strict quality requires --scan-existing to compute coverage against approved artifact paths.",
        ]
        return result

    scan_normalized = str(Path(scan_existing).as_posix()).lower()
    if not any(seg.lower() in scan_normalized for seg in result["allowlist"]):
        result["ok"] = False
        result["errors"] = [
            "✗ Strict quality requires --scan-existing to target approved artifact paths.",
            f"  Allowed path segments: {', '.join(result['allowlist'])}",
            "  Use --no-strict-quality to bypass this safeguard.",
        ]
        return result

    if scan_normalized.endswith("/docs") or scan_normalized == "docs":
        result["ok"] = False
        result["errors"] = [
            "✗ Strict quality rejects docs-only scan paths; point --scan-existing "
            "to project root or generated artifact directories.",
            "  Use --no-strict-quality to bypass this safeguard.",
        ]
        return result

    if not result["emit_provenance"]:
        result["emit_provenance"] = True
        result["warnings"].append("⚠ Strict quality enables --emit-provenance automatically.")
    if not result["embed_provenance"]:
        result["embed_provenance"] = True
        result["warnings"].append("⚠ Strict quality enables --embed-provenance automatically.")
        
    if not result["emit_run_provenance"]:
        result["emit_run_provenance"] = True
        result["warnings"].append("⚠ Strict quality enables --emit-run-provenance automatically.")

    return result


def validate_manifest_api_pin(
    strict_quality: bool,
    policy: Dict[str, Any],
    raw_data: Dict[str, Any],
) -> Optional[str]:
    if not strict_quality:
        return None
    schema_pins = policy.get("schema_pins", {})
    expected_api = schema_pins.get("manifest_api_version")
    actual_api = raw_data.get("apiVersion")
    if expected_api and actual_api != expected_api:
        return (
            f"✗ Strict quality schema pin mismatch: apiVersion={actual_api}, "
            f"expected={expected_api}"
        )
    return None


def validate_export_schema_pins(
    strict_quality: bool,
    policy: Dict[str, Any],
    onboarding_metadata: Dict[str, Any],
    validation_report: Dict[str, Any],
) -> Optional[str]:
    if not strict_quality:
        return None

    schema_pins = policy.get("schema_pins", {})
    expected_onboarding_schema = schema_pins.get("onboarding_schema")
    expected_validation_schema = schema_pins.get("validation_schema")
    expected_schema_version = schema_pins.get("schema_version")

    if expected_onboarding_schema and onboarding_metadata.get("schema") != expected_onboarding_schema:
        return (
            "✗ Strict quality schema pin mismatch for onboarding metadata schema: "
            f"{onboarding_metadata.get('schema')} != {expected_onboarding_schema}"
        )
    if expected_validation_schema and validation_report.get("schema") != expected_validation_schema:
        return (
            "✗ Strict quality schema pin mismatch for validation report schema: "
            f"{validation_report.get('schema')} != {expected_validation_schema}"
        )
    if expected_schema_version and (
        onboarding_metadata.get("schema_version") != expected_schema_version
        or validation_report.get("schema_version") != expected_schema_version
    ):
        return "✗ Strict quality schema version mismatch in generated metadata/reports."
    return None
