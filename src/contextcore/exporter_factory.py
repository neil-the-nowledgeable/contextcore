"""
OTLP Exporter Factory.

Centralizes OTLP exporter creation with protocol selection based on
standard OTel environment variables:
- OTEL_EXPORTER_OTLP_PROTOCOL (general)
- OTEL_EXPORTER_OTLP_TRACES_PROTOCOL (signal-specific override)
- OTEL_EXPORTER_OTLP_METRICS_PROTOCOL (signal-specific override)

Default protocol is 'grpc' for backward compatibility.
"""

from __future__ import annotations

import logging
import os

from contextcore.contracts.timeouts import OTEL_DEFAULT_GRPC_PORT, OTEL_DEFAULT_HTTP_PORT

logger = logging.getLogger(__name__)

_VALID_PROTOCOLS = ("grpc", "http/protobuf")


def _get_protocol(signal: str | None = None) -> str:
    """
    Determine OTLP protocol from environment variables.

    Args:
        signal: Optional signal name ("traces" or "metrics") for
                signal-specific override.

    Returns:
        Protocol string: "grpc" or "http/protobuf"
    """
    # Signal-specific override takes precedence
    if signal:
        env_key = f"OTEL_EXPORTER_OTLP_{signal.upper()}_PROTOCOL"
        value = os.environ.get(env_key, "").strip()
        if value:
            if value in _VALID_PROTOCOLS:
                return value
            logger.warning(
                f"Invalid {env_key}={value!r}, expected one of {_VALID_PROTOCOLS}. "
                f"Falling back to general setting."
            )

    # General protocol setting
    value = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "").strip()
    if value:
        if value in _VALID_PROTOCOLS:
            return value
        logger.warning(
            f"Invalid OTEL_EXPORTER_OTLP_PROTOCOL={value!r}, "
            f"expected one of {_VALID_PROTOCOLS}. Defaulting to 'grpc'."
        )

    return "grpc"


def _default_port_for_protocol(protocol: str) -> int:
    """Return the default port for the given protocol."""
    if protocol == "http/protobuf":
        return OTEL_DEFAULT_HTTP_PORT
    return OTEL_DEFAULT_GRPC_PORT


def create_span_exporter(endpoint: str | None = None, insecure: bool = True):
    """
    Create an OTLP span exporter using the configured protocol.

    Args:
        endpoint: OTLP endpoint. If None, reads from
                  OTEL_EXPORTER_OTLP_ENDPOINT (default: localhost:<port>).
        insecure: Use insecure (non-TLS) connection.

    Returns:
        An OTLPSpanExporter instance (gRPC or HTTP).

    Raises:
        ImportError: If the required exporter package is not installed.
    """
    protocol = _get_protocol("traces")
    default_port = _default_port_for_protocol(protocol)
    endpoint = endpoint or os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", f"localhost:{default_port}"
    )

    if protocol == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        # HTTP exporter expects a full URL
        if not endpoint.startswith(("http://", "https://")):
            scheme = "http" if insecure else "https"
            endpoint = f"{scheme}://{endpoint}"
        logger.info(f"Creating HTTP/protobuf span exporter to {endpoint}")
        return OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        logger.info(f"Creating gRPC span exporter to {endpoint}")
        return OTLPSpanExporter(endpoint=endpoint, insecure=insecure)


def create_metric_exporter(endpoint: str | None = None, insecure: bool = True):
    """
    Create an OTLP metric exporter using the configured protocol.

    Args:
        endpoint: OTLP endpoint. If None, reads from
                  OTEL_EXPORTER_OTLP_ENDPOINT (default: localhost:<port>).
        insecure: Use insecure (non-TLS) connection.

    Returns:
        An OTLPMetricExporter instance (gRPC or HTTP).

    Raises:
        ImportError: If the required exporter package is not installed.
    """
    protocol = _get_protocol("metrics")
    default_port = _default_port_for_protocol(protocol)
    endpoint = endpoint or os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", f"localhost:{default_port}"
    )

    if protocol == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        if not endpoint.startswith(("http://", "https://")):
            scheme = "http" if insecure else "https"
            endpoint = f"{scheme}://{endpoint}"
        logger.info(f"Creating HTTP/protobuf metric exporter to {endpoint}")
        return OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
    else:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        logger.info(f"Creating gRPC metric exporter to {endpoint}")
        return OTLPMetricExporter(endpoint=endpoint, insecure=insecure)
