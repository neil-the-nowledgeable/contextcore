"""Deployment method selector widget for ContextCore TUI."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RadioButton, Static
from textual.containers import Vertical

__all__ = ["DeploymentSelector"]


class DeploymentSelector(Widget):
    """Widget for selecting deployment method."""

    method_selected: reactive[bool] = reactive(True)  # Default is selected
    selected_method: reactive[str] = reactive("docker_compose")

    DEFAULT_CSS = """
    DeploymentSelector {
        height: auto;
        padding: 1;
    }

    .section-header {
        text-style: bold;
        margin-bottom: 1;
    }

    .deployment-options {
        margin: 1 0;
    }

    .method-description {
        color: $text-muted;
        margin-left: 3;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Choose your deployment method:", classes="section-header")
        with Vertical(classes="deployment-options"):
            yield RadioButton("Docker Compose (Recommended)", value=True, id="docker_compose")
            yield Static("Quick local development", classes="method-description")
            yield RadioButton("Kind Cluster", id="kind")
            yield Static("Kubernetes patterns", classes="method-description")
            yield RadioButton("Custom", id="custom")
            yield Static("Existing infrastructure", classes="method-description")

    def on_radio_button_changed(self, event: RadioButton.Changed) -> None:
        """Handle deployment method selection."""
        if event.value:
            button_id = event.radio_button.id
            if button_id:
                self.selected_method = button_id
                self.method_selected = True
