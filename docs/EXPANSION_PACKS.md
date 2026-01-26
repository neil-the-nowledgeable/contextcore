# Expansion Packs

ContextCore expansion packs extend the core framework with specialized capabilities. Each pack follows the [animal naming convention](NAMING_CONVENTION.md) and integrates seamlessly with ContextCore's observability infrastructure.

## Design Boundaries

Understanding what each component IS and IS NOT is critical for maintaining clean architecture. These boundaries prevent scope creep and ensure each component serves its intended purpose.

### Core ContextCore (Asabikeshiinh - Spider)

**IS**:
- Project observability framework (tasks as OpenTelemetry spans)
- Dual-telemetry emission (spans to Tempo, logs to Loki)
- Agent insight storage and querying
- Project context management (CRDs, metadata)
- Dashboard provisioning for project health visualization

**IS NOT**:
- A communication channel between components
- An alert automation system (use Rabbit)
- An LLM provider (use Beaver)

### Rabbit (Waabooz) - Alert Automation

**IS**:
- A trigger mechanism to "wake up" systems in response to alerts
- Webhook receiver for alert payloads (Grafana, Alertmanager)
- Action dispatcher for automated responses
- One-way alert-to-action pipeline

**IS NOT**:
- A general communication channel between components
- A message bus or queue system
- A workflow orchestration engine
- A bi-directional RPC mechanism

**Key Design Principle**: Rabbit is for *triggering* actions, not *orchestrating* workflows. When an alert fires, Rabbit wakes up the appropriate handler. It does not manage ongoing conversations or coordinate multi-step processes.

### Fox (Waagosh) - Context Enrichment

**IS**:
- ContextCore integration layer for Rabbit
- Alert enrichment with project context (criticality, owner, SLOs)
- Intelligent routing based on project metadata

**IS NOT**:
- A standalone system (requires Rabbit)
- A replacement for Rabbit's core functionality

### Beaver (Amik) - LLM Abstraction

**IS**:
- Unified interface for LLM providers (OpenAI, Anthropic, local)
- Cost tracking and token accounting
- Rate limiting and retry logic
- Streaming support

**IS NOT**:
- A workflow orchestration engine
- A task management system (use Core ContextCore)

### Owl (Gookooko'oo) - Grafana Visualization

> **Note**: Owl is currently an internal sub-component, not a user-facing expansion pack.
> The name "contextcore-owl" is not official and should not be included in user onboarding,
> documentation, or the "harbor tour" of capabilities. It exists purely as an implementation
> detail for Grafana plugin development.

**IS**:
- Grafana plugins for ContextCore visualization
- Chat panels for interactive LLM queries
- Trigger panels for initiating actions (via Rabbit)
- Datasources for CORS-free API access
- **Internal tooling** (not user-facing)

**IS NOT**:
- A data storage layer
- A backend service
- The source of truth for workflows (that's Core ContextCore)
- **A user-facing product or capability**

### Squirrel (Ajidamoo) - Skills Library

**IS**:
- Token-efficient skill storage and discovery
- Progressive disclosure for agent capabilities
- Ready-to-use skills for common patterns

**IS NOT**:
- A runtime execution engine
- A replacement for ContextCore task tracking

---

## Official Expansion Packs

### contextcore-rabbit (Waabooz)

**Alert-Triggered Automation Framework**

*Formerly known as Hermes / Hermes Conrad*

| Field | Value |
|-------|-------|
| **Animal** | Rabbit |
| **Anishinaabe** | Waabooz |
| **Status** | Beta |
| **Repository** | [contextcore-rabbit](https://github.com/contextcore/contextcore-rabbit) |
| **License** | Equitable Use License v1.0 |

**Description**: Rabbit is a trigger mechanism that "wakes up" systems in response to alerts. It receives webhook payloads from monitoring systems (Grafana, Alertmanager), parses them into a unified format, and dispatches configured actions. Think of it as the alarm clock of the system—it doesn't manage the day, it just makes sure the right things wake up at the right time.

**Key Design Principle**: Rabbit is for *triggering*, not *orchestrating*. It handles the alert → action pipeline but does not:
- Manage ongoing workflows (use Core ContextCore for task tracking)
- Serve as a communication channel between components
- Coordinate multi-step processes (use Coyote for pipelines)

**Key Features**:
- Unified Alert model across alerting systems
- Pluggable payload parsers (Grafana, Alertmanager, extensible)
- Action framework with built-in actions (Log, Notify, Script, Wake Agent)
- Flask-based webhook server
- Optional OpenTelemetry integration
- Fire-and-forget action dispatch

**Installation**:
```bash
pip install contextcore-rabbit
```

**Quick Start**:
```python
from contextcore_rabbit import WebhookServer, Action, action_registry

# Start webhook server
server = WebhookServer(port=8080)
server.run()
```

---

### contextcore-fox (Waagosh)

**ContextCore Integration for Alert Automation**

| Field | Value |
|-------|-------|
| **Animal** | Fox |
| **Anishinaabe** | Waagosh |
| **Status** | Beta |
| **Repository** | [contextcore-fox](https://github.com/contextcore/contextcore-fox) |
| **License** | Equitable Use License v1.0 |
| **Depends On** | contextcore-rabbit |

**Description**: Fox is the ContextCore integration layer for alert automation. It builds on Rabbit and adds project context enrichment:

- **Project Context Enrichment**: Alerts enriched with criticality, owner, SLO targets
- **Intelligent Routing**: Critical projects route to Claude for analysis
- **ContextCore Telemetry**: Action spans emitted to observability stack

**Installation**:
```bash
pip install contextcore-fox  # Also installs contextcore-rabbit
```

**Quick Start**:
```python
from contextcore_fox import configure
from contextcore_fox.hermes import ProjectContextEnricher, ClaudeAction

# Configure with ContextCore integration
configure(
    contextcore_enabled=True,
    otel_endpoint="http://localhost:4317"
)

# Fox re-exports Rabbit's WebhookServer with ContextCore extensions
from contextcore_fox.hermes import BaseWebhookServer
server = BaseWebhookServer(port=8080)
server.run()
```

---

### contextcore-coyote (Wiisagi-ma'iingan)

**Multi-Agent Incident Resolution Pipeline**

*Formerly known as agent-pipeline*

| Field | Value |
|-------|-------|
| **Animal** | Coyote |
| **Anishinaabe** | Wiisagi-ma'iingan |
| **Status** | Beta |
| **Repository** | [contextcore-coyote](https://github.com/contextcore/contextcore-coyote) |
| **License** | Equitable Use License v1.0 |

**Description**: Coyote automates the debugging lifecycle through a multi-agent pipeline:

```
Error Detection → Investigation → Fix Design → Implementation → Testing → Knowledge Capture
```

Each stage is handled by a specialized agent:
- **Investigator**: Root cause analysis via stack traces, git blame, and o11y queries
- **Designer**: Fix specification with tradeoffs and alternatives
- **Implementer**: Production-quality code generation
- **Tester**: Validation and regression checking
- **Knowledge Agent**: Lessons learned capture

**Key Features**:
- Pipeline orchestration with optional human checkpoints
- Pre-built agent personalities with customizable prompts
- O11y integration (Prometheus, Loki, Tempo)
- Knowledge base for lessons learned
- ContextCore telemetry integration

**Installation**:
```bash
pip install contextcore-coyote

# With all integrations
pip install contextcore-coyote[all]
```

**Quick Start**:
```python
from contextcore_coyote import Pipeline, Incident

# Create incident from error
incident = Incident.from_error(
    error_message="TypeError: Cannot read property 'id' of undefined",
    source="production-logs",
)

# Run full pipeline
pipeline = Pipeline.full()
result = pipeline.run(incident)
print(result.summary())
```

---

### contextcore-beaver (Amik)

**LLM Provider Abstraction**

*Formerly known as startd8*

| Field | Value |
|-------|-------|
| **Animal** | Beaver |
| **Anishinaabe** | Amik |
| **Status** | Beta |
| **Repository** | [contextcore-beaver](https://github.com/contextcore/contextcore-beaver) |
| **License** | Equitable Use License v1.0 |

**Description**: Beaver is the LLM provider abstraction layer. It provides a unified interface for interacting with multiple LLM providers (OpenAI, Anthropic, local models) with built-in cost tracking, token accounting, and ContextCore telemetry integration.

**Key Features**:
- Unified provider interface (OpenAI, Anthropic, local models)
- Cost tracking and token accounting
- Rate limiting and retry logic
- Streaming support across providers
- ContextCore telemetry integration
- Workflow orchestration primitives

**Installation**:
```bash
pip install contextcore-beaver

# With specific providers
pip install contextcore-beaver[anthropic]
pip install contextcore-beaver[openai]
pip install contextcore-beaver[all]
```

**Quick Start**:
```python
from contextcore_beaver import LLMClient

# Unified interface across providers
client = LLMClient(provider="anthropic", model="claude-sonnet-4-20250514")
response = client.complete("Explain observability in one sentence")

# Built-in cost tracking
print(f"Cost: ${client.session_cost:.4f}")
print(f"Tokens: {client.session_tokens}")
```

---

### contextcore-owl (Gookooko'oo)

**Unified Grafana Plugin Package**

> ⚠️ **Internal Sub-Component**: Owl is not a user-facing expansion pack. The name
> "contextcore-owl" is unofficial and exists only as an internal code organization
> convention. Do not include Owl in user documentation, onboarding flows, or the
> "harbor tour" of ContextCore capabilities. Users interact with Grafana dashboards
> directly—they don't need to know about the plugin packaging.

| Field | Value |
|-------|-------|
| **Animal** | Owl |
| **Anishinaabe** | Gookooko'oo |
| **Status** | Internal (not user-facing) |
| **Repository** | [contextcore-owl](https://github.com/contextcore/contextcore-owl) |
| **License** | Equitable Use License v1.0 |
| **Depends On** | contextcore-beaver (optional, for scaffold script) |

**Description**: Owl is an internal package for Grafana plugin development. It consolidates all Grafana extensions—action trigger panels, chat panels, and datasources—into a single package with consistent branding and shared infrastructure.

**Key Features**:
- **contextcore-chat-panel**: Chat with Claude via webhook (ported from O11yBubo)
- **contextcore-action-trigger-panel**: Trigger Rabbit actions from dashboards (fire-and-forget)
- **contextcore-datasource**: Datasource with Grafana route proxy for CORS-free API calls
- **scaffold_plugin.py**: Generate new plugins using contextcore-beaver for LLM assistance

**Plugins Included**:
| Plugin ID | Type | Description |
|-----------|------|-------------|
| `contextcore-chat-panel` | Panel | Interactive chat panel for Claude via webhook |
| `contextcore-action-trigger-panel` | Panel | Fire Rabbit actions (wake agents, run scripts) |
| `contextcore-datasource` | Datasource | Proxied access to Rabbit API endpoints |

**Note**: The action trigger panel is for *initiating* Rabbit actions, not for managing workflows. To view project tasks, workflow history, and progress, use the Core ContextCore dashboards that query Tempo.

**Installation**:
```bash
# Clone and build
git clone https://github.com/contextcore/contextcore-owl
cd contextcore-owl
npm install
npm run build

# Copy to Grafana plugins directory
cp -r dist/* /var/lib/grafana/plugins/

# Or use Docker volume mount
docker run -v ./contextcore-owl/grafana/plugins:/var/lib/grafana/plugins grafana/grafana
```

**Docker Compose Integration**:
```yaml
grafana:
  volumes:
    - ./contextcore-owl/grafana/plugins:/var/lib/grafana/plugins
  environment:
    GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS: contextcore-chat-panel,contextcore-workflow-panel,contextcore-datasource
```

---

### contextcore-squirrel (Ajidamoo)

**Skills Library for Token-Efficient Agent Discovery**

*Formerly known as contextcore-skills*

| Field | Value |
|-------|-------|
| **Animal** | Squirrel |
| **Anishinaabe** | Ajidamoo |
| **Status** | Beta |
| **Repository** | [contextcore-squirrel](https://github.com/contextcore/contextcore-squirrel) |
| **License** | Equitable Use License v1.0 |

**Description**: Squirrel is the skills library for ContextCore. It provides ready-to-use skills that can be loaded into Tempo for token-efficient agent discovery. Skills use progressive disclosure—agents load minimal manifests first, then retrieve specific capabilities as needed.

**Key Features**:
- Token-efficient progressive disclosure (MANIFEST → index → capabilities)
- Ready-to-use skills (dev-tour-guide, capability-value-promoter)
- Agent-to-agent handoff protocols
- Infrastructure registry (prevents duplicate services)
- TraceQL-queryable skill storage
- Value Capabilities Dashboard integration

**Included Skills**:
| Skill | Purpose |
|-------|---------|
| **dev-tour-guide** | Onboarding guide for local development infrastructure |
| **capability-value-promoter** | Extract and communicate capability value to users |

**Installation**:
```bash
pip install contextcore-squirrel
```

**Quick Start**:
```bash
# Emit skills to Tempo
contextcore skill emit --path /path/to/skills/dev-tour-guide

# Query skills in Grafana (TraceQL)
{ name =~ "skill:.*" }

# Find capabilities by trigger
{ capability.triggers =~ ".*format.*" }
```

**Progressive Loading Pattern**:
```yaml
# Agent reads manifest first (~100 tokens)
cat skills/dev-tour-guide/MANIFEST.yaml

# Then loads specific capabilities as needed (~300-500 tokens each)
cat skills/dev-tour-guide/agent/capabilities/observability.yaml
```

---

## Creating an Expansion Pack

### Requirements

1. **Naming**: Follow the [naming convention](NAMING_CONVENTION.md)
2. **Integration**: Depend on `contextcore` and use its telemetry primitives
3. **License**: Use a compatible open-source license
4. **Documentation**: Include README with quick start and examples

### Recommended Structure

```
contextcore-{animal}/
├── pyproject.toml
├── README.md
├── LICENSE.md
├── CHANGELOG.md
├── src/contextcore_{animal}/
│   ├── __init__.py
│   ├── config.py           # Configuration management
│   └── ...                  # Feature modules
├── dashboards/             # Grafana dashboard JSON files
├── docs/
│   └── INTEGRATION.md
└── examples/
    └── basic_usage.py
```

### Integration Points

Expansion packs should integrate with ContextCore through:

1. **Task/Action Spans**: Emit spans for significant operations
2. **Project Context**: Use `ProjectContextDetector` to enrich telemetry
3. **Configuration**: Follow the pattern from `contextcore.config`
4. **Dashboards**: Provide Grafana dashboards that work with ContextCore's datasources

### pyproject.toml Template

```toml
[project]
name = "contextcore-{animal}"
version = "0.1.0"
description = "{Animal} ({Anishinaabe}) - {Brief description} for ContextCore"
readme = "README.md"
license = {text = "MIT"}  # or your chosen license
requires-python = ">=3.9"
dependencies = [
    "contextcore>=0.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "mypy>=1.0",
    "ruff>=0.1",
]

[project.urls]
Homepage = "https://github.com/contextcore/contextcore-{animal}"
Documentation = "https://github.com/contextcore/contextcore-{animal}#readme"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Submitting for Registry

To add your expansion pack to this registry:

1. Ensure it meets all requirements above
2. Open a PR to this repository adding your pack to this document
3. Include:
   - Brief description
   - Link to repository
   - Current status (alpha, beta, stable)
   - Animal name and Anishinaabe name (follow naming convention)

---

## Status Definitions

| Status | Meaning |
|--------|---------|
| **Planned** | Design phase, not yet implemented |
| **Alpha** | Experimental, API may change significantly |
| **Beta** | Feature-complete, API stabilizing |
| **Stable** | Production-ready, semantic versioning |
| **Deprecated** | No longer maintained, migration path provided |
