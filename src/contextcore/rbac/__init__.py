"""
ContextCore RBAC Module.

Role-Based Access Control for ContextCore Tour Guide, enabling
permission-based access to knowledge capabilities with elevated
roles for sensitive sections.

Example usage:
    from contextcore.rbac import (
        RBACEnforcer,
        PrincipalResolver,
        Resource,
        ResourceType,
        Action,
        AccessDeniedError,
    )

    # Get enforcer
    enforcer = RBACEnforcer()

    # Resolve principal from context
    principal = PrincipalResolver.from_cli_context()

    # Check access
    resource = Resource(
        resource_type=ResourceType.KNOWLEDGE_CATEGORY,
        resource_id="security",
        sensitive=True,
    )

    try:
        enforcer.require_access(
            principal.id,
            principal.principal_type,
            resource,
            Action.READ,
        )
    except AccessDeniedError as e:
        print(f"Access denied: {e.decision.denial_reason}")

CLI usage:
    # Grant a role
    contextcore rbac grant -p claude-code --principal-type agent -r reader

    # Check access
    contextcore rbac check -p claude-code -r knowledge_category/security -a read

    # List roles
    contextcore rbac list-roles

    # View audit trail
    contextcore rbac audit --principal claude-code --time-range 24h
"""

from contextcore.rbac.models import (
    # Enums
    PrincipalType,
    ResourceType,
    Action,
    PolicyDecision,
    # Models
    Principal,
    Resource,
    Permission,
    Role,
    RoleBinding,
    AccessDecision,
    AccessDeniedError,
    # Built-in roles
    BUILT_IN_ROLES,
    BUILT_IN_ROLE_IDS,
)

from contextcore.rbac.store import (
    BaseRBACStore,
    RBACFileStore,
    RBACMemoryStore,
    get_rbac_store,
    set_rbac_store,
    reset_rbac_store,
)

from contextcore.rbac.enforcer import (
    RBACEnforcer,
    PrincipalResolver,
    get_enforcer,
    set_enforcer,
    reset_enforcer,
)

from contextcore.rbac.decorators import (
    require_permission,
    require_permission_dynamic,
    with_rbac_filter,
    RBACContext,
)

from contextcore.rbac.audit import (
    RBACAuditEmitter,
    AuditingEnforcer,
    get_auditing_enforcer,
)

from contextcore.rbac.k8s_sync import (
    K8sRBACSync,
    HybridRBACStore,
    detect_kubernetes,
    get_current_namespace,
    DEFAULT_K8S_ROLE_MAPPING,
)

__all__ = [
    # Enums
    "PrincipalType",
    "ResourceType",
    "Action",
    "PolicyDecision",
    # Models
    "Principal",
    "Resource",
    "Permission",
    "Role",
    "RoleBinding",
    "AccessDecision",
    "AccessDeniedError",
    # Built-in
    "BUILT_IN_ROLES",
    "BUILT_IN_ROLE_IDS",
    # Store
    "BaseRBACStore",
    "RBACFileStore",
    "RBACMemoryStore",
    "get_rbac_store",
    "set_rbac_store",
    "reset_rbac_store",
    # Enforcer
    "RBACEnforcer",
    "PrincipalResolver",
    "get_enforcer",
    "set_enforcer",
    "reset_enforcer",
    # Decorators
    "require_permission",
    "require_permission_dynamic",
    "with_rbac_filter",
    "RBACContext",
    # Audit
    "RBACAuditEmitter",
    "AuditingEnforcer",
    "get_auditing_enforcer",
    # K8s
    "K8sRBACSync",
    "HybridRBACStore",
    "detect_kubernetes",
    "get_current_namespace",
    "DEFAULT_K8S_ROLE_MAPPING",
]
