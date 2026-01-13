# ContextCore

**Unified metadata model from project initiation to operations via Kubernetes CRDs.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-CRD-326CE5)](https://kubernetes.io/)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-native-blueviolet)](https://opentelemetry.io/)

## The Problem

Design-time knowledge is isolated from runtime operations:

| Project Management | Kubernetes/Operations |
|--------------------|-----------------------|
| Business value | Deployment specs |
| Design documents | Service configs |
| Requirements | Resource limits |
| Risk assessments | Alerting rules |
| **Lives in Jira/Notion** | **Lives in YAML** |

When an alert fires at 2am, responders ask: *"What is this service? Why is it important? Where's the design doc?"* — and the answers are scattered across disconnected systems.

## The Solution

**ContextCore** uses a Kubernetes CRD to inject project management context directly into the cluster:

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
    tasks: ["TASK-789"]

  design:
    doc: "https://docs.internal/checkout-redesign"
    adr: "ADR-015-event-driven-checkout"

  business:
    criticality: critical
    value: revenue-primary
    owner: commerce-team

  requirements:
    availability: "99.95"
    latencyP99: "200ms"

  risks:
    - type: security
      description: "Handles PII and payment data"
      priority: P1

  targets:
    - kind: Deployment
      name: checkout-service
```

## Key Features

### Value-Based Observability Derivation

The controller auto-generates observability artifacts from project metadata:

| Project Signal | Generated Artifact |
|----------------|-------------------|
| `criticality: critical` | 100% trace sampling, 10s metrics, P1 alerts |
| `value: revenue-primary` | SLO definition, error budget tracking |
| `requirements.latencyP99` | PrometheusRule with latency alert |
| `risks[].type: security` | Extended audit logging |
| `design.adr` | Runbook link in alert annotations |

### Context-Rich Telemetry

All runtime telemetry automatically includes project context via OTel Resource Detector:

```python
from contextcore import ProjectContextDetector
from opentelemetry.sdk.resources import get_aggregated_resources
from opentelemetry.sdk.trace import TracerProvider

resource = get_aggregated_resources([ProjectContextDetector()])
provider = TracerProvider(resource=resource)

# Every span now includes:
# - project.id, project.epic
# - business.criticality, business.value
# - design.doc, design.adr
```

### Incident Context at Your Fingertips

Alerts include design docs, ADRs, and business context:

```yaml
annotations:
  summary: "High latency on checkout-service"
  design_doc: "https://docs.internal/checkout-redesign"
  adr: "ADR-015-event-driven-checkout"
  business_criticality: "critical"
  owner: "commerce-team"
```

## Quick Start

### Install

```bash
pip install contextcore
```

### Apply CRD

```bash
kubectl apply -f https://raw.githubusercontent.com/contextcore/contextcore/main/crds/projectcontext.yaml
```

### Create ProjectContext

```bash
contextcore create \
  --name checkout-context \
  --namespace commerce \
  --project commerce-platform \
  --criticality critical \
  --design-doc "https://docs.internal/checkout"
```

### Or via YAML

```yaml
apiVersion: contextcore.io/v1
kind: ProjectContext
metadata:
  name: checkout-context
  namespace: commerce
spec:
  project:
    id: "commerce-platform"
  business:
    criticality: critical
  targets:
    - kind: Deployment
      name: checkout-service
```

```bash
kubectl apply -f projectcontext.yaml
```

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         PROJECT LAYER                               │
│   Jira  ──  Notion  ──  GitHub  ──  ADRs                           │
│         └─────────────┬─────────────┘                              │
│                       │ contextcore sync                           │
└───────────────────────┼────────────────────────────────────────────┘
                        ▼
┌────────────────────────────────────────────────────────────────────┐
│                      KUBERNETES LAYER                               │
│                                                                     │
│   ┌──────────────────────────────────────────────────────────┐    │
│   │                  ProjectContext CRD                       │    │
│   │   Single source of truth for project + operational context│    │
│   └──────────────────────────────────────────────────────────┘    │
│                        │                                            │
│                        │ contextcore-controller                     │
│                        ▼                                            │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                 │
│   │ ServiceMon. │ │ Prom. Rule  │ │  Dashboard  │ (generated)     │
│   └─────────────┘ └─────────────┘ └─────────────┘                 │
│   ┌─────────────┐ ┌─────────────┐                                  │
│   │ Deployment  │ │   Service   │ (annotated with context)        │
│   └─────────────┘ └─────────────┘                                  │
└────────────────────────────────────────────────────────────────────┘
                        │
                        │ OTel Resource Detector
                        ▼
┌────────────────────────────────────────────────────────────────────┐
│                     OBSERVABILITY LAYER                             │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                 │
│   │ Traces  │ │ Metrics │ │  Logs   │ │ Alerts  │                 │
│   │+project │ │+project │ │+project │ │+context │                 │
│   └─────────┘ └─────────┘ └─────────┘ └─────────┘                 │
└────────────────────────────────────────────────────────────────────┘
```

## Commands

```bash
# Create ProjectContext
contextcore create --name my-context --project my-project --criticality high

# List ProjectContexts
kubectl get projectcontexts
kubectl get pctx  # short name

# Sync from Jira
contextcore sync jira --project MYPROJ --namespace default

# Generate observability artifacts
contextcore generate --context default/my-context --output ./generated/

# Annotate existing deployment
contextcore annotate deployment/my-app --context my-context

# Run controller locally
contextcore controller --kubeconfig ~/.kube/config
```

## Integrations

### GitOps

ProjectContext is just YAML — store it alongside your Helm charts:

```
my-app/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   └── service.yaml
└── projectcontext.yaml  # ← Versioned with your app
```

### Incident Management

When PagerDuty fires:
- Alert includes `design_doc`, `adr`, `owner`
- Responder has immediate context
- Post-incident traces to originating task

### Project Tools

Sync adapters for bidirectional updates:
- **Jira** → ProjectContext (requirements, tasks)
- **GitHub Issues** → ProjectContext (tasks)
- **Notion** → ProjectContext (design docs)
- **Runtime incidents** → Jira/GitHub (feedback loop)

## Why CRD?

| Approach | Problem |
|----------|---------|
| Annotations only | No schema, scattered, no lifecycle |
| External database | Disconnected from K8s, drift |
| ConfigMaps | No validation, no controller |

**ProjectContext CRD provides:**
- Schema validation
- Controller reconciliation
- Single source of truth
- K8s-native RBAC
- Audit logging
- GitOps compatible

## Requirements

- Kubernetes 1.24+
- Python 3.11+ (for CLI/controller)
- OpenTelemetry-compatible backend (optional)

## Installation

```bash
# CLI only
pip install contextcore

# With sync adapters
pip install contextcore[sync]

# Development
pip install contextcore[dev]
```

## Documentation

- [CLAUDE.md](CLAUDE.md) - Full technical documentation
- [Semantic Conventions](docs/semantic-conventions.md) - Attribute reference
- [CRD Schema](crds/projectcontext.yaml) - Full CRD specification

## License

MIT
