"""
File-based storage backend for local development.

Stores data in JSON files under ~/.contextcore/storage/<namespace>/
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
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


@register_backend(StorageType.FILE)
class FileStorage(BaseStorage):
    """
    File-based storage backend.

    Ideal for:
    - Local development
    - Single-machine deployments
    - Testing

    Data layout:
        ~/.contextcore/storage/<namespace>/
        ├── <project_id>/
        │   ├── handoffs/
        │   │   ├── <handoff_id>.json
        │   ├── sessions/
        │   │   ├── <session_id>.json
        │   ├── insights/
        │   │   ├── <insight_id>.json
        │   └── guidance.json
    """

    def __init__(
        self,
        namespace: str = "default",
        base_dir: Optional[str] = None,
    ):
        super().__init__(namespace=namespace)
        self.base_dir = Path(
            base_dir or os.environ.get(
                "CONTEXTCORE_STORAGE_DIR",
                os.path.expanduser("~/.contextcore/storage")
            )
        )
        self.namespace_dir = self.base_dir / namespace
        self.namespace_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"FileStorage initialized at {self.namespace_dir}")

    def _project_dir(self, project_id: str) -> Path:
        """Get project directory, creating if needed."""
        project_dir = self.namespace_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    def _handoffs_dir(self, project_id: str) -> Path:
        """Get handoffs directory for a project."""
        handoffs_dir = self._project_dir(project_id) / "handoffs"
        handoffs_dir.mkdir(exist_ok=True)
        return handoffs_dir

    def _sessions_dir(self, project_id: str) -> Path:
        """Get sessions directory for a project."""
        sessions_dir = self._project_dir(project_id) / "sessions"
        sessions_dir.mkdir(exist_ok=True)
        return sessions_dir

    def _insights_dir(self, project_id: str) -> Path:
        """Get insights directory for a project."""
        insights_dir = self._project_dir(project_id) / "insights"
        insights_dir.mkdir(exist_ok=True)
        return insights_dir

    # Handoff operations

    def save_handoff(self, project_id: str, handoff: HandoffData) -> None:
        """Save a handoff to the queue."""
        if handoff.created_at is None:
            handoff.created_at = datetime.now(timezone.utc)

        file_path = self._handoffs_dir(project_id) / f"{handoff.id}.json"
        with open(file_path, "w") as f:
            json.dump(handoff.to_dict(), f, indent=2, default=str)
        logger.debug(f"Saved handoff {handoff.id} to {file_path}")

    def get_handoff(self, project_id: str, handoff_id: str) -> Optional[HandoffData]:
        """Get a handoff by ID."""
        file_path = self._handoffs_dir(project_id) / f"{handoff_id}.json"
        if not file_path.exists():
            return None

        with open(file_path) as f:
            data = json.load(f)
        return HandoffData.from_dict(data)

    def update_handoff_status(
        self,
        project_id: str,
        handoff_id: str,
        status: str,
        result_trace_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update handoff status."""
        handoff = self.get_handoff(project_id, handoff_id)
        if handoff is None:
            raise ValueError(f"Handoff {handoff_id} not found")

        handoff.status = status
        if result_trace_id:
            handoff.result_trace_id = result_trace_id
        if error_message:
            handoff.error_message = error_message

        self.save_handoff(project_id, handoff)

    def list_handoffs(
        self,
        project_id: str,
        status: Optional[str] = None,
        to_agent: Optional[str] = None,
    ) -> List[HandoffData]:
        """List handoffs with optional filters."""
        handoffs_dir = self._handoffs_dir(project_id)
        handoffs = []

        for file_path in handoffs_dir.glob("*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                handoff = HandoffData.from_dict(data)

                # Apply filters
                if status and handoff.status != status:
                    continue
                if to_agent and handoff.to_agent != to_agent:
                    continue

                handoffs.append(handoff)
            except Exception as e:
                logger.warning(f"Failed to load handoff {file_path}: {e}")

        # Sort by created_at (newest first)
        handoffs.sort(
            key=lambda h: h.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return handoffs

    # Session operations

    def save_session(self, session: SessionData) -> None:
        """Save an agent session."""
        if session.started_at is None:
            session.started_at = datetime.now(timezone.utc)

        file_path = self._sessions_dir(session.project_id) / f"{session.session_id}.json"
        data = {
            "sessionId": session.session_id,
            "agentId": session.agent_id,
            "projectId": session.project_id,
            "agentType": session.agent_type,
            "startedAt": session.started_at.isoformat() if session.started_at else None,
            "endedAt": session.ended_at.isoformat() if session.ended_at else None,
            "status": session.status,
            "capabilitiesUsed": session.capabilities_used,
            "insightCount": session.insight_count,
            "tasksCompleted": session.tasks_completed,
        }
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Saved session {session.session_id}")

    def get_session(self, project_id: str, session_id: str) -> Optional[SessionData]:
        """Get a session by ID."""
        file_path = self._sessions_dir(project_id) / f"{session_id}.json"
        if not file_path.exists():
            return None

        with open(file_path) as f:
            data = json.load(f)

        started_at = None
        if data.get("startedAt"):
            started_at = datetime.fromisoformat(data["startedAt"])
        ended_at = None
        if data.get("endedAt"):
            ended_at = datetime.fromisoformat(data["endedAt"])

        return SessionData(
            session_id=data["sessionId"],
            agent_id=data["agentId"],
            project_id=data["projectId"],
            agent_type=data.get("agentType", "code_assistant"),
            started_at=started_at,
            ended_at=ended_at,
            status=data.get("status", "active"),
            capabilities_used=data.get("capabilitiesUsed", []),
            insight_count=data.get("insightCount", 0),
            tasks_completed=data.get("tasksCompleted", []),
        )

    def update_session(self, session: SessionData) -> None:
        """Update an existing session."""
        self.save_session(session)

    def list_sessions(
        self,
        project_id: str,
        status: Optional[str] = None,
    ) -> List[SessionData]:
        """List sessions for a project."""
        sessions_dir = self._sessions_dir(project_id)
        sessions = []

        for file_path in sessions_dir.glob("*.json"):
            session = self.get_session(project_id, file_path.stem)
            if session:
                if status and session.status != status:
                    continue
                sessions.append(session)

        # Sort by started_at (newest first)
        sessions.sort(
            key=lambda s: s.started_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return sessions

    # Insight operations

    def save_insight(self, insight: InsightData) -> None:
        """Save an agent insight."""
        if insight.timestamp is None:
            insight.timestamp = datetime.now(timezone.utc)

        file_path = self._insights_dir(insight.project_id) / f"{insight.id}.json"
        data = {
            "id": insight.id,
            "projectId": insight.project_id,
            "agentId": insight.agent_id,
            "insightType": insight.insight_type,
            "summary": insight.summary,
            "confidence": insight.confidence,
            "timestamp": insight.timestamp.isoformat() if insight.timestamp else None,
            "traceId": insight.trace_id,
            "appliesTo": insight.applies_to,
            "context": insight.context,
        }
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Saved insight {insight.id}")

    def list_insights(
        self,
        project_id: str,
        insight_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[InsightData]:
        """List insights with optional filters."""
        insights_dir = self._insights_dir(project_id)
        insights = []

        for file_path in insights_dir.glob("*.json"):
            if len(insights) >= limit:
                break

            try:
                with open(file_path) as f:
                    data = json.load(f)

                timestamp = None
                if data.get("timestamp"):
                    timestamp = datetime.fromisoformat(data["timestamp"])

                # Apply time filter
                if since and timestamp and timestamp < since:
                    continue

                # Apply type filter
                if insight_type and data.get("insightType") != insight_type:
                    continue

                insight = InsightData(
                    id=data["id"],
                    project_id=data["projectId"],
                    agent_id=data["agentId"],
                    insight_type=data["insightType"],
                    summary=data["summary"],
                    confidence=data["confidence"],
                    timestamp=timestamp,
                    trace_id=data.get("traceId"),
                    applies_to=data.get("appliesTo", []),
                    context=data.get("context", {}),
                )
                insights.append(insight)

            except Exception as e:
                logger.warning(f"Failed to load insight {file_path}: {e}")

        # Sort by timestamp (newest first)
        insights.sort(
            key=lambda i: i.timestamp or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return insights[:limit]

    # Guidance operations

    def get_guidance(self, project_id: str) -> Dict[str, Any]:
        """Get guidance for a project."""
        file_path = self._project_dir(project_id) / "guidance.json"
        if not file_path.exists():
            return {}

        with open(file_path) as f:
            return json.load(f)

    def update_guidance(self, project_id: str, guidance: Dict[str, Any]) -> None:
        """Update guidance for a project."""
        file_path = self._project_dir(project_id) / "guidance.json"
        with open(file_path, "w") as f:
            json.dump(guidance, f, indent=2)
        logger.debug(f"Updated guidance for {project_id}")
