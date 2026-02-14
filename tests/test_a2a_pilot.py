"""
Tests for the PI-101-002 pilot runner.

Day 5 spec: "Full pilot trace exists with gate evidence and no silent phase
transitions."

Tests verify:
- Happy path completes all 10 spans with gate evidence.
- Checksum mismatch blocks at CONTRACT_INTEGRITY (S3).
- Gap parity failure blocks at INGEST_PARSE_ASSESS (S4).
- Test failures block at TEST_VALIDATE (S8).
- Review blocking issues block at REVIEW_CALIBRATE (S9).
- Evidence file is written correctly.
- Every gate result passes JSON schema validation.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from contextcore.contracts.a2a.pilot import PilotResult, PilotRunner, PilotSeed
from contextcore.contracts.a2a.validator import validate_payload


class TestPilotHappyPath:
    """Default seed should produce a clean, complete trace."""

    def test_all_spans_completed(self) -> None:
        result = PilotRunner().execute()
        assert result.final_status == "completed"
        assert result.is_success
        assert len(result.spans) == 10
        for span in result.spans:
            assert span.status == "completed", f"{span.span_id} is {span.status}"

    def test_no_blocked_spans(self) -> None:
        result = PilotRunner().execute()
        assert result.blocked_spans == []

    def test_gate_results_emitted(self) -> None:
        result = PilotRunner().execute()
        # At minimum: S2-C1, S3-C1, S3-C2, S4-C1, S6-C1, S7-C1, S8-G1, S9-G1, S10-C1
        assert len(result.gate_results) >= 9

    def test_all_gates_pass(self) -> None:
        result = PilotRunner().execute()
        for gr in result.gate_results:
            assert gr["result"] == "pass", f"Gate {gr['gate_id']} failed: {gr.get('reason')}"

    def test_summary_structure(self) -> None:
        result = PilotRunner().execute()
        s = result.summary()
        assert s["trace_id"] == "PI-101-002"
        assert s["total_spans"] == 10
        assert s["completed_spans"] == 10
        assert s["is_success"] is True

    def test_spans_have_contracts(self) -> None:
        result = PilotRunner().execute()
        for span in result.spans:
            assert span.contract is not None, f"{span.span_id} has no contract"
            assert span.contract["schema_version"] == "v1"
            assert span.contract["task_id"] == span.span_id

    def test_spans_have_events(self) -> None:
        result = PilotRunner().execute()
        for span in result.spans:
            # Every span should have at least span.started and span.completed
            event_types = [e["event_type"] for e in span.events]
            assert "span.started" in event_types, f"{span.span_id} missing span.started"
            assert "span.completed" in event_types, f"{span.span_id} missing span.completed"


class TestChecksumMismatchBlocks:
    """Stale source checksum should block at S3 (CONTRACT_INTEGRITY)."""

    def test_blocks_at_s3(self) -> None:
        seed = PilotSeed(source_checksum="sha256:STALE")
        result = PilotRunner(seed=seed).execute()
        assert result.final_status == "blocked"
        assert "PI-101-002-S3" in result.blocked_spans

    def test_downstream_spans_not_started(self) -> None:
        seed = PilotSeed(source_checksum="sha256:STALE")
        result = PilotRunner(seed=seed).execute()
        # S4 through S10 should be not_started
        for span in result.spans:
            if span.span_id in ("PI-101-002-S4", "PI-101-002-S5", "PI-101-002-S6",
                                "PI-101-002-S7", "PI-101-002-S8", "PI-101-002-S9",
                                "PI-101-002-S10"):
                assert span.status == "not_started", f"{span.span_id} is {span.status}"

    def test_s1_s2_completed(self) -> None:
        seed = PilotSeed(source_checksum="sha256:STALE")
        result = PilotRunner(seed=seed).execute()
        assert result.spans[0].status == "completed"  # S1
        assert result.spans[1].status == "completed"  # S2

    def test_blocked_span_has_reason(self) -> None:
        seed = PilotSeed(source_checksum="sha256:STALE")
        result = PilotRunner(seed=seed).execute()
        s3 = result.spans[2]
        assert s3.blocked_reason is not None
        assert "checksum" in s3.blocked_reason.lower() or "mismatch" in s3.blocked_reason.lower()
        assert s3.next_action is not None


class TestGapParityBlocks:
    """Dropped feature should block at S4 (INGEST_PARSE_ASSESS)."""

    def test_blocks_at_s4(self) -> None:
        seed = PilotSeed(
            feature_ids=["gap-latency-panel"]  # missing 2 of 3
        )
        result = PilotRunner(seed=seed).execute()
        assert result.final_status == "blocked"
        assert "PI-101-002-S4" in result.blocked_spans

    def test_s1_s2_s3_completed(self) -> None:
        seed = PilotSeed(feature_ids=["gap-latency-panel"])
        result = PilotRunner(seed=seed).execute()
        assert result.spans[0].status == "completed"  # S1
        assert result.spans[1].status == "completed"  # S2
        assert result.spans[2].status == "completed"  # S3


class TestTestFailureBlocks:
    """Critical test failures should block at S8 (TEST_VALIDATE)."""

    def test_blocks_at_s8(self) -> None:
        seed = PilotSeed(test_critical_failures=2)
        result = PilotRunner(seed=seed).execute()
        assert result.final_status == "blocked"
        assert "PI-101-002-S8" in result.blocked_spans

    def test_s1_through_s7_completed(self) -> None:
        seed = PilotSeed(test_critical_failures=1)
        result = PilotRunner(seed=seed).execute()
        for i in range(7):  # S1-S7
            assert result.spans[i].status == "completed", (
                f"{result.spans[i].span_id} is {result.spans[i].status}"
            )


class TestReviewBlockingBlocks:
    """Blocking review issues should block at S9 (REVIEW_CALIBRATE)."""

    def test_blocks_at_s9(self) -> None:
        seed = PilotSeed(review_blocking_issues=1)
        result = PilotRunner(seed=seed).execute()
        assert result.final_status == "blocked"
        assert "PI-101-002-S9" in result.blocked_spans


class TestEvidenceOutput:
    """Trace evidence should be written to a JSON file."""

    def test_write_evidence(self) -> None:
        result = PilotRunner().execute()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = result.write_evidence(Path(tmpdir) / "trace.json")
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["trace_id"] == "PI-101-002"
            assert data["final_status"] == "completed"
            assert len(data["spans"]) == 10

    def test_evidence_contains_gate_results(self) -> None:
        result = PilotRunner().execute()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = result.write_evidence(Path(tmpdir) / "trace.json")
            data = json.loads(path.read_text())
            assert len(data["gate_results"]) >= 9

    def test_blocked_evidence_shows_reason(self) -> None:
        seed = PilotSeed(source_checksum="sha256:STALE")
        result = PilotRunner(seed=seed).execute()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = result.write_evidence(Path(tmpdir) / "trace.json")
            data = json.loads(path.read_text())
            assert data["final_status"] == "blocked"
            s3 = data["spans"][2]
            assert s3["blocked_reason"] is not None


class TestGateResultSchemaCompliance:
    """Every GateResult emitted by the pilot must pass JSON schema validation."""

    def test_all_gate_results_valid(self) -> None:
        result = PilotRunner().execute()
        for gr in result.gate_results:
            report = validate_payload("GateResult", gr)
            assert report.is_valid, (
                f"Gate {gr['gate_id']} failed schema: "
                f"{[e.message for e in report.errors]}"
            )

    def test_blocked_gate_results_valid(self) -> None:
        seed = PilotSeed(source_checksum="sha256:STALE")
        result = PilotRunner(seed=seed).execute()
        for gr in result.gate_results:
            report = validate_payload("GateResult", gr)
            assert report.is_valid, (
                f"Gate {gr['gate_id']} failed schema: "
                f"{[e.message for e in report.errors]}"
            )
