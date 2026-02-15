# Context Propagation Contracts — Layer 1 Design

**Status:** Implemented
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.92
**Implementation:** `src/contextcore/contracts/propagation/` (62 tests)
**Related:**
- [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — theoretical foundation
- [ADR-001: Tasks as Spans](../adr/001-tasks-as-spans.md) — foundational architecture
- [A2A Contracts Design](A2A_CONTRACTS_DESIGN.md) — contract-first agent coordination
- [Weaver Cross-Repo Alignment Plan](../plans/WEAVER_CROSS_REPO_ALIGNMENT_PLAN.md) — Layer 3 (semantic conventions)
- [Design Principle: Context Propagation](../design-principles/context-propagation.md) — original gap analysis

---

## 1. Problem

Multi-phase workflow pipelines pass a shared context dictionary from phase to
phase. Each phase reads fields it needs, writes fields it produces, and the
context travels forward. This works until it doesn't — and when it doesn't,
the failure is silent.

The Artisan pipeline has 7 phases (plan → scaffold → design → implement →
test → review → finalize). During the WCP investigation (PI-006 through
PI-013), we discovered that domain classification — a critical upstream
decision — was not reaching downstream phases. All 12 tasks ran with
`domain: "unknown"`, silently disabling domain-specific prompt constraints,
validators, and token budgets. The system produced output. The output was
worse. No error was raised.

This happened because:

1. **No declaration** of what fields each phase requires
2. **No validation** that enrichment fields survived the phase chain
3. **No provenance** tracking of where a field was set and whether it arrived
4. **No signal** when a field degraded to its default value

The WCP epic ([WCP-001 through WCP-011](../design-principles/context-propagation.md))
fixed the immediate gaps with point solutions — inline span events, a
completeness check in finalize, dashboard panels. But point solutions don't
prevent the next gap. The system needs a **structural** answer.

---

## 2. Solution Overview

A contract system that treats context propagation like a type system for
workflow pipelines. Pipelines declare what context flows where in YAML
contracts. Validators enforce contracts at every phase boundary. Trackers
stamp provenance as context flows. OTel events make violations observable.

```
                    YAML Contract
                  (artisan-pipeline.contract.yaml)
                         │
                    ContractLoader
                     (parse + cache)
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        BoundaryValidator    PropagationTracker
        (entry/exit/enrichment)  (stamp + check chains)
              │                      │
              ▼                      ▼
    ContractValidationResult   PropagationChainResult
    (passed, field_results,    (INTACT/DEGRADED/BROKEN,
     blocking_failures,         source_present,
     propagation_status)        destination_present)
              │                      │
              └──────────┬───────────┘
                         ▼
               OTel Span Event Emission
               (context.boundary.entry,
                context.chain.validated,
                context.propagation_summary)
```

### Split Placement

The framework (schema models, loader, validators, tracker, OTel helpers) lives
in **ContextCore**. Concrete pipeline contracts (Artisan YAML) live in
**startd8-sdk**. This mirrors the existing split where ContextCore defines
abstractions and startd8-sdk consumes them.

| Component | Repo | Path |
|---|---|---|
| Schema models | ContextCore | `src/contextcore/contracts/propagation/schema.py` |
| YAML loader | ContextCore | `src/contextcore/contracts/propagation/loader.py` |
| Boundary validator | ContextCore | `src/contextcore/contracts/propagation/validator.py` |
| Propagation tracker | ContextCore | `src/contextcore/contracts/propagation/tracker.py` |
| OTel emission | ContextCore | `src/contextcore/contracts/propagation/otel.py` |
| Artisan contract | startd8-sdk | `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml` |
| Validation wrapper | startd8-sdk | `src/startd8/contractors/context_schema.py` |
| Orchestrator wiring | startd8-sdk | `src/startd8/contractors/artisan_contractor.py` |

---

## 3. Contract Format

Contracts are YAML files validated against Pydantic v2 models
(`ContextContract`). All models use `extra="forbid"` to reject unknown keys
at parse time.

### 3.1 Top-Level Structure

```yaml
schema_version: "0.1.0"        # SemVer, starts at 0.1.0 per Weaver convention
pipeline_id: artisan            # Which pipeline this governs
description: >
  Human-readable purpose.

phases:                         # Per-phase boundary contracts
  plan: { ... }
  implement: { ... }

propagation_chains:             # End-to-end field flow declarations
  - chain_id: domain_to_implement
    source: { phase: plan, field: domain_summary.domain }
    destination: { phase: implement, field: domain_summary.domain }
```

### 3.2 Phase Contracts

Each phase declares **entry** requirements (what it needs to start) and
**exit** requirements (what it must produce).

```yaml
implement:
  description: "Test construction + code development"
  entry:
    required:                   # MUST be present — blocks phase if absent
      - name: tasks
        type: list
        severity: blocking
      - name: design_results
        type: dict
        severity: blocking
    enrichment:                 # SHOULD propagate — degrades gracefully
      - name: domain_summary.domain
        type: str
        severity: warning
        default: "unknown"
        source_phase: plan
        description: "Domain classification from preflight"
  exit:
    required:
      - name: generation_results
        type: dict
        severity: blocking
    optional:
      - name: implementation
        type: dict
        severity: advisory
```

The **required** vs **enrichment** distinction is the key design decision.
Required fields block the phase. Enrichment fields degrade gracefully — the
validator applies the default value and continues, but emits a WARNING-level
signal. This models how real pipelines work: some context is load-bearing
(tasks list), some is quality-enhancing (domain constraints).

### 3.3 Field Specifications

Each field in a contract is a `FieldSpec`:

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | str | Yes | Dot-path field name (e.g. `domain_summary.domain`) |
| `type` | str | No | Expected Python type name. Default: `"str"` |
| `severity` | enum | No | `blocking` / `warning` / `advisory`. Default: `blocking` |
| `default` | any | No | Value to apply when field is absent. Default: `None` |
| `description` | str | No | Human-readable description |
| `source_phase` | str | No | Phase that originally produces this field |
| `constraints` | dict | No | Additional constraints (reserved for future use) |

**Dot-path resolution:** Fields like `domain_summary.domain` are resolved by
walking nested dicts. `context["domain_summary"]["domain"]` must exist and
be non-None.

### 3.4 Propagation Chains

Chains declare end-to-end field flow. Unlike per-phase contracts (which check
"is the field here right now?"), chains check "did the field flow correctly
from its source to its destination?"

```yaml
propagation_chains:
  - chain_id: domain_to_implement
    description: >
      Domain classification flows from plan preflight to implement phase
      where it constrains code generation prompts.
    source:
      phase: plan
      field: domain_summary.domain
    waypoints:                    # Intermediate phases (informational)
      - phase: design
        field: domain_summary.domain
    destination:
      phase: implement
      field: domain_summary.domain
    severity: warning             # Chain-level severity
    verification: "dest not in (None, '', 'unknown')"
```

**Chain components:**

| Component | Required | Description |
|---|---|---|
| `chain_id` | Yes | Unique identifier (used in OTel events, dashboards) |
| `source` | Yes | Phase + field where the value originates |
| `waypoints` | No | Intermediate phases it passes through |
| `destination` | Yes | Phase + field where the value must arrive |
| `severity` | No | Default: `warning` |
| `verification` | No | Python expression evaluated with `source` and `dest` variables |

**Verification expressions** are evaluated in a sandboxed scope with only
`context`, `source` (source field value), and `dest` (destination field value)
available. This allows semantic checks beyond presence:

```yaml
# Value must not be the default
verification: "dest not in (None, '', 'unknown')"

# Source and destination must match
verification: "source == dest"

# Destination must be non-empty list
verification: "len(dest) > 0"
```

---

## 4. Severity Model

The severity model maps directly to `ConstraintSeverity` from
`contracts/types.py:183`, reusing the existing enum rather than introducing
a new one.

### 4.1 Field Severity Behavior

| Severity | On Absence | Pass/Fail | Side Effect | Log Level |
|---|---|---|---|---|
| `BLOCKING` | Sets `passed=False` | Fails | Caller should halt phase | WARNING |
| `WARNING` | Applies default if available, continues | Passes | `PropagationStatus.DEFAULTED` | INFO |
| `ADVISORY` | Logs, continues | Passes | `PropagationStatus.PARTIAL` | DEBUG |

When a field with severity `WARNING` is absent and has a `default` value
specified, the validator **mutates the context dict** to inject the default.
This is intentional — downstream phases receive a usable value rather than
crashing, and the OTel event records that a default was applied.

When a field with severity `WARNING` is absent and has **no** default, the
validator records `DEFAULTED` status with `default_applied=False`. This
distinguishes "I applied a known default" from "the field is simply missing."

### 4.2 Chain Status

Chains use `ChainStatus` (added to `contracts/types.py`):

| Status | Meaning | When |
|---|---|---|
| `INTACT` | Field flowed correctly | Source present, destination present, destination non-empty, verification passes |
| `DEGRADED` | Field present but has default/empty value | Destination exists but value is `None`, `""`, `"unknown"`, `[]`, or `{}` |
| `BROKEN` | Field did not flow | Source absent, destination absent, or verification fails |

The degradation detection checks for common "silent default" values. This list
(`None, "", "unknown", [], {}`) was derived from the WCP investigation where
every propagation failure manifested as one of these sentinel values.

### 4.3 Propagation Status

The overall validation result uses `PropagationStatus` from
`contracts/types.py:247`:

| Status | Meaning |
|---|---|
| `PROPAGATED` | All fields present, no warnings |
| `DEFAULTED` | Some fields defaulted (warnings present, no blocking failures) |
| `PARTIAL` | Advisory-level absences only |
| `FAILED` | Blocking failures — phase should not proceed |

### 4.4 Mapping to Weaver Requirement Levels

Per the Weaver cross-repo alignment plan, the severity levels map to Weaver
terminology:

| Contract Severity | Weaver Level | Meaning |
|---|---|---|
| `blocking` | `required` | Phase cannot proceed without this field |
| `warning` | `recommended` | Should propagate, degrades gracefully |
| `advisory` | `opt_in` | Nice to have, informational only |

---

## 5. Validation Flow

### 5.1 Per-Phase Boundary Validation

At each phase transition, two levels of validation occur:

```
Phase N-1 completes
       │
       ▼
┌──────────────────────────┐
│ validate_phase_entry()    │  ← Existing (context_schema.py)
│ Checks: required keys     │     Raises PhaseContextError if missing
│ present and non-None      │     UNCHANGED — backward compatible
└──────────────────────────┘
       │ (passes)
       ▼
┌──────────────────────────┐
│ validate_phase_boundary() │  ← New (context_schema.py wrapper)
│ Checks: enrichment fields │     Applies defaults, emits OTel events
│ from contract YAML        │     Returns ContractValidationResult
└──────────────────────────┘
       │
       ▼
   Phase N executes
       │
       ▼
┌──────────────────────────┐
│ validate_phase_exit()     │  ← Existing (context_schema.py)
│ Checks: Pydantic output   │     Raises PhaseContextError if invalid
│ model construction        │     UNCHANGED — backward compatible
└──────────────────────────┘
```

**Critical design decision:** The existing `validate_phase_entry()` and
`validate_phase_exit()` are **preserved as-is**. They are the blocking
validation layer — if required context keys are missing, the phase does not
run. The contract system adds enrichment validation **on top**, not instead of.
This means:

- Existing callers are completely unchanged
- Contract validation is opt-in via `contract_path` parameter
- If ContextCore is not installed (e.g. in a minimal SDK deployment), the
  wrapper returns `None` and the existing validation still runs

### 5.2 Orchestrator Integration

The `ArtisanContractorWorkflow` orchestrator wires contract validation into
`_execute_phase()`:

```python
class ArtisanContractorWorkflow:
    def __init__(self, ..., contract_path: Path | None = None):
        self._contract_path = contract_path  # Opt-in

    def _execute_phase(self, phase, context, ...):
        # 1. Blocking entry validation (always runs)
        validate_phase_entry(phase, context)

        # 2. Enrichment validation (opt-in)
        if self._contract_path:
            result = validate_phase_boundary(
                phase, context, "entry", self._contract_path
            )
            if result:
                emit_boundary_result(result)  # OTel span event

        # 3. Phase execution
        result_dict = handler.execute(phase, context, ...)

        # 4. Blocking exit validation (always runs)
        validate_phase_exit(phase, context)
```

Callers that don't pass `contract_path` get identical behavior to before. This
is the "progressive adoption" path — you can add contracts to one pipeline at
a time.

### 5.3 Default Application

When the validator encounters a `WARNING`-severity field that is absent and has
a default value, it **writes the default into the context dict**:

```python
def _validate_field(spec: FieldSpec, context: dict) -> FieldValidationResult:
    present, value = _resolve_field(context, spec.name)

    if not present or value is None:
        if spec.severity == ConstraintSeverity.WARNING:
            if spec.default is not None:
                _set_field(context, spec.name, spec.default)
                return FieldValidationResult(
                    field=spec.name,
                    status=PropagationStatus.DEFAULTED,
                    default_applied=True,
                    message=f"Field '{spec.name}' defaulted to {spec.default!r}",
                )
```

This mutation is intentional and safe because:

1. The context dict is the shared mutable state of the pipeline (it's designed
   to be written to by phases)
2. The default values are declared in the contract YAML (reviewed in PRs)
3. The OTel event records that a default was applied (observable)
4. The phase receives a usable value instead of None/missing (better behavior)

**Dot-path writing:** For nested fields like `domain_summary.domain`, the
`_set_field()` helper creates intermediate dicts as needed:

```python
_set_field(context, "domain_summary.domain", "unknown")
# Equivalent to:
# context.setdefault("domain_summary", {})["domain"] = "unknown"
```

---

## 6. Provenance Tracking

### 6.1 Data Model

The `PropagationTracker` stamps provenance metadata into the context dict
itself, under the reserved key `_cc_propagation`:

```python
context = {
    "domain_summary": {"domain": "web_application"},
    "tasks": [...],
    # Provenance metadata — travels with the context
    "_cc_propagation": {
        "domain_summary.domain": FieldProvenance(
            origin_phase="plan",
            set_at="2026-02-15T10:30:00+00:00",
            value_hash="a1b2c3d4",
        ),
        "domain_constraints": FieldProvenance(
            origin_phase="implement",
            set_at="2026-02-15T10:31:00+00:00",
            value_hash="e5f6g7h8",
        ),
    },
}
```

**Why store provenance in the context dict?** Because the context dict is the
carrier. Provenance must travel with the data it describes, through the same
channel, subject to the same propagation dynamics. If provenance were stored
externally, it would itself be subject to propagation failures — a meta-problem.

**`FieldProvenance` fields:**

| Field | Type | Description |
|---|---|---|
| `origin_phase` | str | Phase that set this field |
| `set_at` | str | ISO 8601 timestamp |
| `value_hash` | str | `sha256(repr(value))[:8]` — detects value mutation |

The `value_hash` is a short hash of the value's repr. It doesn't store the
value (which could be large) but can detect if the value was mutated between
stamp and check. If phase A stamps domain as hash `a1b2c3d4` and phase F
reads domain with hash `e5f6g7h8`, the value was changed in transit.

### 6.2 Chain Verification Algorithm

```
check_chain(chain_spec, context):
    1. Resolve source field → (source_present, source_value)
    2. Resolve destination field → (dest_present, dest_value)
    3. Resolve waypoints → [wp_present, ...]

    if NOT source_present:
        return BROKEN ("Source absent")

    if NOT dest_present:
        return BROKEN ("Destination absent")

    if dest_value in (None, "", "unknown", [], {}):
        return DEGRADED ("Destination has default/empty value")

    if verification expression exists:
        eval(verification, {source, dest, context})
        if result is falsy:
            return BROKEN ("Verification failed")

    return INTACT
```

**Waypoint presence is informational, not blocking.** Waypoints track where a
field *should* pass through, but a missing waypoint doesn't break the chain if
the destination is present. This accommodates pipelines where phases may be
skipped or where the context dict is the carrier (all phases see the same dict,
so a field set in phase 1 is automatically visible in phase 5 without explicit
passing through phases 2-4).

### 6.3 End-of-Pipeline Validation

At the finalize phase, `validate_all_chains()` checks every declared
propagation chain and emits a summary:

```python
tracker = PropagationTracker()
chain_results = tracker.validate_all_chains(contract, context)
emit_propagation_summary(chain_results)

# Summary: 3/3 intact (100.0%), 0 degraded, 0 broken
# — or —
# Summary: 1/3 intact (33.3%), 1 degraded, 1 broken
```

This replaces the inline `_validate_propagation_completeness()` method that
was the WCP-004 point fix, with a contract-driven generalization. The inline
fallback is preserved for environments where ContextCore is not installed.

---

## 7. OTel Event Semantics

All events follow the ContextCore telemetry conventions and are emitted as
OTel span events on the current active span. If OTel is not installed, events
are logged only (no crash).

### 7.1 Boundary Events

**Event name:** `context.boundary.{direction}` where direction is `entry`,
`exit`, or `enrichment`.

| Attribute | Type | Description |
|---|---|---|
| `context.phase` | str | Phase name (e.g. `"implement"`) |
| `context.direction` | str | `"entry"`, `"exit"`, or `"enrichment"` |
| `context.passed` | bool | Whether validation passed |
| `context.propagation_status` | str | `propagated` / `defaulted` / `partial` / `failed` |
| `context.blocking_count` | int | Number of blocking failures |
| `context.warning_count` | int | Number of warnings |
| `context.blocking.{i}` | str | Name of the i-th blocking field (first 3) |

**TraceQL query — find phases with enrichment defaults:**
```traceql
{ name = "context.boundary.enrichment" && span.context.propagation_status = "defaulted" }
```

### 7.2 Chain Events

**Event names:**
- `context.chain.validated` — chain is INTACT
- `context.chain.degraded` — chain has default/empty destination
- `context.chain.broken` — chain failed (source absent, verification failed)

| Attribute | Type | Description |
|---|---|---|
| `context.chain_id` | str | Chain identifier (e.g. `"domain_to_implement"`) |
| `context.chain_status` | str | `intact` / `degraded` / `broken` |
| `context.source_present` | bool | Whether source field exists |
| `context.destination_present` | bool | Whether destination field exists |
| `context.message` | str | Human-readable explanation |

**TraceQL query — find broken chains:**
```traceql
{ name = "context.chain.broken" }
```

**TraceQL query — find degraded chains by chain ID:**
```traceql
{ name = "context.chain.degraded" && span.context.chain_id = "domain_to_implement" }
```

### 7.3 Summary Event

**Event name:** `context.propagation_summary`

Emitted once per pipeline run (typically at finalize), aggregating all chain
results.

| Attribute | Type | Description |
|---|---|---|
| `context.total_chains` | int | Total number of chains checked |
| `context.intact` | int | Count of INTACT chains |
| `context.degraded` | int | Count of DEGRADED chains |
| `context.broken` | int | Count of BROKEN chains |
| `context.completeness_pct` | float | `intact / total * 100` |

**TraceQL query — find runs with low completeness:**
```traceql
{ name = "context.propagation_summary" && span.context.completeness_pct < 100 }
```

### 7.4 Relationship to WCP Events

The Layer 1 events supersede the WCP inline events:

| WCP Event | Layer 1 Replacement |
|---|---|
| `context.propagated` (WCP-003) | `context.boundary.enrichment` + `PropagationTracker.stamp()` |
| `context.defaulted` (WCP-003) | `context.boundary.enrichment` with `propagation_status=defaulted` |
| `context.propagation_summary` (WCP-004) | `context.propagation_summary` (same name, driven by contract chains) |

The startd8-sdk integration preserves the WCP-003/WCP-004 inline code as
a **fallback** when ContextCore is not installed. Both paths produce compatible
event schemas — dashboards and queries work with either.

---

## 8. The Artisan Pipeline Contract

The reference contract declares all 7 Artisan phases and 3 propagation chains.

### 8.1 Phase Summary

| Phase | Entry Required | Entry Enrichment | Exit Required |
|---|---|---|---|
| plan | `project_root` | — | `enriched_seed_path`, `tasks`, `task_index`, `plan_title`, `plan_goals`, `domain_summary`, `preflight_summary`, `total_estimated_loc` |
| scaffold | `tasks`, `task_index`, `project_root` | — | `scaffold` |
| design | `tasks`, `task_index` | — | `design_results` |
| implement | `tasks`, `design_results` | `domain_summary.domain` (default: `"unknown"`), `domain_summary.prompt_constraints` (default: `[]`), `domain_summary.post_generation_validators` (default: `[]`), `design_calibration` (advisory) | `implementation`, `generation_results` |
| test | `tasks`, `generation_results` | `domain_summary.post_generation_validators` (default: `[]`) | `test_results` |
| review | `generation_results` | — | `review_results` |
| finalize | `tasks`, `generation_results` | — | `workflow_summary` |

### 8.2 Propagation Chains

```
Chain 1: domain_to_implement (WARNING)
    plan.domain_summary.domain ──────────────→ implement.domain_summary.domain
    Verification: dest not in (None, '', 'unknown')

Chain 2: validators_to_test (WARNING)
    plan.domain_summary.post_generation_validators
        │
        └─→ implement.domain_summary.post_generation_validators (waypoint)
                │
                └─→ test.domain_summary.post_generation_validators

Chain 3: calibration_to_implement (ADVISORY)
    plan.design_calibration ─────────────────→ implement.design_calibration
```

**Chain 1** is the one that failed silently in PI-006 through PI-013. With the
contract system, the `DEGRADED` status would have fired at the implement phase
boundary, producing an observable signal in the first run — not the twelfth.

---

## 9. Adoption Path

### 9.1 For Existing Pipelines

1. **Start with declaration only.** Write a YAML contract for your pipeline.
   This costs nothing — it's a documentation exercise that happens to be
   machine-parseable.

2. **Add the loader.** Pass `contract_path` to your orchestrator. The
   enrichment validator runs, emits events, but doesn't block anything (all
   enrichment fields are `WARNING` or `ADVISORY`).

3. **Monitor.** Build a dashboard panel for `context.propagation_summary`
   events. Watch the `completeness_pct` metric over time.

4. **Tighten.** As you gain confidence, promote fields from `advisory` →
   `warning` → `blocking`. Add `verification` expressions. Add more chains.

This mirrors TypeScript's adoption path: start with `any`, add types
incrementally, turn on strict mode when ready.

### 9.2 For New Pipelines

Write the contract YAML alongside the pipeline definition. Review it in the
same PR. This is the "design-time guarantee" — before any code runs, the
contract declares the information flow requirements.

### 9.3 For Non-Artisan Pipelines

The framework is generic. Any pipeline that uses a shared mutable context dict
(which is every pipeline) can define a contract YAML. The only Artisan-specific
artifact is `artisan-pipeline.contract.yaml` itself.

---

## 10. Dashboard Integration

### 10.1 Recommended Panels

**Propagation Completeness (Stat panel)**
```traceql
{ name = "context.propagation_summary" }
| select(span.context.completeness_pct)
```

**Broken Chains Over Time (Time series)**
```traceql
{ name =~ "context.chain.*" && span.context.chain_status != "intact" }
| rate()
```

**Chain Health by Pipeline Run (Table)**
```traceql
{ name = "context.propagation_summary" }
| select(
    span.context.total_chains,
    span.context.intact,
    span.context.degraded,
    span.context.broken,
    span.context.completeness_pct
  )
```

**Enrichment Defaults Applied (Logs panel)**
```traceql
{ name = "context.boundary.enrichment" && span.context.propagation_status = "defaulted" }
```

### 10.2 Alerting Rules

**Alert: Propagation completeness below threshold**
```yaml
- alert: ContextPropagationDegraded
  expr: |
    sum(rate({job="artisan"} | json | event="context.propagation_summary"
      | completeness_pct < 100 [5m])) > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Context propagation chains are not fully intact"
```

**Alert: Broken propagation chain**
```yaml
- alert: ContextChainBroken
  expr: |
    count_over_time({job="artisan"} | json | event="context.chain.broken" [15m]) > 0
  for: 0m
  labels:
    severity: critical
  annotations:
    summary: "A context propagation chain is broken — field not reaching destination"
```

---

## 11. Patterns Reused

The implementation deliberately reuses patterns from the existing A2A contract
system to maintain consistency:

| Pattern | Source | Usage in Propagation |
|---|---|---|
| `extra="forbid"` | `a2a/models.py` | All Pydantic models reject unknown fields |
| `_VALIDATORS` cache | `a2a/validator.py:73` | `ContractLoader._cache` per-path |
| `_enforce()` + error reporting | `a2a/boundary.py:135-161` | `BoundaryValidator._validate_fields()` |
| `_emit_failure_event()` | `a2a/boundary.py:99-132` | `emit_boundary_result()` |
| `_HAS_OTEL` guard | `a2a/boundary.py:34-39` | `otel.py:_HAS_OTEL` |
| `ValidationErrorEnvelope` | `a2a/validator.py:91` | `FieldValidationResult` |
| `ConstraintSeverity` enum | `contracts/types.py:183` | Reused directly (not duplicated) |
| `PropagationStatus` enum | `contracts/types.py:247` | Reused directly |
| `PhaseContextError` | `context_schema.py:28` | Raised by existing validators (unchanged) |

---

## 12. Consequences

### Positive

1. **Silent degradation becomes impossible.** Every propagation failure produces
   an observable signal — span event, log, or blocking error.
2. **Contracts are reviewable artifacts.** YAML files in PRs, not implicit
   assumptions in handler code.
3. **Progressive adoption.** Fully opt-in. Existing pipelines unchanged until
   `contract_path` is provided.
4. **Framework is generic.** Not tied to Artisan — any pipeline can define
   contracts.
5. **Meta-observable.** The contract system itself emits OTel events,
   queryable through the same infrastructure.

### Neutral

1. **YAML contract must be maintained.** When phases change, the contract must
   be updated. This is the same cost as maintaining type annotations in code.
2. **Default application mutates context.** The validator writes defaults into
   the context dict. This is intentional but requires awareness.

### Negative

1. **Verification expressions use `eval()`.** Sandboxed (no builtins), but
   still eval. If contract YAML comes from untrusted sources, this is a risk.
   For our use case (contracts checked into the repo alongside code), this is
   acceptable.
2. **Dot-path resolution is simple.** Does not handle list indexing
   (`tasks[0].domain`). If needed, a more sophisticated path resolver can be
   added later.
3. **Provenance stored in context dict.** Adds a `_cc_propagation` key that
   handlers must not accidentally overwrite. The key uses a `_cc_` prefix to
   signal "internal, do not touch."

---

## 13. Future Work

1. **Static analysis (Layer 2).** Walk the requires/produces graph at
   `contextcore manifest validate` time to find dangling reads, dead writes,
   and shadow defaults — before any workflow runs.
2. **Pre-flight verification (Layer 3).** Before `workflow.execute()`, validate
   that the initial context satisfies all chain sources.
3. **CI integration (Layer 7).** GitHub Action that loads the contract YAML,
   checks for regressions (removed fields, weakened severity), and blocks PRs
   that break propagation contracts.
4. **Weaver registry integration.** Register propagation event names
   (`context.boundary.*`, `context.chain.*`, `context.propagation_summary`)
   in the Weaver semconv registry when Phase 1 lands.
5. **List-path resolution.** Support `tasks[*].domain` patterns for validating
   that every item in a list has a required field.
6. **Cross-pipeline chains.** Chains that span multiple pipeline contracts
   (e.g. domain classification in pipeline A must reach code generation in
   pipeline B).

---

## Appendix A: Complete File Inventory

| File | Lines | Tests |
|---|---|---|
| `contracts/propagation/__init__.py` | 83 | — |
| `contracts/propagation/schema.py` | 184 | 10 |
| `contracts/propagation/loader.py` | 86 | 7 |
| `contracts/propagation/validator.py` | 326 | 13 |
| `contracts/propagation/tracker.py` | 264 | 19 |
| `contracts/propagation/otel.py` | 153 | 10 |
| `contracts/types.py` (modified) | +9 | — |
| `contracts/__init__.py` (modified) | +10 | — |
| **Total** | **1,115** | **59** |

Plus 3 files in startd8-sdk (contract YAML, validation wrapper, orchestrator
wiring) and 6 SDK tests.

## Appendix B: Type Hierarchy

```
ContextContract
├── schema_version: str
├── pipeline_id: str
├── description: str?
├── phases: dict[str, PhaseContract]
│   └── PhaseContract
│       ├── description: str?
│       ├── entry: PhaseEntryContract
│       │   ├── required: list[FieldSpec]
│       │   └── enrichment: list[FieldSpec]
│       └── exit: PhaseExitContract
│           ├── required: list[FieldSpec]
│           └── optional: list[FieldSpec]
└── propagation_chains: list[PropagationChainSpec]
    └── PropagationChainSpec
        ├── chain_id: str
        ├── source: ChainEndpoint {phase, field}
        ├── waypoints: list[ChainEndpoint]
        ├── destination: ChainEndpoint {phase, field}
        ├── severity: ConstraintSeverity
        └── verification: str?

FieldSpec
├── name: str              (dot-path, e.g. "domain_summary.domain")
├── type: str              (Python type name)
├── severity: ConstraintSeverity  (blocking | warning | advisory)
├── default: Any?          (applied when field absent + severity=warning)
├── description: str?
├── source_phase: str?
└── constraints: dict?
```
