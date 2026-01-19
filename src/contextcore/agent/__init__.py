"""
ContextCore Agent Communication SDK

Provides primitives for agent-to-agent, agent-to-human, and human-to-agent
communication using ContextCore's observability-native approach.

Supports two modes:
- Production: Emit/query via OTel to Tempo
- Development: Local JSON file storage (no infrastructure needed)

Quick Start:
    from contextcore.agent import InsightEmitter, InsightQuerier, GuidanceReader

    # Emit insights (with local fallback for development)
    emitter = InsightEmitter(
        project_id="my-project",
        agent_id="claude",
        local_storage_path="~/.contextcore/insights"  # Optional: for dev without Tempo
    )
    emitter.emit_decision("Selected async architecture", confidence=0.9)
    emitter.emit_lesson(
        summary="Always mock OTLP exporter in tests",
        category="testing",
        applies_to=["src/tracker.py"]
    )

    # Query insights from other agents/sessions
    querier = InsightQuerier(local_storage_path="~/.contextcore/insights")
    decisions = querier.query(project_id="my-project", insight_type="decision")
    lessons = querier.get_lessons(project_id="my-project", applies_to="tracker.py")

    # Read human guidance from K8s CRD
    reader = GuidanceReader(project_id="my-project")
    constraints = reader.get_constraints_for_path("src/api/")

CLI Usage:
    # Emit a lesson
    contextcore insight emit --type lesson \\
        --summary "Mock OTLP in tests" --category testing

    # Query lessons
    contextcore insight lessons --project my-project
"""

from contextcore.agent.insights import InsightEmitter, InsightQuerier
from contextcore.agent.handoff import HandoffManager, HandoffReceiver
from contextcore.agent.guidance import GuidanceReader, GuidanceResponder
from contextcore.agent.personalization import PersonalizedQuerier

__all__ = [
    "InsightEmitter",
    "InsightQuerier",
    "HandoffManager",
    "HandoffReceiver",
    "GuidanceReader",
    "GuidanceResponder",
    "PersonalizedQuerier",
]
