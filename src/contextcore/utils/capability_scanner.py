"""
Scan contract domains and A2A governance to discover implemented capabilities.

Reads ``src/contextcore/contracts/`` directory structure to discover the 7-layer
defense-in-depth contract system and A2A governance contracts, producing
capability entries suitable for merging into the capability index.

Each contract domain follows a consistent structure:
    schema.py   — Pydantic v2 models (has docstring describing the domain)
    loader.py   — YAML loading with caching
    validator.py — Contract enforcement logic
    tracker.py  — Provenance tracking
    otel.py     — OTel span event emission

Used by: capability_builder.py
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Domain → capability mapping ──────────────────────────────────────────

DOMAIN_MAP: Dict[str, Dict[str, Any]] = {
    "propagation": {
        "capability_id": "contextcore.contract.propagation",
        "layer": "L1",
        "summary": "Declare end-to-end field flow contracts, validate at phase boundaries, track provenance",
        "triggers": [
            "context contract",
            "propagation chain",
            "boundary validation",
            "field flow",
            "context propagation",
            "chain status",
        ],
    },
    "schema_compat": {
        "capability_id": "contextcore.contract.schema_compat",
        "layer": "L2",
        "summary": "Cross-service schema compatibility checking with field mapping and value translation",
        "triggers": [
            "schema compatibility",
            "contract drift",
            "field mapping",
            "value translation",
            "schema evolution",
        ],
    },
    "semconv": {
        "capability_id": "contextcore.contract.semantic_convention",
        "layer": "L3",
        "summary": "Attribute naming and enum consistency enforcement across services",
        "triggers": [
            "semantic convention",
            "attribute naming",
            "enum consistency",
            "naming convention enforcement",
        ],
    },
    "ordering": {
        "capability_id": "contextcore.contract.causal_ordering",
        "layer": "L4",
        "summary": "Cross-boundary event ordering contracts with timestamp verification",
        "triggers": [
            "causal ordering",
            "event ordering",
            "ordering constraint",
            "happens-before",
        ],
    },
    "capability": {
        "capability_id": "contextcore.contract.capability_propagation",
        "layer": "L5",
        "summary": "End-to-end permission and capability flow verification through call chains",
        "triggers": [
            "capability propagation",
            "permission flow",
            "authorization chain",
            "capability verification",
        ],
    },
    "budget": {
        "capability_id": "contextcore.contract.slo_budget",
        "layer": "L6",
        "summary": "Per-hop latency budget allocation, tracking, and DEGRADED/BROKEN signaling",
        "triggers": [
            "SLO budget",
            "latency budget",
            "budget tracking",
            "deadline propagation",
        ],
    },
    "lineage": {
        "capability_id": "contextcore.contract.data_lineage",
        "layer": "L7",
        "summary": "Transformation history verification and data provenance tracking",
        "triggers": [
            "data lineage",
            "provenance",
            "transformation history",
            "data origin",
        ],
    },
}

# A2A governance capability definitions
A2A_CAPABILITIES: List[Dict[str, Any]] = [
    {
        "capability_id": "contextcore.a2a.contract.task_span",
        "category": "transform",
        "summary": "Typed contract for task span interchange — validates SpanState v2 compliance, required attributes, and enum values",
        "triggers": [
            "task span contract",
            "span validation",
            "a2a contract",
            "task interchange",
            "SpanState validation",
        ],
    },
    {
        "capability_id": "contextcore.a2a.contract.handoff",
        "category": "transform",
        "summary": "Typed contract for agent-to-agent handoff — validates ExpectedOutput, lifecycle status, and provenance chain",
        "triggers": [
            "handoff contract",
            "a2a contract",
            "delegation validation",
            "handoff integrity",
        ],
    },
    {
        "capability_id": "contextcore.a2a.contract.artifact_intent",
        "category": "transform",
        "summary": "Typed declaration of expected artifacts with semantic roles — the Mottainai principle",
        "triggers": [
            "artifact intent",
            "a2a contract",
            "artifact declaration",
            "pipeline output",
            "Mottainai",
        ],
    },
    {
        "capability_id": "contextcore.a2a.contract.gate_result",
        "category": "transform",
        "summary": "Typed result from governance gates — pass/fail/warning with structured diagnostics",
        "triggers": [
            "gate result",
            "governance gate",
            "gate diagnostic",
            "integrity check result",
        ],
    },
    {
        "capability_id": "contextcore.a2a.gate.pipeline_integrity",
        "category": "action",
        "summary": "Gate 1: 6 structural integrity checks on exported pipeline artifacts",
        "triggers": [
            "pipeline integrity",
            "governance gate",
            "a2a-check-pipeline",
            "integrity checks",
            "export validation",
        ],
    },
    {
        "capability_id": "contextcore.a2a.gate.diagnostic",
        "category": "action",
        "summary": "Gate 2: Three Questions diagnostic — Was anything lost? Does the shape match? Can we trace the lineage?",
        "triggers": [
            "diagnostic gate",
            "three questions",
            "a2a-diagnose",
            "governance diagnostic",
            "pipeline diagnostic",
        ],
    },
]

# Expected files per contract domain (for confidence scoring)
EXPECTED_FILES = ["schema.py", "loader.py", "validator.py", "otel.py"]
EXPECTED_OPTIONAL = ["tracker.py"]


def _extract_docstring(py_file: Path) -> Optional[str]:
    """Extract the module docstring from a Python file via AST."""
    try:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        return ast.get_docstring(tree)
    except Exception:
        logger.debug("Failed to extract docstring from %s", py_file, exc_info=True)
        return None


def _count_test_files(domain_name: str, project_root: Path) -> int:
    """Count test files for a contract domain."""
    test_dir = project_root / "tests" / "unit" / "contextcore" / "contracts" / domain_name
    if not test_dir.is_dir():
        return 0
    return sum(1 for f in test_dir.glob("test_*.py") if f.is_file())


def _compute_confidence(domain_dir: Path, domain_name: str, project_root: Path) -> float:
    """Compute confidence score based on file completeness and tests."""
    found = sum(1 for f in EXPECTED_FILES if (domain_dir / f).is_file())
    has_tests = _count_test_files(domain_name, project_root) > 0

    if found == len(EXPECTED_FILES) and has_tests:
        return 0.90
    elif found == len(EXPECTED_FILES):
        return 0.80
    elif has_tests:
        return 0.70
    elif found >= 2:
        return 0.60
    else:
        return 0.40


def scan_contract_domains(
    contracts_dir: Path,
    project_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Scan contract domain directories and produce capability entries.

    Args:
        contracts_dir: Path to ``src/contextcore/contracts/``
        project_root: Project root for test discovery. If None, inferred
            from contracts_dir (3 levels up).

    Returns:
        List of capability dicts following the manifest YAML schema.
    """
    if project_root is None:
        # contracts_dir is typically src/contextcore/contracts/
        project_root = contracts_dir.parent.parent.parent

    capabilities: List[Dict[str, Any]] = []

    for domain_name, meta in DOMAIN_MAP.items():
        domain_dir = contracts_dir / domain_name
        if not domain_dir.is_dir():
            logger.debug("Contract domain directory not found: %s", domain_dir)
            continue

        # Extract description from schema.py docstring
        schema_file = domain_dir / "schema.py"
        docstring = _extract_docstring(schema_file) if schema_file.is_file() else None

        # Compute confidence
        confidence = _compute_confidence(domain_dir, domain_name, project_root)

        # Count evidence
        present_files = [f for f in EXPECTED_FILES + EXPECTED_OPTIONAL if (domain_dir / f).is_file()]
        test_count = _count_test_files(domain_name, project_root)

        cap: Dict[str, Any] = {
            "capability_id": meta["capability_id"],
            "category": "transform",
            "maturity": "beta",
            "summary": meta["summary"],
            "triggers": list(meta["triggers"]),
            "confidence": confidence,
            "evidence": {
                "source_dir": str(domain_dir.relative_to(project_root)),
                "files": present_files,
                "test_count": test_count,
                "layer": meta["layer"],
            },
        }

        if docstring:
            # Use first paragraph as agent description
            first_para = docstring.split("\n\n")[0].strip()
            cap["description"] = {"agent": first_para}

        capabilities.append(cap)

    return capabilities


def scan_a2a_contracts(
    contracts_dir: Path,
    project_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Scan A2A governance contracts and produce capability entries.

    Checks for the presence of key A2A modules (models.py, gates.py,
    validator.py, boundary.py, pilot.py, pipeline_checker.py,
    three_questions.py) to determine which A2A capabilities exist.

    Args:
        contracts_dir: Path to ``src/contextcore/contracts/``
        project_root: Project root for test discovery.

    Returns:
        List of capability dicts for A2A governance.
    """
    if project_root is None:
        project_root = contracts_dir.parent.parent.parent

    a2a_dir = contracts_dir / "a2a"
    if not a2a_dir.is_dir():
        logger.debug("A2A contract directory not found: %s", a2a_dir)
        return []

    # Check for key A2A modules
    key_modules = {
        "models.py": ["contextcore.a2a.contract.task_span", "contextcore.a2a.contract.handoff",
                       "contextcore.a2a.contract.artifact_intent", "contextcore.a2a.contract.gate_result"],
        "gates.py": ["contextcore.a2a.gate.pipeline_integrity"],
        "three_questions.py": ["contextcore.a2a.gate.diagnostic"],
        "pipeline_checker.py": ["contextcore.a2a.gate.pipeline_integrity"],
    }

    # Find which modules exist
    existing_modules = [f.name for f in a2a_dir.glob("*.py") if f.is_file()]
    a2a_test_dir = project_root / "tests" / "unit" / "contextcore" / "contracts" / "a2a"
    has_tests = a2a_test_dir.is_dir() and any(a2a_test_dir.glob("test_*.py"))

    # Determine available capability IDs based on existing modules
    available_ids: set[str] = set()
    for module_name, cap_ids in key_modules.items():
        if module_name in existing_modules:
            available_ids.update(cap_ids)

    # Build capabilities for available IDs
    capabilities: List[Dict[str, Any]] = []
    for cap_def in A2A_CAPABILITIES:
        if cap_def["capability_id"] not in available_ids:
            continue

        confidence = 0.85 if has_tests else 0.70

        cap: Dict[str, Any] = {
            "capability_id": cap_def["capability_id"],
            "category": cap_def["category"],
            "maturity": "beta",
            "summary": cap_def["summary"],
            "triggers": list(cap_def["triggers"]),
            "confidence": confidence,
            "evidence": {
                "source_dir": str(a2a_dir.relative_to(project_root)),
                "modules": [m for m in existing_modules if not m.startswith("__")],
            },
        }
        capabilities.append(cap)

    return capabilities
