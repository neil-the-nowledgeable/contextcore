"""Tests for service communication graph extraction (REQ-CCL-100–201, REQ-SIG-100–104)."""

from __future__ import annotations

import pytest

from contextcore.cli.init_from_plan_ops import (
    _extract_service_communication_graph,
    infer_init_from_plan,
    build_v2_manifest_template,
)


# ---------------------------------------------------------------------------
# Sample plan text fixtures
# ---------------------------------------------------------------------------

PLAN_WITH_SERVICES = """\
# Online Boutique Microservices

## Overview

A 10-service gRPC microservices demo application.

### F-002a: Email Service — gRPC Server

Target: `src/emailservice/main.py`

This service sends order confirmation emails.
Imports: `demo_pb2`, `demo_pb2_grpc`

### F-003: Product Catalog Service — gRPC Server

Target: `src/productcatalogservice/server.go`

Imports: `demo_pb2`, `demo_pb2_grpc`
Exposes: ListProducts, GetProduct, SearchProducts

### F-004: Frontend Service — HTTP

Target: `src/frontend/main.go`

This service handles web traffic.
It calls product_catalog_stub.ListProducts() and
currency_stub.GetSupportedCurrencies() for the home page.
Imports: `demo_pb2`, `demo_pb2_grpc`

Proto schemas are defined in protos/demo.proto.
"""

PLAN_WITHOUT_SERVICES = """\
# Simple CLI Tool

## Phase 1: Core Implementation

- Implement argument parsing
- Add output formatting

## Phase 2: Testing

- Unit tests for all modules
"""

REQUIREMENTS_TEXT = """\
REQ-001: All gRPC services must expose health checks.
REQ-002: Proto schemas must be kept in protos/ directory.
"""


# ---------------------------------------------------------------------------
# Unit tests for _extract_service_communication_graph
# ---------------------------------------------------------------------------

class TestServiceGraphExtraction:
    def test_service_name_from_heading(self):
        graph = _extract_service_communication_graph(PLAN_WITH_SERVICES, "")
        services = graph["services"]
        assert "emailservice" in services

    def test_service_name_from_target_dir(self):
        graph = _extract_service_communication_graph(PLAN_WITH_SERVICES, "")
        services = graph["services"]
        assert "productcatalogservice" in services

    def test_import_extraction(self):
        graph = _extract_service_communication_graph(PLAN_WITH_SERVICES, "")
        email_imports = graph["services"]["emailservice"]["imports"]
        assert "demo_pb2" in email_imports
        assert "demo_pb2_grpc" in email_imports

    def test_rpc_call_extraction(self):
        graph = _extract_service_communication_graph(PLAN_WITH_SERVICES, "")
        frontend = graph["services"]["frontend"]
        methods = [c["method"] for c in frontend["rpc_calls"]]
        assert "ListProducts" in methods
        targets = [c["target_service"] for c in frontend["rpc_calls"]]
        assert "product_catalog" in targets

    def test_shared_module_detection(self):
        graph = _extract_service_communication_graph(PLAN_WITH_SERVICES, "")
        shared = graph["shared_modules"]
        assert "demo_pb2" in shared
        assert len(shared["demo_pb2"]["used_by"]) >= 2
        assert shared["demo_pb2"]["type"] == "proto_stub"

    def test_grpc_signal_detection(self):
        graph = _extract_service_communication_graph(PLAN_WITH_SERVICES, "")
        # Email service has _pb2 imports + gRPC heading → protocol: grpc
        assert graph["services"]["emailservice"]["protocol"] == "grpc"

    def test_transport_protocol_from_heading(self):
        graph = _extract_service_communication_graph(PLAN_WITH_SERVICES, "")
        # Frontend has "HTTP" in heading
        assert graph["services"]["frontend"]["protocol"] in ("http", "grpc")

    def test_proto_file_detection(self):
        graph = _extract_service_communication_graph(PLAN_WITH_SERVICES, "")
        assert "protos/demo.proto" in graph["proto_schemas"]

    def test_empty_graph_backward_compat(self):
        graph = _extract_service_communication_graph(PLAN_WITHOUT_SERVICES, "")
        assert graph["services"] == {}
        assert graph["shared_modules"] == {}
        assert graph["proto_schemas"] == []

    def test_requirements_text_contributes(self):
        plan = "# Simple\n\n## Service\n\nTarget: `src/myservice/app.py`\n"
        reqs = "The service uses protos/api.proto for gRPC communication."
        graph = _extract_service_communication_graph(plan, reqs)
        assert "protos/api.proto" in graph["proto_schemas"]


# ---------------------------------------------------------------------------
# Integration test: through infer_init_from_plan
# ---------------------------------------------------------------------------

class TestGraphInInitFromPlan:
    def test_full_integration(self):
        manifest_data = build_v2_manifest_template("online-boutique")
        result = infer_init_from_plan(
            manifest_data=manifest_data,
            plan_text=PLAN_WITH_SERVICES,
            requirements_text=REQUIREMENTS_TEXT,
            project_root=None,
            emit_guidance_questions=False,
        )
        md = result["manifest_data"]
        graph = md["spec"].get("service_communication_graph")
        assert graph is not None
        assert len(graph["services"]) >= 2
        # Check inference record
        inf_fields = [i["field_path"] for i in result["inferences"]]
        assert "spec.service_communication_graph" in inf_fields

    def test_no_graph_when_no_services(self):
        manifest_data = build_v2_manifest_template("cli-tool")
        result = infer_init_from_plan(
            manifest_data=manifest_data,
            plan_text=PLAN_WITHOUT_SERVICES,
            requirements_text="",
            project_root=None,
            emit_guidance_questions=False,
        )
        md = result["manifest_data"]
        assert "service_communication_graph" not in md["spec"]
