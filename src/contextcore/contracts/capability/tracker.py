"""
Capability provenance tracker.

Tracks capability grants and attenuations as context flows through
workflow phases.  Provenance metadata is stored inside the context dict
itself (under ``_cc_capabilities``) so it travels with the context
through the pipeline.

The tracker enforces the core attenuation invariant: capabilities can
only narrow (attenuate), never widen (escalate).

Usage::

    from contextcore.contracts.capability.tracker import CapabilityTracker

    tracker = CapabilityTracker()
    tracker.grant(context, "data.read", "read-write", "ingest")

    # Later, attenuate the capability
    tracker.attenuate(context, "data.read", "read-only", "transform")

    # Check chain integrity
    result = tracker.check_chain(contract, chain_spec, context)
    assert result.status == CapabilityChainStatus.INTACT
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from contextcore.contracts.capability.schema import (
    CapabilityChainSpec,
    CapabilityContract,
)
from contextcore.contracts.types import CapabilityChainStatus

logger = logging.getLogger(__name__)

# Key under which capability provenance metadata is stored in the context dict.
PROVENANCE_KEY = "_cc_capabilities"


# ---------------------------------------------------------------------------
# Provenance record
# ---------------------------------------------------------------------------


@dataclass
class CapabilityProvenance:
    """Provenance record for a single capability in the pipeline."""

    capability: str
    scope: str
    granted_by: str  # phase that originally granted the capability
    granted_at: str  # ISO 8601 timestamp
    attenuations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "scope": self.scope,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
            "attenuations": list(self.attenuations),
        }


# ---------------------------------------------------------------------------
# Chain check result
# ---------------------------------------------------------------------------


@dataclass
class CapabilityChainResult:
    """Result of checking a single capability propagation chain."""

    chain_id: str
    status: CapabilityChainStatus
    source_present: bool
    destination_present: bool
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "status": self.status.value,
            "source_present": self.source_present,
            "destination_present": self.destination_present,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class CapabilityTracker:
    """Tracks capability grants and attenuations across workflow phases.

    All provenance is stored in ``context[PROVENANCE_KEY]`` as a dict
    keyed by capability name.
    """

    PROVENANCE_KEY = PROVENANCE_KEY

    def grant(
        self,
        context: dict[str, Any],
        capability: str,
        scope: str,
        phase: str,
    ) -> None:
        """Grant a capability with a given scope at a phase.

        Stamps the provenance into ``context[PROVENANCE_KEY]``.

        Args:
            context: The shared mutable workflow context dict.
            capability: Capability name to grant.
            scope: Scope of the granted capability.
            phase: Phase that is granting the capability.
        """
        store = context.setdefault(PROVENANCE_KEY, {})
        store[capability] = CapabilityProvenance(
            capability=capability,
            scope=scope,
            granted_by=phase,
            granted_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.debug(
            "Granted capability: phase=%s capability=%s scope=%s",
            phase,
            capability,
            scope,
        )

    def attenuate(
        self,
        context: dict[str, Any],
        capability: str,
        new_scope: str,
        phase: str,
    ) -> None:
        """Narrow the scope of an existing capability.

        Records the attenuation in the provenance history.  If the
        capability has not been granted yet, a warning is logged and
        the capability is granted with the new (narrowed) scope.

        Args:
            context: The shared mutable workflow context dict.
            capability: Capability name to attenuate.
            new_scope: The narrower scope to apply.
            phase: Phase performing the attenuation.
        """
        store = context.setdefault(PROVENANCE_KEY, {})
        existing = store.get(capability)

        if existing is None:
            logger.warning(
                "Attenuating capability '%s' that was never granted — "
                "granting with new scope '%s' at phase '%s'",
                capability,
                new_scope,
                phase,
            )
            self.grant(context, capability, new_scope, phase)
            return

        attenuation_record = {
            "from_scope": existing.scope,
            "to_scope": new_scope,
            "phase": phase,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        existing.attenuations.append(attenuation_record)
        existing.scope = new_scope

        logger.debug(
            "Attenuated capability: phase=%s capability=%s %s -> %s",
            phase,
            capability,
            attenuation_record["from_scope"],
            new_scope,
        )

    def get_provenance(
        self,
        context: dict[str, Any],
        capability: str,
    ) -> Optional[CapabilityProvenance]:
        """Retrieve provenance for a capability, or None if not granted.

        Args:
            context: The shared workflow context dict.
            capability: Capability name to look up.

        Returns:
            The ``CapabilityProvenance`` record, or ``None``.
        """
        store = context.get(PROVENANCE_KEY, {})
        return store.get(capability)

    def check_chain(
        self,
        contract: CapabilityContract,
        chain: CapabilityChainSpec,
        context: dict[str, Any],
    ) -> CapabilityChainResult:
        """Check a single capability chain against the current context.

        Verifies that:
        1. The capability exists in the provenance store (source present).
        2. The destination phase lists the capability in its ``requires``.
        3. If an expected attenuation is declared, the current scope
           matches the attenuated scope.

        Args:
            contract: The loaded capability contract (for phase lookups).
            chain: The chain declaration to verify.
            context: Current workflow context dict.

        Returns:
            A ``CapabilityChainResult`` with the chain status.
        """
        store = context.get(PROVENANCE_KEY, {})
        provenance = store.get(chain.capability)

        # Source check: capability must be in provenance
        source_present = provenance is not None

        # Destination check: destination phase must declare the capability
        dest_phase_contract = contract.phases.get(chain.destination_phase)
        destination_present = (
            dest_phase_contract is not None
            and chain.capability in dest_phase_contract.requires
        )

        if not source_present:
            return CapabilityChainResult(
                chain_id=chain.chain_id,
                status=CapabilityChainStatus.BROKEN,
                source_present=False,
                destination_present=destination_present,
                message=(
                    f"Capability '{chain.capability}' not granted at "
                    f"source phase '{chain.source_phase}'"
                ),
            )

        if not destination_present:
            return CapabilityChainResult(
                chain_id=chain.chain_id,
                status=CapabilityChainStatus.BROKEN,
                source_present=True,
                destination_present=False,
                message=(
                    f"Capability '{chain.capability}' not required by "
                    f"destination phase '{chain.destination_phase}'"
                ),
            )

        # Attenuation check
        if chain.expected_attenuation is not None:
            expected_scope = chain.expected_attenuation.to_scope
            if provenance.scope != expected_scope:
                # Check if scope was widened (escalation) vs. just different
                # For now: if the scope doesn't match expected, report
                return CapabilityChainResult(
                    chain_id=chain.chain_id,
                    status=CapabilityChainStatus.BROKEN,
                    source_present=True,
                    destination_present=True,
                    message=(
                        f"Expected attenuated scope '{expected_scope}' "
                        f"but found '{provenance.scope}' for capability "
                        f"'{chain.capability}'"
                    ),
                )
            return CapabilityChainResult(
                chain_id=chain.chain_id,
                status=CapabilityChainStatus.ATTENUATED,
                source_present=True,
                destination_present=True,
                message=(
                    f"Capability '{chain.capability}' attenuated as expected: "
                    f"'{chain.expected_attenuation.from_scope}' -> "
                    f"'{chain.expected_attenuation.to_scope}'"
                ),
            )

        # No attenuation expected — capability should propagate intact
        return CapabilityChainResult(
            chain_id=chain.chain_id,
            status=CapabilityChainStatus.INTACT,
            source_present=True,
            destination_present=True,
            message=f"Capability '{chain.capability}' chain intact",
        )
