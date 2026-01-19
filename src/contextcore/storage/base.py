"""
Base storage protocol and factory.

Defines the interface that all storage backends must implement.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Protocol, Type, runtime_checkable

from contextcore.contracts.types import (
    AgentType,
    HandoffStatus,
    InsightType,
    Priority,
    SessionStatus,
)

logger = logging.getLogger(__name__)


class StorageType(str, Enum):
    """Available storage backend types."""
    KUBERNETES = "kubernetes"
    FILE = "file"
    MEMORY = "memory"
    REDIS = "redis"


@dataclass
class HandoffData:
    """Data structure for agent handoffs."""
    id: str
    from_agent: str
    to_agent: str
    capability_id: str
    task: str
    inputs: Dict[str, Any]
    expected_output: Dict[str, Any]
    priority: str = Priority.MEDIUM.value
    timeout_ms: int = 300000
    status: str = HandoffStatus.PENDING.value
    created_at: Optional[datetime] = None
    result_trace_id: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        """Validate enum fields after initialization."""
        # Validate priority
        valid_priorities = [p.value for p in Priority]
        if self.priority not in valid_priorities:
            raise ValueError(
                f"Invalid priority '{self.priority}'. "
                f"Must be one of: {valid_priorities}"
            )
        # Validate status
        valid_statuses = [s.value for s in HandoffStatus]
        if self.status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{self.status}'. "
                f"Must be one of: {valid_statuses}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "fromAgent": self.from_agent,
            "toAgent": self.to_agent,
            "capabilityId": self.capability_id,
            "task": self.task,
            "inputs": self.inputs,
            "expectedOutput": self.expected_output,
            "priority": self.priority,
            "timeoutMs": self.timeout_ms,
            "status": self.status,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "resultTraceId": self.result_trace_id,
            "errorMessage": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HandoffData":
        """Create from dictionary."""
        created_at = None
        if data.get("createdAt"):
            created_at = datetime.fromisoformat(data["createdAt"])

        return cls(
            id=data["id"],
            from_agent=data.get("fromAgent", data.get("from_agent", "")),
            to_agent=data.get("toAgent", data.get("to_agent", "")),
            capability_id=data.get("capabilityId", data.get("capability_id", "")),
            task=data["task"],
            inputs=data.get("inputs", {}),
            expected_output=data.get("expectedOutput", data.get("expected_output", {})),
            priority=data.get("priority", Priority.MEDIUM.value),
            timeout_ms=data.get("timeoutMs", data.get("timeout_ms", 300000)),
            status=data.get("status", HandoffStatus.PENDING.value),
            created_at=created_at,
            result_trace_id=data.get("resultTraceId", data.get("result_trace_id")),
            error_message=data.get("errorMessage", data.get("error_message")),
        )


@dataclass
class SessionData:
    """Data structure for agent sessions."""
    session_id: str
    agent_id: str
    project_id: str
    agent_type: str = AgentType.CODE_ASSISTANT.value
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: str = SessionStatus.ACTIVE.value
    capabilities_used: List[str] = None
    insight_count: int = 0
    tasks_completed: List[str] = None

    def __post_init__(self):
        if self.capabilities_used is None:
            self.capabilities_used = []
        if self.tasks_completed is None:
            self.tasks_completed = []

        # Validate agent_type
        valid_agent_types = [t.value for t in AgentType]
        if self.agent_type not in valid_agent_types:
            raise ValueError(
                f"Invalid agent_type '{self.agent_type}'. "
                f"Must be one of: {valid_agent_types}"
            )
        # Validate status
        valid_statuses = [s.value for s in SessionStatus]
        if self.status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{self.status}'. "
                f"Must be one of: {valid_statuses}"
            )


@dataclass
class InsightData:
    """Data structure for agent insights."""
    id: str
    project_id: str
    agent_id: str
    insight_type: str  # Use InsightType enum values: decision, recommendation, blocker, discovery
    summary: str
    confidence: float
    timestamp: Optional[datetime] = None
    trace_id: Optional[str] = None
    applies_to: List[str] = None
    context: Dict[str, Any] = None

    def __post_init__(self):
        if self.applies_to is None:
            self.applies_to = []
        if self.context is None:
            self.context = {}

        # Validate insight_type
        valid_insight_types = [t.value for t in InsightType]
        if self.insight_type not in valid_insight_types:
            raise ValueError(
                f"Invalid insight_type '{self.insight_type}'. "
                f"Must be one of: {valid_insight_types}"
            )
        # Validate confidence range
        if not 0 <= self.confidence <= 1:
            raise ValueError(
                f"Confidence must be between 0 and 1, got {self.confidence}"
            )


@runtime_checkable
class StorageBackend(Protocol):
    """
    Protocol defining the storage backend interface.

    All storage implementations must provide these methods.
    """

    # Handoff operations
    def save_handoff(self, project_id: str, handoff: HandoffData) -> None:
        """Save a handoff to the queue."""
        ...

    def get_handoff(self, project_id: str, handoff_id: str) -> Optional[HandoffData]:
        """Get a handoff by ID."""
        ...

    def update_handoff_status(
        self,
        project_id: str,
        handoff_id: str,
        status: str,
        result_trace_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update handoff status."""
        ...

    def list_handoffs(
        self,
        project_id: str,
        status: Optional[str] = None,
        to_agent: Optional[str] = None,
    ) -> List[HandoffData]:
        """List handoffs with optional filters."""
        ...

    # Session operations
    def save_session(self, session: SessionData) -> None:
        """Save an agent session."""
        ...

    def get_session(self, project_id: str, session_id: str) -> Optional[SessionData]:
        """Get a session by ID."""
        ...

    def update_session(self, session: SessionData) -> None:
        """Update an existing session."""
        ...

    def list_sessions(
        self,
        project_id: str,
        status: Optional[str] = None,
    ) -> List[SessionData]:
        """List sessions for a project."""
        ...

    # Insight operations
    def save_insight(self, insight: InsightData) -> None:
        """Save an agent insight."""
        ...

    def list_insights(
        self,
        project_id: str,
        insight_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[InsightData]:
        """List insights with optional filters."""
        ...

    # Guidance operations
    def get_guidance(self, project_id: str) -> Dict[str, Any]:
        """Get guidance for a project."""
        ...

    def update_guidance(self, project_id: str, guidance: Dict[str, Any]) -> None:
        """Update guidance for a project."""
        ...


class BaseStorage(ABC):
    """
    Abstract base class for storage backends.

    Provides common functionality and default implementations.
    """

    def __init__(self, namespace: str = "default"):
        self.namespace = namespace

    @abstractmethod
    def save_handoff(self, project_id: str, handoff: HandoffData) -> None:
        """Save a handoff to the queue."""
        pass

    @abstractmethod
    def get_handoff(self, project_id: str, handoff_id: str) -> Optional[HandoffData]:
        """Get a handoff by ID."""
        pass

    @abstractmethod
    def update_handoff_status(
        self,
        project_id: str,
        handoff_id: str,
        status: str,
        result_trace_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update handoff status."""
        pass

    @abstractmethod
    def list_handoffs(
        self,
        project_id: str,
        status: Optional[str] = None,
        to_agent: Optional[str] = None,
    ) -> List[HandoffData]:
        """List handoffs with optional filters."""
        pass

    @abstractmethod
    def save_session(self, session: SessionData) -> None:
        """Save an agent session."""
        pass

    @abstractmethod
    def get_session(self, project_id: str, session_id: str) -> Optional[SessionData]:
        """Get a session by ID."""
        pass

    @abstractmethod
    def update_session(self, session: SessionData) -> None:
        """Update an existing session."""
        pass

    @abstractmethod
    def list_sessions(
        self,
        project_id: str,
        status: Optional[str] = None,
    ) -> List[SessionData]:
        """List sessions for a project."""
        pass

    @abstractmethod
    def save_insight(self, insight: InsightData) -> None:
        """Save an agent insight."""
        pass

    @abstractmethod
    def list_insights(
        self,
        project_id: str,
        insight_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[InsightData]:
        """List insights with optional filters."""
        pass

    @abstractmethod
    def get_guidance(self, project_id: str) -> Dict[str, Any]:
        """Get guidance for a project."""
        pass

    @abstractmethod
    def update_guidance(self, project_id: str, guidance: Dict[str, Any]) -> None:
        """Update guidance for a project."""
        pass


# Storage backend registry
_BACKENDS: Dict[StorageType, Type[BaseStorage]] = {}


def register_backend(storage_type: StorageType):
    """Decorator to register a storage backend."""
    def decorator(cls: Type[BaseStorage]) -> Type[BaseStorage]:
        _BACKENDS[storage_type] = cls
        return cls
    return decorator


def get_storage(
    storage_type: Optional[StorageType] = None,
    namespace: str = "default",
    **kwargs: Any,
) -> BaseStorage:
    """
    Get a storage backend instance.

    Auto-detects the appropriate backend if not specified:
    - Uses Kubernetes if running in-cluster or KUBECONFIG is set
    - Falls back to file storage otherwise

    Args:
        storage_type: Explicit storage type to use
        namespace: Namespace/directory for storage
        **kwargs: Additional backend-specific options

    Returns:
        Storage backend instance
    """
    # Import backends to register them
    from contextcore.storage import file, kubernetes

    if storage_type is None:
        storage_type = _detect_storage_type()

    if storage_type not in _BACKENDS:
        raise ValueError(f"Unknown storage type: {storage_type}")

    backend_class = _BACKENDS[storage_type]
    return backend_class(namespace=namespace, **kwargs)


def _detect_storage_type() -> StorageType:
    """Auto-detect the appropriate storage type."""
    # Check for Kubernetes
    if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount"):
        logger.info("Detected in-cluster Kubernetes environment")
        return StorageType.KUBERNETES

    if os.environ.get("KUBECONFIG"):
        logger.info("Detected KUBECONFIG environment variable")
        return StorageType.KUBERNETES

    if os.path.exists(os.path.expanduser("~/.kube/config")):
        logger.info("Detected local kubeconfig file")
        return StorageType.KUBERNETES

    # Default to file storage
    logger.info("No Kubernetes detected, using file storage")
    return StorageType.FILE
