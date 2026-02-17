"""
Transformation record tracker for data lineage.

Records individual field transformations as context flows through pipeline
phases.  Transformation metadata is stored inside the context dict itself
(under ``_cc_lineage``) so it travels with the context through the pipeline.

Hash computation uses ``sha256[:8]`` of ``repr(value)`` — the same scheme
used by ``propagation/tracker.py``.

Usage::

    from contextcore.contracts.lineage.tracker import LineageTracker
    from contextcore.contracts.types import TransformOp

    tracker = LineageTracker()
    tracker.record_transformation(
        context, "domain", "classify",
        TransformOp.CLASSIFY, raw_text, "web_application",
    )
    history = tracker.get_history(context, "domain")
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from contextcore.contracts.types import TransformOp

logger = logging.getLogger(__name__)


def _value_hash(value: Any) -> str:
    """Compute a short hash of a value for lineage tracking."""
    return hashlib.sha256(repr(value).encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Transformation record
# ---------------------------------------------------------------------------


@dataclass
class TransformationRecord:
    """Record of a single transformation applied to a field."""

    phase: str
    operation: TransformOp
    input_hash: str
    output_hash: str
    timestamp: str  # ISO 8601

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "phase": self.phase,
            "operation": self.operation.value,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Lineage tracker
# ---------------------------------------------------------------------------


class LineageTracker:
    """Tracks field transformation history across pipeline phases.

    Stores records under ``context[LINEAGE_KEY][field]`` as a list of
    ``TransformationRecord`` instances.
    """

    LINEAGE_KEY = "_cc_lineage"

    def record_transformation(
        self,
        context: dict[str, Any],
        field: str,
        phase: str,
        operation: TransformOp,
        input_value: Any,
        output_value: Any,
    ) -> TransformationRecord:
        """Append a transformation record for *field* at *phase*.

        Args:
            context: The shared mutable workflow context dict.
            field: Dot-path of the field being transformed.
            phase: Pipeline phase performing the transformation.
            operation: Type of transformation applied.
            input_value: Value before transformation (used for hash).
            output_value: Value after transformation (used for hash).

        Returns:
            The newly created ``TransformationRecord``.
        """
        lineage_store = context.setdefault(self.LINEAGE_KEY, {})
        field_history: list[TransformationRecord] = lineage_store.setdefault(
            field, []
        )

        record = TransformationRecord(
            phase=phase,
            operation=operation,
            input_hash=_value_hash(input_value),
            output_hash=_value_hash(output_value),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        field_history.append(record)

        logger.debug(
            "Recorded transformation: field=%s phase=%s op=%s "
            "in_hash=%s out_hash=%s",
            field,
            phase,
            operation.value,
            record.input_hash,
            record.output_hash,
        )
        return record

    def get_history(
        self,
        context: dict[str, Any],
        field: str,
    ) -> list[TransformationRecord]:
        """Retrieve the full transformation history for a field.

        Args:
            context: The shared workflow context dict.
            field: Dot-path of the field.

        Returns:
            List of ``TransformationRecord`` in chronological order,
            or an empty list if no history exists.
        """
        lineage_store = context.get(self.LINEAGE_KEY, {})
        return lineage_store.get(field, [])

    def get_latest(
        self,
        context: dict[str, Any],
        field: str,
    ) -> Optional[TransformationRecord]:
        """Retrieve the most recent transformation record for a field.

        Args:
            context: The shared workflow context dict.
            field: Dot-path of the field.

        Returns:
            The latest ``TransformationRecord``, or ``None`` if no
            history exists.
        """
        history = self.get_history(context, field)
        return history[-1] if history else None
