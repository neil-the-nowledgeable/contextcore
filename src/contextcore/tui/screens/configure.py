"""Configuration screen for ContextCore TUI."""

from __future__ import annotations

import asyncio
from typing import Dict

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Container, Vertical, Horizontal
from textual.widgets import Button, Static, Label, Footer
from textual.screen import Screen
from textual.reactive import reactive
from textual import on

from ..widgets.config_input import ConfigInput
from ..utils.config import ConfigManager, CONFIG_SCHEMA

__all__ = ["ConfigureScreen"]


class ConfigureScreen(Screen):
    """Configuration screen for ContextCore environment settings."""

    BINDINGS = [
        ("s", "save_config", "Save to .env"),
        ("r", "reset_defaults", "Reset"),
        ("t", "test_connection", "Test"),
        ("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    ConfigureScreen {
        padding: 1;
    }

    .section {
        border: solid $primary;
        margin: 1 0;
        padding: 1;
    }

    .section-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    .status {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }

    .modified {
        color: $warning;
    }

    .saved {
        color: $success;
    }

    .error {
        color: $error;
    }
    """

    has_unsaved_changes: bool = reactive(False)
    status_message: str = reactive("Ready")

    def __init__(self) -> None:
        super().__init__()
        self.config_manager = ConfigManager()
        self.config_inputs: Dict[str, ConfigInput] = {}
        self.config_data: Dict[str, str] = {}

    def compose(self) -> ComposeResult:
        """Create the screen layout."""
        with ScrollableContainer():
            with Vertical(id="main-container"):
                yield Label("ContextCore Configuration", classes="section-title")

                for section_name, items in CONFIG_SCHEMA.items():
                    with Container(classes="section"):
                        yield Label(section_name, classes="section-title")
                        for item in items:
                            config_input = ConfigInput(
                                name=item.name,
                                value=self.config_data.get(item.name, item.default),
                                description=item.description,
                                is_password=item.is_password,
                                choices=item.choices
                            )
                            self.config_inputs[item.name] = config_input
                            yield config_input

        yield Static(self.status_message, classes="status", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Load configuration when screen mounts."""
        self.config_data = await self.config_manager.load_config()
        self.title = "ContextCore Configuration"

    @on(ConfigInput.Changed)
    def on_config_changed(self, event: ConfigInput.Changed) -> None:
        """Handle configuration input changes."""
        self.config_data[event.name] = event.value
        self.has_unsaved_changes = True
        self.status_message = "Modified - Press 's' to save"

    async def action_save_config(self) -> None:
        """Save configuration to .env file."""
        if not self.has_unsaved_changes:
            self.status_message = "No changes to save"
            return

        try:
            success = await self.config_manager.save_config(self.config_data)
            if success:
                self.has_unsaved_changes = False
                self.status_message = "Configuration saved successfully"
                # Clear modification indicators
                for config_input in self.config_inputs.values():
                    config_input.mark_modified(False)
            else:
                self.status_message = "Error saving configuration"
        except Exception as e:
            self.status_message = f"Error: {str(e)}"

    async def action_reset_defaults(self) -> None:
        """Reset all configuration to defaults."""
        # Load fresh config from environment/file
        self.config_data = await self.config_manager.load_config()

        # Update all input widgets
        for name, config_input in self.config_inputs.items():
            # Find the default value for this config item
            default_value = ""
            for items in CONFIG_SCHEMA.values():
                for item in items:
                    if item.name == name:
                        default_value = item.default
                        break

            config_input.set_value(self.config_data.get(name, default_value))
            config_input.mark_modified(False)

        self.has_unsaved_changes = False
        self.status_message = "Reset to defaults"

    async def action_test_connection(self) -> None:
        """Test all endpoint connections."""
        self.status_message = "Testing connections..."

        # Test endpoints concurrently
        test_tasks = []
        endpoint_inputs = []

        for name, config_input in self.config_inputs.items():
            if "URL" in name or "ENDPOINT" in name:
                endpoint_inputs.append((name, config_input))
                test_tasks.append(
                    self.config_manager.test_endpoint(name, config_input.get_value())
                )

        if not test_tasks:
            self.status_message = "No endpoints to test"
            return

        try:
            results = await asyncio.gather(*test_tasks, return_exceptions=True)

            # Update UI with results
            success_count = 0
            for (name, config_input), result in zip(endpoint_inputs, results):
                if isinstance(result, Exception):
                    config_input.set_test_result(False, f"Error: {str(result)}")
                else:
                    success, response_time, message = result
                    config_input.set_test_result(success, message or "")
                    if success:
                        success_count += 1

            self.status_message = f"Tested {len(test_tasks)} endpoints - {success_count} successful"

        except Exception as e:
            self.status_message = f"Test error: {str(e)}"

    async def action_go_back(self) -> None:
        """Go back to main screen, with unsaved changes warning."""
        if self.has_unsaved_changes:
            # In a real implementation, you'd show a confirmation dialog
            self.status_message = "Warning: You have unsaved changes!"
            return

        self.app.pop_screen()
