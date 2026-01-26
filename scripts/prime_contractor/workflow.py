"""
Prime Contractor Workflow - Continuous Integration Wrapper for Lead Contractor.

The Prime Contractor ensures that code is integrated immediately after each
feature is developed, preventing the "backlog integration nightmare" where
multiple features developed in isolation create merge conflicts and regressions.

Key Principles:
1. INTEGRATE IMMEDIATELY: Each feature is integrated right after generation
2. CHECKPOINT VALIDATION: Code must pass all checks before next feature starts
3. FAIL FAST: Stop the pipeline if integration fails, don't accumulate problems
4. MAINLINE ALWAYS WORKS: The main codebase is always in a working state

This is the "general contractor" pattern - just as a general contractor
coordinates subcontractors and ensures each phase is complete before the
next begins, the Prime Contractor coordinates Lead Contractor tasks and
ensures each feature is integrated before moving on.
"""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prime_contractor.checkpoint import (
    IntegrationCheckpoint,
    CheckpointResult,
    CheckpointStatus,
)
from scripts.prime_contractor.feature_queue import (
    FeatureQueue,
    FeatureSpec,
    FeatureStatus,
)

# Import lead contractor functions
from scripts.lead_contractor.integrate_backlog import (
    scan_backlog,
    generate_integration_plan,
    integrate_file,
    infer_target_path,
    GeneratedFile,
    merge_files_automatically,
    detect_merge_strategy,
    analyze_file_content,
    check_if_integrated,
    detect_incomplete_file,
    clean_markdown_code_blocks,
)
from scripts.lead_contractor.runner import (
    Feature,
    run_workflow as run_lead_contractor,
    save_result,
    get_result_file_path,
)


class PrimeContractorWorkflow:
    """
    Orchestrates the Lead Contractor workflow with continuous integration.
    
    Instead of generating all features and then integrating them in a batch
    (which causes conflicts), this workflow:
    
    1. Takes one feature at a time
    2. Generates the code (via Lead Contractor)
    3. Integrates it immediately
    4. Runs checkpoints to validate
    5. Only proceeds to next feature if checkpoints pass
    
    This prevents the exact problem you experienced where multiple changes
    to the same file created conflicts that required careful manual merging.
    """
    
    def __init__(
        self,
        project_root: Path = PROJECT_ROOT,
        dry_run: bool = False,
        auto_commit: bool = False,
        strict_checkpoints: bool = False,
        max_retries: int = 2,
        on_feature_complete: Optional[Callable[[FeatureSpec], None]] = None,
        on_checkpoint_failed: Optional[Callable[[FeatureSpec, List[CheckpointResult]], None]] = None,
    ):
        self.project_root = project_root
        self.dry_run = dry_run
        self.auto_commit = auto_commit
        self.strict_checkpoints = strict_checkpoints
        self.max_retries = max_retries
        self.on_feature_complete = on_feature_complete
        self.on_checkpoint_failed = on_checkpoint_failed
        
        self.queue = FeatureQueue()
        self.checkpoint = IntegrationCheckpoint(
            project_root=project_root,
            run_tests=True,
            strict_mode=strict_checkpoints
        )
        
        # Track integration history for conflict detection
        self.integration_history: List[Dict] = []
        self.files_modified_this_session: Dict[str, List[str]] = {}  # file -> [features]
    
    def import_from_backlog(self) -> int:
        """
        Import features from the Lead Contractor's generated backlog.
        
        This scans the generated/ directory and creates feature specs
        for each generated file that hasn't been integrated yet.
        
        Returns:
            Number of features imported
        """
        print("Scanning Lead Contractor backlog...")
        files = scan_backlog()
        
        if not files:
            print("No generated files found in backlog.")
            return 0
        
        plan = generate_integration_plan(files)
        
        # Group by target to detect potential conflicts BEFORE they happen
        target_to_features: Dict[str, List[str]] = {}
        
        for item in plan.get("files", []):
            target = item.get("target", "")
            feature = item.get("feature", "unknown")
            
            if target not in target_to_features:
                target_to_features[target] = []
            target_to_features[target].append(feature)
        
        # Warn about potential conflicts
        conflicts = {t: fs for t, fs in target_to_features.items() if len(fs) > 1}
        if conflicts:
            print(f"\n⚠️  POTENTIAL CONFLICTS DETECTED:")
            print(f"   {len(conflicts)} target(s) have multiple features:")
            for target, features in list(conflicts.items())[:5]:
                target_rel = Path(target).relative_to(self.project_root) if target else "unknown"
                print(f"   • {target_rel}:")
                for f in features:
                    print(f"     - {f}")
            print("\n   The Prime Contractor will integrate these one at a time")
            print("   to prevent conflicts. Order matters!\n")
        
        # Add features to queue
        added = self.queue.add_features_from_plan(plan)
        
        print(f"Imported {len(added)} feature(s) from backlog")
        return len(added)
    
    def validate_generated_code(self, feature: FeatureSpec) -> Tuple[bool, List[str]]:
        """
        Validate generated code files before integration.

        Checks for truncation, syntax errors, and other issues that would
        corrupt the target codebase if integrated.

        Args:
            feature: Feature spec with generated_files list

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        for source_file in feature.generated_files:
            source_path = Path(source_file)

            if not source_path.exists():
                errors.append(f"Source file not found: {source_path}")
                continue

            try:
                with open(source_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                errors.append(f"Failed to read {source_path.name}: {e}")
                continue

            # Clean markdown code blocks
            if source_path.suffix == '.py':
                content = clean_markdown_code_blocks(content)

                # Check for truncation and other issues
                issues = detect_incomplete_file(content, source_path)
                truncation_issues = [i for i in issues if i.startswith("TRUNCATED:")]

                if truncation_issues:
                    errors.append(f"{source_path.name}: {'; '.join(truncation_issues)}")

        is_valid = len(errors) == 0
        return is_valid, errors

    def detect_conflict_risk(self, feature: FeatureSpec) -> Tuple[str, List[str]]:
        """
        Detect if integrating this feature might cause conflicts.
        
        Returns:
            Tuple of (risk_level, warnings)
            risk_level: "LOW", "MEDIUM", "HIGH"
        """
        warnings = []
        risk_score = 0
        
        for target_file in feature.target_files:
            target_path = Path(target_file)
            
            # Check if this file was modified by a previous feature in this session
            if target_file in self.files_modified_this_session:
                prev_features = self.files_modified_this_session[target_file]
                warnings.append(
                    f"File {target_path.name} was already modified by: {', '.join(prev_features)}"
                )
                risk_score += 30
            
            # Check if target file exists and has recent changes
            if target_path.exists():
                # Analyze content to understand what might be overwritten
                analysis = analyze_file_content(target_path)
                if "error" not in analysis:
                    if analysis.get("classes"):
                        warnings.append(
                            f"Target has {len(analysis['classes'])} class(es) that might be affected"
                        )
                        risk_score += 10
                    if analysis.get("functions"):
                        warnings.append(
                            f"Target has {len(analysis['functions'])} function(s) that might be affected"
                        )
                        risk_score += 5
        
        # Determine risk level
        if risk_score >= 50:
            risk_level = "HIGH"
        elif risk_score >= 20:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        return risk_level, warnings
    
    def develop_feature(self, feature: FeatureSpec) -> bool:
        """
        Develop a feature using the Lead Contractor workflow.

        This calls the Lead Contractor (Claude Sonnet + GPT-4o-mini drafter)
        to generate code for the feature.

        Returns:
            True if code generation succeeded, False otherwise
        """
        print(f"\n{'='*70}")
        print(f"DEVELOPING FEATURE: {feature.name}")
        print(f"{'='*70}")

        # Mark as developing
        self.queue.start_feature(feature.id)

        # Create a Lead Contractor Feature from the FeatureSpec
        lc_feature = Feature(
            task=feature.description,
            name=feature.name.replace(" ", "_"),
            is_typescript=any(f.endswith('.ts') or f.endswith('.tsx') for f in feature.target_files),
            output_subdir=f"prime_contractor/{feature.id}",
        )

        if self.dry_run:
            print(f"  [DRY RUN] Would generate code for: {feature.name}")
            print(f"  Task description: {feature.description[:100]}...")
            print(f"  Target files: {feature.target_files}")
            # In dry run, simulate generated files based on target files
            simulated_files = [f"generated/prime_contractor/{feature.id}/{Path(t).name}" for t in feature.target_files] if feature.target_files else [f"generated/prime_contractor/{feature.id}/code.py"]
            feature.generated_files = simulated_files
            feature.status = FeatureStatus.GENERATED
            self.queue.save_state()
            print(f"  [DRY RUN] Would produce: {simulated_files}")
            return True

        print(f"  Running Lead Contractor workflow...")
        print(f"  Lead Agent: Claude Sonnet (spec creation, review)")
        print(f"  Drafter Agent: GPT-4o-mini (implementation)")
        print()

        try:
            # Run the Lead Contractor workflow
            result = run_lead_contractor(lc_feature, verbose=True)

            if result.success:
                # Save the result
                meta_file, code_file = save_result(result, lc_feature)

                # Update feature with generated files
                feature.generated_files = [str(code_file)]
                feature.status = FeatureStatus.GENERATED
                self.queue.save_state()

                print(f"\n✓ Code generated successfully!")
                print(f"  Cost: ${result.total_cost:.4f}")
                print(f"  Iterations: {result.iterations}")
                print(f"  Output: {code_file}")

                return True
            else:
                error_msg = result.error or "Lead Contractor workflow failed"
                print(f"\n✗ Code generation failed: {error_msg}")
                self.queue.fail_feature(feature.id, error_msg)
                return False

        except Exception as e:
            error_msg = f"Exception during code generation: {e}"
            print(f"\n✗ {error_msg}")
            self.queue.fail_feature(feature.id, error_msg)
            return False

    def process_feature(self, feature: FeatureSpec) -> bool:
        """
        Process a feature through the full lifecycle: develop then integrate.

        This is the Prime Contractor's main orchestration method:
        1. If PENDING: Run Lead Contractor to generate code
        2. If GENERATED: Integrate the code
        3. Run checkpoints and validate

        Returns:
            True if the feature was fully processed, False otherwise
        """
        # Step 1: Develop if needed
        if feature.status == FeatureStatus.PENDING:
            if not self.develop_feature(feature):
                return False

        # Step 2: Integrate
        if feature.status == FeatureStatus.GENERATED:
            return self.integrate_feature(feature)

        # Feature is in an unexpected state
        print(f"  ⚠ Feature in unexpected state: {feature.status}")
        return False

    def integrate_feature(self, feature: FeatureSpec) -> bool:
        """
        Integrate a single feature immediately.

        This is the core of the Prime Contractor pattern:
        - Validate generated code (check for truncation)
        - Integrate the feature
        - Run checkpoints
        - Commit if successful
        - Fail fast if not

        Returns:
            True if integration succeeded, False otherwise
        """
        print(f"\n{'='*70}")
        print(f"INTEGRATING FEATURE: {feature.name}")
        print(f"{'='*70}")

        # CRITICAL: Validate generated code BEFORE integration
        # This prevents truncated/corrupted code from overwriting good code
        is_valid, validation_errors = self.validate_generated_code(feature)
        if not is_valid:
            print(f"\n❌ VALIDATION FAILED - Generated code is invalid:")
            for error in validation_errors:
                print(f"   • {error}")
            print(f"\n   The generated code appears truncated or corrupted.")
            print(f"   This typically happens when LLM output exceeds token limits.")
            print(f"\n   Options:")
            print(f"     1. Regenerate with smaller scope (split into multiple features)")
            print(f"     2. Manually fix the truncated code in generated/")
            print(f"     3. Remove this feature from the queue")
            self.queue.fail_feature(feature.id, f"Validation failed: {'; '.join(validation_errors[:2])}")
            return False

        # Check for conflict risk
        risk_level, warnings = self.detect_conflict_risk(feature)
        if warnings:
            print(f"\n⚠️  Conflict Risk: {risk_level}")
            for warning in warnings:
                print(f"   • {warning}")
        
        # Mark as integrating
        self.queue.start_integration(feature.id)
        
        # Get the generated files to integrate
        integrated_files = []
        
        for i, source_file in enumerate(feature.generated_files):
            source_path = Path(source_file)

            # Determine target path
            if i < len(feature.target_files):
                target_path = Path(feature.target_files[i])
            else:
                if not source_path.exists():
                    if self.dry_run:
                        # In dry run, use a placeholder target based on source name
                        target_path = self.project_root / "src" / source_path.name
                    else:
                        print(f"  ✗ Source file not found: {source_path}")
                        continue
                else:
                    # Infer target from source
                    gen_file = GeneratedFile(
                        path=source_path,
                        feature_name=feature.name,
                        result_file=source_path,  # Placeholder
                    )
                    target_path = infer_target_path(gen_file)
                    if not target_path:
                        print(f"  ✗ Could not infer target for: {source_path.name}")
                        continue

            # In dry run mode, skip file existence checks and just report what would happen
            if self.dry_run:
                try:
                    target_rel = target_path.relative_to(self.project_root)
                except ValueError:
                    target_rel = target_path
                if target_path.exists():
                    print(f"  [DRY RUN] Would update: {target_rel}")
                else:
                    print(f"  [DRY RUN] Would create: {target_rel}")
                integrated_files.append(target_path)
                continue

            # Live mode - check source exists
            if not source_path.exists():
                print(f"  ✗ Source file not found: {source_path}")
                continue

            # Check if already integrated
            gen_file = GeneratedFile(
                path=source_path,
                feature_name=feature.name,
                result_file=source_path,
            )
            if check_if_integrated(gen_file, target_path):
                print(f"  ○ Already integrated: {target_path.relative_to(self.project_root)}")
                integrated_files.append(target_path)
                continue

            # Check if we need to merge with existing content
            if target_path.exists():
                # Detect merge strategy
                merge_strategy = detect_merge_strategy(
                    target_path,
                    [gen_file]
                )

                if merge_strategy == "merge":
                    print(f"  ⊕ Merging with existing: {target_path.relative_to(self.project_root)}")

                    merged_content = merge_files_automatically(
                        target_path,
                        [{"source": str(source_path), "feature": feature.name}],
                        strategy="merge"
                    )

                    if merged_content:
                        # Backup existing
                        backup_path = target_path.with_suffix(f"{target_path.suffix}.backup")
                        shutil.copy2(target_path, backup_path)

                        # Write merged content
                        with open(target_path, "w", encoding="utf-8") as f:
                            f.write(merged_content)

                        print(f"  ✓ Merged: {target_path.relative_to(self.project_root)}")
                        integrated_files.append(target_path)
                    else:
                        print(f"  ✗ Merge failed for: {target_path.name}")
                else:
                    # Standard integration (overwrite)
                    if integrate_file(source_path, target_path, dry_run=False):
                        integrated_files.append(target_path)
            else:
                # New file - just integrate
                if integrate_file(source_path, target_path, dry_run=False):
                    integrated_files.append(target_path)
        
        if not integrated_files:
            self.queue.fail_feature(feature.id, "No files were integrated")
            return False
        
        # Track which files were modified by this feature
        for file_path in integrated_files:
            file_str = str(file_path)
            if file_str not in self.files_modified_this_session:
                self.files_modified_this_session[file_str] = []
            self.files_modified_this_session[file_str].append(feature.name)
        
        # Run checkpoints
        if not self.dry_run:
            print("\nRunning integration checkpoints...")
            results = self.checkpoint.run_all_checkpoints(integrated_files, feature.name)
            all_passed = self.checkpoint.summarize_results(results)
            
            if not all_passed:
                # Checkpoint failed
                failed_checks = [r for r in results if r.status == CheckpointStatus.FAILED]
                error_msg = "; ".join(r.message for r in failed_checks)
                
                self.queue.fail_feature(feature.id, error_msg)
                
                if self.on_checkpoint_failed:
                    self.on_checkpoint_failed(feature, results)
                
                return False
        else:
            print("\n[DRY RUN] Would run integration checkpoints")
            all_passed = True
        
        # Commit if auto-commit is enabled
        if self.auto_commit and not self.dry_run and all_passed:
            self._commit_feature(feature, integrated_files)
        
        # Mark complete
        self.queue.complete_feature(feature.id)
        
        # Record in history
        self.integration_history.append({
            "feature": feature.name,
            "files": [str(f) for f in integrated_files],
            "timestamp": datetime.now().isoformat()
        })
        
        if self.on_feature_complete:
            self.on_feature_complete(feature)
        
        print(f"\n✓ Feature '{feature.name}' integrated successfully!")
        return True
    
    def _commit_feature(self, feature: FeatureSpec, files: List[Path]):
        """Commit the integrated feature to git."""
        # Stage files
        for file_path in files:
            subprocess.run(
                ["git", "add", str(file_path)],
                cwd=self.project_root,
                capture_output=True
            )
        
        # Commit
        commit_msg = f"feat: Integrate {feature.name}\n\nIntegrated via Prime Contractor workflow"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=self.project_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"  ✓ Committed: {feature.name}")
        else:
            print(f"  ⚠ Commit failed: {result.stderr}")
    
    def run(
        self,
        max_features: Optional[int] = None,
        stop_on_failure: bool = True
    ) -> Dict:
        """
        Run the Prime Contractor workflow.
        
        This is the main entry point that:
        1. Gets the next feature from the queue
        2. Integrates it
        3. Runs checkpoints
        4. Repeats until done or failure
        
        Args:
            max_features: Maximum number of features to process (None = all)
            stop_on_failure: Stop processing if a feature fails
        
        Returns:
            Summary dict with results
        """
        print("\n" + "=" * 70)
        print("PRIME CONTRACTOR WORKFLOW")
        print("=" * 70)
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"Auto-commit: {self.auto_commit}")
        print(f"Stop on failure: {stop_on_failure}")
        
        # Capture test baseline for regression detection
        if not self.dry_run:
            print("\nCapturing test baseline for regression detection...")
            baseline = self.checkpoint.capture_test_baseline()
            print(f"  Baseline: {len(baseline)} test(s)")
        
        # Show queue status
        self.queue.print_status()
        
        # Process features
        features_processed = 0
        features_succeeded = 0
        features_failed = 0
        
        while True:
            # Check max features limit
            if max_features and features_processed >= max_features:
                print(f"\nReached max features limit ({max_features})")
                break
            
            # Get next feature
            feature = self.queue.get_next_feature()
            
            if not feature:
                print("\nNo more features to process")
                break
            
            features_processed += 1

            # Process the feature (develop if needed, then integrate)
            success = self.process_feature(feature)

            if success:
                features_succeeded += 1
            else:
                features_failed += 1

                if stop_on_failure:
                    print(f"\n❌ STOPPING: Feature '{feature.name}' failed")
                    print("   Fix the issue and re-run to continue")
                    break
        
        # Final summary
        print("\n" + "=" * 70)
        print("WORKFLOW SUMMARY")
        print("=" * 70)
        print(f"  Features processed: {features_processed}")
        print(f"  Succeeded: {features_succeeded}")
        print(f"  Failed: {features_failed}")
        print(f"  Progress: {self.queue.get_progress():.1f}%")
        
        if features_failed > 0:
            print("\n⚠️  Some features failed. Review errors and re-run.")
        elif features_processed > 0:
            print("\n✓ All processed features integrated successfully!")
        
        return {
            "processed": features_processed,
            "succeeded": features_succeeded,
            "failed": features_failed,
            "progress": self.queue.get_progress(),
            "history": self.integration_history
        }
    
    def run_single_feature(self, feature_id: str) -> bool:
        """
        Run integration for a single specific feature.
        
        Useful for retrying a failed feature after fixing issues.
        """
        feature = self.queue.features.get(feature_id)
        if not feature:
            print(f"Feature not found: {feature_id}")
            return False
        
        return self.integrate_feature(feature)
    
    def reset_failed_features(self):
        """Reset all failed features to appropriate status for retry."""
        reset_count = 0
        for feature in self.queue.features.values():
            if feature.status in (FeatureStatus.FAILED, FeatureStatus.BLOCKED):
                # Reset to PENDING if no generated files, otherwise GENERATED
                if feature.generated_files:
                    feature.status = FeatureStatus.GENERATED
                    print(f"  Reset {feature.name} -> GENERATED (has code)")
                else:
                    feature.status = FeatureStatus.PENDING
                    print(f"  Reset {feature.name} -> PENDING (needs development)")
                feature.error_message = None
                reset_count += 1

        self.queue.save_state()
        print(f"\nReset {reset_count} failed/blocked feature(s)")


def main():
    """CLI entry point for Prime Contractor workflow."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Prime Contractor: Continuous integration wrapper for Lead Contractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The Prime Contractor prevents integration conflicts by:
1. Processing features one at a time
2. Integrating immediately after generation
3. Running checkpoints before proceeding
4. Failing fast if issues are detected

This prevents the "backlog nightmare" where multiple features
create conflicts when integrated all at once.

Examples:
  # Import features from backlog and run
  %(prog)s --import-backlog
  
  # Dry run to preview
  %(prog)s --import-backlog --dry-run
  
  # Process only 3 features
  %(prog)s --import-backlog --max-features 3
  
  # Continue even if features fail
  %(prog)s --import-backlog --no-stop-on-failure
  
  # Auto-commit each feature
  %(prog)s --import-backlog --auto-commit
  
  # Show current queue status
  %(prog)s --status
  
  # Reset failed features for retry
  %(prog)s --reset-failed
        """
    )
    
    parser.add_argument("--import-backlog", action="store_true",
                       help="Import features from Lead Contractor backlog")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview changes without executing")
    parser.add_argument("--auto-commit", action="store_true",
                       help="Commit each feature after successful integration")
    parser.add_argument("--max-features", type=int,
                       help="Maximum number of features to process")
    parser.add_argument("--no-stop-on-failure", action="store_true",
                       help="Continue processing even if a feature fails")
    parser.add_argument("--strict", action="store_true",
                       help="Enable strict checkpoint mode (fail on warnings)")
    parser.add_argument("--status", action="store_true",
                       help="Show current queue status and exit")
    parser.add_argument("--reset-failed", action="store_true",
                       help="Reset failed features to pending status")
    parser.add_argument("--feature", type=str,
                       help="Process a specific feature by ID")
    
    args = parser.parse_args()
    
    # Create workflow
    workflow = PrimeContractorWorkflow(
        dry_run=args.dry_run,
        auto_commit=args.auto_commit,
        strict_checkpoints=args.strict
    )
    
    # Handle commands
    if args.status:
        workflow.queue.print_status()
        return
    
    if args.reset_failed:
        workflow.reset_failed_features()
        return
    
    if args.import_backlog:
        workflow.import_from_backlog()
    
    if args.feature:
        # Process single feature
        workflow.run_single_feature(args.feature)
    else:
        # Run full workflow
        workflow.run(
            max_features=args.max_features,
            stop_on_failure=not args.no_stop_on_failure
        )


if __name__ == "__main__":
    main()
