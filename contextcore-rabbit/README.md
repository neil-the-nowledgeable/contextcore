# ContextCore Rabbit (Waabooz)

Alert-triggered automation framework for ContextCore.

## Overview

Rabbit is a trigger mechanism that "wakes up" systems in response to alerts. It receives webhook payloads from monitoring systems (Grafana, Alertmanager), parses them into a unified format, and dispatches configured actions.

**Key Design Principle**: Rabbit is for *triggering*, not *orchestrating*. It handles the alert → action pipeline but does not manage ongoing workflows or conversations.

## Installation

```bash
pip install contextcore-rabbit
```

## Quick Start

```python
from contextcore_rabbit import WebhookServer, action_registry

# Start the server
server = WebhookServer(port=8082)
server.run()
```

## Built-in Actions

| Action | Description |
|--------|-------------|
| `log` | Log the trigger payload |
| `beaver_workflow` | Trigger Beaver Lead Contractor workflow |
| `beaver_workflow_dry_run` | Preview workflow steps |
| `beaver_workflow_status` | Get workflow run status |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/actions` | GET | List registered actions |
| `/trigger` | POST | Trigger an action directly |
| `/webhook/grafana` | POST | Handle Grafana alerts |
| `/webhook/alertmanager` | POST | Handle Alertmanager alerts |
| `/webhook/manual` | POST | Handle manual triggers |

## Usage with Grafana

The `contextcore-workflow-panel` in Grafana calls Rabbit's `/trigger` endpoint:

```json
POST /trigger
{
  "action": "beaver_workflow",
  "payload": { "project_id": "my-project" },
  "context": { "source": "grafana_panel" }
}
```

## License

Equitable Use License v1.0
