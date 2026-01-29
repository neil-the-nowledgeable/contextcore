#!/usr/bin/env python3
"""
Run Lead Contractor Workflow for ContextCore TUI Implementation.

This script uses the startd8 SDK's Lead Contractor workflow to implement
the Terminal User Interface (TUI) for ContextCore installation and management.

Working Directory: ~/Documents/dev/ContextCore

Usage:
    # Activate venv first
    cd ~/Documents/dev/ContextCore
    source .venv/bin/activate

    # Run all features
    python3 scripts/run_lead_contractor_tui.py

    # Run specific feature (1-6)
    python3 scripts/run_lead_contractor_tui.py 1   # Core App
    python3 scripts/run_lead_contractor_tui.py 2   # Welcome Screen
    python3 scripts/run_lead_contractor_tui.py 3   # Install Wizard
    python3 scripts/run_lead_contractor_tui.py 4   # Status Dashboard
    python3 scripts/run_lead_contractor_tui.py 5   # Configure Screen
    python3 scripts/run_lead_contractor_tui.py 6   # CLI Integration

Output:
    Generated code will be saved to: ~/Documents/dev/ContextCore/generated/tui/
"""

import sys
import os
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add startd8 SDK to path (prefer $STARTD8_SDK_ROOT if set)
STARTD8_SDK_PATH = os.environ.get("STARTD8_SDK_ROOT", "")
if STARTD8_SDK_PATH:
    STARTD8_SDK_PATH = os.path.join(STARTD8_SDK_PATH, "src")
    if os.path.exists(STARTD8_SDK_PATH):
        sys.path.insert(0, STARTD8_SDK_PATH)

# Output configuration
OUTPUT_DIR = Path(__file__).parent.parent / "generated" / "tui"
PROJECT_ROOT = Path(__file__).parent.parent

# Agent configuration
LEAD_AGENT = "anthropic:claude-sonnet-4-20250514"
DRAFTER_AGENT = "openai:gpt-4o-mini"
MAX_ITERATIONS = 3
PASS_THRESHOLD = 80

# Context for TUI development
TUI_CONTEXT = {
    "language": "Python 3.9+",
    "framework": "Textual TUI framework, Click CLI, async/await",
    "project": "ContextCore Terminal User Interface",
    "style": "PEP 8, type hints, docstrings, dataclasses, Textual CSS",
    "key_dependencies": "textual>=0.47.0, click, rich",
}

TUI_INTEGRATION = """
Finalize the code for production use:
1. Ensure all imports are at the top (textual, click, etc.)
2. Add proper __all__ export list
3. Verify type hints are complete
4. Use Textual's reactive properties and message system
5. Follow Textual's CSS styling patterns
6. Handle errors gracefully with user-friendly messages
7. Ensure async operations don't block the UI
8. Code should be self-contained and drop into src/contextcore/tui/
"""

# =============================================================================
# FEATURE 1: Core TUI Application
# =============================================================================
FEATURE_1_CORE_APP = """
Create the core TUI application framework for ContextCore.

## Goal
Build the main Textual application class that serves as the foundation for the TUI,
with screen routing, theming, and global key bindings.

## Context
- This is for ContextCore at /Users/neilyashinsky/Documents/dev/ContextCore
- File location: src/contextcore/tui/app.py
- Uses Textual framework (textual>=0.47.0)
- Should work with Python 3.9+

## Requirements

### 1. Main Application Class (ContextCoreTUI)
Create a Textual App subclass with:
- CSS_PATH pointing to "styles/app.tcss"
- TITLE = "ContextCore"
- SUB_TITLE = "Project Management Observability"
- BINDINGS for global shortcuts:
  - ("q", "quit", "Quit")
  - ("?", "show_help", "Help")
  - ("escape", "go_back", "Back")
  - ("d", "toggle_dark", "Dark/Light")
- SCREENS dict mapping screen names to screen classes
- MODES dict with "normal" and "help" modes

### 2. Screen Names to Support
- "welcome" - WelcomeScreen (default)
- "install" - InstallScreen
- "status" - StatusScreen
- "configure" - ConfigureScreen
- "help" - HelpScreen

### 3. Methods to Implement
```python
def __init__(self, initial_screen: str = "welcome"):
    # Store initial screen, call super().__init__()
    
def on_mount(self) -> None:
    # Push initial screen
    
def action_go_back(self) -> None:
    # Pop screen if not on welcome, otherwise confirm quit
    
def action_show_help(self) -> None:
    # Push help screen overlay
    
async def check_services(self) -> Dict[str, bool]:
    # Check health of Grafana, Tempo, Mimir, Loki, OTLP
    # Return dict mapping service name to health status
    # Use aiohttp or asyncio for non-blocking HTTP calls
```

### 4. Helper Functions
```python
def get_env_config() -> Dict[str, str]:
    # Return dict of environment variables with defaults:
    # GRAFANA_URL, TEMPO_URL, MIMIR_URL, LOKI_URL, 
    # OTEL_EXPORTER_OTLP_ENDPOINT, GRAFANA_USER, GRAFANA_PASSWORD
    
async def check_service_health(url: str, timeout: float = 2.0) -> bool:
    # Check if service responds to health endpoint
    # Handle connection errors gracefully
```

### 5. CSS Theme File (styles/app.tcss)
Create a modern, accessible theme with:
- Dark mode as default with cyan/green accent colors
- Light mode alternative
- Consistent spacing and borders
- Status colors: success (green), warning (yellow), error (red)
- Card-style containers for widgets
- Clear typography hierarchy

## Output
Provide two files:
1. app.py - The main application code
2. app.tcss - The CSS theme

Mark the separation clearly with:
```python
# === FILE: src/contextcore/tui/app.py ===
```
and
```css
/* === FILE: src/contextcore/tui/styles/app.tcss === */
```
"""

# =============================================================================
# FEATURE 2: Welcome Screen
# =============================================================================
FEATURE_2_WELCOME_SCREEN = """
Create the Welcome Screen for the ContextCore TUI.

## Goal
Build an inviting landing screen with ASCII art logo, project description,
and navigation cards to all major features.

## Context
- File location: src/contextcore/tui/screens/welcome.py
- Uses Textual framework
- Should integrate with the main ContextCoreTUI app

## Requirements

### 1. WelcomeScreen Class
Create a Textual Screen subclass with:
- BINDINGS for quick navigation:
  - ("i", "push_screen('install')", "Install")
  - ("s", "push_screen('status')", "Status")
  - ("c", "push_screen('configure')", "Configure")
  - ("d", "push_screen('demo')", "Demo")
  - ("h", "push_screen('help')", "Help")

### 2. Compose Method
The screen should display:
1. ASCII art logo for "CONTEXTCORE" (creative, modern style)
2. Tagline: "Project Management Observability Framework"
3. Three key benefits as bullet points:
   - "Tasks as spans • Unified telemetry • Zero manual reports"
4. Navigation grid with 6 cards (2 rows of 3):
   - Install (I) - "Guided setup wizard"
   - Status (S) - "Health dashboard"
   - Configure (C) - "Environment settings"
   - Demo (D) - "Generate sample data"
   - Help (H) - "Documentation"
   - Quit (Q) - "Exit TUI"

### 3. NavigationCard Widget
Create a custom widget class:
```python
class NavigationCard(Static):
    def __init__(self, key: str, title: str, description: str, action: str):
        # Store properties, create content
        
    def on_click(self) -> None:
        # Post message to push target screen
```

### 4. Styling
- Cards should be visually distinct with borders
- Show the keyboard shortcut prominently (e.g., "[I]nstall")
- Cards should respond to hover (highlight)
- Use grid layout for responsive arrangement

### 5. Footer
- Show "Press key in brackets or click to navigate"
- Show version number (from contextcore.__version__ or "0.1.0")

## ASCII Art Logo Example
Use something creative like:
```
 ╔═╗╔═╗╔╗╔╔╦╗╔═╗═╗ ╦╔╦╗  ╔═╗╔═╗╦═╗╔═╗
 ║  ║ ║║║║ ║ ╠═ ╔╩╦╝ ║   ║  ║ ║╠╦╝╠═ 
 ╚═╝╚═╝╝╚╝ ╩ ╚═╝╩ ╚═ ╩   ╚═╝╚═╝╩╚═╚═╝
```

## Output
Provide:
1. screens/welcome.py - The welcome screen implementation
2. widgets/navigation_card.py - The navigation card widget

Mark file separations clearly.
"""

# =============================================================================
# FEATURE 3: Installation Wizard
# =============================================================================
FEATURE_3_INSTALL_WIZARD = """
Create the Installation Wizard Screen for the ContextCore TUI.

## Goal
Build a multi-step installation wizard that guides users through:
1. Prerequisites check
2. Deployment method selection
3. Configuration
4. Stack deployment
5. Verification

## Context
- File location: src/contextcore/tui/screens/install.py
- Uses Textual framework with reactive state
- Integrates with contextcore.install module for verification

## Requirements

### 1. InstallScreen Class
Create a Textual Screen with:
- Reactive property: current_step = reactive(1)
- Total steps: 5
- BINDINGS:
  - ("n", "next_step", "Next")
  - ("b", "prev_step", "Back")
  - ("enter", "confirm", "Confirm")
  - ("escape", "cancel", "Cancel")

### 2. Step 1: Prerequisites Check
Widget: PrerequisitesChecker
Check and display status of:
- Python version (≥3.9) 
- Docker installed and running
- kubectl available (optional, show as warning if missing)
- Ports available: 3000, 3100, 3200, 4317, 9009
- Each item shows: name, status (✅/⚠️/❌), detail message

Implement async check methods that don't block UI.

### 3. Step 2: Deployment Selection
Widget: DeploymentSelector
Radio button group with options:
- "Docker Compose" - "Quick local development (~2 min)" [recommended badge]
- "Kind Cluster" - "Kubernetes patterns (~5 min)"
- "Custom" - "Existing infrastructure"

Store selection in reactive property.

### 4. Step 3: Configuration
Widget: ConfigurationForm
Show form inputs based on deployment method:

For Docker Compose:
- Grafana URL (default: http://localhost:3000)
- OTLP Endpoint (default: localhost:4317)

For Kind Cluster:
- Cluster name (default: o11y-dev)
- Namespace (default: observability)

For Custom:
- All endpoints manually specified
- Validation on input

### 5. Step 4: Deployment Progress
Widget: DeploymentProgress
- Progress bar showing overall progress
- Log output area (RichLog widget)
- Service status indicators (waiting → deploying → ready)
- Cancel button

Implement async deployment that:
- For Docker Compose: runs `make up` via asyncio.subprocess
- Streams output to the log area
- Updates progress as services become ready

### 6. Step 5: Verification
Widget: VerificationResults
- Run contextcore install verify
- Display results in a table
- Show completeness percentage
- Link to open dashboards

### 7. Navigation Footer
- Progress indicator: "Step X of 5: [Step Name]"
- Progress bar visual
- Back / Next / Cancel buttons

### 8. InstallWizardState Dataclass
```python
@dataclass
class InstallWizardState:
    deployment_method: str = "docker_compose"
    config: Dict[str, str] = field(default_factory=dict)
    prerequisites_passed: bool = False
    deployment_started: bool = False
    deployment_complete: bool = False
    verification_result: Optional[Any] = None
```

## Output
Provide:
1. screens/install.py - Main install screen with step navigation
2. widgets/prerequisites.py - Prerequisites checker widget
3. widgets/deployment_selector.py - Deployment method selector
4. widgets/config_form.py - Configuration form widget
5. widgets/progress.py - Deployment progress widget

Mark file separations clearly.
"""

# =============================================================================
# FEATURE 4: Status Dashboard
# =============================================================================
FEATURE_4_STATUS_DASHBOARD = """
Create the Status Dashboard Screen for the ContextCore TUI.

## Goal
Build a real-time monitoring dashboard showing the health of all services
in the observability stack with auto-refresh capabilities.

## Context
- File location: src/contextcore/tui/screens/status.py
- Uses Textual framework with workers for async updates
- Connects to Grafana, Tempo, Mimir, Loki, and OTLP endpoints

## Requirements

### 1. StatusScreen Class
Create a Textual Screen with:
- Auto-refresh timer (default: 10 seconds)
- BINDINGS:
  - ("r", "refresh", "Refresh Now")
  - ("o", "open_grafana", "Open Grafana")
  - ("v", "run_verify", "Verify Installation")
  - ("p", "toggle_auto_refresh", "Pause/Resume Auto")
- Worker for background health checks

### 2. Service Cards Grid
Display 6 service cards in a grid (3x2):
1. Grafana - Port 3000, /api/health endpoint
2. Tempo - Port 3200, /ready endpoint
3. Mimir - Port 9009, /ready endpoint
4. Loki - Port 3100, /ready endpoint
5. Alloy - Port 12345, /ready endpoint
6. OTLP gRPC - Port 4317, TCP check

### 3. ServiceCard Widget
Custom widget showing:
```
┌─────────────┐
│  GRAFANA    │  ← Service name (bold)
│   ✅ OK     │  ← Status icon + text (colored)
│ :3000       │  ← Port
│ 45ms        │  ← Response time (if available)
└─────────────┘
```

Status states:
- ✅ OK (green) - Service responding
- ⚠️ SLOW (yellow) - Response >500ms
- ❌ DOWN (red) - Not responding
- ⏳ CHECKING (cyan) - Currently checking

Props:
- name: str
- port: int
- status: Literal["ok", "slow", "down", "checking"]
- response_time_ms: Optional[int]
- endpoint: str

### 4. Installation Status Section
Below the service grid, show:
- Completeness bar: "████████████████████████ 100%"
- Critical requirements: "25/25 ✅"
- Last verified timestamp

### 5. Auto-Refresh Worker
```python
@work(exclusive=True)
async def refresh_services(self) -> None:
    # Check all services concurrently
    # Update ServiceCard widgets
    # Run every self.refresh_interval seconds if auto_refresh enabled
```

### 6. ServiceHealthChecker Class
Helper class for health checks:
```python
@dataclass
class ServiceHealth:
    name: str
    healthy: bool
    response_time_ms: Optional[int]
    error: Optional[str]

class ServiceHealthChecker:
    async def check_http(self, url: str, timeout: float = 2.0) -> ServiceHealth
    async def check_tcp(self, host: str, port: int, timeout: float = 2.0) -> ServiceHealth
    async def check_all(self) -> Dict[str, ServiceHealth]
```

### 7. Quick Actions Footer
- "Last updated: 10s ago" (live counter)
- Buttons: [R]efresh | [O]pen Grafana | [V]erify | [B]ack

### 8. Status Summary Header
Show overall status:
- "All Systems Operational" (green) if all healthy
- "Degraded: N services down" (yellow) if some unhealthy
- "Critical: Stack Unavailable" (red) if Grafana+Tempo down

## Output
Provide:
1. screens/status.py - Main status screen
2. widgets/service_card.py - Service health card widget
3. utils/health_checker.py - Async health check utilities

Mark file separations clearly.
"""

# =============================================================================
# FEATURE 5: Configuration Screen
# =============================================================================
FEATURE_5_CONFIGURE_SCREEN = """
Create the Configuration Screen for the ContextCore TUI.

## Goal
Build a screen for viewing and editing ContextCore environment configuration,
with the ability to save to .env file.

## Context
- File location: src/contextcore/tui/screens/configure.py
- Uses Textual framework with Input widgets
- Manages environment variables for the observability stack

## Requirements

### 1. ConfigureScreen Class
Create a Textual Screen with:
- BINDINGS:
  - ("s", "save_config", "Save to .env")
  - ("r", "reset_defaults", "Reset")
  - ("t", "test_connection", "Test")
  - ("escape", "go_back", "Back")
- Load current config on mount
- Track unsaved changes

### 2. Configuration Sections
Organize settings into collapsible sections:

**Endpoints Section:**
| Variable | Default | Description |
|----------|---------|-------------|
| OTEL_EXPORTER_OTLP_ENDPOINT | localhost:4317 | OTLP gRPC endpoint |
| GRAFANA_URL | http://localhost:3000 | Grafana base URL |
| TEMPO_URL | http://localhost:3200 | Tempo base URL |
| MIMIR_URL | http://localhost:9009 | Mimir base URL |
| LOKI_URL | http://localhost:3100 | Loki base URL |

**Credentials Section:**
| Variable | Default | Description |
|----------|---------|-------------|
| GRAFANA_USER | admin | Grafana username |
| GRAFANA_PASSWORD | admin | Grafana password (masked input) |

**OTel Settings Section:**
| Variable | Default | Description |
|----------|---------|-------------|
| CONTEXTCORE_EMIT_MODE | dual | Emit mode: dual/legacy/otel |

### 3. ConfigInput Widget
Custom widget for each config item:
```python
class ConfigInput(Static):
    def __init__(self, name: str, value: str, description: str, 
                 is_password: bool = False, choices: List[str] = None):
        # Create input with label and description
        
    def on_input_changed(self, event: Input.Changed) -> None:
        # Mark as modified, post message
```

Features:
- Show variable name as label
- Show current value in Input widget
- Password masking for sensitive values
- Dropdown for choice fields (OTEL_MODE)
- Visual indicator when modified (asterisk)
- Inline validation feedback

### 4. Config Loading/Saving
```python
def load_config(self) -> Dict[str, str]:
    # Load from environment variables first
    # Then override with .env file if exists
    # Return dict of all config values
    
async def save_config(self, config: Dict[str, str]) -> bool:
    # Write to .env file in project root
    # Use python-dotenv format
    # Return success status
```

### 5. Test Connection Action
When user presses 't':
- Test each endpoint concurrently
- Show results inline next to each input
- Green checkmark for successful, red X for failed

### 6. Unsaved Changes Warning
- Track which fields have been modified
- Show warning before leaving if unsaved
- Confirm dialog: "You have unsaved changes. Save before leaving?"

### 7. Footer
- Show save status: "Saved" / "Modified" / "Error saving"
- Buttons: [S]ave | [R]eset | [T]est | [B]ack

## Output
Provide:
1. screens/configure.py - Main configuration screen
2. widgets/config_input.py - Configuration input widget
3. utils/config.py - Config loading/saving utilities

Mark file separations clearly.
"""

# =============================================================================
# FEATURE 6: CLI Integration
# =============================================================================
FEATURE_6_CLI_INTEGRATION = """
Create the CLI command and module init files to integrate the TUI with ContextCore.

## Goal
Add the `contextcore tui` command that launches the Terminal User Interface,
with options to start on specific screens.

## Context
- CLI file: src/contextcore/cli/tui.py
- Module init: src/contextcore/tui/__init__.py
- Integrates with existing Click CLI in src/contextcore/cli/__init__.py

## Requirements

### 1. CLI Command (cli/tui.py)
```python
import click

@click.group()
def tui():
    \"\"\"Launch the ContextCore Terminal User Interface.\"\"\"
    pass

@tui.command("launch")
@click.option(
    "--screen", "-s",
    type=click.Choice(["welcome", "install", "status", "configure", "help"]),
    default="welcome",
    help="Initial screen to display"
)
@click.option(
    "--no-auto-refresh",
    is_flag=True,
    help="Disable auto-refresh on status screen"
)
def launch(screen: str, no_auto_refresh: bool):
    \"\"\"Launch the interactive TUI.
    
    Examples:
        contextcore tui launch
        contextcore tui launch --screen install
        contextcore tui launch --screen status --no-auto-refresh
    \"\"\"
    # Import here to avoid loading Textual unless needed
    from contextcore.tui import ContextCoreTUI
    
    app = ContextCoreTUI(
        initial_screen=screen,
        auto_refresh=not no_auto_refresh
    )
    app.run()

@tui.command("install")
@click.option(
    "--method", "-m",
    type=click.Choice(["docker", "kind", "custom"]),
    default=None,
    help="Pre-select deployment method"
)
@click.option(
    "--auto",
    is_flag=True,
    help="Run with all defaults (non-interactive)"
)
def install_wizard(method: Optional[str], auto: bool):
    \"\"\"Launch the installation wizard directly.
    
    Examples:
        contextcore tui install
        contextcore tui install --method docker --auto
    \"\"\"
    if auto:
        # Run non-interactive install
        click.echo("Running automated installation...")
        from contextcore.tui.installer import run_auto_install
        run_auto_install(method=method or "docker")
    else:
        from contextcore.tui import ContextCoreTUI
        app = ContextCoreTUI(
            initial_screen="install",
            install_method=method
        )
        app.run()

@tui.command("status")
@click.option(
    "--watch", "-w",
    is_flag=True,
    help="Keep watching (don't exit after first check)"
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON (non-interactive)"
)
def status_check(watch: bool, output_json: bool):
    \"\"\"Check service status.
    
    Examples:
        contextcore tui status
        contextcore tui status --json
        contextcore tui status --watch
    \"\"\"
    if output_json:
        import asyncio
        from contextcore.tui.utils.health_checker import ServiceHealthChecker
        
        checker = ServiceHealthChecker()
        results = asyncio.run(checker.check_all())
        
        import json
        click.echo(json.dumps({
            name: {
                "healthy": h.healthy,
                "response_time_ms": h.response_time_ms,
                "error": h.error
            }
            for name, h in results.items()
        }, indent=2))
    else:
        from contextcore.tui import ContextCoreTUI
        app = ContextCoreTUI(
            initial_screen="status",
            auto_refresh=watch
        )
        app.run()
```

### 2. Module Init (tui/__init__.py)
```python
\"\"\"
ContextCore Terminal User Interface.

This module provides an interactive TUI for ContextCore installation,
configuration, and monitoring.

Usage:
    from contextcore.tui import ContextCoreTUI
    
    app = ContextCoreTUI()
    app.run()

CLI:
    contextcore tui launch
    contextcore tui install
    contextcore tui status
\"\"\"

from .app import ContextCoreTUI, get_env_config

__all__ = [
    "ContextCoreTUI",
    "get_env_config",
]

__version__ = "0.1.0"
```

### 3. Screens Init (tui/screens/__init__.py)
```python
\"\"\"TUI Screen definitions.\"\"\"

from .welcome import WelcomeScreen
from .install import InstallScreen
from .status import StatusScreen
from .configure import ConfigureScreen
from .help import HelpScreen

__all__ = [
    "WelcomeScreen",
    "InstallScreen", 
    "StatusScreen",
    "ConfigureScreen",
    "HelpScreen",
]
```

### 4. Widgets Init (tui/widgets/__init__.py)
```python
\"\"\"TUI Widget components.\"\"\"

from .navigation_card import NavigationCard
from .service_card import ServiceCard
from .config_input import ConfigInput
from .prerequisites import PrerequisitesChecker
from .progress import DeploymentProgress

__all__ = [
    "NavigationCard",
    "ServiceCard",
    "ConfigInput",
    "PrerequisitesChecker",
    "DeploymentProgress",
]
```

### 5. Utils Init (tui/utils/__init__.py)
```python
\"\"\"TUI Utility functions.\"\"\"

from .health_checker import ServiceHealthChecker, ServiceHealth
from .config import load_config, save_config

__all__ = [
    "ServiceHealthChecker",
    "ServiceHealth",
    "load_config",
    "save_config",
]
```

### 6. Help Screen (screens/help.py)
Simple help/documentation screen:
```python
class HelpScreen(Screen):
    \"\"\"Help and documentation screen.\"\"\"
    
    BINDINGS = [("escape", "app.pop_screen", "Back")]
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Markdown(HELP_TEXT)
        yield Footer()

HELP_TEXT = \"\"\"
# ContextCore TUI Help

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit application |
| `?` | Show this help |
| `Esc` | Go back / Cancel |
| `d` | Toggle dark/light mode |

## Screens

### Welcome
The landing screen with navigation to all features.

### Install  
Guided installation wizard for setting up the observability stack.

### Status
Real-time health monitoring of all services.

### Configure
View and edit environment configuration.

## Getting Started

1. Run `contextcore tui install` to set up the stack
2. Use `contextcore tui status` to monitor health
3. Open Grafana at http://localhost:3000

## More Information

- Documentation: https://github.com/contextcore/contextcore
- Report issues: https://github.com/contextcore/contextcore/issues
\"\"\"
```

### 7. Auto Installer (installer.py)
Non-interactive installer for CI/CD:
```python
\"\"\"Non-interactive installation for CI/CD.\"\"\"

import subprocess
import sys
from typing import Optional

def run_auto_install(method: str = "docker") -> bool:
    \"\"\"Run automated installation.
    
    Args:
        method: Deployment method (docker, kind, custom)
        
    Returns:
        True if installation succeeded
    \"\"\"
    print(f"Running automated {method} installation...")
    
    if method == "docker":
        # Run make full-setup
        result = subprocess.run(
            ["make", "full-setup"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False
            
    elif method == "kind":
        # Run kind setup script
        result = subprocess.run(
            ["./scripts/create-cluster.sh"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False
            
    # Run verification
    result = subprocess.run(
        ["contextcore", "install", "verify"],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    
    return result.returncode == 0
```

## Output
Provide:
1. cli/tui.py - CLI commands
2. tui/__init__.py - Module init
3. tui/screens/__init__.py - Screens init
4. tui/widgets/__init__.py - Widgets init
5. tui/utils/__init__.py - Utils init
6. tui/screens/help.py - Help screen
7. tui/installer.py - Non-interactive installer

Mark file separations clearly.
"""


# =============================================================================
# Workflow Runner
# =============================================================================

def run_workflow(task_description: str, feature_name: str) -> dict:
    """Run Lead Contractor workflow for a feature."""
    try:
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow
    except ImportError:
        print("Error: startd8 SDK not found.")
        print("Install via: pip install startd8")
        print("Or set $STARTD8_SDK_ROOT environment variable (source contextcore-beaver/env.sh)")
        return {
            "feature": feature_name,
            "success": False,
            "final_implementation": "",
            "summary": {},
            "error": "startd8 SDK not found",
            "total_cost": 0,
            "total_iterations": 0,
        }

    print(f"\n{'='*70}")
    print(f"Running Lead Contractor: {feature_name}")
    print(f"{'='*70}\n")

    workflow = LeadContractorWorkflow()

    config = {
        "task_description": task_description,
        "context": TUI_CONTEXT,
        "lead_agent": LEAD_AGENT,
        "drafter_agent": DRAFTER_AGENT,
        "max_iterations": MAX_ITERATIONS,
        "pass_threshold": PASS_THRESHOLD,
        "integration_instructions": TUI_INTEGRATION,
    }

    try:
        result = workflow.run(config=config)
    except Exception as e:
        print(f"Workflow execution error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "feature": feature_name,
            "success": False,
            "final_implementation": "",
            "summary": {},
            "error": str(e),
            "total_cost": 0,
            "total_iterations": 0,
        }

    # Handle None or missing output
    if result is None:
        return {
            "feature": feature_name,
            "success": False,
            "final_implementation": "",
            "summary": {},
            "error": "Workflow returned None result",
            "total_cost": 0,
            "total_iterations": 0,
        }

    # Safely extract output
    output = result.output if (hasattr(result, 'output') and result.output) else {}
    
    # Safely extract metrics
    total_cost = 0
    if hasattr(result, 'metrics') and result.metrics:
        try:
            total_cost = result.metrics.total_cost if hasattr(result.metrics, 'total_cost') else 0
        except (AttributeError, TypeError):
            total_cost = 0
    
    # Safely extract metadata
    total_iterations = 0
    if hasattr(result, 'metadata') and result.metadata:
        try:
            total_iterations = result.metadata.get("total_iterations", 0) if isinstance(result.metadata, dict) else 0
        except (AttributeError, TypeError):
            total_iterations = 0
    
    return {
        "feature": feature_name,
        "success": result.success if hasattr(result, 'success') else False,
        "final_implementation": output.get("final_implementation", "") if isinstance(output, dict) else "",
        "summary": output.get("summary", {}) if isinstance(output, dict) else {},
        "error": result.error if hasattr(result, 'error') else None,
        "total_cost": total_cost,
        "total_iterations": total_iterations,
    }


def extract_code_blocks(text: str) -> List[Dict[str, str]]:
    """Extract code blocks with file markers."""
    files = []
    
    if not text or not isinstance(text, str):
        return files
    
    try:
        # First, try to find code blocks with file markers inside them
        # Pattern: ```python\n# === FILE: path ===\n...code...```
        code_block_pattern = r'```(python|css|tcss)\n(.*?)```'
        
        for match in re.finditer(code_block_pattern, text, re.DOTALL):
            try:
                lang = match.group(1)
                block_content = match.group(2)
                
                # Look for file marker inside the code block
                file_marker_pattern = r'(?:#|/\*)\s*===\s*FILE:\s*([^\s=]+(?:\s+[^\s=]+)*)\s*===\s*(?:\*/)?'
                file_match = re.search(file_marker_pattern, block_content)
                
                if file_match:
                    path = file_match.group(1).strip()
                    # Remove the file marker line from the code
                    code = re.sub(file_marker_pattern, '', block_content, count=1).strip()
                    if path and code:
                        files.append({
                            "path": path,
                            "content": code
                        })
            except (IndexError, AttributeError) as e:
                # Skip malformed matches
                continue
        
        # If we found files via markers, return them
        if files:
            return files
        
        # Fallback: extract all code blocks without markers
        code_pattern = r'```(?:python|css|tcss)?\n(.*?)```'
        matches = re.findall(code_pattern, text, re.DOTALL)
        if matches:
            # Try to infer file names from content or use defaults
            for i, code in enumerate(matches):
                try:
                    # Check if code contains file marker
                    file_marker_pattern = r'(?:#|/\*)\s*===\s*FILE:\s*([^\s=]+(?:\s+[^\s=]+)*)\s*===\s*(?:\*/)?'
                    file_match = re.search(file_marker_pattern, code)
                    if file_match:
                        path = file_match.group(1).strip()
                        code = re.sub(file_marker_pattern, '', code, count=1).strip()
                        if path and code:
                            files.append({"path": path, "content": code})
                    else:
                        # Default naming
                        ext = ".py" if "python" in code[:100] else ".css"
                        if code.strip():
                            files.append({
                                "path": f"output_{i}{ext}",
                                "content": code.strip()
                            })
                except (IndexError, AttributeError):
                    # Skip malformed code blocks
                    continue
    except Exception as e:
        print(f"Error extracting code blocks: {e}")
        return []
    
    return files


def save_result(result: dict, output_dir: Path):
    """Save workflow result to files."""
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error creating output directory {output_dir}: {e}")
        return
    
    slug = result.get("feature", "unknown").replace(" ", "_").lower()
    
    # Save metadata
    try:
        meta_file = output_dir / f"{slug}_result.json"
        with open(meta_file, "w") as f:
            json.dump({
                "feature": result.get("feature", "unknown"),
                "success": result.get("success", False),
                "summary": result.get("summary", {}),
                "error": result.get("error"),
                "total_cost": result.get("total_cost", 0),
                "total_iterations": result.get("total_iterations", 0),
                "timestamp": datetime.now().isoformat(),
            }, f, indent=2)
        print(f"Saved metadata: {meta_file}")
    except Exception as e:
        print(f"Error saving metadata: {e}")
    
    # Extract and save code files
    final_implementation = result.get("final_implementation", "")
    if final_implementation and isinstance(final_implementation, str):
        try:
            files = extract_code_blocks(final_implementation)
            
            if files:
                for file_info in files:
                    try:
                        file_path = output_dir / file_info.get("path", "unknown.py")
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        content = file_info.get("content", "")
                        with open(file_path, "w") as f:
                            f.write(content)
                        print(f"Saved code: {file_path}")
                    except Exception as e:
                        print(f"Error saving code file {file_info.get('path', 'unknown')}: {e}")
            else:
                print("Warning: No code files extracted from implementation")
        except Exception as e:
            print(f"Error extracting code blocks: {e}")
    else:
        print("Warning: No final_implementation to extract")
    
    # Also save raw implementation
    try:
        raw_file = output_dir / f"{slug}_raw.md"
        with open(raw_file, "w") as f:
            f.write(final_implementation if isinstance(final_implementation, str) else "")
        print(f"Saved raw: {raw_file}")
    except Exception as e:
        print(f"Error saving raw file: {e}")


def main():
    """Run Lead Contractor workflow for TUI features."""
    features = [
        (FEATURE_1_CORE_APP, "Feature_1_Core_App"),
        (FEATURE_2_WELCOME_SCREEN, "Feature_2_Welcome_Screen"),
        (FEATURE_3_INSTALL_WIZARD, "Feature_3_Install_Wizard"),
        (FEATURE_4_STATUS_DASHBOARD, "Feature_4_Status_Dashboard"),
        (FEATURE_5_CONFIGURE_SCREEN, "Feature_5_Configure_Screen"),
        (FEATURE_6_CLI_INTEGRATION, "Feature_6_CLI_Integration"),
    ]
    
    # Check which feature to run
    if len(sys.argv) > 1:
        try:
            idx = int(sys.argv[1]) - 1
            if 0 <= idx < len(features):
                features = [features[idx]]
            else:
                print(f"Invalid feature index. Use 1-{len(features)}")
                print("\nAvailable features:")
                for i, (_, name) in enumerate(features, 1):
                    print(f"  {i}. {name}")
                sys.exit(1)
        except ValueError:
            print("Usage: python run_lead_contractor_tui.py [feature_number]")
            print("\nAvailable features:")
            for i, (_, name) in enumerate(features, 1):
                print(f"  {i}. {name}")
            sys.exit(1)
    
    print(f"\n{'='*70}")
    print("ContextCore TUI Implementation via Lead Contractor Workflow")
    print(f"{'='*70}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Features to run: {len(features)}")
    print()
    
    results = []
    for task, name in features:
        try:
            result = run_workflow(task, name)
            if not result:
                print(f"\nWarning: {name} returned None result")
                result = {
                    "feature": name,
                    "success": False,
                    "final_implementation": "",
                    "summary": {},
                    "error": "Workflow returned None",
                    "total_cost": 0,
                    "total_iterations": 0,
                }
            
            results.append(result)
            save_result(result, OUTPUT_DIR)
            
            print(f"\n{name} Result:")
            print(f"  Success: {result.get('success', False)}")
            print(f"  Iterations: {result.get('total_iterations', 0)}")
            print(f"  Cost: ${result.get('total_cost', 0):.4f}")
            if result.get("error"):
                print(f"  Error: {result['error']}")
                
        except Exception as e:
            print(f"\nError running {name}: {e}")
            import traceback
            traceback.print_exc()
            # Add failed result to list
            results.append({
                "feature": name,
                "success": False,
                "final_implementation": "",
                "summary": {},
                "error": str(e),
                "total_cost": 0,
                "total_iterations": 0,
            })
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    successful = sum(1 for r in results if r["success"])
    total_cost = sum(r["total_cost"] for r in results)
    
    print(f"Total features: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {len(results) - successful}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"\nGenerated code saved to: {OUTPUT_DIR}")
    
    # Post-processing instructions
    print(f"\n{'='*70}")
    print("NEXT STEPS")
    print(f"{'='*70}")
    print("""
All commands should be run from: ~/Documents/dev/ContextCore

1. Review generated code:
   cd ~/Documents/dev/ContextCore
   ls -la generated/tui/

2. Create the TUI module structure:
   cd ~/Documents/dev/ContextCore
   mkdir -p src/contextcore/tui/{screens,widgets,utils,styles}

3. Copy generated files to the appropriate locations:
   cd ~/Documents/dev/ContextCore
   # Copy files from generated/tui/ to src/contextcore/tui/

4. Activate virtual environment and add Textual dependency:
   cd ~/Documents/dev/ContextCore
   source .venv/bin/activate
   pip3 install textual>=0.47.0

5. Register TUI command in src/contextcore/cli/__init__.py:
   # Add these lines:
   from .tui import tui
   main.add_command(tui)

6. Test the TUI:
   cd ~/Documents/dev/ContextCore
   source .venv/bin/activate
   contextcore tui launch
""")


if __name__ == "__main__":
    main()
