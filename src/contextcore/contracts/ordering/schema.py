"""
Pydantic v2 models for causal ordering contract YAML format.

Contracts declare happens-before dependencies between pipeline events.
Each dependency specifies that one event (before) must have a lower
logical timestamp than another (after).  Violations indicate events
arriving in the wrong order within a pipeline execution.

All models use ``extra="forbid"`` to reject unknown keys at parse time,
following the same pattern as ``contracts/propagation/schema.py``.

Usage::

    from contextcore.contracts.ordering.schema import OrderingConstraintSpec
    import yaml

    with open("pipeline-ordering.contract.yaml") as fh:
        raw = yaml.safe_load(fh)
    spec = OrderingConstraintSpec.model_validate(raw)
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.types import ConstraintSeverity


# ---------------------------------------------------------------------------
# Endpoint and dependency models
# ---------------------------------------------------------------------------


class CausalEndpoint(BaseModel):
    """A phase + event pair identifying a point in the pipeline timeline."""

    model_config = ConfigDict(extra="forbid")

    phase: str = Field(..., min_length=1, description="Pipeline phase name")
    event: str = Field(..., min_length=1, description="Event name within the phase")


class CausalDependency(BaseModel):
    """A happens-before relationship between two pipeline events.

    Declares that ``before`` must have a strictly lower logical timestamp
    than ``after``.  If this ordering is violated at validation time, the
    severity determines whether it blocks, warns, or advises.
    """

    model_config = ConfigDict(extra="forbid")

    before: CausalEndpoint = Field(
        ..., description="Event that must happen first"
    )
    after: CausalEndpoint = Field(
        ..., description="Event that must happen second"
    )
    severity: ConstraintSeverity = Field(
        ConstraintSeverity.WARNING,
        description="Severity when ordering is violated",
    )
    description: Optional[str] = Field(
        None, description="Human-readable description of why this ordering matters"
    )


# ---------------------------------------------------------------------------
# Top-level contract
# ---------------------------------------------------------------------------


class OrderingConstraintSpec(BaseModel):
    """
    Root model for a causal ordering contract YAML file.

    Declares happens-before dependencies between pipeline events and
    the severity of violations.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        ..., min_length=1, description="Contract schema version (e.g. 0.1.0)"
    )
    contract_type: Literal["causal_ordering"] = Field(
        ..., description="Must be 'causal_ordering'"
    )
    pipeline_id: str = Field(
        ..., min_length=1, description="Pipeline this contract governs"
    )
    dependencies: list[CausalDependency] = Field(
        ..., description="Ordered list of happens-before dependencies"
    )
    description: Optional[str] = Field(
        None, description="Human-readable description of this ordering contract"
    )
