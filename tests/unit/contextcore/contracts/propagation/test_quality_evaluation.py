"""Tests for QualitySpec and EvaluationSpec defense-in-depth extensions."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contextcore.contracts.propagation.schema import (
    ContextContract,
    EvaluationSpec,
    FieldSpec,
    PhaseContract,
    PhaseEntryContract,
    QualitySpec,
)
from contextcore.contracts.propagation.tracker import (
    EvaluationResult,
    FieldProvenance,
    PropagationTracker,
    PROVENANCE_KEY,
)
from contextcore.contracts.propagation.validator import (
    BoundaryValidator,
    ContractValidationResult,
    QualityViolation,
)
from contextcore.contracts.types import (
    ConstraintSeverity,
    EvaluationPolicy,
    PropagationStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def validator():
    return BoundaryValidator()


@pytest.fixture
def tracker():
    return PropagationTracker()


def _make_contract(entry_required: list[FieldSpec] | None = None) -> ContextContract:
    """Create a minimal contract with one phase."""
    return ContextContract(
        schema_version="0.1.0",
        pipeline_id="test",
        phases={
            "implement": PhaseContract(
                entry=PhaseEntryContract(
                    required=entry_required or [],
                ),
            ),
        },
    )


def _long_doc(lines: int = 100) -> str:
    """Generate a multi-line design document."""
    return "\n".join(f"## Section {i}\nContent for section {i}." for i in range(lines))


# ===========================================================================
# Schema tests
# ===========================================================================


class TestQualitySpecSchema:
    def test_quality_spec_round_trip(self):
        qs = QualitySpec(metric="line_count", threshold=50.0)
        d = qs.model_dump()
        assert d["metric"] == "line_count"
        assert d["threshold"] == 50.0
        assert d["on_below"] == "warning"
        roundtripped = QualitySpec.model_validate(d)
        assert roundtripped.metric == "line_count"

    def test_evaluation_spec_round_trip(self):
        es = EvaluationSpec(
            policy=EvaluationPolicy.SCORE_THRESHOLD,
            threshold=75.0,
        )
        d = es.model_dump()
        assert d["policy"] == "score_threshold"
        assert d["threshold"] == 75.0
        roundtripped = EvaluationSpec.model_validate(d)
        assert roundtripped.policy == EvaluationPolicy.SCORE_THRESHOLD

    def test_field_spec_with_quality(self):
        fs = FieldSpec(
            name="design_document",
            quality=QualitySpec(metric="line_count", threshold=50.0),
        )
        assert fs.quality is not None
        assert fs.quality.metric == "line_count"

    def test_field_spec_with_evaluation(self):
        fs = FieldSpec(
            name="design_document",
            evaluation=EvaluationSpec(
                policy=EvaluationPolicy.HUMAN_OR_MODEL,
            ),
        )
        assert fs.evaluation is not None
        assert fs.evaluation.policy == EvaluationPolicy.HUMAN_OR_MODEL

    def test_quality_spec_rejects_unknown_keys(self):
        with pytest.raises(ValidationError):
            QualitySpec(metric="line_count", threshold=50.0, bogus="nope")

    def test_evaluation_spec_rejects_unknown_keys(self):
        with pytest.raises(ValidationError):
            EvaluationSpec(
                policy=EvaluationPolicy.ANY_EVALUATOR,
                bogus="nope",
            )


# ===========================================================================
# Quality validation tests
# ===========================================================================


class TestQualityValidation:
    def test_quality_check_passes_above_threshold(self, validator):
        doc = _long_doc(100)
        contract = _make_contract([
            FieldSpec(
                name="design_document",
                quality=QualitySpec(metric="line_count", threshold=50.0),
            ),
        ])
        context = {"design_document": doc}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].status == PropagationStatus.PROPAGATED

    def test_quality_check_fails_below_threshold(self, validator):
        contract = _make_contract([
            FieldSpec(
                name="design_document",
                quality=QualitySpec(
                    metric="line_count",
                    threshold=50.0,
                    on_below=ConstraintSeverity.BLOCKING,
                ),
            ),
        ])
        context = {"design_document": "stub\nonly two lines"}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is False
        assert result.field_results[0].status == PropagationStatus.FAILED
        assert len(result.field_results[0].quality_violations) == 1

    def test_quality_warning_below_threshold(self, validator):
        contract = _make_contract([
            FieldSpec(
                name="design_document",
                quality=QualitySpec(
                    metric="line_count",
                    threshold=50.0,
                    on_below=ConstraintSeverity.WARNING,
                ),
            ),
        ])
        context = {"design_document": "stub"}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True  # WARNING doesn't block
        assert len(result.field_results[0].quality_violations) == 1
        assert result.field_results[0].quality_violations[0].severity == ConstraintSeverity.WARNING

    def test_quality_blocking_below_threshold(self, validator):
        contract = _make_contract([
            FieldSpec(
                name="design_document",
                quality=QualitySpec(
                    metric="line_count",
                    threshold=50.0,
                    on_below=ConstraintSeverity.BLOCKING,
                ),
            ),
        ])
        context = {"design_document": "stub"}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is False
        assert "design_document" in result.blocking_failures

    def test_quality_char_count_metric(self, validator):
        contract = _make_contract([
            FieldSpec(
                name="doc",
                quality=QualitySpec(metric="char_count", threshold=100.0),
            ),
        ])
        context = {"doc": "x" * 200}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].quality_violations == []

    def test_quality_section_count_metric(self, validator):
        doc = "## Intro\ntext\n## Design\ntext\n## Impl\ntext"
        contract = _make_contract([
            FieldSpec(
                name="doc",
                quality=QualitySpec(metric="section_count", threshold=2.0),
            ),
        ])
        context = {"doc": doc}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True

    def test_quality_length_metric_on_list(self, validator):
        contract = _make_contract([
            FieldSpec(
                name="tasks",
                quality=QualitySpec(metric="length", threshold=3.0),
            ),
        ])
        context = {"tasks": [1, 2, 3, 4, 5]}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True

    def test_quality_unknown_metric_ignored(self, validator):
        contract = _make_contract([
            FieldSpec(
                name="doc",
                quality=QualitySpec(
                    metric="nonexistent_metric",
                    threshold=10.0,
                    on_below=ConstraintSeverity.BLOCKING,
                ),
            ),
        ])
        context = {"doc": "some text"}
        result = validator.validate_entry("implement", context, contract)
        # Unknown metric is skipped gracefully — field passes
        assert result.passed is True
        assert result.field_results[0].quality_violations == []


# ===========================================================================
# Evaluation gate tests
# ===========================================================================


class TestEvaluationGate:
    def test_evaluation_gate_satisfied(self, validator, tracker):
        contract = _make_contract([
            FieldSpec(
                name="design_document",
                evaluation=EvaluationSpec(
                    policy=EvaluationPolicy.ANY_EVALUATOR,
                ),
            ),
        ])
        context = {"design_document": "full design content here"}
        tracker.stamp(context, "design", "design_document", "full design content here")
        tracker.stamp_evaluation(context, "design_document", "model:claude-sonnet", score=90.0)
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].evaluation_satisfied is True

    def test_evaluation_gate_unevaluated(self, validator):
        contract = _make_contract([
            FieldSpec(
                name="design_document",
                evaluation=EvaluationSpec(
                    policy=EvaluationPolicy.ANY_EVALUATOR,
                    on_unevaluated=ConstraintSeverity.BLOCKING,
                ),
            ),
        ])
        context = {"design_document": "content without evaluation stamp"}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is False
        assert result.field_results[0].evaluation_satisfied is False

    def test_evaluation_score_threshold_pass(self, validator, tracker):
        contract = _make_contract([
            FieldSpec(
                name="doc",
                evaluation=EvaluationSpec(
                    policy=EvaluationPolicy.SCORE_THRESHOLD,
                    threshold=75.0,
                ),
            ),
        ])
        context = {"doc": "design content"}
        tracker.stamp(context, "design", "doc", "design content")
        tracker.stamp_evaluation(context, "doc", "model:claude", score=85.0)
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].evaluation_satisfied is True

    def test_evaluation_score_threshold_fail(self, validator, tracker):
        contract = _make_contract([
            FieldSpec(
                name="doc",
                evaluation=EvaluationSpec(
                    policy=EvaluationPolicy.SCORE_THRESHOLD,
                    threshold=75.0,
                    on_below_threshold=ConstraintSeverity.BLOCKING,
                ),
            ),
        ])
        context = {"doc": "design content"}
        tracker.stamp(context, "design", "doc", "design content")
        tracker.stamp_evaluation(context, "doc", "model:claude", score=60.0)
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is False
        assert result.field_results[0].evaluation_satisfied is False

    def test_human_required_policy_with_model(self, validator, tracker):
        contract = _make_contract([
            FieldSpec(
                name="doc",
                evaluation=EvaluationSpec(
                    policy=EvaluationPolicy.HUMAN_REQUIRED,
                    on_unevaluated=ConstraintSeverity.BLOCKING,
                ),
            ),
        ])
        context = {"doc": "content"}
        tracker.stamp(context, "design", "doc", "content")
        tracker.stamp_evaluation(context, "doc", "model:claude", score=95.0)
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is False
        assert result.field_results[0].evaluation_satisfied is False

    def test_stamp_evaluation_creates_provenance(self, tracker):
        context: dict = {}
        result = tracker.stamp_evaluation(context, "doc", "human:reviewer", score=88.0)
        assert isinstance(result, EvaluationResult)
        assert result.field_path == "doc"
        assert result.evaluator == "human:reviewer"
        assert result.score == 88.0
        assert result.timestamp is not None
        prov = tracker.get_provenance(context, "doc")
        assert prov is not None
        assert prov.evaluated_by == "human:reviewer"
        assert prov.evaluation_score == 88.0

    def test_stamp_evaluation_updates_existing(self, tracker):
        context: dict = {}
        tracker.stamp(context, "design", "doc", "content")
        prov_before = tracker.get_provenance(context, "doc")
        assert prov_before is not None
        assert prov_before.evaluated_by is None

        tracker.stamp_evaluation(context, "doc", "model:claude", score=72.0)
        prov_after = tracker.get_provenance(context, "doc")
        assert prov_after is not None
        assert prov_after.origin_phase == "design"  # preserved
        assert prov_after.evaluated_by == "model:claude"
        assert prov_after.evaluation_score == 72.0

    def test_evaluation_result_fields(self, tracker):
        context: dict = {}
        result = tracker.stamp_evaluation(context, "field_a", "human:bob", score=50.0)
        assert result.field_path == "field_a"
        assert result.evaluator == "human:bob"
        assert result.score == 50.0
        assert isinstance(result.timestamp, str)

    def test_evaluation_gate_with_no_eval_spec(self, validator):
        """FieldSpec without evaluation spec leaves evaluation_satisfied as None."""
        contract = _make_contract([
            FieldSpec(name="simple_field"),
        ])
        context = {"simple_field": "value"}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].evaluation_satisfied is None


# ===========================================================================
# Integration tests
# ===========================================================================


class TestIntegration:
    def test_quality_and_evaluation_combined(self, validator, tracker):
        doc = _long_doc(100)
        contract = _make_contract([
            FieldSpec(
                name="design_document",
                quality=QualitySpec(metric="line_count", threshold=50.0),
                evaluation=EvaluationSpec(
                    policy=EvaluationPolicy.SCORE_THRESHOLD,
                    threshold=70.0,
                ),
            ),
        ])
        context = {"design_document": doc}
        tracker.stamp(context, "design", "design_document", doc)
        tracker.stamp_evaluation(context, "design_document", "model:claude", score=85.0)
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].quality_violations == []
        assert result.field_results[0].evaluation_satisfied is True

    def test_contract_validation_aggregates_quality(self, validator):
        contract = _make_contract([
            FieldSpec(
                name="doc_a",
                quality=QualitySpec(
                    metric="line_count",
                    threshold=50.0,
                    on_below=ConstraintSeverity.WARNING,
                ),
            ),
            FieldSpec(
                name="doc_b",
                quality=QualitySpec(
                    metric="char_count",
                    threshold=500.0,
                    on_below=ConstraintSeverity.WARNING,
                ),
            ),
        ])
        context = {"doc_a": "stub", "doc_b": "short"}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True  # both are WARNING
        assert len(result.quality_violations) == 2

    def test_gate_result_includes_quality(self, validator):
        contract = _make_contract([
            FieldSpec(
                name="doc",
                quality=QualitySpec(
                    metric="line_count",
                    threshold=50.0,
                    on_below=ConstraintSeverity.BLOCKING,
                ),
            ),
        ])
        context = {"doc": "stub"}
        result = validator.validate_entry("implement", context, contract)
        gate = result.to_gate_result()
        quality_evidence = [
            e for e in gate["evidence"] if e["type"] == "quality_violation"
        ]
        assert len(quality_evidence) == 1

    def test_backward_compat_field_spec_no_quality(self, validator):
        """FieldSpec without quality/evaluation behaves identically to before."""
        contract = _make_contract([
            FieldSpec(name="tasks", severity=ConstraintSeverity.BLOCKING),
        ])
        context = {"tasks": [1, 2, 3]}
        result = validator.validate_entry("implement", context, contract)
        assert result.passed is True
        assert result.field_results[0].status == PropagationStatus.PROPAGATED
        assert result.field_results[0].quality_violations == []
        assert result.field_results[0].evaluation_satisfied is None
        assert result.quality_violations == []
