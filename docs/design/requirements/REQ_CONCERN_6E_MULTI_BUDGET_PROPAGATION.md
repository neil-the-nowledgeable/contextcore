# REQ: Concern 6e -- Multi-Budget Propagation

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Companion Document:** [Context Correctness Extensions](../CONTEXT_CORRECTNESS_EXTENSIONS.md), Concern 6e
**Implementation Estimate:** ~200 lines + tests
**Priority Tier:** Tier 1 (High Value, Low Complexity)

---

## Problem Statement

The original SLO Budget Propagation (Concern 6 in the parent design document) addresses latency budgets only. Framework comparison against nine agent/LLM frameworks reveals three additional budget types that exhaust silently across pipeline phases:

1. **Retry budgets** (Guidance/Instructor): Validation retry loops consume time and tokens. A phase that burns 5 retries to produce a valid structured output starves downstream phases of their retry allocation. No pipeline-wide retry accounting exists.

2. **Token budgets** (All frameworks): Verbose intermediate responses consume context window capacity. A planning phase that generates 40,000 tokens of intermediate reasoning leaves only 60,000 tokens for implementation, design, and validation combined. No framework tracks cumulative token consumption against a pipeline-wide budget.

3. **Cost budgets** (DSPy): Optimization trials consume compute budget. Early-phase prompt optimization can exhaust the cost budget before later phases execute. The budget is per-run, not per-pipeline, so early phases starve later ones.

**Core pathology:** Each budget type follows the same pattern -- a finite resource is divided among pipeline phases, but no contract declares the allocation, no tracker stamps the remaining balance at boundaries, and no alert fires when a phase exceeds its allocation. The result is silent starvation: downstream phases receive less budget than expected and produce degraded output.

**Framework evidence:**
- Guidance/Instructor: Structured output validation retries are unbounded per-phase
- DSPy: Optimization trials consume compute budget without pipeline-wide accounting
- All frameworks: Token consumption at each phase reduces available context downstream

---

## Requirements

### Pydantic Models

#### REQ-6E-001: BudgetDefinition Model

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-001 |
| **Priority** | P1 |
| **Description** | Create a `BudgetDefinition` Pydantic model representing a single budget dimension. The model declares the budget identifier, total available amount, unit of measurement, per-phase allocations, and the enforcement action when a phase exceeds its allocation. |
| **Acceptance Criteria** | 1. Model uses `ConfigDict(extra="forbid")` consistent with all contract models. 2. Fields: `budget_id` (str, required, min_length=1), `total` (float, required, gt=0), `unit` (str, required -- e.g. "ms", "retries", "tokens", "usd"), `allocations` (dict[str, float], required -- maps phase name to allocation), `on_exceeded` (ConstraintSeverity, default WARNING). 3. Model validates successfully against the YAML schema example from the companion document. |
| **Affected Files** | `src/contextcore/contracts/propagation/schema.py` |

#### REQ-6E-002: BudgetPropagationSpec Model

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-002 |
| **Priority** | P1 |
| **Description** | Create a `BudgetPropagationSpec` Pydantic model that contains a list of `BudgetDefinition` instances. This is the top-level container for multi-dimensional budget declarations within a contract. |
| **Acceptance Criteria** | 1. Model uses `ConfigDict(extra="forbid")`. 2. Fields: `budgets` (list[BudgetDefinition], required, min_length=1). 3. Model parses the full multi-budget YAML example from the companion document (latency + retry + tokens + cost). |
| **Affected Files** | `src/contextcore/contracts/propagation/schema.py` |

#### REQ-6E-003: ContextContract Integration

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-003 |
| **Priority** | P1 |
| **Description** | Add an optional `budget_propagation` field of type `BudgetPropagationSpec` to the `ContextContract` root model. Contracts without budget declarations continue to work unchanged. |
| **Acceptance Criteria** | 1. `ContextContract` gains `budget_propagation: Optional[BudgetPropagationSpec] = None`. 2. Existing contracts without `budget_propagation` parse and validate without error. 3. Contracts with `budget_propagation` parse successfully. |
| **Affected Files** | `src/contextcore/contracts/propagation/schema.py` |

### Pre-flight Validation

#### REQ-6E-004: Allocation Sum Validation

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-004 |
| **Priority** | P1 |
| **Description** | At contract load time (or pre-flight), validate that per-phase allocations for each budget sum to less than or equal to the total budget. Allocations that exceed the total indicate a contract authoring error. |
| **Acceptance Criteria** | 1. For each `BudgetDefinition`, `sum(allocations.values()) <= total`. 2. Violation produces a preflight error with the budget_id, allocation sum, and total. 3. This check can run as a Pydantic `model_validator(mode="after")` on `BudgetDefinition` or as a method on `BudgetPropagationSpec`. |
| **Affected Files** | `src/contextcore/contracts/propagation/schema.py` |

#### REQ-6E-005: Phase Name Consistency Check

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-005 |
| **Priority** | P2 |
| **Description** | Pre-flight validation must warn when budget allocation phase names do not match the phases declared in the contract's `phases` dict. This catches typos and stale phase references. |
| **Acceptance Criteria** | 1. For each `BudgetDefinition`, every key in `allocations` should appear in `ContextContract.phases`. 2. Extra allocation phases (not in contract) produce a WARNING-level preflight finding. 3. Missing allocation phases (in contract but not in allocations) produce an ADVISORY-level finding (unbudgeted phase). |
| **Affected Files** | `src/contextcore/contracts/preflight/checker.py` |

### Budget Tracking

#### REQ-6E-006: BudgetTracker Class

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-006 |
| **Priority** | P1 |
| **Description** | Create a `BudgetTracker` class that maintains running budget state during pipeline execution. It stamps `remaining_budget_{budget_id}` into the context dict at each phase boundary and checks whether the phase consumed more than its allocation. |
| **Acceptance Criteria** | 1. `BudgetTracker.__init__` accepts a `BudgetPropagationSpec`. 2. `record_consumption(context, phase, budget_id, consumed)` stamps the remaining balance into the context under a `_cc_budgets` key (analogous to `_cc_propagation`). 3. Returns a `BudgetCheckResult` indicating whether the phase exceeded its allocation and whether the pipeline remaining balance is negative. 4. Consumption values must be non-negative (raises ValueError otherwise). |
| **Affected Files** | `src/contextcore/contracts/propagation/tracker.py` (or new file `src/contextcore/contracts/propagation/budget.py`) |

#### REQ-6E-007: BudgetCheckResult Model

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-007 |
| **Priority** | P1 |
| **Description** | Create a `BudgetCheckResult` dataclass or Pydantic model returned by `BudgetTracker.record_consumption()`. Captures the budget_id, phase, allocated amount, consumed amount, remaining pipeline budget, and status. |
| **Acceptance Criteria** | 1. Fields: `budget_id` (str), `phase` (str), `allocated` (float), `consumed` (float), `remaining` (float), `status` (ChainStatus -- INTACT if within allocation, DEGRADED if exceeded allocation but remaining >= 0, BROKEN if remaining < 0), `on_exceeded` (ConstraintSeverity). 2. `exceeded` property returns True when `consumed > allocated`. 3. `exhausted` property returns True when `remaining < 0`. |
| **Affected Files** | `src/contextcore/contracts/propagation/tracker.py` (or `src/contextcore/contracts/propagation/budget.py`) |

#### REQ-6E-008: Budget State Persistence in Context

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-008 |
| **Priority** | P1 |
| **Description** | Budget state must travel with the context dict through the pipeline. The `BudgetTracker` stores remaining balances under `context["_cc_budgets"][budget_id]` so that downstream phases can inspect upstream consumption without external state. |
| **Acceptance Criteria** | 1. After `record_consumption()`, `context["_cc_budgets"][budget_id]` contains at minimum: `remaining` (float), `last_phase` (str), `last_consumed` (float). 2. Multiple calls accumulate correctly: calling `record_consumption` for phase "seed" then "plan" yields the correct running total. 3. The `_cc_budgets` key is created lazily (only when budgets are tracked). |
| **Affected Files** | `src/contextcore/contracts/propagation/tracker.py` (or `src/contextcore/contracts/propagation/budget.py`) |

#### REQ-6E-009: Batch Consumption Recording

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-009 |
| **Priority** | P2 |
| **Description** | Provide a convenience method `record_phase_budgets(context, phase, consumptions)` that records consumption for multiple budget types in a single call. This is the expected calling pattern at phase boundaries. |
| **Acceptance Criteria** | 1. `consumptions` is `dict[str, float]` mapping budget_id to consumed amount. 2. Returns `list[BudgetCheckResult]` with one result per budget. 3. Budget IDs not in the spec are silently ignored (forward-compatible). 4. Budget IDs in the spec but not in consumptions are skipped (no zero recording). |
| **Affected Files** | `src/contextcore/contracts/propagation/tracker.py` (or `src/contextcore/contracts/propagation/budget.py`) |

### Layer 4 Integration (Runtime Boundary Guard)

#### REQ-6E-010: RuntimeBoundaryGuard Budget Checks

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-010 |
| **Priority** | P1 |
| **Description** | Extend `RuntimeBoundaryGuard.exit_phase()` to check budget consumption when a `BudgetPropagationSpec` is present in the contract and budget consumption data is available in the context. The guard reads `_cc_budgets` state and enforces the `on_exceeded` severity. |
| **Acceptance Criteria** | 1. When `contract.budget_propagation` is not None and `context["_cc_budgets"]` exists, the guard checks each budget at `exit_phase`. 2. BLOCKING budgets with negative remaining raise `BoundaryViolationError` in strict mode. 3. WARNING budgets that exceed allocation are logged and recorded but do not block. 4. ADVISORY budgets are logged only. 5. Budget check results are included in `PhaseExecutionRecord` (new optional field `budget_results`). |
| **Affected Files** | `src/contextcore/contracts/runtime/guard.py` |

#### REQ-6E-011: Budget-Aware WorkflowRunSummary

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-011 |
| **Priority** | P2 |
| **Description** | Extend `WorkflowRunSummary` to include aggregate budget metrics across all phases: total budgets tracked, budgets exceeded, budgets exhausted (remaining negative). |
| **Acceptance Criteria** | 1. New optional fields on `WorkflowRunSummary`: `budgets_tracked` (int, default 0), `budgets_exceeded` (int, default 0), `budgets_exhausted` (int, default 0). 2. `summarize()` populates these from `PhaseExecutionRecord.budget_results`. 3. Existing code that does not use budgets sees zero values (backward compatible). |
| **Affected Files** | `src/contextcore/contracts/runtime/guard.py` |

### Layer 5 Integration (Post-Execution Validation)

#### REQ-6E-012: Post-Execution Budget Accounting

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-012 |
| **Priority** | P2 |
| **Description** | Extend `PostExecutionValidator` to verify final budget state after all phases complete. Checks that no budget has a negative remaining balance and reports the utilization percentage for each budget. |
| **Acceptance Criteria** | 1. When `contract.budget_propagation` is present and `_cc_budgets` exists in the final context, the post-execution report includes budget utilization. 2. New field on `PostExecutionReport`: `budget_utilization` (optional list of dicts with budget_id, total, consumed, remaining, utilization_pct). 3. Budgets with remaining < 0 contribute to `passed = False`. 4. Budget utilization > 90% but remaining >= 0 produces a warning. |
| **Affected Files** | `src/contextcore/contracts/postexec/validator.py` |

### Layer 6 Integration (Observability and Alerting)

#### REQ-6E-013: Budget Exhaustion Alert Rules

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-013 |
| **Priority** | P2 |
| **Description** | Add default alert rules to `DEFAULT_ALERT_RULES` for budget exhaustion conditions. These fire based on metrics extracted from `WorkflowRunSummary` and `PostExecutionReport`. |
| **Acceptance Criteria** | 1. New rule `budget.exhausted.critical`: fires when `budgets_exhausted > 0`, severity BLOCKING. 2. New rule `budget.exceeded.warning`: fires when `budgets_exceeded > 0`, severity WARNING. 3. New rule `budget.utilization.high`: fires when any budget utilization exceeds 90%, severity ADVISORY. 4. `AlertEvaluator._extract_metrics()` extracts `budgets_exhausted`, `budgets_exceeded`, and `budget_utilization_max_pct` from the provided results. |
| **Affected Files** | `src/contextcore/contracts/observability/alerts.py` |

#### REQ-6E-014: Budget Alert Rule Extensibility

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-014 |
| **Priority** | P3 |
| **Description** | Users must be able to define custom alert rules for specific budget IDs (e.g., "alert when retry budget utilization exceeds 80%"). The existing `AlertRule` model should work for budget-specific metrics without modification. |
| **Acceptance Criteria** | 1. Budget metrics are exposed with budget_id suffix: `budget.{budget_id}.utilization_pct`, `budget.{budget_id}.remaining`. 2. Users can add `AlertRule(metric="budget.retry.utilization_pct", operator="gt", threshold=80.0)` to their rule set. 3. `_extract_metrics()` produces per-budget-id metrics when budget data is available. |
| **Affected Files** | `src/contextcore/contracts/observability/alerts.py` |

### OTel Emission

#### REQ-6E-015: Budget Boundary Span Events

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-015 |
| **Priority** | P1 |
| **Description** | Emit an OTel span event at each phase boundary recording budget consumption and remaining balance. Follows the `_HAS_OTEL` guard + `_add_span_event()` pattern from `contracts/runtime/otel.py`. |
| **Acceptance Criteria** | 1. Event name: `context.budget.phase_boundary`. 2. Attributes include: `budget.id` (str), `budget.phase` (str), `budget.allocated` (float), `budget.consumed` (float), `budget.remaining` (float), `budget.exceeded` (bool), `budget.status` (str -- "intact", "degraded", "broken"). 3. One event per budget dimension per phase boundary. 4. When OTel is not installed, the function is a no-op (graceful degradation). |
| **Affected Files** | `src/contextcore/contracts/runtime/otel.py` (or new file `src/contextcore/contracts/propagation/budget_otel.py`) |

#### REQ-6E-016: Budget Summary Span Event

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-016 |
| **Priority** | P2 |
| **Description** | Emit an OTel span event at workflow completion summarizing all budget dimensions. This complements the existing `context.runtime.workflow_summary` event. |
| **Acceptance Criteria** | 1. Event name: `context.budget.workflow_summary`. 2. Attributes include: `budget.total_tracked` (int), `budget.total_exceeded` (int), `budget.total_exhausted` (int), and per-budget utilization as `budget.{budget_id}.utilization_pct` (float). 3. Emitted alongside `emit_workflow_summary()` when budget data is present. 4. Guarded by `_HAS_OTEL`. |
| **Affected Files** | `src/contextcore/contracts/runtime/otel.py` (or `src/contextcore/contracts/propagation/budget_otel.py`) |

### Edge Cases and Error Handling

#### REQ-6E-017: Budget Overflow Handling

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-017 |
| **Priority** | P1 |
| **Description** | When a phase consumes more than its allocation, the excess is deducted from the pipeline remaining balance. The next phase still receives its declared allocation -- budgets do not "borrow" from future phases. Status transitions: INTACT when within allocation, DEGRADED when exceeded but pipeline remaining >= 0, BROKEN when pipeline remaining < 0. |
| **Acceptance Criteria** | 1. Phase consuming 300ms of a 200ms allocation leaves remaining = total - all_consumed_so_far (not total - sum_of_allocations). 2. Status is computed from the pipeline-wide remaining, not the per-phase delta. 3. Downstream phases are not penalized in their allocation amounts (they still get their declared allocation checked, not a reduced one). |
| **Affected Files** | `src/contextcore/contracts/propagation/tracker.py` (or `src/contextcore/contracts/propagation/budget.py`) |

#### REQ-6E-018: Unbudgeted Phase Handling

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-018 |
| **Priority** | P2 |
| **Description** | When `record_consumption` is called for a phase that has no allocation in the `BudgetDefinition`, the consumption is still deducted from the pipeline total, and the result has `allocated = 0.0` with `exceeded = True`. This handles dynamically added phases or phases not anticipated at contract authoring time. |
| **Acceptance Criteria** | 1. Calling `record_consumption(context, "unknown_phase", "latency", 100)` succeeds. 2. Result shows `allocated=0.0`, `consumed=100`, `exceeded=True`. 3. The pipeline remaining balance decreases by 100. 4. An ADVISORY-level log message notes the unbudgeted phase. |
| **Affected Files** | `src/contextcore/contracts/propagation/tracker.py` (or `src/contextcore/contracts/propagation/budget.py`) |

#### REQ-6E-019: Zero and Negative Budget Guards

| Field | Value |
|-------|-------|
| **ID** | REQ-6E-019 |
| **Priority** | P2 |
| **Description** | Budget definitions must reject invalid values at parse time. Total must be positive. Allocations must be non-negative. Consumption values must be non-negative at recording time. |
| **Acceptance Criteria** | 1. `BudgetDefinition` rejects `total <= 0` with a Pydantic validation error. 2. `BudgetDefinition` rejects negative values in `allocations`. 3. `BudgetTracker.record_consumption()` raises `ValueError` if `consumed < 0`. |
| **Affected Files** | `src/contextcore/contracts/propagation/schema.py`, `src/contextcore/contracts/propagation/tracker.py` (or `budget.py`) |

---

## Contract Schema

Complete YAML example showing the `budget_propagation` block within a context contract:

```yaml
schema_version: "0.2.0"
pipeline_id: "artisan-pipeline"
description: "Multi-budget propagation for the artisan code generation pipeline"

budget_propagation:
  budgets:
    - budget_id: "latency"
      total: 2000
      unit: "ms"
      allocations:
        seed: 200
        plan: 500
        design: 300
        implement: 800
        validate: 200
      on_exceeded: WARNING

    - budget_id: "retry"
      total: 10
      unit: "retries"
      allocations:
        seed: 2
        plan: 2
        design: 2
        implement: 3
        validate: 1
      on_exceeded: BLOCKING

    - budget_id: "tokens"
      total: 100000
      unit: "tokens"
      allocations:
        seed: 5000
        plan: 20000
        design: 25000
        implement: 40000
        validate: 10000
      on_exceeded: WARNING

    - budget_id: "cost"
      total: 5.00
      unit: "usd"
      allocations:
        seed: 0.25
        plan: 1.00
        design: 1.25
        implement: 2.00
        validate: 0.50
      on_exceeded: ADVISORY

phases:
  seed:
    entry:
      required:
        - name: project.id
          severity: BLOCKING
    exit:
      required:
        - name: domain
          severity: BLOCKING
  plan:
    entry:
      required:
        - name: domain
          severity: BLOCKING
    exit:
      required:
        - name: architecture_plan
          severity: BLOCKING
  design:
    entry:
      required:
        - name: architecture_plan
          severity: BLOCKING
    exit:
      required:
        - name: design_spec
          severity: BLOCKING
  implement:
    entry:
      required:
        - name: design_spec
          severity: BLOCKING
    exit:
      required:
        - name: generated_code
          severity: BLOCKING
  validate:
    entry:
      required:
        - name: generated_code
          severity: BLOCKING
    exit:
      required:
        - name: validation_result
          severity: BLOCKING

propagation_chains: []
```

### Context State Example (After Phase "plan" Completes)

```python
context = {
    "project.id": "myproject",
    "domain": "web_application",
    "architecture_plan": "...",
    "_cc_propagation": { ... },       # Field provenance (existing)
    "_cc_budgets": {                   # Budget state (new)
        "latency": {
            "remaining": 1300.0,       # 2000 - 200 (seed) - 500 (plan)
            "last_phase": "plan",
            "last_consumed": 450.0,    # Actual plan consumption
        },
        "retry": {
            "remaining": 7,            # 10 - 1 (seed) - 2 (plan)
            "last_phase": "plan",
            "last_consumed": 2,
        },
        "tokens": {
            "remaining": 78000,        # 100000 - 4000 (seed) - 18000 (plan)
            "last_phase": "plan",
            "last_consumed": 18000,
        },
        "cost": {
            "remaining": 3.90,         # 5.00 - 0.20 (seed) - 0.90 (plan)
            "last_phase": "plan",
            "last_consumed": 0.90,
        },
    },
}
```

---

## Integration Points

Multi-Budget Propagation plugs into the existing 7-layer defense-in-depth architecture without modifying any layer's structure. It adds a new contract type that the existing layers validate.

### Layer 1: Context Contracts (Declarations)

`BudgetPropagationSpec` and `BudgetDefinition` are declared in the contract YAML alongside `phases` and `propagation_chains`. The models live in `schema.py` following the existing pattern.

### Layer 2: Static Analysis

No direct integration. Budget allocations are simple arithmetic (sum <= total) handled by Pydantic validators. If a static analyzer is added later, it can verify budget consistency across graph topologies (Concern 12).

### Layer 3: Pre-Flight Verification

The `PreflightChecker` gains two new checks (REQ-6E-004, REQ-6E-005):
- Allocation sum validation (allocations must sum <= total)
- Phase name consistency (allocation phase names must match contract phases)

### Layer 4: Runtime Boundary Checks

`RuntimeBoundaryGuard.exit_phase()` reads `_cc_budgets` from the context and checks whether the phase exceeded its allocation. Enforcement follows the existing mode semantics (strict/permissive/audit). Budget results are recorded in `PhaseExecutionRecord`.

### Layer 5: Post-Execution Validation

`PostExecutionValidator` checks final budget state after all phases complete. Reports utilization percentages and flags exhausted budgets (remaining < 0) as failures.

### Layer 6: Observability and Alerting

`AlertEvaluator` gains new default rules for budget exhaustion. Per-budget metrics are extracted for custom alert rules. OTel span events are emitted at each boundary and at workflow completion.

### Layer 7: Regression Prevention

No direct integration in this iteration. Future work: `RegressionGate` could track budget utilization trends over time and alert when a phase's consumption drifts upward across runs.

---

## Test Requirements

### Unit Tests

| Test | Description | Requirements Covered |
|------|-------------|---------------------|
| `test_budget_definition_valid` | Parse a valid `BudgetDefinition` from dict | REQ-6E-001 |
| `test_budget_definition_rejects_extra_fields` | `extra="forbid"` rejects unknown keys | REQ-6E-001 |
| `test_budget_definition_rejects_zero_total` | `total=0` raises validation error | REQ-6E-019 |
| `test_budget_definition_rejects_negative_allocation` | Negative allocation value raises error | REQ-6E-019 |
| `test_budget_propagation_spec_valid` | Parse a full multi-budget spec | REQ-6E-002 |
| `test_context_contract_with_budgets` | Parse a contract with `budget_propagation` | REQ-6E-003 |
| `test_context_contract_without_budgets` | Existing contract without budgets still parses | REQ-6E-003 |
| `test_allocation_sum_validation` | Allocations summing > total raises error | REQ-6E-004 |
| `test_allocation_sum_equal_to_total` | Allocations summing = total is valid | REQ-6E-004 |
| `test_allocation_sum_less_than_total` | Allocations summing < total is valid (slack) | REQ-6E-004 |
| `test_tracker_record_consumption` | Record consumption for a single phase/budget | REQ-6E-006, REQ-6E-007 |
| `test_tracker_accumulates_across_phases` | Multiple phases accumulate correctly | REQ-6E-006, REQ-6E-008 |
| `test_tracker_stamps_context` | `_cc_budgets` key populated in context | REQ-6E-008 |
| `test_tracker_exceeded_within_total` | Phase exceeds allocation but remaining >= 0 -> DEGRADED | REQ-6E-007, REQ-6E-017 |
| `test_tracker_exhausted` | Remaining < 0 -> BROKEN | REQ-6E-007, REQ-6E-017 |
| `test_tracker_within_allocation` | Phase within allocation -> INTACT | REQ-6E-007 |
| `test_tracker_negative_consumption_raises` | Negative consumed raises ValueError | REQ-6E-019 |
| `test_tracker_batch_consumption` | `record_phase_budgets()` records multiple budgets | REQ-6E-009 |
| `test_tracker_unbudgeted_phase` | Unknown phase still tracks consumption | REQ-6E-018 |
| `test_guard_budget_blocking_strict` | Guard raises in strict mode on exhausted BLOCKING budget | REQ-6E-010 |
| `test_guard_budget_warning_continues` | Guard logs but continues on WARNING budget exceeded | REQ-6E-010 |
| `test_guard_summary_includes_budgets` | Summary includes budget aggregate metrics | REQ-6E-011 |
| `test_postexec_budget_utilization` | Post-exec report includes budget utilization | REQ-6E-012 |
| `test_postexec_exhausted_fails` | Exhausted budget causes `passed=False` | REQ-6E-012 |
| `test_alert_exhausted_fires` | Budget exhaustion alert rule fires | REQ-6E-013 |
| `test_alert_exceeded_fires` | Budget exceeded alert rule fires | REQ-6E-013 |
| `test_otel_phase_boundary_event` | Span event emitted with budget attributes | REQ-6E-015 |
| `test_otel_summary_event` | Workflow summary span event includes budget data | REQ-6E-016 |
| `test_otel_no_otel_graceful` | No crash when OTel is not installed | REQ-6E-015, REQ-6E-016 |

### Integration Tests

| Test | Description |
|------|-------------|
| `test_full_pipeline_budget_tracking` | Run a 5-phase pipeline with all four budget types, verify context state at each boundary and final report |
| `test_budget_with_existing_propagation` | Budgets compose correctly with field propagation tracking (`_cc_propagation` and `_cc_budgets` coexist) |
| `test_budget_alert_pipeline` | Budget data flows from Layer 4 -> Layer 5 -> Layer 6 alert evaluation |

### Test File Location

Tests should be placed in `tests/unit/contextcore/contracts/propagation/test_budget.py` for unit tests and `tests/integration/contracts/test_budget_pipeline.py` for integration tests.

---

## Non-Requirements

The following are explicitly out of scope for this implementation:

1. **Dynamic budget reallocation.** Budgets are declared statically in the contract. There is no mechanism for a phase to "negotiate" a larger allocation at runtime by borrowing from downstream phases. This is a potential future enhancement.

2. **Budget inheritance across nested pipelines.** If pipeline A calls sub-pipeline B, B does not automatically inherit A's remaining budget. Each pipeline tracks its own budgets independently.

3. **Historical budget trending (Layer 7).** Regression gates that track budget utilization trends over time (e.g., "this phase's token consumption increased 30% over the last 10 runs") are deferred to a future Layer 7 extension.

4. **Budget-aware scheduling.** The budget system does not influence phase ordering or parallelization decisions. It is purely observational and enforcement -- it reports and optionally blocks, but does not reroute.

5. **Automatic budget estimation.** There is no mechanism to auto-detect consumption amounts. The caller (phase executor or framework adapter) must report consumption values explicitly to `BudgetTracker.record_consumption()`.

6. **Currency conversion or unit normalization.** The `unit` field is informational. The system does not convert between units (e.g., tokens to cost). Each budget dimension is tracked independently in its declared unit.

7. **Grafana dashboard.** Dashboard panels for budget visualization are a separate deliverable, not covered by this requirements document.
