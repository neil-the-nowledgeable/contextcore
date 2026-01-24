"""
Knowledge Emitter for OTel spans.

Extends SkillCapabilityEmitter to add knowledge-specific attributes:
- knowledge.category
- capability.source_section, capability.line_range
- capability.tools, capability.ports, capability.env_vars, capability.paths
- capability.has_code, capability.has_tables
"""

from __future__ import annotations

from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode, Link

from contextcore.skill.emitter import SkillCapabilityEmitter
from contextcore.knowledge.models import (
    KnowledgeCapability,
    KnowledgeManifest,
)


class KnowledgeEmitter(SkillCapabilityEmitter):
    """
    Emit knowledge capabilities as OTel spans.

    Extends SkillCapabilityEmitter with knowledge-specific attributes
    for markdown document content.

    Example:
        emitter = KnowledgeEmitter(
            agent_id="dev-tour-guide",
            session_id="session-123",
        )

        manifest, capabilities = parser.parse()
        trace_id, span_ids = emitter.emit_knowledge_with_capabilities(
            manifest, capabilities
        )
    """

    def __init__(
        self,
        agent_id: str = "knowledge-emitter",
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        tracer_name: str = "contextcore.knowledge",
    ):
        super().__init__(
            agent_id=agent_id,
            session_id=session_id,
            project_id=project_id,
            tracer_name=tracer_name,
        )

    def emit_knowledge_manifest(self, manifest: KnowledgeManifest) -> str:
        """
        Emit a knowledge manifest as a parent span.

        Adds knowledge-specific attributes to the skill manifest span.

        Args:
            manifest: The knowledge manifest to emit

        Returns:
            trace_id (hex string) for linking child capabilities
        """
        with self.tracer.start_as_current_span(
            f"skill:{manifest.skill_id}",
            kind=SpanKind.INTERNAL,
        ) as span:
            # Agent attribution
            self._set_agent_attributes(span)

            # Core skill attributes (from parent class pattern)
            span.set_attribute("skill.id", manifest.skill_id)
            span.set_attribute("skill.type", manifest.skill_type)
            span.set_attribute("skill.version", manifest.version)
            span.set_attribute("skill.description", manifest.description)

            # Token budget tracking
            span.set_attribute("skill.manifest_tokens", manifest.manifest_tokens)
            span.set_attribute("skill.index_tokens", manifest.index_tokens)
            span.set_attribute("skill.total_tokens", manifest.total_tokens)
            span.set_attribute("skill.compressed_tokens", manifest.compressed_tokens)

            # Capability references
            span.set_attribute("skill.capability_count", len(manifest.capability_refs))
            if manifest.capability_refs:
                span.set_attribute("skill.capabilities", ",".join(manifest.capability_refs))

            # Source path
            if manifest.source_path:
                span.set_attribute("skill.source_path", manifest.source_path)

            # Knowledge-specific attributes
            span.set_attribute("knowledge.source_file", manifest.source_file)
            span.set_attribute("knowledge.total_lines", manifest.total_lines)
            span.set_attribute("knowledge.section_count", manifest.section_count)
            span.set_attribute("knowledge.subsection_count", manifest.subsection_count)
            span.set_attribute("knowledge.has_frontmatter", manifest.has_frontmatter)

            # Timestamps
            span.set_attribute("skill.created_at", manifest.created_at.isoformat())
            span.set_attribute("skill.updated_at", manifest.updated_at.isoformat())

            # Project linkage
            if manifest.project_refs:
                span.set_attribute("skill.project_refs", ",".join(manifest.project_refs))

            # Lifecycle event
            span.add_event(
                "skill.registered",
                attributes={
                    "registered_by": self.agent_id,
                    "capability_count": len(manifest.capability_refs),
                    "source_type": "markdown",
                }
            )

            span.set_status(Status(StatusCode.OK))

            # Store context for child capabilities
            span_context = span.get_span_context()
            self._skill_contexts[manifest.skill_id] = span_context
            trace_id = format(span_context.trace_id, "032x")

        return trace_id

    def emit_knowledge_capability(
        self,
        skill_id: str,
        capability: KnowledgeCapability,
        parent_trace_id: Optional[str] = None,
    ) -> str:
        """
        Emit a knowledge capability as a span.

        Adds knowledge-specific attributes to the capability span.

        Args:
            skill_id: Parent skill identifier
            capability: The knowledge capability to emit
            parent_trace_id: Optional trace ID to link as parent

        Returns:
            span_id (hex string)
        """
        # Build links if we have parent context
        links = []
        if parent_trace_id and skill_id in self._skill_contexts:
            parent_ctx = self._skill_contexts[skill_id]
            links.append(Link(parent_ctx, attributes={"link.type": "child_of"}))

        with self.tracer.start_as_current_span(
            f"capability:{capability.capability_id}",
            kind=SpanKind.INTERNAL,
            links=links,
        ) as span:
            # Agent attribution
            self._set_agent_attributes(span)

            # Skill context
            span.set_attribute("skill.id", skill_id)
            if capability.skill_version:
                span.set_attribute("skill.version", capability.skill_version)
            if capability.skill_type:
                span.set_attribute("skill.type", capability.skill_type)

            # Capability identity
            span.set_attribute("capability.id", capability.capability_id)
            span.set_attribute("capability.name", capability.capability_name)
            span.set_attribute("capability.category", capability.category)

            # Summary (compressed content)
            span.set_attribute("capability.summary", capability.summary)
            span.set_attribute("capability.summary_tokens", capability.summary_tokens)

            # Token budget
            span.set_attribute("capability.token_budget", capability.token_budget)

            # Triggers for routing/discovery
            if capability.triggers:
                span.set_attribute("capability.triggers", ",".join(capability.triggers))

            # Interoperability scores
            span.set_attribute("capability.interop_human", capability.interop_human)
            span.set_attribute("capability.interop_agent", capability.interop_agent)

            # Audience (may be string due to use_enum_values=True in model config)
            audience = capability.get_audience()
            audience_value = audience if isinstance(audience, str) else audience.value
            span.set_attribute("capability.audience", audience_value)

            # Confidence and reliability
            span.set_attribute("capability.confidence", capability.confidence)

            # Timestamps
            span.set_attribute("capability.created_at", capability.created_at.isoformat())
            span.set_attribute("capability.updated_at", capability.updated_at.isoformat())

            # =========================================================
            # Knowledge-specific attributes
            # =========================================================

            # Knowledge category
            span.set_attribute("knowledge.category", capability.knowledge_category)

            # Source tracking
            span.set_attribute("capability.source_section", capability.source_section)
            if capability.source_subsection:
                span.set_attribute("capability.source_subsection", capability.source_subsection)
            span.set_attribute("capability.line_range", capability.line_range)

            # Content analysis
            span.set_attribute("capability.has_code", capability.has_code)
            span.set_attribute("capability.has_tables", capability.has_tables)
            span.set_attribute("capability.code_block_count", capability.code_block_count)

            # Reference extraction (comma-separated for queryability)
            if capability.tools:
                span.set_attribute("capability.tools", ",".join(capability.tools))
            if capability.ports:
                span.set_attribute("capability.ports", ",".join(capability.ports))
            if capability.env_vars:
                span.set_attribute("capability.env_vars", ",".join(capability.env_vars))
            if capability.paths:
                span.set_attribute("capability.paths", ",".join(capability.paths))
            if capability.related_skills:
                span.set_attribute("capability.related_skills", ",".join(capability.related_skills))

            # Evidence as events (references to full content)
            for ev in capability.evidence:
                ev_attrs = {
                    "evidence.type": ev.type,
                    "evidence.ref": ev.ref,
                }
                if ev.tokens is not None:
                    ev_attrs["evidence.tokens"] = ev.tokens
                if ev.description:
                    ev_attrs["evidence.description"] = ev.description

                span.add_event("evidence.added", attributes=ev_attrs)

            # Lifecycle event
            span.add_event(
                "capability.registered",
                attributes={
                    "registered_by": self.agent_id,
                    "session_id": self.session_id,
                    "source_type": "markdown",
                }
            )

            span.set_status(Status(StatusCode.OK))

            span_context = span.get_span_context()
            span_id = format(span_context.span_id, "016x")

            # Store for lifecycle events
            self._capability_spans[capability.capability_id] = span_id

        return span_id

    def emit_knowledge_with_capabilities(
        self,
        manifest: KnowledgeManifest,
        capabilities: list[KnowledgeCapability],
    ) -> tuple[str, list[str]]:
        """
        Emit a complete knowledge document with all capabilities.

        Convenience method that emits the manifest and all capabilities
        in a single call, properly linking them.

        Args:
            manifest: The knowledge manifest
            capabilities: List of capabilities to emit

        Returns:
            Tuple of (trace_id, list of span_ids)
        """
        trace_id = self.emit_knowledge_manifest(manifest)

        span_ids = []
        for capability in capabilities:
            span_id = self.emit_knowledge_capability(
                skill_id=manifest.skill_id,
                capability=capability,
                parent_trace_id=trace_id,
            )
            span_ids.append(span_id)

        return trace_id, span_ids
