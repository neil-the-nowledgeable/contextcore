"""
Personalized Presentation

Same data, audience-appropriate views. Enables agents to format
output for different human audiences.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from kubernetes import client, config

from contextcore.agent.insights import Insight, InsightQuerier


class AudienceType(str, Enum):
    """Target audience types."""
    EXECUTIVE = "executive"
    MANAGER = "manager"
    DEVELOPER = "developer"
    OPERATOR = "operator"
    AGENT = "agent"


class TechnicalDepth(str, Enum):
    """Level of technical detail."""
    SUMMARY = "summary"
    STANDARD = "standard"
    DETAILED = "detailed"
    EXPERT = "expert"


@dataclass
class PersonalizationSettings:
    """Audience-specific presentation settings."""
    audience_type: AudienceType
    dashboard_id: str | None = None
    technical_depth: TechnicalDepth = TechnicalDepth.STANDARD
    max_context_tokens: int | None = None
    summary_fields: list[str] | None = None


@dataclass
class PersonalizedInsight:
    """Insight formatted for a specific audience."""
    insight: Insight
    formatted_summary: str
    formatted_detail: str | None = None
    audience: AudienceType = AudienceType.DEVELOPER


class PersonalizedQuerier:
    """
    Query and format insights for specific audiences.

    Same underlying data, different presentation based on
    personalization settings in ProjectContext.

    Example:
        querier = PersonalizedQuerier(project_id="checkout-service")

        # Get executive view
        exec_insights = querier.get_insights(audience=AudienceType.EXECUTIVE)
        # Returns: High-level summaries, counts, trends

        # Get developer view
        dev_insights = querier.get_insights(audience=AudienceType.DEVELOPER)
        # Returns: Full technical detail, code references
    """

    def __init__(
        self,
        project_id: str,
        namespace: str = "default",
        kubeconfig: str | None = None,
        tempo_url: str = "http://localhost:3200",
    ):
        self.project_id = project_id
        self.namespace = namespace
        self.tempo_url = tempo_url

        # Initialize K8s client
        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig)
        else:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()

        self.custom_api = client.CustomObjectsApi()
        self.insight_querier = InsightQuerier(tempo_url=tempo_url)

    def _get_personalization_settings(self, audience: AudienceType) -> PersonalizationSettings:
        """Get personalization settings from ProjectContext."""
        context = self.custom_api.get_namespaced_custom_object(
            group="contextcore.io",
            version="v2",
            namespace=self.namespace,
            plural="projectcontexts",
            name=self.project_id,
        )

        personalization = context.get("spec", {}).get("personalization", {})
        audience_settings = personalization.get(audience.value, {})

        # Map technical depth based on audience
        depth_map = {
            AudienceType.EXECUTIVE: TechnicalDepth.SUMMARY,
            AudienceType.MANAGER: TechnicalDepth.STANDARD,
            AudienceType.DEVELOPER: TechnicalDepth.DETAILED,
            AudienceType.OPERATOR: TechnicalDepth.DETAILED,
            AudienceType.AGENT: TechnicalDepth.EXPERT,
        }

        return PersonalizationSettings(
            audience_type=audience,
            dashboard_id=audience_settings.get("dashboardId"),
            technical_depth=TechnicalDepth(
                audience_settings.get("preferredFormat", depth_map[audience].value)
            ),
            max_context_tokens=audience_settings.get("maxContextTokens"),
            summary_fields=audience_settings.get("summaryFields"),
        )

    def _format_for_audience(
        self,
        insight: Insight,
        settings: PersonalizationSettings,
    ) -> PersonalizedInsight:
        """Format an insight for a specific audience."""
        audience = settings.audience_type

        if audience == AudienceType.EXECUTIVE:
            # Executive: Very brief, business impact only
            formatted_summary = f"{insight.type.value.title()}: {insight.summary}"
            formatted_detail = None

        elif audience == AudienceType.MANAGER:
            # Manager: Summary with context
            formatted_summary = f"[{insight.type.value}] {insight.summary}"
            formatted_detail = f"Confidence: {insight.confidence:.0%}"
            if insight.rationale:
                formatted_detail += f"\nRationale: {insight.rationale}"

        elif audience == AudienceType.DEVELOPER:
            # Developer: Full technical detail
            formatted_summary = f"{insight.type.value}: {insight.summary}"
            formatted_detail = f"""
Confidence: {insight.confidence:.0%}
Agent: {insight.agent_id}
Session: {insight.session_id}
Rationale: {insight.rationale or 'N/A'}
Evidence:
{self._format_evidence(insight.evidence)}
Trace ID: {insight.trace_id}
"""

        elif audience == AudienceType.AGENT:
            # Agent: Structured YAML-like output
            formatted_summary = insight.summary
            formatted_detail = f"""
insight_id: {insight.id}
type: {insight.type.value}
confidence: {insight.confidence}
trace_id: {insight.trace_id}
evidence_count: {len(insight.evidence)}
"""

        else:
            formatted_summary = insight.summary
            formatted_detail = insight.rationale

        return PersonalizedInsight(
            insight=insight,
            formatted_summary=formatted_summary,
            formatted_detail=formatted_detail,
            audience=audience,
        )

    def _format_evidence(self, evidence: list) -> str:
        """Format evidence list."""
        if not evidence:
            return "  (none)"

        lines = []
        for ev in evidence:
            line = f"  - [{ev.type}] {ev.ref}"
            if ev.description:
                line += f": {ev.description}"
            lines.append(line)

        return "\n".join(lines)

    def get_insights(
        self,
        audience: AudienceType,
        time_range: str = "24h",
        limit: int = 10,
        insight_type: str | None = None,
    ) -> list[PersonalizedInsight]:
        """
        Get insights formatted for a specific audience.

        Args:
            audience: Target audience
            time_range: Time range to query
            limit: Maximum results
            insight_type: Filter by type

        Returns:
            Insights formatted for the audience
        """
        settings = self._get_personalization_settings(audience)

        # Query raw insights
        insights = self.insight_querier.query(
            project_id=self.project_id,
            insight_type=insight_type,
            time_range=time_range,
            limit=limit,
        )

        # Format for audience
        return [
            self._format_for_audience(insight, settings)
            for insight in insights
        ]

    def get_summary(
        self,
        audience: AudienceType,
        time_range: str = "7d",
    ) -> dict[str, Any]:
        """
        Get project summary for an audience.

        Args:
            audience: Target audience
            time_range: Time range for summary

        Returns:
            Summary dict appropriate for audience
        """
        settings = self._get_personalization_settings(audience)

        # Get insights
        all_insights = self.insight_querier.query(
            project_id=self.project_id,
            time_range=time_range,
        )

        # Build summary based on audience
        if audience == AudienceType.EXECUTIVE:
            return {
                "total_insights": len(all_insights),
                "decisions_made": sum(1 for i in all_insights if i.type.value == "decision"),
                "blockers": sum(1 for i in all_insights if i.type.value == "blocker"),
                "period": time_range,
            }

        elif audience == AudienceType.MANAGER:
            by_type = {}
            for insight in all_insights:
                by_type[insight.type.value] = by_type.get(insight.type.value, 0) + 1

            return {
                "total_insights": len(all_insights),
                "by_type": by_type,
                "high_confidence": sum(1 for i in all_insights if i.confidence > 0.9),
                "agents_active": len(set(i.agent_id for i in all_insights)),
                "period": time_range,
            }

        elif audience == AudienceType.DEVELOPER:
            return {
                "total_insights": len(all_insights),
                "insights": [
                    {
                        "id": i.id,
                        "type": i.type.value,
                        "summary": i.summary,
                        "confidence": i.confidence,
                        "trace_id": i.trace_id,
                    }
                    for i in all_insights
                ],
                "period": time_range,
            }

        else:
            return {
                "insights": all_insights,
                "period": time_range,
            }
