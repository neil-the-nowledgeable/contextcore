# Requirements: Generation Profile Consumer Integration

**Status:** Draft
**Date:** 2026-03-16
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (pipeline correctness)
**Predecessor:** [REQ_GENERATION_PROFILES](REQ_GENERATION_PROFILES.md) (Phases 1-3 implemented in ContextCore)
**Target Repo:** startd8-sdk (`~/Documents/dev/startd8-sdk`)

---

## Problem Statement

ContextCore now emits generation-profile-scoped exports with 7 audience-aware profiles:

| Profile | Audience | Artifact Types Included |
|---------|----------|------------------------|
| `source` | Developer/machine | SOURCE + always-included |
| `monitoring` | Machine (automation) | MONITORING + always-included |
| `operator` | SRE | MONITORING + OPERATOR + STAKEHOLDER + always-included |
| `sponsor` | Business owner | STAKEHOLDER + always-included |
| `practitioner` | Marketing/sales | STAKEHOLDER + always-included (portal dashboards) |
| `observability` | All ops roles | All observability subcategories + always-included |
| `full` | Everyone | Everything (default, backward compatible) |

Under non-full profiles, onboarding metadata sections outside the profile's audience are replaced with `{"_omitted": "profile=<name>"}` markers instead of their normal dict/list values. The gating is declarative — each section declares which profiles include it via `_SECTION_PROFILES` in `onboarding.py`.

Sections subject to profile gating:

| Omitted Section | Normal Type | Used By |
|----------------|-------------|---------|
| `derivation_rules` | `Dict[str, List[Dict]]` | Design phase fallback map |
| `design_calibration_hints` | `Dict[artifact_type, Dict]` | `extract_guidance()` depth hints |
| `expected_output_contracts` | `Dict[str, Dict]` | Design phase fallback map |
| `parameter_resolvability` | `Dict[artifact_id, Dict]` | Preflight validation |
| `artifact_dependency_graph` | `Dict[str, List[str]]` | Design phase ordering |

The startd8-sdk pipeline has **zero awareness of generation profiles**. When it ingests source-profile export output, `_omitted` marker dicts silently pass existing type guards (`isinstance(val, dict)` returns `True` for markers) and propagate into:

1. **Design prompts** — `EnrichmentModule.render()` iterates `{"_omitted": "profile=source"}` and produces `- \`_omitted\`: profile=source` in the LLM prompt, which the model interprets as a real parameter name
2. **Context seed JSON** — `_build_seed_artifacts()` embeds marker dicts as valid `example_artifacts` data
3. **Service metadata inference** — `_infer_service_metadata()` assigns a dict to a variable expecting a string when `transport_protocol` is a marker

These are **silent data poisoning** failures — no errors are raised, no warnings are logged, and the pipeline produces subtly wrong output.

### Why This Matters

The generation profiles feature was built so source-code generation projects don't carry ~200KB of observability noise. But if the consumer pipeline doesn't understand profiles, the "noise reduction" turns into "data corruption" — worse than the original problem.

---

## Requirements

### Layer 1: Omitted Marker Detection (Foundation)

#### REQ-GPC-100: `is_omitted()` Utility Function

The startd8-sdk SHALL provide a utility function to detect ContextCore omitted-section markers:

```python
def is_omitted(value: Any) -> bool:
    """Return True if value is a ContextCore profile-omitted marker."""
    return isinstance(value, dict) and "_omitted" in value
```

**Where:** `src/startd8/seeds/utils.py` or similar shared location.

**Why:** Every consumer of onboarding fields needs this check. Without a shared function, each call site reinvents the detection logic (or more likely, doesn't check at all). The marker format `{"_omitted": "profile=source"}` is a ContextCore contract — centralizing detection means only one place to update if the marker format evolves.

**Acceptance:** `is_omitted({"_omitted": "profile=source"})` returns `True`. `is_omitted({"dashboard": {...}})` returns `False`. `is_omitted(None)` returns `False`. `is_omitted([])` returns `False`.

---

### Layer 2: Extraction Guards (Prevent Ingestion)

#### REQ-GPC-200: Plan Phase Extracts `generation_profile`

The PLAN phase handler (`context_seed/phases/plan.py`, line 135) SHALL extract `generation_profile` from the onboarding dict and store it in context:

```python
context["generation_profile"] = _onboarding.get("generation_profile", "full")
```

**Why:** Every downstream decision point (preflight, fallback selection, prompt assembly, consumption tracking) needs to know which profile produced the onboarding data. Extracting it once at the PLAN phase — the earliest point where onboarding is read — ensures it's available everywhere via the shared `context` dict. Without it, each consumer would need to re-read the raw onboarding dict.

**Acceptance:** After PLAN phase, `context["generation_profile"]` is one of `"source"`, `"monitoring"`, `"operator"`, `"sponsor"`, `"practitioner"`, `"observability"`, or `"full"` (defaulting to `"full"` for pre-profile exports that lack the field).

#### REQ-GPC-201: Extraction Skips Omitted Fields

The 8-field extraction loop in `plan.py:135-157` and the resume/recovery path in `shared.py:380-402` SHALL skip fields whose values are omitted markers, setting them to `None` in context instead:

```python
for field_key, ctx_key in _ONBOARDING_FIELDS:
    raw = _onboarding.get(field_key)
    context[ctx_key] = None if is_omitted(raw) else raw
```

**Why:** The current code does `context[ctx_key] = _onboarding.get(field_key)`, which assigns marker dicts directly into context. These markers then flow to the design phase fallback map, where `isinstance(marker, dict)` returns `True` and the marker is accepted as valid calibration/contract data. Setting to `None` instead activates existing fallback logic (LOC-based heuristics, complexity-based defaults) which is correct behavior when the field was intentionally excluded.

**Acceptance:** When onboarding contains `{"derivation_rules": {"_omitted": "profile=source"}}`, `context["onboarding_derivation_rules"]` is `None`, not the marker dict.

#### REQ-GPC-202: Resume/Recovery Preserves Profile

The `_ensure_context_loaded()` function in `shared.py:380-438` SHALL restore `generation_profile` alongside the 8 onboarding fields during session resume:

```python
if "generation_profile" not in context:
    context["generation_profile"] = _onboarding.get("generation_profile", "full")
```

**Why:** The contractor workflow supports session resume — when a phase crashes and restarts, context is reconstructed from the seed. If `generation_profile` isn't restored, the resumed session loses profile awareness and may re-ingest omitted fields as valid data. The "only restore if not already in context" pattern (matching existing fields at line 400) prevents clobbering a profile that was already correctly extracted.

**Acceptance:** After a session resume from a source-profile seed, `context["generation_profile"]` is `"source"`.

---

### Layer 3: Preflight Validation (Fail Fast)

#### REQ-GPC-300: Profile-Aware Preflight Validation

`_preflight_export_contract()` in `plan_ingestion_workflow.py:1545-1682` SHALL read `generation_profile` from onboarding and relax validation for fields known to be omitted under that profile:

| Profile | Fields Validated | Fields Skipped |
|---------|-----------------|----------------|
| `full` | All (current behavior) | None |
| `source` | `artifact_manifest_path`, `project_context_path`, `coverage`, `source_checksum` | `parameter_resolvability`, derivation_rules, calibration_hints |
| `monitoring` | All observability fields | Source artifact paths |
| `operator` | All observability fields | Source artifact paths |
| `sponsor` | Stakeholder fields + contracts/calibration | Derivation rules, dependency graph, parameter_resolvability |
| `practitioner` | Same as sponsor | Same as sponsor |
| `observability` | All observability fields | Source artifact paths |

**Why:** The current preflight (line 1620-1629) requires either `resolved_artifact_parameters` or `parameter_resolvability` to be a dict. Under source profile, `parameter_resolvability` is `{"_omitted": ...}` — this passes `isinstance(dict)` but is semantically empty. Without profile-aware relaxation, preflight either (a) passes incorrectly (the marker dict satisfies `isinstance(dict)`), giving a false positive, or (b) after REQ-GPC-201 converts it to `None`, fails with a spurious error demanding a field that was intentionally excluded.

**Acceptance:** `--profile source` export output passes preflight without errors or false warnings about missing observability fields. `--profile full` export output passes preflight identically to current behavior.

#### REQ-GPC-301: Preflight Logs Detected Profile

Preflight SHALL log the detected generation profile at INFO level:

```python
logger.info("Preflight: detected generation_profile=%s", generation_profile)
```

**Why:** When debugging pipeline failures, the first question is "what profile produced this export?" Currently this requires opening `onboarding-metadata.json` and searching for the field. A single log line at preflight time makes it immediately visible in pipeline logs and OTel spans.

**Acceptance:** Pipeline logs contain the generation profile for every run.

---

### Layer 4: Seed Assembly (Clean Propagation)

#### REQ-GPC-400: `ContextSeed` Carries `generation_profile`

The `ContextSeed` dataclass in `seeds/models.py` SHALL include a `generation_profile` field:

```python
@dataclass
class ContextSeed:
    # ... existing fields ...
    generation_profile: Optional[str] = None
```

**Why:** Currently the profile is buried inside the `onboarding` dict (`seed.onboarding["generation_profile"]`). Promoting it to a top-level field makes it accessible without parsing the onboarding blob. This matters because: (a) the seed is the handoff contract between plan ingestion and the contractor — top-level fields are the contract surface, (b) `onboarding` is `Optional[Dict[str, Any]]` with no schema, so extracting from it requires defensive coding at every call site, (c) serialization to `context-seed.json` makes the profile immediately visible in seed inspection tools.

**Acceptance:** `context-seed.json` contains `"generation_profile": "source"` at top level. Existing seeds without the field default to `None` (interpreted as `"full"`).

#### REQ-GPC-401: Seed Builder Sets Profile from Onboarding

`SeedBuilder.set_artifacts()` in `builder.py` SHALL extract `generation_profile` from the onboarding dict and store it on the builder:

```python
if onboarding:
    self._generation_profile = onboarding.get("generation_profile", "full")
```

And `build()` SHALL include it in the final `ContextSeed`.

**Why:** The `SeedBuilder` is the single assembly point where onboarding flows into the seed. Extracting the profile here means it's set once, correctly, and doesn't need to be re-derived downstream. The builder already extracts `source_checksum` from onboarding the same way (line 798) — this follows the established pattern.

**Acceptance:** A seed built from source-profile onboarding has `generation_profile="source"`.

#### REQ-GPC-402: `_build_seed_artifacts()` Guards Marker Dicts

`_build_seed_artifacts()` in `plan_ingestion_emitter.py:781-806` SHALL use `is_omitted()` before embedding onboarding fields into the artifacts dict:

```python
if ex and isinstance(ex, dict) and not is_omitted(ex):
    artifacts_out["example_artifacts"] = dict(ex)
```

**Why:** The current code at line 790 does `isinstance(ex, dict)` — the `_omitted` marker passes this check because it IS a dict. The marker then gets embedded as `{"example_artifacts": {"_omitted": "profile=source"}}` in the seed's artifacts section. Downstream code that iterates `example_artifacts` expecting artifact-type keys will process `_omitted` as an artifact type. Adding `not is_omitted(ex)` prevents this without changing the existing guard structure.

**Acceptance:** A seed built from source-profile output does not contain `_omitted` marker values in its `artifacts` section.

---

### Layer 5: Design Phase (Correct Behavior)

#### REQ-GPC-500: Fallback Map Respects Profile

The design phase fallback map in `design.py:1038-1064` SHALL skip fallback for fields that are `None` due to profile omission (as opposed to fields that are `None` because the inventory loaded them first):

```python
profile = context.get("generation_profile", "full")
for local_var, ctx_key in _fallback_map:
    fb_val = context.get(ctx_key)
    if fb_val is None:
        continue  # Omitted by profile or genuinely absent — either way, skip
    if isinstance(fb_val, dict):
        # ... existing assignment logic ...
```

**Why:** The existing fallback code already handles `None` correctly — if a field is `None`, the fallback is skipped and the design phase uses its default behavior (LOC-based heuristics). REQ-GPC-201 ensures omitted fields are `None`. So the existing fallback map needs no structural change — it just needs to NOT have its guards broken by marker dicts (which REQ-GPC-201 prevents upstream).

The real value of this requirement is the **logging**: when a fallback is skipped because the profile omitted it, the log should say so explicitly rather than silently using defaults:

```python
if fb_val is None and profile != "full":
    logger.debug("DESIGN: %s skipped (omitted by %s profile)", ctx_key, profile)
```

**Acceptance:** Source-profile seed runs produce design prompts that use LOC-based heuristics instead of observability calibration hints. Log lines explain why.

#### REQ-GPC-501: `extract_guidance()` Handles Missing Calibration

`extract_guidance()` in `seed_mapping.py:140-186` already handles `calibration_hints=None` gracefully (the `if calibration_hints and task.artifact_types_addressed:` guard at line 165 short-circuits). No code change is needed IF REQ-GPC-201 is implemented correctly.

**Why this requirement exists as documentation:** The current code is accidentally correct — `None` calibration_hints works fine. But `{"_omitted": "..."}` calibration_hints does NOT work fine (the truthiness check passes, but `calibration_hints.get("dashboard")` returns `None`, so the depth hint is silently lost). By documenting this dependency, we ensure REQ-GPC-201 is understood as a prerequisite for correct guidance extraction, not just a nice-to-have.

**Acceptance:** `extract_guidance(task, calibration_hints=None)` returns guidance without depth_hint. Same behavior as before profiles existed.

#### REQ-GPC-502: `EnrichmentModule.render()` Cannot Receive Markers

`EnrichmentModule.render()` in `modules.py:143-203` iterates `parameter_sources.items()` and renders each key-value pair into the LLM prompt. If it receives `{"_omitted": "profile=source"}`, it produces:

```
**Parameter Sources (use these names exactly):**
- `_omitted`: profile=source
```

The LLM then treats `_omitted` as a real parameter name and generates code using it.

**This is prevented by REQ-GPC-201** — if omitted fields are set to `None` at extraction time, `parameter_sources` will be `None`, and the enrichment module's `if parameter_sources:` guard (line 157) skips rendering entirely.

**Why this requirement exists as documentation:** This is the most dangerous failure mode — prompt poisoning — and it's prevented entirely by the upstream guard in REQ-GPC-201. But if someone later bypasses the extraction layer (e.g., reading onboarding directly instead of from context), the rendering layer has no defense. A defense-in-depth guard in the render method itself would be:

```python
if is_omitted(param_sources):
    return PromptFragment(text="", token_estimate=0)
```

**Acceptance:** Design prompts from source-profile seeds never contain `_omitted` as a parameter name.

---

### Layer 6: Service Metadata Inference (Type Safety)

#### REQ-GPC-600: `_infer_service_metadata()` Guards Against Marker Values

`_infer_service_metadata()` in `plan_ingestion_workflow.py:658-715` does:

```python
transport = onboarding.get("transport_protocol", "") or ""
```

If `transport_protocol` is a marker dict, `transport` becomes `{"_omitted": "..."}` (a dict, not a string). Downstream code writes `metadata["transport_protocol"] = transport`, embedding a dict where a string is expected.

**Change needed:**

```python
raw_transport = onboarding.get("transport_protocol", "")
transport = raw_transport if isinstance(raw_transport, str) else ""
```

**Why:** Unlike the onboarding fields (which are gated by REQ-GPC-201 at extraction time), `_infer_service_metadata()` reads directly from the raw onboarding dict, not from context. It's called during seed assembly, before the extraction layer runs. So the REQ-GPC-201 guard doesn't protect this path. A local type check is needed.

**Acceptance:** Source-profile onboarding with marker values in top-level fields produces service metadata with empty-string transport (triggering feature-based inference fallback) instead of dict-typed transport.

---

### Layer 7: Consumption Tracking (Observability)

#### REQ-GPC-700: Consumption Tracking Records Profile

`_track_onboarding_consumption()` in `shared.py:524-531` SHALL include `generation_profile` in its audit record:

```python
audit = context.setdefault("_onboarding_consumption", {})
audit["_generation_profile"] = context.get("generation_profile", "full")
```

**Why:** When reviewing pipeline telemetry, the consumption audit shows which phases consumed which onboarding fields. Without the profile, an audit showing "derivation_rules: never consumed" is ambiguous — was it a bug (field was available but no phase used it) or intentional (field was omitted by profile)? Including the profile makes the audit self-documenting.

**Acceptance:** Consumption audit in seed output includes `_generation_profile`.

#### REQ-GPC-701: No "Unconsumed" Warnings for Omitted Fields

If the pipeline emits warnings about unconsumed onboarding fields, it SHALL NOT warn for fields that were `None` due to profile omission:

```python
if field_value is None and generation_profile != "full":
    continue  # Intentionally omitted, not unconsumed
```

**Why:** False warnings erode trust in the warning system. If every source-profile run produces 5 "unconsumed field" warnings for fields that were never supposed to be present, operators learn to ignore warnings — including real ones.

**Acceptance:** Source-profile pipeline runs produce zero spurious unconsumed-field warnings.

---

## Implementation Order

### Phase A: Foundation (must ship together)

| Req | Description | File | Lines |
|-----|-------------|------|-------|
| REQ-GPC-100 | `is_omitted()` utility | `seeds/utils.py` (new) | ~5 |
| REQ-GPC-200 | Extract `generation_profile` at PLAN | `context_seed/phases/plan.py` | ~3 |
| REQ-GPC-201 | Skip omitted fields at extraction | `context_seed/phases/plan.py` + `shared.py` | ~15 |
| REQ-GPC-202 | Restore profile on resume | `context_seed/shared.py` | ~3 |

**~26 lines. Prevents all silent data poisoning.**

### Phase B: Clean Propagation

| Req | Description | File | Lines |
|-----|-------------|------|-------|
| REQ-GPC-300 | Profile-aware preflight | `plan_ingestion_workflow.py` | ~15 |
| REQ-GPC-301 | Log detected profile | `plan_ingestion_workflow.py` | ~2 |
| REQ-GPC-400 | Top-level seed field | `seeds/models.py` | ~3 |
| REQ-GPC-401 | Builder sets profile | `seeds/builder.py` | ~5 |
| REQ-GPC-402 | Guard markers in seed artifacts | `plan_ingestion_emitter.py` | ~5 |
| REQ-GPC-600 | Type guard in service metadata | `plan_ingestion_workflow.py` | ~3 |

**~33 lines. Ensures clean data flow from export to seed.**

### Phase C: Observability + Defense-in-Depth

| Req | Description | File | Lines |
|-----|-------------|------|-------|
| REQ-GPC-500 | Design fallback logging | `context_seed/phases/design.py` | ~5 |
| REQ-GPC-502 | Render-layer marker guard | `design_prompts/modules.py` | ~3 |
| REQ-GPC-700 | Profile in consumption audit | `context_seed/shared.py` | ~3 |
| REQ-GPC-701 | Suppress false warnings | `context_seed/shared.py` | ~5 |

**~16 lines. Makes the pipeline self-documenting.**

---

## Total Estimated Effort

~75 lines across 8 files in startd8-sdk. Phase A is the critical path — without it, source-profile exports produce silently corrupt seeds.

---

## Test Plan

### Phase A Tests

1. `test_is_omitted_detects_markers` — True for `{"_omitted": ...}`, False for normal dicts, None, lists
2. `test_plan_phase_extracts_generation_profile` — "source" from source-profile onboarding, "full" default
3. `test_plan_phase_sets_omitted_fields_to_none` — All 5 omitted fields are None in context
4. `test_plan_phase_preserves_non_omitted_fields` — Fields without markers pass through normally
5. `test_resume_restores_generation_profile` — Profile survives session resume
6. `test_resume_does_not_restore_omitted_as_markers` — Resumed context has None, not markers

### Phase B Tests

7. `test_preflight_passes_source_profile` — Source-profile output passes preflight
8. `test_preflight_fails_full_profile_missing_resolvability` — Full-profile still enforces current rules
9. `test_seed_has_top_level_generation_profile` — JSON contains the field
10. `test_seed_artifacts_no_markers` — No `_omitted` keys in seed artifacts section
11. `test_service_metadata_string_transport` — Dict transport becomes empty string

### Phase C Tests

12. `test_design_logs_profile_omission` — Log contains profile explanation
13. `test_render_skips_marker_parameter_sources` — No `_omitted` in prompt text
14. `test_consumption_audit_includes_profile` — Audit dict has `_generation_profile`

---

## Cap-Dev-Pipe Requirements (REQ-GP-402)

The capability delivery pipeline orchestrates the full flow: export → plan ingestion → contractor execution. It needs to accept and forward the generation profile.

### REQ-GPC-800: Pipeline Accepts `--profile` Flag

`run-pipeline.sh` SHALL accept a `--profile` flag and pass it through to `contextcore manifest export`:

```bash
./run-pipeline.sh --profile operator --plan plan.md
# Internally runs: contextcore manifest export ... --profile operator
```

**Why:** Without this, operators must manually run `contextcore manifest export --profile X` before invoking the pipeline — defeating the purpose of having an orchestrated pipeline. The profile must be a first-class pipeline parameter, not a pre-step.

**Acceptance:** `./run-pipeline.sh --profile source` produces source-scoped export artifacts in the pipeline's output directory.

### REQ-GPC-801: `pipeline.env` Supports `GENERATION_PROFILE`

`pipeline.env` SHALL support a `GENERATION_PROFILE` variable defaulting to `full`:

```bash
# pipeline.env
GENERATION_PROFILE=full  # source | monitoring | operator | sponsor | practitioner | observability | full
```

**Why:** CI/CD pipelines often configure behavior via environment variables rather than CLI flags. A team might set `GENERATION_PROFILE=source` in their CI config to always produce source-scoped exports for code generation pipelines, separately from `GENERATION_PROFILE=observability` for their ops pipeline.

**Acceptance:** Setting `GENERATION_PROFILE=operator` in `pipeline.env` and running `./run-pipeline.sh` (no `--profile` flag) produces operator-scoped output. CLI `--profile` overrides the env var.

### REQ-GPC-802: Pipeline Forwards Profile to Plan Ingestion

The pipeline SHALL pass `generation_profile` to the plan ingestion workflow configuration so the seed builder receives it:

```python
workflow_config = {
    "generation_profile": generation_profile,
    # ... other config ...
}
```

**Why:** The plan ingestion emitter needs the profile to set it on `ContextSeed` (REQ-GPC-400/401). If the pipeline doesn't forward it, plan ingestion falls back to reading it from onboarding metadata — which works but is indirect and loses the "operator explicitly chose this profile" signal.

**Acceptance:** The context seed produced by plan ingestion contains the profile value passed via `--profile`.

### REQ-GPC-803: Pipeline Validates Profile Before Export

The pipeline SHALL validate the `--profile` value before invoking export, producing a clear error for invalid values:

```bash
./run-pipeline.sh --profile invalid
# Error: Invalid generation profile 'invalid'. Valid values: source, monitoring, operator, sponsor, practitioner, observability, full
```

**Why:** Click validates at the `contextcore manifest export` level, but the pipeline should fail fast with a clear message rather than propagating to a Click error buried in pipeline output.

**Acceptance:** Invalid profile values produce a pipeline-level error message before any export is attempted.

---

## Audience-Aware Design Phase Enhancements (Future)

These are NOT required for correctness but would improve quality for non-full profiles:

### REQ-GPC-900: Profile-Specific Dashboard Pattern Default

When the seed contains `generation_profile`, the design phase SHOULD set a default `dashboard_pattern` parameter on dashboard artifacts:

| Profile | Default `dashboard_pattern` | Default `audience` |
|---------|---------------------------|-------------------|
| `operator` | `operational` | `operator` |
| `sponsor` | `business_health` | `sponsor` |
| `practitioner` | `portal` | `practitioner` |
| `full` / `observability` | `operational` (current behavior) | `operator` |

**Why:** This connects the profile selection to the dashboard content template without requiring the operator to also specify `--dashboard-pattern`. The profile IS the audience selection.

### REQ-GPC-901: Practitioner Portal Content Pattern

Dashboard generation for `practitioner` profile SHOULD produce portal-style dashboards with:
- Plain-language headings (no technical jargon)
- Navigation links to relevant views
- Stat panels showing domain-native KPIs (ROI, ROAS, conversion rate)
- "Start here" orientation sections
- Zero assumed Grafana literacy

**Why:** The practitioner persona (marketing, sales, support) has no observability background. The dashboard must function as a content page, not a metrics page.

---

## Relationship to Existing Work

| Document | Relationship |
|----------|-------------|
| [REQ_GENERATION_PROFILES](REQ_GENERATION_PROFILES.md) | Producer side — defines the `_omitted` marker contract and `_SECTION_PROFILES` table |
| [REQ_CROSS_CUTTING_CONTEXT_LOSS](REQ_CROSS_CUTTING_CONTEXT_LOSS.md) | Origin — identified the 200KB overhead problem |
| ContextCore `filter_artifacts_by_profile()` | Produces the filtered artifact manifest |
| ContextCore `build_onboarding_metadata()` | Produces the `_omitted` markers via `_SECTION_PROFILES` |
| ContextCore `AudienceRole` enum | Defines operator/sponsor/practitioner roles |
| ContextCore `MONITORING_TYPES`, `OPERATOR_TYPES`, `STAKEHOLDER_TYPES` | Audience-aware subcategories of `OBSERVABILITY_TYPES` |

---

## Non-Goals

- Changing the `_omitted` marker format (that's a ContextCore contract)
- Adding new onboarding fields for audience-specific data (use `parameters.audience` on `ArtifactSpec`)
- Multiple dashboard variants per service in a single export run (use sequential profile runs)
- Automatic profile selection based on plan content (profile is always explicit)
