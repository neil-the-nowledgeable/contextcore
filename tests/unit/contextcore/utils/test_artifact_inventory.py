"""Tests for contextcore.utils.artifact_inventory."""

import json

import pytest

from contextcore.utils.artifact_inventory import (
    EXPORT_INVENTORY_ROLES,
    PRE_PIPELINE_INVENTORY_ROLES,
    build_export_inventory,
    build_inventory_entry,
    compute_sub_document_checksum,
    extend_inventory,
)


class TestComputeSubDocumentChecksum:
    def test_deterministic(self):
        """Same data should produce same checksum."""
        data = {"key": "value", "nested": {"a": 1}}
        c1 = compute_sub_document_checksum(data)
        c2 = compute_sub_document_checksum(data)
        assert c1 == c2

    def test_order_independent(self):
        """Key order should not affect checksum (sort_keys=True)."""
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        assert compute_sub_document_checksum(d1) == compute_sub_document_checksum(d2)

    def test_different_data_different_checksum(self):
        assert compute_sub_document_checksum({"a": 1}) != compute_sub_document_checksum({"a": 2})

    def test_hex_format(self):
        result = compute_sub_document_checksum({"x": 1})
        assert len(result) == 64  # SHA-256 hex digest length
        assert all(c in "0123456789abcdef" for c in result)


class TestBuildInventoryEntry:
    def test_includes_required_fields(self):
        entry = build_inventory_entry(
            role="derivation_rules",
            stage="export",
            source_file="onboarding-metadata.json",
            produced_by="contextcore.manifest.export",
            data={"rule_1": "value"},
        )
        assert entry["artifact_id"] == "export.derivation_rules"
        assert entry["role"] == "derivation_rules"
        assert entry["stage"] == "export"
        assert entry["source_file"] == "onboarding-metadata.json"
        assert entry["produced_by"] == "contextcore.manifest.export"
        assert "sha256" in entry
        assert "produced_at" in entry
        assert isinstance(entry["consumers"], list)

    def test_includes_json_path_when_provided(self):
        entry = build_inventory_entry(
            role="test",
            stage="export",
            source_file="test.json",
            produced_by="test",
            data={"k": "v"},
            json_path="$.test_field",
        )
        assert entry["json_path"] == "$.test_field"

    def test_excludes_json_path_when_not_provided(self):
        entry = build_inventory_entry(
            role="test",
            stage="export",
            source_file="test.json",
            produced_by="test",
            data={"k": "v"},
        )
        assert "json_path" not in entry

    def test_includes_freshness(self):
        entry = build_inventory_entry(
            role="test",
            stage="export",
            source_file="test.json",
            produced_by="test",
            data={"k": "v"},
            source_checksum="abc123",
            source_checksum_file=".contextcore.yaml",
        )
        assert entry["freshness"]["source_checksum"] == "abc123"
        assert entry["freshness"]["source_file"] == ".contextcore.yaml"

    def test_no_freshness_without_checksum(self):
        entry = build_inventory_entry(
            role="test",
            stage="export",
            source_file="test.json",
            produced_by="test",
            data={"k": "v"},
        )
        assert "freshness" not in entry


class TestBuildExportInventory:
    def test_creates_entries_for_present_roles(self):
        metadata = {
            "derivation_rules": {"dashboard": {"alertSeverity": "P2"}},
            "resolved_artifact_parameters": {"dashboard-1": {"severity": "P2"}},
            "expected_output_contracts": {"dashboard": {"max_lines": 200}},
        }
        inventory = build_export_inventory(metadata, source_checksum="abc")
        roles = {e["role"] for e in inventory}
        assert "derivation_rules" in roles
        assert "resolved_parameters" in roles
        assert "output_contracts" in roles
        assert len(inventory) == 3

    def test_skips_missing_roles(self):
        metadata = {
            "derivation_rules": {"dashboard": {"alertSeverity": "P2"}},
            # resolved_artifact_parameters is missing
        }
        inventory = build_export_inventory(metadata)
        roles = {e["role"] for e in inventory}
        assert "derivation_rules" in roles
        assert "resolved_parameters" not in roles

    def test_skips_empty_roles(self):
        metadata = {
            "derivation_rules": {},  # Empty dict
            "open_questions": [],  # Empty list
        }
        inventory = build_export_inventory(metadata)
        assert len(inventory) == 0

    def test_all_ten_roles_when_present(self):
        metadata = {}
        for role, spec in EXPORT_INVENTORY_ROLES.items():
            metadata[spec["metadata_key"]] = {"some": "data"}
        inventory = build_export_inventory(metadata)
        assert len(inventory) == 10

    def test_entries_have_correct_stage(self):
        metadata = {"derivation_rules": {"x": 1}}
        inventory = build_export_inventory(metadata)
        assert all(e["stage"] == "export" for e in inventory)

    def test_entries_reference_onboarding_metadata(self):
        metadata = {"derivation_rules": {"x": 1}}
        inventory = build_export_inventory(metadata, source_file="custom.json")
        assert inventory[0]["source_file"] == "custom.json"

    def test_freshness_propagated(self):
        metadata = {"derivation_rules": {"x": 1}}
        inventory = build_export_inventory(
            metadata,
            source_checksum="sha256hash",
            source_checksum_file=".contextcore.yaml",
        )
        assert inventory[0]["freshness"]["source_checksum"] == "sha256hash"
        assert inventory[0]["freshness"]["source_file"] == ".contextcore.yaml"


class TestPrePipelineRoles:
    def test_project_context_role_exists(self):
        assert "project_context" in PRE_PIPELINE_INVENTORY_ROLES

    def test_polish_report_role_exists(self):
        assert "polish_report" in PRE_PIPELINE_INVENTORY_ROLES

    def test_project_context_stage(self):
        assert PRE_PIPELINE_INVENTORY_ROLES["project_context"]["stage"] == "create"

    def test_polish_report_stage(self):
        assert PRE_PIPELINE_INVENTORY_ROLES["polish_report"]["stage"] == "polish"

    def test_roles_have_consumers(self):
        for role, spec in PRE_PIPELINE_INVENTORY_ROLES.items():
            assert len(spec["consumers"]) > 0, f"{role} has no consumers"


class TestExtendInventory:
    def test_creates_new_provenance(self, tmp_path):
        """Creates run-provenance.json when none exists."""
        entry = build_inventory_entry(
            role="project_context", stage="create",
            source_file="project-context.yaml",
            produced_by="contextcore.create", data={"k": "v"},
        )
        result = extend_inventory(tmp_path, [entry])
        assert result is True
        prov = json.loads((tmp_path / "run-provenance.json").read_text())
        assert prov["version"] == "2.0.0"
        assert len(prov["artifact_inventory"]) == 1
        assert prov["artifact_inventory"][0]["artifact_id"] == "create.project_context"

    def test_extends_existing_inventory(self, tmp_path):
        """Appends to existing artifact_inventory."""
        # Pre-seed with one entry
        seed = {
            "version": "2.0.0",
            "artifact_inventory": [
                {"artifact_id": "create.project_context", "role": "project_context"}
            ],
        }
        (tmp_path / "run-provenance.json").write_text(json.dumps(seed))

        new_entry = build_inventory_entry(
            role="polish_report", stage="polish",
            source_file="polish-report.json",
            produced_by="contextcore.polish", data={"x": 1},
        )
        extend_inventory(tmp_path, [new_entry])
        prov = json.loads((tmp_path / "run-provenance.json").read_text())
        assert len(prov["artifact_inventory"]) == 2

    def test_deduplicates_by_artifact_id(self, tmp_path):
        """Existing entries win on artifact_id collision."""
        seed = {
            "version": "2.0.0",
            "artifact_inventory": [
                {"artifact_id": "create.project_context", "role": "project_context", "marker": "original"}
            ],
        }
        (tmp_path / "run-provenance.json").write_text(json.dumps(seed))

        dup_entry = build_inventory_entry(
            role="project_context", stage="create",
            source_file="project-context.yaml",
            produced_by="contextcore.create", data={"new": True},
        )
        extend_inventory(tmp_path, [dup_entry])
        prov = json.loads((tmp_path / "run-provenance.json").read_text())
        assert len(prov["artifact_inventory"]) == 1
        assert prov["artifact_inventory"][0].get("marker") == "original"

    def test_upgrades_v1_to_v2(self, tmp_path):
        """Upgrades v1 provenance to v2."""
        seed = {"version": "1.0.0", "workflow": "manifest export"}
        (tmp_path / "run-provenance.json").write_text(json.dumps(seed))

        entry = build_inventory_entry(
            role="polish_report", stage="polish",
            source_file="polish-report.json",
            produced_by="contextcore.polish", data={"x": 1},
        )
        extend_inventory(tmp_path, [entry])
        prov = json.loads((tmp_path / "run-provenance.json").read_text())
        assert prov["version"] == "2.0.0"
        assert prov["workflow"] == "manifest export"  # preserved
        assert len(prov["artifact_inventory"]) == 1

    def test_handles_malformed_json(self, tmp_path):
        """Malformed JSON is treated as empty payload."""
        (tmp_path / "run-provenance.json").write_text("not json {{{")
        entry = build_inventory_entry(
            role="project_context", stage="create",
            source_file="project-context.yaml",
            produced_by="contextcore.create", data={"k": "v"},
        )
        result = extend_inventory(tmp_path, [entry])
        assert result is True
        prov = json.loads((tmp_path / "run-provenance.json").read_text())
        assert prov["version"] == "2.0.0"
        assert len(prov["artifact_inventory"]) == 1

    def test_creates_output_dir_if_missing(self, tmp_path):
        """Creates output directory tree if it doesn't exist."""
        nested = tmp_path / "a" / "b" / "c"
        entry = build_inventory_entry(
            role="project_context", stage="create",
            source_file="project-context.yaml",
            produced_by="contextcore.create", data={"k": "v"},
        )
        extend_inventory(nested, [entry])
        assert (nested / "run-provenance.json").exists()


class TestExportProvenanceV2Integration:
    """Tests that export writes v2 provenance with inventory."""

    def test_build_run_provenance_v2_with_inventory(self):
        from contextcore.utils.provenance import build_run_provenance_payload

        inventory = [
            {
                "artifact_id": "export.derivation_rules",
                "role": "derivation_rules",
                "sha256": "abc123",
            }
        ]
        payload = build_run_provenance_payload(
            workflow_or_command="manifest export",
            inputs=[],
            outputs=[],
            artifact_inventory=inventory,
        )
        assert payload["version"] == "2.0.0"
        assert payload["artifact_inventory"] == inventory

    def test_build_run_provenance_v1_without_inventory(self):
        from contextcore.utils.provenance import build_run_provenance_payload

        payload = build_run_provenance_payload(
            workflow_or_command="manifest export",
            inputs=[],
            outputs=[],
        )
        assert payload["version"] == "1.0.0"
        assert "artifact_inventory" not in payload
