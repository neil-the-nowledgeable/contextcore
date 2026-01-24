# Integration Workflow Improvements

After analyzing the conflicts encountered during backlog integration, several improvements should be made to the integration workflow to handle similar situations better in the future.

## Current Issues Identified

### 1. **No Automatic Merge Strategy**
- Current workflow detects conflicts but doesn't attempt automatic merging
- Files that should be merged together (like `parts.py` with 4 complementary files) are treated as conflicts
- Requires manual intervention even for predictable merge patterns

### 2. **Limited Merge Pattern Detection**
- Workflow doesn't recognize when multiple files are meant to be combined
- No heuristics to detect complementary vs conflicting files
- Can't distinguish between "overwrite conflict" vs "merge opportunity"

### 3. **No Merge Strategy Registry**
- No way to define merge strategies for specific file patterns
- Can't specify "always merge these files together" vs "choose one"
- No knowledge base of known merge patterns

## Recommended Improvements

### Improvement 1: Add Merge Strategy Detection

**Location**: `scripts/lead_contractor/integrate_backlog.py`

**Add function to detect merge patterns**:

```python
def detect_merge_strategy(
    target_path: Path,
    source_files: List[GeneratedFile]
) -> Optional[str]:
    """
    Detect if files should be merged vs chosen.
    
    Returns:
        'merge' - Files should be merged together
        'choose' - User should choose one file
        'largest' - Use largest file (for duplicates)
        None - Unknown, require manual review
    """
    target_name = target_path.name
    
    # Known merge patterns
    merge_patterns = {
        'parts.py': 'merge',  # Always merge parts-related files
        '__init__.py': 'merge',  # Merge __init__ files
    }
    
    # Known "choose one" patterns
    choose_patterns = {
        'otel_genai.py': 'choose',  # Complex, needs review
        'handoff.py': 'choose',  # May have conflicting implementations
    }
    
    # Check for exact matches
    if target_name in merge_patterns:
        return merge_patterns[target_name]
    
    if target_name in choose_patterns:
        return choose_patterns[target_name]
    
    # Heuristics for unknown patterns
    # If files have complementary classes/functions, suggest merge
    if len(source_files) > 1:
        all_classes = set()
        all_functions = set()
        
        for src_file in source_files:
            analysis = analyze_file_content(src_file.path)
            if 'error' not in analysis:
                all_classes.update(analysis.get('classes', set()))
                all_functions.update(analysis.get('functions', set()))
        
        # If total unique classes/functions > any single file, likely complementary
        for src_file in source_files:
            analysis = analyze_file_content(src_file.path)
            if 'error' not in analysis:
                file_classes = analysis.get('classes', set())
                file_functions = analysis.get('functions', set())
                
                if len(all_classes) > len(file_classes) * 1.5:
                    return 'merge'  # Files have complementary classes
                if len(all_functions) > len(file_functions) * 1.5:
                    return 'merge'  # Files have complementary functions
    
    return None  # Unknown, require review
```

### Improvement 2: Add Automatic Merge Function

**Location**: `scripts/lead_contractor/integrate_backlog.py`

**Add merge function that can be called automatically**:

```python
def merge_files_automatically(
    target_path: Path,
    source_files: List[Dict],
    strategy: str = 'merge'
) -> Optional[str]:
    """
    Automatically merge multiple files into target.
    
    Args:
        target_path: Target file path
        source_files: List of source file dicts with 'source' and 'feature' keys
        strategy: Merge strategy ('merge', 'largest', 'newest')
    
    Returns:
        Merged content as string, or None if merge failed
    """
    if strategy == 'largest':
        # Use largest file
        files_content = []
        for src in source_files:
            src_path = Path(src['source'])
            if src_path.exists():
                with open(src_path, 'r', encoding='utf-8') as f:
                    content = clean_markdown_code_blocks(f.read())
                    files_content.append((len(content), content))
        
        if files_content:
            files_content.sort(key=lambda x: x[0], reverse=True)
            return files_content[0][1]
    
    elif strategy == 'merge':
        # Merge all files intelligently
        return merge_files_intelligently(target_path, source_files)
    
    return None


def merge_files_intelligently(
    target_path: Path,
    source_files: List[Dict]
) -> str:
    """
    Intelligently merge multiple Python files.
    
    Strategy:
    1. Collect all imports (deduplicate)
    2. Collect all classes (preserve all)
    3. Collect all functions (preserve all)
    4. Combine docstrings (use first non-empty)
    5. Generate __all__ list
    """
    imports = set()
    classes = {}
    functions = {}
    docstring = None
    module_level_code = []
    
    for src in source_files:
        src_path = Path(src['source'])
        if not src_path.exists():
            continue
        
        with open(src_path, 'r', encoding='utf-8') as f:
            content = clean_markdown_code_blocks(f.read())
        
        # Parse file (simplified - would need AST parsing for production)
        lines = content.split('\n')
        in_class = None
        in_function = None
        class_lines = []
        function_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Collect imports
            if stripped.startswith('import ') or stripped.startswith('from '):
                imports.add(stripped)
            
            # Collect docstring
            elif not docstring and stripped.startswith('"""'):
                doc_end = content.find('"""', content.find('"""') + 3)
                if doc_end > 0:
                    docstring = content[content.find('"""'):doc_end+3]
            
            # Collect classes
            elif stripped.startswith('class '):
                if in_class:
                    classes[in_class] = '\n'.join(class_lines)
                class_name = stripped.split('(')[0].split(':')[0].replace('class ', '').strip()
                in_class = class_name
                class_lines = [line]
            
            # Collect functions
            elif stripped.startswith('def ') and not in_class:
                if in_function:
                    functions[in_function] = '\n'.join(function_lines)
                func_name = stripped.split('(')[0].replace('def ', '').strip()
                in_function = func_name
                function_lines = [line]
            
            # Continue collecting
            elif in_class:
                class_lines.append(line)
            elif in_function:
                function_lines.append(line)
            else:
                # Module-level code
                if stripped and not stripped.startswith('#'):
                    module_level_code.append(line)
        
        # Save last class/function
        if in_class:
            classes[in_class] = '\n'.join(class_lines)
        if in_function:
            functions[in_function] = '\n'.join(function_lines)
    
    # Build merged content
    result = []
    
    # Docstring
    if docstring:
        result.append(docstring)
    result.append('')
    
    # Imports (sorted)
    sorted_imports = sorted(imports)
    for imp in sorted_imports:
        result.append(imp)
    result.append('')
    
    # Module-level code
    if module_level_code:
        result.extend(module_level_code)
        result.append('')
    
    # Classes (sorted by name)
    for class_name, class_content in sorted(classes.items()):
        result.append(class_content)
        result.append('')
    
    # Functions (sorted by name)
    for func_name, func_content in sorted(functions.items()):
        result.append(func_content)
        result.append('')
    
    # __all__ export
    all_exports = sorted(set(list(classes.keys()) + list(functions.keys())))
    if all_exports:
        result.append(f"__all__ = {all_exports}")
    
    return '\n'.join(result)
```

### Improvement 3: Update Integration Plan to Include Merge Strategy

**Location**: `scripts/lead_contractor/integrate_backlog.py` - `generate_integration_plan()`

**Modify to detect and suggest merge strategies**:

```python
# In generate_integration_plan(), after detecting duplicate targets:

# Detect duplicate targets and analyze conflicts
for target_str, source_files in target_to_sources.items():
    if len(source_files) > 1:
        plan["duplicate_targets"][target_str] = [
            {"source": str(f.path), "feature": f.feature_name}
            for f in source_files
        ]
        
        # Detect merge strategy
        target_path = Path(target_str)
        merge_strategy = detect_merge_strategy(target_path, source_files)
        
        if merge_strategy == 'merge':
            # Mark as merge opportunity, not conflict
            plan["merge_opportunities"][target_str] = {
                "strategy": "merge",
                "sources": [
                    {"source": str(f.path), "feature": f.feature_name}
                    for f in source_files
                ]
            }
            continue  # Skip conflict analysis for merge opportunities
        
        # Analyze conflicts for non-merge cases
        # ... existing conflict analysis code ...
```

### Improvement 4: Add Merge Execution to Workflow

**Location**: `scripts/lead_contractor/run_integrate_backlog_workflow.py`

**Add automatic merge execution**:

```python
# After generating integration plan, before conflict resolution:

# Handle merge opportunities automatically
if plan.get('merge_opportunities'):
    print(f"\n{'='*70}")
    print("MERGE OPPORTUNITIES DETECTED")
    print(f"{'='*70}")
    
    for target_str, merge_info in plan['merge_opportunities'].items():
        target_path = Path(target_str)
        sources = merge_info['sources']
        
        print(f"\nMerging: {target_path.relative_to(PROJECT_ROOT)}")
        print(f"  Sources: {len(sources)} files")
        
        if args.auto or args.dry_run:
            # Auto-merge
            merged_content = merge_files_automatically(
                target_path,
                sources,
                strategy=merge_info['strategy']
            )
            
            if merged_content and not args.dry_run:
                # Create backup
                if target_path.exists():
                    backup = target_path.with_suffix(f"{target_path.suffix}.backup")
                    shutil.copy2(target_path, backup)
                
                # Write merged content
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(merged_content)
                
                print(f"  ✓ Auto-merged {len(sources)} files")
            elif args.dry_run:
                print(f"  [DRY RUN] Would merge {len(sources)} files")
        else:
            # Ask for confirmation
            response = input(f"  Auto-merge {len(sources)} files? (yes/no): ")
            if response.lower() in ('yes', 'y'):
                merged_content = merge_files_automatically(
                    target_path,
                    sources,
                    strategy=merge_info['strategy']
                )
                # ... write merged content ...
```

### Improvement 5: Add Merge Strategy Configuration File

**Create**: `scripts/lead_contractor/merge_strategies.yaml`

```yaml
# Merge strategies for known file patterns

# Files that should always be merged
merge_always:
  - pattern: "parts.py"
    description: "Merge all parts-related models (Part, Message, Artifact)"
    strategy: "intelligent_merge"
  
  - pattern: "__init__.py"
    description: "Merge __init__ files by combining exports"
    strategy: "init_merge"

# Files that need manual review
manual_review:
  - pattern: "otel_genai.py"
    description: "Complex OTel compatibility layer - needs careful review"
    reason: "May have conflicting implementations"
  
  - pattern: "handoff.py"
    description: "Agent handoff logic - may have state conflicts"
    reason: "Different state management approaches"

# Files that should use largest version
use_largest:
  - pattern: "*statefile*.py"
    description: "State files - use most complete version"
  
  - pattern: "*config*.py"
    description: "Config files - use most complete version"
```

## Implementation Priority

1. **High Priority**:
   - Add `detect_merge_strategy()` function
   - Add merge strategy detection to `generate_integration_plan()`
   - Add basic `merge_files_automatically()` for simple cases

2. **Medium Priority**:
   - Implement intelligent merge for Python files
   - Add merge execution to workflow
   - Add merge strategy configuration file

3. **Low Priority**:
   - AST-based parsing for more accurate merging
   - Merge conflict detection (when auto-merge fails)
   - Merge history tracking

## Testing Strategy

After implementing improvements:

1. **Test with known merge patterns**:
   ```bash
   # Test parts.py merge
   python3 scripts/lead_contractor/integrate_backlog.py --test-merge parts.py
   ```

2. **Test conflict detection**:
   ```bash
   # Verify conflicts still detected correctly
   python3 scripts/lead_contractor/analyze_conflicts.py
   ```

3. **Test auto-merge**:
   ```bash
   # Test automatic merging
   python3 scripts/lead_contractor/run_integrate_backlog_workflow.py --auto-merge
   ```

## Migration Path

1. **Phase 1**: Add merge detection (non-breaking)
   - Add functions but don't change default behavior
   - Log merge opportunities for review

2. **Phase 2**: Add auto-merge with opt-in flag
   - Add `--auto-merge` flag
   - Users can opt-in to automatic merging

3. **Phase 3**: Make auto-merge default for known patterns
   - After validation, make merge default for `parts.py`, `__init__.py`, etc.
   - Still require manual review for complex cases

## Benefits

- **Reduced Manual Work**: Automatically merge complementary files
- **Faster Integration**: Less time spent on predictable merges
- **Better Detection**: Distinguish merge opportunities from conflicts
- **Consistency**: Standardized merge strategies for common patterns
- **Scalability**: Handle more files without proportional manual effort
