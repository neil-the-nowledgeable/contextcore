"""Tests for security contract verification requirements (REQ-SCV-001–004)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from contextcore.install.requirements import (
    RequirementCategory,
    check_security_audit_policy,
    check_security_credential_sources,
    check_security_manifest_declaration,
    _get_security_data_stores,
    _load_contextcore_yaml,
    INSTALLATION_REQUIREMENTS,
)


# ---------------------------------------------------------------------------
# REQ-SCV-001: SECURITY category exists
# ---------------------------------------------------------------------------

class TestSecurityCategory:
    def test_security_category_exists(self):
        assert RequirementCategory.SECURITY == "security"

    def test_security_requirements_in_registry(self):
        security_reqs = [
            r for r in INSTALLATION_REQUIREMENTS
            if r.category == RequirementCategory.SECURITY
        ]
        assert len(security_reqs) == 3
        ids = {r.id for r in security_reqs}
        assert ids == {
            "security_manifest_declaration",
            "security_audit_policy",
            "security_credential_sources",
        }

    def test_all_security_requirements_non_critical(self):
        security_reqs = [
            r for r in INSTALLATION_REQUIREMENTS
            if r.category == RequirementCategory.SECURITY
        ]
        assert all(not r.critical for r in security_reqs)


# ---------------------------------------------------------------------------
# REQ-SCV-002: Manifest security declaration check
# ---------------------------------------------------------------------------

class TestSecurityManifestDeclaration:
    def test_no_manifest_passes(self):
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=None,
        ):
            assert check_security_manifest_declaration() is True

    def test_manifest_with_data_stores_passes(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{"id": "db", "type": "postgresql"}],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_manifest_declaration() is True

    def test_no_security_no_detected_databases_passes(self, tmp_path: Path):
        data = {"spec": {"project": {"id": "test"}}}
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ), mock.patch(
            "contextcore.install.requirements._find_project_root",
            return_value=tmp_path,
        ):
            assert check_security_manifest_declaration() is True

    def test_no_security_but_detected_databases_fails(self, tmp_path: Path):
        data = {"spec": {"project": {"id": "test"}}}
        # Create onboarding metadata with detected databases
        export_dir = tmp_path / "out" / "export"
        export_dir.mkdir(parents=True)
        onboarding = {
            "instrumentation_hints": {
                "cartservice": {
                    "detected_databases": ["spanner"],
                },
            },
        }
        (export_dir / "onboarding-metadata.json").write_text(
            json.dumps(onboarding), encoding="utf-8",
        )
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ), mock.patch(
            "contextcore.install.requirements._find_project_root",
            return_value=tmp_path,
        ):
            assert check_security_manifest_declaration() is False

    def test_detected_databases_empty_list_passes(self, tmp_path: Path):
        data = {"spec": {"project": {"id": "test"}}}
        export_dir = tmp_path / "out" / "export"
        export_dir.mkdir(parents=True)
        onboarding = {
            "instrumentation_hints": {
                "emailservice": {
                    "detected_databases": [],
                },
            },
        }
        (export_dir / "onboarding-metadata.json").write_text(
            json.dumps(onboarding), encoding="utf-8",
        )
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ), mock.patch(
            "contextcore.install.requirements._find_project_root",
            return_value=tmp_path,
        ):
            assert check_security_manifest_declaration() is True


# ---------------------------------------------------------------------------
# REQ-SCV-003: High-sensitivity audit policy check
# ---------------------------------------------------------------------------

class TestSecurityAuditPolicy:
    def test_no_manifest_passes(self):
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=None,
        ):
            assert check_security_audit_policy() is True

    def test_no_data_stores_passes(self):
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value={"spec": {}},
        ):
            assert check_security_audit_policy() is True

    def test_high_sensitivity_with_audit_passes(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{
                        "id": "db",
                        "type": "spanner",
                        "sensitivity": "high",
                        "access_policy": {"audit_access": True},
                    }],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_audit_policy() is True

    def test_high_sensitivity_without_audit_fails(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{
                        "id": "db",
                        "type": "spanner",
                        "sensitivity": "high",
                    }],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_audit_policy() is False

    def test_medium_sensitivity_without_audit_passes(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{
                        "id": "cache",
                        "type": "redis",
                        "sensitivity": "medium",
                    }],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_audit_policy() is True

    def test_camel_case_audit_access(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{
                        "id": "db",
                        "type": "spanner",
                        "sensitivity": "high",
                        "accessPolicy": {"auditAccess": True},
                    }],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_audit_policy() is True


# ---------------------------------------------------------------------------
# REQ-SCV-004: Credential source validation
# ---------------------------------------------------------------------------

class TestSecurityCredentialSources:
    def test_no_manifest_passes(self):
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=None,
        ):
            assert check_security_credential_sources() is True

    def test_known_sources_pass(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [
                        {"id": "a", "type": "x", "credential_source": "env_var"},
                        {"id": "b", "type": "y", "credential_source": "secrets_manager"},
                        {"id": "c", "type": "z", "credential_source": "workload_identity"},
                        {"id": "d", "type": "w", "credential_source": "environment_variable"},
                    ],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_credential_sources() is True

    def test_unknown_source_fails(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{
                        "id": "db",
                        "type": "postgresql",
                        "credential_source": "envvar",  # typo
                    }],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_credential_sources() is False

    def test_empty_source_passes(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{
                        "id": "db",
                        "type": "redis",
                        "credential_source": "",
                    }],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_credential_sources() is True

    def test_camel_case_credential_source(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{
                        "id": "db",
                        "type": "postgresql",
                        "credentialSource": "bad_value",
                    }],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_credential_sources() is False

    def test_no_credential_source_passes(self):
        data = {
            "spec": {
                "security": {
                    "data_stores": [{"id": "db", "type": "redis"}],
                },
            },
        }
        with mock.patch(
            "contextcore.install.requirements._load_contextcore_yaml",
            return_value=data,
        ):
            assert check_security_credential_sources() is True


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

class TestGetSecurityDataStores:
    def test_snake_case(self):
        data = {"spec": {"security": {"data_stores": [{"id": "a"}]}}}
        assert _get_security_data_stores(data) == [{"id": "a"}]

    def test_camel_case(self):
        data = {"spec": {"security": {"dataStores": [{"id": "b"}]}}}
        assert _get_security_data_stores(data) == [{"id": "b"}]

    def test_missing_security(self):
        assert _get_security_data_stores({"spec": {}}) == []

    def test_missing_spec(self):
        assert _get_security_data_stores({}) == []
