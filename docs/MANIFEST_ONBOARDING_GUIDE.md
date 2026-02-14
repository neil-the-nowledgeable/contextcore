# Manifest Onboarding Guide

How to create a `.contextcore.yaml` v2 manifest for any project and export its artifact manifest for Wayfinder.

This guide walks through the full lifecycle: scaffold, fill in business context, add strategy and governance, validate, and export. It applies to any project in the ContextCore ecosystem -- microservices, libraries, SDKs, or infrastructure components.

## Quick Navigation

| I want to... | Go to... |
|--------------|----------|
| Create a new manifest from scratch | [Step 1: Scaffold the Manifest](#step-1-scaffold-the-manifest) |
| Understand what fields are required | [Minimal Viable Manifest](#minimal-viable-manifest) |
| Add business context (SLOs, risks) | [Step 2: Fill in Business Context](#step-2-fill-in-business-context-spec) |
| Add objectives and tactics | [Step 3: Add Strategic Context](#step-3-add-strategic-context-strategy) |
| Add agent governance rules | [Step 4: Add Governance](#step-4-add-governance-guidance) |
| Add derived insights | [Step 5: Add Insights](#step-5-add-insights-optional) |
| Validate my manifest | [Step 6: Validate](#step-6-validate) |
| Export for Wayfinder | [Step 7: Export for Wayfinder](#step-7-export-for-wayfinder) |
| Validate A2A pipeline integrity | [Step 8: A2A Pipeline Integrity](#step-8-validate-a2a-pipeline-integrity-optional) |
| See a real-world example | [Worked Example: startd8-sdk](#worked-example-startd8-sdk) |
| Look up enum values | [Field Reference](#field-reference) |
| Fix validation errors | [Troubleshooting](#troubleshooting) |

## Prerequisites

1. **ContextCore CLI installed**:
   ```bash
   cd /path/to/ContextCore
   pip3 install -e ".[dev]"
   ```

2. **Familiarity with the project being onboarded**: You need to know (or decide) the project's business criticality, SLO targets, known risks, and strategic objectives.

3. **Python 3.9+** available as `python3`.

## Step 1: Scaffold the Manifest

### Option A: Use the CLI (recommended)

```bash
contextcore manifest init --name my-project --version v2
```

This creates `.contextcore.yaml` with a starter v2 template and prints the recommended 6-step workflow:

```
Next steps:
  1. Edit .contextcore.yaml to add your project details
  2. Run: contextcore manifest validate --path .contextcore.yaml
  3. Run: contextcore install init
  4. Run: contextcore manifest export -p .contextcore.yaml -o ./out/export --emit-provenance
  5. Run: contextcore contract a2a-check-pipeline ./out/export
  6. Run: startd8 workflow run plan-ingestion (or contextcore contract a2a-diagnose)
```

Use `--path` to write to a different location:

```bash
contextcore manifest init --name my-project --version v2 --path path/to/.contextcore.yaml
```

### Option B: Copy from the v2 example

```bash
cp /path/to/ContextCore/examples/context_manifest_v2_example.yaml .contextcore.yaml
```

Then replace the example values with your project's details.

### Option C: Migrate from v1.1

If the project already has a v1.1 manifest:

```bash
contextcore manifest migrate --path .contextcore.yaml --in-place
```

This preserves all existing data and adds the v2 `strategy` and `guidance` sections.

### Minimal Viable Manifest

The smallest valid v2 manifest requires only `metadata`, `spec.project`, `spec.business`, and at least one `spec.targets` entry:

```yaml
apiVersion: contextcore.io/v1alpha2
kind: ContextManifest

metadata:
  name: my-project
  owners:
    - team: engineering

spec:
  project:
    id: my-project
    name: My Project
  business:
    criticality: medium
    owner: engineering
  targets:
    - kind: Deployment
      name: my-service
      namespace: default
```

Everything else (`strategy`, `guidance`, `insights`, `state`) is optional and can be added incrementally.

## Step 2: Fill in Business Context (spec)

The `spec` section maps to the Kubernetes ProjectContext CRD. It contains operational metadata that drives observability derivation.

### Project Identification

```yaml
spec:
  project:
    id: checkout-service          # Unique project ID (required)
    name: Checkout Service        # Human-readable name
    description: >                # Optional longer description
      Handles cart checkout, payment processing, and order creation
    epic: EPIC-42                 # Optional epic reference
```

### Business Context

```yaml
  business:
    criticality: critical         # Required: critical | high | medium | low
    owner: commerce-platform      # Required: owning team
    value: revenue-primary        # Optional: business value classification
    costCenter: platform-eng      # Optional: cost center code
```

**Criticality drives observability derivation:**

| Criticality | Trace Sampling | Metrics Interval | Alert Severity | Dashboard Placement |
|-------------|---------------|------------------|----------------|---------------------|
| `critical`  | 100%          | 10s              | P1             | featured            |
| `high`      | 50%           | 15s              | P2             | standard            |
| `medium`    | 10%           | 30s              | P3             | standard            |
| `low`       | 1%            | 60s              | P4             | standard            |

### Requirements (SLOs)

```yaml
  requirements:
    availability: "99.95"         # Target availability percentage
    latencyP99: "200ms"           # P99 latency target
    latencyP50: "50ms"            # P50 latency target (optional)
    throughput: "5000rps"         # Throughput target (optional)
    errorBudget: "0.05"           # Error budget percentage (optional)
```

Format rules:
- `availability` and `errorBudget`: plain number string (e.g., `"99.95"`, `"0.05"`)
- `latencyP50` / `latencyP99`: number with unit suffix (e.g., `"200ms"`, `"1s"`)
- `throughput`: number with unit suffix (e.g., `"1000rps"`, `"500rpm"`)

### Targets

At least one target is required. Targets identify the Kubernetes resources (or logical services) that this project maps to.

**For Kubernetes services:**

```yaml
  targets:
    - kind: Deployment
      name: checkout-api
      namespace: commerce
    - kind: Deployment
      name: checkout-worker
      namespace: commerce
```

**For libraries and SDKs** (no K8s deployment): use `Service` kind with a logical name:

```yaml
  targets:
    - kind: Service
      name: startd8-agent-runtime
      namespace: agents
```

### Risks

```yaml
  risks:
    - type: availability
      description: "LLM provider API failure cascades to all dependent agents"
      priority: P1
      mitigation: "Provider fallback chain with configurable retry"
    - type: financial
      description: "Cost tracking drift between SDK estimates and provider invoices"
      priority: P2
      mitigation: "Reconciliation job compares tracked costs with billing data"
```

### Observability Overrides

Override the defaults derived from criticality:

```yaml
  observability:
    traceSampling: 1.0            # Override: sample everything
    metricsInterval: "30s"
    logLevel: info                # debug | info | warn | error
    dashboardPlacement: standard  # featured | standard | archived
    alertChannels:
      - commerce-oncall
```

## Step 3: Add Strategic Context (strategy)

The `strategy` section connects operational work to business objectives. It has two main components: **objectives** (the "why") and **tactics** (the "how").

### Objectives

Each objective represents a measurable business goal:

```yaml
strategy:
  objectives:
    - id: OBJ-RELIABILITY
      description: "Achieve 99.99% availability for Black Friday"
      keyResults:
        - metricKey: availability
          unit: "%"
          target: 99.99
          targetOperator: gte
          baseline: 99.95
          window: "30d"
          dataSource: "promql:avg_over_time(up{service='checkout'}[30d])"
```

**ID pattern**: `OBJ-` followed by uppercase alphanumeric and hyphens (e.g., `OBJ-RELIABILITY`, `OBJ-COST-ACCURACY`).

**KeyResult fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `metricKey` | Yes | Metric identifier |
| `unit` | No | Unit: `%`, `ms`, `s`, `rps`, `rpm`, `count`, `ratio` |
| `target` | No | Target numeric value |
| `targetOperator` | No | `gte` (at least), `lte` (at most), `eq` (exactly) |
| `baseline` | No | Starting value for comparison |
| `window` | No | Evaluation window (e.g., `"7d"`, `"30d"`) |
| `dataSource` | No | Query to compute the metric |

### Tactics

Tactics are specific actions implementing objectives:

```yaml
  tactics:
    - id: TAC-CIRCUIT-BREAKER
      description: "Implement circuit breaker for payment gateway calls"
      status: in_progress
      owner: alice@example.com
      linkedObjectives:
        - OBJ-RELIABILITY
      startDate: "2024-01-10"
      dueDate: "2024-01-25"
      progress: 60
      artifacts:
        - type: pr
          id: pr-142
          url: "https://github.com/example/checkout-service/pull/142"

    - id: TAC-CACHE-INVENTORY
      description: "Add Redis cache layer for inventory checks"
      status: planned
      linkedObjectives:
        - OBJ-LATENCY

    - id: TAC-ASYNC-NOTIFICATIONS
      description: "Move order notifications to async queue"
      status: blocked
      blockedReason: "Waiting for Kafka cluster provisioning (INFRA-234)"
      linkedObjectives:
        - OBJ-LATENCY
```

**ID pattern**: `TAC-` followed by uppercase alphanumeric and hyphens.

**Cross-reference requirement**: every ID in `linkedObjectives` must match an existing objective ID. The validator will reject the manifest if a tactic references a nonexistent objective.

**Blocked reason requirement**: if `status: blocked`, then `blockedReason` is required.

### Strategy Groups (optional)

Group objectives into strategic themes:

```yaml
  strategyGroups:
    - id: STRAT-ASYNC-FIRST
      description: "Adopt async-first patterns to reduce synchronous dependencies"
      horizon: near                # now | next | later
      rationale: "Black Friday readiness requires removing sync calls"
      objectiveRefs:
        - OBJ-RELIABILITY
        - OBJ-LATENCY
```

## Step 4: Add Governance (guidance)

The `guidance` section directs agent behavior. It is what makes v2 an "active control plane" rather than a passive config file.

### Focus Areas

Tell agents what to prioritize:

```yaml
guidance:
  focus:
    areas:
      - reliability
      - performance
      - Black Friday preparation
    reason: "All work should prioritize Black Friday readiness (Nov 29)"
    until: "2024-11-30"
```

### Constraints

Hard rules that agents must follow. `severity: blocking` means agents should stop and ask if they would violate it:

```yaml
  constraints:
    - id: C-NO-NEW-SYNC-DEPS
      rule: "Do not add new synchronous external service dependencies"
      severity: blocking
      rationale: "Sync dependencies increase latency and reduce fault tolerance"
      appliesTo:
        - src/services/
        - src/handlers/

    - id: C-PREFER-STRUCTURED-LOGGING
      rule: "Use structured logging (JSON) instead of string interpolation"
      severity: warning
      rationale: "Improves log searchability in Loki"
```

### Preferences

Non-blocking guidance for preferred patterns:

```yaml
  preferences:
    - id: PREF-CIRCUIT-BREAKER
      description: "Use resilience4j for circuit breakers over custom implementations"
      example: "CircuitBreaker.ofDefaults('payment-gateway')"
```

### Questions

Open questions for agents to answer. This creates a feedback loop where agents can update the manifest:

```yaml
  questions:
    - id: Q-REDIS-CLUSTER
      question: "Should we use Redis Cluster or Redis Sentinel for the cache layer?"
      status: open
      priority: high

    - id: Q-CIRCUIT-BREAKER-CONFIG
      question: "What are the recommended failure thresholds?"
      status: answered
      priority: medium
      answer: "5 failures in 30 seconds with 60 second reset timeout"
      answeredBy: agent:claude
      answeredAt: "2024-01-18T10:30:00Z"
```

## Step 5: Add Insights (optional)

Insights capture derived knowledge, detected patterns, or signals. They are ephemeral -- each has an optional `expiresAt` after which it is stale.

```yaml
insights:
  - id: INS-DEP-EOL
    type: risk
    summary: "PostgreSQL driver version 42.2 reaches EOL in 60 days"
    confidence: 0.95
    source: "scanner:dependency-check"
    severity: critical
    observedAt: "2024-01-15T08:00:00Z"
    expiresAt: "2024-03-15T00:00:00Z"
    impact: "Security vulnerabilities will not be patched after EOL"
    evidence:
      - type: scanner-report
        ref: "https://nvd.nist.gov/vuln/detail/CVE-2024-XXXX"
        description: "CVE details for vulnerable driver version"
    recommendedActions:
      - "Upgrade to PostgreSQL driver 42.7+ in TAC-DEP-UPGRADE"
      - "Create upgrade tactic if not exists"
```

**ID pattern**: `INS-` followed by uppercase alphanumeric and hyphens.

**Insight fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique insight ID |
| `type` | Yes | `risk`, `pattern`, or `opportunity` |
| `summary` | Yes | Brief description |
| `confidence` | Yes | 0.0 to 1.0 |
| `source` | Yes | Origin (e.g., `"agent:claude"`, `"scanner:dependency-check"`) |
| `severity` | No | `critical`, `high`, `medium`, `low`, `info` (default: `medium`) |
| `observedAt` | No | ISO 8601 timestamp |
| `expiresAt` | No | ISO 8601 expiration timestamp |
| `impact` | No | Business or technical impact description |
| `evidence` | No | List of evidence items (type, ref, description) |
| `recommendedActions` | No | List of suggested next steps |

## Step 6: Validate

Run the validator to check schema compliance and cross-references:

```bash
contextcore manifest validate --path .contextcore.yaml
```

Expected output for a valid manifest:

```
Valid v2 manifest: .contextcore.yaml
  Warning: Manifest has 2 open question(s)
```

Use `--strict` to treat warnings as errors:

```bash
contextcore manifest validate --path .contextcore.yaml --strict
```

Use `--format json` for CI/automation:

```bash
contextcore manifest validate --path .contextcore.yaml --format json
```

Inspect the parsed contents with `show`:

```bash
contextcore manifest show --path .contextcore.yaml
contextcore manifest show --path .contextcore.yaml --format yaml
contextcore manifest show --path .contextcore.yaml --format json
```

## Step 7: Export for Wayfinder

The `export` command generates two files that bridge ContextCore (knows WHAT is needed) and Wayfinder (knows HOW to create artifacts). Use `--emit-provenance` to include checksum chain for A2A gate validation:

```bash
contextcore manifest export -p .contextcore.yaml -o output/ --emit-provenance
```

This produces:

```
output/
  my-project-projectcontext.yaml    # Kubernetes CRD (do NOT kubectl apply directly)
  my-project-artifact-manifest.yaml # Artifact manifest for Wayfinder
```

### What Gets Generated

1. **ProjectContext CRD**: The operational `spec` section extracted as a Kubernetes resource. This is a reference file -- Wayfinder implementations use it to configure cluster resources.

2. **Artifact Manifest**: A specification of all observability artifacts the project needs, derived from its business context. For each target, it generates requirements for:
   - Dashboard
   - Prometheus alerting rules
   - SLO definition
   - Service monitor
   - Loki recording rules
   - Notification policy
   - Runbook (required for `critical` services)

### Coverage Summary

The export prints a coverage summary showing what exists vs what is needed:

```
Coverage Summary:
  Overall: 0.0%
  Required: 5
  Existing: 0

Missing by Type:
  - dashboard: 1
  - prometheus_rule: 1
  - slo_definition: 1
  - service_monitor: 1
  - notification_policy: 1
```

### Marking Existing Artifacts

If artifacts already exist, mark them so coverage tracking is accurate:

```bash
# Mark specific artifacts
contextcore manifest export -p .contextcore.yaml -o output/ \
  --existing "checkout_api-dashboard:grafana/dashboards/checkout.json" \
  --existing "checkout_api-prometheus-rules:rules/checkout.yaml"

# Or scan a directory for artifacts matching naming conventions
contextcore manifest export -p .contextcore.yaml -o output/ \
  --scan-existing ./grafana/provisioning/
```

### Programmatic Onboarding Metadata

For plan ingestion workflows that consume the export (e.g., startd8 artisan, Coyote):

```bash
contextcore manifest export -p .contextcore.yaml -o output/ --emit-onboarding
```

This produces `onboarding-metadata.json` with:
- **artifact_manifest_path** / **project_context_path** — references for downstream consumers
- **artifact_types** — schema per type (parameter keys, output conventions)
- **coverage** — gaps, by-target, by-type summary
- **semantic_conventions** — OTel attributes, metrics, query templates for dashboards
- **guidance** — constraints, preferences from governance
- **provenance** — when used with `--emit-provenance`

### Dry Run

Preview without writing files:

```bash
contextcore manifest export -p .contextcore.yaml -o output/ --dry-run
```

## Worked Example: startd8-sdk

The `startd8-sdk` (Beaver/Amik) was onboarded to ContextCore with the following decisions:

**Business context**: `criticality: high` (not `critical`) because it is an SDK consumed by other services, not a directly user-facing production service. `value: enabler` because it enables other packages.

**Targets**: A single `Service` target (`startd8-agent-runtime`) since the SDK is a library, not a K8s Deployment. Libraries use `Service` kind with a logical name.

**Objectives**: Three objectives covering provider reliability (99.9% success rate), cost tracking accuracy (<1% variance), and OTel telemetry coverage (100% of interactions).

**Tactics**: Five tactics, two already `done` (OpenLLMetry integration, dual-emit), one `in_progress` (Artisan stabilization), two `planned` (provider fallback, cost reconciliation).

**Constraints**: Three rules -- no breaking API changes (`blocking`), lazy-load provider dependencies (`blocking`), and TrackedAgentMixin inheritance for new agents (`warning`).

**Insights**: Three -- an OpenLLMetry overlap pattern, a Gemini install risk, and an Artisan telemetry opportunity.

The full manifest is at `startd8-sdk/.contextcore.yaml`. The onboarding pipeline:

```bash
# Validate
contextcore manifest validate --path ~/Documents/dev/startd8-sdk/.contextcore.yaml

# Inspect
contextcore manifest show --path ~/Documents/dev/startd8-sdk/.contextcore.yaml

# Export
contextcore manifest export \
  -p ~/Documents/dev/startd8-sdk/.contextcore.yaml \
  -o ~/Documents/dev/startd8-sdk/output/
```

## Field Reference

### Enums: Criticality

| Value | Description |
|-------|-------------|
| `critical` | Revenue-impacting, immediate escalation |
| `high` | Important, same-day response |
| `medium` | Standard priority |
| `low` | Best-effort |

### Enums: BusinessValue

| Value | Description |
|-------|-------------|
| `revenue-primary` | Direct revenue generation |
| `revenue-secondary` | Indirect revenue contribution |
| `cost-reduction` | Reduces operational costs |
| `compliance` | Regulatory or legal requirement |
| `enabler` | Enables other services/teams |
| `internal` | Internal tooling |

### Enums: RiskType

| Value | Description |
|-------|-------------|
| `security` | Security vulnerability or exposure |
| `compliance` | Regulatory compliance risk |
| `data-integrity` | Data corruption or loss |
| `availability` | Service availability risk |
| `financial` | Financial impact risk |
| `reputational` | Brand or reputation risk |

### Enums: TacticStatus

| Value | Description |
|-------|-------------|
| `planned` | Not yet started |
| `in_progress` | Active work underway |
| `blocked` | Blocked (requires `blockedReason`) |
| `in_review` | Under review |
| `done` | Completed |
| `cancelled` | Cancelled |

### Enums: ConstraintSeverity

| Value | Description |
|-------|-------------|
| `blocking` | Agent must stop and ask before violating |
| `warning` | Agent should flag but may proceed |
| `advisory` | Informational guidance only |

### Enums: QuestionStatus

| Value | Description |
|-------|-------------|
| `open` | Awaiting answer |
| `answered` | Answer provided |
| `deferred` | Postponed |

### Enums: InsightSeverity

| Value | Description |
|-------|-------------|
| `critical` | Immediate attention required |
| `high` | High priority |
| `medium` | Standard priority |
| `low` | Low priority |
| `info` | Informational only |

### Enums: TargetKind

| Value | Description |
|-------|-------------|
| `Deployment` | Kubernetes Deployment |
| `StatefulSet` | Kubernetes StatefulSet |
| `DaemonSet` | Kubernetes DaemonSet |
| `Service` | Kubernetes Service (also used for libraries/SDKs) |
| `Ingress` | Kubernetes Ingress |
| `ConfigMap` | Kubernetes ConfigMap |
| `Secret` | Kubernetes Secret |
| `CronJob` | Kubernetes CronJob |
| `Job` | Kubernetes Job |

### Enums: MetricUnit

| Value | Description |
|-------|-------------|
| `%` | Percentage |
| `ms` | Milliseconds |
| `s` | Seconds |
| `rps` | Requests per second |
| `rpm` | Requests per minute |
| `count` | Count |
| `ratio` | Ratio |

### Enums: TargetOperator

| Value | Description |
|-------|-------------|
| `gte` | Greater than or equal (e.g., availability >= 99.9%) |
| `lte` | Less than or equal (e.g., latency <= 200ms) |
| `eq` | Exactly equal (e.g., error count == 0) |

### Enums: DashboardPlacement

| Value | Description |
|-------|-------------|
| `featured` | Highlighted on portfolio view |
| `standard` | Normal visibility |
| `archived` | Hidden from default views |

### Enums: StrategicHorizon

| Value | Description |
|-------|-------------|
| `now` | Current focus (this quarter) |
| `next` | Next up (next quarter) |
| `later` | Long term (12 months+) |

### ID Patterns

| Section | Pattern | Example |
|---------|---------|---------|
| Objectives | `OBJ-[A-Z0-9-]+` | `OBJ-RELIABILITY` |
| Strategies | `STRAT-[A-Z0-9-]+` | `STRAT-ASYNC-FIRST` |
| Tactics | `TAC-[A-Z0-9-]+` | `TAC-CIRCUIT-BREAKER` |
| Insights | `INS-[A-Z0-9-]+` | `INS-DEP-EOL` |
| Constraints | `C-*` (convention) | `C-NO-NEW-SYNC-DEPS` |
| Preferences | `PREF-*` (convention) | `PREF-PYDANTIC-V2` |
| Questions | `Q-*` (convention) | `Q-REDIS-CLUSTER` |

## Troubleshooting

### "Cross-reference validation failed"

```
Tactic 'TAC-FOO' references unknown objective: 'OBJ-BAR'
```

Every entry in a tactic's `linkedObjectives` list must match an `id` in `strategy.objectives`. Fix by either adding the missing objective or correcting the reference.

### "Tactic has status=blocked but missing blocked_reason"

```
Tactic TAC-ASYNC-NOTIFICATIONS has status=blocked but missing blocked_reason
```

When `status: blocked`, the `blockedReason` field is required. Add it:

```yaml
- id: TAC-ASYNC-NOTIFICATIONS
  status: blocked
  blockedReason: "Waiting for Kafka cluster provisioning (INFRA-234)"
```

### "targets: ensure this value has at least 1 item"

The `spec.targets` list requires at least one entry. Even libraries need a logical target:

```yaml
targets:
  - kind: Service
    name: my-library-runtime
    namespace: default
```

### "Artifact manifest generation requires v2 manifest"

The `export` command only works with v2 manifests. Migrate first:

```bash
contextcore manifest migrate --path .contextcore.yaml --in-place
```

### YAML parse errors

Common causes:
- Unquoted special characters in strings (use quotes around values containing `:`, `#`, `{`, `}`)
- Inconsistent indentation (use 2 spaces, no tabs)
- Missing quotes around numeric strings like availability: `"99.95"` (without quotes, YAML treats it as a float)

### Validation error on requirements fields

Format requirements:
- `availability`: numeric string like `"99.95"` (not `"99.95%"`)
- `latencyP99`: duration string like `"200ms"` (not `"200"`)
- `throughput`: rate string like `"1000rps"` (not `"1000"`)

## Step 8: Validate A2A Pipeline Integrity (Optional)

After exporting, run the A2A pipeline checker to validate contract integrity before plan ingestion:

```bash
# Gate 1: 6 structural integrity checks
contextcore contract a2a-check-pipeline ./out/export

# Gate 2: Three Questions diagnostic (after plan ingestion)
contextcore contract a2a-diagnose ./out/export --ingestion-dir ./out/plan-ingestion
```

This validates:
- Structural integrity of exported files
- Checksum chain consistency (`--emit-provenance` required)
- Provenance consistency across artifacts
- Mapping completeness (targets ↔ artifacts)
- Gap parity (coverage gaps ↔ parsed features)
- Design calibration (artifact depth vs criticality)

## Next Steps

After exporting:

1. **Run A2A pipeline checks**: `contextcore contract a2a-check-pipeline ./out/export` — validates export integrity before downstream processing.

2. **Pass artifacts to Wayfinder**: The artifact manifest tells Wayfinder what dashboards, alert rules, SLOs, and other artifacts to generate.

3. **Set up CI validation**: Add manifest validation to your CI pipeline. See [DEPENDENCY_MANIFEST_PATTERN.md](DEPENDENCY_MANIFEST_PATTERN.md) for the pattern.

4. **Re-export with `--scan-existing`**: After Wayfinder creates artifacts, re-run export with `--scan-existing` to update coverage tracking.

5. **Iterate on governance**: As agents work with the project, update the `guidance` section with new constraints, answer questions, and refine focus areas.

6. **Run Three Questions diagnostic**: After plan ingestion, `contextcore contract a2a-diagnose` validates the full pipeline end-to-end.
