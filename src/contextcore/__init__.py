"""
ContextCore - Unified metadata model from project initiation to operations.

This package provides Kubernetes Custom Resource Definitions (CRDs) that inject
project management context (business value, design documents, requirements, risk
signals) directly into the cluster alongside deployments.

Key Features:
- ProjectContext CRD links K8s resources to project artifacts
- Value-based observability derivation (SLOs, alerts from requirements)
- OTel Resource Detector injects context into all telemetry
- Sync adapters for Jira, GitHub, Notion

Example usage:
    from contextcore import ProjectContextDetector
    from opentelemetry.sdk.resources import get_aggregated_resources

    # Auto-detect project context from K8s annotations
    resource = get_aggregated_resources([ProjectContextDetector()])

    # All traces/metrics/logs now include project context:
    # - project.id, project.epic, project.task
    # - business.criticality, business.value, business.owner
    # - design.doc, design.adr
    # - requirement.availability, requirement.latency_p99
"""

__version__ = "0.1.0"
__all__ = [
    "ProjectContextDetector",
    "TaskTracker",
    "SprintTracker",
    "TaskMetrics",
    "get_task_link",
    "__version__",
]


# Lazy imports to avoid loading heavy dependencies at import time
def __getattr__(name: str):
    if name == "ProjectContextDetector":
        from contextcore.detector import ProjectContextDetector
        return ProjectContextDetector
    if name == "TaskTracker":
        from contextcore.tracker import TaskTracker
        return TaskTracker
    if name == "SprintTracker":
        from contextcore.tracker import SprintTracker
        return SprintTracker
    if name == "TaskMetrics":
        from contextcore.metrics import TaskMetrics
        return TaskMetrics
    if name == "get_task_link":
        from contextcore.tracker import TaskTracker
        # Return a helper function
        def get_task_link(task_id: str, project: str = "default"):
            tracker = TaskTracker(project=project)
            return tracker.get_task_link(task_id)
        return get_task_link
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
