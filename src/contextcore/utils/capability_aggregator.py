"""
Capability Index Aggregator.

Pulls capability manifests from multiple sources and creates a unified index.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import yaml


@dataclass
class Source:
    """A source repository for capability manifests."""
    name: str
    repo: Optional[str] = None  # Git URL
    path: str = "capabilities/manifest.yaml"
    local_path: Optional[Path] = None  # For local directories


@dataclass
class AggregatorConfig:
    """Configuration for the aggregator."""
    sources: List[Source] = field(default_factory=list)
    output_dir: Path = field(default_factory=lambda: Path("index"))
    manifests_dir: str = "manifests"
    views_dir: str = "views"
    generated_dir: str = "generated"
    generate: List[str] = field(default_factory=lambda: ["full_index"])


def load_config(config_path: Path) -> AggregatorConfig:
    """Load aggregator configuration from YAML."""
    with open(config_path) as f:
        data = yaml.safe_load(f)

    sources: List[Source] = []
    for s in data.get("sources", []):
        sources.append(Source(
            name=s["name"],
            repo=s.get("repo"),
            path=s.get("path", "capabilities/manifest.yaml"),
            local_path=Path(s["local_path"]) if "local_path" in s else None
        ))

    output = data.get("output", {})
    return AggregatorConfig(
        sources=sources,
        output_dir=Path(output.get("dir", data.get("output_dir", "index"))),
        manifests_dir=output.get("manifests_dir", "manifests"),
        views_dir=output.get("views_dir", "views"),
        generated_dir=output.get("generated_dir", "generated"),
        generate=data.get("generate", ["full_index"])
    )


def clone_or_pull(repo_url: str, target_dir: Path) -> bool:
    """Clone a repo or pull if it exists."""
    if target_dir.exists():
        result = subprocess.run(
            ["git", "-C", str(target_dir), "pull", "--ff-only"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    else:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
            capture_output=True,
            text=True
        )
        return result.returncode == 0


def load_manifest(path: Path) -> Optional[dict]:
    """Load a manifest file."""
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def aggregate_manifests(
    config: AggregatorConfig,
    work_dir: Path
) -> List[dict]:
    """Fetch and aggregate all manifests from sources."""
    manifests: List[dict] = []

    for source in config.sources:
        print(f"Processing source: {source.name}")

        # Determine manifest path
        if source.local_path:
            manifest_path = source.local_path / source.path
        elif source.repo:
            repo_dir = work_dir / "repos" / source.name
            if not clone_or_pull(source.repo, repo_dir):
                print(f"  Failed to fetch {source.repo}")
                continue
            manifest_path = repo_dir / source.path
        else:
            print(f"  No repo or local_path specified")
            continue

        # Load manifest
        manifest = load_manifest(manifest_path)
        if manifest is None:
            print(f"  Manifest not found: {manifest_path}")
            continue

        # Add source metadata
        manifest["_source"] = {
            "name": source.name,
            "path": str(manifest_path),
            "fetched_at": datetime.utcnow().isoformat() + "Z"
        }

        manifests.append(manifest)
        cap_count = len(manifest.get("capabilities", []))
        print(f"  Loaded {cap_count} capabilities")

    return manifests


def write_manifests(
    manifests: List[dict],
    output_dir: Path
) -> None:
    """Write individual manifests to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for manifest in manifests:
        manifest_id = manifest.get("manifest_id", "unknown")
        filename = f"{manifest_id}.yaml"
        output_path = output_dir / filename

        with open(output_path, "w") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

        print(f"  Wrote: {output_path}")


def generate_full_index(
    manifests: List[dict],
    output_dir: Path
) -> None:
    """Generate a full searchable index."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Flatten all capabilities
    capabilities: List[dict] = []
    for manifest in manifests:
        manifest_id = manifest.get("manifest_id", "unknown")
        for cap in manifest.get("capabilities", []):
            cap_entry = {
                "capability_id": cap.get("capability_id"),
                "manifest_id": manifest_id,
                "category": cap.get("category"),
                "maturity": cap.get("maturity"),
                "summary": cap.get("summary"),
                "audiences": cap.get("audiences", ["human"]),
                "triggers": cap.get("triggers", []),
                "confidence": cap.get("confidence", 0.5),
                "internal": cap.get("internal", False)
            }
            capabilities.append(cap_entry)

    index = {
        "version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "manifest_count": len(manifests),
        "capability_count": len(capabilities),
        "capabilities": capabilities
    }

    # Write JSON (for programmatic access)
    json_path = output_dir / "full-index.json"
    with open(json_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"  Wrote: {json_path}")

    # Write YAML (for human readability)
    yaml_path = output_dir / "full-index.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(index, f, default_flow_style=False, sort_keys=False)
    print(f"  Wrote: {yaml_path}")


def generate_by_category_view(
    manifests: List[dict],
    output_dir: Path
) -> None:
    """Generate a view grouped by category."""
    output_dir.mkdir(parents=True, exist_ok=True)

    by_category: dict = {}

    for manifest in manifests:
        manifest_id = manifest.get("manifest_id", "unknown")
        for cap in manifest.get("capabilities", []):
            category = cap.get("category", "unknown")
            if category not in by_category:
                by_category[category] = []

            by_category[category].append({
                "capability_id": cap.get("capability_id"),
                "manifest_id": manifest_id,
                "summary": cap.get("summary"),
                "maturity": cap.get("maturity")
            })

    view = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "categories": by_category
    }

    output_path = output_dir / "by-category.yaml"
    with open(output_path, "w") as f:
        yaml.dump(view, f, default_flow_style=False, sort_keys=False)
    print(f"  Wrote: {output_path}")


def generate_by_audience_view(
    manifests: List[dict],
    output_dir: Path
) -> None:
    """Generate a view grouped by audience."""
    output_dir.mkdir(parents=True, exist_ok=True)

    by_audience: dict = {"agent": [], "human": [], "gtm": []}

    for manifest in manifests:
        manifest_id = manifest.get("manifest_id", "unknown")
        for cap in manifest.get("capabilities", []):
            audiences = cap.get("audiences", ["human"])
            for audience in audiences:
                if audience in by_audience:
                    by_audience[audience].append({
                        "capability_id": cap.get("capability_id"),
                        "manifest_id": manifest_id,
                        "summary": cap.get("summary"),
                        "maturity": cap.get("maturity")
                    })

    view = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "audiences": by_audience
    }

    output_path = output_dir / "by-audience.yaml"
    with open(output_path, "w") as f:
        yaml.dump(view, f, default_flow_style=False, sort_keys=False)
    print(f"  Wrote: {output_path}")


def run_aggregation(
    config: AggregatorConfig,
    work_dir: Path,
) -> List[dict]:
    """Run full aggregation pipeline.

    This is the main entry point for CLI integration.
    """
    print(f"Aggregating from {len(config.sources)} sources...")

    manifests = aggregate_manifests(config, work_dir)

    if not manifests:
        print("No manifests loaded")
        return []

    print(f"\nAggregated {len(manifests)} manifests")

    # Write individual manifests
    print("\nWriting manifests...")
    manifests_dir = config.output_dir / config.manifests_dir
    write_manifests(manifests, manifests_dir)

    # Generate views and indexes
    print("\nGenerating outputs...")

    if "full_index" in config.generate:
        generate_full_index(manifests, config.output_dir / config.generated_dir)

    if "by_category" in config.generate:
        generate_by_category_view(manifests, config.output_dir / config.views_dir)

    if "by_audience" in config.generate:
        generate_by_audience_view(manifests, config.output_dir / config.views_dir)

    print("\nDone!")
    return manifests
