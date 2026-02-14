# Prime Contractor Framework README - Improvement Suggestions

**Document reviewed**: `startd8-sdk/src/startd8/contractors/README.md`
**Reviewer**: Claude (ContextCore session)
**Date**: 2026-01-27

---

## Executive Summary

The README is well-structured and documents the consolidation effectively. These suggestions aim to strengthen the document by adding missing context, improving discoverability, and capturing institutional knowledge that would otherwise be lost.

---

## Suggestions

### 1. Add a "Lessons Learned" Section

**What**: Add a dedicated section capturing the anti-patterns that motivated this consolidation.

**Why**: Future maintainers need to understand *why* certain decisions were made to avoid repeating past mistakes. The current README explains *what* was done but not the pain that led to it.

**Suggested content**:

```markdown
## Lessons Learned

### Anti-Patterns We Eliminated

| Anti-Pattern | Impact | Solution |
|--------------|--------|----------|
| Workflow embedded in application code | Couldn't test without full stack | Protocol-based design with standalone adapters |
| Bridge package (contextcore-startd8) | 583 LOC of glue code, extra maintenance | Single package with optional adapters |
| Hard dependencies on observability | Slow startup, complex testing | Standalone-first with optional enhancement |
| Script-style imports (`from scripts.xxx`) | Fragile, non-standard | Proper package structure (`from startd8.contractors`) |

### Key Insight

> The Prime Contractor pattern (generate → integrate → validate → repeat) is independent of observability.

This realization enabled the entire consolidation. When we stopped treating telemetry as a requirement and started treating it as an enhancement, the architecture became clear.
```

---

### 2. Add Concrete Migration Examples

**What**: Show before/after code for common migration scenarios.

**Why**: The current migration section is brief. Developers migrating existing code need copy-paste-ready examples.

**Suggested content**:

```markdown
## Migration Examples

### Migrating a ContextCore Script

**Before** (ContextCore-coupled):
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.prime_contractor.workflow import PrimeContractorWorkflow
from scripts.prime_contractor.feature_queue import FeatureQueue

workflow = PrimeContractorWorkflow(
    dry_run=False,
    auto_commit=True,
)
workflow.run()
```

**After** (startd8-native):
```python
from startd8.contractors import PrimeContractorWorkflow
from startd8.contractors.adapters.contextcore import ContextCoreInstrumentor

workflow = PrimeContractorWorkflow(
    instrumentor=ContextCoreInstrumentor(project_id="myproject"),
    dry_run=False,
    auto_commit=True,
)
workflow.run()
```

### Key Differences
- No `sys.path` manipulation
- Explicit instrumentor injection
- Same API, cleaner imports
```

---

### 3. Document the Cost Tracking Pattern

**What**: Add documentation for BLC-009 cost tracking capabilities.

**Why**: The workflow now tracks LLM costs (as seen in the modified workflow.py), but this isn't documented. Users need to know how to access and interpret cost data.

**Suggested content**:

```markdown
## Cost Tracking

The workflow tracks LLM usage costs across all features:

```python
result = workflow.run()
print(f"Total cost: ${result['total_cost_usd']:.4f}")
print(f"Input tokens: {result['total_input_tokens']}")
print(f"Output tokens: {result['total_output_tokens']}")
```

### Cost Attributes in Telemetry

When using ContextCoreInstrumentor, costs are emitted as span attributes:

| Attribute | Description |
|-----------|-------------|
| `gen_ai.usage.input_tokens` | Tokens sent to LLM |
| `gen_ai.usage.output_tokens` | Tokens received from LLM |
| `contextcore.cost.usd` | Cost in USD for this operation |
| `contextcore.cost.cumulative_usd` | Running total across workflow |
```

---

### 4. Add Troubleshooting Section

**What**: Document common failure modes and their solutions.

**Why**: Users will encounter issues. Proactive documentation reduces support burden and improves developer experience.

**Suggested content**:

```markdown
## Troubleshooting

### "No files were integrated"

**Cause**: Generated code exists but target paths couldn't be determined.

**Solutions**:
1. Check that `target_files` is set in the feature spec
2. Verify generated files exist in `generated/prime_contractor/{feature_id}/`
3. Run with `--dry-run` to preview integration paths

### "Validation failed: TRUNCATED"

**Cause**: LLM output was cut off mid-generation.

**Solutions**:
1. Split the feature into smaller tasks (fewer target files per feature)
2. Enable pre-flight estimation: the workflow will warn before generating
3. Use a model with higher output limits

### "Repository has uncommitted changes"

**Cause**: Git safety check preventing integration over dirty files.

**Solutions**:
1. Commit your changes: `git add . && git commit -m "WIP"`
2. Auto-stash: `--auto-stash` flag
3. Force proceed: `--allow-dirty` (not recommended)
```

---

### 5. Add Observability Integration Diagram

**What**: Visual showing how ContextCoreInstrumentor connects to the observability stack.

**Why**: The current diagram shows the protocol structure but not how telemetry flows to backends.

**Suggested content**:

```markdown
## Observability Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    PrimeContractorWorkflow                      │
│                              │                                   │
│                    ContextCoreInstrumentor                       │
│                              │                                   │
└──────────────────────────────┼───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      OpenTelemetry SDK                           │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                 │
│  │   Tracer   │  │   Meter    │  │   Logger   │                 │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘                 │
└────────┼───────────────┼───────────────┼────────────────────────┘
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │  Tempo  │    │  Mimir  │    │  Loki   │
    │ (spans) │    │(metrics)│    │ (logs)  │
    └─────────┘    └─────────┘    └─────────┘
```

### What Gets Emitted

| Signal | Examples |
|--------|----------|
| Spans | `code_generation.generate`, `code_generation.verify`, `prime_contractor.feature_cost` |
| Events | `feature_selected`, `integration_success`, `integration_failed` |
| Metrics | Cost per feature, tokens per workflow, integration duration |
```

---

### 6. Add "When NOT to Use" Section

**What**: Document scenarios where this framework isn't the right choice.

**Why**: Helps users self-select and prevents misuse.

**Suggested content**:

```markdown
## When NOT to Use Prime Contractor

| Scenario | Better Alternative |
|----------|--------------------|
| Single file generation | Use Lead Contractor directly |
| No integration needed (exploratory) | Use `run_workflow()` from `startd8.workflows` |
| Real-time streaming required | Use Agent SDK with streaming callbacks |
| Human-in-the-loop approval | Use review mode but consider custom workflow |

The Prime Contractor is designed for **batch code generation with immediate integration**. If your use case doesn't involve integrating generated code into a source tree, simpler alternatives exist.
```

---

### 7. Add Version History / Changelog Stub

**What**: Add a changelog section or link.

**Why**: Users upgrading need to know what changed between versions.

**Suggested content**:

```markdown
## Changelog

### v0.3.0 (2026-01-27)
- Consolidated from ContextCore scripts into startd8-sdk
- Added protocol-based design with pluggable adapters
- Added pre-flight size estimation (truncation prevention)
- Added git safety features (dirty check, auto-stash)
- Added cost tracking (BLC-009)
- Added insight emission (BLC-008)
- Deprecated contextcore-startd8 bridge package

### v0.2.0 (Previous)
- Initial implementation in ContextCore/scripts/prime_contractor/
```

---

## Summary of Suggestions

| # | Suggestion | Effort | Impact |
|---|------------|--------|--------|
| 1 | Add "Lessons Learned" section | Low | High - prevents repeating mistakes |
| 2 | Add concrete migration examples | Low | High - reduces migration friction |
| 3 | Document cost tracking | Low | Medium - surfaces hidden capability |
| 4 | Add troubleshooting section | Medium | High - reduces support burden |
| 5 | Add observability flow diagram | Low | Medium - clarifies integration |
| 6 | Add "When NOT to Use" section | Low | Medium - prevents misuse |
| 7 | Add changelog stub | Low | Medium - aids upgrades |

---

## Meta-Feedback

The README demonstrates strong technical writing:
- Clear problem/solution framing
- Good use of diagrams
- Practical code examples
- Protocol documentation with type hints

The suggestions above are enhancements, not corrections. The document is already effective; these would elevate it from "good documentation" to "institutional knowledge capture."
