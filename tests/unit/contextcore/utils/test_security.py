"""Tests for security contract derivation (REQ-ICD-106)."""

from __future__ import annotations

import pytest

from contextcore.utils.security import derive_security_contract


class TestDeriveSecurityContract:
    def test_no_security_section_returns_none(self):
        assert derive_security_contract({"spec": {}}) is None
        assert derive_security_contract({}) is None
        assert derive_security_contract({"spec": {"project": {}}}) is None

    def test_empty_data_stores_returns_none(self):
        data = {"spec": {"security": {"data_stores": []}}}
        assert derive_security_contract(data) is None

    def test_single_data_store(self):
        data = {
            "spec": {
                "security": {
                    "sensitivity": "high",
                    "data_stores": [
                        {
                            "id": "cartdb",
                            "type": "spanner",
                            "client_library": "Google.Cloud.Spanner.Data",
                            "credential_source": "workload_identity",
                            "sensitivity": "high",
                        },
                    ],
                },
            },
        }
        result = derive_security_contract(data)
        assert result is not None
        assert result["source"] == "manifest"
        assert result["sensitivity"] == "high"
        assert "cartdb" in result["databases"]
        db = result["databases"]["cartdb"]
        assert db["type"] == "spanner"
        assert db["client_library"] == "Google.Cloud.Spanner.Data"
        assert db["credential_source"] == "workload_identity"
        assert db["sensitivity"] == "high"

    def test_multiple_data_stores(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [
                        {"id": "cartdb", "type": "spanner"},
                        {"id": "cache", "type": "redis"},
                    ],
                },
            },
        }
        result = derive_security_contract(data)
        assert len(result["databases"]) == 2
        assert "cartdb" in result["databases"]
        assert "cache" in result["databases"]

    def test_defaults_applied(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{"id": "db", "type": "postgresql"}],
                },
            },
        }
        result = derive_security_contract(data)
        db = result["databases"]["db"]
        assert db["sensitivity"] == "medium"
        assert db["client_library"] == ""
        assert db["credential_source"] == ""
        assert result["sensitivity"] == "medium"

    def test_access_policy_included(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [
                        {
                            "id": "cartdb",
                            "type": "spanner",
                            "sensitivity": "high",
                            "access_policy": {
                                "allowed_principals": ["service_account"],
                                "required_role": "security-reader",
                                "audit_access": True,
                            },
                        },
                    ],
                },
            },
        }
        result = derive_security_contract(data)
        ap = result["databases"]["cartdb"]["access_policy"]
        assert ap["allowed_principals"] == ["service_account"]
        assert ap["required_role"] == "security-reader"
        assert ap["audit_access"] is True

    def test_access_policy_omitted_when_not_declared(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{"id": "db", "type": "redis"}],
                },
            },
        }
        result = derive_security_contract(data)
        assert "access_policy" not in result["databases"]["db"]

    def test_camel_case_keys(self):
        data = {
            "spec": {
                "security": {
                    "dataStores": [
                        {
                            "id": "db",
                            "type": "postgresql",
                            "clientLibrary": "Npgsql",
                            "credentialSource": "env_var",
                            "accessPolicy": {
                                "allowedPrincipals": ["user"],
                                "requiredRole": "admin",
                                "auditAccess": True,
                            },
                        },
                    ],
                },
            },
        }
        result = derive_security_contract(data)
        assert result is not None
        db = result["databases"]["db"]
        assert db["client_library"] == "Npgsql"
        assert db["credential_source"] == "env_var"
        assert db["access_policy"]["allowed_principals"] == ["user"]

    def test_store_without_id_skipped(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [
                        {"type": "redis"},  # no id
                        {"id": "valid", "type": "postgresql"},
                    ],
                },
            },
        }
        result = derive_security_contract(data)
        assert len(result["databases"]) == 1
        assert "valid" in result["databases"]

    def test_non_list_data_stores_returns_none(self):
        data = {"spec": {"security": {"data_stores": "not-a-list"}}}
        assert derive_security_contract(data) is None


class TestSecurityContractInOnboarding:
    def test_security_contract_emitted_in_onboarding(self):
        """Security contract appears in onboarding metadata when project_context_data provided."""
        from contextcore.models.artifact_manifest import (
            ArtifactManifest,
            ArtifactManifestMetadata,
            ArtifactPriority,
            ArtifactSpec,
            ArtifactStatus,
            ArtifactType,
            CoverageSummary,
        )
        from contextcore.utils.onboarding import build_onboarding_metadata

        manifest = ArtifactManifest(
            metadata=ArtifactManifestMetadata(
                generated_from="test.yaml",
                project_id="test-project",
            ),
            artifacts=[
                ArtifactSpec(
                    id="test-dashboard",
                    type=ArtifactType.DASHBOARD,
                    name="Test",
                    target="test",
                    priority=ArtifactPriority.REQUIRED,
                    status=ArtifactStatus.NEEDED,
                ),
            ],
            coverage=CoverageSummary(),
        )

        raw_data = {
            "spec": {
                "security": {
                    "sensitivity": "high",
                    "data_stores": [
                        {"id": "cartdb", "type": "spanner", "sensitivity": "high"},
                    ],
                },
            },
        }

        result = build_onboarding_metadata(
            artifact_manifest=manifest,
            artifact_manifest_path="test.yaml",
            project_context_path="test-crd.yaml",
            project_context_data=raw_data,
        )
        assert "security_contract" in result
        assert result["security_contract"]["source"] == "manifest"
        assert "cartdb" in result["security_contract"]["databases"]

    def test_no_security_contract_without_project_context_data(self):
        """Security contract absent when project_context_data not provided."""
        from contextcore.models.artifact_manifest import (
            ArtifactManifest,
            ArtifactManifestMetadata,
            ArtifactPriority,
            ArtifactSpec,
            ArtifactStatus,
            ArtifactType,
            CoverageSummary,
        )
        from contextcore.utils.onboarding import build_onboarding_metadata

        manifest = ArtifactManifest(
            metadata=ArtifactManifestMetadata(
                generated_from="test.yaml",
                project_id="test-project",
            ),
            artifacts=[
                ArtifactSpec(
                    id="test-dashboard",
                    type=ArtifactType.DASHBOARD,
                    name="Test",
                    target="test",
                    priority=ArtifactPriority.REQUIRED,
                    status=ArtifactStatus.NEEDED,
                ),
            ],
            coverage=CoverageSummary(),
        )

        result = build_onboarding_metadata(
            artifact_manifest=manifest,
            artifact_manifest_path="test.yaml",
            project_context_path="test-crd.yaml",
        )
        assert "security_contract" not in result
