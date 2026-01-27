"""
Action framework for Rabbit.

Actions are fire-and-forget handlers that respond to alerts/triggers.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class ActionStatus(Enum):
    """Result status of an action execution."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ActionResult:
    """Result of an action execution."""
    status: ActionStatus
    action_name: str
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "action_name": self.action_name,
            "message": self.message,
            "data": self.data,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


class Action(ABC):
    """
    Base class for Rabbit actions.

    Actions are fire-and-forget handlers. They receive a trigger payload,
    do their work, and return a result. They should NOT:
    - Wait for long-running operations to complete
    - Manage ongoing state or conversations
    - Coordinate multi-step processes

    For complex workflows, the action should trigger another system
    (like Beaver) and return immediately.
    """

    name: str = "base_action"
    description: str = "Base action class"

    @abstractmethod
    def execute(self, payload: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        """
        Execute the action.

        Args:
            payload: The trigger payload (alert data, webhook body, etc.)
            context: Additional context (project info, enrichment data, etc.)

        Returns:
            ActionResult indicating success/failure
        """
        pass

    def validate(self, payload: Dict[str, Any]) -> Optional[str]:
        """
        Validate the payload before execution.

        Returns:
            Error message if invalid, None if valid
        """
        return None


class ActionRegistry:
    """
    Registry for Rabbit actions.

    Actions can be registered via decorator or direct registration.
    """

    def __init__(self):
        self._actions: Dict[str, Type[Action]] = {}
        self._instances: Dict[str, Action] = {}

    def register(self, name: str) -> Callable[[Type[Action]], Type[Action]]:
        """
        Decorator to register an action class.

        Usage:
            @action_registry.register("my_action")
            class MyAction(Action):
                ...
        """
        def decorator(cls: Type[Action]) -> Type[Action]:
            cls.name = name
            self._actions[name] = cls
            logger.info(f"Registered action: {name}")
            return cls
        return decorator

    def register_class(self, name: str, cls: Type[Action]) -> None:
        """Register an action class directly."""
        cls.name = name
        self._actions[name] = cls
        logger.info(f"Registered action: {name}")

    def get(self, name: str) -> Optional[Action]:
        """Get an action instance by name."""
        if name not in self._actions:
            return None

        # Lazy instantiation
        if name not in self._instances:
            self._instances[name] = self._actions[name]()

        return self._instances[name]

    def list_actions(self) -> List[Dict[str, str]]:
        """List all registered actions."""
        return [
            {"name": name, "description": cls.description}
            for name, cls in self._actions.items()
        ]

    def execute(
        self,
        action_name: str,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ActionResult:
        """
        Execute an action by name.

        This is fire-and-forget - it starts the action and returns
        the immediate result. Long-running work should be delegated
        to background systems.
        """
        import time
        start_time = time.time()

        action = self.get(action_name)
        if not action:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_name=action_name,
                message=f"Action not found: {action_name}"
            )

        context = context or {}

        # Validate
        error = action.validate(payload)
        if error:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_name=action_name,
                message=f"Validation failed: {error}"
            )

        # Execute
        try:
            result = action.execute(payload, context)
            result.duration_ms = (time.time() - start_time) * 1000
            return result
        except Exception as e:
            logger.exception(f"Action {action_name} failed")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_name=action_name,
                message=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )


# Global registry instance
action_registry = ActionRegistry()
