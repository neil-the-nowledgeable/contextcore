"""Tests for capability propagation contracts (Layer 5)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from contextcore.contracts.capability.loader import CapabilityLoader
from contextcore.contracts.capability.otel import emit_capability_result
from contextcore.contracts.capability.schema import (
    AttenuationSpec,
    CapabilityChainSpec,
    CapabilityContract,
    CapabilityDefinition,
    PhaseCapabilityContract,
)
from contextcore.contracts.capability.tracker import (
    PROVENANCE_KEY,
    CapabilityChainResult,
    CapabilityProvenance,
    CapabilityTracker,
)
from contextcore.contracts.capability.validator import CapabilityValidator
from contextcore.contracts.types import CapabilityChainStatus, ConstraintSeverity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract() -> CapabilityContract:
    return CapabilityContract(
        schema_version="0.1.0",
        contract_type="capability_propagation",
        pipeline_id="test",
        capabilities=[
            CapabilityDefinition(name="fs_access", scope="read-write"),
            CapabilityDefinition(name="api_access", scope="admin", attenuable=True),
            CapabilityDefinition(name="audit_log", scope="write", attenuable=False),
        ],
        phases={
            "plan": PhaseCapabilityContract(
                requires=[],
                provides=["fs_access", "api_access", "audit_log"],
            ),
            "design": PhaseCapabilityContract(
                requires=["fs_access", "api_access"],
                provides=["fs_access", "api_access"],
            ),
            "implement": PhaseCapabilityContract(
                requires=["fs_access"],
                provides=["fs_access"],
            ),
        },
        chains=[
            CapabilityChainSpec(
                chain_id="fs_to_implement",
                capability="fs_access",
                source_phase="plan",
                destination_phase="implement",
            ),
        ],
    )


MINIMAL_YAML = textwrap.dedent("""\
    schema_version: "0.1.0"
    contract_type: capability_propagation
    pipeline_id: test
    capabilities:
      - name: fs_access
        scope: read-write
    phases:
      plan:
        provides: [fs_access]
    chains: []
""")


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_valid_contract(self):
        c = _make_contract()
        assert len(c.capabilities) == 3
        assert len(c.phases) == 3
        assert len(c.chains) == 1

    def test_attenuation_spec(self):
        a = AttenuationSpec(from_scope="rw", to_scope="ro")
        assert a.from_scope == "rw"

    def test_wrong_type_rejected(self):
        with pytest.raises(ValidationError):
            CapabilityContract(
                schema_version="0.1.0",
                contract_type="wrong",
                pipeline_id="t",
                capabilities=[],
                phases={},
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            CapabilityDefinition(name="x", scope="y", bogus="z")


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    CapabilityLoader.clear_cache()
    yield
    CapabilityLoader.clear_cache()


class TestLoader:
    def test_load_from_string(self):
        c = CapabilityLoader().load_from_string(MINIMAL_YAML)
        assert c.pipeline_id == "test"
        assert len(c.capabilities) == 1

    def test_load_from_file(self, tmp_path: Path):
        f = tmp_path / "cap.yaml"
        f.write_text(MINIMAL_YAML)
        c = CapabilityLoader().load(f)
        assert c.pipeline_id == "test"

    def test_caching(self, tmp_path: Path):
        f = tmp_path / "cap.yaml"
        f.write_text(MINIMAL_YAML)
        loader = CapabilityLoader()
        assert loader.load(f) is loader.load(f)

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            CapabilityLoader().load(Path("/nonexistent.yaml"))


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


class TestValidator:
    def test_all_required_present(self):
        contract = _make_contract()
        v = CapabilityValidator(contract)
        ctx: dict = {}
        tracker = CapabilityTracker()
        tracker.grant(ctx, "fs_access", "read-write", "plan")
        tracker.grant(ctx, "api_access", "admin", "plan")
        r = v.validate_entry("design", ctx)
        assert r.passed is True

    def test_missing_required(self):
        contract = _make_contract()
        v = CapabilityValidator(contract)
        ctx: dict = {}
        tracker = CapabilityTracker()
        tracker.grant(ctx, "api_access", "admin", "plan")
        # fs_access missing
        r = v.validate_entry("design", ctx)
        assert r.passed is False
        assert "fs_access" in r.missing_capabilities

    def test_unknown_phase_passes(self):
        contract = _make_contract()
        v = CapabilityValidator(contract)
        r = v.validate_entry("unknown_phase", {})
        assert r.passed is True

    def test_exit_all_provided(self):
        contract = _make_contract()
        v = CapabilityValidator(contract)
        ctx: dict = {}
        tracker = CapabilityTracker()
        tracker.grant(ctx, "fs_access", "read-write", "implement")
        r = v.validate_exit("implement", ctx)
        assert r.passed is True


# ---------------------------------------------------------------------------
# Tracker tests
# ---------------------------------------------------------------------------


class TestTracker:
    def test_grant_and_get(self):
        t = CapabilityTracker()
        ctx: dict = {}
        t.grant(ctx, "fs_access", "read-write", "plan")
        prov = t.get_provenance(ctx, "fs_access")
        assert prov is not None
        assert prov.scope == "read-write"
        assert prov.granted_by == "plan"

    def test_missing_provenance(self):
        t = CapabilityTracker()
        assert t.get_provenance({}, "fs_access") is None

    def test_attenuate(self):
        t = CapabilityTracker()
        ctx: dict = {}
        t.grant(ctx, "fs_access", "read-write", "plan")
        t.attenuate(ctx, "fs_access", "read-only", "design")
        prov = t.get_provenance(ctx, "fs_access")
        assert prov is not None
        assert prov.scope == "read-only"
        assert len(prov.attenuations) == 1
        assert prov.attenuations[0]["from_scope"] == "read-write"
        assert prov.attenuations[0]["to_scope"] == "read-only"

    def test_check_chain_intact(self):
        contract = _make_contract()
        t = CapabilityTracker()
        ctx: dict = {}
        t.grant(ctx, "fs_access", "read-write", "plan")
        result = t.check_chain(contract, contract.chains[0], ctx)
        assert result.status == CapabilityChainStatus.INTACT
        assert result.source_present is True
        assert result.destination_present is True

    def test_check_chain_broken(self):
        contract = _make_contract()
        t = CapabilityTracker()
        ctx: dict = {}
        # No capability granted
        result = t.check_chain(contract, contract.chains[0], ctx)
        assert result.status == CapabilityChainStatus.BROKEN
        assert result.source_present is False


# ---------------------------------------------------------------------------
# OTel tests
# ---------------------------------------------------------------------------


class TestOtel:
    def test_no_otel_no_crash(self):
        with patch("contextcore.contracts._otel_helpers.HAS_OTEL", False):
            emit_capability_result(MagicMock())
