"""
Propagation health scorer — Layer 6.

Computes a single 0-100 health score from Layer 3-5 results, providing
a unified signal for dashboards and alerting.  The score is a weighted
combination of:

- **Completeness** (40%) — propagation chain completeness from Layer 5.
- **Boundary health** (30%) — runtime boundary pass rate from Layer 4.
- **Preflight** (20%) — pre-flight pass/fail from Layer 3.
- **Discrepancy penalty** (10%) — deduction for runtime discrepancies.

Usage::

    from contextcore.contracts.observability import HealthScorer

    scorer = HealthScorer()
    score = scorer.score(
        preflight_result=preflight,
        runtime_summary=summary,
        postexec_report=report,
    )
    print(f"Propagation health: {score.overall}/100")
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.postexec.validator import PostExecutionReport
from contextcore.contracts.preflight.checker import PreflightResult
from contextcore.contracts.runtime.guard import WorkflowRunSummary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class HealthScore(BaseModel):
    """Propagation health score breakdown."""

    model_config = ConfigDict(extra="forbid")

    overall: float = Field(
        ..., ge=0.0, le=100.0, description="Combined score 0-100"
    )
    completeness_score: float = Field(
        default=100.0, ge=0.0, le=100.0,
        description="Chain completeness contribution (0-100)",
    )
    boundary_score: float = Field(
        default=100.0, ge=0.0, le=100.0,
        description="Runtime boundary health contribution (0-100)",
    )
    preflight_score: float = Field(
        default=100.0, ge=0.0, le=100.0,
        description="Pre-flight pass contribution (0-100)",
    )
    discrepancy_penalty: float = Field(
        default=0.0, ge=0.0, le=100.0,
        description="Deduction for runtime discrepancies (0-100)",
    )


# ---------------------------------------------------------------------------
# Default weights
# ---------------------------------------------------------------------------


DEFAULT_WEIGHTS = {
    "completeness": 0.40,
    "boundary": 0.30,
    "preflight": 0.20,
    "discrepancy": 0.10,
}


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class HealthScorer:
    """Computes a unified propagation health score from Layer 3-5 results."""

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self._weights = weights or dict(DEFAULT_WEIGHTS)

    def score(
        self,
        preflight_result: Optional[PreflightResult] = None,
        runtime_summary: Optional[WorkflowRunSummary] = None,
        postexec_report: Optional[PostExecutionReport] = None,
    ) -> HealthScore:
        """Compute the propagation health score.

        Any combination of results can be provided.  Missing results
        default to a perfect score (100) for their component, so the
        scorer degrades gracefully.

        Args:
            preflight_result: Layer 3 pre-flight result.
            runtime_summary: Layer 4 workflow run summary.
            postexec_report: Layer 5 post-execution report.

        Returns:
            ``HealthScore`` with per-component and overall scores.
        """
        completeness = self._score_completeness(postexec_report)
        boundary = self._score_boundary(runtime_summary)
        preflight = self._score_preflight(preflight_result)
        discrepancy = self._score_discrepancy(postexec_report)

        w = self._weights
        overall = (
            completeness * w.get("completeness", 0.4)
            + boundary * w.get("boundary", 0.3)
            + preflight * w.get("preflight", 0.2)
            + (100.0 - discrepancy) * w.get("discrepancy", 0.1)
        )
        overall = round(max(0.0, min(100.0, overall)), 1)

        result = HealthScore(
            overall=overall,
            completeness_score=completeness,
            boundary_score=boundary,
            preflight_score=preflight,
            discrepancy_penalty=discrepancy,
        )

        logger.info(
            "Propagation health: %.1f/100 "
            "(completeness=%.1f, boundary=%.1f, preflight=%.1f, "
            "discrepancy_penalty=%.1f)",
            result.overall,
            completeness,
            boundary,
            preflight,
            discrepancy,
        )
        return result

    @staticmethod
    def _score_completeness(
        report: Optional[PostExecutionReport],
    ) -> float:
        """Score from chain completeness (0-100)."""
        if report is None:
            return 100.0
        return report.completeness_pct

    @staticmethod
    def _score_boundary(
        summary: Optional[WorkflowRunSummary],
    ) -> float:
        """Score from runtime boundary pass rate (0-100)."""
        if summary is None:
            return 100.0
        if summary.total_phases == 0:
            return 100.0
        return round(
            summary.passed_phases / summary.total_phases * 100, 1
        )

    @staticmethod
    def _score_preflight(
        result: Optional[PreflightResult],
    ) -> float:
        """Score from pre-flight result (0 or 100)."""
        if result is None:
            return 100.0
        return 100.0 if result.passed else 0.0

    @staticmethod
    def _score_discrepancy(
        report: Optional[PostExecutionReport],
    ) -> float:
        """Penalty from runtime discrepancies (0-100).

        Each discrepancy deducts 25 points, capped at 100.
        """
        if report is None:
            return 0.0
        count = len(report.runtime_discrepancies)
        return min(count * 25.0, 100.0)
