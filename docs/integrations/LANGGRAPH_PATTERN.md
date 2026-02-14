# LangGraph → ContextCore Integration Pattern

Map LangGraph's graph execution model to ContextCore governance without duplicating runtime logic.

## Mapping summary

| LangGraph concept | ContextCore contract | Governance value |
|-------------------|---------------------|------------------|
| Graph definition | Parent `TaskSpanContract` (type: story) | Trace-level visibility |
| Node execution | Child `TaskSpanContract` (type: task) | Per-node lifecycle tracking |
| Edge traversal | `GateResult` at decision point | Fail-fast on invalid transitions |
| Conditional edge | `GateResult` with blocking semantics | Policy-enforced routing |
| Tool call within node | `HandoffContract` | Typed delegation with validation |
| Checkpoint | Checksum gate + provenance attributes | Integrity verification on resume |
| State dict | Span attributes (metrics, checksums) | Queryable execution context |

---

## Pattern 1: Graph as parent trace, nodes as child spans

```python
from contextcore.contracts.a2a import (
    TaskSpanContract, Phase, SpanStatus, validate_outbound,
)

# Parent trace for the full graph execution
parent = TaskSpanContract(
    project_id="my-project",
    task_id="checkout-workflow",
    phase=Phase.OTHER,
    status=SpanStatus.IN_PROGRESS,
)
validate_outbound("TaskSpanContract", parent.model_dump(mode="json", exclude_none=True))

# Each node becomes a child span
node_span = TaskSpanContract(
    project_id="my-project",
    trace_id="checkout-workflow",
    task_id="checkout-workflow-validate-order",
    parent_task_id="checkout-workflow",
    phase=Phase.TEST_VALIDATE,
    status=SpanStatus.IN_PROGRESS,
)
validate_outbound("TaskSpanContract", node_span.model_dump(mode="json", exclude_none=True))
```

**Lineage attributes to add:**

```python
span_attrs = {
    "graph.id": "checkout-workflow",
    "graph.node": "validate_order",
    "graph.edge": "start -> validate_order",
}
```

---

## Pattern 2: Conditional edges as gate checks

When LangGraph evaluates a conditional edge, emit a `GateResult` to make the routing decision observable and governable.

```python
from langgraph.graph import StateGraph
from contextcore.contracts.a2a import (
    GateResult, GateOutcome, GateSeverity, Phase,
)
from datetime import datetime, timezone


def route_after_validation(state: dict) -> str:
    """LangGraph conditional edge function — wrapped with gate emission."""

    is_valid = state.get("order_valid", False)
    confidence = state.get("validation_confidence", 0.0)

    # Emit GateResult for observability
    gate = GateResult(
        gate_id=f"checkout-workflow-validate-edge",
        phase=Phase.ROUTING_DECISION,
        result=GateOutcome.PASS if is_valid else GateOutcome.FAIL,
        severity=GateSeverity.INFO if is_valid else GateSeverity.ERROR,
        reason=f"Order validation: valid={is_valid}, confidence={confidence}",
        next_action="Process payment" if is_valid else "Return to cart with errors",
        blocking=not is_valid,
        checked_at=datetime.now(timezone.utc),
    )

    # Log or emit the gate result
    # validate_outbound("GateResult", gate.model_dump(mode="json", exclude_none=True))

    if is_valid:
        return "process_payment"
    else:
        return "handle_error"


# Wire into LangGraph
graph = StateGraph(dict)
graph.add_conditional_edges("validate_order", route_after_validation)
```

---

## Pattern 3: Checkpoint governance

When resuming from a LangGraph checkpoint, verify integrity before proceeding.

```python
from contextcore.contracts.a2a import GateChecker

checker = GateChecker(trace_id="checkout-workflow")

# Before resuming from checkpoint, verify the state hasn't been tampered with
result = checker.check_checksum_chain(
    gate_id="checkpoint-integrity",
    task_id="checkout-workflow-resume",
    expected_checksums={
        "state_hash": checkpoint_metadata["state_hash"],
        "config_hash": checkpoint_metadata["config_hash"],
    },
    actual_checksums={
        "state_hash": compute_hash(current_state),
        "config_hash": compute_hash(current_config),
    },
)

if checker.has_blocking_failure:
    # Don't resume — state integrity broken
    print(f"Cannot resume: {result.reason}")
else:
    # Safe to resume
    graph.invoke(current_state, config={"configurable": {"thread_id": thread_id}})
```

**Checkpoint lineage attributes:**

```python
span_attrs = {
    "graph.checkpoint_id": "cp-abc123",
    "graph.checkpoint_approved_by": "integrity-gate",
}
```

---

## Pattern 4: Tool calls as handoff contracts

When a LangGraph node calls a tool, wrap it in a `HandoffContract` for boundary validation.

```python
from contextcore.contracts.a2a import (
    HandoffContract, ExpectedOutput, validate_outbound, validate_inbound,
)


def call_tool_with_governance(tool_name: str, inputs: dict) -> dict:
    """Wrap a LangGraph tool call with handoff contract validation."""

    handoff = HandoffContract(
        handoff_id=f"tool-{tool_name}-{uuid4().hex[:8]}",
        from_agent="checkout-graph",
        to_agent=tool_name,
        capability_id=tool_name,
        inputs=inputs,
        expected_output=ExpectedOutput(type="tool_result"),
    )

    # Validate outbound
    payload = handoff.model_dump(mode="json", exclude_none=True)
    validate_outbound("HandoffContract", payload)

    # Call the actual tool (LangGraph handles this)
    result = invoke_tool(tool_name, inputs)

    # Validate inbound result if it has contract structure
    # validate_inbound("HandoffContract", result_payload)

    return result
```

---

## Query examples

Once instrumented, use these queries to observe LangGraph execution:

```
# Find all blocked graph nodes
{ resource.service.name = "contextcore" && span.graph.id = "checkout-workflow" && span.task.status = "blocked" }

# Find conditional edge decisions
{ resource.service.name = "contextcore" && span.graph.id = "checkout-workflow" && span.gate.phase = "ROUTING_DECISION" }

# Find checkpoint integrity failures
{ resource.service.name = "contextcore" && span.graph.checkpoint_id != "" && span.gate.result = "fail" }

# Trace a full graph execution
{ resource.service.name = "contextcore" && span.task.parent_id = "checkout-workflow" }
```

---

## What NOT to do

- **Don't rebuild LangGraph's state management** in ContextCore — use graph lineage attributes.
- **Don't replace conditional edges** with ContextCore gate logic — emit gates alongside edge evaluation.
- **Don't store graph state in contracts** — contracts carry governance metadata, not runtime state.
- **Don't block graph execution synchronously** on ContextCore validation in hot paths — validate asynchronously or in non-critical paths first, then tighten.
