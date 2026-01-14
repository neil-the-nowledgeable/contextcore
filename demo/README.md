# ContextCore Demo: microservices-demo Integration

This demo showcases ContextCore's value proposition using Google's [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo) (microservices-demo) as the target application.

## Overview

The demo demonstrates three key capabilities:

1. **Tasks as Spans**: Generate realistic project history (epics, stories, tasks) as OpenTelemetry spans, viewable in Grafana Tempo
2. **ProjectContext CRDs**: Link project metadata to Kubernetes deployments for all 11 microservices
3. **Value-Based Observability**: Derive monitoring configuration from business criticality

## Quick Start

### Prerequisites

- [kind](https://kind.sigs.k8s.io/) - Kubernetes in Docker
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [helm](https://helm.sh/)
- Python 3.9+ with contextcore installed

### 1. Deploy the Demo Environment

```bash
# Full deployment (cluster + observability + microservices-demo)
./demo/setup/deploy.sh

# Or step by step:
./demo/setup/deploy.sh --cluster-only
./demo/setup/deploy.sh --observability-only
./demo/setup/deploy.sh --demo-only
./demo/setup/deploy.sh --dashboards-only
```

### 2. Generate Demo Project Data

```bash
# Generate 3-month project history
contextcore demo generate --project online-boutique

# With a fixed seed for reproducibility
contextcore demo generate --seed 42
```

### 3. Load Data to Tempo

```bash
# Load generated spans
contextcore demo load --file ./demo_output/demo_spans.json
```

### 4. Explore in Grafana

Open http://localhost:3000 (admin/admin) and navigate to:

- **ContextCore: Project Progress** - Epic/story/task visualization
- **ContextCore: Sprint Metrics** - Velocity and cycle time trends
- **ContextCore: Project-to-Operations** - Runtime correlation with project context

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Demo Architecture                                  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Historical Project Data                           │   │
│  │                                                                       │   │
│  │  contextcore demo generate                                            │   │
│  │         │                                                             │   │
│  │         ▼                                                             │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │   │
│  │  │ EPIC-001        │    │ Sprint 1-6      │    │ TASK-0001..0200 │  │   │
│  │  │ Platform Dev    │───▶│ 2-week cycles   │───▶│ Per-service     │  │   │
│  │  │ (3 months)      │    │ with velocity   │    │ with blockers   │  │   │
│  │  └─────────────────┘    └─────────────────┘    └─────────────────┘  │   │
│  │                                                          │            │   │
│  │                                                          ▼            │   │
│  │                                                   demo_spans.json     │   │
│  └──────────────────────────────────────────────────────────┼───────────┘   │
│                                                              │                │
│                        contextcore demo load                 │                │
│                                                              ▼                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Observability Stack                             │   │
│  │                                                                       │   │
│  │  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐  │   │
│  │  │   Tempo   │    │Prometheus │    │  Grafana  │    │   Loki    │  │   │
│  │  │  (traces) │    │ (metrics) │    │(dashboards│    │  (logs)   │  │   │
│  │  └───────────┘    └───────────┘    └───────────┘    └───────────┘  │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Kubernetes Cluster (Kind)                         │   │
│  │                                                                       │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │              ProjectContext CRDs (11 services)                  │ │   │
│  │  │                                                                  │ │   │
│  │  │  frontend-context      checkoutservice-context    cartservice   │ │   │
│  │  │  productcatalog-ctx    paymentservice-context     currency-ctx  │ │   │
│  │  │  shippingservice-ctx   emailservice-context       recommend-ctx │ │   │
│  │  │  adservice-context     loadgenerator-context                    │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                              │                                        │   │
│  │                              ▼                                        │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │              Online Boutique (11 Microservices)                 │ │   │
│  │  │                                                                  │ │   │
│  │  │  frontend (Go)         checkoutservice (Go)    cartservice (C#) │ │   │
│  │  │  productcatalog (Go)   paymentservice (Node)   currencyserv     │ │   │
│  │  │  shippingserv (Go)     emailservice (Python)   recommendserv    │ │   │
│  │  │  adservice (Java)      loadgenerator (Python)                   │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Services Overview

| Service | Language | Criticality | Business Value | P99 Latency |
|---------|----------|-------------|----------------|-------------|
| frontend | Go | critical | revenue-primary | 500ms |
| checkoutservice | Go | critical | revenue-primary | 200ms |
| cartservice | C# | critical | revenue-primary | 100ms |
| productcatalogservice | Go | high | revenue-primary | 150ms |
| paymentservice | Node.js | critical | revenue-primary | 300ms |
| currencyservice | Node.js | high | enabler | 50ms |
| shippingservice | Go | high | revenue-secondary | 100ms |
| emailservice | Python | medium | enabler | 1000ms |
| recommendationservice | Python | medium | revenue-secondary | 200ms |
| adservice | Java | medium | revenue-secondary | 300ms |
| loadgenerator | Python | low | internal | - |

## Generated Data

### Project Structure

The demo generates a compressed 3-month project timeline:

- **1 Epic**: "Online Boutique Platform Development"
- **11 Stories**: One per microservice
- **~200 Tasks**: Design, implementation, testing, deployment, observability per service
- **6 Sprints**: 2-week sprints with realistic velocity variance
- **Blockers**: ~15% of tasks experience blocking events

### Task Types

- Design spikes (ADRs, API contracts)
- Implementation stories
- Testing tasks
- Deployment configurations
- Observability setup

### Blocker Scenarios

- API design review delays
- Upstream service changes
- Infrastructure setup pending
- Security review waiting
- Third-party dependency issues

## CLI Commands

```bash
# List available microservices
contextcore demo services

# Generate project history
contextcore demo generate [OPTIONS]
  --project TEXT      Project identifier (default: online-boutique)
  --output TEXT       Output directory (default: ./demo_output)
  --months INT        Duration in months (default: 3)
  --seed INT          Random seed for reproducibility
  --format TEXT       Output format: json|otlp

# Load spans to Tempo
contextcore demo load [OPTIONS]
  --file PATH         JSON spans file (required)
  --endpoint TEXT     OTLP endpoint (default: localhost:4317)
  --insecure/--secure Use insecure connection

# Full environment setup
contextcore demo setup [OPTIONS]
  --cluster-name TEXT     Kind cluster name
  --skip-cluster          Use existing cluster
  --skip-observability    Skip Grafana stack
  --skip-demo             Skip microservices-demo
```

## Directory Structure

```
demo/
├── README.md                     # This file
├── dashboards/
│   ├── project-progress.json     # Task/epic visualization
│   ├── sprint-metrics.json       # Velocity and cycle time
│   └── project-operations.json   # Runtime correlation
├── manifests/
│   ├── base/
│   │   └── kustomization.yaml    # Upstream manifests
│   └── overlays/
│       └── contextcore/
│           └── kustomization.yaml # Adds annotations
├── projectcontexts/
│   ├── frontend.yaml
│   ├── checkoutservice.yaml
│   ├── cartservice.yaml
│   ├── productcatalogservice.yaml
│   ├── paymentservice.yaml
│   ├── currencyservice.yaml
│   ├── shippingservice.yaml
│   ├── emailservice.yaml
│   ├── recommendationservice.yaml
│   ├── adservice.yaml
│   └── loadgenerator.yaml
└── setup/
    ├── kind-cluster.yaml         # Kind configuration
    └── deploy.sh                 # Deployment script
```

## Exploring the Demo

### TraceQL Queries

View tasks in Tempo using TraceQL:

```traceql
# All epics
{task.type="epic" && project.id="online-boutique"}

# Blocked tasks
{task.status="blocked"}

# Tasks for frontend service
{task.title=~".*frontend.*"}

# In-progress tasks
{task.status="in_progress"}
```

### ProjectContext Resources

```bash
# List all ProjectContext resources
kubectl get projectcontext -n online-boutique

# Describe a specific context
kubectl describe projectcontext frontend-context -n online-boutique

# View annotations on deployments
kubectl get deployment frontend -n online-boutique -o yaml | grep contextcore
```

### Grafana Dashboards

1. **Project Progress**: Overview of epics, stories, tasks, and blockers
2. **Sprint Metrics**: Velocity trends, WIP limits, cycle time analysis
3. **Project-to-Operations**: Correlate project context with runtime metrics

## Troubleshooting

### Cluster Creation Fails

```bash
# Check Docker is running
docker info

# Delete existing cluster
kind delete cluster --name contextcore-demo

# Retry
./demo/setup/deploy.sh --cluster-only
```

### Spans Not Appearing in Tempo

```bash
# Check Tempo is running
kubectl get pods -n observability -l app.kubernetes.io/name=tempo

# Check OTLP port forwarding
kubectl port-forward svc/tempo -n observability 4317:4317

# Retry load
contextcore demo load --file ./demo_output/demo_spans.json
```

### Grafana Dashboards Missing

```bash
# Re-import dashboards
./demo/setup/deploy.sh --dashboards-only
```

## Next Steps

1. **Modify ProjectContext**: Edit YAMLs in `demo/projectcontexts/` and re-apply
2. **Add Custom Tasks**: Use `contextcore task start` CLI commands
3. **Explore Correlations**: Link runtime traces to project tasks
4. **Build Your Own**: Use this demo as a template for your own projects
