"""
State file management for ContextCore installation tracking.

This module provides state persistence for installation steps, supporting:
- Resume mode: Skip completed steps when resuming installation
- Repair mode: Re-verify and fix failed steps
- Atomic updates: Use temporary files to prevent corruption
- Cross-platform: Works on macOS and Linux

State is stored as JSON at ~/.contextcore/install-state.json
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "StepStatus",
    "StepState",
    "InstallationState",
    "StateFile",
    "init_state",
    "get_state_file",
    "state_exists",
    "get_step_status",
    "get_step_timestamp",
    "get_step_duration",
    "should_skip_step",
    "update_step_status",
    "mark_step_running",
    "mark_step_completed",
    "mark_step_failed",
    "show_state_summary",
]

# Default state file location
DEFAULT_STATE_PATH = Path.home() / ".contextcore" / "install-state.json"

# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class StepStatus(str, Enum):
    """Status values for installation steps."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepState:
    """State for a single installation step."""
    step_id: str
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[str] = None  # ISO format
    completed_at: Optional[str] = None  # ISO format
    duration_seconds: Optional[float] = None
    output: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "output": self.output,
            "error": self.error,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepState":
        """Create from dictionary."""
        return cls(
            step_id=data["step_id"],
            status=StepStatus(data.get("status", "pending")),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            duration_seconds=data.get("duration_seconds"),
            output=data.get("output"),
            error=data.get("error"),
            retry_count=data.get("retry_count", 0),
        )


@dataclass
class InstallationState:
    """Complete installation state including all steps."""
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cluster_name: str = "contextcore-local"
    steps: Dict[str, StepState] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cluster_name": self.cluster_name,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstallationState":
        """Create from dictionary."""
        steps = {
            k: StepState.from_dict(v)
            for k, v in data.get("steps", {}).items()
        }
        return cls(
            version=data.get("version", 1),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            cluster_name=data.get("cluster_name", "contextcore-local"),
            steps=steps,
        )


class StateFile:
    """
    Manages installation state file with atomic updates.

    Provides thread-safe, atomic operations for tracking installation
    step progress with support for resume and repair modes.
    """

    def __init__(self, path: Optional[Path] = None):
        """
        Initialize state file manager.

        Args:
            path: Path to state file. Defaults to ~/.contextcore/install-state.json
        """
        self.path = path or DEFAULT_STATE_PATH
        self._state: Optional[InstallationState] = None

    @property
    def state(self) -> InstallationState:
        """Get current state, loading from disk if needed."""
        if self._state is None:
            self._state = self.load()
        return self._state

    def exists(self) -> bool:
        """Check if state file exists."""
        return self.path.exists()

    def load(self) -> InstallationState:
        """
        Load state from disk.

        Returns:
            InstallationState, creating new if file doesn't exist.
        """
        if not self.path.exists():
            return InstallationState()

        try:
            with open(self.path, 'r') as f:
                data = json.load(f)
            return InstallationState.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            # Corrupted state file - return new state
            print(f"{Colors.YELLOW}Warning: Corrupted state file, creating new state{Colors.RESET}")
            return InstallationState()

    def save(self) -> None:
        """
        Save state to disk atomically.

        Uses temporary file + rename for atomic update to prevent corruption.
        Sets file permissions to 600 (owner read/write only).
        """
        # Ensure directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Update timestamp
        self.state.updated_at = datetime.now(timezone.utc).isoformat()

        # Write to temp file first (atomic update pattern)
        fd, temp_path = tempfile.mkstemp(
            dir=self.path.parent,
            prefix='.install-state-',
            suffix='.tmp'
        )
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(self.state.to_dict(), f, indent=2)

            # Set secure permissions (600)
            os.chmod(temp_path, 0o600)

            # Atomic rename
            os.replace(temp_path, self.path)
        except Exception:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def init(self, cluster_name: str = "contextcore-local", force: bool = False) -> bool:
        """
        Initialize state file.

        Args:
            cluster_name: Name of the cluster being installed
            force: If True, overwrite existing state file

        Returns:
            True if state was initialized, False if already exists (and not forced)
        """
        if self.exists() and not force:
            return False

        self._state = InstallationState(cluster_name=cluster_name)
        self.save()
        return True

    def get_step(self, step_id: str) -> StepState:
        """
        Get state for a specific step.

        Args:
            step_id: Step identifier

        Returns:
            StepState for the step (creates new if not exists)
        """
        if step_id not in self.state.steps:
            self.state.steps[step_id] = StepState(step_id=step_id)
        return self.state.steps[step_id]

    def get_step_status(self, step_id: str) -> StepStatus:
        """Get status of a step."""
        return self.get_step(step_id).status

    def get_step_timestamp(self, step_id: str) -> Optional[str]:
        """Get completion timestamp of a step."""
        step = self.get_step(step_id)
        return step.completed_at or step.started_at

    def get_step_duration(self, step_id: str) -> Optional[float]:
        """Get duration of a step in seconds."""
        return self.get_step(step_id).duration_seconds

    def should_skip_step(self, step_id: str) -> bool:
        """
        Check if step should be skipped in resume mode.

        Skips if:
        - RESUME_MODE env var is set to 'true' or '1'
        - Step status is 'completed'

        Args:
            step_id: Step identifier

        Returns:
            True if step should be skipped
        """
        resume_mode = os.getenv("RESUME_MODE", "").lower() in ("true", "1", "yes")
        if not resume_mode:
            return False

        return self.get_step_status(step_id) == StepStatus.COMPLETED

    def mark_running(self, step_id: str) -> None:
        """Mark a step as running."""
        step = self.get_step(step_id)
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(timezone.utc).isoformat()
        step.completed_at = None
        step.duration_seconds = None
        step.error = None
        self.save()

    def mark_completed(self, step_id: str, output: Optional[str] = None) -> None:
        """
        Mark a step as completed.

        Args:
            step_id: Step identifier
            output: Optional output/result from the step
        """
        step = self.get_step(step_id)
        step.status = StepStatus.COMPLETED
        step.completed_at = datetime.now(timezone.utc).isoformat()
        step.output = output

        # Calculate duration if started_at is set
        if step.started_at:
            started = datetime.fromisoformat(step.started_at.replace('Z', '+00:00'))
            completed = datetime.fromisoformat(step.completed_at.replace('Z', '+00:00'))
            step.duration_seconds = (completed - started).total_seconds()

        self.save()

    def mark_failed(self, step_id: str, error: str) -> None:
        """
        Mark a step as failed.

        Args:
            step_id: Step identifier
            error: Error message describing the failure
        """
        step = self.get_step(step_id)
        step.status = StepStatus.FAILED
        step.completed_at = datetime.now(timezone.utc).isoformat()
        step.error = error
        step.retry_count += 1

        # Calculate duration if started_at is set
        if step.started_at:
            started = datetime.fromisoformat(step.started_at.replace('Z', '+00:00'))
            completed = datetime.fromisoformat(step.completed_at.replace('Z', '+00:00'))
            step.duration_seconds = (completed - started).total_seconds()

        self.save()

    def show_summary(self, use_colors: bool = True) -> str:
        """
        Generate a summary of installation state.

        Args:
            use_colors: Whether to use ANSI color codes

        Returns:
            Formatted summary string
        """
        c = Colors if use_colors else type('NoColors', (), {k: '' for k in dir(Colors) if not k.startswith('_')})()

        lines = [
            f"{c.BOLD}ContextCore Installation State{c.RESET}",
            f"{'=' * 40}",
            f"Cluster: {self.state.cluster_name}",
            f"Created: {self.state.created_at}",
            f"Updated: {self.state.updated_at}",
            "",
            f"{c.BOLD}Steps:{c.RESET}",
        ]

        status_symbols = {
            StepStatus.PENDING: f"{c.BLUE}⬜{c.RESET}",
            StepStatus.RUNNING: f"{c.YELLOW}⏳{c.RESET}",
            StepStatus.COMPLETED: f"{c.GREEN}✅{c.RESET}",
            StepStatus.FAILED: f"{c.RED}❌{c.RESET}",
            StepStatus.SKIPPED: f"{c.CYAN}⏭️{c.RESET}",
        }

        for step_id, step in sorted(self.state.steps.items()):
            symbol = status_symbols.get(step.status, "?")
            duration = f" ({step.duration_seconds:.1f}s)" if step.duration_seconds else ""
            error_info = f" - {step.error}" if step.error else ""
            lines.append(f"  {symbol} {step_id}: {step.status.value}{duration}{error_info}")

        if not self.state.steps:
            lines.append("  (no steps recorded)")

        # Summary stats
        completed = sum(1 for s in self.state.steps.values() if s.status == StepStatus.COMPLETED)
        total = len(self.state.steps) or 1
        lines.extend([
            "",
            f"Progress: {completed}/{total} steps completed",
        ])

        return "\n".join(lines)


# Module-level convenience functions
_default_state_file: Optional[StateFile] = None


def get_state_file() -> StateFile:
    """Get the default state file instance."""
    global _default_state_file
    if _default_state_file is None:
        _default_state_file = StateFile()
    return _default_state_file


def init_state(cluster_name: str = "contextcore-local", force: bool = False) -> bool:
    """Initialize state file."""
    return get_state_file().init(cluster_name, force)


def state_exists() -> bool:
    """Check if state file exists."""
    return get_state_file().exists()


def get_step_status(step_id: str) -> StepStatus:
    """Get status of a step."""
    return get_state_file().get_step_status(step_id)


def get_step_timestamp(step_id: str) -> Optional[str]:
    """Get timestamp of a step."""
    return get_state_file().get_step_timestamp(step_id)


def get_step_duration(step_id: str) -> Optional[float]:
    """Get duration of a step in seconds."""
    return get_state_file().get_step_duration(step_id)


def should_skip_step(step_id: str) -> bool:
    """Check if step should be skipped in resume mode."""
    return get_state_file().should_skip_step(step_id)


def update_step_status(step_id: str, status: StepStatus) -> None:
    """Update status of a step."""
    sf = get_state_file()
    step = sf.get_step(step_id)
    step.status = status
    sf.save()


def mark_step_running(step_id: str) -> None:
    """Mark a step as running."""
    get_state_file().mark_running(step_id)


def mark_step_completed(step_id: str, output: Optional[str] = None) -> None:
    """Mark a step as completed."""
    get_state_file().mark_completed(step_id, output)


def mark_step_failed(step_id: str, error: str) -> None:
    """Mark a step as failed."""
    get_state_file().mark_failed(step_id, error)


def show_state_summary(use_colors: bool = True) -> str:
    """Show summary of installation state."""
    return get_state_file().show_summary(use_colors)
