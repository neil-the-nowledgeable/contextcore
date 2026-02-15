"""Tests for RuntimeBoundaryGuard (Layer 4)."""

import pytest
from pydantic import ValidationError

from contextcore.contracts.propagation.schema import (
    ContextContract,
    FieldSpec,
    PhaseContract,
    PhaseEntryContract,
    PhaseExitContract,
)
from contextcore.contracts.propagation.validator import ContractValidationResult
from contextcore.contracts.runtime.guard import (
    BoundaryViolationError,
    PhaseExecutionRecord,
    RuntimeBoundaryGuard,
    WorkflowRunSummary,
)
from contextcore.contracts.types import (
    ConstraintSeverity,
    EnforcementMode,
    PropagationStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(phases):
    """Create a minimal contract with the given phases dict."""
    return ContextContract(
        schema_version="0.1.0",
        pipeline_id="test-pipeline",
        phases=phases,
    )


def _simple_contract():
    """Contract with one phase ('plan') requiring 'domain' on entry, 'plan_output' on exit."""
    return _make_contract(
        phases={
            "plan": PhaseContract(
                entry=PhaseEntryContract(
                    required=[
                        FieldSpec(name="domain", severity=ConstraintSeverity.BLOCKING),
                    ],
                    enrichment=[
                        FieldSpec(
                            name="domain_hints",
                            severity=ConstraintSeverity.WARNING,
                            default="none",
                        ),
                    ],
                ),
                exit=PhaseExitContract(
                    required=[
                        FieldSpec(name="plan_output", severity=ConstraintSeverity.BLOCKING),
                    ],
                ),
            ),
        },
    )


def _multi_phase_contract():
    """Contract with three phases: plan -> implement -> verify."""
    return _make_contract(
        phases={
            "plan": PhaseContract(
                entry=PhaseEntryContract(
                    required=[
                        FieldSpec(name="domain", severity=ConstraintSeverity.BLOCKING),
                    ],
                ),
                exit=PhaseExitContract(
                    required=[
                        FieldSpec(name="plan_output", severity=ConstraintSeverity.BLOCKING),
                    ],
                ),
            ),
            "implement": PhaseContract(
                entry=PhaseEntryContract(
                    required=[
                        FieldSpec(name="plan_output", severity=ConstraintSeverity.BLOCKING),
                    ],
                    enrichment=[
                        FieldSpec(
                            name="style_guide",
                            severity=ConstraintSeverity.WARNING,
                            default="standard",
                        ),
                    ],
                ),
                exit=PhaseExitContract(
                    required=[
                        FieldSpec(name="code_output", severity=ConstraintSeverity.BLOCKING),
                    ],
                ),
            ),
            "verify": PhaseContract(
                entry=PhaseEntryContract(
                    required=[
                        FieldSpec(name="code_output", severity=ConstraintSeverity.BLOCKING),
                    ],
                ),
                exit=PhaseExitContract(
                    required=[
                        FieldSpec(name="verified", severity=ConstraintSeverity.BLOCKING),
                    ],
                ),
            ),
        },
    )


# ---------------------------------------------------------------------------
# BoundaryViolationError
# ---------------------------------------------------------------------------


class TestBoundaryViolationError:
    def test_construction_stores_attributes(self):
        """Construction stores phase, direction, and result."""
        result = ContractValidationResult(
            passed=False,
            phase="plan",
            direction="entry",
            blocking_failures=["domain"],
        )
        error = BoundaryViolationError("plan", "entry", result)

        assert error.phase == "plan"
        assert error.direction == "entry"
        assert error.result is result

    def test_message_includes_blocking_field_names(self):
        """Error message includes the names of the blocking fields."""
        result = ContractValidationResult(
            passed=False,
            phase="implement",
            direction="exit",
            blocking_failures=["code_output", "tests_output"],
        )
        error = BoundaryViolationError("implement", "exit", result)
        message = str(error)

        assert "implement" in message
        assert "exit" in message
        assert "code_output" in message
        assert "tests_output" in message


# ---------------------------------------------------------------------------
# PhaseExecutionRecord
# ---------------------------------------------------------------------------


class TestPhaseExecutionRecord:
    def test_passed_when_all_results_passed(self):
        """Record reports passed=True when all present results have passed=True."""
        record = PhaseExecutionRecord(
            phase="plan",
            entry_result=ContractValidationResult(passed=True, phase="plan", direction="entry"),
            exit_result=ContractValidationResult(passed=True, phase="plan", direction="exit"),
        )
        assert record.passed is True

    def test_passed_when_only_entry_present_and_passed(self):
        """Record reports passed=True when only entry_result exists and passes."""
        record = PhaseExecutionRecord(
            phase="plan",
            entry_result=ContractValidationResult(passed=True, phase="plan", direction="entry"),
        )
        assert record.passed is True

    def test_not_passed_when_entry_failed(self):
        """Record reports passed=False when entry_result has passed=False."""
        record = PhaseExecutionRecord(
            phase="plan",
            entry_result=ContractValidationResult(
                passed=False,
                phase="plan",
                direction="entry",
                blocking_failures=["domain"],
            ),
        )
        assert record.passed is False

    def test_not_passed_when_exit_failed(self):
        """Record reports passed=False when exit_result has passed=False."""
        record = PhaseExecutionRecord(
            phase="plan",
            entry_result=ContractValidationResult(passed=True, phase="plan", direction="entry"),
            exit_result=ContractValidationResult(
                passed=False,
                phase="plan",
                direction="exit",
                blocking_failures=["plan_output"],
            ),
        )
        assert record.passed is False

    def test_propagation_status_returns_worst(self):
        """propagation_status returns the worst status across all boundaries."""
        # Entry: PROPAGATED, Exit: FAILED -> overall should be FAILED
        record = PhaseExecutionRecord(
            phase="plan",
            entry_result=ContractValidationResult(
                passed=True,
                phase="plan",
                direction="entry",
                propagation_status=PropagationStatus.PROPAGATED,
            ),
            exit_result=ContractValidationResult(
                passed=False,
                phase="plan",
                direction="exit",
                propagation_status=PropagationStatus.FAILED,
            ),
        )
        assert record.propagation_status == PropagationStatus.FAILED

        # Entry: DEFAULTED, Exit: PARTIAL -> PARTIAL wins (worse)
        record2 = PhaseExecutionRecord(
            phase="plan",
            entry_result=ContractValidationResult(
                passed=True,
                phase="plan",
                direction="entry",
                propagation_status=PropagationStatus.DEFAULTED,
            ),
            exit_result=ContractValidationResult(
                passed=True,
                phase="plan",
                direction="exit",
                propagation_status=PropagationStatus.PARTIAL,
            ),
        )
        assert record2.propagation_status == PropagationStatus.PARTIAL

        # No results at all -> defaults to PROPAGATED
        record3 = PhaseExecutionRecord(phase="empty")
        assert record3.propagation_status == PropagationStatus.PROPAGATED


# ---------------------------------------------------------------------------
# WorkflowRunSummary
# ---------------------------------------------------------------------------


class TestWorkflowRunSummary:
    def test_basic_construction_with_defaults(self):
        """WorkflowRunSummary can be constructed with just mode; defaults are correct."""
        summary = WorkflowRunSummary(mode=EnforcementMode.STRICT)

        assert summary.mode == EnforcementMode.STRICT
        assert summary.phases == []
        assert summary.total_phases == 0
        assert summary.passed_phases == 0
        assert summary.failed_phases == 0
        assert summary.total_fields_checked == 0
        assert summary.total_blocking_failures == 0
        assert summary.total_warnings == 0
        assert summary.total_defaults_applied == 0
        assert summary.overall_passed is True
        assert summary.overall_status == PropagationStatus.PROPAGATED

    def test_extra_fields_rejected(self):
        """ConfigDict extra='forbid' rejects extra fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            WorkflowRunSummary(
                mode=EnforcementMode.STRICT,
                unexpected_field="oops",
            )


# ---------------------------------------------------------------------------
# RuntimeBoundaryGuard - strict mode
# ---------------------------------------------------------------------------


class TestStrictMode:
    def test_enter_phase_passes_when_fields_present(self):
        """enter_phase returns a passing result when required fields are present."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.STRICT)

        result = guard.enter_phase("plan", {"domain": "web_app"})

        assert result.passed is True

    def test_enter_phase_raises_on_blocking_failure(self):
        """enter_phase raises BoundaryViolationError when BLOCKING field is missing."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.STRICT)

        with pytest.raises(BoundaryViolationError) as exc_info:
            guard.enter_phase("plan", {})

        assert exc_info.value.phase == "plan"
        assert exc_info.value.direction == "entry"
        assert "domain" in exc_info.value.result.blocking_failures

    def test_exit_phase_passes_when_fields_present(self):
        """exit_phase returns a passing result when required exit fields are present."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.STRICT)

        # Must enter first so the record is created
        guard.enter_phase("plan", {"domain": "web_app"})
        result = guard.exit_phase("plan", {"domain": "web_app", "plan_output": "the plan"})

        assert result.passed is True

    def test_exit_phase_raises_on_blocking_failure(self):
        """exit_phase raises BoundaryViolationError when BLOCKING exit field is missing."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.STRICT)

        guard.enter_phase("plan", {"domain": "web_app"})

        with pytest.raises(BoundaryViolationError) as exc_info:
            guard.exit_phase("plan", {"domain": "web_app"})  # plan_output missing

        assert exc_info.value.phase == "plan"
        assert exc_info.value.direction == "exit"
        assert "plan_output" in exc_info.value.result.blocking_failures

    def test_phase_context_manager_validates_entry_and_exit(self):
        """The phase() context manager validates both entry and exit."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.STRICT)

        context = {"domain": "web_app", "plan_output": "the plan"}

        with guard.phase("plan", context) as entry_result:
            assert entry_result.passed is True

        # Record should be stored
        assert len(guard.records) == 1
        record = guard.records[0]
        assert record.phase == "plan"
        assert record.entry_result is not None
        assert record.exit_result is not None
        assert record.passed is True

    def test_phase_context_manager_raises_on_entry_failure(self):
        """The phase() context manager raises BoundaryViolationError on entry failure."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.STRICT)

        with pytest.raises(BoundaryViolationError) as exc_info:
            with guard.phase("plan", {}):
                pass  # Should never reach here

        assert exc_info.value.phase == "plan"
        assert exc_info.value.direction == "entry"


# ---------------------------------------------------------------------------
# RuntimeBoundaryGuard - permissive mode
# ---------------------------------------------------------------------------


class TestPermissiveMode:
    def test_enter_phase_does_not_raise_on_blocking_failure(self):
        """In permissive mode, enter_phase does NOT raise on BLOCKING failure."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        # Should NOT raise even though 'domain' is missing
        result = guard.enter_phase("plan", {})
        assert result.passed is False

    def test_exit_phase_does_not_raise_on_blocking_failure(self):
        """In permissive mode, exit_phase does NOT raise on BLOCKING failure."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        guard.enter_phase("plan", {})
        # Should NOT raise even though 'plan_output' is missing
        result = guard.exit_phase("plan", {})
        assert result.passed is False

    def test_result_still_records_failure(self):
        """In permissive mode, the result still records that the phase failed."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        guard.enter_phase("plan", {})
        guard.exit_phase("plan", {})

        assert len(guard.records) == 1
        record = guard.records[0]
        assert record.passed is False
        assert record.entry_result is not None
        assert record.entry_result.passed is False

    def test_phase_context_manager_completes_without_error(self):
        """In permissive mode, phase() context manager completes even with failures."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        # Both entry and exit will have blocking failures, but no exception
        with guard.phase("plan", {}) as entry_result:
            assert entry_result.passed is False

        assert len(guard.records) == 1


# ---------------------------------------------------------------------------
# RuntimeBoundaryGuard - audit mode
# ---------------------------------------------------------------------------


class TestAuditMode:
    def test_treats_blocking_same_as_permissive(self):
        """In audit mode, BLOCKING failures do not raise (same as permissive)."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.AUDIT)

        # Should NOT raise
        result = guard.enter_phase("plan", {})
        assert result.passed is False

    def test_records_results(self):
        """In audit mode, results are still recorded in the guard."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.AUDIT)

        guard.enter_phase("plan", {})
        guard.exit_phase("plan", {})

        assert len(guard.records) == 1
        record = guard.records[0]
        assert record.entry_result is not None
        assert record.exit_result is not None

    def test_warning_fields_still_recorded(self):
        """In audit mode, WARNING field results are still recorded."""
        contract = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="hint", severity=ConstraintSeverity.WARNING),
                        ],
                    ),
                ),
            },
        )
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.AUDIT)

        result = guard.enter_phase("plan", {})
        # WARNING field missing is not a blocking failure so passed=True
        assert result.passed is True
        # But warnings should be recorded
        assert len(result.warnings) >= 1
        guard.exit_phase("plan", {})

        assert len(guard.records) == 1


# ---------------------------------------------------------------------------
# RuntimeBoundaryGuard - summarize
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_empty_guard_returns_empty_summary(self):
        """An empty guard (no phases run) returns a summary with all zeros."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.STRICT)

        summary = guard.summarize()

        assert summary.total_phases == 0
        assert summary.passed_phases == 0
        assert summary.failed_phases == 0
        assert summary.total_fields_checked == 0
        assert summary.total_blocking_failures == 0
        assert summary.total_warnings == 0
        assert summary.total_defaults_applied == 0
        assert summary.overall_passed is True
        assert summary.overall_status == PropagationStatus.PROPAGATED

    def test_summarize_after_one_passing_phase(self):
        """Summary after one passing phase shows 1 passed, 0 failed."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.STRICT)

        context = {"domain": "web_app", "plan_output": "the plan"}
        guard.enter_phase("plan", context)
        guard.exit_phase("plan", context)

        summary = guard.summarize()

        assert summary.total_phases == 1
        assert summary.passed_phases == 1
        assert summary.failed_phases == 0
        assert summary.overall_passed is True
        assert summary.total_fields_checked >= 2  # at least domain + plan_output

    def test_summarize_after_mixed_phases(self):
        """Summary after one passing phase and one failing phase."""
        contract = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="domain", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(name="plan_output", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
                "implement": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="plan_output", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[
                            FieldSpec(name="code_output", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        # Use permissive mode so we can observe failures without exceptions
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        # Phase 1: passes
        ctx = {"domain": "web_app", "plan_output": "the plan"}
        guard.enter_phase("plan", ctx)
        guard.exit_phase("plan", ctx)

        # Phase 2: entry passes (plan_output present), exit fails (code_output missing)
        guard.enter_phase("implement", ctx)
        guard.exit_phase("implement", ctx)

        summary = guard.summarize()

        assert summary.total_phases == 2
        assert summary.passed_phases == 1
        assert summary.failed_phases == 1
        assert summary.overall_passed is False
        assert summary.total_blocking_failures >= 1

    def test_total_fields_checked_counts_all(self):
        """total_fields_checked counts field results across all boundaries."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        context = {"domain": "web_app", "plan_output": "the plan"}
        guard.enter_phase("plan", context)
        guard.exit_phase("plan", context)

        summary = guard.summarize()

        # Entry has 1 required field (domain) + enrichment has 1 field (domain_hints)
        # Exit has 1 required field (plan_output)
        # Total = at least 3
        assert summary.total_fields_checked >= 3

    def test_total_defaults_applied_counts_default_fields(self):
        """total_defaults_applied counts fields where default_applied=True."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        # domain_hints is missing and has default="none" -> default will be applied
        context = {"domain": "web_app", "plan_output": "the plan"}
        guard.enter_phase("plan", context)
        guard.exit_phase("plan", context)

        summary = guard.summarize()

        # domain_hints should have its default applied
        assert summary.total_defaults_applied >= 1

    def test_reset_clears_records(self):
        """reset() clears all collected records."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        context = {"domain": "web_app", "plan_output": "the plan"}
        guard.enter_phase("plan", context)
        guard.exit_phase("plan", context)

        assert len(guard.records) == 1

        guard.reset()

        assert len(guard.records) == 0
        summary = guard.summarize()
        assert summary.total_phases == 0


# ---------------------------------------------------------------------------
# RuntimeBoundaryGuard - enrichment
# ---------------------------------------------------------------------------


class TestEnrichment:
    def test_enter_phase_also_validates_enrichment(self):
        """enter_phase validates enrichment fields in addition to entry fields."""
        contract = _simple_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        # domain_hints is an enrichment field and is missing
        guard.enter_phase("plan", {"domain": "web_app"})
        guard.exit_phase("plan", {"domain": "web_app", "plan_output": "plan"})

        record = guard.records[0]
        assert record.enrichment_result is not None
        # domain_hints is WARNING severity with a default -> should be recorded
        assert len(record.enrichment_result.field_results) >= 1

    def test_enrichment_result_stored_in_record(self):
        """The enrichment result is stored separately in the PhaseExecutionRecord."""
        contract = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="domain", severity=ConstraintSeverity.BLOCKING),
                        ],
                        enrichment=[
                            FieldSpec(
                                name="author",
                                severity=ConstraintSeverity.WARNING,
                                default="unknown",
                            ),
                            FieldSpec(
                                name="priority",
                                severity=ConstraintSeverity.WARNING,
                            ),
                        ],
                    ),
                ),
            },
        )
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        guard.enter_phase("plan", {"domain": "web_app"})
        guard.exit_phase("plan", {"domain": "web_app"})

        record = guard.records[0]
        assert record.enrichment_result is not None
        assert record.enrichment_result.direction == "enrichment"
        # Two enrichment fields checked
        assert len(record.enrichment_result.field_results) == 2


# ---------------------------------------------------------------------------
# Integration patterns
# ---------------------------------------------------------------------------


class TestIntegrationPatterns:
    def test_full_workflow_enter_exit_three_phases_summarize(self):
        """Full workflow: enter/exit three phases, then summarize."""
        contract = _multi_phase_contract()
        guard = RuntimeBoundaryGuard(contract, mode=EnforcementMode.PERMISSIVE)

        # Phase 1: plan
        ctx = {"domain": "web_app"}
        guard.enter_phase("plan", ctx)
        ctx["plan_output"] = "the plan"
        guard.exit_phase("plan", ctx)

        # Phase 2: implement
        guard.enter_phase("implement", ctx)
        ctx["code_output"] = "the code"
        guard.exit_phase("implement", ctx)

        # Phase 3: verify
        guard.enter_phase("verify", ctx)
        ctx["verified"] = True
        guard.exit_phase("verify", ctx)

        summary = guard.summarize()

        assert summary.total_phases == 3
        assert summary.passed_phases == 3
        assert summary.failed_phases == 0
        assert summary.overall_passed is True
        assert summary.mode == EnforcementMode.PERMISSIVE

        # Verify individual phase records
        phases_in_records = [r.phase for r in summary.phases]
        assert phases_in_records == ["plan", "implement", "verify"]

    def test_mode_can_be_passed_as_string(self):
        """EnforcementMode can be passed as a string to the constructor."""
        contract = _simple_contract()

        guard_strict = RuntimeBoundaryGuard(contract, mode="strict")
        assert guard_strict.mode == EnforcementMode.STRICT

        guard_permissive = RuntimeBoundaryGuard(contract, mode="permissive")
        assert guard_permissive.mode == EnforcementMode.PERMISSIVE

        guard_audit = RuntimeBoundaryGuard(contract, mode="audit")
        assert guard_audit.mode == EnforcementMode.AUDIT
