"""Tests for contract YAML loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from contextcore.contracts.propagation.loader import ContractLoader


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the loader cache before each test."""
    ContractLoader.clear_cache()
    yield
    ContractLoader.clear_cache()


MINIMAL_CONTRACT_YAML = textwrap.dedent("""\
    schema_version: "0.1.0"
    pipeline_id: test-pipeline
    phases:
      plan:
        entry:
          required:
            - name: project_root
              type: str
              severity: blocking
        exit:
          required:
            - name: tasks
              type: list
              severity: blocking
""")


class TestContractLoader:
    def test_load_from_string(self):
        loader = ContractLoader()
        contract = loader.load_from_string(MINIMAL_CONTRACT_YAML)
        assert contract.pipeline_id == "test-pipeline"
        assert "plan" in contract.phases
        assert len(contract.phases["plan"].entry.required) == 1

    def test_load_from_file(self, tmp_path: Path):
        contract_file = tmp_path / "test.contract.yaml"
        contract_file.write_text(MINIMAL_CONTRACT_YAML)

        loader = ContractLoader()
        contract = loader.load(contract_file)
        assert contract.pipeline_id == "test-pipeline"

    def test_load_caches_result(self, tmp_path: Path):
        contract_file = tmp_path / "test.contract.yaml"
        contract_file.write_text(MINIMAL_CONTRACT_YAML)

        loader = ContractLoader()
        c1 = loader.load(contract_file)
        c2 = loader.load(contract_file)
        assert c1 is c2  # Same object from cache

    def test_load_missing_file(self):
        loader = ContractLoader()
        with pytest.raises(FileNotFoundError, match="Contract file not found"):
            loader.load(Path("/nonexistent/contract.yaml"))

    def test_load_invalid_yaml_schema(self, tmp_path: Path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("schema_version: '0.1.0'\npipeline_id: test\n")
        loader = ContractLoader()
        with pytest.raises(ValidationError):
            loader.load(bad_yaml)

    def test_load_malformed_yaml(self, tmp_path: Path):
        bad_yaml = tmp_path / "malformed.yaml"
        bad_yaml.write_text(": : :\n  invalid yaml [[[")
        loader = ContractLoader()
        with pytest.raises(Exception):
            loader.load(bad_yaml)

    def test_load_with_propagation_chains(self):
        yaml_str = textwrap.dedent("""\
            schema_version: "0.1.0"
            pipeline_id: chain-test
            phases:
              plan:
                exit:
                  required:
                    - name: domain
                      type: str
                      severity: blocking
              implement:
                entry:
                  enrichment:
                    - name: domain
                      type: str
                      severity: warning
                      default: "unknown"
            propagation_chains:
              - chain_id: domain_flow
                source:
                  phase: plan
                  field: domain
                destination:
                  phase: implement
                  field: domain
                severity: warning
        """)
        loader = ContractLoader()
        contract = loader.load_from_string(yaml_str)
        assert len(contract.propagation_chains) == 1
        assert contract.propagation_chains[0].chain_id == "domain_flow"
