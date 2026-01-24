"""
Tests for TaskTracker - the core tasks-as-spans implementation.
"""

import pytest
import tempfile
import os
from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from contextcore.tracker import (
    TaskTracker,
    SprintTracker,
    TaskType,
    TaskStatus,
    Priority,
    TASK_ID,
    TASK_TYPE,
    TASK_TITLE,
    TASK_STATUS,
    TASK_PRIORITY,
    TASK_PERCENT_COMPLETE,
    PROJECT_ID)


class CollectingExporter(SpanExporter):
    """Collects spans in memory for testing."""

    def __init__(self):
        self.spans = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


@pytest.fixture
def temp_state_dir():
    """Create a temporary directory for state persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def exporter():
    """Create a collecting exporter for testing."""
    return CollectingExporter()


@pytest.fixture
def tracker(temp_state_dir, exporter):
    """Create a TaskTracker with test configuration."""
    return TaskTracker(
        project="test-project",
        service_name="test-service",
        state_dir=temp_state_dir,
        exporter=exporter)


class TestTaskCreation:
    """Tests for task creation."""

    def test_start_task_creates_span(self, tracker, exporter):
        """Starting a task should create an active span."""
        ctx = tracker.start_task(
            task_id="TASK-1",
            title="Test task",
            task_type="task")

        assert ctx is not None
        assert "TASK-1" in tracker.get_active_tasks()

    def test_start_task_sets_attributes(self, tracker, exporter):
        """Task attributes should be set on the span."""
        tracker.start_task(
            task_id="TASK-2",
            title="Test with attributes",
            task_type="story",
            priority="high",
            assignee="alice",
            story_points=5,
            labels=["backend", "api"])

        # Complete to flush span
        tracker.complete_task("TASK-2")
        tracker.shutdown()

        assert len(exporter.spans) >= 1
        span = exporter.spans[-1]

        assert span.attributes[TASK_ID] == "TASK-2"
        assert span.attributes[TASK_TYPE] == "story"
        assert span.attributes[TASK_TITLE] == "Test with attributes"
        assert span.attributes[TASK_PRIORITY] == "high"
        assert span.attributes["task.assignee"] == "alice"
        assert span.attributes["task.story_points"] == 5

    def test_start_task_with_parent(self, tracker, exporter):
        """Task with parent should create child span."""
        # Start parent
        tracker.start_task(
            task_id="EPIC-1",
            title="Parent epic",
            task_type="epic")

        # Start child
        tracker.start_task(
            task_id="STORY-1",
            title="Child story",
            task_type="story",
            parent_id="EPIC-1")

        assert "EPIC-1" in tracker.get_active_tasks()
        assert "STORY-1" in tracker.get_active_tasks()
        assert tracker._parent_map["STORY-1"] == "EPIC-1"

    def test_start_task_duplicate_returns_existing(self, tracker, exporter):
        """Starting same task twice should return existing span."""
        ctx1 = tracker.start_task(task_id="TASK-DUP", title="Original")
        ctx2 = tracker.start_task(task_id="TASK-DUP", title="Duplicate")

        assert ctx1.span_id == ctx2.span_id


class TestStatusUpdates:
    """Tests for status transitions."""

    def test_update_status_adds_event(self, tracker, exporter):
        """Updating status should add span event."""
        tracker.start_task(task_id="TASK-S1", title="Status test")
        tracker.update_status("TASK-S1", "in_progress")
        tracker.complete_task("TASK-S1")
        tracker.shutdown()

        span = exporter.spans[-1]
        events = [e.name for e in span.events]
        assert "task.status_changed" in events

    def test_block_task_sets_error_status(self, tracker, exporter):
        """Blocking a task should set ERROR status."""
        tracker.start_task(task_id="TASK-B1", title="Block test")
        tracker.block_task("TASK-B1", reason="Waiting on dependency")

        # Verify span status (need to complete to see in exporter)
        tracker.complete_task("TASK-B1")
        tracker.shutdown()

        span = exporter.spans[-1]
        events = [e.name for e in span.events]
        assert "task.blocked" in events

    def test_unblock_task_clears_error(self, tracker, exporter):
        """Unblocking should clear error status."""
        tracker.start_task(task_id="TASK-U1", title="Unblock test")
        tracker.block_task("TASK-U1", reason="Blocked")
        tracker.unblock_task("TASK-U1", new_status="in_progress")
        tracker.complete_task("TASK-U1")
        tracker.shutdown()

        span = exporter.spans[-1]
        events = [e.name for e in span.events]
        assert "task.blocked" in events
        assert "task.unblocked" in events


class TestCompletion:
    """Tests for task completion."""

    def test_complete_task_ends_span(self, tracker, exporter):
        """Completing a task should end the span."""
        tracker.start_task(task_id="TASK-C1", title="Complete test")
        tracker.complete_task("TASK-C1")

        assert "TASK-C1" not in tracker.get_active_tasks()

    def test_complete_task_sets_done_status(self, tracker, exporter):
        """Completed task should have DONE status."""
        tracker.start_task(task_id="TASK-C2", title="Status check")
        tracker.complete_task("TASK-C2")
        tracker.shutdown()

        span = exporter.spans[-1]
        assert span.attributes[TASK_STATUS] == TaskStatus.DONE.value

    def test_complete_task_sets_100_percent(self, tracker, exporter):
        """Completed task should be 100% complete."""
        tracker.start_task(task_id="TASK-C3", title="Progress check")
        tracker.complete_task("TASK-C3")
        tracker.shutdown()

        span = exporter.spans[-1]
        assert span.attributes[TASK_PERCENT_COMPLETE] == 100.0

    def test_cancel_task_ends_span(self, tracker, exporter):
        """Cancelling a task should end the span."""
        tracker.start_task(task_id="TASK-X1", title="Cancel test")
        tracker.cancel_task("TASK-X1", reason="No longer needed")

        assert "TASK-X1" not in tracker.get_active_tasks()


class TestProgress:
    """Tests for progress tracking."""

    def test_set_progress_updates_attribute(self, tracker, exporter):
        """Manual progress should update attribute."""
        tracker.start_task(task_id="TASK-P1", title="Progress test")
        tracker.set_progress("TASK-P1", 50.0)

        progress = tracker.get_progress("TASK-P1")
        assert progress == 50.0

    def test_progress_clamped_to_range(self, tracker, exporter):
        """Progress should be clamped to 0-100."""
        tracker.start_task(task_id="TASK-P2", title="Clamp test")

        tracker.set_progress("TASK-P2", 150.0)
        assert tracker.get_progress("TASK-P2") == 100.0

        tracker.set_progress("TASK-P2", -10.0)
        assert tracker.get_progress("TASK-P2") == 0.0

    def test_child_completion_updates_parent_progress(self, tracker, exporter):
        """Completing child tasks should update parent progress."""
        # Create parent
        tracker.start_task(task_id="STORY-P", title="Parent story", task_type="story")

        # Create 2 children
        tracker.start_task(
            task_id="TASK-P1",
            title="Child 1",
            task_type="task",
            parent_id="STORY-P")
        tracker.start_task(
            task_id="TASK-P2",
            title="Child 2",
            task_type="task",
            parent_id="STORY-P")

        # Complete one child
        tracker.complete_task("TASK-P1")

        # Parent should be 50% complete
        progress = tracker.get_progress("STORY-P")
        assert progress == 50.0


class TestSprintTracker:
    """Tests for SprintTracker."""

    def test_start_sprint(self, tracker, exporter):
        """Starting a sprint should create span."""
        sprint_tracker = SprintTracker(tracker)
        ctx = sprint_tracker.start_sprint(
            sprint_id="sprint-1",
            name="Sprint 1",
            goal="Complete feature X",
            planned_points=20)

        assert ctx is not None

    def test_end_sprint(self, tracker, exporter):
        """Ending a sprint should end span with stats."""
        sprint_tracker = SprintTracker(tracker)
        sprint_tracker.start_sprint(sprint_id="sprint-2", name="Sprint 2")
        sprint_tracker.end_sprint(sprint_id="sprint-2", completed_points=15)

        # Sprint should no longer be active
        assert "sprint-2" not in sprint_tracker._active_sprints


class TestStatePersistence:
    """Tests for state persistence."""

    def test_state_saved_on_task_start(self, temp_state_dir, exporter):
        """State should be saved when task starts."""
        tracker = TaskTracker(
            project="persist-test",
            state_dir=temp_state_dir,
            exporter=exporter)

        tracker.start_task(task_id="PERSIST-1", title="Persist test")

        # Check state file exists
        state_file = os.path.join(temp_state_dir, "persist-test", "PERSIST-1.json")
        assert os.path.exists(state_file)

    def test_state_removed_on_complete(self, temp_state_dir, exporter):
        """State should be moved to completed on task complete."""
        tracker = TaskTracker(
            project="persist-test",
            state_dir=temp_state_dir,
            exporter=exporter)

        tracker.start_task(task_id="PERSIST-2", title="Complete test")
        tracker.complete_task("PERSIST-2")

        # Active state file should be gone
        active_file = os.path.join(temp_state_dir, "persist-test", "PERSIST-2.json")
        assert not os.path.exists(active_file)

        # Should be in completed
        completed_file = os.path.join(
            temp_state_dir, "persist-test", "completed", "PERSIST-2.json"
        )
        assert os.path.exists(completed_file)


class TestTaskLinks:
    """Tests for task linking."""

    def test_get_task_link_returns_link(self, tracker, exporter):
        """Should return Link object for active task."""
        tracker.start_task(task_id="LINK-1", title="Link source")
        link = tracker.get_task_link("LINK-1")

        assert link is not None
        assert link.attributes["link.type"] == "implements_task"

    def test_get_task_link_none_for_missing(self, tracker, exporter):
        """Should return None for non-existent task."""
        link = tracker.get_task_link("NONEXISTENT")
        assert link is None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_update_nonexistent_task(self, tracker, exporter):
        """Updating non-existent task should not crash."""
        # Should log warning but not raise
        tracker.update_status("MISSING", "done")

    def test_complete_nonexistent_task(self, tracker, exporter):
        """Completing non-existent task should not crash."""
        tracker.complete_task("MISSING")

    def test_empty_title_allowed(self, tracker, exporter):
        """Empty title should be allowed."""
        tracker.start_task(task_id="EMPTY-TITLE", title="")
        assert "EMPTY-TITLE" in tracker.get_active_tasks()
