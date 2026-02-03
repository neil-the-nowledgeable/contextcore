"""
Metric and label schema contracts.

Defines the canonical names for metrics, labels, and events used throughout
ContextCore. All telemetry emission and querying should use these definitions
to prevent naming drift.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field, field_validator

from contextcore.contracts.types import (
    TASK_STATUS_VALUES,
    PRIORITY_VALUES,
)


class MetricName(str, Enum):
    """
    Canonical metric names for project tracking.

    These names are appended to the project-specific prefix for project-scoped metrics,
    or used as-is for standard OTel semantic convention metrics.

    Example: with prefix "lm1_", PROGRESS becomes "lm1_progress"

    Note: Metrics prefixed with "task." or "sprint." follow OTel semantic conventions
    and are used as-is without project prefix.
    """

    # Overall project metrics (use with project prefix)
    PROGRESS = "progress"
    COMPLETION_RATE = "completion_rate"
    BLOCKED_COUNT = "blocked_count"

    # Task count metrics (use with project prefix)
    TASKS_TOTAL = "tasks_total"
    TASKS_BY_PHASE = "tasks_by_phase"
    TASKS_BY_PRIORITY = "tasks_by_priority"

    # Phase/story metrics (use with project prefix)
    PHASE_PROGRESS = "phase_progress"

    # Effort metrics (use with project prefix)
    EFFORT_POINTS_TOTAL = "effort_points_total"

    # Individual task metrics (use with project prefix)
    TASK_PERCENT_COMPLETE = "task_percent_complete"

    # Flow metrics (OTel semantic convention names, use as-is)
    # These are implemented in contextcore.metrics.TaskMetrics
    TASK_LEAD_TIME = "task.lead_time"  # Histogram: creation to completion (seconds)
    TASK_CYCLE_TIME = "task.cycle_time"  # Histogram: in_progress to completion (seconds)
    TASK_BLOCKED_TIME = "task.blocked_time"  # Histogram: total blocked duration (seconds)
    TASK_WIP = "task.wip"  # Gauge: work in progress count
    TASK_THROUGHPUT = "task.throughput"  # Counter: tasks completed
    TASK_STORY_POINTS_COMPLETED = "task.story_points_completed"  # Counter: points completed
    TASK_COUNT_BY_STATUS = "task.count_by_status"  # Gauge: breakdown by status
    TASK_COUNT_BY_TYPE = "task.count_by_type"  # Gauge: breakdown by type

    # Sprint metrics (OTel semantic convention names, use as-is)
    SPRINT_VELOCITY = "sprint.velocity"  # Gauge: points per sprint

    # GenAI metrics (OTel semantic convention names, use as-is)
    # Contracts for metrics recorded by contextcore-beaver.
    # See: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/
    GENAI_CLIENT_TOKEN_USAGE = "gen_ai.client.token.usage"
    GENAI_SERVER_REQUEST_DURATION = "gen_ai.server.request.duration"
    GENAI_SERVER_TIME_TO_FIRST_TOKEN = "gen_ai.server.time_to_first_token"
    GENAI_SERVER_TIME_PER_OUTPUT_TOKEN = "gen_ai.server.time_per_output_token"


# OTel GenAI recommended histogram bucket boundaries for token counts
GENAI_TOKEN_USAGE_BUCKETS = [
    1, 4, 16, 64, 256, 1024, 4096, 16384,
    65536, 262144, 1048576, 4194304, 16777216, 67108864,
]

# Duration histogram buckets (seconds) for LLM timing metrics
GENAI_DURATION_BUCKETS = [
    0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64,
    1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
]


class RecordingRuleName(str, Enum):
    """
    Canonical recording rule names following kubernetes-mixin convention.

    Pattern: <aggregation_level>:<base_metric>:<aggregation_function>
    """

    TASK_PERCENT_COMPLETE = "project:contextcore_task_percent_complete:max_over_time5m"
    SPRINT_AVG_PROGRESS = "project_sprint:contextcore_task_percent_complete:avg"
    TASK_COMPLETED_COUNT = "project_sprint:contextcore_task_completed:count"
    TASK_PROGRESS_RATE = "project_task:contextcore_task_progress:rate1h"
    TASK_COUNT_BY_STATUS = "project:contextcore_task_count:count_by_status"
    SPRINT_PLANNED_POINTS = "project_sprint:contextcore_sprint_planned_points:last"


class AlertRuleName(str, Enum):
    """
    Canonical alert rule names following kubernetes-mixin convention.

    Pattern: ContextCore[Resource][Issue]

    Severity taxonomy:
    - critical: pages on-call immediately
    - warning: next-business-day work queue
    """

    EXPORTER_FAILURE = "ContextCoreExporterFailure"
    SPAN_STATE_LOSS = "ContextCoreSpanStateLoss"
    INSIGHT_LATENCY_HIGH = "ContextCoreInsightLatencyHigh"
    TASK_STALLED = "ContextCoreTaskStalled"


class LabelName(str, Enum):
    """
    Canonical label names for telemetry.

    These labels are used consistently across metrics, logs, and traces.
    Follow OTel semantic conventions where applicable.

    Note: Use PHASE for sprint/story/phase groupings. STORY was removed
    as a redundant alias - use PHASE instead.
    """

    # Required labels
    PROJECT = "project"
    PROJECT_ID = "project.id"  # OTel semantic convention form

    # Task labels (OTel semantic convention: task.*)
    TASK_ID = "task.id"
    TASK_TYPE = "task.type"
    TASK_STATUS = "task.status"
    TASK_PRIORITY = "task.priority"
    TASK_ASSIGNEE = "task.assignee"
    TASK_TITLE = "task.title"
    TASK_PARENT_ID = "task.parent_id"
    TASK_STORY_POINTS = "task.story_points"
    TASK_PERCENT_COMPLETE = "task.percent_complete"

    # Hierarchy labels
    PHASE = "phase"
    EPIC = "epic"
    SPRINT_ID = "sprint.id"

    # Deprecated - use TASK_* equivalents instead
    STATUS = "status"  # Deprecated: use TASK_STATUS
    PRIORITY = "priority"  # Deprecated: use TASK_PRIORITY
    ASSIGNEE = "assignee"  # Deprecated: use TASK_ASSIGNEE

    # Effort labels
    TYPE = "type"  # For effort metrics: "total", "complete"

    # Service labels
    SERVICE = "service"
    JOB = "job"


class EventType(str, Enum):
    """
    Canonical event types for structured logging.

    These event types are used in the `event` field of structured logs.
    """

    # Task lifecycle
    TASK_CREATED = "task.created"
    TASK_STATUS_CHANGED = "task.status_changed"
    TASK_BLOCKED = "task.blocked"
    TASK_UNBLOCKED = "task.unblocked"
    TASK_COMPLETED = "task.completed"
    TASK_CANCELLED = "task.cancelled"
    TASK_PROGRESS_UPDATED = "task.progress_updated"
    TASK_ASSIGNED = "task.assigned"
    TASK_COMMENTED = "task.commented"

    # Subtask events
    SUBTASK_COMPLETED = "subtask.completed"

    # Sprint events
    SPRINT_STARTED = "sprint.started"
    SPRINT_ENDED = "sprint.ended"

    # Agent events
    AGENT_SESSION_STARTED = "agent.session_started"
    AGENT_SESSION_ENDED = "agent.session_ended"
    AGENT_INSIGHT_EMITTED = "agent.insight_emitted"
    AGENT_HANDOFF_CREATED = "agent.handoff_created"
    AGENT_HANDOFF_COMPLETED = "agent.handoff_completed"


# Labels that must be present on all metrics
REQUIRED_LABELS: Set[str] = {LabelName.PROJECT.value}

# Labels that should be present on task-level metrics
TASK_LABELS: Set[str] = {
    LabelName.PROJECT.value,
    LabelName.TASK_ID.value,
}

# Labels that should be present on aggregated metrics
AGGREGATE_LABELS: Set[str] = {
    LabelName.PROJECT.value,
    LabelName.PHASE.value,
    LabelName.STATUS.value,
}


def validate_labels(
    labels: Dict[str, Any],
    required: Optional[Set[str]] = None,
    context: str = "",
) -> List[str]:
    """
    Validate that required labels are present.

    Args:
        labels: Dictionary of label names to values
        required: Set of required label names (defaults to REQUIRED_LABELS)
        context: Context string for error messages

    Returns:
        List of validation error messages (empty if valid)
    """
    required = required or REQUIRED_LABELS
    errors = []

    # Check for missing required labels
    missing = required - set(labels.keys())
    if missing:
        errors.append(
            f"{context}Missing required labels: {', '.join(sorted(missing))}"
        )

    # Check for empty values
    empty = [k for k, v in labels.items() if v is None or v == ""]
    if empty:
        errors.append(
            f"{context}Empty label values: {', '.join(sorted(empty))}"
        )

    return errors


def validate_metric_name(name: str, prefix: str = "") -> List[str]:
    """
    Validate a metric name against conventions.

    Args:
        name: The metric name to validate
        prefix: Expected prefix (e.g., "lm1_")

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Check prefix
    if prefix and not name.startswith(prefix):
        errors.append(f"Metric '{name}' should start with prefix '{prefix}'")

    # Check valid characters (lowercase, numbers, underscores)
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        errors.append(
            f"Metric '{name}' must be lowercase with underscores, starting with a letter"
        )

    # Check against known metric names
    suffix = name[len(prefix):] if prefix else name
    known_suffixes = {m.value for m in MetricName}
    if suffix not in known_suffixes:
        # Warning, not error - allow custom metrics
        pass

    return errors


class ProjectSchema(BaseModel):
    """
    Schema contract for a project's telemetry.

    Defines the metric prefix, label values, and provides helpers for
    building queries with correct naming.

    Example:
        schema = ProjectSchema(
            project_id="lm1_campaign",
            metric_prefix="lm1_",
            phases=["foundation", "authority", "launch", "scale"],
        )

        # Get full metric name
        schema.metric(MetricName.PROGRESS)  # "lm1_progress"

        # Build PromQL query
        schema.promql(MetricName.PROGRESS)  # 'lm1_progress{project="lm1_campaign"}'

        # Build PromQL with extra labels
        schema.promql(MetricName.TASKS_TOTAL, status="complete")
        # 'lm1_tasks_total{project="lm1_campaign",status="complete"}'
    """

    schema_version: str = Field(
        default="1.0",
        description="Schema version for compatibility checking",
        pattern=r"^\d+\.\d+$",
    )
    project_id: str = Field(..., description="Project identifier used in labels")
    metric_prefix: str = Field(..., description="Prefix for all metric names")
    phases: List[str] = Field(default_factory=list, description="Valid phase names")
    statuses: List[str] = Field(
        default=TASK_STATUS_VALUES,
        description="Valid status values (from contracts.types.TaskStatus)",
    )
    priorities: List[str] = Field(
        default=PRIORITY_VALUES,
        description="Valid priority values (from contracts.types.Priority)",
    )

    @field_validator("metric_prefix")
    @classmethod
    def validate_prefix(cls, v: str) -> str:
        """Ensure prefix ends with underscore and is lowercase."""
        if not v:
            return v
        if not v.endswith("_"):
            v = f"{v}_"
        if not v.islower():
            raise ValueError("Metric prefix must be lowercase")
        return v

    def metric(self, name: MetricName) -> str:
        """
        Get the full metric name with prefix.

        Args:
            name: The metric name enum value

        Returns:
            Full metric name (e.g., "lm1_progress")
        """
        return f"{self.metric_prefix}{name.value}"

    def promql(
        self,
        metric: MetricName,
        **labels: Any,
    ) -> str:
        """
        Build a PromQL query with correct labels.

        Args:
            metric: The metric to query
            **labels: Additional label filters

        Returns:
            PromQL query string
        """
        full_name = self.metric(metric)
        all_labels = {LabelName.PROJECT.value: self.project_id, **labels}

        label_parts = [f'{k}="{v}"' for k, v in sorted(all_labels.items())]
        return f"{full_name}{{{','.join(label_parts)}}}"

    def logql(
        self,
        event_type: Optional[EventType] = None,
        **labels: Any,
    ) -> str:
        """
        Build a LogQL query with correct labels.

        Args:
            event_type: Optional event type filter
            **labels: Additional label filters

        Returns:
            LogQL query string
        """
        all_labels = {LabelName.PROJECT.value: self.project_id, **labels}
        label_parts = [f'{k}="{v}"' for k, v in sorted(all_labels.items())]
        base = f"{{{','.join(label_parts)}}}"

        if event_type:
            return f'{base} | json | event = "{event_type.value}"'
        return base

    def validate_phase(self, phase: str) -> bool:
        """Check if a phase value is valid for this project."""
        if not self.phases:
            return True  # No phase restrictions
        return phase in self.phases

    def validate_status(self, status: str) -> bool:
        """Check if a status value is valid."""
        return status in self.statuses

    def validate_priority(self, priority: str) -> bool:
        """Check if a priority value is valid."""
        return priority in self.priorities

    def is_compatible(self, other_version: str) -> bool:
        """
        Check if this schema is compatible with another version.

        Compatibility rules:
        - Same major version = compatible
        - Different major version = incompatible

        Args:
            other_version: Version string to check against (e.g., "1.0")

        Returns:
            True if compatible, False otherwise
        """
        try:
            self_major = int(self.schema_version.split(".")[0])
            other_major = int(other_version.split(".")[0])
            return self_major == other_major
        except (ValueError, IndexError):
            return False


# Current schema version
SCHEMA_VERSION = "1.0"


# Pre-defined schemas for common projects
LM1_SCHEMA = ProjectSchema(
    schema_version=SCHEMA_VERSION,
    project_id="lm1_campaign",
    metric_prefix="lm1_",
    phases=["foundation", "authority", "launch", "scale"],
)

CONTEXTCORE_SCHEMA = ProjectSchema(
    schema_version=SCHEMA_VERSION,
    project_id="contextcore",
    metric_prefix="cc_",
    phases=["core", "agent", "integrations", "docs"],
)

# languagemodel1oh.io Site Launch project schema
LM1OH_SCHEMA = ProjectSchema(
    schema_version=SCHEMA_VERSION,
    project_id="languagemodel1oh",
    metric_prefix="lm1oh_",
    phases=["planning", "design", "development", "testing", "pre_launch", "launch"],
)
