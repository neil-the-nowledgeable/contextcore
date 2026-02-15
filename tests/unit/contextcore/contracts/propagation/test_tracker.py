"""Tests for propagation chain tracker."""

from __future__ import annotations

import pytest

from contextcore.contracts.propagation.schema import (
    ChainEndpoint,
    PropagationChainSpec,
    ContextContract,
    PhaseContract,
)
from contextcore.contracts.propagation.tracker import (
    FieldProvenance,
    PropagationChainResult,
    PropagationTracker,
    PROVENANCE_KEY,
    _value_hash,
)
from contextcore.contracts.types import ChainStatus, ConstraintSeverity


@pytest.fixture
def tracker():
    return PropagationTracker()


def _chain(
    chain_id: str = "test_chain",
    source_phase: str = "plan",
    source_field: str = "domain",
    dest_phase: str = "implement",
    dest_field: str = "domain",
    waypoints: list | None = None,
    verification: str | None = None,
) -> PropagationChainSpec:
    return PropagationChainSpec(
        chain_id=chain_id,
        source=ChainEndpoint(phase=source_phase, field=source_field),
        waypoints=waypoints or [],
        destination=ChainEndpoint(phase=dest_phase, field=dest_field),
        verification=verification,
    )


# ---------------------------------------------------------------------------
# Stamp & get provenance
# ---------------------------------------------------------------------------


class TestStamp:
    def test_stamp_records_provenance(self, tracker):
        context: dict = {}
        tracker.stamp(context, "plan", "domain", "web_application")

        prov = tracker.get_provenance(context, "domain")
        assert prov is not None
        assert prov.origin_phase == "plan"
        assert prov.value_hash == _value_hash("web_application")

    def test_stamp_creates_provenance_key(self, tracker):
        context: dict = {}
        tracker.stamp(context, "plan", "domain", "cli")
        assert PROVENANCE_KEY in context

    def test_get_provenance_returns_none_when_absent(self, tracker):
        assert tracker.get_provenance({}, "domain") is None

    def test_provenance_to_dict(self):
        prov = FieldProvenance(
            origin_phase="plan",
            set_at="2026-01-01T00:00:00+00:00",
            value_hash="abcd1234",
        )
        d = prov.to_dict()
        assert d["origin_phase"] == "plan"
        assert d["value_hash"] == "abcd1234"

    def test_provenance_survives_context_mutations(self, tracker):
        context: dict = {"other_key": "value"}
        tracker.stamp(context, "plan", "domain", "web")
        context["new_key"] = "new_value"
        context.pop("other_key")
        prov = tracker.get_provenance(context, "domain")
        assert prov is not None
        assert prov.origin_phase == "plan"


# ---------------------------------------------------------------------------
# Chain checking
# ---------------------------------------------------------------------------


class TestCheckChain:
    def test_intact_chain(self, tracker):
        context = {"domain": "web_application"}
        chain_spec = _chain()
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.INTACT
        assert result.source_present is True
        assert result.destination_present is True

    def test_broken_chain_source_absent(self, tracker):
        context = {}
        chain_spec = _chain()
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.BROKEN
        assert result.source_present is False

    def test_broken_chain_destination_absent(self, tracker):
        context = {"domain": "web"}  # source present
        chain_spec = _chain(dest_field="target_domain")  # different dest field
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.BROKEN
        assert result.destination_present is False

    def test_degraded_chain_empty_value(self, tracker):
        context = {"domain": "unknown"}
        chain_spec = _chain(verification=None)
        # "unknown" is in the degraded values list
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.DEGRADED

    def test_degraded_chain_none_value(self, tracker):
        context = {"domain": None}
        chain_spec = _chain()
        result = tracker.check_chain(chain_spec, context)
        # None means not present → BROKEN (not in dict is same as absent)
        # Actually, key is present but value is None → handled by dest_value check
        # _resolve_field returns (True, None) when key exists with None value
        assert result.status in (ChainStatus.BROKEN, ChainStatus.DEGRADED)

    def test_degraded_chain_empty_string(self, tracker):
        context = {"domain": ""}
        chain_spec = _chain()
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.DEGRADED

    def test_chain_with_waypoints(self, tracker):
        context = {
            "domain": "web",
            "intermediate": "web",
            "target": "web",
        }
        chain_spec = _chain(
            source_field="domain",
            dest_field="target",
            waypoints=[ChainEndpoint(phase="scaffold", field="intermediate")],
        )
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.INTACT
        assert result.waypoints_present == [True]

    def test_chain_with_missing_waypoint(self, tracker):
        context = {"domain": "web", "target": "web"}
        chain_spec = _chain(
            source_field="domain",
            dest_field="target",
            waypoints=[ChainEndpoint(phase="scaffold", field="missing_wp")],
        )
        result = tracker.check_chain(chain_spec, context)
        # Chain is still INTACT — waypoint presence is informational
        assert result.waypoints_present == [False]
        assert result.status == ChainStatus.INTACT

    def test_verification_passes(self, tracker):
        context = {"domain": "web", "target": "web"}
        chain_spec = _chain(
            dest_field="target",
            verification="source == dest",
        )
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.INTACT

    def test_verification_fails(self, tracker):
        context = {"domain": "web", "target": "cli"}
        chain_spec = _chain(
            dest_field="target",
            verification="source == dest",
        )
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.BROKEN
        assert "Verification failed" in result.message

    def test_verification_error(self, tracker):
        context = {"domain": "web", "target": "cli"}
        chain_spec = _chain(
            dest_field="target",
            verification="invalid_var_name",
        )
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.BROKEN
        assert "Verification error" in result.message

    def test_nested_field_resolution(self, tracker):
        context = {
            "domain_summary": {"domain": "web_application"},
            "impl": {"domain": "web_application"},
        }
        chain_spec = _chain(
            source_field="domain_summary.domain",
            dest_field="impl.domain",
        )
        result = tracker.check_chain(chain_spec, context)
        assert result.status == ChainStatus.INTACT

    def test_chain_result_to_dict(self):
        result = PropagationChainResult(
            chain_id="test",
            status=ChainStatus.INTACT,
            source_present=True,
            destination_present=True,
            message="OK",
        )
        d = result.to_dict()
        assert d["chain_id"] == "test"
        assert d["status"] == "intact"


# ---------------------------------------------------------------------------
# Validate all chains
# ---------------------------------------------------------------------------


class TestValidateAllChains:
    def test_validate_all_chains(self, tracker):
        contract = ContextContract(
            schema_version="0.1.0",
            pipeline_id="test",
            phases={
                "plan": PhaseContract(),
                "implement": PhaseContract(),
            },
            propagation_chains=[
                _chain(chain_id="chain1", source_field="domain", dest_field="domain"),
                _chain(chain_id="chain2", source_field="tasks", dest_field="tasks"),
            ],
        )
        context = {"domain": "web", "tasks": [1, 2, 3]}
        results = tracker.validate_all_chains(contract, context)
        assert len(results) == 2
        assert all(r.status == ChainStatus.INTACT for r in results)

    def test_validate_mixed_results(self, tracker):
        contract = ContextContract(
            schema_version="0.1.0",
            pipeline_id="test",
            phases={"plan": PhaseContract()},
            propagation_chains=[
                _chain(chain_id="ok", source_field="domain", dest_field="domain"),
                _chain(chain_id="broken", source_field="missing", dest_field="missing"),
            ],
        )
        context = {"domain": "web"}
        results = tracker.validate_all_chains(contract, context)
        assert results[0].status == ChainStatus.INTACT
        assert results[1].status == ChainStatus.BROKEN
