# Weaver Cross-Repo Alignment — Implementation Plan

**Date:** 2026-02-28
**Requirements:** `WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md`
**Companion to:** `WEAVER_REGISTRY_REQUIREMENTS.md`
**Weaver target version:** v0.21.2+ (V2 schema support)
**Updated:** 2026-02-28 — Updated to reflect Layers 1–7, 10-gate pipeline, REQ-EFE, and Weaver v0.21.2

---

## Overview

**Objectives:** Phases 1-2 are ContextCore-only (establish the registry).

Seven work packages across three repos, ordered by dependency. Phases 1-2 are ContextCore-only (establish the registry). Phase 3 aligns StartD8 SDK. Phase 4 aligns Wayfinder. Phase 5 adds cross-repo CI. Phases 6-7 are cleanup and documentation.

**Estimated scope:** ~49 files modified/created, no LLM calls, no runtime behavior changes.

**Weaver context:** Weaver v0.21.2+ V2 schema format (`file_format: definition/2`) is now the target. Registry version starts at 0.1.0 (per applied R2-S5), signaling instability until the schema stabilizes.

---

**Goals:**
- Complete bootstrap weaver registry (contextcore)
- Complete consolidate attribute_mappings (contextcore)
- Complete align startd8 emitter (startd8 sdk)
- Complete reconcile handoffstatus (contextcore)
- Complete wayfinder registry reference (wayfinder)
- Register all 7 contract domain layers (propagation, schema_compat, semconv, boundary, capability, budget, lineage)
- Publish pipeline gate manifest (REQ-11)
- Acknowledge edit-first enforcement cross-repo contract (REQ-9)

## Functional Requirements

| ID | Source Phase |
|-----|-------------|
| REQ-1 | Phase 1: Bootstrap Weaver Registry (ContextCore) |
| REQ-2 | Phase 3: Align StartD8 Emitter (StartD8 SDK) |
| REQ-3 | Phase 2: Consolidate ATTRIBUTE_MAPPINGS (ContextCore) |
| REQ-4 | Phase 4: Reconcile HandoffStatus (ContextCore) |
| REQ-5 | Phase 5: Wayfinder Registry Reference (Wayfinder) |
| REQ-6 | Phase 6: Cross-Repo CI (ContextCore + StartD8 SDK) |
| REQ-7 | Phase 3: Align StartD8 Emitter (StartD8 SDK) |
| REQ-8 | Phase 7: Documentation — multi-project discovery + telemetry schema change notification |
| REQ-9 | Phase 7: Edit-First Enforcement acknowledgment (already implemented) |
| REQ-10 | Phase 2: Contract Domain Layer Registry Coverage |
| REQ-11 | Phase 1: Pipeline Gate Manifest |

## Phase 1: Bootstrap Weaver Registry (ContextCore)

**Satisfies:** WEAVER_REGISTRY_REQUIREMENTS.md Phase 1 + REQ-1 + REQ-11
**Repo:** ContextCore
**Depends on:** Nothing (unblocked)

### 1.1 Create registry manifest

**File:** `semconv/manifest.yaml`

```yaml
file_format: definition/2
schema_url: https://contextcore.io/semconv/v0.1.0
registry:
  name: contextcore
  version: 0.1.0
  description: ContextCore semantic conventions for project observability
imports:
  - url: https://opentelemetry.io/schemas/1.34.0
    scope:
      - gen_ai.*
      - service.*
      - k8s.*
      - messaging.*
      - cicd.pipeline.*
      - feature_flag.*
```

**Key changes from original plan:**
- File renamed: `registry_manifest.yaml` → `manifest.yaml` (Weaver v0.21.2 convention)
- Field renamed: `registry_url` → `schema_url` (Weaver v0.21.2 convention)
- Version: `1.0.0` → `0.1.0` (per applied R2-S5, signals instability)
- Added `file_format: definition/2` (V2 schema format)
- Added `imports:` section referencing OTel semconv `gen_ai.*` attributes (v0.15.3+ capability)
- Dependency chain: `contextcore-semconv` → `otel-semconv` (v1.34.0)

### 1.2 Generate attribute group YAMLs from Python contracts

Source of truth: `src/contextcore/contracts/types.py` + `tracker.py` constants.

| File | Source | Attributes | Enums |
|------|--------|------------|-------|
| `semconv/registry/task.yaml` | tracker.py task.* constants | 17 core + 5 opt_in (prompt, feature_id, target_files, estimated_loc, depends_on) = 22 | TaskStatus (7), TaskType (7), Priority (4) |
| `semconv/registry/project.yaml` | tracker.py project.* constants | 5 | — |
| `semconv/registry/sprint.yaml` | tracker.py sprint.* constants | 7 | — |
| `semconv/registry/agent.yaml` | ATTRIBUTE_MAPPINGS deprecated pairs | 6 (all deprecated) | AgentType (4) |

All files use V2 `file_format: definition/2` format. Layer 1–7 attribute groups are added in Phase 2 (per REQ-10).

**Key decision (REQ-1):** `task.depends_on` vs `task.blocked_by`

Recommendation: **Keep both.** They have different semantics:
- `task.blocked_by` (existing, required) — runtime blockers (something is actively blocking this task)
- `task.depends_on` (new, opt_in) — structural dependencies (this task should start after those tasks)

Both are `string[]`. The emitter writes `depends_on` (structural); the tracker writes `blocked_by` (runtime). They serve different purposes and should coexist.

**New opt_in attributes for task.yaml:**

| Attribute | Type | Req Level | Rationale |
|-----------|------|-----------|-----------|
| `task.depends_on` | string[] | opt_in | Structural dependencies from plan ingestion |
| `task.prompt` | string | opt_in | LLM implementation instructions |
| `task.feature_id` | string | opt_in | Links task to parent feature in plan hierarchy |
| `task.target_files` | string[] | opt_in | Expected output file paths |
| `task.estimated_loc` | int | opt_in | Pre-generation size estimate |

### 1.3 Generate event and span YAMLs

| File | Source | Contents |
|------|--------|----------|
| `semconv/events/task_events.yaml` | EventType enum (10 task events) | task.created, task.status_changed, task.blocked, task.unblocked, task.completed, task.cancelled, task.progress_updated, task.assigned, task.commented, subtask.completed |
| `semconv/spans/task_spans.yaml` | tracker.py span creation | contextcore.task span definition |

### 1.4 Add CI validation

**File:** `.github/workflows/validate-semconv.yml`

```yaml
on:
  pull_request:
    paths: ['semconv/**', 'src/contextcore/contracts/types.py']
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: open-telemetry/setup-weaver@v1
        with:
          version: '0.21.2'  # pin to V2 schema support
      - run: weaver registry check --registry semconv/
      - run: weaver registry resolve --registry semconv/
```

**Key changes from original plan:**
- Weaver pinned to `v0.21.2` (was `0.12.0`)
- Uses `weaver registry check` (not deprecated `weaver registry search`)
- CI uses `PolicyFinding` terminology (was `Violation`/`Advice`)

### 1.5 Add Makefile targets

```makefile
semconv-check:
	weaver registry check --registry semconv/

semconv-resolve:
	weaver registry resolve --registry semconv/
```

### 1.6 Document Registry Conventions (per applied R2-S6)

**File:** `semconv/README.md`

Define behavioral contracts for requirement levels:

| Level | Producer Contract | Consumer Contract |
|-------|-------------------|-------------------|
| `required` | MUST emit | MAY depend on presence |
| `recommended` | SHOULD emit | MUST tolerate absence |
| `opt_in` | MAY emit | MUST tolerate absence |

References `RequirementLevel` enum from `contracts/types.py` as the canonical definition.

Also includes:
- Deprecation lifecycle policy (per applied R2-S3): deprecated attributes supported for 2 minor versions, removed in next major version
- Registry versioning strategy: 0.x = unstable, 1.0 = stable contract

### 1.7 Pipeline Gate Manifest (per REQ-11)

**File:** `semconv/pipeline-gates.yaml`

Machine-readable gate manifest documenting all 11 pipeline gates from `PipelineChecker` (10 standard + 1 conditional):

```yaml
file_format: definition/2
pipeline:
  name: contextcore-a2a-pipeline
  version: 0.1.0
  gates:
    - gate: 1
      name: structural_integrity
      blocking: true
      severity: ERROR
      phase: FINALIZE_VERIFY
    - gate: 2
      name: checksum_chain
      blocking: true
      severity: ERROR
      phase: FINALIZE_VERIFY
    - gate: 3
      name: provenance_consistency
      blocking: false
      severity: WARNING
      phase: FINALIZE_VERIFY
    - gate: 4
      name: mapping_completeness
      blocking: false
      severity: WARNING
      phase: FINALIZE_VERIFY
    - gate: 5
      name: gap_parity
      blocking: false
      severity: WARNING
      phase: FINALIZE_VERIFY
    - gate: 6
      name: design_calibration
      blocking: false
      severity: WARNING
      phase: FINALIZE_VERIFY
    - gate: 7
      name: parameter_resolvability
      blocking: false
      severity: WARNING
      phase: FINALIZE_VERIFY
    - gate: 8
      name: artifact_inventory
      blocking: false
      severity: WARNING
      phase: FINALIZE_VERIFY
    - gate: 9
      name: service_metadata
      blocking: false
      severity: WARNING
      phase: FINALIZE_VERIFY
    - gate: 10
      name: edit_first_coverage
      blocking: false
      severity: WARNING
      phase: FINALIZE_VERIFY
    - gate: 11
      name: min_coverage_enforcement
      blocking: true
      severity: ERROR
      phase: FINALIZE_VERIFY
      conditional: true  # Only runs when --min-coverage flag is provided
```

Enables consumer repos to detect when upstream adds new gates (gate count in manifest vs. expected count). Gate 11 is conditional — only runs when `--min-coverage` is explicitly requested via CLI.

**Deliverables:** 10 files created, 2 files modified (Makefile, CI workflow)
**Validation:** `weaver registry check` passes with zero errors

---

## Phase 2: Consolidate ATTRIBUTE_MAPPINGS + Layer 1–7 (ContextCore)

**Satisfies:** REQ-3, REQ-10
**Repo:** ContextCore
**Depends on:** Phase 1 (registry exists to validate against)

### 2.1 Merge dicts in otel_genai.py

Consolidate the 3 overlapping `ATTRIBUTE_MAPPINGS` dicts into one canonical dict of 11 entries:

```python
ATTRIBUTE_MAPPINGS: Dict[str, str] = {
    # agent.* → gen_ai.* (6 mappings)
    "agent.id": "gen_ai.agent.id",
    "agent.type": "gen_ai.agent.type",
    "agent.session_id": "gen_ai.conversation.id",
    "agent.model": "gen_ai.request.model",
    "agent.name": "gen_ai.agent.name",
    "agent.version": "gen_ai.agent.version",
    # context.* → gen_ai.* (2 mappings)
    "context.id": "gen_ai.request.id",
    "context.model": "gen_ai.request.model",
    # handoff.* → gen_ai.tool.* (3 mappings)
    "handoff.capability_id": "gen_ai.tool.name",
    "handoff.inputs": "gen_ai.tool.call.arguments",
    "handoff.id": "gen_ai.tool.call.id",
    # insight.* → gen_ai.insight.* (3 mappings)
    "insight.type": "gen_ai.insight.type",
    "insight.value": "gen_ai.insight.value",
    "insight.confidence": "gen_ai.insight.confidence",
}
```

### 2.2 Add completeness test

**File:** `tests/compat/test_attribute_mappings.py`

Test that every `deprecated:` attribute in `semconv/registry/agent.yaml` has a corresponding entry in `ATTRIBUTE_MAPPINGS`, and vice versa.

### 2.3 Layer 1–7 Attribute Groups (per REQ-10)

Add 7 new registry YAML files for contract domain layers:

| File | Layer | Attributes | Enums |
|------|-------|------------|-------|
| `semconv/registry/propagation.yaml` | 1 | propagation.status, propagation.chain_status, propagation.field_count, propagation.defaulted_count, propagation.quality_metric, propagation.quality_threshold | PropagationStatus(4), ChainStatus(3), EvaluationPolicy(4) |
| `semconv/registry/schema_compat.yaml` | 2 | schema_compat.level, schema_compat.source_version, schema_compat.target_version | CompatibilityLevel(3) |
| `semconv/registry/semconv_enforcement.yaml` | 3 | semconv.requirement_level, semconv.attribute_count, semconv.violations | RequirementLevel(3) |
| `semconv/registry/boundary.yaml` | 4 | boundary.enforcement_mode, boundary.violations_count, boundary.phase | EnforcementMode(3) |
| `semconv/registry/capability_chain.yaml` | 5 | capability.chain_status, capability.attenuations, capability.escalation_attempts | CapabilityChainStatus(4) |
| `semconv/registry/budget.yaml` | 6 | budget.type, budget.allocated, budget.consumed, budget.remaining, budget.health, budget.overflow_policy | BudgetType(5), OverflowPolicy(3), BudgetHealth(3) |
| `semconv/registry/lineage.yaml` | 7 | lineage.status, lineage.transform_op, lineage.stage_count, lineage.verified_stages | TransformOp(6), LineageStatus(4) |

All files use `file_format: definition/2`. Total: 28 attributes across 7 files, referencing 12 enums.

### 2.4 Remaining Attribute Groups

Additional registry YAML files for non-layer attribute groups:

| File | Attributes | Enums |
|------|------------|-------|
| `semconv/registry/service_metadata.yaml` | service_metadata.transport_protocol, service_metadata.schema_contract | TransportProtocol (grpc, http, grpc-web) |
| `semconv/registry/business.yaml` | business.*, design.*, requirement.*, risk.* (16 attrs) | BusinessValue(6), RiskType(6), Criticality(4) |
| `semconv/registry/insight.yaml` | insight.*, evidence.* (15 attrs) | InsightType(4), SessionStatus(3) |
| `semconv/registry/handoff.yaml` | handoff.* (10 attrs) | HandoffStatus(6) |
| `semconv/registry/guidance.yaml` | guidance.* (7 attrs) | — |
| `semconv/registry/install.yaml` | contextcore.install.* (12 attrs) | — |
| `semconv/registry/code_generation.yaml` | gen_ai.code.* (16 attrs) | — |

Cross-cutting enums also registered: AlertPriority(4), DashboardPlacement(3), LogLevel(4), ConstraintSeverity(3), QuestionStatus(3).

### 2.5 Referenced OTel Attributes

Import `gen_ai.*`, `feature_flag.*`, `messaging.*`, `cicd.pipeline.*` via `imports:` section (not redefine):

| Namespace | Reference Method | OTel Semconv Version |
|-----------|-----------------|---------------------|
| `gen_ai.*` | `imports:` in manifest.yaml | v1.34.0 |
| `feature_flag.*` | `ref:` in registry YAMLs | v1.34.0 |
| `messaging.*` | `ref:` in registry YAMLs | v1.34.0 |
| `cicd.pipeline.*` | `ref:` in registry YAMLs | v1.34.0 |

Source: `FeatureFlagAttribute`, `MessagingAttribute`, `CicdLabelName` in `contracts/metrics.py`.

### 2.6 Spans, Events, and Metrics

**Spans:**
- `semconv/spans/sprint_span.yaml` — contextcore.sprint span
- `semconv/spans/install_span.yaml` — contextcore.install.verify hierarchy
- `semconv/spans/handoff_spans.yaml` — handoff lifecycle spans

**Events:**
- `semconv/events/agent_events.yaml` — 5 agent session/insight/handoff events

**Metrics:**
- `semconv/metrics/task_metrics.yaml` — 9 task flow metrics
- `semconv/metrics/install_metrics.yaml` — 3 install verification metrics
- `semconv/metrics/genai_metrics.yaml` — 4 GenAI metrics with bucket boundaries:

| Metric | Instrument | Unit | Buckets Source |
|--------|-----------|------|---------------|
| `gen_ai.client.token.usage` | histogram | {tokens} | `GENAI_TOKEN_USAGE_BUCKETS` |
| `gen_ai.server.request.duration` | histogram | s | `GENAI_DURATION_BUCKETS` |
| `gen_ai.server.time_to_first_token` | histogram | s | `GENAI_DURATION_BUCKETS` |
| `gen_ai.server.time_per_output_token` | histogram | s | `GENAI_DURATION_BUCKETS` |

**Deliverables:** 23 files new/modified (7 layer YAMLs + 8 additional groups + 3 span YAMLs + 1 event YAML + 3 metric YAMLs + 1 test)
**Validation:** `weaver registry check` passes; all 27 enum values match Python contracts

---

## Phase 3: Align StartD8 Emitter (StartD8 SDK)

**Satisfies:** REQ-2, REQ-7
**Repo:** StartD8 SDK
**Depends on:** Phase 1 (attribute names finalized in registry)

### 3.1 Update task_tracking_emitter.py attribute names

If Phase 1 keeps both `task.depends_on` and `task.blocked_by` (recommended), no rename needed. The emitter already uses `task.depends_on` correctly for structural dependencies.

Verify all emitter attributes are present in the registry:

| Attribute | Registry Status After Phase 1 |
|-----------|-------------------------------|
| `task.id` | required |
| `task.title` | opt_in |
| `task.type` | recommended |
| `task.status` | required |
| `task.priority` | recommended |
| `task.story_points` | opt_in |
| `task.prompt` | opt_in (new) |
| `task.depends_on` | opt_in (new) |
| `task.labels` | opt_in |
| `task.feature_id` | opt_in (new) |
| `task.target_files` | opt_in (new) |
| `task.estimated_loc` | opt_in (new) |
| `project.id` | required |
| `sprint.id` | required |

### 3.2 Add SpanState round-trip test

**File:** `tests/unit/test_task_tracking_emitter.py` (extend existing)

New test class `TestSpanStateRoundTrip`:
- Write state file with emitter
- Load with `ContextCore.state.SpanState.from_dict()` (mock or import)
- Verify all attributes survive the round trip using **semantic equivalence comparison** (per applied R2-S4):
  - Ignore key ordering in JSON dicts
  - Tolerate timestamp precision differences (compare to millisecond)
  - Handle null/default values consistently (missing key equivalent to null)
- Verify `schema_version`, `project_id`, `created_at` are present

### 3.3 Add schema validation to emitter tests

Extract the set of valid attribute names from the registry YAML (or hardcode the allowlist until cross-repo CI exists) and validate that every emitter attribute is in the set.

### 3.4 Edit-First Enforcement Validation

Verify startd8-sdk `ImplementPhaseHandler` respects `edit_min_pct` from `schema_features`:
- Add test that `ImplementPhaseHandler` enforces Gate 5 size regression check when `schema_features` includes `"edit_first_enforcement"`
- Add test that `edit_first.size_regression` span event is emitted on violation with correct attributes (`edit_first.artifact_type`, `edit_first.input_size`, `edit_first.output_size`, `edit_first.ratio`, `edit_first.threshold`, `edit_first.action`)

**Deliverables:** 1 file modified (emitter, if renames needed), 2 files modified (tests)
**Validation:** All 18+ emitter tests pass; new round-trip test passes; edit-first tests pass

---

## Phase 4: Reconcile HandoffStatus (ContextCore)

**Satisfies:** REQ-4
**Repo:** ContextCore
**Depends on:** Phase 1

### 4.1 Decide canonical cardinality

The handoff module (`handoff.py`) uses 9 members at runtime:
```
pending, accepted, in_progress, completed, failed, timeout,
input_required, cancelled, rejected
```

`types.py` declares 6 (missing `input_required`, `cancelled`, `rejected`).

**Recommendation:** Expand `types.py` to 9 members. The runtime values are real and used. The enum should reflect reality.

### 4.2 Update types.py

Add `input_required`, `cancelled`, `rejected` to `HandoffStatus` enum.

### 4.3 Update registry

Update `semconv/registry/handoff.yaml` (Phase 2 of WEAVER_REGISTRY_REQUIREMENTS.md) to list 9 members.

### 4.4 Update docs

Update `docs/semantic-conventions.md` HandoffStatus section to list 9 members (will be auto-generated in WEAVER Phase 3, but fix now to stop the drift).

**Deliverables:** 3 files modified (types.py, handoff.yaml, semantic-conventions.md)
**Validation:** `weaver registry check` passes; `HandoffStatus` enum has 9 members

---

## Phase 5: Wayfinder Registry Reference (Wayfinder)

**Satisfies:** REQ-5
**Repo:** Wayfinder
**Depends on:** Phase 1 (registry exists to reference)

### 5.1 Replace duplicated conventions in prose

Update `docs/skill-semantic-conventions.md`:
- Remove inline definitions of `task.*`, `project.*`, `sprint.*`, `agent.*` namespaces
- Add a "Referenced Conventions" section pointing to ContextCore's `semconv/registry/` path
- Keep `skill.*` and `capability.*` definitions (Wayfinder-specific)

### 5.2 Add registry dependency note

Add to Wayfinder's `CLAUDE.md` or `docs/` a note:

> Task, project, sprint, and agent semantic conventions are defined in the ContextCore Weaver registry (`semconv/registry/`). Wayfinder-specific namespaces (skill.*, capability.*) are defined locally.

### 5.3 Evaluate Wayfinder-specific registry extension

If `skill.*` and `capability.*` attributes warrant machine validation, create a Wayfinder-local `semconv/` that extends ContextCore's registry. Defer to Phase 2+ of the Weaver plan.

**Deliverables:** 1 file modified (skill-semantic-conventions.md), 1 file modified (CLAUDE.md or docs)
**Validation:** No conflicting attribute definitions; skill.* conventions still documented

---

## Phase 6: Cross-Repo CI (ContextCore + StartD8 SDK)

**Satisfies:** REQ-6
**Repo:** Both
**Depends on:** Phases 1, 3

### 6.1 Shared attribute allowlist

Generate a JSON allowlist from the registry YAML covering all 20 attribute groups (expanded from original 4):

```json
{
  "task": ["id", "type", "status", "priority", "title", "story_points",
           "labels", "url", "due_date", "blocked_by", "parent_id",
           "percent_complete", "subtask_count", "subtask_completed",
           "deliverable.count", "deliverable.verified",
           "prompt", "feature_id", "target_files", "estimated_loc", "depends_on"],
  "project": ["id", "name", "epic", "task", "trace_id"],
  "sprint": ["id", "name", "goal", "start_date", "end_date",
             "planned_points", "completed_points"],
  "propagation": ["status", "chain_status", "field_count", "defaulted_count",
                   "quality_metric", "quality_threshold"],
  "schema_compat": ["level", "source_version", "target_version"],
  "semconv": ["requirement_level", "attribute_count", "violations"],
  "boundary": ["enforcement_mode", "violations_count", "phase"],
  "capability": ["chain_status", "attenuations", "escalation_attempts"],
  "budget": ["type", "allocated", "consumed", "remaining", "health", "overflow_policy"],
  "lineage": ["status", "transform_op", "stage_count", "verified_stages"]
}
```

### 6.2 StartD8 CI check

Add a test or CI step that validates emitter output attributes against the allowlist.

**Option A (lightweight):** Hardcode allowlist in test file, update manually when registry changes.
**Option B (robust):** CI step fetches ContextCore's `semconv/registry/task.yaml`, parses attribute names, validates.

Recommend Option A for now; Option B when cross-repo CI is established.

### 6.3 ContextCore CI check

The `validate-semconv.yml` workflow from Phase 1 already runs `weaver registry check` with V2 schema. Add a step that cross-checks **all enums** in `types.py` against registry YAML enum values (per applied R2-S7):

```bash
python3 scripts/validate_enum_consistency.py \
  --registry semconv/ \
  --contracts src/contextcore/contracts/types.py \
  --scope all  # validates ALL 27 enums, not just HandoffStatus
```

The script iterates over all enums found in the registry YAMLs and checks for a corresponding, matching enum in `types.py`.

### 6.4 Weaver Advanced Capabilities

Note the following Weaver capabilities for future consideration (not blocking for Phase 6):

| Capability | Version | Status | Use Case |
|------------|---------|--------|----------|
| `weaver registry mcp` | v0.21.2 | Available | Agent-facing discovery of ContextCore attributes |
| `weaver registry live-check` | v0.20.0 | Available | Runtime validation of emitted OTLP against registry |
| `weaver registry infer` | Unreleased | Future | Auto-discover registry from live OTLP |
| `weaver registry diff` | v0.20.0 | Available | Compare current vs tagged release with V2 support |

**Scoping note:** These are future capabilities, not blocking for Phase 6. `weaver registry mcp` is of particular interest as an optional agent-facing discovery mechanism but adds operational complexity that should be deferred until agent discovery is a priority.

**Deliverables:** 1 script created (validate_enum_consistency.py), CI workflows updated in both repos, capabilities documented
**Validation:** CI passes in both repos; attribute allowlist is authoritative; all 27 enums validated

---

## Phase 7: Documentation Refresh

**Satisfies:** Cleanup + REQ-8 + REQ-9
**Repos:** All three
**Depends on:** Phases 1-6

### 7.1 ContextCore CLAUDE.md

Add to "Must Do" section:
- Run `make semconv-check` before adding new OTel attributes
- Use `task.depends_on` for structural deps, `task.blocked_by` for runtime blockers
- All new attributes must be added to `semconv/registry/` YAML before use in code

### 7.2 StartD8 SDK CLAUDE.md

Add to "Must Do" section:
- Emitter attribute names must match ContextCore Weaver registry (`semconv/registry/task.yaml`)
- New opt_in attributes require a corresponding registry addition in ContextCore

### 7.3 Wayfinder CLAUDE.md

Add to "Conventions" or equivalent section:
- `task.*`, `project.*`, `sprint.*`, `agent.*` conventions are owned by ContextCore's Weaver registry
- Wayfinder-specific conventions (`skill.*`, `capability.*`) are documented locally

### 7.4 Update WEAVER_REGISTRY_REQUIREMENTS.md

Note: WEAVER_REGISTRY_REQUIREMENTS.md has already been updated (2026-02-28) with:
- 27 enums (was ~10)
- 20 attribute groups (was 4)
- V2 schema format (`file_format: definition/2`)
- Weaver v0.21.2+ targeting
- GenAI metrics with bucket boundaries
- 7 contract domain layers (Layers 1–7)
- Directory structure with full file listing

No further changes needed to this file.

### 7.5 REQ-9 Acknowledgment (Edit-First Enforcement)

Record that the edit-first enforcement cross-repo contract is **already implemented**:

| Component | Implementation | Status |
|-----------|---------------|--------|
| ContextCore: `EXPECTED_OUTPUT_CONTRACTS` | 19 artifact types with `edit_min_pct` thresholds | Complete (REQ-EFE-010) |
| ContextCore: `schema_features` | Includes `"edit_first_enforcement"` in onboarding metadata | Complete (REQ-EFE-012) |
| ContextCore: Pipeline gate 10 | Validates `edit_min_pct` presence and range (0–100) with NaN guard | Complete (REQ-EFE-013) |
| startd8-sdk: `ImplementPhaseHandler` | Gate 5 size regression check when `schema_features` includes `"edit_first_enforcement"` | Complete (REQ-EFE-020) |
| startd8-sdk: Rejection telemetry | `edit_first.size_regression` span event with full attributes | Complete (REQ-EFE-022) |
| Documentation | `docs/design/requirements/REQ_EDIT_FIRST_ENFORCEMENT.md` | Complete |

**No new work required.** The `schema_features` field negotiates capability between producer (ContextCore) and consumer (startd8-sdk). This pattern is the template for future cross-repo contracts.

**Deliverables:** 5 files modified (3 CLAUDE.md files + acknowledgment record + existing WEAVER_REGISTRY_REQUIREMENTS.md already updated)

---

## Execution Order & Dependencies

```
Phase 1: Bootstrap Registry (ContextCore)     ← UNBLOCKED
    │
    ├──► Phase 2: Consolidate + Layer 1-7     ← depends on Phase 1 (EXPANDED)
    │
    ├──► Phase 3: Align StartD8 Emitter       ← depends on Phase 1
    │
    ├──► Phase 4: Reconcile HandoffStatus      ← depends on Phase 1
    │
    └──► Phase 5: Wayfinder Registry Ref       ← depends on Phase 1
              │
              └──► Phase 6: Cross-Repo CI      ← depends on Phases 1, 3 (EXPANDED)
                       │
                       └──► Phase 7: Docs      ← depends on Phases 1-6 (EXPANDED)
```

Phases 2, 3, 4, 5 are independent and can run in parallel after Phase 1.

---

## Risk Register

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | Weaver binary version incompatibility | MEDIUM | Pin to v0.21.2 release in CI; test locally first |
| 2 | opt_in attributes rejected by Weaver schema validation | LOW | `opt_in` is a valid requirement level in OTel semconv |
| 3 | HandoffStatus expansion breaks existing consumers | LOW | New members are additive; existing code handles unknown values |
| 4 | Cross-repo CI adds fragile coupling | MEDIUM | Option A (hardcoded allowlist) decouples repos; upgrade to Option B later |
| 5 | Wayfinder team disagrees on reference approach | LOW | skill.* and capability.* remain Wayfinder-owned; only shared namespaces reference ContextCore |
| 6 | V2 schema format still evolving (`file_format: definition/2` is unreleased default) | HIGH | Pin to Weaver v0.21.2 release behavior; monitor upstream for format finalization |
| 7 | `weaver registry search` deprecated; no V2-compatible replacement | MEDIUM | Use generated docs + `weaver registry resolve` instead |
| 8 | Layer 1–7 scope expansion significantly increases Phase 2 effort | HIGH | Layer YAMLs are mechanical translations from types.py; can be scripted |
| 9 | REQ-10 acceptance requires 12 enum cross-checks | LOW | Enum consistency script (Phase 6.3) covers this automatically |
| 10 | `gen_ai.code.*` namespace conflict with OTel GenAI SIG | MEDIUM | Monitor SIG; v0.19 structured deprecation format helps migration |
| 11 | Registry dependency chain on OTel semconv may break on upstream version bump | MEDIUM | Pin to v1.34.0; add CI check for upstream compatibility |
| 12 | `weaver registry mcp` adds operational complexity | LOW | Optional capability; defer until agent discovery is a priority |

---

## Estimated Effort

| Phase | Files (was) | Files (now) | Complexity | Notes |
|-------|-------------|-------------|------------|-------|
| 1. Bootstrap Registry | 9 new | 12 new | Medium | +manifest rename, +README, +gate manifest; Weaver YAML syntax learning curve |
| 2. Consolidate + Layers | 2 modified | 23 new/modified | Medium-High | +7 layer YAMLs, +8 additional groups, +spans/events/metrics |
| 3. Align Emitter | 2 modified | 3 modified | Low | +edit-first enforcement validation |
| 4. HandoffStatus | 3 modified | 3 modified | Low | Unchanged |
| 5. Wayfinder Reference | 2 modified | 2 modified | Low | Unchanged |
| 6. Cross-Repo CI | 3 new/modified | 4 new/modified | Medium | +expanded enum scope (27 enums), +Weaver capabilities section |
| 7. Documentation | 4 modified | 5 modified | Low | +REQ-9 acknowledgment |

**Total:** ~49 files touched across 3 repos (was ~25). No runtime behavior changes. No LLM costs.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Needing Further Review

- **architecture**: 2 accepted (R2-S3, R2-S5) — needs 1 more to reach threshold of 3
- **clarity**: no accepted suggestions yet — needs 3 to reach threshold
- **completeness**: no accepted suggestions yet — needs 3 to reach threshold
- **maintainability**: no accepted suggestions yet — needs 3 to reach threshold
- **scalability**: no accepted suggestions yet — needs 3 to reach threshold
- **security**: no accepted suggestions yet — needs 3 to reach threshold
- **testability**: no accepted suggestions yet — needs 3 to reach threshold

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R2-S3 | Add a formal deprecation lifecycle policy documenting timelines for removal and breaking change communication. | gemini-2.5 (gemini-2.5-pro) | Phase 2 introduces deprecated attributes with no mechanism for eventual removal, guaranteeing unbounded schema growth. A lightweight deprecation policy document is low effort and essential for long-term maintainability of the registry. Without it, deprecated attributes will accumulate indefinitely. | 2026-02-14 21:57:14 UTC |
| R2-S4 | Define semantic equivalence comparison semantics for the round-trip test in Phase 3.2 instead of relying on literal diff. | gemini-2.5 (gemini-2.5-pro) | Endorsed by a reviewer. The current description 'verify all attributes survive' is ambiguous and a naive diff will produce false failures due to key ordering, timestamp precision, or null handling. Specifying semantic comparison makes the test robust and actually useful. This is a low-cost clarification with high impact on test reliability. Applied in Phase 3.2 with explicit comparison rules: ignore key ordering, tolerate timestamp precision to millisecond, handle null/default equivalence. | 2026-02-14 21:57:14 UTC |
| R2-S5 | Start the registry at version 0.1.0 instead of 1.0.0 to signal instability. | gemini-2.5 (gemini-2.5-pro) | The registry is brand new with many opt_in fields and the plan itself acknowledges potential changes. Following semantic versioning conventions, 0.x correctly communicates to consumers that breaking changes may occur. Starting at 1.0.0 prematurely signals stability guarantees the project cannot yet deliver. This is a trivial change with meaningful signaling value. Applied in Phase 1.1 manifest.yaml (version: 0.1.0). | 2026-02-14 21:57:14 UTC |
| R2-S6 | Add documentation in Phase 1 explicitly defining the behavioral contract for opt_in attributes (producers MAY emit, consumers MUST tolerate absence). | gemini-2.5 (gemini-2.5-pro) | The term 'opt_in' is used throughout the plan across three repos but its precise contract is never explicitly stated. This is a low-effort documentation task that prevents misinterpretation by developers, especially in a multi-repo context where implicit assumptions are dangerous. It can be combined with R2-S3's deprecation policy in the same README. Applied as Section 1.6: semconv/README.md with RequirementLevel table and deprecation policy. | 2026-02-14 21:57:14 UTC |
| R2-S7 | Scope the enum consistency script in Phase 6.3 to validate all shared enums, not just HandoffStatus. | gemini-2.5 (gemini-2.5-pro) | The plan fixes HandoffStatus drift as a specific instance but the CI check should prevent drift in all enums (TaskStatus, TaskType, Priority, etc.). Scoping the script comprehensively is marginal additional effort during initial implementation but prevents the same class of bug from recurring in other enums. This is a straightforward improvement to the validation coverage. Applied in Phase 6.3 with `--scope all` flag validating all 27 enums. | 2026-02-14 21:57:14 UTC |
| R1-F8 / R2-S7 / R3-F7 | `opt_in` formally defined via RequirementLevel enum. | Multiple reviewers | `RequirementLevel` enum (required, recommended, opt_in) added to `contracts/types.py` as Section 3.21 in WEAVER_REGISTRY_REQUIREMENTS.md. This provides machine-readable definition of the `opt_in` semantics. Referenced in Section 1.6 README.md. | 2026-02-28 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-S1 | Mandate Option B (automated schema distribution) and remove Option A from Phase 6.2. | gemini-2.5 (gemini-2.5-pro) | The plan explicitly acknowledges Option B as the long-term goal and recommends Option A as an intentional stepping stone. Mandating Option B before cross-repo CI infrastructure exists adds complexity and risk to an already multi-repo effort. The pragmatic phased approach (Option A now, Option B later) is sound engineering. The plan already mitigates drift via CI checks and tests within each repo. | 2026-02-14 21:57:14 UTC |
| R2-S2 | Add a work package to Phase 5 to update Wayfinder's runtime consumers to use new opt_in attributes. | gemini-2.5 (gemini-2.5-pro) | The plan's stated scope is alignment and drift prevention with 'no runtime behavior changes.' Updating downstream consumers like Grafana dashboards and Python scripts is valuable but represents a separate feature/enhancement effort that should be tracked independently. Including runtime consumer changes would expand scope significantly and conflate schema alignment with feature delivery. | 2026-02-14 21:57:14 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R2
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-14 21:55:05 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|---|---|---|---|---|---|---|
| R2-S1 | architecture | critical | Mandate and define an automated schema distribution mechanism. The proposed "Option A (lightweight)" in Phase 6.2 re-introduces a manual synchronization step that undermines the project's entire goal of preventing drift. | Without a reliable, automated way for consumer repos to fetch the canonical schema, drift is inevitable. Option A is a temporary fix that will become permanent technical debt. The plan must solve the core cross-repo dependency problem head-on. | Modify Phase 6.2 to remove Option A and mandate a robust approach (Option B). Add a new step to Phase 1 to publish the generated schema/allowlist as a versioned artifact (e.g., to a GitHub release) from the ContextCore repo. | The StartD8 CI pipeline must fetch a versioned schema artifact from ContextCore as part of its validation step, not rely on a checked-in, manually-updated file. |
| R2-S2 | validation | high | Add a work package to Phase 5 to audit and update Wayfinder's key runtime consumers (`load_tasks_to_tempo.py`, Grafana dashboards) to use the newly available `opt_in` attributes. | The problem statement highlights that "Emitter-only attributes are invisible downstream unless consumers are updated." Phase 5 only updates documentation, failing to close the loop and deliver user value by making the new data visible in dashboards and scripts. | Add a new step 5.4 in Phase 5: "Update Downstream Consumers". This includes auditing consumer code and filing/linking tickets to implement the necessary changes. | A pull request in the Wayfinder repo modifies `load_tasks_to_tempo.py` to correctly parse at least one of the new `opt_in` attributes (e.g., `task.feature_id`). |
| R2-S3 | architecture | high | Add a task to define and document a formal deprecation lifecycle policy, including timelines for removal and the process for communicating breaking changes. | Phase 2 consolidates deprecation mappings but provides no mechanism to ever remove them. This guarantees schema bloat and an ever-increasing maintenance burden for backward compatibility. A formal policy is required for long-term health. | Add a new step 2.3: "Document Deprecation Policy" in a new `semconv/README.md` file. The policy should align with a semantic versioning strategy for the registry. | The policy document must specify (1) how long a deprecated attribute is supported (e.g., 2 minor versions) and (2) the process for its final removal in a future major version. |
| R2-S4 | validation | medium | Explicitly define the comparison semantics for the round-trip test in Phase 3.2 to require semantic equivalence, not a literal diff. | The current description, "Verify all attributes survive," is ambiguous. A naive diff will be brittle and fail on non-functional changes like JSON key ordering or timestamp precision. The test must be robust to be useful. | Add implementation details to the description of Phase 3.2, specifying that the comparison must ignore key order, tolerate timestamp precision differences (e.g., to the millisecond), and handle default/null values consistently. | The test code for the round-trip check must demonstrate semantic comparison, for example by loading both files into dictionaries and performing a deep comparison. |
| R2-S5 | architecture | medium | Start the registry at version `0.1.0` instead of `1.0.0` in the manifest. | The registry is new, experimental, and introduces many `opt_in` fields. Following semantic versioning conventions, a `0.x` version correctly signals to consumers that the schema is not yet stable and breaking changes may occur before a stable `1.0.0` release. | Modify the `registry_manifest.yaml` file in Phase 1.1. | The `semconv/registry_manifest.yaml` file checked into the ContextCore repository contains `version: 0.1.0`. |
| R2-S6 | data | medium | Add a task to Phase 1 to explicitly document the behavioral contract for `opt_in` attributes in the registry's README. | The term `opt_in` is used throughout the plan, but its contract for producers (MAY emit) and consumers (MUST tolerate absence) is assumed, not stated. Explicitly documenting this prevents misinterpretation by developers in any of the three repos. | Add a new step 1.6: "Document Registry Conventions", creating a `semconv/README.md` file that defines the requirement levels used. | The README must contain a section defining the stability and requirement levels, clarifying that `opt_in` means producers MAY emit the attribute and consumers MUST NOT fail if it is absent. |
| R2-S7 | validation | low | The enum consistency script proposed in Phase 6.3 should be explicitly scoped to validate *all* enums defined in `types.py` against the registry, not just the `HandoffStatus` enum. | The plan fixes the `HandoffStatus` drift (Phase 4), but the CI check in Phase 6.3 is only implicitly scoped. The check should be comprehensive to prevent future drift in other enums like `TaskStatus` or `Priority`. | Clarify the scope in the description of the `validate_enum_consistency.py` script in Phase 6.3 to state it covers all enums shared between the contracts file and the registry. | The implementation of `scripts/validate_enum_consistency.py` iterates over all enums found in the registry YAMLs and checks for a corresponding, matching enum in `types.py`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: This is the most critical missing piece; the plan's proposed workaround of a hardcoded allowlist is a major architectural weakness that must be addressed.
- R1-F7: Solving the problem for end-users (in Wayfinder) is the ultimate goal of the project, and the plan currently misses this crucial last-mile step of updating consumer code.
- R1-F2: A formal schema evolution and versioning policy is the necessary partner to a distribution mechanism; you need both to manage change safely across repositories.
- R2-S4: A formal deprecation lifecycle is essential for long-term maintainability and preventing the schema and associated compatibility logic from accumulating cruft indefinitely.
