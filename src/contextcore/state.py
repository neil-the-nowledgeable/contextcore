"""
State persistence for long-running task spans.

Tasks can run for days or weeks, so we need to persist span state across
process restarts. This module handles:

1. Serializing active span context to disk
2. Reconstructing spans on startup
3. Managing span lifecycle across restarts

State is stored as JSON files in ~/.contextcore/state/<project>/
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SpanState:
    """Serializable span state."""
    task_id: str
    span_name: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    start_time: str  # ISO format
    attributes: Dict[str, Any]
    events: List[Dict[str, Any]]
    status: str  # "OK", "ERROR", "UNSET"
    status_description: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpanState":
        return cls(**data)


class StateManager:
    """
    Manage persistent state for task spans.

    Stores span state as JSON files that can survive process restarts.
    On startup, reconstructs span contexts for linking.
    """

    def __init__(self, project: str, state_dir: Optional[str] = None):
        """
        Initialize state manager.

        Args:
            project: Project identifier
            state_dir: Base directory for state files
        """
        self.project = project
        self.base_dir = Path(state_dir or os.path.expanduser("~/.contextcore/state"))
        self.project_dir = self.base_dir / project
        self.project_dir.mkdir(parents=True, exist_ok=True)

        self._active_spans: Dict[str, SpanState] = {}
        self._completed_spans: Dict[str, SpanState] = {}

    def save_span(self, state: SpanState) -> None:
        """
        Save span state to disk.

        Args:
            state: SpanState to persist
        """
        file_path = self.project_dir / f"{state.task_id}.json"
        try:
            with open(file_path, 'w') as f:
                json.dump(state.to_dict(), f, indent=2)
            self._active_spans[state.task_id] = state
            logger.debug(f"Saved span state: {state.task_id}")
        except Exception as e:
            logger.error(f"Failed to save span state {state.task_id}: {e}")

    def load_span(self, task_id: str) -> Optional[SpanState]:
        """
        Load span state from disk.

        Args:
            task_id: Task identifier

        Returns:
            SpanState or None if not found
        """
        if task_id in self._active_spans:
            return self._active_spans[task_id]

        file_path = self.project_dir / f"{task_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path) as f:
                data = json.load(f)
            state = SpanState.from_dict(data)
            self._active_spans[task_id] = state
            return state
        except Exception as e:
            logger.error(f"Failed to load span state {task_id}: {e}")
            return None

    def remove_span(self, task_id: str) -> None:
        """
        Remove span state (called when span completes).

        Moves to completed directory for historical queries.

        Args:
            task_id: Task identifier
        """
        file_path = self.project_dir / f"{task_id}.json"

        # Move to completed
        completed_dir = self.project_dir / "completed"
        completed_dir.mkdir(exist_ok=True)

        if file_path.exists():
            try:
                # Load, add end time, save to completed
                with open(file_path) as f:
                    data = json.load(f)
                data["end_time"] = datetime.now(timezone.utc).isoformat()

                completed_path = completed_dir / f"{task_id}.json"
                with open(completed_path, 'w') as f:
                    json.dump(data, f, indent=2)

                # Remove active file
                file_path.unlink()
                logger.debug(f"Moved span to completed: {task_id}")

            except Exception as e:
                logger.error(f"Failed to archive span {task_id}: {e}")

        # Remove from cache
        self._active_spans.pop(task_id, None)

    def get_active_spans(self) -> Dict[str, SpanState]:
        """
        Get all active (incomplete) spans.

        Returns:
            Dict mapping task_id to SpanState
        """
        # Load all JSON files in project directory
        for file_path in self.project_dir.glob("*.json"):
            task_id = file_path.stem
            if task_id not in self._active_spans:
                self.load_span(task_id)

        return self._active_spans.copy()

    def get_completed_spans(
        self,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SpanState]:
        """
        Get completed spans for analysis.

        Args:
            since: Only return spans completed after this time
            limit: Maximum number to return

        Returns:
            List of completed SpanState objects
        """
        completed_dir = self.project_dir / "completed"
        if not completed_dir.exists():
            return []

        spans = []
        for file_path in sorted(completed_dir.glob("*.json"), reverse=True):
            if len(spans) >= limit:
                break

            try:
                with open(file_path) as f:
                    data = json.load(f)

                if since:
                    end_time = datetime.fromisoformat(data.get("end_time", ""))
                    if end_time < since:
                        continue

                spans.append(SpanState.from_dict(data))
            except Exception as e:
                logger.warning(f"Failed to load completed span {file_path}: {e}")

        return spans

    def add_event(self, task_id: str, event_name: str, attributes: Dict[str, Any]) -> None:
        """
        Add an event to a span's state.

        Args:
            task_id: Task identifier
            event_name: Event name
            attributes: Event attributes
        """
        state = self.load_span(task_id)
        if not state:
            logger.warning(f"Cannot add event to unknown span: {task_id}")
            return

        event = {
            "name": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attributes": attributes,
        }
        state.events.append(event)
        self.save_span(state)

    def update_attribute(self, task_id: str, key: str, value: Any) -> None:
        """
        Update a span attribute.

        Args:
            task_id: Task identifier
            key: Attribute key
            value: Attribute value
        """
        state = self.load_span(task_id)
        if not state:
            logger.warning(f"Cannot update attribute on unknown span: {task_id}")
            return

        state.attributes[key] = value
        self.save_span(state)

    def update_status(self, task_id: str, status: str, description: Optional[str] = None) -> None:
        """
        Update span status.

        Args:
            task_id: Task identifier
            status: New status ("OK", "ERROR", "UNSET")
            description: Status description
        """
        state = self.load_span(task_id)
        if not state:
            return

        state.status = status
        state.status_description = description
        self.save_span(state)


def format_trace_id(trace_id: int) -> str:
    """Format trace ID as hex string."""
    return format(trace_id, '032x')


def format_span_id(span_id: int) -> str:
    """Format span ID as hex string."""
    return format(span_id, '016x')


def parse_trace_id(trace_id_hex: str) -> int:
    """Parse hex trace ID to int."""
    return int(trace_id_hex, 16)


def parse_span_id(span_id_hex: str) -> int:
    """Parse hex span ID to int."""
    return int(span_id_hex, 16)
