"""
Phase gate library for A2A governance.

Provides reusable gate checks that emit :class:`GateResult` objects and
optionally block downstream phase execution on failure.

Day 4 spec gates:
- **Checksum chain integrity** — ``check_checksum_chain``
- **Artifact-task mapping completeness** — ``check_mapping_completeness``
- **Gap parity** — ``check_gap_parity``

Usage::

    from contextcore.contracts.a2a.gates import GateChecker

    checker = GateChecker(trace_id="trace-123")

    result = checker.check_checksum_chain(
        task_id="PI-101-002-S3",
        expected={"source": "sha256:aaa"},
        actual={"source": "sha256:aaa"},
    )
    if result.blocking and result.result.value == "fail":
        # Do not proceed to the next phase
        ...
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from contextcore.contracts.a2a.models import (
    EvidenceItem,
    GateOutcome,
    GateResult,
    GateSeverity,
    Phase,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standalone gate functions
# ---------------------------------------------------------------------------


def check_checksum_chain(
    *,
    gate_id: str,
    task_id: str,
    phase: Phase | str = Phase.CONTRACT_INTEGRITY,
    expected_checksums: dict[str, str],
    actual_checksums: dict[str, str],
    trace_id: str | None = None,
    blocking: bool = True,
) -> GateResult:
    """
    Verify that actual checksums match the expected chain.

    Compares each key in *expected_checksums* against *actual_checksums*.
    Any mismatch or missing key is a failure.

    Args:
        gate_id: Unique gate identifier (e.g. ``PI-101-002-S3-C2``).
        task_id: Parent task span ID.
        phase: Execution phase (default ``CONTRACT_INTEGRITY``).
        expected_checksums: Map of label -> expected hash.
        actual_checksums: Map of label -> actual hash.
        trace_id: Optional trace ID.
        blocking: Whether a failure should block downstream phases.

    Returns:
        A :class:`GateResult` recording the outcome.
    """
    if isinstance(phase, str):
        phase = Phase(phase)

    mismatches: list[str] = []
    missing: list[str] = []
    evidence: list[EvidenceItem] = []

    for key, expected_hash in expected_checksums.items():
        actual_hash = actual_checksums.get(key)
        if actual_hash is None:
            missing.append(key)
            evidence.append(
                EvidenceItem(
                    type="checksum_missing",
                    ref=key,
                    description=f"Expected checksum for '{key}' but not found in actual checksums.",
                )
            )
        elif actual_hash != expected_hash:
            mismatches.append(key)
            evidence.append(
                EvidenceItem(
                    type="checksum_mismatch",
                    ref=key,
                    description=(
                        f"Checksum mismatch for '{key}': "
                        f"expected={expected_hash}, actual={actual_hash}"
                    ),
                )
            )

    if mismatches or missing:
        reason_parts = []
        if mismatches:
            reason_parts.append(f"mismatched: {', '.join(mismatches)}")
        if missing:
            reason_parts.append(f"missing: {', '.join(missing)}")
        reason = "Checksum chain broken — " + "; ".join(reason_parts)

        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.FAIL,
            severity=GateSeverity.ERROR,
            reason=reason,
            next_action="Regenerate upstream artifacts with matching checksums before proceeding.",
            blocking=blocking,
            evidence=evidence,
            checked_at=datetime.now(timezone.utc),
        )
    else:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason="All checksums match expected chain.",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            evidence=[
                EvidenceItem(
                    type="checksum_verified",
                    ref="all",
                    description=f"Verified {len(expected_checksums)} checksum(s).",
                )
            ],
            checked_at=datetime.now(timezone.utc),
        )

    logger.info(
        "Gate %s [%s]: %s",
        gate_id,
        result.result.value,
        result.reason,
    )
    return result


def check_mapping_completeness(
    *,
    gate_id: str,
    task_id: str,
    phase: Phase | str = Phase.CONTRACT_INTEGRITY,
    artifact_ids: list[str],
    task_mapping: dict[str, str],
    trace_id: str | None = None,
    blocking: bool = True,
) -> GateResult:
    """
    Verify that every artifact ID has a corresponding task mapping entry.

    Args:
        gate_id: Unique gate identifier (e.g. ``PI-101-002-S3-C1``).
        task_id: Parent task span ID.
        phase: Execution phase (default ``CONTRACT_INTEGRITY``).
        artifact_ids: List of artifact IDs that must be mapped.
        task_mapping: Dict mapping artifact IDs to task IDs.
        trace_id: Optional trace ID.
        blocking: Whether a failure should block downstream phases.

    Returns:
        A :class:`GateResult` recording the outcome.
    """
    if isinstance(phase, str):
        phase = Phase(phase)

    unmapped = [aid for aid in artifact_ids if aid not in task_mapping]
    evidence: list[EvidenceItem] = []

    if unmapped:
        for aid in unmapped:
            evidence.append(
                EvidenceItem(
                    type="unmapped_artifact",
                    ref=aid,
                    description=f"Artifact '{aid}' has no task mapping entry.",
                )
            )

        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.FAIL,
            severity=GateSeverity.ERROR,
            reason=f"Mapping incomplete: {len(unmapped)} artifact(s) unmapped — {', '.join(unmapped)}.",
            next_action="Add task mapping entries for all unmapped artifacts before proceeding.",
            blocking=blocking,
            evidence=evidence,
            checked_at=datetime.now(timezone.utc),
        )
    else:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"All {len(artifact_ids)} artifact(s) mapped to tasks.",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            evidence=[
                EvidenceItem(
                    type="mapping_complete",
                    ref="artifact_task_mapping",
                    description=f"Verified {len(artifact_ids)} mapping(s).",
                )
            ],
            checked_at=datetime.now(timezone.utc),
        )

    logger.info(
        "Gate %s [%s]: %s",
        gate_id,
        result.result.value,
        result.reason,
    )
    return result


def check_gap_parity(
    *,
    gate_id: str,
    task_id: str,
    phase: Phase | str = Phase.INGEST_PARSE_ASSESS,
    gap_ids: list[str],
    feature_ids: list[str],
    trace_id: str | None = None,
    blocking: bool = True,
) -> GateResult:
    """
    Verify that the set of gaps and the set of parsed features are in parity.

    Every gap should have a corresponding feature, and no features should be
    orphaned (present without a gap).  This catches artifacts that were
    silently dropped during PARSE/TRANSFORM.

    Args:
        gate_id: Unique gate identifier (e.g. ``PI-101-002-S4-C1``).
        task_id: Parent task span ID.
        phase: Execution phase (default ``INGEST_PARSE_ASSESS``).
        gap_ids: Coverage gap identifiers from the assessment.
        feature_ids: Feature identifiers produced by the parser.
        trace_id: Optional trace ID.
        blocking: Whether a failure should block downstream phases.

    Returns:
        A :class:`GateResult` recording the outcome.
    """
    if isinstance(phase, str):
        phase = Phase(phase)

    gap_set = set(gap_ids)
    feature_set = set(feature_ids)
    missing_features = gap_set - feature_set
    orphan_features = feature_set - gap_set

    evidence: list[EvidenceItem] = []
    problems: list[str] = []

    if missing_features:
        problems.append(f"{len(missing_features)} gap(s) have no matching feature")
        for gid in sorted(missing_features):
            evidence.append(
                EvidenceItem(
                    type="missing_feature",
                    ref=gid,
                    description=f"Gap '{gid}' has no corresponding parsed feature.",
                )
            )

    if orphan_features:
        problems.append(f"{len(orphan_features)} feature(s) have no matching gap")
        for fid in sorted(orphan_features):
            evidence.append(
                EvidenceItem(
                    type="orphan_feature",
                    ref=fid,
                    description=f"Feature '{fid}' has no corresponding gap.",
                )
            )

    if problems:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.FAIL,
            severity=GateSeverity.ERROR,
            reason=f"Gap parity broken: {'; '.join(problems)}.",
            next_action=(
                "Re-run PARSE/TRANSFORM to ensure all gaps produce features "
                "and no artifacts are dropped."
            ),
            blocking=blocking,
            evidence=evidence,
            checked_at=datetime.now(timezone.utc),
        )
    else:
        result = GateResult(
            gate_id=gate_id,
            trace_id=trace_id,
            task_id=task_id,
            phase=phase,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"Gap parity verified: {len(gap_ids)} gap(s) ↔ {len(feature_ids)} feature(s).",
            next_action=f"Proceed to next phase after {phase.value}.",
            blocking=False,
            evidence=[
                EvidenceItem(
                    type="gap_parity_verified",
                    ref="coverage",
                    description=f"All {len(gap_ids)} gap(s) have matching features.",
                )
            ],
            checked_at=datetime.now(timezone.utc),
        )

    logger.info(
        "Gate %s [%s]: %s",
        gate_id,
        result.result.value,
        result.reason,
    )
    return result


# ---------------------------------------------------------------------------
# GateChecker — convenience class carrying shared context
# ---------------------------------------------------------------------------


class GateChecker:
    """
    Convenience wrapper that carries shared context (trace_id, project_id)
    across multiple gate checks.

    Usage::

        checker = GateChecker(trace_id="trace-123")
        r1 = checker.check_checksum_chain(...)
        r2 = checker.check_mapping_completeness(...)
        if checker.has_blocking_failure:
            print("Blocked:", checker.blocking_failures)
    """

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id
        self.results: list[GateResult] = []

    # --- Properties --------------------------------------------------------

    @property
    def has_blocking_failure(self) -> bool:
        """``True`` if any gate result is blocking **and** failed."""
        return any(
            r.blocking and r.result == GateOutcome.FAIL for r in self.results
        )

    @property
    def blocking_failures(self) -> list[GateResult]:
        """Return all blocking failures."""
        return [
            r for r in self.results
            if r.blocking and r.result == GateOutcome.FAIL
        ]

    @property
    def all_passed(self) -> bool:
        """``True`` if every gate passed."""
        return all(r.result == GateOutcome.PASS for r in self.results)

    # --- Delegate methods --------------------------------------------------

    def check_checksum_chain(
        self,
        *,
        gate_id: str,
        task_id: str,
        expected_checksums: dict[str, str],
        actual_checksums: dict[str, str],
        phase: Phase | str = Phase.CONTRACT_INTEGRITY,
        blocking: bool = True,
    ) -> GateResult:
        """Run :func:`check_checksum_chain` and record the result."""
        result = check_checksum_chain(
            gate_id=gate_id,
            task_id=task_id,
            phase=phase,
            expected_checksums=expected_checksums,
            actual_checksums=actual_checksums,
            trace_id=self.trace_id,
            blocking=blocking,
        )
        self.results.append(result)
        return result

    def check_mapping_completeness(
        self,
        *,
        gate_id: str,
        task_id: str,
        artifact_ids: list[str],
        task_mapping: dict[str, str],
        phase: Phase | str = Phase.CONTRACT_INTEGRITY,
        blocking: bool = True,
    ) -> GateResult:
        """Run :func:`check_mapping_completeness` and record the result."""
        result = check_mapping_completeness(
            gate_id=gate_id,
            task_id=task_id,
            phase=phase,
            artifact_ids=artifact_ids,
            task_mapping=task_mapping,
            trace_id=self.trace_id,
            blocking=blocking,
        )
        self.results.append(result)
        return result

    def check_gap_parity(
        self,
        *,
        gate_id: str,
        task_id: str,
        gap_ids: list[str],
        feature_ids: list[str],
        phase: Phase | str = Phase.INGEST_PARSE_ASSESS,
        blocking: bool = True,
    ) -> GateResult:
        """Run :func:`check_gap_parity` and record the result."""
        result = check_gap_parity(
            gate_id=gate_id,
            task_id=task_id,
            phase=phase,
            gap_ids=gap_ids,
            feature_ids=feature_ids,
            trace_id=self.trace_id,
            blocking=blocking,
        )
        self.results.append(result)
        return result

    def summary(self) -> dict[str, Any]:
        """Return a summary dict suitable for logging / telemetry."""
        return {
            "total_gates": len(self.results),
            "passed": sum(1 for r in self.results if r.result == GateOutcome.PASS),
            "failed": sum(1 for r in self.results if r.result == GateOutcome.FAIL),
            "blocking_failures": len(self.blocking_failures),
            "all_passed": self.all_passed,
            "gate_ids": [r.gate_id for r in self.results],
        }
