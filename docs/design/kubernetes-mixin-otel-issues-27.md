# ContextCore Contribution to kubernetes-mixin-otel Recording Rules

**Issue**: [grafana/kubernetes-mixin-otel#27 — Recording Rules Candidate](https://github.com/grafana/kubernetes-mixin-otel/issues/27)
**Date**: 2026-03-03
**Status**: Analysis / Proposal

---

## Issue Summary

kubernetes-mixin-otel#27 identifies 6 strong candidates for Prometheus recording rules
to pre-compute expensive pod-level CPU/memory queries:

| Candidate | Reason | Suggested Name |
|-----------|--------|----------------|
| `cpuUsageByPod` | Rate calculation, reused in ratios | `namespace:pod_cpu:rate5m` |
| `cpuRequestsByPod` | Join with `k8s_pod_phase` | `namespace:pod_cpu_request:active` |
| `cpuLimitsByPod` | Join with `k8s_pod_phase` | `namespace:pod_cpu_limit:active` |
| `memoryUsageByPod` | Frequently used, reused in ratios | `namespace:pod_memory_working_set:bytes` |
| `memoryRequestsByPod` | Join with `k8s_pod_phase` | `namespace:pod_memory_request:active` |
| `memoryLimitsByPod` | Join with `k8s_pod_phase` | `namespace:pod_memory_limit:active` |

Key observations from the issue:
- The `k8s_pod_phase` join + `clamp_max` pattern is repeated 6 times (expensive)
- `rate()` on counters is expensive at query time
- Once base metrics are recorded, ratio queries become cheap division
- A common prefix (`kmo:` — **K**ubernetes-**M**ixin **O**Tel) is proposed
- Benchmarking shows ~130ms average for CPU Quota table at 200 pods / 50 nodes
- High-cardinality concerns flagged for `k8s_pod_network_io_bytes_total` (extra `direction` + `interface` labels)

---

## What ContextCore Already Has

### 1. Recording Rule Naming Convention (kubernetes-mixin aligned)

ContextCore's Loki recording rules in `loki/rules/fake/contextcore-rules.yaml` already
follow the `<level>:<metric>:<aggregation>` pattern that kubernetes-mixin established:

```
project:contextcore_task_percent_complete:max_over_time5m
project_sprint:contextcore_task_percent_complete:avg
project_sprint:contextcore_task_completed:count
project_task:contextcore_task_progress:rate1h
project:contextcore_task_count:count_by_status
```

The semantic conventions document (`docs/reference/semantic-conventions.md`, lines 1326+)
explicitly references kubernetes-mixin alignment:

> Recording rules and alerts follow the kubernetes-mixin naming conventions to ensure
> consistency with the broader Kubernetes/Prometheus ecosystem.

**Contribution**: The naming validation functions in `src/contextcore/contracts/metrics.py`
(`validate_recording_rule_name()`, `validate_alert_rule_name()`) can enforce the `kmo:`
prefix convention programmatically — ensuring rule names follow the pattern at build time,
not just by convention in an issue thread.

### 2. Dependency Manifests (Rule → Dashboard Traceability)

The issue identifies 6 candidates but does not connect them to downstream consumers.
ContextCore's `grafana/provisioning/dashboards/dependencies.yaml` closes this gap by
declaring which dashboards use which datasources and derived metrics.

Applied to kmo, this would look like:

```yaml
recording_rules:
  - name: "kmo:namespace:pod_cpu:rate5m"
    source_metrics:
      - "k8s_pod_cpu_time_seconds_total"
    consumed_by:
      - "kubernetes-compute-resources-namespace-pods.json"
      - "kubernetes-compute-resources-namespace-workloads.json"
      - "kubernetes-compute-resources-pod.json"

  - name: "kmo:namespace:pod_cpu_request:active"
    source_metrics:
      - "k8s_container_cpu_request"
      - "k8s_pod_phase"
    consumed_by:
      - "kubernetes-compute-resources-namespace-pods.json"
```

This makes the impact of changing or removing a recording rule visible — you know
exactly what dashboards break. It also enables CI validation: "does every recording
rule name referenced in a dashboard panel actually exist in a rule file?"

### 3. Artifact Type System with Output Contracts

ContextCore models `PROMETHEUS_RULE` and `LOKI_RULE` as first-class artifact types in
`src/contextcore/models/artifact_manifest.py`, each with:

- **Parameter sources**: which manifest fields populate the rule
- **Completeness markers**: `["groups", "rules", "alert", "expr"]`
- **Size constraints**: max lines/tokens for generation
- **Output conventions**: path templates, schema URLs

```python
# From src/contextcore/utils/artifact_conventions.py
EXPECTED_OUTPUT_CONTRACTS = {
    ArtifactType.PROMETHEUS_RULE.value: {
        "expected_depth": "standard",
        "max_lines": 150,
        "max_tokens": 750,
        "completeness_markers": ["groups", "rules", "alert", "expr"],
    },
    ArtifactType.LOKI_RULE.value: {
        "expected_depth": "standard",
        "max_lines": 100,
        "max_tokens": 500,
        "completeness_markers": ["groups", "rules", "expr", "by"],
    },
}
```

For kmo, recording rules could be declared as artifacts in the mixin's manifest with
their parameter sources traced back to the source metrics and label dimensions.

### 4. Onboarding Metadata for Programmatic Generation

ContextCore's `src/contextcore/utils/onboarding.py` maps `ArtifactType → parameter_sources`,
enabling programmatic rule generation from manifest metadata rather than hand-authoring YAML.

For Kubernetes recording rules:

```python
ArtifactType.PROMETHEUS_RULE.value: {
    "namespace": "crd.metadata.namespace",
    "metricPrefix": "kmo",
    "podPhaseFilter": "k8s_pod_phase == 'Running'",
    "rateWindow": "5m",
    "labelDimensions": ["cluster", "namespace", "pod"],
}
```

An agent or CI pipeline could generate the 6 candidate rules deterministically from
the manifest — turning the issue's table into a governed artifact.

---

## New Value ContextCore Could Contribute

### 5. Cardinality-Aware Rule Generation from Capability Metadata

The issue flags `k8s_pod_network_io_bytes_total` as "most concerning for cardinality"
due to extra `direction` and `interface` labels (2x multiplier). ContextCore's capability
index already tracks label cardinality guidelines.

Extended to Kubernetes metrics, this becomes machine-readable metadata:

```yaml
cardinality_profiles:
  k8s_pod_cpu_time_seconds_total:
    dimensions: [cluster, namespace, pod, container]
    multiplier: "clusters x namespaces x pods x containers"
    recording_rule_action: "aggregate away container, keep namespace+pod"

  k8s_pod_network_io_bytes_total:
    dimensions: [cluster, namespace, pod, direction, interface]
    multiplier: "2x (direction) x N (interface)"
    recording_rule_action: "aggregate away interface, sum by direction"

  k8s_container_cpu_request:
    dimensions: [cluster, namespace, pod, container]
    multiplier: "clusters x namespaces x pods x containers"
    recording_rule_action: "join with k8s_pod_phase, filter active, drop container"
```

A pipeline can validate that recording rules actually reduce cardinality as intended,
rather than discovering cardinality explosions after deployment.

### 6. A2A Contract Validation for Rule–Dashboard Consistency

ContextCore's Gate 1 (`a2a-check-pipeline`) runs 9 integrity checks including
"parameter resolvability" — verifying that every parameter source references a field
that actually exists. Applied to kmo:

| Gate Check | Applied to Recording Rules |
|------------|---------------------------|
| **Structural integrity** | Required fields (`groups`, `rules`, `record`, `expr`) exist in every rule file |
| **Parameter resolvability** | Every PromQL `metric_name` in a recording rule exists in the OTel collector's metric list |
| **Mapping completeness** | Every recording rule consumed by a dashboard panel actually produces output |
| **Label dimension match** | Label dimensions in recording rules match what dashboard `$variables` expect |
| **Checksum chain** | Rule file checksums match stored provenance (detects drift) |

This addresses the implicit question behind sleepyfoodie's benchmarking screenshots —
not just "are these rules candidates?" but "do the deployed rules actually help?"

### 7. Three Questions Diagnostic for Rule Lifecycle

ContextCore's Three Questions pattern (`a2a-diagnose`) maps to recording rule governance:

| Question | Recording Rule Application |
|----------|---------------------------|
| **Is the contract complete?** | Are all high-cardinality metrics that dashboards query covered by recording rules? Identify gaps where expensive queries remain unoptimized. |
| **Was it faithfully translated?** | Do the generated rules match the declared parameter sources? (rate window, label dimensions, phase filter, prefix) |
| **Was it faithfully executed?** | Do the deployed rules in Mimir/Prometheus produce the expected metrics? Query and verify non-empty results. |

### 8. Recording Rule as Governed Artifact (Full Lifecycle)

Combining the above, a recording rule becomes a governed artifact with full lifecycle:

```
Declare (manifest)
  → Derive parameters (onboarding metadata)
  → Validate cardinality (cardinality profiles)
  → Generate rule YAML (artifact conventions + output contracts)
  → Check naming (recording rule name validator)
  → Verify dashboard consumption (dependency manifest)
  → Deploy (Mimir/Prometheus rule group)
  → Diagnose (Three Questions — is it producing data?)
  → Track drift (checksum chain in provenance)
```

Each step has a corresponding ContextCore component already implemented or directly
extensible.

---

## Concrete Proposal

### For kubernetes-mixin-otel

1. **Adopt dependency manifest pattern** — declare which dashboards consume which
   recording rules. This makes rule changes safe by showing blast radius before deployment.

2. **Adopt naming validation** — enforce the `kmo:` prefix and `<level>:<metric>:<aggregation>`
   pattern in CI, not just in documentation.

3. **Add cardinality profiles** — document the label dimensions and multipliers for each
   source metric. This turns the issue's cardinality table into testable metadata.

4. **Add benchmarking contract** — for each recording rule candidate, declare the expected
   improvement (e.g., "CPU Quota table query time should drop from 130ms to <50ms at
   200 pods / 50 nodes"). This makes the benchmarking spreadsheet a validation artifact.

### For ContextCore

1. **Extend `ArtifactType`** — add `KUBERNETES_RECORDING_RULE` or use `PROMETHEUS_RULE`
   with a `rule_type: recording` discriminator.

2. **Add `cardinality_profile` to capability manifest** — per-metric label dimension
   metadata that pipelines can validate against.

3. **Extend `a2a-check-pipeline`** — add gate check for "recording rule covers all
   high-cardinality source metrics used in dashboard panels."

4. **Create recording rule template** — parameterized template in `artifact_conventions`
   that generates kmo-style rules from manifest metadata.

---

## What This Does Not Cover

- **PromQL benchmarking mechanics** — the actual query performance measurement
  (sleepyfoodie's screenshots) is runtime observability, not metadata governance.
- **Mimir-specific deployment** — rule group management, tenant isolation, rule evaluation
  intervals are infrastructure concerns outside ContextCore's scope.
- **Jsonnet templating** — kubernetes-mixin-otel uses jsonnet; ContextCore uses Python.
  The metadata patterns are language-agnostic, but the generation tooling would need
  a jsonnet adapter.

---

## Key Insight

The issue currently frames recording rules as a **performance optimization** (pre-compute
expensive queries). ContextCore's contribution reframes them as **governed artifacts** —
declared in manifests, validated by contracts, connected to consumers via dependency
tracking, and diagnosed via lifecycle gates.

This moves from "6 candidates in a GitHub issue table" to "6 artifacts in a governed
pipeline with dependency tracking and validation gates."

---

## References

| Resource | Path |
|----------|------|
| ContextCore recording rules | `loki/rules/fake/contextcore-rules.yaml` |
| Semantic conventions (recording rules section) | `docs/reference/semantic-conventions.md` (lines 1326–1530) |
| Dependency manifest | `grafana/provisioning/dashboards/dependencies.yaml` |
| Artifact type enum | `src/contextcore/models/artifact_manifest.py` |
| Output contracts | `src/contextcore/utils/artifact_conventions.py` |
| Onboarding metadata | `src/contextcore/utils/onboarding.py` |
| Recording rule name validator | `src/contextcore/contracts/metrics.py` |
| A2A pipeline checker | `src/contextcore/contracts/a2a/pipeline_checker.py` |
| Three Questions diagnostic | `src/contextcore/contracts/a2a/three_questions.py` |
| Capability index manifest | `docs/capability-index/contextcore.agent.yaml` |
| kubernetes-mixin-otel issue | https://github.com/grafana/kubernetes-mixin-otel/issues/27 |
