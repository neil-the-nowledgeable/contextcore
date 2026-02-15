"""
Observability and alerting — Layer 6 of defense-in-depth.

Defines alert rules tied to propagation contracts, computes a unified
health score from Layer 3-5 results, and emits OTel span events for
dashboards and alerting backends.

Public API::

    from contextcore.contracts.observability import (
        # Alerts
        AlertEvaluator,
        AlertRule,
        AlertEvent,
        AlertEvaluationResult,
        DEFAULT_ALERT_RULES,
        # Health
        HealthScorer,
        HealthScore,
        # OTel helpers
        emit_health_score,
        emit_alert_event,
        emit_alert_evaluation,
    )
"""

from contextcore.contracts.observability.alerts import (
    DEFAULT_ALERT_RULES,
    AlertEvaluationResult,
    AlertEvaluator,
    AlertEvent,
    AlertRule,
)
from contextcore.contracts.observability.health import (
    HealthScore,
    HealthScorer,
)
from contextcore.contracts.observability.otel import (
    emit_alert_evaluation,
    emit_alert_event,
    emit_health_score,
)

__all__ = [
    # Alerts
    "AlertEvaluator",
    "AlertRule",
    "AlertEvent",
    "AlertEvaluationResult",
    "DEFAULT_ALERT_RULES",
    # Health
    "HealthScorer",
    "HealthScore",
    # OTel
    "emit_health_score",
    "emit_alert_event",
    "emit_alert_evaluation",
]
