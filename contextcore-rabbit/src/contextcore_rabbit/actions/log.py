"""
Log action - writes alerts/triggers to the log.

A simple built-in action for debugging and testing.
"""

import logging
from typing import Any, Dict

from contextcore_rabbit.action import Action, ActionResult, ActionStatus, action_registry

logger = logging.getLogger(__name__)


@action_registry.register("log")
class LogAction(Action):
    """
    Log action - writes payload to logs.

    Useful for debugging webhook integrations.
    """

    name = "log"
    description = "Log the trigger payload to console/file"

    def execute(self, payload: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        """Log the payload."""
        logger.info(f"[LogAction] Payload: {payload}")
        logger.info(f"[LogAction] Context: {context}")

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_name=self.name,
            message="Payload logged successfully",
            data={"payload_keys": list(payload.keys())},
        )
