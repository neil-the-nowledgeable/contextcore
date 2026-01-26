# Code Generation Rules

These rules apply when generating code for multiple features or making changes to the codebase.

## Rule 1: Integrate Immediately

**NEVER** batch multiple features for later integration. Each feature MUST be integrated and validated before starting the next.

```
✅ DO: Feature 1 → Integrate → Validate → Feature 2 → Integrate → Validate
❌ DON'T: Feature 1, Feature 2, Feature 3 → Integrate all → Fix conflicts
```

## Rule 2: Use Prime Contractor for Multiple Features

When generating more than one feature, use the Prime Contractor workflow:

```bash
python3 scripts/prime_contractor/cli.py run --import-backlog
```

This ensures:
- Features are integrated one at a time
- Conflicts are detected early
- Checkpoints validate each integration
- The mainline stays working

## Rule 3: Check for Overlapping Targets

Before generating a feature, check if it targets files modified by previous features:

```bash
python3 scripts/prime_contractor/cli.py status
```

If overlap exists, the Prime Contractor will handle merging appropriately.

## Rule 4: Stop on Failure

If integration or checkpoints fail:
1. STOP immediately
2. Fix the issue
3. Retry the feature
4. Only then proceed to the next feature

```bash
# After fixing the issue
python3 scripts/prime_contractor/cli.py retry feature_id
```

## Rule 5: Commit Atomically

Each feature should be committed separately, not batched:

```bash
# Use auto-commit for atomic commits
python3 scripts/prime_contractor/cli.py run --import-backlog --auto-commit
```

## Rule 6: Pre-Flight Size Validation

**ALWAYS** estimate output size BEFORE generating code. The Prime Contractor does this automatically, but when manually generating:

```python
from contextcore.agent.size_estimation import SizeEstimator

estimator = SizeEstimator()
estimate = estimator.estimate(
    task="Implement user authentication with OAuth2",
    inputs={"required_exports": ["AuthClient", "TokenManager"]}
)

if estimate.lines > 150:
    # Split into smaller tasks
    print(f"WARNING: Estimated {estimate.lines} lines exceeds safe limit")
```

**Safe limits:**
- 150 lines per file (most LLMs)
- 500 tokens per output
- 100 lines for complex logic

## Rule 7: Use CodeGenerationHandoff for A2A

For agent-to-agent code generation requests, use `CodeGenerationHandoff` instead of raw `HandoffManager`:

```python
from contextcore.agent.code_generation import (
    CodeGenerationHandoff,
    CodeGenerationSpec,
)

handoff = CodeGenerationHandoff(project_id="myproject", agent_id="orchestrator")

result = handoff.request_code(
    to_agent="code-generator",
    spec=CodeGenerationSpec(
        target_file="src/mymodule.py",
        description="Implement FooBar class",
        max_lines=150,  # Size constraint
        required_exports=["FooBar"],  # Completeness markers
    )
)
```

Benefits:
- Size constraints in handoff contract
- Pre-flight validation by receiver
- Decomposition coordination
- Verification spans for monitoring

## Rule 8: Monitor Code Generation Health

Check the Code Generation Health dashboard for:

1. **Truncation Rate**: Should be < 1%
2. **Decomposition Frequency**: High rates indicate scope issues
3. **Size Estimation Accuracy**: Estimated vs actual lines
4. **Failed Verifications**: Syntax errors, missing exports

TraceQL queries for diagnostics:
```traceql
# Find truncated generations
{ span.gen_ai.code.truncated = true }

# Check decomposition decisions
{ span.gen_ai.code.action = "decompose" }

# Verification failures
{ name = "code_generation.verify" && status = error }
```

## Anti-Patterns to Avoid

1. **Backlog Accumulation**: Generating many features without integration
2. **Skip Validation**: Proceeding without running checkpoints
3. **Big Bang Integration**: Integrating all features at once
4. **Ignoring Conflicts**: Hoping conflicts will resolve themselves
5. **Context Loss**: Generating features without knowledge of recent changes
6. **Warn-Then-Proceed**: Ignoring size warnings and generating anyway
7. **Generate-Complete-Module**: Generating large outputs without size checks
8. **Post-Hoc Validation Only**: Only validating after generation fails
9. **Silent Truncation**: Not recording truncation events in telemetry

## When in Doubt

If unsure whether to use Prime Contractor:
- More than 1 feature? → Use Prime Contractor
- Features might touch same files? → Use Prime Contractor
- Want to avoid manual merging? → Use Prime Contractor

The Prime Contractor is always safer. The only downside is slightly slower processing (one feature at a time), but this is far better than hours of manual conflict resolution.
