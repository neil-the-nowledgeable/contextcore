# Error Context Enrichment Contracts — Cross-Cutting Concern Design

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.82
**Implementation:** Not yet implemented
**Related:**
- [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — theoretical foundation (Concern 8)
- [Context Propagation Contracts — Layer 1](CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) — provenance primitives
- [ADR-001: Tasks as Spans](../adr/001-tasks-as-spans.md) — foundational architecture
- [A2A Contracts Design](A2A_CONTRACTS_DESIGN.md) — contract-first agent coordination
- [Semantic Conventions](../semantic-conventions.md) — attribute naming standards

---

## 1. Problem

When an error occurs in a multi-phase pipeline or distributed system, the error
message describes what happened at the point of failure. It does not describe
*why* the failure occurred — which is almost always a decision made upstream, in
a different phase, by a different service, at a different time.

This is the distributed systems analog of debugging a segfault by staring at the
crashing instruction without seeing the allocation that caused the corruption
ten thousand instructions earlier. In a single process, debuggers and exception
chaining (`__cause__` in Python, `getCause()` in Java) reconstruct the causal
chain. In distributed systems, that chain is scattered across services, each of
which caught the exception, logged it locally, and re-threw a sanitized version.
By the time a human sees the error, the causal narrative is gone.

### Concrete Failures

**Failure 1: Domain classification silently defaulted.**

Phase 5 (test) fails with `AssertionError: expected domain-specific test`. The
test phase expected domain-specific validators — validators selected based on
the domain classification performed in phase 1 (plan). But the domain
classification returned `"unknown"`, and this default value propagated silently
through phases 2, 3, and 4 without any phase raising an error. By phase 5, the
generic validators were applied, the domain-specific test assertion failed, and
the error message said "assertion failed." The message tells the developer
*what* failed (an assertion in phase 5) but not *why* (domain classification
returned a default in phase 1, which was never challenged in phases 2-4). A
developer looking at phase 5's test code would see nothing wrong. The bug is
four phases upstream.

The full causal chain is:
1. Phase 1 (plan): `classify_domain()` returned `"unknown"` because the project
   description was ambiguous
2. Phase 2 (scaffold): Received `domain: "unknown"`, did not use the field,
   passed it through unchanged
3. Phase 3 (design): Received `domain: "unknown"`, did not use the field,
   passed it through unchanged
4. Phase 4 (implement): Received `domain: "unknown"`, selected generic
   validators instead of domain-specific ones
5. Phase 5 (test): Generic validators ran, domain-specific assertion failed

The error in phase 5 contains none of this context.

**Failure 2: Token budget exhausted upstream.**

Agent B fails with `RateLimitError: rate limit exceeded`. The immediate cause is
clear — Agent B hit the API rate limit. But the root cause is that Agent A, which
ran before Agent B in the same pipeline, consumed 90% of the shared token budget
with an oversized prompt. Agent A completed successfully. Agent B failed because
the remaining budget was insufficient. The error in Agent B has no information
about Agent A's overconsumption. A developer investigating Agent B would tune
Agent B's prompts, never realizing that Agent A is the problem.

The full causal chain is:
1. Pipeline starts with a 100,000 token budget
2. Agent A generates a 45,000 token prompt (expected: 20,000) and receives a
   40,000 token response, consuming 85,000 tokens total
3. Agent B receives 15,000 remaining tokens, attempts a 25,000 token prompt
4. API returns 429 (rate limit exceeded)

The error in Agent B says "rate limit exceeded." It does not say "Agent A
consumed 85% of the budget, leaving you with 15%."

**Failure 3: Malformed input cascades through the pipeline.**

Service D returns HTTP 500. The stack trace shows a `NullPointerException` in
Service D's handler. A developer investigates Service D's code, finds the null
check was missing, adds the null check, and deploys. The 500 goes away. But the
underlying problem remains: Service A sent a field with value `""` (empty
string) instead of the expected value. Service B parsed it as an empty object.
Service C used the empty object in a computation that produced `null`. Service D
dereferenced the `null`. Each service handled its input correctly from its own
perspective — none knew that the empty string from Service A was incorrect.

The full causal chain is:
1. Service A: Sent `field: ""` (empty string, should have been a domain name)
2. Service B: Parsed `""` as `{}` (empty JSON object — this is the bug, but
   Service B has no way to know the empty string was wrong)
3. Service C: Used `{}` in a lookup, got `null` result (correct behavior for
   empty input)
4. Service D: Dereferenced `null`, threw NullPointerException

The 500 error shows only step 4. Steps 1-3 are invisible.

### The Pattern

All three failures share the same structure:

1. A decision is made upstream (default domain, oversized prompt, empty field)
2. The decision propagates through intermediate phases without challenge
3. The decision causes a failure downstream
4. The downstream error has no context about the upstream decision
5. The developer investigates the wrong phase

---

## 2. Solution Overview

An error context enrichment system that automatically attaches provenance and
contract context to errors as they occur, constructing causal narratives from
the contract metadata that the other 7 layers have already stamped into the
context.

The key insight: **if every boundary stamps provenance (Layer 1), validates
schemas (Layer 2), enforces naming (Layer 3), checks ordering (Layer 4),
verifies capabilities (Layer 5), tracks budgets (Layer 6), and records lineage
(Layer 7), then when an error occurs, all the information needed to construct
the causal chain is already present in the context.** Error context enrichment
doesn't add new instrumentation — it *synthesizes* the instrumentation from all
other layers into a coherent explanation at the moment of failure.

```
Error occurs in phase F
         │
         ▼
┌────────────────────────────┐
│   ErrorContextCollector     │  ← Gathers context from all layers
│   Reads:                    │
│   - _cc_propagation         │     Layer 1: provenance stamps
│   - _cc_schema_checks       │     Layer 2: schema validation results
│   - _cc_convention_checks   │     Layer 3: naming validation results
│   - _cc_ordering            │     Layer 4: ordering constraints
│   - _cc_capabilities        │     Layer 5: capability chain state
│   - _cc_budgets             │     Layer 6: budget allocations
│   - _cc_lineage             │     Layer 7: transformation history
│   - _cc_error_context       │     Prior error breadcrumbs
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│   CausalNarrativeBuilder   │  ← Constructs human-readable explanation
│   Correlates:               │
│   - Provenance trail        │     Which phase set the failing field?
│   - Contract violations     │     Were any contracts violated upstream?
│   - Budget state            │     Was a budget exhausted?
│   - Capability chain        │     Was a capability lost?
│   - Default applications    │     Were any fields defaulted?
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│    EnrichedError            │  ← Wraps Python exception
│    Contains:                │
│    - Original exception     │
│    - ErrorContext model     │
│    - Causal narrative       │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│   ErrorContextEmitter       │  ← OTel span events
│   Emits:                    │
│   - error.enriched          │
│   - error.causal_chain      │
│   - error.contributing      │
│     _violation              │
└────────────────────────────┘
```

### Split Placement

Like Layer 1, the framework lives in **ContextCore** and concrete error
enrichment configuration lives in consuming codebases.

| Component | Repo | Path |
|---|---|---|
| Error context model | ContextCore | `src/contextcore/contracts/errors/models.py` |
| Error context collector | ContextCore | `src/contextcore/contracts/errors/collector.py` |
| Causal narrative builder | ContextCore | `src/contextcore/contracts/errors/narrative.py` |
| Enriched error wrapper | ContextCore | `src/contextcore/contracts/errors/enriched.py` |
| OTel emission | ContextCore | `src/contextcore/contracts/errors/otel.py` |
| Pipeline error hooks | startd8-sdk | `src/startd8/contractors/error_enrichment.py` |
| Orchestrator wiring | startd8-sdk | `src/startd8/contractors/artisan_contractor.py` |

---

## 3. Error Enrichment Model

### 3.1 Core Data Model

The `ErrorContext` model captures everything known about the circumstances of
an error at the moment it occurs. It draws from all 7 contract layers.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ContractViolation(BaseModel):
    """A contract violation that may have contributed to the error."""

    model_config = {"extra": "forbid"}

    layer: int  # Which contract layer (1-7)
    layer_name: str  # Human-readable layer name
    phase: str  # Phase where violation occurred
    violation_type: str  # e.g., "field_defaulted", "budget_exceeded"
    field: str | None = None  # Field involved, if applicable
    severity: str  # blocking / warning / advisory
    message: str  # Human-readable description
    detected_at: str  # ISO 8601 timestamp
    contributed_to_error: bool = False  # Set by causal analysis


class BudgetAllocation(BaseModel):
    """Budget state for a resource at a point in time."""

    model_config = {"extra": "forbid"}

    resource: str  # e.g., "tokens", "latency_ms", "api_calls"
    total: float  # Total budget
    consumed: float  # Amount consumed
    remaining: float  # Amount remaining
    consumed_by_phase: dict[str, float] = Field(default_factory=dict)
    exhausted: bool = False  # True if remaining <= 0


class ErrorContext(BaseModel):
    """Rich error context including provenance trail, contract violations,
    budget state, and capability chain."""

    model_config = {"extra": "forbid"}

    # Error identification
    error_id: str  # Unique identifier for this error occurrence
    error_phase: str  # Phase where error occurred
    error_type: str  # Exception class name (e.g., "AssertionError")
    error_message: str  # Original error message

    # Provenance trail (from Layer 1)
    provenance_trail: list[dict] = Field(default_factory=list)
    # Each entry: {"field": str, "origin_phase": str, "set_at": str,
    #              "value_hash": str}

    # Contract violations that may have contributed (from Layers 1-7)
    contributing_violations: list[ContractViolation] = Field(
        default_factory=list
    )

    # Budget state at time of error (from Layer 6)
    budget_state: dict[str, BudgetAllocation] | None = None

    # Capability chain state (from Layer 5)
    capability_state: list[str] | None = None

    # Lineage entries for affected fields (from Layer 7)
    lineage_entries: list[dict] = Field(default_factory=list)

    # Ordering context (from Layer 4)
    ordering_context: list[dict] = Field(default_factory=list)

    # Schema validation context (from Layer 2)
    schema_context: list[dict] = Field(default_factory=list)

    # Causal narrative (auto-generated by CausalNarrativeBuilder)
    causal_narrative: str = ""

    # Root cause analysis
    root_cause_phase: str | None = None  # Phase identified as root cause
    root_cause_confidence: float = 0.0  # 0.0–1.0

    # Metadata
    pipeline_id: str | None = None
    trace_id: str | None = None
    timestamp: str = ""  # ISO 8601

    # Chain of enriched errors if multiple occurred
    prior_errors: list[str] = Field(default_factory=list)
    # List of error_ids from earlier phases
```

### 3.2 EnrichedError Wrapper

The `EnrichedError` wraps a standard Python exception with full ContextCore
context, analogous to Python's `__cause__` but for distributed/multi-phase
systems.

```python
class EnrichedError(Exception):
    """Exception wrapper that carries full ContextCore error context.

    Uses Python's exception chaining (__cause__) for the original exception
    and adds structured context from all contract layers.
    """

    def __init__(
        self,
        message: str,
        original: Exception,
        error_context: ErrorContext,
    ):
        super().__init__(message)
        self.__cause__ = original
        self.error_context = error_context

    def __str__(self) -> str:
        if self.error_context.causal_narrative:
            return self.error_context.causal_narrative
        return (
            f"EnrichedError in phase '{self.error_context.error_phase}': "
            f"{self.error_context.error_message}"
        )

    @property
    def root_cause_phase(self) -> str | None:
        return self.error_context.root_cause_phase

    @property
    def contributing_violations(self) -> list[ContractViolation]:
        return self.error_context.contributing_violations

    @property
    def causal_narrative(self) -> str:
        return self.error_context.causal_narrative
```

### 3.3 Design Rationale

**Why a wrapper rather than modifying the original exception?** The original
exception must be preserved for existing error handling code. Code that catches
`AssertionError` must still work. The `EnrichedError` adds context *alongside*
the original, not *instead of*. This is the same principle as Python's
`__cause__` — the chain extends, it doesn't replace.

**Why Pydantic models?** Structured data enables OTel serialization,
dashboard queries, and programmatic analysis. An unstructured error message is
only useful to humans reading logs. A structured `ErrorContext` is useful to
dashboards, alerting rules, and (in future work) AI-powered root cause analysis.

**Why `extra="forbid"`?** Consistent with Layer 1. Unknown fields in error
context indicate a schema mismatch, which should fail fast rather than silently
pass through extra data.

---

## 4. Error Context Collector

The `ErrorContextCollector` is responsible for gathering context from all
available contract layers when an error occurs. It reads the reserved keys
that each layer stamps into the context dict.

### 4.1 Reserved Context Keys

Each contract layer stores its metadata under a reserved `_cc_` prefix key in
the context dict. The collector reads all available keys:

| Key | Layer | Contents |
|---|---|---|
| `_cc_propagation` | Layer 1 | `FieldProvenance` entries (origin, timestamp, hash) |
| `_cc_schema_checks` | Layer 2 | Schema validation results per phase |
| `_cc_convention_checks` | Layer 3 | Naming convention validation results |
| `_cc_ordering` | Layer 4 | Ordering constraint check results |
| `_cc_capabilities` | Layer 5 | Capability chain state |
| `_cc_budgets` | Layer 6 | Budget allocation and consumption records |
| `_cc_lineage` | Layer 7 | Data transformation history |
| `_cc_error_context` | Errors | Prior error breadcrumbs from earlier phases |
| `_cc_boundary_results` | Layer 1 | Accumulated boundary validation results |

### 4.2 Collection Algorithm

```python
class ErrorContextCollector:
    """Collects context from all contract layers at the moment of error."""

    def collect(
        self,
        exception: Exception,
        phase: str,
        context: dict,
        pipeline_id: str | None = None,
        trace_id: str | None = None,
    ) -> ErrorContext:
        """Collect all available context for an error.

        This method is designed to be called in an except block. It never
        raises — if any collection step fails, it logs and continues with
        partial context. An error in the error enrichment system must not
        mask the original error.
        """
        error_ctx = ErrorContext(
            error_id=_generate_error_id(),
            error_phase=phase,
            error_type=type(exception).__name__,
            error_message=str(exception),
            pipeline_id=pipeline_id,
            trace_id=trace_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

        # Layer 1: Provenance trail
        error_ctx.provenance_trail = self._collect_provenance(context)

        # Layer 2: Schema validation context
        error_ctx.schema_context = self._collect_schema_checks(context)

        # Layer 3-7: Contract violations
        error_ctx.contributing_violations = (
            self._collect_violations(context, phase)
        )

        # Layer 5: Capability state
        error_ctx.capability_state = self._collect_capabilities(context)

        # Layer 6: Budget state
        error_ctx.budget_state = self._collect_budget_state(context)

        # Layer 7: Lineage
        error_ctx.lineage_entries = self._collect_lineage(context)

        # Prior errors
        error_ctx.prior_errors = self._collect_prior_errors(context)

        return error_ctx
```

### 4.3 Graceful Collection

**Critical design decision:** The collector never raises exceptions. Every
collection step is wrapped in a try/except that logs the collection failure and
continues with partial context. The rationale is identical to OTel's design
principle — instrumentation must not break the instrumented code.

```python
def _collect_provenance(self, context: dict) -> list[dict]:
    try:
        propagation = context.get("_cc_propagation", {})
        return [
            {
                "field": field,
                "origin_phase": prov.origin_phase,
                "set_at": prov.set_at,
                "value_hash": prov.value_hash,
            }
            for field, prov in propagation.items()
        ]
    except Exception:
        logger.debug("Failed to collect provenance for error context")
        return []
```

This pattern repeats for every collection method. Partial context is always
better than no context, and no context is always better than crashing the
error handling path.

### 4.4 Violation Correlation

The collector identifies contract violations that may have *contributed* to
the current error. The heuristic is conservative:

1. **Temporal**: Only violations detected before the current error
2. **Directional**: Only violations in phases upstream of the error phase
3. **Field-based**: If the error message references a field name that appears
   in a violation, mark the violation as `contributed_to_error=True`
4. **Budget-based**: If the error is a rate limit or timeout and a budget was
   exhausted, mark the budget violation as contributing

```python
def _correlate_violations(
    self,
    violations: list[ContractViolation],
    error_phase: str,
    error_message: str,
    phase_order: list[str],
) -> list[ContractViolation]:
    """Mark violations that likely contributed to this error."""
    error_phase_idx = phase_order.index(error_phase)

    for v in violations:
        v_idx = phase_order.index(v.phase) if v.phase in phase_order else -1

        # Only upstream violations can contribute
        if v_idx >= error_phase_idx:
            continue

        # Field name appears in error message
        if v.field and v.field in error_message:
            v.contributed_to_error = True

        # Default was applied to a field referenced by error
        if v.violation_type == "field_defaulted":
            v.contributed_to_error = True

        # Budget exhaustion correlates with rate/timeout errors
        if v.violation_type == "budget_exceeded" and any(
            term in error_message.lower()
            for term in ("rate limit", "timeout", "exceeded", "budget")
        ):
            v.contributed_to_error = True

    return violations
```

This correlation is heuristic, not definitive. The `contributed_to_error` flag
indicates "this violation is in the causal neighborhood of the error," not
"this violation definitely caused the error." The causal narrative presents the
information for human judgment.

---

## 5. Causal Narrative Generation

The causal narrative is a human-readable explanation of the error's likely
causal chain. It is auto-generated from the collected error context and
designed to answer the question: *"What happened before this error that
explains why it occurred?"*

### 5.1 Narrative Structure

Every causal narrative follows a consistent structure:

```
Error in phase '{phase}': {error_type}: {error_message}

Causal chain:
1. Phase '{source_phase}' set {field} = {value_repr} (hash: {hash})
   → {annotation about what this means}
2. Phase '{intermediate_phase}' received {field} = {value_repr}
   → {annotation about contract violation or pass-through}
3. Phase '{error_phase}' expected {expected} but received {actual}
   → This is the likely root cause of the {error_type}

Propagation chain '{chain_id}': {status}
Budget state: {budget_summary}
```

### 5.2 Narrative Examples

**Example 1: Domain classification failure**

```
Error in phase 'test': AssertionError: expected domain-specific test

Causal chain:
1. Phase 'plan' set domain_summary.domain = "unknown" (hash: a1b2c3d4)
   → WARNING: Domain classification returned default value
2. Phase 'scaffold' received domain_summary.domain = "unknown"
   → Pass-through: field not consumed by this phase
3. Phase 'design' received domain_summary.domain = "unknown"
   → Pass-through: field not consumed by this phase
4. Phase 'implement' received domain_summary.domain = "unknown"
   → Contract violation: enrichment field defaulted (severity: warning)
   → Generic validators selected instead of domain-specific validators
5. Phase 'test' expected domain-specific validators but domain was "unknown"
   → This is the likely root cause of the assertion failure

Propagation chain 'domain_to_implement': DEGRADED
Root cause phase: plan (confidence: 0.85)
```

**Example 2: Token budget exhaustion**

```
Error in phase 'agent_b': RateLimitError: rate limit exceeded

Causal chain:
1. Pipeline started with token budget: 100,000 tokens
2. Phase 'agent_a' consumed 85,000 tokens (budget: 20,000, actual: 85,000)
   → WARNING: Agent A exceeded its budget allocation by 325%
   → Remaining budget after agent_a: 15,000 tokens
3. Phase 'agent_b' attempted 25,000 token request with 15,000 remaining
   → This is the likely root cause of the rate limit error

Budget state:
  tokens: 85,000 / 100,000 consumed (85.0%)
  agent_a consumed: 85,000 (allocation: 20,000) ← EXCEEDED
  agent_b consumed: 0 (allocation: 25,000, available: 15,000) ← INSUFFICIENT

Root cause phase: agent_a (confidence: 0.90)
```

**Example 3: Cascading field corruption**

```
Error in phase 'service_d': NullPointerException: field 'result' is null

Causal chain:
1. Phase 'service_a' set input_field = "" (hash: e3b0c442)
   → WARNING: Empty string may indicate missing data
2. Phase 'service_b' transformed input_field: "" → {} (hash: 44136fa3)
   → Lineage: value hash changed (e3b0c442 → 44136fa3)
   → WARNING: Empty string parsed as empty object
3. Phase 'service_c' used {} in lookup, produced null
   → Lineage: derived field 'result' set to null (hash: 37a6259c)
4. Phase 'service_d' dereferenced null result
   → This is the immediate cause, but the root cause is in service_a

Propagation chain 'input_to_result': BROKEN
Root cause phase: service_a (confidence: 0.75)
```

### 5.3 Narrative Builder Algorithm

```python
class CausalNarrativeBuilder:
    """Constructs human-readable causal narratives from ErrorContext."""

    def build(self, error_ctx: ErrorContext) -> str:
        """Build a causal narrative from collected error context.

        The algorithm:
        1. Start with the error itself
        2. Walk backward through contributing violations
        3. Add provenance trail entries
        4. Add budget state if relevant
        5. Identify the most likely root cause phase
        6. Format as a numbered chain
        """
        lines = []

        # Header
        lines.append(
            f"Error in phase '{error_ctx.error_phase}': "
            f"{error_ctx.error_type}: {error_ctx.error_message}"
        )
        lines.append("")

        # Build causal chain
        chain_entries = self._build_chain_entries(error_ctx)

        if chain_entries:
            lines.append("Causal chain:")
            for i, entry in enumerate(chain_entries, 1):
                lines.append(f"{i}. {entry.summary}")
                for annotation in entry.annotations:
                    lines.append(f"   → {annotation}")
            lines.append("")

        # Propagation chain status
        chain_statuses = self._extract_chain_statuses(error_ctx)
        for chain_id, status in chain_statuses.items():
            lines.append(f"Propagation chain '{chain_id}': {status}")

        # Budget state
        if error_ctx.budget_state:
            lines.append("")
            lines.append("Budget state:")
            for resource, alloc in error_ctx.budget_state.items():
                pct = (alloc.consumed / alloc.total * 100) if alloc.total else 0
                lines.append(
                    f"  {resource}: {alloc.consumed:,.0f} / "
                    f"{alloc.total:,.0f} consumed ({pct:.1f}%)"
                )
                for phase, amount in alloc.consumed_by_phase.items():
                    marker = " ← EXCEEDED" if amount > alloc.total * 0.5 else ""
                    lines.append(f"  {phase} consumed: {amount:,.0f}{marker}")

        # Root cause
        if error_ctx.root_cause_phase:
            lines.append("")
            lines.append(
                f"Root cause phase: {error_ctx.root_cause_phase} "
                f"(confidence: {error_ctx.root_cause_confidence:.2f})"
            )

        error_ctx.causal_narrative = "\n".join(lines)
        return error_ctx.causal_narrative
```

### 5.4 Root Cause Identification

The builder uses a scoring heuristic to identify the most likely root cause
phase. The score is based on:

| Factor | Weight | Rationale |
|---|---|---|
| Phase distance from error | 0.3 | Further upstream = more likely root cause |
| Number of contributing violations in phase | 0.25 | More violations = more suspicious |
| Severity of violations | 0.2 | BLOCKING violations weigh more |
| Budget overconsumption in phase | 0.15 | Budget abuse directly causes downstream failures |
| Default values applied in phase | 0.1 | Defaults indicate silent degradation |

```python
def _score_root_cause(
    self,
    phase: str,
    error_ctx: ErrorContext,
    phase_order: list[str],
) -> float:
    """Score a phase's likelihood of being the root cause."""
    score = 0.0

    # Distance factor: further upstream = higher score
    error_idx = phase_order.index(error_ctx.error_phase)
    phase_idx = phase_order.index(phase)
    distance = error_idx - phase_idx
    if distance > 0:
        score += 0.3 * min(distance / len(phase_order), 1.0)

    # Violation count factor
    phase_violations = [
        v for v in error_ctx.contributing_violations
        if v.phase == phase and v.contributed_to_error
    ]
    score += 0.25 * min(len(phase_violations) / 3.0, 1.0)

    # Severity factor
    blocking = sum(1 for v in phase_violations if v.severity == "blocking")
    score += 0.2 * min(blocking, 1.0)

    # Budget factor
    if error_ctx.budget_state:
        for alloc in error_ctx.budget_state.values():
            phase_consumed = alloc.consumed_by_phase.get(phase, 0)
            if alloc.total > 0 and phase_consumed > alloc.total * 0.5:
                score += 0.15

    # Default factor
    defaults = sum(
        1 for v in phase_violations
        if v.violation_type == "field_defaulted"
    )
    score += 0.1 * min(defaults, 1.0)

    return min(score, 1.0)
```

The confidence score is the highest phase score. Scores above 0.6 are reported
as "likely root cause." Scores below 0.4 are not reported — the narrative
presents the chain without identifying a root cause, because the evidence is
insufficient.

---

## 6. Error Collection Points

Error context is accumulated progressively as the pipeline executes. By the
time an error occurs, the context dict already contains all the breadcrumbs
needed for enrichment.

### 6.1 Accumulation Model

Each phase boundary adds breadcrumbs to `context["_cc_error_context"]`:

```python
context["_cc_error_context"] = {
    "boundary_results": [
        # From Layer 1 BoundaryValidator
        {
            "phase": "plan",
            "direction": "exit",
            "passed": True,
            "propagation_status": "propagated",
            "timestamp": "2026-02-15T10:30:00Z",
        },
        {
            "phase": "implement",
            "direction": "entry",
            "passed": True,
            "propagation_status": "defaulted",
            "defaulted_fields": ["domain_summary.domain"],
            "timestamp": "2026-02-15T10:31:00Z",
        },
    ],
    "violations": [
        # From all layers
        {
            "layer": 1,
            "phase": "implement",
            "type": "field_defaulted",
            "field": "domain_summary.domain",
            "severity": "warning",
            "timestamp": "2026-02-15T10:31:00Z",
        },
    ],
    "prior_errors": [],  # Error IDs from earlier phases (if any)
}
```

### 6.2 Collection Hooks

The collector integrates at four points:

**Point 1: Phase boundary validation (entry/exit)**

After each `BoundaryValidator` run, the result is appended to
`_cc_error_context.boundary_results`. This happens in the existing
`validate_phase_boundary()` wrapper — one additional line of code.

```python
def validate_phase_boundary(phase, context, direction, contract_path):
    result = _validate(phase, context, direction, contract_path)
    if result:
        _append_error_breadcrumb(context, result)
        emit_boundary_result(result)
    return result
```

**Point 2: Provenance stamping**

After each `PropagationTracker.stamp()`, the stamp is recorded in
`_cc_propagation` (already done by Layer 1). No additional work needed — the
collector reads `_cc_propagation` at error time.

**Point 3: Contract violations**

When any layer detects a violation (defaulted field, broken chain, budget
exceeded, capability lost, ordering violation, schema mismatch, lineage break),
the violation is appended to `_cc_error_context.violations`. Each layer's
validator calls a shared `_record_violation()` helper.

```python
def _record_violation(
    context: dict,
    layer: int,
    phase: str,
    violation_type: str,
    severity: str,
    field: str | None = None,
    message: str = "",
):
    """Record a contract violation for error context enrichment.

    Called by all layer validators. Never raises."""
    try:
        ec = context.setdefault("_cc_error_context", {})
        violations = ec.setdefault("violations", [])
        violations.append({
            "layer": layer,
            "layer_name": _LAYER_NAMES.get(layer, f"Layer {layer}"),
            "phase": phase,
            "type": violation_type,
            "field": field,
            "severity": severity,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
    except Exception:
        pass  # Never fail in instrumentation
```

**Point 4: Error catch sites**

At each phase's try/except in the orchestrator, the `ErrorContextCollector`
is invoked. If the error is not fatal (e.g., a retryable error), the error ID
is appended to `_cc_error_context.prior_errors` and execution continues. If
the error is fatal, the `EnrichedError` is raised (or the enriched context is
emitted and the original exception re-raised).

```python
def _execute_phase(self, phase, context, ...):
    try:
        result = handler.execute(phase, context, ...)
    except Exception as exc:
        # Collect context from all layers
        error_ctx = self._collector.collect(
            exception=exc,
            phase=phase,
            context=context,
            pipeline_id=self._pipeline_id,
        )

        # Build causal narrative
        self._narrative_builder.build(error_ctx)

        # Emit to OTel
        self._emitter.emit_enriched_error(error_ctx)

        # Re-raise with context (or wrap in EnrichedError)
        if self._wrap_errors:
            raise EnrichedError(
                str(error_ctx.causal_narrative),
                original=exc,
                error_context=error_ctx,
            ) from exc
        else:
            # Store context for later retrieval without wrapping
            context.setdefault("_cc_error_context", {})
            context["_cc_error_context"]["last_error"] = (
                error_ctx.model_dump()
            )
            raise
```

### 6.3 Context Size Management

The accumulated error context grows with each phase boundary. To prevent
unbounded growth:

1. **Boundary results**: Only the most recent 20 entries are retained. Older
   entries are summarized as a count.
2. **Violations**: Only the most recent 50 violations are retained. This is
   generous — a pipeline would need to violate more than 50 contracts across
   7 phases to hit this limit.
3. **Prior errors**: Only error IDs are stored, not full `ErrorContext` objects.
   Full contexts are in OTel events.
4. **Provenance trail**: Inherits Layer 1's existing size — one entry per
   tracked field, typically 10-30 entries.

---

## 7. OTel Event Semantics

All events follow ContextCore telemetry conventions and are emitted as OTel
span events on the current active span. If OTel is not installed, events are
logged only (no crash).

### 7.1 Error Enriched Event

**Event name:** `error.enriched`

Emitted when an error is caught and enriched with contract context.

| Attribute | Type | Description |
|---|---|---|
| `error.enriched.error_id` | str | Unique error occurrence ID |
| `error.enriched.error_phase` | str | Phase where error occurred |
| `error.enriched.error_type` | str | Exception class name |
| `error.enriched.error_message` | str | Original error message (truncated to 500 chars) |
| `error.enriched.root_cause_phase` | str | Identified root cause phase (if any) |
| `error.enriched.root_cause_confidence` | float | Confidence in root cause identification |
| `error.enriched.contributing_violations_count` | int | Number of contributing violations |
| `error.enriched.causal_chain_length` | int | Number of steps in causal chain |
| `error.enriched.pipeline_id` | str | Pipeline identifier |
| `error.enriched.layers_involved` | str | Comma-separated layer numbers with data |
| `error.enriched.has_budget_context` | bool | Whether budget state was available |
| `error.enriched.has_provenance_trail` | bool | Whether provenance trail was available |

**TraceQL query — find enriched errors with identified root cause:**
```traceql
{ name = "error.enriched" && span.error.enriched.root_cause_phase != "" }
```

**TraceQL query — find errors enriched from Layer 1 (propagation) data:**
```traceql
{ name = "error.enriched" && span.error.enriched.has_provenance_trail = true }
```

### 7.2 Causal Chain Event

**Event name:** `error.causal_chain`

Emitted alongside `error.enriched`, containing the full causal narrative as
a string attribute. Separated from the enriched event because narratives can
be long and some backends truncate attribute values.

| Attribute | Type | Description |
|---|---|---|
| `error.causal_chain.error_id` | str | Links to the `error.enriched` event |
| `error.causal_chain.narrative` | str | Full causal narrative text |
| `error.causal_chain.root_cause_phase` | str | Root cause phase (duplicated for queryability) |
| `error.causal_chain.chain_length` | int | Number of steps |

**TraceQL query — find causal chains that identify plan as root cause:**
```traceql
{ name = "error.causal_chain" && span.error.causal_chain.root_cause_phase = "plan" }
```

### 7.3 Contributing Violation Event

**Event name:** `error.contributing_violation`

Emitted once per contributing violation, enabling per-violation queries. For
errors with many contributing violations, this produces multiple events on the
same span — consistent with OTel's event model.

| Attribute | Type | Description |
|---|---|---|
| `error.contributing_violation.error_id` | str | Links to the `error.enriched` event |
| `error.contributing_violation.layer` | int | Contract layer (1-7) |
| `error.contributing_violation.layer_name` | str | Human-readable layer name |
| `error.contributing_violation.phase` | str | Phase where violation occurred |
| `error.contributing_violation.violation_type` | str | Violation type |
| `error.contributing_violation.field` | str | Field involved (if applicable) |
| `error.contributing_violation.severity` | str | blocking / warning / advisory |
| `error.contributing_violation.message` | str | Human-readable description |

**TraceQL query — find errors caused by budget violations:**
```traceql
{ name = "error.contributing_violation" && span.error.contributing_violation.violation_type = "budget_exceeded" }
```

**TraceQL query — find contributing violations from Layer 1:**
```traceql
{ name = "error.contributing_violation" && span.error.contributing_violation.layer = 1 }
```

### 7.4 Emitter Implementation

```python
class ErrorContextEmitter:
    """Emits enriched error events to OTel."""

    def emit_enriched_error(self, error_ctx: ErrorContext) -> None:
        """Emit all error context events.

        Emits three types of events:
        1. error.enriched — summary event
        2. error.causal_chain — narrative event
        3. error.contributing_violation — one per violation
        """
        if not _HAS_OTEL:
            logger.info(
                "error.enriched phase=%s type=%s root_cause=%s",
                error_ctx.error_phase,
                error_ctx.error_type,
                error_ctx.root_cause_phase,
            )
            return

        span = trace.get_current_span()
        if not span or not span.is_recording():
            return

        # 1. Summary event
        span.add_event(
            "error.enriched",
            attributes={
                "error.enriched.error_id": error_ctx.error_id,
                "error.enriched.error_phase": error_ctx.error_phase,
                "error.enriched.error_type": error_ctx.error_type,
                "error.enriched.error_message": (
                    error_ctx.error_message[:500]
                ),
                "error.enriched.root_cause_phase": (
                    error_ctx.root_cause_phase or ""
                ),
                "error.enriched.root_cause_confidence": (
                    error_ctx.root_cause_confidence
                ),
                "error.enriched.contributing_violations_count": len(
                    error_ctx.contributing_violations
                ),
                "error.enriched.causal_chain_length": len(
                    error_ctx.provenance_trail
                ),
                "error.enriched.pipeline_id": (
                    error_ctx.pipeline_id or ""
                ),
                "error.enriched.has_budget_context": (
                    error_ctx.budget_state is not None
                ),
                "error.enriched.has_provenance_trail": (
                    len(error_ctx.provenance_trail) > 0
                ),
            },
        )

        # 2. Causal chain event
        if error_ctx.causal_narrative:
            span.add_event(
                "error.causal_chain",
                attributes={
                    "error.causal_chain.error_id": error_ctx.error_id,
                    "error.causal_chain.narrative": (
                        error_ctx.causal_narrative
                    ),
                    "error.causal_chain.root_cause_phase": (
                        error_ctx.root_cause_phase or ""
                    ),
                    "error.causal_chain.chain_length": len(
                        error_ctx.provenance_trail
                    ),
                },
            )

        # 3. Contributing violations (one event each)
        for v in error_ctx.contributing_violations:
            if not v.contributed_to_error:
                continue
            span.add_event(
                "error.contributing_violation",
                attributes={
                    "error.contributing_violation.error_id": (
                        error_ctx.error_id
                    ),
                    "error.contributing_violation.layer": v.layer,
                    "error.contributing_violation.layer_name": v.layer_name,
                    "error.contributing_violation.phase": v.phase,
                    "error.contributing_violation.violation_type": (
                        v.violation_type
                    ),
                    "error.contributing_violation.field": v.field or "",
                    "error.contributing_violation.severity": v.severity,
                    "error.contributing_violation.message": v.message,
                },
            )
```

---

## 8. Relationship to All Layers

Error context enrichment is the **capstone** of the Context Correctness by
Construction system. It is what gives the other 7 layers practical value for
debugging. Without error enrichment, the other layers prevent silent
degradation but do not help diagnose failures when they occur. With error
enrichment, every failure carries a causal narrative constructed from the
contracts and provenance that the other layers have accumulated.

### 8.1 Layer-by-Layer Synthesis

| Layer | What It Stamps | What Error Enrichment Extracts |
|---|---|---|
| **Layer 1: Propagation** | `FieldProvenance` (origin phase, timestamp, value hash) | "This field was set by phase A at time T with value hash H. The value at the error site has hash H', which means it was mutated in transit." |
| **Layer 2: Schema** | Schema validation results (expected type, received type) | "Phase B expected field X to be type `dict`, but received type `str`. This schema mismatch may have caused the downstream parsing failure." |
| **Layer 3: Conventions** | Naming convention checks (canonical name, received name) | "Phase C emitted `user_id` but the convention requires `user.id`. Downstream queries for `user.id` would have missed this data." |
| **Layer 4: Ordering** | Ordering constraint results (expected order, actual order) | "Event B arrived before Event A. Phase D assumed A-then-B ordering and produced incorrect state." |
| **Layer 5: Capabilities** | Capability chain state (available, required, missing) | "Phase E required capability `write:config` but it was not present. The capability was available at phase A but was dropped at phase C (no propagation)." |
| **Layer 6: Budgets** | Budget allocation and consumption (total, consumed, remaining) | "Phase F was allocated 20,000 tokens but phase D consumed 85,000, leaving only 15,000 for F. The rate limit error is caused by D's overconsumption, not F's request." |
| **Layer 7: Lineage** | Transformation history (input hash, output hash, transform ID) | "Field X was `'web_app'` at phase A (hash: a1b2), transformed to `{'type': 'web_app'}` at phase C (hash: c3d4), then to `null` at phase E (hash: 37a6). The null was introduced at phase E's transformation." |

### 8.2 Progressive Value

The error enrichment system provides value proportional to the number of
layers deployed:

- **Layer 1 only**: Errors include provenance trails. "This field was set by
  phase X." Already more useful than a bare stack trace.
- **Layers 1 + 6**: Errors include provenance plus budget state. Budget
  exhaustion errors identify the overconsumer.
- **Layers 1 + 2 + 3**: Errors include provenance plus schema and naming
  context. Type mismatches and naming violations appear in the causal chain.
- **All layers**: Full causal narrative with provenance, violations, budgets,
  capabilities, ordering, and lineage.

This progressive value is why error enrichment is a cross-cutting concern
rather than a numbered layer. It does not require all layers to be useful, but
it becomes more useful with each layer that is added.

### 8.3 Why Not a Layer?

Error context enrichment is not Layer 8 because:

1. **It does not declare contracts.** There is no "error enrichment contract
   YAML." It synthesizes contracts declared by other layers.
2. **It does not validate at boundaries.** It activates at error time, not at
   phase boundaries. (It *reads* boundary validation results, but does not
   perform boundary validation itself.)
3. **It does not stamp provenance.** It reads provenance stamps from Layer 1
   and lineage records from Layer 7.
4. **It spans all layers.** A numbered layer has a specific domain (propagation,
   schema, ordering, etc.). Error enrichment has no specific domain — it is the
   *integration point* for all domains.

It uses the **Emit** primitive (OTel span events) but not the Declare,
Validate, or Track primitives. It is a consumer of all layers, not a peer.

---

## 9. Relationship to Existing Error Handling

### 9.1 Python Exception Chaining

Python's `__cause__` (explicit chaining via `raise X from Y`) and `__context__`
(implicit chaining) preserve the causal chain within a single process. This is
a solved problem for single-process systems — the traceback shows every frame.

**What ContextCore adds:** In a multi-phase pipeline, each phase is a separate
execution context. Python's exception chaining stops at phase boundaries
because the exception is caught, logged, and (typically) re-thrown as a
phase-level error. `EnrichedError` extends the causal chain across phase
boundaries using provenance data instead of stack frames.

### 9.2 Java Cause Chains

Java's `Exception.getCause()` provides the same single-process chaining.
Frameworks like Spring add context with `NestedServletException`. But the
chain breaks at service boundaries (HTTP, gRPC, message queues).

**What ContextCore adds:** Same as above — cross-boundary context from
contract provenance.

### 9.3 Distributed Tracing

OpenTelemetry distributed tracing links spans across services. A trace shows
*that* Service A called Service B called Service C. If Service C fails, you
can see the trace and know that A and B were involved.

**What tracing misses:** The trace shows the *call graph*, not the *data flow*.
It shows that Service A was called, not what Service A contributed to the
failure. If Service A set a field to a default value, and that default
propagated silently through B, causing C to fail — the trace shows three
healthy spans and one error span. The connection between A's default value
and C's error is invisible.

**What ContextCore adds:** Provenance data on spans. The trace shows the call
graph. ContextCore's error enrichment events on the trace show the data flow
and causal chain. The same trace that shows "A called B called C" now also
shows "A set field X to 'unknown', which propagated through B, causing C's
assertion to fail."

### 9.4 Structured Logging

Structured logging (JSON logs with structured fields) enables correlation
across services. Tools like Loki can query for a trace ID across all services
and reconstruct the timeline.

**What structured logging misses:** Each service logs its own perspective.
Service A logs "set domain to unknown." Service C logs "assertion failed."
The human must read both logs, realize they share a trace ID, and manually
construct the causal chain.

**What ContextCore adds:** Automatic causal narrative construction. The
`error.causal_chain` event contains the narrative that a human would construct
by reading all the logs — but it's generated automatically and attached to the
error span. No log correlation required.

### 9.5 Summary of Differentiation

| Mechanism | Scope | What It Shows | Gap |
|---|---|---|---|
| Python `__cause__` | Single process | Stack frame chain | Stops at phase/service boundaries |
| Distributed tracing | Cross-service | Call graph (spans) | Shows *that* A was called, not *what* A contributed |
| Structured logging | Cross-service | Per-service events | Requires manual correlation |
| Error context enrichment | Cross-phase/service | Causal data flow chain | Automatic narrative from contract provenance |

---

## 10. Dashboard Integration

### 10.1 Error Investigation Dashboard

The error investigation dashboard provides a drill-down from high-level error
rates to full causal narratives. It is designed for the workflow:
"I see an error. Show me why it happened."

**Panel 1: Enriched Error Rate (Time series)**
```traceql
{ name = "error.enriched" }
| rate()
```

**Panel 2: Root Cause Phase Distribution (Pie chart)**
```traceql
{ name = "error.enriched" && span.error.enriched.root_cause_phase != "" }
| select(span.error.enriched.root_cause_phase)
```
Shows which phases are most frequently identified as root causes. Phases that
appear disproportionately indicate systemic upstream issues.

**Panel 3: Contributing Violations by Layer (Bar chart)**
```traceql
{ name = "error.contributing_violation" }
| select(span.error.contributing_violation.layer_name)
```
Shows which contract layers most frequently contribute to errors. A spike in
Layer 6 (budgets) violations suggests resource allocation issues.

**Panel 4: Causal Chain Length Distribution (Histogram)**
```traceql
{ name = "error.enriched" }
| select(span.error.enriched.causal_chain_length)
```
Longer causal chains indicate more deeply nested root causes. A trend toward
longer chains suggests increasing system complexity.

**Panel 5: Recent Causal Narratives (Table)**
```traceql
{ name = "error.causal_chain" }
| select(
    span.error.causal_chain.root_cause_phase,
    span.error.causal_chain.chain_length,
    span.error.causal_chain.narrative
  )
```
Full-text causal narratives for recent errors. The primary investigation tool.

**Panel 6: Root Cause Confidence Distribution (Stat panel)**
```traceql
{ name = "error.enriched" && span.error.enriched.root_cause_confidence > 0 }
| avg(span.error.enriched.root_cause_confidence)
```
Average confidence in root cause identification. Low confidence suggests that
more contract layers are needed to provide sufficient context.

### 10.2 Alerting Rules

**Alert: High-confidence root cause in upstream phase**
```yaml
- alert: UpstreamRootCauseDetected
  expr: |
    count_over_time({job="artisan"} | json
      | event="error.enriched"
      | root_cause_confidence > 0.7
      | root_cause_phase != error_phase [15m]) > 0
  for: 0m
  labels:
    severity: warning
  annotations:
    summary: >
      Errors are being caused by upstream phases. The root cause is
      not in the failing phase — investigate the identified root cause
      phase.
```

**Alert: Repeated contributing violations from same layer**
```yaml
- alert: SystemicContractViolations
  expr: |
    count_over_time({job="artisan"} | json
      | event="error.contributing_violation" [1h]) > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: >
      More than 10 contract violations contributed to errors in the
      last hour. This may indicate a systemic issue in the identified
      contract layer.
```

---

## 11. Adoption Path

### 11.1 Progressive Adoption

Error context enrichment is immediately useful with **only Layer 1 deployed**.
The adoption path matches the layer deployment order:

**Stage 1: Layer 1 only (current state)**

With only propagation contracts deployed, errors receive:
- Provenance trail (which phase set which fields)
- Boundary validation results (which fields were defaulted)
- Propagation chain status (INTACT/DEGRADED/BROKEN)

The causal narrative for the domain classification failure (Example 1) is
fully constructible from Layer 1 data alone. This is the most common class of
pipeline error.

**Stage 2: Layers 1 + 6 (budgets)**

Adding budget tracking enables enrichment of rate limit, timeout, and resource
exhaustion errors. The token budget failure (Example 2) requires Layer 6 data.

**Stage 3: Layers 1 + 2 + 7 (schema + lineage)**

Adding schema validation and data lineage enables enrichment of type mismatch
and data corruption errors. The cascading corruption failure (Example 3)
requires Layer 2 (schema) and Layer 7 (lineage) data.

**Stage 4: All layers**

Full enrichment across all contract domains.

### 11.2 Opt-In Integration

The error enrichment system is opt-in at the orchestrator level:

```python
class ArtisanContractorWorkflow:
    def __init__(
        self,
        ...,
        contract_path: Path | None = None,
        error_enrichment: bool = True,  # Enabled when contract_path is set
    ):
        if contract_path and error_enrichment:
            self._collector = ErrorContextCollector()
            self._narrative_builder = CausalNarrativeBuilder()
            self._emitter = ErrorContextEmitter()
        else:
            self._collector = None
```

When `error_enrichment` is `False` or no contract is loaded, the orchestrator's
error handling is unchanged. No performance cost, no behavioral change.

### 11.3 Backward Compatibility

- **Existing exception handling**: `EnrichedError` wraps the original
  exception. Code that catches `AssertionError` still works because
  `EnrichedError` preserves `__cause__`.
- **Existing logging**: The original error message is preserved. Enriched
  context is *added*, not *replaced*.
- **Existing dashboards**: Standard error panels (error rate, error type
  distribution) work unchanged. Enrichment adds new panels, not new semantics
  to existing panels.
- **No OTel dependency**: If OTel is not installed, enrichment still works
  (narrative is constructed, context is stored in the context dict). Only OTel
  emission is skipped.

### 11.4 Configuration

```python
class ErrorEnrichmentConfig(BaseModel):
    """Configuration for error context enrichment."""

    model_config = {"extra": "forbid"}

    enabled: bool = True
    wrap_errors: bool = False  # Wrap in EnrichedError vs store context only
    max_boundary_results: int = 20  # Context size limit
    max_violations: int = 50  # Context size limit
    min_root_cause_confidence: float = 0.4  # Below this, don't report
    emit_contributing_violations: bool = True  # Emit per-violation events
    narrative_max_length: int = 5000  # Truncate narrative if longer
```

`wrap_errors=False` is the default. This means the original exception is
re-raised unchanged, and the enriched context is stored in the context dict
for retrieval by the caller. This is the safest default — it ensures that
error handling code in consuming codebases is completely unaffected.

Setting `wrap_errors=True` wraps the exception in `EnrichedError`, which
changes the exception type. This is useful for codebases that want to catch
`EnrichedError` and display the causal narrative, but requires that existing
exception handling code be updated.

---

## 12. Consequences

### Positive

1. **Errors become self-documenting.** Instead of "assertion failed," the error
   says "assertion failed because domain was 'unknown' because phase 1 returned
   a default because the project description was ambiguous." The human
   investigating the error starts at the right place, not the wrong place.

2. **Root cause analysis shifts from manual to automatic.** The causal narrative
   replaces the manual process of "read the logs, correlate by trace ID,
   reconstruct the chain." For common failure patterns, the narrative is more
   accurate than manual investigation because it has access to contract
   metadata that logs don't contain.

3. **Upstream problems become visible.** Without enrichment, an error in phase
   5 generates investigation in phase 5. With enrichment, the error identifies
   phase 1 as the root cause, directing investigation to the right place. This
   is especially valuable in large teams where different teams own different
   phases.

4. **Contract adoption is incentivized.** Each layer deployed makes error
   enrichment richer. Teams that deploy Layer 1 see immediate value in error
   messages. This creates a natural incentive to deploy additional layers for
   even richer context.

5. **All existing layers become more valuable.** Without error enrichment,
   Layer 1 prevents silent degradation (positive) but doesn't help diagnose
   errors (neutral). With error enrichment, Layer 1 both prevents degradation
   AND provides causal context for errors (double positive). The same logic
   applies to all layers.

### Neutral

1. **Context dict grows with breadcrumbs.** The `_cc_error_context` key
   accumulates data as the pipeline runs. The size limits (20 boundary results,
   50 violations) bound the growth, but it is still additional memory usage.
   For pipelines with large context dicts (common), this is negligible.

2. **Causal narrative is heuristic.** The root cause identification is based
   on scoring heuristics, not definitive causal analysis. The narrative says
   "likely root cause" because it cannot prove causation — only correlation
   with contract metadata. This is still far more useful than no root cause
   analysis, but users should understand the confidence scores.

3. **Multiple events per error.** An error with 5 contributing violations
   emits 7 OTel events (1 enriched + 1 narrative + 5 violations). This is
   consistent with OTel's event model but increases span event count. For error
   cases (which are infrequent by definition), this overhead is acceptable.

### Negative

1. **Partial context may mislead.** If only Layer 1 is deployed and the root
   cause is a budget violation (Layer 6), the causal narrative will identify
   the wrong root cause — the most suspicious provenance entry rather than the
   budget. The confidence score should be low in this case, but users may not
   notice the low confidence.

2. **Error enrichment adds latency to error paths.** Collecting context from
   all layers, building the narrative, and emitting events adds processing
   time to the error handling path. This is typically 1-5ms — negligible for
   error paths (which are already slow due to exception handling, logging, and
   cleanup) but non-zero.

3. **Wrap mode changes exception types.** When `wrap_errors=True`, the
   exception type changes from (e.g.) `AssertionError` to `EnrichedError`.
   Code that catches specific exception types will not catch `EnrichedError`
   unless updated. This is why `wrap_errors=False` is the default.

---

## 13. Future Work

1. **AI-powered root cause analysis.** The structured `ErrorContext` model is
   designed for programmatic analysis. A future integration could send the
   error context to an LLM (via Beaver) and ask: "Given this causal chain,
   contract violations, and budget state, what is the most likely root cause
   and what is the recommended fix?" The structured model provides far richer
   input than a raw stack trace.

2. **Automated remediation suggestions.** For known failure patterns (domain
   defaulted, budget exhausted, schema mismatch), the system could suggest
   specific fixes: "Increase Agent A's token budget from 20,000 to 50,000"
   or "Add explicit domain classification for project type 'embedded'."

3. **Error pattern database.** Collect enriched error contexts over time to
   build a database of failure patterns. When a new error matches a known
   pattern, the narrative can include: "This matches pattern P-042: domain
   classification default. See previous resolution in pipeline run XYZ."

4. **Cross-pipeline error correlation.** When pipeline B fails because
   pipeline A produced incorrect output, the error enrichment in B could
   reference the provenance from A's output. This requires cross-pipeline
   lineage (Layer 7 future work).

5. **Interactive causal exploration.** A Grafana dashboard panel that allows
   users to click on a causal chain step and drill down to the specific phase
   execution, provenance stamp, or contract violation. This requires the
   contextcore-owl plugin infrastructure.

6. **Severity escalation.** When the same root cause phase is identified in
   multiple errors across multiple pipeline runs, automatically escalate the
   contract violation severity from `advisory` to `warning` to `blocking`.
   This closes the loop — errors drive contract tightening.

7. **Error context in A2A handoffs.** When an agent-to-agent handoff fails,
   the `EnrichedError` context should be included in the handoff failure
   response. The receiving agent can then understand why the upstream agent
   failed, not just that it failed.

---

## Appendix A: Proposed File Inventory

| File | Estimated Lines | Purpose |
|---|---|---|
| `contracts/errors/__init__.py` | 60 | Public API exports |
| `contracts/errors/models.py` | 180 | ErrorContext, ContractViolation, BudgetAllocation, EnrichedError |
| `contracts/errors/collector.py` | 250 | ErrorContextCollector, violation correlation |
| `contracts/errors/narrative.py` | 300 | CausalNarrativeBuilder, root cause scoring |
| `contracts/errors/otel.py` | 150 | ErrorContextEmitter |
| `contracts/errors/config.py` | 40 | ErrorEnrichmentConfig |
| `contracts/errors/helpers.py` | 60 | _record_violation(), _generate_error_id() |
| **Total** | **~1,040** | |

Plus orchestrator wiring in startd8-sdk (~50 lines) and tests (~400 lines).

## Appendix B: Type Hierarchy

```
ErrorContext
├── error_id: str
├── error_phase: str
├── error_type: str
├── error_message: str
├── provenance_trail: list[dict]
│   └── {field, origin_phase, set_at, value_hash}
├── contributing_violations: list[ContractViolation]
│   └── ContractViolation
│       ├── layer: int
│       ├── layer_name: str
│       ├── phase: str
│       ├── violation_type: str
│       ├── field: str?
│       ├── severity: str
│       ├── message: str
│       ├── detected_at: str
│       └── contributed_to_error: bool
├── budget_state: dict[str, BudgetAllocation]?
│   └── BudgetAllocation
│       ├── resource: str
│       ├── total: float
│       ├── consumed: float
│       ├── remaining: float
│       ├── consumed_by_phase: dict[str, float]
│       └── exhausted: bool
├── capability_state: list[str]?
├── lineage_entries: list[dict]
├── ordering_context: list[dict]
├── schema_context: list[dict]
├── causal_narrative: str
├── root_cause_phase: str?
├── root_cause_confidence: float
├── pipeline_id: str?
├── trace_id: str?
├── timestamp: str
└── prior_errors: list[str]

EnrichedError (Exception)
├── __cause__: Exception        (original exception)
├── error_context: ErrorContext (full structured context)
├── root_cause_phase: property  (shortcut)
├── contributing_violations: property (shortcut)
└── causal_narrative: property  (shortcut)

ErrorEnrichmentConfig
├── enabled: bool
├── wrap_errors: bool
├── max_boundary_results: int
├── max_violations: int
├── min_root_cause_confidence: float
├── emit_contributing_violations: bool
└── narrative_max_length: int
```

## Appendix C: Interaction with Layer 1 Provenance

The error context collector reads `_cc_propagation` — the same key that
Layer 1's `PropagationTracker.stamp()` writes. This means error enrichment
benefits immediately from Layer 1 without any additional integration work.

```python
# Layer 1 stamps provenance during normal execution:
context["_cc_propagation"]["domain_summary.domain"] = FieldProvenance(
    origin_phase="plan",
    set_at="2026-02-15T10:30:00+00:00",
    value_hash="a1b2c3d4",
)

# When error occurs in phase 'test', the collector reads:
provenance = context.get("_cc_propagation", {})
# → {"domain_summary.domain": FieldProvenance(origin_phase="plan", ...)}

# The narrative builder uses this to construct:
# "Phase 'plan' set domain_summary.domain = ... (hash: a1b2c3d4)"
```

This tight coupling between Layer 1's output and error enrichment's input is
by design. Layer 1 is the keystone layer — it provides the provenance that
makes causal narratives possible. Error enrichment is the capstone — it
synthesizes Layer 1's provenance (and all other layers' metadata) into
actionable explanations.
