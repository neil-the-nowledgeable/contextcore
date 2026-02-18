"""
Build an enhanced capability index by merging scanned capabilities with
hand-authored content and REQ-CID enhancements.

Workflow:
    1. Load base manifest (existing contextcore.agent.yaml)
    2. Scan contract domains + A2A governance for implemented capabilities
    3. Merge scanned capabilities (never overwrite existing)
    4. Inject design principles from _principles.yaml
    5. Inject patterns from _patterns.yaml
    6. Enrich triggers from _trigger_enrichments.yaml
    7. Merge P2 capabilities from _p2_capabilities.yaml (REQ-CID-004/005)
    8. Merge discovery paths from _discovery_paths.yaml (REQ-CID-008)
    9. Bump version and return updated manifest dict

Used by: contextcore capability-index build
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    """Load a YAML file, returning None on error."""
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not available")
        return None

    if not path.is_file():
        logger.debug("File not found: %s", path)
        return None

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to load %s: %s", path, e)
        return None


def _bump_version(version: str) -> str:
    """Bump minor version: 1.10.1 -> 1.11.0."""
    parts = version.split(".")
    if len(parts) == 3:
        try:
            major, minor, _ = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{major}.{minor + 1}.0"
        except ValueError:
            pass
    return version


def _get_existing_cap_ids(manifest: Dict[str, Any]) -> set[str]:
    """Extract existing capability_ids from a manifest dict."""
    return {
        c.get("capability_id", "")
        for c in (manifest.get("capabilities") or [])
        if isinstance(c, dict) and c.get("capability_id")
    }


def build_capability_index(
    project_root: Path,
    *,
    index_dir: Optional[Path] = None,
    contracts_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> Tuple[Dict[str, Any], "BuildReport"]:
    """Build an enhanced capability index manifest.

    Args:
        project_root: Root of the ContextCore project.
        index_dir: Path to capability index directory (default:
            ``project_root / docs / capability-index``).
        contracts_dir: Path to contracts source (default:
            ``project_root / src / contextcore / contracts``).
        dry_run: If True, do not write to disk.

    Returns:
        Tuple of (manifest_dict, BuildReport).
    """
    from contextcore.utils.capability_scanner import (
        scan_a2a_contracts,
        scan_contract_domains,
    )

    if index_dir is None:
        index_dir = project_root / "docs" / "capability-index"
    if contracts_dir is None:
        contracts_dir = project_root / "src" / "contextcore" / "contracts"

    report = BuildReport()

    # 1. Load base manifest
    base_path = index_dir / "contextcore.agent.yaml"
    manifest = _load_yaml(base_path)
    if manifest is None:
        manifest = {
            "manifest_id": "contextcore.agent",
            "name": "ContextCore Agent Capabilities",
            "version": "1.0.0",
            "capabilities": [],
        }
        report.notes.append("No existing manifest found; created skeleton")
    else:
        manifest = copy.deepcopy(manifest)

    report.original_version = manifest.get("version", "")
    existing_ids = _get_existing_cap_ids(manifest)
    report.original_capability_count = len(existing_ids)

    # 2. Scan contract domains + A2A
    contract_caps = scan_contract_domains(contracts_dir, project_root=project_root)
    a2a_caps = scan_a2a_contracts(contracts_dir, project_root=project_root)

    # 3. Merge scanned capabilities (never overwrite existing)
    if "capabilities" not in manifest:
        manifest["capabilities"] = []

    for cap in contract_caps + a2a_caps:
        cap_id = cap["capability_id"]
        if cap_id not in existing_ids:
            manifest["capabilities"].append(cap)
            existing_ids.add(cap_id)
            report.added_capabilities.append(cap_id)
        else:
            report.skipped_capabilities.append(cap_id)

    # 4. Inject design principles
    principles_path = index_dir / "_principles.yaml"
    principles_data = _load_yaml(principles_path)
    if principles_data and "design_principles" in principles_data:
        existing_principles = manifest.get("design_principles") or []
        existing_principle_ids = {
            p.get("id", "") for p in existing_principles if isinstance(p, dict)
        }
        new_principles = [
            p for p in principles_data["design_principles"]
            if isinstance(p, dict) and p.get("id") not in existing_principle_ids
        ]
        if new_principles:
            manifest["design_principles"] = existing_principles + new_principles
            report.principles_added = len(new_principles)
    else:
        report.notes.append("No _principles.yaml found or empty")

    # 5. Inject patterns
    patterns_path = index_dir / "_patterns.yaml"
    patterns_data = _load_yaml(patterns_path)
    if patterns_data and "patterns" in patterns_data:
        existing_patterns = manifest.get("patterns") or []
        existing_pattern_ids = {
            p.get("pattern_id", "") for p in existing_patterns if isinstance(p, dict)
        }
        new_patterns = [
            p for p in patterns_data["patterns"]
            if isinstance(p, dict) and p.get("pattern_id") not in existing_pattern_ids
        ]
        if new_patterns:
            manifest["patterns"] = existing_patterns + new_patterns
            report.patterns_added = len(new_patterns)
    else:
        report.notes.append("No _patterns.yaml found or empty")

    # 6. Enrich triggers
    enrichments_path = index_dir / "_trigger_enrichments.yaml"
    enrichments_data = _load_yaml(enrichments_path)
    if enrichments_data and "trigger_enrichments" in enrichments_data:
        enrichments = enrichments_data["trigger_enrichments"]
        for cap in manifest.get("capabilities", []):
            if not isinstance(cap, dict):
                continue
            cap_id = cap.get("capability_id", "")
            if cap_id in enrichments:
                existing_triggers = set(cap.get("triggers") or [])
                new_triggers = [
                    t for t in enrichments[cap_id]
                    if t not in existing_triggers
                ]
                if new_triggers:
                    cap.setdefault("triggers", []).extend(new_triggers)
                    report.triggers_enriched[cap_id] = new_triggers
    else:
        report.notes.append("No _trigger_enrichments.yaml found or empty")

    # 7. Merge P2 capabilities (REQ-CID-004, REQ-CID-005)
    p2_path = index_dir / "_p2_capabilities.yaml"
    p2_data = _load_yaml(p2_path)
    if p2_data and "capabilities" in p2_data:
        for cap in p2_data["capabilities"]:
            if not isinstance(cap, dict):
                continue
            cap_id = cap.get("capability_id", "")
            if cap_id and cap_id not in existing_ids:
                manifest["capabilities"].append(cap)
                existing_ids.add(cap_id)
                report.added_capabilities.append(cap_id)
            elif cap_id:
                report.skipped_capabilities.append(cap_id)
    else:
        report.notes.append("No _p2_capabilities.yaml found or empty")

    # 8. Merge discovery paths (REQ-CID-008)
    discovery_path = index_dir / "_discovery_paths.yaml"
    discovery_data = _load_yaml(discovery_path)
    if discovery_data and "discovery_paths" in discovery_data:
        paths_map = discovery_data["discovery_paths"]
        for cap in manifest.get("capabilities", []):
            if not isinstance(cap, dict):
                continue
            cap_id = cap.get("capability_id", "")
            if cap_id in paths_map:
                existing_paths = set(cap.get("discovery_paths") or [])
                new_paths = [
                    p for p in paths_map[cap_id]
                    if p not in existing_paths
                ]
                if new_paths:
                    cap.setdefault("discovery_paths", []).extend(new_paths)
                    report.discovery_paths_added[cap_id] = new_paths
    else:
        report.notes.append("No _discovery_paths.yaml found or empty")

    # 9. Default audiences for non-internal capabilities (REQ-CID-019)
    # Without audiences, MCP/A2A generators default to ["human"] and silently
    # exclude the capability from agent-facing exports (the Phase 3 root cause).
    for cap in manifest.get("capabilities", []):
        if not isinstance(cap, dict):
            continue
        if "audiences" not in cap and not cap.get("internal", False):
            cap["audiences"] = ["agent", "human"]
            cap_id = cap.get("capability_id", "unknown")
            report.audiences_defaulted.append(cap_id)

    # 10. Bump version
    old_version = manifest.get("version", "1.0.0")
    new_version = _bump_version(old_version)
    manifest["version"] = new_version
    report.new_version = new_version

    return manifest, report


def write_manifest(manifest: Dict[str, Any], output_path: Path) -> None:
    """Write manifest dict to YAML file.

    Raises:
        OSError: If the file cannot be written (permissions, disk full).
    """
    import yaml

    try:
        output_path.write_text(
            yaml.dump(
                manifest,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=120,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        logger.error("Failed to write manifest to %s: %s", output_path, e)
        raise


class BuildReport:
    """Report of what build_capability_index() did."""

    def __init__(self) -> None:
        self.original_version: str = ""
        self.new_version: str = ""
        self.original_capability_count: int = 0
        self.added_capabilities: List[str] = []
        self.skipped_capabilities: List[str] = []
        self.audiences_defaulted: List[str] = []
        self.principles_added: int = 0
        self.patterns_added: int = 0
        self.triggers_enriched: Dict[str, List[str]] = {}
        self.discovery_paths_added: Dict[str, List[str]] = {}
        self.notes: List[str] = []

    @property
    def total_capabilities(self) -> int:
        return self.original_capability_count + len(self.added_capabilities)

    def summary(self) -> str:
        lines = [
            f"Version: {self.original_version} -> {self.new_version}",
            f"Capabilities: {self.original_capability_count} existing + {len(self.added_capabilities)} added = {self.total_capabilities}",
        ]
        if self.added_capabilities:
            lines.append(f"  Added: {', '.join(self.added_capabilities)}")
        if self.skipped_capabilities:
            lines.append(f"  Skipped (already exist): {', '.join(self.skipped_capabilities)}")
        if self.audiences_defaulted:
            lines.append(f"  Audiences defaulted to [agent, human]: {len(self.audiences_defaulted)} capabilities")
        if self.principles_added:
            lines.append(f"Principles: {self.principles_added} added")
        if self.patterns_added:
            lines.append(f"Patterns: {self.patterns_added} added")
        if self.triggers_enriched:
            enriched_count = sum(len(v) for v in self.triggers_enriched.values())
            lines.append(f"Triggers: {enriched_count} new triggers across {len(self.triggers_enriched)} capabilities")
        if self.discovery_paths_added:
            paths_count = sum(len(v) for v in self.discovery_paths_added.values())
            lines.append(f"Discovery paths: {paths_count} paths across {len(self.discovery_paths_added)} capabilities")
        if self.notes:
            lines.append(f"Notes: {'; '.join(self.notes)}")
        return "\n".join(lines)
