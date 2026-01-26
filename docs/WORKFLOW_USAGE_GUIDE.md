# Workflow Usage Guide

This guide covers day-to-day usage of ContextCore's code generation and task management workflows.

## Quick Reference

```bash
# Check workflow status
python3 scripts/prime_contractor/cli.py status

# Import and run features
python3 scripts/prime_contractor/cli.py import
python3 scripts/prime_contractor/cli.py run

# Clear the queue (after issues)
python3 scripts/prime_contractor/cli.py clear --force
```

## Safe Workflow Patterns

### Pattern 1: Single Feature Integration

For one feature at a time (safest):

```bash
# 1. Import features
python3 scripts/prime_contractor/cli.py import

# 2. Check what will be processed
python3 scripts/prime_contractor/cli.py status

# 3. Run with max-features=1
python3 scripts/prime_contractor/cli.py run --max-features 1

# 4. Verify tests pass
python3 -m pytest tests/

# 5. Commit if successful
git add -A && git commit -m "feat: Integrate <feature_name>"
```

### Pattern 2: Batch Processing with Validation

For multiple features with checkpoints:

```bash
# 1. Dry run first
python3 scripts/prime_contractor/cli.py run --import-backlog --dry-run

# 2. Run with continue-on-failure to see all issues
python3 scripts/prime_contractor/cli.py run --continue-on-failure

# 3. Review results
python3 scripts/prime_contractor/cli.py status
```

### Pattern 3: Manual Integration (Most Control)

When automation fails, integrate manually:

```bash
# 1. Find the generated code
ls generated/phase*/

# 2. Review the code
cat generated/phase3/a2a/parts/parts_artifactmodel_code.py

# 3. Validate syntax
python3 -c "import ast; ast.parse(open('generated/...').read())"

# 4. Copy to target location (edit as needed)
cp generated/.../feature_code.py src/contextcore/...

# 5. Run tests
python3 -m pytest tests/

# 6. Commit
git add -A && git commit -m "feat: Manually integrate <feature>"
```

## Handling Common Issues

### Truncated Code

**Symptoms:** Code ends mid-function, missing closing braces, `...` placeholders

**Solution:**
```bash
# Regenerate with smaller scope
python3 scripts/lead_contractor/cli.py regenerate --feature-id FEATURE_ID --max-tokens 2000
```

Or decompose the feature into smaller tasks.

### Merge Corruption

**Symptoms:** Target file has duplicate code, syntax errors after merge

**Solution:**
```bash
# 1. Restore the file
git checkout -- src/contextcore/agent/affected_file.py

# 2. Run tests to confirm working state
python3 -m pytest tests/

# 3. Manually integrate the feature
```

### Import Errors

**Symptoms:** `ModuleNotFoundError: No module named 'contextcore.X'`

**Cause:** Generated code imports from modules that don't exist yet.

**Solution:**
1. Create the missing module (if needed)
2. Or skip the feature until dependencies are ready
3. Or modify the generated code to use existing modules

### Test Regressions

**Symptoms:** Tests that were passing now fail

**Solution:**
```bash
# 1. See what changed
git diff src/

# 2. Restore and manually review
git checkout -- src/contextcore/...

# 3. Apply changes more carefully
```

## Task Management

### Viewing Backlog

Tasks are tracked in Tempo traces. To view:

```bash
# Use contextcore-mole to scan task files
mole scan /path/to/task/files

# Or query Tempo directly (if running)
curl http://localhost:3200/api/search?q='{task.status="pending"}'
```

### Task Status Values

| Status | Meaning |
|--------|---------|
| `backlog` | Not started, low priority |
| `pending` | Ready to start |
| `in_progress` | Currently being worked on |
| `done` | Completed |
| `cancelled` | Abandoned |

### Prioritizing Tasks

Recommended priority order:

1. **Documentation tasks** - Zero risk, always safe
2. **New file creation** - No merge conflicts
3. **Config/folder structure** - File operations only
4. **Modifications to isolated modules** - Low conflict risk
5. **Modifications to shared modules** - High conflict risk, manual review

## Dashboard Provisioning

### Check Dashboard Status

```bash
# List provisioned dashboards
contextcore dashboards list

# Preview what would be provisioned
contextcore dashboards provision --dry-run
```

### Folder Structure

Dashboards are organized by extension pack:

```
grafana/provisioning/dashboards/
├── core/           # ContextCore core dashboards
├── beaver/         # LLM/code generation dashboards
├── squirrel/       # Skills library dashboards
├── rabbit/         # Alert automation dashboards
├── fox/            # Context enrichment dashboards
├── coyote/         # Multi-agent pipeline dashboards
├── owl/            # Grafana plugin dashboards
└── external/       # Third-party dashboards
```

### Creating New Dashboards

1. Create JSON file in appropriate folder
2. Use UID prefix matching the extension (e.g., `beaver-*` for beaver dashboards)
3. Restart Grafana or wait for auto-reload (30s)

## Environment Setup

### Required Environment Variables

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317
export GRAFANA_URL=http://localhost:3000
export GRAFANA_PASSWORD=admin  # or adminadminadmin for TEST env
```

### Two-Environment Setup

| Environment | Path | Grafana Password |
|-------------|------|------------------|
| DEV | `~/Documents/dev/ContextCore` | `admin` |
| TEST | `~/Documents/Deploy` | `adminadminadmin` |

Always verify which environment you're in before making changes.

## Troubleshooting Commands

```bash
# Check if tests pass
python3 -m pytest tests/ -v --tb=short

# Check syntax of all Python files
python3 -m py_compile src/contextcore/**/*.py

# Check imports
python3 -c "import contextcore; print('OK')"

# Reset git changes if needed
git checkout -- src/contextcore/

# View recent commits
git log --oneline -10
```

## See Also

- [PRIME_CONTRACTOR_WORKFLOW.md](PRIME_CONTRACTOR_WORKFLOW.md) - Prime Contractor details
- [CONFLICT_RESOLUTION_GUIDE.md](CONFLICT_RESOLUTION_GUIDE.md) - Handling merge conflicts
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) - Current known issues
