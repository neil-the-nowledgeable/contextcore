"""
Structured logging for task events.

Outputs JSON-formatted logs for Loki ingestion. Only logs status-changing
events per design decision - comments and assignments are stored as span
events but not logged separately.

Logged events:
- task.created
- task.status_changed
- task.blocked
- task.unblocked
- task.completed
- task.cancelled
- subtask.completed (triggers parent progress update)

Usage:
    from contextcore.logger import TaskLogger

    logger = TaskLogger(project="my-project")
    logger.log_task_created(task_id="PROJ-123", title="Do thing", task_type="story")
    logger.log_status_changed(task_id="PROJ-123", from_status="todo", to_status="in_progress")
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Configure structured logger for Loki
_loki_logger = logging.getLogger("contextcore.tasks")
_loki_logger.setLevel(logging.INFO)

# Default handler outputs JSON to stdout (for container/Loki pickup)
if not _loki_logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _loki_logger.addHandler(handler)


class TaskLogger:
    """
    Structured logger for task events.

    Outputs JSON logs designed for Loki ingestion and querying.
    Each log entry includes standard fields for filtering:
    - project_id, task_id, task_type
    - event type and event-specific attributes
    - actor and trigger information
    """

    def __init__(
        self,
        project: str,
        service_name: str = "contextcore",
        extra_labels: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize task logger.

        Args:
            project: Project identifier (used as Loki label)
            service_name: Service name for log attribution
            extra_labels: Additional labels for Loki filtering
        """
        self.project = project
        self.service_name = service_name
        self.extra_labels = extra_labels or {}
        self._logger = _loki_logger

    def _emit(
        self,
        event: str,
        task_id: str,
        level: str = "info",
        task_type: Optional[str] = None,
        task_title: Optional[str] = None,
        sprint_id: Optional[str] = None,
        actor: Optional[str] = None,
        actor_type: str = "user",
        trigger: str = "manual",
        **extra_fields: Any,
    ) -> None:
        """
        Emit a structured log entry.

        Args:
            event: Event type (e.g., "task.created")
            task_id: Task identifier
            level: Log level (info, warn, error)
            task_type: Task type (epic, story, task, etc.)
            task_title: Task title
            sprint_id: Sprint identifier
            actor: Who triggered the event
            actor_type: user, system, or integration
            trigger: How event was triggered (manual, webhook, sync)
            **extra_fields: Event-specific fields
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            "service": self.service_name,
            "project_id": self.project,
            "task_id": task_id,
        }

        if task_type:
            entry["task_type"] = task_type
        if task_title:
            entry["task_title"] = task_title
        if sprint_id:
            entry["sprint_id"] = sprint_id
        if actor:
            entry["actor"] = actor
            entry["actor_type"] = actor_type
        entry["trigger"] = trigger

        # Add extra fields
        entry.update(extra_fields)

        # Add custom labels
        if self.extra_labels:
            entry["labels"] = self.extra_labels

        # Output as JSON
        log_line = json.dumps(entry, default=str)

        if level == "error":
            self._logger.error(log_line)
        elif level == "warn":
            self._logger.warning(log_line)
        else:
            self._logger.info(log_line)

    def log_task_created(
        self,
        task_id: str,
        title: str,
        task_type: str = "task",
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        story_points: Optional[int] = None,
        sprint_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> None:
        """Log task creation event."""
        self._emit(
            event="task.created",
            task_id=task_id,
            task_type=task_type,
            task_title=title,
            sprint_id=sprint_id,
            actor=actor,
            priority=priority,
            assignee=assignee,
            story_points=story_points,
            parent_id=parent_id,
        )

    def log_status_changed(
        self,
        task_id: str,
        from_status: str,
        to_status: str,
        task_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
        actor: Optional[str] = None,
        trigger: str = "manual",
    ) -> None:
        """Log status transition event."""
        self._emit(
            event="task.status_changed",
            task_id=task_id,
            task_type=task_type,
            sprint_id=sprint_id,
            actor=actor,
            trigger=trigger,
            from_status=from_status,
            to_status=to_status,
        )

    def log_blocked(
        self,
        task_id: str,
        reason: str,
        blocked_by: Optional[str] = None,
        task_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> None:
        """Log task blocked event."""
        self._emit(
            event="task.blocked",
            task_id=task_id,
            task_type=task_type,
            sprint_id=sprint_id,
            actor=actor,
            level="warn",
            reason=reason,
            blocked_by=blocked_by,
        )

    def log_unblocked(
        self,
        task_id: str,
        resolution: Optional[str] = None,
        blocked_duration_seconds: Optional[float] = None,
        task_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> None:
        """Log task unblocked event."""
        self._emit(
            event="task.unblocked",
            task_id=task_id,
            task_type=task_type,
            sprint_id=sprint_id,
            actor=actor,
            resolution=resolution,
            blocked_duration_seconds=blocked_duration_seconds,
        )

    def log_completed(
        self,
        task_id: str,
        task_type: Optional[str] = None,
        story_points: Optional[int] = None,
        lead_time_seconds: Optional[float] = None,
        cycle_time_seconds: Optional[float] = None,
        sprint_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> None:
        """Log task completion event."""
        self._emit(
            event="task.completed",
            task_id=task_id,
            task_type=task_type,
            sprint_id=sprint_id,
            actor=actor,
            story_points=story_points,
            lead_time_seconds=lead_time_seconds,
            cycle_time_seconds=cycle_time_seconds,
        )

    def log_cancelled(
        self,
        task_id: str,
        reason: Optional[str] = None,
        task_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> None:
        """Log task cancellation event."""
        self._emit(
            event="task.cancelled",
            task_id=task_id,
            task_type=task_type,
            sprint_id=sprint_id,
            actor=actor,
            reason=reason,
        )

    def log_subtask_completed(
        self,
        parent_id: str,
        subtask_id: str,
        subtask_completed: int,
        subtask_count: int,
        percent_complete: float,
        parent_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
    ) -> None:
        """Log subtask completion and parent progress update."""
        self._emit(
            event="subtask.completed",
            task_id=parent_id,
            task_type=parent_type,
            sprint_id=sprint_id,
            subtask_id=subtask_id,
            subtask_completed=subtask_completed,
            subtask_count=subtask_count,
            percent_complete=percent_complete,
        )

    def log_sprint_started(
        self,
        sprint_id: str,
        name: str,
        goal: Optional[str] = None,
        planned_points: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> None:
        """Log sprint start event."""
        self._emit(
            event="sprint.started",
            task_id=sprint_id,  # Using task_id field for sprint
            task_type="sprint",
            sprint_id=sprint_id,
            actor=actor,
            sprint_name=name,
            goal=goal,
            planned_points=planned_points,
            start_date=start_date,
            end_date=end_date,
        )

    def log_sprint_ended(
        self,
        sprint_id: str,
        name: str,
        planned_points: Optional[int] = None,
        completed_points: Optional[int] = None,
        percent_complete: Optional[float] = None,
        actor: Optional[str] = None,
    ) -> None:
        """Log sprint end event."""
        self._emit(
            event="sprint.ended",
            task_id=sprint_id,
            task_type="sprint",
            sprint_id=sprint_id,
            actor=actor,
            sprint_name=name,
            planned_points=planned_points,
            completed_points=completed_points,
            percent_complete=percent_complete,
        )

    def log_progress_updated(
        self,
        task_id: str,
        percent_complete: float,
        task_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
        source: str = "manual",
        subtask_completed: Optional[int] = None,
        subtask_count: Optional[int] = None,
        actor: Optional[str] = None,
    ) -> None:
        """
        Log task progress update event.

        This event is used to derive metrics from logs via Loki recording rules.
        The percent_complete field enables time-series tracking of task progress.

        Args:
            task_id: Task identifier
            percent_complete: Progress percentage (0-100)
            task_type: Task type (epic, story, task, etc.)
            sprint_id: Sprint identifier
            source: How progress was determined (manual, subtask, estimate)
            subtask_completed: Number of subtasks completed (if source=subtask)
            subtask_count: Total subtasks (if source=subtask)
            actor: Who triggered the update
        """
        self._emit(
            event="task.progress_updated",
            task_id=task_id,
            task_type=task_type,
            sprint_id=sprint_id,
            actor=actor,
            percent_complete=percent_complete,
            source=source,
            subtask_completed=subtask_completed,
            subtask_count=subtask_count,
        )
