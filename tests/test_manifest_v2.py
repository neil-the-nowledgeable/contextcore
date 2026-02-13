"""
Tests for Context Manifest v2.0 models, loader, and migration.

This module tests:
- V2-01a: ContextManifestV2 basic structure
- V2-02: AgentGuidanceSpec models and validation
- V2-03: Version-aware loader
- V2-05: v1.1 → v2.0 migration

Run with: python3 -m pytest tests/test_manifest_v2.py -v
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from contextcore.contracts.types import ConstraintSeverity, QuestionStatus, Priority
from contextcore.models.manifest import load_context_manifest, TacticStatus
from contextcore.models.manifest_v2 import (
    AgentGuidanceSpec,
    Constraint,
    ContextManifestV2,
    Focus,
    InsightV2,
    ManifestMetadataV2,
    ManifestState,
    ObjectiveV2,
    Preference,
    Question,
    StrategySpec,
    TacticV2,
)
from contextcore.models.manifest_loader import (
    detect_manifest_version,
    load_manifest,
    load_manifest_from_dict,
    load_manifest_v1,
    load_manifest_v2,
)
from contextcore.models.manifest_migrate import (
    migrate_v1_to_v2,
    migrate_v1_to_v2_model,
    validate_migration,
)


# Helper function to create a minimal valid spec dict
def _make_spec(project_id: str = "test", project_name: str = "Test") -> dict:
    """Create a minimal valid ProjectContextSpec dict."""
    return {
        "project": {"id": project_id, "name": project_name},
        "business": {"criticality": "medium", "owner": "engineering"},
        "targets": [{"kind": "Deployment", "name": f"{project_id}-deployment", "namespace": "default"}],
    }


# =============================================================================
# V2-01a Tests: Basic ContextManifestV2 structure
# =============================================================================


def test_v2_model_basic_structure() -> None:
    """Test that ContextManifestV2 can be instantiated with minimal data."""
    manifest = ContextManifestV2(
        metadata=ManifestMetadataV2(name="test-project"),
        spec=_make_spec("test", "Test Project"),
    )

    assert manifest.api_version == "contextcore.io/v1alpha2"
    assert manifest.kind == "ContextManifest"
    assert manifest.metadata.name == "test-project"
    assert manifest.strategy.objectives == []
    assert manifest.strategy.tactics == []
    assert manifest.guidance.constraints == []
    assert manifest.insights == []


def test_v2_model_with_full_data() -> None:
    """Test ContextManifestV2 with all sections populated."""
    manifest = ContextManifestV2(
        metadata=ManifestMetadataV2(name="full-project"),
        spec=_make_spec("full", "Full Project"),
        strategy=StrategySpec(
            objectives=[
                ObjectiveV2(id="OBJ-001", description="Test objective")
            ],
            tactics=[
                TacticV2(
                    id="TAC-001",
                    description="Test tactic",
                    linked_objectives=["OBJ-001"],
                )
            ],
        ),
        guidance=AgentGuidanceSpec(
            focus=Focus(areas=["reliability", "performance"]),
            constraints=[
                Constraint(
                    id="C-001",
                    rule="Do not modify production configs",
                    severity=ConstraintSeverity.BLOCKING,
                )
            ],
            questions=[
                Question(
                    id="Q-001",
                    question="What is the expected latency?",
                    status=QuestionStatus.OPEN,
                )
            ],
        ),
        insights=[
            InsightV2(
                id="INS-001",
                type="risk",
                summary="Potential bottleneck",
                confidence=0.85,
                source="scanner:perf-analysis",
            )
        ],
    )

    assert len(manifest.strategy.objectives) == 1
    assert len(manifest.strategy.tactics) == 1
    assert len(manifest.guidance.constraints) == 1
    assert len(manifest.guidance.questions) == 1
    assert len(manifest.insights) == 1


# =============================================================================
# V2-02 Tests: AgentGuidanceSpec models
# =============================================================================


def test_guidance_constraint_requires_id_and_rule() -> None:
    """Test that Constraint requires both id and rule."""
    # Valid constraint
    constraint = Constraint(id="C-001", rule="No AWS SDK")
    assert constraint.id == "C-001"
    assert constraint.rule == "No AWS SDK"
    assert constraint.severity == ConstraintSeverity.BLOCKING  # default

    # Missing id should fail
    with pytest.raises(Exception):  # pydantic validation error
        Constraint(rule="No AWS SDK")  # type: ignore

    # Missing rule should fail
    with pytest.raises(Exception):
        Constraint(id="C-001")  # type: ignore


def test_guidance_uses_canonical_enums() -> None:
    """Test that guidance models use canonical enums from contracts/types.py."""
    constraint = Constraint(
        id="C-001",
        rule="Test",
        severity=ConstraintSeverity.WARNING,
    )
    assert constraint.severity == ConstraintSeverity.WARNING

    question = Question(
        id="Q-001",
        question="Test?",
        status=QuestionStatus.ANSWERED,
        priority=Priority.HIGH,
    )
    assert question.status == QuestionStatus.ANSWERED
    assert question.priority == Priority.HIGH


def test_focus_requires_areas_list() -> None:
    """Test that Focus.areas must be a non-empty list."""
    # Valid focus
    focus = Focus(areas=["reliability", "performance"])
    assert isinstance(focus.areas, list)
    assert len(focus.areas) == 2

    # Empty list should fail
    with pytest.raises(Exception):
        Focus(areas=[])


def test_preference_model() -> None:
    """Test Preference model."""
    pref = Preference(
        id="PREF-001",
        description="Use dataclasses over dicts",
        example="@dataclass class Config: ...",
    )
    assert pref.id == "PREF-001"
    assert "dataclasses" in pref.description


def test_question_answer_fields() -> None:
    """Test Question model with answer fields."""
    question = Question(
        id="Q-001",
        question="What is the SLA?",
        status=QuestionStatus.ANSWERED,
        answer="99.9% availability",
        answered_by="agent:claude",
        answered_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    )
    assert question.status == QuestionStatus.ANSWERED
    assert question.answer == "99.9% availability"
    assert question.answered_by == "agent:claude"


# =============================================================================
# V2-03 Tests: Manifest loader
# =============================================================================


def test_loader_returns_v1_for_v1alpha1() -> None:
    """Test that loader returns ContextManifest for v1 manifests."""
    # Use the existing example which is v1.1
    manifest = load_manifest("examples/context_manifest_example.yaml")
    from contextcore.models.manifest import ContextManifest

    assert isinstance(manifest, ContextManifest)


def test_loader_returns_v2_for_v1alpha2() -> None:
    """Test that loader returns ContextManifestV2 for v2 manifests."""
    v2_data = {
        "apiVersion": "contextcore.io/v1alpha2",
        "kind": "ContextManifest",
        "metadata": {"name": "test-v2"},
        "spec": _make_spec("test", "Test"),
    }

    manifest = load_manifest_from_dict(v2_data)
    assert isinstance(manifest, ContextManifestV2)


def test_detect_manifest_version_v1() -> None:
    """Test version detection for v1.1 manifests."""
    v1_data = {"apiVersion": "contextcore.io/v1alpha1", "version": "1.1"}
    assert detect_manifest_version(v1_data) == "v1.1"

    v1_data_legacy = {"version": "1.0"}
    assert detect_manifest_version(v1_data_legacy) == "v1.1"


def test_detect_manifest_version_v2() -> None:
    """Test version detection for v2 manifests."""
    v2_data = {"apiVersion": "contextcore.io/v1alpha2"}
    assert detect_manifest_version(v2_data) == "v2"


def test_load_manifest_v1_rejects_v2() -> None:
    """Test that load_manifest_v1 rejects v2 manifests."""
    v2_data = {
        "apiVersion": "contextcore.io/v1alpha2",
        "kind": "ContextManifest",
        "metadata": {"name": "test-v2"},
        "spec": _make_spec("test", "Test"),
    }

    # Write temp file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(v2_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="Expected v1.1 manifest but got v2"):
            load_manifest_v1(temp_path)
    finally:
        Path(temp_path).unlink()


# =============================================================================
# V2-05 Tests: Migration v1.1 → v2.0
# =============================================================================


def test_migrate_example_yaml_produces_valid_v2() -> None:
    """Test that migrating the example YAML produces a valid v2 manifest."""
    v1 = load_context_manifest("examples/context_manifest_example.yaml")
    v2_dict = migrate_v1_to_v2(v1)

    # Should be parseable as v2
    v2 = ContextManifestV2(**v2_dict)

    # Basic structure checks
    assert v2.api_version == "contextcore.io/v1alpha2"
    assert v2.metadata.name == v1.metadata.name
    assert len(v2.strategy.objectives) == len(v1.objectives)


def test_migrate_preserves_changelog() -> None:
    """Test that migration preserves existing changelog and adds entry."""
    v1 = load_context_manifest("examples/context_manifest_example.yaml")
    original_changelog_len = len(v1.metadata.changelog) if v1.metadata else 0

    v2_dict = migrate_v1_to_v2(v1)
    v2 = ContextManifestV2(**v2_dict)

    # Should have one more entry
    assert len(v2.metadata.changelog) == original_changelog_len + 1

    # Last entry should be the migration entry
    migration_entry = v2.metadata.changelog[-1]
    assert migration_entry.version == "2.0"
    assert "contextcore-migrate" in (migration_entry.actor or "")


def test_migrate_flattens_tactics() -> None:
    """Test that migration flattens tactics from strategy hierarchy."""
    v1 = load_context_manifest("examples/context_manifest_example.yaml")

    # Count total tactics in v1 (nested in strategies)
    v1_tactic_count = sum(len(s.tactics) for s in v1.strategies)

    v2 = migrate_v1_to_v2_model(v1)

    # v2 should have all tactics at top level
    assert len(v2.strategy.tactics) == v1_tactic_count


def test_migrate_creates_empty_guidance() -> None:
    """Test that migration creates empty guidance section."""
    v1 = load_context_manifest("examples/context_manifest_example.yaml")
    v2 = migrate_v1_to_v2_model(v1)

    assert v2.guidance.constraints == []
    assert v2.guidance.preferences == []
    assert v2.guidance.questions == []


def test_migrate_preserves_insights() -> None:
    """Test that migration preserves insights."""
    v1 = load_context_manifest("examples/context_manifest_example.yaml")
    v2 = migrate_v1_to_v2_model(v1)

    assert len(v2.insights) == len(v1.insights)

    # All insights should have IDs
    for insight in v2.insights:
        assert insight.id is not None


def test_validate_migration_reports_issues() -> None:
    """Test that validate_migration reports mismatches."""
    v1 = load_context_manifest("examples/context_manifest_example.yaml")
    v2 = migrate_v1_to_v2_model(v1)

    # Valid migration should have no issues
    issues = validate_migration(v1, v2)
    assert len(issues) == 0


# =============================================================================
# Cross-reference validation tests
# =============================================================================


def test_v2_validates_tactic_objective_refs() -> None:
    """Test that ContextManifestV2 validates tactic → objective references."""
    with pytest.raises(ValueError, match="unknown objective"):
        ContextManifestV2(
            metadata=ManifestMetadataV2(name="test"),
            spec=_make_spec("test", "Test"),
            strategy=StrategySpec(
                objectives=[ObjectiveV2(id="OBJ-001", description="Real objective")],
                tactics=[
                    TacticV2(
                        id="TAC-001",
                        description="Test tactic",
                        linked_objectives=["OBJ-NONEXISTENT"],  # Invalid ref
                    )
                ],
            ),
        )


def test_tactic_blocked_requires_reason() -> None:
    """Test that blocked tactics must have a reason."""
    with pytest.raises(ValueError, match="missing blocked_reason"):
        TacticV2(
            id="TAC-001",
            description="Blocked tactic",
            status=TacticStatus.BLOCKED,
            # No blocked_reason!
        )

    # Valid blocked tactic
    tactic = TacticV2(
        id="TAC-001",
        description="Blocked tactic",
        status=TacticStatus.BLOCKED,
        blocked_reason="Waiting for dependency",
    )
    assert tactic.blocked_reason == "Waiting for dependency"


# =============================================================================
# Helper method tests
# =============================================================================


def test_v2_get_open_questions() -> None:
    """Test get_open_questions helper."""
    manifest = ContextManifestV2(
        metadata=ManifestMetadataV2(name="test"),
        spec=_make_spec("test", "Test"),
        guidance=AgentGuidanceSpec(
            questions=[
                Question(id="Q-001", question="Open?", status=QuestionStatus.OPEN),
                Question(id="Q-002", question="Answered?", status=QuestionStatus.ANSWERED),
                Question(id="Q-003", question="Also open?", status=QuestionStatus.OPEN),
            ]
        ),
    )

    open_questions = manifest.get_open_questions()
    assert len(open_questions) == 2
    assert all(q.status == QuestionStatus.OPEN for q in open_questions)


def test_v2_get_active_constraints() -> None:
    """Test get_active_constraints helper."""
    manifest = ContextManifestV2(
        metadata=ManifestMetadataV2(name="test"),
        spec=_make_spec("test", "Test"),
        guidance=AgentGuidanceSpec(
            constraints=[
                Constraint(id="C-001", rule="Blocking rule", severity=ConstraintSeverity.BLOCKING),
                Constraint(id="C-002", rule="Warning rule", severity=ConstraintSeverity.WARNING),
                Constraint(id="C-003", rule="Another blocking", severity=ConstraintSeverity.BLOCKING),
            ]
        ),
    )

    blocking = manifest.get_active_constraints()
    assert len(blocking) == 2
    assert all(c.severity == ConstraintSeverity.BLOCKING for c in blocking)


def test_v2_compute_state() -> None:
    """Test compute_state helper."""
    manifest = ContextManifestV2(
        metadata=ManifestMetadataV2(name="test"),
        spec=_make_spec("test", "Test"),
        strategy=StrategySpec(
            objectives=[
                ObjectiveV2(id="OBJ-001", description="Obj 1"),
                ObjectiveV2(id="OBJ-002", description="Obj 2"),
            ],
            tactics=[
                TacticV2(id="TAC-001", description="In progress", status=TacticStatus.IN_PROGRESS),
                TacticV2(id="TAC-002", description="Done", status=TacticStatus.DONE),
            ],
        ),
        guidance=AgentGuidanceSpec(
            questions=[
                Question(id="Q-001", question="Open?", status=QuestionStatus.OPEN),
            ]
        ),
    )

    state = manifest.compute_state()
    assert state.objective_count == 2
    assert state.active_tactic_count == 1  # Only in_progress
    assert state.open_question_count == 1


def test_v2_distill_crd() -> None:
    """Test distill_crd produces valid K8s CRD structure."""
    manifest = ContextManifestV2(
        metadata=ManifestMetadataV2(name="my-service"),
        spec=_make_spec("my-service", "My Service"),
    )

    crd = manifest.distill_crd(namespace="production", name="my-service-context")

    assert crd["apiVersion"] == "contextcore.io/v1"
    assert crd["kind"] == "ProjectContext"
    assert crd["metadata"]["name"] == "my-service-context"
    assert crd["metadata"]["namespace"] == "production"
    assert "spec" in crd


# =============================================================================
# Enriched Artifact Manifest Export Tests
# =============================================================================

from contextcore.models.artifact_manifest import ArtifactType as ArtifactManifestType
from contextcore.models.manifest import KeyResult, MetricUnit, Owner, TargetOperator


def _make_enriched_manifest(**overrides) -> ContextManifestV2:
    """
    Create a ContextManifestV2 with enriched data for artifact manifest tests.

    Supports overriding any top-level section via keyword arguments.
    """
    defaults = dict(
        metadata=ManifestMetadataV2(
            name="enriched-project",
            owners=[
                Owner(team="platform-team", slack="#platform-oncall", email="platform@example.com", oncall="platform-rotation"),
                Owner(team="sre-team", slack="#sre-alerts", email="sre@example.com", oncall="sre-rotation"),
            ],
            links={"repo": "https://github.com/example/enriched", "wiki": "https://wiki.example.com/enriched"},
        ),
        spec={
            "project": {"id": "enriched", "name": "Enriched Project"},
            "business": {
                "criticality": "critical",
                "owner": "platform-team",
                "costCenter": "CC-1234",
                "value": "revenue-primary",
            },
            "requirements": {
                "availability": "99.99",
                "latencyP99": "200ms",
                "latencyP50": "50ms",
                "errorBudget": "0.01",
                "throughput": "5000rps",
            },
            "risks": [
                {
                    "type": "availability",
                    "description": "OTLP exporter failure",
                    "priority": "P1",
                    "mitigation": "Fallback to file-based persistence",
                },
            ],
            "targets": [
                {"kind": "Deployment", "name": "enriched-deployment", "namespace": "production"},
            ],
        },
        strategy=StrategySpec(
            objectives=[
                ObjectiveV2(
                    id="OBJ-1",
                    description="Improve availability",
                    key_results=[
                        KeyResult(
                            metric_key="availability",
                            unit=MetricUnit.PERCENT,
                            target=99.99,
                            data_source="promql:avg_over_time(up[30d])",
                        ),
                    ],
                ),
            ],
        ),
        guidance=AgentGuidanceSpec(
            focus=Focus(areas=["reliability", "performance"], reason="Q1 priority"),
            constraints=[
                Constraint(id="C-1", rule="no sync deps", severity=ConstraintSeverity.BLOCKING),
            ],
            preferences=[
                Preference(id="P-1", description="use structured logging", example="logger.info(data={})"),
            ],
        ),
    )
    defaults.update(overrides)
    return ContextManifestV2(**defaults)


def test_export_includes_project_context() -> None:
    """Test that generate_artifact_manifest() populates project_context."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    assert am.project_context is not None
    assert am.project_context.name == "enriched-project"
    assert am.project_context.owner == "platform-team"
    assert am.project_context.cost_center == "CC-1234"
    assert am.project_context.links is not None
    assert "repo" in am.project_context.links
    assert "wiki" in am.project_context.links


def test_export_includes_owners() -> None:
    """Test that generate_artifact_manifest() includes owner contacts."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    assert len(am.owners) == 2
    assert am.owners[0].team == "platform-team"
    assert am.owners[0].slack == "#platform-oncall"
    assert am.owners[0].email == "platform@example.com"
    assert am.owners[1].team == "sre-team"


def test_export_includes_guidance() -> None:
    """Test that generate_artifact_manifest() includes governance guidance."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    assert am.guidance is not None
    assert am.guidance.focus is not None
    assert len(am.guidance.focus.areas) == 2
    assert "reliability" in am.guidance.focus.areas
    assert "performance" in am.guidance.focus.areas
    assert len(am.guidance.constraints) == 1
    assert am.guidance.constraints[0].severity == "blocking"
    assert len(am.guidance.preferences) == 1
    assert am.guidance.preferences[0].id == "P-1"


def test_export_includes_objectives() -> None:
    """Test that generate_artifact_manifest() includes strategic objectives."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    assert len(am.objectives) == 1
    assert am.objectives[0].id == "OBJ-1"
    assert am.objectives[0].description == "Improve availability"
    assert len(am.objectives[0].key_results) == 1
    assert am.objectives[0].key_results[0].data_source is not None
    assert "promql" in am.objectives[0].key_results[0].data_source


def test_export_includes_semantic_conventions() -> None:
    """Test that generate_artifact_manifest() includes OTel semantic convention hints."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    assert am.semantic_conventions is not None
    assert "gen_ai.*" in am.semantic_conventions.attribute_namespaces
    # Standard should only include contextcore metrics, not implementation-specific
    assert "contextcore" in am.semantic_conventions.metrics
    assert "task_by_project" in am.semantic_conventions.query_templates
    assert am.semantic_conventions.log_format == "otel"


def test_export_semantic_conventions_no_implementation_metrics_by_default() -> None:
    """Test that standard export doesn't include implementation-specific metrics.

    Per ADR-002: ContextCore is the standard, expansion pack metrics (e.g., startd8/Beaver)
    should not be hardcoded. They are injected via extra_metrics at the CLI layer.
    """
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    # Standard export should NOT include expansion pack metrics
    assert "startd8" not in am.semantic_conventions.metrics
    assert "beaver" not in am.semantic_conventions.metrics


def test_export_extra_metrics_injected() -> None:
    """Test that extra_metrics parameter injects implementation-specific metrics."""
    manifest = _make_enriched_manifest()
    beaver_metrics = {
        "beaver": ["startd8_cost_total", "startd8_active_sessions"],
    }
    am = manifest.generate_artifact_manifest(extra_metrics=beaver_metrics)

    assert "beaver" in am.semantic_conventions.metrics
    assert "startd8_cost_total" in am.semantic_conventions.metrics["beaver"]
    # Standard metrics should still be present
    assert "contextcore" in am.semantic_conventions.metrics


def test_export_dashboard_has_enriched_params() -> None:
    """Test that dashboard artifact includes datasources and risks in parameters."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    dashboards = [a for a in am.artifacts if a.type == ArtifactManifestType.DASHBOARD]
    assert len(dashboards) >= 1
    dashboard = dashboards[0]

    assert "datasources" in dashboard.parameters
    assert "Tempo" in dashboard.parameters["datasources"]
    assert "Loki" in dashboard.parameters["datasources"]
    assert "mimir" in dashboard.parameters["datasources"]
    assert "risks" in dashboard.parameters
    assert isinstance(dashboard.parameters["risks"], list)
    assert len(dashboard.parameters["risks"]) >= 1


def test_export_prometheus_rules_has_latency_p50() -> None:
    """Test that prometheus_rule artifact includes latencyP50Threshold."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    prom_rules = [a for a in am.artifacts if a.type == ArtifactManifestType.PROMETHEUS_RULE]
    assert len(prom_rules) >= 1
    rule = prom_rules[0]

    assert "latencyP50Threshold" in rule.parameters
    assert rule.parameters["latencyP50Threshold"] == "50ms"


def test_export_loki_rules_has_enriched_params() -> None:
    """Test that loki_rule artifact includes recording rules, label extractors, and log format."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    loki_rules = [a for a in am.artifacts if a.type == ArtifactManifestType.LOKI_RULE]
    assert len(loki_rules) >= 1
    rule = loki_rules[0]

    assert "recordingRules" in rule.parameters
    assert "labelExtractors" in rule.parameters
    assert "logFormat" in rule.parameters
    assert rule.parameters["logFormat"] == "otel"


def test_export_artifact_dependencies() -> None:
    """Test that artifacts have correct dependency chains."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    # Get artifacts for the first target
    target_name = "enriched-deployment"
    target_artifacts = {a.type: a for a in am.artifacts if a.target == target_name}

    sm = target_artifacts[ArtifactManifestType.SERVICE_MONITOR]
    prom = target_artifacts[ArtifactManifestType.PROMETHEUS_RULE]
    notify = target_artifacts[ArtifactManifestType.NOTIFICATION_POLICY]
    runbook = target_artifacts[ArtifactManifestType.RUNBOOK]

    # Service monitor has no dependencies
    assert sm.depends_on == []

    # Prometheus rules depend on service monitor
    assert sm.id in prom.depends_on

    # Notification depends on prometheus rules
    assert prom.id in notify.depends_on

    # Runbook depends on both prometheus rules and notification
    assert prom.id in runbook.depends_on
    assert notify.id in runbook.depends_on


def test_export_notification_has_full_owners() -> None:
    """Test that notification_policy artifact includes full owner contacts."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    notifications = [a for a in am.artifacts if a.type == ArtifactManifestType.NOTIFICATION_POLICY]
    assert len(notifications) >= 1
    notify = notifications[0]

    assert "owners" in notify.parameters
    owners = notify.parameters["owners"]
    assert isinstance(owners, list)
    assert len(owners) == 2
    assert owners[0]["team"] == "platform-team"
    assert owners[0]["slack"] == "#platform-oncall"
    assert owners[0]["email"] == "platform@example.com"


def test_export_runbook_has_enriched_params() -> None:
    """Test that runbook artifact includes escalation contacts and risk mitigations."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    runbooks = [a for a in am.artifacts if a.type == ArtifactManifestType.RUNBOOK]
    assert len(runbooks) >= 1
    runbook = runbooks[0]

    # Escalation contacts
    assert "escalationContacts" in runbook.parameters
    contacts = runbook.parameters["escalationContacts"]
    assert isinstance(contacts, list)
    assert len(contacts) == 2
    assert contacts[0]["team"] == "platform-team"
    assert contacts[0]["slack"] == "#platform-oncall"
    assert contacts[0]["email"] == "platform@example.com"

    # Risks with mitigation
    assert "risks" in runbook.parameters
    risks = runbook.parameters["risks"]
    assert isinstance(risks, list)
    assert len(risks) >= 1
    assert "mitigation" in risks[0]
    assert risks[0]["mitigation"] == "Fallback to file-based persistence"


def test_build_onboarding_metadata_is_json_serializable() -> None:
    """Onboarding metadata must be JSON-serializable for plan ingestion."""
    import json

    from contextcore.utils.onboarding import build_onboarding_metadata

    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    meta = build_onboarding_metadata(
        artifact_manifest=am,
        artifact_manifest_path="out/project-artifact-manifest.yaml",
        project_context_path="out/project-context.yaml",
    )
    # Should not raise; output_path_conventions uses string keys/values
    json_str = json.dumps(meta)
    assert isinstance(json_str, str)
    assert "artifact_manifest_path" in json_str


# =============================================================================
# Export Enrichment Plan Tests (Changes 1-6 + Guide §6 calibration hints)
# =============================================================================


def _build_enriched_onboarding():
    """Helper: build onboarding metadata from an enriched manifest with questions."""
    from contextcore.utils.onboarding import build_onboarding_metadata

    manifest = _make_enriched_manifest(
        guidance=AgentGuidanceSpec(
            focus=Focus(areas=["reliability"], reason="Q1"),
            constraints=[
                Constraint(id="C-1", rule="no sync deps", severity=ConstraintSeverity.BLOCKING),
            ],
            preferences=[
                Preference(id="P-1", description="structured logging"),
            ],
            questions=[
                Question(
                    id="Q-DASHBOARD-FORMAT",
                    question="Should dashboards target Grafana provisioning or API format?",
                    status=QuestionStatus.OPEN,
                    priority=Priority.HIGH,
                ),
                Question(
                    id="Q-ANSWERED",
                    question="Which log format?",
                    status=QuestionStatus.ANSWERED,
                    priority=Priority.LOW,
                    answer="OTEL",
                    answered_by="claude",
                ),
            ],
        ),
        strategy=StrategySpec(
            objectives=[
                ObjectiveV2(
                    id="OBJ-PERF",
                    description="Maintain sub-500ms P99 latency",
                    key_results=[
                        KeyResult(
                            metric_key="latency_p99",
                            unit=MetricUnit.MILLISECONDS,
                            target=500.0,
                            operator=TargetOperator.LTE,
                            window="30d",
                            data_source="promql:histogram_quantile(0.99, ...)",
                        ),
                    ],
                ),
            ],
        ),
    )
    am = manifest.generate_artifact_manifest()
    meta = build_onboarding_metadata(
        artifact_manifest=am,
        artifact_manifest_path="out/artifact-manifest.yaml",
        project_context_path="out/project-context.yaml",
    )
    return meta, am


def test_enrichment_derivation_rules() -> None:
    """Change 1: derivation_rules surfaces derived_from rules grouped by artifact type."""
    meta, _ = _build_enriched_onboarding()

    assert "derivation_rules" in meta
    dr = meta["derivation_rules"]
    # All artifact types with derived_from should be present
    assert "dashboard" in dr
    assert "prometheus_rule" in dr
    assert "loki_rule" in dr  # Change 6 fix
    # Each entry should have property and sourceField
    for rules in dr.values():
        for rule in rules:
            assert "property" in rule
            assert "sourceField" in rule
            assert "transformation" in rule


def test_enrichment_objectives() -> None:
    """Change 2: objectives surfaces strategic objectives with operator/window."""
    meta, _ = _build_enriched_onboarding()

    assert "objectives" in meta
    objs = meta["objectives"]
    assert len(objs) == 1
    assert objs[0]["id"] == "OBJ-PERF"
    assert objs[0]["description"] == "Maintain sub-500ms P99 latency"
    # Key results should include operator and window
    kr = objs[0]["keyResults"][0]
    assert kr["metricKey"] == "latency_p99"
    assert kr["target"] == 500.0
    assert kr["targetOperator"] == "lte"
    assert kr["window"] == "30d"


def test_enrichment_artifact_dependency_graph() -> None:
    """Change 3: artifact_dependency_graph surfaces depends_on relationships."""
    meta, _ = _build_enriched_onboarding()

    assert "artifact_dependency_graph" in meta
    graph = meta["artifact_dependency_graph"]
    # Prometheus rules depend on service monitor
    rules_key = [k for k in graph if "prometheus-rules" in k]
    assert len(rules_key) >= 1
    # Value should be a list of artifact IDs
    for deps in graph.values():
        assert isinstance(deps, list)
        for dep in deps:
            assert isinstance(dep, str)


def test_enrichment_resolved_artifact_parameters() -> None:
    """Change 4: resolved_artifact_parameters surfaces concrete parameter values."""
    meta, _ = _build_enriched_onboarding()

    assert "resolved_artifact_parameters" in meta
    params = meta["resolved_artifact_parameters"]
    # Should have entries for artifacts with non-None parameters
    assert len(params) > 0
    # Prometheus rules should have alertSeverity
    rules_key = [k for k in params if "prometheus-rules" in k]
    assert len(rules_key) >= 1
    rules_params = params[rules_key[0]]
    assert "alertSeverity" in rules_params
    assert rules_params["alertSeverity"] == "P1"  # critical → P1


def test_enrichment_open_questions() -> None:
    """Change 5: open_questions surfaces only open questions from guidance."""
    meta, _ = _build_enriched_onboarding()

    assert "open_questions" in meta
    oqs = meta["open_questions"]
    # Only the OPEN question should be surfaced, not the ANSWERED one
    assert len(oqs) == 1
    assert oqs[0]["id"] == "Q-DASHBOARD-FORMAT"
    assert oqs[0]["priority"] == "high"
    assert oqs[0]["status"] == "open"


def test_enrichment_loki_rule_has_derived_from() -> None:
    """Change 6: loki_rule artifacts now include derived_from rules."""
    manifest = _make_enriched_manifest()
    am = manifest.generate_artifact_manifest()

    loki_artifacts = [a for a in am.artifacts if a.type == ArtifactManifestType.LOKI_RULE]
    assert len(loki_artifacts) >= 1
    for loki in loki_artifacts:
        assert len(loki.derived_from) > 0, f"Loki artifact {loki.id} missing derived_from"
        props = [r.property for r in loki.derived_from]
        assert "logSelectors" in props


def test_enrichment_expected_output_contracts() -> None:
    """Guide §6 + ExpectedOutput: expected_output_contracts unifies calibration, size, and fields."""
    meta, _ = _build_enriched_onboarding()

    assert "expected_output_contracts" in meta
    contracts = meta["expected_output_contracts"]
    # All artifact types in the manifest should have contracts
    assert "dashboard" in contracts
    assert "prometheus_rule" in contracts
    assert "service_monitor" in contracts
    assert "loki_rule" in contracts
    # Each contract should have all ExpectedOutput-pattern fields
    for art_type, contract in contracts.items():
        assert "expected_depth" in contract, f"Missing expected_depth for {art_type}"
        assert "max_lines" in contract, f"Missing max_lines for {art_type}"
        assert "max_tokens" in contract, f"Missing max_tokens for {art_type}"
        assert "completeness_markers" in contract, f"Missing completeness_markers for {art_type}"
        assert "fields" in contract, f"Missing fields for {art_type}"
        assert "red_flag" in contract, f"Missing red_flag for {art_type}"
        # Size limits should be positive
        assert contract["max_lines"] > 0
        assert contract["max_tokens"] > 0
        # Fields should come from parameter schema
        assert isinstance(contract["fields"], list)
        # Completeness markers should be non-empty
        assert len(contract["completeness_markers"]) > 0
    # Spot-check specific calibrations
    assert contracts["dashboard"]["expected_depth"] == "comprehensive"
    assert contracts["dashboard"]["max_lines"] == 300
    assert "panels" in contracts["dashboard"]["completeness_markers"]
    assert "criticality" in contracts["dashboard"]["fields"]
    assert contracts["service_monitor"]["expected_depth"] == "brief"
    assert contracts["service_monitor"]["max_lines"] == 50


def test_enrichment_guidance_includes_questions_export() -> None:
    """Verify the guidance export now includes questions in the raw dump."""
    manifest = _make_enriched_manifest(
        guidance=AgentGuidanceSpec(
            questions=[
                Question(
                    id="Q-1",
                    question="Test question?",
                    status=QuestionStatus.OPEN,
                    priority=Priority.HIGH,
                ),
            ],
        ),
    )
    am = manifest.generate_artifact_manifest()

    assert am.guidance is not None
    assert len(am.guidance.questions) == 1
    assert am.guidance.questions[0].id == "Q-1"
    assert am.guidance.questions[0].status == "open"


def test_enrichment_key_result_operator_window_export() -> None:
    """Verify KeyResultExport carries operator and window from source model."""
    from contextcore.models.manifest import TargetOperator

    manifest = _make_enriched_manifest(
        strategy=StrategySpec(
            objectives=[
                ObjectiveV2(
                    id="OBJ-AVAIL",
                    description="High availability",
                    key_results=[
                        KeyResult(
                            metric_key="availability",
                            unit=MetricUnit.PERCENT,
                            target=99.99,
                            operator=TargetOperator.GTE,
                            window="30d",
                            baseline=99.5,
                        ),
                    ],
                ),
            ],
        ),
    )
    am = manifest.generate_artifact_manifest()

    assert len(am.objectives) == 1
    kr = am.objectives[0].key_results[0]
    assert kr.metric_key == "availability"
    assert kr.operator == "gte"
    assert kr.window == "30d"
    assert kr.baseline == 99.5
