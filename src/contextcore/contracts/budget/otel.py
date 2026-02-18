"""
OTel span event emission helpers for budget propagation.

Follows the ``add_span_event()`` pattern from
``contracts/propagation/otel.py`` -- log + optional OTel span event.
All functions are guarded by ``_HAS_OTEL`` so they degrade gracefully
when OTel is not installed.

Usage::

    from contextcore.contracts.budget.otel import (
        emit_budget_check,
        emit_budget_summary,
    )

    emit_budget_check(check_result)
    emit_budget_summary(summary_result)
"""

from __future__ import annotations

import logging

from contextcore.contracts._otel_helpers import add_span_event
from contextcore.contracts.budget.validator import BudgetCheckResult, BudgetSummaryResult
from contextcore.contracts.types import BudgetHealth

logger = logging.getLogger(__name__)


def emit_budget_check(result: BudgetCheckResult) -> None:
    """Emit a span event for a single budget check result.

    Event name: ``budget.check.{health}``
    (e.g. ``budget.check.within_budget``, ``budget.check.budget_exhausted``).
    """
    event_name = f"budget.check.{result.health.value}"

    attrs: dict[str, str | int | float | bool] = {
        "budget.id": result.budget_id,
        "budget.phase": result.phase,
        "budget.health": result.health.value,
        "budget.allocated": result.allocated,
        "budget.consumed": result.consumed,
        "budget.remaining": result.remaining,
        "budget.message": result.message,
    }

    if result.health == BudgetHealth.WITHIN_BUDGET:
        logger.debug(
            "Budget check: %s phase=%s health=%s",
            result.budget_id,
            result.phase,
            result.health.value,
        )
    else:
        logger.warning(
            "Budget check: %s phase=%s health=%s consumed=%.2f/%.2f",
            result.budget_id,
            result.phase,
            result.health.value,
            result.consumed,
            result.allocated,
        )

    add_span_event(event_name, attrs)


def emit_budget_summary(result: BudgetSummaryResult) -> None:
    """Emit a summary span event for a budget validation pass.

    Event name: ``budget.summary``
    """
    attrs: dict[str, str | int | float | bool] = {
        "budget.total_budgets": result.total_budgets,
        "budget.passed": result.passed,
        "budget.exhausted_count": result.exhausted_count,
        "budget.over_allocated_count": result.over_allocated_count,
    }

    log_fn = logger.info if result.passed else logger.warning
    log_fn(
        "Budget summary: %d budgets, passed=%s, exhausted=%d, over_allocated=%d",
        result.total_budgets,
        result.passed,
        result.exhausted_count,
        result.over_allocated_count,
    )

    add_span_event("budget.summary", attrs)
