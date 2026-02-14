# Capability Index Structural Enhancement Plan

**Date:** 2026-02-13
**Status:** Draft — Pending Validation
**Author:** Analysis collaboration (human + agent)
**Prerequisite Reading:** `docs/capability-index/CAPABILITY_INDEX_GAP_ANALYSIS.md`
**Relates to:** Coyote Modular Pipeline Design (`wayfinder/contextcore-coyote/docs/MODULAR_PIPELINE_DESIGN.md`)

---

## 1. Problem Statement

### What Happened

While designing the Coyote modular pipeline, the team needed a structured way for pipeline stages to exchange typed data — replacing regex-based parsing of LLM markdown output. ContextCore's A2A communication primitives (`Part`, `Message`, `Handoff`, `ExpectedOutput`) were the exact solution, but they were **not discovered** during the initial design analysis despite the capability-index being available.

### Why It Happened

The capability-index currently functions as a **flat catalog** — it documents *what* each capability does, but not *why* you'd reach for it from different entry points. Discovery depends on already knowing the right vocabulary:

| What the designer searched for | What the index calls it |
|-------------------------------|------------------------|
| "stage output contract" | `handoff.initiate` → `expected_output` |
| "typed data between pipeline steps" | `a2a.content_model` → `Part` |
| "replace regex parsing of LLM output" | No match — no trigger or capability addresses this |
| "how should agents exchange structured data" | Implicit in structure, never stated as principle |

### What This Reveals

The capability-index embodies ContextCore's most important differentiator — **structured, versioned, queryable capability data replaces ambiguous documents** — but it doesn't support its own thesis. It is structured vertically (each capability is self-contained) but lacks the horizontal connective tissue that enables discovery across capabilities, from problems to solutions, and from principles to implementations.

The index needs to be **reverse-engineered** — both horizontally (across capabilities) and vertically (from principles down to evidence and from evidence up to principles) — to enable **top-down and bottom-up discovery and browsability**.

---

## 2. Design Philosophy

### 2.1 The Two-Direction Discovery Principle

Every element in the capability-index should be reachable from at least two directions:

```
                    PRINCIPLES (why)
                         │
               ┌─────────┼─────────┐
               ▼         ▼         ▼
            PATTERNS (how to compose)
               │         │         │
         ┌─────┼────┐    │    ┌────┼─────┐
         ▼     ▼    ▼    ▼    ▼    ▼     ▼
      CAPABILITIES (what exists)
         │     │    │    │    │    │     │
         ▼     ▼    ▼    ▼    ▼    ▼     ▼
       EVIDENCE (proof it works)
```

- **Top-down:** "I believe in typed data exchange" → which patterns implement this? → which capabilities power those patterns? → show me the code.
- **Bottom-up:** "I see `Part.json_data()`" → what pattern does this serve? → what principle does this embody? → why does this matter?
- **Horizontal:** "I'm using `handoff.initiate`" → what else do I need? → what capabilities compose with this? → what patterns combine them?
- **Problem-in:** "I'm parsing LLM output with regex and it's brittle" → which anti-pattern is this? → which principle addresses it? → which pattern solves it? → which capabilities implement the pattern?

### 2.2 The Self-Describing Index Principle

The capability-index should describe *itself* — why structured queryable data beats documents, how the index is organized, and how to navigate it. An agent encountering the index for the first time should be able to understand the navigational model without external documentation.

### 2.3 Compatibility Principle

All structural enhancements are **additive**. No existing fields are removed or renamed. Existing consumers of the capability-index YAML continue to work unchanged. New structural elements are optional and progressively enhance discoverability.

---

## 3. Current State Inventory

### 3.1 Existing Manifests

| File | `manifest_id` | Version | Entries | Purpose |
|------|---------------|---------|---------|---------|
| `contextcore.agent.yaml` | `contextcore.agent` | 1.6.0 | 27 capabilities | Agent-facing capabilities |
| `contextcore.user.yaml` | `contextcore.user` | 1.3.0 | ~15 capabilities | User/GTM-facing capabilities |
| `contextcore.benefits.yaml` | `contextcore.benefits` | 1.2.0 | ~25 benefits | Value statements per persona |
| `contextcore.pain_points.yaml` | `contextcore.pain_points` | 2.2.0 | Pain points per persona | Cost/ROI quantification |
| `roadmap.yaml` | `contextcore.roadmap` | 2.1.0 | Phased roadmap items | Implementation tracking |
| `startd8.workflow.benefits.yaml` | (cross-project) | — | startd8 benefits | External project reference |

### 3.2 Current Per-Capability Schema

```yaml
- capability_id: string           # Unique ID
  category: enum                  # action | query | transform | observe | integration
  maturity: enum                  # stable | beta | experimental | planned
  summary: string                 # One-line description
  audiences: list[enum]           # [agent, human, gtm]
  description:
    agent: string                 # Compact, structured for LLM consumption
    human: string                 # Readable, contextual
    gtm: string                   # (optional) Go-to-market framing
  user_benefit: string            # (optional) Value statement
  triggers: list[string]          # Discovery keywords/phrases
  inputs: json_schema             # Input contract
  outputs: json_schema            # Output contract
  evidence: list[Evidence]        # Code refs, tests, docs
  confidence: float               # 0.0–1.0
  anti_patterns: list[string]     # (optional) What NOT to do
  risk_flags: list[string]        # (optional) Known risks
  traceql_examples: list[Example] # (optional) Query examples
  roadmap: string                 # (optional) Future plans
  delivers_benefit: string        # (optional) Link to benefits manifest
```

### 3.3 Current Cross-Referencing

| From | To | Via |
|------|----|-----|
| Capability → Benefit | `delivers_benefit` field | One-way |
| Benefit → Capability | `delivered_by` field | One-way |
| Pain Point → Benefit | `benefits_manifest_ref` | Manifest-level |
| Roadmap → Capability | `capabilities` list per phase | One-way |
| Capability → Capability | **None** | Gap |
| Principle → Capability | **None** | Gap |
| Pattern → Capability | **None** | Gap |
| Problem → Pattern | **None** | Gap |

### 3.4 What's Missing

| Element | Current State | Impact |
|---------|--------------|--------|
| Design principles | Not in index | Can't discover *why* capabilities are designed the way they are |
| Named patterns | Not in index | Can't discover *how* capabilities compose into solutions |
| Cross-references between capabilities | Not in index | Can't discover *what goes together* |
| Problem-centric triggers | Only verb-centric triggers exist | Can't enter from "I have this problem" |
| Discovery paths per capability | Not in index | Can't reach capabilities from unfamiliar entry points |
| Index self-description | Not in index | Index can't explain its own value |

---

## 4. Proposed Structural Enhancements

### Overview

Seven structural additions, organized into three tiers. Each tier builds on the previous, and each addition is independently deployable.

```
Tier 1: Foundation          Tier 2: Connective Tissue       Tier 3: Self-Awareness
─────────────────           ──────────────────────────       ──────────────────────
P1: design_principles       P4: cross_references             P6: index self-description
P2: patterns                P5: discovery_paths              P7: problem-to-solution index
P3: enriched triggers
```

---

### P1: Design Principles (Manifest-Level Section)

**What:** A new top-level section in capability manifests that articulates the governing principles behind capability design.

**Why:** Principles are the highest-level navigational anchor. An agent or human who understands the principles can reason about which capabilities are appropriate *even for use cases not explicitly documented*.

**Where:** Added to `contextcore.agent.yaml` initially. Each manifest can carry its own principles section.

**Schema:**

```yaml
design_principles:

  - id: typed_over_prose
    principle: "All inter-agent data exchange uses typed schemas, not natural language parsing"
    rationale: |
      Structured data eliminates version drift, format ambiguity, and regex fragility.
      ExpectedOutput.fields replaces regex section extraction.
      Part.json_data() replaces string interpolation.
      Time-series databases make structured data queryable and trackable over time.
    evidence:
      - type: code
        ref: src/contextcore/agent/handoff.py
        description: "ExpectedOutput model with typed fields, max_lines, completeness_markers"
      - type: code
        ref: src/contextcore/models/part.py
        description: "Part model with json_data(), text() typed accessors"
    anti_patterns:
      - id: regex_parsing
        description: "Parsing LLM markdown output with regex to extract structured fields"
        why_harmful: "Brittle to format changes; fails silently on unexpected output"
      - id: string_context
        description: "Passing raw strings between pipeline stages instead of typed objects"
        why_harmful: "No validation, no schema evolution, no discoverability"
      - id: document_contracts
        description: "Using document sections as the contract between agents"
        why_harmful: "Documents drift from code; no machine validation possible"
    implements:
      - contextcore.handoff.initiate
      - contextcore.a2a.content_model
      - contextcore.code_generation.contract
      - contextcore.contract.expected_output  # New (P1 informs P2)

  - id: validate_at_boundary
    principle: "Validate data at every boundary crossing — between agents, stages, or systems"
    rationale: |
      Boundary validation catches errors at the point of entry, not downstream.
      Defense in Depth principle: never trust upstream output is well-formed.
      Combined with typed schemas, boundary validation becomes declarative.
    evidence:
      - type: code
        ref: src/contextcore/contracts/validate.py
        description: "Contract validation engine"
    anti_patterns:
      - id: end_only_validation
        description: "Validating only the final result of a multi-step pipeline"
        why_harmful: "By the time validation fails, upstream cause is lost"
      - id: trust_upstream
        description: "Assuming upstream agent output is well-formed"
        why_harmful: "LLM outputs are inherently stochastic; validation is not optional"
    implements:
      - contextcore.handoff.receive
      - contextcore.contract.validate

  - id: structured_over_documents
    principle: "Structured queryable data replaces ambiguous documents as the source of truth"
    rationale: |
      Documents suffer from version drift, stale content, authority ambiguity,
      format inconsistency, and lack of queryability. Structured data in a
      time-series database inherently solves all five:
      - Versioned (manifest_id + version)
      - Live (emitted by code, not written by humans)
      - Authoritative (single queryable source)
      - Consistent (YAML schema enforced)
      - Queryable (TraceQL, LogQL, PromQL)
    evidence:
      - type: doc
        ref: docs/capability-index/contextcore.agent.yaml
        description: "The capability-index itself is the evidence"
    anti_patterns:
      - id: readme_as_source
        description: "Treating READMEs or Confluence pages as authoritative capability lists"
        why_harmful: "Documents are static snapshots; capabilities are living, emitted data"
      - id: manual_capability_docs
        description: "Manually maintaining capability documentation separate from code"
        why_harmful: "Guaranteed to drift from implementation"
    implements:
      - contextcore.meta.structured_authority  # New (see P7)

  - id: observe_dont_report
    principle: "Derive project status from existing artifacts — don't require manual reporting"
    rationale: |
      Manual status reporting is redundant work. Commits, PRs, CI results, and
      deployments already contain status information. Observe it, don't duplicate it.
    evidence:
      - type: code
        ref: examples/03_artifact_status_derivation.py
        description: "Status derivation from Git activity"
    anti_patterns:
      - id: dual_entry
        description: "Requiring developers to update status in both code and project management tools"
        why_harmful: "Double work; the human-entered status inevitably lags behind reality"
    implements:
      - contextcore.status.auto_derive
      - contextcore.status.stale_detection
```

**Effort:** 2–3 hours (draft 4–6 principles, map to existing capabilities)
**Validates:** Tier 1 foundation is in place

---

### P2: Named Patterns (Manifest-Level Section)

**What:** A new top-level section that names and describes **composition patterns** — how capabilities work together to solve categories of problems.

**Why:** Patterns bridge the gap between abstract principles and concrete capabilities. They are the "how" between "why" (principles) and "what" (capabilities). They are the primary vehicle for **horizontal discovery** — "I'm using capability X, what else do I need?"

**Where:** Added to `contextcore.agent.yaml` initially. Patterns compose capabilities within and across manifests.

**Schema:**

```yaml
patterns:

  - pattern_id: typed_handoff
    name: "Typed Handoff"
    summary: "Define output contracts, produce Part-based output, validate at boundary"
    problem: |
      Agents or pipeline stages exchange data as unstructured strings, requiring
      brittle regex parsing. Format changes break downstream consumers silently.
    solution: |
      1. Declare ExpectedOutput with required fields, size constraints, and
         completeness markers
      2. Produce output as Part objects (Part.json_data for structured fields,
         Part.text for prose summaries)
      3. Validate output against ExpectedOutput contract at the boundary
      4. Reject malformed output immediately (fail loud, fail early, fail specific)
    capabilities:
      - contextcore.handoff.initiate
      - contextcore.a2a.content_model
      - contextcore.code_generation.contract
      - contextcore.contract.expected_output  # New
    implements_principles:
      - typed_over_prose
      - validate_at_boundary
    triggers:
      - phrase: "typed output contract"
        context: pipeline_design
      - phrase: "replace regex parsing"
        context: refactoring
      - phrase: "structured handoff between stages"
        context: pipeline_design
      - phrase: "LLM output validation"
        context: quality
      - phrase: "agent output schema"
        context: a2a_communication
    anti_patterns:
      - regex_parsing
      - string_context
      - document_contracts
    example: |
      # Define what the investigation stage must produce
      expected = ExpectedOutput(
          type="investigation_result",
          fields=["root_cause", "affected_services", "severity", "evidence"],
          max_tokens=2000,
          completeness_markers=["root_cause identified", "severity assessed"]
      )

      # Handoff carries the contract
      handoff = Handoff(
          to_agent="investigator",
          capability_id="investigate_error",
          expected_output=expected,
          inputs={"error": error_context}
      )

  - pattern_id: insight_accumulation
    name: "Insight Accumulation"
    summary: "Emit insights as spans, query accumulated knowledge, compound over time"
    problem: |
      Agent knowledge is trapped in chat transcripts, session logs, or ephemeral
      memory. Lessons learned during one task are not available to future tasks.
    solution: |
      1. Emit structured insights (decisions, lessons, blockers) as OTel spans
      2. Query prior insights before starting new work
      3. Knowledge compounds: each task benefits from all prior insights
      4. Time-series storage enables trend analysis ("are we getting better?")
    capabilities:
      - contextcore.insight.emit
      - contextcore.insight.query
    implements_principles:
      - structured_over_documents
      - observe_dont_report
    triggers:
      - phrase: "accumulate agent knowledge"
        context: learning
      - phrase: "lessons from previous tasks"
        context: continuous_improvement
      - phrase: "agent memory across sessions"
        context: architecture
    anti_patterns:
      - readme_as_source
      - manual_capability_docs

  - pattern_id: constraint_gated_execution
    name: "Constraint-Gated Execution"
    summary: "Read constraints before acting, validate compliance, emit decisions"
    problem: |
      Agents operate without awareness of governance rules, project constraints,
      or quality thresholds. Constraints are hardcoded in prompts rather than
      queried from a live source.
    solution: |
      1. Read active constraints from CRD/storage before executing
      2. Apply constraints to scope agent behavior
      3. Validate output against constraints at boundary
      4. Emit decisions with constraint references for audit trail
    capabilities:
      - contextcore.guidance.read_constraints
      - contextcore.guidance.respond
      - contextcore.insight.emit
    implements_principles:
      - validate_at_boundary
    triggers:
      - phrase: "enforce governance rules"
        context: compliance
      - phrase: "agent guardrails"
        context: safety
      - phrase: "project constraints"
        context: planning
    anti_patterns:
      - id: hardcoded_constraints
        description: "Hardcoding governance rules in agent prompts"

  - pattern_id: pipeline_stage_communication
    name: "Pipeline Stage Communication"
    summary: "Apply A2A typed primitives for intra-pipeline stage-to-stage data exchange"
    problem: |
      Pipeline stages pass data as unstructured dictionaries or concatenated strings.
      Each stage must parse its predecessor's output format ad-hoc. Changes to one
      stage's output silently break downstream stages.
    solution: |
      1. Each stage declares an output contract (typed Pydantic model or ExpectedOutput)
      2. Stage output uses Part objects for typed content units
      3. Validation gates between stages check outputs against contracts
      4. Context fingerprints ensure data integrity across the pipeline
    capabilities:
      - contextcore.a2a.content_model
      - contextcore.handoff.initiate
      - contextcore.contract.expected_output  # New
    implements_principles:
      - typed_over_prose
      - validate_at_boundary
    triggers:
      - phrase: "stage-to-stage data exchange"
        context: pipeline_design
      - phrase: "pipeline context propagation"
        context: pipeline_design
      - phrase: "typed pipeline stages"
        context: refactoring
    anti_patterns:
      - string_context
      - end_only_validation
    relates_to:
      - pattern_id: typed_handoff
        relationship: "adapts for intra-pipeline use"
```

**Effort:** 3–4 hours (draft 4–6 patterns, map capabilities and principles)
**Validates:** Horizontal discovery across capabilities; problem-to-solution navigation

---

### P3: Enriched Triggers with Problem-Context Tags

**What:** Extend existing per-capability `triggers` to support tagged entries with problem-context metadata, alongside existing plain-string triggers (backward-compatible).

**Why:** Current triggers are verb-centric ("handoff to", "delegate task"). Problem-centric triggers ("replace regex parsing", "typed stage output") enable discovery from the problem space, not just the solution space.

**Current format (preserved):**

```yaml
triggers:
  - "handoff to"           # Plain string — still works
  - "delegate task"        # Plain string — still works
```

**Enhanced format (additive):**

```yaml
triggers:
  - "handoff to"                                  # Existing — unchanged
  - "delegate task"                               # Existing — unchanged
  - phrase: "typed output contract"               # New — tagged
    context: pipeline_design
  - phrase: "replace regex parsing of LLM output" # New — tagged
    context: refactoring
  - phrase: "stage boundary validation"           # New — tagged
    context: pipeline_design
  - phrase: "structured agent response format"    # New — tagged
    context: a2a_communication
```

**Context tags (standardized vocabulary):**

| Tag | Meaning |
|-----|---------|
| `pipeline_design` | Building or refactoring multi-step pipelines |
| `a2a_communication` | Agent-to-agent data exchange |
| `refactoring` | Improving existing code/architecture |
| `quality` | Output quality, validation, testing |
| `learning` | Knowledge accumulation, lessons learned |
| `compliance` | Governance, audit, constraints |
| `architecture` | System design decisions |
| `incident_response` | Real-time incident handling |
| `continuous_improvement` | Process improvement over time |
| `safety` | Guardrails, boundaries, risk mitigation |
| `planning` | Task/sprint/project planning |

**Capabilities to receive enriched triggers (highest priority):**

| Capability | New Triggers to Add | Context |
|-----------|-------------------|---------|
| `contextcore.handoff.initiate` | "typed output contract", "stage output schema" | `pipeline_design` |
| `contextcore.a2a.content_model` | "typed data between stages", "replace string passing" | `pipeline_design`, `refactoring` |
| `contextcore.code_generation.contract` | "LLM output validation", "size-bounded generation" | `quality` |
| `contextcore.handoff.receive` | "validate agent output", "boundary validation" | `quality`, `pipeline_design` |
| `contextcore.insight.emit` | "record agent decision", "audit trail" | `compliance`, `learning` |

**Effort:** 1–2 hours (add 3–5 tagged triggers to 8–10 key capabilities)
**Validates:** Problem-centric discovery works; can search by context tag

---

### P4: Cross-References Between Capabilities

**What:** A new per-capability field that declares relationships to other capabilities.

**Why:** Capabilities don't exist in isolation. Knowing "I need `handoff.initiate`" should immediately surface "you'll also need `a2a.content_model` and `handoff.receive`." Currently, an agent must read every capability to find these relationships.

**Schema:**

```yaml
- capability_id: contextcore.handoff.initiate
  # ... existing fields ...

  cross_references:
    - capability_id: contextcore.a2a.content_model
      relationship: uses
      description: "Handoffs carry Part objects as typed payloads"
    - capability_id: contextcore.handoff.receive
      relationship: paired_with
      description: "Initiating a handoff requires a receiver to process it"
    - capability_id: contextcore.contract.expected_output
      relationship: defines_contract_for
      description: "ExpectedOutput schema is the contract handoffs enforce"
    - capability_id: contextcore.code_generation.contract
      relationship: specialized_by
      description: "Code generation uses handoff contracts with size limits"
```

**Relationship types (standardized vocabulary):**

| Relationship | Meaning | Direction |
|-------------|---------|-----------|
| `uses` | This capability depends on the referenced capability | A uses B |
| `paired_with` | These capabilities are used together (symmetric) | A ↔ B |
| `specialized_by` | The referenced capability is a specialization of this one | A generalized, B specialized |
| `defines_contract_for` | This capability provides the contract the other enforces | A defines, B enforces |
| `extends` | The referenced capability adds behavior to this one | A base, B extension |
| `alternative_to` | These capabilities serve similar purposes (choose one) | A or B |

**Effort:** 2–3 hours (map relationships for 15–20 most-connected capabilities)
**Validates:** Horizontal discovery; "what else do I need?" answerable from any capability

---

### P5: Discovery Paths (Per-Capability)

**What:** A new per-capability field that provides **alternative entry points** — phrases an agent or human might use when they don't yet know the capability exists.

**Why:** This is the deepest fix for the discoverability failure. Triggers assume you know what you're looking for ("handoff to"). Discovery paths assume you **don't** — they answer "if you're trying to solve X, this capability is relevant because Y."

**Schema:**

```yaml
- capability_id: contextcore.a2a.content_model
  # ... existing fields ...

  discovery_paths:
    - context: pipeline_design
      entry_phrase: "How should stages exchange data in a multi-step pipeline?"
      relevance: |
        Part model provides typed content units (TEXT, JSON, TRACE, etc.) that
        replace string passing between stages. Part.json_data() carries structured
        data; Part.text() carries prose. No regex needed.
    - context: refactoring
      entry_phrase: "How do I stop parsing LLM output with regex?"
      relevance: |
        LLM output can be structured into Part objects: JSON parts for data,
        TEXT parts for summaries. The receiving stage calls json_data() instead
        of parsing markdown with regex.
    - context: a2a_communication
      entry_phrase: "What content types can agents exchange?"
      relevance: |
        Part supports TEXT, JSON, TRACE, CODE, and custom types. Message wraps
        multiple Parts. Artifact adds versioning and metadata.
    - context: architecture
      entry_phrase: "How do I design a typed interface between agents?"
      relevance: |
        Part + Message + ExpectedOutput form a typed communication protocol.
        Agents declare what they produce (Part types) and what they expect
        (ExpectedOutput fields), enabling compile-time-like safety at runtime.
```

**Effort:** 3–4 hours (add 2–4 discovery paths to 10–15 key capabilities)
**Validates:** Discovery from unfamiliar entry points; agent can navigate from problem to capability

---

### P6: Index Self-Description (Manifest-Level)

**What:** A new top-level section in each manifest that describes the index itself — its navigational model, structural elements, and how to use it for discovery.

**Why:** An agent encountering the capability-index for the first time should understand *how to navigate it* without reading external documentation. The index should be self-aware.

**Schema:**

```yaml
# At the top of contextcore.agent.yaml (or a shared index-of-indexes)

index_meta:
  purpose: |
    This capability-index is a structured, versioned, queryable manifest of what
    ContextCore can do. It replaces ambiguous documents (READMEs, Confluence pages,
    design docs) as the authoritative source of truth for capabilities.

  navigational_model: |
    The index supports four discovery directions:

    TOP-DOWN: Start from a design principle → find patterns that implement it
              → find capabilities that power the pattern → see evidence.

    BOTTOM-UP: Start from a code reference or capability → find what pattern
               it serves → find what principle it embodies → understand why.

    HORIZONTAL: Start from any capability → follow cross_references to find
                related capabilities → follow patterns to see full compositions.

    PROBLEM-IN: Start from a problem or anti-pattern → find the principle that
                addresses it → find the pattern that solves it → find the
                capabilities that implement the pattern.

  structural_elements:
    - element: design_principles
      scope: manifest
      purpose: "Governing principles — the 'why' behind capability design"
      navigate_to: "patterns (which principles does this pattern implement?)"
    - element: patterns
      scope: manifest
      purpose: "Composition patterns — the 'how' of combining capabilities"
      navigate_to: "capabilities (which capabilities power this pattern?), principles (which principles govern this pattern?)"
    - element: capabilities
      scope: per-entry
      purpose: "Individual capabilities — the 'what' of the system"
      navigate_to: "cross_references (what goes together?), discovery_paths (how to find this?), evidence (proof it works)"
    - element: cross_references
      scope: per-capability
      purpose: "Relationships between capabilities"
      navigate_to: "related capabilities"
    - element: discovery_paths
      scope: per-capability
      purpose: "Alternative entry points for reaching this capability"
      navigate_to: "the capability itself, from unfamiliar starting points"
    - element: triggers
      scope: per-capability
      purpose: "Keywords and phrases for automated discovery"
      navigate_to: "the capability itself, both plain-text and context-tagged"

  why_structured_over_documents: |
    This index exists because documents fail at scale:

    | Document Problem                    | Structured Index Advantage                    |
    |-------------------------------------|-----------------------------------------------|
    | Version drift — which doc is current? | manifest_id + version = single source of truth |
    | Stale content — failure to update   | Emitted by code; if code changes, emission changes |
    | Authority ambiguity                 | One queryable manifest per domain               |
    | No queryability                     | TraceQL/LogQL return precise answers             |
    | No composability                    | Typed inputs/outputs enable machine composition  |
    | No audit trail                      | Time-series retention tracks changes over time   |
    | Format inconsistency                | YAML schema enforces consistent structure        |
    | Discovery requires human reading    | triggers + discovery_paths enable auto-discovery |
```

**Effort:** 1–2 hours
**Validates:** New users/agents can self-orient within the index

---

### P7: Problem-to-Solution Index (New Manifest or Section)

**What:** A dedicated section (or standalone manifest) that indexes **problems and anti-patterns** as first-class entry points, each pointing to the principle, pattern, and capabilities that address them.

**Why:** This completes the "problem-in" discovery direction. Currently, anti-patterns are scattered across individual capabilities. Centralizing them creates a "what's wrong and how to fix it" reference that mirrors how people actually seek help.

**Two options for location:**

- **Option A:** New section in `contextcore.agent.yaml` (keeps everything in one file)
- **Option B:** New manifest `contextcore.anti_patterns.yaml` (separates concerns, enables independent versioning)

**Recommendation:** Option B — a new manifest. Anti-patterns are a cross-cutting concern that spans multiple capability manifests. They deserve their own versioned, queryable manifest.

**Schema:**

```yaml
manifest_id: contextcore.anti_patterns
name: ContextCore Anti-Pattern Index
version: "1.0.0"
description: |
  Indexed anti-patterns that ContextCore capabilities address. Each entry
  describes a problem, explains why it's harmful, and points to the principle,
  pattern, and capabilities that provide the solution.

  USE THIS INDEX WHEN: You've identified a problem in your codebase and want
  to find the ContextCore solution. Start from the anti-pattern, follow the
  links to the pattern, then to the capabilities.

anti_patterns:

  - anti_pattern_id: regex_parsing_llm_output
    name: "Regex Parsing of LLM Output"
    category: data_exchange
    description: |
      Parsing LLM markdown output with regex to extract structured fields.
      Common in pipeline stages that need structured data from an LLM but
      lack typed output contracts.
    why_harmful: |
      - Brittle: breaks when LLM changes formatting
      - Silent failure: regex mismatch returns empty, not an error
      - Untestable: can't validate regex against all possible LLM outputs
      - No schema evolution: format changes require regex updates everywhere
    symptoms:
      - "re.search() or re.findall() on LLM response text"
      - "Markdown section headers used as field delimiters"
      - "Stage output is a dict built from string extraction"
    addressed_by:
      principle: typed_over_prose
      pattern: typed_handoff
      capabilities:
        - contextcore.a2a.content_model
        - contextcore.contract.expected_output
        - contextcore.handoff.initiate
    triggers:
      - "regex parsing"
      - "parse LLM output"
      - "extract sections from markdown"
      - "brittle output parsing"

  - anti_pattern_id: string_context_propagation
    name: "String-Based Context Propagation"
    category: data_exchange
    description: |
      Passing raw strings or untyped dictionaries between pipeline stages.
      Each stage must know the implicit format of its predecessor's output.
    why_harmful: |
      - No validation: malformed data propagates silently
      - No discoverability: new developers must read code to understand format
      - No evolution: adding a field requires updating all consumers
      - No integrity: data can be mutated without detection
    symptoms:
      - "result['summary'] or context.get('previous_output')"
      - "Concatenating strings to build stage context"
      - "Dict keys known only by convention, not by schema"
    addressed_by:
      principle: typed_over_prose
      pattern: pipeline_stage_communication
      capabilities:
        - contextcore.a2a.content_model
        - contextcore.contract.expected_output

  - anti_pattern_id: end_only_validation
    name: "End-Only Validation"
    category: validation
    description: |
      Validating only the final output of a multi-step pipeline. Intermediate
      stage outputs are trusted without verification.
    why_harmful: |
      - Root cause obscured: final validation failure doesn't indicate which stage failed
      - Wasted compute: later stages process garbage from earlier failures
      - Debugging is archaeological: must trace backward through all stages
    symptoms:
      - "Validation logic only in the last stage"
      - "No assertions or checks between stages"
      - "Errors surface as 'invalid final output' with no upstream context"
    addressed_by:
      principle: validate_at_boundary
      pattern: typed_handoff
      capabilities:
        - contextcore.handoff.receive
        - contextcore.contract.validate

  - anti_pattern_id: document_as_source_of_truth
    name: "Documents as Source of Truth"
    category: knowledge_management
    description: |
      Treating READMEs, Confluence pages, or design docs as the authoritative
      source for what a system can do, how it's configured, or what its status is.
    why_harmful: |
      - Version drift: document lags behind code within days
      - Authority confusion: multiple documents claim to be current
      - No queryability: must read entire document to find one answer
      - No time-series: can't track how the system evolved over time
    symptoms:
      - "Check the wiki for the latest architecture"
      - "I'll update the README after this sprint"
      - "Which Confluence page has the current API spec?"
    addressed_by:
      principle: structured_over_documents
      pattern: insight_accumulation
      capabilities:
        - contextcore.meta.structured_authority
```

**Effort:** 3–4 hours (draft 8–12 anti-patterns, map to principles/patterns/capabilities)
**Validates:** "Problem-in" discovery direction works; agents can navigate from symptoms to solutions

---

## 5. New Capabilities to Add

The structural enhancements surface the need for two new capabilities that should be added to `contextcore.agent.yaml`:

### 5.1 `contextcore.contract.expected_output`

Currently buried as a sub-schema in `handoff.initiate`. Deserves promotion to first-class capability for independent discoverability.

```yaml
- capability_id: contextcore.contract.expected_output
  category: transform
  maturity: beta
  summary: Define typed output contracts with required fields, size limits, and completeness markers

  audiences: [agent]

  description:
    agent: |
      Define what a stage or agent must produce. In: {type: string, fields: string[],
      max_lines?: int, max_tokens?: int, completeness_markers?: string[]}.
      Use to declare contracts between pipeline stages, in handoff initiation,
      and in code generation requests. Validates output structure at boundary.
    human: |
      ExpectedOutput is a contract that defines what an agent or pipeline stage
      must produce. It specifies required fields, size constraints, and markers
      that indicate completeness. Gates and validators use this contract to
      reject malformed output at boundaries.

  triggers:
    - "output contract"
    - "expected output"
    - "required fields"
    - "completeness markers"
    - "output schema"
    - "typed output"
    - phrase: "what should a stage produce"
      context: pipeline_design
    - phrase: "define agent output format"
      context: a2a_communication
    - phrase: "size-bounded output"
      context: quality

  evidence:
    - type: code
      ref: src/contextcore/agent/handoff.py
      description: "ExpectedOutput model definition"

  confidence: 0.85

  cross_references:
    - capability_id: contextcore.handoff.initiate
      relationship: used_by
      description: "Handoffs carry ExpectedOutput as their contract"
    - capability_id: contextcore.a2a.content_model
      relationship: paired_with
      description: "Part objects are what ExpectedOutput validates"
    - capability_id: contextcore.code_generation.contract
      relationship: specialized_by
      description: "Code generation adds code-specific constraints"

  delivers_benefit: quality.typed_over_prose
```

### 5.2 `contextcore.meta.structured_authority`

The index's value proposition, made queryable.

```yaml
- capability_id: contextcore.meta.structured_authority
  category: query
  maturity: stable
  summary: Structured queryable capability manifests replace ambiguous documents as source of truth

  audiences: [agent, human, gtm]

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
    agent: |
      Query capability manifests instead of reading documentation. In: {manifest_id: string,
      capability_id?: string, trigger?: string, context?: string}. Out: Capability[].
      Manifest data is structured YAML with typed schemas, versioned, and queryable.

  triggers:
    - "capability lookup"
    - "what can the system do"
    - "source of truth"
    - phrase: "replace documentation with structured data"
      context: architecture
    - phrase: "queryable capability registry"
      context: planning

  delivers_benefit: quality.structured_authority
```

---

## 6. Implementation Plan

### Tier 1: Foundation (Week 1)

| Step | What | File(s) | Effort | Depends On |
|------|------|---------|--------|------------|
| 1.1 | Add `design_principles` section (P1) | `contextcore.agent.yaml` | 2h | — |
| 1.2 | Add `patterns` section (P2) | `contextcore.agent.yaml` | 3h | 1.1 |
| 1.3 | Add enriched triggers to 10 key capabilities (P3) | `contextcore.agent.yaml` | 2h | 1.2 (uses pattern context tags) |
| 1.4 | Add `contextcore.contract.expected_output` capability (5.1) | `contextcore.agent.yaml` | 1h | 1.1 |
| 1.5 | Validate: run trigger search simulation — can "pipeline stage communication" reach A2A capabilities? | Manual test | 30m | 1.3 |

**Exit criteria:** An agent searching for "typed data between pipeline stages" finds `a2a.content_model`, `handoff.initiate`, and `contract.expected_output` via triggers and/or patterns.

### Tier 2: Connective Tissue (Week 2)

| Step | What | File(s) | Effort | Depends On |
|------|------|---------|--------|------------|
| 2.1 | Add `cross_references` to 15 key capabilities (P4) | `contextcore.agent.yaml` | 3h | Tier 1 |
| 2.2 | Add `discovery_paths` to 10 key capabilities (P5) | `contextcore.agent.yaml` | 3h | Tier 1 |
| 2.3 | Add `contextcore.meta.structured_authority` capability (5.2) | `contextcore.agent.yaml` or `contextcore.user.yaml` | 1h | 2.1 |
| 2.4 | Update `contextcore.benefits.yaml` with new `delivered_by` links | `contextcore.benefits.yaml` | 1h | 2.3 |
| 2.5 | Validate: run "problem-in" simulation — can "regex parsing LLM output" navigate to solution? | Manual test | 30m | 2.2 |

**Exit criteria:** Starting from any capability, an agent can reach all related capabilities within 1 hop via `cross_references`. Starting from a discovery path entry phrase, an agent reaches the target capability.

### Tier 3: Self-Awareness (Week 3)

| Step | What | File(s) | Effort | Depends On |
|------|------|---------|--------|------------|
| 3.1 | Add `index_meta` self-description (P6) | `contextcore.agent.yaml` | 1h | Tier 2 |
| 3.2 | Create `contextcore.anti_patterns.yaml` (P7) | New file | 4h | Tier 1 (principles), Tier 2 (cross-refs) |
| 3.3 | Cross-link anti-patterns manifest from `contextcore.agent.yaml` | `contextcore.agent.yaml` | 30m | 3.2 |
| 3.4 | Update `roadmap.yaml` with capability-index enhancement tracking | `roadmap.yaml` | 30m | 3.2 |
| 3.5 | Final validation: end-to-end discovery test from all four directions | Manual test | 1h | All |

**Exit criteria:** All four discovery directions (top-down, bottom-up, horizontal, problem-in) work. The index self-describes its navigational model. Anti-patterns link to solutions.

---

## 7. Migration and Compatibility

### 7.1 No Breaking Changes

All enhancements are additive:

| Change | Backward Compatible? | Reason |
|--------|---------------------|--------|
| `design_principles` section | Yes | New top-level key; existing consumers ignore unknown keys |
| `patterns` section | Yes | New top-level key |
| Tagged triggers | Yes | Mixed list of strings and objects; string-only consumers see strings |
| `cross_references` field | Yes | New optional field per capability |
| `discovery_paths` field | Yes | New optional field per capability |
| `index_meta` section | Yes | New top-level key |
| New manifest file | Yes | Separate file; no impact on existing manifests |
| New capabilities | Yes | Additional entries in existing list |

### 7.2 Consumer Update Path

Consumers that want to leverage new structure:

| Consumer Type | What to Update | When |
|--------------|---------------|------|
| Agent reading triggers | Handle both `string` and `{phrase, context}` entries | Tier 1 |
| Agent building dependency graphs | Read `cross_references` field | Tier 2 |
| Agent doing problem-based search | Read `discovery_paths` field | Tier 2 |
| Agent orienting to index | Read `index_meta` section | Tier 3 |
| Agent searching anti-patterns | Read new `contextcore.anti_patterns.yaml` | Tier 3 |

### 7.3 Risks and Mitigations

| Risk | Impact | Mitigation | Owner |
|------|--------|------------|-------|
| **Authority centralization** | Single point of failure: if the index is wrong, every consumer is wrong. High-value target for tampering. | Cryptographic signing (R3-S1), access control (R3-S2), health checks (R3-S8), deployment/rollback procedures (R3-S7). Define fallback behavior when index is unavailable. | TBD |
| **Schema sprawl** | New structural elements proliferate without governance; schema becomes unmaintainable. | JSON Schema (Tier 3), controlled vocabularies for tags/relationship types (R1-S12, R1-S17), governance process (R2-S9). | TBD |
| **Cross-reference maintenance burden** | Bidirectional consistency drifts; broken references accumulate silently. | Automated validation in CI (R1-S6, R3-S11, R4-S16), pre-commit hooks. | TBD |
| **Staleness** | Discovery paths and triggers become outdated as capabilities evolve. | Freshness thresholds, completeness metrics (R1-S13), ownership per element (R1-S8). | TBD |
| **Single-file scalability** | `contextcore.agent.yaml` exceeds manageable size; readability and LLM context efficiency suffer. | Estimate final file size before Tier 2; define splitting strategy if >1000 lines (R1-S4). | TBD |

---

## 8. Validation Criteria

### 8.1 Discovery Test Scenarios

Each scenario should be answerable purely from the enhanced capability-index, without reading code or external documents:

| # | Scenario | Entry Point | Expected Path |
|---|----------|-------------|---------------|
| 1 | "How should pipeline stages exchange typed data?" | Discovery path on `a2a.content_model` | → Part model → typed_handoff pattern → handoff.initiate + expected_output |
| 2 | "I'm parsing LLM output with regex and it's brittle" | Anti-pattern `regex_parsing_llm_output` | → typed_over_prose principle → typed_handoff pattern → a2a.content_model + expected_output |
| 3 | "What goes with handoff.initiate?" | Cross-reference on `handoff.initiate` | → a2a.content_model (uses), handoff.receive (paired_with), expected_output (defines_contract_for) |
| 4 | "Why does ContextCore use typed schemas?" | Design principle `typed_over_prose` | → rationale + evidence + implements list |
| 5 | "How do I define what an agent must produce?" | Trigger "output contract" or "expected output" | → contract.expected_output → cross-ref to handoff.initiate |
| 6 | "What is this capability-index and how do I use it?" | `index_meta` section | → navigational model + structural elements + why_structured_over_documents |
| 7 | "How do agents exchange structured data in ContextCore?" | Pattern `typed_handoff` or tagged trigger `a2a_communication` | → capabilities list → evidence |

### 8.2 Quantitative Targets

| Metric | Current | Target | How Measured |
|--------|---------|--------|-------------|
| Discovery hops from problem to capability | 3+ (read all capabilities) | 1–2 (pattern or anti-pattern → capability) | Count navigation steps in test scenarios |
| Capabilities with cross-references | 0 | 15+ | Count `cross_references` entries |
| Capabilities with discovery paths | 0 | 10+ | Count `discovery_paths` entries |
| Named patterns | 0 | 4+ | Count `patterns` entries |
| Named design principles | 0 | 4+ | Count `design_principles` entries |
| Anti-patterns indexed | ~15 (scattered, per-capability) | 8+ centralized + per-capability | Count entries in anti-patterns manifest |

---

## 9. Relationship to Coyote Pipeline Design

This plan directly addresses **Open Question Q1** in the Coyote Modular Pipeline Design (`MODULAR_PIPELINE_DESIGN.md`):

> **Q1:** Should contracted stages use JSON mode for LLM output?
>
> **Answer (Option D — A2A-Native):** Use ContextCore's existing A2A primitives (Part, ExpectedOutput, Message) for stage communication. The structural enhancements in this plan ensure these primitives are *discoverable* for this use case.

Specifically:

| Coyote Need | Capability-Index Enhancement That Addresses It |
|-------------|-----------------------------------------------|
| "How should stages exchange data?" | P5: Discovery path on `a2a.content_model` |
| "What replaces regex parsing?" | P7: Anti-pattern `regex_parsing_llm_output` |
| "What output contract should stages declare?" | P1: New capability `contract.expected_output` |
| "What pattern should the pipeline follow?" | P2: Pattern `pipeline_stage_communication` |
| "Why typed over string?" | P1: Principle `typed_over_prose` |

Once Tier 1 is implemented, the Coyote pipeline design analysis would have discovered the A2A primitives without manual code exploration.

---

## 10. Future Considerations

### 10.1 Time-Series Emission

Currently the capability-index is a static YAML file. The logical next step — consistent with the `structured_over_documents` principle — is to **emit capability-index entries as OTel resource attributes**, making them queryable via TraceQL:

```
{ resource.capability.manifest_id = "contextcore.agent" && span.capability.id = "contextcore.handoff.initiate" }
```

This would make the index truly time-series-native: you could query "what capabilities existed last month?" or "when was this capability added?"

**Effort:** 1–2 days. **Priority:** After Tier 3 is validated.

### 10.2 Capability-Index Skill (SKILL.md)

A dedicated skill that agents use to navigate the capability-index systematically — following patterns, cross-references, and discovery paths rather than scanning linearly.

**Effort:** 1 hour. **Priority:** After Tier 2.

### 10.3 Cross-Manifest Patterns

Some patterns span multiple manifests (e.g., a pattern that involves agent capabilities from `contextcore.agent.yaml` and user-facing capabilities from `contextcore.user.yaml`). A future enhancement would add a manifest-of-manifests that indexes cross-manifest patterns.

**Effort:** 2–3 hours. **Priority:** After Tier 3.

### 10.4 Automated Validation

Linting rules to enforce structural integrity:

- Every `implements` reference in a principle resolves to an existing `capability_id`
- Every `cross_references.capability_id` resolves to an existing capability
- Every pattern's `capabilities` list resolves to existing capabilities
- Every anti-pattern's `addressed_by.capabilities` list resolves to existing capabilities
- Bidirectional consistency: if A references B, B should reference A

**Effort:** 1 day. **Priority:** After Tier 2 (to catch consistency errors during Tier 3).

---

## 11. Open Questions

| # | Question | Options | Recommendation |
|---|----------|---------|---------------|
| Q1 | Should `design_principles` live in each manifest or in a shared file? | (a) Per-manifest, (b) Shared `contextcore.principles.yaml`, (c) Per-manifest with shared imports | **(a)** initially — keep co-located for simplicity. Refactor to (c) if principles diverge across manifests. |
| Q2 | Should `patterns` live in the capability manifest or in a separate file? | (a) In `contextcore.agent.yaml`, (b) Separate `contextcore.patterns.yaml` | **(a)** initially — patterns are tightly coupled to capabilities. Move to (b) if patterns span multiple manifests. |
| Q3 | How should we version-track the structural schema itself? | (a) Document in index_meta, (b) Formal JSON Schema for the YAML, (c) Both | **(c)** — document for humans, JSON Schema for automation. JSON Schema in Tier 3. |
| Q4 | Should the anti-patterns manifest cross-reference the `pain_points.yaml`? | (a) Yes — pain points are the business framing of anti-patterns, (b) No — keep them independent | **(a)** — anti-patterns are technical; pain points are business. Cross-reference enriches both. |
| Q5 | Should we add `discovery_paths` to the benefits manifest too? | (a) Yes — benefits should be discoverable from problem context, (b) No — benefits are already persona-indexed | **(a)** in Tier 3 — but lower priority than agent capability discovery. |
| Q6 | How should we mitigate the authority centralization risk (single source of truth = single point of failure)? | (a) Rely on R3-S1/S2/S7/S8 mitigations, (b) Add redundancy/fallback behavior, (c) Conduct failure-mode analysis before Tier 1 | **(a)** — accepted mitigations (signing, access control, health checks, rollback) are sufficient for Tier 1. Conduct failure-mode analysis (b/c) before cross-project federation. |

---

## Summary

This plan transforms the ContextCore capability-index from a **flat catalog** into a **navigable knowledge graph** by adding five structural elements (principles, patterns, enriched triggers, cross-references, discovery paths) and two meta-awareness elements (self-description, anti-pattern index).

The result: any agent or human can discover the right ContextCore capabilities from **any starting point** — whether they begin with a problem, a principle, a related capability, or a question they don't yet know how to phrase.

Every enhancement is additive, backward-compatible, and independently deployable across three tiers of increasing depth.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **architecture**: 7 suggestions applied (R1-S1, R1-S4, R1-S7, R1-S11, R1-S14, R2-S8, R2-S10)
- **data**: 3 suggestions applied (R1-S6, R1-S12, R2-S9)
- **interfaces**: 3 suggestions applied (R1-S5, R1-S17, R2-S4)
- **ops**: 6 suggestions applied (R3-S7, R3-S8, R3-S11, R4-S9, R1-S8, R2-S3)
- **risks**: 5 suggestions applied (R3-S18, R1-S2, R1-S16, R2-S1, R2-S12)
- **security**: 9 suggestions applied (R3-S1, R3-S2, R3-S3, R3-S4, R3-S10, R3-S14, R3-S16, R3-S20, R4-S11)
- **validation**: 8 suggestions applied (R3-S19, R4-S16, R1-S3, R1-S9, R1-S13, R1-S18, R2-S2, R2-S6)

### Areas Needing Further Review

All areas have reached the substantially addressed threshold.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Define a formal YAML schema (JSON Schema) for all new structural elements before Tier 1 implementation begins, not deferred to Tier 3. | claude-4 (claude-opus-4-6) | The plan explicitly defers JSON Schema to Tier 3 (Q3), meaning 2+ weeks of unvalidated YAML accumulates. Schema-first is a foundational best practice that prevents costly rework and enables all downstream validation suggestions. This is correctly classified as critical. | 2026-02-13 16:28:04 UTC |
| R1-S2 | Add an explicit risk register section covering schema sprawl, cross-reference maintenance burden, staleness, and single-file scalability. | claude-4 (claude-opus-4-6) | The plan introduces 7 new structural elements and significant complexity but contains zero risk analysis. For an enterprise architectural plan, this is a significant omission. A risk register with mitigations and owners is standard practice. | 2026-02-13 16:28:04 UTC |
| R1-S3 | Replace manual validation steps (1.5, 2.5, 3.5) with automated, repeatable test scripts runnable in CI. | claude-4 (claude-opus-4-6) | Manual testing contradicts the plan's own `observe_dont_report` principle and is not repeatable or scalable. Automated discovery-path tests are essential for regression testing as the index evolves. This is a high-value, high-alignment suggestion. | 2026-02-13 16:28:04 UTC |
| R1-S4 | Address single-file scalability by estimating final file size and defining a file-splitting strategy if contextcore.agent.yaml exceeds manageable limits. | claude-4 (claude-opus-4-6) | Adding principles, patterns, cross-references, discovery paths, and enriched triggers to 27+ capabilities will substantially grow the file. Both human readability and LLM context window efficiency are at risk. The plan acknowledges multi-file concerns in §10.3 but defers them too late. | 2026-02-13 16:28:04 UTC |
| R1-S5 | Specify how consumers should parse the mixed-type triggers list (strings and objects) with a normalization algorithm or reference parser. | claude-4 (claude-opus-4-6) | P3 introduces backward-compatible mixed triggers but provides no canonical parsing approach. Without this, multiple consumers will implement differently, creating subtle behavioral divergence. A reference parser or pseudocode is low-effort and high-impact. | 2026-02-13 16:28:04 UTC |
| R1-S6 | Define referential integrity constraints for all cross-manifest links and enforce them via pre-commit hooks or CI. | claude-4 (claude-opus-4-6) | The plan introduces extensive cross-references across manifests but defers automated linting to §10.4. Without pre-commit enforcement, broken references will silently accumulate — exactly the 'drift' problem the plan criticizes in documents. This should be promoted to Tier 2 at latest. | 2026-02-13 16:28:04 UTC |
| R1-S7 | Clarify the relationship type vocabulary and specify whether cross-references should be stored unidirectionally or bidirectionally. | claude-4 (claude-opus-4-6) | The plan uses `uses` in P4 but `used_by` in §5.1 without defining both in the vocabulary. Whether both directions are authored or one is derived is a fundamental data modeling decision that affects all tooling. This must be resolved before Tier 2 implementation. | 2026-02-13 16:28:04 UTC |
| R1-S8 | Define ownership and maintenance responsibilities for each new structural element (principles, patterns, cross-references, anti-patterns). | claude-4 (claude-opus-4-6) | The plan is silent on who maintains these structures after creation. Without defined ownership and review cadence, the new structures will decay — directly contradicting the `structured_over_documents` principle the plan champions. | 2026-02-13 16:28:04 UTC |
| R1-S9 | Add negative test scenarios to §8.1 to validate precision (queries that should NOT match) alongside recall. | claude-4 (claude-opus-4-6) | All 7 test scenarios verify correct capabilities are found but none verify incorrect capabilities are excluded. A discovery system with high recall but no precision is useless. Negative scenarios are essential for meaningful validation. | 2026-02-13 16:28:04 UTC |
| R1-S11 | Define conflict resolution strategy for when multiple patterns claim overlapping capability sets or give contradictory guidance. | claude-4 (claude-opus-4-6) | typed_handoff and pipeline_stage_communication share 2 of 3 capabilities and have a relates_to link, but no guidance exists for agents choosing between overlapping patterns. Without disambiguation rules, agents will make arbitrary choices. Pattern precedence or selection heuristics are needed. | 2026-02-13 16:28:04 UTC |
| R1-S12 | Formalize the context tag vocabulary from P3 as a controlled enumeration with governance for additions. | claude-4 (claude-opus-4-6) | P3 lists 11 context tags but doesn't specify if the vocabulary is open or closed. If open, tag proliferation will degrade search precision. A closed enum with a versioned governance process is low-cost and prevents entropy. | 2026-02-13 16:28:04 UTC |
| R1-S13 | Add completeness metrics tracking the percentage of capabilities with each new structural element populated. | claude-4 (claude-opus-4-6) | §8.2 sets absolute targets (15+ cross-references) but doesn't track coverage percentage. Knowing 15 of 27 capabilities have cross-references (56%) is essential for prioritization and progress tracking. Low effort to add. | 2026-02-13 16:28:04 UTC |
| R1-S14 | Clarify how the capability-index interacts with the Coyote SKILL.md mechanism at runtime — is it a skill input, a skill itself, or a queried resource? | claude-4 (claude-opus-4-6) | §10.2 mentions a 'Capability-Index Skill' and §9 ties to Coyote, but the runtime consumption model is undefined. Whether the index is embedded in prompts, queried via API, or loaded as context fundamentally affects structural decisions. This should be resolved early, not deferred. | 2026-02-13 16:28:04 UTC |
| R1-S16 | Identify and mitigate the risk that enriched index structures increase LLM token consumption when agents load the full manifest. | claude-4 (claude-opus-4-6) | The plan enriches a YAML file that agents consume in context windows. Adding principles, patterns, cross-references, and discovery paths to 27 capabilities could significantly increase token count. LLM context windows are finite and expensive. A selective loading strategy should be defined proactively. | 2026-02-13 16:28:04 UTC |
| R1-S17 | Specify anti-pattern category values as a controlled vocabulary enumeration. | claude-4 (claude-opus-4-6) | P7 introduces categories (data_exchange, validation, knowledge_management) informally. Formalizing them as an enum in the schema prevents proliferation and maintains navigational value. Low effort, consistent with R1-S12 for context tags. | 2026-02-13 16:28:04 UTC |
| R1-S18 | Define what constitutes a 'hop' operationally in the '1–2 hops' discovery metric from §8.2. | claude-4 (claude-opus-4-6) | Without a clear definition, the metric is unmeasurable and therefore meaningless. Is following a cross_reference one hop? Is reading patterns and then navigating to a capability two hops? This must be defined for the metric to be actionable. | 2026-02-13 16:28:04 UTC |
| R2-S1 | Re-evaluate all effort estimates with implementation teams as current estimates appear overly optimistic. | gemini-2.5 (gemini-2.5-pro) | The estimates (e.g., 2-3 hours for design principles with evidence mapping) likely don't account for schema design (per R1-S1), data validation, cross-reference verification, and testing. Underestimating effort is a significant project risk that could force scope reduction or timeline slippage. | 2026-02-13 16:28:04 UTC |
| R2-S2 | Build an automated test suite for Discovery Test Scenarios instead of relying on manual simulations. | gemini-2.5 (gemini-2.5-pro) | This directly overlaps with R1-S3 and is equally valid. Manual validation is not repeatable or suitable for regression testing. Automated tests are essential for ensuring index integrity as it evolves. Accepting both R1-S3 and R2-S2 as they reinforce the same critical need. | 2026-02-13 16:28:04 UTC |
| R2-S3 | Define the manifest lifecycle management process including source control, change approval workflow, and CI/CD for publishing. | gemini-2.5 (gemini-2.5-pro) | The manifests are being positioned as critical 'source of truth' artifacts. Without a defined operational process for proposing, approving, and deploying changes, the manifests face the same governance problems the plan criticizes in documents. | 2026-02-13 16:28:04 UTC |
| R2-S4 | Specify the intended agent consumption mechanism — library, API, or direct file parsing with prescribed search logic. | gemini-2.5 (gemini-2.5-pro) | The plan describes rich navigation patterns (top-down, bottom-up, horizontal, problem-in) but never specifies how agents actually execute these navigations at runtime. This is a critical interface gap that blocks consumer implementation and could lead to inconsistent client-side logic. | 2026-02-13 16:28:04 UTC |
| R2-S6 | Integrate automated validation (linter) from Future Considerations into the core plan, delivered in Tier 2. | gemini-2.5 (gemini-2.5-pro) | This aligns with R1-S6 and is critical. Finding structural integrity issues after creation is inefficient. A linter that validates referential integrity in CI should be part of Tier 2, not a future consideration. The plan's own §10.4 acknowledges this need but defers it too late. | 2026-02-13 16:28:04 UTC |
| R2-S8 | Re-classify Time-Series Emission (§10.1) from a small future consideration to a major, separate architectural initiative. | gemini-2.5 (gemini-2.5-pro) | The '1-2 days' estimate for introducing an OTel observability stack, collectors, and time-series database is a severe underestimate. This fundamentally changes the index from static files to a dynamic event-driven system. Misrepresenting scope creates massive planning risk. | 2026-02-13 16:28:04 UTC |
| R2-S9 | Define a governance process for extending controlled vocabularies such as context tags and relationship types. | gemini-2.5 (gemini-2.5-pro) | This complements R1-S12 and R1-S17. Without a process for managing vocabulary extensions, tags and relationship types will sprawl, degrading discovery quality. A lightweight proposal/approval process is sufficient. | 2026-02-13 16:28:04 UTC |
| R2-S10 | Formalize the relates_to field for patterns, which appears in an example but is not defined in the P2 schema. | gemini-2.5 (gemini-2.5-pro) | The pipeline_stage_communication pattern uses relates_to in its example, but this field is not part of the formal P2 schema. Implicit fields in examples create ambiguity. If pattern-to-pattern relationships are a feature, they must be formally specified. | 2026-02-13 16:28:04 UTC |
| R2-S12 | Add a Data Quality Assurance section requiring peer review of populated metadata for accuracy and adherence to schemas. | gemini-2.5 (gemini-2.5-pro) | The initiative's success depends entirely on the accuracy and completeness of the new metadata. Without a quality assurance step, data could be populated hastily or incorrectly, undermining the discovery goal. Peer review of the first batch is a practical safeguard. | 2026-02-13 16:28:04 UTC |
| R3-S1 | Add a threat model for manifest integrity with cryptographic signing and provenance attestation. | claude-4 (claude-opus-4-6) | Manifests are positioned as the single source of truth; without integrity verification, tampered manifests poison all consumers. This is a fundamental security gap for an authoritative knowledge base. | 2026-02-13 16:34:44 UTC |
| R3-S2 | Define an access control model for who/what can modify capability manifests, patterns, and anti-patterns. | claude-4 (claude-opus-4-6) | Write-path authorization is essential when manifests are the canonical registry. Unauthorized modification is equivalent to redefining system capabilities. Git-native controls (branch protection, CODEOWNERS) are practical and low-cost to specify. | 2026-02-13 16:34:44 UTC |
| R3-S3 | Add input validation and sanitization requirements for all new structured fields to prevent injection attacks. | claude-4 (claude-opus-4-6) | Free-text fields like triggers, discovery_paths, and anti-pattern symptoms that agents consume and interpolate are genuine prompt injection vectors. Schema constraints (max length, allowed characters) are essential and low-cost to define. | 2026-02-13 16:34:44 UTC |
| R3-S4 | Define trust boundaries for cross-manifest references, especially cross-project manifests. | claude-4 (claude-opus-4-6) | The plan already shows cross-project references (startd8.workflow.benefits.yaml) and proposes cross-manifest patterns (§10.3) without defining trust scope. Without trust boundaries, confused-deputy scenarios are possible where agents follow references into untrusted capability spaces. | 2026-02-13 16:34:44 UTC |
| R3-S7 | Define manifest deployment and rollback procedures for promoting changes across environments. | claude-4 (claude-opus-4-6) | Manifests are the single source of truth and a broken manifest can affect all consuming agents simultaneously. Defining rollback procedures is operationally essential and aligns with the tiered deployment model already in the plan. | 2026-02-13 16:34:44 UTC |
| R3-S8 | Add health checks and freshness/integrity validation for the capability index. | claude-4 (claude-opus-4-6) | The plan's own 'observe_dont_report' principle should apply to the index itself. Freshness thresholds and structural integrity checks via CI are practical, low-cost, and prevent silent degradation of the authoritative source. | 2026-02-13 16:34:44 UTC |
| R3-S10 | Add a 'deprecated' lifecycle state to the capability maturity enum with secure deprecation procedures. | claude-4 (claude-opus-4-6) | The absence of a deprecated state is a genuine schema gap. Without it, there's no way to mark capabilities as unsafe while maintaining backward compatibility. This is a small, high-value addition to the maturity enum. | 2026-02-13 16:34:44 UTC |
| R3-S11 | Promote cross-reference bidirectional consistency validation from future consideration to Tier 2 implementation. | claude-4 (claude-opus-4-6) | Section 10.4 already identifies this need but defers it. With 15+ cross-references planned for Tier 2, integrity validation should be concurrent, not deferred. This aligns with previously accepted suggestions about automated validation. | 2026-02-13 16:34:44 UTC |
| R3-S14 | Add behavioral compatibility analysis for schema versioning, ensuring older agents degrade safely when new structural constraints are invisible. | claude-4 (claude-opus-4-6) | The plan claims backward compatibility for parsing but doesn't address behavioral safety. An older agent ignoring cross_references could use capabilities incorrectly (e.g., handoff.initiate without handoff.receive). Defining safe degradation behavior is important and low-cost to document. | 2026-02-13 16:34:44 UTC |
| R3-S16 | Require validation that all evidence references are resolvable and point to authorized repositories. | claude-4 (claude-opus-4-6) | Evidence references are implicit trust anchors. CI validation that evidence refs resolve to existing files in authorized repositories is straightforward to implement and prevents both accidental breakage and malicious external references. This fits naturally into the §10.4 automated validation work. | 2026-02-13 16:34:44 UTC |
| R3-S18 | Add an explicit risk entry for authority centralization — the plan concentrates all capability truth in YAML manifests creating a single point of failure. | claude-4 (claude-opus-4-6) | This is the fundamental architectural trade-off of the plan and should be explicitly acknowledged with defined mitigations. It ties together several accepted suggestions (R3-S1, R3-S2, R3-S7, R3-S8) into a coherent risk narrative. Low effort, high clarity value. | 2026-02-13 16:34:44 UTC |
| R3-S19 | Add adversarial discovery test scenarios to Section 8.1 testing malformed, ambiguous, or misleading queries. | claude-4 (claude-opus-4-6) | All seven current test scenarios are positive cases. Negative/adversarial testing is essential for a system agents will autonomously navigate. Adding 3-5 adversarial scenarios is low effort and directly validates the robustness of the structural enhancements. | 2026-02-13 16:34:44 UTC |
| R3-S20 | Add secrets scanning requirements to prevent accidentally embedded secrets in manifest free-text fields. | claude-4 (claude-opus-4-6) | Manifests contain substantial free-text (examples, descriptions, evidence) authored by developers. Integrating existing secrets scanners (truffleHog, gitleaks) into CI for manifest files is trivial to implement and prevents a real class of accidental exposure. | 2026-02-13 16:34:44 UTC |
| R4-S9 | Establish a federated ownership model with per-manifest team ownership for operational scaling. | gemini-2.5 (gemini-2.5-pro) | The plan shows cross-project manifests and proposes cross-manifest patterns (§10.3) but doesn't define ownership. Adding a top-level owner field and governance process is lightweight, prevents bottlenecks, and complements accepted R3-S2 (access control). Essential for scaling beyond a single team. | 2026-02-13 16:34:44 UTC |
| R4-S11 | Mandate secure YAML parsing (e.g., yaml.safe_load) to prevent code execution via malicious manifest content. | gemini-2.5 (gemini-2.5-pro) | YAML deserialization vulnerabilities are well-documented and trivially exploitable. Requiring safe parsing mode is a one-line change with significant security impact. This is a concrete, actionable, and low-cost requirement that should be a documented standard for all manifest consumers. | 2026-02-13 16:34:44 UTC |
| R4-S16 | Promote automated bidirectional link validation from future consideration (§10.4) to a Tier 1/2 CI requirement. | gemini-2.5 (gemini-2.5-pro) | Reinforces already accepted R3-S11. Broken links in the knowledge graph undermine the entire discovery model. This validation is simple to implement as a CI check and should not be deferred to 'future considerations' when it's foundational to structural integrity. | 2026-02-13 16:34:44 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S10 | Assess whether discovery paths and anti-pattern descriptions could leak sensitive architectural details if exposed externally. | claude-4 (claude-opus-4-6) | The capability-index is an internal architectural artifact. The anti-patterns describe general software engineering problems (regex parsing, string passing), not proprietary secrets. The GTM audience tag refers to marketing framing, not public exposure of the YAML itself. The risk is speculative and the effort to implement audience-gated visibility is disproportionate at this stage. | 2026-02-13 16:28:04 UTC |
| R1-S15 | Define a versioning strategy for contextcore.anti_patterns.yaml including what constitutes a breaking change. | claude-4 (claude-opus-4-6) | While versioning is important, the anti-patterns manifest is a new, additive knowledge artifact — not a code library. Standard manifest-level versioning (already established in the existing manifests) applies. Defining SemVer semantics for a knowledge manifest at this stage is premature optimization; revisit once the manifest is in use and consumers exist. | 2026-02-13 16:28:04 UTC |
| R1-S19 | Add a deprecated_by relationship type to the cross-reference vocabulary for capability evolution. | claude-4 (claude-opus-4-6) | No capabilities are currently being deprecated, and the relationship vocabulary can be extended later. Adding speculative relationship types before they're needed increases schema complexity without immediate value. Revisit when the first capability deprecation occurs. | 2026-02-13 16:28:04 UTC |
| R1-S20 | Define a rollback plan for each tier in case structural additions cause unexpected consumer breakage. | claude-4 (claude-opus-4-6) | All changes are explicitly additive and backward-compatible (§7.1). YAML consumers that fail on unknown keys are already broken by convention. Standard version control (git revert) provides inherent rollback capability. A formal, documented rollback procedure per tier is disproportionate overhead for additive YAML changes. | 2026-02-13 16:28:04 UTC |
| R2-S5 | Define governance and access control model for capability-index manifests. | gemini-2.5 (gemini-2.5-pro) | This is already addressed by R2-S3 (operational governance) and R1-S8 (ownership). Standard source control practices (branch protection, required reviewers) are sufficient. A separate security-focused access control model for YAML files in a repository is excessive — these are not runtime-mutable configuration files. | 2026-02-13 16:28:04 UTC |
| R2-S7 | Define a formal rollback strategy for manifest updates. | gemini-2.5 (gemini-2.5-pro) | This duplicates R1-S20 which was already rejected. All changes are additive and backward-compatible. Git provides inherent rollback. A formal rollback strategy with staging environment testing is disproportionate for additive YAML changes to a static file. | 2026-02-13 16:28:04 UTC |
| R2-S13 | Specify versioning strategy for individual entities within a manifest, such as patterns or principles. | gemini-2.5 (gemini-2.5-pro) | This is premature. The manifests already have manifest-level versioning. Sub-entity versioning adds significant complexity without demonstrated need. Manifest-level versioning is sufficient until there's evidence that entity-level change tracking is required by consumers. | 2026-02-13 16:28:04 UTC |
| R2-S14 | Explicitly address the risk of monolithic manifest files and outline a future federation strategy. | gemini-2.5 (gemini-2.5-pro) | This duplicates R1-S4 which was already accepted. R1-S4 addresses single-file scalability with a concrete validation approach (estimate file size, define splitting strategy if >1000 lines). A separate future considerations subsection on manifest federation is redundant given R1-S4's acceptance. | 2026-02-13 16:28:04 UTC |
| R3-S5 | Add audit logging requirements for manifest reads and capability discovery queries. | claude-4 (claude-opus-4-6) | The manifests are currently static YAML files in a Git repository — there is no query API to audit. This suggestion assumes an API serving layer that doesn't yet exist. Read-side audit logging is premature; it should be addressed when/if an API is built (§10.1). Previously accepted R2-S9/R2-S10 and the OTel future consideration already cover observability direction. | 2026-02-13 16:34:44 UTC |
| R3-S6 | Specify rate limiting and abuse prevention for capability discovery queries. | claude-4 (claude-opus-4-6) | There is no serving API defined in this plan — manifests are static YAML files. Rate limiting is an implementation concern for a future API layer (§10.1), not for the structural enhancement plan itself. This is premature and over-engineers a system that doesn't exist yet. | 2026-02-13 16:34:44 UTC |
| R3-S9 | Define capacity planning, archival governance, and maximum size for the anti-patterns manifest. | claude-4 (claude-opus-4-6) | The anti-patterns manifest is being created with 8-12 entries. Capacity planning for a YAML file at this scale is premature. The plan already recommends separate manifests (Option B) which is a natural sharding mechanism. Governance can be added when growth warrants it. | 2026-02-13 16:34:44 UTC |
| R3-S12 | Define data classification levels and audience-based field visibility filtering for manifest content. | claude-4 (claude-opus-4-6) | The manifests are YAML files in a Git repository with standard repository access controls. Audience-based field filtering adds significant schema and tooling complexity for a problem better solved by repository-level access control (R3-S2). Internal code paths in a private repo are not a meaningful exposure risk. | 2026-02-13 16:34:44 UTC |
| R3-S13 | Define runbook templates for common index operational scenarios like manifest corruption and cross-reference cycles. | claude-4 (claude-opus-4-6) | The system is static YAML files in Git with CI validation. Manifest corruption recovery is 'git revert'. Runbooks are warranted for complex runtime systems, not for version-controlled config files. This adds documentation overhead disproportionate to operational risk at current scale. | 2026-02-13 16:34:44 UTC |
| R3-S15 | Define SLOs for capability discovery latency and accuracy with precision/recall measurements. | claude-4 (claude-opus-4-6) | The index is a static YAML file, not a query service. There is no latency to measure. Discovery accuracy SLOs are premature — the plan already defines qualitative test scenarios (§8.1) and quantitative structural targets (§8.2). Formal precision/recall measurement is over-engineering for the current state. | 2026-02-13 16:34:44 UTC |
| R3-S17 | Add observability for trigger match quality to enable continuous trigger refinement. | claude-4 (claude-opus-4-6) | Trigger matching is not a runtime system — it's a static lookup in YAML. There's no match engine producing logs to analyze. The plan's manual test scenarios (§8.1) are the appropriate validation mechanism at this stage. Trigger telemetry becomes relevant only if/when an automated discovery API exists. | 2026-02-13 16:34:44 UTC |
| R4-S1 | Implement Role-Based Access Control (RBAC) for index entities with per-entity access_control fields. | gemini-2.5 (gemini-2.5-pro) | Duplicates R3-S2 (already accepted) which covers access control via Git-native mechanisms. Adding RBAC fields to the schema and building an enforcement API is over-engineering for static YAML files in a Git repository. Repository-level access control is the appropriate mechanism at this stage. | 2026-02-13 16:34:44 UTC |
| R4-S2 | Replace direct source code file paths in evidence fields with abstract references resolved via a secure service. | gemini-2.5 (gemini-2.5-pro) | Evidence file paths are in a private Git repository with access controls. Abstracting them adds indirection complexity and a new service dependency without proportional security benefit. R3-S16 (accepted) already covers validating that evidence refs resolve to authorized repositories, which is the appropriate mitigation. | 2026-02-13 16:34:44 UTC |
| R4-S3 | Mandate cryptographic signing of manifests with a top-level signature field. | gemini-2.5 (gemini-2.5-pro) | Duplicates R3-S1 (already accepted) which covers manifest integrity including cryptographic signing. The specific implementation detail of a top-level signature field vs. other approaches (e.g., detached signatures, Git commit signing) should be determined during implementation, not prescribed in the architectural plan. | 2026-02-13 16:34:44 UTC |
| R4-S4 | Implement a comprehensive query audit trail for all queries to the index serving API. | gemini-2.5 (gemini-2.5-pro) | There is no index serving API — the plan defines static YAML files in Git. Git's own audit trail covers access. This was also rejected as R3-S5 for the same reason: premature for the current architecture. Should be revisited if/when an API is built. | 2026-02-13 16:34:44 UTC |
| R4-S5 | Enforce query complexity limits and timeouts for the index serving API. | gemini-2.5 (gemini-2.5-pro) | No serving API exists. The plan describes static YAML files. Query complexity limits are an implementation concern for a future query service, not for this structural enhancement plan. Duplicates the spirit of rejected R3-S6. | 2026-02-13 16:34:44 UTC |
| R4-S6 | Define and monitor SLOs for the index API including 99.9% availability and p95 latency targets. | gemini-2.5 (gemini-2.5-pro) | There is no index API. The plan is about structural enhancements to YAML files. SLOs for a non-existent service are premature. This duplicates rejected R3-S15. The plan's §8.2 quantitative targets are the appropriate success metrics for this phase. | 2026-02-13 16:34:44 UTC |
| R4-S7 | Support version pinning in the index API so consumers can bind to specific manifest versions. | gemini-2.5 (gemini-2.5-pro) | Manifests are YAML files in Git — version pinning is inherent (Git commits/tags). There is no API that serves 'latest' by default. The plan already specifies manifest_id + version fields (§3.2). This solution solves a problem that Git already solves natively. | 2026-02-13 16:34:44 UTC |
| R4-S8 | Formalize a zero-downtime deployment and instant rollback process for the index serving layer. | gemini-2.5 (gemini-2.5-pro) | Duplicates R3-S7 (already accepted) which covers deployment and rollback procedures. Additionally, this assumes a serving layer that doesn't exist. For Git-based YAML files, rollback is 'git revert'. The accepted R3-S7 is the appropriate scope. | 2026-02-13 16:34:44 UTC |
| R4-S10 | Add a linting rule scanning manifest changes for high-entropy strings and common secret key names. | gemini-2.5 (gemini-2.5-pro) | Duplicates R3-S20 (already accepted) which covers secrets scanning with tools like truffleHog/gitleaks integrated into CI for manifest files. | 2026-02-13 16:34:44 UTC |
| R4-S12 | Define a disaster recovery plan including geographically replicated backups and cross-region restoration procedures. | gemini-2.5 (gemini-2.5-pro) | The manifests are YAML files in Git, which is inherently distributed and replicated (every clone is a full backup). DR for Git repositories is a platform concern, not specific to this capability index plan. This is disproportionate to the actual risk. | 2026-02-13 16:34:44 UTC |
| R4-S13 | Specify indexed queries for efficient server-side data retrieval from the capability index. | gemini-2.5 (gemini-2.5-pro) | There is no serving API. The plan describes static YAML files. Query efficiency is an implementation concern for a future service. The YAML files at current scale (27 capabilities) do not have a performance problem requiring indexed queries. | 2026-02-13 16:34:44 UTC |
| R4-S15 | Isolate sensitive data categories (GTM, roadmap) into separate manifests from operational data. | gemini-2.5 (gemini-2.5-pro) | The plan already uses separate manifests for different concerns (contextcore.agent.yaml, contextcore.benefits.yaml, roadmap.yaml, etc.). GTM fields are optional per-capability annotations, not co-located security-sensitive data. Repository access controls are the appropriate mechanism for data isolation. | 2026-02-13 16:34:44 UTC |
| R4-S18 | Require liveness and readiness probes for the index service. | gemini-2.5 (gemini-2.5-pro) | There is no index service. The plan describes static YAML files. Health probes are relevant for a future serving layer but are premature for this structural enhancement plan. R3-S8 (accepted) covers CI-based health checks appropriate to the current architecture. | 2026-02-13 16:34:44 UTC |
| R4-S19 | Add a security_context field with risk_level and permissions_required to the capability schema. | gemini-2.5 (gemini-2.5-pro) | The capability index describes what capabilities exist and how to discover them — it is not a runtime authorization system. Risk classification and permission enforcement belong in the execution layer, not the discovery manifest. This conflates capability discovery with capability invocation governance. | 2026-02-13 16:34:44 UTC |
| R4-S20 | Implement a multi-level caching strategy (in-memory + Redis) for manifests and queries. | gemini-2.5 (gemini-2.5-pro) | There is no serving API or query engine. The plan describes static YAML files read from disk or Git. Caching is an implementation detail for a future service layer, not a structural enhancement concern. Premature optimization for a non-existent system. | 2026-02-13 16:34:44 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-13 16:24:22 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | critical | Define a formal YAML schema (JSON Schema or equivalent) for all new structural elements (P1–P7) before implementation begins, not deferred to Tier 3 as Q3 suggests | Without a schema upfront, Tier 1 and Tier 2 implementations will produce inconsistent structures that require costly rework. The plan acknowledges automated validation is needed (§10.4) but defers schema definition to Tier 3 — by which point 3 weeks of unvalidated YAML has accumulated. Schema-first prevents this. | Section 6, as a new Step 0 before Tier 1 (or integrated into Step 1.1) | JSON Schema exists and passes validation against all example YAML fragments in Sections 4 and 5 |
| R1-S2 | Risks | critical | Add an explicit risk register section addressing key execution risks: schema sprawl, maintenance burden of cross-references, staleness of discovery paths, and single-file scalability | The plan introduces 7 new structural elements into YAML files but contains no risk analysis. Cross-references are bidirectional by aspiration (§10.4) but unidirectional by implementation — this creates guaranteed consistency drift. No discussion of who maintains these structures or how staleness is detected. | New Section between §7 and §8 (or as §7.3) | Each identified risk has a mitigation strategy and an owner; risk review is part of each tier's exit criteria |
| R1-S3 | Validation | high | Replace "manual test" validation steps (1.5, 2.5, 3.5) with automated, repeatable test scripts that can be run in CI | Manual validation is antithetical to the document's own `observe_dont_report` principle. If discovery paths are the solution to discoverability, they should be testable by a script that simulates agent search behavior and asserts expected navigation outcomes. | Section 6, replace "Manual test" entries in each tier's validation step | CI pipeline includes a discovery-path test suite; all 7 scenarios from §8.1 are automated |
| R1-S4 | Architecture | high | Address single-file scalability: `contextcore.agent.yaml` will grow substantially with principles, patterns, cross-references, discovery paths added to 27+ capabilities | The plan adds ~5 new sections and enriches all 27 capabilities with 2–3 new fields each. A single YAML file could exceed thousands of lines, degrading both human readability and LLM context window efficiency. The plan defers multi-file concerns to §10.3 but the problem manifests in Tier 1. | Section 4 overview or Section 11 (promote from future consideration to active design decision) | Estimate final file size after all tiers; if >1000 lines, define a file-splitting strategy before Tier 2 |
| R1-S5 | Interfaces | high | Specify how consumers should parse the mixed-type `triggers` list (strings and objects) — provide a normalization algorithm or utility function | §P3 introduces backward-compatible mixed triggers but no consumer guidance beyond "Handle both string and {phrase, context} entries." Without a canonical parsing approach, each consumer will implement differently, creating subtle behavioral divergence. | Section 7.2 (Consumer Update Path), expanded with a parsing specification or pseudocode | Provide a reference parser; validate that at least 2 consumer implementations produce identical trigger match results |
| R1-S6 | Data | high | Define referential integrity constraints for all cross-manifest links and include a mechanism to enforce them pre-commit | The plan introduces cross-references across manifests (anti-patterns → agent capabilities, benefits → capabilities). §10.4 mentions automated linting but defers it. Without pre-commit enforcement, broken references will accumulate silently — the exact "drift" problem the plan criticizes in documents. | Section 6, as a linting step added to each tier's exit criteria; or Section 10.4 promoted to Tier 2 | Pre-commit hook or CI check validates all `capability_id`, `pattern_id`, `principle_id`, and `anti_pattern_id` references resolve |
| R1-S7 | Architecture | high | Clarify the relationship type vocabulary — `uses` vs `used_by` asymmetry, and whether cross-references should be stored unidirectionally or bidirectionally | §P4 defines `uses` as a relationship type but §5.1 uses `used_by` (not in the standardized vocabulary). The plan aspires to bidirectional consistency (§10.4) but doesn't specify whether both directions should be authored or one should be derived. This is a fundamental data modeling decision that affects all downstream tooling. | Section 4, P4 (Cross-References), add a subsection on directionality rules | Relationship vocabulary is complete and consistent; automated check confirms no undefined relationship types are used |
| R1-S8 | Ops | high | Define ownership and maintenance responsibilities for each new structural element | The plan is silent on who maintains principles, patterns, cross-references, and anti-patterns after initial creation. Without ownership, these structures will decay — contradicting the `structured_over_documents` principle. If the index is "emitted by code," how are the new manually-authored sections kept current? | New subsection in Section 6 or 7, addressing ongoing maintenance model | Each structural element has a defined owner (role, not person) and a review cadence |
| R1-S9 | Validation | high | Add negative test scenarios to §8.1 — queries that should NOT match, to validate precision alongside recall | All 7 test scenarios verify that correct capabilities are found (recall). None verify that incorrect capabilities are excluded (precision). A discovery system that returns everything for every query is useless. Test that "regex parsing" does NOT surface unrelated capabilities like `insight.emit`. | Section 8.1, add 3–4 negative scenarios | Negative scenarios documented; automated tests assert expected non-matches |
| R1-S10 | Security | medium | Assess whether discovery paths and anti-pattern descriptions could leak sensitive architectural details if the capability-index is exposed externally | The plan introduces detailed problem descriptions, code paths, and architectural weaknesses (anti-patterns with symptoms). §5.2 marks `contextcore.meta.structured_authority` for `[agent, human, gtm]` audiences. If GTM-facing, the index may be semi-public. Anti-patterns like "regex parsing LLM output" with code symptoms could reveal internal implementation details. | Section 7 (Migration and Compatibility) or a new Security Considerations subsection | Review all anti-pattern `symptoms` and `evidence.ref` fields for information sensitivity; define audience-gated visibility if needed |
| R1-S11 | Architecture | medium | Define conflict resolution strategy for when patterns claim overlapping capability sets or when capabilities appear in contradictory patterns | `typed_handoff` and `pipeline_stage_communication` share 2 of 3 capabilities and have a `relates_to` link, but the plan doesn't address how agents should choose between overlapping patterns, or what happens when patterns give contradictory guidance for the same capability. | Section 4, P2 (Named Patterns), add guidance on pattern selection when multiple patterns match | Document pattern precedence rules or selection heuristics; test scenario where multiple patterns match and verify correct disambiguation |
| R1-S12 | Data | medium | Formalize the context tag vocabulary from §P3 as a controlled enumeration rather than free-text convention | §P3 lists 11 context tags as a table but doesn't specify whether they're an open or closed vocabulary. If open, tag proliferation will degrade search precision. If closed, the enumeration needs a governance process for additions. | Section 4, P3, specify vocabulary governance (closed enum with versioned additions) | JSON Schema constrains context tags to the defined enumeration; CI rejects undefined tags |
| R1-S13 | Validation | medium | Add a completeness metric: percentage of capabilities with each new structural element populated | §8.2 sets absolute targets (15+ cross-references, 10+ discovery paths) but doesn't track coverage percentage. If 15 of 27 capabilities have cross-references, that's 56% — useful for prioritization but not tracked. | Section 8.2 (Quantitative Targets), add percentage-based metrics | Dashboard or CI report shows coverage percentages; Tier exit criteria include minimum coverage thresholds |
| R1-S14 | Architecture | medium | Address how the capability-index interacts with the Coyote SKILL.md mechanism — is the index a skill input, a skill itself, or a resource the skill queries? | §10.2 mentions a "Capability-Index Skill" but §9 doesn't clarify how Coyote pipeline stages would actually consume the enhanced index at runtime. Is it embedded in prompts? Queried via API? Loaded as context? The integration model affects all structural decisions. | Section 9 (Relationship to Coyote Pipeline Design), add a subsection on runtime consumption model | Integration model documented; at least one Coyote stage demonstrates index consumption in practice |
| R1-S15 | Ops | medium | Define a versioning strategy for the new `contextcore.anti_patterns.yaml` manifest — when do version bumps occur and what constitutes a breaking change? | The plan recommends Option B (separate manifest) for anti-patterns but doesn't define its versioning semantics. Adding anti-patterns is additive, but changing `addressed_by` links could break consumers. SemVer semantics for a knowledge manifest differ from code libraries. | Section 4, P7, add versioning policy | Versioning policy documented; first release follows the policy; CI validates version bump on changes |
| R1-S16 | Risks | medium | Identify and mitigate the risk that enriched index structure increases LLM token consumption when agents load the full manifest into context | The plan enriches a YAML file that agents consume. Adding principles, patterns, cross-references, and discovery paths to 27 capabilities could double or triple the token count. LLM context windows are finite and expensive. The plan doesn't discuss selective loading or summarization strategies. | Section 7.2 or new subsection on agent consumption optimization | Measure token count before and after enhancements; if >2x increase, define a selective loading strategy (e.g., load only relevant patterns\discovery paths) |
| R1-S17 | Interfaces | medium | Specify the `category` field values for anti-patterns (`data_exchange`, `validation`, `knowledge_management`) as a controlled vocabulary, analogous to capability categories | §P7 introduces anti-pattern categories but doesn't formalize them. Without a controlled vocabulary, categories will proliferate and lose navigational value. | Section 4, P7 schema definition | Anti-pattern categories defined as enum in JSON Schema; CI validates |
| R1-S18 | Validation | medium | Define what "1–2 hops" means operationally in §8.2's "Discovery hops from problem to capability" metric | The plan targets 1–2 hops but doesn't define what constitutes a "hop." Is following a `cross_references` link one hop? Is reading the `patterns` section and then following to a capability two hops? Without a definition, the metric is unmeasurable. | Section 8.2, add hop definition | Hop definition documented; automated test counts hops and asserts against target |
| R1-S19 | Architecture | low | Consider adding a `deprecated_by` relationship type to the cross-reference vocabulary for capability evolution | The relationship vocabulary (§P4) covers current-state relationships but not lifecycle transitions. As capabilities evolve, being able to mark "X is deprecated in favor of Y" within the cross-reference system avoids orphaned references. | Section 4, P4 relationship types table | `deprecated_by` added to vocabulary; at least one example demonstrates capability deprecation flow |
| R1-S20 | Ops | low | Define a rollback plan for each tier in case structural additions cause unexpected consumer breakage | §7.1 claims all changes are backward-compatible, but consumers of YAML may have brittle parsers that fail on unknown keys (strict-mode parsers, schema validators). No rollback procedure is defined. | Section 6, add rollback steps per tier | Each tier has a documented rollback procedure; tested by temporarily reverting and confirming consumers recover |

#### Review Round R2
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-13 16:25:42 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Risks | high | Re-evaluate all effort estimates with implementation teams. The current estimates (e.g., 2-3 hours) appear overly optimistic and may not account for schema implementation, data population, testing, and documentation. | Underestimating effort creates significant project risk, jeopardizing timelines and potentially forcing scope reduction. A more realistic plan is needed for predictable execution. | Section 6: Implementation Plan | Review the updated estimates with a senior engineer and project manager to confirm they account for the full scope of work for each step. |
| R2-S2 | Validation | high | Define and build an automated test suite for the Discovery Test Scenarios instead of relying on manual simulations. | Manual validation is not repeatable, scalable, or suitable for regression testing. Automated tests are essential for ensuring the index's integrity as it evolves. | Section 8.1: Discovery Test Scenarios | A CI job that runs a test suite against the YAML manifests. The suite should programmatically execute the queries from the test scenarios and assert the expected results are returned. |
| R2-S3 | Ops | high | Define the manifest lifecycle management process, including source control strategy (e.g., git), change approval workflow (e.g., PRs), and CI/CD for publishing/distributing the manifests. | The manifests are a critical production artifact. Without a defined operational process, changes could be un-audited, break consumers, or be difficult to deploy, undermining the system's reliability. | New Section: "12. Operational Governance" | Document the end-to-end process for proposing, approving, and deploying a change to a capability manifest. |
| R2-S4 | Interfaces | high | Specify the intended agent consumption mechanism. Is it a library, a standalone API, or direct file parsing with a prescribed search logic (e.g., semantic vs. keyword)? | The current plan is ambiguous about how an agent will query this new graph structure. This is a critical interface gap that blocks consumer implementation and could lead to inconsistent client-side logic. | New Section: "4.1 Consumption Model" | Prototype a client library or API endpoint that can execute the queries defined in the validation scenarios. |
| R2-S5 | Security | high | Define the governance and access control model for the capability-index manifests. | As the "source of truth" that can influence automated agent behavior, unauthorized or malicious modifications to these manifests present a significant security and operational risk. | Section 12: Operational Governance (new, from R2-S3) | Document the roles and permissions for manifest modification within the chosen source control system (e.g., git branch protection rules, required reviewers). |
| R2-S6 | Validation | high | Integrate the "Automated Validation" (linter) from Future Considerations into the core implementation plan, specifically to be delivered in Tier 2. | Finding and fixing structural integrity issues (e.g., broken links, schema violations) *after* they have been created is inefficient. A linter should be part of the CI process to prevent such errors from ever being merged. | Section 6: Implementation Plan (add as Step 2.0) | The CI pipeline fails if a proposed change to a manifest violates a linting rule (e.g., a `cross_reference` points to a non-existent `capability_id`). |
| R2-S7 | Risks | high | Define a formal rollback strategy for manifest updates. | If a published change to the index causes unintended behavior in consumer agents, a documented and tested process to revert to a last-known-good version is critical for operational safety. | Section 7: Migration and Compatibility | Demonstrate a successful rollback of a manifest change in a staging environment without impacting consumers. |
| R2-S8 | Architecture | critical | Re-classify "Time-Series Emission" (10.1) from a small future consideration to a major, separate architectural initiative. The "1-2 days" effort estimate is a severe underestimate. | This proposal involves introducing an entire observability stack (OTel, collectors, time-series DB) and fundamentally changes the index from static files to a dynamic, event-driven system. Misrepresenting this as a small task creates massive planning risk. | Section 10.1: Time-Series Emission | Create a separate, one-page design document for the time-series approach that outlines the required infrastructure, implementation phases, and a realistic effort estimate. |
| R2-S9 | Data | medium | Define a governance process for extending controlled vocabularies, such as `context` tags (P3) and `relationship` types (P4). | Without a process for managing these lists, they are likely to sprawl, leading to inconsistent or redundant tags that degrade the quality of discovery. | Section 12: Operational Governance (new, from R2-S3) | Document the process for proposing and approving a new tag or relationship type, including criteria for acceptance. |
| R2-S10 | Architecture | medium | Formalize the `relates_to` field for patterns, which appears in an example but is not defined in the P2 schema. | An implicit field in an example is not part of the contract. To make pattern-to-pattern relationships a first-class feature of the graph, this field must be formally specified. | Section 4: P2: Named Patterns (Schema) | Add the `relates_to` field to the pattern schema definition and validate its presence with the linter (R2-S6). |
| R2-S11 | Data | medium | Clarify the relationship between the `anti_patterns` list within a `design_principle` (P1) and the new dedicated `contextcore.anti_patterns.yaml` manifest (P7). | Having two locations for anti-pattern definitions creates a risk of data redundancy and inconsistency. The plan should specify a single source of truth. | Section 4: P1 and P7 | State explicitly that the list in `design_principles` should only contain IDs that reference the full definitions in the `contextcore.anti_patterns.yaml` manifest. |
| R2-S12 | Risks | medium | Add a "Data Quality Assurance" section to the implementation plan. | The success of this entire initiative depends on the accuracy and completeness of the new metadata. There is a risk that this data will be populated hastily or incorrectly, undermining the discovery goal. | Section 6: Implementation Plan | Conduct a peer review of the populated metadata for the first 5 capabilities, checking for correctness, clarity, and adherence to the defined schemas. |
| R2-S13 | Data | medium | Specify the versioning strategy for individual entities within a manifest, such as `patterns` or `principles`. | If a pattern's definition changes, it's not clear if the entire manifest's version must be bumped. This could lead to either excessive churn or an inability to track the evolution of specific composite structures. | Section 7: Migration and Compatibility | Add a sub-section discussing how changes to patterns or principles will be versioned, even if the decision is to stick with manifest-level versioning for now. |
| R2-S14 | Architecture | medium | Explicitly address the risk of monolithic manifest files and outline a future strategy for federation. | While starting with a single file is pragmatic, the plan should acknowledge that as the system grows, this file will become a bottleneck. A strategy for splitting manifests by domain should be considered. | Section 10: Future Considerations | Add a new sub-section "10.5 Manifest Federation" that outlines a potential future state where manifests can import or reference entities from other manifests. |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-13 16:29:46 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Security | critical | Add a threat model for manifest integrity — define how consumers verify that capability manifests haven't been tampered with (e.g., cryptographic signing, checksums, provenance attestation) | The plan introduces manifests as the "single source of truth" replacing documents. If an attacker modifies a manifest (e.g., alters `cross_references` to redirect agents to malicious capabilities, or injects a trojanized `anti_pattern` entry pointing to compromised code), every consumer trusts the poisoned data. Static YAML files have no built-in integrity verification. Section 10.1's OTel emission amplifies the blast radius — tampered data propagates into observability infrastructure. | New subsection under Section 7 ("Migration and Compatibility") or new Section 7.3 "Manifest Integrity and Provenance" | Implement signature verification in CI; add a validation scenario to Section 8.1 testing that unsigned/modified manifests are rejected |
| R3-S2 | Security | critical | Define an access control model for who/what can modify capability manifests, patterns, and anti-patterns | The plan treats manifests as authoritative ("single queryable source") but never addresses write-path authorization. Any agent or CI job that can write to the YAML files can alter capability definitions, inject anti-patterns, or modify cross-references. With the `contextcore.meta.structured_authority` capability (§5.2) positioning the index as the canonical registry, unauthorized modification is equivalent to redefining what the system can do. | New subsection in Section 7 or Section 4 (P6 self-description should reference the governance model) | Review that Git branch protection, CODEOWNERS, or CRD admission controllers gate manifest changes; add to Section 10.4 automated validation |
| R3-S3 | Security | critical | Add input validation and sanitization requirements for all new structured fields (`discovery_paths`, `triggers`, `cross_references`, `anti_patterns`) to prevent injection attacks | New fields like `discovery_paths[].relevance` and `anti_patterns[].symptoms` contain free-text that agents consume and may interpolate into prompts or queries. Without sanitization requirements, these fields become prompt injection vectors — an attacker who can modify a manifest can inject instructions that agents execute. The `triggers` field is particularly dangerous since agents use it for automated matching. | New subsection in Section 4 covering input validation constraints for each new field type, or add as a security principle in P1 `design_principles` | Add schema constraints (max length, allowed characters, no executable patterns) to the JSON Schema proposed in Q3; test with adversarial trigger/discovery-path content |
| R3-S4 | Security | high | Define trust boundaries for cross-manifest references, especially for the `startd8.workflow.benefits.yaml` cross-project manifest and future cross-manifest patterns (§10.3) | Section 3.1 shows `startd8.workflow.benefits.yaml` as a cross-project reference. Section 10.3 proposes cross-manifest patterns. The plan never defines trust boundaries: Can an external manifest's `cross_references` point into the core manifest? Can an anti-pattern in one manifest claim to be `addressed_by` capabilities in another? Without trust boundaries, cross-project references can create confused-deputy scenarios where agents follow references into untrusted capability spaces. | Add trust boundary definitions to P6 `index_meta` (§4, P6) and to the cross-manifest patterns discussion (§10.3) | Validate that cross-manifest reference resolution enforces trust scope; add negative test cases for references crossing trust boundaries |
| R3-S5 | Security | high | Add audit logging requirements for manifest reads and capability discovery — who queried what, when, and which discovery path was followed | The plan creates four discovery directions and promotes the index to authoritative source of truth, but provides no observability into how the index is consumed. Without read-side audit logging, you cannot detect reconnaissance (an agent systematically querying all capabilities), cannot debug discovery failures (why didn't the agent find the right capability?), and cannot measure discovery effectiveness. This is critical for Section 8's validation criteria — you need data to measure "discovery hops." | Add audit/observability requirements to Section 8 and reference in P6's `index_meta` navigational model | Verify that discovery queries emit OTel spans with capability_id, entry_point, hops_taken; validate that Section 8.2 quantitative targets are measurable from audit data |
| R3-S6 | Security | high | Specify rate limiting and abuse prevention for capability discovery queries, particularly for the TraceQL-based queries proposed in §10.1 | Section 10.1 proposes emitting index entries as OTel resource attributes queryable via TraceQL. Section 5.2 defines `contextcore.meta.structured_authority` as a query interface. Without rate limiting, a compromised or misbehaving agent can DoS the observability backend with capability queries, or use unbounded queries to exfiltrate the full capability graph (which may reveal internal architecture to unauthorized consumers). | Add rate limiting/quota requirements to Section 10.1 (OTel emission) and to the `contextcore.meta.structured_authority` capability definition (§5.2) | Load test the query path; verify that per-agent query quotas are enforced; validate that bulk enumeration is detectable in audit logs |
| R3-S7 | Ops | high | Define manifest deployment and rollback procedures — how are manifest changes promoted across environments, and how do you roll back a bad manifest version? | The plan specifies three tiers of additive changes but treats deployment as implicit. Manifests are the "single source of truth" — a broken manifest (e.g., circular cross-references, invalid capability_id in a pattern) can break all consuming agents simultaneously. The plan needs blue-green or canary deployment patterns for manifests, and rollback procedures that don't require understanding the full dependency graph at incident time. | New subsection in Section 6 (Implementation Plan) covering deployment procedures per tier, or new Section 6.5 "Deployment and Rollback" | Validate by simulating a bad manifest deployment and measuring time-to-rollback; verify that rollback restores previous cross-references without orphaned links |
| R3-S8 | Ops | high | Add health checks and liveness probes for the capability-index — how do consuming agents detect that the index is stale, corrupted, or unavailable? | The plan positions the index as authoritative but provides no mechanism for consumers to detect index degradation. If the YAML file becomes corrupted, if the OTel emission pipeline (§10.1) stops emitting, or if the file is stale (last modified weeks ago despite active development), consuming agents silently operate on bad data. The `observe_dont_report` principle (P1) should apply to the index itself. | Add health check specification to P6 `index_meta` (§4) — define freshness thresholds, structural integrity checks, and how agents should behave when the index is degraded | Implement a CI job that validates index freshness and structural integrity; add a degraded-index scenario to Section 8.1 validation tests |
| R3-S9 | Ops | high | Define capacity planning for the anti-patterns manifest (P7) — establish governance for growth, archival of resolved anti-patterns, and maximum manifest size | The plan proposes a new `contextcore.anti_patterns.yaml` manifest that will grow over time as teams document more anti-patterns. Without governance, this manifest becomes the same sprawling, hard-to-navigate document the plan criticizes. At what size does the manifest need sharding? How are resolved/obsolete anti-patterns archived? What's the maximum query response time SLA as the manifest grows? | Add governance and capacity notes to Section 4 (P7) and reference in the anti-patterns manifest schema | Monitor manifest file size and query latency over time; validate that anti-pattern count stays within defined bounds or triggers archival workflow |
| R3-S10 | Security | medium | Add a `deprecated` lifecycle state to capabilities and define secure deprecation procedures that prevent agents from discovering and using deprecated capabilities with known vulnerabilities | Section 3.2 defines `maturity: enum` with values `stable \| beta \| experimental \| planned`. There is no `deprecated` state. When a capability has a security issue (e.g., `contract.validate` has a bypass vulnerability), there's no way to mark it as "do not use" while keeping it in the index for backward compatibility. Agents discovering capabilities via patterns or cross-references will continue routing to vulnerable capabilities. | Add `deprecated` to the maturity enum in Section 3.2; add deprecation handling to cross_references and patterns in Section 4 (P2, P4); define how discovery_paths handle deprecated capabilities | Validate that deprecated capabilities are excluded from pattern resolution and discovery paths; test that agents receive explicit warnings when following cross-references to deprecated capabilities |
| R3-S11 | Ops | medium | Specify monitoring and alerting for cross-reference integrity — detect when capability additions or removals create orphaned or broken cross-references in production | Section 10.4 mentions automated linting for bidirectional consistency, but only as a future consideration. With 15+ capabilities having cross-references (§8.2 target), plus patterns referencing capabilities, and anti-patterns referencing both — the reference graph is complex enough that CI-time validation alone is insufficient. Runtime reference resolution failures need monitoring. | Elevate the bidirectional consistency check from §10.4 "future" to Tier 2 implementation; add runtime alerting for unresolvable references to Section 6 (Tier 2 steps) | Implement a periodic integrity scan that alerts on orphaned references; verify zero orphaned references after each deployment |
| R3-S12 | Security | medium | Define data classification levels for manifest content and ensure sensitive architectural details (evidence code paths, internal service names) are not exposed to unauthorized audiences | The plan defines multiple audiences (`agent`, `human`, `gtm`) per capability and §3.1 shows cross-project manifests. Evidence fields contain internal code paths (e.g., `src/contextcore/agent/handoff.py`), which reveal internal repository structure. Discovery paths contain detailed architectural reasoning. When manifests are queried by external agents or GTM consumers, sensitive internal details should be filtered based on the requester's authorization level. | Add audience-based field visibility rules to the schema in Section 3.2; specify which fields are public vs. internal in P6 `index_meta` | Validate that GTM-audience queries don't return evidence code paths; test that cross-project manifest consumers receive only authorized fields |
| R3-S13 | Ops | medium | Define runbook templates for common index operational scenarios: manifest corruption recovery, discovery path false-positive triage, cross-reference cycle detection and resolution | The plan adds significant structural complexity (four discovery directions, cross-references, patterns, anti-patterns) but provides no operational runbooks. When things go wrong — circular cross-references cause infinite agent loops, a bad discovery path sends agents to the wrong capability, or a manifest merge conflict corrupts the YAML — operators need documented procedures, not ad-hoc debugging. | New Section 6.6 "Operational Runbooks" with templates for top 5 failure scenarios; reference from Section 8 validation criteria | Conduct failure injection exercises (chaos engineering) for each runbook scenario; validate that mean-time-to-resolution meets target SLAs |
| R3-S14 | Security | medium | Add schema versioning with backward-compatibility guarantees for the structural enhancements, and define how older agents that don't understand new fields behave securely | Section 7.1 claims backward compatibility, but doesn't address the security implications of field ignorance. An older agent that ignores `cross_references` might use a capability in isolation that the newer schema marks as requiring a paired capability (e.g., using `handoff.initiate` without `handoff.receive`). The compatibility principle (§2.3) ensures *parsing* doesn't break, but doesn't ensure *behavioral* safety when new structural constraints are invisible to old consumers. | Add behavioral compatibility analysis to Section 7.1; define minimum agent version requirements for security-relevant structural fields | Test old-version agent behavior against new manifests; verify that security-critical cross-references degrade safely (not silently) when ignored |
| R3-S15 | Ops | medium | Define SLOs for capability discovery latency and accuracy — how fast must discovery resolve, and what false-positive/false-negative rates are acceptable? | Section 8.2 defines quantitative targets for structural coverage (15+ cross-references, 10+ discovery paths) but no performance or accuracy SLOs. As the index grows, discovery queries could slow down. More importantly, enriched triggers and discovery paths increase the chance of false positives (finding the wrong capability). Without defined SLOs, there's no threshold for "discovery is degraded" and no trigger for remediation. | Add performance and accuracy SLOs to Section 8.2; define measurement methodology (precision/recall for discovery scenarios) | Run Section 8.1 test scenarios under load; measure P95 discovery latency and false-positive rate; alert when SLOs are breached |
| R3-S16 | Security | medium | Require that all `evidence` references (code refs, doc refs) are validated as resolvable and point to authorized repositories — prevent evidence field from being used to reference malicious external resources | Evidence fields currently contain file paths (e.g., `ref: src/contextcore/agent/handoff.py`). The plan doesn't constrain evidence references to internal repositories. An attacker modifying a manifest could add evidence pointing to external URLs or unauthorized repositories, which agents might fetch and trust. As the index becomes authoritative, evidence references become implicit trust anchors. | Add evidence reference validation rules to Section 10.4 (automated validation); define allowlist of valid evidence ref prefixes in the schema | CI validation that all evidence refs resolve to files in authorized repositories; reject manifests with external or out-of-scope evidence references |
| R3-S17 | Ops | medium | Add observability for trigger match quality — instrument which triggers are matched, which are never matched, and which produce false-positive matches, to enable continuous trigger refinement | P3 (enriched triggers) adds context-tagged triggers, but provides no feedback loop. Without observability into trigger match quality, the team cannot know which triggers are effective, which are never used, and which lead agents to the wrong capability. Section 8.2 targets "capabilities with discovery paths" but not "discovery paths that actually work." | Add trigger-match telemetry requirements to P3 (Section 4); define a trigger effectiveness dashboard specification | Analyze trigger match logs after Tier 1 deployment; validate that >80% of trigger matches lead to correct capability selection; prune or refine triggers below threshold |
| R3-S18 | Risks | high | Add risk of "authority centralization" — the plan concentrates all capability truth in YAML manifests, creating a single point of failure for all agent decision-making and a high-value target for attacks | The plan explicitly argues for "single queryable source" and "structured authority." This is architecturally sound but creates concentrated risk: if the index is wrong, every consumer is wrong. The risks section (currently implicit in anti-patterns) should explicitly acknowledge this concentration risk and define mitigations (redundancy, fallback behavior, split-brain detection). This is distinct from R3-S7 (deployment/rollback) — this is about the fundamental architectural risk of centralized authority. | New risk entry in a risks section or as an addition to Section 11 (Open Questions) as a new Q6; reference mitigations from R3-S1 (integrity), R3-S2 (access control), R3-S8 (health checks) | Conduct a failure mode analysis: what happens when the index is unavailable, stale, or incorrect? Define and test agent fallback behavior for each mode |
| R3-S19 | Validation | high | Add adversarial discovery test scenarios to Section 8.1 — test that malformed, ambiguous, or deliberately misleading queries don't lead agents to incorrect capabilities | Section 8.1 defines seven discovery scenarios, all positive ("can you find the right thing?"). None test negative cases: What happens when a query is ambiguous? When it matches multiple capabilities? When the trigger phrase partially matches an unrelated capability? Adversarial testing is essential given that agents will autonomously navigate the index — a false-positive discovery could lead an agent to use the wrong capability with production consequences. | Add 3-5 adversarial scenarios to Section 8.1 (e.g., "ambiguous query matching multiple patterns," "query matching an anti-pattern but not its solution," "query with terms from a deprecated capability") | Run adversarial scenarios after each tier; measure false-positive rate; validate that ambiguous queries return ranked results rather than arbitrary single matches |
| R3-S20 | Security | medium | Define secrets hygiene requirements — ensure that manifest content (especially `evidence` refs, `example` code blocks, and `description` fields) is scanned for accidentally embedded secrets, API keys, or internal hostnames | The plan adds substantial free-text content: examples in patterns (P2), discovery path relevance descriptions (P5), anti-pattern symptoms (P7). These fields are authored by developers who may inadvertently include internal URLs, API keys in example code, or sensitive hostnames. Since manifests are positioned as widely-queryable (including by external agents via cross-project references), embedded secrets would be exposed to unintended audiences. | Add secrets scanning requirement to Section 10.4 (automated validation); reference in Section 7.2 (consumer update path) as a pre-publication gate | Integrate secrets scanner (e.g., truffleHog, gitleaks) into CI for manifest files; validate that no manifest passes CI with detected secrets patterns |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- *(No prior untriaged suggestions from Appendix C to endorse, as this is the first R3 review.)*

#### Review Round R4
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-13 16:31:43 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Security | critical | Implement Role-Based Access Control (RBAC) for Index Entities | The index mixes public, internal, and sensitive GTM/roadmap data. Without access controls, any agent or user can query all data, exposing strategic information. This is a critical flaw for an authoritative knowledge base. | Add `access_control: { level: enum, roles: list }` to the schema for principles, patterns, and capabilities. The serving API must enforce this based on the querier's identity. | Create three test users/agents (public, internal, gtm-team). For each, run a standard set of queries and validate that results are filtered according to their roles. |
| R4-S2 | Security | critical | Sanitize or Abstract Source Code References in 'evidence' | The `evidence` field links directly to source code file paths (e.g., `src/contextcore/agent/handoff.py`). This provides a detailed map of the codebase to any attacker who gains query access, dramatically increasing data exfiltration and vulnerability discovery risk. | Replace direct file paths with abstract references (e.g., `evidence_id: HANDOFF_MODEL_DEF`) that resolve to URLs via a secure service with its own access controls, or link to published documentation instead of source. | Security code review to confirm no direct, sensitive file paths are exposed via the API. Penetration test scenario focused on using the index to map the application's internal structure. |
| R4-S3 | Security | high | Mandate Cryptographic Signing of Manifests | The plan establishes manifests as the "source of truth" but provides no mechanism to guarantee their integrity. A malicious actor could modify a manifest at rest or in transit to inject a harmful capability, which would then be trusted by all agents. | Add a top-level `signature` field to each manifest. The CI/CD pipeline for publishing manifests must sign them with a protected key. The index serving layer and all consumers must verify this signature before loading. | Attempt to load a manually-altered (unsigned or invalidly signed) manifest into the system. The load must fail with a clear security error. |
| R4-S4 | Security | high | Implement a Comprehensive Query Audit Trail | As the central repository of the system's "IP," access patterns are highly sensitive. The plan lacks any requirement for auditing who queries what. Without an audit trail, detecting or investigating data exfiltration, reconnaissance, or misuse is impossible. | All queries to the index serving API must generate a structured audit log event containing the querier's identity, the full query, a summary of results (e.g., number of capabilities returned), and the timestamp. | In a test environment, perform 10-15 different queries with various agent identities. Verify that each query generates a corresponding, accurate, and queryable audit log entry. |
| R4-S5 | Security | high | Enforce Query Complexity Limits and Timeouts | The graph structure enables complex queries that can traverse many nodes. A single malicious or poorly-formed recursive query could consume 100% of the serving layer's resources, causing a Denial of Service (DoS) that impacts all dependent agents. | The index serving API must implement and enforce strict limits on query depth, returned results, and execution time. Any query exceeding these limits must be terminated immediately. | Develop a suite of "abusive" queries (e.g., traverse every relationship, find all paths between two nodes) and execute them. Validate that they are correctly terminated and do not impact the API's overall responsiveness. |
| R4-S6 | Ops | critical | Define and Monitor Service Level Objectives (SLOs) for the Index API | The index is positioned as a critical dependency for agent discovery, but the plan treats it as static files. The inevitable API serving this data is an unmanaged dependency. Without defined SLOs for availability and latency, its operational performance is not guaranteed, creating a high-risk single point of failure. | Add a new section "12. Operational Requirements" defining explicit SLOs (e.g., 99.9% availability, p95 query latency < 150ms). Mandate creation of a monitoring dashboard to track these SLOs. | The production-readiness checklist for the index serving API must include a review of the monitoring dashboard showing at least 7 days of SLO compliance under simulated load. |
| R4-S7 | Ops | high | Support Version Pinning in the Index API | The plan assumes consumers use the "latest" version of a manifest. This is operationally fragile. A non-breaking but behavior-changing update to a capability's description could cause production agents to fail. Consumers must be able to bind to a specific, known-good version. | The index serving API must support versioned queries (e.g., `/api/manifests/contextcore.agent/v1.6.0/query`). Consumers must be encouraged to pin to specific versions. | Deploy two versions of a manifest (`1.1.0` and `1.2.0`). Write a test client that queries for `1.1.0` and validate it receives the old data, even though `1.2.0` is the latest. |
| R4-S8 | Ops | high | Formalize a Zero-Downtime Deployment and Instant Rollback Process | A bad change to a central, critical service like the index could cause a widespread outage. The plan lacks a strategy for deploying updates safely. A manual or slow rollback process would extend the mean time to recovery (MTTR) unacceptably. | Add to "6. Implementation Plan" a requirement for a blue-green or canary deployment strategy for the index serving layer. The deployment pipeline must include a one-click, sub-second rollback capability. | In a staging environment, deploy a "bad" version of a manifest. Trigger the rollback mechanism and validate that the service is restored to the previous version within 5 seconds and with zero dropped requests. |
| R4-S9 | Ops | high | Establish a Federated Ownership and Governance Model | A centralized model where one team owns the entire index will become a bottleneck, slowing down development. The plan acknowledges cross-project manifests but doesn't define an ownership model, which is critical for operational scaling. | Add a new top-level `owner: { team: string }` field to each manifest schema. Define a governance process where teams can self-service publish their own manifests to a central registry, which are then aggregated by the serving API. | Onboard two separate teams to the process. Have each team independently publish and update their own manifest file. Validate that the central API reflects changes from both teams without manual intervention. |
| R4-S10 | Security | medium | Proactively Prevent Secret Leakage via Schema Linting | While not currently in the schema, developers under pressure may be tempted to add configuration hints or temporary keys to capabilities. The plan should proactively prevent the index from becoming a repository for secrets. | Add to "10.4 Automated Validation" a linting rule that scans all manifest changes for high-entropy strings and common secret key names (e.g., `API_KEY`, `TOKEN`, `PASSWORD`) and fails the build if any are found. | Add a capability with a field `example_config: { api_key: "..." }` to a manifest in a feature branch. Validate that the CI pipeline fails on the linting step. |
| R4-S11 | Security | medium | Mandate Secure Parsing of YAML Manifests | The plan relies on parsing YAML, a complex format with known vulnerabilities (e.g., Billion Laughs, arbitrary code execution via constructor tags). An attacker-controlled manifest could exploit a misconfigured parser to achieve DoS or RCE on the index service or any agent that parses it directly. | Add a security requirement to use a vetted YAML parsing library configured in a "safe" mode (e.g., `yaml.safe_load()` in Python), which disables execution of arbitrary tags. This must be a documented standard for all services that consume manifests. | Create a malicious YAML file containing a known exploit tag (e.g., `!!python/object/apply:os.system ['ls']`). Attempt to parse it with the chosen library and configuration. The parse must fail safely without executing the command. |
| R4-S12 | Ops | medium | Define a Disaster Recovery (DR) Plan for the Index | The index is designated the authoritative source of truth. Loss or corruption of the underlying Git repository or storage would be catastrophic. The plan has no provision for business continuity in a DR scenario. | Add section "12. Operational Requirements" detailing a DR plan. This must include automated, geographically replicated backups of all manifests and a documented, tested procedure for restoring the index serving API in a different region. | Conduct a DR test: destroy the primary manifest storage in the test environment. Follow the DR procedure to restore the service from backups in a secondary region. Measure the time to recovery against a pre-defined RTO (Recovery Time Objective). |
| R4-S13 | Ops | medium | Specify Indexed Queries for Efficient Data Retrieval | The plan implies consumers will download and parse entire manifests. As the index grows to hundreds of capabilities, this will be highly inefficient and slow. The operational viability of the system depends on efficient, server-side querying. | Specify that the index serving API must support indexed queries (e.g., `/api/capabilities?id=...`, `/api/patterns?implements_principle=...`) that do not require a full manifest scan on the server or a full download on the client. | Measure the response time and bandwidth usage for fetching a single capability from a 10MB manifest via a full download vs. a direct, indexed lookup. The indexed lookup should be orders of magnitude faster and smaller. |
| R4-S14 | Ops | high | Define a Conflict Resolution Strategy for Federated IDs | A federated model (R4-S9) creates the risk of "split brain," where two teams independently define the same `capability_id` or `pattern_id`. The serving layer needs a deterministic way to handle these conflicts to avoid serving inconsistent or ambiguous data. | In the governance model for federation, specify a conflict resolution policy. Options: (a) "first-in wins" and the second submission is rejected by CI, (b) IDs must be prefixed with a team namespace (e.g., `teamA.my_cap`). Recommend (b) as it prevents conflicts by design. | Create two test manifests from different "teams" that both define `capability_id: "shared.id"`. Attempt to publish both. Validate that the CI/CD pipeline rejects the second submission with a clear error message about the conflict. |
| R4-S15 | Security | medium | Isolate Sensitive Data Categories into Separate Manifests | The current schema mixes operational data (`contextcore.agent.yaml`) with business strategy (`gtm` fields) and future plans (`roadmap` fields). This violates the principle of least privilege by co-locating data with different security classifications, making fine-grained access control (R4-S1) harder. | Propose a structural change: split the `gtm` content into `contextcore.gtm.yaml` and roadmap data into `contextcore.roadmap.yaml`, linking them by `capability_id`. The agent-facing manifest should contain only the technical details agents need. | Review the final manifest structure. Validate that `contextcore.agent.yaml` contains no `gtm` or `roadmap` fields, and that this data resides in separate, access-controlled files. |
| R4-S16 | Validation | high | Promote Automated Bidirectional Link Validation to a Tier 1 Requirement | The plan lists automated validation of links (e.g., cross-references) as a "Future Consideration" (10.4). This is a critical gap. An inconsistent knowledge graph with broken links is unreliable and will erode trust. This validation is essential for the integrity of the proposed system. | Move "10.4 Automated Validation" into the "Tier 1 Implementation Plan" as a mandatory CI check for all pull requests that modify manifests. The check must validate that all `cross_references`, `implements`, and `capabilities` links are valid and, where applicable, bidirectional. | Create a PR with a `cross_reference` from capability A to non-existent capability B. The CI check must fail. Create a PR where A is `paired_with` B, but B does not have a corresponding reference to A. The CI check must fail. |
| R4-S17 | Security | high | Define a Threat Model for the Capability Index Ecosystem | The plan focuses on features but hasn't systematically analyzed the security risks of making this index a central, queryable, and trusted component. A formal threat model is needed to uncover risks beyond the obvious, such as second-order effects of agents trusting tainted data. | Add a task to Tier 1: "Conduct a threat modeling exercise (e.g., STRIDE) for the capability index and its serving API." The model should consider threats from malicious agents, compromised developers, and insecure consumers. | The threat model document is the deliverable. It should identify at least 10 specific threats and propose mitigations for each. This document must be reviewed and approved by the security team. |
| R4-S18 | Ops | medium | Require Liveness and Readiness Probes for the Index Service | For the index API to be a reliable dependency in a containerized environment, it needs health checks. A simple liveness probe isn't enough; the service could be running but unable to serve correct data if a manifest fails to load, leading to a "zombie" state. | In "12. Operational Requirements," specify that the index API must expose `/live` and `/ready` endpoints. The `/ready` probe must fail if the service has not successfully loaded and validated all configured manifests, ensuring it's removed from the load balancer until healthy. | In a test environment, deploy the service with a malformed manifest. Validate that the service starts (passing `/live`) but fails its `/ready` check and does not receive traffic. After deploying a valid manifest, validate the `/ready` probe passes. |
| R4-S19 | Security | medium | Establish a 'Security Context' Tag for Risky Capabilities | Not all capabilities are equal in risk. A capability that interacts with production systems is riskier than a pure data transformation. Agents need a way to assess this risk before invoking a capability discovered via the index. | Add an optional `security_context: { risk_level: enum, permissions_required: list }` field to the capability schema. `risk_level` could be `low` \| `medium` \| `high`. This allows agents to apply stricter policies when using high-risk capabilities. | Define two capabilities, one high-risk (e.g., `deploy_service`) and one low-risk (`format_string`). An agent's policy should allow it to use the latter but require human-in-the-loop approval for the former, based on reading the `security_context` field. |
| R4-S20 | Ops | medium | Implement Caching Strategy for Manifests and Queries | The index data is read-heavy and changes infrequently. Without a caching layer, the serving API will repeatedly parse the same YAML files and run the same queries, leading to unnecessary load and higher latency. | Add a requirement for the index serving API to implement a multi-level caching strategy: an in-memory cache for hot manifests and a distributed cache (e.g., Redis) for common query results. Cache invalidation should be triggered upon manifest publication. | Measure the p95 latency for a complex query. Perform the same query a second time. The second query's latency should be significantly lower, demonstrating that the result was served from cache. |
