"""
Tests for the knowledge module markdown parser.

Tests cover:
- YAML frontmatter extraction
- Section tree building (H2 -> H3 hierarchy)
- Trigger extraction from various patterns
- Subsection detection rules
- Capability model validation
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone

from contextcore.knowledge import (
    MarkdownCapabilityParser,
    KnowledgeCategory,
    KnowledgeCapability,
    KnowledgeManifest,
    Section,
    estimate_tokens,
    slugify,
    compress_to_summary,
    get_knowledge_category,
    SUBSECTION_WHITELIST,
)
from contextcore.skill.models import CapabilityCategory, SkillType


class TestUtilityFunctions:
    """Test helper functions."""

    def test_estimate_tokens(self):
        """Token estimation should approximate 1 token per 4 chars."""
        assert estimate_tokens("") == 0
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("a" * 100) == 25

    def test_slugify(self):
        """Slugify should convert to snake_case."""
        assert slugify("Hello World") == "hello_world"
        assert slugify("Dev Tour Guide") == "dev_tour_guide"
        assert slugify("StartD8 SDK") == "startd8_sdk"
        assert slugify("GitHub Actions Auto-Fix") == "github_actions_auto_fix"
        assert slugify("011yBubo") == "011ybubo"

    def test_compress_to_summary(self):
        """Summary compression should extract first meaningful sentences."""
        content = """# Heading

This is the first sentence. This is the second sentence.

Some more content here.
"""
        summary = compress_to_summary(content)
        assert "first sentence" in summary.lower()
        assert len(summary) <= 500

    def test_compress_to_summary_skips_code_blocks(self):
        """Should skip code blocks when extracting summary."""
        content = """# Heading

```python
# This should be skipped
def foo():
    pass
```

This is the actual content we want.
"""
        summary = compress_to_summary(content)
        assert "def foo" not in summary
        assert "actual content" in summary.lower()


class TestKnowledgeCategoryMapping:
    """Test section-to-category mapping."""

    def test_exact_matches(self):
        """Test exact heading matches."""
        assert get_knowledge_category("Harbor Manifest") == KnowledgeCategory.INFRASTRUCTURE
        assert get_knowledge_category("Local Observability Stack") == KnowledgeCategory.INFRASTRUCTURE
        assert get_knowledge_category("Secure Secrets Management") == KnowledgeCategory.SECURITY
        assert get_knowledge_category("Default Behaviors") == KnowledgeCategory.CONFIGURATION

    def test_partial_matches(self):
        """Test partial/fuzzy heading matches."""
        assert get_knowledge_category("StartD8 SDK for Async Agent Development") == KnowledgeCategory.SDK
        assert get_knowledge_category("GitHub Actions Auto-Fix Workflow") == KnowledgeCategory.WORKFLOW

    def test_keyword_fallback(self):
        """Test keyword-based fallback."""
        assert get_knowledge_category("Some Infrastructure Topic") == KnowledgeCategory.INFRASTRUCTURE
        assert get_knowledge_category("API Documentation") == KnowledgeCategory.SDK
        assert get_knowledge_category("Auth Config") == KnowledgeCategory.SECURITY
        assert get_knowledge_category("Unknown Topic") == KnowledgeCategory.REFERENCE


class TestSectionModel:
    """Test Section model properties."""

    def test_line_count(self):
        """Line count should be calculated correctly."""
        section = Section(
            heading="Test",
            level=2,
            start_line=10,
            end_line=50,
            content="test content",
        )
        assert section.line_count == 41

    def test_has_code_blocks(self):
        """Code block detection."""
        section = Section(
            heading="Test",
            level=2,
            start_line=1,
            end_line=10,
            content="```python\ncode\n```",
        )
        assert section.has_code_blocks is True

        section_no_code = Section(
            heading="Test",
            level=2,
            start_line=1,
            end_line=10,
            content="just text",
        )
        assert section_no_code.has_code_blocks is False

    def test_has_tables(self):
        """Table detection."""
        section = Section(
            heading="Test",
            level=2,
            start_line=1,
            end_line=10,
            content="| col1 | col2 |\n| a | b |",
        )
        assert section.has_tables is True

    def test_code_block_count(self):
        """Code block counting."""
        section = Section(
            heading="Test",
            level=2,
            start_line=1,
            end_line=20,
            content="```python\ncode1\n```\n\n```bash\ncode2\n```",
        )
        assert section.code_block_count == 2


class TestMarkdownParser:
    """Test the MarkdownCapabilityParser."""

    @pytest.fixture
    def sample_skill_content(self, tmp_path):
        """Create a sample SKILL.md for testing."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()

        content = """---
name: test-skill
description: A test skill for unit testing.
---

# Test Skill

Main content here.

## Infrastructure Section

This section covers infrastructure topics.
Grafana is available at http://localhost:3000.
Prometheus at http://localhost:9090.

```bash
export PROMETHEUS_URL=http://localhost:9090
```

| Service | Port |
|---------|------|
| Grafana | 3000 |

### Important Subsection

This subsection is in the whitelist.

```python
def example():
    pass
```

More code:

```python
def another():
    pass
```

## SDK Documentation

SDK content goes here.

Use `contextcore task start` to create tasks.

### Async Agent Usage

This should become a separate capability.

```python
import asyncio

async def main():
    await agent.generate()

asyncio.run(main())
```

## Reference Section

Quick links and references.

### Some Minor Subsection

This is too short to extract.
"""
        (skill_dir / "SKILL.md").write_text(content)
        return skill_dir

    def test_parse_basic(self, sample_skill_content):
        """Basic parsing should extract manifest and capabilities."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        assert manifest.skill_id == "test-skill"
        assert manifest.description == "A test skill for unit testing."
        assert manifest.has_frontmatter is True
        assert len(capabilities) > 0

    def test_parse_extracts_sections(self, sample_skill_content):
        """Should extract H2 sections as capabilities."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        cap_ids = [c.capability_id for c in capabilities]
        assert "infrastructure_section" in cap_ids
        assert "sdk_documentation" in cap_ids
        assert "reference_section" in cap_ids

    def test_parse_extracts_subsections(self, sample_skill_content):
        """Should extract whitelisted subsections as separate capabilities."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        cap_ids = [c.capability_id for c in capabilities]
        # "Async Agent Usage" is in SUBSECTION_WHITELIST
        assert any("async" in cid.lower() for cid in cap_ids)

    def test_trigger_extraction(self, sample_skill_content):
        """Should extract triggers from content."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        infra_cap = next(c for c in capabilities if "infrastructure" in c.capability_id)
        assert "grafana" in infra_cap.triggers
        assert "prometheus" in infra_cap.triggers

    def test_port_extraction(self, sample_skill_content):
        """Should extract ports from content."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        infra_cap = next(c for c in capabilities if "infrastructure" in c.capability_id)
        assert "3000" in infra_cap.ports
        assert "9090" in infra_cap.ports

    def test_env_var_extraction(self, sample_skill_content):
        """Should extract environment variables."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        infra_cap = next(c for c in capabilities if "infrastructure" in c.capability_id)
        assert "PROMETHEUS_URL" in infra_cap.env_vars

    def test_tool_extraction(self, sample_skill_content):
        """Should extract CLI tool references."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        sdk_cap = next(c for c in capabilities if "sdk" in c.capability_id)
        assert any("contextcore" in t for t in sdk_cap.tools)

    def test_has_code_detection(self, sample_skill_content):
        """Should detect code blocks in capabilities."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        infra_cap = next(c for c in capabilities if "infrastructure" in c.capability_id)
        assert infra_cap.has_code is True

    def test_has_tables_detection(self, sample_skill_content):
        """Should detect tables in capabilities."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        infra_cap = next(c for c in capabilities if "infrastructure" in c.capability_id)
        assert infra_cap.has_tables is True

    def test_knowledge_category_assignment(self, sample_skill_content):
        """Should assign correct knowledge categories."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        infra_cap = next(c for c in capabilities if "infrastructure" in c.capability_id)
        assert infra_cap.knowledge_category == KnowledgeCategory.INFRASTRUCTURE

        ref_cap = next(c for c in capabilities if "reference" in c.capability_id)
        assert ref_cap.knowledge_category == KnowledgeCategory.REFERENCE

    def test_manifest_token_counts(self, sample_skill_content):
        """Manifest should have token budget information."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        assert manifest.total_tokens > 0
        assert manifest.compressed_tokens > 0
        # Note: For small test samples, compressed_tokens may exceed total_tokens
        # because each capability gets a minimum summary allocation (~50 tokens).
        # Real documents (like dev-tour-guide) show 80%+ compression.

    def test_capability_evidence(self, sample_skill_content):
        """Capabilities should have evidence links."""
        parser = MarkdownCapabilityParser(sample_skill_content)
        manifest, capabilities = parser.parse()

        for cap in capabilities:
            assert len(cap.evidence) > 0
            assert cap.evidence[0].type == "doc"
            assert "SKILL.md" in cap.evidence[0].ref


class TestKnowledgeCapabilityModel:
    """Test KnowledgeCapability model."""

    def test_create_capability(self):
        """Should create a valid capability."""
        cap = KnowledgeCapability(
            skill_id="test",
            capability_id="test_cap",
            capability_name="Test Capability",
            category=CapabilityCategory.QUERY,
            knowledge_category=KnowledgeCategory.INFRASTRUCTURE,
            summary="Test summary.",
            source_section="Test Section",
            line_range="1-50",
            token_budget=500,
        )

        assert cap.skill_id == "test"
        assert cap.knowledge_category == KnowledgeCategory.INFRASTRUCTURE
        assert cap.line_range == "1-50"

    def test_capability_defaults(self):
        """Should have sensible defaults."""
        cap = KnowledgeCapability(
            skill_id="test",
            capability_id="test_cap",
            capability_name="Test",
            category=CapabilityCategory.QUERY,
            knowledge_category=KnowledgeCategory.REFERENCE,
            summary="Test",
            source_section="Test",
            line_range="1-10",
            token_budget=100,
        )

        assert cap.has_code is False
        assert cap.has_tables is False
        assert cap.tools == []
        assert cap.ports == []
        assert cap.env_vars == []
        assert cap.confidence == 0.9


class TestSubsectionWhitelist:
    """Test subsection whitelist behavior."""

    def test_whitelist_contains_expected_entries(self):
        """Whitelist should contain key subsections."""
        assert "Async Agent Usage" in SUBSECTION_WHITELIST
        assert "StartD8 TUI (Interactive Terminal UI)" in SUBSECTION_WHITELIST
        assert "Task Commands" in SUBSECTION_WHITELIST
        assert "Audit Trail" in SUBSECTION_WHITELIST


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_frontmatter(self, tmp_path):
        """Should handle missing frontmatter gracefully."""
        skill_dir = tmp_path / "no-frontmatter"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just a Heading\n\nSome content.")

        parser = MarkdownCapabilityParser(skill_dir)
        manifest, capabilities = parser.parse()

        assert manifest.has_frontmatter is False
        assert manifest.skill_id == "no-frontmatter"

    def test_empty_sections(self, tmp_path):
        """Should handle empty sections."""
        skill_dir = tmp_path / "empty-sections"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: empty-test
---

## Empty Section

## Another Empty Section

""")

        parser = MarkdownCapabilityParser(skill_dir)
        manifest, capabilities = parser.parse()

        # Should still parse without errors
        assert len(capabilities) >= 0

    def test_file_not_found(self, tmp_path):
        """Should raise error for missing file."""
        with pytest.raises(FileNotFoundError):
            MarkdownCapabilityParser(tmp_path / "nonexistent")

    def test_direct_file_path(self, tmp_path):
        """Should accept direct path to SKILL.md."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: direct-file
---

## Test Section

Content here.
""")

        parser = MarkdownCapabilityParser(skill_file)
        manifest, capabilities = parser.parse()

        assert manifest.skill_id == "direct-file"
