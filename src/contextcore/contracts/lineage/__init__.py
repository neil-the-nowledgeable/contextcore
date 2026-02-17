"""
Data lineage contracts — Layer 7 of defense-in-depth.

Maintains full transformation history of fields through pipeline phases.
Enables forensic root cause analysis when outputs are wrong by tracking
every operation applied to every tracked field.

Public API::

    from contextcore.contracts.lineage import (
        # Schema models
        LineageContract,
        LineageChainSpec,
        StageSpec,
        # Tracker
        LineageTracker,
        TransformationRecord,
        # Auditor
        ProvenanceAuditor,
        LineageAuditResult,
        LineageAuditSummary,
        # Loader
        LineageLoader,
        # OTel helpers
        emit_transformation,
        emit_audit_result,
        emit_audit_summary,
    )
"""

from contextcore.contracts.lineage.auditor import (
    LineageAuditResult,
    LineageAuditSummary,
    ProvenanceAuditor,
)
from contextcore.contracts.lineage.loader import LineageLoader
from contextcore.contracts.lineage.otel import (
    emit_audit_result,
    emit_audit_summary,
    emit_transformation,
)
from contextcore.contracts.lineage.schema import (
    LineageChainSpec,
    LineageContract,
    StageSpec,
)
from contextcore.contracts.lineage.tracker import (
    LineageTracker,
    TransformationRecord,
)

__all__ = [
    # Schema
    "LineageContract",
    "LineageChainSpec",
    "StageSpec",
    # Tracker
    "LineageTracker",
    "TransformationRecord",
    # Auditor
    "ProvenanceAuditor",
    "LineageAuditResult",
    "LineageAuditSummary",
    # Loader
    "LineageLoader",
    # OTel
    "emit_transformation",
    "emit_audit_result",
    "emit_audit_summary",
]
