"""
Capability Index Query Tool.

Query the aggregated capability index with filters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional

import yaml


def load_index(path: Path) -> dict:
    """Load the capability index."""
    if path.is_dir():
        # Try common locations
        candidates = [
            path / "generated" / "full-index.json",
            path / "generated" / "full-index.yaml",
            path / "full-index.json",
            path / "full-index.yaml"
        ]
        for candidate in candidates:
            if candidate.exists():
                path = candidate
                break
        else:
            raise FileNotFoundError(f"No index found in {path}")

    if path.suffix == ".json":
        with open(path) as f:
            return json.load(f)
    else:
        with open(path) as f:
            return yaml.safe_load(f)


def query_capabilities(
    index: dict,
    capability_id: Optional[str] = None,
    category: Optional[str] = None,
    maturity: Optional[str] = None,
    audience: Optional[str] = None,
    trigger: Optional[str] = None,
    min_confidence: Optional[float] = None,
    exclude_internal: bool = True
) -> List[dict]:
    """Query capabilities with filters."""
    capabilities = index.get("capabilities", [])
    results: List[dict] = []

    for cap in capabilities:
        # Filter by capability_id (exact or prefix match)
        if capability_id:
            cap_id = cap.get("capability_id", "")
            if not (cap_id == capability_id or cap_id.startswith(capability_id + ".")):
                continue

        # Filter by category
        if category and cap.get("category") != category:
            continue

        # Filter by maturity
        if maturity and cap.get("maturity") != maturity:
            continue

        # Filter by audience
        if audience and audience not in cap.get("audiences", []):
            continue

        # Filter by trigger (substring match)
        if trigger:
            triggers = cap.get("triggers", [])
            if not any(trigger.lower() in t.lower() for t in triggers):
                continue

        # Filter by confidence
        if min_confidence is not None:
            if cap.get("confidence", 0) < min_confidence:
                continue

        # Exclude internal
        if exclude_internal and cap.get("internal", False):
            continue

        results.append(cap)

    return results


def format_capability(cap: dict, verbose: bool = False) -> str:
    """Format a capability for display."""
    lines: List[str] = []

    cap_id = cap.get("capability_id", "unknown")
    maturity = cap.get("maturity", "?")
    category = cap.get("category", "?")
    confidence = cap.get("confidence", 0)

    # Header line
    maturity_icon = {
        "draft": "[draft]",
        "beta": "[beta]",
        "stable": "[stable]",
        "deprecated": "[deprecated]"
    }.get(maturity, "[?]")

    lines.append(f"{maturity_icon} {cap_id}")
    lines.append(f"   {cap.get('summary', 'No summary')}")

    if verbose:
        lines.append(f"   Category: {category} | Maturity: {maturity} | Confidence: {confidence:.0%}")
        lines.append(f"   Manifest: {cap.get('manifest_id', 'unknown')}")
        audiences = ", ".join(cap.get("audiences", []))
        lines.append(f"   Audiences: {audiences}")
        triggers = cap.get("triggers", [])
        if triggers:
            lines.append(f"   Triggers: {', '.join(triggers[:5])}")

    return "\n".join(lines)


def query_from_file(
    index_path: Path,
    capability_id: Optional[str] = None,
    category: Optional[str] = None,
    maturity: Optional[str] = None,
    audience: Optional[str] = None,
    trigger: Optional[str] = None,
    min_confidence: Optional[float] = None,
    include_internal: bool = False,
) -> List[dict]:
    """Query capabilities from an index file.

    This is the main entry point for CLI integration.
    """
    index = load_index(index_path)
    return query_capabilities(
        index,
        capability_id=capability_id,
        category=category,
        maturity=maturity,
        audience=audience,
        trigger=trigger,
        min_confidence=min_confidence,
        exclude_internal=not include_internal,
    )
