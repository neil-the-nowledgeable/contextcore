"""
Built-in Rabbit actions.

These actions are automatically registered when Rabbit is imported.
"""

from contextcore_rabbit.actions.log import LogAction
from contextcore_rabbit.actions.beaver_workflow import BeaverWorkflowAction

__all__ = ["LogAction", "BeaverWorkflowAction"]
