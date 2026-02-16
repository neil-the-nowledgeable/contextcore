"""Tests for contextcore create --output-dir inventory integration."""

import json

import pytest
import yaml
from click.testing import CliRunner

from contextcore.cli.core import create


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "create-out"


class TestCreateOutputDir:
    def test_writes_project_context_yaml(self, runner, output_dir):
        """--output-dir produces project-context.yaml."""
        result = runner.invoke(
            create,
            ["--name", "test-ctx", "--project", "testproj", "--output-dir", str(output_dir)],
        )
        assert result.exit_code == 0, result.output
        pc_file = output_dir / "project-context.yaml"
        assert pc_file.exists()
        data = yaml.safe_load(pc_file.read_text())
        assert data["kind"] == "ProjectContext"
        assert data["metadata"]["name"] == "test-ctx"

    def test_creates_inventory_entry(self, runner, output_dir):
        """--output-dir registers create.project_context in run-provenance.json."""
        result = runner.invoke(
            create,
            ["--name", "test-ctx", "--project", "testproj", "--output-dir", str(output_dir)],
        )
        assert result.exit_code == 0, result.output
        prov_file = output_dir / "run-provenance.json"
        assert prov_file.exists()
        payload = json.loads(prov_file.read_text())
        assert payload["version"] == "2.0.0"
        ids = [e["artifact_id"] for e in payload["artifact_inventory"]]
        assert "create.project_context" in ids

    def test_inventory_entry_has_correct_fields(self, runner, output_dir):
        """Inventory entry has role, stage, consumers, etc."""
        runner.invoke(
            create,
            ["--name", "test-ctx", "--project", "testproj", "--output-dir", str(output_dir)],
        )
        payload = json.loads((output_dir / "run-provenance.json").read_text())
        entry = payload["artifact_inventory"][0]
        assert entry["role"] == "project_context"
        assert entry["stage"] == "create"
        assert entry["produced_by"] == "contextcore.create"
        assert "contextcore.manifest.export" in entry["consumers"]
