# Requirements: Concern 9 -- Intermediate Quality Propagation

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (high value, low complexity)
**Companion doc:** [Context Correctness Extensions](../CONTEXT_CORRECTNESS_EXTENSIONS.md) -- Concern 9
**Parent doc:** [Context Correctness by Construction](../CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)
**Estimated implementation:** ~100 lines + tests

---

## Problem Statement

Context Propagation (Concern 1, Layer 1) checks that a field *exists* at each
phase boundary. Schema Evolution (Concern 2, Layer 2) checks that a field has
the *right structure*. Neither checks that a field's *value is good enough*.

A retrieval phase returns low-confidence results. The field exists (passes
propagation check). The structure is valid (passes schema check). But the
quality is poor, and the downstream generation phase produces subtly worse
output because it was given low-quality input.

This is the most literal instantiation of the design document's core problem
statement: **"no errors, reduced quality."**

**Why current defenses miss it:** `BoundaryValidator._validate_field()` in
`contracts/propagation/validator.py` checks presence and severity. It calls
`_resolve_field()` for dot-path traversal and returns `PROPAGATED` when the
field exists. It never inspects the field's *quality*. A retrieval confidence
of 0.1 is treated identically to a confidence of 0.99.

**The CS parallel:** This is **refinement types** from programming language
theory (Freeman & Pfenning, 1991). A plain type says "value exists and has
the right shape." A refinement type says "value exists, has the right shape,
AND satisfies a predicate." Quality propagation adds refinement predicates to
context fields: `{x: retrieved_context | retrieval_confidence >= 0.7}`.

**Framework evidence:**
- **LlamaIndex** computes retrieval confidence scores -- but they are local
  to the retrieval step, not propagated as contracts to generation.
- **Haystack** components have quality thresholds -- but thresholds are
  per-component configuration, not pipeline-wide contracts.
- **DSPy** optimizes for metrics (accuracy, coherence, cost) -- but metrics
  are evaluation-time constructs, not boundary-time contracts.

All three frameworks *have* quality signals. None of them *propagate* quality
as a contract.

---

## Requirements

### REQ-9-001: QualitySpec Pydantic model

**Priority:** P1
**Description:** Define a `QualitySpec` Pydantic v2 model that declares a
quality assertion for a context field. The model specifies which metric to
check, the minimum acceptable threshold, the severity when the threshold is
not met, and a human-readable description.

**Acceptance criteria:**
- `QualitySpec` is a `BaseModel` with `ConfigDict(extra="forbid")`.
- Fields: `metric` (str, required, min_length=1), `threshold` (float,
  required), `on_below` (ConstraintSeverity, required), `description`
  (Optional[str]).
- `threshold` must accept any float value (quality metrics may use different
  scales -- 0.0-1.0 for confidence, 0-100 for percentages, etc.).
- Model validates successfully with `model_validate()` from YAML-loaded dicts.
- Model rejects unknown keys via `extra="forbid"`.

**Affected files:**
- `src/contextcore/contracts/propagation/schema.py` (new class)

---

### REQ-9-002: Extend FieldSpec with optional quality block

**Priority:** P1
**Description:** Add an optional `quality` field of type `QualitySpec` to the
existing `FieldSpec` model. When present, quality validation is performed in
addition to presence validation. When absent, behavior is unchanged (backward
compatible).

**Acceptance criteria:**
- `FieldSpec.quality` is `Optional[QualitySpec]`, defaulting to `None`.
- Existing contracts without `quality` blocks parse identically to before.
- Contracts with `quality` blocks parse and validate correctly.
- `FieldSpec` remains `extra="forbid"` (no unrelated keys allowed).
- Round-trip: `FieldSpec.model_validate(spec.model_dump())` is identity.

**Affected files:**
- `src/contextcore/contracts/propagation/schema.py` (modify `FieldSpec`)

---

### REQ-9-003: Quality metric resolution from context dict

**Priority:** P1
**Description:** Quality metrics are resolved from the context dict using the
same dot-path traversal as field values. The metric name in `QualitySpec` is
treated as a dot-path key into the context dict (e.g.,
`retrieval_confidence` resolves `context["retrieval_confidence"]`;
`rag.retrieval_confidence` resolves `context["rag"]["retrieval_confidence"]`).

**Acceptance criteria:**
- Quality metric resolution reuses `_resolve_field()` from
  `contracts/propagation/validator.py`.
- Nested dot-paths work (e.g., `rag.confidence.score`).
- Resolution returns `(present: bool, value: Any)` tuple.
- Non-numeric resolved values are treated as "metric not available" (same as
  missing), not as validation errors.

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py` (reuse existing function)

---

### REQ-9-004: QualityViolation result type

**Priority:** P1
**Description:** Define a `QualityViolation` data structure to represent a
quality threshold violation. This is returned alongside field validation
results when a quality check fails.

**Acceptance criteria:**
- `QualityViolation` is a Pydantic `BaseModel` with `ConfigDict(extra="forbid")`.
- Fields: `field` (str -- the field whose quality was checked), `metric`
  (str -- the quality metric name), `threshold` (float -- the declared
  minimum), `actual_value` (float -- the observed value), `severity`
  (ConstraintSeverity -- the `on_below` severity from `QualitySpec`),
  `message` (str -- human-readable description).
- Can be serialized to dict for OTel span event attributes.

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py` (new class)

---

### REQ-9-005: Extend FieldValidationResult with quality violation

**Priority:** P1
**Description:** Add an optional `quality_violation` field to the existing
`FieldValidationResult` model. When a quality check fails, this field
contains the `QualityViolation` details. When quality passes or no quality
spec is declared, this field is `None`.

**Acceptance criteria:**
- `FieldValidationResult.quality_violation` is `Optional[QualityViolation]`,
  defaulting to `None`.
- Existing code that reads `FieldValidationResult` is unaffected (new field
  is optional).
- When `quality_violation` is present, `FieldValidationResult.status`
  reflects the quality severity (see REQ-9-006).

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py` (modify
  `FieldValidationResult`)

---

### REQ-9-006: BoundaryValidator quality threshold checking

**Priority:** P1
**Description:** Extend `_validate_field()` in `BoundaryValidator` to check
quality thresholds after confirming field presence. Quality checking occurs
only when `FieldSpec.quality` is not `None` AND the field itself is present.
The check resolves the quality metric from the context dict and compares it
against the threshold.

**Acceptance criteria:**
- If the field is absent, quality is NOT checked (presence failure takes
  precedence).
- If the field is present and `quality` is `None`, behavior is identical to
  the current implementation.
- If the field is present and `quality` is set:
  - Resolve `quality.metric` from context via `_resolve_field()`.
  - If metric is missing or non-numeric: skip quality check (see REQ-9-011).
  - If metric value >= threshold: quality passes, no violation.
  - If metric value < threshold: create `QualityViolation` and apply
    severity per `quality.on_below`:
    - `BLOCKING`: set `FieldValidationResult.status` to `FAILED`.
    - `WARNING`: set status to `DEFAULTED`, append to warnings.
    - `ADVISORY`: set status to `PARTIAL`, log only.
- Quality validation must NOT mutate the context dict.

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py` (modify
  `_validate_field()`)

---

### REQ-9-007: ContractValidationResult quality aggregation

**Priority:** P2
**Description:** Extend `ContractValidationResult` to aggregate quality
violations alongside field presence violations. The result must expose how
many quality violations occurred and at what severity.

**Acceptance criteria:**
- `ContractValidationResult` gains a `quality_violations` field:
  `list[QualityViolation]`, default empty.
- `_validate_fields()` in `BoundaryValidator` populates
  `quality_violations` from individual `FieldValidationResult` instances.
- BLOCKING quality violations contribute to `blocking_failures`.
- WARNING quality violations contribute to `warnings`.
- `to_gate_result()` includes quality violation evidence in the output dict.

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py` (modify
  `ContractValidationResult`, `_validate_fields()`)

---

### REQ-9-008: OTel span event emission for quality violations

**Priority:** P2
**Description:** Emit an OTel span event named `context.quality.violation`
when a quality threshold is breached. Follow the existing `_HAS_OTEL` guard
and `_add_span_event()` pattern from `contracts/postexec/otel.py`.

**Acceptance criteria:**
- Event name: `context.quality.violation`.
- Event attributes:
  - `quality.field` (str): the field name.
  - `quality.metric` (str): the metric name.
  - `quality.threshold` (float): the declared threshold.
  - `quality.actual_value` (float): the observed value.
  - `quality.severity` (str): the `on_below` severity value.
  - `quality.phase` (str): the phase where the violation occurred.
  - `quality.direction` (str): entry or exit.
- Guarded by `_HAS_OTEL` -- degrades gracefully when OTel is not installed.
- A corresponding `emit_quality_summary()` function emits a summary event
  (`context.quality.summary`) with total violation counts per severity.

**Affected files:**
- `src/contextcore/contracts/propagation/otel.py` (new functions, or new
  file `src/contextcore/contracts/quality/otel.py`)

---

### REQ-9-009: Integration with Layer 4 RuntimeBoundaryGuard

**Priority:** P2
**Description:** The `RuntimeBoundaryGuard` (Layer 4) must respect quality
violations according to its enforcement mode. Quality violations with
BLOCKING severity must be handled identically to field-presence BLOCKING
failures.

**Acceptance criteria:**
- In `strict` mode: a BLOCKING quality violation raises
  `BoundaryViolationError`.
- In `permissive` mode: a BLOCKING quality violation is logged but execution
  continues.
- In `audit` mode: quality violations are logged and emitted via OTel only.
- `PhaseExecutionRecord` and `WorkflowRunSummary` include quality violation
  counts in their aggregation.
- No changes to `RuntimeBoundaryGuard` API are required -- it delegates to
  `BoundaryValidator`, which already returns `ContractValidationResult`.
  Quality violations flow through the existing result propagation path.

**Affected files:**
- `src/contextcore/contracts/runtime/guard.py` (potentially extend
  `WorkflowRunSummary` with `total_quality_violations` counter)

---

### REQ-9-010: Integration with Layer 6 AlertEvaluator

**Priority:** P2
**Description:** The `AlertEvaluator` (Layer 6) must support quality-based
alert rules. Quality violation counts should be extractable as metrics from
the Layer 4 `WorkflowRunSummary` and evaluated against alert thresholds.

**Acceptance criteria:**
- `AlertEvaluator._extract_metrics()` extracts `quality_violations` and
  `quality_violations_blocking` from `WorkflowRunSummary` when available.
- Default alert rules include a quality-specific rule:
  - `rule_id`: `"quality.violations_blocking"`
  - `metric`: `"quality_violations_blocking"`
  - `operator`: `"gt"`
  - `threshold`: `0.0`
  - `severity`: `BLOCKING`
- Custom alert rules can target specific quality metrics by name (e.g.,
  `metric: "quality.retrieval_confidence.violations"`).

**Affected files:**
- `src/contextcore/contracts/observability/alerts.py` (extend
  `_extract_metrics()`, add default rules)

---

### REQ-9-011: Graceful degradation when quality metric is missing

**Priority:** P1
**Description:** When a quality metric cannot be resolved from the context
dict (missing key, non-numeric value, or `None`), the quality check must be
skipped rather than failing. This ensures that quality assertions do not
break pipelines that legitimately omit quality metadata.

**Acceptance criteria:**
- Missing metric: quality check is skipped, field validation result reflects
  only presence status.
- `None` metric value: treated as missing, quality check is skipped.
- Non-numeric metric value (str, list, dict): treated as missing, quality
  check is skipped.
- A debug-level log message is emitted when a quality check is skipped due
  to missing metric: `"Quality metric '%s' not found for field '%s', skipping quality check"`.
- An OTel span event `context.quality.skipped` is emitted with the field
  name and metric name.

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py` (within the quality
  check logic in `_validate_field()`)

---

### REQ-9-012: Integration with Layer 7 RegressionGate

**Priority:** P2
**Description:** The `RegressionGate` (Layer 7) must include a quality
regression check. If quality violations increase between baseline and current
runs, the gate should fail.

**Acceptance criteria:**
- `RegressionGate.check()` accepts optional `baseline_summary` and
  `current_summary` (`WorkflowRunSummary`) parameters.
- When both are provided, a `"quality_regression"` gate check compares
  `total_quality_violations` between baseline and current.
- The check fails if current quality violations exceed baseline by more
  than `max_quality_violation_increase` (configurable threshold, default 0).
- A separate `"quality_score_regression"` check can compare aggregate
  quality scores if quality summary data is available.

**Affected files:**
- `src/contextcore/contracts/regression/gate.py` (extend `check()` method
  and `DEFAULT_THRESHOLDS`)

---

### REQ-9-013: Pre-flight validation of quality metric producibility

**Priority:** P2
**Description:** The pre-flight checker (Layer 3) should validate that every
quality metric referenced in a contract is producible -- i.e., some upstream
phase declares it as an exit field or as a known context key. This catches
contract errors at design time, not at runtime.

**Acceptance criteria:**
- For each `FieldSpec` with a non-null `quality` block, the pre-flight
  checker verifies that `quality.metric` appears as either:
  - An exit field of the current or an upstream phase, OR
  - An entry field of the current phase (stamped by a prior phase).
- If the metric is not producible, a WARNING-level pre-flight violation is
  emitted (not BLOCKING, because the metric may be stamped dynamically).
- Violation message includes the field name, metric name, and the phase
  where the quality assertion is declared.

**Affected files:**
- `src/contextcore/contracts/preflight/checker.py` (extend pre-flight
  checks)

---

### REQ-9-014: Quality block in contract YAML schema

**Priority:** P1
**Description:** The context contract YAML schema must accept the `quality`
block within `FieldSpec` entries. The schema must be documented with
examples.

**Acceptance criteria:**
- The following YAML parses successfully into a `ContextContract`:
  ```yaml
  schema_version: "0.2.0"
  pipeline_id: "rag-pipeline"
  phases:
    retrieve:
      exit:
        required:
          - name: retrieved_context
            severity: blocking
            quality:
              metric: retrieval_confidence
              threshold: 0.7
              on_below: warning
              description: "Retrieval confidence below 0.7 degrades generation"
          - name: coverage_score
            severity: blocking
            quality:
              metric: topic_coverage
              threshold: 0.8
              on_below: blocking
              description: "Topic coverage below 80% means generation will miss key topics"
    generate:
      entry:
        required:
          - name: retrieved_context
            severity: blocking
      exit:
        required:
          - name: generated_output
            severity: blocking
            quality:
              metric: coherence_score
              threshold: 0.85
              on_below: warning
  ```
- Fields without `quality` blocks continue to work unchanged.
- Invalid `quality` blocks (e.g., missing `metric`, wrong type for
  `threshold`) produce Pydantic validation errors at parse time.

**Affected files:**
- `src/contextcore/contracts/propagation/schema.py` (already covered by
  REQ-9-001 and REQ-9-002)

---

### REQ-9-015: Quality composability with propagation chains

**Priority:** P3
**Description:** Quality assertions should compose with propagation chains
(Layer 1 `PropagationChainSpec`). When a propagation chain declares a field
flowing from source to destination, quality assertions at the destination
should be checkable against quality metrics stamped at the source.

**Acceptance criteria:**
- Post-execution chain validation (Layer 5) can detect "quality degradation
  along chain" -- where the quality metric at the destination is lower than
  at the source.
- Chain status vocabulary is extended: a chain can be `INTACT` (field
  present, quality OK), `DEGRADED` (field present, quality below threshold),
  or `BROKEN` (field absent).
- Quality-aware chain status is reported in `PostExecutionReport`.

**Affected files:**
- `src/contextcore/contracts/postexec/validator.py` (extend chain
  evaluation)

---

### REQ-9-016: Logging and observability for quality checks

**Priority:** P2
**Description:** All quality check outcomes (pass, fail, skip) must be logged
at appropriate levels and included in structured logging output.

**Acceptance criteria:**
- Quality pass: `DEBUG` level -- `"Quality check passed: field='%s' metric='%s' value=%.3f >= threshold=%.3f"`.
- Quality fail (BLOCKING): `WARNING` level -- `"Quality check FAILED: field='%s' metric='%s' value=%.3f < threshold=%.3f (severity=blocking)"`.
- Quality fail (WARNING): `INFO` level -- with the quality metric, value,
  and threshold.
- Quality fail (ADVISORY): `DEBUG` level.
- Quality skip (missing metric): `DEBUG` level (see REQ-9-011).
- Log messages include phase name and direction (entry/exit) when available.

**Affected files:**
- `src/contextcore/contracts/propagation/validator.py` (within quality
  check logic)

---

### REQ-9-017: Quality metric stamping convention

**Priority:** P2
**Description:** Define a convention for how producing phases stamp quality
metrics into the context dict. Quality metrics should be co-located with the
fields they describe, using a consistent naming pattern.

**Acceptance criteria:**
- Recommended convention: quality metrics are stored at a path derived from
  the field name plus a suffix. For example, a field `retrieved_context`
  with quality metric `retrieval_confidence` stores the metric at
  `context["retrieval_confidence"]` (explicit, referenced by name in the
  contract).
- Alternative convention: quality metrics can be stored in a dedicated
  `_quality` namespace, e.g., `context["_quality"]["retrieved_context"]["retrieval_confidence"]`.
- The contract YAML `quality.metric` field is the dot-path to the metric in
  the context dict -- this is the authoritative location.
- Convention is documented in `docs/semantic-conventions.md` under a new
  "Quality Metrics" section.

**Affected files:**
- `docs/semantic-conventions.md` (documentation only)

---

### REQ-9-018: Backward compatibility guarantee

**Priority:** P1
**Description:** All changes for Concern 9 must be fully backward compatible.
Existing contracts without `quality` blocks must parse and validate
identically to the current behavior. No existing tests may break.

**Acceptance criteria:**
- All existing tests in `tests/` pass without modification.
- `FieldSpec` without `quality` is serialized/deserialized identically.
- `BoundaryValidator` returns identical results for contracts that do not
  use quality blocks.
- `ContractValidationResult.quality_violations` is an empty list for
  contracts without quality assertions.
- `RuntimeBoundaryGuard`, `AlertEvaluator`, and `RegressionGate` behavior
  is unchanged when no quality data is present.

**Affected files:**
- All files modified by REQ-9-001 through REQ-9-017

---

## Contract Schema

The quality block extends the existing `FieldSpec` within the context
propagation contract YAML format:

```yaml
# schema_version bumps to 0.2.0 to indicate quality extension
schema_version: "0.2.0"
pipeline_id: "rag-pipeline"
description: "RAG pipeline with quality-gated propagation"

phases:
  retrieve:
    description: "Retrieve relevant context from vector store"
    exit:
      required:
        - name: retrieved_context
          severity: blocking
          quality:
            metric: retrieval_confidence
            threshold: 0.7
            on_below: warning
            description: "Retrieval confidence below 0.7 degrades generation quality"

        - name: coverage_score
          severity: blocking
          quality:
            metric: topic_coverage
            threshold: 0.8
            on_below: blocking
            description: "Topic coverage below 80% means generation will miss key topics"

  generate:
    description: "Generate output from retrieved context"
    entry:
      required:
        - name: retrieved_context
          severity: blocking
          # No quality block here -- quality is checked at retrieve.exit.
          # Entry checks presence only; exit checks quality.
    exit:
      required:
        - name: generated_output
          severity: blocking
          quality:
            metric: coherence_score
            threshold: 0.85
            on_below: warning
            description: "Coherence score below 0.85 indicates generation quality issues"

  validate:
    description: "Validate generated output"
    entry:
      required:
        - name: generated_output
          severity: blocking
      enrichment:
        - name: coherence_score
          severity: advisory
          description: "Coherence score from generation phase for validation context"
    exit:
      required:
        - name: validation_result
          severity: blocking

propagation_chains:
  - chain_id: "retrieval_to_generation"
    source:
      phase: retrieve
      field: retrieved_context
    destination:
      phase: generate
      field: retrieved_context
    severity: blocking
```

### QualitySpec model (Pydantic v2)

```python
class QualitySpec(BaseModel):
    """Quality assertion for a context field value."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(
        ..., min_length=1,
        description="Dot-path to the quality metric in the context dict"
    )
    threshold: float = Field(
        ...,
        description="Minimum acceptable value for the quality metric"
    )
    on_below: ConstraintSeverity = Field(
        ...,
        description="Severity when metric is below threshold: blocking/warning/advisory"
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable explanation of why this threshold matters"
    )
```

---

## Integration Points

Quality Propagation composes with all seven existing layers without modifying
their interfaces. It adds a new *contract type* that the existing layers
validate.

### Layer 1: Context Contracts (Declarations)

Quality is declared in the same YAML contract as field presence. The
`quality` block is part of `FieldSpec`, so no new top-level contract type is
needed.

**Composition:** "Field exists AND is good enough."

### Layer 2: Static Analysis

The static analyzer can verify that quality metrics referenced in `quality`
blocks are declared as fields in the contract (either as exit fields of the
producing phase or as known context keys).

**Composition:** "Quality metric references are resolvable in the contract graph."

### Layer 3: Pre-Flight Verification

Pre-flight checks verify that quality metrics are producible by upstream
phases (REQ-9-013). This is a design-time check, not a runtime check.

**Composition:** "Quality assertions are satisfiable before execution begins."

### Layer 4: Runtime Boundary Checks

`RuntimeBoundaryGuard` enforces quality violations using the same enforcement
modes as presence violations (strict/permissive/audit). No API changes
required -- quality violations flow through the existing
`ContractValidationResult` (REQ-9-009).

**Composition:** "Quality checked at every boundary, enforcement mode applies."

### Layer 5: Post-Execution Validation

Post-execution chain validation can detect quality degradation along
propagation chains (REQ-9-015). A field that propagates but loses quality is
marked `DEGRADED`.

**Composition:** "End-to-end quality tracked alongside field presence."

### Layer 6: Observability and Alerting

`AlertEvaluator` supports quality-based alert rules (REQ-9-010). Quality
violation counts are extractable as metrics from `WorkflowRunSummary`.

**Composition:** "Alert when quality drops below threshold."

### Layer 7: Regression Prevention

`RegressionGate` prevents quality regressions in CI (REQ-9-012). Quality
violation counts must not increase between baseline and current runs.

**Composition:** "Quality must not decrease between releases."

---

## Test Requirements

### Unit Tests

| Test | Validates | Priority |
|------|-----------|----------|
| `test_quality_spec_valid` | QualitySpec parses valid YAML | P1 |
| `test_quality_spec_rejects_unknown_keys` | `extra="forbid"` enforcement | P1 |
| `test_quality_spec_requires_metric` | Missing `metric` raises ValidationError | P1 |
| `test_quality_spec_requires_threshold` | Missing `threshold` raises ValidationError | P1 |
| `test_quality_spec_requires_on_below` | Missing `on_below` raises ValidationError | P1 |
| `test_field_spec_with_quality` | FieldSpec accepts optional quality block | P1 |
| `test_field_spec_without_quality` | FieldSpec without quality is backward compatible | P1 |
| `test_validate_field_quality_passes` | Metric >= threshold returns PROPAGATED | P1 |
| `test_validate_field_quality_fails_blocking` | Metric < threshold with on_below=BLOCKING returns FAILED | P1 |
| `test_validate_field_quality_fails_warning` | Metric < threshold with on_below=WARNING returns DEFAULTED | P1 |
| `test_validate_field_quality_fails_advisory` | Metric < threshold with on_below=ADVISORY returns PARTIAL | P1 |
| `test_validate_field_quality_missing_metric` | Missing metric skips quality check | P1 |
| `test_validate_field_quality_non_numeric_metric` | Non-numeric metric skips quality check | P1 |
| `test_validate_field_quality_none_metric` | `None` metric value skips quality check | P1 |
| `test_validate_field_absent_skips_quality` | Absent field does not trigger quality check | P1 |
| `test_quality_violation_model` | QualityViolation serializes correctly | P1 |
| `test_contract_validation_result_quality_violations` | Quality violations aggregated in result | P2 |
| `test_boundary_validator_quality_blocking_fails_validation` | BLOCKING quality violation sets `passed=False` | P1 |
| `test_boundary_validator_quality_warning_passes_validation` | WARNING quality violation keeps `passed=True` | P1 |
| `test_full_contract_yaml_with_quality` | Complete contract YAML with quality blocks parses | P1 |
| `test_contract_yaml_without_quality_unchanged` | Contracts without quality are identical | P1 |

### Integration Tests

| Test | Validates | Priority |
|------|-----------|----------|
| `test_runtime_guard_strict_quality_blocking` | Strict mode raises BoundaryViolationError on BLOCKING quality violation | P2 |
| `test_runtime_guard_permissive_quality_blocking` | Permissive mode logs but continues on BLOCKING quality violation | P2 |
| `test_runtime_guard_audit_quality_blocking` | Audit mode emits OTel event only | P2 |
| `test_runtime_guard_summary_quality_counts` | WorkflowRunSummary includes quality violation counts | P2 |
| `test_alert_evaluator_quality_metric` | AlertEvaluator evaluates quality-specific alert rules | P2 |
| `test_regression_gate_quality_regression` | RegressionGate detects quality violation increase | P2 |
| `test_otel_quality_violation_event` | OTel span event emitted with correct attributes | P2 |
| `test_otel_quality_summary_event` | OTel summary event emitted with violation counts | P2 |
| `test_otel_degradation_without_otel` | Quality emission degrades gracefully without OTel | P2 |

### Property-Based Tests (optional, P3)

| Test | Validates |
|------|-----------|
| `test_quality_threshold_boundary` | Value exactly at threshold passes (>= not >) |
| `test_quality_negative_threshold` | Negative thresholds work (for metrics like error rate) |
| `test_quality_zero_threshold` | Zero threshold means any positive value passes |

---

## Non-Requirements

The following are explicitly out of scope for Concern 9:

1. **Quality computation.** This concern declares quality thresholds and
   validates them. It does NOT compute quality metrics. Computing retrieval
   confidence, coherence scores, or coverage metrics is the responsibility
   of the producing phase or an external evaluation step.

2. **Quality improvement.** When a quality threshold is breached, the system
   reports the violation. It does NOT automatically retry, re-retrieve, or
   re-generate to improve quality. Remediation is the pipeline
   orchestrator's responsibility.

3. **Multi-metric conjunctions.** A `FieldSpec` has at most one `quality`
   block with one metric and one threshold. Conjunctive assertions
   ("confidence >= 0.7 AND coverage >= 0.8") require two separate fields,
   each with their own quality block. A future extension could add
   `quality_rules: list[QualitySpec]` if needed.

4. **Quality metric history.** Quality violations are emitted as span events
   and logged. This concern does NOT maintain a time-series history of
   quality metric values for trend analysis. That is the observability
   backend's responsibility (Loki recording rules, Mimir metrics).

5. **Domain-specific quality semantics.** The quality system is
   domain-agnostic. It compares a numeric value against a numeric threshold.
   It does NOT understand what "retrieval confidence" means or whether 0.7
   is a good threshold for a particular use case. Threshold selection is the
   contract author's responsibility.

6. **Evaluation gating.** Quality propagation checks whether a quality
   *metric* meets a *threshold*. It does NOT check whether a *qualified
   evaluator* has confirmed the output. Evaluation gating is Concern 13
   (separate contract type).

7. **Graph topology awareness.** Quality checks operate at individual phase
   boundaries. They do NOT perform path-sensitive quality analysis across
   branching graph topologies. Graph topology correctness is Concern 12.

8. **Prompt/configuration quality.** This concern validates quality of
   *data* flowing through the pipeline. It does NOT validate quality of
   *prompts* or *configurations* that control pipeline behavior.
   Configuration evolution is Concern 11.
