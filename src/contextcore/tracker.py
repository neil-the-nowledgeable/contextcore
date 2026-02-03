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

import atexit
import logging
import os
import socket
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider, Span
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Link, SpanKind, Status, StatusCode

from contextcore.contracts.types import TaskStatus, TaskType, Priority
from contextcore.detector import (
    get_telemetry_sdk_attributes,
    get_service_attributes,
    get_host_attributes,
)
from contextcore.logger import TaskLogger
from contextcore.state import StateManager, SpanState, format_trace_id, format_span_id
from contextcore.compat.otel_genai import transform_attributes

logger = logging.getLogger(__name__)

# Export mode tracking
EXPORT_MODE_OTLP = "otlp"
EXPORT_MODE_CONSOLE = "console"
EXPORT_MODE_NONE = "none"


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
TASK_PERCENT_COMPLETE = "task.percent_complete"
TASK_SUBTASK_COUNT = "task.subtask_count"
TASK_SUBTASK_COMPLETED = "task.subtask_completed"
TASK_PARENT_ID = "task.parent_id"

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
        exporter: Optional[Any] = None):
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
        self._parent_map: Dict[str, str] = {}  # child_id -> parent_id
        self._children_map: Dict[str, List[str]] = {}  # parent_id -> [child_ids]
        self._shutdown_called = False
        # Store task attributes separately to avoid relying on span._attributes (internal API)
        self._task_attributes: Dict[str, Dict[str, Any]] = {}

        # Initialize structured logger for Loki
        self._task_logger = TaskLogger(project=project, service_name=service_name)

        # Initialize state manager for persistence
        self._state_manager = StateManager(project=project, state_dir=state_dir)

        # Initialize OTel with standard resource attributes
        resource_attrs = {
            # Standard OTel SDK attributes
            **get_telemetry_sdk_attributes(),
            # Service identification (override service.name if provided)
            **get_service_attributes(service_name=service_name),
            # Host/process/OS context
            **get_host_attributes(),
            # ContextCore project attributes
            PROJECT_ID: project,
            PROJECT_NAME: project,
        }
        resource = Resource.create(resource_attrs)

        self._provider = TracerProvider(resource=resource)
        self._export_mode = EXPORT_MODE_NONE

        if exporter:
            self._provider.add_span_processor(BatchSpanProcessor(exporter))
            self._export_mode = EXPORT_MODE_OTLP
        else:
            self._setup_default_exporter()

        # Use tracer from our own provider (don't set global to avoid test conflicts)
        self._tracer = self._provider.get_tracer("contextcore.tracker")

        # Load persisted state
        self._load_state()

        # Register shutdown handler to ensure spans are flushed
        atexit.register(self._atexit_shutdown)

    def _atexit_shutdown(self) -> None:
        """Shutdown handler called at process exit."""
        try:
            self._provider.force_flush(timeout_millis=5000)
            self._provider.shutdown()
        except Exception as e:
            logger.debug(f"Error during atexit shutdown: {e}")

    def _check_endpoint_available(self, endpoint: str, timeout: float = 2.0) -> bool:
        """
        Check if OTLP endpoint is reachable.

        Args:
            endpoint: Host:port string (e.g., "localhost:4317")
            timeout: Connection timeout in seconds

        Returns:
            True if endpoint accepts connections, False otherwise
        """
        try:
            # Parse host and port
            if "://" in endpoint:
                # Handle URLs like http://localhost:4317
                from urllib.parse import urlparse
                parsed = urlparse(endpoint)
                host = parsed.hostname or "localhost"
                port = parsed.port or 4317
            else:
                # Handle host:port format
                parts = endpoint.split(":")
                host = parts[0] if parts else "localhost"
                port = int(parts[1]) if len(parts) > 1 else 4317

            # Attempt TCP connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                logger.debug(f"OTLP endpoint {host}:{port} is reachable")
                return True
            else:
                logger.debug(f"OTLP endpoint {host}:{port} connection failed: error code {result}")
                return False

        except (socket.timeout, socket.error, ValueError, OSError) as e:
            logger.debug(f"OTLP endpoint check failed: {e}")
            return False

    def _setup_default_exporter(self) -> None:
        """
        Set up OTLP exporter to Alloy with fallback handling.

        Checks endpoint availability first to avoid silent failures.
        Falls back to console exporter in debug mode if OTLP unavailable.
        """
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
        fallback_to_console = os.environ.get("CONTEXTCORE_FALLBACK_CONSOLE", "").lower() in ("1", "true", "yes")

        try:
            from contextcore.exporter_factory import create_span_exporter

            # Check if endpoint is reachable before configuring
            if self._check_endpoint_available(endpoint):
                exporter = create_span_exporter(endpoint=endpoint)
                self._provider.add_span_processor(BatchSpanProcessor(exporter))
                self._export_mode = EXPORT_MODE_OTLP
                logger.info(f"Configured OTLP exporter to {endpoint}")
            else:
                logger.warning(
                    f"OTLP endpoint {endpoint} not reachable. "
                    f"Spans will be persisted locally but not exported. "
                    f"Set CONTEXTCORE_FALLBACK_CONSOLE=1 to enable console export."
                )
                if fallback_to_console:
                    self._provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
                    self._export_mode = EXPORT_MODE_CONSOLE
                    logger.info("Enabled console span exporter as fallback")
                else:
                    self._export_mode = EXPORT_MODE_NONE

        except ImportError:
            logger.warning("OTLP exporter not available, spans will not be exported")
            self._export_mode = EXPORT_MODE_NONE

    @property
    def export_mode(self) -> str:
        """Current export mode: 'otlp', 'console', or 'none'."""
        return self._export_mode

    def _get_task_attr(self, task_id: str, key: str, default: Any = None) -> Any:
        """
        Get a task attribute value.

        Uses the internal _task_attributes dictionary instead of span._attributes
        to avoid relying on OTel SDK internal APIs.

        Args:
            task_id: Task identifier
            key: Attribute key
            default: Default value if not found

        Returns:
            Attribute value or default
        """
        if task_id in self._task_attributes:
            return self._task_attributes[task_id].get(key, default)
        return default

    def _set_task_attr(self, task_id: str, key: str, value: Any) -> None:
        """
        Set a task attribute value.

        Updates both the span (via set_attribute) and the internal tracking dict.

        Args:
            task_id: Task identifier
            key: Attribute key
            value: Attribute value
        """
        if task_id in self._active_spans:
            self._active_spans[task_id].set_attribute(key, value)
        if task_id in self._task_attributes:
            self._task_attributes[task_id][key] = value

    def _get_task_attrs(self, task_id: str) -> Dict[str, Any]:
        """
        Get all attributes for a task.

        Args:
            task_id: Task identifier

        Returns:
            Copy of task attributes dict, or empty dict if not found
        """
        return self._task_attributes.get(task_id, {}).copy()

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
        **extra_attributes: Any) -> trace.SpanContext:
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
        if parent_id:
            attributes[TASK_PARENT_ID] = parent_id

        # Initialize progress tracking
        attributes[TASK_PERCENT_COMPLETE] = 0.0
        attributes[TASK_SUBTASK_COUNT] = 0
        attributes[TASK_SUBTASK_COMPLETED] = 0
        
        attributes.update(extra_attributes)
        
        # Add OTel GenAI operation name
        attributes["gen_ai.operation.name"] = "task"

        # Apply dual-emit mapping
        attributes = transform_attributes(attributes)

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

        # Create span name following OTel conventions:
        # - Use dot separators (not colons)
        # - Keep type in name (low cardinality)
        # - ID goes in attributes (task.id), not span name (high cardinality)
        span_name = f"contextcore.task.{task_type}"

        # Start the span
        span = self._tracer.start_span(
            name=span_name,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            links=links,
            context=parent_context)

        # Add creation event
        span.add_event(
            "task.created",
            attributes={
                "task.title": title,
                "task.type": task_type,
            }
        )

        # Store span and its attributes
        self._active_spans[task_id] = span
        self._span_contexts[task_id] = span.get_span_context()
        self._task_attributes[task_id] = attributes.copy()

        # Track parent-child relationships
        if parent_id:
            self._parent_map[task_id] = parent_id
            if parent_id not in self._children_map:
                self._children_map[parent_id] = []
            self._children_map[parent_id].append(task_id)
            # Increment parent's subtask count
            self._increment_subtask_count(parent_id)

        # Persist state
        self._save_state()

        # Log to Loki
        self._task_logger.log_task_created(
            task_id=task_id,
            title=title,
            task_type=task_type,
            priority=priority,
            assignee=assignee,
            story_points=story_points,
            sprint_id=sprint_id,
            parent_id=parent_id)

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

        # Get current status from our attributes dict
        old_status = self._get_task_attr(task_id, TASK_STATUS, "unknown")

        # Add status change event
        span.add_event(
            "task.status_changed",
            attributes={
                "from": old_status,
                "to": new_status,
            }
        )

        # Update attribute in both span and our tracking dict
        self._set_task_attr(task_id, TASK_STATUS, new_status)

        # Handle blocked status
        if new_status == TaskStatus.BLOCKED.value:
            span.set_status(Status(StatusCode.ERROR, "Task blocked"))
        elif old_status == TaskStatus.BLOCKED.value:
            span.set_status(Status(StatusCode.OK))

        self._save_state()

        # Log to Loki
        task_type = self._get_task_attr(task_id, TASK_TYPE)
        sprint_id = self._get_task_attr(task_id, SPRINT_ID)

        self._task_logger.log_status_changed(
            task_id=task_id,
            from_status=old_status,
            to_status=new_status,
            task_type=task_type,
            sprint_id=sprint_id)

        logger.info(f"Task {task_id}: {old_status} → {new_status}")

    def block_task(
        self,
        task_id: str,
        reason: str,
        blocked_by: Optional[str] = None) -> None:
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
            self._set_task_attr(task_id, TASK_BLOCKED_BY, blocked_by)

        span.add_event("task.blocked", attributes=event_attrs)
        self._set_task_attr(task_id, TASK_STATUS, TaskStatus.BLOCKED.value)
        span.set_status(Status(StatusCode.ERROR, f"Blocked: {reason}"))

        self._save_state()

        # Log to Loki
        task_type = self._get_task_attr(task_id, TASK_TYPE)
        sprint_id = self._get_task_attr(task_id, SPRINT_ID)

        self._task_logger.log_blocked(
            task_id=task_id,
            reason=reason,
            blocked_by=blocked_by,
            task_type=task_type,
            sprint_id=sprint_id)

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
        self._set_task_attr(task_id, TASK_STATUS, new_status)
        span.set_status(Status(StatusCode.OK))

        self._save_state()

        # Log to Loki
        task_type = self._get_task_attr(task_id, TASK_TYPE)
        sprint_id = self._get_task_attr(task_id, SPRINT_ID)

        self._task_logger.log_unblocked(
            task_id=task_id,
            task_type=task_type,
            sprint_id=sprint_id)

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

        old_assignee = self._get_task_attr(task_id, TASK_ASSIGNEE)

        span.add_event(
            "task.assigned",
            attributes={
                "from": old_assignee or "unassigned",
                "to": assignee,
            }
        )
        self._set_task_attr(task_id, TASK_ASSIGNEE, assignee)

        self._save_state()
        logger.info(f"Task {task_id} assigned to {assignee}")

    def complete_task(self, task_id: str) -> None:
        """
        Complete a task (ends the span with OK status).

        Also updates parent's progress if this task has a parent.

        Args:
            task_id: Task identifier
        """
        span = self._get_span(task_id)
        if not span:
            return

        # Mark as 100% complete
        self._set_task_attr(task_id, TASK_PERCENT_COMPLETE, 100.0)
        span.add_event("task.completed")
        self._set_task_attr(task_id, TASK_STATUS, TaskStatus.DONE.value)
        span.set_status(Status(StatusCode.OK))
        span.end()

        # Get task info before removing span (from our tracking dict)
        task_type = self._get_task_attr(task_id, TASK_TYPE)
        sprint_id = self._get_task_attr(task_id, SPRINT_ID)
        story_points = self._get_task_attr(task_id, TASK_STORY_POINTS)

        # Update parent's progress
        if task_id in self._parent_map:
            parent_id = self._parent_map[task_id]
            self._update_parent_progress(parent_id, completed=True)

        # Remove from active spans but keep context for linking
        del self._active_spans[task_id]
        # Also clean up attributes tracking (keep for a bit for any late lookups)
        self._task_attributes.pop(task_id, None)

        # Archive completed span state
        self._state_manager.remove_span(task_id)

        # Log to Loki
        self._task_logger.log_completed(
            task_id=task_id,
            task_type=task_type,
            story_points=story_points,
            sprint_id=sprint_id)

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
        self._set_task_attr(task_id, TASK_STATUS, TaskStatus.CANCELLED.value)
        span.set_status(Status(StatusCode.OK))
        span.end()

        # Get task info before removing (from our tracking dict)
        task_type = self._get_task_attr(task_id, TASK_TYPE)
        sprint_id = self._get_task_attr(task_id, SPRINT_ID)

        del self._active_spans[task_id]
        self._task_attributes.pop(task_id, None)

        # Archive cancelled span state
        self._state_manager.remove_span(task_id)

        # Log to Loki
        self._task_logger.log_cancelled(
            task_id=task_id,
            reason=reason,
            task_type=task_type,
            sprint_id=sprint_id)

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

    def _record_exception(
        self,
        span: Span,
        exc: BaseException,
        task_id: Optional[str] = None,
    ) -> None:
        """
        Record an exception on a span with OTel standard attributes.

        Adds an event named "exception" with:
        - exception.type: Fully qualified exception class name
        - exception.message: Exception message string
        - exception.stacktrace: Full stack trace

        Also sets the span status to ERROR.

        See: https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/
        """
        # record_exception is a standard OTel SDK method that handles
        # exception.type, exception.message, and exception.stacktrace
        span.record_exception(exc)
        span.set_status(Status(
            StatusCode.ERROR,
            f"{type(exc).__name__}: {exc}",
        ))
        if task_id:
            logger.debug(f"Recorded exception on task {task_id}: {exc}")

    def record_task_exception(
        self,
        task_id: str,
        exc: BaseException,
    ) -> None:
        """
        Record an exception against a task's span (public API).

        Use this to record errors that occur during task execution,
        e.g., build failures, test failures, deployment errors.

        Args:
            task_id: Task identifier
            exc: The exception to record
        """
        span = self._get_span(task_id)
        if span:
            self._record_exception(span, exc, task_id)

    def _increment_subtask_count(self, parent_id: str) -> None:
        """Increment subtask count on parent span."""
        span = self._get_span(parent_id)
        if not span:
            return

        current = self._get_task_attr(parent_id, TASK_SUBTASK_COUNT, 0)
        self._set_task_attr(parent_id, TASK_SUBTASK_COUNT, current + 1)

    def _update_parent_progress(self, parent_id: str, completed: bool = True) -> None:
        """
        Update parent's progress when a child completes.

        Uses simple count method: percent = (completed / total) * 100

        Args:
            parent_id: Parent task ID
            completed: Whether child was completed (vs cancelled)
        """
        span = self._get_span(parent_id)
        if not span:
            return

        # Get current counts from our tracking dict
        subtask_count = self._get_task_attr(parent_id, TASK_SUBTASK_COUNT, 0)
        subtask_completed = self._get_task_attr(parent_id, TASK_SUBTASK_COMPLETED, 0)
        task_type = self._get_task_attr(parent_id, TASK_TYPE)
        sprint_id = self._get_task_attr(parent_id, SPRINT_ID)

        # Increment completed count
        if completed:
            subtask_completed += 1
            self._set_task_attr(parent_id, TASK_SUBTASK_COMPLETED, subtask_completed)

        # Calculate percent complete (simple count method)
        if subtask_count > 0:
            percent = (subtask_completed / subtask_count) * 100
            self._set_task_attr(parent_id, TASK_PERCENT_COMPLETE, percent)

            # Add progress event
            span.add_event(
                "task.progress_updated",
                attributes={
                    "subtask_completed": subtask_completed,
                    "subtask_count": subtask_count,
                    "percent_complete": percent,
                }
            )

            # Log to Loki for metrics derivation
            self._task_logger.log_progress_updated(
                task_id=parent_id,
                percent_complete=percent,
                task_type=task_type,
                sprint_id=sprint_id,
                source="subtask",
                subtask_completed=subtask_completed,
                subtask_count=subtask_count)

            logger.info(f"Task {parent_id}: {subtask_completed}/{subtask_count} ({percent:.1f}%)")

    def set_progress(self, task_id: str, percent: float) -> None:
        """
        Manually set task progress percentage.

        Use for tasks without subtasks where progress is tracked manually.

        Args:
            task_id: Task identifier
            percent: Progress percentage (0-100)
        """
        span = self._get_span(task_id)
        if not span:
            return

        percent = max(0.0, min(100.0, percent))  # Clamp to 0-100
        self._set_task_attr(task_id, TASK_PERCENT_COMPLETE, percent)
        span.add_event(
            "task.progress_updated",
            attributes={"percent_complete": percent, "source": "manual"}
        )

        self._save_state()

        # Get task info for logging (from our tracking dict)
        task_type = self._get_task_attr(task_id, TASK_TYPE)
        sprint_id = self._get_task_attr(task_id, SPRINT_ID)

        # Log to Loki for metrics derivation
        self._task_logger.log_progress_updated(
            task_id=task_id,
            percent_complete=percent,
            task_type=task_type,
            sprint_id=sprint_id,
            source="manual")

        logger.info(f"Task {task_id} progress: {percent:.1f}%")

    def get_progress(self, task_id: str) -> Optional[float]:
        """
        Get current progress percentage for a task.

        Args:
            task_id: Task identifier

        Returns:
            Progress percentage (0-100) or None if task not found
        """
        if task_id not in self._active_spans:
            logger.warning(f"Task {task_id} not found in active spans")
            return None

        return self._get_task_attr(task_id, TASK_PERCENT_COMPLETE, 0.0)

    def _load_state(self) -> None:
        """
        Load persisted span state from disk.

        Reconstructs parent-child relationships and span contexts from saved state.
        Note: OTel spans cannot be fully reconstructed, but we restore enough
        context for linking and progress tracking.
        """
        saved_states = self._state_manager.get_active_spans()

        for task_id, state in saved_states.items():
            # Restore span context for linking
            from opentelemetry.trace import SpanContext, TraceFlags
            from contextcore.state import parse_trace_id, parse_span_id

            try:
                span_context = SpanContext(
                    trace_id=parse_trace_id(state.trace_id),
                    span_id=parse_span_id(state.span_id),
                    is_remote=False,
                    trace_flags=TraceFlags(0x01),  # SAMPLED
                )
                self._span_contexts[task_id] = span_context

                # Restore parent-child relationships
                parent_id = state.attributes.get(TASK_PARENT_ID)
                if parent_id:
                    self._parent_map[task_id] = parent_id
                    if parent_id not in self._children_map:
                        self._children_map[parent_id] = []
                    if task_id not in self._children_map[parent_id]:
                        self._children_map[parent_id].append(task_id)

                logger.debug(f"Restored state for task: {task_id}")

            except Exception as e:
                logger.warning(f"Failed to restore state for {task_id}: {e}")

    def _save_state(self) -> None:
        """
        Persist active span state to disk.

        Saves span metadata for restoration across process restarts.
        """
        for task_id, span in self._active_spans.items():
            try:
                ctx = span.get_span_context()

                # Get parent span ID if exists
                parent_span_id = None
                if task_id in self._parent_map:
                    parent_id = self._parent_map[task_id]
                    if parent_id in self._span_contexts:
                        parent_span_id = format_span_id(self._span_contexts[parent_id].span_id)

                # Build attributes dict from our tracking dict (avoids span._attributes internal API)
                attributes = self._get_task_attrs(task_id)

                # Build events list from span (if accessible)
                events = []
                if hasattr(span, '_events'):
                    for event in span._events:
                        events.append({
                            "name": event.name,
                            "timestamp": datetime.fromtimestamp(
                                event.timestamp / 1e9, tz=timezone.utc
                            ).isoformat() if event.timestamp else None,
                            "attributes": dict(event.attributes) if event.attributes else {},
                        })

                # Get span status
                status = "UNSET"
                status_desc = None
                if hasattr(span, '_status') and span._status:
                    status = span._status.status_code.name
                    status_desc = span._status.description

                state = SpanState(
                    task_id=task_id,
                    span_name=span.name,
                    trace_id=format_trace_id(ctx.trace_id),
                    span_id=format_span_id(ctx.span_id),
                    parent_span_id=parent_span_id,
                    start_time=datetime.fromtimestamp(
                        span.start_time / 1e9, tz=timezone.utc
                    ).isoformat() if hasattr(span, 'start_time') and span.start_time else datetime.now(timezone.utc).isoformat(),
                    attributes=attributes,
                    events=events,
                    status=status,
                    status_description=status_desc)

                self._state_manager.save_span(state)

            except Exception as e:
                # Record exception on the task span with OTel standard attributes
                self._record_exception(span, e, task_id)
                logger.warning(f"Failed to save state for {task_id}: {e}")

    def shutdown(self) -> None:
        """
        Flush and shutdown the tracker.

        Safe to call multiple times - subsequent calls are no-ops.
        Also called automatically at process exit via atexit.
        """
        if getattr(self, '_shutdown_called', False):
            return

        self._shutdown_called = True

        try:
            # Unregister atexit handler to avoid duplicate shutdown
            atexit.unregister(self._atexit_shutdown)
        except Exception:
            pass  # atexit.unregister may fail if not registered

        try:
            self._provider.force_flush(timeout_millis=5000)
            self._provider.shutdown()
            logger.debug("TaskTracker shutdown complete")
        except Exception as e:
            logger.warning(f"Error during TaskTracker shutdown: {e}")


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
        planned_points: Optional[int] = None) -> trace.SpanContext:
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

        # Sprint span name follows OTel conventions:
        # - Use dot separator (not colon)
        # - ID goes in attributes (sprint.id), not span name
        span = self._tracer.start_span(
            name="contextcore.sprint",
            kind=SpanKind.INTERNAL,
            attributes=attributes)

        span.add_event("sprint.started", attributes={"name": name})

        self._active_sprints[sprint_id] = span
        logger.info(f"Started sprint: {sprint_id} ({name})")

        return span.get_span_context()

    def end_sprint(
        self,
        sprint_id: str,
        completed_points: Optional[int] = None,
        notes: Optional[str] = None) -> None:
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
