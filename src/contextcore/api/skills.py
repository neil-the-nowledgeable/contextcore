"""
A2A-style API facade for the Skills API.
__all__ = ['SkillNotFoundError', 'SkillsAPI', 'CapabilitiesAPI']


This module provides a modern API surface using resource.action naming pattern 
for skill registration and invocation, mapping to existing SkillCapabilityEmitter/Querier.
"""

from typing import Dict, List, Optional, Any
import logging

from opentelemetry import trace

from src.contextcore.skill.capability_emitter import SkillCapabilityEmitter
from src.contextcore.skill.capability_querier import SkillCapabilityQuerier
from src.contextcore.compat.otel_genai import DualEmitAttributes
from src.contextcore.models.skill import SkillManifest, SkillCapability

# Initialize tracer for OpenTelemetry spans
tracer = trace.get_tracer(__name__)

# Set up logger for error handling
logger = logging.getLogger(__name__)

__all__ = ['SkillsAPI', 'CapabilitiesAPI', 'SkillNotFoundError']


class SkillNotFoundError(Exception):
    """Raised when a skill or capability cannot be found."""
    pass


class SkillsAPI:
    """A2A-style API for agent skills.

    Provides a modern API surface using resource.action naming pattern for skill
    registration and invocation, mapping to existing SkillCapabilityEmitter/Querier.

    Example:
        api = SkillsAPI(agent_id="claude-code")

        # Register skill
        api.emit(manifest=my_manifest, capabilities=[cap1, cap2])

        # Query skills
        matching = api.query(trigger="format code", budget_tokens=1000)

        # Invoke capability
        api.capabilities.invoke("skill-1", "format", inputs={"code": "..."})
    """

    def __init__(self, agent_id: str, tempo_url: Optional[str] = None) -> None:
        """Initialize the Skills API.

        Args:
            agent_id: Unique identifier for the agent
            tempo_url: Optional Tempo URL for telemetry backend

        Raises:
            ValueError: If agent_id is empty or None
        """
        if not agent_id:
            raise ValueError("agent_id cannot be empty")
        
        self.agent_id = agent_id
        self._emitter = SkillCapabilityEmitter(agent_id=agent_id)
        self._querier = SkillCapabilityQuerier(tempo_url=tempo_url)
        self._capabilities_api = CapabilitiesAPI(self._emitter)

    def emit(self, manifest: SkillManifest, capabilities: List[SkillCapability]) -> None:
        """Register a skill with its capabilities.
        
        Args:
            manifest: The skill manifest to register
            capabilities: List of capabilities associated with the skill

        Raises:
            ValueError: If manifest or capabilities are invalid
        """
        if not manifest or not isinstance(capabilities, list):
            raise ValueError("Invalid manifest or capabilities provided")

        attributes = DualEmitAttributes.transform({
            'skill_id': manifest.id,
            'agent_id': self.agent_id,
            'capability_count': len(capabilities)
        })
        
        with tracer.start_as_current_span("skills.emit", attributes=attributes):
            self._emitter.emit_skill_with_capabilities(manifest, capabilities)

    def query(
        self, 
        trigger: str, 
        category: Optional[str] = None, 
        budget_tokens: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query skills based on trigger and optional filters.

        Args:
            trigger: The trigger string to match skills
            category: Optional category filter
            budget_tokens: Optional token budget filter

        Returns:
            List of matched skills based on the query

        Raises:
            ValueError: If trigger is empty
        """
        if not trigger:
            raise ValueError("trigger cannot be empty")

        attributes = DualEmitAttributes.transform({
            'trigger': trigger,
            'category': category,
            'budget_tokens': budget_tokens,
            'agent_id': self.agent_id
        })

        try:
            with tracer.start_as_current_span("skills.query", attributes=attributes):
                return self._querier.query(
                    trigger, 
                    category=category, 
                    budget_tokens=budget_tokens
                )
        except Exception as e:
            logger.error(f"Query failed for trigger '{trigger}': {e}")
            raise

    def get(self, skill_id: str) -> Optional[SkillManifest]:
        """Retrieve a specific skill by its ID.

        Args:
            skill_id: The ID of the skill to retrieve

        Returns:
            The skill manifest or None if not found

        Raises:
            ValueError: If skill_id is empty
        """
        if not skill_id:
            raise ValueError("skill_id cannot be empty")

        attributes = DualEmitAttributes.transform({
            'skill_id': skill_id,
            'agent_id': self.agent_id
        })

        try:
            with tracer.start_as_current_span("skills.get", attributes=attributes):
                return self._querier.get(skill_id)
        except Exception as e:
            logger.error(f"Failed to retrieve skill {skill_id}: {e}")
            return None

    def list(self) -> List[SkillManifest]:
        """List all registered skills.

        Returns:
            List of all skill manifests

        Raises:
            RuntimeError: If there's a failure while listing skills
        """
        attributes = DualEmitAttributes.transform({
            'agent_id': self.agent_id
        })

        try:
            with tracer.start_as_current_span("skills.list", attributes=attributes):
                return self._querier.list()
        except Exception as e:
            logger.error(f"Failed to list skills: {e}")
            raise RuntimeError(f"Failed to list skills: {e}") from e

    @property
    def capabilities(self) -> 'CapabilitiesAPI':
        """Access capability-specific operations.
        
        Returns:
            CapabilitiesAPI instance for capability operations
        """
        return self._capabilities_api


class CapabilitiesAPI:
    """Nested API class for capability-specific operations.
    
    Handles capability emission, invocation, completion, and failure operations
    with proper telemetry and error handling.
    """

    def __init__(self, emitter: SkillCapabilityEmitter) -> None:
        """Initialize the Capabilities API.

        Args:
            emitter: The skill capability emitter instance
        """
        self._emitter = emitter

    def emit(self, skill_id: str, capability: SkillCapability) -> None:
        """Emit a capability for a specific skill.

        Args:
            skill_id: The ID of the skill
            capability: The capability to emit

        Raises:
            ValueError: If skill_id or capability is invalid
        """
        if not skill_id or not capability:
            raise ValueError("skill_id and capability cannot be empty")
        
        attributes = DualEmitAttributes.transform({
            'skill_id': skill_id,
            'capability_id': capability.id
        })

        with tracer.start_as_current_span("capabilities.emit", attributes=attributes):
            self._emitter.emit_capability(skill_id=skill_id, capability=capability)

    def invoke(
        self, 
        skill_id: str, 
        capability_id: str, 
        inputs: Dict[str, Any]
    ) -> None:
        """Invoke a specific capability of a skill.

        Args:
            skill_id: The ID of the skill
            capability_id: The ID of the capability to invoke
            inputs: The inputs for the capability

        Raises:
            ValueError: If required parameters are empty
            RuntimeError: If invocation fails
        """
        if not skill_id or not capability_id:
            raise ValueError("skill_id and capability_id cannot be empty")
        
        if inputs is None:
            inputs = {}

        attributes = DualEmitAttributes.transform({
            'skill_id': skill_id,
            'capability_id': capability_id,
            'input_keys': list(inputs.keys()) if inputs else []
        })

        try:
            with tracer.start_as_current_span("capabilities.invoke", attributes=attributes):
                self._emitter.emit_invoked(skill_id, capability_id, inputs)
        except Exception as e:
            logger.error(f"Failed to invoke capability {capability_id} on skill {skill_id}: {e}")
            raise RuntimeError(f"Capability invocation failed: {e}") from e

    def complete(
        self, 
        skill_id: str, 
        capability_id: str, 
        outputs: Dict[str, Any]
    ) -> None:
        """Mark a capability invocation as successfully completed.

        Args:
            skill_id: The ID of the skill
            capability_id: The ID of the capability
            outputs: The outputs from the successful completion

        Raises:
            ValueError: If required parameters are empty
        """
        if not skill_id or not capability_id:
            raise ValueError("skill_id and capability_id cannot be empty")
        
        if outputs is None:
            outputs = {}

        attributes = DualEmitAttributes.transform({
            'skill_id': skill_id,
            'capability_id': capability_id,
            'output_keys': list(outputs.keys()) if outputs else []
        })

        with tracer.start_as_current_span("capabilities.complete", attributes=attributes):
            self._emitter.emit_succeeded(skill_id, capability_id, outputs)

    def fail(self, skill_id: str, capability_id: str, error: str) -> None:
        """Mark a capability invocation as failed.

        Args:
            skill_id: The ID of the skill
            capability_id: The ID of the capability
            error: The error message describing the failure

        Raises:
            ValueError: If required parameters are empty
        """
        if not skill_id or not capability_id or not error:
            raise ValueError("skill_id, capability_id, and error cannot be empty")

        attributes = DualEmitAttributes.transform({
            'skill_id': skill_id,
            'capability_id': capability_id,
            'error': error
        })

        with tracer.start_as_current_span("capabilities.fail", attributes=attributes):
            self._emitter.emit_failed(skill_id, capability_id, error)
