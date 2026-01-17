"""
Skill Capability Emitter

Emit skill capabilities as OTel spans to Tempo, enabling
TraceQL-based capability discovery and agent-to-agent communication.

Integrates with ContextCore patterns:
- Agent attribution (agent.id, agent.session_id)
- Project linkage (project.id, project_refs)
- Insight system (discovery insights on queries)
- Lifecycle events (registered, invoked, succeeded, failed)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode, Link
from opentelemetry.trace.propagation import get_current_span

from contextcore.skill.models import (
    Audience,
    Evidence,
    SkillCapability,
    SkillManifest,
)


class SkillCapabilityEmitter:
    """
    Emit skill capabilities as OTel spans.

    Skills become parent spans containing capability child spans,
    mirroring the epic -> story -> task hierarchy in TaskTracker.

    Integrates with ContextCore patterns:
    - Agent attribution: All spans tagged with agent.id, agent.session_id
    - Project linkage: Skills can be linked to projects
    - Lifecycle events: capability.registered, capability.invoked, etc.

    Example:
        emitter = SkillCapabilityEmitter(
            agent_id="claude-code",
            session_id="session-abc123",
            project_id="checkout-service"  # Optional
        )

        # Emit entire skill from manifest
        trace_id = emitter.emit_skill(manifest)

        # Emit capabilities as child spans
        for capability in capabilities:
            emitter.emit_capability(
                skill_id="llm-formatter",
                capability=capability,
                parent_trace_id=trace_id
            )

        # Track capability invocation
        emitter.emit_lifecycle_event(
            skill_id="llm-formatter",
            capability_id="transform_document",
            event_type="invoked",
            inputs={"source": "SKILL.md"}
        )
    """

    def __init__(
        self,
        agent_id: str = "unknown",
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        tracer_name: str = "contextcore.skills",
    ):
        """
        Initialize emitter with agent context.

        Args:
            agent_id: Agent identifier (e.g., "claude-code", "dev-tour-guide")
            session_id: Session identifier (auto-generated if not provided)
            project_id: Optional project context for linking
            tracer_name: OTel tracer name
        """
        self.agent_id = agent_id
        self.session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
        self.project_id = project_id
        self.tracer = trace.get_tracer(tracer_name)
        self._skill_contexts: dict[str, trace.SpanContext] = {}
        self._capability_spans: dict[str, str] = {}  # capability_id -> span_id

    def _set_agent_attributes(self, span) -> None:
        """Set common agent attribution attributes on a span."""
        span.set_attribute("agent.id", self.agent_id)
        span.set_attribute("agent.session_id", self.session_id)
        if self.project_id:
            span.set_attribute("project.id", self.project_id)

    def emit_skill(self, manifest: SkillManifest) -> str:
        """
        Emit a skill manifest as a parent span.

        Args:
            manifest: The skill manifest to emit

        Returns:
            trace_id (hex string) for linking child capabilities
        """
        with self.tracer.start_as_current_span(
            f"skill:{manifest.skill_id}",
            kind=SpanKind.INTERNAL,
        ) as span:
            # Agent attribution
            self._set_agent_attributes(span)

            # Core attributes
            span.set_attribute("skill.id", manifest.skill_id)
            span.set_attribute("skill.type", manifest.skill_type)
            span.set_attribute("skill.version", manifest.version)
            span.set_attribute("skill.description", manifest.description)

            # Token budget tracking
            span.set_attribute("skill.manifest_tokens", manifest.manifest_tokens)
            span.set_attribute("skill.index_tokens", manifest.index_tokens)
            span.set_attribute("skill.total_tokens", manifest.total_tokens)
            span.set_attribute("skill.compressed_tokens", manifest.compressed_tokens)

            # Capability references (for discovery)
            span.set_attribute("skill.capability_count", len(manifest.capability_refs))
            if manifest.capability_refs:
                span.set_attribute("skill.capabilities", ",".join(manifest.capability_refs))

            # Constraints
            if manifest.constraints:
                span.set_attribute("skill.constraints", ",".join(manifest.constraints))

            # Source path (for parser reference)
            if manifest.source_path:
                span.set_attribute("skill.source_path", manifest.source_path)

            # Timestamps
            span.set_attribute("skill.created_at", manifest.created_at.isoformat())
            span.set_attribute("skill.updated_at", manifest.updated_at.isoformat())

            # Project linkage
            if manifest.project_refs:
                span.set_attribute("skill.project_refs", ",".join(manifest.project_refs))

            # Quick actions as events
            for qa in manifest.quick_actions:
                span.add_event(
                    "quick_action",
                    attributes={
                        "action.name": qa.name,
                        "action.capability_id": qa.capability_id,
                        "action.description": qa.description,
                    }
                )

            # Lifecycle event: skill.registered
            span.add_event(
                "skill.registered",
                attributes={
                    "registered_by": self.agent_id,
                    "capability_count": len(manifest.capability_refs),
                }
            )

            span.set_status(Status(StatusCode.OK))

            # Store context for child capabilities
            span_context = span.get_span_context()
            self._skill_contexts[manifest.skill_id] = span_context
            trace_id = format(span_context.trace_id, "032x")

        return trace_id

    def emit_capability(
        self,
        skill_id: str,
        capability: SkillCapability,
        parent_trace_id: Optional[str] = None,
    ) -> str:
        """
        Emit a capability as a span.

        When parent_trace_id is provided, the capability span links to
        the parent skill span for hierarchical queries.

        Args:
            skill_id: Parent skill identifier
            capability: The capability to emit
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

            # Audience (derived from interop scores or explicit)
            audience = capability.get_audience()
            span.set_attribute("capability.audience", audience.value)

            # Confidence and reliability
            span.set_attribute("capability.confidence", capability.confidence)
            if capability.success_rate is not None:
                span.set_attribute("capability.success_rate", capability.success_rate)
            span.set_attribute("capability.invocation_count", capability.invocation_count)

            # Timestamps
            span.set_attribute("capability.created_at", capability.created_at.isoformat())
            span.set_attribute("capability.updated_at", capability.updated_at.isoformat())
            if capability.expires_at:
                span.set_attribute("capability.expires_at", capability.expires_at.isoformat())

            # Version evolution
            if capability.supersedes:
                span.set_attribute("capability.supersedes", capability.supersedes)

            # Project linkage
            if capability.project_refs:
                span.set_attribute("capability.project_refs", ",".join(capability.project_refs))

            # Anti-patterns
            if capability.anti_patterns:
                span.set_attribute("capability.anti_patterns", ",".join(capability.anti_patterns))

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
                if ev.query:
                    ev_attrs["evidence.query"] = ev.query
                if ev.timestamp:
                    ev_attrs["evidence.timestamp"] = ev.timestamp.isoformat()

                span.add_event("evidence.added", attributes=ev_attrs)

            # Inputs as events
            for inp in capability.inputs:
                span.add_event(
                    "input.defined",
                    attributes={
                        "input.name": inp.name,
                        "input.type": inp.type,
                        "input.required": inp.required,
                        "input.description": inp.description,
                        **({"input.default": inp.default} if inp.default else {}),
                        **({"input.enum_values": ",".join(inp.enum_values)} if inp.enum_values else {}),
                    }
                )

            # Outputs as events
            for out in capability.outputs:
                span.add_event(
                    "output.defined",
                    attributes={
                        "output.name": out.name,
                        "output.type": out.type,
                        "output.description": out.description,
                    }
                )

            # Lifecycle event: capability.registered
            span.add_event(
                "capability.registered",
                attributes={
                    "registered_by": self.agent_id,
                    "session_id": self.session_id,
                }
            )

            span.set_status(Status(StatusCode.OK))

            span_context = span.get_span_context()
            span_id = format(span_context.span_id, "016x")

            # Store for lifecycle events
            self._capability_spans[capability.capability_id] = span_id

        return span_id

    def emit_skill_with_capabilities(
        self,
        manifest: SkillManifest,
        capabilities: list[SkillCapability],
    ) -> tuple[str, list[str]]:
        """
        Emit a complete skill with all capabilities.

        Convenience method that emits the manifest and all capabilities
        in a single call, properly linking them.

        Args:
            manifest: The skill manifest
            capabilities: List of capabilities to emit

        Returns:
            Tuple of (trace_id, list of span_ids)
        """
        trace_id = self.emit_skill(manifest)

        span_ids = []
        for capability in capabilities:
            span_id = self.emit_capability(
                skill_id=manifest.skill_id,
                capability=capability,
                parent_trace_id=trace_id,
            )
            span_ids.append(span_id)

        return trace_id, span_ids

    def clear_contexts(self):
        """Clear stored skill contexts."""
        self._skill_contexts.clear()
        self._capability_spans.clear()

    # -------------------------------------------------------------------------
    # Lifecycle Events
    # -------------------------------------------------------------------------

    def emit_lifecycle_event(
        self,
        skill_id: str,
        capability_id: str,
        event_type: str,
        inputs: Optional[dict] = None,
        outputs: Optional[dict] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
        handoff_id: Optional[str] = None,
    ) -> str:
        """
        Emit a capability lifecycle event.

        Lifecycle events track capability usage patterns:
        - capability.invoked: When a capability is called
        - capability.succeeded: When invocation completes successfully
        - capability.failed: When invocation fails
        - capability.deprecated: When capability is marked for removal

        Args:
            skill_id: Skill identifier
            capability_id: Capability identifier
            event_type: Event type (invoked, succeeded, failed, deprecated)
            inputs: Optional input parameters used
            outputs: Optional output produced
            error: Error message for failed events
            duration_ms: Execution duration in milliseconds
            handoff_id: Link to handoff that triggered this invocation

        Returns:
            span_id for the event span
        """
        with self.tracer.start_as_current_span(
            f"capability.{event_type}",
            kind=SpanKind.INTERNAL,
        ) as span:
            # Agent attribution
            self._set_agent_attributes(span)

            # Capability reference
            span.set_attribute("skill.id", skill_id)
            span.set_attribute("capability.id", capability_id)
            span.set_attribute("lifecycle.event", event_type)

            # Timing
            span.set_attribute("lifecycle.timestamp", datetime.now(timezone.utc).isoformat())
            if duration_ms is not None:
                span.set_attribute("lifecycle.duration_ms", duration_ms)

            # Handoff linkage (enables tracing handoff -> invocation)
            if handoff_id:
                span.set_attribute("handoff.id", handoff_id)

            # Input/output tracking
            if inputs:
                for key, value in inputs.items():
                    span.set_attribute(f"input.{key}", str(value))

            if outputs:
                for key, value in outputs.items():
                    span.set_attribute(f"output.{key}", str(value))

            # Error details
            if error:
                span.set_attribute("error.message", error)
                span.set_status(Status(StatusCode.ERROR, error))
            else:
                span.set_status(Status(StatusCode.OK))

            span_context = span.get_span_context()
            return format(span_context.span_id, "016x")

    def emit_invoked(
        self,
        skill_id: str,
        capability_id: str,
        inputs: Optional[dict] = None,
        handoff_id: Optional[str] = None,
    ) -> str:
        """
        Emit capability.invoked event.

        Call this when a capability invocation starts.
        """
        return self.emit_lifecycle_event(
            skill_id=skill_id,
            capability_id=capability_id,
            event_type="invoked",
            inputs=inputs,
            handoff_id=handoff_id,
        )

    def emit_succeeded(
        self,
        skill_id: str,
        capability_id: str,
        outputs: Optional[dict] = None,
        duration_ms: Optional[int] = None,
        handoff_id: Optional[str] = None,
    ) -> str:
        """
        Emit capability.succeeded event.

        Call this when a capability invocation completes successfully.
        """
        return self.emit_lifecycle_event(
            skill_id=skill_id,
            capability_id=capability_id,
            event_type="succeeded",
            outputs=outputs,
            duration_ms=duration_ms,
            handoff_id=handoff_id,
        )

    def emit_failed(
        self,
        skill_id: str,
        capability_id: str,
        error: str,
        duration_ms: Optional[int] = None,
        handoff_id: Optional[str] = None,
    ) -> str:
        """
        Emit capability.failed event.

        Call this when a capability invocation fails.
        """
        return self.emit_lifecycle_event(
            skill_id=skill_id,
            capability_id=capability_id,
            event_type="failed",
            error=error,
            duration_ms=duration_ms,
            handoff_id=handoff_id,
        )
