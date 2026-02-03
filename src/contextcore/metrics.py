"""
Derived metrics from task spans.

Generates standard project management metrics from task span data:
- Lead time: time from task creation to completion
- Cycle time: time from in_progress to completion
- Throughput: tasks completed per time period
- WIP: current work in progress count
- Velocity: story points per sprint
- Blocked time: percentage of time tasks are blocked

These metrics are exposed via OpenTelemetry for Prometheus/Mimir scraping.
"""

from __future__ import annotations

import atexit
import logging
import os
import socket
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource

from contextcore.contracts.metrics import MetricName
from contextcore.contracts.timeouts import (
    OTEL_FLUSH_TIMEOUT_MS,
    OTEL_ENDPOINT_CHECK_TIMEOUT_S,
    OTEL_DEFAULT_GRPC_PORT,
)
from contextcore.detector import (
    get_telemetry_sdk_attributes,
    get_service_attributes,
    get_host_attributes,
)
from contextcore.state import StateManager, SpanState

logger = logging.getLogger(__name__)

# Export mode tracking
METRICS_EXPORT_MODE_OTLP = "otlp"
METRICS_EXPORT_MODE_CONSOLE = "console"
METRICS_EXPORT_MODE_NONE = "none"

# Metric names from central contracts (ensures consistency)
LEAD_TIME_METRIC = MetricName.TASK_LEAD_TIME.value
CYCLE_TIME_METRIC = MetricName.TASK_CYCLE_TIME.value
BLOCKED_TIME_METRIC = MetricName.TASK_BLOCKED_TIME.value
WIP_METRIC = MetricName.TASK_WIP.value
THROUGHPUT_METRIC = MetricName.TASK_THROUGHPUT.value
VELOCITY_METRIC = MetricName.SPRINT_VELOCITY.value
STORY_POINTS_COMPLETED = MetricName.TASK_STORY_POINTS_COMPLETED.value
TASK_COUNT_BY_STATUS = MetricName.TASK_COUNT_BY_STATUS.value
TASK_COUNT_BY_TYPE = MetricName.TASK_COUNT_BY_TYPE.value


class TaskMetrics:
    """
    Generate project management metrics from task span state.

    Reads from StateManager to compute metrics across process restarts.
    Exposes metrics via OTel metrics API for Prometheus scraping.
    """

    def __init__(
        self,
        project: str,
        service_name: str = "contextcore-metrics",
        state_dir: Optional[str] = None,
        export_interval_ms: int = 60000,
        exporter: Optional[Any] = None,
    ):
        """
        Initialize metrics collector.

        Args:
            project: Project identifier
            service_name: OTel service name
            state_dir: Directory for span state (shares with TaskTracker)
            export_interval_ms: How often to export metrics
            exporter: Custom metric exporter (defaults to OTLP)
        """
        self.project = project
        self._state = StateManager(project, state_dir)
        self._export_mode = METRICS_EXPORT_MODE_NONE
        self._shutdown_called = False

        # Initialize OTel metrics with standard resource attributes
        resource_attrs = {
            # Standard OTel SDK attributes
            **get_telemetry_sdk_attributes(),
            # Service identification (override service.name if provided)
            **get_service_attributes(service_name=service_name),
            # Host/process/OS context
            **get_host_attributes(),
            # ContextCore project attributes
            "project.id": project,
        }
        resource = Resource.create(resource_attrs)

        # Set up exporter
        if exporter:
            reader = PeriodicExportingMetricReader(
                exporter,
                export_interval_millis=export_interval_ms,
            )
            self._export_mode = METRICS_EXPORT_MODE_OTLP
        else:
            reader = self._setup_default_reader(export_interval_ms)

        # Create provider without setting global (avoids conflicts with other metrics users)
        self._provider = MeterProvider(resource=resource, metric_readers=[reader] if reader else [])
        self._meter = self._provider.get_meter("contextcore.metrics")

        # Create instruments
        self._setup_instruments()

        # Register shutdown handler
        atexit.register(self._atexit_shutdown)

    def _atexit_shutdown(self) -> None:
        """Shutdown handler called at process exit."""
        try:
            self._provider.force_flush(timeout_millis=OTEL_FLUSH_TIMEOUT_MS)
            self._provider.shutdown()
        except Exception as e:
            logger.debug(f"Error during metrics atexit shutdown: {e}")

    def _check_endpoint_available(
        self, endpoint: str, timeout: float = OTEL_ENDPOINT_CHECK_TIMEOUT_S
    ) -> bool:
        """
        Check if OTLP endpoint is reachable.

        Args:
            endpoint: Host:port string
            timeout: Connection timeout in seconds

        Returns:
            True if endpoint accepts connections
        """
        try:
            if "://" in endpoint:
                from urllib.parse import urlparse
                parsed = urlparse(endpoint)
                host = parsed.hostname or "localhost"
                port = parsed.port or OTEL_DEFAULT_GRPC_PORT
            else:
                parts = endpoint.split(":")
                host = parts[0] if parts else "localhost"
                port = int(parts[1]) if len(parts) > 1 else OTEL_DEFAULT_GRPC_PORT

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0

        except (socket.timeout, socket.error, ValueError, OSError) as e:
            logger.debug(f"OTLP metrics endpoint check failed: {e}")
            return False

    def _setup_default_reader(self, export_interval_ms: int) -> Optional[PeriodicExportingMetricReader]:
        """
        Set up default OTLP metric exporter with fallback handling.

        Checks endpoint availability first. Falls back to console exporter if
        CONTEXTCORE_FALLBACK_CONSOLE is set and OTLP is unavailable.
        """
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
        fallback_to_console = os.environ.get("CONTEXTCORE_FALLBACK_CONSOLE", "").lower() in ("1", "true", "yes")

        try:
            from contextcore.exporter_factory import create_metric_exporter

            if self._check_endpoint_available(endpoint):
                exporter = create_metric_exporter(endpoint=endpoint)
                self._export_mode = METRICS_EXPORT_MODE_OTLP
                logger.info(f"Configured OTLP metrics exporter to {endpoint}")
                return PeriodicExportingMetricReader(
                    exporter,
                    export_interval_millis=export_interval_ms,
                )
            else:
                logger.warning(
                    f"OTLP metrics endpoint {endpoint} not reachable. "
                    f"Metrics will not be exported."
                )
                if fallback_to_console:
                    self._export_mode = METRICS_EXPORT_MODE_CONSOLE
                    logger.info("Enabled console metrics exporter as fallback")
                    return PeriodicExportingMetricReader(
                        ConsoleMetricExporter(),
                        export_interval_millis=export_interval_ms,
                    )
                return None

        except ImportError:
            logger.warning("OTLP metric exporter not available")
            return None

    @property
    def export_mode(self) -> str:
        """Current export mode: 'otlp', 'console', or 'none'."""
        return self._export_mode

    def shutdown(self) -> None:
        """
        Flush and shutdown the metrics provider.

        Safe to call multiple times.
        """
        if self._shutdown_called:
            return

        self._shutdown_called = True

        try:
            atexit.unregister(self._atexit_shutdown)
        except Exception:
            pass

        try:
            self._provider.force_flush(timeout_millis=OTEL_FLUSH_TIMEOUT_MS)
            self._provider.shutdown()
            logger.debug("TaskMetrics shutdown complete")
        except Exception as e:
            logger.warning(f"Error during TaskMetrics shutdown: {e}")

    def _setup_instruments(self) -> None:
        """Create OTel metric instruments."""
        # Histograms for timing metrics
        self._lead_time = self._meter.create_histogram(
            name=LEAD_TIME_METRIC,
            description="Time from task creation to completion",
            unit="s",
        )

        self._cycle_time = self._meter.create_histogram(
            name=CYCLE_TIME_METRIC,
            description="Time from task start (in_progress) to completion",
            unit="s",
        )

        self._blocked_time = self._meter.create_histogram(
            name=BLOCKED_TIME_METRIC,
            description="Total time task was blocked",
            unit="s",
        )

        # Gauges for current state
        self._wip_gauge = self._meter.create_observable_gauge(
            name=WIP_METRIC,
            callbacks=[self._observe_wip],
            description="Current work in progress count",
            unit="{tasks}",
        )

        self._status_gauge = self._meter.create_observable_gauge(
            name=TASK_COUNT_BY_STATUS,
            callbacks=[self._observe_by_status],
            description="Task count by status",
            unit="{tasks}",
        )

        self._type_gauge = self._meter.create_observable_gauge(
            name=TASK_COUNT_BY_TYPE,
            callbacks=[self._observe_by_type],
            description="Task count by type",
            unit="{tasks}",
        )

        # Counters for throughput
        self._throughput = self._meter.create_counter(
            name=THROUGHPUT_METRIC,
            description="Tasks completed",
            unit="{tasks}",
        )

        self._points_completed = self._meter.create_counter(
            name=STORY_POINTS_COMPLETED,
            description="Story points completed",
            unit="{points}",
        )

    def _observe_wip(self, options: metrics.CallbackOptions) -> Iterable[metrics.Observation]:
        """Callback for WIP gauge."""
        active = self._state.get_active_spans()
        wip_count = sum(
            1 for s in active.values()
            if s.attributes.get("task.status") == "in_progress"
        )
        yield metrics.Observation(
            wip_count,
            {"project.id": self.project}
        )

    def _observe_by_status(self, options: metrics.CallbackOptions) -> Iterable[metrics.Observation]:
        """Callback for status breakdown gauge."""
        active = self._state.get_active_spans()
        counts: Dict[str, int] = {}

        for state in active.values():
            status = state.attributes.get("task.status", "unknown")
            counts[status] = counts.get(status, 0) + 1

        for status, count in counts.items():
            yield metrics.Observation(
                count,
                {"project.id": self.project, "task.status": status}
            )

    def _observe_by_type(self, options: metrics.CallbackOptions) -> Iterable[metrics.Observation]:
        """Callback for type breakdown gauge."""
        active = self._state.get_active_spans()
        counts: Dict[str, int] = {}

        for state in active.values():
            task_type = state.attributes.get("task.type", "task")
            counts[task_type] = counts.get(task_type, 0) + 1

        for task_type, count in counts.items():
            yield metrics.Observation(
                count,
                {"project.id": self.project, "task.type": task_type}
            )

    def record_completion(self, span_state: SpanState) -> None:
        """
        Record metrics when a task completes.

        Args:
            span_state: Completed span state with timing info
        """
        attrs = span_state.attributes
        labels = {
            "project.id": self.project,
            "task.type": attrs.get("task.type", "task"),
            "task.priority": attrs.get("task.priority", "medium"),
        }

        # Lead time (creation to completion)
        if span_state.start_time:
            start = datetime.fromisoformat(span_state.start_time)
            end = datetime.now(timezone.utc)
            lead_time = (end - start).total_seconds()
            self._lead_time.record(lead_time, labels)

        # Cycle time (from first in_progress to completion)
        cycle_start = self._find_status_event(span_state.events, "in_progress")
        if cycle_start:
            start = datetime.fromisoformat(cycle_start)
            end = datetime.now(timezone.utc)
            cycle_time = (end - start).total_seconds()
            self._cycle_time.record(cycle_time, labels)

        # Blocked time (total time spent blocked)
        blocked_time = self._calculate_blocked_time(span_state.events)
        if blocked_time > 0:
            self._blocked_time.record(blocked_time, labels)

        # Throughput counter
        self._throughput.add(1, labels)

        # Story points
        points = attrs.get("task.story_points")
        if points:
            self._points_completed.add(int(points), labels)

    def _find_status_event(self, events: List[Dict[str, Any]], target_status: str) -> Optional[str]:
        """Find timestamp when task first reached a status."""
        for event in events:
            if event.get("name") == "task.status_changed":
                if event.get("attributes", {}).get("to") == target_status:
                    return event.get("timestamp")
        return None

    def _calculate_blocked_time(self, events: List[Dict[str, Any]]) -> float:
        """Calculate total seconds task was blocked."""
        blocked_time = 0.0
        block_start: Optional[datetime] = None

        for event in events:
            name = event.get("name", "")
            timestamp = event.get("timestamp")

            if not timestamp:
                continue

            ts = datetime.fromisoformat(timestamp)

            if name == "task.blocked":
                block_start = ts
            elif name == "task.unblocked" and block_start:
                blocked_time += (ts - block_start).total_seconds()
                block_start = None

        # If still blocked, count up to now
        if block_start:
            blocked_time += (datetime.now(timezone.utc) - block_start).total_seconds()

        return blocked_time

    def get_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get summary metrics for a time period.

        Args:
            days: Number of days to look back

        Returns:
            Dict with computed metrics
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        completed = self._state.get_completed_spans(since=since)
        active = self._state.get_active_spans()

        # Compute aggregates
        lead_times: List[float] = []
        cycle_times: List[float] = []
        total_points = 0

        for state in completed:
            if state.start_time:
                start = datetime.fromisoformat(state.start_time)
                # Use end_time from completed span
                end_time_str = state.attributes.get("end_time")
                if end_time_str:
                    end = datetime.fromisoformat(end_time_str)
                    lead_times.append((end - start).total_seconds())

            cycle_start = self._find_status_event(state.events, "in_progress")
            if cycle_start:
                start = datetime.fromisoformat(cycle_start)
                end_time_str = state.attributes.get("end_time")
                if end_time_str:
                    end = datetime.fromisoformat(end_time_str)
                    cycle_times.append((end - start).total_seconds())

            points = state.attributes.get("task.story_points")
            if points:
                total_points += int(points)

        # Count by status
        status_counts: Dict[str, int] = {}
        for state in active.values():
            status = state.attributes.get("task.status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "period_days": days,
            "tasks_completed": len(completed),
            "tasks_active": len(active),
            "story_points_completed": total_points,
            "avg_lead_time_hours": (sum(lead_times) / len(lead_times) / 3600) if lead_times else None,
            "avg_cycle_time_hours": (sum(cycle_times) / len(cycle_times) / 3600) if cycle_times else None,
            "wip": status_counts.get("in_progress", 0),
            "blocked": status_counts.get("blocked", 0),
            "status_breakdown": status_counts,
        }


def compute_velocity(
    sprints: List[Dict[str, Any]],
    num_sprints: int = 5,
) -> Dict[str, Any]:
    """
    Compute velocity metrics from sprint data.

    Args:
        sprints: List of sprint data with completed_points
        num_sprints: Number of sprints to average

    Returns:
        Dict with velocity metrics
    """
    recent = sprints[-num_sprints:] if len(sprints) > num_sprints else sprints

    if not recent:
        return {
            "average_velocity": 0,
            "trend": "unknown",
            "sprints_analyzed": 0,
        }

    velocities = [s.get("completed_points", 0) for s in recent]
    avg = sum(velocities) / len(velocities)

    # Determine trend
    if len(velocities) >= 3:
        first_half = sum(velocities[:len(velocities)//2]) / (len(velocities)//2)
        second_half = sum(velocities[len(velocities)//2:]) / (len(velocities) - len(velocities)//2)
        if second_half > first_half * 1.1:
            trend = "increasing"
        elif second_half < first_half * 0.9:
            trend = "decreasing"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    return {
        "average_velocity": avg,
        "recent_velocities": velocities,
        "trend": trend,
        "sprints_analyzed": len(recent),
    }
