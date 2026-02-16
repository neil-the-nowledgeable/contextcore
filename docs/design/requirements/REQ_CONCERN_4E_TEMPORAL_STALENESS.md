# Temporal Staleness Requirements (Concern 4e)

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Parent:** [Context Correctness Extensions](../CONTEXT_CORRECTNESS_EXTENSIONS.md) -- Concern 4e
**Companion:** [Context Correctness by Construction](../CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)
**Depends on:** Checkpoint Recovery (Concern 10) for full value; Layer 4 RuntimeBoundaryGuard for enforcement

Purpose: define the behavioral requirements for temporal staleness detection -- the
contract extension that validates whether context fields remain temporally valid
when workflows checkpoint and resume after a delay.

This document is intentionally living guidance. Update it as the implementation evolves.

---

## Vision

Context propagation (Layer 1) verifies that a field *exists* at a boundary.
Schema compatibility (Layer 2) verifies that a field has the *right structure*.
Neither verifies that a field's value is still *temporally valid*.

When a workflow checkpoints at time T and resumes at time T+Delta, every context
field has an implicit validity interval. A model version stamped 24 hours ago is
probably fine. A RAG index snapshot stamped 3 days ago is probably stale. An API
key rotated since checkpoint time is definitely invalid. No signal fires.

Temporal staleness detection closes this gap. It extends `OrderingConstraintSpec`
with per-field `staleness_budget` declarations and integrates with
`BoundaryValidator` and `RuntimeBoundaryGuard` to validate freshness at resume
boundaries.

**Core principle:** A checkpoint preserves internal consistency. It does not
preserve external consistency. The passage of time is a channel through which
context silently degrades.

**Framework evidence:**
- **LangGraph:** Checkpoint recovery creates temporal gaps where context staleness is unchecked
- **AutoGen:** Asynchronous turn delivery creates ordering ambiguity from the perspective of context dependence
- **CrewAI:** Flow resumability trusts persisted state without re-validation

---

## Problem Statement

### The Failure Mode

1. A workflow reaches the `plan` phase and checkpoints. The context contains
   `model.version = "gpt-4-0125"` and `rag.index_snapshot = "idx-2026-02-15T10:00"`.
2. The workflow pauses for 48 hours.
3. On resume, the model has been rotated to `gpt-4-0215` and the RAG index has
   been rebuilt with new documents.
4. The `implement` phase runs with the stale context. It generates code using
   constraints optimized for the old model and retrieval results from a stale index.
5. No error. No warning. Subtly degraded output.

### Why It Is Hard

Checkpoints are designed for durability. The entire point is that you can resume
from the exact state you left. But "exact state" is only the *internal* state --
the external world has moved on. No checkpoint system validates whether the
internal state is still consistent with the external world on resume.

### The CS Parallel

This is **temporal logic** applied to distributed state. Specifically, it is the
**validity interval** concept from temporal databases (Snodgrass, 1987) -- every
fact has a time range during which it is valid. Context fields have implicit
validity intervals that are never checked.

---

## Requirements

### Schema Model

#### REQ-4E-001: OrderingConstraintSpec Model

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-001 |
| **Priority** | P1 |
| **Description** | Define an `OrderingConstraintSpec` Pydantic v2 model that declares per-field staleness budgets and stale-value behavior. |
| **Acceptance Criteria** | 1. Model uses `ConfigDict(extra="forbid")` consistent with all other contract models. 2. Fields: `constraint_id` (str, required, min_length=1), `field` (str, required, dot-path), `staleness_budget_seconds` (int, required, > 0), `on_stale` (ConstraintSeverity, required), `description` (Optional[str]). 3. Model validates that `staleness_budget_seconds` is positive. 4. Model is importable from `contextcore.contracts.staleness.schema`. |
| **Affected Files** | `src/contextcore/contracts/staleness/__init__.py` (new), `src/contextcore/contracts/staleness/schema.py` (new) |

#### REQ-4E-002: StalenessContractSpec Container Model

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-002 |
| **Priority** | P1 |
| **Description** | Define a `StalenessContractSpec` Pydantic v2 model that serves as the top-level container for a list of ordering constraints plus optional global configuration. |
| **Acceptance Criteria** | 1. Fields: `schema_version` (str, required), `ordering_constraints` (list[OrderingConstraintSpec], required, min 1 item), `default_staleness_budget_seconds` (Optional[int], default None -- used when a field has no explicit constraint). 2. Model uses `ConfigDict(extra="forbid")`. 3. Model is loadable from a YAML file via `model_validate()`. |
| **Affected Files** | `src/contextcore/contracts/staleness/schema.py` |

#### REQ-4E-003: CheckpointResumeRecord Model

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-003 |
| **Priority** | P1 |
| **Description** | Define a `CheckpointResumeRecord` Pydantic v2 model that captures metadata about a checkpoint-resume boundary, including who approved the resume and under what policy. |
| **Acceptance Criteria** | 1. Fields: `checkpoint_id` (str, required), `checkpoint_phase` (str, required), `checkpoint_time` (str, ISO 8601, required), `resume_time` (str, ISO 8601, required), `pause_duration_seconds` (float, computed from checkpoint_time and resume_time), `approved_by` (Optional[str] -- agent ID or "human"), `approval_policy` (Optional[str] -- e.g. "auto", "human_required", "orchestrator"), `approval_reason` (Optional[str]). 2. `pause_duration_seconds` is computed via a `@model_validator`. 3. Model uses `ConfigDict(extra="forbid")`. |
| **Affected Files** | `src/contextcore/contracts/staleness/schema.py` |

---

### Staleness Validation

#### REQ-4E-004: StalenessChecker Core Logic

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-004 |
| **Priority** | P1 |
| **Description** | Implement a `StalenessChecker` class that evaluates whether context fields have exceeded their staleness budgets at a given point in time. |
| **Acceptance Criteria** | 1. `check_field(field_path, provenance: FieldProvenance, constraint: OrderingConstraintSpec, current_time: datetime) -> StalenessResult`. 2. Computes age as `current_time - provenance.set_at`. 3. Returns `StalenessResult` with: `field` (str), `stale` (bool), `age_seconds` (float), `budget_seconds` (int), `overage_seconds` (float, 0 if not stale), `severity` (ConstraintSeverity), `message` (str). 4. Returns `stale=False` when age <= budget. Returns `stale=True` when age > budget. |
| **Affected Files** | `src/contextcore/contracts/staleness/checker.py` (new) |

#### REQ-4E-005: StalenessResult Model

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-005 |
| **Priority** | P1 |
| **Description** | Define a `StalenessResult` Pydantic v2 model that captures the result of checking a single field for staleness. |
| **Acceptance Criteria** | 1. Fields: `field` (str), `stale` (bool), `age_seconds` (float), `budget_seconds` (int), `overage_seconds` (float), `severity` (ConstraintSeverity), `message` (str). 2. Model uses `ConfigDict(extra="forbid")`. 3. Provides `to_dict()` method for OTel attribute conversion. |
| **Affected Files** | `src/contextcore/contracts/staleness/checker.py` |

#### REQ-4E-006: Batch Staleness Check

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-006 |
| **Priority** | P1 |
| **Description** | `StalenessChecker` must support batch validation of all ordering constraints against a context dict in a single call. |
| **Acceptance Criteria** | 1. `check_all(context: dict, staleness_contract: StalenessContractSpec, current_time: datetime) -> StalenessReport`. 2. For each constraint in `ordering_constraints`, retrieves `FieldProvenance` from `context[PROVENANCE_KEY][field]`. 3. If no provenance exists for a constrained field, reports it as stale with age = infinity and a diagnostic message. 4. `StalenessReport` contains: `results` (list[StalenessResult]), `stale_count` (int), `blocking_stale_count` (int), `overall_fresh` (bool -- True only if no BLOCKING fields are stale), `checkpoint_resume` (Optional[CheckpointResumeRecord]). |
| **Affected Files** | `src/contextcore/contracts/staleness/checker.py` |

---

### BoundaryValidator Extension

#### REQ-4E-007: Staleness Check at Resume Boundary

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-007 |
| **Priority** | P1 |
| **Description** | Extend `BoundaryValidator` to accept an optional `StalenessContractSpec` and run staleness checks alongside field presence checks at phase entry boundaries. |
| **Acceptance Criteria** | 1. New method `validate_entry_with_staleness(phase, context, contract, staleness_contract, current_time) -> ContractValidationResult`. 2. First runs standard `validate_entry()` for field presence. 3. Then runs `StalenessChecker.check_all()` for temporal validity. 4. Merges staleness results into the `ContractValidationResult`: stale BLOCKING fields are added to `blocking_failures`, stale WARNING fields are added to `warnings`. 5. Original field presence validation is not affected when `staleness_contract` is None (backward compatible). |
| **Affected Files** | `src/contextcore/contracts/propagation/validator.py` |

#### REQ-4E-008: Re-validation of Entry Requirements on Resume

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-008 |
| **Priority** | P2 |
| **Description** | When a checkpoint resume is detected, the validator must re-run the full entry validation of the *next* phase, not just staleness checks. Context that was valid at checkpoint time may have been externally invalidated. |
| **Acceptance Criteria** | 1. `validate_resume(phase, context, contract, staleness_contract, checkpoint_resume: CheckpointResumeRecord) -> ContractValidationResult`. 2. Calls `validate_entry()` to re-verify field presence (a field may have been removed from an external store during the pause). 3. Calls staleness check on all constrained fields. 4. Records the `CheckpointResumeRecord` in the result for audit. 5. The combined result reflects the worst status from both checks. |
| **Affected Files** | `src/contextcore/contracts/propagation/validator.py` |

---

### PropagationTracker Extension

#### REQ-4E-009: Timestamp-Aware Provenance Querying

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-009 |
| **Priority** | P1 |
| **Description** | `PropagationTracker` must expose a method to compute the age of a stamped field's provenance relative to a reference time. |
| **Acceptance Criteria** | 1. New method `get_field_age(context, field_path, reference_time: datetime) -> Optional[float]` returns age in seconds, or None if no provenance exists. 2. Parses `FieldProvenance.set_at` (ISO 8601) to compute delta. 3. Handles timezone-aware and timezone-naive datetimes consistently (all internal timestamps are UTC). |
| **Affected Files** | `src/contextcore/contracts/propagation/tracker.py` |

#### REQ-4E-010: Staleness-Aware Chain Check

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-010 |
| **Priority** | P2 |
| **Description** | `PropagationTracker.check_chain()` must optionally accept staleness constraints and factor temporal validity into chain status. |
| **Acceptance Criteria** | 1. New optional parameter `staleness_constraints: Optional[list[OrderingConstraintSpec]]` on `check_chain()`. 2. When provided, after verifying field presence (existing logic), checks whether any field in the chain (source, waypoints, destination) exceeds its staleness budget. 3. A chain whose fields are all present but temporally stale returns `ChainStatus.DEGRADED` with a message indicating which fields are stale. 4. When `staleness_constraints` is None, behavior is identical to current implementation (backward compatible). |
| **Affected Files** | `src/contextcore/contracts/propagation/tracker.py` |

---

### RuntimeBoundaryGuard Integration

#### REQ-4E-011: Guard Accepts Staleness Contract

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-011 |
| **Priority** | P1 |
| **Description** | `RuntimeBoundaryGuard.__init__()` must accept an optional `StalenessContractSpec` and pass it to boundary validation calls. |
| **Acceptance Criteria** | 1. New optional parameter `staleness_contract: Optional[StalenessContractSpec]` on `__init__()`. 2. When provided, `enter_phase()` uses `validate_entry_with_staleness()` instead of `validate_entry()`. 3. When not provided, behavior is identical to current implementation. 4. Enforcement mode (strict/permissive/audit) applies to staleness violations the same way it applies to field presence violations. |
| **Affected Files** | `src/contextcore/contracts/runtime/guard.py` |

#### REQ-4E-012: Guard Resume Method

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-012 |
| **Priority** | P2 |
| **Description** | `RuntimeBoundaryGuard` must expose a `resume_phase()` method specifically for checkpoint-resume boundaries that combines re-validation with staleness checking. |
| **Acceptance Criteria** | 1. `resume_phase(phase, context, checkpoint_resume: CheckpointResumeRecord) -> ContractValidationResult`. 2. Internally calls `validate_resume()` from the extended `BoundaryValidator`. 3. Records the result in `PhaseExecutionRecord` with a new field distinguishing resume from normal entry. 4. In strict mode, raises `BoundaryViolationError` if any BLOCKING staleness violation occurs. 5. The `CheckpointResumeRecord` is included in OTel emission for audit. |
| **Affected Files** | `src/contextcore/contracts/runtime/guard.py` |

---

### Approval Tracking

#### REQ-4E-013: Approval Required for Resume

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-013 |
| **Priority** | P2 |
| **Description** | The staleness contract must support declaring that resume from a checkpoint requires explicit approval, and the guard must enforce this. |
| **Acceptance Criteria** | 1. `StalenessContractSpec` gains optional fields: `approval_required` (bool, default False), `approval_policy` (Optional[str] -- "auto", "human_required", "human_or_orchestrator"). 2. When `approval_required=True` and `resume_phase()` is called, the `CheckpointResumeRecord.approved_by` must be non-None. If it is None, the guard treats this as a BLOCKING violation. 3. The approval policy is recorded in OTel span events for governance audit. |
| **Affected Files** | `src/contextcore/contracts/staleness/schema.py`, `src/contextcore/contracts/runtime/guard.py` |

#### REQ-4E-014: Approval Audit Trail via OTel

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-014 |
| **Priority** | P2 |
| **Description** | Every checkpoint-resume event -- whether approved, auto-approved, or rejected -- must emit an OTel span event for governance audit. |
| **Acceptance Criteria** | 1. Span event name: `context.staleness.checkpoint_resume`. 2. Attributes include: `checkpoint.id`, `checkpoint.phase`, `checkpoint.pause_duration_seconds`, `checkpoint.approved_by`, `checkpoint.approval_policy`, `checkpoint.stale_field_count`, `checkpoint.blocking_stale_count`, `checkpoint.overall_fresh`. 3. Follows the `_HAS_OTEL` guard + `_add_span_event()` pattern from `contracts/propagation/otel.py`. |
| **Affected Files** | `src/contextcore/contracts/staleness/otel.py` (new) |

---

### OTel Emission

#### REQ-4E-015: Staleness Violation Span Events

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-015 |
| **Priority** | P1 |
| **Description** | Each staleness violation must emit an OTel span event with sufficient detail for querying and alerting in Grafana. |
| **Acceptance Criteria** | 1. Span event name: `context.staleness.violation`. 2. Attributes: `staleness.field` (str), `staleness.age_seconds` (float), `staleness.budget_seconds` (int), `staleness.overage_seconds` (float), `staleness.severity` (str -- "blocking"/"warning"/"advisory"), `staleness.constraint_id` (str). 3. Follows the `_HAS_OTEL` guard + `_add_span_event()` pattern. 4. Function signature: `emit_staleness_violation(result: StalenessResult, constraint_id: str) -> None`. |
| **Affected Files** | `src/contextcore/contracts/staleness/otel.py` (new) |

#### REQ-4E-016: Staleness Summary Span Event

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-016 |
| **Priority** | P1 |
| **Description** | After batch staleness validation, emit a summary span event capturing the overall freshness status. |
| **Acceptance Criteria** | 1. Span event name: `context.staleness.summary`. 2. Attributes: `staleness.total_fields_checked` (int), `staleness.stale_count` (int), `staleness.blocking_stale_count` (int), `staleness.overall_fresh` (bool), `staleness.phase` (str), `staleness.direction` (str -- "resume" or "entry"). 3. Function signature: `emit_staleness_summary(report: StalenessReport, phase: str, direction: str) -> None`. 4. Follows the `_HAS_OTEL` guard + `_add_span_event()` pattern. |
| **Affected Files** | `src/contextcore/contracts/staleness/otel.py` |

---

### Configuration

#### REQ-4E-017: Per-Phase Staleness Budget Overrides

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-017 |
| **Priority** | P3 |
| **Description** | Staleness budgets must be overridable per phase, so that the same field can have different freshness requirements at different pipeline stages. |
| **Acceptance Criteria** | 1. `OrderingConstraintSpec` gains an optional `phase_overrides` field: `dict[str, int]` mapping phase name to staleness_budget_seconds. 2. `StalenessChecker.check_field()` accepts an optional `phase` parameter. When provided and the constraint has a matching phase override, the override budget is used instead of the default. 3. When no override exists for the current phase, the top-level `staleness_budget_seconds` is used. |
| **Affected Files** | `src/contextcore/contracts/staleness/schema.py`, `src/contextcore/contracts/staleness/checker.py` |

#### REQ-4E-018: Default Staleness Budget Fallback

| Field | Value |
|-------|-------|
| **ID** | REQ-4E-018 |
| **Priority** | P3 |
| **Description** | Fields with provenance but no explicit staleness constraint must be checkable against a configurable default budget. |
| **Acceptance Criteria** | 1. `StalenessContractSpec.default_staleness_budget_seconds` (from REQ-4E-002) serves as the fallback. 2. `StalenessChecker.check_all()` applies the default budget to any field that has provenance metadata but no explicit constraint, if `default_staleness_budget_seconds` is set. 3. When `default_staleness_budget_seconds` is None, unconstrained fields are not checked (current behavior). 4. Default-budget violations use severity `WARNING` (never BLOCKING). |
| **Affected Files** | `src/contextcore/contracts/staleness/checker.py` |

---

## Contract Schema

Example YAML contract for temporal staleness:

```yaml
schema_version: "1.0.0"
ordering_constraints:
  - constraint_id: "model_version_freshness"
    field: "model.version"
    staleness_budget_seconds: 86400  # 24 hours
    on_stale: WARNING
    description: "Model version must be re-validated if checkpoint pause exceeds 24h"

  - constraint_id: "retrieval_index_freshness"
    field: "rag.index_snapshot"
    staleness_budget_seconds: 3600  # 1 hour
    on_stale: BLOCKING
    description: "Index snapshot is stale after 1h; re-retrieval required"
    phase_overrides:
      validate: 7200  # More lenient during validation phase

  - constraint_id: "api_key_freshness"
    field: "auth.api_key_hash"
    staleness_budget_seconds: 43200  # 12 hours
    on_stale: BLOCKING
    description: "API keys may rotate; re-validate after 12h pause"

  - constraint_id: "prompt_template_freshness"
    field: "prompt.template.hash"
    staleness_budget_seconds: 172800  # 48 hours
    on_stale: WARNING
    description: "Prompt templates are relatively stable; warn after 48h"

default_staleness_budget_seconds: 604800  # 7 days for unconstrained fields
approval_required: false
approval_policy: "auto"
```

This contract composes with an existing `ContextContract` (Layer 1). Both are
loaded independently. At resume time, the `RuntimeBoundaryGuard` runs Layer 1
field presence checks AND staleness checks.

---

## Integration Points

### How Concern 4e Fits Into the Existing Layer Architecture

The parent document's Extensions document specifies that extensions add new
**contract types** that plug into existing layers. Temporal staleness does NOT
add a new layer. It adds a new contract type that the following existing layers
validate:

```
Layer 7: Regression Prevention
  + Gate: staleness violation rate must not increase between runs

Layer 6: Observability & Alerting
  + Alert: context.staleness.violation events with severity BLOCKING
  + Alert: checkpoint resume with stale_count > 0

Layer 5: Post-Execution Validation
  + Check: all fields in completed pipeline have age < staleness_budget

Layer 4: Runtime Boundary Checks                     <-- PRIMARY INTEGRATION
  + RuntimeBoundaryGuard.resume_phase() runs staleness checks
  + Enforcement mode (strict/permissive/audit) governs behavior

Layer 3: Pre-Flight Verification
  + Verify staleness budgets are declared for all critical fields
  + Verify staleness budgets are achievable (e.g., not < expected phase duration)

Layer 2: Static Analysis
  + Analyze staleness constraints against pipeline topology

Layer 1: Context Contracts (Declarations)
  + StalenessContractSpec declares ordering constraints as YAML
```

### Composition with Existing Components

| Existing Component | How Staleness Integrates |
|--------------------|------------------------|
| `FieldProvenance.set_at` (tracker.py) | Source of truth for field timestamps. Staleness checker reads this to compute age. No changes to FieldProvenance needed. |
| `BoundaryValidator` (validator.py) | New `validate_entry_with_staleness()` method composes field presence + staleness in sequence. |
| `RuntimeBoundaryGuard` (guard.py) | New `resume_phase()` method. Existing `enter_phase()` gains optional staleness awareness. |
| `ConstraintSeverity` (types.py) | Reused directly. `on_stale` uses the same BLOCKING/WARNING/ADVISORY model. No changes to types.py needed. |
| `ChainStatus` (types.py) | Stale chains return DEGRADED. Reused directly. No changes to types.py needed. |
| `PropagationTracker.stamp()` (tracker.py) | Already records ISO 8601 timestamps. No changes needed. |
| `_HAS_OTEL` + `_add_span_event()` pattern | New `staleness/otel.py` follows identical pattern. |

### Composition with Other Extensions

| Extension | Relationship |
|-----------|-------------|
| Concern 10 (Checkpoint Recovery) | Staleness checking is a *sub-capability* of checkpoint recovery. Full checkpoint recovery validates staleness + re-runs entry validation + optionally requires approval. Concern 4e provides the staleness primitives that Concern 10 orchestrates. |
| Concern 9 (Quality Propagation) | Quality and staleness are independent axes. A field can be fresh but low-quality, or stale but high-quality. Both should be checked at resume boundaries. |
| Concern 6e (Multi-Budget) | Time is a budget. The staleness budget is conceptually similar to a latency budget, but measured from stamp time rather than from pipeline start. Future unification could model staleness as a budget type. |
| Concern 7e (Version Lineage) | Version lineage records *which* configuration produced a field. Staleness checks *when* it was produced. Together: "this field was set by phase A using config version V at time T, and T was more than 24h ago." |

---

## Test Requirements

### Unit Tests

All tests must be placed in `tests/unit/contextcore/contracts/staleness/`.

| Test Area | Min Tests | Description |
|-----------|-----------|-------------|
| `OrderingConstraintSpec` model validation | 6 | Valid construction, missing fields rejected, non-positive budget rejected, `on_stale` accepts all `ConstraintSeverity` values, `extra="forbid"` rejects unknown fields, `phase_overrides` accepted |
| `StalenessContractSpec` model validation | 4 | Valid YAML round-trip, empty constraints rejected, default budget optional, approval fields optional |
| `CheckpointResumeRecord` model validation | 4 | Valid construction, `pause_duration_seconds` computed correctly, timezone handling, approval fields optional |
| `StalenessChecker.check_field()` | 8 | Fresh field (age < budget), stale field (age > budget), exact boundary (age == budget is fresh), missing provenance reports stale, each severity level, phase override used when present, fallback to default when no override |
| `StalenessChecker.check_all()` | 6 | All fresh returns `overall_fresh=True`, one BLOCKING stale returns `overall_fresh=False`, WARNING stale does not block, missing provenance handled, default budget fallback, empty constraints list |
| `BoundaryValidator.validate_entry_with_staleness()` | 5 | Staleness results merged into `ContractValidationResult`, BLOCKING stale adds to `blocking_failures`, WARNING stale adds to `warnings`, None staleness contract is backward compatible, combined field-missing + field-stale scenario |
| `PropagationTracker.get_field_age()` | 3 | Valid provenance returns age, missing provenance returns None, timezone-aware comparison |
| `RuntimeBoundaryGuard.resume_phase()` | 5 | Strict mode raises on BLOCKING stale, permissive mode logs, audit mode emits only, approval required but missing rejected, approval present accepted |
| OTel emission | 4 | Violation event emitted with correct attributes, summary event emitted, checkpoint resume event emitted, `_HAS_OTEL=False` degrades gracefully |
| **Total** | **45** | |

### Integration Tests

| Test | Description |
|------|-------------|
| Full pipeline with checkpoint-resume | Workflow checkpoints after `plan`, pauses, resumes. Staleness contract declares 1-second budget on a field. Verify BLOCKING staleness violation fires on resume. |
| Staleness + field presence combined | A resume boundary has both a missing field (Layer 1 violation) and a stale field (Concern 4e violation). Both are reported in the same `ContractValidationResult`. |
| YAML contract loading end-to-end | Load a staleness contract from YAML, construct `StalenessChecker`, validate against a context with stamped provenance. |

---

## Non-Requirements

This document explicitly does NOT cover:

1. **Automatic re-retrieval or re-computation of stale fields.** Staleness
   detection identifies *that* a field is stale. Recovery actions (re-retrieve,
   re-generate, re-authenticate) are the responsibility of the workflow runtime
   or Concern 10 (Checkpoint Recovery). The staleness contract can declare a
   `recovery` hint per constraint (as shown in the parent Extensions doc), but
   implementing recovery logic is out of scope.

2. **External state polling.** The checker does not query external systems to
   verify whether a field's value is still correct. It uses the `set_at`
   timestamp from `FieldProvenance` as a proxy for freshness. External
   validation (e.g., checking whether a model version is still deployed) is a
   separate capability.

3. **Causal ordering between pipeline instances.** This concern addresses
   temporal staleness *within* a single pipeline's checkpoint-resume cycle. It
   does not address ordering between concurrent pipeline instances (e.g., two
   workflows both checkpoint and resume with overlapping context). Cross-pipeline
   causal ordering is addressed by Concern 4 (Causal Ordering) in the parent
   design document.

4. **Automatic checkpoint creation.** This concern validates context freshness
   at resume boundaries. The decision of *when* to checkpoint is made by the
   workflow runtime (LangGraph, CrewAI, etc.), not by ContextCore.

5. **UI for approval workflows.** Approval tracking (REQ-4E-013, REQ-4E-014)
   records who approved a resume and under what policy. It does not provide a
   user interface for approval workflows. The approval is passed in
   programmatically via `CheckpointResumeRecord`.

6. **Real-time staleness monitoring.** This concern checks staleness at discrete
   resume boundaries. It does not provide a continuous monitoring loop that
   checks staleness in the background while a workflow is paused.

---

## Related Docs

- `docs/design/CONTEXT_CORRECTNESS_EXTENSIONS.md` -- Parent document (Concern 4e, Concern 10)
- `docs/design/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md` -- Foundational design (7-layer architecture)
- `src/contextcore/contracts/types.py` -- Canonical enums (ConstraintSeverity, ChainStatus, EnforcementMode)
- `src/contextcore/contracts/propagation/tracker.py` -- PropagationTracker, FieldProvenance
- `src/contextcore/contracts/propagation/validator.py` -- BoundaryValidator
- `src/contextcore/contracts/propagation/schema.py` -- FieldSpec, ContextContract
- `src/contextcore/contracts/runtime/guard.py` -- RuntimeBoundaryGuard, BoundaryViolationError
- `src/contextcore/contracts/propagation/otel.py` -- OTel emission pattern (_HAS_OTEL, _add_span_event)

### Theory References

- Snodgrass, R.T. (1987). *The Temporal Query Language TQuel*. ACM TODS 12(2).
  -- Temporal databases with validity intervals; theoretical basis for staleness budgets.
- Lamport, L. (1978). *Time, Clocks, and the Ordering of Events in a Distributed System*. CACM 21(7).
  -- Causal ordering in distributed systems.
