# Next Steps After Merge Analysis

This document outlines the recommended path forward after identifying the merge function issues.

## Current State

### Completed
- [x] Parts integration (manual) - `Artifact`, enhanced `Message` docstrings
- [x] Learning_Retriever integration (automated)
- [x] Backlog tasks BLC-010, BLC-011, DP-001, DP-008
- [x] Merge function issues documented

### Backlog Remaining

| Project | Tasks | Risk Level |
|---------|-------|------------|
| beaver-lead-contractor | 9 tasks (BLC-001 to BLC-009) | Mixed |
| dashboard-persistence | 41 tasks | Low-Medium |

## Decision Point: Fix Merge or Work Around?

### Option 1: Work Around (Faster, Lower Risk)

Continue with tasks that don't require the merge function:

**Safe to proceed now:**
- Documentation tasks (no code)
- New file creation (no merge needed)
- File/folder operations (DP-002 to DP-007)
- Config changes (DP-009)
- Tasks targeting isolated modules

**Must wait for merge fix:**
- Features modifying `parts.py`, `handoff.py`, `insights.py`
- Any feature where multiple generated files target the same destination

### Option 2: Fix Merge First (Slower, Enables Full Automation)

Implement AST-based merge before continuing:

**Effort:** ~2-4 hours
**Benefit:** Unlocks all backlog tasks for automation

## Recommended Path: Hybrid Approach

### Phase 1: Safe Tasks (Now)

Process tasks that don't need merge:

```bash
# Dashboard persistence - file operations
DP-002: Create extension folders
DP-003: Move core dashboards
DP-004: Move squirrel dashboards
DP-005: Move rabbit dashboards
DP-006: Move external dashboards
DP-007: Update dashboard UIDs
DP-009: Create multi-provider config
DP-014: Test Grafana reload
```

These are file system operations - create folders, move files, update configs. No Python merge needed.

### Phase 2: New Module Creation (Now)

Create new Python modules (no merge conflicts):

```bash
# New files - safe to automate
DP-015: Create discovery.py module (NEW FILE)
DP-037: Create persistence module (NEW FILE)
DP-038: Create detector.py (NEW FILE)
DP-056: Create exporter.py (NEW FILE)
DP-066: Create audit.py (NEW FILE)
```

### Phase 3: Beaver API Tasks (Now - Manual Integration)

The BLC-001 to BLC-003 tasks add API endpoints to Rabbit:

```bash
BLC-001: Add workflow run endpoint to Rabbit API
BLC-002: Implement workflow status endpoint
BLC-003: Add workflow history endpoint
```

If these target new files in contextcore-rabbit, they're safe. If they modify existing files, use manual integration.

### Phase 4: Fix Merge Function (When Needed)

Implement AST-based merge when we hit tasks that require it:

```python
# Minimal AST merge implementation
# scripts/lead_contractor/ast_merge.py

import ast
from pathlib import Path
from typing import Dict, List

def merge_python_files(sources: List[Path]) -> str:
    """Merge multiple Python files using AST."""

    all_imports = []
    all_classes: Dict[str, ast.ClassDef] = {}
    all_functions: Dict[str, ast.FunctionDef] = {}
    module_docstring = None

    for source in sources:
        tree = ast.parse(source.read_text())

        for node in tree.body:
            # Capture module docstring
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                if module_docstring is None:
                    module_docstring = node

            # Collect imports
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                all_imports.append(node)

            # Merge classes
            elif isinstance(node, ast.ClassDef):
                if node.name in all_classes:
                    # Merge methods into existing class
                    existing = all_classes[node.name]
                    existing_methods = {
                        n.name for n in existing.body
                        if isinstance(n, ast.FunctionDef)
                    }
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            if item.name not in existing_methods:
                                existing.body.append(item)
                else:
                    all_classes[node.name] = node

            # Collect functions
            elif isinstance(node, ast.FunctionDef):
                if node.name not in all_functions:
                    all_functions[node.name] = node

    # Build merged module
    body = []
    if module_docstring:
        body.append(module_docstring)

    # Deduplicate imports
    body.extend(deduplicate_imports(all_imports))

    # Add classes (sorted by dependency if possible)
    body.extend(all_classes.values())

    # Add functions
    body.extend(all_functions.values())

    merged = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(merged)

    return ast.unparse(merged)

def deduplicate_imports(imports: List[ast.stmt]) -> List[ast.stmt]:
    """Remove duplicate imports while preserving order."""
    seen = set()
    result = []
    for imp in imports:
        key = ast.dump(imp)
        if key not in seen:
            seen.add(key)
            result.append(imp)
    return result
```

### Phase 5: Modification Tasks (After Merge Fix)

Once AST merge is working:

```bash
# Provisioner updates
DP-023: Import discovery module
DP-024: Remove DEFAULT_DASHBOARDS
DP-025: Update provision_all method
DP-029: Update provisioner tests

# CLI modifications
DP-030: Add --extension flag to provision
DP-033: Add --source flag to list
DP-034: Create extensions command
```

## Execution Order

### Week 1: Safe Tasks

```bash
# Day 1: Dashboard folder structure
DP-002, DP-003, DP-004, DP-005, DP-006, DP-007

# Day 2: Config and testing
DP-008 (done), DP-009, DP-014

# Day 3-4: New module creation
DP-015, DP-037, DP-038
```

### Week 2: API and Merge Fix

```bash
# Day 1-2: Beaver API (manual if needed)
BLC-001, BLC-002, BLC-003

# Day 3: Implement AST merge
Create ast_merge.py, add tests, integrate

# Day 4-5: UI panels (may need merge)
BLC-004, BLC-005, BLC-006
```

### Week 3: Integration Tasks

```bash
# Provisioner updates (need merge)
DP-023, DP-024, DP-025, DP-029

# CLI enhancements
DP-030, DP-033, DP-034
```

## Task-by-Task Risk Assessment

### Low Risk (Proceed Now)

| Task | Description | Why Safe |
|------|-------------|----------|
| DP-002 | Create extension folders | File system only |
| DP-003-006 | Move dashboards | File system only |
| DP-009 | Multi-provider config | YAML file |
| DP-015 | Create discovery.py | New file |
| DP-037 | Create persistence module | New file |
| DP-038 | Create detector.py | New file |
| BLC-010 | Update CLAUDE.md | Done |
| BLC-011 | Workflow guide | Done |

### Medium Risk (Manual Integration)

| Task | Description | Risk Factor |
|------|-------------|-------------|
| BLC-001-003 | Rabbit API endpoints | Depends on target file |
| BLC-004-006 | UI panels | Depends on implementation |
| DP-016-020 | Discovery implementation | Methods in new module |

### High Risk (Need Merge Fix)

| Task | Description | Why Risky |
|------|-------------|-----------|
| DP-023 | Import discovery module | Modifies __init__.py |
| DP-024 | Remove DEFAULT_DASHBOARDS | Modifies provisioner.py |
| DP-025 | Update provision_all | Modifies provisioner.py |
| BLC-008 | Add insight emission | May modify insights.py |

## Monitoring Progress

Track completed tasks:

```bash
# Update mole task file after each completion
mole export /tmp/mole_tasks.txt --status done > completed.json

# Or query Tempo for task spans
curl "http://localhost:3200/api/search?q={task.status=\"done\"}"
```

## Success Criteria

### Phase 1 Complete When:
- [ ] All dashboard folders created and populated
- [ ] dashboards.yaml multi-provider config working
- [ ] Grafana reloads and shows dashboards in correct folders

### Phase 2 Complete When:
- [ ] discovery.py module created with tests
- [ ] persistence module created with tests
- [ ] All new modules importable without errors

### Phase 3 Complete When:
- [ ] AST merge function implemented
- [ ] Unit tests for merge scenarios passing
- [ ] Can merge two files with overlapping classes correctly

### Full Backlog Complete When:
- [ ] All 50+ tasks marked done
- [ ] 268+ tests still passing
- [ ] No manual merge interventions needed

## Commands Reference

```bash
# Check what's safe to do
python3 scripts/prime_contractor/cli.py status

# Process one task at a time (safest)
python3 scripts/prime_contractor/cli.py run --max-features 1

# Run tests after each integration
python3 -m pytest tests/ -q

# Restore if something breaks
git checkout -- src/contextcore/

# Manual integration
cp generated/path/to/feature.py src/contextcore/target/
python3 -m pytest tests/  # verify
git add -A && git commit -m "feat: Integrate <feature>"
```

## Next Action

**Recommended immediate next step:**

```bash
# Start with dashboard folder operations (DP-002 to DP-007)
# These are pure file system operations - zero merge risk
```

Would you like to proceed with these, or implement the AST merge fix first?
