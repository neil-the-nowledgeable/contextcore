# REQ-CONCERN-13: Evaluation-Gated Propagation

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Companion doc:** [Context Correctness Extensions](../CONTEXT_CORRECTNESS_EXTENSIONS.md) -- Concern 13
**CS parallel:** Proof-Carrying Code (Necula, 1997) -- outputs carry evaluation proofs of fitness

---

## Problem Statement

Some phase outputs need to be *evaluated* -- by a model, a metric, or a human --
before propagating to the next phase. An output may exist (passes Concern 1
propagation check), have valid structure (passes Concern 2 schema check), and
even have acceptable quality metrics (passes Concern 9 quality check). But it
has not been *judged* as fit for downstream use.

An un-evaluated output that propagates is a quality risk. The evaluation is a
signal: "a qualified observer confirmed this output is fit for use." Without
that signal, fitness is *assumed* -- and assumptions are where silent degradation
lives.

Current `FieldSpec` in `contracts/propagation/schema.py` declares field presence
and severity. Current `BoundaryValidator._validate_field()` in
`contracts/propagation/validator.py` checks presence and applies defaults. Current
`FieldProvenance` in `contracts/propagation/tracker.py` records `origin_phase`,
`set_at`, and `value_hash`. None of these capture whether a field's value has been
evaluated, by whom, with what score, or whether the evaluation passed.

**Framework evidence:**
- OpenAI Agents SDK: eval/trace grading hooks exist but are optional and post-execution
- DSPy: metric-driven validation during optimization loops, not production boundary gates
- LlamaIndex: retrieval evaluation patterns exist as separate pipeline steps, not boundary constraints

All three frameworks *can* evaluate. None *require* evaluation as a propagation
precondition.

---

## Requirements

### REQ-13-001: EvaluationPolicy Enum

**Priority:** P1
**Description:** Define an `EvaluationPolicy` string enum in `contracts/types.py`
with values representing who/what may perform the evaluation.

**Values:**
- `score_threshold` -- any evaluator; pass/fail determined by score >= threshold
- `human_or_model` -- either a human or a model evaluator is acceptable
- `human_required` -- only a human evaluator satisfies the gate
- `any_evaluator` -- any evaluator, no threshold required (presence-only)

**Acceptance Criteria:**
- [ ] `EvaluationPolicy` is a `str, Enum` subclass in `contracts/types.py`
- [ ] Follows the existing naming convention (`SCORE_THRESHOLD = "score_threshold"`, etc.)
- [ ] `EVALUATION_POLICY_VALUES` convenience list is exported
- [ ] No import changes needed in existing modules

**Affected files:**
- `src/contextcore/contracts/types.py`

---

### REQ-13-002: EvaluationSpec Pydantic Model

**Priority:** P1
**Description:** Define an `EvaluationSpec` Pydantic v2 model in
`contracts/propagation/schema.py` that declares the evaluation requirements for
a single field.

**Fields:**
- `required: bool` -- must evaluation happen before propagation? (default: `False`)
- `policy: EvaluationPolicy` -- which evaluation policy applies (default: `score_threshold`)
- `threshold: float` -- minimum acceptable score (default: `0.0`, range 0.0-1.0)
- `evaluator: Optional[str]` -- expected evaluator identifier (default: `None`, meaning any)
- `on_unevaluated: ConstraintSeverity` -- severity when evaluation is missing (default: `BLOCKING`)
- `on_below_threshold: ConstraintSeverity` -- severity when score is below threshold (default: `WARNING`)
- `description: Optional[str]` -- human-readable description

**Acceptance Criteria:**
- [ ] `EvaluationSpec` uses `ConfigDict(extra="forbid")` per project convention
- [ ] `threshold` field has `ge=0.0, le=1.0` validators
- [ ] All severity fields use `ConstraintSeverity` enum from `contracts/types.py`
- [ ] Model is importable from `contextcore.contracts.propagation.schema`

**Affected files:**
- `src/contextcore/contracts/propagation/schema.py`

---

### REQ-13-003: FieldSpec Extension with Optional Evaluation

**Priority:** P1
**Description:** Extend the existing `FieldSpec` model in
`contracts/propagation/schema.py` with an optional `evaluation` field of type
`EvaluationSpec`.

**Acceptance Criteria:**
- [ ] `FieldSpec.evaluation` is `Optional[EvaluationSpec]` with default `None`
- [ ] Existing contracts without `evaluation` parse unchanged (backward compatible)
- [ ] `extra="forbid"` still rejects unknown keys
- [ ] Existing tests continue to pass without modification

**Affected files:**
- `src/contextcore/contracts/propagation/schema.py`

---

### REQ-13-004: EvaluationResult Model

**Priority:** P1
**Description:** Define an `EvaluationResult` dataclass or Pydantic model to
represent the outcome of a single evaluation. This is the "evaluation proof"
that travels with the context.

**Fields:**
- `evaluator: str` -- identifier of who/what performed the evaluation
- `score: float` -- numeric evaluation score (0.0-1.0)
- `passed: bool` -- whether the evaluation passed the threshold
- `timestamp: str` -- ISO 8601 timestamp of when evaluation occurred
- `policy_applied: str` -- which `EvaluationPolicy` was applied
- `threshold_applied: float` -- what threshold was used

**Acceptance Criteria:**
- [ ] `EvaluationResult` is a dataclass in `contracts/propagation/tracker.py`
  (alongside existing `FieldProvenance` and `PropagationChainResult`)
- [ ] Has a `to_dict()` method following the pattern of `FieldProvenance.to_dict()`
- [ ] `score` is constrained to 0.0-1.0 range
- [ ] `timestamp` defaults to `datetime.now(timezone.utc).isoformat()` when not provided

**Affected files:**
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-13-005: FieldProvenance Extension with Evaluation Stamp

**Priority:** P1
**Description:** Extend the existing `FieldProvenance` dataclass in
`contracts/propagation/tracker.py` with optional evaluation stamp fields.

**New fields (all optional, default `None`):**
- `evaluated_by: Optional[str]` -- evaluator identifier
- `evaluation_score: Optional[float]` -- score assigned
- `evaluation_timestamp: Optional[str]` -- when evaluation occurred

**Acceptance Criteria:**
- [ ] New fields default to `None` (backward compatible with existing stamps)
- [ ] `to_dict()` includes evaluation fields only when they are not `None`
- [ ] Existing `stamp()` calls continue to work without providing evaluation data
- [ ] Evaluation stamp fields are independently settable (can stamp evaluation
  after initial provenance stamp)

**Affected files:**
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-13-006: PropagationTracker.stamp_evaluation()

**Priority:** P1
**Description:** Add a `stamp_evaluation()` method to `PropagationTracker` that
records an evaluation result against an existing field provenance record.

**Signature:**
```python
def stamp_evaluation(
    self,
    context: dict[str, Any],
    field_path: str,
    evaluator: str,
    score: float,
    passed: bool,
) -> EvaluationResult:
```

**Behavior:**
1. Look up existing `FieldProvenance` for `field_path` in context
2. If no provenance exists, log a warning and create a minimal provenance record
3. Update the provenance with `evaluated_by`, `evaluation_score`, `evaluation_timestamp`
4. Return an `EvaluationResult` capturing the full evaluation outcome

**Acceptance Criteria:**
- [ ] Updates `context[PROVENANCE_KEY][field_path]` in place
- [ ] Returns `EvaluationResult` with all fields populated
- [ ] Logs at DEBUG level on success, WARNING if no prior provenance
- [ ] Does not modify the field value itself (evaluation is metadata-only)

**Affected files:**
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-13-007: BoundaryValidator 3-Step Evaluation Check

**Priority:** P1
**Description:** Extend `_validate_field()` in `contracts/propagation/validator.py`
to perform a 3-step validation sequence when `FieldSpec.evaluation` is present.

**Validation sequence:**
1. **Exists check** (existing) -- is the field present in context?
2. **Schema check** (existing) -- does the value match the expected type/constraints?
3. **Evaluation check** (new) -- has the field been evaluated, and did it pass?

**Step 3 logic:**
- If `evaluation.required` is `False`, skip evaluation check
- If `evaluation.required` is `True`:
  - Look up `FieldProvenance` for the field via `context[PROVENANCE_KEY]`
  - If no evaluation stamp exists: apply `evaluation.on_unevaluated` severity
  - If evaluation stamp exists but `evaluation_score < evaluation.threshold`:
    apply `evaluation.on_below_threshold` severity
  - If `evaluation.policy == "human_required"` and evaluator does not match a
    human identifier pattern: apply `evaluation.on_unevaluated` severity
  - If `evaluation.evaluator` is specified and does not match `evaluated_by`:
    apply `evaluation.on_unevaluated` severity

**Acceptance Criteria:**
- [ ] When `FieldSpec.evaluation` is `None`, behavior is identical to current
- [ ] BLOCKING severity from evaluation check sets `passed=False`
- [ ] WARNING severity from evaluation check adds to warnings list
- [ ] ADVISORY severity from evaluation check is logged only
- [ ] `FieldValidationResult` message indicates which step failed (presence,
  schema, or evaluation)

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py`

---

### REQ-13-008: FieldValidationResult Evaluation Fields

**Priority:** P2
**Description:** Extend `FieldValidationResult` in `contracts/propagation/validator.py`
with optional fields to report evaluation check outcomes.

**New fields:**
- `evaluation_checked: bool = False` -- whether evaluation check was performed
- `evaluation_passed: Optional[bool] = None` -- whether evaluation passed
- `evaluation_score: Optional[float] = None` -- score found (if any)
- `evaluation_message: str = ""` -- detail about evaluation outcome

**Acceptance Criteria:**
- [ ] Default values maintain backward compatibility
- [ ] `to_gate_result()` includes evaluation evidence when `evaluation_checked` is `True`
- [ ] Fields are populated by the extended `_validate_field()` from REQ-13-007

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py`

---

### REQ-13-009: OTel Emission for Evaluation Results

**Priority:** P1
**Description:** Add an `emit_evaluation_result()` function in
`contracts/propagation/otel.py` that emits a span event for evaluation outcomes.

**Event name:** `context.evaluation.result`

**Attributes:**
- `context.field`: field path that was evaluated
- `context.evaluator`: evaluator identifier
- `context.evaluation_score`: numeric score
- `context.evaluation_passed`: boolean
- `context.evaluation_policy`: policy applied
- `context.evaluation_threshold`: threshold used
- `context.phase`: phase where evaluation occurred

**Acceptance Criteria:**
- [ ] Follows `_HAS_OTEL` guard + `_add_span_event()` pattern from existing code
- [ ] Logs at INFO on pass, WARNING on fail (matching existing severity logging pattern)
- [ ] Attributes use `context.` prefix consistent with existing propagation events
- [ ] Importable from `contextcore.contracts.propagation.otel`

**Affected files:**
- `src/contextcore/contracts/propagation/otel.py`

---

### REQ-13-010: Integration with Layer 4 RuntimeBoundaryGuard

**Priority:** P1
**Description:** The `RuntimeBoundaryGuard` in `contracts/runtime/guard.py` must
apply enforcement modes (strict/permissive/audit) to evaluation check failures,
identical to how it handles field presence failures.

**Behavior by mode:**
- `strict`: BLOCKING evaluation failure raises `BoundaryViolationError`
- `permissive`: BLOCKING evaluation failure is logged but execution continues
- `audit`: all evaluation results are logged/emitted, nothing blocks

**Acceptance Criteria:**
- [ ] No changes needed to `RuntimeBoundaryGuard` code if `BoundaryValidator`
  correctly maps evaluation failures to `BLOCKING`/`WARNING`/`ADVISORY` severity
  (the guard already delegates to the validator)
- [ ] Verify via tests that strict mode raises on unevaluated BLOCKING fields
- [ ] Verify via tests that audit mode allows unevaluated BLOCKING fields
- [ ] `WorkflowRunSummary` counts evaluation failures in `total_blocking_failures`

**Affected files:**
- `src/contextcore/contracts/runtime/guard.py` (test-only; no code changes expected)
- `tests/` (integration tests)

---

### REQ-13-011: Integration with Layer 5 Post-Execution Validation

**Priority:** P2
**Description:** Post-execution chain integrity checks must verify that all
fields with `evaluation.required = True` in the contract were actually evaluated
before the workflow completed.

**Check:** "Evaluation chain completeness" -- for every field in every phase
with an evaluation spec where `required=True`, verify that a corresponding
evaluation stamp exists in the context provenance.

**Acceptance Criteria:**
- [ ] `PropagationTracker.validate_all_chains()` or a new
  `validate_evaluation_completeness()` method checks evaluation stamps
- [ ] Returns a list of fields that required evaluation but were not evaluated
- [ ] Result is emittable via OTel (span event: `context.evaluation.completeness`)
- [ ] Missing evaluations are reported with severity from `on_unevaluated`

**Affected files:**
- `src/contextcore/contracts/propagation/tracker.py`
- `src/contextcore/contracts/propagation/otel.py`

---

### REQ-13-012: Integration with Layer 7 Regression Gate

**Priority:** P2
**Description:** The regression gate must verify that the evaluation pass rate
does not decrease between workflow runs. If run N had 95% evaluation pass rate,
run N+1 must not drop below 95% (within a configurable tolerance).

**Acceptance Criteria:**
- [ ] Evaluation pass rate is computed as: (fields with passing evaluation) /
  (fields with evaluation required) per workflow run
- [ ] Regression gate can compare current run's evaluation pass rate against a
  baseline stored from previous runs
- [ ] Configurable tolerance (e.g., 5% drop is acceptable)
- [ ] Regression failure respects the contract's severity model
  (BLOCKING/WARNING/ADVISORY)

**Affected files:**
- Regression gate module (to be determined; may be in `contracts/runtime/` or
  a new `contracts/regression/` module)

---

### REQ-13-013: Contract YAML Schema for Evaluation

**Priority:** P1
**Description:** The evaluation block must be parseable from YAML contract files
following the existing `ContextContract` parsing pipeline via
`contracts/propagation/loader.py`.

**Acceptance Criteria:**
- [ ] The following YAML parses successfully into `ContextContract`:

```yaml
schema_version: "0.1.0"
pipeline_id: "evaluation-gated-pipeline"
phases:
  generate:
    exit:
      required:
        - name: generated_code
          severity: blocking
          evaluation:
            required: true
            policy: "score_threshold"
            threshold: 0.8
            evaluator: "code_review_agent"
            on_unevaluated: blocking
            on_below_threshold: warning
        - name: generated_documentation
          severity: warning
          evaluation:
            required: true
            policy: "human_or_model"
            threshold: 0.7
            on_unevaluated: warning
            on_below_threshold: advisory
  review:
    entry:
      required:
        - name: generated_code
          severity: blocking
          evaluation:
            required: true
            policy: "score_threshold"
            threshold: 0.8
            on_unevaluated: blocking
```

- [ ] Unknown keys inside `evaluation` block are rejected (`extra="forbid"`)
- [ ] Invalid `policy` values are rejected by Pydantic validation
- [ ] Invalid `threshold` values (< 0.0 or > 1.0) are rejected

**Affected files:**
- `src/contextcore/contracts/propagation/schema.py`
- `src/contextcore/contracts/propagation/loader.py`

---

### REQ-13-014: Backward Compatibility

**Priority:** P1
**Description:** All changes must be backward compatible with existing contracts
that do not use the `evaluation` block.

**Acceptance Criteria:**
- [ ] Contracts without `evaluation` fields parse and validate identically to
  current behavior
- [ ] `FieldSpec` with `evaluation: None` (the default) produces the same
  `FieldValidationResult` as today
- [ ] No existing test requires modification (all new behavior is additive)
- [ ] `FieldProvenance` without evaluation stamps serializes identically to today
- [ ] `PropagationTracker.stamp()` signature is unchanged

**Affected files:**
- All modified files (verified via existing test suite)

---

### REQ-13-015: Graceful Degradation without OTel

**Priority:** P2
**Description:** All evaluation-related code must work correctly when
OpenTelemetry is not installed, following the existing `_HAS_OTEL` guard pattern.

**Acceptance Criteria:**
- [ ] `emit_evaluation_result()` is a no-op when `_HAS_OTEL` is `False`
- [ ] Evaluation validation (`_validate_field()` step 3) works without OTel
- [ ] `stamp_evaluation()` works without OTel
- [ ] No `ImportError` when `opentelemetry` package is absent

**Affected files:**
- `src/contextcore/contracts/propagation/otel.py`
- `src/contextcore/contracts/propagation/validator.py`
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-13-016: Evaluation Policy Enforcement Logic

**Priority:** P1
**Description:** The evaluation check in `_validate_field()` must enforce the
declared `EvaluationPolicy` correctly.

**Policy enforcement rules:**
| Policy | Pass condition |
|--------|---------------|
| `score_threshold` | `evaluation_score >= threshold` |
| `human_or_model` | evaluation stamp exists AND `evaluation_score >= threshold` |
| `human_required` | evaluation stamp exists AND `evaluator` is a human identifier AND `evaluation_score >= threshold` |
| `any_evaluator` | evaluation stamp exists (score not checked) |

**Human identifier pattern:** An evaluator is considered human if it does not
match the pattern `*_agent`, `*_model`, `*_bot`, or starts with `ai:`, `model:`,
`agent:`. This pattern should be extractable to a configurable predicate.

**Acceptance Criteria:**
- [ ] Each policy produces the correct pass/fail for valid and invalid evaluation stamps
- [ ] `human_required` policy correctly rejects model-based evaluators
- [ ] `any_evaluator` policy passes regardless of score
- [ ] `score_threshold` policy uses `>=` comparison (not `>`)
- [ ] Human identifier detection is implemented as a standalone function that can be
  overridden or configured

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py`

---

### REQ-13-017: Evaluator Matching

**Priority:** P2
**Description:** When `EvaluationSpec.evaluator` specifies an expected evaluator,
the evaluation check must verify that the actual evaluator matches.

**Acceptance Criteria:**
- [ ] If `EvaluationSpec.evaluator` is `None`, any evaluator is accepted
- [ ] If `EvaluationSpec.evaluator` is set, `FieldProvenance.evaluated_by` must
  match exactly
- [ ] Mismatch applies `on_unevaluated` severity (treated as if not evaluated
  by the right entity)
- [ ] Evaluator mismatch message includes both expected and actual evaluator

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py`

---

### REQ-13-018: ContractValidationResult Evaluation Summary

**Priority:** P3
**Description:** `ContractValidationResult` should include aggregate evaluation
statistics for observability.

**New fields:**
- `evaluations_required: int = 0` -- count of fields with evaluation required
- `evaluations_passed: int = 0` -- count of fields where evaluation passed
- `evaluations_missing: int = 0` -- count of fields missing evaluation

**Acceptance Criteria:**
- [ ] Fields default to 0 (backward compatible)
- [ ] `to_gate_result()` includes evaluation summary in evidence when
  `evaluations_required > 0`
- [ ] Summary is populated by `_validate_fields()` aggregation loop

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py`

---

## Contract Schema

The evaluation block extends `FieldSpec` in the existing context contract YAML
format:

```yaml
# Full contract example with evaluation-gated fields
schema_version: "0.1.0"
pipeline_id: "code-generation-pipeline"
description: "Pipeline with evaluation gates on generated outputs"

phases:
  generate:
    description: "Generate code and documentation from specifications"
    exit:
      required:
        - name: generated_code
          type: str
          severity: blocking
          description: "Generated source code"
          evaluation:
            required: true
            policy: "score_threshold"
            threshold: 0.8
            evaluator: "code_review_agent"
            on_unevaluated: blocking
            on_below_threshold: warning
            description: "Code must be reviewed before downstream use"

        - name: generated_documentation
          type: str
          severity: warning
          description: "Generated documentation"
          evaluation:
            required: true
            policy: "human_or_model"
            threshold: 0.7
            on_unevaluated: warning
            on_below_threshold: advisory
            description: "Documentation should be reviewed"

        - name: test_coverage_report
          type: dict
          severity: advisory
          description: "Test coverage metrics"
          # No evaluation block -- propagates without evaluation gate

  review:
    description: "Review phase consumes evaluated outputs"
    entry:
      required:
        - name: generated_code
          severity: blocking
          evaluation:
            required: true
            policy: "score_threshold"
            threshold: 0.8
            on_unevaluated: blocking

  deploy:
    description: "Deployment requires human-evaluated code"
    entry:
      required:
        - name: generated_code
          severity: blocking
          evaluation:
            required: true
            policy: "human_required"
            threshold: 0.9
            on_unevaluated: blocking
            on_below_threshold: blocking
            description: "Deployment requires human sign-off with high confidence"

propagation_chains:
  - chain_id: "code_to_deploy"
    source:
      phase: generate
      field: generated_code
    destination:
      phase: deploy
      field: generated_code
    severity: blocking
```

---

## Integration Points

### Relationship to Existing Layers 1-7

Evaluation-Gated Propagation does NOT add a new layer. It adds a new
**contract type** (`EvaluationSpec`) that the existing layers validate:

```
Layer 7: Regression Prevention
  +-- Gate: evaluation pass rate must not decrease (REQ-13-012)

Layer 6: Observability & Alerting
  +-- Alert: evaluation failures emitted via OTel (REQ-13-009)

Layer 5: Post-Execution Validation
  +-- Check: evaluation chain completeness (REQ-13-011)

Layer 4: Runtime Boundary Checks
  +-- Validates: evaluation stamps present, score >= threshold (REQ-13-010)
  +-- Enforcement modes apply to evaluation failures identically

Layer 3: Pre-Flight Verification
  +-- Checks: evaluation specs are consistent (evaluator exists, thresholds valid)

Layer 2: Static Analysis
  +-- Analyzes: evaluation dependency graph (which fields require which evaluators)

Layer 1: Context Contracts (Declarations)
  +-- Declares: EvaluationSpec on FieldSpec (REQ-13-002, REQ-13-003, REQ-13-013)
```

### Integration with Concern 9 (Quality Propagation)

Evaluation and quality are complementary:
- **Quality Propagation** checks that a computed metric meets a threshold (automated)
- **Evaluation-Gated Propagation** checks that a judgment has been rendered (may involve humans)

A field can have both `quality` and `evaluation` blocks. The validation
sequence becomes:
1. Field exists
2. Schema valid
3. Quality metric above threshold (Concern 9)
4. Evaluation stamp present and passed (Concern 13)

### Integration with Existing Code

| Component | Current | Change |
|-----------|---------|--------|
| `FieldSpec` | `name, type, severity, default, description, source_phase, constraints` | Add `evaluation: Optional[EvaluationSpec]` |
| `FieldProvenance` | `origin_phase, set_at, value_hash` | Add `evaluated_by, evaluation_score, evaluation_timestamp` |
| `_validate_field()` | Checks presence + default | Add step 3: evaluation check |
| `PropagationTracker` | `stamp()`, `get_provenance()`, `check_chain()` | Add `stamp_evaluation()` |
| `otel.py` | `emit_boundary_result()`, `emit_chain_result()` | Add `emit_evaluation_result()` |
| `types.py` | Existing enums | Add `EvaluationPolicy` enum |
| `RuntimeBoundaryGuard` | Delegates to `BoundaryValidator` | No code changes (enforcement modes apply automatically) |

---

## Test Requirements

### Unit Tests (~25 tests)

**EvaluationSpec model tests:**
- [ ] Valid spec with all fields parses correctly
- [ ] Valid spec with defaults (minimal fields) parses correctly
- [ ] Invalid threshold (> 1.0 or < 0.0) raises `ValidationError`
- [ ] Invalid policy value raises `ValidationError`
- [ ] Unknown keys rejected (`extra="forbid"`)

**FieldSpec extension tests:**
- [ ] FieldSpec without evaluation parses as before
- [ ] FieldSpec with evaluation block parses correctly
- [ ] Round-trip: parse from dict, serialize to dict, parse again

**EvaluationResult tests:**
- [ ] Construction with all fields
- [ ] `to_dict()` produces expected structure

**FieldProvenance extension tests:**
- [ ] Existing provenance without evaluation fields serializes as before
- [ ] Provenance with evaluation fields includes them in `to_dict()`
- [ ] Provenance with `None` evaluation fields omits them from `to_dict()`

**PropagationTracker.stamp_evaluation() tests:**
- [ ] Stamps evaluation on existing provenance record
- [ ] Creates minimal provenance when none exists (with warning)
- [ ] Returns correct `EvaluationResult`

### Validation Tests (~20 tests)

**_validate_field() with evaluation:**
- [ ] Field present, no evaluation spec: passes (existing behavior)
- [ ] Field present, evaluation required, no stamp: applies `on_unevaluated` severity
- [ ] Field present, evaluation required, stamp exists, score above threshold: passes
- [ ] Field present, evaluation required, stamp exists, score below threshold: applies `on_below_threshold`
- [ ] Field absent, evaluation required: presence check fails first (evaluation not reached)

**Policy enforcement tests:**
- [ ] `score_threshold`: passes at threshold, fails below
- [ ] `human_or_model`: passes with human or model evaluator
- [ ] `human_required`: passes with human, fails with model evaluator
- [ ] `any_evaluator`: passes with any stamp regardless of score
- [ ] Evaluator mismatch when `EvaluationSpec.evaluator` is specified

**Severity mapping tests:**
- [ ] BLOCKING `on_unevaluated` sets `passed=False`
- [ ] WARNING `on_unevaluated` adds to warnings, `passed=True`
- [ ] ADVISORY `on_unevaluated` is logged only, `passed=True`
- [ ] BLOCKING `on_below_threshold` sets `passed=False`
- [ ] WARNING `on_below_threshold` adds to warnings

### Integration Tests (~10 tests)

**RuntimeBoundaryGuard integration:**
- [ ] Strict mode raises on unevaluated BLOCKING field
- [ ] Permissive mode logs but continues on unevaluated BLOCKING field
- [ ] Audit mode allows all evaluation failures

**End-to-end contract parsing:**
- [ ] Full YAML contract with evaluation blocks parses and validates correctly
- [ ] Workflow with proper evaluation stamps passes all boundaries
- [ ] Workflow with missing evaluation stamps fails at expected boundary

**OTel emission tests:**
- [ ] `emit_evaluation_result()` adds span event with correct attributes
- [ ] `emit_evaluation_result()` is no-op without OTel installed

**Backward compatibility:**
- [ ] Existing test suite passes without modification
- [ ] Contract without evaluation blocks behaves identically

---

## Non-Requirements

The following are explicitly out of scope for Concern 13:

1. **Evaluation orchestration.** This concern declares that evaluation must
   happen and checks whether it happened. It does NOT orchestrate the evaluation
   itself (invoking models, scheduling humans, routing to review queues). That
   is the runtime's responsibility.

2. **Evaluation content storage.** The evaluation stamp records *who* evaluated,
   *when*, and *what score* they gave. It does NOT store the evaluation
   rationale, comments, or detailed feedback. Those belong in the evaluation
   system, not the propagation contract.

3. **Multi-evaluator consensus.** This concern supports a single evaluation
   stamp per field. If multiple evaluators must agree, that is modeled as
   multiple fields with separate evaluation specs, or handled by the evaluation
   orchestration layer before stamping.

4. **Evaluation UI/UX.** No dashboard, CLI command, or user interface for
   performing evaluations is in scope. This concern provides the contract
   schema and validation logic only.

5. **Real-time evaluation streaming.** Evaluation is a discrete event, not a
   continuous stream. The stamp captures a point-in-time judgment.

6. **Evaluation caching or memoization.** Whether a previous evaluation can be
   reused for a new run is a runtime concern, not a contract concern.

7. **Quality Propagation (Concern 9).** Quality checks are a separate concern
   with a separate spec (`QualityPropagationSpec`). Evaluation gates complement
   quality checks but do not replace them.
