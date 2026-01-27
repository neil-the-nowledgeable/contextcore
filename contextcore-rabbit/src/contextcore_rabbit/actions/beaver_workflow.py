"""
Beaver Workflow Action - Triggers Lead Contractor workflows.

This action "wakes up" Beaver to run Lead Contractor workflows.
It's fire-and-forget: starts the workflow and returns immediately.
Status is tracked via spans in Tempo, not through Rabbit.
"""

import logging
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from contextcore_rabbit.action import Action, ActionResult, ActionStatus, action_registry

logger = logging.getLogger(__name__)

# Track running workflows for status queries
_workflow_runs: Dict[str, Dict[str, Any]] = {}


def _get_project_root() -> Path:
    """Find the ContextCore project root."""
    # Try to find it relative to this file
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "contextcore").exists():
            return parent
    # Fallback
    return Path.cwd()


def _run_workflow_background(run_id: str, project_id: str, dry_run: bool):
    """Run the workflow in a background thread."""
    try:
        _workflow_runs[run_id]["status"] = "running"
        _workflow_runs[run_id]["started_at"] = datetime.now().isoformat()

        project_root = _get_project_root()
        sys.path.insert(0, str(project_root))

        # Import Prime Contractor
        try:
            from scripts.prime_contractor.workflow import PrimeContractorWorkflow
            from scripts.prime_contractor.feature_queue import FeatureStatus
        except ImportError as e:
            logger.error(f"Failed to import Prime Contractor: {e}")
            _workflow_runs[run_id]["status"] = "failed"
            _workflow_runs[run_id]["error"] = f"Prime Contractor not available: {e}"
            return

        # Create and run workflow
        workflow = PrimeContractorWorkflow(
            project_root=project_root,
            dry_run=dry_run,
        )

        # Import features from backlog
        imported = workflow.import_from_backlog()
        _workflow_runs[run_id]["steps_total"] = len(workflow.queue.features)
        _workflow_runs[run_id]["steps_completed"] = 0

        # Track progress
        def on_complete(feature):
            _workflow_runs[run_id]["steps_completed"] += 1

        workflow.on_feature_complete = on_complete

        # Run
        result = workflow.run(stop_on_failure=True)

        # Update status
        _workflow_runs[run_id]["status"] = "completed" if result["failed"] == 0 else "failed"
        _workflow_runs[run_id]["completed_at"] = datetime.now().isoformat()
        _workflow_runs[run_id]["steps_completed"] = result["succeeded"]
        _workflow_runs[run_id]["result"] = {
            "processed": result["processed"],
            "succeeded": result["succeeded"],
            "failed": result["failed"],
        }

        if result["failed"] > 0:
            _workflow_runs[run_id]["error"] = f"{result['failed']} feature(s) failed"

    except Exception as e:
        logger.exception(f"Workflow {run_id} failed")
        _workflow_runs[run_id]["status"] = "failed"
        _workflow_runs[run_id]["error"] = str(e)
        _workflow_runs[run_id]["completed_at"] = datetime.now().isoformat()


@action_registry.register("beaver_workflow")
class BeaverWorkflowAction(Action):
    """
    Trigger a Beaver Lead Contractor workflow.

    This action starts the workflow and returns immediately (fire-and-forget).
    The workflow runs in a background thread. Status can be queried via
    the workflow status endpoint or by querying Tempo for spans.

    Payload:
        {
            "project_id": "my-project",
            "dry_run": false
        }
    """

    name = "beaver_workflow"
    description = "Trigger Beaver Lead Contractor workflow (fire-and-forget)"

    def execute(self, payload: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        """Start the Beaver workflow."""
        project_id = payload.get("project_id", "default")
        dry_run = payload.get("dry_run", False)

        run_id = str(uuid.uuid4())[:8]

        # Initialize tracking
        _workflow_runs[run_id] = {
            "run_id": run_id,
            "project_id": project_id,
            "dry_run": dry_run,
            "status": "starting",
            "started_at": None,
            "completed_at": None,
            "steps_total": 0,
            "steps_completed": 0,
            "error": None,
        }

        # Start workflow in background thread
        thread = threading.Thread(
            target=_run_workflow_background,
            args=(run_id, project_id, dry_run),
            daemon=True,
        )
        thread.start()

        mode = "dry_run" if dry_run else "execute"
        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_name=self.name,
            message=f"Workflow started ({mode})",
            data={
                "run_id": run_id,
                "project_id": project_id,
                "mode": mode,
                "status_endpoint": f"/workflow/status/{run_id}",
            },
        )

    def validate(self, payload: Dict[str, Any]) -> Optional[str]:
        """Validate the payload."""
        # project_id is optional (defaults to "default")
        return None


@action_registry.register("beaver_workflow_status")
class BeaverWorkflowStatusAction(Action):
    """
    Get the status of a running Beaver workflow.

    Payload:
        {
            "run_id": "abc12345"
        }
    """

    name = "beaver_workflow_status"
    description = "Get status of a Beaver workflow run"

    def execute(self, payload: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        """Get workflow status."""
        run_id = payload.get("run_id")

        if not run_id:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_name=self.name,
                message="Missing run_id",
            )

        if run_id not in _workflow_runs:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_name=self.name,
                message=f"Run not found: {run_id}",
            )

        run_data = _workflow_runs[run_id]

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_name=self.name,
            message=f"Status: {run_data['status']}",
            data=run_data,
        )


@action_registry.register("beaver_workflow_history")
class BeaverWorkflowHistoryAction(Action):
    """
    Get history of all workflow runs.

    Payload:
        {
            "project_id": "optional-filter",
            "limit": 20
        }
    """

    name = "beaver_workflow_history"
    description = "Get history of all workflow runs"

    def execute(self, payload: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        """Get workflow history."""
        project_filter = payload.get("project_id")
        limit = payload.get("limit", 20)

        # Get all runs, optionally filtered by project
        runs = list(_workflow_runs.values())

        if project_filter:
            runs = [r for r in runs if r.get("project_id") == project_filter]

        # Sort by started_at (most recent first)
        runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)

        # Apply limit
        runs = runs[:limit]

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_name=self.name,
            message=f"Found {len(runs)} workflow runs",
            data={
                "runs": runs,
                "total": len(_workflow_runs),
            },
        )


@action_registry.register("beaver_workflow_dry_run")
class BeaverWorkflowDryRunAction(Action):
    """
    Preview Beaver workflow steps without executing.

    This is synchronous (not fire-and-forget) since it's just a preview.

    Payload:
        {
            "project_id": "my-project"
        }
    """

    name = "beaver_workflow_dry_run"
    description = "Preview Beaver workflow steps (synchronous)"

    def execute(self, payload: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        """Get workflow preview."""
        project_id = payload.get("project_id", "default")

        try:
            project_root = _get_project_root()
            sys.path.insert(0, str(project_root))

            from scripts.prime_contractor.workflow import PrimeContractorWorkflow

            workflow = PrimeContractorWorkflow(dry_run=True)
            workflow.import_from_backlog()

            steps = []
            for fid, feature in workflow.queue.features.items():
                status_str = feature.status.value if hasattr(feature.status, 'value') else str(feature.status)

                if status_str == "completed":
                    step_status = "would_skip"
                    reason = "Already integrated"
                elif status_str == "failed":
                    step_status = "would_skip"
                    reason = feature.error_message or "Previously failed"
                else:
                    step_status = "would_execute"
                    reason = None

                steps.append({
                    "name": feature.name,
                    "status": step_status,
                    "reason": reason,
                    "target_files": feature.target_files[:3] if feature.target_files else [],
                })

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_name=self.name,
                message=f"Found {len(steps)} features",
                data={
                    "project_id": project_id,
                    "steps": steps,
                    "total": len(steps),
                    "would_execute": len([s for s in steps if s["status"] == "would_execute"]),
                    "would_skip": len([s for s in steps if s["status"] == "would_skip"]),
                },
            )

        except ImportError as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_name=self.name,
                message=f"Prime Contractor not available: {e}",
            )
        except Exception as e:
            logger.exception("Dry run failed")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_name=self.name,
                message=str(e),
            )
