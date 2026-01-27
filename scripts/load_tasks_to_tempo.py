#!/usr/bin/env python3
"""
Load task JSON data into Tempo via OTLP.

Usage:
    python3 scripts/load_tasks_to_tempo.py plans/beaver-lead-contractor-tasks.json
    python3 scripts/load_tasks_to_tempo.py plans/dashboard-persistence-tasks.json
    python3 scripts/load_tasks_to_tempo.py --all  # Load all task files
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_task_file(filepath: str) -> Dict[str, Any]:
    """Load a task JSON file."""
    with open(filepath) as f:
        return json.load(f)


def create_spans_from_tasks(
    data: Dict[str, Any],
    tracer: trace.Tracer,
    base_time: Optional[datetime] = None,
) -> int:
    """
    Create spans from task data.

    Supports two formats:
    1. Simple task list: {"project": {...}, "tasks": [...]}
    2. Span format: {"project": {...}, "spans": [...]}
    """
    project = data.get("project", {})
    project_id = project.get("id", "unknown")

    if base_time is None:
        base_time = datetime.now(timezone.utc) - timedelta(days=7)

    spans_created = 0

    # Check for spans format (dashboard-persistence style)
    if "spans" in data:
        spans_data = data["spans"]
        span_map = {}  # Track spans by span_id for parent linking

        # Sort by span_id to ensure parents are created before children
        spans_data.sort(key=lambda x: x.get("span_id", ""))

        for i, span_data in enumerate(spans_data):
            attrs = span_data.get("attributes", {})
            task_id = attrs.get("task.id", f"task-{i}")
            task_type = attrs.get("task.type", "task")
            task_title = attrs.get("task.title", task_id)
            task_status = attrs.get("task.status", "backlog")

            # Calculate timing (spread tasks over the time range)
            start_offset = timedelta(hours=i * 2)
            duration = timedelta(hours=1) if task_status == "done" else timedelta(hours=4)

            start_time = base_time + start_offset
            end_time = start_time + duration if task_status == "done" else None

            # Build span attributes
            span_attrs = {
                "task.id": task_id,
                "task.type": task_type,
                "task.title": task_title,
                "task.status": task_status,
                "project.id": project_id,
            }

            # Add optional attributes
            if "task.story_points" in attrs:
                span_attrs["task.story_points"] = attrs["task.story_points"]
            if "task.description" in attrs:
                span_attrs["task.description"] = attrs["task.description"][:200]  # Truncate
            if "task.blocked_by" in attrs:
                span_attrs["task.blocked_by"] = json.dumps(attrs["task.blocked_by"])

            # Create span
            start_time_ns = int(start_time.timestamp() * 1e9)

            span = tracer.start_span(
                name=f"{task_type}:{task_id}",
                kind=SpanKind.INTERNAL,
                attributes=span_attrs,
                start_time=start_time_ns,
            )

            # Add creation event
            span.add_event("task.created", timestamp=start_time_ns)

            # Set status based on task status
            if task_status == "done":
                span.set_status(Status(StatusCode.OK))
            elif task_status == "blocked":
                span.set_status(Status(StatusCode.ERROR, "Task blocked"))

            # End span if completed
            if end_time:
                end_time_ns = int(end_time.timestamp() * 1e9)
                span.add_event("task.completed", timestamp=end_time_ns)
                span.end(end_time=end_time_ns)
            else:
                # Leave in-progress spans open for a bit then close
                span.end()

            spans_created += 1

    # Check for simple tasks format (beaver style)
    elif "tasks" in data:
        tasks = data["tasks"]

        for i, task in enumerate(tasks):
            task_id = task.get("id", f"task-{i}")
            task_type = task.get("type", "task")
            task_title = task.get("title", task_id)
            task_status = task.get("status", "backlog")

            # Calculate timing
            start_offset = timedelta(hours=i * 3)
            duration = timedelta(hours=2) if task_status == "done" else timedelta(hours=6)

            start_time = base_time + start_offset
            end_time = start_time + duration if task_status == "done" else None

            # Build span attributes
            span_attrs = {
                "task.id": task_id,
                "task.type": task_type,
                "task.title": task_title,
                "task.status": task_status,
                "project.id": project_id,
            }

            if "description" in task:
                span_attrs["task.description"] = task["description"][:200]
            if "story_points" in task:
                span_attrs["task.story_points"] = task["story_points"]

            # Create span
            start_time_ns = int(start_time.timestamp() * 1e9)

            span = tracer.start_span(
                name=f"{task_type}:{task_id}",
                kind=SpanKind.INTERNAL,
                attributes=span_attrs,
                start_time=start_time_ns,
            )

            span.add_event("task.created", timestamp=start_time_ns)

            if task_status == "done":
                span.set_status(Status(StatusCode.OK))

            if end_time:
                end_time_ns = int(end_time.timestamp() * 1e9)
                span.add_event("task.completed", timestamp=end_time_ns)
                span.end(end_time=end_time_ns)
            else:
                span.end()

            spans_created += 1

    return spans_created


def load_to_tempo(
    task_files: List[str],
    endpoint: str = "localhost:30317",
    insecure: bool = True,
) -> Dict[str, Any]:
    """
    Load task files into Tempo via OTLP.

    Args:
        task_files: List of task JSON file paths
        endpoint: OTLP gRPC endpoint
        insecure: Use insecure connection

    Returns:
        Statistics about the export
    """
    results = {
        "endpoint": endpoint,
        "files_processed": 0,
        "total_spans": 0,
        "errors": [],
    }

    for filepath in task_files:
        try:
            logger.info(f"Loading {filepath}...")
            data = load_task_file(filepath)

            project = data.get("project", {})
            project_id = project.get("id", Path(filepath).stem)
            project_name = project.get("name", project_id)

            # Create resource for this project
            resource = Resource.create({
                "service.name": "contextcore",
                "service.namespace": "contextcore",
                "project.id": project_id,
                "project.name": project_name,
            })

            # Create exporter and provider
            exporter = OTLPSpanExporter(
                endpoint=endpoint,
                insecure=insecure,
            )

            provider = TracerProvider(resource=resource)
            provider.add_span_processor(BatchSpanProcessor(exporter))

            tracer = provider.get_tracer("contextcore.task-loader")

            # Create spans from tasks
            spans_created = create_spans_from_tasks(data, tracer)

            # Flush and shutdown
            provider.force_flush()
            provider.shutdown()

            logger.info(f"  Created {spans_created} spans for project '{project_id}'")

            results["files_processed"] += 1
            results["total_spans"] += spans_created

        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
            results["errors"].append({"file": filepath, "error": str(e)})

    return results


def find_task_files(base_dir: str) -> List[str]:
    """Find all task JSON files in the project."""
    task_files = []

    # Check plans directory
    plans_dir = Path(base_dir) / "plans"
    if plans_dir.exists():
        for f in plans_dir.glob("*tasks*.json"):
            task_files.append(str(f))

    return task_files


def main():
    parser = argparse.ArgumentParser(description="Load task data into Tempo")
    parser.add_argument("files", nargs="*", help="Task JSON files to load")
    parser.add_argument("--all", action="store_true", help="Load all task files")
    parser.add_argument("--endpoint", default="localhost:30317", help="OTLP endpoint")
    parser.add_argument("--secure", action="store_true", help="Use secure connection")

    args = parser.parse_args()

    # Determine which files to load
    if args.all:
        base_dir = Path(__file__).parent.parent
        task_files = find_task_files(str(base_dir))
        if not task_files:
            logger.error("No task files found")
            sys.exit(1)
    elif args.files:
        task_files = args.files
    else:
        parser.print_help()
        sys.exit(1)

    logger.info(f"Loading {len(task_files)} task file(s) to {args.endpoint}")

    results = load_to_tempo(
        task_files=task_files,
        endpoint=args.endpoint,
        insecure=not args.secure,
    )

    print("\n" + "=" * 50)
    print("RESULTS")
    print("=" * 50)
    print(f"Endpoint: {results['endpoint']}")
    print(f"Files processed: {results['files_processed']}")
    print(f"Total spans created: {results['total_spans']}")

    if results["errors"]:
        print(f"Errors: {len(results['errors'])}")
        for err in results["errors"]:
            print(f"  - {err['file']}: {err['error']}")

    print("=" * 50)


if __name__ == "__main__":
    main()
