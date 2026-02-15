"""Tests for boundary validator."""

from __future__ import annotations

import pytest

from contextcore.contracts.propagation.loader import ContractLoader
from contextcore.contracts.propagation.schema import (
    ContextContract,
    FieldSpec,
    PhaseContract,
    PhaseEntryContract,
    PhaseExitContract,
)
from contextcore.contracts.propagation.validator import (
    BoundaryValidator,
    ContractValidationResult,
    FieldValidationResult,
)
from contextcore.contracts.types import ConstraintSeverity, PropagationStatus


@pytest.fixture
def validator():
    return BoundaryValidator()


def _make_contract(**phase_kwargs) -> ContextContract:
    """Create a minimal contract with a single phase."""
    return ContextContract(
        schema_version="0.1.0",
        pipeline_id="test",
        phases={"implement": PhaseContract(**phase_kwargs)},
    )


# ---------------------------------------------------------------------------
# Entry validation — blocking fields
# ---------------------------------------------------------------------------


class TestValidateEntry:
    def test_all_required_present(self, validator):
        contract = _make_contract(
            entry=PhaseEntryContract(
                required=[
                    FieldSpec(name="tasks", severity=ConstraintSeverity.BLOCKING),
                    FieldSpec(name="design_results", severity=ConstraintSeverity.BLOCKING),
                ],
            ),
        )
        context = {"tasks": [1, 2], "design_results": {"a": 1}}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True
        assert result.propagation_status == PropagationStatus.PROPAGATED

    def test_missing_blocking_field(self, validator):
        contract = _make_contract(
            entry=PhaseEntryContract(
                required=[
                    FieldSpec(name="tasks", severity=ConstraintSeverity.BLOCKING),
                ],
            ),
        )
        context = {}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is False
        assert "tasks" in result.blocking_failures
        assert result.propagation_status == PropagationStatus.FAILED

    def test_unknown_phase_passes(self, validator):
        contract = _make_contract()
        result = validator.validate_entry("nonexistent", {}, contract)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Exit validation
# ---------------------------------------------------------------------------


class TestValidateExit:
    def test_exit_required_present(self, validator):
        contract = _make_contract(
            exit=PhaseExitContract(
                required=[FieldSpec(name="generation_results")],
            ),
        )
        context = {"generation_results": {"files": []}}
        result = validator.validate_exit("implement", context, contract)
        assert result.passed is True

    def test_exit_missing_required(self, validator):
        contract = _make_contract(
            exit=PhaseExitContract(
                required=[FieldSpec(name="generation_results")],
            ),
        )
        result = validator.validate_exit("implement", {}, contract)
        assert result.passed is False


# ---------------------------------------------------------------------------
# Enrichment validation
# ---------------------------------------------------------------------------


class TestValidateEnrichment:
    def test_enrichment_present(self, validator):
        contract = _make_contract(
            entry=PhaseEntryContract(
                enrichment=[
                    FieldSpec(
                        name="domain",
                        severity=ConstraintSeverity.WARNING,
                        default="unknown",
                    ),
                ],
            ),
        )
        context = {"domain": "web_application"}
        result = validator.validate_enrichment("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].status == PropagationStatus.PROPAGATED

    def test_enrichment_missing_applies_default(self, validator):
        contract = _make_contract(
            entry=PhaseEntryContract(
                enrichment=[
                    FieldSpec(
                        name="domain",
                        severity=ConstraintSeverity.WARNING,
                        default="unknown",
                    ),
                ],
            ),
        )
        context = {}
        result = validator.validate_enrichment("implement", context, contract)
        assert result.passed is True  # WARNING doesn't block
        assert result.field_results[0].status == PropagationStatus.DEFAULTED
        assert result.field_results[0].default_applied is True
        assert context["domain"] == "unknown"  # default was applied

    def test_enrichment_missing_no_default(self, validator):
        contract = _make_contract(
            entry=PhaseEntryContract(
                enrichment=[
                    FieldSpec(
                        name="domain",
                        severity=ConstraintSeverity.WARNING,
                    ),
                ],
            ),
        )
        context = {}
        result = validator.validate_enrichment("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].status == PropagationStatus.DEFAULTED
        assert result.field_results[0].default_applied is False

    def test_advisory_field_absent_passes(self, validator):
        contract = _make_contract(
            entry=PhaseEntryContract(
                enrichment=[
                    FieldSpec(
                        name="calibration",
                        severity=ConstraintSeverity.ADVISORY,
                    ),
                ],
            ),
        )
        result = validator.validate_enrichment("implement", {}, contract)
        assert result.passed is True
        assert result.field_results[0].status == PropagationStatus.PARTIAL

    def test_nested_field_resolution(self, validator):
        contract = _make_contract(
            entry=PhaseEntryContract(
                enrichment=[
                    FieldSpec(
                        name="domain_summary.domain",
                        severity=ConstraintSeverity.WARNING,
                        default="unknown",
                    ),
                ],
            ),
        )
        context = {"domain_summary": {"domain": "web_application"}}
        result = validator.validate_enrichment("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].status == PropagationStatus.PROPAGATED


# ---------------------------------------------------------------------------
# GateResult conversion
# ---------------------------------------------------------------------------


class TestGateResultConversion:
    def test_passing_gate_result(self, validator):
        contract = _make_contract(
            entry=PhaseEntryContract(
                required=[FieldSpec(name="tasks")],
            ),
        )
        result = validator.validate_entry("implement", {"tasks": [1]}, contract)
        gate = result.to_gate_result()
        assert gate["result"] == "pass"
        assert gate["blocking"] is False
        assert gate["gate_id"] == "propagation.implement.entry"

    def test_failing_gate_result(self, validator):
        contract = _make_contract(
            entry=PhaseEntryContract(
                required=[FieldSpec(name="tasks")],
            ),
        )
        result = validator.validate_entry("implement", {}, contract)
        gate = result.to_gate_result()
        assert gate["result"] == "fail"
        assert gate["blocking"] is True
        assert len(gate["evidence"]) > 0
