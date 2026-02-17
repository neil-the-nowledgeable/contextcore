"""
Budget boundary validator for SLO budget propagation contracts.

Validates that budget consumption recorded in a workflow context dict does not
exceed the allocations declared in a :class:`BudgetPropagationSpec`.

Maps :class:`~contextcore.contracts.types.BudgetHealth` to
:class:`~contextcore.contracts.types.ChainStatus`:

- ``WITHIN_BUDGET``     -> ``INTACT``
- ``OVER_ALLOCATION``   -> ``DEGRADED``
- ``BUDGET_EXHAUSTED``  -> ``BROKEN``

Usage::

    from contextcore.contracts.budget.validator import BudgetValidator
    from contextcore.contracts.budget.schema import BudgetPropagationSpec

    validator = BudgetValidator(contract)
    result = validator.check_phase("design", context)
    if not result.passed:
        raise BudgetExhaustedError(...)
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.budget.schema import BudgetPropagationSpec, BudgetSpec
from contextcore.contracts.budget.tracker import BudgetTracker
from contextcore.contracts.types import BudgetHealth, ChainStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Health → ChainStatus mapping
# ---------------------------------------------------------------------------

_HEALTH_TO_CHAIN: dict[BudgetHealth, ChainStatus] = {
    BudgetHealth.WITHIN_BUDGET: ChainStatus.INTACT,
    BudgetHealth.OVER_ALLOCATION: ChainStatus.DEGRADED,
    BudgetHealth.BUDGET_EXHAUSTED: ChainStatus.BROKEN,
}


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class BudgetCheckResult(BaseModel):
    """Result of checking a single budget for a phase."""

    model_config = ConfigDict(extra="forbid")

    budget_id: str = Field(..., description="Budget identifier")
    phase: str = Field(..., description="Phase that was checked")
    health: BudgetHealth = Field(..., description="Health status")
    allocated: float = Field(..., description="Amount allocated for this phase")
    consumed: float = Field(..., description="Amount consumed by this phase")
    remaining: float = Field(..., description="Remaining phase allocation")
    message: str = Field("", description="Human-readable diagnostic")

    @property
    def chain_status(self) -> ChainStatus:
        """Map BudgetHealth to ChainStatus for interop with L1 tooling."""
        return _HEALTH_TO_CHAIN[self.health]


class BudgetSummaryResult(BaseModel):
    """Aggregated result of checking budgets across all phases or a single phase."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(..., description="True if no budgets are exhausted")
    total_budgets: int = Field(..., description="Number of budgets checked")
    results: list[BudgetCheckResult] = Field(
        default_factory=list,
        description="Per-budget check results",
    )
    exhausted_count: int = Field(0, description="Number of exhausted budgets")
    over_allocated_count: int = Field(0, description="Number of over-allocated budgets")


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _find_phase_allocation(budget: BudgetSpec, phase: str) -> float:
    """Find the allocated amount for a phase, or 0.0 if not declared."""
    for alloc in budget.allocations:
        if alloc.phase == phase:
            return alloc.amount
    return 0.0


def _assess_health(
    allocated: float,
    consumed: float,
    total: float,
    total_consumed: float,
) -> BudgetHealth:
    """Determine budget health for a phase.

    - BUDGET_EXHAUSTED:  total consumed >= total budget (nothing left at all)
    - OVER_ALLOCATION:   phase consumed > phase allocation (but total budget not exhausted)
    - WITHIN_BUDGET:     phase consumed <= phase allocation
    """
    if total_consumed >= total:
        return BudgetHealth.BUDGET_EXHAUSTED
    if consumed > allocated and allocated > 0:
        return BudgetHealth.OVER_ALLOCATION
    return BudgetHealth.WITHIN_BUDGET


class BudgetValidator:
    """Validates budget consumption against a budget propagation contract.

    Args:
        contract: The budget propagation spec to validate against.
    """

    def __init__(self, contract: BudgetPropagationSpec) -> None:
        self._contract = contract
        self._tracker = BudgetTracker()

    def check_phase(
        self,
        phase: str,
        context: dict[str, Any],
    ) -> BudgetSummaryResult:
        """Check all budgets for a specific phase.

        Args:
            phase: Phase name to check.
            context: Shared workflow context dict with consumption records.

        Returns:
            Summary result with per-budget health for the given phase.
        """
        results: list[BudgetCheckResult] = []

        for budget in self._contract.budgets:
            allocated = _find_phase_allocation(budget, phase)
            consumed = self._tracker.get_phase_consumed(context, budget.budget_id, phase)
            total_consumed = self._tracker.get_consumed(context, budget.budget_id)
            remaining = allocated - consumed

            health = _assess_health(allocated, consumed, budget.total, total_consumed)

            message = self._build_message(budget.budget_id, phase, health, allocated, consumed, remaining)

            results.append(
                BudgetCheckResult(
                    budget_id=budget.budget_id,
                    phase=phase,
                    health=health,
                    allocated=allocated,
                    consumed=consumed,
                    remaining=remaining,
                    message=message,
                )
            )

            if health != BudgetHealth.WITHIN_BUDGET:
                logger.warning(
                    "Budget check: %s phase=%s health=%s consumed=%.2f/%.2f",
                    budget.budget_id,
                    phase,
                    health.value,
                    consumed,
                    allocated,
                )

        return self._summarise(results)

    def check_all(
        self,
        context: dict[str, Any],
    ) -> BudgetSummaryResult:
        """Check all budgets across all phases (end-of-run summary).

        Examines total consumption vs. total budget for each budget spec,
        then also checks each individual phase allocation.

        Args:
            context: Shared workflow context dict with consumption records.

        Returns:
            Summary result with per-budget health across all phases.
        """
        results: list[BudgetCheckResult] = []

        for budget in self._contract.budgets:
            total_consumed = self._tracker.get_consumed(context, budget.budget_id)

            # Check each declared phase allocation
            phases_checked: set[str] = set()
            for alloc in budget.allocations:
                phase = alloc.phase
                phases_checked.add(phase)
                phase_consumed = self._tracker.get_phase_consumed(
                    context, budget.budget_id, phase
                )
                remaining = alloc.amount - phase_consumed
                health = _assess_health(
                    alloc.amount, phase_consumed, budget.total, total_consumed
                )
                message = self._build_message(
                    budget.budget_id, phase, health, alloc.amount, phase_consumed, remaining
                )
                results.append(
                    BudgetCheckResult(
                        budget_id=budget.budget_id,
                        phase=phase,
                        health=health,
                        allocated=alloc.amount,
                        consumed=phase_consumed,
                        remaining=remaining,
                        message=message,
                    )
                )

            # Also emit a top-level total check (phase = "__total__")
            total_remaining = budget.total - total_consumed
            if total_consumed >= budget.total:
                total_health = BudgetHealth.BUDGET_EXHAUSTED
            elif total_consumed > budget.total * 0.9:
                total_health = BudgetHealth.OVER_ALLOCATION
            else:
                total_health = BudgetHealth.WITHIN_BUDGET

            total_message = self._build_message(
                budget.budget_id, "__total__", total_health,
                budget.total, total_consumed, total_remaining,
            )
            results.append(
                BudgetCheckResult(
                    budget_id=budget.budget_id,
                    phase="__total__",
                    health=total_health,
                    allocated=budget.total,
                    consumed=total_consumed,
                    remaining=total_remaining,
                    message=total_message,
                )
            )

        return self._summarise(results)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_message(
        budget_id: str,
        phase: str,
        health: BudgetHealth,
        allocated: float,
        consumed: float,
        remaining: float,
    ) -> str:
        if health == BudgetHealth.WITHIN_BUDGET:
            return (
                f"Budget '{budget_id}' phase '{phase}': within budget "
                f"(consumed {consumed:.2f} / allocated {allocated:.2f}, "
                f"remaining {remaining:.2f})"
            )
        elif health == BudgetHealth.OVER_ALLOCATION:
            return (
                f"Budget '{budget_id}' phase '{phase}': over-allocated "
                f"(consumed {consumed:.2f} / allocated {allocated:.2f}, "
                f"over by {abs(remaining):.2f})"
            )
        else:
            return (
                f"Budget '{budget_id}' phase '{phase}': EXHAUSTED "
                f"(consumed {consumed:.2f} / allocated {allocated:.2f})"
            )

    @staticmethod
    def _summarise(results: list[BudgetCheckResult]) -> BudgetSummaryResult:
        exhausted = sum(1 for r in results if r.health == BudgetHealth.BUDGET_EXHAUSTED)
        over_alloc = sum(1 for r in results if r.health == BudgetHealth.OVER_ALLOCATION)
        passed = exhausted == 0
        return BudgetSummaryResult(
            passed=passed,
            total_budgets=len(results),
            results=results,
            exhausted_count=exhausted,
            over_allocated_count=over_alloc,
        )
