#!/usr/bin/env python3
"""Analyze conflicts in the backlog."""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.lead_contractor.integrate_backlog import scan_backlog, generate_integration_plan

def main():
    files = scan_backlog()
    plan = generate_integration_plan(files)

    print('='*70)
    print('CONFLICT ANALYSIS')
    print('='*70)
    print(f'Total files: {len(files)}')
    print(f'Files to integrate: {len(plan["files"])}')
    print(f'Already integrated: {len(plan["already_integrated"])}')
    print(f'Duplicate targets: {len(plan.get("duplicate_targets", {}))}')
    print(f'Conflicts detected: {len(plan.get("conflicts", {}))}')
    print()

    if plan.get('conflicts'):
        print('CONFLICTS FOUND:')
        print('-'*70)
        for target_str, conflict_info in plan['conflicts'].items():
            target_rel = Path(target_str).relative_to(Path.cwd())
            print(f'\n📁 {target_rel}')
            print(f'   Risk Level: {conflict_info.get("max_risk_level", "UNKNOWN")}')
            print(f'   Risk Score: {conflict_info.get("max_risk_score", 0)}/100')
            print(f'   Files: {conflict_info.get("file_count", 0)}')
            
            sources = plan['duplicate_targets'].get(target_str, [])
            for src in sources:
                print(f'     • {src["feature"]}')
            
            if conflict_info.get('conflicts'):
                worst = max(conflict_info['conflicts'], key=lambda c: c.get('risk_score', 0))
                print(f'   Worst conflict: {worst.get("feature1")} vs {worst.get("feature2")}')
                if worst.get('classes_removed'):
                    removed = list(worst['classes_removed'])[:3]
                    print(f'     ⚠️  Would remove classes: {", ".join(removed)}')
                if worst.get('functions_removed'):
                    removed = list(worst['functions_removed'])[:3]
                    print(f'     ⚠️  Would remove functions: {", ".join(removed)}')
                if worst.get('size_diff_percent', 0) > 20:
                    print(f'     ⚠️  Size difference: {worst["size_diff_percent"]:.1f}%')
    else:
        print('No conflicts detected!')
    
    return plan

if __name__ == '__main__':
    main()
