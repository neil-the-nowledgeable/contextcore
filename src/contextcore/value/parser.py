"""
Value Capability Parser.

Parses value-focused SKILL.md files (like capability-value-promoter)
into structured ValueCapability objects for OTel emission.

Extends the MarkdownCapabilityParser pattern with value-specific extraction:
- Pain points and benefits
- Persona detection
- Channel adaptation
- Value type classification (direct, indirect, ripple)
- Cross-linking to technical capabilities
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from contextcore.skill.models import (
    Audience,
    CapabilityCategory,
    Evidence,
    EvidenceType,
    SkillType,
)
from contextcore.knowledge.models import (
    KnowledgeCategory,
    Section,
    get_knowledge_category,
)
from contextcore.knowledge.md_parser import (
    MarkdownCapabilityParser,
    estimate_tokens,
    slugify,
    compress_to_summary,
    STOP_WORDS,
)
from contextcore.value.models import (
    Channel,
    Persona,
    ValueAttribute,
    ValueCapability,
    ValueManifest,
    ValueType,
    get_persona_from_context,
    get_channel_from_context,
)


# Keywords that indicate different value types
VALUE_TYPE_INDICATORS = {
    ValueType.DIRECT: [
        "time saved", "hours saved", "minutes saved",
        "faster", "quicker", "immediate",
        "eliminate", "automate", "reduce",
        "no longer need", "don't have to",
        "cognitive load", "mental space",
        "fewer errors", "prevent errors",
    ],
    ValueType.INDIRECT: [
        "skills", "learn", "expertise",
        "confidence", "capability", "ability",
        "portfolio", "demonstrate", "showcase",
        "satisfaction", "craft", "mastery",
    ],
    ValueType.RIPPLE: [
        "family", "friends", "colleagues",
        "community", "open source", "shared",
        "team", "organization", "others",
        "enable", "help others", "knowledge transfer",
    ],
}

# Keywords for pain point detection
PAIN_POINT_INDICATORS = [
    "pain", "problem", "struggle", "frustrat",
    "difficult", "challenge", "issue",
    "time-consuming", "manual", "tedious",
    "error-prone", "confusing", "complex",
    "tired of", "waste", "inefficient",
]

# Keywords for benefit detection
BENEFIT_INDICATORS = [
    "benefit", "advantage", "value",
    "save", "gain", "improve",
    "faster", "easier", "simpler",
    "automat", "eliminate", "reduce",
    "unlock", "enable", "achieve",
]


class ValueCapabilityParser(MarkdownCapabilityParser):
    """
    Parse value-focused SKILL.md files into ValueCapabilities.

    Extends MarkdownCapabilityParser with:
    - Value type detection (direct, indirect, ripple)
    - Persona extraction
    - Pain point / benefit extraction
    - Channel adaptation detection
    - Cross-linking to technical capabilities

    Example:
        parser = ValueCapabilityParser(Path("~/.claude/skills/capability-value-promoter"))
        manifest, capabilities = parser.parse()

        # Query by value type
        direct_caps = [c for c in capabilities if c.value.value_type == ValueType.DIRECT]

        # Query by persona
        dev_caps = [c for c in capabilities if Persona.DEVELOPER in c.value.personas]
    """

    def parse(self) -> tuple[ValueManifest, list[ValueCapability]]:
        """
        Parse markdown into manifest and value capabilities.

        Returns:
            Tuple of (ValueManifest, list of ValueCapability)
        """
        # 1. Extract YAML frontmatter
        frontmatter, content_start = self._extract_frontmatter()

        # 2. Build section tree (H2 -> H3 hierarchy)
        sections = self._build_section_tree(content_start)

        # 3. Extract value capabilities using hybrid rules
        capabilities = []
        capability_refs = []
        personas_covered = set()
        channels_supported = set()

        for section in sections:
            # Major section capability
            cap = self._extract_value_capability(section)
            capabilities.append(cap)
            capability_refs.append(cap.capability_id)
            personas_covered.update(cap.value.personas)
            channels_supported.update(cap.value.channels)

            # Check subsections
            for subsection in section.subsections:
                if self._should_extract_subsection(subsection):
                    sub_cap = self._extract_value_capability(
                        subsection,
                        parent_section=section.heading
                    )
                    capabilities.append(sub_cap)
                    capability_refs.append(sub_cap.capability_id)
                    personas_covered.update(sub_cap.value.personas)
                    channels_supported.update(sub_cap.value.channels)

        # 4. Build manifest
        manifest = self._build_value_manifest(
            frontmatter=frontmatter,
            capability_refs=capability_refs,
            sections=sections,
            personas_covered=list(personas_covered),
            channels_supported=list(channels_supported),
        )

        return manifest, capabilities

    def _extract_value_capability(
        self,
        section: Section,
        parent_section: Optional[str] = None,
    ) -> ValueCapability:
        """
        Extract value capability from a section.

        Extends base extraction with value-specific attributes.
        """
        # Generate capability ID
        if parent_section:
            cap_id = slugify(f"{parent_section}_{section.heading}")[:50]
        else:
            cap_id = slugify(section.heading)[:50]

        # Determine categories
        source_section = parent_section or section.heading
        knowledge_cat = get_knowledge_category(source_section)

        # Map to capability category
        category_map = {
            KnowledgeCategory.VALUE_PROPOSITION: CapabilityCategory.TRANSFORM,
            KnowledgeCategory.MESSAGING: CapabilityCategory.GENERATE,
            KnowledgeCategory.PERSONA: CapabilityCategory.ANALYZE,
            KnowledgeCategory.CHANNEL: CapabilityCategory.TRANSFORM,
            # Fall back to base categories
            KnowledgeCategory.INFRASTRUCTURE: CapabilityCategory.QUERY,
            KnowledgeCategory.WORKFLOW: CapabilityCategory.ACTION,
            KnowledgeCategory.SDK: CapabilityCategory.ACTION,
            KnowledgeCategory.REFERENCE: CapabilityCategory.QUERY,
            KnowledgeCategory.SECURITY: CapabilityCategory.ACTION,
            KnowledgeCategory.CONFIGURATION: CapabilityCategory.VALIDATE,
        }
        capability_cat = category_map.get(knowledge_cat, CapabilityCategory.QUERY)

        # Extract triggers (including value-specific keywords)
        triggers = self._extract_value_triggers(section)

        # Generate summary
        summary = compress_to_summary(section.content)

        # Extract value-specific attributes
        value_attr = self._extract_value_attributes(section)

        # Extract references
        tools = self._extract_tools(section.content)
        ports = self._extract_ports(section.content)
        env_vars = self._extract_env_vars(section.content)
        paths = self._extract_paths(section.content)
        related_skills = self._extract_skill_refs(section.content)
        related_capabilities = self._extract_capability_refs(section.content)

        # Build evidence
        evidence = [
            Evidence(
                type=EvidenceType.DOC.value,
                ref=str(self.skill_file),
                description=f"Lines {section.start_line}-{section.end_line}: {section.heading}",
                tokens=estimate_tokens(section.content),
            )
        ]

        # Token budget
        token_budget = estimate_tokens(section.content)
        summary_tokens = estimate_tokens(summary)

        # Generate channel-specific messaging
        slack_message = self._generate_slack_message(summary, value_attr)
        one_liner = self._generate_one_liner(section.heading, value_attr)

        return ValueCapability(
            skill_id=self.skill_id,
            skill_type=SkillType.SPECIALIST,
            capability_id=cap_id,
            capability_name=section.heading,
            category=capability_cat,
            knowledge_category=knowledge_cat,
            summary=summary,
            triggers=triggers,
            source_section=source_section,
            source_subsection=section.heading if parent_section else None,
            line_range=f"{section.start_line}-{section.end_line}",
            has_code=section.has_code_blocks,
            has_tables=section.has_tables,
            code_block_count=section.code_block_count,
            tools=tools,
            ports=ports,
            env_vars=env_vars,
            paths=paths,
            related_skills=related_skills,
            related_sections=[],
            evidence=evidence,
            token_budget=token_budget,
            summary_tokens=summary_tokens,
            confidence=0.9,
            interop_human=4,
            interop_agent=5,
            audience=Audience.BOTH,
            # Value-specific attributes
            value=value_attr,
            related_capabilities=related_capabilities,
            slack_message=slack_message,
            one_liner=one_liner,
            value_keywords=self._extract_value_keywords(section),
        )

    def _extract_value_attributes(self, section: Section) -> ValueAttribute:
        """
        Extract value-specific attributes from section content.
        """
        content = section.content
        content_lower = content.lower()

        # Determine value type
        value_type = self._detect_value_type(content_lower)

        # Extract personas
        personas = self._extract_personas(content)

        # Extract pain point and benefit
        pain_point = self._extract_pain_point(content)
        benefit = self._extract_benefit(content)

        # Extract channels
        channels = self._extract_channels(content)

        # Extract value dimensions
        time_savings = self._extract_time_savings(content)
        cognitive_load = self._extract_cognitive_load(content)
        error_prevention = self._extract_error_prevention(content)

        # Extract creator value (for Audience of 1 sections)
        creator_direct = None
        creator_indirect = None
        creator_ripple = None

        if "audience of 1" in content_lower or "creator" in content_lower:
            creator_direct = self._extract_creator_direct_value(content)
            creator_indirect = self._extract_creator_indirect_value(content)
            creator_ripple = self._extract_creator_ripple_value(content)

        return ValueAttribute(
            value_type=value_type,
            personas=personas,
            pain_point=pain_point,
            benefit=benefit,
            channels=channels,
            time_savings=time_savings,
            cognitive_load_reduction=cognitive_load,
            error_prevention=error_prevention,
            creator_direct_value=creator_direct,
            creator_indirect_value=creator_indirect,
            creator_ripple_value=creator_ripple,
        )

    def _detect_value_type(self, content_lower: str) -> ValueType:
        """
        Detect primary value type from content.

        Priority: ripple > indirect > direct
        """
        scores = {
            ValueType.DIRECT: 0,
            ValueType.INDIRECT: 0,
            ValueType.RIPPLE: 0,
        }

        for value_type, indicators in VALUE_TYPE_INDICATORS.items():
            for indicator in indicators:
                if indicator in content_lower:
                    scores[value_type] += 1

        # Return highest scoring, with ripple as tiebreaker
        if scores[ValueType.RIPPLE] > 0 and scores[ValueType.RIPPLE] >= max(scores.values()) - 1:
            return ValueType.RIPPLE
        if scores[ValueType.INDIRECT] > scores[ValueType.DIRECT]:
            return ValueType.INDIRECT
        return ValueType.DIRECT

    def _extract_personas(self, content: str) -> list[Persona]:
        """Extract target personas from content."""
        personas = set()
        content_lower = content.lower()

        # Check for persona keywords
        persona_keywords = {
            Persona.DEVELOPER: ["developer", "engineer", "coder", "programmer"],
            Persona.OPERATOR: ["devops", "sre", "ops", "platform", "infrastructure"],
            Persona.ARCHITECT: ["architect", "tech lead", "system design"],
            Persona.CREATOR: ["creator", "maker", "builder"],
            Persona.DESIGNER: ["designer", "ux", "ui"],
            Persona.MANAGER: ["manager", "lead", "team lead", "eng manager"],
            Persona.EXECUTIVE: ["cto", "ceo", "director", "executive", "vp"],
            Persona.PRODUCT: ["product manager", "pm", "product owner"],
            Persona.SECURITY: ["security", "infosec", "compliance"],
            Persona.DATA: ["data engineer", "data scientist", "analyst"],
        }

        for persona, keywords in persona_keywords.items():
            for keyword in keywords:
                if keyword in content_lower:
                    personas.add(persona)
                    break

        # Default to ANY if no specific personas found
        if not personas:
            personas.add(Persona.ANY)

        return list(personas)

    def _extract_pain_point(self, content: str) -> str:
        """Extract primary pain point from content."""
        lines = content.split('\n')

        # Look for explicit pain point patterns
        patterns = [
            r"pain[_\s]*point[s]?\s*[:=]\s*[\"']?([^\"'\n]+)",
            r"problem\s*[:=]\s*[\"']?([^\"'\n]+)",
            r"the\s+problem\s*[:=]?\s*[\"']?([^\"'\n]+)",
            r"challenge[s]?\s*[:=]\s*[\"']?([^\"'\n]+)",
            r"frustrat\w+\s+(?:with|by|about)\s*[\"']?([^\"'\n]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:200]

        # Look for lines with pain point indicators
        for line in lines:
            line_lower = line.lower()
            for indicator in PAIN_POINT_INDICATORS:
                if indicator in line_lower:
                    cleaned = re.sub(r'^\s*[-*#]+\s*', '', line).strip()
                    if len(cleaned) > 20:
                        return cleaned[:200]

        # Fallback: infer from section heading
        return "Technical complexity and manual processes"

    def _extract_benefit(self, content: str) -> str:
        """Extract primary benefit from content."""
        lines = content.split('\n')

        # Look for explicit benefit patterns
        patterns = [
            r"benefit[s]?\s*[:=]\s*[\"']?([^\"'\n]+)",
            r"value\s*[:=]\s*[\"']?([^\"'\n]+)",
            r"solution\s*[:=]\s*[\"']?([^\"'\n]+)",
            r"the\s+solution\s*[:=]?\s*[\"']?([^\"'\n]+)",
            r"result[s]?\s+in\s+([^\"'\n]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:200]

        # Look for lines with benefit indicators
        for line in lines:
            line_lower = line.lower()
            for indicator in BENEFIT_INDICATORS:
                if indicator in line_lower:
                    cleaned = re.sub(r'^\s*[-*#]+\s*', '', line).strip()
                    if len(cleaned) > 20:
                        return cleaned[:200]

        # Fallback
        return "Streamlined workflow and improved efficiency"

    def _extract_channels(self, content: str) -> list[Channel]:
        """Extract target channels from content."""
        channels = set()
        content_lower = content.lower()

        channel_keywords = {
            Channel.SLACK: ["slack", "chat", "message"],
            Channel.EMAIL: ["email", "mail", "newsletter"],
            Channel.DOCS: ["documentation", "docs", "readme", "guide"],
            Channel.IN_APP: ["in-app", "tooltip", "onboarding"],
            Channel.SOCIAL: ["linkedin", "twitter", "social"],
            Channel.BLOG: ["blog", "article", "post"],
            Channel.PRESS: ["press", "release", "announcement"],
            Channel.VIDEO: ["video", "youtube", "tutorial"],
            Channel.ALERT: ["alert", "notification", "pagerduty"],
            Channel.CHANGELOG: ["changelog", "release notes"],
            Channel.MEETING: ["meeting", "presentation", "demo", "slides"],
        }

        for channel, keywords in channel_keywords.items():
            for keyword in keywords:
                if keyword in content_lower:
                    channels.add(channel)
                    break

        # Default to DOCS if no specific channels found
        if not channels:
            channels.add(Channel.DOCS)

        return list(channels)

    def _extract_time_savings(self, content: str) -> Optional[str]:
        """Extract time savings estimate from content."""
        patterns = [
            r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\s*(?:per|/)\s*(?:week|month|year)",
            r"(\d+)\s*(?:minutes?|mins?)\s*(?:per|/)\s*(?:use|task|operation)",
            r"save[s]?\s+(\d+(?:\.\d+)?)\s*(?:hours?|minutes?)",
            r"time[_\s]*saved[:]?\s*([^\n]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(0).strip()[:100]

        return None

    def _extract_cognitive_load(self, content: str) -> Optional[str]:
        """Extract cognitive load reduction description."""
        patterns = [
            r"cognitive[_\s]*load[_\s]*reduced?\s*[:=]?\s*([^\n]+)",
            r"no[_\s]*longer[_\s]*need[_\s]*to[:]?\s*([^\n]+)",
            r"don'?t[_\s]*have[_\s]*to[_\s]*remember\s*([^\n]+)",
            r"mental[_\s]*space\s*([^\n]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:150]

        return None

    def _extract_error_prevention(self, content: str) -> Optional[str]:
        """Extract error prevention description."""
        patterns = [
            r"error[s]?[_\s]*prevented?\s*[:=]?\s*([^\n]+)",
            r"prevent[s]?\s+([^\n]*error[^\n]*)",
            r"no[_\s]*more[_\s]*([^\n]*fail[^\n]*)",
            r"eliminate[sd]?\s+([^\n]*error[^\n]*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:150]

        return None

    def _extract_creator_direct_value(self, content: str) -> Optional[str]:
        """Extract direct value for creators (Audience of 1)."""
        pattern = r"direct[_\s]*value[:]?\s*([^\n]+(?:\n\s*[-*]\s*[^\n]+)*)"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:200]
        return None

    def _extract_creator_indirect_value(self, content: str) -> Optional[str]:
        """Extract indirect value for creators (Audience of 1)."""
        pattern = r"indirect[_\s]*value[:]?\s*([^\n]+(?:\n\s*[-*]\s*[^\n]+)*)"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:200]
        return None

    def _extract_creator_ripple_value(self, content: str) -> Optional[str]:
        """Extract ripple effects for creators (Audience of 1)."""
        patterns = [
            r"ripple[_\s]*(?:effect|value)[s]?[:]?\s*([^\n]+)",
            r"family[_\s]*value[:]?\s*([^\n]+)",
            r"community[_\s]*value[:]?\s*([^\n]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:200]
        return None

    def _extract_value_triggers(self, section: Section) -> list[str]:
        """Extract triggers including value-specific keywords."""
        # Start with base triggers
        triggers = set(self._extract_triggers(section))

        # Add value-specific keywords
        content_lower = section.content.lower()

        value_keywords = [
            "value", "benefit", "pain", "solution",
            "persona", "audience", "user", "customer",
            "channel", "messaging", "onboarding",
            "adoption", "engagement", "retention",
            "roi", "time saved", "efficiency",
        ]

        for kw in value_keywords:
            if kw in content_lower:
                triggers.add(kw.replace(" ", "_"))

        # Add persona triggers
        for persona in Persona:
            if persona.value in content_lower:
                triggers.add(f"persona_{persona.value}")

        # Add channel triggers
        for channel in Channel:
            if channel.value in content_lower:
                triggers.add(f"channel_{channel.value}")

        return sorted(list(triggers))[:25]

    def _extract_value_keywords(self, section: Section) -> list[str]:
        """Extract additional keywords for value-based discovery."""
        keywords = set()
        content_lower = section.content.lower()

        # Extract words near value indicators
        value_context_pattern = r"(\w+)\s+(?:value|benefit|pain|solution)\s+(\w+)"
        for match in re.finditer(value_context_pattern, content_lower):
            word1 = match.group(1)
            word2 = match.group(2)
            if word1 not in STOP_WORDS and len(word1) > 2:
                keywords.add(word1)
            if word2 not in STOP_WORDS and len(word2) > 2:
                keywords.add(word2)

        return sorted(list(keywords))[:15]

    def _extract_capability_refs(self, content: str) -> list[str]:
        """Extract references to specific capabilities."""
        refs = set()

        # Pattern: capability_id: xyz or capability: xyz
        patterns = [
            r"capability[_\s]*id[:\s]+[\"']?(\w+)[\"']?",
            r"capability[:\s]+[\"']?(\w+)[\"']?",
            r"references?\s+(?:the\s+)?[\"']?(\w+)[\"']?\s+capability",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                cap_id = match.group(1).lower()
                if cap_id not in ["this", "the", "a", "an"]:
                    refs.add(cap_id)

        return sorted(list(refs))

    def _generate_slack_message(self, summary: str, value: ValueAttribute) -> str:
        """Generate Slack-optimized message."""
        # Keep it under 280 chars for Slack
        if value.benefit:
            return f"💡 {value.benefit[:200]}"
        return f"💡 {summary[:200]}"

    def _generate_one_liner(self, heading: str, value: ValueAttribute) -> str:
        """Generate one-line value proposition."""
        if value.benefit and value.pain_point:
            return f"Solve '{value.pain_point[:40]}' with {heading}"[:100]
        return f"Unlock value with {heading}"[:100]

    def _build_value_manifest(
        self,
        frontmatter: dict,
        capability_refs: list[str],
        sections: list[Section],
        personas_covered: list[str],
        channels_supported: list[str],
    ) -> ValueManifest:
        """Build value manifest from parsed data."""
        # Extract from frontmatter
        name = frontmatter.get("name", self.skill_id)
        description = frontmatter.get("description", f"Value capabilities: {self.skill_id}")

        # Count subsections
        subsection_count = len(capability_refs) - len(sections)

        # Calculate token budgets
        total_tokens = estimate_tokens(self.content)
        manifest_tokens = 150
        compressed_tokens = sum(50 for _ in capability_refs)

        # Extract related technical skills from content
        related_technical = self._extract_skill_refs(self.content)

        return ValueManifest(
            skill_id=name,
            skill_type=SkillType.SPECIALIST,
            description=description,
            capability_refs=capability_refs,
            source_path=str(self.skill_path),
            source_file=str(self.skill_file),
            total_lines=len(self.lines),
            section_count=len(sections),
            subsection_count=subsection_count,
            has_frontmatter=bool(frontmatter),
            manifest_tokens=manifest_tokens,
            total_tokens=total_tokens,
            compressed_tokens=compressed_tokens,
            # Value-specific
            total_value_capabilities=len(capability_refs),
            personas_covered=personas_covered,
            channels_supported=channels_supported,
            related_technical_skills=related_technical,
        )
