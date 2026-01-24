"""
Value Emitter for OTel spans.

Extends KnowledgeEmitter to add value-specific attributes:
- value.type (direct, indirect, ripple)
- value.persona, value.personas
- value.channel, value.channels
- value.pain_point, value.benefit
- value.time_savings, value.cognitive_load_reduction
- value.related_skills, value.related_capabilities

Enables TraceQL queries like:
    { value.persona = "developer" }
    { value.type = "direct" && value.pain_point =~ ".*time.*" }
"""

from __future__ import annotations

from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode, Link

from contextcore.knowledge.emitter import KnowledgeEmitter
from contextcore.value.models import (
    ValueCapability,
    ValueManifest,
)


class ValueEmitter(KnowledgeEmitter):
    """
    Emit value capabilities as OTel spans.

    Extends KnowledgeEmitter with value-specific attributes
    for discovery through value propositions.

    Example:
        emitter = ValueEmitter(
            agent_id="capability-value-promoter",
            session_id="session-123",
        )

        manifest, capabilities = parser.parse()
        trace_id, span_ids = emitter.emit_value_with_capabilities(
            manifest, capabilities
        )

    TraceQL Queries:
        # Find direct value capabilities
        { value.type = "direct" }

        # Find capabilities for developers
        { value.persona = "developer" }

        # Find capabilities that save time
        { value.time_savings != "" }

        # Cross-linked queries
        { value.related_skills =~ ".*dev-tour-guide.*" }
    """

    def __init__(
        self,
        agent_id: str = "value-emitter",
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        tracer_name: str = "contextcore.value",
    ):
        super().__init__(
            agent_id=agent_id,
            session_id=session_id,
            project_id=project_id,
            tracer_name=tracer_name,
        )

    def emit_value_manifest(self, manifest: ValueManifest) -> str:
        """
        Emit a value manifest as a parent span.

        Adds value-specific aggregate attributes.

        Args:
            manifest: The value manifest to emit

        Returns:
            trace_id (hex string) for linking child capabilities
        """
        with self.tracer.start_as_current_span(
            f"value_skill:{manifest.skill_id}",
            kind=SpanKind.INTERNAL,
        ) as span:
            # Agent attribution
            self._set_agent_attributes(span)

            # Core skill attributes
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

            # =========================================================
            # Value-specific manifest attributes
            # =========================================================
            span.set_attribute("value.total_capabilities", manifest.total_value_capabilities)

            if manifest.personas_covered:
                span.set_attribute("value.personas_covered", ",".join(manifest.personas_covered))
                span.set_attribute("value.persona_count", len(manifest.personas_covered))

            if manifest.channels_supported:
                span.set_attribute("value.channels_supported", ",".join(manifest.channels_supported))
                span.set_attribute("value.channel_count", len(manifest.channels_supported))

            # Cross-linking to technical skills
            if manifest.related_technical_skills:
                span.set_attribute(
                    "value.related_technical_skills",
                    ",".join(manifest.related_technical_skills)
                )

            # Timestamps
            span.set_attribute("skill.created_at", manifest.created_at.isoformat())
            span.set_attribute("skill.updated_at", manifest.updated_at.isoformat())

            # Project linkage
            if manifest.project_refs:
                span.set_attribute("skill.project_refs", ",".join(manifest.project_refs))

            # Lifecycle event
            span.add_event(
                "value_skill.registered",
                attributes={
                    "registered_by": self.agent_id,
                    "capability_count": manifest.total_value_capabilities,
                    "source_type": "value_markdown",
                    "personas_covered": len(manifest.personas_covered),
                    "channels_supported": len(manifest.channels_supported),
                }
            )

            span.set_status(Status(StatusCode.OK))

            # Store context for child capabilities
            span_context = span.get_span_context()
            self._skill_contexts[manifest.skill_id] = span_context
            trace_id = format(span_context.trace_id, "032x")

        return trace_id

    def emit_value_capability(
        self,
        skill_id: str,
        capability: ValueCapability,
        parent_trace_id: Optional[str] = None,
    ) -> str:
        """
        Emit a value capability as a span.

        Adds value-specific attributes for discovery.

        Args:
            skill_id: Parent skill identifier
            capability: The value capability to emit
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
            f"value_capability:{capability.capability_id}",
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

            # Knowledge-specific attributes
            span.set_attribute("knowledge.category", capability.knowledge_category)
            span.set_attribute("capability.source_section", capability.source_section)
            if capability.source_subsection:
                span.set_attribute("capability.source_subsection", capability.source_subsection)
            span.set_attribute("capability.line_range", capability.line_range)

            # Content analysis
            span.set_attribute("capability.has_code", capability.has_code)
            span.set_attribute("capability.has_tables", capability.has_tables)
            span.set_attribute("capability.code_block_count", capability.code_block_count)

            # Reference extraction
            if capability.tools:
                span.set_attribute("capability.tools", ",".join(capability.tools))
            if capability.ports:
                span.set_attribute("capability.ports", ",".join(capability.ports))
            if capability.env_vars:
                span.set_attribute("capability.env_vars", ",".join(capability.env_vars))
            if capability.paths:
                span.set_attribute("capability.paths", ",".join(capability.paths))

            # =========================================================
            # Value-specific attributes
            # =========================================================
            value = capability.value

            # Value type (direct, indirect, ripple)
            span.set_attribute("value.type", value.value_type)

            # Personas (both primary and list)
            primary_persona = value.get_primary_persona()
            span.set_attribute("value.persona", primary_persona)
            if value.personas:
                span.set_attribute("value.personas", ",".join([p for p in value.personas]))

            # Pain point and benefit (core value messaging)
            span.set_attribute("value.pain_point", value.pain_point)
            span.set_attribute("value.benefit", value.benefit)

            if value.pain_point_category:
                span.set_attribute("value.pain_point_category", value.pain_point_category)
            if value.benefit_metric:
                span.set_attribute("value.benefit_metric", value.benefit_metric)

            # Channels
            primary_channel = value.get_primary_channel()
            span.set_attribute("value.channel", primary_channel)
            if value.channels:
                span.set_attribute("value.channels", ",".join([c for c in value.channels]))

            # Value dimensions (for nuanced discovery)
            if value.time_savings:
                span.set_attribute("value.time_savings", value.time_savings)
            if value.cognitive_load_reduction:
                span.set_attribute("value.cognitive_load_reduction", value.cognitive_load_reduction)
            if value.error_prevention:
                span.set_attribute("value.error_prevention", value.error_prevention)

            # Creator-specific value (Audience of 1)
            if value.creator_direct_value:
                span.set_attribute("value.creator_direct", value.creator_direct_value)
            if value.creator_indirect_value:
                span.set_attribute("value.creator_indirect", value.creator_indirect_value)
            if value.creator_ripple_value:
                span.set_attribute("value.creator_ripple", value.creator_ripple_value)

            # Cross-linking (critical for value-to-technical discovery)
            if capability.related_skills:
                span.set_attribute("value.related_skills", ",".join(capability.related_skills))
            if capability.related_capabilities:
                span.set_attribute("value.related_capabilities", ",".join(capability.related_capabilities))

            # Pre-generated messaging
            if capability.slack_message:
                span.set_attribute("value.slack_message", capability.slack_message)
            if capability.email_subject:
                span.set_attribute("value.email_subject", capability.email_subject)
            if capability.one_liner:
                span.set_attribute("value.one_liner", capability.one_liner)

            # Value keywords for discovery
            if capability.value_keywords:
                span.set_attribute("value.keywords", ",".join(capability.value_keywords))

            # Evidence as events
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
                "value_capability.registered",
                attributes={
                    "registered_by": self.agent_id,
                    "session_id": self.session_id,
                    "source_type": "value_markdown",
                    "value_type": value.value_type,
                    "primary_persona": primary_persona,
                    "primary_channel": primary_channel,
                }
            )

            span.set_status(Status(StatusCode.OK))

            span_context = span.get_span_context()
            span_id = format(span_context.span_id, "016x")

            # Store for lifecycle events
            self._capability_spans[capability.capability_id] = span_id

        return span_id

    def emit_value_with_capabilities(
        self,
        manifest: ValueManifest,
        capabilities: list[ValueCapability],
    ) -> tuple[str, list[str]]:
        """
        Emit a complete value document with all capabilities.

        Convenience method that emits the manifest and all capabilities
        in a single call, properly linking them.

        Args:
            manifest: The value manifest
            capabilities: List of value capabilities to emit

        Returns:
            Tuple of (trace_id, list of span_ids)
        """
        trace_id = self.emit_value_manifest(manifest)

        span_ids = []
        for capability in capabilities:
            span_id = self.emit_value_capability(
                skill_id=manifest.skill_id,
                capability=capability,
                parent_trace_id=trace_id,
            )
            span_ids.append(span_id)

        return trace_id, span_ids

    def emit_cross_link(
        self,
        value_capability_id: str,
        technical_capability_id: str,
        technical_skill_id: str,
        link_type: str = "describes",
    ) -> str:
        """
        Emit a cross-link between value and technical capabilities.

        Creates a span that explicitly links a value proposition
        to its underlying technical capability.

        Args:
            value_capability_id: ID of the value capability
            technical_capability_id: ID of the technical capability
            technical_skill_id: ID of the skill containing the technical capability
            link_type: Type of relationship (describes, complements, extends)

        Returns:
            span_id of the cross-link span
        """
        with self.tracer.start_as_current_span(
            f"value_link:{value_capability_id}:{technical_capability_id}",
            kind=SpanKind.INTERNAL,
        ) as span:
            # Agent attribution
            self._set_agent_attributes(span)

            # Link attributes
            span.set_attribute("link.type", link_type)
            span.set_attribute("link.value_capability_id", value_capability_id)
            span.set_attribute("link.technical_capability_id", technical_capability_id)
            span.set_attribute("link.technical_skill_id", technical_skill_id)

            # Lifecycle event
            span.add_event(
                "value_link.created",
                attributes={
                    "created_by": self.agent_id,
                    "link_type": link_type,
                }
            )

            span.set_status(Status(StatusCode.OK))

            span_context = span.get_span_context()
            return format(span_context.span_id, "016x")
