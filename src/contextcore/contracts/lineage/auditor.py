"""
Provenance auditor for data lineage contracts.

Verifies that recorded transformation history in the pipeline context
matches the declared lineage chains in a ``LineageContract``.  Detects:

- **Missing stages**: declared stages with no corresponding record.
- **Unexpected mutations**: passthrough operations where the hash changed.
- **Expected transforms**: transform operations where the hash stayed the same.

Usage::

    from contextcore.contracts.lineage.auditor import ProvenanceAuditor
    from contextcore.contracts.lineage.loader import LineageLoader

    loader = LineageLoader()
    contract = loader.load(Path("lineage.contract.yaml"))
    auditor = ProvenanceAuditor(contract)
    summary = auditor.audit_all(context)
    assert summary.passed
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.lineage.schema import LineageChainSpec, LineageContract
from contextcore.contracts.lineage.tracker import LineageTracker, TransformationRecord
from contextcore.contracts.types import LineageStatus, TransformOp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class LineageAuditResult(BaseModel):
    """Result of auditing a single lineage chain."""

    model_config = ConfigDict(extra="forbid")

    chain_id: str
    status: LineageStatus
    expected_stages: int
    actual_stages: int
    broken_links: list[str] = Field(default_factory=list)
    mutations: list[str] = Field(default_factory=list)
    message: str = ""


class LineageAuditSummary(BaseModel):
    """Aggregated result of auditing all lineage chains in a contract."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    total_chains: int
    results: list[LineageAuditResult] = Field(default_factory=list)
    verified_count: int = 0
    broken_count: int = 0


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------


class ProvenanceAuditor:
    """Audits lineage chains against recorded transformation history.

    Args:
        contract: The loaded lineage contract declaring expected chains.
    """

    def __init__(self, contract: LineageContract) -> None:
        self._contract = contract
        self._tracker = LineageTracker()

    def audit_chain(
        self,
        chain: LineageChainSpec,
        context: dict[str, Any],
    ) -> LineageAuditResult:
        """Audit a single lineage chain against the context.

        Checks:
        1. All declared stages have corresponding transformation records.
        2. PASSTHROUGH operations have ``input_hash == output_hash``.
        3. TRANSFORM operations have ``input_hash != output_hash``.

        Args:
            chain: The declared lineage chain spec.
            context: The shared workflow context dict containing lineage
                     metadata under ``_cc_lineage``.

        Returns:
            A ``LineageAuditResult`` with the chain audit outcome.
        """
        history: list[TransformationRecord] = self._tracker.get_history(
            context, chain.field
        )

        expected_stages = len(chain.stages)
        actual_stages = len(history)
        broken_links: list[str] = []
        mutations: list[str] = []

        # Build a lookup of recorded records by (phase, operation)
        recorded_by_phase: dict[str, TransformationRecord] = {}
        for record in history:
            # Key by phase — if multiple records for same phase, last wins
            recorded_by_phase[record.phase] = record

        # Check each declared stage
        for stage in chain.stages:
            record = recorded_by_phase.get(stage.phase)

            if record is None:
                broken_links.append(
                    f"Stage '{stage.phase}' ({stage.operation.value}): "
                    f"no transformation record found"
                )
                continue

            # Operation-specific hash checks
            if stage.operation == TransformOp.PASSTHROUGH:
                if record.input_hash != record.output_hash:
                    mutations.append(
                        f"Stage '{stage.phase}' (passthrough): "
                        f"unexpected mutation — "
                        f"input_hash={record.input_hash} != "
                        f"output_hash={record.output_hash}"
                    )

            elif stage.operation == TransformOp.TRANSFORM:
                if record.input_hash == record.output_hash:
                    mutations.append(
                        f"Stage '{stage.phase}' (transform): "
                        f"expected mutation but hashes match — "
                        f"input_hash={record.input_hash} == "
                        f"output_hash={record.output_hash}"
                    )

        # Determine status
        if broken_links:
            if actual_stages == 0:
                status = LineageStatus.CHAIN_BROKEN
                message = (
                    f"No transformation records for field '{chain.field}'; "
                    f"expected {expected_stages} stages"
                )
            else:
                status = LineageStatus.INCOMPLETE
                message = (
                    f"{len(broken_links)} of {expected_stages} stages missing "
                    f"for field '{chain.field}'"
                )
        elif mutations:
            status = LineageStatus.MUTATION_DETECTED
            message = (
                f"{len(mutations)} unexpected mutation(s) in chain "
                f"'{chain.chain_id}'"
            )
        else:
            status = LineageStatus.VERIFIED
            message = (
                f"Chain '{chain.chain_id}' verified: "
                f"{actual_stages} stages match declaration"
            )

        result = LineageAuditResult(
            chain_id=chain.chain_id,
            status=status,
            expected_stages=expected_stages,
            actual_stages=actual_stages,
            broken_links=broken_links,
            mutations=mutations,
            message=message,
        )

        if status != LineageStatus.VERIFIED:
            logger.warning(
                "Lineage audit: chain=%s status=%s — %s",
                chain.chain_id,
                status.value,
                message,
            )
        else:
            logger.debug(
                "Lineage audit: chain=%s verified", chain.chain_id
            )

        return result

    def audit_all(
        self,
        context: dict[str, Any],
    ) -> LineageAuditSummary:
        """Audit all chains declared in the contract.

        Args:
            context: The shared workflow context dict.

        Returns:
            A ``LineageAuditSummary`` with per-chain results and counts.
        """
        results: list[LineageAuditResult] = []
        verified_count = 0
        broken_count = 0

        for chain in self._contract.chains:
            result = self.audit_chain(chain, context)
            results.append(result)

            if result.status == LineageStatus.VERIFIED:
                verified_count += 1
            else:
                broken_count += 1

        passed = broken_count == 0
        total_chains = len(results)

        if passed:
            logger.info(
                "Lineage audit passed: %d/%d chains verified",
                verified_count,
                total_chains,
            )
        else:
            logger.warning(
                "Lineage audit: %d/%d chains failed",
                broken_count,
                total_chains,
            )

        return LineageAuditSummary(
            passed=passed,
            total_chains=total_chains,
            results=results,
            verified_count=verified_count,
            broken_count=broken_count,
        )
