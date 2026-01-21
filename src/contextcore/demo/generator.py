"""
Historical Task Tracker and Demo Data Generator.

Extends TaskTracker with time manipulation support to create backdated spans
for demonstrating project-to-operations correlation.

Emits BOTH spans (for Tempo) AND logs (for Loki) to support the full
ContextCore dual-telemetry architecture.
"""

from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Link, SpanKind, Status, StatusCode

from contextcore.tracker import TaskTracker, TaskType, TaskStatus

logger = logging.getLogger(__name__)


class HistoricalTaskLogger:
    """
    Logger that collects structured log entries with historical timestamps.

    Unlike TaskLogger which emits logs immediately, this class collects
    log entries for batch export alongside spans.
    """

    def __init__(self, project: str, service_name: str = "contextcore"):
        """
        Initialize historical logger.

        Args:
            project: Project identifier
            service_name: Service name for log attribution
        """
        self.project = project
        self.service_name = service_name
        self._logs: List[Dict[str, Any]] = []

    def _emit(
        self,
        event: str,
        task_id: str,
        timestamp: datetime,
        level: str = "info",
        task_type: Optional[str] = None,
        task_title: Optional[str] = None,
        sprint_id: Optional[str] = None,
        **extra_fields: Any,
    ) -> None:
        """Collect a structured log entry with historical timestamp."""
        entry = {
            "timestamp": timestamp.isoformat(),
            "level": level,
            "event": event,
            "service": self.service_name,
            "project_id": self.project,
            "task_id": task_id,
            "trigger": "demo",
        }

        if task_type:
            entry["task_type"] = task_type
        if task_title:
            entry["task_title"] = task_title
        if sprint_id:
            entry["sprint_id"] = sprint_id

        entry.update(extra_fields)
        self._logs.append(entry)

    def log_task_created(
        self,
        task_id: str,
        title: str,
        timestamp: datetime,
        task_type: str = "task",
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        story_points: Optional[int] = None,
        sprint_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> None:
        """Log task creation event."""
        self._emit(
            event="task.created",
            task_id=task_id,
            timestamp=timestamp,
            task_type=task_type,
            task_title=title,
            sprint_id=sprint_id,
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
        timestamp: datetime,
        task_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
    ) -> None:
        """Log status transition event."""
        self._emit(
            event="task.status_changed",
            task_id=task_id,
            timestamp=timestamp,
            task_type=task_type,
            sprint_id=sprint_id,
            from_status=from_status,
            to_status=to_status,
        )

    def log_blocked(
        self,
        task_id: str,
        reason: str,
        timestamp: datetime,
        blocked_by: Optional[str] = None,
        task_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
    ) -> None:
        """Log task blocked event."""
        self._emit(
            event="task.blocked",
            task_id=task_id,
            timestamp=timestamp,
            task_type=task_type,
            sprint_id=sprint_id,
            level="warn",
            reason=reason,
            blocked_by=blocked_by,
        )

    def log_unblocked(
        self,
        task_id: str,
        timestamp: datetime,
        task_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
    ) -> None:
        """Log task unblocked event."""
        self._emit(
            event="task.unblocked",
            task_id=task_id,
            timestamp=timestamp,
            task_type=task_type,
            sprint_id=sprint_id,
        )

    def log_completed(
        self,
        task_id: str,
        timestamp: datetime,
        task_type: Optional[str] = None,
        story_points: Optional[int] = None,
        sprint_id: Optional[str] = None,
    ) -> None:
        """Log task completion event."""
        self._emit(
            event="task.completed",
            task_id=task_id,
            timestamp=timestamp,
            task_type=task_type,
            sprint_id=sprint_id,
            story_points=story_points,
        )

    def log_progress_updated(
        self,
        task_id: str,
        percent_complete: float,
        timestamp: datetime,
        task_type: Optional[str] = None,
        sprint_id: Optional[str] = None,
        source: str = "manual",
    ) -> None:
        """Log task progress update event."""
        self._emit(
            event="task.progress_updated",
            task_id=task_id,
            timestamp=timestamp,
            task_type=task_type,
            sprint_id=sprint_id,
            percent_complete=percent_complete,
            source=source,
        )

    def get_logs(self) -> List[Dict[str, Any]]:
        """Get all collected log entries."""
        return self._logs.copy()

    def clear(self) -> None:
        """Clear collected logs."""
        self._logs.clear()


class HistoricalTaskTracker(TaskTracker):
    """
    TaskTracker with support for historical (backdated) spans.

    Extends the base TaskTracker to allow creating spans with arbitrary
    start and end times, enabling generation of realistic demo data.

    Emits BOTH spans (Tempo) AND logs (Loki) for full observability.
    """

    def __init__(
        self,
        project: str,
        service_name: str = "contextcore",
        exporter: Optional[SpanExporter] = None,
    ):
        """
        Initialize historical tracker.

        Args:
            project: Project identifier
            service_name: OTel service name
            exporter: Custom span exporter (default: in-memory for batch export)
        """
        self.project = project
        self._spans: List[Dict[str, Any]] = []  # Store spans for batch export

        # Initialize historical logger for Loki
        self._task_logger = HistoricalTaskLogger(project=project, service_name=service_name)

        # Track task metadata for logging
        self._task_metadata: Dict[str, Dict[str, Any]] = {}

        # Initialize OTel with custom exporter
        resource = Resource.create({
            "service.name": service_name,
            "service.namespace": "contextcore",
            "project.id": project,
        })

        self._provider = TracerProvider(resource=resource)

        if exporter:
            self._provider.add_span_processor(BatchSpanProcessor(exporter))
        else:
            # Use collecting exporter for later batch export
            self._collector = SpanCollector()
            self._provider.add_span_processor(BatchSpanProcessor(self._collector))

        trace.set_tracer_provider(self._provider)
        self._tracer = trace.get_tracer("contextcore.demo")

        # Active spans tracking
        self._active_spans: Dict[str, trace.Span] = {}
        self._span_contexts: Dict[str, trace.SpanContext] = {}

    def start_task_at(
        self,
        task_id: str,
        title: str,
        start_time: datetime,
        task_type: str = "task",
        status: str = "todo",
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        story_points: Optional[int] = None,
        labels: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        sprint_id: Optional[str] = None,
        **extra_attributes: Any,
    ) -> trace.SpanContext:
        """
        Start a task span at a specific historical timestamp.

        Args:
            task_id: Unique task identifier
            title: Task title
            start_time: Historical start timestamp
            task_type: epic|story|task|subtask|bug
            status: Initial status
            priority: Priority level
            assignee: Assigned person
            story_points: Story point estimate
            labels: Task labels
            parent_id: Parent task ID
            depends_on: Dependency task IDs
            sprint_id: Sprint identifier
            **extra_attributes: Additional span attributes

        Returns:
            SpanContext for the created span
        """
        if task_id in self._active_spans:
            logger.warning(f"Task {task_id} already active")
            return self._active_spans[task_id].get_span_context()

        # Build attributes
        attributes: Dict[str, Any] = {
            "task.id": task_id,
            "task.type": task_type,
            "task.title": title,
            "task.status": status,
            "project.id": self.project,
        }

        if priority:
            attributes["task.priority"] = priority
        if assignee:
            attributes["task.assignee"] = assignee
        if story_points is not None:
            attributes["task.story_points"] = story_points
        if labels:
            attributes["task.labels"] = labels
        if sprint_id:
            attributes["sprint.id"] = sprint_id

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

        # Get parent context
        parent_context = None
        if parent_id and parent_id in self._active_spans:
            parent_context = trace.set_span_in_context(self._active_spans[parent_id])

        # Create span with historical start time (nanoseconds)
        start_time_ns = int(start_time.timestamp() * 1e9)

        span = self._tracer.start_span(
            name=f"{task_type}:{task_id}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            links=links,
            context=parent_context,
            start_time=start_time_ns,
        )

        # Add creation event
        span.add_event(
            "task.created",
            attributes={"task.title": title, "task.type": task_type},
            timestamp=start_time_ns,
        )

        self._active_spans[task_id] = span
        self._span_contexts[task_id] = span.get_span_context()

        # Store metadata for later logging
        self._task_metadata[task_id] = {
            "task_type": task_type,
            "title": title,
            "sprint_id": sprint_id,
            "story_points": story_points,
            "status": status,
        }

        # Log to Loki
        self._task_logger.log_task_created(
            task_id=task_id,
            title=title,
            timestamp=start_time,
            task_type=task_type,
            priority=priority,
            assignee=assignee,
            story_points=story_points,
            sprint_id=sprint_id,
            parent_id=parent_id,
        )

        logger.debug(f"Started historical task: {task_id} at {start_time}")
        return span.get_span_context()

    def add_event_at(
        self,
        task_id: str,
        event_name: str,
        timestamp: datetime,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add an event to a task at a specific timestamp.

        Args:
            task_id: Task identifier
            event_name: Event name (e.g., "task.status_changed")
            timestamp: Event timestamp
            attributes: Event attributes
        """
        span = self._active_spans.get(task_id)
        if not span:
            logger.warning(f"Task {task_id} not found")
            return

        timestamp_ns = int(timestamp.timestamp() * 1e9)
        span.add_event(event_name, attributes=attributes or {}, timestamp=timestamp_ns)

    def update_status_at(
        self,
        task_id: str,
        new_status: str,
        timestamp: datetime,
    ) -> None:
        """
        Update task status at a specific timestamp.

        Args:
            task_id: Task identifier
            new_status: New status value
            timestamp: Status change timestamp
        """
        span = self._active_spans.get(task_id)
        if not span:
            logger.warning(f"Task {task_id} not found")
            return

        # Get current status from metadata
        metadata = self._task_metadata.get(task_id, {})
        old_status = metadata.get("status", "unknown")

        # Add status change event
        self.add_event_at(
            task_id,
            "task.status_changed",
            timestamp,
            {"from": old_status, "to": new_status},
        )

        span.set_attribute("task.status", new_status)

        # Update metadata
        if task_id in self._task_metadata:
            self._task_metadata[task_id]["status"] = new_status

        # Log to Loki
        self._task_logger.log_status_changed(
            task_id=task_id,
            from_status=old_status,
            to_status=new_status,
            timestamp=timestamp,
            task_type=metadata.get("task_type"),
            sprint_id=metadata.get("sprint_id"),
        )

        # Set span status for blocked
        if new_status == TaskStatus.BLOCKED.value:
            span.set_status(Status(StatusCode.ERROR, "Task blocked"))
        elif old_status == TaskStatus.BLOCKED.value:
            span.set_status(Status(StatusCode.OK))

    def block_task_at(
        self,
        task_id: str,
        reason: str,
        timestamp: datetime,
        blocked_by: Optional[str] = None,
    ) -> None:
        """
        Block a task at a specific timestamp.

        Args:
            task_id: Task identifier
            reason: Blocking reason
            timestamp: Block timestamp
            blocked_by: Blocking task ID
        """
        span = self._active_spans.get(task_id)
        if not span:
            return

        event_attrs: Dict[str, Any] = {"reason": reason}
        if blocked_by:
            event_attrs["blocker_id"] = blocked_by
            span.set_attribute("task.blocked_by", blocked_by)

        self.add_event_at(task_id, "task.blocked", timestamp, event_attrs)
        span.set_attribute("task.status", TaskStatus.BLOCKED.value)
        span.set_status(Status(StatusCode.ERROR, f"Blocked: {reason}"))

        # Update metadata
        if task_id in self._task_metadata:
            self._task_metadata[task_id]["status"] = TaskStatus.BLOCKED.value

        # Log to Loki
        metadata = self._task_metadata.get(task_id, {})
        self._task_logger.log_blocked(
            task_id=task_id,
            reason=reason,
            timestamp=timestamp,
            blocked_by=blocked_by,
            task_type=metadata.get("task_type"),
            sprint_id=metadata.get("sprint_id"),
        )

    def unblock_task_at(
        self,
        task_id: str,
        timestamp: datetime,
        new_status: str = "in_progress",
    ) -> None:
        """
        Unblock a task at a specific timestamp.

        Args:
            task_id: Task identifier
            timestamp: Unblock timestamp
            new_status: Status after unblocking
        """
        span = self._active_spans.get(task_id)
        if not span:
            return

        self.add_event_at(task_id, "task.unblocked", timestamp)

        # Log unblock to Loki (before status change to capture the unblock event)
        metadata = self._task_metadata.get(task_id, {})
        self._task_logger.log_unblocked(
            task_id=task_id,
            timestamp=timestamp,
            task_type=metadata.get("task_type"),
            sprint_id=metadata.get("sprint_id"),
        )

        self.update_status_at(task_id, new_status, timestamp)
        span.set_status(Status(StatusCode.OK))

    def complete_task_at(self, task_id: str, end_time: datetime) -> None:
        """
        Complete a task at a specific timestamp.

        Args:
            task_id: Task identifier
            end_time: Completion timestamp
        """
        span = self._active_spans.get(task_id)
        if not span:
            logger.warning(f"Task {task_id} not found")
            return

        end_time_ns = int(end_time.timestamp() * 1e9)

        span.add_event("task.completed", timestamp=end_time_ns)
        span.set_attribute("task.status", TaskStatus.DONE.value)
        span.set_status(Status(StatusCode.OK))
        span.end(end_time=end_time_ns)

        # Log to Loki
        metadata = self._task_metadata.get(task_id, {})
        self._task_logger.log_completed(
            task_id=task_id,
            timestamp=end_time,
            task_type=metadata.get("task_type"),
            story_points=metadata.get("story_points"),
            sprint_id=metadata.get("sprint_id"),
        )

        # Also log progress update for metrics derivation
        self._task_logger.log_progress_updated(
            task_id=task_id,
            percent_complete=100.0,
            timestamp=end_time,
            task_type=metadata.get("task_type"),
            sprint_id=metadata.get("sprint_id"),
            source="completion",
        )

        del self._active_spans[task_id]
        self._task_metadata.pop(task_id, None)
        logger.debug(f"Completed task: {task_id} at {end_time}")

    def get_collected_spans(self) -> List[ReadableSpan]:
        """Get all spans collected by the internal exporter."""
        if hasattr(self, '_collector'):
            return self._collector.get_spans()
        return []

    def get_collected_logs(self) -> List[Dict[str, Any]]:
        """Get all logs collected by the internal logger."""
        return self._task_logger.get_logs()

    def flush(self) -> None:
        """Force flush all spans."""
        self._provider.force_flush()

    def shutdown(self) -> None:
        """Shutdown the tracer provider."""
        self._provider.force_flush()
        self._provider.shutdown()


class SpanCollector(SpanExporter):
    """Collects spans in memory for batch export."""

    def __init__(self):
        self._spans: List[ReadableSpan] = []

    def export(self, spans) -> SpanExportResult:
        self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def get_spans(self) -> List[ReadableSpan]:
        return self._spans.copy()

    def clear(self) -> None:
        self._spans.clear()


def generate_demo_data(
    project: str = "online-boutique",
    output_dir: Optional[str] = None,
    duration_months: int = 3,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate demo project data for the microservices-demo application.

    Generates BOTH spans (for Tempo) AND logs (for Loki) to support
    the full ContextCore dual-telemetry architecture.

    Args:
        project: Project identifier
        output_dir: Directory to save generated data
        duration_months: Duration of project history to generate
        seed: Random seed for reproducibility

    Returns:
        Dictionary with generation statistics
    """
    from contextcore.demo.project_data import generate_project_structure

    if seed is not None:
        random.seed(seed)

    tracker = HistoricalTaskTracker(project=project)

    # Generate project structure
    stats = generate_project_structure(
        tracker=tracker,
        duration_months=duration_months,
    )

    # Flush and collect spans
    tracker.flush()
    spans = tracker.get_collected_spans()
    logs = tracker.get_collected_logs()

    stats["total_spans"] = len(spans)
    stats["total_logs"] = len(logs)

    # Save to output directory if specified
    if output_dir:
        from contextcore.demo.exporter import save_spans_to_file, save_logs_to_file
        os.makedirs(output_dir, exist_ok=True)

        # Save spans
        spans_file = os.path.join(output_dir, "demo_spans.json")
        save_spans_to_file(spans, spans_file)
        stats["spans_file"] = spans_file

        # Save logs
        logs_file = os.path.join(output_dir, "demo_logs.json")
        save_logs_to_file(logs, logs_file)
        stats["logs_file"] = logs_file

        # Keep backward compatibility
        stats["output_file"] = spans_file

    tracker.shutdown()

    logger.info(f"Generated {stats['total_spans']} spans and {stats['total_logs']} logs for {project}")
    return stats
