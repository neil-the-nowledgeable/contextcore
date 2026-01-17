"""
ContextCore Knowledge Module.

Convert markdown knowledge documents (SKILL.md) into queryable
OpenTelemetry spans for agent discovery and human visualization.

Example usage:
    from contextcore.knowledge import (
        MarkdownCapabilityParser,
        KnowledgeEmitter,
        KnowledgeCategory,
    )

    # Parse SKILL.md
    parser = MarkdownCapabilityParser("~/.claude/skills/dev-tour-guide")
    manifest, capabilities = parser.parse()

    # Emit to Tempo
    emitter = KnowledgeEmitter(agent_id="dev-tour-guide")
    trace_id, span_ids = emitter.emit_knowledge_with_capabilities(
        manifest, capabilities
    )

Query examples (TraceQL):
    # All dev-tour-guide capabilities
    { skill.id = "dev-tour-guide" && name =~ "capability:.*" }

    # Find by knowledge category
    { knowledge.category = "infrastructure" }

    # Find capabilities with specific port
    { capability.ports =~ ".*3000.*" }
"""

from contextcore.knowledge.models import (
    KnowledgeCategory,
    KnowledgeCapability,
    KnowledgeManifest,
    Section,
    SUBSECTION_WHITELIST,
    SECTION_CATEGORY_MAP,
    get_knowledge_category,
)
from contextcore.knowledge.md_parser import (
    MarkdownCapabilityParser,
    estimate_tokens,
    slugify,
    compress_to_summary,
)
from contextcore.knowledge.emitter import KnowledgeEmitter

__all__ = [
    # Models
    "KnowledgeCategory",
    "KnowledgeCapability",
    "KnowledgeManifest",
    "Section",
    "SUBSECTION_WHITELIST",
    "SECTION_CATEGORY_MAP",
    "get_knowledge_category",
    # Parser
    "MarkdownCapabilityParser",
    "estimate_tokens",
    "slugify",
    "compress_to_summary",
    # Emitter
    "KnowledgeEmitter",
]
