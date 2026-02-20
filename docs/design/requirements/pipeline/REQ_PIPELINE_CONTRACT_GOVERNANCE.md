# Requirements: Pipeline Contract Governance

**Status:** Draft
**Date:** 2026-02-19
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (contract enforcement)
**Consolidates:**
- [Context Correctness by Construction](../CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) -- theoretical foundation
- [ContextCore Context Contracts](../ContextCore-context-contracts.md) -- defense-in-depth layers
- [Context Propagation Contracts Design](../CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) -- Layer 1 detailed design
- [A2A Communications Design](../contextcore-a2a-comms-design.md) -- A2A governance layer
- [A2A Contracts Design](../A2A_CONTRACTS_DESIGN.md) -- contract-first conceptual design
**Companion:** [REQ_CAPABILITY_DELIVERY_PIPELINE.md](REQ_CAPABILITY_DELIVERY_PIPELINE.md) -- pipeline orchestration mechanics

** Related Plan **

/Users/neilyashinsky/Documents/dev/ContextCore/docs/plans/pipeline-contract-governance-plan.md
---

## Purpose

Define the contract governance requirements for the Capability Delivery Pipeline
end-to-end. This document consolidates five design documents into a single
requirements reference that specifies **what contracts are enforced**, **where
in the pipeline enforcement occurs**, and **how the ContextCore-to-startd8
handoff preserves contract integrity**.

The pipeline has two halves:

- **ContextCore half** (stages 0--4): Metadata declaration, quality gates,
  context contract generation, and export. Produces the artifact manifest,
  provenance chain, and onboarding metadata that constitute the handoff
  contract.
- **startd8-sdk half** (stages 5--7): Plan ingestion, contractor execution
  (Artisan or Prime), and finalize verification. Consumes the handoff
  contract and delivers generated artifacts under gate enforcement.

The central claim from the source documents:

> *"Context propagation is not a feature to be added to observability -- it is
> a structural property that must be enforced at design time, the same way type
> systems enforce correctness in programming languages."*
> -- Context Correctness by Construction

This document turns that claim into verifiable requirements.

---

## Audience

- **Pipeline integrators** wiring contract enforcement into new or existing
  stages
- **Operators** diagnosing gate failures and context degradation
- **Contributors** adding new contract domains or defense-in-depth layers

---

## Pipeline Overview

```text
                        ContextCore (stages 0-4)
  +------------------------------------------------------------------------+
  |                                                                        |
  |  Stage 0     Stage 1    Stage 1.5   Stage 2         Stage 3   Stage 4   |
  |  CREATE      POLISH     FIX         2a: ANALYZE    VALIDATE  EXPORT    |
  |  project     plan       auto-remedy 2b: INIT-FROM  schema    artifact  |
  |  context     quality                -PLAN manifest check     contract  |
  |                                     boot                               |
  |                                                                        |
  |     Context Propagation Contracts (Layer 1)                            |
  |     7 Contract Domains (Layers 1-7)                                   |
  |     Defense-in-Depth Lifecycle (preflight, runtime, postexec)          |
  |                                                                        |
  +------------------------------------+-----------------------------------+
                                       |
                  Handoff artifacts:    |  {project}-artifact-manifest.yaml
                                       |  onboarding-metadata.json
                                       |  run-provenance.json
                                       |  (checksum chain intact)
                                       |
  +------------------------------------v-----------------------------------+
  |                                                                        |
  |                       startd8-sdk (stages 5-7)                         |
  |                                                                        |
  |  Stage 5: Gate 1 +      Stage 6: Contractor     Stage 7: Gate 3 +    |
  |  Plan Ingestion          Execution               Finalize Verify      |
  |  ----------------        ------------------      ----------------     |
  |  a2a-check-pipeline      Artisan (7 phases)      per-artifact sha256  |
  |  parse/assess/           or Prime Contractor     provenance chain     |
  |  transform/refine                                status rollup        |
  |  --- Gate 2 ---                                                        |
  |  a2a-diagnose                                                          |
  |                                                                        |
  |     A2A Governance (4 contract types)                                  |
  |     Boundary Enforcement (validate_outbound / validate_inbound)        |
  |     Three Questions Diagnostic (Q1/Q2/Q3)                              |
  |                                                                        |
  +------------------------------------------------------------------------+
```

---

## Part 1: Context Correctness Requirements (ContextCore Half)

These requirements derive from the Context Correctness by Construction
foundation, the Context Contracts defense-in-depth design, and the Context
Propagation Contracts Layer 1 specification.

### 1.1 Theoretical Foundation

The pipeline treats context flow through service boundaries the same way a type
system treats data flow through function signatures:

| Type System | Context Flow |
|---|---|
| **Declaration**: `fn foo(x: int) -> str` | **Contract**: Phase X requires field Y of type Z |
| **Check**: Compiler verifies types at every call site | **Validate**: Boundary checker verifies fields at every phase transition |
| **Error**: Compile error when types don't match | **Signal**: Span event when context doesn't propagate |
| **Guarantee**: Well-typed programs don't go wrong | **Guarantee**: Contract-valid pipelines don't silently degrade |

### 1.2 Contract Domain Requirements

Seven contract domains enforce different correctness properties. All share four
primitives: **Declare** (YAML contract), **Validate** (boundary checking),
**Track** (provenance stamping), **Emit** (OTel span events).

---

#### REQ-PCG-001: Context Propagation Contracts (Domain 1)

**Priority:** P1
**Status:** Implemented -- `contracts/propagation/` (62 tests)

The pipeline MUST enforce end-to-end field flow contracts via
`PropagationChainSpec`. At every phase boundary, the `BoundaryValidator` MUST
check declared fields and emit `ChainStatus` (INTACT/DEGRADED/BROKEN).

**Requirements:**

1. Pipelines MUST declare context flow requirements in YAML contracts with
   `schema_version`, `pipeline_id`, per-phase `entry`/`exit` contracts, and
   `propagation_chains`.
2. Each field declaration (`FieldSpec`) MUST specify `name` (dot-path),
   `severity` (BLOCKING/WARNING/ADVISORY), and optionally `default`,
   `source_phase`, `type`, and `description`.
3. BLOCKING fields that are absent MUST set `passed=False` and halt the phase.
4. WARNING fields that are absent MUST apply the declared default (mutating
   the context dict), emit a DEFAULTED status, and continue.
5. ADVISORY fields that are absent MUST log and continue with PARTIAL status.
6. Propagation chains MUST verify source-to-destination field flow with
   optional waypoints and verification expressions.
7. Chain verification MUST produce INTACT (field flowed correctly), DEGRADED
   (destination has default/empty value), or BROKEN (source absent, destination
   absent, or verification failed).

**Acceptance criteria:**
- `context.boundary.{entry|exit|enrichment}` span events emitted at every
  phase transition
- `context.chain.{validated|degraded|broken}` span events emitted per chain
- `context.propagation_summary` event emitted once per pipeline run with
  `completeness_pct`

---

#### REQ-PCG-002: Schema Compatibility Contracts (Domain 2)

**Priority:** P1
**Status:** Implemented -- `contracts/schema_compat/` (~68 tests)

The pipeline MUST validate semantic contracts between services, not just
structural schemas. When Service A produces `{"status": "active"}` and
Service B expects `{"state": "running"}`, the mapping MUST be declared and
validated at integration boundaries.

**Requirements:**

1. Schema compatibility contracts MUST declare the semantic mapping between
   producer and consumer field names and values.
2. Violations MUST produce structured signals distinguishing structural
   mismatches from semantic mismatches.

**Acceptance criteria:**
- Schema compatibility checks run at phase boundaries alongside propagation
  checks
- Violations produce OTel span events with schema context

---

#### REQ-PCG-003: Semantic Convention Alignment (Domain 3)

**Priority:** P2
**Status:** Partial -- domain logic implemented in `contracts/semconv/` (20 tests); lifecycle wiring implemented but end-to-end integration pending validation

The pipeline MUST enforce consistent attribute naming across services. When
one component emits `user.id` and another emits `user_id`, the convention
check MUST flag the discrepancy.

**Requirements:**

1. Convention specs MUST declare canonical attribute names per namespace.
2. CI validation MUST check emitted attributes against the convention spec.
3. Violations MUST identify the non-conforming attribute and the canonical
   alternative.

**Acceptance criteria:**
- `validate_enum_consistency.py` enforces conventions across repos
- Convention violations produce actionable error messages

---

#### REQ-PCG-004: Causal Ordering Contracts (Domain 4)

**Priority:** P2
**Status:** Partial -- domain logic implemented in `contracts/ordering/` (22 tests); lifecycle wiring implemented but end-to-end integration pending validation

The pipeline MUST enforce ordering constraints for events that must be
processed sequentially.

**Requirements:**

1. `OrderingConstraintSpec` MUST declare "event A must be processed before
   event B across any execution path."
2. Ordering violations MUST produce BROKEN chain status with a causal
   explanation referencing provenance timestamps.

**Acceptance criteria:**
- Phase-sequential execution model enforces ordering within a pipeline
- Cross-boundary ordering violations are detectable and signaled

---

#### REQ-PCG-005: Capability/Permission Propagation (Domain 5)

**Priority:** P2
**Status:** Partial -- domain logic implemented in `contracts/capability/` (18 tests); lifecycle wiring implemented but end-to-end integration pending validation

The pipeline MUST verify that required capabilities and permissions propagate
through trust boundaries.

**Requirements:**

1. `CapabilityChainSpec` MUST declare available capabilities at the source
   and required capabilities at the destination.
2. Chain validation MUST verify the capability survived the channel, using
   the same primitives as `PropagationChainSpec`.

**Acceptance criteria:**
- Capability propagation uses `FieldSpec(name="auth.scopes",
  severity=BLOCKING)` at relevant boundaries
- Missing capabilities produce BROKEN status

---

#### REQ-PCG-006: SLO Budget Propagation (Domain 6)

**Priority:** P2
**Status:** Partial -- domain logic implemented in `contracts/budget/` (19 tests); lifecycle wiring implemented but end-to-end integration pending validation

The pipeline MUST track per-phase budget allocations so that budget overflows
are detected before they cascade.

**Requirements:**

1. `BudgetPropagationSpec` MUST declare per-phase budget allocations.
2. The tracker MUST stamp `remaining_budget_ms` at each boundary.
3. DEGRADED status MUST fire when a hop consumes more than its allocation.
4. BROKEN status MUST fire when the remaining budget goes negative.

**Acceptance criteria:**
- Budget tracking spans include `remaining_budget_ms` at each phase boundary
- DEGRADED budget violation emits a WARNING-severity `GateResult` with `context.budget.status = "degraded"` scoped to the phase that exceeded its allocation
- BROKEN budget violation (negative remaining budget) emits a BLOCKING-severity `GateResult` with `context.budget.status = "broken"`

---

#### REQ-PCG-007: Data Lineage/Provenance (Domain 7)

**Priority:** P2
**Status:** Partial -- domain logic implemented in `contracts/lineage/` (21 tests); lifecycle wiring implemented but end-to-end integration pending validation

The pipeline MUST track the origin and transformation history of context
data flowing through phases.

**Requirements:**

1. `PropagationTracker.stamp()` MUST record `FieldProvenance(origin_phase,
   set_at, value_hash)` in the context dict under the reserved key
   `_cc_propagation`.
2. `value_hash` MUST be `sha256(repr(value))[:8]` to detect value mutation
   without storing the full value.
3. Provenance MUST travel with the data it describes (stored in the context
   dict, not externally) to avoid meta-propagation failures.
4. At finalize, all chain provenance MUST be verifiable: if a field was set
   in phase A with hash H, phase F must be able to confirm the hash matches.

**Acceptance criteria:**
- `_cc_propagation` key present in context dict with per-field provenance
- Hash mismatch between stamp and check produces a signal

---

### 1.3 Defense-in-Depth Lifecycle Requirements

Each contract domain can be enforced at multiple lifecycle stages. These
requirements specify the enforcement timing.

---

#### REQ-PCG-008: Pre-Flight Validation (BEFORE execution)

**Priority:** P1
**Status:** Implemented -- `contracts/preflight/`

Before any pipeline stage executes, the system MUST verify:

1. All critical `entry.required` fields have non-default values in the
   initial context.
2. The enriched seed contains the expected enrichment keys.
3. The dependency graph of phases matches the contract graph.

**Requirements:**

1. `workflow.verify_propagation_contracts(initial_context)` MUST return
   violations categorized as critical (halt) or warning (log and continue).
2. Pre-flight validation MUST run automatically when `contract_path` is
   provided to the orchestrator.
3. Pre-flight MUST be bypassable via `--skip-preflight` flag, consistent
   with `--skip-polish`, `--skip-fix`, `--skip-validate` in the companion
   pipeline. This supports environments where contracts are being adopted
   incrementally.

**Acceptance criteria:**
- Critical pre-flight violations halt execution with actionable error
- Warning-level violations are logged and appear in OTel

---

#### REQ-PCG-009: Runtime Boundary Checks (DURING execution)

**Priority:** P1
**Status:** Implemented -- `contracts/runtime/`

At each phase transition during execution, the system MUST:

1. Run `validate_phase_boundary()` checking enrichment fields from the
   contract YAML.
2. Apply defaults for WARNING-severity absent fields (mutating the context).
3. Emit `context.boundary.{entry|exit|enrichment}` span events.
4. Preserve backward compatibility: existing `validate_phase_entry()` and
   `validate_phase_exit()` MUST remain unchanged. Contract validation adds
   enrichment checking on top, not instead of.

**Requirements:**

1. The existing blocking validation layer (`validate_phase_entry()`,
   `validate_phase_exit()`) MUST NOT be modified.
2. Contract validation MUST be opt-in via `contract_path` parameter.
3. If ContextCore is not installed (minimal SDK deployment), the wrapper
   MUST return `None` and existing validation MUST still run.

**Acceptance criteria:**
- Contract validation adds no overhead when `contract_path` is not provided
- Phase transitions with contracts produce both blocking validation and
  enrichment validation events

---

#### REQ-PCG-010: Post-Execution Validation (AFTER execution)

**Priority:** P1
**Status:** Implemented -- `contracts/postexec/`

After pipeline execution completes, the system MUST:

1. Run `validate_all_chains()` checking every declared propagation chain.
2. Emit `context.propagation_summary` with `total_chains`, `intact`,
   `degraded`, `broken`, and `completeness_pct`.
3. Replace the inline `_validate_propagation_completeness()` point fix
   with contract-driven generalization (inline fallback preserved for
   environments without ContextCore).

**Acceptance criteria:**
- Summary event emitted at finalize with accurate chain counts
- `completeness_pct` queryable via TraceQL

---

#### REQ-PCG-011: Observability Contracts (CONTINUOUS)

**Priority:** P1
**Status:** Implemented -- `contracts/observability/`

The contract system itself MUST be observable through the same infrastructure
it validates.

**Requirements:**

1. All contract enforcement actions MUST emit OTel span events on the
   current active span.
2. If OTel is not installed, events MUST be logged only (no crash).
3. TraceQL queries MUST be able to find: broken chains, degraded chains,
   phases with enrichment defaults, runs with low completeness.
4. Grafana dashboards MUST include panels for propagation completeness,
   broken chains over time, and enrichment defaults applied.
5. Alerting rules MUST fire when propagation completeness drops below
   threshold or a chain is broken.

**Acceptance criteria:**
- `{ name = "context.chain.broken" }` returns results in TraceQL
- `{ name = "context.propagation_summary" && span.context.completeness_pct < 100 }` works
- Alert rules defined for `ContextPropagationDegraded` and `ContextChainBroken`

---

#### REQ-PCG-012: Regression Detection (CI/CD)

**Priority:** P2
**Status:** Implemented -- `contracts/regression/`

The CI pipeline MUST prevent contract regressions.

**Requirements:**

1. A CI gate MUST run propagation graph analysis on PRs that modify
   phase handlers or contract YAML.
2. Propagation completeness MUST NOT decrease between builds.
3. Contract drift MUST be detected: if a phase changes its
   produces/requires, the graph MUST be re-validated.
4. Removed fields or weakened severity MUST block the PR.

**Acceptance criteria:**
- CI blocks PRs that reduce propagation completeness
- Contract drift detection runs on modified contract YAML files

---

### 1.4 Severity Model Requirements

---

#### REQ-PCG-013: Three-Tier Severity Model

**Priority:** P1

The pipeline MUST use a three-tier severity model that maps to existing
`ConstraintSeverity` from `contracts/types.py`.

| Severity | On Absence | Behavior | Weaver Level |
|---|---|---|---|
| `BLOCKING` | Sets `passed=False` | Halts phase | `required` |
| `WARNING` | Applies default, continues | Emits DEFAULTED status | `recommended` |
| `ADVISORY` | Logs, continues | Emits PARTIAL status | `opt_in` |

**Requirements:**

1. Severity MUST reuse the existing `ConstraintSeverity` enum (not a new one).
2. BLOCKING-severity absent fields MUST prevent the phase from executing.
3. WARNING-severity absent fields with a declared default MUST have the
   default injected into the context dict (intentional mutation).
4. WARNING-severity absent fields without a default MUST record DEFAULTED
   status with `default_applied=False`.
5. ADVISORY-severity absent fields MUST be logged at DEBUG level only.
6. When defaults are injected (requirement 3), the injecting phase MUST
   stamp provenance via `PropagationTracker.stamp()` with the current
   phase as `origin_phase` and `default_applied=True` in the provenance
   metadata.

**Acceptance criteria:**
- BLOCKING absence emits `context.boundary.entry` with `context.passed = false` and `context.blocking_count >= 1`
- WARNING absence emits `context.boundary.enrichment` with `context.propagation_status = "defaulted"` and `context.default_applied = true`
- ADVISORY absence emits `context.boundary.enrichment` with `context.propagation_status = "partial"` at DEBUG level
- No new severity enum introduced

---

### 1.5 Provenance Requirements

---

#### REQ-PCG-014: Provenance Tracking

**Priority:** P1

Context provenance MUST be tracked inline with the context it describes.

**Requirements:**

1. Provenance metadata MUST be stored in the context dict under the reserved
   key `_cc_propagation`.
2. Each stamped field MUST have a `FieldProvenance` record containing
   `origin_phase` (str), `set_at` (ISO 8601), and `value_hash`
   (`sha256(repr(value))[:8]`).
3. Handlers MUST NOT overwrite the `_cc_propagation` key (the `_cc_` prefix
   signals "internal, do not touch").
4. Provenance MUST travel with the data through the same channel, subject
   to the same propagation dynamics, to avoid meta-propagation failures.
5. Stages 0 (CREATE) and 1 (POLISH) MUST seed the `_cc_propagation` dict
   with initial project context provenance. Without this seeding, the
   provenance chain starts late and misses the project root context.

**Acceptance criteria:**
- Provenance survives all phase transitions intact
- Value mutation between stamp and check is detectable via hash comparison
- `_cc_propagation` dict is present after Stage 0 with initial field provenance

---

### 1.6 Contract Declaration Requirements

---

#### REQ-PCG-015: Dual-Declaration Pattern

**Priority:** P1

Contracts MUST follow the dual-declaration pattern: YAML as source of truth,
Python validates against it.

**Requirements:**

1. Contract YAML MUST be the authoritative declaration of context flow
   requirements, reviewed in PRs alongside code.
2. Pydantic v2 models (`ContextContract`, `FieldSpec`, `PhaseContract`,
   `PropagationChainSpec`) MUST validate the YAML with `extra="forbid"`
   to reject unknown keys at parse time.
3. The framework (schema models, loader, validators, tracker, OTel helpers)
   MUST live in **ContextCore** under `src/contextcore/contracts/propagation/`.
4. Concrete pipeline contracts (Artisan YAML) MUST live in **startd8-sdk**
   under `src/startd8/contractors/contracts/`.

**Acceptance criteria:**
- Contract YAML is parseable by `ContractLoader`
- Unknown keys in YAML produce parse-time errors
- ContextCore and startd8-sdk each own their respective contract artifacts

---

#### REQ-PCG-016: Progressive Adoption Path

**Priority:** P2

The contract system MUST support incremental adoption without requiring
full commitment on day one.

**Requirements:**

1. All contract validation MUST be opt-in via `contract_path` parameter.
2. Existing pipelines MUST work unchanged without `contract_path`.
3. Adoption MUST follow the path: declaration only (documentation) ->
   loader (emit events, don't block) -> monitor (dashboard) -> tighten
   (promote severity levels).
4. Fields MUST be promotable from `advisory` -> `warning` -> `blocking`
   as confidence grows.
5. New contract domains MUST be deployable independently -- each layer
   can be implemented without the others.

**Acceptance criteria:**
- A pipeline without `contract_path` has zero overhead from contract system
- A pipeline can use Layer 1 only without Layers 2-7

---

## Part 2: A2A Governance Requirements (startd8-sdk Half)

These requirements derive from the A2A Communications Design, the A2A
Contracts Design, and the defense-in-depth principles. They govern stages
5-7 of the pipeline where startd8-sdk consumes the handoff contract and
delivers generated artifacts.

### 2.1 Contract Type Requirements

---

#### REQ-PCG-017: Four Typed A2A Contracts

**Priority:** P1
**Status:** Implemented -- `contracts/a2a/` (154 tests)
**Source:** [5] A2A Contracts Design §2 (Contract Types); [4] A2A Communications Design §3 (Typed Contract Models)

All agent-to-agent communication MUST use one of four typed contracts.

| Contract | Purpose | Key Fields |
|---|---|---|
| `TaskSpanContract` | Task/subtask lifecycle as a trace span | `project_id`, `task_id`, `phase`, `status`, `checksums`, `metrics` |
| `HandoffContract` | Agent-to-agent delegation | `from_agent`, `to_agent`, `capability_id`, `inputs`, `expected_output`, `priority` |
| `ArtifactIntent` | Declaration of planned artifact work | `artifact_id`, `artifact_type`, `intent`, `parameter_sources`, `promotion_reason` |
| `GateResult` | Quality/integrity gate outcome | `gate_id`, `phase`, `result`, `severity`, `blocking`, `evidence`, `reason`, `next_action` |

**Requirements:**

1. Each contract MUST have both a JSON schema (in `schemas/contracts/`)
   and a matching Pydantic v2 model (in `contracts/a2a/models.py`).
2. All models MUST use `ConfigDict(extra="forbid")` and enforce
   `schema_version = "v1"`.
3. All producers MUST set `project_id`, `task_id` (or `handoff_id`),
   phase/status fields, checksum fields when applicable, deterministic
   timestamps, and explicit result/status enum values.
4. All consumers MUST validate against the correct schema version, reject
   invalid payloads, return actionable reasons on rejection, and emit
   `GateResult` on boundary outcomes.

**Acceptance criteria:**
- All four contract types have JSON schemas and Pydantic models
- Invalid payloads produce structured `ValidationErrorEnvelope`
- Boundary enforcement emits telemetry on rejection

---

### 2.2 Boundary Enforcement Requirements

---

#### REQ-PCG-018: Validate at Every Boundary

**Priority:** P1
**Status:** Implemented -- `boundary.py`
**Source:** [4] A2A Communications Design §4 (Boundary Enforcement); [2] ContextCore Context Contracts (defense-in-depth layers)

Every handoff between pipeline steps MUST be validated.

**Requirements:**

1. `validate_outbound(contract_name, payload)` MUST validate before sending.
2. `validate_inbound(contract_name, payload)` MUST validate on receipt.
3. Failures MUST raise `BoundaryEnforcementError` with
   `.to_failure_event()` for telemetry.
4. When an OTel span is active, failure events MUST be automatically
   attached as span events.
5. The validator MUST reject unknown fields (`additionalProperties: false`),
   enforce required fields, validate enums, and produce structured error
   envelopes with `error_code`, `failed_path`, `message`, and `next_action`.

**Acceptance criteria:**
- Every handoff has both outbound and inbound validation
- Silent handoff failures are impossible in instrumented code paths

---

#### REQ-PCG-019: Checksums as Circuit Breakers

**Priority:** P1
**Status:** Implemented -- `gates.py`, `pipeline_checker.py`
**Source:** [4] A2A Communications Design §5 (Checksum Chain Integrity)

The pipeline MUST maintain a checksum chain that is recomputed from actual
files and compared against stored values at every gate.

```text
.contextcore.yaml --sha256--> onboarding-metadata.json
                              |-- source_checksum          <-- recomputed
                              |-- artifact_manifest_checksum <-- recomputed
                              +-- project_context_checksum   <-- recomputed
                                        |
                    provenance.json cross-checks source_checksum
                                        |
                              artisan seed.json (source_checksum)
                                        |
                              FINALIZE report (per-artifact sha256)
```

**Requirements:**

1. If `source_checksum` at any stage doesn't match the original, the
   pipeline MUST halt (checksum gate is BLOCKING).
2. Checksums MUST be recomputed from files at verification time, not
   trusted from stored values alone.
3. Stale data from previous runs MUST be detectable via checksum mismatch.

**Acceptance criteria:**
- Tampered `source_checksum` causes gate failure
- `a2a-pilot --source-checksum sha256:BAD` demonstrates failure injection

---

### 2.3 Gate Requirements

---

#### REQ-PCG-020: Gate 1 -- Pipeline Integrity (Export -> Plan Ingestion)

**Priority:** P1
**Status:** Implemented -- `pipeline_checker.py` (34 tests)
**Source:** [4] A2A Communications Design §6 (Gate Definitions, Gate 1)

Gate 1 MUST run 8 integrity checks on export output before plan ingestion
consumes it.

| # | Gate | Blocking? |
|---|---|---|
| 1 | Structural integrity (required fields, schema prefix) | Yes |
| 2 | Checksum chain (recomputed SHA-256 vs stored) | Yes |
| 3 | Provenance cross-check (provenance.json vs onboarding metadata) | Yes |
| 4 | Mapping completeness (every gap has a task mapping) | Yes |
| 5 | Gap parity (declared coverage gaps in `{project}-artifact-manifest.yaml` match artifact features) | Yes |
| 6 | Design calibration (valid depth tiers, expected LOC) | No (warning) |
| 7 | Parameter resolvability (parameter_sources resolve to values) | No (warning) |
| 8 | Artifact inventory (Mottainai provenance v2 cross-check) | No (warning) |

**Requirements:**

1. All 8 gates MUST run via `contextcore contract a2a-check-pipeline`.
2. Blocking gate failures MUST halt downstream execution.
3. Non-blocking failures (gates 6-8) MUST produce warnings with
   `next_action` guidance.
4. `PipelineCheckReport` MUST aggregate results with `is_healthy`,
   `to_text()`, `summary()`, and `write_json()`.
5. An optional `--min-coverage` threshold MUST fail if overall coverage
   is below the specified minimum.

**Acceptance criteria:**
- All 8 gates produce `GateResult` with evidence and next_action
- `--fail-on-unhealthy` exits non-zero on any blocking failure
- Gate results are queryable in Tempo

---

#### REQ-PCG-021: Gate 2 -- Three Questions Diagnostic (Plan Ingestion -> Contractor)

**Priority:** P1
**Status:** Implemented -- `three_questions.py` (25 tests)
**Source:** [4] A2A Communications Design §6 (Gate Definitions, Three Questions Diagnostic)

Gate 2 MUST implement the Three Questions diagnostic, stopping at the first
failing question.

| Question | Layer | Checks |
|---|---|---|
| **Q1: Is the contract complete?** | Export | All Gate 1 checks + artifact manifest population, derivation rules, parameter schema |
| **Q2: Was the contract faithfully translated?** | Plan Ingestion | PARSE coverage, ASSESS complexity score, TRANSFORM routing correctness, review output |
| **Q3: Was the translated plan faithfully executed?** | Contractor | Design handoff fidelity, output files, test/review results, FINALIZE report |

**Requirements:**

1. The diagnostic MUST stop at the first failing question ("if Q1 fails,
   fixing anything in Q2 or Q3 is wasted effort").
2. `DiagnosticResult` MUST include `all_passed`, `first_failure`, and
   `start_here` recommendation.
3. Q2 MUST verify: PARSE extracted all coverage gaps as features, ASSESS
   complexity score satisfies the variance invariant (at least 2 of 7
   dimensions MUST differ by ≥10 points; standard deviation across
   dimensions MUST exceed 5), TRANSFORM routing matches complexity score
   OR an explicit `force_route` override is documented in the routing
   decision.
4. Q3 MUST verify: per-task status rollup, artifact list matches
   `coverage.gaps`, provenance chain intact from export through finalize.

**Acceptance criteria:**
- Diagnostic stops at Q1 failure and does not evaluate Q2/Q3
- `start_here` field provides actionable first step for operator
- `--fail-on-issue` exits non-zero on any question failure

---

#### REQ-PCG-022: Gate 3 -- Finalize Verification (Contractor -> Output)

**Priority:** P1
**Status:** Partial -- Gate 3 validation exists in startd8-sdk (`context_seed_handlers.py`) for multi-file split completeness; end-to-end finalize verification not yet wired as standalone gate
**Source:** [4] A2A Communications Design §6 (Gate Definitions, Gate 3 / Q3)

Gate 3 MUST verify the final artifacts against the original contract.
Gate 3 runs Q3 of the Three Questions diagnostic (`a2a-diagnose`) against
contractor outputs. This is the same tool used for Gate 2 but evaluating
only the Q3 checks.

**Requirements:**

1. Per-artifact SHA-256 checksums MUST be computed by hashing files on
   disk (integrity verification). This checks that artifacts exist and
   are not corrupted — it does NOT require deterministic regeneration
   (reproducibility).
2. The provenance chain MUST be verifiable: `source_checksum` from export
   MUST match the source checksum in the finalize report.
3. Status rollup MUST report: total tasks, succeeded, failed, partial.
4. A `partial` or `failed` overall status MUST indicate which artifacts
   were not generated.
5. Every gap from `coverage.gaps` MUST have a corresponding artifact with
   a checksum in the finalize report.
6. **Content-level verification** — Gate 3 MUST perform the following
   checks on generated artifact content (not just existence/integrity):
   a. **Placeholder scan** — all generated files MUST be scanned for
      common placeholder patterns (`REPLACE_WITH`, `TODO`, `FIXME`,
      `PLACEHOLDER`, `INSERT_HERE`, `xxx`). Any match MUST produce a
      BLOCKING gate failure with evidence citing the file, line, and
      matched pattern.
   b. **Schema field cross-reference** — when the input context includes
      `.proto`, OpenAPI, or JSON Schema files, Gate 3 MUST verify that
      generated source code uses field names consistent with those
      schemas. Mismatches MUST produce a WARNING gate result with
      evidence identifying the expected and actual field names.
   c. **Cross-artifact consistency** — for each service, Gate 3 MUST
      verify that dependency manifests (`requirements.in`, `go.mod`,
      `package.json`) declare all packages imported by the service's
      source files. Missing dependencies MUST produce a BLOCKING gate
      failure.
   d. **Protocol coherence** — when `service_metadata` (REQ-PCG-024
      requirement 7) declares a transport protocol, Gate 3 MUST verify
      that generated Dockerfiles, client code, and health checks are
      consistent with that protocol. Protocol mismatches MUST produce
      a BLOCKING gate failure.

**Acceptance criteria:**
- All generated artifacts have checksums
- Missing artifacts are identifiable from the finalize report
- Provenance chain from `.contextcore.yaml` through finalize is intact
- No generated artifact contains placeholder/template strings (6a)
- Generated code field names match input schema field names (6b)
- Dependency manifests declare all imported packages (6c)
- Protocol-specific artifacts match declared service protocol (6d)

---

### 2.4 Fail Loud, Fail Early, Fail Specific

---

#### REQ-PCG-023: Structured Gate Results

**Priority:** P1
**Source:** [4] A2A Communications Design §4 (Gate Result Specification); [5] A2A Contracts Design §3 (GateResult Contract)

Every gate failure MUST produce a `GateResult` with actionable guidance.

**Requirements:**

1. Every `GateResult` MUST include: `gate_id`, `phase`, `result`
   (pass/fail), `severity`, `blocking` (boolean), `evidence` (list of
   `EvidenceItem` with `type`, `ref`, `description`), `reason`, and
   `next_action`.
2. `next_action` MUST be a specific, executable instruction (e.g.,
   "Re-run export with --emit-provenance to populate provenance.json").
3. For each failure, diagnostics MUST check 4 dimensions: input integrity,
   completeness, freshness, and parameter fidelity.

**Acceptance criteria:**
- No gate produces a failure without a `next_action`
- `next_action` values are specific enough to be executed by an operator

---

### 2.5 Handoff Contract Requirements

---

#### REQ-PCG-024: ContextCore-to-startd8 Handoff Integrity

**Priority:** P1
**Source:** [4] A2A Communications Design §3 (Handoff Contract); [5] A2A Contracts Design §3 (HandoffContract Type)

The handoff between ContextCore stages (0-4) and startd8-sdk stages (5-7)
MUST be governed by explicit contract artifacts.

**Requirements:**

1. The handoff MUST consist of three core artifacts plus optional
   enrichment files:
   - `{project}-artifact-manifest.yaml` -- what artifacts are needed (the CONTRACT)
   - `onboarding-metadata.json` -- machine-readable schemas, checksums,
     enrichment data for automated validation
   - `run-provenance.json` -- audit trail with checksums across all stages
   - Optional: `*.json` and `*.yaml` files matching
     `{output_dir}/**/*-enrichment.*` glob pattern for additional
     enrichment data
2. The artifact manifest MUST declare every observability artifact needed,
   derived from business criticality, SLOs, and alerting requirements.
3. Onboarding metadata MUST include the fields documented in the A2A
   Communications Design:
   - REQUIRED (core) fields — absence causes Gate 1 failure:
     `artifact_types`, `parameter_sources`, `parameter_schema`,
     `coverage.gaps`, `semantic_conventions`, checksums (source, manifest,
     CRD), `artifact_task_mapping`, `design_calibration_hints`,
     `file_ownership`
   - OPTIONAL (enrichment) fields — absence produces Gate 1 warning:
     `derivation_rules`, `expected_output_contracts`,
     `artifact_dependency_graph`, `resolved_artifact_parameters`,
     `open_questions`, `objectives`, `requirements_hints`
7. When the project generates executable services, onboarding metadata
   MUST include a `service_metadata` map keyed by service name. Each
   entry MUST declare:
   - `transport_protocol` (REQUIRED): `grpc` | `http` | `grpc-web`.
     Drives Dockerfile HEALTHCHECK type, client stub generation, and
     protocol fidelity validation (REQ-PCG-027 requirement 5b).
   - `schema_contract` (REQUIRED when `transport_protocol` is `grpc`):
     relative path to the `.proto` file defining the service's RPC
     interface. Used for schema field validation (REQ-PCG-027
     requirement 5c).
   - `base_image` (OPTIONAL): fully qualified base image reference with
     digest (e.g., `python:3.14.2-alpine@sha256:31da4cb5...`). When
     provided, MUST be propagated to `resolved_artifact_parameters` so
     the contractor does not need to resolve digests at generation time.
   - `healthcheck_type` (OPTIONAL, defaults to `transport_protocol`):
     override for services where the health check protocol differs from
     the service protocol.

   Absence of `service_metadata` for a service-generating project MUST
   produce a Gate 1 warning. Absence of `transport_protocol` for any
   declared service MUST produce a Gate 1 failure.

   Example:
   ```yaml
   service_metadata:
     recommendationservice:
       transport_protocol: grpc
       schema_contract: context/demo.proto
       base_image: "python:3.14.2-alpine@sha256:31da4cb5..."
     shoppingassistantservice:
       transport_protocol: http
       base_image: "python:3.14.2-slim"
   ```
4. The provenance chain MUST accumulate across all ContextCore stages
   (create -> polish -> fix -> export) so that startd8-sdk can verify
   the full history.
5. `source_checksum` in onboarding metadata MUST match the SHA-256 of
   the source `.contextcore.yaml` file.
6. The E2E orchestration runtime environment spanning both ContextCore
   and startd8-sdk is deferred to Phase 2 (containerized or documented
   venv setup required for reproducible execution).
8. Onboarding enrichment fields (`derivation_rules`,
   `resolved_artifact_parameters`, `expected_output_contracts`,
   `design_calibration_hints`, `open_questions`,
   `artifact_dependency_graph`, `semantic_conventions`) MUST be
   available for end-to-end propagation when present in
   `onboarding-metadata.json`. Gate 1 MUST verify that enrichment
   fields present in the file are structurally valid (correct types,
   non-empty when populated). Gate 1 MUST emit a WARNING when OPTIONAL
   enrichment fields are absent from `onboarding-metadata.json` in a
   project that produces them at export time.
   **Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Failure 3, Gaps 1–7
9. The provenance chain (`run-provenance.json`) MUST record which
   onboarding enrichment fields were available at export time, enabling
   downstream stages to detect when enrichment was available but not
   forwarded. The record MUST include field names and a boolean
   presence indicator per field (not field values).

**Acceptance criteria:**
- Gate 1 passes when handoff artifacts are well-formed
- Gate 1 fails when any artifact is missing, stale, or has checksum mismatch
- Plan ingestion can consume the handoff without additional manual steps
- Enrichment fields present in `onboarding-metadata.json` are readable
  by plan-ingestion without transformation
- Gate 1 emits WARNING when enrichment fields are absent but the
  project's export stage is capable of producing them
- Provenance chain records enrichment field availability at export time

---

#### REQ-PCG-025: Context Propagation Across the Handoff Boundary

**Priority:** P1
**Source:** [2] ContextCore Context Contracts (dual-declaration architecture); [3] Context Propagation Contracts Design §5 (cross-boundary propagation)

Context propagation contracts (Layer 1) MUST extend across the ContextCore-to-
startd8 handoff boundary.

**Requirements:**

1. The `PropagationChainSpec` MUST support chains that span both halves
   of the pipeline (e.g., domain classification set in ContextCore stages
   must reach Artisan IMPLEMENT in startd8-sdk).
2. Framework code (schema, loader, validator, tracker, OTel helpers) MUST
   live in ContextCore; concrete pipeline contracts MUST live in startd8-sdk.
3. `BoundaryValidator` MUST operate at the handoff boundary the same way
   it operates at intra-pipeline phase boundaries.
4. If ContextCore is not installed in the startd8-sdk environment, the
   **Propagation Contract** validation wrapper MUST degrade gracefully
   (return `None`, existing validation still runs). However, **A2A
   Contract** validation (Pydantic models in startd8-sdk) MUST remain
   active regardless of ContextCore availability — these are mandatory
   contracts that live in startd8-sdk itself.

| Component | Repository | Path |
|---|---|---|
| Schema models | ContextCore | `src/contextcore/contracts/propagation/schema.py` |
| YAML loader | ContextCore | `src/contextcore/contracts/propagation/loader.py` |
| Boundary validator | ContextCore | `src/contextcore/contracts/propagation/validator.py` |
| Propagation tracker | ContextCore | `src/contextcore/contracts/propagation/tracker.py` |
| OTel emission | ContextCore | `src/contextcore/contracts/propagation/otel.py` |
| Artisan contract YAML | startd8-sdk | `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml` |
| Validation wrapper | startd8-sdk | `src/startd8/contractors/context_schema.py` |
| Orchestrator wiring | startd8-sdk | `src/startd8/contractors/artisan_contractor.py` |

**Acceptance criteria:**
- A propagation chain spanning both halves produces INTACT/DEGRADED/BROKEN
  status at finalize
- startd8-sdk without ContextCore installed still runs (graceful degradation)

---

### 2.6 Contractor Execution Requirements

---

#### REQ-PCG-026: Plan Ingestion Contract Compliance (Stage 5)

**Priority:** P1
**Source:** [4] A2A Communications Design §7 (Plan Ingestion Stages: PARSE/ASSESS/TRANSFORM/REFINE/EMIT)

Plan ingestion MUST faithfully translate the artifact manifest contract into
executable work items.

**Requirements:**

1. PARSE MUST extract every `coverage.gaps` entry as a candidate feature.
   Dropped artifacts MUST be detectable by gap parity checks.
2. ASSESS MUST score 7 complexity dimensions (0-100) using
   `parameter_sources`, `artifact_types`, and `coverage.gaps`. Scores
   MUST satisfy the variance invariant: at least 2 of 7 dimensions MUST
   differ by ≥10 points, and standard deviation across dimensions MUST
   exceed 5. Degenerate scores (all 0, all 100, or uniform) MUST be
   rejected.
3. TRANSFORM MUST route by complexity: score <= 40 to Prime Contractor,
   > 40 to Artisan. `force_route` MUST be able to override.
4. Gaps MAY be excluded via `excluded_gaps` in the artifact manifest
   with a mandatory `reason` field per excluded gap. Excluded gaps MUST
   appear in the audit trail but MUST NOT cause parse coverage failure.
4. REFINE MUST run N rounds of architectural review against the artifact
   manifest as requirements spec.
5. EMIT MUST write review config and optionally ContextCore task tracking
   artifacts.
6. EMIT MUST bridge all onboarding enrichment fields from the export
   output directory into the context seed:
   a. Read `onboarding-metadata.json` from the pipeline output directory
      (i.e., `contextcore_export_dir` — the same directory containing
      the artifact manifest and provenance), NOT from `context_files`.
   b. Populate the seed's `onboarding` section with all enrichment
      fields present in the file (`derivation_rules`,
      `resolved_artifact_parameters`, `expected_output_contracts`,
      `design_calibration_hints`, `open_questions`,
      `artifact_dependency_graph`, `semantic_conventions`).
   c. Populate per-task `artifact_types_addressed` from target file
      patterns (extension-based heuristic) or manifest artifact-type
      mappings. EMIT MUST emit a WARNING when `artifact_types_addressed`
      is empty for any task.
   d. Extract REFINE suggestions from the plan document appendix
      (structured suggestions with area, severity, rationale,
      validation approach) into the seed's per-task or global
      `refine_suggestions` field.
   **Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Failure 3, Gaps 1–8
7. When `onboarding-metadata.json` is absent or unreadable, EMIT MUST
   log a WARNING and proceed with empty `onboarding` (graceful
   degradation per Mottainai application rule 3). Silent omission —
   proceeding without `onboarding` and without logging — is a
   violation.

**Acceptance criteria:**
- Every gap becomes a feature (parse coverage = 100%)
- Complexity score is reasonable (not all 0 or all 100)
- Routing matches complexity score (or force_route override)
- Seed `onboarding` section is populated when `onboarding-metadata.json`
  is present in the export output directory
- Per-task `artifact_types_addressed` is non-empty when target file
  patterns allow type inference
- REFINE suggestions from the plan document appendix appear in the seed
- Absent `onboarding-metadata.json` produces a WARNING log entry (not
  silent omission)

---

#### REQ-PCG-027: Artisan Workflow Contract Compliance (Stage 6)

**Priority:** P1
**Source:** [4] A2A Communications Design §8 (Artisan 7-Phase Workflow)

When routed to Artisan, the contractor MUST execute 7 phases with contract
enforcement at every transition.

**Requirements:**

1. PLAN MUST deconstruct the artifact manifest into tasks with
   `architectural_context`.
2. SCAFFOLD MUST use `output_path`/`output_ext` from onboarding metadata.
3. DESIGN MUST assign depth tiers (brief/standard/comprehensive) based
   on estimated LOC and `design_calibration_hints`. DESIGN MUST consume
   `service_metadata` from onboarding metadata (see REQ-PCG-024
   requirement 7) to correctly classify each service's transport protocol,
   health check type, and schema contracts.
4. IMPLEMENT MUST use `parameter_sources` and `resolved_artifact_parameters`
   from onboarding metadata. IMPLEMENT MUST resolve all parameterized
   values (e.g., base image digests, version pins) — leaving placeholder
   or template strings in generated artifacts is a gate failure.
5. TEST MUST validate generated artifacts against `expected_output_contracts`.
   In addition to external tool validators (linters, type checkers), TEST
   MUST perform **self-consistency validation** across the artisan's own
   outputs:
   a. **Dependency consistency** — every import statement in generated
      source files MUST have a corresponding entry in the dependency
      manifest (`requirements.in`, `go.mod`, `package.json`, etc.).
      This is a static text cross-reference that requires no external
      execution environment.
   b. **Protocol fidelity** — generated client code and Dockerfile
      health checks MUST use the transport protocol declared in
      `service_metadata` (see REQ-PCG-024 requirement 7). A gRPC client
      against an HTTP service, or an HTTP health probe against a gRPC
      service, is a TEST failure.
   c. **Schema field validation** — when input context includes schema
      contracts (`.proto` files, OpenAPI specs, JSON Schema), generated
      code that references schema-defined fields MUST use the field names
      as declared in the schema. Singular/plural mismatches, camelCase
      vs snake_case divergences, and misspellings are TEST failures.
   d. **Placeholder detection** — all generated files MUST be scanned for
      unresolved placeholder patterns (`REPLACE_WITH_*`, `TODO:`,
      `FIXME:`, `PLACEHOLDER`, `xxx`, `<INSERT_*>`). Any match is a
      TEST failure.
   e. **Dockerfile/service coherence** — Dockerfile `HEALTHCHECK` type
      MUST match the service's transport protocol. Base image references
      MUST contain valid, resolvable digests or tags — not placeholder
      strings.
6. REVIEW MUST use multi-agent review via tiered cost model
   (drafter/validator/reviewer).
7. FINALIZE MUST produce per-artifact SHA-256, status rollup, and cost
   aggregation.
8. DESIGN MUST adopt prior valid designs instead of regenerating them
   (implements Mottainai application rule 2: "Forward, don't
   regenerate"). The DESIGN status check MUST accept both `"designed"`
   (fresh generation) and `"adopted"` (reused from a prior run) as
   valid statuses indicating a usable design document exists. See
   AR-122 for artisan-level implementation detail of the three-way
   branch.
   **Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Failure 2
9. DESIGN MUST consume onboarding enrichment fields when present in the
   context seed. For fields already covered by artisan requirements
   (`parameter_sources` per AR-303–305, `semantic_conventions` per
   AR-306, `output_conventions` per AR-307, `calibration_hints` per
   AR-308, `coverage_gaps` per AR-311), this requirement mandates the
   same governance for both artisan and prime routes. Additionally,
   DESIGN MUST consume fields NOT covered by any AR:
   - `derivation_rules` as deterministic constraints (values MUST NOT
     be re-derived by LLM when deterministic rules are present)
   - `open_questions` injected into the DESIGN prompt as flagged
     uncertainties
   - `expected_output_contracts` to inform depth tier assignment
   - REFINE suggestions as advisory constraints in the DESIGN prompt
   - TRANSFORM plan document architecture and risk register sections
     when available in the seed
   When any of these fields are absent, DESIGN MUST fall back to LLM
   inference with a logged WARNING per absent field.
   **Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Gaps 1–8
10. IMPLEMENT MUST reuse existing generated artifacts on retry rather
    than regenerating them. When target files exist on disk, are
    non-empty, and match a prior generation's checksum (if available),
    IMPLEMENT MUST skip generation for those files and proceed to the
    next phase. See AR-134 for artisan-level resume mechanics.
    **Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Gap 14

**Acceptance criteria:**
- Task count matches gap count
- Generated artifacts pass schema validation
- Generated artifacts pass self-consistency validation (5a–5e)
- Finalize report includes checksums for all generated artifacts
- No generated artifact contains placeholder/template strings
- Prior valid designs with status `"adopted"` are reused without
  regeneration
- Onboarding enrichment fields present in the seed reach the DESIGN
  prompt; absent fields produce logged warnings
- Deterministic fields (`derivation_rules`, `resolved_artifact_parameters`)
  take precedence over LLM-derived equivalents when both are available
- Retry runs skip generation for existing non-empty target files

---

### 2.7 Observability Requirements

---

#### REQ-PCG-028: A2A Governance Dashboard

**Priority:** P2
**Status:** Implemented -- `k8s/observability/dashboards/a2a-governance.json`

The pipeline MUST have a Grafana dashboard with panels for governance
visibility.

**Requirements:**

1. The dashboard MUST include panels for:
   - Blocked Span Hotspot (which phases block most often)
   - Gate Failures (which gates fail and severity)
   - Blocked Spans -- Reason & Next Action
   - Finalize Outcomes (success vs fail rate)
   - Handoff Validation Failures
   - Dropped Artifacts (gap parity violations)
   - Finalize Failure Trend
   - Boundary Enforcement Errors
2. Pre-built TraceQL queries MUST be available for: blocked span hotspot,
   gate failure rate, gate results by phase, finalize outcomes, and
   trace-by-id lookup.
3. Pre-built LogQL queries MUST be available for: handoff validation
   failures, dropped artifacts, finalize failure trend, and boundary
   enforcement errors.

**Acceptance criteria:**
- Dashboard is provisioned with all 8 panels
- Queries return results when governance events are present

---

#### REQ-PCG-029: Context Propagation Dashboard

**Priority:** P2

The pipeline MUST have dashboard panels for context propagation health.

**Requirements:**

1. Propagation Completeness stat panel: `{ name = "context.propagation_summary" } | select(span.context.completeness_pct)`
2. Broken Chains Over Time time series: `{ name =~ "context.chain.*" && span.context.chain_status != "intact" } | rate()`
3. Chain Health by Pipeline Run table: total chains, intact, degraded, broken, completeness_pct
4. Enrichment Defaults Applied logs panel: `{ name = "context.boundary.enrichment" && span.context.propagation_status = "defaulted" }`

**Acceptance criteria:**
- All 4 panels render with data from a contract-validated pipeline run

---

## Part 3: Cross-Cutting Requirements

These requirements span both halves of the pipeline.

---

#### REQ-PCG-030: Use Contracts for Boundary Decisions, Events for Diagnostics

**Priority:** P1

The pipeline MUST distinguish between contract objects and span events.

**Requirements:**

1. Use a **contract object** when data must be consumed by another
   agent/system, validated at a boundary, used for routing/blocking
   decisions, or audited later.
2. Use a **span event** when data is local diagnostic detail,
   non-routing commentary, or ephemeral debug context.
3. Contract objects MUST use typed fields (not prose). Text is supporting
   context; fields are authoritative.

**Acceptance criteria:**
- Every boundary decision is governed by a contract object
- Diagnostic details are emitted as span events without contract validation

---

#### REQ-PCG-033: Pipeline Resumption (Scoped)

**Priority:** P1 (contractor resume), P2 (pipeline-level)
**Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Failure 1; commit `21548e4`
**Cross-ref:** AR-134 (artisan resume), AR-500–511 (artisan recovery)

Resumption requirements are scoped differently for each pipeline half.

**Requirements:**

1. **ContextCore half (stages 0–4):** Checkpoint-based pipeline
   resumption is a non-goal. The sequential pipeline has no resume
   mechanism; any mid-pipeline failure requires a full re-run from
   Stage 0. NFR-CDP-002 (idempotent re-runs) mitigates wasted work by
   ensuring repeated execution is safe. See Extension Concern 10
   (Checkpoint Recovery) for the deferred design.
2. **startd8-sdk half (stages 5–7):** Contractor-level resume MUST be
   supported:
   a. `--retry-incomplete` MUST detect complete tasks from both per-task
      result files AND batch result files (e.g., `workflow-result.json`
      without task-ID suffix). Detection MUST NOT rely on a single file
      naming convention.
   b. Previously generated artifacts (source files, design documents,
      state files) MUST be preserved across retry invocations and
      reusable without regeneration.
   c. State files (e.g., `.prime_contractor_state.json`,
      `.startd8/state/review_results.json`) MUST persist across retry
      invocations and MUST be consulted before re-queuing tasks.
   d. Skip/retry decisions MUST be logged with cost attribution
      (estimated cost saved by skip, estimated cost of regeneration).
   See AR-134 and AR-500–511 for artisan-level recovery mechanics.
3. The distinction between pipeline-level non-goal (requirement 1) and
   contractor-level requirement (requirement 2) MUST be documented in
   operator guides to prevent confusion about what `--retry-incomplete`
   does versus re-running the full pipeline.

**Acceptance criteria:**
- `--retry-incomplete` correctly identifies completed tasks from both
  per-task and batch result files
- Previously generated artifacts are preserved and reused on retry
- Skip/retry decisions appear in structured logs with cost attribution
- Operator guide documents the two-tier resumption model

---

#### REQ-PCG-034: Generic Failure Injection

**Priority:** P2

The pipeline MUST support a generic failure injection mechanism for all
contract types and gates, not just checksums.

**Requirements:**

1. Failure injection MUST be available for propagation contracts (inject
   DEGRADED/BROKEN status), schema compatibility (inject mismatch),
   causal ordering (inject out-of-order), and all three gates.
2. Injection MUST be via CLI flags or configuration, not code
   modification.
3. Injection MUST be auditable — injected failures MUST be
   distinguishable from real failures in OTel events and gate results.

**Acceptance criteria:**
- `a2a-pilot` supports injection of propagation failures in addition to
  existing checksum injection
- Injected failures trigger the correct alerts and dashboard panels

---

#### REQ-PCG-035: Schema Versioning Strategy (Placeholder)

**Priority:** P2
**Status:** Deferred to Phase 2

Contract schemas MUST support at minimum N and N-1 versions during
rolling deployments. The versioning and migration strategy (version
negotiation, dual-version acceptance windows, migration tooling) is
deferred to Phase 2 design.

**Requirements (Phase 2):**

1. The contract loader MUST accept both the current and previous schema
   version during a migration window.
2. Version mismatches at the handoff boundary MUST produce actionable
   errors referencing the upgrade path.
3. Breaking schema changes MUST increment `schema_version` and provide
   a migration guide.

---

**Cross-cutting note (R2-S5):** Malformed `run-provenance.json` MUST
produce a warning (not silently ignored) to align with REQ-PCG-023's
Fail Loud principle. Silent ignoring contradicts the chain-of-custody
assurance the governance system is designed to protect.

---

### 3.2 Artifact Reuse Requirements (Mottainai Principle)

The following requirements codify the [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md)
into verifiable governance contracts. The principle: **every artifact
produced by an earlier stage carries invested computation, context, and
deterministic correctness — discarding it or regenerating it via an
expensive LLM call when it could be passed forward is mottainai.**

For artisan-specific implementation detail, see the
[Artisan Contractor Requirements](startd8-sdk: docs/ARTISAN_REQUIREMENTS.md)
AR-3xx (ContextCore Data Flow) and AR-1xx/5xx (workflow/recovery).
Requirements below reference AR-xxx where overlap exists and add
governance for aspects not covered by any AR.

---

#### REQ-PCG-036: Onboarding Enrichment End-to-End Propagation

**Priority:** P1
**Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Gaps 1–8, Failure 3
**Cross-ref:** AR-303–308 implement artisan-side consumption for 5 of 7 fields

The 7 onboarding enrichment fields produced by ContextCore export MUST
propagate end-to-end from export through plan-ingestion to contractor
DESIGN/IMPLEMENT phases.

**Requirements:**

1. The following 7 enrichment fields MUST propagate end-to-end when
   present in `onboarding-metadata.json`:
   - `derivation_rules` — deterministic business-to-parameter mappings
   - `resolved_artifact_parameters` — pre-resolved parameter values
   - `expected_output_contracts` — per-artifact-type output contracts
   - `design_calibration_hints` — per-artifact-type depth/complexity hints
   - `open_questions` — unresolved questions from the manifest
   - `artifact_dependency_graph` — deterministic artifact dependency ordering
   - `semantic_conventions` — attribute naming standards per artifact type
2. Propagation path for each field:

   | Field | Source | Carrier | Consumer | AR Cross-ref |
   |-------|--------|---------|----------|-------------|
   | `parameter_sources` | export | seed `onboarding` | DESIGN/IMPLEMENT | AR-303–305 |
   | `semantic_conventions` | export | seed `onboarding` | DESIGN | AR-306 |
   | `output_conventions` | export | seed `onboarding` | DESIGN/TEST | AR-307 |
   | `design_calibration_hints` | export | seed `onboarding` | DESIGN | AR-308 |
   | `coverage_gaps` | export | seed `onboarding` | PARSE/DESIGN | AR-311 |
   | `derivation_rules` | export | seed `onboarding` | DESIGN | — (governance only) |
   | `resolved_artifact_parameters` | export | seed `onboarding` | DESIGN/IMPLEMENT | — (governance only) |
   | `expected_output_contracts` | export | seed `onboarding` | DESIGN/TEST | — (governance only) |
   | `open_questions` | export | seed `onboarding` | DESIGN | — (governance only) |
   | `artifact_dependency_graph` | export | seed `onboarding` | PLAN/IMPLEMENT | — (governance only) |

3. **Gap logging:** When a field is present at the source
   (`onboarding-metadata.json`) but absent at the consumer (DESIGN
   context), a structured WARNING MUST be emitted with: field name,
   source file path, consumer phase, and reason for absence. Prose-only
   logging is insufficient — the warning MUST be machine-parseable.
4. **Deterministic precedence:** Deterministic fields
   (`derivation_rules`, `resolved_artifact_parameters`,
   `artifact_dependency_graph`) MUST take precedence over LLM-derived
   equivalents when both are available. The LLM-derived value MAY be
   logged for comparison but MUST NOT override the deterministic value.
5. **Per-task `artifact_types_addressed`:** EMIT (REQ-PCG-026
   requirement 6c) MUST populate this field for each task. DESIGN MUST
   use `artifact_types_addressed` to select matching enrichment fields
   per artifact type.
6. **REFINE suggestion forwarding:** REFINE suggestions extracted during
   plan-ingestion (REQ-PCG-026 requirement 6d) MUST be available in the
   seed and forwarded to the DESIGN prompt as advisory constraints.
7. **TRANSFORM plan document accessibility:** When the TRANSFORM phase
   produces a structured plan document with architecture, risk register,
   and verification strategy sections, these MUST be accessible to
   DESIGN (via the seed or a sidecar reference). DESIGN MUST NOT be
   required to re-derive architecture and risk analysis from scratch.

**Acceptance criteria:**
- Pipeline run with enrichment produces a seed with populated
  `onboarding` section containing all 7 fields
- DESIGN prompts include deterministic fields when present in seed
- Gap logging fires when enrichment is present at source but absent at
  consumer
- Deterministic fields override LLM-derived values
- Per-task `artifact_types_addressed` is populated for tasks with
  inferable artifact types
- REFINE suggestions appear in DESIGN prompt when present in seed

---

#### REQ-PCG-037: Contractor Resume and Artifact Preservation

**Priority:** P1
**Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Failures 1–2, Gap 14
**Cross-ref:** AR-122 (adopt prior, artisan), AR-134 (resume, artisan), AR-500–511 (recovery)

Contractor execution MUST preserve and reuse artifacts across retries
to avoid wasteful regeneration.

**Requirements:**

1. **Multi-format task completion detection:** `--retry-incomplete`
   MUST detect completed tasks from per-task result files (e.g.,
   `workflow-result-{task_id}.json`), batch result files (e.g.,
   `workflow-result.json`), and state files (e.g.,
   `.startd8/state/review_results.json`). Detection MUST NOT rely on a
   single file naming convention. This requirement has no AR-xxx
   overlap — it governs both artisan and prime routes at the
   orchestration level.
2. **Design three-way branch with "adopted" acceptance:** The DESIGN
   phase MUST implement a three-way branch: (a) no prior design →
   generate fresh, (b) prior design with status `"designed"` → adopt,
   (c) prior design with status `"adopted"` → adopt. Status `"adopted"`
   MUST be accepted as equivalent to `"designed"` for adoption purposes.
   See AR-122 for artisan-level three-way branch implementation. This
   governance requirement applies to both artisan and prime routes.
3. **Generated file preservation and reuse on retry:** When target files
   exist on disk from a prior generation run, are non-empty, and have
   valid content (verified by checksum when available), they MUST be
   reused rather than regenerated. See AR-134 for artisan-level resume
   mechanics.
4. **Prime contractor generation result caching:** The prime workflow
   MUST check `FeatureSpec.generated_files` before calling the code
   generator. If generated files exist on disk and are non-empty,
   generation MUST be skipped and the workflow MUST proceed to
   integration. This requirement has no AR-xxx overlap — it is
   prime-specific.
5. **Cost attribution by category:** Each skip/adopt/regenerate
   decision MUST be logged with cost attribution:
   - `skip`: estimated cost saved (based on prior generation cost or
     task complexity estimate)
   - `adopt`: $0 generation cost, design reuse noted
   - `regenerate`: actual generation cost
   This requirement has no AR-xxx overlap.
6. **Structured logging of all skip/adopt decisions:** Every task
   processed by `--retry-incomplete` MUST produce a structured log
   entry with: task ID, decision (skip/adopt/regenerate), reason,
   source file(s) consulted, and estimated cost impact.

**Acceptance criteria:**
- `--retry-incomplete` identifies completed tasks from per-task, batch,
  and state files
- Adopted designs (status `"adopted"`) are reused without regeneration
- Generated files from prior runs are preserved and reused on retry
- Prime workflow skips generation when `generated_files` exist on disk
- Cost report categorizes decisions as skip/adopt/regenerate with cost
  attribution
- Structured logs contain task ID, decision, reason, and cost impact
  for every retry task

---

#### REQ-PCG-038: Prime Contractor Context Parity

**Priority:** P2
**Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Gaps 9–13
**Cross-ref:** None (no AR-xxx coverage for the prime route)

The prime contractor route MUST have access to the same enrichment
context as the artisan route, adapted for the prime workflow's
architecture.

**Requirements:**

1. **FeatureSpec metadata field:** `FeatureSpec` MUST include an
   optional `metadata: Dict[str, Any]` field.
   `FeatureQueue.add_features_from_seed()` MUST forward per-task
   `_enrichment` blocks from the seed into `metadata`. `_generate_code()`
   MUST check `feature.metadata.get("_enrichment")` before falling back
   to runtime enrichment (e.g., `DomainChecklist._get_domain_enrichment()`).
2. **Onboarding injection into code generation context:** The prime
   workflow MUST load the seed's `onboarding` section and forward
   relevant fields (`derivation_rules`, `resolved_artifact_parameters`,
   `semantic_conventions`) into the `LeadContractorCodeGenerator`
   context so they reach the code generation prompt.
3. **Lightweight architectural context:** Plan-ingestion MUST compute a
   lightweight architectural summary for prime seeds containing at
   minimum: project goals and mentioned files from the parsed plan.
   This is deterministic extraction — no LLM cost.
4. **Per-task token budgets from estimated LOC:** The prime workflow
   MUST compute per-task token budgets from `ParsedFeature.estimated_loc`
   (already available in the seed) rather than using a flat uniform
   limit. This is arithmetic — no LLM cost.
5. **REFINE suggestion forwarding:** REFINE suggestions extracted into
   the seed (REQ-PCG-036 requirement 6) MUST be forwarded to prime code
   generation as advisory constraints.
6. **Domain enrichment reuse from metadata:** The prime workflow MUST
   check `feature.metadata` for pre-computed domain enrichment before
   invoking runtime domain classification. Re-classification MUST only
   occur when metadata is absent or stale.

**Acceptance criteria:**
- `FeatureSpec.metadata` round-trips through `add_features_from_seed()`
  and back
- Prime code generation context includes onboarding enrichment fields
- Architectural summary (goals + mentioned files) is present in prime
  seeds
- Token budgets vary by task based on estimated LOC
- REFINE suggestions reach prime code generation when present
- Domain enrichment from metadata is used before runtime re-classification

---

#### REQ-PCG-039: Source Artifact Type Coverage

**Priority:** P2
**Source:** [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) Gap 15
**Cross-ref:** None (no AR-xxx coverage)

The artifact type registry MUST support source artifact types to enable
export-time enrichment and existing-artifact detection for non-observability
deliverables.

**Requirements:**

1. **Modular artifact type registry:** The `ArtifactType` registry
   MUST support a modular extension mechanism (e.g., `ArtifactTypeModule`
   ABC) that allows drop-in registration of new artifact type families
   without modifying core registry code.
2. **Source type registration:** The following source artifact types
   MUST be registrable: source modules (`.py`, `.go`, `.js`, `.java`,
   `.cs`), Dockerfiles, dependency manifests (`requirements.in`,
   `go.mod`, `package.json`, etc.), and proto contracts (`.proto`).
3. **Export output parity:** Once registered, source artifact types
   MUST receive the same export outputs as observability types:
   `design_calibration_hints`, `expected_output_contracts`, and
   `resolved_artifact_parameters`.
4. **Existing artifact detection:** The pipeline MUST support an
   `ArtifactStatus` signal with at least three states: `EXISTS` (fresh
   file on disk), `STALE` (file exists but is outdated per manifest or
   checksum), and `ABSENT` (no file found). Detection MUST leverage
   existing discovery mechanisms (capability-index
   `_discovery_paths.yaml`, export `scan_existing_artifacts`,
   SCAFFOLD `target_path.exists()`).
5. **Skip-existing task support:** When a task's target files have
   `ArtifactStatus.EXISTS` and the operator has not requested
   regeneration, the contractor MUST support a `skip_existing` mode
   that bypasses generation for those files with an audit trail
   recording: task ID, skipped files, status, and reason.
6. **Detection fragment consolidation:** The four existing detection
   fragments (export `scan_existing_artifacts`, capability-index
   `_discovery_paths.yaml`, artifact inventory, SCAFFOLD
   `target_path.exists()`) MUST be consolidated into a single
   end-to-end signal that flows from discovery through
   `ArtifactStatus` to contractor skip decisions.

**Acceptance criteria:**
- Source artifact types are registered via the modular mechanism
- Registered source types receive calibration hints and output contracts
  at export time
- Existing files are detected with correct `ArtifactStatus`
- `skip_existing` tasks produce an audit trail
- The four detection fragments are consolidated into a single signal
  path

---

#### REQ-PCG-031: OTel Span Event Schema Consistency

**Priority:** P1

All contract enforcement events MUST follow a consistent naming and
attribute schema.

**Requirements:**

1. Boundary events MUST use `context.boundary.{direction}` naming with
   attributes: `context.phase`, `context.direction`, `context.passed`,
   `context.propagation_status`, `context.blocking_count`,
   `context.warning_count`.
2. Chain events MUST use `context.chain.{validated|degraded|broken}` with
   attributes: `context.chain_id`, `context.chain_status`,
   `context.source_present`, `context.destination_present`,
   `context.message`.
3. Summary events MUST use `context.propagation_summary` with attributes:
   `context.total_chains`, `context.intact`, `context.degraded`,
   `context.broken`, `context.completeness_pct`.
4. A2A governance events MUST use the attribute namespaces documented in
   `docs/agent-semantic-conventions.md`.

**Acceptance criteria:**
- All events follow the documented schema
- TraceQL queries from both Layer 1 and A2A designs return expected results

---

#### REQ-PCG-032: Design Calibration Guards

**Priority:** P2

The pipeline MUST validate that design calibration hints match expected
artifact depth.

**Requirements:**

1. `design_calibration_hints` in onboarding metadata MUST cover all
   artifact types with gaps.
2. Calibration MUST use valid depth tiers: `brief`, `standard`,
   `comprehensive`, `standard-comprehensive`.
3. Each calibration hint MUST have `expected_loc_range` and `red_flag`
   descriptions.
4. Cross-check against `expected_output_contracts` MUST be performed if
   present.
5. When generated artifact LOC falls outside the expected range, a warning
   MUST be emitted (non-blocking).
6. When the project generates executable services,
   `design_calibration_hints` MUST include per-service entries that
   reference `service_metadata` (REQ-PCG-024 requirement 7):
   a. Each service hint MUST declare the service's `transport_protocol`
      (sourced from `service_metadata`).
   b. Dockerfile hints MUST specify the expected `healthcheck_type`
      consistent with the service protocol.
   c. Client/test hints MUST specify the expected transport library
      (e.g., `grpc` stubs for gRPC services, `requests`/`urllib` for
      HTTP services).
   d. A mismatch between `design_calibration_hints` and
      `service_metadata` on protocol classification MUST produce a
      warning-severity gate result.

| Artifact Type | Expected Depth | Red Flag |
|---|---|---|
| ServiceMonitor | Brief (<=50 LOC) | Calibrated as "comprehensive" |
| PrometheusRule | Standard (51-150 LOC) | Calibrated as "brief" |
| Dashboard (Grafana JSON) | Comprehensive (>150 LOC) | Calibrated as "brief" |
| SLO Definition | Standard | Calibrated as "comprehensive" |
| Runbook | Standard-Comprehensive | Calibrated as "brief" |
| Dockerfile (gRPC service) | Standard | HEALTHCHECK uses HTTP probe |
| Dockerfile (HTTP service) | Standard | HEALTHCHECK uses gRPC probe |
| Client stub (gRPC service) | Standard | Uses HTTP/REST transport |
| Client stub (HTTP service) | Brief | Uses gRPC transport |

**Acceptance criteria:**
- Miscalibration produces a warning-severity gate result
- Red flags appear in gate evidence
- Protocol mismatch between calibration hints and service_metadata
  produces a warning

---

## Part 4: Extension Concern Requirements (Designed, Not Yet Implemented)

Nine extension concerns have full requirements documents. These extend the
7 core contract domains with specialized correctness properties.

| ID | Extension Concern | Requirements Document | Related Domain |
|---|---|---|---|
| 4E | Temporal Staleness | `REQ_CONCERN_4E_TEMPORAL_STALENESS.md` | Causal Ordering |
| 5E | Delegation Authority | `REQ_CONCERN_5E_DELEGATION_AUTHORITY.md` | Capability Propagation |
| 6E | Multi-Budget Coordination | `REQ_CONCERN_6E_MULTI_BUDGET.md` | SLO Budget |
| 7E | Version Lineage | `REQ_CONCERN_7E_VERSION_LINEAGE.md` | Data Lineage |
| 9 | Quality Propagation | `REQ_CONCERN_9_QUALITY_PROPAGATION.md` | (new domain) |
| 10 | Checkpoint Recovery | `REQ_CONCERN_10_CHECKPOINT_RECOVERY.md` | (new domain) |
| 11 | Config Evolution | `REQ_CONCERN_11_CONFIG_EVOLUTION.md` | (new domain) |
| 12 | Graph Topology | `REQ_CONCERN_12_GRAPH_TOPOLOGY.md` | (new domain) |
| 13 | Evaluation-Gated Propagation | `REQ_CONCERN_13_EVALUATION_GATED_PROPAGATION.md` | (new domain) |

These are out of scope for this document but referenced for completeness.

---

## Non-Functional Requirements

### NFR-PCG-001: Zero Overhead Without Contracts

When `contract_path` is not provided, the contract system MUST add zero
runtime overhead. No contract loading, no validation, no OTel events.

### NFR-PCG-002: Graceful Degradation Without ContextCore

startd8-sdk pipelines MUST function without ContextCore installed. The
**Propagation Contract** validation wrapper MUST return `None` and
existing phase validation MUST still execute. Note: **A2A Contract**
validation (Pydantic models defined in startd8-sdk itself) MUST remain
active regardless of ContextCore availability — these are mandatory
contracts, not degradable ones.

### NFR-PCG-003: Contract System Self-Observability

The contract system MUST be observable through the same infrastructure it
validates. Meta-observability (dashboards showing "85% of chains INTACT,
10% DEGRADED, 5% BROKEN") makes the contract system trustworthy.

### NFR-PCG-004: Verification Expression Safety

Verification expressions in propagation chain specs use `eval()` in a
sandboxed scope (no builtins, only `context`, `source`, `dest` variables).
Contract YAML MUST come from trusted sources (checked into repo alongside
code). If contract YAML ever comes from untrusted sources, the `eval()`
mechanism MUST be replaced with a safe expression evaluator (e.g., CEL —
see R6-S1 for the planned migration path).

**Interim hardening (implemented):** Verification expressions MUST be
validated against an AST allowlist at parse time, before they ever reach
`eval()`:

1. **Maximum expression length**: 500 characters.
2. **Prohibited AST nodes**: `Import`, `ImportFrom`, `JoinedStr`
   (f-strings — prevents sensitive value exfiltration per R5-S5).
3. **Allowed function calls**: Only allowlisted builtins (`len`, `str`,
   `int`, `float`, `bool`, `isinstance`) and method calls on allowed
   variables (`context`, `source`, `dest`) one level deep (e.g.,
   `context.get("field", "")` is allowed; `context.get("x").strip()`
   is rejected because `.strip()` is called on a return value, not an
   allowed variable).
4. **Attribute access**: Only on allowed variables, one level deep.
   Deep chains (e.g., `context.__class__.__bases__`) are rejected.
5. **Execution timeout**: 1-second `signal.alarm` timeout (Unix only).
   Timeout produces BROKEN chain status with message "Verification
   expression timed out after 1 second". Timeout behavior is
   deterministic per NFR-PCG-005.
6. **Validation errors**: Malicious or malformed expressions are
   rejected at Pydantic parse time via `@field_validator("verification")`
   on `PropagationChainSpec`, producing a structured `ValueError`.

This AST allowlist is interim hardening. The long-term plan is CEL
migration (R6-S1) for cross-language portability and stronger security.

### NFR-PCG-005: Idempotent Gate Execution

Running any gate check multiple times with the same input MUST produce
the same result. Gates MUST NOT have side effects beyond OTel event emission.

---

## Implementation Status Matrix

### Contract Domains x Lifecycle Stages

Cells marked **Y** are fully integrated; **Y\*** = domain logic +
lifecycle wiring implemented, end-to-end integration pending validation
(Phase 2); **--** = not applicable.

|                         | Pre-Flight | Runtime | Post-Exec | Observability | Regression |
|-------------------------|:----------:|:-------:|:---------:|:-------------:|:----------:|
| Context Propagation     | Y          | Y       | Y         | Y             | Y          |
| Schema Compatibility    | Y          | Y       | Y         | Y             | Y          |
| Semantic Conventions    | Y*         | Y*      | Y*        | Y*            | Y*         |
| Causal Ordering         | Y*         | Y*      | Y*        | Y*            | Y*         |
| Capability Propagation  | Y*         | Y*      | Y*        | Y*            | Y*         |
| SLO Budget Tracking     | Y*         | Y*      | Y*        | Y*            | Y*         |
| Data Lineage            | Y*         | Y*      | Y*        | Y*            | Y*         |

### Promotion Criteria (D → Y → Y*)

To promote a domain from **Y\*** to **Y** (fully validated), the
following must hold for each lifecycle stage:

1. An end-to-end integration test exercises the domain's enforcement
   through the specific lifecycle stage (preflight, runtime, postexec).
2. The test produces verifiable OTel span events matching the documented
   attribute schema (REQ-PCG-031).
3. The test passes in CI without mocks for the domain-specific validation
   logic.

Phase 2 will execute these integration tests for domains 3–7.

### Requirement-to-Domain Traceability

Lifecycle requirements REQ-PCG-008/009/010 apply across all 7 domains:

| Requirement | Lifecycle | Domains (Y) | Domains (Y*) |
|-------------|-----------|-------------|--------------|
| REQ-PCG-008 (Pre-Flight) | Pre-Flight | Propagation, Schema Compat | SemConv, Ordering, Capability, Budget, Lineage |
| REQ-PCG-009 (Runtime) | Runtime | Propagation, Schema Compat | SemConv, Ordering, Capability, Budget, Lineage |
| REQ-PCG-010 (Post-Exec) | Post-Exec | Propagation, Schema Compat | SemConv, Ordering, Capability, Budget, Lineage |

### A2A Governance

| Component | Status | Tests |
|---|---|---|
| Pydantic models + JSON schema validation | Implemented | 50 |
| Boundary enforcement | Implemented | (in above) |
| PI-101-002 pilot runner | Implemented | 21 |
| TraceQL/LogQL queries | Implemented | 24 |
| Pipeline integrity checker (Gate 1) | Implemented | 34 |
| Three Questions diagnostic (Gate 2) | Implemented | 25 |
| Finalize verification (Gate 3) | Partial | see `context_seed_handlers.py` |
| **Total** | | **154+** |

---

## Verification Plan

| Req | Verification Method |
|-----|-------------------|
| REQ-PCG-001 | 62 tests in `contracts/propagation/` |
| REQ-PCG-002 | ~68 tests in `contracts/schema_compat/` |
| REQ-PCG-003 | 20 tests in `contracts/semconv/` |
| REQ-PCG-004 | 22 tests in `contracts/ordering/` |
| REQ-PCG-005 | 18 tests in `contracts/capability/` |
| REQ-PCG-006 | 19 tests in `contracts/budget/` |
| REQ-PCG-007 | 21 tests in `contracts/lineage/` |
| REQ-PCG-008 | 26 tests in `contracts/preflight/` |
| REQ-PCG-009 | 30 tests in `contracts/runtime/` |
| REQ-PCG-010 | 30 tests in `contracts/postexec/` |
| REQ-PCG-011 | TraceQL queries return results; dashboard panels render |
| REQ-PCG-012 | Tests in `contracts/regression/` |
| REQ-PCG-013 | Unit tests: each severity produces documented side effects |
| REQ-PCG-014 | Unit tests: provenance survives phase transitions, hash mismatch detected |
| REQ-PCG-015 | Contract YAML parsing with `extra="forbid"` rejects unknown keys |
| REQ-PCG-016 | Pipeline without `contract_path` has no overhead |
| REQ-PCG-017 | 50 tests in `test_a2a_contracts.py` |
| REQ-PCG-018 | Boundary enforcement emits failure events |
| REQ-PCG-019 | `a2a-pilot --source-checksum sha256:BAD` fails |
| REQ-PCG-020 | 34 tests in `test_pipeline_checker.py` |
| REQ-PCG-021 | 25 tests in `test_three_questions.py` |
| REQ-PCG-022 | Partial -- Gate 3 validation exists in startd8-sdk `context_seed_handlers.py` for multi-file split completeness; standalone Gate 3 test suite pending |
| REQ-PCG-023 | Gate failures include `next_action` field |
| REQ-PCG-024 | Gate 1 passes on well-formed handoff, fails on stale/missing artifacts |
| REQ-PCG-025 | Cross-boundary chain produces INTACT/DEGRADED/BROKEN status |
| REQ-PCG-026 | Parse coverage = 100%, routing matches score |
| REQ-PCG-027 | Finalize report includes checksums; task count matches gap count |
| REQ-PCG-028 | Dashboard provisioned with all 8 panels |
| REQ-PCG-029 | Dashboard panels render with contract validation data |
| REQ-PCG-030 | Boundary decisions use contracts; diagnostics use events |
| REQ-PCG-031 | TraceQL queries return expected attributes |
| REQ-PCG-032 | Miscalibration produces warning gate result |
| REQ-PCG-033 | Retry test: `--retry-incomplete` identifies incomplete tasks from both batch and per-task result files; previously generated artifacts preserved; cost attribution in structured logs |
| REQ-PCG-036 | Integration test: pipeline with enrichment produces populated seed `onboarding`; DESIGN prompts include deterministic fields; gap logging fires when enrichment present at source but absent at consumer; AR-303–308 tests cover artisan consumption |
| REQ-PCG-037 | Retry test: adopted designs (status `"adopted"`) reused without regeneration; generated files preserved across retries; cost report categorizes skip/adopt/regenerate decisions |
| REQ-PCG-038 | Unit test: `FeatureSpec.metadata` round-trips through `add_features_from_seed()`; prime code generation context includes onboarding enrichment; token budgets vary by estimated LOC |
| REQ-PCG-039 | Integration test: source artifact types registered via modular mechanism; existing files detected with `ArtifactStatus`; `skip_existing` tasks produce audit trail |

---

## References

### Source Documents (Consolidated Here)

1. [Context Correctness by Construction](../CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) -- theoretical foundation, 7-layer architecture, 8 cross-cutting concerns
2. [ContextCore Context Contracts](../ContextCore-context-contracts.md) -- defense-in-depth layers, dual-declaration architecture
3. [Context Propagation Contracts Design](../CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) -- Layer 1 specification (contract format, validation, provenance, OTel events)
4. [A2A Communications Design](../contextcore-a2a-comms-design.md) -- A2A governance (contract types, gates, defense-in-depth, extensions)
5. [A2A Contracts Design](../A2A_CONTRACTS_DESIGN.md) -- conceptual design for 4 contract types

### Companion Documents

- [REQ_CAPABILITY_DELIVERY_PIPELINE.md](REQ_CAPABILITY_DELIVERY_PIPELINE.md) -- pipeline orchestration mechanics (stages 0-7)
- [Export Pipeline Analysis Guide](../../guides/EXPORT_PIPELINE_ANALYSIS_GUIDE.md) -- operational reference
- [Semantic Conventions](../../semantic-conventions.md) -- attribute naming standards
- [Agent Communication Protocol](../../agent-communication-protocol.md) -- OTel-level agent protocols
- [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) -- artifact reuse principle, violation inventory, application rules
- [Artisan Contractor Requirements](startd8-sdk: docs/ARTISAN_REQUIREMENTS.md) -- AR-xxx implementation requirements (Layer 3: ContextCore Data Flow implements artisan-side enrichment consumption)

### Computer Science Theory

- Milner (1978) -- type soundness ("well-typed programs don't go wrong")
- Denning (1976) -- information flow as lattice properties
- Dennis & Van Horn (1966) -- capability-based security
- Lamport (1978) -- causal ordering in distributed systems
- Buneman et al. (2001) -- provenance theory for databases
- Honda et al. (2008) -- multiparty asynchronous session types

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

- **ambiguity**: 11 suggestions applied (R13-S5, R1-S4, R2-S3, R3-S1, R3-S6, R4-S2, R5-S6, R7-S5, R9-S5, R11-S8, R12-S7)
- **completeness**: 22 suggestions applied (R13-S2, R14-S2, R15-S1, R15-S2, R15-S3, R15-S4, R15-S5, R15-S6, R15-S7, R15-S8, R1-S2, R1-S3, R1-S8, R5-S3, R5-S9, R6-S5, R7-S3, R7-S9, R8-S4, R9-S3, R10-S4, R11-S6)
- **consistency**: 25 suggestions applied (R13-S1, R13-S6, R1-S1, R1-S6, R1-S10, R2-S1, R2-S5, R2-S8, R4-S7, R5-S1, R5-S5, R6-S3, R7-S1, R7-S6, R8-S5, R9-S1, R9-S6, R9-S10, R10-S2, R10-S5, R11-S1, R11-S5, R12-S1, R12-S3, R12-S4)
- **feasibility**: 22 suggestions applied (R13-S3, R14-S1, R14-S4, R14-S5, R2-S2, R3-S2, R3-S3, R3-S7, R4-S1, R5-S2, R5-S8, R6-S1, R6-S4, R7-S2, R7-S8, R8-S7, R8-S8, R9-S2, R9-S8, R10-S1, R12-S5, R12-S6)
- **testability**: 15 suggestions applied (R13-S4, R13-S10, R1-S5, R2-S4, R3-S4, R3-S8, R3-S10, R4-S8, R5-S4, R6-S6, R7-S4, R7-S10, R9-S4, R11-S4, R11-S10)
- **traceability**: 8 suggestions applied (R13-S9, R1-S7, R2-S9, R3-S5, R4-S3, R4-S6, R4-S9, R8-S6)
- **unknown**: 19 suggestions applied (R1-S9, R3-S9, R5-S7, R1-F1, R1-F2, R1-F3, R1-F5, R1-F6, R7-S7, R3-F1, R3-F2, R3-F3, R3-F4, R4-F1, R4-F2, R4-F3, R4-F4, R4-F5, R13-S9)

### Areas Needing Further Review

All areas have reached the substantially addressed threshold.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Reconcile the inconsistent Gate 1 check count between REQ-PCG-020 (7 checks) and REQ-CDP-011 (6 checks). | claude-4 (claude-opus-4-6) | A critical consistency issue: downstream implementers and test authors need a single authoritative count. The discrepancy between the two companion documents will cause confusion and potentially divergent test suites. | 2026-02-19 17:46:51 UTC |
| R1-S2 | Add an explicit implementation status marker and test count to REQ-PCG-022 (Gate 3), which is missing unlike Gates 1 and 2. | claude-4 (claude-opus-4-6) | Every other gate requirement includes status and test counts. The omission makes it unclear whether Gate 3 is implemented, planned, or partially done, which directly affects the Implementation Status Matrix's accuracy and project planning. | 2026-02-19 17:46:51 UTC |
| R1-S3 | Add a requirement or explicit non-goal for checkpoint-based pipeline resumption when intermediate stages fail. | claude-4 (claude-opus-4-6) | The sequential pipeline (stages 0-4) has no resume mechanism, meaning any mid-pipeline failure requires a full re-run. Given that Concern 10 (Checkpoint Recovery) is out-of-scope for extensions, the core pipeline should at minimum declare this as an explicit non-goal with rationale, so stakeholders understand the tradeoff. | 2026-02-19 17:46:51 UTC |
| R1-S4 | Fix the typo in REQ-PCG-008 requirement 3 ('byppassable') and specify the exact bypass mechanism for pre-flight validation. | claude-4 (claude-opus-4-6) | The typo undermines document precision, and the lack of a specified bypass mechanism (flag, config setting, or environment variable) creates ambiguity for implementers. The companion document defines specific bypass flags for other stages, so pre-flight should be equally precise. | 2026-02-19 17:46:51 UTC |
| R1-S5 | Add specific test names or minimum test counts to the Verification Plan entries for REQ-PCG-008 through REQ-PCG-010. | claude-4 (claude-opus-4-6) | These three entries reference only directory paths without test counts, unlike all other domain requirements (REQ-PCG-001 through REQ-PCG-007) which include counts. A directory reference alone is insufficient for coverage verification in CI — the directory could be empty. | 2026-02-19 17:46:51 UTC |
| R1-S6 | Add a parse-time allowlist constraint for verification expressions in NFR-PCG-004 to enforce defense-in-depth against injection. | claude-4 (claude-opus-4-6) | Relying solely on trusted-source assumptions contradicts the document's own defense-in-depth philosophy. A parse-time allowlist of safe operations would catch malicious expressions before they reach the eval sandbox, providing a meaningful additional security layer at low implementation cost. | 2026-02-19 17:46:51 UTC |
| R1-S7 | Add promotion criteria for the 5 contract domains currently at status 'D' in the Implementation Status Matrix. | claude-4 (claude-opus-4-6) | Without defined criteria for promoting from 'D' (domain logic implemented) to 'Y' (fully integrated), the matrix is a static snapshot with no actionable tracking value. Stakeholders cannot assess progress or plan lifecycle wiring work. | 2026-02-19 17:46:51 UTC |
| R1-S8 | Annotate onboarding metadata fields in REQ-PCG-024 as REQUIRED or OPTIONAL to clarify Gate 1 behavior. | claude-4 (claude-opus-4-6) | Gate 1 checks 'structural integrity (required fields)' but the required-field set is undefined. Without REQUIRED/OPTIONAL annotations, implementers cannot determine which missing fields should cause gate failure versus a warning, leading to ambiguous gate behavior and test design. | 2026-02-19 17:46:51 UTC |
| R1-S9 | Add a gap exclusion declaration mechanism to REQ-PCG-026 so that intentionally skipped gaps don't cause false Gate 2 failures. | claude-4 (claude-opus-4-6) | The '100% parse coverage' acceptance criterion with no exclusion mechanism is impractical. The pipeline already supports selective execution via --task-filter, but the parse stage has no corresponding filter. An exclusion declaration with audit trail balances completeness with operational flexibility. | 2026-02-19 17:46:51 UTC |
| R1-S10 | Define a schema versioning and migration strategy for when breaking changes require moving beyond schema_version 'v1'. | claude-4 (claude-opus-4-6) | REQ-PCG-017 mandates schema_version='v1' with no versioning strategy. The first breaking schema change will either require a coordinated flag day across ContextCore and startd8-sdk or produce silent validation failures. This is a foreseeable and critical gap for long-term maintainability. | 2026-02-19 17:46:51 UTC |
| R2-S1 | Clarify Gate 3's command and relationship to a2a-diagnose, which is currently associated with Gate 2 in REQ-PCG-021. | gemini-2.5 (gemini-2.5-pro) | REQ-CDP-011 specifies a2a-diagnose for Gate 3, but REQ-PCG-021 defines it as the Gate 2 diagnostic tool. This creates genuine confusion about whether Gate 3 reuses the same tool (running only Q3) or has its own command. Operators and script implementers need clarity. | 2026-02-19 17:46:51 UTC |
| R2-S2 | Define the runtime environment and dependency management strategy for the E2E orchestration script that spans both ContextCore and startd8-sdk. | gemini-2.5 (gemini-2.5-pro) | The E2E script lives in ContextCore but requires startd8-sdk, creating tight coupling and potential dependency conflicts. A specified environment strategy (containerization, venv, etc.) is necessary for reproducible execution and CI reliability. | 2026-02-19 17:46:51 UTC |
| R2-S3 | Explicitly define the complete set of artifacts that constitute the handoff contract consumed by stages 5-7. | gemini-2.5 (gemini-2.5-pro) | REQ-PCG-024 lists three key files but the directory listing shows many more. An incomplete contract definition risks downstream stage failures on missing inputs. A definitive list or glob pattern is needed for Gate 1 to reliably verify completeness. | 2026-02-19 17:46:51 UTC |
| R2-S4 | Add a requirement for a generic failure injection mechanism to test all major contract types and gates, not just checksums. | gemini-2.5 (gemini-2.5-pro) | REQ-PCG-019 only specifies failure injection for checksums. Without a broader mechanism, testing observability and alerting requirements (REQ-PCG-011, REQ-PCG-028) for other contract types (propagation, schema, ordering) would be difficult and likely manual. This directly impacts testability of the governance system. | 2026-02-19 17:46:51 UTC |
| R2-S5 | Change the behavior for malformed run-provenance.json from 'silently ignored' to 'fail loudly' to align with REQ-PCG-023's Fail Loud principle. | gemini-2.5 (gemini-2.5-pro) | Silently ignoring a corrupt provenance file directly contradicts the document's own 'Fail Loud, Fail Early' principle (REQ-PCG-023) and can hide fundamental pipeline setup errors, breaking the chain of custody that the entire governance system is designed to protect. | 2026-02-19 17:46:51 UTC |
| R2-S8 | Synchronize pipeline diagrams to reflect the two-step implementation of Stage 2 (analyze-plan and init-from-plan). | gemini-2.5 (gemini-2.5-pro) | While low severity, the inconsistency between diagrams showing a single 'INIT-FROM-PLAN' stage and REQ-CDP-008 defining two distinct commands creates unnecessary confusion for anyone mapping diagrams to implementation. This is a straightforward fix that improves document accuracy. | 2026-02-19 17:46:51 UTC |
| R2-S9 | Add a 'Source' field to each requirement to trace it back to the original design document it consolidates. | gemini-2.5 (gemini-2.5-pro) | The PCG document consolidates five source documents, and its value depends on maintainers being able to trace requirements back to their origins for deeper context. Without source traceability, the consolidation creates an information silo rather than a navigable reference. | 2026-02-19 17:46:51 UTC |
| R3-S1 | Define concrete thresholds for 'reasonable' complexity scores in REQ-PCG-021 and REQ-PCG-026. | claude-4 (claude-opus-4-6) | The term 'reasonable (not all 0 or all 100)' is genuinely ambiguous and is used in a blocking gate (Gate 2 Q2). Without quantified bounds, two implementations could disagree on what passes. The suggestion to specify minimum variance or distribution constraints is actionable and directly impacts automated enforcement. | 2026-02-19 18:32:33 UTC |
| R3-S2 | Specify how BoundaryValidator bridges the file-based ContextCore-to-startd8 handoff with its in-memory API. | claude-4 (claude-opus-4-6) | REQ-PCG-025 places BoundaryValidator at the handoff boundary but the handoff is file-based (YAML/JSON artifacts on disk) while the validator API operates on in-memory context dicts. This is a real impedance mismatch that must be resolved for implementers to know whether to reuse or adapt the existing validator. The hydration step specification is essential. | 2026-02-19 18:32:33 UTC |
| R3-S3 | Clarify the discrepancy between 'Implemented' status and 'D' (domain logic only) in the Implementation Status Matrix for domains 3-7. | claude-4 (claude-opus-4-6) | REQ-PCG-004 and REQ-PCG-006 (and domains 3-7 generally) are marked 'Implemented' with test counts but the matrix shows 'D' meaning lifecycle wiring is pending. This creates false confidence — tests exist for domain logic but the enforcement infrastructure at pre-flight/runtime/post-exec stages is absent. Correcting the status and specifying the wiring gap prevents misleading verification claims. | 2026-02-19 18:32:33 UTC |
| R3-S4 | Add concrete test references for REQ-PCG-022 (Gate 3 — Finalize Verification) in the Verification Plan. | claude-4 (claude-opus-4-6) | Gate 3 is a P1 requirement and the final integrity check before artifact delivery, yet it is the only P1 gate without a specific test file or test count in the Verification Plan. Gates 1 and 2 cite 34 and 25 tests respectively. This gap makes it impossible to verify whether Gate 3 is actually tested. | 2026-02-19 18:32:33 UTC |
| R3-S5 | Add 'Derives from' annotations to Part 2 requirements (REQ-PCG-017 through REQ-PCG-027) linking to specific source document sections. | claude-4 (claude-opus-4-6) | The document consolidates 5 source documents and Part 1 requirements have clear derivation, but Part 2 requirements lack backward traceability. An auditor cannot verify consolidation completeness without manually cross-referencing entire source documents. This is a legitimate traceability gap for a consolidation document. | 2026-02-19 18:32:33 UTC |
| R3-S6 | Specify concrete sandbox constraints for eval() in NFR-PCG-004 including prohibited AST nodes, max expression length, timeout, and error reporting. | claude-4 (claude-opus-4-6) | The current 'trusted source' assumption is fragile — a malicious PR could inject verification expressions. The requirement acknowledges the risk but provides no mechanical enforcement criteria. Specifying prohibited AST node types, length limits, and timeouts makes the sandbox auditable and testable. This complements R4-S5 but focuses on hardening the existing mechanism rather than replacing it. | 2026-02-19 18:32:33 UTC |
| R3-S7 | Define the baseline against which REQ-PCG-012's 'MUST NOT decrease propagation completeness' is measured. | claude-4 (claude-opus-4-6) | The requirement mandates that completeness must not decrease between builds but never specifies the comparison target (main branch HEAD, release tag, threshold file). This is a genuine feasibility gap — without a defined baseline source, the CI gate cannot be implemented deterministically, and merge order conflicts are unresolvable. | 2026-02-19 18:32:33 UTC |
| R3-S8 | Specify the test harness approach for observability requirements (REQ-PCG-011, REQ-PCG-028, REQ-PCG-029) — whether automated against mocks, schema validation, or manual. | claude-4 (claude-opus-4-6) | These P1/P2 requirements have acceptance criteria requiring running Tempo/Grafana instances ('TraceQL queries return results; dashboard panels render') but no specification of how this is verified in CI. The 24 cited tests aren't connected to specific requirements. Without clarifying the test approach, these requirements risk being unverifiable in automated regression. | 2026-02-19 18:32:33 UTC |
| R3-S9 | Add a requirement-to-domain traceability mapping connecting REQ-PCG-0XX IDs to Implementation Status Matrix cells. | claude-4 (claude-opus-4-6) | The matrix operates at domain×lifecycle granularity but requirements (REQ-PCG-008/009/010) apply across all 7 domains. Without an explicit mapping, an auditor cannot determine which requirements are fully vs partially satisfied. The discrepancy between 'Implemented' status labels and 'D' matrix cells (raised in R3-S3) is amplified by this traceability gap. | 2026-02-19 18:32:33 UTC |
| R3-S10 | Replace qualitative acceptance criteria ('appropriately-scoped alerts', 'documented side effects') in REQ-PCG-006 and REQ-PCG-013 with specific testable predicates. | claude-4 (claude-opus-4-6) | Acceptance criteria using 'appropriate' and 'documented' cannot be mechanically verified. Specifying exact GateResult severity values, span event names, and attribute values for each severity×budget state combination converts these from subjective judgments to automated test assertions. | 2026-02-19 18:32:33 UTC |
| R4-S1 | Modify REQ-PCG-020 Gate 1 row 5 (Gap parity) to check against declared gaps in artifact-manifest.yaml, not extracted features from Stage 5. | gemini-3 (gemini-3-pro-preview) | Gate 1 runs at the Export→Plan Ingestion boundary (before Stage 5 PARSE), so 'artifact features' produced by PARSE do not exist yet. Checking gap parity against extracted features is temporally impossible. The gate must check against declared gaps in the manifest. This is a clear feasibility error. | 2026-02-19 18:32:33 UTC |
| R4-S2 | Explicitly distinguish degradable Propagation Contracts from mandatory A2A Contracts in REQ-PCG-025 and NFR-PCG-002. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-017 mandates A2A validation (Pydantic models in startd8-sdk) while NFR-PCG-002 says validation degrades without ContextCore. These are different contract systems with different degradation semantics — A2A Pydantic validation lives in startd8-sdk and should remain active regardless of ContextCore availability. The current text conflates them, creating an ambiguity that could lead to A2A validation being incorrectly disabled. | 2026-02-19 18:32:33 UTC |
| R4-S3 | Update REQ-PCG-021 Gate 2 Q2 to account for force_route overrides when validating routing against complexity scores. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-026 explicitly supports force_route overrides, but Gate 2 Q2 checks that 'TRANSFORM routing matches score' without acknowledging overrides. This would produce false gate failures when force_route is legitimately used. The acceptance criteria for REQ-PCG-026 already mentions 'or force_route override' but the gate requirement itself doesn't account for it. | 2026-02-19 18:32:33 UTC |
| R4-S6 | Clarify in REQ-PCG-013 that default injection must stamp provenance with the current phase as origin_phase. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-013 requirement 3 specifies that WARNING-severity defaults are injected into the context dict, and REQ-PCG-014 specifies provenance stamping, but neither explicitly requires that defaulted values get provenance stamps with the injecting phase as origin. Without this, defaulted values break the audit trail — they appear with no origin or misleading provenance. This is a small but important consistency gap between the severity model and provenance requirements. | 2026-02-19 18:32:33 UTC |
| R4-S7 | Standardize the artifact manifest filename reference in REQ-PCG-024 to {project}-artifact-manifest.yaml to match REQ-CDP-007. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-024 references 'artifact-manifest.yaml' while the companion pipeline document uses '{project}-artifact-manifest.yaml'. Inconsistent filenames between the two documents will cause implementation confusion and potential file-not-found errors at the handoff boundary. This is a straightforward consistency fix. | 2026-02-19 18:32:33 UTC |
| R4-S8 | Clarify in REQ-PCG-022 whether checksums verify integrity (hash of disk files) or reproducibility (regenerate and compare). | gemini-3 (gemini-3-pro-preview) | REQ-PCG-019 says 'recomputed from actual files' and REQ-PCG-022 requires 'per-artifact SHA-256 checksums MUST be computed for all generated artifacts.' The ambiguity between integrity checking (hash files on disk) vs reproducibility checking (regenerate artifacts and compare hashes) has significant implementation implications — reproducibility requires deterministic generation. The test approach differs fundamentally between the two interpretations. | 2026-02-19 18:32:33 UTC |
| R4-S9 | Explicitly require create and polish stages (0-1) to seed the _cc_propagation provenance dict in REQ-PCG-014. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-014 specifies provenance tracking under _cc_propagation but doesn't specify when the provenance chain must be initialized. If stages 0-1 (create/polish) don't seed the provenance dict, the chain tracking effectively starts late, missing the project root context. This creates a gap where early-stage context has no provenance, undermining the end-to-end chain verification required by REQ-PCG-007 and REQ-PCG-024. | 2026-02-19 18:32:33 UTC |
| R5-S1 | Define contract versioning and migration strategy for schema evolution beyond v1. | claude-4 (claude-opus-4-6) | The combination of `extra="forbid"` (REQ-PCG-017) and `schema_version: "v1"` creates a real brittleness problem: any v2 contract with new fields will be rejected by v1 validators during rolling deployments. This is a critical gap that must be addressed before the system matures, and the suggestion correctly identifies the interaction between previously accepted strict schema enforcement and future evolution needs. | 2026-02-19 19:02:22 UTC |
| R5-S2 | Address clock skew and timestamp reliability for provenance chain verification across distributed pipeline halves. | claude-4 (claude-opus-4-6) | REQ-PCG-007 relies on ISO 8601 timestamps and REQ-PCG-004 requires causal ordering based on provenance timestamps. In a distributed deployment where ContextCore and startd8-sdk run on different hosts, clock skew is a real operational concern that could silently break causal ordering validation. Specifying that phase sequence (logical ordering) is primary and wall-clock is secondary is a practical and necessary clarification. | 2026-02-19 19:02:22 UTC |
| R5-S3 | Specify deterministic resolution behavior when a field appears in multiple propagation chains with conflicting severity levels. | claude-4 (claude-opus-4-6) | REQ-PCG-001 allows multiple PropagationChainSpec entries and REQ-PCG-013 defines three severity tiers, but there is no specified behavior for the case where the same field has BLOCKING severity in one chain and ADVISORY in another. This is a genuine ambiguity that would lead to implementation-dependent behavior. A deterministic resolution rule (e.g., highest severity wins) is essential for predictable gate outcomes. | 2026-02-19 19:02:22 UTC |
| R5-S4 | Require an end-to-end integration test exercising the full pipeline path (stages 0→7) with contract enforcement enabled. | claude-4 (claude-opus-4-6) | The Verification Plan lists extensive unit and component tests per requirement but lacks a mandatory integration test spanning both pipeline halves with real handoff artifacts. The handoff boundary between ContextCore and startd8-sdk is the highest-risk point for integration failures, and unit tests alone cannot validate artifact serialization assumptions across this boundary. | 2026-02-19 19:02:22 UTC |
| R5-S5 | Reconcile the `_cc_propagation` reserved key with `extra="forbid"` on Pydantic models at the handoff boundary. | claude-4 (claude-opus-4-6) | This identifies a genuine consistency issue: REQ-PCG-014 stores provenance under `_cc_propagation` in the context dict, while REQ-PCG-015/017 enforce `extra="forbid"` on all Pydantic models. If the context dict is ever validated through a Pydantic model at the handoff boundary, the `_cc_propagation` key would be rejected. The document must clarify whether this key is stripped before validation or explicitly declared in the model. | 2026-02-19 19:02:22 UTC |
| R5-S6 | Define concrete bounds for "reasonable" complexity score in Q2 ASSESS validation, replacing the ambiguous term. | claude-4 (claude-opus-4-6) | REQ-PCG-021 Q2 and REQ-PCG-026 both use the term "reasonable" for complexity scores without defining it, making this gate check unimplementable as a deterministic pass/fail. Replacing it with concrete criteria (e.g., minimum non-zero dimensions, standard deviation threshold) is necessary for testability and NFR-PCG-005 (idempotent gate execution). | 2026-02-19 19:02:22 UTC |
| R5-S7 | Add traceability mapping from Part 4 extension concerns to specific REQ-PCG base requirement IDs. | claude-4 (claude-opus-4-6) | Part 4 lists 9 extension concerns with related domains but provides no explicit traceability to the REQ-PCG requirements they extend. This is a straightforward traceability gap that is easy to fix (add a column to the table) and prevents future implementation work from violating or duplicating core requirements. | 2026-02-19 19:02:22 UTC |
| R5-S8 | Specify maximum contract YAML size, chain count, expression complexity limits, and validation timeout to prevent unbounded validation latency. | claude-4 (claude-opus-4-6) | No requirement currently bounds the overhead of contract validation when contracts are present. Combined with the eval() mechanism in NFR-PCG-004, pathological contracts could cause unbounded latency. This is a legitimate feasibility concern that becomes critical as the system scales or if contracts grow organically over time. | 2026-02-19 19:02:22 UTC |
| R5-S9 | Specify provenance re-stamping behavior when Stage 1.5 (FIX auto-remedy) modifies fields already stamped in Stage 1. | claude-4 (claude-opus-4-6) | The pipeline diagram shows Stage 1.5 between Stages 1 and 2, but REQ-PCG-014 doesn't address what happens when auto-remediation modifies a provenance-stamped field. The hash mismatch would either cause a false positive integrity failure or require explicit re-stamping rules. This is a completeness gap in the provenance tracking specification. | 2026-02-19 19:02:22 UTC |
| R6-S1 | Replace Python eval() in NFR-PCG-004 with a standard expression language like CEL for security and portability. | gemini-3 (gemini-3-pro-preview) | NFR-PCG-004 already acknowledges the risk by noting eval() must be replaced if contracts come from untrusted sources. However, even sandboxed eval() has known escape vectors in Python, and it permanently ties contract validation to the Python runtime. CEL or a similar safe expression language addresses both the security risk and the cross-language portability concern. This aligns with and strengthens the existing requirement text. | 2026-02-19 19:02:22 UTC |
| R6-S3 | Mandate reconciliation between inline _cc_propagation and external run-provenance.json at Gate 1. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-007 stores provenance inline and REQ-PCG-024 stores it externally in run-provenance.json, but no requirement ensures they are consistent. A buggy or malicious stage could update the context dict without updating the external audit trail. Adding this as a Gate 1 check closes a real integrity gap in the provenance verification chain. | 2026-02-19 19:02:22 UTC |
| R6-S4 | Distinguish between execution time and wall time in SLO Budget Propagation to handle human-in-the-loop stages. | gemini-3 (gemini-3-pro-preview) | Stage 6 includes REVIEW which can involve human review. If REQ-PCG-006 budget tracking uses wall-clock time, any human pause will exhaust the budget and produce false BROKEN signals. The requirement must clarify whether remaining_budget_ms tracks compute time only, or explicitly exclude/account for human wait time. This is a practical feasibility concern for real pipeline operations. | 2026-02-19 19:02:22 UTC |
| R6-S5 | Define fail-closed behavior for critical/safety contracts when ContextCore is missing. | gemini-3 (gemini-3-pro-preview) | NFR-PCG-002 specifies graceful degradation (return None) when ContextCore is not installed. However, if a contract enforces a safety-critical check (e.g., PII scrubbing), running without validation silently bypasses that safety control. The requirement should distinguish between optional and safety-critical contracts, with the latter requiring fail-closed behavior even when ContextCore is absent. | 2026-02-19 19:02:22 UTC |
| R6-S6 | Explicitly define determinism requirements for the ASSESS phase to ensure compliance with idempotent gate execution. | gemini-3 (gemini-3-pro-preview) | If ASSESS uses probabilistic methods (e.g., LLM-based scoring), it would violate NFR-PCG-005 (Idempotent Gate Execution), since re-running with the same input could produce different complexity scores and routing decisions. This is a real tension in the requirements that needs explicit resolution—either ASSESS must be deterministic, or NFR-PCG-005's scope must be clarified to exclude scoring phases. | 2026-02-19 19:02:22 UTC |
| R1-F1 | Add a requirement defining the minimum required schema for run-provenance.json. |  | Gate 1's provenance cross-check is unspecifiable without a defined schema. Two implementations could define different schemas and both claim compliance. This is a real gap that impacts the accepted R6-S3 reconciliation work. | 2026-02-19 19:09:57 UTC |
| R1-F2 | Document the frozen interface signatures for validate_phase_entry() and validate_phase_exit(). |  | The 'MUST remain unchanged' constraint in REQ-PCG-009 is unenforceable without a documented interface definition. Specifying parameters, return types, and error signaling makes the backward compatibility guarantee concrete and testable. | 2026-02-19 19:09:57 UTC |
| R1-F3 | Add a requirement for backward compatibility tooling during the eval-to-CEL migration. |  | The CEL migration (R6-S1) will break all existing verification expressions. Capturing the compatibility requirement now, before implementation begins, prevents a foreseeable migration failure. This can be a deferred requirement but should be documented. | 2026-02-19 19:09:57 UTC |
| R1-F5 | Define partial phase success semantics for the Artisan 7-phase workflow in REQ-PCG-027. |  | Partial success is the most common real-world scenario in multi-artifact workflows. Without defined semantics, implementations will diverge on whether to halt, continue, or report partial results. This is a genuine requirements gap. | 2026-02-19 19:09:57 UTC |
| R1-F6 | Add a version constraint strategy requirement for the ContextCore dependency in startd8-sdk. |  | The cross-repo dependency is the highest-risk integration point. Without a specified versioning strategy, the two packages can drift silently. This directly supports the accepted R5-S1 versioning strategy and prevents real integration failures. | 2026-02-19 19:09:57 UTC |
| R7-S1 | Define contract schema versioning and migration strategy across the ContextCore/startd8-sdk boundary. | claude-4 (claude-opus-4-6) | REQ-PCG-017 mandates schema_version='v1' and REQ-PCG-015 uses extra='forbid', but there is no requirement governing schema evolution across repos. Given the cross-repo split in REQ-PCG-025, a v2 schema from ContextCore would be rejected by startd8-sdk's strict validation with no upgrade path or version negotiation. This is a genuine high-risk coordination gap that previously accepted suggestions did not address. | 2026-02-19 19:19:51 UTC |
| R7-S2 | Specify maximum contract YAML size and validation time budget for pre-flight and runtime checks. | claude-4 (claude-opus-4-6) | NFR-PCG-001 promises zero overhead without contracts, but no requirement bounds the cost of validation when contracts ARE active. As domains scale, cumulative validation overhead could become significant, especially given eval()-based verification expressions at every phase boundary. The irony of validation itself busting the SLO budget (REQ-PCG-006) is a real feasibility concern that needs addressing. | 2026-02-19 19:19:51 UTC |
| R7-S3 | Specify aggregation semantics when multiple contract domains produce conflicting verdicts at the same phase boundary. | claude-4 (claude-opus-4-6) | Seven domains can each produce BLOCKING/WARNING/ADVISORY results at the same boundary, but no requirement specifies how these are aggregated into a single go/no-go decision. This is a critical completeness gap: implementers need to know whether one BLOCKING from any domain halts the phase, or whether there is domain precedence. Without this, runtime behavior is undefined. | 2026-02-19 19:19:51 UTC |
| R7-S4 | Add integration/end-to-end test requirements to the Verification Plan beyond unit test counts. | claude-4 (claude-opus-4-6) | The Verification Plan only cites unit test suites per domain. There is no requirement for an integration test exercising a full pipeline run (stages 0→7) with all contract domains active, which is essential to verify cross-domain composition and cross-repo handoff (REQ-PCG-024/025). Unit tests passing individually does not guarantee correct composition at runtime. | 2026-02-19 19:19:51 UTC |
| R7-S5 | Replace repr() with a deterministic canonical serialization for provenance hashing in REQ-PCG-014. | claude-4 (claude-opus-4-6) | repr() output varies across Python versions for floats, dicts, and custom objects, creating a real portability risk especially given the cross-repo architecture where ContextCore and startd8-sdk may run different Python versions. This is the same issue as R8-S1 and both identify a genuine correctness problem with the provenance hash mechanism. | 2026-02-19 19:19:51 UTC |
| R7-S6 | Clarify contract governance posture for Stage 1.5 (FIX auto-remedy) which appears in the pipeline diagram but has no corresponding requirements. | claude-4 (claude-opus-4-6) | Stage 1.5 is shown in the pipeline overview but no REQ-PCG requirement specifies boundary checks, context declarations, or provenance behavior for it. If FIX mutates context fields, provenance hashes from Stage 1 could be invalidated. Even a brief note clarifying that Stage 1.5 follows Stage 1's governance rules would close this gap. | 2026-02-19 19:19:51 UTC |
| R7-S7 | Add prerequisite core requirement traceability to Part 4 extension concerns. | claude-4 (claude-opus-4-6) | Part 4 lists 9 extension concerns with 'Related Domain' but doesn't trace which core REQ-PCG requirements they depend on or extend. Without this mapping, implementers cannot determine prerequisites or which acceptance criteria must be preserved. Adding a 'Prerequisite Core REQs' column is low effort and high value for traceability. | 2026-02-19 19:19:51 UTC |
| R7-S8 | Strengthen NFR-PCG-004's eval() sandboxing by specifying operational trust controls or requiring a safe expression evaluator. | claude-4 (claude-opus-4-6) | The current mitigation (restricted globals) is well-known to be bypassable in Python. While the document acknowledges trusted input, it doesn't operationally define 'trusted' (e.g., CODEOWNERS, branch protection). Specifying the operational trust boundary or requiring an AST-based evaluator closes a real security gap without overcomplicating the design. | 2026-02-19 19:19:51 UTC |
| R7-S9 | Add requirements addressing concurrent pipeline runs sharing the same project context or artifact namespace. | claude-4 (claude-opus-4-6) | Shared filesystem artifacts (.contextcore.yaml, onboarding-metadata.json) could be overwritten by concurrent runs, causing checksum mismatches diagnosed as corruption rather than concurrency. NFR-PCG-005 (idempotent gates) doesn't cover input mutation by concurrent runs. This is a realistic operational scenario that needs at least a documented isolation requirement. | 2026-02-19 19:19:51 UTC |
| R7-S10 | Distinguish domain-logic tests from lifecycle-integration tests in the Verification Plan for domains at 'D' status. | claude-4 (claude-opus-4-6) | The Implementation Status Matrix shows 5 domains at 'D' (lifecycle wiring pending) but the Verification Plan claims tests exist for all 7 domains without distinguishing test scope. This creates false confidence that lifecycle integration is tested when only domain logic is. A simple footnote or column addition would clarify the actual verification coverage. | 2026-02-19 19:19:51 UTC |
| R8-S3 | Add a sensitive=True attribute to FieldSpec to inhibit value hashing/storage in provenance for sensitive fields. | gemini-3 (gemini-3-pro-preview) | Storing repr(value) or its hash for low-entropy secrets (API keys, tokens) in _cc_propagation risks leaking sensitive data via logs, error dumps, or rainbow-table attacks on short hashes. This is a genuine security gap not covered by existing requirements. The fix is straightforward: add a field attribute and suppress hashing for marked fields. | 2026-02-19 19:19:51 UTC |
| R8-S4 | Require Gate 3 to verify no unaccounted artifacts exist in the output directory (strict allowlist). | gemini-3 (gemini-3-pro-preview) | Current Gate 3 requirements (REQ-PCG-022) only verify that planned artifacts exist but don't prevent extra unexpected artifacts from being generated. A strict allowlist check is a natural extension of the defense-in-depth philosophy and prevents artifact namespace pollution by buggy or compromised contractors. | 2026-02-19 19:19:51 UTC |
| R8-S5 | Mandate that applying a default value (REQ-PCG-013) stamps a 'System Default' entry into the provenance chain. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-013 specifies that WARNING-severity absent fields get defaults injected, but REQ-PCG-014's provenance tracking doesn't account for system-initiated mutations. Without a provenance stamp, a default injection appears as an unexplained value change in the provenance chain, undermining the correctness-by-construction guarantee. | 2026-02-19 19:19:51 UTC |
| R8-S6 | Create a formal contract or bypass event for manual interventions like force_route and gate skips. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-026 allows force_route and REQ-PCG-008 allows bypassing pre-flight, but neither requires these overrides to be recorded in the provenance chain or contract system. This creates an audit gap where the 'Correctness by Construction' claim can be silently invalidated. A lightweight BypassEvent with user attribution closes this gap. | 2026-02-19 19:19:51 UTC |
| R8-S7 | Define a pruning or summarization strategy for _cc_propagation to prevent context bloat. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-007 requires provenance to travel with the data, meaning _cc_propagation grows linearly with pipeline length and field count. For long chains or repeated runs, this could cause memory issues or exceed transport limits. A retention/summarization policy is a pragmatic feasibility concern. | 2026-02-19 19:19:51 UTC |
| R8-S8 | Add a critical cleanup budget reservation or exemption to REQ-PCG-006 for Export/Finalize stages. | gemini-3 (gemini-3-pro-preview) | If an earlier stage exhausts the SLO budget, REQ-PCG-006 implies the pipeline halts, which would prevent the Export/Finalize stages from saving artifacts and logs needed to diagnose the failure. A small reserved budget for cleanup/finalization is a practical necessity that preserves debuggability without undermining budget governance. | 2026-02-19 19:19:51 UTC |
| R1-F1 | Add a requirement defining the minimum required schema for run-provenance.json. |  | Gate 1's provenance cross-check is unverifiable without a defined schema. Two implementations could diverge on what constitutes valid provenance. This is a genuine completeness gap that directly impacts enforceability of existing requirements. | 2026-02-19 19:28:23 UTC |
| R1-F2 | Document the frozen interface signatures for validate_phase_entry() and validate_phase_exit(). |  | The 'MUST remain unchanged' constraint in REQ-PCG-009 is unenforceable without specifying what 'unchanged' means at the API level. Documenting parameter types, return types, and error signaling is essential for backward compatibility enforcement. | 2026-02-19 19:28:23 UTC |
| R1-F3 | Add a requirement for an eval()-to-CEL expression compatibility validation tool during the migration. |  | The CEL migration (accepted R6-S1) will break all existing verification expressions unless portability is validated. This is a foreseeable transition risk that should be captured as a requirement before implementation begins. | 2026-02-19 19:28:23 UTC |
| R1-F5 | Define partial phase success semantics for the Artisan 7-phase workflow in REQ-PCG-027. |  | Partial success is the most common real-world scenario and the current requirements only cover full success and full failure. Without defined semantics, implementations will diverge on whether to propagate partial results or halt entirely. | 2026-02-19 19:28:23 UTC |
| R3-F1 | Specify the cardinality of context.boundary span events — whether per-boundary (summary) or per-field (detailed). |  | With 7 domains active, per-field emission could produce dozens of span events per phase transition, overwhelming OTel collectors. This is a practical operational concern that must be specified before implementation to avoid tracing infrastructure issues. | 2026-02-19 19:28:23 UTC |
| R3-F2 | Add dependency direction arrows to REQ-PCG-025's component-to-repository mapping and resolve the circular dependency between ContextCore and startd8-sdk. |  | The circular dependency (startd8-sdk imports ContextCore validators, but ContextCore's loader consumes startd8-sdk's contract YAML) is a real architectural issue that will block clean builds and testing. Specifying unidirectional dependency is essential even if the full hydration adapter is deferred to Phase 2. | 2026-02-19 19:28:23 UTC |
| R3-F3 | Require that error envelopes from boundary validation must not include field values for fields marked sensitive in the contract schema. |  | The intersection of boundary enforcement error reporting and the accepted sensitive field proposal (R8-S3) creates a data leakage vector. This is a straightforward security fix that prevents sensitive values from appearing in logs via the failed_path in error envelopes. | 2026-02-19 19:28:23 UTC |
| R3-F4 | Clarify what existing regression tests in contracts/regression/ actually verify, since the regression baseline is deferred to Phase 2. |  | If the Verification Plan claims tests exist but those tests verify a different property (YAML syntax vs. cross-PR completeness), the plan is misleading. Clarifying actual test scope prevents false confidence in coverage. | 2026-02-19 19:28:23 UTC |
| R8-S2 | Replace eval() in NFR-PCG-004 with a restricted expression parser to prevent CPU/memory exhaustion attacks. | gemini-3 (gemini-3-pro-preview) | NFR-PCG-004 acknowledges the eval() risk but the current mitigation (restricted globals) is insufficient against resource exhaustion attacks like 9**9**9. Since contract YAML is parsed in CI (REQ-PCG-012), this is a concrete security vector. Replacing eval() with an AST-whitelist or simpleeval is a proportionate and well-understood mitigation. | 2026-02-19 19:41:04 UTC |
| R9-S1 | Define contract versioning and migration strategy for schema_version transitions beyond v1. | claude-4 (claude-opus-4-6) | REQ-PCG-017 enforces extra='forbid' with schema_version='v1', meaning any new field is a breaking change. Without a version negotiation or dual-version acceptance window strategy, the first schema evolution will require atomic coordinated deployment across all producers and consumers. This is a real architectural gap that should be addressed proactively. | 2026-02-19 19:41:04 UTC |
| R9-S2 | Address eval() sandbox escape risk when CI runs contract analysis on untrusted PR YAML from forks. | claude-4 (claude-opus-4-6) | This is a distinct and more specific concern than R8-S2. REQ-PCG-012 runs contract YAML analysis on PRs, and in open-source models, PRs from forks contain untrusted YAML. The 'trusted sources only' assumption in NFR-PCG-004 directly contradicts the CI regression detection use case. The suggestion to either not evaluate expressions on unmerged PRs or replace eval() is well-targeted. | 2026-02-19 19:41:04 UTC |
| R9-S3 | Specify aggregation semantics when multiple contract domains produce conflicting decisions at the same boundary. | claude-4 (claude-opus-4-6) | Seven domains can independently produce BLOCKING/WARNING/ADVISORY results at the same boundary, but no requirement specifies the merge function. The suggested worst-of-all-domains aggregation with per-domain breakdown is the obvious correct behavior but must be explicitly specified to avoid implementation ambiguity. | 2026-02-19 19:41:04 UTC |
| R9-S4 | Add an end-to-end integration test requirement spanning Stages 0-7 with real contract enforcement. | claude-4 (claude-opus-4-6) | The verification plan only lists per-requirement unit/integration tests scoped to individual components. With 76+ accepted suggestions modifying behavior across two halves of the pipeline, a true end-to-end test exercising real contract YAML, real checksums, and real OTel emission is essential to validate the system works as a whole, not just in parts. | 2026-02-19 19:41:04 UTC |
| R9-S5 | Clarify 'zero overhead' in NFR-PCG-001 with a measurable threshold since literal zero is physically impossible. | claude-4 (claude-opus-4-6) | NFR-PCG-001 states 'zero runtime overhead' which is untestable as stated — even a null check has nonzero cost. Redefining as a measurable bound (e.g., <1ms per phase transition, <100KB memory) makes the requirement verifiable and adds a benchmark test to the verification plan. | 2026-02-19 19:41:04 UTC |
| R9-S6 | Reconcile the truncated sha256[:8] hash in REQ-PCG-014 provenance with full SHA-256 in gate checksums, and document interop semantics. | claude-4 (claude-opus-4-6) | REQ-PCG-014 uses 8-character truncated hashes (32 bits, birthday collision at ~65K values) while REQ-PCG-019/022 use full SHA-256. Gate 3 must verify the provenance chain end-to-end but the document never specifies how these formats interoperate. Clarifying the distinction (field-level spot check vs. artifact-level tamper detection) and documenting collision risk is important for security and consistency. | 2026-02-19 19:41:04 UTC |
| R9-S8 | Specify maximum contract YAML size and loading timeout to prevent resource exhaustion in CI. | claude-4 (claude-opus-4-6) | With 7 core domains plus 9 extensions and progressive adoption growing contracts over time, unbounded YAML loading in CI pipelines processing many PRs (per REQ-PCG-012) is a real resource exhaustion risk. A reasonable size limit and timeout with structured error is a simple, defensive requirement. | 2026-02-19 19:41:04 UTC |
| R9-S10 | Explicitly include Stage 1.5 (FIX auto-remedy) in contract enforcement scope with provenance tracking. | claude-4 (claude-opus-4-6) | Stage 1.5 is shown in the pipeline diagram and mutates context, but REQ-PCG-009 only defines validation at 'phase boundaries' without explicitly listing Stage 1.5. Since auto-remedy mutations change field values that may be under propagation contracts, these mutations must be tracked in provenance (REQ-PCG-014) and validated at the 1.5→2 boundary. The omission creates an implicit gap in the enforcement model. | 2026-02-19 19:41:04 UTC |
| R10-S1 | Add a Gate 1 bypass or native implementation requirement for startd8-sdk minimal installs without ContextCore. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-020 mandates running `contextcore contract a2a-check-pipeline` for Gate 1, but NFR-PCG-002 requires operation without ContextCore installed. This is a direct contradiction — a minimal install cannot execute a CLI tool from a package that isn't installed. A bypass or native fallback implementation is necessary to resolve this conflict. | 2026-02-19 19:41:04 UTC |
| R10-S2 | Clarify NFR-PCG-005 idempotency when REQ-PCG-001 mutates context by applying defaults, changing observed state on second run. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-001 applies defaults for WARNING-severity absent fields (mutating context), so a second validation run sees the field as present rather than defaulted, producing different telemetry status. This is a genuine tension between mutation behavior and idempotency guarantees that needs explicit clarification — either idempotency is defined over the original input (not mutated state) or the mutation semantics need refinement. | 2026-02-19 19:41:04 UTC |
| R10-S4 | Require schema_version compatibility check in REQ-PCG-024 handoff metadata to fail fast on version mismatch. | gemini-3 (gemini-3-pro-preview) | ContextCore and startd8-sdk have distinct release lifecycles. If ContextCore exports v2 artifacts while startd8-sdk expects v1, the pipeline should fail immediately at the handoff boundary with a clear version error, not deep in processing with a cryptic validation error. This complements the accepted R9-S1 versioning strategy and makes the handoff boundary more robust. | 2026-02-19 19:41:04 UTC |
| R10-S5 | Require provenance (REQ-PCG-007) to re-stamp value_hash when defaults are applied by REQ-PCG-001. | gemini-3 (gemini-3-pro-preview) | When a WARNING-severity default is applied, the field value changes. If provenance isn't updated with the new value_hash, subsequent lineage verification will detect a hash mismatch and report a false broken chain. This is a clear interaction between two requirements that needs explicit coordination. | 2026-02-19 19:41:04 UTC |
| R1-F1 | Add a requirement defining the minimum required schema for run-provenance.json |  | Gate 1's provenance cross-check and accepted R6-S3 reconciliation both depend on knowing what fields run-provenance.json must contain. Without a schema definition, compliance is ambiguous and two implementations could diverge. | 2026-02-19 19:49:46 UTC |
| R1-F2 | Document the frozen interface signatures for validate_phase_entry() and validate_phase_exit() |  | The 'MUST remain unchanged' constraint in REQ-PCG-009 req 4 is unenforceable without specifying what constitutes the frozen API surface. This is directly referenced by R4-F4 as well, confirming the gap. | 2026-02-19 19:49:46 UTC |
| R1-F5 | Define partial phase success semantics for the Artisan 7-phase workflow |  | Partial success is the most common real-world scenario and the current requirements only cover full success/failure. Without defined semantics, implementers will make inconsistent choices about whether subsequent phases run on partial results. | 2026-02-19 19:49:46 UTC |
| R3-F1 | Define cardinality of context.boundary span events — per-boundary summary vs per-field detailed |  | High-cardinality span events can overwhelm OTel collectors. Implementers need to know whether to emit one event per boundary crossing or one per field checked, especially with 7 domains active. | 2026-02-19 19:49:46 UTC |
| R3-F2 | Clarify dependency direction between ContextCore and startd8-sdk to prevent circular dependencies |  | The cross-repo component mapping in REQ-PCG-025 has an implicit circular dependency (startd8-sdk imports from ContextCore, but ContextCore's loader consumes startd8-sdk's contract YAML). This must be resolved architecturally before implementation. | 2026-02-19 19:49:46 UTC |
| R3-F3 | Ensure error envelopes from boundary validation do not leak sensitive field values |  | The intersection of boundary enforcement error reporting and sensitive fields is a genuine data leakage vector. Error envelopes should include field paths but not field values for sensitive fields. This is a targeted, implementable security fix. | 2026-02-19 19:49:46 UTC |
| R3-F4 | Clarify what existing regression tests in contracts/regression/ actually verify vs what requires Phase 2 baseline |  | The Verification Plan claims tests exist in contracts/regression/ but the baseline for cross-PR completeness comparison is deferred. Clarifying the actual scope prevents misleading implementers about current test coverage. | 2026-02-19 19:49:46 UTC |
| R4-F1 | Add observable graduation criteria for progressive adoption stage transitions in REQ-PCG-016 |  | Without concrete criteria for stage transitions, progressive adoption is aspirational. Teams need measurable thresholds to know when to move from 'monitor' to 'tighten' — this makes the adoption path actionable. | 2026-02-19 19:49:46 UTC |
| R4-F2 | Rewrite REQ-PCG-027 requirement 6 to focus on validation outcomes rather than internal review architecture details |  | Requirements should specify WHAT, not HOW. The drafter/validator/reviewer pattern is an implementation choice. Endorsed by 1 reviewer, and the suggestion correctly identifies that implementation details in requirements constrain future changes unnecessarily. | 2026-02-19 19:49:46 UTC |
| R4-F3 | Generalize BudgetPropagationSpec to support multiple budget types beyond time (tokens, cost) |  | The Artisan workflow explicitly uses a 'tiered cost model' and LLM token consumption. A time-only budget spec cannot represent these real constraints. Generalizing to support budget_unit types makes the domain applicable to actual pipeline economics. | 2026-02-19 19:49:46 UTC |
| R4-F4 | Clarify what 'unchanged' means for validate_phase_entry/exit — API signature vs behavioral semantics |  | This directly complements R1-F2 and provides the specific resolution: public API signatures and return types are frozen, but internal implementation may be extended. Without this clarification, any contract system integration could be considered a breaking change. | 2026-02-19 19:49:46 UTC |
| R4-F5 | Resolve the conflict between idempotent gate execution (NFR-PCG-005) and WARNING defaults that mutate context (REQ-PCG-001 req 4) |  | This is a real semantic conflict: if validation mutates context by applying defaults, a re-run sees different input state. The suggestion to define idempotency over original input and record mutations deterministically is the correct resolution. | 2026-02-19 19:49:46 UTC |
| R11-S1 | Define explicit contract versioning and migration strategy for schema evolution beyond v1. | claude-4 (claude-opus-4-6) | With `extra="forbid"` (REQ-PCG-015) and `schema_version = "v1"` (REQ-PCG-017) already mandated, any schema evolution will cause hard failures. This is a genuine second-order gap created by previously accepted strict-validation suggestions. A version negotiation or migration strategy is essential to avoid big-bang coordinated deployments across two repos. | 2026-02-19 20:20:04 UTC |
| R11-S4 | Specify contract testing for the graceful degradation path when ContextCore is not installed, including behavior of `_cc_propagation` keys. | claude-4 (claude-opus-4-6) | NFR-PCG-002 requires graceful degradation but the verification plan has no explicit test for this path. The specific question of what happens to `_cc_propagation` keys in a context dict when they arrive at a startd8-sdk instance without ContextCore is a real gap — they could cause KeyErrors or silent data loss. An explicit test entry is low-cost and high-value. | 2026-02-19 20:20:04 UTC |
| R11-S5 | Reconcile and explicitly distinguish the truncated sha256 (8 chars) for provenance value hashes from full SHA-256 for file/artifact checksums. | claude-4 (claude-opus-4-6) | REQ-PCG-014.2 uses `sha256(repr(value))[:8]` while REQ-PCG-019 and REQ-PCG-022 use full SHA-256. The two conventions serve different purposes but are never explicitly distinguished. An implementer could easily conflate them. A simple clarifying note or naming convention (e.g., `value_hash` vs `checksum`) eliminates this ambiguity at negligible cost. | 2026-02-19 20:20:04 UTC |
| R11-S6 | Define behavior when verification expressions in propagation chains raise runtime exceptions rather than returning True/False. | claude-4 (claude-opus-4-6) | REQ-PCG-001.6 references verification expressions but only specifies outcomes for boolean results (INTACT/DEGRADED/BROKEN). An expression that raises TypeError or KeyError has no defined behavior. This is a genuine error-handling gap distinct from the security concern addressed by NFR-PCG-004. Specifying that exceptions map to BROKEN status with exception details is a straightforward and necessary clarification. | 2026-02-19 20:20:04 UTC |
| R11-S8 | Replace the ambiguous 'reasonable' qualifier for ASSESS complexity scores with a concrete invariant. | claude-4 (claude-opus-4-6) | REQ-PCG-026.2 and REQ-PCG-021 Q2 use 'reasonable' with only degenerate cases excluded (all 0 or all 100). This makes gate enforcement subjective. A concrete rule like 'at least 2 of 7 dimensions MUST have distinct non-zero scores' is easy to implement, test, and enforce consistently. This removes ambiguity from an acceptance criterion. | 2026-02-19 20:20:04 UTC |
| R11-S10 | Add an end-to-end contract validation test exercising the full pipeline (stages 0-7) with deliberately injected contract violations at each stage. | claude-4 (claude-opus-4-6) | The verification plan lists per-domain and per-gate test suites but lacks an integration test that validates emergent behavior across all enforcement points. With many individually accepted gates and checks, cross-boundary interactions (e.g., a WARNING default satisfying a downstream BLOCKING check with a semantically wrong value) could go undetected. An E2E fault-injection test is a standard best practice for contract-heavy systems. | 2026-02-19 20:20:04 UTC |
| R12-S1 | Resolve contradiction between REQ-PCG-013 (context mutation for defaults) and NFR-PCG-005 (gates must not have side effects). | gemini-3 (gemini-3-pro-preview) | This is a genuine contradiction. REQ-PCG-013.3 explicitly says 'WARNING-severity absent fields MUST have the default injected into the context dict (intentional mutation)' while NFR-PCG-005 says 'Gates MUST NOT have side effects beyond OTel event emission.' These two requirements directly conflict. The resolution likely involves clarifying that default injection is a defined effect (not a 'side effect') or separating validation from mutation, but the contradiction must be explicitly resolved. | 2026-02-19 20:20:04 UTC |
| R12-S3 | REQ-PCG-019 must specify a strict canonicalization method for file checksumming to ensure deterministic results. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-019 says checksums must be 'recomputed from actual files' but JSON serialization is non-deterministic (key ordering, whitespace). Two tools generating semantically identical JSON will produce different SHA-256 checksums. This is a known practical problem. Specifying canonicalization (e.g., sorted keys, consistent whitespace) is essential for reliable checksum verification. This has 2 endorsements from prior rounds (R8-S4). | 2026-02-19 20:20:04 UTC |
| R12-S4 | Replace `repr(value)` with a stable serialization method for provenance hashing. | gemini-3 (gemini-3-pro-preview) | This aligns with and reinforces R7-S7 (2 endorsements). `repr()` is implementation-dependent — dict repr ordering changed between Python versions, and custom objects include memory addresses. Using `json.dumps(val, sort_keys=True)` or equivalent ensures deterministic hashing across Python versions and processes. This is a real correctness bug, not a theoretical concern. | 2026-02-19 20:20:04 UTC |
| R12-S5 | Unconditionally require a restricted expression evaluator instead of allowing `eval()` for verification expressions. | gemini-3 (gemini-3-pro-preview) | NFR-PCG-004 allows `eval()` 'if contract YAML comes from trusted sources' but 'trusted' is contextually fragile (fork PRs, supply chain attacks). A restricted evaluator like `ast.literal_eval` or a simple DSL parser is feasible and eliminates an entire class of RCE vulnerabilities. The 'trusted source' caveat is operationally unenforceable. This suggestion has been raised multiple times across reviews. | 2026-02-19 20:20:04 UTC |
| R12-S6 | REQ-PCG-025 must include a runtime version compatibility check between startd8-sdk and ContextCore. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-025.4 requires graceful degradation when ContextCore is absent, but there's no requirement for handling an incompatible version of ContextCore being present. An API mismatch (e.g., ContractLoader signature change) would cause runtime crashes rather than graceful degradation. A simple version check with fallback is consistent with the existing graceful degradation philosophy. | 2026-02-19 20:20:04 UTC |
| R12-S7 | REQ-PCG-022 must explicitly define whether 'Partial' status rollup results in pipeline failure (non-zero exit code). | gemini-3 (gemini-3-pro-preview) | REQ-PCG-022 defines 'partial' as a status but doesn't specify its effect on pipeline exit codes. For CI orchestration, this is a critical ambiguity — operators need to know whether 'partial' is a pass or fail. The requirement should specify deterministic behavior, likely configurable (e.g., partial = fail by default, with a flag to treat as warning). | 2026-02-19 20:20:04 UTC |
| R1-F1 | Add a requirement defining the minimum required schema for run-provenance.json |  | Gate 1 references a provenance cross-check against run-provenance.json but without a defined schema, the check is unspecifiable. This is a genuine completeness gap that would cause interoperability issues between implementations. | 2026-02-19 20:25:47 UTC |
| R1-F2 | Document frozen interface signatures for validate_phase_entry() and validate_phase_exit() |  | The 'MUST remain unchanged' constraint in REQ-PCG-009 req 4 is unenforceable without specifying what constitutes the frozen API surface. This is a legitimate clarity gap that directly impacts backward compatibility guarantees. | 2026-02-19 20:25:47 UTC |
| R1-F3 | Add a requirement for eval()-to-CEL migration compatibility validation tooling |  | The transition from eval() to CEL will break existing verification expressions. Requiring a compatibility validation tool before the switch is a reasonable risk mitigation that prevents foreseeable breakage during the NFR-PCG-004 migration path. | 2026-02-19 20:25:47 UTC |
| R1-F5 | Define partial phase success semantics for the Artisan 7-phase workflow |  | Partial success is the most common real-world scenario and leaving it unspecified will cause inconsistent implementations. The requirement should define whether subsequent phases operate on successful artifacts and how FINALIZE reports partial outcomes. | 2026-02-19 20:25:47 UTC |
| R3-F1 | Specify cardinality of context.boundary span events — per-boundary summary vs per-field detailed |  | High-cardinality span events can overwhelm OTel collectors. With 7 domains active, the difference between per-boundary and per-field emission is orders of magnitude. This is a necessary implementation-guiding clarification. | 2026-02-19 20:25:47 UTC |
| R3-F2 | Add dependency direction arrows to REQ-PCG-025 component table and verify acyclic dependency graph |  | The cross-repo dependency between ContextCore and startd8-sdk appears potentially circular (SDK imports ContextCore, but ContextCore loads contract YAML from SDK). Clarifying dependency direction is essential for maintainability and independent buildability. | 2026-02-19 20:25:47 UTC |
| R3-F3 | Require error envelopes to exclude field values for fields marked sensitive=True |  | This is a genuine security gap at the intersection of boundary enforcement error reporting and the accepted R8-S3 sensitive field proposal. Leaking sensitive values in error messages is a well-known data exposure pattern that should be explicitly prevented. | 2026-02-19 20:25:47 UTC |
| R3-F4 | Clarify what existing regression tests in contracts/regression/ actually verify vs what requires the Phase 2 baseline |  | The verification plan claims tests exist but the baseline for cross-PR completeness comparison is deferred to Phase 2. Clarifying the actual scope of existing tests prevents misleading claims about verification coverage. | 2026-02-19 20:25:47 UTC |
| R4-F1 | Add observable per-stage graduation criteria for the progressive adoption path in REQ-PCG-016 |  | Endorsed by 1 reviewer. Without graduation criteria, the progressive adoption path is aspirational. Specifying minimum observation periods and confidence thresholds makes stage transitions verifiable and actionable. | 2026-02-19 20:25:47 UTC |
| R4-F2 | Rewrite REQ-PCG-027 requirement 6 to focus on validation outcomes rather than internal review architecture |  | Endorsed by 1 reviewer. Requirements should specify WHAT is validated, not the internal drafter/validator/reviewer implementation pattern. This is a legitimate separation of concerns that improves requirement longevity. | 2026-02-19 20:25:47 UTC |
| R4-F3 | Generalize BudgetPropagationSpec to support multiple budget types (time, tokens, cost) |  | Endorsed by 1 reviewer. The Artisan workflow uses LLM-based phases consuming tokens and a tiered cost model. A time-only budget spec cannot represent these real constraints. Generalizing to multiple budget units aligns the spec with actual pipeline economics. | 2026-02-19 20:25:47 UTC |
| R4-F4 | Clarify that 'MUST remain unchanged' in REQ-PCG-009 req 4 means API signatures/return types, while internal implementation MAY be extended |  | Endorsed by 1 reviewer. This directly supports R1-F2 and resolves ambiguity that would block implementers. The distinction between API compatibility and internal extensibility is critical for the domain wiring integration. | 2026-02-19 20:25:47 UTC |
| R4-F5 | Resolve NFR-PCG-005 idempotency conflict with REQ-PCG-001 context mutation by defining idempotency over original input state |  | This is a genuine logical conflict: if validation mutates context by applying defaults, a second run sees different input. The requirement must specify that idempotency is defined over original input, with mutations recorded and replayed deterministically. | 2026-02-19 20:25:47 UTC |
| R13-S1 | Define explicit contract versioning and migration strategy when schema_version changes from v1 to v2. | claude-4 (claude-opus-4-6) | REQ-PCG-017 mandates schema_version=v1 and REQ-PCG-018 requires validation against the correct version, but no requirement addresses version migration across two independent repos. Rolling deployments will inevitably hit version mismatches, and without a negotiation/deprecation strategy, this will cause hard-to-diagnose failures at the handoff boundary. | 2026-02-19 20:39:45 UTC |
| R13-S2 | Specify maximum allowable clock skew for provenance timestamp verification across the two pipeline halves. | claude-4 (claude-opus-4-6) | REQ-PCG-007 and REQ-PCG-004 rely on wall-clock timestamps for provenance and causal ordering, but the two pipeline halves can run on different hosts/CI runners. Without a clock skew tolerance, false-positive ordering violations and provenance chain breaks are inevitable. This aligns with the already-endorsed R14-S5 concern about logical clocks. | 2026-02-19 20:39:45 UTC |
| R13-S3 | Address eval() replacement timeline and interim hardening for NFR-PCG-004 verification expressions. | claude-4 (claude-opus-4-6) | Has 1 endorsement. NFR-PCG-004 acknowledges the eval() risk but provides no concrete mitigation timeline. REQ-PCG-016's progressive adoption path means the trust boundary erodes as more teams contribute contract YAML. A concrete requirement for an allowed expression grammar subset and a CI gate rejecting unsafe AST nodes is a practical interim hardening step. | 2026-02-19 20:39:45 UTC |
| R13-S4 | Require integration tests that exercise the full 8-stage pipeline end-to-end with contract enforcement active. | claude-4 (claude-opus-4-6) | The Verification Plan lists only per-component test suites but no end-to-end integration test spanning stages 0-7 with contracts active. The interaction between numerous accepted suggestions creates emergent behaviors only visible in integration. Unit test fixtures may diverge from real handoff artifacts. | 2026-02-19 20:39:45 UTC |
| R13-S5 | Clarify whether _cc_propagation survives serialization across the handoff boundary and in what format. | claude-4 (claude-opus-4-6) | REQ-PCG-014 requires provenance under _cc_propagation in the context dict, and REQ-PCG-024 specifies JSON/YAML handoff files, but no requirement specifies which file carries _cc_propagation or whether it's reconstructed on the startd8-sdk side. This ambiguity makes REQ-PCG-025's BoundaryValidator at the handoff boundary unimplementable consistently. | 2026-02-19 20:39:45 UTC |
| R13-S6 | Reconcile the severity model between ContextCore contracts (BLOCKING/WARNING/ADVISORY) and A2A gate results (blocking boolean + severity field). | claude-4 (claude-opus-4-6) | REQ-PCG-013 defines a three-tier severity model while REQ-PCG-023 defines a separate severity+blocking model. Without an explicit mapping, a WARNING propagation failure could inconsistently map to different GateResult combinations, undermining the reliability of gate decisions across the pipeline. | 2026-02-19 20:39:45 UTC |
| R13-S9 | Link each Part 4 extension concern to the specific core REQ-PCG-XXX requirements it depends on or extends. | claude-4 (claude-opus-4-6) | Part 4 lists 9 extension concerns with only a 'Related Domain' column but no traceability to specific requirements or their implementation status. This makes it impossible to assess whether extension concerns are blocked by incomplete core domain wiring (5 of 7 domains are status 'D'). Adding a dependency column is low-effort and high-value for planning. | 2026-02-19 20:39:45 UTC |
| R13-S10 | Require fault injection tests for the graceful degradation path where ContextCore is not installed. | claude-4 (claude-opus-4-6) | NFR-PCG-002 and REQ-PCG-025 require startd8-sdk to function without ContextCore, but the Verification Plan has no explicit test for this path. With 125+ accepted suggestions adding contract machinery, the degradation path has many untested code branches. A CI matrix job without ContextCore is a straightforward and valuable addition. | 2026-02-19 20:39:45 UTC |
| R14-S1 | Replace repr(value) with a canonical deterministic serialization for value_hash calculation. | gemini-3 (gemini-3-pro-preview) | repr() is not guaranteed to produce deterministic output for unordered collections (sets, dicts in older Python) or across Python implementations. REQ-PCG-007 and REQ-PCG-014 both specify sha256(repr(value))[:8] for provenance hashing. Using json.dumps(sort_keys=True) or equivalent deterministic serialization eliminates false-positive mutation signals. | 2026-02-19 20:39:45 UTC |
| R14-S2 | Add a sensitive boolean attribute to FieldSpec and enforce redaction of sensitive fields in OTel span events and logs. | gemini-3 (gemini-3-pro-preview) | The current design emits context values into observability backends for debugging (REQ-PCG-011). Without sensitivity tagging, secrets (API keys, tokens) flowing through the context will leak into traces and logs. This is a security concern that becomes more critical as adoption scales per REQ-PCG-016's progressive adoption path. | 2026-02-19 20:39:45 UTC |
| R14-S4 | Explicitly mandate fail-closed behavior for unhandled exceptions within Gate logic. | gemini-3 (gemini-3-pro-preview) | NFR-PCG-001 and NFR-PCG-005 address zero overhead and idempotency, but no requirement specifies behavior when gate logic itself crashes. Security governance requires that infrastructure errors treat the gate as Failed (fail-closed), not silently Passed. This is a critical reliability gap given that gates make blocking pipeline decisions. | 2026-02-19 20:39:45 UTC |
| R14-S5 | Use logical clocks or step counters instead of wall-clock timestamps for Causal Ordering Contracts. | gemini-3 (gemini-3-pro-preview) | This aligns with and reinforces R13-S2 (clock skew tolerance). REQ-PCG-004 relies on wall-clock timestamps for 'A before B' validation, but the two pipeline halves run on different nodes/containers. Logical clocks/step counters provide correct causal ordering regardless of clock skew, which is the theoretically sound approach per the Lamport reference in the document itself. | 2026-02-19 20:39:45 UTC |
| R1-F1 | Add a requirement defining the minimum required schema for run-provenance.json. |  | Without a defined schema, Gate 1's provenance cross-check is unverifiable — two implementations could define different schemas and both claim compliance. This is a genuine completeness gap that affects the already-accepted R6-S3 reconciliation check. | 2026-02-19 20:45:18 UTC |
| R1-F2 | Document frozen interface signatures for validate_phase_entry() and validate_phase_exit(). |  | REQ-PCG-009 req 4 says these MUST remain unchanged but doesn't define what unchanged means at the API level. Without documented signatures, the backward-compatibility constraint is unenforceable. This is directly actionable and low-cost. | 2026-02-19 20:45:18 UTC |
| R1-F3 | Add a requirement for a compatibility validation tool for the eval()-to-CEL expression migration. |  | The accepted R6-S1 CEL migration will break existing verification expressions unless there's a defined migration path. Capturing this as a requirement now prevents a foreseeable breaking change during the transition. | 2026-02-19 20:45:18 UTC |
| R1-F5 | Define partial phase success semantics for the Artisan 7-phase workflow. |  | Partial success is the most common real-world scenario and the current requirements only cover full success and full failure. Without defined behavior, implementations will diverge on how partial IMPLEMENT results flow through REVIEW and FINALIZE. | 2026-02-19 20:45:18 UTC |
| R3-F1 | Specify whether boundary span events are emitted per-boundary (summary) or per-field (detailed) to control cardinality. |  | High-cardinality span events can overwhelm OTel collectors. With 7 domains active, per-field emission could produce dozens of events per phase transition. This is an important operational concern that must be specified to ensure consistent implementation and manageable trace data. | 2026-02-19 20:45:18 UTC |
| R3-F2 | Specify dependency direction between ContextCore and startd8-sdk to prevent circular dependencies. |  | The bidirectional data flow (startd8-sdk imports from ContextCore, but ContextCore's loader consumes startd8-sdk's YAML) is a genuine architectural concern. Clarifying the dependency direction is essential for maintainability and independent buildability of both repos. | 2026-02-19 20:45:18 UTC |
| R3-F3 | Ensure error envelopes from boundary validation do not leak sensitive field values into logs. |  | This is a genuine security concern at the intersection of boundary enforcement error reporting and sensitive field handling. The fix is simple (include field path but not value for sensitive fields) and prevents a data leakage vector. Has 1 endorsement. | 2026-02-19 20:45:18 UTC |
| R3-F4 | Clarify what existing regression tests in contracts/regression/ actually verify versus the deferred cross-PR completeness comparison. |  | If the Verification Plan claims tests exist but they verify a different property than what REQ-PCG-012 requires, the plan is misleading. Clarifying the scope of existing tests is low-cost and prevents false confidence. | 2026-02-19 20:45:18 UTC |
| R4-F1 | Add observable per-stage graduation criteria to REQ-PCG-016's progressive adoption path. |  | Without defined criteria for stage transitions, progressive adoption is aspirational rather than actionable. This has 2 endorsements and addresses a real gap — teams need to know when they've satisfied conditions for moving from monitor to tighten. | 2026-02-19 20:45:18 UTC |
| R4-F2 | Rewrite REQ-PCG-027 requirement 6 to focus on validation outcomes rather than internal review architecture (drafter/validator/reviewer). |  | Requirements should specify WHAT must be validated, not HOW the validation is internally structured. The tiered cost model is an implementation detail that may change. Has 1 endorsement. | 2026-02-19 20:45:18 UTC |
| R4-F4 | Clarify that 'MUST remain unchanged' in REQ-PCG-009 req 4 means public API signatures and return types, while internal implementation may be extended. |  | This directly resolves the ambiguity identified in the already-accepted R1-F2 and provides the specific language needed. Has 2 endorsements via R4-F4. The proposed wording is precise and actionable. | 2026-02-19 20:45:18 UTC |
| R4-F5 | Define idempotency in NFR-PCG-005 as being over the original input state, with deterministic mutation replay. |  | The conflict between idempotent gate execution and WARNING defaults mutating context is a real semantic gap. Without clarification, re-running validation on mutated context produces different telemetry, violating idempotency expectations. | 2026-02-19 20:45:18 UTC |

#### Phase 1 Implementation Log (2026-02-19)

The following Appendix C suggestions were implemented in the document body and code as part of Phase 1 (Pipeline Contract Governance Plan):

**Task 1 — Document Corrections (33 suggestions applied):**

| Suggestion IDs | Category | What was implemented |
|----------------|----------|---------------------|
| R1-S1, R4-S1 | Factual fix | Gate 1 table updated from 7 to 8 checks; row 8 (artifact inventory) added; row 5 corrected to reference declared gaps; companion docs updated |
| R1-S2 | Factual fix | REQ-PCG-022 Gate 3 status marker added |
| R1-S4 | Factual fix | "byppassable" typo fixed; `--skip-preflight` bypass mechanism specified |
| R3-S3 | Factual fix | REQ-PCG-003 through REQ-PCG-007 status changed from "Implemented" to "Partial" |
| R4-S7 | Factual fix | Artifact filename standardized to `{project}-artifact-manifest.yaml` |
| R2-S8 | Factual fix | Pipeline diagram updated with Stage 2a (ANALYZE) / 2b (INIT) |
| R2-S5 | Factual fix | Fail-loud note for malformed run-provenance.json added to cross-cutting section |
| R1-S7 | Status/traceability | Promotion Criteria (D → Y → Y*) subsection added below matrix |
| R3-S9 | Status/traceability | Requirement-to-domain traceability table added |
| R3-S5, R2-S9 | Status/traceability | Source fields added to REQ-PCG-017 through REQ-PCG-027 |
| R1-S5, R3-S4 | Precision/testability | Test counts added to verification plan for REQ-PCG-008 (26), -009 (30), -010 (30), -022 (partial) |
| R1-S8 | Precision/testability | REQUIRED/OPTIONAL annotations added to REQ-PCG-024 onboarding metadata fields |
| R3-S1 | Precision/testability | Complexity score variance invariant defined in REQ-PCG-021 and REQ-PCG-026 |
| R3-S10 | Precision/testability | Qualitative acceptance criteria replaced with specific event names/severity values in REQ-PCG-006 and REQ-PCG-013 |
| R4-S8 | Precision/testability | REQ-PCG-022 clarified: checksums verify integrity, not reproducibility |
| R4-S3 | Precision/testability | Gate 2 Q2 updated to accept force_route override |
| R1-S3 | Architecture | REQ-PCG-033 added: pipeline resumption explicit non-goal |
| R4-S2 | Architecture | Degradable Propagation Contracts vs mandatory A2A Contracts distinction added to REQ-PCG-025 and NFR-PCG-002 |
| R4-S6 | Architecture | Default injection provenance stamping requirement added to REQ-PCG-013 |
| R4-S9 | Architecture | Stages 0-1 provenance seeding requirement added to REQ-PCG-014 |
| R2-S1 | Architecture | Gate 3 relationship to a2a-diagnose Q3 clarified in REQ-PCG-022 |
| R2-S3 | Architecture | Complete handoff artifact set defined in REQ-PCG-024 (3 core + glob) |
| R2-S2 | Architecture | E2E runtime environment note added as REQ-PCG-024 requirement 6 |
| R1-S6, R3-S6 | Security | NFR-PCG-004 expanded with full AST allowlist specification |
| R2-S4 | New requirement | REQ-PCG-034 added: generic failure injection mechanism |
| R1-S9 | New requirement | Gap exclusion via `excluded_gaps` added to REQ-PCG-026 |
| R1-S10 | New requirement | REQ-PCG-035 added: schema versioning placeholder (deferred to Phase 2) |

**Task 2 — Implementation Status Matrix:**
- 5 domains updated from D to Y* with legend
- Gate 3 row added to A2A governance table
- Promotion criteria subsection added

**Task 3 — eval() Sandbox Hardening (NFR-PCG-004):**
- `_validate_expression()` AST allowlist added to `contracts/propagation/schema.py`
- `@field_validator("verification")` added to `PropagationChainSpec`
- 1-second SIGALRM timeout wrapper added to `tracker.py` eval() call
- 19 new tests in `test_expression_safety.py` (all pass)

**Task 4 — Companion Document Updates:**
- `REQ_CAPABILITY_DELIVERY_PIPELINE.md`: Gate 1 description updated to 8 checks; filename pattern fixed
- `MANIFEST_EXPORT_REQUIREMENTS.md`: All gate count references updated from 6 to 8

**Task 5 — Mottainai Violation Coverage (R15):**

Applied R15-S1 through R15-S8 from Review Round R15 (Mottainai Violation Coverage). All 8 suggestions target completeness.

| ID | Category | Applied Change |
|----|----------|---------------|
| R15-S1 | Handoff enrichment | REQ-PCG-024 requirements 8–9: enrichment field propagation contract, provenance recording |
| R15-S2 | EMIT bridging | REQ-PCG-026 requirements 6–7: EMIT bridges onboarding from export dir to seed; WARNING on absent file |
| R15-S3 | Consumer-side | REQ-PCG-027 requirements 8–10: adopt-prior designs, enrichment consumption (AR cross-refs), IMPLEMENT reuse |
| R15-S4 | Resumption scope | REQ-PCG-033 refined: ContextCore non-goal, startd8-sdk contractor-level resume MUST (multi-format detection, artifact preservation, cost attribution) |
| R15-S5 | New requirement | REQ-PCG-036: Onboarding Enrichment End-to-End Propagation (P1, 7 requirements) |
| R15-S6 | New requirement | REQ-PCG-037: Contractor Resume and Artifact Preservation (P1, 6 requirements) |
| R15-S7 | New requirement | REQ-PCG-038: Prime Contractor Context Parity (P2, 6 requirements) |
| R15-S8 | New requirement | REQ-PCG-039: Source Artifact Type Coverage (P2, 6 requirements) |

**Traceability: Every Mottainai Violation Covered**

| Violation | Existing REQ | New REQ | AR Cross-ref |
|-----------|-------------|---------|-------------|
| F1: batch result mismatch | REQ-PCG-033 (2.a) | REQ-PCG-037 (1) | — |
| F2: adopted design rejection | REQ-PCG-027 (8) | REQ-PCG-037 (2) | AR-122 |
| F3: onboarding not bridged | REQ-PCG-024 (8–9), -026 (6–7) | REQ-PCG-036 | — |
| G1–G7: enrichment not forwarded | REQ-PCG-027 (9) | REQ-PCG-036 (2,4) | AR-303–308 (5 of 7) |
| G8: TRANSFORM plan not read | REQ-PCG-027 (9) | REQ-PCG-036 (7) | — |
| G9: enrichment dropped at queue | — | REQ-PCG-038 (1) | — |
| G10: onboarding not in prime ctx | — | REQ-PCG-038 (2) | — |
| G11: no arch context for prime | — | REQ-PCG-038 (3) | — |
| G12: no calibration for prime | — | REQ-PCG-038 (4) | — |
| G13: REFINE not forwarded to prime | — | REQ-PCG-038 (5) | — |
| G14: no gen result caching | — | REQ-PCG-037 (4) | — |
| G15: source types not registered | — | REQ-PCG-039 | — |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-S6 | Add requirements for managing contract schema evolution and versioning. | gemini-2.5 (gemini-2.5-pro) | This is a duplicate of R1-S10 which already covers the same gap (schema_version='v1' with no versioning/migration strategy). Accepting both would create redundant requirements. R1-S10 is sufficient. | 2026-02-19 17:46:51 UTC |
| R2-S7 | Add a requirement for a CI linter to statically analyze verification_expressions in contract YAML for safety. | gemini-2.5 (gemini-2.5-pro) | This is a duplicate of R1-S6 which already covers parse-time validation of verification expressions against an allowlist of safe operations. R1-S6's broader framing (parse-time allowlist constraint) subsumes a CI linter requirement. Accepting both would create redundant requirements. | 2026-02-19 17:46:51 UTC |
| R2-S10 | Define requirements for contract-driven automated remediation actions linked to gate failures. | gemini-2.5 (gemini-2.5-pro) | This is a significant scope expansion that introduces a closed-loop auto-remediation system. The current pipeline already has a Stage 1.5 FIX stage for auto-remedy and REQ-PCG-023 provides next_action guidance for operators. Automated remediation tied to gate results is better suited as an extension concern (similar to the Part 4 extensions) rather than a core governance requirement at this stage. | 2026-02-19 17:46:51 UTC |
| R4-S4 | Add requirements to propagate financial (USD) budget via BudgetPropagationSpec or a new domain. | gemini-3 (gemini-3-pro-preview) | While the observation about financial budget propagation is valid, this is a new feature requirement rather than a gap in the existing requirements document. The companion REQ_CAPABILITY_DELIVERY_PIPELINE.md handles cost budget at the pipeline orchestration level. Adding a new propagation domain is a scope expansion that belongs in Part 4 (Extension Concerns) or a separate requirements document, not in the current triage of governance requirements. | 2026-02-19 18:32:33 UTC |
| R4-S5 | Replace eval() with a restricted expression parser (e.g., simpleeval) immediately in NFR-PCG-004. | gemini-3 (gemini-3-pro-preview) | This is an implementation recommendation, not a requirements clarification. R3-S6 (already accepted) addresses the same concern at the requirements level by specifying concrete sandbox constraints. NFR-PCG-004 already states 'the eval() mechanism MUST be replaced with a safe expression evaluator' if untrusted sources are involved. Mandating a specific library choice (simpleeval) or timing ('immediately') is an implementation decision, not a requirements gap. | 2026-02-19 18:32:33 UTC |
| R6-S2 | Relax extra="forbid" for Handoff Contracts or mandate strict Semantic Versioning negotiation. | gemini-3 (gemini-3-pro-preview) | This substantially overlaps with R5-S1 (already accepted), which addresses the same versioning and forward-compatibility concern for extra="forbid". R5-S1's framing (define a versioning and migration strategy) is more comprehensive and allows for multiple solutions including version negotiation, whereas R6-S2 prescribes a specific solution (relax extra="forbid") that may conflict with the strict schema enforcement rationale already accepted in prior rounds. | 2026-02-19 19:02:22 UTC |
| R6-S7 | Add a size threshold or trusted cache mechanism for checksum recomputation on large artifacts. | gemini-3 (gemini-3-pro-preview) | This is a low-severity optimization concern. REQ-PCG-019's requirement to recompute checksums from files is a core security property of the checksum chain. Introducing a cache or size threshold weakens this guarantee. The current pipeline's artifact types (YAML, JSON, monitoring configs) are small; multi-GB artifacts like ML models are not in scope for this pipeline. If they become relevant, this can be addressed as an extension concern rather than modifying a core integrity requirement. | 2026-02-19 19:02:22 UTC |
| R1-F4 | Add replay attack protection (nonce/timestamp) to boundary payload validation in REQ-PCG-018. |  | This is a valid security concern in general, but the pipeline operates within a single execution context where payloads are generated and consumed in the same process or orchestrated run. The file-based handoff already recomputes checksums from disk (REQ-PCG-019), and in-memory validation occurs within a single pipeline execution. Adding replay protection adds complexity without addressing a realistic threat model for this system's trust boundaries. If the threat model evolves, this can be revisited. | 2026-02-19 19:09:57 UTC |
| R1-F7 | Specify default threshold values and evaluation windows for alerting rules in REQ-PCG-011. |  | While operationally useful, alerting thresholds are deployment-specific configuration, not requirements-level concerns. The requirement correctly mandates that alerting rules exist; specific thresholds belong in operational runbooks or configuration documentation. Over-specifying deployment parameters in requirements creates unnecessary rigidity. | 2026-02-19 19:09:57 UTC |
| R8-S1 | Replace repr(value) with canonical serialization for provenance hashing in REQ-PCG-014. | gemini-3 (gemini-3-pro-preview) | This is a duplicate of R7-S5 which has already been accepted above. Both identify the same repr() non-determinism issue in REQ-PCG-014. Accepting both would create redundant requirements. | 2026-02-19 19:19:51 UTC |
| R1-F4 | Add replay protection (nonce/timestamp) for boundary validation payloads in REQ-PCG-018. |  | This is an in-process validation system, not a network protocol. Boundary payloads are constructed and consumed within the same pipeline run. REQ-PCG-019's checksum recomputation from files already provides freshness for file-based handoffs. Adding replay protection to in-memory validation adds complexity without addressing a realistic attack vector in the current architecture. | 2026-02-19 19:28:23 UTC |
| R1-F6 | Specify the version constraint strategy for the ContextCore dependency in startd8-sdk. |  | Schema versioning strategy is already deferred to Phase 2 (REQ-PCG-035/R1-S10). Adding a version constraint requirement now, before the versioning strategy is designed, would be premature and could conflict with the Phase 2 design decisions. | 2026-02-19 19:28:23 UTC |
| R1-F7 | Specify default threshold values and evaluation windows for alerting rules in REQ-PCG-011. |  | Alerting thresholds are deployment-specific operational parameters, not architectural requirements. The requirement correctly specifies that alerts must exist and fire on the named conditions. Hardcoding specific thresholds (90%, 5-minute window) in a requirements document would be premature — these should be configurable defaults defined during deployment, not in the architecture spec. | 2026-02-19 19:28:23 UTC |
| R3-F5 | Add a requirement for a span-event-to-contract-field promotion pattern in REQ-PCG-030. |  | This is a process/lifecycle concern about how the contract schema evolves over time, not an architectural requirement. The standard PR review process already governs contract changes. Formalizing a promotion pattern for a scenario that hasn't yet occurred is premature and adds unnecessary process overhead. | 2026-02-19 19:28:23 UTC |
| R9-S7 | Add explicit source-to-requirement traceability from each REQ-PCG to its source document section. | claude-4 (claude-opus-4-6) | While source traceability is valuable in general, the document already lists the 5 source documents in the header and groups requirements by their derivation context (Part 1 from ContextCore sources, Part 2 from A2A sources). Adding per-requirement Source: fields to 32+ requirements is a significant documentation burden with limited practical value given the document already consolidates these sources. Inter-requirement tracing (already accepted via R1-S7, R2-S9) provides more actionable traceability. | 2026-02-19 19:41:04 UTC |
| R9-S9 | Define retry and recovery semantics for transient gate failures with exponential backoff and error classification. | claude-4 (claude-opus-4-6) | NFR-PCG-005 requires idempotent gate execution, which enables safe retry, but retry policy is an operational/infrastructure concern better handled by the pipeline orchestrator (covered in the companion REQ_CAPABILITY_DELIVERY_PIPELINE.md). Adding retry semantics, backoff strategies, and error_class fields to gate contracts conflates infrastructure concerns with contract governance. This level of detail is more appropriate for the orchestration document. | 2026-02-19 19:41:04 UTC |
| R10-S3 | Define budget propagation semantics for parallel execution branches in REQ-PCG-006. | gemini-3 (gemini-3-pro-preview) | The pipeline overview shows a sequential stage model (0→1→1.5→2→3→4→5→6→7), and REQ-PCG-006 tracks per-phase budget allocations in this sequential context. Parallel execution within phases is not part of the current pipeline architecture. Specifying parallel budget semantics for a scenario that doesn't exist in the current design is premature and adds complexity without addressing a real gap. | 2026-02-19 19:41:04 UTC |
| R10-S6 | Add execution timeout/resource limits to NFR-PCG-004 verification expression safety. | gemini-3 (gemini-3-pro-preview) | This is substantially duplicative of R8-S2 (already accepted), which addresses the same eval() resource exhaustion concern and proposes replacing eval() with a restricted expression parser. If eval() is replaced with an AST-whitelist or simpleeval as R8-S2 suggests, CPU exhaustion via complex expressions is addressed at the parser level, making separate timeout requirements redundant. | 2026-02-19 19:41:04 UTC |
| R1-F3 | Add a backward compatibility requirement for eval()-to-CEL expression migration |  | CEL migration (R6-S1) is a future direction, not a current Phase 1 task. Adding migration tooling requirements now is premature — the CEL evaluator itself hasn't been designed yet. This should be addressed when the CEL migration is actually planned. | 2026-02-19 19:49:46 UTC |
| R1-F4 | Add replay attack protection (nonce/timestamp) for boundary validation payloads |  | This is an in-process governance system, not a networked protocol. Boundary validation operates on in-memory context dicts within a single pipeline run. The threat model of capturing and replaying payloads doesn't apply to this architecture — REQ-PCG-019's checksum recomputation already handles file-based freshness. | 2026-02-19 19:49:46 UTC |
| R1-F6 | Specify the version constraint strategy for the ContextCore dependency in startd8-sdk |  | This is an operational packaging concern that belongs in a dependency management policy, not in a requirements document. The accepted R1-S10 already defers schema versioning to Phase 2, and version constraint strategy is part of that deferred work. | 2026-02-19 19:49:46 UTC |
| R1-F7 | Specify default alerting thresholds and evaluation windows for ContextPropagationDegraded and ContextChainBroken |  | Alerting thresholds are deployment-specific operational parameters. The requirement correctly specifies WHAT to alert on; the specific thresholds should be configurable and documented in an operations guide, not hardcoded in requirements. | 2026-02-19 19:49:46 UTC |
| R3-F5 | Define a span-event-to-contract-field promotion pattern in REQ-PCG-030 |  | This is a process governance concern about how contract changes are managed over time. The existing PR review process is sufficient — adding a formal promotion pattern for a speculative future need adds unnecessary complexity to the requirements. | 2026-02-19 19:49:46 UTC |
| R11-S2 | Specify maximum acceptable latency budget for cumulative contract validation across all phase boundaries. | claude-4 (claude-opus-4-6) | While a valid performance concern, this is a premature optimization requirement. NFR-PCG-001 already covers the zero-contract case. The with-contracts path is opt-in and the overhead is implementation-dependent. Performance budgets should be established through benchmarking during implementation, not as upfront requirements at this stage. Adding a speculative latency number provides no real value. | 2026-02-19 20:20:04 UTC |
| R11-S3 | Add requirements for contract validation behavior under concurrent/parallel pipeline execution. | claude-4 (claude-opus-4-6) | REQ-PCG-004 explicitly states 'phase-sequential execution model enforces ordering within a pipeline.' The document assumes sequential execution by design. Speculating about future parallelism introduces scope creep. If parallelism is introduced later, isolation requirements should be added at that time. The mutable `_cc_propagation` dict is scoped per-pipeline-run, and concurrent runs would naturally have separate context dicts. | 2026-02-19 20:20:04 UTC |
| R11-S7 | Add bidirectional traceability between Part 4 extension concerns and core REQ-PCG requirements. | claude-4 (claude-opus-4-6) | Part 4 explicitly states these are 'Designed, Not Yet Implemented' and 'out of scope for this document but referenced for completeness.' Adding detailed traceability links to out-of-scope extension concerns is premature. When these extensions are implemented, their own requirements documents should reference the core requirements they depend on. | 2026-02-19 20:20:04 UTC |
| R11-S9 | Address clock skew implications for ISO 8601 timestamps in provenance and budget tracking across ContextCore and startd8-sdk. | claude-4 (claude-opus-4-6) | The handoff between ContextCore and startd8-sdk is file-based (artifact-manifest.yaml, onboarding-metadata.json, run-provenance.json), not a real-time distributed system call. Timestamps are recorded sequentially within each half. Budget tracking (REQ-PCG-006) is per-phase within a single execution context. The two-repo split doesn't imply distributed clock coordination — it implies sequential file production and consumption. This concern is architecturally misplaced. | 2026-02-19 20:20:04 UTC |
| R12-S2 | Require W3C traceparent propagation in HandoffContract and TaskSpanContract to link ContextCore and startd8-sdk traces. | gemini-3 (gemini-3-pro-preview) | The handoff between ContextCore and startd8-sdk is file-based (YAML/JSON artifacts), not a synchronous request-response pattern. W3C traceparent is designed for HTTP/gRPC propagation. The document already has OTel span event requirements (REQ-PCG-031) and provenance tracking (REQ-PCG-014). Trace correlation can be achieved through project_id/task_id already present in the contracts. Adding W3C traceparent to file-based handoffs conflates two different observability patterns. | 2026-02-19 20:20:04 UTC |
| R12-S8 | Define a strategy for emitting `_cc_propagation` data to OTel to avoid attribute size limits. | gemini-3 (gemini-3-pro-preview) | This is a low-severity implementation detail. The pipeline has a bounded number of phases (7 for Artisan) and fields, so `_cc_propagation` growth is naturally bounded. OTel attribute size limits are backend-specific and can be handled at the implementation level. REQ-PCG-031 already governs span event schema. Adding truncation requirements prematurely constrains implementation without evidence of an actual size problem. | 2026-02-19 20:20:04 UTC |
| R1-F4 | Add replay attack protection (nonce/timestamp) for boundary validation payloads |  | This is an in-process validation system, not a network protocol. Boundary validation operates on the current context dict in memory within a single pipeline run. Replay attacks are not a realistic threat model here — an attacker with the ability to inject payloads into the in-memory context already has full process control. REQ-PCG-019's file-based freshness checks are sufficient for the actual threat surface. | 2026-02-19 20:25:47 UTC |
| R1-F6 | Specify version constraint strategy for ContextCore dependency in startd8-sdk |  | This is a package management operational concern, not a requirements-level specification. The accepted R1-S10/R5-S1 versioning strategy placeholder already covers this space. Specifying pip version constraints in a requirements doc is too prescriptive and belongs in dependency management documentation. | 2026-02-19 20:25:47 UTC |
| R1-F7 | Specify default threshold values and evaluation windows for alerting rules |  | Alerting thresholds are inherently deployment-specific and should be configurable, not hardcoded in a requirements document. The requirement correctly specifies WHAT to alert on; the specific thresholds belong in operational configuration documentation or deployment guides. | 2026-02-19 20:25:47 UTC |
| R3-F5 | Add a span-event-to-contract-field promotion pattern requirement |  | This is a process/governance concern about how contract fields get added over time, not a technical requirement. The existing PR review process already covers adding new contract fields. Formalizing a 'promotion pattern' adds procedural overhead without clear technical benefit at this stage of maturity. | 2026-02-19 20:25:47 UTC |
| R13-S7 | Specify behavior when multiple propagation chains conflict about the same field's status. | claude-4 (claude-opus-4-6) | While theoretically valid, the current implementation has only 2 fully integrated domains (Context Propagation and Schema Compatibility) and the scenario of conflicting chains for the same field is an edge case that would add complexity without clear immediate benefit. The completeness_pct computation is already defined as a chain-level metric in REQ-PCG-010. This can be addressed when more domains are lifecycle-integrated. | 2026-02-19 20:39:45 UTC |
| R13-S8 | Address contract YAML file size and loading performance as contract domains scale from 2 to 7+. | claude-4 (claude-opus-4-6) | Five of seven domains are at status 'D' (lifecycle wiring pending). Specifying a performance budget now is premature optimization — the actual overhead depends on implementation details that don't yet exist. NFR-PCG-001 already covers the zero-overhead case when contracts are disabled, and performance benchmarking is better done empirically once domains are wired in. | 2026-02-19 20:39:45 UTC |
| R14-S3 | Define provenance behavior for iterative loops (Stage 1.5 Fix -> Stage 1 Polish) with iteration counters or history lists. | gemini-3 (gemini-3-pro-preview) | The pipeline overview shows Fix (Stage 1.5) as a single auto-remedy pass, not an iterative loop. Adding iteration counters/history lists for a scenario that isn't clearly part of the current pipeline design adds complexity without demonstrated need. The existing single-slot provenance with latest-wins semantics is adequate for the current linear pipeline model. | 2026-02-19 20:39:45 UTC |
| R14-S6 | Require FieldProvenance to explicitly flag values injected via defaults versus values set by handlers. | gemini-3 (gemini-3-pro-preview) | REQ-PCG-001 requirement 4 already specifies that WARNING fields with defaults emit a DEFAULTED status, and REQ-PCG-013 requirement 3 documents default injection behavior. The provenance origin_phase plus the DEFAULTED status already provide sufficient information to distinguish defaulted values. Adding another boolean field is redundant with existing status signals. | 2026-02-19 20:39:45 UTC |
| R1-F4 | Add replay protection (nonce/timestamp) for boundary validation payloads. |  | This is an in-process validation system, not a network protocol. Boundary validation operates on in-memory data structures within a single pipeline run. The threat model of capturing and replaying valid payloads is not realistic for this architecture — REQ-PCG-019's checksum recomputation from files already addresses the file-based case. Adding replay protection adds complexity without meaningful security benefit. | 2026-02-19 20:45:18 UTC |
| R1-F6 | Specify the version constraint strategy for the ContextCore dependency in startd8-sdk. |  | This is an operational/packaging concern rather than a requirements-level concern. The accepted R5-S1 versioning strategy and R1-S10 schema versioning placeholder already cover the design space. Specifying pip version constraints in a requirements document is overly prescriptive — this belongs in the implementation/packaging documentation. | 2026-02-19 20:45:18 UTC |
| R1-F7 | Specify default thresholds and evaluation windows for alerting rules in REQ-PCG-011. |  | Alerting thresholds are inherently deployment-specific and belong in operational configuration, not in a requirements document. The requirement correctly specifies that alerts must fire for the named conditions; the specific thresholds should be configurable defaults defined in implementation, not locked into requirements. | 2026-02-19 20:45:18 UTC |
| R3-F5 | Define a pattern for promoting span events to contract fields when they carry boundary-decision data. |  | This is a speculative future concern. REQ-PCG-030 already distinguishes contract objects from span events. Adding a formal promotion pattern before there's evidence of the need is premature. The standard PR review process is sufficient for adding new contract fields when the need arises. | 2026-02-19 20:45:18 UTC |
| R4-F3 | Generalize BudgetPropagationSpec to support multiple budget types (time, tokens, cost). |  | This is a feature enhancement that significantly expands scope. The current time-based budget tracking is a well-defined domain. Adding token and cost budgets requires substantial design work and is better addressed as a future extension rather than a Phase 1 correction. | 2026-02-19 20:45:18 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 17:44:07 UTC
- **Scope**: Review requirements for completeness, consistency, testability, and traceability across the ContextCore/startd8-sdk pipeline split.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | consistency | critical | Gate 1 check count is inconsistent: REQ-PCG-020 says "7 integrity checks" in the heading but the table lists 7 checks (1-7). However, the companion REQ_CAPABILITY_DELIVERY_PIPELINE.md (REQ-CDP-011, Gate 1 description) says "6 structural integrity checks (checksums, provenance, gap parity)". Reconcile to a single authoritative count. | Downstream implementers and test authors will not know whether to expect 6 or 7 gate results. The discrepancy between the two documents could cause Gate 1 tests to pass in one repo and fail in the other. | REQ-PCG-020 table and REQ_CAPABILITY_DELIVERY_PIPELINE.md Gate table (both need alignment) | Cross-document grep for "Gate 1" check counts; integration test asserts exact gate result count matches spec |
| R1-S2 | completeness | high | REQ-PCG-022 (Gate 3) has no implementation status marker, unlike Gates 1 and 2 which are marked "Implemented". Add explicit status and test count, or mark as "Not yet implemented" with a tracking note. | Every other gate requirement (REQ-PCG-020, REQ-PCG-021) declares implementation status and test counts. Gate 3's omission makes it unclear whether it's implemented, partially implemented, or planned. This affects the Implementation Status Matrix accuracy. | REQ-PCG-022 status line (add after "Priority: P1") | Verify status marker is present; cross-check with Implementation Status Matrix |
| R1-S3 | completeness | high | No requirement governs error recovery or partial-run resumption. If Stage 2 (INIT) fails after Stage 1 (POLISH) succeeds, the operator must re-run the entire pipeline from Stage 0. Add a requirement (or explicit non-goal) for checkpoint-based resumption within the ContextCore half. | REQ_CAPABILITY_DELIVERY_PIPELINE.md REQ-CDP-008 orchestrates stages 0–4 sequentially but provides no `--resume-from` mechanism. NFR-CDP-002 (idempotent re-runs) mitigates but doesn't eliminate wasted work. The extension concern "Checkpoint Recovery" (Concern 10) is listed as out-of-scope but the gap exists in the core pipeline too. | Section 3 (Cross-Cutting Requirements), as a new REQ-PCG-033 or as an explicit non-goal in Scope | Review whether `--resume-from STAGE` is feasible given NFR-CDP-003 (stage isolation) |
| R1-S4 | ambiguity | high | REQ-PCG-008 requirement 3 says pre-flight "MUST be bypassable" but uses a typo ("byppassable") and does not specify the mechanism. Meanwhile REQ-CDP-008 defines `--skip-polish` and `--skip-validate` bypass flags. Clarify whether pre-flight bypass uses the same flags, a separate `--skip-preflight` flag, or a config setting. | An implementer reading only this document cannot determine how to bypass pre-flight validation. The typo further reduces confidence in the precision of the requirement. | REQ-PCG-008 requirement 3 — specify the bypass mechanism and fix the typo | Code review: verify bypass flag exists and matches spec |
| R1-S5 | testability | high | Verification plan entries for REQ-PCG-008 through REQ-PCG-010 reference test directories (e.g., "Tests in `contracts/preflight/`") without specific test names or counts. All other domain requirements (REQ-PCG-001 through REQ-PCG-007) include test counts. Add counts or named test suites. | Without test counts or names, there is no way to verify coverage completeness during CI. A directory reference is insufficient — the directory could be empty and the verification plan would still appear satisfied. | Verification Plan table, rows for REQ-PCG-008 through REQ-PCG-010 | CI check: assert test count per directory >= expected minimum |
| R1-S6 | consistency | high | NFR-PCG-004 acknowledges `eval()` risk in verification expressions but defers mitigation to "if contract YAML ever comes from untrusted sources." REQ-PCG-015 requires `extra="forbid"` for unknown keys but does not address expression injection. Add an explicit constraint: verification expressions MUST be validated against an allowlist of safe operations at parse time, not just at eval time. | Defense-in-depth is a core principle of this document. Relying solely on trusted-source assumptions for `eval()` safety contradicts the document's own philosophy. A parse-time allowlist would catch malicious expressions before they reach the sandbox. | NFR-PCG-004 — add a sub-requirement for parse-time expression validation | Unit test: contract YAML with `__import__` or `os.system` in verification expression is rejected at parse time |
| R1-S7 | traceability | medium | The Implementation Status Matrix shows 5 domains (Semantic Conventions through Data Lineage) at status "D" (domain logic implemented, lifecycle wiring pending) across all lifecycle stages. No requirements or timeline exist for promoting these from D to Y. Add traceability: which requirements block the promotion, and what is the acceptance criterion for "Y"? | Without promotion criteria, the matrix becomes a permanent snapshot rather than a tracking tool. Stakeholders cannot distinguish "D since last week" from "D for six months with no plan." | Below the Implementation Status Matrix, add a "Promotion Criteria" subsection | Review: each "D" cell has a linked issue or requirement for lifecycle wiring |
| R1-S8 | completeness | medium | REQ-PCG-024 requirement 3 lists onboarding metadata fields in two groups (core and enrichment) but does not specify which fields are REQUIRED vs OPTIONAL. Gate 1 (REQ-PCG-020) checks "structural integrity (required fields)" but the required-field list is not defined here. | An implementer cannot determine which missing enrichment fields should cause Gate 1 failure vs. a warning. This creates ambiguity in gate behavior and test design. | REQ-PCG-024 requirement 3 — annotate each field as REQUIRED or OPTIONAL (or reference the schema that does) | Unit test: Gate 1 with missing REQUIRED field fails; Gate 1 with missing OPTIONAL field warns |
| R1-S9 | feasibility | medium | REQ-PCG-026 acceptance criterion states "parse coverage = 100%" — every gap becomes a feature. In practice, some gaps may be intentionally excluded (e.g., already-covered, out-of-scope). There is no mechanism for declaring intentional exclusions. | A 100% coverage requirement with no exclusion mechanism will cause false Gate 2 failures when operators intentionally skip certain gaps. REQ-CDP-011 supports `--task-filter TASK_IDS` which implies selective execution, but the parse stage has no corresponding filter. | REQ-PCG-026 — add a requirement for gap exclusion declarations (e.g., `excluded_gaps` in the artifact manifest) with audit trail | Integration test: pipeline with excluded gaps passes Gate 2 when exclusions are declared |
| R1-S10 | consistency | medium | REQ-PCG-017 says all models MUST enforce `schema_version = "v1"`. REQ-PCG-015 references `ContextContract` with `schema_version` in the YAML. There is no versioning strategy defined: what happens when a breaking change requires `v2`? How do consumers handle mixed versions during rollout? | Without a versioning/migration strategy, the first breaking schema change will either require a flag day (all producers and consumers upgrade simultaneously) or produce silent validation failures. This is especially risky across the ContextCore/startd8-sdk boundary. | After REQ-PCG-017 or in a new cross-cutting requirement — define version negotiation rules (reject unknown versions, support N and N-1, or document the constraint) | Review: schema version bump scenario is tested with both old and new payloads |

#### Review Round R2
**Reviewer**: gemini-2.5 (gemini-2.5-pro)
**Date**: 2026-02-19 17:45:03 UTC
**Scope**: Review requirements for completeness, consistency, testability, and traceability across the ContextCore/startd8-sdk pipeline split.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| --- | --- | --- | --- | --- | --- | --- |
| R2-S1 | consistency | high | Clarify the role and command for Gate 3. REQ-CDP-011 specifies `a2a-diagnose` for Gate 3, but REQ-PCG-021 defines this tool as the "Three Questions" diagnostic for Gate 2. | The current requirements are confusing. It's unclear if Gate 3 is a full re-run of the diagnostic or just the "Q3" portion. This ambiguity affects operator understanding and script implementation. Citing the "A2A Communications Design" lesson of precise gate definitions is relevant here. | REQ-PCG-022 (Gate 3) and REQ-CDP-011 (orchestration script). | The requirement text for Gate 3 should explicitly name the command used (`a2a-diagnose`) and clarify that it is executing the "Question 3" checks against the contractor outputs. |
| R2-S2 | feasibility | medium | Define the runtime environment and dependency management strategy for the E2E orchestration script. | REQ-CDP-012 places `run-cap-delivery-e2e.sh` in the ContextCore repo but requires startd8-sdk to be installed. This creates a tight coupling and risks dependency conflicts. The requirement should specify how a stable, shared environment is achieved (e.g., containerization, documented venv setup). | Add a new NFR to REQ_CAPABILITY_DELIVERY_PIPELINE.md. | An integration test runs the E2E script in a clean environment built according to the specified dependency management strategy, proving it can resolve dependencies from both codebases. |
| R2-S3 | ambiguity | medium | Explicitly define the complete set of artifacts that constitute the handoff contract consumed by stages 5-7. | REQ-PCG-024 and the CDP handoff table list three key files, but the directory listing in REQ-CDP-007 shows many more. It's unclear if files like `plan-analysis.json` are part of the contract. An incomplete contract definition risks downstream stages failing on missing inputs. | REQ-PCG-024 and the "Handoff contract" section in REQ_CAPABILITY_DELIVERY_PIPELINE.md. | The requirement should be updated with a definitive list or glob pattern of all files consumed by `run-cap-delivery-stages5-7.sh`. The Gate 1 preflight check should verify the presence of all specified files. |
| R2-S4 | testability | high | Add a requirement for a generic failure injection mechanism to test all major contract types and gates. | REQ-PCG-019 specifies failure injection for checksums, but not for other critical contracts (e.g., propagation, schema, ordering). Without this, testing the observability and alerting requirements (REQ-PCG-011, REQ-PCG-028) is difficult and likely to be manual. | Add a new requirement to "Part 3: Cross-Cutting Requirements" in `REQ_PIPELINE_CONTRACT_GOVERNANCE.md`. | Integration tests demonstrate injecting a `DEGRADED` propagation status or a `BLOCKING` Gate 2 failure, and then verify that the correct OTel events, dashboard panels, and alerts are triggered. |
| R2-S5 | consistency | high | Change the behavior for malformed `run-provenance.json` from "silently ignored" to "fail loudly". | REQ-CDP-006's "silently ignored" clause contradicts the "Fail Loud, Fail Early" principle of REQ-PCG-023. Silently ignoring a corrupt provenance file can hide fundamental pipeline setup errors and break the chain of custody. | REQ-CDP-006. | An integration test that runs `contextcore manifest export` with a deliberately corrupted `run-provenance.json` in the output directory should cause a non-zero exit code and a clear error message. |
| R2-S6 | completeness | high | Add requirements for managing contract schema evolution and versioning. | The documents specify `schema_version = "v1"` (REQ-PCG-017) but lack a strategy for handling schema changes (e.g., to "v2"). This is a critical omission for long-term maintainability, as it leaves the process for introducing breaking changes undefined. | Add a new section to "Part 3: Cross-Cutting Requirements" in `REQ_PIPELINE_CONTRACT_GOVERNANCE.md`. | The new requirement defines a process, such as requiring a temporary compatibility layer or a coordinated flag-day migration, for introducing a new contract version. |
| R2-S7 | completeness | medium | Add a requirement for a CI linter to statically analyze `verification_expressions` in contract YAML for safety. | NFR-PCG-004 correctly identifies the security risk of using `eval()` but relies on process (trusted sources). A technical control, like a CI check that flags potentially unsafe expressions, would provide stronger defense-in-depth, aligning with the project's security posture. | Add a new requirement under REQ-PCG-012 (Regression Detection). | A CI job is created that scans `.contract.yaml` files and fails if it finds expressions that use disallowed built-ins or import statements. |
| R2-S8 | consistency | low | Synchronize the pipeline diagrams with the two-step implementation of Stage 2 (Analyze and Init). | REQ-CDP-008 details Stage 2 as two distinct commands (`analyze-plan` and `init-from-plan`), but the diagrams in both documents show it as a single "INIT-FROM-PLAN" stage. This inconsistency creates a small but unnecessary point of confusion for anyone trying to map the diagram to the implementation. | Update the diagrams in both `REQ_CAPABILITY_DELIVERY_PIPELINE.md` and `REQ_PIPELINE_CONTRACT_GOVERNANCE.md`. | The pipeline diagrams are updated to show "Stage 2a: ANALYZE" and "Stage 2b: INIT" as distinct sub-steps within Stage 2. |
| R2-S9 | traceability | low | Add a "Source" field to each requirement in the PCG document to trace it back to the original design document. | The PCG document's value is that it consolidates five source documents. Adding direct traceability (e.g., `Source: CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md, Sec 3.1`) would make it much easier for future contributors to find the deeper context and rationale behind a specific requirement. | Add a `Source` field to the metadata block of each `REQ-PCG-*` requirement. | A spot-check of 5 requirements confirms the `Source` field correctly points to the relevant section in one of the five consolidated design documents. |
| R2-S10 | completeness | medium | Define requirements for contract-driven automated remediation actions. | The pipeline includes a `fix` stage and gate failures produce a `next_action` (REQ-PCG-023), but there is no mechanism to link them. A requirement for a "remediation contract" could define machine-executable actions for specific `GateResult` failures, enabling a closed-loop system that moves beyond just detection. | Add a new requirement or extend REQ-PCG-023 in `REQ_PIPELINE_CONTRACT_GOVERNANCE.md`. | An integration test triggers a known, auto-remediable failure (e.g., a WARNING-level convention violation) and verifies that a remediation script (e.g., to apply a `sed` fix) is automatically invoked by the pipeline orchestrator. |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 18:27:55 UTC
- **Scope**: Review requirements for completeness, consistency, testability, and traceability across the ContextCore/startd8-sdk pipeline split.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | ambiguity | high | Define "reasonable" complexity score bounds in REQ-PCG-021 and REQ-PCG-026. Both require ASSESS complexity scores to be "reasonable (not all 0 or all 100)" but never specify what constitutes an unreasonable score distribution. Add concrete thresholds (e.g., "at least 2 of 7 dimensions must differ by ≥10 points" or "standard deviation across dimensions must exceed 5"). | Without a quantified definition, two implementers could write conflicting reasonableness checks and both claim compliance. Gate 2 (Q2) relies on this judgment, making it a blocking ambiguity for automated enforcement. The companion REQ_CAPABILITY_DELIVERY_PIPELINE.md's complexity-based routing (threshold 40) amplifies this: if "reasonable" is undefined, the routing decision's validity cannot be audited. | REQ-PCG-021 Q2 checks and REQ-PCG-026 requirement 2, add a sub-requirement specifying minimum variance or distribution constraints for the 7-dimension score vector | Unit test: generate score vectors with zero variance, single-dimension spikes, and uniform distributions; assert the reasonableness check correctly classifies each |
| R3-S2 | feasibility | critical | REQ-PCG-025 requires `BoundaryValidator` to operate at the ContextCore-to-startd8 handoff boundary, but the handoff is file-based (YAML/JSON artifacts on disk), not an in-process phase transition. The current `BoundaryValidator` API (`validate_phase_boundary()`) assumes an in-memory context dict. Specify how file-based boundary validation works: does startd8-sdk deserialize handoff artifacts into a context dict and then invoke `BoundaryValidator`, or does a new file-oriented validation mode need to exist? | The architecture table in REQ-PCG-025 places the validator in ContextCore but the handoff is cross-process and cross-repository. Without specifying the deserialization/hydration step, implementers face an unresolved impedance mismatch between the in-memory contract validation API and the file-based artifact exchange. This is not just a design detail — it determines whether the existing `BoundaryValidator` can be reused or a new adapter is needed. | REQ-PCG-025, add a requirement specifying the hydration step: "startd8-sdk MUST deserialize handoff artifacts into a context dict conforming to the `PropagationChainSpec` schema before invoking `BoundaryValidator`" with the specific fields that must be hydrated from each file | Integration test: produce handoff artifacts from stages 0–4, invoke boundary validation in startd8-sdk, assert chain status is reported correctly for both well-formed and deliberately degraded handoff sets |
| R3-S3 | feasibility | high | REQ-PCG-004 (Causal Ordering) and REQ-PCG-006 (SLO Budget) are marked "Implemented" with test counts, but the Implementation Status Matrix shows them as "D" (domain logic only, lifecycle wiring pending). Clarify the actual status and add requirements for the lifecycle wiring gap. If the domain logic exists but cannot be enforced at runtime boundaries, these contracts are inert. | The status discrepancy creates a false confidence signal: the Verification Plan cites "22 tests" and "19 tests" respectively, suggesting full coverage, while the matrix reveals these domains cannot actually enforce at pre-flight, runtime, or post-exec stages. This is a feasibility gap — the requirements claim enforcement but the infrastructure to enforce doesn't exist yet for 5 of 7 domains. | REQ-PCG-004 and REQ-PCG-006 Status fields should say "Partial — domain logic implemented, lifecycle wiring pending" and a new cross-cutting requirement should specify the lifecycle wiring work needed for domains 3–7 | Audit: for each domain marked "D", verify that calling `validate_phase_boundary()` with a contract referencing that domain actually invokes domain-specific validation (not just a no-op pass-through) |
| R3-S4 | testability | high | REQ-PCG-022 (Gate 3 — Finalize Verification) has no test reference in the Verification Plan. The plan says "Finalize report contains checksums for all artifacts" but cites no test suite, test file, or test count — unlike Gates 1 and 2 which cite specific test files and counts (34 and 25 tests respectively). Add a concrete verification method with test location. | Gate 3 is the final integrity check before artifacts are delivered. It is the only P1 gate requirement without a specific test reference. Given that Gates 1 and 2 have 34 and 25 tests respectively, Gate 3's absence from the test inventory suggests it may not be tested at all, or tests exist but are not tracked. Either case is a testability gap for a P1 requirement. | Verification Plan entry for REQ-PCG-022: replace generic statement with specific test file path and expected test count (e.g., "N tests in `test_finalize_verification.py`" or "Integration test: `test_gate3_finalize.py::test_all_artifacts_checksummed`") | Review test inventory for finalize verification tests; if none exist, flag as implementation gap |
| R3-S5 | traceability | high | REQ-PCG-024 (Handoff Integrity) and REQ-PCG-025 (Cross-Boundary Propagation) have no backward traceability to the source design documents they consolidate. Each requirement in Part 1 (1.2–1.6) can be traced to a specific source document section, but Part 2 requirements lack explicit "Derives from" annotations linking to the 5 consolidated design documents listed in the header. | The document header lists 5 source documents, and the References section maps them by number, but individual Part 2 requirements don't cite which source document section they derive from. This breaks the consolidation promise: an auditor cannot verify that all A2A Communications Design requirements are captured without manually cross-referencing the entire source document. For the handoff requirements specifically, content comes from both the A2A Comms Design (§ Handoff Contract) and the A2A Contracts Design (§ Contract Types), and it's unclear which requirement captures which source obligation. | Add "Derives from:" annotations to REQ-PCG-017 through REQ-PCG-027, citing specific source document numbers and section names from the References list (e.g., "Derives from: [4] §3.2 Contract Types, [5] §2.1 Typed Contracts") | Traceability matrix: for each Part 2 requirement, verify at least one source document section is cited; for each source document section in scope, verify at least one requirement traces to it |
| R3-S6 | ambiguity | high | NFR-PCG-004 states verification expressions use `eval()` in a "sandboxed scope" but does not define the sandbox constraints beyond listing allowed variables (`context`, `source`, `dest`). Specify: (a) maximum expression length, (b) prohibited AST node types (e.g., `Import`, `Call` to non-allowlisted functions, `Attribute` access beyond one level), (c) execution timeout, and (d) how violations are reported. | The current wording acknowledges the security risk ("if contract YAML ever comes from untrusted sources, replace `eval()`") but the "trusted source" assumption is fragile — a malicious PR could inject a verification expression. Without AST-level constraints, a reviewer cannot mechanically verify that an expression is safe. This is a second-order risk that becomes acute as the contract system sees wider adoption (REQ-PCG-016 progressive adoption path). | NFR-PCG-004, expand to specify concrete sandbox constraints: prohibited AST nodes, max expression length, timeout, and error reporting format | Security review: craft verification expressions using `__import__`, nested `getattr`, and long-running loops; assert all are rejected before `eval()` is invoked |
| R3-S7 | feasibility | high | REQ-PCG-012 requires CI to block PRs that "reduce propagation completeness" but does not specify the baseline. Is completeness measured against `main` branch? Against the last release tag? Against a checked-in threshold file? Without a defined baseline source, the CI gate cannot be implemented deterministically. | Propagation completeness is a floating metric — it changes as contracts and phases evolve. A CI gate needs a stable reference point. If measured against `main`, merge order matters (two PRs that each add phases could conflict). If measured against a threshold file, someone must maintain it. This is a feasibility gap because the requirement mandates behavior ("MUST NOT decrease") without specifying the comparison target. | REQ-PCG-012, add a requirement specifying the baseline: "Completeness MUST be compared against the value computed from the `main` branch HEAD at PR creation time" or "against a `.propagation-baseline.json` file checked into the repository" | CI test: submit a PR that removes a field from a contract YAML, verify CI blocks it; submit a PR that adds a field, verify CI allows it; verify baseline source is documented and accessible to CI |
| R3-S8 | testability | high | The Verification Plan for REQ-PCG-011 (Observability Contracts) and REQ-PCG-028/029 (Dashboards) specifies "TraceQL queries return results; dashboard panels render" but provides no test harness specification. How are dashboard rendering and TraceQL query correctness verified in CI? These are P1/P2 requirements with acceptance criteria that require a running Tempo/Grafana instance. Specify whether verification is: (a) integration test against a local Tempo/Grafana stack, (b) JSON schema validation of dashboard provisioning files, or (c) manual verification with a documented procedure. | Observability requirements are notoriously difficult to test in CI. Without specifying the test approach, these requirements risk being "verified by demo" rather than automated regression. The 24 TraceQL/LogQL tests cited in the Implementation Status Matrix suggest some automation exists, but the Verification Plan doesn't connect these tests to specific requirements. | Verification Plan entries for REQ-PCG-011, REQ-PCG-028, REQ-PCG-029: specify the test harness (e.g., "24 query validation tests in `test_traceql_queries.py` verify query syntax and expected attribute presence against mock span data") and distinguish automated from manual verification steps | Review the 24 cited TraceQL/LogQL tests to confirm they cover the specific queries referenced in REQ-PCG-028 and REQ-PCG-029; flag any dashboard panel without a corresponding query test |
| R3-S9 | traceability | medium | The Implementation Status Matrix shows two tiers of implementation (Y vs D) but there is no requirement-to-domain mapping that connects specific REQ-PCG-0XX IDs to cells in the matrix. An auditor cannot determine which requirements are fully satisfied (Y) vs partially satisfied (D) without manually cross-referencing requirement text against domain names and lifecycle stages. | The matrix is a valuable status tool but it operates at the domain level, not the requirement level. REQ-PCG-008 (Pre-Flight), REQ-PCG-009 (Runtime), REQ-PCG-010 (Post-Exec) each apply to ALL 7 domains, but only 2 domains are "Y" across all lifecycle stages. This means REQ-PCG-008/009/010 are partially implemented but the Verification Plan lists them as having tests without qualification. Adding requirement IDs to the matrix (or a separate traceability table mapping REQ → domain × lifecycle cells) would make the gap explicit. | Add a traceability table or annotate the Implementation Status Matrix with the requirement IDs that each cell satisfies (e.g., cell [Context Propagation, Pre-Flight] = REQ-PCG-001 + REQ-PCG-008) | Automated check: for each REQ-PCG-0XX marked as "Implemented" in Status field, verify corresponding matrix cell is "Y" not "D" |
| R3-S10 | testability | medium | REQ-PCG-006 (SLO Budget) acceptance criterion states "Budget violations produce appropriately-scoped alerts" but does not define what "appropriately-scoped" means. Similarly, REQ-PCG-013 acceptance criterion says "Each severity level produces the documented side effects" without specifying an observable assertion. Convert these acceptance criteria into testable predicates with specific observable outputs. | Acceptance criteria that use qualitative language ("appropriate", "documented") cannot be mechanically verified. For REQ-PCG-006, specify: "DEGRADED budget violation emits a WARNING-severity `GateResult` scoped to the phase that exceeded its allocation; BROKEN budget violation emits a BLOCKING-severity `GateResult`." For REQ-PCG-013, specify the exact span event names and attribute values each severity level must produce. | REQ-PCG-006 acceptance criteria and REQ-PCG-013 acceptance criteria: replace qualitative language with specific event names, severity values, and attribute assertions that a test can check | Unit test: for each severity level × budget state combination, assert the specific `GateResult` severity and span event name produced |

#### Review Round R4

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 18:29:19 UTC
- **Scope**: Review requirements for completeness, consistency, testability, and traceability across the ContextCore/startd8-sdk pipeline split.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Feasibility | Critical | Modify REQ-PCG-020 (Gate 1) to check "Gap parity" against *declared* gaps in `artifact-manifest.yaml`, not *extracted* features. | Gate 1 runs before Plan Ingestion (Stage 5), so "artifact features" (produced by PARSE in Stage 5) do not exist yet. Checking against them is impossible at this stage. | REQ-PCG-020 Table Row 5 | Verify Gate 1 passes on a fresh export before ingestion runs. |
| R4-S2 | Ambiguity | High | Explicitly distinguish between "Propagation Contracts" (degradable) and "A2A Contracts" (mandatory) in REQ-PCG-025 and NFR-PCG-002. | REQ-PCG-017 mandates A2A validation, but NFR-PCG-002 says validation degrades if ContextCore is missing. A2A validation (Pydantic) must remain active in `startd8-sdk` even without the ContextCore propagation engine. | REQ-PCG-025 Requirement 4 | Run `startd8-sdk` without ContextCore installed and verify A2A payloads are still validated. |
| R4-S3 | Traceability | Medium | Update REQ-PCG-021 (Gate 2) Question 2 to validate routing against "complexity score OR force_route override". | If `force_route` is used (REQ-CDP-011), the routing will intentionally mismatch the complexity score. Gate 2 must account for this to avoid false positives. | REQ-PCG-021 Requirement 3 | Run pipeline with `force_route` and ensure Gate 2 passes despite score mismatch. |
| R4-S4 | Traceability | Medium | Add requirements to propagate the Financial Budget (USD) via `BudgetPropagationSpec` (REQ-PCG-006) or a new domain. | REQ-CDP-011 accepts a cost budget, but REQ-PCG-006 only covers time (SLO) budgets. Agents need the financial context propagated to make autonomous stop decisions deep in the workflow. | REQ-PCG-006 or new REQ | Verify nested agents receive remaining USD budget in their context. |
| R4-S5 | Feasibility | High | Replace `eval()` in NFR-PCG-004 with a restricted expression parser (e.g., `simpleeval` or AST subset) immediately. | `eval()` is inherently risky and hard to sandbox effectively. Relying on "trusted sources" is fragile in CI environments with PRs. | NFR-PCG-004 | Attempt to inject malicious code in a verification expression and verify it fails to execute. |
| R4-S6 | Traceability | Low | Clarify in REQ-PCG-013 that default injection must stamp provenance with the *current* phase as `origin_phase`. | Without explicit stamping, defaulted values appear to have no origin or inherit misleading provenance from previous steps, breaking the audit trail. | REQ-PCG-013 Requirement 4 | Inspect context after default injection to verify `_cc_propagation` entry. |
| R4-S7 | Consistency | Low | Standardize filename reference in REQ-PCG-024 to `{project}-artifact-manifest.yaml` to match REQ-CDP-007. | Inconsistent filenames between the Pipeline definition and Governance definition will cause "File Not Found" errors during Handoff. | REQ-PCG-024 Requirement 1 | Verify Handoff looks for the correct filename pattern. |
| R4-S8 | Testability | Medium | Clarify REQ-PCG-022 (Gate 3) to specify if checksums verify *integrity* (disk vs hash) or *reproducibility* (regen vs hash). | "Recomputed from actual files" is ambiguous. If it means "regenerate artifacts", it requires determinism. If "hash disk files", it checks integrity. Context suggests integrity, but precision is needed for testing. | REQ-PCG-022 Requirement 1 | Run Gate 3 without regenerating files; it should pass if files match disk. |
| R4-S9 | Traceability | Medium | Explicitly require `create` and `polish` stages to seed `_cc_propagation` in REQ-PCG-014. | REQ-CDP-001/002 produce inventory, but if they don't seed the provenance dict, the chain tracking (REQ-PCG-001) effectively starts late, missing the project root context. | REQ-PCG-014 Requirement 5 | Check `project-context.yaml` or runtime context for initial provenance seed. |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 18:58:59 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | consistency | high | Define contract versioning and migration strategy for when contract YAML schemas evolve beyond `schema_version: "v1"` | REQ-PCG-017 mandates `schema_version = "v1"` and `extra="forbid"`, but no requirement addresses what happens when v2 contracts are introduced. With `extra="forbid"`, a v2 contract with new fields will be rejected by v1 validators. The interaction between strict schema enforcement (accepted via multiple rounds) and schema evolution creates a brittle upgrade path. Need requirements for version negotiation, multi-version coexistence during rolling deployments, and migration tooling. | New REQ-PCG-033 in Part 3 (Cross-Cutting Requirements) | Scenario test: deploy v2 contract YAML while v1 validators are still running; verify graceful rejection with actionable `next_action` rather than opaque parse error |
| R5-S2 | feasibility | high | Address clock skew and timestamp reliability for provenance chain verification across ContextCore and startd8-sdk halves | REQ-PCG-007 requires `set_at` (ISO 8601) in `FieldProvenance`, REQ-PCG-004 requires causal ordering based on provenance timestamps, and REQ-PCG-019 requires checksum chain integrity. If ContextCore and startd8-sdk run on different hosts (or in different containers), clock skew can cause provenance timestamps to appear out of order, breaking causal ordering validation and making staleness checks unreliable. No requirement specifies clock synchronization expectations or monotonic ordering fallbacks. | New sub-requirement under REQ-PCG-014 (Provenance Tracking) | Test with artificially skewed clocks (>5s drift) between pipeline halves; verify causal ordering checks use logical ordering (phase sequence) as primary and wall-clock as secondary |
| R5-S3 | completeness | high | Specify behavior when multiple propagation chains conflict on the same field with different severity levels | REQ-PCG-001 allows multiple `PropagationChainSpec` entries, and REQ-PCG-013 defines the three-tier severity model, but no requirement addresses what happens when field `X` appears in Chain A as BLOCKING and Chain B as ADVISORY. The validator must resolve this conflict deterministically. The accepted severity model (R1-S4, R3-S6) tightened definitions but didn't address multi-chain field overlap. | New sub-requirement under REQ-PCG-001 or REQ-PCG-013 | Unit test: declare field in two chains with conflicting severities; verify deterministic resolution (e.g., highest severity wins) and that resolution is logged |
| R5-S4 | testability | medium | Require end-to-end integration test that exercises the full pipeline path (stages 0→7) with contract enforcement enabled | The Verification Plan lists unit/component tests per requirement (62 tests here, 34 there), but no requirement mandates an integration test spanning both pipeline halves with real handoff artifacts. Accepted suggestions strengthened individual gate tests, but the interaction between gates — especially the handoff boundary where ContextCore artifacts are consumed by startd8-sdk — is only tested implicitly. A single broken assumption in artifact serialization could pass all unit tests but fail in production. | New entry in Verification Plan table and a new NFR | Integration test: run stages 0-4 producing real artifacts, then stages 5-7 consuming them; verify all gates pass, all chains report INTACT, and finalize report is complete |
| R5-S5 | consistency | medium | Reconcile the `_cc_propagation` reserved key convention with `extra="forbid"` on Pydantic models | REQ-PCG-014 stores provenance under `_cc_propagation` in the context dict, and REQ-PCG-015 requires `extra="forbid"` on all Pydantic models. If the context dict is ever validated through a Pydantic model (e.g., during serialization for handoff), the `_cc_propagation` key will be rejected as an unknown field. The document doesn't specify whether the context dict passes through Pydantic validation at the handoff boundary, creating an ambiguity that could manifest as a runtime failure. | Clarification in REQ-PCG-014 or REQ-PCG-015 specifying that `_cc_propagation` is either stripped before Pydantic validation or explicitly declared in the model | Test: serialize context dict with `_cc_propagation` through the handoff boundary Pydantic model; verify it either passes (if declared) or is cleanly stripped and restored (if filtered) |
| R5-S6 | ambiguity | medium | Define "reasonable" complexity score bounds for Q2 ASSESS validation in Gate 2 | REQ-PCG-021 Q2 requires "ASSESS complexity score is reasonable (not all 0 or all 100)" and REQ-PCG-026 repeats this. The word "reasonable" is undefined — is a score of 1 across all 7 dimensions reasonable? Is [0, 0, 0, 0, 0, 0, 100] reasonable? Without concrete bounds or statistical criteria, this gate check is unimplementable as a deterministic pass/fail. | REQ-PCG-021 Q2 and REQ-PCG-026 requirement 2 — replace "reasonable" with concrete criteria (e.g., "at least 2 of 7 dimensions must be non-zero, and standard deviation across dimensions must exceed 5") | Parameterized test with edge-case score distributions; verify gate produces consistent pass/fail for boundary cases |
| R5-S7 | traceability | medium | Extension concerns in Part 4 lack traceability to the core requirements they extend | Part 4 lists 9 extension concerns with their related domains but doesn't specify which REQ-PCG-0XX requirements they depend on or extend. For example, "4E Temporal Staleness" relates to "Causal Ordering" but doesn't reference REQ-PCG-004. When extension concerns are implemented, there's no traceability chain to verify they don't violate or duplicate core requirements. | Add a column to the Part 4 table mapping each extension to specific REQ-PCG IDs (e.g., 4E → REQ-PCG-004, 5E → REQ-PCG-005) | Review: verify each extension concern's requirements document references the correct REQ-PCG base requirements |
| R5-S8 | feasibility | medium | Specify maximum contract YAML size and validation timeout to prevent pathological contracts from stalling the pipeline | REQ-PCG-008 requires pre-flight validation and REQ-PCG-009 requires runtime boundary checks. NFR-PCG-001 ensures zero overhead without contracts, but no requirement bounds the overhead *with* contracts. A contract YAML with thousands of propagation chains or deeply nested verification expressions could make validation latency unbounded. The `eval()` mechanism in NFR-PCG-004 compounds this — even sandboxed, complex expressions can be computationally expensive. | New NFR (e.g., NFR-PCG-006) specifying maximum contract size, maximum chain count, verification expression complexity limits, and validation timeout | Stress test: generate contract YAML with 10,000 chains and complex verification expressions; verify validation completes within timeout or fails with a clear error |
| R5-S9 | completeness | medium | Specify the behavior when Stage 1.5 (FIX auto-remedy) modifies context that has already been provenance-stamped in Stage 1 | REQ-PCG-014 requires provenance stamping with value hashes, and the pipeline diagram shows Stage 1.5 (FIX auto-remedy) between Stage 1 (POLISH) and Stage 2. If Stage 1 stamps a field's provenance hash and Stage 1.5 then modifies that field's value as part of auto-remediation, the provenance hash becomes stale. No requirement specifies whether Stage 1.5 must re-stamp, whether the original stamp is preserved as history, or whether the hash mismatch is expected and tolerated at this boundary. | New sub-requirement under REQ-PCG-014 specifying provenance re-stamping behavior for auto-remedy stages | Test: stamp field in Stage 1, modify in Stage 1.5, verify provenance chain at Stage 2 entry correctly reflects the modification with updated hash |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (No prior untriaged suggestions found in Appendix C to endorse)

#### Review Round R6
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 18:59:54 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | feasibility | high | Replace Python `eval()` in NFR-PCG-004 with a standard expression language like Common Expression Language (CEL). | `eval()`—even sandboxed—poses severe security risks (sandbox escapes) and limits pipeline portability. It ties the contract logic permanently to Python, preventing future agent implementations in Go/Rust from validating contracts. | NFR-PCG-004 | Attempt to define a contract with an infinite loop or high-memory consumption expression; verify CEL rejects/limits it where `eval` might hang. |
| R6-S2 | feasibility | critical | Relax `extra="forbid"` (REQ-PCG-017) for Handoff Contracts or mandate strict Semantic Versioning negotiation. | Strict rejection of unknown fields breaks forward compatibility. If ContextCore (producer) upgrades to v1.1 and sends a new advisory field, startd8 (consumer v1.0) will crash/block, preventing independent component lifecycles. | REQ-PCG-017 | Test a "rolling upgrade" scenario: Producer sends v1.1 payload to Consumer v1.0. Verify consumer accepts valid v1.0 subset instead of crashing. |
| R6-S3 | consistency | medium | Mandate reconciliation between inline `_cc_propagation` and external `run-provenance.json` at Gate 1. | REQ-PCG-007 stores provenance inline; REQ-PCG-024 stores it externally. A malicious or buggy stage could update the data but not the external audit trail. Gate 1 must verify they match to ensure the audit trail is authentic. | REQ-PCG-020 (add Gate 1 check #8) | Introduce a discrepancy between the context dict's `_cc_propagation` and the `run-provenance.json` file; verify Gate 1 blocks. |
| R6-S4 | feasibility | medium | Distinguish between "Execution Time" and "Wall Time" in SLO Budget Propagation (REQ-PCG-006). | The pipeline includes "REVIEW" (Stage 6) which is human-in-the-loop. If budget is wall-clock time, a 2-hour human review will always break the budget chain, causing false positive "BROKEN" signals. | REQ-PCG-006 | Run a pipeline with a simulated 1-hour manual pause. Verify `remaining_budget_ms` is decremented only by compute time, not wait time. |
| R6-S5 | completeness | high | Define "Fail-Closed" behavior for Critical contracts when ContextCore is missing (NFR-PCG-002). | NFR-PCG-002 allows graceful degradation (returning `None`). If a contract enforces a critical safety check (e.g., "PII Scrubbing"), running without ContextCore bypasses this safety. Critical contracts must force a halt even if the wrapper is missing. | NFR-PCG-002 | Mark a contract as `criticality: safety`. Uninstall ContextCore. Run pipeline. Verify it halts rather than proceeding without validation. |
| R6-S6 | testability | medium | Explicitly define the determinism requirements for the `ASSESS` phase (REQ-PCG-026). | If `ASSESS` uses probabilistic heuristics (or LLMs) to score complexity, it violates NFR-PCG-005 (Idempotent Gate Execution). Re-running a failed pipeline might route differently, making debugging impossible. | REQ-PCG-026 | Run `ASSESS` 100 times on the same input. Verify the complexity score and routing decision are identical every time. |
| R6-S7 | feasibility | low | Add a size threshold or trusted cache mechanism for Checksum Recomputation (REQ-PCG-019). | "Checksums MUST be recomputed from files" is computationally prohibitive for multi-GB artifacts (e.g., ML models, container images) at every single gate. It may induce timeouts or excessive CPU costs. | REQ-PCG-019 | Benchmark pipeline with a 5GB artifact. Verify gate duration does not exceed timeout thresholds. |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 19:04:43 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Requirement Section | Issue | Suggested Fix |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | completeness | high | REQ-PCG-019 (Checksums as Circuit Breakers) | The checksum chain diagram shows `.contextcore.yaml → onboarding-metadata.json → provenance.json → artisan seed.json → FINALIZE report` but REQ-PCG-019 requirements only specify `source_checksum` verification. The intermediate links (artifact_manifest_checksum, project_context_checksum) are shown in the diagram but have no corresponding MUST-level requirements for verification. | Add explicit requirements: "artifact_manifest_checksum MUST be recomputed from {project}-artifact-manifest.yaml at Gate 1" and "project_context_checksum MUST be recomputed from project-context.yaml at Gate 1" |
| R1-F2 | ambiguity | high | REQ-PCG-009 Requirement 4 | "Preserve backward compatibility: existing `validate_phase_entry()` and `validate_phase_exit()` MUST remain unchanged" conflicts with the plan's potential need to modify these functions to integrate domain-specific lifecycle wiring (domains 3-7). If these functions cannot be changed, how do new domains inject their validation? The requirement should clarify whether "unchanged" means API-unchanged or implementation-unchanged. | Clarify: "The public API signatures of `validate_phase_entry()` and `validate_phase_exit()` MUST remain backward compatible. Internal implementation MAY be extended to invoke domain-specific validators via the contract system." |
| R1-F3 | consistency | medium | REQ-PCG-020 vs Plan Task 1a | The plan changes Gate 1 from 7 to 8 checks, adding "Artifact inventory (Mottainai provenance v2 cross-check)" as check #8. However, accepted suggestion R6-S3 also adds Gate 1 check for inline/external provenance reconciliation. This would make 9 checks total if both are applied, but the plan only counts 8. | Reconcile: either R6-S3 becomes check #9, or it is merged with the existing provenance cross-check (check #3). Update the count accordingly. |
| R1-F4 | ambiguity | medium | REQ-PCG-027 Requirement 6 | "REVIEW MUST use multi-agent review via tiered cost model (drafter/validator/reviewer)" describes an implementation pattern, not a verifiable contract requirement. A requirements document should specify what the review must validate, not how the review is internally structured. | Rewrite as: "REVIEW MUST validate generated artifacts against the declared `expected_output_contracts` from onboarding metadata. The review process MUST produce a structured review result with pass/fail per artifact and actionable feedback for failures." |
| R1-F5 | testability | medium | REQ-PCG-011 Requirement 3 | "TraceQL queries MUST be able to find: broken chains, degraded chains, phases with enrichment defaults, runs with low completeness" — the acceptance criteria provide specific query syntax but the requirement itself doesn't specify the span event attribute names that make these queries possible. The requirement depends on REQ-PCG-031 for attribute schema but doesn't cross-reference it. | Add explicit cross-reference: "This requirement depends on REQ-PCG-031 for attribute naming. TraceQL queryability MUST be verified using the attribute names defined in REQ-PCG-031." |
| R1-F6 | completeness | medium | NFR-PCG-005 (Idempotent Gate Execution) | "Gates MUST NOT have side effects beyond OTel event emission" — but OTel event emission IS a side effect (it appends to spans, writes to collectors). If a gate is re-run on the same span, it will emit duplicate events. The requirement should clarify whether duplicate events are acceptable or whether gates must be idempotent with respect to OTel emission as well. | Clarify: "Gates MUST produce the same pass/fail result when re-run with identical inputs. OTel events MAY be emitted on each run (duplicate events are acceptable and distinguishable by timestamp)." |
| R1-F7 | clarity | medium | REQ-PCG-025 Table | The component-to-repository mapping table lists 8 components but doesn't indicate which are new (to be created) versus existing (to be modified). A plan implementer cannot determine whether `src/contextcore/contracts/propagation/otel.py` already exists or needs to be created. | Add a "Status" column: Existing/New/Modified for each component |
| R1-F8 | completeness | low | REQ-PCG-032 (Design Calibration) | The calibration table maps artifact types to depth tiers but doesn't cover all artifact types that might appear in coverage.gaps. If a new artifact type (e.g., AlertmanagerConfig) has no calibration entry, the requirement doesn't specify whether this is a warning, an error, or silently skipped. | Add: "Artifact types without calibration entries MUST produce an ADVISORY-level gate result noting the missing calibration, with next_action: 'Add calibration hint for {artifact_type} to design_calibration_hints.'" |

#### Review Round R2

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 19:08:52 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
(None - The Phase 1 Plan accurately targets the known issues in the Feature Requirements, subject to the improvements suggested above.)

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 19:16:36 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-S1 | consistency | high | Define contract schema versioning and migration strategy across the ContextCore/startd8-sdk boundary | REQ-PCG-017 mandates `schema_version = "v1"` and REQ-PCG-015 uses Pydantic `extra="forbid"`, but there is no requirement governing what happens when contract schemas evolve. If ContextCore upgrades a contract schema to v2 while startd8-sdk still expects v1, the `extra="forbid"` constraint will reject valid payloads. The cross-repo nature of REQ-PCG-025's component split makes this a high-risk coordination gap. Accepted suggestions R2-S1 (consistency) and R4-S7 likely addressed internal consistency but not cross-repo schema evolution. | New requirement REQ-PCG-033 in Part 3 (Cross-Cutting), or as sub-requirements under REQ-PCG-015 and REQ-PCG-017 | Verify that a v2 contract YAML produced by ContextCore is either (a) accepted by startd8-sdk with v1 compatibility mode, or (b) rejected with an actionable version-mismatch error referencing the upgrade path |
| R7-S2 | feasibility | high | Specify maximum contract YAML size and validation time budget for pre-flight and runtime checks | REQ-PCG-008 and REQ-PCG-009 require validation at every phase boundary, and REQ-PCG-001 declares 62 tests, but no requirement bounds the computational cost of validation. As contract domains scale (7 domains × multiple chains × verification expressions with `eval()`), the cumulative validation overhead could violate NFR-PCG-001's "zero overhead" promise for the non-contract path while creating latency issues for the contract path. The interaction between REQ-PCG-006 (SLO budget tracking) and unbounded validation time is particularly ironic—validation could itself bust the budget. | NFR section, as NFR-PCG-006 or sub-requirements under REQ-PCG-008/009 | Benchmark: contract validation for a 50-chain pipeline completes within X ms; add a test that fails if validation exceeds the budget allocated to that phase in REQ-PCG-006 |
| R7-S3 | completeness | high | Specify behavior when multiple contract domains produce conflicting verdicts at the same phase boundary | REQ-PCG-009 runs boundary checks during execution, and 7 contract domains can each produce BLOCKING/WARNING/ADVISORY results. No requirement specifies the aggregation semantics: does one BLOCKING from Domain 6 (budget) override a PASS from Domain 1 (propagation)? What is the precedence when Domain 5 (capability) says BLOCKING but Domain 2 (schema) says WARNING for the same field? The defense-in-depth model implies layered independence, but runtime enforcement requires a single go/no-go decision. | New requirement under Section 1.3, or as sub-requirement of REQ-PCG-009 | Unit test: two domains return conflicting severities for the same phase boundary; verify the aggregation produces the expected composite result per the documented precedence rules |
| R7-S4 | testability | medium | Verification Plan lacks integration/end-to-end test requirements—only unit test counts are cited | The Verification Plan table maps every REQ to unit test suites (e.g., "62 tests in `contracts/propagation/`"), but no requirement specifies an integration test that exercises a full pipeline run (stages 0→7) with contract enforcement active. Individual domain tests passing does not verify that the domains compose correctly at runtime, especially given the cross-repo handoff (REQ-PCG-024/025). The accepted suggestion R3-S4 (testability) may have added test structure but the plan still lacks explicit E2E coverage. | Verification Plan table—add rows for integration/E2E verification of REQ-PCG-024, REQ-PCG-025, and the full pipeline | A CI job runs a synthetic pipeline from stage 0 through stage 7 with all 7 contract domains active, producing a finalize report with verifiable propagation summary |
| R7-S5 | ambiguity | medium | REQ-PCG-014.2 specifies `sha256(repr(value))[:8]` but `repr()` is not deterministic across Python versions or platforms | `repr()` output for floats, sets, dicts, and custom objects varies across Python 3.x minor versions and platforms. An 8-character hash prefix also has a birthday-problem collision risk (~1 in 4.3 billion, but with many fields across many runs, false negatives become plausible). This was likely not caught earlier because the hash mechanism appears simple, but it's a latent portability and correctness risk for cross-environment provenance verification (e.g., ContextCore on Python 3.11, startd8-sdk on 3.12). | REQ-PCG-014, requirement 2—tighten the serialization specification | Test: compute value_hash for the same value on two different Python versions; verify they match. Specify canonical serialization (e.g., `json.dumps(value, sort_keys=True, default=str)`) |
| R7-S6 | consistency | medium | Stage 1.5 "FIX auto-remedy" appears in the pipeline diagram but has no corresponding contract governance requirements | The pipeline overview diagram shows Stage 1.5 (FIX auto-remedy) between POLISH and INIT-FROM-PLAN. No REQ-PCG requirement governs what contracts are enforced at this stage's boundaries, what context it produces/consumes, or how auto-remediation interacts with the provenance chain (REQ-PCG-014). If FIX mutates context fields, provenance hashes from Stage 1 would be invalidated, but REQ-PCG-007/014 don't account for legitimate mid-pipeline mutations. | Add a brief requirement or note under Part 1 clarifying Stage 1.5's contract governance posture (even if it's "Stage 1.5 is governed by the same boundary checks as Stage 1") | Review the contract YAML to confirm Stage 1.5 has entry/exit field declarations; verify provenance stamps are updated after auto-remedy mutations |
| R7-S7 | traceability | medium | Extension concerns (Part 4) lack dependency mapping to core requirements they extend | Part 4 lists 9 extension concerns with "Related Domain" but doesn't trace which core REQ-PCG-0xx requirements they depend on or extend. For example, Concern 4E (Temporal Staleness) relates to "Causal Ordering" but doesn't reference REQ-PCG-004. Without this traceability, implementers of extension concerns cannot determine which core requirements serve as prerequisites or which acceptance criteria must be preserved. | Part 4 table—add a column "Prerequisite Core REQs" mapping each extension to its foundational requirements | Review: each extension concern document references the specific REQ-PCG IDs it depends on; a traceability matrix can be auto-generated |
| R7-S8 | feasibility | medium | NFR-PCG-004's `eval()` sandboxing is insufficient—restricted `eval()` is a known bypass-prone pattern in Python | NFR-PCG-004 acknowledges the risk ("if contract YAML ever comes from untrusted sources, the `eval()` mechanism MUST be replaced") but the mitigation (no builtins, limited scope) is well-documented as insufficient in Python security literature. Even with `__builtins__` removed, attribute access chains (`().__class__.__bases__[0].__subclasses__()`) can escape. Since REQ-PCG-015 specifies contract YAML is "reviewed in PRs alongside code," the threat model assumes trusted input—but the document doesn't specify what "trusted" means operationally (e.g., branch protection rules, CODEOWNERS on contract files). | NFR-PCG-004—either specify the operational trust controls (CODEOWNERS, branch protection) or require a safe expression evaluator (e.g., AST-based allowlist) even for the current trusted-source scenario | Security review: attempt sandbox escape via verification expressions in contract YAML; verify either (a) the escape is blocked or (b) operational controls prevent untrusted YAML from reaching `eval()` |
| R7-S9 | completeness | medium | No requirement addresses concurrent pipeline runs sharing the same project context or artifact namespace | REQ-PCG-019 specifies checksums are recomputed from files, and REQ-PCG-014 stores provenance in the context dict, but no requirement addresses what happens when two pipeline runs execute concurrently against the same project. Shared filesystem artifacts (`.contextcore.yaml`, `onboarding-metadata.json`) could be overwritten mid-run, causing checksum mismatches that are diagnosed as corruption rather than concurrency. NFR-PCG-005 (idempotent gates) doesn't cover this because the inputs themselves may be mutated by a concurrent run. | New NFR or sub-requirement under REQ-PCG-019/024 specifying isolation requirements for concurrent runs | Test: launch two pipeline runs concurrently for the same project; verify either (a) file-level locking prevents races or (b) run-scoped artifact paths prevent collision |
| R7-S10 | testability | low | Implementation Status Matrix shows 5 domains at "D" (domain logic only) but Verification Plan claims tests exist for all 7 domains | REQ-PCG-003 through REQ-PCG-007 each cite test counts (20, 22, 18, 19, 21 tests respectively), and the Verification Plan references these suites. However, the Implementation Status Matrix marks Semantic Conventions, Causal Ordering, Capability Propagation, SLO Budget, and Data Lineage as "D" (lifecycle wiring pending). This means the cited tests verify domain logic in isolation but not lifecycle integration (pre-flight, runtime, post-exec). The Verification Plan should distinguish between domain-logic tests and lifecycle-integration tests to avoid false confidence. | Verification Plan table—add a "Lifecycle Integration" column or footnote distinguishing domain-only tests from end-to-end lifecycle tests | For each "D"-status domain, verify whether existing tests cover lifecycle hooks (pre-flight/runtime/post-exec) or only domain validation logic |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (No prior untriaged suggestions found in Appendix C to endorse — all prior suggestions have been triaged to Applied or Rejected per the preamble.)

#### Review Round R8
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 19:17:44 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-S1 | feasibility | high | Replace `repr(value)` with canonical serialization (e.g., `json.dumps(sort_keys=True)`) for provenance hashing in REQ-PCG-014. | `repr()` for dictionaries depends on insertion order (even in Python 3.7+). Re-ordering keys without changing data will change the hash, causing false-positive "modification" alerts in the provenance chain, breaking the "Correctness" guarantee. | REQ-PCG-014 | Create a unit test where a dictionary is copied with different key insertion order; verify hashes match with JSON sort, fail with `repr`. |
| R8-S2 | security | high | Replace `eval()` in NFR-PCG-004 with a restricted expression parser (e.g., AST whitelist or `simpleeval`). | `eval()` with restricted globals is still vulnerable to CPU exhaustion attacks (e.g., `9**9**9...`) and memory segfaults. As contracts are "code", allowing `eval` opens a vector for malicious contract YAML to DoS the pipeline. | NFR-PCG-004 | Attempt to execute a contract with a CPU-intensive math expression; verify it is rejected or timed out safely. |
| R8-S3 | security | high | Add `sensitive=True` attribute to `FieldSpec` and inhibit value hashing/storage in provenance for these fields. | Storing `repr(value)` (or even a hash of a low-entropy secret) in the `_cc_propagation` context dict risks leaking secrets via logs, error dumps, or rainbow table attacks on the hash. | REQ-PCG-007 | Define a contract with a sensitive field; verify `_cc_propagation` contains a placeholder or timestamp only, not the value/hash. |
| R8-S4 | completeness | medium | Require Gate 3 (REQ-PCG-022) to verify that *no* unaccounted artifacts exist in the output directory (strict allowlist). | Current requirements verify that *planned* artifacts exist. They do not prevent a compromised or buggy contractor from generating *extra* artifacts (malware, temp files) that pollute the downstream environment. | REQ-PCG-022 | Run a test where the contractor generates a required file AND an unlisted `malware.sh`; verify Gate 3 fails. |
| R8-S5 | consistency | medium | Mandate that applying a default value (REQ-PCG-013) MUST stamp a "System Default" entry into the provenance chain. | If the system mutates the context (injects default) without stamping provenance, the chain will show a value change between the previous phase and the current one without an explanatory record, appearing as a data integrity violation. | REQ-PCG-013 | Configure a WARNING severity field; omit it; verify the resulting context has a provenance entry indicating the default was applied. |
| R8-S6 | traceability | medium | Create a formal `OverrideContract` or `BypassEvent` for manual interventions (e.g., `force_route`, gate skips). | REQ-PCG-026 allows `force_route` and REQ-PCG-008 allows bypassing pre-flight. Without a formal contract for the *override itself*, the "Correctness by Construction" claim is broken silently. Overrides must be cryptographically linked to the run. | REQ-PCG-026 | Execute a pipeline with `force_route`; verify the finalize report explicitly lists the override and the user responsible. |
| R8-S7 | feasibility | medium | Define a pruning or summarization strategy for `_cc_propagation` (REQ-PCG-007) to prevent context bloat. | "Provenance MUST travel with the data" implies the `_cc_propagation` list grows linearly with pipeline length. For long chains or loops, this can exceed header limits (if propagated via HTTP) or cause OOMs. | REQ-PCG-007 | Simulate a pipeline with 1000 hops; verify performance impact and define a "tail-only" retention policy if needed. |
| R8-S8 | feasibility | medium | Add a "Critical Cleanup" budget reservation or exemption to REQ-PCG-006 for the Export/Finalize stages. | If the "Fix" stage (1.5) exhausts the entire SLO budget, REQ-PCG-006 implies the pipeline breaks/halts. This prevents the "Export" stage from saving the artifacts/logs needed to diagnose *why* it failed. | REQ-PCG-006 | Simulate budget exhaustion in Stage 1.5; verify Stage 4 can still run to persist the failure state. |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 19:22:17 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Requirement Section | Issue | Suggested Fix |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | clarity | high | REQ-PCG-009 Req 3 | "Emit `context.boundary.{entry\|exit\|enrichment}` span events" — the `{enrichment}` event type is only meaningful for the contract validation layer (added on top of existing entry/exit), but the requirement doesn't specify when enrichment events fire vs. entry/exit events. Are there 2 events per boundary (entry + enrichment) or 3 (entry + enrichment + exit)? The plan's Task 1 doesn't clarify this. | Specify: "At each phase boundary, emit `context.boundary.entry` before phase execution, `context.boundary.exit` after phase execution, and `context.boundary.enrichment` when contract-driven enrichment checks run (between entry and execution). Enrichment events are only emitted when `contract_path` is provided." |
| R3-F2 | clarity | medium | REQ-PCG-016 Req 3 | The progressive adoption path specifies "declaration only → loader → monitor → tighten" but doesn't define the observable criteria for progressing between stages. When is a team "ready" to move from "loader (emit events, don't block)" to "monitor (dashboard)"? Without criteria, adoption stalls at the easiest stage. | Add per-stage graduation criteria: "Promotion from 'loader' to 'monitor' requires ≥1 week of span event data with ≥95% chain INTACT. Promotion from 'monitor' to 'tighten' requires dashboard review confirming no false positives in DEGRADED/BROKEN chains." |
| R3-F3 | security | high | REQ-PCG-018 Req 5 | "Produce structured error envelopes with `error_code`, `failed_path`, `message`, and `next_action`" — the `failed_path` field could expose internal filesystem paths or field paths containing sensitive data in error responses. No requirement governs what information is safe to include in error envelopes returned to callers. | Add: "Error envelopes MUST NOT include absolute filesystem paths. `failed_path` MUST be relative to the project root. `message` MUST NOT include field values, only field names and expected types." |
| R3-F4 | architecture | high | REQ-PCG-025 Table | The component mapping places `Boundary validator` in ContextCore and `Validation wrapper` in startd8-sdk, but accepted R3-S2 identified that the handoff is file-based while BoundaryValidator is in-memory. The plan defers the hydration adapter to Phase 2 but the requirements table still implies direct reuse. The requirements should note the impedance mismatch. | Add footnote to REQ-PCG-025 table: "† The BoundaryValidator operates on in-memory context dicts. At the file-based handoff boundary, startd8-sdk MUST hydrate handoff artifacts into a context dict before invoking BoundaryValidator. The hydration adapter specification is deferred to Phase 2." |
| R3-F5 | testability | medium | Verification Plan (REQ-PCG-030) | REQ-PCG-030 ("Use Contracts for Boundary Decisions, Events for Diagnostics") has acceptance criteria ("Every boundary decision is governed by a contract object") but no verification method in the Verification Plan table — it's the only requirement without one. | Add row: "REQ-PCG-030 | Code review: audit all boundary decision points in pipeline orchestrator; verify each uses a typed contract (not span event) for go/no-go; automated: grep for `if.*span_event` in decision paths" |

#### Review Round R4

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 19:25:56 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Requirement Section | Issue | Suggested Fix |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Security | High | REQ-PCG-014.2 | The 8-character hex hash prefix (32 bits) has a high collision probability (Birthday Paradox) given the volume of fields and runs. | Increase hash prefix to at least 16 characters (64 bits) or use the full hash. |
| R4-F2 | Scalability | Medium | REQ-PCG-006 | The requirement binds budgets specifically to time (`remaining_budget_ms`). Future agents may need token-based (LLM) or cost-based budgets. | Generalize `BudgetPropagationSpec` to support multiple budget units (Time, Tokens, Cost). |
| R4-F3 | Maintainability | Medium | REQ-PCG-025 | The table implies `startd8-sdk` must depend on `contextcore` source paths. It's unclear if this is a hard package dependency or a dev-time requirement. | Clarify if `contextcore` is a required peer dependency for `startd8-sdk` runtime validation. |

#### Review Round R9

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 19:37:39 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R9-S1 | consistency | high | Define contract versioning and migration strategy for schema_version transitions beyond "v1" | REQ-PCG-017 mandates `schema_version = "v1"` with `extra="forbid"`, but there is no requirement governing how contracts evolve from v1 to v2. With `extra="forbid"` enforced, any new field addition is a breaking change. The accepted progressive adoption path (REQ-PCG-016) covers severity promotion but not schema evolution. This creates a cliff: the moment v2 is needed, every consumer must update atomically or validation fails. | New requirement REQ-PCG-033 in Part 3 (Cross-Cutting) specifying version negotiation, dual-version acceptance windows, and migration tooling requirements | Review whether a v1→v2 migration can be performed without coordinated simultaneous deployment of all producers and consumers |
| R9-S2 | feasibility | high | Address eval() sandbox escape via contract YAML injection in CI/CD environments | NFR-PCG-004 acknowledges eval() risk but defers to "trusted sources (checked into repo)". However, PRs from forks (open-source model) or compromised CI pipelines can inject malicious verification expressions. The accepted regression detection (REQ-PCG-012) runs contract YAML analysis on PRs — meaning untrusted YAML is parsed and potentially evaluated during CI. This contradicts the "trusted sources only" assumption. | Add a requirement under NFR-PCG-004 mandating that verification expressions are parsed but NOT evaluated during CI PR checks from external contributors, or replace eval() with an AST-whitelist evaluator before enabling CI contract analysis on untrusted PRs | Static analysis of CI pipeline configuration to verify eval() is never invoked on unmerged PR contract YAML; integration test demonstrating sandbox containment |
| R9-S3 | completeness | high | Specify behavior when multiple contract domains produce conflicting decisions at the same boundary | REQ-PCG-009 runs boundary checks and REQ-PCG-001 through REQ-PCG-007 define seven domains, each capable of producing BLOCKING/WARNING/ADVISORY results. No requirement specifies the aggregation semantics when Domain 1 says PASS but Domain 5 says BLOCKING, or when Domain 6 budget says DEGRADED while Domain 4 ordering says INTACT. The defense-in-depth lifecycle (Section 1.3) assumes independent domain execution but doesn't define the merge function for multi-domain boundary results. | New requirement in Section 1.3 specifying domain result aggregation: BLOCKING from any domain halts; composite status is worst-of-all-domains; the aggregated result includes per-domain breakdown for diagnostics | Unit test with two domains producing conflicting results at the same boundary; verify aggregated result matches specification |
| R9-S4 | testability | medium | Add end-to-end integration test requirement spanning both pipeline halves with contract validation | The verification plan (Section: Verification Plan) lists per-requirement unit/integration tests, all scoped to either ContextCore or startd8-sdk. No verification entry covers a full pipeline run from Stage 0 through Stage 7 with contract enforcement active on both halves. REQ-PCG-025 requires cross-boundary chains but its verification ("Cross-boundary chain produces INTACT/DEGRADED/BROKEN status") could be satisfied by a mock. A true end-to-end test is needed to validate the interaction between all 76 accepted suggestions. | Add a verification row for REQ-PCG-025 requiring at least one automated end-to-end test that runs Stages 0-7 with real contract YAML, real checksum computation, and real OTel emission, verifying the full provenance chain | CI pipeline includes an e2e test target that exercises both halves; test fails if any chain status is unexpected or provenance is broken |
| R9-S5 | ambiguity | medium | Clarify "zero overhead" semantics in NFR-PCG-001 with measurable threshold | NFR-PCG-001 states "zero runtime overhead" when contracts are absent, but "zero" is physically impossible — even an `if contract_path is None: return` check has nonzero cost. Without a measurable definition, this NFR is untestable. Prior testability suggestions focused on functional tests, not performance assertions. | Redefine NFR-PCG-001 as "negligible overhead: < 1ms per phase transition and < 100KB additional memory" or similar measurable bound, and add a benchmark test to the verification plan | Benchmark test comparing phase transition latency with and without contract_path; assert delta < defined threshold |
| R9-S6 | consistency | medium | Reconcile checksum algorithm between ContextCore provenance (sha256[:8] truncated hash) and startd8-sdk gates (full SHA-256) | REQ-PCG-014 specifies `value_hash = sha256(repr(value))[:8]` (8-character truncated hash) for inline provenance, while REQ-PCG-019 and REQ-PCG-022 require full SHA-256 for file checksums. When Gate 3 verifies the provenance chain end-to-end, it must compare field-level provenance (truncated) against file-level checksums (full). The document never specifies how these two hash formats interoperate or whether truncated hashes are sufficient for tamper detection at the 8-char level (only 32 bits of entropy, birthday collision at ~65K values). | Add a note to REQ-PCG-014 distinguishing field-level provenance hashes (truncated, for mutation detection) from artifact-level integrity hashes (full SHA-256, for tamper detection), and specify that Gate 3 provenance chain verification uses full SHA-256 for file artifacts and truncated hashes only for field-level spot checks | Security analysis documenting collision probability for 8-char truncated hashes given expected field cardinality; integration test verifying Gate 3 uses correct hash format per context |
| R9-S7 | traceability | medium | Add explicit traceability from each REQ-PCG to its source document section | The document lists 5 source documents in References but individual requirements (REQ-PCG-001 through REQ-PCG-032) don't specify which source document section they derive from. For a consolidation document, this makes it impossible to verify that all source material was captured or to trace a requirement back to its design rationale. The existing traceability suggestions (R1-S7, R2-S9, etc.) addressed inter-requirement tracing but not source-to-requirement tracing. | Add a `Source:` field to each REQ-PCG entry referencing the specific source document and section (e.g., "Source: Context Propagation Contracts Design §3.2") | Completeness matrix mapping every section of the 5 source documents to at least one REQ-PCG; orphan sections flagged for review |
| R9-S8 | feasibility | medium | Specify contract YAML maximum size and loading timeout to prevent resource exhaustion | REQ-PCG-015 requires Pydantic v2 parsing with `extra="forbid"`, and REQ-PCG-016 allows progressive adoption where contracts grow over time. As more domains (7 core + 9 extensions) add contract declarations, the YAML could grow large. No requirement bounds the contract file size or specifies loading timeout behavior. In a CI pipeline running hundreds of PRs (per REQ-PCG-012), unbounded contract loading could cause resource pressure. | Add a sub-requirement under REQ-PCG-015 specifying maximum contract YAML size (e.g., 1MB) and a loading timeout (e.g., 5 seconds), with structured error on exceedance | Load test with progressively larger contract YAML files; verify graceful failure at boundary |
| R9-S9 | completeness | medium | Define retry and recovery semantics for transient gate failures (network, filesystem) | REQ-PCG-020 through REQ-PCG-022 define gates that read files, compute checksums, and cross-reference artifacts. NFR-PCG-005 requires idempotent gate execution. However, no requirement addresses what happens when a gate fails due to a transient error (filesystem temporarily unavailable, OTel collector unreachable). The idempotency guarantee enables safe retry, but the retry policy itself (max attempts, backoff, whether to distinguish transient from permanent failures) is unspecified. | Add a requirement specifying gate retry semantics: transient errors (IO, network) are retryable up to N times with exponential backoff; permanent errors (schema violation, checksum mismatch) are not retryable; the distinction MUST be encoded in GateResult via an `error_class` field | Test gate with injected transient filesystem error; verify retry occurs and succeeds; test with permanent error; verify no retry |
| R9-S10 | consistency | medium | Align Stage 1.5 "FIX auto-remedy" with contract enforcement model — specify whether auto-remedy mutations are contract-governed | The pipeline diagram shows Stage 1.5 "FIX auto-remedy" between POLISH and INIT-FROM-PLAN, but no REQ-PCG requirement governs this stage's contract behavior. Auto-remedy mutates context (fixing issues found by POLISH), but REQ-PCG-009 only defines contract validation at phase boundaries. If Stage 1.5 mutates fields that are under propagation contracts, those mutations must be tracked in provenance (per REQ-PCG-014) and validated at the 1.5→2 boundary. The current requirements implicitly assume all stages are covered but never explicitly include Stage 1.5. | Add Stage 1.5 to the contract enforcement scope in REQ-PCG-009, specifying that auto-remedy mutations MUST be stamped in provenance and validated at the Stage 1.5 exit boundary | Unit test verifying that a field mutated by auto-remedy has updated provenance hash and triggers boundary validation at Stage 2 entry |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R7-S7: The interaction between `extra="forbid"` and forward compatibility is a real deployment risk that R9-S1 above also addresses from the versioning angle — both perspectives reinforce the need for an explicit evolution strategy.
- R8-S4: Completeness coverage for Stages 0-4 contract enforcement is a genuine gap; my R9-S10 specifically identifies Stage 1.5 as an instance of this broader issue.

#### Review Round R10
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 19:38:47 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R10-S1 | Feasibility | Critical | Add a "Gate 1 Bypass" or "Native Implementation" requirement for startd8-sdk minimal installs (NFR-PCG-002). | REQ-PCG-020 mandates `contextcore contract a2a-check-pipeline` for Gate 1, but NFR-PCG-002 requires operation without `contextcore` installed. Currently, a minimal install hits a blocking failure at Gate 1 because the CLI tool is missing. | REQ-PCG-020 or NFR-PCG-002 | Test startd8-sdk setup without `contextcore` package installed. |
| R10-S2 | Consistency | High | Clarify NFR-PCG-005 (Idempotency) regarding REQ-PCG-001 (Mutation/Defaults). | REQ-PCG-001 mutates context (applies defaults) during validation. A second run sees the value as "Present" rather than "Defaulted", changing the emitted telemetry status. This violates strict idempotency (same input state -> same result) and complicates debugging. | NFR-PCG-005 | Run validation loop twice; verify status stability. |
| R10-S3 | Ambiguity | Medium | Define budget propagation semantics for parallel execution branches in REQ-PCG-006. | `remaining_budget_ms` is a scalar. In parallel execution (implied by dependency graphs), it is unclear if budget is split, duplicated, or decremented by wall-clock time shared across threads. | REQ-PCG-006 | Simulation of parallel phases with tight budget. |
| R10-S4 | Completeness | High | REQ-PCG-024 MUST include a `schema_version` compatibility check in the handoff metadata. | ContextCore and startd8-sdk are distinct lifecycles. If ContextCore exports v2 and startd8 expects v1, the pipeline should fail fast with a clear version error at the boundary, not a validation error deep in processing. | REQ-PCG-024 | Export v2 manifest, attempt ingest with v1 SDK. |
| R10-S5 | Consistency | Medium | Explicitly require Provenance (REQ-PCG-007) to re-stamp `value_hash` when Defaults (REQ-PCG-001) are applied. | If a default is applied, the value changes. If provenance isn't updated, the lineage hash check will fail (mismatch between recorded origin hash and current value hash) or the chain will appear broken. | REQ-PCG-007 | Test default application followed immediately by lineage verification. |
| R10-S6 | Feasibility | Low | Add execution timeout/resource limits to NFR-PCG-004 (Verification Expression Safety). | Sandboxed `eval` prevents namespace pollution but not CPU exhaustion (infinite loops) or memory spikes. A robust pipeline requires resource bounds on contract evaluation to prevent DoS. | NFR-PCG-004 | Fuzzing with complex expressions. |

#### Review Round R4

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 19:43:13 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Requirement Section | Issue | Suggested Fix |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | clarity | high | REQ-PCG-001 Req 6-7 | "Propagation chains MUST verify source-to-destination field flow with optional waypoints and verification expressions" — the term "waypoints" is used only here and never defined. It's unclear whether waypoints are intermediate phases that must contain the field, intermediate phases where the field must have a specific value, or simply ordering constraints. | Define "waypoint" in the requirement: "A waypoint is an intermediate phase through which the field MUST pass with a non-null value. Waypoints enforce that the field was not dropped and re-created, but do not constrain the field's value at the waypoint." |
| R4-F2 | maintainability | high | REQ-PCG-015 Req 3-4 | The framework/concrete split ("framework in ContextCore, concrete YAML in startd8-sdk") creates a coupling where startd8-sdk contract YAML must conform to ContextCore's schema models, but schema model changes require coordinated releases. No requirement specifies the compatibility contract *between* the framework and the concrete YAML it validates. | Add: "ContextCore schema models MUST maintain backward compatibility with concrete contract YAML for at least one minor version. Breaking schema changes MUST increment the schema_version and provide a migration guide." |
| R4-F3 | scalability | medium | REQ-PCG-011 Req 4-5 | "Grafana dashboards MUST include panels for propagation completeness, broken chains over time, and enrichment defaults applied" — this assumes a single dashboard for all pipelines. As the system scales to multiple pipelines and teams, a single dashboard becomes unreadable. No requirement addresses per-pipeline or per-team dashboard scoping. | Add: "Dashboard panels MUST support filtering by `pipeline_id` and `project_id`. Dashboard provisioning MUST support templated instantiation for per-pipeline views." |
| R4-F4 | testability | high | REQ-PCG-012 Req 2-4 | "Propagation completeness MUST NOT decrease between builds. Removed fields or weakened severity MUST block the PR." — this assumes contract changes are always additive. Legitimate refactoring (renaming a field, splitting a chain) would decrease completeness temporarily. No mechanism exists for declaring intentional regressions with approval. | Add: "Intentional completeness decreases MUST be declared via a `contract-regression-allowlist.yaml` file checked in with the PR, containing the specific field/chain being removed and a mandatory `reason` field. The CI gate MUST verify the allowlist covers exactly the detected regressions." |
| R4-F5 | clarity | medium | REQ-PCG-030 | "Use a contract object when data must be consumed by another agent/system" vs "Use a span event when data is local diagnostic detail" — the distinction is unclear for intermediate cases like the propagation summary (REQ-PCG-010), which is emitted as a span event but consumed by dashboards and alerting rules. Is the propagation summary a "contract object" or a "span event" under this taxonomy? | Clarify: "Span events that are consumed by alerting rules or dashboards are considered 'structured diagnostic events' — they follow the span event schema (REQ-PCG-031) but are NOT validated at boundaries. They are distinct from contract objects which govern go/no-go decisions." |

#### Review Round R5

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 19:47:00 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Requirement Section | Issue | Suggested Fix |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | scalability | medium | REQ-PCG-019 | Requirement "checksums MUST be recomputed from actual files" implies local filesystem dependency. This hinders future streaming or in-memory pipeline architectures. | Clarify "files" to "artifacts (on disk or in memory)" and allow checksums to be computed from byte streams. |
| R5-F2 | maintainability | medium | REQ-PCG-023 | Requirement mentions `error_code` but lacks a requirement for a centralized definition/registry, leading to arbitrary string codes. | Add "Error codes MUST be drawn from a centralized `GateErrorCode` enum defined in the SDK." |
| R5-F3 | testability | medium | REQ-PCG-012 | Regression detection covers propagation completeness but misses *performance* regression. Contracts could become valid but intolerably slow. | Add requirement: "CI MUST fail if contract validation latency exceeds baseline by >X%." |

#### Review Round R11

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 20:16:22 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R11-S1 | consistency | high | Define explicit contract versioning and migration strategy for when contract schemas evolve between `schema_version: v1` and future versions | REQ-PCG-017 mandates `schema_version = "v1"` and REQ-PCG-015 uses `extra="forbid"`, but there is no requirement governing what happens when v2 contracts are introduced. With `extra="forbid"`, a v2 contract with new fields will be rejected by a v1 validator. The combination of strict parsing + no version negotiation creates a cliff: any schema evolution becomes a coordinated big-bang deployment across both ContextCore and startd8-sdk. This is a second-order effect of the accepted strict-validation suggestions. | New requirement REQ-PCG-033 in Part 3 (Cross-Cutting), or as sub-requirements under REQ-PCG-015 and REQ-PCG-017 | Verify that a v2 contract YAML with an additional field is handled gracefully (version-aware loader selects correct model); integration test for mixed-version deployment |
| R11-S2 | feasibility | high | Specify maximum acceptable latency budget for cumulative contract validation across all phase boundaries in a full pipeline run | REQ-PCG-009 states "no overhead when contract_path is not provided," and NFR-PCG-001 covers the zero-contract case, but there is no performance budget for the *with-contracts* path. A full Artisan pipeline has 7 phases × (entry + exit + enrichment) validation + chain validation + provenance stamping. If each boundary check takes even 50ms, the cumulative overhead across ~20+ validation points becomes material. Without a stated budget, there is no basis to reject a slow validator implementation. | New NFR (e.g., NFR-PCG-006) in Non-Functional Requirements section | Benchmark test: full pipeline with contracts enabled must complete validation overhead within stated budget; CI regression gate on validation latency |
| R11-S3 | completeness | high | Add requirements for contract validation behavior under concurrent/parallel pipeline execution | The document assumes sequential phase execution (REQ-PCG-004 states "phase-sequential execution model enforces ordering within a pipeline"), but REQ-PCG-006 tracks budget per-phase and REQ-PCG-014 stores provenance in a mutable context dict (`_cc_propagation`). If two pipeline runs share a process or if future parallelism is introduced, the mutable context dict becomes a race condition vector. There is no requirement specifying isolation guarantees between concurrent runs. | New requirement in Part 3 (Cross-Cutting) or as a sub-requirement of REQ-PCG-014 | Unit test: two concurrent pipeline runs with overlapping phases do not corrupt each other's `_cc_propagation` entries |
| R11-S4 | testability | medium | Specify contract testing for the graceful degradation path (ContextCore not installed) beyond "return None" | REQ-PCG-009.3 and REQ-PCG-025.4 both state the wrapper "MUST return `None`" when ContextCore is absent, and NFR-PCG-002 requires existing validation still runs. However, the verification plan has no explicit test for this path. The 154+ A2A tests and 62+ propagation tests presumably all run *with* ContextCore installed. There's an untested interaction: what happens to `_cc_propagation` keys in the context dict when they arrive at a startd8-sdk instance without ContextCore? Are they silently carried, stripped, or do they cause key errors in downstream handlers? | Verification Plan table — add explicit entry for NFR-PCG-002 | Integration test: run stages 5-7 with a context dict containing `_cc_propagation` keys but without ContextCore importable; verify no crashes, existing validation passes, provenance keys are preserved or explicitly documented as dropped |
| R11-S5 | consistency | medium | Reconcile the checksum algorithm between Layer 1 provenance (sha256 truncated to 8 chars) and A2A gates (full sha256) | REQ-PCG-014.2 specifies `value_hash = sha256(repr(value))[:8]` for provenance tracking, while REQ-PCG-019 and REQ-PCG-022 use full SHA-256 for file checksums. The 8-character truncation in provenance gives only 32 bits of collision resistance, which is fine for mutation detection of individual field values but could cause false negatives in adversarial or high-volume scenarios. More importantly, the two different checksum conventions are never explicitly distinguished — an implementer might incorrectly apply truncated hashes to file checksums or vice versa. | Add a note to REQ-PCG-014 explicitly distinguishing provenance value hashes (truncated, detection-grade) from artifact/file checksums (full, integrity-grade), or create a cross-cutting checksum conventions requirement | Review: confirm all file-level checksum usages reference full SHA-256; confirm all field-level provenance usages reference truncated form; add a naming convention (e.g., `value_hash` vs `checksum`) |
| R11-S6 | completeness | medium | Define behavior when `eval()`-based verification expressions in propagation chains fail with runtime errors (not just boolean false) | NFR-PCG-004 addresses the *security* of `eval()` (sandboxed scope, trusted sources), but REQ-PCG-001.6 references "verification expressions" without specifying what happens when an expression raises an exception (e.g., `TypeError`, `KeyError`, `AttributeError`) rather than returning `True`/`False`. Should an exception be treated as BROKEN, DEGRADED, or should it raise to the caller? This is distinct from the security concern — it's an error-handling gap. | Add sub-requirement to REQ-PCG-001 (e.g., requirement 8) specifying exception-during-verification behavior | Unit test: verification expression that raises TypeError produces BROKEN status with exception details in chain event attributes |
| R11-S7 | traceability | medium | Add bidirectional traceability between the 9 extension concerns (Part 4) and the core requirements they depend on | Part 4 lists 9 extension concerns with their "Related Domain" but does not specify which core REQ-PCG-0XX requirements they extend or depend on. For example, Concern 4E (Temporal Staleness) relates to "Causal Ordering" but doesn't reference REQ-PCG-004 explicitly. When a core requirement changes, there's no way to identify which extension concerns are impacted without reading each extension document. | Add a column to the Part 4 table: "Depends On" listing specific REQ-PCG IDs; or add forward references in the affected core requirements | Review: each extension concern document references specific core REQ-PCG IDs; changes to core requirements trigger review of dependent extension documents |
| R11-S8 | ambiguity | medium | Clarify what "reasonable" means for ASSESS complexity scores in REQ-PCG-026.2 and REQ-PCG-021 Q2 | REQ-PCG-026.2 says ASSESS "MUST score 7 complexity dimensions (0-100)" and REQ-PCG-021 Q2 says "ASSESS complexity score is reasonable (not all 0 or all 100)." The only definition of "unreasonable" is the degenerate case of uniform scores. What about scores that are all 50? Or a single dimension at 100 with others at 0? The acceptance criteria repeat "reasonable" without operationalizing it. This makes the gate subjectively enforceable. | REQ-PCG-026.2 — replace "reasonable" with a concrete invariant such as "at least 2 of 7 dimensions MUST have distinct non-zero scores" or "standard deviation across dimensions MUST exceed a configurable minimum" | Unit test: ASSESS output with degenerate score distributions (all same, single outlier, all zero except one) is correctly flagged or passed per the concrete rule |
| R11-S9 | feasibility | medium | Address clock skew implications for ISO 8601 timestamps in provenance and budget tracking across ContextCore and startd8-sdk | REQ-PCG-014.2 requires `set_at` as ISO 8601, REQ-PCG-006 tracks `remaining_budget_ms` with per-phase timing, and REQ-PCG-004 enforces causal ordering using provenance timestamps. If ContextCore stages run on one machine/container and startd8-sdk stages run on another (which is architecturally implied by the two-repo split), clock skew between hosts could cause: provenance timestamps to appear non-monotonic, budget calculations to over/under-count, and causal ordering violations that are artifacts of clock drift rather than real ordering errors. | Add a note or sub-requirement to REQ-PCG-014 and REQ-PCG-006 specifying that timestamps MUST use monotonic ordering within a pipeline run (e.g., logical clocks or sequence numbers supplement wall-clock timestamps) | Integration test: simulate 500ms clock skew between ContextCore and startd8-sdk stages; verify provenance chain and budget tracking still produce correct results |
| R11-S10 | testability | medium | Add end-to-end contract validation test that exercises the full pipeline (stages 0-7) with deliberately injected contract violations at each stage | The verification plan lists per-domain and per-gate test suites, but there is no requirement for an end-to-end test that validates the *interaction* between all contract enforcement points. Accepted suggestions have added many individual gates and checks, but the combination could have emergent behaviors: e.g., a WARNING default applied at Stage 1 might satisfy a BLOCKING check at Stage 5 with a value that is technically present but semantically wrong. The current test suites wouldn't catch this cross-boundary semantic issue. | Verification Plan — add an end-to-end integration test row covering the full pipeline with fault injection | E2E test: inject one BLOCKING violation, one WARNING-with-default, and one checksum tamper at different stages; verify the pipeline halts at the correct point, defaults are applied correctly, and the tamper is caught at the expected gate |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R7-S7: The interaction between accepted strict-validation suggestions (extra="forbid") and real-world schema evolution makes forward/backward compatibility testing essential — this aligns with my R11-S1 finding about version migration gaps.
- R8-S4: Completeness of the verification plan is critical given the number of accepted suggestions that added new validation points without corresponding test entries.
- R10-S4: The gap in specifying behavior for partial ContextCore installation scenarios directly supports my R11-S4 finding about untested degradation paths.

#### Review Round R12
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 20:17:32 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R12-S1 | consistency | critical | Resolve contradiction between REQ-PCG-013 (which mandates context mutation for defaults) and NFR-PCG-005 (which forbids side effects in gates). | REQ-PCG-013 states "WARNING-severity absent fields MUST apply the declared default (mutating the context dict)", while NFR-PCG-005 states "Gates MUST NOT have side effects". This ambiguity leaves implementers unsure whether validation is pure or transformative. | NFR-PCG-005 | Create a test case where a gate applies a default; assert whether the context object remains changed after the gate returns. |
| R12-S2 | traceability | high | Explicitly require W3C `traceparent` propagation in `HandoffContract` and `TaskSpanContract` to link ContextCore and startd8-sdk traces. | REQ-PCG-017 lists contract fields but omits trace context. Without explicit `traceparent` passing in the file/API handoff, the "ContextCore half" and "startd8-sdk half" will appear as disjoint traces, breaking the "End-to-End" observability promise. | REQ-PCG-017 | Inject a `traceparent` in the handoff artifact; verify the consuming startd8 span becomes a child of the producing ContextCore span. |
| R12-S3 | consistency | high | REQ-PCG-019 MUST specify a strict canonicalization method (e.g., JCS or sorted keys) for file checksumming. | "Recomputed from actual files" is fragile because JSON serialization (whitespace, key order) is non-deterministic across tools/versions. Without canonicalization, semantically identical files will fail Gate 1 checksums. | REQ-PCG-019 | Generate two JSON files with identical data but different key order; assert checksum verification passes only when canonicalization is applied. |
| R12-S4 | consistency | high | REQ-PCG-007 MUST replace `repr(value)` with a stable serialization method (e.g., `json.dumps(val, sort_keys=True)`) for provenance hashing. | `repr()` is not guaranteed to be deterministic across Python versions or implementations (e.g., object memory addresses). Using it for provenance hashing will cause false-positive integrity failures. | REQ-PCG-007 | Compute provenance hash for a dict in two different Python processes; assert hashes match (which `repr` fails to guarantee). |
| R12-S5 | feasibility | medium | NFR-PCG-004 MUST unconditionally require a restricted expression evaluator (e.g., `ast.literal_eval`), removing the allowance for `eval()`. | Allowing `eval()` "if contract YAML comes from trusted sources" is a security risk, as "trusted" is often context-dependent and mutable (e.g., PRs from forks). A safe evaluator is feasible and eliminates RCE vectors. | NFR-PCG-004 | Attempt to execute `__import__('os')` in a chain verification spec; assert the validator raises a security error. |
| R12-S6 | feasibility | medium | REQ-PCG-025 MUST include a runtime version compatibility check between `startd8-sdk` and the installed `ContextCore` library. | If `startd8-sdk` is installed alongside an incompatible version of `ContextCore` (e.g., API mismatch in `ContractLoader`), the pipeline will crash at runtime. It should detect the mismatch and degrade gracefully. | REQ-PCG-025 | Mock an incompatible `ContextCore` version; verify `startd8-sdk` logs a warning and disables validation instead of crashing. |
| R12-S7 | ambiguity | medium | REQ-PCG-022 MUST explicitly define whether a "Partial" status rollup results in a pipeline failure (non-zero exit code). | "Partial" status is ambiguous for CI orchestration. If critical artifacts are missing, the pipeline must fail. If only optional ones are missing, it might pass. This behavior must be deterministic. | REQ-PCG-022 | Run a pipeline that results in "Partial" status; verify the process exit code matches the requirement. |
| R12-S8 | feasibility | low | REQ-PCG-031 MUST define a strategy (truncation/summary) for emitting `_cc_propagation` data to OTel to avoid attribute size limits. | `_cc_propagation` grows with every phase. Dumping the full context into span attributes will likely exceed OTel backend limits (e.g., 64KB), causing span rejection or data loss. | REQ-PCG-031 | Simulate a deep pipeline run; verify emitted span attributes remain within standard OTel size limits. |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 20:22:41 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Requirement Section | Issue | Suggested Fix |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | security | high | REQ-PCG-024 Req 5 | `source_checksum` is verified against `.contextcore.yaml` but no requirement specifies WHO computes the initial checksum or how it is protected from tampering between Stage 0 (CREATE) and Stage 4 (EXPORT). If Stage 0 computes the checksum but a compromised Stage 1.5 (FIX) modifies `.contextcore.yaml` without updating the checksum, the entire chain is silently broken. The checksum origin and update protocol across stages 0-4 is unspecified. | Add: "The `source_checksum` MUST be recomputed at each ContextCore stage that modifies `.contextcore.yaml`. The recomputation MUST be performed by the stage runner (not the handler), ensuring handlers cannot bypass checksum updates. The provenance chain MUST record each recomputation with the stage that triggered it." |
| R5-F2 | scalability | high | REQ-PCG-001 Req 1 | Contract YAML requires `pipeline_id` as a top-level field, but no requirement addresses how contracts are scoped when a single project has multiple pipelines (e.g., dev vs. staging vs. production) that share some but not all contract declarations. Without pipeline-scoped contract inheritance or composition, teams must duplicate entire contract files per pipeline, creating maintenance burden at scale. | Add: "Contract YAML MAY declare `extends: {base_contract_path}` to inherit field declarations from a base contract. Extended contracts MUST be able to override severity levels (promotion only: ADVISORY→WARNING→BLOCKING) and add new fields. Severity demotion in extensions MUST be rejected at parse time." |
| R5-F3 | testability | high | REQ-PCG-010 Req 2 | `context.propagation_summary` emits `completeness_pct` but the calculation method is not specified. Is it `intact_chains / total_chains * 100`? Does it weight chains by severity? A chain with all BLOCKING fields that is DEGRADED should arguably reduce completeness more than a chain with all ADVISORY fields. Without a formula, two implementations could produce different percentages for identical chain results. | Specify: "`completeness_pct` MUST be calculated as `(intact_count / total_chains) * 100`, rounded to one decimal place. DEGRADED and BROKEN chains are both counted as not-intact. Severity-weighted completeness MAY be emitted as an additional attribute `weighted_completeness_pct` but is not required for Phase 1." |
| R5-F4 | security | medium | REQ-PCG-018 Req 5 | `ValidationErrorEnvelope` includes `failed_path` which could expose internal schema structure to callers. Combined with accepted R3-F3 (no filesystem paths in envelopes), the requirement still doesn't address whether `failed_path` values like `$.handoff.auth.scopes` reveal contract structure that an attacker could use to craft targeted bypass payloads. | Add: "Error envelopes MUST NOT include contract schema paths that reveal enforcement structure (e.g., which fields are BLOCKING vs ADVISORY). `failed_path` MUST reference the payload structure, not the contract structure. A separate `contract_evidence` field MAY be included in internal (non-returned) audit logs." |
| R5-F5 | completeness | medium | REQ-PCG-027 Req 4 | "IMPLEMENT MUST use `parameter_sources` and `resolved_artifact_parameters` from onboarding metadata" — but no requirement specifies fallback behavior when `resolved_artifact_parameters` is empty or contains unresolvable references. Gate 1 check #7 (parameter resolvability) is non-blocking (warning only), meaning IMPLEMENT can receive unresolved parameters. The requirement should specify whether IMPLEMENT halts, uses defaults, or emits DEGRADED status for unresolved parameters. | Add: "When `resolved_artifact_parameters` contains unresolved references (marked by Gate 1 check #7 warning), IMPLEMENT MUST emit a WARNING-severity span event per unresolved parameter and MUST use the raw `parameter_sources` expression as a string placeholder. The finalize report MUST flag artifacts generated with unresolved parameters." |

#### Review Round R6

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 20:24:10 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Requirement Section | Issue | Suggested Fix |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | scalability | medium | REQ-PCG-007 | Linear growth of `_cc_propagation` context dict is a scalability risk for long pipelines. | Add requirement for provenance snapshotting/offloading when size exceeds threshold. |
| R6-F2 | security | high | REQ-PCG-018 | Error envelopes returning unsanitized input (`failed_path`, `message`) create log injection/XSS risks. | Add requirement: "Error envelope fields MUST be sanitized and truncated." |

#### Review Round R13

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 20:36:32 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R13-S1 | consistency | high | Define explicit contract versioning and migration strategy when `schema_version` changes from `v1` to `v2` | REQ-PCG-017 mandates `schema_version = "v1"` and REQ-PCG-018 requires validation against "the correct schema version," but no requirement addresses what happens when a version bump occurs. With two independent repos (ContextCore and startd8-sdk) per REQ-PCG-015/REQ-PCG-025, a version mismatch during rolling deployment is inevitable. The accepted suggestions around schema compatibility (REQ-PCG-002) address inter-service semantic mapping but not intra-contract-system version migration. | New requirement REQ-PCG-033 or addition to REQ-PCG-017 specifying version negotiation, minimum supported version, and deprecation window | Simulate a v1→v2 schema migration with one repo updated and the other on v1; verify boundary validation produces actionable errors rather than cryptic parse failures |
| R13-S2 | completeness | high | Specify maximum allowable clock skew for provenance timestamp verification across the two pipeline halves | REQ-PCG-007 requires `set_at` (ISO 8601) timestamps and REQ-PCG-004 requires causal ordering verification using "provenance timestamps," but no requirement specifies acceptable clock skew tolerance between ContextCore and startd8-sdk environments. If they run on different hosts (or CI runners), monotonicity of `set_at` across the handoff boundary is not guaranteed, causing false-positive ordering violations and provenance chain breaks. | Addition to REQ-PCG-014 or REQ-PCG-004 specifying clock skew tolerance and whether logical clocks (sequence numbers) should supplement wall-clock timestamps | Test with simulated 5-second clock skew between pipeline halves; verify provenance chain validation does not produce false positives |
| R13-S3 | feasibility | high | Address `eval()` replacement timeline and interim hardening for NFR-PCG-004 verification expressions | NFR-PCG-004 acknowledges the `eval()` risk and states it "MUST be replaced" if contracts come from untrusted sources, but provides no requirement for when or how. Since REQ-PCG-016 promotes progressive adoption (contracts start advisory, get promoted), the trust boundary will blur as more teams contribute contract YAML. The "trusted sources" assumption erodes as adoption succeeds — a second-order effect of the progressive adoption path. | Add a concrete requirement specifying: (a) allowed expression grammar subset, (b) static analysis CI check that verification expressions contain no side effects, (c) migration path to a safe evaluator (e.g., `asteval` or restricted AST) | CI gate that parses all verification expressions into AST and rejects any node types beyond Compare, BoolOp, Attribute, Name, Constant |
| R13-S4 | testability | high | Require integration tests that exercise the full 8-stage pipeline end-to-end with contract enforcement, not just per-component unit tests | The Verification Plan lists per-component test suites (62 tests here, 34 there) but no requirement mandates an end-to-end integration test that runs stages 0→7 with contracts active. The interaction between accepted suggestions (e.g., R5-S1 consistency + R6-S1 feasibility + R3-S4 testability) creates emergent behaviors only visible in integration. Unit tests for Gate 1 pass, unit tests for Gate 2 pass, but the handoff artifacts from a real Stage 4 export may differ from test fixtures. | New section in Verification Plan or new NFR requiring at least one golden-path integration test and one failure-injection integration test per release | Integration test that runs `contextcore` stages 0-4, produces handoff artifacts, then runs `startd8-sdk` stages 5-7; verify provenance chain INTACT end-to-end |
| R13-S5 | ambiguity | medium | Clarify whether `_cc_propagation` survives serialization across the handoff boundary and in what format | REQ-PCG-014 requires provenance in the context dict under `_cc_propagation`, and REQ-PCG-024 specifies the handoff uses JSON/YAML files. But no requirement specifies whether `_cc_propagation` is serialized into `onboarding-metadata.json`, `run-provenance.json`, or a separate file — or whether it's reconstructed on the startd8-sdk side from `run-provenance.json`. This ambiguity means REQ-PCG-025 ("BoundaryValidator MUST operate at the handoff boundary") cannot be implemented consistently. | Clarify in REQ-PCG-014 or REQ-PCG-024 the exact serialization target for `_cc_propagation` at the handoff boundary and whether startd8-sdk reconstructs it from provenance files | Verify that `_cc_propagation` round-trips through the handoff artifacts by asserting equality before export and after plan ingestion |
| R13-S6 | consistency | medium | Reconcile the severity model between ContextCore contracts (BLOCKING/WARNING/ADVISORY) and A2A gate results (blocking boolean + severity field) | REQ-PCG-013 defines a three-tier severity model (BLOCKING/WARNING/ADVISORY) for ContextCore, while REQ-PCG-023 defines gate results with a separate `severity` field plus a `blocking` boolean. These are two different severity systems governing the same pipeline. A WARNING-severity propagation failure in ContextCore could produce a gate result where `blocking=false` but `severity=high` — or the mapping could go the other way. No requirement specifies the mapping between these two severity models. | Add a mapping table to REQ-PCG-013 or REQ-PCG-023 specifying how ContextCore severity levels translate to GateResult severity and blocking fields | Unit test asserting that a BLOCKING propagation failure always produces `blocking=true` in the corresponding GateResult, and ADVISORY never produces `blocking=true` |
| R13-S7 | completeness | medium | Specify behavior when multiple propagation chains conflict (e.g., one chain says INTACT, another says BROKEN for the same field via different paths) | REQ-PCG-001 and REQ-PCG-010 define chain validation producing per-chain status and a summary `completeness_pct`. But a single field can participate in multiple chains (e.g., `project.domain` might be in a classification chain and a capability chain). No requirement specifies the conflict resolution when chains disagree about the same field's status, or whether `completeness_pct` is computed per-chain or per-field. | Add conflict resolution semantics to REQ-PCG-010: specify whether completeness is chain-weighted or field-weighted, and whether the worst-case chain status for a field governs | Test with a field that is INTACT in chain A but DEGRADED in chain B; verify completeness_pct computation matches the documented formula |
| R13-S8 | feasibility | medium | Address contract YAML file size and loading performance as the number of contract domains scales from 2 (implemented) to 7+ (planned) | REQ-PCG-009 requires "no overhead when `contract_path` is not provided" (NFR-PCG-001), but says nothing about overhead when it IS provided. With 7 domains × multiple lifecycle stages, contract loading could become a bottleneck. The Implementation Status Matrix shows 5 domains at status "D" (pending lifecycle wiring). When these are wired in, every phase boundary triggers 7 domain validations × 3 lifecycle checks. No performance budget is specified. | Add a performance NFR specifying maximum acceptable latency overhead per phase boundary when all 7 contract domains are active (e.g., < 50ms per boundary check) | Benchmark phase boundary validation with all 7 domains loaded; assert overhead stays within budget |
| R13-S9 | traceability | medium | Link each extension concern (Part 4) to the specific core requirements it extends or depends on | Part 4 lists 9 extension concerns with "Related Domain" but no traceability to specific REQ-PCG-XXX requirements they depend on or extend. For example, "4E Temporal Staleness" relates to Causal Ordering but doesn't specify whether it depends on REQ-PCG-004 being fully lifecycle-integrated (currently status "D"). This makes it impossible to assess whether extension concerns are blocked by incomplete core domain wiring. | Add a dependency column to the Part 4 table mapping each extension to its prerequisite REQ-PCG-XXX IDs and their required implementation status | Review each extension concern requirements document; verify its prerequisites are met by inspecting the Implementation Status Matrix |
| R13-S10 | testability | medium | Require fault injection tests for the graceful degradation path (NFR-PCG-002) where ContextCore is not installed | NFR-PCG-002 and REQ-PCG-025 require startd8-sdk to function without ContextCore, but the Verification Plan has no test that actually exercises this path. The acceptance criterion "startd8-sdk without ContextCore installed still runs" implies a test exists, but it's not listed. Given that 125 accepted suggestions have added significant contract machinery, the degradation path likely has untested code branches where absent imports are caught. | Add explicit test entries to the Verification Plan for NFR-PCG-002 that run the startd8-sdk test suite with ContextCore uninstalled (e.g., via a CI matrix job) | CI matrix job that installs startd8-sdk without ContextCore dependency; runs stages 5-7 tests; asserts all pass with validation wrapper returning `None` |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R10-S4: The companion document cross-reference gap is real — as contract governance and pipeline orchestration evolve independently, their requirements can drift without explicit linkage.
- R12-S7: Clarifying the distinction between "domain logic implemented" (D) and "fully integrated" (Y) in the Implementation Status Matrix is essential for planning the 5 pending domain wiring efforts.
- R9-S3: Explicit error taxonomy for contract validation failures would prevent inconsistent error handling across the 7 domains as they get wired into lifecycle stages.
- R8-S4: The gap around what constitutes a "trusted source" for contract YAML directly feeds into R13-S3 above — progressive adoption blurs the trust boundary.

#### Review Round R14
- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 20:37:39 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R14-S1 | Feasibility | High | Replace `repr(value)` with a canonical deterministic serialization (e.g., `json.dumps(sort_keys=True)`) for `value_hash` calculation in REQ-PCG-007 and REQ-PCG-014. | `repr()` is not guaranteed to be deterministic for unordered collections (e.g., sets) or across Python implementations, leading to false-positive "modification" signals in provenance checks when the semantic value hasn't changed. | REQ-PCG-007 (Requirement 2), REQ-PCG-014 (Requirement 2) | Unit test with `set` and `dict` types ensuring hash stability across process restarts. |
| R14-S2 | Completeness | Critical | Add a `sensitive` boolean attribute to `FieldSpec` (REQ-PCG-001) and enforce redaction of these fields in OTel span events and logs. | The current design emits context values into observability backends for debugging. Without explicit sensitivity tagging, secrets (API keys, tokens) flowing through the context will be leaked into TraceQL/logs. | REQ-PCG-001 (Requirement 2), REQ-PCG-011 | Verify that fields marked `sensitive=True` appear as `[REDACTED]` in emitted span attributes. |
| R14-S3 | Traceability | Medium | Define provenance behavior for iterative loops (Stage 1.5 Fix -> Stage 1 Polish) in REQ-PCG-014; specifically, require an iteration counter or history list. | The current single-slot `_cc_propagation` design implies that a "Fix" pass overwrites the provenance of the "Polish" pass. Losing the history of value mutation during remediation cycles hinders debugging of "flapping" fixes. | REQ-PCG-014 | Test a loop scenario where a value changes in Pass 2; verify provenance reflects the latest pass or full history. |
| R14-S4 | Reliability | High | Explicitly mandate "Fail-Closed" behavior for unhandled exceptions within Gate logic (REQ-PCG-020). | NFR-PCG-001 ensures zero overhead when disabled, but doesn't specify behavior if the Gate *crashes* while enabled. Security governance requires that infrastructure errors treat the gate as Failed, not Passed. | REQ-PCG-020 | Chaos test: Inject a `RuntimeError` into the gate validator and ensure the pipeline halts. |
| R14-S5 | Feasibility | Medium | Use logical clocks (or step counters) instead of wall-clock timestamps for Causal Ordering Contracts (REQ-PCG-004). | ContextCore and startd8-sdk may run on different nodes/containers. Reliance on wall-clock timestamps for "A before B" validation is prone to clock skew failures in distributed environments. | REQ-PCG-004 | Verify ordering checks pass even if the consumer's system clock is slightly behind the producer's. |
| R14-S6 | Traceability | Low | Require `FieldProvenance` to explicitly flag values injected via defaults (REQ-PCG-013), distinct from values set by handlers. | REQ-PCG-013 allows mutation via defaults. Downstream consumers need to know if a value is "real" or "defaulted" via the provenance metadata, rather than inferring it from the value itself. | REQ-PCG-013 | Verify `_cc_propagation` entry for a defaulted field indicates `is_default=True`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R12-S7: Explicitly defining the transport medium for the handoff is critical for the "physical" completeness of the interface.

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-19 20:42:07 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Requirement Section | Issue | Suggested Fix |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | completeness | high | REQ-PCG-006 Req 1-2 | `BudgetPropagationSpec` specifies `remaining_budget_ms` but accepted R6-S4 requires distinguishing execution time from wall time, and accepted R4-F3 requires supporting multiple budget types (tokens, cost). The requirement text still only mentions time. These accepted suggestions are not yet reflected in the requirement body. | Add: "BudgetPropagationSpec MUST support a `budget_unit` field (enum: `time_ms`, `tokens`, `cost_usd`) and per-phase allocations in the declared unit. `remaining_budget_ms` is the time-specific convenience alias. Budget tracking MUST distinguish compute time from wall-clock time for time-based budgets (per R6-S4)." |
| R7-F2 | architecture | high | REQ-PCG-020 (Gate 1) | The plan adds Gate 1 check #8 (artifact inventory / Mottainai provenance v2 cross-check) and accepted R6-S3 adds inline/external provenance reconciliation. These are potentially two separate checks (inventory completeness vs. provenance consistency) but the plan counts them as one check (#8). The total could be 8 or 9 depending on interpretation. | Explicitly enumerate all Gate 1 checks in the updated requirement with unambiguous numbering. If R6-S3 reconciliation is merged into existing check #3 (provenance cross-check), state this. If it's a separate check #9, update the count. |
| R7-F3 | clarity | high | REQ-PCG-009 Req 4 | "Existing `validate_phase_entry()` and `validate_phase_exit()` MUST remain unchanged" — accepted R1-F2 and R4-F4 both require documenting frozen interface signatures, but the plan only mentions adding a clarification note. The actual parameter types, return types, and error signaling are still unspecified. Without them, "unchanged" is unenforceable. | Add to REQ-PCG-009 or a linked appendix: the current function signatures including parameter names, types, return type, and exception behavior. Example: `validate_phase_entry(context: dict, phase: str) -> ValidationResult` (or whatever the actual signature is). |
| R7-F4 | security | medium | NFR-PCG-004 | The plan's Task 3 specifies an AST allowlist with max expression length (500 chars) and 1-second timeout, but accepted R9-S2 specifically identified that CI runs contract analysis on PR YAML from forks — meaning untrusted expressions reach the parser even if eval() isn't called. The plan's AST validation runs at Pydantic parse time, which IS during CI analysis. If the AST parser itself has vulnerabilities (e.g., deeply nested expressions causing stack overflow in `ast.parse`), the hardening has a gap. | Add to Task 3: "AST parsing MUST be wrapped in a try/except for RecursionError and MemoryError. Expressions with AST depth > 10 MUST be rejected. CI analysis on untrusted PR YAML MUST run expression validation in a subprocess with resource limits." |
| R7-F5 | completeness | medium | REQ-PCG-022 (Gate 3) | Accepted R8-S4 requires Gate 3 to verify no unaccounted artifacts exist (strict allowlist), and accepted R12-S7 requires explicit semantics for "Partial" status exit codes. The plan marks Gate 3 as "Partial" status but doesn't integrate these accepted suggestions into the Gate 3 requirement text or the plan's Task 1 changes. | Add to Task 1a or 1c: update REQ-PCG-022 requirements to include (a) strict artifact allowlist check per R8-S4, (b) explicit exit code semantics for Partial status per R12-S7: "Partial status MUST exit non-zero by default; `--allow-partial` flag MAY override to exit 0 with a WARNING gate result." |
| R7-F6 | completeness | medium | REQ-PCG-013 + REQ-PCG-014 | Accepted R8-S5 requires default injection to stamp "System Default" provenance, and accepted R10-S5 requires re-stamping value_hash when defaults are applied. The plan's Task 1d applies R4-S6 (stamp provenance on default injection) but doesn't mention the value_hash update or the "System Default" marker. These three accepted suggestions all target the same interaction but the plan only partially addresses it. | Consolidate R4-S6, R8-S5, and R10-S5 into a single coherent addition to REQ-PCG-013/014: "When defaults are injected, `PropagationTracker.stamp()` MUST be called with `origin_phase='system_default:{phase_name}'` and the value_hash MUST reflect the default value, not the absent value." |
| R7-F7 | testability | medium | Verification Plan | Accepted R13-S10 requires fault injection tests for the graceful degradation path (ContextCore not installed), and accepted R11-S4 requires testing `_cc_propagation` key behavior without ContextCore. The plan's Verification section doesn't include any degradation-path test — it only verifies that existing tests pass and eval() safety tests work. | Add to Verification section: "Run startd8-sdk stage 5-7 tests with ContextCore uninstalled (e.g., `pip uninstall contextcore && pytest tests/`); verify all pass with validation wrapper returning None." |

#### Review Round R8

- **Reviewer**: gemini-3 (gemini-3-pro-preview)
- **Date**: 2026-02-19 20:43:48 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Requirement Section | Issue | Suggested Fix |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R8-F1 | clarity | medium | REQ-PCG-021 (Gate 2) | Question 1 asks "Is the contract complete?" and checks "Artifact manifest population". However, Gate 1 runs *before* Plan Ingestion (Stage 5), while the Manifest is created in Stage 2. The timeline of when "Manifest" vs "Plan" exists is slightly ambiguous in the gate definitions. | Clarify that Gate 1 checks the *Exported* Manifest (from Stage 4) and Gate 2 checks the *Ingested* Plan (in Stage 5). |
| R8-F2 | scalability | medium | REQ-PCG-011 | "All contract enforcement actions MUST emit OTel span events". For high-throughput pipelines, this creates massive cardinality. | Add "Telemetry MUST support sampling or aggregation for high-frequency checks to prevent OTel backend saturation." |

#### Review Round R9 — Artisan Run 1 Deviation Analysis (Applied)

- **Reviewer**: human + claude-opus-4-6
- **Date**: 2026-02-19
- **Scope**: Post-mortem analysis of 5 production-blocking bugs from Artisan Run 1 (Python services). Mapped each defect to specific requirement gaps and applied amendments.
- **Source**: [ARTISAN_RUN1_DEVIATION_REPORT.md](../../../Processes/cap-dev-pipe-test/design/ARTISAN_RUN1_DEVIATION_REPORT.md)

| ID | Area | Severity | Applied Change | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R9-S1 | completeness | critical | **REQ-PCG-027.5 amended** — Added 5 self-consistency validation sub-requirements (5a–5e): dependency consistency, protocol fidelity, schema field validation, placeholder detection, Dockerfile/service coherence. | Artisan TEST phase (AR-140) only runs external linters (mypy, ruff, pylint). None catch semantic errors: HTTP client against gRPC service (DEV-001), missing `opentelemetry-exporter-otlp-proto-grpc` in requirements.in (DEV-003), `product_id` vs `product_ids` proto mismatch (DEV-005), gRPC health probe against Flask (DEV-004), placeholder SHA256 digest (DEV-002). All 5 bugs are self-consistency failures within the artisan's own output. |
| R9-S2 | completeness | critical | **REQ-PCG-022 amended** — Added requirement 6 (content-level verification) with 4 sub-requirements (6a–6d): placeholder scan, schema field cross-reference, cross-artifact consistency, protocol coherence. | Gate 3 (Finalize Verification) checks artifact existence and checksums but not content quality. A Dockerfile with `sha256:REPLACE_WITH_ACTUAL_DIGEST` passes Gate 3 because the file exists and has a valid checksum of its own bytes. Gate 3 is the last line of defense; it must validate content, not just existence. Status was "Partial" — these additions define what "complete" means. |
| R9-S3 | completeness | high | **REQ-PCG-024 amended** — Added requirement 7: `service_metadata` map in onboarding metadata with `transport_protocol` (REQUIRED), `schema_contract`, `base_image`, and `healthcheck_type` per service. | DEV-001 (HTTP client against gRPC) and DEV-004 (gRPC probe against Flask) both trace to the same root cause: the artisan had no structured signal for service protocol type. It defaulted to gRPC templates for all services. DEV-002 (placeholder digest) traces to missing `base_image` in resolvable parameters. Adding `service_metadata` to the handoff gives the artisan facts it cannot safely infer. |
| R9-S4 | completeness | medium | **REQ-PCG-032 amended** — Added requirement 6: per-service design calibration hints referencing `service_metadata`, including transport_protocol, healthcheck_type, and transport library. Added protocol-specific rows to the red flag table. | Design calibration hints covered artifact depth (LOC) but not service protocol classification. The artisan DESIGN phase had no structured signal to distinguish gRPC from HTTP services, leading to incorrect Dockerfile and client templates. |
| R9-S5 | completeness | medium | **REQ-PCG-027.3 amended** — DESIGN MUST consume `service_metadata` for protocol classification. | The DESIGN phase applied gRPC Dockerfile templates to an HTTP service (DEV-004) because it had no protocol classification input. |
| R9-S6 | completeness | medium | **REQ-PCG-027.4 amended** — IMPLEMENT MUST resolve all parameterized values; placeholder strings are a gate failure. | DEV-002 (placeholder digest) occurred because IMPLEMENT left an unresolved template string rather than failing when it couldn't resolve a parameter. |

#### Review Round R15 — Mottainai Violation Coverage

- **Reviewer**: human + claude-opus-4-6
- **Date**: 2026-02-19
- **Scope**: Close the requirements coverage gap for artifact reuse, enrichment propagation, and contractor resume semantics identified by the [Mottainai Design Principle](../../design-principles/MOTTAINAI_DESIGN_PRINCIPLE.md) (15 gaps + 3 observed failures from Artisan Run 1). Cross-references [Artisan Contractor Requirements](startd8-sdk: docs/ARTISAN_REQUIREMENTS.md) AR-xxx for artisan-level implementation detail.
- **Source**: Mottainai Design Principle document — Gaps 1–15, Failures 1–3; Run 1 evidence ($2.61 wasted on DESIGN re-derivation, 11 design documents overwritten, empty `onboarding` and `artifact_types_addressed: []` in all 17 seed tasks)

| ID | Area | Severity | Applied Change | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R15-S1 | completeness | critical | **REQ-PCG-024 amended** — Added requirements 8–9: onboarding enrichment fields (7 fields) MUST be available for end-to-end propagation; provenance chain MUST record which enrichment fields were available at export time. | Failure 3 root cause: `onboarding-metadata.json` contained 7 enrichment field sets but none reached the seed. Establishes handoff-level propagation contract for Gaps 1–7. |
| R15-S2 | completeness | critical | **REQ-PCG-026 amended** — Added requirements 6–7: EMIT MUST bridge all onboarding enrichment fields from export output directory into the context seed; absent `onboarding-metadata.json` MUST log WARNING (not silent omission). | Root cause of Failure 3 and Gaps 1–8 on the producer side. EMIT reads `onboarding-metadata.json` from `contextcore_export_dir`, populates seed `onboarding`, populates per-task `artifact_types_addressed`, and extracts REFINE suggestions. |
| R15-S3 | completeness | critical | **REQ-PCG-027 amended** — Added requirements 8–10: DESIGN MUST adopt prior valid designs (Mottainai rule 2); DESIGN MUST consume onboarding enrichment fields (cross-ref AR-303–308 for 5 of 7 fields, plus 5 fields NOT in AR); IMPLEMENT MUST reuse existing generated artifacts on retry. | Closes Failure 2 (adopted-status rejection), Gaps 1–8 consumer side, and retry regeneration waste. AR cross-refs avoid restating artisan-specific implementation detail. |
| R15-S4 | completeness | critical | **REQ-PCG-033 refined** — Replaced "Explicit Non-Goal" with scoped resumption: ContextCore half (non-goal, idempotent re-runs mitigate) vs. startd8-sdk half (contractor-level resume MUST be supported with multi-format task detection, artifact preservation, state file persistence, cost attribution logging). | Closes Failure 1 (batch result detection mismatch). Codifies fix from commit `21548e4`. Cross-refs AR-134 and AR-500–511 for artisan-level recovery mechanics. |
| R15-S5 | completeness | high | **REQ-PCG-036 added** — Onboarding Enrichment End-to-End Propagation (P1): 7 requirements covering field list, propagation path table with AR cross-refs, gap logging, deterministic precedence, per-task `artifact_types_addressed`, REFINE forwarding, TRANSFORM accessibility. | New cross-cutting requirement closing Gaps 1–8. References AR-303–308 for artisan consumption of 5 fields; adds governance for the 5 fields NOT covered by any AR. |
| R15-S6 | completeness | high | **REQ-PCG-037 added** — Contractor Resume and Artifact Preservation (P1): 6 requirements covering multi-format task detection, design three-way branch with "adopted" acceptance, generated file preservation, prime caching, cost attribution, structured skip/adopt logging. | New cross-cutting requirement closing Failures 1–2 and Gap 14. Governance layer over AR-122 (adopt prior) and AR-134 (resume), plus prime-specific requirements not in any AR. |
| R15-S7 | completeness | high | **REQ-PCG-038 added** — Prime Contractor Context Parity (P2): 6 requirements covering FeatureSpec metadata field, onboarding injection into code generation context, lightweight architectural context, per-task token budgets, REFINE forwarding, domain enrichment reuse. | New requirement closing Gaps 9–13 (prime-specific violations). No AR-xxx overlap — entirely new coverage for the prime route. |
| R15-S8 | completeness | medium | **REQ-PCG-039 added** — Source Artifact Type Coverage (P2): 6 requirements covering modular registry extension, source type registration, export output parity, existing artifact detection with ArtifactStatus, skip-existing task support, consolidation of 4 detection fragments. | New requirement closing Gap 15 (source types not registered). No AR-xxx overlap. |

