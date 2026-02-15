"""
Compatibility checker for cross-service schema contracts.

Validates that a payload from one service is compatible with the field
mappings declared for another service.  Read-only — does NOT transform
payloads.

Severity handling:
    - ``BLOCKING`` drift → ``compatible=False``
    - ``WARNING`` / ``ADVISORY`` → ``compatible=True`` with drift_details

Usage::

    from contextcore.contracts.schema_compat.checker import CompatibilityChecker

    checker = CompatibilityChecker(spec)
    result = checker.check("tracker", "exporter", payload)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from contextcore.contracts.schema_compat.schema import (
    CompatibilityResult,
    FieldCompatibilityDetail,
    FieldMapping,
    SchemaCompatibilitySpec,
)
from contextcore.contracts.types import CompatibilityLevel, ConstraintSeverity

logger = logging.getLogger(__name__)

# Python type name -> built-in type mapping for basic checking
_TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


class CompatibilityChecker:
    """Checks payload compatibility against declared field mappings."""

    def __init__(self, contract: SchemaCompatibilitySpec) -> None:
        self._contract = contract

    def check(
        self,
        source_service: str,
        target_service: str,
        payload: dict[str, Any],
        level: str = "semantic",
    ) -> CompatibilityResult:
        """Run a compatibility check at the given level.

        Args:
            source_service: Service producing the payload.
            target_service: Service consuming the payload.
            payload: The data dict to validate.
            level: Check depth — ``"structural"`` or ``"semantic"``.

        Returns:
            Aggregated ``CompatibilityResult``.
        """
        compat_level = CompatibilityLevel(level)
        if compat_level == CompatibilityLevel.STRUCTURAL:
            return self.check_structural(source_service, target_service, payload)
        return self.check_semantic(source_service, target_service, payload)

    def check_structural(
        self,
        source_service: str,
        target_service: str,
        payload: dict[str, Any],
    ) -> CompatibilityResult:
        """Check structural compatibility (field existence and type)."""
        mappings = self._find_mappings(source_service, target_service)
        field_results: list[FieldCompatibilityDetail] = []
        drift_details: list[str] = []
        has_blocking_drift = False
        max_severity = ConstraintSeverity.ADVISORY

        for mapping in mappings:
            present, value = _resolve_field_value(payload, mapping.source_field)

            if not present:
                detail = FieldCompatibilityDetail(
                    source_field=mapping.source_field,
                    target_field=mapping.target_field,
                    compatible=False,
                    drift_type="missing_field",
                    detail=f"Field '{mapping.source_field}' not found in payload",
                )
                field_results.append(detail)
                drift_details.append(detail.detail)
                if mapping.severity == ConstraintSeverity.BLOCKING:
                    has_blocking_drift = True
                max_severity = _max_severity(max_severity, mapping.severity)
                continue

            if not _check_type_compat(value, mapping.source_type):
                detail = FieldCompatibilityDetail(
                    source_field=mapping.source_field,
                    target_field=mapping.target_field,
                    compatible=False,
                    drift_type="type_mismatch",
                    detail=(
                        f"Field '{mapping.source_field}' expected type "
                        f"'{mapping.source_type}', got '{type(value).__name__}'"
                    ),
                )
                field_results.append(detail)
                drift_details.append(detail.detail)
                if mapping.severity == ConstraintSeverity.BLOCKING:
                    has_blocking_drift = True
                max_severity = _max_severity(max_severity, mapping.severity)
                continue

            field_results.append(
                FieldCompatibilityDetail(
                    source_field=mapping.source_field,
                    target_field=mapping.target_field,
                    compatible=True,
                )
            )

        compatible = not has_blocking_drift
        return CompatibilityResult(
            compatible=compatible,
            level=CompatibilityLevel.STRUCTURAL,
            source_service=source_service,
            target_service=target_service,
            field_results=field_results,
            drift_details=drift_details,
            severity=max_severity if drift_details else ConstraintSeverity.WARNING,
            message=self._build_message(compatible, drift_details),
        )

    def check_semantic(
        self,
        source_service: str,
        target_service: str,
        payload: dict[str, Any],
    ) -> CompatibilityResult:
        """Check semantic compatibility (values, translations, allowed sets)."""
        mappings = self._find_mappings(source_service, target_service)
        field_results: list[FieldCompatibilityDetail] = []
        drift_details: list[str] = []
        has_blocking_drift = False
        max_severity = ConstraintSeverity.ADVISORY

        for mapping in mappings:
            present, value = _resolve_field_value(payload, mapping.source_field)

            if not present:
                detail = FieldCompatibilityDetail(
                    source_field=mapping.source_field,
                    target_field=mapping.target_field,
                    compatible=False,
                    drift_type="missing_field",
                    detail=f"Field '{mapping.source_field}' not found in payload",
                )
                field_results.append(detail)
                drift_details.append(detail.detail)
                if mapping.severity == ConstraintSeverity.BLOCKING:
                    has_blocking_drift = True
                max_severity = _max_severity(max_severity, mapping.severity)
                continue

            if not _check_type_compat(value, mapping.source_type):
                detail = FieldCompatibilityDetail(
                    source_field=mapping.source_field,
                    target_field=mapping.target_field,
                    compatible=False,
                    drift_type="type_mismatch",
                    detail=(
                        f"Field '{mapping.source_field}' expected type "
                        f"'{mapping.source_type}', got '{type(value).__name__}'"
                    ),
                )
                field_results.append(detail)
                drift_details.append(detail.detail)
                if mapping.severity == ConstraintSeverity.BLOCKING:
                    has_blocking_drift = True
                max_severity = _max_severity(max_severity, mapping.severity)
                continue

            # Semantic: check value is in allowed set or has translation
            str_value = str(value)

            if mapping.source_values and str_value not in mapping.source_values:
                detail = FieldCompatibilityDetail(
                    source_field=mapping.source_field,
                    target_field=mapping.target_field,
                    compatible=False,
                    drift_type="value_outside_set",
                    detail=(
                        f"Value '{str_value}' for '{mapping.source_field}' "
                        f"not in allowed set {mapping.source_values}"
                    ),
                )
                field_results.append(detail)
                drift_details.append(detail.detail)
                if mapping.severity == ConstraintSeverity.BLOCKING:
                    has_blocking_drift = True
                max_severity = _max_severity(max_severity, mapping.severity)
                continue

            if mapping.mapping is not None:
                translatable, _ = _translate_value(mapping, str_value)
                if not translatable:
                    detail = FieldCompatibilityDetail(
                        source_field=mapping.source_field,
                        target_field=mapping.target_field,
                        compatible=False,
                        drift_type="unmapped_value",
                        detail=(
                            f"Value '{str_value}' for '{mapping.source_field}' "
                            f"has no translation in mapping"
                        ),
                    )
                    field_results.append(detail)
                    drift_details.append(detail.detail)
                    if mapping.severity == ConstraintSeverity.BLOCKING:
                        has_blocking_drift = True
                    max_severity = _max_severity(max_severity, mapping.severity)
                    continue

            field_results.append(
                FieldCompatibilityDetail(
                    source_field=mapping.source_field,
                    target_field=mapping.target_field,
                    compatible=True,
                )
            )

        compatible = not has_blocking_drift
        return CompatibilityResult(
            compatible=compatible,
            level=CompatibilityLevel.SEMANTIC,
            source_service=source_service,
            target_service=target_service,
            field_results=field_results,
            drift_details=drift_details,
            severity=max_severity if drift_details else ConstraintSeverity.WARNING,
            message=self._build_message(compatible, drift_details),
        )

    def find_mapping(
        self,
        source_service: str,
        target_service: str,
        source_field: str,
    ) -> Optional[FieldMapping]:
        """Find a specific field mapping between two services."""
        for m in self._contract.mappings:
            if (
                m.source_service == source_service
                and m.target_service == target_service
                and m.source_field == source_field
            ):
                return m
        return None

    # -- internal helpers --------------------------------------------------

    def _find_mappings(
        self, source_service: str, target_service: str
    ) -> list[FieldMapping]:
        """Return all mappings from source to target service."""
        return [
            m
            for m in self._contract.mappings
            if m.source_service == source_service
            and m.target_service == target_service
        ]

    @staticmethod
    def _build_message(compatible: bool, drift_details: list[str]) -> str:
        if compatible and not drift_details:
            return "All fields compatible"
        elif compatible:
            return f"Compatible with {len(drift_details)} warning(s)"
        else:
            return f"Incompatible: {len(drift_details)} drift(s) detected"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _resolve_field_value(
    payload: dict[str, Any], field_path: str
) -> tuple[bool, Any]:
    """Resolve a dot-path field from a payload dict.

    Returns (present, value).
    """
    parts = field_path.split(".")
    current: Any = payload
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def _check_type_compat(value: Any, expected_type: str) -> bool:
    """Check whether *value* matches the expected type name."""
    py_type = _TYPE_MAP.get(expected_type)
    if py_type is None:
        # Unknown type — pass through
        return True
    return isinstance(value, py_type)


def _translate_value(
    mapping: FieldMapping, source_value: str
) -> tuple[bool, Any]:
    """Translate a source value using the mapping dict.

    Returns (translatable, translated_value).
    """
    if mapping.mapping is None:
        return False, None
    if source_value in mapping.mapping:
        return True, mapping.mapping[source_value]
    return False, None


def _max_severity(
    current: ConstraintSeverity, candidate: ConstraintSeverity
) -> ConstraintSeverity:
    """Return the more severe of two severities."""
    order = {
        ConstraintSeverity.ADVISORY: 0,
        ConstraintSeverity.WARNING: 1,
        ConstraintSeverity.BLOCKING: 2,
    }
    if order[candidate] > order[current]:
        return candidate
    return current
