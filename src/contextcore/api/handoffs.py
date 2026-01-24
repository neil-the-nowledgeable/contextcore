"""A2A-style API facade for agent handoffs.
__all__ = ['HandoffsAPI']


This module provides a modern API surface using resource.action naming patterns
for agent-to-agent handoffs, mapping to existing HandoffManager and HandoffReceiver
functionality from the ContextCore project.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, Generator, Optional

from contextcore.agent.handoff import HandoffManager, HandoffReceiver, HandoffStorage, HandoffResult
from contextcore.compat.otel_genai import DualEmitAttributes
from opentelemetry import trace

__all__ = ["HandoffsAPI"]


class HandoffsAPI:
    """A2A-style API for agent handoffs.

    Provides a modern API surface using resource.action naming pattern for
    agent-to-agent handoffs, mapping to existing HandoffManager and 
    HandoffReceiver functionality.

    Example:
        api = HandoffsAPI(project_id="checkout", agent_id="claude")
        handoff = api.create(
            to_agent="o11y-agent",
            capability_id="investigate", 
            task="Find root cause of latency spike",
            inputs={"trace_id": "abc123"}
        )
        result = api.await_(handoff.id, timeout_ms=30000)
    """

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        storage: Optional[HandoffStorage] = None,
    ) -> None:
        """Initialize the HandoffsAPI.

        Args:
            project_id: The project identifier
            agent_id: The agent identifier
            storage: Optional handoff storage backend
        """
        self._project_id = project_id
        self._agent_id = agent_id
        self._manager = HandoffManager(project_id, agent_id, storage)
        self._receiver = HandoffReceiver(agent_id, storage)
        self._dual_emit = DualEmitAttributes()

    # Client-side methods (HandoffManager mapping)

    def create(
        self,
        to_agent: str,
        capability_id: str,
        task: str,
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> HandoffResult:
        """Create a handoff to another agent.

        Args:
            to_agent: Target agent identifier
            capability_id: Capability to invoke on target agent
            task: Description of the task to perform
            inputs: Input parameters for the task
            **kwargs: Additional handoff parameters

        Returns:
            HandoffResult with handoff details and status
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_span("handoffs.create") as span:
            attributes = self._dual_emit.transform({
                "handoff.to_agent": to_agent,
                "handoff.capability_id": capability_id,
                "handoff.task": task,
                "agent.id": self._agent_id,
                "project.id": self._project_id,
            })
            span.set_attributes(attributes)
            
            return self._manager.create_handoff(
                to_agent=to_agent,
                capability_id=capability_id,
                task=task,
                inputs=inputs,
                **kwargs,
            )

    def get(self, handoff_id: str) -> HandoffResult:
        """Get the current status of a handoff.

        Args:
            handoff_id: Unique identifier of the handoff

        Returns:
            HandoffResult with current status
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_span("handoffs.get") as span:
            attributes = self._dual_emit.transform({
                "handoff.id": handoff_id,
                "agent.id": self._agent_id,
            })
            span.set_attributes(attributes)
            
            return self._manager.get_handoff_status(handoff_id)

    def await_(self, handoff_id: str, timeout_ms: int = 30000) -> HandoffResult:
        """Await the result of a handoff.

        Note: Method name uses await_ to avoid Python keyword conflict.

        Args:
            handoff_id: Unique identifier of the handoff
            timeout_ms: Maximum time to wait in milliseconds

        Returns:
            HandoffResult with final result or timeout status

        Raises:
            TimeoutError: If handoff doesn't complete within timeout
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_span("handoffs.await") as span:
            attributes = self._dual_emit.transform({
                "handoff.id": handoff_id,
                "handoff.timeout_ms": timeout_ms,
                "agent.id": self._agent_id,
            })
            span.set_attributes(attributes)
            
            return self._manager.await_result(handoff_id, timeout_ms)

    def cancel(self, handoff_id: str) -> bool:
        """Cancel a pending handoff.

        Args:
            handoff_id: Unique identifier of the handoff to cancel

        Returns:
            True if successfully cancelled, False otherwise
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_span("handoffs.cancel") as span:
            attributes = self._dual_emit.transform({
                "handoff.id": handoff_id,
                "agent.id": self._agent_id,
            })
            span.set_attributes(attributes)
            
            # Map to existing manager method or implement cancellation logic
            return self._manager.cancel_handoff(handoff_id)

    def send(
        self,
        to_agent: str,
        capability_id: str,
        task: str,
        inputs: Dict[str, Any],
        timeout_ms: int = 30000,
    ) -> HandoffResult:
        """Create and immediately await a handoff (convenience method).

        Args:
            to_agent: Target agent identifier
            capability_id: Capability to invoke on target agent
            task: Description of the task to perform
            inputs: Input parameters for the task
            timeout_ms: Maximum time to wait in milliseconds

        Returns:
            HandoffResult with final result
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_span("handoffs.send") as span:
            attributes = self._dual_emit.transform({
                "handoff.to_agent": to_agent,
                "handoff.capability_id": capability_id,
                "handoff.task": task,
                "handoff.timeout_ms": timeout_ms,
                "agent.id": self._agent_id,
                "project.id": self._project_id,
            })
            span.set_attributes(attributes)
            
            # Create handoff then immediately await result
            handoff = self.create(to_agent, capability_id, task, inputs)
            return self.await_(handoff.id, timeout_ms)

    # Server-side methods (HandoffReceiver mapping)

    def accept(self, handoff_id: str) -> bool:
        """Accept an incoming handoff.

        Args:
            handoff_id: Unique identifier of the handoff to accept

        Returns:
            True if successfully accepted, False otherwise
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_span("handoffs.accept") as span:
            attributes = self._dual_emit.transform({
                "handoff.id": handoff_id,
                "agent.id": self._agent_id,
            })
            span.set_attributes(attributes)
            
            return self._receiver.accept(handoff_id)

    def complete(self, handoff_id: str, result_trace_id: str) -> bool:
        """Complete a handoff with successful result.

        Args:
            handoff_id: Unique identifier of the handoff
            result_trace_id: Trace ID of the completed work

        Returns:
            True if successfully completed, False otherwise
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_span("handoffs.complete") as span:
            attributes = self._dual_emit.transform({
                "handoff.id": handoff_id,
                "handoff.result_trace_id": result_trace_id,
                "agent.id": self._agent_id,
            })
            span.set_attributes(attributes)
            
            return self._receiver.complete(handoff_id, result_trace_id)

    def fail(self, handoff_id: str, reason: str) -> bool:
        """Fail a handoff with error reason.

        Args:
            handoff_id: Unique identifier of the handoff
            reason: Description of why the handoff failed

        Returns:
            True if failure recorded successfully, False otherwise
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_span("handoffs.fail") as span:
            attributes = self._dual_emit.transform({
                "handoff.id": handoff_id,
                "handoff.failure_reason": reason,
                "agent.id": self._agent_id,
            })
            span.set_attributes(attributes)
            
            return self._receiver.fail(handoff_id, reason)

    def subscribe(self, project_id: Optional[str] = None) -> Generator[HandoffResult, None, None]:
        """Subscribe to incoming handoffs as a generator.

        Args:
            project_id: Optional project filter, defaults to instance project_id

        Yields:
            HandoffResult objects for incoming handoffs
        """
        tracer = trace.get_tracer(__name__)
        with tracer.start_span("handoffs.subscribe") as span:
            target_project = project_id or self._project_id
            attributes = self._dual_emit.transform({
                "project.id": target_project,
                "agent.id": self._agent_id,
            })
            span.set_attributes(attributes)
            
            # Map poll_handoffs to generator pattern
            for handoff in self._receiver.poll_handoffs(target_project):
                yield handoff


# Add deprecation warning patch - to be applied to original classes
def _patch_deprecation_warnings() -> None:
    """Patch original classes with deprecation warnings."""
    import contextcore.agent.handoff as handoff_module
    
    # Store original classes
    OriginalHandoffManager = handoff_module.HandoffManager
    OriginalHandoffReceiver = handoff_module.HandoffReceiver
    
    class _DeprecatedHandoffManager(OriginalHandoffManager):
        def __init__(self, *args, **kwargs):
            warnings.warn(
                "Direct usage of HandoffManager is deprecated. "
                "Use HandoffsAPI from contextcore.api.handoffs instead.",
                DeprecationWarning,
                stacklevel=2
            )
            super().__init__(*args, **kwargs)
    
    class _DeprecatedHandoffReceiver(OriginalHandoffReceiver):
        def __init__(self, *args, **kwargs):
            warnings.warn(
                "Direct usage of HandoffReceiver is deprecated. "
                "Use HandoffsAPI from contextcore.api.handoffs instead.",
                DeprecationWarning,
                stacklevel=2
            )
            super().__init__(*args, **kwargs)
    
    # Replace classes in module
    handoff_module.HandoffManager = _DeprecatedHandoffManager
    handoff_module.HandoffReceiver = _DeprecatedHandoffReceiver


# Apply deprecation warnings on module import
_patch_deprecation_warnings()
