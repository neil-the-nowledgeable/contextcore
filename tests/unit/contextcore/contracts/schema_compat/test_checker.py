"""Tests for the compatibility checker."""

from __future__ import annotations

import pytest

from contextcore.contracts.schema_compat.checker import CompatibilityChecker
from contextcore.contracts.schema_compat.schema import (
    FieldMapping,
    SchemaCompatibilitySpec,
)
from contextcore.contracts.types import CompatibilityLevel, ConstraintSeverity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(**kwargs) -> SchemaCompatibilitySpec:
    """Build a spec with sensible defaults."""
    defaults = {"schema_version": "0.1.0"}
    defaults.update(kwargs)
    return SchemaCompatibilitySpec(**defaults)


def _make_mapping(**kwargs) -> FieldMapping:
    """Build a mapping with sensible defaults."""
    defaults = {
        "source_service": "tracker",
        "source_field": "task.status",
        "target_service": "exporter",
        "target_field": "status",
    }
    defaults.update(kwargs)
    return FieldMapping(**defaults)


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------


class TestStructuralCheck:
    def test_field_present_and_correct_type(self):
        spec = _make_spec(mappings=[_make_mapping(source_type="str")])
        checker = CompatibilityChecker(spec)
        result = checker.check_structural(
            "tracker", "exporter", {"task": {"status": "in_progress"}}
        )
        assert result.compatible is True
        assert len(result.field_results) == 1
        assert result.field_results[0].compatible is True

    def test_field_missing(self):
        spec = _make_spec(
            mappings=[_make_mapping(severity="blocking")]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_structural(
            "tracker", "exporter", {"task": {}}
        )
        assert result.compatible is False
        assert result.field_results[0].drift_type == "missing_field"

    def test_field_missing_warning_still_compatible(self):
        spec = _make_spec(
            mappings=[_make_mapping(severity="warning")]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_structural(
            "tracker", "exporter", {"task": {}}
        )
        assert result.compatible is True
        assert len(result.drift_details) == 1

    def test_type_mismatch(self):
        spec = _make_spec(
            mappings=[_make_mapping(source_type="int", severity="blocking")]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_structural(
            "tracker", "exporter", {"task": {"status": "string_value"}}
        )
        assert result.compatible is False
        assert result.field_results[0].drift_type == "type_mismatch"

    def test_type_mismatch_warning(self):
        spec = _make_spec(
            mappings=[_make_mapping(source_type="int", severity="warning")]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_structural(
            "tracker", "exporter", {"task": {"status": "oops"}}
        )
        assert result.compatible is True
        assert result.field_results[0].drift_type == "type_mismatch"

    def test_no_mappings_returns_compatible(self):
        spec = _make_spec(mappings=[])
        checker = CompatibilityChecker(spec)
        result = checker.check_structural("tracker", "exporter", {"anything": 1})
        assert result.compatible is True
        assert result.field_results == []


# ---------------------------------------------------------------------------
# Semantic checks
# ---------------------------------------------------------------------------


class TestSemanticCheck:
    def test_value_in_source_values(self):
        spec = _make_spec(
            mappings=[_make_mapping(source_values=["todo", "in_progress", "done"])]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_semantic(
            "tracker", "exporter", {"task": {"status": "in_progress"}}
        )
        assert result.compatible is True

    def test_value_outside_source_values(self):
        spec = _make_spec(
            mappings=[
                _make_mapping(
                    source_values=["todo", "done"],
                    severity="blocking",
                )
            ]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_semantic(
            "tracker", "exporter", {"task": {"status": "unknown"}}
        )
        assert result.compatible is False
        assert result.field_results[0].drift_type == "value_outside_set"

    def test_value_has_mapping(self):
        spec = _make_spec(
            mappings=[
                _make_mapping(
                    mapping={"todo": "pending", "done": "complete"},
                )
            ]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_semantic(
            "tracker", "exporter", {"task": {"status": "todo"}}
        )
        assert result.compatible is True

    def test_unmapped_value(self):
        spec = _make_spec(
            mappings=[
                _make_mapping(
                    mapping={"todo": "pending"},
                    severity="blocking",
                )
            ]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_semantic(
            "tracker", "exporter", {"task": {"status": "unknown"}}
        )
        assert result.compatible is False
        assert result.field_results[0].drift_type == "unmapped_value"

    def test_unmapped_value_warning_compatible(self):
        spec = _make_spec(
            mappings=[
                _make_mapping(
                    mapping={"todo": "pending"},
                    severity="warning",
                )
            ]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_semantic(
            "tracker", "exporter", {"task": {"status": "unknown"}}
        )
        assert result.compatible is True
        assert len(result.drift_details) == 1

    def test_missing_field_semantic(self):
        spec = _make_spec(
            mappings=[_make_mapping(severity="blocking")]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_semantic(
            "tracker", "exporter", {}
        )
        assert result.compatible is False
        assert result.field_results[0].drift_type == "missing_field"

    def test_type_mismatch_semantic(self):
        spec = _make_spec(
            mappings=[_make_mapping(source_type="int", severity="blocking")]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_semantic(
            "tracker", "exporter", {"task": {"status": "not_int"}}
        )
        assert result.compatible is False
        assert result.field_results[0].drift_type == "type_mismatch"

    def test_no_source_values_no_mapping_passes(self):
        """Field present, correct type, no value constraints → pass."""
        spec = _make_spec(mappings=[_make_mapping()])
        checker = CompatibilityChecker(spec)
        result = checker.check_semantic(
            "tracker", "exporter", {"task": {"status": "anything"}}
        )
        assert result.compatible is True

    def test_level_in_result(self):
        spec = _make_spec(mappings=[])
        checker = CompatibilityChecker(spec)
        result = checker.check_semantic("tracker", "exporter", {})
        assert result.level == CompatibilityLevel.SEMANTIC


# ---------------------------------------------------------------------------
# Dot-path resolution
# ---------------------------------------------------------------------------


class TestDotPathResolution:
    def test_nested_field(self):
        spec = _make_spec(
            mappings=[
                _make_mapping(source_field="order.details.status")
            ]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_structural(
            "tracker",
            "exporter",
            {"order": {"details": {"status": "shipped"}}},
        )
        assert result.compatible is True

    def test_missing_intermediate(self):
        spec = _make_spec(
            mappings=[
                _make_mapping(source_field="order.details.status", severity="blocking")
            ]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_structural(
            "tracker", "exporter", {"order": {}}
        )
        assert result.compatible is False


# ---------------------------------------------------------------------------
# find_mapping
# ---------------------------------------------------------------------------


class TestFindMapping:
    def test_returns_correct_mapping(self):
        m1 = _make_mapping(source_field="task.status")
        m2 = _make_mapping(source_field="task.type")
        spec = _make_spec(mappings=[m1, m2])
        checker = CompatibilityChecker(spec)

        found = checker.find_mapping("tracker", "exporter", "task.type")
        assert found is not None
        assert found.source_field == "task.type"

    def test_returns_none_for_unknown(self):
        spec = _make_spec(mappings=[_make_mapping()])
        checker = CompatibilityChecker(spec)
        assert checker.find_mapping("tracker", "exporter", "nonexistent") is None

    def test_returns_none_for_wrong_services(self):
        spec = _make_spec(mappings=[_make_mapping()])
        checker = CompatibilityChecker(spec)
        assert checker.find_mapping("wrong", "exporter", "task.status") is None


# ---------------------------------------------------------------------------
# check() dispatch
# ---------------------------------------------------------------------------


class TestCheckDispatch:
    def test_structural_level(self):
        spec = _make_spec(mappings=[_make_mapping()])
        checker = CompatibilityChecker(spec)
        result = checker.check(
            "tracker", "exporter", {"task": {"status": "x"}}, level="structural"
        )
        assert result.level == CompatibilityLevel.STRUCTURAL

    def test_semantic_level(self):
        spec = _make_spec(mappings=[_make_mapping()])
        checker = CompatibilityChecker(spec)
        result = checker.check(
            "tracker", "exporter", {"task": {"status": "x"}}, level="semantic"
        )
        assert result.level == CompatibilityLevel.SEMANTIC

    def test_invalid_level_raises(self):
        spec = _make_spec(mappings=[])
        checker = CompatibilityChecker(spec)
        with pytest.raises(ValueError):
            checker.check("a", "b", {}, level="invalid")


# ---------------------------------------------------------------------------
# Multiple mappings
# ---------------------------------------------------------------------------


class TestMultipleMappings:
    def test_multiple_mappings_same_services(self):
        spec = _make_spec(
            mappings=[
                _make_mapping(source_field="task.status"),
                _make_mapping(source_field="task.type"),
            ]
        )
        checker = CompatibilityChecker(spec)
        result = checker.check_structural(
            "tracker",
            "exporter",
            {"task": {"status": "done", "type": "story"}},
        )
        assert result.compatible is True
        assert len(result.field_results) == 2
