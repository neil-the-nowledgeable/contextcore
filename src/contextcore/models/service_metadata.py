"""
Service-level metadata for pipeline export enrichment.

Provides typed models describing per-service transport, schema, and
infrastructure details that downstream consumers (plan ingestion, artisan
DESIGN, contractor) use for protocol-aware code generation.

Addresses:
- REQ-PCG-024 req 7: onboarding metadata lacks service-level metadata
- REQ-PCG-032 req 6: calibration hints need transport-protocol context
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TransportProtocol(str, Enum):
    """Transport protocol used by a service."""

    GRPC = "grpc"
    HTTP = "http"
    GRPC_WEB = "grpc-web"


class RPCDependency(BaseModel):
    """A single RPC dependency from one service to another (REQ-CCL-500)."""

    model_config = ConfigDict(extra="forbid")

    target_service: str = Field(..., description="Name of the service being called.")
    method: str = Field(..., description="RPC method name (e.g. ListProducts).")
    proto_module: Optional[str] = Field(
        None, description="Proto-generated module providing the stub (e.g. demo_pb2_grpc)."
    )


class ServiceMetadataEntry(BaseModel):
    """Metadata for a single service in the project."""

    model_config = ConfigDict(extra="forbid")

    transport_protocol: TransportProtocol = Field(
        ..., description="Primary transport protocol for the service."
    )
    schema_contract: Optional[str] = Field(
        None,
        min_length=1,
        description="Path to schema file (e.g. demo.proto for gRPC services).",
    )
    base_image: Optional[str] = Field(
        None,
        min_length=1,
        description="Base container image (e.g. python:3.12-slim).",
    )
    healthcheck_type: Optional[str] = Field(
        None,
        min_length=1,
        description="Healthcheck mechanism (e.g. grpc_health_probe, http_get).",
    )
    imports: Optional[List[str]] = Field(
        None, description="Modules imported by this service (e.g. demo_pb2, demo_pb2_grpc)."
    )
    rpc_dependencies: Optional[List[RPCDependency]] = Field(
        None, description="RPC calls this service makes to other services."
    )
    exposes_rpcs: Optional[List[str]] = Field(
        None, description="RPC methods this service exposes."
    )

    @property
    def effective_healthcheck(self) -> str:
        """Return explicit healthcheck or derive from transport protocol."""
        if self.healthcheck_type:
            return self.healthcheck_type
        return {
            TransportProtocol.GRPC: "grpc_health_probe",
            TransportProtocol.HTTP: "http_get",
            TransportProtocol.GRPC_WEB: "http_get",
        }[self.transport_protocol]


# Convenience type alias for use in function signatures
ServiceMetadataMap = Dict[str, ServiceMetadataEntry]
