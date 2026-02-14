# Reusable Patterns for OTel Blueprints

> **Phase 1 Deliverable**: Extracted patterns and conventions from ContextCore that can be applied to other OTel Blueprint implementations.

---

## Pattern Catalog

### Pattern 1: Domain Objects as Spans

**Problem**: Domain-specific objects (tasks, orders, workflows) need lifecycle tracking but don't fit traditional request/response tracing.

**Solution**: Model domain objects with temporal lifecycle as OpenTelemetry spans.

**When to Use**:
- Objects have start time, end time, and status
- Objects form hierarchies (parent-child relationships)
- State transitions are important events
- Historical queries are needed

**Structure**:

```
┌────────────────────────────────────────────────────────────┐
│  Domain Object          OTel Span Mapping                  │
├────────────────────────────────────────────────────────────┤
│  object.id          →   span.name or attribute             │
│  object.created_at  →   span.start_time                    │
│  object.completed_at →  span.end_time                      │
│  object.status      →   span attribute + events            │
│  object.parent_id   →   span parent (trace hierarchy)      │
│  state transitions  →   span events                        │
│  metadata           →   span attributes                    │
└────────────────────────────────────────────────────────────┘
```

**Implementation**:

```python
# Generic pattern
class DomainObjectTracker:
    def __init__(self, tracer: Tracer, object_type: str):
        self.tracer = tracer
        self.object_type = object_type
        self.active_spans: Dict[str, Span] = {}

    def start(self, object_id: str, attributes: Dict) -> None:
        span = self.tracer.start_span(
            name=f"{self.object_type}.lifecycle",
            attributes={
                f"{self.object_type}.id": object_id,
                **attributes
            }
        )
        self.active_spans[object_id] = span

    def update_status(self, object_id: str, new_status: str) -> None:
        span = self.active_spans.get(object_id)
        if span:
            span.add_event(
                f"{self.object_type}.status_changed",
                attributes={"status": new_status}
            )
            span.set_attribute(f"{self.object_type}.status", new_status)

    def complete(self, object_id: str) -> None:
        span = self.active_spans.pop(object_id, None)
        if span:
            span.end()
```

**Reuse Examples**:
- **Order Processing**: `order.lifecycle` spans tracking order states
- **Workflow Engines**: `workflow.execution` spans with step children
- **Incident Management**: `incident.lifecycle` spans from detection to resolution
- **Approval Flows**: `approval.request` spans tracking approver actions

**Value Delivered**:
| Persona | Benefit |
|---------|---------|
| Operations | Query "all orders blocked > 1 hour" via TraceQL |
| Analytics | Time-series analysis of lifecycle durations |
| Compliance | Audit trail with timestamps for all state changes |

---

### Pattern 2: Value-Based Observability Derivation

**Problem**: Observability configuration (sampling, alerting, retention) doesn't reflect business importance, leading to over-instrumentation of low-value services and under-instrumentation of critical ones.

**Solution**: Derive observability configuration from business metadata.

**When to Use**:
- Services have varying business criticality
- Cost optimization requires differentiated instrumentation
- Alert prioritization should reflect business impact
- Compliance requires full tracing for certain workloads

**Derivation Rules**:

```yaml
# Input: Business metadata
business:
  criticality: critical | high | medium | low
  value: revenue-primary | revenue-secondary | cost-reduction | internal
  compliance: pci | hipaa | sox | none

# Output: Observability configuration
observability_derived:
  # From criticality
  trace_sampling:
    critical: 1.0      # 100% sampling
    high: 0.5          # 50% sampling
    medium: 0.1        # 10% sampling
    low: 0.01          # 1% sampling

  metrics_interval:
    critical: 10s
    high: 30s
    medium: 60s
    low: 120s

  alert_priority:
    critical: P1
    high: P2
    medium: P3
    low: P4

  # From compliance
  audit_logging:
    pci: extended      # Full request/response logging
    hipaa: extended
    sox: standard
    none: minimal

  retention:
    pci: 365d
    hipaa: 2555d       # 7 years
    sox: 2555d
    none: 30d
```

**Implementation**:

```python
class ObservabilityDeriver:
    SAMPLING_RATES = {
        "critical": 1.0,
        "high": 0.5,
        "medium": 0.1,
        "low": 0.01
    }

    def derive_config(self, project_context: ProjectContext) -> ObservabilityConfig:
        criticality = project_context.business.criticality

        return ObservabilityConfig(
            trace_sampling=self.SAMPLING_RATES.get(criticality, 0.1),
            alert_priority=self._derive_alert_priority(criticality),
            retention=self._derive_retention(project_context.business.compliance),
            # ... other derived values
        )
```

**Reuse Examples**:
- **Multi-tenant Platforms**: Tier-based observability (free vs. premium)
- **Microservices**: Critical path services get full sampling
- **Data Pipelines**: PII-containing pipelines get extended audit logging
- **Edge Services**: Low-criticality edge nodes get reduced sampling

**Value Delivered**:
| Persona | Benefit |
|---------|---------|
| Platform Team | Automated config, no manual tuning per service |
| FinOps | Cost scales with business value, not traffic |
| Security | Compliance requirements automatically enforced |

---

### Pattern 3: CRD as Source of Truth

**Problem**: Project/service metadata scattered across multiple systems (Jira, Confluence, CMDB, Kubernetes labels) with no authoritative source.

**Solution**: Use Kubernetes Custom Resource Definition as the canonical source, with controllers that propagate to other systems.

**When to Use**:
- Running on Kubernetes
- Multiple consumers need the same metadata
- Configuration changes should be auditable (GitOps)
- Metadata should be version-controlled

**Structure**:

```
┌─────────────────────────────────────────────────────────────┐
│                    ProjectContext CRD                        │
│                    (Source of Truth)                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
┌─────────────────┐ ┌───────────┐ ┌─────────────────┐
│ OTel Collector  │ │ Grafana   │ │ Alert Manager   │
│ (sampling)      │ │ (labels)  │ │ (routing)       │
└─────────────────┘ └───────────┘ └─────────────────┘
```

**CRD Design Principles**:

1. **Comprehensive**: Include all metadata any consumer might need
2. **Validated**: Use strict schema validation (Pydantic, JSON Schema)
3. **Namespaced**: One CRD per service/project, in the service's namespace
4. **Watchable**: Controllers react to changes via Kubernetes watch API

**Implementation**:

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: projectcontexts.contextcore.io
spec:
  group: contextcore.io
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          required: [spec]
          properties:
            spec:
              type: object
              required: [project, business]
              properties:
                project:
                  type: object
                  properties:
                    id: { type: string }
                    epic: { type: string }
                business:
                  type: object
                  properties:
                    criticality:
                      type: string
                      enum: [critical, high, medium, low]
                    owner: { type: string }
```

**Reuse Examples**:
- **Service Catalogs**: ServiceContext CRD with ownership, dependencies
- **Feature Flags**: FeatureContext CRD with rollout percentages
- **Data Pipelines**: PipelineContext CRD with SLOs, data classification
- **ML Models**: ModelContext CRD with versioning, performance thresholds

**Value Delivered**:
| Persona | Benefit |
|---------|---------|
| Platform Team | Single API for all metadata queries |
| GitOps | All config changes in version control |
| Auditors | Complete history via `kubectl get --show-managed-fields` |

---

### Pattern 4: Agent Telemetry Protocol

**Problem**: AI agent decisions and lessons learned disappear when sessions end, forcing repeated context-gathering and inconsistent recommendations.

**Solution**: Store agent insights as structured telemetry with defined semantic conventions.

**When to Use**:
- AI agents make decisions that affect future work
- Multiple agents need to coordinate
- Humans need to audit agent reasoning
- Agent-to-agent handoffs occur

**Insight Types**:

| Type | Purpose | Key Attributes |
|------|---------|----------------|
| `decision` | Architectural/implementation choice | `confidence`, `alternatives_considered` |
| `lesson` | Pattern learned from experience | `category`, `applies_to` |
| `question` | Unresolved item needing human input | `urgency`, `blocking` |
| `handoff` | Context for next agent/human | `recipient`, `context_summary` |

**Semantic Conventions**:

```yaml
# Required for all agent insights
agent.id: string              # Unique agent identifier
agent.session.id: string      # Session/conversation ID
agent.insight.type: enum      # decision | lesson | question | handoff
agent.insight.summary: string # Human-readable summary
agent.insight.timestamp: int  # Unix timestamp

# Type-specific attributes
# For decisions:
agent.insight.confidence: float      # 0.0-1.0
agent.insight.rationale: string
agent.insight.alternatives: string[] # Considered but rejected

# For lessons:
agent.insight.category: string       # testing | architecture | performance
agent.insight.applies_to: string[]   # File/module paths

# For questions:
agent.insight.urgency: enum          # blocking | high | medium | low
agent.insight.options: string[]      # Possible answers

# For handoffs:
agent.insight.recipient: string      # Next agent or human
agent.insight.context: string        # Serialized context
```

**Implementation**:

```python
class InsightEmitter:
    def emit_decision(
        self,
        summary: str,
        confidence: float,
        rationale: str,
        alternatives: List[str] = None
    ) -> str:
        span = self.tracer.start_span("agent.insight")
        span.set_attributes({
            "agent.id": self.agent_id,
            "agent.insight.type": "decision",
            "agent.insight.summary": summary,
            "agent.insight.confidence": confidence,
            "agent.insight.rationale": rationale,
        })
        if alternatives:
            span.set_attribute("agent.insight.alternatives", alternatives)
        span.end()
        return span.context.trace_id
```

**Query Patterns**:

```traceql
# All decisions for a project with high confidence
{ agent.insight.type = "decision" && agent.insight.confidence > 0.8 }

# Lessons learned about testing
{ agent.insight.type = "lesson" && agent.insight.category = "testing" }

# Unresolved blocking questions
{ agent.insight.type = "question" && agent.insight.urgency = "blocking" }
```

**Value Delivered**:
| Persona | Benefit |
|---------|---------|
| AI Agent | Access prior decisions via TraceQL before making new ones |
| Human Reviewer | Audit trail of all agent reasoning |
| Platform Team | Monitor agent decision patterns across projects |

---

### Pattern 5: Multi-Audience Dashboard Design

**Problem**: Different stakeholders need different views of the same underlying data, leading to dashboard proliferation or one-size-fits-none designs.

**Solution**: Design dashboard hierarchy with progressive disclosure from executive summary to task-level detail.

**When to Use**:
- Multiple personas consume project/service data
- Drill-down from summary to detail is needed
- Different time horizons matter to different audiences
- Both real-time and historical views are required

**Dashboard Hierarchy**:

```
┌─────────────────────────────────────────────────────────────┐
│  Level 1: Portfolio Overview (Executive)                    │
│  - Health matrix: all projects at a glance                  │
│  - Blocked count, velocity trend, risk summary              │
│  - Time range: 30 days                                      │
└─────────────────────────┬───────────────────────────────────┘
                          │ click project
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Level 2: Project Details (Manager)                         │
│  - Sprint burndown, Kanban board, cycle time                │
│  - Team workload, blocker details                           │
│  - Time range: current sprint                               │
└─────────────────────────┬───────────────────────────────────┘
                          │ click task
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Level 3: Task Timeline (Engineer)                          │
│  - Span waterfall, status events, linked commits            │
│  - Agent decisions related to this task                     │
│  - Time range: task lifecycle                               │
└─────────────────────────────────────────────────────────────┘
```

**Design Principles**:

1. **No manual data entry**: All panels derive from telemetry
2. **Consistent drill-down**: Click any element to go deeper
3. **Persona-appropriate metrics**: Executives see trends, engineers see details
4. **Time-appropriate defaults**: Match persona's decision horizon

**Panel Patterns by Persona**:

| Persona | Panel Type | Query Pattern |
|---------|------------|---------------|
| Executive | Stat (single number) | `count() by (project.id)` |
| Executive | Heatmap (health matrix) | `status by (project.id, week)` |
| Manager | Timeseries (burndown) | `sum(story_points) over time` |
| Manager | Table (blockers) | `status = "blocked"` with details |
| Engineer | Trace view | `span.id = X` with waterfall |
| Engineer | Logs panel | `{task.id="X"}` filtered logs |

**Value Delivered**:
| Persona | Benefit |
|---------|---------|
| Executive | 30-second portfolio health check |
| Manager | Real-time sprint progress without meetings |
| Engineer | Task context without switching tools |

---

## Convention Summary

### Namespace Allocation

When creating new semantic conventions, follow this namespace pattern:

```
{domain}.{object}.{attribute}

Examples:
- project.id
- task.status
- agent.insight.confidence
- business.criticality
- requirement.latency_p99
```

### Cardinality Guidelines

| Cardinality | Safe For | Avoid In |
|-------------|----------|----------|
| Low (< 100 values) | Metric labels, dashboard filters | - |
| Medium (100-10k) | Span attributes, log fields | Metric labels |
| High (> 10k) | Span attributes, trace IDs | Metric labels, filters |

### Stability Levels

Follow OTel stability conventions:

| Level | Meaning | Migration |
|-------|---------|-----------|
| Experimental | May change without notice | None required |
| Stable | Breaking changes follow semver | Schema transformations |
| Deprecated | Will be removed | Migration path documented |

---

## Applying These Patterns

To apply these patterns in your own OTel Blueprint:

1. **Identify domain objects** with temporal lifecycle → Pattern 1
2. **Map business metadata** to observability config → Pattern 2
3. **Choose authoritative source** for metadata → Pattern 3
4. **Define agent communication** if AI is involved → Pattern 4
5. **Design dashboard hierarchy** for your personas → Pattern 5

Each pattern is independent but they compose well together.
