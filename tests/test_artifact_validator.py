"""
Tests for artifact_validator post-generation validation.
"""

from contextcore.generators.artifact_validator import (
    validate_artifact,
    validate_artifacts,
)


class TestValidateArtifact:
    """Tests for validate_artifact."""

    def test_empty_content_invalid(self) -> None:
        """Empty or whitespace-only content should be invalid."""
        r = validate_artifact("service_monitor", "", None)
        assert not r.valid
        assert "empty" in r.errors[0].lower()

        r = validate_artifact("service_monitor", "   \n\t  ", None)
        assert not r.valid

    def test_valid_yaml_passes(self) -> None:
        """Valid YAML content for YAML artifact types should pass."""
        r = validate_artifact(
            "service_monitor",
            "apiVersion: v1\nkind: ServiceMonitor\nmetadata:\n  name: test",
            "test-monitor",
        )
        assert r.valid
        assert not r.errors

    def test_invalid_yaml_fails(self) -> None:
        """Invalid YAML should produce parse error."""
        r = validate_artifact("service_monitor", "bad: yaml: [[[", None)
        assert not r.valid
        assert any("YAML parse error" in e for e in r.errors)

    def test_valid_json_passes(self) -> None:
        """Valid JSON for dashboard (JSON artifact type) should pass."""
        r = validate_artifact("dashboard", '{"uid": "test", "panels": []}', None)
        assert r.valid
        assert not r.errors

    def test_invalid_json_fails(self) -> None:
        """Invalid JSON should produce parse error."""
        r = validate_artifact("dashboard", "{invalid json}", None)
        assert not r.valid
        assert any("JSON parse error" in e for e in r.errors)

    def test_unknown_artifact_type_defaults_to_yaml(self) -> None:
        """Unknown artifact types default to .yaml validation."""
        r = validate_artifact("unknown_type", "key: value", None)
        assert r.valid

        r = validate_artifact("unknown_type", "not: valid: [[[", None)
        assert not r.valid
        assert any("YAML parse error" in e for e in r.errors)

    def test_runbook_without_header_warns(self) -> None:
        """Markdown runbook without # header gets warning."""
        r = validate_artifact("runbook", "No header here\n\njust content", None)
        assert r.valid
        assert any("header" in w.lower() for w in r.warnings)

    def test_runbook_with_header_passes(self) -> None:
        """Markdown runbook with # header passes without warning."""
        r = validate_artifact("runbook", "# Incident Runbook\n\nSteps here", None)
        assert r.valid
        assert not any("header" in w.lower() for w in r.warnings)


class TestValidateArtifacts:
    """Tests for validate_artifacts."""

    def test_valid_artifacts_all_pass(self) -> None:
        """Multiple valid artifacts all pass."""
        artifacts = [
            ("service_monitor", "apiVersion: v1\nkind: ServiceMonitor", "sm-1"),
            ("dashboard", '{"panels": []}', "dash-1"),
        ]
        results = validate_artifacts(artifacts)
        assert len(results) == 2
        assert all(r.valid for r in results)

    def test_invalid_tuple_length_fails(self) -> None:
        """Tuple with wrong element count produces error."""
        artifacts = [
            ("service_monitor", "apiVersion: v1", None),  # valid
            ("a", "b"),  # only 2 elements
        ]
        results = validate_artifacts(artifacts)
        assert len(results) == 2
        assert results[0].valid
        assert not results[1].valid
        assert "expected 3 elements" in results[1].errors[0]

    def test_non_tuple_item_fails(self) -> None:
        """Non-tuple/list item produces error."""
        artifacts = [
            ("service_monitor", "apiVersion: v1", None),
            "not a tuple",  # type: ignore[list-item]
        ]
        results = validate_artifacts(artifacts)
        assert len(results) == 2
        assert results[0].valid
        assert not results[1].valid
        assert "expected list or tuple" in results[1].errors[0]

    def test_empty_list_returns_empty(self) -> None:
        """Empty artifacts list returns empty results."""
        results = validate_artifacts([])
        assert results == []
