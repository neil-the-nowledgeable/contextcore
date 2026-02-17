"""
Lamport logical clock and causal provenance for pipeline events.

Provides a ``CausalClock`` that implements Lamport's logical clock
algorithm for establishing happens-before relationships between
pipeline events.  ``CausalProvenance`` captures the full causal
context of an event for downstream validation.

Usage::

    from contextcore.contracts.ordering.clock import CausalClock, CausalProvenance

    clock = CausalClock()
    ts = clock.tick()  # 1
    prov = CausalProvenance(
        phase="plan", event="started", logical_ts=ts,
        wall_clock="2026-02-17T12:00:00Z", causal_deps=[],
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class CausalClock:
    """Lamport logical clock for tracking happens-before relationships.

    Each ``tick()`` increments the local counter and returns the new value.
    ``receive(remote_ts)`` merges a remote timestamp using
    ``max(local, remote) + 1``, ensuring monotonicity across processes.
    """

    def __init__(self) -> None:
        self._counter: int = 0

    def tick(self) -> int:
        """Increment the clock and return the new timestamp."""
        self._counter += 1
        return self._counter

    def receive(self, remote_ts: int) -> int:
        """Merge a remote timestamp and return the new local timestamp.

        Args:
            remote_ts: Timestamp received from another process/event.

        Returns:
            New local timestamp after merging.
        """
        self._counter = max(self._counter, remote_ts) + 1
        return self._counter

    def current(self) -> int:
        """Return the current timestamp without incrementing."""
        return self._counter


@dataclass
class CausalProvenance:
    """Provenance record for a single pipeline event with causal metadata.

    Captures both the logical timestamp (for ordering validation) and
    wall-clock time (for human-readable diagnostics).
    """

    phase: str
    event: str
    logical_ts: int
    wall_clock: str  # ISO 8601 timestamp
    causal_deps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for JSON/YAML emission."""
        return {
            "phase": self.phase,
            "event": self.event,
            "logical_ts": self.logical_ts,
            "wall_clock": self.wall_clock,
            "causal_deps": list(self.causal_deps),
        }

    @staticmethod
    def now_iso() -> str:
        """Return the current UTC time as an ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()
