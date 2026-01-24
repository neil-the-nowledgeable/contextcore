"""A2A client for communicating with A2A-compatible agents."""
__all__ = ['A2AError', 'A2AClient']


from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx

from ..agents.card import AgentCard
from ..core.handoff import Handoff
from ..core.message import Message
from .adapters import TaskAdapter
from .auth import AuthConfig
import json

__all__ = ["A2AClient", "A2AError"]


class A2AError(Exception):
    """Error from A2A JSON-RPC response."""
    
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"A2A Error {code}: {message}")


class A2AClient:
    """Client for communicating with A2A-compatible agents."""
    
    def __init__(
        self,
        base_url: str,
        auth: AuthConfig | None = None,
        timeout_seconds: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.timeout = timeout_seconds
        self._http: httpx.Client | None = None
        self._request_counter = 0
    
    def __enter__(self) -> "A2AClient":
        self._http = httpx.Client(timeout=self.timeout)
        return self
    
    def __exit__(self, *args) -> None:
        if self._http:
            self._http.close()
    
    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client instance."""
        if self._http is None:
            self._http = httpx.Client(timeout=self.timeout)
        return self._http
    
    def _next_request_id(self) -> str:
        """Generate next unique request ID."""
        self._request_counter += 1
        return f"req-{self._request_counter}"
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers if auth is configured."""
        if self.auth:
            return self.auth.get_headers()
        return {}
    
    def _request(self, method: str, params: dict | None = None) -> dict:
        """Send JSON-RPC request."""
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._next_request_id(),
        }
        
        headers = {"Content-Type": "application/json"}
        headers.update(self._get_auth_headers())
        
        # Use correct A2A endpoint
        response = self._get_client().post(
            f"{self.base_url}/a2a",
            json=request,
            headers=headers,
        )
        response.raise_for_status()
        
        result = response.json()
        if "error" in result:
            error = result["error"]
            raise A2AError(
                error.get("code", -1),
                error.get("message", "Unknown error"),
                error.get("data")
            )
        
        return result.get("result", {})
    
    def send_message(
        self,
        message: Message,
        context_id: str | None = None,
        capability_id: str | None = None,
    ) -> dict:
        """Send message to remote agent (message.send)."""
        params = {
            "message": message.to_a2a_dict(),
        }
        if context_id:
            params["contextId"] = context_id
        if capability_id:
            params["capabilityId"] = capability_id
        
        return self._request("message.send", params)
    
    def get_task(self, task_id: str) -> dict:
        """Get task status (tasks.get)."""
        return self._request("tasks.get", {"taskId": task_id})
    
    def list_tasks(self, context_id: str | None = None, limit: int = 100) -> list[dict]:
        """List tasks (tasks.list)."""
        params = {"limit": limit}
        if context_id:
            params["contextId"] = context_id
        result = self._request("tasks.list", params)
        return result.get("tasks", [])
    
    def cancel_task(self, task_id: str) -> dict:
        """Cancel task (tasks.cancel)."""
        return self._request("tasks.cancel", {"taskId": task_id})
    
    def get_agent_card(self) -> AgentCard:
        """Fetch agent card from .well-known/agent.json."""
        headers = self._get_auth_headers()
        response = self._get_client().get(
            f"{self.base_url}/.well-known/agent.json",
            headers=headers
        )
        response.raise_for_status()
        return AgentCard.from_json(response.json())
    
    def send_and_await(
        self,
        message: Message,
        timeout_ms: int = 300000,
        poll_interval_ms: int = 1000,
    ) -> Handoff:
        """Send message and wait for completion, returning as Handoff."""
        task_response = self.send_message(message)
        task_id = task_response.get("taskId")
        
        if not task_id:
            raise A2AError(-1, "No taskId returned from send_message")
        
        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            task = self.get_task(task_id)
            status = task.get("status")
            
            if status in ("COMPLETED", "FAILED", "CANCELLED", "REJECTED"):
                return TaskAdapter.task_to_handoff(task, "local", "remote")
            
            time.sleep(poll_interval_ms / 1000)
        
        raise TimeoutError(f"Task {task_id} did not complete within {timeout_ms}ms")
    
    def send_text(self, text: str, **kwargs) -> dict:
        """Convenience method to send text message."""
        return self.send_message(Message.from_text(text), **kwargs)
