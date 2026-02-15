# Causal Ordering Contracts — Layer 4 Design

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.75
**Implementation:** Not yet implemented
**Related:**
- [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — theoretical foundation
- [Context Propagation Contracts (Layer 1)](CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) — field flow contracts and provenance tracking
- [ADR-001: Tasks as Spans](../adr/001-tasks-as-spans.md) — foundational architecture
- [A2A Contracts Design](A2A_CONTRACTS_DESIGN.md) — contract-first agent coordination
- [Weaver Cross-Repo Alignment Plan](../plans/WEAVER_CROSS_REPO_ALIGNMENT_PLAN.md) — Layer 3 (semantic conventions)

---

## 1. Problem

Systems that process events or execute pipeline phases in the wrong order
produce incorrect results — silently. Unlike a missing field (which Layer 1
catches) or a malformed schema (which Layer 2 catches), a causal ordering
violation means the *right* data arrives at the *right* destination but at the
*wrong time*. The downstream consumer processes stale, incomplete, or
inconsistent information and produces subtly worse output. No error is thrown.
No alert fires.

### Concrete Examples

**Cross-pipeline data dependency.** Pipeline A produces a training dataset.
Pipeline B trains a model on it. If B starts before A completes its latest
export, B trains on stale data. The model deploys. Predictions degrade. The
degradation is only discovered days later through offline evaluation — if
anyone runs one.

**Cross-service authentication.** Service A validates a user's identity and
emits a validation event. Service B authorizes an action based on that
validation. Under load, B receives the authorization request before A's
validation event has propagated. B either blocks (adding latency that violates
SLOs) or defaults to permissive (a security hole). Neither failure mode
produces an error log that would explain the root cause.

**Agent-to-agent context dependency.** Agent A classifies the problem domain
(web application, CLI tool, data pipeline). Agent B generates code constrained
by that classification. If B starts generation before A's classification
propagates through the shared context, B uses the default domain — `"unknown"`.
The generated code works but misses domain-specific patterns, validators, and
token budget optimizations. The WCP investigation (PI-006 through PI-013)
revealed exactly this failure mode: all 12 tasks ran with `domain: "unknown"`
because domain classification did not reach downstream phases.

**Within-phase event ordering.** A review phase processes code quality signals:
linting results, test coverage, security scan findings. If the security scan
results arrive after the review agent has already formed its assessment, the
review omits security findings. The review looks complete. The security
vulnerability ships.

### Why This Is Hard

In a single process, ordering is trivial — function calls execute sequentially,
and the call stack enforces happens-before relationships. In distributed
systems, there is no global clock, no shared memory, and no implicit ordering.

The theoretical options are:

1. **Total ordering via consensus** (Paxos, Raft). Guarantees ordering but
   requires coordination on every event, destroying throughput and latency.
2. **Eventual consistency**. Accepts that events arrive out of order and relies
   on convergent data structures (CRDTs) or application-level reconciliation.
   Works for commutative operations but fails for operations where order matters.
3. **Causal ordering via logical clocks** (Lamport, vector clocks). Tracks the
   *potential* for ordering violations without requiring consensus. Detects
   violations but does not prevent them.

Most systems choose option 2 and hope that ordering violations are rare enough
not to matter. ContextCore can do better because of its **phase-sequential
execution model**.

### ContextCore's Structural Advantage

ContextCore's pipeline architecture executes phases sequentially: plan →
scaffold → design → implement → test → review → finalize. Within a single
pipeline, this sequential execution provides total ordering *for free*. Phase N
always completes before phase N+1 starts. No consensus protocol is needed.

This means the ordering problem in ContextCore is **narrower** than in general
distributed systems:

| Scope | Ordering Guarantee | Contract Role |
|---|---|---|
| Within a pipeline, across phases | **Free** — sequential execution | Contracts *declare* what's already true (documentation + monitoring) |
| Within a phase, across events | **Partial** — depends on event sources | Contracts *detect* violations via timestamps |
| Across pipelines | **None** — independent execution | Contracts *enforce* ordering via dependency checks |
| Across services (microservices) | **None** — distributed system | Contracts *detect* violations via logical clocks |

The contract system is therefore **lighter** than a general causal ordering
solution. It leverages the sequential model where it exists, adds detection
where ordering is not guaranteed, and enforces blocking constraints only at
cross-pipeline boundaries where violations have the highest impact.

---

## 2. Solution Overview

An `OrderingConstraintSpec` contract system that declares causal dependencies
between events, phases, and pipelines. Constraints are verified at runtime
using provenance timestamps from Layer 1's `PropagationTracker` and
Lamport-style logical clocks. Violations produce OTel span events with
severity-graded responses.

```
                    YAML Contract
                  (ordering.contract.yaml)
                         │
                    ContractLoader
                     (parse + cache — reuses Layer 1)
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
       CausalValidator      CausalClock
       (check constraints)  (logical timestamps)
              │                      │
              ▼                      ▼
    OrderingCheckResult      CausalProvenance
    (satisfied/violated/     (extends FieldProvenance
     skipped, details)        with logical clock)
              │                      │
              └──────────┬───────────┘
                         ▼
               OTel Span Event Emission
               (causal.ordering.verified,
                causal.ordering.violation,
                causal.ordering.skipped)
```

### Split Placement

Following Layer 1's pattern, the framework lives in ContextCore and concrete
pipeline contracts live alongside their pipelines.

| Component | Repo | Path |
|---|---|---|
| Schema models | ContextCore | `src/contextcore/contracts/ordering/schema.py` |
| Causal validator | ContextCore | `src/contextcore/contracts/ordering/validator.py` |
| Causal clock | ContextCore | `src/contextcore/contracts/ordering/clock.py` |
| OTel emission | ContextCore | `src/contextcore/contracts/ordering/otel.py` |
| Artisan ordering contract | startd8-sdk | `src/startd8/contractors/contracts/artisan-ordering.contract.yaml` |
| Cross-pipeline contracts | Per-project | `contracts/ordering/*.contract.yaml` |

---

## 3. Contract Format

Contracts are YAML files validated against Pydantic v2 models. All models use
`extra="forbid"` to reject unknown keys at parse time, consistent with Layer 1.

### 3.1 Top-Level Structure

```yaml
schema_version: "0.1.0"        # SemVer, starts at 0.1.0 per Weaver convention
contract_type: causal_ordering
pipeline_id: artisan            # Which pipeline this governs
description: >
  Causal ordering constraints for the Artisan code generation pipeline.
  Most within-pipeline ordering is enforced by sequential execution;
  these contracts declare those invariants for monitoring and document
  cross-pipeline dependencies where ordering must be explicitly checked.

constraints:                    # Within-pipeline causal constraints
  - constraint_id: domain_before_generation
    description: "Domain classification must complete before code generation starts"
    before:
      phase: plan
      event: domain_classified
    after:
      phase: implement
      event: generation_started
    severity: blocking

  - constraint_id: tests_before_review
    description: "Test results must be available before review begins"
    before:
      phase: test
      event: tests_completed
    after:
      phase: review
      event: review_started
    severity: warning

  - constraint_id: design_before_implementation
    description: "Design decisions must be finalized before code generation"
    before:
      phase: design
      event: design_finalized
    after:
      phase: implement
      event: generation_started
    severity: blocking

cross_pipeline:                 # Cross-pipeline causal constraints
  - constraint_id: training_data_ready
    description: "Training dataset must be published before model training starts"
    before:
      pipeline: data_pipeline
      phase: export
      event: dataset_published
    after:
      pipeline: ml_pipeline
      phase: train
      event: training_started
    severity: blocking
    timeout_ms: 300000          # Max 5 minutes to wait for dependency

  - constraint_id: schema_validated_before_ingestion
    description: "Schema validation pipeline must approve schema before data ingestion starts"
    before:
      pipeline: schema_validation
      phase: validate
      event: schema_approved
    after:
      pipeline: data_ingestion
      phase: ingest
      event: ingestion_started
    severity: blocking
    timeout_ms: 60000
```

### 3.2 Constraint Specifications

Each constraint is a `CausalDependency`:

| Property | Type | Required | Description |
|---|---|---|---|
| `constraint_id` | str | Yes | Unique identifier (used in OTel events, dashboards) |
| `description` | str | No | Human-readable explanation of why this ordering matters |
| `before` | `CausalEndpoint` | Yes | Event that must happen first |
| `after` | `CausalEndpoint` | Yes | Event that must happen second |
| `severity` | enum | No | `blocking` / `warning` / `advisory`. Default: `warning` |
| `timeout_ms` | int | No | For cross-pipeline: max wait time for `before` event. Default: `None` (no timeout) |

### 3.3 Endpoint Specifications

Each endpoint is a `CausalEndpoint`:

| Property | Type | Required | Description |
|---|---|---|---|
| `pipeline` | str | No | Pipeline identifier (required for `cross_pipeline` constraints) |
| `phase` | str | Yes | Phase name (e.g. `"plan"`, `"implement"`) |
| `event` | str | Yes | Event name (e.g. `"domain_classified"`, `"generation_started"`) |

For within-pipeline constraints, the `pipeline` field is omitted and inherited
from the top-level `pipeline_id`. For cross-pipeline constraints, `pipeline`
is required on both `before` and `after` endpoints.

### 3.4 Severity Behavior

| Severity | On Violation | Response | Log Level |
|---|---|---|---|
| `BLOCKING` | Constraint violated | Halt execution, emit error event | ERROR |
| `WARNING` | Constraint violated | Continue execution, emit warning event | WARNING |
| `ADVISORY` | Constraint violated | Continue execution, emit info event | INFO |

For within-pipeline constraints with `BLOCKING` severity, a violation indicates
a regression in the pipeline's sequential execution model — something that
*should* be impossible has happened. These are treated as bugs in the pipeline
orchestrator.

For cross-pipeline constraints with `BLOCKING` severity, a violation means the
dependent pipeline should not proceed. The validator returns a blocking result
that the orchestrator must respect.

---

## 4. Causal Verification

### 4.1 Within-Pipeline Verification

ContextCore's sequential execution model means that within-pipeline ordering
constraints are **inherently satisfied** by the pipeline orchestrator. If
phase N always completes before phase N+1 starts, then any event in phase N
happens-before any event in phase N+1.

The contract system's role for within-pipeline constraints is therefore
**monitoring, not enforcement**:

```
Phase Execution:  plan ──→ scaffold ──→ design ──→ implement ──→ test ──→ review ──→ finalize
                   │                      │           │
                   │ domain_classified     │           │ generation_started
                   │                      │           │
                   └──── Sequential ──────┘───────────┘
                         execution guarantees
                         happens-before
```

The validator confirms that the sequential model is holding:

```python
def verify_within_pipeline(
    constraint: CausalDependency,
    phase_timestamps: dict[str, PhaseTimestamp],
) -> OrderingCheckResult:
    before_ts = phase_timestamps.get(constraint.before.phase)
    after_ts = phase_timestamps.get(constraint.after.phase)

    if before_ts is None:
        return OrderingCheckResult(
            constraint_id=constraint.constraint_id,
            status=OrderingStatus.SKIPPED,
            message=f"Before phase '{constraint.before.phase}' has no timestamp",
        )

    if after_ts is None:
        return OrderingCheckResult(
            constraint_id=constraint.constraint_id,
            status=OrderingStatus.SKIPPED,
            message=f"After phase '{constraint.after.phase}' has not executed yet",
        )

    if before_ts.completed_at <= after_ts.started_at:
        return OrderingCheckResult(
            constraint_id=constraint.constraint_id,
            status=OrderingStatus.SATISFIED,
            before_timestamp=before_ts.completed_at,
            after_timestamp=after_ts.started_at,
            message="Sequential execution maintained ordering",
        )
    else:
        return OrderingCheckResult(
            constraint_id=constraint.constraint_id,
            status=OrderingStatus.VIOLATED,
            before_timestamp=before_ts.completed_at,
            after_timestamp=after_ts.started_at,
            message=(
                f"Ordering violation: '{constraint.before.phase}' completed at "
                f"{before_ts.completed_at} but '{constraint.after.phase}' started at "
                f"{after_ts.started_at}"
            ),
        )
```

A within-pipeline violation means the pipeline orchestrator is broken. This is
a P1 bug, not a constraint tuning issue.

### 4.2 Cross-Pipeline Verification

Cross-pipeline constraints are where the contract system provides real value.
Two independent pipelines have no implicit ordering. The validator uses
provenance timestamps from Layer 1's `_cc_propagation` metadata to check
ordering.

```python
def verify_cross_pipeline(
    constraint: CausalDependency,
    provenance_store: ProvenanceStore,
) -> OrderingCheckResult:
    # Look up the "before" event's provenance
    before_prov = provenance_store.get_event_provenance(
        pipeline=constraint.before.pipeline,
        phase=constraint.before.phase,
        event=constraint.before.event,
    )

    # Look up the "after" event's provenance
    after_prov = provenance_store.get_event_provenance(
        pipeline=constraint.after.pipeline,
        phase=constraint.after.phase,
        event=constraint.after.event,
    )

    if before_prov is None:
        return OrderingCheckResult(
            constraint_id=constraint.constraint_id,
            status=OrderingStatus.VIOLATED,
            message=(
                f"Before event '{constraint.before.event}' in pipeline "
                f"'{constraint.before.pipeline}' has no provenance record — "
                f"dependency may not have executed"
            ),
            severity=constraint.severity,
        )

    if after_prov is None:
        return OrderingCheckResult(
            constraint_id=constraint.constraint_id,
            status=OrderingStatus.SKIPPED,
            message=f"After event has not occurred yet",
        )

    # Compare timestamps
    if before_prov.set_at <= after_prov.set_at:
        return OrderingCheckResult(
            constraint_id=constraint.constraint_id,
            status=OrderingStatus.SATISFIED,
            before_timestamp=before_prov.set_at,
            after_timestamp=after_prov.set_at,
            logical_clock_before=before_prov.logical_clock,
            logical_clock_after=after_prov.logical_clock,
        )
    else:
        return OrderingCheckResult(
            constraint_id=constraint.constraint_id,
            status=OrderingStatus.VIOLATED,
            before_timestamp=before_prov.set_at,
            after_timestamp=after_prov.set_at,
            logical_clock_before=before_prov.logical_clock,
            logical_clock_after=after_prov.logical_clock,
            message=(
                f"Causal ordering violated: '{constraint.before.event}' "
                f"(clock={before_prov.logical_clock}) occurred after "
                f"'{constraint.after.event}' (clock={after_prov.logical_clock})"
            ),
            severity=constraint.severity,
        )
```

### 4.3 Timeout Handling for Cross-Pipeline Constraints

Cross-pipeline `BLOCKING` constraints with a `timeout_ms` field define a
maximum wait time. If the `before` event has not occurred when the `after`
pipeline is ready to proceed:

1. The validator returns `PENDING` status
2. The orchestrator polls or subscribes for the event
3. If the event arrives within `timeout_ms`, the constraint is `SATISFIED`
4. If the timeout expires, the constraint is `VIOLATED` with a timeout
   explanation

```python
@dataclass
class OrderingCheckResult:
    constraint_id: str
    status: OrderingStatus  # SATISFIED | VIOLATED | SKIPPED | PENDING
    message: str = ""
    before_timestamp: str | None = None
    after_timestamp: str | None = None
    logical_clock_before: int | None = None
    logical_clock_after: int | None = None
    severity: ConstraintSeverity = ConstraintSeverity.WARNING
    timeout_exceeded: bool = False
    waited_ms: int | None = None
```

---

## 5. Logical Clock Design

### 5.1 Why Lamport Clocks, Not Vector Clocks

**Lamport clocks** assign a single incrementing integer to each event. They
guarantee that if event A causally precedes event B, then
`clock(A) < clock(B)`. However, the converse is not true — a lower clock
value does not prove causality.

**Vector clocks** assign a vector of integers (one per process) to each event.
They provide exact causality detection: `A → B` if and only if
`vector(A) < vector(B)`. However, vector clocks grow linearly with the number
of processes and require every message to carry the full vector.

For ContextCore, Lamport clocks are sufficient because:

1. **Within-pipeline ordering is already guaranteed.** The sequential execution
   model provides a total order. Lamport clocks only need to confirm it.
2. **Cross-pipeline interactions are few.** Most pipelines are independent. The
   handful of cross-pipeline dependencies are explicitly declared in contracts
   and can be verified with timestamps + logical clocks.
3. **Vector clock overhead is unjustified.** ContextCore pipelines are not
   general message-passing processes. They are sequential phases with
   well-defined interfaces. The O(N) overhead of vector clocks (where N is the
   number of pipelines) adds complexity without proportional benefit.
4. **False positives are acceptable.** If a Lamport clock comparison says "A
   might have happened before B" when it didn't, the worst case is a
   `SATISFIED` result that should have been `SKIPPED`. This is safe — it means
   the contract system might miss a violation, but it won't create false
   violations. And the wall-clock timestamp comparison catches most real
   violations regardless.

If ContextCore later needs to track causality across a large number of
interacting pipelines, vector clocks can be added as an opt-in upgrade (see
Section 12, Future Work).

### 5.2 CausalProvenance Model

Extend Layer 1's `FieldProvenance` with a logical clock component:

```python
@dataclass
class CausalProvenance(FieldProvenance):
    """FieldProvenance extended with causal ordering metadata.

    Inherits from FieldProvenance:
        origin_phase: str       # Phase that set this field
        set_at: str             # ISO 8601 timestamp
        value_hash: str         # sha256(repr(value))[:8]

    Adds:
        logical_clock: int      # Lamport timestamp
        causal_dependencies: list[str]  # field_paths this depends on
    """
    logical_clock: int = 0
    causal_dependencies: list[str] = field(default_factory=list)
```

The `logical_clock` is incremented by the `CausalClock` at each event.
`causal_dependencies` records which other field provenance records this event
depends on, enabling reconstruction of the causal graph.

### 5.3 CausalClock Implementation

```python
class CausalClock:
    """Lamport-style logical clock for causal ordering.

    Usage:
        clock = CausalClock()

        # Local event
        t1 = clock.tick()  # Returns 1

        # Receiving a message with sender's clock
        t2 = clock.receive(sender_clock=5)  # Returns max(local, 5) + 1 = 6

        # Stamp provenance with current clock
        prov = clock.stamp_provenance(
            field_path="domain_summary.domain",
            origin_phase="plan",
            value=domain_value,
            dependencies=["project_root"],
        )
    """

    def __init__(self, initial: int = 0):
        self._counter = initial

    def tick(self) -> int:
        """Increment clock for a local event. Returns new clock value."""
        self._counter += 1
        return self._counter

    def receive(self, sender_clock: int) -> int:
        """Update clock on receiving a message. Returns new clock value.

        Lamport rule: local = max(local, sender) + 1
        """
        self._counter = max(self._counter, sender_clock) + 1
        return self._counter

    @property
    def current(self) -> int:
        """Current clock value without incrementing."""
        return self._counter

    def stamp_provenance(
        self,
        field_path: str,
        origin_phase: str,
        value: Any,
        dependencies: list[str] | None = None,
    ) -> CausalProvenance:
        """Create a CausalProvenance record with the current clock value.

        Increments the clock (this is a local event) and returns a
        provenance record with the new timestamp.
        """
        clock_value = self.tick()
        value_hash = hashlib.sha256(repr(value).encode()).hexdigest()[:8]

        return CausalProvenance(
            origin_phase=origin_phase,
            set_at=datetime.now(timezone.utc).isoformat(),
            value_hash=value_hash,
            logical_clock=clock_value,
            causal_dependencies=dependencies or [],
        )
```

### 5.4 Clock Propagation Rules

1. **Phase start.** When a phase begins, the pipeline orchestrator calls
   `clock.tick()`. The resulting clock value is stamped on the phase's start
   provenance.

2. **Phase end.** When a phase completes, the orchestrator calls `clock.tick()`
   again. All exit provenance records receive this clock value.

3. **Cross-pipeline handoff.** When pipeline B depends on pipeline A's output,
   pipeline B's orchestrator calls `clock.receive(A's_final_clock)` before
   starting its dependent phase. This ensures B's clock is strictly greater
   than A's, establishing the happens-before relationship.

4. **Provenance storage.** The `logical_clock` value is stored alongside
   existing `FieldProvenance` data in the context dict's `_cc_propagation`
   metadata:

```python
context = {
    "domain_summary": {"domain": "web_application"},
    "_cc_propagation": {
        "domain_summary.domain": CausalProvenance(
            origin_phase="plan",
            set_at="2026-02-15T10:30:00+00:00",
            value_hash="a1b2c3d4",
            logical_clock=3,
            causal_dependencies=["project_root"],
        ),
    },
}
```

---

## 6. OTel Event Semantics

All events follow ContextCore telemetry conventions and are emitted as OTel
span events on the current active span. If OTel is not installed, events are
logged only (no crash). This follows the same `_HAS_OTEL` guard pattern used
in Layer 1.

### 6.1 Ordering Events

**Event name: `causal.ordering.verified`** — constraint satisfied

Emitted when a causal ordering constraint is checked and the happens-before
relationship holds.

| Attribute | Type | Description |
|---|---|---|
| `causal.constraint_id` | str | Constraint identifier (e.g. `"domain_before_generation"`) |
| `causal.status` | str | `"satisfied"` |
| `causal.before_phase` | str | Phase of the "before" event |
| `causal.before_event` | str | Event name of the "before" event |
| `causal.after_phase` | str | Phase of the "after" event |
| `causal.after_event` | str | Event name of the "after" event |
| `causal.before_clock` | int | Lamport timestamp of the "before" event |
| `causal.after_clock` | int | Lamport timestamp of the "after" event |
| `causal.severity` | str | Constraint severity (`blocking` / `warning` / `advisory`) |

**Event name: `causal.ordering.violation`** — constraint violated

Emitted when a causal ordering constraint is checked and the happens-before
relationship does not hold.

| Attribute | Type | Description |
|---|---|---|
| `causal.constraint_id` | str | Constraint identifier |
| `causal.status` | str | `"violated"` |
| `causal.before_phase` | str | Phase of the "before" event |
| `causal.before_event` | str | Event name of the "before" event |
| `causal.after_phase` | str | Phase of the "after" event |
| `causal.after_event` | str | Event name of the "after" event |
| `causal.before_clock` | int | Lamport timestamp (or -1 if missing) |
| `causal.after_clock` | int | Lamport timestamp |
| `causal.before_timestamp` | str | ISO 8601 wall-clock timestamp of "before" event |
| `causal.after_timestamp` | str | ISO 8601 wall-clock timestamp of "after" event |
| `causal.severity` | str | Constraint severity |
| `causal.timeout_exceeded` | bool | Whether a cross-pipeline timeout was exceeded |
| `causal.waited_ms` | int | Milliseconds waited before timeout (if applicable) |
| `causal.message` | str | Human-readable explanation of the violation |

**Event name: `causal.ordering.skipped`** — constraint check could not be
performed

Emitted when a causal ordering constraint cannot be verified because one or
both events have no provenance record.

| Attribute | Type | Description |
|---|---|---|
| `causal.constraint_id` | str | Constraint identifier |
| `causal.status` | str | `"skipped"` |
| `causal.reason` | str | Why the check was skipped (e.g. `"before event has no timestamp"`) |
| `causal.severity` | str | Constraint severity |

### 6.2 Summary Event

**Event name: `causal.ordering.summary`**

Emitted once per pipeline run (typically at finalize), aggregating all
constraint check results.

| Attribute | Type | Description |
|---|---|---|
| `causal.total_constraints` | int | Total number of constraints checked |
| `causal.satisfied` | int | Count of SATISFIED constraints |
| `causal.violated` | int | Count of VIOLATED constraints |
| `causal.skipped` | int | Count of SKIPPED constraints |
| `causal.satisfaction_pct` | float | `satisfied / (total - skipped) * 100` |
| `causal.has_blocking_violations` | bool | Whether any BLOCKING constraint was violated |

### 6.3 TraceQL Queries

```traceql
# Find any ordering violations
{ name = "causal.ordering.violation" }

# Find blocking violations (pipeline should have halted)
{ name = "causal.ordering.violation" && span.causal.severity = "blocking" }

# Find cross-pipeline timeout violations
{ name = "causal.ordering.violation" && span.causal.timeout_exceeded = true }

# Find runs with less than 100% constraint satisfaction
{ name = "causal.ordering.summary" && span.causal.satisfaction_pct < 100 }

# Find specific constraint violations
{ name = "causal.ordering.violation" && span.causal.constraint_id = "training_data_ready" }
```

---

## 7. Relationship to Layers 1–3

### Layer 1: Context Propagation — Foundation

Layer 4 depends directly on Layer 1's infrastructure:

| Layer 1 Component | Layer 4 Usage |
|---|---|
| `FieldProvenance` | Extended by `CausalProvenance` with logical clock |
| `PropagationTracker.stamp()` | Provenance timestamps used for ordering verification |
| `_cc_propagation` metadata | Storage location for `CausalProvenance` records |
| `ContractLoader` | Reused for parsing ordering contract YAML |
| `ConstraintSeverity` enum | Reused for constraint severity (not duplicated) |
| `emit_*_result()` pattern | Followed for OTel emission helpers |

The key reuse is **provenance timestamps**. Layer 1 stamps `set_at` timestamps
on every field provenance record. Layer 4 reads those timestamps to verify
ordering constraints. No new data collection is required — Layer 4 adds
*interpretation* of data that Layer 1 already collects.

### Layer 2: Schema Compatibility — Orthogonal

Layer 2 validates that the *shape* of data is correct across service
boundaries. Layer 4 validates that data arrives in the *right order*. The two
are orthogonal: data can arrive in order but with the wrong schema (Layer 2
violation), or in the wrong order but with the correct schema (Layer 4
violation).

However, they compose: a cross-pipeline constraint can declare both "pipeline
A's output must arrive before pipeline B starts" (Layer 4) and "pipeline A's
output must conform to pipeline B's expected schema" (Layer 2). A single YAML
contract can reference both constraint types.

### Layer 3: Semantic Conventions — Naming

Layer 3 ensures that attribute names are consistent. Layer 4 introduces new
attribute names (`causal.*`) that must be registered in the semantic convention
registry. The `causal.constraint_id`, `causal.status`, `causal.severity`
attributes follow the naming patterns established by Layer 1's `context.*`
attributes and must be validated by Layer 3's convention enforcement.

---

## 8. Relationship to Distributed Systems Theory

### 8.1 Lamport's Happens-Before Relation

Lamport (1978) defined the **happens-before** relation (→) for distributed
systems:

1. If A and B are events in the same process, and A comes before B, then A → B
2. If A is the sending of a message and B is the receipt of that message, then A → B
3. If A → B and B → C, then A → C (transitivity)

Two events are **concurrent** if neither happens-before the other.

In ContextCore's phase-sequential model, rule 1 provides ordering within a
pipeline (phases are events in the same "process"). Rule 2 applies to
cross-pipeline dependencies where one pipeline's output is another's input.
Rule 3 gives transitive ordering through chains.

ContextCore's `CausalDependency` contract is a formal statement of the
happens-before relation: "event `before` → event `after`". The `CausalValidator`
checks whether the relation holds using timestamps and logical clocks.

### 8.2 Lamport Clocks

A Lamport clock assigns an integer timestamp to each event such that if A → B,
then `C(A) < C(B)`. ContextCore's `CausalClock` implements this:

- `tick()` increments the counter (rule 1: local event ordering)
- `receive(sender_clock)` sets `counter = max(counter, sender_clock) + 1`
  (rule 2: message receipt ordering)

The limitation: `C(A) < C(B)` does not imply A → B. Two concurrent events can
have comparable clock values. For ContextCore, this is acceptable because:

- Within-pipeline ordering is already guaranteed by sequential execution
- Cross-pipeline ordering is explicitly declared in contracts
- The clock values supplement wall-clock timestamps, not replace them

### 8.3 Vector Clocks

Vector clocks (Fidge, 1988; Mattern, 1989) provide exact causality detection:
`VC(A) < VC(B)` if and only if A → B. Each process maintains a vector of
counters, one per process. Message exchange propagates the full vector.

For ContextCore, vector clocks would provide:

- **Exact concurrency detection**: Distinguish "A happened before B" from
  "A and B are concurrent"
- **Causal history**: The vector encodes the full causal past of an event

The cost is O(N) space per event (where N is the number of pipelines) and
O(N) comparison time. For a system with 3–5 pipelines, this is negligible.
For a system with hundreds of microservices, it becomes significant.

ContextCore defers vector clocks to future work because the current use case
(a handful of interacting pipelines) does not justify the complexity. See
Section 12.

### 8.4 Session Types

Session types (Honda, Yoshida, Carbone, 2008) provide **compile-time**
guarantees for message-passing protocols. A session type declares the sequence
of message types exchanged between processes:

```
S = !Request.?Response.end
T = ?Request.!Response.end
```

Process S sends a Request, then receives a Response. Process T does the dual.
The type system guarantees that if both processes type-check, they will never
deadlock or receive an unexpected message type.

ContextCore's ordering contracts are a **runtime approximation** of session
types. Where session types prove ordering at compile time, ContextCore checks
ordering at each phase boundary. Where session types cover all possible
execution paths, ContextCore checks the single path that actually executed.

The gap between the two is the difference between **verification** (proving a
property holds for all executions) and **monitoring** (checking a property held
for one execution). ContextCore occupies the monitoring end of this spectrum,
which is appropriate for a system where pipelines are defined dynamically
(YAML contracts, not compiled type systems).

### 8.5 Why Total Ordering Is Overkill

Total ordering (every event has a unique, globally agreed-upon position in a
sequence) requires consensus protocols like Paxos or Raft. These add latency
(at least one round-trip per event) and complexity (leader election, log
replication).

ContextCore does not need total ordering because:

1. Within-pipeline ordering is provided by sequential execution (no consensus
   needed)
2. Cross-pipeline ordering only matters for explicitly declared dependencies
   (most pipelines are independent)
3. The system tolerates eventual detection of violations (it does not need to
   prevent them in real time)

Causal ordering (Lamport clocks) provides the right level of ordering
guarantee: strong enough to detect violations, cheap enough to not impact
performance.

---

## 9. Dashboard Integration

### 9.1 Recommended Panels

**Causal Constraint Satisfaction Rate (Stat panel)**
```traceql
{ name = "causal.ordering.summary" }
| select(span.causal.satisfaction_pct)
```

**Ordering Violations Over Time (Time series)**
```traceql
{ name = "causal.ordering.violation" }
| rate()
```

**Violation Details (Table)**
```traceql
{ name = "causal.ordering.violation" }
| select(
    span.causal.constraint_id,
    span.causal.before_phase,
    span.causal.after_phase,
    span.causal.severity,
    span.causal.message
  )
```

**Cross-Pipeline Timeout Violations (Table)**
```traceql
{ name = "causal.ordering.violation" && span.causal.timeout_exceeded = true }
| select(
    span.causal.constraint_id,
    span.causal.waited_ms,
    span.causal.message
  )
```

**Constraint Health by Pipeline Run (Table)**
```traceql
{ name = "causal.ordering.summary" }
| select(
    span.causal.total_constraints,
    span.causal.satisfied,
    span.causal.violated,
    span.causal.skipped,
    span.causal.satisfaction_pct,
    span.causal.has_blocking_violations
  )
```

### 9.2 Alerting Rules

**Alert: Blocking causal ordering violation**
```yaml
- alert: CausalOrderingBlockingViolation
  expr: |
    count_over_time(
      {job="artisan"} | json | event="causal.ordering.violation"
        | severity="blocking" [5m]
    ) > 0
  for: 0m
  labels:
    severity: critical
  annotations:
    summary: "A blocking causal ordering constraint was violated"
    description: >
      A happens-before dependency was not satisfied. This indicates either
      a pipeline orchestration bug (within-pipeline) or a missing dependency
      check (cross-pipeline).
```

**Alert: Cross-pipeline timeout exceeded**
```yaml
- alert: CausalOrderingTimeout
  expr: |
    count_over_time(
      {job="artisan"} | json | event="causal.ordering.violation"
        | timeout_exceeded="true" [15m]
    ) > 0
  for: 0m
  labels:
    severity: warning
  annotations:
    summary: "A cross-pipeline dependency timed out"
    description: >
      A pipeline waited for a dependency from another pipeline and the
      dependency did not arrive within the configured timeout.
```

**Alert: Satisfaction rate drop**
```yaml
- alert: CausalSatisfactionDegraded
  expr: |
    sum(rate(
      {job="artisan"} | json | event="causal.ordering.summary"
        | satisfaction_pct < 100 [15m]
    )) > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Causal ordering satisfaction rate is below 100%"
```

---

## 10. Adoption Path

### 10.1 For Existing Pipelines (Phase 1 — Declaration)

1. **Start with within-pipeline contracts only.** Write a YAML contract that
   declares the ordering constraints that the sequential execution model
   already guarantees. This costs nothing — you are documenting invariants that
   are already true.

2. **Enable validation.** Wire the `CausalValidator` into your pipeline
   orchestrator. All within-pipeline constraints should be `SATISFIED` because
   sequential execution enforces them. If any are `VIOLATED`, you have found
   a bug in your orchestrator.

3. **Monitor.** Build a dashboard panel for `causal.ordering.summary` events.
   The `satisfaction_pct` should be 100% for within-pipeline constraints. A
   deviation is a regression.

This is pure documentation value: machine-readable, machine-verifiable
documentation of ordering invariants that humans previously held in their
heads.

### 10.2 Cross-Pipeline Contracts (Phase 2 — Enforcement)

4. **Identify cross-pipeline dependencies.** Most pipelines are independent.
   For the few that have ordering dependencies, write `cross_pipeline`
   constraints.

5. **Start with `WARNING` severity.** Cross-pipeline constraints begin as
   warnings — they emit signals when violated but don't block execution. This
   lets you measure the violation rate before deciding which constraints
   deserve `BLOCKING` severity.

6. **Promote to `BLOCKING` with timeouts.** For constraints where violations
   cause real damage (stale training data, unauthorized access), promote to
   `BLOCKING` with a `timeout_ms`. The orchestrator will wait for the
   dependency up to the timeout before proceeding.

### 10.3 Logical Clock Integration (Phase 3 — Precision)

7. **Enable `CausalClock`.** Pass a `CausalClock` instance to the pipeline
   orchestrator. Clock values are stamped on provenance records automatically.

8. **Enable cross-pipeline clock propagation.** When pipeline B depends on
   pipeline A, propagate A's final clock value to B's `CausalClock.receive()`.
   This establishes the happens-before relationship in the logical clock space.

9. **Dashboard upgrade.** Add clock-based panels that show logical clock
   progression and gaps, supplementing the wall-clock timestamp panels from
   Phase 1.

### 10.4 Effort Estimate

| Phase | Effort | Risk | Benefit |
|---|---|---|---|
| Phase 1: Within-pipeline declaration | 1-2 days | Very low (documenting existing invariants) | Machine-verifiable ordering documentation |
| Phase 2: Cross-pipeline enforcement | 3-5 days | Medium (cross-pipeline coordination) | Prevent stale-data and race condition failures |
| Phase 3: Logical clock integration | 2-3 days | Low (additive, non-breaking) | Precise causality tracking, forensic capability |

---

## 11. Consequences

### Positive

1. **Cross-pipeline ordering violations become detectable.** Without contracts,
   a pipeline consuming stale data from another pipeline produces no signal.
   With contracts, the `VIOLATED` status fires immediately.

2. **Within-pipeline ordering invariants are machine-documented.** The
   sequential execution model provides ordering guarantees, but those
   guarantees exist only in the orchestrator's code. Contracts make them
   explicit, reviewable, and verifiable.

3. **Lightweight for ContextCore's use case.** Because the phase-sequential
   model handles most ordering, the contract system does not need consensus
   protocols, vector clocks, or other heavy distributed systems machinery.
   Lamport clocks and wall-clock timestamps are sufficient.

4. **Composable with Layers 1–3.** Reuses `FieldProvenance`, `ContractLoader`,
   `ConstraintSeverity`, and the OTel emission pattern. No new framework — just
   new contract types plugged into the existing infrastructure.

5. **Progressive adoption.** Within-pipeline contracts are documentation with
   verification. Cross-pipeline contracts can start as warnings. Logical clocks
   are opt-in. Each phase adds value without requiring the next.

### Neutral

1. **Within-pipeline contracts are mostly monitoring.** Because sequential
   execution already guarantees ordering, within-pipeline contracts confirm
   what's already true rather than preventing violations. The value is in
   regression detection and documentation, not enforcement.

2. **Logical clocks add metadata to context dicts.** The `CausalProvenance`
   records are larger than `FieldProvenance` records (extra `logical_clock`
   and `causal_dependencies` fields). For pipelines with many fields, this
   increases the context dict size. The overhead is small (two fields per
   provenance record) but non-zero.

### Negative

1. **Cross-pipeline verification requires a shared provenance store.** Two
   independent pipelines must be able to query each other's provenance records.
   This requires either a shared database (e.g., Tempo — provenance records are
   already emitted as span events) or a message-passing mechanism. The design
   assumes Tempo as the shared store, which couples Layer 4 to the
   observability backend.

2. **Timeout-based blocking adds latency.** Cross-pipeline `BLOCKING`
   constraints with `timeout_ms` cause the dependent pipeline to wait. If the
   dependency is slow, the wait time is added directly to the pipeline's
   execution time. This is an explicit tradeoff: correctness (waiting for the
   dependency) vs. performance (proceeding without it).

3. **Clock synchronization across pipelines is imperfect.** Lamport clocks
   provide causal ordering but not exact timing. If two pipelines run on
   different machines with clock skew, wall-clock timestamp comparisons can
   produce false positives or false negatives. The logical clock mitigates this
   but does not eliminate it for pipelines that do not exchange messages (and
   thus cannot call `clock.receive()`).

---

## 12. Future Work

1. **Vector clocks for full causality tracking.** If ContextCore grows to
   coordinate many interacting pipelines (10+), Lamport clocks may produce too
   many ambiguous comparisons. Vector clocks would provide exact causality
   detection at the cost of O(N) space per event. Implementation would extend
   `CausalProvenance` with a `vector_clock: dict[str, int]` field and add
   vector comparison logic to `CausalValidator`.

2. **Integration with event sourcing systems.** Event sourcing architectures
   (EventStore, Kafka with event ordering) maintain their own ordering
   guarantees. Layer 4 contracts could declare ordering constraints against
   event store sequence numbers, bridging ContextCore's pipeline model with
   event-sourced architectures.

3. **Causal graph visualization.** Build a Grafana panel (or extend the
   contextcore-owl plugin) that renders the causal dependency graph across
   pipelines. Nodes are events, edges are happens-before relationships, and
   red edges indicate violations. This would provide at-a-glance understanding
   of cross-pipeline ordering health.

4. **Static analysis of ordering contracts.** At `contextcore manifest
   validate` time, analyze the dependency graph for cycles (deadlocks: A
   depends on B, B depends on A) and unreachable constraints (constraint
   references a phase or event that doesn't exist). This would catch
   configuration errors before runtime.

5. **Session type generation.** Generate session type specifications from
   ordering contracts for pipelines that interact frequently. This would bridge
   the gap between runtime monitoring (Layer 4) and compile-time verification
   (session types), enabling formal verification of pipeline interaction
   protocols.

6. **Adaptive timeout tuning.** Use historical provenance timestamps to
   automatically adjust `timeout_ms` values. If a cross-pipeline dependency
   consistently completes in 200ms, the timeout could be auto-tightened from
   5000ms to 500ms (with a safety margin), providing faster violation detection.

---

## Appendix A: Planned File Inventory

| File | Estimated Lines | Purpose |
|---|---|---|
| `contracts/ordering/__init__.py` | ~40 | Public API exports |
| `contracts/ordering/schema.py` | ~120 | Pydantic models: `CausalDependency`, `CausalEndpoint`, `OrderingConstraintSpec` |
| `contracts/ordering/validator.py` | ~200 | `CausalValidator`: within-pipeline and cross-pipeline verification |
| `contracts/ordering/clock.py` | ~80 | `CausalClock`: Lamport clock implementation |
| `contracts/ordering/otel.py` | ~120 | OTel span event emission helpers |
| `contracts/types.py` (modified) | +15 | `OrderingStatus` enum, `CausalProvenance` dataclass |
| `contracts/__init__.py` (modified) | +5 | Re-exports for ordering module |
| **Total (estimated)** | **~580** | — |

## Appendix B: Type Hierarchy

```
OrderingConstraintSpec
├── schema_version: str
├── contract_type: Literal["causal_ordering"]
├── pipeline_id: str
├── description: str?
├── constraints: list[CausalDependency]
│   └── CausalDependency
│       ├── constraint_id: str
│       ├── description: str?
│       ├── before: CausalEndpoint
│       │   ├── pipeline: str?
│       │   ├── phase: str
│       │   └── event: str
│       ├── after: CausalEndpoint
│       │   ├── pipeline: str?
│       │   ├── phase: str
│       │   └── event: str
│       ├── severity: ConstraintSeverity  (blocking | warning | advisory)
│       └── timeout_ms: int?
└── cross_pipeline: list[CausalDependency]

CausalProvenance (extends FieldProvenance)
├── origin_phase: str          (inherited)
├── set_at: str                (inherited, ISO 8601)
├── value_hash: str            (inherited, sha256[:8])
├── logical_clock: int         (Lamport timestamp)
└── causal_dependencies: list[str]  (field_paths this depends on)

OrderingCheckResult
├── constraint_id: str
├── status: OrderingStatus     (SATISFIED | VIOLATED | SKIPPED | PENDING)
├── message: str
├── before_timestamp: str?
├── after_timestamp: str?
├── logical_clock_before: int?
├── logical_clock_after: int?
├── severity: ConstraintSeverity
├── timeout_exceeded: bool
└── waited_ms: int?

OrderingStatus (enum)
├── SATISFIED    — happens-before relationship holds
├── VIOLATED     — happens-before relationship does not hold
├── SKIPPED      — cannot verify (missing timestamps/provenance)
└── PENDING      — waiting for dependency (cross-pipeline with timeout)
```
