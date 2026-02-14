# OTel GenAI Semantic Conventions Adoption Plan

**Purpose:** Align ContextCore with OpenTelemetry GenAI semantic conventions using the startd8 SDK Lead Contractor Workflow for cost-efficient implementation.

**Date:** 2026-01-18
**Status:** Planning

---

## Executive Summary

ContextCore currently uses custom namespaces (`agent.*`, `insight.*`, `handoff.*`) for agent communication. The OTel community is standardizing GenAI observability via the `gen_ai.*` namespace ([PR #3249](https://github.com/open-telemetry/semantic-conventions/pull/3249), [GenAI spans spec](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md)).

This plan adopts OTel GenAI conventions while preserving ContextCore's unique project management focus, using the **Lead Contractor Workflow** for implementation.

---

## Workflow Configuration

```python
from startd8.workflows.builtin import LeadContractorWorkflow

workflow = LeadContractorWorkflow()

# Default configuration for all tasks
DEFAULT_CONFIG = {
    "lead_agent": "anthropic:claude-sonnet-4-20250514",
    "drafter_agent": "openai:gpt-4o-mini",
    "max_iterations": 3,
    "pass_threshold": 80,
}
```

**Estimated Total Cost:** $0.80 - $1.50 (7 tasks)

---

## Namespace Mapping Strategy

| Current ContextCore | OTel GenAI Equivalent | Action |
|---------------------|----------------------|--------|
| `agent.id` | `gen_ai.agent.id` (proposed) | Alias + new |
| `agent.type` | `gen_ai.agent.type` (proposed) | Alias + new |
| `agent.session_id` | `gen_ai.conversation.id` | Migrate |
| `insight.*` | Keep (ContextCore-specific) | Preserve |
| `handoff.*` | `gen_ai.tool.*` pattern | Partial align |
| `guidance.*` | Keep (ContextCore-specific) | Preserve |
| (new) | `gen_ai.operation.name` | Add |
| (new) | `gen_ai.provider.name` | Add |
| (new) | `gen_ai.request.model` | Add |

---

## Tasks for Lead Contractor Workflow

### Task 1: Gap Analysis Document (HIGH Priority)

**Description:** Analyze current ContextCore semantic conventions against OTel GenAI spec and produce detailed gap analysis.

```python
TASK_1 = {
    "task_description": """
    Analyze ContextCore's current semantic conventions against OTel GenAI conventions.

    INPUTS:
    - ContextCore conventions: docs/semantic-conventions.md, docs/agent-semantic-conventions.md
    - OTel GenAI spec: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md

    OUTPUT: Gap analysis document with:
    1. Attribute-by-attribute comparison table
    2. Exact mapping recommendations (alias, migrate, add, preserve)
    3. Breaking change assessment
    4. Migration complexity score (1-5) per attribute
    5. Recommended adoption order
    """,
    "context": {
        "contextcore_conventions": "docs/semantic-conventions.md",
        "agent_conventions": "docs/agent-semantic-conventions.md",
        "otel_spec_url": "https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md"
    },
    "output_format": "Markdown document with tables",
    "integration_instructions": "Save as docs/OTEL_GENAI_GAP_ANALYSIS.md"
}
```

**Acceptance Criteria:**
- [ ] All current ContextCore attributes mapped
- [ ] All relevant OTel GenAI attributes listed
- [ ] Clear recommendation per attribute
- [ ] Breaking changes identified

---

### Task 2: Dual-Emit Attribute Layer (HIGH Priority)

**Description:** Create compatibility layer that emits both old and new attribute names during migration.

```python
TASK_2 = {
    "task_description": """
    Implement a dual-emit compatibility layer for ContextCore that:

    1. Emits BOTH old (agent.*) and new (gen_ai.*) attributes during transition
    2. Is configurable via environment variable: CONTEXTCORE_EMIT_MODE=dual|legacy|otel
    3. Provides deprecation warnings when legacy attributes are queried
    4. Has zero performance overhead when mode=otel (future default)

    IMPLEMENTATION REQUIREMENTS:
    - Create src/contextcore/compat/otel_genai.py
    - Add attribute mapping registry
    - Hook into existing span emission code
    - Add unit tests for all three modes

    EXAMPLE:
    When emitting agent.id="claude-code", also emit gen_ai.agent.id="claude-code"
    """,
    "context": {
        "current_emitter": "src/contextcore/agent/insights.py",
        "tracker": "src/contextcore/tracker.py"
    },
    "output_format": "Python module with tests",
    "integration_instructions": "Integrate with InsightEmitter.emit() and TaskTracker.start_task()"
}
```

**Acceptance Criteria:**
- [ ] Three emit modes working (dual, legacy, otel)
- [ ] Environment variable controls mode
- [ ] Deprecation warnings functional
- [ ] Unit tests pass
- [ ] No performance regression

---

### Task 3: gen_ai.operation.name Support (HIGH Priority)

**Description:** Add operation name tracking to all ContextCore spans.

```python
TASK_3 = {
    "task_description": """
    Add gen_ai.operation.name attribute to all ContextCore span types.

    OPERATION MAPPINGS:
    - Task spans: operation.name = "task.{action}" (task.start, task.update, task.complete)
    - Insight spans: operation.name = "insight.emit"
    - Handoff spans: operation.name = "handoff.{status}" (handoff.request, handoff.complete)
    - Verification spans: operation.name = "install.verify"

    IMPLEMENTATION:
    - Update TaskTracker to emit gen_ai.operation.name
    - Update InsightEmitter to emit gen_ai.operation.name
    - Update HandoffManager to emit gen_ai.operation.name
    - Update InstallationVerifier to emit gen_ai.operation.name

    Must work with dual-emit layer from Task 2.
    """,
    "context": {
        "tracker": "src/contextcore/tracker.py",
        "insights": "src/contextcore/agent/insights.py",
        "handoff": "src/contextcore/agent/handoff.py",
        "verifier": "src/contextcore/install/verifier.py"
    },
    "output_format": "Code changes with tests",
    "integration_instructions": "Update semantic-conventions.md with new attributes"
}
```

**Acceptance Criteria:**
- [ ] All span types emit gen_ai.operation.name
- [ ] Operation names follow OTel conventions
- [ ] TraceQL queries work: `{ gen_ai.operation.name = "task.start" }`
- [ ] Documentation updated

---

### Task 4: gen_ai.provider.name and gen_ai.request.model (MEDIUM Priority)

**Description:** Track which LLM provider/model generated agent insights.

```python
TASK_4 = {
    "task_description": """
    Add provider and model tracking to insight spans.

    When an agent emits an insight, capture:
    - gen_ai.provider.name: "anthropic", "openai", "google", etc.
    - gen_ai.request.model: "claude-opus-4-5-20251101", "gpt-4o", etc.

    IMPLEMENTATION:
    - Add optional provider/model params to InsightEmitter
    - Auto-detect from environment if not provided (OTEL_SERVICE_NAME pattern)
    - Store in span attributes

    This enables queries like:
    - "Show me all decisions made by Claude Opus"
    - "Compare insight confidence by model"
    """,
    "context": {
        "insights": "src/contextcore/agent/insights.py",
        "models": "src/contextcore/agent/models.py"
    },
    "output_format": "Code changes with tests",
    "integration_instructions": "Add to CLI: contextcore insight emit --provider anthropic --model claude-opus-4-5"
}
```

**Acceptance Criteria:**
- [ ] Provider/model captured on insight spans
- [ ] Auto-detection works
- [ ] CLI updated
- [ ] Queryable via TraceQL

---

### Task 5: gen_ai.tool.* for Handoffs (MEDIUM Priority)

**Description:** Align handoff attributes with OTel tool execution conventions.

```python
TASK_5 = {
    "task_description": """
    Map ContextCore handoff attributes to OTel gen_ai.tool.* conventions.

    CURRENT → NEW MAPPING:
    - handoff.capability_id → gen_ai.tool.name
    - handoff.inputs → gen_ai.tool.call.arguments (JSON)
    - handoff.expected_output → (keep, no OTel equivalent)
    - handoff.status → gen_ai.tool.call.result (on completion)
    - (new) gen_ai.tool.type = "agent_handoff"
    - (new) gen_ai.tool.call.id = handoff.id

    IMPLEMENTATION:
    - Update HandoffManager to emit both old and new attributes
    - Use dual-emit layer from Task 2
    - Update handoff completion to record result
    """,
    "context": {
        "handoff": "src/contextcore/agent/handoff.py",
        "conventions": "docs/agent-semantic-conventions.md"
    },
    "output_format": "Code changes with tests",
    "integration_instructions": "Document tool.type='agent_handoff' as ContextCore extension"
}
```

**Acceptance Criteria:**
- [ ] Handoff spans include gen_ai.tool.* attributes
- [ ] Existing handoff.* attributes preserved (dual-emit)
- [ ] Tool type clearly identifies agent handoffs
- [ ] Documentation updated

---

### Task 6: gen_ai.conversation.id Migration (MEDIUM Priority)

**Description:** Migrate agent.session_id to gen_ai.conversation.id.

```python
TASK_6 = {
    "task_description": """
    Replace agent.session_id with gen_ai.conversation.id per OTel conventions.

    MIGRATION:
    - agent.session_id → gen_ai.conversation.id
    - Keep agent.session_id as alias during transition (dual-emit)
    - Update all code references
    - Update CLI commands
    - Update documentation

    The conversation.id represents the session/thread that groups related
    agent interactions, aligning with OTel's concept.
    """,
    "context": {
        "insights": "src/contextcore/agent/insights.py",
        "cli": "src/contextcore/cli.py"
    },
    "output_format": "Code changes with tests",
    "integration_instructions": "Add migration note to CHANGELOG"
}
```

**Acceptance Criteria:**
- [ ] gen_ai.conversation.id emitted
- [ ] agent.session_id aliased (dual-emit)
- [ ] CLI updated
- [ ] Docs updated
- [ ] Migration note in changelog

---

### Task 7: Updated Semantic Conventions Documentation (HIGH Priority)

**Description:** Comprehensive documentation update reflecting OTel alignment.

```python
TASK_7 = {
    "task_description": """
    Update ContextCore semantic conventions documentation to reflect OTel GenAI alignment.

    DOCUMENTATION UPDATES:
    1. docs/semantic-conventions.md:
       - Add "OTel GenAI Alignment" section
       - Document all gen_ai.* attributes used
       - Show mapping from ContextCore-specific to OTel

    2. docs/agent-semantic-conventions.md:
       - Update attribute tables with OTel equivalents
       - Add migration guide section
       - Update query examples to use gen_ai.* attributes

    3. New: docs/OTEL_GENAI_MIGRATION_GUIDE.md:
       - Step-by-step migration for existing users
       - Query migration examples (old → new)
       - Timeline for deprecation of legacy attributes

    TONE: Position ContextCore as "OTel GenAI conventions + project management extensions"
    """,
    "context": {
        "semantic_conventions": "docs/semantic-conventions.md",
        "agent_conventions": "docs/agent-semantic-conventions.md"
    },
    "output_format": "Markdown documents",
    "integration_instructions": "Link from README.md"
}
```

**Acceptance Criteria:**
- [ ] All docs updated with OTel alignment
- [ ] Migration guide complete
- [ ] Query examples updated
- [ ] Deprecation timeline documented

---

## Execution Script

```python
#!/usr/bin/env python3
"""
Execute OTel GenAI adoption tasks via Lead Contractor Workflow.

Usage:
    python scripts/adopt_otel_genai.py              # Run all tasks
    PRIORITY=HIGH python scripts/adopt_otel_genai.py  # Run HIGH priority only
    TASK=1 python scripts/adopt_otel_genai.py       # Run specific task
"""

import os
import json
from pathlib import Path
from startd8.workflows.builtin import LeadContractorWorkflow

# Task definitions from plan
TASKS = {
    1: {"priority": "HIGH", "name": "Gap Analysis", "config": TASK_1},
    2: {"priority": "HIGH", "name": "Dual-Emit Layer", "config": TASK_2},
    3: {"priority": "HIGH", "name": "Operation Name", "config": TASK_3},
    4: {"priority": "MEDIUM", "name": "Provider/Model", "config": TASK_4},
    5: {"priority": "MEDIUM", "name": "Tool Mapping", "config": TASK_5},
    6: {"priority": "MEDIUM", "name": "Conversation ID", "config": TASK_6},
    7: {"priority": "HIGH", "name": "Documentation", "config": TASK_7},
}

DEFAULT_CONFIG = {
    "lead_agent": "anthropic:claude-sonnet-4-20250514",
    "drafter_agent": "openai:gpt-4o-mini",
    "max_iterations": 3,
    "pass_threshold": 80,
}

def main():
    workflow = LeadContractorWorkflow()
    results_dir = Path("results/otel-genai-adoption")
    results_dir.mkdir(parents=True, exist_ok=True)

    priority_filter = os.environ.get("PRIORITY")
    task_filter = os.environ.get("TASK")

    for task_id, task in TASKS.items():
        # Apply filters
        if task_filter and str(task_id) != task_filter:
            continue
        if priority_filter and task["priority"] != priority_filter:
            continue

        print(f"\n{'='*60}")
        print(f"Task {task_id}: {task['name']} ({task['priority']})")
        print(f"{'='*60}")

        config = {**DEFAULT_CONFIG, **task["config"]}
        result = workflow.run(config=config)

        # Save result
        output_file = results_dir / f"task-{task_id}-{task['name'].lower().replace(' ', '-')}.json"
        with open(output_file, "w") as f:
            json.dump({
                "task_id": task_id,
                "name": task["name"],
                "priority": task["priority"],
                "success": result.success,
                "output": result.output,
                "metrics": {
                    "total_cost": result.metrics.get("total_cost"),
                    "iterations": result.metadata.get("iterations"),
                    "final_score": result.metadata.get("final_score"),
                }
            }, f, indent=2)

        status = "✅ PASSED" if result.success else "❌ FAILED"
        print(f"\nResult: {status}")
        print(f"Cost: ${result.metrics.get('total_cost', 0):.4f}")
        print(f"Output: {output_file}")

if __name__ == "__main__":
    main()
```

---

## Execution Order

| Phase | Tasks | Est. Cost | Outcome |
|-------|-------|-----------|---------|
| **1. Analysis** | Task 1 | $0.15 | Gap analysis document |
| **2. Foundation** | Task 2 | $0.20 | Dual-emit compatibility layer |
| **3. Core Attributes** | Tasks 3, 6 | $0.30 | Operation name + conversation ID |
| **4. Extended Attributes** | Tasks 4, 5 | $0.25 | Provider/model + tool mapping |
| **5. Documentation** | Task 7 | $0.15 | Updated docs + migration guide |

**Total Estimated Cost:** $1.05

---

## Success Metrics

1. **Compatibility**: Existing TraceQL queries continue to work (dual-emit)
2. **Standards Compliance**: OTel GenAI spec validation passes
3. **Query Parity**: All queries possible with both old and new attributes
4. **Documentation**: Users can migrate with clear guide
5. **Performance**: No measurable latency increase

---

## Timeline

| Week | Milestone |
|------|-----------|
| 1 | Tasks 1-2: Gap analysis + dual-emit layer |
| 2 | Tasks 3, 6: Core attribute migration |
| 3 | Tasks 4-5: Extended attributes |
| 4 | Task 7: Documentation + testing |
| 5 | Release v2.0 with OTel GenAI alignment |

---

## References

- [OTel GenAI Spans Spec](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md)
- [PR #3249: Invoke Workflow Operation](https://github.com/open-telemetry/semantic-conventions/pull/3249)
- [startd8 Lead Contractor Workflow](https://github.com/Force-Multiplier-Labs/startd8)
- [ContextCore Semantic Conventions](docs/semantic-conventions.md)
