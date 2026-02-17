"""
Deterministic auto-remediation for fixable polish checks.

Bridges the gap between polish (detection) and init-from-plan (extraction)
by applying safe, content-preserving fixes to plan documents.

Three checks are fixable:
- overview-objectives: Insert **Objectives:** from Overview prose
- overview-goals: Insert **Goals:** from phase headings
- requirements-exist: Build ## Functional Requirements from Satisfies lines

All fixes are idempotent, composable, and never modify the original file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from contextcore.cli.polish import (
    _extract_section_text,
    _PHASE_HEADING_PATTERN,
    _H1_TITLE_PATTERN,
)
from contextcore.cli.init_from_plan_ops import (
    _REQ_ID_PATTERN,
    _SATISFIES_PATTERN,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FixAction:
    """Result of a single fix attempt."""

    check_id: str
    status: str  # "fixed" | "skipped" | "not_applicable"
    strategy: Optional[str] = None
    diff_summary: Optional[str] = None
    reason: Optional[str] = None
    traceability: Optional[Dict[str, str]] = None


@dataclass
class FixResult:
    """Aggregate result for a file."""

    source_path: str
    original_content: str
    remediated_content: str
    actions: List[FixAction] = field(default_factory=list)

    @property
    def fixed_count(self) -> int:
        return sum(1 for a in self.actions if a.status == "fixed")

    @property
    def skipped_count(self) -> int:
        return sum(1 for a in self.actions if a.status == "skipped")

    @property
    def not_applicable_count(self) -> int:
        return sum(1 for a in self.actions if a.status == "not_applicable")


# ---------------------------------------------------------------------------
# Intent verbs for objective extraction
# ---------------------------------------------------------------------------

_INTENT_VERBS = [
    "implement", "establish", "create", "enable", "ensure", "define",
    "build", "design", "deliver", "align", "provide", "integrate",
    "support", "automate", "validate", "verify", "introduce", "extend",
    "unify", "standardize", "bridge", "consolidate", "migrate", "resolve",
]

_INTENT_VERB_PATTERN = re.compile(
    r'\b(' + '|'.join(_INTENT_VERBS) + r')\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Unfixable check reasons
# ---------------------------------------------------------------------------

UNFIXABLE_REASONS: Dict[str, str] = {
    "risks-exist": "Requires domain knowledge to identify and describe risks.",
    "validation-exist": "Validation criteria depend on implementation approach.",
    "pipeline-phases-exist": "Phase decomposition requires understanding of work.",
    "pipeline-phase-metadata": "Satisfies/Depends on/Repo require per-phase decisions.",
    "pipeline-deliverables": "Deliverable paths require knowledge of target codebase.",
    "pipeline-validation-criteria": "Per-phase validation depends on deliverable types.",
    "context-propagation": "Self-validation harness is domain-specific.",
    "no-placeholders": "Placeholder content must be filled by the author.",
    "overview-exists": "Cannot generate an overview from nothing.",
    "pipeline-req-ids-found": "REQ-IDs must be authored, not fabricated.",
    "pipeline-plan-title": "H1 title requires human decision.",
}


# ---------------------------------------------------------------------------
# Fix strategy: overview-objectives
# ---------------------------------------------------------------------------

def _fix_overview_objectives(content: str) -> Optional[FixAction]:
    """Insert **Objectives:** line extracted from Overview prose.

    Returns None if the check already passes or Overview is missing.
    """
    overview_text = _extract_section_text(content, r"^#{1,3}\s+Overview")
    if overview_text is None:
        return None

    # Already has objectives keyword
    if re.search(r"\bObjectives?\b", overview_text, re.IGNORECASE):
        return None

    # Extract sentences containing intent verbs
    sentences = re.split(r'(?<=[.!?])\s+', overview_text.strip())
    objective_phrases = []
    for sentence in sentences:
        if _INTENT_VERB_PATTERN.search(sentence):
            # Clean up the sentence
            cleaned = sentence.strip().rstrip(".")
            if len(cleaned) > 15:
                objective_phrases.append(cleaned)

    if not objective_phrases:
        # Fall back to first meaningful prose line
        for line in overview_text.strip().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and len(stripped) > 20:
                objective_phrases.append(stripped.rstrip("."))
                break

    if not objective_phrases:
        return FixAction(
            check_id="overview-objectives",
            status="skipped",
            strategy="extract_from_overview_prose",
            reason="No intent verbs or meaningful prose found in Overview.",
        )

    # Build the objectives line (use top 3)
    selected = objective_phrases[:3]
    objectives_line = "**Objectives:** " + "; ".join(selected) + "."

    return FixAction(
        check_id="overview-objectives",
        status="fixed",
        strategy="extract_from_overview_prose",
        diff_summary=f"Inserted **Objectives:** line with {len(selected)} phrase(s)",
        traceability={
            "polish_detects": "Overview exists but lacks Objectives keyword",
            "fix_remediates": "Extracts intent verbs from prose, inserts **Objectives:** line",
            "init_extracts": "Overview text enriches spec.project.description",
            "manifest_contains": "spec.project.description with objective-enriched text",
            "export_produces": "Description in onboarding-metadata for downstream agents",
        },
    ), objectives_line


def _apply_overview_objectives(content: str) -> tuple[str, Optional[FixAction]]:
    """Apply the overview-objectives fix to content."""
    result = _fix_overview_objectives(content)
    if result is None:
        return content, None
    if isinstance(result, FixAction):
        return content, result

    action, objectives_line = result

    # Find the Overview section and insert objectives line after the header
    match = re.search(r"^(#{1,3}\s+Overview\s*\n)", content, re.IGNORECASE | re.MULTILINE)
    if not match:
        return content, None

    insert_pos = match.end()
    # Skip any blank lines after the header
    remaining = content[insert_pos:]
    blank_match = re.match(r"(\s*\n)*", remaining)
    if blank_match:
        insert_pos += blank_match.end()

    new_content = content[:insert_pos] + objectives_line + "\n\n" + content[insert_pos:]
    return new_content, action


# ---------------------------------------------------------------------------
# Fix strategy: overview-goals
# ---------------------------------------------------------------------------

def _fix_overview_goals(content: str) -> Optional[FixAction]:
    """Insert **Goals:** block synthesized from phase headings.

    Returns None if the check already passes or Overview is missing.
    """
    overview_text = _extract_section_text(content, r"^#{1,3}\s+Overview")
    if overview_text is None:
        return None

    # Already has goals keyword
    if re.search(r"\bGoals?\b", overview_text, re.IGNORECASE):
        return None

    # Extract phase headings for goal synthesis
    phase_headings = _PHASE_HEADING_PATTERN.findall(content)
    phase_lines = re.findall(
        r"^#{2,3}\s*(?:phase|milestone|action|step|task)\s*\d*[:\s]*(.*)",
        content,
        re.IGNORECASE | re.MULTILINE,
    )

    goals = []
    if phase_lines:
        for heading_text in phase_lines[:5]:
            cleaned = heading_text.strip().rstrip(".")
            if cleaned and len(cleaned) > 5:
                goals.append(f"Complete {cleaned.lower()}")
    else:
        # No phases found -- synthesize a generic completion goal
        h1_match = _H1_TITLE_PATTERN.search(content)
        if h1_match:
            title_line = content[h1_match.start():].split("\n")[0]
            title = re.sub(r"^#\s+", "", title_line).strip()
            goals.append(f"Deliver {title.lower()}")

    if not goals:
        return FixAction(
            check_id="overview-goals",
            status="skipped",
            strategy="synthesize_from_phases",
            reason="No phase headings or H1 title found to synthesize goals.",
        )

    # Build the goals block
    goals_lines = ["**Goals:**"]
    for goal in goals:
        goals_lines.append(f"- {goal}")

    return FixAction(
        check_id="overview-goals",
        status="fixed",
        strategy="synthesize_from_phases",
        diff_summary=f"Inserted **Goals:** block with {len(goals)} goal(s)",
        traceability={
            "polish_detects": "Overview exists but lacks Goals keyword",
            "fix_remediates": "Synthesizes goals from phase headings, inserts **Goals:** block",
            "init_extracts": "### Goals section parsed to populate strategy.objectives",
            "manifest_contains": "strategy.objectives with goal-derived OBJ-PLAN entries",
            "export_produces": "Objectives in onboarding-metadata for agent planning",
        },
    ), "\n".join(goals_lines)


def _apply_overview_goals(content: str) -> tuple[str, Optional[FixAction]]:
    """Apply the overview-goals fix to content."""
    result = _fix_overview_goals(content)
    if result is None:
        return content, None
    if isinstance(result, FixAction):
        return content, result

    action, goals_block = result

    # Insert goals block at end of Overview section, before the next heading
    overview_match = re.search(r"^(#{1,3}\s+Overview\s*\n)", content, re.IGNORECASE | re.MULTILINE)
    if not overview_match:
        return content, None

    level = overview_match.group(0).count("#")
    start = overview_match.end()
    remaining = content[start:]

    # Find next same-or-higher-level heading
    next_hdr = re.search(rf"^#{{1,{level}}}\s+", remaining, re.MULTILINE)
    if next_hdr:
        insert_pos = start + next_hdr.start()
    else:
        insert_pos = len(content)

    # Insert before the next heading, with proper spacing
    before = content[:insert_pos].rstrip("\n")
    after = content[insert_pos:]
    new_content = before + "\n\n" + goals_block + "\n\n" + after
    return new_content, action


# ---------------------------------------------------------------------------
# Fix strategy: requirements-exist
# ---------------------------------------------------------------------------

def _fix_requirements_exist(content: str) -> Optional[FixAction]:
    """Build ## Functional Requirements table from Satisfies lines.

    Returns None if the check already passes or no REQ-IDs exist.
    """
    # Already has Functional Requirements section
    if re.search(
        r"^#{1,3}\s+.*(?:Functional\s+Requirements|FR)\b",
        content,
        re.IGNORECASE | re.MULTILINE,
    ):
        return None

    # Collect REQ-IDs from Satisfies lines, mapping each to its phase
    req_phase_map: Dict[str, str] = {}
    current_phase = "(no phase)"

    for line in content.splitlines():
        # Track current phase heading
        phase_match = re.match(
            r"^#{2,3}\s*(phase|milestone|action|step|task)\b(.*)",
            line,
            re.IGNORECASE,
        )
        if phase_match:
            current_phase = phase_match.group(0).lstrip("#").strip()

        # Check for Satisfies line
        satisfies_match = _SATISFIES_PATTERN.match(line.strip())
        if satisfies_match:
            raw = satisfies_match.group(1)
            ids = _REQ_ID_PATTERN.findall(raw)
            for req_id in ids:
                if req_id not in req_phase_map:
                    req_phase_map[req_id] = current_phase

    # Also collect any REQ-IDs from anywhere in the document that aren't mapped
    all_ids = set(_REQ_ID_PATTERN.findall(content))
    for req_id in sorted(all_ids):
        if req_id not in req_phase_map:
            req_phase_map[req_id] = "(document-level)"

    if not req_phase_map:
        return FixAction(
            check_id="requirements-exist",
            status="skipped",
            strategy="collect_req_ids_from_satisfies",
            reason="No REQ-IDs found in document.",
        )

    # Build the Functional Requirements section
    lines = ["## Functional Requirements", ""]
    lines.append("| ID | Source Phase |")
    lines.append("|-----|-------------|")
    for req_id in sorted(req_phase_map.keys()):
        phase = req_phase_map[req_id]
        lines.append(f"| {req_id} | {phase} |")

    return FixAction(
        check_id="requirements-exist",
        status="fixed",
        strategy="collect_req_ids_from_satisfies",
        diff_summary=f"Built ## Functional Requirements table with {len(req_phase_map)} ID(s)",
        traceability={
            "polish_detects": "No Functional Requirements section found",
            "fix_remediates": "Collects REQ-IDs from Satisfies lines, builds FR table",
            "init_extracts": "_REQ_ID_PATTERN extracts IDs for requirement_ids inference",
            "manifest_contains": "requirement_ids populated, traceability_matrix coverage_ratio > 0",
            "export_produces": "Requirements in traceability context for downstream agents",
        },
    ), "\n".join(lines)


def _apply_requirements_exist(content: str) -> tuple[str, Optional[FixAction]]:
    """Apply the requirements-exist fix to content."""
    result = _fix_requirements_exist(content)
    if result is None:
        return content, None
    if isinstance(result, FixAction):
        return content, result

    action, fr_section = result

    # Insert before the first phase heading, or before Risks, or at end
    # Prefer: after Overview section, before first ## Phase heading
    phase_match = re.search(
        r"^#{2,3}\s*(?:phase|milestone|action|step|task)\b",
        content,
        re.IGNORECASE | re.MULTILINE,
    )
    risks_match = re.search(r"^#{1,3}\s+.*Risks?\b", content, re.IGNORECASE | re.MULTILINE)

    if phase_match:
        insert_pos = phase_match.start()
    elif risks_match:
        insert_pos = risks_match.start()
    else:
        insert_pos = len(content)

    before = content[:insert_pos].rstrip("\n")
    after = content[insert_pos:]
    new_content = before + "\n\n" + fr_section + "\n\n" + after
    return new_content, action


# ---------------------------------------------------------------------------
# Fix registry
# ---------------------------------------------------------------------------

# Maps check_id -> fix applicator function
_FIX_REGISTRY = {
    "overview-objectives": _apply_overview_objectives,
    "overview-goals": _apply_overview_goals,
    "requirements-exist": _apply_requirements_exist,
}

# All check_ids that have a fix strategy
FIXABLE_CHECK_IDS = frozenset(_FIX_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def apply_fixes(
    content: str,
    polish_checks: List[Dict[str, Any]],
    source_path: str,
) -> FixResult:
    """Apply all applicable fixes to plan content.

    Args:
        content: The raw markdown content of the plan.
        polish_checks: List of check dicts from polish-report.json
            (each with check_id, status, message, etc.).
        source_path: Path to the original file (for reporting).

    Returns:
        FixResult with original content, remediated content, and actions.
    """
    result = FixResult(
        source_path=source_path,
        original_content=content,
        remediated_content=content,
    )

    # Build a lookup of check statuses
    check_status_map = {c["check_id"]: c["status"] for c in polish_checks}

    # Process all checks from the polish report
    processed_ids = set()

    for check in polish_checks:
        check_id = check["check_id"]
        status = check["status"]

        if check_id in processed_ids:
            continue
        processed_ids.add(check_id)

        if check_id in _FIX_REGISTRY:
            if status == "passed":
                # Check already passes -- no fix needed
                result.actions.append(FixAction(
                    check_id=check_id,
                    status="not_applicable",
                    reason="Check already passes.",
                ))
            elif status in ("failed", "skipped"):
                # Attempt to fix
                fix_fn = _FIX_REGISTRY[check_id]
                new_content, action = fix_fn(result.remediated_content)
                if action is not None:
                    result.actions.append(action)
                    if action.status == "fixed":
                        result.remediated_content = new_content
                else:
                    result.actions.append(FixAction(
                        check_id=check_id,
                        status="not_applicable",
                        reason="Fix strategy found no content to remediate.",
                    ))
        elif check_id in UNFIXABLE_REASONS:
            if status == "failed":
                result.actions.append(FixAction(
                    check_id=check_id,
                    status="skipped",
                    reason=UNFIXABLE_REASONS[check_id],
                ))
            else:
                result.actions.append(FixAction(
                    check_id=check_id,
                    status="not_applicable",
                    reason="Check already passes.",
                ))
        else:
            # Unknown check -- skip silently
            result.actions.append(FixAction(
                check_id=check_id,
                status="not_applicable",
                reason="No fix strategy available for this check.",
            ))

    return result
