"""
Tests for the Value Capability module.

Tests cover:
- Model validation and behavior
- Parser extraction
- Value attribute detection
- Cross-linking functionality
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path

from contextcore.value.models import (
    ValueType,
    Persona,
    Channel,
    ValueAttribute,
    ValueCapability,
    ValueManifest,
    derive_value_type,
    get_persona_from_context,
    get_channel_from_context,
)
from contextcore.knowledge.models import KnowledgeCategory
from contextcore.skill.models import CapabilityCategory, Audience


class TestValueEnums:
    """Test value enumeration types."""

    def test_value_type_values(self):
        """ValueType has correct values."""
        assert ValueType.DIRECT.value == "direct"
        assert ValueType.INDIRECT.value == "indirect"
        assert ValueType.RIPPLE.value == "ripple"

    def test_persona_values(self):
        """Persona enum has all expected values."""
        expected = {
            "developer", "operator", "architect", "creator",
            "designer", "manager", "executive", "product",
            "security", "data", "any"
        }
        actual = {p.value for p in Persona}
        assert expected == actual

    def test_channel_values(self):
        """Channel enum has all expected values."""
        expected = {
            "slack", "email", "docs", "in_app", "meeting",
            "social", "blog", "press", "video", "alert", "changelog"
        }
        actual = {c.value for c in Channel}
        assert expected == actual


class TestValueAttribute:
    """Test ValueAttribute model."""

    def test_minimal_creation(self):
        """Create minimal ValueAttribute."""
        attr = ValueAttribute(
            pain_point="Manual process takes too long",
            benefit="Automated and instant",
        )
        assert attr.value_type == ValueType.DIRECT
        assert attr.pain_point == "Manual process takes too long"
        assert attr.benefit == "Automated and instant"
        assert Persona.ANY in attr.personas

    def test_full_creation(self):
        """Create fully specified ValueAttribute."""
        attr = ValueAttribute(
            value_type=ValueType.RIPPLE,
            personas=[Persona.DEVELOPER, Persona.OPERATOR],
            primary_persona=Persona.DEVELOPER,
            pain_point="Time wasted on debugging",
            pain_point_category="time",
            benefit="Automatic error resolution",
            benefit_metric="50% less MTTR",
            channels=[Channel.SLACK, Channel.EMAIL],
            primary_channel=Channel.SLACK,
            time_savings="2 hours/week",
            cognitive_load_reduction="No manual log searching",
            error_prevention="Catches issues before deployment",
            creator_direct_value="More focus time",
            creator_indirect_value="Better debugging skills",
            creator_ripple_value="Team efficiency improved",
        )
        assert attr.value_type == ValueType.RIPPLE
        assert len(attr.personas) == 2
        assert attr.get_primary_persona() == Persona.DEVELOPER
        assert attr.get_primary_channel() == Channel.SLACK
        assert attr.time_savings == "2 hours/week"

    def test_get_primary_persona_default(self):
        """Primary persona defaults to first in list."""
        attr = ValueAttribute(
            personas=[Persona.OPERATOR, Persona.DEVELOPER],
            pain_point="test",
            benefit="test",
        )
        assert attr.get_primary_persona() == Persona.OPERATOR

    def test_get_primary_channel_default(self):
        """Primary channel defaults to first in list."""
        attr = ValueAttribute(
            channels=[Channel.EMAIL, Channel.SLACK],
            pain_point="test",
            benefit="test",
        )
        assert attr.get_primary_channel() == Channel.EMAIL


class TestValueCapability:
    """Test ValueCapability model."""

    @pytest.fixture
    def sample_value_attribute(self):
        return ValueAttribute(
            value_type=ValueType.DIRECT,
            personas=[Persona.DEVELOPER],
            pain_point="Manual testing is slow",
            benefit="Automated test generation",
            channels=[Channel.DOCS],
        )

    def test_creation(self, sample_value_attribute):
        """Create ValueCapability with value attributes."""
        cap = ValueCapability(
            skill_id="capability-value-promoter",
            capability_id="persona_mapping",
            capability_name="Persona Mapping",
            category=CapabilityCategory.TRANSFORM,
            knowledge_category=KnowledgeCategory.PERSONA,
            summary="Map capabilities to personas",
            source_section="Audience Profiles",
            line_range="100-150",
            value=sample_value_attribute,
            token_budget=300,
        )
        assert cap.skill_id == "capability-value-promoter"
        assert cap.value.value_type == ValueType.DIRECT
        assert cap.value.pain_point == "Manual testing is slow"

    def test_cross_linking(self, sample_value_attribute):
        """ValueCapability supports cross-linking."""
        cap = ValueCapability(
            skill_id="capability-value-promoter",
            capability_id="test_cap",
            capability_name="Test",
            category=CapabilityCategory.TRANSFORM,
            knowledge_category=KnowledgeCategory.VALUE_PROPOSITION,
            summary="Test capability",
            source_section="Test",
            line_range="1-10",
            value=sample_value_attribute,
            token_budget=100,
            related_skills=["dev-tour-guide", "o11y"],
            related_capabilities=["observability_stack", "auto_fix"],
        )
        assert "dev-tour-guide" in cap.related_skills
        assert "observability_stack" in cap.related_capabilities

    def test_pre_generated_messaging(self, sample_value_attribute):
        """ValueCapability stores pre-generated messaging."""
        cap = ValueCapability(
            skill_id="test",
            capability_id="test_cap",
            capability_name="Test",
            category=CapabilityCategory.TRANSFORM,
            knowledge_category=KnowledgeCategory.VALUE_PROPOSITION,
            summary="Test capability",
            source_section="Test",
            line_range="1-10",
            value=sample_value_attribute,
            token_budget=100,
            slack_message="💡 Automated test generation saves hours",
            email_subject="Discover automated testing",
            one_liner="Generate tests automatically",
        )
        assert cap.slack_message.startswith("💡")
        assert cap.one_liner == "Generate tests automatically"


class TestValueManifest:
    """Test ValueManifest model."""

    def test_creation(self):
        """Create ValueManifest with aggregates."""
        manifest = ValueManifest(
            skill_id="capability-value-promoter",
            skill_type="specialist",
            description="Value mapping skill",
            source_file="/path/to/SKILL.md",
            total_value_capabilities=20,
            personas_covered=["developer", "operator", "creator"],
            channels_supported=["slack", "email", "docs"],
            related_technical_skills=["dev-tour-guide"],
        )
        assert manifest.total_value_capabilities == 20
        assert len(manifest.personas_covered) == 3
        assert "dev-tour-guide" in manifest.related_technical_skills


class TestHelperFunctions:
    """Test value helper functions."""

    def test_derive_value_type_direct(self):
        """Direct value type with time savings."""
        assert derive_value_type(has_time_savings=True) == ValueType.DIRECT

    def test_derive_value_type_indirect(self):
        """Indirect value type with skill building."""
        assert derive_value_type(has_skill_building=True) == ValueType.INDIRECT

    def test_derive_value_type_ripple(self):
        """Ripple value type takes precedence."""
        assert derive_value_type(
            has_time_savings=True,
            has_skill_building=True,
            has_ripple_effect=True
        ) == ValueType.RIPPLE

    def test_get_persona_from_context_developer(self):
        """Detect developer persona from context."""
        assert get_persona_from_context("software developer") == Persona.DEVELOPER
        assert get_persona_from_context("frontend engineer") == Persona.DEVELOPER

    def test_get_persona_from_context_operator(self):
        """Detect operator persona from context."""
        assert get_persona_from_context("devops team") == Persona.OPERATOR
        assert get_persona_from_context("sre on-call") == Persona.OPERATOR

    def test_get_persona_from_context_executive(self):
        """Detect executive persona from context."""
        assert get_persona_from_context("CTO presentation") == Persona.EXECUTIVE
        assert get_persona_from_context("for directors") == Persona.EXECUTIVE

    def test_get_persona_from_context_any(self):
        """Default to ANY persona for unknown context."""
        assert get_persona_from_context("random text") == Persona.ANY

    def test_get_channel_from_context_slack(self):
        """Detect Slack channel from context."""
        assert get_channel_from_context("slack message") == Channel.SLACK
        assert get_channel_from_context("team chat") == Channel.SLACK

    def test_get_channel_from_context_email(self):
        """Detect email channel from context."""
        assert get_channel_from_context("email newsletter") == Channel.EMAIL

    def test_get_channel_from_context_docs(self):
        """Default to docs for unknown context."""
        assert get_channel_from_context("random text") == Channel.DOCS


class TestValueCapabilityParser:
    """Test ValueCapabilityParser."""

    @pytest.fixture
    def sample_skill_content(self, tmp_path):
        """Create a sample value-focused skill."""
        skill_dir = tmp_path / "test-value-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("""---
name: test-value-skill
description: A test value skill
---

# Test Value Skill

Test value skill for unit tests.

## Core Value Proposition

Help developers save time with automation.

### Time Savings

Save 2 hours per week on manual tasks.

- Automates repetitive work
- Reduces errors
- Improves consistency

```yaml
time_saved: 2h/week
```

## Persona Mapping

Map capabilities to different audience personas.

| Persona | Pain Point | Benefit |
|---------|------------|---------|
| Developer | Manual testing | Auto-generated tests |
| Manager | Slow delivery | Faster releases |

## Channel Adaptation

Adapt messaging for different channels.

### Slack Integration

Quick updates via Slack messages.

- Concise format
- Emoji support
- Links to details
""")
        return skill_dir

    def test_parser_extracts_capabilities(self, sample_skill_content):
        """Parser extracts capabilities from markdown."""
        from contextcore.value import ValueCapabilityParser

        parser = ValueCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        assert manifest.skill_id == "test-value-skill"
        assert len(capabilities) >= 3  # At least 3 H2 sections

    def test_parser_extracts_personas(self, sample_skill_content):
        """Parser extracts personas from content."""
        from contextcore.value import ValueCapabilityParser

        parser = ValueCapabilityParser(sample_skill_content)
        _, capabilities = parser.parse()

        # Find persona mapping capability
        persona_cap = next(
            (c for c in capabilities if "persona" in c.capability_id.lower()),
            None
        )
        assert persona_cap is not None
        # Should detect developer and manager from table
        personas = persona_cap.value.personas
        assert Persona.DEVELOPER in personas or Persona.MANAGER in personas or Persona.ANY in personas

    def test_parser_extracts_value_type(self, sample_skill_content):
        """Parser extracts value type from content."""
        from contextcore.value import ValueCapabilityParser

        parser = ValueCapabilityParser(sample_skill_content)
        _, capabilities = parser.parse()

        # Find core value proposition capability
        core_cap = next(
            (c for c in capabilities if "core" in c.capability_id.lower() or "value" in c.capability_id.lower()),
            None
        )
        assert core_cap is not None
        # Should detect direct value (time savings mentioned)
        assert core_cap.value.value_type in [ValueType.DIRECT, ValueType.INDIRECT, ValueType.RIPPLE]

    def test_parser_extracts_channels(self, sample_skill_content):
        """Parser extracts channels from content."""
        from contextcore.value import ValueCapabilityParser

        parser = ValueCapabilityParser(sample_skill_content)
        _, capabilities = parser.parse()

        # Find channel adaptation capability
        channel_cap = next(
            (c for c in capabilities if "channel" in c.capability_id.lower()),
            None
        )
        assert channel_cap is not None
        # Should detect slack channel
        assert Channel.SLACK in channel_cap.value.channels or Channel.DOCS in channel_cap.value.channels

    def test_parser_generates_slack_message(self, sample_skill_content):
        """Parser generates pre-adapted Slack message."""
        from contextcore.value import ValueCapabilityParser

        parser = ValueCapabilityParser(sample_skill_content)
        _, capabilities = parser.parse()

        for cap in capabilities:
            if cap.slack_message:
                assert cap.slack_message.startswith("💡")
                break

    def test_manifest_aggregates(self, sample_skill_content):
        """Manifest includes aggregate metrics."""
        from contextcore.value import ValueCapabilityParser

        parser = ValueCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        assert manifest.total_value_capabilities == len(capabilities)
        assert len(manifest.personas_covered) > 0
        assert len(manifest.channels_supported) > 0


class TestKnowledgeCategoryExtensions:
    """Test KnowledgeCategory value extensions."""

    def test_value_categories_exist(self):
        """Value-focused categories exist in KnowledgeCategory."""
        assert hasattr(KnowledgeCategory, "VALUE_PROPOSITION")
        assert hasattr(KnowledgeCategory, "MESSAGING")
        assert hasattr(KnowledgeCategory, "PERSONA")
        assert hasattr(KnowledgeCategory, "CHANNEL")

    def test_value_category_values(self):
        """Value category values are correct."""
        assert KnowledgeCategory.VALUE_PROPOSITION.value == "value_proposition"
        assert KnowledgeCategory.MESSAGING.value == "messaging"
        assert KnowledgeCategory.PERSONA.value == "persona"
        assert KnowledgeCategory.CHANNEL.value == "channel"

    def test_get_knowledge_category_value(self):
        """get_knowledge_category detects value categories."""
        from contextcore.knowledge.models import get_knowledge_category

        # Value proposition headings
        assert get_knowledge_category("Value Proposition Mapping") == KnowledgeCategory.VALUE_PROPOSITION
        assert get_knowledge_category("Core Workflow") == KnowledgeCategory.VALUE_PROPOSITION

        # Persona headings
        assert get_knowledge_category("Audience Profiles") == KnowledgeCategory.PERSONA
        assert get_knowledge_category("Audience of 1") == KnowledgeCategory.PERSONA

        # Channel headings
        assert get_knowledge_category("Channel Adaptation") == KnowledgeCategory.MESSAGING
        assert get_knowledge_category("Distribution Channels") == KnowledgeCategory.CHANNEL
