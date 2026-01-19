"""
Tests for state persistence - SpanState and StateManager.
"""

import json
import os
import pytest
import tempfile
from datetime import datetime, timezone

from contextcore.state import (
    SpanState,
    StateManager,
    format_trace_id,
    format_span_id,
    parse_trace_id,
    parse_span_id,
)


@pytest.fixture
def temp_state_dir():
    """Create a temporary directory for state files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def state_manager(temp_state_dir):
    """Create a StateManager with test directory."""
    return StateManager(project="test-project", state_dir=temp_state_dir)


@pytest.fixture
def sample_span_state():
    """Create a sample SpanState for testing."""
    return SpanState(
        task_id="TASK-123",
        span_name="task:TASK-123",
        trace_id="0" * 32,
        span_id="0" * 16,
        parent_span_id=None,
        start_time=datetime.now(timezone.utc).isoformat(),
        attributes={
            "task.id": "TASK-123",
            "task.type": "task",
            "task.title": "Test task",
            "task.status": "in_progress",
        },
        events=[
            {
                "name": "task.created",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "attributes": {},
            }
        ],
        status="UNSET",
        status_description=None,
    )


class TestSpanState:
    """Tests for SpanState dataclass."""

    def test_to_dict(self, sample_span_state):
        """SpanState should convert to dict."""
        d = sample_span_state.to_dict()

        assert d["task_id"] == "TASK-123"
        assert d["span_name"] == "task:TASK-123"
        assert d["trace_id"] == "0" * 32
        assert d["attributes"]["task.type"] == "task"

    def test_from_dict(self, sample_span_state):
        """SpanState should reconstruct from dict."""
        d = sample_span_state.to_dict()
        restored = SpanState.from_dict(d)

        assert restored.task_id == sample_span_state.task_id
        assert restored.span_name == sample_span_state.span_name
        assert restored.attributes == sample_span_state.attributes

    def test_roundtrip(self, sample_span_state):
        """Dict conversion should be lossless."""
        d = sample_span_state.to_dict()
        restored = SpanState.from_dict(d)
        d2 = restored.to_dict()

        assert d == d2


class TestStateManager:
    """Tests for StateManager."""

    def test_save_span(self, state_manager, sample_span_state):
        """Should save span state to file."""
        state_manager.save_span(sample_span_state)

        # Check file exists
        file_path = state_manager.project_dir / "TASK-123.json"
        assert file_path.exists()

        # Check contents
        with open(file_path) as f:
            data = json.load(f)
        assert data["task_id"] == "TASK-123"

    def test_load_span(self, state_manager, sample_span_state):
        """Should load span state from file."""
        state_manager.save_span(sample_span_state)

        # Clear cache to force file read
        state_manager._active_spans.clear()

        loaded = state_manager.load_span("TASK-123")
        assert loaded is not None
        assert loaded.task_id == "TASK-123"
        assert loaded.attributes["task.type"] == "task"

    def test_load_span_nonexistent(self, state_manager):
        """Should return None for missing span."""
        loaded = state_manager.load_span("NONEXISTENT")
        assert loaded is None

    def test_remove_span(self, state_manager, sample_span_state):
        """Should move span to completed directory."""
        state_manager.save_span(sample_span_state)
        state_manager.remove_span("TASK-123")

        # Active file should be gone
        active_file = state_manager.project_dir / "TASK-123.json"
        assert not active_file.exists()

        # Should be in completed
        completed_file = state_manager.project_dir / "completed" / "TASK-123.json"
        assert completed_file.exists()

        # Should have end_time
        with open(completed_file) as f:
            data = json.load(f)
        assert "end_time" in data

    def test_get_active_spans(self, state_manager):
        """Should return all active spans."""
        # Create multiple spans
        for i in range(3):
            state = SpanState(
                task_id=f"TASK-{i}",
                span_name=f"task:TASK-{i}",
                trace_id="0" * 32,
                span_id=f"{i}" * 16,
                parent_span_id=None,
                start_time=datetime.now(timezone.utc).isoformat(),
                attributes={"task.id": f"TASK-{i}"},
                events=[],
                status="UNSET",
                status_description=None,
            )
            state_manager.save_span(state)

        # Clear cache
        state_manager._active_spans.clear()

        active = state_manager.get_active_spans()
        assert len(active) == 3
        assert "TASK-0" in active
        assert "TASK-1" in active
        assert "TASK-2" in active

    def test_get_completed_spans(self, state_manager, sample_span_state):
        """Should return completed spans."""
        # Save and complete
        state_manager.save_span(sample_span_state)
        state_manager.remove_span("TASK-123")

        completed = state_manager.get_completed_spans()
        assert len(completed) == 1
        assert completed[0].task_id == "TASK-123"

    def test_get_completed_spans_since(self, state_manager, sample_span_state):
        """Should filter by time."""
        state_manager.save_span(sample_span_state)
        state_manager.remove_span("TASK-123")

        # Future date should return nothing
        future = datetime(2030, 1, 1, tzinfo=timezone.utc)
        completed = state_manager.get_completed_spans(since=future)
        assert len(completed) == 0

    def test_add_event(self, state_manager, sample_span_state):
        """Should add event to span state."""
        state_manager.save_span(sample_span_state)

        state_manager.add_event(
            "TASK-123",
            "task.status_changed",
            {"from": "todo", "to": "in_progress"},
        )

        # Reload and check
        state_manager._active_spans.clear()
        loaded = state_manager.load_span("TASK-123")
        assert len(loaded.events) == 2
        assert loaded.events[-1]["name"] == "task.status_changed"

    def test_update_attribute(self, state_manager, sample_span_state):
        """Should update span attribute."""
        state_manager.save_span(sample_span_state)

        state_manager.update_attribute("TASK-123", "task.status", "done")

        state_manager._active_spans.clear()
        loaded = state_manager.load_span("TASK-123")
        assert loaded.attributes["task.status"] == "done"

    def test_update_status(self, state_manager, sample_span_state):
        """Should update span status."""
        state_manager.save_span(sample_span_state)

        state_manager.update_status("TASK-123", "OK", "Task completed")

        state_manager._active_spans.clear()
        loaded = state_manager.load_span("TASK-123")
        assert loaded.status == "OK"
        assert loaded.status_description == "Task completed"


class TestTraceIdFormatting:
    """Tests for trace/span ID formatting utilities."""

    def test_format_trace_id(self):
        """Should format trace ID as hex."""
        trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        formatted = format_trace_id(trace_id)
        assert formatted == "1234567890abcdef1234567890abcdef"
        assert len(formatted) == 32

    def test_format_span_id(self):
        """Should format span ID as hex."""
        span_id = 0x1234567890ABCDEF
        formatted = format_span_id(span_id)
        assert formatted == "1234567890abcdef"
        assert len(formatted) == 16

    def test_parse_trace_id(self):
        """Should parse hex trace ID."""
        hex_str = "1234567890abcdef1234567890abcdef"
        parsed = parse_trace_id(hex_str)
        assert parsed == 0x1234567890ABCDEF1234567890ABCDEF

    def test_parse_span_id(self):
        """Should parse hex span ID."""
        hex_str = "1234567890abcdef"
        parsed = parse_span_id(hex_str)
        assert parsed == 0x1234567890ABCDEF

    def test_roundtrip_trace_id(self):
        """Format then parse should be identity."""
        original = 0xDEADBEEFCAFEBABEDEADBEEFCAFEBABE
        formatted = format_trace_id(original)
        parsed = parse_trace_id(formatted)
        assert parsed == original

    def test_roundtrip_span_id(self):
        """Format then parse should be identity."""
        original = 0xDEADBEEFCAFEBABE
        formatted = format_span_id(original)
        parsed = parse_span_id(formatted)
        assert parsed == original

    def test_format_zero_padded(self):
        """Small IDs should be zero-padded."""
        trace_id = 0x1
        formatted = format_trace_id(trace_id)
        assert formatted == "00000000000000000000000000000001"
        assert len(formatted) == 32
