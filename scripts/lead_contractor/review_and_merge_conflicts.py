#!/usr/bin/env python3
"""
Review and merge conflicts one at a time.

This script helps review conflicts and merge them interactively.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.lead_contractor.integrate_backlog import (
    scan_backlog, generate_integration_plan, show_file_preview, 
    analyze_file_content, compare_files_for_conflicts
)

def show_conflict_details(target_path: Path, sources: list, conflict_info: dict):
    """Show detailed information about a conflict."""
    print(f"\n{'='*70}")
    print(f"CONFLICT: {target_path.relative_to(PROJECT_ROOT)}")
    print(f"{'='*70}")
    print(f"Risk Level: {conflict_info.get('max_risk_level', 'UNKNOWN')}")
    print(f"Risk Score: {conflict_info.get('max_risk_score', 0)}/100")
    print(f"Number of conflicting files: {len(sources)}")
    
    # Show current target if exists
    if target_path.exists():
        print(f"\nCurrent target file:")
        target_analysis = analyze_file_content(target_path)
        if 'error' not in target_analysis:
            print(f"  Size: {target_analysis['size']:,} bytes")
            print(f"  Lines: {target_analysis['lines']:,}")
            print(f"  Classes: {len(target_analysis['classes'])}")
            print(f"  Functions: {len(target_analysis['functions'])}")
            if target_analysis['classes']:
                print(f"  Classes: {', '.join(list(target_analysis['classes'])[:5])}")
    
    # Show each source file
    print(f"\nSource files:")
    for i, src in enumerate(sources, 1):
        src_path = Path(src['source'])
        print(f"\n[{i}] {src['feature']}")
        print(f"    File: {src_path}")
        if src_path.exists():
            src_analysis = analyze_file_content(src_path)
            if 'error' not in src_analysis:
                print(f"    Size: {src_analysis['size']:,} bytes")
                print(f"    Lines: {src_analysis['lines']:,}")
                print(f"    Classes: {len(src_analysis['classes'])}")
                print(f"    Functions: {len(src_analysis['functions'])}")
                if src_analysis['classes']:
                    print(f"    Classes: {', '.join(list(src_analysis['classes'])[:5])}")
                if src_analysis['functions']:
                    print(f"    Functions: {', '.join(list(src_analysis['functions'])[:5])}")
        else:
            print(f"    ⚠️  FILE NOT FOUND")
    
    # Show conflict details
    if conflict_info.get('conflicts'):
        print(f"\nConflict Analysis:")
        worst = max(conflict_info['conflicts'], key=lambda c: c.get('risk_score', 0))
        print(f"  Worst conflict: {worst.get('feature1')} vs {worst.get('feature2')}")
        if worst.get('classes_removed'):
            removed = list(worst['classes_removed'])[:5]
            print(f"  ⚠️  Would remove classes: {', '.join(removed)}")
        if worst.get('functions_removed'):
            removed = list(worst['functions_removed'])[:5]
            print(f"  ⚠️  Would remove functions: {', '.join(removed)}")
        if worst.get('size_diff_percent', 0) > 20:
            print(f"  ⚠️  Size difference: {worst['size_diff_percent']:.1f}%")

def main():
    files = scan_backlog()
    plan = generate_integration_plan(files)
    
    conflicts = plan.get('conflicts', {})
    duplicate_targets = plan.get('duplicate_targets', {})
    
    if not conflicts:
        print("No conflicts found!")
        return
    
    print(f"\nFound {len(conflicts)} conflict(s) to resolve")
    print("="*70)
    
    # Sort by risk score (highest first)
    sorted_conflicts = sorted(
        conflicts.items(),
        key=lambda x: x[1].get('max_risk_score', 0),
        reverse=True
    )
    
    for idx, (target_str, conflict_info) in enumerate(sorted_conflicts, 1):
        target_path = Path(target_str)
        sources = duplicate_targets.get(target_str, [])
        
        print(f"\n\nCONFLICT {idx}/{len(conflicts)}")
        show_conflict_details(target_path, sources, conflict_info)
        
        print(f"\n{'='*70}")
        print("Options:")
        print("  [1-N] View file preview (enter number)")
        print("  [s] Skip this conflict")
        print("  [q] Quit")
        
        choice = input("\nSelect option: ").strip().lower()
        
        if choice == 'q':
            print("Quitting...")
            break
        elif choice == 's':
            print("Skipping this conflict")
            continue
        elif choice.isdigit():
            file_idx = int(choice) - 1
            if 0 <= file_idx < len(sources):
                src_path = Path(sources[file_idx]['source'])
                print(f"\nPreview of {sources[file_idx]['feature']}:")
                show_file_preview(src_path, max_lines=50)
            else:
                print("Invalid file number")
        else:
            print("Invalid option")

if __name__ == '__main__':
    main()
