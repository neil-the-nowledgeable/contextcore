#!/usr/bin/env python3
"""
Process backlog of generated Lead Contractor code.

Scans generated/ directories, identifies unintegrated code,
and provides integration assistance.

Usage:
    # List all pending integrations
    python3 scripts/lead_contractor/integrate_backlog.py --list
    
    # Preview integration plan (dry-run)
    python3 scripts/lead_contractor/integrate_backlog.py --dry-run
    
    # Integrate all files (with confirmation)
    python3 scripts/lead_contractor/integrate_backlog.py
    
    # Integrate specific feature
    python3 scripts/lead_contractor/integrate_backlog.py --feature graph_schema
"""

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class GeneratedFile:
    """Represents a generated code file."""
    path: Path
    feature_name: str
    result_file: Path
    target_path: Optional[Path] = None
    integrated: bool = False
    metadata: Dict = field(default_factory=dict)


def scan_backlog() -> List[GeneratedFile]:
    """Scan generated/ directories for unintegrated code."""
    generated_files = []
    generated_dir = PROJECT_ROOT / "generated"
    
    if not generated_dir.exists():
        print(f"Warning: {generated_dir} does not exist")
        print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
        print(f"  Generated dir: {generated_dir}")
        return []
    
    # Find all *_code.py and *_code.ts files
    code_files = list(generated_dir.rglob("*_code.*"))
    if not code_files:
        print(f"Debug: No *_code.* files found in {generated_dir}")
        print(f"  Generated dir exists: {generated_dir.exists()}")
        # Try alternative search
        if generated_dir.exists():
            all_files = list(generated_dir.rglob("*"))
            print(f"  Total files in generated/: {len(all_files)}")
            code_like = [f for f in all_files if "_code" in f.name]
            print(f"  Files with '_code' in name: {len(code_like)}")
        return []
    
    print(f"Debug: Found {len(code_files)} code files")
    
    for code_file in code_files:
        # Skip if already in source tree (likely integrated)
        code_file_posix = code_file.as_posix()
        if "/src/" in code_file_posix or "/extensions/" in code_file_posix:
            continue
            
        # Find corresponding result file
        # Pattern: feature_3_1a_graph_schema_code.py -> feature_3_1a_graph_schema_result.json
        result_file = code_file.parent / code_file.name.replace("_code.", "_result.")
        
        # If result file doesn't exist, try .json extension
        if not result_file.exists() and result_file.suffix != ".json":
            result_file = result_file.with_suffix(".json")
        
        if result_file.exists():
            try:
                with open(result_file) as f:
                    result = json.load(f)
                    feature_name = result.get("feature", "unknown")
                    
                    generated_files.append(GeneratedFile(
                        path=code_file,
                        feature_name=feature_name,
                        result_file=result_file,
                        integrated=False,
                        metadata=result
                    ))
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not read {result_file}: {e}")
    
    return generated_files


def infer_target_path(generated_file: GeneratedFile) -> Optional[Path]:
    """Infer target path from feature name and file content."""
    feature = generated_file.feature_name.lower()
    file_name = generated_file.path.name
    
    # Remove _code suffix and get base name
    base_name = file_name.replace("_code.py", ".py").replace("_code.ts", ".ts")
    
    # Heuristics based on feature name patterns
    if "graph" in feature:
        if "schema" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "graph" / "schema.py"
        elif "builder" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "graph" / "builder.py"
        elif "queries" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "graph" / "queries.py"
        elif "cli" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "graph" / "cli.py"
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "graph" / base_name
    
    elif "a2a" in feature or "adapter" in feature:
        if "discovery" in feature:
            # Discovery features go to src/contextcore/discovery/, not agent/
            if "agentcard" in feature:
                return PROJECT_ROOT / "src" / "contextcore" / "discovery" / "agentcard.py"
            elif "endpoint" in feature:
                return PROJECT_ROOT / "src" / "contextcore" / "discovery" / "endpoint.py"
            elif "client" in feature:
                return PROJECT_ROOT / "src" / "contextcore" / "discovery" / "client.py"
            elif "package" in feature:
                return PROJECT_ROOT / "src" / "contextcore" / "discovery" / "__init__.py"
            else:
                return PROJECT_ROOT / "src" / "contextcore" / "discovery" / base_name
        elif "adapter" in feature:
            if "task" in feature:
                return PROJECT_ROOT / "src" / "contextcore" / "agent" / "a2a_adapter.py"
            elif "message" in feature:
                return PROJECT_ROOT / "src" / "contextcore" / "agent" / "a2a_adapter.py"
            elif "server" in feature or "client" in feature:
                return PROJECT_ROOT / "src" / "contextcore" / "agent" / "a2a_adapter.py"
            else:
                return PROJECT_ROOT / "src" / "contextcore" / "agent" / "a2a_adapter.py"
        elif "state" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "handoff.py"
        elif "parts" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "parts.py"
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / base_name
    
    elif "tui" in feature:
        # TUI files may have specific paths in the content
        return PROJECT_ROOT / "src" / "contextcore" / "tui" / base_name
    
    elif "install" in feature or "tracking" in feature:
        if file_name.endswith(".sh"):
            return PROJECT_ROOT / "scripts" / base_name
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "install" / base_name
    
    elif "slo" in feature or "test" in feature:
        return PROJECT_ROOT / "src" / "contextcore" / "generators" / "slo_tests.py"
    
    elif "pr" in feature and "review" in feature:
        return PROJECT_ROOT / "src" / "contextcore" / "integrations" / "github_review.py"
    
    elif "contract" in feature and "drift" in feature:
        return PROJECT_ROOT / "src" / "contextcore" / "integrations" / "contract_drift.py"
    
    elif "api" in feature:
        if "insights" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "api" / "insights.py"
        elif "handoffs" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "api" / "handoffs.py"
        elif "skills" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "api" / "skills.py"
        elif "package" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "api" / "__init__.py"
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "api" / base_name
    
    elif "discovery" in feature:
        if "agentcard" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "discovery" / "agentcard.py"
        elif "endpoint" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "discovery" / "endpoint.py"
        elif "client" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "discovery" / "client.py"
        elif "package" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "discovery" / "__init__.py"
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "discovery" / base_name
    
    elif "state" in feature:
        if "input" in feature or "request" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "handoff.py"
        elif "enhanced" in feature or "status" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "handoff.py"
        elif "events" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "events.py"
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "handoff.py"
    
    elif "parts" in feature:
        if "message" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "parts.py"
        elif "part" in feature and "model" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "parts.py"
        elif "artifact" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "parts.py"
        elif "models" in feature and "package" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "parts.py"
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "agent" / "parts.py"
    
    elif "otel" in feature or "unified" in feature:
        if "conversation" in feature or "conversationid" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "compat" / "otel_genai.py"
        elif "operation" in feature or "operationname" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "compat" / "operations.py"
        elif "tool" in feature and "mapping" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "compat" / "otel_genai.py"
        elif "provider" in feature or "model" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "tracing" / "insight_emitter.py"
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "compat" / base_name
    
    elif "foundation" in feature:
        if "gap" in feature or "analysis" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "compat" / "otel_genai.py"
        elif "dual" in feature or "emit" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "compat" / "otel_genai.py"
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "compat" / base_name
    
    elif "docs" in feature or "documentation" in feature:
        # Documentation updates might be markdown files or code
        if file_name.endswith(".md"):
            return PROJECT_ROOT / "docs" / base_name
        else:
            # Code that generates docs might go in docs/ or src/
            return PROJECT_ROOT / "docs" / base_name
    
    elif "learning" in feature:
        if "models" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "learning" / "models.py"
        elif "emitter" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "learning" / "emitter.py"
        elif "retriever" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "learning" / "retriever.py"
        elif "loop" in feature:
            return PROJECT_ROOT / "src" / "contextcore" / "learning" / "loop.py"
        else:
            return PROJECT_ROOT / "src" / "contextcore" / "learning" / base_name
    
    elif "vscode" in feature or "assembly" in feature:
        # VSCode extension files
        if "package" in feature:
            return PROJECT_ROOT / "extensions" / "vscode" / "package.json"
        elif file_name.endswith(".ts"):
            # Try to infer from file content or use generic location
            return PROJECT_ROOT / "extensions" / "vscode" / "src" / base_name
        else:
            return PROJECT_ROOT / "extensions" / "vscode" / base_name
    
    # Default: try to infer from file content
    try:
        with open(generated_file.path, 'r') as f:
            content = f.read(500)  # Read first 500 chars
            # Look for module path hints
            if "src/contextcore" in content:
                # Try to extract path hints
                import re
                path_match = re.search(r'src/contextcore/([^\s"\']+)', content)
                if path_match:
                    rel_path = path_match.group(1).split()[0]
                    return PROJECT_ROOT / "src" / "contextcore" / rel_path
    except IOError:
        pass
    
    return None


def check_if_integrated(generated_file: GeneratedFile, target_path: Path) -> bool:
    """Check if file has already been integrated."""
    if not target_path.exists():
        return False
    
    # Check for known resolved conflicts - these files have been manually merged
    resolved_conflicts = {
        'src/contextcore/compat/otel_genai.py': [
            'OTel_ConversationId', 'OTel_ToolMapping', 
            'Foundation_GapAnalysis', 'Foundation_DualEmit'
        ],
        'src/contextcore/agent/handoff.py': [
            'State_InputRequest', 'State_EnhancedStatus'
        ],
        'src/contextcore/install/installtracking_statefile.py': [
            'InstallTracking_StateFile'
        ],
    }
    
    target_str = str(target_path)

    # Check for known resolved conflicts - match against both absolute and relative paths
    for resolved_path, resolved_features in resolved_conflicts.items():
        # Match if target ends with the resolved path (handles both relative and absolute)
        if target_str.endswith(resolved_path) or resolved_path in target_str:
            # Check if this feature was part of the resolved conflict
            feature_name = generated_file.feature_name
            if any(resolved_feature in feature_name for resolved_feature in resolved_features):
                # File exists and this feature was already resolved
                # Check if target is significantly larger (indicating merge was done)
                try:
                    target_stat = target_path.stat()
                    source_stat = generated_file.path.stat()
                    # If target is larger, likely merged
                    if target_stat.st_size > source_stat.st_size * 1.2:
                        return True
                except OSError:
                    pass
    
    # Compare file sizes and modification times as heuristic
    # (Not perfect, but good enough for detection)
    try:
        source_stat = generated_file.path.stat()
        target_stat = target_path.stat()
        
        # If target is newer and similar size, likely integrated
        if target_stat.st_mtime > source_stat.st_mtime:
            size_diff = abs(source_stat.st_size - target_stat.st_size)
            if size_diff < 100:  # Within 100 bytes
                return True
    except OSError:
        pass
    
    return False


def analyze_file_content(file_path: Path) -> Dict[str, any]:
    """Analyze file content to help detect conflicts."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract key identifiers (classes, functions, imports)
        classes = re.findall(r'^class\s+([A-Za-z_][A-Za-z0-9_]*)', content, re.MULTILINE)
        functions = re.findall(r'^def\s+([A-Za-z_][A-Za-z0-9_]*)', content, re.MULTILINE)
        imports = re.findall(r'^(?:from|import)\s+([^\s]+)', content, re.MULTILINE)
        
        return {
            'size': len(content),
            'lines': len(content.split('\n')),
            'classes': set(classes),
            'functions': set(functions),
            'imports': set(imports),
            'has_main': 'if __name__' in content or '__main__' in content,
        }
    except Exception as e:
        return {'error': str(e)}


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
        'otel_genai.py': 'merge',  # Merge complementary OTel attributes/mappings
        'handoff.py': 'merge',  # Merge complementary handoff classes (HandoffResult, HandoffStorage, etc.)
    }
    
    # Known "choose one" patterns (complex cases that need manual review)
    choose_patterns = {
        # Removed otel_genai.py and handoff.py - now handled as merge opportunities
    }
    
    # Known "use largest" patterns
    largest_patterns = {
        '*statefile*.py': 'largest',  # State files - use most complete version
        '*config*.py': 'largest',  # Config files - use most complete version
        'installtracking_statefile.py': 'largest',  # Installation state - use complete implementation
    }
    
    # Check for exact matches
    if target_name in merge_patterns:
        return merge_patterns[target_name]
    
    if target_name in choose_patterns:
        return choose_patterns[target_name]
    
    # Check pattern matches
    import fnmatch
    for pattern, strategy in largest_patterns.items():
        if fnmatch.fnmatch(target_name, pattern):
            return strategy
    
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


def merge_files_intelligently(
    target_path: Path,
    source_files: List[Dict]
) -> str:
    """
    Intelligently merge multiple Python files using AST parsing.

    This function uses Python's ast module for robust parsing that correctly
    handles decorators, multi-line strings, and class dependencies.

    Strategy:
    1. Parse each file into AST
    2. Collect all imports (deduplicate, __future__ first)
    3. Collect all classes (topologically sorted by dependencies)
    4. Collect all functions
    5. Combine docstrings (use first non-empty)
    6. Generate __all__ list

    Falls back to legacy text-based merge if AST parsing fails.
    """
    import os

    # Feature flag for safe rollout - can disable AST merge if issues found
    use_ast_merge = os.environ.get('CONTEXTCORE_AST_MERGE', 'true').lower() == 'true'

    if not use_ast_merge:
        return _merge_files_legacy(target_path, source_files)

    try:
        from scripts.lead_contractor.ast_merge import (
            parse_python_file,
            merge_parsed_files,
        )

        parsed_files = []

        # Include existing target first (so its content takes precedence)
        if target_path.exists():
            try:
                existing = parse_python_file(target_path)
                parsed_files.append(existing)
            except SyntaxError as e:
                print(f"  Warning: Target {target_path.name} has syntax error: {e}")

        # Parse source files
        for src in source_files:
            src_path = Path(src['source'])
            if not src_path.exists():
                continue
            try:
                parsed = parse_python_file(src_path)
                parsed_files.append(parsed)
            except SyntaxError as e:
                print(f"  Warning: Skipping {src_path.name} due to syntax error: {e}")
                continue

        if not parsed_files:
            return ""

        result = merge_parsed_files(parsed_files)

        # Print warnings from merge
        for warning in result.warnings:
            print(f"  Warning: {warning}")

        if result.classes_merged:
            print(f"  Merged classes: {', '.join(result.classes_merged)}")

        return result.content

    except ImportError as e:
        print(f"  Warning: AST merge module not available ({e}), using legacy merge")
        return _merge_files_legacy(target_path, source_files)
    except Exception as e:
        print(f"  Warning: AST merge failed ({e}), falling back to legacy merge")
        return _merge_files_legacy(target_path, source_files)


def _merge_files_legacy(
    target_path: Path,
    source_files: List[Dict]
) -> str:
    """
    Legacy text-based merge (preserved for fallback).

    WARNING: This function can corrupt Python files by:
    - Separating decorators from their classes
    - Breaking multi-line strings
    - Incorrectly identifying class boundaries

    Use only as fallback when AST merge is unavailable.
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
        in_docstring = False
        docstring_lines = []
        indent_level = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            current_indent = len(line) - len(line.lstrip())

            # Collect imports
            if stripped.startswith('import ') or stripped.startswith('from '):
                imports.add(stripped)

            # Collect docstring
            elif not docstring and stripped.startswith('"""'):
                if stripped.count('"""') == 2:
                    # Single-line docstring
                    docstring = stripped
                else:
                    # Multi-line docstring
                    in_docstring = True
                    docstring_lines = [line]

            elif in_docstring:
                docstring_lines.append(line)
                if '"""' in stripped:
                    docstring = '\n'.join(docstring_lines)
                    in_docstring = False

            # Collect classes
            elif stripped.startswith('class '):
                if in_class:
                    classes[in_class] = '\n'.join(class_lines)
                if in_function:
                    functions[in_function] = '\n'.join(function_lines)
                    in_function = None
                    function_lines = []

                class_name = stripped.split('(')[0].split(':')[0].replace('class ', '').strip()
                in_class = class_name
                class_lines = [line]
                indent_level = current_indent

            # Collect functions (only at module level)
            elif stripped.startswith('def ') and not in_class:
                if in_function:
                    functions[in_function] = '\n'.join(function_lines)
                func_name = stripped.split('(')[0].replace('def ', '').strip()
                in_function = func_name
                function_lines = [line]
                indent_level = current_indent

            # Continue collecting class/function content
            elif in_class:
                if stripped and not stripped.startswith('#') and current_indent <= indent_level:
                    # End of class
                    classes[in_class] = '\n'.join(class_lines)
                    in_class = None
                    class_lines = []
                else:
                    class_lines.append(line)

            elif in_function:
                if stripped and not stripped.startswith('#') and current_indent <= indent_level:
                    # End of function
                    functions[in_function] = '\n'.join(function_lines)
                    in_function = None
                    function_lines = []
                else:
                    function_lines.append(line)

            else:
                # Module-level code (not in class/function)
                if stripped and not stripped.startswith('#') and not stripped.startswith('@'):
                    # Check if it's not an import or docstring
                    if not (stripped.startswith('import ') or stripped.startswith('from ') or
                            stripped.startswith('"""') or stripped.startswith("'''")):
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
    if sorted_imports:
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
    
    elif strategy == 'newest':
        # Use newest file
        files_content = []
        for src in source_files:
            src_path = Path(src['source'])
            if src_path.exists():
                stat = src_path.stat()
                with open(src_path, 'r', encoding='utf-8') as f:
                    content = clean_markdown_code_blocks(f.read())
                    files_content.append((stat.st_mtime, content))
        
        if files_content:
            files_content.sort(key=lambda x: x[0], reverse=True)
            return files_content[0][1]
    
    elif strategy == 'merge':
        # Merge all files intelligently
        return merge_files_intelligently(target_path, source_files)
    
    return None


def compare_files_for_conflicts(file1: Path, file2: Path) -> Dict[str, any]:
    """Compare two files to detect potential conflicts."""
    analysis1 = analyze_file_content(file1)
    analysis2 = analyze_file_content(file2)
    
    if 'error' in analysis1 or 'error' in analysis2:
        return {'error': 'Could not analyze one or both files'}
    
    conflicts = {
        'size_diff': abs(analysis1['size'] - analysis2['size']),
        'size_diff_percent': abs(analysis1['size'] - analysis2['size']) / max(analysis1['size'], analysis2['size'], 1) * 100,
        'classes_added': analysis2['classes'] - analysis1['classes'],
        'classes_removed': analysis1['classes'] - analysis2['classes'],
        'functions_added': analysis2['functions'] - analysis1['functions'],
        'functions_removed': analysis1['functions'] - analysis2['functions'],
        'imports_changed': (analysis1['imports'] | analysis2['imports']) - (analysis1['imports'] & analysis2['imports']),
    }
    
    # Calculate conflict risk score (0-100)
    risk_score = 0
    if conflicts['size_diff_percent'] > 50:
        risk_score += 30  # Large size difference
    if len(conflicts['classes_removed']) > 0:
        risk_score += 25  # Classes would be removed
    if len(conflicts['functions_removed']) > 0:
        risk_score += 20  # Functions would be removed
    if len(conflicts['imports_changed']) > 5:
        risk_score += 15  # Many import changes
    if conflicts['size_diff_percent'] > 20:
        risk_score += 10  # Moderate size difference
    
    conflicts['risk_score'] = min(risk_score, 100)
    conflicts['risk_level'] = 'HIGH' if risk_score >= 50 else 'MEDIUM' if risk_score >= 25 else 'LOW'
    
    return conflicts


def generate_integration_plan(
    files: List[GeneratedFile],
    feature_filter: Optional[str] = None
) -> Dict:
    """Generate integration plan with target paths."""
    plan = {
        "files": [],
        "warnings": [],
        "requires_review": [],
        "already_integrated": [],
        "duplicate_targets": {},  # Track files that map to same target
        "conflicts": {},  # Track conflicts for duplicate targets
        "merge_opportunities": {}  # Track files that should be merged (not conflicting)
    }
    
    # Track targets to detect duplicates
    target_to_sources = {}
    
    for file in files:
        # Filter by feature if specified
        if feature_filter and feature_filter.lower() not in file.feature_name.lower():
            continue
        
        target = infer_target_path(file)
        if target:
            target_str = str(target)
            
            # Track duplicate targets
            if target_str not in target_to_sources:
                target_to_sources[target_str] = []
            target_to_sources[target_str].append(file)
            
            # Check if already integrated
            if check_if_integrated(file, target):
                plan["already_integrated"].append({
                    "source": str(file.path),
                    "target": target_str,
                    "feature": file.feature_name
                })
            else:
                plan["files"].append({
                    "source": str(file.path),
                    "target": target_str,
                    "feature": file.feature_name
                })
        else:
            plan["warnings"].append(f"Could not infer target for {file.path.name} ({file.feature_name})")
            plan["requires_review"].append(file)
    
    # Detect duplicate targets and analyze conflicts
    # First, build a set of already-integrated source paths for fast lookup
    already_integrated_sources = {item["source"] for item in plan["already_integrated"]}

    for target_str, source_files in target_to_sources.items():
        if len(source_files) > 1:
            target_path = Path(target_str)

            # Check if ALL source files for this target are already integrated
            all_integrated = all(
                str(f.path) in already_integrated_sources
                for f in source_files
            )
            if all_integrated:
                # Skip conflict analysis - all files are already integrated
                continue

            # Detect merge strategy
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

            # Track as duplicate target
            plan["duplicate_targets"][target_str] = [
                {"source": str(f.path), "feature": f.feature_name}
                for f in source_files
            ]
            
            # Analyze conflicts for non-merge cases
            conflicts = []
            
            # Compare each pair of files
            for i in range(len(source_files)):
                for j in range(i + 1, len(source_files)):
                    file1 = source_files[i].path
                    file2 = source_files[j].path
                    
                    conflict = compare_files_for_conflicts(file1, file2)
                    conflict['file1'] = str(file1.relative_to(PROJECT_ROOT))
                    conflict['file2'] = str(file2.relative_to(PROJECT_ROOT))
                    conflict['feature1'] = source_files[i].feature_name
                    conflict['feature2'] = source_files[j].feature_name
                    conflicts.append(conflict)
            
            if conflicts:
                # Get highest risk conflict
                max_risk = max(c.get('risk_score', 0) for c in conflicts)
                plan["conflicts"][target_str] = {
                    "max_risk_score": max_risk,
                    "max_risk_level": max([c.get('risk_level', 'LOW') for c in conflicts], 
                                         key=lambda x: ['LOW', 'MEDIUM', 'HIGH'].index(x)),
                    "conflicts": conflicts,
                    "file_count": len(source_files),
                    "merge_strategy": merge_strategy  # Include detected strategy
                }
    
    return plan


def clean_markdown_code_blocks(content: str) -> str:
    """Remove markdown code blocks from file content."""
    # Remove opening ```python or ``` at the start
    content = content.lstrip()
    lines = content.split("\n")
    
    # Remove opening code block marker
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
        content = "\n".join(lines)
    
    # Remove closing ``` at the end
    content = content.rstrip()
    lines = content.split("\n")
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
        content = "\n".join(lines)
    
    return content


def detect_incomplete_file(content: str, file_path: Path) -> List[str]:
    """
    Detect if a file appears incomplete or truncated.

    Returns:
        List of issues found (empty if file appears complete)
    """
    issues = []
    lines = content.split('\n')

    if not lines:
        issues.append("File is empty")
        return issues

    # Check for incomplete lines (lines ending with incomplete identifiers)
    last_line = lines[-1].strip()
    # Check if last line looks incomplete (ends with identifier but no statement)
    if last_line and not last_line.endswith((':', ')', ']', '}', '"""', "'''", '"""', "'''", ',', '#')):
        # Check if it's just an identifier without assignment or function call
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*$', last_line):
            issues.append(f"TRUNCATED: File ends with incomplete identifier: '{last_line}'")
        # Check for incomplete assignment (e.g., "x = ")
        elif re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*$', last_line):
            issues.append(f"TRUNCATED: File ends with incomplete assignment: '{last_line}'")
        # Check for incomplete method call (e.g., "foo.bar")
        elif re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*\s*$', last_line) and '.' in last_line:
            issues.append(f"TRUNCATED: File ends with incomplete expression: '{last_line}'")

    # Check for incomplete function/class definitions
    incomplete_defs = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(('def ', 'class ')) and not stripped.endswith(':'):
            # Check if next line exists and is indented
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if next_line.strip() and not next_line.startswith((' ', '\t')):
                    incomplete_defs.append(f"Line {i+1}: {stripped[:50]}")

    if incomplete_defs:
        issues.append(f"TRUNCATED: Incomplete definitions found: {incomplete_defs[:3]}")

    # Check for unmatched brackets/parentheses/braces (basic check)
    paren_diff = content.count('(') - content.count(')')
    bracket_diff = content.count('[') - content.count(']')
    brace_diff = content.count('{') - content.count('}')

    if paren_diff > 0:
        issues.append(f"TRUNCATED: {paren_diff} unclosed parenthese(s)")
    if bracket_diff > 0:
        issues.append(f"TRUNCATED: {bracket_diff} unclosed bracket(s)")
    if brace_diff > 0:
        issues.append(f"TRUNCATED: {brace_diff} unclosed brace(s)")

    # Check for incomplete string literals
    triple_double = content.count('"""')
    triple_single = content.count("'''")
    if triple_double % 2 != 0:
        issues.append("TRUNCATED: Unclosed triple-quoted string (\"\"\")")
    if triple_single % 2 != 0:
        issues.append("TRUNCATED: Unclosed triple-quoted string (''')")

    # Check if __all__ exports reference missing definitions
    all_match = re.search(r"__all__\s*=\s*\[([^\]]+)\]", content)
    if all_match:
        exports = re.findall(r"['\"]([a-zA-Z_][a-zA-Z0-9_]*)['\"]", all_match.group(1))
        # Get defined classes and functions
        defined_classes = set(re.findall(r'^class\s+([A-Za-z_][A-Za-z0-9_]*)', content, re.MULTILINE))
        defined_functions = set(re.findall(r'^def\s+([A-Za-z_][A-Za-z0-9_]*)', content, re.MULTILINE))
        defined_all = defined_classes | defined_functions

        missing = [e for e in exports if e not in defined_all]
        if missing:
            issues.append(f"TRUNCATED: __all__ references missing definitions: {missing[:5]}")

    # Check for Python syntax errors (quick validation)
    try:
        compile(content, str(file_path), 'exec')
    except SyntaxError as e:
        # Only flag as truncation if it's at the end of the file
        if e.lineno and e.lineno > len(lines) - 5:
            issues.append(f"TRUNCATED: Syntax error near end of file (line {e.lineno}): {e.msg}")

    return issues


def show_file_preview(file_path: Path, max_lines: int = 30) -> None:
    """Show a preview of file content."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"\n  Preview of {file_path.name} ({len(lines)} lines):")
        print("  " + "-" * 66)
        
        # Show first few lines
        for i, line in enumerate(lines[:max_lines], 1):
            print(f"  {i:3d} | {line.rstrip()}")
        
        if len(lines) > max_lines:
            print(f"  ... ({len(lines) - max_lines} more lines)")
        
        # Show file stats
        analysis = analyze_file_content(file_path)
        if 'error' not in analysis:
            print(f"\n  Stats:")
            print(f"    Size: {analysis['size']:,} bytes")
            print(f"    Lines: {analysis['lines']:,}")
            print(f"    Classes: {len(analysis['classes'])}")
            print(f"    Functions: {len(analysis['functions'])}")
            if analysis['classes']:
                print(f"    Classes: {', '.join(list(analysis['classes'])[:5])}")
            if analysis['functions']:
                print(f"    Functions: {', '.join(list(analysis['functions'])[:5])}")
        
    except Exception as e:
        print(f"  Error reading file: {e}")


def resolve_conflict_interactive(
    target_path: Path,
    source_files: List[Dict],
    plan: Dict
) -> Optional[Dict]:
    """
    Interactively resolve a conflict by letting user choose which file to integrate.
    
    Args:
        target_path: Path to the target file (may be Path or str)
        source_files: List of dicts with 'source' and 'feature' keys
        plan: Integration plan dict with conflicts info
    
    Returns:
        Selected file dict, or None if user skips/quits
    """
    # Ensure target_path is a Path object
    if isinstance(target_path, str):
        target_path = Path(target_path)
    
    target_rel = target_path.relative_to(PROJECT_ROOT)
    conflict_info = plan.get('conflicts', {}).get(str(target_path), {})
    risk_level = conflict_info.get('max_risk_level', 'UNKNOWN')
    risk_score = conflict_info.get('max_risk_score', 0)
    
    print(f"\n{'='*70}")
    print(f"CONFLICT RESOLUTION: {target_rel}")
    print(f"{'='*70}")
    print(f"Risk Level: {risk_level} (Score: {risk_score}/100)")
    print(f"Files targeting this destination: {len(source_files)}")
    
    # Show conflict details if available
    if conflict_info.get('conflicts'):
        worst_conflict = max(conflict_info['conflicts'], 
                           key=lambda c: c.get('risk_score', 0))
        print(f"\nConflict Details:")
        print(f"  Comparing: {worst_conflict.get('feature1')} vs {worst_conflict.get('feature2')}")
        if worst_conflict.get('classes_removed'):
            removed = list(worst_conflict['classes_removed'])[:5]
            print(f"  ⚠️  Would remove classes: {', '.join(removed)}")
        if worst_conflict.get('functions_removed'):
            removed = list(worst_conflict['functions_removed'])[:5]
            print(f"  ⚠️  Would remove functions: {', '.join(removed)}")
        if worst_conflict.get('size_diff_percent', 0) > 20:
            print(f"  ⚠️  Size difference: {worst_conflict['size_diff_percent']:.1f}%")
    
    # Show current target if it exists
    if target_path.exists():
        print(f"\nCurrent target file exists:")
        try:
            target_stat = target_path.stat()
            print(f"  Size: {target_stat.st_size:,} bytes")
            print(f"  Modified: {target_stat.st_mtime}")
        except:
            pass
    
    # Show options
    print(f"\nOptions:")
    for i, src in enumerate(source_files, 1):
        src_path = Path(src['source'])
        try:
            src_stat = src_path.stat()
            size = src_stat.st_size
            print(f"  [{i}] {src['feature']}")
            print(f"      File: {src_path.name}")
            print(f"      Size: {size:,} bytes")
        except:
            print(f"  [{i}] {src['feature']} (file not found)")
    
    print(f"  [s] Skip this conflict")
    print(f"  [v] View file details")
    print(f"  [q] Quit workflow")
    
    while True:
        choice = input("\nSelect option: ").strip().lower()
        
        if choice == 'q':
            return None  # Signal to quit
        
        if choice == 's':
            return None  # Skip
        
        if choice == 'v':
            # Show detailed view
            print("\nFile Details:")
            for i, src in enumerate(source_files, 1):
                print(f"\n[{i}] {src['feature']}:")
                show_file_preview(Path(src['source']), max_lines=20)
            continue
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(source_files):
                selected = source_files[idx]
                print(f"\n✓ Selected: {selected['feature']}")
                return selected
            else:
                print(f"Invalid option. Choose 1-{len(source_files)}, s, v, or q")
        except ValueError:
            print(f"Invalid input. Choose 1-{len(source_files)}, s, v, or q")
    
    return None


def integrate_file(
    source: Path,
    target: Path,
    dry_run: bool = False,
    fail_on_truncation: bool = True
) -> bool:
    """
    Integrate a single file.

    Args:
        source: Source file path
        target: Target file path
        dry_run: If True, only preview without modifying files
        fail_on_truncation: If True, refuse to integrate truncated files (default: True)

    Returns:
        True if integration succeeded, False otherwise
    """
    if dry_run:
        print(f"  [DRY RUN] Would copy {source.name}")
        print(f"    From: {source}")
        print(f"    To:   {target}")
        return True

    # Read source file and clean it BEFORE creating backup
    try:
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  ✗ Failed to read {source.name}: {e}")
        return False

    # Clean markdown code blocks for Python files
    if source.suffix == '.py':
        original_content = content
        content = clean_markdown_code_blocks(content)
        if content != original_content:
            print(f"  [Cleaned] Removed markdown code blocks from {source.name}")

        # Check for incomplete/truncated files BEFORE making any changes
        incomplete_issues = detect_incomplete_file(content, source)
        truncation_issues = [i for i in incomplete_issues if i.startswith("TRUNCATED:")]

        if truncation_issues:
            print(f"  ❌ REJECTED: File appears truncated or incomplete:")
            for issue in truncation_issues:
                print(f"    - {issue}")

            if fail_on_truncation:
                print(f"  ⛔ Integration blocked to prevent corrupting target file.")
                print(f"     The generated code was likely cut off due to LLM token limits.")
                print(f"     Options:")
                print(f"       1. Regenerate the feature with a smaller scope")
                print(f"       2. Manually complete the truncated code")
                print(f"       3. Use fail_on_truncation=False to force integration (dangerous)")
                return False
            else:
                print(f"  ⚠️  Proceeding despite truncation (fail_on_truncation=False)")

        # Show non-truncation warnings but don't block
        other_issues = [i for i in incomplete_issues if not i.startswith("TRUNCATED:")]
        if other_issues:
            print(f"  ⚠️  Warnings:")
            for issue in other_issues[:3]:
                print(f"    - {issue}")

    # Create backup if target exists (only after validation passes)
    if target.exists():
        backup = target.with_suffix(f"{target.suffix}.backup")
        shutil.copy2(target, backup)
        print(f"  Backed up existing file to {backup.name}")

    # Create target directory
    target.parent.mkdir(parents=True, exist_ok=True)

    # Write cleaned content
    try:
        with open(target, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ Integrated: {target.relative_to(PROJECT_ROOT)}")
    except Exception as e:
        print(f"  ✗ Failed to write {target.name}: {e}")
        return False

    return True


def main():
    """Main integration workflow."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Integrate Lead Contractor generated code into source tree",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all pending integrations
  %(prog)s --list
  
  # Preview integration plan
  %(prog)s --dry-run
  
  # Integrate all files
  %(prog)s
  
  # Integrate specific feature
  %(prog)s --feature graph_schema
        """
    )
    parser.add_argument("--dry-run", action="store_true", 
                       help="Preview changes without integrating")
    parser.add_argument("--feature", type=str, 
                       help="Process specific feature (partial match)")
    parser.add_argument("--list", action="store_true", 
                       help="List all pending integrations")
    parser.add_argument("--auto", action="store_true", 
                       help="Auto-integrate without confirmation (use with caution)")
    parser.add_argument("--allow-conflicts", action="store_true",
                       help="Allow integration even with high-risk conflicts (dangerous)")
    
    args = parser.parse_args()
    
    print("Scanning generated/ directories...")
    files = scan_backlog()
    
    if not files:
        print("No generated files found.")
        return
    
    print(f"Found {len(files)} generated file(s)")
    
    if args.list:
        print(f"\n{'='*70}")
        print("Generated Files Inventory")
        print(f"{'='*70}\n")
        
        for f in files:
            target = infer_target_path(f)
            status = "✓" if target and check_if_integrated(f, target) else "?"
            print(f"{status} {f.feature_name}")
            print(f"    File: {f.path.relative_to(PROJECT_ROOT)}")
            if target:
                integrated = check_if_integrated(f, target)
                status_text = " (already integrated)" if integrated else ""
                print(f"    -> {target.relative_to(PROJECT_ROOT)}{status_text}")
            else:
                print(f"    -> [Could not infer target path]")
            print()
        return
    
    # Generate integration plan
    plan = generate_integration_plan(files, feature_filter=args.feature)
    
    print(f"\n{'='*70}")
    print("Integration Plan")
    print(f"{'='*70}")
    print(f"  Files to integrate: {len(plan['files'])}")
    print(f"  Already integrated: {len(plan['already_integrated'])}")
    print(f"  Requires review: {len(plan['requires_review'])}")
    print(f"  Warnings: {len(plan['warnings'])}")
    print(f"  Duplicate targets: {len(plan.get('duplicate_targets', {}))}")
    
    # Show conflicts in detail
    if plan.get('conflicts'):
        print(f"\n🚨 CONFLICT ANALYSIS ({len(plan['conflicts'])} target(s) with conflicts):")
        high_risk_count = sum(1 for c in plan['conflicts'].values() 
                            if c.get('max_risk_level') == 'HIGH')
        medium_risk_count = sum(1 for c in plan['conflicts'].values() 
                               if c.get('max_risk_level') == 'MEDIUM')
        
        print(f"  High risk: {high_risk_count}, Medium risk: {medium_risk_count}")
        
        for target_str, conflict_info in plan['conflicts'].items():
            target_rel = Path(target_str).relative_to(PROJECT_ROOT)
            risk_level = conflict_info.get('max_risk_level', 'UNKNOWN')
            risk_score = conflict_info.get('max_risk_score', 0)
            file_count = conflict_info.get('file_count', 0)
            
            print(f"\n  📁 {target_rel} ({risk_level} RISK - Score: {risk_score}/100)")
            print(f"     {file_count} file(s) will overwrite this target:")
            
            # Show which files conflict
            sources = plan['duplicate_targets'].get(target_str, [])
            for src in sources:
                print(f"       • {src['feature']}: {Path(src['source']).name}")
            
            # Show conflict details
            conflicts = conflict_info.get('conflicts', [])
            if conflicts:
                worst_conflict = max(conflicts, key=lambda c: c.get('risk_score', 0))
                print(f"     Worst conflict:")
                print(f"       {worst_conflict['feature1']} vs {worst_conflict['feature2']}")
                if worst_conflict.get('classes_removed'):
                    print(f"       ⚠️  Would remove classes: {', '.join(list(worst_conflict['classes_removed'])[:3])}")
                if worst_conflict.get('functions_removed'):
                    print(f"       ⚠️  Would remove functions: {', '.join(list(worst_conflict['functions_removed'])[:3])}")
                if worst_conflict.get('size_diff_percent', 0) > 20:
                    print(f"       ⚠️  Size difference: {worst_conflict['size_diff_percent']:.1f}%")
        
        if high_risk_count > 0 and not args.allow_conflicts:
            print(f"\n❌ BLOCKING: {high_risk_count} high-risk conflict(s) detected!")
            print("   Use --allow-conflicts to proceed anyway (may cause regressions)")
            return
    
    if plan.get('duplicate_targets'):
        print(f"\n⚠️  Duplicate Targets ({len(plan['duplicate_targets'])}):")
        print("  Multiple files will integrate to the same target (last one wins):")
        for target, sources in list(plan['duplicate_targets'].items())[:5]:  # Show first 5
            print(f"    {Path(target).relative_to(PROJECT_ROOT)}:")
            for src in sources:
                print(f"      - {src['feature']}: {Path(src['source']).name}")
        if len(plan['duplicate_targets']) > 5:
            print(f"    ... and {len(plan['duplicate_targets']) - 5} more")
    
    if plan['already_integrated']:
        print(f"\nAlready Integrated ({len(plan['already_integrated'])}):")
        for item in plan['already_integrated']:
            print(f"  ✓ {item['feature']}")
    
    if plan['warnings']:
        print(f"\n⚠️  Warnings ({len(plan['warnings'])}):")
        for warning in plan['warnings']:
            print(f"  - {warning}")
    
    if plan['requires_review']:
        print(f"\n📋 Requires Manual Review ({len(plan['requires_review'])}):")
        for file in plan['requires_review']:
            print(f"  - {file.feature_name}: {file.path.name}")
    
    if not plan['files']:
        print("\nNo files to integrate.")
        return
    
    print(f"\n📦 Files to Integrate ({len(plan['files'])}):")
    for item in plan['files']:
        source_rel = Path(item['source']).relative_to(PROJECT_ROOT)
        target_rel = Path(item['target']).relative_to(PROJECT_ROOT)
        print(f"  • {item['feature']}")
        print(f"    {source_rel} -> {target_rel}")
    
    if args.dry_run:
        print(f"\n{'='*70}")
        print("DRY RUN MODE - No files will be modified")
        print(f"{'='*70}\n")
        for item in plan['files']:
            integrate_file(Path(item['source']), Path(item['target']), dry_run=True)
        return
    
    if not args.auto:
        print(f"\n{'='*70}")
        response = input("Proceed with integration? (yes/no): ")
        if response.lower() not in ('yes', 'y'):
            print("Cancelled.")
            return
    
    # Integrate files
    print(f"\n{'='*70}")
    print("Integrating Files")
    print(f"{'='*70}\n")
    
    integrated = 0
    failed = 0
    
    for item in plan['files']:
        source = Path(item['source'])
        target = Path(item['target'])
        
        try:
            if integrate_file(source, target, dry_run=False):
                integrated += 1
        except Exception as e:
            print(f"  ✗ Failed to integrate {source.name}: {e}")
            failed += 1
    
    print(f"\n{'='*70}")
    print("Integration Complete")
    print(f"{'='*70}")
    print(f"  ✓ Integrated: {integrated}")
    if failed > 0:
        print(f"  ✗ Failed: {failed}")
    print(f"\nNext steps:")
    print(f"  1. Review integrated files")
    print(f"  2. Update imports/exports as needed")
    print(f"  3. Run tests: python3 -m pytest")
    print(f"  4. Commit changes")


if __name__ == "__main__":
    main()
