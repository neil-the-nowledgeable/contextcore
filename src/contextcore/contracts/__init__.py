"""
Schema contracts for ContextCore telemetry.

This module provides centralized definitions for:
- Metric names and prefixes
- Label names and required labels
- Event types and attributes
- Dashboard query builders
- Core type enums (TaskStatus, Priority, etc.)

Using these contracts ensures consistency between:
- Metric emission (TaskTracker, TaskLogger)
- Dashboard queries (Grafana)
- Alert rules (Prometheus/Mimir)
- Log queries (Loki)

Example:
    from contextcore.contracts import ProjectSchema, MetricName, TaskStatus

    # Define project schema
    schema = ProjectSchema(
        project_id="lm1_campaign",
        metric_prefix="lm1_",
    )

    # Get validated metric name
    metric = schema.metric(MetricName.PROGRESS)
    # Returns: "lm1_progress"

    # Build query with correct labels
    query = schema.promql(MetricName.PROGRESS)
    # Returns: 'lm1_progress{project="lm1_campaign"}'

    # Use canonical status values
    status = TaskStatus.IN_PROGRESS  # "in_progress"
"""

from contextcore.contracts.metrics import (
    MetricName,
    LabelName,
    EventType,
    ProjectSchema,
    RecordingRuleName,
    AlertRuleName,
    validate_labels,
    validate_metric_name,
    GENAI_TOKEN_USAGE_BUCKETS,
    GENAI_DURATION_BUCKETS,
)
from contextcore.contracts.queries import (
    PromQLBuilder,
    LogQLBuilder,
    TraceQLBuilder,
)
from contextcore.contracts.types import (
    # Task types
    TaskStatus,
    TaskType,
    Priority,
    # Agent types
    AgentType,
    InsightType,
    HandoffStatus,
    SessionStatus,
    ConstraintSeverity,
    QuestionStatus,
    # Business types
    Criticality,
    BusinessValue,
    RiskType,
    AlertPriority,
    # Observability types
    DashboardPlacement,
    LogLevel,
    # Value lists for validation
    TASK_STATUS_VALUES,
    PRIORITY_VALUES,
    TASK_TYPE_VALUES,
    AGENT_TYPE_VALUES,
    INSIGHT_TYPE_VALUES,
    HANDOFF_STATUS_VALUES,
    SESSION_STATUS_VALUES,
)
from contextcore.contracts.validate import (
    ContractValidator,
    ValidationResult,
    validate_all,
)
from contextcore.contracts.timeouts import (
    # OTel timeouts
    OTEL_FLUSH_TIMEOUT_MS,
    OTEL_ENDPOINT_CHECK_TIMEOUT_S,
    OTEL_DEFAULT_GRPC_PORT,
    # HTTP timeouts
    HTTP_CLIENT_TIMEOUT_S,
    HTTP_HEALTH_CHECK_TIMEOUT_S,
    HTTP_TRACE_FETCH_TIMEOUT_S,
    # K8s timeouts
    K8S_API_CONNECT_TIMEOUT_S,
    K8S_API_READ_TIMEOUT_S,
    # Handoff timeouts
    HANDOFF_DEFAULT_TIMEOUT_MS,
    HANDOFF_POLL_INTERVAL_S,
    # Subprocess timeouts
    SUBPROCESS_DEFAULT_TIMEOUT_S,
    # Retry config
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_S,
    DEFAULT_RETRY_BACKOFF,
    RETRYABLE_HTTP_STATUS_CODES,
)

__all__ = [
    # Metrics
    "MetricName",
    "LabelName",
    "EventType",
    "ProjectSchema",
    "validate_labels",
    "validate_metric_name",
    # Queries
    "PromQLBuilder",
    "LogQLBuilder",
    "TraceQLBuilder",
    # Validation
    "ContractValidator",
    "ValidationResult",
    "validate_all",
    # Task types
    "TaskStatus",
    "TaskType",
    "Priority",
    # Agent types
    "AgentType",
    "InsightType",
    "HandoffStatus",
    "SessionStatus",
    "ConstraintSeverity",
    "QuestionStatus",
    # Business types
    "Criticality",
    "BusinessValue",
    "RiskType",
    "AlertPriority",
    # Observability types
    "DashboardPlacement",
    "LogLevel",
    # Value lists
    "TASK_STATUS_VALUES",
    "PRIORITY_VALUES",
    "TASK_TYPE_VALUES",
    "AGENT_TYPE_VALUES",
    "INSIGHT_TYPE_VALUES",
    "HANDOFF_STATUS_VALUES",
    "SESSION_STATUS_VALUES",
    # Timeouts
    "OTEL_FLUSH_TIMEOUT_MS",
    "OTEL_ENDPOINT_CHECK_TIMEOUT_S",
    "OTEL_DEFAULT_GRPC_PORT",
    "HTTP_CLIENT_TIMEOUT_S",
    "HTTP_HEALTH_CHECK_TIMEOUT_S",
    "HTTP_TRACE_FETCH_TIMEOUT_S",
    "K8S_API_CONNECT_TIMEOUT_S",
    "K8S_API_READ_TIMEOUT_S",
    "HANDOFF_DEFAULT_TIMEOUT_MS",
    "HANDOFF_POLL_INTERVAL_S",
    "SUBPROCESS_DEFAULT_TIMEOUT_S",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_DELAY_S",
    "DEFAULT_RETRY_BACKOFF",
    "RETRYABLE_HTTP_STATUS_CODES",
    # GenAI metric constants
    "GENAI_TOKEN_USAGE_BUCKETS",
    "GENAI_DURATION_BUCKETS",
    # Recording and alert rule contracts
    "RecordingRuleName",
    "AlertRuleName",
]
