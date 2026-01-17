"""
RBAC storage backends.

Stores roles and role bindings in file-based or Kubernetes storage.
Supports hybrid mode: file-based locally, K8s in cluster.

Data layout (file-based):
    ~/.contextcore/rbac/
    ├── roles/
    │   ├── reader.yaml
    │   ├── agent-standard.yaml
    │   └── custom-role.yaml
    ├── bindings/
    │   └── <binding_id>.yaml
    └── config.yaml
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from contextcore.rbac.models import (
    BUILT_IN_ROLES,
    BUILT_IN_ROLE_IDS,
    PrincipalType,
    Role,
    RoleBinding,
)

logger = logging.getLogger(__name__)


class BaseRBACStore(ABC):
    """Abstract base class for RBAC storage backends."""

    @abstractmethod
    def get_role(self, role_id: str) -> Optional[Role]:
        """Get a role by ID."""
        pass

    @abstractmethod
    def list_roles(self) -> List[Role]:
        """List all roles."""
        pass

    @abstractmethod
    def save_role(self, role: Role) -> None:
        """Save a role (create or update)."""
        pass

    @abstractmethod
    def delete_role(self, role_id: str) -> bool:
        """Delete a role. Returns False if built-in or not found."""
        pass

    @abstractmethod
    def get_binding(self, binding_id: str) -> Optional[RoleBinding]:
        """Get a role binding by ID."""
        pass

    @abstractmethod
    def list_bindings(
        self,
        principal_id: Optional[str] = None,
        role_id: Optional[str] = None,
    ) -> List[RoleBinding]:
        """List bindings, optionally filtered."""
        pass

    @abstractmethod
    def save_binding(self, binding: RoleBinding) -> None:
        """Save a role binding."""
        pass

    @abstractmethod
    def delete_binding(self, binding_id: str) -> bool:
        """Delete a role binding."""
        pass

    def get_roles_for_principal(
        self,
        principal_id: str,
        principal_type: PrincipalType,
        project_scope: Optional[str] = None,
    ) -> List[Role]:
        """
        Get all roles assigned to a principal.

        Includes inherited roles via role hierarchy.
        """
        bindings = self.list_bindings(principal_id=principal_id)

        # Filter by principal type and scope
        # Handle both enum and string values for comparison
        pt_value = principal_type.value if hasattr(principal_type, 'value') else principal_type
        valid_bindings = []
        for b in bindings:
            b_pt_value = b.principal_type.value if hasattr(b.principal_type, 'value') else b.principal_type
            if b_pt_value != pt_value:
                continue
            if b.is_expired():
                continue
            if project_scope and b.project_scope and b.project_scope != project_scope:
                continue
            valid_bindings.append(b)

        # Resolve roles with inheritance
        role_ids_to_resolve = {b.role_id for b in valid_bindings}
        resolved_roles: Dict[str, Role] = {}

        while role_ids_to_resolve:
            role_id = role_ids_to_resolve.pop()
            if role_id in resolved_roles:
                continue

            role = self.get_role(role_id)
            if role is None:
                logger.warning(f"Role {role_id} not found for binding")
                continue

            resolved_roles[role_id] = role

            # Add inherited roles to resolve
            for parent_id in role.inherits_from:
                if parent_id not in resolved_roles:
                    role_ids_to_resolve.add(parent_id)

        return list(resolved_roles.values())


class RBACFileStore(BaseRBACStore):
    """
    File-based RBAC storage for standalone deployments.

    Stores roles and bindings as YAML files for easy inspection.
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(
            base_dir or os.environ.get(
                "CONTEXTCORE_RBAC_DIR",
                os.path.expanduser("~/.contextcore/rbac")
            )
        )
        self._ensure_dirs()
        self._load_built_in_roles()
        logger.debug(f"RBACFileStore initialized at {self.base_dir}")

    def _ensure_dirs(self) -> None:
        """Create directory structure."""
        (self.base_dir / "roles").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "bindings").mkdir(parents=True, exist_ok=True)

    def _load_built_in_roles(self) -> None:
        """Ensure built-in roles exist."""
        for role in BUILT_IN_ROLES:
            role_file = self.base_dir / "roles" / f"{role.id}.yaml"
            if not role_file.exists():
                self.save_role(role)

    def _role_path(self, role_id: str) -> Path:
        """Get path for a role file."""
        return self.base_dir / "roles" / f"{role_id}.yaml"

    def _binding_path(self, binding_id: str) -> Path:
        """Get path for a binding file."""
        return self.base_dir / "bindings" / f"{binding_id}.yaml"

    def get_role(self, role_id: str) -> Optional[Role]:
        """Get a role by ID."""
        path = self._role_path(role_id)
        if not path.exists():
            return None

        with open(path) as f:
            data = yaml.safe_load(f)

        return Role.model_validate(data)

    def list_roles(self) -> List[Role]:
        """List all roles."""
        roles = []
        roles_dir = self.base_dir / "roles"

        for path in roles_dir.glob("*.yaml"):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                roles.append(Role.model_validate(data))
            except Exception as e:
                logger.error(f"Error loading role from {path}: {e}")

        return roles

    def save_role(self, role: Role) -> None:
        """Save a role (create or update)."""
        path = self._role_path(role.id)

        # Don't allow modifying built-in roles
        if path.exists() and role.id in BUILT_IN_ROLE_IDS:
            existing = self.get_role(role.id)
            if existing and existing.built_in and not role.built_in:
                raise ValueError(f"Cannot modify built-in role: {role.id}")

        data = role.model_dump(mode="json")

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        logger.debug(f"Saved role {role.id} to {path}")

    def delete_role(self, role_id: str) -> bool:
        """Delete a role. Returns False if built-in or not found."""
        if role_id in BUILT_IN_ROLE_IDS:
            logger.warning(f"Cannot delete built-in role: {role_id}")
            return False

        path = self._role_path(role_id)
        if not path.exists():
            return False

        path.unlink()
        logger.debug(f"Deleted role {role_id}")
        return True

    def get_binding(self, binding_id: str) -> Optional[RoleBinding]:
        """Get a role binding by ID."""
        path = self._binding_path(binding_id)
        if not path.exists():
            return None

        with open(path) as f:
            data = yaml.safe_load(f)

        return RoleBinding.model_validate(data)

    def list_bindings(
        self,
        principal_id: Optional[str] = None,
        role_id: Optional[str] = None,
    ) -> List[RoleBinding]:
        """List bindings, optionally filtered."""
        bindings = []
        bindings_dir = self.base_dir / "bindings"

        for path in bindings_dir.glob("*.yaml"):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                binding = RoleBinding.model_validate(data)

                # Apply filters
                if principal_id and binding.principal_id != principal_id:
                    continue
                if role_id and binding.role_id != role_id:
                    continue

                bindings.append(binding)
            except Exception as e:
                logger.error(f"Error loading binding from {path}: {e}")

        return bindings

    def save_binding(self, binding: RoleBinding) -> None:
        """Save a role binding."""
        path = self._binding_path(binding.id)
        data = binding.model_dump(mode="json")

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        logger.debug(f"Saved binding {binding.id} to {path}")

    def delete_binding(self, binding_id: str) -> bool:
        """Delete a role binding."""
        path = self._binding_path(binding_id)
        if not path.exists():
            return False

        path.unlink()
        logger.debug(f"Deleted binding {binding_id}")
        return True


class RBACMemoryStore(BaseRBACStore):
    """
    In-memory RBAC storage for testing.

    Data is lost when the process exits.
    """

    def __init__(self):
        self._roles: Dict[str, Role] = {}
        self._bindings: Dict[str, RoleBinding] = {}
        self._load_built_in_roles()

    def _load_built_in_roles(self) -> None:
        """Load built-in roles into memory."""
        for role in BUILT_IN_ROLES:
            self._roles[role.id] = role

    def get_role(self, role_id: str) -> Optional[Role]:
        return self._roles.get(role_id)

    def list_roles(self) -> List[Role]:
        return list(self._roles.values())

    def save_role(self, role: Role) -> None:
        if role.id in BUILT_IN_ROLE_IDS:
            existing = self._roles.get(role.id)
            if existing and existing.built_in and not role.built_in:
                raise ValueError(f"Cannot modify built-in role: {role.id}")
        self._roles[role.id] = role

    def delete_role(self, role_id: str) -> bool:
        if role_id in BUILT_IN_ROLE_IDS:
            return False
        if role_id not in self._roles:
            return False
        del self._roles[role_id]
        return True

    def get_binding(self, binding_id: str) -> Optional[RoleBinding]:
        return self._bindings.get(binding_id)

    def list_bindings(
        self,
        principal_id: Optional[str] = None,
        role_id: Optional[str] = None,
    ) -> List[RoleBinding]:
        bindings = list(self._bindings.values())

        if principal_id:
            bindings = [b for b in bindings if b.principal_id == principal_id]
        if role_id:
            bindings = [b for b in bindings if b.role_id == role_id]

        return bindings

    def save_binding(self, binding: RoleBinding) -> None:
        self._bindings[binding.id] = binding

    def delete_binding(self, binding_id: str) -> bool:
        if binding_id not in self._bindings:
            return False
        del self._bindings[binding_id]
        return True


# =============================================================================
# Store Factory
# =============================================================================

_default_store: Optional[BaseRBACStore] = None


def get_rbac_store() -> BaseRBACStore:
    """
    Get the default RBAC store.

    Auto-detects environment:
    - Returns file-based store for local development
    - Can be extended for K8s in future
    """
    global _default_store

    if _default_store is None:
        _default_store = RBACFileStore()

    return _default_store


def set_rbac_store(store: BaseRBACStore) -> None:
    """Set the default RBAC store (for testing)."""
    global _default_store
    _default_store = store


def reset_rbac_store() -> None:
    """Reset the default store (for testing)."""
    global _default_store
    _default_store = None
