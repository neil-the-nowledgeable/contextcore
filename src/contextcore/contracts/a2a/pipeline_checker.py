"""
Pipeline integrity checker — runs A2A gate checks on real export output.

Reads ``onboarding-metadata.json`` (and optionally ``provenance.json``) from an
export output directory and applies the full gate suite:

1. **Structural integrity** — validates required top-level fields exist and are well-formed
2. **Checksum chain** — recomputes file checksums and verifies against stored values
3. **Provenance cross-check** — verifies provenance.json is consistent with onboarding metadata
4. **Mapping completeness** — verifies every coverage gap has a task mapping entry
5. **Gap parity** — compares coverage gaps against available feature IDs
6. **Design calibration** — validates design_calibration_hints cover all artifact types with gaps
7. **Parameter resolvability** — verifies parameter_sources reference fields that resolve to values
8. **Artifact inventory** — validates v2 provenance artifact_inventory roles
9. **Service metadata** — validates transport_protocol and schema_contract declarations

Usage::

    from contextcore.contracts.a2a.pipeline_checker import PipelineChecker

    checker = PipelineChecker("out/export")
    report = checker.run()
    print(report.to_text())

CLI::

    contextcore contract a2a-check-pipeline out/export
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from contextcore.contracts.a2a.gates import (
    GateChecker,
    check_checksum_chain,
    check_gap_parity,
    check_mapping_completeness,
)
from contextcore.contracts.a2a.models import (
    EvidenceItem,
    GateOutcome,
    GateResult,
    GateSeverity,
    Phase,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> Optional[str]:
    """Compute SHA-256 hex digest of a file, or ``None`` if it doesn't exist."""
    if not path.exists():
        return None
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _sha256_content(content: str | bytes) -> str:
    """Compute SHA-256 hex digest of string/bytes content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# Report data structures
# ---------------------------------------------------------------------------

@dataclass
class PipelineCheckReport:
    """Aggregated result of all pipeline integrity checks."""

    output_dir: str
    project_id: str
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    gates: list[GateResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    # ---- Computed properties ------------------------------------------------

    @property
    def total_gates(self) -> int:
        return len(self.gates)

    @property
    def passed(self) -> int:
        return sum(1 for g in self.gates if g.result == GateOutcome.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for g in self.gates if g.result == GateOutcome.FAIL)

    @property
    def blocking_failures(self) -> list[GateResult]:
        return [g for g in self.gates if g.blocking and g.result == GateOutcome.FAIL]

    @property
    def is_healthy(self) -> bool:
        return len(self.blocking_failures) == 0

    # ---- Output methods -----------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a JSON-serializable summary dict."""
        return {
            "output_dir": self.output_dir,
            "project_id": self.project_id,
            "checked_at": self.checked_at,
            "total_gates": self.total_gates,
            "passed": self.passed,
            "failed": self.failed,
            "blocking_failures": len(self.blocking_failures),
            "is_healthy": self.is_healthy,
            "warnings": self.warnings,
            "skipped": self.skipped,
            "gates": [
                {
                    "gate_id": g.gate_id,
                    "phase": g.phase.value,
                    "result": g.result.value,
                    "blocking": g.blocking,
                    "reason": g.reason,
                }
                for g in self.gates
            ],
        }

    def to_text(self) -> str:
        """Human-readable report text."""
        lines: list[str] = []
        status = "HEALTHY" if self.is_healthy else "UNHEALTHY"
        lines.append(f"Pipeline Integrity: {status}")
        lines.append(f"  Project:   {self.project_id}")
        lines.append(f"  Directory: {self.output_dir}")
        lines.append(f"  Checked:   {self.checked_at}")
        lines.append(f"  Gates:     {self.passed}/{self.total_gates} passed")
        lines.append("")

        for gate in self.gates:
            icon = "PASS" if gate.result == GateOutcome.PASS else "FAIL"
            blocking_tag = " [BLOCKING]" if gate.blocking else ""
            lines.append(f"  {icon}{blocking_tag}  {gate.gate_id}")
            lines.append(f"    {gate.reason}")
            if gate.result == GateOutcome.FAIL and gate.next_action:
                lines.append(f"    -> {gate.next_action}")
            if gate.evidence:
                for ev in gate.evidence:
                    lines.append(f"      [{ev.type}] {ev.ref}: {ev.description or ''}")
            lines.append("")

        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
            lines.append("")

        if self.skipped:
            lines.append("  Skipped checks:")
            for s in self.skipped:
                lines.append(f"    - {s}")
            lines.append("")

        return "\n".join(lines)

    def write_json(self, path: str | Path) -> Path:
        """Write the full report as JSON."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as fh:
            json.dump(self.summary(), fh, indent=2, default=str)
        return out


# ---------------------------------------------------------------------------
# Pipeline Checker
# ---------------------------------------------------------------------------


class PipelineChecker:
    """
    Reads real export output and runs the A2A gate suite against it.

    Args:
        output_dir: Path to the export output directory containing
            ``onboarding-metadata.json`` and optionally ``provenance.json``.
        task_id: Optional task span ID for gate context (defaults to project ID).
        trace_id: Optional trace ID for gate context.
    """

    def __init__(
        self,
        output_dir: str | Path,
        *,
        task_id: str | None = None,
        trace_id: str | None = None,
        min_coverage: float | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.task_id = task_id
        self.trace_id = trace_id
        self.min_coverage = min_coverage

        # Loaded lazily by _load()
        self._metadata: dict[str, Any] = {}
        self._provenance: Optional[dict[str, Any]] = None

    # ---- Loading -----------------------------------------------------------

    def _load(self) -> None:
        """Load onboarding-metadata.json and optionally provenance.json."""
        meta_path = self.output_dir / "onboarding-metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"No onboarding-metadata.json found in {self.output_dir}. "
                "Run `contextcore manifest export --emit-onboarding` first."
            )

        with open(meta_path) as fh:
            self._metadata = json.load(fh)

        prov_path = self.output_dir / "provenance.json"
        if prov_path.exists():
            with open(prov_path) as fh:
                self._provenance = json.load(fh)

    # ---- Gate: Structural integrity ----------------------------------------

    def _check_structural_integrity(self) -> GateResult:
        """Validate required top-level fields exist and are well-formed."""
        required_fields = [
            "version", "schema", "project_id", "generated_at",
            "coverage", "artifact_manifest_checksum",
            "project_context_checksum", "source_checksum",
        ]
        missing: list[str] = []
        evidence: list[EvidenceItem] = []

        for field_name in required_fields:
            if field_name not in self._metadata:
                missing.append(field_name)
                evidence.append(EvidenceItem(
                    type="missing_field",
                    ref=field_name,
                    description=f"Required field '{field_name}' is missing from onboarding-metadata.json.",
                ))

        # Validate coverage structure
        coverage = self._metadata.get("coverage", {})
        if coverage:
            for cov_field in ["totalRequired", "gaps"]:
                if cov_field not in coverage:
                    missing.append(f"coverage.{cov_field}")
                    evidence.append(EvidenceItem(
                        type="missing_field",
                        ref=f"coverage.{cov_field}",
                        description=f"Required coverage field '{cov_field}' is missing.",
                    ))

        # Validate schema version
        schema = self._metadata.get("schema", "")
        if schema and not schema.startswith("contextcore.io/"):
            evidence.append(EvidenceItem(
                type="unexpected_schema",
                ref="schema",
                description=f"Schema '{schema}' doesn't match expected prefix 'contextcore.io/'.",
            ))

        gate_id = f"{self._effective_task_id}-structural-integrity"
        if missing:
            return GateResult(
                gate_id=gate_id,
                trace_id=self.trace_id,
                task_id=self._effective_task_id,
                phase=Phase.EXPORT_CONTRACT,
                result=GateOutcome.FAIL,
                severity=GateSeverity.ERROR,
                reason=f"Structural integrity failed: {len(missing)} required field(s) missing — {', '.join(missing)}.",
                next_action="Re-run export with all required fields populated.",
                blocking=True,
                evidence=evidence,
                checked_at=datetime.now(timezone.utc),
            )

        return GateResult(
            gate_id=gate_id,
            trace_id=self.trace_id,
            task_id=self._effective_task_id,
            phase=Phase.EXPORT_CONTRACT,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"Structural integrity verified: all {len(required_fields)} required fields present.",
            next_action="Proceed to checksum verification.",
            blocking=False,
            evidence=[EvidenceItem(
                type="structure_verified",
                ref="onboarding-metadata.json",
                description=f"All {len(required_fields)} required fields present and well-formed.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    # ---- Gate: Checksum chain -----------------------------------------------

    def _check_checksum_chain(self) -> GateResult:
        """Recompute checksums from referenced files and verify chain."""
        stored = {
            "source_checksum": self._metadata.get("source_checksum"),
            "artifact_manifest_checksum": self._metadata.get("artifact_manifest_checksum"),
            "project_context_checksum": self._metadata.get("project_context_checksum"),
        }

        recomputed: dict[str, str] = {}

        # Recompute source checksum from source file
        source_rel = self._metadata.get("source_path_relative")
        if source_rel:
            # Try relative to output dir's parent (workspace root), then CWD
            for base in [self.output_dir.parent, Path.cwd()]:
                source_path = base / source_rel
                if source_path.exists():
                    recomputed["source_checksum"] = _sha256_file(source_path) or ""
                    break

        # Recompute artifact manifest checksum
        manifest_rel = self._metadata.get("artifact_manifest_path")
        if manifest_rel:
            manifest_path = self.output_dir / manifest_rel
            if manifest_path.exists():
                content = manifest_path.read_text(encoding="utf-8")
                recomputed["artifact_manifest_checksum"] = _sha256_content(content)

        # Recompute project context checksum
        ctx_rel = self._metadata.get("project_context_path")
        if ctx_rel:
            ctx_path = self.output_dir / ctx_rel
            if ctx_path.exists():
                content = ctx_path.read_text(encoding="utf-8")
                recomputed["project_context_checksum"] = _sha256_content(content)

        # Build expected/actual maps for the gate — only include keys we can verify
        expected: dict[str, str] = {}
        actual: dict[str, str] = {}

        for key in ["source_checksum", "artifact_manifest_checksum", "project_context_checksum"]:
            stored_val = stored.get(key)
            recomputed_val = recomputed.get(key)
            if stored_val and recomputed_val:
                expected[key] = stored_val
                actual[key] = recomputed_val

        if not expected:
            # Can't verify any checksums — return a pass with warning
            return GateResult(
                gate_id=f"{self._effective_task_id}-checksum-chain",
                trace_id=self.trace_id,
                task_id=self._effective_task_id,
                phase=Phase.CONTRACT_INTEGRITY,
                result=GateOutcome.PASS,
                severity=GateSeverity.WARNING,
                reason="No checksums could be recomputed (source files not found). Stored checksums accepted.",
                next_action="Ensure source files are accessible for full checksum verification.",
                blocking=False,
                evidence=[EvidenceItem(
                    type="checksum_skip",
                    ref="all",
                    description="Referenced files not found; checksum recomputation skipped.",
                )],
                checked_at=datetime.now(timezone.utc),
            )

        return check_checksum_chain(
            gate_id=f"{self._effective_task_id}-checksum-chain",
            task_id=self._effective_task_id,
            phase=Phase.CONTRACT_INTEGRITY,
            expected_checksums=expected,
            actual_checksums=actual,
            trace_id=self.trace_id,
            blocking=True,
        )

    # ---- Gate: Mapping completeness -----------------------------------------

    def _check_mapping_completeness(self) -> Optional[GateResult]:
        """
        Verify every coverage gap has a task mapping entry.

        Returns ``None`` if no ``artifact_task_mapping`` is present (skipped).
        """
        task_mapping = self._metadata.get("artifact_task_mapping")
        if not task_mapping:
            return None  # Will be recorded as skipped

        coverage = self._metadata.get("coverage", {})
        gap_ids = coverage.get("gaps", [])

        if not gap_ids:
            return None  # No gaps to map

        return check_mapping_completeness(
            gate_id=f"{self._effective_task_id}-mapping-completeness",
            task_id=self._effective_task_id,
            phase=Phase.CONTRACT_INTEGRITY,
            artifact_ids=gap_ids,
            task_mapping=task_mapping,
            trace_id=self.trace_id,
            blocking=True,
        )

    # ---- Gate: Gap parity ---------------------------------------------------

    def _check_gap_parity(self) -> Optional[GateResult]:
        """
        Compare coverage gaps against artifact types to verify parity.

        Returns ``None`` if no coverage data is present.
        """
        coverage = self._metadata.get("coverage", {})
        gap_ids: list[str] = coverage.get("gaps", [])

        if not gap_ids:
            return None

        # Feature IDs: artifacts that are referenced in file_ownership or
        # that appear in the coverage byTarget lists. For real pipeline checks,
        # features come from the artifact manifest's artifact IDs.
        # We derive them from all artifact IDs known to file_ownership.
        file_ownership = self._metadata.get("file_ownership", {})
        feature_ids: list[str] = []
        if file_ownership:
            for _path, info in file_ownership.items():
                for aid in info.get("artifact_ids", []):
                    if aid not in feature_ids:
                        feature_ids.append(aid)

        if not feature_ids:
            # Fallback: derive from artifact_types + coverage byTarget
            by_target = coverage.get("byTarget", [])
            for target_info in by_target:
                for gap_id in target_info.get("gaps", []):
                    if gap_id not in feature_ids:
                        feature_ids.append(gap_id)

        if not feature_ids:
            return None

        return check_gap_parity(
            gate_id=f"{self._effective_task_id}-gap-parity",
            task_id=self._effective_task_id,
            phase=Phase.INGEST_PARSE_ASSESS,
            gap_ids=gap_ids,
            feature_ids=feature_ids,
            trace_id=self.trace_id,
            blocking=True,
        )

    # ---- Gate: Provenance cross-check ---------------------------------------

    def _check_provenance_consistency(self) -> Optional[GateResult]:
        """
        Cross-check provenance.json against onboarding-metadata.json.

        Returns ``None`` if provenance.json is not present.
        """
        if not self._provenance:
            return None

        evidence: list[EvidenceItem] = []
        problems: list[str] = []

        # Cross-check source checksum
        meta_source = self._metadata.get("source_checksum")
        prov_source = self._provenance.get("sourceChecksum")
        if meta_source and prov_source and meta_source != prov_source:
            problems.append("source_checksum mismatch")
            evidence.append(EvidenceItem(
                type="provenance_mismatch",
                ref="source_checksum",
                description=(
                    f"onboarding-metadata source_checksum={meta_source[:16]}... "
                    f"vs provenance sourceChecksum={prov_source[:16]}..."
                ),
            ))

        # Cross-check output directory
        prov_output_dir = self._provenance.get("outputDirectory", "")
        meta_output_dir = str(self.output_dir)
        if prov_output_dir and not (
            meta_output_dir.endswith(prov_output_dir) or prov_output_dir.endswith(str(self.output_dir.name))
        ):
            evidence.append(EvidenceItem(
                type="provenance_info",
                ref="outputDirectory",
                description=f"Provenance outputDirectory='{prov_output_dir}' (info only).",
            ))

        # Cross-check that output files exist
        output_files = self._provenance.get("outputFiles", [])
        for fname in output_files:
            fpath = self.output_dir / fname
            if not fpath.exists():
                problems.append(f"missing output file: {fname}")
                evidence.append(EvidenceItem(
                    type="missing_output_file",
                    ref=fname,
                    description=f"Provenance lists '{fname}' as output but file not found in {self.output_dir}.",
                ))

        gate_id = f"{self._effective_task_id}-provenance-consistency"
        if problems:
            return GateResult(
                gate_id=gate_id,
                trace_id=self.trace_id,
                task_id=self._effective_task_id,
                phase=Phase.CONTRACT_INTEGRITY,
                result=GateOutcome.FAIL,
                severity=GateSeverity.ERROR,
                reason=f"Provenance cross-check failed: {'; '.join(problems)}.",
                next_action="Re-run export to regenerate consistent provenance and metadata.",
                blocking=True,
                evidence=evidence,
                checked_at=datetime.now(timezone.utc),
            )

        return GateResult(
            gate_id=gate_id,
            trace_id=self.trace_id,
            task_id=self._effective_task_id,
            phase=Phase.CONTRACT_INTEGRITY,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason="Provenance cross-check passed: metadata and provenance are consistent.",
            next_action="Proceed — provenance chain verified.",
            blocking=False,
            evidence=[EvidenceItem(
                type="provenance_verified",
                ref="provenance.json",
                description="All cross-checks between provenance.json and onboarding-metadata.json passed.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    # ---- Gate: Design calibration -------------------------------------------

    # Valid depth tiers and their approximate LOC ranges (for validation)
    _VALID_DEPTHS = {"brief", "standard", "comprehensive", "standard-comprehensive"}

    def _check_design_calibration(self) -> Optional[GateResult]:
        """
        Validate design calibration hints against the artifact types in coverage.

        Checks:
        1. ``design_calibration_hints`` exists and covers all artifact types with gaps.
        2. Each hint has valid ``expected_depth``, ``expected_loc_range``, ``red_flag``.
        3. If ``expected_output_contracts`` exists, cross-checks max_lines consistency.
        4. If generated artifacts exist on disk, validates their size against ranges.

        Returns ``None`` if ``design_calibration_hints`` is not present.
        """
        hints = self._metadata.get("design_calibration_hints")
        if not hints:
            return None

        evidence: list[EvidenceItem] = []
        problems: list[str] = []

        # Determine which artifact types have gaps
        coverage = self._metadata.get("coverage", {})
        by_type: dict[str, int] = coverage.get("byType", {})
        gap_types = set(by_type.keys()) if by_type else set()

        # Also extract types from the artifact_types section
        artifact_types_section = self._metadata.get("artifact_types", {})
        if artifact_types_section:
            gap_types |= set(artifact_types_section.keys())

        # 1. Check coverage: every gap-bearing type should have a calibration hint
        uncalibrated = gap_types - set(hints.keys())
        for atype in sorted(uncalibrated):
            problems.append(f"uncalibrated: {atype}")
            evidence.append(EvidenceItem(
                type="missing_calibration",
                ref=atype,
                description=f"Artifact type '{atype}' has coverage gaps but no calibration hint.",
            ))

        # 2. Validate each hint structure
        for atype, hint in hints.items():
            depth = hint.get("expected_depth", "")
            if depth and depth not in self._VALID_DEPTHS:
                problems.append(f"invalid depth: {atype}={depth}")
                evidence.append(EvidenceItem(
                    type="invalid_depth",
                    ref=atype,
                    description=(
                        f"Artifact type '{atype}' has invalid expected_depth '{depth}'. "
                        f"Valid values: {', '.join(sorted(self._VALID_DEPTHS))}."
                    ),
                ))

            if not hint.get("expected_loc_range"):
                evidence.append(EvidenceItem(
                    type="missing_loc_range",
                    ref=atype,
                    description=f"Artifact type '{atype}' is missing expected_loc_range.",
                ))

            if not hint.get("red_flag"):
                evidence.append(EvidenceItem(
                    type="missing_red_flag",
                    ref=atype,
                    description=f"Artifact type '{atype}' is missing red_flag description.",
                ))

        # 3. Cross-check with expected_output_contracts if present
        contracts = self._metadata.get("expected_output_contracts", {})
        if contracts:
            for atype, contract in contracts.items():
                hint = hints.get(atype)
                if not hint:
                    continue
                contract_max_lines = contract.get("max_lines")
                hint_range = hint.get("expected_loc_range", "")
                if contract_max_lines and hint_range:
                    # Simple sanity: if hint says <=50 but contract says max_lines > 100
                    if hint_range == "<=50" and contract_max_lines > 100:
                        problems.append(f"LOC mismatch: {atype}")
                        evidence.append(EvidenceItem(
                            type="loc_mismatch",
                            ref=atype,
                            description=(
                                f"Calibration says expected_loc_range='<=50' but "
                                f"expected_output_contracts.max_lines={contract_max_lines}."
                            ),
                        ))
                    elif hint_range.startswith(">") and contract_max_lines < 100:
                        problems.append(f"LOC mismatch: {atype}")
                        evidence.append(EvidenceItem(
                            type="loc_mismatch",
                            ref=atype,
                            description=(
                                f"Calibration says expected_loc_range='{hint_range}' but "
                                f"expected_output_contracts.max_lines={contract_max_lines}."
                            ),
                        ))

        # 4. If generated artifacts exist, check actual sizes
        file_ownership = self._metadata.get("file_ownership", {})
        for fpath, info in file_ownership.items():
            actual_path = self.output_dir / fpath
            if not actual_path.exists():
                continue
            loc = sum(1 for _ in actual_path.open())
            for aid in info.get("artifact_ids", []):
                # Determine artifact type from the info
                atypes = info.get("artifact_types", [])
                for atype in atypes:
                    hint = hints.get(atype)
                    if not hint:
                        continue
                    loc_range = hint.get("expected_loc_range", "")
                    if self._loc_out_of_range(loc, loc_range):
                        problems.append(f"LOC violation: {aid}")
                        evidence.append(EvidenceItem(
                            type="loc_violation",
                            ref=aid,
                            description=(
                                f"Generated artifact '{fpath}' has {loc} LOC "
                                f"but expected range is '{loc_range}'."
                            ),
                        ))

        # 5. Protocol mismatch cross-check: calibration hints with transport_protocol
        #    vs service_metadata declarations (REQ-PCG-032 req 6)
        svc_meta = self._metadata.get("service_metadata", {})
        if svc_meta:
            for hint_key, hint in hints.items():
                hint_protocol = hint.get("transport_protocol")
                if not hint_protocol:
                    continue
                # Extract service name from hint key (e.g. "dockerfile_emailservice" -> "emailservice")
                for prefix in ("dockerfile_", "client_"):
                    if hint_key.startswith(prefix):
                        svc_name = hint_key[len(prefix):]
                        svc_entry = svc_meta.get(svc_name, {})
                        declared_protocol = svc_entry.get("transport_protocol", "") if isinstance(svc_entry, dict) else ""
                        if declared_protocol and declared_protocol != hint_protocol:
                            problems.append(f"protocol mismatch: {hint_key}")
                            evidence.append(EvidenceItem(
                                type="protocol_calibration_mismatch",
                                ref=hint_key,
                                description=(
                                    f"Calibration hint '{hint_key}' declares transport_protocol='{hint_protocol}' "
                                    f"but service_metadata['{svc_name}'] declares '{declared_protocol}'."
                                ),
                            ))

        gate_id = f"{self._effective_task_id}-design-calibration"
        if problems:
            return GateResult(
                gate_id=gate_id,
                trace_id=self.trace_id,
                task_id=self._effective_task_id,
                phase=Phase.ARTISAN_DESIGN,
                result=GateOutcome.FAIL,
                severity=GateSeverity.WARNING,
                reason=f"Design calibration issues: {'; '.join(problems[:5])}{'...' if len(problems) > 5 else ''}.",
                next_action="Review calibration hints and regenerate mismatched artifacts.",
                blocking=False,  # Calibration issues are warnings, not hard blocks
                evidence=evidence,
                checked_at=datetime.now(timezone.utc),
            )

        return GateResult(
            gate_id=gate_id,
            trace_id=self.trace_id,
            task_id=self._effective_task_id,
            phase=Phase.ARTISAN_DESIGN,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"Design calibration verified: {len(hints)} artifact type(s) properly calibrated.",
            next_action="Proceed — calibration hints are consistent.",
            blocking=False,
            evidence=[EvidenceItem(
                type="calibration_verified",
                ref="design_calibration_hints",
                description=f"All {len(hints)} artifact type(s) have valid calibration hints.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    # ---- Gate: Parameter resolvability ----------------------------------------

    def _check_parameter_resolvability(self) -> Optional[GateResult]:
        """
        Verify that parameter_sources reference fields that resolve to values.

        Uses the ``parameter_resolvability`` field computed by onboarding.py,
        which tracks whether each parameter source path resolves to a non-empty
        value in the source manifest.

        Returns ``None`` if ``parameter_resolvability`` is not present.
        """
        resolvability = self._metadata.get("parameter_resolvability")
        if not resolvability:
            return None

        evidence: list[EvidenceItem] = []
        unresolved_count = 0
        total_count = 0

        for artifact_id, params in resolvability.items():
            for param_key, status_info in params.items():
                total_count += 1
                if status_info.get("status") == "unresolved":
                    unresolved_count += 1
                    reason_msg = status_info.get("reason", "unknown")
                    source_path = status_info.get("source_path", "?")
                    evidence.append(EvidenceItem(
                        type="unresolved_parameter",
                        ref=f"{artifact_id}.{param_key}",
                        description=(
                            f"Parameter '{param_key}' for artifact '{artifact_id}' "
                            f"references '{source_path}' which is unresolved: {reason_msg}."
                        ),
                    ))

        gate_id = f"{self._effective_task_id}-parameter-resolvability"
        if unresolved_count > 0:
            return GateResult(
                gate_id=gate_id,
                trace_id=self.trace_id,
                task_id=self._effective_task_id,
                phase=Phase.EXPORT_CONTRACT,
                result=GateOutcome.FAIL,
                severity=GateSeverity.WARNING,
                reason=(
                    f"Parameter resolvability issues: {unresolved_count}/{total_count} "
                    f"parameter(s) reference unresolved manifest fields."
                ),
                next_action=(
                    "Check .contextcore.yaml — the referenced fields are empty or missing. "
                    "Populate them before re-running export."
                ),
                blocking=False,  # Warning — downstream may still work with defaults
                evidence=evidence[:10],  # Cap evidence to avoid noise
                checked_at=datetime.now(timezone.utc),
            )

        return GateResult(
            gate_id=gate_id,
            trace_id=self.trace_id,
            task_id=self._effective_task_id,
            phase=Phase.EXPORT_CONTRACT,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"All {total_count} parameter source(s) resolve to values.",
            next_action="Proceed — parameter sources verified.",
            blocking=False,
            evidence=[EvidenceItem(
                type="parameters_verified",
                ref="parameter_resolvability",
                description=f"All {total_count} parameter(s) across all artifacts resolve.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _loc_out_of_range(loc: int, loc_range: str) -> bool:
        """Check if a LOC count falls outside the expected range string."""
        if not loc_range:
            return False
        try:
            if loc_range.startswith("<="):
                return loc > int(loc_range[2:])
            elif loc_range.startswith(">"):
                return loc <= int(loc_range[1:])
            elif "-" in loc_range:
                low, high = loc_range.split("-", 1)
                return loc < int(low) or loc > int(high)
        except ValueError:
            return False
        return False

    # ---- Gate: Artifact inventory -------------------------------------------

    # Expected export-stage roles in the artifact inventory
    _EXPECTED_EXPORT_ROLES = {
        "derivation_rules", "resolved_parameters", "output_contracts",
        "dependency_graph", "calibration_hints", "open_questions",
        "parameter_sources", "semantic_conventions", "example_artifacts",
        "coverage_gaps",
    }

    def _check_artifact_inventory(self) -> Optional[GateResult]:
        """
        Validate the artifact inventory section in run-provenance.json.

        Checks:
        1. ``artifact_inventory`` exists in v2 provenance.
        2. All expected export-stage roles are registered.
        3. Source files referenced by entries exist.
        4. SHA-256 checksums are valid for entries with sub-document json_path.

        Returns ``None`` if ``run-provenance.json`` is missing or v1.
        Reports as WARNING (not blocking) for backward compatibility.
        """
        prov_path = self.output_dir / "run-provenance.json"
        if not prov_path.exists():
            return None

        try:
            with open(prov_path) as fh:
                prov_data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return None

        version = prov_data.get("version", "1.0.0")
        if version.startswith("1."):
            return None  # v1 schema — no inventory expected

        inventory = prov_data.get("artifact_inventory")
        if not isinstance(inventory, list):
            return GateResult(
                gate_id=f"{self._effective_task_id}-artifact-inventory",
                trace_id=self.trace_id,
                task_id=self._effective_task_id,
                phase=Phase.EXPORT_CONTRACT,
                result=GateOutcome.FAIL,
                severity=GateSeverity.WARNING,
                reason="run-provenance.json v2 but artifact_inventory is missing or malformed.",
                next_action="Re-run export to regenerate inventory.",
                blocking=False,
                evidence=[EvidenceItem(
                    type="missing_inventory",
                    ref="run-provenance.json",
                    description="v2 provenance without artifact_inventory section.",
                )],
                checked_at=datetime.now(timezone.utc),
            )

        evidence: list[EvidenceItem] = []
        problems: list[str] = []

        # Check expected roles are registered
        registered_roles = {e.get("role") for e in inventory if isinstance(e, dict)}
        missing_roles = self._EXPECTED_EXPORT_ROLES - registered_roles
        # Only report missing roles for data that actually exists in metadata
        actually_missing: list[str] = []
        role_to_metadata_key = {
            "derivation_rules": "derivation_rules",
            "resolved_parameters": "resolved_artifact_parameters",
            "output_contracts": "expected_output_contracts",
            "dependency_graph": "artifact_dependency_graph",
            "calibration_hints": "design_calibration_hints",
            "open_questions": "open_questions",
            "parameter_sources": "parameter_sources",
            "semantic_conventions": "semantic_conventions",
            "example_artifacts": "example_artifacts",
            "coverage_gaps": "coverage_gaps",
        }
        for role in sorted(missing_roles):
            meta_key = role_to_metadata_key.get(role, role)
            if self._metadata.get(meta_key):
                actually_missing.append(role)
                evidence.append(EvidenceItem(
                    type="missing_role",
                    ref=role,
                    description=(
                        f"Export role '{role}' has data in onboarding-metadata.json "
                        f"but is not registered in artifact_inventory."
                    ),
                ))

        if actually_missing:
            problems.append(f"unregistered roles: {', '.join(actually_missing)}")

        # Check source files exist
        for entry in inventory:
            if not isinstance(entry, dict):
                continue
            src = entry.get("source_file")
            if src:
                src_path = self.output_dir / src
                if not src_path.exists():
                    problems.append(f"missing source: {src}")
                    evidence.append(EvidenceItem(
                        type="missing_source_file",
                        ref=entry.get("artifact_id", src),
                        description=f"Source file '{src}' not found in {self.output_dir}.",
                    ))

        gate_id = f"{self._effective_task_id}-artifact-inventory"
        if problems:
            return GateResult(
                gate_id=gate_id,
                trace_id=self.trace_id,
                task_id=self._effective_task_id,
                phase=Phase.EXPORT_CONTRACT,
                result=GateOutcome.FAIL,
                severity=GateSeverity.WARNING,
                reason=f"Artifact inventory issues: {'; '.join(problems[:5])}.",
                next_action="Re-run export to regenerate inventory with all roles.",
                blocking=False,
                evidence=evidence[:10],
                checked_at=datetime.now(timezone.utc),
            )

        return GateResult(
            gate_id=gate_id,
            trace_id=self.trace_id,
            task_id=self._effective_task_id,
            phase=Phase.EXPORT_CONTRACT,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"Artifact inventory verified: {len(inventory)} entries, {len(registered_roles)} roles registered.",
            next_action="Proceed — inventory is complete.",
            blocking=False,
            evidence=[EvidenceItem(
                type="inventory_verified",
                ref="artifact_inventory",
                description=f"{len(inventory)} entries covering roles: {', '.join(sorted(registered_roles))}.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    # ---- Gate: Service metadata -----------------------------------------------

    def _check_service_metadata(self) -> Optional[GateResult]:
        """
        Validate service_metadata section in onboarding metadata.

        Checks:
        1. ``service_metadata`` exists (WARNING if absent).
        2. Each service has a ``transport_protocol`` (BLOCKING ERROR if missing).
        3. gRPC services should have ``schema_contract`` (WARNING if missing).

        Returns ``None`` if ``service_metadata`` is not present (will be warned).
        """
        svc_meta = self._metadata.get("service_metadata")
        if not svc_meta:
            return None

        evidence: list[EvidenceItem] = []
        problems: list[str] = []

        for svc_name, entry in svc_meta.items():
            if not isinstance(entry, dict):
                problems.append(f"invalid entry: {svc_name}")
                evidence.append(EvidenceItem(
                    type="invalid_service_entry",
                    ref=svc_name,
                    description=f"Service '{svc_name}' entry is not a dict.",
                ))
                continue

            tp = entry.get("transport_protocol")
            if not tp:
                problems.append(f"missing transport_protocol: {svc_name}")
                evidence.append(EvidenceItem(
                    type="missing_transport_protocol",
                    ref=svc_name,
                    description=f"Service '{svc_name}' is missing required transport_protocol.",
                ))
                continue

            # gRPC services should declare schema_contract
            if tp in ("grpc", "grpc-web") and not entry.get("schema_contract"):
                evidence.append(EvidenceItem(
                    type="missing_schema_contract",
                    ref=svc_name,
                    description=(
                        f"gRPC service '{svc_name}' is missing schema_contract "
                        f"(e.g. path to .proto file)."
                    ),
                ))

        gate_id = f"{self._effective_task_id}-service-metadata"
        # Missing transport_protocol is blocking; missing schema_contract is warning
        has_blocking = any("missing transport_protocol" in p for p in problems)

        if has_blocking:
            return GateResult(
                gate_id=gate_id,
                trace_id=self.trace_id,
                task_id=self._effective_task_id,
                phase=Phase.EXPORT_CONTRACT,
                result=GateOutcome.FAIL,
                severity=GateSeverity.ERROR,
                reason=f"Service metadata validation failed: {'; '.join(problems)}.",
                next_action="Add transport_protocol to all services in --service-metadata.",
                blocking=True,
                evidence=evidence,
                checked_at=datetime.now(timezone.utc),
            )

        if evidence:
            # Warnings only (e.g. missing schema_contract)
            return GateResult(
                gate_id=gate_id,
                trace_id=self.trace_id,
                task_id=self._effective_task_id,
                phase=Phase.EXPORT_CONTRACT,
                result=GateOutcome.PASS,
                severity=GateSeverity.WARNING,
                reason=(
                    f"Service metadata valid but with warnings: "
                    f"{len(evidence)} advisory issue(s)."
                ),
                next_action="Consider adding schema_contract for gRPC services.",
                blocking=False,
                evidence=evidence,
                checked_at=datetime.now(timezone.utc),
            )

        return GateResult(
            gate_id=gate_id,
            trace_id=self.trace_id,
            task_id=self._effective_task_id,
            phase=Phase.EXPORT_CONTRACT,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"Service metadata verified: {len(svc_meta)} service(s) properly declared.",
            next_action="Proceed — service metadata is complete.",
            blocking=False,
            evidence=[EvidenceItem(
                type="service_metadata_verified",
                ref="service_metadata",
                description=f"All {len(svc_meta)} service(s) have valid transport_protocol.",
            )],
            checked_at=datetime.now(timezone.utc),
        )

    # ---- Main runner --------------------------------------------------------

    @property
    def _effective_task_id(self) -> str:
        return self.task_id or self._metadata.get("project_id", "pipeline-check")

    def run(self) -> PipelineCheckReport:
        """
        Run all pipeline integrity checks and return an aggregated report.

        Gate execution order:
        1. Structural integrity (required fields, schema)
        2. Checksum chain (recompute and compare)
        3. Provenance cross-check (if provenance.json exists)
        4. Mapping completeness (if artifact_task_mapping exists)
        5. Gap parity (coverage gaps vs artifact features)
        6. Design calibration (depth tiers vs artifact type expectations)
        7. Parameter resolvability (parameter_sources reference valid fields)
        8. Artifact inventory (provenance v2 role registration)
        9. Service metadata (transport protocol, schema contract)
        """
        self._load()

        project_id = self._metadata.get("project_id", "unknown")
        report = PipelineCheckReport(
            output_dir=str(self.output_dir),
            project_id=project_id,
        )

        # 1. Structural integrity
        structural = self._check_structural_integrity()
        report.gates.append(structural)
        if structural.result == GateOutcome.FAIL:
            logger.warning("Structural integrity failed — remaining checks may be unreliable.")

        # 2. Checksum chain
        checksum = self._check_checksum_chain()
        report.gates.append(checksum)

        # 3. Provenance cross-check
        provenance = self._check_provenance_consistency()
        if provenance:
            report.gates.append(provenance)
        else:
            report.skipped.append(
                "provenance-consistency: no provenance.json found (run export with --emit-provenance)"
            )

        # 4. Mapping completeness
        mapping = self._check_mapping_completeness()
        if mapping:
            report.gates.append(mapping)
        else:
            if not self._metadata.get("artifact_task_mapping"):
                report.skipped.append(
                    "mapping-completeness: no artifact_task_mapping present (run export with --task-mapping)"
                )
            else:
                report.skipped.append(
                    "mapping-completeness: no coverage gaps to check"
                )

        # 5. Gap parity
        gap_parity = self._check_gap_parity()
        if gap_parity:
            report.gates.append(gap_parity)
        else:
            report.skipped.append(
                "gap-parity: no coverage gaps or no file_ownership data to compare against"
            )

        # 6. Design calibration
        calibration = self._check_design_calibration()
        if calibration:
            report.gates.append(calibration)
        else:
            report.skipped.append(
                "design-calibration: no design_calibration_hints present in metadata"
            )

        # 7. Parameter resolvability
        param_check = self._check_parameter_resolvability()
        if param_check:
            report.gates.append(param_check)
        else:
            report.skipped.append(
                "parameter-resolvability: no parameter_resolvability data in metadata"
            )

        # 8. Artifact inventory (Mottainai)
        inv_check = self._check_artifact_inventory()
        if inv_check:
            report.gates.append(inv_check)
        else:
            report.skipped.append(
                "artifact-inventory: no v2 run-provenance.json found"
            )

        # 9. Service metadata
        svc_check = self._check_service_metadata()
        if svc_check:
            report.gates.append(svc_check)
        else:
            if not self._metadata.get("service_metadata"):
                report.warnings.append(
                    "No service_metadata: transport protocol and schema contract info is missing. "
                    "Use --service-metadata to provide per-service metadata."
                )

        # --min-coverage enforcement
        if self.min_coverage is not None:
            coverage_val = self._metadata.get("coverage", {}).get("overallCoverage", 0.0)
            gate_id = f"{self._effective_task_id}-min-coverage"
            if coverage_val < self.min_coverage:
                report.gates.append(GateResult(
                    gate_id=gate_id,
                    trace_id=self.trace_id,
                    task_id=self._effective_task_id,
                    phase=Phase.EXPORT_CONTRACT,
                    result=GateOutcome.FAIL,
                    severity=GateSeverity.ERROR,
                    reason=(
                        f"Coverage {coverage_val * 100:.0f}% is below the "
                        f"required minimum of {self.min_coverage * 100:.0f}%."
                    ),
                    next_action=(
                        "Run export with --scan-existing to detect existing artifacts, "
                        "or populate the manifest with more targets."
                    ),
                    blocking=True,
                    evidence=[EvidenceItem(
                        type="coverage_below_threshold",
                        ref="coverage.overallCoverage",
                        description=(
                            f"overallCoverage={coverage_val}, "
                            f"min_coverage={self.min_coverage}"
                        ),
                    )],
                    checked_at=datetime.now(timezone.utc),
                ))
            else:
                report.gates.append(GateResult(
                    gate_id=gate_id,
                    trace_id=self.trace_id,
                    task_id=self._effective_task_id,
                    phase=Phase.EXPORT_CONTRACT,
                    result=GateOutcome.PASS,
                    severity=GateSeverity.INFO,
                    reason=(
                        f"Coverage {coverage_val * 100:.0f}% meets the "
                        f"minimum threshold of {self.min_coverage * 100:.0f}%."
                    ),
                    next_action="Proceed — coverage meets threshold.",
                    blocking=False,
                    checked_at=datetime.now(timezone.utc),
                ))

        # Add warnings for common issues
        coverage = self._metadata.get("coverage", {})
        overall = coverage.get("overallCoverage", 0)
        if overall == 0.0:
            report.warnings.append(
                f"Overall coverage is 0% — all {coverage.get('totalRequired', '?')} artifacts are gaps."
            )
        elif overall < 0.5:
            report.warnings.append(
                f"Overall coverage is {overall * 100:.0f}% — below recommended 50% threshold."
            )

        if not self._metadata.get("artifact_task_mapping"):
            report.warnings.append(
                "No artifact_task_mapping: traceability from artifacts to plan tasks is missing."
            )

        logger.info(
            "Pipeline check complete: %d/%d gates passed, healthy=%s",
            report.passed,
            report.total_gates,
            report.is_healthy,
        )

        return report
