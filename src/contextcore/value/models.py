"""
Pydantic models for Value Capability management.

Value capabilities bridge technical capabilities to user benefits,
enabling discovery through value propositions rather than technical features.

Schema:
- value.type: direct, indirect, ripple
- value.persona: developer, operator, creator, etc.
- value.channel: slack, email, docs, in_app, social
- value.pain_point: Problem being solved
- value.benefit: Benefit provided

Cross-links to technical capabilities via related_skills attribute.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from contextcore.knowledge.models import (
    KnowledgeCapability,
    KnowledgeCategory,
    KnowledgeManifest,
)
from contextcore.skill.models import (
    Audience,
    CapabilityCategory,
    Evidence,
    SkillType,
)


class ValueType(str, Enum):
    """
    Classification of value by how directly it impacts the user.

    From capability-value-promoter's "Creator Value Framework":
    - Direct: Immediate, tangible time/effort savings
    - Indirect: Skills, confidence, portfolio growth over time
    - Ripple: Benefits that extend to others (team, family, community)
    """
    DIRECT = "direct"       # Time saved, cognitive load reduced, errors prevented
    INDIRECT = "indirect"   # Skills gained, confidence built, portfolio enhanced
    RIPPLE = "ripple"       # Benefits to others (team efficiency, family time, community impact)


class Persona(str, Enum):
    """
    Target audience persona for value propositions.

    Aligns with capability-value-promoter's audience profiles.
    """
    # Technical personas
    DEVELOPER = "developer"         # Software engineers, coders
    OPERATOR = "operator"           # DevOps, SRE, platform engineers
    ARCHITECT = "architect"         # System designers, tech leads
    # Creative personas
    CREATOR = "creator"             # Content creators, makers
    DESIGNER = "designer"           # UX/UI designers
    # Business personas
    MANAGER = "manager"             # Engineering managers, team leads
    EXECUTIVE = "executive"         # C-suite, directors
    PRODUCT = "product"             # Product managers, owners
    # Specialized personas
    SECURITY = "security"           # Security engineers, analysts
    DATA = "data"                   # Data engineers, scientists
    # Meta
    ANY = "any"                     # Universal applicability


class Channel(str, Enum):
    """
    Distribution channel for value messaging.

    From capability-value-promoter's channel adaptation patterns.
    """
    # Internal channels
    SLACK = "slack"             # Team chat (concise, informal)
    EMAIL = "email"             # Formal communication
    DOCS = "docs"               # Technical documentation
    IN_APP = "in_app"           # In-app messaging, tooltips
    MEETING = "meeting"         # Presentation, demo
    # External channels
    SOCIAL = "social"           # LinkedIn, Twitter
    BLOG = "blog"               # Blog posts, articles
    PRESS = "press"             # Press releases
    VIDEO = "video"             # YouTube, tutorials
    # Automated
    ALERT = "alert"             # Automated notifications
    CHANGELOG = "changelog"     # Release notes


class ValueAttribute(BaseModel):
    """
    Value-specific attributes for a capability.

    These attributes enable value-based discovery:
    - Query by persona: "What capabilities help developers?"
    - Query by pain point: "What solves cognitive overload?"
    - Query by benefit: "What provides time savings?"
    """

    # Value Type Classification
    value_type: ValueType = Field(
        default=ValueType.DIRECT,
        description="How directly the value impacts the user"
    )

    # Target Persona
    personas: List[Persona] = Field(
        default_factory=lambda: [Persona.ANY],
        description="Target audience personas"
    )
    primary_persona: Optional[Persona] = Field(
        None,
        description="Primary target persona (derived from personas[0] if not set)"
    )

    # Pain Point / Problem
    pain_point: str = Field(
        ...,
        max_length=200,
        description="The problem or pain being solved"
    )
    pain_point_category: Optional[str] = Field(
        None,
        description="Category of pain (time, cognitive_load, errors, coordination)"
    )

    # Benefit / Solution
    benefit: str = Field(
        ...,
        max_length=200,
        description="The benefit provided to the user"
    )
    benefit_metric: Optional[str] = Field(
        None,
        description="Quantifiable metric for the benefit (e.g., '10x faster', '50% less errors')"
    )

    # Channel Adaptation
    channels: List[Channel] = Field(
        default_factory=lambda: [Channel.DOCS],
        description="Channels this value proposition is adapted for"
    )
    primary_channel: Optional[Channel] = Field(
        None,
        description="Primary distribution channel"
    )

    # Value Dimensions (for nuanced discovery)
    time_savings: Optional[str] = Field(
        None,
        description="Time savings estimate (e.g., '2-4 hours/week')"
    )
    cognitive_load_reduction: Optional[str] = Field(
        None,
        description="How it reduces cognitive load"
    )
    error_prevention: Optional[str] = Field(
        None,
        description="What errors it prevents"
    )

    # Creator-specific value (Audience of 1 mode)
    creator_direct_value: Optional[str] = Field(
        None,
        description="Direct value for creators (time, cognitive load)"
    )
    creator_indirect_value: Optional[str] = Field(
        None,
        description="Indirect value for creators (skills, confidence)"
    )
    creator_ripple_value: Optional[str] = Field(
        None,
        description="Ripple effects (family, friends, community)"
    )

    def get_primary_persona(self) -> Persona:
        """Get primary persona, defaulting to first in list."""
        if self.primary_persona:
            return self.primary_persona
        return self.personas[0] if self.personas else Persona.ANY

    def get_primary_channel(self) -> Channel:
        """Get primary channel, defaulting to first in list."""
        if self.primary_channel:
            return self.primary_channel
        return self.channels[0] if self.channels else Channel.DOCS

    class Config:
        use_enum_values = True


class ValueCapability(KnowledgeCapability):
    """
    A value-focused capability stored as an OTel span.

    Extends KnowledgeCapability with value-specific attributes,
    enabling discovery through value propositions:

    TraceQL Examples:
        # Find capabilities for developers
        { value.persona = "developer" }

        # Find capabilities that reduce cognitive load
        { value.pain_point =~ ".*cognitive.*" }

        # Find direct value with time savings
        { value.type = "direct" && value.time_savings != "" }

        # Cross-link to technical capabilities
        { name =~ "value_capability" && related_skills =~ ".*dev-tour-guide.*" }

    Example:
        cap = ValueCapability(
            skill_id="capability-value-promoter",
            capability_id="persona_mapping",
            capability_name="Persona Mapping",
            category=CapabilityCategory.TRANSFORM,
            knowledge_category=KnowledgeCategory.PERSONA,
            summary="Map technical capabilities to audience-specific value propositions",
            triggers=["persona", "audience", "user", "value"],
            source_section="Audience Profiles",
            line_range="100-150",
            value=ValueAttribute(
                value_type=ValueType.DIRECT,
                personas=[Persona.CREATOR, Persona.DEVELOPER],
                pain_point="Difficult to articulate capability value to different audiences",
                benefit="Instantly generate persona-specific value messaging",
                channels=[Channel.SLACK, Channel.DOCS, Channel.EMAIL],
                time_savings="30+ minutes per capability",
            ),
            related_skills=["dev-tour-guide", "channel-adapter"],
            token_budget=300,
        )
    """

    # Value-specific attributes
    value: ValueAttribute = Field(
        ...,
        description="Value-specific attributes for discovery"
    )

    # Cross-linking to technical capabilities
    related_skills: List[str] = Field(
        default_factory=list,
        description="Skills that this value capability relates to"
    )
    related_capabilities: List[str] = Field(
        default_factory=list,
        description="Specific capability IDs this value capability describes"
    )

    # Value proposition messaging (pre-generated for channels)
    slack_message: Optional[str] = Field(
        None,
        max_length=280,
        description="Pre-adapted Slack message"
    )
    email_subject: Optional[str] = Field(
        None,
        max_length=100,
        description="Pre-adapted email subject"
    )
    one_liner: Optional[str] = Field(
        None,
        max_length=100,
        description="One-line value proposition"
    )

    # Discovery optimization
    value_keywords: List[str] = Field(
        default_factory=list,
        description="Additional keywords for value-based discovery"
    )

    class Config:
        use_enum_values = True


class ValueManifest(KnowledgeManifest):
    """
    Extended manifest for value-focused skill documents.

    Adds aggregate value metrics and cross-references.
    """

    # Value aggregates
    total_value_capabilities: int = Field(
        default=0,
        description="Count of value capabilities"
    )
    personas_covered: List[str] = Field(
        default_factory=list,
        description="Personas covered by this manifest"
    )
    channels_supported: List[str] = Field(
        default_factory=list,
        description="Channels supported by this manifest"
    )

    # Cross-references
    related_technical_skills: List[str] = Field(
        default_factory=list,
        description="Technical skills this value manifest relates to"
    )

    class Config:
        use_enum_values = True


# =============================================================================
# Helper Functions
# =============================================================================


def derive_value_type(
    has_time_savings: bool = False,
    has_skill_building: bool = False,
    has_ripple_effect: bool = False,
) -> ValueType:
    """
    Derive value type from content indicators.

    Priority: ripple > indirect > direct
    (ripple implies both indirect and direct)
    """
    if has_ripple_effect:
        return ValueType.RIPPLE
    if has_skill_building:
        return ValueType.INDIRECT
    return ValueType.DIRECT


def get_persona_from_context(context: str) -> Persona:
    """
    Infer persona from context string.

    Used during parsing to auto-classify capabilities.
    """
    context_lower = context.lower()

    # Check for specific persona keywords
    persona_keywords = {
        Persona.DEVELOPER: ["developer", "engineer", "coder", "programming", "code"],
        Persona.OPERATOR: ["devops", "sre", "operator", "platform", "infrastructure"],
        Persona.ARCHITECT: ["architect", "design", "system", "tech lead"],
        Persona.CREATOR: ["creator", "maker", "builder", "artist"],
        Persona.DESIGNER: ["designer", "ux", "ui", "visual"],
        Persona.MANAGER: ["manager", "lead", "team", "management"],
        Persona.EXECUTIVE: ["executive", "cto", "ceo", "director", "vp"],
        Persona.PRODUCT: ["product", "pm", "roadmap", "feature"],
        Persona.SECURITY: ["security", "infosec", "compliance", "audit"],
        Persona.DATA: ["data", "analytics", "ml", "ai", "scientist"],
    }

    for persona, keywords in persona_keywords.items():
        if any(kw in context_lower for kw in keywords):
            return persona

    return Persona.ANY


def get_channel_from_context(context: str) -> Channel:
    """
    Infer channel from context string.
    """
    context_lower = context.lower()

    channel_keywords = {
        Channel.SLACK: ["slack", "chat", "message", "dm"],
        Channel.EMAIL: ["email", "mail", "newsletter"],
        Channel.DOCS: ["documentation", "docs", "readme", "guide"],
        Channel.IN_APP: ["in-app", "tooltip", "onboarding", "notification"],
        Channel.SOCIAL: ["linkedin", "twitter", "social", "post"],
        Channel.BLOG: ["blog", "article", "medium"],
        Channel.PRESS: ["press", "pr", "announcement", "release"],
        Channel.VIDEO: ["video", "youtube", "tutorial", "demo"],
        Channel.ALERT: ["alert", "pagerduty", "oncall"],
        Channel.CHANGELOG: ["changelog", "release notes", "what's new"],
        Channel.MEETING: ["meeting", "presentation", "slides"],
    }

    for channel, keywords in channel_keywords.items():
        if any(kw in context_lower for kw in keywords):
            return channel

    return Channel.DOCS
