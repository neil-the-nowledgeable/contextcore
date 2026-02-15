"""
Runtime boundary guard for context propagation contracts — Layer 4.

Wraps Layer 1's ``BoundaryValidator`` into an automatic guard that
validates context at each phase boundary and collects results across
an entire workflow run.

Three enforcement modes:

- **strict** — BLOCKING failures raise ``BoundaryViolationError``.
- **permissive** — BLOCKING failures are logged but execution continues.
- **audit** — everything is logged/emitted via OTel, nothing blocks.

Usage::

    from contextcore.contracts.runtime import RuntimeBoundaryGuard

    guard = RuntimeBoundaryGuard(contract, mode="strict")

    # Context-manager style (recommended)
    with guard.phase("implement", context):
        run_implement_phase(context)

    # Or explicit enter/exit
    guard.enter_phase("implement", context)
    run_implement_phase(context)
    guard.exit_phase("implement", context)

    # After all phases
    summary = guard.summarize()
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.propagation.schema import ContextContract
from contextcore.contracts.propagation.validator import (
    BoundaryValidator,
    ContractValidationResult,
)
from contextcore.contracts.types import (
    ConstraintSeverity,
    EnforcementMode,
    PropagationStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BoundaryViolationError(Exception):
    """Raised in strict mode when a BLOCKING boundary violation occurs."""

    def __init__(
        self,
        phase: str,
        direction: str,
        result: ContractValidationResult,
    ) -> None:
        self.phase = phase
        self.direction = direction
        self.result = result
        failures = ", ".join(result.blocking_failures)
        super().__init__(
            f"Boundary violation in phase '{phase}' ({direction}): "
            f"blocking fields: [{failures}]"
        )


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class PhaseExecutionRecord(BaseModel):
    """Records all boundary validation results for a single phase."""

    model_config = ConfigDict(extra="forbid")

    phase: str
    entry_result: Optional[ContractValidationResult] = None
    exit_result: Optional[ContractValidationResult] = None
    enrichment_result: Optional[ContractValidationResult] = None

    @property
    def passed(self) -> bool:
        """True if no boundary had BLOCKING failures."""
        for r in (self.entry_result, self.exit_result, self.enrichment_result):
            if r is not None and not r.passed:
                return False
        return True

    @property
    def propagation_status(self) -> PropagationStatus:
        """Worst propagation status across all boundaries."""
        statuses: list[PropagationStatus] = []
        for r in (self.entry_result, self.exit_result, self.enrichment_result):
            if r is not None:
                statuses.append(r.propagation_status)
        if not statuses:
            return PropagationStatus.PROPAGATED
        priority = [
            PropagationStatus.FAILED,
            PropagationStatus.PARTIAL,
            PropagationStatus.DEFAULTED,
            PropagationStatus.PROPAGATED,
        ]
        for status in priority:
            if status in statuses:
                return status
        return PropagationStatus.PROPAGATED


class WorkflowRunSummary(BaseModel):
    """Aggregated summary of all phase boundary checks in a workflow run."""

    model_config = ConfigDict(extra="forbid")

    mode: EnforcementMode
    phases: list[PhaseExecutionRecord] = Field(default_factory=list)
    total_phases: int = 0
    passed_phases: int = 0
    failed_phases: int = 0
    total_fields_checked: int = 0
    total_blocking_failures: int = 0
    total_warnings: int = 0
    total_defaults_applied: int = 0
    overall_passed: bool = True
    overall_status: PropagationStatus = PropagationStatus.PROPAGATED


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class RuntimeBoundaryGuard:
    """Validates context at phase boundaries using Layer 1 contracts.

    Wraps ``BoundaryValidator`` with enforcement mode semantics and
    result collection across an entire workflow run.
    """

    def __init__(
        self,
        contract: ContextContract,
        mode: EnforcementMode | str = EnforcementMode.STRICT,
        validator: Optional[BoundaryValidator] = None,
    ) -> None:
        self._contract = contract
        self._mode = (
            EnforcementMode(mode) if isinstance(mode, str) else mode
        )
        self._validator = validator or BoundaryValidator()
        self._records: list[PhaseExecutionRecord] = []
        self._current_record: Optional[PhaseExecutionRecord] = None

    @property
    def mode(self) -> EnforcementMode:
        return self._mode

    @property
    def records(self) -> list[PhaseExecutionRecord]:
        return list(self._records)

    def enter_phase(
        self, phase: str, context: dict[str, Any]
    ) -> ContractValidationResult:
        """Validate entry requirements and enrichment for a phase.

        Returns the entry validation result.  In strict mode, raises
        ``BoundaryViolationError`` if BLOCKING fields are missing.
        """
        record = PhaseExecutionRecord(phase=phase)
        self._current_record = record

        # Validate entry
        entry_result = self._validator.validate_entry(
            phase, context, self._contract
        )
        record.entry_result = entry_result
        self._handle_result(phase, "entry", entry_result)

        # Validate enrichment
        enrichment_result = self._validator.validate_enrichment(
            phase, context, self._contract
        )
        record.enrichment_result = enrichment_result
        # Enrichment is never blocking by design, but we still record it
        self._log_result(phase, "enrichment", enrichment_result)

        return entry_result

    def exit_phase(
        self, phase: str, context: dict[str, Any]
    ) -> ContractValidationResult:
        """Validate exit requirements for a phase.

        Returns the exit validation result.  In strict mode, raises
        ``BoundaryViolationError`` if BLOCKING fields are missing.
        """
        exit_result = self._validator.validate_exit(
            phase, context, self._contract
        )

        if self._current_record is not None and self._current_record.phase == phase:
            self._current_record.exit_result = exit_result
            self._records.append(self._current_record)
            self._current_record = None
        else:
            # exit_phase called without matching enter_phase — create a record
            record = PhaseExecutionRecord(phase=phase, exit_result=exit_result)
            self._records.append(record)

        self._handle_result(phase, "exit", exit_result)
        return exit_result

    @contextmanager
    def phase(
        self, phase_name: str, context: dict[str, Any]
    ) -> Generator[ContractValidationResult, None, None]:
        """Context manager that validates entry on enter, exit on leave.

        Usage::

            with guard.phase("implement", ctx) as entry_result:
                if entry_result.passed:
                    run_implement(ctx)
        """
        entry_result = self.enter_phase(phase_name, context)
        try:
            yield entry_result
        finally:
            self.exit_phase(phase_name, context)

    def summarize(self) -> WorkflowRunSummary:
        """Produce an aggregated summary of all phase records."""
        total_fields = 0
        total_blocking = 0
        total_warnings = 0
        total_defaults = 0

        for record in self._records:
            for r in (record.entry_result, record.exit_result, record.enrichment_result):
                if r is None:
                    continue
                total_fields += len(r.field_results)
                total_blocking += len(r.blocking_failures)
                total_warnings += len(r.warnings)
                total_defaults += sum(
                    1 for fr in r.field_results if fr.default_applied
                )

        passed_phases = sum(1 for r in self._records if r.passed)
        failed_phases = len(self._records) - passed_phases
        overall_passed = failed_phases == 0

        # Determine overall status
        statuses = [r.propagation_status for r in self._records]
        priority = [
            PropagationStatus.FAILED,
            PropagationStatus.PARTIAL,
            PropagationStatus.DEFAULTED,
            PropagationStatus.PROPAGATED,
        ]
        overall_status = PropagationStatus.PROPAGATED
        for status in priority:
            if status in statuses:
                overall_status = status
                break

        return WorkflowRunSummary(
            mode=self._mode,
            phases=list(self._records),
            total_phases=len(self._records),
            passed_phases=passed_phases,
            failed_phases=failed_phases,
            total_fields_checked=total_fields,
            total_blocking_failures=total_blocking,
            total_warnings=total_warnings,
            total_defaults_applied=total_defaults,
            overall_passed=overall_passed,
            overall_status=overall_status,
        )

    def reset(self) -> None:
        """Clear all collected records for a fresh run."""
        self._records.clear()
        self._current_record = None

    # -- internal --------------------------------------------------------------

    def _handle_result(
        self,
        phase: str,
        direction: str,
        result: ContractValidationResult,
    ) -> None:
        """Enforce the result according to the current mode."""
        self._log_result(phase, direction, result)

        if not result.passed and self._mode == EnforcementMode.STRICT:
            raise BoundaryViolationError(phase, direction, result)

    def _log_result(
        self,
        phase: str,
        direction: str,
        result: ContractValidationResult,
    ) -> None:
        """Log the validation result."""
        if not result.passed:
            logger.warning(
                "Runtime boundary [%s] %s/%s FAILED: blocking=%s",
                self._mode.value,
                phase,
                direction,
                result.blocking_failures,
            )
        elif result.warnings:
            logger.info(
                "Runtime boundary [%s] %s/%s passed with %d warning(s)",
                self._mode.value,
                phase,
                direction,
                len(result.warnings),
            )
        else:
            logger.debug(
                "Runtime boundary [%s] %s/%s passed",
                self._mode.value,
                phase,
                direction,
            )
