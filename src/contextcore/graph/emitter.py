"""Emit service dependency spans to Tempo from a communication graph (REQ-CCL-401).

Creates one span per service dependency (RPC call, shared module import)
using the existing OTel tracer infrastructure.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


def emit_service_dependency_spans(
    comm_graph: Dict[str, Any],
    tracer: Optional[Any] = None,
) -> int:
    """Emit spans for each service dependency in the communication graph.

    Args:
        comm_graph: Communication graph dict with ``services`` and ``shared_modules``.
        tracer: Optional OTel tracer; defaults to ``trace.get_tracer("contextcore.graph")``.

    Returns:
        Number of spans emitted.
    """
    if not _OTEL_AVAILABLE:
        logger.debug("OTel not available — skipping service dependency span emission")
        return 0

    if tracer is None:
        tracer = trace.get_tracer("contextcore.graph")

    services = comm_graph.get("services", {})
    shared_modules = comm_graph.get("shared_modules", {})
    span_count = 0

    # Emit RPC dependency spans
    for svc_name, svc_data in services.items():
        for rpc_call in svc_data.get("rpc_calls", []):
            target_service = rpc_call.get("target_service", "unknown")
            method = rpc_call.get("method", "unknown")
            with tracer.start_as_current_span(
                "contextcore.service_dependency",
                attributes={
                    "service.source": svc_name,
                    "service.target": target_service,
                    "dependency.type": "rpc",
                    "dependency.method": method,
                },
            ):
                span_count += 1

    # Emit shared module dependency spans
    for mod_name, mod_data in shared_modules.items():
        for svc_name in mod_data.get("used_by", []):
            with tracer.start_as_current_span(
                "contextcore.service_dependency",
                attributes={
                    "service.source": svc_name,
                    "service.target": mod_name,
                    "dependency.type": "shared_module",
                    "dependency.module": mod_name,
                },
            ):
                span_count += 1

    logger.debug("Emitted %d service dependency spans", span_count)
    return span_count
