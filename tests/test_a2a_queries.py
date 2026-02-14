"""
Tests for A2A governance observability queries.

Day 6 spec: "On-call/operator can answer 'what failed, where, why, what next'
in minutes."

Validates that query builders produce syntactically correct TraceQL/LogQL
and that every query maps to a concrete operational action.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextcore.contracts.a2a.queries import A2AQueries


@pytest.fixture
def queries() -> A2AQueries:
    return A2AQueries(project_id="contextcore")


class TestTraceQLQueries:
    """TraceQL queries (Tempo) for span-level observability."""

    def test_blocked_span_hotspot(self, queries: A2AQueries) -> None:
        q = queries.blocked_span_hotspot()
        assert 'span.task.status = "blocked"' in q
        assert 'span.project.id = "contextcore"' in q

    def test_blocked_spans_with_reason(self, queries: A2AQueries) -> None:
        q = queries.blocked_spans_with_reason()
        assert "span.task.blocked_reason" in q
        assert "span.task.next_action" in q
        assert "select(" in q

    def test_gate_failures(self, queries: A2AQueries) -> None:
        q = queries.gate_failures()
        assert 'span.gate.result = "fail"' in q

    def test_gate_results_by_phase(self, queries: A2AQueries) -> None:
        q = queries.gate_results_by_phase("CONTRACT_INTEGRITY")
        assert 'span.gate.phase = "CONTRACT_INTEGRITY"' in q

    def test_finalize_outcomes(self, queries: A2AQueries) -> None:
        q = queries.finalize_outcomes()
        assert 'span.task.phase = "FINALIZE_VERIFY"' in q

    def test_trace_by_id(self, queries: A2AQueries) -> None:
        q = queries.trace_by_id("PI-101-002")
        assert 'span.task.id = "PI-101-002"' in q

    def test_spans_by_parent(self, queries: A2AQueries) -> None:
        q = queries.spans_by_parent("PI-101-002")
        assert 'span.task.parent_id = "PI-101-002"' in q

    def test_all_traceql_contain_service_name(self, queries: A2AQueries) -> None:
        """Every TraceQL query should scope to the contextcore service."""
        traceql_methods = [
            queries.blocked_span_hotspot,
            queries.blocked_spans_with_reason,
            queries.gate_failures,
            queries.finalize_outcomes,
        ]
        for method in traceql_methods:
            q = method()
            assert 'resource.service.name = "contextcore"' in q, (
                f"{method.__name__} missing service.name filter"
            )


class TestLogQLQueries:
    """LogQL queries (Loki) for event-level observability."""

    def test_handoff_validation_failures(self, queries: A2AQueries) -> None:
        q = queries.handoff_validation_failures()
        assert "handoff.validation" in q
        assert "failed" in q
        assert "json" in q

    def test_handoff_failures_by_direction(self, queries: A2AQueries) -> None:
        q = queries.handoff_failures_by_direction("inbound")
        assert "handoff.validation.inbound.failed" in q
        assert 'direction = "inbound"' in q

    def test_dropped_artifacts(self, queries: A2AQueries) -> None:
        q = queries.dropped_artifacts()
        assert "gap_parity" in q
        assert "missing_feature" in q

    def test_finalize_failure_trend(self, queries: A2AQueries) -> None:
        q = queries.finalize_failure_trend()
        assert "count_over_time" in q
        assert "FINALIZE_VERIFY" in q
        assert "1h" in q

    def test_boundary_enforcement_errors(self, queries: A2AQueries) -> None:
        q = queries.boundary_enforcement_errors()
        assert "Boundary enforcement failure" in q


class TestAllQueriesDict:
    """Tests for the all_queries() convenience method."""

    def test_returns_all_expected_panels(self, queries: A2AQueries) -> None:
        all_q = queries.all_queries()
        expected_keys = {
            "blocked_span_hotspot",
            "blocked_spans_detail",
            "gate_failures",
            "finalize_outcomes",
            "handoff_validation_failures",
            "dropped_artifacts",
            "finalize_failure_trend",
            "boundary_enforcement_errors",
        }
        assert set(all_q.keys()) == expected_keys

    def test_each_query_has_required_fields(self, queries: A2AQueries) -> None:
        for name, panel in queries.all_queries().items():
            assert "datasource" in panel, f"{name} missing datasource"
            assert "query" in panel, f"{name} missing query"
            assert "description" in panel, f"{name} missing description"
            assert "action" in panel, f"{name} missing action"
            assert panel["datasource"] in ("tempo", "loki"), (
                f"{name} has invalid datasource: {panel['datasource']}"
            )

    def test_each_query_has_actionable_description(self, queries: A2AQueries) -> None:
        """Day 6 requirement: every panel maps to a concrete operational action."""
        for name, panel in queries.all_queries().items():
            assert len(panel["description"]) > 10, f"{name} description too short"
            assert len(panel["action"]) > 10, f"{name} action too short"


class TestDashboardJSON:
    """Validate the Grafana dashboard JSON is well-formed."""

    @pytest.fixture
    def dashboard(self) -> dict:
        path = Path(__file__).parent.parent / "k8s" / "observability" / "dashboards" / "a2a-governance.json"
        with open(path) as fh:
            return json.load(fh)

    def test_has_uid(self, dashboard: dict) -> None:
        assert dashboard["uid"] == "contextcore-a2a-governance"

    def test_has_panels(self, dashboard: dict) -> None:
        assert len(dashboard["panels"]) == 8

    def test_panels_have_titles(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            assert "title" in panel
            assert len(panel["title"]) > 0

    def test_panels_have_descriptions(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            assert "description" in panel
            assert len(panel["description"]) > 0

    def test_panels_have_datasources(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            ds = panel.get("datasource", {})
            if ds:
                assert ds.get("type") in ("tempo", "loki"), (
                    f"Panel '{panel['title']}' has unexpected datasource type"
                )

    def test_panels_have_targets(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            assert "targets" in panel
            assert len(panel["targets"]) > 0

    def test_has_project_template_variable(self, dashboard: dict) -> None:
        variables = dashboard.get("templating", {}).get("list", [])
        names = [v["name"] for v in variables]
        assert "project" in names

    def test_has_contextcore_tag(self, dashboard: dict) -> None:
        assert "contextcore" in dashboard["tags"]
        assert "a2a" in dashboard["tags"]
