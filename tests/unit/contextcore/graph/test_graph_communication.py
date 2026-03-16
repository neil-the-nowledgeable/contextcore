"""Tests for knowledge graph communication graph population and span emission (REQ-CCL-400–401)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from contextcore.graph.schema import NodeType, EdgeType, Graph, Node, Edge
from contextcore.graph.builder import GraphBuilder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_comm_graph():
    """Communication graph with 3 services sharing demo_pb2."""
    return {
        "services": {
            "emailservice": {
                "imports": ["demo_pb2", "demo_pb2_grpc"],
                "rpc_calls": [],
                "protocol": "grpc",
            },
            "frontend": {
                "imports": ["demo_pb2", "demo_pb2_grpc"],
                "rpc_calls": [
                    {"target_service": "productcatalogservice", "method": "ListProducts"},
                    {"target_service": "emailservice", "method": "SendEmail"},
                ],
                "protocol": "http",
            },
            "productcatalogservice": {
                "imports": ["demo_pb2", "demo_pb2_grpc"],
                "rpc_calls": [],
                "protocol": "grpc",
            },
        },
        "shared_modules": {
            "demo_pb2": {
                "type": "proto_stub",
                "used_by": ["emailservice", "frontend", "productcatalogservice"],
            },
            "demo_pb2_grpc": {
                "type": "proto_stub",
                "used_by": ["emailservice", "frontend", "productcatalogservice"],
            },
        },
        "proto_schemas": ["protos/demo.proto"],
    }


@pytest.fixture
def empty_comm_graph():
    return {"services": {}, "shared_modules": {}, "proto_schemas": []}


# ---------------------------------------------------------------------------
# GraphBuilder.populate_from_communication_graph tests
# ---------------------------------------------------------------------------

class TestPopulateFromCommunicationGraph:
    def test_creates_service_nodes(self, sample_comm_graph):
        builder = GraphBuilder()
        builder.populate_from_communication_graph(sample_comm_graph)
        node = builder.graph.get_node("service:emailservice")
        assert node is not None

    def test_creates_module_nodes(self, sample_comm_graph):
        builder = GraphBuilder()
        builder.populate_from_communication_graph(sample_comm_graph)
        node = builder.graph.get_node("module:demo_pb2")
        assert node is not None

    def test_rpc_calls_create_calls_rpc_edges(self, sample_comm_graph):
        builder = GraphBuilder()
        builder.populate_from_communication_graph(sample_comm_graph)
        edges = builder.graph.get_edges_from("service:frontend")
        rpc_edges = [e for e in edges if e.type == EdgeType.CALLS_RPC]
        targets = {e.target_id for e in rpc_edges}
        assert "service:productcatalogservice" in targets
        assert "service:emailservice" in targets

    def test_shared_modules_create_shared_by_edges(self, sample_comm_graph):
        builder = GraphBuilder()
        builder.populate_from_communication_graph(sample_comm_graph)
        edges = builder.graph.get_edges_from("module:demo_pb2")
        shared_by_edges = [e for e in edges if e.type == EdgeType.SHARED_BY]
        # 3 services share demo_pb2
        assert len(shared_by_edges) == 3

    def test_imports_edges_created(self, sample_comm_graph):
        builder = GraphBuilder()
        builder.populate_from_communication_graph(sample_comm_graph)
        edges = builder.graph.get_edges_from("service:emailservice")
        import_edges = [e for e in edges if e.type == EdgeType.IMPORTS]
        targets = {e.target_id for e in import_edges}
        assert "module:demo_pb2" in targets
        assert "module:demo_pb2_grpc" in targets

    def test_empty_graph_creates_no_nodes(self, empty_comm_graph):
        builder = GraphBuilder()
        builder.populate_from_communication_graph(empty_comm_graph)
        assert len(builder.graph.nodes) == 0
        assert len(builder.graph.edges) == 0

    def test_edge_count_for_three_services(self, sample_comm_graph):
        builder = GraphBuilder()
        builder.populate_from_communication_graph(sample_comm_graph)
        # 3 IMPORTS edges per shared module (demo_pb2 + demo_pb2_grpc) = 6 IMPORTS
        # 3 SHARED_BY per module = 6 SHARED_BY
        # 2 CALLS_RPC from frontend
        import_edges = [e for e in builder.graph.edges if e.type == EdgeType.IMPORTS]
        shared_edges = [e for e in builder.graph.edges if e.type == EdgeType.SHARED_BY]
        rpc_edges = [e for e in builder.graph.edges if e.type == EdgeType.CALLS_RPC]
        assert len(import_edges) == 6
        assert len(shared_edges) == 6
        assert len(rpc_edges) == 2


# ---------------------------------------------------------------------------
# Span emission tests
# ---------------------------------------------------------------------------

class TestServiceDependencySpanEmission:
    def test_span_emission_attributes(self, sample_comm_graph):
        from contextcore.graph.emitter import emit_service_dependency_spans

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        count = emit_service_dependency_spans(sample_comm_graph, tracer=mock_tracer)

        # 2 RPC calls + 6 shared module usages = 8 spans
        assert count == 8
        # Check that span names are correct
        calls = mock_tracer.start_as_current_span.call_args_list
        for call in calls:
            assert call[0][0] == "contextcore.service_dependency"
            attrs = call[1].get("attributes", {})
            assert "service.source" in attrs
            assert "dependency.type" in attrs

    def test_span_emission_empty_graph(self, empty_comm_graph):
        from contextcore.graph.emitter import emit_service_dependency_spans

        mock_tracer = MagicMock()
        count = emit_service_dependency_spans(empty_comm_graph, tracer=mock_tracer)
        assert count == 0
        mock_tracer.start_as_current_span.assert_not_called()
