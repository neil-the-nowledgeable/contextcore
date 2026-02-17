"""
Semantic convention validator for attribute naming enforcement.

Validates that a dict of attributes conforms to the canonical naming
conventions declared in a ``ConventionContract``.  Detects non-canonical
names (aliases), unknown attributes, invalid enum values, and missing
required attributes.

Severity behavior:
    - REQUIRED attributes missing     -> ``BLOCKING``
    - Alias used instead of canonical  -> ``WARNING``
    - Unknown attribute name           -> ``ADVISORY``
    - Invalid enum value               -> ``WARNING``

Usage::

    from contextcore.contracts.semconv.validator import ConventionValidator

    validator = ConventionValidator(contract)
    result = validator.validate_attributes({"service.name": "foo", "svc_name": "bar"})
    if not result.passed:
        for r in result.results:
            if r.status != "valid":
                logger.warning("Convention: %s", r.message)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.semconv.schema import ConventionContract
from contextcore.contracts.types import ConstraintSeverity, RequirementLevel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class AttributeValidationResult(BaseModel):
    """Result of validating a single attribute against conventions."""

    model_config = ConfigDict(extra="forbid")

    attribute: str = Field(
        ..., description="The attribute name as provided"
    )
    canonical_name: Optional[str] = Field(
        None, description="Resolved canonical name (None if unknown)"
    )
    status: str = Field(
        ..., description="valid | alias_resolved | unknown | invalid_value"
    )
    severity: ConstraintSeverity = Field(
        ConstraintSeverity.ADVISORY,
        description="Severity of this finding",
    )
    message: str = Field(
        "", description="Human-readable description of the finding"
    )


class ConventionValidationResult(BaseModel):
    """Aggregated result of validating attributes against conventions."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(
        ..., description="True if no blocking violations found"
    )
    total_checked: int = Field(
        0, description="Total number of attributes checked"
    )
    results: list[AttributeValidationResult] = Field(
        default_factory=list,
        description="Per-attribute validation results",
    )
    violations: int = Field(
        0, description="Count of blocking violations"
    )
    aliases_resolved: int = Field(
        0, description="Count of aliases that were resolved to canonical names"
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class ConventionValidator:
    """Validates attribute dicts against a semantic convention contract.

    Builds internal lookup dicts from the contract on init for O(1)
    attribute resolution and value validation.

    Args:
        contract: Loaded ``ConventionContract`` to validate against.
    """

    def __init__(self, contract: ConventionContract) -> None:
        self._contract = contract

        # canonical_name -> AttributeConvention
        self._canonical: dict[str, Any] = {}
        # alias -> canonical_name
        self._alias_to_canonical: dict[str, str] = {}
        # canonical_name -> set of allowed values (None = any)
        self._allowed_values: dict[str, set[str] | None] = {}
        # canonical_name -> RequirementLevel
        self._requirement_levels: dict[str, RequirementLevel] = {}

        # enum name -> set of allowed values
        self._enum_values: dict[str, set[str]] = {}
        # enum name -> extensible flag
        self._enum_extensible: dict[str, bool] = {}

        self._build_lookups()

    def _build_lookups(self) -> None:
        """Build lookup dicts from the contract."""
        for attr in self._contract.attributes:
            self._canonical[attr.name] = attr
            self._requirement_levels[attr.name] = attr.requirement_level
            self._allowed_values[attr.name] = (
                set(attr.allowed_values) if attr.allowed_values is not None else None
            )
            for alias in attr.aliases:
                self._alias_to_canonical[alias] = attr.name

        for enum in self._contract.enums:
            self._enum_values[enum.name] = set(enum.values)
            self._enum_extensible[enum.name] = enum.extensible

    def resolve_alias(self, name: str) -> Optional[str]:
        """Resolve an attribute name to its canonical form.

        Args:
            name: Attribute name (possibly an alias).

        Returns:
            Canonical name if found (including if ``name`` is already
            canonical), or ``None`` if unknown.
        """
        if name in self._canonical:
            return name
        return self._alias_to_canonical.get(name)

    def validate_value(self, attr_name: str, value: Any) -> bool:
        """Check whether a value is valid for a given canonical attribute.

        Args:
            attr_name: Canonical attribute name.
            value: Value to validate.

        Returns:
            ``True`` if valid or if no allowed_values constraint exists.
            ``False`` if the value is not in the allowed set.
        """
        # Resolve alias first
        canonical = self.resolve_alias(attr_name)
        if canonical is None:
            # Unknown attribute — cannot validate value
            return True

        allowed = self._allowed_values.get(canonical)
        if allowed is None:
            return True

        return str(value) in allowed

    def validate_attributes(
        self, attributes: dict[str, Any]
    ) -> ConventionValidationResult:
        """Validate a dict of attributes against the convention contract.

        Checks each provided attribute for:
        1. Whether the name is canonical, an alias, or unknown.
        2. Whether the value is in the allowed set (if one is declared).

        Also checks that all REQUIRED attributes are present.

        Args:
            attributes: Dict of attribute name -> value pairs.

        Returns:
            ``ConventionValidationResult`` with per-attribute detail.
        """
        results: list[AttributeValidationResult] = []
        violations = 0
        aliases_resolved = 0

        # Track which canonical attributes have been seen (for requirement check)
        seen_canonical: set[str] = set()

        for attr_name, value in attributes.items():
            result = self._validate_single(attr_name, value)
            results.append(result)

            if result.canonical_name is not None:
                seen_canonical.add(result.canonical_name)

            if result.status == "alias_resolved":
                aliases_resolved += 1

            if result.severity == ConstraintSeverity.BLOCKING:
                violations += 1

        # Check for missing REQUIRED attributes
        for canonical_name, level in self._requirement_levels.items():
            if level == RequirementLevel.REQUIRED and canonical_name not in seen_canonical:
                results.append(
                    AttributeValidationResult(
                        attribute=canonical_name,
                        canonical_name=canonical_name,
                        status="invalid_value",
                        severity=ConstraintSeverity.BLOCKING,
                        message=(
                            f"Required attribute '{canonical_name}' is missing"
                        ),
                    )
                )
                violations += 1

        passed = violations == 0

        if not passed:
            logger.warning(
                "Convention validation FAILED: %d violation(s) in %d attributes",
                violations,
                len(attributes),
            )
        elif aliases_resolved > 0:
            logger.info(
                "Convention validation passed with %d alias(es) resolved",
                aliases_resolved,
            )

        return ConventionValidationResult(
            passed=passed,
            total_checked=len(attributes),
            results=results,
            violations=violations,
            aliases_resolved=aliases_resolved,
        )

    def _validate_single(
        self, attr_name: str, value: Any
    ) -> AttributeValidationResult:
        """Validate a single attribute name + value pair."""
        # Case 1: Canonical name
        if attr_name in self._canonical:
            # Check value
            if not self.validate_value(attr_name, value):
                allowed = self._allowed_values.get(attr_name, set())
                return AttributeValidationResult(
                    attribute=attr_name,
                    canonical_name=attr_name,
                    status="invalid_value",
                    severity=ConstraintSeverity.WARNING,
                    message=(
                        f"Attribute '{attr_name}' has invalid value "
                        f"'{value}'; allowed: {sorted(allowed) if allowed else '(any)'}"
                    ),
                )
            return AttributeValidationResult(
                attribute=attr_name,
                canonical_name=attr_name,
                status="valid",
                severity=ConstraintSeverity.ADVISORY,
                message="",
            )

        # Case 2: Known alias
        canonical = self._alias_to_canonical.get(attr_name)
        if canonical is not None:
            # Check value against canonical allowed set
            if not self.validate_value(canonical, value):
                allowed = self._allowed_values.get(canonical, set())
                return AttributeValidationResult(
                    attribute=attr_name,
                    canonical_name=canonical,
                    status="invalid_value",
                    severity=ConstraintSeverity.WARNING,
                    message=(
                        f"Alias '{attr_name}' -> '{canonical}' has invalid "
                        f"value '{value}'; allowed: {sorted(allowed) if allowed else '(any)'}"
                    ),
                )
            return AttributeValidationResult(
                attribute=attr_name,
                canonical_name=canonical,
                status="alias_resolved",
                severity=ConstraintSeverity.WARNING,
                message=(
                    f"Non-canonical name '{attr_name}' resolved to "
                    f"canonical '{canonical}'"
                ),
            )

        # Case 3: Unknown attribute
        return AttributeValidationResult(
            attribute=attr_name,
            canonical_name=None,
            status="unknown",
            severity=ConstraintSeverity.ADVISORY,
            message=f"Unknown attribute '{attr_name}' not in convention",
        )
