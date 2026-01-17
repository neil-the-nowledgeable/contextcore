"""
Pydantic models for Knowledge Base telemetry.

These models extend the skill capability patterns for storing
markdown knowledge documents (like SKILL.md) as queryable OTel spans.

Knowledge capabilities enable:
- TraceQL queries for agent discovery
- Grafana dashboards for human visualization
- Progressive disclosure (summary + evidence to full content)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from contextcore.skill.models import (
    Audience,
    CapabilityCategory,
    Evidence,
    SkillCapability,
    SkillManifest,
    SkillType,
)


class KnowledgeCategory(str, Enum):
    """Classification of knowledge content by nature."""
    # Technical knowledge categories (from dev-tour-guide)
    INFRASTRUCTURE = "infrastructure"    # Harbor Manifest, Observability Stack, ports
    WORKFLOW = "workflow"                # Auto-fix, Session Management, CI/CD
    SDK = "sdk"                          # StartD8, ContextCore, programmatic usage
    REFERENCE = "reference"              # Lessons Learned, Skills Catalog, Quick Reference
    SECURITY = "security"                # Secrets Management, credentials, auth
    CONFIGURATION = "configuration"      # Default Behaviors, Hooks, settings
    # Value-focused categories (from capability-value-promoter)
    VALUE_PROPOSITION = "value_proposition"  # User benefits, problem-solution pairs
    MESSAGING = "messaging"              # Channel-adapted content, templates
    PERSONA = "persona"                  # Audience profiles, user contexts
    CHANNEL = "channel"                  # Distribution channels, format adaptations


# Categories that require elevated RBAC permissions
SENSITIVE_CATEGORIES: set[KnowledgeCategory] = {
    KnowledgeCategory.SECURITY,
}


def is_sensitive_category(category: KnowledgeCategory) -> bool:
    """Check if a knowledge category requires elevated RBAC permissions."""
    return category in SENSITIVE_CATEGORIES


# Subsection whitelist - these H3 sections always become separate capabilities
SUBSECTION_WHITELIST = {
    # StartD8 SDK subsections
    "Async Agent Usage",
    "Parallel Agent Execution",
    "Connection Pooling for Multi-Agent Workloads",
    "Retry Configuration",
    "Cost Tracking Integration",
    "Truncation Detection",
    "Session Tracking with Prometheus",
    "StartD8 TUI (Interactive Terminal UI)",
    "StartD8 Workflow System (Agent-Accessible)",
    # ContextCore subsections
    "Task Commands",
    "Metrics Commands",
    "Demo Module (microservices-demo Integration)",
    "Agent Memory (Persistent Insights)",
    # Secrets subsections
    "Audit Trail",
    # GitHub Auto-Fix subsections
    "Grafana Alert Rules",
    "GitHub Actions Workflow",
}


class Section(BaseModel):
    """Parsed markdown section."""
    heading: str = Field(..., description="Section heading text")
    level: int = Field(..., ge=1, le=6, description="Heading level (1-6)")
    start_line: int = Field(..., ge=1, description="Start line in source")
    end_line: int = Field(..., ge=1, description="End line in source")
    content: str = Field(..., description="Section content including heading")
    subsections: List["Section"] = Field(default_factory=list, description="Child sections")

    @property
    def line_count(self) -> int:
        """Number of lines in this section."""
        return self.end_line - self.start_line + 1

    @property
    def has_code_blocks(self) -> bool:
        """Check if section contains code blocks."""
        return "```" in self.content

    @property
    def has_tables(self) -> bool:
        """Check if section contains markdown tables."""
        lines = self.content.split("\n")
        for line in lines:
            if line.strip().startswith("|") and "|" in line[1:]:
                return True
        return False

    @property
    def code_block_count(self) -> int:
        """Count code blocks in section."""
        return self.content.count("```") // 2


class KnowledgeCapability(SkillCapability):
    """
    Extended capability for knowledge base content.

    Adds knowledge-specific attributes for markdown documents:
    - Source tracking (section, subsection, line range)
    - Content analysis (code blocks, tables)
    - Reference extraction (tools, ports, env vars, paths)

    Example:
        cap = KnowledgeCapability(
            skill_id="dev-tour-guide",
            capability_id="observability_stack",
            capability_name="Local Observability Stack",
            category=CapabilityCategory.QUERY,
            knowledge_category=KnowledgeCategory.INFRASTRUCTURE,
            summary="Grafana ecosystem on localhost with Prometheus, Loki, Tempo, Mimir, Pyroscope.",
            triggers=["grafana", "prometheus", "loki", "tempo", "observability", "metrics", "logs"],
            source_section="Local Observability Stack",
            line_range="52-81",
            ports=["3000", "9090", "9009", "3100", "3200", "4040"],
            tools=["o11y", "grafana-dashboards"],
            token_budget=400,
        )
    """

    # Knowledge classification
    knowledge_category: KnowledgeCategory = Field(
        ...,
        description="Classification by content nature"
    )

    # Source tracking
    source_section: str = Field(
        ...,
        description="H2 heading from source document"
    )
    source_subsection: Optional[str] = Field(
        None,
        description="H3 heading if this is a subsection capability"
    )
    line_range: str = Field(
        ...,
        description="Start-end lines in source (e.g., '50-120')"
    )

    # Content analysis
    has_code: bool = Field(
        default=False,
        description="Contains code examples"
    )
    has_tables: bool = Field(
        default=False,
        description="Contains tables"
    )
    code_block_count: int = Field(
        default=0,
        description="Number of code blocks"
    )

    # Reference extraction
    tools: List[str] = Field(
        default_factory=list,
        description="CLI commands referenced (contextcore, startd8, etc.)"
    )
    ports: List[str] = Field(
        default_factory=list,
        description="Network ports referenced"
    )
    env_vars: List[str] = Field(
        default_factory=list,
        description="Environment variables referenced"
    )
    paths: List[str] = Field(
        default_factory=list,
        description="File paths referenced"
    )

    # Related content
    related_skills: List[str] = Field(
        default_factory=list,
        description="Skills referenced in content"
    )
    related_sections: List[str] = Field(
        default_factory=list,
        description="Cross-references to other sections"
    )

    class Config:
        use_enum_values = True


class KnowledgeManifest(SkillManifest):
    """
    Extended manifest for knowledge documents.

    Adds document-level metadata extracted from markdown.
    """

    # Document metadata
    source_file: str = Field(
        ...,
        description="Path to source markdown file"
    )
    total_lines: int = Field(
        default=0,
        description="Total lines in source document"
    )
    section_count: int = Field(
        default=0,
        description="Number of H2 sections"
    )
    subsection_count: int = Field(
        default=0,
        description="Number of H3 subsections extracted as capabilities"
    )

    # Content summary
    has_frontmatter: bool = Field(
        default=False,
        description="Document has YAML frontmatter"
    )

    class Config:
        use_enum_values = True


# Map section headings to knowledge categories
SECTION_CATEGORY_MAP: dict[str, KnowledgeCategory] = {
    # Infrastructure
    "Harbor Manifest": KnowledgeCategory.INFRASTRUCTURE,
    "Local Observability Stack": KnowledgeCategory.INFRASTRUCTURE,
    # Workflow
    "Claude Code Cost Tracking": KnowledgeCategory.WORKFLOW,
    "011yBubo": KnowledgeCategory.WORKFLOW,
    "GitHub Actions Auto-Fix Workflow": KnowledgeCategory.WORKFLOW,
    "Session Management": KnowledgeCategory.WORKFLOW,
    # SDK
    "StartD8 SDK for Async Agent Development": KnowledgeCategory.SDK,
    "StartD8 TUI (Interactive Terminal UI)": KnowledgeCategory.SDK,
    "StartD8 Workflow System (Agent-Accessible)": KnowledgeCategory.SDK,
    "ContextCore: Project O11y via Kubernetes CRDs": KnowledgeCategory.SDK,
    # Reference
    "Lessons Learned Library": KnowledgeCategory.REFERENCE,
    "Prompt Engineering Framework": KnowledgeCategory.REFERENCE,
    "Available Skills": KnowledgeCategory.REFERENCE,
    "Quick Reference": KnowledgeCategory.REFERENCE,
    # Security
    "Secure Secrets Management": KnowledgeCategory.SECURITY,
    # Configuration
    "Default Behaviors": KnowledgeCategory.CONFIGURATION,
    "Active Hooks & Guards": KnowledgeCategory.CONFIGURATION,
    # Value Proposition (capability-value-promoter)
    "Core Workflow": KnowledgeCategory.VALUE_PROPOSITION,
    "Capability Extraction": KnowledgeCategory.VALUE_PROPOSITION,
    "Value Proposition Mapping": KnowledgeCategory.VALUE_PROPOSITION,
    "Value Dimensions": KnowledgeCategory.VALUE_PROPOSITION,
    "Creator Value Framework": KnowledgeCategory.VALUE_PROPOSITION,
    # Messaging
    "Channel Adaptation": KnowledgeCategory.MESSAGING,
    "Message Templates": KnowledgeCategory.MESSAGING,
    "Tone Calibration": KnowledgeCategory.MESSAGING,
    # Persona
    "Audience Profiles": KnowledgeCategory.PERSONA,
    "Audience of 1": KnowledgeCategory.PERSONA,
    "Personalization": KnowledgeCategory.PERSONA,
    # Channel
    "Channel Guidelines": KnowledgeCategory.CHANNEL,
    "Distribution Channels": KnowledgeCategory.CHANNEL,
    "Format Specifications": KnowledgeCategory.CHANNEL,
}


def get_knowledge_category(heading: str) -> KnowledgeCategory:
    """
    Determine knowledge category from section heading.

    Falls back to REFERENCE for unknown headings.
    """
    # Exact match
    if heading in SECTION_CATEGORY_MAP:
        return SECTION_CATEGORY_MAP[heading]

    # Partial match (heading contains key)
    heading_lower = heading.lower()
    for key, category in SECTION_CATEGORY_MAP.items():
        if key.lower() in heading_lower or heading_lower in key.lower():
            return category

    # Keyword-based fallback
    if any(kw in heading_lower for kw in ["infrastructure", "stack", "harbor", "port"]):
        return KnowledgeCategory.INFRASTRUCTURE
    if any(kw in heading_lower for kw in ["workflow", "action", "auto", "ci/cd"]):
        return KnowledgeCategory.WORKFLOW
    if any(kw in heading_lower for kw in ["sdk", "api", "library", "module"]):
        return KnowledgeCategory.SDK
    if any(kw in heading_lower for kw in ["secret", "credential", "auth", "key"]):
        return KnowledgeCategory.SECURITY
    if any(kw in heading_lower for kw in ["config", "setting", "hook", "behavior"]):
        return KnowledgeCategory.CONFIGURATION
    # Value-focused categories
    if any(kw in heading_lower for kw in ["value", "benefit", "proposition", "pain point", "problem"]):
        return KnowledgeCategory.VALUE_PROPOSITION
    if any(kw in heading_lower for kw in ["message", "template", "tone", "copy"]):
        return KnowledgeCategory.MESSAGING
    if any(kw in heading_lower for kw in ["persona", "audience", "user", "creator"]):
        return KnowledgeCategory.PERSONA
    if any(kw in heading_lower for kw in ["channel", "slack", "email", "social", "distribution"]):
        return KnowledgeCategory.CHANNEL

    return KnowledgeCategory.REFERENCE
