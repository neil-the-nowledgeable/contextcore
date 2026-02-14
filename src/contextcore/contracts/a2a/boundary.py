"""
A2A boundary enforcement for outbound and inbound handoffs.

Ensures that every payload crossing an agent boundary is validated against its
contract schema **before** it is sent (outbound) or accepted (inbound).
Invalid payloads are rejected deterministically, and structured failure events
are emitted for observability.

Day 3 spec: "No unvalidated handoff can enter the execution path."

Usage::

    from contextcore.contracts.a2a.boundary import validate_outbound, validate_inbound

    # Before sending a handoff
    validated = validate_outbound("HandoffContract", payload)  # raises on failure

    # On receiving a handoff
    validated = validate_inbound("HandoffContract", payload)   # raises on failure
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from contextcore.contracts.a2a.validator import (
    A2AValidator,
    ValidationErrorEnvelope,
    ValidationReport,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class BoundaryEnforcementError(Exception):
    """
    Raised when a payload fails boundary validation.

    Attributes:
        direction: ``"outbound"`` or ``"inbound"``.
        contract_name: Contract that was violated.
        report: Full :class:`ValidationReport` with structured errors.
    """

    def __init__(
        self,
        direction: str,
        contract_name: str,
        report: ValidationReport,
    ) -> None:
        self.direction = direction
        self.contract_name = contract_name
        self.report = report
        error_summaries = "; ".join(e.message for e in report.errors[:3])
        if len(report.errors) > 3:
            error_summaries += f" (and {len(report.errors) - 3} more)"
        super().__init__(
            f"{direction.upper()} boundary validation failed for {contract_name}: "
            f"{error_summaries}"
        )

    def to_failure_event(self) -> dict[str, Any]:
        """
        Serialize to a structured failure event suitable for span events / logs.

        The event follows ContextCore telemetry conventions so it can be
        queried in Loki/Tempo dashboards.
        """
        return {
            "event_type": f"handoff.validation.{self.direction}.failed",
            "contract_name": self.contract_name,
            "direction": self.direction,
            "error_count": len(self.report.errors),
            "errors": [e.to_dict() for e in self.report.errors],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_validator = A2AValidator()


def _emit_failure_event(event: dict[str, Any]) -> None:
    """
    Emit a structured failure event.

    Currently logs at WARNING level.  When an OTel span is active, callers
    should also attach this as a span event.
    """
    logger.warning(
        "Boundary enforcement failure: %s %s — %d error(s)",
        event.get("direction"),
        event.get("contract_name"),
        event.get("error_count"),
    )


def _enforce(
    direction: str,
    contract_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate *payload* and raise :class:`BoundaryEnforcementError` on failure.

    On success, returns the original payload (pass-through).
    """
    report = _validator.validate(contract_name, payload)

    if not report.is_valid:
        error = BoundaryEnforcementError(
            direction=direction,
            contract_name=contract_name,
            report=report,
        )
        _emit_failure_event(error.to_failure_event())
        raise error

    logger.debug(
        "%s boundary validation passed for %s",
        direction.capitalize(),
        contract_name,
    )
    return payload


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_outbound(contract_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Validate a payload **before** writing/sending an outbound handoff.

    Args:
        contract_name: Contract to validate against (e.g. ``"HandoffContract"``).
        payload: Raw dict to validate.

    Returns:
        The original *payload* if validation succeeds.

    Raises:
        BoundaryEnforcementError: If the payload fails schema validation.
    """
    return _enforce("outbound", contract_name, payload)


def validate_inbound(contract_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Validate a payload **on receipt** before accepting an inbound handoff.

    Args:
        contract_name: Contract to validate against.
        payload: Raw dict to validate.

    Returns:
        The original *payload* if validation succeeds.

    Raises:
        BoundaryEnforcementError: If the payload fails schema validation.
    """
    return _enforce("inbound", contract_name, payload)
