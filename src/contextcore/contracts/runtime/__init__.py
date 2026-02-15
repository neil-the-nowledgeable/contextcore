"""
Runtime boundary checks — Layer 4 of defense-in-depth.

Wraps Layer 1's ``BoundaryValidator`` into automatic phase boundary
guards with configurable enforcement modes (strict/permissive/audit).
Collects boundary validation results across a workflow run and emits
OTel span events for observability.

Public API::

    from contextcore.contracts.runtime import (
        # Guard
        RuntimeBoundaryGuard,
        BoundaryViolationError,
        # Result models
        PhaseExecutionRecord,
        WorkflowRunSummary,
        # OTel helpers
        emit_phase_boundary,
        emit_workflow_summary,
    )
"""

from contextcore.contracts.runtime.guard import (
    BoundaryViolationError,
    PhaseExecutionRecord,
    RuntimeBoundaryGuard,
    WorkflowRunSummary,
)
from contextcore.contracts.runtime.otel import (
    emit_phase_boundary,
    emit_workflow_summary,
)

__all__ = [
    # Guard
    "RuntimeBoundaryGuard",
    "BoundaryViolationError",
    # Result models
    "PhaseExecutionRecord",
    "WorkflowRunSummary",
    # OTel
    "emit_phase_boundary",
    "emit_workflow_summary",
]
