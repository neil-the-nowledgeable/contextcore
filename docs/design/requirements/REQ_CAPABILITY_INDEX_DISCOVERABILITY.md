# Requirements: Capability Index Discoverability Enhancements

**Status:** Phase 1 implemented (REQ-CID-001–012), Phase 2 in progress (REQ-CID-013–018), Phase 3 defined (REQ-CID-019–021)
**Date:** 2026-02-16 (Phase 1 requirements), 2026-02-17 (Phase 1 implementation), 2026-02-18 (Phase 2 + Phase 3 requirements)
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (high value, low complexity)
**Companion docs:**
- [Capability Index Gap Analysis](../../capability-index/CAPABILITY_INDEX_GAP_ANALYSIS.md)
- [Discoverability Failure Investigation (2026-02-18)](../DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md)
**Capability manifests affected:**
- `docs/capability-index/contextcore.agent.yaml`
- `docs/capability-index/contextcore.benefits.yaml`
- `docs/capability-index/contextcore.user.yaml`
**Estimated implementation:** Phase 1: ~200 YAML lines (done) | Phase 2: ~300 lines + code changes | Phase 3: ~50 YAML lines + artifact regeneration

---

## Implementation Status

### Phase 1 (2026-02-17): Capability Discovery — All Implemented

All 12 Phase 1 requirements (P1 + P2 + P3) have been implemented via programmatic capability index generation tooling:

| REQ ID | Priority | Status | Implementation |
|--------|----------|--------|----------------|
| REQ-CID-001 | P1 | **Implemented** | 9 design principles in `contextcore.agent.yaml` via `_principles.yaml` sidecar |
| REQ-CID-002 | P1 | **Implemented** | 6 communication patterns in `contextcore.agent.yaml` via `_patterns.yaml` sidecar |
| REQ-CID-003 | P1 | **Implemented** | 10 pipeline triggers across 4 capabilities via `_trigger_enrichments.yaml` |
| REQ-CID-004 | P2 | **Implemented** | `contextcore.pipeline.typed_handoff` in `_p2_capabilities.yaml` sidecar |
| REQ-CID-005 | P2 | **Implemented** | `contextcore.contract.expected_output` in `_p2_capabilities.yaml` sidecar |
| REQ-CID-006 | P2 | **Implemented** | `contextcore.meta.structured_authority` benefit in `contextcore.benefits.yaml` |
| REQ-CID-007 | P1 | **Implemented** | Pipeline communication primitives cross-reference in Export Pipeline Analysis Guide |
| REQ-CID-008 | P3 | **Implemented** | `discovery_paths` field on Capability dataclass + `_discovery_paths.yaml` sidecar |
| REQ-CID-009 | P3 | **Implemented** | Existing `/capability-index` skill satisfies navigation requirement |
| REQ-CID-010 | P1 | **Implemented** | All pre-existing capability IDs preserved; version bumped 1.10.1→1.12.0 |
| REQ-CID-011 | P1 | **Implemented** | 7 `contextcore.contract.*` capabilities scanned from `src/contextcore/contracts/` |
| REQ-CID-012 | P1 | **Implemented** | 6 A2A governance capabilities (4 contracts + 2 gates) |

### Phase 2 (2026-02-18): Scope Discovery — Requirements Defined

Triggered by [Discoverability Failure Investigation](../DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md): an AI agent exhaustively searched the capability index (12 independent sources) and concluded — incorrectly with HIGH confidence — that ContextCore's artifact scope is limited to observability artifacts. The correct answer (agent_card, mcp_tools, onboarding_metadata, provenance, ingestion-traceability) was found only after human intervention.

**Failure class:** Scope discovery failure — qualitatively different from Phase 1's capability discovery failure. Phase 1 fixed "agent can't find the right capability." Phase 2 fixes "agent can't determine the complete boundary of what the system produces."

| REQ ID | Priority | Status | Summary |
|--------|----------|--------|---------|
| REQ-CID-013 | P1 | **Pending** | Unified artifact type registry as first-class capability |
| REQ-CID-014 | P1 | **Pending** | Scope boundary declaration in capability index |
| REQ-CID-015 | P1 | **Pending** | Cross-reference enforcement between requirements and capability index |
| REQ-CID-016 | P1 | **Pending** | Anti-false-ceiling validation (subset must not present as complete) |
| REQ-CID-017 | P1 | **Pending** | Scope-question discoverability tests |
| REQ-CID-018 | P1 | **Pending** | ArtifactType enum consolidation with all pipeline artifact types |

### Phase 3 (2026-02-18): MCP/A2A Export Integrity — Requirements Defined

Triggered by [MCP and A2A Tools Documentation Audit](../capability-index/MCP_A2A_TOOLS_DOCUMENTATION_AUDIT.md): audit validated that all 34 exported capabilities are correctly documented in `mcp-tools.json` and `agent-card.json`, but discovered that 15 capabilities added by Phase 1 are **silently excluded** from export because they lack `audiences: ["agent"]`. Additionally, the manifest lacks A2A deployment metadata and discovery endpoint documentation.

**Failure class:** Export coverage gap — qualitatively different from Phase 1's capability discovery and Phase 2's scope discovery. Phase 3 fixes "capabilities exist in the manifest but are invisible to MCP/A2A consumers."

| REQ ID | Priority | Status | Summary |
|--------|----------|--------|---------|
| REQ-CID-019 | P1 | **Pending** | MCP/A2A export coverage for Phase 1+ capabilities (15 missing) |
| REQ-CID-020 | P2 | **Pending** | A2A manifest section (url, authentication, provider) |
| REQ-CID-021 | P2 | **Pending** | Discovery endpoint documentation in capability index |

### Tooling implemented

| Module | Purpose |
|--------|---------|
| `src/contextcore/utils/capability_scanner.py` | Scans `contracts/` directories to discover L1-L7 and A2A capabilities |
| `src/contextcore/utils/capability_builder.py` | Merges scanned + hand-authored + sidecar content, bumps version |
| `src/contextcore/utils/capability_validator.py` | Schema validation + REQ-CID acceptance criteria (220/230 checks) |
| `src/contextcore/cli/capability_index.py` | CLI: `contextcore capability-index build \| validate \| diff` |
| `docs/capability-index/_principles.yaml` | 9 design principles (REQ-CID-001) |
| `docs/capability-index/_patterns.yaml` | 6 communication patterns (REQ-CID-002) |
| `docs/capability-index/_trigger_enrichments.yaml` | Pipeline triggers for 4 capabilities (REQ-CID-003) |
| `docs/capability-index/_p2_capabilities.yaml` | P2 capabilities: typed_handoff + expected_output (REQ-CID-004/005) |
| `docs/capability-index/_discovery_paths.yaml` | Discovery paths for 7 capabilities (REQ-CID-008) |

### Pipeline integration

- `CAPABILITY_INDEX` added to `ArtifactType` enum in `src/contextcore/models/artifact_manifest.py`
- Onboarding metadata enriched for `capability_index` artifact type in `src/contextcore/utils/onboarding.py`
- 84 unit tests across scanner (19), builder (17), validator (32), existing loader (16)

### Manifest state

- Version: **1.12.0** (from 1.10.1)
- Capabilities: **47** (34 original + 13 added by scanner)
- Design principles: **9**
- Communication patterns: **6**
- Trigger enrichments: **10** new triggers across 4 capabilities
- Validation: 220/230 checks pass (10 warnings from pre-existing categories/maturities)

---

## Problem Statement

ContextCore's capability index (`contextcore.agent.yaml`, v1.10.1, 27+
capabilities) thoroughly documents A2A communication **mechanics** — handoff
initiation, content models, server/client patterns, task adapters. But when
designing the Coyote modular pipeline, the A2A typed communication primitives
(Part, Message, Handoff, ExpectedOutput) were the exact solution needed but
were **NOT discovered** during initial plan analysis. They were only found via
manual code exploration.

This is a **discoverability failure, not a documentation failure.** The content
exists; it is not discoverable from the pipeline/workflow entry point.

Five specific gaps were identified in the
[gap analysis](../../capability-index/CAPABILITY_INDEX_GAP_ANALYSIS.md):

1. **The "Typed Over Prose" design principle is invisible.** The most important
   meta-principle — use typed structured data instead of natural language
   parsing — is implicit in every capability's schema but never explicitly
   stated. Agents designing new workflows cannot discover the governing
   principle.

2. **No pipeline communication capability.** The index models A2A as
   agent-to-agent (separate agents over HTTP/storage). There is no capability
   for stage-to-stage communication within a single pipeline, which is the
   pattern Coyote and any multi-step workflow needs. The primitives are the
   same (Part, ExpectedOutput), but the use case is absent.

3. **The value proposition of structured queries over documents is not
   articulated.** The capability index IS the value proposition (structured,
   versioned, queryable), but it does not describe itself as such. An agent
   designing a communication pattern cannot discover "why should I use
   structured queries instead of documents?"

4. **ExpectedOutput is buried.** `ExpectedOutput` is arguably the most
   important primitive for pipeline communication, but it is a sub-schema
   inside `handoff.initiate`'s input definition. An agent searching for "how
   do I define output contracts" will not find it.

5. **No pattern-level organization.** The index organizes by function
   (action, query, transform, integration) but not by **communication
   pattern**. An agent trying to answer "how should agents communicate?" must
   mentally assemble the pattern from scattered capabilities.

**Root causes** (from gap analysis section 3):

| Root Cause | Impact |
|------------|--------|
| Trigger mismatch | "pipeline", "stage", "workflow" don't match A2A triggers |
| Category mismatch | Pipeline communication is not an explicit category |
| Naming mismatch | "handoff" implies inter-agent, not intra-pipeline |
| No cross-reference | Pipeline analysis docs don't point to A2A primitives |

**The CS parallel:** This is the **feature interaction problem** from software
engineering (Zave, 1993). Individual capabilities are correct in isolation, but
their composition into patterns is not documented, so agents cannot discover
how capabilities interact to solve higher-level problems.

---

## Requirements

### REQ-CID-001: Design principles section in agent capability manifest

**Priority:** P1
**Description:** Add a top-level `design_principles` section to
`contextcore.agent.yaml` that declares the governing principles for capability
composition. The first and most important principle is "typed over prose" — all
inter-agent data exchange uses typed schemas, not natural language parsing.

**Acceptance criteria:**
- `contextcore.agent.yaml` has a `design_principles` key at the top level
  (after `labels`, before `capabilities`).
- At least **nine** principle entries:
  1. `typed_over_prose` — All inter-agent data exchange uses typed schemas,
     not natural language parsing.
  2. `prescriptive_over_descriptive` — Declare what *should* happen and
     verify it did, rather than recording what happened after the fact.
     (Source: [CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md](../../design/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md))
  3. `design_time_over_runtime` — Catch context correctness issues when the
     pipeline is designed, not when it fails in production. YAML contracts
     are reviewed in PRs alongside code.
  4. `graceful_degradation` — Not all context fields are equally critical.
     The severity model (BLOCKING/WARNING/ADVISORY) mirrors how real systems
     work: some fields are load-bearing, some are optimization hints.
  5. `composable_primitives` — Every contract layer uses the same four
     primitives (Declare, Validate, Track, Emit). New layers are new contract
     types plugged into the same framework, not new frameworks.
  6. `opt_in_over_mandatory` — Every layer is opt-in. Existing systems work
     unchanged. Contracts add verification on top without replacing existing
     validation.
  7. `observable_contracts` — The contract system itself emits OTel events.
     You can build a dashboard showing contract health. The meta-observability
     makes the contract system trustworthy.
  8. `framework_agnostic_contracts` — Contracts declare what must be true
     about context propagation, not how frameworks achieve it. ContextCore
     works with LangGraph, AutoGen, CrewAI, or any runtime — the contracts
     are runtime-independent governance.
     (Source: [CONTEXT_CORRECTNESS_EXTENSIONS.md](../../design/CONTEXT_CORRECTNESS_EXTENSIONS.md))
  9. `governance_metadata_over_runtime` — ContextCore adds governance
     metadata (contracts, provenance, lineage) on top of whatever runtime
     metadata the framework already produces. It does not duplicate
     framework-native telemetry.
     (Source: [CONTEXT_CORRECTNESS_EXTENSIONS.md](../../design/CONTEXT_CORRECTNESS_EXTENSIONS.md))
- Each principle entry has: `id` (str), `principle` (str, one-sentence),
  `rationale` (str, multi-line), `anti_patterns` (list[str]),
  `applies_to` (list[str] of capability_ids).
- Principles are discoverable via the existing emission pipeline — when
  capabilities are emitted as OTel spans, principles are emitted as span
  attributes or a separate span.
- An agent reading the manifest encounters principles BEFORE individual
  capabilities (document ordering matters for LLM context).
- Principles 2-7 reference the defense-in-depth contract system capabilities
  (REQ-CID-011) in their `applies_to` lists.
- Principles 8-9 reference A2A governance capabilities (REQ-CID-012) and
  contract system capabilities (REQ-CID-011) in their `applies_to` lists.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`

---

### REQ-CID-002: Communication patterns section in agent capability manifest

**Priority:** P1
**Description:** Add a top-level `patterns` section to
`contextcore.agent.yaml` that composes individual capabilities into named
communication patterns. Each pattern has a name, summary, the list of
capabilities it composes, and an anti-pattern it replaces.

**Acceptance criteria:**
- `contextcore.agent.yaml` has a `patterns` key at the top level (after
  `design_principles`, before `capabilities`).
- At least **five** pattern entries:
  - `typed_handoff`: ExpectedOutput -> Part-based output -> validation.
  - `insight_accumulation`: Emit insights -> query accumulated knowledge ->
    compound over time.
  - `constraint_gated`: Read constraints -> apply constraints -> emit decisions.
  - `pipeline_communication`: Stage declares contract -> produces typed output
    -> gate validates.
  - `contract_validation`: Declare contracts in YAML -> Validate at boundaries
    -> Track provenance as context flows -> Emit OTel events for violations.
    This is the 4-primitive pattern (Declare, Validate, Track, Emit) shared
    across all 7 defense-in-depth contract layers. Anti-pattern: "Propagate
    context and hope for the best without boundary checking." Capabilities:
    all 7 `contextcore.contract.*` capabilities from REQ-CID-011.
- Each pattern entry has: `pattern_id` (str), `name` (str), `summary` (str),
  `capabilities` (list[str] of capability_ids), `anti_pattern` (str).
- Patterns are queryable: an agent can look up a pattern by name to find
  which capabilities to use.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`

---

### REQ-CID-003: Pipeline-specific triggers on A2A capabilities

**Priority:** P1
**Description:** Add pipeline-oriented trigger keywords to existing A2A
capabilities so that agents searching from a pipeline/workflow context
discover the same primitives that A2A-oriented agents find.

**Acceptance criteria:**
- `contextcore.handoff.initiate` gains triggers: `"stage output contract"`,
  `"pipeline stage handoff"`, `"typed stage output"`.
- `contextcore.a2a.content_model` gains triggers: `"pipeline data model"`,
  `"stage output type"`, `"typed pipeline message"`.
- `contextcore.code_generation.contract` gains triggers:
  `"pipeline output contract"`, `"generation size limit"`.
- `contextcore.handoff.receive` gains triggers: `"stage input validation"`,
  `"pipeline stage input"`.
- Existing triggers are NOT removed — new triggers are appended.
- After the change, searching for "pipeline" in any trigger field matches
  at least 4 capabilities.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`

---

### REQ-CID-004: Pipeline typed handoff capability entry

**Priority:** P2
**Description:** Add a new capability `contextcore.pipeline.typed_handoff`
that bridges A2A primitives to pipeline-internal stage-to-stage communication.
This capability does not implement new code — it documents the pattern of
using Part, ExpectedOutput, and validation gates within a sequential pipeline.

**Acceptance criteria:**
- New capability entry with `capability_id: contextcore.pipeline.typed_handoff`.
- `category: transform`, `maturity: beta`.
- `description.agent` explains: use A2A primitives (Part, ExpectedOutput)
  for intra-pipeline stage communication; stages declare ExpectedOutput
  contracts; stage outputs use Part objects; gates validate at boundaries.
- `description.human` explains the same in user-friendly language.
- `delivers_benefit` references the "typed over prose" benefit.
- `triggers` include: `"pipeline communication"`, `"stage contract"`,
  `"intra-pipeline handoff"`, `"typed stage output"`, `"stage-to-stage"`.
- `inputs` and `outputs` schemas reference existing Part and ExpectedOutput
  types (not new types).

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`

---

### REQ-CID-005: ExpectedOutput promoted to discoverable capability

**Priority:** P2
**Description:** Either promote `ExpectedOutput` to its own capability entry
or add dedicated triggers and cross-references so it is discoverable
independently of `handoff.initiate`.

**Acceptance criteria:**
- One of:
  - (Option A) New capability `contextcore.contract.expected_output` with
    `category: transform`, dedicated triggers (`"output contract"`,
    `"expected output"`, `"required fields"`, `"completeness markers"`,
    `"output schema"`, `"typed output"`), and a schema definition.
  - (Option B) `contextcore.handoff.initiate` gains a `cross_references`
    field listing `contextcore.contract.expected_output` as an alias, AND
    the triggers `"output contract"`, `"expected output"`,
    `"completeness markers"` are added to `handoff.initiate`.
- After the change, searching for "output contract" or "expected output"
  in triggers finds at least one capability.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`

---

### REQ-CID-006: Structured authority meta-capability

**Priority:** P2
**Description:** Add a capability or benefit entry that articulates the value
proposition of the capability index itself: structured, versioned, queryable
capability manifests replace ambiguous documents as the source of truth.

**Acceptance criteria:**
- New entry (capability or benefit) with id
  `contextcore.meta.structured_authority`.
- `description.human` explains the 8 document problems the capability index
  solves (version drift, staleness, authority ambiguity, no queryability,
  no composability, no audit trail, format inconsistency, discovery requires
  human reading) and how structured queries address each.
- `description.gtm` (or `description.agent`) provides a concise value pitch.
- `user_benefit` is a one-paragraph summary.
- The entry is self-referential: it describes why the capability index exists.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml` or
  `docs/capability-index/contextcore.benefits.yaml`

---

### REQ-CID-007: Cross-reference from Export Pipeline Analysis Guide

**Priority:** P1
**Description:** Add a cross-reference from the Export Pipeline Analysis Guide
(`docs/guides/EXPORT_PIPELINE_ANALYSIS_GUIDE.md`) to the A2A capabilities in
the agent capability manifest. This closes the root-cause gap where pipeline
analysis documentation does not point to A2A primitives as the communication
solution.

**Acceptance criteria:**
- `docs/guides/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` references the capability
  manifest `docs/capability-index/contextcore.agent.yaml` in a new
  "Related capability manifests" or existing cross-reference section.
- The reference specifically calls out `contextcore.handoff.initiate`,
  `contextcore.a2a.content_model`, and `contextcore.pipeline.typed_handoff`
  (once REQ-CID-004 is implemented) as the communication primitives for
  pipeline stages.
- The reference explains that A2A primitives (Part, ExpectedOutput) apply
  to both inter-agent and intra-pipeline communication.

**Affected files:**
- `docs/guides/EXPORT_PIPELINE_ANALYSIS_GUIDE.md`

---

### REQ-CID-008: Discovery paths on capability entries

**Priority:** P3
**Description:** Add an optional `discovery_paths` field to capability entries
that provides alternate entry-point descriptions. These paths answer "if you
are looking for X, this capability is what you need" for common search
patterns that don't match the primary triggers.

**Acceptance criteria:**
- `discovery_paths` is an optional list[str] field on capability entries.
- At least the following capabilities have discovery paths:
  - `contextcore.handoff.initiate`: `"If you need to define what a pipeline
    stage should produce, use ExpectedOutput via this capability."`
  - `contextcore.a2a.content_model`: `"If you need typed data structures
    for passing between pipeline stages, use Part and Message."`
  - `contextcore.insight.emit`: `"If you need to persist knowledge that
    survives across sessions, emit insights as spans."`
- Discovery paths are informational (for LLM context) — they do not need
  to be emitted as OTel attributes.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`

---

### REQ-CID-009: Capability index skill for agent navigation

**Priority:** P3
**Description:** Create a SKILL.md file (or extend an existing skill) that
agents can use to systematically navigate the capability index. The skill
encodes the search strategy: check design principles first, then patterns,
then individual capabilities by trigger match.

**Acceptance criteria:**
- A skill exists that guides agents through capability index navigation.
- The skill's workflow:
  1. Read `design_principles` for governing constraints.
  2. Check `patterns` for named composition patterns matching the use case.
  3. Search `capabilities` by `triggers` for specific capabilities.
  4. Check `discovery_paths` for alternate entry points.
- The skill is referenced from the capability index manifest itself
  (self-referential discovery).

**Affected files:**
- New skill file (location TBD based on skill infrastructure)
- `docs/capability-index/contextcore.agent.yaml` (reference to skill)

---

### REQ-CID-010: Backward compatibility guarantee

**Priority:** P1
**Description:** All changes to the capability index manifests must be
backward compatible. Existing consumers that parse `capabilities` arrays
must continue to work. New top-level sections (`design_principles`,
`patterns`) are additive — they do not modify the `capabilities` schema.

**Acceptance criteria:**
- Existing YAML parsers that read `capabilities` array are unaffected.
- No existing capability entries are removed or renamed.
- New fields on existing entries (`discovery_paths`) are optional.
- `manifest_id`, `version`, and `name` fields remain at their current
  positions.
- Version is bumped (minor) to reflect the additive changes.
- Existing OTel emission code (`contextcore terminology emit`) handles
  new sections gracefully (ignores unknown keys or emits them).

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`
- `src/contextcore/terminology/parser.py` (verify compatibility)
- `src/contextcore/terminology/emitter.py` (verify compatibility)

---

### REQ-CID-011: Contract layer capabilities in agent manifest

**Priority:** P1
**Description:** Add 7 capability entries to `contextcore.agent.yaml`, one per
defense-in-depth contract layer. These capabilities represent the implemented
contract system in `src/contextcore/contracts/` — ContextCore's most
differentiating capability set. No other workflow framework treats context
propagation as a first-class, verifiable concern.

This was identified as Gap 6 in the
[gap analysis](../../capability-index/CAPABILITY_INDEX_GAP_ANALYSIS.md)
(added 2026-02-16) after the contract system was fully implemented.

**Acceptance criteria:**
- 7 new capability entries in `contextcore.agent.yaml`:

  | capability_id | category | summary |
  |---|---|---|
  | `contextcore.contract.propagation` | transform | Declare end-to-end field flow contracts, validate at phase boundaries, track provenance |
  | `contextcore.contract.schema_compat` | transform | Cross-service schema compatibility checking with field mapping and value translation |
  | `contextcore.contract.semantic_convention` | transform | Attribute naming and enum consistency enforcement across services |
  | `contextcore.contract.causal_ordering` | transform | Cross-boundary event ordering contracts with Lamport timestamp verification |
  | `contextcore.contract.capability_propagation` | transform | End-to-end permission and capability flow verification through call chains |
  | `contextcore.contract.slo_budget` | transform | Per-hop latency budget allocation, tracking, and DEGRADED/BROKEN signaling |
  | `contextcore.contract.data_lineage` | transform | Transformation history verification and data provenance tracking |

- Each capability entry has:
  - `maturity: beta` (all layers are implemented with tests)
  - `description.agent` explaining the declare/validate/track/emit workflow
  - `description.human` explaining the business value
  - `triggers` including contract-specific and generic terms (e.g.,
    `"context contract"`, `"boundary validation"`, `"propagation chain"`,
    `"schema checking"`, `"ordering constraint"`, `"budget tracking"`,
    `"data lineage"`, `"provenance"`)
  - `delivers_benefit` referencing the `prescriptive_over_descriptive`
    principle and/or a contract-specific benefit
  - `inputs` and `outputs` schemas referencing the Pydantic models
    (e.g., `PropagationChainSpec`, `CompatibilityChecker`,
    `OrderingConstraintSpec`)

- After the change, searching triggers for "contract" matches >= 7
  capabilities.
- After the change, searching triggers for "validation" or "boundary"
  matches >= 3 capabilities.
- The `contract_validation` pattern (REQ-CID-002) references all 7
  capability_ids in its `capabilities` list.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`

**Source documents:**
- [CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md](../../design/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — theoretical foundation
- [CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md](../../design/CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) — Layer 1 detailed design
- [ContextCore-context-contracts.md](../../design/ContextCore-context-contracts.md) — original design thinking

---

### REQ-CID-012: A2A governance contract capabilities in agent manifest

**Priority:** P1
**Description:** Add capability entries for the A2A governance contract system
— 4 typed contract structures and 2 governance gate commands. The A2A comms
design (`contextcore-a2a-comms-design.md`) implements a 7-step pipeline with
3 governance gates, 4 typed contract structures, and 154 tests. This system
is completely absent from the capability index.

This was discovered via framework comparison analysis (LangGraph, AutoGen,
CrewAI) which identified that ContextCore's A2A governance layer — typed
contracts at pipeline boundaries with integrity gates — is a unique
differentiator not found in any competing framework.

**Acceptance criteria:**
- 6 new capability entries in `contextcore.agent.yaml`:

  | capability_id | category | summary |
  |---|---|---|
  | `contextcore.a2a.contract.task_span` | transform | Typed contract for task span interchange — validates SpanState v2 compliance, required attributes, and enum values |
  | `contextcore.a2a.contract.handoff` | transform | Typed contract for agent-to-agent handoff — validates ExpectedOutput, lifecycle status, and provenance chain |
  | `contextcore.a2a.contract.artifact_intent` | transform | Typed declaration of expected artifacts with semantic roles — the Mottainai principle (respect for what has already been created) |
  | `contextcore.a2a.contract.gate_result` | transform | Typed result from governance gates — pass/fail/warning with structured diagnostics and remediation hints |
  | `contextcore.a2a.gate.pipeline_integrity` | action | Gate 1: 6 structural integrity checks on exported pipeline artifacts (checksum chain, provenance, mapping completeness, gap parity, design calibration) |
  | `contextcore.a2a.gate.diagnostic` | action | Gate 2: Three Questions diagnostic — "Was anything lost?", "Does the shape match?", "Can we trace the lineage?" |

- Each capability entry has:
  - `maturity: beta` (all implemented with tests)
  - `description.agent` explaining the typed contract structure and gate workflow
  - `description.human` explaining the business value
  - `triggers` including governance-specific and generic terms (e.g.,
    `"a2a contract"`, `"task span contract"`, `"handoff contract"`,
    `"artifact intent"`, `"governance gate"`, `"pipeline integrity"`,
    `"diagnostic gate"`, `"three questions"`)
  - `delivers_benefit` referencing `typed_over_prose` and/or
    `prescriptive_over_descriptive` principles

- After the change, searching triggers for "governance" matches >= 2
  capabilities.
- After the change, searching triggers for "a2a contract" matches >= 4
  capabilities.
- The A2A governance capabilities are referenced from the
  `contract_validation` pattern (REQ-CID-002) or a new
  `a2a_governance` pattern.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`

**Source documents:**
- [contextcore-a2a-comms-design.md](../../design/contextcore-a2a-comms-design.md) — A2A governance architecture (v1, 154 tests)
- [A2A_CONTRACTS_DESIGN.md](../../design/A2A_CONTRACTS_DESIGN.md) — conceptual design for 4 typed structures
- [A2A_GATE_REQUIREMENTS.md](../../design/A2A_GATE_REQUIREMENTS.md) — gate behavioral requirements

---

## Phase 2 Problem Statement: Artifact Scope False Ceiling

> **Full investigation:** [DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md](../DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md)

Phase 1 fixed **capability discovery** — an agent with a known problem can find the
capabilities that solve it. Phase 2 addresses a deeper failure: **scope discovery** —
an agent cannot determine the complete boundary of what the system produces.

### The Failure

An agent (Claude Opus 4.6) was asked whether Dockerfiles should be produced at
the ContextCore export stage. It searched 12 independent sources:

1. `run-provenance.json` — 9 artifacts, all observability/pre-pipeline
2. `online-boutique-python-artifact-manifest.yaml` — 8 artifacts, all observability
3. `.contextcore.yaml` — Dockerfiles in tactics deliverables, not artifact spec
4. `ArtifactType` enum (`artifact_manifest.py:28`) — docstring: "Types of **observability** artifacts"
5. `MANIFEST_EXPORT_REQUIREMENTS.md:99` — "Must support **8 artifact types**"
6. `REQ_CAPABILITY_DELIVERY_PIPELINE.md` — no Dockerfile mentions
7. `contextcore.agent.yaml` (115K, 3300 lines) — zero non-observability artifact mentions
8. `contextcore.benefits.yaml:717` — "observability artifacts"
9. `contextcore.user.yaml` — no Dockerfile references
10. `_patterns.yaml`, `_principles.yaml`, `_discovery_paths.yaml` — no artifact scope content
11. `onboarding-metadata.json` artifact_types section — only observability types + capability_index
12. `artifact-intent.schema.json:5` — "observability artifact need"

**Conclusion (wrong, high confidence):** "ContextCore only produces observability artifacts."

**Correct answer** (found only after human hint to check `pipeline-requirements-onboarding.md`):
The pipeline defines non-observability artifact types: `agent_card`, `mcp_tools`,
`onboarding_metadata`, `provenance`, `ingestion-traceability`. This document is
referenced from **zero** other documents in the system.

### Seven Reinforcing Breakpoints

| # | Source | False Ceiling Text | Impact |
|---|--------|-------------------|--------|
| 1 | `artifact_manifest.py:28` | "Types of observability artifacts" | Enum presents itself as authoritative and complete |
| 2 | `MANIFEST_EXPORT_REQUIREMENTS.md:99` | "Must support 8 artifact types" | Specific count + explicit list reads as exhaustive |
| 3 | `contextcore.benefits.yaml:717` | "observability artifacts" in value statement | User-facing benefit reinforces scope from independent angle |
| 4 | `artifact-intent.schema.json:5` | "observability artifact need" | A2A governance layer confirms scope from schema angle |
| 5 | `pipeline-requirements-onboarding.md` | Zero inbound cross-references | The document with the answer is an island |
| 6 | No "artifact type registry" capability | — | No capability describes the complete artifact vocabulary |
| 7 | Search vocabulary mismatch | — | "artifact scope", "beyond observability" returns zero results |

### The Quantified Failure

**12** sources confirming wrong boundary **:** **1** source with right answer **:** **0** cross-references connecting them

This 12:1:0 ratio measures the false ceiling's strength. Each confirming source
increases agent confidence — a **multiple-corroboration trap** where wrong information
appearing in multiple places is more convincing than wrong information in one place.

---

### REQ-CID-013: Artifact type registry as first-class capability

**Priority:** P1
**Failure addressed:** Breakpoints 4, 6 — no single capability describes the complete artifact vocabulary
**Description:** Add a capability entry to `contextcore.agent.yaml` that serves as
the **single discoverable source** for all artifact types the pipeline can produce,
organized by category (observability, onboarding, integrity). This capability does
not implement new code — it documents the complete artifact type taxonomy so agents
can answer "what types of artifacts does this pipeline produce?" by reading one
capability entry.

**Acceptance criteria:**
- New capability entry with `capability_id: contextcore.meta.artifact_type_registry`.
- `category: query`, `maturity: stable`.
- `description.agent` lists ALL artifact types across all categories:
  - **Observability** (8): dashboard, prometheus_rule, slo_definition, service_monitor,
    loki_rule, notification_policy, runbook, alert_template
  - **Onboarding** (4): capability_index, agent_card, mcp_tools, onboarding_metadata
  - **Integrity** (2): provenance, ingestion-traceability
- `description.human` explains: "The pipeline produces artifacts in three categories.
  Observability artifacts are generated from business metadata. Onboarding and integrity
  artifacts are pipeline-innate — they are produced automatically regardless of the
  project's business context."
- `triggers` include: `"artifact types"`, `"what artifacts"`, `"artifact scope"`,
  `"artifact categories"`, `"pipeline produces"`, `"artifact taxonomy"`,
  `"artifact registry"`, `"beyond observability"`, `"non-observability artifacts"`,
  `"pipeline-innate"`.
- `cross_references` links to `pipeline-requirements-onboarding.md` and
  `artifact_manifest.py`.
- After the change, searching triggers for "artifact type" or "what artifacts" matches
  this capability.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`
- `docs/capability-index/_p2_capabilities.yaml` (sidecar for new capability)

**Source documents:**
- [pipeline-requirements-onboarding.md](../../reference/pipeline-requirements-onboarding.md) — defines onboarding + integrity types
- [DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md](../DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md) — documents the failure

---

### REQ-CID-014: Scope boundary declaration in capability index

**Priority:** P1
**Failure addressed:** Breakpoints 6, 7 — no mechanism for declaring "what the system covers"
**Description:** Add a top-level `scope_boundaries` section to `contextcore.agent.yaml`
that explicitly declares the domains and artifact categories the system operates in.
This addresses the meta-problem identified in the investigation: agents can discover
individual capabilities but cannot determine the system's complete scope.

**Acceptance criteria:**
- `contextcore.agent.yaml` has a `scope_boundaries` key at the top level (after
  `patterns`, before `capabilities`).
- The section includes:
  - `artifact_categories`: List of categories with their artifact types
    ```yaml
    artifact_categories:
      - category: observability
        description: "Generated from business metadata in .contextcore.yaml"
        types: [dashboard, prometheus_rule, slo_definition, service_monitor,
                loki_rule, notification_policy, runbook, alert_template]
      - category: onboarding
        description: "Pipeline-innate artifacts produced automatically"
        types: [capability_index, agent_card, mcp_tools, onboarding_metadata]
      - category: integrity
        description: "Pipeline-innate provenance and traceability artifacts"
        types: [provenance, ingestion-traceability]
    ```
  - `pipeline_stages`: List of 7 pipeline stages with their roles
  - `explicit_non_scope`: What the system does NOT produce (e.g., application code,
    Dockerfiles, CI/CD configs — these are plan deliverables, not pipeline artifacts)
- The scope boundaries are positioned BEFORE individual capabilities in document
  order (agents encounter scope before searching capabilities).
- An agent reading `scope_boundaries` can answer: "How many artifact categories
  exist?" and "Does the system produce X?" without searching individual capabilities.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml`

---

### REQ-CID-015: Cross-reference enforcement between requirements and capability index

**Priority:** P1
**Failure addressed:** Breakpoint 5 — `pipeline-requirements-onboarding.md` has zero
inbound cross-references
**Description:** Every requirements document that defines artifact types, pipeline
behaviors, or capability contracts MUST be referenced from at least one capability
index entry. Conversely, every capability index entry that describes artifacts or
pipeline stages MUST reference its authoritative requirements document.

**Acceptance criteria:**
- `pipeline-requirements-onboarding.md` is referenced from:
  - `contextcore.agent.yaml` — at least one capability's `cross_references` field
  - `contextcore.benefits.yaml` — in the `pipeline.contract_first_planning` benefit
  - `MANIFEST_EXPORT_REQUIREMENTS.md` — in a "Related Requirements" section
  - `artifact_manifest.py` — in the `ArtifactType` enum docstring
- A validation check (manual or automated) verifies that for every `.md` file in
  `docs/reference/` that defines `REQ-CDP-*` requirements, at least one capability
  or benefit entry cross-references it.
- New requirements documents added to `docs/reference/` must include a
  "Capability Index Cross-References" section listing which capabilities they
  relate to.
- The following specific cross-references are added:
  - `artifact_manifest.py:28` docstring → cites `pipeline-requirements-onboarding.md`
  - `MANIFEST_EXPORT_REQUIREMENTS.md:99` → notes additional categories exist
  - `contextcore.benefits.yaml:717` → replaces "observability artifacts" with "artifacts"
  - `artifact-intent.schema.json:5` → removes "observability" qualifier

**Affected files:**
- `docs/reference/pipeline-requirements-onboarding.md` (add outbound cross-references)
- `docs/capability-index/contextcore.agent.yaml` (add inbound cross-references)
- `docs/capability-index/contextcore.benefits.yaml` (fix scope language)
- `docs/design/MANIFEST_EXPORT_REQUIREMENTS.md` (add related requirements section)
- `src/contextcore/models/artifact_manifest.py` (fix docstring)
- `schemas/contracts/artifact-intent.schema.json` (fix description)

**Source documents:**
- [DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md](../DISCOVERABILITY_FAILURE_INVESTIGATION_2026-02-18.md) — Breakpoint 5 analysis

---

### REQ-CID-016: Anti-false-ceiling validation

**Priority:** P1
**Failure addressed:** Breakpoints 1, 2, 3, 4 — multiple documents present a subset
as complete without noting the superset
**Description:** No document, docstring, or schema description in the ContextCore
codebase should present a subset of artifact types as the complete set without
explicitly noting that additional types exist in other categories. This is the
"anti-false-ceiling" principle: **any enumeration that is not exhaustive must say so.**

**Acceptance criteria:**
- `ArtifactType` enum docstring (`artifact_manifest.py:28`) changes from:
  "Types of observability artifacts that can be generated" to:
  "Types of artifacts that can be generated. Observability types are listed here.
  See pipeline-requirements-onboarding.md for onboarding and integrity types."
- `ArtifactManifest` class docstring (`artifact_manifest.py:489`) changes from:
  "contract for observability artifact generation" to:
  "contract for artifact generation"
- `MANIFEST_EXPORT_REQUIREMENTS.md:99` "Must support 8 artifact types" adds a note:
  "These 8 types represent the observability category. Additional categories
  (onboarding, integrity) are defined in pipeline-requirements-onboarding.md."
- `contextcore.benefits.yaml:717` `pipeline.contract_first_planning` value_statement
  changes "observability artifacts" to "pipeline artifacts" or "artifacts".
- `artifact-intent.schema.json:5` description changes from "observability artifact
  need" to "artifact need".
- `onboarding.py:1-13` module docstring adds: "In addition to observability artifacts,
  the pipeline produces onboarding and integrity artifacts defined in
  pipeline-requirements-onboarding.md."
- A validation heuristic: any string matching `"[0-9]+ artifact types"` (e.g.,
  "8 artifact types", "9 artifact types") must be within 3 lines of text noting
  the existence of other categories.

**Affected files:**
- `src/contextcore/models/artifact_manifest.py` (lines 28, 489)
- `docs/design/MANIFEST_EXPORT_REQUIREMENTS.md` (line 99)
- `docs/capability-index/contextcore.benefits.yaml` (line 717)
- `schemas/contracts/artifact-intent.schema.json` (line 5)
- `src/contextcore/utils/onboarding.py` (lines 1-13)
- `docs/design/ARTIFACT_MANIFEST_CONTRACT.md` (lines 92-106, add category headers)
- `docs/plans/EXPORT_PIPELINE_IMPLEMENTATION_SUMMARY.md` (line 70)

---

### REQ-CID-017: Scope-question discoverability tests

**Priority:** P1
**Failure addressed:** The investigation demonstrated that no existing test would catch
the 12:1:0 failure ratio
**Description:** Add discoverability tests that ask **scope questions** (not just
capability-matching questions). These tests simulate the agent's search path and
verify that the capability index can answer boundary questions like "what types of
artifacts does this pipeline produce?" and "does this system produce non-observability
artifacts?"

**Acceptance criteria:**
- Tests are implemented as part of the capability validator test suite.
- At minimum, the following scope tests exist:

| Test | Question Simulated | Pass Condition |
|------|--------------------|----------------|
| `test_scope_artifact_types_complete` | "What artifact types exist?" | Searching triggers/descriptions for "artifact type" finds a capability that lists ALL types across ALL categories |
| `test_scope_beyond_observability` | "Does the system produce non-observability artifacts?" | Searching for "non-observability" OR "onboarding" OR "pipeline-innate" in triggers matches >= 1 capability |
| `test_scope_artifact_categories` | "How many artifact categories exist?" | `scope_boundaries.artifact_categories` contains >= 3 categories |
| `test_scope_boundary_present` | "What is the system's scope?" | `scope_boundaries` section exists in manifest |
| `test_no_false_ceiling_enum` | "Is the ArtifactType enum observability-only?" | Enum docstring does NOT contain the word "observability" without qualification |
| `test_no_false_ceiling_schema` | "Does artifact-intent say observability?" | Schema description does NOT contain "observability" without qualification |
| `test_cross_reference_coverage` | "Are requirements documents referenced?" | Every `REQ-CDP-*` document in `docs/reference/` has >= 1 inbound cross-reference from capability index |
| `test_pipeline_innate_discoverable` | "Can I find pipeline-innate artifacts?" | Searching for "pipeline-innate" matches >= 1 capability or scope boundary entry |

- Tests use the same search strategy an agent would use (trigger matching, description
  searching, scope boundary reading) — they do not use internal knowledge of where
  the answer lives.
- At least one "negative test": verify that searching ONLY the old Phase 1 content
  (triggers for "artifact", "pipeline output") does NOT return a false-ceiling
  response (i.e., the results include non-observability types).

**Affected files:**
- `tests/test_capability_discoverability.py` (new or extended)
- `src/contextcore/utils/capability_validator.py` (scope validation rules)

---

### REQ-CID-018: ArtifactType enum consolidation

**Priority:** P1
**Failure addressed:** Background investigation found 15 artifact types across 9
fragmented definition sources with inconsistencies (e.g., `artifact_conventions.py`
missing CAPABILITY_INDEX, `pipeline_requirements.py` defining types not in the enum)
**Description:** Consolidate the `ArtifactType` enum to include ALL artifact types
produced by the pipeline, with category annotations. This is the code-level single
source of truth that REQ-CID-013 (the capability entry) describes programmatically.

**Acceptance criteria:**
- `ArtifactType` enum in `artifact_manifest.py` includes all 14 types:
  ```python
  class ArtifactType(str, Enum):
      """Types of artifacts produced by the ContextCore pipeline.

      Organized by category:
      - Observability: generated from business metadata
      - Onboarding: pipeline-innate, produced automatically
      - Integrity: pipeline-innate provenance and traceability

      See docs/reference/pipeline-requirements-onboarding.md for requirements.
      """

      # Observability (8)
      DASHBOARD = "dashboard"
      PROMETHEUS_RULE = "prometheus_rule"
      LOKI_RULE = "loki_rule"
      SLO_DEFINITION = "slo_definition"
      SERVICE_MONITOR = "service_monitor"
      NOTIFICATION_POLICY = "notification_policy"
      RUNBOOK = "runbook"
      ALERT_TEMPLATE = "alert_template"

      # Onboarding (4)
      CAPABILITY_INDEX = "capability_index"
      AGENT_CARD = "agent_card"
      MCP_TOOLS = "mcp_tools"
      ONBOARDING_METADATA = "onboarding_metadata"

      # Integrity (2)
      PROVENANCE = "provenance"
      INGESTION_TRACEABILITY = "ingestion-traceability"
  ```
- Category can be derived programmatically:
  ```python
  OBSERVABILITY_TYPES = {DASHBOARD, PROMETHEUS_RULE, LOKI_RULE, SLO_DEFINITION,
                         SERVICE_MONITOR, NOTIFICATION_POLICY, RUNBOOK, ALERT_TEMPLATE}
  ONBOARDING_TYPES = {CAPABILITY_INDEX, AGENT_CARD, MCP_TOOLS, ONBOARDING_METADATA}
  INTEGRITY_TYPES = {PROVENANCE, INGESTION_TRACEABILITY}
  ```
- `ARTIFACT_OUTPUT_CONVENTIONS` in `artifact_conventions.py` updated with entries
  for all new types.
- `ARTIFACT_PARAMETER_SOURCES` in `onboarding.py` updated with entries for all new types.
- `pipeline_requirements.py` `satisfied_by_artifact` values validated against
  `ArtifactType` enum (no free-form strings that aren't in the enum).
- Backward compatibility: existing code using `ArtifactType.DASHBOARD` etc. is unaffected.
- Tests verify enum completeness against `pipeline-requirements-onboarding.md` definitions.

**Affected files:**
- `src/contextcore/models/artifact_manifest.py` (enum expansion + docstring)
- `src/contextcore/utils/artifact_conventions.py` (add missing types)
- `src/contextcore/utils/onboarding.py` (add missing parameter sources)
- `src/contextcore/utils/pipeline_requirements.py` (validate against enum)
- `tests/test_artifact_types.py` (new — enum completeness tests)

---

## Phase 3 Problem Statement: MCP/A2A Export Coverage Gap

> **Audit report:** [MCP_A2A_TOOLS_DOCUMENTATION_AUDIT.md](../capability-index/MCP_A2A_TOOLS_DOCUMENTATION_AUDIT.md)

Phase 1 fixed **capability discovery** within the manifest. Phase 2 fixes **scope
discovery** so agents can determine the system's complete boundary. Phase 3 addresses
a third failure class: **export coverage** — capabilities that exist in the manifest
but are invisible to MCP and A2A consumers because they are silently excluded from
the generated artifacts.

### The Failure

An audit of `mcp-tools.json` and `agent-card.json` found both files contain exactly
**34 tools/skills** with a perfect 1:1 mapping. However, the manifest
(`contextcore.agent.yaml` v1.14.0) contains **49 capabilities**. The 15 missing
capabilities are all Phase 1 additions:

| # | Capability ID | Why excluded |
|---|---|---|
| 1 | `contextcore.contract.propagation` | No `audiences` field (defaults to `["human"]`) |
| 2 | `contextcore.contract.schema_compat` | No `audiences` field |
| 3 | `contextcore.contract.semantic_convention` | No `audiences` field |
| 4 | `contextcore.contract.causal_ordering` | No `audiences` field |
| 5 | `contextcore.contract.capability_propagation` | No `audiences` field |
| 6 | `contextcore.contract.slo_budget` | No `audiences` field |
| 7 | `contextcore.contract.data_lineage` | No `audiences` field |
| 8 | `contextcore.a2a.contract.task_span` | No `audiences` field |
| 9 | `contextcore.a2a.contract.handoff` | No `audiences` field |
| 10 | `contextcore.a2a.contract.artifact_intent` | No `audiences` field |
| 11 | `contextcore.a2a.contract.gate_result` | No `audiences` field |
| 12 | `contextcore.a2a.gate.pipeline_integrity` | No `audiences` field |
| 13 | `contextcore.a2a.gate.diagnostic` | No `audiences` field |
| 14 | `contextcore.pipeline.typed_handoff` | No `audiences` field |
| 15 | `contextcore.contract.expected_output` | No `audiences` field |

### Root Cause

The MCP generator (`capability_mcp_generator.py:34-40`) filters capabilities by
checking `audiences` for `"agent"`. If the field is absent, it defaults to
`["human"]` — silently excluding the capability. The A2A generator uses the same
filter. Phase 1 capabilities were added via `capability_scanner.py` and sidecar
YAML files which did not include `audiences` fields.

### Additional Gaps (from audit)

The audit also identified three documentation/configuration gaps:

1. **Placeholder URL in Agent Card**: `agent-card.json` uses
   `https://api.example.com/contextcore.agent` because the manifest has no `a2a`
   section with a real URL.
2. **Missing `a2a` section in manifest**: The schema supports `a2a.url`,
   `a2a.authentication`, and `a2a.provider` but the manifest doesn't define them.
3. **Discovery path undocumented**: The A2A discovery endpoint
   (`/.well-known/agent.json`) is implemented in `a2a_server.py` and
   `endpoint.py` but not documented in the capability index artifacts.

---

### REQ-CID-019: MCP/A2A export coverage for Phase 1+ capabilities

**Priority:** P1
**Failure addressed:** 15 capabilities silently excluded from MCP tools and A2A Agent
Card because they lack `audiences: ["agent"]`
**Description:** All capabilities that represent agent-usable actions, contracts, or
gates MUST include `audiences: ["agent", "human"]` so that MCP and A2A generators
export them. After adding audience tags, the MCP/A2A artifacts must be regenerated
and a synchronization check must verify that the manifest capability count matches
the exported tool count (accounting for any intentionally human-only capabilities).

**Acceptance criteria:**
- All 15 capabilities listed in the Phase 3 Problem Statement gain
  `audiences: ["agent", "human"]` in `contextcore.agent.yaml`.
- After regeneration (`contextcore capability-index generate-mcp` and
  `contextcore capability-index generate-a2a`):
  - `mcp-tools.json` contains **49 tools** (was 34).
  - `agent-card.json` contains **49 skills** (was 34).
  - 1:1 mapping between MCP tools and A2A skills is maintained.
- The `capability_scanner.py` is updated to emit `audiences: ["agent", "human"]`
  for all scanned capabilities by default (so future scans don't reproduce this gap).
- The `capability_builder.py` merge logic preserves `audiences` from sidecar files
  and applies a default of `["agent", "human"]` when the field is absent on
  non-internal capabilities.
- A new validation check in `capability_validator.py` warns when a non-internal
  capability lacks an `audiences` field.
- The `_p2_capabilities.yaml` and any other sidecar files that define Phase 1
  capabilities are updated to include `audiences`.
- After the change, `mcp-tools.json` tool count equals the number of capabilities
  in `contextcore.agent.yaml` that have `"agent"` in their `audiences` field.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml` (add audiences to 15 capabilities)
- `docs/capability-index/_p2_capabilities.yaml` (add audiences)
- `docs/capability-index/mcp-tools.json` (regenerated)
- `docs/capability-index/agent-card.json` (regenerated)
- `src/contextcore/utils/capability_scanner.py` (default audiences on scanned capabilities)
- `src/contextcore/utils/capability_builder.py` (default audiences in merge logic)
- `src/contextcore/utils/capability_validator.py` (audiences coverage warning)

**Source documents:**
- [MCP_A2A_TOOLS_DOCUMENTATION_AUDIT.md](../capability-index/MCP_A2A_TOOLS_DOCUMENTATION_AUDIT.md) — audit report
- [capability_mcp_generator.py](../../../src/contextcore/utils/capability_mcp_generator.py) — filter logic (lines 34-40)

---

### REQ-CID-020: A2A manifest section

**Priority:** P2
**Failure addressed:** Audit Gap #1 and #3 — placeholder URL in Agent Card, missing
manifest configuration for A2A deployment
**Description:** Add a top-level `a2a` section to `contextcore.agent.yaml` that
provides deployment metadata for A2A discovery. The manifest schema already supports
this section (`manifest.schema.yaml:164`) but the manifest does not define it, causing
the A2A generator to emit a placeholder URL.

**Acceptance criteria:**
- `contextcore.agent.yaml` has an `a2a` key at the top level (after `labels`,
  before `design_principles`).
- The section includes:
  ```yaml
  a2a:
    url: "${CONTEXTCORE_A2A_URL:-https://localhost:8080/contextcore.agent}"
    discovery_endpoint: "/.well-known/agent.json"
    extended_discovery_endpoint: "/.well-known/contextcore.json"
    authentication:
      schemes: [bearer, none]
    provider:
      organization: "force-multiplier-labs"
      url: "https://github.com/Force-Multiplier-Labs/contextcore"
  ```
- The `url` field uses an environment variable placeholder with a localhost default,
  following the same pattern as `OTEL_EXPORTER_OTLP_ENDPOINT`.
- The A2A generator reads `a2a.url` from the manifest instead of constructing
  a placeholder URL.
- After regeneration, `agent-card.json` contains the configured URL (or localhost
  default) instead of `https://api.example.com/contextcore.agent`.
- The `discovery_endpoint` and `extended_discovery_endpoint` fields are emitted
  in the Agent Card's metadata, making discovery paths programmatically accessible.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml` (add `a2a` section)
- `docs/capability-index/agent-card.json` (regenerated with real URL)
- `src/contextcore/utils/capability_a2a_generator.py` (read `a2a.url` from manifest)

**Source documents:**
- [MCP_A2A_TOOLS_DOCUMENTATION_AUDIT.md](../capability-index/MCP_A2A_TOOLS_DOCUMENTATION_AUDIT.md) — Gaps #1, #3
- [manifest.schema.yaml](../../../src/contextcore/utils/capability_schemas/manifest.schema.yaml) — `a2a` schema (line 164)

---

### REQ-CID-021: Discovery endpoint documentation in capability index

**Priority:** P2
**Failure addressed:** Audit Gap #2 — discovery path implemented but not documented
in capability index artifacts
**Description:** The A2A discovery endpoints (`/.well-known/agent.json` and
`/.well-known/contextcore.json`) are implemented in `a2a_server.py` and
`endpoint.py` but are not documented in the capability index. An agent reading the
capability index cannot determine how to discover the ContextCore agent
programmatically.

**Acceptance criteria:**
- A new capability entry `contextcore.discovery.well_known` is added to
  `contextcore.agent.yaml` with:
  - `capability_id: contextcore.discovery.well_known`
  - `category: query`
  - `maturity: beta`
  - `audiences: ["agent", "human"]`
  - `summary`: "Serve A2A Agent Card and ContextCore extended discovery at
    standard well-known endpoints"
  - `description.agent`: Documents both endpoints, their response formats
    (A2A Agent Card JSON, ContextCore extended JSON), and how to use them
    for programmatic agent discovery.
  - `description.human`: Explains that the system exposes standard discovery
    URLs that other agents and tools can use to find capabilities automatically.
  - `triggers`: `"discovery endpoint"`, `"well-known"`, `"agent discovery"`,
    `"agent card endpoint"`, `".well-known/agent.json"`,
    `"programmatic discovery"`, `"MCP discovery"`, `"A2A discovery"`
  - `cross_references`: Links to `src/contextcore/agent/a2a_server.py` and
    `src/contextcore/discovery/endpoint.py`
- The capability is exported to `mcp-tools.json` and `agent-card.json` after
  regeneration.
- After the change, searching triggers for "discovery" or "well-known" matches
  at least this capability.
- The existing `contextcore.a2a.server` capability gains a `cross_references`
  field linking to `contextcore.discovery.well_known`.

**Affected files:**
- `docs/capability-index/contextcore.agent.yaml` (new capability + cross-reference)
- `docs/capability-index/mcp-tools.json` (regenerated)
- `docs/capability-index/agent-card.json` (regenerated)

**Source documents:**
- [MCP_A2A_TOOLS_DOCUMENTATION_AUDIT.md](../capability-index/MCP_A2A_TOOLS_DOCUMENTATION_AUDIT.md) — Gap #2
- [a2a_server.py](../../../src/contextcore/agent/a2a_server.py) — endpoint implementation
- [endpoint.py](../../../src/contextcore/discovery/endpoint.py) — discovery document serving

---

## Manifest Schema Changes

The following top-level sections are added to `contextcore.agent.yaml`:

```yaml
# NEW — after labels, before capabilities
design_principles:
  - id: typed_over_prose
    principle: "All inter-agent data exchange uses typed schemas, not natural language parsing"
    rationale: |
      Structured data eliminates version drift, format ambiguity, and regex fragility.
      ExpectedOutput.fields replaces regex section extraction.
      Part.json_data() replaces string interpolation.
      Time-series databases make structured data queryable over time.
    anti_patterns:
      - "Parsing LLM markdown output with regex to extract structured fields"
      - "Passing strings between pipeline stages instead of typed objects"
      - "Using document sections as the contract between agents"
    applies_to:
      - contextcore.handoff.initiate
      - contextcore.a2a.content_model
      - contextcore.code_generation.contract

  - id: prescriptive_over_descriptive
    principle: "Declare what should happen and verify it did, rather than recording what happened after the fact"
    rationale: |
      Traditional observability describes what happened. ContextCore prescribes what
      should happen and verifies that it did. Contracts are the prescriptions.
      This shifts context correctness from runtime hope to design-time guarantee.
    anti_patterns:
      - "Relying on post-hoc log analysis to detect context loss"
      - "Observing failures after they reach production instead of preventing them at design time"
    applies_to:
      - contextcore.contract.propagation
      - contextcore.contract.schema_compat
      - contextcore.contract.semantic_convention

  - id: design_time_over_runtime
    principle: "Catch context correctness issues when the pipeline is designed, not when it fails in production"
    rationale: |
      YAML contracts are reviewed in PRs alongside code. Static analysis
      walks the requires/produces graph before any workflow runs.
    anti_patterns:
      - "Discovering context propagation failures only in production"
      - "Testing contract compatibility only during integration testing"
    applies_to:
      - contextcore.contract.propagation
      - contextcore.contract.schema_compat

  - id: graceful_degradation
    principle: "Not all context fields are equally critical; the severity model (BLOCKING/WARNING/ADVISORY) mirrors real system priorities"
    rationale: |
      Some fields are load-bearing (task list), some are quality-enhancing
      (domain constraints), some are diagnostic aids (debug metadata).
      The severity model enables progressive tightening without all-or-nothing adoption.
    anti_patterns:
      - "Treating all context fields as equally critical (fail-fast on everything)"
      - "Treating all context fields as non-critical (ignore all failures)"
    applies_to:
      - contextcore.contract.propagation
      - contextcore.contract.capability_propagation
      - contextcore.contract.slo_budget

  - id: composable_primitives
    principle: "Every contract layer uses the same four primitives: Declare, Validate, Track, Emit"
    rationale: |
      New layers are new contract types plugged into the same framework, not new frameworks.
      The shared primitives ensure consistency across all 7 defense-in-depth layers.
    anti_patterns:
      - "Building a custom validation framework for each new contract type"
      - "Inconsistent checking approaches across different boundary types"
    applies_to:
      - contextcore.contract.propagation
      - contextcore.contract.schema_compat
      - contextcore.contract.causal_ordering
      - contextcore.contract.data_lineage

  - id: opt_in_over_mandatory
    principle: "Every layer is opt-in; existing systems work unchanged; contracts add verification on top"
    rationale: |
      Progressive adoption without breaking existing systems. Start with detection,
      add contracts when ready, get prevention for free. Mirrors TypeScript's adoption
      path — you don't need strict mode on day one.
    anti_patterns:
      - "Requiring all services to adopt contracts simultaneously"
      - "Breaking existing pipelines when adding contract validation"
    applies_to:
      - contextcore.contract.propagation
      - contextcore.contract.schema_compat

  - id: observable_contracts
    principle: "The contract system itself emits OTel events, making contract health observable through the same infrastructure"
    rationale: |
      You can build a dashboard showing '85% of propagation chains are INTACT,
      10% are DEGRADED, 5% are BROKEN.' The meta-observability makes the contract
      system trustworthy and queryable via TraceQL.
    anti_patterns:
      - "Contract validation that produces only pass/fail with no observability"
      - "Separate monitoring for contract health vs runtime health"
    applies_to:
      - contextcore.contract.propagation
      - contextcore.contract.schema_compat
      - contextcore.contract.slo_budget

  - id: framework_agnostic_contracts
    principle: "Contracts declare what must be true about context propagation, not how frameworks achieve it"
    rationale: |
      ContextCore works with LangGraph, AutoGen, CrewAI, or any runtime. Contracts
      are runtime-independent governance — they validate invariants regardless of
      which framework executes the pipeline. This emerged from framework comparison
      analysis showing that ContextCore's value is orthogonal to runtime choice.
    anti_patterns:
      - "Coupling contract validation to a specific framework's execution model"
      - "Requiring framework-specific adapters for each contract type"
    applies_to:
      - contextcore.contract.propagation
      - contextcore.contract.schema_compat
      - contextcore.a2a.contract.task_span
      - contextcore.a2a.contract.handoff

  - id: governance_metadata_over_runtime
    principle: "ContextCore adds governance metadata (contracts, provenance, lineage) on top of whatever runtime metadata the framework already produces"
    rationale: |
      Frameworks like LangGraph emit their own telemetry (graph nodes, edges,
      checkpoints). ContextCore does not duplicate this — it adds governance
      metadata: was the contract satisfied? Was provenance maintained? Did the
      lineage remain intact? This layered approach means adopting ContextCore
      never conflicts with existing framework instrumentation.
    anti_patterns:
      - "Duplicating framework-native telemetry in ContextCore spans"
      - "Replacing framework telemetry instead of augmenting it"
    applies_to:
      - contextcore.contract.propagation
      - contextcore.contract.data_lineage
      - contextcore.a2a.gate.pipeline_integrity
      - contextcore.a2a.gate.diagnostic

# NEW — after design_principles, before capabilities
patterns:
  - pattern_id: typed_handoff
    name: "Typed Handoff"
    summary: "Define output contracts, produce Part-based output, validate at boundary"
    capabilities:
      - contextcore.handoff.initiate
      - contextcore.a2a.content_model
      - contextcore.code_generation.contract
    anti_pattern: "String-based context propagation with regex parsing"

  - pattern_id: insight_accumulation
    name: "Insight Accumulation"
    summary: "Emit insights as spans, query accumulated knowledge, compound over time"
    capabilities:
      - contextcore.insight.emit
      - contextcore.insight.query
    anti_pattern: "Storing knowledge in chat transcripts or session logs"

  - pattern_id: constraint_gated
    name: "Constraint-Gated Execution"
    summary: "Read constraints before acting, validate compliance, emit decisions"
    capabilities:
      - contextcore.guidance.read_constraints
      - contextcore.insight.emit
    anti_pattern: "Ignoring governance rules or hardcoding them in prompts"

  - pattern_id: pipeline_communication
    name: "Pipeline Communication"
    summary: "Stages declare typed contracts, produce Part-based output, gates validate at boundaries"
    capabilities:
      - contextcore.pipeline.typed_handoff
      - contextcore.contract.expected_output
      - contextcore.handoff.initiate
    anti_pattern: "Passing untyped strings between pipeline stages and parsing with regex"

  - pattern_id: contract_validation
    name: "Contract Validation (Defense-in-Depth)"
    summary: "Declare contracts in YAML, validate at boundaries, track provenance, emit OTel events"
    capabilities:
      - contextcore.contract.propagation
      - contextcore.contract.schema_compat
      - contextcore.contract.semantic_convention
      - contextcore.contract.causal_ordering
      - contextcore.contract.capability_propagation
      - contextcore.contract.slo_budget
      - contextcore.contract.data_lineage
    anti_pattern: "Propagating context through service boundaries without boundary validation or provenance tracking"

  - pattern_id: a2a_governance
    name: "A2A Governance"
    summary: "Typed contracts at pipeline export boundaries with integrity gates and diagnostic checks"
    capabilities:
      - contextcore.a2a.contract.task_span
      - contextcore.a2a.contract.handoff
      - contextcore.a2a.contract.artifact_intent
      - contextcore.a2a.contract.gate_result
      - contextcore.a2a.gate.pipeline_integrity
      - contextcore.a2a.gate.diagnostic
    anti_pattern: "Exporting pipeline artifacts without structural integrity checks or typed contracts"

capabilities:
  # ... existing capabilities unchanged ...

  # NEW capability entries (REQ-CID-004, REQ-CID-005)
  - capability_id: contextcore.pipeline.typed_handoff
    category: transform
    maturity: beta
    summary: Use A2A typed primitives (Part, ExpectedOutput) for intra-pipeline stage communication

    description:
      agent: |
        Apply A2A communication patterns within a sequential pipeline. Stages declare
        ExpectedOutput contracts. Stage outputs use Part objects (Part.json_data for
        structured fields, Part.text for prose). Gates validate at boundaries using
        ExpectedOutput.fields and completeness_markers.
      human: |
        Enables the same typed communication primitives used for agent-to-agent
        handoffs to work within a multi-stage pipeline.

    triggers:
      - "pipeline communication"
      - "stage contract"
      - "intra-pipeline handoff"
      - "typed stage output"
      - "stage-to-stage"

    delivers_benefit: quality.typed_over_prose

  - capability_id: contextcore.contract.expected_output
    category: transform
    maturity: beta
    summary: Define typed output contracts with required fields, size limits, and completeness markers

    triggers:
      - "output contract"
      - "expected output"
      - "required fields"
      - "completeness markers"
      - "output schema"
      - "typed output"

  # NEW capability entries (REQ-CID-011) — 7 contract layers
  - capability_id: contextcore.contract.propagation
    category: transform
    maturity: beta
    summary: Declare end-to-end field flow contracts, validate at phase boundaries, track provenance

    description:
      agent: |
        Declare PropagationChainSpec contracts in YAML. BoundaryValidator checks
        fields at every phase transition. PropagationTracker stamps FieldProvenance
        (origin_phase, timestamp, value_hash). ChainStatus (INTACT/DEGRADED/BROKEN)
        signals context health. Severity model: BLOCKING/WARNING/ADVISORY.
      human: |
        Ensures that critical context fields flow correctly through pipeline stages.
        When a field like 'domain classification' is set in stage 1 and needed in
        stage 5, the contract system verifies it survived all intermediate stages
        and signals when it degrades to a default value.

    triggers:
      - "context contract"
      - "propagation chain"
      - "boundary validation"
      - "field flow"
      - "context propagation"
      - "chain status"

    delivers_benefit: quality.prescriptive_over_descriptive

  - capability_id: contextcore.contract.schema_compat
    category: transform
    maturity: beta
    summary: Cross-service schema compatibility checking with field mapping and value translation

    triggers:
      - "schema compatibility"
      - "contract drift"
      - "field mapping"
      - "value translation"
      - "schema evolution"

  - capability_id: contextcore.contract.semantic_convention
    category: transform
    maturity: beta
    summary: Attribute naming and enum consistency enforcement across services

    triggers:
      - "semantic convention"
      - "attribute naming"
      - "enum consistency"
      - "naming convention enforcement"

  - capability_id: contextcore.contract.causal_ordering
    category: transform
    maturity: beta
    summary: Cross-boundary event ordering contracts with timestamp verification

    triggers:
      - "causal ordering"
      - "event ordering"
      - "ordering constraint"
      - "happens-before"

  - capability_id: contextcore.contract.capability_propagation
    category: transform
    maturity: beta
    summary: End-to-end permission and capability flow verification through call chains

    triggers:
      - "capability propagation"
      - "permission flow"
      - "authorization chain"
      - "capability verification"

  - capability_id: contextcore.contract.slo_budget
    category: transform
    maturity: beta
    summary: Per-hop latency budget allocation, tracking, and DEGRADED/BROKEN signaling

    triggers:
      - "SLO budget"
      - "latency budget"
      - "budget tracking"
      - "deadline propagation"

  - capability_id: contextcore.contract.data_lineage
    category: transform
    maturity: beta
    summary: Transformation history verification and data provenance tracking

    triggers:
      - "data lineage"
      - "provenance"
      - "transformation history"
      - "data origin"

  # NEW capability entries (REQ-CID-012) — A2A governance contracts
  - capability_id: contextcore.a2a.contract.task_span
    category: transform
    maturity: beta
    summary: Typed contract for task span interchange — validates SpanState v2 compliance, required attributes, and enum values

    description:
      agent: |
        TaskSpanContract validates that exported task spans comply with SpanState v2:
        required fields (task_id, span_name, trace_id, span_id, status), canonical
        enum values (TaskStatus, TaskType, Priority), and structural integrity.
        Used at export boundaries before A2A interchange.
      human: |
        Ensures task data exported from one system can be reliably imported by another.
        Validates that all required fields are present and values use the standard enums.

    triggers:
      - "task span contract"
      - "span validation"
      - "a2a contract"
      - "task interchange"
      - "SpanState validation"

    delivers_benefit: quality.typed_over_prose

  - capability_id: contextcore.a2a.contract.handoff
    category: transform
    maturity: beta
    summary: Typed contract for agent-to-agent handoff — validates ExpectedOutput, lifecycle status, and provenance chain

    description:
      agent: |
        HandoffContract validates handoff integrity: ExpectedOutput schema compliance,
        lifecycle status transitions (pending → accepted → completed/failed), and
        provenance chain continuity. Ensures handoff metadata survives agent boundaries.
      human: |
        Validates that agent-to-agent handoffs carry all required metadata and follow
        the correct lifecycle. Prevents silent data loss during agent delegation.

    triggers:
      - "handoff contract"
      - "a2a contract"
      - "delegation validation"
      - "handoff integrity"

  - capability_id: contextcore.a2a.contract.artifact_intent
    category: transform
    maturity: beta
    summary: Typed declaration of expected artifacts with semantic roles — the Mottainai principle

    description:
      agent: |
        ArtifactIntent declares what artifacts a pipeline run should produce, with
        semantic roles (primary, supporting, diagnostic, provenance). Follows the
        Mottainai Design Principle — respect for what has already been created.
        Gates validate that declared artifacts exist and match their intent.
      human: |
        Declares upfront what a pipeline run should produce (files, reports, data),
        then verifies the output matches the declaration. Prevents silently lost outputs.

    triggers:
      - "artifact intent"
      - "a2a contract"
      - "artifact declaration"
      - "pipeline output"
      - "Mottainai"

  - capability_id: contextcore.a2a.contract.gate_result
    category: transform
    maturity: beta
    summary: Typed result from governance gates — pass/fail/warning with structured diagnostics

    triggers:
      - "gate result"
      - "governance gate"
      - "gate diagnostic"
      - "integrity check result"

  - capability_id: contextcore.a2a.gate.pipeline_integrity
    category: action
    maturity: beta
    summary: "Gate 1: 6 structural integrity checks on exported pipeline artifacts"

    description:
      agent: |
        Runs 6 integrity checks via `contextcore contract a2a-check-pipeline`:
        (1) structural validation, (2) checksum chain verification, (3) provenance
        consistency, (4) mapping completeness, (5) gap parity, (6) design calibration.
        Returns GateResult with pass/fail per check and remediation hints.
      human: |
        Automatically validates that exported pipeline data is structurally sound,
        checksums match, and provenance is traceable — before any downstream system
        consumes the data.

    triggers:
      - "pipeline integrity"
      - "governance gate"
      - "a2a-check-pipeline"
      - "integrity checks"
      - "export validation"

    delivers_benefit: quality.prescriptive_over_descriptive

  - capability_id: contextcore.a2a.gate.diagnostic
    category: action
    maturity: beta
    summary: "Gate 2: Three Questions diagnostic — Was anything lost? Does the shape match? Can we trace the lineage?"

    description:
      agent: |
        Runs the Three Questions diagnostic via `contextcore contract a2a-diagnose`:
        (1) Was anything lost? — artifact count parity between declaration and output.
        (2) Does the shape match? — schema conformance of exported artifacts.
        (3) Can we trace the lineage? — provenance chain from source to output.
        Returns structured diagnostic with per-question results.
      human: |
        Asks three simple questions about exported data to catch common problems:
        missing files, schema drift, and broken provenance chains.

    triggers:
      - "diagnostic gate"
      - "three questions"
      - "a2a-diagnose"
      - "governance diagnostic"
      - "pipeline diagnostic"
```

---

## Integration Points

### Capability Index Emission (OTel)

Design principles and patterns should be emittable via `contextcore terminology emit`.
When the terminology emitter encounters `design_principles` and `patterns` sections,
it should emit them as span events on the manifest span. This makes principles and
patterns queryable in Tempo alongside capabilities.

### Export Pipeline Analysis Guide

REQ-CID-007 adds a cross-reference from the pipeline guide to the capability
manifest. This closes the discoverability gap identified in the root cause
analysis (section 3 of the gap analysis doc).

### Coyote Pipeline

The Coyote pipeline is the original consumer that triggered this gap analysis.
Once the pipeline communication pattern (REQ-CID-002) and typed handoff
capability (REQ-CID-004) are in the manifest, Coyote's design sessions should
discover them via trigger matching.

### startd8-sdk Capability Manifests

The `startd8.workflow.capabilities.yaml` and `startd8.sdk.capabilities.yaml`
manifests should adopt the same `design_principles` and `patterns` schema
for consistency across the ecosystem. This is out of scope for this
requirements document but noted as a follow-on.

---

## Test Requirements

### Validation Tests

| Test | Validates | Priority |
|------|-----------|----------|
| `test_manifest_parses_with_principles` | YAML with `design_principles` parses without error | P1 |
| `test_manifest_parses_with_patterns` | YAML with `patterns` parses without error | P1 |
| `test_existing_capabilities_unchanged` | All 27+ existing capabilities still present and valid | P1 |
| `test_new_triggers_appended` | Pipeline triggers added to A2A capabilities | P1 |
| `test_new_capability_typed_handoff` | `contextcore.pipeline.typed_handoff` is parseable | P2 |
| `test_new_capability_expected_output` | `contextcore.contract.expected_output` is parseable | P2 |
| `test_pattern_references_valid` | All capability_ids in patterns exist in capabilities | P1 |
| `test_principle_applies_to_valid` | All capability_ids in applies_to exist in capabilities | P1 |
| `test_discovery_paths_optional` | Capabilities without discovery_paths parse correctly | P2 |
| `test_version_bumped` | Manifest version is incremented from current | P1 |

### Discoverability Tests

| Test | Validates | Priority |
|------|-----------|----------|
| `test_trigger_search_pipeline` | Searching triggers for "pipeline" matches >= 4 capabilities | P1 |
| `test_trigger_search_output_contract` | Searching triggers for "output contract" matches >= 1 | P2 |
| `test_trigger_search_stage` | Searching triggers for "stage" matches >= 3 | P2 |
| `test_trigger_search_contract` | Searching triggers for "contract" matches >= 7 capabilities | P1 |
| `test_trigger_search_boundary` | Searching triggers for "boundary" or "validation" matches >= 3 | P1 |
| `test_pattern_lookup_typed_handoff` | Pattern `typed_handoff` is findable by pattern_id | P1 |
| `test_pattern_lookup_contract_validation` | Pattern `contract_validation` is findable by pattern_id | P1 |
| `test_principle_lookup_typed_over_prose` | Principle `typed_over_prose` is findable by id | P1 |
| `test_principle_lookup_prescriptive` | Principle `prescriptive_over_descriptive` is findable by id | P1 |
| `test_principle_count` | At least 9 principles exist in design_principles | P1 |
| `test_contract_capabilities_count` | At least 7 `contextcore.contract.*` capabilities exist | P1 |
| `test_trigger_search_governance` | Searching triggers for "governance" matches >= 2 capabilities | P1 |
| `test_trigger_search_a2a_contract` | Searching triggers for "a2a contract" matches >= 4 capabilities | P1 |
| `test_a2a_governance_capabilities_count` | At least 6 `contextcore.a2a.contract.*` + `contextcore.a2a.gate.*` capabilities exist | P1 |
| `test_pattern_lookup_a2a_governance` | Pattern `a2a_governance` is findable by pattern_id | P1 |

### Phase 2 Scope Discovery Tests (REQ-CID-017)

| Test | Validates | Priority |
|------|-----------|----------|
| `test_scope_artifact_types_complete` | Searching for "artifact type" finds capability listing ALL types across ALL categories | P1 |
| `test_scope_beyond_observability` | Searching for "non-observability" OR "onboarding" OR "pipeline-innate" matches >= 1 capability | P1 |
| `test_scope_artifact_categories` | `scope_boundaries.artifact_categories` contains >= 3 categories (observability, onboarding, integrity) | P1 |
| `test_scope_boundary_present` | `scope_boundaries` section exists in manifest | P1 |
| `test_no_false_ceiling_enum` | ArtifactType docstring does NOT say "observability" without qualification | P1 |
| `test_no_false_ceiling_schema` | artifact-intent.schema.json does NOT say "observability" without qualification | P1 |
| `test_cross_reference_coverage` | Every `REQ-CDP-*` doc in `docs/reference/` has >= 1 inbound capability index cross-reference | P1 |
| `test_pipeline_innate_discoverable` | Searching for "pipeline-innate" matches >= 1 capability or scope boundary entry | P1 |
| `test_artifact_type_enum_complete` | `ArtifactType` enum has >= 14 values (8 observability + 4 onboarding + 2 integrity) | P1 |
| `test_artifact_conventions_complete` | `ARTIFACT_OUTPUT_CONVENTIONS` has entry for every `ArtifactType` value | P1 |
| `test_no_orphaned_requirements` | `pipeline-requirements-onboarding.md` is referenced from >= 1 capability index file | P1 |

### Emission Tests

| Test | Validates | Priority |
|------|-----------|----------|
| `test_emit_principles_as_span_events` | Principles emitted via terminology emit | P3 |
| `test_emit_patterns_as_span_events` | Patterns emitted via terminology emit | P3 |
| `test_emit_backward_compat` | Emission without new sections still works | P1 |

### Phase 3 Export Coverage Tests (REQ-CID-019–021)

| Test | Validates | Priority |
|------|-----------|----------|
| `test_mcp_export_count_matches_manifest` | `mcp-tools.json` tool count equals manifest capabilities with `audiences: ["agent"]` | P1 |
| `test_a2a_export_count_matches_manifest` | `agent-card.json` skill count equals manifest capabilities with `audiences: ["agent"]` | P1 |
| `test_mcp_a2a_parity` | `mcp-tools.json` and `agent-card.json` have identical capability IDs (1:1 mapping) | P1 |
| `test_contract_capabilities_exported` | All 7 `contextcore.contract.*` capabilities appear in `mcp-tools.json` | P1 |
| `test_a2a_governance_exported` | All 6 `contextcore.a2a.contract.*` + `contextcore.a2a.gate.*` capabilities appear in `mcp-tools.json` | P1 |
| `test_no_missing_audiences` | All non-internal capabilities in manifest have an explicit `audiences` field | P1 |
| `test_scanner_default_audiences` | `capability_scanner.py` emits `audiences: ["agent", "human"]` by default | P1 |
| `test_builder_audiences_fallback` | `capability_builder.py` applies default audiences when field absent | P1 |
| `test_agent_card_url_not_placeholder` | `agent-card.json` URL does not contain `api.example.com` | P2 |
| `test_manifest_has_a2a_section` | `contextcore.agent.yaml` has top-level `a2a` key with `url` and `provider` | P2 |
| `test_discovery_capability_exists` | `contextcore.discovery.well_known` capability exists in manifest | P2 |
| `test_discovery_trigger_search` | Searching triggers for "discovery" or "well-known" matches >= 1 capability | P2 |

---

## Non-Requirements

The following are explicitly out of scope (Phase 1 + Phase 2 + Phase 3):

1. **New code for pipeline communication.** REQ-CID-004 documents the pattern
   of using existing A2A primitives (Part, ExpectedOutput) within pipelines.
   It does NOT implement new pipeline-specific communication code. The
   primitives already exist in the startd8-sdk.

2. **Restructuring existing capabilities.** The existing 27+ capabilities in
   `contextcore.agent.yaml` are not moved, renamed, or reorganized. New
   sections (`design_principles`, `patterns`) and new entries are additive.

3. **Automated discoverability scoring.** This document does not require a
   system that automatically scores how discoverable a capability is. The
   improvements are manual additions to the manifest based on the gap
   analysis findings.

4. **Cross-ecosystem manifest alignment.** Aligning `startd8.workflow.capabilities.yaml`
   and `startd8.sdk.capabilities.yaml` with the new `design_principles` and
   `patterns` schema is desirable but out of scope. It should be tracked
   separately.

5. **Dynamic capability discovery via OTel queries.** REQ-CID-009 describes
   a navigation skill, not a live TraceQL-based discovery system. Real-time
   capability discovery from Tempo spans is a future enhancement (noted in
   the gap analysis as item 9, low priority).

6. **Capability deprecation or removal.** No existing capabilities are
   deprecated or removed. The `contextcore.handoff.initiate` capability
   retains all existing triggers and schema — new triggers are appended.

7. **Multi-manifest federation.** The patterns section references capabilities
   within a single manifest. Cross-manifest pattern composition (e.g., a
   pattern that spans `contextcore.agent.yaml` and
   `startd8.workflow.capabilities.yaml`) is not addressed.

8. **Extension concern capabilities.** The 9 extension concerns (4E, 5E, 6E,
   7E, 9, 10, 11, 12, 13) have requirements documents but no implementation
   yet. Capability entries for extension concerns will be added when they are
   implemented. Only the 7 implemented contract layers get capability entries
   in this iteration.

9. **Dockerfile or application code as pipeline artifacts.** REQ-CID-013/014
   explicitly classify Dockerfiles, application source code, and CI/CD configs
   as plan deliverables (defined in `.contextcore.yaml` strategy.tactics),
   NOT as pipeline artifacts. The scope boundary makes this distinction
   programmatically clear.

10. **Automated cross-reference graph enforcement at CI time.** REQ-CID-015
    defines the required cross-references but does not mandate a CI check that
    automatically fails on missing cross-references. A manual checklist or
    periodic audit is sufficient for v1. CI enforcement is a future enhancement.

11. **Retroactive renaming of artifact types.** REQ-CID-018 adds new enum values
    but does NOT rename existing ones (e.g., `CAPABILITY_INDEX` stays as-is,
    not renamed to `ONBOARDING_CAPABILITY_INDEX`). Backward compatibility is
    maintained.

12. **Production A2A deployment.** REQ-CID-020 adds the `a2a` manifest section
    with a localhost default URL. Deploying a production A2A endpoint (DNS,
    TLS, authentication middleware, rate limiting) is out of scope. The
    requirement only ensures the manifest structure exists so the generator
    can produce non-placeholder values.

13. **MCP server implementation.** REQ-CID-021 documents the discovery endpoint
    as a capability. It does NOT require implementing an MCP server that serves
    `mcp-tools.json` at runtime. The MCP tools file is a static artifact for
    agent consumption, not a live server endpoint.

14. **Selective audience tagging.** REQ-CID-019 adds `audiences: ["agent", "human"]`
    to all 15 Phase 1 capabilities. A more granular approach (some capabilities
    agent-only, some human-only) is not addressed. All non-internal capabilities
    are assumed to be relevant to both audiences.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-16 23:14:22 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Requirement | Issue Type | Description | Impact | Recommendation |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | REQ-CID-001 | Ambiguity | The acceptance criteria state principles should be "emitted as span attributes or a separate span" — this is an either/or that leaves the implementation decision unspecified. Span attributes have size limits (256 chars default in OTel SDK); span events do not. Principle `rationale` fields are multi-line and will exceed attribute limits. | Implementer must guess; wrong choice requires rework. If span attributes are chosen, rationale will be truncated silently. | Specify: principles are emitted as span events (one event per principle) on the manifest span. Rationale is an event attribute with no truncation. |
| R1-F2 | REQ-CID-002 | Missing detail | The `pipeline_communication` pattern references `contextcore.contract.expected_output` (from REQ-CID-005 Option A) but REQ-CID-005 offers two options (A or B). If Option B is chosen, `contextcore.contract.expected_output` doesn't exist as a capability_id, breaking the pattern reference. | Pattern validation test `test_pattern_references_valid` will fail if Option B is chosen. | Either: (a) mandate Option A in REQ-CID-005, or (b) update `pipeline_communication` pattern to reference `contextcore.handoff.initiate` if Option B is chosen. |
| R1-F3 | REQ-CID-004 | Conflict | REQ-CID-004 sets `category: transform` but the capability describes a communication pattern (bridging A2A to pipeline), not a data transformation. The existing `contextcore.handoff.initiate` uses `category: action`. A pipeline handoff capability should arguably be `category: integration` or `category: action` to match the existing handoff category. | Category mismatch is one of the original root causes of the discoverability failure (requirements doc, section "Root causes"). Adding a new capability with a mismatched category perpetuates the problem. | Change to `category: integration` (consistent with bridging two communication contexts) or `category: action` (consistent with `handoff.initiate`). |
| R1-F4 | REQ-CID-011 | Missing detail | All 7 contract capabilities are `category: transform`, but `contextcore.contract.propagation` performs boundary validation (an action), tracks provenance (a side effect), and emits OTel events (an integration). The uniform `transform` category obscures the multi-faceted nature of contracts. | An agent searching by `category: action` for validation capabilities won't find contracts. This is the same category mismatch root cause identified in the problem statement. | Consider `category: governance` as a new category, or use `category: transform` but add `secondary_categories: [action, integration]` to improve discoverability. |
| R1-F5 | REQ-CID-006 | Ambiguity | The requirement says "New entry (capability or benefit)" — the choice of manifest file is unspecified. If it's a capability in `contextcore.agent.yaml`, it needs the full capability schema (triggers, inputs, outputs). If it's a benefit in `contextcore.benefits.yaml`, it needs the benefit schema. These are different schemas with different fields. | Implementer must choose file and schema without guidance, risking rework. | Specify: add as a benefit entry in `contextcore.benefits.yaml` (since it describes value proposition, not an executable action). Add a cross-reference from `contextcore.agent.yaml` via a new `meta` section or pattern. |
| R1-F6 | REQ-CID-009 | Missing detail | The SKILL.md file location is "TBD based on skill infrastructure." There is no skill infrastructure described in the plan or requirements. If no skill infrastructure exists, this requirement cannot be implemented without first building that infrastructure — making it incorrectly classified as P3 (it has an unstated dependency). | If skill infrastructure doesn't exist, this requirement is blocked. If it does exist, the location should be specified. | Either: (a) specify the skill file location (e.g., `docs/skills/CAPABILITY_INDEX_NAVIGATION.skill.md`), or (b) add a prerequisite noting skill infrastructure must exist. |
| R1-F7 | REQ-CID-010 | Missing detail | "Version is bumped (minor) to reflect the additive changes" — but the requirements don't specify whether all changes land in one version bump or whether intermediate versions are used for phased delivery. If phased (per R1-S4), each phase could bump the patch version, with the final phase bumping minor. | Multiple PRs without version guidance risks version conflicts or consumers seeing partially-complete manifests. | Specify: single minor version bump (v1.10.1 → v1.11.0) applied in the final PR. Intermediate PRs use pre-release versions (v1.11.0-alpha.1, etc.) or hold the version bump until the last merge. |
| R1-F8 | REQ-CID-012 | Inconsistency | The `a2a_governance` pattern in REQ-CID-002 lists 6 capabilities, but the table in REQ-CID-012 also lists 6 entries. However, REQ-CID-002's acceptance criteria say "A2A governance capabilities are referenced from the `contract_validation` pattern OR a new `a2a_governance` pattern." The schema example shows a separate `a2a_governance` pattern. The "or" creates ambiguity — are A2A governance capabilities in `contract_validation`, in `a2a_governance`, or in both? | Pattern composition is unclear. If both patterns reference the same capabilities, there's redundancy. If only one, the other pattern's test may fail. | Specify: A2A governance capabilities are in the `a2a_governance` pattern only (not in `contract_validation`). The `contract_validation` pattern references only the 7 `contextcore.contract.*` capabilities. This matches the schema example. |
| R1-F9 | REQ-CID-003 & REQ-CID-011 | Overlap | REQ-CID-003 adds triggers to existing capabilities (e.g., `contextcore.code_generation.contract` gains `"pipeline output contract"`). REQ-CID-011 adds new capabilities with overlapping triggers (e.g., `contextcore.contract.propagation` has `"context contract"`). Searching for "contract" will return both old capabilities with added triggers and new capabilities. The discoverability test `test_trigger_search_contract` requires >= 7 matches — this is achievable only if counting both old+new. The requirements should clarify whether the >= 7 threshold counts only the 7 new contract capabilities or includes existing ones. | If the threshold is meant to validate that the 7 new contract layers exist, it should test for exactly those 7 capability_ids. If it's a general discoverability metric, the >= 7 is fine but may inflate over time. | Clarify: `test_trigger_search_contract` validates that at least the 7 `contextcore.contract.*` capabilities appear in results. Additional matches from existing capabilities are acceptable but not required for the threshold. |
| R1-F10 | General | Missing requirement | There is no requirement for updating `contextcore.user.yaml` or `contextcore.benefits.yaml` with corresponding entries for the 13 new capabilities. The "Capability manifests affected" header lists all three files, but only REQ-CID-006 mentions `contextcore.benefits.yaml` and no requirement addresses `contextcore.user.yaml`. If user-facing and benefit-facing manifests are not updated in sync, the capability index will have internal inconsistency — the same discoverability gap at a different level. | Users and benefit-oriented agents won't discover the contract system or A2A governance capabilities through their respective manifests. | Add a follow-on requirement (or expand REQ-CID-011/012) to update `contextcore.benefits.yaml` with benefit entries for contract validation and A2A governance, and `contextcore.user.yaml` with user-oriented descriptions. |

---

#### Review Round R2

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-16 23:17:03 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion |
| ---- | ---- | ---- | ---- |
| R2-F1 | ambiguity | medium | The acceptance criteria in REQ-CID-001 (principles) and REQ-CID-002 (patterns) reference capabilities from REQ-CID-011 and REQ-CID-012. This creates a circular dependency for implementation. The requirements should clarify if placeholder IDs are acceptable initially or specify an implementation order. |
| R2-F2 | ambiguity | low | The distinction between `triggers` (REQ-CID-003) and `discovery_paths` (REQ-CID-008) is not sufficiently defined. The document should provide a clear heuristic for when a search term should be a trigger versus a discovery path to ensure consistent application by future contributors. |
| R2-F3 | completeness | medium | REQ-CID-002's acceptance criteria should be updated to explicitly require the `a2a_governance` pattern. The current AC lists five patterns, but the schema example correctly includes this sixth, critical pattern which composes the 6 new capabilities from REQ-CID-012. |
| R2-F4 | ambiguity | high | REQ-CID-009's requirement for a "SKILL.md" file has a "TBD" location and depends on an undefined "skill infrastructure." This makes the requirement untestable and potentially unimplementable. It should be re-scoped as an epic or have the infrastructure dependency listed as a prerequisite risk. |

