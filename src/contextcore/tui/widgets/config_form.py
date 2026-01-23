"""Configuration form widget for ContextCore TUI."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Input, Static, Label
from textual.containers import Vertical

__all__ = ["ConfigurationForm"]


class ConfigurationForm(Widget):
    """Widget for deployment configuration."""

    DEFAULT_CSS = """
    ConfigurationForm {
        height: auto;
        padding: 1;
    }

    .section-header {
        text-style: bold;
        margin-bottom: 1;
    }

    .config-form {
        margin: 1 0;
    }

    Label {
        margin-top: 1;
    }

    Input {
        margin-bottom: 1;
    }
    """

    def __init__(self, deployment_method: str = "docker_compose"):
        super().__init__()
        self.deployment_method = deployment_method

    def compose(self) -> ComposeResult:
        yield Static("Configure your deployment:", classes="section-header")

        if self.deployment_method == "docker_compose":
            with Vertical(classes="config-form"):
                yield Label("Grafana URL:")
                yield Input(value="http://localhost:3000", id="grafana_url")
                yield Label("OTLP Endpoint:")
                yield Input(value="localhost:4317", id="otlp_endpoint")
                yield Label("Grafana Username:")
                yield Input(value="admin", id="grafana_user")
                yield Label("Grafana Password:")
                yield Input(value="admin", password=True, id="grafana_password")
        elif self.deployment_method == "kind":
            with Vertical(classes="config-form"):
                yield Label("Cluster Name:")
                yield Input(value="o11y-dev", id="cluster_name")
                yield Label("Namespace:")
                yield Input(value="observability", id="namespace")
                yield Label("Deploy Directory:")
                yield Input(value="~/Documents/Deploy", id="deploy_dir")
        else:
            with Vertical(classes="config-form"):
                yield Label("Custom OTLP Endpoint:")
                yield Input(placeholder="e.g., your-otlp-server:4317", id="custom_endpoint")
                yield Label("Custom Grafana URL:")
                yield Input(placeholder="e.g., https://your-grafana.com", id="custom_grafana")

    def get_config(self) -> dict:
        """Get the current configuration values."""
        config = {}
        try:
            for input_widget in self.query(Input):
                if input_widget.id:
                    config[input_widget.id] = input_widget.value
        except Exception:
            pass
        return config
