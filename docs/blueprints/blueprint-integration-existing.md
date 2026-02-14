# ContextCore Integration with Existing OTel Blueprints

> **Phase 2 Deliverable**: How ContextCore patterns enhance existing OTel Blueprint categories.

---

## Overview

ContextCore patterns complement and extend existing OTel Blueprint categories. This document maps ContextCore capabilities to active OTel projects, showing how project management observability enhances each domain.

---

## Integration Matrix

| OTel Project/Blueprint | ContextCore Enhancement | Value Added |
|------------------------|------------------------|-------------|
| **Kubernetes SemConv** | ProjectContext CRD, namespace-level context | Business metadata on K8s resources |
| **CI/CD Phase 2** | Task-pipeline correlation, build context | Link deployments to project tasks |
| **Gen AI** | Agent insight telemetry, session tracking | Structured AI decision persistence |
| **Service & Deployment** | Business criticality propagation | Value-based observability config |
| **Security SemConv** | Risk tracking, compliance context | Risk-aware sampling and alerting |
| **System SemConv** | Resource requirements from project context | SLO derivation from business needs |

---

## 1. Kubernetes Semantic Conventions Integration

### Current State
Kubernetes SemConv defines attributes for pods, deployments, namespaces, and nodes. Resource attributes like `k8s.namespace.name`, `k8s.deployment.name` provide infrastructure context.

### ContextCore Enhancement

**Add ProjectContext CRD as first-class resource:**

```yaml
# Proposed addition to k8s namespace
k8s.projectcontext.name: string     # ProjectContext CRD name
k8s.projectcontext.namespace: string # Namespace containing the CRD

# Derived attributes propagated to all resources in namespace
project.id: string                   # From ProjectContext.spec.project.id
business.criticality: string         # From ProjectContext.spec.business.criticality
business.owner: string               # From ProjectContext.spec.business.owner
```

**Use Case: Namespace-Level Business Context**

```yaml
# Current: Resource attributes on a pod
k8s.namespace.name: "commerce"
k8s.deployment.name: "checkout-service"
k8s.pod.name: "checkout-service-abc123"

# Enhanced with ContextCore: Business context included
k8s.namespace.name: "commerce"
k8s.deployment.name: "checkout-service"
k8s.projectcontext.name: "checkout-context"
project.id: "commerce-platform"
business.criticality: "critical"
business.owner: "commerce-team"
```

**Value Proposition:**

| Persona | Without ContextCore | With ContextCore |
|---------|---------------------|------------------|
| SRE | "Pod is crashing" | "Critical revenue service owned by commerce-team is crashing" |
| Platform | Manual tagging of business context | Auto-propagated from CRD |
| Security | No risk context on workloads | Risk priority attached to alerts |

### Proposed Blueprint Section

```markdown
## Kubernetes Blueprint: Business Context Integration

### Challenge
Infrastructure telemetry lacks business context, making incident prioritization difficult.

### Guiding Policy
Attach business metadata at namespace level via ProjectContext CRD,
propagate to all workloads automatically.

### Coherent Action
1. Deploy ProjectContext CRD to cluster
2. Create ProjectContext per namespace with business metadata
3. Configure OTel Collector to enrich spans with CRD attributes
4. Update alert routing rules to use business.criticality
```

---

## 2. CI/CD Phase 2 Integration

### Current State
CI/CD SemConv (in development) defines attributes for pipelines, jobs, and artifacts. Focus is on build and deployment observability.

### ContextCore Enhancement

**Link pipelines to project tasks:**

```yaml
# CI/CD attributes (existing/proposed)
cicd.pipeline.id: string
cicd.pipeline.name: string
cicd.job.id: string
cicd.artifact.id: string

# ContextCore correlation attributes
task.id: string              # Task that triggered this pipeline
task.ids: string[]           # All tasks included in this deployment
project.id: string           # Project context
sprint.id: string            # Sprint context (for release tracking)
```

**Use Case: Deployment-to-Task Traceability**

```
┌─────────────────────────────────────────────────────────────┐
│  Task Span (PROJ-123)                                       │
│  ├── status: in_progress                                    │
│  └── events: [created, in_progress, in_review]              │
│                                                             │
│      ┌─────────────────────────────────────────────────┐    │
│      │  Pipeline Span (pipeline-456)                   │    │
│      │  ├── task.id: PROJ-123                          │    │
│      │  ├── cicd.pipeline.name: "deploy-prod"          │    │
│      │  └── status: success                            │    │
│      │                                                 │    │
│      │      ┌─────────────────────────────────────┐    │    │
│      │      │  Job Span (build)                   │    │    │
│      │      └─────────────────────────────────────┘    │    │
│      │      ┌─────────────────────────────────────┐    │    │
│      │      │  Job Span (test)                    │    │    │
│      │      └─────────────────────────────────────┘    │    │
│      │      ┌─────────────────────────────────────┐    │    │
│      │      │  Job Span (deploy)                  │    │    │
│      │      └─────────────────────────────────────┘    │    │
│      └─────────────────────────────────────────────────┘    │
│                                                             │
│  └── events: [..., deployed, done]                          │
└─────────────────────────────────────────────────────────────┘
```

**Correlation Pattern:**

```python
# Extract task ID from commit message or branch name
def extract_task_id(commit_message: str) -> str:
    """Extract PROJ-123 style task IDs from commit messages."""
    match = re.search(r'([A-Z]+-\d+)', commit_message)
    return match.group(1) if match else None

# In CI/CD pipeline instrumentation
task_ids = [extract_task_id(c.message) for c in commits]
task_ids = [t for t in task_ids if t]  # Filter None

span.set_attribute("task.ids", task_ids)
span.set_attribute("project.id", get_project_from_repo())
```

**Value Proposition:**

| Persona | Without ContextCore | With ContextCore |
|---------|---------------------|------------------|
| Developer | "Build failed" | "Build for PROJ-123 failed" |
| PM | Manual deployment tracking | Auto-update task status on deploy |
| Release Mgr | "What's in this release?" | Query: `{ cicd.pipeline.id = X } | task.ids` |

### Proposed Blueprint Section

```markdown
## CI/CD Blueprint: Task Correlation

### Challenge
Deployments disconnected from project tasks, no automatic status updates.

### Guiding Policy
Extract task IDs from commits, link pipeline spans to task spans,
auto-complete tasks on successful deployment.

### Coherent Action
1. Configure commit message convention (PROJ-123 prefix)
2. Add task extraction to CI pipeline instrumentation
3. Set up webhook to update task status on pipeline completion
4. Link deployment spans as children of task spans
```

---

## 3. Gen AI Integration

### Current State
Gen AI SemConv defines attributes for LLM calls: `gen_ai.system`, `gen_ai.request.model`, token counts, etc. Focus is on model invocation telemetry.

### ContextCore Enhancement

**Add agent-level telemetry above individual LLM calls:**

```yaml
# Existing Gen AI attributes (per LLM call)
gen_ai.system: "anthropic"
gen_ai.request.model: "claude-3-opus"
gen_ai.usage.input_tokens: 1500
gen_ai.usage.output_tokens: 500

# ContextCore agent layer (per session/task)
agent.id: string                    # Unique agent identifier
agent.session.id: string            # Conversation/session ID
agent.insight.type: enum            # decision | lesson | question | handoff
agent.insight.summary: string       # Human-readable summary
agent.insight.confidence: float     # 0.0-1.0 confidence score
agent.insight.applies_to: string[]  # Files/modules affected
```

**Telemetry Hierarchy:**

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Session Span                                         │
│  ├── agent.id: "claude-code"                                │
│  ├── agent.session.id: "session-789"                        │
│  ├── project.id: "my-project"                               │
│  │                                                          │
│  │   ┌──────────────────────────────────────────────────┐   │
│  │   │  LLM Call Span                                   │   │
│  │   │  ├── gen_ai.system: "anthropic"                  │   │
│  │   │  ├── gen_ai.request.model: "claude-opus-4"       │   │
│  │   │  └── gen_ai.usage.total_tokens: 2000             │   │
│  │   └──────────────────────────────────────────────────┘   │
│  │   ┌──────────────────────────────────────────────────┐   │
│  │   │  Insight Span (decision)                         │   │
│  │   │  ├── agent.insight.type: "decision"              │   │
│  │   │  ├── agent.insight.summary: "Selected FastAPI"   │   │
│  │   │  └── agent.insight.confidence: 0.88              │   │
│  │   └──────────────────────────────────────────────────┘   │
│  │   ┌──────────────────────────────────────────────────┐   │
│  │   │  LLM Call Span                                   │   │
│  │   │  └── ...                                         │   │
│  │   └──────────────────────────────────────────────────┘   │
│  │                                                          │
│  └─────────────────────────────────────────────────────────┘
```

**Value Proposition:**

| Persona | Without ContextCore | With ContextCore |
|---------|---------------------|------------------|
| AI/ML Team | Token costs per call | Decisions per project, ROI per insight |
| Developer | Agent context lost between sessions | Query prior decisions before coding |
| Compliance | No audit trail of AI reasoning | Full trace of agent decision-making |

### Proposed Blueprint Section

```markdown
## Gen AI Blueprint: Agent Memory and Coordination

### Challenge
AI agent decisions don't persist, leading to repeated context gathering
and inconsistent recommendations across sessions.

### Guiding Policy
Store agent insights (decisions, lessons, questions) as spans in trace
storage, query prior context before making new decisions.

### Coherent Action
1. Wrap LLM calls in agent session spans
2. Emit insight spans for significant decisions
3. Query prior insights at session start
4. Implement handoff protocol for agent-to-agent transitions
```

---

## 4. Service & Deployment SemConv Integration

### Current State
Service SemConv defines `service.name`, `service.namespace`, `service.version`. Deployment SemConv (in development) adds deployment environment context.

### ContextCore Enhancement

**Propagate business metadata to service identity:**

```yaml
# Existing service attributes
service.name: "checkout-service"
service.namespace: "commerce"
service.version: "1.2.3"
deployment.environment: "production"

# ContextCore business context
business.criticality: "critical"
business.owner: "commerce-team"
business.value: "revenue-primary"
business.cost_center: "CC-4521"

# Derived observability config
observability.trace_sampling: 1.0      # Derived from criticality
observability.alert_priority: "P1"     # Derived from criticality
observability.retention: "90d"         # Derived from compliance
```

**Value-Based Configuration Derivation:**

```python
class ServiceObservabilityConfig:
    """Derive observability config from business metadata."""

    CRITICALITY_TO_SAMPLING = {
        "critical": 1.0,
        "high": 0.5,
        "medium": 0.1,
        "low": 0.01
    }

    CRITICALITY_TO_ALERT_PRIORITY = {
        "critical": "P1",
        "high": "P2",
        "medium": "P3",
        "low": "P4"
    }

    def derive(self, project_context: ProjectContext) -> dict:
        criticality = project_context.business.criticality

        return {
            "trace_sampling": self.CRITICALITY_TO_SAMPLING[criticality],
            "alert_priority": self.CRITICALITY_TO_ALERT_PRIORITY[criticality],
            "metrics_interval": self._derive_metrics_interval(criticality),
            "retention": self._derive_retention(project_context.business.compliance)
        }
```

**Value Proposition:**

| Persona | Without ContextCore | With ContextCore |
|---------|---------------------|------------------|
| Platform | Manual config per service | Auto-derived from business metadata |
| FinOps | Uniform sampling = wasted spend | Cost scales with business value |
| SRE | All alerts same priority | Critical services get P1 routing |

### Proposed Blueprint Section

```markdown
## Service Blueprint: Value-Based Observability

### Challenge
Observability configuration doesn't reflect business importance,
leading to over-instrumentation of low-value services.

### Guiding Policy
Derive sampling rates, alert priorities, and retention from business
criticality declared in ProjectContext.

### Coherent Action
1. Add business.criticality to service resource attributes
2. Configure OTel Collector sampling based on criticality
3. Set up AlertManager routing rules using business.owner
4. Configure retention policies per criticality tier
```

---

## 5. Security SemConv Integration

### Current State
Security SemConv (in development) focuses on vulnerability attributes, security events, and threat detection telemetry.

### ContextCore Enhancement

**Link security telemetry to project risk context:**

```yaml
# Existing security attributes (proposed)
security.vulnerability.id: "CVE-2024-1234"
security.vulnerability.severity: "critical"
security.event.type: "authentication_failure"

# ContextCore risk context
risk.type: "security"
risk.priority: "P1"
risk.mitigation: "ADR-015-input-validation"
risk.status: "mitigated"

# Project compliance context
business.compliance: "pci"
business.data_classification: "sensitive"
```

**Risk-Aware Alerting:**

```yaml
# AlertManager config derived from risk context
routes:
  - match:
      risk.priority: P1
      risk.type: security
    receiver: security-oncall-immediate
    group_wait: 0s

  - match:
      risk.priority: P2
      risk.type: security
    receiver: security-oncall-standard
    group_wait: 5m
```

**Value Proposition:**

| Persona | Without ContextCore | With ContextCore |
|---------|---------------------|------------------|
| Security | Alerts without project context | Risk priority + mitigation links in alerts |
| Compliance | Manual risk tracking | Queryable risk telemetry with status |
| Auditor | Separate risk documentation | Risk context attached to runtime events |

---

## 6. System SemConv Integration

### Current State
System SemConv defines attributes for processes, containers, hosts. Focus is on system-level resource telemetry.

### ContextCore Enhancement

**Connect system resources to SLO requirements:**

```yaml
# Existing system attributes
process.cpu.utilization: 0.75
process.memory.usage: 1073741824
container.cpu.limit: 2.0
container.memory.limit: 4294967296

# ContextCore requirements context
requirement.latency_p99: "200ms"
requirement.availability: "99.95"
requirement.throughput: "1000rps"
requirement.error_budget: "0.05"

# Derived alerts (from requirements + system)
alert: process.cpu.utilization > 0.8 for service with requirement.availability > 99.9
```

**SLO Derivation Pattern:**

```python
def generate_slo_alerts(project_context: ProjectContext) -> list:
    """Generate Prometheus alerts from SLO requirements."""
    alerts = []

    if project_context.requirements.latency_p99:
        threshold_ms = parse_duration(project_context.requirements.latency_p99)
        alerts.append({
            "alert": f"{project_context.project.id}_latency_p99",
            "expr": f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{service="{project_context.project.id}"}}[5m])) > {threshold_ms/1000}',
            "labels": {
                "severity": project_context.business.criticality,
                "owner": project_context.business.owner
            }
        })

    return alerts
```

---

## Summary: Cross-Cutting Patterns

ContextCore introduces three cross-cutting patterns that enhance all existing blueprints:

### Pattern A: Business Context Propagation

**Applies to**: All blueprints
**Mechanism**: ProjectContext CRD → Resource attributes → Spans/Metrics/Logs
**Benefit**: Every telemetry signal carries business context for filtering and routing

### Pattern B: Value-Based Configuration

**Applies to**: Kubernetes, Service, Security blueprints
**Mechanism**: Business metadata → Derived observability config
**Benefit**: Observability investment scales with business importance

### Pattern C: Cross-Domain Correlation

**Applies to**: CI/CD, Gen AI, System blueprints
**Mechanism**: `project.id` and `task.id` as correlation keys
**Benefit**: Trace from task → code → build → deploy → runtime

---

## Next Steps

1. **Propose attributes**: Submit ContextCore attributes to relevant SemConv SIGs
2. **Create integration examples**: Build reference implementations for each integration
3. **Validate with users**: Test patterns with end-user organizations
4. **Document in blueprints**: Add sections to official OTel Blueprint documentation
