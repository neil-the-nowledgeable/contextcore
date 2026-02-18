"""
MCP Tool Definition Generator.

Generates Model Context Protocol (MCP) tool definitions from capability manifests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional

import yaml


def load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def capability_to_mcp_tool(
    cap: dict,
    manifest_id: str
) -> Optional[dict]:
    """
    Convert a capability to an MCP tool definition.

    Only capabilities with audience=agent are converted.
    """
    # Skip if not agent-facing
    audiences = cap.get("audiences", ["human"])
    if "agent" not in audiences:
        return None

    # Skip draft capabilities
    if cap.get("maturity") == "draft":
        return None

    # Skip internal capabilities (unless explicitly opted in)
    if cap.get("internal", False):
        return None

    capability_id = cap.get("capability_id", "")

    # Build description from summary + anti-patterns
    description_parts = [cap.get("summary", "")]
    anti_patterns = cap.get("anti_patterns", [])
    if anti_patterns:
        description_parts.append("\n\nAvoid:")
        for ap in anti_patterns:
            description_parts.append(f"- {ap}")

    description = "\n".join(description_parts)

    # Build input schema
    input_schema = cap.get("inputs", {
        "type": "object",
        "properties": {}
    })

    # Ensure required fields
    if "type" not in input_schema:
        input_schema["type"] = "object"

    tool: dict = {
        "name": capability_id,
        "description": description,
        "inputSchema": input_schema
    }

    # Add output schema if defined (MCP extension)
    if "outputs" in cap:
        tool["outputSchema"] = cap["outputs"]

    # Add metadata as annotations (MCP extension)
    tool["annotations"] = {
        "manifest_id": manifest_id,
        "category": cap.get("category"),
        "maturity": cap.get("maturity"),
        "confidence": cap.get("confidence", 0.5)
    }

    return tool


def generate_mcp_tools(manifest: dict) -> List[dict]:
    """Generate MCP tool definitions from a manifest."""
    tools = []
    manifest_id = manifest.get("manifest_id", "unknown")

    for cap in manifest.get("capabilities", []):
        tool = capability_to_mcp_tool(cap, manifest_id)
        if tool:
            tools.append(tool)

    return tools


def generate_mcp_server_config(
    tools: List[dict],
    manifest: dict
) -> dict:
    """Generate a full MCP server configuration."""
    return {
        "name": manifest.get("name", manifest.get("manifest_id", "unknown")),
        "version": manifest.get("version", "1.0.0"),
        "description": manifest.get("description", ""),
        "tools": tools
    }


def aggregate_tools(index_dir: Path) -> List[dict]:
    """Aggregate tools from all manifests in an index directory."""
    all_tools: List[dict] = []

    manifests_dir = index_dir / "manifests"
    if not manifests_dir.exists():
        manifests_dir = index_dir  # Try the directory itself

    for manifest_path in manifests_dir.glob("*.yaml"):
        manifest = load_yaml(manifest_path)
        tools = generate_mcp_tools(manifest)
        all_tools.extend(tools)

    return all_tools


def generate_mcp_from_file(
    manifest_path: Path,
    server_config: bool = False,
) -> dict:
    """Generate MCP output from a manifest file.

    This is the main entry point for CLI integration.

    Returns:
        Dict with tools list (or full server config if server_config=True).
    """
    manifest = load_yaml(manifest_path)
    tools = generate_mcp_tools(manifest)

    if server_config:
        return generate_mcp_server_config(tools, manifest)

    return {
        "manifest_id": manifest.get("manifest_id"),
        "tools": tools,
        "tool_count": len(tools)
    }
