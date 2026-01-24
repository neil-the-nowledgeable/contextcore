#!/usr/bin/env python3
"""
Merge conflicts by combining multiple generated files into target files.

This script intelligently merges conflicting files based on their content.
"""
import sys
from pathlib import Path
from typing import List, Dict

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.lead_contractor.integrate_backlog import (
    scan_backlog, generate_integration_plan, clean_markdown_code_blocks
)

def merge_parts_files(sources: List[Dict]) -> str:
    """
    Merge multiple parts-related files into a single parts.py file.
    
    Strategy:
    1. Use the package docstring from Parts_ModelsPackage (or first file)
    2. Combine all imports (deduplicated)
    3. Combine all classes and functions
    4. Ensure proper ordering (PartType, Part, MessageRole, Message, Artifact)
    """
    imports = set()
    classes = {}
    functions = {}
    docstring = None
    
    # Process each source file
    for src in sources:
        src_path = Path(src['source'])
        if not src_path.exists():
            continue
        
        with open(src_path, 'r', encoding='utf-8') as f:
            content = clean_markdown_code_blocks(f.read())
        
        lines = content.split('\n')
        
        # Extract docstring
        if not docstring and content.strip().startswith('"""'):
            doc_end = content.find('"""', 3)
            if doc_end > 0:
                docstring = content[3:doc_end].strip()
        
        # Extract imports
        for line in lines:
            line = line.strip()
            if line.startswith('import ') or line.startswith('from '):
                imports.add(line)
        
        # Extract classes and functions (simple heuristic)
        in_class = None
        in_function = None
        class_lines = []
        function_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Class definition
            if stripped.startswith('class '):
                # Save previous class/function if any
                if in_class:
                    classes[in_class] = '\n'.join(class_lines)
                if in_function:
                    functions[in_function] = '\n'.join(function_lines)
                
                # Start new class
                class_name = stripped.split('(')[0].split(':')[0].replace('class ', '').strip()
                in_class = class_name
                class_lines = [line]
                in_function = None
                function_lines = []
            
            # Function definition
            elif stripped.startswith('def ') and not in_class:
                if in_function:
                    functions[in_function] = '\n'.join(function_lines)
                
                func_name = stripped.split('(')[0].replace('def ', '').strip()
                in_function = func_name
                function_lines = [line]
            
            # Continue collecting lines
            elif in_class:
                class_lines.append(line)
                if stripped and not stripped.startswith(' ') and not stripped.startswith('\t'):
                    if not stripped.startswith('@') and not stripped.startswith('class '):
                        # End of class
                        classes[in_class] = '\n'.join(class_lines)
                        in_class = None
                        class_lines = []
            
            elif in_function:
                function_lines.append(line)
                if stripped and not stripped.startswith(' ') and not stripped.startswith('\t'):
                    if not stripped.startswith('@') and not stripped.startswith('def '):
                        # End of function
                        functions[in_function] = '\n'.join(function_lines)
                        in_function = None
                        function_lines = []
        
        # Save last class/function
        if in_class:
            classes[in_class] = '\n'.join(class_lines)
        if in_function:
            functions[in_function] = '\n'.join(function_lines)
    
    # Build merged content
    result = []
    
    # Docstring
    if docstring:
        result.append(f'"""{docstring}"""')
    else:
        result.append('"""ContextCore Data Models - A2A-compatible with ContextCore extensions."""')
    
    result.append('')
    
    # Imports (sorted)
    sorted_imports = sorted(imports)
    for imp in sorted_imports:
        result.append(imp)
    
    result.append('')
    
    # Classes in order: PartType, Part, MessageRole, Message, Artifact
    class_order = ['PartType', 'Part', 'MessageRole', 'Message', 'Artifact']
    for class_name in class_order:
        if class_name in classes:
            result.append(classes[class_name])
            result.append('')
    
    # Other classes
    for class_name, class_content in sorted(classes.items()):
        if class_name not in class_order:
            result.append(class_content)
            result.append('')
    
    # Functions
    for func_name, func_content in sorted(functions.items()):
        result.append(func_content)
        result.append('')
    
    return '\n'.join(result)

def merge_otel_genai_files(sources: List[Dict]) -> str:
    """
    Merge OTel GenAI files - prioritize Foundation_DualEmit as it's the correct implementation.
    """
    # Find Foundation_DualEmit first (it's the correct one)
    for src in sources:
        if 'dual' in src['feature'].lower() or 'emit' in src['feature'].lower():
            src_path = Path(src['source'])
            if src_path.exists():
                with open(src_path, 'r', encoding='utf-8') as f:
                    return clean_markdown_code_blocks(f.read())
    
    # Fallback: use first available file
    for src in sources:
        src_path = Path(src['source'])
        if src_path.exists():
            with open(src_path, 'r', encoding='utf-8') as f:
                return clean_markdown_code_blocks(f.read())
    
    return ""

def merge_handoff_files(sources: List[Dict]) -> str:
    """
    Merge handoff files - need to examine which is more complete.
    """
    # Read both files and compare
    files_content = []
    for src in sources:
        src_path = Path(src['source'])
        if src_path.exists():
            with open(src_path, 'r', encoding='utf-8') as f:
                content = clean_markdown_code_blocks(f.read())
                files_content.append((src['feature'], len(content), content))
    
    # Use the larger/more complete file
    if files_content:
        files_content.sort(key=lambda x: x[1], reverse=True)
        return files_content[0][2]
    
    return ""

def merge_installtracking_statefile_files(sources: List[Dict]) -> str:
    """
    Merge install tracking statefile - use the larger/more complete one.
    """
    files_content = []
    for src in sources:
        src_path = Path(src['source'])
        if src_path.exists():
            with open(src_path, 'r', encoding='utf-8') as f:
                content = clean_markdown_code_blocks(f.read())
                files_content.append((src['feature'], len(content), content))
    
    if files_content:
        files_content.sort(key=lambda x: x[1], reverse=True)
        return files_content[0][2]
    
    return ""

def main():
    """Main merge function."""
    files = scan_backlog()
    plan = generate_integration_plan(files)
    
    conflicts = plan.get('conflicts', {})
    duplicate_targets = plan.get('duplicate_targets', {})
    
    if not conflicts:
        print("No conflicts to merge!")
        return
    
    print(f"Found {len(conflicts)} conflict(s) to merge\n")
    
    # Merge each conflict
    merged_files = {}
    
    for target_str, conflict_info in conflicts.items():
        target_path = Path(target_str)
        sources = duplicate_targets.get(target_str, [])
        
        print(f"Merging: {target_path.relative_to(PROJECT_ROOT)}")
        print(f"  Sources: {len(sources)} files")
        
        # Choose merge strategy based on target
        target_name = target_path.name
        
        if target_name == 'parts.py':
            merged_content = merge_parts_files(sources)
        elif target_name == 'otel_genai.py':
            merged_content = merge_otel_genai_files(sources)
        elif target_name == 'handoff.py':
            merged_content = merge_handoff_files(sources)
        elif 'installtracking_statefile' in target_name:
            merged_content = merge_installtracking_statefile_files(sources)
        else:
            # Default: use largest file
            files_content = []
            for src in sources:
                src_path = Path(src['source'])
                if src_path.exists():
                    with open(src_path, 'r', encoding='utf-8') as f:
                        content = clean_markdown_code_blocks(f.read())
                        files_content.append((len(content), content))
            
            if files_content:
                files_content.sort(key=lambda x: x[0], reverse=True)
                merged_content = files_content[0][1]
            else:
                merged_content = ""
        
        if merged_content:
            merged_files[target_path] = merged_content
            print(f"  ✓ Merged {len(merged_content)} bytes")
        else:
            print(f"  ✗ Failed to merge")
    
    # Write merged files
    print(f"\nWriting {len(merged_files)} merged file(s)...")
    for target_path, content in merged_files.items():
        # Create backup
        if target_path.exists():
            backup = target_path.with_suffix(f"{target_path.suffix}.backup")
            import shutil
            shutil.copy2(target_path, backup)
            print(f"  Backed up: {backup.name}")
        
        # Write merged content
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ Wrote: {target_path.relative_to(PROJECT_ROOT)}")

if __name__ == '__main__':
    main()
