"""Security contract derivation from manifest spec.security (REQ-ICD-106).

Derives a security_contract dict from ``spec.security.data_stores`` in the
raw project context YAML.  The emitted contract matches the schema expected
by startd8-sdk ``security_prime/contract.py:_derive_from_manifest()``.

Used by: ``build_onboarding_metadata()`` in ``onboarding.py``
Consumed by: startd8-sdk Security Prime (Anzen) orchestration layer
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def derive_security_contract(
    project_context_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Derive a security contract from ``spec.security`` in the manifest.

    Args:
        project_context_data: Raw YAML dict loaded from ``.contextcore.yaml``.

    Returns:
        Security contract dict suitable for inclusion in
        ``onboarding-metadata.json``, or ``None`` when ``spec.security``
        is absent.
    """
    spec = project_context_data.get("spec") or {}
    security_section = spec.get("security")
    if not security_section or not isinstance(security_section, dict):
        return None

    data_stores_raw: List[Dict[str, Any]] = security_section.get(
        "data_stores", security_section.get("dataStores", [])
    )
    if not isinstance(data_stores_raw, list):
        logger.warning("spec.security.data_stores is not a list — skipping")
        return None

    databases: Dict[str, Dict[str, Any]] = {}
    for store in data_stores_raw:
        if not isinstance(store, dict):
            continue
        store_id = store.get("id")
        if not store_id:
            logger.debug("Skipping data store entry without id")
            continue

        entry: Dict[str, Any] = {
            "type": store.get("type", ""),
            "client_library": store.get("client_library", store.get("clientLibrary", "")),
            "credential_source": store.get(
                "credential_source", store.get("credentialSource", "")
            ),
            "sensitivity": store.get("sensitivity", "medium"),
        }

        # Include access_policy only when declared (no default fabrication)
        access_policy = store.get("access_policy", store.get("accessPolicy"))
        if isinstance(access_policy, dict):
            policy_entry: Dict[str, Any] = {}
            allowed = access_policy.get(
                "allowed_principals", access_policy.get("allowedPrincipals", [])
            )
            if allowed:
                policy_entry["allowed_principals"] = allowed
            required_role = access_policy.get(
                "required_role", access_policy.get("requiredRole")
            )
            if required_role:
                policy_entry["required_role"] = required_role
            audit = access_policy.get(
                "audit_access", access_policy.get("auditAccess", False)
            )
            if audit:
                policy_entry["audit_access"] = True
            if policy_entry:
                entry["access_policy"] = policy_entry

        databases[store_id] = entry

    if not databases:
        return None

    return {
        "databases": databases,
        "sensitivity": security_section.get("sensitivity", "medium"),
        "source": "manifest",
    }
