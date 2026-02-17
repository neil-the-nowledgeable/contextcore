"""
Pydantic v2 models for semantic convention contract YAML format.

Contracts declare canonical attribute names, aliases, allowed values, and
enum conventions for a given namespace.  Used by ``ConventionValidator``
to detect non-canonical names, unknown values, and conflicting aliases.

All models use ``extra="forbid"`` to reject unknown keys at parse time,
following the same pattern as ``propagation/schema.py``.

Usage::

    from contextcore.contracts.semconv.schema import ConventionContract
    import yaml

    with open("otel-semconv.contract.yaml") as fh:
        raw = yaml.safe_load(fh)
    contract = ConventionContract.model_validate(raw)
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.types import RequirementLevel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Attribute conventions
# ---------------------------------------------------------------------------


class AttributeConvention(BaseModel):
    """Declares a single canonical attribute and its conventions."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ..., min_length=1, description="Canonical attribute name"
    )
    type: str = Field(
        "str", description="Expected value type (str, int, float, bool, etc.)"
    )
    requirement_level: RequirementLevel = Field(
        RequirementLevel.RECOMMENDED,
        description="Whether this attribute is required, recommended, or opt-in",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Non-canonical names that should resolve to this attribute",
    )
    allowed_values: Optional[list[str]] = Field(
        None, description="Closed set of allowed values (None = any value)"
    )
    description: str = Field(
        "", description="Human-readable description of this attribute"
    )


# ---------------------------------------------------------------------------
# Enum conventions
# ---------------------------------------------------------------------------


class EnumConvention(BaseModel):
    """Declares a named enum with a fixed or extensible value set."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ..., min_length=1, description="Enum name"
    )
    values: list[str] = Field(
        ..., description="Allowed enum values"
    )
    extensible: bool = Field(
        False, description="Whether values beyond the declared set are allowed"
    )


# ---------------------------------------------------------------------------
# Top-level contract
# ---------------------------------------------------------------------------


class ConventionContract(BaseModel):
    """
    Root model for a semantic convention contract YAML file.

    Declares canonical attribute names, aliases, allowed values, and
    enum conventions for a namespace.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        ..., min_length=1, description="Contract schema version (e.g. 0.1.0)"
    )
    contract_type: Literal["semantic_conventions"] = Field(
        "semantic_conventions",
        description="Contract type discriminator",
    )
    namespace: str = Field(
        ..., min_length=1, description="Convention namespace (e.g. 'otel.resource')"
    )
    attributes: list[AttributeConvention] = Field(
        default_factory=list,
        description="Canonical attribute conventions",
    )
    enums: list[EnumConvention] = Field(
        default_factory=list,
        description="Enum conventions",
    )
    description: str = Field(
        "", description="Human-readable description of this convention contract"
    )
