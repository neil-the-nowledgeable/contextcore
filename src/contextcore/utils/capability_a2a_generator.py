"""
A2A Agent Card Generator.

Generates Agent-to-Agent (A2A) protocol Agent Cards from capability manifests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional

import yaml

logger = logging.getLogger(__name__)


def load_yaml(path: Path) -> dict:
    """Load a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed YAML as a dict (empty dict for empty files).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file contains invalid YAML.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("Manifest file not found: %s", path)
        raise
    except OSError as e:
        logger.error("Failed to read %s: %s", path, e)
        raise

    try:
        return yaml.safe_load(content) or {}
    except yaml.YAMLError as e:
        logger.error("Invalid YAML in %s: %s", path, e)
        raise ValueError(f"Invalid YAML in {path}: {e}") from e


def capability_to_a2a_skill(cap: dict) -> Optional[dict]:
    """
    Convert a capability to an A2A skill descriptor.

    Only agent-facing capabilities are included.
    Draft capabilities are included with maturity metadata so agents
    can discover planned capabilities without depending on them.
    """
    audiences = cap.get("audiences", ["human"])
    if "agent" not in audiences:
        return None

    if cap.get("internal", False):
        return None

    maturity = cap.get("maturity", "development")
    summary = cap.get("summary", "")
    if maturity == "development":
        summary = f"[DEVELOPMENT - not yet implemented] {summary}"

    tags = list(cap.get("triggers", []))
    tags.append(f"maturity:{maturity}")

    return {
        "id": cap.get("capability_id"),
        "name": cap.get("capability_id", "").split(".")[-1].replace("_", " ").title(),
        "description": summary,
        "tags": tags,
        "maturity": maturity,
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

    # Add discovery metadata from a2a config (REQ-CID-021)
    metadata = {}
    if "discovery_endpoint" in a2a_config:
        metadata["discoveryEndpoint"] = a2a_config["discovery_endpoint"]
    if "extended_discovery_endpoint" in a2a_config:
        metadata["extendedDiscoveryEndpoint"] = a2a_config["extended_discovery_endpoint"]
    if metadata:
        agent_card["metadata"] = metadata

    return agent_card


def aggregate_agent_cards(index_dir: Path) -> List[dict]:
    """Generate Agent Cards from all manifests in an index directory."""
    cards: List[dict] = []

    manifests_dir = index_dir / "manifests"
    if not manifests_dir.exists():
        manifests_dir = index_dir

    for manifest_path in manifests_dir.glob("*.yaml"):
        try:
            manifest = load_yaml(manifest_path)
            card = manifest_to_agent_card(manifest)
            cards.append(card)
        except (ValueError, FileNotFoundError, OSError) as e:
            logger.warning("Skipping %s: %s", manifest_path.name, e)
            continue

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
