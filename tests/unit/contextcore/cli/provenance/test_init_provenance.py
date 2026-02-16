import json
import tempfile
from pathlib import Path
import pytest
from click.testing import CliRunner
from contextcore.cli.manifest import init, init_from_plan

class TestManifestInitProvenance:
    def test_init_emits_provenance(self):
        """Should emit init-run-provenance.json on successful init."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            output_file = cwd / ".contextcore.yaml"
            
            result = runner.invoke(init, [
                "--path", str(output_file),
                "--name", "test-project",
                "--no-validate"  # Skip validation for speed/mocking
            ])
            
            assert result.exit_code == 0
            assert output_file.exists()
            
            prov_file = cwd / "init-run-provenance.json"
            assert prov_file.exists()
            
            prov_data = json.loads(prov_file.read_text())
            assert prov_data["workflow_or_command"] == "manifest init"
            assert "run_id" in prov_data
            assert prov_data["outputs"][0]["path"] == str(output_file.resolve())

    def test_init_from_plan_emits_provenance(self):
        """Should emit init-run-provenance.json with plan inputs."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plan_file = cwd / "PLAN.md"
            plan_file.write_text("# Plan\n\n## Overview\nTest plan.")
            output_file = cwd / ".contextcore.yaml"
            report_file = cwd / "report.json"
            
            result = runner.invoke(init_from_plan, [
                "--plan", str(plan_file),
                "--output", str(output_file),
                "--report-out", str(report_file),
                "--no-strict-quality", # Avoid failing on low inference count
                "--no-validate"
            ])
            
            assert result.exit_code == 0
            
            prov_file = cwd / "init-run-provenance.json"
            assert prov_file.exists()
            
            prov_data = json.loads(prov_file.read_text())
            assert prov_data["workflow_or_command"] == "manifest init-from-plan"
            
            # Check inputs
            input_paths = [i["path"] for i in prov_data["inputs"]]
            assert str(plan_file.resolve()) in input_paths
            
            # Check outputs
            output_paths = [o["path"] for o in prov_data["outputs"]]
            assert str(output_file.resolve()) in output_paths
            assert str(report_file.resolve()) in output_paths
