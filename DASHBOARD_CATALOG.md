# ContextCore Dashboard Catalog

A comprehensive catalog of all Grafana dashboard JSON files in the ContextCore project.

---

## Primary Location: `grafana/provisioning/dashboards/`

Canonical dashboards organized by expansion pack subdirectory, auto-provisioned to Grafana.

### Task/Workflow Management

| File | Title | UID | Description |
|------|-------|-----|-------------|
| `core/project-tasks.json` | Project Tasks | `contextcore-tasks` | View project tasks as OpenTelemetry spans from Tempo |
| `beaver/beaver-lead-contractor-progress.json` | [BEAVER] Lead Contractor Progress | `contextcore-beaver-lead-contractor-progress` | Track project progress with Lead Contractor integration |
| `core/project-progress.json` | [CORE] ContextCore: Project Progress | `contextcore-core-contextcore-project-progress` | Track epics, stories, and tasks as OpenTelemetry spans |
| `core/sprint-metrics.json` | [CORE] ContextCore: Sprint Metrics | `contextcore-core-contextcore-sprint-metrics` | Track velocity, throughput, and sprint performance |

### Portfolio/Overview

| File | Title | UID | Description |
|------|-------|-----|-------------|
| `core/portfolio.json` | [CORE] Project Portfolio Overview | `contextcore-core-project-portfolio-overview` | Multi-project portfolio view with health indicators |

### Operations & Infrastructure

| File | Title | UID | Description |
|------|-------|-----|-------------|
| `core/installation.json` | [CORE] ContextCore Installation Status | `contextcore-core-contextcore-installation-status` | Self-monitoring dashboard for installation completeness |
| `core/project-operations.json` | [CORE] ContextCore: Project-to-Operations | `contextcore-core-contextcore-project-to-operations` | Correlate project context with runtime telemetry |
| `core/code-generation-health.json` | [CORE] Code Generation Health | `contextcore-code-gen-health` | Monitor code generation pipeline health |

### Agent & Automation

| File | Title | UID | Description |
|------|-------|-----|-------------|
| `fox/fox-alert-automation.json` | [FOX] Fox Alert Automation | `contextcore-fox-fox-alert-automation` | Alert context enrichment, criticality routing, and action telemetry |
| `external/agent-trigger.json` | [EXTERNAL] Agent Trigger | `contextcore-external-agent-trigger` | Dashboard for triggering Claude agent from Grafana |

### Skills & Capabilities

| File | Title | UID | Description |
|------|-------|-----|-------------|
| `squirrel/skills-browser.json` | [SQUIRREL] Skills Browser | `contextcore-squirrel-skills-browser` | Skills catalog browser |
| `squirrel/value-capabilities.json` | [SQUIRREL] Value Capabilities Explorer | `contextcore-squirrel-value-capabilities-explorer` | Explore value capabilities and skills |

### Deprecated

| File | Title | UID | Status |
|------|-------|-----|--------|
| `core/workflow.json` | [RABBIT] ContextCore Workflow Manager | `contextcore-workflow` | Replaced by `core/project-tasks.json`. Remove after confirming no references. |

---

## Other Locations

### `k8s/observability/dashboards/` (Kubernetes Deployment)

Copies of dashboards for Kubernetes ConfigMap deployment:

- `beaver-lead-contractor-progress.json`
- `installation.json`
- `portfolio.json`
- `project-operations.json`
- `project-progress.json`
- `sprint-metrics.json`
- `value-capabilities.json`
- `workflow.json` (stale - should be replaced with `project-tasks.json`)

### `demo/dashboards/` (Demo Data)

Dashboards bundled with demo scenarios:

- `project-operations.json`
- `project-progress.json`
- `sprint-metrics.json`

### `src/contextcore/dashboards/` (Python Package)

Embedded dashboards for programmatic provisioning:

- `installation.json`
- `portfolio.json`
- `value-capabilities.json`

### `contextcore-owl/plugins-new/` (Grafana Plugins)

Plugin development dashboards (not provisioned to production):

- `contextcore-chat-panel/provisioning/dashboards/dashboard.json` - Chat panel test dashboard
- `contextcore-workflow-panel/provisioning/dashboards/dashboard.json` - Workflow panel test dashboard

### `docs/dashboards/` (Documentation)

- `languagemodel1oh-site-launch-contextcore.json` - Documentation example

---

## Quick Reference: Task Management

**Looking for a task management dashboard?**

Use: `grafana/provisioning/dashboards/core/project-tasks.json`

**Project Tasks** dashboard features:
- Project task overview from Tempo traces
- Multi-project support via `$project` template variable
- 30-second auto-refresh
- 7-day default time range

**Access in Grafana:** `http://localhost:3000/d/contextcore-tasks`

---

## Dashboard Tags

| Tag | Dashboards |
|-----|------------|
| `contextcore` | All ContextCore dashboards |
| `beaver` | beaver-lead-contractor-progress.json |
| `startd8` | beaver-lead-contractor-progress.json |
| `fox` | fox-alert-automation.json |
| `waagosh` | fox-alert-automation.json |
| `alerts` | fox-alert-automation.json |
| `skills` | skills-browser.json |
| `squirrel` | skills-browser.json, value-capabilities.json |
| `value` | value-capabilities.json |
| `capabilities` | value-capabilities.json |
| `tasks` | project-tasks.json |
| `code-gen` | code-generation-health.json |
