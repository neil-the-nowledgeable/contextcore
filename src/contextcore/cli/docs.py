"""
Documentation Index CLI commands.

Provides tooling for generating and querying the documentation index:
- index: Generate contextcore.docs.yaml from capability index + directory scan
- show: Query the docs index with filters (type, orphaned, capability, freshness)
- audit: Reverse-engineer capability indexes to find documentation gaps
- curate: Generate persona-specific documentation catalogs with gap detection

Usage:
    contextcore docs index
    contextcore docs index --dry-run --no-git
    contextcore docs show
    contextcore docs show --type requirements
    contextcore docs show --orphaned
    contextcore docs show --capability contextcore.pipeline.check_pipeline
    contextcore docs show --refs-for docs/MANIFEST_EXPORT_REQUIREMENTS.md
    contextcore docs show --stale-days 30
    contextcore docs audit
    contextcore docs audit --min-importance 0.5
    contextcore docs audit --type requirements --verbose
    contextcore docs curate
    contextcore docs curate --persona operator
    contextcore docs curate --category onboarding --gaps-only
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import yaml


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = "docs/capability-index/contextcore.docs.yaml"

CAPABILITY_INDEX_FILES = [
    "contextcore.agent.yaml",
    "contextcore.user.yaml",
    "contextcore.benefits.yaml",
    "contextcore.pain_points.yaml",
]

DOC_SCAN_DIRS = ["docs", "plans"]
DOC_EXTENSIONS = {".md", ".yaml", ".yml"}
EXCLUDE_PATTERNS = {"docs/capability-index", "docs/plans/.startd8"}


# ---------------------------------------------------------------------------
# Document type taxonomy
# ---------------------------------------------------------------------------

DOCUMENT_TYPES = {
    "requirements": "Behavioral specification (FR/NFR, acceptance criteria)",
    "design": "Implementation design, schema definitions, architecture",
    "operational": "How-to guides, runbooks, setup instructions, troubleshooting",
    "adr": "Architecture Decision Records",
    "analysis": "Investigative analysis, gap assessment, audit",
    "plan": "Implementation plans with phases, milestones, checklists",
    "reference": "Semantic conventions, API reference, specifications",
    "session": "Session logs, meeting notes, retrospectives",
    "governance": "Policies, licenses, governance rules",
}

# Filename-based classification (order matters: first match wins)
_FILENAME_TYPE_RULES = [
    (re.compile(r"^docs/adr/"), "adr"),
    (re.compile(r"_requirements\b|REQUIREMENTS\b", re.I), "requirements"),
    (re.compile(r"^plans/"), "plan"),
    (re.compile(r"^docs/plans/"), "plan"),
    (re.compile(r"_plan\b|PLAN\b|checklist|execution_|kickoff|agenda", re.I), "plan"),
    (re.compile(r"troubleshoot|runbook|installation\b|quickstart|setup|known.?issues|how.?to|guide\b|onboarding", re.I), "operational"),
    (re.compile(r"analysis|audit\b|gap_|comparison|_issues\b|improvement|feedback|data.?issues", re.I), "analysis"),
    (re.compile(r"design\b|schema\b|contract\b|architecture|blueprint|_pattern\b", re.I), "design"),
    (re.compile(r"session\b|_log\b|retrospective|handoff\b|notes\b", re.I), "session"),
    (re.compile(r"license|governance|policy\b", re.I), "governance"),
    (re.compile(r"convention|reference|migration|naming\b|_spec\b|semantic|value.?prop|alignment\b|standard", re.I), "reference"),
    (re.compile(r"^docs/dashboards/", re.I), "design"),
    (re.compile(r"harbor.?tour", re.I), "operational"),
    (re.compile(r"submission|proposal|issue", re.I), "reference"),
    (re.compile(r"pattern|prevention|truncation|workflow\b", re.I), "design"),
]

# Content-based classification fallback
_CONTENT_TYPE_SIGNALS = [
    (re.compile(r"functional.?requirement|FR-\d|acceptance.?criteria|shall\b.*requirement", re.I), "requirements"),
    (re.compile(r"phase\s+\d|milestone|timeline|estimated.?completion|deliverable", re.I), "plan"),
    (re.compile(r"architecture|data.?model|schema|sequence.?diagram", re.I), "design"),
    (re.compile(r"step\s+\d.*:|prerequisit|install|configure|troubleshoot", re.I), "operational"),
    (re.compile(r"gap.?analysis|findings|recommendation|observation|current.?state", re.I), "analysis"),
]

# Maturity signals
_MATURITY_SIGNALS = {
    "draft": re.compile(r"\bDRAFT\b|\[DRAFT\]|\bWIP\b|work.?in.?progress", re.I),
    "stable": re.compile(r"living.?guidance|intentionally.?living|production.?ready", re.I),
    "deprecated": re.compile(r"\bDEPRECATED\b|\[DEPRECATED\]|superseded.?by|replaced.?by", re.I),
}

# Cross-reference patterns
_DOC_REF_PATTERNS = [
    re.compile(r"\]\(([^)]+\.(?:md|yaml|yml))\)"),
    re.compile(r"`((?:docs|plans|examples)/[^`]+\.(?:md|yaml|yml))`"),
    re.compile(r"(?:^|\s)((?:docs|plans|examples)/[\w/.-]+\.(?:md|yaml|yml))"),
]


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _should_exclude(rel_path: str) -> bool:
    return any(rel_path.startswith(p) for p in EXCLUDE_PATTERNS)


def _classify_doc_type(rel_path: str, content: str) -> str:
    for pattern, doc_type in _FILENAME_TYPE_RULES:
        if pattern.search(rel_path):
            return doc_type
    for pattern, doc_type in _CONTENT_TYPE_SIGNALS:
        if pattern.search(content[:3000]):
            return doc_type
    return "unknown"


def _extract_title(content: str) -> str:
    for line in content.split("\n")[:20]:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _detect_maturity(content: str) -> str:
    header = content[:2000]
    if _MATURITY_SIGNALS["deprecated"].search(header):
        return "deprecated"
    if _MATURITY_SIGNALS["draft"].search(header):
        return "draft"
    if _MATURITY_SIGNALS["stable"].search(header):
        return "stable"
    return "active"


def _extract_scope_keywords(content: str) -> list:
    keywords = set()
    for m in re.finditer(r"contextcore\s+([\w-]+(?:\s+[\w-]+)?)", content):
        keywords.add(f"contextcore {m.group(1).strip()}")
    for m in re.finditer(r"(?:step|gate)\s+(\d+)", content, re.I):
        keywords.add(f"pipeline step {m.group(1)}")
    return sorted(keywords)[:10]


def _extract_cross_references(content: str, own_path: str) -> list:
    refs = set()
    for pattern in _DOC_REF_PATTERNS:
        for match in pattern.finditer(content):
            ref = match.group(1).strip()
            ref = re.sub(r"^(\.\./)*", "", ref)
            ref = re.sub(r"^\./", "", ref)
            if ref == own_path or ref.startswith(("#", "http://", "https://")):
                continue
            refs.add(ref)
    return sorted(refs)


def _make_doc_id(rel_path: str) -> str:
    p = Path(rel_path)
    stem = p.stem.lower().replace("-", "_")
    parts = list(p.parent.parts)
    if parts and parts[0] == "docs":
        parts = parts[1:]
    if parts:
        subdomain = ".".join(part.lower().replace("-", "_") for part in parts)
        return f"contextcore.docs.{subdomain}.{stem}"
    return f"contextcore.docs.{stem}"


# ---------------------------------------------------------------------------
# Core generation logic
# ---------------------------------------------------------------------------

def _extract_doc_evidence(repo_root: Path) -> dict:
    """Extract type: doc evidence from capability index files."""
    index_dir = repo_root / "docs" / "capability-index"
    doc_refs = defaultdict(list)

    for filename in CAPABILITY_INDEX_FILES:
        filepath = index_dir / filename
        if not filepath.exists():
            continue
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError:
            click.echo(f"  Warning: skipping {filename} (YAML parse error)", err=True)
            continue
        if not data:
            continue

        capabilities = data.get("capabilities", []) or data.get("benefits", []) or []
        for cap in capabilities:
            cap_id = cap.get("capability_id") or cap.get("benefit_id", "unknown")
            for ev in cap.get("evidence", []):
                if ev.get("type") == "doc":
                    doc_refs[ev["ref"]].append({
                        "capability_id": cap_id,
                        "description": ev.get("description", ""),
                    })
        for ev in data.get("evidence", []):
            if ev.get("type") == "doc":
                doc_refs[ev["ref"]].append({
                    "capability_id": "_global",
                    "description": ev.get("description", ""),
                })

    return dict(doc_refs)


def _scan_doc_directories(repo_root: Path) -> list:
    """Scan doc directories for all documentation files."""
    doc_files = []
    for scan_dir in DOC_SCAN_DIRS:
        dir_path = repo_root / scan_dir
        if not dir_path.exists():
            continue
        for root, _dirs, files in os.walk(dir_path):
            for fname in sorted(files):
                fpath = Path(root) / fname
                rel = str(fpath.relative_to(repo_root))
                if fpath.suffix not in DOC_EXTENSIONS:
                    continue
                if _should_exclude(rel):
                    continue
                doc_files.append(rel)
    return sorted(doc_files)


def _get_git_last_modified(rel_paths: list, repo_root: Path) -> dict:
    """Get git last-modified dates for files."""
    result = {}
    for rel_path in rel_paths:
        try:
            proc = subprocess.run(
                ["git", "log", "-1", "--format=%aI", "--", rel_path],
                capture_output=True, text=True, cwd=str(repo_root), timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                result[rel_path] = proc.stdout.strip()[:10]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return result


def _analyze_document(rel_path: str, repo_root: Path) -> dict:
    """Analyze a single document file."""
    full_path = repo_root / rel_path
    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"title": "", "doc_type": "unknown", "maturity": "unknown",
                "line_count": 0, "scope_keywords": [], "references": []}

    if rel_path.endswith((".yaml", ".yml")):
        return {"title": "", "doc_type": _classify_doc_type(rel_path, content),
                "maturity": "active", "line_count": sum(1 for l in content.split("\n") if l.strip()),
                "scope_keywords": [], "references": []}

    return {
        "title": _extract_title(content),
        "doc_type": _classify_doc_type(rel_path, content),
        "maturity": _detect_maturity(content),
        "line_count": sum(1 for l in content.split("\n") if l.strip()),
        "scope_keywords": _extract_scope_keywords(content),
        "references": _extract_cross_references(content, rel_path),
    }


def generate_docs_index(repo_root: Path, skip_git: bool = False) -> dict:
    """Generate the complete documentation index.

    This is the core logic shared between the CLI and the standalone script.
    """
    doc_evidence = _extract_doc_evidence(repo_root)
    all_doc_files = _scan_doc_directories(repo_root)
    git_dates = {} if skip_git else _get_git_last_modified(all_doc_files, repo_root)
    all_paths_set = set(all_doc_files)

    documents = []
    referenced_count = 0
    orphan_count = 0
    type_counts = defaultdict(int)

    for rel_path in all_doc_files:
        metadata = _analyze_document(rel_path, repo_root)

        governs = []
        if rel_path in doc_evidence:
            for ref in doc_evidence[rel_path]:
                governs.append({
                    "capability_id": ref["capability_id"],
                    "role": ref["description"],
                })
            referenced_count += 1
        else:
            orphan_count += 1

        doc_type = metadata["doc_type"]
        type_counts[doc_type] += 1

        doc_entry = {
            "doc_id": _make_doc_id(rel_path),
            "path": rel_path,
            "type": doc_type,
            "maturity": metadata["maturity"],
            "referenced": bool(governs),
        }

        if metadata["title"]:
            doc_entry["title"] = metadata["title"]
        if metadata["line_count"]:
            doc_entry["line_count"] = metadata["line_count"]
        if metadata["scope_keywords"]:
            doc_entry["scope_keywords"] = metadata["scope_keywords"]
        if governs:
            doc_entry["governs_capabilities"] = governs

        valid_refs = [r for r in metadata.get("references", []) if r in all_paths_set]
        if valid_refs:
            doc_entry["references"] = valid_refs

        if rel_path in git_dates:
            doc_entry["last_modified"] = git_dates[rel_path]

        documents.append(doc_entry)

    # External evidence refs
    external_refs = []
    for ref_path, refs in doc_evidence.items():
        if ref_path not in all_paths_set:
            external_refs.append({
                "path": ref_path,
                "referenced_by": [r["capability_id"] for r in refs],
            })

    total_cross_refs = sum(len(d.get("references", [])) for d in documents)
    docs_with_refs = sum(1 for d in documents if d.get("references"))

    index = {
        "manifest_id": "contextcore.docs",
        "name": "ContextCore Documentation Index",
        "version": "2.0.0",
        "description": (
            "Programmatically derived documentation index. "
            "Generated by contextcore docs index from capability index "
            "evidence entries and docs/ directory scan."
        ),
        "generated_at": date.today().isoformat(),
        "generator": "contextcore docs index",
        "sources": {
            "capability_index_files": CAPABILITY_INDEX_FILES,
            "scanned_directories": DOC_SCAN_DIRS,
        },
        "document_types": DOCUMENT_TYPES,
        "summary": {
            "total_documents": len(documents),
            "referenced_by_capabilities": referenced_count,
            "orphaned": orphan_count,
            "by_type": dict(sorted(type_counts.items())),
            "cross_references": total_cross_refs,
            "documents_with_cross_references": docs_with_refs,
            "external_evidence_refs": len(external_refs),
        },
        "documents": documents,
    }

    if external_refs:
        index["external_evidence_refs"] = sorted(external_refs, key=lambda x: x["path"])

    return index


# ---------------------------------------------------------------------------
# Audit: Importance scoring, expected-doc rules, gap detection, clustering
# ---------------------------------------------------------------------------

# All four capability index files used by the audit engine
_AUDIT_INDEX_FILES = {
    "agent": "contextcore.agent.yaml",
    "user": "contextcore.user.yaml",
    "benefits": "contextcore.benefits.yaml",
    "roadmap": "roadmap.yaml",
}

_MATURITY_WEIGHTS = {"stable": 1.0, "beta": 0.7, "draft": 0.4}
_CATEGORY_BONUS = {"validate": 0.3, "integration": 0.3}
_PRIORITY_WEIGHTS = {"high": 1.0, "medium": 0.6, "low": 0.3}
_STATUS_WEIGHTS = {"gap": 1.0, "partial": 0.7, "delivered": 0.4}


def _load_all_indexes(repo_root: Path) -> dict:
    """Load all capability index files into a structured dict."""
    index_dir = repo_root / "docs" / "capability-index"
    result = {}
    for key, filename in _AUDIT_INDEX_FILES.items():
        filepath = index_dir / filename
        if not filepath.exists():
            result[key] = None
            continue
        try:
            with open(filepath) as f:
                result[key] = yaml.safe_load(f)
        except yaml.YAMLError:
            result[key] = None
    return result


def _extract_all_capabilities(indexes: dict) -> list:
    """Extract capability entries from agent and user indexes."""
    caps = []
    for source_key in ("agent", "user"):
        data = indexes.get(source_key)
        if not data:
            continue
        for cap in data.get("capabilities", []):
            cap["_source"] = source_key
            caps.append(cap)
    return caps


def _build_benefit_lookup(indexes: dict) -> dict:
    """Build benefit_id -> benefit dict and delivered_by reverse index."""
    data = indexes.get("benefits")
    if not data:
        return {}
    lookup = {}
    for b in data.get("benefits", []):
        bid = b.get("benefit_id", "")
        lookup[bid] = b
    return lookup


def _build_dependency_fanout(capabilities: list) -> dict:
    """Count how many capabilities depend on each capability (inbound deps)."""
    fanout = defaultdict(int)
    for cap in capabilities:
        for dep in cap.get("dependencies", []):
            fanout[dep] += 1
        roadmap = cap.get("roadmap", {})
        if isinstance(roadmap, dict):
            for dep in roadmap.get("depends_on", []):
                fanout[dep] += 1
    return dict(fanout)


def _build_cap_to_benefit(capabilities: list, benefit_lookup: dict) -> dict:
    """Map capability_id -> benefit entry via delivers_benefit and delivered_by."""
    result = {}
    # Forward: capability.delivers_benefit -> benefit
    for cap in capabilities:
        db = cap.get("delivers_benefit")
        if db and db in benefit_lookup:
            result[cap["capability_id"]] = benefit_lookup[db]
    # Reverse: benefit.delivered_by -> capabilities
    for bid, benefit in benefit_lookup.items():
        for cap_id in benefit.get("delivered_by", []):
            if cap_id not in result:
                result[cap_id] = benefit
    return result


def _count_input_properties(cap: dict) -> int:
    """Count input schema properties."""
    inputs = cap.get("inputs", {})
    if not isinstance(inputs, dict):
        return 0
    props = inputs.get("properties", {})
    return len(props) if isinstance(props, dict) else 0


def _count_required_fields(cap: dict) -> int:
    """Count required input fields."""
    inputs = cap.get("inputs", {})
    if not isinstance(inputs, dict):
        return 0
    req = inputs.get("required", [])
    return len(req) if isinstance(req, list) else 0


def _count_output_properties(cap: dict) -> int:
    """Count output schema properties."""
    outputs = cap.get("outputs", {})
    if not isinstance(outputs, dict):
        return 0
    props = outputs.get("properties", {})
    return len(props) if isinstance(props, dict) else 0


def _normalize_0_1(value: float, max_val: float) -> float:
    """Normalize to [0, 1] with a soft ceiling."""
    if max_val <= 0:
        return 0.0
    return min(value / max_val, 1.0)


def score_importance(cap: dict, fanout: dict, cap_benefit: dict) -> dict:
    """Compute the 4-dimension importance score for a capability.

    Returns dict with dimension scores and final weighted score.
    """
    cap_id = cap.get("capability_id", "")

    # --- Dimension A: Maturity-Confidence Composite (30%) ---
    maturity = cap.get("maturity", "draft")
    confidence = cap.get("confidence", 0.5)
    mat_weight = _MATURITY_WEIGHTS.get(maturity, 0.4)
    mc_composite = 0.6 * mat_weight + 0.4 * confidence

    # --- Dimension B: Structural Complexity (25%) ---
    input_props = _count_input_properties(cap)
    required_count = _count_required_fields(cap)
    output_props = _count_output_properties(cap)
    anti_count = len(cap.get("anti_patterns", []))
    risk_count = len(cap.get("risk_flags", []))
    raw_complexity = (
        input_props + required_count + output_props
        + 2 * anti_count
        + 3 * risk_count
    )
    # Empirical max: ~20 (8 input + 3 required + 5 output + 2*3 + 3*0)
    complexity = _normalize_0_1(raw_complexity, 20.0)

    # --- Dimension C: Cross-Cutting Impact (25%) ---
    cap_fanout = fanout.get(cap_id, 0)
    persona_count = len(cap.get("personas", []))
    # For benefits-linked persona importance, check benefit
    critical_personas = 0
    benefit = cap_benefit.get(cap_id)
    if benefit:
        for p in benefit.get("personas", []):
            if isinstance(p, dict) and p.get("importance") == "critical":
                critical_personas += 1
    category = cap.get("category", "action")
    cat_bonus = _CATEGORY_BONUS.get(category, 0.0)
    raw_cross = 3 * cap_fanout + persona_count + 2 * critical_personas + cat_bonus * 10
    # Empirical max: ~15 (3*3 fanout + 4 personas + 2*2 critical + 3 bonus)
    cross_cutting = _normalize_0_1(raw_cross, 15.0)

    # --- Dimension D: Benefit Linkage (20%) ---
    if benefit:
        priority = benefit.get("priority", "medium")
        status = benefit.get("delivery_status", "delivered")
        persona_breadth = min(len(benefit.get("personas", [])) / 4.0, 1.0)
        benefit_score = (
            _PRIORITY_WEIGHTS.get(priority, 0.6)
            * persona_breadth
            * _STATUS_WEIGHTS.get(status, 0.4)
        )
    else:
        benefit_score = 0.2  # orphan capability — mild concern

    # --- Final weighted score ---
    final = (
        0.30 * mc_composite
        + 0.25 * complexity
        + 0.25 * cross_cutting
        + 0.20 * benefit_score
    )

    return {
        "importance": round(final, 3),
        "mc_composite": round(mc_composite, 3),
        "complexity": round(complexity, 3),
        "cross_cutting": round(cross_cutting, 3),
        "benefit_linkage": round(benefit_score, 3),
        "detail": {
            "maturity": maturity,
            "confidence": confidence,
            "input_props": input_props,
            "required_fields": required_count,
            "output_props": output_props,
            "anti_patterns": anti_count,
            "risk_flags": risk_count,
            "fanout": cap_fanout,
            "persona_count": persona_count,
            "critical_personas": critical_personas,
            "category": category,
            "has_benefit": benefit is not None,
        },
    }


# ---------------------------------------------------------------------------
# Expected Document Rules
# ---------------------------------------------------------------------------

def _has_cli_triggers(cap: dict) -> bool:
    """Check if any trigger phrases mention CLI-like commands."""
    for trigger in cap.get("triggers", []):
        if re.search(r"contextcore|cli|command", trigger, re.I):
            return True
    # Also check agent description for CLI mentions
    desc = cap.get("description", {})
    agent_desc = desc.get("agent", "") if isinstance(desc, dict) else ""
    return bool(re.search(r"CLI:|`contextcore\s", agent_desc))


def compute_expected_docs(cap: dict, benefit: Optional[dict]) -> set:
    """Determine which document types should exist for a capability.

    Returns a set of expected doc type strings.
    """
    expected = set()
    maturity = cap.get("maturity", "draft")
    confidence = cap.get("confidence", 0.5)
    category = cap.get("category", "action")
    input_props = _count_input_properties(cap)
    anti_count = len(cap.get("anti_patterns", []))
    risk_count = len(cap.get("risk_flags", []))

    # R1: requirements — stable + (CLI command OR complex inputs)
    if maturity == "stable" and (_has_cli_triggers(cap) or input_props >= 3):
        expected.add("requirements")

    # R2: design — stable/beta + high complexity
    raw_complexity = (
        input_props + _count_required_fields(cap) + _count_output_properties(cap)
        + 2 * anti_count + 3 * risk_count
    )
    if maturity in ("stable", "beta") and raw_complexity > 10:
        expected.add("design")

    # R3: operational — has CLI triggers
    if _has_cli_triggers(cap):
        expected.add("operational")

    # R4: adr — has anti_patterns or risk_flags
    if anti_count > 0 or risk_count > 0:
        expected.add("adr")

    # R5: requirements — validate category + stable
    if category == "validate" and maturity == "stable":
        expected.add("requirements")

    # R6: design — integration category
    if category == "integration":
        expected.add("design")

    # R7: requirements — delivers a gap benefit with functional_requirements
    if benefit:
        if benefit.get("delivery_status") == "gap":
            frs = benefit.get("functional_requirements", [])
            if frs:
                expected.add("requirements")

    # R8: reference — stable + high confidence
    if maturity == "stable" and confidence >= 0.9:
        expected.add("reference")

    return expected


# ---------------------------------------------------------------------------
# Gap Detection
# ---------------------------------------------------------------------------

def _build_doc_coverage(docs_index: dict) -> dict:
    """Build capability_id -> set of doc types from the docs index.

    Reads governs_capabilities from each document and maps capability_id
    to the set of document types that cover it.
    """
    coverage = defaultdict(set)
    for doc in docs_index.get("documents", []):
        doc_type = doc.get("type", "unknown")
        for gov in doc.get("governs_capabilities", []):
            cap_id = gov.get("capability_id", "")
            if cap_id and cap_id != "_global":
                coverage[cap_id].add(doc_type)
    return dict(coverage)


def detect_gaps(capabilities: list, indexes: dict, docs_index: dict) -> list:
    """Detect documentation gaps for all capabilities.

    Returns a list of gap dicts sorted by importance descending.
    """
    benefit_lookup = _build_benefit_lookup(indexes)
    fanout = _build_dependency_fanout(capabilities)
    cap_benefit = _build_cap_to_benefit(capabilities, benefit_lookup)
    doc_coverage = _build_doc_coverage(docs_index)

    gaps = []
    for cap in capabilities:
        cap_id = cap.get("capability_id", "")
        importance_data = score_importance(cap, fanout, cap_benefit)
        expected = compute_expected_docs(cap, cap_benefit.get(cap_id))
        actual = doc_coverage.get(cap_id, set())
        missing = expected - actual

        if not missing:
            continue

        gaps.append({
            "capability_id": cap_id,
            "source": cap.get("_source", "agent"),
            "maturity": cap.get("maturity", "draft"),
            "category": cap.get("category", "action"),
            "importance": importance_data["importance"],
            "importance_detail": importance_data,
            "expected_doc_types": sorted(expected),
            "actual_doc_types": sorted(actual),
            "missing_doc_types": sorted(missing),
            "rationale": _build_rationale(cap, missing, importance_data),
        })

    gaps.sort(key=lambda g: g["importance"], reverse=True)
    return gaps


def _build_rationale(cap: dict, missing: set, importance_data: dict) -> str:
    """Build a human-readable rationale for why docs are needed."""
    parts = []
    detail = importance_data["detail"]

    if detail["anti_patterns"] > 0:
        parts.append(f"{detail['anti_patterns']} anti-patterns")
    if detail["risk_flags"] > 0:
        parts.append(f"{detail['risk_flags']} risk flags")
    if detail["input_props"] >= 3:
        parts.append(f"{detail['input_props']} input properties")
    if detail["fanout"] > 0:
        parts.append(f"depended on by {detail['fanout']} other capabilities")
    if detail["critical_personas"] > 0:
        parts.append(f"{detail['critical_personas']} critical personas")
    if not detail["has_benefit"]:
        parts.append("no benefit linkage")

    if "requirements" in missing and detail["maturity"] == "stable":
        parts.append("stable capability without requirements doc")
    if "adr" in missing and (detail["anti_patterns"] > 0 or detail["risk_flags"] > 0):
        parts.append("lessons/risks not captured in ADR")
    if "operational" in missing:
        parts.append("CLI command without operational guide")

    return "; ".join(parts) if parts else "documentation coverage below expected level"


# ---------------------------------------------------------------------------
# Cluster Consolidation
# ---------------------------------------------------------------------------

def _cluster_namespace(cap_id: str) -> str:
    """Extract cluster namespace (first two dotted segments)."""
    parts = cap_id.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return cap_id


def _suggest_filename(cluster_ns: str, doc_type: str) -> str:
    """Suggest a filename for a cluster gap."""
    # contextcore.handoff -> HANDOFF, contextcore.aos -> AOS
    parts = cluster_ns.split(".")
    name_part = parts[-1].upper() if len(parts) > 1 else cluster_ns.upper()
    type_suffix = {
        "requirements": "REQUIREMENTS",
        "design": "DESIGN",
        "operational": "GUIDE",
        "adr": "ADR",
        "reference": "REFERENCE",
        "analysis": "ANALYSIS",
    }
    suffix = type_suffix.get(doc_type, doc_type.upper())
    return f"docs/{name_part}_{suffix}.md"


def consolidate_clusters(gaps: list) -> list:
    """Group gaps by namespace and missing doc type, merge into clusters.

    Returns a list of cluster-gap dicts sorted by avg importance descending.
    """
    # Group: (cluster_ns, missing_type) -> list of gaps
    cluster_map = defaultdict(list)
    for gap in gaps:
        ns = _cluster_namespace(gap["capability_id"])
        for missing_type in gap["missing_doc_types"]:
            cluster_map[(ns, missing_type)].append(gap)

    clusters = []
    for (ns, missing_type), members in cluster_map.items():
        importances = [m["importance"] for m in members]
        avg_importance = sum(importances) / len(importances)
        max_member = max(members, key=lambda m: m["importance"])

        # Merge rationales (deduplicate)
        all_rationale_parts = set()
        for m in members:
            for part in m["rationale"].split("; "):
                if part:
                    all_rationale_parts.add(part)

        clusters.append({
            "cluster": f"{ns}.*",
            "missing_type": missing_type,
            "capability_count": len(members),
            "avg_importance": round(avg_importance, 3),
            "max_importance": round(max(importances), 3),
            "highest_capability": max_member["capability_id"],
            "highest_maturity": max_member["maturity"],
            "capabilities": [m["capability_id"] for m in members],
            "rationale": "; ".join(sorted(all_rationale_parts)),
            "suggested_file": _suggest_filename(ns, missing_type),
            "priority": (
                "high" if avg_importance >= 0.6
                else "medium" if avg_importance >= 0.4
                else "low"
            ),
        })

    clusters.sort(key=lambda c: c["avg_importance"], reverse=True)
    return clusters


def run_audit(repo_root: Path, docs_index: dict, min_importance: float = 0.3) -> dict:
    """Run the full documentation audit.

    Returns audit results with per-capability gaps, clusters, and summary.
    """
    indexes = _load_all_indexes(repo_root)
    capabilities = _extract_all_capabilities(indexes)
    all_gaps = detect_gaps(capabilities, indexes, docs_index)
    filtered_gaps = [g for g in all_gaps if g["importance"] >= min_importance]
    clusters = consolidate_clusters(filtered_gaps)

    # Summary
    high_clusters = sum(1 for c in clusters if c["priority"] == "high")
    medium_clusters = sum(1 for c in clusters if c["priority"] == "medium")
    low_clusters = sum(1 for c in clusters if c["priority"] == "low")

    missing_type_counts = defaultdict(int)
    for g in filtered_gaps:
        for mt in g["missing_doc_types"]:
            missing_type_counts[mt] += 1

    return {
        "audit_date": date.today().isoformat(),
        "min_importance_threshold": min_importance,
        "summary": {
            "capabilities_analyzed": len(capabilities),
            "with_documentation_gaps": len(filtered_gaps),
            "cluster_gaps_identified": len(clusters),
            "priority_breakdown": {
                "high": high_clusters,
                "medium": medium_clusters,
                "low": low_clusters,
            },
            "missing_doc_types": dict(sorted(
                missing_type_counts.items(), key=lambda x: -x[1]
            )),
        },
        "clusters": clusters,
        "per_capability_gaps": filtered_gaps,
    }


# ---------------------------------------------------------------------------
# Personas: persona-to-documentation mapping engine
# ---------------------------------------------------------------------------

# Document type affinity per persona role
_PERSONA_TYPE_AFFINITY = {
    "developer": {"requirements", "design", "reference", "operational"},
    "project_manager": {"plan", "operational", "analysis"},
    "engineering_leader": {"design", "plan", "analysis"},
    "operator": {"operational", "reference"},
    "compliance": {"governance", "reference", "analysis"},
    "ai_agent": {"reference", "design"},
}

# Onboarding vs operations classification
_ONBOARDING_TITLE_SIGNALS = re.compile(
    r"quickstart|getting.?started|install|onboarding|harbor.?tour|"
    r"first.?steps|setup|introduction|overview|tutorial",
    re.I,
)
_OPERATIONS_TITLE_SIGNALS = re.compile(
    r"troubleshoot|runbook|known.?issues|migration|upgrade|"
    r"incident|recovery|maintenance|monitoring",
    re.I,
)


def _load_personas(indexes: dict) -> dict:
    """Load persona definitions from benefits.yaml and user.yaml.

    Returns persona_id -> {name, description, goals, primary_value, pain_point}.
    """
    personas = {}
    benefits_data = indexes.get("benefits")
    if benefits_data and isinstance(benefits_data.get("personas"), dict):
        for pid, pdata in benefits_data["personas"].items():
            personas[pid] = {
                "persona_id": pid,
                "name": pdata.get("name", pid),
                "description": pdata.get("description", ""),
                "goals": pdata.get("goals", []),
                "primary_value": "",
                "pain_point": "",
            }

    user_data = indexes.get("user")
    if user_data and isinstance(user_data.get("personas"), dict):
        for pid, pdata in user_data["personas"].items():
            if pid not in personas:
                personas[pid] = {
                    "persona_id": pid,
                    "name": pid,
                    "description": "",
                    "goals": [],
                }
            personas[pid]["primary_value"] = pdata.get("primary_value", "")
            personas[pid]["pain_point"] = pdata.get("pain_point", "")

    return personas


def _walk_capability_evidence(capabilities: list) -> dict:
    """Build capability_id -> list of doc evidence refs."""
    cap_docs = defaultdict(list)
    for cap in capabilities:
        cap_id = cap.get("capability_id", "")
        for ev in cap.get("evidence", []):
            if ev.get("type") == "doc":
                cap_docs[cap_id].append(ev.get("ref", ""))
    return dict(cap_docs)


def _persona_capability_ids(indexes: dict) -> dict:
    """Map persona_id -> set of capability_ids from user.yaml."""
    result = defaultdict(set)
    user_data = indexes.get("user")
    if user_data:
        for cap in user_data.get("capabilities", []):
            cap_id = cap.get("capability_id", "")
            for pid in cap.get("personas", []):
                result[pid].add(cap_id)
    return dict(result)


def _persona_benefit_caps(indexes: dict) -> dict:
    """Map persona_id -> list of {benefit_id, importance, delivered_by} from benefits.yaml."""
    result = defaultdict(list)
    benefits_data = indexes.get("benefits")
    if not benefits_data:
        return {}
    for benefit in benefits_data.get("benefits", []):
        bid = benefit.get("benefit_id", "")
        delivered_by = benefit.get("delivered_by", [])
        for p in benefit.get("personas", []):
            if isinstance(p, dict):
                pid = p.get("persona_id", "")
                importance = p.get("importance", "medium")
            else:
                pid = str(p)
                importance = "medium"
            if pid:
                result[pid].append({
                    "benefit_id": bid,
                    "importance": importance,
                    "delivery_status": benefit.get("delivery_status", "gap"),
                    "delivered_by": delivered_by if isinstance(delivered_by, list) else [],
                })
    return dict(result)


def _classify_doc_category(doc: dict) -> str:
    """Classify a document as 'onboarding' or 'operations'."""
    doc_type = doc.get("type", "unknown")
    title = doc.get("title", "")
    path = doc.get("path", "")
    combined = f"{title} {path}"

    # Explicit onboarding signals
    if _ONBOARDING_TITLE_SIGNALS.search(combined):
        return "onboarding"
    # Explicit operations signals
    if _OPERATIONS_TITLE_SIGNALS.search(combined):
        return "operations"

    # Type-based defaults
    if doc_type == "reference":
        return "onboarding"
    if doc_type == "operational":
        return "onboarding"  # default for guides
    if doc_type in ("requirements", "design", "analysis", "plan", "adr", "governance"):
        return "operations"

    return "operations"  # fallback


def _detect_persona_gaps(persona_id: str, persona: dict,
                         onboarding_docs: list, operations_docs: list,
                         benefit_info: list) -> list:
    """Detect documentation gaps for a persona."""
    gaps = []

    if not onboarding_docs:
        gaps.append({
            "gap": f"No onboarding documentation for {persona['name']}",
            "suggested": f"docs/onboarding/{persona_id.replace('_', '-')}-quickstart.md",
            "priority": "high",
        })

    if not operations_docs:
        gaps.append({
            "gap": f"No operations documentation for {persona['name']}",
            "suggested": f"docs/operations/{persona_id.replace('_', '-')}-guide.md",
            "priority": "medium",
        })

    # Check critical benefits have doc coverage
    for bi in benefit_info:
        if bi["importance"] == "critical" and bi["delivery_status"] != "gap":
            # Check if any onboarding doc covers the delivering capabilities
            covered_caps = set()
            for doc in onboarding_docs + operations_docs:
                covered_caps.update(doc.get("via_capabilities", []))
            uncovered = [c for c in bi["delivered_by"] if c not in covered_caps]
            if uncovered:
                caps_str = ", ".join(uncovered)
                gaps.append({
                    "gap": (f"Critical benefit '{bi['benefit_id']}' — "
                            f"capabilities {caps_str} lack documentation for {persona['name']}"),
                    "suggested": None,
                    "priority": "high",
                })

    # Persona-specific gap rules
    if persona_id == "operator":
        has_troubleshoot = any(
            _OPERATIONS_TITLE_SIGNALS.search(d.get("title", "") + " " + d.get("path", ""))
            for d in operations_docs
        )
        if not has_troubleshoot:
            gaps.append({
                "gap": "No troubleshooting/runbook documentation for operator persona",
                "suggested": f"docs/operations/operator-troubleshooting.md",
                "priority": "medium",
            })

    if persona_id == "compliance":
        has_governance = any(d.get("type") == "governance" for d in operations_docs)
        if not has_governance:
            gaps.append({
                "gap": "No governance/audit procedure documentation for compliance persona",
                "suggested": f"docs/governance/compliance-audit-procedures.md",
                "priority": "medium",
            })

    return gaps


def run_curate(repo_root: Path, docs_index: dict,
                 min_relevance: float = 0.4,
                 persona_filter: Optional[str] = None) -> dict:
    """Run persona-to-documentation analysis.

    Returns per-persona doc catalogs with onboarding/operations classification
    and gap detection.
    """
    indexes = _load_all_indexes(repo_root)
    personas = _load_personas(indexes)
    all_caps = _extract_all_capabilities(indexes)
    cap_evidence = _walk_capability_evidence(all_caps)
    persona_caps = _persona_capability_ids(indexes)
    persona_benefits = _persona_benefit_caps(indexes)

    # Build set of all doc paths in the index for validation
    docs_by_path = {}
    for doc in docs_index.get("documents", []):
        docs_by_path[doc.get("path", "")] = doc

    results = []
    for pid in sorted(personas.keys()):
        if persona_filter and pid != persona_filter:
            continue

        persona = personas[pid]
        cap_ids = persona_caps.get(pid, set())
        benefit_info = persona_benefits.get(pid, [])

        # Count capabilities and benefits
        cap_count = len(cap_ids)
        benefit_count = len(benefit_info)

        # --- Signal 1: Capability Evidence Chain ---
        signal1_docs = {}  # path -> {score, via, via_capabilities}
        for cap_id in cap_ids:
            for doc_path in cap_evidence.get(cap_id, []):
                if doc_path in docs_by_path:
                    if doc_path not in signal1_docs or signal1_docs[doc_path]["score"] < 0.9:
                        signal1_docs[doc_path] = {
                            "score": 0.9,
                            "via": f"{cap_id} (evidence chain)",
                            "via_capabilities": [cap_id],
                        }
                    else:
                        signal1_docs[doc_path]["via_capabilities"].append(cap_id)

        # --- Signal 2: Benefit-to-Capability Chain ---
        signal2_docs = {}
        for bi in benefit_info:
            for cap_id in bi["delivered_by"]:
                for doc_path in cap_evidence.get(cap_id, []):
                    if doc_path in docs_by_path:
                        if doc_path not in signal2_docs or signal2_docs[doc_path]["score"] < 0.7:
                            signal2_docs[doc_path] = {
                                "score": 0.7,
                                "via": f"{bi['benefit_id']} benefit (benefit chain)",
                                "via_capabilities": [cap_id],
                            }
                        else:
                            if cap_id not in signal2_docs[doc_path]["via_capabilities"]:
                                signal2_docs[doc_path]["via_capabilities"].append(cap_id)

        # --- Signal 3: Document Type Affinity ---
        affinity_types = _PERSONA_TYPE_AFFINITY.get(pid, set())
        signal3_docs = {}
        for doc_path, doc in docs_by_path.items():
            if doc.get("type") in affinity_types:
                signal3_docs[doc_path] = {
                    "score": 0.4,
                    "via": f"{doc['type']} type affinity",
                    "via_capabilities": [],
                }

        # --- Merge signals (max score wins) ---
        all_matched = {}
        for signals in [signal1_docs, signal2_docs, signal3_docs]:
            for doc_path, info in signals.items():
                if doc_path not in all_matched or info["score"] > all_matched[doc_path]["score"]:
                    all_matched[doc_path] = info
                elif info["score"] == all_matched[doc_path]["score"]:
                    # Merge via_capabilities
                    for c in info["via_capabilities"]:
                        if c not in all_matched[doc_path]["via_capabilities"]:
                            all_matched[doc_path]["via_capabilities"].append(c)

        # Filter by min relevance
        matched = {p: i for p, i in all_matched.items() if i["score"] >= min_relevance}

        # --- Classify onboarding vs operations ---
        onboarding_docs = []
        operations_docs = []
        for doc_path, info in sorted(matched.items(), key=lambda x: -x[1]["score"]):
            doc = docs_by_path[doc_path]
            entry = {
                "path": doc_path,
                "title": doc.get("title", ""),
                "type": doc.get("type", "unknown"),
                "relevance": info["score"],
                "via": info["via"],
                "via_capabilities": info["via_capabilities"],
            }
            category = _classify_doc_category(doc)
            entry["category"] = category
            if category == "onboarding":
                onboarding_docs.append(entry)
            else:
                operations_docs.append(entry)

        # --- Gap detection ---
        gaps = _detect_persona_gaps(pid, persona, onboarding_docs,
                                    operations_docs, benefit_info)

        results.append({
            "persona_id": pid,
            "name": persona["name"],
            "description": persona.get("description", ""),
            "pain_point": persona.get("pain_point", ""),
            "goals": persona.get("goals", []),
            "primary_value": persona.get("primary_value", ""),
            "capability_count": cap_count,
            "benefit_count": benefit_count,
            "onboarding": onboarding_docs,
            "operations": operations_docs,
            "total_docs": len(onboarding_docs) + len(operations_docs),
            "gaps": gaps,
        })

    # Summary
    total_personas = len(results)
    total_gaps = sum(len(r["gaps"]) for r in results)
    high_gaps = sum(1 for r in results for g in r["gaps"] if g["priority"] == "high")

    return {
        "audit_date": date.today().isoformat(),
        "min_relevance_threshold": min_relevance,
        "summary": {
            "personas_analyzed": total_personas,
            "total_documentation_gaps": total_gaps,
            "high_priority_gaps": high_gaps,
            "avg_docs_per_persona": round(
                sum(r["total_docs"] for r in results) / max(total_personas, 1), 1
            ),
        },
        "personas": results,
    }


# ---------------------------------------------------------------------------
# CLI: docs group
# ---------------------------------------------------------------------------

@click.group()
def docs():
    """Documentation index — generate and query the docs catalog."""
    pass


@docs.command()
@click.option("--output", "-o", default=DEFAULT_OUTPUT, help="Output file path")
@click.option("--dry-run", is_flag=True, help="Print to stdout instead of writing file")
@click.option("--no-git", is_flag=True, help="Skip git freshness lookup (faster)")
@click.option("--format", "fmt", type=click.Choice(["yaml", "json"]), default="yaml", help="Output format")
def index(output, dry_run, no_git, fmt):
    """Generate the documentation index from capability index + directory scan.

    Scans capability index YAMLs for type: doc evidence entries, walks docs/
    and plans/ directories, classifies documents by type, extracts titles and
    cross-references, and produces contextcore.docs.yaml.

    \b
    Pipeline context:
      This is a meta-capability — it indexes the documentation that describes
      the pipeline, not a pipeline step itself. Run periodically or after
      adding/removing documentation files.

    \b
    Examples:
      contextcore docs index                     # Generate with git freshness
      contextcore docs index --no-git            # Fast mode, skip git dates
      contextcore docs index --dry-run           # Preview without writing
      contextcore docs index --format json -o -  # JSON to stdout
    """
    repo_root = _find_repo_root()

    click.echo(f"Scanning capability index and documentation directories...")
    data = generate_docs_index(repo_root, skip_git=no_git)

    summary = data["summary"]

    # Serialize
    if fmt == "json":
        output_text = json.dumps(data, indent=2, default=str)
    else:
        output_text = yaml.dump(data, default_flow_style=False, sort_keys=False,
                                allow_unicode=True, width=120)

    if dry_run or output == "-":
        click.echo(output_text)
    else:
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = repo_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"# Auto-generated by contextcore docs index\n"
            f"# Do not edit manually — re-run the command to update.\n"
            f"# Last generated: {date.today().isoformat()}\n\n"
        )
        with open(output_path, "w") as f:
            if fmt == "yaml":
                f.write(header)
            f.write(output_text)
        click.echo(f"\nDocumentation index generated: {output}")

    click.echo(f"  {summary['total_documents']} documents indexed "
               f"({summary['referenced_by_capabilities']} referenced, "
               f"{summary['orphaned']} orphaned)")
    click.echo(f"  {summary['cross_references']} cross-references across "
               f"{summary['documents_with_cross_references']} documents")

    # Type breakdown
    type_parts = [f"{t} ({c})" for t, c in sorted(summary["by_type"].items(), key=lambda x: -x[1])]
    click.echo(f"  Types: {', '.join(type_parts)}")

    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Review orphaned documents for capability linkage opportunities")
    click.echo("  2. Run: contextcore docs show --orphaned       (list unreferenced docs)")
    click.echo("  3. Run: contextcore docs show --type requirements  (list by type)")


@docs.command()
@click.option("--index-path", default=DEFAULT_OUTPUT, help="Path to docs index YAML")
@click.option("--type", "doc_type", type=click.Choice(list(DOCUMENT_TYPES.keys())), help="Filter by document type")
@click.option("--orphaned", is_flag=True, help="Show only unreferenced documents")
@click.option("--referenced", is_flag=True, help="Show only referenced documents")
@click.option("--capability", help="Show docs governing a specific capability ID")
@click.option("--refs-for", "refs_for", help="Show cross-reference graph for a document path")
@click.option("--stale-days", type=int, help="Show documents not modified in N days")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "yaml"]), default="text", help="Output format")
def show(index_path, doc_type, orphaned, referenced, capability, refs_for, stale_days, fmt):
    """Query the documentation index with filters.

    Without filters, shows a summary. With filters, shows matching documents.

    \b
    Examples:
      contextcore docs show                          # Summary
      contextcore docs show --type requirements      # All requirements docs
      contextcore docs show --orphaned               # Unreferenced docs
      contextcore docs show --capability contextcore.pipeline.check_pipeline
      contextcore docs show --refs-for docs/MANIFEST_EXPORT_REQUIREMENTS.md
      contextcore docs show --stale-days 30          # Stale docs
      contextcore docs show --type plan --format json
    """
    repo_root = _find_repo_root()
    idx_path = Path(index_path)
    if not idx_path.is_absolute():
        idx_path = repo_root / idx_path

    if not idx_path.exists():
        raise click.ClickException(
            f"Documentation index not found at {index_path}\n"
            f"Run: contextcore docs index"
        )

    with open(idx_path) as f:
        data = yaml.safe_load(f)

    documents = data.get("documents", [])

    # Apply filters
    filtered = documents
    filter_desc = []

    if doc_type:
        filtered = [d for d in filtered if d.get("type") == doc_type]
        filter_desc.append(f"type={doc_type}")

    if orphaned:
        filtered = [d for d in filtered if not d.get("referenced")]
        filter_desc.append("orphaned")

    if referenced:
        filtered = [d for d in filtered if d.get("referenced")]
        filter_desc.append("referenced")

    if capability:
        filtered = [
            d for d in filtered
            if any(g["capability_id"] == capability for g in d.get("governs_capabilities", []))
        ]
        filter_desc.append(f"capability={capability}")

    if stale_days is not None:
        cutoff = (datetime.now() - timedelta(days=stale_days)).strftime("%Y-%m-%d")
        filtered = [
            d for d in filtered
            if d.get("last_modified", "9999-99-99") < cutoff
        ]
        filter_desc.append(f"stale>{stale_days}d")

    # Special mode: cross-reference graph for a specific doc
    if refs_for:
        _show_refs_graph(refs_for, documents, fmt)
        return

    # No filters: show summary
    if not filter_desc:
        _show_summary(data, fmt)
        return

    # Filtered results
    if fmt == "json":
        click.echo(json.dumps(filtered, indent=2, default=str))
    elif fmt == "yaml":
        click.echo(yaml.dump(filtered, default_flow_style=False, sort_keys=False))
    else:
        _show_table(filtered, filter_desc)


@docs.command()
@click.option("--index-path", default=DEFAULT_OUTPUT, help="Path to docs index YAML")
@click.option("--min-importance", type=float, default=0.3,
              help="Only report gaps above this importance threshold (0.0-1.0)")
@click.option("--type", "gap_type",
              type=click.Choice(["requirements", "design", "operational", "adr", "reference"]),
              help="Filter to show only gaps of a specific document type")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "yaml"]), default="text",
              help="Output format")
@click.option("--verbose", is_flag=True, help="Show per-capability detail instead of cluster summaries")
def audit(index_path, min_importance, gap_type, fmt, verbose):
    """Audit documentation gaps by reverse-engineering the capability index.

    Computes a per-capability importance score from maturity, complexity,
    cross-cutting impact, and benefit linkage, then applies rules to determine
    which document types should exist. Reports gaps as namespace clusters
    sorted by priority.

    \b
    Importance score (4 dimensions, 0-1):
      30%  Maturity-Confidence composite (stable > beta > draft)
      25%  Structural complexity (inputs, anti-patterns, risk flags)
      25%  Cross-cutting impact (dependency fanout, persona breadth)
      20%  Benefit linkage (priority, delivery status, persona count)

    \b
    Expected document rules:
      R1  requirements: stable + CLI command or complex inputs
      R2  design: stable/beta + high complexity
      R3  operational: has CLI triggers
      R4  adr: has anti_patterns or risk_flags
      R5  requirements: validate category + stable
      R6  design: integration category
      R7  requirements: delivers gap benefit with FRs
      R8  reference: stable + confidence >= 0.9

    \b
    Examples:
      contextcore docs audit                          # Full audit
      contextcore docs audit --min-importance 0.5     # High-importance only
      contextcore docs audit --type requirements      # Requirements gaps only
      contextcore docs audit --verbose                # Per-capability detail
      contextcore docs audit --format json            # Machine-readable
    """
    repo_root = _find_repo_root()
    idx_path = Path(index_path)
    if not idx_path.is_absolute():
        idx_path = repo_root / idx_path

    if not idx_path.exists():
        raise click.ClickException(
            f"Documentation index not found at {index_path}\n"
            f"Run: contextcore docs index"
        )

    with open(idx_path) as f:
        docs_index = yaml.safe_load(f)

    click.echo("Analyzing capability indexes and documentation coverage...")
    results = run_audit(repo_root, docs_index, min_importance=min_importance)

    # Filter by gap type if specified
    if gap_type:
        results["clusters"] = [
            c for c in results["clusters"] if c["missing_type"] == gap_type
        ]
        results["per_capability_gaps"] = [
            g for g in results["per_capability_gaps"]
            if gap_type in g["missing_doc_types"]
        ]

    if fmt == "json":
        click.echo(json.dumps(results, indent=2, default=str))
    elif fmt == "yaml":
        click.echo(yaml.dump(results, default_flow_style=False, sort_keys=False))
    else:
        _show_audit_text(results, verbose=verbose, gap_type=gap_type)


@docs.command()
@click.option("--index-path", default=DEFAULT_OUTPUT, help="Path to docs index YAML")
@click.option("--persona", "persona_filter",
              help="Show results for a single persona (e.g., operator, developer)")
@click.option("--category",
              type=click.Choice(["onboarding", "operations"]),
              help="Show only onboarding or operations docs")
@click.option("--gaps-only", is_flag=True,
              help="Only show documentation gaps, not the full catalog")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "yaml"]),
              default="text", help="Output format")
@click.option("--min-relevance", type=float, default=0.4,
              help="Minimum document-persona relevance threshold (0.0-1.0)")
def curate(index_path, persona_filter, category, gaps_only, fmt, min_relevance):
    """Curate persona-specific documentation catalogs.

    Traces persona-to-capability-to-document chains via three signals:

    \b
    Signal 1 — Capability Evidence Chain (score 0.9):
      persona -> capabilities -> evidence[type=doc]

    Signal 2 — Benefit-to-Capability Chain (score 0.7):
      persona -> benefits -> delivered_by capabilities -> evidence[type=doc]

    Signal 3 — Document Type Affinity (score 0.4):
      Match documents by type affinity for the persona role

    Each document is classified as onboarding or operations and gaps are
    detected based on persona profile and benefit importance.

    \b
    Examples:
      contextcore docs curate                          # Full persona catalog
      contextcore docs curate --persona operator       # Single persona
      contextcore docs curate --category onboarding    # Onboarding docs only
      contextcore docs curate --gaps-only              # Only show gaps
      contextcore docs curate --format json            # Machine-readable
      contextcore docs curate --min-relevance 0.7      # High-relevance only
    """
    repo_root = _find_repo_root()
    idx_path = Path(index_path)
    if not idx_path.is_absolute():
        idx_path = repo_root / idx_path

    if not idx_path.exists():
        raise click.ClickException(
            f"Documentation index not found at {index_path}\n"
            f"Run: contextcore docs index"
        )

    with open(idx_path) as f:
        docs_index = yaml.safe_load(f)

    click.echo("Curating persona-to-documentation catalog...")
    results = run_curate(repo_root, docs_index,
                           min_relevance=min_relevance,
                           persona_filter=persona_filter)

    if fmt == "json":
        click.echo(json.dumps(results, indent=2, default=str))
    elif fmt == "yaml":
        click.echo(yaml.dump(results, default_flow_style=False, sort_keys=False))
    else:
        _show_curate_text(results, category=category, gaps_only=gaps_only)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Find the repository root by walking up from CWD."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".contextcore.yaml").exists() or (parent / ".git").exists():
            return parent
    return cwd


def _show_audit_text(results: dict, verbose: bool = False, gap_type: Optional[str] = None):
    """Render audit results as formatted text."""
    summary = results["summary"]
    clusters = results["clusters"]
    per_cap = results["per_capability_gaps"]

    filter_str = f" (type={gap_type})" if gap_type else ""
    click.echo()
    click.echo(f"Documentation Audit — {results['audit_date']}{filter_str}")
    click.echo("═" * 60)
    click.echo(f"  Capabilities analyzed:     {summary['capabilities_analyzed']}")
    click.echo(f"  With documentation gaps:   {summary['with_documentation_gaps']}")
    click.echo(f"  Cluster gaps identified:   {summary['cluster_gaps_identified']}")
    pb = summary["priority_breakdown"]
    click.echo(f"  Gap priority:              {pb['high']} high, {pb['medium']} medium, {pb['low']} low")
    click.echo(f"  Importance threshold:       >= {results['min_importance_threshold']}")

    if summary.get("missing_doc_types"):
        click.echo()
        click.echo("Missing doc types across all gaps:")
        for dt, count in summary["missing_doc_types"].items():
            click.echo(f"  {dt:<15} {count:>3} capabilities")

    if clusters:
        click.echo()
        click.echo("─" * 60)

        for cluster in clusters:
            priority_marker = {
                "high": "▲", "medium": "●", "low": "○"
            }.get(cluster["priority"], "?")

            click.echo()
            click.echo(
                f"{priority_marker} CLUSTER GAP: {cluster['cluster']} "
                f"({cluster['capability_count']} capabilities, "
                f"avg importance: {cluster['avg_importance']:.2f})"
            )
            click.echo(f"    Missing: {cluster['missing_type']}")
            click.echo(
                f"    Highest: {cluster['highest_capability']} "
                f"(importance: {cluster['max_importance']:.2f}, "
                f"maturity: {cluster['highest_maturity']})"
            )
            click.echo(f"    Rationale: {cluster['rationale']}")
            click.echo(f"    Suggested: {cluster['suggested_file']}")

            if verbose:
                click.echo(f"    Capabilities:")
                # Find matching per-cap gaps
                for cap_id in cluster["capabilities"]:
                    matching = [g for g in per_cap if g["capability_id"] == cap_id]
                    if matching:
                        g = matching[0]
                        click.echo(
                            f"      - {g['capability_id']}  "
                            f"importance={g['importance']:.3f}  "
                            f"maturity={g['maturity']}  "
                            f"category={g['category']}"
                        )
                        click.echo(
                            f"        expected: {', '.join(g['expected_doc_types'])}  "
                            f"actual: {', '.join(g['actual_doc_types']) or '(none)'}"
                        )
    else:
        click.echo()
        click.echo("  No documentation gaps found above the importance threshold.")

    click.echo()
    click.echo("Next steps:")
    if clusters:
        top = clusters[0]
        click.echo(f"  1. Create {top['suggested_file']} for highest-priority cluster")
        click.echo(f"  2. Run: contextcore docs audit --verbose   (see per-capability detail)")
    click.echo(f"  3. Run: contextcore docs audit --format json  (export for automation)")


def _show_summary(data: dict, fmt: str):
    """Show index summary."""
    summary = data["summary"]

    if fmt in ("json", "yaml"):
        output = {
            "summary": summary,
            "document_types": data.get("document_types", {}),
            "external_evidence_refs": data.get("external_evidence_refs", []),
        }
        if fmt == "json":
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo(yaml.dump(output, default_flow_style=False, sort_keys=False))
        return

    click.echo(f"Documentation Index (generated: {data.get('generated_at', 'unknown')})")
    click.echo(f"{'─' * 60}")
    click.echo(f"  Total documents:    {summary['total_documents']}")
    click.echo(f"  Referenced:         {summary['referenced_by_capabilities']}")
    click.echo(f"  Orphaned:           {summary['orphaned']}")
    click.echo(f"  Cross-references:   {summary.get('cross_references', 'N/A')}")
    click.echo(f"  External refs:      {summary.get('external_evidence_refs', 0)}")
    click.echo()
    click.echo("By type:")
    for doc_type, count in sorted(summary.get("by_type", {}).items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 40)
        click.echo(f"  {doc_type:<15} {count:>3}  {bar}")
    click.echo()
    click.echo("Filters available:")
    click.echo("  --type TYPE          Filter by document type")
    click.echo("  --orphaned           Show unreferenced documents")
    click.echo("  --referenced         Show capability-linked documents")
    click.echo("  --capability ID      Show docs governing a capability")
    click.echo("  --refs-for PATH      Show cross-reference graph")
    click.echo("  --stale-days N       Show docs not modified in N days")


def _show_table(docs: list, filter_desc: list):
    """Show filtered documents as a table."""
    desc = ", ".join(filter_desc)
    click.echo(f"Documents matching: {desc}  ({len(docs)} results)")
    click.echo(f"{'─' * 80}")

    if not docs:
        click.echo("  (no matching documents)")
        return

    for d in docs:
        title = d.get("title", "")
        title_str = f"  {title}" if title else ""
        modified = d.get("last_modified", "")
        modified_str = f"  [{modified}]" if modified else ""
        refs_count = len(d.get("references", []))
        refs_str = f"  ({refs_count} refs)" if refs_count else ""

        click.echo(f"  {d['path']}")
        click.echo(f"    type={d['type']}  maturity={d['maturity']}"
                    f"  lines={d.get('line_count', '?')}{modified_str}{refs_str}")
        if title_str:
            click.echo(f"   {title_str}")
        if d.get("governs_capabilities"):
            cap_ids = [g["capability_id"] for g in d["governs_capabilities"]]
            click.echo(f"    governs: {', '.join(cap_ids)}")
        click.echo()


def _show_refs_graph(doc_path: str, all_docs: list, fmt: str):
    """Show inbound and outbound cross-references for a document."""
    # Find the target document
    target = None
    for d in all_docs:
        if d["path"] == doc_path:
            target = d
            break

    if not target:
        raise click.ClickException(f"Document not found in index: {doc_path}")

    # Outbound: docs this document references
    outbound = target.get("references", [])

    # Inbound: docs that reference this document
    inbound = []
    for d in all_docs:
        if doc_path in d.get("references", []):
            inbound.append(d["path"])

    result = {
        "document": doc_path,
        "title": target.get("title", ""),
        "type": target.get("type", "unknown"),
        "outbound_references": outbound,
        "inbound_references": inbound,
        "governs_capabilities": target.get("governs_capabilities", []),
    }

    if fmt == "json":
        click.echo(json.dumps(result, indent=2))
    elif fmt == "yaml":
        click.echo(yaml.dump(result, default_flow_style=False, sort_keys=False))
    else:
        click.echo(f"Cross-references for: {doc_path}")
        if target.get("title"):
            click.echo(f"  Title: {target['title']}")
        click.echo(f"  Type: {target['type']}  Maturity: {target['maturity']}")
        click.echo()

        click.echo(f"Outbound ({len(outbound)} — this doc references):")
        if outbound:
            for ref in outbound:
                click.echo(f"  → {ref}")
        else:
            click.echo("  (none)")

        click.echo()
        click.echo(f"Inbound ({len(inbound)} — referenced by):")
        if inbound:
            for ref in inbound:
                click.echo(f"  ← {ref}")
        else:
            click.echo("  (none)")

        if target.get("governs_capabilities"):
            click.echo()
            click.echo("Governs capabilities:")
            for g in target["governs_capabilities"]:
                click.echo(f"  ◆ {g['capability_id']} — {g['role']}")


def _show_curate_text(results: dict, category: Optional[str] = None,
                        gaps_only: bool = False):
    """Render curated persona documentation catalog as formatted text."""
    summary = results["summary"]

    click.echo()
    click.echo(f"Persona Documentation Catalog — {results['audit_date']}")
    click.echo("═" * 55)
    click.echo(f"  Personas analyzed:       {summary['personas_analyzed']}")
    click.echo(f"  Total doc gaps:          {summary['total_documentation_gaps']}")
    click.echo(f"  High-priority gaps:      {summary['high_priority_gaps']}")
    click.echo(f"  Avg docs per persona:    {summary['avg_docs_per_persona']}")
    click.echo(f"  Relevance threshold:     >= {results['min_relevance_threshold']}")
    click.echo()

    for p in results["personas"]:
        # Header
        name_upper = p["name"].upper()
        click.echo(f"{name_upper} ({p['capability_count']} capabilities, "
                    f"{p['benefit_count']} benefits)")
        if p.get("pain_point"):
            click.echo(f'  Pain point: "{p["pain_point"]}"')
        if p.get("goals"):
            click.echo(f"  Goals: {', '.join(p['goals'])}")
        click.echo()

        # Onboarding section
        if not gaps_only and (category is None or category == "onboarding"):
            onb = p["onboarding"]
            click.echo(f"  Onboarding ({len(onb)} docs):")
            if onb:
                for doc in onb:
                    click.echo(f"    {doc['relevance']:.2f}  {doc['path']}")
                    click.echo(f"          via: {doc['via']}")
            else:
                click.echo("    (none)")
            click.echo()

        # Operations section
        if not gaps_only and (category is None or category == "operations"):
            ops = p["operations"]
            click.echo(f"  Operations ({len(ops)} docs):")
            if ops:
                for doc in ops:
                    click.echo(f"    {doc['relevance']:.2f}  {doc['path']}")
                    click.echo(f"          via: {doc['via']}")
            else:
                click.echo("    (none)")
            click.echo()

        # Gaps section
        if p["gaps"]:
            click.echo(f"  Gaps ({len(p['gaps'])}):")
            for g in p["gaps"]:
                prio = g["priority"].upper()
                click.echo(f"    [{prio}] {g['gap']}")
                if g.get("suggested"):
                    click.echo(f"           Suggested: {g['suggested']}")
            click.echo()
        elif not gaps_only:
            click.echo("  Gaps: (none)")
            click.echo()

        click.echo("─" * 55)
        click.echo()
