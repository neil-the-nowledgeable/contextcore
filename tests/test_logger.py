"""
Tests for TaskLogger - structured logging for Loki.
"""

import json
import pytest
from io import StringIO
from unittest.mock import patch

from contextcore.logger import TaskLogger


@pytest.fixture
def captured_logs():
    """Capture log output for testing."""
    output = StringIO()
    return output


@pytest.fixture
def logger(captured_logs):
    """Create a TaskLogger that writes to captured output."""
    logger = TaskLogger(
        project="test-project",
        service_name="test-service",
    )
    # Redirect the internal logger's handler
    import logging
    loki_logger = logging.getLogger("contextcore.tasks")

    # Clear existing handlers and add our test handler
    loki_logger.handlers.clear()
    handler = logging.StreamHandler(captured_logs)
    handler.setFormatter(logging.Formatter("%(message)s"))
    loki_logger.addHandler(handler)

    return logger


def parse_log_line(captured_logs) -> dict:
    """Parse the last JSON log line."""
    captured_logs.seek(0)
    lines = captured_logs.read().strip().split("\n")
    if lines and lines[-1]:
        return json.loads(lines[-1])
    return {}


class TestTaskCreatedLogs:
    """Tests for task.created event logging."""

    def test_log_task_created_basic(self, logger, captured_logs):
        """Basic task creation should log required fields."""
        logger.log_task_created(
            task_id="TASK-1",
            title="Test task",
        )

        log = parse_log_line(captured_logs)
        assert log["event"] == "task.created"
        assert log["task_id"] == "TASK-1"
        assert log["task_title"] == "Test task"
        assert log["project_id"] == "test-project"
        assert log["service"] == "test-service"

    def test_log_task_created_full(self, logger, captured_logs):
        """Full task creation should include all fields."""
        logger.log_task_created(
            task_id="TASK-2",
            title="Full test",
            task_type="story",
            priority="high",
            assignee="alice",
            story_points=5,
            sprint_id="sprint-1",
            parent_id="EPIC-1",
            actor="bob",
        )

        log = parse_log_line(captured_logs)
        assert log["event"] == "task.created"
        assert log["task_type"] == "story"
        assert log["priority"] == "high"
        assert log["assignee"] == "alice"
        assert log["story_points"] == 5
        assert log["sprint_id"] == "sprint-1"
        assert log["parent_id"] == "EPIC-1"
        assert log["actor"] == "bob"


class TestStatusChangeLogs:
    """Tests for task.status_changed event logging."""

    def test_log_status_changed(self, logger, captured_logs):
        """Status change should log transition."""
        logger.log_status_changed(
            task_id="TASK-3",
            from_status="todo",
            to_status="in_progress",
        )

        log = parse_log_line(captured_logs)
        assert log["event"] == "task.status_changed"
        assert log["from_status"] == "todo"
        assert log["to_status"] == "in_progress"

    def test_log_status_changed_with_actor(self, logger, captured_logs):
        """Status change with actor should include actor info."""
        logger.log_status_changed(
            task_id="TASK-4",
            from_status="in_progress",
            to_status="done",
            actor="alice",
            trigger="webhook",
        )

        log = parse_log_line(captured_logs)
        assert log["actor"] == "alice"
        assert log["trigger"] == "webhook"


class TestBlockedLogs:
    """Tests for task.blocked event logging."""

    def test_log_blocked(self, logger, captured_logs):
        """Blocked event should log reason."""
        logger.log_blocked(
            task_id="TASK-5",
            reason="Waiting on API",
        )

        log = parse_log_line(captured_logs)
        assert log["event"] == "task.blocked"
        assert log["reason"] == "Waiting on API"
        assert log["level"] == "warn"

    def test_log_blocked_with_blocker(self, logger, captured_logs):
        """Blocked by another task should include blocker ID."""
        logger.log_blocked(
            task_id="TASK-6",
            reason="Dependency not ready",
            blocked_by="TASK-5",
        )

        log = parse_log_line(captured_logs)
        assert log["blocked_by"] == "TASK-5"


class TestUnblockedLogs:
    """Tests for task.unblocked event logging."""

    def test_log_unblocked(self, logger, captured_logs):
        """Unblocked event should be logged."""
        logger.log_unblocked(task_id="TASK-7")

        log = parse_log_line(captured_logs)
        assert log["event"] == "task.unblocked"

    def test_log_unblocked_with_duration(self, logger, captured_logs):
        """Unblocked with duration should include timing."""
        logger.log_unblocked(
            task_id="TASK-8",
            resolution="Dependency deployed",
            blocked_duration_seconds=3600.0,
        )

        log = parse_log_line(captured_logs)
        assert log["resolution"] == "Dependency deployed"
        assert log["blocked_duration_seconds"] == 3600.0


class TestCompletionLogs:
    """Tests for task.completed event logging."""

    def test_log_completed(self, logger, captured_logs):
        """Completed event should be logged."""
        logger.log_completed(task_id="TASK-9")

        log = parse_log_line(captured_logs)
        assert log["event"] == "task.completed"

    def test_log_completed_with_metrics(self, logger, captured_logs):
        """Completed with metrics should include timing."""
        logger.log_completed(
            task_id="TASK-10",
            task_type="story",
            story_points=5,
            lead_time_seconds=86400.0,
            cycle_time_seconds=28800.0,
        )

        log = parse_log_line(captured_logs)
        assert log["story_points"] == 5
        assert log["lead_time_seconds"] == 86400.0
        assert log["cycle_time_seconds"] == 28800.0


class TestCancelledLogs:
    """Tests for task.cancelled event logging."""

    def test_log_cancelled(self, logger, captured_logs):
        """Cancelled event should be logged."""
        logger.log_cancelled(task_id="TASK-11")

        log = parse_log_line(captured_logs)
        assert log["event"] == "task.cancelled"

    def test_log_cancelled_with_reason(self, logger, captured_logs):
        """Cancelled with reason should include it."""
        logger.log_cancelled(
            task_id="TASK-12",
            reason="Scope changed",
        )

        log = parse_log_line(captured_logs)
        assert log["reason"] == "Scope changed"


class TestProgressLogs:
    """Tests for task.progress_updated event logging."""

    def test_log_progress_updated(self, logger, captured_logs):
        """Progress update should be logged."""
        logger.log_progress_updated(
            task_id="TASK-13",
            percent_complete=50.0,
        )

        log = parse_log_line(captured_logs)
        assert log["event"] == "task.progress_updated"
        assert log["percent_complete"] == 50.0

    def test_log_progress_with_subtasks(self, logger, captured_logs):
        """Progress from subtasks should include counts."""
        logger.log_progress_updated(
            task_id="TASK-14",
            percent_complete=66.67,
            source="subtask",
            subtask_completed=2,
            subtask_count=3,
        )

        log = parse_log_line(captured_logs)
        assert log["source"] == "subtask"
        assert log["subtask_completed"] == 2
        assert log["subtask_count"] == 3


class TestSprintLogs:
    """Tests for sprint event logging."""

    def test_log_sprint_started(self, logger, captured_logs):
        """Sprint start should be logged."""
        logger.log_sprint_started(
            sprint_id="sprint-1",
            name="Sprint 1",
            goal="Complete feature X",
            planned_points=20,
            start_date="2026-01-15",
            end_date="2026-01-29",
        )

        log = parse_log_line(captured_logs)
        assert log["event"] == "sprint.started"
        assert log["sprint_name"] == "Sprint 1"
        assert log["goal"] == "Complete feature X"
        assert log["planned_points"] == 20

    def test_log_sprint_ended(self, logger, captured_logs):
        """Sprint end should be logged."""
        logger.log_sprint_ended(
            sprint_id="sprint-1",
            name="Sprint 1",
            planned_points=20,
            completed_points=18,
            percent_complete=90.0,
        )

        log = parse_log_line(captured_logs)
        assert log["event"] == "sprint.ended"
        assert log["completed_points"] == 18
        assert log["percent_complete"] == 90.0


class TestLogFormat:
    """Tests for log formatting."""

    def test_log_is_valid_json(self, logger, captured_logs):
        """All logs should be valid JSON."""
        logger.log_task_created(task_id="JSON-1", title="JSON test")

        captured_logs.seek(0)
        line = captured_logs.read().strip()
        # Should not raise
        parsed = json.loads(line)
        assert isinstance(parsed, dict)

    def test_log_includes_timestamp(self, logger, captured_logs):
        """Logs should include timestamp."""
        logger.log_task_created(task_id="TS-1", title="Timestamp test")

        log = parse_log_line(captured_logs)
        assert "timestamp" in log
        # Should be ISO format
        assert "T" in log["timestamp"]

    def test_extra_labels_included(self):
        """Extra labels should be included in output."""
        output = StringIO()
        import logging
        loki_logger = logging.getLogger("contextcore.tasks")
        loki_logger.handlers.clear()
        handler = logging.StreamHandler(output)
        handler.setFormatter(logging.Formatter("%(message)s"))
        loki_logger.addHandler(handler)

        logger = TaskLogger(
            project="label-test",
            extra_labels={"environment": "staging", "team": "platform"},
        )
        logger.log_task_created(task_id="LABEL-1", title="Label test")

        output.seek(0)
        log = json.loads(output.read().strip())
        assert log["labels"]["environment"] == "staging"
        assert log["labels"]["team"] == "platform"
