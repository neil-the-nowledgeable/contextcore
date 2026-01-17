"""
Skill Capability Management

Store and query skill capabilities as OTel spans in Tempo,
enabling TraceQL-based capability discovery and token-efficient
agent-to-agent communication.
"""

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
from contextcore.skill.parser import SkillParser, parse_skill_directory

# Lazy imports for optional dependencies
def __getattr__(name):
    if name == "SkillCapabilityEmitter":
        from contextcore.skill.emitter import SkillCapabilityEmitter
        return SkillCapabilityEmitter
    elif name == "SkillCapabilityQuerier":
        from contextcore.skill.querier import SkillCapabilityQuerier
        return SkillCapabilityQuerier
    elif name == "SkillManifestQuerier":
        from contextcore.skill.querier import SkillManifestQuerier
        return SkillManifestQuerier
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Models
    "CapabilityCategory",
    "CapabilityEvidence",
    "CapabilityInput",
    "CapabilityOutput",
    "EvidenceType",
    "QuickAction",
    "SkillCapability",
    "SkillManifest",
    "SkillType",
    # Emitter (lazy)
    "SkillCapabilityEmitter",
    # Parser
    "SkillParser",
    "parse_skill_directory",
    # Querier (lazy)
    "SkillCapabilityQuerier",
    "SkillManifestQuerier",
]
