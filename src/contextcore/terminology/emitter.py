"""
Terminology Emitter

Emit Wayfinder terminology definitions as OTel spans to Tempo,
enabling TraceQL-based discovery and agent guidance.

Example queries after emission:
    { term.id = "wayfinder" }
    { term.type = "implementation" }
    { term.category = "core_concepts" }
    { distinction.question =~ ".*ContextCore.*" }
    { routing.keyword = "suite" }
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode, Link

from contextcore.terminology.models import (
    TerminologyDistinction,
    TerminologyManifest,
    TerminologyTerm,
    TermToAvoid,
)


class TerminologyEmitter:
    """
    Emit terminology definitions as OTel spans.

    Follows the same patterns as SkillCapabilityEmitter:
    - Parent span for manifest
    - Child spans for individual terms
    - Additional spans for distinctions and routing
    - Agent attribution on all spans

    Usage:
        emitter = TerminologyEmitter(agent_id="terminology-emitter")

        # Emit complete terminology set
        trace_id, span_ids = emitter.emit_terminology(
            manifest, terms, distinctions, routing
        )

        # Or emit individually
        trace_id = emitter.emit_manifest(manifest)
        for term in terms:
            emitter.emit_term(term, parent_trace_id=trace_id)
    """

    def __init__(
        self,
        agent_id: str = "terminology-emitter",
        session_id: Optional[str] = None,
        tracer_name: str = "contextcore.terminology",
    ):
        """
        Initialize emitter with agent context.

        Args:
            agent_id: Agent identifier
            session_id: Session identifier (auto-generated if not provided)
            tracer_name: OTel tracer name
        """
        self.agent_id = agent_id
        self.session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
        self.tracer = trace.get_tracer(tracer_name)
        self._manifest_context: Optional[trace.SpanContext] = None

    def _set_agent_attributes(self, span) -> None:
        """Set common agent attribution attributes on a span."""
        span.set_attribute("agent.id", self.agent_id)
        span.set_attribute("agent.session_id", self.session_id)

    def emit_manifest(self, manifest: TerminologyManifest) -> str:
        """
        Emit terminology manifest as parent span.

        Args:
            manifest: The terminology manifest

        Returns:
            trace_id (hex string) for linking child spans
        """
        with self.tracer.start_as_current_span(
            f"terminology:{manifest.terminology_id}",
            kind=SpanKind.INTERNAL,
        ) as span:
            # Agent attribution
            self._set_agent_attributes(span)

            # Core attributes
            span.set_attribute("terminology.id", manifest.terminology_id)
            span.set_attribute("terminology.schema_version", manifest.schema_version)
            span.set_attribute("terminology.last_updated", manifest.last_updated)
            span.set_attribute("terminology.status", manifest.status)

            # Token budget
            span.set_attribute("terminology.manifest_tokens", manifest.manifest_tokens)
            span.set_attribute("terminology.index_tokens", manifest.index_tokens)
            span.set_attribute("terminology.total_tokens", manifest.total_tokens)

            # Counts
            term_count = sum(len(cat.terms) for cat in manifest.categories.values())
            span.set_attribute("terminology.term_count", term_count)
            span.set_attribute("terminology.category_count", len(manifest.categories))
            span.set_attribute("terminology.routing_count", len(manifest.routing))

            # Categories
            if manifest.categories:
                span.set_attribute(
                    "terminology.categories",
                    ",".join(manifest.categories.keys())
                )

            # Constraints as events
            for constraint in manifest.constraints:
                span.add_event(
                    "constraint.defined",
                    attributes={
                        "constraint.id": constraint.get("id", "unknown"),
                        "constraint.rule": constraint.get("rule", ""),
                    }
                )

            # Quick lookup entries as events
            for term_id, entry in manifest.quick_lookup.items():
                span.add_event(
                    "quick_lookup.entry",
                    attributes={
                        "term.id": term_id,
                        "term.type": entry.type,
                        "term.one_liner": entry.one_liner,
                        **({"term.analogy": entry.analogy} if entry.analogy else {}),
                        **({"term.producer": entry.producer} if entry.producer else {}),
                    }
                )

            # Lifecycle event
            span.add_event(
                "terminology.registered",
                attributes={
                    "registered_by": self.agent_id,
                    "term_count": term_count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            span.set_status(Status(StatusCode.OK))

            # Store context for child spans
            span_context = span.get_span_context()
            self._manifest_context = span_context
            trace_id = format(span_context.trace_id, "032x")

        return trace_id

    def emit_term(
        self,
        term: TerminologyTerm,
        parent_trace_id: Optional[str] = None,
    ) -> str:
        """
        Emit a terminology term as a span.

        Args:
            term: The term to emit
            parent_trace_id: Optional trace ID to link as parent

        Returns:
            span_id (hex string)
        """
        # Build links if we have parent context
        links = []
        if parent_trace_id and self._manifest_context:
            links.append(Link(self._manifest_context, attributes={"link.type": "child_of"}))

        with self.tracer.start_as_current_span(
            f"term:{term.id}",
            kind=SpanKind.INTERNAL,
            links=links,
        ) as span:
            # Agent attribution
            self._set_agent_attributes(span)

            # Core attributes
            span.set_attribute("term.id", term.id)
            span.set_attribute("term.name", term.name)
            span.set_attribute("term.type", term.type)
            span.set_attribute("term.version", term.version)
            span.set_attribute("term.definition", term.definition)

            # Optional attributes
            if term.category:
                span.set_attribute("term.category", term.category)
            if term.codename:
                span.set_attribute("term.codename", term.codename)
            if term.producer:
                span.set_attribute("term.producer", term.producer)

            # Package-specific attributes
            if term.anishinaabe_name:
                span.set_attribute("term.anishinaabe_name", term.anishinaabe_name)
            if term.package_name:
                span.set_attribute("term.package_name", term.package_name)
            if term.purpose:
                span.set_attribute("term.purpose", term.purpose)

            # Discovery attributes
            if term.triggers:
                span.set_attribute("term.triggers", ",".join(term.triggers))
            if term.related_terms:
                span.set_attribute("term.related_terms", ",".join(term.related_terms))

            # Token budget
            span.set_attribute("term.token_budget", term.token_budget)

            # Source tracking
            if term.source_file:
                span.set_attribute("term.source_file", term.source_file)

            # Persistence queries as events
            if term.tempo_query or term.loki_query:
                span.add_event(
                    "persistence.configured",
                    attributes={
                        **({"tempo_query": term.tempo_query} if term.tempo_query else {}),
                        **({"loki_query": term.loki_query} if term.loki_query else {}),
                    }
                )

            # Name origin as event (if complex)
            if term.name_origin:
                span.add_event(
                    "name_origin",
                    attributes={
                        "inspiration": term.name_origin.inspiration,
                        "meaning": term.name_origin.meaning[:200] if term.name_origin.meaning else "",
                        **({"reflects": ",".join(term.name_origin.reflects)} if term.name_origin.reflects else {}),
                    }
                )

            # Components as events (for implementation type)
            if term.components:
                for comp in term.components:
                    for comp_name, comp_desc in comp.items():
                        span.add_event(
                            "component",
                            attributes={
                                "component.name": comp_name,
                                "component.description": comp_desc,
                            }
                        )

            # Clarifications as events
            if term.is_not:
                for clarification in term.is_not:
                    span.add_event(
                        "is_not",
                        attributes={"clarification": clarification}
                    )

            # Lifecycle event
            span.add_event(
                "term.registered",
                attributes={
                    "registered_by": self.agent_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            span.set_status(Status(StatusCode.OK))

            span_context = span.get_span_context()
            return format(span_context.span_id, "016x")

    def emit_distinction(
        self,
        distinction: TerminologyDistinction,
        parent_trace_id: Optional[str] = None,
    ) -> str:
        """
        Emit a terminology distinction as a span.

        Distinctions help resolve common confusions between terms.

        Args:
            distinction: The distinction to emit
            parent_trace_id: Optional trace ID to link as parent

        Returns:
            span_id (hex string)
        """
        links = []
        if parent_trace_id and self._manifest_context:
            links.append(Link(self._manifest_context, attributes={"link.type": "child_of"}))

        with self.tracer.start_as_current_span(
            f"distinction:{distinction.id}",
            kind=SpanKind.INTERNAL,
            links=links,
        ) as span:
            # Agent attribution
            self._set_agent_attributes(span)

            # Core attributes
            span.set_attribute("distinction.id", distinction.id)
            span.set_attribute("distinction.question", distinction.question)
            span.set_attribute("distinction.answer", distinction.answer)

            if distinction.analogy:
                span.set_attribute("distinction.analogy", distinction.analogy)
            if distinction.terms_involved:
                span.set_attribute("distinction.terms_involved", ",".join(distinction.terms_involved))

            span.set_status(Status(StatusCode.OK))

            span_context = span.get_span_context()
            return format(span_context.span_id, "016x")

    def emit_routing(
        self,
        routing: Dict[str, str],
        parent_trace_id: Optional[str] = None,
    ) -> List[str]:
        """
        Emit routing table entries as spans.

        Routing maps keywords to term IDs for discovery.

        Args:
            routing: Dict of keyword -> term_id
            parent_trace_id: Optional trace ID to link as parent

        Returns:
            List of span_ids
        """
        span_ids = []

        for keyword, term_id in routing.items():
            links = []
            if parent_trace_id and self._manifest_context:
                links.append(Link(self._manifest_context, attributes={"link.type": "child_of"}))

            with self.tracer.start_as_current_span(
                f"routing:{keyword}",
                kind=SpanKind.INTERNAL,
                links=links,
            ) as span:
                self._set_agent_attributes(span)

                span.set_attribute("routing.keyword", keyword)
                span.set_attribute("routing.term_id", term_id)

                span.set_status(Status(StatusCode.OK))

                span_context = span.get_span_context()
                span_ids.append(format(span_context.span_id, "016x"))

        return span_ids

    def emit_avoid_term(
        self,
        avoid: TermToAvoid,
        parent_trace_id: Optional[str] = None,
    ) -> str:
        """
        Emit a term-to-avoid as a span.

        Args:
            avoid: The term to avoid entry
            parent_trace_id: Optional trace ID to link as parent

        Returns:
            span_id (hex string)
        """
        links = []
        if parent_trace_id and self._manifest_context:
            links.append(Link(self._manifest_context, attributes={"link.type": "child_of"}))

        with self.tracer.start_as_current_span(
            f"avoid:{avoid.term}",
            kind=SpanKind.INTERNAL,
            links=links,
        ) as span:
            self._set_agent_attributes(span)

            span.set_attribute("avoid.term", avoid.term)
            span.set_attribute("avoid.reason", avoid.reason)
            if avoid.alternatives:
                span.set_attribute("avoid.alternatives", ",".join(avoid.alternatives))

            span.set_status(Status(StatusCode.OK))

            span_context = span.get_span_context()
            return format(span_context.span_id, "016x")

    def emit_terminology(
        self,
        manifest: TerminologyManifest,
        terms: List[TerminologyTerm],
        distinctions: List[TerminologyDistinction],
        avoid_terms: List[TermToAvoid],
    ) -> Tuple[str, List[str]]:
        """
        Emit complete terminology set.

        Convenience method that emits manifest, all terms, distinctions,
        routing, and terms to avoid.

        Args:
            manifest: The terminology manifest
            terms: List of term definitions
            distinctions: List of distinctions
            avoid_terms: List of terms to avoid

        Returns:
            Tuple of (trace_id, list of all span_ids)
        """
        # Emit manifest first
        trace_id = self.emit_manifest(manifest)

        span_ids = []

        # Emit all terms
        for term in terms:
            span_id = self.emit_term(term, parent_trace_id=trace_id)
            span_ids.append(span_id)

        # Emit distinctions
        for distinction in distinctions:
            span_id = self.emit_distinction(distinction, parent_trace_id=trace_id)
            span_ids.append(span_id)

        # Emit routing table
        routing_ids = self.emit_routing(manifest.routing, parent_trace_id=trace_id)
        span_ids.extend(routing_ids)

        # Emit terms to avoid
        for avoid in avoid_terms:
            span_id = self.emit_avoid_term(avoid, parent_trace_id=trace_id)
            span_ids.append(span_id)

        return trace_id, span_ids

    def clear_context(self):
        """Clear stored manifest context."""
        self._manifest_context = None
