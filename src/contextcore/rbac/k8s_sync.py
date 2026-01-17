"""
Kubernetes RBAC Synchronization.

Syncs K8s RBAC with ContextCore RBAC for hybrid deployments.

Maps:
- K8s ClusterRole/Role -> ContextCore Role (by name mapping)
- K8s ClusterRoleBinding/RoleBinding -> ContextCore RoleBinding
- K8s ServiceAccount -> ContextCore Principal

Example:
    sync = K8sRBACSync(namespace="default")
    bindings = sync.sync_service_account("my-agent")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from contextcore.rbac.models import (
    PrincipalType,
    RoleBinding,
)

logger = logging.getLogger(__name__)


# Default mapping from K8s roles to ContextCore roles
DEFAULT_K8S_ROLE_MAPPING: Dict[str, str] = {
    "cluster-admin": "admin",
    "admin": "admin",
    "edit": "agent-standard",
    "view": "reader",
}


def detect_kubernetes() -> bool:
    """
    Detect if running inside a Kubernetes cluster.

    Checks for service account token mount.
    """
    sa_token_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    return sa_token_path.exists()


def get_current_namespace() -> str:
    """
    Get the current Kubernetes namespace.

    Reads from mounted service account namespace file.
    Falls back to 'default' if not in cluster.
    """
    ns_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
    if ns_path.exists():
        return ns_path.read_text().strip()
    return os.environ.get("CONTEXTCORE_NAMESPACE", "default")


class K8sRBACSync:
    """
    Synchronizes K8s RBAC with ContextCore RBAC.

    Maps Kubernetes ClusterRoles and Roles to ContextCore roles,
    and syncs RoleBindings/ClusterRoleBindings as ContextCore bindings.

    Example:
        sync = K8sRBACSync(namespace="default")

        # Sync a service account
        bindings = sync.sync_service_account("my-agent")

        # Get principal for service account
        principal = sync.get_principal_for_service_account("my-agent")
    """

    def __init__(
        self,
        namespace: str = "default",
        role_mapping: Optional[Dict[str, str]] = None,
    ):
        self.namespace = namespace
        self.role_mapping = role_mapping or DEFAULT_K8S_ROLE_MAPPING
        self._k8s_available = detect_kubernetes()

        if self._k8s_available:
            try:
                from kubernetes import client, config

                # Load in-cluster config or kubeconfig
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()

                self.rbac_api = client.RbacAuthorizationV1Api()
                self.core_api = client.CoreV1Api()
                logger.info(f"K8sRBACSync initialized for namespace {namespace}")
            except ImportError:
                logger.warning("kubernetes package not installed, K8s sync disabled")
                self._k8s_available = False
            except Exception as e:
                logger.warning(f"Failed to initialize K8s client: {e}")
                self._k8s_available = False
        else:
            logger.debug("Not running in K8s, sync disabled")

    @property
    def is_available(self) -> bool:
        """Check if K8s sync is available."""
        return self._k8s_available

    def get_k8s_bindings_for_sa(
        self,
        sa_name: str,
        namespace: Optional[str] = None,
    ) -> List[dict]:
        """
        Get K8s RoleBindings and ClusterRoleBindings for a service account.

        Returns list of binding info dicts with role_name and binding_name.
        """
        if not self._k8s_available:
            return []

        ns = namespace or self.namespace
        bindings = []

        try:
            # Check ClusterRoleBindings
            crbs = self.rbac_api.list_cluster_role_binding()
            for crb in crbs.items:
                if crb.subjects:
                    for subject in crb.subjects:
                        if (
                            subject.kind == "ServiceAccount"
                            and subject.name == sa_name
                            and (subject.namespace == ns or subject.namespace is None)
                        ):
                            bindings.append({
                                "binding_name": crb.metadata.name,
                                "role_name": crb.role_ref.name,
                                "role_kind": crb.role_ref.kind,
                                "cluster_wide": True,
                            })

            # Check RoleBindings in namespace
            rbs = self.rbac_api.list_namespaced_role_binding(ns)
            for rb in rbs.items:
                if rb.subjects:
                    for subject in rb.subjects:
                        if (
                            subject.kind == "ServiceAccount"
                            and subject.name == sa_name
                        ):
                            bindings.append({
                                "binding_name": rb.metadata.name,
                                "role_name": rb.role_ref.name,
                                "role_kind": rb.role_ref.kind,
                                "cluster_wide": False,
                            })

        except Exception as e:
            logger.error(f"Error fetching K8s bindings for {sa_name}: {e}")

        return bindings

    def sync_service_account(
        self,
        sa_name: str,
        namespace: Optional[str] = None,
    ) -> List[RoleBinding]:
        """
        Sync K8s service account bindings to ContextCore.

        Returns list of created ContextCore RoleBindings.
        """
        if not self._k8s_available:
            logger.warning("K8s not available, cannot sync service account")
            return []

        ns = namespace or self.namespace
        k8s_bindings = self.get_k8s_bindings_for_sa(sa_name, ns)

        context_bindings = []
        for kb in k8s_bindings:
            k8s_role = kb["role_name"]

            # Map K8s role to ContextCore role
            if k8s_role in self.role_mapping:
                cc_role = self.role_mapping[k8s_role]
            else:
                # Check for partial match
                cc_role = None
                for k8s_pattern, cc_mapped in self.role_mapping.items():
                    if k8s_pattern in k8s_role or k8s_role in k8s_pattern:
                        cc_role = cc_mapped
                        break

                if cc_role is None:
                    logger.debug(f"No mapping for K8s role {k8s_role}, skipping")
                    continue

            binding = RoleBinding(
                id=f"k8s-{kb['binding_name']}",
                principal_id=f"{ns}:{sa_name}",
                principal_type=PrincipalType.SERVICE_ACCOUNT,
                role_id=cc_role,
                namespace_scope=ns if not kb["cluster_wide"] else None,
                created_by="k8s-sync",
            )
            context_bindings.append(binding)

            logger.info(
                f"Synced K8s binding: {sa_name} -> {cc_role} "
                f"(from {k8s_role})"
            )

        return context_bindings

    def sync_all_service_accounts(
        self,
        namespace: Optional[str] = None,
    ) -> Dict[str, List[RoleBinding]]:
        """
        Sync all service accounts in a namespace.

        Returns dict mapping service account name to their bindings.
        """
        if not self._k8s_available:
            return {}

        ns = namespace or self.namespace
        result = {}

        try:
            sas = self.core_api.list_namespaced_service_account(ns)
            for sa in sas.items:
                bindings = self.sync_service_account(sa.metadata.name, ns)
                if bindings:
                    result[sa.metadata.name] = bindings
        except Exception as e:
            logger.error(f"Error syncing service accounts in {ns}: {e}")

        return result

    def add_role_mapping(self, k8s_role: str, contextcore_role: str) -> None:
        """Add a custom K8s to ContextCore role mapping."""
        self.role_mapping[k8s_role] = contextcore_role
        logger.info(f"Added role mapping: {k8s_role} -> {contextcore_role}")


class HybridRBACStore:
    """
    Hybrid RBAC store that combines file and K8s storage.

    Behavior:
    - Standalone: Uses file storage only
    - K8s detected: Uses K8s ConfigMap with file fallback
    - K8s RBAC sync enabled: Also syncs from K8s RBAC
    """

    def __init__(
        self,
        namespace: str = "default",
        sync_k8s_rbac: bool = False,
        role_mapping: Optional[Dict[str, str]] = None,
    ):
        from contextcore.rbac.store import RBACFileStore

        self.namespace = namespace
        self.file_store = RBACFileStore()
        self.sync_enabled = sync_k8s_rbac

        if sync_k8s_rbac:
            self.k8s_sync = K8sRBACSync(namespace, role_mapping)
        else:
            self.k8s_sync = None

    def get_roles_for_principal(
        self,
        principal_id: str,
        principal_type: PrincipalType,
        project_scope: Optional[str] = None,
    ):
        """
        Get roles for a principal, including K8s synced roles.
        """
        # Get from file store
        roles = self.file_store.get_roles_for_principal(
            principal_id, principal_type, project_scope
        )

        # If K8s sync is enabled and this is a service account, sync
        if (
            self.sync_enabled
            and self.k8s_sync
            and self.k8s_sync.is_available
            and principal_type == PrincipalType.SERVICE_ACCOUNT
        ):
            # Parse namespace:name format
            if ":" in principal_id:
                ns, sa_name = principal_id.split(":", 1)
            else:
                ns = self.namespace
                sa_name = principal_id

            # Sync bindings from K8s
            k8s_bindings = self.k8s_sync.sync_service_account(sa_name, ns)

            # Add K8s-synced roles
            for binding in k8s_bindings:
                role = self.file_store.get_role(binding.role_id)
                if role and role not in roles:
                    roles.append(role)

        return roles
