"""
Agent Learning Loop module for ContextCore.

This module provides a high-level integration class that manages the learning loop
workflow for agents. It simplifies retrieving relevant lessons before tasks and
emitting new lessons after task completion.
"""

from __future__ import annotations

from typing import Optional

from contextcore.learning.emitter import LessonEmitter
from contextcore.learning.retriever import LessonRetriever
from contextcore.learning.models import Lesson, LessonCategory, LessonSource

__all__ = ["LearningLoop"]


class LearningLoop:
    """
    A high-level integration class that manages the learning loop workflow for agents.

    This class provides simplified methods for retrieving relevant lessons before agent tasks
    and emitting new lessons after task completion.

    Example usage:
        from contextcore.learning import LearningLoop

        loop = LearningLoop(project_id="my-project", agent_id="claude-code")

        # Before starting work - get relevant lessons
        lessons = loop.before_task(task_type="testing", files=["src/auth/oauth.py"])
        for lesson in lessons:
            print(f"Tip: {lesson.summary}")

        # After work - emit lessons learned
        loop.after_task_blocker(
            blocker="OAuth token refresh failed in tests",
            resolution="Mock the token refresh endpoint in conftest.py",
            affected_files=["tests/conftest.py", "src/auth/oauth.py"]
        )
    """

    def __init__(self, project_id: str, agent_id: str, tempo_url: str = "http://localhost:3200"):
        """
        Initialize the learning loop.

        Args:
            project_id: Unique identifier for the project
            agent_id: Unique identifier for the agent
            tempo_url: Optional Tempo URL for retriever (default: http://localhost:3200)
        """
        self.project_id = project_id
        self.agent_id = agent_id
        self.emitter = LessonEmitter(project_id=project_id, agent_id=agent_id)
        self.retriever = LessonRetriever(tempo_url=tempo_url)

    def before_task(self, task_type: str, files: Optional[list[str]] = None) -> list[Lesson]:
        """
        Retrieve relevant lessons before starting a task.

        Args:
            task_type: Type of task (e.g., "testing", "debugging", "implementation", "refactoring")
            files: Optional list of file paths relevant to the task

        Returns:
            List of relevant lessons for the task
        """
        lessons = []

        # Get lessons for the task type
        task_lessons = self.retriever.get_lessons_for_task(task_type, self.project_id)
        lessons.extend(task_lessons)

        # Get lessons for specific files if provided
        if files:
            for file_path in files:
                file_lessons = self.retriever.get_lessons_for_file(file_path, self.project_id)
                lessons.extend(file_lessons)

        # Deduplicate by lesson ID and sort by effectiveness
        seen_ids = set()
        unique_lessons = []
        for lesson in lessons:
            if lesson.id not in seen_ids:
                seen_ids.add(lesson.id)
                unique_lessons.append(lesson)

        # Sort by effectiveness score descending
        unique_lessons.sort(key=lambda x: x.effectiveness_score, reverse=True)
        return unique_lessons

    def after_task_blocker(
        self,
        blocker: str,
        resolution: str,
        affected_files: Optional[list[str]] = None
    ) -> None:
        """
        Emit a lesson learned from resolving a blocker.

        Args:
            blocker: Description of the blocker that was encountered
            resolution: How the blocker was resolved
            affected_files: Optional list of files affected by this blocker resolution
        """
        applies_to = affected_files or []

        self.emitter.emit_lesson(
            summary=blocker,
            category=LessonCategory.ERROR_HANDLING,
            source=LessonSource.ERROR_FIXED,
            applies_to=applies_to,
            confidence=0.9,
            context=resolution,
            code_example=None,
            anti_pattern=None,
            global_lesson=False
        )
