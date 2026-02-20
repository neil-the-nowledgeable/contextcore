"""
Tests for capability discoverability — prevents the false ceiling regression.

The 2026-02-18 investigation found that an AI agent concluded with HIGH
confidence that ContextCore only produces observability artifacts. The
defense-in-depth plan (Layers 1-6) ensures the complete artifact taxonomy
is discoverable from multiple independent paths.

These tests validate that:
1. The capability index has scope_boundaries with all 3 categories
2. The artifact_type_registry capability exists with correct triggers
3. The schema describes all categories
4. No unqualified "observability artifact" language exists in key files
5. Cross-references connect the artifact taxonomy across docs
"""

import json
from pathlib import Path

import yaml
import pytest

REPO_ROOT = Path(__file__).parent.parent
CAPABILITY_INDEX_PATH = REPO_ROOT / "docs" / "capability-index" / "contextcore.agent.yaml"
SCHEMA_PATH = REPO_ROOT / "schemas" / "contracts" / "artifact-intent.schema.json"
BENEFITS_PATH = REPO_ROOT / "docs" / "capability-index" / "contextcore.benefits.yaml"
USER_PATH = REPO_ROOT / "docs" / "capability-index" / "contextcore.user.yaml"
PIPELINE_REQ_PATH = REPO_ROOT / "docs" / "reference" / "pipeline-requirements-onboarding.md"


@pytest.fixture(scope="module")
def capability_manifest() -> dict:
    """Load the capability index YAML."""
    with open(CAPABILITY_INDEX_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def schema() -> dict:
    """Load the artifact-intent JSON schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


class TestScopeBoundaries:
    """Layer 3: scope_boundaries section in capability index."""

    def test_scope_boundaries_present(self, capability_manifest: dict) -> None:
        """scope_boundaries section must exist."""
        assert "scope_boundaries" in capability_manifest

    def test_has_three_artifact_categories(self, capability_manifest: dict) -> None:
        """scope_boundaries must define at least 3 artifact categories."""
        boundaries = capability_manifest["scope_boundaries"]
        categories = boundaries.get("artifact_categories", [])
        assert len(categories) >= 3

    def test_category_names(self, capability_manifest: dict) -> None:
        """Must have observability, onboarding, and integrity categories."""
        boundaries = capability_manifest["scope_boundaries"]
        category_names = {c["category"] for c in boundaries["artifact_categories"]}
        assert "observability" in category_names
        assert "onboarding" in category_names
        assert "integrity" in category_names

    def test_observability_has_8_types(self, capability_manifest: dict) -> None:
        categories = capability_manifest["scope_boundaries"]["artifact_categories"]
        obs = next(c for c in categories if c["category"] == "observability")
        assert obs["count"] == 8

    def test_onboarding_has_4_types(self, capability_manifest: dict) -> None:
        categories = capability_manifest["scope_boundaries"]["artifact_categories"]
        onb = next(c for c in categories if c["category"] == "onboarding")
        assert onb["count"] == 4

    def test_integrity_has_2_types(self, capability_manifest: dict) -> None:
        categories = capability_manifest["scope_boundaries"]["artifact_categories"]
        intg = next(c for c in categories if c["category"] == "integrity")
        assert intg["count"] == 2

    def test_pipeline_stages_present(self, capability_manifest: dict) -> None:
        boundaries = capability_manifest["scope_boundaries"]
        assert "pipeline_stages" in boundaries
        stages = boundaries["pipeline_stages"]
        assert len(stages) >= 5

    def test_explicit_non_scope_present(self, capability_manifest: dict) -> None:
        boundaries = capability_manifest["scope_boundaries"]
        assert "explicit_non_scope" in boundaries


class TestArtifactTypeRegistry:
    """Layer 3: artifact_type_registry capability."""

    def test_registry_capability_exists(self, capability_manifest: dict) -> None:
        """contextcore.meta.artifact_type_registry must exist."""
        cap_ids = [c["capability_id"] for c in capability_manifest["capabilities"]]
        assert "contextcore.meta.artifact_type_registry" in cap_ids

    def test_registry_has_triggers(self, capability_manifest: dict) -> None:
        registry = next(
            c for c in capability_manifest["capabilities"]
            if c["capability_id"] == "contextcore.meta.artifact_type_registry"
        )
        triggers = registry.get("triggers", [])
        assert len(triggers) >= 5
        trigger_set = set(triggers)
        assert "artifact types" in trigger_set
        assert "artifact categories" in trigger_set

    def test_registry_description_mentions_all_categories(self, capability_manifest: dict) -> None:
        registry = next(
            c for c in capability_manifest["capabilities"]
            if c["capability_id"] == "contextcore.meta.artifact_type_registry"
        )
        agent_desc = registry["description"]["agent"].lower()
        assert "observability" in agent_desc
        assert "onboarding" in agent_desc
        assert "source" in agent_desc
        assert "integrity" in agent_desc

    def test_registry_description_mentions_19_types(self, capability_manifest: dict) -> None:
        registry = next(
            c for c in capability_manifest["capabilities"]
            if c["capability_id"] == "contextcore.meta.artifact_type_registry"
        )
        agent_desc = registry["description"]["agent"].lower()
        assert "19" in agent_desc


class TestSchemaDiscoverability:
    """Layer 2: artifact-intent.schema.json."""

    def test_schema_description_not_observability_only(self, schema: dict) -> None:
        desc = schema["description"].lower()
        if "observability" in desc:
            assert "onboarding" in desc
            assert "integrity" in desc

    def test_schema_has_artifact_category_field(self, schema: dict) -> None:
        assert "artifact_category" in schema["properties"]

    def test_artifact_category_enum_values(self, schema: dict) -> None:
        cat_field = schema["properties"]["artifact_category"]
        assert set(cat_field["enum"]) == {"observability", "onboarding", "integrity"}


class TestNoFalseCeiling:
    """Layer 4+6: No unqualified 'observability artifact' language."""

    def test_benefits_no_unqualified_observability_artifact(self) -> None:
        """benefits.yaml must not say 'observability artifact' without qualification."""
        content = BENEFITS_PATH.read_text()
        # Find all occurrences of "observability artifact"
        lower = content.lower()
        idx = 0
        while True:
            idx = lower.find("observability artifact", idx)
            if idx == -1:
                break
            # Check context: should be qualified with mention of other categories
            context = lower[max(0, idx - 200):idx + 200]
            assert "onboarding" in context or "integrity" in context or "also" in context, (
                f"Unqualified 'observability artifact' at position {idx} in benefits.yaml"
            )
            idx += 1

    def test_user_yaml_no_unqualified_observability_artifact(self) -> None:
        """user.yaml must not say 'observability artifact' without qualification."""
        content = USER_PATH.read_text()
        lower = content.lower()
        idx = 0
        while True:
            idx = lower.find("observability artifact", idx)
            if idx == -1:
                break
            context = lower[max(0, idx - 200):idx + 200]
            assert "onboarding" in context or "integrity" in context or "also" in context, (
                f"Unqualified 'observability artifact' at position {idx} in user.yaml"
            )
            idx += 1


class TestCrossReferences:
    """Layer 5: Cross-reference connectivity."""

    def test_pipeline_requirements_has_inbound_refs(self) -> None:
        """pipeline-requirements-onboarding.md must be referenced by >= 5 files."""
        count = 0
        for path in REPO_ROOT.rglob("*"):
            if path.suffix in (".py", ".md", ".json", ".yaml", ".yml"):
                if path == PIPELINE_REQ_PATH:
                    continue
                try:
                    if "pipeline-requirements-onboarding" in path.read_text():
                        count += 1
                except (UnicodeDecodeError, PermissionError):
                    continue
        assert count >= 5, (
            f"pipeline-requirements-onboarding.md has only {count} inbound references (need >= 5)"
        )

    def test_pipeline_requirements_has_referenced_by_section(self) -> None:
        """pipeline-requirements-onboarding.md must have a Referenced By section."""
        content = PIPELINE_REQ_PATH.read_text()
        assert "## Referenced By" in content


class TestAgentScopeSearchSimulation:
    """Layer 6: Simulate an agent's search path for artifact scope."""

    def test_agent_finds_complete_taxonomy_in_3_hops(self, capability_manifest: dict) -> None:
        """Simulate an agent searching for 'artifact type'.

        This test follows the search path that triggered the 2026-02-18
        discoverability failure and verifies the complete taxonomy is
        discoverable within 3 hops.
        """
        # Hop 1: Search triggers for "artifact type"
        matches = []
        for cap in capability_manifest["capabilities"]:
            triggers = cap.get("triggers", [])
            for trigger in triggers:
                if "artifact type" in trigger.lower():
                    matches.append(cap)
                    break
        assert len(matches) >= 1, "No capability found for 'artifact type' trigger"

        # Hop 2: Read the matched capability's description
        registry = next(
            (c for c in matches
             if c["capability_id"] == "contextcore.meta.artifact_type_registry"),
            matches[0],
        )
        desc = registry["description"]["agent"].lower()

        # Hop 3: Verify description mentions all 3 categories
        assert "observability" in desc, "Agent description missing 'observability'"
        assert "onboarding" in desc, "Agent description missing 'onboarding'"
        assert "integrity" in desc, "Agent description missing 'integrity'"

        # Verify scope_boundaries are also reachable
        assert "scope_boundaries" in capability_manifest
        categories = capability_manifest["scope_boundaries"]["artifact_categories"]
        category_names = {c["category"] for c in categories}
        assert {"observability", "onboarding", "integrity"}.issubset(category_names)
