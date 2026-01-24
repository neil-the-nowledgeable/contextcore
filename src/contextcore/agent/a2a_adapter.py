"""A2A Task Adapter for ContextCore.
__all__ = ['TaskState', 'TaskAdapter']


Provides bidirectional translation between A2A Task format and ContextCore Handoff,
enabling interoperability with A2A-compatible agents.
"""

from enum import Enum
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
import uuid

from ..models.handoff import Handoff, HandoffStatus, HandoffPriority, ExpectedOutput
from ..models.message import Message
from ..models.artifact import Artifact


class TaskState(str, Enum):
    """A2A Task state enumeration."""
    PENDING = "PENDING"
    WORKING = "WORKING"
    INPUT_REQUIRED = "INPUT_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class TaskAdapter:
    """Bidirectional translation between A2A Task and ContextCore Handoff."""

    # Status mapping tables - comprehensive mappings for all HandoffStatus values
    _HANDOFF_TO_TASK: Dict[HandoffStatus, TaskState] = {
        HandoffStatus.PENDING: TaskState.PENDING,
        HandoffStatus.ACCEPTED: TaskState.WORKING,
        HandoffStatus.IN_PROGRESS: TaskState.WORKING,
        HandoffStatus.INPUT_REQUIRED: TaskState.INPUT_REQUIRED,
        HandoffStatus.COMPLETED: TaskState.COMPLETED,
        HandoffStatus.FAILED: TaskState.FAILED,
        HandoffStatus.TIMEOUT: TaskState.FAILED,
        HandoffStatus.CANCELLED: TaskState.CANCELLED,
        HandoffStatus.REJECTED: TaskState.REJECTED,
    }

    _TASK_TO_HANDOFF: Dict[TaskState, HandoffStatus] = {
        TaskState.PENDING: HandoffStatus.PENDING,
        TaskState.WORKING: HandoffStatus.IN_PROGRESS,
        TaskState.INPUT_REQUIRED: HandoffStatus.INPUT_REQUIRED,
        TaskState.COMPLETED: HandoffStatus.COMPLETED,
        TaskState.FAILED: HandoffStatus.FAILED,
        TaskState.CANCELLED: HandoffStatus.CANCELLED,
        TaskState.REJECTED: HandoffStatus.REJECTED,
    }

    @classmethod
    def handoff_to_task(
        cls, 
        handoff: Handoff, 
        messages: Optional[List[Message]] = None, 
        artifacts: Optional[List[Artifact]] = None
    ) -> Dict[str, Any]:
        """Convert ContextCore Handoff to A2A Task JSON."""
        return {
            "taskId": handoff.id,
            "contextId": f"{handoff.from_agent}:{handoff.to_agent}",
            "status": cls._status_to_task_state(handoff.status).value,
            "messages": [m.to_a2a_dict() for m in (messages or [])],
            "artifacts": [a.to_a2a_dict() for a in (artifacts or [])],
            "createdTime": handoff.created_at.isoformat(),
            "updatedTime": datetime.now(timezone.utc).isoformat(),
            # A2A metadata with ContextCore specifics
            "metadata": {
                "contextcore": {
                    "from_agent": handoff.from_agent,
                    "to_agent": handoff.to_agent,
                    "capability_id": handoff.capability_id,
                    "priority": handoff.priority.value,
                }
            }
        }

    @classmethod
    def task_to_handoff(
        cls,
        task: Dict[str, Any],
        from_agent: str,
        to_agent: str,
        capability_id: str = "unknown",
    ) -> Handoff:
        """Convert A2A Task JSON to ContextCore Handoff."""
        # Extract ContextCore metadata if present
        cc_meta = task.get("metadata", {}).get("contextcore", {})

        status = cls._task_state_to_status(task.get("status", "PENDING"))

        return Handoff(
            id=task.get("taskId", f"task-{uuid.uuid4().hex[:12]}"),
            from_agent=cc_meta.get("from_agent", from_agent),
            to_agent=cc_meta.get("to_agent", to_agent),
            capability_id=cc_meta.get("capability_id", capability_id),
            task=cls._extract_task_description(task),
            inputs=cls._extract_inputs(task),
            expected_output=ExpectedOutput(type="any", fields=[]),
            priority=HandoffPriority(cc_meta.get("priority", "normal")),
            status=status,
            created_at=cls._parse_timestamp(task.get("createdTime")),
        )

    @classmethod
    def _status_to_task_state(cls, status: HandoffStatus) -> TaskState:
        """Convert HandoffStatus to TaskState."""
        return cls._HANDOFF_TO_TASK.get(status, TaskState.PENDING)

    @classmethod
    def _task_state_to_status(cls, state: str) -> HandoffStatus:
        """Convert TaskState string to HandoffStatus."""
        try:
            task_state = TaskState(state)
        except ValueError:
            # Invalid state defaults to PENDING
            task_state = TaskState.PENDING
        return cls._TASK_TO_HANDOFF.get(task_state, HandoffStatus.PENDING)

    @classmethod
    def _extract_task_description(cls, task: Dict[str, Any]) -> str:
        """Extract task description from first text message."""
        for msg in task.get("messages", []):
            for part in msg.get("parts", []):
                if "text" in part:
                    return part["text"]
        return ""

    @classmethod
    def _extract_inputs(cls, task: Dict[str, Any]) -> Dict[str, Any]:
        """Extract inputs from task messages and metadata."""
        inputs = {}
        
        # Look for inputs in metadata first
        inputs.update(task.get("metadata", {}).get("inputs", {}))
        
        # Look for JSON/data parts in messages
        for msg in task.get("messages", []):
            for part in msg.get("parts", []):
                if "data" in part:
                    try:
                        # Merge data parts into inputs
                        if isinstance(part["data"], dict):
                            inputs.update(part["data"])
                    except (TypeError, ValueError):
                        # Skip malformed data
                        continue
        
        return inputs

    @classmethod
    def _parse_timestamp(cls, timestamp_str: Optional[str]) -> datetime:
        """Parse timestamp string to datetime, with UTC fallback."""
        if timestamp_str:
            try:
                # Handle both ISO format with and without timezone
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                # Ensure UTC timezone
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    @classmethod
    def messages_from_task(cls, task: Dict[str, Any]) -> List[Message]:
        """Extract Messages from A2A Task."""
        messages = []
        for msg_dict in task.get("messages", []):
            try:
                messages.append(Message.from_a2a_dict(msg_dict))
            except (ValueError, KeyError):
                # Skip malformed messages
                continue
        return messages

    @classmethod
    def artifacts_from_task(cls, task: Dict[str, Any]) -> List[Artifact]:
        """Extract Artifacts from A2A Task."""
        artifacts = []
        for artifact_dict in task.get("artifacts", []):
            try:
                artifacts.append(Artifact.from_a2a_dict(artifact_dict))
            except (ValueError, KeyError):
                # Skip malformed artifacts
                continue
        return artifacts


__all__ = ["TaskState", "TaskAdapter"]


# Convert Handoff to A2A Task
task_json = TaskAdapter.handoff_to_task(handoff, messages, artifacts)

# Convert A2A Task to Handoff
handoff = TaskAdapter.task_to_handoff(task_json, "agent1", "agent2", "capability")
