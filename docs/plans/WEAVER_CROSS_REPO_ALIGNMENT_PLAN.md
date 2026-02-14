# Weaver Cross-Repo Alignment — Implementation Plan

**Date:** 2026-02-11
**Requirements:** `WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md`
**Companion to:** `WEAVER_REGISTRY_REQUIREMENTS.md`

---

## Overview

Seven work packages across three repos, ordered by dependency. Phases 1-2 are ContextCore-only (establish the registry). Phase 3 aligns StartD8 SDK. Phase 4 aligns Wayfinder. Phase 5 adds cross-repo CI. Phases 6-7 are cleanup and documentation.

**Estimated scope:** ~15 files modified/created, no LLM calls, no runtime behavior changes.

---

## Phase 1: Bootstrap Weaver Registry (ContextCore)

**Satisfies:** WEAVER_REGISTRY_REQUIREMENTS.md Phase 1 + REQ-1
**Repo:** ContextCore
**Depends on:** Nothing (unblocked)

### 1.1 Create registry manifest

**File:** `semconv/registry_manifest.yaml`

```yaml
schema_url: https://opentelemetry.io/schemas/1.34.0
registry:
  name: contextcore
  version: 1.0.0
  description: ContextCore semantic conventions for project observability
```

### 1.2 Generate attribute group YAMLs from Python contracts

Source of truth: `src/contextcore/contracts/types.py` + `tracker.py` constants.

| File | Source | Attributes | Enums |
|------|--------|------------|-------|
| `semconv/registry/task.yaml` | tracker.py task.* constants | 17 core + 5 opt_in (prompt, feature_id, target_files, estimated_loc, depends_on) = 22 | TaskStatus (7), TaskType (7), Priority (4) |
| `semconv/registry/project.yaml` | tracker.py project.* constants | 5 | — |
| `semconv/registry/sprint.yaml` | tracker.py sprint.* constants | 7 | — |
| `semconv/registry/agent.yaml` | ATTRIBUTE_MAPPINGS deprecated pairs | 6 (all deprecated) | — |

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
          version: '0.12.0'  # pin
      - run: weaver registry check --registry semconv/
      - run: weaver registry resolve --registry semconv/
```

### 1.5 Add Makefile targets

```makefile
semconv-check:
	weaver registry check --registry semconv/

semconv-resolve:
	weaver registry resolve --registry semconv/
```

**Deliverables:** 7 files created, 2 files modified (Makefile, CI workflow)
**Validation:** `weaver registry check` passes with zero errors

---

## Phase 2: Consolidate ATTRIBUTE_MAPPINGS (ContextCore)

**Satisfies:** REQ-3
**Repo:** ContextCore
**Depends on:** Phase 1 (registry exists to validate against)

### 2.1 Merge dicts in otel_genai.py

Consolidate the 2-3 overlapping `ATTRIBUTE_MAPPINGS` dicts into one canonical dict:

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

**Deliverables:** 1 file modified (`otel_genai.py`), 1 file created (test)
**Validation:** Existing tests pass; new test validates dict↔registry consistency

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
- Verify all attributes survive the round trip
- Verify `schema_version`, `project_id`, `created_at` are present

### 3.3 Add schema validation to emitter tests

Extract the set of valid attribute names from the registry YAML (or hardcode the allowlist until cross-repo CI exists) and validate that every emitter attribute is in the set.

**Deliverables:** 1 file modified (emitter, if renames needed), 1 file modified (tests)
**Validation:** All 18+ emitter tests pass; new round-trip test passes

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

Generate a JSON allowlist from the registry YAML:

```json
{
  "task": ["id", "type", "status", "priority", "title", "story_points",
           "labels", "url", "due_date", "blocked_by", "parent_id",
           "percent_complete", "subtask_count", "subtask_completed",
           "deliverable.count", "deliverable.verified",
           "prompt", "feature_id", "target_files", "estimated_loc", "depends_on"],
  "project": ["id", "name", "epic", "task", "trace_id"],
  "sprint": ["id", "name", "goal", "start_date", "end_date",
             "planned_points", "completed_points"]
}
```

### 6.2 StartD8 CI check

Add a test or CI step that validates emitter output attributes against the allowlist.

**Option A (lightweight):** Hardcode allowlist in test file, update manually when registry changes.
**Option B (robust):** CI step fetches ContextCore's `semconv/registry/task.yaml`, parses attribute names, validates.

Recommend Option A for now; Option B when cross-repo CI is established.

### 6.3 ContextCore CI check

The `validate-semconv.yml` workflow from Phase 1 already runs `weaver registry check`. Add a step that cross-checks `types.py` enum values against registry YAML enum values:

```bash
python3 scripts/validate_enum_consistency.py --registry semconv/ --contracts src/contextcore/contracts/types.py
```

**Deliverables:** 1 script created (validate_enum_consistency.py), CI workflows updated in both repos
**Validation:** CI passes in both repos; attribute allowlist is authoritative

---

## Phase 7: Documentation Refresh

**Satisfies:** Cleanup
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

Amend Phase 1 scope to include the 5 new opt_in attributes added in this plan. Update the attribute count from 17 to 22 for `task.yaml`.

**Deliverables:** 4 files modified (3 CLAUDE.md files + WEAVER_REGISTRY_REQUIREMENTS.md)

---

## Execution Order & Dependencies

```
Phase 1: Bootstrap Registry (ContextCore)          ← UNBLOCKED
    │
    ├──► Phase 2: Consolidate ATTRIBUTE_MAPPINGS    ← depends on Phase 1
    │
    ├──► Phase 3: Align StartD8 Emitter             ← depends on Phase 1
    │
    ├──► Phase 4: Reconcile HandoffStatus            ← depends on Phase 1
    │
    └──► Phase 5: Wayfinder Registry Reference       ← depends on Phase 1
              │
              └──► Phase 6: Cross-Repo CI            ← depends on Phases 1, 3
                       │
                       └──► Phase 7: Documentation   ← depends on Phases 1-6
```

Phases 2, 3, 4, 5 are independent and can run in parallel after Phase 1.

---

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Weaver binary version incompatibility | MEDIUM | Pin to specific release in CI; test locally first |
| opt_in attributes rejected by Weaver schema validation | LOW | `opt_in` is a valid requirement level in OTel semconv |
| HandoffStatus expansion breaks existing consumers | LOW | New members are additive; existing code handles unknown values |
| Cross-repo CI adds fragile coupling | MEDIUM | Option A (hardcoded allowlist) decouples repos; upgrade to Option B later |
| Wayfinder team disagrees on reference approach | LOW | skill.* and capability.* remain Wayfinder-owned; only shared namespaces reference ContextCore |

---

## Estimated Effort

| Phase | Files | Complexity | Notes |
|-------|-------|------------|-------|
| 1. Bootstrap Registry | 9 new | Medium | Mechanical translation from Python; Weaver YAML syntax learning curve |
| 2. Consolidate Mappings | 2 modified | Low | Dict merge + test |
| 3. Align Emitter | 2 modified | Low | Possibly zero changes if naming is accepted as-is |
| 4. HandoffStatus | 3 modified | Low | Add 3 enum members + propagate |
| 5. Wayfinder Reference | 2 modified | Low | Prose editing |
| 6. Cross-Repo CI | 3 new/modified | Medium | Script + CI config |
| 7. Documentation | 4 modified | Low | CLAUDE.md updates |

**Total:** ~25 files touched across 3 repos. No runtime behavior changes. No LLM costs.
