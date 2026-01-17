"""
RBAC Enforcer.

Evaluates access decisions and enforces permissions.
Hard enforcement: raises AccessDeniedError on denial.

Example:
    enforcer = RBACEnforcer()

    # Check access (returns decision)
    decision = enforcer.check_access(
        principal_id="claude-code",
        principal_type=PrincipalType.AGENT,
        resource=Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id="security",
            sensitive=True,
        ),
        action=Action.READ,
    )

    # Require access (raises on denial)
    enforcer.require_access(
        principal_id="claude-code",
        principal_type=PrincipalType.AGENT,
        resource=security_resource,
        action=Action.READ,
    )
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from contextcore.rbac.models import (
    AccessDecision,
    AccessDeniedError,
    Action,
    Permission,
    PolicyDecision,
    Principal,
    PrincipalType,
    Resource,
    ResourceType,
    Role,
)
from contextcore.rbac.store import BaseRBACStore, get_rbac_store

logger = logging.getLogger(__name__)


class PrincipalResolver:
    """
    Resolves principal identity from various contexts.

    Supports:
    - Agent identity from spans (agent_id, session_id)
    - Human identity from CLI/environment
    - K8s service account identity
    """

    @classmethod
    def from_agent_context(
        cls,
        agent_id: str,
        session_id: Optional[str] = None,
    ) -> Principal:
        """Resolve from existing agent span attributes."""
        return Principal(
            id=agent_id,
            principal_type=PrincipalType.AGENT,
            display_name=agent_id,
            agent_id=agent_id,
            session_id=session_id,
        )

    @classmethod
    def from_cli_context(cls) -> Principal:
        """
        Resolve from CLI environment.

        Priority:
        1. CONTEXTCORE_USER env var
        2. CONTEXTCORE_AGENT_ID env var (for agent mode)
        3. USER env var
        4. "anonymous"
        """
        # Check for explicit agent mode
        agent_id = os.environ.get("CONTEXTCORE_AGENT_ID")
        if agent_id:
            return Principal(
                id=agent_id,
                principal_type=PrincipalType.AGENT,
                display_name=agent_id,
                agent_id=agent_id,
            )

        # Human user
        user = os.environ.get("CONTEXTCORE_USER") or os.environ.get("USER", "anonymous")
        return Principal(
            id=user,
            principal_type=PrincipalType.USER,
            display_name=user,
        )

    @classmethod
    def from_service_account(
        cls,
        name: str,
        namespace: str = "default",
    ) -> Principal:
        """Resolve from K8s service account."""
        sa_id = f"{namespace}:{name}"
        return Principal(
            id=sa_id,
            principal_type=PrincipalType.SERVICE_ACCOUNT,
            display_name=f"ServiceAccount/{namespace}/{name}",
            namespace=namespace,
        )


class RBACEnforcer:
    """
    Evaluates access decisions and enforces permissions.

    Features:
    - Permission caching for performance
    - Role hierarchy resolution
    - Sensitive resource protection
    - Audit-ready decisions
    """

    def __init__(
        self,
        store: Optional[BaseRBACStore] = None,
        cache_ttl_seconds: int = 300,
    ):
        self.store = store or get_rbac_store()
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: Dict[str, Tuple[datetime, List[Role]]] = {}

    def _get_cached_roles(
        self,
        principal_id: str,
        principal_type: PrincipalType,
        project_scope: Optional[str] = None,
    ) -> List[Role]:
        """Get roles for principal with caching."""
        # Handle both enum and string values for principal_type
        pt_value = principal_type.value if hasattr(principal_type, 'value') else principal_type
        cache_key = f"{principal_id}:{pt_value}:{project_scope or '*'}"

        # Check cache
        if cache_key in self._cache:
            cached_time, roles = self._cache[cache_key]
            if datetime.now(timezone.utc) - cached_time < self.cache_ttl:
                return roles

        # Fetch from store
        roles = self.store.get_roles_for_principal(
            principal_id, principal_type, project_scope
        )

        # Update cache
        self._cache[cache_key] = (datetime.now(timezone.utc), roles)

        return roles

    def clear_cache(self) -> None:
        """Clear the role cache."""
        self._cache.clear()

    def check_access(
        self,
        principal_id: str,
        principal_type: PrincipalType,
        resource: Resource,
        action: Action,
        project_scope: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AccessDecision:
        """
        Check if principal can perform action on resource.

        Returns AccessDecision with full audit trail.
        Does NOT raise exceptions - use require_access for enforcement.
        """
        # Get roles for this principal
        roles = self._get_cached_roles(principal_id, principal_type, project_scope)

        if not roles:
            return AccessDecision(
                decision=PolicyDecision.DENY,
                principal_id=principal_id,
                resource=resource,
                action=action,
                denial_reason="No roles assigned to principal",
            )

        # Check each role's permissions
        for role in roles:
            for permission in role.permissions:
                if permission.allows(action, resource):
                    return AccessDecision(
                        decision=PolicyDecision.ALLOW,
                        principal_id=principal_id,
                        resource=resource,
                        action=action,
                        matched_role=role.id,
                        matched_permission=permission.id,
                    )

        # Build denial reason
        if resource.sensitive:
            denial_reason = f"No permission for sensitive resource '{resource.resource_id}'"
        else:
            denial_reason = f"No permission for {action.value} on {resource.resource_type.value}/{resource.resource_id}"

        return AccessDecision(
            decision=PolicyDecision.DENY,
            principal_id=principal_id,
            resource=resource,
            action=action,
            denial_reason=denial_reason,
        )

    def require_access(
        self,
        principal_id: str,
        principal_type: PrincipalType,
        resource: Resource,
        action: Action,
        project_scope: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AccessDecision:
        """
        Hard enforcement: raises AccessDeniedError if denied.

        Use this for actual enforcement at security boundaries.
        """
        decision = self.check_access(
            principal_id, principal_type, resource, action, project_scope, context
        )

        if decision.decision != PolicyDecision.ALLOW:
            logger.warning(
                f"Access denied: principal={principal_id}, "
                f"resource={resource.resource_type}/{resource.resource_id}, "
                f"action={action.value}, reason={decision.denial_reason}"
            )
            raise AccessDeniedError(decision)

        logger.debug(
            f"Access allowed: principal={principal_id}, "
            f"resource={resource.resource_type}/{resource.resource_id}, "
            f"action={action.value}, role={decision.matched_role}"
        )

        return decision

    def filter_by_permission(
        self,
        principal_id: str,
        principal_type: PrincipalType,
        items: List[Any],
        get_resource: callable,
        action: Action = Action.READ,
        project_scope: Optional[str] = None,
    ) -> Tuple[List[Any], int]:
        """
        Filter a list of items by permission.

        Args:
            principal_id: Who is requesting access
            principal_type: Type of principal
            items: List of items to filter
            get_resource: Function to extract Resource from each item
            action: Action being performed
            project_scope: Optional project scope

        Returns:
            Tuple of (filtered_items, num_filtered)
        """
        allowed = []
        filtered_count = 0

        for item in items:
            resource = get_resource(item)
            decision = self.check_access(
                principal_id, principal_type, resource, action, project_scope
            )

            if decision.decision == PolicyDecision.ALLOW:
                allowed.append(item)
            else:
                filtered_count += 1
                logger.debug(
                    f"Filtered item: resource={resource.resource_id}, "
                    f"reason={decision.denial_reason}"
                )

        return allowed, filtered_count


# =============================================================================
# Global Enforcer
# =============================================================================

_default_enforcer: Optional[RBACEnforcer] = None


def get_enforcer() -> RBACEnforcer:
    """Get the default RBAC enforcer."""
    global _default_enforcer

    if _default_enforcer is None:
        _default_enforcer = RBACEnforcer()

    return _default_enforcer


def set_enforcer(enforcer: RBACEnforcer) -> None:
    """Set the default enforcer (for testing)."""
    global _default_enforcer
    _default_enforcer = enforcer


def reset_enforcer() -> None:
    """Reset the default enforcer (for testing)."""
    global _default_enforcer
    _default_enforcer = None
