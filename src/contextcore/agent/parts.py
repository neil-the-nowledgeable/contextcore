"""A2A-compatible Message model for handoff communication."""

from .insight import Insight
from .part import Part
from .part import Part, PartType
from __future__ import annotations
from contextcore.agent.insights import Evidence
from contextcore.models import Message, Part
from dataclasses import dataclass, field
from datetime import datetime
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from typing import Any, Dict, Optional, TYPE_CHECKING
from typing import Any, TYPE_CHECKING
import uuid

Unified Part model supporting both A2A and ContextCore content types.
This module provides a single Part model that can represent:
- A2A content types (TextPart, FilePart, etc.)
- ContextCore observability types (trace references, log queries, etc.)
if TYPE_CHECKING:
text_part = Part.text("Hello world")
file_part = Part.file("s3://bucket/file.pdf", "application/pdf", "document.pdf")
trace_part = Part.trace("trace-123", "User login flow")
log_part = Part.log_query('level="error" | count by service', "Error count by service")
commit_part = Part.commit("abc123", "Fix authentication bug", "https://github.com/repo/commit/abc123")
adr_part = Part.adr("ADR-001", "Use PostgreSQL for primary database")
a2a_dict = part.to_a2a_dict()  # Convert to A2A format
full_dict = part.to_dict()     # Full serialization
evidence = part.to_evidence()  # Legacy Evidence format
A2A-compatible Artifact model for handoff outputs with ContextCore extensions.
This module provides the Artifact class that represents outputs generated during
handoff execution, with full compatibility with the A2A (Agent-to-Agent) protocol
and additional ContextCore features for OpenTelemetry integration.
if TYPE_CHECKING:
ContextCore Data Models
This package provides A2A-compatible data models with ContextCore extensions.
Core Models:
- Part: Unified content unit (replaces Evidence)
- Message: Communication with role and parts
- Artifact: Generated outputs
Migration from Evidence to Part:
msg = Message.from_text("Hello", role=MessageRole.USER)
a2a_dict = msg.to_a2a_dict()  # A2A-compatible format

class Artifact:
    """A2A-compatible artifact with ContextCore extensions for handoff outputs.
    
    Represents structured outputs from agent handoffs, supporting both simple
    single-part artifacts and complex multi-part streaming scenarios.
    
    A2A Core Fields:
        artifact_id: Unique identifier for the artifact
        parts: List of content parts (text, json, files, etc.)
        media_type: MIME type of the primary content
        index: Sequence number for streaming chunks
        append: Whether this chunk should be appended to previous
        last_chunk: Whether this is the final chunk in a stream
        
    ContextCore Extensions:
        trace_id: OpenTelemetry trace identifier for correlation
        name: Human-readable artifact name
        description: Detailed description of the artifact
        metadata: Additional key-value metadata
        created_at: UTC timestamp of creation
    """
    
    # Core A2A fields - maintain exact compatibility
    artifact_id: str | None = None
    parts: list[Part] = field(default_factory=list)
    media_type: str = "application/json"
    index: int = 0
    append: bool = False
    last_chunk: bool = True
    
    # ContextCore extensions for enhanced functionality
    trace_id: str | None = None  # Link to OTel trace for correlation
    name: str | None = None  # Human-readable identifier
    description: str | None = None  # Detailed description
    metadata: dict[str, Any] = field(default_factory=dict)  # Extensible metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Post-initialization validation and auto-generation."""
        # Generate artifact_id if not provided
        if self.artifact_id is None:
            self.artifact_id = f"artifact-{uuid.uuid4().hex[:12]}"

    def to_a2a_dict(self) -> dict:
        """Convert to A2A Artifact format, excluding ContextCore extensions.
        
        Returns a dictionary that conforms exactly to the A2A specification
        for maximum interoperability with other A2A-compatible systems.
        """
        return {
            "artifactId": self.artifact_id,
            "parts": [part.to_a2a_dict() for part in self.parts],
            "mediaType": self.media_type,
            "index": self.index,
            "append": self.append,
            "lastChunk": self.last_chunk,
        }

    def to_dict(self) -> dict:
        """Convert to full dictionary with ContextCore extensions included.
        
        Includes all fields for complete serialization, useful for internal
        storage and debugging scenarios.
        """
        return {
            "artifact_id": self.artifact_id,
            "parts": [part.to_a2a_dict() for part in self.parts],
            "media_type": self.media_type,
            "index": self.index,
            "append": self.append,
            "last_chunk": self.last_chunk,
            "trace_id": self.trace_id,
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_a2a_dict(cls, data: dict) -> Artifact:
        """Parse artifact from A2A format dictionary.
        
        Creates an Artifact instance from a dictionary that conforms to the
        A2A specification. ContextCore extensions will use default values.
        
        Args:
            data: Dictionary containing A2A artifact fields
            
        Returns:
            New Artifact instance
            
        Raises:
            ValueError: If required A2A fields are missing or invalid
        """
        try:
            parts_data = data.get("parts", [])
            parts = [Part.from_a2a_dict(part) for part in parts_data]
            
            return cls(
                artifact_id=data.get("artifactId"),
                parts=parts,
                media_type=data.get("mediaType", "application/json"),
                index=data.get("index", 0),
                append=data.get("append", False),
                last_chunk=data.get("lastChunk", True),
            )
        except Exception as e:
            raise ValueError(f"Invalid A2A artifact data: {e}") from e

    def is_complete(self) -> bool:
        """Check if artifact represents a complete, non-streaming entity.
        
        Returns True for complete artifacts or final chunks in a stream.
        Returns False for intermediate streaming chunks.
        """
        return self.last_chunk and not self.append

    @classmethod
    def from_json(cls, data: dict, artifact_id: str = None, name: str = None) -> Artifact:
        """Create artifact from JSON data dictionary.
        
        Convenience factory for creating artifacts from structured data.
        The entire dictionary becomes a single JSON part.
        
        Args:
            data: JSON-serializable dictionary
            artifact_id: Optional custom artifact ID
            name: Optional human-readable name
        """
        json_part = Part.json_data(data)
        return cls(
            artifact_id=artifact_id,
            parts=[json_part],
            media_type="application/json",
            name=name,
        )

    @classmethod
    def from_text(cls, text: str, artifact_id: str = None, name: str = None) -> Artifact:
        """Create artifact from plain text content.
        
        Convenience factory for text-based artifacts like summaries or logs.
        
        Args:
            text: Text content
            artifact_id: Optional custom artifact ID
            name: Optional human-readable name
        """
        text_part = Part.text(text)
        return cls(
            artifact_id=artifact_id,
            parts=[text_part],
            media_type="text/plain",
            name=name,
        )

    @classmethod
    def from_file(cls, uri: str, mime_type: str, artifact_id: str = None, name: str = None) -> Artifact:
        """Create artifact from file reference.
        
        Creates an artifact that references an external file resource.
        
        Args:
            uri: File URI or path
            mime_type: MIME type of the file
            artifact_id: Optional custom artifact ID
            name: Optional human-readable name
        """
        file_part = Part.file(uri, mime_type)
        return cls(
            artifact_id=artifact_id,
            parts=[file_part],
            media_type=mime_type,
            name=name,
        )

    @classmethod
    def from_insight(cls, insight: Insight) -> Artifact:
        """Create artifact from an Insight instance.
        
        Converts ContextCore Insights into artifacts for handoff scenarios,
        preserving trace correlation and key insight data.
        
        Args:
            insight: Insight instance to convert
        """
        # Extract key insight data into structured JSON
        insight_data = {
            "id": insight.id,
            "type": insight.type.value,
            "summary": insight.summary,
            "confidence": insight.confidence,
        }
        
        json_part = Part.json_data(insight_data)
        return cls(
            artifact_id=f"insight-{insight.id}",
            parts=[json_part],
            media_type="application/json",
            name=f"Insight: {insight.summary[:50]}{'...' if len(insight.summary) > 50 else ''}",
            trace_id=insight.trace_id,
        )

    @classmethod
    def create_chunk(
        cls,
        artifact_id: str,
        parts: list[Part],
        index: int,
        is_last: bool,
    ) -> Artifact:
        """Create a streaming chunk for large artifact delivery.
        
        Used in streaming scenarios where large artifacts are delivered
        in multiple chunks to avoid memory issues or timeouts.
        
        Args:
            artifact_id: Shared ID across all chunks
            parts: Content parts for this chunk
            index: Sequence number of this chunk
            is_last: Whether this is the final chunk
        """
        return cls(
            artifact_id=artifact_id,
            parts=parts,
            index=index,
            append=True,  # Streaming chunks are always appended
            last_chunk=is_last,
        )


# Export list for clean module interface

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



class Part:
    """Unified content part (A2A-compatible with ContextCore extensions)."""
    
    type: PartType

    # Text content (TEXT type)
    text: Optional[str] = None

    # File content (FILE type)
    file_uri: Optional[str] = None
    mime_type: Optional[str] = None
    file_name: Optional[str] = None

    # Structured data (DATA, JSON, FORM types)
    data: Optional[Dict[str, Any]] = None

    # ContextCore observability (TRACE, SPAN, LOG_QUERY, METRIC_QUERY)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    query: Optional[str] = None  # TraceQL, LogQL, PromQL

    # Reference (COMMIT, PR, ADR, DOC, CAPABILITY, INSIGHT, TASK)
    ref: Optional[str] = None
    ref_url: Optional[str] = None
    description: Optional[str] = None

    # Token budget (ContextCore extension)
    tokens: Optional[int] = None

    # Timestamp
    timestamp: Optional[datetime] = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate that required fields are present for the part type."""
        self._validate()

    def _validate(self):
        """Validate that required fields are present for the part type."""
        validations = {
            PartType.TEXT: lambda: self.text is not None,
            PartType.FILE: lambda: self.file_uri is not None and self.mime_type is not None,
            PartType.DATA: lambda: self.data is not None,
            PartType.JSON: lambda: self.data is not None,
            PartType.FORM: lambda: self.data is not None,
            PartType.TRACE: lambda: self.trace_id is not None,
            PartType.SPAN: lambda: self.span_id is not None,
            PartType.LOG_QUERY: lambda: self.query is not None,
            PartType.METRIC_QUERY: lambda: self.query is not None,
            PartType.COMMIT: lambda: self.ref is not None,
            PartType.PR: lambda: self.ref is not None,
            PartType.ADR: lambda: self.ref is not None,
            PartType.DOC: lambda: self.ref is not None,
            PartType.CAPABILITY: lambda: self.ref is not None,
            PartType.INSIGHT: lambda: self.ref is not None,
            PartType.TASK: lambda: self.ref is not None,
        }
        
        validator = validations.get(self.type)
        if validator and not validator():
            raise ValueError(f"{self.type.value} type missing required fields")

    def to_a2a_dict(self) -> Dict[str, Any]:
        """Convert to A2A Part format (only A2A-compatible fields)."""
        if self.type == PartType.TEXT:
            return {"text": self.text}
        
        elif self.type == PartType.FILE:
            result = {"fileUri": self.file_uri, "mimeType": self.mime_type}
            if self.file_name:
                result["fileName"] = self.file_name
            return result
        
        elif self.type in (PartType.DATA, PartType.JSON, PartType.FORM):
            return {"json" if self.type == PartType.JSON else "data": self.data}
        
        elif self.type == PartType.IFRAME:
            return {"data": self.data} if self.data else {}
        
        elif self.type in (PartType.VIDEO, PartType.AUDIO):
            result = {}
            if self.file_uri:
                result["fileUri"] = self.file_uri
            if self.mime_type:
                result["mimeType"] = self.mime_type
            return result
        
        elif self.type == PartType.ACTION:
            return {"data": self.data} if self.data else {}
        
        else:
            # ContextCore extension types - represent as data
            return {"json": self.to_dict()}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to full dict representation."""
        result = {"type": self.type.value}
        
        # Add non-None fields
        for field_name, value in self.__dict__.items():
            if value is not None and field_name != "type":
                # Convert datetime to ISO format for serialization
                if isinstance(value, datetime):
                    result[field_name] = value.isoformat()
                else:
                    result[field_name] = value
        
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Part":
        """Parse from dict (handles both A2A and CC formats)."""
        # Convert string timestamp back to datetime if present
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data = data.copy()
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        
        # Ensure type is a PartType enum
        if "type" in data:
            data = data.copy()
            data["type"] = PartType(data["type"])
        
        return cls(**data)

    @classmethod
    def from_a2a_dict(cls, data: Dict[str, Any]) -> "Part":
        """Parse from A2A Part format."""
        if "text" in data:
            return cls(type=PartType.TEXT, text=data["text"])
        
        elif "fileUri" in data:
            return cls(
                type=PartType.FILE,
                file_uri=data["fileUri"],
                mime_type=data["mimeType"],
                file_name=data.get("fileName")
            )
        
        elif "json" in data:
            return cls(type=PartType.JSON, data=data["json"])
        
        elif "data" in data:
            return cls(type=PartType.DATA, data=data["data"])
        
        else:
            raise ValueError(f"Unsupported A2A format: {data}")

    def _type_to_evidence_type(self) -> str:
        """Convert Part type to Evidence type string."""
        # Map ContextCore types to evidence types
        mapping = {
            PartType.TRACE: "trace",
            PartType.SPAN: "span", 
            PartType.LOG_QUERY: "log_query",
            PartType.METRIC_QUERY: "metric_query",
            PartType.COMMIT: "commit",
            PartType.PR: "pr",
            PartType.ADR: "adr",
            PartType.DOC: "doc",
            PartType.FILE: "file",
            PartType.CAPABILITY: "capability",
            PartType.INSIGHT: "insight",
            PartType.TASK: "task",
        }
        return mapping.get(self.type, self.type.value)

    def to_evidence(self) -> "Evidence":
        """Convert to legacy Evidence format for backward compatibility."""
        return Evidence(
            type=self._type_to_evidence_type(),
            ref=self.ref or self.trace_id or self.file_uri or "",
            description=self.description,
            query=self.query,
            timestamp=self.timestamp,
        )

    @classmethod
    def from_evidence(cls, evidence: "Evidence") -> "Part":
        """Create Part from legacy Evidence."""
        # Determine part type from evidence type
        part_type = PartType(evidence.type)
        
        kwargs = {
            "type": part_type,
            "description": evidence.description,
            "query": evidence.query,
            "timestamp": evidence.timestamp,
        }
        
        # Set appropriate reference field based on type
        if part_type in (PartType.TRACE, PartType.SPAN):
            kwargs["trace_id"] = evidence.ref
        elif part_type == PartType.FILE:
            kwargs["file_uri"] = evidence.ref
        else:
            kwargs["ref"] = evidence.ref
        
        return cls(**kwargs)

    # Factory methods for A2A types
    @classmethod
    def text(cls, text: str) -> "Part":
        """Create a text part."""
        return cls(type=PartType.TEXT, text=text)

    @classmethod
    def file(cls, uri: str, mime_type: str, name: Optional[str] = None) -> "Part":
        """Create a file part."""
        return cls(type=PartType.FILE, file_uri=uri, mime_type=mime_type, file_name=name)

    @classmethod
    def json_data(cls, data: Dict[str, Any]) -> "Part":
        """Create a JSON data part."""
        return cls(type=PartType.JSON, data=data)

    @classmethod
    def data_part(cls, data: Dict[str, Any]) -> "Part":
        """Create a data part."""
        return cls(type=PartType.DATA, data=data)

    @classmethod
    def form_part(cls, data: Dict[str, Any]) -> "Part":
        """Create a form part."""
        return cls(type=PartType.FORM, data=data)

    # Factory methods for ContextCore observability types
    @classmethod
    def trace(cls, trace_id: str, description: Optional[str] = None) -> "Part":
        """Create a trace reference part."""
        return cls(type=PartType.TRACE, trace_id=trace_id, description=description)

    @classmethod
    def span(cls, span_id: str, trace_id: Optional[str] = None, description: Optional[str] = None) -> "Part":
        """Create a span reference part."""
        return cls(type=PartType.SPAN, span_id=span_id, trace_id=trace_id, description=description)

    @classmethod
    def log_query(cls, query: str, description: Optional[str] = None) -> "Part":
        """Create a log query part."""
        return cls(type=PartType.LOG_QUERY, query=query, description=description)

    @classmethod
    def metric_query(cls, query: str, description: Optional[str] = None) -> "Part":
        """Create a metric query part."""
        return cls(type=PartType.METRIC_QUERY, query=query, description=description)

    # Factory methods for ContextCore artifact types
    @classmethod
    def commit(cls, sha: str, description: Optional[str] = None, url: Optional[str] = None) -> "Part":
        """Create a commit reference part."""
        return cls(type=PartType.COMMIT, ref=sha, description=description, ref_url=url)

    @classmethod
    def pr(cls, pr_number: str, description: Optional[str] = None, url: Optional[str] = None) -> "Part":
        """Create a pull request reference part."""
        return cls(type=PartType.PR, ref=pr_number, description=description, ref_url=url)

    @classmethod
    def adr(cls, ref: str, description: Optional[str] = None, url: Optional[str] = None) -> "Part":
        """Create an ADR reference part."""
        return cls(type=PartType.ADR, ref=ref, description=description, ref_url=url)

    @classmethod
    def doc(cls, ref: str, description: Optional[str] = None, url: Optional[str] = None) -> "Part":
        """Create a document reference part."""
        return cls(type=PartType.DOC, ref=ref, description=description, ref_url=url)

    @classmethod
    def capability(cls, ref: str, description: Optional[str] = None, url: Optional[str] = None) -> "Part":
        """Create a capability reference part."""
        return cls(type=PartType.CAPABILITY, ref=ref, description=description, ref_url=url)

    @classmethod
    def insight(cls, ref: str, description: Optional[str] = None, url: Optional[str] = None) -> "Part":
        """Create an insight reference part."""
        return cls(type=PartType.INSIGHT, ref=ref, description=description, ref_url=url)

    @classmethod
    def task(cls, ref: str, description: Optional[str] = None, url: Optional[str] = None) -> "Part":
        """Create a task reference part."""
        return cls(type=PartType.TASK, ref=ref, description=description, ref_url=url)



class PartType(str, Enum):
    """Enum for all supported part types."""
    # A2A-compatible types
    TEXT = "text"
    FILE = "file"
    DATA = "data"
    JSON = "json"
    FORM = "form"
    IFRAME = "iframe"
    VIDEO = "video"
    AUDIO = "audio"
    ACTION = "action"
    
    # ContextCore observability types
    TRACE = "trace"
    SPAN = "span"
    LOG_QUERY = "log_query"
    METRIC_QUERY = "metric_query"
    
    # ContextCore artifact types
    COMMIT = "commit"
    PR = "pr"
    ADR = "adr"
    DOC = "doc"
    CAPABILITY = "capability"
    INSIGHT = "insight"
    TASK = "task"



__all__ = ['Artifact', 'Message', 'MessageRole', 'Part', 'PartType']