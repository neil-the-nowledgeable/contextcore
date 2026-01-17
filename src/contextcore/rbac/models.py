"""
Pydantic models for RBAC (Role-Based Access Control).

Provides permission-based access to ContextCore resources, with
special support for protecting sensitive knowledge capabilities.

Key concepts:
- Principal: Identity (agent or human) that can be granted permissions
- Resource: Protected entity (knowledge category, project, insight)
- Action: Operation that can be performed (read, write, query, emit)
- Permission: Grant of actions on a resource with optional conditions
- Role: Named collection of permissions
- RoleBinding: Assignment of role to principal within a scope
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PrincipalType(str, Enum):
    """Classification of principals (subjects) in the RBAC system."""
    AGENT = "agent"                      # AI agents (claude-code, o11y, dev-tour-guide)
    USER = "user"                        # Human individuals
    TEAM = "team"                        # Human teams/groups
    SERVICE_ACCOUNT = "service_account"  # K8s service accounts


class ResourceType(str, Enum):
    """Types of resources that can be protected."""
    KNOWLEDGE_CATEGORY = "knowledge_category"      # Maps to KnowledgeCategory
    KNOWLEDGE_CAPABILITY = "knowledge_capability"  # Specific capability
    PROJECT = "project"                            # ProjectContext access
    INSIGHT = "insight"                            # Agent insights
    HANDOFF = "handoff"                            # Agent handoffs
    GUIDANCE = "guidance"                          # Human guidance
    TASK = "task"                                  # Project tasks


class Action(str, Enum):
    """Actions that can be performed on resources."""
    READ = "read"           # View/get resource
    WRITE = "write"         # Create/update resource
    DELETE = "delete"       # Remove resource
    QUERY = "query"         # Search/list resources
    EMIT = "emit"           # Emit telemetry (insights, capabilities)
    DELEGATE = "delegate"   # Hand off to another agent


class PolicyDecision(str, Enum):
    """Result of policy evaluation."""
    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


class Principal(BaseModel):
    """
    Identity that can be granted permissions.

    Supports AI agents, human users, teams, and K8s service accounts.

    Example:
        agent_principal = Principal(
            id="claude-code",
            principal_type=PrincipalType.AGENT,
            display_name="Claude Code Assistant",
            agent_id="claude-code",
        )

        user_principal = Principal(
            id="alice@example.com",
            principal_type=PrincipalType.USER,
            display_name="Alice Developer",
            email="alice@example.com",
            groups=["developers", "security-team"],
        )
    """
    id: str = Field(..., description="Unique identifier")
    principal_type: PrincipalType = Field(..., description="Type of principal")
    display_name: str = Field(..., description="Human-readable name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional attributes")

    # Agent-specific fields
    agent_id: Optional[str] = Field(None, description="Maps to agent.id span attribute")
    session_id: Optional[str] = Field(None, description="Current session identifier")

    # Human-specific fields
    email: Optional[str] = Field(None, description="Email address for users")
    groups: List[str] = Field(default_factory=list, description="Group memberships (LDAP/OIDC)")

    # K8s-specific fields
    namespace: Optional[str] = Field(None, description="K8s namespace for service accounts")

    class Config:
        use_enum_values = True


class Resource(BaseModel):
    """
    A protected resource.

    Supports both category-level and instance-level control.

    Example:
        # Category-level: all security knowledge
        security_knowledge = Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
            sensitive=True,
            sensitivity_reason="Contains secrets management documentation",
        )

        # Instance-level: specific capability
        secrets_cap = Resource(
            resource_type=ResourceType.KNOWLEDGE_CAPABILITY,
            resource_id="secrets_management",
            project_scope="my-project",
        )
    """
    resource_type: ResourceType = Field(..., description="Type of resource")
    resource_id: str = Field(..., description="Resource identifier or '*' for all")
    project_scope: Optional[str] = Field(None, description="Limit to specific project")

    # Sensitivity marker
    sensitive: bool = Field(default=False, description="Requires elevated permissions")
    sensitivity_reason: Optional[str] = Field(None, description="Why this is sensitive")

    class Config:
        use_enum_values = True

    def matches(self, other: "Resource") -> bool:
        """Check if this resource matches another (for permission checking)."""
        # Type must match
        if self.resource_type != other.resource_type:
            return False

        # Wildcard matches everything
        if self.resource_id == "*":
            return True

        # Exact match
        if self.resource_id != other.resource_id:
            return False

        # Project scope check (None means all projects)
        if self.project_scope and other.project_scope:
            if self.project_scope != other.project_scope:
                return False

        return True


class Permission(BaseModel):
    """
    A specific permission grant.

    Combines resource, actions, and optional conditions.

    Example:
        read_public = Permission(
            id="read-public-knowledge",
            resource=Resource(
                resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                resource_id="*",
                sensitive=False,
            ),
            actions=[Action.READ, Action.QUERY],
        )
    """
    id: str = Field(..., description="Unique permission identifier")
    resource: Resource = Field(..., description="Resource this permission applies to")
    actions: List[Action] = Field(..., description="Allowed actions")
    conditions: Dict[str, Any] = Field(default_factory=dict, description="Optional conditions")

    # Time-based access
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")

    # Audit fields
    granted_by: Optional[str] = Field(None, description="Who granted this permission")
    granted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When permission was granted"
    )
    reason: Optional[str] = Field(None, description="Reason for granting")

    class Config:
        use_enum_values = True

    def is_expired(self) -> bool:
        """Check if permission has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def allows(self, action: Action, resource: Resource) -> bool:
        """Check if this permission allows the given action on resource."""
        if self.is_expired():
            return False

        if action not in self.actions:
            return False

        # Sensitivity check: if resource is sensitive, permission resource must also be sensitive-allowed
        if resource.sensitive and not self.resource.sensitive:
            return False

        return self.resource.matches(resource)


class Role(BaseModel):
    """
    Named collection of permissions.

    Roles can inherit from other roles for hierarchy.

    Example:
        reader_role = Role(
            id="reader",
            name="Reader",
            description="Read access to non-sensitive knowledge",
            permissions=[read_public_permission],
            built_in=True,
        )
    """
    id: str = Field(..., description="Unique role identifier")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="What this role provides")
    permissions: List[Permission] = Field(default_factory=list, description="Granted permissions")

    # Role hierarchy
    inherits_from: List[str] = Field(
        default_factory=list,
        description="Role IDs this role inherits from"
    )

    # Assignment restrictions
    assignable_to: List[PrincipalType] = Field(
        default_factory=lambda: list(PrincipalType),
        description="Principal types that can be assigned this role"
    )

    # Built-in flag (cannot be deleted/modified)
    built_in: bool = Field(default=False, description="System-defined role")

    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    class Config:
        use_enum_values = True


class RoleBinding(BaseModel):
    """
    Assignment of a role to a principal within a scope.

    Example:
        binding = RoleBinding(
            id="claude-code-reader",
            principal_id="claude-code",
            principal_type=PrincipalType.AGENT,
            role_id="reader",
            created_by="admin",
        )
    """
    id: str = Field(..., description="Unique binding identifier")
    principal_id: str = Field(..., description="Principal receiving the role")
    principal_type: PrincipalType = Field(..., description="Type of principal")
    role_id: str = Field(..., description="Role being assigned")

    # Scope limitation
    project_scope: Optional[str] = Field(None, description="Limit to project (None = all)")
    namespace_scope: Optional[str] = Field(None, description="K8s namespace scope")

    # Audit fields
    created_by: str = Field(..., description="Who created this binding")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")

    class Config:
        use_enum_values = True

    def is_expired(self) -> bool:
        """Check if binding has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


class AccessDecision(BaseModel):
    """
    Result of an access check.

    Includes audit information for logging and compliance.

    Example:
        decision = AccessDecision(
            decision=PolicyDecision.ALLOW,
            principal_id="claude-code",
            resource=security_resource,
            action=Action.READ,
            matched_role="security-reader",
        )
    """
    decision: PolicyDecision = Field(..., description="Allow/Deny/N/A")
    principal_id: str = Field(..., description="Who requested access")
    resource: Resource = Field(..., description="What they tried to access")
    action: Action = Field(..., description="What action they tried")

    # Decision details
    matched_role: Optional[str] = Field(None, description="Role that granted access")
    matched_permission: Optional[str] = Field(None, description="Permission that matched")
    denial_reason: Optional[str] = Field(None, description="Why access was denied")

    # Audit trail
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    trace_id: Optional[str] = Field(None, description="OTel trace ID for correlation")

    class Config:
        use_enum_values = True


class AccessDeniedError(Exception):
    """
    Raised when access is denied (hard enforcement).

    Contains the full AccessDecision for logging/debugging.
    """

    def __init__(self, decision: AccessDecision):
        self.decision = decision
        reason = decision.denial_reason or "Insufficient permissions"
        super().__init__(f"Access denied: {reason}")


# =============================================================================
# Built-in Roles
# =============================================================================

def _create_built_in_roles() -> List[Role]:
    """Create the built-in roles for the RBAC system."""

    # Reader: Non-sensitive knowledge access
    reader = Role(
        id="reader",
        name="Reader",
        description="Read access to non-sensitive knowledge",
        permissions=[
            Permission(
                id="read-public-knowledge",
                resource=Resource(
                    resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                    resource_id="*",
                    sensitive=False,
                ),
                actions=[Action.READ, Action.QUERY],
            ),
        ],
        built_in=True,
    )

    # Agent Standard: Default permissions for AI agents
    agent_standard = Role(
        id="agent-standard",
        name="Standard Agent",
        description="Default permissions for AI agents",
        permissions=[
            Permission(
                id="query-knowledge",
                resource=Resource(
                    resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                    resource_id="*",
                    sensitive=False,
                ),
                actions=[Action.READ, Action.QUERY],
            ),
            Permission(
                id="emit-insights",
                resource=Resource(
                    resource_type=ResourceType.INSIGHT,
                    resource_id="*",
                ),
                actions=[Action.EMIT, Action.READ],
            ),
            Permission(
                id="handoff",
                resource=Resource(
                    resource_type=ResourceType.HANDOFF,
                    resource_id="*",
                ),
                actions=[Action.READ, Action.DELEGATE],
            ),
        ],
        assignable_to=[PrincipalType.AGENT],
        built_in=True,
    )

    # Security Reader: Elevated access to security knowledge
    security_reader = Role(
        id="security-reader",
        name="Security Reader",
        description="Read access to security knowledge (elevated)",
        permissions=[
            Permission(
                id="read-security-knowledge",
                resource=Resource(
                    resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                    resource_id="security",
                    sensitive=True,
                    sensitivity_reason="Contains secrets and credential documentation",
                ),
                actions=[Action.READ, Action.QUERY],
            ),
        ],
        inherits_from=["reader"],
        built_in=True,
    )

    # Admin: Full access
    admin = Role(
        id="admin",
        name="Administrator",
        description="Full access to all resources",
        permissions=[
            Permission(
                id="full-access",
                resource=Resource(
                    resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                    resource_id="*",
                    sensitive=True,  # Can access sensitive too
                ),
                actions=list(Action),
            ),
            Permission(
                id="full-project-access",
                resource=Resource(
                    resource_type=ResourceType.PROJECT,
                    resource_id="*",
                ),
                actions=list(Action),
            ),
            Permission(
                id="full-insight-access",
                resource=Resource(
                    resource_type=ResourceType.INSIGHT,
                    resource_id="*",
                ),
                actions=list(Action),
            ),
            Permission(
                id="full-task-access",
                resource=Resource(
                    resource_type=ResourceType.TASK,
                    resource_id="*",
                ),
                actions=list(Action),
            ),
        ],
        assignable_to=[PrincipalType.USER, PrincipalType.SERVICE_ACCOUNT],
        built_in=True,
    )

    return [reader, agent_standard, security_reader, admin]


BUILT_IN_ROLES: List[Role] = _create_built_in_roles()
BUILT_IN_ROLE_IDS: set[str] = {r.id for r in BUILT_IN_ROLES}
