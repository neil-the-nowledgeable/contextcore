"""
Pydantic v2 models for data lineage contract YAML format.

Contracts declare transformation chains — the sequence of operations each
field undergoes as it flows through pipeline phases.  Used by
``ProvenanceAuditor`` to verify that recorded transformations match the
declared spec.

All models use ``extra="forbid"`` to reject unknown keys at parse time,
following the same pattern as ``propagation/schema.py``.

Usage::

    from contextcore.contracts.lineage.schema import LineageContract
    import yaml

    with open("pipeline-lineage.contract.yaml") as fh:
        raw = yaml.safe_load(fh)
    contract = LineageContract.model_validate(raw)
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.types import TransformOp


# ---------------------------------------------------------------------------
# Stage specification
# ---------------------------------------------------------------------------


class StageSpec(BaseModel):
    """A single declared transformation stage within a lineage chain."""

    model_config = ConfigDict(extra="forbid")

    phase: str = Field(..., min_length=1, description="Pipeline phase name")
    operation: TransformOp = Field(
        ..., description="Type of transformation applied in this stage"
    )
    description: Optional[str] = Field(
        None, description="Human-readable description of what this stage does"
    )


# ---------------------------------------------------------------------------
# Lineage chain specification
# ---------------------------------------------------------------------------


class LineageChainSpec(BaseModel):
    """Declares the full transformation chain for a single field."""

    model_config = ConfigDict(extra="forbid")

    chain_id: str = Field(
        ..., min_length=1, description="Unique chain identifier"
    )
    field: str = Field(
        ..., min_length=1, description="Dot-path field name being tracked"
    )
    stages: list[StageSpec] = Field(
        ..., description="Ordered sequence of declared transformation stages"
    )
    description: Optional[str] = Field(None)


# ---------------------------------------------------------------------------
# Top-level contract
# ---------------------------------------------------------------------------


class LineageContract(BaseModel):
    """
    Root model for a data lineage contract YAML file.

    Declares per-field transformation chains that the ``ProvenanceAuditor``
    uses to verify recorded lineage matches the intended design.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        ..., min_length=1, description="Contract schema version (e.g. 0.1.0)"
    )
    contract_type: Literal["data_lineage"] = Field(
        "data_lineage",
        description="Contract type discriminator",
    )
    pipeline_id: str = Field(
        ..., min_length=1, description="Pipeline this contract governs"
    )
    chains: list[LineageChainSpec] = Field(
        default_factory=list,
        description="Declared transformation chains for tracked fields",
    )
    description: Optional[str] = Field(None)
