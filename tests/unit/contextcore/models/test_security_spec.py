"""Tests for SecuritySpec, DataStoreSpec, AccessPolicySpec models (REQ-ICD-106)."""

from __future__ import annotations

import pytest

from contextcore.models.core import (
    AccessPolicySpec,
    DataStoreSpec,
    ProjectContextSpec,
    ProjectSpec,
    SecuritySpec,
    TargetKind,
    TargetSpec,
)
from contextcore.rbac.models import ResourceType


# ---------------------------------------------------------------------------
# DataStoreSpec
# ---------------------------------------------------------------------------

class TestDataStoreSpec:
    def test_minimal_data_store(self):
        ds = DataStoreSpec(id="cartdb", type="spanner")
        assert ds.id == "cartdb"
        assert ds.type == "spanner"
        assert ds.sensitivity == "medium"
        assert ds.client_library is None
        assert ds.credential_source is None
        assert ds.access_policy is None

    def test_full_data_store(self):
        ds = DataStoreSpec(
            id="cartdb",
            type="spanner",
            client_library="Google.Cloud.Spanner.Data",
            credential_source="workload_identity",
            sensitivity="high",
        )
        assert ds.client_library == "Google.Cloud.Spanner.Data"
        assert ds.credential_source == "workload_identity"
        assert ds.sensitivity == "high"

    def test_camel_case_aliases(self):
        ds = DataStoreSpec.model_validate({
            "id": "cache",
            "type": "redis",
            "clientLibrary": "StackExchange.Redis",
            "credentialSource": "environment_variable",
        })
        assert ds.client_library == "StackExchange.Redis"
        assert ds.credential_source == "environment_variable"


# ---------------------------------------------------------------------------
# AccessPolicySpec
# ---------------------------------------------------------------------------

class TestAccessPolicySpec:
    def test_defaults(self):
        ap = AccessPolicySpec()
        assert ap.allowed_principals == []
        assert ap.required_role is None
        assert ap.audit_access is False

    def test_full_policy(self):
        ap = AccessPolicySpec(
            allowed_principals=["service_account"],
            required_role="security-reader",
            audit_access=True,
        )
        assert ap.allowed_principals == ["service_account"]
        assert ap.required_role == "security-reader"
        assert ap.audit_access is True

    def test_camel_case_aliases(self):
        ap = AccessPolicySpec.model_validate({
            "allowedPrincipals": ["agent", "user"],
            "requiredRole": "admin",
            "auditAccess": True,
        })
        assert ap.allowed_principals == ["agent", "user"]
        assert ap.required_role == "admin"
        assert ap.audit_access is True

    def test_data_store_with_access_policy(self):
        ds = DataStoreSpec(
            id="cartdb",
            type="spanner",
            sensitivity="high",
            access_policy=AccessPolicySpec(
                allowed_principals=["service_account"],
                required_role="security-reader",
                audit_access=True,
            ),
        )
        assert ds.access_policy is not None
        assert ds.access_policy.required_role == "security-reader"


# ---------------------------------------------------------------------------
# SecuritySpec
# ---------------------------------------------------------------------------

class TestSecuritySpec:
    def test_defaults(self):
        ss = SecuritySpec()
        assert ss.sensitivity == "medium"
        assert ss.data_stores == []

    def test_with_data_stores(self):
        ss = SecuritySpec(
            sensitivity="high",
            data_stores=[
                DataStoreSpec(id="cartdb", type="spanner"),
                DataStoreSpec(id="cache", type="redis"),
            ],
        )
        assert len(ss.data_stores) == 2
        assert ss.data_stores[0].id == "cartdb"

    def test_camel_case_alias(self):
        ss = SecuritySpec.model_validate({
            "sensitivity": "high",
            "dataStores": [
                {"id": "db", "type": "postgresql"},
            ],
        })
        assert len(ss.data_stores) == 1


# ---------------------------------------------------------------------------
# ProjectContextSpec integration
# ---------------------------------------------------------------------------

class TestProjectContextSpecSecurity:
    def test_security_field_optional(self):
        spec = ProjectContextSpec(
            project=ProjectSpec(id="test"),
            targets=[TargetSpec(kind=TargetKind.DEPLOYMENT, name="test")],
        )
        assert spec.security is None

    def test_security_field_populated(self):
        spec = ProjectContextSpec(
            project=ProjectSpec(id="test"),
            targets=[TargetSpec(kind=TargetKind.DEPLOYMENT, name="test")],
            security=SecuritySpec(
                sensitivity="high",
                data_stores=[DataStoreSpec(id="db", type="postgresql")],
            ),
        )
        assert spec.security is not None
        assert spec.security.sensitivity == "high"
        assert len(spec.security.data_stores) == 1


# ---------------------------------------------------------------------------
# RBAC ResourceType
# ---------------------------------------------------------------------------

class TestDataStoreResourceType:
    def test_data_store_in_resource_type(self):
        assert ResourceType.DATA_STORE == "data_store"
        assert ResourceType("data_store") == ResourceType.DATA_STORE
