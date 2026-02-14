"""
Comprehensive tests for A2A contract models, validators, boundary enforcement,
and phase gates.

Covers Day 2-4 of the A2A Governance 7-Day Execution Checklist:
- Day 2: Validation helpers — invalid payloads fail with actionable errors.
- Day 3: Boundary enforcement — no unvalidated handoff enters execution path.
- Day 4: Phase gate library — gates block downstream on failure.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from contextcore.contracts.a2a.models import (
    ArtifactIntent,
    ArtifactIntentAction,
    Checksums,
    EvidenceItem,
    ExpectedOutput,
    GateOutcome,
    GateResult,
    GateSeverity,
    HandoffContract,
    HandoffContractStatus,
    HandoffPriority,
    OutputConvention,
    Phase,
    PromotionReason,
    SpanMetrics,
    SpanStatus,
    TaskSpanContract,
)
from contextcore.contracts.a2a.validator import (
    A2AValidator,
    ValidationErrorEnvelope,
    ValidationReport,
    validate_payload,
)
from contextcore.contracts.a2a.boundary import (
    BoundaryEnforcementError,
    validate_inbound,
    validate_outbound,
)
from contextcore.contracts.a2a.gates import (
    GateChecker,
    check_checksum_chain,
    check_gap_parity,
    check_mapping_completeness,
)


# ============================================================================
# Fixtures — minimal valid payloads
# ============================================================================


@pytest.fixture
def valid_task_span_payload() -> dict:
    return {
        "schema_version": "v1",
        "project_id": "contextcore",
        "task_id": "PI-101-002-S3",
        "phase": "CONTRACT_INTEGRITY",
        "status": "in_progress",
    }


@pytest.fixture
def valid_handoff_payload() -> dict:
    return {
        "schema_version": "v1",
        "handoff_id": "handoff-001",
        "from_agent": "orchestrator",
        "to_agent": "artifact-generator",
        "capability_id": "generate_dashboard",
        "inputs": {"service": "checkout-api"},
        "expected_output": {"type": "artifact_bundle"},
    }


@pytest.fixture
def valid_artifact_intent_payload() -> dict:
    return {
        "schema_version": "v1",
        "artifact_id": "dashboard-checkout",
        "artifact_type": "grafana_dashboard",
        "intent": "create",
        "owner": "observability-team",
        "parameter_sources": {"service_name": "manifest.spec.project.id"},
    }


@pytest.fixture
def valid_gate_result_payload() -> dict:
    return {
        "schema_version": "v1",
        "gate_id": "PI-101-002-S3-C2",
        "phase": "CONTRACT_INTEGRITY",
        "result": "pass",
        "severity": "info",
        "checked_at": "2026-02-13T20:40:00Z",
    }


# ============================================================================
# PART 1 — Pydantic model tests
# ============================================================================


class TestTaskSpanContract:
    """Tests for TaskSpanContract Pydantic model."""

    def test_minimal_valid(self) -> None:
        m = TaskSpanContract(
            project_id="proj",
            task_id="T-1",
            phase=Phase.INIT_BASELINE,
            status=SpanStatus.NOT_STARTED,
        )
        assert m.schema_version == "v1"
        assert m.project_id == "proj"
        assert m.phase == Phase.INIT_BASELINE
        assert m.status == SpanStatus.NOT_STARTED

    def test_full_payload(self) -> None:
        m = TaskSpanContract(
            project_id="contextcore",
            trace_id="trace-123",
            span_id="span-abc",
            task_id="PI-101-002-S3",
            parent_task_id="PI-101-002",
            phase=Phase.CONTRACT_INTEGRITY,
            status=SpanStatus.IN_PROGRESS,
            checksums=Checksums(
                source_checksum="sha256:111",
                artifact_manifest_checksum="sha256:222",
            ),
            metrics=SpanMetrics(gap_count=6, feature_count=6),
            acceptance_criteria=["checksum must match"],
            timestamp=datetime(2026, 2, 13, 20, 30, tzinfo=timezone.utc),
        )
        assert m.checksums.source_checksum == "sha256:111"
        assert m.metrics.gap_count == 6

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(Exception):
            TaskSpanContract(
                project_id="proj",
                task_id="T-1",
                phase="INIT_BASELINE",
                status="in_progress",
                rogue_field="should fail",
            )

    def test_rejects_invalid_schema_version(self) -> None:
        with pytest.raises(Exception):
            TaskSpanContract(
                schema_version="v2",
                project_id="proj",
                task_id="T-1",
                phase="INIT_BASELINE",
                status="in_progress",
            )

    def test_rejects_invalid_phase(self) -> None:
        with pytest.raises(Exception):
            TaskSpanContract(
                project_id="proj",
                task_id="T-1",
                phase="NONEXISTENT_PHASE",
                status="in_progress",
            )

    def test_rejects_empty_project_id(self) -> None:
        with pytest.raises(Exception):
            TaskSpanContract(
                project_id="",
                task_id="T-1",
                phase="INIT_BASELINE",
                status="in_progress",
            )

    def test_blocked_span_fields(self) -> None:
        m = TaskSpanContract(
            project_id="proj",
            task_id="T-1",
            phase=Phase.EXPORT_CONTRACT,
            status=SpanStatus.BLOCKED,
            blocked_reason="Stale checksum",
            blocked_on_span_id="T-0",
            next_action="Re-export",
        )
        assert m.blocked_reason == "Stale checksum"


class TestHandoffContract:
    """Tests for HandoffContract Pydantic model."""

    def test_minimal_valid(self) -> None:
        m = HandoffContract(
            handoff_id="h-1",
            from_agent="a",
            to_agent="b",
            capability_id="cap",
            inputs={"key": "val"},
            expected_output=ExpectedOutput(type="artifact_bundle"),
        )
        assert m.schema_version == "v1"
        assert m.priority == HandoffPriority.NORMAL
        assert m.status == HandoffContractStatus.PENDING

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(Exception):
            HandoffContract(
                handoff_id="h-1",
                from_agent="a",
                to_agent="b",
                capability_id="cap",
                inputs={},
                expected_output=ExpectedOutput(type="x"),
                bonus="nope",
            )


class TestArtifactIntent:
    """Tests for ArtifactIntent Pydantic model."""

    def test_minimal_valid(self) -> None:
        m = ArtifactIntent(
            artifact_id="art-1",
            artifact_type="grafana_dashboard",
            intent=ArtifactIntentAction.CREATE,
            owner="team",
            parameter_sources={"svc": "manifest.spec.project.id"},
        )
        assert m.promoted_to_task is False
        assert m.promotion_reason == PromotionReason.NONE

    def test_promoted_artifact(self) -> None:
        m = ArtifactIntent(
            artifact_id="art-2",
            artifact_type="alert_rule",
            intent=ArtifactIntentAction.CREATE,
            owner="sre-team",
            parameter_sources={"svc": "value"},
            promoted_to_task=True,
            promotion_reason=PromotionReason.RISK,
            task_id="T-42",
        )
        assert m.promoted_to_task is True
        assert m.promotion_reason == PromotionReason.RISK

    def test_output_convention(self) -> None:
        m = ArtifactIntent(
            artifact_id="art-3",
            artifact_type="dashboard",
            intent=ArtifactIntentAction.CREATE,
            owner="team",
            parameter_sources={"svc": "x"},
            output_convention=OutputConvention(output_path="grafana/", output_ext=".json"),
        )
        assert m.output_convention.output_path == "grafana/"


class TestGateResult:
    """Tests for GateResult Pydantic model."""

    def test_minimal_valid(self) -> None:
        m = GateResult(
            gate_id="g-1",
            phase=Phase.CONTRACT_INTEGRITY,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            checked_at=datetime.now(timezone.utc),
        )
        assert m.blocking is False

    def test_blocking_failure(self) -> None:
        m = GateResult(
            gate_id="g-2",
            phase=Phase.CONTRACT_INTEGRITY,
            result=GateOutcome.FAIL,
            severity=GateSeverity.CRITICAL,
            reason="Checksum mismatch",
            next_action="Re-export",
            blocking=True,
            evidence=[
                EvidenceItem(type="checksum", ref="source_checksum"),
            ],
            checked_at=datetime.now(timezone.utc),
        )
        assert m.blocking is True
        assert m.result == GateOutcome.FAIL
        assert len(m.evidence) == 1


# ============================================================================
# PART 2 — JSON schema validator tests (Day 2)
# ============================================================================


class TestA2AValidator:
    """Unit tests proving invalid payloads fail with actionable errors."""

    def test_valid_task_span(self, valid_task_span_payload: dict) -> None:
        report = validate_payload("TaskSpanContract", valid_task_span_payload)
        assert report.is_valid
        assert report.errors == []

    def test_valid_handoff(self, valid_handoff_payload: dict) -> None:
        report = validate_payload("HandoffContract", valid_handoff_payload)
        assert report.is_valid

    def test_valid_artifact_intent(self, valid_artifact_intent_payload: dict) -> None:
        report = validate_payload("ArtifactIntent", valid_artifact_intent_payload)
        assert report.is_valid

    def test_valid_gate_result(self, valid_gate_result_payload: dict) -> None:
        report = validate_payload("GateResult", valid_gate_result_payload)
        assert report.is_valid

    def test_missing_required_field(self) -> None:
        payload = {
            "schema_version": "v1",
            # missing project_id, task_id, phase, status
        }
        report = validate_payload("TaskSpanContract", payload)
        assert not report.is_valid
        codes = {e.error_code for e in report.errors}
        assert "MISSING_REQUIRED_FIELD" in codes

    def test_unknown_top_level_field_rejected(self, valid_task_span_payload: dict) -> None:
        payload = {**valid_task_span_payload, "rogue": "value"}
        report = validate_payload("TaskSpanContract", payload)
        assert not report.is_valid
        codes = {e.error_code for e in report.errors}
        assert "UNKNOWN_FIELD" in codes

    def test_invalid_enum_value(self, valid_task_span_payload: dict) -> None:
        payload = {**valid_task_span_payload, "status": "bogus"}
        report = validate_payload("TaskSpanContract", payload)
        assert not report.is_valid
        codes = {e.error_code for e in report.errors}
        assert "INVALID_ENUM_VALUE" in codes

    def test_invalid_schema_version(self, valid_task_span_payload: dict) -> None:
        payload = {**valid_task_span_payload, "schema_version": "v2"}
        report = validate_payload("TaskSpanContract", payload)
        assert not report.is_valid

    def test_error_envelope_has_all_fields(self) -> None:
        payload = {"schema_version": "v2"}  # many errors expected
        report = validate_payload("TaskSpanContract", payload)
        assert not report.is_valid
        for err in report.errors:
            assert isinstance(err, ValidationErrorEnvelope)
            assert err.error_code
            assert err.schema_id
            assert err.failed_path
            assert err.message
            assert err.next_action

    def test_error_envelope_to_dict(self) -> None:
        envelope = ValidationErrorEnvelope(
            error_code="MISSING_REQUIRED_FIELD",
            schema_id="test",
            failed_path="/project_id",
            message="missing",
            next_action="add it",
        )
        d = envelope.to_dict()
        assert d["error_code"] == "MISSING_REQUIRED_FIELD"
        assert "/project_id" in d["failed_path"]

    def test_unknown_contract_name(self) -> None:
        with pytest.raises(ValueError, match="Unknown contract name"):
            validate_payload("NonexistentContract", {})

    def test_handoff_missing_required_fields(self) -> None:
        payload = {"schema_version": "v1"}
        report = validate_payload("HandoffContract", payload)
        assert not report.is_valid
        # Must fail for handoff_id, from_agent, to_agent, capability_id, inputs, expected_output
        assert len(report.errors) >= 5

    def test_gate_result_invalid_severity(self, valid_gate_result_payload: dict) -> None:
        payload = {**valid_gate_result_payload, "severity": "extreme"}
        report = validate_payload("GateResult", payload)
        assert not report.is_valid


# ============================================================================
# PART 3 — Boundary enforcement tests (Day 3)
# ============================================================================


class TestBoundaryEnforcement:
    """Day 3: No unvalidated handoff can enter execution path."""

    def test_outbound_valid_passes(self, valid_handoff_payload: dict) -> None:
        result = validate_outbound("HandoffContract", valid_handoff_payload)
        assert result == valid_handoff_payload

    def test_inbound_valid_passes(self, valid_handoff_payload: dict) -> None:
        result = validate_inbound("HandoffContract", valid_handoff_payload)
        assert result == valid_handoff_payload

    def test_outbound_invalid_raises(self) -> None:
        bad_payload = {"schema_version": "v1"}  # missing many fields
        with pytest.raises(BoundaryEnforcementError) as exc_info:
            validate_outbound("HandoffContract", bad_payload)
        assert exc_info.value.direction == "outbound"
        assert exc_info.value.contract_name == "HandoffContract"
        assert not exc_info.value.report.is_valid

    def test_inbound_invalid_raises(self) -> None:
        bad_payload = {"schema_version": "v1", "rogue": "x"}
        with pytest.raises(BoundaryEnforcementError) as exc_info:
            validate_inbound("HandoffContract", bad_payload)
        assert exc_info.value.direction == "inbound"

    def test_failure_event_has_structure(self) -> None:
        bad_payload = {"schema_version": "v1"}
        with pytest.raises(BoundaryEnforcementError) as exc_info:
            validate_outbound("TaskSpanContract", bad_payload)
        event = exc_info.value.to_failure_event()
        assert event["event_type"] == "handoff.validation.outbound.failed"
        assert event["contract_name"] == "TaskSpanContract"
        assert event["error_count"] >= 1
        assert isinstance(event["errors"], list)

    def test_all_four_contracts_enforced(
        self,
        valid_task_span_payload: dict,
        valid_handoff_payload: dict,
        valid_artifact_intent_payload: dict,
        valid_gate_result_payload: dict,
    ) -> None:
        """Every contract type can be enforced at boundaries."""
        validate_outbound("TaskSpanContract", valid_task_span_payload)
        validate_outbound("HandoffContract", valid_handoff_payload)
        validate_outbound("ArtifactIntent", valid_artifact_intent_payload)
        validate_outbound("GateResult", valid_gate_result_payload)

    def test_inbound_blocks_extra_fields(self, valid_task_span_payload: dict) -> None:
        payload = {**valid_task_span_payload, "extra": True}
        with pytest.raises(BoundaryEnforcementError):
            validate_inbound("TaskSpanContract", payload)


# ============================================================================
# PART 4 — Phase gate tests (Day 4)
# ============================================================================


class TestChecksumChain:
    """Tests for checksum chain integrity gate."""

    def test_all_match(self) -> None:
        result = check_checksum_chain(
            gate_id="g-c1",
            task_id="T-3",
            expected_checksums={"source": "sha256:aaa", "manifest": "sha256:bbb"},
            actual_checksums={"source": "sha256:aaa", "manifest": "sha256:bbb"},
        )
        assert result.result == GateOutcome.PASS
        assert result.blocking is False

    def test_mismatch_detected(self) -> None:
        result = check_checksum_chain(
            gate_id="g-c2",
            task_id="T-3",
            expected_checksums={"source": "sha256:aaa"},
            actual_checksums={"source": "sha256:DIFFERENT"},
        )
        assert result.result == GateOutcome.FAIL
        assert result.blocking is True
        assert "mismatch" in result.reason.lower()

    def test_missing_checksum_detected(self) -> None:
        result = check_checksum_chain(
            gate_id="g-c3",
            task_id="T-3",
            expected_checksums={"source": "sha256:aaa", "manifest": "sha256:bbb"},
            actual_checksums={"source": "sha256:aaa"},
        )
        assert result.result == GateOutcome.FAIL
        assert "missing" in result.reason.lower()

    def test_non_blocking_option(self) -> None:
        result = check_checksum_chain(
            gate_id="g-c4",
            task_id="T-3",
            expected_checksums={"source": "sha256:aaa"},
            actual_checksums={"source": "sha256:DIFFERENT"},
            blocking=False,
        )
        assert result.result == GateOutcome.FAIL
        assert result.blocking is False


class TestMappingCompleteness:
    """Tests for artifact-task mapping completeness gate."""

    def test_all_mapped(self) -> None:
        result = check_mapping_completeness(
            gate_id="g-m1",
            task_id="T-3",
            artifact_ids=["art-1", "art-2"],
            task_mapping={"art-1": "T-10", "art-2": "T-11"},
        )
        assert result.result == GateOutcome.PASS

    def test_unmapped_artifact(self) -> None:
        result = check_mapping_completeness(
            gate_id="g-m2",
            task_id="T-3",
            artifact_ids=["art-1", "art-2", "art-3"],
            task_mapping={"art-1": "T-10"},
        )
        assert result.result == GateOutcome.FAIL
        assert result.blocking is True
        assert "art-2" in result.reason
        assert "art-3" in result.reason

    def test_empty_artifact_list_passes(self) -> None:
        result = check_mapping_completeness(
            gate_id="g-m3",
            task_id="T-3",
            artifact_ids=[],
            task_mapping={},
        )
        assert result.result == GateOutcome.PASS


class TestGapParity:
    """Tests for gap/feature parity gate."""

    def test_perfect_parity(self) -> None:
        result = check_gap_parity(
            gate_id="g-p1",
            task_id="T-4",
            gap_ids=["g1", "g2", "g3"],
            feature_ids=["g1", "g2", "g3"],
        )
        assert result.result == GateOutcome.PASS

    def test_missing_features(self) -> None:
        result = check_gap_parity(
            gate_id="g-p2",
            task_id="T-4",
            gap_ids=["g1", "g2", "g3"],
            feature_ids=["g1"],
        )
        assert result.result == GateOutcome.FAIL
        assert "gap" in result.reason.lower()

    def test_orphan_features(self) -> None:
        result = check_gap_parity(
            gate_id="g-p3",
            task_id="T-4",
            gap_ids=["g1"],
            feature_ids=["g1", "g2"],
        )
        assert result.result == GateOutcome.FAIL
        assert "orphan" in result.reason.lower() or "feature" in result.reason.lower()

    def test_empty_sets_pass(self) -> None:
        result = check_gap_parity(
            gate_id="g-p4",
            task_id="T-4",
            gap_ids=[],
            feature_ids=[],
        )
        assert result.result == GateOutcome.PASS


class TestGateChecker:
    """Tests for the GateChecker convenience class."""

    def test_all_pass(self) -> None:
        checker = GateChecker(trace_id="trace-test")
        checker.check_checksum_chain(
            gate_id="c1",
            task_id="T-1",
            expected_checksums={"src": "x"},
            actual_checksums={"src": "x"},
        )
        checker.check_mapping_completeness(
            gate_id="m1",
            task_id="T-1",
            artifact_ids=["a"],
            task_mapping={"a": "t"},
        )
        checker.check_gap_parity(
            gate_id="p1",
            task_id="T-1",
            gap_ids=["g"],
            feature_ids=["g"],
        )
        assert checker.all_passed
        assert not checker.has_blocking_failure
        assert checker.summary()["total_gates"] == 3

    def test_blocking_failure_detected(self) -> None:
        checker = GateChecker(trace_id="trace-test")
        checker.check_checksum_chain(
            gate_id="c1",
            task_id="T-1",
            expected_checksums={"src": "x"},
            actual_checksums={"src": "WRONG"},
        )
        assert checker.has_blocking_failure
        assert len(checker.blocking_failures) == 1
        assert not checker.all_passed

    def test_summary_structure(self) -> None:
        checker = GateChecker()
        checker.check_checksum_chain(
            gate_id="c1",
            task_id="T-1",
            expected_checksums={"a": "1"},
            actual_checksums={"a": "1"},
        )
        s = checker.summary()
        assert "total_gates" in s
        assert "passed" in s
        assert "failed" in s
        assert "blocking_failures" in s
        assert "all_passed" in s
        assert "gate_ids" in s

    def test_gate_result_is_valid_pydantic_model(self) -> None:
        """Every GateResult returned by gate functions is a valid Pydantic model."""
        result = check_checksum_chain(
            gate_id="g-val",
            task_id="T-5",
            expected_checksums={"a": "1"},
            actual_checksums={"a": "1"},
        )
        assert isinstance(result, GateResult)
        # Serialize excluding None values (JSON schema does not allow null for optional string fields)
        payload = result.model_dump(mode="json", exclude_none=True)
        report = validate_payload("GateResult", payload)
        assert report.is_valid, f"GateResult failed JSON schema: {report.errors}"

    def test_failed_gate_result_passes_schema(self) -> None:
        """A failed GateResult also conforms to the JSON schema."""
        result = check_checksum_chain(
            gate_id="g-val2",
            task_id="T-5",
            expected_checksums={"a": "1"},
            actual_checksums={"a": "WRONG"},
        )
        payload = result.model_dump(mode="json", exclude_none=True)
        report = validate_payload("GateResult", payload)
        assert report.is_valid, f"Failed GateResult failed JSON schema: {report.errors}"
