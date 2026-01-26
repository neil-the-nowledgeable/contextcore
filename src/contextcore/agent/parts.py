"""A2A-compatible Message model for handoff communication."""

from .part import Part, PartType
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

class Message:
    """A2A-compatible message with ContextCore extensions.
    
    Provides bi-directional compatibility between A2A Message format
    and ContextCore's extended message model with agent attribution.
    """
    message_id: str = field(default="")
    role: MessageRole = MessageRole.USER
    parts: list[Part] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # ContextCore extensions
    agent_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize message with auto-generated ID if needed."""
        if not self.message_id:
            # Use object.__setattr__ to modify frozen dataclass
            object.__setattr__(self, 'message_id', f"msg-{uuid.uuid4().hex[:12]}")

    def to_a2a_dict(self) -> dict[str, Any]:
        """Convert to A2A Message format.
        
        Returns only the standard A2A fields, excluding ContextCore extensions.
        """
        return {
            "messageId": self.message_id,
            "role": self.role.value,
            "parts": [part.to_a2a_dict() for part in self.parts],
            "timestamp": self.timestamp.isoformat(),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to full dict with ContextCore extensions.
        
        Includes all fields including agent_id, session_id, and metadata.
        """
        return {
            "message_id": self.message_id,
            "role": self.role.value,
            "parts": [part.to_dict() for part in self.parts],
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_a2a_dict(cls, data: dict[str, Any]) -> Message:
        """Parse from A2A Message format.
        
        Args:
            data: Dictionary containing A2A message fields
            
        Returns:
            Message instance with A2A data
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        try:
            # Parse timestamp - handle both string and datetime
            timestamp_data = data["timestamp"]
            if isinstance(timestamp_data, str):
                timestamp = datetime.fromisoformat(timestamp_data.replace('Z', '+00:00'))
            else:
                timestamp = timestamp_data
                
            parts = [Part.from_a2a_dict(part_data) for part_data in data["parts"]]
            
            return cls(
                message_id=data["messageId"],
                role=MessageRole(data["role"]),
                parts=parts,
                timestamp=timestamp,
            )
        except KeyError as e:
            raise ValueError(f"Missing required A2A field: {e}")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid A2A message data: {e}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """Parse from dict (handles both A2A and ContextCore formats).
        
        Auto-detects format based on field names and parses accordingly.
        """
        # Detect format by checking for ContextCore-specific fields
        if "message_id" in data:
            # ContextCore format
            try:
                timestamp_data = data["timestamp"]
                if isinstance(timestamp_data, str):
                    timestamp = datetime.fromisoformat(timestamp_data.replace('Z', '+00:00'))
                else:
                    timestamp = timestamp_data
                    
                parts = [Part.from_dict(part_data) for part_data in data["parts"]]
                
                return cls(
                    message_id=data["message_id"],
                    role=MessageRole(data["role"]),
                    parts=parts,
                    timestamp=timestamp,
                    agent_id=data.get("agent_id"),
                    session_id=data.get("session_id"),
                    metadata=data.get("metadata", {}),
                )
            except KeyError as e:
                raise ValueError(f"Missing required ContextCore field: {e}")
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid ContextCore message data: {e}")
        else:
            # Assume A2A format
            return cls.from_a2a_dict(data)

    @classmethod
    def from_text(cls, text: str, role: MessageRole = MessageRole.USER, **kwargs) -> Message:
        """Create message from plain text.
        
        Args:
            text: Message text content
            role: Message role (defaults to USER)
            **kwargs: Additional message fields
            
        Returns:
            Message with single text part
        """
        return cls(
            role=role,
            parts=[Part.text(text)],
            **kwargs
        )

    @classmethod
    def from_parts(cls, parts: list[Part], role: MessageRole = MessageRole.USER, **kwargs) -> Message:
        """Create message from parts.
        
        Args:
            parts: List of message parts
            role: Message role (defaults to USER)
            **kwargs: Additional message fields
            
        Returns:
            Message with specified parts
        """
        return cls(
            role=role,
            parts=parts,
            **kwargs
        )

    @classmethod
    def system_message(cls, text: str, **kwargs) -> Message:
        """Create system message.
        
        Args:
            text: System message text
            **kwargs: Additional message fields
            
        Returns:
            System message with text content
        """
        return cls.from_text(text, role=MessageRole.SYSTEM, **kwargs)

    @classmethod
    def agent_message(cls, text: str, agent_id: str, **kwargs) -> Message:
        """Create agent message with attribution.
        
        Args:
            text: Agent message text
            agent_id: ID of the agent sending the message
            **kwargs: Additional message fields
            
        Returns:
            Agent message with attribution
        """
        return cls.from_text(text, role=MessageRole.AGENT, agent_id=agent_id, **kwargs)

    def get_text_content(self) -> str:
        """Extract all text content from parts.
        
        Returns:
            Combined text from all text parts, space-separated
        """
        texts = []
        for part in self.parts:
            if part.type == PartType.TEXT and part.text:
                texts.append(part.text)
        return " ".join(texts)

    def get_files(self) -> list[Part]:
        """Get all file parts.
        
        Returns:
            List of parts with file type
        """
        return [part for part in self.parts if part.type == PartType.FILE]

    def add_part(self, part: Part) -> Message:
        """Add a part and return new message instance.
        
        Args:
            part: Part to add to the message
            
        Returns:
            New Message instance with the added part
        """
        new_parts = self.parts.copy()
        new_parts.append(part)
        
        return Message(
            message_id=self.message_id,
            role=self.role,
            parts=new_parts,
            timestamp=self.timestamp,
            agent_id=self.agent_id,
            session_id=self.session_id,
            metadata=self.metadata.copy(),
        )

    def has_content(self) -> bool:
        """Check if message has any meaningful content.
        
        Returns:
            True if message has parts with content
        """
        return bool(self.parts) and any(
            (part.type == PartType.TEXT and part.text and part.text.strip()) or
            (part.type == PartType.FILE and part.data)
            for part in self.parts
        )



class MessageRole(str, Enum):
    """Message role enumeration compatible with A2A standard."""
    USER = "user"      # Client/caller
    AGENT = "agent"    # Remote agent
    SYSTEM = "system"  # System-generated (CC extension)



__all__ = ['Message', 'MessageRole']