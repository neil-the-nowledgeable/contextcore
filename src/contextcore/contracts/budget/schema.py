"""
Pydantic v2 models for SLO budget propagation contract format.

Contracts declare per-phase budget allocations for latency, cost, token, and
error-rate budgets.  The :class:`BudgetPropagationSpec` is the top-level model
loaded from YAML (or constructed programmatically) and consumed by
:class:`~contextcore.contracts.budget.tracker.BudgetTracker` and
:class:`~contextcore.contracts.budget.validator.BudgetValidator`.

All models use ``extra="forbid"`` to reject unknown keys at parse time,
following the same pattern as ``contracts/propagation/schema.py``.

Usage::

    from contextcore.contracts.budget.schema import BudgetPropagationSpec
    import yaml

    with open("pipeline-budget.contract.yaml") as fh:
        raw = yaml.safe_load(fh)
    spec = BudgetPropagationSpec.model_validate(raw)
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contextcore.contracts.types import BudgetType, OverflowPolicy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase-level allocation
# ---------------------------------------------------------------------------


class PhaseAllocation(BaseModel):
    """Budget amount allocated to a single pipeline phase."""

    model_config = ConfigDict(extra="forbid")

    phase: str = Field(..., min_length=1, description="Phase name (e.g. 'design', 'implement')")
    amount: float = Field(..., ge=0, description="Budget amount allocated to this phase")
    description: Optional[str] = Field(None, description="Human-readable note about the allocation")


# ---------------------------------------------------------------------------
# Individual budget specification
# ---------------------------------------------------------------------------


class BudgetSpec(BaseModel):
    """Specification for a single budget (latency, cost, tokens, etc.)."""

    model_config = ConfigDict(extra="forbid")

    budget_id: str = Field(..., min_length=1, description="Unique budget identifier")
    budget_type: BudgetType = Field(..., description="Type of budget metric")
    total: float = Field(..., ge=0, description="Total budget amount")
    allocations: list[PhaseAllocation] = Field(
        default_factory=list,
        description="Per-phase budget allocations",
    )
    overflow_policy: OverflowPolicy = Field(
        OverflowPolicy.WARN,
        description="Policy when a phase exceeds its allocation",
    )
    description: Optional[str] = Field(None, description="Human-readable description of this budget")

    @model_validator(mode="after")
    def _check_allocation_sum(self) -> "BudgetSpec":
        """Warn if the sum of phase allocations exceeds the total budget.

        Over-allocation is allowed (especially with REDISTRIBUTE policy) but
        is worth flagging so operators are aware.
        """
        alloc_sum = sum(a.amount for a in self.allocations)
        if alloc_sum > self.total:
            logger.warning(
                "Budget '%s': allocation sum (%.2f) exceeds total (%.2f) — "
                "overflow_policy=%s",
                self.budget_id,
                alloc_sum,
                self.total,
                self.overflow_policy.value,
            )
        return self


# ---------------------------------------------------------------------------
# Top-level contract
# ---------------------------------------------------------------------------


class BudgetPropagationSpec(BaseModel):
    """
    Root model for a budget propagation contract YAML file.

    Declares per-phase budget allocations and overflow policies for a
    workflow pipeline.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        ..., min_length=1, description="Contract schema version (e.g. 0.1.0)"
    )
    contract_type: Literal["budget_propagation"] = Field(
        ..., description="Must be 'budget_propagation'"
    )
    pipeline_id: str = Field(
        ..., min_length=1, description="Pipeline this contract governs"
    )
    budgets: list[BudgetSpec] = Field(
        default_factory=list,
        description="Budget specifications for this pipeline",
    )
    description: Optional[str] = Field(None, description="Human-readable description")
