import json
from pathlib import Path

from contextcore.cli.export_io_ops import write_export_outputs


def _sample_provenance_dict() -> dict:
    return {
        "generatedAt": "2026-02-14T00:00:00Z",
        "sourcePath": "/tmp/source/.contextcore.yaml",
        "sourceChecksum": "abc123",
        "contextcoreVersion": "2.0.0",
        "outputDirectory": "/tmp/out",
        "outputFiles": ["artifact.yaml"],
        "cliOptions": {},
    }


def test_export_writes_run_provenance_and_bridge(tmp_path: Path):
    output_files: list[str] = ["proj-projectcontext.yaml", "proj-artifact-manifest.yaml"]
    result = write_export_outputs(
        output_path=tmp_path,
        crd_filename="proj-projectcontext.yaml",
        crd_yaml="apiVersion: v1\nkind: ConfigMap\n",
        artifact_filename="proj-artifact-manifest.yaml",
        artifact_content="apiVersion: contextcore.io/v1\n",
        emit_provenance=True,
        provenance=_sample_provenance_dict(),
        emit_onboarding=True,
        onboarding_metadata={"project_id": "proj"},
        validation_report={"coverage": {"meets_minimum": True}},
        emit_quality_report=True,
        quality_report={"strict_quality": True, "gates": {"coverage_meets_minimum": True}},
        output_files=output_files,
        run_provenance_inputs=[str(tmp_path / "source.yaml")],
        document_write_strategy="update_existing",
        emit_run_provenance=True,
    )

    run_prov_path = Path(result["run_provenance_file"])
    assert run_prov_path.exists()
    run_prov = json.loads(run_prov_path.read_text(encoding="utf-8"))
    assert run_prov["workflow_or_command"] == "manifest export"
    assert "artifact_references" in run_prov
    assert run_prov["artifact_references"]["provenance_json_path"].endswith("provenance.json")

    prov_path = Path(result["provenance_file"])
    assert prov_path.exists()
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    assert "cliOptions" in prov
    assert prov["cliOptions"]["run_provenance_path"].endswith("run-provenance.json")


def test_export_can_skip_run_provenance(tmp_path: Path):
    output_files: list[str] = ["proj-projectcontext.yaml", "proj-artifact-manifest.yaml"]
    result = write_export_outputs(
        output_path=tmp_path,
        crd_filename="proj-projectcontext.yaml",
        crd_yaml="apiVersion: v1\nkind: ConfigMap\n",
        artifact_filename="proj-artifact-manifest.yaml",
        artifact_content="apiVersion: contextcore.io/v1\n",
        emit_provenance=False,
        provenance=None,
        emit_onboarding=False,
        onboarding_metadata={},
        validation_report={"coverage": {"meets_minimum": True}},
        emit_quality_report=False,
        quality_report={},
        output_files=output_files,
        run_provenance_inputs=[],
        document_write_strategy="update_existing",
        emit_run_provenance=False,
    )

    assert result["run_provenance_file"] is None
    assert not (tmp_path / "run-provenance.json").exists()
