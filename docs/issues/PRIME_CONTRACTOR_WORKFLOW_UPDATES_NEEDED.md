# Prime Contractor Workflow Documentation - Updates Needed

> **STATUS: APPLIED (2026-01-27)**
>
> All suggested changes in this document have been applied to `docs/PRIME_CONTRACTOR_WORKFLOW.md`.
>
> **Changes applied:**
> - Fixed FeatureQueue API example (correct import path and parameters)
> - Added Truncation Prevention section
> - Added `validate`, `add`, `clear` command documentation
> - Added `--strict` flag documentation
> - Updated Basic Workflow to include validation step
> - Added comprehensive CLI Reference table
> - Added truncation troubleshooting entry
> - Updated Architecture section
>
> This file is preserved for audit purposes.
>
> ---

> **Author:** Claude Code (automated review)
> **Date:** 2026-01-27
> **Target File:** `docs/PRIME_CONTRACTOR_WORKFLOW.md`
> **Priority:** High (missing critical truncation prevention content)

---

## Executive Summary

The current documentation is approximately **75% accurate** but is missing critical content related to truncation prevention and several CLI commands. The core concepts and main workflow are correct, but users following this documentation would not know about important safety features.

---

## 1. Missing CLI Commands

### 1.1 `validate` Command (Critical)

**Why it matters:** This command detects truncated/corrupted generated code BEFORE integration. Without it, users may integrate incomplete code that causes syntax errors.

**Add to Usage section:**

```markdown
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
```

### 1.2 `add` Command

**Add to Usage section:**

```markdown
### Add Features Manually

Add features directly without importing from backlog:

```bash
python3 scripts/prime_contractor/cli.py add "My Feature" \
    --description "Implements authentication" \
    --depends-on auth_service \
    --target-files src/mymodule.py src/api.py
```
```

### 1.3 `clear` Command

**Add to Usage section:**

```markdown
### Clear the Queue

Remove all features from the queue:

```bash
# With confirmation prompt
python3 scripts/prime_contractor/cli.py clear

# Skip confirmation
python3 scripts/prime_contractor/cli.py clear --force
```
```

### 1.4 `--strict` Flag

**Add to the `run` command options:**

```markdown
### Strict Checkpoint Mode

```bash
# Fail on warnings, not just errors
python3 scripts/prime_contractor/cli.py run --import-backlog --strict
```
```

---

## 2. Inaccurate Code Example

### Current (Incorrect):

```python
from scripts.prime_contractor import FeatureQueue

queue = FeatureQueue()
queue.add_feature("auth_service", "Authentication Service")
queue.add_feature("user_api", "User API", dependencies=["auth_service"])
```

### Should Be:

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

**Changes:**
- Import path: `scripts.prime_contractor.feature_queue` (not `scripts.prime_contractor`)
- All parameters must be keyword arguments
- `description`, `dependencies`, and `target_files` are required parameters

---

## 3. Missing Section: Truncation Prevention

**Add new section after "Key Concepts":**

```markdown
## Truncation Prevention

Generated code may be truncated if the LLM hits its output token limit. The Prime Contractor has built-in protection against integrating corrupted code.

### Why Truncation Happens

- LLM output token limits (e.g., 4K-64K depending on model)
- Complex features that generate large amounts of code
- Network timeouts causing incomplete responses

### Symptoms of Truncated Code

- Unclosed code blocks (``` without closing ```)
- Incomplete class or function definitions
- Files ending mid-statement
- Missing expected sections (e.g., no `return` statement)
- Syntax errors after integration

### Pre-Integration Validation

**Always validate before integrating:**

```bash
# Step 1: Validate all generated files
python3 scripts/prime_contractor/cli.py validate

# Step 2: If all valid, proceed with integration
python3 scripts/prime_contractor/cli.py run --import-backlog
```

### Handling Truncated Files

If validation detects truncation:

1. **Regenerate with smaller scope**
   - Break the feature into multiple smaller features
   - Reduce the complexity of the task description

2. **Manually complete the code**
   - Open the truncated file
   - Complete the missing sections by hand
   - Re-run validation to confirm fix

3. **Remove from backlog**
   - Delete the truncated feature file
   - Skip the feature entirely

### Automatic Rejection

The integration process will automatically reject truncated files:

```
⛔ REJECTED: feature_auth_code.py is truncated
   • Unclosed code block detected
   Cannot integrate incomplete code.
```

This prevents corrupted code from entering your codebase.
```

---

## 4. Recommended Workflow Update

**Update the "Basic Workflow" section to include validation:**

### Current:

```bash
# Import features from Lead Contractor backlog and run
python3 scripts/prime_contractor/cli.py run --import-backlog
```

### Should Be:

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

---

## 5. Update CLI Reference Table

**Add comprehensive CLI reference:**

```markdown
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
```

---

## 6. Minor Updates

### 6.1 Update Troubleshooting Section

**Add new troubleshooting entry:**

```markdown
### "File is truncated and will be REJECTED"

The generated code is incomplete. This happens when the LLM hits its output token limit.

1. Run `validate` to see which files are affected
2. Either regenerate with smaller scope or manually complete the code
3. Re-run validation to confirm the fix
```

### 6.2 Update Architecture Section

**Add validate command to architecture:**

```markdown
scripts/prime_contractor/
├── __init__.py          # Package exports
├── workflow.py          # PrimeContractorWorkflow class
├── checkpoint.py        # IntegrationCheckpoint validation
├── feature_queue.py     # FeatureQueue management
└── cli.py              # Command-line interface
                         #   - run, status, validate, import
                         #   - add, retry, reset, clear
```

---

## Summary of Changes

| Section | Change Type | Priority |
|---------|-------------|----------|
| Add `validate` command | New content | **Critical** |
| Add `add` command | New content | Medium |
| Add `clear` command | New content | Low |
| Add `--strict` flag | New content | Medium |
| Fix FeatureQueue API example | Correction | Medium |
| Add Truncation Prevention section | New content | **Critical** |
| Update Basic Workflow | Enhancement | High |
| Add CLI Reference table | New content | High |
| Update Troubleshooting | Enhancement | Medium |

---

## Verification

After making these updates, verify by:

1. Running each documented command to confirm it works as described
2. Testing the code examples in a Python REPL
3. Following the "Basic Workflow" steps end-to-end

---

*This review was generated based on comparison of `docs/PRIME_CONTRACTOR_WORKFLOW.md` against the actual implementation in `scripts/prime_contractor/cli.py` and related files.*
