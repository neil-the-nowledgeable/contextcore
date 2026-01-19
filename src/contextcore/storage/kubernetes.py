"""
Kubernetes CRD-based storage backend.

Stores data in ProjectContext CRDs using the v2 schema.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from contextcore.storage.base import (
    BaseStorage,
    HandoffData,
    InsightData,
    SessionData,
    StorageType,
    register_backend,
)

logger = logging.getLogger(__name__)

# Kubernetes client is optional - only import if available
try:
    from kubernetes import client, config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False
    logger.warning("kubernetes package not installed - KubernetesStorage unavailable")


@register_backend(StorageType.KUBERNETES)
class KubernetesStorage(BaseStorage):
    """
    Kubernetes CRD-based storage backend.

    Stores agent data in ProjectContext CRDs:
    - Handoffs in spec.handoffQueue
    - Sessions in spec.agentSessions
    - Insights summary in spec.agentInsights
    - Guidance in spec.agentGuidance

    Ideal for:
    - Kubernetes-native deployments
    - Multi-agent coordination
    - Production environments

    Requires ProjectContext v2 CRD to be installed.
    """

    CRD_GROUP = "contextcore.io"
    CRD_VERSION = "v2"
    CRD_PLURAL = "projectcontexts"

    def __init__(
        self,
        namespace: str = "default",
        kubeconfig: Optional[str] = None,
    ):
        super().__init__(namespace=namespace)

        if not K8S_AVAILABLE:
            raise RuntimeError(
                "kubernetes package required for KubernetesStorage. "
                "Install with: pip install kubernetes"
            )

        # Initialize K8s client
        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig)
        else:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()

        self.custom_api = client.CustomObjectsApi()
        logger.debug(f"KubernetesStorage initialized for namespace {namespace}")

    def _get_context(self, project_id: str) -> Dict[str, Any]:
        """Get ProjectContext for a project."""
        try:
            return self.custom_api.get_namespaced_custom_object(
                group=self.CRD_GROUP,
                version=self.CRD_VERSION,
                namespace=self.namespace,
                plural=self.CRD_PLURAL,
                name=project_id,
            )
        except Exception as e:
            logger.error(f"Failed to get ProjectContext {project_id}: {e}")
            raise

    def _patch_context(self, project_id: str, patch: Dict[str, Any]) -> None:
        """Patch a ProjectContext."""
        try:
            self.custom_api.patch_namespaced_custom_object(
                group=self.CRD_GROUP,
                version=self.CRD_VERSION,
                namespace=self.namespace,
                plural=self.CRD_PLURAL,
                name=project_id,
                body=patch,
            )
        except Exception as e:
            logger.error(f"Failed to patch ProjectContext {project_id}: {e}")
            raise

    # Handoff operations

    def save_handoff(self, project_id: str, handoff: HandoffData) -> None:
        """Save a handoff to the queue."""
        if handoff.created_at is None:
            handoff.created_at = datetime.now(timezone.utc)

        # Get current queue
        context = self._get_context(project_id)
        queue = context.get("spec", {}).get("handoffQueue", [])

        # Check if handoff already exists
        existing_idx = None
        for i, h in enumerate(queue):
            if h.get("id") == handoff.id:
                existing_idx = i
                break

        if existing_idx is not None:
            queue[existing_idx] = handoff.to_dict()
        else:
            queue.append(handoff.to_dict())

        # Patch the context
        self._patch_context(project_id, {"spec": {"handoffQueue": queue}})
        logger.debug(f"Saved handoff {handoff.id} to ProjectContext {project_id}")

    def get_handoff(self, project_id: str, handoff_id: str) -> Optional[HandoffData]:
        """Get a handoff by ID."""
        context = self._get_context(project_id)
        queue = context.get("spec", {}).get("handoffQueue", [])

        for h in queue:
            if h.get("id") == handoff_id:
                return HandoffData.from_dict(h)

        return None

    def update_handoff_status(
        self,
        project_id: str,
        handoff_id: str,
        status: str,
        result_trace_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update handoff status."""
        context = self._get_context(project_id)
        queue = context.get("spec", {}).get("handoffQueue", [])

        for handoff in queue:
            if handoff.get("id") == handoff_id:
                handoff["status"] = status
                if result_trace_id:
                    handoff["resultTraceId"] = result_trace_id
                if error_message:
                    handoff["errorMessage"] = error_message
                break
        else:
            raise ValueError(f"Handoff {handoff_id} not found")

        self._patch_context(project_id, {"spec": {"handoffQueue": queue}})

    def list_handoffs(
        self,
        project_id: str,
        status: Optional[str] = None,
        to_agent: Optional[str] = None,
    ) -> List[HandoffData]:
        """List handoffs with optional filters."""
        context = self._get_context(project_id)
        queue = context.get("spec", {}).get("handoffQueue", [])
        handoffs = []

        for h in queue:
            if status and h.get("status") != status:
                continue
            if to_agent and h.get("toAgent") != to_agent:
                continue
            handoffs.append(HandoffData.from_dict(h))

        return handoffs

    # Session operations

    def save_session(self, session: SessionData) -> None:
        """Save an agent session."""
        if session.started_at is None:
            session.started_at = datetime.now(timezone.utc)

        context = self._get_context(session.project_id)
        sessions = context.get("spec", {}).get("agentSessions", [])

        session_data = {
            "sessionId": session.session_id,
            "agentId": session.agent_id,
            "agentType": session.agent_type,
            "startedAt": session.started_at.isoformat() if session.started_at else None,
            "endedAt": session.ended_at.isoformat() if session.ended_at else None,
            "status": session.status,
            "capabilitiesUsed": session.capabilities_used,
            "insightCount": session.insight_count,
            "tasksCompleted": session.tasks_completed,
        }

        # Check if session already exists
        existing_idx = None
        for i, s in enumerate(sessions):
            if s.get("sessionId") == session.session_id:
                existing_idx = i
                break

        if existing_idx is not None:
            sessions[existing_idx] = session_data
        else:
            sessions.append(session_data)

        self._patch_context(session.project_id, {"spec": {"agentSessions": sessions}})

    def get_session(self, project_id: str, session_id: str) -> Optional[SessionData]:
        """Get a session by ID."""
        context = self._get_context(project_id)
        sessions = context.get("spec", {}).get("agentSessions", [])

        for s in sessions:
            if s.get("sessionId") == session_id:
                started_at = None
                if s.get("startedAt"):
                    started_at = datetime.fromisoformat(s["startedAt"])
                ended_at = None
                if s.get("endedAt"):
                    ended_at = datetime.fromisoformat(s["endedAt"])

                return SessionData(
                    session_id=s["sessionId"],
                    agent_id=s["agentId"],
                    project_id=project_id,
                    agent_type=s.get("agentType", "code_assistant"),
                    started_at=started_at,
                    ended_at=ended_at,
                    status=s.get("status", "active"),
                    capabilities_used=s.get("capabilitiesUsed", []),
                    insight_count=s.get("insightCount", 0),
                    tasks_completed=s.get("tasksCompleted", []),
                )

        return None

    def update_session(self, session: SessionData) -> None:
        """Update an existing session."""
        self.save_session(session)

    def list_sessions(
        self,
        project_id: str,
        status: Optional[str] = None,
    ) -> List[SessionData]:
        """List sessions for a project."""
        context = self._get_context(project_id)
        sessions_data = context.get("spec", {}).get("agentSessions", [])
        sessions = []

        for s in sessions_data:
            if status and s.get("status") != status:
                continue

            started_at = None
            if s.get("startedAt"):
                started_at = datetime.fromisoformat(s["startedAt"])
            ended_at = None
            if s.get("endedAt"):
                ended_at = datetime.fromisoformat(s["endedAt"])

            sessions.append(SessionData(
                session_id=s["sessionId"],
                agent_id=s["agentId"],
                project_id=project_id,
                agent_type=s.get("agentType", "code_assistant"),
                started_at=started_at,
                ended_at=ended_at,
                status=s.get("status", "active"),
                capabilities_used=s.get("capabilitiesUsed", []),
                insight_count=s.get("insightCount", 0),
                tasks_completed=s.get("tasksCompleted", []),
            ))

        return sessions

    # Insight operations (summary in CRD, detail in Tempo)

    def save_insight(self, insight: InsightData) -> None:
        """
        Save an insight summary to the CRD.

        Note: Full insight detail is stored in Tempo spans.
        The CRD only stores a summary for quick access.
        """
        if insight.timestamp is None:
            insight.timestamp = datetime.now(timezone.utc)

        context = self._get_context(insight.project_id)
        insights = context.get("spec", {}).get("agentInsights", {})

        # Update counts
        by_type = insights.get("byType", {})
        type_key = f"{insight.insight_type}s"  # e.g., "decisions"
        by_type[type_key] = by_type.get(type_key, 0) + 1

        insights["byType"] = by_type
        insights["totalCount"] = insights.get("totalCount", 0) + 1
        insights["lastUpdated"] = datetime.now(timezone.utc).isoformat()

        # Add to recent high confidence if applicable
        if insight.confidence > 0.9:
            recent = insights.get("recentHighConfidence", [])
            recent.insert(0, {
                "id": insight.id,
                "type": insight.insight_type,
                "summary": insight.summary,
                "confidence": insight.confidence,
                "timestamp": insight.timestamp.isoformat(),
                "traceId": insight.trace_id,
            })
            # Keep only last 10
            insights["recentHighConfidence"] = recent[:10]

        # Track blockers
        if insight.insight_type == "blocker":
            blockers = insights.get("unresolvedBlockers", [])
            blockers.append({
                "id": insight.id,
                "summary": insight.summary,
                "createdAt": insight.timestamp.isoformat(),
                "traceId": insight.trace_id,
            })
            insights["unresolvedBlockers"] = blockers

        self._patch_context(insight.project_id, {"spec": {"agentInsights": insights}})

    def list_insights(
        self,
        project_id: str,
        insight_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[InsightData]:
        """
        List insights from the CRD summary.

        Note: For full insight queries, use TraceQL against Tempo.
        """
        context = self._get_context(project_id)
        insights_summary = context.get("spec", {}).get("agentInsights", {})

        # Return recent high confidence insights from CRD
        recent = insights_summary.get("recentHighConfidence", [])
        insights = []

        for r in recent:
            if insight_type and r.get("type") != insight_type:
                continue

            timestamp = None
            if r.get("timestamp"):
                timestamp = datetime.fromisoformat(r["timestamp"])

            if since and timestamp and timestamp < since:
                continue

            insights.append(InsightData(
                id=r["id"],
                project_id=project_id,
                agent_id="unknown",  # Not stored in summary
                insight_type=r["type"],
                summary=r["summary"],
                confidence=r["confidence"],
                timestamp=timestamp,
                trace_id=r.get("traceId"),
            ))

        return insights[:limit]

    # Guidance operations

    def get_guidance(self, project_id: str) -> Dict[str, Any]:
        """Get guidance for a project."""
        context = self._get_context(project_id)
        return context.get("spec", {}).get("agentGuidance", {})

    def update_guidance(self, project_id: str, guidance: Dict[str, Any]) -> None:
        """Update guidance for a project."""
        self._patch_context(project_id, {"spec": {"agentGuidance": guidance}})
