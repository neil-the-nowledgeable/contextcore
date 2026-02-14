#!/usr/bin/env python3
"""Generate contextcore.docs.yaml from capability index evidence + docs/ directory scan.

Iteration 1: Basic extraction and skeleton generation.
Iteration 2: Document type classification, title extraction, content heuristics.
Iteration 3: Cross-document relationships, git freshness, orphan analysis.
- Scans capability index YAMLs for type: doc evidence entries
- Scans docs/ directory for all .md files
- Classifies documents by type (requirements, design, operational, adr, plan, analysis, reference)
- Extracts title from first H1 heading
- Detects maturity signals from content
- Discovers cross-document references (doc-to-doc links)
- Adds git last-modified timestamps for freshness tracking
- Produces a docs index YAML with document paths and governing capabilities

Usage:
    python3 scripts/generate_docs_index.py
    python3 scripts/generate_docs_index.py --output docs/capability-index/contextcore.docs.yaml
    python3 scripts/generate_docs_index.py --dry-run
    python3 scripts/generate_docs_index.py --no-git   # skip git freshness (faster)
"""

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

CAPABILITY_INDEX_DIR = REPO_ROOT / "docs" / "capability-index"

CAPABILITY_INDEX_FILES = [
    "contextcore.agent.yaml",
    "contextcore.user.yaml",
    "contextcore.benefits.yaml",
    "contextcore.pain_points.yaml",
]

# Directories to scan for documentation files
DOC_SCAN_DIRS = [
    "docs",
    "plans",
]

# File extensions to consider as documentation
DOC_EXTENSIONS = {".md", ".yaml", ".yml"}

# Paths to exclude from scanning (relative to repo root)
EXCLUDE_PATTERNS = {
    "docs/capability-index",  # The index itself, not indexed docs
    "docs/plans/.startd8",    # Build artifacts
}


def should_exclude(rel_path: str) -> bool:
    """Check if a path should be excluded from doc scanning."""
    for pattern in EXCLUDE_PATTERNS:
        if rel_path.startswith(pattern):
            return True
    return False


# ---------------------------------------------------------------------------
# Step 1: Extract doc evidence from capability index YAMLs
# ---------------------------------------------------------------------------

def extract_doc_evidence(index_dir: Path) -> dict:
    """Extract all type: doc evidence entries from capability index files.

    Returns:
        dict mapping doc_ref -> list of {capability_id, description, source_file}
    """
    doc_refs = defaultdict(list)

    for filename in CAPABILITY_INDEX_FILES:
        filepath = index_dir / filename
        if not filepath.exists():
            continue

        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"  WARNING: Skipping {filename} — YAML parse error: {e}")
            continue

        if not data:
            continue

        # Extract from capabilities array
        capabilities = data.get("capabilities", [])
        if not capabilities:
            # benefits.yaml uses "benefits" key
            capabilities = data.get("benefits", [])

        for cap in capabilities:
            cap_id = cap.get("capability_id") or cap.get("benefit_id", "unknown")

            # Check capability-level evidence
            for ev in cap.get("evidence", []):
                if ev.get("type") == "doc":
                    doc_refs[ev["ref"]].append({
                        "capability_id": cap_id,
                        "description": ev.get("description", ""),
                        "source_file": filename,
                    })

        # Check global evidence
        for ev in data.get("evidence", []):
            if ev.get("type") == "doc":
                doc_refs[ev["ref"]].append({
                    "capability_id": "_global",
                    "description": ev.get("description", ""),
                    "source_file": filename,
                })

    return dict(doc_refs)


# ---------------------------------------------------------------------------
# Step 2: Scan docs/ directory for all documentation files
# ---------------------------------------------------------------------------

def scan_doc_directories(repo_root: Path) -> list:
    """Scan documentation directories for all doc files.

    Returns:
        list of relative paths (strings) to doc files
    """
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
                if should_exclude(rel):
                    continue

                doc_files.append(rel)

    return sorted(doc_files)


# ---------------------------------------------------------------------------
# Step 3: Classify documents by type and extract metadata
# ---------------------------------------------------------------------------

# Document type taxonomy
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
    "unknown": "Unclassified document",
}

# Filename-based classification rules (checked in order, first match wins)
# NOTE: Order matters — more specific patterns must come before broader ones.
FILENAME_TYPE_RULES = [
    # ADRs (very specific path)
    (re.compile(r"^docs/adr/"), "adr"),
    # Requirements (filename must end with or contain "requirements" as distinct word)
    (re.compile(r"_requirements\b|REQUIREMENTS\b", re.I), "requirements"),
    # Plans (directory-based and filename-based)
    (re.compile(r"^plans/"), "plan"),
    (re.compile(r"^docs/plans/"), "plan"),
    (re.compile(r"_plan\b|PLAN\b|checklist|execution_|kickoff|agenda", re.I), "plan"),
    # Operational / troubleshooting
    (re.compile(r"troubleshoot|runbook|installation\b|quickstart|setup|known.?issues|how.?to|guide\b|onboarding", re.I), "operational"),
    # Analysis / audit
    (re.compile(r"analysis|audit\b|gap_|comparison|_issues\b|improvement|feedback|data.?issues", re.I), "analysis"),
    # Design
    (re.compile(r"design\b|schema\b|contract\b|architecture|blueprint|_pattern\b", re.I), "design"),
    # Session / handoff
    (re.compile(r"session\b|_log\b|retrospective|handoff\b|notes\b", re.I), "session"),
    # Governance
    (re.compile(r"license|governance|policy\b", re.I), "governance"),
    # Reference
    (re.compile(r"convention|reference|migration|naming\b|_spec\b|semantic|value.?prop|alignment\b|standard", re.I), "reference"),
    # Documentation / specification (broad catch for dashboard specs, etc.)
    (re.compile(r"^docs/dashboards/", re.I), "design"),
    (re.compile(r"harbor.?tour", re.I), "operational"),
    # Submission / proposal
    (re.compile(r"submission|proposal|issue", re.I), "reference"),
    # Design / patterns (broad catch)
    (re.compile(r"pattern|prevention|truncation|workflow\b", re.I), "design"),
]

# Content-based classification signals (searched if filename rules don't match)
CONTENT_TYPE_SIGNALS = [
    # Requirements patterns
    (re.compile(r"functional.?requirement|FR-\d|acceptance.?criteria|shall\b|must\b.*requirement", re.I), "requirements"),
    # Plan patterns
    (re.compile(r"phase\s+\d|milestone|timeline|estimated.?completion|deliverable", re.I), "plan"),
    # Design patterns
    (re.compile(r"architecture|data.?model|schema|sequence.?diagram|component.?diagram", re.I), "design"),
    # Operational patterns
    (re.compile(r"step\s+\d.*:|prerequisit|install|configure|troubleshoot", re.I), "operational"),
    # Analysis patterns
    (re.compile(r"gap.?analysis|findings|recommendation|observation|current.?state", re.I), "analysis"),
]

# Maturity signals from content
MATURITY_SIGNALS = {
    "draft": re.compile(r"\bDRAFT\b|\[DRAFT\]|\bWIP\b|work.?in.?progress", re.I),
    "stable": re.compile(r"living.?guidance|intentionally.?living|production.?ready", re.I),
    "deprecated": re.compile(r"\bDEPRECATED\b|\[DEPRECATED\]|superseded.?by|replaced.?by", re.I),
}


def classify_doc_type(rel_path: str, content: str) -> str:
    """Classify a document by type using filename and content heuristics."""
    # Try filename rules first
    for pattern, doc_type in FILENAME_TYPE_RULES:
        if pattern.search(rel_path):
            return doc_type

    # Fall back to content signals
    for pattern, doc_type in CONTENT_TYPE_SIGNALS:
        if pattern.search(content[:3000]):  # Only scan first 3000 chars
            return doc_type

    return "unknown"


def extract_title(content: str) -> str:
    """Extract the first H1 heading from markdown content."""
    for line in content.split("\n")[:20]:  # Only check first 20 lines
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def detect_maturity(content: str) -> str:
    """Detect document maturity from content signals."""
    header = content[:2000]
    if MATURITY_SIGNALS["deprecated"].search(header):
        return "deprecated"
    if MATURITY_SIGNALS["draft"].search(header):
        return "draft"
    if MATURITY_SIGNALS["stable"].search(header):
        return "stable"
    return "active"  # Default: exists and not flagged


def extract_scope_keywords(content: str) -> list:
    """Extract CLI commands and key concepts referenced in the document."""
    keywords = set()

    # Find CLI commands: contextcore <subcommand> <subcommand>
    for m in re.finditer(r"contextcore\s+([\w-]+(?:\s+[\w-]+)?)", content):
        keywords.add(f"contextcore {m.group(1).strip()}")

    # Find pipeline step references
    for m in re.finditer(r"(?:step|gate)\s+(\d+)", content, re.I):
        keywords.add(f"pipeline step {m.group(1)}")

    return sorted(keywords)[:10]  # Cap at 10 most relevant


def count_lines(content: str) -> int:
    """Count non-empty lines in content."""
    return sum(1 for line in content.split("\n") if line.strip())


# Patterns for detecting cross-document references in markdown content
_DOC_REF_PATTERNS = [
    # Markdown links: [text](path/to/doc.md)
    re.compile(r"\]\(([^)]+\.(?:md|yaml|yml))\)"),
    # Backtick references: `docs/SOME_FILE.md`
    re.compile(r"`((?:docs|plans|examples)/[^`]+\.(?:md|yaml|yml))`"),
    # Plain path references: docs/SOME_FILE.md (preceded by whitespace or start)
    re.compile(r"(?:^|\s)((?:docs|plans|examples)/[\w/.-]+\.(?:md|yaml|yml))"),
]


def extract_cross_references(content: str, own_path: str) -> list:
    """Extract references to other documentation files from content."""
    refs = set()
    for pattern in _DOC_REF_PATTERNS:
        for match in pattern.finditer(content):
            ref = match.group(1).strip()
            # Normalize: strip leading ./ or ../
            ref = re.sub(r"^(\.\./)*", "", ref)
            ref = re.sub(r"^\./", "", ref)
            # Skip self-references and anchors-only
            if ref == own_path or ref.startswith("#"):
                continue
            # Skip URLs
            if ref.startswith(("http://", "https://")):
                continue
            refs.add(ref)
    return sorted(refs)


def get_git_last_modified(rel_paths: list, repo_root: Path) -> dict:
    """Get git last-modified dates for a batch of files.

    Returns dict mapping rel_path -> ISO date string (or None if not in git).
    """
    result = {}
    try:
        # Batch: get all tracked files with their last commit date
        proc = subprocess.run(
            ["git", "log", "--format=%aI", "--name-only", "--diff-filter=ACMR",
             "-1", "--"] + rel_paths,
            capture_output=True, text=True, cwd=str(repo_root), timeout=30,
        )
        if proc.returncode != 0:
            return {}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {}

    # Fallback: per-file approach (git log batch output is hard to parse for many files)
    for rel_path in rel_paths:
        try:
            proc = subprocess.run(
                ["git", "log", "-1", "--format=%aI", "--", rel_path],
                capture_output=True, text=True, cwd=str(repo_root), timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                # Extract just the date portion (YYYY-MM-DD)
                iso_date = proc.stdout.strip()[:10]
                result[rel_path] = iso_date
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return result


def analyze_document(rel_path: str, repo_root: Path) -> dict:
    """Analyze a document file and extract metadata."""
    full_path = repo_root / rel_path
    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return {
            "title": "",
            "doc_type": "unknown",
            "maturity": "unknown",
            "line_count": 0,
            "scope_keywords": [],
        }

    # YAML files get simpler treatment
    if rel_path.endswith((".yaml", ".yml")):
        return {
            "title": "",
            "doc_type": classify_doc_type(rel_path, content),
            "maturity": "active",
            "line_count": count_lines(content),
            "scope_keywords": [],
        }

    return {
        "title": extract_title(content),
        "doc_type": classify_doc_type(rel_path, content),
        "maturity": detect_maturity(content),
        "line_count": count_lines(content),
        "scope_keywords": extract_scope_keywords(content),
        "references": extract_cross_references(content, rel_path),
    }


# ---------------------------------------------------------------------------
# Step 4: Build the docs index
# ---------------------------------------------------------------------------

def make_doc_id(rel_path: str) -> str:
    """Generate a doc_id from a relative file path.

    Examples:
        docs/MANIFEST_EXPORT_REQUIREMENTS.md -> contextcore.docs.manifest_export_requirements
        docs/adr/001-tasks-as-spans.md -> contextcore.docs.adr.001_tasks_as_spans
        plans/PHASE4_UNIFIED_ALIGNMENT.md -> contextcore.docs.plans.phase4_unified_alignment
    """
    p = Path(rel_path)
    stem = p.stem.lower().replace("-", "_")

    # Build path segments (skip the first directory if it's "docs")
    parts = list(p.parent.parts)
    if parts and parts[0] == "docs":
        parts = parts[1:]

    if parts:
        subdomain = ".".join(p.lower().replace("-", "_") for p in parts)
        return f"contextcore.docs.{subdomain}.{stem}"
    else:
        return f"contextcore.docs.{stem}"


def build_docs_index(
    doc_evidence: dict,
    all_doc_files: list,
    repo_root: Path,
    skip_git: bool = False,
) -> dict:
    """Build the documentation index structure.

    Args:
        doc_evidence: mapping from doc ref -> list of capability references
        all_doc_files: list of all doc file paths found on disk
        repo_root: path to repository root
        skip_git: if True, skip git freshness lookup (faster)

    Returns:
        dict suitable for YAML serialization
    """
    # Git freshness lookup (batch)
    git_dates = {}
    if not skip_git:
        git_dates = get_git_last_modified(all_doc_files, repo_root)

    documents = []
    referenced_count = 0
    orphan_count = 0
    type_counts = defaultdict(int)
    all_paths_set = set(all_doc_files)

    for rel_path in all_doc_files:
        doc_id = make_doc_id(rel_path)

        # Analyze document content
        metadata = analyze_document(rel_path, repo_root)

        # Find capability references
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
            "doc_id": doc_id,
            "path": rel_path,
            "type": doc_type,
            "maturity": metadata["maturity"],
            "referenced": bool(governs),
        }

        # Only include non-empty optional fields
        if metadata["title"]:
            doc_entry["title"] = metadata["title"]
        if metadata["line_count"]:
            doc_entry["line_count"] = metadata["line_count"]
        if metadata["scope_keywords"]:
            doc_entry["scope_keywords"] = metadata["scope_keywords"]
        if governs:
            doc_entry["governs_capabilities"] = governs

        # Cross-document references (only include refs to docs that exist on disk)
        refs = metadata.get("references", [])
        valid_refs = [r for r in refs if r in all_paths_set]
        if valid_refs:
            doc_entry["references"] = valid_refs

        # Git freshness
        if rel_path in git_dates:
            doc_entry["last_modified"] = git_dates[rel_path]

        documents.append(doc_entry)

    # Compute evidence refs that point outside scanned dirs
    all_on_disk = set(all_doc_files)
    external_refs = []
    for ref_path, refs in doc_evidence.items():
        if ref_path not in all_on_disk:
            external_refs.append({
                "path": ref_path,
                "referenced_by": [r["capability_id"] for r in refs],
            })

    # Build the full index
    index = {
        "manifest_id": "contextcore.docs",
        "name": "ContextCore Documentation Index",
        "version": "2.0.0",
        "description": (
            "Programmatically derived documentation index. "
            "Generated by scripts/generate_docs_index.py from capability index "
            "evidence entries and docs/ directory scan."
        ),
        "generated_at": date.today().isoformat(),
        "generator": "scripts/generate_docs_index.py",
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
            "external_evidence_refs": len(external_refs),
        },
        "documents": documents,
    }

    # Only include external refs if there are any
    if external_refs:
        index["external_evidence_refs"] = sorted(
            external_refs, key=lambda x: x["path"]
        )

    return index


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate contextcore.docs.yaml from capability index evidence"
    )
    parser.add_argument(
        "--output", "-o",
        default=str(CAPABILITY_INDEX_DIR / "contextcore.docs.yaml"),
        help="Output file path (default: docs/capability-index/contextcore.docs.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print to stdout instead of writing file",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Skip git freshness lookup (faster, no last_modified dates)",
    )
    args = parser.parse_args()

    print(f"[1/4] Extracting doc evidence from capability index YAMLs...")
    doc_evidence = extract_doc_evidence(CAPABILITY_INDEX_DIR)
    print(f"       Found {len(doc_evidence)} unique doc references across capabilities")

    print(f"[2/4] Scanning documentation directories...")
    all_docs = scan_doc_directories(REPO_ROOT)
    print(f"       Found {len(all_docs)} documentation files")

    git_label = " (skipping git)" if args.no_git else " (with git freshness)"
    print(f"[3/4] Building docs index{git_label}...")
    index = build_docs_index(doc_evidence, all_docs, REPO_ROOT, skip_git=args.no_git)

    # Count cross-references
    total_refs = sum(
        len(d.get("references", []))
        for d in index["documents"]
    )
    docs_with_refs = sum(
        1 for d in index["documents"] if d.get("references")
    )
    print(f"[4/4] Cross-reference analysis: {total_refs} links across {docs_with_refs} documents")

    summary = index["summary"]
    print(f"       {summary['total_documents']} total documents")
    print(f"       {summary['referenced_by_capabilities']} referenced by capabilities")
    print(f"       {summary['orphaned']} orphaned (not referenced)")
    print(f"       {summary['external_evidence_refs']} external evidence refs (outside scanned dirs)")
    print(f"       By type:")
    for doc_type, count in sorted(summary["by_type"].items()):
        print(f"         {doc_type}: {count}")

    # Serialize
    output_yaml = yaml.dump(
        index,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )

    if args.dry_run:
        print("\n--- Generated YAML ---")
        print(output_yaml)
    else:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(f"# Auto-generated by scripts/generate_docs_index.py\n")
            f.write(f"# Do not edit manually — re-run the script to update.\n")
            f.write(f"# Last generated: {date.today().isoformat()}\n\n")
            f.write(output_yaml)
        print(f"\n  Wrote {output_path}")


if __name__ == "__main__":
    main()
