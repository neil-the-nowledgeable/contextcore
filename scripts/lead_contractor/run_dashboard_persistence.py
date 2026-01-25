#!/usr/bin/env python3
"""
Run Lead Contractor workflow for Dashboard & Persistence Architecture.

Usage:
    # Run all phases (1-9)
    python3 scripts/lead_contractor/run_dashboard_persistence.py

    # Run specific phase group
    python3 scripts/lead_contractor/run_dashboard_persistence.py --phases 1-3
    python3 scripts/lead_contractor/run_dashboard_persistence.py --phases 4-6
    python3 scripts/lead_contractor/run_dashboard_persistence.py --phases 7-9

    # Dry run (list features without executing)
    python3 scripts/lead_contractor/run_dashboard_persistence.py --dry-run

    # Force re-run even if results exist
    python3 scripts/lead_contractor/run_dashboard_persistence.py --force
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.lead_contractor.runner import run_features
from scripts.lead_contractor.tasks.dashboard_persistence import (
    DASHBOARD_PERSISTENCE_FEATURES,
    PHASES_1_3_FEATURES,
    PHASES_4_6_FEATURES,
    PHASES_7_9_FEATURES,
)


def main():
    parser = argparse.ArgumentParser(
        description="Run Dashboard & Persistence Architecture workflow"
    )
    parser.add_argument(
        "--phases",
        choices=["1-3", "4-6", "7-9", "all"],
        default="all",
        help="Which phases to run (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List features without executing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-run even if results exist",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop on first error",
    )
    args = parser.parse_args()

    # Select features based on phase group
    phase_map = {
        "1-3": PHASES_1_3_FEATURES,
        "4-6": PHASES_4_6_FEATURES,
        "7-9": PHASES_7_9_FEATURES,
        "all": DASHBOARD_PERSISTENCE_FEATURES,
    }
    features = phase_map[args.phases]

    print(f"\n{'='*60}")
    print("Dashboard & Persistence Architecture")
    print(f"{'='*60}")
    print(f"Phases: {args.phases}")
    print(f"Features: {len(features)}")
    print()

    if args.dry_run:
        print("Features to run:")
        for i, f in enumerate(features, 1):
            print(f"  {i}. {f.name}")
            print(f"     Output: {f.output_subdir}")
        return

    # Run the workflow
    results = run_features(
        features,
        verbose=True,
        stop_on_error=args.stop_on_error,
        skip_existing=not args.force,
        force=args.force,
    )

    # Summary
    success_count = sum(1 for r in results if r.success)
    total_cost = sum(r.total_cost for r in results)

    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"Success: {success_count}/{len(results)}")
    print(f"Total Cost: ${total_cost:.4f}")

    if success_count < len(results):
        print("\nFailed features:")
        for r in results:
            if not r.success:
                print(f"  - {r.feature_name}: {r.error}")


if __name__ == "__main__":
    main()
