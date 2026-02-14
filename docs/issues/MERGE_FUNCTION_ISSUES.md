# Merge Function Issues and Fixes

> **Status: RESOLVED** (2026-01-26) - AST-based merge implemented and deployed.

## Resolution Summary

The text-based `merge_files_intelligently()` function has been replaced with an AST-based implementation that correctly handles Python file structure. The fix:

- **New module**: `scripts/lead_contractor/ast_merge.py` (666 lines)
- **Test suite**: `tests/test_ast_merge.py` (42 tests, all passing)
- **Feature flag**: `CONTEXTCORE_AST_MERGE=false` to disable if needed
- **Python compatibility**: Tested on Python 3.14 (uses `ast.Constant`, not deprecated `ast.Str`)

## Original Problem Summary

The Lead Contractor's merge function corrupted files when multiple generated features target the same file. This was discovered when integrating the `Parts_*` features (parts_messagemodel, parts_partmodel, parts_artifactmodel), which all targeted `src/contextcore/agent/parts.py`.

## What Happened

1. Three features were generated, each producing code for `parts.py`
2. The merge function attempted to combine them
3. The resulting file had syntax errors, duplicate code, and missing sections
4. Manual restoration from git was required

## Root Causes

### 1. Naive Text-Based Parsing

**Location:** `scripts/lead_contractor/merge_conflicts.py:18` (`merge_parts_files`)

The function uses line-by-line text parsing instead of Python's AST:

```python
# Current approach (broken)
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('class '):
        # ... extract class
```

**Problems:**
- Doesn't handle decorators (`@dataclass`, `@classmethod`)
- Breaks on multi-line strings and docstrings
- Misidentifies end of class (checks for non-indented lines, but comments/blank lines confuse it)
- Doesn't preserve method order or relationships

### 2. Class Extraction Heuristics Fail

The function tries to detect "end of class" by finding non-indented lines:

```python
if stripped and not stripped.startswith(' ') and not stripped.startswith('\t'):
    if not stripped.startswith('@') and not stripped.startswith('class '):
        # End of class (WRONG - this triggers on comments, __all__, etc.)
        classes[in_class] = '\n'.join(class_lines)
```

This causes:
- Classes being truncated prematurely
- `__all__` statements being separated from their classes
- Decorators being orphaned

### 3. Import Deduplication Loses Context

```python
imports = set()  # Loses order and conditional imports
for line in lines:
    if line.startswith('import ') or line.startswith('from '):
        imports.add(line)
```

**Lost:**
- Import order (may matter for circular import prevention)
- `TYPE_CHECKING` conditional imports
- Comments explaining imports

### 4. Fixed Class Order Assumption

```python
class_order = ['PartType', 'Part', 'MessageRole', 'Message', 'Artifact']
```

Assumes all classes will be named exactly this way. If a generated file has `TextPart` or `FilePart`, they get sorted alphabetically at the end, breaking dependencies.

### 5. Last-Write-Wins for Duplicate Classes

If two features both define `class Message`, whichever is processed last wins. No attempt to merge methods or detect conflicts.

### 6. File Structure Mismatch

The codebase has:
- `part.py` → `Part`, `PartType`
- `parts.py` → `Message`, `MessageRole` (imports from `part.py`)

But the merge function assumes everything goes into `parts.py`, ignoring the actual file structure.

## Symptoms

When merge fails, you'll see:

1. **Syntax errors** after integration
   ```
   SyntaxError: unexpected EOF while parsing
   ```

2. **Duplicate definitions**
   ```python
   class Message:
       ...
   class Message:  # duplicate!
       ...
   ```

3. **Missing methods** - class body truncated

4. **Broken imports** - references to undefined names

5. **`__all__` mismatch** - exports don't match actual definitions

## Previous Workaround (No Longer Needed)

> **Note:** With the AST-based merge now in place, these workarounds are no longer necessary. They are preserved here for historical reference.

~~Until fixed, avoid the merge function entirely:~~

```bash
# These workarounds are OBSOLETE - AST merge handles these cases correctly now

# 1. Don't run multiple features targeting the same file
# python3 scripts/prime_contractor/cli.py run --max-features 1

# 2. If merge corrupted a file, restore it
# git checkout -- src/contextcore/agent/parts.py

# 3. Manually integrate features one at a time
```

**Current approach:** Just run the Prime Contractor normally - AST merge handles multiple features targeting the same file correctly.

## Recommended Fix

### Option A: AST-Based Merging (Recommended)

Replace text parsing with Python's `ast` module:

```python
import ast
from typing import Dict, List, Set

def merge_python_files_ast(sources: List[Path], target: Path) -> str:
    """Merge Python files using AST parsing."""

    # Parse all source files
    trees = []
    for src in sources:
        with open(src) as f:
            trees.append(ast.parse(f.read()))

    # Collect all definitions
    imports: List[ast.stmt] = []
    classes: Dict[str, ast.ClassDef] = {}
    functions: Dict[str, ast.FunctionDef] = {}

    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
            elif isinstance(node, ast.ClassDef):
                if node.name in classes:
                    # Merge methods from both definitions
                    classes[node.name] = merge_class_definitions(
                        classes[node.name], node
                    )
                else:
                    classes[node.name] = node
            elif isinstance(node, ast.FunctionDef):
                functions[node.name] = node

    # Build merged AST
    merged = ast.Module(body=[], type_ignores=[])

    # Deduplicate imports
    merged.body.extend(deduplicate_imports(imports))

    # Add classes in dependency order
    for cls in topological_sort_classes(classes):
        merged.body.append(classes[cls])

    # Add functions
    for func in functions.values():
        merged.body.append(func)

    return ast.unparse(merged)

def merge_class_definitions(existing: ast.ClassDef, new: ast.ClassDef) -> ast.ClassDef:
    """Merge two class definitions, combining methods."""
    existing_methods = {
        node.name: node
        for node in existing.body
        if isinstance(node, ast.FunctionDef)
    }

    for node in new.body:
        if isinstance(node, ast.FunctionDef):
            if node.name not in existing_methods:
                existing.body.append(node)
            # else: keep existing (or implement conflict resolution)

    return existing
```

**Benefits:**
- Correct Python syntax understanding
- Handles decorators, docstrings, type hints
- Can merge class methods intelligently
- Preserves comments with `ast.get_source_segment()`

### Option B: Incremental Patching

Instead of merging files, apply incremental patches:

```python
def apply_feature_as_patch(feature_code: str, target_path: Path) -> str:
    """Apply feature as incremental changes, not full replacement."""

    # Parse feature to find what it adds
    feature_tree = ast.parse(feature_code)

    # Parse existing target
    with open(target_path) as f:
        target_tree = ast.parse(f.read())

    # Find new definitions in feature
    new_classes = find_new_classes(feature_tree, target_tree)
    new_methods = find_new_methods(feature_tree, target_tree)
    new_imports = find_new_imports(feature_tree, target_tree)

    # Apply only the new parts
    for cls in new_classes:
        target_tree.body.append(cls)

    for cls_name, methods in new_methods.items():
        inject_methods_into_class(target_tree, cls_name, methods)

    # ... etc

    return ast.unparse(target_tree)
```

### Option C: File-Per-Feature Architecture

Restructure to avoid merge conflicts entirely:

```
src/contextcore/agent/
├── __init__.py          # Re-exports from submodules
├── part.py              # Part, PartType (base types)
├── message.py           # Message, MessageRole
├── artifact.py          # Artifact (NEW - already done!)
└── _extensions/
    ├── trace_part.py    # Extension for trace-related parts
    └── file_part.py     # Extension for file-related parts
```

Each feature targets its own file, eliminating merge conflicts.

## Implementation Plan

### Phase 1: Immediate (Workaround)
- [x] Document the issue (this file)
- [x] Add warning when multiple features target same file
- [x] Block automatic merge for high-risk files (parts.py, handoff.py)

### Phase 2: Short-term (AST Merge) - COMPLETED (2026-01-26)
- [x] Implement `merge_python_files_ast()` - See `scripts/lead_contractor/ast_merge.py`
- [x] Add unit tests with known merge scenarios - See `tests/test_ast_merge.py` (42 tests)
- [x] Replace `merge_parts_files()` with AST version
- [x] Replace `merge_files_intelligently()` with AST version
- [x] Add feature flag for safe rollout (`CONTEXTCORE_AST_MERGE` env var)
- [x] Preserve legacy merge as fallback (`_merge_files_legacy()`)

### Phase 3: Long-term (Architecture)
- [ ] Evaluate file-per-feature restructure
- [ ] Update Lead Contractor to generate to separate files
- [ ] Add conflict detection at planning stage

## Testing the Fix

### Running the Test Suite

```bash
# Run all AST merge tests (42 tests)
python3 -m pytest tests/test_ast_merge.py -v

# Run specific test categories
python3 -m pytest tests/test_ast_merge.py::TestParseFile -v
python3 -m pytest tests/test_ast_merge.py::TestClassMerging -v
python3 -m pytest tests/test_ast_merge.py::TestRegressionCases -v
```

### Manual Testing

```bash
# Test case: merge two files with same class
echo 'class Foo:
    def method_a(self): pass
' > /tmp/a.py

echo 'class Foo:
    def method_b(self): pass
' > /tmp/b.py

# Expected merged output:
# class Foo:
#     def method_a(self): pass
#     def method_b(self): pass

python3 -c "
from scripts.lead_contractor.ast_merge import merge_python_files
from pathlib import Path
result = merge_python_files(Path('/tmp/merged.py'), [Path('/tmp/a.py'), Path('/tmp/b.py')])
print(result.content)
print('Warnings:', result.warnings)
"
```

### Disabling AST Merge (Rollback)

If issues are found with the AST merge, you can disable it:

```bash
# Disable AST merge, fall back to legacy text-based merge
export CONTEXTCORE_AST_MERGE=false
python3 scripts/prime_contractor/cli.py run --import-backlog
```

## Current Implementation (AST-Based)

The AST-based merge is now the default in `scripts/lead_contractor/ast_merge.py`. Key features:

### Core Functions

- **`parse_python_file()`** - Parse a Python file into categorized components
- **`merge_parsed_files()`** - Merge multiple parsed files into one
- **`merge_class_definitions()`** - Merge two class definitions, combining methods
- **`deduplicate_imports()`** - Merge and deduplicate imports
- **`topological_sort_classes()`** - Sort classes by dependency order
- **`detect_class_dependencies()`** - Find class dependencies for ordering

### Data Structures

```python
@dataclass
class ParsedPythonFile:
    """Represents a parsed Python file with categorized components."""
    module_docstring: Optional[str]
    future_imports: List[ast.ImportFrom]
    regular_imports: List[Union[ast.Import, ast.ImportFrom]]
    type_checking_imports: List[ast.stmt]
    classes: Dict[str, ast.ClassDef]
    functions: Dict[str, ast.FunctionDef]
    constants: List[ast.Assign]
    all_export: Optional[List[str]]

@dataclass
class MergeResult:
    """Result of merging Python files."""
    content: str
    warnings: List[str]
    classes_merged: List[str]
    functions_merged: List[str]
    imports_deduplicated: int
```

### Key Improvements Over Legacy

1. **Decorator Preservation** - `@dataclass`, `@classmethod` stay attached to their targets
2. **Dependency Ordering** - Classes sorted topologically so `MessageRole` comes before `Message`
3. **Import Deduplication** - Merges `from X import a` and `from X import b` into `from X import a, b`
4. **`__future__` First** - Future imports always at the top
5. **TYPE_CHECKING Blocks** - Preserved separately from regular imports
6. **Class Merging** - New methods added to existing classes with duplicate warnings
7. **Syntax Validation** - Uses `ast.parse()` which catches syntax errors early

### Python 3.14 Compatibility

The implementation uses only `ast.Constant` (not the deprecated `ast.Str`, `ast.Num`, etc. which were removed in Python 3.14):

```python
# Correct (works on Python 3.9-3.14+)
if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
    docstring = node.value.value

# Wrong (breaks on Python 3.14)
if isinstance(node.value, ast.Str):  # AttributeError: module 'ast' has no attribute 'Str'
    docstring = node.value.s
```

## Related Files

- `scripts/lead_contractor/ast_merge.py` - **NEW**: AST-based merge implementation
- `scripts/lead_contractor/merge_conflicts.py` - Specialized merge functions (now use AST)
- `scripts/lead_contractor/integrate_backlog.py` - Integration workflow
- `scripts/prime_contractor/workflow.py` - Prime Contractor orchestration
- `tests/test_ast_merge.py` - **NEW**: Comprehensive test suite (42 tests)

## References

- Python AST documentation: https://docs.python.org/3/library/ast.html
- `ast.unparse()` (Python 3.9+): https://docs.python.org/3/library/ast.html#ast.unparse
