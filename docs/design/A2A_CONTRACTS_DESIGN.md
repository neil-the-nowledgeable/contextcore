# A2A Contracts Design

> **Status**: Predecessor document (pre-implementation conceptual design). The implemented architecture is documented in [A2A Communications Design](design/contextcore-a2a-comms-design.md), which includes pipeline integrity checking, Three Questions diagnostic, defense-in-depth implementation, and 154 tests across 5 test files.

## Purpose

Define the design for using discrete, typed contracts to coordinate developer and agent execution in ContextCore with high interoperability and low telemetry noise.

## Audience

- Developers implementing workflow logic
- Agent authors implementing delegation and execution
- Operators validating trace integrity and rollout health

---

## What this is

A contract-first design that standardizes four data structures across A2A execution:

- `TaskSpanContract`
- `HandoffContract`
- `ArtifactIntent`
- `GateResult`

These contracts are used at every trust boundary so systems exchange typed objects instead of implicit prose.

---

## Why use it

- Prevents translation loss between export, ingestion, and artisan phases
- Makes failures attributable to a precise span/gate
- Enables deterministic automation and safer retries
- Preserves provenance and checksum continuity
- Improves A2A portability to protocol adapters

---

## Design principles

- **Typed over narrative**: fields are authoritative; text is supporting context.
- **Boundary validation**: every handoff is validated before acceptance.
- **Minimal viable telemetry**: small required attribute set first; expand only on proven query needs.
- **Fail-fast on integrity**: checksum/schema/gap-parity failures block downstream execution.
- **Versioned contracts**: schemas are explicit and pinned by `schema_version`.

---

## Where each contract is used

| Contract | Primary stage | Producer | Consumer |
| --- | --- | --- | --- |
| `TaskSpanContract` | Task lifecycle and span transitions | Orchestrator / workflow controller | Trace store, dashboards, downstream agents |
| `HandoffContract` | Agent delegation | Calling agent | Receiving agent / handoff manager |
| `ArtifactIntent` | Artifact planning and promotion decision | Export/ingestion/orchestrator | Artifact generator / validator |
| `GateResult` | Phase boundary decisions | Gate checker | Orchestrator / policy engine |

---

## When to use contracts vs events

Use a **contract object** when data must be:

- consumed by another agent/system,
- validated at a boundary,
- used for routing/blocking decisions,
- or audited later.

Use a **span event** when data is:

- local diagnostic detail,
- non-routing commentary,
- or ephemeral debug context.

---

## Artifact-as-task policy (anti-overuse)

Promote an artifact requirement into a task when one or more are true:

1. multi-step lifecycle needed,
2. dependency chain exists,
3. risk/severity warrants explicit control,
4. ownership and acceptance criteria are defined,
5. traceability/audit evidence required.

Otherwise keep it as an event within an existing phase task.

---

## End-to-end flow (high-level)

1. `TaskSpanContract` opens parent and phase spans.
2. `ArtifactIntent` defines what artifact work is required.
3. `HandoffContract` delegates work to specialized agents.
4. `GateResult` determines if downstream phase can start.
5. `TaskSpanContract` records completion/block/failure with reason and next action.

---

## Required interoperability baseline

All producers must set:

- `project_id` and `task_id` (or `handoff_id`)
- phase/status fields for lifecycle clarity
- checksum fields when present at that stage
- deterministic timestamps (`date-time`)
- explicit result/status enum values

All consumers must:

- validate against the correct schema version,
- reject invalid payloads,
- return actionable reasons on rejection,
- and emit `GateResult` on boundary outcomes.

---

## Failure modes this design addresses

- stale export/seed mismatch
- dropped artifacts during parse/transform
- handoff payload ambiguity across agents
- finalize-phase surprise failures
- over-instrumentation that creates noisy, low-value traces

---

## Non-goals (v1)

- comprehensive domain ontology for all artifact types
- auto-generated policy engine for every gate rule
- mandatory adoption across every workflow on day one

v1 is intentionally small and focused on high-value boundaries.

---

## Adoption recommendation

Start with one pilot (`PI-101-002`), prove queryability and reduced failure latency, then expand to other features after baseline stability.

> **Update**: The PI-101-002 pilot is complete. All contract types are implemented with JSON schemas, Pydantic v2 models, boundary enforcement, and phase gates. See [A2A Communications Design](design/contextcore-a2a-comms-design.md) for the full implemented architecture.
