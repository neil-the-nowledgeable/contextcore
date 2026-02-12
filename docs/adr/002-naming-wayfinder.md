# ADR-002: Naming Convention — Wayfinder and ContextCore

**Status:** Accepted
**Date:** 2026-01-28
**Author:** Force Multiplier Labs
**Codename:** Project Muad'Dib

---

## Context

As the ContextCore ecosystem matured, a clear distinction emerged between:

1. **The metadata model** — A specification/standard that defines how business context is structured, queried, and exchanged between humans, agents, and systems
2. **The reference implementation** — The suite of tools, dashboards, and expansion packs that implement this standard

These needed separate names to communicate their different purposes and enable others to implement the standard independently.

---

## Decision

### Naming Structure

| Layer | Name | Description |
|-------|------|-------------|
| **Standard** | **ContextCore** | The metadata model and specification |
| **Implementation** | **Wayfinder** | The reference implementation suite |
| **Internal Codename** | **Project Muad'Dib** | Development reference |

### Expansion Packs

The animal-named packages (using Anishinaabe/Ojibwe names) remain as components within Wayfinder:

| Package | Animal | Anishinaabe | Purpose |
|---------|--------|-------------|---------|
| contextcore | Spider | Asabikeshiinh | Core framework |
| contextcore-rabbit | Rabbit | Waabooz | Alert automation |
| contextcore-fox | Fox | Waagosh | Context enrichment |
| contextcore-coyote | Coyote | Wiisagi-ma'iingan | Multi-agent incident resolution |
| contextcore-beaver | Beaver | Amik | LLM provider abstraction |
| contextcore-squirrel | Squirrel | Ajidamoo | Skills library |

---

## Rationale

### Why "Wayfinder"

The name draws inspiration from the Muad'Dib—the small desert mouse in Frank Herbert's *Dune* that the Fremen respect for its wisdom and ability to survive in hostile terrain. The mouse "points the way."

This metaphor resonates with Wayfinder's purpose:

- **Points the way** through fragmented, ad-hoc tooling
- **Humble but essential** — a small thing (metadata) that enables survival in complex environments
- **Guides without overclaiming** — it's a guide, not the destination
- **Anti-hype positioning** — wisdom in humility, aligned with the Language Model 1.0 philosophy

#### Acknowledgment of Source Material

We acknowledge the valid criticism of the *Dune* series' colonial and orientalist overtones—its borrowing from Middle Eastern, North African, and Islamic cultures to construct an exotic "other" for Western audiences. The Fremen, while portrayed sympathetically, exist within a narrative framework that has been rightly critiqued by scholars and readers.

We chose the Muad'Dib reference narrowly: a small creature that survives through wisdom rather than power, that points the way rather than conquers. We do not adopt the messianic or colonial themes of the broader narrative.

*No Sapho juice was consumed in the creation of most of this project.*

### Why Separate Standard from Implementation

ContextCore as a standard can be implemented by others. Wayfinder is Force Multiplier Labs' reference implementation—the first composed development and observability suite built for Language Model 1.0.

This separation:
- Enables ecosystem growth
- Clarifies that the metadata model has value independent of specific tooling
- Positions ContextCore as a potential industry standard

### ContextCore Ships Code (Model C)

ContextCore is both a **specification** and a **reference library**. The `contextcore` Python package ships reusable code that any implementation can import. This is not a contradiction with the standard/implementation separation — it follows the same pattern as OpenTelemetry (specification + SDK).

**Litmus test**: "Would a third-party developer building their own implementation need this?" If yes, it belongs in ContextCore.

| Belongs in ContextCore (library) | Belongs in Wayfinder (deployment) |
|----------------------------------|-----------------------------------|
| Pydantic models (`models/`) | Sampler factory wiring |
| Type enums (`contracts/types.py`) | W3C baggage propagator setup |
| Validators (`contracts/validators.py`) | A2A trace middleware |
| Semantic convention contracts | Kubernetes-mixin recording rules |
| Metric name enums | Alertmanager routing config |
| Manifest schema and export logic | Dashboard provisioning to Grafana |
| Agent communication protocol types | Helm chart and operator deployment |
| OTel GenAI emit mode utilities | Fox/Rabbit/Coyote runtime wiring |

This means the ContextCore repository (`~/Documents/dev/ContextCore`) is **actively developed** — it is not frozen or archived. The `archived-post-separation` git tag marks the completion of the monorepo split (2026-02-01), not a code freeze. Development of library code continues on `main`.

#### Repository Roles

| Repository | Ships | Active Development |
|------------|-------|--------------------|
| `ContextCore` | `contextcore` Python package (library) | Yes — contracts, models, types, manifest logic |
| `wayfinder` | Wayfinder deployment suite | Yes — runtime wiring, dashboards, K8s manifests |
| `startd8-sdk` | `contextcore-beaver` package (library) | Yes — LLM abstraction, cost tracking |

#### Why This Matters for Agents

AI agents reading this codebase should understand:

1. **ContextCore is not spec-only.** It contains production Python code that is `pip install`-able.
2. **The `archived-post-separation` tag is a milestone, not a freeze.** 17+ commits have landed since that tag.
3. **New contracts, types, and models belong here**, not in Wayfinder. Wayfinder *consumes* ContextCore; it should not duplicate or redefine types that originate here.
4. **Implementation-specific code does not belong here.** Metrics from expansion packs (e.g., `startd8_*` from Beaver) should be injected at the CLI/deployment layer, not hardcoded in library code.

---

## Naming Principles

### Terms to Avoid

**"Native"** (e.g., "ContextCore Native", "LM-Native") should be avoided as product/feature naming.

While "native" has technical meanings (native code, cloud-native), its use in product naming risks being perceived as appropriative of Indigenous cultures. Given that:

1. This project already honors Indigenous peoples through Anishinaabe animal names
2. The Language Model 1.0 philosophy emphasizes thoughtful, inclusive development
3. Long-term success requires avoiding harm to communities and cultures

We choose to find alternative terminology that achieves the same meaning without potential harm.

**Alternatives to "Native":**
- "Built for" instead of "native to"
- "Designed for" instead of "native"
- "First-class" instead of "native support"
- "Integrated" instead of "native integration"

### Guiding Philosophy

All naming and communication in this ecosystem should reflect the values required for responsible LLM development:

1. **Thoughtfulness** — Consider implications before choosing terms
2. **Inclusivity** — Avoid language that excludes or appropriates
3. **Humility** — Anti-hype, honest about limitations
4. **Respect** — For Indigenous cultures, for users, for the broader web of life

These principles aren't constraints—they're foundations. LLM endeavors built on exploitation, appropriation, or harm are unsustainable. Those built on respect and inclusion compound trust over time.

---

## Positioning

**Wayfinder** by Force Multiplier Labs

*Positioning tagline: TBD — concept not yet fully baked*

Core ideas under consideration:
- Points the way through fragmented tooling
- Built on the ContextCore metadata standard
- Designed for human+agent collaboration
- Connection to Language Model 1.0 era and Force Multiplier Labs

---

## Consequences

### Positive
- Clear separation of standard vs implementation
- Memorable, meaningful name with depth for those who know the reference
- Aligned with anti-hype, humble positioning
- Inclusive naming principles documented for future decisions

### Neutral
- Some explanation needed for the Dune reference (acceptable—it rewards curiosity)
- May need to update existing documentation that conflates standard and implementation

### Negative
- None identified

---

## References

- Frank Herbert, *Dune* (1965) — Muad'Dib as "the one who points the way"
- Language Model 1.0 Manifesto (see FMLs marketing materials)
- ContextCore Harbor Tour (see contextcore-dot-me repo)
- [Expansion Pack Naming Convention](./docs/NAMING_CONVENTION.md)

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-28 | Initial decision documented |
| 2026-02-12 | Added "Model C" section clarifying ContextCore ships code (library vs deployment boundary) |
