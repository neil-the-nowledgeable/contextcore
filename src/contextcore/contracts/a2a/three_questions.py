"""
Three Questions diagnostic — structured issue analysis for the export pipeline.

Implements **Principle 6** from the Export Pipeline Analysis Guide:

    1. **Is the contract complete?** (Export layer)
    2. **Was the contract faithfully translated?** (Plan Ingestion layer)
    3. **Was the translated plan faithfully executed?** (Artisan layer)

The key insight: *"If the answer to question 1 is 'no', fixing anything in
questions 2 or 3 is wasted effort. Always start from the source."*

The diagnostic runs questions in order and stops at the first failure,
producing a clear "start here" recommendation.

Usage::

    from contextcore.contracts.a2a.three_questions import ThreeQuestionsDiagnostic

    diag = ThreeQuestionsDiagnostic(
        export_dir="out/enrichment-validation",
        ingestion_dir="out/plan-ingestion",    # optional
        artisan_dir="out/artisan",             # optional
    )
    result = diag.run()
    print(result.to_text())

CLI::

    contextcore contract a2a-diagnose out/enrichment-validation
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from contextcore.contracts.a2a.models import (
    EvidenceItem,
    GateOutcome,
    GateResult,
    GateSeverity,
    Phase,
)
from contextcore.contracts.a2a.pipeline_checker import PipelineChecker, PipelineCheckReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class QuestionStatus(str, Enum):
    """Status of a diagnostic question."""
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"
    NOT_REACHED = "not_reached"


@dataclass
class QuestionResult:
    """Result of a single diagnostic question."""
    number: int
    title: str
    layer: str
    status: QuestionStatus
    checks: list[CheckResult] = field(default_factory=list)
    recommendation: str = ""

    @property
    def passed(self) -> bool:
        return self.status == QuestionStatus.PASS

    @property
    def failed(self) -> bool:
        return self.status == QuestionStatus.FAIL


@dataclass
class CheckResult:
    """Individual check within a question."""
    name: str
    passed: bool
    detail: str
    severity: str = "error"  # error, warning, info


@dataclass
class DiagnosticResult:
    """Complete result of the Three Questions diagnostic."""
    export_dir: str
    project_id: str
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    questions: list[QuestionResult] = field(default_factory=list)
    start_here: str = ""
    pipeline_report: Optional[PipelineCheckReport] = None

    @property
    def all_passed(self) -> bool:
        return all(q.passed for q in self.questions if q.status != QuestionStatus.NOT_REACHED)

    @property
    def first_failure(self) -> Optional[QuestionResult]:
        for q in self.questions:
            if q.failed:
                return q
        return None

    def summary(self) -> dict[str, Any]:
        """Return a JSON-serializable summary dict."""
        return {
            "export_dir": self.export_dir,
            "project_id": self.project_id,
            "checked_at": self.checked_at,
            "all_passed": self.all_passed,
            "start_here": self.start_here,
            "questions": [
                {
                    "number": q.number,
                    "title": q.title,
                    "layer": q.layer,
                    "status": q.status.value,
                    "checks_passed": sum(1 for c in q.checks if c.passed),
                    "checks_total": len(q.checks),
                    "recommendation": q.recommendation,
                    "checks": [
                        {
                            "name": c.name,
                            "passed": c.passed,
                            "detail": c.detail,
                            "severity": c.severity,
                        }
                        for c in q.checks
                    ],
                }
                for q in self.questions
            ],
        }

    def to_text(self) -> str:
        """Human-readable diagnostic report."""
        lines: list[str] = []
        verdict = "ALL CLEAR" if self.all_passed else "ISSUE FOUND"
        lines.append(f"Three Questions Diagnostic: {verdict}")
        lines.append(f"  Project:   {self.project_id}")
        lines.append(f"  Directory: {self.export_dir}")
        lines.append(f"  Checked:   {self.checked_at}")
        lines.append("")

        for q in self.questions:
            icon = {
                QuestionStatus.PASS: "PASS",
                QuestionStatus.FAIL: "FAIL",
                QuestionStatus.SKIPPED: "SKIP",
                QuestionStatus.NOT_REACHED: "----",
            }[q.status]

            lines.append(f"  Q{q.number}. {q.title}  [{icon}]")
            lines.append(f"      Layer: {q.layer}")

            if q.status == QuestionStatus.NOT_REACHED:
                lines.append(f"      (Not reached — earlier question failed)")
                lines.append("")
                continue

            passed = sum(1 for c in q.checks if c.passed)
            lines.append(f"      Checks: {passed}/{len(q.checks)} passed")

            for c in q.checks:
                check_icon = "ok" if c.passed else "FAIL" if c.severity == "error" else "WARN"
                lines.append(f"        [{check_icon}] {c.name}")
                if not c.passed:
                    lines.append(f"              {c.detail}")

            if q.recommendation:
                lines.append(f"      Recommendation: {q.recommendation}")
            lines.append("")

        if self.start_here:
            lines.append(f"  >>> START HERE: {self.start_here}")
            lines.append("")

        return "\n".join(lines)

    def write_json(self, path: str | Path) -> Path:
        """Write the diagnostic result as JSON."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as fh:
            json.dump(self.summary(), fh, indent=2, default=str)
        return out


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------


class ThreeQuestionsDiagnostic:
    """
    Structured diagnostic that walks through the Three Questions in order.

    Args:
        export_dir: Path to the export output directory.
        ingestion_dir: Optional path to plan ingestion output directory.
        artisan_dir: Optional path to artisan workflow output directory.
        trace_id: Optional trace ID for gate context.
    """

    def __init__(
        self,
        export_dir: str | Path,
        *,
        ingestion_dir: str | Path | None = None,
        artisan_dir: str | Path | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.export_dir = Path(export_dir)
        self.ingestion_dir = Path(ingestion_dir) if ingestion_dir else None
        self.artisan_dir = Path(artisan_dir) if artisan_dir else None
        self.trace_id = trace_id

        self._metadata: dict[str, Any] = {}

    # ---- Loading -----------------------------------------------------------

    def _load_metadata(self) -> None:
        meta_path = self.export_dir / "onboarding-metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"No onboarding-metadata.json found in {self.export_dir}. "
                "Run `contextcore manifest export --emit-onboarding` first."
            )
        with open(meta_path) as fh:
            self._metadata = json.load(fh)

    # ---- Q1: Is the contract complete? -------------------------------------

    def _question_1(self) -> QuestionResult:
        """
        Q1: Is the contract complete? (Export layer)

        Checks:
        - Pipeline checker gates (structural, checksum, provenance, gaps, calibration)
        - Artifact manifest lists every artifact needed (coverage completeness)
        - Derivation rules populated with real values
        - Parameter schema completeness
        """
        q = QuestionResult(
            number=1,
            title="Is the contract complete?",
            layer="Export",
            status=QuestionStatus.PASS,
        )

        # Run pipeline checker for foundational gates
        try:
            checker = PipelineChecker(self.export_dir, trace_id=self.trace_id)
            pipeline_report = checker.run()
        except FileNotFoundError as exc:
            q.status = QuestionStatus.FAIL
            q.checks.append(CheckResult(
                name="Export output exists",
                passed=False,
                detail=str(exc),
            ))
            q.recommendation = "Run `contextcore manifest export --emit-onboarding` to generate export output."
            return q

        # Translate pipeline gates to check results
        for gate in pipeline_report.gates:
            is_pass = gate.result == GateOutcome.PASS
            q.checks.append(CheckResult(
                name=gate.gate_id.split("-", 1)[-1] if "-" in gate.gate_id else gate.gate_id,
                passed=is_pass,
                detail=gate.reason or "",
                severity="error" if gate.blocking and not is_pass else "warning" if not is_pass else "info",
            ))
            if not is_pass and gate.blocking:
                q.status = QuestionStatus.FAIL

        # Additional Q1 checks beyond the pipeline checker

        # Check: Does coverage.gaps list all needed artifacts?
        coverage = self._metadata.get("coverage", {})
        total_required = coverage.get("totalRequired", 0)
        gaps = coverage.get("gaps", [])
        existing = coverage.get("totalExisting", 0)
        if total_required == 0:
            q.checks.append(CheckResult(
                name="artifact-manifest-populated",
                passed=False,
                detail="No required artifacts found in coverage. Is the artifact manifest empty?",
            ))
            q.status = QuestionStatus.FAIL
        else:
            q.checks.append(CheckResult(
                name="artifact-manifest-populated",
                passed=True,
                detail=f"{total_required} required artifact(s): {existing} existing, {len(gaps)} gap(s).",
                severity="info",
            ))

        # Check: Are derivation rules populated?
        derivation_rules = self._metadata.get("derivation_rules", {})
        artifact_types = self._metadata.get("artifact_types", {})
        if artifact_types and not derivation_rules:
            q.checks.append(CheckResult(
                name="derivation-rules-present",
                passed=True,  # Not a hard requirement, but worth noting
                detail="No derivation_rules section — artifact generation will use parameter_sources only.",
                severity="warning",
            ))
        elif derivation_rules:
            empty_rules = [k for k, v in derivation_rules.items() if not v]
            if empty_rules:
                q.checks.append(CheckResult(
                    name="derivation-rules-populated",
                    passed=False,
                    detail=f"Derivation rules empty for: {', '.join(empty_rules)}.",
                    severity="warning",
                ))
            else:
                q.checks.append(CheckResult(
                    name="derivation-rules-populated",
                    passed=True,
                    detail=f"Derivation rules populated for {len(derivation_rules)} artifact type(s).",
                    severity="info",
                ))

        # Check: Parameter schema completeness
        param_schema = self._metadata.get("parameter_schema", {})
        if artifact_types:
            types_without_params = [
                t for t in artifact_types
                if t not in param_schema or not param_schema.get(t)
            ]
            if types_without_params:
                q.checks.append(CheckResult(
                    name="parameter-schema-complete",
                    passed=False,
                    detail=f"Artifact types without parameter schema: {', '.join(types_without_params)}.",
                    severity="warning",
                ))
            else:
                q.checks.append(CheckResult(
                    name="parameter-schema-complete",
                    passed=True,
                    detail=f"Parameter schema defined for all {len(artifact_types)} artifact type(s).",
                    severity="info",
                ))

        # Check: scan-existing coverage (is totalExisting reasonable?)
        if total_required > 0 and existing == 0:
            q.checks.append(CheckResult(
                name="existing-artifact-scan",
                passed=True,  # Not a failure — could be first run
                detail=(
                    "No existing artifacts detected (totalExisting=0). "
                    "If artifacts already exist, re-run with --scan-existing."
                ),
                severity="warning",
            ))

        if q.status == QuestionStatus.FAIL:
            q.recommendation = (
                "Fix the export layer first. Re-run `contextcore manifest export` after "
                "correcting the source manifest. Do NOT proceed to plan ingestion until Q1 passes."
            )

        return q

    # ---- Q2: Was the contract faithfully translated? -----------------------

    def _question_2(self) -> QuestionResult:
        """
        Q2: Was the contract faithfully translated? (Plan Ingestion layer)

        Checks:
        - Plan ingestion output exists
        - PARSE: every gap extracted as a feature
        - ASSESS: complexity score is reasonable
        - TRANSFORM: routing decision matches score
        - REFINE: architectural review ran
        """
        q = QuestionResult(
            number=2,
            title="Was the contract faithfully translated?",
            layer="Plan Ingestion",
            status=QuestionStatus.PASS,
        )

        # Check if ingestion directory was provided and exists
        if not self.ingestion_dir:
            q.status = QuestionStatus.SKIPPED
            q.checks.append(CheckResult(
                name="ingestion-dir-provided",
                passed=False,
                detail="No ingestion directory specified. Use --ingestion-dir to enable Q2 checks.",
                severity="info",
            ))
            q.recommendation = (
                "Provide the plan ingestion output directory to enable translation checks."
            )
            return q

        if not self.ingestion_dir.exists():
            q.status = QuestionStatus.FAIL
            q.checks.append(CheckResult(
                name="ingestion-output-exists",
                passed=False,
                detail=f"Plan ingestion directory not found: {self.ingestion_dir}",
            ))
            q.recommendation = "Run plan ingestion first, then point --ingestion-dir to the output."
            return q

        q.checks.append(CheckResult(
            name="ingestion-output-exists",
            passed=True,
            detail=f"Plan ingestion output found at {self.ingestion_dir}.",
            severity="info",
        ))

        # Look for plan ingestion result files
        result_files = list(self.ingestion_dir.glob("*result*.json")) + \
                       list(self.ingestion_dir.glob("*plan*.json"))

        if not result_files:
            q.checks.append(CheckResult(
                name="ingestion-result-files",
                passed=False,
                detail="No plan ingestion result files found (expected *result*.json or *plan*.json).",
                severity="warning",
            ))
        else:
            q.checks.append(CheckResult(
                name="ingestion-result-files",
                passed=True,
                detail=f"Found {len(result_files)} result file(s): {', '.join(f.name for f in result_files[:5])}.",
                severity="info",
            ))

            # Try to load and analyze the first result
            for rfile in result_files:
                try:
                    with open(rfile) as fh:
                        result_data = json.load(fh)
                    self._check_parse_phase(q, result_data)
                    self._check_assess_phase(q, result_data)
                    self._check_transform_phase(q, result_data)
                    break  # Only need the first valid result
                except (json.JSONDecodeError, KeyError):
                    continue

        # Look for feature files / extracted features
        feature_files = list(self.ingestion_dir.glob("*feature*.json")) + \
                        list(self.ingestion_dir.glob("*feature*.yaml"))
        coverage_gaps = self._metadata.get("coverage", {}).get("gaps", [])

        if feature_files:
            q.checks.append(CheckResult(
                name="features-extracted",
                passed=True,
                detail=f"Found {len(feature_files)} feature file(s) for {len(coverage_gaps)} gap(s).",
                severity="info",
            ))
        elif coverage_gaps:
            q.checks.append(CheckResult(
                name="features-extracted",
                passed=False,
                detail=f"{len(coverage_gaps)} coverage gaps but no feature files found in ingestion output.",
                severity="warning",
            ))

        # Check for architectural review output
        review_files = list(self.ingestion_dir.glob("*review*.json")) + \
                       list(self.ingestion_dir.glob("*refine*.json"))
        if review_files:
            q.checks.append(CheckResult(
                name="architectural-review-ran",
                passed=True,
                detail=f"Architectural review output found: {review_files[0].name}.",
                severity="info",
            ))

        if any(not c.passed and c.severity == "error" for c in q.checks):
            q.status = QuestionStatus.FAIL
            q.recommendation = (
                "Fix translation issues before proceeding to the artisan workflow. "
                "Re-run plan ingestion after correcting the identified problems."
            )

        return q

    def _check_parse_phase(self, q: QuestionResult, data: dict) -> None:
        """Check PARSE phase results from plan ingestion output."""
        features = data.get("features", data.get("parsed_features", []))
        gaps = self._metadata.get("coverage", {}).get("gaps", [])

        if features:
            feature_ids = {f.get("id", f.get("artifact_id", "")) for f in features if isinstance(f, dict)}
            missing = set(gaps) - feature_ids
            if missing:
                q.checks.append(CheckResult(
                    name="parse-coverage",
                    passed=False,
                    detail=f"PARSE missed {len(missing)} gap(s): {', '.join(sorted(missing)[:5])}.",
                ))
            else:
                q.checks.append(CheckResult(
                    name="parse-coverage",
                    passed=True,
                    detail=f"PARSE extracted all {len(gaps)} gap(s) as features.",
                    severity="info",
                ))

    def _check_assess_phase(self, q: QuestionResult, data: dict) -> None:
        """Check ASSESS phase results from plan ingestion output."""
        score = data.get("complexity_score", data.get("assess", {}).get("score"))
        if score is not None:
            reasonable = 0 <= score <= 100
            q.checks.append(CheckResult(
                name="assess-complexity-score",
                passed=reasonable,
                detail=f"Complexity score: {score}" + ("" if reasonable else " (out of valid 0-100 range)"),
                severity="info" if reasonable else "error",
            ))

    def _check_transform_phase(self, q: QuestionResult, data: dict) -> None:
        """Check TRANSFORM/routing decision from plan ingestion output."""
        route = data.get("route", data.get("transform", {}).get("route"))
        score = data.get("complexity_score", data.get("assess", {}).get("score"))

        if route and score is not None:
            expected = "artisan" if score > 40 else "prime_contractor"
            matches = route.lower().replace("-", "_") == expected
            q.checks.append(CheckResult(
                name="transform-routing",
                passed=matches,
                detail=(
                    f"Route='{route}' for score={score} "
                    f"({'correct' if matches else f'expected {expected}'})"
                ),
                severity="info" if matches else "warning",
            ))

    # ---- Q3: Was the translated plan faithfully executed? ------------------

    def _question_3(self) -> QuestionResult:
        """
        Q3: Was the translated plan faithfully executed? (Artisan layer)

        Checks:
        - Artisan output exists
        - DESIGN used correct derivation rules
        - IMPLEMENT produced expected files
        - TEST/REVIEW results
        - FINALIZE report: all tasks succeeded
        """
        q = QuestionResult(
            number=3,
            title="Was the translated plan faithfully executed?",
            layer="Artisan",
            status=QuestionStatus.PASS,
        )

        if not self.artisan_dir:
            q.status = QuestionStatus.SKIPPED
            q.checks.append(CheckResult(
                name="artisan-dir-provided",
                passed=False,
                detail="No artisan directory specified. Use --artisan-dir to enable Q3 checks.",
                severity="info",
            ))
            q.recommendation = (
                "Provide the artisan workflow output directory to enable execution checks."
            )
            return q

        if not self.artisan_dir.exists():
            q.status = QuestionStatus.FAIL
            q.checks.append(CheckResult(
                name="artisan-output-exists",
                passed=False,
                detail=f"Artisan output directory not found: {self.artisan_dir}",
            ))
            q.recommendation = "Run the artisan workflow first, then point --artisan-dir to the output."
            return q

        q.checks.append(CheckResult(
            name="artisan-output-exists",
            passed=True,
            detail=f"Artisan output found at {self.artisan_dir}.",
            severity="info",
        ))

        # Check for design handoff
        design_files = list(self.artisan_dir.glob("*design*handoff*.json")) + \
                       list(self.artisan_dir.glob("*design*.json"))
        if design_files:
            q.checks.append(CheckResult(
                name="design-handoff-exists",
                passed=True,
                detail=f"Design handoff found: {design_files[0].name}.",
                severity="info",
            ))
            # Try to validate the design handoff
            try:
                with open(design_files[0]) as fh:
                    design_data = json.load(fh)
                self._check_design_fidelity(q, design_data)
            except (json.JSONDecodeError, KeyError):
                pass
        else:
            q.checks.append(CheckResult(
                name="design-handoff-exists",
                passed=False,
                detail="No design handoff file found. DESIGN phase may not have completed.",
                severity="warning",
            ))

        # Check for generated output files
        coverage_gaps = self._metadata.get("coverage", {}).get("gaps", [])
        file_ownership = self._metadata.get("file_ownership", {})
        generated_count = 0
        missing_outputs: list[str] = []

        for fpath in file_ownership:
            output_path = self.artisan_dir / fpath
            if output_path.exists():
                generated_count += 1
            else:
                missing_outputs.append(fpath)

        if file_ownership:
            all_generated = len(missing_outputs) == 0
            q.checks.append(CheckResult(
                name="implement-output-files",
                passed=all_generated,
                detail=(
                    f"Generated {generated_count}/{len(file_ownership)} expected output file(s)."
                    + (f" Missing: {', '.join(missing_outputs[:5])}" if missing_outputs else "")
                ),
                severity="info" if all_generated else "warning",
            ))

        # Check for test results
        test_files = list(self.artisan_dir.glob("*test*result*.json")) + \
                     list(self.artisan_dir.glob("*test*report*.json"))
        if test_files:
            q.checks.append(CheckResult(
                name="test-results-exist",
                passed=True,
                detail=f"Test results found: {test_files[0].name}.",
                severity="info",
            ))

        # Check for finalize report (supports both ContextCore naming and
        # startd8-sdk naming: workflow-execution-report.json)
        finalize_files = list(self.artisan_dir.glob("*finalize*report*.json")) + \
                         list(self.artisan_dir.glob("*finalize*.json")) + \
                         list(self.artisan_dir.glob("*execution*report*.json")) + \
                         list(self.artisan_dir.glob("workflow-execution-report.json"))
        if finalize_files:
            try:
                with open(finalize_files[0]) as fh:
                    finalize_data = json.load(fh)
                self._check_finalize_report(q, finalize_data)
            except (json.JSONDecodeError, KeyError):
                q.checks.append(CheckResult(
                    name="finalize-report-valid",
                    passed=False,
                    detail=f"Could not parse finalize report: {finalize_files[0].name}.",
                    severity="warning",
                ))
        else:
            q.checks.append(CheckResult(
                name="finalize-report-exists",
                passed=False,
                detail="No finalize report found. FINALIZE phase may not have completed.",
                severity="warning",
            ))

        if any(not c.passed and c.severity == "error" for c in q.checks):
            q.status = QuestionStatus.FAIL
            q.recommendation = (
                "Fix execution issues in the artisan workflow. Check design handoff for "
                "correct derivation rules and re-run from the failing phase."
            )

        return q

    def _check_design_fidelity(self, q: QuestionResult, data: dict) -> None:
        """Check DESIGN phase used correct derivation rules."""
        # Verify schema version
        schema_ver = data.get("schema_version", data.get("version"))
        if schema_ver:
            q.checks.append(CheckResult(
                name="design-schema-version",
                passed=True,
                detail=f"Design handoff schema version: {schema_ver}.",
                severity="info",
            ))

        # Check if enriched seed references the current export
        seed_path = data.get("enriched_seed_path", data.get("seed_path"))
        if seed_path:
            # Verify the seed path points to current export
            seed = Path(seed_path)
            if str(self.export_dir) in str(seed) or seed.name in [
                f.name for f in self.export_dir.glob("*")
            ]:
                q.checks.append(CheckResult(
                    name="design-uses-current-export",
                    passed=True,
                    detail=f"Design references current export: {seed_path}.",
                    severity="info",
                ))
            else:
                q.checks.append(CheckResult(
                    name="design-uses-current-export",
                    passed=False,
                    detail=f"Design seed_path '{seed_path}' may not reference current export.",
                    severity="warning",
                ))

    def _check_finalize_report(self, q: QuestionResult, data: dict) -> None:
        """Check FINALIZE report for task completion status."""
        tasks_total = data.get("tasks_total", data.get("total", 0))
        tasks_succeeded = data.get("tasks_succeeded", data.get("succeeded", 0))
        tasks_failed = data.get("tasks_failed", data.get("failed", 0))

        all_succeeded = tasks_failed == 0 and tasks_succeeded > 0
        q.checks.append(CheckResult(
            name="finalize-all-tasks-succeeded",
            passed=all_succeeded,
            detail=(
                f"Finalize: {tasks_succeeded}/{tasks_total} succeeded, {tasks_failed} failed."
            ),
            severity="info" if all_succeeded else "error",
        ))

    # ---- Main runner --------------------------------------------------------

    def run(self) -> DiagnosticResult:
        """
        Run the Three Questions diagnostic in order.

        Stops at the first failing question to avoid wasted analysis.
        """
        self._load_metadata()

        project_id = self._metadata.get("project_id", "unknown")
        result = DiagnosticResult(
            export_dir=str(self.export_dir),
            project_id=project_id,
        )

        # Q1: Is the contract complete?
        q1 = self._question_1()
        result.questions.append(q1)

        if q1.failed:
            # Stop here — downstream analysis is wasted effort
            result.questions.append(QuestionResult(
                number=2,
                title="Was the contract faithfully translated?",
                layer="Plan Ingestion",
                status=QuestionStatus.NOT_REACHED,
            ))
            result.questions.append(QuestionResult(
                number=3,
                title="Was the translated plan faithfully executed?",
                layer="Artisan",
                status=QuestionStatus.NOT_REACHED,
            ))
            result.start_here = (
                "Q1 (Export layer) — The contract is incomplete. "
                f"{q1.recommendation}"
            )
            return result

        # Q2: Was the contract faithfully translated?
        q2 = self._question_2()
        result.questions.append(q2)

        if q2.failed:
            result.questions.append(QuestionResult(
                number=3,
                title="Was the translated plan faithfully executed?",
                layer="Artisan",
                status=QuestionStatus.NOT_REACHED,
            ))
            result.start_here = (
                "Q2 (Plan Ingestion layer) — The contract was not faithfully translated. "
                f"{q2.recommendation}"
            )
            return result

        # Q3: Was the translated plan faithfully executed?
        q3 = self._question_3()
        result.questions.append(q3)

        if q3.failed:
            result.start_here = (
                "Q3 (Artisan layer) — The translated plan was not faithfully executed. "
                f"{q3.recommendation}"
            )
        elif result.all_passed:
            result.start_here = "All clear — no issues detected across the pipeline."
        else:
            # Some questions were skipped
            skipped = [q for q in result.questions if q.status == QuestionStatus.SKIPPED]
            if skipped:
                layers = ", ".join(q.layer for q in skipped)
                result.start_here = (
                    f"Q1 passed. Skipped checks for: {layers}. "
                    "Provide --ingestion-dir and --artisan-dir for full diagnostic."
                )

        return result
