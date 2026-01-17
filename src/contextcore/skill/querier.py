"""
Skill Capability Querier

Query skill capabilities from Tempo via TraceQL, enabling
agents to discover capabilities without loading full skill content.

Integrates with ContextCore patterns:
- Discovery insights: Emits insight.discovery when capabilities are found
- Agent attribution: Queries can filter by agent.id, agent.session_id
- Audience filtering: Filter by capability.audience (agent, human, both)
"""

from __future__ import annotations

import json
import uuid
import warnings
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlencode

import requests

from contextcore.skill.models import (
    Audience,
    CapabilityCategory,
    Evidence,
    CapabilityInput,
    CapabilityOutput,
    EvidenceType,
    SkillCapability,
    SkillManifest,
    SkillType,
)

if TYPE_CHECKING:
    from contextcore.agent.insights import InsightEmitter


class SkillCapabilityQuerier:
    """
    Query skill capabilities from Tempo.

    Enables agents to discover capabilities without loading full skill content.
    Uses TraceQL to query spans emitted by SkillCapabilityEmitter.

    Integrates with insight system:
    - Automatically emits insight.discovery when capabilities are found
    - This enables other agents to learn from capability usage patterns

    Example:
        # Basic querier
        querier = SkillCapabilityQuerier(tempo_url="http://localhost:3200")

        # With insight emission (recommended for agent use)
        from contextcore.agent.insights import InsightEmitter
        insight_emitter = InsightEmitter(
            project_id="checkout-service",
            agent_id="claude-code",
            session_id="session-123"
        )
        querier = SkillCapabilityQuerier(
            tempo_url="http://localhost:3200",
            insight_emitter=insight_emitter
        )

        # Find capabilities by trigger keyword
        caps = querier.query_by_trigger("format")
        # → Automatically emits: insight.discovery("Found 3 capabilities matching 'format'")

        # Find capabilities by category
        caps = querier.query_by_category(CapabilityCategory.TRANSFORM)

        # Get all capabilities under token budget
        caps = querier.query_within_budget(max_tokens=500)

        # Find high-confidence, agent-optimized capabilities
        caps = querier.query(
            audience=Audience.AGENT,
            min_confidence=0.9
        )

        # Get routing table for a skill
        routing = querier.get_routing_table("llm-formatter")
        # Returns: {"format": "transform_document", "convert": "transform_document", ...}
    """

    def __init__(
        self,
        tempo_url: str = "http://localhost:3200",
        timeout: int = 30,
        insight_emitter: Optional["InsightEmitter"] = None,
        emit_discoveries: bool = True,
    ):
        """
        Initialize querier.

        Args:
            tempo_url: Tempo API URL
            timeout: Request timeout in seconds
            insight_emitter: Optional InsightEmitter for discovery insights
            emit_discoveries: Whether to emit discovery insights (default True)
        """
        self.tempo_url = tempo_url.rstrip("/")
        self.timeout = timeout
        self.insight_emitter = insight_emitter
        self.emit_discoveries = emit_discoveries and insight_emitter is not None

    def query(
        self,
        skill_id: Optional[str] = None,
        capability_id: Optional[str] = None,
        category: Optional[CapabilityCategory | str] = None,
        trigger: Optional[str] = None,
        max_tokens: Optional[int] = None,
        min_interop_agent: Optional[int] = None,
        audience: Optional[Audience | str] = None,
        min_confidence: Optional[float] = None,
        project_ref: Optional[str] = None,
        agent_id: Optional[str] = None,
        time_range: str = "24h",
        limit: int = 100,
        emit_insight: bool = True,
    ) -> list[SkillCapability]:
        """
        Query capabilities from Tempo.

        Args:
            skill_id: Filter by skill ID
            capability_id: Filter by capability ID
            category: Filter by category
            trigger: Filter by trigger keyword (partial match)
            max_tokens: Maximum token budget
            min_interop_agent: Minimum agent interop score
            audience: Filter by intended audience (agent, human, both)
            min_confidence: Minimum confidence score (0.0-1.0)
            project_ref: Filter by project reference
            agent_id: Filter by agent that registered the capability
            time_range: Time range (e.g., "1h", "24h", "7d")
            limit: Maximum results
            emit_insight: Whether to emit discovery insight (default True)

        Returns:
            List of matching SkillCapability objects
        """
        conditions = ['name =~ "capability:.*"']

        if skill_id:
            conditions.append(f'skill.id = "{skill_id}"')

        if capability_id:
            conditions.append(f'capability.id = "{capability_id}"')

        if category:
            cat_val = category.value if isinstance(category, CapabilityCategory) else category
            conditions.append(f'capability.category = "{cat_val}"')

        if trigger:
            conditions.append(f'capability.triggers =~ ".*{trigger}.*"')

        if max_tokens is not None:
            conditions.append(f'capability.token_budget < {max_tokens}')

        if min_interop_agent is not None:
            conditions.append(f'capability.interop_agent >= {min_interop_agent}')

        if audience:
            aud_val = audience.value if isinstance(audience, Audience) else audience
            conditions.append(f'capability.audience = "{aud_val}"')

        if min_confidence is not None:
            conditions.append(f'capability.confidence >= {min_confidence}')

        if project_ref:
            conditions.append(f'capability.project_refs =~ ".*{project_ref}.*"')

        if agent_id:
            conditions.append(f'agent.id = "{agent_id}"')

        query = "{ " + " && ".join(conditions) + " }"
        results = self._execute_traceql(query, time_range, limit)

        # Emit discovery insight if enabled and we found results
        if emit_insight and self.emit_discoveries and results:
            self._emit_discovery_insight(
                results=results,
                trigger=trigger,
                category=category,
                query=query,
            )

        return results

    def _emit_discovery_insight(
        self,
        results: list[SkillCapability],
        trigger: Optional[str] = None,
        category: Optional[CapabilityCategory | str] = None,
        query: Optional[str] = None,
    ) -> None:
        """Emit a discovery insight for found capabilities."""
        if not self.insight_emitter:
            return

        # Build summary
        if trigger:
            summary = f"Found {len(results)} capabilities matching trigger '{trigger}'"
        elif category:
            cat_val = category.value if isinstance(category, CapabilityCategory) else category
            summary = f"Found {len(results)} {cat_val} capabilities"
        else:
            summary = f"Found {len(results)} capabilities"

        # Add capability details
        cap_names = [f"{r.skill_id}:{r.capability_id}" for r in results[:5]]
        if len(results) > 5:
            cap_names.append(f"... and {len(results) - 5} more")

        # Build evidence from results
        from contextcore.agent.insights import Evidence as InsightEvidence
        evidence = [
            InsightEvidence(
                type="capability",
                ref=f"{r.skill_id}:{r.capability_id}",
                description=r.summary[:100] if r.summary else None,
                query=query,
                timestamp=datetime.now(timezone.utc),
            )
            for r in results[:10]  # Limit evidence to first 10
        ]

        # Calculate average confidence
        avg_confidence = sum(r.confidence for r in results) / len(results) if results else 0.5

        self.insight_emitter.emit_discovery(
            summary=f"{summary}: {', '.join(cap_names)}",
            confidence=min(0.95, avg_confidence),
            evidence=evidence,
        )

    def query_by_trigger(
        self,
        trigger: str,
        time_range: str = "24h",
        limit: int = 100,
    ) -> list[SkillCapability]:
        """
        Find capabilities matching a trigger keyword.

        Args:
            trigger: Keyword to search for in triggers
            time_range: Time range
            limit: Maximum results

        Returns:
            List of matching capabilities
        """
        return self.query(trigger=trigger, time_range=time_range, limit=limit)

    def query_by_category(
        self,
        category: CapabilityCategory | str,
        time_range: str = "24h",
        limit: int = 100,
    ) -> list[SkillCapability]:
        """
        Find capabilities by category.

        Args:
            category: Capability category
            time_range: Time range
            limit: Maximum results

        Returns:
            List of matching capabilities
        """
        return self.query(category=category, time_range=time_range, limit=limit)

    def query_within_budget(
        self,
        max_tokens: int,
        time_range: str = "24h",
        limit: int = 100,
    ) -> list[SkillCapability]:
        """
        Find capabilities within token budget.

        Args:
            max_tokens: Maximum token budget
            time_range: Time range
            limit: Maximum results

        Returns:
            List of matching capabilities
        """
        return self.query(max_tokens=max_tokens, time_range=time_range, limit=limit)

    def get_skill_capabilities(
        self,
        skill_id: str,
        time_range: str = "24h",
    ) -> list[SkillCapability]:
        """
        Get all capabilities for a skill.

        Args:
            skill_id: Skill identifier
            time_range: Time range

        Returns:
            List of capabilities for the skill
        """
        return self.query(skill_id=skill_id, time_range=time_range)

    def get_routing_table(
        self,
        skill_id: str,
        time_range: str = "24h",
    ) -> dict[str, str]:
        """
        Get trigger -> capability_id mapping for a skill.

        Args:
            skill_id: Skill identifier
            time_range: Time range

        Returns:
            Dictionary mapping trigger keywords to capability IDs
        """
        capabilities = self.get_skill_capabilities(skill_id, time_range)

        routing = {}
        for cap in capabilities:
            for trigger in cap.triggers:
                routing[trigger] = cap.capability_id

        return routing

    def get_agent_friendly_capabilities(
        self,
        min_interop: int = 4,
        time_range: str = "24h",
        limit: int = 100,
    ) -> list[SkillCapability]:
        """
        Get high-interoperability capabilities suitable for agent use.

        Args:
            min_interop: Minimum agent interop score
            time_range: Time range
            limit: Maximum results

        Returns:
            List of agent-friendly capabilities
        """
        return self.query(min_interop_agent=min_interop, time_range=time_range, limit=limit)

    def _execute_traceql(
        self,
        query: str,
        time_range: str,
        limit: int,
    ) -> list[SkillCapability]:
        """
        Execute TraceQL query against Tempo.

        Args:
            query: TraceQL query string
            time_range: Time range (e.g., "1h", "24h")
            limit: Maximum results

        Returns:
            List of SkillCapability objects from query results
        """
        # Parse time range to seconds
        time_seconds = self._parse_time_range(time_range)

        # Build API request
        params = {
            "q": query,
            "limit": limit,
            "start": f"-{time_seconds}s",
        }

        url = f"{self.tempo_url}/api/search?{urlencode(params)}"

        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            return self._parse_trace_results(data)

        except requests.exceptions.ConnectionError:
            warnings.warn(
                f"Cannot connect to Tempo at {self.tempo_url}. "
                "Ensure Tempo is running and accessible.",
                UserWarning
            )
            return []

        except requests.exceptions.HTTPError as e:
            warnings.warn(
                f"Tempo query failed: {e}. Query: {query}",
                UserWarning
            )
            return []

        except Exception as e:
            warnings.warn(
                f"Unexpected error querying Tempo: {e}",
                UserWarning
            )
            return []

    def _parse_time_range(self, time_range: str) -> int:
        """
        Parse time range string to seconds.

        Args:
            time_range: Time range like "1h", "24h", "7d"

        Returns:
            Time in seconds
        """
        unit = time_range[-1].lower()
        value = int(time_range[:-1])

        if unit == "s":
            return value
        elif unit == "m":
            return value * 60
        elif unit == "h":
            return value * 3600
        elif unit == "d":
            return value * 86400
        else:
            return 86400  # Default to 24h

    def _parse_trace_results(self, data: dict) -> list[SkillCapability]:
        """
        Parse Tempo search results into SkillCapability objects.

        Args:
            data: Tempo API response

        Returns:
            List of SkillCapability objects
        """
        capabilities = []

        traces = data.get("traces", [])
        for trace in traces:
            for span in trace.get("spanSet", {}).get("spans", []):
                try:
                    capability = self._span_to_capability(span)
                    if capability:
                        capabilities.append(capability)
                except Exception:
                    # Skip malformed spans
                    continue

        return capabilities

    def _span_to_capability(self, span: dict) -> Optional[SkillCapability]:
        """
        Convert a Tempo span to SkillCapability.

        Args:
            span: Span data from Tempo

        Returns:
            SkillCapability or None if conversion fails
        """
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
            elif "boolValue" in value:
                attrs[key] = value["boolValue"]

        # Required attributes
        if "capability.id" not in attrs or "skill.id" not in attrs:
            return None

        # Parse triggers from comma-separated string
        triggers_str = attrs.get("capability.triggers", "")
        triggers = [t.strip() for t in triggers_str.split(",") if t.strip()]

        # Parse category
        category_str = attrs.get("capability.category", "action")
        try:
            category = CapabilityCategory(category_str)
        except ValueError:
            category = CapabilityCategory.ACTION

        # Parse skill type
        skill_type_str = attrs.get("skill.type")
        skill_type = None
        if skill_type_str:
            try:
                skill_type = SkillType(skill_type_str)
            except ValueError:
                pass

        # Parse audience
        audience_str = attrs.get("capability.audience")
        audience = None
        if audience_str:
            try:
                audience = Audience(audience_str)
            except ValueError:
                pass

        # Parse timestamps
        created_at = None
        if "capability.created_at" in attrs:
            try:
                created_at = datetime.fromisoformat(attrs["capability.created_at"])
            except ValueError:
                pass

        updated_at = None
        if "capability.updated_at" in attrs:
            try:
                updated_at = datetime.fromisoformat(attrs["capability.updated_at"])
            except ValueError:
                pass

        expires_at = None
        if "capability.expires_at" in attrs:
            try:
                expires_at = datetime.fromisoformat(attrs["capability.expires_at"])
            except ValueError:
                pass

        # Parse project_refs from comma-separated string
        project_refs_str = attrs.get("capability.project_refs", "")
        project_refs = [p.strip() for p in project_refs_str.split(",") if p.strip()]

        # Parse anti-patterns from comma-separated string
        anti_patterns_str = attrs.get("capability.anti_patterns", "")
        anti_patterns = [a.strip() for a in anti_patterns_str.split(",") if a.strip()]

        return SkillCapability(
            skill_id=attrs["skill.id"],
            skill_type=skill_type,
            skill_version=attrs.get("skill.version", "2.0"),
            capability_id=attrs["capability.id"],
            capability_name=attrs.get("capability.name", attrs["capability.id"]),
            category=category,
            triggers=triggers,
            summary=attrs.get("capability.summary", ""),
            summary_tokens=attrs.get("capability.summary_tokens", 50),
            token_budget=attrs.get("capability.token_budget", 0),
            interop_human=attrs.get("capability.interop_human", 4),
            interop_agent=attrs.get("capability.interop_agent", 5),
            # New fields
            audience=audience,
            confidence=attrs.get("capability.confidence", 0.9),
            success_rate=attrs.get("capability.success_rate"),
            invocation_count=attrs.get("capability.invocation_count", 0),
            created_at=created_at or datetime.now(timezone.utc),
            updated_at=updated_at or datetime.now(timezone.utc),
            expires_at=expires_at,
            supersedes=attrs.get("capability.supersedes"),
            project_refs=project_refs,
            anti_patterns=anti_patterns,
        )


class SkillManifestQuerier:
    """
    Query skill manifests from Tempo.

    Example:
        querier = SkillManifestQuerier(tempo_url="http://localhost:3200")

        # List all skills
        skills = querier.list_skills()

        # Get a specific skill manifest
        manifest = querier.get_skill("llm-formatter")
    """

    def __init__(
        self,
        tempo_url: str = "http://localhost:3200",
        timeout: int = 30,
    ):
        self.tempo_url = tempo_url.rstrip("/")
        self.timeout = timeout
        self._capability_querier = SkillCapabilityQuerier(tempo_url, timeout)

    def list_skills(
        self,
        skill_type: Optional[SkillType | str] = None,
        time_range: str = "24h",
        limit: int = 100,
    ) -> list[SkillManifest]:
        """
        List all skills in Tempo.

        Args:
            skill_type: Filter by skill type
            time_range: Time range
            limit: Maximum results

        Returns:
            List of SkillManifest objects
        """
        conditions = ['name =~ "skill:.*"']

        if skill_type:
            type_val = skill_type.value if isinstance(skill_type, SkillType) else skill_type
            conditions.append(f'skill.type = "{type_val}"')

        query = "{ " + " && ".join(conditions) + " }"
        return self._execute_skill_query(query, time_range, limit)

    def get_skill(
        self,
        skill_id: str,
        time_range: str = "24h",
    ) -> Optional[SkillManifest]:
        """
        Get a specific skill manifest.

        Args:
            skill_id: Skill identifier
            time_range: Time range

        Returns:
            SkillManifest or None if not found
        """
        query = f'{{ name =~ "skill:.*" && skill.id = "{skill_id}" }}'
        manifests = self._execute_skill_query(query, time_range, limit=1)
        return manifests[0] if manifests else None

    def _execute_skill_query(
        self,
        query: str,
        time_range: str,
        limit: int,
    ) -> list[SkillManifest]:
        """Execute skill manifest query."""
        # Similar implementation to SkillCapabilityQuerier
        time_seconds = self._capability_querier._parse_time_range(time_range)

        params = {
            "q": query,
            "limit": limit,
            "start": f"-{time_seconds}s",
        }

        url = f"{self.tempo_url}/api/search?{urlencode(params)}"

        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            return self._parse_skill_results(data)

        except Exception as e:
            warnings.warn(f"Skill query failed: {e}", UserWarning)
            return []

    def _parse_skill_results(self, data: dict) -> list[SkillManifest]:
        """Parse skill manifest results from Tempo."""
        manifests = []

        for trace in data.get("traces", []):
            for span in trace.get("spanSet", {}).get("spans", []):
                try:
                    manifest = self._span_to_manifest(span)
                    if manifest:
                        manifests.append(manifest)
                except Exception:
                    continue

        return manifests

    def _span_to_manifest(self, span: dict) -> Optional[SkillManifest]:
        """Convert a Tempo span to SkillManifest."""
        attrs = {}
        for attr in span.get("attributes", []):
            key = attr.get("key", "")
            value = attr.get("value", {})
            if "stringValue" in value:
                attrs[key] = value["stringValue"]
            elif "intValue" in value:
                attrs[key] = int(value["intValue"])

        if "skill.id" not in attrs:
            return None

        # Parse skill type
        skill_type_str = attrs.get("skill.type", "utility")
        try:
            skill_type = SkillType(skill_type_str)
        except ValueError:
            skill_type = SkillType.UTILITY

        # Parse capability refs
        caps_str = attrs.get("skill.capabilities", "")
        capability_refs = [c.strip() for c in caps_str.split(",") if c.strip()]

        return SkillManifest(
            skill_id=attrs["skill.id"],
            skill_type=skill_type,
            version=attrs.get("skill.version", "2.0"),
            description=attrs.get("skill.description", ""),
            capability_refs=capability_refs,
            manifest_tokens=attrs.get("skill.manifest_tokens", 150),
            index_tokens=attrs.get("skill.index_tokens", 200),
            total_tokens=attrs.get("skill.total_tokens", 0),
            compressed_tokens=attrs.get("skill.compressed_tokens", 0),
        )
