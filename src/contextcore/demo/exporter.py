"""
Telemetry export utilities for demo data.

Supports exporting collected spans and logs to:
- JSON files for later loading
- OTLP endpoint (Tempo) for span ingestion
- Loki endpoint for log ingestion

The dual export (spans + logs) supports the ContextCore architecture where:
- Tempo stores task spans for TraceQL queries
- Loki stores structured logs for LogQL queries and metrics derivation
"""

from __future__ import annotations

import json
import logging
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

logger = logging.getLogger(__name__)


def span_to_dict(span: ReadableSpan) -> Dict[str, Any]:
    """
    Convert a ReadableSpan to a JSON-serializable dictionary.

    Args:
        span: OTel ReadableSpan

    Returns:
        Dictionary representation of the span
    """
    # Extract basic span info
    context = span.get_span_context()

    result: Dict[str, Any] = {
        "name": span.name,
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
        "start_time_ns": span.start_time,
        "end_time_ns": span.end_time,
        "status": {
            "status_code": span.status.status_code.name,
            "description": span.status.description,
        },
        "kind": span.kind.name if span.kind else "INTERNAL",
    }

    # Add parent span ID if present
    if span.parent and span.parent.span_id:
        result["parent_span_id"] = format(span.parent.span_id, "016x")

    # Add attributes
    if span.attributes:
        result["attributes"] = dict(span.attributes)

    # Add events
    if span.events:
        result["events"] = [
            {
                "name": event.name,
                "timestamp_ns": event.timestamp,
                "attributes": dict(event.attributes) if event.attributes else {},
            }
            for event in span.events
        ]

    # Add links
    if span.links:
        result["links"] = [
            {
                "trace_id": format(link.context.trace_id, "032x"),
                "span_id": format(link.context.span_id, "016x"),
                "attributes": dict(link.attributes) if link.attributes else {},
            }
            for link in span.links
        ]

    # Add resource attributes
    if span.resource:
        result["resource"] = dict(span.resource.attributes)

    return result


def save_spans_to_file(spans: List[ReadableSpan], filepath: str) -> None:
    """
    Save spans to a JSON file.

    Args:
        spans: List of ReadableSpan objects
        filepath: Output file path
    """
    data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "span_count": len(spans),
        "spans": [span_to_dict(span) for span in spans],
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    logger.info(f"Saved {len(spans)} spans to {filepath}")


def load_spans_from_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Load spans from a JSON file.

    Args:
        filepath: Input file path

    Returns:
        List of span dictionaries
    """
    with open(filepath) as f:
        data = json.load(f)

    logger.info(f"Loaded {data['span_count']} spans from {filepath}")
    return data["spans"]


def save_logs_to_file(logs: List[Dict[str, Any]], filepath: str) -> None:
    """
    Save logs to a JSON file.

    Args:
        logs: List of log entry dictionaries
        filepath: Output file path
    """
    data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "log_count": len(logs),
        "logs": logs,
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    logger.info(f"Saved {len(logs)} logs to {filepath}")


def load_logs_from_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Load logs from a JSON file.

    Args:
        filepath: Input file path

    Returns:
        List of log dictionaries
    """
    with open(filepath) as f:
        data = json.load(f)

    logger.info(f"Loaded {data['log_count']} logs from {filepath}")
    return data["logs"]


def load_to_loki(
    endpoint: str,
    logs_file: Optional[str] = None,
    logs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Load logs to Loki via push API.

    Args:
        endpoint: Loki push endpoint (e.g., http://localhost:3100/loki/api/v1/push)
        logs_file: Path to JSON file with logs (alternative to logs param)
        logs: List of log dictionaries (alternative to logs_file param)

    Returns:
        Statistics about the export
    """
    if logs_file:
        log_entries = load_logs_from_file(logs_file)
    elif logs:
        log_entries = logs
    else:
        raise ValueError("Either logs_file or logs must be provided")

    # Group logs by service label for efficient Loki push
    streams: Dict[str, List[List]] = {}

    for log_entry in log_entries:
        # Build label set
        service = log_entry.get("service", "contextcore")
        project_id = log_entry.get("project_id", "unknown")

        label_key = f'{{service="{service}", project_id="{project_id}"}}'

        if label_key not in streams:
            streams[label_key] = []

        # Convert timestamp to nanoseconds
        ts = log_entry.get("timestamp", datetime.utcnow().isoformat())
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            ts_ns = str(int(dt.timestamp() * 1e9))
        else:
            ts_ns = str(int(ts * 1e9))

        # Log line is the full JSON entry
        log_line = json.dumps(log_entry, default=str)

        streams[label_key].append([ts_ns, log_line])

    # Build Loki push payload
    payload = {
        "streams": [
            {
                "stream": json.loads(label_key.replace("{", '{"').replace("=", '":"').replace(", ", '","').replace("}", '"}')),
                "values": values
            }
            for label_key, values in streams.items()
        ]
    }

    # Actually, Loki expects a specific format. Let me fix this:
    loki_streams = []
    for label_key, values in streams.items():
        # Parse labels from the key
        labels = {}
        label_key_clean = label_key.strip("{}")
        for part in label_key_clean.split(", "):
            k, v = part.split("=")
            labels[k] = v.strip('"')

        loki_streams.append({
            "stream": labels,
            "values": values
        })

    payload = {"streams": loki_streams}

    # Push to Loki
    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        logger.info(f"Pushed {len(log_entries)} logs to Loki at {endpoint}")
        return {
            "endpoint": endpoint,
            "logs_pushed": len(log_entries),
            "streams": len(loki_streams),
            "success": True,
        }

    except requests.RequestException as e:
        logger.error(f"Failed to push logs to Loki: {e}")
        return {
            "endpoint": endpoint,
            "logs_pushed": 0,
            "success": False,
            "error": str(e),
        }


def load_to_tempo(
    endpoint: str,
    spans_file: Optional[str] = None,
    spans: Optional[List[ReadableSpan]] = None,
    insecure: bool = True,
) -> Dict[str, Any]:
    """
    Load spans to Tempo via OTLP.

    Args:
        endpoint: OTLP gRPC endpoint (e.g., localhost:4317)
        spans_file: Path to JSON file with spans (alternative to spans param)
        spans: List of ReadableSpan objects (alternative to spans_file param)
        insecure: Use insecure connection (no TLS)

    Returns:
        Statistics about the export
    """
    if spans_file:
        span_dicts = load_spans_from_file(spans_file)
        # For file-based loading, we need to reconstruct and export
        # This requires using the OTLP exporter with reconstructed span data
        logger.info(f"Loaded {len(span_dicts)} span definitions from {spans_file}")

        # Create exporter
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=insecure,
        )

        # Export spans in batches
        # Note: For JSON-loaded spans, we need to reconstruct them
        # This is handled by the BatchOTLPExporter below
        batch_exporter = BatchOTLPExporter(endpoint, insecure=insecure)
        result = batch_exporter.export_span_dicts(span_dicts)

        return {
            "endpoint": endpoint,
            "spans_exported": len(span_dicts),
            "success": result == SpanExportResult.SUCCESS,
        }

    elif spans:
        # Direct span export
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=insecure,
        )

        result = exporter.export(spans)
        exporter.shutdown()

        return {
            "endpoint": endpoint,
            "spans_exported": len(spans),
            "success": result == SpanExportResult.SUCCESS,
        }

    else:
        raise ValueError("Either spans_file or spans must be provided")


class BatchOTLPExporter:
    """
    Batch exporter for sending span dictionaries to OTLP endpoint.

    Reconstructs span data from JSON format and exports via OTLP.
    """

    def __init__(self, endpoint: str, insecure: bool = True, batch_size: int = 100):
        """
        Initialize batch exporter.

        Args:
            endpoint: OTLP gRPC endpoint
            insecure: Use insecure connection
            batch_size: Number of spans per batch
        """
        self.endpoint = endpoint
        self.insecure = insecure
        self.batch_size = batch_size
        self._exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=insecure,
        )

    def export_span_dicts(self, span_dicts: List[Dict[str, Any]]) -> SpanExportResult:
        """
        Export span dictionaries to OTLP endpoint.

        Note: This creates new spans with the same attributes but new trace/span IDs.
        For historical data demonstration, this maintains the timing relationships.

        Args:
            span_dicts: List of span dictionaries from JSON

        Returns:
            SpanExportResult indicating success/failure
        """
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Group spans by resource
        resource_spans: Dict[str, List[Dict]] = {}
        for span_dict in span_dicts:
            resource_key = json.dumps(span_dict.get("resource", {}), sort_keys=True)
            if resource_key not in resource_spans:
                resource_spans[resource_key] = []
            resource_spans[resource_key].append(span_dict)

        total_exported = 0
        last_result = SpanExportResult.SUCCESS

        for resource_json, spans in resource_spans.items():
            resource_attrs = json.loads(resource_json)
            resource = Resource.create(resource_attrs)

            # Create provider for this resource
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(BatchSpanProcessor(self._exporter))
            tracer = provider.get_tracer("contextcore.demo.reload")

            # Recreate spans
            for span_dict in spans:
                span = tracer.start_span(
                    name=span_dict["name"],
                    start_time=span_dict["start_time_ns"],
                    attributes=span_dict.get("attributes", {}),
                )

                # Add events
                for event in span_dict.get("events", []):
                    span.add_event(
                        event["name"],
                        attributes=event.get("attributes", {}),
                        timestamp=event["timestamp_ns"],
                    )

                # End span at original time
                if span_dict.get("end_time_ns"):
                    span.end(end_time=span_dict["end_time_ns"])
                else:
                    span.end()

                total_exported += 1

            # Flush this batch
            provider.force_flush()
            provider.shutdown()

        logger.info(f"Exported {total_exported} spans to {self.endpoint}")
        return last_result

    def shutdown(self) -> None:
        """Shutdown the exporter."""
        self._exporter.shutdown()


class FileSpanExporter(SpanExporter):
    """
    SpanExporter that writes spans to a JSON file.

    Useful for capturing spans during generation for later replay.
    """

    def __init__(self, filepath: str):
        """
        Initialize file exporter.

        Args:
            filepath: Output file path
        """
        self.filepath = filepath
        self._spans: List[ReadableSpan] = []

    def export(self, spans) -> SpanExportResult:
        """Export spans to internal buffer."""
        self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        """Write all spans to file on shutdown."""
        if self._spans:
            save_spans_to_file(self._spans, self.filepath)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush is a no-op for file exporter."""
        return True
