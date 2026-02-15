"""
Boundary validator for context propagation contracts.

Validates that a workflow context dict satisfies the entry/exit/enrichment
requirements declared in a ``ContextContract``.  Follows the
``_enforce()`` + structured error reporting pattern from
``contracts/a2a/boundary.py``.

Severity behavior:
    - ``BLOCKING`` → sets ``passed=False``, caller should halt the phase.
    - ``WARNING``  → sets field status to DEFAULTED, continues.
    - ``ADVISORY`` → logs only, no impact on pass/fail.

Usage::

    from contextcore.contracts.propagation.validator import BoundaryValidator

    validator = BoundaryValidator()
    result = validator.validate_entry("implement", context, contract)
    if not result.passed:
        raise PhaseContextError(...)
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.propagation.schema import (
    ContextContract,
    FieldSpec,
)
from contextcore.contracts.types import ConstraintSeverity, PropagationStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class FieldValidationResult(BaseModel):
    """Result of validating a single field at a boundary."""

    model_config = ConfigDict(extra="forbid")

    field: str
    status: PropagationStatus
    severity: ConstraintSeverity
    message: str = ""
    default_applied: bool = False


class ContractValidationResult(BaseModel):
    """Aggregated result of boundary validation for one phase."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    phase: str
    direction: str = Field(description="entry, exit, or enrichment")
    field_results: list[FieldValidationResult] = Field(default_factory=list)
    blocking_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    propagation_status: PropagationStatus = PropagationStatus.PROPAGATED

    def to_gate_result(self) -> dict[str, Any]:
        """Convert to a GateResult-compatible dict for emission via GateEmitter."""
        return {
            "gate_id": f"propagation.{self.phase}.{self.direction}",
            "phase": self.phase,
            "result": "pass" if self.passed else "fail",
            "severity": "error" if not self.passed else "info",
            "reason": (
                f"Blocking failures: {self.blocking_failures}"
                if self.blocking_failures
                else f"Propagation {self.propagation_status.value}"
            ),
            "blocking": not self.passed,
            "evidence": [
                {"type": "field_validation", "ref": fr.field, "description": fr.message}
                for fr in self.field_results
                if fr.status != PropagationStatus.PROPAGATED
            ],
        }


# ---------------------------------------------------------------------------
# Field resolution
# ---------------------------------------------------------------------------


def _resolve_field(context: dict[str, Any], field_path: str) -> tuple[bool, Any]:
    """Resolve a dot-path field from a context dict.

    Returns (present, value).
    """
    parts = field_path.split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def _validate_field(
    spec: FieldSpec,
    context: dict[str, Any],
) -> FieldValidationResult:
    """Validate a single field spec against the context."""
    present, value = _resolve_field(context, spec.name)

    if not present or value is None:
        if spec.severity == ConstraintSeverity.BLOCKING:
            return FieldValidationResult(
                field=spec.name,
                status=PropagationStatus.FAILED,
                severity=spec.severity,
                message=f"Required field '{spec.name}' is missing",
            )
        elif spec.severity == ConstraintSeverity.WARNING:
            # Apply default if available
            if spec.default is not None:
                _set_field(context, spec.name, spec.default)
                return FieldValidationResult(
                    field=spec.name,
                    status=PropagationStatus.DEFAULTED,
                    severity=spec.severity,
                    message=f"Field '{spec.name}' defaulted to {spec.default!r}",
                    default_applied=True,
                )
            return FieldValidationResult(
                field=spec.name,
                status=PropagationStatus.DEFAULTED,
                severity=spec.severity,
                message=f"Field '{spec.name}' is missing (no default)",
            )
        else:
            # ADVISORY — log only
            return FieldValidationResult(
                field=spec.name,
                status=PropagationStatus.PARTIAL,
                severity=spec.severity,
                message=f"Advisory: field '{spec.name}' is absent",
            )

    return FieldValidationResult(
        field=spec.name,
        status=PropagationStatus.PROPAGATED,
        severity=spec.severity,
    )


def _set_field(context: dict[str, Any], field_path: str, value: Any) -> None:
    """Set a dot-path field in the context dict, creating intermediates."""
    parts = field_path.split(".")
    current = context
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class BoundaryValidator:
    """Validates context dicts against propagation contracts."""

    def validate_entry(
        self,
        phase: str,
        context: dict[str, Any],
        contract: ContextContract,
    ) -> ContractValidationResult:
        """Validate entry requirements for a phase.

        Args:
            phase: Phase name (e.g. ``"implement"``).
            context: Shared workflow context dict.
            contract: Loaded context propagation contract.

        Returns:
            Validation result with field-level detail.
        """
        phase_contract = contract.phases.get(phase)
        if phase_contract is None:
            return ContractValidationResult(
                passed=True,
                phase=phase,
                direction="entry",
            )

        return self._validate_fields(
            phase=phase,
            direction="entry",
            fields=phase_contract.entry.required,
            context=context,
        )

    def validate_exit(
        self,
        phase: str,
        context: dict[str, Any],
        contract: ContextContract,
    ) -> ContractValidationResult:
        """Validate exit requirements for a phase.

        Args:
            phase: Phase name.
            context: Shared workflow context dict (after phase execution).
            contract: Loaded context propagation contract.

        Returns:
            Validation result with field-level detail.
        """
        phase_contract = contract.phases.get(phase)
        if phase_contract is None:
            return ContractValidationResult(
                passed=True,
                phase=phase,
                direction="exit",
            )

        return self._validate_fields(
            phase=phase,
            direction="exit",
            fields=phase_contract.exit.required,
            context=context,
        )

    def validate_enrichment(
        self,
        phase: str,
        context: dict[str, Any],
        contract: ContextContract,
    ) -> ContractValidationResult:
        """Validate enrichment fields for a phase.

        Enrichment fields degrade gracefully — they use WARNING/ADVISORY
        severity and apply defaults when absent.

        Args:
            phase: Phase name.
            context: Shared workflow context dict.
            contract: Loaded context propagation contract.

        Returns:
            Validation result with field-level detail.
        """
        phase_contract = contract.phases.get(phase)
        if phase_contract is None:
            return ContractValidationResult(
                passed=True,
                phase=phase,
                direction="enrichment",
            )

        return self._validate_fields(
            phase=phase,
            direction="enrichment",
            fields=phase_contract.entry.enrichment,
            context=context,
        )

    def _validate_fields(
        self,
        phase: str,
        direction: str,
        fields: list[FieldSpec],
        context: dict[str, Any],
    ) -> ContractValidationResult:
        """Core validation logic for a list of field specs."""
        field_results: list[FieldValidationResult] = []
        blocking_failures: list[str] = []
        warnings: list[str] = []

        for spec in fields:
            result = _validate_field(spec, context)
            field_results.append(result)

            if result.status == PropagationStatus.FAILED:
                blocking_failures.append(result.field)
            elif result.status == PropagationStatus.DEFAULTED:
                warnings.append(f"{result.field}: {result.message}")

        # Determine overall propagation status
        if blocking_failures:
            propagation_status = PropagationStatus.FAILED
        elif warnings:
            propagation_status = PropagationStatus.PARTIAL
        else:
            propagation_status = PropagationStatus.PROPAGATED

        passed = len(blocking_failures) == 0

        if not passed:
            logger.warning(
                "Boundary validation failed: phase=%s direction=%s blocking=%s",
                phase,
                direction,
                blocking_failures,
            )
        elif warnings:
            logger.info(
                "Boundary validation passed with warnings: phase=%s direction=%s warnings=%d",
                phase,
                direction,
                len(warnings),
            )

        return ContractValidationResult(
            passed=passed,
            phase=phase,
            direction=direction,
            field_results=field_results,
            blocking_failures=blocking_failures,
            warnings=warnings,
            propagation_status=propagation_status,
        )
