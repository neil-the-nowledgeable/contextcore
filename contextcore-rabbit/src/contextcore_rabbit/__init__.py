"""
ContextCore Rabbit (Waabooz) - Alert-Triggered Automation Framework.

Rabbit is a trigger mechanism that "wakes up" systems in response to alerts.
It receives webhook payloads, parses them into a unified format, and dispatches
configured actions. Fire-and-forget design.

Usage:
    from contextcore_rabbit import WebhookServer, action_registry

    # Register custom actions
    @action_registry.register("my_action")
    class MyAction(Action):
        def execute(self, alert, context):
            # Do something
            pass

    # Start server
    server = WebhookServer(port=8080)
    server.run()
"""

from contextcore_rabbit.action import Action, ActionResult, action_registry
from contextcore_rabbit.alert import Alert, AlertSeverity
from contextcore_rabbit.server import WebhookServer

__version__ = "0.1.0"
__all__ = [
    "Action",
    "ActionResult",
    "action_registry",
    "Alert",
    "AlertSeverity",
    "WebhookServer",
]
