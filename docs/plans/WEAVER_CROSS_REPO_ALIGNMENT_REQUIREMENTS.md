# Weaver Cross-Repo Alignment Requirements

**Date:** 2026-02-11
**Status:** Draft
**Companion to:** `WEAVER_REGISTRY_REQUIREMENTS.md`
**Repos in scope:** ContextCore, Wayfinder, StartD8 SDK

---

## 1. Problem Statement

Three repositories produce and consume ContextCore-compatible OTel task state files. Each has evolved independently, creating schema drift that no automated validation catches.

| Repo | Role | Evidence |
|------|------|----------|
| **ContextCore** | Canonical producer (StateManager, TaskTracker) + schema owner | `src/contextcore/state.py`, `contracts/types.py` |
| **StartD8 SDK** | Secondary producer (task_tracking_emitter) + consumer (ContextCoreTaskSource) | `workflows/builtin/task_tracking_emitter.py`, `integrations/contextcore.py` |
| **Wayfinder** | Consumer (scripts, dashboards, progress tracker skill) | `scripts/load_tasks_to_tempo.py`, Grafana dashboards |

The WEAVER_REGISTRY_REQUIREMENTS.md plan addresses ContextCore's internal drift (prose vs. Python enums) but does not account for:

1. **Cross-repo producers** — StartD8's `task_tracking_emitter.py` writes state files with attributes not in the registry plan
2. **Cross-repo consumers** — `ContextCoreTaskSource._load_task_from_file()` in StartD8 reads attributes defensively but has no schema contract
3. **Wayfinder's parallel semconv prose** — `docs/skill-semantic-conventions.md` (70+ attributes) duplicates ContextCore conventions without referencing a shared schema
4. **ATTRIBUTE_MAPPINGS fragmentation** — `otel_genai.py` contains 2-3 overlapping mapping dicts

---

## 2. Identified Gaps

### 2.1 Attribute Name Drift Between Producers

| Attribute | ContextCore (tracker.py) | StartD8 Emitter | Registry Plan (4.1) | Risk |
|-----------|-------------------------|-----------------|---------------------|------|
| `task.blocked_by` | Defined | Not used | Defined | Consumer confusion |
| `task.depends_on` | Not defined | Used | Not defined | Emitter writes, registry ignores |
| `task.prompt` | Not defined | Used | Not defined | Useful but unformalized |
| `task.feature_id` | Not defined | Used | Not defined | Hierarchy link, no spec |
| `task.target_files` | Not defined | Used | Not defined | Code generation context |
| `task.estimated_loc` | Not defined | Used | Not defined | Sizing heuristic |

**Impact:** `ContextCoreTaskSource` reads whatever is in `attributes` — it won't reject unknown keys, but Grafana dashboards, recording rules, and the progress tracker skill only query attributes they know about. Emitter-only attributes are invisible downstream unless consumers are updated.

### 2.2 Enum Drift

| Enum | types.py (canonical) | Handoff module | Docs (prose) | Registry Plan |
|------|---------------------|----------------|-------------|---------------|
| HandoffStatus | 6 members | 9 members (+input_required, cancelled, rejected) | 9 members | 6 members |
| InsightType | 4 members | 4 members | 4 members | 4 members |

**Impact:** `types.py` is the declared source of truth, but the handoff module and docs disagree on HandoffStatus cardinality. The Weaver registry plan inherits the types.py values (6), leaving 3 runtime values unrepresented.

### 2.3 ATTRIBUTE_MAPPINGS Fragmentation

`otel_genai.py` contains multiple `ATTRIBUTE_MAPPINGS` dicts:

| Dict Location | Keys | Notes |
|---------------|------|-------|
| Top-level (lines ~17-30) | 8 mappings (agent, insight) | Primary |
| Earlier block (lines ~24-50) | 5 mappings (context, handoff) | Overlapping, different scope |
| TOOL_ATTRIBUTES | 1 constant | Correct but separate |

**Impact:** Adding a new deprecated attribute requires updating the right dict. No test validates completeness. The Weaver registry's `deprecated:` fields should be the single source for this mapping.

### 2.4 Wayfinder Parallel Specification

Wayfinder's `docs/skill-semantic-conventions.md` defines 70+ attributes covering:
- `skill.*`, `capability.*` namespaces (Wayfinder-specific)
- `agent.*`, `gen_ai.*` namespaces (duplicates ContextCore conventions)
- `task.*`, `project.*`, `sprint.*` (duplicates ContextCore conventions)

This prose document has no machine-readable counterpart and no cross-reference to ContextCore's `contracts/types.py` or the planned Weaver registry.

**Impact:** Wayfinder could introduce attributes that shadow or conflict with ContextCore conventions. No CI catches this.

### 2.5 No Cross-Repo CI Validation

| Validation | ContextCore | StartD8 SDK | Wayfinder |
|------------|-------------|-------------|-----------|
| Python enum consistency | Not automated | N/A | N/A |
| State file schema check | Not automated | Not automated | Not automated |
| Attribute name allowlist | Not automated | Not automated | Not automated |
| ATTRIBUTE_MAPPINGS completeness | Not automated | N/A | N/A |
| Weaver `registry check` | Not started | N/A | N/A |

---

## 3. Requirements

### REQ-1: Registry Must Cover Cross-Repo Attributes

The Weaver registry MUST include all attributes written by any producer, not just ContextCore's internal set.

**Acceptance criteria:**
- Registry `task.yaml` includes `task.prompt`, `task.feature_id`, `task.target_files`, `task.estimated_loc` as `opt_in` attributes
- Registry resolves `task.depends_on` vs `task.blocked_by` naming — one canonical name, the other either removed or aliased
- All attributes written by `task_tracking_emitter.py` are present in the registry

### REQ-2: Emitter Alignment

The StartD8 `task_tracking_emitter.py` MUST use attribute names from the Weaver registry.

**Acceptance criteria:**
- Emitter uses `task.blocked_by` (not `task.depends_on`) if registry chooses that name, or vice versa
- All emitter attributes pass `weaver registry check` when validated against the registry
- State files produced by the emitter are loadable by both `ContextCoreTaskSource` and `StateManager.load_span()`

### REQ-3: ATTRIBUTE_MAPPINGS Consolidation

The `otel_genai.py` dual-emit layer MUST have a single canonical `ATTRIBUTE_MAPPINGS` dict.

**Acceptance criteria:**
- One dict, no duplicates, no overlapping keys across multiple dicts
- Dict entries match `deprecated:` → replacement pairs in the Weaver registry
- Unit test validates dict completeness against registry YAML (Phase 1: manual; Phase 3: automated)

### REQ-4: HandoffStatus Enum Reconciliation

The HandoffStatus enum MUST have a single cardinality across all sources.

**Acceptance criteria:**
- `types.py` HandoffStatus has the canonical set (decide: 6 or 9 members)
- `handoff.py` runtime values are a subset of the enum
- `docs/semantic-conventions.md` matches the enum
- Weaver registry `handoff.yaml` matches the enum

### REQ-5: Wayfinder References ContextCore Registry

Wayfinder MUST NOT duplicate ContextCore semantic conventions in prose.

**Acceptance criteria:**
- `docs/skill-semantic-conventions.md` references ContextCore's registry for `task.*`, `project.*`, `sprint.*`, `agent.*` namespaces
- Wayfinder-specific namespaces (`skill.*`, `capability.*`) are either added to ContextCore's registry or maintained in a Wayfinder-specific registry extension
- No conflicting attribute definitions between the two repos

### REQ-6: Cross-Repo Schema Validation

At least one CI check MUST validate that state files conform to the registry.

**Acceptance criteria:**
- StartD8 emitter tests validate output against a schema derived from the registry
- ContextCore StateManager tests validate output against the same schema
- Schema version (currently `2`) is tracked in the registry manifest

### REQ-7: Emitter↔StateManager Format Parity

State files from `task_tracking_emitter.py` MUST be loadable by ContextCore's `StateManager.load_span()` and vice versa.

**Acceptance criteria:**
- Emitter output includes all fields required by `SpanState.from_dict()`: `task_id`, `span_name`, `trace_id`, `span_id`, `start_time`, `attributes`, `events`, `schema_version`, `project_id`
- `StateManager.load_span()` tolerates `opt_in` attributes it doesn't know about
- Round-trip test: emitter → StateManager.load_span() → StateManager.save_span() → diff is empty

---

## 4. Out of Scope

- Modifying ContextCore's runtime dual-emit behavior (registry documents, doesn't change runtime)
- Upstream OTel semconv contribution (that's a separate track in `docs/otel-semconv-wg-proposal.md`)
- Replacing `contracts/types.py` with generated code from Weaver (Python remains canonical)
- Wayfinder's `skill.*` / `capability.*` namespaces (Wayfinder-specific, can be a registry extension later)

---

## 5. Dependencies

| Dependency | Source | Status |
|------------|--------|--------|
| WEAVER_REGISTRY_REQUIREMENTS.md Phase 1 | ContextCore | Not started |
| OTel Weaver binary in CI | open-telemetry/weaver | Available (pinnable) |
| `task_tracking_emitter.py` | StartD8 SDK | Merged (commit 0d91ce8) |
| `ContextCoreTaskSource` | StartD8 SDK | Production |
| `StateManager` + `SpanState` v2 | ContextCore | Production |

---

## 6. Success Metrics

1. `weaver registry check --registry semconv/` passes with zero errors in ContextCore CI
2. All state files from all 3 producers validate against the registry schema
3. Zero attribute name drift between producers (enforced by CI)
4. Single ATTRIBUTE_MAPPINGS dict in `otel_genai.py`
5. HandoffStatus cardinality identical across types.py, handoff.py, docs, and registry
