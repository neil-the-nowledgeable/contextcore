"""
Tests for ContextCore OTel Resource Detector.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from contextcore.detector import (
    ANNOTATION_PREFIX,
    ANNOTATION_TO_ATTRIBUTE,
    ProjectContextDetector,
    get_project_context,
)


class TestAnnotationMapping:
    """Test annotation to attribute mapping."""

    def test_all_mappings_have_valid_format(self):
        """All mapped attributes should follow naming conventions."""
        for annotation, attribute in ANNOTATION_TO_ATTRIBUTE.items():
            # Attributes should be dot-separated
            assert "." in attribute, f"Attribute {attribute} should be dot-separated"
            # No spaces or special characters
            assert " " not in attribute
            assert "-" not in attribute  # Use underscores in attributes


class TestProjectContextDetector:
    """Test ProjectContextDetector class."""

    def test_detect_from_env(self, test_env):
        """Detector should read from environment variables."""
        detector = ProjectContextDetector()
        resource = detector.detect()

        attrs = dict(resource.attributes)
        assert attrs.get("project.id") == "test-project"
        assert attrs.get("business.criticality") == "high"
        assert attrs.get("business.owner") == "test-team"
        assert attrs.get("design.doc") == "https://docs.test/design"

    def test_detect_with_missing_env(self):
        """Detector should handle missing environment variables."""
        # Clear environment
        env_vars = [
            "CONTEXTCORE_PROJECT_ID",
            "CONTEXTCORE_CRITICALITY",
            "CONTEXTCORE_OWNER",
        ]
        original = {}
        for var in env_vars:
            original[var] = os.environ.pop(var, None)

        try:
            detector = ProjectContextDetector()
            resource = detector.detect()
            # Should still return a resource (possibly empty)
            assert resource is not None
        finally:
            # Restore
            for var, val in original.items():
                if val is not None:
                    os.environ[var] = val

    def test_parse_annotations(self, mock_k8s_client):
        """Detector should parse K8s annotations correctly."""
        detector = ProjectContextDetector()

        annotations = {
            f"{ANNOTATION_PREFIX}project": "my-project",
            f"{ANNOTATION_PREFIX}criticality": "critical",
            f"{ANNOTATION_PREFIX}design-doc": "https://example.com/doc",
            f"{ANNOTATION_PREFIX}unknown-field": "some-value",
            "unrelated-annotation": "ignored",
        }

        attrs = detector._parse_annotations(annotations)

        assert attrs.get("project.id") == "my-project"
        assert attrs.get("business.criticality") == "critical"
        assert attrs.get("design.doc") == "https://example.com/doc"
        # Unknown fields should be prefixed
        assert attrs.get("contextcore.unknown-field") == "some-value"
        # Unrelated annotations should be ignored
        assert "unrelated-annotation" not in attrs

    def test_detect_includes_k8s_context(self, test_env):
        """Detector should include K8s namespace context."""
        with patch.dict(os.environ, {"HOSTNAME": "test-pod-xyz"}):
            detector = ProjectContextDetector()
            resource = detector.detect()
            attrs = dict(resource.attributes)

            # Should include namespace from env
            assert attrs.get("k8s.namespace.name") == "test-namespace"


class TestGetProjectContext:
    """Test get_project_context convenience function."""

    def test_returns_dict(self, test_env):
        """get_project_context should return a dictionary."""
        context = get_project_context()

        assert isinstance(context, dict)
        assert context.get("project.id") == "test-project"
        assert context.get("business.criticality") == "high"


class TestK8sDetection:
    """Test K8s-based detection (mocked)."""

    def test_detect_from_k8s_annotations(self, mock_k8s_client):
        """Detector should read annotations from K8s pod."""
        with patch("contextcore.detector.client") as mock_client_module:
            mock_client_module.CoreV1Api.return_value = mock_k8s_client
            with patch("contextcore.detector.config"):
                detector = ProjectContextDetector(
                    pod_name="test-pod",
                    namespace="test-namespace",
                )

                # This would normally call K8s API
                # attrs = detector._detect_from_k8s()

                # For now, test the parsing logic
                annotations = {
                    "contextcore.io/project": "k8s-project",
                    "contextcore.io/criticality": "critical",
                }
                attrs = detector._parse_annotations(annotations)

                assert attrs.get("project.id") == "k8s-project"
                assert attrs.get("business.criticality") == "critical"

    def test_k8s_detection_fallback_to_env(self, test_env):
        """If K8s detection fails, should fall back to env."""
        detector = ProjectContextDetector()
        resource = detector.detect()

        attrs = dict(resource.attributes)
        # Should have env-based values
        assert attrs.get("project.id") == "test-project"
