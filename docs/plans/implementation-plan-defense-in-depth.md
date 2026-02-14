# Implementation Plan: Defense-in-Depth as a ContextCore Resource

**Companion to**: `feature-enhancement-defense-in-depth.md`
**Implementer**: Human (with agent assistance as needed)
**Approach**: Incremental phases, each independently useful

---

## Phasing Strategy

The implementation is structured so that **each phase delivers standalone value** and can be shipped independently. Later phases build on earlier ones but aren't blocked by them.

```
Phase 1: CRD + Static Dashboard     (the declaration + visibility)
    ↓
Phase 2: Telemetry Instrumentation   (the data pipeline)
    ↓
Phase 3: Dynamic Dashboard + Alerts  (live posture monitoring)
    ↓
Phase 4: Guard Controller            (automated evaluation + reconciliation)
    ↓
Phase 5: Agent Guidance Integration  (constraints flow to agents automatically)
```

---

## Phase 1: CRD Schema + Static Dashboard

**Goal**: Declare the guard as a real CRD and build a dashboard that reads from static/semi-static data. This phase provides the declaration vocabulary and the visibility, even before automated telemetry exists.

### Step 1.1: Define the InfrastructureGuard CRD

**Where**: `~/Documents/dev/wayfinder/vendor/contextcore-spec/crds/infrastructureguard.yaml`
(Also copy to `~/Documents/Deploy/contextcore/crds/` for local cluster)

**What**:
- Write the OpenAPI v3 schema based on the spec in the feature enhancement doc
- Include `spec.invariants[]`, `spec.layers[]`, `spec.vectors[]`, `spec.agentGuidance`, `spec.business`
- Include `status.posture`, `status.postureScore`, `status.layerStatus[]`, `status.invariantStatus[]`, `status.coverage`, `status.recentEvents`
- Add printer columns: Name, Posture, Score, Layers, Invariants, Age
- Register short names: `ig`, `guard`

**Validation**:
```bash
kubectl apply -f contextcore/crds/infrastructureguard.yaml
kubectl explain infrastructureguard.spec
kubectl explain infrastructureguard.spec.layers
```

**Files to create**:
- `vendor/contextcore-spec/crds/infrastructureguard.yaml` (the CRD definition)

**Files to modify**:
- `~/Documents/Deploy/contextcore/kustomization.yaml` (add CRD resource)
- `~/Documents/Deploy/observability/kustomization.yaml` (add guard instance resource)

### Step 1.2: Migrate pvc-protection.yaml to CRD Instance

**Where**: `~/Documents/Deploy/observability/pvc-protection.yaml`

**What**:
- Restructure the existing `pvc-protection.yaml` to conform to the new CRD schema
- Move from the current ad-hoc format to the formal `spec.invariants[]`, `spec.layers[]`, `spec.vectors[]` structure
- Keep backward compatibility: the drift-check.sh and webhook still need to read `protectedVolumes`; either update them to read from the new schema or keep a `protectedVolumes` shorthand that maps to invariants

**Decision point**: The existing consumers (hook, drift-check, webhook) all parse `spec.protectedVolumes`. Options:
  - **Option A**: Update all consumers to read `spec.invariants[]` format (cleaner, more work)
  - **Option B**: Keep `spec.protectedVolumes` as an alias/shorthand that the controller expands to invariants (less breakage)
  - **Option C**: Keep both schemas in the file, with a comment that `protectedVolumes` is legacy (simplest, some duplication)

**Recommendation**: Option A. The consumers are small scripts. Update them to parse the new format.

**Files to modify**:
- `observability/pvc-protection.yaml` (restructure to CRD format)
- `scripts/drift-check.sh` (parse `spec.invariants[]` instead of `spec.protectedVolumes`)
- `observability/pvc-guard/server.py` (parse `spec.invariants[]`)
- `~/.claude/hooks/o11y-pvc-guard.sh` (update protected deployment extraction if needed)

**Validation**:
```bash
kubectl apply -f observability/pvc-protection.yaml
kubectl get guard -n observability
make drift-check                    # still works with new format
kubectl apply -f - --dry-run=server # webhook still blocks emptyDir
```

### Step 1.3: Build the Static Dashboard

**Where**: `~/Documents/Deploy/observability/grafana/dashboards/contextcore/defense-in-depth.json`

**What**:
Build a Grafana dashboard that visualizes the guard's protection posture using **static data panels and Loki log queries** (no custom metrics yet; those come in Phase 2).

**Panel plan for Phase 1** (simplified version of the full dashboard):

| Panel | Type | Data Source | What It Shows |
|-------|------|-------------|---------------|
| Posture Score | gauge | static/annotation | Manual score from guard status (updated by CronJob in Phase 2) |
| Layers Defined | stat | static | Count from guard YAML |
| Invariants Defined | stat | static | Count from guard YAML |
| Layer Status | table | Loki or static | Layer type, enforcement, scope, health |
| Coverage Matrix | table | static | Vectors × Layers with coverage indicators |
| Webhook Decisions | timeseries | Loki | `{app="pvc-guard"} \|= "DENIED" or "ALLOWED"` |
| Recent Protection Events | logs | Loki | Combined webhook + hook log stream |
| Drift Check Results | table | Loki or Mimir | From drift-check output (if logged) |
| Gap Analysis | text/markdown | static | Known gaps from the guard spec |

**Build approach**: Follow the existing ContextCore dashboard conventions:
- Schema version 39
- Tags: `["contextcore", "defense-in-depth"]`
- UID: `contextcore-core-defense-in-depth`
- Title: `[CORE] Defense in Depth`
- Template variables: `$loki_datasource`, `$prometheus_datasource`
- Use the Jsonnet mixin if comfortable, or raw JSON following existing patterns

**Files to create**:
- `observability/grafana/dashboards/contextcore/defense-in-depth.json`

**Files to modify**:
- `observability/grafana/configmap-dashboards-contextcore.yaml` (or whichever ConfigMap provisions dashboards to Grafana -- add the new JSON)

**Validation**:
```bash
make up-observability
# Open Grafana → ContextCore folder → Defense in Depth dashboard
# Verify all panels render (static panels show expected data, Loki panels show webhook logs)
```

### Step 1.4: Fix Known Hook Gaps — COMPLETED 2026-02-11

**Status**: **DONE**

**What was done**:
1. Added Rule 1b: Blocks non-canonical kustomize paths (`kubectl apply -k k8s/observability/` etc.)
2. Added Rule 8b: Blocks absolute-path applies with emptyDir for observability deployments
3. Added tilde expansion (`~/` → `$HOME/`) at top of guard script
4. **Critical additional fix**: Replaced fragile `grep -o '"command":"[^"]*"'` JSON parser in `infra-guard-hook.sh` with `jq -r '.tool_input.command // empty'` — the grep parser silently failed on JSON with spaces after colons (standard formatting), making the hook a complete passthrough
5. Added fail-closed behavior: when jq can't parse the command and the input mentions kubectl, the hook blocks (exit 2) instead of allowing
6. Added decision logging to `~/.claude/hooks/infra-guard.log` with timestamps, ALLOW/BLOCK/PARSE_FAIL verdicts, and rule descriptions
7. Created integration test suite at `~/.claude/hooks/test-infra-guard.sh` with 27 tests covering JSON format variants, canonical allows, cross-project blocks, stdin/inline blocks, harbor guard blocks, and non-kubectl commands — all pass

**Files modified**:
- `~/.claude/hooks/o11y-pvc-guard.sh` (Rules 1b, 8b, tilde expansion)
- `~/.claude/hooks/infra-guard-hook.sh` (jq parser, fail-closed, decision logging)

**Files created**:
- `~/.claude/hooks/test-infra-guard.sh` (27 integration tests)

### Step 1.5: Narrow Permissions — COMPLETED 2026-02-11

**Status**: **DONE**

**What was done**:

Deploy project — removed `Bash(kubectl apply:*)` and `Bash(kubectl create:*)`, replaced with scoped:
- `Bash(kubectl apply -k observability:*)`
- `Bash(kubectl apply -f observability/:*)`
- `Bash(kubectl apply -f namespaces/:*)`
- `Bash(kubectl apply -f contextcore/:*)`
- `Bash(kubectl apply --dry-run:*)`
- `Bash(kubectl apply -f /Users/neilyashinsky/Documents/Deploy/observability/:*)`

Wayfinder project — replaced `Bash(kubectl:*)` with read-only:
- `kubectl get`, `describe`, `logs`, `exec`, `rollout`, `port-forward`, `config`, `cluster-info`, `top`, `apply --dry-run`

**Caveat discovered**: Claude Code auto-adds `Bash(kubectl apply:*)` to settings.local.json when a user approves a specific kubectl apply command. This was detected and removed during the session. Monitor settings.local.json after sessions for re-broadened permissions.

**Files modified**:
- `~/Documents/Deploy/.claude/settings.local.json`
- `~/Documents/dev/wayfinder/.claude/settings.local.json`

---

## Phase 2: Telemetry Instrumentation

**Goal**: Make protection layers emit metrics and logs so the dashboard can show live data.

### Step 2.1: Instrument the Webhook Server

**Where**: `observability/pvc-guard/server.py`

**What**: Add Prometheus metrics endpoint.

**Changes**:
1. Add a `/metrics` endpoint to the HTTP server
2. Track counters:
   - `contextcore_guard_webhook_decisions_total{guard="observability-pvc-protection", action="allowed|denied", deployment="grafana|mimir|..."}`
   - `contextcore_guard_webhook_evaluations_total{guard="observability-pvc-protection"}`
3. Track gauges:
   - `contextcore_guard_webhook_up{guard="observability-pvc-protection"}` (always 1 while server running)

**Implementation approach**: Use `prometheus_client` Python library (add to Dockerfile) or implement the text format manually (it's simple enough for 3 metrics).

**Files to modify**:
- `observability/pvc-guard/server.py` (add /metrics endpoint and counters)
- `observability/pvc-guard/Dockerfile` (add prometheus_client if using the library)

**New files**:
- `observability/pvc-guard/servicemonitor.yaml` (Prometheus ServiceMonitor to scrape the webhook, or add a scrape annotation to the existing service)

**Validation**:
```bash
# Port-forward to the webhook and check metrics
kubectl port-forward -n observability svc/pvc-guard 8443:443 &
curl -k https://localhost:8443/metrics
# Should see contextcore_guard_* metrics
```

### Step 2.2: Instrument Drift Detection

**Where**: `scripts/drift-check.sh`

**What**: Output results in a format that can be scraped or pushed to Prometheus.

**Options**:
- **Option A**: Write a Prometheus textfile to a node-exporter textfile directory (requires node-exporter)
- **Option B**: Push metrics to Mimir's remote-write endpoint via `curl` (simpler for Kind)
- **Option C**: Log results as structured JSON to stdout, picked up by Alloy → Loki, then use Loki-based recording rules

**Recommendation**: Option C (structured logging to Loki). The drift-check already outputs results; add a `--prometheus` flag that outputs Prometheus text format, and a CronJob can push to Mimir's push gateway or simply log it.

**Changes**:
1. Add `--prometheus` output mode to drift-check.sh
2. Output format:
   ```
   contextcore_guard_invariant_compliant{guard="observability-pvc-protection",invariant_id="grafana-pvc",resource="deployment/grafana"} 1
   contextcore_guard_invariant_compliant{guard="observability-pvc-protection",invariant_id="mimir-pvc",resource="deployment/mimir"} 1
   contextcore_guard_posture_score{guard="observability-pvc-protection"} 1.0
   ```

**Files to modify**:
- `scripts/drift-check.sh` (add --prometheus output mode)

### Step 2.3: Create Drift-Check CronJob

**Where**: `observability/drift-check/cronjob.yaml`

**What**: A Kubernetes CronJob that runs drift-check every 5 minutes and pushes results.

**What it does**:
1. Runs `drift-check.sh --prometheus`
2. Pushes metrics to Mimir via remote-write or Pushgateway
3. Logs results as structured JSON (picked up by Alloy → Loki)

**Files to create**:
- `observability/drift-check/cronjob.yaml`
- `observability/drift-check/configmap.yaml` (drift-check script as ConfigMap, or use an init container that clones the repo)
- `observability/drift-check/rbac.yaml` (ServiceAccount with get/list on deployments + PVCs)

**Files to modify**:
- `observability/kustomization.yaml` (add drift-check resources)

**Validation**:
```bash
kubectl get cronjob -n observability
kubectl create job --from=cronjob/drift-check test-drift -n observability
kubectl logs job/test-drift -n observability
# Should see drift-check output with metrics
```

### Step 2.4: Instrument the Hook — PARTIALLY COMPLETED 2026-02-11

**Status**: **PARTIALLY DONE** (decision logging exists, Alloy integration remaining)

**What was done**:
- Decision logging added to `~/.claude/hooks/infra-guard-hook.sh` (implemented during Step 1.4 parser fix)
- Every invocation logged to `~/.claude/hooks/infra-guard.log` with format:
  `TIMESTAMP | ALLOW/BLOCK/PARSE_FAIL | rule description | command (truncated to 200 chars)`
- Log is actively recording decisions (verified with 57 entries)

**Remaining work**:
- Convert log format from pipe-delimited to structured JSON (for Loki compatibility)
- Configure Alloy to tail the log file and forward to Loki
- Add guard/layer metadata fields to log entries

**Files modified**:
- `~/.claude/hooks/infra-guard-hook.sh` (log_decision function at every exit point)

**Files still to modify**:
- Alloy config (add file tail source for hook logs)

---

## Phase 3: Dynamic Dashboard + Alerts

**Goal**: Replace static dashboard panels with live queries and add alerting rules.

### Step 3.1: Update Dashboard with Live Queries

**Where**: `observability/grafana/dashboards/contextcore/defense-in-depth.json`

**What**: Replace static panels from Phase 1 with Prometheus/Loki queries:

| Panel | Query |
|-------|-------|
| Posture Score | `contextcore_guard_posture_score{guard="observability-pvc-protection"}` |
| Layers Active | `count(contextcore_guard_layer_healthy{guard="observability-pvc-protection"} == 1)` |
| Invariants OK | `count(contextcore_guard_invariant_compliant{guard="observability-pvc-protection"} == 1)` |
| Webhook Decisions | `rate(contextcore_guard_webhook_decisions_total[5m])` by action |
| Drift Events | `contextcore_guard_drift_detected_total` over time |
| Event Log | `{app=~"pvc-guard\|drift-check\|o11y-pvc-guard"} \| json` |

### Step 3.2: Create Alert Rules

**Where**: `observability/mimir/rules/contextcore/defense-in-depth-alerts.yaml`

**What**: PrometheusRule resources for the alerts defined in the feature enhancement doc.

**Files to create**:
- `observability/mimir/rules/contextcore/defense-in-depth-alerts.yaml`

**Alert naming**: Follow ContextCore convention `ContextCore[Resource][Issue]`:
- `ContextCoreGuardPostureDegraded`
- `ContextCoreGuardPostureExposed`
- `ContextCoreGuardLayerDown`
- `ContextCoreGuardWebhookDown`
- `ContextCoreGuardDriftDetected`
- `ContextCoreGuardNoRecentCheck`

### Step 3.3: Add Recording Rules

**Where**: `observability/mimir/rules/contextcore/defense-in-depth-recording.yaml`

**What**: Pre-computed aggregations for dashboard performance:
- `guard:contextcore_guard_posture_score:current` -- latest posture score
- `guard:contextcore_guard_layers_active:count` -- count of healthy layers
- `guard:contextcore_guard_invariants_compliant:ratio` -- compliant / total

---

## Phase 4: Guard Controller (Optional)

**Goal**: An operator that watches InfrastructureGuard resources and automatically evaluates protection posture.

### Step 4.1: Guard Evaluator Script

**Where**: `scripts/guard-evaluate.sh` or `src/contextcore/guard/evaluator.py`

**What**: A script/program that:
1. Reads the InfrastructureGuard resource from K8s
2. Evaluates each layer's health check (file-exists, k8s-resource condition, etc.)
3. Evaluates each invariant by querying the live K8s state
4. Computes the posture score using the coverage model
5. Updates the InfrastructureGuard `status` subresource
6. Emits Prometheus metrics

**This could run as**:
- A CronJob (simplest, good enough for most cases)
- A long-running controller watching for changes (more responsive, more complex)
- Part of the existing ContextCore operator (if one exists)

### Step 4.2: Change Webhook FailurePolicy — COMPLETED 2026-02-11

**Status**: **PARTIALLY DONE**

**What was done**:
- Changed `failurePolicy: Ignore` to `failurePolicy: Fail` in `observability/pvc-guard/webhook-config.yaml`
- Applied to cluster with `kubectl apply`
- Verified: webhook correctly denies emptyDir deployments; Fail policy means unavailability blocks deploys (safety > availability tradeoff)

**Remaining work**:
- PodDisruptionBudget not yet created
- Resource limits not yet increased
- 2 replicas with anti-affinity not yet configured

**Files modified**:
- `observability/pvc-guard/webhook-config.yaml` (failurePolicy → Fail)

**Files still to create**:
- `observability/pvc-guard/pdb.yaml` (PodDisruptionBudget)

---

## Phase 5: Agent Guidance Integration

**Goal**: Guard constraints automatically flow into ProjectContext, so any agent reading the ProjectContext inherits infrastructure protection rules.

### Step 5.1: Add InfrastructureGuard Reference to ProjectContext CRD

**Where**: `vendor/contextcore-spec/crds/projectcontext-v2.yaml`

**What**: Add an optional field to ProjectContext spec:
```yaml
spec:
  guards:
    - name: observability-pvc-protection
      namespace: observability
```

The controller (or a static enrichment step) reads the referenced guards and merges their `agentGuidance.constraints` into the ProjectContext's `agentGuidance.constraints`.

### Step 5.2: Implement Constraint Merging

**Where**: `src/contextcore/guard/guidance_merger.py`

**What**: A function that:
1. Takes a ProjectContext and a list of InfrastructureGuard resources
2. For each guard, extracts `spec.agentGuidance.constraints`
3. Merges them into the ProjectContext's constraints with:
   - `id` prefixed with `guard:{guard.name}:`
   - `reason` prefixed with `[Guard: {guard.name}]`
   - `severity` set to `blocking`
4. Returns the enriched ProjectContext

This can be called:
- By the GuidanceReader when loading constraints for an agent
- By the controller when reconciling a ProjectContext
- By `contextcore install verify` during installation checks

### Step 5.3: Add to Semantic Conventions Doc

**Where**: `vendor/contextcore-spec/docs/semantic-conventions.md`

**What**: Add the `guard.*` attribute namespace:

| Attribute | Type | Description |
|-----------|------|-------------|
| `guard.id` | string | InfrastructureGuard resource name |
| `guard.type` | string | Guard type label |
| `guard.layer.id` | string | Protection layer identifier |
| `guard.layer.type` | string | Layer taxonomy type |
| `guard.action` | enum | `allowed`, `denied`, `detected`, `restored` |
| `guard.invariant.id` | string | Invariant identifier |
| `guard.vector.id` | string | Attack vector identifier |
| `guard.posture` | enum | `protected`, `degraded`, `exposed`, `unknown` |
| `guard.posture_score` | float | 0.0-1.0 protection completeness |

---

## File Summary

| Phase | File | Action | Description |
|-------|------|--------|-------------|
| 1.1 | `vendor/contextcore-spec/crds/infrastructureguard.yaml` | Create | CRD schema definition |
| 1.1 | `~/Documents/Deploy/contextcore/crds/infrastructureguard.yaml` | Create | CRD for local cluster (copy) |
| 1.1 | `~/Documents/Deploy/contextcore/kustomization.yaml` | Modify | Add CRD resource |
| 1.2 | `observability/pvc-protection.yaml` | Modify | Restructure to CRD format |
| 1.2 | `scripts/drift-check.sh` | Modify | Parse new schema |
| 1.2 | `observability/pvc-guard/server.py` | Modify | Parse new schema |
| 1.3 | `observability/grafana/dashboards/contextcore/defense-in-depth.json` | Create | Dashboard JSON |
| 1.3 | Grafana ConfigMap or kustomization | Modify | Add dashboard to provisioning |
| 1.4 | `~/.claude/hooks/o11y-pvc-guard.sh` | **DONE** | Fix cross-project gaps + tilde expansion |
| 1.4 | `~/.claude/hooks/infra-guard-hook.sh` | **DONE** | jq parser, fail-closed, decision logging |
| 1.4 | `~/.claude/hooks/test-infra-guard.sh` | **DONE** | 27 integration tests |
| 1.5 | `~/Documents/Deploy/.claude/settings.local.json` | **DONE** | Narrow permissions |
| 1.5 | `~/Documents/dev/wayfinder/.claude/settings.local.json` | **DONE** | Narrow permissions |
| 2.1 | `observability/pvc-guard/server.py` | Modify | Add /metrics endpoint |
| 2.1 | `observability/pvc-guard/Dockerfile` | Modify | Add prometheus_client |
| 2.1 | `observability/pvc-guard/servicemonitor.yaml` | Create | Prometheus scrape config |
| 2.2 | `scripts/drift-check.sh` | Modify | Add --prometheus output |
| 2.3 | `observability/drift-check/cronjob.yaml` | Create | Continuous drift monitoring |
| 2.3 | `observability/drift-check/rbac.yaml` | Create | CronJob RBAC |
| 2.3 | `observability/kustomization.yaml` | Modify | Add drift-check resources |
| 2.4 | `~/.claude/hooks/infra-guard-hook.sh` | **PARTIAL** | Decision logging exists; Alloy integration remaining |
| 3.1 | `observability/grafana/dashboards/contextcore/defense-in-depth.json` | Modify | Replace static with live queries |
| 3.2 | `observability/mimir/rules/contextcore/defense-in-depth-alerts.yaml` | Create | Alert rules |
| 3.3 | `observability/mimir/rules/contextcore/defense-in-depth-recording.yaml` | Create | Recording rules |
| 4.1 | `scripts/guard-evaluate.sh` | Create | Posture evaluator |
| 4.2 | `observability/pvc-guard/webhook-config.yaml` | **DONE** | failurePolicy → Fail |
| 4.2 | `observability/pvc-guard/deployment.yaml` | Modify | Resources + replicas (remaining) |
| 4.2 | `observability/pvc-guard/pdb.yaml` | Create | PodDisruptionBudget (remaining) |
| 5.1 | `vendor/contextcore-spec/crds/projectcontext-v2.yaml` | Modify | Add guards reference |
| 5.2 | `src/contextcore/guard/guidance_merger.py` | Create | Constraint merging logic |
| 5.3 | `vendor/contextcore-spec/docs/semantic-conventions.md` | Modify | Add guard.* attributes |

---

## Estimated Effort per Phase

| Phase | Steps | Complexity | Key Risk | Status |
|-------|-------|------------|----------|--------|
| **Phase 1** | 5 steps | Medium | CRD schema design choices; dashboard JSON is tedious but mechanical | Steps 1.4, 1.5 **DONE**; 1.1-1.3 remaining |
| **Phase 2** | 4 steps | Low-Medium | Prometheus instrumentation is straightforward; CronJob RBAC needs care | Step 2.4 **PARTIAL** (logging done, Alloy remaining); 2.1-2.3 remaining |
| **Phase 3** | 3 steps | Low | Queries follow established patterns; alert thresholds need tuning | Not started |
| **Phase 4** | 2 steps | Medium | failurePolicy: Fail requires confidence in webhook reliability | Step 4.2 **PARTIAL** (policy done, PDB remaining); 4.1 remaining |
| **Phase 5** | 3 steps | Medium-High | CRD schema changes require careful migration; guidance merger is new code | Not started |

---

## Review Questions for Implementer

Before starting, consider these design choices:

1. **CRD location**: Should the InfrastructureGuard CRD live in `contextcore-spec` (the standard) or as a Deploy-only extension? If it's in the spec, it becomes part of the ContextCore standard that other projects can use.

2. **Guard scope**: Should guards be namespace-scoped (as proposed) or cluster-scoped? Namespace-scoped is simpler and aligns with how PVC protection works, but a cluster-scoped guard could protect cross-namespace invariants.

3. **Posture score formula**: The proposed formula gives blocking layers weight 1.0 and detecting layers weight 0.5. Should `failOpen: true` reduce the weight further? The current proposal applies a flat -0.1 penalty per failOpen layer.

4. **Dashboard builder**: Should the dashboard be built as raw JSON (consistent with most existing dashboards) or using the Jsonnet mixin (consistent with the wayfinder-mixin pattern)? Jsonnet is more maintainable for complex dashboards but adds a build step.

5. **Phase 1 vs Phase 2 boundary**: Is the static dashboard (Phase 1) useful enough to ship without telemetry (Phase 2)? If not, consider merging them.

6. **Permissions narrowing** (Step 1.5): **RESOLVED** — Implemented 2026-02-11. Friction is manageable; the bigger risk is Claude Code auto-re-adding broad permissions when users approve specific commands. Monitor `settings.local.json` after sessions.

7. **ContextCore version**: Should this target the existing v1alpha1 API group or wait for v2? The feature enhancement proposes v1alpha1 graduating with the rest of ContextCore.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **architecture**: 11 suggestions applied (R4-S1, R4-S7, R1-S3, R1-S5, R1-S7, R1-S9, R2-S1, R2-S20, R3-S4, R3-S12, R3-S19)
- **data**: 9 suggestions applied (R4-S2, R4-S8, R1-S8, R2-S2, R2-S9, R2-S16, R3-S5, R3-S11, R3-S18)
- **interfaces**: 9 suggestions applied (R4-S3, R4-S10, R2-S5, R2-S12, R3-S1, R3-S2, R3-S3, R3-S10, R3-S17)
- **ops**: 10 suggestions applied (R4-S4, R4-S11, R4-S17, R1-S1, R1-S2, R1-S6, R2-S7, R2-S15, R3-S8, R3-S15)
- **risks**: 8 suggestions applied (R4-S9, R4-S13, R4-S19, R2-S3, R2-S10, R2-S17, R3-S6, R3-S13)
- **security**: 7 suggestions applied (R4-S5, R4-S15, R1-S10, R2-S6, R2-S13, R3-S9, R3-S16)
- **validation**: 8 suggestions applied (R4-S6, R4-S14, R1-S4, R2-S4, R2-S11, R2-S18, R3-S7, R3-S14)

### Areas Needing Further Review

All areas have reached the substantially addressed threshold.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Add rollback strategy section to each phase documenting how to revert changes | claude-opus (claude-opus-4-6) | Critical for production safety - phases 1.5 and 4.2 are particularly high-risk with no documented recovery path | 2026-02-11 20:49:09 UTC |
| R1-S2 | Replace one-shot permission narrowing with staged rollout based on usage analysis | claude-opus (claude-opus-4-6) | The current approach acknowledges friction but provides no migration path - staged rollout reduces risk of breaking active agent workflows | 2026-02-11 20:49:09 UTC |
| R1-S3 | Reclassify Step 2.4 from Optional to Required and add dependency annotation | claude-opus (claude-opus-4-6) | Phase 3 dashboard explicitly depends on hook logs but this dependency isn't marked - will cause confusion when panels show no data | 2026-02-11 20:49:09 UTC |
| R1-S4 | Add automated test strategy covering CRD validation, drift-check format, dashboard JSON, and webhook decisions | claude-opus (claude-opus-4-6) | Manual validation commands are insufficient for a reusable ContextCore standard - automated tests prevent regression | 2026-02-11 20:49:09 UTC |
| R1-S5 | Add PromQL/LogQL fallback expressions so dashboard panels degrade gracefully | claude-opus (claude-opus-4-6) | Better UX to show static baseline than 'No data' when metrics are unavailable | 2026-02-11 20:49:09 UTC |
| R1-S6 | Add self-monitoring for the guard evaluator CronJob | claude-opus (claude-opus-4-6) | The evaluator computes critical posture scores but has no observability - silent failures leave stale protection data | 2026-02-11 20:49:09 UTC |
| R1-S7 | Add CRD conversion webhook plan for v1alpha1 to v1 graduation | claude-opus (claude-opus-4-6) | Version graduation is mentioned but migration mechanism is missing - existing resources will break without conversion | 2026-02-11 20:49:09 UTC |
| R1-S8 | Add migration strategy for existing ProjectContext v1 resources when adding spec.guards field | claude-opus (claude-opus-4-6) | Phase 5.1 modifies CRD schema but provides no migration path for existing resources | 2026-02-11 20:49:09 UTC |
| R1-S9 | Remove manual text format option and standardize on prometheus_client library | claude-opus (claude-opus-4-6) | Manual implementation is tech debt that will drift from Prometheus spec as metrics are added | 2026-02-11 20:49:09 UTC |
| R1-S10 | Specify namespace-scoped RBAC for drift-check CronJob rather than cluster-scoped | claude-opus (claude-opus-4-6) | Follows least-privilege principle for single-namespace use case while documenting expansion path | 2026-02-11 20:49:09 UTC |
| R2-S1 | Define clear boundaries between defense layers to prevent overlap | claude-4 (claude-opus-4-20250514) | Current taxonomy allows ambiguity which leads to incorrect layer classification and coverage gaps | 2026-02-11 20:49:09 UTC |
| R2-S2 | Add versioning strategy for InfrastructureGuard resources | claude-4 (claude-opus-4-20250514) | Guards will evolve over time - without versioning, updates break consumers and lose protection history | 2026-02-11 20:49:09 UTC |
| R2-S3 | Define failure recovery procedures for each protection layer | claude-4 (claude-opus-4-20250514) | failOpen behaviors are identified but concrete recovery runbooks are missing for operational incidents | 2026-02-11 20:49:09 UTC |
| R2-S4 | Establish production-readiness certification requirements for protection layers | claude-4 (claude-opus-4-20250514) | Not all blocking layers are equally reliable - certification criteria ensure consistent quality | 2026-02-11 20:49:09 UTC |
| R2-S5 | Specify standardized health check protocol for all layer types | claude-4 (claude-opus-4-20250514) | Incomplete health check specification leads to inconsistent implementation across layer types | 2026-02-11 20:49:09 UTC |
| R2-S6 | Add authentication requirements section for protection layers | claude-4 (claude-opus-4-20250514) | Several layers need Kubernetes credentials but credential management isn't addressed | 2026-02-11 20:49:09 UTC |
| R2-S7 | Define SLIs/SLOs for defense-in-depth system performance | claude-4 (claude-opus-4-20250514) | Protection posture needs measurable objectives to ensure system meets operational requirements | 2026-02-11 20:49:09 UTC |
| R2-S9 | Design state reconciliation policy for drift between spec and status | claude-4 (claude-opus-4-20250514) | Stale status after spec changes could misrepresent protection posture - reconciliation timing is critical | 2026-02-11 20:49:09 UTC |
| R2-S10 | Add circuit breaker pattern for blocking layers to prevent deployment halts | claude-4 (claude-opus-4-20250514) | Frequently failing blocking layers could stop all deployments - automatic degradation prevents outages | 2026-02-11 20:49:09 UTC |
| R2-S11 | Include negative test cases in validation approach | claude-4 (claude-opus-4-20250514) | Current validation only tests success paths - negative tests ensure protection actually blocks violations | 2026-02-11 20:49:09 UTC |
| R2-S12 | Standardize telemetry attribute naming across all layers | claude-4 (claude-opus-4-20250514) | Consistent naming enables correlation across layers for debugging and monitoring | 2026-02-11 20:49:09 UTC |
| R2-S13 | Document minimum privilege requirements for each layer type | claude-4 (claude-opus-4-20250514) | Different layers need different RBAC permissions - explicit documentation prevents over-privileging | 2026-02-11 20:49:09 UTC |
| R2-S15 | Design zero-downtime update procedures for guards | claude-4 (claude-opus-4-20250514) | Guard updates, especially webhook changes, could cause protection gaps during deployment | 2026-02-11 20:49:09 UTC |
| R2-S16 | Define retention policy for protection events in status | claude-4 (claude-opus-4-20250514) | Unbounded event growth in CRD status will cause performance issues | 2026-02-11 20:49:09 UTC |
| R2-S17 | Analyze and document correlated failure domains across layers | claude-4 (claude-opus-4-20250514) | Multiple layers sharing dependencies could fail together, reducing defense effectiveness | 2026-02-11 20:49:09 UTC |
| R2-S18 | Create guard template library for common protection patterns | claude-4 (claude-opus-4-20250514) | Reusable templates accelerate adoption and ensure best practices | 2026-02-11 20:49:09 UTC |
| R2-S20 | Define migration path from ad-hoc format to CRD format | claude-4 (claude-opus-4-20250514) | Existing pvc-protection.yaml uses different schema - backward compatibility is essential | 2026-02-11 20:49:09 UTC |
| R3-S1 | Add OpenAPI endpoint for guard status queries | claude-4 (claude-opus-4-20250514) | Essential for programmatic access to guard status without kubectl dependency, enables integration with monitoring tools and agents | 2026-02-11 21:38:17 UTC |
| R3-S2 | Define plugin interface for custom layer health checks | claude-4 (claude-opus-4-20250514) | Extensibility is crucial for organizations to add custom protection layers beyond the 12 built-in types without modifying core code | 2026-02-11 21:38:17 UTC |
| R3-S3 | Specify webhook → guard controller communication protocol | claude-4 (claude-opus-4-20250514) | Critical for Phase 4 controller to receive rich event data from webhook for accurate posture updates | 2026-02-11 21:38:17 UTC |
| R3-S4 | Define guard status update consistency model | claude-4 (claude-opus-4-20250514) | Multiple components updating the same status field will cause race conditions and inconsistent data without proper coordination | 2026-02-11 21:38:17 UTC |
| R3-S5 | Specify metrics cardinality limits | claude-4 (claude-opus-4-20250514) | Unbounded deployment labels in metrics can overwhelm Prometheus, cardinality limits are essential for production stability | 2026-02-11 21:38:17 UTC |
| R3-S6 | Add rollback procedure for CRD migration | claude-4 (claude-opus-4-20250514) | Critical safety mechanism for production - CRD format changes can break existing consumers and need tested rollback path | 2026-02-11 21:38:17 UTC |
| R3-S7 | Add integration tests for cross-project kubectl paths | claude-4 (claude-opus-4-20250514) | Step 1.4 fixes critical security gap but validation only shows unit testing - need end-to-end verification | 2026-02-11 21:38:17 UTC |
| R3-S8 | Define Phase 1→2 migration safety check | claude-4 (claude-opus-4-20250514) | Dashboard showing stale 'protected' status during migration could give false security confidence | 2026-02-11 21:38:17 UTC |
| R3-S9 | Specify webhook TLS certificate rotation | claude-4 (claude-opus-4-20250514) | Expired certificates would break protection entirely - cert management is critical for webhook availability | 2026-02-11 21:38:17 UTC |
| R3-S10 | Add CLI tool for guard validation | claude-4 (claude-opus-4-20250514) | Pre-apply validation prevents misconfigurations and improves operator experience | 2026-02-11 21:38:17 UTC |
| R3-S11 | Define time-series data retention policy | claude-4 (claude-opus-4-20250514) | Protection event history needed for security forensics and compliance auditing | 2026-02-11 21:38:17 UTC |
| R3-S12 | Clarify drift-check CronJob failure handling | claude-4 (claude-opus-4-20250514) | Silent failures in drift detection could leave gaps undetected - need explicit failure handling and alerting | 2026-02-11 21:38:17 UTC |
| R3-S13 | Add protection for guard resources themselves | claude-4 (claude-opus-4-20250514) | Guards protecting critical infrastructure must themselves be protected from deletion or tampering | 2026-02-11 21:38:17 UTC |
| R3-S14 | Add schema migration tests | claude-4 (claude-opus-4-20250514) | Phase 5 CRD changes could break existing resources - migration testing prevents production breakage | 2026-02-11 21:38:17 UTC |
| R3-S15 | Document Phase 4 evaluator debugging | claude-4 (claude-opus-4-20250514) | Complex posture score calculations need verbose debugging mode for troubleshooting | 2026-02-11 21:38:17 UTC |
| R3-S16 | Scope webhook ServiceAccount permissions | claude-4 (claude-opus-4-20250514) | Webhook should have minimal RBAC following principle of least privilege | 2026-02-11 21:38:17 UTC |
| R3-S17 | Define Prometheus scrape interval coordination | claude-4 (claude-opus-4-20250514) | Misaligned scrape intervals cause stale metrics and missed drift events | 2026-02-11 21:38:17 UTC |
| R3-S18 | Add guard resource naming convention | claude-4 (claude-opus-4-20250514) | Multiple guards per namespace need consistent naming to avoid conflicts | 2026-02-11 21:38:17 UTC |
| R3-S19 | Specify hook log rotation | claude-4 (claude-opus-4-20250514) | Unbounded log growth could fill disk and cause hook failures | 2026-02-11 21:38:17 UTC |
| R4-S1 | Add explicit migration strategy for existing pvc-guard implementations | claude-4 (claude-opus-4-20250514) | Critical gap - changing webhook/hook configuration without downtime planning could disable protection | 2026-02-11 21:50:01 UTC |
| R4-S2 | Define schema evolution strategy for InfrastructureGuard CRD | claude-4 (claude-opus-4-20250514) | CRD evolution is inevitable and breaking existing guards would be catastrophic - conversion webhooks are standard practice | 2026-02-11 21:50:01 UTC |
| R4-S3 | Specify exact consumer contract for drift-check.sh format changes | claude-4 (claude-opus-4-20250514) | YAML parsing in shell scripts is fragile - explicit parsing logic prevents subtle breakage | 2026-02-11 21:50:01 UTC |
| R4-S4 | Add pre-Phase 1 backup and rollback procedures | claude-4 (claude-opus-4-20250514) | Modifying critical protection infrastructure requires escape plan - standard ops practice | 2026-02-11 21:50:01 UTC |
| R4-S5 | Define security context and RBAC for drift-check CronJob | claude-4 (claude-opus-4-20250514) | CronJob needs minimal privileges - explicit RBAC prevents over-privileged components | 2026-02-11 21:50:01 UTC |
| R4-S6 | Add end-to-end protection verification suite | claude-4 (claude-opus-4-20250514) | Defense-in-depth requires holistic testing - individual layer tests insufficient | 2026-02-11 21:50:01 UTC |
| R4-S7 | Clarify controller deployment model for Phase 4 | claude-4 (claude-opus-4-20250514) | Three options presented without recommendation - implementer needs guidance based on ContextCore patterns | 2026-02-11 21:50:01 UTC |
| R4-S8 | Specify metric cardinality limits and retention | claude-4 (claude-opus-4-20250514) | Unbounded cardinality can overwhelm Mimir - must plan for worst case | 2026-02-11 21:50:01 UTC |
| R4-S9 | Address circular dependency risk in Phase 5 | claude-4 (claude-opus-4-20250514) | Guard→ProjectContext→agent→guard cycle could cause infinite reconciliation - critical to prevent | 2026-02-11 21:50:01 UTC |
| R4-S10 | Define structured logging format for all protection events | claude-4 (claude-opus-4-20250514) | Multiple components need correlated logs - JSON schema enables proper observability | 2026-02-11 21:50:01 UTC |
| R4-S11 | Add gradual rollout strategy for permissions narrowing | claude-4 (claude-opus-4-20250514) | Step 1.5 could break legitimate workflows - phased rollout with monitoring is essential | 2026-02-11 21:50:01 UTC |
| R4-S13 | Add protection for the protection system | claude-4 (claude-opus-4-20250514) | Meta-protection prevents accidental self-destruction - guards must protect themselves | 2026-02-11 21:50:01 UTC |
| R4-S14 | Define performance benchmarks for protection layers | claude-4 (claude-opus-4-20250514) | No performance requirements specified - latency impacts user experience and must be bounded | 2026-02-11 21:50:01 UTC |
| R4-S15 | Specify mTLS requirements for webhook | claude-4 (claude-opus-4-20250514) | Webhook handles security-critical decisions - TLS configuration must be explicit and secure | 2026-02-11 21:50:01 UTC |
| R4-S17 | Define operational runbook for each failure mode | claude-4 (claude-opus-4-20250514) | Feature requires runbooks but plan doesn't create them - ops teams need documented procedures | 2026-02-11 21:50:01 UTC |
| R4-S19 | Address state consistency during Phase 1→2 transition | claude-4 (claude-opus-4-20250514) | Dashboard showing stale data without indication misleads operators - freshness indicator prevents confusion | 2026-02-11 21:50:01 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-S8 | Clarify relationship between InfrastructureGuard and NetworkPolicy/RBAC | claude-4 (claude-opus-4-20250514) | While useful context, this belongs in the feature enhancement document rather than the implementation plan | 2026-02-11 20:49:09 UTC |
| R2-S14 | Add support for external policy engines like OPA | claude-4 (claude-opus-4-20250514) | While valuable for future extensibility, this adds significant complexity beyond the current scope | 2026-02-11 20:49:09 UTC |
| R2-S19 | Add CLI for guard management beyond kubectl | claude-4 (claude-opus-4-20250514) | While improving UX, a custom CLI is premature before core functionality is proven | 2026-02-11 20:49:09 UTC |
| R4-S12 | Document decision on guard resource naming convention | claude-4 (claude-opus-4-20250514) | Low priority - naming conventions can be established organically as patterns emerge | 2026-02-11 21:50:01 UTC |
| R4-S16 | Add OpenAPI spec for webhook metrics endpoint | claude-4 (claude-opus-4-20250514) | Over-engineering for a simple metrics endpoint - Prometheus text format is self-documenting | 2026-02-11 21:50:01 UTC |
| R4-S18 | Specify time synchronization requirements | claude-4 (claude-opus-4-20250514) | Kubernetes nodes already require time sync - redundant to specify again | 2026-02-11 21:50:01 UTC |
| R4-S20 | Clarify expansion pack potential for guard templates | claude-4 (claude-opus-4-20250514) | Premature optimization - expansion pack pattern can be explored after core implementation succeeds | 2026-02-11 21:50:01 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1
- **Reviewer**: claude-opus (claude-opus-4-6)
- **Date**: 2026-02-11 00:00:00 UTC
- **Scope**: Review implementation plan for defense-in-depth CRD, focusing on rollback safety, phase dependencies, testing gaps, and CRD lifecycle.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | ops | high | Add a rollback strategy section to each phase documenting how to revert changes if something breaks mid-phase | Phases 1.5 (permission narrowing) and 4.2 (failurePolicy: Fail) are high-disruption changes with no documented undo path. A failed mid-phase change could leave agents blocked or the webhook rejecting all applies. | Each Phase section, as a new "Rollback" subsection after "Validation" | Dry-run each rollback procedure in a Kind cluster before shipping the phase |
| R1-S2 | ops | high | Replace the one-shot permission narrowing in Step 1.5 with a staged rollout: observe current usage patterns → identify needed allows → narrow → monitor for 1 week → finalize | The plan acknowledges "this will cause friction" but proposes no migration strategy. One-shot cutover risks breaking agents mid-task with no visibility into which commands are actually used. | Step 1.5, replace the current "Risk" paragraph with a phased migration plan | Run `grep -r 'Bash(kubectl' ~/.claude/` across all projects to catalog current auto-approved patterns before narrowing |
| R1-S3 | architecture | high | Reclassify Step 2.4 (hook instrumentation) from "Optional" to "Required for Phase 3 dashboard" and add a dependency annotation | Phase 3 dashboard Row 5 expects `{app=~"o11y-pvc-guard"}` Loki log data from hook structured logging. If 2.4 is skipped, those panels render empty with no fallback. | Step 2.4 title and Phase 3.1 panel plan table | Verify dashboard JSON references match available log labels after Phase 2 completes |
| R1-S4 | validation | high | Add an automated test strategy section covering: CRD schema validation tests, drift-check output format tests, dashboard JSON linting, and webhook decision integration tests | Every validation section is manual `kubectl` commands. For a plan aimed at becoming a reusable ContextCore standard, the absence of automated tests means regressions will be caught only by manual verification. | New section "## Automated Test Strategy" after "## Estimated Effort per Phase" | CI pipeline runs schema validation and drift-check format tests on every PR touching guard-related files |
| R1-S5 | architecture | medium | Add PromQL/LogQL `or()` fallback expressions in Phase 3.1 so dashboard panels gracefully degrade to static values when Phase 2 metrics are unavailable | Phase 3.1 replaces static panels with live queries, but if Phase 2 instrumentation is incomplete or metrics pipelines lag, panels show "No data" instead of the static baseline. This is worse than Phase 1's static dashboard. | Phase 3.1 panel query specifications | Deploy Phase 3 dashboard in a cluster with Phase 2 metrics disabled; verify all panels show fallback values |
| R1-S6 | ops | medium | Add a self-monitoring requirement for the guard evaluator CronJob in Phase 4.1: a `contextcore_guard_evaluator_last_success_timestamp` gauge and a `ContextCoreGuardEvaluatorStale` alert | The plan instruments webhook, drift-check, and hooks, but the CronJob that computes posture scores has no monitoring. If it fails silently, the protection dashboard shows stale data with no alert. | Phase 4.1, add to the evaluator's metric emissions and Phase 3.2 alert rules | Pause the CronJob; verify alert fires within the configured threshold |
| R1-S7 | architecture | medium | Add a CRD conversion webhook plan for v1alpha1 → v1 graduation, or document the breaking-change upgrade path if conversion webhooks are not used | v1alpha1 graduation to v1 is mentioned in the feature enhancement doc but the implementation plan has no migration mechanism. Existing InfrastructureGuard resources will fail validation after CRD version upgrade without a conversion webhook or explicit migration script. | New subsection under Phase 5 or as a new Phase 6 | Apply v1alpha1 guard resource, upgrade CRD to v1, verify resource is still readable via `kubectl get guard` |
| R1-S8 | data | medium | Add an explicit migration strategy for existing ProjectContext v1 resources when adding the `spec.guards` reference field in Phase 5.1 | The effort table notes "CRD schema changes require careful migration" but the plan contains no migration steps. If ProjectContext v1 → v2 is required, existing resources need either a conversion webhook or a manual migration script. | Phase 5.1, new "Migration" subsection | Apply existing ProjectContext v1 resources after CRD update; verify they still validate and the new `spec.guards` field is optional |
| R1-S9 | architecture | low | Remove the "implement text format manually" option from Step 2.1 and standardize on `prometheus_client` library | The plan offers manual Prometheus text format as a viable option ("simple enough for 3 metrics"), but this is tech debt from day one. Future metric additions in Phases 3-4 are inevitable, and hand-rolled text format will drift from the spec. | Step 2.1 "Implementation approach" paragraph | Verify `/metrics` endpoint output passes `promtool check metrics` |
| R1-S10 | security | low | Specify that the drift-check CronJob RBAC in Step 2.3 should be namespace-scoped (Role + RoleBinding) rather than cluster-scoped (ClusterRole + ClusterRoleBinding) | The plan says "ServiceAccount with get/list on deployments + PVCs" without specifying scope. For the stated use case (single-namespace guard), namespace-scoped RBAC follows least-privilege. The generalizability goal should be addressed by documenting how to expand scope for multi-namespace guards. | Step 2.3 "Files to create" section, expand the rbac.yaml description | `kubectl auth can-i --as=system:serviceaccount:observability:drift-check get deployments -n observability` returns yes; same command without `-n` returns no |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — first review round)

#### Review Round R2

**Reviewer**: claude-4 (claude-opus-4-20250514)  
**Date**: 2026-02-11 20:47:08 UTC  
**Scope**: Requirements traceability and architecture review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | Define clear boundaries between defense layers to prevent overlap and confusion | The current layer taxonomy allows ambiguity (e.g., drift-monitor vs continuous-monitor, cli-hook vs permission-scope). Clear separation ensures each layer has a single responsibility. | Add "Layer Boundaries" section after taxonomy defining mutual exclusivity rules | Document review with examples showing which layer type to use for specific scenarios |
| R2-S2 | Data | critical | Add versioning strategy for InfrastructureGuard resources | As protection requirements evolve, guards will need updates. Without versioning, changes could break existing consumers or lose historical protection posture data. | Add spec.version field and status.appliedVersion with migration semantics | Test guard updates with version transitions, ensure status preserves history |
| R2-S3 | Risks | critical | Define failure recovery procedures for each protection layer | The plan identifies failOpen behaviors but lacks concrete recovery procedures when layers fail. Teams need runbooks for "webhook is down" or "drift detection stopped working" scenarios. | Add spec.layers[].recovery section with step-by-step procedures | Chaos testing: deliberately fail each layer and verify recovery procedures work |
| R2-S4 | Validation | high | Establish protection layer certification requirements | Not all "blocking" layers are equally reliable. Define what makes a layer production-ready (uptime SLO, latency requirements, failure handling). | Add "Layer Certification" section with reliability criteria and testing requirements | Performance and reliability testing of each layer type under load |
| R2-S5 | Interfaces | high | Specify the protocol for layer health checks | Different layer types need different health check mechanisms. The spec mentions "file-exists" and "k8s-resource" but lacks a complete protocol. | Expand spec.layers[].healthCheck with standardized check types and expected responses | Unit tests for each health check type with success/failure scenarios |
| R2-S6 | Security | critical | Add authentication requirements for protection layers | Several layers (webhook, drift-monitor) need credentials to query Kubernetes. The plan doesn't address credential management or rotation. | Add spec.layers[].authentication section for credential references | Security audit of credential usage, rotation testing |
| R2-S7 | Ops | high | Define SLIs/SLOs for the defense-in-depth system | "Protection posture" needs measurable objectives. What's acceptable latency for drift detection? What's the required uptime for blocking layers? | Add "Operational Requirements" section with specific SLIs and SLOs per layer type | Continuous monitoring against SLOs with alerting on violations |
| R2-S8 | Architecture | medium | Clarify the relationship between InfrastructureGuard and NetworkPolicy/RBAC | The feature could overlap with existing Kubernetes security primitives. Make explicit when to use InfrastructureGuard vs native K8s resources. | Add "Relationship to K8s Security" section with decision matrix | Documentation review with examples of each approach |
| R2-S9 | Data | high | Design state reconciliation for drift between spec and status | When the guard spec changes, status may be stale. Define how quickly status must reflect spec changes and what happens during transition. | Add spec.reconciliationPolicy with timing and consistency guarantees | Integration tests modifying spec and measuring status convergence time |
| R2-S10 | Risks | high | Add circuit breaker pattern for blocking layers | If a blocking layer starts failing frequently, it could halt all deployments. Need automatic degradation to advisory mode after threshold. | Add spec.layers[].circuitBreaker with failure threshold and backoff policy | Fault injection testing to verify circuit breaker triggers appropriately |
| R2-S11 | Validation | medium | Include negative test cases in validation approach | Current validation focuses on "should work" cases. Need explicit "should fail" cases (e.g., webhook should reject bad YAML). | Add "Negative Testing" subsection to each phase's validation | Test suite with deliberate protection violations |
| R2-S12 | Interfaces | medium | Standardize telemetry attribute naming across all layers | Different layers emit different metric names. Need consistent naming for correlation (e.g., all use guard= label). | Add "Telemetry Standards" section enforcing naming conventions | Metric validation script checking all emitted metrics follow conventions |
| R2-S13 | Security | high | Define privilege requirements for each layer type | Some layers need cluster-admin (webhook), others need read-only (drift-monitor). Document minimum required privileges. | Add spec.layers[].requiredPrivileges with RBAC rules | RBAC testing with minimal permissions per layer |
| R2-S14 | Architecture | medium | Add support for external policy engines | The current design embeds policy logic in each layer. Consider integration points for OPA/Gatekeeper for complex policies. | Add spec.layers[].policyEngine for external policy references | Integration tests with OPA evaluating guard policies |
| R2-S15 | Ops | critical | Design for zero-downtime guard updates | Updating a guard (especially webhook changes) could cause protection gaps. Need blue-green or rolling update strategy. | Add "Guard Lifecycle Management" section with update procedures | Update testing with continuous traffic to verify no protection gaps |
| R2-S16 | Data | medium | Define retention policy for protection events | RecentEvents could grow unbounded. Need age or count-based eviction policy. | Add spec.eventRetention with max count and max age | Load testing with high event volume to verify eviction works |
| R2-S17 | Risks | medium | Add protection against simultaneous layer failures | Multiple layers could fail together (e.g., webhook and drift detection both need K8s API access). | Add failure domain analysis to coverage matrix showing correlated failures | Failure correlation testing with shared dependencies |
| R2-S18 | Validation | high | Create guard template library | Teams will create similar guards. Provide tested templates for common patterns (PVC protection, RBAC protection, etc.). | Add examples/ directory with parameterized guard templates | Template testing across different scenarios |
| R2-S19 | Interfaces | low | Add CLI for guard management | kubectl explain is good for discovery but a contextcore guard command would improve UX for evaluation and debugging. | Design CLI commands: validate, evaluate, coverage-report | CLI integration tests with mock guards |
| R2-S20 | Architecture | medium | Define clear migration path from ad-hoc to CRD | Existing pvc-protection.yaml uses different schema. Need backward compatibility or migration tools. | Add "Migration Guide" appendix with step-by-step conversion | Migration testing from legacy format to CRD format |

#### Review Round R3

**Reviewer**: claude-4 (claude-opus-4-20250514)
**Date**: 2026-02-11 21:35:45 UTC
**Scope**: Requirements traceability and architecture review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|----|------|----------|------------|-----------|-------------------|---------------------|
| R3-S1 | Interfaces | critical | Add OpenAPI endpoint for guard status queries | The plan relies on reading guard status from K8s resources (Step 1.3, 3.1), but agents need a programmatic interface to query protection posture without kubectl. An HTTP API exposing guard status enables tool integration and agent queries. | Phase 2.5: Add `/api/v1/guards/{namespace}/{name}/status` endpoint to webhook server or new API service | Test API returns guard status JSON; verify agents can query via HTTP tools |
| R3-S2 | Interfaces | high | Define plugin interface for custom layer health checks | Step 4.1 mentions evaluating "each layer's health check" but doesn't specify how custom health check types are implemented. A plugin interface allows adding new layer types without modifying core evaluator. | Phase 4.1: Define HealthCheckPlugin interface with check(config) method returning healthy/unhealthy/degraded | Unit test plugin loading; integration test custom health check execution |
| R3-S3 | Interfaces | high | Specify webhook → guard controller communication protocol | Phase 2.1 instruments webhook with metrics, but Phase 4 controller needs richer event data. Define event schema for webhook→controller communication (e.g., structured logs or event API). | Phase 2.1: Add event emission to webhook; Phase 4.1: Controller consumes events for posture updates | Mock event flow; verify controller updates guard status based on webhook events |
| R3-S4 | Architecture | critical | Define guard status update consistency model | Multiple components update guard status (drift-check CronJob, guard evaluator, webhook). Without coordination, status updates may conflict or produce inconsistent posture scores. | Phase 4.1: Define status update protocol using resourceVersion/generation checks and partial status updates | Concurrent update test: run drift-check + evaluator simultaneously, verify no lost updates |
| R3-S5 | Data | high | Specify metrics cardinality limits | Webhook metrics include deployment label which could explode cardinality if many deployments exist. Define cardinality budget and implement limits. | Phase 2.1: Document max 10 deployments per guard; implement metric dropping if exceeded | Load test webhook with 50+ deployments; verify metrics don't overwhelm Prometheus |
| R3-S6 | Risks | critical | Add rollback procedure for CRD migration | Step 1.2 migrates pvc-protection.yaml format but doesn't specify rollback if new format breaks consumers. Critical for production safety. | Phase 1.2: Add rollback section with commands to restore old format and restart consumers | Test rollback procedure: apply new format, simulate failure, execute rollback, verify recovery |
| R3-S7 | Validation | high | Add integration tests for cross-project kubectl paths | Step 1.4 adds hook rules for cross-project paths but validation only shows direct hook testing. Need end-to-end tests from agent sessions. | Phase 1.4: Add integration test simulating wayfinder agent applying k8s/observability/ | Mock agent session test: verify hook blocks cross-project apply attempts |
| R3-S8 | Ops | critical | Define Phase 1→2 migration safety check | Phase 1 static dashboard + Phase 2 telemetry could have period where dashboard shows stale data. Define safety check to prevent misleading "protected" status. | Phase 2 start: Add migration mode indicator to dashboard showing "Telemetry being enabled" | Verify dashboard shows clear migration status during Phase 1→2 transition |
| R3-S9 | Security | high | Specify webhook TLS certificate rotation | Phase 2.1 adds HTTPS endpoint but doesn't specify cert management. Expired certs would break protection. | Phase 2.1: Document cert-manager integration or manual rotation procedure with 30-day expiry | Test cert rotation: expire cert manually, execute rotation, verify webhook remains accessible |
| R3-S10 | Interfaces | medium | Add CLI tool for guard validation | Operators need to validate guard YAML before applying. A CLI tool that checks schema + evaluates health checks would prevent misconfigurations. | Phase 1.1: Create `contextcore-guard validate <file>` command in scripts/ | Test CLI validates good/bad guard YAML; verify error messages are actionable |
| R3-S11 | Data | medium | Define time-series data retention policy | Phases 2-3 add metrics/recording rules but don't specify retention. Protection event history needed for forensics. | Phase 3.3: Document 90-day retention for guard metrics, 1-year for protection events | Verify Mimir retention config; test old metrics are queryable after retention period |
| R3-S12 | Architecture | medium | Clarify drift-check CronJob failure handling | Phase 2.3 creates CronJob but doesn't specify behavior on failure (e.g., script error, RBAC denied). | Phase 2.3: Add `failurePolicy` to CronJob spec, emit failure metric, alert on consecutive failures | Test CronJob with broken RBAC; verify failure metric emitted and alert fires |
| R3-S13 | Risks | medium | Add protection for guard resources themselves | Guards protect deployments but what protects the guard CRD/instances from deletion? Meta-protection needed. | Phase 1.1: Add RBAC rules preventing guard deletion; Phase 4: Add self-protection guard | Test: attempt to delete guard resource as various users; verify protection blocks deletion |
| R3-S14 | Validation | medium | Add schema migration tests | Phase 5.1 modifies ProjectContext CRD but doesn't test existing resources still validate after schema change. | Phase 5.1: Add migration test validating all existing ProjectContexts against new schema | Apply new CRD schema to cluster with existing ProjectContexts; verify no validation errors |
| R3-S15 | Ops | medium | Document Phase 4 evaluator debugging | When posture score is wrong, operators need to debug why. Evaluator needs verbose logging mode. | Phase 4.1: Add --debug flag to evaluator with detailed score calculation logs | Test debug mode shows each vector×layer evaluation and score contribution |
| R3-S16 | Security | medium | Scope webhook ServiceAccount permissions | Phase 2.1 mentions webhook needs to "get InfrastructureGuard resources" but doesn't specify minimal RBAC. | Phase 2.1: Create webhook ServiceAccount with get/list on InfrastructureGuards only | Test webhook with minimal RBAC; verify it can read guards but not modify them |
| R3-S17 | Interfaces | low | Define Prometheus scrape interval coordination | Drift-check runs every 5min but Prometheus scrape interval undefined. Misalignment causes stale metrics. | Phase 2.3: Document Prometheus scrape must be ≤2min to catch all drift-check runs | Verify Prometheus scrapes webhook/drift-check endpoints at correct interval |
| R3-S18 | Data | low | Add guard resource naming convention | Multiple guards per namespace possible but examples only show one. Define naming convention for multiple guards. | Phase 1.1: Document convention: `<protected-resource>-<protection-type>` (e.g., pvc-protection, rbac-protection) | Validate multiple guards in same namespace don't conflict; test name uniqueness |
| R3-S19 | Architecture | low | Specify hook log rotation | Phase 2.4 appends to ~/.claude/logs/pvc-guard.jsonl but unbounded growth could fill disk. | Phase 2.4: Add log rotation via logrotate config or size check in hook | Test hook with 10K commands; verify log file rotates at size limit |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
|-----|------------|----------|------|
| **InfrastructureGuard CRD** (spec + status schemas) | Phase 1.1, 1.2 | Full | Schema definition and migration covered |
| **Protection Layer Taxonomy** | Implicitly throughout | Partial | No explicit step documents the taxonomy or validates layer types against it |
| **Defense-in-Depth Dashboard** | Phase 1.3, 3.1 | Full | Static then dynamic dashboard with all specified panels |
| **Telemetry Integration** (OTel attributes, metrics) | Phase 2.1, 2.2, 2.3, 2.4 | Full | All components instrumented with specified metrics |
| **Agent Guidance Derivation** | Phase 5.1, 5.2 | Full | Guards flow into ProjectContext as specified |
| **Rollback & Recovery** (operational requirement) | Missing | Missing | No phase includes rollback procedures or recovery runbooks |
| **Production-Readiness Certification** | Partial in 4.2 | Partial | Only webhook reliability addressed, not other blocking layers |
| **SLIs/SLOs** | Missing | Missing | No phase implements SLO monitoring or measurement |
| **Zero-Downtime Updates** | Partial in 4.2 | Partial | Only webhook update strategy mentioned, not CRD or evaluator |
| **Circuit Breaker** | Missing | Missing | No implementation of automatic degradation on repeated failures |
| **Version Graduation** | Phase 1.1 mentions v1alpha1 | Partial | No conversion webhook or migration timeline planning |
| **Security & RBAC** | Phase 2.3, implicit elsewhere | Partial | RBAC for CronJob covered, but not for webhook, evaluator, or guard protection |
| **Automated Testing** | Validation commands throughout | Partial | Manual kubectl commands provided, but no automated test suite |
| **Health Check Protocol** | Mentioned in 4.1 | Partial | Evaluator consumes health checks but protocol not explicitly defined |
| **Failure Domain Analysis** | Missing | Missing | No phase analyzes correlated failures or documents them |
| **Event Retention Policy** | Missing | Missing | Status.recentEvents pruning not implemented |
| **Guard Template Library** | Missing | Missing | No phase creates reusable guard templates |

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
- **Date**: 2026-02-11 21:47:16 UTC
- **Scope**: Requirements traceability and architecture review — dual-document gap-hunting mode

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Architecture | high | Add explicit migration strategy for existing pvc-guard implementations | The plan restructures pvc-protection.yaml (Step 1.2) but doesn't detail how to handle running webhook/hook instances during migration. With failOpen:true, a misconfigured migration could silently disable protection. | Add new subsection "Step 1.2a: Zero-Downtime Migration Sequence" detailing: pre-migration validation, parallel running strategy, cutover verification | Test migration on a copy of production guard config; verify no protection gap during cutover |
| R4-S2 | Data | high | Define schema evolution strategy for InfrastructureGuard CRD | The CRD will evolve (v1alpha1→v1), but no conversion webhook or storage migration strategy is specified. Without this, existing guards break on CRD updates. | Phase 1, Step 1.1 add "CRD Evolution Strategy" section with conversion webhook approach and storage version migration plan | Deploy v1alpha1, create guards, upgrade to v1 with conversion webhook, verify guards still readable |
| R4-S3 | Interfaces | high | Specify exact consumer contract for drift-check.sh format changes | Step 1.2 updates drift-check.sh to parse spec.invariants[] but doesn't show the exact parsing logic or error handling for malformed specs. Scripts parsing YAML are fragile. | Step 1.2 add code snippet showing jq/yq query for invariants extraction with error handling | Unit test drift-check.sh with valid/invalid guard specs; verify graceful failure |
| R4-S4 | Ops | critical | Add pre-Phase 1 backup and rollback procedures | Phase 1 modifies critical protection infrastructure (webhook, hooks, permissions). No rollback plan if these changes break protection. | Add "Phase 0: Pre-Implementation Backup" with steps to snapshot current protection state and test rollback | Execute rollback procedure in test environment; verify protection restored |
| R4-S5 | Security | high | Define security context and RBAC for drift-check CronJob | Phase 2.3 creates a CronJob with get/list permissions but doesn't specify security context, service account privileges, or namespace isolation. | Phase 2.3 add detailed RBAC manifest and Pod security context (runAsNonRoot, readOnlyRootFilesystem) | Run CronJob with minimal privileges; verify it can read guards/deployments but nothing else |
| R4-S6 | Validation | medium | Add end-to-end protection verification suite | Each phase has isolated validation but no comprehensive test that verifies the entire defense-in-depth system works together. | Add "Phase 6: End-to-End Validation" with test scenarios covering all layers and attack vectors | Run test suite simulating each attack vector; verify appropriate layer blocks it |
| R4-S7 | Architecture | medium | Clarify controller deployment model for Phase 4 | Phase 4 mentions three options (CronJob, controller, operator integration) but doesn't recommend which fits the ContextCore architecture. | Phase 4.1 add decision matrix comparing options with recommendation based on ContextCore patterns | Deploy recommended option; measure resource usage and responsiveness |
| R4-S8 | Data | medium | Specify metric cardinality limits and retention | Phase 2 adds many labeled metrics but doesn't address cardinality explosion (guard×layer×invariant×resource). | Phase 2 add "Metric Cardinality Management" section with label value limits and aggregation rules | Calculate worst-case cardinality; verify Mimir handles it |
| R4-S9 | Risks | high | Address circular dependency risk in Phase 5 | Phase 5 makes guards affect ProjectContext which affects agents which could modify guards. This creates potential circular dependencies or infinite reconciliation loops. | Phase 5 add "Circular Dependency Prevention" section with cycle detection and limits | Create guard→ProjectContext→guard cycle; verify reconciliation terminates |
| R4-S10 | Interfaces | medium | Define structured logging format for all protection events | Multiple components emit logs (webhook, hook, drift-check) but no unified schema specified. Makes correlation difficult. | Phase 2 add "Unified Event Schema" defining JSON structure all components must follow | Verify all components emit compliant logs; test Loki correlation queries |
| R4-S11 | Ops | high | Add gradual rollout strategy for permissions narrowing | Step 1.5 narrows permissions drastically which could block legitimate workflows. No gradual rollout or monitoring specified. | Step 1.5 add phased rollout: dry-run mode → audit mode → enforce mode with metrics at each stage | Monitor permission denial rate; rollback if >5% legitimate commands blocked |
| R4-S12 | Architecture | low | Document decision on guard resource naming convention | Guards need consistent naming (observability-pvc-protection) but no naming convention documented. Will lead to inconsistency. | Phase 1.1 add "Guard Naming Convention" section with pattern and examples | Validate guard names match convention in webhook admission |
| R4-S13 | Risks | high | Add protection for the protection system | The guard system itself (webhook, CronJob, dashboards) could be accidentally deleted/modified. No meta-protection specified. | Add "Phase 1.6: Bootstrap Protection" creating guards for the guard infrastructure itself | Attempt to delete pvc-guard deployment; verify protection blocks it |
| R4-S14 | Validation | medium | Define performance benchmarks for protection layers | No performance requirements specified. Webhook latency, hook execution time, drift-check duration all affect user experience. | Add performance requirements to each phase: webhook <100ms p99, hook <50ms, drift-check <30s | Benchmark each component under load; verify meets SLOs |
| R4-S15 | Security | medium | Specify mTLS requirements for webhook | Phase 2.1 adds HTTPS endpoint but doesn't specify TLS version, cipher suites, or certificate rotation strategy. | Phase 2.1 add "TLS Configuration" with cert-manager integration and rotation policy | Test with TLS 1.2 minimum; verify cert rotation doesn't cause downtime |
| R4-S16 | Interfaces | low | Add OpenAPI spec for webhook metrics endpoint | Phase 2.1 adds /metrics but no formal API specification. Makes client integration harder. | Phase 2.1 add OpenAPI 3.0 spec for metrics endpoint | Generate client from spec; verify metrics parse correctly |
| R4-S17 | Ops | medium | Define operational runbook for each failure mode | Feature doc requires recovery runbooks but implementation plan doesn't create them. | Add "Phase 1.7: Runbook Creation" with templates for each component failure | Simulate each failure mode; verify runbook steps recover successfully |
| R4-S18 | Data | low | Specify time synchronization requirements | Correlation across webhook, hook, and drift-check requires synchronized clocks but no NTP requirement specified. | Add time sync requirement to Phase 2 prerequisites | Verify all components use same time source; test with clock skew |
| R4-S19 | Risks | medium | Address state consistency during Phase 1→2 transition | Phase 1 has static dashboard, Phase 2 adds metrics. During transition, dashboard shows stale data with no indication. | Phase 1.3 add "Data Freshness Indicator" panel showing last update time | Deploy Phase 1, verify freshness indicator shows data is static |
| R4-S20 | Architecture | low | Clarify expansion pack potential for guard templates | Feature doc mentions guard template library but implementation doesn't structure it as a reusable expansion pack. | Add note exploring guard templates as ContextCore expansion pack pattern | Create sample expansion pack structure for guard templates |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-F4: The JSONPath syntax ambiguity is critical — without specifying exact syntax (kubectl vs jq vs yq), implementations will diverge
- R3-F5: The troubleshooting guide is essential given the multi-layer complexity and failure modes across different technologies

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| **InfrastructureGuard CRD** (spec schema) | Phase 1, Step 1.1 | Full | CRD location still an open question; version migration strategy missing |
| **Protection Layer taxonomy** | Referenced in Step 1.2 but not implemented | Partial | No explicit enumeration of 12 layer types in implementation |
| **Defense-in-Depth Dashboard** | Phase 1 Step 1.3, Phase 3 Step 3.1 | Full | Coverage matrix implementation details sparse |
| **Telemetry Integration** | Phase 2 (all steps) | Full | Semantic conventions implementation not shown |
| **Agent Guidance Derivation** | Phase 5 (all steps) | Full | Circular dependency risk not addressed |
| **Operational Requirements - Rollback** | Not addressed | Missing | No rollback procedures for any phase |
| **Operational Requirements - Production Readiness** | Partially in Phase 4.2 | Partial | Missing layer certification criteria implementation |
| **Operational Requirements - SLIs/SLOs** | Not addressed | Missing | No implementation of SLI measurement or alerts |
| **Zero-Downtime Updates** | Mentioned for webhook but not comprehensive | Partial | Missing details for CRD updates and hook updates |
| **Circuit Breaker for Blocking Layers** | Not addressed | Missing | Critical gap — no automatic degradation specified |
| **Version Graduation** | Mentioned in Step 1.1 | Partial | Conversion webhook implementation missing |
| **Migration from Ad-Hoc Format** | Phase 1 Step 1.2 | Full | Options provided but no validation of migrated resources |
| **Security & RBAC Requirements** | Phase 2.3 mentions RBAC | Partial | Minimum privilege definitions incomplete |
| **Testing Requirements - Automated** | Validation sections per phase | Partial | No unified test suite; mostly manual validation |
| **Testing Requirements - Negative** | Not addressed | Missing | No negative test scenarios implemented |
| **Health Check Protocol** | Referenced but not implemented | Missing | Standardized protocol not codified |
| **Event Retention Policy** | Not addressed | Missing | recentEvents array unbounded growth risk |
| **Guard Template Library** | Mentioned in review questions | Missing | No template creation or structure defined |

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Ops | critical | Add circuit breaker implementation requirement | Feature requires automatic degradation from blocking→detecting but provides no implementation guidance. This is critical for production stability. | Add new section "Circuit Breaker Implementation" with state machine, thresholds, and restoration logic | Test circuit breaker with failing webhook; verify automatic degradation and restoration |
| R4-F2 | Validation | high | Expand negative test cases with specific scenarios | Feature mentions negative testing need but provides no concrete test cases. Hard to verify protection works without these. | Add "Negative Test Scenarios" section with 10+ specific test cases including commands and expected blocks | Execute each negative test; verify protection layer blocks correctly |
| R4-F3 | Architecture | medium | Clarify guard controller vs evaluator distinction | Feature uses "controller" and "evaluator" interchangeably but these have different implications in Kubernetes. | Add terminology section distinguishing evaluator (stateless) from controller (stateful reconciliation) | Document which pattern ContextCore uses |
| R4-F4 | Security | medium | Add Pod Security Standards alignment | Feature requires security hardening but doesn't reference Kubernetes Pod Security Standards (restricted/baseline). | Add section mapping InfrastructureGuard security requirements to Pod Security Standards | Deploy guards under restricted PSS; verify functionality |
| R4-F5 | Data | medium | Specify guard status size limits | Feature allows unlimited events/layers in status. Large status objects can break etcd. | Add status size limits: max 100 events, max 50 layers, max 20KB total status | Test with maximum sizes; verify Kubernetes accepts |
