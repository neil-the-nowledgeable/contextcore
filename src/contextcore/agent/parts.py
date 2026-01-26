"""
Unified Part model supporting both A2A and ContextCore content types.

This module provides a single Part model that can represent:
- A2A content types (TextPart, FilePart, etc.)
- ContextCore observability types (trace references, log queries, etc.)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from contextcore.agent.insights import Evidence


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


@dataclass
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
        from contextcore.agent.insights import Evidence
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


__all__ = ["Part", "PartType"]
