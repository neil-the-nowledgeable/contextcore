"""
Pydantic v2 models for schema compatibility contract YAML format.

Contracts declare cross-service field mappings, value translations, and
schema evolution rules.  Used by ``CompatibilityChecker`` and
``EvolutionTracker`` to detect drift between services.

All models use ``extra="forbid"`` to reject unknown keys at parse time,
following the same pattern as ``propagation/schema.py``.

Usage::

    from contextcore.contracts.schema_compat.schema import SchemaCompatibilitySpec
    import yaml

    with open("cross-service.compat.yaml") as fh:
        raw = yaml.safe_load(fh)
    spec = SchemaCompatibilitySpec.model_validate(raw)
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contextcore.contracts.types import CompatibilityLevel, ConstraintSeverity


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


class FieldMapping(BaseModel):
    """Declares how a field maps between two services."""

    model_config = ConfigDict(extra="forbid")

    source_service: str = Field(..., min_length=1)
    source_field: str = Field(..., min_length=1, description="Dot-path field name in source")
    source_type: str = Field("str", description="Expected Python type name")
    source_values: Optional[list[str]] = Field(
        None, description="Allowed values in source service"
    )
    target_service: str = Field(..., min_length=1)
    target_field: str = Field(..., min_length=1, description="Dot-path field name in target")
    target_type: str = Field("str", description="Expected Python type name")
    target_values: Optional[list[str]] = Field(
        None, description="Allowed values in target service"
    )
    mapping: Optional[dict[str, str]] = Field(
        None, description="Value translation map (source_value -> target_value)"
    )
    severity: ConstraintSeverity = Field(
        ConstraintSeverity.WARNING,
        description="Severity when drift is detected",
    )
    description: Optional[str] = Field(None)
    bidirectional: bool = Field(
        False, description="Whether the mapping is invertible"
    )

    @model_validator(mode="after")
    def _check_bidirectional_injective(self) -> "FieldMapping":
        """If bidirectional, the mapping must be injective (no duplicate values)."""
        if self.bidirectional and self.mapping:
            values = list(self.mapping.values())
            if len(values) != len(set(values)):
                raise ValueError(
                    "Bidirectional mapping must be injective (no duplicate values)"
                )
        return self


# ---------------------------------------------------------------------------
# Evolution rules and versions
# ---------------------------------------------------------------------------


class SchemaEvolutionRule(BaseModel):
    """Policy governing allowed schema changes for a service scope."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., min_length=1)
    scope: str = Field(..., min_length=1, description="Service name or prefix to match")
    policy: Literal["additive_only", "backward_compatible", "full"] = Field(
        ..., description="Evolution policy"
    )
    allowed_changes: list[str] = Field(
        default_factory=list,
        description="Change types explicitly allowed beyond policy defaults",
    )
    forbidden_changes: list[str] = Field(
        default_factory=list,
        description="Change types explicitly forbidden regardless of policy",
    )
    description: Optional[str] = Field(None)


class SchemaVersion(BaseModel):
    """Snapshot of a service's schema at a point in time."""

    model_config = ConfigDict(extra="forbid")

    service: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    fields: dict[str, str] = Field(
        ..., description="Field name -> type name mapping"
    )
    enums: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Enum field name -> allowed values",
    )
    required_fields: list[str] = Field(default_factory=list)
    deprecated_fields: list[str] = Field(default_factory=list)
    timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp")


# ---------------------------------------------------------------------------
# Top-level contract
# ---------------------------------------------------------------------------


class SchemaCompatibilitySpec(BaseModel):
    """
    Root model for a schema compatibility contract YAML file.

    Declares cross-service field mappings, evolution rules, and version
    snapshots for schema drift detection.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        ..., min_length=1, description="Contract schema version (e.g. 0.1.0)"
    )
    contract_type: Literal["schema_compatibility"] = Field(
        "schema_compatibility",
        description="Contract type discriminator",
    )
    description: Optional[str] = Field(None)
    mappings: list[FieldMapping] = Field(default_factory=list)
    evolution_rules: list[SchemaEvolutionRule] = Field(default_factory=list)
    versions: list[SchemaVersion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class FieldCompatibilityDetail(BaseModel):
    """Result of checking a single field mapping."""

    model_config = ConfigDict(extra="forbid")

    source_field: str
    target_field: str
    compatible: bool
    drift_type: Optional[str] = Field(
        None, description="Type of drift detected (type_mismatch, unmapped_value, etc.)"
    )
    detail: str = ""


class CompatibilityResult(BaseModel):
    """Aggregated result of a compatibility check between two services."""

    model_config = ConfigDict(extra="forbid")

    compatible: bool
    level: CompatibilityLevel
    source_service: str
    target_service: str
    field_results: list[FieldCompatibilityDetail] = Field(default_factory=list)
    drift_details: list[str] = Field(default_factory=list)
    severity: ConstraintSeverity = Field(ConstraintSeverity.WARNING)
    message: str = ""


class EvolutionCheckResult(BaseModel):
    """Result of checking schema evolution between two versions."""

    model_config = ConfigDict(extra="forbid")

    compatible: bool
    service: str
    old_version: str
    new_version: str
    total_changes: int = 0
    breaking_changes: list[dict[str, Any]] = Field(default_factory=list)
    compatible_changes: list[dict[str, Any]] = Field(default_factory=list)
    applicable_rule: Optional[str] = Field(None)
    message: str = ""
