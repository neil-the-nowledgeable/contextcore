# src/contextcore/compat/operations.py
"""Operation name constants for OpenTelemetry GenAI semantic conventions.

This module provides standardized operation names for consistent tracking
across all ContextCore span types.
"""
from typing import Dict

__all__ = ['OPERATION_NAMES']

# Standard operation name mappings following module.action convention
OPERATION_NAMES: Dict[str, str] = {
    # Task operations - core workflow tracking
    "task_start": "task.start",
    "task_update": "task.update", 
    "task_complete": "task.complete",
    
    # Insight operations - analytics and monitoring
    "insight_emit": "insight.emit",
    "insight_query": "insight.query",
    
    # Handoff operations - inter-agent communication
    "handoff_create": "handoff.create",
    "handoff_accept": "handoff.accept",
    "handoff_complete": "handoff.complete",
    "handoff_fail": "handoff.fail",
    "handoff_cancel": "handoff.cancel",
    
    # Skill operations - capability execution
    "skill_emit": "skill.emit",
    "skill_invoke": "skill.invoke", 
    "skill_complete": "skill.complete",
    "skill_fail": "skill.fail",
}


# src/contextcore/compat/otel_genai.py (updated section)
"""Enhanced DualEmitAttributes for GenAI Operation Name Management."""
from typing import Dict, Any, Optional

from contextcore.compat import EmitMode

__all__ = ['DualEmitAttributes']

class DualEmitAttributes:
    """Manages dual emission of attributes for legacy and GenAI modes."""
    
    def __init__(self, mode: EmitMode) -> None:
        """Initialize with the specified emission mode.
        
        Args:
            mode: The emission mode (LEGACY or GENAI)
        """
        self.mode = mode

    def add_operation_name(self, attributes: Dict[str, Any], operation_key: str) -> Dict[str, Any]:
        """Add gen_ai.operation.name attribute based on emit mode.
        
        This method conditionally adds the GenAI operation name attribute
        only when not in legacy mode, ensuring backward compatibility.
        
        Args:
            attributes: Existing span attributes dictionary
            operation_key: Key to lookup operation name in OPERATION_NAMES
            
        Returns:
            Enhanced attributes dict with operation name if applicable
            
        Raises:
            TypeError: If attributes is not a dictionary
        """
        if not isinstance(attributes, dict):
            raise TypeError("attributes must be a dictionary")
            
        # Skip operation name addition in legacy mode
        if self.mode == EmitMode.LEGACY or not operation_key:
            return attributes

        # Import here to avoid circular imports
        from .operations import OPERATION_NAMES
        
        # Add standardized operation name
        op_name = OPERATION_NAMES.get(operation_key, operation_key)
        enhanced_attributes = attributes.copy()
        enhanced_attributes["gen_ai.operation.name"] = op_name
        
        return enhanced_attributes


# src/contextcore/tracker.py (updated sections)
"""Task tracking with OpenTelemetry GenAI operation names."""
from typing import Optional, Dict, Any

from contextcore.compat.otel_genai import DualEmitAttributes
from contextcore.compat import EmitMode

class TaskTracker:
    """Tracks task lifecycle events with proper operation naming."""
    
    def __init__(self, emit_mode: EmitMode) -> None:
        """Initialize tracker with emission mode configuration.
        
        Args:
            emit_mode: Determines attribute emission strategy
        """
        self.emit_mode = emit_mode
        self._dual_emit = DualEmitAttributes(emit_mode)

    def start_task(self, task_id: str, description: Optional[str] = None, **kwargs: Any) -> None:
        """Start a new task with proper operation tracking.
        
        Args:
            task_id: Unique identifier for the task
            description: Optional task description
            **kwargs: Additional task attributes
        """
        attributes = {
            "task.id": task_id,
            "task.status": "started",
            "task.description": description or "",
            **kwargs
        }

        # Add GenAI operation name via dual-emit layer
        attributes = self._dual_emit.add_operation_name(attributes, "task_start")

        # Create span with enhanced attributes
        span = self._tracer.start_span(
            name="task.start",
            attributes=attributes
        )
        # ... existing task start logic

    def update_task(self, task_id: str, updates: Dict[str, Any], **kwargs: Any) -> None:
        """Update an existing task with operation tracking."""
        attributes = {
            "task.id": task_id,
            "task.status": "updated",
            "task.updates": str(updates),  # Serialize for tracing
            **kwargs
        }
        
        attributes = self._dual_emit.add_operation_name(attributes, "task_update")
        
        span = self._tracer.start_span(
            name="task.update",
            attributes=attributes
        )
        # ... existing task update logic

    def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        """Complete a task with final operation tracking."""
        attributes = {
            "task.id": task_id,
            "task.status": "completed",
            "task.result": str(result) if result else "",
            **kwargs
        }

        attributes = self._dual_emit.add_operation_name(attributes, "task_complete")
        
        span = self._tracer.start_span(
            name="task.complete",
            attributes=attributes
        )
        # ... existing task completion logic


# src/contextcore/insights.py (updated sections)
"""Insight emission with GenAI operation tracking."""
from typing import Dict, Any

from contextcore.compat.otel_genai import DualEmitAttributes
from contextcore.compat import EmitMode

class InsightEmitter:
    """Emits insights with standardized operation naming."""
    
    def __init__(self, emit_mode: EmitMode) -> None:
        """Initialize emitter with emission mode configuration."""
        self.emit_mode = emit_mode
        self._dual_emit = DualEmitAttributes(emit_mode)

    def emit_insight(self, insight_data: Dict[str, Any], **kwargs: Any) -> None:
        """Emit insight data with proper operation tracking.
        
        Args:
            insight_data: The insight payload to emit
            **kwargs: Additional insight attributes
        """
        attributes = {
            "insight.type": insight_data.get("type", "unknown"),
            "insight.payload_size": len(str(insight_data)),
            **kwargs
        }
        
        # Add GenAI operation name
        attributes = self._dual_emit.add_operation_name(attributes, "insight_emit")
        
        span = self._tracer.start_span(
            name="insight.emit",
            attributes=attributes
        )
        # ... existing insight emission logic

    def query_insights(self, query_params: Dict[str, Any], **kwargs: Any) -> None:
        """Query existing insights with operation tracking."""
        attributes = {
            "insight.query": str(query_params),
            **kwargs
        }
        
        attributes = self._dual_emit.add_operation_name(attributes, "insight_query")
        
        span = self._tracer.start_span(
            name="insight.query", 
            attributes=attributes
        )
        # ... existing insight query logic


# src/contextcore/handoff.py (updated sections)
"""Handoff management with GenAI operation tracking."""
from typing import Optional, Dict, Any

from contextcore.compat.otel_genai import DualEmitAttributes
from contextcore.compat import EmitMode

class HandoffManager:
    """Manages handoff creation with operation tracking."""
    
    def __init__(self, emit_mode: EmitMode) -> None:
        """Initialize manager with emission mode configuration."""
        self.emit_mode = emit_mode
        self._dual_emit = DualEmitAttributes(emit_mode)

    def create_handoff(self, handoff_id: str, target_agent: str, **kwargs: Any) -> None:
        """Create a handoff with proper operation tracking."""
        attributes = {
            "handoff.id": handoff_id,
            "handoff.target": target_agent,
            "handoff.status": "created",
            **kwargs
        }
        
        attributes = self._dual_emit.add_operation_name(attributes, "handoff_create")

        span = self._tracer.start_span(
            name="handoff.create",
            attributes=attributes
        )
        # ... existing handoff creation logic

class HandoffReceiver:
    """Handles handoff acceptance with operation tracking."""
    
    def __init__(self, emit_mode: EmitMode) -> None:
        """Initialize receiver with emission mode configuration."""
        self.emit_mode = emit_mode
        self._dual_emit = DualEmitAttributes(emit_mode)

    def accept_handoff(self, handoff_id: str, **kwargs: Any) -> None:
        """Accept a handoff with proper operation tracking."""
        attributes = {
            "handoff.id": handoff_id,
            "handoff.status": "accepted",
            **kwargs
        }
        
        attributes = self._dual_emit.add_operation_name(attributes, "handoff_accept")

        span = self._tracer.start_span(
            name="handoff.accept",
            attributes=attributes
        )
        # ... existing handoff acceptance logic

    def complete_handoff(self, handoff_id: str, **kwargs: Any) -> None:
        """Complete a handoff with operation tracking."""
        attributes = {
            "handoff.id": handoff_id,
            "handoff.status": "completed",
            **kwargs
        }
        
        attributes = self._dual_emit.add_operation_name(attributes, "handoff_complete")

        span = self._tracer.start_span(
            name="handoff.complete",
            attributes=attributes
        )
        # ... existing handoff completion logic


# src/contextcore/skill/emitter.py (updated sections)
"""Skill capability emission with GenAI operation tracking."""
from typing import Dict, Any

from contextcore.compat.otel_genai import DualEmitAttributes
from contextcore.compat import EmitMode

class SkillCapabilityEmitter:
    """Emits skill capabilities with standardized operation naming."""
    
    def __init__(self, emit_mode: EmitMode) -> None:
        """Initialize emitter with emission mode configuration."""
        self.emit_mode = emit_mode
        self._dual_emit = DualEmitAttributes(emit_mode)

    def emit_skill_event(self, skill_data: Dict[str, Any], **kwargs: Any) -> None:
        """Emit skill event with proper operation tracking.
        
        Args:
            skill_data: The skill event payload
            **kwargs: Additional skill attributes
        """
        attributes = {
            "skill.name": skill_data.get("name", "unknown"),
            "skill.type": skill_data.get("type", "event"),
            **kwargs
        }
        
        # Add GenAI operation name
        attributes = self._dual_emit.add_operation_name(attributes, "skill_emit")
        
        span = self._tracer.start_span(
            name="skill.emit",
            attributes=attributes
        )
        # ... existing skill emission logic

    def invoke_skill(self, skill_name: str, parameters: Dict[str, Any], **kwargs: Any) -> None:
        """Invoke a skill with operation tracking."""
        attributes = {
            "skill.name": skill_name,
            "skill.parameters": str(parameters),
            "skill.status": "invoked",
            **kwargs
        }
        
        attributes = self._dual_emit.add_operation_name(attributes, "skill_invoke")
        
        span = self._tracer.start_span(
            name="skill.invoke",
            attributes=attributes
        )
        # ... existing skill invocation logic


# tests/test_operation_names.py
"""Comprehensive tests for GenAI operation name integration."""
import unittest
from unittest.mock import Mock, patch
from typing import Dict, Any

from contextcore.tracker import TaskTracker
from contextcore.insights import InsightEmitter
from contextcore.handoff import HandoffManager
from contextcore.skill.emitter import SkillCapabilityEmitter
from contextcore.compat import EmitMode
from contextcore.compat.operations import OPERATION_NAMES

class TestOperationNameIntegration(unittest.TestCase):
    """Test operation name emission across all components."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.genai_mode = EmitMode.GENAI
        self.legacy_mode = EmitMode.LEGACY
    
    def test_task_tracker_operation_names(self) -> None:
        """Test TaskTracker emits correct operation names."""
        tracker = TaskTracker(emit_mode=self.genai_mode)
        
        with patch.object(tracker, '_tracer') as mock_tracer:
            mock_span = Mock()
            mock_tracer.start_span.return_value = mock_span
            
            # Test task start operation
            tracker.start_task("test-task-1", "Test description")
            
            # Verify span was created with correct attributes
            call_args = mock_tracer.start_span.call_args
            span_name = call_args[1]["name"] if "name" in call_args[1] else call_args[0][0]
            attributes = call_args[1]["attributes"]
            
            self.assertEqual(span_name, "task.start")
            self.assertIn("gen_ai.operation.name", attributes)
            self.assertEqual(attributes["gen_ai.operation.name"], "task.start")
    
    def test_legacy_mode_no_operation_names(self) -> None:
        """Test that legacy mode doesn't emit operation names."""
        tracker = TaskTracker(emit_mode=self.legacy_mode)
        
        with patch.object(tracker, '_tracer') as mock_tracer:
            mock_span = Mock()
            mock_tracer.start_span.return_value = mock_span
            
            tracker.start_task("test-task-1")
            
            call_args = mock_tracer.start_span.call_args
            attributes = call_args[1]["attributes"]
            
            # Should not contain GenAI operation name
            self.assertNotIn("gen_ai.operation.name", attributes)
    
    def test_all_operation_mappings_exist(self) -> None:
        """Test that all expected operation mappings are defined."""
        expected_operations = [
            "task_start", "task_update", "task_complete",
            "insight_emit", "insight_query",
            "handoff_create", "handoff_accept", "handoff_complete", "handoff_fail", "handoff_cancel",
            "skill_emit", "skill_invoke", "skill_complete", "skill_fail"
        ]
        
        for operation in expected_operations:
            self.assertIn(operation, OPERATION_NAMES)
            # Verify naming convention (module.action)
            self.assertRegex(OPERATION_NAMES[operation], r'^[a-z]+\.[a-z]+$')

if __name__ == '__main__':
    unittest.main()