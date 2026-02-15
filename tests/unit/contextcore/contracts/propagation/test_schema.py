"""Tests for context propagation contract schema models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contextcore.contracts.propagation.schema import (
    ChainEndpoint,
    ContextContract,
    FieldSpec,
    PhaseContract,
    PhaseEntryContract,
    PhaseExitContract,
    PropagationChainSpec,
)
from contextcore.contracts.types import ConstraintSeverity


# ---------------------------------------------------------------------------
# FieldSpec
# ---------------------------------------------------------------------------


class TestFieldSpec:
    def test_minimal_field(self):
        f = FieldSpec(name="project_root")
        assert f.name == "project_root"
        assert f.type == "str"
        assert f.severity == ConstraintSeverity.BLOCKING
        assert f.default is None

    def test_full_field(self):
        f = FieldSpec(
            name="domain_summary.domain",
            type="str",
            severity=ConstraintSeverity.WARNING,
            default="unknown",
            description="Domain classification",
            source_phase="plan",
            constraints={"allowed_values": ["web", "cli"]},
        )
        assert f.severity == ConstraintSeverity.WARNING
        assert f.default == "unknown"
        assert f.source_phase == "plan"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            FieldSpec(name="")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            FieldSpec(name="foo", bogus_field="bar")


# ---------------------------------------------------------------------------
# PhaseContract
# ---------------------------------------------------------------------------


class TestPhaseContract:
    def test_empty_phase_contract(self):
        pc = PhaseContract()
        assert pc.entry.required == []
        assert pc.entry.enrichment == []
        assert pc.exit.required == []
        assert pc.exit.optional == []

    def test_phase_with_fields(self):
        pc = PhaseContract(
            description="Test phase",
            entry=PhaseEntryContract(
                required=[FieldSpec(name="tasks")],
                enrichment=[
                    FieldSpec(name="domain", severity=ConstraintSeverity.WARNING, default="unknown")
                ],
            ),
            exit=PhaseExitContract(
                required=[FieldSpec(name="results")],
            ),
        )
        assert len(pc.entry.required) == 1
        assert len(pc.entry.enrichment) == 1
        assert pc.entry.enrichment[0].default == "unknown"


# ---------------------------------------------------------------------------
# PropagationChainSpec
# ---------------------------------------------------------------------------


class TestPropagationChainSpec:
    def test_chain_spec(self):
        chain = PropagationChainSpec(
            chain_id="domain_to_implement",
            source=ChainEndpoint(phase="plan", field="domain"),
            destination=ChainEndpoint(phase="implement", field="domain"),
        )
        assert chain.chain_id == "domain_to_implement"
        assert chain.severity == ConstraintSeverity.WARNING  # default

    def test_chain_with_waypoints(self):
        chain = PropagationChainSpec(
            chain_id="validators_to_test",
            source=ChainEndpoint(phase="plan", field="validators"),
            waypoints=[ChainEndpoint(phase="implement", field="validators")],
            destination=ChainEndpoint(phase="test", field="validators"),
            severity=ConstraintSeverity.BLOCKING,
            verification="len(dest) > 0",
        )
        assert len(chain.waypoints) == 1
        assert chain.verification == "len(dest) > 0"

    def test_empty_chain_id_rejected(self):
        with pytest.raises(ValidationError):
            PropagationChainSpec(
                chain_id="",
                source=ChainEndpoint(phase="a", field="b"),
                destination=ChainEndpoint(phase="c", field="d"),
            )


# ---------------------------------------------------------------------------
# ContextContract (top-level)
# ---------------------------------------------------------------------------


class TestContextContract:
    def test_minimal_contract(self):
        contract = ContextContract(
            schema_version="0.1.0",
            pipeline_id="test",
            phases={"plan": PhaseContract()},
        )
        assert contract.pipeline_id == "test"
        assert len(contract.phases) == 1
        assert contract.propagation_chains == []

    def test_full_contract(self):
        contract = ContextContract(
            schema_version="0.1.0",
            pipeline_id="artisan",
            description="Test pipeline",
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[FieldSpec(name="project_root")],
                    ),
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="tasks"), FieldSpec(name="domain")],
                    ),
                ),
                "implement": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[FieldSpec(name="tasks")],
                        enrichment=[
                            FieldSpec(name="domain", severity=ConstraintSeverity.WARNING, default="unknown"),
                        ],
                    ),
                ),
            },
            propagation_chains=[
                PropagationChainSpec(
                    chain_id="domain_flow",
                    source=ChainEndpoint(phase="plan", field="domain"),
                    destination=ChainEndpoint(phase="implement", field="domain"),
                ),
            ],
        )
        assert len(contract.phases) == 2
        assert len(contract.propagation_chains) == 1

    def test_extra_top_level_field_rejected(self):
        with pytest.raises(ValidationError):
            ContextContract(
                schema_version="0.1.0",
                pipeline_id="test",
                phases={},
                unknown_field="oops",
            )

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ContextContract(
                pipeline_id="test",
                phases={},
            )
