# Known Issues and Fixes

This document catalogs known issues in the ContextCore codebase and their solutions.

## Table of Contents

- [Workflow Trigger Shows "0/N Steps"](#workflow-trigger-shows-0n-steps)
- [Prime Contractor Merge Corrupts Python Files](#prime-contractor-merge-corrupts-python-files)
- [Module Import Errors](#module-import-errors)
- [Example Code Executed at Import Time](#example-code-executed-at-import-time)
- [Missing Module Files](#missing-module-files)

---

## Workflow Trigger Shows "0/N Steps"

**Symptom:** The Grafana workflow trigger panel shows "0/8 steps" and completes in ~2 seconds without processing any features.

**Root Cause:** One of:
1. The first feature in the queue has a syntax/import error, causing immediate failure
2. All features are already marked as complete in the queue
3. The `generated/` directory has no `*_code.*` files

**Diagnosis:**
```bash
# Check feature queue status
python3 -c "
from scripts.prime_contractor.feature_queue import FeatureQueue
queue = FeatureQueue()
queue.print_status()
"

# Check for syntax errors in target files
python3 -m py_compile src/contextcore/agent/parts.py

# Check what features would run
curl -s -X POST http://localhost:8082/trigger \
  -H 'Content-Type: application/json' \
  -d '{"action": "beaver_workflow_dry_run", "payload": {"project_id": "contextcore"}}' | jq
```

**Fix:**
1. If syntax errors: Restore corrupted file from git or fix manually
2. If queue issues: Reset feature queue state
3. If no generated files: Run Lead Contractor first

```bash
# Restore corrupted file
git checkout src/contextcore/agent/parts.py

# Reset failed features to retry
python3 -c "
from scripts.prime_contractor.feature_queue import FeatureQueue, FeatureStatus
queue = FeatureQueue()
for fid, f in queue.features.items():
    if f.status == FeatureStatus.FAILED:
        f.status = FeatureStatus.GENERATED
        f.error_message = None
queue.save_state()
"
```

---

## Prime Contractor Merge Corrupts Python Files

**Symptom:** After running `python3 scripts/prime_contractor/cli.py run --import-backlog`, target Python files become syntactically invalid with:
- Imports scattered throughout the file
- Class definitions mixed with example code
- Missing decorators (@dataclass, @classmethod)
- Code outside class bodies

**Root Cause:** The `merge_files_intelligently()` function in `scripts/lead_contractor/integrate_backlog.py` incorrectly merges Python files by:
1. Extracting functions/classes without preserving structure
2. Mixing docstrings, imports, and code incorrectly
3. Including example code from generated files

**Affected Files:**
- `src/contextcore/agent/parts.py` (most common)
- Any file targeted by multiple generated features

**Fix:**

Option 1: Restore from git and mark features complete
```bash
# Restore the file
git checkout src/contextcore/agent/parts.py

# Mark affected features as complete
python3 -c "
from scripts.prime_contractor.feature_queue import FeatureQueue, FeatureStatus
queue = FeatureQueue()
for fid in ['parts_messagemodel', 'parts_partmodel', 'parts_artifactmodel', 'parts_modelspackage']:
    if fid in queue.features:
        queue.features[fid].status = FeatureStatus.COMPLETE
        queue.features[fid].error_message = 'Manually completed - merge function broken'
queue.save_state()
"
```

Option 2: Use generated source directly
```bash
# Copy clean generated file to target
cp generated/phase3/a2a/parts/parts_partmodel_code.py src/contextcore/agent/part.py

# Remove example code at end of file (lines after __all__)
```

**Long-term Fix:** The `merge_files_intelligently()` function needs to be rewritten to:
1. Parse Python AST properly
2. Preserve class/function structure
3. Exclude example code sections
4. Handle imports correctly

---

## Module Import Errors

### `from __future__ imports must occur at the beginning`

**Symptom:**
```
SyntaxError: from __future__ imports must occur at the beginning of the file
```

**Cause:** The merge process placed `from __future__ import annotations` after other imports.

**Fix:**
```python
# Move to immediately after the docstring
"""Module docstring."""

from __future__ import annotations  # Must be first!

from dataclasses import dataclass
# ... other imports
```

### `cannot import name 'X' from 'module'`

**Symptom:**
```
ImportError: cannot import name 'write_tests' from 'contextcore.generators.slo_tests'
```

**Cause:** The `__init__.py` exports a name that doesn't exist in the module.

**Fix:** Remove the non-existent import from `__init__.py`:
```python
# In src/contextcore/generators/__init__.py
# Remove 'write_tests' from imports and __all__
```

### `No module named 'contextcore.X.models'`

**Symptom:**
```
ModuleNotFoundError: No module named 'contextcore.discovery.models'
```

**Cause:** Import path references a non-existent file.

**Fix:** Update to correct path:
```python
# Wrong
from .models import AgentCard

# Correct
from .agentcard import AgentCard
```

### `NameError: name 'X' is not defined`

**Symptom:**
```
NameError: name 'MessageRole' is not defined
```

**Cause:** Class/enum referenced before it's defined (wrong order in file).

**Fix:** Reorder definitions so dependencies come first:
```python
# Define MessageRole BEFORE Message class
class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"

@dataclass
class Message:
    role: MessageRole = MessageRole.USER  # Now works
```

---

## Example Code Executed at Import Time

**Symptom:** Module import fails with errors like:
```
TypeError: AgentCard.__init__() missing 3 required positional arguments
```

**Cause:** Generated files contain example/demo code at module level that executes during import:
```python
# This runs at import time!
agent = AgentCard(name="MyAgent")  # Missing required args
endpoint = DiscoveryEndpoint(agent)
```

**Affected Files:**
- `src/contextcore/discovery/endpoint.py`
- `src/contextcore/compat/docs_unifiedupdate.py`

**Fix:** Remove or guard example code:

Option 1: Delete example code section
```bash
# Find and remove lines after the last class/function definition
```

Option 2: Guard with `if __name__ == "__main__":`
```python
if __name__ == "__main__":
    # Example code here - only runs when file is executed directly
    agent = AgentCard(...)
```

Option 3: Rename non-module files
```bash
mv src/contextcore/compat/docs_unifiedupdate.py \
   src/contextcore/compat/docs_unifiedupdate.py.example
```

---

## Missing Module Files

### `part.py` Missing (Part and PartType classes)

**Symptom:**
```
ModuleNotFoundError: No module named 'contextcore.agent.part'
```

**Cause:** The `parts.py` file expects to import from `part.py` which doesn't exist.

**Fix:** Create `src/contextcore/agent/part.py` with Part and PartType:
```bash
# Copy from generated source
cp generated/phase3/a2a/parts/parts_partmodel_code.py src/contextcore/agent/part.py

# Remove example code at the end (after __all__ = [...])
```

The file should contain:
- `PartType` enum (TEXT, FILE, TRACE, etc.)
- `Part` dataclass with factory methods

### `discovery/models.py` Missing

**Symptom:**
```
ModuleNotFoundError: No module named 'contextcore.discovery.models'
```

**Cause:** Import path is wrong - classes are in `agentcard.py`, not `models.py`.

**Fix:** Update `discovery/__init__.py`:
```python
# Change this:
from .models import AgentCard, AgentCapabilities, ...

# To this:
from .agentcard import AgentCard, AgentCapabilities, ...
```

---

## Quick Reference: Health Check Commands

```bash
# Check all critical modules import correctly
python3 -c "
import sys
sys.path.insert(0, 'src')
for mod in ['contextcore.agent.part', 'contextcore.agent.parts',
            'contextcore.agent.handoff', 'contextcore.generators',
            'contextcore.discovery']:
    try:
        __import__(mod)
        print(f'✓ {mod}')
    except Exception as e:
        print(f'✗ {mod}: {e}')
"

# Check syntax of a specific file
python3 -m py_compile src/contextcore/agent/parts.py

# Check workflow trigger health
curl -s http://localhost:8082/health

# View feature queue status
python3 -c "
from scripts.prime_contractor.feature_queue import FeatureQueue
FeatureQueue().print_status()
"
```

---

## Prevention

1. **Before running Prime Contractor:** Check that target files have no uncommitted changes
2. **After merge failures:** Always restore from git before retrying
3. **For multi-feature targets:** Consider integrating manually instead of using merge
4. **Test imports:** Run module health check after any integration

---

*Last updated: 2026-01-26*
