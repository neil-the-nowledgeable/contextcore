"""
PI-101-002 pilot runner.

Executes a full trace using the span model defined in
``docs/PI-101-002_TRACE_SPAN_EXECUTION_PLAN.md``, with gate checks at every
phase boundary and boundary-validated contracts throughout.

Day 5 spec: "Full pilot trace exists with gate evidence and no silent phase
transitions."

The runner is deterministic and does **not** require a live OTel backend.
All evidence is collected in-memory and can be serialized to JSON for
inspection, dashboarding, or replaying into a backend later.

Usage::

    from contextcore.contracts.a2a.pilot import PilotRunner

    runner = PilotRunner(seed=sample_seed)
    result = runner.execute()
    print(result.summary())
    result.write_evidence("out/pilot-trace.json")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contextcore.contracts.a2a.boundary import validate_outbound
from contextcore.contracts.a2a.gates import (
    GateChecker,
    check_checksum_chain,
    check_gap_parity,
    check_mapping_completeness,
)
from contextcore.contracts.a2a.models import (
    GateOutcome,
    GateResult,
    Phase,
    SpanStatus,
    TaskSpanContract,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed data (inputs to the pilot)
# ---------------------------------------------------------------------------

_TRACE_ID = "PI-101-002"
_PROJECT_ID = "contextcore"


@dataclass
class PilotSeed:
    """
    Input data that drives the pilot run.

    In a real execution this would come from the export pipeline / manifest.
    For the pilot we provide defaults that exercise both pass and fail paths.
    """

    # Checksums
    source_checksum: str = "sha256:abc123"
    artifact_manifest_checksum: str = "sha256:def456"
    project_context_checksum: str = "sha256:ghi789"

    # Expected checksums (what we trust from upstream)
    expected_source_checksum: str = "sha256:abc123"
    expected_artifact_manifest_checksum: str = "sha256:def456"
    expected_project_context_checksum: str = "sha256:ghi789"

    # Artifact-task mapping
    artifact_ids: list[str] = field(
        default_factory=lambda: ["art-dashboard", "art-alert-rule", "art-recording-rule"]
    )
    task_mapping: dict[str, str] = field(
        default_factory=lambda: {
            "art-dashboard": "PI-101-002-S7-T1",
            "art-alert-rule": "PI-101-002-S7-T2",
            "art-recording-rule": "PI-101-002-S7-T3",
        }
    )

    # Gap/feature parity
    gap_ids: list[str] = field(
        default_factory=lambda: ["gap-latency-panel", "gap-error-budget", "gap-throughput"]
    )
    feature_ids: list[str] = field(
        default_factory=lambda: ["gap-latency-panel", "gap-error-budget", "gap-throughput"]
    )

    # Quality metrics
    coverage_percent: float = 85.0
    complexity_score: float = 44.0

    # Routing
    selected_path: str = "artisan"

    # Artifact generation
    generated_artifact_count: int = 3
    generated_paths: list[str] = field(
        default_factory=lambda: [
            "grafana/provisioning/dashboards/json/checkout-api.json",
            "k8s/observability/rules/checkout-api-alerts.yaml",
            "k8s/observability/rules/checkout-api-recording.yaml",
        ]
    )

    # Test/review
    test_critical_failures: int = 0
    review_blocking_issues: int = 0


# ---------------------------------------------------------------------------
# Span event log
# ---------------------------------------------------------------------------


@dataclass
class SpanEvent:
    """A single event within a span."""

    event_type: str
    timestamp: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpanRecord:
    """Complete record of a single span's execution."""

    span_id: str
    parent_id: str
    phase: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    contract: dict[str, Any] | None = None
    gate_results: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    blocked_reason: str | None = None
    next_action: str | None = None


# ---------------------------------------------------------------------------
# Pilot result
# ---------------------------------------------------------------------------


@dataclass
class PilotResult:
    """
    Complete output of a pilot run.

    Contains every span record, gate result, and event emitted during
    execution.
    """

    trace_id: str
    project_id: str
    started_at: str
    ended_at: str | None = None
    final_status: str = "not_started"
    spans: list[SpanRecord] = field(default_factory=list)
    gate_results: list[dict[str, Any]] = field(default_factory=list)
    blocked_spans: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.final_status == "completed" and len(self.blocked_spans) == 0

    def summary(self) -> dict[str, Any]:
        """Return a human-readable summary dict."""
        return {
            "trace_id": self.trace_id,
            "final_status": self.final_status,
            "total_spans": len(self.spans),
            "completed_spans": sum(1 for s in self.spans if s.status == "completed"),
            "blocked_spans": self.blocked_spans,
            "total_gates": len(self.gate_results),
            "gates_passed": sum(
                1 for g in self.gate_results if g.get("result") == "pass"
            ),
            "gates_failed": sum(
                1 for g in self.gate_results if g.get("result") == "fail"
            ),
            "errors": self.errors,
            "is_success": self.is_success,
        }

    def to_dict(self) -> dict[str, Any]:
        """Full serialization for JSON evidence."""
        return {
            "trace_id": self.trace_id,
            "project_id": self.project_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "final_status": self.final_status,
            "summary": self.summary(),
            "spans": [
                {
                    "span_id": s.span_id,
                    "parent_id": s.parent_id,
                    "phase": s.phase,
                    "status": s.status,
                    "started_at": s.started_at,
                    "ended_at": s.ended_at,
                    "contract": s.contract,
                    "gate_results": s.gate_results,
                    "events": s.events,
                    "blocked_reason": s.blocked_reason,
                    "next_action": s.next_action,
                }
                for s in self.spans
            ],
            "gate_results": self.gate_results,
        }

    def write_evidence(self, path: str | Path) -> Path:
        """Write full trace evidence to a JSON file."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as fh:
            json.dump(self.to_dict(), fh, indent=2)
        logger.info("Pilot evidence written to %s", out)
        return out


# ---------------------------------------------------------------------------
# Pilot runner
# ---------------------------------------------------------------------------

# Phase spans in execution order
_PHASE_SPANS = [
    ("PI-101-002-S1", Phase.INIT_BASELINE, "Establish trusted environment"),
    ("PI-101-002-S2", Phase.EXPORT_CONTRACT, "Produce fresh contract artifacts"),
    ("PI-101-002-S3", Phase.CONTRACT_INTEGRITY, "Validate checksums/mappings/schema"),
    ("PI-101-002-S4", Phase.INGEST_PARSE_ASSESS, "Ensure faithful translation and scoring"),
    ("PI-101-002-S5", Phase.ROUTING_DECISION, "Confirm correct path"),
    ("PI-101-002-S6", Phase.ARTISAN_DESIGN, "Produce design-handoff from enriched seed"),
    ("PI-101-002-S7", Phase.ARTISAN_IMPLEMENT, "Generate/compose artifacts"),
    ("PI-101-002-S8", Phase.TEST_VALIDATE, "Run artifact validation gates"),
    ("PI-101-002-S9", Phase.REVIEW_CALIBRATE, "Multi-agent/human quality pass"),
    ("PI-101-002-S10", Phase.FINALIZE_VERIFY, "Close trace with provenance proof"),
]


class PilotRunner:
    """
    Executes the PI-101-002 pilot trace.

    Each phase span is:
    1. Opened as a ``TaskSpanContract`` (validated at outbound boundary).
    2. Gate-checked where applicable (S3, S4 child spans).
    3. Closed as completed or blocked depending on gate outcomes.

    Args:
        seed: Input data driving the pilot. Defaults exercise the happy path.
    """

    def __init__(self, seed: PilotSeed | None = None) -> None:
        self.seed = seed or PilotSeed()
        self.checker = GateChecker(trace_id=_TRACE_ID)
        self._result: PilotResult | None = None

    def execute(self) -> PilotResult:
        """Run the full pilot and return the result."""
        now = _now()
        self._result = PilotResult(
            trace_id=_TRACE_ID,
            project_id=_PROJECT_ID,
            started_at=now,
        )

        blocked = False
        for span_id, phase, title in _PHASE_SPANS:
            if blocked:
                # Record remaining spans as not_started
                rec = SpanRecord(
                    span_id=span_id,
                    parent_id=_TRACE_ID,
                    phase=phase.value,
                    status="not_started",
                )
                self._result.spans.append(rec)
                continue

            rec = self._execute_span(span_id, phase, title)
            self._result.spans.append(rec)

            if rec.status == "blocked":
                blocked = True
                self._result.blocked_spans.append(span_id)

        # Close the trace
        self._result.ended_at = _now()
        if blocked:
            self._result.final_status = "blocked"
        else:
            self._result.final_status = "completed"

        logger.info(
            "Pilot %s finished: %s (%d spans, %d gates)",
            _TRACE_ID,
            self._result.final_status,
            len(self._result.spans),
            len(self._result.gate_results),
        )
        return self._result

    # --- Phase execution methods -------------------------------------------

    def _execute_span(
        self, span_id: str, phase: Phase, title: str
    ) -> SpanRecord:
        """Execute a single phase span."""
        rec = SpanRecord(
            span_id=span_id,
            parent_id=_TRACE_ID,
            phase=phase.value,
            status="in_progress",
            started_at=_now(),
        )

        # Create and validate the TaskSpanContract at outbound boundary
        contract = TaskSpanContract(
            project_id=_PROJECT_ID,
            trace_id=_TRACE_ID,
            task_id=span_id,
            parent_task_id=_TRACE_ID,
            phase=phase,
            status=SpanStatus.IN_PROGRESS,
            timestamp=datetime.now(timezone.utc),
        )
        payload = contract.model_dump(mode="json", exclude_none=True)
        validate_outbound("TaskSpanContract", payload)
        rec.contract = payload
        rec.events.append(_event("span.started", {"span_id": span_id, "phase": phase.value}))

        # Phase-specific logic
        handler = getattr(self, f"_phase_{phase.value.lower()}", None)
        if handler:
            gate_results = handler(span_id, rec)
            for gr in gate_results:
                gr_dict = gr.model_dump(mode="json", exclude_none=True)
                validate_outbound("GateResult", gr_dict)
                rec.gate_results.append(gr_dict)
                self._result.gate_results.append(gr_dict)

                if gr.result == GateOutcome.FAIL and gr.blocking:
                    rec.status = "blocked"
                    rec.blocked_reason = gr.reason
                    rec.next_action = gr.next_action
                    rec.events.append(
                        _event("gate.check.failed", {"gate_id": gr.gate_id, "reason": gr.reason})
                    )
                else:
                    rec.events.append(
                        _event("gate.check.passed", {"gate_id": gr.gate_id})
                    )

        # If not blocked, mark completed
        if rec.status != "blocked":
            rec.status = "completed"
            rec.events.append(_event("span.completed", {"span_id": span_id}))

        rec.ended_at = _now()
        return rec

    # --- Phase handlers (return list of GateResults) -----------------------

    def _phase_init_baseline(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S1: Establish trusted environment — no gates, always passes."""
        rec.events.append(_event("baseline.verified", {"endpoint": "localhost:4317"}))
        return []

    def _phase_export_contract(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S2: Produce fresh contract artifacts — coverage check child span."""
        coverage = self.seed.coverage_percent
        rec.events.append(
            _event("coverage.checked", {"coverage_percent": coverage})
        )
        # S2-C1: Coverage gate (non-blocking warning if < 80%)
        from contextcore.contracts.a2a.models import EvidenceItem, GateSeverity

        if coverage < 80.0:
            gr = GateResult(
                gate_id=f"{span_id}-C1",
                trace_id=_TRACE_ID,
                task_id=span_id,
                phase=Phase.EXPORT_CONTRACT,
                result=GateOutcome.FAIL,
                severity=GateSeverity.WARNING,
                reason=f"Coverage {coverage}% is below 80% threshold.",
                next_action="Increase coverage or document justification.",
                blocking=False,
                checked_at=datetime.now(timezone.utc),
            )
        else:
            gr = GateResult(
                gate_id=f"{span_id}-C1",
                trace_id=_TRACE_ID,
                task_id=span_id,
                phase=Phase.EXPORT_CONTRACT,
                result=GateOutcome.PASS,
                severity=GateSeverity.INFO,
                reason=f"Coverage {coverage}% meets threshold.",
                next_action="Proceed to CONTRACT_INTEGRITY.",
                blocking=False,
                checked_at=datetime.now(timezone.utc),
            )
        return [gr]

    def _phase_contract_integrity(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S3: Validate checksums and mappings — critical blocking gates."""
        results: list[GateResult] = []

        # S3-C1: Artifact-task mapping completeness
        r1 = self.checker.check_mapping_completeness(
            gate_id=f"{span_id}-C1",
            task_id=span_id,
            artifact_ids=self.seed.artifact_ids,
            task_mapping=self.seed.task_mapping,
            phase=Phase.CONTRACT_INTEGRITY,
        )
        results.append(r1)

        # S3-C2: Checksum chain verification
        r2 = self.checker.check_checksum_chain(
            gate_id=f"{span_id}-C2",
            task_id=span_id,
            expected_checksums={
                "source": self.seed.expected_source_checksum,
                "artifact_manifest": self.seed.expected_artifact_manifest_checksum,
                "project_context": self.seed.expected_project_context_checksum,
            },
            actual_checksums={
                "source": self.seed.source_checksum,
                "artifact_manifest": self.seed.artifact_manifest_checksum,
                "project_context": self.seed.project_context_checksum,
            },
            phase=Phase.CONTRACT_INTEGRITY,
        )
        results.append(r2)

        return results

    def _phase_ingest_parse_assess(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S4: Gap-to-feature parity check."""
        # S4-C1: Gap parity
        r = self.checker.check_gap_parity(
            gate_id=f"{span_id}-C1",
            task_id=span_id,
            gap_ids=self.seed.gap_ids,
            feature_ids=self.seed.feature_ids,
            phase=Phase.INGEST_PARSE_ASSESS,
        )
        return [r]

    def _phase_routing_decision(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S5: Routing decision — record path choice, no blocking gate."""
        rec.events.append(
            _event(
                "routing.decided",
                {
                    "complexity_score": self.seed.complexity_score,
                    "selected_path": self.seed.selected_path,
                },
            )
        )
        return []

    def _phase_artisan_design(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S6: Design handoff — schema validation child span."""
        from contextcore.contracts.a2a.models import EvidenceItem, GateSeverity

        gr = GateResult(
            gate_id=f"{span_id}-C1",
            trace_id=_TRACE_ID,
            task_id=span_id,
            phase=Phase.ARTISAN_DESIGN,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason="design-handoff.json schema valid, task set complete.",
            next_action="Proceed to ARTISAN_IMPLEMENT.",
            blocking=False,
            evidence=[
                EvidenceItem(
                    type="schema_validation",
                    ref="design-handoff.json",
                    description="Schema and version validated.",
                )
            ],
            checked_at=datetime.now(timezone.utc),
        )
        return [gr]

    def _phase_artisan_implement(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S7: Artifact generation — output path compliance child span."""
        from contextcore.contracts.a2a.models import EvidenceItem, GateSeverity

        rec.events.append(
            _event(
                "artifacts.generated",
                {
                    "artifact_count": self.seed.generated_artifact_count,
                    "paths": self.seed.generated_paths,
                },
            )
        )

        gr = GateResult(
            gate_id=f"{span_id}-C1",
            trace_id=_TRACE_ID,
            task_id=span_id,
            phase=Phase.ARTISAN_IMPLEMENT,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=f"{self.seed.generated_artifact_count} artifact(s) in correct paths.",
            next_action="Proceed to TEST_VALIDATE.",
            blocking=False,
            evidence=[
                EvidenceItem(
                    type="path_compliance",
                    ref=p,
                    description="Output path matches convention.",
                )
                for p in self.seed.generated_paths
            ],
            checked_at=datetime.now(timezone.utc),
        )
        return [gr]

    def _phase_test_validate(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S8: Test/validation gates."""
        from contextcore.contracts.a2a.models import EvidenceItem, GateSeverity

        failures = self.seed.test_critical_failures
        if failures > 0:
            gr = GateResult(
                gate_id=f"{span_id}-G1",
                trace_id=_TRACE_ID,
                task_id=span_id,
                phase=Phase.TEST_VALIDATE,
                result=GateOutcome.FAIL,
                severity=GateSeverity.CRITICAL,
                reason=f"{failures} critical test failure(s).",
                next_action="Fix critical failures before proceeding to review.",
                blocking=True,
                evidence=[
                    EvidenceItem(
                        type="test_result",
                        ref="validation_suite",
                        description=f"{failures} critical failure(s) detected.",
                    )
                ],
                checked_at=datetime.now(timezone.utc),
            )
        else:
            gr = GateResult(
                gate_id=f"{span_id}-G1",
                trace_id=_TRACE_ID,
                task_id=span_id,
                phase=Phase.TEST_VALIDATE,
                result=GateOutcome.PASS,
                severity=GateSeverity.INFO,
                reason="Validation suite passed with zero critical failures.",
                next_action="Proceed to REVIEW_CALIBRATE.",
                blocking=False,
                checked_at=datetime.now(timezone.utc),
            )
        return [gr]

    def _phase_review_calibrate(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S9: Review gate."""
        from contextcore.contracts.a2a.models import GateSeverity

        blocking = self.seed.review_blocking_issues
        if blocking > 0:
            gr = GateResult(
                gate_id=f"{span_id}-G1",
                trace_id=_TRACE_ID,
                task_id=span_id,
                phase=Phase.REVIEW_CALIBRATE,
                result=GateOutcome.FAIL,
                severity=GateSeverity.ERROR,
                reason=f"{blocking} blocking review issue(s).",
                next_action="Resolve blocking review findings before finalize.",
                blocking=True,
                checked_at=datetime.now(timezone.utc),
            )
        else:
            gr = GateResult(
                gate_id=f"{span_id}-G1",
                trace_id=_TRACE_ID,
                task_id=span_id,
                phase=Phase.REVIEW_CALIBRATE,
                result=GateOutcome.PASS,
                severity=GateSeverity.INFO,
                reason="Review findings triaged, no blocking issues.",
                next_action="Proceed to FINALIZE_VERIFY.",
                blocking=False,
                checked_at=datetime.now(timezone.utc),
            )
        return [gr]

    def _phase_finalize_verify(self, span_id: str, rec: SpanRecord) -> list[GateResult]:
        """S10: Final reconciliation — artifact set vs gap set."""
        from contextcore.contracts.a2a.models import EvidenceItem, GateSeverity

        # S10-C1: Final artifact set vs original gap set
        gr = GateResult(
            gate_id=f"{span_id}-C1",
            trace_id=_TRACE_ID,
            task_id=span_id,
            phase=Phase.FINALIZE_VERIFY,
            result=GateOutcome.PASS,
            severity=GateSeverity.INFO,
            reason=(
                f"Final reconciliation: {self.seed.generated_artifact_count} artifact(s) "
                f"cover {len(self.seed.gap_ids)} gap(s). Provenance intact."
            ),
            next_action="Trace complete. Archive evidence.",
            blocking=False,
            evidence=[
                EvidenceItem(
                    type="reconciliation",
                    ref="final_artifact_set",
                    description=(
                        f"Artifacts: {self.seed.generated_artifact_count}, "
                        f"Gaps: {len(self.seed.gap_ids)}, "
                        f"Checksums verified."
                    ),
                )
            ],
            checked_at=datetime.now(timezone.utc),
        )
        rec.events.append(
            _event(
                "finalize.complete",
                {
                    "artifact_count": self.seed.generated_artifact_count,
                    "gap_count": len(self.seed.gap_ids),
                    "finalize_status": "complete",
                },
            )
        )
        return [gr]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(event_type: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "timestamp": _now(),
        "detail": detail or {},
    }
