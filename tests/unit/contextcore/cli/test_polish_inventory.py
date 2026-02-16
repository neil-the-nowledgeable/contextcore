"""Tests for contextcore polish --output-dir inventory integration."""

import json

import pytest
from click.testing import CliRunner

from contextcore.cli.polish import polish


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def plan_file(tmp_path):
    """A minimal plan that passes polish checks."""
    content = """\
# Test Plan

## Overview

**Objectives:** Test objectives here.

**Goals:**
- Goal 1

## Functional Requirements

- FR-001: Requirement

## Risks

- Risk 1

## Validation

- Test 1
"""
    f = tmp_path / "test-plan.md"
    f.write_text(content)
    return f


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "polish-out"


class TestPolishOutputDir:
    def test_writes_polish_report_json(self, runner, plan_file, output_dir):
        """--output-dir produces polish-report.json."""
        result = runner.invoke(
            polish,
            [str(plan_file), "--output-dir", str(output_dir)],
        )
        assert result.exit_code == 0, result.output
        report_file = output_dir / "polish-report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert "summary" in data[0]

    def test_creates_inventory_entry(self, runner, plan_file, output_dir):
        """--output-dir registers polish.polish_report in run-provenance.json."""
        result = runner.invoke(
            polish,
            [str(plan_file), "--output-dir", str(output_dir)],
        )
        assert result.exit_code == 0, result.output
        prov_file = output_dir / "run-provenance.json"
        assert prov_file.exists()
        payload = json.loads(prov_file.read_text())
        assert payload["version"] == "2.0.0"
        ids = [e["artifact_id"] for e in payload["artifact_inventory"]]
        assert "polish.polish_report" in ids

    def test_extend_accumulates_with_create(self, runner, plan_file, output_dir):
        """Polish extends inventory that create already wrote."""
        from contextcore.cli.core import create as create_cmd

        # Run create first
        runner.invoke(
            create_cmd,
            ["--name", "ctx", "--project", "proj", "--output-dir", str(output_dir)],
        )
        # Then polish into same dir
        result = runner.invoke(
            polish,
            [str(plan_file), "--output-dir", str(output_dir)],
        )
        assert result.exit_code == 0, result.output

        payload = json.loads((output_dir / "run-provenance.json").read_text())
        ids = [e["artifact_id"] for e in payload["artifact_inventory"]]
        assert "create.project_context" in ids
        assert "polish.polish_report" in ids
        assert len(ids) == 2

    def test_inventory_entry_has_correct_fields(self, runner, plan_file, output_dir):
        """Inventory entry has role, stage, consumers, etc."""
        runner.invoke(
            polish,
            [str(plan_file), "--output-dir", str(output_dir)],
        )
        payload = json.loads((output_dir / "run-provenance.json").read_text())
        entry = payload["artifact_inventory"][0]
        assert entry["role"] == "polish_report"
        assert entry["stage"] == "polish"
        assert entry["produced_by"] == "contextcore.polish"
        assert "artisan.review" in entry["consumers"]
