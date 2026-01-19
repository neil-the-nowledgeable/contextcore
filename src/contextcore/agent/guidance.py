"""
Human-to-Agent Guidance

Read human direction from ProjectContext CRD and respond to questions.
Guidance persists across agent sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from kubernetes import client, config

from contextcore.agent.insights import Evidence, InsightEmitter, InsightType, InsightAudience


class ConstraintSeverity(str, Enum):
    """How strictly a constraint must be followed."""
    BLOCKING = "blocking"
    WARNING = "warning"
    ADVISORY = "advisory"


class QuestionPriority(str, Enum):
    """Priority of a question."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class QuestionStatus(str, Enum):
    """Current state of a question."""
    OPEN = "open"
    ANSWERED = "answered"
    DEFERRED = "deferred"


@dataclass
class Focus:
    """Current priority focus areas."""
    areas: list[str]
    reason: str | None = None
    until: datetime | None = None


@dataclass
class Constraint:
    """What agents must NOT do."""
    id: str
    rule: str
    scope: str | None = None
    severity: ConstraintSeverity = ConstraintSeverity.BLOCKING
    reason: str | None = None


@dataclass
class Preference:
    """Preferred approach (not mandatory)."""
    id: str
    preference: str
    reason: str | None = None


@dataclass
class Question:
    """Question for agents to answer."""
    id: str
    question: str
    priority: QuestionPriority = QuestionPriority.NORMAL
    context: str | None = None
    status: QuestionStatus = QuestionStatus.OPEN


@dataclass
class Context:
    """Background information for agents."""
    topic: str
    content: str
    source: str | None = None


@dataclass
class AgentGuidance:
    """Complete human-to-agent guidance."""
    focus: Focus | None = None
    constraints: list[Constraint] = field(default_factory=list)
    preferences: list[Preference] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    context: list[Context] = field(default_factory=list)


class GuidanceReader:
    """
    Read human guidance from ProjectContext.

    Enables agents to understand human direction that persists
    across sessions.

    Example:
        reader = GuidanceReader(project_id="checkout-service")

        # Get focus areas
        focus = reader.get_focus()
        print(f"Focus: {focus.areas}")

        # Check constraints before action
        path = "src/api/checkout.py"
        constraints = reader.get_constraints_for_path(path)
        for c in constraints:
            if c.severity == ConstraintSeverity.BLOCKING:
                print(f"BLOCKED: {c.rule}")

        # Get open questions
        questions = reader.get_open_questions()
        for q in questions:
            if q.priority == QuestionPriority.CRITICAL:
                print(f"CRITICAL: {q.question}")
    """

    def __init__(
        self,
        project_id: str,
        namespace: str = "default",
        kubeconfig: str | None = None,
    ):
        self.project_id = project_id
        self.namespace = namespace

        # Initialize K8s client
        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig)
        else:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()

        self.custom_api = client.CustomObjectsApi()
        self._cache: AgentGuidance | None = None
        self._cache_time: datetime | None = None

    def _get_context(self) -> dict[str, Any]:
        """Get ProjectContext from K8s."""
        return self.custom_api.get_namespaced_custom_object(
            group="contextcore.io",
            version="v2",
            namespace=self.namespace,
            plural="projectcontexts",
            name=self.project_id,
        )

    def get_guidance(self, refresh: bool = False) -> AgentGuidance:
        """
        Get complete guidance (with caching).

        Args:
            refresh: Force refresh from K8s

        Returns:
            AgentGuidance with all sections
        """
        if self._cache is not None and not refresh:
            return self._cache

        context = self._get_context()
        guidance_data = context.get("spec", {}).get("agentGuidance", {})

        # Parse focus
        focus = None
        if focus_data := guidance_data.get("focus"):
            focus = Focus(
                areas=focus_data.get("areas", []),
                reason=focus_data.get("reason"),
                until=datetime.fromisoformat(focus_data["until"]) if focus_data.get("until") else None,
            )

        # Parse constraints
        constraints = [
            Constraint(
                id=c["id"],
                rule=c["rule"],
                scope=c.get("scope"),
                severity=ConstraintSeverity(c.get("severity", "blocking")),
                reason=c.get("reason"),
            )
            for c in guidance_data.get("constraints", [])
        ]

        # Parse preferences
        preferences = [
            Preference(
                id=p["id"],
                preference=p["preference"],
                reason=p.get("reason"),
            )
            for p in guidance_data.get("preferences", [])
        ]

        # Parse questions
        questions = [
            Question(
                id=q["id"],
                question=q["question"],
                priority=QuestionPriority(q.get("priority", "normal")),
                context=q.get("context"),
                status=QuestionStatus(q.get("status", "open")),
            )
            for q in guidance_data.get("questions", [])
        ]

        # Parse context
        context_items = [
            Context(
                topic=c["topic"],
                content=c["content"],
                source=c.get("source"),
            )
            for c in guidance_data.get("context", [])
        ]

        self._cache = AgentGuidance(
            focus=focus,
            constraints=constraints,
            preferences=preferences,
            questions=questions,
            context=context_items,
        )
        self._cache_time = datetime.now()

        return self._cache

    def get_focus(self) -> Focus | None:
        """Get current focus areas."""
        return self.get_guidance().focus

    def get_constraints(self) -> list[Constraint]:
        """Get all constraints."""
        return self.get_guidance().constraints

    def get_constraints_for_path(self, path: str) -> list[Constraint]:
        """
        Get constraints that apply to a specific path.

        Args:
            path: File or directory path

        Returns:
            Constraints with matching scope patterns
        """
        import fnmatch

        constraints = []
        for c in self.get_constraints():
            if c.scope is None:
                # No scope means applies everywhere
                constraints.append(c)
            elif fnmatch.fnmatch(path, c.scope):
                constraints.append(c)

        return constraints

    def check_blocking_constraints(self, path: str) -> list[Constraint]:
        """Get blocking constraints for a path."""
        return [
            c for c in self.get_constraints_for_path(path)
            if c.severity == ConstraintSeverity.BLOCKING
        ]

    def get_preferences(self) -> list[Preference]:
        """Get all preferences."""
        return self.get_guidance().preferences

    def get_questions(self) -> list[Question]:
        """Get all questions."""
        return self.get_guidance().questions

    def get_open_questions(self) -> list[Question]:
        """Get open (unanswered) questions."""
        return [q for q in self.get_questions() if q.status == QuestionStatus.OPEN]

    def get_critical_questions(self) -> list[Question]:
        """Get critical priority open questions."""
        return [
            q for q in self.get_open_questions()
            if q.priority == QuestionPriority.CRITICAL
        ]

    def get_context(self, topic: str | None = None) -> list[Context]:
        """
        Get context items, optionally filtered by topic.

        Args:
            topic: Filter by topic (case-insensitive contains)

        Returns:
            Matching context items
        """
        contexts = self.get_guidance().context
        if topic is None:
            return contexts

        topic_lower = topic.lower()
        return [c for c in contexts if topic_lower in c.topic.lower()]


class GuidanceResponder:
    """
    Respond to guidance questions.

    When answering a question, also emits an insight span for
    persistence and queryability.

    Example:
        responder = GuidanceResponder(
            project_id="checkout-service",
            agent_id="claude-code"
        )

        responder.answer_question(
            question_id="q-latency-cause",
            answer="Root cause is N+1 database query in payment verification",
            confidence=0.95,
            evidence=[
                Evidence(type="trace", ref="trace-abc123"),
                Evidence(type="log_query", ref='{app="checkout"} |= "query_time"')
            ]
        )
    """

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        session_id: str | None = None,
        namespace: str = "default",
        kubeconfig: str | None = None,
    ):
        self.project_id = project_id
        self.agent_id = agent_id
        self.session_id = session_id
        self.namespace = namespace

        # Initialize K8s client
        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig)
        else:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()

        self.custom_api = client.CustomObjectsApi()

        # Initialize insight emitter for recording answers
        self.emitter = InsightEmitter(
            project_id=project_id,
            agent_id=agent_id,
            session_id=session_id,
        )

    def answer_question(
        self,
        question_id: str,
        answer: str,
        confidence: float,
        evidence: list[Evidence] | None = None,
    ):
        """
        Answer a guidance question.

        Updates the question status in ProjectContext and emits
        an insight span with the answer.

        Args:
            question_id: ID of the question being answered
            answer: The answer text
            confidence: Confidence in the answer (0.0-1.0)
            evidence: Supporting evidence
        """
        # Get current context
        context = self.custom_api.get_namespaced_custom_object(
            group="contextcore.io",
            version="v2",
            namespace=self.namespace,
            plural="projectcontexts",
            name=self.project_id,
        )

        # Find and update question
        guidance = context.get("spec", {}).get("agentGuidance", {})
        questions = guidance.get("questions", [])

        question_text = None
        for q in questions:
            if q.get("id") == question_id:
                q["status"] = "answered"
                question_text = q.get("question")
                break

        if question_text is None:
            raise ValueError(f"Question {question_id} not found")

        # Update ProjectContext
        patch = {"spec": {"agentGuidance": {"questions": questions}}}
        self.custom_api.patch_namespaced_custom_object(
            group="contextcore.io",
            version="v2",
            namespace=self.namespace,
            plural="projectcontexts",
            name=self.project_id,
            body=patch,
        )

        # Emit insight with the answer
        self.emitter.emit(
            insight_type=InsightType.ANALYSIS,
            summary=f"Answer to: {question_text}",
            confidence=confidence,
            audience=InsightAudience.BOTH,
            rationale=answer,
            evidence=evidence or [],
        )
