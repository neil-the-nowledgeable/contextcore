"""Help and documentation screen for ContextCore TUI."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Markdown


class HelpScreen(Screen):
    """Help and documentation screen with keyboard shortcuts and usage guide."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("q", "app.quit", "Quit"),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        padding: 1;
    }

    Markdown {
        margin: 1;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the help screen layout."""
        yield Header()
        yield Markdown(HELP_TEXT, id="help-content")
        yield Footer()


HELP_TEXT = """
# ContextCore TUI Help

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit application |
| `?` | Show this help |
| `Esc` | Go back / Cancel |
| `d` | Toggle dark/light mode |
| `Tab` | Navigate between elements |
| `Enter` | Activate focused element |
| `Space` | Select/toggle checkbox |

## Screens

### Welcome
The landing screen with navigation to all features:
- Quick access to installation wizard
- Service status overview
- Configuration shortcuts
- Script generator

### Install
Guided installation wizard for the observability stack:
- **Prerequisites**: Automatic checking of system requirements
- **Method Selection**: Choose from Docker, Kind, or custom deployment
- **Configuration**: Set service ports, resource limits, and credentials
- **Progress**: Real-time installation monitoring with logs
- **Verification**: Automated testing of deployed services

### Status
Real-time health monitoring dashboard:
- **Service Health**: Visual indicators for all components
- **Response Times**: Performance metrics and trends
- **Auto-refresh**: Configurable update intervals
- **Quick Actions**: Restart services, view logs, open dashboards

### Configure
Environment configuration management:
- **Service Endpoints**: Modify host and port settings
- **Authentication**: Configure credentials and API keys
- **Environment Variables**: Custom configuration overrides
- **Validation**: Real-time configuration validation

### Script Generator
Generate custom installation scripts:
- **Docker Compose**: For local development
- **Kind Cluster**: For Kubernetes patterns
- Copy to clipboard or save to file
- Execute directly from TUI

## Getting Started

### 1. Fresh Installation
```bash
# Launch installation wizard
contextcore tui launch --screen install

# Or use automated install
contextcore tui install --method docker --auto
```

### 2. Monitor Services
```bash
# Interactive status dashboard
contextcore tui status

# JSON output for scripting
contextcore tui status --json

# Continuous monitoring
contextcore tui status --watch
```

### 3. Generate Install Script
Press `g` from the welcome screen to access the Script Generator.

## Service Access

Once installed, access services at:

| Service | URL | Default Credentials |
|---------|-----|-------------------|
| **Grafana** | http://localhost:3000 | admin / admin |
| **Tempo** | http://localhost:3200 | - |
| **Mimir** | http://localhost:9009 | - |
| **Loki** | http://localhost:3100 | - |

## CLI Integration

```bash
# Full TUI experience
contextcore tui launch

# Direct to specific screen
contextcore tui launch --screen status

# Installation wizard
contextcore tui install --method docker

# Status monitoring
contextcore tui status --watch

# JSON output for automation
contextcore tui status --json
```

---
*ContextCore TUI v0.1.0 - Built with Textual*
"""


__all__ = ["HelpScreen", "HELP_TEXT"]
