# Capability Index Gap Analysis: A2A Communication Discoverability

**Date:** 2026-02-13
**Trigger:** While designing Coyote modular pipeline, the A2A typed communication primitives (Part, Message, Handoff, ExpectedOutput) were the exact solution needed but were NOT discovered during initial plan analysis. They were only found via manual code exploration.
**Question:** Why didn't the capability-index surface these assets during analysis? What needs to change?

---

## 1. What's Well Documented

The `contextcore.agent.yaml` (v1.10.1, 38 capabilities) covers A2A communication thoroughly at the **mechanics** level:

| Capability | Maturity | What's Documented |
|-----------|----------|------------------|
| `contextcore.handoff.initiate` | beta | ExpectedOutput schema with `fields`, `completeness_markers`, `max_lines`, `max_tokens` |
| `contextcore.handoff.receive` | beta | Polling pattern, accept/complete/fail lifecycle |
| `contextcore.a2a.content_model` | beta | Part/Message/Artifact types with factory methods |
| `contextcore.a2a.server` | beta | Flask/FastAPI, JSON-RPC 2.0, .well-known discovery |
| `contextcore.a2a.client` | beta | httpx client, send_and_await pattern |
| `contextcore.a2a.task_adapter` | beta | Bidirectional A2A Task <-> Handoff conversion |
| `contextcore.handoff.input_request` | beta | Mid-handoff clarification with typed input types |
| `contextcore.code_generation.contract` | beta | Size-limited generation with completeness markers |

**Verdict: The mechanics are well-documented. The problem is elsewhere.**

---

## 2. What's NOT Documented — The Gaps

### Gap 1: The "Typed Over Prose" Principle Is Invisible

The single most important design principle — that ContextCore uses **typed structured data instead of natural language parsing** for inter-agent communication — is NOT explicitly stated anywhere in the capability-index.

It's implicit in the structure (every capability has typed `inputs` and `outputs` schemas), but never called out as a principle that downstream consumers should adopt.

**Why this matters:** When an agent or developer analyzes the capability-index to design a new workflow, they see 38 capabilities. But they don't see the *meta-principle* that should govern how those capabilities compose. The Coyote pipeline design session nearly went with "Option A: JSON mode" or "Option B: markdown parsing" — both of which would have been anti-patterns — because the principle wasn't discoverable.

**Recommendation:** Add a top-level `design_principles` section to the agent capability manifest:

```yaml
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
```

### Gap 2: No "Pipeline Communication" Capability

The capability-index models A2A as **agent-to-agent** (separate agents communicating over HTTP/storage). But there's no capability for **stage-to-stage** communication within a single pipeline — which is the pattern Coyote (and any multi-step workflow) needs.

The primitives are the same (Part, ExpectedOutput, typed inputs/outputs), but the use case is different: stages in a pipeline don't need HTTP, storage backends, or polling. They need typed contracts between sequential steps.

**Recommendation:** Add a capability that bridges A2A primitives to pipeline-internal communication:

```yaml
  - capability_id: contextcore.pipeline.typed_handoff
    category: transform
    maturity: beta
    summary: Use A2A typed primitives (Part, ExpectedOutput) for intra-pipeline stage communication

    description:
      agent: |
        Apply A2A communication patterns within a sequential pipeline. Stages declare
        ExpectedOutput contracts. Stage outputs use Part objects (Part.json_data for
        structured fields, Part.text for prose). Gates validate at boundaries using
        ExpectedOutput.fields and completeness_markers. Replaces string-based context
        propagation and regex parsing.
      human: |
        Enables the same typed communication primitives used for agent-to-agent
        handoffs to work within a multi-stage pipeline. Instead of passing strings
        between stages and parsing with regex, each stage declares what it expects
        and what it produces using the same Part/ExpectedOutput contracts.

    delivers_benefit: quality.typed_over_prose
```

### Gap 3: The Value Proposition of Structured Queries Over Documents Is Not Articulated

This is the deepest gap. ContextCore's capability-index YAMLs are themselves an example of the value proposition, but that value proposition is not self-described.

**The argument:** Documents (markdown, confluence, READMEs) suffer from:

| Document Problem | Structured Query Advantage |
|-----------------|--------------------------|
| Version drift — which doc is current? | Time-series database tracks changes over time |
| Failure to update — stale content | Capabilities are emitted by code; if code changes, emission changes |
| Ambiguity about authority — "is this the right doc?" | `manifest_id` + `version` = single source of truth |
| No queryability — must read entire doc to find relevant section | TraceQL/LogQL queries return precise answers |
| No composability — can't combine docs programmatically | Capabilities have typed `inputs`/`outputs` for machine composition |
| No audit trail — who changed what when? | Time-series retention + OTel span history |
| Format inconsistency — every doc is structured differently | YAML schema enforces consistent structure |
| Discovery requires human reading | `triggers` field enables agent auto-discovery |

This table IS the ContextCore value proposition for communication. But it's not in the capability-index. It's not queryable. An agent designing a communication pattern can't discover "why should I use structured queries instead of documents?"

**Recommendation:** This deserves a first-class benefit and/or capability entry:

```yaml
  - capability_id: contextcore.meta.structured_authority
    category: query
    maturity: stable
    summary: Structured queryable capabilities replace ambiguous documents as source of truth

    description:
      human: |
        The capability-index itself demonstrates ContextCore's core value proposition:
        structured, versioned, queryable capability manifests replace ambiguous documents.
        When agents or humans need to know "what can this system do?", they query the
        capability-index — not read a README. The time-series database tracks how
        capabilities evolve. The YAML schema enforces consistency. The triggers field
        enables automated discovery.
      gtm: |
        Stop wondering which document is authoritative. ContextCore's capability index
        is the single, queryable, versioned source of truth for what your system can do.
        When capabilities change, the index updates. When you need to know what happened
        last quarter, query the time-series data — don't dig through Confluence.

    user_benefit: |
      One queryable source of truth replaces scattered, stale documents.
      Time-series data tracks how capabilities evolve over time.
      Agents discover capabilities automatically via structured queries.
```

### Gap 4: ExpectedOutput Deserves Its Own Capability Entry

`ExpectedOutput` is arguably the most important primitive for pipeline communication, but it's buried as a sub-schema inside `handoff.initiate`'s input definition. An agent searching for "how do I define output contracts" won't find it via triggers or capability_id.

**Current state:** ExpectedOutput appears in:
- `handoff.initiate` inputs (as a nested object schema)
- `code_generation.contract` inputs (referenced but not defined)

**Recommendation:** Either promote `ExpectedOutput` to its own capability, or add cross-reference triggers:

```yaml
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
```

### Gap 5: No "Communication Pattern" Category

The capability-index organizes by function (action, query, transform, integration) but not by **pattern**. An agent trying to answer "how should agents communicate?" must mentally assemble the pattern from scattered capabilities.

> **Note (2026-02-16):** See also Gap 6 below — the defense-in-depth contract system adds a second dimension of missing discoverability beyond communication patterns.

Patterns that exist in the code but aren't named in the index:
- **Typed handoff pattern**: ExpectedOutput → Part-based output → validation
- **Insight accumulation pattern**: emit insights → query insights → compound knowledge
- **Constraint-gated pattern**: read constraints → apply constraints → emit decisions
- **Pipeline communication pattern**: stage declares contract → produces typed output → gate validates

**Recommendation:** Add a `patterns` section to the manifest:

```yaml
patterns:
  - pattern_id: typed_handoff
    name: "Typed Handoff"
    summary: "Define output contracts, produce Part-based output, validate at boundary"
    capabilities: [contextcore.handoff.initiate, contextcore.a2a.content_model, contextcore.code_generation.contract]
    anti_pattern: "String-based context propagation with regex parsing"

  - pattern_id: insight_accumulation
    name: "Insight Accumulation"
    summary: "Emit insights as spans, query accumulated knowledge, compound over time"
    capabilities: [contextcore.insight.emit, contextcore.insight.query]
    anti_pattern: "Storing knowledge in chat transcripts or session logs"

  - pattern_id: constraint_gated
    name: "Constraint-Gated Execution"
    summary: "Read constraints before acting, validate compliance, emit decisions"
    capabilities: [contextcore.guidance.read_constraints, contextcore.insight.emit]
    anti_pattern: "Ignoring governance rules or hardcoding them in prompts"
```

### Gap 6: Defense-in-Depth Contract System Has No Capability Index Presence

> **Added 2026-02-16.** This gap was identified after the original gap analysis, when the 7-layer defense-in-depth contract system was implemented (2026-02-14 through 2026-02-15).

ContextCore's most differentiating capability set — contract-based context correctness — is **entirely absent** from the capability index. The 7-layer defense-in-depth system (`src/contextcore/contracts/`) implements:

| Layer | Module | What It Does | Tests |
|-------|--------|-------------|-------|
| L1: Context Propagation | `contracts/propagation/` | Declare field flow, validate at boundaries, track provenance | 62 |
| L2: Schema Compatibility | `contracts/schema_compat/` | Cross-service schema contract validation | ~68 |
| L3: Semantic Conventions | `contracts/semconv/` | Attribute naming and enum consistency enforcement | ~55 |
| L4: Causal Ordering | `contracts/ordering/` | Cross-boundary event ordering contracts | ~45 |
| L5: Capability Propagation | `contracts/capability/` | End-to-end permission flow verification | ~45 |
| L6: SLO Budget Tracking | `contracts/budget/` | Per-hop latency budget allocation and tracking | ~55 |
| L7: Data Lineage | `contracts/lineage/` | Transformation history verification and provenance | ~55 |

Plus 9 extension concerns (temporal staleness, delegation authority, multi-budget, version lineage, quality propagation, checkpoint recovery, config evolution, graph topology, evaluation-gated propagation) designed but not yet implemented.

**Why this matters:** An agent or architect evaluating ContextCore for context correctness — the exact use case the contract system solves — will search for "context validation", "contract", "propagation", "schema checking", "boundary validation" in the capability index and find **nothing**. They would have to discover the `contracts/` module through code exploration.

**What's missing from the capability index:**

1. **No capability entries** for any of the 7 contract layers
2. **No triggers** matching "context contract", "boundary validation", "propagation chain", "schema compatibility", "causal ordering", "SLO budget", "data lineage"
3. **The 6 design principles** from [CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md](../design/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) (Prescriptive Over Descriptive, Design Time Over Runtime, Graceful Degradation, Composable Primitives, Opt-In, Observable Contracts) are not in the `design_principles` section
4. **The 4 shared primitives** (Declare, Validate, Track, Emit) are not captured as a named pattern
5. **The "type checker for service architectures" value proposition** — ContextCore's positioning as the compiler for service compositions — is not articulated anywhere in the capability index

**Recommendation:** Add 7 capability entries (one per contract layer), add the 6 design principles to the `design_principles` section, and add a `contract_validation` pattern to the `patterns` section. See [REQ-CID-011](../design/requirements/REQ_CAPABILITY_INDEX_DISCOVERABILITY.md) for the full requirement.

This is arguably a higher-priority gap than Gaps 1-5, because the contract system IS the differentiator (no other workflow framework treats context propagation as a first-class concern), and it is completely invisible in the capability index.

### Gap 7: A2A Governance Contract System Has No Capability Index Presence

> **Added 2026-02-16.** This gap was identified during framework comparison review, which revealed that ContextCore's A2A governance layer is a unique differentiator not found in LangGraph, AutoGen, CrewAI, or other frameworks.

The A2A governance contract system (`contextcore-a2a-comms-design.md`) implements:

| Component | What It Does | Tests |
|-----------|-------------|-------|
| `TaskSpanContract` | Typed contract for task span interchange — SpanState v2 compliance, required attrs, enum validation | Part of 154 |
| `HandoffContract` | Typed contract for agent-to-agent handoff — ExpectedOutput, lifecycle, provenance chain | Part of 154 |
| `ArtifactIntent` | Typed artifact declaration with semantic roles (Mottainai principle) | Part of 154 |
| `GateResult` | Typed governance gate result — pass/fail/warning with diagnostics | Part of 154 |
| `a2a-check-pipeline` (Gate 1) | 6 structural integrity checks (checksum, provenance, mapping, gap parity, design calibration) | Part of 154 |
| `a2a-diagnose` (Gate 2) | Three Questions diagnostic (lost? shape match? traceable lineage?) | Part of 154 |

Additionally, 2 design principles emerged from the framework comparison analysis:
- **`framework_agnostic_contracts`** — Contracts declare what must be true, not how frameworks achieve it
- **`governance_metadata_over_runtime`** — ContextCore adds governance metadata on top, not duplicating runtime metadata

**Why this matters:** The A2A governance system — typed contracts at pipeline boundaries with integrity gates — was identified through framework comparison as having no equivalent in competing frameworks. An architect evaluating ContextCore for cross-agent data governance would search for "governance", "a2a contract", "pipeline integrity", "gate" in the capability index and find nothing.

**Recommendation:** Add 6 A2A governance capability entries, add the `a2a_governance` pattern, and add principles 8-9 to the `design_principles` section. See [REQ-CID-012](../design/requirements/REQ_CAPABILITY_INDEX_DISCOVERABILITY.md) for the full requirement.

---

## 3. Root Cause: Why These Weren't Discovered

The initial analysis of the Coyote pipeline design examined:
1. startd8-sdk capability-index YAMLs (workflow capabilities)
2. startd8-sdk codebase (workflow implementation)
3. ContextCore EXPORT_PIPELINE_ANALYSIS_GUIDE.md (Defense in Depth principles)
4. Coyote pipeline code (HOWL implementation)

The ContextCore agent capability-index was NOT examined because:

| Reason | Why It Matters |
|--------|---------------|
| **Trigger mismatch** — searching for "pipeline", "stage", "workflow" wouldn't match A2A triggers like "handoff to", "delegate task" | Triggers are tuned for A2A use case, not pipeline-internal use case |
| **Category mismatch** — pipeline communication is not an explicit category | The functional categories (action, query, transform) don't surface the communication *pattern* |
| **Naming mismatch** — "handoff" implies inter-agent delegation, not intra-pipeline stage-to-stage contracts | The capability names are A2A-centric |
| **No cross-reference** — the EXPORT_PIPELINE_ANALYSIS_GUIDE.md (which was examined) doesn't reference the capability-index | Pipeline analysis docs don't point to A2A primitives as the solution |

**This is a discoverability failure, not a documentation failure.** The content exists; it's just not discoverable from the pipeline/workflow entry point.

---

## 4. Recommended Enhancements (Priority Order)

### High Priority

| # | Enhancement | What It Addresses | Effort |
|---|------------|------------------|--------|
| 1 | Add `design_principles` section with "typed over prose" as first principle | Gap 1: invisible meta-principle | 1 hour |
| 2 | Add `patterns` section composing capabilities into named patterns | Gap 5: no pattern-level organization | 2 hours |
| 3 | Add pipeline-specific triggers to A2A capabilities ("stage output contract", "pipeline validation", "typed stage output") | Root cause: trigger mismatch | 30 min |
| 4 | Cross-reference A2A capabilities from EXPORT_PIPELINE_ANALYSIS_GUIDE.md | Root cause: no cross-reference | 30 min |

### Medium Priority

| # | Enhancement | What It Addresses | Effort |
|---|------------|------------------|--------|
| 5 | Add `contextcore.pipeline.typed_handoff` capability entry | Gap 2: no pipeline communication capability | 1 hour |
| 6 | Promote `ExpectedOutput` to its own capability or add dedicated triggers | Gap 4: buried sub-schema | 1 hour |
| 7 | Add `contextcore.meta.structured_authority` capability/benefit entry | Gap 3: value proposition not self-described | 1 hour |

### High Priority (Defense-in-Depth)

> **Added 2026-02-16.** These address Gap 6 — the contract system's absence from the capability index.

| # | Enhancement | What It Addresses | Effort |
|---|------------|------------------|--------|
| 11 | Add 7 contract layer capabilities to agent manifest | Gap 6: no contract capabilities in index | 2 hours |
| 12 | Add defense-in-depth design principles (6 principles) | Gap 6: principles not in design_principles section | 1 hour |
| 13 | Add `contract_validation` pattern (Declare/Validate/Track/Emit) | Gap 6: shared primitives not captured as pattern | 30 min |
| 14 | Add 6 A2A governance capability entries to agent manifest | Gap 7: A2A governance contracts absent from index | 1.5 hours |
| 15 | Add 2 framework-comparison design principles (principles 8-9) | Gap 7: principles from framework comparison not in index | 30 min |
| 16 | Add `a2a_governance` pattern | Gap 7: A2A governance not captured as pattern | 15 min |

### Low Priority (Strategic)

| # | Enhancement | What It Addresses | Effort |
|---|------------|------------------|--------|
| 8 | Add `discovery_paths` to capabilities — "if you're looking for X, this is what you need" | Root cause: entry-point dependent discovery | 2 hours |
| 9 | Emit capability-index as OTel resource attributes for time-series queryability | Gap 3: walking the talk on structured queries | 1-2 days |
| 10 | Create a capability-index skill (SKILL.md) that agents use to navigate the index | Root cause: no skill for systematic index navigation | 1 hour |

---

## 5. The Meta-Insight

The capability-index is ContextCore's most powerful differentiator — it's the embodiment of "structured queries over documents." But it doesn't describe *itself* as such. The value proposition of:

> **Structured, versioned, queryable capability manifests that live in time-series databases inherently solve version drift, stale documentation, authority ambiguity, and format inconsistency — problems that no amount of markdown can fix because documents are static snapshots while capabilities are living, emitted data.**

...is the single most important thing ContextCore offers to human-to-human, human-to-agent, and agent-to-agent communication. And it's not in the capability-index.

The capability-index should be self-aware: it should describe why it exists, what problems it solves, and why a structured query against a time-series database is fundamentally superior to reading a document — including the document you're reading right now.
