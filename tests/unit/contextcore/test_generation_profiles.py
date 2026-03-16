"""Tests for generation profile filtering (REQ-GP-100 through REQ-GP-401)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from contextcore.models.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestMetadata,
    ArtifactPriority,
    ArtifactSpec,
    ArtifactStatus,
    ArtifactType,
    CoverageSummary,
    ExportProvenance,
    GenerationProfile,
    INTEGRITY_TYPES,
    OBSERVABILITY_TYPES,
    ONBOARDING_TYPES,
    PROFILE_INCLUDED_TYPES,
    SOURCE_TYPES,
    filter_artifacts_by_profile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_artifact(art_type: ArtifactType, art_id: str | None = None) -> ArtifactSpec:
    return ArtifactSpec(
        id=art_id or f"test-{art_type.value}",
        type=art_type,
        name=f"Test {art_type.value}",
        target="test-svc",
        priority=ArtifactPriority.REQUIRED,
        status=ArtifactStatus.NEEDED,
    )


def _make_mixed_artifacts() -> list[ArtifactSpec]:
    """One artifact from each category."""
    return [
        _make_artifact(ArtifactType.DASHBOARD),            # observability
        _make_artifact(ArtifactType.PROMETHEUS_RULE),       # observability
        _make_artifact(ArtifactType.DOCKERFILE),            # source
        _make_artifact(ArtifactType.CI_WORKFLOW),           # source
        _make_artifact(ArtifactType.CAPABILITY_INDEX),      # onboarding
        _make_artifact(ArtifactType.PROVENANCE),            # integrity
    ]


# ---------------------------------------------------------------------------
# Phase 1 tests
# ---------------------------------------------------------------------------

class TestGenerationProfileEnum:
    def test_profile_enum_values(self):
        assert set(GenerationProfile) == {
            GenerationProfile.SOURCE,
            GenerationProfile.OBSERVABILITY,
            GenerationProfile.FULL,
        }

    def test_profile_from_string(self):
        assert GenerationProfile("source") == GenerationProfile.SOURCE
        assert GenerationProfile("observability") == GenerationProfile.OBSERVABILITY
        assert GenerationProfile("full") == GenerationProfile.FULL


class TestFilterArtifactsByProfile:
    def test_full_profile_returns_all(self):
        artifacts = _make_mixed_artifacts()
        result = filter_artifacts_by_profile(artifacts, GenerationProfile.FULL)
        assert result is artifacts  # identity — no copy for full
        assert len(result) == 6

    def test_source_profile_excludes_observability(self):
        artifacts = _make_mixed_artifacts()
        result = filter_artifacts_by_profile(artifacts, GenerationProfile.SOURCE)
        result_types = {a.type for a in result}
        # Should have source + onboarding + integrity, NOT observability
        assert ArtifactType.DOCKERFILE in result_types
        assert ArtifactType.CI_WORKFLOW in result_types
        assert ArtifactType.CAPABILITY_INDEX in result_types
        assert ArtifactType.PROVENANCE in result_types
        assert ArtifactType.DASHBOARD not in result_types
        assert ArtifactType.PROMETHEUS_RULE not in result_types
        assert len(result) == 4

    def test_observability_profile_excludes_source(self):
        artifacts = _make_mixed_artifacts()
        result = filter_artifacts_by_profile(artifacts, GenerationProfile.OBSERVABILITY)
        result_types = {a.type for a in result}
        assert ArtifactType.DASHBOARD in result_types
        assert ArtifactType.PROMETHEUS_RULE in result_types
        assert ArtifactType.CAPABILITY_INDEX in result_types
        assert ArtifactType.PROVENANCE in result_types
        assert ArtifactType.DOCKERFILE not in result_types
        assert ArtifactType.CI_WORKFLOW not in result_types
        assert len(result) == 4

    def test_empty_list(self):
        assert filter_artifacts_by_profile([], GenerationProfile.SOURCE) == []

    def test_profile_included_types_completeness(self):
        """FULL profile includes all known types."""
        all_types = SOURCE_TYPES | OBSERVABILITY_TYPES | ONBOARDING_TYPES | INTEGRITY_TYPES
        assert PROFILE_INCLUDED_TYPES[GenerationProfile.FULL] == all_types


class TestProvenanceRecordsProfile:
    def test_provenance_serializes_generation_profile(self):
        prov = ExportProvenance(
            source_path="/tmp/test.yaml",
            generation_profile="source",
        )
        data = prov.model_dump(by_alias=True, exclude_none=True, mode="json")
        assert data["generationProfile"] == "source"

    def test_provenance_generation_profile_defaults_none(self):
        prov = ExportProvenance(source_path="/tmp/test.yaml")
        assert prov.generation_profile is None


class TestCoverageRecalcAfterFilter:
    def test_coverage_matches_filtered_list(self):
        artifacts = _make_mixed_artifacts()
        manifest = ArtifactManifest(
            metadata=ArtifactManifestMetadata(
                generated_from="test.yaml",
                project_id="test",
            ),
            artifacts=artifacts,
        )
        # Filter to source profile
        manifest.artifacts = filter_artifacts_by_profile(
            manifest.artifacts, GenerationProfile.SOURCE
        )
        coverage = manifest.compute_coverage()
        # All remaining are REQUIRED + NEEDED
        assert coverage.total_required == len(manifest.artifacts)
        assert coverage.total_existing == 0


# ---------------------------------------------------------------------------
# Phase 2 tests (onboarding metadata)
# ---------------------------------------------------------------------------

class TestOnboardingProfileScoping:
    """Tests for build_onboarding_metadata with generation_profile parameter."""

    def _build_minimal_manifest(self) -> ArtifactManifest:
        return ArtifactManifest(
            metadata=ArtifactManifestMetadata(
                generated_from="test.yaml",
                project_id="test-project",
            ),
            artifacts=[
                _make_artifact(ArtifactType.DOCKERFILE),
                _make_artifact(ArtifactType.CAPABILITY_INDEX),
            ],
            coverage=CoverageSummary(),
        )

    def _call_build(self, generation_profile: str = "full") -> dict:
        from contextcore.utils.onboarding import build_onboarding_metadata

        manifest = self._build_minimal_manifest()
        return build_onboarding_metadata(
            artifact_manifest=manifest,
            artifact_manifest_path="test-artifact-manifest.yaml",
            project_context_path="test-crd.yaml",
            generation_profile=generation_profile,
        )

    def test_source_omits_derivation_rules(self):
        result = self._call_build("source")
        assert result["derivation_rules"] == {"_omitted": "profile=source"}

    def test_source_omits_artifact_dep_graph(self):
        result = self._call_build("source")
        assert result["artifact_dependency_graph"] == {"_omitted": "profile=source"}

    def test_source_omits_parameter_resolvability(self):
        result = self._call_build("source")
        assert result["parameter_resolvability"] == {"_omitted": "profile=source"}
        assert result["parameter_resolvability_summary"] == {"_omitted": "profile=source"}

    def test_source_omits_expected_output_contracts(self):
        result = self._call_build("source")
        assert result["expected_output_contracts"] == {"_omitted": "profile=source"}

    def test_source_omits_design_calibration_hints(self):
        result = self._call_build("source")
        assert result["design_calibration_hints"] == {"_omitted": "profile=source"}

    def test_source_keeps_service_metadata_key(self):
        """service_metadata section is always included when provided."""
        from contextcore.utils.onboarding import build_onboarding_metadata

        manifest = self._build_minimal_manifest()
        result = build_onboarding_metadata(
            artifact_manifest=manifest,
            artifact_manifest_path="test.yaml",
            project_context_path="test-crd.yaml",
            generation_profile="source",
            service_metadata={"svc1": {"transport_protocol": "http"}},
        )
        assert result.get("service_metadata") == {"svc1": {"transport_protocol": "http"}}

    def test_source_keeps_semantic_conventions(self):
        result = self._call_build("source")
        # semantic_conventions is always in result (may be None for minimal manifest)
        assert "semantic_conventions" in result

    def test_full_backward_compat(self):
        """Full profile does not produce _omitted markers."""
        result = self._call_build("full")
        for key in ["derivation_rules", "artifact_dependency_graph",
                     "parameter_resolvability", "expected_output_contracts",
                     "design_calibration_hints"]:
            val = result.get(key)
            if val is not None:
                assert "_omitted" not in val, f"{key} should not have _omitted marker for full profile"

    def test_schema_version_bumped_for_source(self):
        result = self._call_build("source")
        assert result["schema_version"] == "1.1.0"

    def test_schema_version_bumped_for_observability(self):
        result = self._call_build("observability")
        assert result["schema_version"] == "1.1.0"

    def test_schema_version_unchanged_for_full(self):
        result = self._call_build("full")
        assert result["schema_version"] == "1.0.0"

    def test_profile_indicator_present(self):
        for prof in ("source", "observability", "full"):
            result = self._call_build(prof)
            assert result["generation_profile"] == prof
