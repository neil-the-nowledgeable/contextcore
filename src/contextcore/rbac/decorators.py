"""
RBAC Decorators for CLI and function protection.

Provides decorators for enforcing RBAC permissions on CLI commands
and functions.

Example:
    @knowledge.command("query")
    @require_permission(
        ResourceType.KNOWLEDGE_CATEGORY,
        "security",
        Action.QUERY,
        sensitive=True,
    )
    def knowledge_query_security(...):
        ...

    # Or with dynamic resource extraction
    @require_permission_dynamic(
        get_resource=lambda category: Resource(
            resource_type=ResourceType.KNOWLEDGE_CATEGORY,
            resource_id=category,
            sensitive=(category == "security"),
        ),
        action=Action.QUERY,
        resource_param="category",
    )
    def knowledge_query(category: str, ...):
        ...
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Optional

import click

from contextcore.rbac.models import (
    AccessDeniedError,
    Action,
    Resource,
    ResourceType,
)
from contextcore.rbac.enforcer import (
    PrincipalResolver,
    get_enforcer,
)

logger = logging.getLogger(__name__)


def require_permission(
    resource_type: ResourceType,
    resource_id: str,
    action: Action,
    sensitive: bool = False,
    project_param: Optional[str] = None,
):
    """
    CLI decorator for static permission enforcement.

    Checks permission before executing the command.
    Raises click.ClickException on access denial.

    Args:
        resource_type: Type of resource being accessed
        resource_id: Specific resource ID or "*" for any
        action: Action being performed
        sensitive: Whether this requires elevated permissions
        project_param: CLI parameter name for project scope (optional)

    Example:
        @cli.command()
        @require_permission(
            ResourceType.KNOWLEDGE_CATEGORY,
            "security",
            Action.READ,
            sensitive=True,
        )
        def read_secrets():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Resolve principal from CLI context
            principal = PrincipalResolver.from_cli_context()

            # Build resource
            resource = Resource(
                resource_type=resource_type,
                resource_id=resource_id,
                sensitive=sensitive,
            )

            # Get project scope if specified
            project_scope = None
            if project_param and project_param in kwargs:
                project_scope = kwargs[project_param]

            # Enforce permission
            enforcer = get_enforcer()
            try:
                enforcer.require_access(
                    principal.id,
                    principal.principal_type,
                    resource,
                    action,
                    project_scope=project_scope,
                )
            except AccessDeniedError as e:
                raise click.ClickException(
                    f"Permission denied: {e.decision.denial_reason}\n"
                    f"Required: {action.value} on {resource_type.value}/{resource_id}"
                )

            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_permission_dynamic(
    get_resource: Callable[..., Resource],
    action: Action,
    resource_param: Optional[str] = None,
    project_param: Optional[str] = None,
):
    """
    CLI decorator for dynamic permission enforcement.

    Extracts resource from function arguments using get_resource callback.

    Args:
        get_resource: Function to build Resource from kwargs
        action: Action being performed
        resource_param: Parameter name to pass to get_resource (optional)
        project_param: CLI parameter name for project scope (optional)

    Example:
        @cli.command()
        @require_permission_dynamic(
            get_resource=lambda category: Resource(
                resource_type=ResourceType.KNOWLEDGE_CATEGORY,
                resource_id=category or "*",
                sensitive=(category == "security"),
            ),
            action=Action.QUERY,
            resource_param="category",
        )
        def query(category: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Resolve principal from CLI context
            principal = PrincipalResolver.from_cli_context()

            # Build resource dynamically
            if resource_param and resource_param in kwargs:
                resource = get_resource(kwargs[resource_param])
            else:
                resource = get_resource(**kwargs)

            # Get project scope if specified
            project_scope = None
            if project_param and project_param in kwargs:
                project_scope = kwargs[project_param]

            # Enforce permission
            enforcer = get_enforcer()
            try:
                enforcer.require_access(
                    principal.id,
                    principal.principal_type,
                    resource,
                    action,
                    project_scope=project_scope,
                )
            except AccessDeniedError as e:
                raise click.ClickException(
                    f"Permission denied: {e.decision.denial_reason}"
                )

            return func(*args, **kwargs)
        return wrapper
    return decorator


def with_rbac_filter(
    get_resource: Callable[[Any], Resource],
    action: Action = Action.READ,
    results_param: str = "results",
):
    """
    Decorator that filters function results by RBAC permission.

    For functions that return lists, this filters out items
    the principal doesn't have access to.

    Args:
        get_resource: Function to extract Resource from each item
        action: Action being performed on items
        results_param: Name of the return value to filter

    Note: This decorator expects the wrapped function to return
    a dict with the results_param key, or a list directly.

    Example:
        @with_rbac_filter(
            get_resource=lambda cap: Resource(
                resource_type=ResourceType.KNOWLEDGE_CAPABILITY,
                resource_id=cap.capability_id,
                sensitive=(cap.knowledge_category == "security"),
            ),
        )
        def query_capabilities():
            return {"results": [...], "total": 100}
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # Resolve principal
            principal = PrincipalResolver.from_cli_context()
            enforcer = get_enforcer()

            # Handle dict return with results key
            if isinstance(result, dict) and results_param in result:
                items = result[results_param]
                filtered, count = enforcer.filter_by_permission(
                    principal.id,
                    principal.principal_type,
                    items,
                    get_resource,
                    action,
                )
                result[results_param] = filtered
                result["filtered_by_permission"] = count
                return result

            # Handle list return
            if isinstance(result, list):
                filtered, count = enforcer.filter_by_permission(
                    principal.id,
                    principal.principal_type,
                    result,
                    get_resource,
                    action,
                )
                return filtered

            return result
        return wrapper
    return decorator


class RBACContext:
    """
    Context manager for RBAC-protected operations.

    Useful when you need fine-grained control over permission checking
    within a function.

    Example:
        with RBACContext(principal_id="claude-code", principal_type=PrincipalType.AGENT) as rbac:
            rbac.require(security_resource, Action.READ)
            # Do protected operation
    """

    def __init__(
        self,
        principal_id: Optional[str] = None,
        principal_type: Optional[str] = None,
    ):
        if principal_id and principal_type:
            from contextcore.rbac.models import PrincipalType as PT
            self.principal_id = principal_id
            self.principal_type = PT(principal_type)
        else:
            principal = PrincipalResolver.from_cli_context()
            self.principal_id = principal.id
            self.principal_type = principal.principal_type

        self.enforcer = get_enforcer()

    def __enter__(self) -> "RBACContext":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def check(
        self,
        resource: Resource,
        action: Action,
        project_scope: Optional[str] = None,
    ):
        """Check access without raising (returns decision)."""
        return self.enforcer.check_access(
            self.principal_id,
            self.principal_type,
            resource,
            action,
            project_scope,
        )

    def require(
        self,
        resource: Resource,
        action: Action,
        project_scope: Optional[str] = None,
    ):
        """Require access (raises AccessDeniedError on denial)."""
        return self.enforcer.require_access(
            self.principal_id,
            self.principal_type,
            resource,
            action,
            project_scope,
        )
