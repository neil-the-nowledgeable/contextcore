import json
import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from contextcore.cli.export_io_ops import resolve_export_output_paths
from contextcore.utils.provenance import get_file_fingerprint, build_run_provenance_payload

class TestExportPathResolution:
    def test_default_output_dir(self):
        """Should resolve to './out' by default."""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            manifest = cwd / "contextcore.yaml"
            manifest.touch()
            
            original_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                paths = resolve_export_output_paths(
                    manifest_path=str(manifest),
                    output_arg=None
                )
                
                # Resolve paths to handle symlinks (e.g. macOS /var -> /private/var)
                actual = Path(paths["base_dir"]).resolve()
                expected = (cwd / "out").resolve()
                
                assert str(actual) == str(expected)
                assert str(paths["onboarding_metadata"]).endswith("onboarding-metadata.json")
            finally:
                os.chdir(original_cwd)

    def test_explicit_output_dir(self):
        """Should respect explicit output directory."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "custom-export"
            manifest = Path(tmp) / "manifest.yaml"
            
            paths = resolve_export_output_paths(
                manifest_path=str(manifest),
                output_arg=str(output_dir)
            )
            
            assert paths["base_dir"] == str(output_dir)

class TestRunProvenancePayload:
    def test_payload_structure(self):
        """Should include all required provenance fields."""
        payload = build_run_provenance_payload(
            workflow_or_command="test-command",
            inputs=["in.yaml"],
            outputs=["out.json"],
            config_snapshot={"strict": True}
        )
        
        assert payload["workflow_or_command"] == "test-command"
        assert "run_id" in payload
        assert "started_at" in payload # Was "timestamp_start" in test but code uses "started_at"
        assert "environment" in payload
        assert payload["config_snapshot"]["strict"] is True # Code uses "config_snapshot" key for config

        
    def test_fingerprinting(self):
        """Should calculate correct file fingerprints."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.txt"
            p.write_text("content")
            
            fp = get_file_fingerprint(p)
            
            assert fp["exists"] is True
            assert fp["sha256"] is not None
            assert fp["path"] == str(p)

    def test_missing_file_fingerprint(self):
        """Should handle missing files gracefully."""
        fp = get_file_fingerprint("nonexistent.txt")
        assert fp["exists"] is False
        assert fp["sha256"] is None

    def test_capability_index_version_included(self):
        """Should include capability_index when version provided (REQ-CAP-009)."""
        payload = build_run_provenance_payload(
            workflow_or_command="manifest export",
            inputs=[],
            outputs=[],
            capability_index_version="1.10.1",
        )
        assert "capability_index" in payload
        assert payload["capability_index"]["version"] == "1.10.1"

    def test_capability_index_version_omitted(self):
        """Should omit capability_index when version not provided."""
        payload = build_run_provenance_payload(
            workflow_or_command="manifest export",
            inputs=[],
            outputs=[],
        )
        assert "capability_index" not in payload
