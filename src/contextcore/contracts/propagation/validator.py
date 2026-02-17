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
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.propagation.schema import (
    ContextContract,
    FieldSpec,
)
from contextcore.contracts.propagation.tracker import PROVENANCE_KEY, FieldProvenance
from contextcore.contracts.types import (
    ConstraintSeverity,
    EvaluationPolicy,
    PropagationStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class QualityViolation(BaseModel):
    """Detail of a quality threshold violation."""

    model_config = ConfigDict(extra="forbid")

    field: str
    metric: str
    actual: float
    threshold: float
    severity: ConstraintSeverity
    message: str = ""


class FieldValidationResult(BaseModel):
    """Result of validating a single field at a boundary."""

    model_config = ConfigDict(extra="forbid")

    field: str
    status: PropagationStatus
    severity: ConstraintSeverity
    message: str = ""
    default_applied: bool = False
    quality_violations: list[QualityViolation] = Field(default_factory=list)
    evaluation_satisfied: bool | None = None  # None = no eval spec


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
    quality_violations: list[QualityViolation] = Field(default_factory=list)

    def to_gate_result(self) -> dict[str, Any]:
        """Convert to a GateResult-compatible dict for emission via GateEmitter."""
        evidence = [
            {"type": "field_validation", "ref": fr.field, "description": fr.message}
            for fr in self.field_results
            if fr.status != PropagationStatus.PROPAGATED
        ]
        for qv in self.quality_violations:
            evidence.append({
                "type": "quality_violation",
                "ref": qv.field,
                "description": qv.message,
            })
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
            "evidence": evidence,
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


# ---------------------------------------------------------------------------
# Quality metric extractors
# ---------------------------------------------------------------------------

_QUALITY_EXTRACTORS: dict[str, Callable[[Any], float]] = {
    "line_count": lambda v: float(len(str(v).strip().splitlines())) if v else 0.0,
    "char_count": lambda v: float(len(str(v).strip())) if v else 0.0,
    "section_count": lambda v: float(
        sum(1 for line in str(v).splitlines() if line.strip().startswith("##"))
    ) if v else 0.0,
    "length": lambda v: float(len(v)) if isinstance(v, (list, dict, str)) else 0.0,
}


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

    # --- Field is present; run quality and evaluation checks ---
    quality_violations: list[QualityViolation] = []
    evaluation_satisfied: bool | None = None
    status = PropagationStatus.PROPAGATED
    message = ""

    # Quality check (REQ_CONCERN_9)
    if spec.quality is not None:
        extractor = _QUALITY_EXTRACTORS.get(spec.quality.metric)
        if extractor is not None:
            actual = extractor(value)
            if actual < spec.quality.threshold:
                violation = QualityViolation(
                    field=spec.name,
                    metric=spec.quality.metric,
                    actual=actual,
                    threshold=spec.quality.threshold,
                    severity=spec.quality.on_below,
                    message=(
                        f"Quality check failed: {spec.quality.metric}={actual} "
                        f"< threshold {spec.quality.threshold}"
                    ),
                )
                quality_violations.append(violation)
                if spec.quality.on_below == ConstraintSeverity.BLOCKING:
                    status = PropagationStatus.FAILED
                    message = violation.message
                elif spec.quality.on_below == ConstraintSeverity.WARNING:
                    if status != PropagationStatus.FAILED:
                        status = PropagationStatus.PARTIAL
                    message = violation.message
        else:
            logger.debug(
                "Unknown quality metric '%s' for field '%s', skipping",
                spec.quality.metric,
                spec.name,
            )

    # Evaluation gate check (REQ_CONCERN_13)
    if spec.evaluation is not None and spec.evaluation.required:
        provenance_store = context.get(PROVENANCE_KEY, {})
        prov = provenance_store.get(spec.name)

        has_stamp = prov is not None and isinstance(prov, FieldProvenance) and prov.evaluated_by is not None

        if not has_stamp:
            evaluation_satisfied = False
            sev = spec.evaluation.on_unevaluated
            eval_msg = f"Evaluation gate not satisfied: field '{spec.name}' has no evaluation stamp"
            if sev == ConstraintSeverity.BLOCKING:
                status = PropagationStatus.FAILED
                message = eval_msg
            elif sev == ConstraintSeverity.WARNING:
                if status != PropagationStatus.FAILED:
                    status = PropagationStatus.PARTIAL
                if not message:
                    message = eval_msg
        else:
            # Check policy-specific requirements
            evaluation_satisfied = True
            policy = spec.evaluation.policy

            if policy == EvaluationPolicy.HUMAN_REQUIRED:
                if not (prov.evaluated_by or "").startswith("human:"):
                    evaluation_satisfied = False
                    sev = spec.evaluation.on_unevaluated
                    eval_msg = (
                        f"Evaluation gate not satisfied: field '{spec.name}' "
                        f"requires human evaluation, got '{prov.evaluated_by}'"
                    )
                    if sev == ConstraintSeverity.BLOCKING:
                        status = PropagationStatus.FAILED
                        message = eval_msg
                    elif sev == ConstraintSeverity.WARNING:
                        if status != PropagationStatus.FAILED:
                            status = PropagationStatus.PARTIAL
                        if not message:
                            message = eval_msg

            if policy == EvaluationPolicy.SCORE_THRESHOLD and evaluation_satisfied:
                threshold = spec.evaluation.threshold
                if threshold is not None:
                    score = prov.evaluation_score
                    if score is None or score < threshold:
                        evaluation_satisfied = False
                        sev = spec.evaluation.on_below_threshold
                        eval_msg = (
                            f"Evaluation score {score} < threshold {threshold} "
                            f"for field '{spec.name}'"
                        )
                        if sev == ConstraintSeverity.BLOCKING:
                            status = PropagationStatus.FAILED
                            message = eval_msg
                        elif sev == ConstraintSeverity.WARNING:
                            if status != PropagationStatus.FAILED:
                                status = PropagationStatus.PARTIAL
                            if not message:
                                message = eval_msg
    elif spec.evaluation is not None and not spec.evaluation.required:
        evaluation_satisfied = None  # not required, skip

    return FieldValidationResult(
        field=spec.name,
        status=status,
        severity=spec.severity,
        message=message,
        quality_violations=quality_violations,
        evaluation_satisfied=evaluation_satisfied,
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
        all_quality_violations: list[QualityViolation] = []

        for spec in fields:
            result = _validate_field(spec, context)
            field_results.append(result)

            if result.status == PropagationStatus.FAILED:
                blocking_failures.append(result.field)
            elif result.status in (PropagationStatus.DEFAULTED, PropagationStatus.PARTIAL):
                warnings.append(f"{result.field}: {result.message}")

            all_quality_violations.extend(result.quality_violations)

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
            quality_violations=all_quality_violations,
        )
