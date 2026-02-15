"""
Alert rule definitions for context propagation — Layer 6.

Defines alert thresholds tied to propagation contracts.  Each
``AlertRule`` specifies a condition, severity, and the query pattern
used to evaluate it.  The ``AlertEvaluator`` checks Layer 3-5 results
against these rules and produces ``AlertEvent`` instances for any
that fire.

Built-in rules cover:

- **Completeness** — propagation chain completeness drops below threshold.
- **Boundary failures** — runtime boundary failure count exceeds limit.
- **Degradation** — too many defaulted fields across the workflow.
- **Preflight** — pre-flight violations exceed threshold.

Usage::

    from contextcore.contracts.observability import AlertEvaluator

    evaluator = AlertEvaluator()
    events = evaluator.evaluate(
        preflight_result=preflight_result,
        runtime_summary=guard.summarize(),
        postexec_report=report,
    )
    for event in events:
        if event.firing:
            logger.warning("ALERT: %s — %s", event.rule_id, event.message)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.postexec.validator import PostExecutionReport
from contextcore.contracts.preflight.checker import PreflightResult
from contextcore.contracts.runtime.guard import WorkflowRunSummary
from contextcore.contracts.types import ConstraintSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AlertRule(BaseModel):
    """A single alerting rule for context propagation health."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., min_length=1)
    description: str = ""
    severity: ConstraintSeverity = ConstraintSeverity.WARNING
    metric: str = Field(
        ..., description="Which metric to evaluate (completeness_pct, "
        "blocking_failures, defaults_applied, preflight_violations)"
    )
    operator: str = Field(
        ..., description="Comparison operator: lt, gt, lte, gte, eq"
    )
    threshold: float = Field(..., description="Threshold value")


class AlertEvent(BaseModel):
    """Result of evaluating a single alert rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    firing: bool
    severity: ConstraintSeverity
    metric: str
    actual_value: float
    threshold: float
    operator: str
    message: str = ""


class AlertEvaluationResult(BaseModel):
    """Aggregated result of evaluating all alert rules."""

    model_config = ConfigDict(extra="forbid")

    events: list[AlertEvent] = Field(default_factory=list)
    rules_evaluated: int = 0
    alerts_firing: int = 0

    @property
    def has_firing_alerts(self) -> bool:
        return self.alerts_firing > 0

    @property
    def critical_alerts(self) -> list[AlertEvent]:
        return [
            e for e in self.events
            if e.firing and e.severity == ConstraintSeverity.BLOCKING
        ]

    @property
    def warning_alerts(self) -> list[AlertEvent]:
        return [
            e for e in self.events
            if e.firing and e.severity == ConstraintSeverity.WARNING
        ]


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------


DEFAULT_ALERT_RULES: list[AlertRule] = [
    AlertRule(
        rule_id="propagation.completeness.critical",
        description="Propagation chain completeness below critical threshold",
        severity=ConstraintSeverity.BLOCKING,
        metric="completeness_pct",
        operator="lt",
        threshold=50.0,
    ),
    AlertRule(
        rule_id="propagation.completeness.warning",
        description="Propagation chain completeness below warning threshold",
        severity=ConstraintSeverity.WARNING,
        metric="completeness_pct",
        operator="lt",
        threshold=80.0,
    ),
    AlertRule(
        rule_id="runtime.blocking_failures",
        description="Runtime blocking failures exceed threshold",
        severity=ConstraintSeverity.BLOCKING,
        metric="blocking_failures",
        operator="gt",
        threshold=0.0,
    ),
    AlertRule(
        rule_id="runtime.defaults_applied",
        description="Too many fields defaulted during workflow",
        severity=ConstraintSeverity.WARNING,
        metric="defaults_applied",
        operator="gt",
        threshold=5.0,
    ),
    AlertRule(
        rule_id="preflight.critical_violations",
        description="Pre-flight critical violations detected",
        severity=ConstraintSeverity.BLOCKING,
        metric="preflight_violations",
        operator="gt",
        threshold=0.0,
    ),
]


# ---------------------------------------------------------------------------
# Comparison operators
# ---------------------------------------------------------------------------


_OPERATORS: dict[str, Any] = {
    "lt": lambda a, b: a < b,
    "gt": lambda a, b: a > b,
    "lte": lambda a, b: a <= b,
    "gte": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,
}

_OPERATOR_LABELS: dict[str, str] = {
    "lt": "<",
    "gt": ">",
    "lte": "<=",
    "gte": ">=",
    "eq": "==",
}


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class AlertEvaluator:
    """Evaluates alert rules against Layer 3-5 results."""

    def __init__(
        self,
        rules: Optional[list[AlertRule]] = None,
    ) -> None:
        self._rules = rules if rules is not None else list(DEFAULT_ALERT_RULES)

    @property
    def rules(self) -> list[AlertRule]:
        return list(self._rules)

    def evaluate(
        self,
        preflight_result: Optional[PreflightResult] = None,
        runtime_summary: Optional[WorkflowRunSummary] = None,
        postexec_report: Optional[PostExecutionReport] = None,
    ) -> AlertEvaluationResult:
        """Evaluate all rules against the provided results.

        Any combination of results can be provided.  Metrics that cannot
        be computed from the given results are skipped.

        Args:
            preflight_result: Layer 3 pre-flight result.
            runtime_summary: Layer 4 workflow run summary.
            postexec_report: Layer 5 post-execution report.

        Returns:
            Aggregated ``AlertEvaluationResult``.
        """
        metrics = self._extract_metrics(
            preflight_result, runtime_summary, postexec_report
        )

        events: list[AlertEvent] = []
        for rule in self._rules:
            if rule.metric not in metrics:
                continue

            actual = metrics[rule.metric]
            comparator = _OPERATORS.get(rule.operator)
            if comparator is None:
                logger.warning(
                    "Unknown operator '%s' in rule '%s'",
                    rule.operator,
                    rule.rule_id,
                )
                continue

            firing = comparator(actual, rule.threshold)
            op_label = _OPERATOR_LABELS.get(rule.operator, rule.operator)

            message = ""
            if firing:
                message = (
                    f"{rule.description}: "
                    f"{rule.metric}={actual} {op_label} {rule.threshold}"
                )

            events.append(
                AlertEvent(
                    rule_id=rule.rule_id,
                    firing=firing,
                    severity=rule.severity,
                    metric=rule.metric,
                    actual_value=actual,
                    threshold=rule.threshold,
                    operator=rule.operator,
                    message=message,
                )
            )

        firing_count = sum(1 for e in events if e.firing)

        if firing_count > 0:
            logger.warning(
                "Alert evaluation: %d/%d rules firing",
                firing_count,
                len(events),
            )

        return AlertEvaluationResult(
            events=events,
            rules_evaluated=len(events),
            alerts_firing=firing_count,
        )

    @staticmethod
    def _extract_metrics(
        preflight_result: Optional[PreflightResult],
        runtime_summary: Optional[WorkflowRunSummary],
        postexec_report: Optional[PostExecutionReport],
    ) -> dict[str, float]:
        """Extract numeric metrics from layer results."""
        metrics: dict[str, float] = {}

        if postexec_report is not None:
            metrics["completeness_pct"] = postexec_report.completeness_pct
            metrics["chains_broken"] = float(postexec_report.chains_broken)
            metrics["chains_degraded"] = float(postexec_report.chains_degraded)

        if runtime_summary is not None:
            metrics["blocking_failures"] = float(
                runtime_summary.total_blocking_failures
            )
            metrics["defaults_applied"] = float(
                runtime_summary.total_defaults_applied
            )
            metrics["failed_phases"] = float(runtime_summary.failed_phases)

        if preflight_result is not None:
            metrics["preflight_violations"] = float(
                len(preflight_result.critical_violations)
            )
            metrics["preflight_warnings"] = float(
                len(preflight_result.warnings)
            )

        return metrics
