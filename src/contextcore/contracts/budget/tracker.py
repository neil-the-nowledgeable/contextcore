"""
Budget consumption tracker.

Tracks budget consumption as context flows through workflow phases.
Consumption records are stored inside the context dict itself (under
``_cc_budgets``) so they travel with the context through the pipeline.

Follows the provenance-in-context pattern from
``contracts/propagation/tracker.py``.

Usage::

    from contextcore.contracts.budget.tracker import BudgetTracker
    from contextcore.contracts.budget.schema import BudgetPropagationSpec

    tracker = BudgetTracker()
    tracker.record(context, "latency_budget", "design", 1200.0)

    remaining = tracker.get_remaining(contract, context, "latency_budget")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from contextcore.contracts.budget.schema import BudgetPropagationSpec, BudgetSpec

logger = logging.getLogger(__name__)

# Key under which budget consumption metadata is stored in the context dict.
BUDGET_KEY = "_cc_budgets"


@dataclass
class BudgetConsumption:
    """A single consumption record for a budget at a given phase."""

    budget_id: str
    phase: str
    consumed: float
    timestamp: str  # ISO 8601

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_id": self.budget_id,
            "phase": self.phase,
            "consumed": self.consumed,
            "timestamp": self.timestamp,
        }


def _get_records(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the list of consumption records from the context, creating if absent."""
    return context.setdefault(BUDGET_KEY, [])


def _find_budget(contract: BudgetPropagationSpec, budget_id: str) -> Optional[BudgetSpec]:
    """Find a BudgetSpec by id, or None."""
    for b in contract.budgets:
        if b.budget_id == budget_id:
            return b
    return None


class BudgetTracker:
    """Tracks budget consumption across workflow phases."""

    def record(
        self,
        context: dict[str, Any],
        budget_id: str,
        phase: str,
        consumed: float,
    ) -> BudgetConsumption:
        """Record budget consumption for a phase.

        Args:
            context: The shared mutable workflow context dict.
            budget_id: Identifier of the budget being consumed.
            phase: Phase that consumed budget.
            consumed: Amount consumed.

        Returns:
            The ``BudgetConsumption`` record that was stored.
        """
        records = _get_records(context)
        entry = BudgetConsumption(
            budget_id=budget_id,
            phase=phase,
            consumed=consumed,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        records.append(entry.to_dict())
        logger.debug(
            "Recorded consumption: budget=%s phase=%s consumed=%.2f",
            budget_id,
            phase,
            consumed,
        )
        return entry

    def get_consumed(
        self,
        context: dict[str, Any],
        budget_id: str,
    ) -> float:
        """Return total consumed across all phases for a budget.

        Args:
            context: The shared workflow context dict.
            budget_id: Budget identifier.

        Returns:
            Total consumed amount.
        """
        records = context.get(BUDGET_KEY, [])
        return sum(
            r["consumed"] for r in records if r["budget_id"] == budget_id
        )

    def get_remaining(
        self,
        contract: BudgetPropagationSpec,
        context: dict[str, Any],
        budget_id: str,
    ) -> float:
        """Return remaining budget (total - consumed).

        Args:
            contract: The budget contract spec.
            context: The shared workflow context dict.
            budget_id: Budget identifier.

        Returns:
            Remaining budget.  May be negative if over-consumed.
        """
        budget = _find_budget(contract, budget_id)
        if budget is None:
            logger.warning("Budget '%s' not found in contract", budget_id)
            return 0.0
        consumed = self.get_consumed(context, budget_id)
        return budget.total - consumed

    def get_phase_consumed(
        self,
        context: dict[str, Any],
        budget_id: str,
        phase: str,
    ) -> float:
        """Return consumed amount for a specific budget and phase.

        Args:
            context: The shared workflow context dict.
            budget_id: Budget identifier.
            phase: Phase name.

        Returns:
            Amount consumed by this phase for this budget.
        """
        records = context.get(BUDGET_KEY, [])
        return sum(
            r["consumed"]
            for r in records
            if r["budget_id"] == budget_id and r["phase"] == phase
        )

    def query_budget(
        self,
        contract: BudgetPropagationSpec,
        context: dict[str, Any],
        budget_id: str,
        phase: str,
    ) -> float:
        """Return remaining allocation for a specific phase.

        Computes: phase allocation - phase consumed.  If no allocation is
        declared for the phase, returns 0.0.

        Args:
            contract: The budget contract spec.
            context: The shared workflow context dict.
            budget_id: Budget identifier.
            phase: Phase name.

        Returns:
            Remaining phase allocation.  May be negative if over-consumed.
        """
        budget = _find_budget(contract, budget_id)
        if budget is None:
            logger.warning("Budget '%s' not found in contract", budget_id)
            return 0.0

        # Find the phase allocation
        phase_alloc = 0.0
        for alloc in budget.allocations:
            if alloc.phase == phase:
                phase_alloc = alloc.amount
                break

        phase_consumed = self.get_phase_consumed(context, budget_id, phase)
        return phase_alloc - phase_consumed
