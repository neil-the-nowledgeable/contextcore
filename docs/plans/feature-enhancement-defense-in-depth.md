# Feature Enhancement: Defense-in-Depth as a ContextCore Resource

**Status**: Proposal
**Author**: Human + Claude Code collaborative forensic analysis
**Date**: 2026-02-11
**Relates to**: `contextcore.io/v1alpha1 InfrastructureGuard` (prototype at `observability/pvc-protection.yaml`)

---

## Motivation

On February 4-11, 2026, AI agents operating across three projects (Deploy, Wayfinder, ContextCore) repeatedly destroyed observability data by applying Kubernetes deployment manifests that replaced `persistentVolumeClaim` volumes with `emptyDir: {}`. The damage accumulated silently over 19 days and 31+ deployment revisions before detection.

Forensic analysis revealed five contributing anti-patterns, each of which could have been interrupted by a different protection layer:

| Anti-Pattern | What Happened | What Would Have Caught It |
|---|---|---|
| **Duplicate manifests** | 3 projects had observability manifests for 1 namespace | Single source of truth enforcement |
| **Authoritative bad instructions** | CLAUDE.md told agents to `kubectl apply -k k8s/observability/` | Agent guidance constraints with blocking severity |
| **Over-broad permissions** | `Bash(kubectl:*)` auto-approved all kubectl commands | Scoped permission policies |
| **No admission control** | K8s accepted whatever was applied | ValidatingWebhook on protected resources |
| **No drift detection** | Nobody noticed for 19 days | Continuous monitoring with alerting |

An ad-hoc defense-in-depth system was built reactively:

1. **CLAUDE.md instructions** in 3 project repos (advisory)
2. **PreToolUse hook** intercepting kubectl commands (Claude Code only)
3. **Drift detection script** comparing live state to expected (manual)
4. **K8s ValidatingWebhook** rejecting bad deployments (in-cluster)

This worked, but was hand-built for one specific failure mode (PVC-to-emptyDir). The patterns are generalizable. Any team protecting critical infrastructure from automated agents faces the same challenge: **how do you declare what must be protected, enumerate the layers defending it, and visualize the gaps?**

---

## Proposal

Formalize the defense-in-depth pattern as a first-class ContextCore resource type, with:

1. **`InfrastructureGuard` CRD** -- Declarative resource describing what's protected and how
2. **Protection Layer taxonomy** -- Standard vocabulary for classifying enforcement mechanisms
3. **Defense-in-Depth Dashboard** -- Grafana dashboard visualizing protection posture
4. **Telemetry integration** -- Protection events emitted as OTel metrics and spans
5. **Agent guidance derivation** -- Guard constraints automatically flow into `ProjectContext.agentGuidance`

---

## Design

### 1. InfrastructureGuard CRD

**API Group**: `contextcore.io`
**Version**: `v1alpha1` (graduating to `v1` with the rest of ContextCore)
**Kind**: `InfrastructureGuard`
**Short names**: `ig`, `guard`
**Scope**: Namespaced

#### Spec Schema

```yaml
apiVersion: contextcore.io/v1alpha1
kind: InfrastructureGuard
metadata:
  name: observability-pvc-protection
  namespace: observability
  labels:
    contextcore.io/guard-type: pvc-protection    # taxonomy tag
    contextcore.io/project: deploy-o11y          # links to ProjectContext
spec:
  # --- What this guard protects ---
  description: >
    Protects observability stack PVC bindings from being replaced with
    emptyDir volumes by automated agents or manual kubectl commands.

  # Business context (drives protection intensity, mirrors ProjectContext)
  business:
    criticality: critical          # critical | high | medium | low
    dataClassification: operational # operational | sensitive | regulated | public
    impactDescription: >
      Data loss of all metrics, logs, traces, and dashboards.
      Recovery requires re-ingestion from source systems (if available).

  # --- Protected invariants (the things that must not change) ---
  invariants:
    - id: grafana-pvc
      resource:
        kind: Deployment
        name: grafana
        namespace: observability
      property: spec.template.spec.volumes[?name=grafana-storage]
      expected:
        type: persistentVolumeClaim
        value:
          claimName: grafana-pvc
      violation:
        type: emptyDir              # what the bad state looks like
        impact: "Grafana SQLite DB, dashboards, preferences lost on pod restart"
      manifestPath: observability/grafana/deployment.yaml

    - id: mimir-pvc
      resource:
        kind: Deployment
        name: mimir
        namespace: observability
      property: spec.template.spec.volumes[?name=storage]
      expected:
        type: persistentVolumeClaim
        value:
          claimName: mimir-pvc
      violation:
        type: emptyDir
        impact: "All Prometheus TSDB blocks, WAL, compactor state lost"
      manifestPath: observability/mimir/deployment.yaml

    # ... (loki, tempo, pyroscope follow same pattern)

  # --- Protection layers (what's defending these invariants) ---
  layers:
    - id: claude-md
      type: agent-instruction        # taxonomy (see below)
      name: "CLAUDE.md project instructions"
      description: "Advisory instructions in 3 project CLAUDE.md files"
      scope: agent-only              # agent-only | cluster-wide | ci-pipeline | all
      enforcement: advisory          # advisory | blocking | detecting | recovering
      failOpen: true                 # if this layer fails, does the system remain unprotected?
      locations:
        - ~/Documents/Deploy/CLAUDE.md
        - ~/Documents/dev/wayfinder/CLAUDE.md
        - ~/Documents/dev/ContextCore/CLAUDE.md
      coversVectors:                 # which attack vectors this layer defends against
        - agent-constructs-yaml
        - agent-applies-stale-manifests
      misses:                        # known gaps
        - "Agent may not read CLAUDE.md (context compression, resumed sessions)"
        - "Non-agent users are not covered"

    - id: pretooluse-hook
      type: cli-hook
      name: "o11y-pvc-guard.sh PreToolUse hook"
      description: "Shell hook intercepting kubectl commands before execution"
      scope: agent-only
      enforcement: blocking
      failOpen: true                 # if hook file is missing, commands proceed
      failClosed: true               # if JSON parsing fails for kubectl commands, blocks (jq-based parser)
      locations:
        - ~/.claude/hooks/o11y-pvc-guard.sh
        - ~/.claude/hooks/infra-guard-hook.sh
      coversVectors:
        - agent-constructs-yaml
        - agent-applies-stdin-yaml
        - agent-creates-deployment
        - agent-applies-stale-manifests   # cross-project paths now caught (Rule 1b, 8b)
      misses:
        - "Direct terminal usage outside Claude Code"
        # RESOLVED 2026-02-11: Cross-project paths (k8s/observability/) — Rule 1b blocks non-canonical kustomize paths
        # RESOLVED 2026-02-11: Absolute paths — Rule 8b inspects absolute-path applies; tilde expansion added
        # RESOLVED 2026-02-11: JSON parsing failure — grep-based parser replaced with jq; fail-closed for kubectl
      healthCheck:
        type: file-exists
        target: ~/.claude/hooks/o11y-pvc-guard.sh
      integrationTests:
        location: ~/.claude/hooks/test-infra-guard.sh
        testCount: 27
        addedDate: "2026-02-11"

    - id: k8s-webhook
      type: admission-webhook
      name: "pvc-guard ValidatingWebhook"
      description: "K8s admission controller rejecting emptyDir on protected deployments"
      scope: cluster-wide
      enforcement: blocking
      failOpen: false                # failurePolicy: Fail (changed 2026-02-11)
      locations:
        - observability/pvc-guard/
      coversVectors:
        - agent-constructs-yaml
        - agent-applies-stale-manifests
        - agent-applies-stdin-yaml
        - agent-creates-deployment
        - manual-kubectl
        - ci-pipeline-apply
      misses:
        - "Webhook pod down → failurePolicy: Fail → ALL deploys to observability namespace blocked (availability risk)"
        # RESOLVED 2026-02-11: failurePolicy changed from Ignore to Fail — no more silent bypass
        # NEW RISK: Webhook unavailability now blocks legitimate deploys; mitigate with PDB and replicas
      healthCheck:
        type: k8s-resource
        target:
          kind: Deployment
          name: pvc-guard
          namespace: observability
          condition: Available

    - id: drift-detection
      type: drift-monitor
      name: "drift-check.sh detection script"
      description: "Compares live K8s state against expected PVC bindings"
      scope: cluster-wide
      enforcement: detecting         # detects but does not prevent
      failOpen: true
      locations:
        - scripts/drift-check.sh
      coversVectors:
        - any                        # detects drift regardless of cause
      misses:
        - "Only runs when invoked (no continuous monitoring)"
        - "Detection latency depends on invocation frequency"
      healthCheck:
        type: file-exists
        target: scripts/drift-check.sh

    - id: permissions-policy
      type: permission-scope
      name: "Claude Code settings.local.json permissions"
      description: "Scoped Bash permissions for kubectl commands"
      scope: agent-only
      enforcement: blocking
      failOpen: false                # if settings missing, Claude Code prompts for approval
      locations:
        - .claude/settings.local.json
      coversVectors:
        - agent-constructs-yaml
        - agent-applies-stdin-yaml
        - agent-applies-stale-manifests
      misses:
        # RESOLVED 2026-02-11: Wayfinder narrowed to read-only kubectl (get, describe, logs, exec, rollout, port-forward, config)
        # RESOLVED 2026-02-11: Deploy narrowed to scoped applies (kubectl apply -k observability/, -f observability/*, -f namespaces/, -f contextcore/, --dry-run)
        - "Claude Code may auto-add broad permissions when user approves a specific command (monitor settings.local.json)"

  # --- Attack vectors (the ways protection can be breached) ---
  vectors:
    - id: agent-constructs-yaml
      name: "Agent constructs deployment YAML from scratch"
      description: >
        An AI agent writes a new deployment manifest rather than editing the
        canonical on-disk file. The constructed YAML uses emptyDir because
        the agent doesn't know about PVC requirements.
      likelihood: high
      historicalCount: 31            # Grafana revision count

    - id: agent-applies-stale-manifests
      name: "Agent applies stale manifests from another project"
      description: >
        A cross-project agent follows instructions to apply observability
        manifests that are development copies with emptyDir volumes.
      likelihood: high
      historicalCount: 7             # wayfinder session applied 7 times

    - id: agent-applies-stdin-yaml
      name: "Agent pipes YAML via kubectl apply -f -"
      description: >
        Agent constructs YAML in a heredoc or echo and pipes to kubectl.
        Content cannot be verified against on-disk manifests.
      likelihood: medium

    - id: agent-creates-deployment
      name: "Agent uses kubectl create/replace deployment"
      description: >
        Agent uses imperative commands that bypass manifest files entirely.
      likelihood: low

    - id: manual-kubectl
      name: "Human runs kubectl directly from terminal"
      description: >
        A human operator applies modified YAML from the terminal,
        outside any agent tooling or hook.
      likelihood: low

    - id: ci-pipeline-apply
      name: "CI pipeline applies bad manifests"
      description: >
        A CI/CD pipeline applies generated or templated manifests
        that don't preserve PVC bindings.
      likelihood: low

    - id: webhook-bypass
      name: "Webhook unavailable during apply"
      description: >
        The pvc-guard webhook pod is down or unreachable.
        With failurePolicy: Fail, this blocks ALL deploys to the observability
        namespace (availability risk, not a data-loss risk).
        Previously with failurePolicy: Ignore, this silently bypassed protection.
      likelihood: low

  # --- Agent guidance (auto-derived into ProjectContext) ---
  agentGuidance:
    constraints:
      - id: no-scratch-yaml
        rule: "NEVER construct deployment YAML from scratch for observability components"
        scope: "observability/*"
        severity: blocking
        reason: "Constructed YAML loses PVC bindings, causing data loss"
      - id: no-stdin-apply
        rule: "NEVER use kubectl apply -f - with inline YAML for observability deployments"
        scope: "observability/*"
        severity: blocking
        reason: "Stdin YAML cannot be verified against the protection descriptor"
      - id: no-emptydir-replace
        rule: "NEVER replace persistentVolumeClaim volumes with emptyDir"
        scope: "observability/*"
        severity: blocking
        reason: "emptyDir causes silent data loss on pod restart"
      - id: edit-then-apply
        rule: "ALWAYS edit on-disk manifests then apply via make up-observability"
        scope: "observability/*"
        severity: blocking
        reason: "On-disk manifests are the single source of truth"

    safeWorkflows:
      - name: "Change a deployment"
        steps:
          - "Edit the on-disk file: observability/<component>/deployment.yaml"
          - "Apply via Kustomize: make up-observability"
          - "Verify: make drift-check"
      - name: "Update a ConfigMap"
        steps:
          - "Edit the on-disk file: observability/<component>/configmap.yaml"
          - "Apply: make reload-configs"
      - name: "Restart a component"
        steps:
          - "kubectl rollout restart deployment/<name> -n observability"
      - name: "Fix detected drift"
        steps:
          - "make drift-check   (detect)"
          - "make fix-drift      (restore)"
          - "make drift-check   (verify)"

    remediation:
      - trigger: "drift-detected"
        action: "make fix-drift"
        automated: false
        description: "Re-apply canonical manifests from on-disk files"
      - trigger: "webhook-denied"
        action: "Edit on-disk manifest, then make up-observability"
        automated: false
        description: "The webhook blocked the apply; fix the source file instead"
```

#### Status Schema

```yaml
status:
  # Overall protection posture
  posture: protected              # protected | degraded | exposed | unknown
  postureScore: 0.75              # 0.0 - 1.0 (layers active / layers defined)
  lastEvaluated: "2026-02-11T18:30:00Z"

  # Per-layer health
  layerStatus:
    - id: claude-md
      healthy: true
      lastChecked: "2026-02-11T18:30:00Z"
      message: "3/3 CLAUDE.md files contain guard constraints"
    - id: pretooluse-hook
      healthy: true
      lastChecked: "2026-02-11T18:30:00Z"
      message: "Hook file exists and is executable"
    - id: k8s-webhook
      healthy: true
      lastChecked: "2026-02-11T18:30:00Z"
      message: "pvc-guard pod Running (1/1), webhook registered"
    - id: drift-detection
      healthy: true
      lastChecked: "2026-02-11T18:30:00Z"
      message: "Last drift check: 0 violations"

  # Per-invariant status
  invariantStatus:
    - id: grafana-pvc
      compliant: true
      lastVerified: "2026-02-11T18:30:00Z"
      currentValue: "persistentVolumeClaim: grafana-pvc"
    - id: mimir-pvc
      compliant: true
      lastVerified: "2026-02-11T18:30:00Z"
      currentValue: "persistentVolumeClaim: mimir-pvc"

  # Coverage matrix summary
  coverage:
    vectorsCovered: 7
    vectorsTotal: 7
    gaps:
      - vector: webhook-bypass
        description: "Webhook pod unavailable blocks all observability deploys (availability risk)"
        recommendation: "Add PodDisruptionBudget, consider 2 replicas with anti-affinity"
        # PARTIALLY RESOLVED 2026-02-11: failurePolicy changed to Fail (data-loss risk eliminated)
        # REMAINING: PDB and replicas not yet added (availability hardening)

  # Recent events
  recentEvents:
    - timestamp: "2026-02-11T18:22:00Z"
      layer: k8s-webhook
      action: denied
      detail: "Blocked emptyDir deployment for grafana (dry-run=server test)"
    - timestamp: "2026-02-11T17:50:00Z"
      layer: drift-detection
      action: detected
      detail: "4/5 deployments drifted: grafana, loki, mimir, tempo"

  # Generated artifacts
  generatedArtifacts:
    dashboard: contextcore-defense-in-depth
    prometheusRules:
      - pvc-guard-webhook-health
      - drift-detection-alerts
    webhookConfiguration: pvc-guard
```

### 2. Protection Layer Taxonomy

A standardized vocabulary for classifying protection mechanisms. Each layer has a `type` and an `enforcement` level.

#### Layer Types

| Type | Description | Scope | Example |
|------|-------------|-------|---------|
| `agent-instruction` | Advisory text in project config files | Agent sessions only | CLAUDE.md rules |
| `cli-hook` | PreToolUse/PostToolUse shell hooks | Claude Code sessions | o11y-pvc-guard.sh |
| `permission-scope` | Scoped tool permissions | Claude Code sessions | settings.local.json |
| `admission-webhook` | K8s ValidatingWebhookConfiguration | Cluster-wide | pvc-guard webhook |
| `drift-monitor` | Periodic state comparison | Cluster-wide | drift-check.sh |
| `continuous-monitor` | Always-on state watcher (CronJob, operator) | Cluster-wide | CronJob + alerting |
| `rbac-policy` | K8s RBAC restricting who can mutate resources | Cluster-wide | ServiceAccount roles |
| `gitops-controller` | Git-based desired state reconciliation | Cluster-wide | ArgoCD, Flux |
| `ci-gate` | Pre-merge validation in CI pipeline | CI/CD | GitHub Actions check |
| `backup-restore` | Data backup enabling recovery | Cluster-wide | Velero, VolumeSnapshots |
| `network-policy` | Network-level access restrictions | Cluster-wide | K8s NetworkPolicy |
| `opa-policy` | Open Policy Agent / Gatekeeper constraints | Cluster-wide | OPA ConstraintTemplate |

#### Enforcement Levels

| Level | Behavior | Example |
|-------|----------|---------|
| `advisory` | Informs but does not prevent | CLAUDE.md instructions |
| `blocking` | Actively prevents the violation | Webhook deny, hook exit 2 |
| `detecting` | Identifies violations after the fact | Drift check script |
| `recovering` | Automatically restores correct state | GitOps reconciliation, auto-remediation |

#### Coverage Completeness Model

A guard's **posture score** is derived from how many attack vectors are covered at each enforcement level:

```
postureScore = sum(vectorWeights) where:
  - blocking layer covering vector:    weight = 1.0
  - detecting layer covering vector:   weight = 0.5
  - advisory layer covering vector:    weight = 0.25
  - recovering layer covering vector:  weight = 0.75
  - no layer covering vector:          weight = 0.0

  Normalized to 0.0 - 1.0 range
  Adjusted by -0.1 for each layer with failOpen: true
```

### 3. Defense-in-Depth Dashboard

A Grafana dashboard following ContextCore conventions:

**UID**: `contextcore-core-defense-in-depth`
**Title**: `[CORE] Defense in Depth`
**Tags**: `["contextcore", "defense-in-depth", "infrastructure"]`
**Folder**: ContextCore
**Datasources**: Mimir (Prometheus), Loki, Tempo

#### Dashboard Layout

```
Row 1: Protection Posture Overview
┌─────────────────┬──────────────┬──────────────┬───────────────┐
│  Posture Score   │ Layers Total │ Layers Active│ Invariants OK │
│  (gauge 0-100%)  │  (stat)      │  (stat)      │  (stat x/y)   │
└─────────────────┴──────────────┴──────────────┴───────────────┘

Row 2: Layer Health
┌──────────────────────────────────────────────────────────────────┐
│  Layer Status Matrix (table)                                     │
│  Columns: Layer | Type | Enforcement | Scope | Health | Last     │
│  Color: green=healthy, red=unhealthy, yellow=degraded            │
└──────────────────────────────────────────────────────────────────┘

Row 3: Coverage Matrix
┌──────────────────────────────────────────────────────────────────┐
│  Attack Vector × Layer heatmap (state-timeline or table)         │
│                                                                  │
│  Rows: attack vectors (agent-constructs-yaml, manual-kubectl...) │
│  Columns: protection layers (CLAUDE.md, hook, webhook, drift...) │
│  Cells: covers (green) | misses (red) | partial (yellow)        │
└──────────────────────────────────────────────────────────────────┘

Row 4: Invariant Compliance
┌──────────────────────────────────────────────────────────────────┐
│  Per-Resource Status (table)                                     │
│  Columns: Resource | Expected | Actual | Compliant | Last Check  │
│  Color: compliant=green, drifted=red                             │
└──────────────────────────────────────────────────────────────────┘

Row 5: Recent Protection Events
┌──────────────────────────────┬───────────────────────────────────┐
│  Webhook Denials (timeseries)│  Hook Blocks (timeseries)         │
│  (from pvc-guard logs)       │  (from hook execution logs)       │
└──────────────────────────────┴───────────────────────────────────┘
┌──────────────────────────────┬───────────────────────────────────┐
│  Drift Events (timeseries)   │  Event Log (logs panel)           │
│  (from drift-check runs)     │  (Loki: all protection events)    │
└──────────────────────────────┴───────────────────────────────────┘

Row 6: Gap Analysis
┌──────────────────────────────────────────────────────────────────┐
│  Uncovered Vectors (table)                                       │
│  Columns: Vector | Likelihood | Current Best Layer | Gap         │
│  Shows only vectors without a blocking layer                     │
└──────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────┐
│  Recommendations (text/markdown panel)                           │
│  Static content listing improvement opportunities from the       │
│  InfrastructureGuard status.coverage.gaps array                  │
└──────────────────────────────────────────────────────────────────┘
```

#### Metrics Required

New Prometheus metrics emitted by the pvc-guard webhook and drift-check script:

| Metric | Type | Labels | Source |
|--------|------|--------|--------|
| `contextcore_guard_posture_score` | Gauge | `guard`, `namespace` | Guard controller or CronJob |
| `contextcore_guard_layer_healthy` | Gauge (0/1) | `guard`, `layer_id`, `layer_type` | Guard controller or CronJob |
| `contextcore_guard_invariant_compliant` | Gauge (0/1) | `guard`, `invariant_id`, `resource` | drift-check output |
| `contextcore_guard_webhook_decisions_total` | Counter | `guard`, `action` (allowed/denied) | pvc-guard server |
| `contextcore_guard_hook_decisions_total` | Counter | `guard`, `action` (allowed/blocked) | hook script (via textfile collector) |
| `contextcore_guard_drift_detected_total` | Counter | `guard`, `invariant_id` | drift-check output |
| `contextcore_guard_vectors_covered` | Gauge | `guard` | Guard controller |
| `contextcore_guard_vectors_total` | Gauge | `guard` | Guard controller |

#### Alert Rules

| Alert | Condition | Severity |
|-------|-----------|----------|
| `ContextCoreGuardPostureDegraded` | `posture_score < 0.7` for 5m | warning |
| `ContextCoreGuardPostureExposed` | `posture_score < 0.3` for 5m | critical |
| `ContextCoreGuardLayerDown` | `layer_healthy == 0` for 5m | warning |
| `ContextCoreGuardWebhookDown` | webhook `layer_healthy == 0` for 2m | critical |
| `ContextCoreGuardDriftDetected` | `invariant_compliant == 0` for any invariant | critical |
| `ContextCoreGuardNoRecentCheck` | No drift check in 10m | warning |

### 4. Telemetry Integration

Protection events emitted as OpenTelemetry signals following ContextCore semantic conventions:

#### New Semantic Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `guard.id` | string | InfrastructureGuard resource name |
| `guard.type` | string | Guard type label (e.g., `pvc-protection`) |
| `guard.layer.id` | string | Which layer acted |
| `guard.layer.type` | string | Layer taxonomy type |
| `guard.action` | string | `allowed`, `denied`, `detected`, `restored` |
| `guard.invariant.id` | string | Which invariant was evaluated |
| `guard.vector.id` | string | Which attack vector was matched |
| `guard.posture` | string | Posture at time of event |

#### Span Names

- `contextcore.guard.evaluate` -- Full posture evaluation
- `contextcore.guard.webhook.review` -- Single admission review
- `contextcore.guard.drift.check` -- Drift detection run
- `contextcore.guard.hook.intercept` -- Hook interception event

### 5. Agent Guidance Derivation

When an InfrastructureGuard exists in the same namespace as a ProjectContext, the guard's `agentGuidance.constraints` are automatically merged into the ProjectContext's `agentGuidance.constraints` with:
- `scope` set to the guard's namespace
- `severity` set to `blocking` (guards are not advisory)
- `reason` prefixed with `[InfrastructureGuard: {guard.name}]`

This means any agent reading a ProjectContext automatically inherits infrastructure protection constraints without needing to know about the InfrastructureGuard resource directly.

---

## Relationship to Existing ContextCore Concepts

| ContextCore Concept | Defense-in-Depth Analog | Integration Point |
|---|---|---|
| `ProjectContext.business.criticality` | Drives protection intensity (critical = more layers required) | Guard `spec.business.criticality` mirrors ProjectContext |
| `ProjectContext.risks[]` | Each uncovered attack vector is a risk | Guard vectors auto-generate risk entries |
| `ProjectContext.agentGuidance.constraints` | Guard constraints with `severity: blocking` | Auto-merged into ProjectContext |
| `ProjectContext.observability` | Guard dashboard placement derived from criticality | `dashboardPlacement: featured` for critical guards |
| `status.generatedArtifacts` | Guard generates dashboard, alerts, webhook config | Tracked in guard status |
| Semantic conventions (`guard.*`) | New namespace following existing patterns | Extends the `contextcore.*` convention family |

---

## Operational Requirements

*Derived from architectural review suggestions R1-S1, R2-S3, R2-S4, R2-S7, R2-S10, R2-S15.*

### Rollback & Recovery

Each implementation phase must document a rollback strategy. High-risk phases (CRD migration, webhook failurePolicy changes) must include:

- Pre-change snapshot or backup step
- Concrete rollback commands
- Verification procedure after rollback
- Maximum acceptable rollback time

Each protection layer must have a documented failure recovery runbook. The runbook must cover:

- How to detect the failure (alert → symptom → root cause)
- Steps to restore the layer to healthy status
- Temporary mitigations while the layer is down
- Post-incident verification

### Production-Readiness Certification

Not all blocking layers are equally reliable. Before a layer can be set to `enforcement: blocking`, it must meet certification criteria:

| Criterion | Requirement |
|-----------|-------------|
| Health check defined | Must have a `healthCheck` that can be automated |
| Recovery runbook exists | Documented steps to restore from failure |
| Negative tests pass | Verify the layer actually blocks violations |
| Failure mode documented | What happens when the layer is unavailable |
| Monitoring in place | Alert fires within SLO if layer degrades |

### SLIs / SLOs

The defense-in-depth system must define measurable service-level indicators:

| SLI | SLO | Measurement |
|-----|-----|-------------|
| Posture evaluation freshness | < 5 minutes stale | Time since last `status.lastEvaluated` |
| Webhook decision latency | p99 < 500ms | `contextcore_guard_webhook_decisions_duration_seconds` |
| Drift detection latency | < 10 minutes from change to detection | Time between K8s event and drift alert |
| Alert delivery latency | < 2 minutes from threshold breach | AlertManager → notification channel |
| Layer health check coverage | 100% of defined layers | Layers with automated health checks / total layers |

### Zero-Downtime Updates

Guard updates (especially webhook and CRD schema changes) must not create protection gaps:

- Webhook updates must use rolling deployment with `maxUnavailable: 0`
- CRD schema changes must use conversion webhooks (not delete-and-recreate)
- Guard spec changes must trigger immediate reconciliation, not wait for next CronJob cycle

### Circuit Breaker for Blocking Layers

A blocking layer that fails repeatedly (e.g., webhook pod crashlooping) could halt all deployments. The system must support automatic degradation:

- After N consecutive failures within a time window, temporarily downgrade from `blocking` to `detecting`
- Emit a critical alert when degradation occurs
- Auto-restore to `blocking` when health check passes again
- Log all degradation/restoration events with full context

---

## Version Graduation & Migration

*Derived from architectural review suggestions R1-S7, R1-S8, R2-S2, R2-S20.*

### CRD Version Graduation (v1alpha1 → v1)

The InfrastructureGuard CRD starts at `v1alpha1`. Graduation to `v1` requires:

1. **Conversion webhook**: Serve both `v1alpha1` and `v1` simultaneously during migration
2. **Storage version migration**: Move stored resources from `v1alpha1` to `v1`
3. **Deprecation timeline**: `v1alpha1` deprecated for 2 minor releases after `v1` GA
4. **Breaking change policy**: No breaking changes to `v1` spec without a new API version

### Guard Resource Versioning

Individual guard resources evolve over time. The status must track:

- `status.generation`: Increments on each spec change
- `status.observedGeneration`: Last generation the controller reconciled
- `status.specHash`: SHA256 of the spec for change detection
- Protection history (which layers were active at which time) for audit

### Migration from Ad-Hoc Format

The existing `pvc-protection.yaml` uses a different schema (`spec.protectedVolumes`). Migration must:

- Provide a documented migration path with a conversion script or guide
- Support backward compatibility during transition (existing consumers read old format)
- Validate the migrated resource against the new CRD schema

### ProjectContext Migration

When `spec.guards[]` is added to the ProjectContext CRD (Phase 5), existing ProjectContext resources must not break:

- The new field must be optional with a sensible default (empty list)
- Existing resources must pass validation without modification
- A migration guide must document how to add guard references

---

## Security & RBAC Requirements

*Derived from architectural review suggestions R1-S10, R2-S6, R2-S13.*

### Authentication & Credential Management

Protection layers that interact with the Kubernetes API require credentials. The feature must specify:

| Layer Type | Credential Requirement | Recommendation |
|------------|----------------------|----------------|
| `admission-webhook` | ServiceAccount with TLS cert | Cert-manager issued, auto-rotated |
| `drift-monitor` | ServiceAccount with read access | Namespace-scoped, read-only |
| `continuous-monitor` | ServiceAccount with read access | Namespace-scoped, read-only |
| `cli-hook` | Inherits user's kubeconfig | No additional credentials needed |
| `agent-instruction` | None | N/A |
| `permission-scope` | None | N/A |

### Minimum Privilege per Layer Type

Each layer type must document its minimum required RBAC permissions:

- **Drift-check CronJob**: `get`, `list` on Deployments and PVCs in the guard's namespace only (not cluster-scoped)
- **Webhook server**: `get` on InfrastructureGuard resources in its namespace
- **Guard controller/evaluator**: `get`, `list` on InfrastructureGuard; `patch` on status subresource
- **Agent guidance merger**: `get`, `list` on InfrastructureGuard and ProjectContext

RBAC definitions must be namespace-scoped by default, with documented expansion paths for multi-namespace use cases.

---

## Testing Requirements

*Derived from architectural review suggestions R1-S4, R2-S11.*

### Automated Test Strategy

Manual `kubectl` validation commands are insufficient for a reusable ContextCore standard. The implementation must include automated tests:

| Test Type | What It Covers | Tooling |
|-----------|---------------|---------|
| CRD schema validation | Spec/status schema, required fields, enum values | `kubectl apply --dry-run=server`, schema unit tests |
| Drift-check format | Parser handles new `spec.invariants[]` format | Shell script unit tests |
| Dashboard JSON | Valid Grafana dashboard structure, no broken queries | JSON schema validation, grafonnet tests |
| Webhook decisions | Admission controller accepts/denies correctly | Integration tests with `kubectl apply --dry-run=server` |
| Health check protocol | All layer health checks return consistent results | Health check runner integration tests |
| Guard template validation | Templates produce valid InfrastructureGuard resources | Template expansion + schema validation |

### Negative Test Cases

Validation must include negative tests that verify protection actually blocks violations:

- Apply a deployment with `emptyDir` where PVC is expected → webhook denies
- Remove a protection layer → posture score decreases
- Stop the webhook pod → `failOpen: true` behavior confirmed, alert fires
- Apply a spec change → reconciliation triggers within SLO window
- Submit an invalid InfrastructureGuard resource → CRD validation rejects

---

## Layer Taxonomy Clarifications

*Derived from architectural review suggestions R2-S1, R2-S5, R2-S17.*

### Layer Boundary Rules

Each protection layer must have a clearly defined boundary to prevent overlap and ensure correct coverage accounting:

- A single enforcement action must be attributed to exactly one layer
- If multiple layers could intercept the same action, the **earliest in the chain** gets credit
- The coverage matrix must not double-count a vector as "covered" by overlapping layers with the same enforcement level
- Layer `scope` (agent-only, cluster-wide, ci-pipeline) defines the boundary of applicability

### Standardized Health Check Protocol

All layer health checks must follow a consistent protocol:

| Health Check Type | Expected Behavior | Return Value |
|-------------------|-------------------|--------------|
| `file-exists` | Check file path exists and is executable | `healthy` / `unhealthy` |
| `k8s-resource` | Check resource exists and meets condition | `healthy` / `unhealthy` / `degraded` |
| `http-endpoint` | HTTP GET returns 200 within timeout | `healthy` / `unhealthy` |
| `script` | Run a script, check exit code | 0 = `healthy`, non-zero = `unhealthy` |

All health checks must include:
- A timeout (default 10s)
- A retry count (default 1)
- Last check timestamp
- Human-readable message on failure

### Correlated Failure Domain Analysis

Multiple protection layers may share dependencies. The guard should document known failure correlations:

- **Node failure**: Takes down webhook pod, drift-check CronJob, and Grafana simultaneously
- **Namespace deletion**: Removes all namespaced resources including the guard itself
- **API server unavailability**: All K8s-dependent layers fail together
- **Certificate expiry**: Webhook and any mTLS-dependent layers fail together

The dashboard Gap Analysis row should highlight layers sharing a failure domain.

---

## Status Schema Additions

*Derived from architectural review suggestions R2-S9, R2-S16, R2-S18.*

### State Reconciliation Policy

When the guard spec changes, the status must be reconciled:

- Reconciliation must begin within 30 seconds of a spec change (not wait for CronJob)
- During reconciliation, `status.posture` should be set to `unknown` until evaluation completes
- `status.observedGeneration` tracks which spec version the status reflects
- Stale status (where `observedGeneration < metadata.generation`) must trigger a warning alert

### Event Retention Policy

The `status.recentEvents` array must have bounded growth:

- Maximum 100 events per guard resource
- Events older than 7 days are pruned
- A `lastPruned` timestamp tracks when cleanup last ran
- Events are ordered newest-first for efficient access

### Guard Template Library

Common protection patterns should be captured as reusable templates:

- `pvc-protection` — Protect PVC bindings (the motivating use case)
- `secret-protection` — Protect secret references in deployments
- `resource-limits` — Protect resource limits/requests from removal
- `rbac-protection` — Protect RBAC bindings from modification

Templates are InfrastructureGuard resources with placeholder values and documentation. They are not enforced — they are starting points.

---

## Dashboard Additions

*Derived from architectural review suggestions R1-S5, R1-S6.*

### Graceful Degradation

Dashboard panels must handle missing data gracefully:

- When Prometheus metrics are unavailable (Phase 1, before Phase 2 telemetry), panels should show static baseline values rather than "No data"
- PromQL queries should include fallback expressions (e.g., `or vector(0)`)
- LogQL panels should show "No events in time range" rather than erroring

### Guard Evaluator Self-Monitoring

The guard evaluator (CronJob or controller that computes posture scores) must be self-monitoring:

- A `contextcore_guard_evaluator_last_run_timestamp` metric tracks the last successful evaluation
- Alert: `ContextCoreGuardEvaluatorStale` fires if no evaluation in 2x the expected interval
- The evaluator should emit its own health endpoint or Prometheus metrics for scraping

---

## Telemetry Standardization

*Derived from architectural review suggestions R1-S9, R2-S12.*

### Metrics Implementation

All Prometheus metrics must be emitted using the `prometheus_client` Python library (not manual text format). This ensures:

- Correct content-type headers
- Proper histogram/summary implementation
- Registry management and multi-process support

### Attribute Naming Consistency

All OTel semantic attributes across all layers must follow consistent naming:

- Prefix: `guard.` for guard-level, `guard.layer.` for layer-level
- Snake_case for multi-word attributes (e.g., `guard.posture_score`, not `guard.postureScore`)
- Enum values must use lowercase with hyphens (e.g., `pvc-protection`, not `pvcProtection`)
- All layers must emit the same base attribute set (`guard.id`, `guard.type`, `guard.action`) plus layer-specific attributes

---

## Relationship to Kubernetes Native Policies

*Derived from rejected suggestion R2-S8, which noted this belongs in the feature document.*

The InfrastructureGuard is complementary to (not a replacement for) Kubernetes-native policy mechanisms:

| Mechanism | Relationship to InfrastructureGuard |
|-----------|-------------------------------------|
| **NetworkPolicy** | A guard can reference NetworkPolicy as a protection layer of type `network-policy` |
| **RBAC** | A guard can reference RBAC restrictions as a layer of type `rbac-policy` |
| **OPA/Gatekeeper** | A guard can reference OPA constraints as a layer of type `opa-policy` |
| **PodSecurityStandards** | Could be modeled as a `ci-gate` or `admission-webhook` layer |

The guard does not duplicate these mechanisms — it provides a unified visibility layer showing which mechanisms are in place and where gaps exist. The coverage matrix visualizes how native policies contribute to the overall defense posture.

---

## Non-Goals

- **100% coverage is not the goal.** The dashboard explicitly shows what IS and IS NOT in place. The value is visibility into protection posture, not mandating every possible layer.
- **Not a replacement for GitOps.** This resource describes protection layers; it doesn't implement GitOps. If you adopt ArgoCD, you add a layer of type `gitops-controller` to the guard.
- **Not specific to PVC protection.** While motivated by the PVC incident, the InfrastructureGuard schema is generic. Future guards could protect: database connection strings, secret references, resource limits, network policies, RBAC bindings, or any Kubernetes resource property.

---

## Success Criteria

1. A team can declare an InfrastructureGuard and see their protection posture score
2. The dashboard shows which vectors are covered and which are gaps
3. Adding or removing a protection layer is a YAML edit, not a code change
4. Agents automatically inherit guard constraints via ProjectContext integration
5. Alert fires within 5 minutes of a protection layer going down
6. Drift detection alert fires within 10 minutes of an invariant violation

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R3-F1 | Add acceptance criteria for each protection layer type | claude-4 (claude-opus-4-20250514) | Feature defines 12 layer types but implementation needs concrete test criteria to verify correct behavior | 2026-02-11 21:38:17 UTC |
| R3-F2 | Specify guard resource limits and quotas | claude-4 (claude-opus-4-20250514) | Unbounded guard complexity could overwhelm controllers and degrade cluster performance | 2026-02-11 21:38:17 UTC |
| R3-F3 | Define stable API for external protection layer plugins | claude-4 (claude-opus-4-20250514) | Organizations need to add custom protection layers specific to their infrastructure without forking | 2026-02-11 21:38:17 UTC |
| R3-F4 | Clarify invariant JSONPath syntax | claude-4 (claude-opus-4-20250514) | Ambiguous JSONPath syntax specification could lead to implementation incompatibilities | 2026-02-11 21:38:17 UTC |
| R3-F5 | Add troubleshooting guide appendix | claude-4 (claude-opus-4-20250514) | Complex multi-layer protection system needs systematic debugging documentation for operators | 2026-02-11 21:38:17 UTC |
| R3-F1 | Add acceptance criteria for each protection layer type | claude-4 (claude-opus-4-20250514) | Essential for implementers to know when each layer is correctly functioning - prevents ambiguity in testing | 2026-02-11 21:50:01 UTC |
| R3-F2 | Specify guard resource limits and quotas | claude-4 (claude-opus-4-20250514) | Prevents resource exhaustion and ensures guards remain manageable - critical for production stability | 2026-02-11 21:50:01 UTC |
| R3-F4 | Clarify invariant JSONPath syntax | claude-4 (claude-opus-4-20250514) | Implementation plan shows JSONPath usage but doesn't specify dialect - Kubernetes JSONPath is the right choice for consistency | 2026-02-11 21:50:01 UTC |
| R3-F5 | Add troubleshooting guide appendix | claude-4 (claude-opus-4-20250514) | Complex system with multiple failure modes - operators need systematic debugging approaches | 2026-02-11 21:50:01 UTC |
| R4-F1 | Add circuit breaker implementation requirement | claude-4 (claude-opus-4-20250514) | Automatic degradation is promised but not specified - circuit breaker pattern is industry standard for this | 2026-02-11 21:50:01 UTC |
| R4-F2 | Expand negative test cases with specific scenarios | claude-4 (claude-opus-4-20250514) | Testing philosophy stated but no concrete tests - specific scenarios ensure thorough validation | 2026-02-11 21:50:01 UTC |
| R4-F3 | Clarify guard controller vs evaluator distinction | claude-4 (claude-opus-4-20250514) | Terms used interchangeably cause confusion - clear terminology prevents architectural misunderstanding | 2026-02-11 21:50:01 UTC |
| R4-F4 | Add Pod Security Standards alignment | claude-4 (claude-opus-4-20250514) | Security requirements should reference Kubernetes standards - PSS provides clear compliance target | 2026-02-11 21:50:01 UTC |
| R4-F5 | Specify guard status size limits | claude-4 (claude-opus-4-20250514) | Unbounded status can break etcd - must enforce limits to prevent cluster instability | 2026-02-11 21:50:01 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R3-F3 | Define stable API for external protection layer plugins | claude-4 (claude-opus-4-20250514) | Adds complexity without demonstrated need - the 12 built-in types cover known use cases | 2026-02-11 21:50:01 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-20250514)
- **Date**: 2026-02-11 21:37:36 UTC
- **Scope**: Requirements traceability and architecture review

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|----|------|----------|------------|-----------|-------------------|---------------------|
| R3-F1 | Validation | high | Add acceptance criteria for each protection layer type | Feature doc defines 12 layer types but no criteria for when each is correctly implemented. Implementation needs concrete tests. | Add "Acceptance Criteria" subsection under Protection Layer Taxonomy with specific tests per type | Each layer type has 3+ specific test cases documented |
| R3-F2 | Architecture | high | Specify guard resource limits and quotas | Feature doc allows unlimited guards/layers/vectors but large guards could overwhelm controllers. Need practical limits. | Add "Resource Limits" section: max 50 layers, 100 invariants, 50 vectors per guard | Test guard with 100+ layers rejected by validation |
| R3-F3 | Interfaces | medium | Define stable API for external protection layer plugins | Feature assumes all 12 layer types are built-in but extensibility would allow custom organizational layers | Add "Custom Layer Types" section with plugin API specification | Prototype one custom layer type using the API |
| R3-F4 | Data | medium | Clarify invariant JSONPath syntax | Feature shows `spec.template.spec.volumes[?name=grafana-storage]` but doesn't specify which JSONPath library/syntax | Add note specifying Kubernetes JSONPath syntax as used by kubectl | Test complex JSONPath expressions evaluate correctly |
| R3-F5 | Ops | medium | Add troubleshooting guide appendix | Feature is complex; operators need systematic debugging approach when protection fails | Add "Appendix: Troubleshooting" with common issues and resolution steps | Each major component has troubleshooting section |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None (this is the first R3 review)

#### Review Round R4

- **Reviewer**: claude-4 (claude-opus-4-20250514)
- **Date**: 2026-02-11 21:49:08 UTC
- **Scope**: Requirements traceability and architecture review — dual-document gap-hunting mode

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Ops | critical | Add circuit breaker implementation requirement | Feature requires automatic degradation from blocking→detecting but provides no implementation guidance. This is critical for production stability. | Add new section "Circuit Breaker Implementation" with state machine, thresholds, and restoration logic | Test circuit breaker with failing webhook; verify automatic degradation and restoration |
| R4-F2 | Validation | high | Expand negative test cases with specific scenarios | Feature mentions negative testing need but provides no concrete test cases. Hard to verify protection works without these. | Add "Negative Test Scenarios" section with 10+ specific test cases including commands and expected blocks | Execute each negative test; verify protection layer blocks correctly |
| R4-F3 | Architecture | medium | Clarify guard controller vs evaluator distinction | Feature uses "controller" and "evaluator" interchangeably but these have different implications in Kubernetes. | Add terminology section distinguishing evaluator (stateless) from controller (stateful reconciliation) | Document which pattern ContextCore uses |
| R4-F4 | Security | medium | Add Pod Security Standards alignment | Feature requires security hardening but doesn't reference Kubernetes Pod Security Standards (restricted/baseline). | Add section mapping InfrastructureGuard security requirements to Pod Security Standards | Deploy guards under restricted PSS; verify functionality |
| R4-F5 | Data | medium | Specify guard status size limits | Feature allows unlimited events/layers in status. Large status objects can break etcd. | Add status size limits: max 100 events, max 50 layers, max 20KB total status | Test with maximum sizes; verify Kubernetes accepts |

