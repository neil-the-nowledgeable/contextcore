#!/usr/bin/env python3
"""
Prime Contractor CLI - Command-line interface for the Prime Contractor workflow.

This provides a user-friendly interface for running the Prime Contractor
workflow, which wraps the Lead Contractor with continuous integration.

Usage:
    # Full workflow: import from backlog and integrate one by one
    python3 scripts/prime_contractor/cli.py run
    
    # Dry run to preview
    python3 scripts/prime_contractor/cli.py run --dry-run
    
    # Show queue status
    python3 scripts/prime_contractor/cli.py status
    
    # Add a feature manually
    python3 scripts/prime_contractor/cli.py add "My Feature" --description "Does X"
    
    # Reset failed features
    python3 scripts/prime_contractor/cli.py reset
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prime_contractor.workflow import PrimeContractorWorkflow
from scripts.prime_contractor.feature_queue import FeatureQueue, FeatureStatus


def cmd_run(args):
    """Run the Prime Contractor workflow."""
    workflow = PrimeContractorWorkflow(
        dry_run=args.dry_run,
        auto_commit=args.auto_commit,
        strict_checkpoints=args.strict
    )
    
    # Import from backlog if requested
    if args.import_backlog:
        count = workflow.import_from_backlog()
        if count == 0 and not workflow.queue.features:
            print("No features to process. Add features or import from backlog.")
            return
    
    # Run workflow
    result = workflow.run(
        max_features=args.max_features,
        stop_on_failure=not args.continue_on_failure
    )
    
    # Exit with error code if there were failures
    if result["failed"] > 0:
        sys.exit(1)


def cmd_status(args):
    """Show current queue status."""
    queue = FeatureQueue()
    queue.print_status()
    
    # Show additional details if verbose
    if args.verbose:
        print("\n" + "=" * 70)
        print("INTEGRATION HISTORY")
        print("=" * 70)
        
        state_file = PROJECT_ROOT / ".prime_contractor_state.json"
        if state_file.exists():
            import json
            with open(state_file) as f:
                state = json.load(f)
            print(f"State file: {state_file}")
            print(f"Last saved: {state.get('saved_at', 'unknown')}")


def cmd_add(args):
    """Add a feature to the queue."""
    queue = FeatureQueue()
    
    feature_id = args.name.lower().replace(" ", "_")
    
    spec = queue.add_feature(
        feature_id=feature_id,
        name=args.name,
        description=args.description or "",
        dependencies=args.depends_on or [],
        target_files=args.target_files or []
    )
    
    print(f"✓ Added feature: {spec.name} (id: {spec.id})")
    
    if args.depends_on:
        print(f"  Dependencies: {', '.join(args.depends_on)}")
    if args.target_files:
        print(f"  Target files: {', '.join(args.target_files)}")


def cmd_reset(args):
    """Reset failed features."""
    workflow = PrimeContractorWorkflow()
    
    if args.all:
        # Reset entire queue
        workflow.queue.reset()
        print("✓ Reset all features to PENDING status")
    else:
        # Reset only failed features
        workflow.reset_failed_features()


def cmd_retry(args):
    """Retry a specific failed feature."""
    workflow = PrimeContractorWorkflow(
        dry_run=args.dry_run,
        auto_commit=args.auto_commit
    )
    
    # Find the feature
    feature = workflow.queue.features.get(args.feature_id)
    if not feature:
        print(f"Feature not found: {args.feature_id}")
        print("\nAvailable features:")
        for fid in workflow.queue.features:
            print(f"  - {fid}")
        sys.exit(1)
    
    # Reset status if it was failed
    if feature.status == FeatureStatus.FAILED:
        feature.status = FeatureStatus.GENERATED
        feature.error_message = None
        workflow.queue.save_state()
    
    # Run integration
    success = workflow.integrate_feature(feature)
    
    if not success:
        sys.exit(1)


def cmd_import(args):
    """Import features from Lead Contractor backlog."""
    workflow = PrimeContractorWorkflow()
    count = workflow.import_from_backlog()
    
    if count > 0:
        print(f"\n✓ Imported {count} feature(s)")
        print("\nRun 'python3 scripts/prime_contractor/cli.py run' to integrate them")
    else:
        print("No new features to import")


def cmd_clear(args):
    """Clear the feature queue."""
    queue = FeatureQueue()
    
    if not args.force:
        response = input("Are you sure you want to clear the queue? (yes/no): ")
        if response.lower() not in ("yes", "y"):
            print("Cancelled")
            return
    
    # Clear features
    queue.features = {}
    queue.order = []
    queue.save_state()
    
    print("✓ Queue cleared")


def main():
    parser = argparse.ArgumentParser(
        description="Prime Contractor: Continuous integration for Lead Contractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The Prime Contractor wraps the Lead Contractor workflow to ensure
features are integrated immediately after development, preventing
the "backlog integration nightmare" where multiple features create
merge conflicts when integrated all at once.

Examples:
  %(prog)s run                    # Run full workflow
  %(prog)s run --dry-run          # Preview without changes
  %(prog)s status                 # Show queue status
  %(prog)s import                 # Import from Lead Contractor backlog
  %(prog)s retry my_feature       # Retry a failed feature
  %(prog)s reset                  # Reset failed features
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run the Prime Contractor workflow")
    run_parser.add_argument("--dry-run", action="store_true",
                           help="Preview changes without executing")
    run_parser.add_argument("--auto-commit", action="store_true",
                           help="Commit each feature after integration")
    run_parser.add_argument("--import-backlog", "-i", action="store_true",
                           help="Import features from Lead Contractor backlog first")
    run_parser.add_argument("--max-features", "-n", type=int,
                           help="Maximum number of features to process")
    run_parser.add_argument("--continue-on-failure", "-c", action="store_true",
                           help="Continue processing even if a feature fails")
    run_parser.add_argument("--strict", action="store_true",
                           help="Fail on checkpoint warnings (not just errors)")
    run_parser.set_defaults(func=cmd_run)
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show queue status")
    status_parser.add_argument("--verbose", "-v", action="store_true",
                              help="Show additional details")
    status_parser.set_defaults(func=cmd_status)
    
    # Add command
    add_parser = subparsers.add_parser("add", help="Add a feature to the queue")
    add_parser.add_argument("name", help="Feature name")
    add_parser.add_argument("--description", "-d", help="Feature description")
    add_parser.add_argument("--depends-on", nargs="+",
                           help="Feature IDs this depends on")
    add_parser.add_argument("--target-files", nargs="+",
                           help="Target files for this feature")
    add_parser.set_defaults(func=cmd_add)
    
    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset failed features")
    reset_parser.add_argument("--all", action="store_true",
                             help="Reset all features (not just failed)")
    reset_parser.set_defaults(func=cmd_reset)
    
    # Retry command
    retry_parser = subparsers.add_parser("retry", help="Retry a specific feature")
    retry_parser.add_argument("feature_id", help="Feature ID to retry")
    retry_parser.add_argument("--dry-run", action="store_true",
                             help="Preview changes without executing")
    retry_parser.add_argument("--auto-commit", action="store_true",
                             help="Commit after successful integration")
    retry_parser.set_defaults(func=cmd_retry)
    
    # Import command
    import_parser = subparsers.add_parser("import", help="Import from Lead Contractor backlog")
    import_parser.set_defaults(func=cmd_import)
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear the feature queue")
    clear_parser.add_argument("--force", "-f", action="store_true",
                             help="Skip confirmation")
    clear_parser.set_defaults(func=cmd_clear)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
