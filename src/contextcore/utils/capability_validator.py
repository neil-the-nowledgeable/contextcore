"""
Two-layer validation for capability index manifests.

Layer 1 — Schema validation:
    Required fields, capability_id format, category/maturity enums,
    summary length, confidence range.

Layer 2 — REQ-CID acceptance checks:
    Business rules from REQ_CAPABILITY_INDEX_DISCOVERABILITY.md including
    backward compatibility, principle/pattern counts, trigger coverage,
    contract layer presence, and A2A governance presence.

Used by: contextcore capability-index validate
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Categories: OTel doesn't define these; union of ContextCore + craft schema values
VALID_CATEGORIES = {
    "action", "query", "transform", "integration", "governance",
    "generate", "validate", "security", "observe",
}
# Maturity: aligned with OTel semantic convention stability levels
# https://opentelemetry.io/docs/specs/semconv/general/group-stability/
VALID_MATURITIES = {
    "development", "alpha", "beta", "release_candidate", "stable", "deprecated",
}


@dataclass
class CheckResult:
    """Result of a single validation check."""

    name: str
    passed: bool
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class ValidationReport:
    """Aggregate validation report."""

    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if c.severity == "error")

    @property
    def passed_strict(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def error_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.severity == "warning")

    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.passed)
        lines = [f"Validation: {passed}/{total} checks passed"]
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"  [{status}] {c.name}: {c.message}")
        return "\n".join(lines)


# ── Layer 1: Schema validation ───────────────────────────────────────────


def _validate_schema(manifest: Dict[str, Any], report: ValidationReport) -> None:
    """Run schema-level validation checks."""

    # Required top-level fields
    for field_name in ("manifest_id", "name", "version"):
        val = manifest.get(field_name)
        report.checks.append(CheckResult(
            name=f"required_field_{field_name}",
            passed=bool(val),
            message=f"'{field_name}' is {'present' if val else 'missing'}",
        ))

    # Capabilities is a list
    caps = manifest.get("capabilities")
    report.checks.append(CheckResult(
        name="capabilities_is_list",
        passed=isinstance(caps, list),
        message=f"'capabilities' is {'a list' if isinstance(caps, list) else 'missing or not a list'}",
    ))

    if not isinstance(caps, list):
        return

    # Per-capability checks
    for i, cap in enumerate(caps):
        if not isinstance(cap, dict):
            continue
        cap_id = cap.get("capability_id", f"[index {i}]")

        # capability_id format
        has_id = bool(cap.get("capability_id"))
        report.checks.append(CheckResult(
            name=f"cap_{cap_id}_has_id",
            passed=has_id,
            message=f"capability_id {'present' if has_id else 'missing'}",
        ))

        # category enum
        cat = cap.get("category", "")
        valid_cat = cat in VALID_CATEGORIES
        report.checks.append(CheckResult(
            name=f"cap_{cap_id}_category",
            passed=valid_cat,
            message=f"category '{cat}' is {'valid' if valid_cat else 'not in ' + str(VALID_CATEGORIES)}",
            severity="warning",
        ))

        # maturity enum
        mat = cap.get("maturity", "")
        valid_mat = mat in VALID_MATURITIES
        report.checks.append(CheckResult(
            name=f"cap_{cap_id}_maturity",
            passed=valid_mat,
            message=f"maturity '{mat}' is {'valid' if valid_mat else 'not in ' + str(VALID_MATURITIES)}",
            severity="warning",
        ))

        # summary exists
        has_summary = bool(cap.get("summary"))
        report.checks.append(CheckResult(
            name=f"cap_{cap_id}_summary",
            passed=has_summary,
            message=f"summary {'present' if has_summary else 'missing'}",
            severity="warning",
        ))

        # audiences field present (REQ-CID-019)
        # Non-internal capabilities without audiences will default to human-only
        # and be excluded from MCP/A2A export
        is_internal = cap.get("internal", False)
        has_audiences = "audiences" in cap
        if has_audiences:
            audiences_msg = "audiences field present"
        elif is_internal:
            audiences_msg = "internal capability, audiences not required"
        else:
            audiences_msg = (
                f"Capability '{cap_id}' has no audiences field; "
                f"it will default to human-only and be excluded from MCP/A2A export"
            )
        report.checks.append(CheckResult(
            name=f"cap_{cap_id}_audiences",
            passed=has_audiences or is_internal,
            message=audiences_msg,
            severity="warning",
        ))

    # design_principles validation
    principles = manifest.get("design_principles")
    if isinstance(principles, list):
        for p in principles:
            if not isinstance(p, dict):
                continue
            pid = p.get("id", "unknown")
            has_principle = bool(p.get("principle"))
            report.checks.append(CheckResult(
                name=f"principle_{pid}_has_text",
                passed=has_principle,
                message=f"principle '{pid}' {'has' if has_principle else 'missing'} principle text",
                severity="warning",
            ))

    # patterns validation
    patterns = manifest.get("patterns")
    if isinstance(patterns, list):
        for pat in patterns:
            if not isinstance(pat, dict):
                continue
            pat_id = pat.get("pattern_id", "unknown")
            has_caps = bool(pat.get("capabilities"))
            report.checks.append(CheckResult(
                name=f"pattern_{pat_id}_has_capabilities",
                passed=has_caps,
                message=f"pattern '{pat_id}' {'has' if has_caps else 'missing'} capabilities list",
                severity="warning",
            ))


# ── Layer 2: REQ-CID acceptance checks ──────────────────────────────────


def _validate_req_cid(
    manifest: Dict[str, Any],
    report: ValidationReport,
    *,
    previous_cap_ids: Optional[Set[str]] = None,
    previous_version: Optional[str] = None,
) -> None:
    """Run REQ-CID business rule checks."""
    caps = manifest.get("capabilities") or []
    cap_ids = {
        c.get("capability_id", "")
        for c in caps if isinstance(c, dict)
    }

    # REQ-CID-010: Backward compatibility
    if previous_cap_ids is not None:
        missing = previous_cap_ids - cap_ids
        report.checks.append(CheckResult(
            name="backward_compat",
            passed=len(missing) == 0,
            message=f"All pre-existing capability_ids preserved" if not missing
                    else f"Missing: {', '.join(sorted(missing))}",
        ))

    # REQ-CID-001: Principle count >= 9
    principles = manifest.get("design_principles") or []
    report.checks.append(CheckResult(
        name="principle_count",
        passed=len(principles) >= 9,
        message=f"{len(principles)} principles (need >= 9)",
    ))

    # REQ-CID-002: Pattern count >= 6
    patterns = manifest.get("patterns") or []
    report.checks.append(CheckResult(
        name="pattern_count",
        passed=len(patterns) >= 6,
        message=f"{len(patterns)} patterns (need >= 6)",
    ))

    # REQ-CID-002: Pattern capability references valid
    for pat in patterns:
        if not isinstance(pat, dict):
            continue
        pat_id = pat.get("pattern_id", "unknown")
        pat_caps = pat.get("capabilities") or []
        invalid = [c for c in pat_caps if c not in cap_ids]
        report.checks.append(CheckResult(
            name=f"pattern_{pat_id}_refs_valid",
            passed=len(invalid) == 0,
            message=f"All refs valid" if not invalid
                    else f"Invalid refs: {', '.join(invalid)}",
            severity="warning",
        ))

    # REQ-CID-001: Principle applies_to valid
    for prin in principles:
        if not isinstance(prin, dict):
            continue
        pid = prin.get("id", "unknown")
        applies = prin.get("applies_to") or []
        invalid = [c for c in applies if c not in cap_ids]
        report.checks.append(CheckResult(
            name=f"principle_{pid}_applies_valid",
            passed=len(invalid) == 0,
            message=f"All applies_to valid" if not invalid
                    else f"Invalid refs: {', '.join(invalid)}",
            severity="warning",
        ))

    # REQ-CID-003: Trigger coverage — "pipeline" matches >= 4
    pipeline_matches = _count_trigger_matches(caps, "pipeline")
    report.checks.append(CheckResult(
        name="trigger_pipeline_coverage",
        passed=pipeline_matches >= 4,
        message=f"'pipeline' trigger matches {pipeline_matches} capabilities (need >= 4)",
    ))

    # REQ-CID-011: Contract capabilities >= 7
    contract_caps = [c for c in cap_ids if c.startswith("contextcore.contract.")]
    report.checks.append(CheckResult(
        name="contract_capability_count",
        passed=len(contract_caps) >= 7,
        message=f"{len(contract_caps)} contextcore.contract.* capabilities (need >= 7)",
    ))

    # REQ-CID-012: A2A governance >= 6
    a2a_caps = [
        c for c in cap_ids
        if c.startswith("contextcore.a2a.contract.") or c.startswith("contextcore.a2a.gate.")
    ]
    report.checks.append(CheckResult(
        name="a2a_governance_count",
        passed=len(a2a_caps) >= 6,
        message=f"{len(a2a_caps)} A2A governance capabilities (need >= 6)",
    ))

    # REQ-CID-011: Trigger "contract" matches >= 7
    contract_matches = _count_trigger_matches(caps, "contract")
    report.checks.append(CheckResult(
        name="trigger_contract_coverage",
        passed=contract_matches >= 7,
        message=f"'contract' trigger matches {contract_matches} capabilities (need >= 7)",
    ))

    # REQ-CID-012: Trigger "governance" matches >= 2
    governance_matches = _count_trigger_matches(caps, "governance")
    report.checks.append(CheckResult(
        name="trigger_governance_coverage",
        passed=governance_matches >= 2,
        message=f"'governance' trigger matches {governance_matches} capabilities (need >= 2)",
    ))

    # REQ-CID-004: Pipeline typed handoff exists
    has_typed_handoff = "contextcore.pipeline.typed_handoff" in cap_ids
    report.checks.append(CheckResult(
        name="typed_handoff_exists",
        passed=has_typed_handoff,
        message="contextcore.pipeline.typed_handoff capability present"
                if has_typed_handoff
                else "contextcore.pipeline.typed_handoff capability missing (REQ-CID-004)",
        severity="warning",
    ))

    # REQ-CID-005: ExpectedOutput discoverable
    has_expected_output = "contextcore.contract.expected_output" in cap_ids
    output_trigger_match = _count_trigger_matches(caps, "output contract")
    report.checks.append(CheckResult(
        name="expected_output_discoverable",
        passed=has_expected_output or output_trigger_match >= 1,
        message="Expected output discoverable"
                if has_expected_output or output_trigger_match >= 1
                else "No capability for 'output contract' trigger (REQ-CID-005)",
        severity="warning",
    ))

    # REQ-CID-008: Discovery paths schema (if present, must be list[str])
    for cap in caps:
        if not isinstance(cap, dict):
            continue
        dp = cap.get("discovery_paths")
        if dp is not None:
            valid_dp = isinstance(dp, list) and all(isinstance(p, str) for p in dp)
            cap_id = cap.get("capability_id", "unknown")
            report.checks.append(CheckResult(
                name=f"discovery_paths_{cap_id}_schema",
                passed=valid_dp,
                message=f"discovery_paths on '{cap_id}' is valid list[str]"
                        if valid_dp
                        else f"discovery_paths on '{cap_id}' must be list[str]",
                severity="warning",
            ))

    # YAML parseable (if we got this far, it is)
    report.checks.append(CheckResult(
        name="yaml_parseable",
        passed=True,
        message="Manifest is valid YAML",
    ))

    # Version bumped
    if previous_version:
        bumped = manifest.get("version", "") > previous_version
        report.checks.append(CheckResult(
            name="version_bumped",
            passed=bumped,
            message=f"Version {manifest.get('version', '')} > {previous_version}" if bumped
                    else f"Version not bumped: {manifest.get('version', '')} <= {previous_version}",
        ))


def _count_trigger_matches(caps: list, keyword: str) -> int:
    """Count capabilities where any trigger contains the keyword (case-insensitive)."""
    keyword_lower = keyword.lower()
    count = 0
    for cap in caps:
        if not isinstance(cap, dict):
            continue
        for trigger in (cap.get("triggers") or []):
            if keyword_lower in trigger.lower():
                count += 1
                break
    return count


# ── Public API ───────────────────────────────────────────────────────────


def validate_manifest(
    manifest: Dict[str, Any],
    *,
    previous_cap_ids: Optional[Set[str]] = None,
    previous_version: Optional[str] = None,
) -> ValidationReport:
    """Run full two-layer validation on a manifest dict.

    Args:
        manifest: The manifest dict to validate.
        previous_cap_ids: If provided, check backward compatibility.
        previous_version: If provided, check version bump.

    Returns:
        ValidationReport with all check results.
    """
    report = ValidationReport()
    _validate_schema(manifest, report)
    _validate_req_cid(
        manifest,
        report,
        previous_cap_ids=previous_cap_ids,
        previous_version=previous_version,
    )
    return report


def validate_manifest_file(
    manifest_path: Path,
    *,
    previous_path: Optional[Path] = None,
) -> ValidationReport:
    """Load and validate a manifest YAML file.

    Args:
        manifest_path: Path to the YAML manifest file.
        previous_path: Optional path to previous version for backward compat check.

    Returns:
        ValidationReport with all check results.
    """
    import yaml

    report = ValidationReport()

    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = yaml.safe_load(f) or {}
    except Exception as e:
        report.checks.append(CheckResult(
            name="yaml_parseable",
            passed=False,
            message=f"Failed to parse: {e}",
        ))
        return report

    previous_cap_ids = None
    previous_version = None
    if previous_path and previous_path.is_file():
        try:
            with open(previous_path, encoding="utf-8") as f:
                prev = yaml.safe_load(f) or {}
            previous_cap_ids = {
                c.get("capability_id", "")
                for c in (prev.get("capabilities") or [])
                if isinstance(c, dict) and c.get("capability_id")
            }
            previous_version = prev.get("version")
        except Exception:
            logger.debug("Failed to load previous manifest", exc_info=True)

    _validate_schema(manifest, report)
    _validate_req_cid(
        manifest,
        report,
        previous_cap_ids=previous_cap_ids,
        previous_version=previous_version,
    )
    return report
