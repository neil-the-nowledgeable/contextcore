"""
Tests for ArtifactType enum completeness and category classification.

Prevents regression of the 2026-02-18 discoverability failure where only
observability artifact types were visible. Validates that the enum, category
sets, conventions, and onboarding dicts all cover all artifact types.
"""

from contextcore.models.artifact_manifest import (
    ArtifactType,
    OBSERVABILITY_TYPES,
    ONBOARDING_TYPES,
    INTEGRITY_TYPES,
)
from contextcore.utils.artifact_conventions import ARTIFACT_OUTPUT_CONVENTIONS
from contextcore.utils.onboarding import (
    ARTIFACT_PARAMETER_SOURCES,
    ARTIFACT_EXAMPLE_OUTPUTS,
    EXPECTED_OUTPUT_CONTRACTS,
    ARTIFACT_PARAMETER_SCHEMA,
)
from contextcore.utils.pipeline_requirements import PIPELINE_INNATE_REQUIREMENTS


class TestArtifactTypeEnum:
    """Verify ArtifactType enum is complete."""

    def test_enum_has_at_least_14_members(self) -> None:
        """ArtifactType must have >= 14 members (REQ-CID-018)."""
        assert len(ArtifactType) >= 14

    def test_enum_has_observability_types(self) -> None:
        """All 8 observability types must be present."""
        expected = {
            "dashboard", "prometheus_rule", "loki_rule", "slo_definition",
            "service_monitor", "notification_policy", "runbook", "alert_template",
        }
        actual = {t.value for t in ArtifactType}
        assert expected.issubset(actual)

    def test_enum_has_onboarding_types(self) -> None:
        """All 4 onboarding types must be present."""
        expected = {
            "capability_index", "agent_card", "mcp_tools", "onboarding_metadata",
        }
        actual = {t.value for t in ArtifactType}
        assert expected.issubset(actual)

    def test_enum_has_integrity_types(self) -> None:
        """Both integrity types must be present."""
        expected = {"provenance", "ingestion-traceability"}
        actual = {t.value for t in ArtifactType}
        assert expected.issubset(actual)


class TestCategorySets:
    """Verify category frozensets are complete and non-overlapping."""

    def test_observability_count(self) -> None:
        assert len(OBSERVABILITY_TYPES) == 8

    def test_onboarding_count(self) -> None:
        assert len(ONBOARDING_TYPES) == 4

    def test_integrity_count(self) -> None:
        assert len(INTEGRITY_TYPES) == 2

    def test_categories_cover_all_types(self) -> None:
        """Union of category sets must equal the full enum."""
        all_categorized = OBSERVABILITY_TYPES | ONBOARDING_TYPES | INTEGRITY_TYPES
        assert all_categorized == set(ArtifactType)

    def test_categories_are_disjoint(self) -> None:
        """No type should appear in more than one category."""
        assert not (OBSERVABILITY_TYPES & ONBOARDING_TYPES)
        assert not (OBSERVABILITY_TYPES & INTEGRITY_TYPES)
        assert not (ONBOARDING_TYPES & INTEGRITY_TYPES)


class TestConventionsCoverage:
    """Verify ARTIFACT_OUTPUT_CONVENTIONS covers all types."""

    def test_all_types_have_conventions(self) -> None:
        for t in ArtifactType:
            assert t.value in ARTIFACT_OUTPUT_CONVENTIONS, (
                f"{t.value} missing from ARTIFACT_OUTPUT_CONVENTIONS"
            )

    def test_conventions_have_required_keys(self) -> None:
        for t in ArtifactType:
            conv = ARTIFACT_OUTPUT_CONVENTIONS[t.value]
            assert "output_ext" in conv, f"{t.value} missing output_ext"
            assert "output_path" in conv, f"{t.value} missing output_path"


class TestOnboardingDictsCoverage:
    """Verify onboarding dicts cover all types."""

    def test_parameter_sources_coverage(self) -> None:
        for t in ArtifactType:
            assert t.value in ARTIFACT_PARAMETER_SOURCES, (
                f"{t.value} missing from ARTIFACT_PARAMETER_SOURCES"
            )

    def test_example_outputs_coverage(self) -> None:
        for t in ArtifactType:
            assert t.value in ARTIFACT_EXAMPLE_OUTPUTS, (
                f"{t.value} missing from ARTIFACT_EXAMPLE_OUTPUTS"
            )

    def test_output_contracts_coverage(self) -> None:
        for t in ArtifactType:
            assert t.value in EXPECTED_OUTPUT_CONTRACTS, (
                f"{t.value} missing from EXPECTED_OUTPUT_CONTRACTS"
            )

    def test_parameter_schema_coverage(self) -> None:
        for t in ArtifactType:
            assert t.value in ARTIFACT_PARAMETER_SCHEMA, (
                f"{t.value} missing from ARTIFACT_PARAMETER_SCHEMA"
            )


class TestPipelineRequirementsMatch:
    """Verify pipeline_requirements values match enum."""

    def test_all_satisfied_by_artifact_values_valid(self) -> None:
        valid = {t.value for t in ArtifactType}
        for req in PIPELINE_INNATE_REQUIREMENTS:
            art = req["satisfied_by_artifact"]
            assert art in valid, (
                f'{req["id"]}: satisfied_by_artifact "{art}" not in ArtifactType enum'
            )


class TestAntiFalseCeiling:
    """Verify no false ceiling language in code artifacts."""

    def test_enum_docstring_not_observability_only(self) -> None:
        """ArtifactType docstring must NOT say 'observability' without qualification."""
        doc = ArtifactType.__doc__ or ""
        if "observability" in doc.lower():
            assert "onboarding" in doc.lower(), (
                "ArtifactType docstring mentions observability without onboarding"
            )
            assert "integrity" in doc.lower(), (
                "ArtifactType docstring mentions observability without integrity"
            )
