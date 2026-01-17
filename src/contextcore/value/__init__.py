"""
Value Capability module for ContextCore.

Provides value-focused capabilities that bridge technical capabilities
to user benefits, enabling discovery through value propositions.

Integrates with:
- Knowledge module (extends KnowledgeCapability)
- Skill module (TraceQL queries)
- RBAC (permission-based access)

Example usage:
    from contextcore.value import (
        ValueCapabilityParser,
        ValueEmitter,
        ValueType,
        Persona,
    )

    # Parse a value-focused skill
    parser = ValueCapabilityParser("~/.claude/skills/capability-value-promoter")
    manifest, capabilities = parser.parse()

    # Emit to Tempo
    emitter = ValueEmitter(agent_id="value-promoter")
    trace_id, span_ids = emitter.emit_value_with_capabilities(manifest, capabilities)

    # Query by value type
    # TraceQL: { value.type = "direct" }

    # Query by persona
    # TraceQL: { value.persona = "developer" }
"""

from contextcore.value.models import (
    # Enums
    ValueType,
    Persona,
    Channel,
    # Models
    ValueAttribute,
    ValueCapability,
    ValueManifest,
    # Helpers
    derive_value_type,
    get_persona_from_context,
    get_channel_from_context,
)
from contextcore.value.parser import ValueCapabilityParser
from contextcore.value.emitter import ValueEmitter

__all__ = [
    # Enums
    "ValueType",
    "Persona",
    "Channel",
    # Models
    "ValueAttribute",
    "ValueCapability",
    "ValueManifest",
    # Parser
    "ValueCapabilityParser",
    # Emitter
    "ValueEmitter",
    # Helpers
    "derive_value_type",
    "get_persona_from_context",
    "get_channel_from_context",
]
