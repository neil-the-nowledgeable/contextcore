#!/usr/bin/env python3
"""
Beaver (startd8) workflow for integrating backlog and completing the full cycle.

This workflow:
1. Runs lead_contractor integrate backlog
2. Reviews integrated files
3. Updates imports/exports as needed
4. Runs tests (python3 -m pytest) and fixes errors
5. Commits changes once successful

Usage:
    python3 scripts/lead_contractor/run_integrate_backlog_workflow.py
    python3 scripts/lead_contractor/run_integrate_backlog_workflow.py --feature graph_schema
    python3 scripts/lead_contractor/run_integrate_backlog_workflow.py --dry-run
    python3 scripts/lead_contractor/run_integrate_backlog_workflow.py --skip-tests
    python3 scripts/lead_contractor/run_integrate_backlog_workflow.py --no-commit
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import integrate_backlog functions
from scripts.lead_contractor.integrate_backlog import (
    scan_backlog,
    generate_integration_plan,
    integrate_file,
    infer_target_path,
    GeneratedFile,
    resolve_conflict_interactive,
    show_file_preview,
    merge_files_automatically,
)


def review_integrated_files(plan: Dict) -> List[Dict]:
    """
    Review integrated files for common issues.
    
    Returns:
        List of issues found with file paths and descriptions
    """
    issues = []
    
    for item in plan.get('files', []):
        target_path = Path(item['target'])
        
        if not target_path.exists():
            continue
            
        try:
            with open(target_path, 'r') as f:
                content = f.read()
            
            # Check for common issues
            file_issues = []
            
            # Check for missing imports
            if 'import' not in content and len(content) > 100:
                file_issues.append("No imports found - may need imports")
            
            # Check for syntax errors (basic check)
            if content.count('(') != content.count(')'):
                file_issues.append("Unmatched parentheses")
            if content.count('[') != content.count(']'):
                file_issues.append("Unmatched brackets")
            if content.count('{') != content.count('}'):
                file_issues.append("Unmatched braces")
            
            # Check for TODO/FIXME comments
            if 'TODO' in content or 'FIXME' in content:
                file_issues.append("Contains TODO/FIXME comments")
            
            if file_issues:
                issues.append({
                    'file': str(target_path.relative_to(PROJECT_ROOT)),
                    'issues': file_issues
                })
                
        except Exception as e:
            issues.append({
                'file': str(target_path.relative_to(PROJECT_ROOT)),
                'issues': [f"Error reading file: {e}"]
            })
    
    return issues


def update_imports_exports(plan: Dict, dry_run: bool = False) -> Dict:
    """
    Update imports/exports in integrated files.
    
    Returns:
        Dict with update statistics
    """
    stats = {
        'files_updated': 0,
        'imports_added': 0,
        'exports_updated': 0,
        'errors': []
    }
    
    for item in plan.get('files', []):
        target_path = Path(item['target'])
        
        if not target_path.exists():
            continue
        
        # Only process Python files for now
        if target_path.suffix != '.py':
            continue
        
        try:
            with open(target_path, 'r') as f:
                content = f.read()
            
            original_content = content
            updated = False
            
            # Check if file needs __all__ export list
            if '__all__' not in content and ('def ' in content or 'class ' in content):
                # Extract public definitions
                public_defs = []
                for match in re.finditer(r'^(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)', content, re.MULTILINE):
                    if not match.group(2).startswith('_'):
                        public_defs.append(match.group(2))
                
                if public_defs and '__init__.py' not in str(target_path):
                    # Add __all__ after imports
                    import_end = content.find('\n\n')
                    if import_end > 0:
                        __all__ = f"\n__all__ = {public_defs}\n"
                        content = content[:import_end] + __all__ + content[import_end:]
                        updated = True
                        stats['exports_updated'] += 1
            
            # Check for common missing imports based on usage
            missing_imports = []
            
            # Check for Path usage
            if 'Path(' in content and 'from pathlib import Path' not in content and 'import Path' not in content:
                missing_imports.append('from pathlib import Path')
            
            # Check for json usage
            if 'json.' in content and 'import json' not in content:
                missing_imports.append('import json')
            
            # Check for typing usage
            if re.search(r':\s*(List|Dict|Optional|Union|Any)\[', content) and 'from typing import' not in content:
                missing_imports.append('from typing import List, Dict, Optional, Union, Any')
            
            if missing_imports:
                # Add imports at the top after existing imports
                import_section_end = 0
                for line_num, line in enumerate(content.split('\n')):
                    if line.strip().startswith('import ') or line.strip().startswith('from '):
                        import_section_end = line_num + 1
                    elif line.strip() and import_section_end > 0:
                        break
                
                if import_section_end > 0:
                    lines = content.split('\n')
                    new_imports = '\n'.join(missing_imports)
                    lines.insert(import_section_end, new_imports)
                    content = '\n'.join(lines)
                    updated = True
                    stats['imports_added'] += len(missing_imports)
            
            if updated and not dry_run:
                with open(target_path, 'w') as f:
                    f.write(content)
                stats['files_updated'] += 1
                print(f"  ✓ Updated imports/exports: {target_path.relative_to(PROJECT_ROOT)}")
            elif updated and dry_run:
                print(f"  [DRY RUN] Would update imports/exports: {target_path.relative_to(PROJECT_ROOT)}")
                
        except Exception as e:
            stats['errors'].append(f"{target_path}: {e}")
    
    return stats


def run_tests(dry_run: bool = False, max_attempts: int = 3) -> Dict:
    """
    Run pytest and attempt to fix errors.
    
    Returns:
        Dict with test results and fix attempts
    """
    result = {
        'success': False,
        'attempts': 0,
        'errors': [],
        'fixed': []
    }
    
    if dry_run:
        print("  [DRY RUN] Would run: python3 -m pytest")
        return result
    
    for attempt in range(1, max_attempts + 1):
        result['attempts'] = attempt
        print(f"\n  Running tests (attempt {attempt}/{max_attempts})...")
        
        # Run pytest
        test_result = subprocess.run(
            ['python3', '-m', 'pytest', '-v', '--tb=short'],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )
        
        if test_result.returncode == 0:
            print("  ✓ All tests passed!")
            result['success'] = True
            return result
        
        # Parse errors
        error_output = test_result.stderr + test_result.stdout
        result['errors'].append(error_output)
        
        # Try to fix common issues
        fixes_applied = False
        
        # Extract file paths from error messages
        error_files = set()
        for line in error_output.split('\n'):
            # Look for file paths in errors
            match = re.search(r'([a-zA-Z0-9_/]+\.py):(\d+)', line)
            if match:
                error_files.add(match.group(1))
        
        # Try to fix import errors
        for file_path_str in error_files:
            file_path = PROJECT_ROOT / file_path_str
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Fix common import issues
                    if 'ImportError' in error_output or 'ModuleNotFoundError' in error_output:
                        # Try to add missing imports
                        # This is a simplified fix - in practice, you'd need more sophisticated analysis
                        if 'from contextcore' in error_output and 'from contextcore' not in content:
                            # This is too simplistic, but demonstrates the pattern
                            pass
                    
                    # Fix syntax errors if detected
                    if 'SyntaxError' in error_output:
                        # Basic syntax fixes
                        # Remove trailing commas in function calls
                        content = re.sub(r',\s*\)', ')', content)
                        # Fix common indentation issues
                        # (would need more sophisticated parsing)
                        
                        with open(file_path, 'w') as f:
                            f.write(content)
                        fixes_applied = True
                        result['fixed'].append(str(file_path.relative_to(PROJECT_ROOT)))
                        
                except Exception as e:
                    result['errors'].append(f"Error fixing {file_path}: {e}")
        
        if not fixes_applied:
            print(f"  ✗ Tests failed and no automatic fixes could be applied")
            print(f"  Error output:\n{error_output[:500]}...")
            break
        
        print(f"  Applied fixes, retrying tests...")
    
    return result


def commit_changes(plan: Dict, message: Optional[str] = None, dry_run: bool = False) -> bool:
    """
    Commit integrated changes to git.
    
    Returns:
        True if commit successful, False otherwise
    """
    if dry_run:
        print("  [DRY RUN] Would commit changes")
        return True
    
    # Check if we're in a git repo
    git_check = subprocess.run(
        ['git', 'rev-parse', '--git-dir'],
        capture_output=True,
        cwd=PROJECT_ROOT
    )
    
    if git_check.returncode != 0:
        print("  ⚠️  Not in a git repository, skipping commit")
        return False
    
    # Check if there are changes to commit
    status_check = subprocess.run(
        ['git', 'status', '--porcelain'],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT
    )
    
    if not status_check.stdout.strip():
        print("  ✓ No changes to commit")
        return True
    
    # Stage all changes
    subprocess.run(['git', 'add', '-A'], cwd=PROJECT_ROOT)
    
    # Generate commit message
    if not message:
        files_count = len(plan.get('files', []))
        message = f"Integrate backlog: {files_count} file(s) integrated"
    
    # Commit
    commit_result = subprocess.run(
        ['git', 'commit', '-m', message],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT
    )
    
    if commit_result.returncode == 0:
        print(f"  ✓ Committed changes: {message}")
        return True
    else:
        print(f"  ✗ Failed to commit: {commit_result.stderr}")
        return False


def main():
    """Main workflow execution."""
    parser = argparse.ArgumentParser(
        description="Beaver workflow: Integrate backlog and complete full cycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full workflow with all steps
  %(prog)s
  
  # Interactive conflict resolution (recommended for conflicts)
  %(prog)s --interactive-conflicts
  
  # Dry run to preview
  %(prog)s --dry-run
  
  # Skip tests (for faster iteration)
  %(prog)s --skip-tests
  
  # Don't commit (review first)
  %(prog)s --no-commit
  
  # Process specific feature
  %(prog)s --feature graph_schema
        """
    )
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview changes without executing")
    parser.add_argument("--feature", type=str,
                       help="Process specific feature (partial match)")
    parser.add_argument("--skip-tests", action="store_true",
                       help="Skip running tests")
    parser.add_argument("--no-commit", action="store_true",
                       help="Don't commit changes")
    parser.add_argument("--auto", action="store_true",
                       help="Auto-integrate without confirmation")
    parser.add_argument("--interactive-conflicts", action="store_true",
                       help="Interactively resolve conflicts one at a time")
    parser.add_argument("--auto-merge", action="store_true",
                       help="Automatically merge files when merge opportunities are detected")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Beaver Workflow: Integrate Backlog")
    print("=" * 70)
    print()
    
    # Step 1: Run integrate backlog
    print("Step 1: Running integrate backlog...")
    print("-" * 70)
    
    # Import and run integrate_backlog logic
    files = scan_backlog()
    
    if not files:
        print("No generated files found.")
        return
    
    print(f"Found {len(files)} generated file(s)")
    
    plan = generate_integration_plan(files, feature_filter=args.feature)
    
    if not plan['files']:
        print("No files to integrate.")
        return
    
    print(f"Files to integrate: {len(plan['files'])}")
    print(f"Already integrated: {len(plan.get('already_integrated', []))}")
    
    # Show conflict status
    conflicts = plan.get('conflicts', {})
    merge_opportunities = plan.get('merge_opportunities', {})
    
    if not conflicts:
        print(f"\n✅ No conflicts detected - all clear for integration!")
        if merge_opportunities:
            print(f"   Merge opportunities: {len(merge_opportunities)} (will be handled automatically)")
    else:
        conflict_count = len(conflicts)
        high_risk = sum(1 for c in conflicts.values() if c.get('max_risk_level') == 'HIGH')
        print(f"\n⚠️  Conflicts detected: {conflict_count} ({high_risk} high-risk)")
    
    # Handle merge opportunities automatically
    if plan.get('merge_opportunities'):
        print(f"\n{'='*70}")
        print("MERGE OPPORTUNITIES DETECTED")
        print(f"{'='*70}")
        print(f"Found {len(plan['merge_opportunities'])} merge opportunity(ies)")
        
        for target_str, merge_info in plan['merge_opportunities'].items():
            target_path = Path(target_str)
            sources = merge_info['sources']
            
            print(f"\nMerging: {target_path.relative_to(PROJECT_ROOT)}")
            print(f"  Sources: {len(sources)} files")
            for src in sources:
                print(f"    • {src['feature']}")
            
            if args.dry_run:
                print(f"  [DRY RUN] Would merge {len(sources)} files")
            elif args.auto or args.auto_merge:
                # Auto-merge
                merged_content = merge_files_automatically(
                    target_path,
                    sources,
                    strategy=merge_info['strategy']
                )
                
                if merged_content:
                    # Create backup
                    if target_path.exists():
                        backup = target_path.with_suffix(f"{target_path.suffix}.backup")
                        shutil.copy2(target_path, backup)
                        print(f"  Backed up existing file to {backup.name}")
                    
                    # Write merged content
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(target_path, 'w', encoding='utf-8') as f:
                        f.write(merged_content)
                    
                    print(f"  ✓ Auto-merged {len(sources)} files")
                else:
                    print(f"  ✗ Failed to merge files")
            else:
                # Ask for confirmation
                response = input(f"\n  Auto-merge {len(sources)} files? (yes/no): ")
                if response.lower() in ('yes', 'y'):
                    merged_content = merge_files_automatically(
                        target_path,
                        sources,
                        strategy=merge_info['strategy']
                    )
                    
                    if merged_content:
                        # Create backup
                        if target_path.exists():
                            backup = target_path.with_suffix(f"{target_path.suffix}.backup")
                            shutil.copy2(target_path, backup)
                            print(f"  Backed up existing file to {backup.name}")
                        
                        # Write merged content
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(target_path, 'w', encoding='utf-8') as f:
                            f.write(merged_content)
                        
                        print(f"  ✓ Merged {len(sources)} files")
                    else:
                        print(f"  ✗ Failed to merge files")
                else:
                    print(f"  Skipped merge")
        
        # Remove merged files from plan['files'] to avoid duplicate integration
        merged_targets = set(plan['merge_opportunities'].keys())
        plan['files'] = [
            item for item in plan['files']
            if item['target'] not in merged_targets
        ]
    
    # Handle conflicts interactively if requested
    if args.interactive_conflicts and plan.get('duplicate_targets'):
        # Check if there are actual conflicts (not just merge opportunities)
        actual_conflicts = {
            k: v for k, v in plan.get('duplicate_targets', {}).items()
            if k in plan.get('conflicts', {})
        }
        
        if not actual_conflicts:
            print(f"\n✅ No conflicts to resolve interactively!")
            print(f"   All duplicate targets are merge opportunities (handled automatically)")
        else:
            print(f"\n{'='*70}")
            print("INTERACTIVE CONFLICT RESOLUTION MODE")
            print(f"{'='*70}")
            print("Conflicting files will be resolved one at a time.")
            
            # Separate conflicting files from non-conflicting ones
            conflicting_targets = set(actual_conflicts.keys())
            non_conflicting_files = [
                item for item in plan['files']
                if item['target'] not in conflicting_targets
            ]
            
            # Build conflicting_files_by_target from actual conflicts
            conflicting_files_by_target = {}
            for target_str, source_files in actual_conflicts.items():
                # Filter to only include files that are in plan['files'] (not already integrated)
                conflicting_files_by_target[target_str] = [
                    item for item in plan['files']
                    if item['target'] == target_str
                ]
            
            print(f"\nNon-conflicting files: {len(non_conflicting_files)}")
            print(f"Conflicts to resolve: {len(conflicting_files_by_target)}")
        
            # Integrate non-conflicting files first
            if non_conflicting_files and not args.dry_run:
                if not args.auto:
                    response = input(f"\nIntegrate {len(non_conflicting_files)} non-conflicting files first? (yes/no): ")
                    if response.lower() not in ('yes', 'y'):
                        print("Skipping non-conflicting files.")
                    else:
                        print(f"\nIntegrating non-conflicting files...")
                        for item in non_conflicting_files:
                            integrate_file(Path(item['source']), Path(item['target']), dry_run=False)
            
            # Resolve conflicts one at a time
            resolved_files = []
            skipped_targets = []
            
            for target_str, source_files in conflicting_files_by_target.items():
                target_path = Path(target_str)
                # Convert source_files to the format expected by resolve_conflict_interactive
                source_files_formatted = [
                    {'source': item['source'], 'feature': item['feature']}
                    for item in source_files
                ]
                selected = resolve_conflict_interactive(target_path, source_files_formatted, plan)
                
                if selected is None:
                    print(f"  Skipped conflict for {target_path.relative_to(PROJECT_ROOT)}")
                    skipped_targets.append(target_str)
                    continue
                
                # Integrate selected file
                if not args.dry_run:
                    source_path = Path(selected['source'])
                    if integrate_file(source_path, target_path, dry_run=False):
                        resolved_files.append(selected)
                        print(f"  ✓ Resolved conflict by integrating {selected['feature']}")
                    else:
                        print(f"  ✗ Failed to integrate {selected['feature']}")
                else:
                    print(f"  [DRY RUN] Would integrate {selected['feature']}")
                    resolved_files.append(selected)
            
            print(f"\n{'='*70}")
            print("Conflict Resolution Summary")
            print(f"{'='*70}")
            print(f"  Resolved: {len(resolved_files)}")
            print(f"  Skipped: {len(skipped_targets)}")
            
            if skipped_targets:
                print(f"\n  Skipped targets:")
                for target_str in skipped_targets:
                    print(f"    - {Path(target_str).relative_to(PROJECT_ROOT)}")
            
            # Update plan to reflect resolved conflicts
            plan['files'] = non_conflicting_files + [
                {'source': str(Path(f['source'])), 'target': f['target'], 'feature': f['feature']}
                for f in resolved_files
            ]
        
    else:
        # Original behavior: show conflicts but don't resolve interactively
        if plan.get('conflicts'):
            high_risk_count = sum(1 for c in plan['conflicts'].values() 
                                if c.get('max_risk_level') == 'HIGH')
            medium_risk_count = sum(1 for c in plan['conflicts'].values() 
                                   if c.get('max_risk_level') == 'MEDIUM')
            
            print(f"\n🚨 CONFLICT ANALYSIS:")
            print(f"  High-risk conflicts: {high_risk_count}")
            print(f"  Medium-risk conflicts: {medium_risk_count}")
            
            if high_risk_count > 0:
                print(f"\n  ⚠️  {high_risk_count} HIGH-RISK conflict(s) detected!")
                print("     These may cause regressions (code loss, overwrites)")
                print("     Use --interactive-conflicts to resolve manually")
                
                # Show high-risk conflicts
                for target_str, conflict_info in plan['conflicts'].items():
                    if conflict_info.get('max_risk_level') == 'HIGH':
                        target_rel = Path(target_str).relative_to(PROJECT_ROOT)
                        print(f"\n     📁 {target_rel} (Risk Score: {conflict_info.get('max_risk_score', 0)}/100)")
                        sources = plan['duplicate_targets'].get(target_str, [])
                        for src in sources:
                            print(f"        • {src['feature']}")
            
            if not args.auto and high_risk_count > 0:
                print(f"\n  ⚠️  High-risk conflicts detected. Integration may cause regressions.")
                print(f"  Use --interactive-conflicts to resolve conflicts manually.")
                response = input("  Continue anyway? (yes/no): ")
                if response.lower() not in ('yes', 'y'):
                    print("Cancelled due to high-risk conflicts.")
                    return
        else:
            # No conflicts - show success message
            if merge_opportunities:
                print(f"\n✅ No conflicts detected!")
                print(f"   {len(merge_opportunities)} merge opportunity(ies) will be handled automatically")
            else:
                print(f"\n✅ No conflicts or merge opportunities - ready for integration!")
        
        # Warn about duplicate targets (even if not high risk)
        # Only show if there are actual conflicts, not just merge opportunities
        if plan.get('duplicate_targets') and plan.get('conflicts'):
            non_conflict_duplicates = {k: v for k, v in plan['duplicate_targets'].items() 
                                      if k not in plan.get('conflicts', {})}
            if non_conflict_duplicates:
                print(f"\n⚠️  Warning: {len(non_conflict_duplicates)} target(s) have multiple source files:")
                for target, sources in list(non_conflict_duplicates.items())[:3]:
                    print(f"  • {Path(target).relative_to(PROJECT_ROOT)}: {len(sources)} files")
                    for src in sources[:2]:
                        print(f"    - {src['feature']}")
                if len(non_conflict_duplicates) > 3:
                    print(f"  ... and {len(non_conflict_duplicates) - 3} more")
                print("  Note: Last file integrated will overwrite previous ones.")
                print("  Use --interactive-conflicts to choose which file to integrate.")
        
        if args.dry_run:
            print("\n[DRY RUN MODE - No files will be modified]")
            for item in plan['files']:
                integrate_file(Path(item['source']), Path(item['target']), dry_run=True)
        else:
            if not args.auto:
                response = input("\nProceed with integration? (yes/no): ")
                if response.lower() not in ('yes', 'y'):
                    print("Cancelled.")
                    return
            
            integrated = 0
            for item in plan['files']:
                if integrate_file(Path(item['source']), Path(item['target']), dry_run=False):
                    integrated += 1
            
            print(f"\n✓ Integrated {integrated} file(s)")
    
    # Step 2: Review integrated files
    print("\n" + "=" * 70)
    print("Step 2: Reviewing integrated files...")
    print("-" * 70)
    
    issues = review_integrated_files(plan)
    
    if issues:
        print(f"Found {len(issues)} file(s) with potential issues:")
        for issue in issues:
            print(f"  • {issue['file']}")
            for item in issue['issues']:
                print(f"    - {item}")
    else:
        print("✓ No issues found in integrated files")
    
    # Step 3: Update imports/exports
    print("\n" + "=" * 70)
    print("Step 3: Updating imports/exports...")
    print("-" * 70)
    
    import_stats = update_imports_exports(plan, dry_run=args.dry_run)
    
    if import_stats['files_updated'] > 0:
        print(f"✓ Updated {import_stats['files_updated']} file(s)")
        print(f"  - Added {import_stats['imports_added']} import(s)")
        print(f"  - Updated {import_stats['exports_updated']} export(s)")
    else:
        print("✓ No import/export updates needed")
    
    if import_stats['errors']:
        print(f"\n⚠️  {len(import_stats['errors'])} error(s) during import updates:")
        for error in import_stats['errors']:
            print(f"  - {error}")
    
    # Step 4: Run tests
    if not args.skip_tests:
        print("\n" + "=" * 70)
        print("Step 4: Running tests...")
        print("-" * 70)
        
        test_result = run_tests(dry_run=args.dry_run)
        
        if test_result['success']:
            print("✓ All tests passed!")
        else:
            print(f"✗ Tests failed after {test_result['attempts']} attempt(s)")
            if test_result['fixed']:
                print(f"  Fixed {len(test_result['fixed'])} file(s):")
                for fixed_file in test_result['fixed']:
                    print(f"    - {fixed_file}")
            
            if not args.dry_run:
                print("\n⚠️  Some tests failed. Please review and fix manually.")
                print("  You can run: python3 -m pytest -v")
                if not args.no_commit:
                    response = input("\nCommit changes anyway? (yes/no): ")
                    if response.lower() not in ('yes', 'y'):
                        print("Skipping commit due to test failures.")
                        return
    else:
        print("\n" + "=" * 70)
        print("Step 4: Skipping tests (--skip-tests)")
        print("-" * 70)
    
    # Step 5: Commit changes
    if not args.no_commit:
        print("\n" + "=" * 70)
        print("Step 5: Committing changes...")
        print("-" * 70)
        
        commit_success = commit_changes(plan, dry_run=args.dry_run)
        
        if commit_success:
            print("✓ Workflow completed successfully!")
        else:
            print("✗ Failed to commit changes")
    else:
        print("\n" + "=" * 70)
        print("Step 5: Skipping commit (--no-commit)")
        print("-" * 70)
        print("✓ Workflow completed (changes not committed)")
    
    print("\n" + "=" * 70)
    print("Workflow Summary")
    print("=" * 70)
    print(f"  Files integrated: {len(plan['files'])}")
    print(f"  Files reviewed: {len(plan['files'])}")
    print(f"  Import/export updates: {import_stats['files_updated']}")
    if not args.skip_tests:
        test_status = 'PASSED' if test_result.get('success') else 'FAILED'
        print(f"  Tests: {test_status}")
    else:
        print(f"  Tests: SKIPPED")
    print(f"  Commit: {'YES' if not args.no_commit and not args.dry_run else 'SKIPPED'}")


if __name__ == "__main__":
    main()
