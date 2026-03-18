"""
Operations module for `contextcore manifest fix`.

Detects fixable issues in a context manifest (open questions, etc.)
and applies resolutions either interactively or from a pre-answers file.

This bridges the gap between init-from-plan (which generates open questions)
and validate --strict (which fails on them) by providing a proper Stage 2.5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import yaml

from contextcore.cli.export_io_ops import atomic_write_with_backup


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ResolvedAnswer:
    """A resolved answer for a manifest question."""

    question_id: str
    answer: str
    source: str  # "interactive" | "answers-file"


@dataclass
class ManifestFixReport:
    """Report of fixable issues detected in a manifest."""

    path: str
    open_questions: List[Dict[str, Any]] = field(default_factory=list)
    total_issues: int = 0


@dataclass
class ManifestFixResult:
    """Result of applying fixes to a manifest."""

    path: str
    fixed_count: int = 0
    skipped_count: int = 0
    actions: List[Dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect_manifest_issues(manifest_path: str) -> ManifestFixReport:
    """Detect fixable issues in a manifest.

    Currently detects:
    - Open questions (status != "answered")

    Args:
        manifest_path: Path to the manifest YAML file.

    Returns:
        ManifestFixReport with details of fixable issues.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If the manifest fails schema validation.
        yaml.YAMLError: If the manifest contains invalid YAML.
    """
    from contextcore.models.manifest_loader import load_manifest
    from contextcore.models.manifest_v2 import ContextManifestV2

    manifest = load_manifest(manifest_path)

    report = ManifestFixReport(path=manifest_path)

    if isinstance(manifest, ContextManifestV2):
        open_questions = manifest.get_open_questions()
        for q in open_questions:
            report.open_questions.append({
                "id": q.id,
                "question": q.question,
                "status": q.status.value,
                "priority": q.priority.value,
            })

    report.total_issues = len(report.open_questions)
    return report


# ---------------------------------------------------------------------------
# Resolution: interactive
# ---------------------------------------------------------------------------


def resolve_questions_interactive(
    questions: List[Dict[str, Any]],
) -> List[ResolvedAnswer]:
    """Prompt the user for each open question.

    Args:
        questions: List of question dicts from ManifestFixReport.open_questions.

    Returns:
        List of ResolvedAnswer for questions the user answered.
    """
    resolutions: List[ResolvedAnswer] = []

    for q in questions:
        click.echo(f"\n  [{q['id']}] {q['question']}")
        click.echo(f"  Priority: {q['priority']}")
        answer = click.prompt("  Answer", default="", show_default=False)
        if answer.strip():
            resolutions.append(ResolvedAnswer(
                question_id=q["id"],
                answer=answer.strip(),
                source="interactive",
            ))
        else:
            click.echo("  (skipped)")

    return resolutions


# ---------------------------------------------------------------------------
# Resolution: answers file
# ---------------------------------------------------------------------------


def resolve_questions_from_file(
    questions: List[Dict[str, Any]],
    answers_path: str,
) -> Tuple[List[ResolvedAnswer], List[str]]:
    """Load answers from a YAML/JSON file and match to open questions.

    The answers file should be a mapping of question_id -> answer text::

        Q-001: "The answer"
        Q-CAP-1: "Another answer"

    Or a list of dicts with id/answer keys::

        - id: Q-001
          answer: "The answer"

    Args:
        questions: List of question dicts from ManifestFixReport.open_questions.
        answers_path: Path to the YAML/JSON answers file.

    Returns:
        Tuple of (resolved answers, unmatched question IDs).

    Raises:
        ValueError: If the answers file is empty or contains invalid YAML.
        OSError: If the answers file cannot be read.
    """
    path = Path(answers_path)
    raw = path.read_text(encoding="utf-8")

    try:
        answers_data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in answers file {answers_path}: {exc}") from exc

    # Normalize to dict[question_id -> answer]
    # Supported formats:
    #   1. Flat dict:   { "Q-001": "answer", "Q-002": "answer" }
    #   2. List:        [ { id: Q-001, answer: "..." }, ... ]
    #   3. Wrapped:     { questions: [ { id: Q-001, answer: "..." }, ... ] }
    answers_map: Dict[str, str] = {}

    # Unwrap { questions: [...] } envelope
    if isinstance(answers_data, dict) and "questions" in answers_data:
        answers_data = answers_data["questions"]

    if isinstance(answers_data, dict):
        for k, v in answers_data.items():
            answers_map[str(k)] = str(v)
    elif isinstance(answers_data, list):
        for item in answers_data:
            if isinstance(item, dict) and "id" in item and "answer" in item:
                answers_map[str(item["id"])] = str(item["answer"])
    # answers_data is None (empty file) or unexpected type — answers_map stays empty

    resolutions: List[ResolvedAnswer] = []
    unmatched: List[str] = []

    for q in questions:
        qid = q["id"]
        if qid in answers_map:
            resolutions.append(ResolvedAnswer(
                question_id=qid,
                answer=answers_map[qid],
                source="answers-file",
            ))
        else:
            unmatched.append(qid)

    return resolutions, unmatched


# ---------------------------------------------------------------------------
# Apply fixes
# ---------------------------------------------------------------------------


def apply_manifest_fixes(
    manifest_path: str,
    resolutions: List[ResolvedAnswer],
    dry_run: bool = False,
) -> ManifestFixResult:
    """Apply resolved answers to the manifest YAML.

    Operates on raw YAML (not Pydantic) to preserve formatting.
    Sets status="answered", answer=<text>, answered_by=<source> for each
    resolved question.

    Args:
        manifest_path: Path to the manifest YAML file.
        resolutions: List of ResolvedAnswer to apply.
        dry_run: If True, do not write the file.

    Returns:
        ManifestFixResult with counts and action details.

    Raises:
        yaml.YAMLError: If the manifest contains invalid YAML.
        OSError: If the manifest file cannot be read or written.
    """
    path = Path(manifest_path)
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))

    result = ManifestFixResult(path=manifest_path)

    if not isinstance(raw_data, dict):
        return result

    # Build resolution lookup for O(1) matching
    resolution_map = {r.question_id: r for r in resolutions}

    questions = (raw_data.get("guidance") or {}).get("questions") or []

    for q in questions:
        qid = q.get("id", "")
        if qid in resolution_map:
            r = resolution_map[qid]
            old_status = q.get("status", "open")
            q["status"] = "answered"
            q["answer"] = r.answer
            q["answeredBy"] = r.source
            q["answeredAt"] = datetime.now().isoformat()
            result.fixed_count += 1
            result.actions.append({
                "question_id": qid,
                "action": "answered",
                "old_status": old_status,
                "source": r.source,
            })
        elif q.get("status") in ("open", None):
            result.skipped_count += 1

    if not dry_run and result.fixed_count > 0:
        manifest_yaml = yaml.dump(raw_data, default_flow_style=False, sort_keys=False)
        atomic_write_with_backup(path, manifest_yaml, backup=True)

    return result
