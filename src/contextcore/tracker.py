"""
Task Tracker - Model project tasks as OpenTelemetry spans.

The core insight: Tasks ARE Spans. A task has start time, end time, status,
attributes, parent-child relationships, and events - exactly like OTel spans.

Example:
    from contextcore import TaskTracker

    tracker = TaskTracker(project="my-project")

    # Start a task (creates span)
    tracker.start_task(
        task_id="PROJ-123",
        title="Implement user auth",
        task_type="story",
        parent_id="EPIC-42"
    )

    # Update status (adds span event)
    tracker.update_status("PROJ-123", "in_progress")

    # Block task (adds event, sets ERROR status)
    tracker.block_task("PROJ-123", reason="Waiting on API")

    # Complete task (ends span)
    tracker.complete_task("PROJ-123")
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider, Span
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Link, SpanKind, Status, StatusCode

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Task hierarchy types."""
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
    SUBTASK = "subtask"
    BUG = "bug"
    SPIKE = "spike"
    INCIDENT = "incident"


class TaskStatus(str, Enum):
    """Task lifecycle statuses."""
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class Priority(str, Enum):
    """Task priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Semantic convention attribute names
TASK_ID = "task.id"
TASK_TYPE = "task.type"
TASK_TITLE = "task.title"
TASK_STATUS = "task.status"
TASK_PRIORITY = "task.priority"
TASK_ASSIGNEE = "task.assignee"
TASK_STORY_POINTS = "task.story_points"
TASK_LABELS = "task.labels"
TASK_URL = "task.url"
TASK_DUE_DATE = "task.due_date"
TASK_BLOCKED_BY = "task.blocked_by"

PROJECT_ID = "project.id"
PROJECT_NAME = "project.name"
SPRINT_ID = "sprint.id"
SPRINT_NAME = "sprint.name"


class TaskTracker:
    """
    Track project tasks as OpenTelemetry spans.

    Each task becomes a span with:
    - start_time: when task was created/started
    - end_time: when task was completed (None while in progress)
    - attributes: task.id, task.type, task.status, etc.
    - events: status changes, blockers, comments
    - parent: epic or story span
    - links: dependencies on other tasks
    """

    def __init__(
        self,
        project: str,
        service_name: str = "contextcore-tracker",
        state_dir: Optional[str] = None,
        exporter: Optional[Any] = None,
    ):
        """
        Initialize the task tracker.

        Args:
            project: Project identifier
            service_name: OTel service name
            state_dir: Directory for persisting active span state
            exporter: Optional custom span exporter (defaults to OTLP)
        """
        self.project = project
        self.state_dir = state_dir or os.path.expanduser("~/.contextcore/state")
        self._active_spans: Dict[str, Span] = {}
        self._span_contexts: Dict[str, trace.SpanContext] = {}

        # Initialize OTel
        resource = Resource.create({
            "service.name": service_name,
            "service.namespace": "contextcore",
            PROJECT_ID: project,
            PROJECT_NAME: project,
        })

        self._provider = TracerProvider(resource=resource)

        if exporter:
            self._provider.add_span_processor(BatchSpanProcessor(exporter))
        else:
            self._setup_default_exporter()

        trace.set_tracer_provider(self._provider)
        self._tracer = trace.get_tracer("contextcore.tracker")

        # Load persisted state
        self._load_state()

    def _setup_default_exporter(self) -> None:
        """Set up OTLP exporter to Alloy."""
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            self._provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(f"Configured OTLP exporter to {endpoint}")
        except ImportError:
            logger.warning("OTLP exporter not available, spans will not be exported")

    def start_task(
        self,
        task_id: str,
        title: str,
        task_type: str = "task",
        status: str = "todo",
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        story_points: Optional[int] = None,
        labels: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        url: Optional[str] = None,
        due_date: Optional[str] = None,
        sprint_id: Optional[str] = None,
        **extra_attributes: Any,
    ) -> trace.SpanContext:
        """
        Start a new task span.

        Args:
            task_id: Unique task identifier
            title: Task title/description
            task_type: epic|story|task|subtask|bug|spike|incident
            status: Initial status
            priority: critical|high|medium|low
            assignee: Person assigned
            story_points: Estimated effort
            labels: Tags/labels
            parent_id: Parent task ID (creates parent-child relationship)
            depends_on: Task IDs this depends on (creates span links)
            url: Link to external system
            due_date: Due date (ISO format)
            sprint_id: Sprint identifier
            **extra_attributes: Additional span attributes

        Returns:
            SpanContext for the created span
        """
        if task_id in self._active_spans:
            logger.warning(f"Task {task_id} already active, returning existing span")
            return self._active_spans[task_id].get_span_context()

        # Build attributes
        attributes: Dict[str, Any] = {
            TASK_ID: task_id,
            TASK_TYPE: task_type,
            TASK_TITLE: title,
            TASK_STATUS: status,
        }

        if priority:
            attributes[TASK_PRIORITY] = priority
        if assignee:
            attributes[TASK_ASSIGNEE] = assignee
        if story_points is not None:
            attributes[TASK_STORY_POINTS] = story_points
        if labels:
            attributes[TASK_LABELS] = labels
        if url:
            attributes[TASK_URL] = url
        if due_date:
            attributes[TASK_DUE_DATE] = due_date
        if sprint_id:
            attributes[SPRINT_ID] = sprint_id

        attributes.update(extra_attributes)

        # Build links for dependencies
        links: List[Link] = []
        if depends_on:
            for dep_id in depends_on:
                if dep_id in self._span_contexts:
                    links.append(Link(
                        self._span_contexts[dep_id],
                        attributes={"link.type": "depends_on"}
                    ))

        # Determine parent context
        parent_context = None
        if parent_id and parent_id in self._active_spans:
            parent_context = trace.set_span_in_context(self._active_spans[parent_id])

        # Create span name
        span_name = f"{task_type}:{task_id}"

        # Start the span
        span = self._tracer.start_span(
            name=span_name,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            links=links,
            context=parent_context,
        )

        # Add creation event
        span.add_event(
            "task.created",
            attributes={
                "task.title": title,
                "task.type": task_type,
            }
        )

        # Store span
        self._active_spans[task_id] = span
        self._span_contexts[task_id] = span.get_span_context()

        # Persist state
        self._save_state()

        logger.info(f"Started task span: {task_id} ({task_type})")
        return span.get_span_context()

    def update_status(self, task_id: str, new_status: str) -> None:
        """
        Update task status (adds span event).

        Args:
            task_id: Task identifier
            new_status: New status value
        """
        span = self._get_span(task_id)
        if not span:
            return

        # Get current status
        old_status = "unknown"
        if hasattr(span, '_attributes') and TASK_STATUS in span._attributes:
            old_status = span._attributes[TASK_STATUS]

        # Add status change event
        span.add_event(
            "task.status_changed",
            attributes={
                "from": old_status,
                "to": new_status,
            }
        )

        # Update attribute
        span.set_attribute(TASK_STATUS, new_status)

        # Handle blocked status
        if new_status == TaskStatus.BLOCKED.value:
            span.set_status(Status(StatusCode.ERROR, "Task blocked"))
        elif old_status == TaskStatus.BLOCKED.value:
            span.set_status(Status(StatusCode.OK))

        self._save_state()
        logger.info(f"Task {task_id}: {old_status} → {new_status}")

    def block_task(
        self,
        task_id: str,
        reason: str,
        blocked_by: Optional[str] = None,
    ) -> None:
        """
        Mark task as blocked (adds event, sets ERROR status).

        Args:
            task_id: Task identifier
            reason: Why the task is blocked
            blocked_by: Task ID that's blocking this one
        """
        span = self._get_span(task_id)
        if not span:
            return

        event_attrs: Dict[str, Any] = {"reason": reason}
        if blocked_by:
            event_attrs["blocker_id"] = blocked_by
            span.set_attribute(TASK_BLOCKED_BY, blocked_by)

        span.add_event("task.blocked", attributes=event_attrs)
        span.set_attribute(TASK_STATUS, TaskStatus.BLOCKED.value)
        span.set_status(Status(StatusCode.ERROR, f"Blocked: {reason}"))

        self._save_state()
        logger.info(f"Task {task_id} blocked: {reason}")

    def unblock_task(self, task_id: str, new_status: str = "in_progress") -> None:
        """
        Remove blocker from task.

        Args:
            task_id: Task identifier
            new_status: Status to set after unblocking
        """
        span = self._get_span(task_id)
        if not span:
            return

        span.add_event("task.unblocked")
        span.set_attribute(TASK_STATUS, new_status)
        span.set_status(Status(StatusCode.OK))

        self._save_state()
        logger.info(f"Task {task_id} unblocked → {new_status}")

    def add_comment(self, task_id: str, author: str, text: str) -> None:
        """
        Add a comment to task (as span event).

        Args:
            task_id: Task identifier
            author: Comment author
            text: Comment text
        """
        span = self._get_span(task_id)
        if not span:
            return

        span.add_event(
            "task.commented",
            attributes={
                "author": author,
                "text": text[:500],  # Truncate long comments
            }
        )
        logger.debug(f"Task {task_id}: comment by {author}")

    def assign_task(self, task_id: str, assignee: str) -> None:
        """
        Assign task to someone (adds event, updates attribute).

        Args:
            task_id: Task identifier
            assignee: Person to assign
        """
        span = self._get_span(task_id)
        if not span:
            return

        old_assignee = None
        if hasattr(span, '_attributes') and TASK_ASSIGNEE in span._attributes:
            old_assignee = span._attributes[TASK_ASSIGNEE]

        span.add_event(
            "task.assigned",
            attributes={
                "from": old_assignee or "unassigned",
                "to": assignee,
            }
        )
        span.set_attribute(TASK_ASSIGNEE, assignee)

        self._save_state()
        logger.info(f"Task {task_id} assigned to {assignee}")

    def complete_task(self, task_id: str) -> None:
        """
        Complete a task (ends the span with OK status).

        Args:
            task_id: Task identifier
        """
        span = self._get_span(task_id)
        if not span:
            return

        span.add_event("task.completed")
        span.set_attribute(TASK_STATUS, TaskStatus.DONE.value)
        span.set_status(Status(StatusCode.OK))
        span.end()

        # Remove from active spans but keep context for linking
        del self._active_spans[task_id]

        self._save_state()
        logger.info(f"Task {task_id} completed")

    def cancel_task(self, task_id: str, reason: Optional[str] = None) -> None:
        """
        Cancel a task (ends span with cancelled status).

        Args:
            task_id: Task identifier
            reason: Cancellation reason
        """
        span = self._get_span(task_id)
        if not span:
            return

        event_attrs: Dict[str, Any] = {}
        if reason:
            event_attrs["reason"] = reason

        span.add_event("task.cancelled", attributes=event_attrs)
        span.set_attribute(TASK_STATUS, TaskStatus.CANCELLED.value)
        span.set_status(Status(StatusCode.OK))
        span.end()

        del self._active_spans[task_id]

        self._save_state()
        logger.info(f"Task {task_id} cancelled")

    def get_task_link(self, task_id: str) -> Optional[Link]:
        """
        Get a Link to a task span for use in other traces.

        Args:
            task_id: Task identifier

        Returns:
            Link object or None if task not found
        """
        if task_id in self._span_contexts:
            return Link(
                self._span_contexts[task_id],
                attributes={"link.type": "implements_task"}
            )
        return None

    def get_active_tasks(self) -> List[str]:
        """Get list of active task IDs."""
        return list(self._active_spans.keys())

    def _get_span(self, task_id: str) -> Optional[Span]:
        """Get active span for task."""
        if task_id not in self._active_spans:
            logger.warning(f"Task {task_id} not found in active spans")
            return None
        return self._active_spans[task_id]

    def _load_state(self) -> None:
        """Load persisted span state from disk."""
        # TODO: Implement state persistence for long-running spans
        # This requires serializing span context and recreating spans
        pass

    def _save_state(self) -> None:
        """Persist active span state to disk."""
        # TODO: Implement state persistence
        pass

    def shutdown(self) -> None:
        """Flush and shutdown the tracker."""
        self._provider.force_flush()
        self._provider.shutdown()


class SprintTracker:
    """
    Track sprints as parent spans containing tasks.

    A sprint is a time-boxed span that contains task spans as children.
    """

    def __init__(self, task_tracker: TaskTracker):
        self._tracker = task_tracker
        self._tracer = task_tracker._tracer
        self._active_sprints: Dict[str, Span] = {}

    def start_sprint(
        self,
        sprint_id: str,
        name: str,
        goal: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        planned_points: Optional[int] = None,
    ) -> trace.SpanContext:
        """
        Start a new sprint span.

        Args:
            sprint_id: Sprint identifier
            name: Sprint name
            goal: Sprint goal
            start_date: Sprint start date
            end_date: Sprint end date
            planned_points: Planned story points

        Returns:
            SpanContext for the sprint
        """
        attributes: Dict[str, Any] = {
            SPRINT_ID: sprint_id,
            SPRINT_NAME: name,
        }

        if goal:
            attributes["sprint.goal"] = goal
        if start_date:
            attributes["sprint.start_date"] = start_date
        if end_date:
            attributes["sprint.end_date"] = end_date
        if planned_points is not None:
            attributes["sprint.planned_points"] = planned_points

        span = self._tracer.start_span(
            name=f"sprint:{sprint_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        )

        span.add_event("sprint.started", attributes={"name": name})

        self._active_sprints[sprint_id] = span
        logger.info(f"Started sprint: {sprint_id} ({name})")

        return span.get_span_context()

    def end_sprint(
        self,
        sprint_id: str,
        completed_points: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        End a sprint.

        Args:
            sprint_id: Sprint identifier
            completed_points: Actual points completed
            notes: Sprint retrospective notes
        """
        if sprint_id not in self._active_sprints:
            logger.warning(f"Sprint {sprint_id} not found")
            return

        span = self._active_sprints[sprint_id]

        event_attrs: Dict[str, Any] = {}
        if completed_points is not None:
            event_attrs["completed_points"] = completed_points
            span.set_attribute("sprint.completed_points", completed_points)
        if notes:
            event_attrs["notes"] = notes

        span.add_event("sprint.ended", attributes=event_attrs)
        span.set_status(Status(StatusCode.OK))
        span.end()

        del self._active_sprints[sprint_id]
        logger.info(f"Ended sprint: {sprint_id}")
