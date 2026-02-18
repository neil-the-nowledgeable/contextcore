# Requirements: Capability-Aware Init and Export Pipeline

**Status:** Implemented (all 10 requirements)
**Date:** 2026-02-16 (requirements), 2026-02-17 (prerequisite + implementation update)
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 2 (high value, medium complexity)
**Companion docs:**
- [MANIFEST_EXPORT_REQUIREMENTS.md](../MANIFEST_EXPORT_REQUIREMENTS.md) — behavioral spec for export
- [ONBOARDING_METADATA_SCHEMA.md](../ONBOARDING_METADATA_SCHEMA.md) — onboarding enrichment schema
- [REQ_CAPABILITY_INDEX_DISCOVERABILITY.md](REQ_CAPABILITY_INDEX_DISCOVERABILITY.md) — capability index enhancements (REQ-CID-001 through REQ-CID-012)
**Affected code:**
- `src/contextcore/cli/manifest.py` — CLI command definitions
- `src/contextcore/cli/init_from_plan_ops.py` — init template and inference engine
- `src/contextcore/utils/onboarding.py` — onboarding metadata enrichment
- `src/contextcore/utils/provenance.py` — run provenance payload
- `src/contextcore/cli/export_io_ops.py` — export file writing
**Estimated implementation:** ~400 lines Python + test updates

> **Implementation update (2026-02-17):** All 10 REQ-CAP requirements are **implemented** in production code with 41+ dedicated tests across 4 test files. REQ-CAP-001 is in `src/contextcore/utils/capability_index.py` (209 lines). REQ-CAP-002/003 are in `init_from_plan_ops.py` (`enrich_template_from_capability_index()`, `match_triggers`/`match_patterns`/`match_principles` integration). REQ-CAP-005/006 are in `onboarding.py` (`capability_context`, `design_principles` in guidance). REQ-CAP-007 uses `discover_expansion_pack_metrics()` in `manifest.py`. REQ-CAP-009 passes `capability_index_version` to provenance. All 12 REQ-CID prerequisites (P1 + P2 + P3) are also complete — capability index now has 9 design principles, 6 patterns, 15+ new capabilities (contracts + A2A + P2), discovery paths, and enriched triggers.

---

## Problem Statement

The `manifest init`, `manifest init-from-plan`, and `manifest export` commands were
designed before the capability index enhancements (REQ-CID-001 through REQ-CID-012),
the 7-layer defense-in-depth contract system, and the A2A governance contracts. As a
result, all three commands operate without awareness of:

1. **9 design principles** declared in `contextcore.agent.yaml` `design_principles`
   section (REQ-CID-001) — including `typed_over_prose`,
   `prescriptive_over_descriptive`, `framework_agnostic_contracts`, etc.
2. **6 communication patterns** declared in `contextcore.agent.yaml` `patterns`
   section (REQ-CID-002) — including `contract_validation`, `a2a_governance`,
   `pipeline_communication`, etc.
3. **13 contract capabilities** (`contextcore.contract.*` and `contextcore.a2a.*`)
   declared via REQ-CID-011 and REQ-CID-012.
4. **18 benefits** declared in `contextcore.benefits.yaml`.

### Concrete gaps

| Command | Gap | Impact |
|---------|-----|--------|
| `manifest init` | `guidance.constraints` always empty | New projects start with no governance constraints |
| `manifest init` | `guidance.preferences` always empty | No pattern recommendations |
| `manifest init` | 25+ hardcoded defaults | Same template for microservice, pipeline, UI, and infrastructure |
| `init-from-plan` | No principle/pattern matching from plan text | Plan mentions "multi-agent" but typed_over_prose principle not surfaced |
| `init-from-plan` | A2A gate readiness thresholds are hardcoded | Thresholds don't reflect actual gate requirements |
| `init-from-plan` | No capability-aware question generation | Missing questions not derived from capability coverage gaps |
| `manifest export` | No capability references in onboarding metadata | Downstream consumers can't discover applicable capabilities |
| `manifest export` | No design principle references in export output | Plan ingestion doesn't know which principles govern the pipeline |
| `manifest export` | Expansion pack metrics hardcoded | Beaver metrics literal list instead of capability-derived |
| All three | No capability index loaded during execution | Rich structured data exists but is never consulted |

### What this is NOT

This is NOT a request to make the commands depend on LLM inference or NLP. The
capability index is structured YAML — matching is deterministic keyword/trigger
lookup, not probabilistic analysis. The integration is mechanical: load YAML, match
fields, inject results.

---

## Requirements

### REQ-CAP-001: Capability index loader utility

**Priority:** P1 (prerequisite for all other requirements)
**Status:** **Implemented** (pre-existing, 2026-02-17 confirmed)
**Description:** Create a utility module that loads and caches capability index
manifests from `docs/capability-index/`. This utility is shared by init, init-from-plan,
and export commands.

> **Already implemented** in `src/contextcore/utils/capability_index.py` (209 lines) with all acceptance criteria met: `load_capability_index()`, `CapabilityIndex` dataclass with `principles`, `patterns`, `capabilities`, `benefits`, `match_triggers()`, `match_patterns()`, `match_principles()`, module-level cache with `clear_cache()`. 16 unit tests in `tests/unit/contextcore/utils/test_capability_index.py`. Additionally, programmatic build/validate tooling added: `capability_scanner.py` (19 tests), `capability_builder.py` (17 tests), `capability_validator.py` (32 tests), CLI `contextcore capability-index build|validate|diff`.

**Acceptance criteria:**
- New module `src/contextcore/utils/capability_index.py` with:
  - `load_capability_index(index_dir: Path) -> CapabilityIndex` — loads all `.yaml`
    files from the index directory, returns a structured object.
  - `CapabilityIndex` dataclass or Pydantic model with:
    - `principles: list[Principle]` — from `design_principles` section
    - `patterns: list[Pattern]` — from `patterns` section
    - `capabilities: list[Capability]` — from `capabilities` section
    - `benefits: list[Benefit]` — from benefits manifest
  - `match_triggers(text: str, capabilities: list) -> list[Capability]` — returns
    capabilities whose `triggers` list contains a substring match in the text.
  - `match_principles(capability_ids: list[str]) -> list[Principle]` — returns
    principles whose `applies_to` lists overlap with the given capability IDs.
  - Cache: module-level `_cache` dict keyed by resolved directory path. `clear_cache()`
    classmethod.
- Default index directory: `docs/capability-index/` relative to project root.
  Falls back gracefully if directory does not exist (returns empty CapabilityIndex).
- The loader must handle the case where `design_principles` and `patterns` sections
  do not yet exist in the YAML (pre-enhancement manifests).

**Affected files:**
- `src/contextcore/utils/capability_index.py` (NEW)

---

### REQ-CAP-002: Design principles injected into `manifest init` guidance

**Priority:** P1
**Status:** **Implemented** — `enrich_template_from_capability_index()` in `init_from_plan_ops.py` injects top principles as `guidance.constraints` and top patterns as `guidance.preferences`. Called from `manifest.py:441`.
**Description:** When `manifest init` creates a new manifest, pre-populate
`guidance.constraints` with applicable design principles from the capability
index. The goal is that new projects start with governance guardrails, not
empty constraint lists.

**Acceptance criteria:**
- `build_v2_manifest_template()` (or a post-processing step) loads the capability
  index via REQ-CAP-001.
- If the index is available and contains `design_principles`, the 3 most
  universally applicable principles are injected as `guidance.constraints`:
  - `typed_over_prose` — always applicable
  - `prescriptive_over_descriptive` — always applicable
  - `observable_contracts` — always applicable
- Each injected constraint has:
  - `id`: `C-PRINCIPLE-{N}` (e.g., `C-PRINCIPLE-1`)
  - `rule`: the principle's `principle` field (one-sentence)
  - `severity`: `"advisory"` (not blocking — these are recommendations for new projects)
  - `source`: `"contextcore.agent.yaml#typed_over_prose"` (capability index reference)
- If the capability index is not available, the template is unchanged (graceful
  fallback to current behavior).
- The `guidance.preferences` field is populated with the top 2 most common
  patterns:
  - `typed_handoff`
  - `contract_validation`
- Each injected preference has:
  - `id`: `P-PATTERN-{N}`
  - `description`: the pattern's `summary` field
  - `source`: `"contextcore.agent.yaml#typed_handoff"` (pattern reference)

**Affected files:**
- `src/contextcore/cli/init_from_plan_ops.py` — `build_v2_manifest_template()`

---

### REQ-CAP-003: Pattern matching in `init-from-plan` inference

**Priority:** P1
**Status:** **Implemented** — `infer_init_from_plan()` calls `match_triggers()`, `match_patterns()`, `match_principles()` from `capability_index.py`. Records inferences with `"capability_index:trigger_match"` source. Includes capability coverage readiness check and gap analysis.
**Description:** Extend `infer_init_from_plan()` to match plan text against
capability index triggers and patterns, injecting matched patterns as
`guidance.preferences` and matched principles as `guidance.constraints`.

**Acceptance criteria:**
- After existing text inference (lines 151-477 in `init_from_plan_ops.py`),
  a new inference pass runs:
  1. Load capability index via REQ-CAP-001.
  2. Call `match_triggers(combined_text, capabilities)` to find capabilities
     whose triggers appear in the plan + requirements text.
  3. For each matched capability, look up which patterns include it.
  4. For each matched pattern, look up which principles apply to its capabilities.
  5. Inject matched patterns as `guidance.preferences` entries.
  6. Inject matched principles as `guidance.constraints` entries.
- Each inference is recorded in the `inferences` list with:
  - `field_path`: `"guidance.constraints[N]"` or `"guidance.preferences[N]"`
  - `source`: `"capability_index:trigger_match:{trigger_text}"`
  - `confidence`: `0.75` for trigger matches (same tier as latencyP99 inference)
- Matched capabilities are recorded in a new `matched_capabilities` field in
  the inference report.
- If no triggers match, no constraints or preferences are injected (no noise).
- Existing inferences are NOT modified — capability matching is additive.
- The readiness assessment gains a new check:
  - `capability_coverage`: pass if >= 1 capability matched, warn if 0.
  - Adds 5 points to readiness score if capabilities matched.

**Affected files:**
- `src/contextcore/cli/init_from_plan_ops.py` — `infer_init_from_plan()`

---

### REQ-CAP-004: Gate-derived readiness thresholds in `init-from-plan`

**Priority:** P2
**Status:** **Implemented** — Readiness thresholds externalized; capability-derived gate config consulted when available.
**Description:** Replace hardcoded A2A gate readiness thresholds with values
derived from the gate capability definitions or gate requirements.

**Acceptance criteria:**
- The A2A gate readiness predictions (lines 563-568 in `init_from_plan_ops.py`)
  are derived from gate capability metadata instead of hardcoded:
  - Current: `checksum_chain: ready if populated_reqs >= 2` (hardcoded `2`)
  - Target: threshold loaded from `contextcore.a2a.gate.pipeline_integrity`
    capability's `inputs` schema or from a configuration constant that
    references the gate requirements doc.
- If capability index is not available, fall back to current hardcoded values.
- The readiness verdict thresholds (60/30) are externalized to a config dict
  at module level, with a comment referencing the source rationale.

**Affected files:**
- `src/contextcore/cli/init_from_plan_ops.py` — readiness assessment section

---

### REQ-CAP-005: Capability references in export onboarding metadata

**Priority:** P1
**Status:** **Implemented** — `build_onboarding_metadata()` in `onboarding.py` accepts `capability_index_dir` param, loads the index, and emits `capability_context` with `applicable_principles`, `applicable_patterns`, `contract_layers_applicable`, and `governance_gates`. Called from `manifest.py:1950`.
**Description:** Extend `build_onboarding_metadata()` to include a
`capability_context` section that tells downstream consumers which design
principles, patterns, and contract capabilities are applicable to this
project's exported artifacts.

**Acceptance criteria:**
- `onboarding-metadata.json` gains a new top-level field `capability_context`:
  ```json
  {
    "capability_context": {
      "applicable_principles": [
        {
          "id": "typed_over_prose",
          "principle": "All inter-agent data exchange uses typed schemas...",
          "source": "contextcore.agent.yaml"
        }
      ],
      "applicable_patterns": [
        {
          "pattern_id": "contract_validation",
          "name": "Contract Validation (Defense-in-Depth)",
          "capabilities": ["contextcore.contract.propagation", "..."]
        }
      ],
      "contract_layers_applicable": [
        "contextcore.contract.propagation",
        "contextcore.contract.schema_compat",
        "contextcore.contract.slo_budget"
      ],
      "governance_gates": [
        "contextcore.a2a.gate.pipeline_integrity",
        "contextcore.a2a.gate.diagnostic"
      ]
    }
  }
  ```
- The `capability_context` is derived by:
  1. Loading the capability index via REQ-CAP-001.
  2. Matching artifact types in the manifest against capability triggers.
  3. For each matched capability, including its parent patterns and governing
     principles.
  4. Always including the governance gate capabilities (they apply to all exports).
- If the capability index is not available, `capability_context` is omitted
  (graceful fallback).
- The field is documented in `ONBOARDING_METADATA_SCHEMA.md`.
- Gate 1 (`a2a-check-pipeline`) can optionally validate that `capability_context`
  is present and non-empty (future enhancement, not required in this iteration).

**Affected files:**
- `src/contextcore/utils/onboarding.py` — `build_onboarding_metadata()`
- `docs/design/ONBOARDING_METADATA_SCHEMA.md` — schema documentation

---

### REQ-CAP-006: Principle-sourced guidance in export

**Priority:** P2
**Status:** **Implemented** — `build_onboarding_metadata()` injects `guidance.design_principles` from matched principles in the capability index (`onboarding.py:694`).
**Description:** When export builds the `guidance` field in onboarding metadata,
include applicable design principles from the capability index as governance
context for downstream consumers.

**Acceptance criteria:**
- The `guidance` section in `onboarding-metadata.json` gains a
  `design_principles` subfield:
  ```json
  {
    "guidance": {
      "constraints": [...],
      "preferences": [...],
      "questions": [...],
      "design_principles": [
        {
          "id": "prescriptive_over_descriptive",
          "principle": "Declare what should happen and verify it did...",
          "anti_patterns": ["Relying on post-hoc log analysis..."]
        }
      ]
    }
  }
  ```
- Principles are selected based on which contract capabilities are relevant
  to the project's artifact types (via `applies_to` field matching).
- If the source manifest already has `guidance.constraints` referencing
  principles (e.g., from REQ-CAP-002), those references are preserved and
  not duplicated.

**Affected files:**
- `src/contextcore/utils/onboarding.py` — guidance enrichment section

---

### REQ-CAP-007: Capability-derived expansion pack metrics

**Priority:** P2
**Status:** **Implemented** — `discover_expansion_pack_metrics()` in `capability_index.py` replaces hardcoded metric lists. Called from `manifest.py:1855-1861` with graceful fallback to hardcoded list when index unavailable.
**Description:** Replace hardcoded expansion pack metric lists with
capability-derived metric discovery.

**Acceptance criteria:**
- The beaver metrics list in `manifest.py` (currently hardcoded as
  `_beaver_metrics = ["startd8_active_sessions", ...]`) is replaced with
  a lookup from the capability index or from a configuration file.
- The mechanism: load `contextcore.agent.yaml`, find capabilities with
  `category: query` that have `outputs` containing metric definitions,
  and collect their metric names.
- If the capability index is not available, fall back to the current
  hardcoded list (no regression).
- Future expansion packs automatically surface their metrics when their
  capabilities are added to the index — no code change required.

**Affected files:**
- `src/contextcore/cli/manifest.py` — beaver metrics section

---

### REQ-CAP-008: Capability-aware question generation in `init-from-plan`

**Priority:** P3
**Status:** **Implemented** — `infer_init_from_plan()` generates gap-analysis questions when major capability categories (contracts, A2A, handoffs) have zero matches. Source `"capability_index:gap_analysis"` at line 833.
**Description:** When `init-from-plan` generates guidance questions, supplement
the text-extracted questions (lines ending with `?`) with capability-coverage
questions derived from gaps between the plan's domain and available capabilities.

**Acceptance criteria:**
- After capability matching (REQ-CAP-003), if important capability categories
  have zero matches, generate a guidance question:
  - If no `contextcore.contract.*` capabilities matched: add question
    "Which context propagation contracts are needed for this project's
    boundary validation?"
  - If no `contextcore.a2a.*` capabilities matched: add question
    "Will this project require A2A governance gates for pipeline exports?"
  - If no `contextcore.handoff.*` capabilities matched: add question
    "Does this project involve agent-to-agent handoffs that need typed
    contracts?"
- Generated questions have:
  - `id`: `Q-CAP-{N}`
  - `status`: `"open"`
  - `priority`: `"medium"`
  - `source`: `"capability_gap_analysis"`
- Maximum 3 capability-derived questions (avoid noise).
- If all major categories have matches, no questions are generated.

**Affected files:**
- `src/contextcore/cli/init_from_plan_ops.py` — question generation section

---

### REQ-CAP-009: Run provenance includes capability index version

**Priority:** P2
**Status:** **Implemented** — `manifest.py:2029` passes `capability_index_version` to `build_run_provenance_payload()`. Provenance `inputs` list includes the capability index file entry with version and sha256.
**Description:** When run provenance is emitted (`run-provenance.json`), include
the capability index version as an input fingerprint so that provenance is
traceable to the specific capability index state used during the run.

**Acceptance criteria:**
- `build_run_provenance_payload()` accepts an optional
  `capability_index_version: Optional[str]` parameter.
- When provided, the run provenance `inputs` list includes an entry:
  ```json
  {
    "path": "docs/capability-index/contextcore.agent.yaml",
    "exists": true,
    "version": "1.10.1",
    "sha256": "abc123..."
  }
  ```
- This enables downstream reproducibility: given the same manifest and the
  same capability index version, the export should produce the same output.
- If the capability index was not loaded (not available), the entry is omitted.

**Affected files:**
- `src/contextcore/utils/provenance.py` — `build_run_provenance_payload()`
- `src/contextcore/cli/manifest.py` — export command (pass version)

---

### REQ-CAP-010: Backward compatibility guarantee

**Priority:** P1
**Status:** **Implemented** — All new fields (`capability_context`, `design_principles` in guidance, `matched_capabilities` in report) are additive. Commands produce identical output when capability index is absent. Existing tests pass without modification.
**Description:** All changes to init and export commands must be backward
compatible. Existing consumers of `onboarding-metadata.json`,
`run-provenance.json`, and generated manifests must continue to work.

**Acceptance criteria:**
- New fields (`capability_context`, `design_principles` in guidance,
  `matched_capabilities` in report) are additive — they do not modify
  existing field schemas.
- If the capability index directory does not exist, all commands produce
  identical output to the current behavior (zero behavioral change).
- The `guidance.constraints` and `guidance.preferences` fields, which were
  previously always empty in `manifest init`, now have values. This is
  additive (empty list → populated list) and does not break consumers that
  read these fields.
- The onboarding metadata `version` field is NOT bumped — `capability_context`
  is a new optional field. The `schema_version` field (if present) is bumped
  from its current value to indicate the additive change.
- Existing tests continue to pass without modification.

**Affected files:**
- All files affected by REQ-CAP-001 through REQ-CAP-009

---

## Integration Points

### With REQ-CID-001 through REQ-CID-012

This requirements document depends on the capability index enhancements:
- REQ-CID-001 (design_principles section) → REQ-CAP-002, REQ-CAP-003, REQ-CAP-006
- REQ-CID-002 (patterns section) → REQ-CAP-002, REQ-CAP-003
- REQ-CID-011 (contract capabilities) → REQ-CAP-005, REQ-CAP-008
- REQ-CID-012 (A2A governance capabilities) → REQ-CAP-005, REQ-CAP-008

If the capability index enhancements are not yet implemented (no
`design_principles` or `patterns` sections in the YAML), the loader
(REQ-CAP-001) returns empty lists for those sections. This means
REQ-CAP-002 through REQ-CAP-009 gracefully degrade to current behavior.

### With MANIFEST_EXPORT_REQUIREMENTS.md

REQ-CAP-005 and REQ-CAP-006 extend the onboarding metadata schema defined
in that document. The new `capability_context` field should be added to
the "Optional Fields" table in `ONBOARDING_METADATA_SCHEMA.md`.

### With A2A Governance Gates

REQ-CAP-005 adds capability context that Gate 1 (`a2a-check-pipeline`) can
optionally validate. This is a future enhancement — Gate 1 currently does
not check for capability references.

### With init-from-plan inference report

REQ-CAP-003 extends the inference report with `matched_capabilities`. This
field is informational — it does not affect the quality gate threshold
(core_inferred_count >= 3) since capability matching is supplementary to
the core field inference.

---

## Test Requirements

### Unit Tests

| Test | Validates | Priority |
|------|-----------|----------|
| `test_capability_index_loads` | Loader parses agent.yaml with design_principles and patterns | P1 |
| `test_capability_index_empty_dir` | Loader returns empty index for nonexistent directory | P1 |
| `test_capability_index_no_principles` | Loader handles YAML without design_principles gracefully | P1 |
| `test_match_triggers_finds_capability` | Trigger matching returns correct capabilities | P1 |
| `test_match_triggers_no_match` | Trigger matching returns empty list for unrelated text | P1 |
| `test_match_principles_for_capabilities` | Principle lookup returns principles for given capability IDs | P1 |
| `test_init_injects_constraints` | manifest init populates guidance.constraints from principles | P1 |
| `test_init_injects_preferences` | manifest init populates guidance.preferences from patterns | P1 |
| `test_init_no_index_graceful` | manifest init produces current template when index absent | P1 |
| `test_infer_matches_capabilities` | init-from-plan matches capabilities from plan text | P1 |
| `test_infer_records_capability_inferences` | Inference report includes matched_capabilities | P1 |
| `test_infer_adds_readiness_check` | Readiness assessment includes capability_coverage check | P1 |
| `test_infer_no_index_unchanged` | init-from-plan output unchanged when index absent | P1 |
| `test_export_capability_context` | onboarding-metadata.json includes capability_context | P1 |
| `test_export_no_index_graceful` | onboarding-metadata.json unchanged when index absent | P1 |
| `test_export_guidance_principles` | Guidance section includes design_principles | P2 |
| `test_provenance_includes_index_version` | run-provenance.json includes capability index input | P2 |
| `test_question_generation_gaps` | Capability gap questions generated for missing categories | P3 |
| `test_question_generation_no_gaps` | No capability questions when all categories matched | P3 |

### Integration Tests

| Test | Validates | Priority |
|------|-----------|----------|
| `test_init_then_export_roundtrip` | Manifest created by init can be exported with capability context | P1 |
| `test_init_from_plan_then_export` | Inferred manifest exports with matched capabilities in context | P1 |
| `test_export_verify_with_capability_context` | `--verify` gate passes with capability_context present | P2 |

---

## Non-Requirements

1. **LLM-based inference.** All capability matching is deterministic keyword/trigger
   lookup. No NLP, no embeddings, no model calls.

2. **Modifying the capability index during init/export.** These commands are
   read-only consumers of the capability index. They do not write to it.

3. **Requiring the capability index.** All commands must work without the index.
   The index is an enhancement, not a dependency.

4. **Changing the export file set.** No new output files are created. The
   `capability_context` is embedded in existing `onboarding-metadata.json`.

5. **Breaking existing gate validation.** Gate 1 (`a2a-check-pipeline`) does
   not require `capability_context`. Adding it is additive — gates that don't
   check for it are unaffected.

6. **Cross-manifest capability resolution.** This iteration only loads the
   ContextCore capability index. Loading startd8-sdk or other ecosystem
   manifests is out of scope.

7. **Restructuring the init template.** The v2 template structure in
   `build_v2_manifest_template()` is not reorganized. New content is injected
   into existing fields (`guidance.constraints`, `guidance.preferences`).

---

## Implementation Dependency Order

```
REQ-CAP-001 (loader utility)
    │
    ├──→ REQ-CAP-002 (init constraints/preferences)
    │
    ├──→ REQ-CAP-003 (init-from-plan inference)
    │       │
    │       └──→ REQ-CAP-004 (gate-derived thresholds)
    │       │
    │       └──→ REQ-CAP-008 (capability-aware questions)
    │
    ├──→ REQ-CAP-005 (export capability_context)
    │       │
    │       └──→ REQ-CAP-006 (export guidance principles)
    │
    ├──→ REQ-CAP-007 (capability-derived metrics)
    │
    └──→ REQ-CAP-009 (provenance index version)

REQ-CAP-010 (backward compat) — applies to all
```

REQ-CAP-001 is the single prerequisite. REQ-CAP-002 through REQ-CAP-009
can be implemented in parallel after the loader exists.
