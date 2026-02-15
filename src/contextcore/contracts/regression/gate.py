"""
Regression gate for CI/CD pipelines — Layer 7.

Compares current propagation health against a stored baseline and
produces a pass/fail gate result.  Designed to run in CI on every PR
to prevent propagation regressions from merging.

Checks:

- **Completeness** — propagation chain completeness must not decrease.
- **Health score** — unified health score must stay above threshold.
- **Breaking drift** — no breaking contract changes allowed (unless overridden).
- **Blocking failures** — runtime blocking failure count must not increase.

Usage::

    from contextcore.contracts.regression import RegressionGate

    gate = RegressionGate()
    result = gate.check(
        baseline_report=old_report,
        current_report=new_report,
        drift_report=drift,
        baseline_health=old_health,
        current_health=new_health,
    )
    if not result.passed:
        for f in result.failures:
            print(f"GATE FAIL: {f}")
        sys.exit(1)
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.observability.health import HealthScore
from contextcore.contracts.postexec.validator import PostExecutionReport
from contextcore.contracts.regression.drift import DriftReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class GateCheck(BaseModel):
    """Result of a single gate check."""

    model_config = ConfigDict(extra="forbid")

    check_id: str = Field(..., min_length=1)
    passed: bool = True
    message: str = ""
    baseline_value: Optional[float] = None
    current_value: Optional[float] = None


class GateResult(BaseModel):
    """Aggregated regression gate result."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = True
    checks: list[GateCheck] = Field(default_factory=list)
    total_checks: int = 0
    failed_checks: int = 0

    @property
    def failures(self) -> list[GateCheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def passed_checks_list(self) -> list[GateCheck]:
        return [c for c in self.checks if c.passed]


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------


DEFAULT_THRESHOLDS = {
    "min_health_score": 70.0,
    "max_completeness_drop": 5.0,
    "max_blocking_failure_increase": 0,
}


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


class RegressionGate:
    """CI/CD regression gate that prevents propagation quality degradation."""

    def __init__(
        self,
        thresholds: Optional[dict[str, float]] = None,
        allow_breaking_drift: bool = False,
    ) -> None:
        """Initialise the regression gate.

        Args:
            thresholds: Override default thresholds.  Keys match
                ``DEFAULT_THRESHOLDS``.
            allow_breaking_drift: When ``True``, breaking contract drift
                is reported but does not fail the gate.
        """
        self._thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._allow_breaking_drift = allow_breaking_drift

    def check(
        self,
        baseline_report: Optional[PostExecutionReport] = None,
        current_report: Optional[PostExecutionReport] = None,
        drift_report: Optional[DriftReport] = None,
        baseline_health: Optional[HealthScore] = None,
        current_health: Optional[HealthScore] = None,
    ) -> GateResult:
        """Run all gate checks and produce an aggregated result.

        Any combination of inputs can be provided.  Checks that cannot
        be evaluated from the given inputs are skipped.

        Args:
            baseline_report: Layer 5 report from the baseline (e.g. main branch).
            current_report: Layer 5 report from the current PR.
            drift_report: Layer 7 contract drift report.
            baseline_health: Layer 6 health score from baseline.
            current_health: Layer 6 health score from current PR.

        Returns:
            ``GateResult`` with all checks.
        """
        checks: list[GateCheck] = []

        checks.extend(self._check_completeness(baseline_report, current_report))
        checks.extend(self._check_health(baseline_health, current_health))
        checks.extend(self._check_drift(drift_report))
        checks.extend(
            self._check_blocking_failures(baseline_report, current_report)
        )

        failed = sum(1 for c in checks if not c.passed)
        passed = failed == 0

        if not passed:
            logger.warning(
                "Regression gate FAILED: %d/%d checks failed",
                failed,
                len(checks),
            )
        else:
            logger.info(
                "Regression gate passed: %d checks OK",
                len(checks),
            )

        return GateResult(
            passed=passed,
            checks=checks,
            total_checks=len(checks),
            failed_checks=failed,
        )

    # -- internal: completeness ------------------------------------------------

    def _check_completeness(
        self,
        baseline: Optional[PostExecutionReport],
        current: Optional[PostExecutionReport],
    ) -> list[GateCheck]:
        if baseline is None or current is None:
            return []

        max_drop = self._thresholds.get("max_completeness_drop", 5.0)
        drop = baseline.completeness_pct - current.completeness_pct
        passed = drop <= max_drop

        return [
            GateCheck(
                check_id="completeness_regression",
                passed=passed,
                message=(
                    f"Completeness dropped by {drop:.1f}% "
                    f"(baseline={baseline.completeness_pct:.1f}%, "
                    f"current={current.completeness_pct:.1f}%, "
                    f"max_allowed={max_drop:.1f}%)"
                    if not passed
                    else (
                        f"Completeness OK: {current.completeness_pct:.1f}% "
                        f"(baseline={baseline.completeness_pct:.1f}%)"
                    )
                ),
                baseline_value=baseline.completeness_pct,
                current_value=current.completeness_pct,
            )
        ]

    # -- internal: health score ------------------------------------------------

    def _check_health(
        self,
        baseline: Optional[HealthScore],
        current: Optional[HealthScore],
    ) -> list[GateCheck]:
        checks: list[GateCheck] = []

        min_score = self._thresholds.get("min_health_score", 70.0)

        if current is not None:
            passed = current.overall >= min_score
            checks.append(
                GateCheck(
                    check_id="health_minimum",
                    passed=passed,
                    message=(
                        f"Health score {current.overall:.1f} below minimum "
                        f"{min_score:.1f}"
                        if not passed
                        else f"Health score OK: {current.overall:.1f} >= {min_score:.1f}"
                    ),
                    current_value=current.overall,
                )
            )

        if baseline is not None and current is not None:
            drop = baseline.overall - current.overall
            passed = drop <= self._thresholds.get("max_completeness_drop", 5.0)
            checks.append(
                GateCheck(
                    check_id="health_regression",
                    passed=passed,
                    message=(
                        f"Health score dropped by {drop:.1f} "
                        f"(baseline={baseline.overall:.1f}, "
                        f"current={current.overall:.1f})"
                        if not passed
                        else (
                            f"Health regression OK: {current.overall:.1f} "
                            f"(baseline={baseline.overall:.1f})"
                        )
                    ),
                    baseline_value=baseline.overall,
                    current_value=current.overall,
                )
            )

        return checks

    # -- internal: drift -------------------------------------------------------

    def _check_drift(
        self,
        drift: Optional[DriftReport],
    ) -> list[GateCheck]:
        if drift is None:
            return []

        if not drift.has_breaking_changes:
            return [
                GateCheck(
                    check_id="contract_drift",
                    passed=True,
                    message=(
                        f"No breaking drift ({drift.total_changes} "
                        f"non-breaking changes)"
                    ),
                )
            ]

        passed = self._allow_breaking_drift
        descriptions = "; ".join(
            c.description for c in drift.breaking_changes[:3]
        )
        suffix = ""
        if drift.breaking_count > 3:
            suffix = f" ... and {drift.breaking_count - 3} more"

        return [
            GateCheck(
                check_id="contract_drift",
                passed=passed,
                message=(
                    f"{drift.breaking_count} breaking contract changes: "
                    f"{descriptions}{suffix}"
                ),
                current_value=float(drift.breaking_count),
            )
        ]

    # -- internal: blocking failures -------------------------------------------

    def _check_blocking_failures(
        self,
        baseline: Optional[PostExecutionReport],
        current: Optional[PostExecutionReport],
    ) -> list[GateCheck]:
        if current is None:
            return []

        current_broken = current.chains_broken
        baseline_broken = baseline.chains_broken if baseline else 0
        max_increase = int(
            self._thresholds.get("max_blocking_failure_increase", 0)
        )
        increase = current_broken - baseline_broken
        passed = increase <= max_increase

        return [
            GateCheck(
                check_id="blocking_failures",
                passed=passed,
                message=(
                    f"Broken chains increased by {increase} "
                    f"(baseline={baseline_broken}, current={current_broken})"
                    if not passed
                    else (
                        f"Broken chains OK: {current_broken} "
                        f"(baseline={baseline_broken})"
                    )
                ),
                baseline_value=float(baseline_broken),
                current_value=float(current_broken),
            )
        ]
