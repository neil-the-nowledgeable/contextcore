"""Script Generator screen for ContextCore TUI."""

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Container
from textual.screen import Screen
from textual.widgets import Button, Input, Label, RadioButton, Static, Footer
from textual.reactive import reactive

from ..widgets.script_preview import ScriptPreview
from ..utils.script_templates import (
    render_docker_compose_script,
    render_kind_script,
    render_custom_script,
)

__all__ = ["ScriptGeneratorScreen"]


class ScriptGeneratorScreen(Screen):
    """Screen for generating custom installation scripts."""

    BINDINGS = [
        ("g", "generate", "Generate"),
        ("c", "copy", "Copy"),
        ("s", "save", "Save"),
        ("escape", "app.pop_screen", "Back"),
    ]

    DEFAULT_CSS = """
    ScriptGeneratorScreen {
        padding: 1;
    }

    .screen-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 2;
    }

    .form-section {
        border: solid $primary;
        padding: 1;
        margin: 1 0;
    }

    .section-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .form-row {
        margin: 1 0;
    }

    .form-label {
        width: 25;
    }

    .form-input {
        width: 50;
    }

    .method-options {
        margin: 1 0;
    }

    .method-description {
        color: $text-muted;
        margin-left: 3;
        margin-bottom: 1;
    }

    .button-row {
        margin: 2 0;
        align: center middle;
    }

    #preview-container {
        height: 1fr;
    }
    """

    selected_method: reactive[str] = reactive("docker_compose")
    script_generated: reactive[bool] = reactive(False)

    def __init__(self):
        super().__init__()
        self._script_preview: Optional[ScriptPreview] = None

    def compose(self) -> ComposeResult:
        yield Static("Script Generator", classes="screen-title")

        # Configuration form
        with Container(classes="form-section"):
            yield Label("Deployment Method", classes="section-title")
            with Vertical(classes="method-options"):
                yield RadioButton("Docker Compose (Recommended)", value=True, id="method-docker")
                yield Static("Quick local development with make full-setup", classes="method-description")
                yield RadioButton("Kind Cluster", id="method-kind")
                yield Static("Kubernetes patterns with Kind", classes="method-description")
                yield RadioButton("Custom Infrastructure", id="method-custom")
                yield Static("Connect to existing observability stack", classes="method-description")

        with Container(classes="form-section"):
            yield Label("Configuration", classes="section-title")

            with Horizontal(classes="form-row"):
                yield Label("Project Directory:", classes="form-label")
                yield Input(
                    value=str(Path.home() / "Documents" / "dev" / "ContextCore"),
                    id="project-dir",
                    classes="form-input"
                )

            with Horizontal(classes="form-row"):
                yield Label("Virtual Env Path:", classes="form-label")
                yield Input(value=".venv", id="venv-path", classes="form-input")

            with Horizontal(classes="form-row"):
                yield Label("Custom Grafana URL:", classes="form-label")
                yield Input(
                    placeholder="Leave empty for default (http://localhost:3000)",
                    id="grafana-url",
                    classes="form-input"
                )

            with Horizontal(classes="form-row"):
                yield Label("Custom OTLP Endpoint:", classes="form-label")
                yield Input(
                    placeholder="Leave empty for default (localhost:4317)",
                    id="otel-endpoint",
                    classes="form-input"
                )

            # Kind-specific options (hidden by default)
            with Horizontal(classes="form-row", id="kind-options"):
                yield Label("Cluster Name:", classes="form-label")
                yield Input(value="o11y-dev", id="cluster-name", classes="form-input")

        with Horizontal(classes="button-row"):
            yield Button("Generate Script", id="generate-btn", variant="primary")
            yield Button("Clear", id="clear-btn")

        # Script preview area
        with Container(id="preview-container"):
            self._script_preview = ScriptPreview()
            yield self._script_preview

        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen."""
        self._update_kind_options_visibility()

    def on_radio_button_changed(self, event: RadioButton.Changed) -> None:
        """Handle deployment method selection."""
        if event.value:
            button_id = event.radio_button.id
            if button_id == "method-docker":
                self.selected_method = "docker_compose"
            elif button_id == "method-kind":
                self.selected_method = "kind"
            elif button_id == "method-custom":
                self.selected_method = "custom"

            self._update_kind_options_visibility()

    def _update_kind_options_visibility(self) -> None:
        """Show/hide Kind-specific options based on selected method."""
        try:
            kind_options = self.query_one("#kind-options", Horizontal)
            if self.selected_method == "kind":
                kind_options.display = True
            else:
                kind_options.display = False
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "generate-btn":
            self._generate_script()
        elif event.button.id == "clear-btn":
            self._clear_form()

    def action_generate(self) -> None:
        """Generate script action."""
        self._generate_script()

    def action_copy(self) -> None:
        """Copy to clipboard action."""
        if self._script_preview:
            self._script_preview._copy_to_clipboard()

    def action_save(self) -> None:
        """Save to file action."""
        if self._script_preview:
            self._script_preview._save_to_file()

    def _generate_script(self) -> None:
        """Generate the installation script based on form values."""
        # Get form values
        project_dir = self.query_one("#project-dir", Input).value
        venv_path = self.query_one("#venv-path", Input).value
        grafana_url = self.query_one("#grafana-url", Input).value or None
        otel_endpoint = self.query_one("#otel-endpoint", Input).value or None

        # Generate script based on method
        if self.selected_method == "docker_compose":
            script = render_docker_compose_script(
                project_dir=project_dir,
                venv_path=venv_path,
                grafana_url=grafana_url,
                otel_endpoint=otel_endpoint,
            )
        elif self.selected_method == "kind":
            cluster_name = self.query_one("#cluster-name", Input).value
            script = render_kind_script(
                project_dir=project_dir,
                venv_path=venv_path,
                cluster_name=cluster_name,
                grafana_url=grafana_url,
                otel_endpoint=otel_endpoint,
            )
        else:
            script = render_custom_script(
                project_dir=project_dir,
                venv_path=venv_path,
                grafana_url=grafana_url,
                otel_endpoint=otel_endpoint,
            )

        # Update preview
        if self._script_preview:
            self._script_preview.update_script(script)

        self.script_generated = True

    def _clear_form(self) -> None:
        """Clear the form and preview."""
        # Reset inputs to defaults
        self.query_one("#project-dir", Input).value = str(Path.home() / "Documents" / "dev" / "ContextCore")
        self.query_one("#venv-path", Input).value = ".venv"
        self.query_one("#grafana-url", Input).value = ""
        self.query_one("#otel-endpoint", Input).value = ""
        self.query_one("#cluster-name", Input).value = "o11y-dev"

        # Clear preview
        if self._script_preview:
            self._script_preview.update_script("")

        self.script_generated = False
