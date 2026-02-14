# Wayfinder Terminology

**Version:** 1.0.0
**Last Updated:** 2026-01-28
**Status:** Authoritative

This document defines the core terminology for the Wayfinder ecosystem. It serves as the authoritative source for humans and agents.

---

## Core Concepts

### ContextCore

**Type:** Standard / Specification

**Definition:** The metadata model that defines how business context is structured, queried, and exchanged between humans, agents, and systems.

**What it provides:**
- Schema for `.contextcore.yaml` project files
- Semantic conventions for attributes (e.g., `project.criticality`, `agent.insight.type`)
- Protocol for context exchange
- CRD definitions for Kubernetes

**What it is NOT:**
- Not an application
- Not a specific implementation
- Not tied to any particular tooling

**Analogy:** ContextCore is to Wayfinder as OpenTelemetry (the spec) is to Jaeger/Tempo (implementations).

---

### Wayfinder

**Type:** Reference Implementation

**Definition:** The reference implementation of the ContextCore standard—a suite of integrated development and observability tools.

**Internal Codename:** Project Muad'Dib

**Name Origin:** Inspired by the Muad'Dib (desert mouse) from Frank Herbert's *Dune*—a small creature that survives in hostile terrain and "points the way." The name reflects:
- Guiding users through fragmented tooling
- Humble but essential (metadata enables everything)
- Wisdom without overclaiming

**Components:** See [Expansion Packs](#expansion-packs) below.

**Producer:** Force Multiplier Labs

---

### Business Observability

**Type:** Paradigm

**Definition:** The practice of grounding observability in business context—connecting technical telemetry to business meaning, ownership, and impact.

**Key insight:** Observability frameworks like OpenTelemetry provide plumbing (traces, metrics, logs) but not the business context needed to make that plumbing useful. Business Observability bridges this gap.

**What it enables:**
- Stakeholders find "their" parts in dashboards
- Operators understand systems they didn't build
- Observability artifacts generated from business context, not created ad-hoc
- Authoritative onboarding for humans and agents

---

### Language Model 1.0

**Type:** Era / Paradigm

**Definition:** The current era of computing defined by the Conversational User Interface—machines that understand and generate human language well enough to be useful intermediaries.

**Key characteristics:**
- Human-in-the-middle: LLMs augment, humans validate
- Machine-to-machine: Software communicates via natural language
- Anti-hype: Acknowledges limitations, rejects AGI overclaiming
- "1.0" signals we're at the beginning, not the peak

**Relationship to Wayfinder:** Wayfinder is designed for the LM 1.0 era—built for human+agent collaboration from the ground up, not adapted from pre-LM tooling.

---

## Expansion Packs

Wayfinder components use animal names with Anishinaabe (Ojibwe) translations, honoring the indigenous peoples of Michigan and the Great Lakes region.

| Package | Animal | Anishinaabe | Type | Purpose |
|---------|--------|-------------|------|---------|
| `contextcore` | Spider | Asabikeshiinh | Core | Tasks as spans, agent insights, observability foundation |
| `contextcore-rabbit` | Rabbit | Waabooz | Extension | Alert automation framework |
| `contextcore-fox` | Fox | Waagosh | Extension | Context enrichment for alerts |
| `contextcore-coyote` | Coyote | Wiisagi-ma'iingan | Extension | Multi-agent incident resolution |
| `contextcore-beaver` | Beaver | Amik | Extension | LLM provider abstraction, cost tracking |
| `contextcore-squirrel` | Squirrel | Ajidamoo | Extension | Skills library, token-efficient discovery |

---

## Architectural Layers

```
┌─────────────────────────────────────────────────────────────┐
│                      WAYFINDER                              │
│              (Reference Implementation)                     │
│                                                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ Rabbit  │ │   Fox   │ │ Coyote  │ │ Beaver  │  ...     │
│  │ (alert) │ │(enrich) │ │(resolve)│ │  (LLM)  │          │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘          │
│       └──────────┬┴──────────┬┴───────────┘                │
│                  │           │                              │
│           ┌──────┴───────────┴──────┐                      │
│           │   Spider (contextcore)   │                      │
│           │      Core Framework      │                      │
│           └────────────┬─────────────┘                      │
└────────────────────────┼────────────────────────────────────┘
                         │
┌────────────────────────┼────────────────────────────────────┐
│                  CONTEXTCORE                                │
│            (Metadata Standard)                              │
│                                                             │
│  • .contextcore.yaml schema                                 │
│  • Semantic conventions                                     │
│  • Context exchange protocol                                │
│  • CRD definitions                                          │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              OBSERVABILITY BACKENDS                         │
│         Tempo │ Mimir │ Loki │ Grafana                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Distinctions

| Term | Is | Is NOT |
|------|-----|--------|
| ContextCore | A metadata standard/specification | An application or product |
| Wayfinder | A reference implementation (the suite) | The only way to use ContextCore |
| Spider | The core framework package | The entire ecosystem |
| Business Observability | A paradigm for grounding o11y in context | A product or tool |
| Language Model 1.0 | An era/paradigm framing | A version number for software |

---

## Naming Principles

### Honoring Indigenous Cultures

The animal naming convention uses Anishinaabe (Ojibwe) names to honor the indigenous peoples of Michigan and the Great Lakes region. Each animal's character reflects its package's purpose.

### Terms to Avoid

**"Native"** (e.g., "LM-native", "cloud-native tooling") is avoided in product naming due to potential for cultural appropriation. Alternatives:
- "Built for" instead of "native to"
- "Designed for" instead of "native"
- "First-class" instead of "native support"

### Guiding Philosophy

Naming and communication should reflect values required for responsible LLM development:
- **Thoughtfulness** — Consider implications
- **Inclusivity** — Avoid language that excludes or appropriates
- **Humility** — Anti-hype, honest about limitations
- **Respect** — For cultures, users, and the broader web of life

---

## For Agents

When referencing these concepts:

1. **ContextCore** = the standard (like a specification)
2. **Wayfinder** = the implementation (like a product)
3. **Spider/Rabbit/Fox/etc.** = components within Wayfinder
4. **Business Observability** = the paradigm we're advancing
5. **Language Model 1.0** = the era we're building for

When uncertain about terminology, defer to this document as authoritative.

---

## Versioning

This terminology document follows semantic versioning:
- **Major:** Breaking changes to core definitions
- **Minor:** New terms added
- **Patch:** Clarifications, typo fixes

---

## Future: Structured Persistence

This terminology will be persisted as structured data following the Squirrel (contextcore-squirrel) pattern:
- YAML/JSON manifest for machine consumption
- Time-series storage for version history
- Query interface for agents to discover definitions

See `contextcore-squirrel` documentation for the architectural pattern.
