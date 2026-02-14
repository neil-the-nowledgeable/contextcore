# Prime Contractor Workflow

The Prime Contractor workflow wraps the Lead Contractor workflow to ensure **continuous integration** of features, preventing the "backlog integration nightmare" where multiple features developed in isolation create merge conflicts and regressions.

## The Problem

When using the Lead Contractor workflow without continuous integration:

1. Multiple features are generated and sit in a backlog
2. Each feature may modify the same files
3. Later features are developed without knowledge of earlier (unintegrated) changes
4. When all features are integrated at once, conflicts arise:
   - Same file modified by multiple features
   - Changes overwrite each other
   - Manual merging required
   - Potential regressions introduced

**This is exactly what happened** when the lead contractor workflow was run repeatedly without integration, resulting in multiple changes to the same files that required careful manual merging.

## The Solution: Prime Contractor

The Prime Contractor acts as a "general contractor" that:

1. **Integrates Immediately**: Each feature is integrated right after generation
2. **Validates with Checkpoints**: Code must pass all checks before the next feature starts
3. **Fails Fast**: Stops the pipeline if integration fails
4. **Keeps Mainline Working**: The main codebase is always in a working state

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PRIME CONTRACTOR WORKFLOW                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│  │ Feature  │───▶│ Generate │───▶│Integrate │───▶│Checkpoint│       │
│  │    1     │    │  (Lead)  │    │  (Prime) │    │  Validate│       │
│  └──────────┘    └──────────┘    └──────────┘    └────┬─────┘       │
│                                                       │              │
│                    ┌──────────────────────────────────┘              │
│                    │                                                 │
│                    ▼ PASS                                            │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│  │ Feature  │───▶│ Generate │───▶│Integrate │───▶│Checkpoint│       │
│  │    2     │    │  (Lead)  │    │  (Prime) │    │  Validate│       │
│  └──────────┘    └──────────┘    └──────────┘    └────┬─────┘       │
│                                                       │              │
│                    ┌──────────────────────────────────┘              │
│                    │                                                 │
│                    ▼ PASS                                            │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│  │ Feature  │───▶│ Generate │───▶│Integrate │───▶│Checkpoint│       │
│  │    3     │    │  (Lead)  │    │  (Prime) │    │  Validate│       │
│  └──────────┘    └──────────┘    └──────────┘    └────┬─────┘       │
│                                                       │              │
│                                                       ▼ PASS         │
│                                              ┌──────────────┐        │
│                                              │   COMPLETE   │        │
│                                              └──────────────┘        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Concepts

### 1. Feature Queue

Features are processed in order, with dependency tracking:

```python
from scripts.prime_contractor.feature_queue import FeatureQueue

queue = FeatureQueue()
queue.add_feature(
    feature_id="auth_service",
    name="Authentication Service",
    description="Handles user authentication",
    dependencies=[],
    target_files=["src/auth.py"]
)
queue.add_feature(
    feature_id="user_api",
    name="User API",
    description="User management endpoints",
    dependencies=["auth_service"],
    target_files=["src/api/users.py"]
)
```

### 2. Integration Checkpoints

Each feature must pass checkpoints before the next can start:

- **Syntax Check**: All files have valid Python syntax
- **Import Check**: All imports can be resolved
- **Lint Check**: No critical lint errors
- **Test Check**: No test regressions (tests that were passing now fail)

### 3. Conflict Detection

The Prime Contractor detects potential conflicts BEFORE they happen:

```
⚠️  POTENTIAL CONFLICTS DETECTED:
   2 target(s) have multiple features:
   • src/contextcore/agent/handoff.py:
     - State_InputRequest
     - State_EnhancedStatus
```

### 4. Fail Fast

If a checkpoint fails, the workflow stops immediately:

```
✗ Checkpoint(s) failed - must fix before continuing

STOPPING: Feature 'State_InputRequest' failed integration
Fix the issue and re-run to continue
```

### 5. Truncation Prevention

Generated code may be truncated if the LLM hits its output token limit. The Prime Contractor has built-in protection against integrating corrupted code.

**Why Truncation Happens:**
- LLM output token limits (e.g., 4K-64K depending on model)
- Complex features that generate large amounts of code
- Network timeouts causing incomplete responses

**Symptoms of Truncated Code:**
- Unclosed code blocks (``` without closing ```)
- Incomplete class or function definitions
- Files ending mid-statement
- Missing expected sections (e.g., no `return` statement)

**Pre-Integration Validation:**

Always validate before integrating:

```bash
# Step 1: Validate all generated files
python3 scripts/prime_contractor/cli.py validate

# Step 2: If all valid, proceed with integration
python3 scripts/prime_contractor/cli.py run --import-backlog
```

**Handling Truncated Files:**

1. **Regenerate with smaller scope** - Break the feature into smaller features
2. **Manually complete the code** - Open the truncated file and complete it
3. **Remove from backlog** - Delete the truncated feature file and skip it

The integration process will automatically reject truncated files:

```
⛔ REJECTED: feature_auth_code.py is truncated
   • Unclosed code block detected
   Cannot integrate incomplete code.
```

## Usage

### Basic Workflow

```bash
# Step 1: Import features from backlog
python3 scripts/prime_contractor/cli.py import

# Step 2: Validate for truncation (IMPORTANT)
python3 scripts/prime_contractor/cli.py validate

# Step 3: Check queue status
python3 scripts/prime_contractor/cli.py status

# Step 4: Run integration
python3 scripts/prime_contractor/cli.py run

# Or all at once (validation happens automatically during integration):
python3 scripts/prime_contractor/cli.py run --import-backlog
```

### Dry Run (Preview)

```bash
# Preview what would happen without making changes
python3 scripts/prime_contractor/cli.py run --import-backlog --dry-run
```

### Process Limited Features

```bash
# Process only 3 features at a time
python3 scripts/prime_contractor/cli.py run --import-backlog --max-features 3
```

### Auto-Commit Each Feature

```bash
# Commit each feature after successful integration
python3 scripts/prime_contractor/cli.py run --import-backlog --auto-commit
```

### Continue on Failure

```bash
# Don't stop if a feature fails (not recommended)
python3 scripts/prime_contractor/cli.py run --import-backlog --continue-on-failure
```

### Retry Failed Features

```bash
# After fixing issues, retry a specific feature
python3 scripts/prime_contractor/cli.py retry state_inputrequest
```

### Reset Failed Features

```bash
# Reset all failed features to try again
python3 scripts/prime_contractor/cli.py reset

# Reset ALL features to pending
python3 scripts/prime_contractor/cli.py reset --all
```

### Validate Generated Code

Before integrating, check for truncated or incomplete files:

```bash
# Validate all generated files in backlog
python3 scripts/prime_contractor/cli.py validate

# Validate a specific file
python3 scripts/prime_contractor/cli.py validate --file generated/my_feature_code.py

# Show details for all files (including valid ones)
python3 scripts/prime_contractor/cli.py validate --verbose
```

Example output:
```
======================================================================
VALIDATING GENERATED CODE
======================================================================

❌ feature_auth_code.py: TRUNCATED
   • TRUNCATED: Unclosed code block (``` without closing ```)

✓ feature_api_code.py: OK

======================================================================
VALIDATION SUMMARY
======================================================================
  ✓ Valid:     1
  ❌ Truncated: 1

⛔ 1 file(s) are truncated and will be REJECTED during integration.
```

### Add Features Manually

Add features directly without importing from backlog:

```bash
python3 scripts/prime_contractor/cli.py add "My Feature" \
    --description "Implements authentication" \
    --depends-on auth_service \
    --target-files src/mymodule.py src/api.py
```

### Clear the Queue

Remove all features from the queue:

```bash
# With confirmation prompt
python3 scripts/prime_contractor/cli.py clear

# Skip confirmation
python3 scripts/prime_contractor/cli.py clear --force
```

### Strict Checkpoint Mode

```bash
# Fail on warnings, not just errors
python3 scripts/prime_contractor/cli.py run --import-backlog --strict
```

## Comparison: Lead Contractor vs Prime Contractor

| Aspect | Lead Contractor Only | Prime Contractor |
|--------|---------------------|------------------|
| Integration timing | All at once (batch) | After each feature |
| Conflict detection | After all generated | Before integration |
| Regression risk | High | Low |
| Recovery from failure | Manual merge required | Fix and retry |
| Mainline state | May be broken | Always working |
| Commit granularity | One big commit | Per-feature commits |

## CLI Reference

| Command | Description |
|---------|-------------|
| `run` | Run the Prime Contractor workflow |
| `run --import-backlog` | Import from backlog first, then run |
| `run --dry-run` | Preview without making changes |
| `run --auto-commit` | Commit each feature after integration |
| `run --max-features N` | Process at most N features |
| `run --continue-on-failure` | Don't stop on failures |
| `run --strict` | Fail on warnings, not just errors |
| `status` | Show queue status |
| `status --verbose` | Show additional details |
| `validate` | Check generated files for truncation |
| `validate --file PATH` | Validate specific file |
| `validate --verbose` | Show all files, not just problems |
| `import` | Import features from Lead Contractor backlog |
| `add NAME` | Add a feature manually |
| `add --description TEXT` | Set feature description |
| `add --depends-on ID...` | Set dependencies |
| `add --target-files PATH...` | Set target files |
| `retry FEATURE_ID` | Retry a failed feature |
| `retry --dry-run` | Preview retry without executing |
| `reset` | Reset failed features to pending |
| `reset --all` | Reset ALL features to pending |
| `clear` | Clear the entire queue |
| `clear --force` | Clear without confirmation |

## Architecture

```
scripts/prime_contractor/
├── __init__.py          # Package exports
├── workflow.py          # PrimeContractorWorkflow class
├── checkpoint.py        # IntegrationCheckpoint validation
├── feature_queue.py     # FeatureQueue management
└── cli.py              # Command-line interface
                         #   - run, status, validate, import
                         #   - add, retry, reset, clear
```

### PrimeContractorWorkflow

The main orchestrator that:
- Imports features from Lead Contractor backlog
- Processes features one at a time
- Runs checkpoints after each integration
- Tracks integration history for conflict detection

### IntegrationCheckpoint

Validates integrated code:
- Syntax validation (py_compile)
- Import resolution
- Lint checks (ruff)
- Test regression detection

### FeatureQueue

Manages the feature pipeline:
- Tracks feature status (pending → developing → integrating → complete)
- Enforces dependency ordering
- Blocks dependent features when integration fails
- Persists state for resume capability

## Best Practices

### 1. Always Use Prime Contractor for Multiple Features

If you're generating more than one feature, use the Prime Contractor:

```bash
# DON'T: Generate all, then integrate all
python3 scripts/lead_contractor/run_all.py
python3 scripts/lead_contractor/run_integrate_backlog_workflow.py

# DO: Use Prime Contractor for continuous integration
python3 scripts/prime_contractor/cli.py run --import-backlog
```

### 2. Review Potential Conflicts Early

Before running, check for conflicts:

```bash
python3 scripts/prime_contractor/cli.py import
python3 scripts/prime_contractor/cli.py status
```

### 3. Fix Issues Before Continuing

When a checkpoint fails, fix the issue before proceeding:

```bash
# 1. See what failed
python3 scripts/prime_contractor/cli.py status

# 2. Fix the issue in the generated code

# 3. Retry the feature
python3 scripts/prime_contractor/cli.py retry failed_feature_id
```

### 4. Use Auto-Commit for Audit Trail

Auto-commit creates a clear history of what changed:

```bash
python3 scripts/prime_contractor/cli.py run --import-backlog --auto-commit
```

This creates commits like:
```
feat: Integrate State_InputRequest
feat: Integrate State_EnhancedStatus
feat: Integrate OTel_ConversationId
```

## Troubleshooting

### "No features to process"

The queue is empty. Import from backlog:

```bash
python3 scripts/prime_contractor/cli.py import
```

### "Feature blocked by failed dependency"

A dependency failed. Fix and retry the dependency first:

```bash
python3 scripts/prime_contractor/cli.py status  # See which failed
python3 scripts/prime_contractor/cli.py retry dependency_id
```

### "Checkpoint failed: Import errors"

The integrated code has import issues. Check:
1. Missing imports in the generated file
2. Circular imports
3. Missing dependencies

### "Checkpoint failed: Test regressions"

Tests that were passing now fail. This means the integration broke something:
1. Review what the feature changed
2. Check if it overwrote existing functionality
3. Merge manually if needed

### "File is truncated and will be REJECTED"

The generated code is incomplete. This happens when the LLM hits its output token limit.

1. Run `validate` to see which files are affected
2. Either regenerate with smaller scope or manually complete the code
3. Re-run validation to confirm the fix

```bash
# See what's truncated
python3 scripts/prime_contractor/cli.py validate

# After fixing, verify
python3 scripts/prime_contractor/cli.py validate --verbose
```

## Related Documentation

- [CONFLICT_RESOLUTION_GUIDE.md](../CONFLICT_RESOLUTION_GUIDE.md) - Manual conflict resolution
- [WORKFLOW_ADJUSTMENTS_AFTER_CONFLICT_RESOLUTION.md](../WORKFLOW_ADJUSTMENTS_AFTER_CONFLICT_RESOLUTION.md) - Lead Contractor improvements
- [INTEGRATION_WORKFLOW_IMPROVEMENTS.md](../INTEGRATION_WORKFLOW_IMPROVEMENTS.md) - Integration workflow enhancements
