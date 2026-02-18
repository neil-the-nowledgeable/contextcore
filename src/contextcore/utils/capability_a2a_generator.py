"""
A2A Agent Card Generator.

Generates Agent-to-Agent (A2A) protocol Agent Cards from capability manifests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

import yaml


def load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def capability_to_a2a_skill(cap: dict) -> Optional[dict]:
    """
    Convert a capability to an A2A skill descriptor.

    Only agent-facing capabilities are included.
    """
    audiences = cap.get("audiences", ["human"])
    if "agent" not in audiences:
        return None

    if cap.get("maturity") == "draft":
        return None

    if cap.get("internal", False):
        return None

    return {
        "id": cap.get("capability_id"),
        "name": cap.get("capability_id", "").split(".")[-1].replace("_", " ").title(),
        "description": cap.get("summary", ""),
        "tags": cap.get("triggers", []),
        "inputModes": ["application/json"],
        "outputModes": ["application/json"]
    }


def manifest_to_agent_card(manifest: dict) -> dict:
    """
    Generate an A2A Agent Card from a capability manifest.

    Follows A2A protocol specification.
    """
    manifest_id = manifest.get("manifest_id", "unknown")
    a2a_config = manifest.get("a2a", {})

    # Extract skills from capabilities
    skills: List[dict] = []
    for cap in manifest.get("capabilities", []):
        skill = capability_to_a2a_skill(cap)
        if skill:
            skills.append(skill)

    # Build Agent Card
    agent_card: dict = {
        # Required A2A fields
        "name": manifest.get("name", manifest_id),
        "description": manifest.get("description", ""),
        "url": a2a_config.get("url", f"https://api.example.com/{manifest_id}"),
        "version": manifest.get("version", "1.0.0"),

        # Capabilities (A2A standard)
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False
        },

        # Skills
        "skills": skills,

        # Authentication
        "authentication": a2a_config.get("authentication", {
            "schemes": ["bearer"]
        }),

        # Provider info
        "provider": a2a_config.get("provider", {
            "organization": manifest.get("owner", "Unknown"),
            "url": manifest.get("repository", "")
        })
    }

    # Add contact if available
    if "contact" in manifest:
        agent_card["provider"]["contact"] = manifest["contact"]

    return agent_card


def aggregate_agent_cards(index_dir: Path) -> List[dict]:
    """Generate Agent Cards from all manifests in an index directory."""
    cards: List[dict] = []

    manifests_dir = index_dir / "manifests"
    if not manifests_dir.exists():
        manifests_dir = index_dir

    for manifest_path in manifests_dir.glob("*.yaml"):
        manifest = load_yaml(manifest_path)
        card = manifest_to_agent_card(manifest)
        cards.append(card)

    return cards


def generate_a2a_from_file(
    manifest_path: Path,
    well_known: bool = False,
) -> dict:
    """Generate A2A Agent Card from a manifest file.

    This is the main entry point for CLI integration.

    Returns:
        Dict with agent card (or raw card if well_known=True).
    """
    manifest = load_yaml(manifest_path)
    card = manifest_to_agent_card(manifest)

    if well_known:
        return card

    return {
        "manifest_id": manifest.get("manifest_id"),
        "agent_card": card
    }
