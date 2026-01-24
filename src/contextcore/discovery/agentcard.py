"""
AgentCard model compatible with A2A specification plus ContextCore extensions.

This module provides data models for agent self-description that are compatible
with A2A's AgentCard specification while adding ContextCore-specific extensions
for OpenTelemetry discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
import re

if TYPE_CHECKING:
    from contextcore.skills.manifest import SkillManifest

__all__ = [
    "AuthScheme",
    "AgentCapabilities", 
    "SkillDescriptor",
    "AuthConfig",
    "ProviderInfo",
    "AgentCard"
]


class AuthScheme(str, Enum):
    """Authentication schemes supported by agents."""
    BEARER = "Bearer"
    BASIC = "Basic"
    API_KEY = "ApiKey"
    OAUTH2 = "OAuth2"
    NONE = "None"


@dataclass
class AgentCapabilities:
    """
    Agent capabilities following A2A specification with ContextCore extensions.
    
    A2A standard capabilities default to False, ContextCore extensions default to True.
    """
    # A2A standard capabilities
    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = False
    
    # ContextCore extensions
    insights: bool = True
    handoffs: bool = True
    skills: bool = True
    otel_native: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "streaming": self.streaming,
            "push_notifications": self.push_notifications,
            "state_transition_history": self.state_transition_history,
            "insights": self.insights,
            "handoffs": self.handoffs,
            "skills": self.skills,
            "otel_native": self.otel_native
        }

    def to_a2a_dict(self) -> dict:
        """Convert to A2A-compatible dictionary (excludes ContextCore extensions)."""
        return {
            "streaming": self.streaming,
            "push_notifications": self.push_notifications,
            "state_transition_history": self.state_transition_history
        }


@dataclass
class SkillDescriptor:
    """A2A-compatible skill definition."""
    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=lambda: ["application/json"])
    output_modes: list[str] = field(default_factory=lambda: ["application/json"])

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "examples": self.examples,
            "input_modes": self.input_modes,
            "output_modes": self.output_modes
        }


@dataclass
class AuthConfig:
    """Authentication configuration for agents."""
    schemes: list[AuthScheme] = field(default_factory=list)
    credentials_url: str | None = None
    oauth2_config: dict | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        result = {
            "schemes": [scheme.value for scheme in self.schemes]
        }
        if self.credentials_url:
            result["credentials_url"] = self.credentials_url
        if self.oauth2_config:
            result["oauth2_config"] = self.oauth2_config
        return result

    @classmethod
    def from_dict(cls, data: dict) -> AuthConfig:
        """Create AuthConfig from dictionary."""
        schemes = [AuthScheme(scheme) for scheme in data.get("schemes", [])]
        return cls(
            schemes=schemes,
            credentials_url=data.get("credentials_url"),
            oauth2_config=data.get("oauth2_config")
        )


@dataclass
class ProviderInfo:
    """Information about the agent provider."""
    organization: str
    url: str | None = None
    contact: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        result = {"organization": self.organization}
        if self.url:
            result["url"] = self.url
        if self.contact:
            result["contact"] = self.contact
        return result

    @classmethod
    def from_dict(cls, data: dict) -> ProviderInfo:
        """Create ProviderInfo from dictionary."""
        return cls(
            organization=data["organization"],
            url=data.get("url"),
            contact=data.get("contact")
        )


@dataclass
class AgentCard:
    """
    Agent self-description compatible with A2A specification plus ContextCore extensions.
    
    Example:
        >>> card = AgentCard(
        ...     agent_id="my-agent",
        ...     name="My Agent",
        ...     description="A helpful agent",
        ...     url="https://api.example.com/agents/my-agent",
        ...     version="1.0.0"
        ... )
        >>> json_data = card.to_contextcore_json()
    """
    # A2A required fields
    agent_id: str
    name: str
    description: str
    url: str
    version: str
    capabilities: AgentCapabilities = field(default_factory=AgentCapabilities)
    skills: list[SkillDescriptor] = field(default_factory=list)
    
    # A2A optional fields
    authentication: AuthConfig | None = None
    default_input_modes: list[str] = field(default_factory=lambda: ["application/json", "text/plain"])
    default_output_modes: list[str] = field(default_factory=lambda: ["application/json", "text/plain"])
    documentation_url: str | None = None
    provider: ProviderInfo | None = None
    
    # ContextCore extensions
    tempo_url: str | None = None
    traceql_prefix: str | None = None
    project_refs: list[str] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_a2a_json(self) -> dict:
        """
        Export as A2A-compatible JSON (excludes ContextCore extensions).
        
        Returns:
            dict: A2A-compatible agent card representation
        """
        result = {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "capabilities": self.capabilities.to_a2a_dict(),
            "skills": [skill.to_dict() for skill in self.skills],
            "default_input_modes": self.default_input_modes,
            "default_output_modes": self.default_output_modes
        }
        
        # Add optional fields only if they exist
        if self.authentication:
            result["authentication"] = self.authentication.to_dict()
        if self.documentation_url:
            result["documentation_url"] = self.documentation_url
        if self.provider:
            result["provider"] = self.provider.to_dict()
            
        return result

    def to_contextcore_json(self) -> dict:
        """
        Export with ContextCore extensions.
        
        Returns:
            dict: Full agent card representation including ContextCore extensions
        """
        result = {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "capabilities": self.capabilities.to_dict(),
            "skills": [skill.to_dict() for skill in self.skills],
            "default_input_modes": self.default_input_modes,
            "default_output_modes": self.default_output_modes,
            "project_refs": self.project_refs,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
        
        # Add optional fields only if they exist
        if self.authentication:
            result["authentication"] = self.authentication.to_dict()
        if self.documentation_url:
            result["documentation_url"] = self.documentation_url
        if self.provider:
            result["provider"] = self.provider.to_dict()
        if self.tempo_url:
            result["tempo_url"] = self.tempo_url
        if self.traceql_prefix:
            result["traceql_prefix"] = self.traceql_prefix
            
        return result

    @classmethod
    def from_json(cls, data: dict) -> AgentCard:
        """
        Parse from JSON (handles both A2A and ContextCore formats).
        
        Args:
            data: Dictionary containing agent card data
            
        Returns:
            AgentCard: Parsed agent card instance
        """
        # Parse capabilities
        caps_data = data.get("capabilities", {})
        capabilities = AgentCapabilities(
            streaming=caps_data.get("streaming", False),
            push_notifications=caps_data.get("push_notifications", False),
            state_transition_history=caps_data.get("state_transition_history", False),
            insights=caps_data.get("insights", True),
            handoffs=caps_data.get("handoffs", True),
            skills=caps_data.get("skills", True),
            otel_native=caps_data.get("otel_native", True)
        )
        
        # Parse skills
        skills = []
        for skill_data in data.get("skills", []):
            skills.append(SkillDescriptor(
                id=skill_data["id"],
                name=skill_data["name"],
                description=skill_data["description"],
                tags=skill_data.get("tags", []),
                examples=skill_data.get("examples", []),
                input_modes=skill_data.get("input_modes", ["application/json"]),
                output_modes=skill_data.get("output_modes", ["application/json"])
            ))
        
        # Parse optional fields
        authentication = None
        if "authentication" in data:
            authentication = AuthConfig.from_dict(data["authentication"])
            
        provider = None
        if "provider" in data:
            provider = ProviderInfo.from_dict(data["provider"])
        
        # Parse timestamps
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)
        
        if "created_at" in data:
            created_at = datetime.fromisoformat(data["created_at"].replace('Z', '+00:00'))
        if "updated_at" in data:
            updated_at = datetime.fromisoformat(data["updated_at"].replace('Z', '+00:00'))
        
        return cls(
            agent_id=data["agent_id"],
            name=data["name"],
            description=data["description"],
            url=data["url"],
            version=data["version"],
            capabilities=capabilities,
            skills=skills,
            authentication=authentication,
            default_input_modes=data.get("default_input_modes", ["application/json", "text/plain"]),
            default_output_modes=data.get("default_output_modes", ["application/json", "text/plain"]),
            documentation_url=data.get("documentation_url"),
            provider=provider,
            tempo_url=data.get("tempo_url"),
            traceql_prefix=data.get("traceql_prefix"),
            project_refs=data.get("project_refs", []),
            created_at=created_at,
            updated_at=updated_at
        )

    @classmethod
    def from_skill_manifest(cls, manifest: SkillManifest, agent_id: str, url: str) -> AgentCard:
        """
        Create AgentCard from existing SkillManifest.
        
        Args:
            manifest: SkillManifest to convert
            agent_id: Unique identifier for the agent
            url: Base URL for the agent
            
        Returns:
            AgentCard: New agent card instance
        """
        # Convert manifest skills to SkillDescriptor objects
        skills = []
        for skill in manifest.skills:
            skills.append(SkillDescriptor(
                id=skill.get("id", skill["name"].lower().replace(" ", "_")),
                name=skill["name"],
                description=skill.get("description", ""),
                tags=skill.get("tags", []),
                examples=skill.get("examples", []),
                input_modes=skill.get("input_modes", ["application/json"]),
                output_modes=skill.get("output_modes", ["application/json"])
            ))
        
        return cls(
            agent_id=agent_id,
            name=manifest.name,
            description=manifest.description,
            url=url,
            version=manifest.version,
            skills=skills,
            documentation_url=manifest.metadata.get("documentation_url") if manifest.metadata else None
        )

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL format.
        
        Args:
            url: URL to validate
            
        Returns:
            bool: True if URL is valid, False otherwise
        """
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None