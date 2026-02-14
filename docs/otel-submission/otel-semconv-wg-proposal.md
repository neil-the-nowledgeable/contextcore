# ContextCore: A Potential Blueprint for Project Management Observability

**To: OpenTelemetry Semantic Conventions Working Group**

## Summary

ContextCore is an open-source project that models **project management as OpenTelemetry telemetry** — tasks as spans, status changes as events, progress as metrics. This document outlines how ContextCore could serve as both:

1. A **reference implementation** for how domain-specific semantic conventions extend OTel
2. A potential **OTel Blueprint** for "Project Observability on Kubernetes"

## Alignment with OTel Blueprints Initiative

The Blueprint initiative addresses five core adoption challenges. Here's how ContextCore relates:

| Blueprint Challenge | ContextCore Approach |
|---------------------|---------------------|
| **Cross-functional complexity** | Single vocabulary for platform teams, project managers, and engineers: `task.status`, `sprint.velocity`, `business.criticality` |
| **Architecture variability** | Works in any OTLP-compatible environment — Grafana Cloud, Jaeger, Datadog, New Relic |
| **Documentation gap** | Demonstrates connecting domain concepts (tasks, sprints) to observability primitives (spans, events, metrics) |
| **Strategic feedback loop** | Project health derived from existing artifacts (commits, PRs, CI) rather than manual reporting |
| **Regulated environment support** | Structured format via `ProjectContext` CRD enables audit trails and compliance workflows |

## Semantic Conventions Contribution

ContextCore defines the `project.*`, `task.*`, `sprint.*`, `business.*`, and `requirement.*` namespaces following OTel naming conventions:

```yaml
# Example: ContextCore semantic conventions
project.id: "commerce-platform"
project.epic: "EPIC-42"

task.id: "PROJ-123"
task.type: "story"          # epic | story | task | subtask | bug | spike
task.status: "in_progress"  # backlog | todo | in_progress | in_review | blocked | done
task.priority: "high"

business.criticality: "critical"  # Drives sampling rate, alert priority
requirement.latency_p99: "200ms"  # Source for derived SLOs
```

**Key pattern**: Value-based derivation rules, where business metadata drives observability config:

| Input | Derived Output |
|-------|----------------|
| `business.criticality: critical` | `traceSampling: 1.0`, `alertPriority: P1` |
| `requirement.latency_p99: 200ms` | PrometheusRule with 200ms threshold |
| `risk.priority: P1` | Extended audit logging enabled |

This pattern could inform guidance in the "Value-Based Observability" section of future Blueprints.

## Relevant to Ongoing SemConv Discussions

Based on recent SemConv WG meeting notes, ContextCore touches several active areas:

1. **Entity modeling** (discussed Oct-Dec 2025): `ProjectContext` as a Kubernetes CRD demonstrates how entities with lifecycle can map to OTel Resource + spans

2. **Schema federation** (Weaver v2 discussion): ContextCore semantic conventions could be an example of a domain-specific schema that imports `otel-semconv` and adds project-management-specific attributes

3. **CI/CD SIG coordination**: The `task.*` and `sprint.*` conventions complement the CI/CD pipeline conventions being developed — tasks trigger pipelines, pipelines update task status

4. **Guidance documents** ("How to define semantic conventions"): ContextCore's approach to extending OTel for a new domain could inform best practices

## Proposed Contribution Path

### Short-term (informational)

- Share ContextCore's semantic conventions document as an example of domain-specific extension
- Contribute to OTel Blueprint Template feedback based on implementation experience

### Medium-term (if interest exists)

- Propose `project.*` namespace as an experimental registry entry
- Document the "tasks as spans" pattern for the Blueprint library
- Coordinate with CI/CD SIG on `task <-> pipeline` correlation conventions

## Links

- **ContextCore semantic conventions**: [`docs/semantic-conventions.md`](semantic-conventions.md)
- **ProjectContext CRD**: Kubernetes-native source of truth for project metadata
- **Dashboard provisioning**: Pre-built Grafana dashboards using these conventions

## Discussion Questions for SemConv WG

1. **Namespace interest**: Is `project.*` or `task.*` a namespace the SemConv WG would consider adding to the registry, or should it remain a vendor-neutral extension?

2. **Blueprint fit**: Would a "Project Observability" Blueprint be valuable for the End-User SIG's reference architecture library?

3. **Cross-SIG coordination**: Should we sync with CI/CD SIG on task lifecycle events that trigger/correlate with pipeline executions?

---

**Contact**: Force Multiplier Labs
**Slack**: #otel-semconv-general or #otel-user-sig
