# SLO Budget Propagation Contracts — Layer 6 Design

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.78
**Implementation:** Not yet implemented
**Related:**
- [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — theoretical foundation
- [Context Propagation Contracts (Layer 1)](CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) — foundational contract layer
- [A2A Contracts Design](A2A_CONTRACTS_DESIGN.md) — contract-first agent coordination
- [A2A Truncation Prevention](contextcore-a2a-comms-design.md) — proactive LLM truncation prevention
- [Semantic Conventions](../semantic-conventions.md) — attribute naming standards

---

## 1. Problem

Multi-phase pipelines operate under budgets — latency, cost, tokens, error
rates. These budgets are declared at the pipeline edge ("this workflow must
complete in 30 seconds," "this run must cost less than $0.50") but are
**consumed at every hop**. No system tracks how much budget remains at each
phase boundary. The budget simply overflows, and the violation is detected
after the fact — if it's detected at all.

This is the budget analog of the context propagation problem solved in Layer 1:
information (budget remaining) must travel across phase boundaries, and when it
doesn't, the system degrades silently.

### Example 1: Latency Budget Overflow

The Artisan pipeline has a 30-second end-to-end SLO. Seven phases share this
budget:

```
Phase:     plan → scaffold → design → implement → test → review → finalize
Allocated: 5s      2s         3s       15s          3s     1s       1s
Actual:    4.2s    1.8s       4.0s     25.3s        --     --       --
                              ↑ over   ↑ BLOWN
```

Phase 3 (design) uses 4.0s against a 3s allocation — over its allocation but
not catastrophic. Phase 4 (implement) calls an LLM that takes 25.3s against a
15s allocation. By the time implement finishes, 35.3s have elapsed. The pipeline
misses its 30-second SLO at Phase 4, but nobody knew Phase 4's budget was only
15s until it was too late. Phases 5-7 never execute or run with zero remaining
budget.

The deeper problem: Phase 4 didn't know that Phase 3 had already consumed 1s
of slack. The remaining budget entering Phase 4 was 18s (30 - 4.2 - 1.8 - 4.0),
not the 15s it was allocated. But Phase 4 had no way to query this. It treated
its allocation as an independent constraint, not a slice of a shared budget.

### Example 2: Token Cost Budget

A pipeline has a $0.50 per-run budget for LLM calls. Three phases make LLM
calls:

```
Phase:     plan → implement → review
Allocated: $0.05    $0.30      $0.05
Actual:    $0.15    $0.30      $0.05
           ↑ 3x over
```

Phase 1 (plan) uses $0.15 against a $0.05 allocation — the domain
classification prompt was more expensive than estimated. Phase 2 (implement)
uses its full $0.30 allocation. Total: $0.50. Phase 3 (review) needs $0.05 but
the total budget is exhausted. Nobody tracked remaining budget at each phase
boundary. The run either exceeds its cost budget or the review phase silently
skips LLM-powered quality checks.

### Example 3: Error Budget Exhaustion

A service has a 0.1% error budget over a 30-day window (SLO: 99.9%
availability). Three downstream services share this budget:

```
Service:   A        B        C        D (remaining)
Budget:    0.05%    0.04%    0.01%    0.00%
                                      ↑ exhausted
```

Service A consumes 0.05%, Service B consumes 0.04%. That leaves 0.01% for
Service C and 0.00% for everything else. But nobody propagates the remaining
budget. Service D operates as if it has its full allocation, and its first error
breaches the SLO.

### Example 4: Token Count Budget (LLM Context Windows)

An agent pipeline has a 50,000-token budget for a multi-step reasoning task.
Each phase consumes tokens from the context window:

```
Phase:     plan → implement → test → review
Allocated: 5,000   30,000     10,000  5,000
Actual:    8,200   30,000     --      --
           ↑ large plan
```

Phase 1 produces an oversized plan (8,200 tokens). Phase 2 uses its full
30,000 tokens. Total: 38,200 tokens. Phase 3 needs 10,000 tokens but only
11,800 remain. The LLM either truncates its output or the quality degrades.
Without budget tracking, nobody knows that Phase 1's oversized plan will
cascade into a Phase 3 failure.

### Why Existing Tools Don't Solve This

**SLO monitoring tools** (Sloth, OpenSLO, Nobl9) track whether an SLO is met
*after the fact*. They answer "did we miss our SLO this month?" not "will this
pipeline run exceed its budget at Phase 4?"

**gRPC deadline propagation** propagates a wall-clock deadline across hops, but
it is a *mechanism*, not a *contract system*. It says "you have 15 seconds left"
but not "you *should* use at most 5 seconds." There is no declaration of
per-phase allocation, no tracking of per-phase consumption, and no signal when
a phase exceeds its allocation but the total budget still has room.

**Circuit breakers and retry budgets** react *after* the budget is blown. They
are the equivalent of catching a NullPointerException rather than using a type
system to prevent null references.

**Cost management tools** (AWS Cost Explorer, GCP Billing) track spend at the
account/project level, not at the pipeline-phase level. They can tell you that
LLM costs spiked this week, but not that Phase 1 of the Artisan pipeline is
consuming 3x its allocation.

---

## 2. Solution Overview

A `BudgetPropagationSpec` contract system that applies the same four primitives
from the Context Correctness by Construction framework (Declare, Validate,
Track, Emit) to budget propagation across pipeline phases.

```
                    YAML Contract
              (artisan-pipeline.budget.yaml)
                         |
                    ContractLoader
                     (parse + cache)
                         |
              +----------+----------+
              v                     v
        BudgetValidator       BudgetTracker
        (per-phase checks)    (consume + remaining)
              |                     |
              v                     v
      BudgetCheckResult       BudgetState
      (WITHIN_BUDGET /        (total, consumed,
       OVER_ALLOCATION /       remaining, per_phase)
       BUDGET_EXHAUSTED)
              |                     |
              +----------+----------+
                         |
                         v
               OTel Span Event Emission
               (budget.check.passed,
                budget.check.overallocated,
                budget.exhausted,
                budget.summary)
```

### Core Types

```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Any


class BudgetType(str, Enum):
    """Types of budgets that can be tracked across pipeline phases."""

    LATENCY_MS = "latency_ms"
    COST_DOLLARS = "cost_dollars"
    TOKEN_COUNT = "token_count"
    ERROR_RATE = "error_rate"
    CUSTOM = "custom"


class OverflowPolicy(str, Enum):
    """What to do when a phase exceeds its allocation."""

    WARN = "warn"        # Log + emit OTel event, continue execution
    BLOCK = "block"      # Halt pipeline if total budget exhausted
    REDISTRIBUTE = "redistribute"  # Take from future phases


class BudgetHealth(str, Enum):
    """Budget health at a specific checkpoint."""

    WITHIN_BUDGET = "within_budget"
    OVER_ALLOCATION = "over_allocation"
    BUDGET_EXHAUSTED = "budget_exhausted"


class BudgetAllocation(BaseModel, extra="forbid"):
    """Per-phase budget allocation and consumption tracking."""

    phase: str
    allocated: float
    consumed: float = 0.0
    remaining: float = Field(default=0.0)

    @property
    def utilization_pct(self) -> float:
        if self.allocated == 0:
            return 100.0 if self.consumed > 0 else 0.0
        return (self.consumed / self.allocated) * 100.0

    @property
    def over_allocation(self) -> bool:
        return self.consumed > self.allocated


class BudgetSpec(BaseModel, extra="forbid"):
    """A single budget declaration within a contract."""

    budget_id: str
    type: BudgetType
    total: float
    allocations: dict[str, float]  # phase_name -> allocated amount
    overflow_policy: OverflowPolicy = OverflowPolicy.WARN
    description: str | None = None
    unit: str | None = None  # Optional display unit (e.g. "ms", "$", "tokens")


class BudgetPropagationSpec(BaseModel, extra="forbid"):
    """Top-level budget propagation contract."""

    schema_version: str = "0.1.0"
    contract_type: str = "budget_propagation"
    pipeline_id: str
    description: str | None = None
    budgets: list[BudgetSpec]


class BudgetCheckResult(BaseModel, extra="forbid"):
    """Result of a budget check at a phase boundary."""

    budget_id: str
    budget_type: BudgetType
    phase: str
    health: BudgetHealth
    allocated: float
    consumed: float
    remaining_total: float
    remaining_pct: float
    message: str
    overflow_policy: OverflowPolicy


class BudgetSummaryResult(BaseModel, extra="forbid"):
    """End-of-pipeline budget summary."""

    budget_id: str
    budget_type: BudgetType
    total: float
    consumed: float
    remaining: float
    remaining_pct: float
    phases_within_budget: int
    phases_over_allocation: int
    overall_health: BudgetHealth
    per_phase: list[BudgetAllocation]
```

### Split Placement

Following the same pattern as Layer 1, the framework lives in ContextCore and
concrete pipeline budget contracts live in the consuming repo.

| Component | Repo | Path |
|---|---|---|
| Schema models | ContextCore | `src/contextcore/contracts/budget/schema.py` |
| YAML loader | ContextCore | `src/contextcore/contracts/budget/loader.py` |
| Budget validator | ContextCore | `src/contextcore/contracts/budget/validator.py` |
| Budget tracker | ContextCore | `src/contextcore/contracts/budget/tracker.py` |
| OTel emission | ContextCore | `src/contextcore/contracts/budget/otel.py` |
| Artisan budget contract | startd8-sdk | `src/startd8/contractors/contracts/artisan-pipeline.budget.yaml` |
| Budget wiring | startd8-sdk | `src/startd8/contractors/budget_tracking.py` |

---

## 3. Contract Format

Contracts are YAML files validated against the `BudgetPropagationSpec` Pydantic
v2 model. All models use `extra="forbid"` to reject unknown keys at parse time.

### 3.1 Top-Level Structure

```yaml
schema_version: "0.1.0"
contract_type: budget_propagation
pipeline_id: artisan
description: >
  Budget allocations for the Artisan code generation pipeline.
  Tracks latency, token count, and cost budgets across 7 phases.

budgets:
  - budget_id: latency_budget
    type: latency_ms
    total: 30000  # 30 seconds
    allocations:
      plan: 5000
      scaffold: 2000
      design: 3000
      implement: 15000
      test: 3000
      review: 1000
      finalize: 1000
    overflow_policy: warn

  - budget_id: token_budget
    type: token_count
    total: 50000
    allocations:
      plan: 5000
      implement: 30000
      test: 10000
      review: 5000
    overflow_policy: block

  - budget_id: cost_budget
    type: cost_dollars
    total: 0.50
    allocations:
      plan: 0.05
      implement: 0.30
      test: 0.10
      review: 0.05
    overflow_policy: warn
```

### 3.2 Allocation Rules

**Allocations do not need to sum to total.** The unallocated remainder is a
**reserve** available to any phase that overflows. This is intentional — it
allows pipelines to declare "Phase 4 should use ~15s but can use up to 20s if
there's room."

```yaml
budgets:
  - budget_id: latency_budget
    type: latency_ms
    total: 30000
    allocations:
      plan: 5000       # 5s
      scaffold: 2000   # 2s
      design: 3000     # 3s
      implement: 12000 # 12s
      test: 3000       # 3s
      review: 1000     # 1s
      finalize: 1000   # 1s
      # Sum: 27000 — 3000ms reserve
    overflow_policy: warn
```

If a pipeline has phases not listed in `allocations`, those phases have an
implicit allocation of 0. Any consumption by unlisted phases is drawn from the
total budget's reserve. If the total budget is exhausted, the unlisted phase
triggers a `BUDGET_EXHAUSTED` event.

**Allocations that exceed total are a validation error.** The loader rejects
contracts where `sum(allocations.values()) > total` at parse time.

### 3.3 Partial Budget Contracts

Not every budget needs to track every phase. A cost budget might only track
phases that make LLM calls:

```yaml
budgets:
  - budget_id: llm_cost
    type: cost_dollars
    total: 0.50
    allocations:
      plan: 0.05        # Domain classification LLM call
      implement: 0.30   # Code generation LLM calls
      review: 0.05      # Code review LLM call
    overflow_policy: block
    description: "LLM API costs only — scaffold, design, test, finalize have no LLM calls"
```

Phases not in `allocations` (scaffold, design, test, finalize) are not checked.
Their execution time, tokens, or costs are invisible to this budget. This is
a deliberate design choice: partial contracts are better than no contracts.

### 3.4 Multiple Budget Types

A single pipeline can declare multiple budgets of different types. Each budget
is tracked independently. A phase can be `WITHIN_BUDGET` for latency and
`OVER_ALLOCATION` for cost simultaneously.

The `budget_id` uniquely identifies each budget within a contract. It is used
in OTel event attributes and dashboard queries. Convention:

```
{pipeline_id}_{budget_type}    →    artisan_latency
{pipeline_id}_{custom_name}    →    artisan_llm_cost
```

---

## 4. Budget States

Budget health at any checkpoint is one of three states. These states map to the
`ChainStatus` enum from `contracts/types.py` for consistency across the
contract framework.

### 4.1 State Definitions

| Budget Health | ChainStatus Mapping | Meaning | Trigger |
|---|---|---|---|
| `WITHIN_BUDGET` | `ChainStatus.INTACT` | Phase consumed less than or equal to its allocation | `consumed <= allocated` |
| `OVER_ALLOCATION` | `ChainStatus.DEGRADED` | Phase exceeded its allocation, but total budget still has remaining capacity | `consumed > allocated AND total_remaining > 0` |
| `BUDGET_EXHAUSTED` | `ChainStatus.BROKEN` | Total budget fully consumed; remaining phases have zero budget | `total_remaining <= 0` |

### 4.2 State Transitions

Budget health can only degrade monotonically within a single pipeline run.
Once a budget reaches `BUDGET_EXHAUSTED`, it stays there for all subsequent
phases. `OVER_ALLOCATION` can recover to `WITHIN_BUDGET` in subsequent phases
(a later phase might use less than allocated, restoring slack), but
`BUDGET_EXHAUSTED` is terminal.

```
                       +------------------+
                       | WITHIN_BUDGET    |  ← Phase consumed <= allocation
                       +------------------+
                              |
                     phase exceeds allocation
                     but total has remaining
                              |
                              v
                       +------------------+
                       | OVER_ALLOCATION  |  ← Phase consumed > allocation
                       +------------------+     Total remaining > 0
                              |
                     total budget consumed
                              |
                              v
                       +------------------+
                       | BUDGET_EXHAUSTED |  ← Total remaining <= 0
                       +------------------+     TERMINAL — no recovery
```

### 4.3 Per-Phase vs. Total Budget Health

The distinction between per-phase health and total budget health is critical:

- **Per-phase health** answers: "Did this phase stay within its allocation?"
- **Total budget health** answers: "Does the pipeline have remaining budget?"

A phase can be `OVER_ALLOCATION` (it used more than its slice) while the total
budget is still `WITHIN_BUDGET` (other phases used less than theirs, creating
slack). This is the `DEGRADED` state — the pipeline is not broken, but the
allocation assumptions were wrong.

The dangerous case is when per-phase `OVER_ALLOCATION` accumulates across
multiple phases until the total budget is consumed. This cascade is exactly what
the tracking system is designed to surface early.

---

## 5. Budget Tracking

### 5.1 Context Dict Storage

Budget state is stored in the context dict under the reserved key `_cc_budgets`,
following the same pattern as provenance tracking (`_cc_propagation` in Layer 1).

```python
context["_cc_budgets"] = {
    "latency_budget": {
        "total": 30000,
        "consumed": 10000,
        "remaining": 20000,
        "remaining_pct": 66.7,
        "overflow_policy": "warn",
        "per_phase": {
            "plan": {"allocated": 5000, "consumed": 4200, "remaining": 800},
            "scaffold": {"allocated": 2000, "consumed": 1800, "remaining": 200},
            "design": {"allocated": 3000, "consumed": 4000, "remaining": -1000},
        }
    },
    "cost_budget": {
        "total": 0.50,
        "consumed": 0.25,
        "remaining": 0.25,
        "remaining_pct": 50.0,
        "overflow_policy": "warn",
        "per_phase": {
            "plan": {"allocated": 0.05, "consumed": 0.15, "remaining": -0.10},
            "implement": {"allocated": 0.30, "consumed": 0.10, "remaining": 0.20},
        }
    }
}
```

**Why store in the context dict?** For the same reason Layer 1 stores provenance
there: the context dict is the carrier. Budget state must travel with the
pipeline, through the same channel, subject to the same propagation dynamics.
If budget state were stored externally, downstream phases would need a separate
lookup to check remaining budget — and that lookup could fail, creating a
meta-problem.

The `_cc_` prefix signals "internal, do not touch" — handlers should not
overwrite this key.

### 5.2 BudgetTracker API

```python
class BudgetTracker:
    """Tracks budget consumption across pipeline phases."""

    def __init__(self, contract: BudgetPropagationSpec):
        self._contract = contract
        self._state: dict[str, BudgetState] = {}

    def initialize(self, context: dict) -> None:
        """Initialize budget state in the context dict.

        Called once at pipeline start. Sets up _cc_budgets with total
        budgets and zero consumption for all phases.
        """
        state = {}
        for budget in self._contract.budgets:
            state[budget.budget_id] = {
                "total": budget.total,
                "consumed": 0.0,
                "remaining": budget.total,
                "remaining_pct": 100.0,
                "overflow_policy": budget.overflow_policy.value,
                "per_phase": {},
            }
        context["_cc_budgets"] = state

    def record_consumption(
        self,
        context: dict,
        budget_id: str,
        phase: str,
        consumed: float,
    ) -> BudgetCheckResult:
        """Record budget consumption for a phase and return health check.

        Called after each phase completes. Updates _cc_budgets in the
        context dict and returns a BudgetCheckResult indicating health.
        """
        budget_state = context["_cc_budgets"][budget_id]
        budget_spec = self._get_spec(budget_id)
        allocated = budget_spec.allocations.get(phase, 0.0)

        # Update per-phase state
        budget_state["per_phase"][phase] = {
            "allocated": allocated,
            "consumed": consumed,
            "remaining": allocated - consumed,
        }

        # Update total state
        budget_state["consumed"] += consumed
        budget_state["remaining"] = budget_state["total"] - budget_state["consumed"]
        budget_state["remaining_pct"] = (
            (budget_state["remaining"] / budget_state["total"]) * 100.0
            if budget_state["total"] > 0
            else 0.0
        )

        # Determine health
        if budget_state["remaining"] <= 0:
            health = BudgetHealth.BUDGET_EXHAUSTED
            message = (
                f"Budget '{budget_id}' exhausted: "
                f"consumed {budget_state['consumed']:.2f} "
                f"of {budget_state['total']:.2f} total"
            )
        elif consumed > allocated:
            health = BudgetHealth.OVER_ALLOCATION
            message = (
                f"Phase '{phase}' exceeded allocation for '{budget_id}': "
                f"consumed {consumed:.2f} of {allocated:.2f} allocated "
                f"({budget_state['remaining']:.2f} total remaining)"
            )
        else:
            health = BudgetHealth.WITHIN_BUDGET
            message = (
                f"Phase '{phase}' within budget for '{budget_id}': "
                f"consumed {consumed:.2f} of {allocated:.2f} allocated"
            )

        return BudgetCheckResult(
            budget_id=budget_id,
            budget_type=budget_spec.type,
            phase=phase,
            health=health,
            allocated=allocated,
            consumed=consumed,
            remaining_total=budget_state["remaining"],
            remaining_pct=budget_state["remaining_pct"],
            message=message,
            overflow_policy=budget_spec.overflow_policy,
        )

    def get_remaining(self, context: dict, budget_id: str) -> float:
        """Query remaining budget. Called before a phase to check feasibility."""
        return context["_cc_budgets"][budget_id]["remaining"]

    def get_summary(self, context: dict, budget_id: str) -> BudgetSummaryResult:
        """Generate end-of-pipeline budget summary."""
        ...

    def _get_spec(self, budget_id: str) -> BudgetSpec:
        for spec in self._contract.budgets:
            if spec.budget_id == budget_id:
                return spec
        raise ValueError(f"Unknown budget_id: {budget_id}")
```

### 5.3 Pre-Phase Budget Query

A critical feature is **pre-phase budget querying**. Before a phase executes,
it can check remaining budget and adjust behavior proactively:

```python
def _execute_phase(self, phase, context, ...):
    # 1. Check remaining budget BEFORE execution
    if self._budget_tracker:
        for budget_id in self._budget_tracker.budget_ids:
            remaining = self._budget_tracker.get_remaining(context, budget_id)
            spec = self._budget_tracker._get_spec(budget_id)
            allocated = spec.allocations.get(phase, 0.0)

            if remaining <= 0 and spec.overflow_policy == OverflowPolicy.BLOCK:
                raise BudgetExhaustedError(budget_id, phase, remaining)

            if remaining < allocated:
                # Inform the phase handler that budget is tight
                context[f"_cc_budget_hint_{budget_id}"] = {
                    "allocated": allocated,
                    "remaining": remaining,
                    "constrained": True,
                }

    # 2. Execute phase (with optional budget-aware behavior)
    start_time = time.monotonic()
    result = handler.execute(phase, context, ...)
    elapsed_ms = (time.monotonic() - start_time) * 1000

    # 3. Record consumption
    if self._budget_tracker:
        check = self._budget_tracker.record_consumption(
            context, "latency_budget", phase, elapsed_ms,
        )
        emit_budget_check(check)
```

This pre-phase query is what distinguishes budget *propagation* from budget
*monitoring*. Monitoring tells you after the fact that you exceeded your budget.
Propagation tells the next phase how much budget remains, enabling proactive
adaptation.

---

## 6. Overflow Policies

Three policies govern what happens when a budget is exceeded. The policy is
declared per-budget in the YAML contract.

### 6.1 `warn` — Log and Continue

The default policy. When a phase exceeds its allocation or the total budget is
exhausted:

1. Emit a `budget.check.overallocated` or `budget.exhausted` OTel span event
2. Log a WARNING-level message
3. Continue execution

This is the safe starting point for adoption. The pipeline behavior is
unchanged — the budget system is observational only. Teams can monitor budget
utilization in dashboards and tighten to `block` when they have confidence in
their allocations.

```python
if check.health == BudgetHealth.BUDGET_EXHAUSTED:
    emit_budget_exhausted(check)
    logger.warning(check.message)
    # Continue execution — warn policy
```

### 6.2 `block` — Halt on Exhaustion

When the **total** budget is exhausted (not just a per-phase over-allocation),
halt the pipeline. This prevents runaway cost or latency by treating budget
exhaustion as a blocking failure.

```python
if check.health == BudgetHealth.BUDGET_EXHAUSTED:
    emit_budget_exhausted(check)
    if check.overflow_policy == OverflowPolicy.BLOCK:
        raise BudgetExhaustedError(
            budget_id=check.budget_id,
            phase=check.phase,
            consumed=check.consumed,
            total=budget_spec.total,
        )
```

**`block` only triggers on `BUDGET_EXHAUSTED`, not on `OVER_ALLOCATION`.** A
phase exceeding its allocation is a signal, not a crisis. The crisis is when
the total budget is consumed and remaining phases have zero capacity.

**`BudgetExhaustedError`** is a new exception type in `contracts/types.py`.
It carries budget metadata for diagnostics:

```python
class BudgetExhaustedError(Exception):
    """Raised when a budget with block policy is exhausted."""

    def __init__(self, budget_id: str, phase: str, consumed: float, total: float):
        self.budget_id = budget_id
        self.phase = phase
        self.consumed = consumed
        self.total = total
        super().__init__(
            f"Budget '{budget_id}' exhausted at phase '{phase}': "
            f"consumed {consumed:.2f} of {total:.2f} total"
        )
```

### 6.3 `redistribute` — Dynamic Reallocation

When a phase exceeds its allocation, take remaining budget from future phases
and redistribute proportionally. This models how real teams work: if Phase 1
ran long, you cut time from Phase 6 and Phase 7, not from Phase 2 (which
already ran).

```python
def _redistribute(
    self,
    context: dict,
    budget_id: str,
    over_phase: str,
    overage: float,
) -> dict[str, float]:
    """Redistribute overage across future phases.

    Returns dict of {phase: new_allocation} for phases that were reduced.
    """
    budget_state = context["_cc_budgets"][budget_id]
    budget_spec = self._get_spec(budget_id)
    completed_phases = set(budget_state["per_phase"].keys())

    # Identify future phases with remaining allocation
    future_phases = {
        phase: alloc
        for phase, alloc in budget_spec.allocations.items()
        if phase not in completed_phases and phase != over_phase
    }

    if not future_phases:
        return {}  # No future phases to take from

    total_future = sum(future_phases.values())
    if total_future <= 0:
        return {}

    # Proportional reduction
    adjustments = {}
    for phase, alloc in future_phases.items():
        reduction = overage * (alloc / total_future)
        new_alloc = max(0, alloc - reduction)
        adjustments[phase] = new_alloc

    return adjustments
```

**Redistribution is logged as an OTel event** (`budget.redistributed`) with
the old and new allocations for each affected phase. This makes the adaptive
behavior observable.

**Redistribution does not increase any phase's allocation.** It can only
reduce future phases. If you need to increase a phase's allocation, that's a
contract change (YAML update), not a runtime decision.

---

## 7. OTel Event Semantics

All events follow ContextCore telemetry conventions and are emitted as OTel
span events on the current active span. If OTel is not installed, events are
logged only (no crash), following the `_HAS_OTEL` guard pattern from Layer 1.

### 7.1 Budget Check Events

**Event name:** `budget.check.passed`

Emitted when a phase completes within its allocation.

| Attribute | Type | Description |
|---|---|---|
| `budget.id` | str | Budget identifier (e.g. `"latency_budget"`) |
| `budget.type` | str | Budget type (e.g. `"latency_ms"`) |
| `budget.phase` | str | Phase name (e.g. `"implement"`) |
| `budget.health` | str | `"within_budget"` |
| `budget.allocated` | float | Allocated amount for this phase |
| `budget.consumed` | float | Actual consumption |
| `budget.remaining` | float | Remaining total budget |
| `budget.remaining_pct` | float | Remaining as percentage of total |

**TraceQL query — phases within budget:**
```traceql
{ name = "budget.check.passed" && span.budget.type = "latency_ms" }
```

---

**Event name:** `budget.check.overallocated`

Emitted when a phase exceeds its allocation but the total budget still has
remaining capacity.

| Attribute | Type | Description |
|---|---|---|
| `budget.id` | str | Budget identifier |
| `budget.type` | str | Budget type |
| `budget.phase` | str | Phase name |
| `budget.health` | str | `"over_allocation"` |
| `budget.allocated` | float | Allocated amount for this phase |
| `budget.consumed` | float | Actual consumption |
| `budget.overage` | float | Amount over allocation (`consumed - allocated`) |
| `budget.remaining` | float | Remaining total budget |
| `budget.remaining_pct` | float | Remaining as percentage of total |

**TraceQL query — phases that exceeded allocation:**
```traceql
{ name = "budget.check.overallocated" }
```

**TraceQL query — phases that used more than 2x their allocation:**
```traceql
{ name = "budget.check.overallocated" && span.budget.overage > span.budget.allocated }
```

---

**Event name:** `budget.exhausted`

Emitted when the total budget is consumed. This is the critical event — all
remaining phases have zero budget.

| Attribute | Type | Description |
|---|---|---|
| `budget.id` | str | Budget identifier |
| `budget.type` | str | Budget type |
| `budget.phase` | str | Phase where exhaustion occurred |
| `budget.health` | str | `"budget_exhausted"` |
| `budget.total` | float | Total budget |
| `budget.consumed` | float | Total consumed (>= total) |
| `budget.overflow_policy` | str | Policy applied (`"warn"`, `"block"`, `"redistribute"`) |
| `budget.phases_remaining` | int | Number of phases with zero budget |

**TraceQL query — budget exhaustion events:**
```traceql
{ name = "budget.exhausted" }
```

**TraceQL query — cost budget exhaustion (high priority):**
```traceql
{ name = "budget.exhausted" && span.budget.type = "cost_dollars" }
```

---

**Event name:** `budget.redistributed`

Emitted when the `redistribute` policy reallocates budget from future phases.

| Attribute | Type | Description |
|---|---|---|
| `budget.id` | str | Budget identifier |
| `budget.phase` | str | Phase that triggered redistribution |
| `budget.overage` | float | Amount that exceeded allocation |
| `budget.phases_affected` | int | Number of future phases reduced |
| `budget.redistributed_amount` | float | Total amount redistributed |

---

### 7.2 Summary Event

**Event name:** `budget.summary`

Emitted once per pipeline run (typically at finalize), aggregating budget
results across all phases.

| Attribute | Type | Description |
|---|---|---|
| `budget.id` | str | Budget identifier |
| `budget.type` | str | Budget type |
| `budget.total` | float | Total budget |
| `budget.consumed` | float | Total consumed |
| `budget.remaining` | float | Total remaining |
| `budget.remaining_pct` | float | Remaining as percentage |
| `budget.utilization_pct` | float | `consumed / total * 100` |
| `budget.phases_within_budget` | int | Count of phases within allocation |
| `budget.phases_over_allocation` | int | Count of phases over allocation |
| `budget.overall_health` | str | Overall budget health |

**TraceQL query — pipeline runs that exceeded budget:**
```traceql
{ name = "budget.summary" && span.budget.remaining < 0 }
```

**TraceQL query — budget utilization over 80%:**
```traceql
{ name = "budget.summary" && span.budget.utilization_pct > 80 }
```

### 7.3 Event Naming Convention

Budget events follow the `budget.*` namespace, parallel to the `context.*`
namespace used by Layer 1:

| Layer 1 Event | Layer 6 Budget Event |
|---|---|
| `context.boundary.entry` | `budget.check.passed` |
| `context.chain.degraded` | `budget.check.overallocated` |
| `context.chain.broken` | `budget.exhausted` |
| `context.propagation_summary` | `budget.summary` |

---

## 8. Relationship to Layers 1-5

Layer 6 builds on the primitives established in Layer 1 and extends them with
budget-specific semantics. Here is how the layers interact:

### Layer 1: Context Propagation

Layer 1 asks: "Did field X flow from Phase A to Phase F?" Layer 6 asks a
different question: "Did the budget flow correctly — and did each phase consume
an appropriate share?"

The two layers are complementary:
- Layer 1 tracks *what* flows (field values, provenance)
- Layer 6 tracks *how much* is consumed (budget allocation, utilization)

Both use the same carrier (`context` dict), the same state key pattern
(`_cc_propagation` for Layer 1, `_cc_budgets` for Layer 6), and the same OTel
emission pattern.

A combined query shows both: "Did domain classification propagate correctly
(Layer 1) AND did the pipeline complete within its latency budget (Layer 6)?"

```traceql
{ name = "context.propagation_summary" && span.context.completeness_pct = 100 } &&
{ name = "budget.summary" && span.budget.remaining > 0 }
```

### Layer 2: Schema Compatibility

Schema evolution contracts ensure that the *shape* of data at service boundaries
is correct. Budget contracts ensure that the *resource consumption* at those
boundaries is appropriate. A phase could receive correctly-shaped data (Layer 2
passes) but take too long processing it (Layer 6 fails).

### Layer 3: Semantic Conventions

Budget attribute names (`budget.id`, `budget.type`, `budget.consumed`, etc.)
must be registered in the Weaver semconv registry when this layer is
implemented. This ensures dashboard queries are consistent and discoverable.

### Layer 4: Causal Ordering

Budget tracking implicitly depends on causal ordering — you can only record
consumption for Phase N after Phase N completes. In sequential pipelines
(like Artisan), this is guaranteed by the execution model. In parallel
pipelines, budget tracking would need to handle concurrent consumption, which
is a future consideration.

### Layer 5: Capability Propagation

Budget propagation and capability propagation share a structural parallel:
both are metadata that must travel with the request and be checked at every
boundary. A future composition might track "does the caller have budget
remaining AND does the caller have permission?" at each boundary.

---

## 9. Relationship to Existing SLO Tools

### Google SRE Book — Error Budgets

The Google SRE book popularized **error budgets**: the inverse of an SLO. If
your SLO is 99.9%, your error budget is 0.1%. You can "spend" this budget on
deployments, experiments, or incidents.

ContextCore's budget propagation extends this concept in two ways:

1. **Per-hop allocation.** The SRE book tracks error budgets at the service
   level. ContextCore tracks them at the *pipeline phase* level. This is
   analogous to the difference between a project budget (total) and a
   department budget (per-unit allocation from the total).

2. **Real-time remaining budget.** Error budgets are typically computed from
   historical data (e.g., "we've used 40% of our error budget this month").
   ContextCore tracks remaining budget *within a single pipeline run*, enabling
   proactive decisions at each phase boundary.

### Sloth SLO Generator

[Sloth](https://github.com/slok/sloth) generates Prometheus recording rules and
alerting rules from SLO definitions. It answers "are we meeting our SLO?" over
a time window. ContextCore answers a different question: "will this specific
pipeline run meet its budget?" Sloth is retrospective (computed over historical
windows); ContextCore is prospective (computed at each phase boundary).

The two are complementary: Sloth monitors SLO compliance over time, ContextCore
prevents SLO violations within individual runs.

### OpenSLO

[OpenSLO](https://openslo.com/) is a vendor-neutral SLO specification. It
defines SLOs, SLIs, and error budgets in YAML. ContextCore's budget contracts
are compatible with OpenSLO's approach — an OpenSLO SLO definition could be
decomposed into a ContextCore budget contract that tracks per-phase allocation.

```yaml
# OpenSLO defines the SLO
apiVersion: openslo/v1
kind: SLO
spec:
  budgetingMethod: Occurrences
  objectives:
    - ratioMetrics:
        total: { ... }
        good: { ... }
      target: 0.999

# ContextCore decomposes it into per-phase allocations
schema_version: "0.1.0"
contract_type: budget_propagation
pipeline_id: checkout
budgets:
  - budget_id: error_budget
    type: error_rate
    total: 0.001  # 0.1% error budget from OpenSLO target
    allocations:
      payment: 0.0005
      inventory: 0.0003
      notification: 0.0002
```

### What ContextCore Adds

The unique contribution is **per-hop budget allocation and tracking**. Existing
tools track budgets at the service or system level. ContextCore tracks them at
the phase level within a single execution, with:

1. **Declaration** — per-phase allocations in YAML (not hardcoded)
2. **Propagation** — remaining budget travels with the context dict
3. **Pre-phase query** — phases can check remaining budget before execution
4. **Overflow policies** — configurable response to budget violations
5. **OTel observability** — budget events in the same trace as the pipeline

---

## 10. LLM-Specific Budgets

ContextCore's primary use case for budget propagation is LLM-powered pipelines,
where three budget types are critical:

### 10.1 Token Budgets

LLMs have hard context window limits (4K, 8K, 32K, 128K, 200K tokens depending
on model). A multi-phase pipeline that constructs prompts at each phase must
track total token consumption to avoid:

1. **Context window overflow**: Prompt exceeds model limit, causing truncation
   or API error
2. **Quality degradation**: As the prompt approaches the context limit, model
   attention degrades (the "lost in the middle" problem)
3. **Cost escalation**: Longer prompts cost more; token budget tracking prevents
   unbounded cost growth

Token budget tracking enables **proactive truncation prevention** — the design
goal of the A2A truncation prevention system documented in
[contextcore-a2a-comms-design.md](contextcore-a2a-comms-design.md). When
a phase can query remaining token budget before constructing its prompt, it can:

- Reduce prompt verbosity if budget is tight
- Request summarization of upstream context
- Decompose into multiple smaller prompts
- Signal to the orchestrator that the budget is insufficient for the task

```yaml
budgets:
  - budget_id: context_window
    type: token_count
    total: 128000  # Claude Opus context window
    allocations:
      plan: 8000      # System prompt + project context
      implement: 80000 # Code generation (largest phase)
      test: 25000      # Test generation
      review: 15000    # Code review
    overflow_policy: block  # Hard limit — model will reject
```

### 10.2 Cost Budgets

LLM API calls have per-token pricing. For ContextCore's Beaver (LLM
abstraction) and Artisan (code generation pipeline) use cases, cost tracking
per phase is essential:

```yaml
budgets:
  - budget_id: llm_cost
    type: cost_dollars
    total: 2.00  # Per-run cost ceiling
    allocations:
      plan: 0.10        # Domain classification, task decomposition
      scaffold: 0.00    # No LLM calls (template-based)
      design: 0.20      # Architecture design
      implement: 1.20   # Code generation (most expensive)
      test: 0.30        # Test generation
      review: 0.15      # Code review
      finalize: 0.05    # Summary generation
    overflow_policy: warn
    description: >
      LLM API costs per pipeline run. Implement phase is the most
      expensive due to multiple code generation calls.
```

Cost budgets integrate with Beaver's existing cost tracking
(`contextcore-beaver` already tracks per-provider, per-model costs). The budget
contract adds the *allocation* dimension — not just "how much did this cost?"
but "was this cost within the allocated budget for this phase?"

### 10.3 Integration with Truncation Prevention

The A2A truncation prevention design proposes span-based generation contracts
with `max_lines` and `max_tokens` in `ExpectedOutput`. Budget propagation
provides the *source* for these limits:

```python
# Budget tracking provides remaining tokens
remaining_tokens = budget_tracker.get_remaining(context, "context_window")

# Truncation prevention uses remaining tokens as the constraint
handoff = CodeGenerationHandoff(project_id="artisan", agent_id="orchestrator")
result = handoff.request_code(
    to_agent="code-generator",
    spec=CodeGenerationSpec(
        target_file="src/mymodule.py",
        description="Implement FooBar class",
        max_tokens=remaining_tokens,  # Budget-aware constraint
        required_exports=["FooBar"],
    )
)
```

Without budget tracking, `max_tokens` must be hardcoded or guessed. With
budget tracking, it's dynamically derived from the remaining budget at each
phase boundary.

### 10.4 Model-Specific Token Pricing

For cost budgets, the cost per token varies by model. The budget contract
declares total cost, and the tracker computes cost from consumption:

```python
def compute_cost(
    tokens_consumed: int,
    model: str,
    is_input: bool,
) -> float:
    """Compute cost from token consumption and model pricing.

    This delegates to Beaver's cost tracking for accurate per-model pricing.
    """
    from contextcore_beaver.cost import get_model_pricing
    pricing = get_model_pricing(model)
    rate = pricing.input_per_token if is_input else pricing.output_per_token
    return tokens_consumed * rate
```

---

## 11. Dashboard Integration

### 11.1 Recommended Panels

**Budget Utilization per Run (Stat panel)**

Shows overall budget utilization for the most recent pipeline run.

```traceql
{ name = "budget.summary" && span.budget.type = "latency_ms" }
| select(span.budget.utilization_pct)
```

**Budget Health over Time (Time series)**

Tracks the number of `OVER_ALLOCATION` and `BUDGET_EXHAUSTED` events over time
to identify trends (e.g., "implement phase has been over-allocating for the
last 20 runs").

```traceql
{ name =~ "budget.*" && span.budget.health != "within_budget" }
| rate()
```

**Per-Phase Budget Breakdown (Bar chart)**

Shows allocated vs consumed for each phase in a single pipeline run, per budget
type.

```traceql
{ name =~ "budget.check.*" && span.budget.id = "latency_budget" }
| select(
    span.budget.phase,
    span.budget.allocated,
    span.budget.consumed
  )
```

**Budget Exhaustion Events (Table)**

Shows all budget exhaustion events with phase, budget type, total consumed, and
overflow policy applied.

```traceql
{ name = "budget.exhausted" }
| select(
    span.budget.id,
    span.budget.type,
    span.budget.phase,
    span.budget.consumed,
    span.budget.total,
    span.budget.overflow_policy
  )
```

**Cost Budget Trend (Time series)**

Tracks LLM cost per pipeline run over time, broken down by phase.

```traceql
{ name = "budget.summary" && span.budget.type = "cost_dollars" }
| select(span.budget.consumed)
```

**Token Budget Utilization Heatmap**

Shows token consumption by phase over multiple runs, highlighting phases that
consistently approach their allocation.

```traceql
{ name = "budget.check.passed" && span.budget.type = "token_count" }
| select(span.budget.phase, span.budget.consumed)
```

### 11.2 Alerting Rules

**Alert: Budget exhausted (any type)**
```yaml
- alert: BudgetExhausted
  expr: |
    count_over_time(
      {job="artisan"} | json | event="budget.exhausted" [15m]
    ) > 0
  for: 0m
  labels:
    severity: critical
  annotations:
    summary: "Pipeline budget exhausted — phases running without budget"
```

**Alert: Cost budget utilization exceeding 80%**
```yaml
- alert: CostBudgetHighUtilization
  expr: |
    sum(rate(
      {job="artisan"} | json | event="budget.summary"
        | budget_type="cost_dollars"
        | utilization_pct > 80 [1h]
    )) > 0
  for: 15m
  labels:
    severity: warning
  annotations:
    summary: "LLM cost budget consistently above 80% utilization"
```

**Alert: Phase chronically over-allocated**
```yaml
- alert: PhaseChronicallyOverAllocated
  expr: |
    count_over_time(
      {job="artisan"} | json | event="budget.check.overallocated"
        | phase="implement" [24h]
    ) > 5
  for: 0m
  labels:
    severity: warning
  annotations:
    summary: "Phase 'implement' has exceeded its budget allocation in >5 runs in 24h"
```

---

## 12. Adoption Path

### 12.1 Phase 1: Observation Only (`warn` policy)

1. **Write a budget contract YAML** for your pipeline. Start with one budget
   type (latency is easiest to measure). Estimate allocations generously — the
   goal is to observe, not to enforce.

2. **Wire the BudgetTracker** into your orchestrator. Pass `budget_contract_path`
   alongside the existing `contract_path` for Layer 1.

3. **Monitor.** Build a dashboard panel for `budget.summary` events. Watch
   utilization patterns over 50-100 runs. Identify which phases consistently
   exceed their allocations.

4. **Refine allocations.** Update the YAML based on observed consumption
   patterns. This is the calibration step — your initial estimates were
   guesses, now you have data.

### 12.2 Phase 2: Add Cost and Token Budgets

Once latency budgets are calibrated:

5. **Add cost budgets** if your pipeline makes LLM calls. Start with generous
   allocations and `warn` policy.

6. **Add token budgets** if your pipeline constructs prompts across phases.
   Set allocations based on model context window limits.

7. **Wire pre-phase budget queries** into phase handlers that can adapt their
   behavior (e.g., reduce prompt verbosity when token budget is tight).

### 12.3 Phase 3: Enforce (`block` policy)

After calibration and refinement:

8. **Promote cost budgets to `block` policy.** Prevent runaway LLM costs by
   halting pipelines that exceed their cost ceiling.

9. **Promote token budgets to `block` policy.** Prevent context window
   overflow by halting before the model rejects the prompt.

10. **Keep latency budgets at `warn`.** Latency is the hardest to control
    (depends on model response time, network conditions, etc.). Use `warn` for
    observability, not enforcement.

### 12.4 Phase 4: Redistribute

Once allocations are well-calibrated and teams trust the budget system:

11. **Switch to `redistribute` policy** for latency budgets. If Phase 3 runs
    long, automatically reduce Phase 6 and Phase 7's allocations. This
    enables adaptive behavior without human intervention.

### 12.5 For New Pipelines

Write the budget contract alongside the pipeline definition and the propagation
contract (Layer 1). Review all three in the same PR. The three contracts
together declare:

- **What context flows where** (Layer 1 propagation contract)
- **How much resource each phase can consume** (Layer 6 budget contract)
- **What the code does** (pipeline implementation)

---

## 13. Consequences

### Positive

1. **Budget overflows become observable.** Every budget violation produces a span
   event — `budget.check.overallocated` or `budget.exhausted`. No more
   discovering cost overruns from monthly billing reports.

2. **Per-phase allocation makes budgets actionable.** Knowing that "the pipeline
   is slow" is less useful than knowing "Phase 4 (implement) consumed 25.3s of
   its 15s allocation." Per-phase allocation turns vague SLO violations into
   specific optimization targets.

3. **Pre-phase budget queries enable proactive adaptation.** Instead of
   reacting to budget overflows after the fact, phases can check remaining
   budget and adjust behavior. This is the budget equivalent of Layer 1's
   default application — the system adapts gracefully rather than failing
   silently.

4. **LLM cost control at the phase level.** For LLM-powered pipelines, cost
   tracking per phase prevents the common problem where one expensive LLM call
   dominates the run cost without visibility.

5. **Budget contracts are reviewable artifacts.** Allocations in YAML, reviewed
   in PRs, versioned in git. Changes to budget allocations are visible and
   auditable.

6. **Progressive adoption.** Fully opt-in. Start with `warn` policy and one
   budget type. Tighten incrementally as confidence grows.

### Neutral

1. **Allocations require calibration.** Initial allocations are estimates. The
   system needs 50-100 runs of observation data before allocations are
   meaningful. This is the same calibration challenge as any budgeting system.

2. **Budget state adds to context dict size.** The `_cc_budgets` key adds
   metadata to the context dict. For pipelines with many budgets and many
   phases, this can be significant. The overhead is proportional to
   `num_budgets * num_phases` entries.

3. **Multiple budget types multiply alert volume.** Three budget types with
   seven phases means up to 21 check events per run. Dashboard queries must
   filter by `budget.id` to avoid noise.

### Negative

1. **Budget allocation is an art, not a science.** Setting accurate per-phase
   allocations requires understanding the workload, model characteristics, and
   variability. Allocations that are too tight produce noise (constant
   `OVER_ALLOCATION` events). Allocations that are too generous provide no
   signal.

2. **`block` policy can halt production pipelines.** If allocations are
   miscalibrated and the `block` policy is active, legitimate pipeline runs
   will be rejected. Teams must calibrate with `warn` before promoting to
   `block`.

3. **`redistribute` policy changes downstream behavior.** Dynamic reallocation
   means downstream phases may receive less budget than their YAML declaration
   states. This can be surprising if a phase depends on a minimum allocation.
   Mitigation: phases can set a `min_allocation` floor (future work).

4. **Latency measurement includes framework overhead.** The latency budget
   tracks wall-clock time for the phase, which includes the budget check
   itself. For very short phases, the overhead may be non-trivial. Mitigation:
   subtract framework overhead from consumed time.

---

## 14. Future Work

1. **Adaptive budget allocation.** Use historical consumption data to
   automatically adjust per-phase allocations. If Phase 4 consistently uses
   20s of its 15s allocation while Phase 2 consistently uses 1s of its 2s
   allocation, the system could propose reallocation: Phase 2 → 1.5s,
   Phase 4 → 17.5s. Implementation: a `budget calibrate` CLI command that
   reads `budget.summary` events from Tempo and proposes updated YAML.

2. **Cost forecasting integration with `/cost-intelligence`.** The
   `/cost-intelligence` skill already analyzes token usage and forecasts
   spending. Budget propagation data (per-phase cost consumption) provides
   granular input for these forecasts. A pipeline that shows Phase 4 cost
   trending upward over 30 days enables proactive budget adjustment before
   the SLO is breached.

3. **Cross-pipeline budget aggregation.** Multiple pipelines share
   infrastructure resources (API rate limits, GPU allocation, total monthly
   LLM spend). A cross-pipeline budget contract would declare total resource
   budgets at the system level and track consumption across all pipeline runs.

4. **Minimum allocation floors.** For the `redistribute` policy, allow phases
   to declare a minimum allocation that redistribution cannot breach:
   ```yaml
   allocations:
     review:
       target: 1000
       min: 500  # Never reduce below 500ms
   ```

5. **Budget carryover.** For recurring pipelines (e.g., nightly builds), allow
   unused budget from one run to carry over to the next. This models error
   budget behavior from the SRE book at the pipeline level.

6. **Real-time budget dashboard.** A Grafana panel that shows budget consumption
   *during* a pipeline run (not just after), using Loki live tailing of budget
   check events. Operators could watch a pipeline run and see budget draining
   in real time.

7. **Budget anomaly detection.** Flag runs where budget consumption patterns
   deviate significantly from historical norms. A phase that normally uses 4s
   but suddenly uses 20s indicates either a workload change or a performance
   regression — distinct from a chronic over-allocation.

8. **Integration with Beaver token accounting.** The `contextcore-beaver`
   package already tracks token consumption per LLM call. Budget propagation
   should consume Beaver's token counts rather than requiring separate
   instrumentation. The integration point is `BudgetTracker.record_consumption()`
   receiving Beaver's `TokenUsage` data.

9. **OpenSLO import.** A `budget import-openslo` CLI command that reads an
   OpenSLO YAML file and generates a ContextCore budget contract with
   per-phase allocations derived from the SLO definition.

---

## Appendix A: Proposed File Inventory

| File | Purpose | Estimated Lines |
|---|---|---|
| `contracts/budget/__init__.py` | Public API exports | ~50 |
| `contracts/budget/schema.py` | Pydantic models (BudgetPropagationSpec, etc.) | ~150 |
| `contracts/budget/loader.py` | YAML parsing + validation + caching | ~80 |
| `contracts/budget/validator.py` | Budget check logic + overflow policies | ~250 |
| `contracts/budget/tracker.py` | BudgetTracker + context dict management | ~200 |
| `contracts/budget/otel.py` | OTel span event emission | ~120 |
| `contracts/types.py` (modified) | `BudgetHealth` enum, `BudgetExhaustedError` | +20 |
| `contracts/__init__.py` (modified) | Re-export new types | +10 |
| **Total (ContextCore)** | | **~880** |

Plus 2 files in startd8-sdk (budget contract YAML, orchestrator wiring) and
corresponding tests.

## Appendix B: Type Hierarchy

```
BudgetPropagationSpec
+-- schema_version: str
+-- contract_type: str = "budget_propagation"
+-- pipeline_id: str
+-- description: str?
+-- budgets: list[BudgetSpec]
    +-- BudgetSpec
        +-- budget_id: str
        +-- type: BudgetType  (latency_ms | cost_dollars | token_count | error_rate | custom)
        +-- total: float
        +-- allocations: dict[str, float]  (phase_name -> allocated amount)
        +-- overflow_policy: OverflowPolicy  (warn | block | redistribute)
        +-- description: str?
        +-- unit: str?

BudgetCheckResult
+-- budget_id: str
+-- budget_type: BudgetType
+-- phase: str
+-- health: BudgetHealth  (within_budget | over_allocation | budget_exhausted)
+-- allocated: float
+-- consumed: float
+-- remaining_total: float
+-- remaining_pct: float
+-- message: str
+-- overflow_policy: OverflowPolicy

BudgetSummaryResult
+-- budget_id: str
+-- budget_type: BudgetType
+-- total: float
+-- consumed: float
+-- remaining: float
+-- remaining_pct: float
+-- phases_within_budget: int
+-- phases_over_allocation: int
+-- overall_health: BudgetHealth
+-- per_phase: list[BudgetAllocation]

BudgetAllocation
+-- phase: str
+-- allocated: float
+-- consumed: float
+-- remaining: float

BudgetHealth (maps to ChainStatus)
+-- WITHIN_BUDGET   -> ChainStatus.INTACT
+-- OVER_ALLOCATION -> ChainStatus.DEGRADED
+-- BUDGET_EXHAUSTED -> ChainStatus.BROKEN
```

## Appendix C: Complete Contract Example (Artisan Pipeline)

```yaml
schema_version: "0.1.0"
contract_type: budget_propagation
pipeline_id: artisan
description: >
  Budget allocations for the Artisan code generation pipeline.
  Three budget types: latency (wall-clock time), tokens (LLM context window),
  and cost (LLM API spend). Latency uses warn policy (variable, hard to control).
  Tokens and cost use block policy (hard limits with real consequences).

budgets:
  - budget_id: latency_budget
    type: latency_ms
    total: 30000
    unit: ms
    allocations:
      plan: 5000
      scaffold: 2000
      design: 3000
      implement: 15000
      test: 3000
      review: 1000
      finalize: 1000
    overflow_policy: warn
    description: >
      Wall-clock time budget. Warn on overflow because latency depends on
      external factors (model response time, network). Monitor trends rather
      than enforce hard limits.

  - budget_id: token_budget
    type: token_count
    total: 50000
    unit: tokens
    allocations:
      plan: 5000
      implement: 30000
      test: 10000
      review: 5000
    overflow_policy: block
    description: >
      LLM context window budget. Block on overflow because exceeding the
      context window causes model rejection or severe quality degradation.
      Phases without LLM calls (scaffold, design, finalize) are not tracked.

  - budget_id: cost_budget
    type: cost_dollars
    total: 0.50
    unit: USD
    allocations:
      plan: 0.05
      implement: 0.30
      test: 0.10
      review: 0.05
    overflow_policy: warn
    description: >
      LLM API cost budget per pipeline run. Warn on overflow to track
      cost trends without blocking legitimate work. Promote to block
      after calibration confirms allocations are realistic.
```
