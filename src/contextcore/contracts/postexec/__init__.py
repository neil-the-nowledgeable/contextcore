"""
Post-execution validation — Layer 5 of defense-in-depth.

Validates context integrity after all workflow phases complete.
Checks propagation chain integrity, final exit requirements, and
cross-references Layer 4 runtime records to detect late corruption
or late healing.

Public API::

    from contextcore.contracts.postexec import (
        # Validator
        PostExecutionValidator,
        # Result models
        PostExecutionReport,
        RuntimeDiscrepancy,
        # OTel helpers
        emit_postexec_report,
        emit_postexec_discrepancy,
    )
"""

from contextcore.contracts.postexec.otel import (
    emit_postexec_discrepancy,
    emit_postexec_report,
)
from contextcore.contracts.postexec.validator import (
    PostExecutionReport,
    PostExecutionValidator,
    RuntimeDiscrepancy,
)

__all__ = [
    # Validator
    "PostExecutionValidator",
    # Result models
    "PostExecutionReport",
    "RuntimeDiscrepancy",
    # OTel
    "emit_postexec_report",
    "emit_postexec_discrepancy",
]
