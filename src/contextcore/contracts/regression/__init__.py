"""
Regression prevention — Layer 7 of defense-in-depth.

Provides contract drift detection and a CI/CD regression gate that
prevents propagation quality from degrading across changes.

Public API::

    from contextcore.contracts.regression import (
        # Drift detection
        ContractDriftDetector,
        DriftChange,
        DriftReport,
        # Regression gate
        RegressionGate,
        GateCheck,
        GateResult,
        DEFAULT_THRESHOLDS,
        # OTel helpers
        emit_drift_report,
        emit_gate_result,
        emit_gate_check,
    )
"""

from contextcore.contracts.regression.drift import (
    ContractDriftDetector,
    DriftChange,
    DriftReport,
)
from contextcore.contracts.regression.gate import (
    DEFAULT_THRESHOLDS,
    GateCheck,
    GateResult,
    RegressionGate,
)
from contextcore.contracts.regression.otel import (
    emit_drift_report,
    emit_gate_check,
    emit_gate_result,
)

__all__ = [
    # Drift detection
    "ContractDriftDetector",
    "DriftChange",
    "DriftReport",
    # Regression gate
    "RegressionGate",
    "GateCheck",
    "GateResult",
    "DEFAULT_THRESHOLDS",
    # OTel
    "emit_drift_report",
    "emit_gate_result",
    "emit_gate_check",
]
