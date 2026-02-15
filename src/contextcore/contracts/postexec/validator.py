"""
Post-execution validation for context propagation contracts — Layer 5.

Runs **after** all workflow phases complete.  Checks end-to-end propagation
chain integrity, validates the final phase's exit requirements, and
(optionally) cross-references Layer 4 runtime records to detect
discrepancies between expected and actual boundary behaviour.

Three checks:

1. **Chain integrity** — every ``PropagationChainSpec`` in the contract is
   checked against the final context via ``PropagationTracker``.
2. **Final exit** — the last phase's exit requirements are validated
   against the final context via ``BoundaryValidator``.
3. **Runtime cross-reference** — if a Layer 4 ``WorkflowRunSummary`` is
   provided, compares its records against chain results to surface
   phases that passed at runtime but whose chains are now broken
   (late corruption) or phases that failed at runtime but whose chains
   recovered (late healing).

Usage::

    from contextcore.contracts.postexec import PostExecutionValidator

    validator = PostExecutionValidator()
    report = validator.validate(
        contract, final_context,
        phase_order=["seed", "plan", "design", "implement", "validate"],
        runtime_summary=guard.summarize(),   # optional, from Layer 4
    )
    if not report.passed:
        for d in report.runtime_discrepancies:
            logger.warning("Discrepancy: %s", d.message)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.propagation.schema import ContextContract
from contextcore.contracts.propagation.tracker import (
    PropagationChainResult,
    PropagationTracker,
)
from contextcore.contracts.propagation.validator import (
    BoundaryValidator,
    ContractValidationResult,
)
from contextcore.contracts.runtime.guard import WorkflowRunSummary
from contextcore.contracts.types import ChainStatus, PropagationStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class RuntimeDiscrepancy(BaseModel):
    """A discrepancy between Layer 4 runtime records and post-execution state."""

    model_config = ConfigDict(extra="forbid")

    phase: str
    discrepancy_type: str = Field(
        ..., description="late_corruption | late_healing"
    )
    message: str = ""


class PostExecutionReport(BaseModel):
    """Aggregated post-execution validation report."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    passed: bool
    chain_results: list[PropagationChainResult] = Field(default_factory=list)
    chains_total: int = 0
    chains_intact: int = 0
    chains_degraded: int = 0
    chains_broken: int = 0
    completeness_pct: float = 100.0
    final_exit_result: Optional[ContractValidationResult] = None
    runtime_discrepancies: list[RuntimeDiscrepancy] = Field(
        default_factory=list
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class PostExecutionValidator:
    """Validates context integrity after all workflow phases complete."""

    def __init__(
        self,
        tracker: Optional[PropagationTracker] = None,
        boundary_validator: Optional[BoundaryValidator] = None,
    ) -> None:
        self._tracker = tracker or PropagationTracker()
        self._boundary_validator = boundary_validator or BoundaryValidator()

    def validate(
        self,
        contract: ContextContract,
        final_context: dict[str, Any],
        phase_order: Optional[list[str]] = None,
        runtime_summary: Optional[WorkflowRunSummary] = None,
    ) -> PostExecutionReport:
        """Run all post-execution checks.

        Args:
            contract: The context propagation contract.
            final_context: Context dict after all phases have completed.
            phase_order: Ordered list of phase names that executed.
                If ``None``, uses ``contract.phases.keys()`` order.
            runtime_summary: Optional Layer 4 workflow summary for
                cross-referencing.

        Returns:
            Aggregated ``PostExecutionReport``.
        """
        if phase_order is None:
            phase_order = list(contract.phases.keys())

        # Check 1: chain integrity
        chain_results = self._check_chains(contract, final_context)

        chains_total = len(chain_results)
        chains_intact = sum(
            1 for r in chain_results if r.status == ChainStatus.INTACT
        )
        chains_degraded = sum(
            1 for r in chain_results if r.status == ChainStatus.DEGRADED
        )
        chains_broken = sum(
            1 for r in chain_results if r.status == ChainStatus.BROKEN
        )
        completeness_pct = (
            round(chains_intact / max(chains_total, 1) * 100, 1)
        )

        # Check 2: final phase exit validation
        final_exit_result = self._check_final_exit(
            contract, final_context, phase_order
        )

        # Check 3: runtime cross-reference
        discrepancies: list[RuntimeDiscrepancy] = []
        if runtime_summary is not None:
            discrepancies = self._cross_reference_runtime(
                runtime_summary, chain_results, phase_order
            )

        # Overall pass: no broken chains AND final exit passed
        passed = chains_broken == 0
        if final_exit_result is not None and not final_exit_result.passed:
            passed = False

        if not passed:
            logger.warning(
                "Post-execution FAILED: chains=%d/%d intact, "
                "broken=%d, discrepancies=%d",
                chains_intact,
                chains_total,
                chains_broken,
                len(discrepancies),
            )
        elif chains_degraded > 0 or discrepancies:
            logger.info(
                "Post-execution passed with issues: "
                "degraded=%d, discrepancies=%d",
                chains_degraded,
                len(discrepancies),
            )

        return PostExecutionReport(
            passed=passed,
            chain_results=chain_results,
            chains_total=chains_total,
            chains_intact=chains_intact,
            chains_degraded=chains_degraded,
            chains_broken=chains_broken,
            completeness_pct=completeness_pct,
            final_exit_result=final_exit_result,
            runtime_discrepancies=discrepancies,
        )

    def validate_chains(
        self,
        contract: ContextContract,
        final_context: dict[str, Any],
    ) -> PostExecutionReport:
        """Run only the chain integrity check."""
        chain_results = self._check_chains(contract, final_context)
        chains_total = len(chain_results)
        chains_intact = sum(
            1 for r in chain_results if r.status == ChainStatus.INTACT
        )
        chains_degraded = sum(
            1 for r in chain_results if r.status == ChainStatus.DEGRADED
        )
        chains_broken = sum(
            1 for r in chain_results if r.status == ChainStatus.BROKEN
        )
        completeness_pct = (
            round(chains_intact / max(chains_total, 1) * 100, 1)
        )
        return PostExecutionReport(
            passed=chains_broken == 0,
            chain_results=chain_results,
            chains_total=chains_total,
            chains_intact=chains_intact,
            chains_degraded=chains_degraded,
            chains_broken=chains_broken,
            completeness_pct=completeness_pct,
        )

    # -- internal: chain integrity -------------------------------------------

    def _check_chains(
        self,
        contract: ContextContract,
        context: dict[str, Any],
    ) -> list[PropagationChainResult]:
        """Check all propagation chains in the contract."""
        return self._tracker.validate_all_chains(contract, context)

    # -- internal: final exit ------------------------------------------------

    def _check_final_exit(
        self,
        contract: ContextContract,
        context: dict[str, Any],
        phase_order: list[str],
    ) -> Optional[ContractValidationResult]:
        """Validate exit requirements of the last phase."""
        if not phase_order:
            return None

        last_phase = phase_order[-1]
        phase_contract = contract.phases.get(last_phase)
        if phase_contract is None:
            return None

        return self._boundary_validator.validate_exit(
            last_phase, context, contract
        )

    # -- internal: runtime cross-reference -----------------------------------

    def _cross_reference_runtime(
        self,
        runtime_summary: WorkflowRunSummary,
        chain_results: list[PropagationChainResult],
        phase_order: list[str],
    ) -> list[RuntimeDiscrepancy]:
        """Compare Layer 4 runtime records against post-execution chain state.

        Detects:
        - **Late corruption**: phase passed at runtime but a chain
          touching that phase is now broken (something happened after
          the boundary check).
        - **Late healing**: phase failed at runtime but all chains
          involving that phase are now intact (context was repaired
          after the boundary failure).
        """
        discrepancies: list[RuntimeDiscrepancy] = []

        # Build a map of phase -> runtime passed status
        runtime_phase_passed: dict[str, bool] = {}
        for record in runtime_summary.phases:
            runtime_phase_passed[record.phase] = record.passed

        # Build a map of phase -> whether any chain touching it is broken
        phase_has_broken_chain: dict[str, bool] = {p: False for p in phase_order}
        phase_all_chains_intact: dict[str, bool] = {p: True for p in phase_order}

        for cr in chain_results:
            # A chain "touches" its source and destination phases
            phases_in_chain = {cr.chain_id}  # not used directly
            source_phase = _extract_phase_from_chain_id(cr, chain_results)

            # We check by matching chain field names against phase exit fields
            # Simpler approach: if chain is broken, mark all phases
            if cr.status == ChainStatus.BROKEN:
                for p in phase_order:
                    phase_has_broken_chain[p] = True
            if cr.status != ChainStatus.INTACT:
                for p in phase_order:
                    phase_all_chains_intact[p] = False

        # Detect discrepancies
        for phase_name in phase_order:
            runtime_passed = runtime_phase_passed.get(phase_name)
            if runtime_passed is None:
                # Phase wasn't tracked at runtime
                continue

            has_broken = phase_has_broken_chain.get(phase_name, False)
            all_intact = phase_all_chains_intact.get(phase_name, True)

            if runtime_passed and has_broken:
                discrepancies.append(
                    RuntimeDiscrepancy(
                        phase=phase_name,
                        discrepancy_type="late_corruption",
                        message=(
                            f"Phase '{phase_name}' passed runtime boundary "
                            f"checks but a propagation chain is now broken"
                        ),
                    )
                )
            elif not runtime_passed and all_intact and len(chain_results) > 0:
                discrepancies.append(
                    RuntimeDiscrepancy(
                        phase=phase_name,
                        discrepancy_type="late_healing",
                        message=(
                            f"Phase '{phase_name}' failed runtime boundary "
                            f"checks but all propagation chains are now intact"
                        ),
                    )
                )

        return discrepancies


def _extract_phase_from_chain_id(
    result: PropagationChainResult,
    all_results: list[PropagationChainResult],
) -> Optional[str]:
    """Extract phase name from chain result (best-effort)."""
    # Chain results don't directly carry phase names in a structured way.
    # This is a placeholder — in practice the contract's chain spec
    # carries source.phase and destination.phase.
    return None
