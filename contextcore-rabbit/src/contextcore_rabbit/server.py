"""
Webhook server for Rabbit.

Receives webhooks from various sources and dispatches to registered actions.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

from contextcore_rabbit.action import action_registry, ActionResult, ActionStatus
from contextcore_rabbit.alert import Alert

logger = logging.getLogger(__name__)


class WebhookServer:
    """
    Flask-based webhook server for Rabbit.

    Receives webhooks and dispatches to registered actions.
    Fire-and-forget design - actions are triggered and control returns immediately.
    """

    def __init__(
        self,
        port: int = 8080,
        host: str = "0.0.0.0",
        otel_endpoint: Optional[str] = None,
    ):
        self.port = port
        self.host = host
        self.otel_endpoint = otel_endpoint

        self.app = Flask(__name__)
        CORS(self.app)

        self._setup_routes()

    def _setup_routes(self):
        """Set up Flask routes."""

        @self.app.route("/health", methods=["GET"])
        def health():
            return jsonify({
                "status": "healthy",
                "service": "contextcore-rabbit",
                "timestamp": datetime.now().isoformat(),
            })

        @self.app.route("/actions", methods=["GET"])
        def list_actions():
            """List all registered actions."""
            return jsonify({
                "actions": action_registry.list_actions(),
            })

        @self.app.route("/trigger", methods=["POST"])
        def trigger_action():
            """
            Trigger an action directly.

            This is the main endpoint for the Grafana workflow panel.

            Request body:
                {
                    "action": "beaver_workflow",
                    "payload": { ... },
                    "context": { ... }
                }
            """
            data = request.get_json() or {}

            action_name = data.get("action")
            if not action_name:
                return jsonify({
                    "status": "error",
                    "error": "Missing 'action' field"
                }), 400

            payload = data.get("payload", {})
            context = data.get("context", {})

            # Execute action (fire-and-forget)
            result = action_registry.execute(action_name, payload, context)

            status_code = 200 if result.status == ActionStatus.SUCCESS else 500
            return jsonify(result.to_dict()), status_code

        @self.app.route("/workflow/run", methods=["POST"])
        def workflow_run():
            """
            Trigger Prime Contractor workflow execution.

            Request body:
                {
                    "project_id": "string",        # Required
                    "dry_run": false,              # Optional, default false
                    "max_features": 10             # Optional
                }

            Response (200):
                {
                    "status": "started",
                    "run_id": "uuid",
                    "project_id": "string",
                    "mode": "dry_run" | "execute"
                }

            Response (400):
                {
                    "status": "error",
                    "error": "string"
                }
            """
            data = request.get_json() or {}

            # Validate required field
            project_id = data.get("project_id")
            if not project_id:
                logger.warning("workflow/run called without project_id")
                return jsonify({
                    "status": "error",
                    "error": "Missing required field: project_id"
                }), 400

            # Parse optional parameters with safe defaults
            dry_run = data.get("dry_run", False)
            max_features = data.get("max_features")

            # Build payload for beaver_workflow action
            payload = {
                "project_id": project_id,
                "dry_run": dry_run,
                "trigger_source": "workflow_api",
                "trigger_time": datetime.now().isoformat(),
            }
            if max_features is not None:
                payload["max_features"] = max_features

            # Execute via action registry
            result = action_registry.execute(
                "beaver_workflow",
                payload,
                {"api_endpoint": "/workflow/run"}
            )

            if result.status != ActionStatus.SUCCESS:
                return jsonify({
                    "status": "error",
                    "error": result.message or "Workflow execution failed"
                }), 500

            # Get run_id from action result (action generates its own ID)
            run_id = result.data.get("run_id") if result.data else None

            return jsonify({
                "status": "started",
                "run_id": run_id,
                "project_id": project_id,
                "mode": "dry_run" if dry_run else "execute"
            })

        @self.app.route("/workflow/status/<run_id>", methods=["GET"])
        def workflow_status(run_id: str):
            """
            Get status of a running workflow.

            Response (200):
                {
                    "run_id": "uuid",
                    "status": "starting" | "running" | "completed" | "failed",
                    "project_id": "string",
                    "dry_run": bool,
                    "started_at": "ISO timestamp",
                    "completed_at": "ISO timestamp" | null,
                    "steps_total": int,
                    "steps_completed": int,
                    "progress_percent": float,
                    "error": "string" | null
                }

            Response (404):
                {
                    "status": "error",
                    "error": "Run not found"
                }
            """
            result = action_registry.execute(
                "beaver_workflow_status",
                {"run_id": run_id},
                {"api_endpoint": f"/workflow/status/{run_id}"}
            )

            if result.status != ActionStatus.SUCCESS:
                return jsonify({
                    "status": "error",
                    "error": result.message or "Run not found"
                }), 404

            # Add progress percentage
            data = result.data or {}
            total = data.get("steps_total", 0)
            completed = data.get("steps_completed", 0)
            data["progress_percent"] = (completed / total * 100) if total > 0 else 0

            return jsonify(data)

        @self.app.route("/workflow/history", methods=["GET"])
        def workflow_history():
            """
            Get history of workflow runs.

            Query params:
                - project_id: Optional filter by project
                - limit: Max number of results (default 20)

            Response (200):
                {
                    "runs": [
                        {
                            "run_id": "uuid",
                            "status": "completed" | "failed",
                            "project_id": "string",
                            "dry_run": bool,
                            "started_at": "ISO timestamp",
                            "completed_at": "ISO timestamp",
                            "steps_total": int,
                            "steps_completed": int,
                            "result": { ... }
                        }
                    ],
                    "total": int
                }
            """
            project_id = request.args.get("project_id")
            limit = request.args.get("limit", 20, type=int)

            result = action_registry.execute(
                "beaver_workflow_history",
                {"project_id": project_id, "limit": limit},
                {"api_endpoint": "/workflow/history"}
            )

            return jsonify(result.data or {"runs": [], "total": 0})

        @self.app.route("/webhook/grafana", methods=["POST"])
        def grafana_webhook():
            """
            Handle Grafana alert webhooks.

            Parses Grafana alert format and routes to configured actions.
            """
            payload = request.get_json() or {}

            try:
                alert = Alert.from_grafana(payload)
            except Exception as e:
                logger.error(f"Failed to parse Grafana alert: {e}")
                return jsonify({"status": "error", "error": str(e)}), 400

            # Determine action based on alert labels or default
            action_name = alert.labels.get("rabbit_action", "log")

            result = action_registry.execute(
                action_name,
                alert.to_dict(),
                {"source": "grafana", "raw_payload": payload}
            )

            return jsonify(result.to_dict())

        @self.app.route("/webhook/alertmanager", methods=["POST"])
        def alertmanager_webhook():
            """Handle Alertmanager webhooks."""
            payload = request.get_json() or {}

            try:
                alert = Alert.from_alertmanager(payload)
            except Exception as e:
                logger.error(f"Failed to parse Alertmanager alert: {e}")
                return jsonify({"status": "error", "error": str(e)}), 400

            action_name = alert.labels.get("rabbit_action", "log")

            result = action_registry.execute(
                action_name,
                alert.to_dict(),
                {"source": "alertmanager", "raw_payload": payload}
            )

            return jsonify(result.to_dict())

        @self.app.route("/webhook/manual", methods=["POST"])
        def manual_trigger():
            """
            Handle manual triggers from dashboards.

            This is optimized for the contextcore-workflow-panel.

            Request body:
                {
                    "action": "beaver_workflow",
                    "project_id": "my-project",
                    "dry_run": false,
                    "context": { ... }
                }
            """
            data = request.get_json() or {}

            action_name = data.get("action", "beaver_workflow")
            project_id = data.get("project_id", "default")
            dry_run = data.get("dry_run", False)

            # Build payload for action
            payload = {
                "project_id": project_id,
                "dry_run": dry_run,
                "trigger_source": "dashboard",
                "trigger_time": datetime.now().isoformat(),
            }

            context = data.get("context", {})
            context["manual_trigger"] = True

            result = action_registry.execute(action_name, payload, context)

            return jsonify(result.to_dict())

    def run(self, debug: bool = False):
        """Start the webhook server."""
        logger.info(f"Starting Rabbit webhook server on {self.host}:{self.port}")
        logger.info(f"Registered actions: {[a['name'] for a in action_registry.list_actions()]}")

        self.app.run(host=self.host, port=self.port, debug=debug)
