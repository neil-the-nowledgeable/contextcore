import json
import tempfile
import sys
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest
from click.testing import CliRunner
from contextcore.cli.core import generate

class TestGenerateProvenance:
    @patch("contextcore.cli.core._run_kubectl")
    @patch("contextcore.cli.core.generate_service_monitor")
    def test_generate_emits_provenance(self, mock_gen_sm, mock_kubectl):
        """Should emit run-provenance.json on successful generation."""
        runner = CliRunner()
        
        # Mock kubectl output
        mock_kubectl.return_value = (json.dumps({
            "spec": {
                "project": {"id": "test-proj"},
                "targets": [{"kind": "Deployment", "name": "app"}],
                "business": {"criticality": "high"},
                "requirements": {"availability": "99.9%"}
            }
        }), "")
        
        # Mock generator output
        mock_gen_sm.return_value = {"kind": "ServiceMonitor", "metadata": {"name": "app"}}
        
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            
            result = runner.invoke(generate, [
                "--context", "test-proj",
                "--output", str(output_dir),
                "--service-monitor",
                "--strict-quality" # Should imply --emit-run-provenance
            ])
            
            assert result.exit_code == 0
            
            prov_file = output_dir / "run-provenance.json"
            assert prov_file.exists()
            
            prov_data = json.loads(prov_file.read_text())
            assert prov_data["workflow_or_command"] == "contextcore generate"
            
            # Check outputs
            output_paths = [o["path"] for o in prov_data["outputs"]]
            assert any("test-proj-service-monitor.yaml" in p for p in output_paths)
            assert any("generation-report.json" in p for p in output_paths)
            
            # Check config
            assert prov_data["config_snapshot"]["context"] == "test-proj"
