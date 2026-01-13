"""
Tests for ContextCore Pydantic models.
"""

import pytest
from pydantic import ValidationError

from contextcore.models import (
    BusinessSpec,
    Criticality,
    DashboardPlacement,
    ObservabilitySpec,
    ProjectContextSpec,
    ProjectSpec,
    RequirementsSpec,
    TargetSpec,
    derive_observability,
)


class TestProjectSpec:
    """Test ProjectSpec model."""

    def test_valid_project_spec(self):
        """Valid project spec should parse correctly."""
        spec = ProjectSpec(id="my-project", epic="EPIC-42", tasks=["TASK-1", "TASK-2"])
        assert spec.id == "my-project"
        assert spec.epic == "EPIC-42"
        assert spec.tasks == ["TASK-1", "TASK-2"]

    def test_minimal_project_spec(self):
        """Minimal project spec with only id."""
        spec = ProjectSpec(id="my-project")
        assert spec.id == "my-project"
        assert spec.epic is None
        assert spec.tasks == []

    def test_project_spec_requires_id(self):
        """Project spec without id should fail."""
        with pytest.raises(ValidationError):
            ProjectSpec()


class TestBusinessSpec:
    """Test BusinessSpec model."""

    def test_valid_business_spec(self):
        """Valid business spec should parse correctly."""
        spec = BusinessSpec(
            criticality=Criticality.CRITICAL,
            value="revenue-primary",
            owner="commerce-team",
        )
        assert spec.criticality == Criticality.CRITICAL
        assert spec.owner == "commerce-team"

    def test_invalid_criticality(self):
        """Invalid criticality should fail."""
        with pytest.raises(ValidationError):
            BusinessSpec(criticality="super-critical")


class TestRequirementsSpec:
    """Test RequirementsSpec model."""

    def test_valid_requirements(self):
        """Valid requirements should parse correctly."""
        spec = RequirementsSpec(
            availability="99.95",
            latency_p99="200ms",
            error_budget="0.05",
        )
        assert spec.availability == "99.95"
        assert spec.latency_p99 == "200ms"


class TestTargetSpec:
    """Test TargetSpec model."""

    def test_valid_target(self):
        """Valid target should parse correctly."""
        spec = TargetSpec(kind="Deployment", name="my-app")
        assert spec.kind.value == "Deployment"
        assert spec.name == "my-app"

    def test_invalid_kind(self):
        """Invalid kind should fail."""
        with pytest.raises(ValidationError):
            TargetSpec(kind="Pod", name="my-pod")  # Pod not in allowed kinds


class TestProjectContextSpec:
    """Test full ProjectContextSpec model."""

    def test_valid_full_spec(self, sample_project_context_spec):
        """Full valid spec should parse correctly."""
        spec = ProjectContextSpec(**sample_project_context_spec)
        assert spec.project.id == "commerce-platform"
        assert spec.business.criticality == Criticality.CRITICAL
        assert len(spec.targets) == 2
        assert len(spec.risks) == 1

    def test_minimal_spec(self, minimal_project_context_spec):
        """Minimal spec should parse correctly."""
        spec = ProjectContextSpec(**minimal_project_context_spec)
        assert spec.project.id == "minimal-project"
        assert len(spec.targets) == 1
        assert spec.business is None
        assert spec.design is None

    def test_requires_targets(self):
        """Spec without targets should fail."""
        with pytest.raises(ValidationError):
            ProjectContextSpec(project={"id": "my-project"}, targets=[])


class TestDeriveObservability:
    """Test observability derivation logic."""

    def test_derive_from_critical(self):
        """Critical services get highest observability."""
        spec = ProjectContextSpec(
            project=ProjectSpec(id="test"),
            business=BusinessSpec(criticality=Criticality.CRITICAL),
            targets=[TargetSpec(kind="Deployment", name="app")],
        )
        obs = derive_observability(spec)
        assert obs.trace_sampling == 1.0
        assert obs.metrics_interval == "10s"

    def test_derive_from_low(self):
        """Low criticality services get minimal observability."""
        spec = ProjectContextSpec(
            project=ProjectSpec(id="test"),
            business=BusinessSpec(criticality=Criticality.LOW),
            targets=[TargetSpec(kind="Deployment", name="app")],
        )
        obs = derive_observability(spec)
        assert obs.trace_sampling == 0.01
        assert obs.metrics_interval == "120s"

    def test_derive_dashboard_from_revenue(self):
        """Revenue-primary services get featured dashboards."""
        spec = ProjectContextSpec(
            project=ProjectSpec(id="test"),
            business=BusinessSpec(value="revenue-primary"),
            targets=[TargetSpec(kind="Deployment", name="app")],
        )
        obs = derive_observability(spec)
        assert obs.dashboard_placement == DashboardPlacement.FEATURED

    def test_explicit_overrides_derived(self):
        """Explicit observability config should not be overwritten."""
        spec = ProjectContextSpec(
            project=ProjectSpec(id="test"),
            business=BusinessSpec(criticality=Criticality.CRITICAL),
            targets=[TargetSpec(kind="Deployment", name="app")],
            observability=ObservabilitySpec(trace_sampling=0.5),
        )
        obs = derive_observability(spec)
        # Explicit value preserved
        assert obs.trace_sampling == 0.5
        # Derived value still applied where not explicit
        assert obs.metrics_interval == "10s"
