"""
Pre-flight verification for context propagation contracts — Layer 3.

Validates an initial context dict and phase execution order against a
``ContextContract`` **before** any workflow phase runs.  Catches issues
that would silently degrade quality at runtime.

Three checks:

1. **Field readiness** — every BLOCKING entry requirement across all
   phases has a non-default, non-empty value in the initial context
   *or* is produced by an earlier phase.
2. **Seed enrichment** — if the contract references enrichment fields
   with defaults, verifies the initial context carries real values
   (not placeholders).
3. **Phase graph** — walks the produces/requires graph to detect
   dangling reads (required but never produced) and dead writes
   (produced but never consumed).

Usage::

    from contextcore.contracts.preflight import PreflightChecker

    checker = PreflightChecker()
    result = checker.check(contract, initial_context, phase_order)
    if not result.passed:
        for v in result.critical_violations:
            logger.error("Pre-flight: %s", v.message)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.propagation.schema import ContextContract
from contextcore.contracts.types import ConstraintSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class PreflightViolation(BaseModel):
    """A single pre-flight violation."""

    model_config = ConfigDict(extra="forbid")

    check_type: str = Field(
        ..., description="field_readiness | seed_enrichment | phase_graph"
    )
    phase: str = Field(default="")
    field: Optional[str] = Field(None)
    severity: ConstraintSeverity = Field(ConstraintSeverity.WARNING)
    message: str = Field(default="")


class FieldReadinessDetail(BaseModel):
    """Detail for a single field readiness check."""

    model_config = ConfigDict(extra="forbid")

    field: str
    phase: str
    ready: bool
    has_value: bool
    is_default: bool
    severity: ConstraintSeverity
    message: str = ""


class PhaseGraphIssue(BaseModel):
    """A single phase graph issue (dangling read or dead write)."""

    model_config = ConfigDict(extra="forbid")

    issue_type: str = Field(..., description="dangling_read | dead_write")
    phase: str
    field: str
    message: str = ""


class PreflightResult(BaseModel):
    """Aggregated pre-flight verification result."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    violations: list[PreflightViolation] = Field(default_factory=list)
    field_readiness_details: list[FieldReadinessDetail] = Field(
        default_factory=list
    )
    phase_graph_issues: list[PhaseGraphIssue] = Field(default_factory=list)
    phases_checked: int = 0
    fields_checked: int = 0

    @property
    def critical_violations(self) -> list[PreflightViolation]:
        return [
            v for v in self.violations
            if v.severity == ConstraintSeverity.BLOCKING
        ]

    @property
    def warnings(self) -> list[PreflightViolation]:
        return [
            v for v in self.violations
            if v.severity == ConstraintSeverity.WARNING
        ]

    @property
    def advisories(self) -> list[PreflightViolation]:
        return [
            v for v in self.violations
            if v.severity == ConstraintSeverity.ADVISORY
        ]


# ---------------------------------------------------------------------------
# Field resolution (reused pattern)
# ---------------------------------------------------------------------------


def _resolve_field(context: dict[str, Any], field_path: str) -> tuple[bool, Any]:
    """Resolve a dot-path field from a context dict."""
    parts = field_path.split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


_DEFAULT_SENTINELS = {None, "", "unknown", "UNKNOWN"}
"""Values that indicate a field has its default/placeholder value."""


def _is_default_value(value: Any) -> bool:
    """Check whether a value looks like a default or placeholder."""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    try:
        if value in _DEFAULT_SENTINELS:
            return True
    except TypeError:
        # Unhashable type — not a default sentinel
        return False
    return False


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


class PreflightChecker:
    """Runs pre-flight verification against a context propagation contract."""

    def check(
        self,
        contract: ContextContract,
        initial_context: dict[str, Any],
        phase_order: Optional[list[str]] = None,
    ) -> PreflightResult:
        """Run all pre-flight checks.

        Args:
            contract: Loaded context propagation contract.
            initial_context: The context dict before any phase runs.
            phase_order: Ordered list of phase names that will execute.
                If ``None``, uses ``contract.phases.keys()`` order.

        Returns:
            Aggregated ``PreflightResult``.
        """
        if phase_order is None:
            phase_order = list(contract.phases.keys())

        violations: list[PreflightViolation] = []
        field_details: list[FieldReadinessDetail] = []
        graph_issues: list[PhaseGraphIssue] = []

        # Check 1: field readiness
        readiness_violations, readiness_details = self._check_field_readiness(
            contract, initial_context, phase_order
        )
        violations.extend(readiness_violations)
        field_details.extend(readiness_details)

        # Check 2: seed enrichment
        enrichment_violations, enrichment_details = self._check_seed_enrichment(
            contract, initial_context
        )
        violations.extend(enrichment_violations)
        field_details.extend(enrichment_details)

        # Check 3: phase graph
        graph_violations, issues = self._check_phase_graph(
            contract, initial_context, phase_order
        )
        violations.extend(graph_violations)
        graph_issues.extend(issues)

        passed = not any(
            v.severity == ConstraintSeverity.BLOCKING for v in violations
        )

        if not passed:
            logger.warning(
                "Pre-flight FAILED: %d critical, %d warning, %d advisory",
                sum(1 for v in violations if v.severity == ConstraintSeverity.BLOCKING),
                sum(1 for v in violations if v.severity == ConstraintSeverity.WARNING),
                sum(1 for v in violations if v.severity == ConstraintSeverity.ADVISORY),
            )
        elif violations:
            logger.info(
                "Pre-flight passed with %d warning(s)", len(violations)
            )

        return PreflightResult(
            passed=passed,
            violations=violations,
            field_readiness_details=field_details,
            phase_graph_issues=graph_issues,
            phases_checked=len(phase_order),
            fields_checked=len(field_details),
        )

    def check_field_readiness(
        self,
        contract: ContextContract,
        initial_context: dict[str, Any],
        phase_order: Optional[list[str]] = None,
    ) -> PreflightResult:
        """Run only the field readiness check."""
        if phase_order is None:
            phase_order = list(contract.phases.keys())
        violations, details = self._check_field_readiness(
            contract, initial_context, phase_order
        )
        passed = not any(
            v.severity == ConstraintSeverity.BLOCKING for v in violations
        )
        return PreflightResult(
            passed=passed,
            violations=violations,
            field_readiness_details=details,
            phases_checked=len(phase_order),
            fields_checked=len(details),
        )

    def check_phase_graph(
        self,
        contract: ContextContract,
        initial_context: dict[str, Any],
        phase_order: Optional[list[str]] = None,
    ) -> PreflightResult:
        """Run only the phase graph check."""
        if phase_order is None:
            phase_order = list(contract.phases.keys())
        violations, issues = self._check_phase_graph(
            contract, initial_context, phase_order
        )
        passed = not any(
            v.severity == ConstraintSeverity.BLOCKING for v in violations
        )
        return PreflightResult(
            passed=passed,
            violations=violations,
            phase_graph_issues=issues,
            phases_checked=len(phase_order),
        )

    # -- internal: field readiness -----------------------------------------

    def _check_field_readiness(
        self,
        contract: ContextContract,
        context: dict[str, Any],
        phase_order: list[str],
    ) -> tuple[list[PreflightViolation], list[FieldReadinessDetail]]:
        """Check that critical entry fields have non-default values.

        For each phase in order, check its entry.required fields.
        A field is "ready" if it's present in the initial context with
        a non-default value, OR if an earlier phase produces it.
        """
        violations: list[PreflightViolation] = []
        details: list[FieldReadinessDetail] = []

        # Build set of fields produced by phases seen so far
        produced_fields: set[str] = set()

        for phase_name in phase_order:
            phase_contract = contract.phases.get(phase_name)
            if phase_contract is None:
                continue

            for field_spec in phase_contract.entry.required:
                present, value = _resolve_field(context, field_spec.name)
                has_value = present and value is not None
                is_default = _is_default_value(value) if has_value else True

                # Field is ready if it has a real value in context
                # OR if an earlier phase produces it
                ready = (has_value and not is_default) or (
                    field_spec.name in produced_fields
                )

                detail = FieldReadinessDetail(
                    field=field_spec.name,
                    phase=phase_name,
                    ready=ready,
                    has_value=has_value,
                    is_default=is_default,
                    severity=field_spec.severity,
                )

                if not ready:
                    detail.message = (
                        f"Field '{field_spec.name}' required by phase "
                        f"'{phase_name}' is not ready"
                    )
                    if not has_value:
                        detail.message += " (missing from initial context)"
                    elif is_default:
                        detail.message += f" (has default value: {value!r})"

                    violations.append(
                        PreflightViolation(
                            check_type="field_readiness",
                            phase=phase_name,
                            field=field_spec.name,
                            severity=field_spec.severity,
                            message=detail.message,
                        )
                    )

                details.append(detail)

            # Record what this phase produces for subsequent phases
            for field_spec in phase_contract.exit.required:
                produced_fields.add(field_spec.name)
            for field_spec in phase_contract.exit.optional:
                produced_fields.add(field_spec.name)

        return violations, details

    # -- internal: seed enrichment -----------------------------------------

    def _check_seed_enrichment(
        self,
        contract: ContextContract,
        context: dict[str, Any],
    ) -> tuple[list[PreflightViolation], list[FieldReadinessDetail]]:
        """Check enrichment fields carry real values (not defaults)."""
        violations: list[PreflightViolation] = []
        details: list[FieldReadinessDetail] = []

        for phase_name, phase_contract in contract.phases.items():
            for field_spec in phase_contract.entry.enrichment:
                present, value = _resolve_field(context, field_spec.name)
                has_value = present and value is not None
                is_default = _is_default_value(value) if has_value else True

                ready = has_value and not is_default

                detail = FieldReadinessDetail(
                    field=field_spec.name,
                    phase=phase_name,
                    ready=ready,
                    has_value=has_value,
                    is_default=is_default,
                    severity=field_spec.severity,
                )

                if not ready and field_spec.severity != ConstraintSeverity.ADVISORY:
                    detail.message = (
                        f"Enrichment field '{field_spec.name}' for phase "
                        f"'{phase_name}' has default/missing value"
                    )
                    violations.append(
                        PreflightViolation(
                            check_type="seed_enrichment",
                            phase=phase_name,
                            field=field_spec.name,
                            severity=field_spec.severity,
                            message=detail.message,
                        )
                    )

                details.append(detail)

        return violations, details

    # -- internal: phase graph ---------------------------------------------

    def _check_phase_graph(
        self,
        contract: ContextContract,
        initial_context: dict[str, Any],
        phase_order: list[str],
    ) -> tuple[list[PreflightViolation], list[PhaseGraphIssue]]:
        """Check the produces/requires dependency graph for issues.

        Detects:
        - **Dangling reads**: a phase requires a field that no earlier
          phase produces and that isn't in the initial context.
        - **Dead writes**: a phase produces a field that no later phase
          requires.
        """
        violations: list[PreflightViolation] = []
        issues: list[PhaseGraphIssue] = []

        # Collect all produces and requires
        produces: dict[str, set[str]] = {}  # phase -> set of field names
        requires: dict[str, set[str]] = {}  # phase -> set of field names

        for phase_name in phase_order:
            phase_contract = contract.phases.get(phase_name)
            if phase_contract is None:
                continue

            requires[phase_name] = {
                f.name for f in phase_contract.entry.required
            }
            exit_fields = {f.name for f in phase_contract.exit.required}
            exit_fields |= {f.name for f in phase_contract.exit.optional}
            produces[phase_name] = exit_fields

        # Fields available in initial context
        initial_fields = set(_flatten_keys(initial_context))

        # Check dangling reads
        available_fields = set(initial_fields)
        for phase_name in phase_order:
            phase_requires = requires.get(phase_name, set())
            for field_name in sorted(phase_requires):
                if field_name not in available_fields:
                    issue = PhaseGraphIssue(
                        issue_type="dangling_read",
                        phase=phase_name,
                        field=field_name,
                        message=(
                            f"Phase '{phase_name}' requires '{field_name}' "
                            f"but no earlier phase produces it and it's not "
                            f"in the initial context"
                        ),
                    )
                    issues.append(issue)

                    # Look up severity from the field spec
                    severity = self._get_field_severity(
                        contract, phase_name, field_name
                    )
                    violations.append(
                        PreflightViolation(
                            check_type="phase_graph",
                            phase=phase_name,
                            field=field_name,
                            severity=severity,
                            message=issue.message,
                        )
                    )

            # Add this phase's produces to available
            available_fields |= produces.get(phase_name, set())

        # Check dead writes
        all_required: set[str] = set()
        for r in requires.values():
            all_required |= r

        for phase_name in phase_order:
            phase_produces = produces.get(phase_name, set())
            for field_name in sorted(phase_produces):
                if field_name not in all_required:
                    issue = PhaseGraphIssue(
                        issue_type="dead_write",
                        phase=phase_name,
                        field=field_name,
                        message=(
                            f"Phase '{phase_name}' produces '{field_name}' "
                            f"but no phase requires it"
                        ),
                    )
                    issues.append(issue)
                    # Dead writes are advisory — not blocking
                    violations.append(
                        PreflightViolation(
                            check_type="phase_graph",
                            phase=phase_name,
                            field=field_name,
                            severity=ConstraintSeverity.ADVISORY,
                            message=issue.message,
                        )
                    )

        return violations, issues

    @staticmethod
    def _get_field_severity(
        contract: ContextContract, phase_name: str, field_name: str
    ) -> ConstraintSeverity:
        """Look up the severity of a field spec in a phase's entry requirements."""
        phase_contract = contract.phases.get(phase_name)
        if phase_contract:
            for f in phase_contract.entry.required:
                if f.name == field_name:
                    return f.severity
        return ConstraintSeverity.WARNING


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flatten_keys(d: dict[str, Any], prefix: str = "") -> list[str]:
    """Flatten a nested dict to dot-path keys.

    Example: ``{"a": {"b": 1}, "c": 2}`` → ``["a.b", "a", "c"]``
    """
    keys: list[str] = []
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        keys.append(full_key)
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, full_key))
    return keys
