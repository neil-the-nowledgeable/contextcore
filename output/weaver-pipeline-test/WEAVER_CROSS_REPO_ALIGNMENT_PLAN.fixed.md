# Weaver Cross-Repo Alignment — Implementation Plan

**Date:** 2026-02-11
**Requirements:** `WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md`
**Companion to:** `WEAVER_REGISTRY_REQUIREMENTS.md`

---

## Overview

**Objectives:** Phases 1-2 are ContextCore-only (establish the registry).

Seven work packages across three repos, ordered by dependency. Phases 1-2 are ContextCore-only (establish the registry). Phase 3 aligns StartD8 SDK. Phase 4 aligns Wayfinder. Phase 5 adds cross-repo CI. Phases 6-7 are cleanup and documentation.

**Estimated scope:** ~15 files modified/created, no LLM calls, no runtime behavior changes.

---

**Goals:**
- Complete bootstrap weaver registry (contextcore)
- Complete consolidate attribute_mappings (contextcore)
- Complete align startd8 emitter (startd8 sdk)
- Complete reconcile handoffstatus (contextcore)
- Complete wayfinder registry reference (wayfinder)

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
| R2-S4 | Define semantic equivalence comparison semantics for the round-trip test in Phase 3.2 instead of relying on literal diff. | gemini-2.5 (gemini-2.5-pro) | Endorsed by a reviewer. The current description 'verify all attributes survive' is ambiguous and a naive diff will produce false failures due to key ordering, timestamp precision, or null handling. Specifying semantic comparison makes the test robust and actually useful. This is a low-cost clarification with high impact on test reliability. | 2026-02-14 21:57:14 UTC |
| R2-S5 | Start the registry at version 0.1.0 instead of 1.0.0 to signal instability. | gemini-2.5 (gemini-2.5-pro) | The registry is brand new with many opt_in fields and the plan itself acknowledges potential changes. Following semantic versioning conventions, 0.x correctly communicates to consumers that breaking changes may occur. Starting at 1.0.0 prematurely signals stability guarantees the project cannot yet deliver. This is a trivial change with meaningful signaling value. | 2026-02-14 21:57:14 UTC |
| R2-S6 | Add documentation in Phase 1 explicitly defining the behavioral contract for opt_in attributes (producers MAY emit, consumers MUST tolerate absence). | gemini-2.5 (gemini-2.5-pro) | The term 'opt_in' is used throughout the plan across three repos but its precise contract is never explicitly stated. This is a low-effort documentation task that prevents misinterpretation by developers, especially in a multi-repo context where implicit assumptions are dangerous. It can be combined with R2-S3's deprecation policy in the same README. | 2026-02-14 21:57:14 UTC |
| R2-S7 | Scope the enum consistency script in Phase 6.3 to validate all shared enums, not just HandoffStatus. | gemini-2.5 (gemini-2.5-pro) | The plan fixes HandoffStatus drift as a specific instance but the CI check should prevent drift in all enums (TaskStatus, TaskType, Priority, etc.). Scoping the script comprehensively is marginal additional effort during initial implementation but prevents the same class of bug from recurring in other enums. This is a straightforward improvement to the validation coverage. | 2026-02-14 21:57:14 UTC |

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
