"""
Tests for FailsafeSpanExporter — file-based retry on export failure.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from contextcore.export_retry import FailsafeSpanExporter, _serialize_span


class FailingExporter(SpanExporter):
    """Exporter that fails a configurable number of times then succeeds."""

    def __init__(self, fail_count: int = 0):
        self._fail_count = fail_count
        self._call_count = 0
        self.exported_batches: list = []
        self._shutdown = False

    def export(self, spans):
        self._call_count += 1
        if self._call_count <= self._fail_count:
            return SpanExportResult.FAILURE
        self.exported_batches.append(list(spans))
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis=30000):
        return True

    def shutdown(self):
        self._shutdown = True


class AlwaysFailExporter(SpanExporter):
    """Exporter that always fails."""

    def export(self, spans):
        return SpanExportResult.FAILURE

    def force_flush(self, timeout_millis=30000):
        return True

    def shutdown(self):
        pass


class RaisingExporter(SpanExporter):
    """Exporter that raises exceptions."""

    def export(self, spans):
        raise ConnectionError("endpoint unreachable")

    def force_flush(self, timeout_millis=30000):
        return True

    def shutdown(self):
        pass


def _make_mock_span(name: str = "test.span") -> MagicMock:
    """Create a minimal mock ReadableSpan."""
    span = MagicMock(spec=ReadableSpan)
    ctx = MagicMock()
    ctx.trace_id = 0x1234567890ABCDEF1234567890ABCDEF
    ctx.span_id = 0xFEDCBA0987654321
    span.get_span_context.return_value = ctx
    span.name = name
    span.start_time = 1000000000
    span.end_time = 2000000000
    span.parent = None
    span.kind = MagicMock()
    span.kind.name = "INTERNAL"
    span.attributes = {"task.id": "TEST-1", "task.type": "story"}
    span.events = []
    span.status = MagicMock()
    span.status.status_code = MagicMock()
    span.status.status_code.name = "OK"
    span.status.description = None
    return span


@pytest.fixture
def retry_dir():
    """Create a temporary retry directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestExportSuccess:
    """Tests for when the delegate succeeds."""

    def test_success_delegates_directly(self, retry_dir):
        """Successful export should pass through to delegate."""
        delegate = FailingExporter(fail_count=0)
        failsafe = FailsafeSpanExporter(delegate, retry_dir=retry_dir)

        spans = [_make_mock_span()]
        result = failsafe.export(spans)

        assert result == SpanExportResult.SUCCESS
        assert len(delegate.exported_batches) == 1
        # No retry files created
        assert len(list(retry_dir.glob("*.json"))) == 0

    def test_success_always_returned(self, retry_dir):
        """FailsafeSpanExporter always returns SUCCESS."""
        delegate = AlwaysFailExporter()
        failsafe = FailsafeSpanExporter(delegate, retry_dir=retry_dir)

        result = failsafe.export([_make_mock_span()])
        assert result == SpanExportResult.SUCCESS


class TestExportFailure:
    """Tests for when the delegate fails."""

    def test_failure_persists_to_file(self, retry_dir):
        """Failed export should persist spans to a retry file."""
        delegate = AlwaysFailExporter()
        failsafe = FailsafeSpanExporter(delegate, retry_dir=retry_dir)

        failsafe.export([_make_mock_span("span.1")])

        retry_files = list(retry_dir.glob("*.json"))
        assert len(retry_files) == 1

        with open(retry_files[0]) as f:
            data = json.load(f)
        assert data["attempts"] == 1
        assert len(data["spans"]) == 1
        assert data["spans"][0]["name"] == "span.1"

    def test_exception_persists_to_file(self, retry_dir):
        """Exporter raising exception should also persist spans."""
        delegate = RaisingExporter()
        failsafe = FailsafeSpanExporter(delegate, retry_dir=retry_dir)

        result = failsafe.export([_make_mock_span()])
        assert result == SpanExportResult.SUCCESS
        assert len(list(retry_dir.glob("*.json"))) == 1

    def test_multiple_failures_create_multiple_files(self, retry_dir):
        """Each failed batch creates its own retry file."""
        delegate = AlwaysFailExporter()
        failsafe = FailsafeSpanExporter(delegate, retry_dir=retry_dir)

        failsafe.export([_make_mock_span("batch1")])
        failsafe.export([_make_mock_span("batch2")])

        assert len(list(retry_dir.glob("*.json"))) == 2


class TestDrainPending:
    """Tests for draining retry files on success."""

    def test_success_drains_pending(self, retry_dir):
        """Successful export should drain pending retry files."""
        # First: fail to create retry file
        delegate = FailingExporter(fail_count=1)
        failsafe = FailsafeSpanExporter(delegate, retry_dir=retry_dir)

        failsafe.export([_make_mock_span("failed")])
        assert len(list(retry_dir.glob("*.json"))) == 1

        # Second: succeed, which should drain the retry file
        failsafe.export([_make_mock_span("success")])
        assert len(list(retry_dir.glob("*.json"))) == 0


class TestMaxAttempts:
    """Tests for dead-lettering after max attempts."""

    def test_exceeds_max_attempts_dead_letters(self, retry_dir):
        """Files exceeding max attempts should be moved to dead/ dir."""
        delegate = AlwaysFailExporter()
        failsafe = FailsafeSpanExporter(
            delegate, retry_dir=retry_dir, max_attempts=2
        )

        # Create a retry file manually with attempts=1
        retry_file = retry_dir / "test_retry.json"
        with open(retry_file, "w") as f:
            json.dump({"attempts": 1, "created_at": 0, "spans": []}, f)

        # Drain should increment to 2 and dead-letter
        failsafe._drain_pending(10)

        dead_dir = retry_dir / "dead"
        assert dead_dir.exists()
        assert len(list(dead_dir.glob("*.json"))) == 1
        assert not retry_file.exists()


class TestMaxFiles:
    """Tests for file cap preventing disk exhaustion."""

    def test_max_files_cap(self, retry_dir):
        """Should drop spans when max_files is exceeded."""
        delegate = AlwaysFailExporter()
        failsafe = FailsafeSpanExporter(
            delegate, retry_dir=retry_dir, max_files=2
        )

        failsafe.export([_make_mock_span("batch1")])
        failsafe.export([_make_mock_span("batch2")])
        failsafe.export([_make_mock_span("batch3")])  # Should be dropped

        assert len(list(retry_dir.glob("*.json"))) == 2


class TestForceFlush:
    """Tests for force_flush behavior."""

    def test_force_flush_drains_all(self, retry_dir):
        """force_flush should drain all pending files, not just a batch."""
        delegate = FailingExporter(fail_count=3)
        failsafe = FailsafeSpanExporter(
            delegate, retry_dir=retry_dir, drain_batch=1
        )

        # Create 3 retry files
        failsafe.export([_make_mock_span("a")])
        failsafe.export([_make_mock_span("b")])
        failsafe.export([_make_mock_span("c")])
        assert len(list(retry_dir.glob("*.json"))) == 3

        # force_flush should drain all of them
        failsafe.force_flush()
        assert len(list(retry_dir.glob("*.json"))) == 0


class TestShutdown:
    """Tests for shutdown behavior."""

    def test_shutdown_delegates(self, retry_dir):
        """Shutdown should call delegate's shutdown."""
        delegate = FailingExporter()
        failsafe = FailsafeSpanExporter(delegate, retry_dir=retry_dir)

        failsafe.shutdown()
        assert delegate._shutdown is True


class TestSerializeSpan:
    """Tests for span serialization."""

    def test_serialize_basic_span(self):
        """Should serialize span fields to JSON-safe dict."""
        span = _make_mock_span("test.serialize")
        data = _serialize_span(span)

        assert data["name"] == "test.serialize"
        assert data["trace_id"] == "1234567890abcdef1234567890abcdef"
        assert data["span_id"] == "fedcba0987654321"
        assert data["attributes"]["task.id"] == "TEST-1"
        assert data["kind"] == "INTERNAL"
