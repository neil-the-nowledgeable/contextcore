"""
A2A-style API facade for agent insights.
__all__ = ['InsightsAPI']


This module provides a modern resource.action naming pattern API while maintaining
backward compatibility with existing InsightEmitter and InsightQuerier classes.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

# Import existing classes from the agent insights module
from contextcore.agent.insights import InsightEmitter, InsightQuerier, InsightType, InsightData
from contextcore.compat.otel_genai import DualEmitAttributes


class InsightsAPI:
    """A2A-style API for agent insights.

    Provides a modern API surface using resource.action naming pattern while maintaining
    backward compatibility with existing InsightEmitter and InsightQuerier classes.

    Example:
        api = InsightsAPI(project_id="checkout", agent_id="claude")
        api.emit(type="decision", summary="Chose X over Y", confidence=0.9)
        decisions = api.query(type="decision", time_range="7d")
    """

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        tempo_url: Optional[str] = None,
    ) -> None:
        """Initialize InsightsAPI with project and agent context.

        Args:
            project_id: The ID of the project
            agent_id: The ID of the agent
            tempo_url: Optional URL for tempo service (used by querier)
        """
        self._project_id = project_id
        self._agent_id = agent_id
        
        # Initialize existing classes with correct constructor parameters
        self._emitter = InsightEmitter(project_id, agent_id)
        self._querier = InsightQuerier(tempo_url)  # Querier only takes tempo_url
        
        # Initialize dual-emit layer for OpenTelemetry integration
        self._dual_emit = DualEmitAttributes()

    def emit(
        self,
        type: str,
        summary: str,
        confidence: float = 1.0,
        evidence: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Emit an insight with the specified parameters.

        Uses DualEmitAttributes for OpenTelemetry span attribute transformation.

        Args:
            type: The type of insight (e.g., "decision", "observation")
            summary: Human-readable summary of the insight
            confidence: Confidence level between 0.0 and 1.0
            evidence: Supporting evidence for the insight
            metadata: Additional metadata associated with the insight
            timestamp: Optional timestamp (defaults to current time)

        Returns:
            The ID of the emitted insight

        Raises:
            ValueError: If confidence is not between 0.0 and 1.0
        """
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")

        # Transform attributes for OpenTelemetry emission using dual-emit layer
        span_attributes = self._dual_emit.transform({
            "insight.type": type,
            "insight.summary": summary,
            "insight.confidence": confidence,
            "insight.project_id": self._project_id,
            "insight.agent_id": self._agent_id,
        })
        
        # Add optional attributes if provided
        if evidence:
            span_attributes.update(self._dual_emit.transform({"insight.evidence": str(evidence)}))
        if metadata:
            span_attributes.update(self._dual_emit.transform({"insight.metadata": str(metadata)}))

        # Emit through existing InsightEmitter
        return self._emitter.emit(
            InsightType(type),
            summary,
            confidence,
            evidence,
            metadata,
            timestamp
        )

    def query(
        self,
        project_id: Optional[str] = None,
        type: Optional[str] = None,
        time_range: Optional[Union[str, tuple[datetime, datetime]]] = None,
        confidence_min: Optional[float] = None,
        limit: int = 100,
    ) -> List[InsightData]:
        """Query insights with optional filters.

        Args:
            project_id: Project ID to filter by (defaults to instance project_id)
            type: Insight type to filter by
            time_range: Time range as string ("7d", "24h") or datetime tuple
            confidence_min: Minimum confidence threshold
            limit: Maximum number of results to return

        Returns:
            List of insights matching the query criteria

        Raises:
            ValueError: If limit is not positive or confidence_min is invalid
        """
        if limit <= 0:
            raise ValueError("Limit must be positive")
        if confidence_min is not None and not (0.0 <= confidence_min <= 1.0):
            raise ValueError("confidence_min must be between 0.0 and 1.0")

        # Use instance project_id if not provided
        query_project_id = project_id or self._project_id

        # Delegate to existing querier with proper parameter mapping
        return self._querier.query(
            project_id=query_project_id,
            insight_type=InsightType(type) if type else None,
            time_range=time_range,
            min_confidence=confidence_min,
            limit=limit
        )

    def get(self, insight_id: str) -> Optional[InsightData]:
        """Retrieve a specific insight by its ID.

        Args:
            insight_id: The unique identifier of the insight

        Returns:
            The insight data if found, None otherwise

        Raises:
            ValueError: If insight_id is empty
        """
        if not insight_id.strip():
            raise ValueError("insight_id cannot be empty")

        return self._querier.get_by_id(insight_id)

    def list(
        self,
        project_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[InsightData]:
        """List insights for a project with minimal filtering.

        This is an alias for query() with only project and limit filters.

        Args:
            project_id: Project ID to list insights for (defaults to instance project_id)
            limit: Maximum number of insights to return

        Returns:
            List of insights for the specified project

        Raises:
            ValueError: If limit is not positive
        """
        return self.query(project_id=project_id, limit=limit)


# Add deprecation warnings to existing classes
def _add_deprecation_warning(original_class, class_name: str):
    """Add deprecation warning to existing class constructor."""
    original_init = original_class.__init__

    def deprecated_init(self, *args, **kwargs):
        warnings.warn(
            f"{class_name} is deprecated, use InsightsAPI instead",
            DeprecationWarning,
            stacklevel=2
        )
        return original_init(self, *args, **kwargs)

    return deprecated_init


# Monkey-patch existing classes to add deprecation warnings
InsightEmitter.__init__ = _add_deprecation_warning(InsightEmitter, "InsightEmitter")
InsightQuerier.__init__ = _add_deprecation_warning(InsightQuerier, "InsightQuerier")


# Module exports - both old and new APIs for backward compatibility
__all__ = [
    # New A2A-style API (primary)
    "InsightsAPI",
    
    # Legacy classes (deprecated but still exported)
    "InsightEmitter",
    "InsightQuerier",
    "InsightType",
    "InsightData",
]
