"""Tests for OTel span event emission helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from contextcore.contracts.propagation.otel import (
    emit_boundary_result,
    emit_chain_result,
    emit_propagation_summary,
)
from contextcore.contracts.propagation.tracker import PropagationChainResult
from contextcore.contracts.propagation.validator import ContractValidationResult, FieldValidationResult
from contextcore.contracts.types import ChainStatus, ConstraintSeverity, PropagationStatus


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
    with patch("contextcore.contracts._otel_helpers.HAS_OTEL", True), \
         patch("contextcore.contracts._otel_helpers.otel_trace") as mock_trace:
        mock_trace.get_current_span.return_value = mock_span
        yield mock_span


# ---------------------------------------------------------------------------
# emit_boundary_result
# ---------------------------------------------------------------------------


class TestEmitBoundaryResult:
    def test_emits_entry_event(self, mock_otel):
        result = ContractValidationResult(
            passed=True,
            phase="implement",
            direction="entry",
            propagation_status=PropagationStatus.PROPAGATED,
        )
        emit_boundary_result(result)
        mock_otel.add_event.assert_called_once()
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.boundary.entry"
        attrs = call_args.kwargs["attributes"]
        assert attrs["context.phase"] == "implement"
        assert attrs["context.passed"] is True

    def test_emits_exit_event(self, mock_otel):
        result = ContractValidationResult(
            passed=True,
            phase="plan",
            direction="exit",
            propagation_status=PropagationStatus.PROPAGATED,
        )
        emit_boundary_result(result)
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.boundary.exit"

    def test_failed_result_includes_blocking(self, mock_otel):
        result = ContractValidationResult(
            passed=False,
            phase="implement",
            direction="entry",
            blocking_failures=["tasks", "design_results"],
            propagation_status=PropagationStatus.FAILED,
        )
        emit_boundary_result(result)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["context.blocking_count"] == 2
        assert attrs["context.blocking.0"] == "tasks"
        assert attrs["context.blocking.1"] == "design_results"

    def test_no_otel_does_not_crash(self):
        """When OTel is not available, emit_boundary_result should not crash."""
        with patch("contextcore.contracts._otel_helpers.HAS_OTEL", False):
            result = ContractValidationResult(
                passed=True, phase="test", direction="entry",
            )
            emit_boundary_result(result)  # Should not raise


# ---------------------------------------------------------------------------
# emit_chain_result
# ---------------------------------------------------------------------------


class TestEmitChainResult:
    def test_intact_chain_event(self, mock_otel):
        result = PropagationChainResult(
            chain_id="domain_flow",
            status=ChainStatus.INTACT,
            source_present=True,
            destination_present=True,
            message="Chain intact",
        )
        emit_chain_result(result)
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.chain.validated"

    def test_degraded_chain_event(self, mock_otel):
        result = PropagationChainResult(
            chain_id="domain_flow",
            status=ChainStatus.DEGRADED,
            source_present=True,
            destination_present=True,
            message="defaulted",
        )
        emit_chain_result(result)
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.chain.degraded"

    def test_broken_chain_event(self, mock_otel):
        result = PropagationChainResult(
            chain_id="domain_flow",
            status=ChainStatus.BROKEN,
            source_present=False,
            destination_present=False,
            message="Source absent",
        )
        emit_chain_result(result)
        call_args = mock_otel.add_event.call_args
        assert call_args.kwargs["name"] == "context.chain.broken"
        attrs = call_args.kwargs["attributes"]
        assert attrs["context.chain_id"] == "domain_flow"
        assert attrs["context.source_present"] is False


# ---------------------------------------------------------------------------
# emit_propagation_summary
# ---------------------------------------------------------------------------


class TestEmitPropagationSummary:
    def test_all_intact(self, mock_otel):
        results = [
            PropagationChainResult(chain_id="a", status=ChainStatus.INTACT, source_present=True, destination_present=True),
            PropagationChainResult(chain_id="b", status=ChainStatus.INTACT, source_present=True, destination_present=True),
        ]
        emit_propagation_summary(results)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["context.total_chains"] == 2
        assert attrs["context.intact"] == 2
        assert attrs["context.completeness_pct"] == 100.0

    def test_mixed_results(self, mock_otel):
        results = [
            PropagationChainResult(chain_id="a", status=ChainStatus.INTACT, source_present=True, destination_present=True),
            PropagationChainResult(chain_id="b", status=ChainStatus.DEGRADED, source_present=True, destination_present=True),
            PropagationChainResult(chain_id="c", status=ChainStatus.BROKEN, source_present=False, destination_present=False),
        ]
        emit_propagation_summary(results)
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["context.intact"] == 1
        assert attrs["context.degraded"] == 1
        assert attrs["context.broken"] == 1
        assert attrs["context.completeness_pct"] == pytest.approx(33.3, abs=0.1)

    def test_empty_results(self, mock_otel):
        emit_propagation_summary([])
        attrs = mock_otel.add_event.call_args.kwargs["attributes"]
        assert attrs["context.total_chains"] == 0
        assert attrs["context.completeness_pct"] == 0.0
