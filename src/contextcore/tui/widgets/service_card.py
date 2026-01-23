"""Service status card widget for ContextCore TUI."""

from __future__ import annotations

from typing import Optional, Literal

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

__all__ = ["ServiceCard"]

StatusType = Literal["ok", "slow", "down", "checking"]


class ServiceCard(Widget):
    """Widget displaying the health status of a single service."""

    DEFAULT_CSS = """
    ServiceCard {
        border: solid $primary;
        height: 6;
        padding: 1;
        margin: 0 1;
        background: $surface;
    }

    ServiceCard:hover {
        border: solid $accent;
    }

    .service-name {
        text-style: bold;
        text-align: center;
    }

    .service-status {
        text-align: center;
        margin-top: 1;
    }

    .service-port {
        text-align: center;
        color: $text-muted;
    }

    .service-timing {
        text-align: center;
        color: $text-muted;
    }

    .status-ok { color: green; }
    .status-slow { color: yellow; }
    .status-down { color: red; }
    .status-checking { color: cyan; }
    """

    def __init__(
        self,
        name: str,
        port: int,
        endpoint: str = "",
        status: StatusType = "checking",
        response_time_ms: Optional[int] = None
    ) -> None:
        super().__init__()
        self.service_name = name  # Renamed to avoid Textual 'name' property conflict
        self.port = port
        self.endpoint = endpoint
        self._status = status
        self._response_time_ms = response_time_ms

    def compose(self) -> ComposeResult:
        """Compose the service card layout."""
        yield Static(self.service_name.upper(), classes="service-name")
        yield Static(self._get_status_text(), classes=f"service-status status-{self._status}", id="status-text")
        yield Static(f":{self.port}", classes="service-port")
        yield Static(self._get_timing_text(), classes="service-timing", id="timing-text")

    def update_status(self, status: StatusType, response_time_ms: Optional[int] = None) -> None:
        """Update the service status and response time."""
        self._status = status
        self._response_time_ms = response_time_ms

        try:
            # Update status text and styling
            status_widget = self.query_one("#status-text", Static)
            status_widget.update(self._get_status_text())
            status_widget.remove_class("status-ok", "status-slow", "status-down", "status-checking")
            status_widget.add_class(f"status-{status}")

            # Update timing display
            timing_widget = self.query_one("#timing-text", Static)
            timing_widget.update(self._get_timing_text())
        except Exception:
            pass

    def _get_status_text(self) -> str:
        """Get the status display text with icon."""
        status_map = {
            "ok": "OK",
            "slow": "SLOW",
            "down": "DOWN",
            "checking": "CHECKING"
        }
        return status_map.get(self._status, "UNKNOWN")

    def _get_timing_text(self) -> str:
        """Get the response time display text."""
        if self._response_time_ms is not None:
            return f"{self._response_time_ms}ms"
        return ""
