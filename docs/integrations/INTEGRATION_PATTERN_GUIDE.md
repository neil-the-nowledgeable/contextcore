# Integration Pattern Guide: Any Runtime → ContextCore Governance

This guide shows how to connect **any** agent framework or pipeline runtime to ContextCore's governance layer. The pattern is the same regardless of framework.

## The universal principle

> **Keep execution in the framework. Govern only boundaries and evidence in ContextCore.**

ContextCore does not replace your runtime. It wraps it with typed contracts, boundary validation, phase gates, and observability — so you get auditability, fail-fast detection, and operational dashboards without changing how your agents execute.

---

## The 4-step integration pattern

### Step 1: Map your framework's primitives to ContextCore spans

Every framework has a concept of "units of work." Map those to `TaskSpanContract`:

| Framework | Framework primitive | ContextCore mapping |
|-----------|-------------------|---------------------|
| **LangGraph** | Graph node execution | `TaskSpanContract` (one span per node) |
| **AutoGen** | Conversation turn / agent message | `TaskSpanContract` (one span per turn) |
| **CrewAI** | Crew task | `TaskSpanContract` (one span per task) |
| **Semantic Kernel** | Plugin/function call | `TaskSpanContract` (one span per call) |
| **LlamaIndex** | Query engine step | `TaskSpanContract` (one span per retrieval+generation) |
| **Haystack** | Pipeline component | `TaskSpanContract` (one span per component) |
| **OpenAI Agents SDK** | Tool call | `TaskSpanContract` (one span per tool invocation) |
| **DSPy** | Module execution | `TaskSpanContract` (one span per module) |
| **Guidance/Outlines/Instructor** | Constrained generation call | `TaskSpanContract` (one span per structured output) |

**Python example (any framework):**

```python
from contextcore.contracts.a2a import TaskSpanContract, Phase, SpanStatus, validate_outbound

# Open a span for whatever your framework is doing
contract = TaskSpanContract(
    project_id="my-project",
    task_id="my-workflow-step-1",
    parent_task_id="my-workflow",
    phase=Phase.ARTISAN_IMPLEMENT,       # or whichever phase fits
    status=SpanStatus.IN_PROGRESS,
)
validate_outbound("TaskSpanContract", contract.model_dump(mode="json", exclude_none=True))
```

### Step 2: Wrap delegations with HandoffContract

Whenever your framework delegates work to another agent/component, emit a `HandoffContract`:

| Framework | Delegation primitive | ContextCore mapping |
|-----------|---------------------|---------------------|
| **LangGraph** | Edge traversal to another node | `HandoffContract` |
| **AutoGen** | Agent-to-agent message send | `HandoffContract` |
| **CrewAI** | Task delegation to a crew member | `HandoffContract` |
| **Semantic Kernel** | Plugin invocation | `HandoffContract` (capability_id = plugin name) |
| **OpenAI Agents SDK** | Tool call dispatch | `HandoffContract` (capability_id = tool name) |

**Python example:**

```python
from contextcore.contracts.a2a import HandoffContract, ExpectedOutput, validate_outbound

handoff = HandoffContract(
    handoff_id="h-001",
    from_agent="orchestrator",
    to_agent="specialist-agent",
    capability_id="analyze_data",              # your framework's function/tool name
    inputs={"query": "latency spike root cause"},
    expected_output=ExpectedOutput(type="analysis_report"),
)

# Validate before sending
payload = handoff.model_dump(mode="json", exclude_none=True)
validate_outbound("HandoffContract", payload)

# ... send via your framework's mechanism ...

# On the receiving side:
from contextcore.contracts.a2a import validate_inbound
validate_inbound("HandoffContract", received_payload)
```

### Step 3: Emit GateResult at transition points

Wherever your framework makes a go/no-go decision, emit a `GateResult`. This is where ContextCore adds the most value — catching failures early instead of at finalization.

| Framework | Transition point | Gate to emit |
|-----------|-----------------|--------------|
| **LangGraph** | Conditional edge evaluation | `GateResult` at edge decision |
| **LangGraph** | Checkpoint resume | `GateResult` verifying checkpoint integrity |
| **AutoGen** | Conversation termination check | `GateResult` on termination criteria |
| **CrewAI** | Guardrail check | `GateResult` mapping guardrail outcome |
| **LlamaIndex** | Retrieval confidence threshold | `GateResult` on confidence check |
| **Haystack** | Component output validation | `GateResult` on schema/quality check |
| **DSPy** | Optimization metric threshold | `GateResult` on score pass/fail |
| **Guidance/Outlines** | Schema validation result | `GateResult` on structured output validation |

**Python example (using built-in gates):**

```python
from contextcore.contracts.a2a import GateChecker

checker = GateChecker(trace_id="my-workflow")

# Use built-in gates
result = checker.check_checksum_chain(
    gate_id="integrity-check",
    task_id="step-3",
    expected_checksums={"source": "sha256:abc"},
    actual_checksums={"source": "sha256:abc"},
)

# Or create custom gates for framework-specific checks
from contextcore.contracts.a2a import GateResult, GateOutcome, GateSeverity, Phase
from datetime import datetime, timezone

custom_gate = GateResult(
    gate_id="retrieval-confidence",
    phase=Phase.INGEST_PARSE_ASSESS,
    result=GateOutcome.PASS if confidence > 0.7 else GateOutcome.FAIL,
    severity=GateSeverity.ERROR if confidence < 0.5 else GateSeverity.WARNING,
    reason=f"Retrieval confidence: {confidence}",
    next_action="Retry with broader query" if confidence < 0.7 else "Proceed",
    blocking=confidence < 0.5,
    checked_at=datetime.now(timezone.utc),
)
```

### Step 4: Add framework-specific lineage attributes

Attach optional attributes from the [Framework Interoperability Attributes](../agent-semantic-conventions.md#7-framework-interoperability-attributes-optional) section of the semantic conventions:

```python
# LangGraph example — add graph lineage to span attributes
span_attrs = {
    "graph.id": "checkout-workflow",
    "graph.node": "validate_order",
    "graph.edge": "order_valid -> process_payment",
    "graph.checkpoint_id": "cp-abc123",
}

# CrewAI example — add crew lineage
span_attrs = {
    "crew.id": "analysis-crew",
    "crew.role": "researcher",
    "crew.flow_step": "gather_data",
}

# LlamaIndex example — add RAG lineage
span_attrs = {
    "rag.phase": "retrieval",
    "rag.index_id": "product-docs-v2",
    "rag.retrieval_mode": "hybrid",
    "rag.retrieval_confidence": 0.89,
}
```

---

## What you get

After these 4 steps, you immediately have:

| Capability | How it works |
|------------|-------------|
| **Blocked-span detection** | Any phase that fails a gate is marked `blocked` with reason + next action |
| **Handoff validation** | Invalid payloads are caught before they reach the receiving agent |
| **Provenance tracking** | Checksum chain, mapping completeness, and gap parity are verified |
| **Operational dashboard** | The A2A governance dashboard shows blocked spans, gate failures, dropped artifacts |
| **Root-cause locality** | When something fails, you know *which span*, *which gate*, *why*, and *what to do next* |

---

## Framework-specific guides

For deeper integration patterns with concrete examples:

- [LangGraph Integration Pattern](LANGGRAPH_PATTERN.md) — graph nodes as spans, edges as gates, checkpoints as provenance
- More guides coming: AutoGen, CrewAI, Semantic Kernel, OpenAI Agents SDK

---

## Anti-patterns to avoid

| Don't | Why | Instead |
|-------|-----|---------|
| Duplicate runtime logic in ContextCore | Maintenance burden, version drift | Govern boundaries only |
| Add framework-specific fields to core contracts | Breaks interoperability | Use optional lineage attributes |
| Skip boundary validation "for speed" | Silent failures compound | Always validate outbound and inbound |
| Build custom gate logic for every framework | Reinventing the wheel | Use built-in gates; add custom gates only for domain-specific checks |
| Emit GateResult without `next_action` | Operators can't act on failures | Always include what to do next |
