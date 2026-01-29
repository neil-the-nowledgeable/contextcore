"""
Agent Insight Emission and Query

Insights are agent-generated knowledge stored as OTel spans in Tempo,
enabling cross-agent collaboration and human visibility.
"""

from __future__ import annotations

import logging
import time as time_module
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from contextcore.contracts.timeouts import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_S,
    DEFAULT_RETRY_BACKOFF,
    RETRYABLE_HTTP_STATUS_CODES,
    HTTP_CLIENT_TIMEOUT_S,
)
from contextcore.compat.otel_genai import mapper

logger = logging.getLogger(__name__)


class InsightType(str, Enum):
    """Categories of agent-generated insights."""
    ANALYSIS = "analysis"
    RECOMMENDATION = "recommendation"
    DECISION = "decision"
    QUESTION = "question"
    BLOCKER = "blocker"
    DISCOVERY = "discovery"
    RISK = "risk"
    PROGRESS = "progress"
    LESSON = "lesson"  # Lessons learned for future sessions


class InsightAudience(str, Enum):
    """Intended consumer of the insight."""
    AGENT = "agent"
    HUMAN = "human"
    BOTH = "both"


@dataclass
class Evidence:
    """Supporting data for an insight."""
    type: str  # trace, log_query, file, commit, adr, doc, etc.
    ref: str
    description: str | None = None
    query: str | None = None
    timestamp: datetime | None = None


@dataclass
class Insight:
    """Agent-generated insight."""
    id: str
    type: InsightType
    summary: str
    confidence: float
    audience: InsightAudience
    project_id: str
    agent_id: str
    session_id: str
    rationale: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    supersedes: str | None = None
    expires_at: datetime | None = None
    trace_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # For lessons/decisions that apply to specific files or patterns
    applies_to: list[str] = field(default_factory=list)
    category: str | None = None  # For categorizing lessons (e.g., "testing", "architecture")


class InsightEmitter:
    """
    Emit agent insights as OTel spans.

    Insights are persisted in Tempo and queryable by other agents and humans.
    Optionally also saves to local JSON files for development without OTel.

    Example:
        # Production: emit to OTel only
        emitter = InsightEmitter(
            project_id="checkout-service",
            agent_id="claude-code",
            session_id="session-123"
        )

        # Development: also save locally
        emitter = InsightEmitter(
            project_id="checkout-service",
            agent_id="claude-code",
            local_storage_path="~/.contextcore/insights"
        )

        emitter.emit_decision(
            summary="Selected event-driven architecture",
            confidence=0.92,
            rationale="Lower coupling, aligns with ADR-015",
            evidence=[
                Evidence(type="adr", ref="ADR-015"),
                Evidence(type="trace", ref="abc123", description="Sync latency 200ms")
            ]
        )
    """

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        session_id: str | None = None,
        tracer_name: str = "contextcore.insights",
        local_storage_path: str | None = None,
        agent_name: str | None = None,
        agent_description: str | None = None,
    ):
        self.project_id = project_id
        self.agent_id = agent_id
        self.session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
        self.tracer = trace.get_tracer(tracer_name)
        self.local_storage_path = local_storage_path
        self.agent_name = agent_name
        self.agent_description = agent_description

    def emit(
        self,
        insight_type: InsightType,
        summary: str,
        confidence: float,
        audience: InsightAudience = InsightAudience.BOTH,
        rationale: str | None = None,
        evidence: list[Evidence] | None = None,
        supersedes: str | None = None,
        expires_at: datetime | None = None,
        applies_to: list[str] | None = None,
        category: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        response_model: str | None = None,
        response_id: str | None = None,
        finish_reasons: list[str] | None = None,
    ) -> Insight:
        """
        Emit an insight as an OTel span.

        Args:
            insight_type: Category of insight
            summary: Brief description (1-2 sentences)
            confidence: Confidence score (0.0-1.0)
            audience: Intended consumer
            rationale: Reasoning behind insight
            evidence: Supporting data references
            supersedes: ID of insight this replaces
            expires_at: When insight becomes stale
            applies_to: File paths/patterns this insight applies to
            category: Category for grouping (e.g., "testing", "architecture")
            provider: LLM provider (e.g. "openai", "anthropic"). Auto-detected if None.
            model: LLM model name (e.g. "gpt-4o"). Auto-detected if None.
            input_tokens: Number of input/prompt tokens used.
            output_tokens: Number of output/completion tokens generated.
            temperature: Sampling temperature for the request.
            top_p: Top-p (nucleus) sampling parameter.
            max_tokens: Maximum tokens requested for generation.
            response_model: Model that generated the response (may differ from request).
            response_id: Unique identifier for the LLM response.
            finish_reasons: Reasons the model stopped generating (e.g. ["stop"]).

        Returns:
            The emitted Insight with trace_id populated
        """
        insight_id = f"insight-{uuid.uuid4().hex[:12]}"
        evidence = evidence or []
        applies_to = applies_to or []

        # Auto-detect provider/model if not specified
        if not provider or not model:
            import os
            # Simple heuristic: check env vars or service name
            # This is a basic implementation - could be enhanced to check actual LLM client config
            svc = os.environ.get("OTEL_SERVICE_NAME", "")
            if not provider:
                if "claude" in svc or "anthropic" in svc:
                    provider = "anthropic"
                elif "gpt" in svc or "openai" in svc:
                    provider = "openai"
                
            if not model:
                # Try to extract model from service name if it looks like "provider-model"
                parts = svc.split("-")
                if len(parts) > 1 and parts[0] in ("claude", "gpt", "gemini"):
                    model = svc  # Use full service name as proxy for model

        with self.tracer.start_as_current_span(
            f"insight.{insight_type.value}",
            kind=SpanKind.INTERNAL,
        ) as span:
            # Build attributes dict for mapping
            attributes = {
                "insight.id": insight_id,
                "insight.type": insight_type.value,
                "insight.summary": summary,
                "insight.confidence": confidence,
                "insight.audience": audience.value,
                "project.id": self.project_id,
                "agent.id": self.agent_id,
                "agent.session_id": self.session_id,
                "gen_ai.operation.name": "insight.emit",
            }

            if provider:
                attributes["gen_ai.system"] = provider  # OTel standard for provider
            if model:
                attributes["gen_ai.request.model"] = model

            # Agent metadata (from constructor)
            if self.agent_name:
                attributes["gen_ai.agent.name"] = self.agent_name
            if self.agent_description:
                attributes["gen_ai.agent.description"] = self.agent_description

            # Token usage
            if input_tokens is not None:
                attributes["gen_ai.usage.input_tokens"] = input_tokens
            if output_tokens is not None:
                attributes["gen_ai.usage.output_tokens"] = output_tokens

            # Request parameters
            if temperature is not None:
                attributes["gen_ai.request.temperature"] = temperature
            if top_p is not None:
                attributes["gen_ai.request.top_p"] = top_p
            if max_tokens is not None:
                attributes["gen_ai.request.max_tokens"] = max_tokens

            # Response metadata
            if response_model:
                attributes["gen_ai.response.model"] = response_model
            if response_id:
                attributes["gen_ai.response.id"] = response_id
            if finish_reasons:
                attributes["gen_ai.response.finish_reasons"] = finish_reasons

            # Optional attributes
            if rationale:
                attributes["insight.rationale"] = rationale
            if supersedes:
                attributes["insight.supersedes"] = supersedes
            if expires_at:
                attributes["insight.expires_at"] = expires_at.isoformat()
            if applies_to:
                attributes["insight.applies_to"] = applies_to
            if category:
                attributes["insight.category"] = category

            # Map attributes (dual-emit support)
            mapped_attrs = mapper.map_attributes(attributes)
            
            # Set attributes on span
            for key, value in mapped_attrs.items():
                span.set_attribute(key, value)

            # Add evidence as events
            for ev in evidence:
                span.add_event(
                    "evidence.added",
                    attributes={
                        "evidence.type": ev.type,
                        "evidence.ref": ev.ref,
                        **({"evidence.description": ev.description} if ev.description else {}),
                        **({"evidence.query": ev.query} if ev.query else {}),
                    }
                )

            span.set_status(Status(StatusCode.OK))

            # Get trace ID
            span_context = span.get_span_context()
            trace_id = format(span_context.trace_id, "032x")

        insight = Insight(
            id=insight_id,
            type=insight_type,
            summary=summary,
            confidence=confidence,
            audience=audience,
            project_id=self.project_id,
            agent_id=self.agent_id,
            session_id=self.session_id,
            rationale=rationale,
            evidence=evidence,
            supersedes=supersedes,
            expires_at=expires_at,
            trace_id=trace_id,
            applies_to=applies_to,
            category=category,
        )

        # Also save to local storage if configured
        if self.local_storage_path:
            self._save_locally(insight)

        return insight

    def _save_locally(self, insight: Insight) -> None:
        """Save insight to local JSON file for development/offline use."""
        import json
        import os
        from pathlib import Path

        storage_path = Path(os.path.expanduser(self.local_storage_path))
        storage_path.mkdir(parents=True, exist_ok=True)

        file_path = storage_path / f"{self.project_id}_insights.json"

        # Load existing insights
        existing = []
        if file_path.exists():
            try:
                with open(file_path) as f:
                    existing = json.load(f)
            except json.JSONDecodeError:
                existing = []

        # Add new insight
        existing.append({
            "id": insight.id,
            "type": insight.type.value,
            "summary": insight.summary,
            "confidence": insight.confidence,
            "audience": insight.audience.value,
            "project_id": insight.project_id,
            "agent_id": insight.agent_id,
            "session_id": insight.session_id,
            "rationale": insight.rationale,
            "trace_id": insight.trace_id,
            "timestamp": insight.timestamp.isoformat(),
            "applies_to": insight.applies_to,
            "category": insight.category,
            "evidence": [
                {"type": e.type, "ref": e.ref, "description": e.description}
                for e in insight.evidence
            ],
        })

        # Write back
        with open(file_path, "w") as f:
            json.dump(existing, f, indent=2)

    def emit_decision(
        self,
        summary: str,
        confidence: float,
        **kwargs,
    ) -> Insight:
        """Emit a decision insight."""
        return self.emit(InsightType.DECISION, summary, confidence, **kwargs)

    def emit_recommendation(
        self,
        summary: str,
        confidence: float,
        **kwargs,
    ) -> Insight:
        """Emit a recommendation insight."""
        return self.emit(InsightType.RECOMMENDATION, summary, confidence, **kwargs)

    def emit_blocker(
        self,
        summary: str,
        confidence: float = 1.0,
        audience: InsightAudience = InsightAudience.BOTH,
        **kwargs,
    ) -> Insight:
        """Emit a blocker insight (defaults to high confidence, both audiences)."""
        return self.emit(InsightType.BLOCKER, summary, confidence, audience=audience, **kwargs)

    def emit_discovery(
        self,
        summary: str,
        confidence: float,
        **kwargs,
    ) -> Insight:
        """Emit a discovery insight."""
        return self.emit(InsightType.DISCOVERY, summary, confidence, **kwargs)

    def emit_progress(
        self,
        summary: str,
        confidence: float = 1.0,
        **kwargs,
    ) -> Insight:
        """Emit a progress update insight."""
        return self.emit(InsightType.PROGRESS, summary, confidence, **kwargs)

    def emit_lesson(
        self,
        summary: str,
        category: str,
        confidence: float = 0.9,
        applies_to: list[str] | None = None,
        **kwargs,
    ) -> Insight:
        """
        Emit a lesson learned for future sessions.

        Args:
            summary: What was learned
            category: Category (e.g., "testing", "architecture", "performance")
            confidence: Confidence score (defaults to 0.9)
            applies_to: File paths/patterns this lesson applies to

        Example:
            emitter.emit_lesson(
                summary="Always mock OTLP exporter in unit tests",
                category="testing",
                applies_to=["src/contextcore/tracker.py", "tests/"]
            )
        """
        return self.emit(
            InsightType.LESSON,
            summary,
            confidence,
            category=category,
            applies_to=applies_to,
            **kwargs,
        )


class InsightQuerier:
    """
    Query insights from Tempo or local file storage.

    Enables agents to access insights from other agents without
    parsing chat transcripts.

    Supports two modes:
    - Tempo mode: Query insights from Tempo via HTTP API (production)
    - Local mode: Query insights from JSON files (development)

    Example:
        # Production: query Tempo
        querier = InsightQuerier(tempo_url="http://localhost:3200")

        # Development: query local files
        querier = InsightQuerier(local_storage_path="~/.contextcore/insights")

        # Get recent decisions for a project
        decisions = querier.query(
            project_id="checkout-service",
            insight_type=InsightType.DECISION,
            min_confidence=0.8,
            time_range="24h"
        )

        # Get lessons for a specific file
        lessons = querier.query(
            project_id="my-project",
            insight_type=InsightType.LESSON,
            applies_to="src/contextcore/tracker.py"
        )
    """

    def __init__(
        self,
        tempo_url: str | None = "http://localhost:3200",
        local_storage_path: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY_S,
    ):
        """
        Initialize the querier.

        Args:
            tempo_url: Tempo HTTP API URL (set to None to disable Tempo)
            local_storage_path: Path for local JSON storage fallback
            max_retries: Maximum number of retry attempts for transient failures
            retry_delay: Initial delay between retries (uses exponential backoff)
        """
        self.tempo_url = tempo_url
        self.local_storage_path = local_storage_path
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._http_client = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close HTTP client."""
        self.close()
        return False

    def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception as e:
                logger.debug(f"Error closing HTTP client: {e}")
            finally:
                self._http_client = None

    def _get_http_client(self):
        """Lazy-load httpx client."""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.Client(timeout=HTTP_CLIENT_TIMEOUT_S)
        return self._http_client

    def _request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int | None = None,
        **kwargs,
    ) -> "httpx.Response":
        """
        Execute HTTP request with retry logic for transient failures.

        Args:
            method: HTTP method (get, post, etc.)
            url: Request URL
            max_retries: Override default max retries
            **kwargs: Additional arguments for httpx request

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPStatusError: For non-retryable errors after all retries exhausted
        """
        import httpx

        client = self._get_http_client()
        retries = max_retries if max_retries is not None else self.max_retries
        delay = self.retry_delay
        last_error = None

        for attempt in range(retries + 1):
            try:
                response = getattr(client, method)(url, **kwargs)

                # Check for retryable status codes
                if response.status_code in RETRYABLE_HTTP_STATUS_CODES:
                    if attempt < retries:
                        logger.warning(
                            f"Tempo returned {response.status_code} for {url}, "
                            f"retrying in {delay:.1f}s (attempt {attempt + 1}/{retries + 1})"
                        )
                        time_module.sleep(delay)
                        delay *= DEFAULT_RETRY_BACKOFF
                        continue
                    else:
                        logger.error(
                            f"Tempo returned {response.status_code} for {url} "
                            f"after {retries + 1} attempts"
                        )

                return response

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < retries:
                    logger.warning(
                        f"Tempo request to {url} failed: {e}, "
                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{retries + 1})"
                    )
                    time_module.sleep(delay)
                    delay *= DEFAULT_RETRY_BACKOFF
                else:
                    logger.error(
                        f"Tempo request to {url} failed after {retries + 1} attempts: {e}"
                    )
                    raise

        # Should not reach here, but handle edge case
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected retry loop exit")

    def _parse_time_range(self, time_range: str) -> int:
        """Parse time range string to seconds."""
        import re
        match = re.match(r"(\d+)([smhd])", time_range)
        if not match:
            return 86400  # Default 24h

        value, unit = int(match.group(1)), match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return value * multipliers.get(unit, 3600)

    def query(
        self,
        project_id: str | None = None,
        insight_type: InsightType | str | None = None,
        agent_id: str | None = None,
        audience: InsightAudience | str | None = None,
        min_confidence: float | None = None,
        time_range: str = "24h",
        limit: int = 100,
        applies_to: str | None = None,
        category: str | None = None,
    ) -> list[Insight]:
        """
        Query insights from Tempo or local storage.

        Args:
            project_id: Filter by project
            insight_type: Filter by insight type
            agent_id: Filter by agent
            audience: Filter by audience (agent, human, both)
            min_confidence: Minimum confidence score
            time_range: Time range (e.g., "1h", "24h", "7d")
            limit: Maximum results
            applies_to: Filter by file path (partial match)
            category: Filter by category

        Returns:
            List of matching Insights
        """
        # Try Tempo first, fall back to local storage
        if self.tempo_url:
            try:
                return self._query_tempo(
                    project_id=project_id,
                    insight_type=insight_type,
                    agent_id=agent_id,
                    audience=audience,
                    min_confidence=min_confidence,
                    time_range=time_range,
                    limit=limit,
                    applies_to=applies_to,
                    category=category,
                )
            except Exception as e:
                import warnings
                warnings.warn(f"Tempo query failed: {e}. Falling back to local storage.")

        if self.local_storage_path:
            return self._query_local(
                project_id=project_id,
                insight_type=insight_type,
                agent_id=agent_id,
                audience=audience,
                min_confidence=min_confidence,
                time_range=time_range,
                limit=limit,
                applies_to=applies_to,
                category=category,
            )

        return []

    def _query_tempo(
        self,
        project_id: str | None,
        insight_type: InsightType | str | None,
        agent_id: str | None,
        audience: InsightAudience | str | None,
        min_confidence: float | None,
        time_range: str,
        limit: int,
        applies_to: str | None,
        category: str | None,
    ) -> list[Insight]:
        """Execute TraceQL query against Tempo HTTP API."""
        # Build TraceQL query
        conditions = ['name =~ "insight.*"']

        if insight_type:
            type_val = insight_type.value if isinstance(insight_type, InsightType) else insight_type
            conditions.append(f'span.insight.type = "{type_val}"')

        if project_id:
            conditions.append(f'span.project.id = "{project_id}"')

        if agent_id:
            conditions.append(f'span.agent.id = "{agent_id}"')

        if audience:
            aud_val = audience.value if isinstance(audience, InsightAudience) else audience
            conditions.append(f'span.insight.audience = "{aud_val}"')

        if min_confidence is not None:
            conditions.append(f"span.insight.confidence >= {min_confidence}")

        if category:
            conditions.append(f'span.insight.category = "{category}"')

        query = "{ " + " && ".join(conditions) + " }"

        # Calculate time range
        end_ns = int(time_module.time() * 1_000_000_000)
        start_ns = end_ns - (self._parse_time_range(time_range) * 1_000_000_000)

        # Execute query via Tempo HTTP API with retry
        response = self._request_with_retry(
            "get",
            f"{self.tempo_url}/api/search",
            params={
                "q": query,
                "start": start_ns,
                "end": end_ns,
                "limit": limit,
            },
        )
        response.raise_for_status()

        # Validate response format
        try:
            data = response.json()
        except ValueError as e:
            logger.error(f"Tempo returned invalid JSON: {e}")
            return []

        if not isinstance(data, dict):
            logger.error(f"Tempo returned unexpected response type: {type(data).__name__}")
            return []

        # Parse traces into Insights
        insights = []
        traces_to_fetch = data.get("traces", [])

        if not isinstance(traces_to_fetch, list):
            logger.warning(f"Tempo 'traces' field is not a list: {type(traces_to_fetch).__name__}")
            traces_to_fetch = []

        # Limit trace fetches to avoid overwhelming Tempo
        max_trace_fetches = min(len(traces_to_fetch), limit * 2)  # Allow some buffer for filtering

        for trace_data in traces_to_fetch[:max_trace_fetches]:
            trace_id = trace_data.get("traceID", "")

            # Fetch full trace to get span details with shorter timeout for individual traces
            try:
                trace_response = self._request_with_retry(
                    "get",
                    f"{self.tempo_url}/api/traces/{trace_id}",
                    max_retries=1,  # Fewer retries for individual trace fetches
                )
                if trace_response.status_code != 200:
                    logger.debug(f"Failed to fetch trace {trace_id}: {trace_response.status_code}")
                    continue

                trace_detail = trace_response.json()
                for batch in trace_detail.get("batches", []):
                    for span in batch.get("scopeSpans", [{}])[0].get("spans", []):
                        insight = self._span_to_insight(span, trace_id)
                        if insight:
                            # Apply applies_to filter (post-query since Tempo doesn't support array contains)
                            if applies_to:
                                if not any(applies_to in path for path in insight.applies_to):
                                    continue
                            insights.append(insight)

                            # Early exit if we have enough insights
                            if len(insights) >= limit:
                                return insights[:limit]

            except Exception as e:
                logger.debug(f"Error fetching trace {trace_id}: {e}")
                continue

        return insights[:limit]

    def _span_to_insight(self, span: dict, trace_id: str) -> Insight | None:
        """Convert a Tempo span to an Insight object."""
        attrs = {}
        for attr in span.get("attributes", []):
            key = attr.get("key", "")
            value = attr.get("value", {})
            # Handle different value types
            if "stringValue" in value:
                attrs[key] = value["stringValue"]
            elif "intValue" in value:
                attrs[key] = int(value["intValue"])
            elif "doubleValue" in value:
                attrs[key] = float(value["doubleValue"])
            elif "arrayValue" in value:
                attrs[key] = [
                    v.get("stringValue", "") for v in value["arrayValue"].get("values", [])
                ]

        # Validate required fields exist
        insight_id = attrs.get("insight.id")
        insight_type_str = attrs.get("insight.type")
        insight_summary = attrs.get("insight.summary")

        if not insight_id:
            logger.debug(f"Skipping span in trace {trace_id}: missing insight.id")
            return None

        if not insight_type_str:
            logger.debug(f"Skipping insight {insight_id}: missing insight.type")
            return None

        # Extract insight fields
        try:
            return Insight(
                id=insight_id,
                type=InsightType(insight_type_str),
                summary=insight_summary or "",
                confidence=float(attrs.get("insight.confidence", 0.0)),
                audience=InsightAudience(attrs.get("insight.audience", "both")),
                project_id=attrs.get("project.id", ""),
                agent_id=attrs.get("agent.id", ""),
                session_id=attrs.get("agent.session_id", ""),
                rationale=attrs.get("insight.rationale"),
                trace_id=trace_id,
                applies_to=attrs.get("insight.applies_to", []),
                category=attrs.get("insight.category"),
            )
        except (ValueError, KeyError) as e:
            logger.debug(f"Failed to parse insight {insight_id} from trace {trace_id}: {e}")
            return None

    def _query_local(
        self,
        project_id: str | None,
        insight_type: InsightType | str | None,
        agent_id: str | None,
        audience: InsightAudience | str | None,
        min_confidence: float | None,
        time_range: str,
        limit: int,
        applies_to: str | None,
        category: str | None,
    ) -> list[Insight]:
        """Query insights from local JSON file storage."""
        import json
        import os
        from pathlib import Path

        storage_path = Path(os.path.expanduser(self.local_storage_path))
        if not storage_path.exists():
            return []

        # Calculate cutoff time
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=self._parse_time_range(time_range)
        )

        insights = []

        # Read all insight files for the project
        pattern = f"{project_id or '*'}_insights.json"
        for file_path in storage_path.glob(pattern):
            try:
                with open(file_path) as f:
                    data = json.load(f)

                for item in data:
                    # Parse timestamp
                    ts = datetime.fromisoformat(item.get("timestamp", "2000-01-01"))
                    if ts < cutoff:
                        continue

                    # Apply filters
                    if insight_type:
                        type_val = insight_type.value if isinstance(insight_type, InsightType) else insight_type
                        if item.get("type") != type_val:
                            continue

                    if project_id and item.get("project_id") != project_id:
                        continue

                    if agent_id and item.get("agent_id") != agent_id:
                        continue

                    if audience:
                        aud_val = audience.value if isinstance(audience, InsightAudience) else audience
                        if item.get("audience") != aud_val:
                            continue

                    if min_confidence and float(item.get("confidence", 0)) < min_confidence:
                        continue

                    if category and item.get("category") != category:
                        continue

                    if applies_to:
                        item_applies_to = item.get("applies_to", [])
                        if not any(applies_to in path for path in item_applies_to):
                            continue

                    # Create Insight object
                    insights.append(Insight(
                        id=item.get("id", ""),
                        type=InsightType(item.get("type", "analysis")),
                        summary=item.get("summary", ""),
                        confidence=float(item.get("confidence", 0.0)),
                        audience=InsightAudience(item.get("audience", "both")),
                        project_id=item.get("project_id", ""),
                        agent_id=item.get("agent_id", ""),
                        session_id=item.get("session_id", ""),
                        rationale=item.get("rationale"),
                        trace_id=item.get("trace_id"),
                        timestamp=ts,
                        applies_to=item.get("applies_to", []),
                        category=item.get("category"),
                    ))
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by timestamp descending
        insights.sort(key=lambda x: x.timestamp, reverse=True)
        return insights[:limit]

    def get_blockers(
        self,
        project_id: str,
        include_agent_only: bool = False,
    ) -> list[Insight]:
        """Get unresolved blockers for a project."""
        audience = None if include_agent_only else InsightAudience.BOTH
        return self.query(
            project_id=project_id,
            insight_type=InsightType.BLOCKER,
            audience=audience,
        )

    def get_recent_decisions(
        self,
        project_id: str,
        time_range: str = "7d",
        min_confidence: float = 0.8,
    ) -> list[Insight]:
        """Get recent high-confidence decisions."""
        return self.query(
            project_id=project_id,
            insight_type=InsightType.DECISION,
            min_confidence=min_confidence,
            time_range=time_range,
        )

    def get_lessons(
        self,
        project_id: str,
        applies_to: str | None = None,
        category: str | None = None,
        time_range: str = "30d",
    ) -> list[Insight]:
        """
        Get lessons learned for a project.

        Args:
            project_id: Project to query
            applies_to: Filter by file path (partial match)
            category: Filter by category (e.g., "testing", "architecture")
            time_range: Time range to search

        Returns:
            List of lesson insights
        """
        return self.query(
            project_id=project_id,
            insight_type=InsightType.LESSON,
            applies_to=applies_to,
            category=category,
            time_range=time_range,
        )
