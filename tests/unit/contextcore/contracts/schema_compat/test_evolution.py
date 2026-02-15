"""Tests for the schema evolution tracker."""

from __future__ import annotations

import pytest

from contextcore.contracts.schema_compat.evolution import (
    CHANGE_ADD_ENUM_VALUE,
    CHANGE_ADD_FIELD,
    CHANGE_CHANGE_FIELD_TYPE,
    CHANGE_DEPRECATE_FIELD,
    CHANGE_MAKE_REQUIRED,
    CHANGE_REMOVE_ENUM_VALUE,
    CHANGE_REMOVE_FIELD,
    EvolutionTracker,
)
from contextcore.contracts.schema_compat.schema import (
    SchemaCompatibilitySpec,
    SchemaEvolutionRule,
    SchemaVersion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(**kwargs) -> SchemaCompatibilitySpec:
    defaults = {"schema_version": "0.1.0"}
    defaults.update(kwargs)
    return SchemaCompatibilitySpec(**defaults)


def _make_version(
    service: str = "tracker",
    version: str = "1.0.0",
    fields: dict | None = None,
    enums: dict | None = None,
    required_fields: list | None = None,
    deprecated_fields: list | None = None,
) -> SchemaVersion:
    return SchemaVersion(
        service=service,
        version=version,
        fields=fields or {"task_id": "str", "status": "str"},
        enums=enums or {},
        required_fields=required_fields or [],
        deprecated_fields=deprecated_fields or [],
    )


# ---------------------------------------------------------------------------
# compare_versions
# ---------------------------------------------------------------------------


class TestCompareVersions:
    def test_detect_add_field(self):
        old = _make_version(fields={"task_id": "str"})
        new = _make_version(version="2.0.0", fields={"task_id": "str", "priority": "str"})
        spec = _make_spec()
        tracker = EvolutionTracker(spec)

        changes = tracker.compare_versions(old, new)
        assert any(c["type"] == CHANGE_ADD_FIELD and c["field"] == "priority" for c in changes)

    def test_detect_remove_field(self):
        old = _make_version(fields={"task_id": "str", "status": "str"})
        new = _make_version(version="2.0.0", fields={"task_id": "str"})
        spec = _make_spec()
        tracker = EvolutionTracker(spec)

        changes = tracker.compare_versions(old, new)
        assert any(c["type"] == CHANGE_REMOVE_FIELD and c["field"] == "status" for c in changes)

    def test_detect_change_field_type(self):
        old = _make_version(fields={"task_id": "str", "count": "str"})
        new = _make_version(version="2.0.0", fields={"task_id": "str", "count": "int"})
        spec = _make_spec()
        tracker = EvolutionTracker(spec)

        changes = tracker.compare_versions(old, new)
        type_changes = [c for c in changes if c["type"] == CHANGE_CHANGE_FIELD_TYPE]
        assert len(type_changes) == 1
        assert type_changes[0]["old"] == "str"
        assert type_changes[0]["new"] == "int"

    def test_detect_add_enum_value(self):
        old = _make_version(enums={"status": ["todo", "done"]})
        new = _make_version(version="2.0.0", enums={"status": ["todo", "in_progress", "done"]})
        spec = _make_spec()
        tracker = EvolutionTracker(spec)

        changes = tracker.compare_versions(old, new)
        assert any(
            c["type"] == CHANGE_ADD_ENUM_VALUE and c["new"] == "in_progress"
            for c in changes
        )

    def test_detect_remove_enum_value(self):
        old = _make_version(enums={"status": ["todo", "in_progress", "done"]})
        new = _make_version(version="2.0.0", enums={"status": ["todo", "done"]})
        spec = _make_spec()
        tracker = EvolutionTracker(spec)

        changes = tracker.compare_versions(old, new)
        assert any(
            c["type"] == CHANGE_REMOVE_ENUM_VALUE and c["old"] == "in_progress"
            for c in changes
        )

    def test_detect_make_required(self):
        old = _make_version(required_fields=[])
        new = _make_version(version="2.0.0", required_fields=["task_id"])
        spec = _make_spec()
        tracker = EvolutionTracker(spec)

        changes = tracker.compare_versions(old, new)
        assert any(c["type"] == CHANGE_MAKE_REQUIRED and c["field"] == "task_id" for c in changes)

    def test_detect_deprecate_field(self):
        old = _make_version(deprecated_fields=[])
        new = _make_version(version="2.0.0", deprecated_fields=["status"])
        spec = _make_spec()
        tracker = EvolutionTracker(spec)

        changes = tracker.compare_versions(old, new)
        assert any(
            c["type"] == CHANGE_DEPRECATE_FIELD and c["field"] == "status"
            for c in changes
        )

    def test_no_changes(self):
        v = _make_version()
        spec = _make_spec()
        tracker = EvolutionTracker(spec)

        changes = tracker.compare_versions(v, v)
        assert changes == []


# ---------------------------------------------------------------------------
# Policy: additive_only
# ---------------------------------------------------------------------------


class TestPolicyAdditiveOnly:
    def test_allows_add_field(self):
        rule = SchemaEvolutionRule(
            rule_id="r1", scope="tracker", policy="additive_only"
        )
        spec = _make_spec(evolution_rules=[rule])
        tracker = EvolutionTracker(spec)

        old = _make_version(fields={"task_id": "str"})
        new = _make_version(version="2.0.0", fields={"task_id": "str", "priority": "str"})

        result = tracker.check_evolution(old, new)
        assert result.compatible is True
        assert len(result.compatible_changes) == 1

    def test_blocks_remove_field(self):
        rule = SchemaEvolutionRule(
            rule_id="r1", scope="tracker", policy="additive_only"
        )
        spec = _make_spec(evolution_rules=[rule])
        tracker = EvolutionTracker(spec)

        old = _make_version(fields={"task_id": "str", "status": "str"})
        new = _make_version(version="2.0.0", fields={"task_id": "str"})

        result = tracker.check_evolution(old, new)
        assert result.compatible is False
        assert len(result.breaking_changes) == 1


# ---------------------------------------------------------------------------
# Policy: backward_compatible
# ---------------------------------------------------------------------------


class TestPolicyBackwardCompatible:
    def test_allows_deprecation(self):
        rule = SchemaEvolutionRule(
            rule_id="r1", scope="tracker", policy="backward_compatible"
        )
        spec = _make_spec(evolution_rules=[rule])
        tracker = EvolutionTracker(spec)

        old = _make_version()
        new = _make_version(version="2.0.0", deprecated_fields=["status"])

        result = tracker.check_evolution(old, new)
        assert result.compatible is True

    def test_blocks_type_change(self):
        rule = SchemaEvolutionRule(
            rule_id="r1", scope="tracker", policy="backward_compatible"
        )
        spec = _make_spec(evolution_rules=[rule])
        tracker = EvolutionTracker(spec)

        old = _make_version(fields={"task_id": "str", "count": "str"})
        new = _make_version(version="2.0.0", fields={"task_id": "str", "count": "int"})

        result = tracker.check_evolution(old, new)
        assert result.compatible is False


# ---------------------------------------------------------------------------
# Policy: full
# ---------------------------------------------------------------------------


class TestPolicyFull:
    def test_allows_everything(self):
        rule = SchemaEvolutionRule(
            rule_id="r1", scope="tracker", policy="full"
        )
        spec = _make_spec(evolution_rules=[rule])
        tracker = EvolutionTracker(spec)

        old = _make_version(
            fields={"task_id": "str", "status": "str"},
            enums={"status": ["todo", "done"]},
        )
        new = _make_version(
            version="2.0.0",
            fields={"task_id": "int"},  # type change + removal
            enums={"status": ["active"]},  # enum removal
        )

        result = tracker.check_evolution(old, new)
        assert result.compatible is True


# ---------------------------------------------------------------------------
# allowed_changes / forbidden_changes overrides
# ---------------------------------------------------------------------------


class TestOverrides:
    def test_forbidden_changes_override(self):
        rule = SchemaEvolutionRule(
            rule_id="r1",
            scope="tracker",
            policy="full",
            forbidden_changes=[CHANGE_REMOVE_FIELD],
        )
        spec = _make_spec(evolution_rules=[rule])
        tracker = EvolutionTracker(spec)

        old = _make_version(fields={"task_id": "str", "status": "str"})
        new = _make_version(version="2.0.0", fields={"task_id": "str"})

        result = tracker.check_evolution(old, new)
        assert result.compatible is False

    def test_allowed_changes_override(self):
        rule = SchemaEvolutionRule(
            rule_id="r1",
            scope="tracker",
            policy="additive_only",
            allowed_changes=[CHANGE_DEPRECATE_FIELD],
        )
        spec = _make_spec(evolution_rules=[rule])
        tracker = EvolutionTracker(spec)

        old = _make_version()
        new = _make_version(version="2.0.0", deprecated_fields=["status"])

        result = tracker.check_evolution(old, new)
        assert result.compatible is True


# ---------------------------------------------------------------------------
# No applicable rule
# ---------------------------------------------------------------------------


class TestNoRule:
    def test_no_rule_allows_all(self):
        spec = _make_spec(evolution_rules=[])
        tracker = EvolutionTracker(spec)

        old = _make_version(fields={"task_id": "str", "status": "str"})
        new = _make_version(version="2.0.0", fields={"task_id": "int"})

        result = tracker.check_evolution(old, new)
        assert result.compatible is True
        assert result.applicable_rule is None


# ---------------------------------------------------------------------------
# Result message
# ---------------------------------------------------------------------------


class TestResultMessage:
    def test_no_changes_message(self):
        spec = _make_spec()
        tracker = EvolutionTracker(spec)
        v = _make_version()

        result = tracker.check_evolution(v, v)
        assert "No changes" in result.message

    def test_breaking_changes_message(self):
        rule = SchemaEvolutionRule(
            rule_id="r1", scope="tracker", policy="additive_only"
        )
        spec = _make_spec(evolution_rules=[rule])
        tracker = EvolutionTracker(spec)

        old = _make_version(fields={"task_id": "str", "status": "str"})
        new = _make_version(version="2.0.0", fields={"task_id": "str"})

        result = tracker.check_evolution(old, new)
        assert "breaking" in result.message
