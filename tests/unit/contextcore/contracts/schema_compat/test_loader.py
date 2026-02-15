"""Tests for schema compatibility contract YAML loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from contextcore.contracts.schema_compat.loader import SchemaCompatLoader


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the loader cache before each test."""
    SchemaCompatLoader.clear_cache()
    yield
    SchemaCompatLoader.clear_cache()


MINIMAL_YAML = textwrap.dedent("""\
    schema_version: "0.1.0"
    contract_type: schema_compatibility
""")

FULL_YAML = textwrap.dedent("""\
    schema_version: "0.1.0"
    contract_type: schema_compatibility
    description: Cross-service schema compat
    mappings:
      - source_service: tracker
        source_field: task.status
        source_values: [todo, in_progress, done]
        target_service: exporter
        target_field: status
        target_values: [pending, active, complete]
        mapping:
          todo: pending
          in_progress: active
          done: complete
        severity: blocking
        description: Task status mapping
    evolution_rules:
      - rule_id: tracker-additive
        scope: tracker
        policy: additive_only
    versions:
      - service: tracker
        version: "1.0.0"
        fields:
          task_id: str
          status: str
""")


class TestSchemaCompatLoader:
    def test_load_from_string_minimal(self):
        loader = SchemaCompatLoader()
        spec = loader.load_from_string(MINIMAL_YAML)
        assert spec.schema_version == "0.1.0"
        assert spec.mappings == []

    def test_load_from_string_full(self):
        loader = SchemaCompatLoader()
        spec = loader.load_from_string(FULL_YAML)
        assert len(spec.mappings) == 1
        assert spec.mappings[0].source_service == "tracker"
        assert len(spec.evolution_rules) == 1
        assert len(spec.versions) == 1

    def test_load_from_file(self, tmp_path: Path):
        contract_file = tmp_path / "compat.yaml"
        contract_file.write_text(FULL_YAML)

        loader = SchemaCompatLoader()
        spec = loader.load(contract_file)
        assert spec.schema_version == "0.1.0"
        assert len(spec.mappings) == 1

    def test_cache_hit(self, tmp_path: Path):
        contract_file = tmp_path / "compat.yaml"
        contract_file.write_text(MINIMAL_YAML)

        loader = SchemaCompatLoader()
        s1 = loader.load(contract_file)
        s2 = loader.load(contract_file)
        assert s1 is s2

    def test_cache_clear(self, tmp_path: Path):
        contract_file = tmp_path / "compat.yaml"
        contract_file.write_text(MINIMAL_YAML)

        loader = SchemaCompatLoader()
        s1 = loader.load(contract_file)
        SchemaCompatLoader.clear_cache()
        s2 = loader.load(contract_file)
        assert s1 is not s2

    def test_file_not_found(self):
        loader = SchemaCompatLoader()
        with pytest.raises(FileNotFoundError, match="Contract file not found"):
            loader.load(Path("/nonexistent/compat.yaml"))

    def test_validation_error_on_bad_schema(self, tmp_path: Path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("schema_version: '0.1.0'\ncontract_type: wrong\n")
        loader = SchemaCompatLoader()
        with pytest.raises(ValidationError):
            loader.load(bad_file)

    def test_malformed_yaml(self, tmp_path: Path):
        bad_file = tmp_path / "malformed.yaml"
        bad_file.write_text(": : :\n  invalid yaml [[[")
        loader = SchemaCompatLoader()
        with pytest.raises(Exception):
            loader.load(bad_file)
