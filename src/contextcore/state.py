"""
State persistence for long-running task spans.

Tasks can run for days or weeks, so we need to persist span state across
process restarts. This module handles:

1. Serializing active span context to disk
2. Reconstructing spans on startup
3. Managing span lifecycle across restarts

State is stored as JSON files in ~/.contextcore/state/<project>/

Thread and process safety is achieved through file locking.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, IO

logger = logging.getLogger(__name__)


# Cross-platform file locking
if sys.platform == "win32":
    import msvcrt

    def _lock_file(f: IO, exclusive: bool = True) -> None:
        """Lock file on Windows."""
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK, 1)

    def _unlock_file(f: IO) -> None:
        """Unlock file on Windows."""
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_file(f: IO, exclusive: bool = True) -> None:
        """Lock file on Unix."""
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)

    def _unlock_file(f: IO) -> None:
        """Unlock file on Unix."""
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def file_lock(path: Path, exclusive: bool = True) -> Generator[IO, None, None]:
    """
    Context manager for file locking.

    Creates a lock file adjacent to the target file and acquires a lock on it.
    This prevents race conditions when multiple processes access the same state.

    Args:
        path: Path to the file being protected
        exclusive: If True, acquire exclusive (write) lock; otherwise shared (read) lock

    Yields:
        The lock file handle (for context manager protocol)

    Example:
        with file_lock(state_file):
            with open(state_file, 'w') as f:
                json.dump(data, f)
    """
    lock_path = path.with_suffix(path.suffix + ".lock")

    # Create lock file if it doesn't exist
    lock_path.touch(exist_ok=True)

    lock_file = open(lock_path, "r+" if lock_path.exists() else "w+")
    try:
        _lock_file(lock_file, exclusive)
        yield lock_file
    finally:
        try:
            _unlock_file(lock_file)
        except Exception:
            pass  # Ignore unlock errors
        finally:
            lock_file.close()

# Fallback directory if default state dir is not writable
_FALLBACK_STATE_DIR = Path(tempfile.gettempdir()) / "contextcore" / "state"

# Schema versioning for state files
# Increment when making breaking changes to SpanState structure
SCHEMA_VERSION = 2

# Migration history:
# Version 1 (implicit): Original schema without version field
# Version 2: Added schema_version, project_id, created_at fields


@dataclass
class SpanState:
    """
    Serializable span state with schema versioning.

    Supports forward migration from older schema versions to ensure
    state files created by older versions can still be loaded.
    """
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
    end_time: Optional[str] = None  # ISO format, set when completed
    # New fields added in schema version 2
    schema_version: int = SCHEMA_VERSION
    project_id: Optional[str] = None  # Project identifier for cross-project queries
    created_at: Optional[str] = None  # When state was first persisted (ISO format)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dictionary, always at current schema version."""
        data = asdict(self)
        data["schema_version"] = SCHEMA_VERSION
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpanState":
        """
        Deserialize state from dictionary, migrating if needed.

        Automatically migrates data from older schema versions to current.
        """
        version = data.get("schema_version", 1)

        if version < SCHEMA_VERSION:
            data = cls._migrate(data, version)

        # Remove any unknown fields that may have been added in future versions
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}

        return cls(**filtered_data)

    @classmethod
    def _migrate(cls, data: Dict[str, Any], from_version: int) -> Dict[str, Any]:
        """
        Migrate state data from older schema version to current.

        Args:
            data: State dictionary at from_version
            from_version: Schema version of the data

        Returns:
            Migrated data at current schema version
        """
        # Apply migrations sequentially
        if from_version < 2:
            data = cls._migrate_v1_to_v2(data)

        # Add additional migrations here as schema evolves:
        # if from_version < 3:
        #     data = cls._migrate_v2_to_v3(data)

        data["schema_version"] = SCHEMA_VERSION
        return data

    @classmethod
    def _migrate_v1_to_v2(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate from schema v1 (no version field) to v2.

        Adds:
        - schema_version: 2
        - project_id: extracted from attributes or None
        - created_at: derived from start_time or current time
        """
        # Extract project_id from attributes if available
        attributes = data.get("attributes", {})
        project_id = attributes.get("project.id") or attributes.get("project.name")
        data["project_id"] = project_id

        # Set created_at to start_time (best approximation for existing data)
        data["created_at"] = data.get("start_time")

        logger.debug(f"Migrated state for {data.get('task_id')} from v1 to v2")
        return data


class StateManager:
    """
    Manage persistent state for task spans.

    Stores span state as JSON files that can survive process restarts.
    On startup, reconstructs span contexts for linking.

    If the default state directory is not writable (e.g., in containerized
    environments), automatically falls back to a temp directory.
    """

    def __init__(self, project: str, state_dir: Optional[str] = None):
        """
        Initialize state manager.

        Args:
            project: Project identifier
            state_dir: Base directory for state files
        """
        self.project = project
        self._using_fallback = False

        # Try primary state directory first
        primary_dir = Path(state_dir or os.path.expanduser("~/.contextcore/state"))
        self.base_dir, self.project_dir = self._init_state_directory(primary_dir, project)

        self._active_spans: Dict[str, SpanState] = {}
        self._completed_spans: Dict[str, SpanState] = {}

    def _init_state_directory(self, base_dir: Path, project: str) -> tuple[Path, Path]:
        """
        Initialize and verify state directory is writable.

        Falls back to temp directory if primary is not writable.

        Args:
            base_dir: Preferred base directory
            project: Project identifier

        Returns:
            Tuple of (base_dir, project_dir) that are verified writable
        """
        project_dir = base_dir / project

        try:
            # Attempt to create directory
            project_dir.mkdir(parents=True, exist_ok=True)

            # Verify write permission with a test file
            test_file = project_dir / ".write_test"
            test_file.touch()
            test_file.unlink()

            logger.debug(f"Using state directory: {project_dir}")
            return base_dir, project_dir

        except PermissionError as e:
            logger.warning(
                f"Cannot write to state directory {project_dir}: {e}. "
                f"Falling back to temp directory."
            )
            return self._use_fallback_directory(project)

        except OSError as e:
            # Handle other OS errors (disk full, read-only filesystem, etc.)
            logger.warning(
                f"OS error accessing state directory {project_dir}: {e}. "
                f"Falling back to temp directory."
            )
            return self._use_fallback_directory(project)

    def _use_fallback_directory(self, project: str) -> tuple[Path, Path]:
        """
        Set up fallback state directory in temp location.

        Args:
            project: Project identifier

        Returns:
            Tuple of (base_dir, project_dir) in temp location
        """
        self._using_fallback = True
        fallback_base = _FALLBACK_STATE_DIR
        fallback_project = fallback_base / project

        try:
            fallback_project.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using fallback state directory: {fallback_project}")
            return fallback_base, fallback_project

        except Exception as e:
            # Last resort: use a unique temp directory
            import uuid
            emergency_dir = Path(tempfile.gettempdir()) / f"contextcore-{uuid.uuid4().hex[:8]}" / project
            emergency_dir.mkdir(parents=True, exist_ok=True)
            logger.warning(f"Using emergency temp directory: {emergency_dir}")
            return emergency_dir.parent, emergency_dir

    @property
    def using_fallback(self) -> bool:
        """True if using fallback temp directory instead of primary."""
        return self._using_fallback

    def save_span(self, state: SpanState) -> None:
        """
        Save span state to disk with file locking.

        Automatically populates schema version and timestamps if not set.
        Uses file locking to prevent race conditions in multi-process scenarios.

        Args:
            state: SpanState to persist
        """
        # Ensure schema version and metadata are set
        if state.schema_version != SCHEMA_VERSION:
            state.schema_version = SCHEMA_VERSION

        if state.project_id is None:
            state.project_id = self.project

        if state.created_at is None:
            state.created_at = datetime.now(timezone.utc).isoformat()

        file_path = self.project_dir / f"{state.task_id}.json"
        try:
            with file_lock(file_path, exclusive=True):
                with open(file_path, 'w') as f:
                    json.dump(state.to_dict(), f, indent=2)
            self._active_spans[state.task_id] = state
            logger.debug(f"Saved span state: {state.task_id} (schema v{SCHEMA_VERSION})")
        except Exception as e:
            logger.error(f"Failed to save span state {state.task_id}: {e}")

    def load_span(self, task_id: str) -> Optional[SpanState]:
        """
        Load span state from disk with file locking.

        Automatically migrates state from older schema versions if needed.
        Uses shared (read) lock to allow concurrent reads.

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
            with file_lock(file_path, exclusive=False):  # Shared lock for reading
                with open(file_path) as f:
                    data = json.load(f)

            old_version = data.get("schema_version", 1)
            state = SpanState.from_dict(data)
            self._active_spans[task_id] = state

            # If state was migrated, re-save with new schema (save_span has its own lock)
            if old_version < SCHEMA_VERSION:
                logger.info(f"Migrated state for {task_id} from schema v{old_version} to v{SCHEMA_VERSION}")
                self.save_span(state)

            return state
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted state file for {task_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load span state {task_id}: {e}")
            return None

    def remove_span(self, task_id: str) -> None:
        """
        Remove span state (called when span completes).

        Moves to completed directory for historical queries.
        Uses exclusive file locking to prevent race conditions during
        the read-modify-write-delete sequence.

        Args:
            task_id: Task identifier
        """
        file_path = self.project_dir / f"{task_id}.json"

        # Move to completed
        completed_dir = self.project_dir / "completed"
        completed_dir.mkdir(exist_ok=True)

        if file_path.exists():
            try:
                # Use exclusive lock for the entire read-modify-write-delete operation
                with file_lock(file_path, exclusive=True):
                    # Re-check existence after acquiring lock (another process may have removed it)
                    if not file_path.exists():
                        logger.debug(f"Span already removed by another process: {task_id}")
                        self._active_spans.pop(task_id, None)
                        return

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

    def _atomic_update(
        self,
        task_id: str,
        updater: callable,
        error_message: str,
    ) -> bool:
        """
        Atomically update a span state with file locking.

        Holds an exclusive lock for the entire read-modify-write cycle
        to prevent lost updates from concurrent modifications.

        Args:
            task_id: Task identifier
            updater: Function that takes SpanState and modifies it in place
            error_message: Message to log if span not found

        Returns:
            True if update was successful, False otherwise
        """
        file_path = self.project_dir / f"{task_id}.json"

        if not file_path.exists():
            logger.warning(error_message)
            return False

        try:
            with file_lock(file_path, exclusive=True):
                # Re-check existence after acquiring lock
                if not file_path.exists():
                    logger.warning(error_message)
                    return False

                # Load current state
                with open(file_path) as f:
                    data = json.load(f)

                state = SpanState.from_dict(data)

                # Apply the update
                updater(state)

                # Ensure schema version is current
                state.schema_version = SCHEMA_VERSION

                # Write back
                with open(file_path, 'w') as f:
                    json.dump(state.to_dict(), f, indent=2)

                # Update cache
                self._active_spans[task_id] = state

            return True

        except Exception as e:
            logger.error(f"Failed to update span {task_id}: {e}")
            return False

    def add_event(self, task_id: str, event_name: str, attributes: Dict[str, Any]) -> None:
        """
        Add an event to a span's state atomically.

        Uses file locking to prevent lost updates from concurrent modifications.

        Args:
            task_id: Task identifier
            event_name: Event name
            attributes: Event attributes
        """
        event = {
            "name": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attributes": attributes,
        }

        def updater(state: SpanState) -> None:
            state.events.append(event)

        self._atomic_update(
            task_id,
            updater,
            f"Cannot add event to unknown span: {task_id}",
        )

    def update_attribute(self, task_id: str, key: str, value: Any) -> None:
        """
        Update a span attribute atomically.

        Uses file locking to prevent lost updates from concurrent modifications.

        Args:
            task_id: Task identifier
            key: Attribute key
            value: Attribute value
        """
        def updater(state: SpanState) -> None:
            state.attributes[key] = value

        self._atomic_update(
            task_id,
            updater,
            f"Cannot update attribute on unknown span: {task_id}",
        )

    def update_status(self, task_id: str, status: str, description: Optional[str] = None) -> None:
        """
        Update span status atomically.

        Uses file locking to prevent lost updates from concurrent modifications.

        Args:
            task_id: Task identifier
            status: New status ("OK", "ERROR", "UNSET")
            description: Status description
        """
        def updater(state: SpanState) -> None:
            state.status = status
            state.status_description = description

        self._atomic_update(
            task_id,
            updater,
            f"Cannot update status on unknown span: {task_id}",
        )


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
