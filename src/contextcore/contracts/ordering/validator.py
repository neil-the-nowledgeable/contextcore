"""
Causal ordering validator for pipeline event logs.

Validates that a sequence of ``CausalProvenance`` events satisfies the
happens-before dependencies declared in an ``OrderingConstraintSpec``.
Uses logical timestamps to detect ordering violations.

Follows the ``BoundaryValidator`` + structured result pattern from
``contracts/propagation/validator.py``.

Usage::

    from contextcore.contracts.ordering.validator import CausalValidator
    from contextcore.contracts.ordering.schema import OrderingConstraintSpec

    spec = OrderingConstraintSpec.model_validate(raw)
    validator = CausalValidator(spec)
    result = validator.validate(event_log)
    if not result.passed:
        for v in result.results:
            if not v.satisfied:
                print(v.message)
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.ordering.clock import CausalProvenance
from contextcore.contracts.ordering.schema import (
    CausalDependency,
    OrderingConstraintSpec,
)
from contextcore.contracts.types import ConstraintSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class OrderingCheckResult(BaseModel):
    """Result of checking a single causal dependency."""

    model_config = ConfigDict(extra="forbid")

    dependency: CausalDependency = Field(
        ..., description="The dependency that was checked"
    )
    satisfied: bool = Field(
        ..., description="Whether the ordering constraint was satisfied"
    )
    before_ts: Optional[int] = Field(
        None, description="Logical timestamp of the 'before' event (None if missing)"
    )
    after_ts: Optional[int] = Field(
        None, description="Logical timestamp of the 'after' event (None if missing)"
    )
    message: str = Field(
        "", description="Human-readable explanation of the check result"
    )


class OrderingValidationResult(BaseModel):
    """Aggregated result of validating all causal dependencies."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(
        ..., description="True if no BLOCKING violations were found"
    )
    total_checked: int = Field(
        ..., description="Total number of dependencies checked"
    )
    results: list[OrderingCheckResult] = Field(
        default_factory=list,
        description="Per-dependency check results",
    )
    violations: int = Field(
        0, description="Number of dependencies that were not satisfied"
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class CausalValidator:
    """Validates causal ordering of pipeline events against a contract.

    Builds an index of ``(phase, event) -> logical_ts`` from the event
    log, then checks each declared dependency to ensure the 'before'
    event has a strictly lower timestamp than the 'after' event.

    Args:
        contract: The ordering constraint spec to validate against.
    """

    def __init__(self, contract: OrderingConstraintSpec) -> None:
        self._contract = contract

    def validate(self, event_log: list[CausalProvenance]) -> OrderingValidationResult:
        """Validate an event log against all declared dependencies.

        Args:
            event_log: Ordered list of causal provenance records from
                a pipeline execution.

        Returns:
            ``OrderingValidationResult`` with per-dependency details.
        """
        # Build index: (phase, event) -> logical_ts
        # If duplicate keys exist, keep the first occurrence.
        ts_index: dict[tuple[str, str], int] = {}
        for prov in event_log:
            key = (prov.phase, prov.event)
            if key not in ts_index:
                ts_index[key] = prov.logical_ts

        results: list[OrderingCheckResult] = []
        violations = 0
        has_blocking_violation = False

        for dep in self._contract.dependencies:
            check = self._check_dependency(dep, ts_index)
            results.append(check)

            if not check.satisfied:
                violations += 1
                if dep.severity == ConstraintSeverity.BLOCKING:
                    has_blocking_violation = True
                    logger.warning(
                        "Blocking ordering violation: %s (before_ts=%s, after_ts=%s)",
                        check.message,
                        check.before_ts,
                        check.after_ts,
                    )
                elif dep.severity == ConstraintSeverity.WARNING:
                    logger.warning(
                        "Ordering warning: %s (before_ts=%s, after_ts=%s)",
                        check.message,
                        check.before_ts,
                        check.after_ts,
                    )
                else:
                    logger.info(
                        "Ordering advisory: %s (before_ts=%s, after_ts=%s)",
                        check.message,
                        check.before_ts,
                        check.after_ts,
                    )

        passed = not has_blocking_violation

        if passed and violations > 0:
            logger.info(
                "Ordering validation passed with %d non-blocking violation(s)",
                violations,
            )
        elif passed:
            logger.debug(
                "Ordering validation passed: %d/%d dependencies satisfied",
                len(results),
                len(results),
            )

        return OrderingValidationResult(
            passed=passed,
            total_checked=len(results),
            results=results,
            violations=violations,
        )

    def _check_dependency(
        self,
        dep: CausalDependency,
        ts_index: dict[tuple[str, str], int],
    ) -> OrderingCheckResult:
        """Check a single dependency against the timestamp index."""
        before_key = (dep.before.phase, dep.before.event)
        after_key = (dep.after.phase, dep.after.event)

        before_ts = ts_index.get(before_key)
        after_ts = ts_index.get(after_key)

        # Missing 'before' event
        if before_ts is None:
            desc = dep.description or ""
            msg = (
                f"'before' event ({dep.before.phase}.{dep.before.event}) "
                f"not found in event log"
            )
            if desc:
                msg = f"{msg} — {desc}"
            return OrderingCheckResult(
                dependency=dep,
                satisfied=False,
                before_ts=None,
                after_ts=after_ts,
                message=msg,
            )

        # Missing 'after' event
        if after_ts is None:
            desc = dep.description or ""
            msg = (
                f"'after' event ({dep.after.phase}.{dep.after.event}) "
                f"not found in event log"
            )
            if desc:
                msg = f"{msg} — {desc}"
            return OrderingCheckResult(
                dependency=dep,
                satisfied=False,
                before_ts=before_ts,
                after_ts=None,
                message=msg,
            )

        # Check ordering: before must be strictly less than after
        if before_ts < after_ts:
            return OrderingCheckResult(
                dependency=dep,
                satisfied=True,
                before_ts=before_ts,
                after_ts=after_ts,
                message=(
                    f"Ordering satisfied: {dep.before.phase}.{dep.before.event} "
                    f"(ts={before_ts}) < {dep.after.phase}.{dep.after.event} "
                    f"(ts={after_ts})"
                ),
            )

        # Violation: before_ts >= after_ts
        desc = dep.description or ""
        msg = (
            f"Ordering violated: {dep.before.phase}.{dep.before.event} "
            f"(ts={before_ts}) should precede {dep.after.phase}.{dep.after.event} "
            f"(ts={after_ts})"
        )
        if desc:
            msg = f"{msg} — {desc}"

        return OrderingCheckResult(
            dependency=dep,
            satisfied=False,
            before_ts=before_ts,
            after_ts=after_ts,
            message=msg,
        )
