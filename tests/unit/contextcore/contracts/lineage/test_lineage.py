"""Tests for data lineage contracts (Layer 7)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from contextcore.contracts.lineage.auditor import ProvenanceAuditor
from contextcore.contracts.lineage.loader import LineageLoader
from contextcore.contracts.lineage.otel import emit_audit_result, emit_transformation
from contextcore.contracts.lineage.schema import (
    LineageChainSpec,
    LineageContract,
    StageSpec,
)
from contextcore.contracts.lineage.tracker import LineageTracker, TransformationRecord
from contextcore.contracts.types import LineageStatus, TransformOp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract() -> LineageContract:
    return LineageContract(
        schema_version="0.1.0",
        pipeline_id="test",
        chains=[
            LineageChainSpec(
                chain_id="domain_field",
                field="domain_summary.domain",
                stages=[
                    StageSpec(phase="plan", operation=TransformOp.CLASSIFY),
                    StageSpec(phase="implement", operation=TransformOp.PASSTHROUGH),
                ],
            ),
            LineageChainSpec(
                chain_id="design_text",
                field="design_results",
                stages=[
                    StageSpec(phase="design", operation=TransformOp.TRANSFORM),
                    StageSpec(phase="implement", operation=TransformOp.DERIVE),
                ],
            ),
        ],
    )


MINIMAL_YAML = textwrap.dedent("""\
    schema_version: "0.1.0"
    pipeline_id: test-pipeline
    chains:
      - chain_id: domain_field
        field: domain_summary.domain
        stages:
          - phase: plan
            operation: classify
          - phase: implement
            operation: passthrough
""")


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_valid_contract(self):
        c = _make_contract()
        assert len(c.chains) == 2
        assert c.chains[0].chain_id == "domain_field"

    def test_stage_spec(self):
        s = StageSpec(phase="plan", operation=TransformOp.CLASSIFY)
        assert s.phase == "plan"
        assert s.operation == TransformOp.CLASSIFY

    def test_empty_chain_id_rejected(self):
        with pytest.raises(ValidationError):
            LineageChainSpec(chain_id="", field="x", stages=[])

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            LineageContract(
                schema_version="0.1.0",
                pipeline_id="t",
                bogus="y",
            )


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    LineageLoader.clear_cache()
    yield
    LineageLoader.clear_cache()


class TestLoader:
    def test_load_from_string(self):
        c = LineageLoader().load_from_string(MINIMAL_YAML)
        assert c.pipeline_id == "test-pipeline"
        assert len(c.chains) == 1

    def test_load_from_file(self, tmp_path: Path):
        f = tmp_path / "lineage.yaml"
        f.write_text(MINIMAL_YAML)
        c = LineageLoader().load(f)
        assert c.pipeline_id == "test-pipeline"

    def test_caching(self, tmp_path: Path):
        f = tmp_path / "lineage.yaml"
        f.write_text(MINIMAL_YAML)
        loader = LineageLoader()
        assert loader.load(f) is loader.load(f)

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            LineageLoader().load(Path("/nonexistent.yaml"))


# ---------------------------------------------------------------------------
# Tracker tests
# ---------------------------------------------------------------------------


class TestTracker:
    def test_record_and_get_history(self):
        t = LineageTracker()
        ctx: dict = {}
        t.record_transformation(ctx, "domain", "plan", TransformOp.CLASSIFY, "raw", "web_app")
        history = t.get_history(ctx, "domain")
        assert len(history) == 1
        assert history[0].phase == "plan"
        assert history[0].operation == TransformOp.CLASSIFY

    def test_multiple_records(self):
        t = LineageTracker()
        ctx: dict = {}
        t.record_transformation(ctx, "domain", "plan", TransformOp.CLASSIFY, "raw", "web_app")
        t.record_transformation(ctx, "domain", "implement", TransformOp.PASSTHROUGH, "web_app", "web_app")
        assert len(t.get_history(ctx, "domain")) == 2

    def test_empty_history(self):
        t = LineageTracker()
        assert t.get_history({}, "nonexistent") == []

    def test_get_latest(self):
        t = LineageTracker()
        ctx: dict = {}
        t.record_transformation(ctx, "x", "plan", TransformOp.CLASSIFY, "a", "b")
        t.record_transformation(ctx, "x", "design", TransformOp.TRANSFORM, "b", "c")
        latest = t.get_latest(ctx, "x")
        assert latest is not None
        assert latest.phase == "design"

    def test_get_latest_empty(self):
        t = LineageTracker()
        assert t.get_latest({}, "x") is None

    def test_passthrough_hashes_match(self):
        t = LineageTracker()
        ctx: dict = {}
        t.record_transformation(ctx, "field", "plan", TransformOp.PASSTHROUGH, "same_val", "same_val")
        r = t.get_history(ctx, "field")[0]
        assert r.input_hash == r.output_hash

    def test_transform_hashes_differ(self):
        t = LineageTracker()
        ctx: dict = {}
        t.record_transformation(ctx, "field", "plan", TransformOp.TRANSFORM, "input", "output")
        r = t.get_history(ctx, "field")[0]
        assert r.input_hash != r.output_hash


# ---------------------------------------------------------------------------
# Auditor tests
# ---------------------------------------------------------------------------


class TestAuditor:
    def test_verified_chain(self):
        contract = _make_contract()
        ctx: dict = {}
        t = LineageTracker()
        t.record_transformation(ctx, "domain_summary.domain", "plan", TransformOp.CLASSIFY, "raw", "web")
        t.record_transformation(ctx, "domain_summary.domain", "implement", TransformOp.PASSTHROUGH, "web", "web")

        auditor = ProvenanceAuditor(contract)
        result = auditor.audit_chain(contract.chains[0], ctx)
        assert result.status == LineageStatus.VERIFIED

    def test_incomplete_chain(self):
        contract = _make_contract()
        ctx: dict = {}
        t = LineageTracker()
        t.record_transformation(ctx, "domain_summary.domain", "plan", TransformOp.CLASSIFY, "raw", "web")
        # Missing implement stage

        auditor = ProvenanceAuditor(contract)
        result = auditor.audit_chain(contract.chains[0], ctx)
        assert result.status == LineageStatus.INCOMPLETE

    def test_chain_broken(self):
        contract = _make_contract()
        ctx: dict = {}
        # No records at all

        auditor = ProvenanceAuditor(contract)
        result = auditor.audit_chain(contract.chains[0], ctx)
        assert result.status == LineageStatus.CHAIN_BROKEN

    def test_mutation_detected(self):
        contract = _make_contract()
        ctx: dict = {}
        t = LineageTracker()
        t.record_transformation(ctx, "domain_summary.domain", "plan", TransformOp.CLASSIFY, "raw", "web")
        # Passthrough with different input and output values → different hashes
        t.record_transformation(ctx, "domain_summary.domain", "implement", TransformOp.PASSTHROUGH, "web", "web_CHANGED")

        auditor = ProvenanceAuditor(contract)
        result = auditor.audit_chain(contract.chains[0], ctx)
        assert result.status == LineageStatus.MUTATION_DETECTED

    def test_audit_all(self):
        contract = _make_contract()
        ctx: dict = {}
        t = LineageTracker()
        t.record_transformation(ctx, "domain_summary.domain", "plan", TransformOp.CLASSIFY, "raw", "web")
        t.record_transformation(ctx, "domain_summary.domain", "implement", TransformOp.PASSTHROUGH, "web", "web")
        t.record_transformation(ctx, "design_results", "design", TransformOp.TRANSFORM, "input", "output")
        t.record_transformation(ctx, "design_results", "implement", TransformOp.DERIVE, "output", "derived")

        auditor = ProvenanceAuditor(contract)
        summary = auditor.audit_all(ctx)
        assert summary.total_chains == 2
        assert summary.passed is True
        assert summary.verified_count == 2


# ---------------------------------------------------------------------------
# OTel tests
# ---------------------------------------------------------------------------


class TestOtel:
    def test_no_otel_no_crash(self):
        with patch("contextcore.contracts._otel_helpers.HAS_OTEL", False):
            emit_transformation("field", MagicMock())
            emit_audit_result(MagicMock())
