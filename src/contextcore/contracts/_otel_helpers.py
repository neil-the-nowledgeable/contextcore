"""
Shared OTel span event emission helper for contract domain modules.

Provides ``add_span_event()`` — the single-source implementation used by
all L1-L7 ``otel.py`` modules.  Centralises the OTel import guard and
span recording check so each domain module does not duplicate them.

Usage::

    from contextcore.contracts._otel_helpers import add_span_event

    add_span_event("my.event.name", {"key": "value"})
"""

from __future__ import annotations

try:
    from opentelemetry import trace as otel_trace

    HAS_OTEL = True
except ImportError:  # pragma: no cover
    HAS_OTEL = False


def add_span_event(
    name: str, attributes: dict[str, str | int | float | bool]
) -> None:
    """Add an event to the current OTel span if available.

    No-op when OpenTelemetry is not installed or the current span
    is not recording.

    Args:
        name: Event name (e.g. ``"convention.validation.complete"``).
        attributes: Flat dict of span event attributes.
    """
    if not HAS_OTEL:
        return
    span = otel_trace.get_current_span()
    if span and span.is_recording():
        span.add_event(name=name, attributes=attributes)
