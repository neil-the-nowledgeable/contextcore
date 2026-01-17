"""
Skill Parser

Parse MANIFEST.yaml and capability YAML files into SkillManifest
and SkillCapability models for emission to Tempo.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

from contextcore.skill.models import (
    CapabilityCategory,
    CapabilityEvidence,
    CapabilityInput,
    CapabilityOutput,
    EvidenceType,
    QuickAction,
    SkillCapability,
    SkillManifest,
    SkillType,
)


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Uses rough approximation of 1 token ≈ 4 characters.
    """
    return len(text) // 4


def extract_summary(description: str, max_sentences: int = 2) -> str:
    """
    Extract a 1-2 sentence summary from a longer description.

    Args:
        description: Full description text
        max_sentences: Maximum sentences to include

    Returns:
        Compressed summary
    """
    # Clean up whitespace
    description = " ".join(description.split())

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', description)

    # Take first N sentences
    summary_sentences = sentences[:max_sentences]
    summary = " ".join(summary_sentences)

    # Ensure it ends with punctuation
    if summary and summary[-1] not in ".!?":
        summary += "."

    return summary


def parse_token_annotation(text: str) -> int:
    """
    Extract token count from annotation like '# Token budget: ~400 tokens'.

    Args:
        text: Text containing token annotation

    Returns:
        Token count (0 if not found)
    """
    match = re.search(r'[Tt]oken[s]?\s*(?:budget|cost)?:?\s*~?(\d+)', text)
    if match:
        return int(match.group(1))
    return 0


class SkillParser:
    """
    Parse skill directories into models for Tempo emission.

    Parses MANIFEST.yaml and capability files, extracting:
    - Quick actions
    - Capability references
    - Token budgets
    - Summaries (compressed from descriptions)

    Example:
        parser = SkillParser()
        manifest, capabilities = parser.parse_skill_directory(
            "/path/to/llm-formatter"
        )

        # Emit to Tempo
        emitter = SkillCapabilityEmitter()
        emitter.emit_skill_with_capabilities(manifest, capabilities)
    """

    def __init__(self, compress: bool = True):
        """
        Initialize parser.

        Args:
            compress: Whether to compress descriptions to summaries
        """
        self.compress = compress

    def parse_skill_directory(
        self,
        path: str | Path,
    ) -> tuple[SkillManifest, list[SkillCapability]]:
        """
        Parse an entire skill directory.

        Args:
            path: Path to skill directory

        Returns:
            Tuple of (SkillManifest, list of SkillCapability)
        """
        path = Path(path)

        # Parse manifest
        manifest_path = path / "MANIFEST.yaml"
        if not manifest_path.exists():
            raise FileNotFoundError(f"MANIFEST.yaml not found in {path}")

        manifest = self.parse_manifest(manifest_path)
        manifest.source_path = str(path)

        # Parse capabilities
        capabilities = []
        capabilities_dir = path / "agent" / "capabilities"

        if capabilities_dir.exists():
            for cap_file in capabilities_dir.glob("*.yaml"):
                try:
                    capability = self.parse_capability_file(cap_file, manifest.skill_id)
                    capabilities.append(capability)
                except Exception as e:
                    # Log but continue parsing other capabilities
                    print(f"Warning: Failed to parse {cap_file}: {e}")

        # Update manifest with capability refs and token counts
        manifest.capability_refs = [c.capability_id for c in capabilities]
        manifest.total_tokens = sum(c.token_budget for c in capabilities)
        manifest.compressed_tokens = sum(c.summary_tokens for c in capabilities)

        return manifest, capabilities

    def parse_manifest(self, path: str | Path) -> SkillManifest:
        """
        Parse MANIFEST.yaml into SkillManifest model.

        Args:
            path: Path to MANIFEST.yaml

        Returns:
            SkillManifest model
        """
        path = Path(path)
        content = path.read_text()
        data = yaml.safe_load(content)

        # Extract token budget from file content
        manifest_tokens = parse_token_annotation(content) or 150

        # Parse quick actions
        quick_actions = []
        if "quick_actions" in data:
            for name, qa_data in data["quick_actions"].items():
                quick_actions.append(QuickAction(
                    name=name,
                    capability_id=qa_data.get("capability", ""),
                    description=qa_data.get("description", ""),
                ))

        # Parse capability refs
        capability_refs = []
        if "capabilities" in data:
            for cap in data["capabilities"]:
                if isinstance(cap, dict) and "id" in cap:
                    capability_refs.append(cap["id"])
                elif isinstance(cap, str):
                    capability_refs.append(cap)

        # Parse constraints
        constraints = []
        if "constraints" in data:
            for c in data["constraints"]:
                if isinstance(c, dict) and "rule" in c:
                    constraints.append(c["rule"])
                elif isinstance(c, str):
                    constraints.append(c)

        # Map skill type
        skill_type_str = data.get("skill_type", "utility")
        skill_type = SkillType(skill_type_str) if skill_type_str in SkillType._value2member_map_ else SkillType.UTILITY

        # Build description from defaults or generate one
        description = ""
        if "defaults" in data:
            defaults = data["defaults"]
            if isinstance(defaults, dict):
                description = f"Skill for {', '.join(defaults.keys())}"

        return SkillManifest(
            skill_id=data.get("skill_id", path.parent.name),
            skill_type=skill_type,
            version=data.get("schema_version", "2.0"),
            description=description or f"Skill: {data.get('skill_id', path.parent.name)}",
            quick_actions=quick_actions,
            capability_refs=capability_refs,
            constraints=constraints,
            manifest_tokens=manifest_tokens,
        )

    def parse_capability_file(
        self,
        path: str | Path,
        skill_id: str,
    ) -> SkillCapability:
        """
        Parse a capability YAML file into SkillCapability model.

        Args:
            path: Path to capability YAML file
            skill_id: Parent skill ID

        Returns:
            SkillCapability model
        """
        path = Path(path)
        content = path.read_text()
        data = yaml.safe_load(content)

        # Get capability block (may be nested under 'capability' key)
        cap_data = data.get("capability", data)

        # Extract token budget from file content
        token_budget = parse_token_annotation(content) or estimate_tokens(content)

        # Parse description and extract summary
        description = cap_data.get("description", "")
        if self.compress:
            summary = extract_summary(description)
        else:
            summary = description

        summary_tokens = estimate_tokens(summary)

        # Parse category
        category_str = cap_data.get("category", "action")
        category = CapabilityCategory(category_str) if category_str in CapabilityCategory._value2member_map_ else CapabilityCategory.ACTION

        # Parse triggers
        triggers = cap_data.get("triggers", [])

        # Parse inputs
        inputs = []
        if "inputs" in cap_data:
            for name, inp_data in cap_data["inputs"].items():
                if isinstance(inp_data, dict):
                    inputs.append(CapabilityInput(
                        name=name,
                        type=inp_data.get("type", "string"),
                        required=inp_data.get("required", False),
                        default=str(inp_data.get("default", "")) if inp_data.get("default") else None,
                        enum_values=inp_data.get("values"),
                        description=inp_data.get("description", ""),
                    ))

        # Parse outputs
        outputs = []
        if "outputs" in cap_data:
            for name, out_data in cap_data["outputs"].items():
                if isinstance(out_data, dict):
                    outputs.append(CapabilityOutput(
                        name=name,
                        type=out_data.get("type", "string"),
                        description=out_data.get("description", ""),
                    ))

        # Parse anti-patterns
        anti_patterns = []
        if "anti_patterns" in cap_data:
            for ap in cap_data["anti_patterns"]:
                if isinstance(ap, dict) and "pattern" in ap:
                    anti_patterns.append(ap["pattern"])
                elif isinstance(ap, str):
                    anti_patterns.append(ap)

        # Parse interop scores
        interop = cap_data.get("interop_score", {})
        interop_human = interop.get("human", 4)
        interop_agent = interop.get("agent", 5)

        # Create evidence references
        evidence = [
            CapabilityEvidence(
                type=EvidenceType.FILE,
                ref=str(path.relative_to(path.parent.parent.parent)),
                description=f"Full capability schema for {cap_data.get('id', path.stem)}",
                tokens=token_budget,
            )
        ]

        # Add template reference if invocation exists
        if "invocation" in cap_data and "template" in cap_data["invocation"]:
            evidence.append(CapabilityEvidence(
                type=EvidenceType.TEMPLATE,
                ref=f"invocation.template",
                description="Invocation template",
                tokens=estimate_tokens(cap_data["invocation"]["template"]),
            ))

        return SkillCapability(
            skill_id=skill_id,
            capability_id=cap_data.get("id", path.stem),
            capability_name=cap_data.get("name", cap_data.get("id", path.stem)),
            category=category,
            triggers=triggers,
            summary=summary,
            summary_tokens=summary_tokens,
            token_budget=token_budget,
            evidence=evidence,
            inputs=inputs,
            outputs=outputs,
            anti_patterns=anti_patterns,
            interop_human=interop_human,
            interop_agent=interop_agent,
        )


def parse_skill_directory(path: str | Path) -> tuple[SkillManifest, list[SkillCapability]]:
    """
    Convenience function to parse a skill directory.

    Args:
        path: Path to skill directory

    Returns:
        Tuple of (SkillManifest, list of SkillCapability)
    """
    parser = SkillParser()
    return parser.parse_skill_directory(path)
