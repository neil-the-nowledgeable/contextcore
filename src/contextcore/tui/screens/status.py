"""Status dashboard screen for ContextCore TUI."""

from __future__ import annotations

import asyncio
import datetime
import webbrowser
from typing import Dict, Optional

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Static, Footer
from textual import work

from ..widgets.service_card import ServiceCard
from ..utils.health_checker import ServiceHealthChecker, ServiceHealth

__all__ = ["StatusScreen"]


class StatusScreen(Screen):
    """Real-time monitoring dashboard showing health of all observability services."""

    BINDINGS = [
        ("r", "refresh", "Refresh Now"),
        ("o", "open_grafana", "Open Grafana"),
        ("v", "run_verify", "Verify Installation"),
        ("p", "toggle_auto_refresh", "Pause/Resume Auto"),
        ("escape", "app.pop_screen", "Back"),
    ]

    DEFAULT_CSS = """
    StatusScreen {
        layout: vertical;
    }

    .status-header {
        dock: top;
        height: 3;
        text-align: center;
        background: $primary;
        color: $text;
        padding: 1;
    }

    .service-grid {
        layout: grid;
        grid-size: 3 2;
        grid-gutter: 1;
        margin: 1;
    }

    .status-summary {
        dock: bottom;
        height: 5;
        background: $surface;
        padding: 1;
    }

    .all-ok { color: green; }
    .degraded { color: yellow; }
    .critical { color: red; }
    """

    def __init__(self, refresh_interval: int = 10) -> None:
        super().__init__()
        self.refresh_interval = refresh_interval
        self.auto_refresh_enabled = True
        self.service_healths: Dict[str, ServiceHealth] = {}
        self.last_update: Optional[datetime.datetime] = None
        self.health_checker = ServiceHealthChecker()

        # Service definitions: (name, port, endpoint)
        self.services = [
            ("Grafana", 3000, "/api/health"),
            ("Tempo", 3200, "/ready"),
            ("Mimir", 9009, "/ready"),
            ("Loki", 3100, "/ready"),
            ("Alloy", 12345, "/ready"),
            ("OTLP gRPC", 4317, None),  # TCP check
        ]

        self.service_cards: Dict[str, ServiceCard] = {}

    def compose(self) -> ComposeResult:
        """Create the dashboard layout."""
        yield Static("ContextCore Status Dashboard", classes="status-header")

        with Container(classes="service-grid"):
            for name, port, endpoint in self.services:
                card = ServiceCard(name=name, port=port, endpoint=endpoint or "")
                self.service_cards[name] = card
                yield card

        yield Container(
            Static("", id="status-summary"),
            Static("", id="last-updated"),
            classes="status-summary"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Start the auto-refresh worker when screen mounts."""
        self.refresh_services()

    @work(exclusive=True)
    async def refresh_services(self) -> None:
        """Background worker to refresh service health status."""
        while self.auto_refresh_enabled:
            try:
                # Get health status for all services
                health_results = await self.health_checker.check_all()
                self.service_healths = health_results
                self.last_update = datetime.datetime.now()

                # Update UI on main thread
                self.call_from_thread(self._update_ui)

            except Exception as e:
                self.log.error(f"Error refreshing services: {e}")

            # Wait for next refresh
            await asyncio.sleep(self.refresh_interval)

    def _update_ui(self) -> None:
        """Update the UI components with latest health data."""
        # Update service cards
        for name, card in self.service_cards.items():
            health = self.service_healths.get(name)
            if health:
                if health.healthy:
                    if health.response_time_ms and health.response_time_ms > 500:
                        status = "slow"
                    else:
                        status = "ok"
                else:
                    status = "down"
            else:
                status = "checking"

            card.update_status(status, health.response_time_ms if health else None)

        # Update status summary
        self._update_status_summary()

        # Update last updated time
        if self.last_update:
            time_ago = (datetime.datetime.now() - self.last_update).seconds
            auto_status = "AUTO" if self.auto_refresh_enabled else "PAUSED"
            try:
                last_updated_widget = self.query_one("#last-updated", Static)
                last_updated_widget.update(f"Last updated: {time_ago}s ago [{auto_status}]")
            except Exception:
                pass

    def _update_status_summary(self) -> None:
        """Update the overall status summary."""
        healthy_count = sum(1 for health in self.service_healths.values() if health.healthy)
        total_count = len(self.service_healths)

        if total_count == 0:
            summary = "Initializing..."
            css_class = ""
        elif healthy_count == total_count:
            summary = "All Systems Operational"
            css_class = "all-ok"
        elif healthy_count == 0:
            summary = "Critical: Stack Unavailable"
            css_class = "critical"
        else:
            down_count = total_count - healthy_count
            summary = f"Degraded: {down_count} service{'s' if down_count != 1 else ''} down"
            css_class = "degraded"

        try:
            summary_widget = self.query_one("#status-summary", Static)
            summary_widget.update(summary)
            # Remove old classes and add new one
            summary_widget.remove_class("all-ok", "degraded", "critical")
            if css_class:
                summary_widget.add_class(css_class)
        except Exception:
            pass

    def action_refresh(self) -> None:
        """Manually refresh service status."""
        self.refresh_services()

    def action_open_grafana(self) -> None:
        """Open Grafana in the default web browser."""
        try:
            webbrowser.open("http://localhost:3000")
        except Exception as e:
            self.log.error(f"Failed to open Grafana: {e}")

    def action_run_verify(self) -> None:
        """Run installation verification."""
        self.app.push_screen("install")

    def action_toggle_auto_refresh(self) -> None:
        """Toggle auto-refresh on/off."""
        self.auto_refresh_enabled = not self.auto_refresh_enabled
        if self.auto_refresh_enabled:
            self.refresh_services()
