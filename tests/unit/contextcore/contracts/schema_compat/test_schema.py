"""Tests for schema compatibility Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contextcore.contracts.schema_compat.schema import (
    CompatibilityResult,
    EvolutionCheckResult,
    FieldCompatibilityDetail,
    FieldMapping,
    SchemaCompatibilitySpec,
    SchemaEvolutionRule,
    SchemaVersion,
)
from contextcore.contracts.types import CompatibilityLevel, ConstraintSeverity


# ---------------------------------------------------------------------------
# FieldMapping
# ---------------------------------------------------------------------------


class TestFieldMapping:
    def test_minimal_construction(self):
        m = FieldMapping(
            source_service="tracker",
            source_field="task.status",
            target_service="exporter",
            target_field="task_status",
        )
        assert m.source_type == "str"
        assert m.target_type == "str"
        assert m.severity == ConstraintSeverity.WARNING
        assert m.bidirectional is False
        assert m.mapping is None

    def test_full_construction(self):
        m = FieldMapping(
            source_service="tracker",
            source_field="task.status",
            source_values=["todo", "in_progress", "done"],
            target_service="exporter",
            target_field="status",
            target_values=["pending", "active", "complete"],
            mapping={"todo": "pending", "in_progress": "active", "done": "complete"},
            severity="blocking",
            description="Task status mapping",
            bidirectional=True,
        )
        assert m.bidirectional is True
        assert len(m.mapping) == 3

    def test_bidirectional_injective_passes(self):
        """Bijective mapping (unique values) should be accepted."""
        m = FieldMapping(
            source_service="a",
            source_field="x",
            target_service="b",
            target_field="y",
            mapping={"a": "1", "b": "2", "c": "3"},
            bidirectional=True,
        )
        assert m.bidirectional is True

    def test_bidirectional_non_injective_rejected(self):
        """Duplicate values in bidirectional mapping should raise."""
        with pytest.raises(ValidationError, match="injective"):
            FieldMapping(
                source_service="a",
                source_field="x",
                target_service="b",
                target_field="y",
                mapping={"a": "1", "b": "1"},  # Duplicate value
                bidirectional=True,
            )

    def test_non_bidirectional_allows_duplicates(self):
        """Non-bidirectional mapping allows duplicate values."""
        m = FieldMapping(
            source_service="a",
            source_field="x",
            target_service="b",
            target_field="y",
            mapping={"a": "1", "b": "1"},
            bidirectional=False,
        )
        assert m.mapping == {"a": "1", "b": "1"}

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            FieldMapping(
                source_service="a",
                source_field="x",
                target_service="b",
                target_field="y",
                unknown_field="bad",
            )


# ---------------------------------------------------------------------------
# SchemaEvolutionRule
# ---------------------------------------------------------------------------


class TestSchemaEvolutionRule:
    def test_valid_policies(self):
        for policy in ("additive_only", "backward_compatible", "full"):
            rule = SchemaEvolutionRule(
                rule_id=f"r-{policy}",
                scope="tracker",
                policy=policy,
            )
            assert rule.policy == policy

    def test_invalid_policy_rejected(self):
        with pytest.raises(ValidationError):
            SchemaEvolutionRule(
                rule_id="bad",
                scope="tracker",
                policy="yolo",
            )

    def test_defaults(self):
        rule = SchemaEvolutionRule(
            rule_id="r1",
            scope="tracker",
            policy="additive_only",
        )
        assert rule.allowed_changes == []
        assert rule.forbidden_changes == []
        assert rule.description is None


# ---------------------------------------------------------------------------
# SchemaVersion
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    def test_minimal(self):
        v = SchemaVersion(
            service="tracker",
            version="1.0.0",
            fields={"task_id": "str", "status": "str"},
        )
        assert v.enums == {}
        assert v.required_fields == []
        assert v.deprecated_fields == []

    def test_full(self):
        v = SchemaVersion(
            service="tracker",
            version="2.0.0",
            fields={"task_id": "str", "status": "str", "priority": "str"},
            enums={"status": ["todo", "done"], "priority": ["high", "low"]},
            required_fields=["task_id"],
            deprecated_fields=["priority"],
            timestamp="2026-02-15T00:00:00Z",
        )
        assert len(v.enums) == 2
        assert v.timestamp is not None


# ---------------------------------------------------------------------------
# SchemaCompatibilitySpec
# ---------------------------------------------------------------------------


class TestSchemaCompatibilitySpec:
    def test_minimal(self):
        spec = SchemaCompatibilitySpec(schema_version="0.1.0")
        assert spec.contract_type == "schema_compatibility"
        assert spec.mappings == []
        assert spec.evolution_rules == []
        assert spec.versions == []

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            SchemaCompatibilitySpec(
                schema_version="0.1.0",
                unknown_key="bad",
            )

    def test_wrong_contract_type_rejected(self):
        with pytest.raises(ValidationError):
            SchemaCompatibilitySpec(
                schema_version="0.1.0",
                contract_type="propagation",
            )


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class TestCompatibilityResult:
    def test_defaults(self):
        r = CompatibilityResult(
            compatible=True,
            level=CompatibilityLevel.STRUCTURAL,
            source_service="a",
            target_service="b",
        )
        assert r.field_results == []
        assert r.drift_details == []
        assert r.severity == ConstraintSeverity.WARNING
        assert r.message == ""


class TestFieldCompatibilityDetail:
    def test_defaults(self):
        d = FieldCompatibilityDetail(
            source_field="x",
            target_field="y",
            compatible=True,
        )
        assert d.drift_type is None
        assert d.detail == ""


class TestEvolutionCheckResult:
    def test_defaults(self):
        r = EvolutionCheckResult(
            compatible=True,
            service="tracker",
            old_version="1.0.0",
            new_version="1.1.0",
        )
        assert r.total_changes == 0
        assert r.breaking_changes == []
        assert r.compatible_changes == []
        assert r.applicable_rule is None
