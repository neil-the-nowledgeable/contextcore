"""
Export task emitter — creates OTel task spans for artifact coverage gaps.

When ``--emit-tasks`` is passed to ``contextcore manifest export``, this module
emits an epic → story → task span hierarchy representing the work to be done.

The trace ID of the epic span is recorded in ``onboarding-metadata.json`` as
``task_trace_id`` so downstream systems (plan ingestion, artisan) can correlate.

Usage::

    from contextcore.cli.export_task_emitter import emit_export_tasks

    result = emit_export_tasks(
        artifact_manifest=artifact_manifest,
        onboarding_metadata=onboarding_metadata,
        project_id="my-project",
    )
    # result["task_trace_id"] is the trace ID to record in onboarding metadata

See ``docs/plans/EXPORT_TASK_TRACKING_REQUIREMENTS.md`` for full requirements.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskEmissionResult:
    """Result of emitting task spans for export coverage gaps."""

    task_trace_id: Optional[str] = None
    epic_span_id: Optional[str] = None
    total_tasks_emitted: int = 0
    stories_emitted: int = 0
    tasks_by_status: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    dry_run: bool = False


def emit_export_tasks(
    artifact_manifest: Any,
    onboarding_metadata: Dict[str, Any],
    project_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    dry_run: bool = False,
) -> TaskEmissionResult:
    """
    Emit OTel task spans for each artifact in coverage gaps.

    Creates an epic → story (by artifact type) → task hierarchy.
    Records ``task_trace_id`` in the onboarding metadata dict.

    Args:
        artifact_manifest: The ``ArtifactManifest`` from export.
        onboarding_metadata: Mutable dict; ``task_trace_id`` and
            ``task_emission_timestamp`` are added in-place.
        project_id: Override project ID (defaults to manifest metadata).
        endpoint: OTLP endpoint override (defaults to env var).
        dry_run: If True, compute the plan but don't emit spans.

    Returns:
        TaskEmissionResult with trace ID and statistics.
    """
    result = TaskEmissionResult(dry_run=dry_run)

    # Resolve project ID
    pid = project_id
    if not pid:
        try:
            pid = artifact_manifest.metadata.project_id
        except AttributeError:
            pid = onboarding_metadata.get("project_id", "unknown")

    # Group artifacts by type
    artifacts_by_type: Dict[str, list] = defaultdict(list)
    for artifact in artifact_manifest.artifacts:
        artifacts_by_type[artifact.type.value if hasattr(artifact.type, "value") else str(artifact.type)].append(artifact)

    # Compute coverage stats
    total_required = len(artifact_manifest.artifacts)
    total_gaps = sum(
        1 for a in artifact_manifest.artifacts
        if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "needed"
    )
    total_existing = total_required - total_gaps
    coverage_percent = (total_existing / total_required * 100) if total_required > 0 else 100.0

    if dry_run:
        # Compute plan without emitting
        result.total_tasks_emitted = total_required
        result.stories_emitted = len(artifacts_by_type)
        result.tasks_by_status = {
            "needed": total_gaps,
            "exists": total_existing,
        }
        result.task_trace_id = "(dry-run)"
        return result

    # --- Emit OTel spans ---
    try:
        from contextcore.tracker import TaskTracker

        tracker = TaskTracker(
            project=pid,
            service_name="contextcore-export",
        )

        # 1. Epic span
        epic_id = f"{pid}-artifact-generation"
        epic_ctx = tracker.start_task(
            task_id=epic_id,
            title=f"{pid} Observability Artifact Generation",
            task_type="epic",
            status="todo",
            **{
                "coverage.total_required": total_required,
                "coverage.total_existing": total_existing,
                "coverage.total_gaps": total_gaps,
                "coverage.percent": coverage_percent,
                "export.source": "contextcore.manifest.export",
            },
        )
        result.epic_span_id = format(epic_ctx.span_id, "016x")
        result.task_trace_id = format(epic_ctx.trace_id, "032x")

        # 2. Story spans (one per artifact type with gaps or existing)
        for art_type, arts in artifacts_by_type.items():
            gap_count = sum(
                1 for a in arts
                if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "needed"
            )
            story_id = f"{pid}-{art_type}-artifacts"
            tracker.start_task(
                task_id=story_id,
                title=f"{art_type.replace('_', ' ').title()} Artifacts ({len(arts)} total, {gap_count} needed)",
                task_type="story",
                parent_id=epic_id,
                status="todo" if gap_count > 0 else "done",
                **{
                    "artifact.type": art_type,
                    "artifact.gap_count": gap_count,
                    "artifact.total_count": len(arts),
                },
            )
            result.stories_emitted += 1

            # 3. Task spans (one per artifact)
            for artifact in arts:
                art_status = artifact.status.value if hasattr(artifact.status, "value") else str(artifact.status)
                task_status = "done" if art_status == "exists" else "todo"
                art_priority = artifact.priority.value if hasattr(artifact.priority, "value") else str(artifact.priority)

                depends = []
                if hasattr(artifact, "depends_on") and artifact.depends_on:
                    depends = list(artifact.depends_on)

                extra_attrs: Dict[str, Any] = {
                    "artifact.id": artifact.id,
                    "artifact.type": art_type,
                    "artifact.target": artifact.target,
                    "artifact.priority": art_priority,
                    "artifact.status": art_status,
                }
                # Add resolved parameters as attributes
                if hasattr(artifact, "parameters") and artifact.parameters:
                    for pk, pv in artifact.parameters.items():
                        if isinstance(pv, (str, int, float, bool)):
                            extra_attrs[f"artifact.parameters.{pk}"] = pv

                tracker.start_task(
                    task_id=artifact.id,
                    title=artifact.name,
                    task_type="task",
                    parent_id=story_id,
                    status=task_status,
                    priority=art_priority if art_priority in ("critical", "high", "medium", "low") else None,
                    depends_on=depends,
                    **extra_attrs,
                )

                # Add task.created event
                tracker.add_event(
                    artifact.id,
                    "task.created",
                    attributes={
                        "source": "contextcore.manifest.export",
                        "artifact_type": art_type,
                        "target": artifact.target,
                    },
                )

                # Add task.contract event with derivation rules
                if hasattr(artifact, "derived_from") and artifact.derived_from:
                    derivation_data = [
                        {
                            "property": d.property if hasattr(d, "property") else str(d),
                            "source_field": d.source_field if hasattr(d, "source_field") else "",
                            "transformation": d.transformation if hasattr(d, "transformation") else "",
                        }
                        for d in artifact.derived_from
                    ]
                    tracker.add_event(
                        artifact.id,
                        "task.contract",
                        attributes={
                            "derivation_rules": json.dumps(derivation_data),
                        },
                    )

                # Complete existing artifact tasks immediately
                if task_status == "done":
                    tracker.complete_task(artifact.id)

                result.total_tasks_emitted += 1
                result.tasks_by_status[art_status] = result.tasks_by_status.get(art_status, 0) + 1

            # Complete story if all tasks are done
            if gap_count == 0:
                tracker.complete_task(story_id)

        # If all stories are done, complete the epic
        if total_gaps == 0:
            tracker.complete_task(epic_id)

        # Force flush to ensure spans are exported
        tracker.shutdown()

    except Exception as e:
        logger.warning(f"Task emission failed (best-effort): {e}")
        result.errors.append(str(e))
        # Task emission failure does not fail the export (R7.2)
        return result

    # Record in onboarding metadata for downstream correlation (R4.3, R7.4)
    if result.task_trace_id:
        onboarding_metadata["task_trace_id"] = result.task_trace_id
        onboarding_metadata["task_emission_timestamp"] = datetime.now(timezone.utc).isoformat()

    return result
