# Phase 3 Handoff: What You Need to Know

Session date: 2026-02-03. This document captures context from the Phase 3
implementation session for the agent picking up remaining work.

---

## What Was Done Today

### Wayfinder (4 commits)

| Commit | Summary |
|--------|---------|
| `3e01296` | Phase 3 OTel propagation: sampler factory, W3C baggage, A2A trace middleware, `get_emit_mode()` with `OTEL_SEMCONV_STABILITY_OPT_IN` |
| `4246c40` | Deploy kubernetes-mixin recording rules and alerts (Loki rules, Mimir rules, docker-compose mounts, K8s ConfigMaps, portfolio dashboard updated to use new metric names) |
| `509b272` | Add wayfinder-fox package (standalone enricher, not yet wired to Rabbit) |
| `d1d7abd` | Add wayfinder-mixin Jsonnet scaffold (libsonnet files, Makefile, smoke test) |

### ContextCore (2 commits)

| Commit | Summary |
|--------|---------|
| `bd05662` | Phase 3 contracts: `get_emit_mode()` with `OTEL_SEMCONV_STABILITY_OPT_IN`, `RecordingRuleName` enum (6 members), `AlertRuleName` enum (4 members) |
| `cedc7a1` | kubernetes-mixin naming conventions added to `docs/semantic-conventions.md` (recording rule naming pattern, alert naming pattern, updated Loki rule YAML examples) |

---

## Remaining Work and Gotchas

### 1. validate_metric_name() Rejects Colons — ACTION REQUIRED

`validate_metric_name()` in **both repos** uses this regex:

```python
re.match(r"^[a-z][a-z0-9_]*$", name)
```

This rejects colons, but all `RecordingRuleName` values use the
`level:metric:aggregation` pattern with colons (valid in Prometheus).

**Recommendation**: Add a `validate_recording_rule_name()` function or update
the existing function to accept an `allow_colons=True` parameter. Recording
rules and alert rules have different naming conventions:

- Recording rules: `project:contextcore_task_percent_complete:max_over_time5m` (colons required)
- Alert rules: `ContextCoreExporterFailure` (CamelCase, no colons, starts uppercase)
- Regular metrics: `gen_ai.client.token.usage` (dots, lowercase)

The validation function currently only handles the third case. It needs to
handle all three, or provide separate validators. Both repos need the fix
since contracts are mirrored.

### 2. vendor/contextcore-spec/ Needs Sync (Initiative 1.4)

The vendored spec exists at `wayfinder/vendor/contextcore-spec/docs/semantic-conventions.md`
but is **stale** — it doesn't contain the recording rule naming convention
section added in ContextCore commit `cedc7a1`. Copy the updated file from
ContextCore:

```
Source: ~/Documents/dev/ContextCore/docs/semantic-conventions.md
Target: ~/Documents/dev/wayfinder/vendor/contextcore-spec/docs/semantic-conventions.md
```

Also check if `agent-semantic-conventions.md` needs a refresh (the vendor copy
is 12KB).

### 3. Fox → Rabbit Integration (Initiative 3.4)

Fox (`wayfinder-fox/`) is implemented as a standalone package. It has:
- `ProjectContextEnricher`, `CriticalityRouter`, `EnrichedAlert`, `FoxTracer`
- Actions in `actions/` (context_notify, claude_analysis)
- Tests and demo module

What's **missing**: no `FoxEnrichAction` class with `@action_registry.register("fox_enrich")`.
Fox doesn't import from or hook into Rabbit's dispatch system. The integration
point would be a new action class that wraps the enricher and registers with
Rabbit's action registry. Look at existing Rabbit actions for the pattern.

### 4. Alertmanager Routing (Initiative 3.5)

kubernetes-mixin alerts were deployed (commit `4246c40`) with alert names from
`AlertRuleName` enum, but Alertmanager is not configured to route them through
Fox for enrichment. This needs an Alertmanager config update with a route
matching `alertname=~"ContextCore.*"` that sends to Fox's webhook endpoint.

### 5. rabbit.yaml Needs Fox Updates (Initiative 3.7)

`k8s/observability/rabbit.yaml` exists with a basic Rabbit deployment (image:
`contextcore-rabbit:latest`, port 8080, NodePort 30080). It needs:
- Fox sidecar or separate deployment added
- RBAC for reading ProjectContext CRDs (Fox's enricher needs `get`/`list` on
  `projectcontexts.contextcore.io`)

### 6. wayfinder-mixin Dependencies (Initiative 4.4)

`wayfinder-mixin/vendor/` does not exist — `jb install` has never been run.
The `jsonnetfile.json` declares grafonnet as a dependency. Until `jb install`
is run, `jsonnet` and `make generate` will fail with import errors.

```bash
cd wayfinder-mixin && jb install
```

### 7. Golden File Tests (Initiative 4)

`wayfinder-mixin/tests/golden/` exists but is empty. After `jb install` and a
successful `make generate`, snapshot the output as golden files:

```bash
cd wayfinder-mixin
make generate
cp generated/**/*.json tests/golden/
```

Then the test target can diff against these baselines.

### 8. OPERATIONAL_RUNBOOK.md Exists (Correction)

Contrary to earlier notes, `docs/OPERATIONAL_RUNBOOK.md` **does exist** in both
repos. The alert `runbook_url` annotations referencing it are valid. However,
verify the runbook contains sections matching the alert anchors:
- `#otlp-exporter-failure` (for `ContextCoreExporterFailure`)
- `#span-state-loss` (for `ContextCoreSpanStateLoss`)
- `#insight-latency` (for `ContextCoreInsightLatencyHigh`)
- `#task-stalled` (for `ContextCoreTaskStalled`)

### 9. Expansion Pack Status Updates (Initiative 3)

The plan called for updating Fox's status in:
- `docs/EXPANSION_PACKS.md` — Fox status to "implemented"
- `.contextcore.yaml` — Fox ecosystem entry status

Neither update was made.

---

## Architecture Decisions Made Today

These decisions are now encoded in code and should not be revisited without
good reason:

1. **Model C confirmed**: ContextCore = library (contracts, types, enums).
   Wayfinder = deployment (sampler wiring, propagator setup, middleware, rules).
   Litmus test: "Would a third-party developer need this?" Yes = ContextCore.

2. **`CONTEXTCORE_EMIT_MODE` takes precedence over `OTEL_SEMCONV_STABILITY_OPT_IN`**.
   The project-specific env var wins. The OTel standard var is a fallback.
   Token to match: `gen_ai_latest_experimental`. Both repos have this logic.

3. **Sampler factory defaults to `parentbased_always_on`** (SDK default).
   No behavior change unless env vars are set. This is intentional — sampling
   is a deployment concern, not a library default.

4. **Propagator is idempotent**. `configure_propagator()` uses a module-level
   flag. Safe to call from both `TaskTracker.__init__` and `A2AServer.__init__`.

5. **Recording rule names use kubernetes-mixin convention** with colons.
   This is a deliberate deviation from the metric naming convention (underscores
   only). The enum docstrings explain the pattern.

---

## Uncommitted Files in ContextCore

These are still dirty and may relate to your work:

| File | Content |
|------|---------|
| `src/contextcore/agent/handoff.py` | OTel GenAI span naming (`{operation} {model}` pattern) |
| `src/contextcore/agent/insights.py` | `GenAIMessage` dataclass, input/output message events, content logging gate |

These contain Phase 2 OTel GenAI convention work (span naming, message events).
If your work touches `handoff.py` or `insights.py`, merge carefully — these
changes are unstaged but intentional.

---

## Uncommitted Files in Wayfinder

Only 2 untracked docs remain:
- `docs/CI_WORKFLOW_PLAN.md`
- `docs/WAYFINDER_PHASE2_PROPAGATION.md`

Everything else was committed.
