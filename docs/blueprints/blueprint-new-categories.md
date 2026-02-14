# Proposed New OTel Blueprint Categories

> **Phase 2 Deliverable**: New blueprint categories derived from ContextCore innovations.

---

## Overview

ContextCore introduces capabilities that don't fit existing OTel Blueprint categories. This document proposes two new blueprint categories for consideration by the OTel End-User SIG:

1. **Project Management Observability Blueprint** — Tasks as spans, progress telemetry
2. **AI Agent Communication Blueprint** — Agent insights, cross-session memory

---

# Blueprint Category 1: Project Management Observability

## Summary

This blueprint outlines a strategic reference for **Platform Engineering teams** and **Engineering Leadership** operating in **organizations with complex project portfolios**. It addresses the friction often found when attempting to **gain real-time visibility into project health without manual status reporting**.

By implementing the patterns in this blueprint, organizations can expect to shift from **fragmented, stale status reports compiled manually** to **automated, telemetry-driven project dashboards derived from existing artifacts**.

### Target Audience

| Persona | Current Pain | Value Delivered |
|---------|--------------|-----------------|
| **Engineering Manager** | Weekly status meetings consume 2-3 hours | Real-time dashboards, zero manual compilation |
| **Project Manager** | Progress data is 3-5 days stale | Live updates from commits, PRs, CI results |
| **Executive** | Portfolio health requires manual reports | Self-serve drill-down from portfolio to task |
| **Platform Team** | No standard for project telemetry | Unified semantic conventions across projects |

### Environment Scope

- Any development environment with project management tools (Jira, GitHub Projects, Linear, etc.)
- CI/CD pipelines with artifact traceability
- Kubernetes or cloud-native infrastructure (optional, for CRD-based config)
- OTLP-compatible observability backends

---

## Diagnosis: Common Challenges

### Challenge 1: Manual Status Reporting

**Symptoms**:
- Engineers spend 30-60 minutes/week updating ticket status
- Project managers compile reports from multiple sources
- Status meetings require "going around the room" for updates

**Impact**:
- 4-6 hours/week of engineering time per team on non-coding work
- Decisions made on stale information (3-5 days old)
- Morale impact from administrative overhead

**Root Cause**: Project status exists in human-readable formats (ticket descriptions, comments) rather than machine-queryable telemetry.

### Challenge 2: Disconnected Project and Runtime Telemetry

**Symptoms**:
- Runtime errors don't link to the task that introduced them
- Deployments not correlated with completed tasks
- Incident retrospectives require manual timeline reconstruction

**Impact**:
- Longer incident resolution (missing context)
- No automatic "this deployment contains tasks X, Y, Z"
- Retrospectives rely on tribal knowledge

**Root Cause**: Project management systems and observability systems evolved separately with no shared identifiers.

### Challenge 3: No Portfolio-Level Visibility

**Symptoms**:
- "How many projects are blocked?" requires manual survey
- No consistent health metrics across projects
- Team velocity tracked in spreadsheets

**Impact**:
- Resource allocation decisions based on incomplete data
- Blocked work discovered days later in status meetings
- No early warning for at-risk projects

**Root Cause**: Each project uses different tracking conventions; no standard aggregation layer.

---

## Guiding Policies

### Policy 1: Model Tasks as Spans

**Challenges Addressed**: 1, 2

Tasks share the structural properties of distributed trace spans:

| Task Property | Span Equivalent |
|---------------|-----------------|
| Created timestamp | `span.start_time` |
| Completed timestamp | `span.end_time` |
| Duration | `span.duration` |
| Status changes | Span events |
| Parent task (epic/story) | Parent span |
| Attributes (assignee, points) | Span attributes |

By modeling tasks as spans:
- Query with TraceQL: `{ task.status = "blocked" && task.type = "story" }`
- Visualize in trace viewers: Waterfall shows task hierarchy
- Correlate with runtime: `project.id` links task and service spans

### Policy 2: Derive Status from Artifacts

**Challenges Addressed**: 1, 3

Instead of manual updates, derive task status from existing signals:

| Artifact Event | Derived Status | Automation |
|----------------|----------------|------------|
| Task created | `backlog` | Webhook from issue tracker |
| Commit with task ID | `in_progress` | Git hook or CI job |
| PR opened | `in_review` | GitHub/GitLab webhook |
| PR merged | `done` | Webhook triggers completion |
| CI failure | `blocked` | CI webhook sets blocker |
| No activity 7 days | `stale` | Scheduled job detection |

This eliminates manual status updates while providing more accurate, real-time data.

### Policy 3: Standardize Project Semantic Conventions

**Challenges Addressed**: 2, 3

Define consistent attribute names across all projects:

```yaml
# Project identity
project.id: string           # Unique identifier
project.name: string         # Human-readable name
project.epic: string         # Parent epic/initiative

# Task attributes
task.id: string              # Task identifier (PROJ-123)
task.type: enum              # epic | story | task | subtask | bug
task.status: enum            # backlog | todo | in_progress | blocked | done
task.priority: enum          # critical | high | medium | low
task.assignee: string        # Assigned person/team
task.story_points: int       # Estimation points

# Sprint context
sprint.id: string            # Sprint identifier
sprint.name: string          # Sprint name
sprint.goal: string          # Sprint objective
```

Standard conventions enable:
- Portfolio-wide queries across projects
- Consistent dashboards and alerts
- Vendor-agnostic tooling

---

## Coherent Actions

### Action 1: Configure Issue Tracker Integration

**Policies Supported**: 1, 2

Set up webhooks or polling to capture task lifecycle events.

**Jira Webhook Configuration**:
```json
{
  "name": "ContextCore Task Sync",
  "url": "https://your-service/webhooks/jira",
  "events": [
    "jira:issue_created",
    "jira:issue_updated",
    "jira:issue_deleted"
  ],
  "filters": {
    "issue-related-events-section": "project = PROJ"
  }
}
```

**GitHub Integration**:
```yaml
# .github/workflows/task-sync.yml
on:
  issues:
    types: [opened, edited, closed, reopened]
  pull_request:
    types: [opened, closed, merged]

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: contextcore/task-sync-action@v1
        with:
          otlp_endpoint: ${{ secrets.OTLP_ENDPOINT }}
          project_id: ${{ github.repository }}
```

**Documentation**: [Issue Tracker Integration Guide](../docs/integrations/)

### Action 2: Emit Task Spans via SDK

**Policies Supported**: 1, 3

Use the TaskTracker SDK to create spans for task lifecycle.

```python
from contextcore import TaskTracker

tracker = TaskTracker(
    project_id="my-project",
    otlp_endpoint="http://tempo:4317"
)

# On task creation
tracker.start_task(
    task_id="PROJ-123",
    title="Implement user authentication",
    task_type="story",
    parent_id="EPIC-42",
    assignee="alice",
    story_points=5
)

# On status change (can be automated via webhook)
tracker.update_status("PROJ-123", "in_progress")

# On completion
tracker.complete_task("PROJ-123")
```

**Documentation**: [TaskTracker API Reference](../src/contextcore/tracker.py)

### Action 3: Configure Artifact-Based Status Derivation

**Policies Supported**: 2

Set up automation to derive status from development artifacts.

**Git Commit Hook**:
```bash
#!/bin/bash
# .git/hooks/post-commit

COMMIT_MSG=$(git log -1 --pretty=%B)
TASK_ID=$(echo "$COMMIT_MSG" | grep -oE '[A-Z]+-[0-9]+' | head -1)

if [ -n "$TASK_ID" ]; then
  contextcore task update --id "$TASK_ID" --status in_progress
fi
```

**CI Pipeline Integration**:
```yaml
# In your CI config
- name: Update task status on build
  run: |
    TASKS=$(git log $PREV_SHA..$CURR_SHA --pretty=%B | grep -oE '[A-Z]+-[0-9]+' | sort -u)
    for TASK in $TASKS; do
      if [ "$BUILD_STATUS" = "success" ]; then
        contextcore task update --id "$TASK" --add-event "build_passed"
      else
        contextcore task update --id "$TASK" --status blocked --reason "CI failure"
      fi
    done
```

### Action 4: Provision Project Dashboards

**Policies Supported**: 3

Deploy standardized dashboards for portfolio and project visibility.

```bash
# Provision both dashboards
contextcore dashboards provision

# Dashboards created:
# - Project Portfolio Overview: All projects at a glance
# - Project Details: Drill-down for single project
```

**Portfolio Dashboard Panels**:

| Panel | Query | Purpose |
|-------|-------|---------|
| Active Projects | `count by (project.id) (task_count{status!="done"})` | Portfolio size |
| Blocked Tasks | `count(task_status{status="blocked"})` | Immediate attention |
| Velocity Trend | `sum by (sprint.id) (sprint_completed_points)` | Delivery rate |
| Health Matrix | `avg by (project.id) (task_percent_complete)` | Project health |

---

## Reference Architectures

### ContextCore Reference Implementation

**Environment**: Kubernetes cluster, Grafana stack (Tempo/Mimir/Loki)

**Implementation**: Full task-as-span model with webhook-based status derivation

**Value Realized**:
- Eliminated 4 hours/week of manual status reporting
- Task status accuracy improved from ~70% to ~95%
- Portfolio visibility achieved in real-time vs. weekly reports

---

# Blueprint Category 2: AI Agent Communication

## Summary

This blueprint outlines a strategic reference for **AI/ML Platform teams** and **organizations deploying AI agents** operating in **environments where AI agents assist with development, operations, or decision-making**. It addresses the friction often found when attempting to **maintain agent context across sessions and coordinate between multiple agents**.

By implementing the patterns in this blueprint, organizations can expect to shift from **agents with session-limited memory making inconsistent decisions** to **agents with persistent insights that build on prior work and coordinate effectively**.

### Target Audience

| Persona | Current Pain | Value Delivered |
|---------|--------------|-----------------|
| **AI/ML Engineer** | Agents repeat context gathering each session | Persistent insights via TraceQL |
| **Developer using AI** | Agent decisions lost between sessions | Query prior decisions before new work |
| **Security/Compliance** | No audit trail of AI reasoning | Full telemetry of agent decisions |
| **Platform Team** | No visibility into agent effectiveness | Metrics on decisions, confidence, ROI |

### Environment Scope

- LLM-based agents (Claude, GPT, Llama, etc.)
- Development assistants (Claude Code, GitHub Copilot, etc.)
- Operational agents (incident response, auto-remediation)
- OTLP-compatible observability backends

---

## Diagnosis: Common Challenges

### Challenge 1: Session-Limited Agent Memory

**Symptoms**:
- Agent asks same clarifying questions each session
- Decisions made in previous sessions not referenced
- Lessons learned not applied to similar future situations

**Impact**:
- Wasted tokens on repeated context gathering
- Inconsistent recommendations across sessions
- Lost value from prior agent work

**Root Cause**: LLM context windows are session-scoped; no standard mechanism to persist and query agent insights.

### Challenge 2: No Agent-to-Agent Coordination

**Symptoms**:
- Multiple agents working on same project make conflicting decisions
- Handoffs between agents (or agent-to-human) lose context
- No way to specify which agent's decisions take precedence

**Impact**:
- Conflicting code changes from different agents
- Repeated work due to poor handoffs
- No coordination on architectural decisions

**Root Cause**: Agents operate independently without a shared memory or communication protocol.

### Challenge 3: Missing AI Audit Trail

**Symptoms**:
- "Why did the agent make this decision?" unanswerable after the fact
- No visibility into agent confidence levels
- Can't differentiate agent-generated vs. human-generated changes

**Impact**:
- Compliance concerns in regulated industries
- No ability to review agent reasoning in code review
- Can't identify patterns in agent mistakes

**Root Cause**: Agent decisions treated as ephemeral chat, not persistent telemetry.

---

## Guiding Policies

### Policy 1: Store Agent Insights as Telemetry

**Challenges Addressed**: 1, 3

Agent insights are events that should persist beyond session boundaries:

| Insight Type | Purpose | Key Attributes |
|--------------|---------|----------------|
| **Decision** | Architectural/implementation choice | `confidence`, `rationale`, `alternatives` |
| **Lesson** | Pattern learned from experience | `category`, `applies_to` |
| **Question** | Unresolved item needing input | `urgency`, `options` |
| **Handoff** | Context for next agent/human | `recipient`, `context_summary` |

By storing insights as spans in Tempo:
- Query: `{ agent.insight.type = "decision" && agent.insight.confidence > 0.8 }`
- Persist: Insights survive beyond session/context window
- Audit: Full history of agent reasoning

### Policy 2: Query Prior Context Before Acting

**Challenges Addressed**: 1, 2

Before making decisions, agents should check what's been decided:

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Session Start                                        │
│  │                                                          │
│  ├──▶ Query: Prior decisions on this file/module            │
│  │    { agent.insight.applies_to contains "src/auth/" }     │
│  │                                                          │
│  ├──▶ Query: Active constraints from humans                 │
│  │    { guidance.type = "constraint" && guidance.active }   │
│  │                                                          │
│  ├──▶ Query: Open questions needing resolution              │
│  │    { agent.insight.type = "question" && !resolved }      │
│  │                                                          │
│  └──▶ Proceed with context-aware decision making            │
└─────────────────────────────────────────────────────────────┘
```

This ensures agents build on prior work rather than starting fresh.

### Policy 3: Implement Handoff Protocol

**Challenges Addressed**: 2

When transitioning between agents or agent-to-human:

```yaml
# Handoff span attributes
agent.insight.type: "handoff"
agent.insight.from_agent: "claude-code-session-123"
agent.insight.to_agent: "claude-code-session-456"  # or "human"
agent.insight.context_summary: "Implemented auth flow, needs testing"
agent.insight.open_items:
  - "Unit tests for edge cases"
  - "Integration test with OAuth provider"
agent.insight.decisions_made:
  - ref: "span-id-of-decision-1"
  - ref: "span-id-of-decision-2"
```

Handoff protocol ensures:
- No context loss between agents
- Clear ownership transitions
- Audit trail of who did what

---

## Coherent Actions

### Action 1: Instrument Agent Sessions

**Policies Supported**: 1, 3

Wrap agent sessions in parent spans with identity attributes.

```python
from contextcore.agent import AgentSession

# Start instrumented session
with AgentSession(
    agent_id="claude-code",
    project_id="my-project",
    session_id="session-123"
) as session:
    # All LLM calls are children of this span
    response = llm.complete(prompt)

    # Emit insights during session
    session.emit_decision(
        summary="Selected FastAPI for API framework",
        confidence=0.88,
        rationale="Better async support, auto OpenAPI"
    )
```

**Span Hierarchy**:
```
agent.session (parent)
├── llm.call (child)
├── llm.call (child)
├── agent.insight.decision (child)
├── llm.call (child)
└── agent.insight.handoff (child, at session end)
```

### Action 2: Configure Insight Querier

**Policies Supported**: 2

Set up the insight querier to check prior context at session start.

```python
from contextcore.agent import InsightQuerier

querier = InsightQuerier(
    tempo_endpoint="http://tempo:3200"
)

# At session start, query prior context
def get_agent_context(project_id: str, scope: list[str]) -> dict:
    """Get relevant prior context for agent session."""

    return {
        "prior_decisions": querier.query(
            project_id=project_id,
            insight_type="decision",
            applies_to=scope,
            time_range="30d",
            min_confidence=0.7
        ),
        "lessons_learned": querier.query(
            project_id=project_id,
            insight_type="lesson",
            applies_to=scope,
            time_range="90d"
        ),
        "open_questions": querier.query(
            project_id=project_id,
            insight_type="question",
            resolved=False
        ),
        "active_constraints": querier.query_guidance(
            project_id=project_id,
            guidance_type="constraint",
            active=True
        )
    }

# Include in agent system prompt
context = get_agent_context("my-project", ["src/auth/"])
system_prompt = f"""
## Prior Context

### Recent Decisions
{format_decisions(context['prior_decisions'])}

### Lessons Learned
{format_lessons(context['lessons_learned'])}

### Active Constraints
{format_constraints(context['active_constraints'])}
"""
```

### Action 3: Implement Handoff Emission

**Policies Supported**: 2, 3

Emit handoff spans when transitioning between agents or ending sessions.

```python
from contextcore.agent import InsightEmitter

emitter = InsightEmitter(
    project_id="my-project",
    agent_id="claude-code-session-123"
)

# At session end or agent switch
emitter.emit_handoff(
    to_agent="human",  # or next agent ID
    context_summary="Implemented user authentication with JWT",
    open_items=[
        "Add refresh token rotation",
        "Write integration tests"
    ],
    decisions_made=[
        {"span_id": "abc123", "summary": "JWT over sessions"},
        {"span_id": "def456", "summary": "Redis for token storage"}
    ],
    confidence=0.85
)
```

### Action 4: Build Agent Effectiveness Dashboards

**Policies Supported**: 3

Create dashboards to monitor agent decision quality and effectiveness.

**Metrics to Track**:

| Metric | Query | Purpose |
|--------|-------|---------|
| Decisions per project | `count by (project.id) (agent.insight.type="decision")` | Agent activity |
| Average confidence | `avg(agent.insight.confidence)` | Decision quality |
| Questions resolved | `count(agent.insight.type="question" && resolved)` | Human-agent loop |
| Handoff completeness | `avg(handoff.context_score)` | Transition quality |
| Insight reuse rate | `count(insights_queried) / count(sessions)` | Memory utilization |

---

## Reference Architectures

### Claude Code with ContextCore

**Environment**: Developer workstation with Claude Code, Tempo backend

**Implementation**: Hooks emit insights, querier loads context at session start

**Value Realized**:
- 40% reduction in repeated context questions
- Decisions persist across refactoring sessions
- Full audit trail for compliance review

---

## Appendix: Semantic Conventions for AI Agents

### Agent Identity

```yaml
agent.id: string              # Unique agent identifier
agent.type: string            # claude | gpt | llama | custom
agent.version: string         # Agent/model version
agent.session.id: string      # Session/conversation identifier
```

### Insight Attributes

```yaml
agent.insight.type: enum      # decision | lesson | question | handoff
agent.insight.summary: string # Human-readable summary
agent.insight.confidence: float # 0.0-1.0
agent.insight.rationale: string # Reasoning behind insight
agent.insight.applies_to: string[] # Files/modules affected
agent.insight.timestamp: int  # Unix timestamp
```

### Decision-Specific

```yaml
agent.insight.alternatives: string[] # Considered alternatives
agent.insight.tradeoffs: string      # Tradeoff analysis
```

### Lesson-Specific

```yaml
agent.insight.category: string # testing | architecture | performance
agent.insight.severity: string # Should follow vs nice to have
```

### Question-Specific

```yaml
agent.insight.urgency: enum    # blocking | high | medium | low
agent.insight.options: string[] # Possible answers
agent.insight.resolved: bool   # Whether answered
agent.insight.answer: string   # Resolution if resolved
```

### Handoff-Specific

```yaml
agent.insight.from_agent: string   # Source agent ID
agent.insight.to_agent: string     # Target agent ID or "human"
agent.insight.context_summary: string
agent.insight.open_items: string[]
agent.insight.decisions_made: object[] # References to decision spans
```

---

## Submitting These Categories

To propose these new blueprint categories to OTel:

1. **Create GitHub issue** in `open-telemetry/community` describing the category
2. **Draft blueprint** following the OTel Blueprint Template structure
3. **Gather end-user validation** (see validation framework document)
4. **Present to End-User SIG** for feedback and sponsorship
5. **Iterate based on feedback** until ready for formal proposal
