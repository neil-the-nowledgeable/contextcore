# REQ-10: Checkpoint Recovery Integrity

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Companion:** [CONTEXT_CORRECTNESS_EXTENSIONS.md](../CONTEXT_CORRECTNESS_EXTENSIONS.md) -- Concern 10
**Priority Tier:** Tier 2 (medium value, medium complexity)
**Estimated Implementation:** ~200 lines + tests

---

## Problem Statement

Long-running workflows checkpoint internal state and resume later. The
checkpoint preserves context integrity at checkpoint time T, but resume
happens at time T+Delta in a world that has changed:

- External data sources update (RAG index re-indexed, knowledge base refreshed).
- Model versions rotate (new weights deployed, prompt templates revised).
- Dependencies change (API contracts evolved, library versions bumped).

No existing checkpoint system validates whether the internal state is still
consistent with the external world on resume. The checkpoint is designed for
durability -- it faithfully restores *internal* state -- but the *external*
context against which that state was produced has moved on.

This is a **temporal variant** of context propagation. In the standard model
the "channel" is a sequence of phases. In checkpoint recovery the "channel"
is the passage of time during a pause. Information does not flow through
intermediate services -- it flows through time, and time degrades it.

**CS parallel:** Temporal logic and validity intervals from temporal databases
(Snodgrass, 1987). Every fact has a time range during which it is valid.
Context fields have implicit validity intervals that are never checked.

**Framework evidence:**
- LangGraph: Durable checkpoints with state snapshots; no resume validation.
- CrewAI: Resumable flows via state persistence; resume trusts persisted state.

---

## Requirements

### REQ-10-001: CheckpointIntegritySpec Pydantic Model

**Priority:** P1
**Description:**
Define a `CheckpointIntegritySpec` Pydantic v2 model that declares per-checkpoint
validation requirements. Each spec binds a `checkpoint_id` to a `phase`, and
declares an `on_resume` policy containing staleness checks, entry re-validation,
and approval requirements.

**Acceptance Criteria:**
- Model uses `ConfigDict(extra="forbid")` consistent with all contract models.
- `checkpoint_id` is a non-empty string, unique within the contract.
- `phase` is a non-empty string referencing a valid phase name.
- `on_resume` is a nested `CheckpointResumePolicy` model (see REQ-10-003).
- Model round-trips through `model_validate()` / `model_dump()` with the YAML
  schema from the companion design document.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/schema.py` (new)

---

### REQ-10-002: StalenessCheck Pydantic Model

**Priority:** P1
**Description:**
Define a `StalenessCheck` model representing a single field-level staleness
constraint. Each check declares: which context field to inspect, how long its
provenance timestamp remains valid, what severity to assign when stale, and
which recovery strategy to invoke.

**Acceptance Criteria:**
- `field` is a non-empty string (dot-path, e.g. `"rag.index_snapshot"`).
- `max_age_seconds` is a positive integer.
- `on_stale` is a `ConstraintSeverity` enum value (BLOCKING / WARNING / ADVISORY).
- `recovery` is a `RecoveryStrategy` enum value (see REQ-10-007).
- Optional `description` field for human-readable explanation.
- `ConfigDict(extra="forbid")`.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/schema.py` (new)

---

### REQ-10-003: CheckpointResumePolicy Pydantic Model

**Priority:** P1
**Description:**
Define a `CheckpointResumePolicy` model that aggregates the per-checkpoint
resume behavior: whether to re-run entry validation of the next phase,
the list of staleness checks, and approval requirements.

**Acceptance Criteria:**
- `revalidate_entry` is a boolean (default `True`). When true, the guard
  re-runs `BoundaryValidator.validate_entry()` for the next phase on resume.
- `staleness_checks` is a list of `StalenessCheck` models (may be empty).
- `approval_required` is a boolean (default `False`).
- `approval_policy` is an optional `ApprovalPolicy` enum value
  (see REQ-10-006), required when `approval_required` is true.
- Model validation rejects `approval_required=True` with `approval_policy=None`.
- `ConfigDict(extra="forbid")`.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/schema.py` (new)

---

### REQ-10-004: CheckpointValidator Class

**Priority:** P1
**Description:**
Implement a `CheckpointValidator` class that validates checkpoint staleness
on resume. It reads provenance timestamps from the context (via
`PropagationTracker.get_provenance()`), compares `set_at + max_age_seconds`
against the current wall-clock time, and produces a structured
`CheckpointResumeResult`.

**Acceptance Criteria:**
- `validate_resume(checkpoint_spec, context, resume_time=None)` is the
  primary method. `resume_time` defaults to `datetime.now(timezone.utc)`.
- For each `StalenessCheck` in the spec:
  - Retrieves `FieldProvenance` for the field from the context.
  - If provenance is missing, treats the field as stale (age = infinity).
  - Computes `elapsed = resume_time - set_at`.
  - If `elapsed > max_age_seconds`, marks the field as stale with its
    `on_stale` severity and `recovery` strategy.
- Returns a `CheckpointResumeResult` containing:
  - `checkpoint_id` (str)
  - `passed` (bool) -- false if any BLOCKING staleness check failed
  - `stale_fields` (list of per-field results with field name, elapsed
    seconds, max allowed, severity, recovery)
  - `fresh_fields` (list of field names that passed)
  - `missing_provenance` (list of field names with no provenance stamp)
  - `approval_required` (bool, from the resume policy)
- Does not itself enforce actions (no exceptions, no recovery execution).
  The guard layer (REQ-10-005) interprets the result.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/validator.py` (new)

---

### REQ-10-005: Layer 4 Integration -- Resume as Phase Entry

**Priority:** P1
**Description:**
Extend `RuntimeBoundaryGuard` (or provide a composable wrapper) so that a
checkpoint resume is treated as a phase entry boundary with additional
temporal constraints. On resume, the guard:

1. Runs `CheckpointValidator.validate_resume()` for the checkpoint spec.
2. If `revalidate_entry` is true, runs `BoundaryValidator.validate_entry()`
   for the next phase.
3. If `approval_required` is true, checks for an `ApprovalRecord` in the
   context (see REQ-10-006).
4. Combines results into a single pass/fail decision respecting the
   enforcement mode (strict / permissive / audit).

**Acceptance Criteria:**
- New method `resume_checkpoint(checkpoint_id, context, contract,
  checkpoint_specs)` on `RuntimeBoundaryGuard` or a `CheckpointGuard`
  wrapper.
- In strict mode, BLOCKING staleness failures raise
  `CheckpointStalenessError` (new exception class).
- In permissive mode, BLOCKING staleness failures are logged but execution
  continues.
- In audit mode, everything is logged and emitted via OTel, nothing blocks.
- `PhaseExecutionRecord` or a new `CheckpointResumeRecord` captures the
  resume validation results alongside entry validation results.
- Resume results are included in `WorkflowRunSummary` via `summarize()`.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/guard.py` (new)
- `src/contextcore/contracts/runtime/guard.py` (modification or import)

---

### REQ-10-006: Approval Tracking

**Priority:** P2
**Description:**
Define an `ApprovalPolicy` enum and an `ApprovalRecord` Pydantic model for
tracking who approved a checkpoint resume, when, and under what policy.

**Acceptance Criteria:**
- `ApprovalPolicy` enum with values: `human`, `orchestrator`,
  `human_or_orchestrator`, `auto_if_fresh` (auto-approve if no BLOCKING
  staleness, otherwise require approval).
- `ApprovalRecord` model with fields:
  - `approved_by` (str) -- identifier of the approver (agent ID or human ID)
  - `approved_at` (str) -- ISO 8601 timestamp
  - `policy` (ApprovalPolicy) -- which policy was applied
  - `checkpoint_id` (str)
  - `stale_fields_acknowledged` (list of str) -- fields that were stale but
    approved for continuation
  - `notes` (optional str) -- free-form justification
- `ConfigDict(extra="forbid")`.
- `ApprovalPolicy` and `ApprovalRecord` are importable from
  `contracts/checkpoint/schema.py`.
- The `CheckpointGuard` checks for `ApprovalRecord` in the context under a
  well-known key (e.g. `_cc_checkpoint_approvals.{checkpoint_id}`).

**Affected Files:**
- `src/contextcore/contracts/checkpoint/schema.py` (new)
- `src/contextcore/contracts/types.py` (new enum)

---

### REQ-10-007: RecoveryStrategy Enumeration

**Priority:** P1
**Description:**
Define a `RecoveryStrategy` enum enumerating the possible actions when a
checkpointed field is stale.

**Acceptance Criteria:**
- Values:
  - `re_retrieve` -- re-execute the retrieval phase for this field
  - `re_generate` -- re-execute the generation phase for this field
  - `log_and_continue` -- log the staleness, proceed without recovery
  - `fail` -- halt the pipeline; treat as BLOCKING regardless of severity
- Enum lives in `contracts/types.py` (canonical location for all enums).
- Convenience list `RECOVERY_STRATEGY_VALUES` exported alongside other value
  lists.

**Affected Files:**
- `src/contextcore/contracts/types.py`

---

### REQ-10-008: Recovery Handler Interface

**Priority:** P2
**Description:**
Define an abstract `RecoveryHandler` protocol (or ABC) that implementations
can use to execute recovery strategies. The checkpoint system does not
execute recovery itself -- it produces structured results indicating which
fields need recovery and with what strategy. A `RecoveryHandler` provides the
hook for framework-specific recovery execution.

**Acceptance Criteria:**
- `RecoveryHandler` is a `typing.Protocol` with a single method:
  `recover(field: str, strategy: RecoveryStrategy, context: dict) -> bool`
- Returns `True` if recovery succeeded, `False` otherwise.
- A `NoOpRecoveryHandler` default implementation logs and returns `False`.
- The `CheckpointGuard` accepts an optional `RecoveryHandler` and calls it
  for each stale field before re-evaluating staleness.
- Recovery attempts are recorded in the `CheckpointResumeResult` (field,
  strategy, attempted, succeeded).

**Affected Files:**
- `src/contextcore/contracts/checkpoint/recovery.py` (new)
- `src/contextcore/contracts/checkpoint/guard.py`

---

### REQ-10-009: OTel Emission for Checkpoint Resume

**Priority:** P1
**Description:**
Emit a span event on checkpoint resume following the `_HAS_OTEL` guard +
`_add_span_event()` pattern used by all existing contract layers.

**Acceptance Criteria:**
- Event name: `context.checkpoint.resume`
- Attributes:
  - `checkpoint.id` (str) -- the checkpoint identifier
  - `checkpoint.phase` (str) -- the phase this checkpoint follows
  - `checkpoint.passed` (bool) -- overall pass/fail
  - `checkpoint.stale_field_count` (int)
  - `checkpoint.fresh_field_count` (int)
  - `checkpoint.missing_provenance_count` (int)
  - `checkpoint.approval_required` (bool)
  - `checkpoint.approval_granted` (bool)
  - `checkpoint.enforcement_mode` (str) -- strict/permissive/audit
  - `checkpoint.max_staleness_seconds` (int) -- longest elapsed time among
    stale fields
- Per stale field, emit a child event `context.checkpoint.stale_field` with:
  - `checkpoint.stale.field` (str)
  - `checkpoint.stale.elapsed_seconds` (int)
  - `checkpoint.stale.max_age_seconds` (int)
  - `checkpoint.stale.severity` (str)
  - `checkpoint.stale.recovery` (str)
  - `checkpoint.stale.recovery_attempted` (bool)
  - `checkpoint.stale.recovery_succeeded` (bool)
- All emission is guarded by `_HAS_OTEL`; no crash when OTel is unavailable.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/otel.py` (new)

---

### REQ-10-010: Pre-Flight Validation of Checkpoint Specs

**Priority:** P2
**Description:**
At contract load time (Layer 3 -- pre-flight), validate that checkpoint
specs reference valid phases and that staleness check fields are declared in
the referenced phase's exit contract.

**Acceptance Criteria:**
- Implement `validate_checkpoint_specs(checkpoint_specs, contract)` function.
- For each `CheckpointIntegritySpec`:
  - `phase` must exist as a key in `contract.phases`.
  - Each `staleness_checks[].field` should appear in the referenced phase's
    exit `required` or `optional` field specs (WARNING if not found -- the
    field may be set dynamically).
- Returns a list of diagnostic messages (errors and warnings).
- Integrates with existing `PreflightChecker` pattern if one exists, or
  stands alone as a callable validator.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/preflight.py` (new)

---

### REQ-10-011: Graceful Degradation -- No Spec Means No Check

**Priority:** P1
**Description:**
The checkpoint recovery system must be fully backward compatible. Pipelines
that do not declare `checkpoint_integrity` specs must behave exactly as they
do today: no staleness checks, no approval gates, no additional validation
on resume.

**Acceptance Criteria:**
- `checkpoint_integrity` is an optional field on the contract model
  (default: empty list).
- `RuntimeBoundaryGuard` and all existing Layer 4 code paths are unaffected
  when no checkpoint specs are declared.
- Existing tests pass without modification.
- No new required fields are added to `ContextContract`.

**Affected Files:**
- `src/contextcore/contracts/propagation/schema.py` (optional field addition)
- `src/contextcore/contracts/checkpoint/guard.py`

---

### REQ-10-012: CheckpointResumeResult Model

**Priority:** P1
**Description:**
Define a structured result model for checkpoint resume validation, parallel
to `ContractValidationResult` from Layer 1.

**Acceptance Criteria:**
- `CheckpointResumeResult` Pydantic model with `ConfigDict(extra="forbid")`.
- Fields:
  - `checkpoint_id` (str)
  - `phase` (str)
  - `passed` (bool) -- false if any BLOCKING staleness check failed or
    required approval was not granted
  - `stale_fields` (list of `StalenessCheckResult`) -- each containing:
    field, elapsed_seconds, max_age_seconds, is_stale, severity, recovery,
    recovery_attempted, recovery_succeeded
  - `fresh_fields` (list of str)
  - `missing_provenance` (list of str)
  - `entry_revalidation` (optional `ContractValidationResult`) -- result of
    re-running entry validation, if `revalidate_entry` was true
  - `approval_status` (optional `ApprovalRecord` or None)
- `to_gate_result()` method for emission via `GateEmitter`, following the
  same pattern as `ContractValidationResult.to_gate_result()`.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/validator.py` (new)

---

### REQ-10-013: Provenance Timestamp Consumption

**Priority:** P1
**Description:**
The `CheckpointValidator` must consume `FieldProvenance.set_at` timestamps
stamped by `PropagationTracker.stamp()`. This creates a direct dependency
on Layer 1's provenance tracking -- checkpoint recovery does not introduce
a separate timestamping mechanism.

**Acceptance Criteria:**
- `CheckpointValidator` imports and uses `PropagationTracker.get_provenance()`.
- Staleness is computed as `resume_time - parse_iso(provenance.set_at)`.
- If `PropagationTracker` was not used during the pipeline run (no
  `_cc_propagation` key in context), all fields are treated as having
  missing provenance and reported accordingly (not as stale, not as fresh).
- ISO 8601 timestamp parsing handles both `Z` and `+00:00` timezone formats.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/validator.py` (new)

---

### REQ-10-014: Checkpoint Specs Stored Alongside Contract

**Priority:** P2
**Description:**
Checkpoint integrity specs must be declarable in the same YAML contract file
as phase boundary contracts and propagation chains. They are a peer to
`phases` and `propagation_chains`, not a separate file.

**Acceptance Criteria:**
- `ContextContract` gains an optional `checkpoint_integrity` field typed as
  `list[CheckpointIntegritySpec]` with a default of `[]`.
- Existing YAML contracts that lack `checkpoint_integrity` parse without
  error (backward compatible per REQ-10-011).
- The `checkpoint_integrity` list appears at the contract root level:
  ```yaml
  schema_version: "0.2.0"
  pipeline_id: my-pipeline
  phases: { ... }
  propagation_chains: [ ... ]
  checkpoint_integrity: [ ... ]   # NEW, optional
  ```

**Affected Files:**
- `src/contextcore/contracts/propagation/schema.py`
- `src/contextcore/contracts/checkpoint/schema.py`

---

### REQ-10-015: Staleness Severity Semantics

**Priority:** P2
**Description:**
Document and enforce the severity semantics for staleness checks, consistent
with the existing `ConstraintSeverity` model used throughout ContextCore.

**Acceptance Criteria:**
- `BLOCKING` staleness: `CheckpointResumeResult.passed` is `False`. In
  strict mode, raises `CheckpointStalenessError`. Recovery is attempted
  before declaring failure (if a `RecoveryHandler` is provided).
- `WARNING` staleness: `CheckpointResumeResult.passed` remains `True`, but
  the stale field is included in `stale_fields` and emitted via OTel.
  Recovery is attempted if a handler is provided.
- `ADVISORY` staleness: logged only. Included in OTel emission. No recovery
  attempted.
- These semantics mirror `BoundaryValidator`'s handling of `ConstraintSeverity`
  for field presence checks.

**Affected Files:**
- `src/contextcore/contracts/checkpoint/validator.py`
- `src/contextcore/contracts/checkpoint/guard.py`

---

### REQ-10-016: Unit Tests -- CheckpointValidator

**Priority:** P1
**Description:**
Comprehensive unit tests for `CheckpointValidator.validate_resume()`.

**Acceptance Criteria:**
- Test fresh fields (elapsed < max_age) produce `passed=True`, empty
  `stale_fields`.
- Test stale BLOCKING field produces `passed=False`.
- Test stale WARNING field produces `passed=True` with field in
  `stale_fields`.
- Test stale ADVISORY field produces `passed=True`, advisory logged.
- Test missing provenance (no `_cc_propagation` key) reports all fields as
  `missing_provenance`, not as stale.
- Test missing provenance for individual field (other fields have provenance).
- Test `revalidate_entry=True` triggers `BoundaryValidator.validate_entry()`
  and combines results.
- Test `approval_required=True` without approval record produces
  `passed=False`.
- Test `approval_required=True` with valid approval record produces
  `passed=True`.
- Test edge case: `max_age_seconds=0` (always stale on resume).
- Test edge case: empty `staleness_checks` list (no staleness validation,
  passes trivially).
- Test `resume_time` override for deterministic testing.
- Mock `PropagationTracker.get_provenance()` and
  `BoundaryValidator.validate_entry()`.
- Minimum 15 test cases.

**Affected Files:**
- `tests/unit/contextcore/contracts/checkpoint/test_checkpoint_validator.py` (new)

---

### REQ-10-017: Unit Tests -- CheckpointGuard Integration

**Priority:** P1
**Description:**
Unit tests for the checkpoint guard's integration with Layer 4.

**Acceptance Criteria:**
- Test strict mode raises `CheckpointStalenessError` on BLOCKING staleness.
- Test permissive mode logs but does not raise on BLOCKING staleness.
- Test audit mode logs and emits OTel but does not raise.
- Test `RecoveryHandler` is called for stale fields and its result is
  recorded.
- Test `NoOpRecoveryHandler` logs and returns `False`.
- Test OTel emission (mock `_add_span_event`) produces correct event name
  and attributes.
- Test that guard passes through cleanly when no checkpoint specs are
  declared.
- Test combined resume: staleness check + entry revalidation + approval.
- Minimum 10 test cases.

**Affected Files:**
- `tests/unit/contextcore/contracts/checkpoint/test_checkpoint_guard.py` (new)

---

### REQ-10-018: Unit Tests -- Pre-Flight Validation

**Priority:** P2
**Description:**
Unit tests for pre-flight validation of checkpoint specs against the contract.

**Acceptance Criteria:**
- Test valid spec referencing existing phase produces no errors.
- Test spec referencing non-existent phase produces error diagnostic.
- Test staleness check field not in phase exit spec produces warning.
- Test staleness check field in phase exit spec produces no warning.
- Test `approval_required=True` with missing `approval_policy` is rejected
  by Pydantic validation (model-level, not pre-flight).
- Minimum 5 test cases.

**Affected Files:**
- `tests/unit/contextcore/contracts/checkpoint/test_checkpoint_preflight.py` (new)

---

## Contract Schema

The full YAML contract schema for checkpoint recovery integrity. This is
declared alongside existing `phases` and `propagation_chains` in the
contract file.

```yaml
# --- Existing contract fields ---
schema_version: "0.2.0"
pipeline_id: "retrieval-augmented-generation"
phases:
  retrieve:
    exit:
      required:
        - name: retrieved_context
          severity: BLOCKING
        - name: rag.index_snapshot
          severity: BLOCKING
  generate:
    entry:
      required:
        - name: retrieved_context
          severity: BLOCKING
    exit:
      required:
        - name: generated_output
          severity: BLOCKING

propagation_chains:
  - chain_id: retrieval_to_generation
    source: { phase: retrieve, field: retrieved_context }
    destination: { phase: generate, field: retrieved_context }

# --- NEW: Checkpoint integrity specs ---
checkpoint_integrity:
  - checkpoint_id: "post_retrieval"
    phase: "retrieve"
    on_resume:
      revalidate_entry: true
      staleness_checks:
        - field: "rag.index_snapshot"
          max_age_seconds: 3600
          on_stale: BLOCKING
          recovery: "re_retrieve"
          description: "RAG index older than 1 hour requires re-retrieval"
        - field: "model.version"
          max_age_seconds: 86400
          on_stale: WARNING
          recovery: "log_and_continue"
          description: "Model version changes are logged but non-blocking"
      approval_required: false

  - checkpoint_id: "post_generation"
    phase: "generate"
    on_resume:
      revalidate_entry: true
      staleness_checks:
        - field: "prompt.template.hash"
          max_age_seconds: 43200
          on_stale: WARNING
          recovery: "re_generate"
          description: "Prompt template changes within 12 hours are warned"
      approval_required: true
      approval_policy: "human_or_orchestrator"
```

---

## Integration Points

### How This Fits Into Layers 1-7

Checkpoint recovery integrity does **not** add a new layer. It adds a new
**contract type** that the existing layers validate:

```
Layer 7: Regression Prevention
  Checkpoint staleness rates should not increase across releases.

Layer 6: Observability & Alerting
  context.checkpoint.resume and context.checkpoint.stale_field events
  enable alerting on chronic staleness patterns.

Layer 5: Post-Execution Validation
  After a resumed workflow completes, verify that recovery strategies
  executed successfully (if any).

Layer 4: Runtime Boundary Checks  <-- PRIMARY INTEGRATION POINT
  Resume boundary is treated as a phase entry boundary with additional
  temporal constraints. CheckpointGuard composes with RuntimeBoundaryGuard.

Layer 3: Pre-Flight Verification
  Validate that checkpoint specs reference valid phases and that staleness
  check fields are declared in phase exit contracts.

Layer 2: Static Analysis
  Analyze checkpoint coverage: are all long-running phases covered by
  checkpoint specs? Flag phases with no staleness constraints.

Layer 1: Context Contracts (Declarations)
  CheckpointIntegritySpec declared in YAML alongside phases and chains.
```

### Dependency on Existing Components

| Component | Dependency Type | How Used |
|-----------|----------------|----------|
| `PropagationTracker` | Read | Consumes `FieldProvenance.set_at` timestamps |
| `BoundaryValidator` | Delegate | Re-runs entry validation on resume |
| `RuntimeBoundaryGuard` | Compose | Resume is a specialized phase entry |
| `ConstraintSeverity` | Reuse | BLOCKING / WARNING / ADVISORY semantics |
| `EnforcementMode` | Reuse | strict / permissive / audit semantics |
| `ContractValidationResult` | Embed | Entry revalidation result nested in resume result |
| `ContextContract` | Extend | Optional `checkpoint_integrity` field added |

### New Module Structure

```
src/contextcore/contracts/checkpoint/
  __init__.py
  schema.py        # CheckpointIntegritySpec, StalenessCheck,
                   # CheckpointResumePolicy, ApprovalRecord
  validator.py     # CheckpointValidator, CheckpointResumeResult,
                   # StalenessCheckResult
  guard.py         # CheckpointGuard (Layer 4 integration)
  recovery.py      # RecoveryHandler protocol, NoOpRecoveryHandler
  preflight.py     # Pre-flight validation of checkpoint specs
  otel.py          # OTel emission helpers
```

---

## Test Requirements

| Test File | Coverage Target | Min Cases |
|-----------|----------------|-----------|
| `test_checkpoint_validator.py` | `CheckpointValidator.validate_resume()` | 15 |
| `test_checkpoint_guard.py` | `CheckpointGuard` + enforcement modes | 10 |
| `test_checkpoint_preflight.py` | Pre-flight spec validation | 5 |
| `test_checkpoint_schema.py` | Pydantic model validation + round-trip | 8 |
| `test_checkpoint_otel.py` | OTel emission with mock spans | 5 |
| **Total** | | **43** |

**Testing patterns (from existing codebase):**
- Mock OTel tracer: patch `_HAS_OTEL` and `_add_span_event` in the otel module.
- Mock `PropagationTracker.get_provenance()` to return controlled
  `FieldProvenance` instances with known `set_at` timestamps.
- Use `datetime` injection (`resume_time` parameter) for deterministic
  staleness computation.
- Pydantic `ConfigDict(extra="forbid")` ensures unknown fields are rejected
  in schema tests.

---

## Non-Requirements

This document explicitly does **not** require the following:

1. **Checkpoint persistence mechanism.** How checkpoints are stored and
   restored is the responsibility of the orchestration framework (LangGraph,
   CrewAI, custom). ContextCore validates the *context* after restoration,
   not the restoration mechanism itself.

2. **Automatic recovery execution.** The `RecoveryHandler` protocol provides
   a hook, but ContextCore does not implement re-retrieval, re-generation,
   or any other domain-specific recovery. Recovery is framework-specific.

3. **Checkpoint creation.** This concern addresses resume validation only.
   When and how to create checkpoints is an orchestration decision outside
   ContextCore's scope.

4. **Clock synchronization.** Staleness is computed against local wall-clock
   time. Clock skew between checkpoint creation and resume is the operator's
   responsibility. Staleness budgets should account for expected skew.

5. **Multi-checkpoint ordering.** If a workflow has multiple checkpoints,
   each is validated independently on resume. There is no requirement to
   validate the ordering or consistency between checkpoints.

6. **Approval UI or workflow.** The `ApprovalRecord` captures that approval
   happened, but ContextCore does not provide UI, chat integration, or
   workflow automation for obtaining approval. That is the responsibility of
   the orchestration layer.

7. **Real-time external state polling.** Staleness checks compare provenance
   timestamps against the clock. They do not poll external systems (RAG
   indexes, model registries) to verify current state. The staleness budget
   is a proxy for external change probability, not a guarantee of actual
   change.

8. **Backward migration of existing checkpoints.** Checkpoints created
   before `checkpoint_integrity` was declared are not retroactively
   validated. The system degrades gracefully: no spec means no check
   (REQ-10-011).
