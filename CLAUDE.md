# CLAUDE.md

This file provides guidance to Claude Code for the ContextCore project.

## Project Context

See @.contextcore.yaml for live project metadata including:
- Business criticality and ownership
- Active risks with priorities (P1-P4) and mitigations
- SLO requirements (availability, latency, throughput)
- Design decisions with confidence scores

### Quick Commands

- `/project-context` - Display full project context summary
- `/show-risks` - Show active risks sorted by priority

## Project Summary

**ContextCore** is a project management observability framework that models project tasks as OpenTelemetry spans. It eliminates manual status reporting by deriving project health from existing artifact metadata (commits, PRs, CI results) and exports via OTLP to any compatible backend.

**Core insight**: Tasks share the same structure as distributed trace spans—start time, end time, status, hierarchy, events. By storing tasks in observability infrastructure, you get unified querying, time-series persistence, and correlation with runtime telemetry.

**Architecture**: Dual-telemetry emission—spans to Tempo (hierarchy, timing, TraceQL) and structured logs to Loki (events, status changes, metrics derivation via recording rules). Mimir metrics are derived from Loki logs, not directly emitted.

## Tech Stack

- **Language**: Python 3.9+
- **CRD Framework**: kopf (Kubernetes Operator Framework)
- **Telemetry**: OpenTelemetry SDK, OTLP export
- **Reference Backend**: Grafana (Tempo, Mimir, Loki)
- **CLI**: Click
- **Models**: Pydantic v2

## Project Structure

```
ContextCore/
├── src/contextcore/
│   ├── __init__.py
│   ├── models.py            # Pydantic models for CRD spec
│   ├── tracker.py           # TaskTracker (tasks as spans)
│   ├── state.py             # Span state persistence
│   ├── metrics.py           # Derived project metrics
│   ├── logger.py            # TaskLogger (structured logs)
│   ├── detector.py          # OTel Resource Detector
│   ├── cli/                 # CLI commands (modular)
│   │   ├── install.py       # Installation verification
│   │   ├── task.py          # Task management
│   │   ├── demo.py          # Demo data generation
│   │   └── dashboards.py    # Dashboard provisioning
│   ├── dashboards/          # Dashboard provisioning
│   │   └── provisioner.py   # Grafana API dashboard provisioning
│   ├── agent/               # Agent communication layer
│   │   ├── insights.py      # InsightEmitter, InsightQuerier
│   │   ├── guidance.py      # GuidanceReader
│   │   ├── handoff.py       # Agent-to-agent handoffs
│   │   └── personalization.py
│   ├── compat/              # OTel compatibility layer
│   │   └── otel_genai.py    # Dual-emit for OTel GenAI conventions
│   ├── skill/               # Skill telemetry
│   ├── demo/                # Demo data generation
│   │   ├── generator.py     # HistoricalTaskTracker
│   │   └── exporter.py      # Dual-emit to Tempo/Loki
│   └── install/             # Installation verification
│       ├── requirements.py  # Verification requirements
│       └── verifier.py      # Verification engine
├── examples/                # Practical examples
│   ├── 01_basic_task_tracking.py
│   ├── 02_agent_insights.py
│   └── 03_artifact_status_derivation.py
├── grafana/provisioning/    # Grafana auto-provisioning
│   ├── dashboards/json/     # 6 provisioned dashboards
│   │   ├── portfolio.json
│   │   ├── installation.json
│   │   ├── value-capabilities.json
│   │   ├── project-progress.json
│   │   ├── sprint-metrics.json
│   │   └── project-operations.json
│   └── datasources/         # Datasource configs
├── crds/
│   └── projectcontext.yaml  # CRD definition
├── helm/contextcore/        # Helm chart
├── extensions/
│   └── vscode/              # VSCode extension
│       ├── src/             # TypeScript source
│       └── package.json     # Extension manifest
├── docs/
│   ├── semantic-conventions.md
│   ├── agent-semantic-conventions.md
│   ├── agent-communication-protocol.md
│   ├── OTEL_GENAI_MIGRATION_GUIDE.md  # OTel GenAI migration
│   ├── OTEL_GENAI_GAP_ANALYSIS.md     # Gap analysis
│   └── dashboards/          # Dashboard specifications
│       ├── PROJECT_PORTFOLIO_OVERVIEW.md
│       └── PROJECT_DETAILS.md
├── plans/                   # Phase implementation plans
│   └── PHASE4_UNIFIED_ALIGNMENT.md
├── .claude/                 # Claude Code configuration
│   ├── hooks/               # SessionStart and prompt hooks
│   ├── commands/            # Slash commands (/project-context, /show-risks)
│   ├── rules/               # Path-specific rules
│   └── settings.json        # Hook configuration
├── .contextcore.yaml        # Project context (risks, SLOs, decisions)
└── tests/
```

## System Requirements

**Python Command**: This system only has `python3`, not `python`. Always use:
- `python3` instead of `python`
- `pip3` instead of `pip`
- `python3 -m module` instead of `python -m module`

## Commands

```bash
# Install
pip3 install -e ".[dev]"

# Run tests
python3 -m pytest

# Type checking
mypy src/contextcore

# Linting
ruff check src/
black src/

# CLI usage
contextcore task start --id PROJ-123 --title "Feature" --type story
contextcore task update --id PROJ-123 --status in_progress
contextcore task complete --id PROJ-123
contextcore sprint start --id sprint-3 --name "Sprint 3"
contextcore metrics summary --project my-project

# Dashboard provisioning
contextcore dashboards provision                    # Auto-detect Grafana
contextcore dashboards provision --grafana-url URL  # Explicit Grafana URL
contextcore dashboards provision --dry-run          # Preview without applying
contextcore dashboards list                         # Show provisioned dashboards
contextcore dashboards delete                       # Remove ContextCore dashboards

# Installation verification (self-monitoring)
contextcore install init                            # Initialize and seed dashboard metrics
contextcore install verify                          # Full verification with telemetry
contextcore install verify --no-telemetry           # Skip emitting metrics
contextcore install verify --format json            # JSON output for automation
contextcore install verify --category infrastructure # Check specific category
contextcore install status                          # Quick status check (no telemetry)
```

## Installation Monitoring (Self-Monitoring)

ContextCore monitors its own installation status via the verification system. This enables observability of the observability stack itself.

### Quick Setup (Recommended)

Use the `make full-setup` command for a complete installation with dashboard data:

```bash
# Complete setup: start stack, wait for ready, seed metrics
make full-setup

# View dashboard
open http://localhost:3000/d/contextcore-installation
```

### Step-by-Step Setup

1. **Start the observability stack**:
   ```bash
   make up              # Start Docker Compose stack
   make wait-ready      # Wait for all services to be healthy
   ```

2. **Initialize ContextCore and seed metrics**:
   ```bash
   contextcore install init    # Verify + seed dashboard metrics
   # Or separately:
   make seed-metrics           # Just seed metrics to dashboard
   ```

3. **View dashboard**: Open `http://localhost:3000/d/contextcore-installation`

### Kubernetes Deployment

```bash
kubectl apply -k k8s/observability/
contextcore install init --endpoint tempo.observability:4317
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAFANA_URL` | `http://localhost:3000` | Grafana base URL |
| `GRAFANA_USER` | `admin` | Grafana admin username |
| `GRAFANA_PASSWORD` | `admin` | Grafana admin password |
| `TEMPO_URL` | `http://localhost:3200` | Tempo base URL |
| `MIMIR_URL` | `http://localhost:9009` | Mimir base URL |
| `LOKI_URL` | `http://localhost:3100` | Loki base URL |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `localhost:4317` | OTLP gRPC endpoint |
| `CONTEXTCORE_OTEL_MODE` | `dual` | OTel emit mode: `dual`, `legacy`, or `otel` |

### OTel GenAI Semantic Conventions

ContextCore is migrating to [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). The `CONTEXTCORE_OTEL_MODE` environment variable controls attribute emission:

| Mode | Behavior |
|------|----------|
| `dual` | Emits both `agent.*` (legacy) and `gen_ai.*` (OTel standard) - **default** |
| `legacy` | Emits only `agent.*` attributes (rollback option) |
| `otel` | Emits only `gen_ai.*` attributes (target state) |

See [docs/OTEL_GENAI_MIGRATION_GUIDE.md](docs/OTEL_GENAI_MIGRATION_GUIDE.md) for migration details.

### Metric Naming Convention

OTel metrics are converted to Prometheus format with unit suffixes:

| OTel Metric | Prometheus Metric |
|-------------|-------------------|
| `contextcore.install.completeness` (unit: %) | `contextcore_install_completeness_percent` |
| `contextcore.install.requirement.status` (unit: 1) | `contextcore_install_requirement_status_ratio` |
| `contextcore.install.verification.duration` (unit: ms) | `contextcore_install_verification_duration_milliseconds` |

See [docs/semantic-conventions.md](docs/semantic-conventions.md) for complete metric reference.

## Key Patterns

### Tasks as Spans

```python
from contextcore import TaskTracker

tracker = TaskTracker(project="my-project")
tracker.start_task(task_id="PROJ-123", title="Implement auth", task_type="story")
tracker.update_status("PROJ-123", "in_progress")  # Adds span event
tracker.complete_task("PROJ-123")  # Ends span
```

### Agent Insights

```python
from contextcore.agent import InsightEmitter, InsightQuerier

# Emit insights (stored as spans in Tempo)
emitter = InsightEmitter(project_id="checkout", agent_id="claude")
emitter.emit_decision("Selected event-driven architecture", confidence=0.92)

# Query insights from other agents
querier = InsightQuerier()
decisions = querier.query(project_id="checkout", insight_type="decision")
```

### ProjectContext CRD

```yaml
apiVersion: contextcore.io/v1
kind: ProjectContext
metadata:
  name: checkout-service
  namespace: commerce
spec:
  project:
    id: "commerce-platform"
    epic: "EPIC-42"
  business:
    criticality: critical
    owner: commerce-team
  requirements:
    availability: "99.95"
    latencyP99: "200ms"
  observability:
    traceSampling: 1.0
    alertChannels: ["commerce-oncall"]
```

## Environment Variables

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=contextcore
KUBECONFIG=~/.kube/config
```

## Must Do

- Use ProjectContext CRD as the source of truth for project metadata
- Derive observability config from business metadata (criticality → sampling rate)
- Include context in all generated artifacts (alerts, dashboards)
- Validate CRD schema strictly with Pydantic
- Export via OTLP (vendor-agnostic)
- **Provision dashboards on install**: ContextCore must auto-provision the Project Portfolio Overview and Project Details dashboards to Grafana during installation
- Dashboard provisioning must be idempotent (safe to run multiple times)
- Dashboards must use ContextCore semantic conventions for all queries

## Must Avoid

- Duplicating context in multiple places
- Manual annotation of K8s resources (use controller)
- Storing sensitive data in ProjectContext
- Over-generating artifacts (derive only what's needed)
- Vendor-specific code in core SDK

## Session Context (Dogfooding)

This project uses its own patterns for agent memory. ContextCore manages ContextCore.

### Query Prior Context

Before significant decisions, check what's been decided:

```python
from contextcore.agent import InsightQuerier

querier = InsightQuerier()
prior_decisions = querier.query(
    project_id="contextcore",
    insight_type="decision",
    time_range="30d"
)

# Check for lessons learned about specific files
lessons = querier.query(
    project_id="contextcore",
    insight_type="lesson",
    applies_to="src/contextcore/tracker.py"
)
```

### Emit Insights

After making decisions or learning something, persist for future sessions:

```python
from contextcore.agent import InsightEmitter

emitter = InsightEmitter(project_id="contextcore", agent_id="claude")

# Emit a decision
emitter.emit_decision(
    summary="Chose X over Y because Z",
    confidence=0.9,
    context={"file": "relevant/file.py"}
)

# Emit a lesson learned
emitter.emit_lesson(
    summary="Always mock OTLP exporter in unit tests",
    category="testing",
    applies_to=["src/contextcore/tracker.py"]
)
```

### Check Human Guidance

Query for constraints and open questions set by humans:

```python
from contextcore.agent import GuidanceReader

reader = GuidanceReader(project_id="contextcore")
constraints = reader.get_active_constraints()
questions = reader.get_open_questions()
```

## Expansion Pack Ecosystem

ContextCore uses an animal naming convention with Anishinaabe (Ojibwe) names honoring the indigenous peoples of Michigan and the Great Lakes region. See [docs/NAMING_CONVENTION.md](docs/NAMING_CONVENTION.md) for philosophy and guidelines.

| Package | Animal | Anishinaabe | Purpose |
|---------|--------|-------------|---------|
| **contextcore** | Spider | Asabikeshiinh | Core framework—tasks as spans, agent insights |
| **contextcore-rabbit** | Rabbit | Waabooz | Core alert automation framework (webhooks, parsers, actions) |
| **contextcore-fox** | Fox | Waagosh | ContextCore integration for alert automation (context enrichment) |
| **contextcore-coyote** | Coyote | Wiisagi-ma'iingan | Multi-agent incident resolution pipeline |
| **contextcore-beaver** | Beaver | Amik | LLM provider abstraction (formerly startd8) |
| **contextcore-squirrel** | Squirrel | Ajidamoo | Skills library for token-efficient agent discovery |

### Dependency Graph

```
contextcore-beaver (LLM abstraction)
         │
         ▼
contextcore-coyote (multi-agent pipeline)
         │
         ▼
contextcore-fox (context enrichment)        contextcore-squirrel (skills library)
         │                                           │
         ▼                                           │
contextcore-rabbit (alert automation)                │
         │                                           │
         └───────────────┬───────────────────────────┘
                         ▼
                    contextcore (core)
```

### Installation

```bash
# Core only
pip install contextcore

# With alert automation
pip install contextcore-rabbit

# With ContextCore-aware alerts
pip install contextcore-fox  # includes rabbit

# With multi-agent pipeline
pip install contextcore-coyote

# With LLM abstraction
pip install contextcore-beaver

# With skills library
pip install contextcore-squirrel
```

See [docs/EXPANSION_PACKS.md](docs/EXPANSION_PACKS.md) for full expansion pack documentation.

## Documentation

- [README.md](README.md) — Vision, benefits, quick start
- [CLAUDE-full.md](CLAUDE-full.md) — Extended documentation with diagrams
- [docs/semantic-conventions.md](docs/semantic-conventions.md) — Full attribute reference
- [docs/agent-semantic-conventions.md](docs/agent-semantic-conventions.md) — Agent attributes
- [docs/agent-communication-protocol.md](docs/agent-communication-protocol.md) — Agent integration
- [docs/OTEL_GENAI_MIGRATION_GUIDE.md](docs/OTEL_GENAI_MIGRATION_GUIDE.md) — OTel GenAI migration guide
- [docs/OTEL_GENAI_GAP_ANALYSIS.md](docs/OTEL_GENAI_GAP_ANALYSIS.md) — OTel GenAI gap analysis
- [docs/dashboards/PROJECT_PORTFOLIO_OVERVIEW.md](docs/dashboards/PROJECT_PORTFOLIO_OVERVIEW.md) — Portfolio dashboard spec
- [docs/dashboards/PROJECT_DETAILS.md](docs/dashboards/PROJECT_DETAILS.md) — Project details dashboard spec
- [docs/EXPANSION_PACKS.md](docs/EXPANSION_PACKS.md) — Expansion pack registry
- [docs/NAMING_CONVENTION.md](docs/NAMING_CONVENTION.md) — Animal naming convention

## Examples

The `examples/` directory contains practical demonstrations:

- `01_basic_task_tracking.py` — Task lifecycle management with spans
- `02_agent_insights.py` — Agent insight emission and querying
- `03_artifact_status_derivation.py` — Deriving project status from artifacts
