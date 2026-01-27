# TUI Lead Contractor Script - Error Fixes

## Summary

Fixed multiple potential error conditions in `scripts/run_lead_contractor_tui.py` to ensure robust handling of startd8 SDK workflow results.

## Fixes Applied

### 1. Workflow Result Handling (`run_workflow` function)

**Issue:** Direct access to `result.output.get()` could fail if `result.output` is `None`.

**Fix:** Added defensive checks:
- Check if `result` is `None` before accessing attributes
- Safely extract `output` with fallback to empty dict
- Safely extract `metrics.total_cost` with try/except
- Safely extract `metadata` with type checking

```python
# Before (could fail):
"final_implementation": result.output.get("final_implementation", "")

# After (safe):
output = result.output if (hasattr(result, 'output') and result.output) else {}
"final_implementation": output.get("final_implementation", "") if isinstance(output, dict) else ""
```

### 2. Code Extraction (`extract_code_blocks` function)

**Issue:** Could fail on malformed input or regex errors.

**Fix:** Added:
- Input validation (check if text is string)
- Try/except around regex operations
- Skip malformed matches gracefully
- Return empty list on errors

### 3. File Saving (`save_result` function)

**Issue:** Could fail on file I/O errors or missing keys.

**Fix:** Added:
- Try/except around each file operation
- Safe key access with `.get()` and defaults
- Type checking before string operations
- Graceful error messages for each failure point

### 4. Main Loop Error Handling

**Issue:** Exceptions could crash the entire script.

**Fix:** Added:
- Check if `result` is `None` before using
- Catch exceptions and add failed result to list
- Continue processing remaining features even if one fails

## Error Scenarios Now Handled

1. ✅ **startd8 SDK not found** - Returns error dict, doesn't crash
2. ✅ **Workflow returns None** - Handled gracefully
3. ✅ **result.output is None** - Falls back to empty dict
4. ✅ **result.metrics is None** - Returns 0 for cost
5. ✅ **result.metadata is None** - Returns 0 for iterations
6. ✅ **Malformed code blocks** - Skips and continues
7. ✅ **File I/O errors** - Prints error, continues
8. ✅ **Missing dictionary keys** - Uses `.get()` with defaults
9. ✅ **Type errors** - Validates types before operations
10. ✅ **Regex errors** - Catches and returns empty list

## Testing Recommendations

Before running the script, verify:

1. **startd8 SDK is installed:**
   ```bash
   ls -la $STARTD8_SDK_ROOT/src  # Set via: source ~/Documents/dev/contextcore-beaver/env.sh
   ```

2. **API keys are set:**
   ```bash
   env | grep -E "(ANTHROPIC|OPENAI)"
   ```

3. **Dependencies are installed:**
   ```bash
   source .venv/bin/activate
   pip3 list | grep -E "(anthropic|openai)"
   ```

## Usage

The script is now robust and will handle errors gracefully:

```bash
cd ~/Documents/dev/ContextCore
source .venv/bin/activate

# Run all features (will continue even if one fails)
python3 scripts/run_lead_contractor_tui.py

# Run specific feature
python3 scripts/run_lead_contractor_tui.py 1
```

## Output

All errors are logged but don't stop execution:
- Failed features are logged with error messages
- Successful features continue to be processed
- Summary shows success/failure counts
- Generated files are saved even if some fail
