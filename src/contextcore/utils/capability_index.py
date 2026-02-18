"""
Capability index loader for pipeline-aware init and export commands.

Loads structured capability index YAML from docs/capability-index/ and provides
deterministic trigger/pattern/principle matching for manifest enrichment.

Used by:
- contextcore manifest init (REQ-CAP-002)
- contextcore manifest init-from-plan (REQ-CAP-003)
- contextcore manifest export (REQ-CAP-005, REQ-CAP-006, REQ-CAP-007)
- run provenance (REQ-CAP-009)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_cache: Dict[str, "CapabilityIndex"] = {}


@dataclass
class Principle:
    id: str
    principle: str
    rationale: str = ""
    anti_patterns: List[str] = field(default_factory=list)
    applies_to: List[str] = field(default_factory=list)


@dataclass
class Pattern:
    pattern_id: str
    name: str
    summary: str
    capabilities: List[str] = field(default_factory=list)
    anti_pattern: str = ""


@dataclass
class Capability:
    capability_id: str
    category: str = ""
    maturity: str = ""
    summary: str = ""
    triggers: List[str] = field(default_factory=list)
    discovery_paths: List[str] = field(default_factory=list)


@dataclass
class Benefit:
    benefit_id: str
    category: str = ""
    summary: str = ""


@dataclass
class CapabilityIndex:
    version: str = ""
    principles: List[Principle] = field(default_factory=list)
    patterns: List[Pattern] = field(default_factory=list)
    capabilities: List[Capability] = field(default_factory=list)
    benefits: List[Benefit] = field(default_factory=list)
    source_path: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.capabilities and not self.principles


def load_capability_index(index_dir: Path) -> CapabilityIndex:
    """Load capability index from a directory of YAML files.

    Loads ``contextcore.agent.yaml`` for capabilities, principles, and patterns,
    and ``contextcore.benefits.yaml`` for benefits.  Results are cached by
    resolved directory path.

    Falls back to an empty :class:`CapabilityIndex` on any error.
    """
    resolved = str(index_dir.resolve())
    if resolved in _cache:
        return _cache[resolved]

    index = CapabilityIndex(source_path=resolved)

    if not index_dir.is_dir():
        logger.debug("Capability index directory not found: %s", index_dir)
        _cache[resolved] = index
        return index

    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not available, skipping capability index load")
        _cache[resolved] = index
        return index

    # Load agent manifest (capabilities, principles, patterns)
    agent_path = index_dir / "contextcore.agent.yaml"
    if agent_path.is_file():
        try:
            with open(agent_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            index.version = str(data.get("version", ""))

            # Parse capabilities (first 100 for trigger matching)
            for cap_data in (data.get("capabilities") or [])[:100]:
                if not isinstance(cap_data, dict):
                    continue
                index.capabilities.append(Capability(
                    capability_id=cap_data.get("capability_id", ""),
                    category=cap_data.get("category", ""),
                    maturity=cap_data.get("maturity", ""),
                    summary=cap_data.get("summary", ""),
                    triggers=cap_data.get("triggers") or [],
                    discovery_paths=cap_data.get("discovery_paths") or [],
                ))

            # Parse design_principles (may not exist in pre-enhancement YAML)
            for prin_data in (data.get("design_principles") or []):
                if not isinstance(prin_data, dict):
                    continue
                index.principles.append(Principle(
                    id=prin_data.get("id", ""),
                    principle=prin_data.get("principle", ""),
                    rationale=prin_data.get("rationale", ""),
                    anti_patterns=prin_data.get("anti_patterns") or [],
                    applies_to=prin_data.get("applies_to") or [],
                ))

            # Parse patterns (may not exist in pre-enhancement YAML)
            for pat_data in (data.get("patterns") or []):
                if not isinstance(pat_data, dict):
                    continue
                index.patterns.append(Pattern(
                    pattern_id=pat_data.get("pattern_id", ""),
                    name=pat_data.get("name", ""),
                    summary=pat_data.get("summary", ""),
                    capabilities=pat_data.get("capabilities") or [],
                    anti_pattern=pat_data.get("anti_pattern", ""),
                ))

        except Exception:
            logger.debug("Failed to parse %s", agent_path, exc_info=True)

    # Load benefits manifest
    benefits_path = index_dir / "contextcore.benefits.yaml"
    if benefits_path.is_file():
        try:
            with open(benefits_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for ben_data in (data.get("benefits") or []):
                if not isinstance(ben_data, dict):
                    continue
                index.benefits.append(Benefit(
                    benefit_id=ben_data.get("benefit_id", ""),
                    category=ben_data.get("category", ""),
                    summary=ben_data.get("summary", ""),
                ))
        except Exception:
            logger.debug("Failed to parse %s", benefits_path, exc_info=True)

    _cache[resolved] = index
    return index


def match_triggers(text: str, capabilities: List[Capability]) -> List[Capability]:
    """Return capabilities whose triggers match substrings in *text*.

    Matching is case-insensitive.  Each capability appears at most once.
    """
    lowered = text.lower()
    matched: List[Capability] = []
    seen: set[str] = set()
    for cap in capabilities:
        if cap.capability_id in seen:
            continue
        for trigger in cap.triggers:
            if trigger.lower() in lowered:
                matched.append(cap)
                seen.add(cap.capability_id)
                break
    return matched


def match_patterns(
    capability_ids: List[str], patterns: List[Pattern]
) -> List[Pattern]:
    """Return patterns whose capabilities list overlaps with *capability_ids*."""
    id_set = set(capability_ids)
    return [p for p in patterns if id_set & set(p.capabilities)]


def match_principles(
    capability_ids: List[str], principles: List[Principle]
) -> List[Principle]:
    """Return principles whose applies_to list overlaps with *capability_ids*."""
    id_set = set(capability_ids)
    return [p for p in principles if id_set & set(p.applies_to)]


def discover_expansion_pack_metrics(index: CapabilityIndex) -> Dict[str, List[str]]:
    """Discover expansion pack metrics from capability index.

    Looks for capabilities whose capability_id starts with known expansion pack
    prefixes and whose triggers mention metrics. Returns a dict mapping pack
    name to list of metric names.

    Falls back to empty dict if no metrics found.

    REQ-CAP-007: Capability-derived expansion pack metrics.
    """
    # Known expansion pack prefixes
    pack_prefixes = {
        "startd8.": "beaver",
        "contextcore.beaver.": "beaver",
    }

    metrics: Dict[str, List[str]] = {}

    for cap in index.capabilities:
        for prefix, pack_name in pack_prefixes.items():
            if cap.capability_id.startswith(prefix):
                # Check triggers for metric-related keywords
                for trigger in cap.triggers:
                    trigger_lower = trigger.lower()
                    if any(kw in trigger_lower for kw in ("metric", "cost", "token", "usage")):
                        # This capability is metric-related
                        if pack_name not in metrics:
                            metrics[pack_name] = []
                        # Extract metric name from capability_id
                        metric_name = cap.capability_id.replace(".", "_")
                        if metric_name not in metrics[pack_name]:
                            metrics[pack_name].append(metric_name)
                        break

    return metrics


def clear_cache() -> None:
    """Clear the module-level capability index cache."""
    _cache.clear()
