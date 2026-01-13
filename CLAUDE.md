# CLAUDE.md

This file provides guidance to Claude Code for the ContextCore project.

## Project Overview

**ContextCore** provides a unified metadata model from project initiation through operations using Kubernetes Custom Resource Definitions. It injects project management context (business value, design documents, requirements, risk signals) directly into the cluster alongside deployments, enabling enhanced observational and operational efficiencies.

## The Core Problem

Design-time knowledge is isolated from runtime operations:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         THE CONTEXT GAP                                      │
│                                                                              │
│   Project Management          │         Kubernetes/Operations               │
│   ─────────────────           │         ─────────────────────               │
│   • Business value            │         • Deployment specs                  │
│   • Design documents          │         • Service configs                   │
│   • Requirements              │         • Resource limits                   │
│   • Risk assessments          │         • Observability setup               │
│   • Task tracking             │         • Alerting rules                    │
│                               │                                              │
│           ↓                   │                  ↓                          │
│    Lives in Jira/Notion       │           Lives in YAML/Helm               │
│    Disconnected               │           No business context              │
│                               │                                              │
│   "What's the business        │         "Why is this service               │
│    value of this service?"    │          important?"                        │
│           🤷                   │                 🤷                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

## The Solution: ContextCore CRD

A Kubernetes-native approach that carries project context alongside workloads:

```yaml
apiVersion: contextcore.io/v1
kind: ProjectContext
metadata:
  name: checkout-service
  namespace: commerce
spec:
  # Link to project artifacts
  project:
    id: "commerce-platform"
    epic: "EPIC-42"
    tasks: ["TASK-789", "TASK-790"]

  # Design documentation
  design:
    doc: "https://docs.internal/checkout-redesign"
    adr: "ADR-015-event-driven-checkout"
    apiContract: "https://api.internal/checkout/v2/openapi.yaml"

  # Business context
  business:
    criticality: critical      # critical|high|medium|low
    value: revenue-primary     # revenue-primary|cost-reduction|compliance|enabler
    owner: commerce-team
    costCenter: "CC-4521"

  # Requirements (for SLO derivation)
  requirements:
    availability: "99.95"
    latencyP99: "200ms"
    errorBudget: "0.05"

  # Risk signals (for alert derivation)
  risks:
    - type: security
      description: "Handles PII and payment data"
      priority: P1
    - type: availability
      description: "Revenue impact if down"
      mitigation: "ADR-015"

  # Target K8s resources
  targets:
    - kind: Deployment
      name: checkout-service
    - kind: Service
      name: checkout-api

  # Observability strategy (or derived from above)
  observability:
    traceSampling: 1.0
    metricsInterval: "10s"
    dashboardPlacement: featured
    alertChannels: ["commerce-oncall", "pagerduty-p1"]
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PROJECT LAYER                                   │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐               │
│   │   Jira    │  │  Notion   │  │  GitHub   │  │   ADRs    │               │
│   │  Issues   │  │   Docs    │  │  Issues   │  │           │               │
│   └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘               │
│         └──────────────┴───────┬──────┴──────────────┘                      │
│                                │ contextcore sync                           │
└────────────────────────────────┼────────────────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           KUBERNETES LAYER                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      ProjectContext CRD                               │  │
│  │   Single source of truth for project + operational context            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│         │                                                                    │
│         │ contextcore-controller                                            │
│         ▼                                                                    │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │  Resource  │  │  Service   │  │ Prometheus │  │  Grafana   │           │
│  │Annotations │  │  Monitor   │  │   Rule     │  │ Dashboard  │           │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘           │
│                                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                            │
│  │ Deployment │  │  Service   │  │ ConfigMap  │  (annotated with context)  │
│  └────────────┘  └────────────┘  └────────────┘                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ OTel Resource Detector
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OBSERVABILITY LAYER                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │   Traces   │  │  Metrics   │  │   Logs     │  │   Alerts   │           │
│  │+project.*  │  │+project.*  │  │+project.*  │  │ w/context  │           │
│  │+business.* │  │+business.* │  │+business.* │  │            │           │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘           │
│                                                                              │
│  Every signal carries: business.criticality, project.design_doc,            │
│  project.owner, requirement.*, risk.* - queryable, groupable, actionable   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Value Proposition

### 1. Value-Based Observability Derivation

The controller generates observability artifacts from project metadata:

| Project Signal | Generated Artifact |
|----------------|-------------------|
| `business.criticality: critical` | 100% trace sampling, 10s metrics, P1 alerts |
| `business.value: revenue-primary` | SLO definition, error budget tracking |
| `requirements.latencyP99: 200ms` | PrometheusRule with latency alert |
| `risks[].type: security` | Extended audit logging, anomaly detection |
| `design.adr` | Runbook link in alert annotations |

### 2. Context-Rich Telemetry

All runtime telemetry automatically includes project context:

```json
{
  "trace_id": "abc123",
  "span_name": "checkout.processPayment",
  "attributes": {
    "k8s.deployment.name": "checkout-service",
    "project.id": "commerce-platform",
    "project.task": "TASK-789",
    "business.criticality": "critical",
    "business.value": "revenue-primary",
    "design.doc": "https://docs.internal/checkout",
    "design.adr": "ADR-015"
  }
}
```

### 3. Incident Context at Your Fingertips

When alerts fire, responders get immediate context:

```yaml
# Alert annotation (auto-generated from ProjectContext)
annotations:
  summary: "High latency on checkout-service"
  design_doc: "https://docs.internal/checkout-redesign"
  adr: "ADR-015-event-driven-checkout"
  business_criticality: "critical"
  business_value: "revenue-primary"
  owner: "commerce-team"
  runbook: "https://runbooks.internal/checkout-latency"
```

### 4. Unified Lifecycle Tracking

Project tasks become spans linked to runtime telemetry:

```
Epic: "Checkout Redesign" (span)
  └── Story: "Implement async flow" (span)
        └── Task: "Add event queue" (span)
              └── Deployment: checkout-service (K8s + OTel)
                    └── Runtime spans: processPayment, validateCart
```

## Tech Stack

- **Language**: Python 3.11+
- **CRD Framework**: kopf (Kubernetes Operator Framework)
- **Telemetry**: OpenTelemetry SDK
- **Protocol**: OTLP to Grafana Alloy
- **Storage**: Tempo (traces), Mimir (metrics), Loki (logs)
- **Visualization**: Grafana

## Project Structure

```
ContextCore/
├── CLAUDE.md                    # This file
├── README.md                    # Public documentation
├── pyproject.toml               # Python package config
├── src/
│   └── contextcore/
│       ├── __init__.py
│       ├── models.py            # Pydantic models for CRD spec
│       ├── controller.py        # kopf-based K8s controller
│       ├── detector.py          # OTel Resource Detector
│       ├── generators/
│       │   ├── servicemonitor.py
│       │   ├── prometheusrule.py
│       │   ├── dashboard.py
│       │   └── annotations.py
│       ├── sync/
│       │   ├── jira.py          # Jira → ProjectContext sync
│       │   ├── github.py        # GitHub Issues → ProjectContext
│       │   └── notion.py        # Notion → ProjectContext
│       └── cli.py               # CLI interface
├── crds/
│   └── projectcontext.yaml      # CRD definition
├── helm/
│   └── contextcore/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── crd.yaml
│           ├── deployment.yaml
│           ├── rbac.yaml
│           └── configmap.yaml
├── dashboards/
│   └── contextcore-overview.json
├── docs/
│   ├── semantic-conventions.md
│   └── value-propositions.yaml
└── tests/
```

## Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Apply CRD to cluster
kubectl apply -f crds/projectcontext.yaml

# Run controller locally (development)
python -m contextcore controller --kubeconfig ~/.kube/config

# Create ProjectContext from CLI
contextcore create \
  --name checkout-context \
  --namespace commerce \
  --project commerce-platform \
  --criticality critical \
  --design-doc "https://docs.internal/checkout"

# Sync from Jira
contextcore sync jira \
  --project COMMERCE \
  --namespace commerce

# Generate observability artifacts
contextcore generate \
  --context commerce/checkout-context \
  --output ./generated/

# Annotate existing deployment
contextcore annotate deployment/checkout-service \
  --context checkout-context
```

## Semantic Conventions

### Resource Attributes (on all telemetry)

```
# Project identity
project.id                    # Project identifier
project.epic                  # Epic ID
project.task                  # Current task ID

# Design artifacts
design.doc                    # URL to design document
design.adr                    # ADR identifier or URL
design.api_contract           # OpenAPI/AsyncAPI URL

# Business context
business.criticality          # critical|high|medium|low
business.value                # revenue-primary|cost-reduction|compliance|enabler
business.owner                # Owning team
business.cost_center          # Cost center code

# Requirements
requirement.availability      # Target availability %
requirement.latency_p99       # Target P99 latency
requirement.error_budget      # Error budget %

# Risk signals
risk.type                     # security|compliance|data-integrity|availability
risk.priority                 # P1|P2|P3|P4
risk.mitigation               # Mitigation ADR reference

# K8s context
k8s.projectcontext.name       # ProjectContext resource name
k8s.projectcontext.namespace  # ProjectContext namespace
```

## Development Phases

### Phase 1: CRD + Controller Foundation
- [ ] ProjectContext CRD schema
- [ ] kopf-based controller skeleton
- [ ] Resource annotation from ProjectContext
- [ ] OTel Resource Detector for context injection
- [ ] CLI for ProjectContext management

### Phase 2: Observability Derivation
- [ ] ServiceMonitor generation from criticality
- [ ] PrometheusRule generation from requirements
- [ ] Dashboard JSON generation
- [ ] Trace sampling configuration

### Phase 3: Project Tool Sync
- [ ] Jira sync adapter
- [ ] GitHub Issues sync adapter
- [ ] Notion sync adapter
- [ ] Bidirectional sync (runtime incidents → project tasks)

### Phase 4: Helm + Production
- [ ] Helm chart for controller deployment
- [ ] RBAC configuration
- [ ] High availability setup
- [ ] Documentation and examples

## Environment Variables

```bash
# Controller configuration
CONTEXTCORE_NAMESPACE=contextcore-system
CONTEXTCORE_LOG_LEVEL=info
KUBECONFIG=~/.kube/config

# OTel export
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=contextcore-controller

# Sync adapters
JIRA_URL=https://company.atlassian.net
JIRA_TOKEN=<token>
GITHUB_TOKEN=<token>
NOTION_TOKEN=<token>
```

## Key Design Decisions

### Why Kubernetes CRD?
- **Declarative**: Define desired state, controller reconciles
- **Native**: Works with existing K8s tooling (kubectl, GitOps)
- **Lifecycle**: Tied to cluster resources, not external systems
- **RBAC**: K8s-native access control
- **Audit**: K8s audit log captures all changes

### Why Not Just Annotations?
Annotations work for simple cases, but:
- No schema validation
- No controller reconciliation
- Scattered across resources
- Hard to query/aggregate
- No lifecycle management

ProjectContext CRD provides:
- Validated schema
- Single source of truth
- Controller-driven derivation
- Queryable via K8s API
- Proper lifecycle (create, update, delete)

### Why OTel Resource Detector?
Injecting context at the OTel level means:
- All signals (traces, metrics, logs) get context
- Works with any OTel-instrumented app
- No application code changes needed
- Context available in every query

## Integration Points

### With Existing Observability
ContextCore enhances, doesn't replace:
- **Grafana**: Dashboards grouped by business.value
- **Prometheus**: Alerts include project context
- **Tempo**: Traces filterable by project.id
- **Loki**: Logs queryable by business.criticality

### With GitOps
ProjectContext is just YAML:
- Store in Git alongside Helm charts
- Apply via ArgoCD/Flux
- Review context changes in PRs
- Version history of project metadata

### With Incident Management
When PagerDuty fires:
- Alert includes design_doc, adr, owner
- Responder has immediate context
- Post-incident can trace to originating task

## Must Do
- Use ProjectContext CRD as the source of truth
- Derive observability from project metadata
- Include context in all generated artifacts
- Validate schema strictly

## Must Avoid
- Duplicating context in multiple places
- Manual annotation of resources (use controller)
- Storing sensitive data in ProjectContext
- Over-generating artifacts (derive only what's needed)
