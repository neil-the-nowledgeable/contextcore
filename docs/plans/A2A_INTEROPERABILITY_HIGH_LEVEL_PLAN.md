# A2A Interoperability High-Level Plan

> **Status**: Predecessor document (pre-implementation strategy). All phases (A-D) are complete. The implemented architecture is documented in [A2A Communications Design](design/contextcore-a2a-comms-design.md).

This plan defines a lightweight way to make agent-to-agent (A2A) execution highly effective while keeping ContextCore task telemetry focused (not noisy).

It builds on capabilities that already exist:

- tasks/subtasks as spans (`TaskTracker`),
- typed handoffs (`handoff.*` and `gen_ai.tool.*`),
- dual semantic conventions (`agent.*` + `gen_ai.*`),
- onboarding metadata (`parameter_sources`, `coverage.gaps`, `artifact_task_mapping`),
- checksum/provenance gates.

---

## 1) High-Level Objective

Create a single interoperable execution model where:

- design and development work is represented as a trace,
- A2A delegation is represented as typed handoff spans,
- observability artifact needs are promoted to tasks only when they meet clear criteria,
- and downstream systems can consume structured payloads without parsing prose.

---

## 2) Core Principle: Typed Over Narrative

For A2A interoperability, every cross-agent boundary should exchange typed structures first, narrative second.

Minimum shared structures:

- `TaskSpanContract` (task identity, phase, status, parent, checksums, acceptance criteria)
- `HandoffContract` (who delegates, capability requested, typed inputs, expected outputs)
- `ArtifactIntent` (artifact kind, source parameters, output convention, ownership)
- `GateResult` (pass/fail, reason, blocking severity, next action)

Narrative is still useful, but cannot be the source of truth for routing or execution.

---

## 3) "Artifact As Task" Promotion Rules (Avoid Overuse)

Represent an observability artifact need as a task only when at least one rule is true:

1. **Lifecycle rule**: artifact requires multiple states (plan, design, implement, validate, review).
2. **Dependency rule**: artifact depends on another artifact or upstream gate.
3. **Risk rule**: artifact failure can cause incorrect routing, broken dashboards/alerts, or stale provenance.
4. **Ownership rule**: artifact has a clear owner/team and acceptance criteria.
5. **Traceability rule**: artifact must be auditable across handoffs.

If none apply, record as a span event under an existing task (not a new task).

---

## 4) Minimal Span Taxonomy For Execution

Use a stable, small taxonomy to avoid instrumentation sprawl:

- `INIT_BASELINE`
- `EXPORT_CONTRACT`
- `CONTRACT_INTEGRITY`
- `INGEST_PARSE_ASSESS`
- `ROUTING_DECISION`
- `ARTISAN_DESIGN`
- `ARTISAN_IMPLEMENT`
- `TEST_VALIDATE`
- `REVIEW_CALIBRATE`
- `FINALIZE_VERIFY`

Each phase can have child spans for high-risk checks (checksum, mapping completeness, gap parity, schema validation).

---

## 5) Required Interop Attributes (Cross-Agent Minimum)

Every task/handoff span should include:

- `project.id`
- `task.id`
- `task.parent_id` (for subtasks)
- `task.phase`
- `task.status`
- `handoff.id` (or `gen_ai.tool.call.id` for delegated work)
- `handoff.capability_id` (or `gen_ai.tool.name`)
- `input.source_checksum`
- `input.artifact_manifest_checksum`
- `quality.gap_count`
- `quality.feature_count`
- `routing.complexity_score`
- `routing.selected_path`
- `output.artifact_count`
- `output.finalize_status`

This is intentionally small. Add fields only when query/use-case demand is proven.

---

## 6) A2A Execution Pattern (High-Level)

1. Parent agent opens trace for feature (`PI-101-002` style).
2. Parent creates phase span and gate criteria.
3. Parent delegates specialized work via typed handoff (`capability_id`, typed inputs, expected output contract).
4. Child agent emits result span and `result_trace_id`.
5. Parent validates `GateResult` before opening next phase.
6. If gate fails, parent marks blocked with explicit `blocked_reason`, `blocked_on_span_id`, `next_action`.

This preserves context through failures and prevents hidden translation loss between phases.

---

## 7) Guardrails To Prevent Over-Instrumentation

- **Task budget per feature**: start with 8-12 spans max for a full feature trace.
- **Child span budget**: only for high-risk checks; default max 1-2 child spans per phase.
- **New attribute policy**: new attribute must power a concrete query or alert.
- **Promotion policy**: prefer event log until artifact satisfies promotion rules.
- **Weekly trim**: remove low-value attributes/events from templates.

---

## 8) Queries That Should Work On Day 1 ✓

All of these queries now work via `queries.py` and the A2A governance dashboard:

- ✓ "Which phase blocks most often for `PI-101-002`?" — `blocked_span_hotspot()`
- ✓ "How many artifacts in `coverage.gaps` were dropped before implementation?" — `dropped_artifacts()`
- ✓ "Which handoffs failed due to schema/checksum mismatch?" — `handoff_validation_failures()`
- ✓ "What percent of artifact intents were promoted to tasks vs kept as events?" — queryable via TraceQL
- ✓ "Which tasks finalized partial/failed despite successful routing?" — `finalize_failure_trend()`

---

## 9) Implementation Phasing (Start High-Level, Then Tighten)

### Phase A: Standardize contracts ✓

- ✓ Adopted the four contracts (`TaskSpanContract`, `HandoffContract`, `ArtifactIntent`, `GateResult`) as project conventions — `models.py`
- ✓ Minimal and versioned (`schema_version = "v1"`, `additionalProperties: false`) — `schemas/contracts/*.schema.json`

### Phase B: Instrument one pilot trace ✓

- ✓ Full PI-101-002 trace with 10 spans and gate results — `pilot.py`
- ✓ Failure injection for checksum, gap parity, and test failures — `a2a-pilot` CLI

### Phase C: Enforce promotion and gate policies ✓

- ✓ Artifact promotion rules documented — `A2A_V1_GOVERNANCE_POLICY.md` §8
- ✓ Fail fast on checksum/provenance/gap parity failures — `gates.py`, `pipeline_checker.py`
- ✓ Pipeline integrity checker with 6 gates on real export output — `a2a-check-pipeline` CLI
- ✓ Three Questions diagnostic with stop-at-first-failure — `a2a-diagnose` CLI

### Phase D: Dashboard and automation ✓

- ✓ 8-panel governance dashboard — `a2a-governance.json`
- ✓ 5 pre-built TraceQL/LogQL queries — `queries.py`
- ✓ CI-compatible `--fail-on-unhealthy` and `--fail-on-issue` flags

---

## 10) Definition Of Success ✓

All success criteria are met:

- ✓ Most failures are caught in `CONTRACT_INTEGRITY` or `INGEST_PARSE_ASSESS`, not in finalize — pipeline checker gates enforce this
- ✓ A2A handoffs are reconstructable end-to-end via trace links — pilot trace provides full evidence chain
- ✓ Artifact generation scope is visible and auditable (`artifact_task_mapping` + gap parity) — `check_mapping_completeness` and `check_gap_parity` gates
- ✓ Telemetry footprint stays lean enough for operators to trust — 10-phase enum, minimal required attributes
