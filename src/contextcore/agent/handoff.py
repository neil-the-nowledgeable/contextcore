"""



class InputType(str, Enum):
    TEXT = "text"                # Free-form text input
    CHOICE = "choice"            # Single selection from options
    MULTI_CHOICE = "multi_choice"  # Multiple selections
    CONFIRMATION = "confirmation"   # Yes/No confirmation
    FILE = "file"                # File upload
    JSON = "json"                # Structured JSON input


@dataclass(frozen=True)
class InputOption:
    """Represents a selectable option for choice-based inputs."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, List, Optional, Tuple
from typing import Dict, List, Optional, Set
import json
import re

    value: str
    label: str
    description: Optional[str] = None
    is_default: bool = False
    'InputType',
    'InputOption', 
    'InputRequest',
    'InputResponse',
    'InputRequestManager',
    'StorageBackend'
]
Handoff management for ContextCore agent-to-agent communication.
This module provides status tracking and state management for agent handoffs,
with support for A2A-aligned states and transition validation.
__all__ = [
    'HandoffStatus',
    'StateTransition', 
    'Handoff',
    'VALID_TRANSITIONS',
    'validate_transition'
]
    HandoffStatus.COMPLETED,
    HandoffStatus.FAILED, 
    HandoffStatus.TIMEOUT,
    HandoffStatus.CANCELLED,
    HandoffStatus.REJECTED
})
_ACTIVE_STATES: Set[HandoffStatus] = frozenset({
    HandoffStatus.PENDING,
    HandoffStatus.ACCEPTED,
    HandoffStatus.IN_PROGRESS,
    HandoffStatus.INPUT_REQUIRED
})
    HandoffStatus.PENDING: frozenset({
        HandoffStatus.ACCEPTED,
        HandoffStatus.REJECTED, 
        HandoffStatus.CANCELLED
    }),
    HandoffStatus.ACCEPTED: frozenset({
        HandoffStatus.IN_PROGRESS,
        HandoffStatus.CANCELLED
    }),
    HandoffStatus.IN_PROGRESS: frozenset({
        HandoffStatus.INPUT_REQUIRED,
        HandoffStatus.COMPLETED,
        HandoffStatus.FAILED,
        HandoffStatus.CANCELLED
    }),
    HandoffStatus.INPUT_REQUIRED: frozenset({
        HandoffStatus.IN_PROGRESS,
        HandoffStatus.COMPLETED,
        HandoffStatus.FAILED,
        HandoffStatus.CANCELLED
    })
}

class Handoff:
    """Represents a handoff between agents with transition history.
    
    Maintains backward compatibility while adding transition tracking
    for audit and debugging purposes.
    """
    
    id: str
    source_agent: str
    target_agent: str
    status: HandoffStatus
    transitions: List[StateTransition] = field(default_factory=list)
    
    def add_transition(self, to_status: HandoffStatus, reason: Optional[str] = None, 
                      triggered_by: Optional[str] = None) -> bool:
        """Add a state transition if valid.
        
        Args:
            to_status: Target status to transition to
            reason: Optional reason for the transition
            triggered_by: Optional agent ID that triggered transition
            
        Returns:
            bool: True if transition was added successfully
        """
        if not validate_transition(self.status, to_status):
            return False
            
        transition = StateTransition(
            from_status=self.status,
            to_status=to_status,
            timestamp=datetime.utcnow(),
            reason=reason,
            triggered_by=triggered_by
        )
        
        self.transitions.append(transition)
        self.status = to_status
        return True

class HandoffStatus(str, Enum):
    """Enumeration of possible handoff states with helper methods."""
    
    # Existing states (preserved for backward compatibility)
    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    
    # New A2A-aligned states
    INPUT_REQUIRED = "input_required"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    
    def is_terminal(self) -> bool:
        """Check if this status represents a terminal state.
        
        Terminal states cannot transition to any other state and
        represent the end of a handoff lifecycle.
        
        Returns:
            bool: True if status is terminal (COMPLETED, FAILED, TIMEOUT, CANCELLED, REJECTED)
        """
        return self in _TERMINAL_STATES
    
    def is_active(self) -> bool:
        """Check if this status represents an active state.
        
        Active states indicate the handoff is still being processed
        and may transition to other states.
        
        Returns:
            bool: True if status is active (PENDING, ACCEPTED, IN_PROGRESS, INPUT_REQUIRED)
        """
        return self in _ACTIVE_STATES
    
    def can_accept_messages(self) -> bool:
        """Check if handoff in this status can accept new messages.
        
        Generally, terminal states cannot accept messages while
        active states can.
        
        Returns:
            bool: True if handoff can accept messages
        """
        return not self.is_terminal()


# Pre-computed sets for O(1) lookup performance

class InputRequest:
    """
    Represents a request for user input during an agent handoff.
    
    Example:
        >>> # Create a text input request
        >>> request = InputRequest.text(
        ...     handoff_id="h123",
        ...     question="What is your email?",
        ...     validation_pattern=r'^[^@]+@[^@]+\.[^@]+$'
        ... )
        
        >>> # Create a choice request
        >>> options = [
        ...     InputOption("yes", "Yes", "Proceed with action"),
        ...     InputOption("no", "No", "Cancel action", is_default=True)
        ... ]
        >>> request = InputRequest.choice(
        ...     handoff_id="h123",
        ...     question="Continue with deployment?",
        ...     options=options
        ... )
    """
    request_id: str
    handoff_id: str
    question: str
    input_type: InputType
    options: Optional[List[InputOption]] = None
    default_value: Optional[str] = None
    required: bool = True
    timeout_ms: int = 300000  # 5 minutes default
    validation_pattern: Optional[str] = None  # Regex for TEXT type
    min_selections: Optional[int] = None  # For MULTI_CHOICE
    max_selections: Optional[int] = None  # For MULTI_CHOICE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        """Set expiration time based on timeout."""
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(milliseconds=self.timeout_ms)

    def is_expired(self) -> bool:
        """Check if the input request has expired."""
        if self.expires_at:
            return datetime.now(timezone.utc) > self.expires_at
        return False

    def validate_response(self, value: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate input response against request constraints.
        
        Returns:
            tuple: (is_valid, error_message)
        """
        # Check required field
        if self.required and (value is None or (isinstance(value, str) and not value.strip())):
            return False, "This field is required"

        # Skip validation for optional empty values
        if not self.required and (value is None or value == ""):
            return True, None

        # Type-specific validation
        if self.input_type == InputType.TEXT:
            if not isinstance(value, str):
                return False, "Value must be a string"
            if self.validation_pattern and not re.match(self.validation_pattern, value):
                return False, "Input does not match required pattern"

        elif self.input_type == InputType.CHOICE:
            if not self.options:
                return False, "No options available for choice"
            valid_values = [option.value for option in self.options]
            if value not in valid_values:
                return False, f"Invalid choice. Must be one of: {', '.join(valid_values)}"

        elif self.input_type == InputType.MULTI_CHOICE:
            if not isinstance(value, list):
                return False, "Multi-choice value must be a list"
            if not self.options:
                return False, "No options available for multi-choice"
            
            valid_values = [option.value for option in self.options]
            invalid_values = [v for v in value if v not in valid_values]
            if invalid_values:
                return False, f"Invalid choices: {', '.join(invalid_values)}"
            
            if self.min_selections is not None and len(value) < self.min_selections:
                return False, f"Must select at least {self.min_selections} options"
            if self.max_selections is not None and len(value) > self.max_selections:
                return False, f"Cannot select more than {self.max_selections} options"

        elif self.input_type == InputType.CONFIRMATION:
            if not isinstance(value, bool):
                return False, "Confirmation value must be a boolean"

        elif self.input_type == InputType.JSON:
            if isinstance(value, str):
                try:
                    json.loads(value)
                except json.JSONDecodeError as e:
                    return False, f"Invalid JSON format: {str(e)}"
            elif not isinstance(value, (dict, list)):
                return False, "JSON value must be a valid JSON string, dict, or list"

        elif self.input_type == InputType.FILE:
            # Basic file validation - could be extended for specific file types
            if not isinstance(value, str) or not value:
                return False, "File path/identifier is required"

        return True, None

    @classmethod
    def confirmation(cls, handoff_id: str, question: str, **kwargs) -> 'InputRequest':
        """
        Create a confirmation (yes/no) input request.
        
        Args:
            handoff_id: The handoff requesting input
            question: The question to ask the user
            **kwargs: Additional parameters
            
        Returns:
            InputRequest configured for confirmation
        """
        return cls(
            handoff_id=handoff_id,
            question=question,
            input_type=InputType.CONFIRMATION,
            **kwargs
        )

    @classmethod
    def choice(cls, handoff_id: str, question: str, options: List[InputOption], **kwargs) -> 'InputRequest':
        """
        Create a single-choice input request.
        
        Args:
            handoff_id: The handoff requesting input
            question: The question to ask the user
            options: List of available choices
            **kwargs: Additional parameters
            
        Returns:
            InputRequest configured for single choice
        """
        return cls(
            handoff_id=handoff_id,
            question=question,
            input_type=InputType.CHOICE,
            options=options,
            **kwargs
        )

    @classmethod
    def text(cls, handoff_id: str, question: str, validation_pattern: Optional[str] = None, **kwargs) -> 'InputRequest':
        """
        Create a text input request.
        
        Args:
            handoff_id: The handoff requesting input
            question: The question to ask the user
            validation_pattern: Optional regex pattern for validation
            **kwargs: Additional parameters
            
        Returns:
            InputRequest configured for text input
        """
        return cls(
            handoff_id=handoff_id,
            question=question,
            input_type=InputType.TEXT,
            validation_pattern=validation_pattern,
            **kwargs
        )



class InputRequestManager:
    """
    Manages the lifecycle of input requests and responses.
    
    Example:
        >>> storage = MyStorageBackend()
        >>> manager = InputRequestManager(storage)
        >>> 
        >>> # Create a request
        >>> request = manager.create_request(
        ...     handoff_id="h123",
        ...     question="Enter your name:",
        ...     input_type=InputType.TEXT
        ... )
        >>> 
        >>> # Submit a response
        >>> response = manager.submit_response(
        ...     request_id=request.request_id,
        ...     value="John Doe",
        ...     responded_by="user_456"
        ... )
    """
    
    def __init__(self, storage: StorageBackend):
        """Initialize with a storage backend."""
        self.storage = storage
    
    def create_request(
        self,
        handoff_id: str,
        question: str,
        input_type: InputType,
        options: Optional[List[InputOption]] = None,
        **kwargs
    ) -> InputRequest:
        """
        Create and store a new input request.
        
        Args:
            handoff_id: The handoff requesting input
            question: The question to ask
            input_type: Type of input expected
            options: Options for choice-based inputs
            **kwargs: Additional request parameters
            
        Returns:
            The created InputRequest
        """
        # Generate unique request ID if not provided
        if 'request_id' not in kwargs:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            kwargs['request_id'] = f"req_{handoff_id}_{timestamp}"
        
        request = InputRequest(
            handoff_id=handoff_id,
            question=question,
            input_type=input_type,
            options=options,
            **kwargs
        )
        
        self.storage.save_request(request)
        return request
    
    def get_request(self, request_id: str) -> Optional[InputRequest]:
        """Retrieve an input request by ID."""
        return self.storage.get_request(request_id)
    
    def get_pending_requests(self, handoff_id: str) -> List[InputRequest]:
        """Get all pending (non-expired) requests for a handoff."""
        all_requests = self.storage.get_pending_requests(handoff_id)
        return [req for req in all_requests if not req.is_expired()]
    
    def submit_response(self, request_id: str, value: Any, responded_by: str) -> InputResponse:
        """
        Submit a response to an input request.
        
        Args:
            request_id: ID of the request being responded to
            value: The response value
            responded_by: ID of who provided the response
            
        Returns:
            The created InputResponse
            
        Raises:
            ValueError: If request not found, expired, or response invalid
        """
        request = self.get_request(request_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")
        
        if request.is_expired():
            raise ValueError(f"Request {request_id} has expired")
        
        # Validate the response
        is_valid, error_msg = request.validate_response(value)
        if not is_valid:
            raise ValueError(f"Invalid response: {error_msg}")
        
        response = InputResponse(
            request_id=request_id,
            handoff_id=request.handoff_id,
            value=value,
            responded_by=responded_by
        )
        
        self.storage.save_response(response)
        return response
    
    def cancel_request(self, request_id: str) -> bool:
        """
        Cancel a pending input request.
        
        Args:
            request_id: ID of the request to cancel
            
        Returns:
            True if cancelled successfully, False if not found
        """
        request = self.get_request(request_id)
        if not request:
            return False
        
        # Implementation would depend on storage backend
        # For now, just return True to indicate success
        return True
    
    def cleanup_expired_requests(self) -> int:
        """
        Clean up expired requests from storage.
        
        Returns:
            Number of requests cleaned up
        """
        expired_ids = self.storage.cleanup_expired_requests()
        return len(expired_ids)


# Export public interface

class InputResponse:
    """
    Represents a response to an input request.
    
    Example:
        >>> response = InputResponse(
        ...     request_id="req-123",
        ...     handoff_id="h123",
        ...     value="user@example.com",
        ...     responded_by="user_456"
        ... )
    """
    request_id: str
    handoff_id: str
    value: Any  # str, list[str], bool, dict depending on InputType
    responded_by: str  # agent_id or user_id
    responded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))



class StateTransition:
    """Records a state transition with metadata for audit trail."""
    
    from_status: HandoffStatus
    to_status: HandoffStatus
    timestamp: datetime
    reason: Optional[str] = None
    triggered_by: Optional[str] = None  # agent_id that triggered the transition
    
    def __post_init__(self) -> None:
        """Ensure timestamp is set if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


# Valid state transitions mapping - defines the allowed handoff state machine

class StorageBackend:
    """Abstract base interface for input request storage."""
    
    def save_request(self, request: InputRequest) -> None:
        """Save an input request to storage."""
        raise NotImplementedError
    
    def get_request(self, request_id: str) -> Optional[InputRequest]:
        """Retrieve an input request by ID."""
        raise NotImplementedError
    
    def get_pending_requests(self, handoff_id: str) -> List[InputRequest]:
        """Get all pending requests for a handoff."""
        raise NotImplementedError
    
    def save_response(self, response: InputResponse) -> None:
        """Save an input response to storage."""
        raise NotImplementedError
    
    def cleanup_expired_requests(self) -> List[str]:
        """Remove expired requests and return their IDs."""
        raise NotImplementedError



def validate_transition(from_status: HandoffStatus, to_status: HandoffStatus) -> bool:
    """Validate whether a state transition is allowed.
    
    Args:
        from_status: Current handoff status
        to_status: Desired target status
        
    Returns:
        bool: True if transition is valid according to state machine rules
        
    Examples:
        >>> validate_transition(HandoffStatus.PENDING, HandoffStatus.ACCEPTED)
        True
        >>> validate_transition(HandoffStatus.COMPLETED, HandoffStatus.IN_PROGRESS) 
        False
    """
    # Self-transitions are not allowed
    if from_status == to_status:
        return False
        
    # Check if transition is in valid transitions mapping
    valid_targets = VALID_TRANSITIONS.get(from_status, frozenset())
    return to_status in valid_targets



__all__ = ['Handoff', 'HandoffStatus', 'InputRequest', 'InputRequestManager', 'InputResponse', 'StateTransition', 'StorageBackend', 'validate_transition']