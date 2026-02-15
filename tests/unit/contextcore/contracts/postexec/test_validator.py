"""Tests for PostExecutionValidator (Layer 5)."""

import pytest
from pydantic import ValidationError

from contextcore.contracts.postexec.validator import (
    PostExecutionReport,
    PostExecutionValidator,
    RuntimeDiscrepancy,
)
from contextcore.contracts.propagation.schema import (
    ChainEndpoint,
    ContextContract,
    FieldSpec,
    PhaseContract,
    PhaseEntryContract,
    PhaseExitContract,
    PropagationChainSpec,
)
from contextcore.contracts.propagation.validator import ContractValidationResult
from contextcore.contracts.runtime.guard import (
    PhaseExecutionRecord,
    WorkflowRunSummary,
)
from contextcore.contracts.types import (
    ChainStatus,
    ConstraintSeverity,
    EnforcementMode,
    PropagationStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(phases, chains=None):
    """Create a minimal contract with the given phases dict and optional chains."""
    return ContextContract(
        schema_version="1.0.0",
        pipeline_id="test-pipeline",
        phases=phases,
        propagation_chains=chains or [],
    )


def _two_phase_contract_with_chain():
    """Contract with seed -> plan phases and a domain_flow chain."""
    return _make_contract(
        phases={
            "seed": PhaseContract(
                entry=PhaseEntryContract(
                    required=[
                        FieldSpec(name="domain", severity=ConstraintSeverity.BLOCKING),
                    ],
                ),
                exit=PhaseExitContract(
                    required=[
                        FieldSpec(
                            name="seed_output", severity=ConstraintSeverity.BLOCKING
                        ),
                    ],
                ),
            ),
            "plan": PhaseContract(
                entry=PhaseEntryContract(
                    required=[
                        FieldSpec(
                            name="seed_output", severity=ConstraintSeverity.BLOCKING
                        ),
                    ],
                ),
                exit=PhaseExitContract(
                    required=[
                        FieldSpec(
                            name="plan_output", severity=ConstraintSeverity.BLOCKING
                        ),
                    ],
                ),
            ),
        },
        chains=[
            PropagationChainSpec(
                chain_id="domain_flow",
                source=ChainEndpoint(phase="seed", field="domain"),
                destination=ChainEndpoint(phase="plan", field="domain"),
            ),
        ],
    )


def _make_passing_result(phase, direction="entry"):
    """Build a passing ContractValidationResult."""
    return ContractValidationResult(
        passed=True,
        phase=phase,
        direction=direction,
        propagation_status=PropagationStatus.PROPAGATED,
    )


def _make_failing_result(phase, direction="entry", blocking_fields=None):
    """Build a failing ContractValidationResult."""
    return ContractValidationResult(
        passed=False,
        phase=phase,
        direction=direction,
        blocking_failures=blocking_fields or ["missing_field"],
        propagation_status=PropagationStatus.FAILED,
    )


def _make_workflow_summary(phase_records, overall_passed=True):
    """Build a WorkflowRunSummary from a list of PhaseExecutionRecord."""
    passed_count = sum(1 for r in phase_records if r.passed)
    failed_count = len(phase_records) - passed_count
    return WorkflowRunSummary(
        mode=EnforcementMode.STRICT,
        phases=phase_records,
        total_phases=len(phase_records),
        passed_phases=passed_count,
        failed_phases=failed_count,
        overall_passed=overall_passed,
        overall_status=(
            PropagationStatus.PROPAGATED
            if overall_passed
            else PropagationStatus.FAILED
        ),
    )


# ---------------------------------------------------------------------------
# PostExecutionReport
# ---------------------------------------------------------------------------


class TestPostExecutionReport:
    def test_basic_construction_with_defaults(self):
        """PostExecutionReport can be constructed with only passed; defaults are correct."""
        report = PostExecutionReport(passed=True)

        assert report.passed is True
        assert report.chain_results == []
        assert report.chains_total == 0
        assert report.chains_intact == 0
        assert report.chains_degraded == 0
        assert report.chains_broken == 0
        assert report.completeness_pct == 100.0
        assert report.final_exit_result is None
        assert report.runtime_discrepancies == []

    def test_extra_fields_rejected(self):
        """ConfigDict extra='forbid' rejects extra fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            PostExecutionReport(passed=True, unexpected_field="oops")

    def test_completeness_pct_zero_when_all_broken(self):
        """completeness_pct is 0.0 when chains_intact is 0 out of N total."""
        report = PostExecutionReport(
            passed=False,
            chains_total=3,
            chains_intact=0,
            chains_broken=3,
            completeness_pct=0.0,
        )
        assert report.completeness_pct == 0.0

    def test_completeness_pct_100_when_all_intact(self):
        """completeness_pct is 100.0 when all chains are intact."""
        report = PostExecutionReport(
            passed=True,
            chains_total=4,
            chains_intact=4,
            completeness_pct=100.0,
        )
        assert report.completeness_pct == 100.0


# ---------------------------------------------------------------------------
# RuntimeDiscrepancy
# ---------------------------------------------------------------------------


class TestRuntimeDiscrepancy:
    def test_construction_stores_fields(self):
        """Construction stores phase, discrepancy_type, and message."""
        disc = RuntimeDiscrepancy(
            phase="seed",
            discrepancy_type="late_corruption",
            message="Something went wrong after the runtime check",
        )
        assert disc.phase == "seed"
        assert disc.discrepancy_type == "late_corruption"
        assert disc.message == "Something went wrong after the runtime check"

    def test_extra_fields_rejected(self):
        """ConfigDict extra='forbid' rejects extra fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RuntimeDiscrepancy(
                phase="plan",
                discrepancy_type="late_healing",
                bogus="nope",
            )


# ---------------------------------------------------------------------------
# Chain integrity check
# ---------------------------------------------------------------------------


class TestChainIntegrityCheck:
    def test_no_chains_in_contract(self):
        """No chains in contract -> passed, 0 chains total.

        When chains_total=0 and chains_intact=0, the formula
        ``round(0 / max(0, 1) * 100, 1)`` yields 0.0.
        """
        contract = _make_contract(
            phases={
                "seed": PhaseContract(
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="seed_output",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
            },
            chains=[],
        )
        validator = PostExecutionValidator()
        report = validator.validate(
            contract,
            final_context={"seed_output": "data"},
            phase_order=["seed"],
        )

        assert report.passed is True
        assert report.chains_total == 0
        # With 0 intact out of max(0,1) the formula gives 0.0
        assert report.completeness_pct == 0.0

    def test_all_chains_intact(self):
        """All chains intact -> passed, completeness 100%."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        report = validator.validate(
            contract,
            final_context={
                "domain": "web_app",
                "seed_output": "seeds",
                "plan_output": "the plan",
            },
            phase_order=["seed", "plan"],
        )

        assert report.passed is True
        assert report.chains_total == 1
        assert report.chains_intact == 1
        assert report.chains_broken == 0
        assert report.completeness_pct == 100.0

    def test_one_chain_degraded(self):
        """One chain degraded -> still passed (degraded is not blocking), completeness < 100%."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        # domain at destination is empty string -> DEGRADED
        report = validator.validate(
            contract,
            final_context={
                "domain": "",
                "seed_output": "seeds",
                "plan_output": "the plan",
            },
            phase_order=["seed", "plan"],
        )

        assert report.passed is True
        assert report.chains_degraded == 1
        assert report.chains_broken == 0
        assert report.completeness_pct < 100.0

    def test_one_chain_broken(self):
        """One chain broken -> NOT passed, completeness < 100%."""
        contract = _make_contract(
            phases={
                "seed": PhaseContract(
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="seed_output",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
                "plan": PhaseContract(
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="plan_output",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
            },
            chains=[
                PropagationChainSpec(
                    chain_id="data_flow",
                    source=ChainEndpoint(phase="seed", field="seed_output"),
                    destination=ChainEndpoint(phase="plan", field="seed_output"),
                ),
            ],
        )
        validator = PostExecutionValidator()

        # seed_output is absent from final_context -> source absent -> BROKEN
        report = validator.validate(
            contract,
            final_context={"plan_output": "done"},
            phase_order=["seed", "plan"],
        )

        assert report.passed is False
        assert report.chains_broken == 1
        assert report.completeness_pct < 100.0

    def test_mixed_chains(self):
        """Mixed: 2 intact, 1 degraded, 1 broken -> NOT passed."""
        contract = _make_contract(
            phases={
                "seed": PhaseContract(),
                "plan": PhaseContract(),
            },
            chains=[
                # Chain 1: intact (source and destination present, non-empty)
                PropagationChainSpec(
                    chain_id="chain_intact_1",
                    source=ChainEndpoint(phase="seed", field="field_a"),
                    destination=ChainEndpoint(phase="plan", field="field_a"),
                ),
                # Chain 2: intact
                PropagationChainSpec(
                    chain_id="chain_intact_2",
                    source=ChainEndpoint(phase="seed", field="field_b"),
                    destination=ChainEndpoint(phase="plan", field="field_b"),
                ),
                # Chain 3: degraded (destination is empty string)
                PropagationChainSpec(
                    chain_id="chain_degraded",
                    source=ChainEndpoint(phase="seed", field="field_c"),
                    destination=ChainEndpoint(phase="plan", field="field_c_dest"),
                ),
                # Chain 4: broken (source missing)
                PropagationChainSpec(
                    chain_id="chain_broken",
                    source=ChainEndpoint(phase="seed", field="field_missing"),
                    destination=ChainEndpoint(phase="plan", field="field_d_dest"),
                ),
            ],
        )
        validator = PostExecutionValidator()

        report = validator.validate(
            contract,
            final_context={
                "field_a": "value_a",
                "field_b": "value_b",
                "field_c": "original",
                "field_c_dest": "",  # empty -> degraded
                "field_d_dest": "irrelevant",
                # field_missing is absent -> broken
            },
            phase_order=["seed", "plan"],
        )

        assert report.passed is False
        assert report.chains_total == 4
        assert report.chains_intact == 2
        assert report.chains_degraded == 1
        assert report.chains_broken == 1

    def test_chain_with_verification_expression_passes(self):
        """Chain with a verification expression that evaluates to True -> INTACT."""
        contract = _make_contract(
            phases={
                "seed": PhaseContract(),
                "plan": PhaseContract(),
            },
            chains=[
                PropagationChainSpec(
                    chain_id="verified_chain",
                    source=ChainEndpoint(phase="seed", field="domain"),
                    destination=ChainEndpoint(phase="plan", field="domain"),
                    verification="source == dest",
                ),
            ],
        )
        validator = PostExecutionValidator()

        report = validator.validate(
            contract,
            final_context={"domain": "web_app"},
            phase_order=["seed", "plan"],
        )

        assert report.passed is True
        assert report.chains_intact == 1
        assert report.chains_broken == 0


# ---------------------------------------------------------------------------
# Final exit validation
# ---------------------------------------------------------------------------


class TestFinalExitValidation:
    def test_final_phase_exit_fields_all_present(self):
        """Final phase exit fields all present -> final_exit_result.passed is True."""
        contract = _make_contract(
            phases={
                "seed": PhaseContract(),
                "validate": PhaseContract(
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="validation_report",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
            },
        )
        validator = PostExecutionValidator()

        report = validator.validate(
            contract,
            final_context={"validation_report": "all good"},
            phase_order=["seed", "validate"],
        )

        assert report.final_exit_result is not None
        assert report.final_exit_result.passed is True
        assert report.passed is True

    def test_final_phase_exit_field_missing_blocking(self):
        """Final phase exit field missing (BLOCKING) -> NOT passed."""
        contract = _make_contract(
            phases={
                "seed": PhaseContract(),
                "validate": PhaseContract(
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="validation_report",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
            },
        )
        validator = PostExecutionValidator()

        report = validator.validate(
            contract,
            final_context={},  # validation_report missing
            phase_order=["seed", "validate"],
        )

        assert report.final_exit_result is not None
        assert report.final_exit_result.passed is False
        assert report.passed is False

    def test_empty_phase_order(self):
        """Empty phase_order -> final_exit_result is None."""
        contract = _make_contract(
            phases={
                "seed": PhaseContract(
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="output", severity=ConstraintSeverity.BLOCKING
                            ),
                        ],
                    ),
                ),
            },
        )
        validator = PostExecutionValidator()

        report = validator.validate(
            contract,
            final_context={},
            phase_order=[],
        )

        assert report.final_exit_result is None

    def test_final_phase_not_in_contract(self):
        """Final phase not in contract -> final_exit_result is None."""
        contract = _make_contract(
            phases={
                "seed": PhaseContract(),
            },
        )
        validator = PostExecutionValidator()

        report = validator.validate(
            contract,
            final_context={},
            phase_order=["seed", "nonexistent_phase"],
        )

        # nonexistent_phase is the last in phase_order but not in contract.phases
        # _check_final_exit returns None when phase_contract is None
        assert report.final_exit_result is None


# ---------------------------------------------------------------------------
# Runtime cross-reference
# ---------------------------------------------------------------------------


class TestRuntimeCrossReference:
    def test_no_runtime_summary(self):
        """No runtime summary -> no discrepancies."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        report = validator.validate(
            contract,
            final_context={
                "domain": "web_app",
                "seed_output": "seeds",
                "plan_output": "the plan",
            },
            phase_order=["seed", "plan"],
            runtime_summary=None,
        )

        assert report.runtime_discrepancies == []

    def test_all_runtime_passed_all_chains_intact(self):
        """All runtime passed + all chains intact -> no discrepancies."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        summary = _make_workflow_summary(
            [
                PhaseExecutionRecord(
                    phase="seed",
                    entry_result=_make_passing_result("seed"),
                    exit_result=_make_passing_result("seed", "exit"),
                ),
                PhaseExecutionRecord(
                    phase="plan",
                    entry_result=_make_passing_result("plan"),
                    exit_result=_make_passing_result("plan", "exit"),
                ),
            ],
            overall_passed=True,
        )

        report = validator.validate(
            contract,
            final_context={
                "domain": "web_app",
                "seed_output": "seeds",
                "plan_output": "the plan",
            },
            phase_order=["seed", "plan"],
            runtime_summary=summary,
        )

        assert report.runtime_discrepancies == []

    def test_runtime_passed_but_chain_broken_late_corruption(self):
        """Runtime passed + chain broken -> late_corruption discrepancy."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        summary = _make_workflow_summary(
            [
                PhaseExecutionRecord(
                    phase="seed",
                    entry_result=_make_passing_result("seed"),
                    exit_result=_make_passing_result("seed", "exit"),
                ),
                PhaseExecutionRecord(
                    phase="plan",
                    entry_result=_make_passing_result("plan"),
                    exit_result=_make_passing_result("plan", "exit"),
                ),
            ],
            overall_passed=True,
        )

        # domain field is absent from final context -> chain broken
        report = validator.validate(
            contract,
            final_context={
                "seed_output": "seeds",
                "plan_output": "the plan",
                # domain missing -> chain broken
            },
            phase_order=["seed", "plan"],
            runtime_summary=summary,
        )

        assert report.chains_broken == 1
        # At least one late_corruption discrepancy should exist
        corruption_discs = [
            d
            for d in report.runtime_discrepancies
            if d.discrepancy_type == "late_corruption"
        ]
        assert len(corruption_discs) > 0

    def test_runtime_failed_but_chains_intact_late_healing(self):
        """Runtime failed + all chains intact -> late_healing discrepancy."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        summary = _make_workflow_summary(
            [
                PhaseExecutionRecord(
                    phase="seed",
                    entry_result=_make_failing_result("seed", blocking_fields=["domain"]),
                    exit_result=_make_passing_result("seed", "exit"),
                ),
                PhaseExecutionRecord(
                    phase="plan",
                    entry_result=_make_passing_result("plan"),
                    exit_result=_make_passing_result("plan", "exit"),
                ),
            ],
            overall_passed=False,
        )

        # All chain fields present and non-empty -> chains intact
        report = validator.validate(
            contract,
            final_context={
                "domain": "web_app",
                "seed_output": "seeds",
                "plan_output": "the plan",
            },
            phase_order=["seed", "plan"],
            runtime_summary=summary,
        )

        assert report.chains_intact == 1
        assert report.chains_broken == 0
        # seed phase failed at runtime but chains are intact -> late_healing
        healing_discs = [
            d
            for d in report.runtime_discrepancies
            if d.discrepancy_type == "late_healing"
        ]
        assert len(healing_discs) > 0
        # Verify the discrepancy references the seed phase
        healing_phases = [d.phase for d in healing_discs]
        assert "seed" in healing_phases

    def test_multiple_phases_with_discrepancies(self):
        """Multiple phases with discrepancies are each reported."""
        contract = _make_contract(
            phases={
                "seed": PhaseContract(),
                "plan": PhaseContract(),
                "implement": PhaseContract(),
            },
            chains=[
                PropagationChainSpec(
                    chain_id="flow_a",
                    source=ChainEndpoint(phase="seed", field="field_a"),
                    destination=ChainEndpoint(phase="implement", field="field_a"),
                ),
            ],
        )
        validator = PostExecutionValidator()

        # All phases passed at runtime
        summary = _make_workflow_summary(
            [
                PhaseExecutionRecord(
                    phase="seed",
                    entry_result=_make_passing_result("seed"),
                    exit_result=_make_passing_result("seed", "exit"),
                ),
                PhaseExecutionRecord(
                    phase="plan",
                    entry_result=_make_passing_result("plan"),
                    exit_result=_make_passing_result("plan", "exit"),
                ),
                PhaseExecutionRecord(
                    phase="implement",
                    entry_result=_make_passing_result("implement"),
                    exit_result=_make_passing_result("implement", "exit"),
                ),
            ],
            overall_passed=True,
        )

        # field_a missing -> chain broken -> all phases that passed at runtime
        # get late_corruption discrepancies
        report = validator.validate(
            contract,
            final_context={},  # field_a missing -> broken chain
            phase_order=["seed", "plan", "implement"],
            runtime_summary=summary,
        )

        assert report.chains_broken == 1
        corruption_discs = [
            d
            for d in report.runtime_discrepancies
            if d.discrepancy_type == "late_corruption"
        ]
        # All three phases passed at runtime but chain is broken -> each gets a discrepancy
        assert len(corruption_discs) >= 2

    def test_phase_not_tracked_at_runtime_skipped(self):
        """Phase not tracked at runtime -> skipped (no discrepancy)."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        # Only "seed" tracked at runtime, "plan" was not
        summary = _make_workflow_summary(
            [
                PhaseExecutionRecord(
                    phase="seed",
                    entry_result=_make_passing_result("seed"),
                    exit_result=_make_passing_result("seed", "exit"),
                ),
            ],
            overall_passed=True,
        )

        report = validator.validate(
            contract,
            final_context={
                "domain": "web_app",
                "seed_output": "seeds",
                "plan_output": "the plan",
            },
            phase_order=["seed", "plan"],
            runtime_summary=summary,
        )

        # No discrepancy for "plan" because it was not tracked at runtime
        plan_discs = [d for d in report.runtime_discrepancies if d.phase == "plan"]
        assert len(plan_discs) == 0


# ---------------------------------------------------------------------------
# validate_chains (convenience method)
# ---------------------------------------------------------------------------


class TestValidateChains:
    def test_returns_report_with_only_chain_data(self):
        """validate_chains returns a report with chain data populated."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        report = validator.validate_chains(
            contract,
            final_context={
                "domain": "web_app",
                "seed_output": "seeds",
                "plan_output": "the plan",
            },
        )

        assert report.passed is True
        assert report.chains_total == 1
        assert report.chains_intact == 1
        assert report.completeness_pct == 100.0

    def test_final_exit_result_is_none(self):
        """validate_chains does not perform final exit validation."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        report = validator.validate_chains(
            contract,
            final_context={
                "domain": "web_app",
                "seed_output": "seeds",
                "plan_output": "the plan",
            },
        )

        assert report.final_exit_result is None

    def test_runtime_discrepancies_is_empty(self):
        """validate_chains does not perform runtime cross-reference."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        report = validator.validate_chains(
            contract,
            final_context={
                "domain": "web_app",
                "seed_output": "seeds",
                "plan_output": "the plan",
            },
        )

        assert report.runtime_discrepancies == []


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_workflow_three_phases_all_pass(self):
        """Full workflow: 3 phases with chains, all pass."""
        contract = _make_contract(
            phases={
                "seed": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(
                                name="domain", severity=ConstraintSeverity.BLOCKING
                            ),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="seed_output",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(
                                name="seed_output",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="plan_output",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
                "implement": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(
                                name="plan_output",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="code_output",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
            },
            chains=[
                PropagationChainSpec(
                    chain_id="domain_flow",
                    source=ChainEndpoint(phase="seed", field="domain"),
                    destination=ChainEndpoint(phase="implement", field="domain"),
                ),
                PropagationChainSpec(
                    chain_id="seed_to_plan",
                    source=ChainEndpoint(phase="seed", field="seed_output"),
                    destination=ChainEndpoint(phase="plan", field="seed_output"),
                ),
            ],
        )
        validator = PostExecutionValidator()

        report = validator.validate(
            contract,
            final_context={
                "domain": "web_app",
                "seed_output": "seeds",
                "plan_output": "the plan",
                "code_output": "the code",
            },
            phase_order=["seed", "plan", "implement"],
        )

        assert report.passed is True
        assert report.chains_total == 2
        assert report.chains_intact == 2
        assert report.chains_broken == 0
        assert report.completeness_pct == 100.0
        assert report.final_exit_result is not None
        assert report.final_exit_result.passed is True
        assert report.runtime_discrepancies == []

    def test_full_workflow_with_layer4_cross_reference(self):
        """Full workflow with Layer 4 summary cross-reference."""
        contract = _two_phase_contract_with_chain()
        validator = PostExecutionValidator()

        # Layer 4: seed passed at runtime but domain will be missing post-execution
        summary = _make_workflow_summary(
            [
                PhaseExecutionRecord(
                    phase="seed",
                    entry_result=_make_passing_result("seed"),
                    exit_result=_make_passing_result("seed", "exit"),
                ),
                PhaseExecutionRecord(
                    phase="plan",
                    entry_result=_make_passing_result("plan"),
                    exit_result=_make_passing_result("plan", "exit"),
                ),
            ],
            overall_passed=True,
        )

        # domain is missing from final context -> chain broken
        report = validator.validate(
            contract,
            final_context={
                "seed_output": "seeds",
                "plan_output": "the plan",
                # domain deliberately omitted -> chain breaks
            },
            phase_order=["seed", "plan"],
            runtime_summary=summary,
        )

        assert report.passed is False
        assert report.chains_broken == 1

        # Runtime cross-reference should detect late corruption
        corruption_discs = [
            d
            for d in report.runtime_discrepancies
            if d.discrepancy_type == "late_corruption"
        ]
        assert len(corruption_discs) > 0

    def test_default_phase_order_from_contract_keys(self):
        """When phase_order is None, uses contract.phases.keys() order."""
        contract = _make_contract(
            phases={
                "alpha": PhaseContract(
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="alpha_out",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
                "beta": PhaseContract(
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(
                                name="beta_out",
                                severity=ConstraintSeverity.BLOCKING,
                            ),
                        ],
                    ),
                ),
            },
        )
        validator = PostExecutionValidator()

        # phase_order=None -> defaults to ["alpha", "beta"]
        # Final phase is "beta", its exit requires "beta_out"
        report = validator.validate(
            contract,
            final_context={"alpha_out": "done", "beta_out": "done"},
            phase_order=None,
        )

        assert report.passed is True
        # final_exit_result should be for "beta" (last phase)
        assert report.final_exit_result is not None
        assert report.final_exit_result.phase == "beta"
        assert report.final_exit_result.passed is True
