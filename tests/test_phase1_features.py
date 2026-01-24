"""
Tests for Phase 1 Quick Wins features.

Covers:
- Feature 1.1: Alert Annotation Enrichment
- Feature 1.2: Cost Attribution Labels
- Feature 1.3: Runbook Generation
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

# Store original modules to restore after tests
_original_modules = {}

def _mock_heavy_dependencies():
    """Mock heavy dependencies before importing contextcore.operator."""
    global _original_modules
    modules_to_mock = [
        "kopf",
        "kubernetes",
        "kubernetes.client",
        "kubernetes.config",
        "kubernetes.client.rest",
    ]
    for mod in modules_to_mock:
        _original_modules[mod] = sys.modules.get(mod)
        sys.modules[mod] = MagicMock()

def _restore_modules():
    """Restore original modules after tests."""
    global _original_modules
    for mod, original in _original_modules.items():
        if original is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = original
    _original_modules.clear()

# Mock only non-OTel dependencies (OTel is used by other tests)
_mock_heavy_dependencies()

from contextcore.operator import (
    _build_enriched_annotations,
    _get_mitigation_for_risk_type,
    _sanitize_label_value,
    generate_cost_labels,
    generate_grafana_dashboard,
    generate_prometheus_rules,
    generate_service_monitor)
from contextcore.generators.runbook import (
    generate_runbook,
    _generate_overview_section,
    _generate_slo_section,
    _generate_risks_section,
    _generate_resources_section,
    _generate_procedures_section,
    _generate_escalation_section)


# ============================================================================
# Feature 1.1: Alert Annotation Enrichment Tests
# ============================================================================


class TestAlertAnnotationEnrichment:
    """Tests for enriched alert annotations in PrometheusRule generation."""

    def test_alert_enrichment_with_adr(self, sample_project_context_spec):
        """Generated PrometheusRule should include architecture_decision annotation."""
        rules = generate_prometheus_rules(
            "test-service", "default", sample_project_context_spec, {}
        )

        # Get the alerting rules
        alerting_group = rules["spec"]["groups"][1]
        alert = alerting_group["rules"][0]

        assert "architecture_decision" in alert["annotations"]
        assert alert["annotations"]["architecture_decision"] == "ADR-015-event-driven-checkout"

    def test_alert_enrichment_with_runbook_url(self):
        """Generated PrometheusRule should include runbook_url annotation."""
        spec = {
            "project": {"id": "test-project"},
            "observability": {"runbook": "https://runbook.example.com/test"},
        }
        rules = generate_prometheus_rules("test", "default", spec, {})

        alert = rules["spec"]["groups"][1]["rules"][0]
        assert "runbook_url" in alert["annotations"]
        assert alert["annotations"]["runbook_url"] == "https://runbook.example.com/test"

    def test_alert_enrichment_with_business_context(self, sample_project_context_spec):
        """Generated PrometheusRule should include owner and business_criticality."""
        rules = generate_prometheus_rules(
            "test", "default", sample_project_context_spec, {}
        )

        alert = rules["spec"]["groups"][1]["rules"][0]
        assert "owner" in alert["annotations"]
        assert alert["annotations"]["owner"] == "commerce-team"
        assert "business_criticality" in alert["annotations"]
        assert alert["annotations"]["business_criticality"] == "critical"

    def test_alert_enrichment_with_risks(self, sample_project_context_spec):
        """Generated PrometheusRule should include known_risks summary."""
        rules = generate_prometheus_rules(
            "test", "default", sample_project_context_spec, {}
        )

        alert = rules["spec"]["groups"][1]["rules"][0]
        assert "known_risks" in alert["annotations"]
        assert "security" in alert["annotations"]["known_risks"]
        assert "PII" in alert["annotations"]["known_risks"] or "payment" in alert["annotations"]["known_risks"]

    def test_alert_enrichment_with_multiple_risks(self):
        """known_risks should summarize up to 3 risks."""
        spec = {
            "project": {"id": "test"},
            "risks": [
                {"type": "security", "description": "API key exposure risk"},
                {"type": "availability", "description": "Single point of failure"},
                {"type": "performance", "description": "Database bottleneck"},
                {"type": "compliance", "description": "GDPR requirements"},  # Should be excluded (>3)
            ],
        }
        rules = generate_prometheus_rules("test", "default", spec, {})

        alert = rules["spec"]["groups"][1]["rules"][0]
        known_risks = alert["annotations"]["known_risks"]

        assert "security" in known_risks
        assert "availability" in known_risks
        assert "performance" in known_risks
        # Fourth risk should not be included
        assert known_risks.count(";") == 2  # Two semicolons for 3 items

    def test_alert_enrichment_minimal_spec(self, minimal_project_context_spec):
        """Alert enrichment should work with minimal spec (no enrichment fields)."""
        rules = generate_prometheus_rules(
            "test", "default", minimal_project_context_spec, {}
        )

        alert = rules["spec"]["groups"][1]["rules"][0]
        # Base annotations should still exist
        assert "summary" in alert["annotations"]
        assert "description" in alert["annotations"]
        # Optional annotations should not exist
        assert "architecture_decision" not in alert["annotations"]
        assert "runbook_url" not in alert["annotations"]

    def test_mitigation_hint_for_risk_types(self):
        """Mitigation hints should be provided for known risk types."""
        assert "pod health" in _get_mitigation_for_risk_type("availability")
        assert "access logs" in _get_mitigation_for_risk_type("security")
        assert "database" in _get_mitigation_for_risk_type("data-integrity")
        assert "compliance team" in _get_mitigation_for_risk_type("compliance")
        assert "runbook" in _get_mitigation_for_risk_type("unknown-type")


# ============================================================================
# Feature 1.2: Cost Attribution Labels Tests
# ============================================================================


class TestCostAttributionLabels:
    """Tests for cost attribution labels on generated resources."""

    def test_generate_cost_labels_full(self):
        """Cost labels should be generated from full business context."""
        spec = {
            "project": {"id": "checkout"},
            "business": {
                "costCenter": "CC-1234",
                "owner": "commerce-team",
                "value": "revenue-primary",
                "criticality": "critical",
            },
        }
        labels = generate_cost_labels(spec)

        assert labels["cost-center"] == "CC-1234"
        assert labels["owner"] == "commerce-team"
        assert labels["business-value"] == "revenue-primary"
        assert labels["criticality"] == "critical"
        assert labels["project-id"] == "checkout"

    def test_generate_cost_labels_minimal(self):
        """Cost labels should handle minimal spec gracefully."""
        spec = {"project": {"id": "minimal"}}
        labels = generate_cost_labels(spec)

        assert labels["project-id"] == "minimal"
        assert "cost-center" not in labels
        assert "owner" not in labels

    def test_generate_cost_labels_string_project(self):
        """Cost labels should handle string project ID."""
        spec = {"project": "simple-project"}
        labels = generate_cost_labels(spec)

        assert labels["project-id"] == "simple-project"

    def test_cost_labels_applied_to_service_monitor(self):
        """ServiceMonitor should include cost attribution labels."""
        spec = {
            "project": {"id": "checkout"},
            "business": {
                "costCenter": "CC-1234",
                "owner": "commerce-team",
            },
        }
        sm = generate_service_monitor("test", "default", spec, {})
        labels = sm["metadata"]["labels"]

        assert labels["cost-center"] == "CC-1234"
        assert labels["owner"] == "commerce-team"
        assert labels["project-id"] == "checkout"

    def test_cost_labels_applied_to_prometheus_rules(self):
        """PrometheusRule should include cost attribution labels."""
        spec = {
            "project": {"id": "checkout"},
            "business": {
                "costCenter": "CC-1234",
                "owner": "commerce-team",
            },
        }
        rules = generate_prometheus_rules("test", "default", spec, {})
        labels = rules["metadata"]["labels"]

        assert labels["cost-center"] == "CC-1234"
        assert labels["owner"] == "commerce-team"

    def test_cost_labels_applied_to_dashboard(self):
        """Grafana Dashboard ConfigMap should include cost attribution labels."""
        spec = {
            "project": {"id": "checkout"},
            "business": {
                "costCenter": "CC-1234",
                "owner": "commerce-team",
                "value": "revenue-primary",
                "criticality": "critical",
            },
        }
        dashboard = generate_grafana_dashboard("test", "default", spec, {})
        labels = dashboard["metadata"]["labels"]

        assert labels["cost-center"] == "CC-1234"
        assert labels["owner"] == "commerce-team"
        assert labels["business-value"] == "revenue-primary"
        assert labels["criticality"] == "critical"

    def test_sanitize_label_value_special_chars(self):
        """Label values with special characters should be sanitized."""
        assert _sanitize_label_value("CC-1234") == "CC-1234"
        assert _sanitize_label_value("team@example.com") == "team-example.com"
        assert _sanitize_label_value("  spaces  ") == "spaces"
        assert _sanitize_label_value("valid_value.test") == "valid_value.test"

    def test_sanitize_label_value_length(self):
        """Label values exceeding 63 chars should be truncated."""
        long_value = "a" * 100
        assert len(_sanitize_label_value(long_value)) == 63


# ============================================================================
# Feature 1.3: Runbook Generation Tests
# ============================================================================


class TestRunbookGeneration:
    """Tests for runbook generation from ProjectContext."""

    def test_runbook_generation_minimal(self, minimal_project_context_spec):
        """Runbook should be generated from minimal spec."""
        runbook = generate_runbook("minimal-project", minimal_project_context_spec)

        assert "# minimal-project Operational Runbook" in runbook
        assert "## Service Overview" in runbook
        assert "## Common Procedures" in runbook

    def test_runbook_generation_full(self, sample_project_context_spec):
        """Runbook should include all sections from full spec."""
        runbook = generate_runbook("commerce-platform", sample_project_context_spec)

        # Header
        assert "# commerce-platform Operational Runbook" in runbook
        assert "_Generated:" in runbook

        # Sections
        assert "## Service Overview" in runbook
        assert "## Service Level Objectives" in runbook
        assert "## Known Risks & Mitigations" in runbook
        assert "## Kubernetes Resources" in runbook
        assert "## Common Procedures" in runbook
        assert "## Alert Response" in runbook
        assert "## Escalation" in runbook

    def test_runbook_overview_section(self, sample_project_context_spec):
        """Overview section should include project and business info."""
        overview = _generate_overview_section(sample_project_context_spec)

        assert "commerce-platform" in overview
        assert "EPIC-42" in overview
        assert "commerce-team" in overview
        assert "critical" in overview
        assert "revenue-primary" in overview

    def test_runbook_slo_section(self, sample_project_context_spec):
        """SLO section should include requirements as table."""
        slo = _generate_slo_section(sample_project_context_spec["requirements"])

        assert "Availability" in slo
        assert "99.95" in slo
        assert "Latency P99" in slo
        assert "200ms" in slo

    def test_runbook_risks_section(self, sample_project_context_spec):
        """Risks section should include risks as table."""
        risks = _generate_risks_section(sample_project_context_spec["risks"])

        assert "security" in risks
        assert "PII" in risks or "payment" in risks
        assert "P1" in risks

    def test_runbook_resources_section(self, sample_project_context_spec):
        """Resources section should include kubectl commands."""
        resources = _generate_resources_section(sample_project_context_spec["targets"])

        assert "kubectl get deployment checkout-service" in resources
        assert "kubectl logs" in resources
        assert "kubectl describe" in resources

    def test_runbook_procedures_section(self, sample_project_context_spec):
        """Procedures section should include restart and scale commands."""
        procedures = _generate_procedures_section(sample_project_context_spec)

        assert "### Restart Service" in procedures
        assert "kubectl rollout restart" in procedures
        assert "### Emergency Scale Up" in procedures  # Critical service

    def test_runbook_procedures_non_critical(self, minimal_project_context_spec):
        """Non-critical services should not have emergency scale section."""
        procedures = _generate_procedures_section(minimal_project_context_spec)

        assert "### Restart Service" in procedures
        assert "### Emergency Scale Up" not in procedures

    def test_runbook_escalation_section(self, sample_project_context_spec):
        """Escalation section should include contacts."""
        escalation = _generate_escalation_section(sample_project_context_spec)

        assert "L1" in escalation
        assert "L2" in escalation
        assert "commerce-team" in escalation
        assert "commerce-oncall" in escalation  # Alert channel


class TestRunbookEdgeCases:
    """Edge case tests for runbook generation."""

    def test_runbook_empty_spec(self):
        """Runbook should handle empty spec gracefully."""
        runbook = generate_runbook("empty-project", {})

        assert "# empty-project Operational Runbook" in runbook
        assert "## Service Overview" in runbook

    def test_runbook_string_project_id(self):
        """Runbook should handle string project ID (v1alpha1 schema)."""
        spec = {"project": "string-project"}
        runbook = generate_runbook("string-project", spec)

        assert "string-project" in runbook

    def test_runbook_no_targets(self):
        """Runbook should handle spec without targets."""
        spec = {"project": {"id": "no-targets"}}
        runbook = generate_runbook("no-targets", spec)

        assert "No targets defined" in runbook

    def test_runbook_dependencies(self):
        """Runbook should include dependencies section if present."""
        spec = {
            "project": {"id": "with-deps"},
            "dependencies": [
                {"name": "postgres", "type": "database", "healthEndpoint": "/health"},
                {"name": "redis", "type": "cache"},
            ],
        }
        runbook = generate_runbook("with-deps", spec)

        assert "## Dependencies" in runbook
        assert "postgres" in runbook
        assert "redis" in runbook

    def test_runbook_truncates_long_descriptions(self):
        """Risk descriptions should be truncated in runbook."""
        spec = {
            "project": {"id": "test"},
            "risks": [
                {
                    "type": "security",
                    "description": "A" * 100,  # Very long description
                    "priority": "P1",
                },
            ],
        }
        runbook = generate_runbook("test", spec)

        # Description should be truncated (50 chars in table)
        assert "A" * 51 not in runbook


# ============================================================================
# Module cleanup - restore mocked modules
# ============================================================================


@pytest.fixture(scope="module", autouse=True)
def cleanup_mocks():
    """Restore mocked modules after all tests in this module complete."""
    yield
    _restore_modules()
