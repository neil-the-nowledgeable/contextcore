# File: src/contextcore/a2a/message_handler.py
"""JSON-RPC 2.0 message handler for A2A protocol methods."""
__all__ = ['A2AErrorCode', 'A2AMessageHandler']


from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional

from contextcore.api.handoffs import HandoffsAPI
from contextcore.api.skills import SkillsAPI
from contextcore.models.agent_card import AgentCard
from contextcore.models.message import Message
from contextcore.a2a.task_adapter import TaskAdapter


class A2AErrorCode(IntEnum):
    """JSON-RPC 2.0 and A2A-specific error codes."""
    # Standard JSON-RPC 2.0 error codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # A2A-specific error codes
    TASK_NOT_FOUND = -32001
    TASK_CANCELLED = -32002
    CONTENT_TYPE_NOT_SUPPORTED = -32003
    VERSION_NOT_SUPPORTED = -32004


class A2AMessageHandler:
    """Handle A2A JSON-RPC messages.
    
    This handler processes A2A JSON-RPC 2.0 requests and routes them
    to appropriate ContextCore operations via HandoffsAPI and SkillsAPI.
    """

    def __init__(
        self,
        handoffs_api: HandoffsAPI,
        skills_api: SkillsAPI,
        agent_card: AgentCard,
    ):
        """Initialize the A2A message handler.
        
        Args:
            handoffs_api: API for managing handoffs between agents
            skills_api: API for managing agent skills and capabilities
            agent_card: The agent card for this handler's agent
        """
        self.handoffs = handoffs_api
        self.skills = skills_api
        self.agent_card = agent_card
        
        # Registry of supported A2A methods mapped to their handlers
        self._methods: Dict[str, Callable[[Dict], Dict]] = {
            "message.send": self._handle_message_send,
            "tasks.get": self._handle_tasks_get,
            "tasks.list": self._handle_tasks_list,
            "tasks.cancel": self._handle_tasks_cancel,
            "agent.getExtendedAgentCard": self._handle_get_agent_card,
        }

    def handle(self, request: Dict) -> Dict:
        """Handle JSON-RPC 2.0 request.
        
        Args:
            request: The JSON-RPC 2.0 request dictionary
            
        Returns:
            JSON-RPC 2.0 response dictionary (either success or error)
        """
        # Validate basic request structure
        if not self._is_valid_request(request):
            return self._error_response(
                None, 
                A2AErrorCode.INVALID_REQUEST, 
                "Invalid request"
            )

        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        # Check if method exists
        if method not in self._methods:
            return self._error_response(
                request_id,
                A2AErrorCode.METHOD_NOT_FOUND,
                f"Method not found: {method}"
            )

        # Execute method handler with proper error handling
        try:
            result = self._methods[method](params)
            return self._success_response(request_id, result)
        except ValueError as e:
            return self._error_response(
                request_id,
                A2AErrorCode.INVALID_PARAMS,
                str(e)
            )
        except Exception as e:
            return self._error_response(
                request_id,
                A2AErrorCode.INTERNAL_ERROR,
                str(e)
            )

    def _handle_message_send(self, params: Dict) -> Dict:
        """Handle message.send - creates handoff.
        
        Creates a new handoff task from an incoming A2A message.
        
        Args:
            params: Parameters containing message, contextId, and capabilityId
            
        Returns:
            Task representation of the created handoff
        """
        message = params.get("message", {})
        context_id = params.get("contextId")
        capability_id = params.get("capabilityId", "default")

        # Extract task information from message
        task_text = self._extract_text(message)
        inputs = self._extract_inputs(message)

        # Create handoff in ContextCore
        handoff_id = self.handoffs.create(
            to_agent=self.agent_card.agent_id,
            capability_id=capability_id,
            task=task_text,
            inputs=inputs,
            expected_output={"type": "any", "fields": []},
        )

        # Return task representation
        handoff = self.handoffs.get(handoff_id)
        return TaskAdapter.handoff_to_task(
            handoff,
            messages=[Message.from_a2a_dict(message)],
        )

    def _handle_tasks_get(self, params: Dict) -> Dict:
        """Handle tasks.get - returns task status.
        
        Args:
            params: Parameters containing taskId
            
        Returns:
            Task representation with current status
        """
        task_id = params.get("taskId")
        if not task_id:
            raise ValueError("taskId is required")

        result = self.handoffs.get(task_id)
        if not result:
            raise ValueError("Task not found")
            
        return TaskAdapter.handoff_to_task(result)

    def _handle_tasks_list(self, params: Dict) -> Dict:
        """Handle tasks.list - returns list of tasks.
        
        Args:
            params: Optional filtering parameters
            
        Returns:
            Dictionary containing list of tasks
        """
        # Get all handoffs and convert to task format
        handoffs = self.handoffs.list()
        tasks = [TaskAdapter.handoff_to_task(handoff) for handoff in handoffs]
        
        return {"tasks": tasks}

    def _handle_tasks_cancel(self, params: Dict) -> Dict:
        """Handle tasks.cancel - cancels a task.
        
        Args:
            params: Parameters containing taskId
            
        Returns:
            Cancellation result with task ID and status
        """
        task_id = params.get("taskId")
        if not task_id:
            raise ValueError("taskId is required")

        success = self.handoffs.cancel(task_id)
        return {
            "taskId": task_id,
            "status": "CANCELLED" if success else "FAILED"
        }

    def _handle_get_agent_card(self, params: Dict) -> Dict:
        """Handle agent.getExtendedAgentCard.
        
        Args:
            params: Unused parameters (kept for consistency)
            
        Returns:
            Agent card in A2A JSON format
        """
        return self.agent_card.to_a2a_json()

    def _success_response(self, request_id: Any, result: Any) -> Dict:
        """Create a JSON-RPC 2.0 success response.
        
        Args:
            request_id: The request ID to echo back
            result: The result data to return
            
        Returns:
            JSON-RPC 2.0 success response dictionary
        """
        return {
            "jsonrpc": "2.0",
            "result": result,
            "id": request_id
        }

    def _error_response(self, request_id: Any, code: int, message: str) -> Dict:
        """Create a JSON-RPC 2.0 error response.
        
        Args:
            request_id: The request ID to echo back
            code: The error code (from A2AErrorCode enum)
            message: Human-readable error message
            
        Returns:
            JSON-RPC 2.0 error response dictionary
        """
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message
            },
            "id": request_id
        }

    def _is_valid_request(self, request: Dict) -> bool:
        """Validate the structure of a JSON-RPC 2.0 request.
        
        Args:
            request: The request dictionary to validate
            
        Returns:
            True if the request is valid, False otherwise
        """
        return (
            isinstance(request, dict)
            and request.get("jsonrpc") == "2.0"
            and "method" in request
        )

    def _extract_text(self, message: Dict) -> str:
        """Extract text content from an A2A message.
        
        Args:
            message: The A2A message dictionary
            
        Returns:
            The extracted text content
        """
        return message.get("content", "")

    def _extract_inputs(self, message: Dict) -> Dict:
        """Extract inputs from an A2A message.
        
        Filters out message metadata to get just the input data.
        
        Args:
            message: The A2A message dictionary
            
        Returns:
            Dictionary of input parameters
        """
        return {
            k: v for k, v in message.items() 
            if k not in ["type", "content"]
        }


__all__ = [
    "A2AErrorCode",
    "A2AMessageHandler",
]
