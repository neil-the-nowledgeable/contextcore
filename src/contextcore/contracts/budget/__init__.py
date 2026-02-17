"""
SLO budget propagation contracts -- Layer 6 of defense-in-depth.

Provides a contract system for declaring, tracking, and validating per-phase
budget allocations for latency, cost, token, and error-rate budgets.
Prevents silent overflow of resource budgets across pipeline phases.

Public API::

    from contextcore.contracts.budget import (
        # Schema models
        BudgetPropagationSpec,
        BudgetSpec,
        PhaseAllocation,
        # Loader
        BudgetLoader,
        # Tracker
        BudgetTracker,
        BudgetConsumption,
        BUDGET_KEY,
        # Validator
        BudgetValidator,
        BudgetCheckResult,
        BudgetSummaryResult,
        # OTel helpers
        emit_budget_check,
        emit_budget_summary,
    )
"""

from contextcore.contracts.budget.loader import BudgetLoader
from contextcore.contracts.budget.otel import (
    emit_budget_check,
    emit_budget_summary,
)
from contextcore.contracts.budget.schema import (
    BudgetPropagationSpec,
    BudgetSpec,
    PhaseAllocation,
)
from contextcore.contracts.budget.tracker import (
    BUDGET_KEY,
    BudgetConsumption,
    BudgetTracker,
)
from contextcore.contracts.budget.validator import (
    BudgetCheckResult,
    BudgetSummaryResult,
    BudgetValidator,
)

__all__ = [
    # Schema
    "BudgetPropagationSpec",
    "BudgetSpec",
    "PhaseAllocation",
    # Loader
    "BudgetLoader",
    # Tracker
    "BudgetTracker",
    "BudgetConsumption",
    "BUDGET_KEY",
    # Validator
    "BudgetValidator",
    "BudgetCheckResult",
    "BudgetSummaryResult",
    # OTel
    "emit_budget_check",
    "emit_budget_summary",
]
