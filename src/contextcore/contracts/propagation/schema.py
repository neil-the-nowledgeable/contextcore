"""
Pydantic v2 models for context propagation contract YAML format.

Contracts declare what context fields each workflow phase requires (entry),
produces (exit), and which fields should propagate across phase boundaries
(enrichment).  Propagation chains model end-to-end field flow from source
to destination through intermediate waypoints.

All models use ``extra="forbid"`` to reject unknown keys at parse time,
following the same pattern as ``contracts/a2a/models.py``.

Usage::

    from contextcore.contracts.propagation.schema import ContextContract
    import yaml

    with open("artisan-pipeline.contract.yaml") as fh:
        raw = yaml.safe_load(fh)
    contract = ContextContract.model_validate(raw)
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.types import ConstraintSeverity


# ---------------------------------------------------------------------------
# Field-level specifications
# ---------------------------------------------------------------------------


class FieldSpec(BaseModel):
    """Specification for a single context field at a phase boundary."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Dot-path field name")
    type: str = Field(
        "str", description="Expected Python type name (str, dict, list, etc.)"
    )
    severity: ConstraintSeverity = Field(
        ConstraintSeverity.BLOCKING,
        description="How to handle absence: blocking/warning/advisory",
    )
    default: Optional[Any] = Field(
        None, description="Default value applied when field is absent"
    )
    description: Optional[str] = Field(
        None, description="Human-readable description of what this field carries"
    )
    source_phase: Optional[str] = Field(
        None, description="Phase that originally produces this field"
    )
    constraints: Optional[dict[str, Any]] = Field(
        None,
        description="Additional constraints (min_length, allowed_values, etc.)",
    )


# ---------------------------------------------------------------------------
# Phase boundary contracts
# ---------------------------------------------------------------------------


class PhaseEntryContract(BaseModel):
    """What a phase requires to start."""

    model_config = ConfigDict(extra="forbid")

    required: list[FieldSpec] = Field(
        default_factory=list,
        description="Fields that MUST be present (blocking on absence)",
    )
    enrichment: list[FieldSpec] = Field(
        default_factory=list,
        description="Fields that SHOULD propagate but degrade gracefully",
    )


class PhaseExitContract(BaseModel):
    """What a phase must produce before handing off."""

    model_config = ConfigDict(extra="forbid")

    required: list[FieldSpec] = Field(
        default_factory=list,
        description="Fields that MUST be present after phase completes",
    )
    optional: list[FieldSpec] = Field(
        default_factory=list,
        description="Fields that MAY be present after phase completes",
    )


class PhaseContract(BaseModel):
    """Full contract for a single workflow phase."""

    model_config = ConfigDict(extra="forbid")

    description: Optional[str] = Field(
        None, description="What this phase does"
    )
    entry: PhaseEntryContract = Field(
        default_factory=PhaseEntryContract,
        description="Entry boundary requirements",
    )
    exit: PhaseExitContract = Field(
        default_factory=PhaseExitContract,
        description="Exit boundary requirements",
    )


# ---------------------------------------------------------------------------
# Propagation chains
# ---------------------------------------------------------------------------


class ChainEndpoint(BaseModel):
    """A phase + field pair used as source, waypoint, or destination."""

    model_config = ConfigDict(extra="forbid")

    phase: str = Field(..., min_length=1)
    field: str = Field(..., min_length=1)


class PropagationChainSpec(BaseModel):
    """End-to-end declaration of a field flowing through the pipeline."""

    model_config = ConfigDict(extra="forbid")

    chain_id: str = Field(..., min_length=1, description="Unique chain identifier")
    description: Optional[str] = Field(None)
    source: ChainEndpoint = Field(..., description="Where the field originates")
    waypoints: list[ChainEndpoint] = Field(
        default_factory=list,
        description="Intermediate phases the field passes through",
    )
    destination: ChainEndpoint = Field(
        ..., description="Where the field must arrive"
    )
    severity: ConstraintSeverity = Field(
        ConstraintSeverity.WARNING,
        description="Severity when chain is broken",
    )
    verification: Optional[str] = Field(
        None,
        description="Python expression evaluated against context for verification",
    )


# ---------------------------------------------------------------------------
# Top-level contract
# ---------------------------------------------------------------------------


class ContextContract(BaseModel):
    """
    Root model for a context propagation contract YAML file.

    Declares per-phase entry/exit requirements and end-to-end propagation
    chains for a workflow pipeline.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        ..., min_length=1, description="Contract schema version (e.g. 0.1.0)"
    )
    pipeline_id: str = Field(
        ..., min_length=1, description="Pipeline this contract governs"
    )
    description: Optional[str] = Field(None)
    phases: dict[str, PhaseContract] = Field(
        ..., description="Per-phase boundary contracts keyed by phase name"
    )
    propagation_chains: list[PropagationChainSpec] = Field(
        default_factory=list,
        description="End-to-end field propagation chain declarations",
    )
