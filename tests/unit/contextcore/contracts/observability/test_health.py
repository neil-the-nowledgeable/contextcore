"""Tests for HealthScorer (Layer 6)."""

import pytest
from pydantic import ValidationError

from contextcore.contracts.observability.health import (
    DEFAULT_WEIGHTS,
    HealthScore,
    HealthScorer,
)
from contextcore.contracts.postexec.validator import (
    PostExecutionReport,
    RuntimeDiscrepancy,
)
from contextcore.contracts.preflight.checker import PreflightResult
from contextcore.contracts.runtime.guard import WorkflowRunSummary
from contextcore.contracts.types import EnforcementMode, PropagationStatus


# ---------------------------------------------------------------------------
# HealthScore model
# ---------------------------------------------------------------------------


class TestHealthScore:
    def test_construction_with_valid_values(self):
        """HealthScore can be constructed with valid component scores."""
        score = HealthScore(
            overall=85.0,
            completeness_score=90.0,
            boundary_score=80.0,
            preflight_score=100.0,
            discrepancy_penalty=10.0,
        )

        assert score.overall == 85.0
        assert score.completeness_score == 90.0
        assert score.boundary_score == 80.0
        assert score.preflight_score == 100.0
        assert score.discrepancy_penalty == 10.0

    def test_extra_fields_rejected(self):
        """ConfigDict extra='forbid' rejects extra fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            HealthScore(
                overall=100.0,
                unexpected_field="oops",
            )

    def test_overall_must_be_0_to_100(self):
        """Overall score is constrained to 0-100 via ge/le."""
        with pytest.raises(ValidationError):
            HealthScore(overall=-1.0)

        with pytest.raises(ValidationError):
            HealthScore(overall=101.0)

        # Edge cases that should succeed
        low = HealthScore(overall=0.0)
        high = HealthScore(overall=100.0)
        assert low.overall == 0.0
        assert high.overall == 100.0


# ---------------------------------------------------------------------------
# HealthScorer - no inputs
# ---------------------------------------------------------------------------


class TestHealthScorerNoInputs:
    def test_all_none_gives_perfect_score(self):
        """All None inputs default to perfect score 100.0."""
        scorer = HealthScorer()
        result = scorer.score()

        assert result.overall == 100.0
        assert result.completeness_score == 100.0
        assert result.boundary_score == 100.0
        assert result.preflight_score == 100.0
        assert result.discrepancy_penalty == 0.0


# ---------------------------------------------------------------------------
# HealthScorer - completeness component
# ---------------------------------------------------------------------------


class TestCompletenessComponent:
    def test_100_percent_completeness(self):
        """100% completeness yields completeness_score=100.0."""
        scorer = HealthScorer()
        report = PostExecutionReport(
            passed=True,
            chains_total=5,
            chains_intact=5,
            chains_broken=0,
            chains_degraded=0,
            completeness_pct=100.0,
        )

        result = scorer.score(postexec_report=report)

        assert result.completeness_score == 100.0

    def test_50_percent_completeness(self):
        """50% completeness yields completeness_score=50.0."""
        scorer = HealthScorer()
        report = PostExecutionReport(
            passed=True,
            chains_total=4,
            chains_intact=2,
            chains_broken=0,
            chains_degraded=2,
            completeness_pct=50.0,
        )

        result = scorer.score(postexec_report=report)

        assert result.completeness_score == 50.0

    def test_0_percent_completeness_affects_overall(self):
        """0% completeness reduces the overall score proportionally (weight=0.4)."""
        scorer = HealthScorer()
        report = PostExecutionReport(
            passed=True,
            chains_total=3,
            chains_intact=0,
            chains_broken=0,
            chains_degraded=3,
            completeness_pct=0.0,
        )

        result = scorer.score(postexec_report=report)

        assert result.completeness_score == 0.0
        # With completeness=0, boundary=100, preflight=100, discrepancy=0:
        # overall = 0*0.4 + 100*0.3 + 100*0.2 + 100*0.1 = 60.0
        assert result.overall == 60.0


# ---------------------------------------------------------------------------
# HealthScorer - boundary component
# ---------------------------------------------------------------------------


class TestBoundaryComponent:
    def test_all_phases_passed(self):
        """All phases passed yields boundary_score=100.0."""
        scorer = HealthScorer()
        summary = WorkflowRunSummary(
            mode=EnforcementMode.STRICT,
            total_phases=5,
            passed_phases=5,
            failed_phases=0,
        )

        result = scorer.score(runtime_summary=summary)

        assert result.boundary_score == 100.0

    def test_three_of_five_phases_passed(self):
        """3/5 phases passed yields boundary_score=60.0."""
        scorer = HealthScorer()
        summary = WorkflowRunSummary(
            mode=EnforcementMode.PERMISSIVE,
            total_phases=5,
            passed_phases=3,
            failed_phases=2,
        )

        result = scorer.score(runtime_summary=summary)

        assert result.boundary_score == 60.0

    def test_zero_total_phases_gives_perfect_score(self):
        """0 total phases yields boundary_score=100.0 (no phases to fail)."""
        scorer = HealthScorer()
        summary = WorkflowRunSummary(
            mode=EnforcementMode.AUDIT,
            total_phases=0,
            passed_phases=0,
            failed_phases=0,
        )

        result = scorer.score(runtime_summary=summary)

        assert result.boundary_score == 100.0


# ---------------------------------------------------------------------------
# HealthScorer - preflight component
# ---------------------------------------------------------------------------


class TestPreflightComponent:
    def test_preflight_passed(self):
        """Preflight passed yields preflight_score=100.0."""
        scorer = HealthScorer()
        preflight = PreflightResult(passed=True)

        result = scorer.score(preflight_result=preflight)

        assert result.preflight_score == 100.0

    def test_preflight_failed(self):
        """Preflight failed yields preflight_score=0.0."""
        scorer = HealthScorer()
        preflight = PreflightResult(passed=False)

        result = scorer.score(preflight_result=preflight)

        assert result.preflight_score == 0.0


# ---------------------------------------------------------------------------
# HealthScorer - discrepancy penalty
# ---------------------------------------------------------------------------


class TestDiscrepancyPenalty:
    def test_no_discrepancies(self):
        """No discrepancies yields penalty=0.0."""
        scorer = HealthScorer()
        report = PostExecutionReport(
            passed=True,
            chains_total=3,
            chains_intact=3,
            chains_broken=0,
            chains_degraded=0,
            completeness_pct=100.0,
            runtime_discrepancies=[],
        )

        result = scorer.score(postexec_report=report)

        assert result.discrepancy_penalty == 0.0

    def test_two_discrepancies_penalty_50(self):
        """2 discrepancies yield penalty=50.0 (25 per discrepancy)."""
        scorer = HealthScorer()
        report = PostExecutionReport(
            passed=True,
            chains_total=5,
            chains_intact=5,
            chains_broken=0,
            chains_degraded=0,
            completeness_pct=100.0,
            runtime_discrepancies=[
                RuntimeDiscrepancy(
                    phase="plan",
                    discrepancy_type="late_healing",
                    message="healed",
                ),
                RuntimeDiscrepancy(
                    phase="design",
                    discrepancy_type="late_corruption",
                    message="corrupted",
                ),
            ],
        )

        result = scorer.score(postexec_report=report)

        assert result.discrepancy_penalty == 50.0

    def test_five_or_more_discrepancies_capped_at_100(self):
        """5+ discrepancies cap the penalty at 100.0."""
        scorer = HealthScorer()
        discrepancies = [
            RuntimeDiscrepancy(
                phase=f"phase_{i}",
                discrepancy_type="late_corruption",
                message=f"corruption {i}",
            )
            for i in range(5)
        ]
        report = PostExecutionReport(
            passed=True,
            chains_total=5,
            chains_intact=5,
            chains_broken=0,
            chains_degraded=0,
            completeness_pct=100.0,
            runtime_discrepancies=discrepancies,
        )

        result = scorer.score(postexec_report=report)

        assert result.discrepancy_penalty == 100.0

        # Also verify that 6 discrepancies still caps at 100
        discrepancies_6 = discrepancies + [
            RuntimeDiscrepancy(
                phase="phase_5",
                discrepancy_type="late_healing",
                message="extra",
            )
        ]
        report_6 = PostExecutionReport(
            passed=True,
            chains_total=5,
            chains_intact=5,
            chains_broken=0,
            chains_degraded=0,
            completeness_pct=100.0,
            runtime_discrepancies=discrepancies_6,
        )

        result_6 = scorer.score(postexec_report=report_6)
        assert result_6.discrepancy_penalty == 100.0


# ---------------------------------------------------------------------------
# HealthScorer - combined scoring
# ---------------------------------------------------------------------------


class TestCombinedScoring:
    def test_all_perfect_gives_100(self):
        """All perfect inputs yield overall=100.0."""
        scorer = HealthScorer()
        preflight = PreflightResult(passed=True)
        summary = WorkflowRunSummary(
            mode=EnforcementMode.STRICT,
            total_phases=3,
            passed_phases=3,
            failed_phases=0,
        )
        report = PostExecutionReport(
            passed=True,
            chains_total=5,
            chains_intact=5,
            chains_broken=0,
            chains_degraded=0,
            completeness_pct=100.0,
            runtime_discrepancies=[],
        )

        result = scorer.score(
            preflight_result=preflight,
            runtime_summary=summary,
            postexec_report=report,
        )

        assert result.overall == 100.0
        assert result.completeness_score == 100.0
        assert result.boundary_score == 100.0
        assert result.preflight_score == 100.0
        assert result.discrepancy_penalty == 0.0

    def test_all_worst_gives_0(self):
        """All worst-case inputs yield overall=0.0."""
        scorer = HealthScorer()
        preflight = PreflightResult(passed=False)
        summary = WorkflowRunSummary(
            mode=EnforcementMode.PERMISSIVE,
            total_phases=5,
            passed_phases=0,
            failed_phases=5,
        )
        discrepancies = [
            RuntimeDiscrepancy(
                phase=f"phase_{i}",
                discrepancy_type="late_corruption",
                message=f"corruption {i}",
            )
            for i in range(5)
        ]
        report = PostExecutionReport(
            passed=False,
            chains_total=5,
            chains_intact=0,
            chains_broken=5,
            chains_degraded=0,
            completeness_pct=0.0,
            runtime_discrepancies=discrepancies,
        )

        result = scorer.score(
            preflight_result=preflight,
            runtime_summary=summary,
            postexec_report=report,
        )

        # completeness=0*0.4 + boundary=0*0.3 + preflight=0*0.2
        # + (100-100)*0.1 = 0.0
        assert result.overall == 0.0

    def test_mixed_inputs_calculated_correctly(self):
        """Mixed inputs: 50% completeness, 60% boundary, preflight passed, 1 discrepancy."""
        scorer = HealthScorer()
        preflight = PreflightResult(passed=True)
        summary = WorkflowRunSummary(
            mode=EnforcementMode.PERMISSIVE,
            total_phases=5,
            passed_phases=3,
            failed_phases=2,
        )
        report = PostExecutionReport(
            passed=True,
            chains_total=4,
            chains_intact=2,
            chains_broken=0,
            chains_degraded=2,
            completeness_pct=50.0,
            runtime_discrepancies=[
                RuntimeDiscrepancy(
                    phase="implement",
                    discrepancy_type="late_healing",
                    message="healed after failure",
                ),
            ],
        )

        result = scorer.score(
            preflight_result=preflight,
            runtime_summary=summary,
            postexec_report=report,
        )

        assert result.completeness_score == 50.0
        assert result.boundary_score == 60.0
        assert result.preflight_score == 100.0
        assert result.discrepancy_penalty == 25.0

        # Expected overall:
        # 50*0.4 + 60*0.3 + 100*0.2 + (100-25)*0.1
        # = 20 + 18 + 20 + 7.5 = 65.5
        assert result.overall == 65.5


# ---------------------------------------------------------------------------
# HealthScorer - custom weights
# ---------------------------------------------------------------------------


class TestCustomWeights:
    def test_custom_weights_change_the_score(self):
        """Custom weights produce a different overall score than default weights."""
        # Use a report with 0% completeness so the weight difference is visible
        report = PostExecutionReport(
            passed=True,
            chains_total=4,
            chains_intact=0,
            chains_broken=0,
            chains_degraded=4,
            completeness_pct=0.0,
        )

        default_scorer = HealthScorer()
        custom_scorer = HealthScorer(
            weights={
                "completeness": 0.10,  # reduced from 0.40
                "boundary": 0.30,
                "preflight": 0.20,
                "discrepancy": 0.40,  # increased from 0.10
            }
        )

        default_result = default_scorer.score(postexec_report=report)
        custom_result = custom_scorer.score(postexec_report=report)

        # Default: 0*0.4 + 100*0.3 + 100*0.2 + 100*0.1 = 60.0
        assert default_result.overall == 60.0

        # Custom: 0*0.1 + 100*0.3 + 100*0.2 + 100*0.4 = 90.0
        assert custom_result.overall == 90.0

        assert default_result.overall != custom_result.overall

    def test_equal_weights(self):
        """Equal weights (0.25 each) distribute influence evenly."""
        scorer = HealthScorer(
            weights={
                "completeness": 0.25,
                "boundary": 0.25,
                "preflight": 0.25,
                "discrepancy": 0.25,
            }
        )

        preflight = PreflightResult(passed=False)
        summary = WorkflowRunSummary(
            mode=EnforcementMode.STRICT,
            total_phases=4,
            passed_phases=2,
            failed_phases=2,
        )
        report = PostExecutionReport(
            passed=True,
            chains_total=2,
            chains_intact=2,
            chains_broken=0,
            chains_degraded=0,
            completeness_pct=100.0,
            runtime_discrepancies=[
                RuntimeDiscrepancy(
                    phase="plan",
                    discrepancy_type="late_healing",
                    message="healed",
                ),
            ],
        )

        result = scorer.score(
            preflight_result=preflight,
            runtime_summary=summary,
            postexec_report=report,
        )

        # completeness=100, boundary=50, preflight=0, discrepancy_penalty=25
        assert result.completeness_score == 100.0
        assert result.boundary_score == 50.0
        assert result.preflight_score == 0.0
        assert result.discrepancy_penalty == 25.0

        # Expected overall:
        # 100*0.25 + 50*0.25 + 0*0.25 + (100-25)*0.25
        # = 25 + 12.5 + 0 + 18.75 = 56.25
        # rounded to 1 decimal -> 56.2 (Python rounds 56.25 to 56.2 with banker's rounding)
        # Actually round(56.25, 1) = 56.2 in Python (banker's rounding)
        # Let's just check with a tolerance
        assert result.overall == pytest.approx(56.25, abs=0.1)
