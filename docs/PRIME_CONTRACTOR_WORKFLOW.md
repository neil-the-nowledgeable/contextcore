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
from scripts.prime_contractor import FeatureQueue

queue = FeatureQueue()
queue.add_feature("auth_service", "Authentication Service")
queue.add_feature("user_api", "User API", dependencies=["auth_service"])
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

## Usage

### Basic Workflow

```bash
# Import features from Lead Contractor backlog and run
python3 scripts/prime_contractor/cli.py run --import-backlog

# Or step by step:
python3 scripts/prime_contractor/cli.py import
python3 scripts/prime_contractor/cli.py status
python3 scripts/prime_contractor/cli.py run
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

## Architecture

```
scripts/prime_contractor/
├── __init__.py          # Package exports
├── workflow.py          # PrimeContractorWorkflow class
├── checkpoint.py        # IntegrationCheckpoint validation
├── feature_queue.py     # FeatureQueue management
└── cli.py              # Command-line interface
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

## Related Documentation

- [CONFLICT_RESOLUTION_GUIDE.md](../CONFLICT_RESOLUTION_GUIDE.md) - Manual conflict resolution
- [WORKFLOW_ADJUSTMENTS_AFTER_CONFLICT_RESOLUTION.md](../WORKFLOW_ADJUSTMENTS_AFTER_CONFLICT_RESOLUTION.md) - Lead Contractor improvements
- [INTEGRATION_WORKFLOW_IMPROVEMENTS.md](../INTEGRATION_WORKFLOW_IMPROVEMENTS.md) - Integration workflow enhancements
