"""Tests for contextcore.contracts.observability.alerts — Layer 6 alert evaluation.

Covers AlertRule, AlertEvent, AlertEvaluationResult models, DEFAULT_ALERT_RULES
constants, and the AlertEvaluator against preflight, runtime, and post-execution
results.
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from contextcore.contracts.observability.alerts import (
    DEFAULT_ALERT_RULES,
    AlertEvaluationResult,
    AlertEvaluator,
    AlertEvent,
    AlertRule,
)
from contextcore.contracts.postexec.validator import PostExecutionReport
from contextcore.contracts.preflight.checker import PreflightResult, PreflightViolation
from contextcore.contracts.runtime.guard import WorkflowRunSummary
from contextcore.contracts.types import (
    ConstraintSeverity,
    EnforcementMode,
    PropagationStatus,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable layer results
# ---------------------------------------------------------------------------


@pytest.fixture()
def healthy_report() -> PostExecutionReport:
    return PostExecutionReport(
        passed=True,
        chains_total=5,
        chains_intact=5,
        chains_broken=0,
        chains_degraded=0,
        completeness_pct=100.0,
    )


@pytest.fixture()
def unhealthy_report() -> PostExecutionReport:
    return PostExecutionReport(
        passed=False,
        chains_total=5,
        chains_intact=1,
        chains_broken=3,
        chains_degraded=1,
        completeness_pct=20.0,
    )


@pytest.fixture()
def healthy_runtime() -> WorkflowRunSummary:
    return WorkflowRunSummary(
        mode=EnforcementMode.STRICT,
        total_phases=5,
        passed_phases=5,
        failed_phases=0,
        total_blocking_failures=0,
        total_defaults_applied=0,
        overall_passed=True,
        overall_status=PropagationStatus.PROPAGATED,
    )


@pytest.fixture()
def unhealthy_runtime() -> WorkflowRunSummary:
    return WorkflowRunSummary(
        mode=EnforcementMode.PERMISSIVE,
        total_phases=5,
        passed_phases=2,
        failed_phases=3,
        total_blocking_failures=4,
        total_defaults_applied=8,
        overall_passed=False,
        overall_status=PropagationStatus.FAILED,
    )


@pytest.fixture()
def healthy_preflight() -> PreflightResult:
    return PreflightResult(passed=True, phases_checked=5, fields_checked=20)


@pytest.fixture()
def unhealthy_preflight() -> PreflightResult:
    return PreflightResult(
        passed=False,
        phases_checked=5,
        fields_checked=20,
        violations=[
            PreflightViolation(
                check_type="field_readiness",
                phase="plan",
                field="domain",
                severity=ConstraintSeverity.BLOCKING,
                message="Missing domain",
            ),
        ],
    )


# =========================================================================
# AlertRule model
# =========================================================================


class TestAlertRule:
    """Tests for the AlertRule Pydantic model."""

    def test_valid_construction(self) -> None:
        rule = AlertRule(
            rule_id="test.rule",
            description="A test rule",
            severity=ConstraintSeverity.BLOCKING,
            metric="completeness_pct",
            operator="lt",
            threshold=50.0,
        )
        assert rule.rule_id == "test.rule"
        assert rule.description == "A test rule"
        assert rule.severity == ConstraintSeverity.BLOCKING
        assert rule.metric == "completeness_pct"
        assert rule.operator == "lt"
        assert rule.threshold == 50.0

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlertRule(
                rule_id="test.rule",
                metric="completeness_pct",
                operator="lt",
                threshold=50.0,
                bogus_field="should fail",  # type: ignore[call-arg]
            )

    def test_default_severity_is_warning(self) -> None:
        rule = AlertRule(
            rule_id="test.defaults",
            metric="completeness_pct",
            operator="lt",
            threshold=80.0,
        )
        assert rule.severity == ConstraintSeverity.WARNING


# =========================================================================
# AlertEvent model
# =========================================================================


class TestAlertEvent:
    """Tests for the AlertEvent Pydantic model."""

    def test_construction_stores_all_fields(self) -> None:
        event = AlertEvent(
            rule_id="r1",
            firing=True,
            severity=ConstraintSeverity.BLOCKING,
            metric="completeness_pct",
            actual_value=30.0,
            threshold=50.0,
            operator="lt",
            message="completeness below critical",
        )
        assert event.rule_id == "r1"
        assert event.firing is True
        assert event.severity == ConstraintSeverity.BLOCKING
        assert event.metric == "completeness_pct"
        assert event.actual_value == 30.0
        assert event.threshold == 50.0
        assert event.operator == "lt"
        assert event.message == "completeness below critical"

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AlertEvent(
                rule_id="r1",
                firing=False,
                severity=ConstraintSeverity.WARNING,
                metric="completeness_pct",
                actual_value=90.0,
                threshold=80.0,
                operator="lt",
                extra_thing=42,  # type: ignore[call-arg]
            )


# =========================================================================
# AlertEvaluationResult model
# =========================================================================


class TestAlertEvaluationResult:
    """Tests for the AlertEvaluationResult Pydantic model."""

    def test_default_construction(self) -> None:
        result = AlertEvaluationResult()
        assert result.events == []
        assert result.rules_evaluated == 0
        assert result.alerts_firing == 0
        assert result.has_firing_alerts is False
        assert result.critical_alerts == []
        assert result.warning_alerts == []

    def test_has_firing_alerts_true_when_alerts_firing(self) -> None:
        result = AlertEvaluationResult(
            events=[
                AlertEvent(
                    rule_id="r1",
                    firing=True,
                    severity=ConstraintSeverity.WARNING,
                    metric="completeness_pct",
                    actual_value=70.0,
                    threshold=80.0,
                    operator="lt",
                    message="below warning",
                ),
            ],
            rules_evaluated=1,
            alerts_firing=1,
        )
        assert result.has_firing_alerts is True

    def test_critical_alerts_filters_blocking_firing(self) -> None:
        events = [
            AlertEvent(
                rule_id="crit1",
                firing=True,
                severity=ConstraintSeverity.BLOCKING,
                metric="completeness_pct",
                actual_value=30.0,
                threshold=50.0,
                operator="lt",
                message="critical",
            ),
            AlertEvent(
                rule_id="warn1",
                firing=True,
                severity=ConstraintSeverity.WARNING,
                metric="completeness_pct",
                actual_value=70.0,
                threshold=80.0,
                operator="lt",
                message="warning",
            ),
            AlertEvent(
                rule_id="crit2_not_firing",
                firing=False,
                severity=ConstraintSeverity.BLOCKING,
                metric="blocking_failures",
                actual_value=0.0,
                threshold=0.0,
                operator="gt",
            ),
        ]
        result = AlertEvaluationResult(
            events=events, rules_evaluated=3, alerts_firing=2
        )
        crit = result.critical_alerts
        assert len(crit) == 1
        assert crit[0].rule_id == "crit1"

    def test_warning_alerts_filters_warning_firing(self) -> None:
        events = [
            AlertEvent(
                rule_id="crit1",
                firing=True,
                severity=ConstraintSeverity.BLOCKING,
                metric="completeness_pct",
                actual_value=30.0,
                threshold=50.0,
                operator="lt",
                message="critical",
            ),
            AlertEvent(
                rule_id="warn1",
                firing=True,
                severity=ConstraintSeverity.WARNING,
                metric="completeness_pct",
                actual_value=70.0,
                threshold=80.0,
                operator="lt",
                message="warning",
            ),
            AlertEvent(
                rule_id="warn2_not_firing",
                firing=False,
                severity=ConstraintSeverity.WARNING,
                metric="defaults_applied",
                actual_value=2.0,
                threshold=5.0,
                operator="gt",
            ),
        ]
        result = AlertEvaluationResult(
            events=events, rules_evaluated=3, alerts_firing=2
        )
        warns = result.warning_alerts
        assert len(warns) == 1
        assert warns[0].rule_id == "warn1"


# =========================================================================
# DEFAULT_ALERT_RULES
# =========================================================================


class TestDefaultAlertRules:
    """Tests for the built-in DEFAULT_ALERT_RULES list."""

    def test_contains_five_rules(self) -> None:
        assert len(DEFAULT_ALERT_RULES) == 5

    def test_all_rules_have_valid_operators(self) -> None:
        valid_operators = {"lt", "gt", "lte", "gte", "eq"}
        for rule in DEFAULT_ALERT_RULES:
            assert rule.operator in valid_operators, (
                f"Rule '{rule.rule_id}' has invalid operator '{rule.operator}'"
            )


# =========================================================================
# AlertEvaluator — completeness (postexec)
# =========================================================================


class TestAlertEvaluatorCompleteness:
    """Tests for completeness-based alert evaluation via PostExecutionReport."""

    def test_completeness_100_no_completeness_alerts(
        self, healthy_report: PostExecutionReport
    ) -> None:
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(postexec_report=healthy_report)
        # Completeness rules should not fire at 100%
        completeness_events = [
            e for e in result.events if e.metric == "completeness_pct"
        ]
        assert all(not e.firing for e in completeness_events)

    def test_completeness_60_warning_fires_critical_does_not(self) -> None:
        report = PostExecutionReport(
            passed=False,
            chains_total=5,
            chains_intact=3,
            chains_broken=1,
            chains_degraded=1,
            completeness_pct=60.0,
        )
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(postexec_report=report)

        completeness_events = {
            e.rule_id: e
            for e in result.events
            if e.metric == "completeness_pct"
        }
        # 60 < 80 → warning fires
        warning = completeness_events.get("propagation.completeness.warning")
        assert warning is not None
        assert warning.firing is True
        assert warning.severity == ConstraintSeverity.WARNING

        # 60 >= 50 → critical does not fire
        critical = completeness_events.get("propagation.completeness.critical")
        assert critical is not None
        assert critical.firing is False

    def test_completeness_30_both_fire(self) -> None:
        report = PostExecutionReport(
            passed=False,
            chains_total=5,
            chains_intact=1,
            chains_broken=3,
            chains_degraded=1,
            completeness_pct=30.0,
        )
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(postexec_report=report)

        completeness_events = {
            e.rule_id: e
            for e in result.events
            if e.metric == "completeness_pct"
        }
        assert completeness_events["propagation.completeness.critical"].firing is True
        assert completeness_events["propagation.completeness.warning"].firing is True


# =========================================================================
# AlertEvaluator — runtime
# =========================================================================


class TestAlertEvaluatorRuntime:
    """Tests for runtime-based alert evaluation via WorkflowRunSummary."""

    def test_no_blocking_failures_rule_not_firing(
        self, healthy_runtime: WorkflowRunSummary
    ) -> None:
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(runtime_summary=healthy_runtime)

        blocking_event = next(
            (e for e in result.events if e.rule_id == "runtime.blocking_failures"),
            None,
        )
        assert blocking_event is not None
        assert blocking_event.firing is False

    def test_blocking_failures_gt_zero_rule_fires(
        self, unhealthy_runtime: WorkflowRunSummary
    ) -> None:
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(runtime_summary=unhealthy_runtime)

        blocking_event = next(
            (e for e in result.events if e.rule_id == "runtime.blocking_failures"),
            None,
        )
        assert blocking_event is not None
        assert blocking_event.firing is True
        assert blocking_event.actual_value == 4.0

    def test_defaults_gt_5_warning_fires(
        self, unhealthy_runtime: WorkflowRunSummary
    ) -> None:
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(runtime_summary=unhealthy_runtime)

        defaults_event = next(
            (e for e in result.events if e.rule_id == "runtime.defaults_applied"),
            None,
        )
        assert defaults_event is not None
        assert defaults_event.firing is True
        assert defaults_event.actual_value == 8.0
        assert defaults_event.severity == ConstraintSeverity.WARNING


# =========================================================================
# AlertEvaluator — preflight
# =========================================================================


class TestAlertEvaluatorPreflight:
    """Tests for preflight-based alert evaluation via PreflightResult."""

    def test_no_critical_violations_rule_not_firing(
        self, healthy_preflight: PreflightResult
    ) -> None:
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(preflight_result=healthy_preflight)

        preflight_event = next(
            (e for e in result.events if e.rule_id == "preflight.critical_violations"),
            None,
        )
        assert preflight_event is not None
        assert preflight_event.firing is False

    def test_critical_violations_gt_zero_rule_fires(
        self, unhealthy_preflight: PreflightResult
    ) -> None:
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(preflight_result=unhealthy_preflight)

        preflight_event = next(
            (e for e in result.events if e.rule_id == "preflight.critical_violations"),
            None,
        )
        assert preflight_event is not None
        assert preflight_event.firing is True
        assert preflight_event.actual_value == 1.0


# =========================================================================
# AlertEvaluator — mixed inputs
# =========================================================================


class TestAlertEvaluatorMixedInputs:
    """Tests for evaluating with multiple layer results simultaneously."""

    def test_all_healthy_no_alerts(
        self,
        healthy_report: PostExecutionReport,
        healthy_runtime: WorkflowRunSummary,
        healthy_preflight: PreflightResult,
    ) -> None:
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(
            preflight_result=healthy_preflight,
            runtime_summary=healthy_runtime,
            postexec_report=healthy_report,
        )
        assert result.alerts_firing == 0
        assert result.has_firing_alerts is False
        # All 5 default rules should produce events (none firing)
        assert result.rules_evaluated == 5

    def test_all_unhealthy_multiple_alerts_fire(
        self,
        unhealthy_report: PostExecutionReport,
        unhealthy_runtime: WorkflowRunSummary,
        unhealthy_preflight: PreflightResult,
    ) -> None:
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(
            preflight_result=unhealthy_preflight,
            runtime_summary=unhealthy_runtime,
            postexec_report=unhealthy_report,
        )
        assert result.has_firing_alerts is True
        # With the unhealthy inputs (completeness=20%, blocking_failures=4,
        # defaults=8, preflight_violations=1), all 5 rules should fire.
        assert result.alerts_firing == 5
        assert result.rules_evaluated == 5

    def test_only_runtime_provided_only_runtime_metrics(
        self, unhealthy_runtime: WorkflowRunSummary
    ) -> None:
        evaluator = AlertEvaluator()
        result = evaluator.evaluate(runtime_summary=unhealthy_runtime)

        # Only runtime metrics available: blocking_failures, defaults_applied,
        # failed_phases. Completeness and preflight rules should be skipped.
        evaluated_metrics = {e.metric for e in result.events}
        assert "completeness_pct" not in evaluated_metrics
        assert "preflight_violations" not in evaluated_metrics
        assert "blocking_failures" in evaluated_metrics
        assert "defaults_applied" in evaluated_metrics


# =========================================================================
# AlertEvaluator — custom rules
# =========================================================================


class TestAlertEvaluatorCustomRules:
    """Tests for custom rule injection into the AlertEvaluator."""

    def test_custom_rules_override_defaults(
        self, healthy_report: PostExecutionReport
    ) -> None:
        custom_rule = AlertRule(
            rule_id="custom.strict_completeness",
            description="Completeness must be 100%",
            severity=ConstraintSeverity.BLOCKING,
            metric="completeness_pct",
            operator="lt",
            threshold=100.0,
        )
        # 100% completeness should not fire even with threshold=100 because
        # 100 is NOT less than 100.
        evaluator = AlertEvaluator(rules=[custom_rule])
        result = evaluator.evaluate(postexec_report=healthy_report)
        assert result.rules_evaluated == 1
        assert result.alerts_firing == 0

        # Now test with a report that has 99% completeness
        report_99 = PostExecutionReport(
            passed=True,
            chains_total=100,
            chains_intact=99,
            chains_broken=0,
            chains_degraded=1,
            completeness_pct=99.0,
        )
        result_99 = evaluator.evaluate(postexec_report=report_99)
        assert result_99.alerts_firing == 1
        assert result_99.events[0].firing is True
        assert result_99.events[0].rule_id == "custom.strict_completeness"

    def test_empty_rules_list_no_events(
        self, healthy_report: PostExecutionReport
    ) -> None:
        evaluator = AlertEvaluator(rules=[])
        result = evaluator.evaluate(postexec_report=healthy_report)
        assert result.events == []
        assert result.rules_evaluated == 0
        assert result.alerts_firing == 0


# =========================================================================
# AlertEvaluator — edge cases
# =========================================================================


class TestAlertEvaluatorEdgeCases:
    """Edge-case tests for the AlertEvaluator."""

    def test_unknown_operator_skipped_gracefully(
        self, healthy_report: PostExecutionReport, caplog: pytest.LogCaptureFixture
    ) -> None:
        bad_rule = AlertRule(
            rule_id="bad.operator",
            description="Uses an unsupported operator",
            severity=ConstraintSeverity.WARNING,
            metric="completeness_pct",
            operator="neq",  # not in _OPERATORS
            threshold=50.0,
        )
        evaluator = AlertEvaluator(rules=[bad_rule])

        with caplog.at_level(logging.WARNING):
            result = evaluator.evaluate(postexec_report=healthy_report)

        # The rule should be skipped — no event produced for it
        assert result.rules_evaluated == 0
        assert result.alerts_firing == 0
        assert result.events == []

        # A warning should have been logged
        assert any("Unknown operator" in msg for msg in caplog.messages)
