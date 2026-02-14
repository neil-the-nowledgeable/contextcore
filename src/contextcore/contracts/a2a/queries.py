"""
Baseline observability queries for A2A governance.

Provides pre-built TraceQL and LogQL queries that answer Day 6 operational
questions:

1. **Blocked-span hotspot** — Which phases block most often?
2. **Handoff validation failures** — Which contracts fail inbound/outbound?
3. **Dropped artifacts** — Which artifacts are missing after PARSE/TRANSFORM?
4. **Partial/failed finalize trend** — How often does FINALIZE_VERIFY fail?

Each function returns a query string suitable for Grafana Tempo or Loki.
The queries use the span attributes defined in the PI-101-002 trace model
and the event types emitted by the boundary enforcement module.

Usage::

    from contextcore.contracts.a2a.queries import A2AQueries

    q = A2AQueries(project_id="contextcore")
    print(q.blocked_span_hotspot())
    print(q.handoff_validation_failures())
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class A2AQueries:
    """
    Pre-built observability queries for A2A governance.

    All queries are parameterized by ``project_id`` and return strings
    that can be pasted into Grafana explore or used in dashboard panels.
    """

    project_id: str = "contextcore"

    # ------------------------------------------------------------------
    # TraceQL queries (Tempo)
    # ------------------------------------------------------------------

    def blocked_span_hotspot(self) -> str:
        """
        Find all blocked spans grouped by phase.

        Answers: "Which phases are blocking execution most often?"
        Action: Investigate root cause in the most-blocked phase.
        """
        return (
            '{ resource.service.name = "contextcore" '
            f'&& span.project.id = "{self.project_id}" '
            '&& span.task.status = "blocked" }'
        )

    def blocked_spans_with_reason(self) -> str:
        """
        Find blocked spans including their blocked_reason and next_action.

        Answers: "What failed, where, why, what next?"
        """
        return (
            '{ resource.service.name = "contextcore" '
            f'&& span.project.id = "{self.project_id}" '
            '&& span.task.status = "blocked" } '
            '| select(span.task.id, span.task.phase, '
            'span.task.blocked_reason, span.task.next_action)'
        )

    def gate_failures(self) -> str:
        """
        Find all failed gate results.

        Answers: "Which gates are failing and how severe?"
        Action: Address critical/error gates before proceeding.
        """
        return (
            '{ resource.service.name = "contextcore" '
            f'&& span.project.id = "{self.project_id}" '
            '&& span.gate.result = "fail" }'
        )

    def gate_results_by_phase(self, phase: str) -> str:
        """
        Find all gate results for a specific phase.

        Args:
            phase: Phase name (e.g. ``CONTRACT_INTEGRITY``).
        """
        return (
            '{ resource.service.name = "contextcore" '
            f'&& span.project.id = "{self.project_id}" '
            f'&& span.gate.phase = "{phase}" }}'
        )

    def finalize_outcomes(self) -> str:
        """
        Find all FINALIZE_VERIFY spans and their outcomes.

        Answers: "How often does finalization succeed vs fail/block?"
        Action: If failure rate is rising, investigate upstream gates.
        """
        return (
            '{ resource.service.name = "contextcore" '
            f'&& span.project.id = "{self.project_id}" '
            '&& span.task.phase = "FINALIZE_VERIFY" }'
        )

    def trace_by_id(self, trace_id: str) -> str:
        """
        Fetch a full trace by ID.

        Args:
            trace_id: The trace/task ID (e.g. ``PI-101-002``).
        """
        return (
            '{ resource.service.name = "contextcore" '
            f'&& span.task.id = "{trace_id}" }}'
        )

    def spans_by_parent(self, parent_task_id: str) -> str:
        """Find all child spans of a parent task."""
        return (
            '{ resource.service.name = "contextcore" '
            f'&& span.task.parent_id = "{parent_task_id}" }}'
        )

    # ------------------------------------------------------------------
    # LogQL queries (Loki)
    # ------------------------------------------------------------------

    def handoff_validation_failures(self) -> str:
        """
        Find all handoff validation failure events.

        Answers: "Which handoffs are being rejected and why?"
        Action: Fix the payload producer for the failing contract.
        """
        return (
            '{job="contextcore"} '
            '|= "handoff.validation" '
            '|= "failed" '
            '| json '
            '| event_type =~ "handoff.validation.*.failed"'
        )

    def handoff_failures_by_direction(self, direction: str = "outbound") -> str:
        """
        Filter handoff failures by direction.

        Args:
            direction: ``"outbound"`` or ``"inbound"``.
        """
        return (
            '{job="contextcore"} '
            f'|= "handoff.validation.{direction}.failed" '
            '| json '
            f'| direction = "{direction}"'
        )

    def dropped_artifacts(self) -> str:
        """
        Find gap parity failures (artifacts dropped during PARSE/TRANSFORM).

        Answers: "Which artifacts were silently dropped before implementation?"
        Action: Re-run PARSE/TRANSFORM or investigate the parser.
        """
        return (
            '{job="contextcore"} '
            '|= "gap_parity" '
            '|= "missing_feature" '
            '| json'
        )

    def finalize_failure_trend(self) -> str:
        """
        Count finalize failures over time for trend analysis.

        Answers: "Is the finalize failure rate improving or worsening?"
        """
        return (
            'count_over_time('
            '{job="contextcore"} '
            '|= "FINALIZE_VERIFY" '
            '|= "fail" '
            '| json '
            '[1h])'
        )

    def boundary_enforcement_errors(self) -> str:
        """
        Find all boundary enforcement errors (any contract type).

        Answers: "How many invalid payloads are being caught at boundaries?"
        """
        return (
            '{job="contextcore"} '
            '|= "Boundary enforcement failure" '
            '| json'
        )

    # ------------------------------------------------------------------
    # Convenience: all queries as a dict (for dashboard generation)
    # ------------------------------------------------------------------

    def all_queries(self) -> dict[str, dict[str, str]]:
        """
        Return all queries as a dict keyed by panel name.

        Each value contains ``datasource`` (``"tempo"`` or ``"loki"``),
        ``query``, and ``description``.
        """
        return {
            "blocked_span_hotspot": {
                "datasource": "tempo",
                "query": self.blocked_span_hotspot(),
                "description": "Phases that block execution most often.",
                "action": "Investigate root cause in the most-blocked phase.",
            },
            "blocked_spans_detail": {
                "datasource": "tempo",
                "query": self.blocked_spans_with_reason(),
                "description": "Blocked spans with reason and next action.",
                "action": "Follow next_action to unblock.",
            },
            "gate_failures": {
                "datasource": "tempo",
                "query": self.gate_failures(),
                "description": "Failed gate results by phase and severity.",
                "action": "Address critical/error gates before proceeding.",
            },
            "finalize_outcomes": {
                "datasource": "tempo",
                "query": self.finalize_outcomes(),
                "description": "FINALIZE_VERIFY span outcomes over time.",
                "action": "If failure rate is rising, investigate upstream.",
            },
            "handoff_validation_failures": {
                "datasource": "loki",
                "query": self.handoff_validation_failures(),
                "description": "Handoff payloads rejected at boundaries.",
                "action": "Fix the payload producer for the failing contract.",
            },
            "dropped_artifacts": {
                "datasource": "loki",
                "query": self.dropped_artifacts(),
                "description": "Artifacts dropped during PARSE/TRANSFORM.",
                "action": "Re-run parser or investigate gap parity.",
            },
            "finalize_failure_trend": {
                "datasource": "loki",
                "query": self.finalize_failure_trend(),
                "description": "Finalize failure count over time (1h buckets).",
                "action": "Monitor trend; investigate if rising.",
            },
            "boundary_enforcement_errors": {
                "datasource": "loki",
                "query": self.boundary_enforcement_errors(),
                "description": "All boundary enforcement rejections.",
                "action": "Fix producers sending invalid payloads.",
            },
        }
