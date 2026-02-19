# Defense-in-Depth Plan: Artifact Scope Discoverability

**Date:** 2026-02-18
**Author:** Claude Opus 4.6 (AI Agent), reviewed by human
**Status:** Draft — validated against rescan 2026-02-18
**Companion docs:**
- [Investigation](DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md) — root cause analysis
- [Requirements](requirements/REQ_CAPABILITY_INDEX_DISCOVERABILITY.md) — REQ-CID-013 through REQ-CID-021
**Last validated:** 2026-02-18 (rescan of all capability-index YAMLs + generated artifacts)

---

## Why Defense-in-Depth

The [investigation](DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md) identified **seven independent breakpoints** that all reinforced the same false conclusion. A single-layer fix (e.g., only updating the enum docstring) would leave 6 other reinforcement points active. The next agent to search the system would still encounter multiple sources saying "observability only" and would need to stumble on the one fixed source to break free.

**The lesson from prior attempts:** This problem has been "wrestled with many times before." Each prior fix addressed a single layer, but the false ceiling reformed because other layers continued to reinforce it. Defense-in-depth means fixing ALL layers simultaneously so no single unfixed layer can reconstitute the false ceiling.

---

## Pre-Implementation Validation (Rescan 2026-02-18)

A full rescan of `docs/capability-index/` validated the investigation findings against
the current state of all YAMLs and generated artifacts. This narrows the implementation
scope and confirms what's already correct.

### Already correct (reduces implementation scope)

| Layer | Finding | Impact on Plan |
|-------|---------|----------------|
| Layer 2 (Schema) | `artifact_intent` description says "artifacts with semantic roles" — NOT "observability artifacts" | **Reduces scope**: A2A governance descriptions are NOT false ceiling sources. The schema fix in Layer 2 still applies to `artifact-intent.schema.json:5` but the A2A contract schemas are clean. |
| Layer 3 (Capability) | `contextcore.discovery.well_known` already exists with correct triggers ("agent card endpoint", "MCP discovery") | **Already partially implemented**: This capability needs `audiences: ["agent", "human"]` (Phase 3 REQ-CID-019) but the entry itself exists. |
| Layer 3 (Capability) | `agent-card.json` (29K) and `mcp-tools.json` (70K) are well-formed generated files at v1.15.0 | **Proof of production**: The pipeline already produces non-observability artifacts. The false ceiling is descriptive, not productive — the system does the right thing but describes itself incorrectly. |

### Confirmed false ceiling locations (3 total, all fixable)

| # | File | Line | Text | Layer |
|---|------|------|------|-------|
| 1 | `contextcore.benefits.yaml` | 717 | "Users can declare what **observability artifacts** are needed..." | Layer 4 (Benefits) |
| 2 | `contextcore.user.yaml` | 655 | "derives what **observability artifacts** you need" | Layer 4 (Benefits) |
| 3 | `contextcore.user.yaml` | 662 | "complete **observability artifact** plan" | Layer 4 (Benefits) |

All 3 are in Layer 4 (Benefits). No false ceiling locations exist in Layers 2 (Schema)
or 3 (Capability) for A2A descriptions. This means Layer 4 is the highest-priority fix
after Layer 1 (Data).

### Newly discovered issues

1. **Changelog gap (Layer 5 concern):** `contextcore.agent.yaml` is at v1.15.0 but the
   `changelog` section only covers 1.0.0–1.10.1. Five version bumps are unrecorded. This
   undermines the "structured authority" claim — if version history is incomplete, the
   manifest's promise of being a versioned, queryable source of truth is partially hollow.
   **Action:** Add to Layer 5 cross-reference work — backfill changelog or add a note
   about the gap.

2. **Generated artifact framing gap:** `agent-card.json` and `mcp-tools.json` exist as
   FILES but are not described as pipeline artifact TYPES anywhere in the capability index.
   They are produced automatically by the pipeline but invisible to scope discovery. This
   is exactly the pattern REQ-CID-013 (artifact type registry) addresses — once the
   registry lists `agent_card` and `mcp_tools` as onboarding artifact types, the gap closes.

3. **Version discrepancy in requirements doc:** The requirements doc said v1.12.0; the
   actual YAML is at v1.15.0. This has been corrected in the requirements doc.

---

## Six-Layer Defense Architecture

```
Layer 6: TEST        ← Regression prevention (catches future false ceilings)
Layer 5: CROSS-REF   ← Every doc mentioning artifacts references the registry
Layer 4: BENEFITS     ← Value statements describe full scope
Layer 3: CAPABILITY   ← New capability entry + scope boundaries
Layer 2: SCHEMA       ← artifact-intent.schema.json references full taxonomy
Layer 1: DATA         ← Complete artifact type registry in code
```

Each layer independently prevents the false ceiling from reforming. An agent encountering ANY layer gets the correct answer.

---

## Layer 1: Data Layer — Complete Artifact Type Registry in Code

**Requirement:** REQ-CID-018, REQ-CID-016 (code portions)
**Files:** `artifact_manifest.py`, `artifact_conventions.py`, `onboarding.py`, `pipeline_requirements.py`

### Changes

1. **Expand `ArtifactType` enum** to include all 14 types with category comments:
   ```python
   class ArtifactType(str, Enum):
       """Types of artifacts produced by the ContextCore pipeline.

       Organized by category:
       - Observability (8): generated from business metadata
       - Onboarding (4): pipeline-innate, produced automatically
       - Integrity (2): pipeline-innate provenance and traceability

       See docs/reference/pipeline-requirements-onboarding.md for requirements.
       """

       # Observability
       DASHBOARD = "dashboard"
       PROMETHEUS_RULE = "prometheus_rule"
       LOKI_RULE = "loki_rule"
       SLO_DEFINITION = "slo_definition"
       SERVICE_MONITOR = "service_monitor"
       NOTIFICATION_POLICY = "notification_policy"
       RUNBOOK = "runbook"
       ALERT_TEMPLATE = "alert_template"

       # Onboarding (pipeline-innate)
       CAPABILITY_INDEX = "capability_index"
       AGENT_CARD = "agent_card"
       MCP_TOOLS = "mcp_tools"
       ONBOARDING_METADATA = "onboarding_metadata"

       # Integrity (pipeline-innate)
       PROVENANCE = "provenance"
       INGESTION_TRACEABILITY = "ingestion-traceability"
   ```

2. **Add category classification** as class methods or module-level sets:
   ```python
   OBSERVABILITY_TYPES = frozenset({
       ArtifactType.DASHBOARD, ArtifactType.PROMETHEUS_RULE, ...
   })
   ONBOARDING_TYPES = frozenset({
       ArtifactType.CAPABILITY_INDEX, ArtifactType.AGENT_CARD, ...
   })
   INTEGRITY_TYPES = frozenset({
       ArtifactType.PROVENANCE, ArtifactType.INGESTION_TRACEABILITY,
   })
   ```

3. **Update `ARTIFACT_OUTPUT_CONVENTIONS`** in `artifact_conventions.py` with entries
   for `CAPABILITY_INDEX`, `AGENT_CARD`, `MCP_TOOLS`, `ONBOARDING_METADATA`,
   `PROVENANCE`, `INGESTION_TRACEABILITY`. (`CAPABILITY_INDEX` was missing since
   Phase 1 — enum existed but conventions entry was never added.)

4. **Update all four onboarding dicts** in `onboarding.py` with entries for new types:
   - `ARTIFACT_PARAMETER_SOURCES` — add 5 new types (CAPABILITY_INDEX already exists)
   - `ARTIFACT_EXAMPLE_OUTPUTS` — add 5 new types (CAPABILITY_INDEX already exists)
   - `EXPECTED_OUTPUT_CONTRACTS` — add 6 new types including CAPABILITY_INDEX
     (which was missing since Phase 1)
   - `ARTIFACT_PARAMETER_SCHEMA` — add 5 new types (CAPABILITY_INDEX already exists)

5. **Fix module docstring** (`artifact_manifest.py:1-2`) from "Defines required
   observability artifacts" to "Defines required artifacts for the ContextCore pipeline".

6. **Fix `ArtifactManifest` class docstring** (`artifact_manifest.py:489`) from
   "contract for observability artifact generation" to "contract for artifact generation".

7. **Validate `pipeline_requirements.py`** — ensure all `satisfied_by_artifact` values
   are valid `ArtifactType` enum members.

### Why This Layer Matters

The enum is the first thing a code-reading agent examines. If the enum is complete
and its docstring is accurate, the agent gets the correct scope from the code itself.
This is the foundation all other layers reference.

### Verification

- `python3 -c "from contextcore.models.artifact_manifest import ArtifactType; print(len(ArtifactType))"` → 14
- All existing tests pass (backward compatible)
- New test: `test_artifact_type_enum_complete` verifies >= 14 members

---

## Layer 2: Schema Layer — artifact-intent.schema.json

**Requirement:** REQ-CID-015, REQ-CID-016
**Files:** `schemas/contracts/artifact-intent.schema.json`

### Changes

1. **Fix description** (line 5):
   - From: `"Typed declaration of an observability artifact need before generation."`
   - To: `"Typed declaration of an artifact need before generation. Supports observability, onboarding, and integrity artifact categories."`

2. **Add `artifact_category` field** (optional, for documentation):
   ```json
   "artifact_category": {
     "type": "string",
     "enum": ["observability", "onboarding", "integrity"],
     "description": "The category of artifact. Observability artifacts are generated from business metadata. Onboarding and integrity artifacts are pipeline-innate."
   }
   ```

3. **Add cross-reference** in schema description to `pipeline-requirements-onboarding.md`.

### Why This Layer Matters

The schema is the A2A governance contract. If an agent reads the schema to understand
what `ArtifactIntent` declares, it should learn the full scope from the schema alone.
The investigation showed the schema was a key reinforcement point for the false ceiling.

**Rescan note (2026-02-18):** The A2A contract schemas in `contextcore.agent.yaml` are
already clean — `artifact_intent` says "artifacts with semantic roles," NOT "observability
artifacts." The fix here is limited to `artifact-intent.schema.json:5` (the standalone
JSON Schema file), not the YAML capability descriptions.

### Verification

- JSON schema validation still passes for all existing ArtifactIntent payloads
- New test: `test_no_false_ceiling_schema` — description does NOT say "observability" without qualification

---

## Layer 3: Capability Layer — New Entries + Scope Boundaries

**Requirement:** REQ-CID-013, REQ-CID-014
**Files:** `contextcore.agent.yaml`, `_p2_capabilities.yaml`

### Changes

1. **Add `contextcore.meta.artifact_type_registry` capability** (REQ-CID-013):
   - Triggers: "artifact types", "what artifacts", "artifact scope", "artifact categories",
     "pipeline produces", "artifact taxonomy", "beyond observability", "pipeline-innate"
   - Description lists ALL 14 types across 3 categories
   - Cross-references `pipeline-requirements-onboarding.md`

2. **Add `scope_boundaries` section** (REQ-CID-014):
   ```yaml
   scope_boundaries:
     artifact_categories:
       - category: observability
         count: 8
         description: "Generated from business metadata in .contextcore.yaml"
         types: [dashboard, prometheus_rule, slo_definition, service_monitor,
                 loki_rule, notification_policy, runbook, alert_template]
         source: "ArtifactType enum in src/contextcore/models/artifact_manifest.py"
       - category: onboarding
         count: 4
         description: "Pipeline-innate artifacts produced automatically for every project"
         types: [capability_index, agent_card, mcp_tools, onboarding_metadata]
         source: "docs/reference/pipeline-requirements-onboarding.md REQ-CDP-ONB-*"
       - category: integrity
         count: 2
         description: "Pipeline-innate provenance and traceability artifacts"
         types: [provenance, ingestion-traceability]
         source: "docs/reference/pipeline-requirements-onboarding.md REQ-CDP-INT-*"

     pipeline_stages:
       - stage: init
         produces: [".contextcore.yaml"]
       - stage: validate
         produces: ["validation report"]
       - stage: export
         produces: [artifact_manifest, onboarding_metadata, capability_index, provenance]
       - stage: gate_1
         produces: [gate_result]
       - stage: plan_ingestion
         produces: [context_seed, ingestion_traceability]
       - stage: gate_2
         produces: [diagnostic_result]
       - stage: contractor
         consumes: [context_seed]
         produces: ["plan deliverables (application code, Dockerfiles, etc.)"]

     explicit_non_scope:
       - category: "Plan deliverables"
         description: "Application code, Dockerfiles, CI/CD configs, requirements.txt — these are deliverables defined in .contextcore.yaml strategy.tactics, NOT pipeline artifacts"
         note: "Plan deliverables are produced by the CONTRACTOR stage from context seeds, not by the pipeline export stage"
   ```

3. **Position `scope_boundaries` after `patterns`, before `capabilities`** in document
   order so agents encounter it early.

### Why This Layer Matters

The capability index is the primary discovery mechanism. If an agent searching for
"what artifacts exist" can find a capability entry that lists ALL types AND a scope
boundary that categorizes them, the false ceiling cannot form.

**Rescan note (2026-02-18):** `contextcore.discovery.well_known` already exists in the
YAML with triggers "agent card endpoint" and "MCP discovery". The generated artifacts
(`agent-card.json` at 29K and `mcp-tools.json` at 70K) already exist as well-formed
files — proving the pipeline produces non-observability artifacts. The gap is that no
capability describes `agent_card` and `mcp_tools` as artifact TYPES. The new
`artifact_type_registry` capability (Change #1 above) closes this gap by listing them
explicitly in the onboarding category.

### Verification

- `test_scope_artifact_types_complete` — trigger search finds the registry capability
- `test_scope_artifact_categories` — scope_boundaries has >= 3 categories
- `test_scope_boundary_present` — scope_boundaries section exists

---

## Layer 4: Benefits Layer — Value Statements Describe Full Scope

**Requirement:** REQ-CID-016
**Files:** `contextcore.benefits.yaml`

### Changes

1. **Fix `pipeline.contract_first_planning`** (line 717):
   - From: "Users can declare what **observability artifacts** are needed..."
   - To: "Users can declare what **artifacts** are needed from business metadata.
     The pipeline produces artifacts in three categories: observability (dashboards,
     alerts, SLOs), onboarding (capability index, agent card, MCP tools), and
     integrity (provenance, traceability)."

2. **Fix `pipeline.manifest_to_artifacts`** in `contextcore.user.yaml` (line ~655):
   - From: "derives what observability artifacts you need"
   - To: "derives what artifacts you need—observability (dashboards, alerts),
     onboarding (capability index, agent card), and integrity (provenance)"

3. **Add a new benefit entry** `pipeline.artifact_taxonomy`:
   ```yaml
   - capability_id: pipeline.artifact_taxonomy
     category: action
     summary: "Pipeline produces artifacts in three categories beyond just observability"
     description:
       human: |
         ContextCore doesn't just generate observability dashboards and alerts.
         The pipeline automatically produces onboarding artifacts (capability index,
         agent card, MCP tools) and integrity artifacts (provenance, traceability)
         for every project. These pipeline-innate artifacts enable agent discovery,
         tool integration, and audit trails without manual configuration.
     triggers:
       - "artifact categories"
       - "beyond observability"
       - "what does the pipeline produce"
       - "pipeline-innate"
   ```

### Why This Layer Matters

Benefits YAML is the user-facing and GTM-facing view. If benefits descriptions
accurately state the full scope, users (human or agent) reading the benefits
will learn the correct boundary before diving into capabilities.

**Rescan note (2026-02-18):** These 3 false ceiling locations (benefits.yaml:717,
user.yaml:655, user.yaml:662) are the ONLY remaining false ceiling sources across
all capability-index files. The A2A governance descriptions in agent.yaml are
scope-accurate. This makes Layer 4 the highest-leverage fix — correcting 3 lines
eliminates all remaining false ceiling reinforcement.

### Verification

- Grep for "observability artifact" in benefits YAML returns 0 unqualified matches
- New benefit `pipeline.artifact_taxonomy` is discoverable via "artifact categories" trigger

---

## Layer 5: Cross-Reference Layer — Every Artifact-Mentioning Doc Links to Registry

**Requirement:** REQ-CID-015
**Files:** Multiple (see table below)

### Changes

| File | Current State | Fix |
|------|--------------|-----|
| `artifact_manifest.py:28` | No cross-ref | Add: "See pipeline-requirements-onboarding.md for complete taxonomy" |
| `MANIFEST_EXPORT_REQUIREMENTS.md:99` | "8 artifact types" | Add note: "Additional categories in pipeline-requirements-onboarding.md" |
| `ARTIFACT_MANIFEST_CONTRACT.md:92` | Table with no category headers | Add category row headers (Observability / Onboarding / Integrity) |
| `EXPORT_PIPELINE_IMPLEMENTATION_SUMMARY.md:70` | "all 8 artifact types" | Fix: "all 8 observability artifact types (additional categories in pipeline-requirements-onboarding.md)" |
| `onboarding.py:1-13` | Dashboard-focused docstring | Add: "Plus onboarding and integrity artifacts per pipeline-requirements-onboarding.md" |
| `pipeline-requirements-onboarding.md` | Zero outbound cross-refs | Add "Referenced By" section listing all files that should cite it |
| `contextcore.agent.yaml` | No ref to pipeline-requirements-onboarding.md | `artifact_type_registry` capability cross-references it |
| `contextcore.agent.yaml` changelog | Versions 1.11.0–1.15.0 missing | Backfill changelog entries or add gap note with summary of changes |

### Why This Layer Matters

Cross-references are the connective tissue. The investigation proved that a document
with zero inbound references is effectively invisible. Even if every other layer is
fixed, a future document could create a new false ceiling if it doesn't link to the
registry. This layer ensures connectivity.

### Verification

- `test_no_orphaned_requirements` — `pipeline-requirements-onboarding.md` has >= 1 inbound reference
- `test_cross_reference_coverage` — every `REQ-CDP-*` doc has >= 1 inbound capability index cross-reference
- Manual audit: grep for `pipeline-requirements-onboarding` across all `.md` and `.py` files returns >= 5 matches

---

## Layer 6: Test Layer — Regression Prevention

**Requirement:** REQ-CID-017
**Files:** `tests/test_capability_discoverability.py`, `capability_validator.py`

### Changes

1. **Scope discovery test suite** — 11 tests as specified in REQ-CID-017.

2. **Anti-false-ceiling lint rule** — a validation check that scans for patterns like:
   - `"[0-9]+ artifact types"` without nearby category qualification
   - `"observability artifact"` in docstrings/descriptions without "also" or "including"
   - ArtifactType enum with fewer members than `pipeline-requirements-onboarding.md` defines

3. **Periodic scope audit** — a test that simulates an agent's search path:
   ```python
   def test_agent_scope_search_simulation():
       """Simulate an agent searching for artifact scope.

       This test follows the same search path that triggered the
       2026-02-18 discoverability failure: start from triggers,
       read descriptions, check scope boundaries, and verify that
       the complete artifact taxonomy is discoverable within 3 hops.
       """
       manifest = load_capability_manifest()

       # Step 1: Search triggers for "artifact type"
       matches = search_triggers(manifest, "artifact type")
       assert len(matches) >= 1, "No capability found for 'artifact type'"

       # Step 2: Read the matched capability's description
       registry = find_capability(manifest, "contextcore.meta.artifact_type_registry")
       assert registry is not None

       # Step 3: Verify description mentions all 3 categories
       desc = registry.description.agent
       assert "observability" in desc.lower()
       assert "onboarding" in desc.lower()
       assert "integrity" in desc.lower()

       # Step 4: Verify scope_boundaries exists and is complete
       boundaries = manifest.get("scope_boundaries", {})
       categories = boundaries.get("artifact_categories", [])
       assert len(categories) >= 3
   ```

### Why This Layer Matters

Without tests, any future change could silently reintroduce a false ceiling. The
investigation showed that the false ceiling was created incrementally — each document
was correct when written but collectively they formed an incorrect boundary. Tests
prevent this regression by continuously validating the scope is discoverable.

### Verification

- All 11 scope tests pass
- Anti-false-ceiling lint runs in CI (or as part of `contextcore capability-index validate`)
- Agent simulation test passes

---

## Implementation Order

The layers have a dependency structure:

```
Layer 1 (Data) ──────────────────────────────┐
    │                                         │
    ▼                                         │
Layer 2 (Schema) ─── references Layer 1       │
    │                                         │
    ▼                                         │
Layer 3 (Capability) ─── references Layer 1   │
    │                                         │
    ▼                                         │
Layer 4 (Benefits) ─── uses Layer 3 language  │
    │                                         │
    ▼                                         │
Layer 5 (Cross-Ref) ─── links all layers      │
    │                                         │
    ▼                                         │
Layer 6 (Tests) ─── validates all layers ─────┘
```

**Recommended implementation order:**

| Phase | Layers | Est. Changes | Rationale |
|-------|--------|-------------|-----------|
| Phase 2a | Layer 1 + Layer 2 | ~135 lines code | Foundation — enum, category sets, 4 onboarding dicts, conventions, and schema must be correct first |
| Phase 2b | Layer 3 + Layer 4 | ~150 lines YAML | Capability index and benefits depend on Layer 1 |
| Phase 2c | Layer 5 | ~75 lines across 8 files | Cross-references depend on Layers 1-4; includes changelog backfill |
| Phase 2d | Layer 6 | ~200 lines tests | Tests validate all other layers |

Total estimated: ~460 lines across ~15 files.

---

## Success Criteria

The defense-in-depth is successful when:

1. **An agent searching for "what artifact types exist" finds the complete taxonomy
   within 2 hops** (trigger match → capability description → done).

2. **An agent that reads ONLY the enum docstring gets the correct scope** (not
   "observability only").

3. **An agent that reads ONLY the schema gets the correct scope** (not
   "observability artifact need").

4. **An agent that reads ONLY the benefits gets the correct scope** (not
   "observability artifacts").

5. **No document presents a subset as complete** without noting additional categories.

6. **All 11 scope discovery tests pass** continuously.

7. **The 12:1:0 failure ratio is eliminated** — the answer is now findable from
   multiple independent paths, not just one isolated document.

Target ratio: **6+ sources confirming correct boundary : 0 sources with false ceiling : 10+ cross-references connecting them**

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Backward compatibility break from enum expansion | Low | High | New enum values are additive; existing code uses `.value` strings |
| Schema change breaks existing ArtifactIntent payloads | Low | Medium | `artifact_category` field is optional; description change is non-breaking |
| Scope boundaries section increases YAML parsing time | Very Low | Low | Section is small (~30 lines); capability loader already handles 115K |
| Tests false-positive on partial implementations | Medium | Low | Tests are ordered by Layer dependency — Layer 6 only runs after 1-5 |
| New false ceiling forms in a future document | Medium | High | Layer 6 lint rule catches the pattern; periodic audit recommended |
| Changelog gap undermines structured authority claim | Medium | Medium | Backfill 1.11.0–1.15.0 entries during Layer 5 implementation; add changelog completeness check to Layer 6 tests |
| Generated artifacts not regenerated after Phase 2 fixes | Low | High | MCP/A2A regeneration is Phase 3 work; ensure Phase 2 changes don't break existing agent-card.json/mcp-tools.json |

---

## Connection to Broader ContextCore Strategy

This plan directly supports the value proposition in `contextcore.meta.structured_authority` (REQ-CID-006):

> "Structured, versioned, queryable capability manifests replace ambiguous documents as the source of truth."

Until this defense-in-depth is implemented, the structured authority claim is **aspirational** for artifact scope. The fragmented definitions across 9 sources, with only 1 containing the complete picture, means documents are still the de facto source of truth — and they are telling the wrong story.

After implementation, the artifact type taxonomy will be:
- **Structured** — enum with category classification
- **Versioned** — manifest version bumped
- **Queryable** — triggers, scope boundaries, and capability descriptions all lead to the answer
- **Authoritative** — no document presents a contradicting partial view

This is what "structured authority" looks like for artifact scope.

**Rescan insight (2026-02-18):** The irony confirmed by the rescan is that `agent-card.json`
and `mcp-tools.json` — the very artifacts that PROVE ContextCore produces non-observability
outputs — sit in the `docs/capability-index/` directory alongside the YAML that fails to
describe them as artifact types. The pipeline does the right thing; the description layer
says the wrong thing. This is a description-production gap, not a production failure. The
fix is entirely in Layer 1 (enum), Layer 3 (capability registry), and Layer 4 (benefits
language). No generation infrastructure needs to change for Phase 2.

---

## Appendix: Files Changed by Layer

| Layer | File | Change Type | Est. Lines |
|-------|------|------------|-----------|
| 1 | `src/contextcore/models/artifact_manifest.py` | Edit (enum + docstrings + category sets) | 30 |
| 1 | `src/contextcore/utils/artifact_conventions.py` | Edit (add 6 entries incl. CAPABILITY_INDEX) | 35 |
| 1 | `src/contextcore/utils/onboarding.py` | Edit (add entries across 4 dicts) | 60 |
| 1 | `src/contextcore/utils/pipeline_requirements.py` | Validate only | 0 |
| 2 | `schemas/contracts/artifact-intent.schema.json` | Edit (description + field) | 10 |
| 3 | `docs/capability-index/contextcore.agent.yaml` | Edit (scope_boundaries) | 50 |
| 3 | `docs/capability-index/_p2_capabilities.yaml` | Edit (new capability) | 40 |
| 4 | `docs/capability-index/contextcore.benefits.yaml` | Edit (fix scope language) | 10 |
| 4 | `docs/capability-index/contextcore.user.yaml` | Edit (fix scope language) | 5 |
| 5 | `docs/design/MANIFEST_EXPORT_REQUIREMENTS.md` | Edit (add note) | 3 |
| 5 | `docs/design/ARTIFACT_MANIFEST_CONTRACT.md` | Edit (add category headers) | 5 |
| 5 | `docs/plans/EXPORT_PIPELINE_IMPLEMENTATION_SUMMARY.md` | Edit (fix count) | 2 |
| 5 | `docs/reference/pipeline-requirements-onboarding.md` | Edit (add cross-refs) | 10 |
| 5 | `docs/capability-index/contextcore.agent.yaml` changelog | Edit (backfill 1.11.0–1.15.0) | 25 |
| 6 | `tests/test_capability_discoverability.py` | New | 200 |
| 6 | `tests/test_artifact_types.py` | New | 50 |
| 6 | `src/contextcore/utils/capability_validator.py` | Edit (scope rules) | 30 |
| — | **Total** | | **~565** |
