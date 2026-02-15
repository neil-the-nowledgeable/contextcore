"""Tests for OTel span event emission helpers for schema compatibility."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from contextcore.contracts.schema_compat.otel import (
    emit_compatibility_breaking,
    emit_compatibility_check,
    emit_compatibility_drift,
)
from contextcore.contracts.schema_compat.schema import (
    CompatibilityResult,
    EvolutionCheckResult,
)
from contextcore.contracts.types import CompatibilityLevel, ConstraintSeverity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_span():
    """Create a mock OTel span that is recording."""
    span = MagicMock()
    span.is_recording.return_value = True
    return span


@pytest.fixture
def mock_otel(mock_span):
    """Patch OTel to return our mock span."""
    with patch("contextcore.contracts.schema_compat.otel._HAS_OTEL", True), \
         patch("contextcore.contracts.schema_compat.otel.otel_trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        yield mock_span


# ---------------------------------------------------------------------------
# emit_compatibility_check
# ---------------------------------------------------------------------------


class TestEmitCompatibilityCheck:
    def test_emits_correct_event(self, mock_otel):
        result = CompatibilityResult(
            compatible=True,
            level=CompatibilityLevel.SEMANTIC,
            source_service="tracker",
            target_service="exporter",
            message="All fields compatible",
        )
        emit_compatibility_check(result)
        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "schema.compatibility.check"
        attrs = call_args.kwargs["attributes"]
        assert attrs["schema.source_service"] == "tracker"
        assert attrs["schema.target_service"] == "exporter"
        assert attrs["schema.level"] == "semantic"
        assert attrs["schema.compatible"] is True

    def test_incompatible_result(self, mock_otel):
        result = CompatibilityResult(
            compatible=False,
            level=CompatibilityLevel.STRUCTURAL,
            source_service="a",
            target_service="b",
            drift_details=["drift1", "drift2"],
            message="Incompatible",
        )
        emit_compatibility_check(result)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["schema.compatible"] is False
        assert attrs["schema.drift_count"] == 2

    def test_no_otel_does_not_crash(self):
        with patch("contextcore.contracts.schema_compat.otel._HAS_OTEL", False):
            result = CompatibilityResult(
                compatible=True,
                level=CompatibilityLevel.STRUCTURAL,
                source_service="a",
                target_service="b",
            )
            emit_compatibility_check(result)  # Should not raise


# ---------------------------------------------------------------------------
# emit_compatibility_drift
# ---------------------------------------------------------------------------


class TestEmitCompatibilityDrift:
    def test_emits_correct_event(self, mock_otel):
        result = CompatibilityResult(
            compatible=False,
            level=CompatibilityLevel.SEMANTIC,
            source_service="tracker",
            target_service="exporter",
            severity=ConstraintSeverity.BLOCKING,
        )
        emit_compatibility_drift(
            result,
            drift_field="task.status",
            drift_type="unmapped_value",
            drift_detail="Value 'unknown' has no translation",
        )
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "schema.compatibility.drift"
        attrs = call_args.kwargs["attributes"]
        assert attrs["schema.drift_field"] == "task.status"
        assert attrs["schema.drift_type"] == "unmapped_value"
        assert attrs["schema.severity"] == "blocking"

    def test_no_otel_does_not_crash(self):
        with patch("contextcore.contracts.schema_compat.otel._HAS_OTEL", False):
            result = CompatibilityResult(
                compatible=True,
                level=CompatibilityLevel.STRUCTURAL,
                source_service="a",
                target_service="b",
            )
            emit_compatibility_drift(result, "f", "t", "d")  # Should not raise


# ---------------------------------------------------------------------------
# emit_compatibility_breaking
# ---------------------------------------------------------------------------


class TestEmitCompatibilityBreaking:
    def test_emits_correct_event(self, mock_otel):
        result = EvolutionCheckResult(
            compatible=False,
            service="tracker",
            old_version="1.0.0",
            new_version="2.0.0",
            applicable_rule="r1",
            message="1 breaking",
        )
        change = {"type": "remove_field", "field": "status"}
        emit_compatibility_breaking(result, change)
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "schema.compatibility.breaking"
        attrs = call_args.kwargs["attributes"]
        assert attrs["schema.service"] == "tracker"
        assert attrs["schema.old_version"] == "1.0.0"
        assert attrs["schema.new_version"] == "2.0.0"
        assert attrs["schema.change_type"] == "remove_field"
        assert attrs["schema.change_field"] == "status"
        assert attrs["schema.policy"] == "r1"

    def test_no_applicable_rule(self, mock_otel):
        result = EvolutionCheckResult(
            compatible=False,
            service="tracker",
            old_version="1.0.0",
            new_version="2.0.0",
            applicable_rule=None,
        )
        change = {"type": "remove_field", "field": "x"}
        emit_compatibility_breaking(result, change)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["schema.policy"] == ""

    def test_no_otel_does_not_crash(self):
        with patch("contextcore.contracts.schema_compat.otel._HAS_OTEL", False):
            result = EvolutionCheckResult(
                compatible=False,
                service="tracker",
                old_version="1.0.0",
                new_version="2.0.0",
            )
            emit_compatibility_breaking(result, {"type": "x", "field": "y"})
