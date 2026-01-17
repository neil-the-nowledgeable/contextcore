"""
RBAC Audit Emitter.

Emits access decisions as OTel spans for compliance and analysis.

Enables:
- TraceQL queries for access patterns
- Grafana dashboards for access visualization
- Compliance reporting

Example TraceQL queries:
    # All denials in last 24h
    { name =~ "rbac.deny" }

    # Sensitive access attempts
    { rbac.sensitive_access = true }

    # Access by specific principal
    { rbac.principal_id = "claude-code" }
"""

from __future__ import annotations

import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from contextcore.rbac.models import (
    AccessDecision,
    PolicyDecision,
)

logger = logging.getLogger(__name__)


class RBACAuditEmitter:
    """
    Emits RBAC access decisions as OTel spans.

    Each access decision becomes a span with attributes for:
    - Principal information
    - Resource being accessed
    - Action attempted
    - Decision outcome
    - Timing and correlation

    Example:
        emitter = RBACAuditEmitter()
        trace_id = emitter.emit_decision(decision)
    """

    def __init__(self, tracer_name: str = "contextcore.rbac.audit"):
        self.tracer = trace.get_tracer(tracer_name)

    def emit_decision(self, decision: AccessDecision) -> str:
        """
        Emit access decision as OTel span.

        Returns trace_id for reference.
        """
        span_name = f"rbac.{decision.decision.value}"

        with self.tracer.start_as_current_span(
            span_name,
            kind=SpanKind.INTERNAL,
        ) as span:
            # Core RBAC attributes
            span.set_attribute("rbac.decision", decision.decision.value)
            span.set_attribute("rbac.principal_id", decision.principal_id)
            span.set_attribute("rbac.resource_type", decision.resource.resource_type.value)
            span.set_attribute("rbac.resource_id", decision.resource.resource_id)
            span.set_attribute("rbac.action", decision.action.value)

            # Sensitive access flag
            if decision.resource.sensitive:
                span.set_attribute("rbac.sensitive_access", True)
                if decision.resource.sensitivity_reason:
                    span.set_attribute(
                        "rbac.sensitivity_reason",
                        decision.resource.sensitivity_reason
                    )

            # Decision details
            if decision.matched_role:
                span.set_attribute("rbac.matched_role", decision.matched_role)
            if decision.matched_permission:
                span.set_attribute("rbac.matched_permission", decision.matched_permission)
            if decision.denial_reason:
                span.set_attribute("rbac.denial_reason", decision.denial_reason)

            # Project scope if applicable
            if decision.resource.project_scope:
                span.set_attribute("rbac.project_scope", decision.resource.project_scope)

            # Timestamp
            span.set_attribute(
                "rbac.evaluated_at",
                decision.evaluated_at.isoformat()
            )

            # Add event for decision
            span.add_event(
                "access.evaluated",
                attributes={
                    "decision": decision.decision.value,
                    "principal": decision.principal_id,
                    "resource": f"{decision.resource.resource_type.value}/{decision.resource.resource_id}",
                    "action": decision.action.value,
                }
            )

            # Set status based on decision
            if decision.decision == PolicyDecision.ALLOW:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        decision.denial_reason or "Access denied"
                    )
                )

            # Get trace ID for correlation
            span_context = span.get_span_context()
            trace_id = format(span_context.trace_id, "032x")

            # Update decision with trace_id
            decision.trace_id = trace_id

        return trace_id

    def emit_batch(self, decisions: list[AccessDecision]) -> list[str]:
        """
        Emit multiple decisions as a batch.

        Returns list of trace_ids.
        """
        return [self.emit_decision(d) for d in decisions]


class AuditingEnforcer:
    """
    Enforcer wrapper that automatically emits audit spans.

    Combines RBACEnforcer with RBACAuditEmitter for automatic
    audit trail generation.

    Example:
        enforcer = AuditingEnforcer()
        decision = enforcer.check_access(...)  # Automatically audited
    """

    def __init__(
        self,
        enforcer: Optional["RBACEnforcer"] = None,
        emitter: Optional[RBACAuditEmitter] = None,
        audit_allows: bool = True,
        audit_denies: bool = True,
    ):
        from contextcore.rbac.enforcer import get_enforcer

        self.enforcer = enforcer or get_enforcer()
        self.emitter = emitter or RBACAuditEmitter()
        self.audit_allows = audit_allows
        self.audit_denies = audit_denies

    def check_access(self, *args, **kwargs) -> AccessDecision:
        """Check access and emit audit span."""
        decision = self.enforcer.check_access(*args, **kwargs)
        self._maybe_emit(decision)
        return decision

    def require_access(self, *args, **kwargs) -> AccessDecision:
        """Require access (raises on deny) and emit audit span."""
        try:
            decision = self.enforcer.require_access(*args, **kwargs)
            self._maybe_emit(decision)
            return decision
        except Exception:
            # Decision was denied, get it for auditing
            decision = self.enforcer.check_access(*args, **kwargs)
            self._maybe_emit(decision)
            raise

    def _maybe_emit(self, decision: AccessDecision) -> None:
        """Emit audit span if configured."""
        if decision.decision == PolicyDecision.ALLOW and self.audit_allows:
            self.emitter.emit_decision(decision)
        elif decision.decision == PolicyDecision.DENY and self.audit_denies:
            self.emitter.emit_decision(decision)


# =============================================================================
# Global Auditing Enforcer
# =============================================================================

_auditing_enforcer: Optional[AuditingEnforcer] = None


def get_auditing_enforcer() -> AuditingEnforcer:
    """Get the default auditing enforcer."""
    global _auditing_enforcer

    if _auditing_enforcer is None:
        _auditing_enforcer = AuditingEnforcer()

    return _auditing_enforcer
