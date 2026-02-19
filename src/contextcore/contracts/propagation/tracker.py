"""
Propagation chain provenance tracker.

Tracks field provenance as context flows through workflow phases.
Provenance metadata is stored inside the context dict itself (under
``_cc_propagation``) so it travels with the context through the pipeline.

Usage::

    from contextcore.contracts.propagation.tracker import PropagationTracker

    tracker = PropagationTracker()
    tracker.stamp(context, "plan", "domain", "web_application")

    # Later, check chain integrity
    result = tracker.check_chain(chain_spec, context)
    assert result.status == ChainStatus.INTACT
"""

from __future__ import annotations

import hashlib
import logging
import platform
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from contextcore.contracts.propagation.schema import ContextContract, PropagationChainSpec
from contextcore.contracts.types import ChainStatus

logger = logging.getLogger(__name__)

# Key under which provenance metadata is stored in the context dict.
PROVENANCE_KEY = "_cc_propagation"


@dataclass
class FieldProvenance:
    """Provenance record for a single field at a point in the pipeline."""

    origin_phase: str
    set_at: str  # ISO 8601 timestamp
    value_hash: str  # sha256[:8] of repr(value)
    evaluated_by: Optional[str] = None  # evaluator ID
    evaluation_score: Optional[float] = None  # numeric score
    evaluation_timestamp: Optional[str] = None  # ISO 8601

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "origin_phase": self.origin_phase,
            "set_at": self.set_at,
            "value_hash": self.value_hash,
        }
        if self.evaluated_by is not None:
            d["evaluated_by"] = self.evaluated_by
        if self.evaluation_score is not None:
            d["evaluation_score"] = self.evaluation_score
        if self.evaluation_timestamp is not None:
            d["evaluation_timestamp"] = self.evaluation_timestamp
        return d


@dataclass
class EvaluationResult:
    """Result of an evaluation stamp on a field."""

    field_path: str
    evaluator: str
    score: Optional[float] = None
    timestamp: Optional[str] = None


@dataclass
class PropagationChainResult:
    """Result of checking a single propagation chain."""

    chain_id: str
    status: ChainStatus
    source_present: bool
    destination_present: bool
    waypoints_present: list[bool] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "status": self.status.value,
            "source_present": self.source_present,
            "destination_present": self.destination_present,
            "waypoints_present": self.waypoints_present,
            "message": self.message,
        }


def _value_hash(value: Any) -> str:
    """Compute a short hash of a value for provenance tracking."""
    return hashlib.sha256(repr(value).encode()).hexdigest()[:8]


def _timeout_handler(signum: int, frame: Any) -> None:
    """Signal handler that raises TimeoutError for verification expression timeouts."""
    raise TimeoutError("verification expression timed out")


def _resolve_field(context: dict[str, Any], field_path: str) -> tuple[bool, Any]:
    """Resolve a dot-path field from a context dict.

    Returns (present, value).  Supports simple dot-separated keys.
    Does NOT resolve into list items (``tasks[*].field``).
    """
    parts = field_path.split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


class PropagationTracker:
    """Tracks field provenance across workflow phases."""

    def stamp(
        self,
        context: dict[str, Any],
        phase: str,
        field_path: str,
        value: Any,
    ) -> None:
        """Record provenance for a field set during *phase*.

        Stores metadata under ``context[PROVENANCE_KEY][field_path]``.

        Args:
            context: The shared mutable workflow context dict.
            phase: Phase that is setting this field.
            field_path: Dot-path of the field being set.
            value: The value being set (used for hash, not stored).
        """
        provenance = context.setdefault(PROVENANCE_KEY, {})
        provenance[field_path] = FieldProvenance(
            origin_phase=phase,
            set_at=datetime.now(timezone.utc).isoformat(),
            value_hash=_value_hash(value),
        )
        logger.debug(
            "Stamped provenance: phase=%s field=%s hash=%s",
            phase,
            field_path,
            provenance[field_path].value_hash,
        )

    def get_provenance(
        self, context: dict[str, Any], field_path: str
    ) -> Optional[FieldProvenance]:
        """Retrieve provenance for a field, or None if not stamped."""
        provenance = context.get(PROVENANCE_KEY, {})
        return provenance.get(field_path)

    def stamp_evaluation(
        self,
        context: dict[str, Any],
        field_path: str,
        evaluator: str,
        score: float | None = None,
    ) -> EvaluationResult:
        """Record that a field has been evaluated.

        Updates the existing provenance record with evaluation metadata.
        If no provenance exists, creates a minimal one.
        """
        provenance = context.setdefault(PROVENANCE_KEY, {})
        existing = provenance.get(field_path)
        ts = datetime.now(timezone.utc).isoformat()

        if existing is not None:
            existing.evaluated_by = evaluator
            existing.evaluation_score = score
            existing.evaluation_timestamp = ts
        else:
            provenance[field_path] = FieldProvenance(
                origin_phase="unknown",
                set_at=ts,
                value_hash="",
                evaluated_by=evaluator,
                evaluation_score=score,
                evaluation_timestamp=ts,
            )

        logger.debug(
            "Stamped evaluation: field=%s evaluator=%s score=%s",
            field_path,
            evaluator,
            score,
        )
        return EvaluationResult(
            field_path=field_path,
            evaluator=evaluator,
            score=score,
            timestamp=ts,
        )

    def _evaluate_verification(
        self,
        chain_id: str,
        expression: str,
        context: dict[str, Any],
        source_value: Any,
        dest_value: Any,
    ) -> Optional[str]:
        """Evaluate a verification expression with a 1-second timeout.

        Args:
            chain_id: The chain identifier (used for log messages).
            expression: The verification expression string to evaluate.
            context: The workflow context dict.
            source_value: Resolved value of the source field.
            dest_value: Resolved value of the destination field.

        Returns:
            ``None`` if the verification passes, or an error message string
            describing why it failed.
        """
        try:
            # Set timeout (Unix only — signal.alarm not available on Windows)
            _old_handler = None
            if platform.system() != "Windows":
                _old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(1)

            try:
                result = eval(  # noqa: S307 - expressions are AST-validated at parse time
                    expression,
                    {"__builtins__": {}},
                    {"context": context, "source": source_value, "dest": dest_value},
                )
            finally:
                if _old_handler is not None:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, _old_handler)

            if not result:
                return f"Verification failed: {expression}"
        except TimeoutError:
            logger.warning(
                "Chain %s verification expression timed out",
                chain_id,
                exc_info=True,
            )
            return "Verification expression timed out after 1 second"
        except Exception as exc:
            logger.warning(
                "Chain %s verification expression error: %s",
                chain_id,
                exc,
            )
            return f"Verification error: {exc}"

        return None

    def check_chain(
        self,
        chain_spec: PropagationChainSpec,
        context: dict[str, Any],
    ) -> PropagationChainResult:
        """Check a single propagation chain against the current context.

        Args:
            chain_spec: The chain declaration from the contract.
            context: Current workflow context dict.

        Returns:
            A ``PropagationChainResult`` with the chain status.
        """
        source_present, source_value = _resolve_field(
            context, chain_spec.source.field
        )
        dest_present, dest_value = _resolve_field(
            context, chain_spec.destination.field
        )

        waypoints_present = []
        for wp in chain_spec.waypoints:
            wp_present, _ = _resolve_field(context, wp.field)
            waypoints_present.append(wp_present)

        # Determine chain status
        if not source_present:
            return PropagationChainResult(
                chain_id=chain_spec.chain_id,
                status=ChainStatus.BROKEN,
                source_present=False,
                destination_present=dest_present,
                waypoints_present=waypoints_present,
                message=f"Source field '{chain_spec.source.field}' absent "
                f"at phase '{chain_spec.source.phase}'",
            )

        if not dest_present:
            return PropagationChainResult(
                chain_id=chain_spec.chain_id,
                status=ChainStatus.BROKEN,
                source_present=True,
                destination_present=False,
                waypoints_present=waypoints_present,
                message=f"Destination field '{chain_spec.destination.field}' absent "
                f"at phase '{chain_spec.destination.phase}'",
            )

        # Check if destination has a default/degraded value
        if dest_value in (None, "", "unknown", [], {}):
            return PropagationChainResult(
                chain_id=chain_spec.chain_id,
                status=ChainStatus.DEGRADED,
                source_present=True,
                destination_present=True,
                waypoints_present=waypoints_present,
                message=f"Destination field '{chain_spec.destination.field}' has "
                f"default/empty value at phase '{chain_spec.destination.phase}'",
            )

        # Verification expression (optional)
        # Expressions are AST-validated at parse time (NFR-PCG-004).
        if chain_spec.verification:
            verification_message = self._evaluate_verification(
                chain_id=chain_spec.chain_id,
                expression=chain_spec.verification,
                context=context,
                source_value=source_value,
                dest_value=dest_value,
            )
            if verification_message is not None:
                return PropagationChainResult(
                    chain_id=chain_spec.chain_id,
                    status=ChainStatus.BROKEN,
                    source_present=True,
                    destination_present=True,
                    waypoints_present=waypoints_present,
                    message=verification_message,
                )

        return PropagationChainResult(
            chain_id=chain_spec.chain_id,
            status=ChainStatus.INTACT,
            source_present=True,
            destination_present=True,
            waypoints_present=waypoints_present,
            message="Chain intact",
        )

    def validate_all_chains(
        self,
        contract: ContextContract,
        context: dict[str, Any],
    ) -> list[PropagationChainResult]:
        """Validate all propagation chains declared in a contract.

        Args:
            contract: The loaded context contract.
            context: Current workflow context dict.

        Returns:
            List of ``PropagationChainResult`` for each chain.
        """
        results = []
        for chain_spec in contract.propagation_chains:
            result = self.check_chain(chain_spec, context)
            results.append(result)
            if result.status != ChainStatus.INTACT:
                logger.warning(
                    "Chain %s: %s — %s",
                    result.chain_id,
                    result.status.value,
                    result.message,
                )
        return results
