"""
Agent-to-Agent Handoff Management

Structured task delegation between agents using pluggable storage backends.
Supports both Kubernetes CRD-based storage and file-based storage for
local development.

Example (auto-detect storage):
    manager = HandoffManager(
        project_id="checkout-service",
        agent_id="orchestrator"
    )

Example (explicit file storage for local dev):
    from contextcore.storage import StorageType
    manager = HandoffManager(
        project_id="checkout-service",
        agent_id="orchestrator",
        storage_type=StorageType.FILE
    )
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)


class HandoffPriority(str, Enum):
    """Task priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class HandoffStatus(str, Enum):
    """Handoff lifecycle states."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class ExpectedOutput:
    """Expected response format for a handoff."""
    type: str
    fields: list[str]


@dataclass
class Handoff:
    """Agent-to-agent task delegation."""
    id: str
    from_agent: str
    to_agent: str
    capability_id: str
    task: str
    inputs: dict[str, Any]
    expected_output: ExpectedOutput
    priority: HandoffPriority = HandoffPriority.NORMAL
    timeout_ms: int = 300000
    status: HandoffStatus = HandoffStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result_trace_id: str | None = None
    error_message: str | None = None


@dataclass
class HandoffResult:
    """Result of a completed handoff."""
    handoff_id: str
    status: HandoffStatus
    result_trace_id: str | None = None
    error_message: str | None = None


class HandoffManager:
    """
    Create and manage agent-to-agent handoffs.

    Uses pluggable storage backends (Kubernetes CRD or file-based) to store
    handoffs, allowing agents to coordinate without direct communication.

    Example:
        manager = HandoffManager(
            project_id="checkout-service",
            agent_id="orchestrator"
        )

        # Create handoff and wait for result
        result = manager.create_and_await(
            to_agent="o11y",
            capability_id="investigate_error",
            task="Find root cause of latency spike",
            inputs={
                "error_context": "P99 latency 800ms",
                "time_range": "2h"
            },
            expected_output=ExpectedOutput(
                type="analysis_report",
                fields=["root_cause", "evidence", "recommended_fix"]
            ),
            priority=HandoffPriority.HIGH,
            timeout_ms=300000
        )

        if result.status == HandoffStatus.COMPLETED:
            # Fetch result from Tempo using result_trace_id
            pass
    """

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        namespace: str = "default",
        storage_type: Optional[str] = None,
        kubeconfig: Optional[str] = None,
    ):
        """
        Initialize the handoff manager.

        Args:
            project_id: Project identifier
            agent_id: This agent's identifier
            namespace: Kubernetes namespace (for K8s storage)
            storage_type: Storage backend type (auto-detected if None)
            kubeconfig: Path to kubeconfig (for K8s storage)
        """
        self.project_id = project_id
        self.agent_id = agent_id
        self.namespace = namespace

        # Initialize storage backend
        from contextcore.storage import get_storage, StorageType

        if storage_type:
            storage_type_enum = StorageType(storage_type)
        else:
            storage_type_enum = None

        kwargs = {"namespace": namespace}
        if kubeconfig:
            kwargs["kubeconfig"] = kubeconfig

        self._storage = get_storage(storage_type=storage_type_enum, **kwargs)
        logger.info(
            f"HandoffManager initialized for project {project_id}, "
            f"agent {agent_id}, storage {type(self._storage).__name__}"
        )

    def create_handoff(
        self,
        to_agent: str,
        capability_id: str,
        task: str,
        inputs: dict[str, Any],
        expected_output: ExpectedOutput,
        priority: HandoffPriority = HandoffPriority.NORMAL,
        timeout_ms: int = 300000,
    ) -> str:
        """
        Create a new handoff.

        Returns:
            Handoff ID for tracking
        """
        from contextcore.storage.base import HandoffData

        handoff_id = f"handoff-{uuid.uuid4().hex[:12]}"

        handoff_data = HandoffData(
            id=handoff_id,
            from_agent=self.agent_id,
            to_agent=to_agent,
            capability_id=capability_id,
            task=task,
            inputs=inputs,
            expected_output={
                "type": expected_output.type,
                "fields": expected_output.fields,
            },
            priority=priority.value,
            timeout_ms=timeout_ms,
            status=HandoffStatus.PENDING.value,
            created_at=datetime.now(timezone.utc),
        )

        self._storage.save_handoff(self.project_id, handoff_data)
        logger.info(f"Created handoff {handoff_id} to agent {to_agent}")

        return handoff_id

    def get_handoff_status(self, handoff_id: str) -> HandoffResult:
        """Get current status of a handoff."""
        handoff = self._storage.get_handoff(self.project_id, handoff_id)

        if handoff is None:
            raise ValueError(f"Handoff {handoff_id} not found")

        return HandoffResult(
            handoff_id=handoff_id,
            status=HandoffStatus(handoff.status),
            result_trace_id=handoff.result_trace_id,
            error_message=handoff.error_message,
        )

    def await_result(
        self,
        handoff_id: str,
        timeout_ms: int = 300000,
        poll_interval_ms: int = 1000,
    ) -> HandoffResult:
        """
        Wait for handoff completion (blocking).

        Args:
            handoff_id: Handoff to wait for
            timeout_ms: Maximum wait time
            poll_interval_ms: Poll interval

        Returns:
            HandoffResult with final status
        """
        start = time.time()
        timeout_s = timeout_ms / 1000
        poll_s = poll_interval_ms / 1000

        while time.time() - start < timeout_s:
            result = self.get_handoff_status(handoff_id)

            if result.status in (
                HandoffStatus.COMPLETED,
                HandoffStatus.FAILED,
                HandoffStatus.TIMEOUT,
            ):
                return result

            time.sleep(poll_s)

        # Timeout
        return HandoffResult(
            handoff_id=handoff_id,
            status=HandoffStatus.TIMEOUT,
            error_message=f"Handoff timed out after {timeout_ms}ms",
        )

    def create_and_await(
        self,
        to_agent: str,
        capability_id: str,
        task: str,
        inputs: dict[str, Any],
        expected_output: ExpectedOutput,
        priority: HandoffPriority = HandoffPriority.NORMAL,
        timeout_ms: int = 300000,
    ) -> HandoffResult:
        """Create handoff and wait for result (convenience method)."""
        handoff_id = self.create_handoff(
            to_agent=to_agent,
            capability_id=capability_id,
            task=task,
            inputs=inputs,
            expected_output=expected_output,
            priority=priority,
            timeout_ms=timeout_ms,
        )

        return self.await_result(handoff_id, timeout_ms=timeout_ms)


class HandoffReceiver:
    """
    Receive and process handoffs as a receiving agent.

    Uses pluggable storage backends to poll for pending handoffs.
    Supports graceful shutdown via shutdown() method or context manager.

    Example:
        receiver = HandoffReceiver(
            agent_id="o11y",
            capabilities=["investigate_error", "create_dashboard"]
        )

        # Blocking poll mode with graceful shutdown
        for handoff in receiver.poll_handoffs(project_id="my-project"):
            receiver.accept(handoff.id, project_id="my-project")

            try:
                result = process_handoff(handoff)
                receiver.complete(handoff.id, project_id="my-project", result_trace_id=result.trace_id)
            except Exception as e:
                receiver.fail(handoff.id, project_id="my-project", reason=str(e))

        # Or use as context manager
        with HandoffReceiver(agent_id="o11y", capabilities=["investigate_error"]) as receiver:
            for handoff in receiver.poll_handoffs(project_id="my-project"):
                # Process handoff...
                pass
    """

    def __init__(
        self,
        agent_id: str,
        capabilities: list[str],
        namespace: str = "default",
        storage_type: Optional[str] = None,
        kubeconfig: Optional[str] = None,
    ):
        """
        Initialize the handoff receiver.

        Args:
            agent_id: This agent's identifier
            capabilities: List of capabilities this agent handles
            namespace: Kubernetes namespace (for K8s storage)
            storage_type: Storage backend type (auto-detected if None)
            kubeconfig: Path to kubeconfig (for K8s storage)
        """
        self.agent_id = agent_id
        self.capabilities = set(capabilities)
        self.namespace = namespace

        # Shutdown coordination
        self._shutdown_requested = False
        self._shutdown_event: Optional[asyncio.Event] = None

        # Initialize storage backend
        from contextcore.storage import get_storage, StorageType

        if storage_type:
            storage_type_enum = StorageType(storage_type)
        else:
            storage_type_enum = None

        kwargs = {"namespace": namespace}
        if kubeconfig:
            kwargs["kubeconfig"] = kubeconfig

        self._storage = get_storage(storage_type=storage_type_enum, **kwargs)
        logger.info(
            f"HandoffReceiver initialized for agent {agent_id}, "
            f"capabilities {capabilities}, storage {type(self._storage).__name__}"
        )

    def __enter__(self) -> "HandoffReceiver":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - triggers shutdown."""
        self.shutdown()

    async def __aenter__(self) -> "HandoffReceiver":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - triggers shutdown."""
        self.shutdown()

    def shutdown(self) -> None:
        """
        Request graceful shutdown of polling loops.

        Safe to call multiple times. After calling, poll_handoffs() and
        watch_handoffs_async() will complete their current iteration and return.
        """
        if self._shutdown_requested:
            return

        self._shutdown_requested = True
        logger.info(f"Shutdown requested for HandoffReceiver agent={self.agent_id}")

        # Signal async watchers
        if self._shutdown_event is not None:
            self._shutdown_event.set()

    @property
    def is_shutdown(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested

    def poll_handoffs(
        self,
        project_id: str,
        poll_interval_s: float = 1.0,
        timeout_s: Optional[float] = None,
    ):
        """
        Poll for pending handoffs (generator).

        Supports graceful shutdown via shutdown() method. When shutdown is
        requested, the generator will complete its current iteration and return.

        Args:
            project_id: Project to poll
            poll_interval_s: Seconds between polls
            timeout_s: Total timeout (None = poll until shutdown)

        Yields:
            Handoff objects for this agent's capabilities
        """
        start = time.time()

        while not self._shutdown_requested:
            if timeout_s and (time.time() - start) > timeout_s:
                logger.debug(f"Poll timeout reached after {timeout_s}s")
                return

            try:
                handoffs = self._storage.list_handoffs(
                    project_id=project_id,
                    status=HandoffStatus.PENDING.value,
                    to_agent=self.agent_id,
                )

                for h in handoffs:
                    # Check shutdown between processing handoffs
                    if self._shutdown_requested:
                        logger.debug("Shutdown requested, stopping poll")
                        return

                    if h.capability_id in self.capabilities:
                        expected_output = ExpectedOutput(
                            type=h.expected_output.get("type", ""),
                            fields=h.expected_output.get("fields", []),
                        )
                        yield Handoff(
                            id=h.id,
                            from_agent=h.from_agent,
                            to_agent=h.to_agent,
                            capability_id=h.capability_id,
                            task=h.task,
                            inputs=h.inputs,
                            expected_output=expected_output,
                            priority=HandoffPriority(h.priority),
                            timeout_ms=h.timeout_ms,
                            status=HandoffStatus(h.status),
                            created_at=h.created_at,
                        )

            except Exception as e:
                logger.warning(f"Error polling handoffs: {e}")

            # Use interruptible sleep (check shutdown periodically)
            sleep_remaining = poll_interval_s
            while sleep_remaining > 0 and not self._shutdown_requested:
                sleep_chunk = min(0.1, sleep_remaining)
                time.sleep(sleep_chunk)
                sleep_remaining -= sleep_chunk

        logger.info(f"Polling stopped for agent {self.agent_id}")

    async def watch_handoffs_async(
        self,
        project_id: str,
        poll_interval_s: float = 1.0,
    ) -> AsyncIterator[Handoff]:
        """
        Async generator for watching handoffs.

        Supports graceful shutdown via shutdown() method. When shutdown is
        requested, the generator will complete its current iteration and return.

        Args:
            project_id: Project to watch
            poll_interval_s: Seconds between polls

        Yields:
            Handoff objects for this agent's capabilities
        """
        # Initialize shutdown event for this async context
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()

        while not self._shutdown_requested:
            try:
                handoffs = self._storage.list_handoffs(
                    project_id=project_id,
                    status=HandoffStatus.PENDING.value,
                    to_agent=self.agent_id,
                )

                for h in handoffs:
                    # Check shutdown between processing handoffs
                    if self._shutdown_requested:
                        logger.debug("Shutdown requested, stopping async watch")
                        return

                    if h.capability_id in self.capabilities:
                        expected_output = ExpectedOutput(
                            type=h.expected_output.get("type", ""),
                            fields=h.expected_output.get("fields", []),
                        )
                        yield Handoff(
                            id=h.id,
                            from_agent=h.from_agent,
                            to_agent=h.to_agent,
                            capability_id=h.capability_id,
                            task=h.task,
                            inputs=h.inputs,
                            expected_output=expected_output,
                            priority=HandoffPriority(h.priority),
                            timeout_ms=h.timeout_ms,
                            status=HandoffStatus(h.status),
                            created_at=h.created_at,
                        )

            except Exception as e:
                logger.warning(f"Error watching handoffs: {e}")

            # Use asyncio.wait with shutdown event for interruptible sleep
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=poll_interval_s,
                )
                # If we get here, shutdown was requested
                break
            except asyncio.TimeoutError:
                # Normal timeout, continue polling
                pass

        logger.info(f"Async watch stopped for agent {self.agent_id}")

    def accept(self, handoff_id: str, project_id: str):
        """Mark handoff as accepted."""
        self._storage.update_handoff_status(
            project_id=project_id,
            handoff_id=handoff_id,
            status=HandoffStatus.ACCEPTED.value,
        )
        logger.info(f"Accepted handoff {handoff_id}")

    def complete(
        self,
        handoff_id: str,
        project_id: str,
        result_trace_id: str,
    ):
        """Mark handoff as completed with result."""
        self._storage.update_handoff_status(
            project_id=project_id,
            handoff_id=handoff_id,
            status=HandoffStatus.COMPLETED.value,
            result_trace_id=result_trace_id,
        )
        logger.info(f"Completed handoff {handoff_id}")

    def fail(
        self,
        handoff_id: str,
        project_id: str,
        reason: str,
    ):
        """Mark handoff as failed."""
        self._storage.update_handoff_status(
            project_id=project_id,
            handoff_id=handoff_id,
            status=HandoffStatus.FAILED.value,
            error_message=reason,
        )
        logger.warning(f"Failed handoff {handoff_id}: {reason}")
