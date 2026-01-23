"""Main TUI application class for ContextCore."""

import os
from typing import Dict, Optional, Type
import aiohttp
import asyncio
from textual.app import App
from textual.screen import Screen
from textual.binding import Binding

# Import screens directly to avoid lazy loading issues with Textual 7.x
from contextcore.tui.screens.welcome import WelcomeScreen
from contextcore.tui.screens.install import InstallScreen
from contextcore.tui.screens.status import StatusScreen
from contextcore.tui.screens.configure import ConfigureScreen
from contextcore.tui.screens.help import HelpScreen
from contextcore.tui.screens.script_generator import ScriptGeneratorScreen

__all__ = ["ContextCoreTUI", "get_env_config", "check_service_health"]


def get_env_config() -> Dict[str, str]:
    """Load configuration from environment variables with sensible defaults."""
    return {
        "GRAFANA_URL": os.getenv("GRAFANA_URL", "http://localhost:3000"),
        "TEMPO_URL": os.getenv("TEMPO_URL", "http://localhost:3200"),
        "MIMIR_URL": os.getenv("MIMIR_URL", "http://localhost:9009"),
        "LOKI_URL": os.getenv("LOKI_URL", "http://localhost:3100"),
        "OTEL_EXPORTER_OTLP_ENDPOINT": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"),
        "GRAFANA_USER": os.getenv("GRAFANA_USER", "admin"),
        "GRAFANA_PASSWORD": os.getenv("GRAFANA_PASSWORD", "admin"),
    }


async def check_service_health(url: str, timeout: float = 2.0) -> bool:
    """Check the health of a service by hitting its health endpoint."""
    try:
        # Add common health check endpoints
        health_endpoints = ["/api/health", "/health", "/-/healthy", "/ready"]

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            # Try the base URL first, then health endpoints
            urls_to_try = [url] + [f"{url.rstrip('/')}{endpoint}" for endpoint in health_endpoints]

            for check_url in urls_to_try:
                try:
                    async with session.get(check_url) as response:
                        if 200 <= response.status < 300:
                            return True
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    continue
        return False
    except Exception:
        return False


class ContextCoreTUI(App[None]):
    """Main TUI application class for ContextCore project management observability."""

    # Required Textual App configuration
    CSS_PATH = "styles/app.tcss"
    TITLE = "ContextCore"
    SUB_TITLE = "Project Management Observability"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "show_help", "Help"),
        Binding("escape", "go_back", "Back"),
        Binding("d", "toggle_dark", "Dark/Light"),
    ]

    # Screen routing - using direct class references for Textual 7.x compatibility
    SCREENS: Dict[str, Type[Screen]] = {
        "welcome": WelcomeScreen,
        "install": InstallScreen,
        "status": StatusScreen,
        "configure": ConfigureScreen,
        "help": HelpScreen,
        "script_generator": ScriptGeneratorScreen,
    }

    # MODES dict removed - using default mode handling
    # MODES = {
    #     "normal": "contextcore.tui.screens.welcome:WelcomeScreen",
    #     "help": "contextcore.tui.screens.help:HelpScreen",
    # }

    def __init__(
        self,
        initial_screen: str = "welcome",
        auto_refresh: bool = True,
        install_method: Optional[str] = None,
    ) -> None:
        """Initialize the ContextCore TUI application.

        Args:
            initial_screen: The screen to show on startup (default: "welcome")
            auto_refresh: Enable auto-refresh on status screen
            install_method: Pre-selected installation method
        """
        super().__init__()
        self.initial_screen = initial_screen
        self._enable_auto_refresh = auto_refresh  # Renamed to avoid Textual property conflict
        self.install_method = install_method
        self._screen_history = []

    def on_mount(self) -> None:
        """Called when the app is mounted. Push the initial screen."""
        try:
            self.push_screen(self.initial_screen)
        except Exception as e:
            # Fallback to welcome screen if initial screen fails
            self.log.error(f"Failed to load initial screen '{self.initial_screen}': {e}")
            self.push_screen("welcome")

    def action_go_back(self) -> None:
        """Go back to the previous screen or show quit confirmation if on base screen."""
        if len(self.screen_stack) <= 1:
            # On the base screen, show quit confirmation
            self.action_quit()
        else:
            # Pop the current screen to go back
            self.pop_screen()

    def action_show_help(self) -> None:
        """Display the help screen as a modal overlay."""
        try:
            self.push_screen("help")
        except Exception as e:
            self.log.error(f"Failed to show help screen: {e}")
            # Show a simple notification as fallback
            self.notify("Help screen unavailable", severity="warning")

    async def check_services(self) -> Dict[str, bool]:
        """Check the health of all configured observability services.

        Returns:
            Dict mapping service name to health status (True=healthy, False=unhealthy)
        """
        config = get_env_config()

        # Create tasks for concurrent health checks
        tasks = {
            "grafana": check_service_health(config["GRAFANA_URL"]),
            "tempo": check_service_health(config["TEMPO_URL"]),
            "mimir": check_service_health(config["MIMIR_URL"]),
            "loki": check_service_health(config["LOKI_URL"]),
            "otlp": check_service_health(config["OTEL_EXPORTER_OTLP_ENDPOINT"]),
        }

        # Execute all health checks concurrently
        try:
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            # Map results back to service names
            services = {}
            for i, (service_name, _) in enumerate(tasks.items()):
                result = results[i]
                services[service_name] = result if isinstance(result, bool) else False

            return services

        except Exception as e:
            self.log.error(f"Error checking service health: {e}")
            # Return all services as unhealthy on error
            return {service: False for service in tasks.keys()}

    def get_service_status_summary(self) -> str:
        """Get a summary string of service health status.

        Returns:
            Human-readable status summary
        """
        # This will be called by screens to display status
        return "Status checking..."
