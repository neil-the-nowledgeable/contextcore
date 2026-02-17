"""
Plan analysis engine for ``contextcore manifest analyze-plan`` (Stage 1.5).

Parses plan and requirements documents *separately*, extracting structured
metadata that the inference engine (``init_from_plan_ops.py``) can merge for
richer manifest generation.

Output schema: ``contextcore.io/plan-analysis/v1``
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Reuse patterns from init_from_plan_ops
from contextcore.cli.init_from_plan_ops import (
    _CHECKLIST_PATTERN,
    _DELIVERABLES_PATTERN,
    _DEPENDS_ON_PATTERN,
    _REPO_PATTERN,
    _REQ_ID_PATTERN,
    _SATISFIES_PATTERN,
    _VALIDATION_PATTERN,
)

# Header metadata patterns
_REQUIREMENTS_HEADER = re.compile(
    r'\*{0,2}Requirements?:?\*{0,2}\s*`?([^`\n]+)`?', re.IGNORECASE
)
_COMPANION_HEADER = re.compile(
    r'\*{0,2}Companion\s+to:?\*{0,2}\s*`?([^`\n]+)`?', re.IGNORECASE
)
_DATE_HEADER = re.compile(
    r'\*{0,2}Date:?\*{0,2}\s*([\d\-/]+)', re.IGNORECASE
)
_TITLE_PATTERN = re.compile(r'^#\s+(.+)', re.MULTILINE)


def _extract_requirement_ids(
    text: str,
) -> List[Dict[str, str]]:
    """Find REQ-N/FR-N/NFR-N identifiers with surrounding context.

    Returns a list of ``{"id": ..., "title": ...}`` dicts.
    """
    results: List[Dict[str, str]] = []
    seen: set = set()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        for m in _REQ_ID_PATTERN.finditer(line):
            req_id = m.group(1).upper()
            if req_id in seen:
                continue
            seen.add(req_id)
            # Try to extract a title from the same line
            # Common patterns: "REQ-1: Title here" or "### REQ-1 — Title"
            after = line[m.end():].strip()
            title = ""
            if after.startswith(":") or after.startswith("—") or after.startswith("-"):
                title = after.lstrip(":—- ").strip()
            elif after and not after[0].isdigit():
                title = after
            # Truncate long titles
            if len(title) > 150:
                title = title[:150]
            results.append({"id": req_id, "title": title})
    return results


def _extract_phase_metadata(
    plan_lines: List[str],
) -> List[Dict[str, Any]]:
    """Parse phases with satisfies/depends_on/repo/deliverables metadata.

    Returns a list of phase dicts, each with:
    - phase_id: e.g. "phase-1"
    - heading: full heading text
    - satisfies: list of requirement IDs
    - depends_on: dependency string
    - repo: target repository
    - deliverables: dict with summary and file_count
    """
    phases: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    deliverable_lines: List[str] = []
    collecting_deliverables = False
    phase_counter = 0

    def _flush() -> None:
        nonlocal current, deliverable_lines, collecting_deliverables
        if current is None:
            return
        if deliverable_lines:
            current["deliverables"] = {
                "summary": "; ".join(deliverable_lines[:5]),
                "file_count": len(deliverable_lines),
            }
        phases.append(current)
        current = None
        deliverable_lines = []
        collecting_deliverables = False

    for ln in plan_lines:
        stripped = ln.strip()
        lowered = stripped.lower()

        # Detect phase headings
        if re.match(r'^#{2,3}\s*(phase|milestone|action|step|task)\b', lowered):
            _flush()
            phase_counter += 1
            heading_text = re.sub(r'^#{2,3}\s*', '', stripped).strip()
            current = {
                "phase_id": f"phase-{phase_counter}",
                "heading": heading_text,
                "satisfies": [],
                "depends_on": None,
                "repo": None,
                "deliverables": None,
            }
            continue

        # Non-phase top-level heading ends current phase
        if stripped.startswith("## ") and current is not None:
            if not re.match(r'^#{2,3}\s*(phase|milestone|action|step|task)\b', lowered):
                _flush()
                continue

        if current is None:
            continue

        # Parse metadata lines within a phase
        m = _SATISFIES_PATTERN.match(stripped)
        if m:
            raw = m.group(1).strip()
            ids = [x.upper() for x in _REQ_ID_PATTERN.findall(raw)]
            current["satisfies"] = ids if ids else [raw]
            continue

        m = _DEPENDS_ON_PATTERN.match(stripped)
        if m:
            current["depends_on"] = m.group(1).strip()
            continue

        m = _REPO_PATTERN.match(stripped)
        if m:
            current["repo"] = m.group(1).strip()
            continue

        m = _DELIVERABLES_PATTERN.match(stripped)
        if m:
            inline = m.group(1).strip()
            if inline:
                deliverable_lines.append(inline)
            collecting_deliverables = True
            continue

        m = _VALIDATION_PATTERN.match(stripped)
        if m:
            collecting_deliverables = False
            continue

        if collecting_deliverables:
            cm = _CHECKLIST_PATTERN.match(stripped)
            if cm:
                deliverable_lines.append(cm.group(2).strip())
                continue
            if stripped and not stripped.startswith(" ") and not stripped.startswith("-"):
                collecting_deliverables = False

    _flush()
    return phases


def _build_traceability_matrix(
    phases: List[Dict[str, Any]],
    req_inventory: Dict[str, Any],
) -> Dict[str, List[str]]:
    """Map REQ-ID -> [phase-IDs] that satisfy it."""
    matrix: Dict[str, List[str]] = {}

    # Collect all known requirement IDs
    for doc_name, doc_info in req_inventory.items():
        for entry in doc_info.get("ids", []):
            rid = entry["id"]
            if rid not in matrix:
                matrix[rid] = []

    # Map phases to requirements
    for phase in phases:
        for rid in phase.get("satisfies", []):
            rid_upper = rid.upper() if isinstance(rid, str) else rid
            if rid_upper not in matrix:
                matrix[rid_upper] = []
            matrix[rid_upper].append(phase["phase_id"])

    return matrix


def _build_dependency_graph(
    phases: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Phase dependency DAG: phase-id -> [dependency-phase-ids]."""
    graph: Dict[str, List[str]] = {}
    phase_ids = {p["phase_id"] for p in phases}

    for phase in phases:
        deps: List[str] = []
        dep_str = phase.get("depends_on") or ""
        if dep_str:
            dep_lower = dep_str.lower()
            # Check if string mentions "phase(s)" at all
            if re.search(r'phases?', dep_lower):
                # Match range patterns like "Phases 1-6" first
                range_matches = re.findall(r'phases?\s*(\d+)\s*[-–]\s*(\d+)', dep_lower)
                range_nums: set = set()
                for start, end in range_matches:
                    for num in range(int(start), int(end) + 1):
                        range_nums.add(str(num))
                # Extract all numbers in the dependency string as phase refs
                all_nums = re.findall(r'\b(\d+)\b', dep_lower)
                for num in all_nums:
                    dep_id = f"phase-{num}"
                    if dep_id in phase_ids and dep_id not in deps:
                        deps.append(dep_id)
                # Also add range numbers not yet covered
                for num in sorted(range_nums):
                    dep_id = f"phase-{num}"
                    if dep_id in phase_ids and dep_id not in deps:
                        deps.append(dep_id)
        graph[phase["phase_id"]] = deps

    return graph


def _detect_conflicts(
    req_inventory: Dict[str, Any],
) -> Dict[str, Any]:
    """Detect overlapping/contradictory requirements across documents."""
    # Collect all IDs per document
    id_to_docs: Dict[str, List[str]] = {}
    for doc_name, doc_info in req_inventory.items():
        for entry in doc_info.get("ids", []):
            rid = entry["id"]
            if rid not in id_to_docs:
                id_to_docs[rid] = []
            id_to_docs[rid].append(doc_name)

    overlapping = {
        rid: docs for rid, docs in id_to_docs.items() if len(docs) > 1
    }

    return {
        "overlapping_ids": overlapping,
        "contradictions": [],  # Placeholder for deeper semantic analysis
    }


def _extract_plan_header_metadata(
    plan_lines: List[str],
) -> Dict[str, Any]:
    """Parse header lines like **Requirements:** and **Companion to:**."""
    metadata: Dict[str, Any] = {
        "title": None,
        "date": None,
        "declared_requirements": [],
        "declared_companions": [],
    }

    for ln in plan_lines[:30]:  # Headers are always near the top
        stripped = ln.strip()

        if metadata["title"] is None:
            m = _TITLE_PATTERN.match(stripped)
            if m:
                metadata["title"] = m.group(1).strip()
                continue

        m = _DATE_HEADER.match(stripped)
        if m:
            metadata["date"] = m.group(1).strip()
            continue

        m = _REQUIREMENTS_HEADER.match(stripped)
        if m:
            metadata["declared_requirements"].append(m.group(1).strip())
            continue

        m = _COMPANION_HEADER.match(stripped)
        if m:
            metadata["declared_companions"].append(m.group(1).strip())
            continue

    return metadata


def analyze_plan(
    plan_text: str,
    plan_path: str,
    requirements_docs: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Analyze a plan and its requirements documents.

    Args:
        plan_text: Full text of the plan document.
        plan_path: Path to the plan file.
        requirements_docs: List of ``{"path": ..., "text": ...}`` dicts,
            one per requirements document.

    Returns:
        A ``plan-analysis.json``-compatible dict.
    """
    plan_lines = [ln.strip() for ln in plan_text.splitlines() if ln.strip()]

    # 1. Plan header metadata
    plan_metadata = _extract_plan_header_metadata(plan_lines)

    # 2. Requirement inventory (per-document)
    req_inventory: Dict[str, Any] = {}
    for doc in requirements_docs:
        doc_name = doc["path"].rsplit("/", 1)[-1] if "/" in doc["path"] else doc["path"]
        ids = _extract_requirement_ids(doc["text"])
        req_inventory[doc_name] = {
            "source_path": doc["path"],
            "ids": ids,
        }

    # Also extract from the plan itself (plans may reference requirement IDs)
    plan_ids = _extract_requirement_ids(plan_text)

    # 3. Phase metadata
    phases = _extract_phase_metadata(plan_lines)

    # 4. Traceability matrix
    traceability = _build_traceability_matrix(phases, req_inventory)

    # 5. Dependency graph
    dep_graph = _build_dependency_graph(phases)

    # 6. Conflict detection
    conflicts = _detect_conflicts(req_inventory)

    # 7. Statistics
    total_reqs = sum(len(d.get("ids", [])) for d in req_inventory.values())
    total_phases = len(phases)
    covered_reqs = sum(1 for phases_list in traceability.values() if phases_list)
    coverage_ratio = covered_reqs / total_reqs if total_reqs > 0 else 0.0

    return {
        "schema": "contextcore.io/plan-analysis/v1",
        "generated_at": datetime.now().isoformat(),
        "plan_path": plan_path,
        "plan_metadata": plan_metadata,
        "requirement_inventory": req_inventory,
        "plan_requirement_ids": plan_ids,
        "phase_metadata": [p for p in phases],
        "traceability_matrix": traceability,
        "dependency_graph": dep_graph,
        "conflict_report": conflicts,
        "statistics": {
            "total_requirements": total_reqs,
            "total_phases": total_phases,
            "covered_requirements": covered_reqs,
            "coverage_ratio": round(coverage_ratio, 3),
        },
    }
