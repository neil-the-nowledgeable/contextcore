# Artisan Pipeline Issues & The Tasks-as-Spans Opportunity

**Date:** 2026-02-13
**Context:** Export enrichment implementation session + accumulated lessons from prior artisan workflow testing

---

## Part 1: Issues Identified in This Session

These are the specific problems encountered during the export enrichment implementation (2026-02-13), which was motivated by artisan workflow testing revealing incomplete contract data flowing through the pipeline.

### 1.1 Export Fields Computed but Never Surfaced

**Root cause:** `build_onboarding_metadata()` computed data during export but dropped it before writing `onboarding-metadata.json`. Downstream systems (plan ingestion, artisan DESIGN/IMPLEMENT) operated with incomplete contracts.

| Data | Computed In | Surfaced? | Impact on Artisan |
|------|------------|-----------|-------------------|
| Derivation rules (`derived_from`) | `generate_artifact_manifest()` | No | DESIGN phase had to **guess** how criticality maps to alert severity |
| Strategic objectives with key results | `strategy.objectives` | No | Dashboard generation (PI-019, PI-020) lacked business KPI definitions |
| Artifact dependency graph | `ArtifactSpec.depends_on` | No | Task sequencing relied on plan chain, ignoring artifact-level ordering |
| Resolved parameter values | `ArtifactSpec.parameters` | No | DESIGN phase re-derived concrete values from generic source pointers |
| Open questions from guidance | `guidance.questions` | No | High-priority design decisions (e.g., Q-DASHBOARD-FORMAT) were invisible |
| Design calibration hints | Domain knowledge | No | No depth/LOC signals for calibration guards |

**Fix applied:** Added all 6 fields to onboarding metadata (Changes 1-5 + Guide §6 calibration).

### 1.2 Export Models Dropping Fields During Conversion

**Root cause:** Source models had fields that export models and conversion code silently dropped.

| Source Model | Field | Export Model | Dropped? | Impact |
|-------------|-------|-------------|----------|--------|
| `KeyResult` | `operator` (gte/lte/eq) | `KeyResultExport` | Yes | Downstream can't determine if target is a min, max, or exact value |
| `KeyResult` | `window` (30d, 7d) | `KeyResultExport` | Yes | No time window context for KPI dashboard panels |
| `AgentGuidanceSpec` | `questions: List[Question]` | `GuidanceExport` | Yes | Open design questions invisible to artisan workflow |

**Fix applied:** Extended `KeyResultExport` with `operator`/`window`; added `GuidanceQuestionExport` model and `questions` field to `GuidanceExport`; updated conversion code.

### 1.3 Loki Rule Missing Derivation Audit Trail

**Root cause:** Bug in `manifest_v2.py` — the loki_rule artifact type was the only one of 7 types that didn't populate `derived_from`. All others (dashboard, prometheus_rule, slo_definition, service_monitor, notification_policy, runbook) had derivation rules.

**Impact:** Loki rules had no documented business→artifact mapping, meaning the DESIGN phase had no derivation spec for this artifact type.

**Fix applied:** Added `derived_from` rules for `logSelectors` and `logFormat` to the loki_rule artifact generation.

### 1.4 `manifest init` Template Produces Invalid Manifests — RESOLVED

**Root cause:** The v2 init template was missing required fields and sections needed for a successful init → validate → export cycle.

| Missing | Impact | Status |
|---------|--------|--------|
| `changelog.summary` (required field) | Every freshly-initialized manifest fails validation | **Fixed** |
| `spec.targets` section | Export produces **zero artifacts** — no targets, nothing to generate | **Fixed** |
| `spec.requirements` | Empty derivation rules, empty resolved parameters | **Fixed** |
| `spec.risks` | Empty runbook parameters | **Fixed** |
| `spec.observability` | No metrics interval, alert channels, log level | **Fixed** |
| `metadata.links` | No repo/wiki links in project context | **Fixed** — now includes repo, docs, dashboard |
| `keyResults.targetOperator/window` | Missing fields we just added support for | **Fixed** |
| `spec.observability.dashboardPlacement` | Dashboard derivation rule references this field | **Fixed** |
| `guidance.questions` | No example for users to follow | **Fixed** — now includes example question |

**Fix applied:** Scaffolded all missing sections with example data; added `summary` to changelog. Template now also includes 6-step workflow in next steps (edit → validate → install init → export → a2a-check-pipeline → plan-ingestion).

### 1.5 No Unified Validation Contract for Generated Artifacts

**Root cause:** The export surfaced multiple separate dictionaries (`parameter_schema`, `design_calibration_hints`, `example_outputs`) that downstream consumers had to manually correlate. ContextCore's own `ExpectedOutput` pattern (from `agent/handoff.py`) defines a unified contract with `fields`, `max_lines`, `max_tokens`, `completeness_markers` — but this wasn't used in the export.

**Impact:** No single source of truth for "what does a valid dashboard look like?" — calibration, size, required fields, and completeness markers were scattered across separate data structures.

**Fix applied:** Unified into `expected_output_contracts` per artifact type following the `ExpectedOutput` pattern.

### 1.6 Open Design Questions Not Resolvable from ContextCore Patterns

Two open questions from contextcore-coyote's modular pipeline design (Q-JSON-MODE, Q-CONTEXT-SUMMARIZATION) turned out to have answers already documented in ContextCore's own design principles, but those principles weren't discoverable:

- **Q-JSON-MODE** → ContextCore's `typed_over_prose` principle + `ExpectedOutput` + `Part.json_data()` pattern (already in `CAPABILITY_INDEX_GAP_ANALYSIS.md`)
- **Q-CONTEXT-SUMMARIZATION** → Progressive disclosure (Squirrel pattern) + token budgets per audience + proactive size estimation (already in `agent/personalization.py`, `agent/code_generation.py`, `skill/querier.py`)

**Impact:** Design sessions nearly adopted anti-patterns because existing principles weren't surfaced in the pipeline context.

---

## Part 2: Issues Known from Other Sources

These are accumulated issues from prior artisan workflow testing, quality reports, and defense-in-depth analysis documented across the ContextCore project.

### 2.1 Artisan Context Seed Quality Gaps

**Source:** `docs/ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md`

| Gap | Severity | Description |
|-----|----------|-------------|
| No artifact manifest reference in seed | High | Artisan workflow can't locate the artifact manifest |
| No artifact type → generator mapping | Critical | Generators don't know which parameters each type accepts |
| Provenance chain broken | Medium | Audit trail from manifest → export → ingestion → seed is incomplete |
| Plan vs. context mismatch | Medium | Plan references 77 artifacts for Online Boutique but context has 6 for wayfinder-core |
| No output path conventions in seed | Medium | Generated artifacts have no target directory guidance |
| Semantic conventions not in seed | Low | `semanticConventions` from manifest not carried through |

### 2.2 Silent Cascade Failures

**Source:** `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` §6

The three-piece pipeline (Export → Plan Ingestion → Artisan) has a fundamental property: **each system trusts the output of the one before it.** Documented failure modes:

| Boundary | Failure Mode | Symptom |
|----------|-------------|---------|
| Manifest → Export | Empty fields, missing targets, stale version | Missing artifacts in export |
| Export → Plan Ingestion | Stale export files, checksums don't match, hand-edited metadata | Wrong complexity score, missing features |
| Plan Ingestion → Artisan | Incorrect routing, missing artifacts in plan, incomplete task mapping | Wrong contractor, missing tasks, incomplete seed |
| Artisan → Output | Wrong parameters, missing fields, schema violations | Generated artifacts fail validation |

### 2.3 Design Calibration Mismatches

**Source:** `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` §6 Principle 5

The artisan workflow assigns depth tiers (brief/standard/comprehensive) from estimated LOC, but these can mismatch the artifact type's inherent complexity:

| Artifact Type | Expected | Red Flag Calibration |
|--------------|----------|---------------------|
| ServiceMonitor | Brief (≤50 LOC) | "Comprehensive" — LLM over-engineering a simple YAML |
| PrometheusRule | Standard (51-150 LOC) | "Brief" — will produce incomplete alert rules |
| Dashboard (Grafana JSON) | Comprehensive (>150 LOC) | "Brief" — skeleton, not a usable dashboard |
| Runbook | Standard-Comprehensive | "Brief" — will lack incident procedures |

### 2.4 Downstream Plan Ingestion Gaps

**Source:** `plans/EXPORT_ENRICHMENT_PLAN.md` §Downstream Changes

Even with the export enriched, the plan ingestion layer has known gaps:

1. **Coverage not carried into seed:** `_phase_emit` doesn't copy `onboarding.coverage` — artisan agents don't know actual project state (0% coverage, 7 gaps)
2. **No artifact-type-aware design calibration:** `_derive_design_calibration` doesn't use artifact type as a signal
3. **Open questions not injected as constraints:** `open_questions` from onboarding not surfaced as `design_constraints` in seed tasks
4. **Derivation rules not per-task:** `derivation_rules` not embedded in each seed task's context

### 2.5 Truncation and Token Limit Issues

**Source:** `docs/capability-index/contextcore.pain_points.yaml`, `docs/capability-index/contextcore.agent.yaml`

- LLM-generated code has a practical max of ~150 lines before truncation risk
- No proactive size estimation at the artisan DESIGN phase — truncation discovered at IMPLEMENT time
- Context accumulation across pipeline stages can exceed token limits without warning

### 2.6 Data Integrity Across the Chain

**Source:** `plans/EXPORT_ENRICHMENT_PLAN.md` Review Log

- **Stale cache risk:** No cache coherence between export and ingestion; absence of new fields is ambiguous ("no rules" vs "old format")
- **Cycle detection:** Dependency graph propagation without cycle detection could cause infinite loops in task sequencing
- **Secret leakage:** `resolved_artifact_parameters` could surface secrets if parameter sources change in the future

---

## Part 3: The Fundamental Opportunity — Tasks as Spans for Pipeline Execution

ContextCore's core insight is that **tasks share the same structure as distributed trace spans.** The pipeline itself is a series of tasks. Yet the pipeline is orchestrated outside of ContextCore's own observability infrastructure, meaning we lose the very visibility that ContextCore was built to provide.

### The Mapping

| Pipeline Concept | ContextCore Pattern | OTel Primitive |
|-----------------|---------------------|----------------|
| Pipeline run | Epic | Trace (root span) |
| Pipeline stage | Story/Task | Child span with parent context |
| Gate validation | Task event | Span event (`gate.validation`) |
| Stage output | Task artifact | Span attributes + structured log |
| Context flow | Task metadata | Span attributes / OTel baggage |
| Stage failure | Blocked task | Span status `ERROR` + exception event |
| Stage dependency | Task dependency | Span link (`depends_on`) |
| Parallel stages | Subtasks | Multiple child spans, same parent |
| Pipeline progress | Epic progress | Parent progress derived from children |
| Calibration check | Quality gate | Span event with calibration attributes |
| Checksum verification | Integrity gate | Span event with checksum attributes |

### What This Would Enable

**1. Unified Querying Across Pipeline and Runtime**

Pipeline execution and runtime telemetry live in the same backend (Tempo). A single TraceQL query can correlate:

```
# Which pipeline run generated the dashboard that's currently alerting?
{ pipeline.artifact.id = "checkout-api-dashboard" && pipeline.stage.name = "IMPLEMENT" }
```

**2. Automatic Progress Tracking**

ContextCore's `TaskTracker` already computes parent progress from child completion. A pipeline run with 7 stages would automatically report progress as stages complete — no separate progress tracking system needed.

**3. Boundary Validation as Span Events**

Gate validations become span events with structured attributes:

```python
span.add_event("gate.validation", attributes={
    "gate.name": "SchemaGate",
    "gate.result": "failed",
    "gate.violations": 2,
    "gate.violation.0.field": "root_cause",
    "gate.violation.0.message": "Required field missing",
})
```

These events are queryable in Tempo and derivable as metrics in Loki.

**4. Context Integrity via Trace Context**

OTel trace context (trace_id, span_id) provides built-in integrity:
- Each stage inherits the parent trace context
- Span links establish cross-trace dependencies
- Baggage propagates context (checksums, fingerprints) through the pipeline
- Any break in the trace context = break in the pipeline

**5. Failure Diagnosis via Trace Visualization**

A failed pipeline run is a trace with an ERROR span. The trace view shows:
- Which stage failed (RED span)
- What the gate violations were (span events)
- What context was available (span attributes)
- What the prior stages produced (sibling spans)
- The full timeline from start to failure

This is the "backward failure tracing" from Defense-in-Depth Principle 4 — but built into the observability infrastructure rather than implemented as ad-hoc diagnostic code.

**6. Metrics Derivation from Pipeline Logs**

ContextCore's dual-telemetry pattern (spans to Tempo, structured logs to Loki) enables:
- `pipeline_stage_duration_seconds` — derived from Loki log timestamps
- `pipeline_gate_violations_total` — derived from gate validation events
- `pipeline_success_rate` — derived from pipeline completion events
- `pipeline_calibration_mismatch_total` — derived from calibration gate events

These are the same patterns used for task metrics today — no new infrastructure needed.

### Why This Matters for the Issues Above

Every issue in Parts 1 and 2 is fundamentally a **visibility problem at pipeline boundaries:**

| Issue | Visibility Gap | Tasks-as-Spans Solution |
|-------|---------------|------------------------|
| Fields computed but not surfaced | Can't see what export produced | Export stages emit spans with output attributes |
| Model conversion dropping fields | Can't see what was lost | Conversion step emits before/after field counts |
| Silent cascade failures | Can't trace where data was lost | Trace context links export → ingestion → artisan |
| Design calibration mismatches | Can't see calibration vs. expectation | Calibration gate events with both values |
| Stale data propagation | Can't detect staleness at boundaries | Checksum attributes on every stage span |
| Truncation without warning | Can't see size estimates before generation | Size estimation events before IMPLEMENT |
| Open questions invisible | Can't see unresolved decisions | Question spans linked to affected task spans |

**The pipeline is ContextCore's most important project. It should be managed by ContextCore.**
