"""
Pydantic v2 models for capability propagation contract YAML format.

Contracts declare what capabilities each workflow phase requires (entry),
provides (exit), and how capabilities attenuate across phase boundaries.
The attenuation invariant ensures capabilities can only narrow, never widen.

All models use ``extra="forbid"`` to reject unknown keys at parse time,
following the same pattern as ``contracts/propagation/schema.py``.

Usage::

    from contextcore.contracts.capability.schema import CapabilityContract
    import yaml

    with open("artisan-pipeline.capability.yaml") as fh:
        raw = yaml.safe_load(fh)
    contract = CapabilityContract.model_validate(raw)
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.types import ConstraintSeverity


# ---------------------------------------------------------------------------
# Attenuation specification
# ---------------------------------------------------------------------------


class AttenuationSpec(BaseModel):
    """Declares a scope narrowing from one phase to the next.

    Attenuation is the only valid direction of change for capabilities —
    scope can narrow (e.g. ``"read-write"`` -> ``"read-only"``) but never
    widen.
    """

    model_config = ConfigDict(extra="forbid")

    from_scope: str = Field(
        ..., min_length=1, description="Original capability scope"
    )
    to_scope: str = Field(
        ..., min_length=1, description="Narrowed capability scope"
    )
    description: Optional[str] = Field(None)


# ---------------------------------------------------------------------------
# Capability definition
# ---------------------------------------------------------------------------


class CapabilityDefinition(BaseModel):
    """Definition of a single named capability in the pipeline.

    Capabilities form an optional hierarchy via ``parent``.  When
    ``attenuable`` is ``False`` the capability must propagate without
    scope change — any attenuation attempt is treated as an error.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ..., min_length=1, description="Unique capability name"
    )
    scope: str = Field(
        ..., min_length=1, description="Capability scope (e.g. 'read-write', 'admin')"
    )
    parent: Optional[str] = Field(
        None, description="Parent capability name for hierarchy"
    )
    attenuable: bool = Field(
        True, description="Whether this capability can be attenuated (narrowed)"
    )
    description: Optional[str] = Field(None)


# ---------------------------------------------------------------------------
# Phase-level capability contract
# ---------------------------------------------------------------------------


class PhaseCapabilityContract(BaseModel):
    """Capability requirements and provisions for a single phase."""

    model_config = ConfigDict(extra="forbid")

    requires: list[str] = Field(
        default_factory=list,
        description="Capability names this phase requires on entry",
    )
    provides: list[str] = Field(
        default_factory=list,
        description="Capability names this phase provides on exit",
    )
    attenuations: list[AttenuationSpec] = Field(
        default_factory=list,
        description="Declared attenuations applied during this phase",
    )


# ---------------------------------------------------------------------------
# Capability chain specification
# ---------------------------------------------------------------------------


class CapabilityChainSpec(BaseModel):
    """End-to-end capability propagation chain declaration.

    Declares that a capability must flow from ``source_phase`` to
    ``destination_phase``, optionally undergoing a declared attenuation.
    """

    model_config = ConfigDict(extra="forbid")

    chain_id: str = Field(
        ..., min_length=1, description="Unique chain identifier"
    )
    capability: str = Field(
        ..., min_length=1, description="Capability name being tracked"
    )
    source_phase: str = Field(
        ..., min_length=1, description="Phase where the capability originates"
    )
    destination_phase: str = Field(
        ..., min_length=1, description="Phase where the capability must arrive"
    )
    expected_attenuation: Optional[AttenuationSpec] = Field(
        None, description="Expected scope narrowing along this chain"
    )
    severity: ConstraintSeverity = Field(
        ConstraintSeverity.BLOCKING,
        description="Severity when chain invariant is violated",
    )


# ---------------------------------------------------------------------------
# Top-level contract
# ---------------------------------------------------------------------------


class CapabilityContract(BaseModel):
    """
    Root model for a capability propagation contract YAML file.

    Declares per-phase capability requirements/provisions and end-to-end
    capability chains.  Enforces the attenuation invariant: capabilities
    can only narrow, never widen.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        ..., min_length=1, description="Contract schema version (e.g. 0.1.0)"
    )
    contract_type: Literal["capability_propagation"] = Field(
        ..., description="Must be 'capability_propagation'"
    )
    pipeline_id: str = Field(
        ..., min_length=1, description="Pipeline this contract governs"
    )
    capabilities: list[CapabilityDefinition] = Field(
        ..., description="All capabilities defined for this pipeline"
    )
    phases: dict[str, PhaseCapabilityContract] = Field(
        ..., description="Per-phase capability contracts keyed by phase name"
    )
    chains: list[CapabilityChainSpec] = Field(
        default_factory=list,
        description="End-to-end capability propagation chain declarations",
    )
    description: Optional[str] = Field(None)
