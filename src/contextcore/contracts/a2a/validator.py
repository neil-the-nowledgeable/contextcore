"""
JSON Schema validation helpers for A2A contracts.

Validates raw payloads (dicts) against the canonical JSON schemas in
``schemas/contracts/`` and returns a structured error envelope per the
Day 2 spec: ``error_code``, ``schema_id``, ``failed_path``, ``message``,
``next_action``.

Also supports Pydantic model-level validation as a convenience.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from contextcore.contracts.a2a.models import SCHEMA_FILES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema resolution
# ---------------------------------------------------------------------------

_SCHEMA_DIR: Path | None = None


def _find_schema_dir() -> Path:
    """Locate ``schemas/contracts/`` relative to the package or repo root."""
    global _SCHEMA_DIR
    if _SCHEMA_DIR is not None:
        return _SCHEMA_DIR

    # Walk up from this file to find the repo root containing schemas/
    candidate = Path(__file__).resolve()
    for _ in range(10):
        candidate = candidate.parent
        schemas_path = candidate / "schemas" / "contracts"
        if schemas_path.is_dir():
            _SCHEMA_DIR = schemas_path
            return _SCHEMA_DIR

    raise FileNotFoundError(
        "Cannot locate schemas/contracts/ directory. "
        "Ensure the package is installed from the repo root."
    )


def _load_schema(contract_name: str) -> dict[str, Any]:
    """Load and return the JSON schema for *contract_name*."""
    schema_file = SCHEMA_FILES.get(contract_name)
    if schema_file is None:
        raise ValueError(
            f"Unknown contract name '{contract_name}'. "
            f"Valid names: {sorted(SCHEMA_FILES.keys())}"
        )

    path = _find_schema_dir() / schema_file
    if not path.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")

    with open(path) as fh:
        return json.load(fh)


# Cache compiled validators per contract name
_VALIDATORS: dict[str, Draft202012Validator] = {}


def _get_validator(contract_name: str) -> Draft202012Validator:
    """Return a cached ``Draft202012Validator`` for *contract_name*."""
    if contract_name not in _VALIDATORS:
        schema = _load_schema(contract_name)
        Draft202012Validator.check_schema(schema)
        _VALIDATORS[contract_name] = Draft202012Validator(schema)
    return _VALIDATORS[contract_name]


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


@dataclass
class ValidationErrorEnvelope:
    """
    Standard validation error envelope (Day 2 spec).

    Attributes:
        error_code: Machine-readable error code (e.g. ``SCHEMA_VALIDATION_FAILED``).
        schema_id: ``$id`` of the JSON schema that was violated.
        failed_path: JSON pointer to the offending field (e.g. ``/status``).
        message: Human-readable description of the failure.
        next_action: Recommended corrective action.
    """

    error_code: str
    schema_id: str
    failed_path: str
    message: str
    next_action: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict for logging / telemetry."""
        return {
            "error_code": self.error_code,
            "schema_id": self.schema_id,
            "failed_path": self.failed_path,
            "message": self.message,
            "next_action": self.next_action,
        }


@dataclass
class ValidationReport:
    """
    Aggregated result of validating one payload.

    Attributes:
        contract_name: Which contract was checked.
        is_valid: ``True`` when the payload passes schema validation.
        errors: List of structured error envelopes (empty when valid).
    """

    contract_name: str
    is_valid: bool
    errors: list[ValidationErrorEnvelope] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Error-code classification helpers
# ---------------------------------------------------------------------------


def _error_code_for(error: jsonschema.ValidationError) -> str:
    """Derive a machine-readable error code from a ``jsonschema`` error."""
    validator = error.validator
    if validator == "required":
        return "MISSING_REQUIRED_FIELD"
    if validator == "additionalProperties":
        return "UNKNOWN_FIELD"
    if validator == "enum":
        return "ENUM_MISMATCH"
    if validator == "const":
        return "CONST_VIOLATION"
    if validator == "type":
        return "WRONG_TYPE"
    if validator == "pattern":
        return "PATTERN_MISMATCH"
    if validator == "minLength":
        return "MIN_LENGTH_VIOLATION"
    if validator in ("minimum", "maximum"):
        return "VALUE_OUT_OF_RANGE"
    if validator == "format":
        return "INVALID_FORMAT"
    if validator == "minProperties":
        return "EMPTY_OBJECT"
    return "SCHEMA_ERROR"


def _json_pointer(path: list[str | int]) -> str:
    """Convert a jsonschema path deque to a JSON pointer string."""
    if not path:
        return "/"
    return "/" + "/".join(str(p) for p in path)


def _next_action_for(error_code: str, field_path: str) -> str:
    """Suggest a corrective action based on error code."""
    actions = {
        "MISSING_REQUIRED_FIELD": f"Add the missing required field at '{field_path}'.",
        "UNKNOWN_FIELD": (
            f"Remove the unknown field at '{field_path}'. "
            "v1 contracts do not allow extra top-level fields."
        ),
        "ENUM_MISMATCH": f"Use one of the allowed enum values for '{field_path}'.",
        "CONST_VIOLATION": f"Set '{field_path}' to the required constant value.",
        "WRONG_TYPE": f"Correct the type of '{field_path}'.",
        "PATTERN_MISMATCH": f"Correct the value at '{field_path}' to match the required pattern.",
        "MIN_LENGTH_VIOLATION": f"Provide a non-empty value for '{field_path}'.",
        "VALUE_OUT_OF_RANGE": f"Adjust the value at '{field_path}' to be within the allowed range.",
        "INVALID_FORMAT": f"Correct the format of '{field_path}' (e.g. date-time).",
        "EMPTY_OBJECT": f"Provide at least one property inside '{field_path}'.",
    }
    return actions.get(error_code, f"Fix the validation error at '{field_path}'.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class A2AValidator:
    """
    Validates raw dicts against A2A contract JSON schemas.

    Usage::

        validator = A2AValidator()
        report = validator.validate("TaskSpanContract", payload)
        if not report.is_valid:
            for err in report.errors:
                print(err.message)
    """

    def validate(self, contract_name: str, payload: dict[str, Any]) -> ValidationReport:
        """
        Validate *payload* against the named contract schema.

        Args:
            contract_name: One of ``TaskSpanContract``, ``HandoffContract``,
                ``ArtifactIntent``, ``GateResult``.
            payload: Raw dict to validate.

        Returns:
            A :class:`ValidationReport` containing structured errors (if any).
        """
        schema_validator = _get_validator(contract_name)
        schema = _load_schema(contract_name)
        schema_id = schema.get("$id", contract_name)

        envelopes: list[ValidationErrorEnvelope] = []
        for error in schema_validator.iter_errors(payload):
            code = _error_code_for(error)
            path = _json_pointer(list(error.absolute_path))
            envelope = ValidationErrorEnvelope(
                error_code=code,
                schema_id=schema_id,
                failed_path=path,
                message=error.message,
                next_action=_next_action_for(code, path),
            )
            envelopes.append(envelope)

        is_valid = len(envelopes) == 0
        if not is_valid:
            logger.debug(
                "Validation failed for %s: %d error(s)",
                contract_name,
                len(envelopes),
            )

        return ValidationReport(
            contract_name=contract_name,
            is_valid=is_valid,
            errors=envelopes,
        )


def validate_payload(contract_name: str, payload: dict[str, Any]) -> ValidationReport:
    """
    Module-level convenience function.

    Equivalent to ``A2AValidator().validate(contract_name, payload)``.
    """
    return A2AValidator().validate(contract_name, payload)
