# Discoverability Failure Investigation: Artifact Scope False Ceiling

**Date:** 2026-02-18
**Investigator:** Claude Opus 4.6 (AI Agent)
**Severity:** Critical — threatens ContextCore's central value proposition
**Status:** Active investigation

---

## Executive Summary

An AI agent (Claude Opus 4.6), tasked with determining whether Dockerfiles should be produced at the ContextCore export stage (before plan-ingestion), exhaustively searched the capability index and concluded — **incorrectly** — that ContextCore's artifact scope is limited to observability artifacts. The correct answer, found only after the user directed the agent to check `pipeline-requirements-onboarding.md`, is that the pipeline already defines non-observability artifact types (`agent_card`, `mcp_tools`, `onboarding_metadata`, `provenance`, `ingestion-traceability`).

This is not a documentation failure. The content exists. It is a **discoverability failure** — the same class of failure that `REQ_CAPABILITY_INDEX_DISCOVERABILITY.md` was created to address. But this failure operates at a deeper level: the agent could not determine the **scope boundary** of what the system produces.

**Why this matters:** If the capability index — ContextCore's central mechanism for programmatic capability discovery — cannot communicate its own artifact scope to an agent actively searching for it, then the discoverability system is failing at its most fundamental job. This directly threatens the value proposition articulated in `contextcore.meta.structured_authority`: that structured, versioned, queryable capability manifests replace ambiguous documents as the source of truth.

---

## The Discovery Session: What Happened

### The Question
> "Should the Dockerfile (PI-013) have been produced before plan-ingestion, at the ContextCore export stage?"

### The Search Path (chronological)

| Step | Source Searched | What Was Found | Conclusion Drawn |
|------|---------------|----------------|------------------|
| 1 | `run-provenance.json` | 9 artifacts in inventory, all observability or pre-pipeline | "Dockerfiles not in artifact inventory" |
| 2 | `online-boutique-python-artifact-manifest.yaml` | 8 artifacts, all observability types | "Artifact manifest is observability-only" |
| 3 | `.contextcore.yaml` manifest | Dockerfiles in `strategy.tactics` deliverables, not in artifact spec | "Dockerfiles are plan deliverables, not artifacts" |
| 4 | `artifact_manifest.py:27-38` — `ArtifactType` enum | 9 values, docstring: "Types of **observability** artifacts" | "The enum defines the scope as observability" |
| 5 | `MANIFEST_EXPORT_REQUIREMENTS.md:99` | "Must support **8 artifact types**: dashboard, prometheus_rule..." | "Requirements explicitly limit to 8 observability types" |
| 6 | `REQ_CAPABILITY_DELIVERY_PIPELINE.md` | Pipeline v2.0 requirements, no mention of Dockerfile artifacts | "Pipeline requirements don't include Dockerfiles" |
| 7 | `contextcore.agent.yaml` (115K, ~3300 lines) | No mention of "dockerfile", "container", or non-observability artifacts | "Capability index has no Dockerfile support" |
| 8 | `contextcore.benefits.yaml:717` | `pipeline.contract_first_planning`: "observability artifacts" | "Benefits confirm observability-only scope" |
| 9 | `contextcore.user.yaml`, `contextcore.docs.yaml`, `contextcore.pain_points.yaml` | No Dockerfile references | "No capability file mentions Dockerfiles" |
| 10 | `_patterns.yaml`, `_principles.yaml`, `_discovery_paths.yaml`, `_p2_capabilities.yaml` | No artifact type expansion mentions | "Sidecar files also observability-focused" |
| 11 | `onboarding-metadata.json` artifact_types section | Only observability types + capability_index | "Onboarding metadata confirms limited scope" |
| 12 | `artifact-intent.schema.json:5` | Description: "**observability** artifact need" | "Even the A2A schema says observability" |

### The Wrong Conclusion
> "The capability index clearly shows Dockerfiles are outside ContextCore's current artifact scope. ContextCore only produces observability artifacts at the export stage."

**Confidence at this point: HIGH** — 12 independent sources all pointed in the same direction.

### The Correction
The user said: "check the a2a card." This led to `pipeline-requirements-onboarding.md`, which defines:

| Requirement | Artifact | Category | Status |
|---|---|---|---|
| REQ-CDP-ONB-001 | `capability_index` | onboarding | In ArtifactType enum |
| **REQ-CDP-ONB-002** | **`agent_card`** | **onboarding** | **NOT in ArtifactType enum** |
| REQ-CDP-ONB-003 | `mcp_tools` | onboarding | NOT in ArtifactType enum |
| REQ-CDP-ONB-004 | `onboarding_metadata` | onboarding | NOT in ArtifactType enum |
| REQ-CDP-INT-001 | `provenance` | integrity | NOT in ArtifactType enum |
| REQ-CDP-INT-002 | `ingestion-traceability` | integrity | NOT in ArtifactType enum |

The document's header says: **"satisfied by artifact generation, not by plan features."** This proves the artifact scope extends beyond observability. The agent card is a non-observability, pipeline-innate artifact.

---

## Root Cause Analysis: Seven Reinforcing Breakpoints

This was not a single-point failure. **Every layer of the discoverability system failed in the same direction**, creating a "false ceiling" that was impossible to see through from within the capability index.

### Breakpoint 1: ArtifactType Enum Docstring
**File:** `src/contextcore/models/artifact_manifest.py:28`
**Text:** `"Types of observability artifacts that can be generated."`
**Impact:** The enum presents itself as the authoritative, complete definition of artifact types. The word "observability" creates a conceptual boundary. An agent reading this docstring has no reason to suspect additional artifact types exist elsewhere.
**Why it's wrong:** The enum is incomplete — it's missing `agent_card`, `mcp_tools`, `onboarding_metadata`, `provenance`, and `ingestion-traceability` which are all defined in `pipeline-requirements-onboarding.md`.

### Breakpoint 2: MANIFEST_EXPORT_REQUIREMENTS.md Line 99
**File:** `docs/design/MANIFEST_EXPORT_REQUIREMENTS.md:99`
**Text:** `"Must support 8 artifact types: dashboard, prometheus_rule, slo_definition, service_monitor, loki_rule, notification_policy, runbook, alert_template."`
**Impact:** Reads as an exhaustive enumeration. The word "Must" + specific count "8" + explicit list creates the impression this is the complete set.
**Why it's wrong:** This line describes the artifact manifest's current scope, but pipeline-innate requirements define 5 additional artifact types that the export stage should also handle.

### Breakpoint 3: Benefits YAML Says "Observability Artifacts"
**File:** `docs/capability-index/contextcore.benefits.yaml:717`
**Text:** `pipeline.contract_first_planning` value_statement: "Users can declare what **observability artifacts** are needed from business metadata..."
**Impact:** The user-facing benefit description reinforces the observability-only scope from a completely independent angle (value proposition, not implementation).
**Why it's wrong:** The benefit should describe the full scope of what the pipeline produces, not just the observability subset.

### Breakpoint 4: ArtifactIntent Schema Says "Observability"
**File:** `schemas/contracts/artifact-intent.schema.json:5`
**Text:** `"description": "Typed declaration of an observability artifact need before generation."`
**Impact:** Even the A2A governance layer — the most sophisticated part of the system — describes its artifact intent contract as being about "observability" artifacts, despite `artifact_type` being a free-form string that could hold any value.
**Why it's wrong:** The `ArtifactIntent` model is designed to be general-purpose (free-form `artifact_type` string), but its documentation constrains perception to observability.

### Breakpoint 5: No Cross-Reference to Pipeline-Requirements-Onboarding
**File:** `docs/reference/pipeline-requirements-onboarding.md` (the document with the answer)
**Impact:** This document is referenced from ZERO other documents in the capability index, the artifact manifest model, the export requirements, or the benefits yaml. It is an island.
**Cross-references that should exist but don't:**
- `artifact_manifest.py` → should reference pipeline-requirements-onboarding.md as defining additional types
- `contextcore.agent.yaml` capability `manifest.export_onboarding` → should reference it
- `MANIFEST_EXPORT_REQUIREMENTS.md` → should reference it as defining additional artifact categories
- `contextcore.benefits.yaml` `pipeline.contract_first_planning` → should reference it
- `artifact-intent.schema.json` → should reference it

### Breakpoint 6: No "Artifact Type Registry" Capability
**Impact:** The capability index describes mechanisms (how to declare intents, how to validate gates, how to export) but has NO capability that says "here is the complete vocabulary of artifact types the pipeline can produce." There is no single source that enumerates all artifact types across all categories (observability + onboarding + integrity).

### Breakpoint 7: Search Vocabulary Doesn't Bridge Domains
**Impact:** Searching for Dockerfile-related terms ("dockerfile", "container", "infrastructure", "application artifact") returns zero results. Searching for scope-related terms ("artifact scope", "artifact boundary", "beyond observability") also returns zero results. There is no vocabulary bridge between the problem domain ("what types of artifacts can the pipeline produce?") and the answer domain ("pipeline-innate requirements define additional artifact types").

---

## The Meta-Problem: Scope Discovery vs. Capability Discovery

### What REQ-CID-001–012 fixed
The original discoverability requirements addressed: **"An agent with a known problem can't find the capabilities that solve it."** The Coyote pipeline needed typed communication but couldn't discover A2A primitives through the capability index.

### What this investigation reveals
This failure is at a deeper level: **"An agent can't determine the complete scope of what the system does."** Even after reading every capability in detail, the agent couldn't answer: "Is the artifact type list exhaustive, or are there types defined elsewhere?"

### Why this is worse
- Capability discovery failure: Agent finds the wrong capability (fixable with better triggers/patterns)
- **Scope discovery failure: Agent reaches high confidence in the wrong boundary** (not fixable with better triggers — the content literally doesn't exist in the capability index)

### The confidence trap
When 12 independent sources all say "observability," an agent doesn't think "maybe there's a 13th source that contradicts this." Instead, each confirming source increases confidence. This is the **multiple-corroboration trap**: wrong information that appears in multiple places is more convincing than wrong information in one place.

---

## Quantified Impact

### Documents searched before reaching wrong conclusion: 12
### Documents with the right answer: 1 (pipeline-requirements-onboarding.md)
### Cross-references from the 12 to the 1: 0
### False ceiling reinforcement points: 7 (all independent)
### Agent confidence in wrong answer: HIGH (self-assessed)
### Time to reach wrong conclusion: ~15 minutes of exhaustive search
### Time to find right answer after user hint: ~2 minutes

### The ratio that matters
**12 sources confirming the wrong boundary : 1 source with the right answer : 0 cross-references connecting them**

This 12:1:0 ratio is the quantified measure of the discoverability failure.

---

## Classification

This failure maps to two known patterns from the existing REQ-CID analysis:

1. **Trigger mismatch** (REQ-CID root cause #1): The terms an agent would search for ("artifact scope", "what types", "beyond observability") don't appear anywhere.

2. **Cross-reference gap** (REQ-CID root cause #4): The document with the answer is not referenced from ANY of the 12 documents that create the false ceiling.

But it also introduces a NEW pattern:

3. **Reinforcing false ceiling**: Multiple independent documents all present the same incomplete boundary as authoritative, creating convergent false confidence. This is qualitatively different from a single missing cross-reference — it's a systemic consistency of incompleteness.

---

## Specific Fix Points

### Immediate fixes (break the false ceiling)

| # | File | Fix | Priority |
|---|------|-----|----------|
| 1 | `artifact_manifest.py:28` | Change docstring from "Types of observability artifacts" to "Types of artifacts that can be generated. See pipeline-requirements-onboarding.md for the complete artifact type taxonomy including onboarding and integrity types." | P1 |
| 2 | `MANIFEST_EXPORT_REQUIREMENTS.md:99` | Add: "These 8 types represent the observability artifact category. Additional categories (onboarding, integrity) are defined in pipeline-requirements-onboarding.md." | P1 |
| 3 | `contextcore.benefits.yaml:717` | Change "observability artifacts" to "artifacts" or "pipeline artifacts" in the value_statement | P1 |
| 4 | `artifact-intent.schema.json:5` | Change description from "observability artifact need" to "artifact need" | P1 |
| 5 | `pipeline-requirements-onboarding.md` | Add cross-references FROM this document TO the capability index, AND add this document to the "Related Docs" sections of MANIFEST_EXPORT_REQUIREMENTS.md, artifact_manifest.py, etc. | P1 |

### Structural fixes (prevent recurrence)

| # | What | Why | Priority |
|---|------|-----|----------|
| 6 | Create an `ArtifactTypeRegistry` capability in `contextcore.agent.yaml` | Single source of truth for ALL artifact types across all categories | P1 |
| 7 | Add `artifact_categories` taxonomy to `onboarding-metadata.json` | Programmatic discovery of artifact scope, not just individual types | P1 |
| 8 | Add discoverability test: "searching for 'artifact type' OR 'what artifacts' finds a capability that lists ALL types" | Regression prevention | P1 |
| 9 | Add a `scope_boundary` section to capability index that explicitly states what the system does and does not produce | Agents can read the boundary before searching individual capabilities | P2 |
| 10 | Update the `ArtifactType` enum to include ALL pipeline-innate artifact types, not just observability | Code-level single source of truth | P1 |

---

## Connection to ContextCore's Value Proposition

From `contextcore.meta.structured_authority` (REQ-CID-006):
> "Structured, versioned, queryable capability manifests replace ambiguous documents as the source of truth."

This investigation reveals that the capability manifests are NOT yet the source of truth for artifact scope. The source of truth is fragmented across:
- `ArtifactType` enum (observability subset)
- `MANIFEST_EXPORT_REQUIREMENTS.md` (observability subset, presented as complete)
- `pipeline-requirements-onboarding.md` (onboarding + integrity types, unreferenced)
- `onboarding-metadata.json requirements_hints` (all types, but as data, not schema)

Until the capability index contains a complete artifact type taxonomy and the fragmented definitions are consolidated, the structured authority claim is aspirational rather than actual.

---

## Analogies to Prior Failures

### Coyote Pipeline Discovery Failure (REQ-CID origin)
- **Symptom:** Coyote pipeline designers couldn't find A2A typed communication primitives
- **Root cause:** Trigger mismatch + no pipeline communication capability
- **Fix:** REQ-CID-001–012 (principles, patterns, triggers, capabilities)
- **Parallel to this failure:** Both are discoverability failures where existing content can't be found

### Key difference
The Coyote failure was about finding capabilities (things you CAN do). This failure is about finding scope (what the system COVERS). Scope is meta-information about the capability index itself — it's one level of abstraction higher.

---

## Recommendations

### For REQ_CAPABILITY_INDEX_DISCOVERABILITY.md Enhancement
Add requirements REQ-CID-013 through REQ-CID-018 addressing:
- Artifact type taxonomy as a first-class capability
- Scope boundary declarations
- Cross-reference enforcement between requirements documents and capability index
- Anti-false-ceiling validation (no document should present a subset as complete without noting the superset)
- Discoverability tests for scope questions, not just capability questions

### For Defense-in-Depth Plan
The fix must work at multiple layers simultaneously:
1. **Data layer:** Complete artifact type registry in code
2. **Schema layer:** artifact-intent.schema.json references full taxonomy
3. **Capability layer:** New capability entry for artifact type discovery
4. **Benefits layer:** Value statements describe full scope, not just observability subset
5. **Cross-reference layer:** Every document mentioning artifact types references the registry
6. **Test layer:** Discoverability tests that ask scope questions

### For Ongoing Process
This type of failure should be tested proactively: periodically ask an agent a scope-boundary question about the capability index and verify it can answer correctly without human hints.

---

## Appendix: Files Examined During Investigation

| File | Size | Key Finding |
|------|------|-------------|
| `contextcore.agent.yaml` | 115K | No mention of Dockerfiles or non-observability artifact types |
| `contextcore.benefits.yaml` | 41K | "observability artifacts" in value statement |
| `contextcore.pain_points.yaml` | 72K | No artifact scope pain points |
| `contextcore.docs.yaml` | 63K | Documents code_generation patterns but not artifact scope |
| `contextcore.user.yaml` | 35K | No artifact scope content |
| `_patterns.yaml` | 2.8K | 6 patterns, none about artifact scope |
| `_principles.yaml` | 6.6K | 9 principles, none about artifact scope |
| `_discovery_paths.yaml` | 1.8K | 7 capabilities with discovery paths, none about artifact scope |
| `_p2_capabilities.yaml` | 2.4K | typed_handoff + expected_output, no artifact scope |
| `_trigger_enrichments.yaml` | 0.7K | Pipeline triggers, no artifact scope |
| `startd8.workflow.benefits.yaml` | 42K | StartD8 benefits, no artifact scope |
| `roadmap.yaml` | 31K | Docker-compose mention in Loki rules note, no artifact types |
| `artifact_manifest.py` | 662 lines | ArtifactType enum: "observability artifacts" |
| `MANIFEST_EXPORT_REQUIREMENTS.md` | 288 lines | "Must support 8 artifact types" |
| `artifact-intent.schema.json` | 91 lines | "observability artifact need" |
| `onboarding-metadata.json` | ~1160 lines | requirements_hints with pipeline-innate label |
| **`pipeline-requirements-onboarding.md`** | **62 lines** | **THE ANSWER: agent_card, mcp_tools as pipeline-innate artifacts** |
