"""
Tests for content-level verification gate functions.

Verifies placeholder scanning, schema field verification, import consistency,
and protocol coherence checks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contextcore.contracts.a2a.models import GateOutcome
from contextcore.contracts.a2a.content_verification import (
    ContentVerifier,
    scan_placeholders,
    verify_schema_fields,
    verify_import_consistency,
    verify_protocol_coherence,
)


# ===========================================================================
# Tests — Placeholder scan
# ===========================================================================


class TestPlaceholderScan:
    """Test the scan_placeholders gate function."""

    def test_clean_source_passes(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("import os\nprint('hello')\n")

        result = scan_placeholders(
            gate_id="test-placeholders",
            task_id="T-001",
            source_dir=str(src),
        )
        assert result.result == GateOutcome.PASS
        assert result.blocking is False

    def test_todo_detected(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("# TODO: fix this later\nprint('hello')\n")

        result = scan_placeholders(
            gate_id="test-placeholders",
            task_id="T-001",
            source_dir=str(src),
        )
        assert result.result == GateOutcome.FAIL
        assert result.blocking is True
        assert any("TODO:" in e.description for e in (result.evidence or []))

    def test_fixme_detected(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "helper.py").write_text("x = 1  # FIXME: bad name\n")

        result = scan_placeholders(
            gate_id="test-placeholders",
            task_id="T-001",
            source_dir=str(src),
        )
        assert result.result == GateOutcome.FAIL

    def test_replace_with_detected(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "config.py").write_text("API_KEY = 'REPLACE_WITH_REAL_KEY'\n")

        result = scan_placeholders(
            gate_id="test-placeholders",
            task_id="T-001",
            source_dir=str(src),
        )
        assert result.result == GateOutcome.FAIL
        assert any("REPLACE_WITH" in e.description for e in (result.evidence or []))

    def test_custom_patterns(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("value = CHANGEME_LATER\n")

        result = scan_placeholders(
            gate_id="test-placeholders",
            task_id="T-001",
            source_dir=str(src),
            extra_patterns=[r"\bCHANGEME_\w+"],
        )
        assert result.result == GateOutcome.FAIL

    def test_multi_file_scan(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("# TODO: file a\n")
        (src / "b.py").write_text("# FIXME: file b\n")
        (src / "c.py").write_text("clean file\n")

        result = scan_placeholders(
            gate_id="test-placeholders",
            task_id="T-001",
            source_dir=str(src),
        )
        assert result.result == GateOutcome.FAIL
        assert len(result.evidence or []) >= 2

    def test_empty_directory_passes(self, tmp_path: Path):
        src = tmp_path / "empty"
        src.mkdir()

        result = scan_placeholders(
            gate_id="test-placeholders",
            task_id="T-001",
            source_dir=str(src),
        )
        assert result.result == GateOutcome.PASS

    def test_nonexistent_directory_passes(self, tmp_path: Path):
        result = scan_placeholders(
            gate_id="test-placeholders",
            task_id="T-001",
            source_dir=str(tmp_path / "nonexistent"),
        )
        assert result.result == GateOutcome.PASS


# ===========================================================================
# Tests — Schema field verification
# ===========================================================================


class TestSchemaFieldVerification:
    """Test the verify_schema_fields gate function."""

    def _write_proto(self, tmp_path: Path) -> Path:
        proto = tmp_path / "demo.proto"
        proto.write_text(
            'syntax = "proto3";\n'
            "message Product {\n"
            "  string product_id = 1;\n"
            "  string product_name = 2;\n"
            "  int32 quantity_available = 3;\n"
            "}\n"
        )
        return proto

    def test_correct_field_names_pass(self, tmp_path: Path):
        proto = self._write_proto(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "client.py").write_text(
            "item.product_id = '123'\n"
            "item.product_name = 'Widget'\n"
        )

        result = verify_schema_fields(
            gate_id="test-schema",
            task_id="T-001",
            source_dir=str(src),
            proto_path=str(proto),
        )
        assert result.result == GateOutcome.PASS

    def test_camelcase_mismatch_detected(self, tmp_path: Path):
        proto = self._write_proto(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        # Uses camelCase productId instead of product_id, without also having product_id
        (src / "client.py").write_text(
            "item.productId = '123'\n"
        )

        result = verify_schema_fields(
            gate_id="test-schema",
            task_id="T-001",
            source_dir=str(src),
            proto_path=str(proto),
        )
        assert result.result == GateOutcome.FAIL
        assert any("productId" in e.description for e in (result.evidence or []))

    def test_nonexistent_proto_graceful(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("print('hello')\n")

        result = verify_schema_fields(
            gate_id="test-schema",
            task_id="T-001",
            source_dir=str(src),
            proto_path=str(tmp_path / "nonexistent.proto"),
        )
        # Should pass with warning, not crash
        assert result.result == GateOutcome.PASS
        assert result.severity.value == "warning"

    def test_both_correct_and_camel_present(self, tmp_path: Path):
        """When both snake_case and camelCase are present, don't flag."""
        proto = self._write_proto(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "client.py").write_text(
            "# proto field: product_id\n"
            "item.product_id = '123'\n"
            "# Also used as productId in JSON serialization\n"
            "json_data = {'productId': item.product_id}\n"
        )

        result = verify_schema_fields(
            gate_id="test-schema",
            task_id="T-001",
            source_dir=str(src),
            proto_path=str(proto),
        )
        assert result.result == GateOutcome.PASS


# ===========================================================================
# Tests — Import consistency
# ===========================================================================


class TestImportConsistency:
    """Test the verify_import_consistency gate function."""

    def test_all_present_pass(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text(
            "import grpc\n"
            "import flask\n"
            "import os\n"
        )
        req = tmp_path / "requirements.in"
        req.write_text("grpcio>=1.0\nflask>=2.0\n")

        result = verify_import_consistency(
            gate_id="test-imports",
            task_id="T-001",
            source_dir=str(src),
            manifest_path=str(req),
        )
        assert result.result == GateOutcome.PASS

    def test_missing_dep_fails(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text(
            "import grpc\n"
            "import flask\n"
            "import redis\n"
        )
        req = tmp_path / "requirements.in"
        req.write_text("grpcio>=1.0\nflask>=2.0\n")

        result = verify_import_consistency(
            gate_id="test-imports",
            task_id="T-001",
            source_dir=str(src),
            manifest_path=str(req),
        )
        assert result.result == GateOutcome.FAIL
        assert any("redis" in e.ref for e in (result.evidence or []))

    def test_stdlib_excluded(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text(
            "import os\n"
            "import sys\n"
            "import json\n"
            "import hashlib\n"
            "import logging\n"
        )
        req = tmp_path / "requirements.in"
        req.write_text("# no third-party deps\n")

        result = verify_import_consistency(
            gate_id="test-imports",
            task_id="T-001",
            source_dir=str(src),
            manifest_path=str(req),
        )
        assert result.result == GateOutcome.PASS

    def test_go_mod_stub(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.go").write_text("package main\n")
        gomod = tmp_path / "go.mod"
        gomod.write_text("module example.com/test\n")

        result = verify_import_consistency(
            gate_id="test-imports",
            task_id="T-001",
            source_dir=str(src),
            manifest_path=str(gomod),
        )
        assert result.result == GateOutcome.PASS
        assert "stub" in result.reason

    def test_unknown_manifest_skipped(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        manifest = tmp_path / "Cargo.toml"
        manifest.write_text("[package]\n")

        result = verify_import_consistency(
            gate_id="test-imports",
            task_id="T-001",
            source_dir=str(src),
            manifest_path=str(manifest),
        )
        assert result.result == GateOutcome.PASS
        assert "Unrecognized" in result.reason

    def test_local_module_excluded(self, tmp_path: Path):
        """Local project modules should not be flagged as missing deps."""
        src = tmp_path / "src"
        src.mkdir()
        pkg = src / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "utils.py").write_text("def helper(): pass\n")
        (src / "main.py").write_text("import mypackage\nfrom mypackage import utils\n")

        req = tmp_path / "requirements.in"
        req.write_text("# no third-party deps\n")

        result = verify_import_consistency(
            gate_id="test-imports",
            task_id="T-001",
            source_dir=str(src),
            manifest_path=str(req),
        )
        assert result.result == GateOutcome.PASS


# ===========================================================================
# Tests — Protocol coherence
# ===========================================================================


class TestProtocolCoherence:
    """Test the verify_protocol_coherence gate function."""

    def test_grpc_with_grpc_pass(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "server.py").write_text(
            "import grpc\n"
            "server = grpc.server(futures.ThreadPoolExecutor())\n"
            "add_GreeterServicer_to_server(servicer, server)\n"
        )

        result = verify_protocol_coherence(
            gate_id="test-protocol",
            task_id="T-001",
            source_dir=str(src),
            transport_protocol="grpc",
        )
        assert result.result == GateOutcome.PASS

    def test_grpc_with_http_fail(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "client.py").write_text(
            "import requests\n"
            "response = requests.get('http://service/api')\n"
        )

        result = verify_protocol_coherence(
            gate_id="test-protocol",
            task_id="T-001",
            source_dir=str(src),
            transport_protocol="grpc",
        )
        assert result.result == GateOutcome.FAIL
        assert any("requests" in e.description for e in (result.evidence or []))

    def test_http_with_grpc_fail(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "Dockerfile").write_text(
            "FROM python:3.12-slim\n"
            "COPY grpc_health_probe /bin/grpc_health_probe\n"
            "HEALTHCHECK CMD /bin/grpc_health_probe -addr=:8080\n"
        )

        result = verify_protocol_coherence(
            gate_id="test-protocol",
            task_id="T-001",
            source_dir=str(src),
            transport_protocol="http",
        )
        assert result.result == GateOutcome.FAIL
        assert any("grpc_health_probe" in e.description for e in (result.evidence or []))

    def test_http_with_http_pass(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
        )

        result = verify_protocol_coherence(
            gate_id="test-protocol",
            task_id="T-001",
            source_dir=str(src),
            transport_protocol="http",
        )
        # Flask is an HTTP indicator, but that's *expected* for HTTP services
        # The check only flags cross-protocol mismatches
        assert result.result == GateOutcome.PASS

    def test_empty_directory_passes(self, tmp_path: Path):
        src = tmp_path / "empty"
        src.mkdir()

        result = verify_protocol_coherence(
            gate_id="test-protocol",
            task_id="T-001",
            source_dir=str(src),
            transport_protocol="grpc",
        )
        assert result.result == GateOutcome.PASS


# ===========================================================================
# Tests — ContentVerifier wrapper
# ===========================================================================


class TestContentVerifier:
    """Test the ContentVerifier convenience class."""

    def test_accumulation(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("print('clean')\n")

        verifier = ContentVerifier(trace_id="test-trace")
        verifier.scan_placeholders(task_id="T-001", source_dir=str(src))
        verifier.verify_protocol_coherence(
            task_id="T-001", source_dir=str(src), transport_protocol="grpc",
        )

        assert len(verifier.results) == 2
        assert verifier.all_passed is True
        assert verifier.has_blocking_failure is False

    def test_blocking_failure_detected(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("# TODO: fix this\n")

        verifier = ContentVerifier(trace_id="test-trace")
        verifier.scan_placeholders(task_id="T-001", source_dir=str(src))

        assert verifier.has_blocking_failure is True
        assert len(verifier.blocking_failures) == 1

    def test_summary(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("print('clean')\n")

        verifier = ContentVerifier(trace_id="test-trace")
        verifier.scan_placeholders(task_id="T-001", source_dir=str(src))

        summary = verifier.summary()
        assert summary["total_gates"] == 1
        assert summary["passed"] == 1
        assert summary["failed"] == 0
        assert summary["all_passed"] is True

    def test_trace_id_propagated(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("clean\n")

        verifier = ContentVerifier(trace_id="my-trace-id")
        verifier.scan_placeholders(task_id="T-001", source_dir=str(src))

        assert verifier.results[0].trace_id == "my-trace-id"
