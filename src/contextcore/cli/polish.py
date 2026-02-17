import click
import json as _json
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from contextcore.cli.init_from_plan_ops import (
    _REQ_ID_PATTERN,
    _SATISFIES_PATTERN,
    _DEPENDS_ON_PATTERN,
    _REPO_PATTERN,
    _DELIVERABLES_PATTERN,
    _VALIDATION_PATTERN,
)


# ---------------------------------------------------------------------------
# Context propagation signal patterns
# ---------------------------------------------------------------------------
# These keyword / phrase groups indicate a plan involves multi-phase workflows
# where upstream context must propagate to downstream consumers — the exact
# pattern that benefits from a self-validating test harness.

_PROPAGATION_SIGNALS = {
    "multi_phase_workflow": [
        r"\bmulti[- ]?phase\b",
        r"\bpipeline\s+phase",
        r"\bworkflow\s+phase",
        r"\bupstream.{0,30}downstream\b",
        r"\bphase\s+boundary",
    ],
    "context_flow": [
        r"\bcontext\s+propagat",
        r"\bcontext\s+inject",
        r"\bcontext\s+extract",
        r"\benrichment\s+data\b",
        r"\bbroken\s+context\b",
        r"\bsilent\s+degrad",
    ],
    "gap_analysis": [
        r"\bpropagation\s+gap",
        r"\bidentified\s+gap",
        r"\bgap\s+#?\d",
        r"\bdefault(?:ed|s)\s+to\b.{0,30}\bunknown\b",
        r"\bkey\s+(?:name\s+)?mismatch",
    ],
    "phase_boundaries": [
        r"\bdesign\s+phase\b",
        r"\bimplement\s+phase\b",
        r"\btest\s+phase\b",
        r"\bfinalize\s+phase\b",
        r"\bboundary\s+(?:between|at)\b",
    ],
}

# Minimum signal groups that must match for detection to fire.
_PROPAGATION_DETECTION_THRESHOLD = 2

# ---------------------------------------------------------------------------
# Pipeline readiness patterns
# ---------------------------------------------------------------------------
# Phase heading regex mirrors the inline pattern in init_from_plan_ops.py
# (line ~497).  Keep in sync if either changes.
_PHASE_HEADING_PATTERN = re.compile(
    r'^#{2,3}\s*(phase|milestone|action|step|task)\b',
    re.IGNORECASE | re.MULTILINE,
)
_H1_TITLE_PATTERN = re.compile(r'^#\s+\S', re.MULTILINE)


class CheckResult:
    """Result of a single polish check."""

    def __init__(self, check_id: str, label: str):
        self.check_id = check_id
        self.label = label
        self.status: str = "pending"  # passed | failed | skipped
        self.message: Optional[str] = None
        self.detail: Optional[str] = None  # remediation hint

    def pass_(self, message: Optional[str] = None):
        self.status = "passed"
        self.message = message

    def fail(self, message: str, detail: Optional[str] = None):
        self.status = "failed"
        self.message = message
        self.detail = detail

    def skip(self, reason: str):
        self.status = "skipped"
        self.message = reason


class PolishResult:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.checks: List[CheckResult] = []
        # Legacy compat
        self.suggestions: List[str] = []
        self.warnings: List[str] = []

    def add_check(self, check: CheckResult):
        self.checks.append(check)
        if check.status == "failed":
            self.suggestions.append(check.message or "")

    @property
    def has_issues(self) -> bool:
        return any(c.status in ("failed", "skipped") for c in self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "passed")

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "failed")

    @property
    def skipped_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "skipped")


def _extract_section_text(content: str, header_pattern: str) -> Optional[str]:
    """Extract body text under a markdown header until the next same-or-higher-level header."""
    match = re.search(header_pattern, content, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    level = match.group(0).count("#")
    start = match.end()
    remaining = content[start:]
    # Match next header at same or higher level
    next_hdr = re.search(rf"^#{{1,{level}}}\s+", remaining, re.MULTILINE)
    if next_hdr:
        return remaining[: next_hdr.start()]
    return remaining


def check_plan_structure(content: str, result: PolishResult):
    """Run all plan structure checks, reporting every result."""

    # --- Check 1: Overview section exists ---
    chk_overview = CheckResult("overview-exists", "Overview section exists")
    overview_text = _extract_section_text(content, r"^#{1,3}\s+Overview")
    if overview_text is None:
        chk_overview.fail(
            "Missing 'Overview' section.",
            detail=(
                "Add a top-level '## Overview' section describing the high-level purpose, objectives, and goals. "
                "init-from-plan uses the Overview to seed spec.project.description."
            ),
        )
        result.add_check(chk_overview)
        # Mark downstream checks as skipped (they depend on Overview existing)
        for chk_id, label in [
            ("overview-objectives", "Overview mentions objectives"),
            ("overview-goals", "Overview mentions goals"),
        ]:
            chk = CheckResult(chk_id, label)
            chk.skip("Cannot check — Overview section is missing.")
            result.add_check(chk)
    else:
        chk_overview.pass_("Overview section found.")
        result.add_check(chk_overview)

        # --- Check 2: Objectives in Overview ---
        chk_obj = CheckResult("overview-objectives", "Overview mentions objectives")
        if re.search(r"\bObjectives?\b", overview_text, re.IGNORECASE):
            chk_obj.pass_("Objectives mentioned in Overview.")
        else:
            chk_obj.fail(
                "The 'Overview' section is missing 'Objectives'.",
                detail="Add a line starting with '**Objectives**:' summarizing what the plan aims to accomplish.",
            )
        result.add_check(chk_obj)

        # --- Check 3: Goals in Overview ---
        chk_goals = CheckResult("overview-goals", "Overview mentions goals")
        if re.search(r"\bGoals?\b", overview_text, re.IGNORECASE):
            chk_goals.pass_("Goals mentioned in Overview.")
        else:
            chk_goals.fail(
                "The 'Overview' section is missing 'Goals'.",
                detail="Add a line starting with '**Goals**:' listing measurable completion criteria.",
            )
        result.add_check(chk_goals)

    # --- Check 4: Requirements section exists ---
    chk_reqs = CheckResult("requirements-exist", "Requirements section exists")
    has_fr = re.search(
        r"^#{1,3}\s+.*(?:Functional\s+Requirements|FR)\b", content, re.IGNORECASE | re.MULTILINE
    )
    if has_fr:
        chk_reqs.pass_("Functional Requirements section found.")
    else:
        chk_reqs.fail(
            "No 'Functional Requirements' section found.",
            detail=(
                "Add a section listing FR-001, FR-002, etc. with descriptions and acceptance criteria. "
                "init-from-plan extracts REQ-IDs from this section for the traceability matrix."
            ),
        )
    result.add_check(chk_reqs)

    # --- Check 5: Risks section exists ---
    chk_risks = CheckResult("risks-exist", "Risks section exists")
    has_risks = re.search(r"^#{1,3}\s+.*Risks?\b", content, re.IGNORECASE | re.MULTILINE)
    if has_risks:
        chk_risks.pass_("Risks section found.")
    else:
        chk_risks.fail(
            "No 'Risks' section found.",
            detail=(
                "Add a section listing risks and mitigations. "
                "init-from-plan uses risk keywords to populate spec.risks with typed entries."
            ),
        )
    result.add_check(chk_risks)

    # --- Check 6: Validation / test section exists ---
    chk_tests = CheckResult("validation-exist", "Validation/test obligations exist")
    has_tests = re.search(
        r"^#{1,3}\s+.*(?:Validation|Test\s+Obligations?|Self[- ]?Validat)", content, re.IGNORECASE | re.MULTILINE
    )
    if has_tests:
        chk_tests.pass_("Validation/test section found.")
    else:
        chk_tests.fail(
            "No 'Validation' or 'Test Obligations' section found.",
            detail=(
                "Add a top-level section describing how the plan's implementation will be verified. "
                "This is the document-level validation section, distinct from per-phase "
                "**Validation:** lines checked by pipeline-validation-criteria."
            ),
        )
    result.add_check(chk_tests)

    # --- Check 7: Placeholder detection ---
    chk_placeholders = CheckResult("no-placeholders", "No unfilled placeholders")
    placeholders = re.findall(r"\[(?:describe|in-scope|out-of-scope|assumption|Goal \d|unit/integration)\b[^\]]*\]", content)
    if placeholders:
        unique = sorted(set(placeholders))
        chk_placeholders.fail(
            f"Found {len(unique)} unfilled placeholder(s): {', '.join(unique[:5])}",
            detail="Replace bracketed placeholders with concrete content.",
        )
    else:
        chk_placeholders.pass_("No unfilled placeholders detected.")
    result.add_check(chk_placeholders)


def check_context_propagation(content: str, result: PolishResult):
    """Detect context propagation patterns and suggest self-validation harness."""
    chk = CheckResult("context-propagation", "Context propagation pattern detection")

    matched_groups: List[str] = []
    for group_name, patterns in _PROPAGATION_SIGNALS.items():
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                matched_groups.append(group_name)
                break  # one match per group is enough

    if len(matched_groups) >= _PROPAGATION_DETECTION_THRESHOLD:
        # Check if plan already has self-validation
        has_self_validation = bool(
            re.search(r"self[- ]?validat|plan-as-its-own-test|SV-\d|gap.{0,15}verification", content, re.IGNORECASE)
        )
        if has_self_validation:
            chk.pass_(
                f"Context propagation pattern detected (signals: {', '.join(matched_groups)}). "
                "Self-validation section already present."
            )
        else:
            chk.fail(
                f"Context propagation pattern detected (signals: {', '.join(matched_groups)}) "
                "but no self-validation harness found.",
                detail=(
                    "This plan involves multi-phase context propagation which is prone to silent degradation. "
                    "Consider adding a 'Self-Validating Gap Verification' section where each identified gap "
                    "maps to a runtime integration check (SV-*) that fails before the fix and passes after. "
                    "This plan-as-its-own-test-harness pattern catches missed gaps during execution. "
                    "See DP-4 in docs/design-principles/context-propagation.md."
                ),
            )
    else:
        chk.pass_("No context propagation pattern detected (not applicable).")

    result.add_check(chk)


def check_pipeline_readiness(content: str, result: PolishResult):
    """Validate structural elements that downstream pipeline stages depend on.

    Six checks prefixed ``pipeline-`` ensure the plan contains the patterns
    that ``analyze-plan`` and ``init-from-plan`` need to produce enriched
    manifests (tactics, traceability matrices, readiness verdicts).
    """

    # ── Check 1: Phase / milestone headings exist ─────────────────────
    chk_phases = CheckResult("pipeline-phases-exist", "Phase/milestone headings exist")
    phases_found = _PHASE_HEADING_PATTERN.findall(content)
    has_phases = len(phases_found) > 0
    if has_phases:
        chk_phases.pass_(f"{len(phases_found)} phase/milestone heading(s) found.")
    else:
        chk_phases.fail(
            "No phase or milestone headings found.",
            detail=(
                "WHY: analyze-plan extracts phase_metadata[] and init-from-plan converts "
                "each phase heading into a tactic (TAC-PLAN-NNN). Without phases, "
                "strategy.tactics will be empty.\n"
                "EXPECTED FORMAT:\n"
                "  ## Phase 1: Setup Infrastructure\n"
                "  ## Milestone 2: Core Implementation\n"
                "  ### Step 3: Integration Testing\n"
                "IMPACT IF MISSING: 0 tactics in manifest, empty traceability matrix."
            ),
        )
    result.add_check(chk_phases)

    # ── Check 2: Phase metadata lines (Satisfies / Depends on / Repo) ─
    chk_meta = CheckResult("pipeline-phase-metadata", "Phase metadata lines present")
    if not has_phases:
        chk_meta.skip("No phases found — metadata check not applicable.")
    else:
        has_satisfies = bool(_SATISFIES_PATTERN.search(content))
        has_depends = bool(_DEPENDS_ON_PATTERN.search(content))
        has_repo = bool(_REPO_PATTERN.search(content))
        if has_satisfies or has_depends or has_repo:
            found = []
            if has_satisfies:
                found.append("Satisfies")
            if has_depends:
                found.append("Depends on")
            if has_repo:
                found.append("Repo")
            chk_meta.pass_(f"Phase metadata found: {', '.join(found)}.")
        else:
            chk_meta.fail(
                "Phases exist but no Satisfies/Depends on/Repo metadata found.",
                detail=(
                    "WHY: init-from-plan enriches each tactic with satisfies, dependsOn, "
                    "and repo fields. analyze-plan builds the traceability_matrix from "
                    "Satisfies lines. Without metadata, tactics are unenriched stubs.\n"
                    "EXPECTED FORMAT (under a phase heading):\n"
                    "  **Satisfies:** REQ-001, FR-002\n"
                    "  **Depends on:** Phase 1\n"
                    "  **Repo:** contextcore\n"
                    "IMPACT IF MISSING: coverage_ratio = 0.0 in traceability matrix, "
                    "unenriched tactics with no requirement links."
                ),
            )
    result.add_check(chk_meta)

    # ── Check 3: REQ-ID identifiers anywhere in document ──────────────
    chk_req_ids = CheckResult("pipeline-req-ids-found", "Requirement IDs present (REQ-/FR-/NFR-)")
    req_ids = _REQ_ID_PATTERN.findall(content)
    if req_ids:
        unique_ids = sorted(set(req_ids))
        chk_req_ids.pass_(f"{len(unique_ids)} unique requirement ID(s) found.")
    else:
        chk_req_ids.fail(
            "No requirement identifiers (REQ-N, FR-N, NFR-N) found.",
            detail=(
                "WHY: init-from-plan extracts all REQ-IDs and records them as "
                "requirement_ids inference. analyze-plan uses them to build the "
                "traceability_matrix mapping requirements to phases.\n"
                "EXPECTED FORMAT:\n"
                "  REQ-001, FR-002, NFR-003  (anywhere in the document)\n"
                "IMPACT IF MISSING: Empty requirement_ids, traceability_matrix "
                "has 0 mapped requirements, coverage_ratio = 0.0."
            ),
        )
    result.add_check(chk_req_ids)

    # ── Check 4: H1 title exists ──────────────────────────────────────
    chk_title = CheckResult("pipeline-plan-title", "Plan has H1 title")
    if _H1_TITLE_PATTERN.search(content):
        chk_title.pass_("H1 title found.")
    else:
        chk_title.fail(
            "No H1 title (# Title) found.",
            detail=(
                "WHY: init-from-plan uses the first '# ...' heading as the project "
                "description seed for spec.project.description.\n"
                "EXPECTED FORMAT:\n"
                "  # My Plan Title\n"
                "IMPACT IF MISSING: spec.project.description falls back to "
                "first prose line, which may be vague or empty."
            ),
        )
    result.add_check(chk_title)

    # ── Check 5: Deliverables lines ───────────────────────────────────
    chk_deliverables = CheckResult("pipeline-deliverables", "Per-phase deliverables declared")
    if not has_phases:
        chk_deliverables.skip("No phases found — deliverables check not applicable.")
    else:
        if _DELIVERABLES_PATTERN.search(content):
            chk_deliverables.pass_("Deliverables line(s) found.")
        else:
            chk_deliverables.fail(
                "Phases exist but no **Deliverables:** lines found.",
                detail=(
                    "WHY: init-from-plan collects deliverable checklists under each "
                    "phase and attaches them to tactics as tactic.deliverables "
                    "(summary + file_count).\n"
                    "EXPECTED FORMAT (under a phase heading):\n"
                    "  **Deliverables:**\n"
                    "  - [ ] `src/module.py` — New module\n"
                    "  - [ ] `tests/test_module.py` — Tests\n"
                    "IMPACT IF MISSING: Tactics have no deliverables field, "
                    "deliverable validation in TaskTracker is skipped."
                ),
            )
    result.add_check(chk_deliverables)

    # ── Check 6: Per-phase validation criteria ────────────────────────
    chk_validation = CheckResult(
        "pipeline-validation-criteria", "Per-phase validation criteria declared"
    )
    if not has_phases:
        chk_validation.skip("No phases found — validation criteria check not applicable.")
    else:
        if _VALIDATION_PATTERN.search(content):
            chk_validation.pass_("Per-phase validation line(s) found.")
        else:
            chk_validation.fail(
                "Phases exist but no per-phase **Validation:** lines found.",
                detail=(
                    "WHY: init-from-plan uses **Validation:** lines to delimit the "
                    "deliverables section and to signal phase-level acceptance criteria "
                    "to downstream review stages.\n"
                    "EXPECTED FORMAT (under a phase heading, after deliverables):\n"
                    "  **Validation:** Unit tests pass, integration smoke test green\n"
                    "IMPACT IF MISSING: Deliverable collection may over-run into "
                    "subsequent content; no per-phase acceptance criteria for review."
                ),
            )
    result.add_check(chk_validation)


def polish_file(file_path: Path) -> Optional[PolishResult]:
    """Applies all polish checks to a single file."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    if file_path.suffix.lower() not in [".md", ".markdown"]:
        return None

    result = PolishResult(str(file_path))
    check_plan_structure(content, result)
    check_context_propagation(content, result)
    check_pipeline_readiness(content, result)

    return result


def _render_text_report(results: List[PolishResult]):
    """Render human-readable report showing all checks."""
    for r in results:
        click.echo(click.style(f"\n  {r.file_path}", bold=True))
        click.echo(
            f"  {r.passed_count} passed, {r.failed_count} failed, {r.skipped_count} skipped"
        )
        click.echo()

        for c in r.checks:
            if c.status == "passed":
                icon = click.style("  PASS", fg="green")
                click.echo(f"{icon}  [{c.check_id}] {c.label}")
            elif c.status == "failed":
                icon = click.style("  FAIL", fg="red")
                click.echo(f"{icon}  [{c.check_id}] {c.label}")
                click.echo(f"          {c.message}")
                if c.detail:
                    click.echo(click.style(f"          Fix: {c.detail}", fg="yellow"))
            elif c.status == "skipped":
                icon = click.style("  SKIP", fg="yellow")
                click.echo(f"{icon}  [{c.check_id}] {c.label}")
                click.echo(f"          {c.message}")

    click.echo()


def _render_json_report(results: List[PolishResult]):
    """Render machine-readable JSON report."""
    output = []
    for r in results:
        output.append(
            {
                "file": r.file_path,
                "summary": {
                    "passed": r.passed_count,
                    "failed": r.failed_count,
                    "skipped": r.skipped_count,
                },
                "checks": [
                    {
                        "check_id": c.check_id,
                        "label": c.label,
                        "status": c.status,
                        "message": c.message,
                        "detail": c.detail,
                    }
                    for c in r.checks
                ],
            }
        )
    click.echo(_json.dumps(output, indent=2))


@click.command()
@click.argument("target", type=click.Path(exists=True, file_okay=True, dir_okay=True))
@click.option("--strict", is_flag=True, help="Exit with non-zero code if any check fails.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.option("--output-dir", type=click.Path(), default=None, help="Write polish-report.json and register in artifact inventory")
def polish(target, strict, output_format, output_dir):
    """[EXPERIMENTAL] Advisory step to polish artifacts for better output quality."""

    if output_format == "text":
        click.echo(
            click.style(
                "\u26a0\ufe0f  EXPERIMENTAL: This command is not yet officially part of the pipeline.\n",
                fg="yellow",
            )
        )

    target_path = Path(target)
    results: List[PolishResult] = []

    if target_path.is_file():
        res = polish_file(target_path)
        if res:
            results.append(res)
    else:
        for root, _, files in os.walk(target_path):
            for file in sorted(files):
                file_path = Path(root) / file
                if file_path.suffix.lower() in [".md", ".markdown"]:
                    res = polish_file(file_path)
                    if res:
                        results.append(res)

    if output_format == "json":
        _render_json_report(results)
    else:
        if not results:
            click.echo(click.style("\u2728 All polished! No issues found.", fg="green"))
        else:
            has_failures = any(r.failed_count > 0 for r in results)
            _render_text_report(results)
            if not has_failures:
                click.echo(click.style("\u2728 All polished! No issues found.", fg="green"))

    if output_dir:
        from contextcore.utils.artifact_inventory import (
            build_inventory_entry,
            extend_inventory,
            PRE_PIPELINE_INVENTORY_ROLES,
        )

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Build the same JSON structure as _render_json_report
        report_data = []
        for r in results:
            report_data.append(
                {
                    "file": r.file_path,
                    "summary": {
                        "passed": r.passed_count,
                        "failed": r.failed_count,
                        "skipped": r.skipped_count,
                    },
                    "checks": [
                        {
                            "check_id": c.check_id,
                            "label": c.label,
                            "status": c.status,
                            "message": c.message,
                            "detail": c.detail,
                        }
                        for c in r.checks
                    ],
                }
            )

        report_file = out_path / "polish-report.json"
        report_file.write_text(
            _json.dumps(report_data, indent=2) + "\n", encoding="utf-8"
        )

        role_spec = PRE_PIPELINE_INVENTORY_ROLES["polish_report"]
        entry = build_inventory_entry(
            role="polish_report",
            stage=role_spec["stage"],
            source_file="polish-report.json",
            produced_by="contextcore.polish",
            data=report_data,
            description=role_spec["description"],
            consumers=role_spec["consumers"],
            consumption_hint=role_spec["consumption_hint"],
        )
        extend_inventory(out_path, [entry])
        click.echo(f"Wrote polish-report.json + inventory to {out_path}")

    has_failures = any(r.failed_count > 0 for r in results)
    if strict and has_failures:
        ctx = click.get_current_context()
        ctx.exit(1)
