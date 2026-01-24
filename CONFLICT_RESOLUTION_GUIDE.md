# Conflict Resolution Guide

This document outlines the remaining file conflicts that need to be reviewed and merged manually.

## Status

✅ **RESOLVED**: `src/contextcore/agent/parts.py` - Successfully merged 4 files into unified parts.py

## Remaining Conflicts

### 1. `src/contextcore/compat/otel_genai.py` (HIGH RISK - 60/100)

**Target File**: `src/contextcore/compat/otel_genai.py`

**Conflicting Source Files** (4 files):
- `generated/phase3/unified/phase4/otel_conversationid_code.py` (Feature: OTel_ConversationId)
- `generated/phase3/unified/phase7/otel_toolmapping_code.py` (Feature: OTel_ToolMapping)
- `generated/phase3/unified/phase7/foundation_gapanalysis_code.py` (Feature: Foundation_GapAnalysis)
- `generated/phase3/unified/phase7/foundation_dualemit_code.py` (Feature: Foundation_DualEmit)

**Conflict Details**:
- Risk Level: HIGH (60/100)
- Worst conflict: OTel_ConversationId vs OTel_ToolMapping
- Would remove classes: `InsightQuerier`, `InsightRecord`, `InsightsAPI`
- Would remove functions: `transform`, `query`, `emit`

**Current State**:
The current `otel_genai.py` file contains the dual-emit compatibility layer implementation, which is the correct foundation. The other files may contain:
- Conversation ID handling
- Tool mapping functionality
- Gap analysis utilities

**Merge Strategy**:
1. **Keep the current dual-emit layer** as the base (Foundation_DualEmit is already integrated)
2. **Review** the other 3 files to see if they add:
   - Conversation ID utilities that should be integrated
   - Tool mapping functions that complement the dual-emit layer
   - Gap analysis helpers that are still needed
3. **Integrate selectively** - add only the functions/classes that don't conflict with existing dual-emit functionality
4. **Test** after merging to ensure `transform_attributes()` and related functions still work

**Files to Review**:
```bash
# Current implementation
cat src/contextcore/compat/otel_genai.py

# Generated files to review
cat generated/phase3/unified/phase4/otel_conversationid_code.py
cat generated/phase3/unified/phase7/otel_toolmapping_code.py
cat generated/phase3/unified/phase7/foundation_gapanalysis_code.py
```

---

### 2. `src/contextcore/agent/handoff.py` (HIGH RISK - 65/100)

**Target File**: `src/contextcore/agent/handoff.py`

**Conflicting Source Files** (2 files):
- `generated/phase3/unified/phase2/api_handoffsapi_code.py` (Feature: State_InputRequest)
- `generated/phase3/a2a/state/state_enhancedstatus_code.py` (Feature: State_EnhancedStatus)

**Conflict Details**:
- Risk Level: HIGH (65/100)
- Worst conflict: State_InputRequest vs State_EnhancedStatus
- Would remove classes: `InputRequestManager`, `StorageBackend`, `InputRequest`
- Size difference: 56.8%

**Merge Strategy**:
1. **Examine both files** to understand what each provides:
   - State_InputRequest: Likely handles input request management
   - State_EnhancedStatus: Likely provides enhanced status tracking
2. **Determine if they're complementary** or truly conflicting:
   - If complementary: Merge both, ensuring no naming conflicts
   - If conflicting: Choose the more complete/feature-rich version
3. **Check current handoff.py** to see what's already there
4. **Preserve existing functionality** while integrating new features

**Files to Review**:
```bash
# Current implementation
cat src/contextcore/agent/handoff.py

# Generated files to review
cat generated/phase3/unified/phase2/api_handoffsapi_code.py
cat generated/phase3/a2a/state/state_enhancedstatus_code.py
```

---

### 3. `src/contextcore/install/installtracking_statefile.py` (LOW RISK - 10/100)

**Target File**: `src/contextcore/install/installtracking_statefile.py`

**Conflicting Source Files** (2 files):
- `generated/phase3/install_tracking/installtracking_statefile_code.py` (Feature: InstallTracking_StateFile)
- `generated/install_tracking/install_tracking/installtracking_statefile_code.py` (Feature: InstallTracking_StateFile)

**Conflict Details**:
- Risk Level: LOW (10/100)
- Size difference: 39.8%
- Both have same feature name, likely duplicates or versions

**Merge Strategy**:
1. **Compare file sizes** - the larger file is likely more complete
2. **Compare content** - check if one is a subset of the other
3. **Use the more complete version** - if they're truly duplicates, pick the one with more functionality
4. **Verify** the chosen file has all necessary functions for state file management

**Files to Review**:
```bash
# Current implementation
cat src/contextcore/install/installtracking_statefile.py

# Compare both generated files
wc -l generated/phase3/install_tracking/installtracking_statefile_code.py
wc -l generated/install_tracking/install_tracking/installtracking_statefile_code.py

# View differences
diff generated/phase3/install_tracking/installtracking_statefile_code.py \
     generated/install_tracking/install_tracking/installtracking_statefile_code.py
```

---

## Review Process

### Step 1: Analyze Each Conflict

For each conflict:

1. **Read the current target file** to understand what's already there
2. **Read all conflicting source files** to understand what they provide
3. **Identify**:
   - What functionality is unique to each file
   - What functionality overlaps
   - What functionality conflicts

### Step 2: Determine Merge Strategy

Choose one of these strategies:

- **Strategy A: Keep Current + Add Missing**
  - Keep the current file as-is
  - Add only missing functionality from other files
  - Best when current file is correct/complete

- **Strategy B: Merge Complementary Features**
  - Combine features from multiple files
  - Ensure no naming conflicts
  - Best when files provide different but related functionality

- **Strategy C: Replace with Best Version**
  - Choose the most complete/correct version
  - Replace current file entirely
  - Best when files are duplicates or one is clearly superior

- **Strategy D: Manual Integration**
  - Manually combine code from multiple files
  - Resolve conflicts line-by-line
  - Best for complex conflicts with overlapping functionality

### Step 3: Execute Merge

1. **Create backup** of current file:
   ```bash
   cp src/contextcore/compat/otel_genai.py src/contextcore/compat/otel_genai.py.backup
   ```

2. **Apply merge** using chosen strategy

3. **Clean up**:
   - Remove markdown code blocks if present
   - Fix imports (relative vs absolute)
   - Ensure proper `__all__` exports
   - Fix any syntax errors

### Step 4: Verify

1. **Run syntax check**:
   ```bash
   python3 -m py_compile src/contextcore/compat/otel_genai.py
   ```

2. **Run tests**:
   ```bash
   python3 -m pytest tests/ -k "otel_genai" -v
   ```

3. **Check imports**:
   ```bash
   python3 -c "from contextcore.compat.otel_genai import transform_attributes; print('✓ Import successful')"
   ```

---

## Tools Available

### Conflict Analysis Script
```bash
python3 scripts/lead_contractor/analyze_conflicts.py
```

### Interactive Conflict Resolution
```bash
python3 scripts/lead_contractor/run_integrate_backlog_workflow.py --interactive-conflicts
```

### File Comparison
```bash
# Compare two files
diff -u file1.py file2.py

# View file stats
python3 -c "
from pathlib import Path
from scripts.lead_contractor.integrate_backlog import analyze_file_content
analysis = analyze_file_content(Path('path/to/file.py'))
print(f'Size: {analysis[\"size\"]:,} bytes')
print(f'Lines: {analysis[\"lines\"]:,}')
print(f'Classes: {list(analysis[\"classes\"])}')
print(f'Functions: {list(analysis[\"functions\"])}')
"
```

---

## Priority Order

1. **HIGH PRIORITY**: `otel_genai.py` - Critical for OTel GenAI compatibility
2. **HIGH PRIORITY**: `handoff.py` - Core agent communication functionality
3. **LOW PRIORITY**: `installtracking_statefile.py` - Installation tracking (can be deferred)

---

## After Merging

Once all conflicts are resolved:

1. **Run full test suite**:
   ```bash
   python3 -m pytest tests/ -v
   ```

2. **Verify integration**:
   ```bash
   python3 scripts/lead_contractor/integrate_backlog.py --list
   ```

3. **Commit changes**:
   ```bash
   git add src/contextcore/
   git commit -m "Resolve file conflicts: merge parts.py, otel_genai.py, handoff.py, installtracking_statefile.py"
   ```

---

## Notes

- All generated files are in `generated/` directory
- Current implementations are in `src/contextcore/`
- Backups are created with `.backup` extension
- Use the interactive conflict resolution workflow for guided merging
- When in doubt, preserve existing functionality and add new features incrementally
