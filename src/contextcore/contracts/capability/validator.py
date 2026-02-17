"""
Capability boundary validator for capability propagation contracts.

Validates that a workflow context dict satisfies the entry/exit capability
requirements declared in a ``CapabilityContract``.  Enforces the core
attenuation invariant: capabilities can only narrow, never widen.

Severity behavior:
    - ``BLOCKING`` → sets ``passed=False``, caller should halt the phase.
    - ``WARNING``  → records the issue but continues.
    - ``ADVISORY`` → logs only, no impact on pass/fail.

Usage::

    from contextcore.contracts.capability.validator import CapabilityValidator

    validator = CapabilityValidator(contract)
    result = validator.validate_entry("implement", context)
    if not result.passed:
        raise PhaseCapabilityError(...)
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.capability.schema import CapabilityContract
from contextcore.contracts.capability.tracker import PROVENANCE_KEY, CapabilityProvenance
from contextcore.contracts.types import ConstraintSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class CapabilityValidationResult(BaseModel):
    """Result of validating capabilities at a phase boundary."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    phase: str
    direction: str = Field(description="entry or exit")
    missing_capabilities: list[str] = Field(default_factory=list)
    escalation_attempts: list[str] = Field(default_factory=list)
    message: str = ""


# ---------------------------------------------------------------------------
# Scope hierarchy helpers
# ---------------------------------------------------------------------------


# Well-known scope hierarchy: broader scopes first.
# A scope appearing later in this list is strictly narrower.
_SCOPE_HIERARCHY: list[str] = [
    "admin",
    "read-write",
    "write",
    "read-only",
    "read",
    "none",
]


def _scope_rank(scope: str) -> int:
    """Return the rank of a scope (lower = broader).

    If the scope is not in the known hierarchy, return -1 to indicate
    that no automatic escalation detection is possible.
    """
    try:
        return _SCOPE_HIERARCHY.index(scope)
    except ValueError:
        return -1


def _is_escalation(old_scope: str, new_scope: str) -> bool:
    """Return True if moving from *old_scope* to *new_scope* is an escalation.

    Escalation means the new scope is broader (lower rank) than the old one.
    If either scope is unknown, we cannot determine escalation automatically,
    so we conservatively return ``False`` (caller should compare explicitly).
    """
    old_rank = _scope_rank(old_scope)
    new_rank = _scope_rank(new_scope)
    if old_rank < 0 or new_rank < 0:
        return False
    return new_rank < old_rank


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class CapabilityValidator:
    """Validates context dicts against capability propagation contracts.

    Instantiated with a contract; methods check a single phase at a time.
    """

    def __init__(self, contract: CapabilityContract) -> None:
        self._contract = contract
        self._capability_defs = {
            cap.name: cap for cap in contract.capabilities
        }

    def validate_entry(
        self,
        phase: str,
        context: dict[str, Any],
    ) -> CapabilityValidationResult:
        """Validate required capabilities are present for phase entry.

        Args:
            phase: Phase name (e.g. ``"implement"``).
            context: Shared workflow context dict.

        Returns:
            Validation result indicating pass/fail and details.
        """
        phase_contract = self._contract.phases.get(phase)
        if phase_contract is None:
            return CapabilityValidationResult(
                passed=True,
                phase=phase,
                direction="entry",
                message=f"No capability contract for phase '{phase}'",
            )

        store = context.get(PROVENANCE_KEY, {})
        missing: list[str] = []

        for required_cap in phase_contract.requires:
            if required_cap not in store:
                missing.append(required_cap)
                logger.warning(
                    "Entry validation: phase=%s missing required capability '%s'",
                    phase,
                    required_cap,
                )

        if missing:
            return CapabilityValidationResult(
                passed=False,
                phase=phase,
                direction="entry",
                missing_capabilities=missing,
                message=(
                    f"Phase '{phase}' requires capabilities {missing} "
                    f"which are not present in context"
                ),
            )

        return CapabilityValidationResult(
            passed=True,
            phase=phase,
            direction="entry",
            message=f"All required capabilities present for phase '{phase}'",
        )

    def validate_exit(
        self,
        phase: str,
        context: dict[str, Any],
    ) -> CapabilityValidationResult:
        """Validate provided capabilities are present after phase exit.

        Also checks that no escalation has occurred: if a capability was
        previously attenuated, its scope must not be broader than before.

        Args:
            phase: Phase name.
            context: Shared workflow context dict (after phase execution).

        Returns:
            Validation result indicating pass/fail and details.
        """
        phase_contract = self._contract.phases.get(phase)
        if phase_contract is None:
            return CapabilityValidationResult(
                passed=True,
                phase=phase,
                direction="exit",
                message=f"No capability contract for phase '{phase}'",
            )

        store = context.get(PROVENANCE_KEY, {})
        missing: list[str] = []

        for provided_cap in phase_contract.provides:
            if provided_cap not in store:
                missing.append(provided_cap)
                logger.warning(
                    "Exit validation: phase=%s missing provided capability '%s'",
                    phase,
                    provided_cap,
                )

        # Check for escalation attempts
        escalations = self._check_escalation(context, phase)

        passed = len(missing) == 0 and len(escalations) == 0
        parts: list[str] = []
        if missing:
            parts.append(
                f"Phase '{phase}' should provide capabilities {missing} "
                f"which are not present"
            )
        if escalations:
            parts.append(
                f"Escalation detected for capabilities {escalations}"
            )

        message = "; ".join(parts) if parts else (
            f"All provided capabilities present for phase '{phase}', "
            f"no escalation detected"
        )

        if not passed:
            logger.warning(
                "Exit validation failed: phase=%s missing=%s escalations=%s",
                phase,
                missing,
                escalations,
            )

        return CapabilityValidationResult(
            passed=passed,
            phase=phase,
            direction="exit",
            missing_capabilities=missing,
            escalation_attempts=escalations,
            message=message,
        )

    def _check_escalation(
        self,
        context: dict[str, Any],
        phase: str,
    ) -> list[str]:
        """Detect scope widening (escalation) for capabilities in a phase.

        Examines the attenuation history of each capability in the provenance
        store.  If the current scope is broader than the scope before the
        most recent attenuation, that is an escalation.

        Also checks non-attenuable capabilities: if the definition says
        ``attenuable=False`` but an attenuation record exists, that counts
        as a violation.

        Args:
            context: Shared workflow context dict.
            phase: Phase name (for filtering phase-local attenuations).

        Returns:
            List of capability names that attempted escalation.
        """
        store = context.get(PROVENANCE_KEY, {})
        escalations: list[str] = []

        for cap_name, provenance in store.items():
            if not isinstance(provenance, CapabilityProvenance):
                continue

            cap_def = self._capability_defs.get(cap_name)

            # Check non-attenuable capabilities for any attenuation
            if cap_def is not None and not cap_def.attenuable:
                if provenance.attenuations:
                    escalations.append(cap_name)
                    logger.warning(
                        "Capability '%s' is non-attenuable but has %d attenuation(s)",
                        cap_name,
                        len(provenance.attenuations),
                    )
                    continue

            # Check for scope widening in attenuation history
            for att in provenance.attenuations:
                from_scope = att.get("from_scope", "")
                to_scope = att.get("to_scope", "")
                if _is_escalation(from_scope, to_scope):
                    escalations.append(cap_name)
                    logger.warning(
                        "Escalation detected: capability='%s' "
                        "from_scope='%s' -> to_scope='%s' at phase='%s'",
                        cap_name,
                        from_scope,
                        to_scope,
                        att.get("phase", "unknown"),
                    )
                    break

        return escalations
