"""
State transition event model for tracking handoff lifecycle via OpenTelemetry.
__all__ = ['HandoffEventType', 'HandoffEvent', 'HandoffEventEmitter']


This module provides structured event types and an emitter for tracking handoff
state changes as OTel span events, enabling monitoring and debugging of the
handoff lifecycle in the ContextCore project.
"""

from opentelemetry import trace
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import logging

logger = logging.getLogger(__name__)


class HandoffEventType(str, Enum):
    """Event types for handoff lifecycle tracking."""
    CREATED = "handoff.created"
    STATUS_UPDATE = "handoff.status_update"
    INPUT_REQUIRED = "handoff.input_required"
    INPUT_PROVIDED = "handoff.input_provided"
    ARTIFACT_ADDED = "handoff.artifact_added"
    MESSAGE_ADDED = "handoff.message_added"
    TIMEOUT_WARNING = "handoff.timeout_warning"
    COMPLETED = "handoff.completed"
    FAILED = "handoff.failed"


@dataclass
class HandoffEvent:
    """
    Structured data for handoff lifecycle events.
    
    Contains all necessary fields to capture event context and metadata
    for OpenTelemetry span events and attributes.
    """
    event_type: HandoffEventType
    handoff_id: str
    timestamp: datetime
    from_status: str | None = None
    to_status: str | None = None
    agent_id: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class HandoffEventEmitter:
    """
    OpenTelemetry-based event emitter for handoff lifecycle tracking.
    
    Creates spans and events for each handoff state transition to enable
    monitoring, debugging, and observability of the handoff process.
    """
    
    def __init__(self, tracer_name: str = "contextcore.handoffs"):
        """
        Initialize the event emitter with an OpenTelemetry tracer.
        
        Args:
            tracer_name: Name for the OTel tracer instance
        """
        self._tracer = trace.get_tracer(tracer_name)
    
    def _emit_event(self, event: HandoffEvent) -> None:
        """
        Internal method to emit an event as an OTel span with attributes.
        
        Args:
            event: The structured event data to emit
        """
        try:
            with self._tracer.start_as_current_span(f"handoff.{event.event_type.value.split('.')[-1]}") as span:
                # Set span attributes for all non-None event fields
                attributes = {
                    "handoff.id": event.handoff_id,
                    "handoff.event_type": event.event_type.value,
                    "handoff.timestamp": event.timestamp.isoformat(),
                }
                
                # Add optional attributes if present
                if event.from_status:
                    attributes["handoff.from_status"] = event.from_status
                if event.to_status:
                    attributes["handoff.to_status"] = event.to_status
                if event.agent_id:
                    attributes["handoff.agent_id"] = event.agent_id
                if event.message:
                    attributes["handoff.message"] = event.message
                
                # Add metadata as attributes
                for key, value in event.metadata.items():
                    attributes[f"handoff.{key}"] = str(value)
                
                span.set_attributes(attributes)
                span.add_event(event.event_type.value, attributes)
                
                # Log at appropriate level based on event type
                if event.event_type in [HandoffEventType.FAILED]:
                    logger.error(f"Handoff event: {event.event_type.value} for {event.handoff_id}")
                elif event.event_type in [HandoffEventType.TIMEOUT_WARNING]:
                    logger.warning(f"Handoff event: {event.event_type.value} for {event.handoff_id}")
                else:
                    logger.info(f"Handoff event: {event.event_type.value} for {event.handoff_id}")
                    
        except Exception as e:
            logger.error(f"Failed to emit handoff event {event.event_type.value}: {e}")

    def emit_created(self, handoff_id: str, from_agent: str, to_agent: str, capability_id: str) -> None:
        """
        Emit a handoff creation event.
        
        Args:
            handoff_id: Unique identifier for the handoff
            from_agent: ID of the agent initiating the handoff
            to_agent: ID of the agent receiving the handoff
            capability_id: ID of the capability being handed off
        """
        event = HandoffEvent(
            event_type=HandoffEventType.CREATED,
            handoff_id=handoff_id,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "from_agent": from_agent,
                "to_agent": to_agent,
                "capability_id": capability_id
            }
        )
        self._emit_event(event)

    def emit_status_update(self, handoff_id: str, from_status: str, to_status: str, 
                          agent_id: str | None = None, reason: str | None = None) -> None:
        """
        Emit a handoff status update event.
        
        Args:
            handoff_id: Unique identifier for the handoff
            from_status: Previous handoff status
            to_status: New handoff status
            agent_id: ID of the agent making the status change
            reason: Optional reason for the status change
        """
        event = HandoffEvent(
            event_type=HandoffEventType.STATUS_UPDATE,
            handoff_id=handoff_id,
            timestamp=datetime.now(timezone.utc),
            from_status=from_status,
            to_status=to_status,
            agent_id=agent_id,
            message=reason
        )
        self._emit_event(event)

    def emit_input_required(self, handoff_id: str, question: str, options: list[str] | None = None) -> None:
        """
        Emit an input required event.
        
        Args:
            handoff_id: Unique identifier for the handoff
            question: The question or prompt requiring input
            options: Optional list of valid input options
        """
        event = HandoffEvent(
            event_type=HandoffEventType.INPUT_REQUIRED,
            handoff_id=handoff_id,
            timestamp=datetime.now(timezone.utc),
            message=question,
            metadata={"options": options} if options else {}
        )
        self._emit_event(event)

    def emit_input_provided(self, handoff_id: str, request_id: str, value: str) -> None:
        """
        Emit an input provided event.
        
        Args:
            handoff_id: Unique identifier for the handoff
            request_id: ID of the input request being fulfilled
            value: The input value provided
        """
        event = HandoffEvent(
            event_type=HandoffEventType.INPUT_PROVIDED,
            handoff_id=handoff_id,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "request_id": request_id,
                "value": value
            }
        )
        self._emit_event(event)

    def emit_artifact_added(self, handoff_id: str, artifact_id: str, artifact_type: str) -> None:
        """
        Emit an artifact added event.
        
        Args:
            handoff_id: Unique identifier for the handoff
            artifact_id: ID of the artifact being added
            artifact_type: Type/category of the artifact
        """
        event = HandoffEvent(
            event_type=HandoffEventType.ARTIFACT_ADDED,
            handoff_id=handoff_id,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "artifact_id": artifact_id,
                "artifact_type": artifact_type
            }
        )
        self._emit_event(event)

    def emit_message_added(self, handoff_id: str, message_id: str, role: str) -> None:
        """
        Emit a message added event.
        
        Args:
            handoff_id: Unique identifier for the handoff
            message_id: ID of the message being added
            role: Role of the message sender (user, assistant, etc.)
        """
        event = HandoffEvent(
            event_type=HandoffEventType.MESSAGE_ADDED,
            handoff_id=handoff_id,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "message_id": message_id,
                "role": role
            }
        )
        self._emit_event(event)

    def emit_completed(self, handoff_id: str, result_trace_id: str, duration_ms: float) -> None:
        """
        Emit a handoff completion event.
        
        Args:
            handoff_id: Unique identifier for the handoff
            result_trace_id: Trace ID of the completed handoff result
            duration_ms: Total duration of the handoff in milliseconds
        """
        event = HandoffEvent(
            event_type=HandoffEventType.COMPLETED,
            handoff_id=handoff_id,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "result_trace_id": result_trace_id,
                "duration_ms": duration_ms
            }
        )
        self._emit_event(event)

    def emit_failed(self, handoff_id: str, error_message: str, duration_ms: float) -> None:
        """
        Emit a handoff failure event.
        
        Args:
            handoff_id: Unique identifier for the handoff
            error_message: Description of the failure
            duration_ms: Duration before failure in milliseconds
        """
        event = HandoffEvent(
            event_type=HandoffEventType.FAILED,
            handoff_id=handoff_id,
            timestamp=datetime.now(timezone.utc),
            message=error_message,
            metadata={"duration_ms": duration_ms}
        )
        self._emit_event(event)


# Global default emitter instance for ease of use
default_emitter = HandoffEventEmitter()

__all__ = [
    "HandoffEventType",
    "HandoffEvent", 
    "HandoffEventEmitter",
    "default_emitter"
]
