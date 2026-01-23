# Expansion Packs

ContextCore expansion packs extend the core framework with specialized capabilities. Each pack follows the [animal naming convention](NAMING_CONVENTION.md) and integrates seamlessly with ContextCore's observability infrastructure.

## Official Expansion Packs

### contextcore-rabbit (Waabooz)

**Core Alert Automation Framework**

*Formerly known as Hermes / Hermes Conrad*

| Field | Value |
|-------|-------|
| **Animal** | Rabbit |
| **Anishinaabe** | Waabooz |
| **Status** | Beta |
| **Repository** | [contextcore-rabbit](https://github.com/contextcore/contextcore-rabbit) |
| **License** | Equitable Use License v1.0 |

**Description**: Rabbit is the vendor-agnostic alert automation framework. It receives webhook payloads from monitoring systems (Grafana, Alertmanager), parses them into a unified format, and routes them through configurable action handlers.

**Key Features**:
- Unified Alert model across alerting systems
- Pluggable payload parsers (Grafana, Alertmanager, extensible)
- Action framework with built-in actions (Log, Notify, Script)
- Flask-based webhook server
- Optional OpenTelemetry integration

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
