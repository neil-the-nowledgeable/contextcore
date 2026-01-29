# ContextCore TUI Implementation Plan

**Purpose:** Add an interactive Terminal User Interface (TUI) to ContextCore for guided installation and configuration.

**Status:** Planning  
**Date:** 2026-01-22  
**Working Directory:** `~/Documents/dev/ContextCore`

---

## Quick Start: Run Lead Contractor Workflow

```bash
# Navigate to project directory
cd ~/Documents/dev/ContextCore

# Activate virtual environment
source .venv/bin/activate

# Run Lead Contractor to generate TUI code (all features)
python3 scripts/run_lead_contractor_tui.py

# Or run specific features (1-6)
python3 scripts/run_lead_contractor_tui.py 1   # Core App
python3 scripts/run_lead_contractor_tui.py 2   # Welcome Screen
python3 scripts/run_lead_contractor_tui.py 3   # Install Wizard
python3 scripts/run_lead_contractor_tui.py 4   # Status Dashboard
python3 scripts/run_lead_contractor_tui.py 5   # Configure Screen
python3 scripts/run_lead_contractor_tui.py 6   # CLI Integration

# Generated code output location:
# ~/Documents/dev/ContextCore/generated/tui/
```

---

## Executive Summary

The ContextCore CLI is powerful but can be overwhelming for new users. Adding a TUI will provide:
- **Guided installation wizard** - Step-by-step setup with validation at each stage
- **Interactive configuration** - Visual forms for environment variables and options
- **Real-time status monitoring** - Live dashboard showing service health
- **Better discoverability** - Explore commands and features visually

---

## Technology Choice: Textual

**Selected Framework:** [Textual](https://textual.textualize.io/) (Python)

### Why Textual?

| Criteria | Textual | Rich/Click | Urwid | Blessed |
|----------|---------|------------|-------|---------|
| Modern Python | ✅ Async, Python 3.8+ | ✅ | ❌ Older API | ❌ Node.js port |
| CSS Styling | ✅ Full CSS support | ❌ | ❌ | ❌ |
| Widgets | ✅ Rich widget library | ❌ | ⚠️ Basic | ⚠️ Basic |
| Testing | ✅ Pilot testing framework | ❌ | ❌ | ❌ |
| Maintenance | ✅ Active, Textualize team | ✅ | ⚠️ | ⚠️ |
| Click Integration | ✅ Same ecosystem | ✅ | ❌ | ❌ |

### Dependencies to Add

```bash
# From: ~/Documents/dev/ContextCore
pip3 install textual>=0.47.0
```

Or add to `pyproject.toml`:

```toml
# File: ~/Documents/dev/ContextCore/pyproject.toml
dependencies = [
    # ... existing ...
    "textual>=0.47.0",
]
```

---

## Architecture

```
src/contextcore/
├── cli/
│   └── __init__.py           # Add 'tui' command
├── tui/                       # NEW: TUI module
│   ├── __init__.py
│   ├── app.py                 # Main TUI application
│   ├── screens/               # Screen definitions
│   │   ├── __init__.py
│   │   ├── welcome.py         # Welcome/landing screen
│   │   ├── install.py         # Installation wizard
│   │   ├── configure.py       # Configuration screen
│   │   ├── status.py          # Status dashboard
│   │   └── help.py            # Help/documentation
│   ├── widgets/               # Custom widgets
│   │   ├── __init__.py
│   │   ├── service_card.py    # Service health card
│   │   ├── progress.py        # Installation progress
│   │   └── requirement.py     # Requirement status
│   ├── styles/                # CSS styling
│   │   └── app.tcss           # Application styles
│   └── utils.py               # TUI utilities
```

---

## Feature Breakdown

### 1. Welcome Screen (Landing)

**Purpose:** Entry point, navigation hub

```
┌─────────────────────────────────────────────────────────────┐
│  ╔═══════════════════════════════════════════════════════╗  │
│  ║   ██████╗ ██████╗ ███╗   ██╗████████╗███████╗██╗  ██╗ ║  │
│  ║  ██╔════╝██╔═══██╗████╗  ██║╚══██╔══╝██╔════╝╚██╗██╔╝ ║  │
│  ║  ██║     ██║   ██║██╔██╗ ██║   ██║   █████╗   ╚███╔╝  ║  │
│  ║  ██║     ██║   ██║██║╚██╗██║   ██║   ██╔══╝   ██╔██╗  ║  │
│  ║  ╚██████╗╚██████╔╝██║ ╚████║   ██║   ███████╗██╔╝ ██╗ ║  │
│  ║   ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝ ║  │
│  ╚═══════════════════════════════════════════════════════╝  │
│                                                             │
│  Project Management Observability Framework                 │
│  Tasks as spans • Unified telemetry • Zero manual reports   │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │ [I]nstall    │ │ [S]tatus     │ │ [C]onfigure  │         │
│  │ Guided setup │ │ Health check │ │ Environment  │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │ [D]emo       │ │ [H]elp       │ │ [Q]uit       │         │
│  │ Try it out   │ │ Documentation│ │ Exit TUI     │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
│                                                             │
│  Press key in brackets or click to navigate                 │
└─────────────────────────────────────────────────────────────┘
```

**Key Bindings:**
- `i` → Install wizard
- `s` → Status dashboard
- `c` → Configure environment
- `d` → Demo mode
- `h` → Help screen
- `q` → Quit

---

### 2. Installation Wizard

**Purpose:** Step-by-step guided installation with validation

**Steps:**

1. **Prerequisites Check**
   - Python version ≥3.9
   - Docker installed and running
   - kubectl available (optional)
   - Ports available (3000, 3100, 3200, 4317, 9009)

2. **Deployment Selection**
   - Docker Compose (recommended for solo dev)
   - Kind Cluster (Kubernetes patterns)
   - Custom (manual configuration)

3. **Environment Configuration**
   - OTLP endpoint
   - Grafana credentials
   - Service URLs

4. **Stack Deployment**
   - Real-time progress with log streaming
   - Service health polling
   - Retry on failure

5. **Verification & Seeding**
   - Run `contextcore install verify`
   - Seed metrics for dashboards
   - Show final status

```
┌───────────────────────────────────────────────────────────────┐
│  INSTALLATION WIZARD                              Step 2 of 5 │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  Select Deployment Method                                     │
│                                                               │
│  ○ Docker Compose (Recommended)                               │
│    Quick local development without Kubernetes complexity      │
│    Setup time: ~2 minutes                                     │
│                                                               │
│  ● Kind Cluster                                               │
│    Kubernetes-native development, multi-node scheduling       │
│    Setup time: ~5 minutes                                     │
│                                                               │
│  ○ Custom Configuration                                       │
│    Manually specify endpoints and services                    │
│    For existing infrastructure                                │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│  ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  40%              │
│  [Back]                          [Next]           [Cancel]    │
└───────────────────────────────────────────────────────────────┘
```

---

### 3. Status Dashboard

**Purpose:** Real-time monitoring of the observability stack

```
┌────────────────────────────────────────────────────────────────┐
│  STATUS DASHBOARD                    Last updated: 10s ago    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────┐ │
│  │  GRAFANA    │ │   TEMPO     │ │   MIMIR     │ │   LOKI   │ │
│  │   ✅ OK     │ │   ✅ OK     │ │   ✅ OK     │ │  ✅ OK   │ │
│  │ :3000       │ │ :3200       │ │ :9009       │ │  :3100   │ │
│  │ 45ms        │ │ 23ms        │ │ 67ms        │ │  34ms    │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────┘ │
│                                                                │
│  ┌─────────────┐ ┌─────────────┐                               │
│  │   ALLOY     │ │ OTLP gRPC   │                               │
│  │   ✅ OK     │ │   ✅ OK     │                               │
│  │ :12345      │ │ :4317       │                               │
│  │ 12ms        │ │ 8ms         │                               │
│  └─────────────┘ └─────────────┘                               │
│                                                                │
│  ────────────────────────────────────────────────────────────  │
│                                                                │
│  Installation Completeness: ████████████████████████ 100%     │
│  Critical Requirements:     25/25 ✅                          │
│                                                                │
│  [R]efresh    [O]pen Grafana    [V]erify    [B]ack            │
└────────────────────────────────────────────────────────────────┘
```

**Features:**
- Auto-refresh every 10s (configurable)
- Color-coded health status (green/yellow/red)
- Response time display
- Quick actions (open browser, run verify)

---

### 4. Configuration Screen

**Purpose:** View and edit environment configuration

```
┌───────────────────────────────────────────────────────────────┐
│  CONFIGURATION                                                │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  Endpoints                                                    │
│  ─────────────────────────────────────────────────────────── │
│  OTEL_EXPORTER_OTLP_ENDPOINT   │ localhost:4317        [Edit] │
│  GRAFANA_URL                   │ http://localhost:3000 [Edit] │
│  TEMPO_URL                     │ http://localhost:3200 [Edit] │
│  MIMIR_URL                     │ http://localhost:9009 [Edit] │
│  LOKI_URL                      │ http://localhost:3100 [Edit] │
│                                                               │
│  Credentials                                                  │
│  ─────────────────────────────────────────────────────────── │
│  GRAFANA_USER                  │ admin                 [Edit] │
│  GRAFANA_PASSWORD              │ ********              [Edit] │
│                                                               │
│  OTel Settings                                                │
│  ─────────────────────────────────────────────────────────── │
│  CONTEXTCORE_EMIT_MODE         │ dual                  [Edit] │
│    Options: dual | legacy | otel                              │
│                                                               │
│  [Save to .env]    [Reset to Defaults]    [Back]              │
└───────────────────────────────────────────────────────────────┘
```

---

### 5. Demo Mode

**Purpose:** Interactive demo data generation and exploration

**Features:**
- Generate sample projects with tasks
- Create realistic sprint data
- Show data flowing through the stack
- Open dashboards with populated data

---

## CLI Integration

### New Command: `contextcore tui`

```bash
# From: ~/Documents/dev/ContextCore
# (with venv activated: source .venv/bin/activate)

# Launch the TUI
contextcore tui

# Launch directly to a screen
contextcore tui --screen install
contextcore tui --screen status
contextcore tui --screen configure

# Non-interactive mode (for CI/CD)
contextcore tui install --auto  # Runs wizard with defaults
```

### Implementation in CLI

```python
# src/contextcore/cli/tui.py
import click

@click.group()
def tui():
    """Launch the ContextCore Terminal User Interface."""
    pass

@tui.command("launch")
@click.option("--screen", type=click.Choice(["welcome", "install", "status", "configure"]))
def launch(screen):
    """Launch the interactive TUI."""
    from contextcore.tui import ContextCoreTUI
    app = ContextCoreTUI()
    if screen:
        app.initial_screen = screen
    app.run()
```

---

## Implementation Phases

**All commands run from:** `~/Documents/dev/ContextCore`

### Phase 1: Core Framework (Week 1)
- [ ] Add Textual dependency
  ```bash
  cd ~/Documents/dev/ContextCore
  source .venv/bin/activate
  pip3 install textual>=0.47.0
  ```
- [ ] Create TUI module structure
  ```bash
  cd ~/Documents/dev/ContextCore
  mkdir -p src/contextcore/tui/{screens,widgets,utils,styles}
  touch src/contextcore/tui/__init__.py
  touch src/contextcore/tui/screens/__init__.py
  touch src/contextcore/tui/widgets/__init__.py
  touch src/contextcore/tui/utils/__init__.py
  ```
- [ ] Implement main app with screen routing
- [ ] Create base screen class
- [ ] Define CSS theme

### Phase 2: Welcome & Navigation (Week 1)
- [ ] Welcome screen with ASCII art logo
- [ ] Navigation cards/buttons
- [ ] Key bindings
- [ ] Help overlay

### Phase 3: Installation Wizard (Week 2)
- [ ] Prerequisites checker widget
- [ ] Deployment selector widget
- [ ] Configuration form
- [ ] Progress tracker with log streaming
- [ ] Verification step

### Phase 4: Status Dashboard (Week 2)
- [ ] Service health cards
- [ ] Auto-refresh worker
- [ ] Installation completeness display
- [ ] Quick action buttons

### Phase 5: Configuration Screen (Week 3)
- [ ] Environment variable editor
- [ ] .env file save/load
- [ ] Validation

### Phase 6: Polish & Testing (Week 3)
- [ ] Textual Pilot tests
  ```bash
  cd ~/Documents/dev/ContextCore
  source .venv/bin/activate
  python3 -m pytest tests/test_tui.py
  ```
- [ ] Error handling
- [ ] Accessibility
- [ ] Documentation

---

## User Stories

1. **As a new user**, I want a guided installation so I don't miss any steps.
2. **As a developer**, I want to quickly check if all services are healthy.
3. **As a team lead**, I want to configure ContextCore for my team's infrastructure.
4. **As a demo presenter**, I want to showcase ContextCore's features interactively.

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Installation completion rate | >90% (vs ~60% CLI) |
| Time to first task tracked | <5 minutes |
| User satisfaction | 4.5/5 |
| Support tickets | -50% |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Textual learning curve | Medium | Reference existing TUI patterns |
| Terminal compatibility | Low | Textual handles cross-platform |
| Feature creep | Medium | Strict phase gates |
| Performance | Low | Async operations throughout |

---

## References

- [Textual Documentation](https://textual.textualize.io/)
- [ContextCore Installation Guide](../docs/INSTALLATION.md)
- [Existing CLI Implementation](../src/contextcore/cli/)
- [OpenCode TUI (inspiration)](https://github.com/sst/opencode)
