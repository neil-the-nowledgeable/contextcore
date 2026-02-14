# Agent Semantic Conventions

Semantic conventions for agent-to-agent, agent-to-human, and human-to-agent communication within ContextCore.

---

## Agent-to-Agent Communication (Machine-Readable)

### Entry Point

```bash
# Query agent insights via TraceQL
{ insight.type = "decision" && project.id = "my-project" }

# Query agent sessions via Loki
{agent_id=~".+"} | json | insight_type = "recommendation"
```

### Attribute Reference

| Namespace | Purpose | OTel GenAI Equivalent | Token Cost |
|-----------|---------|-----------------------|------------|
| `agent.*` | Agent identity and session | `gen_ai.agent.*` | ~50 |
| `insight.*` | Agent-generated knowledge | (Custom Extension) | ~100 |
| `guidance.*` | Human-to-agent direction | (Custom Extension) | ~75 |
| `handoff.*` | Agent-to-agent delegation | `gen_ai.tool.*` | ~80 |

> **Note**: ContextCore v2.0+ emits `gen_ai.*` attributes alongside legacy attributes. See [Migration Guide](OTEL_GENAI_MIGRATION_GUIDE.md).

---

## Semantic Conventions

### 1. Agent Identity Attributes (`agent.*`)

Identify which agent emitted telemetry and session context.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent.id` | string | Yes | Unique agent identifier (e.g., `claude-code`, `gpt-4-agent`) |
| `agent.session_id` | string | Yes | Session scope identifier |
| `agent.type` | enum | Yes | Agent category |
| `agent.version` | string | No | Agent/model version |
| `agent.capabilities` | string[] | No | Capabilities available to this agent |
| `agent.parent_session_id` | string | No | Parent session if spawned by another agent |

**`agent.type` values:**
- `code_assistant` - Development-focused agents (Claude Code, Cursor, Copilot)
- `orchestrator` - Agents that coordinate other agents
- `specialist` - Domain-specific agents (o11y, security, testing)
- `automation` - Automated pipeline agents (CI/CD, scheduled tasks)

**Example:**
```yaml
agent:
  id: "claude-code"
  session_id: "2024-01-14-abc123"
  type: "code_assistant"
  version: "claude-opus-4-5-20251101"
  capabilities: ["code_review", "debugging", "refactoring"]
```

---

### 2. Insight Attributes (`insight.*`)

Agent-generated knowledge, decisions, and recommendations.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `insight.id` | string | Yes | Unique insight identifier |
| `insight.type` | enum | Yes | Category of insight |
| `insight.summary` | string | Yes | Brief description (1-2 sentences) |
| `insight.confidence` | float | Yes | Confidence score (0.0-1.0) |
| `insight.audience` | enum | Yes | Intended consumer |
| `insight.rationale` | string | No | Reasoning behind insight |
| `insight.evidence` | object[] | No | Supporting data references |
| `insight.supersedes` | string | No | ID of insight this replaces |
| `insight.expires_at` | timestamp | No | When insight becomes stale |

**`insight.type` values:**
- `analysis` - Understanding of current state
- `recommendation` - Suggested action
- `decision` - Choice made by agent
- `question` - Needs human input
- `blocker` - Cannot proceed without resolution
- `discovery` - New finding about codebase/system
- `risk` - Identified risk or concern
- `progress` - Status update on task

**`insight.audience` values:**
- `agent` - For other agents only
- `human` - For humans only
- `both` - Relevant to both audiences

**Example:**
```yaml
insight:
  id: "insight-2024-01-14-001"
  type: "decision"
  summary: "Selected event-driven architecture for checkout service"
  confidence: 0.92
  audience: "both"
  rationale: "Lower coupling aligns with ADR-015, enables independent scaling"
  evidence:
    - type: "adr"
      ref: "ADR-015-event-driven-checkout"
    - type: "trace"
      id: "abc123"
      description: "Current sync calls show 200ms latency"
  supersedes: null
  expires_at: null
```

---

### 3. Evidence Attributes (`insight.evidence[]`)

References to supporting data for insights.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `type` | enum | Yes | Evidence category |
| `ref` | string | Yes | Reference identifier or URL |
| `description` | string | No | Brief explanation |
| `query` | string | No | Query that produced this evidence |
| `timestamp` | timestamp | No | When evidence was collected |

**`type` values:**
- `trace` - Tempo trace ID
- `log_query` - Loki query
- `metric_query` - PromQL query
- `file` - File path reference
- `commit` - Git commit SHA
- `pr` - Pull request reference
- `adr` - Architecture Decision Record
- `doc` - Documentation URL
- `task` - Task/issue reference

---

### 4. Guidance Attributes (`guidance.*`)

Human-to-agent direction that persists across sessions.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `guidance.id` | string | Yes | Unique guidance identifier |
| `guidance.type` | enum | Yes | Category of guidance |
| `guidance.content` | string | Yes | The guidance text |
| `guidance.priority` | enum | No | Importance level |
| `guidance.scope` | string | No | What this guidance applies to |
| `guidance.expires_at` | timestamp | No | When guidance becomes stale |
| `guidance.author` | string | No | Human who provided guidance |

**`guidance.type` values:**
- `focus` - Priority area for agent attention
- `constraint` - What agent must NOT do
- `preference` - Preferred approach (not mandatory)
- `question` - Question for agent to answer
- `context` - Background information

**Example:**
```yaml
guidance:
  id: "guidance-2024-01-14-001"
  type: "constraint"
  content: "Do not modify the authentication module without explicit approval"
  priority: "critical"
  scope: "src/auth/**"
  author: "alice@example.com"
```

---

### 5. Handoff Attributes (`handoff.*`)

Agent-to-agent task delegation.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `handoff.id` | string | Yes | Unique handoff identifier |
| `handoff.from_agent` | string | Yes | Delegating agent ID |
| `handoff.to_agent` | string | Yes | Receiving agent ID |
| `handoff.capability_id` | string | Yes | Capability being requested |
| `handoff.task` | string | Yes | Natural language task description |
| `handoff.inputs` | object | Yes | Typed inputs for capability |
| `handoff.expected_output` | object | Yes | Expected response format |
| `handoff.priority` | enum | No | Task priority |
| `handoff.timeout_ms` | integer | No | Max wait time |
| `handoff.status` | enum | No | Current handoff status |

**`handoff.status` values:**
- `pending` - Not yet accepted
- `accepted` - Receiving agent acknowledged
- `in_progress` - Work underway
- `input_required` - Agent needs additional input before continuing (A2A-aligned)
- `completed` - Result available
- `failed` - Could not complete
- `timeout` - Exceeded timeout
- `cancelled` - Task was cancelled (A2A-aligned)
- `rejected` - Receiving agent rejected the handoff (A2A-aligned)

**State Machine Helpers** (Python SDK):
```python
from contextcore.agent.handoff import HandoffStatus

status = HandoffStatus.IN_PROGRESS
status.is_terminal()                          # False
status.is_active()                            # True
status.can_transition_to(HandoffStatus.COMPLETED)  # True
status.can_transition_to(HandoffStatus.PENDING)    # False (invalid transition)
```

**Example:**
```yaml
handoff:
  id: "handoff-2024-01-14-001"
  from_agent: "orchestrator"
  to_agent: "o11y"
  capability_id: "investigate_error"
  task: "Find root cause of checkout latency spike"
  inputs:
    error_context: "P99 latency increased from 200ms to 800ms"
    time_range: "2h"
    app_name: "checkout-service"
  expected_output:
    type: "analysis_report"
    fields: ["root_cause", "evidence", "recommended_fix"]
  priority: "high"
  timeout_ms: 300000
  status: "pending"
```

---

### 6. Personalization Attributes (`personalization.*`)

Audience-specific presentation hints.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `personalization.audience_type` | enum | No | Target audience |
| `personalization.technical_depth` | enum | No | Detail level |
| `personalization.format` | enum | No | Preferred format |
| `personalization.language` | string | No | Human language preference |

**`audience_type` values:**
- `executive` - High-level, business-focused
- `manager` - Project/team focused
- `developer` - Technical, implementation focused
- `operator` - Runtime/ops focused
- `agent` - Machine consumption

**`technical_depth` values:**
- `summary` - 1-2 sentences, key points only
- `standard` - Normal level of detail
- `detailed` - Full technical explanation
- `expert` - Assumes deep domain knowledge

---

## Query Patterns

### Agent-to-Agent Queries

```
# Find recent decisions by any agent for this project
{ insight.type = "decision" && project.id = "checkout" }

# Find blockers that need resolution
{ insight.type = "blocker" && insight.audience =~ "agent|both" }

# Find handoffs waiting for this agent
{ handoff.to_agent = "o11y" && handoff.status = "pending" }

# Find insights with high confidence
{ insight.confidence > 0.9 && project.id = "checkout" }
```

### Agent-to-Human Queries (Grafana)

```promql
# Count of agent decisions by project
count by (project_id) (insight_total{insight_type="decision"})

# Agent activity over time
rate(insight_total[1h])

# Blocked tasks needing human attention
insight_count{insight_type="blocker", insight_audience=~"human|both"}
```

### Human-to-Agent Queries

```yaml
# Agent reads guidance from ProjectContext
kubectl get projectcontext checkout-service -o jsonpath='{.spec.agent_guidance}'

# Or via K8s API
GET /apis/contextcore.io/v1/namespaces/commerce/projectcontexts/checkout-service
```

---

### 7. Framework Interoperability Attributes (Optional)

Optional attributes for bridging external agent/pipeline frameworks to ContextCore governance.
These attributes are **never required** — they provide lineage context when ContextCore governs
execution that originates in an external runtime.

#### Graph Orchestration (`graph.*`) — LangGraph, StateGraph

For frameworks that model execution as directed graphs with stateful checkpoints.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `graph.id` | string | No | Graph definition identifier |
| `graph.node` | string | No | Current node within the graph |
| `graph.edge` | string | No | Edge label that triggered this transition |
| `graph.checkpoint_id` | string | No | Durable checkpoint identifier for resumability |
| `graph.checkpoint_approved_by` | string | No | Who/what approved resumption from checkpoint |

#### Crew/Role Orchestration (`crew.*`) — CrewAI

For role-driven agent team frameworks.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `crew.id` | string | No | Crew/team identifier |
| `crew.role` | string | No | Role of the acting agent within the crew |
| `crew.flow_step` | string | No | Current step in the crew's workflow |
| `crew.blocked_on_role` | string | No | Which role is blocking progress |
| `crew.next_action_owner` | string | No | Role responsible for the next action |

#### Pipeline Orchestration (`pipeline.*`) — Haystack, Custom Pipelines

For component-based pipeline frameworks.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `pipeline.id` | string | No | Pipeline definition identifier |
| `pipeline.component` | string | No | Current component/node within the pipeline |
| `pipeline.step` | integer | No | Ordinal step number |
| `pipeline.topology_ref` | string | No | Reference to pipeline topology definition |

#### RAG Orchestration (`rag.*`) — LlamaIndex, Haystack RAG

For retrieval-augmented generation pipelines.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `rag.phase` | string | No | RAG phase: `indexing`, `retrieval`, `generation`, `evaluation` |
| `rag.index_id` | string | No | Index being queried |
| `rag.retrieval_mode` | string | No | Retrieval strategy: `dense`, `sparse`, `hybrid`, `reranked` |
| `rag.retrieval_confidence` | float | No | Retrieval confidence score (0.0-1.0) |
| `rag.chunk_count` | integer | No | Number of chunks retrieved |

#### Conversation Lineage (`conversation.*`) — AutoGen, OpenAI Agents SDK

For conversational multi-agent frameworks.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation.id` | string | No | Conversation/thread identifier |
| `conversation.turn_id` | string | No | Current turn within the conversation |
| `conversation.agent_role` | string | No | Role of agent in this conversation turn |
| `conversation.parent_turn_id` | string | No | Parent turn (for nested conversations) |

#### Optimization/Tuning (`optimization.*`) — DSPy

For programmatic prompt/model optimization frameworks.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `optimization.run_id` | string | No | Optimization run identifier |
| `optimization.metric` | string | No | Target metric being optimized |
| `optimization.baseline_score` | float | No | Score before optimization |
| `optimization.optimized_score` | float | No | Score after optimization |
| `prompt.version` | string | No | Version of the prompt/program being optimized |

#### Structured Output (`validation.*`) — Guidance, Outlines, Instructor

For schema-constrained generation frameworks.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `validation.retry_count` | integer | No | Number of validation retries before success |
| `validation.failure_reason` | string | No | Last validation failure reason |
| `gen_ai.response.schema` | string | No | Schema reference for expected output structure |
| `gen_ai.response.schema_version` | string | No | Version of the response schema |

#### Capability Registry (`capability.*`) — Semantic Kernel, Plugin Systems

For frameworks with explicit capability/plugin registries.

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `capability.id` | string | No | Registered capability identifier |
| `capability.owner` | string | No | Team/agent that owns this capability |
| `capability.risk_tier` | string | No | Risk classification: `low`, `medium`, `high`, `critical` |
| `capability.required_gates` | string[] | No | Gate IDs that must pass before invocation |

> **Usage principle**: Keep execution runtime in the external framework. Use these attributes
> only when ContextCore needs lineage context for governance decisions, gate checks, or
> observability queries. Never duplicate runtime logic.

---

## Human-Readable Documentation (Below)

### Why These Conventions Matter

These semantic conventions enable three critical capabilities:

1. **Agent Memory Across Sessions**: Insights persist in Tempo/Loki, queryable by future agent sessions
2. **Cross-Agent Collaboration**: Agent A's discoveries are available to Agent B via standard queries
3. **Human Visibility**: Same data powers Grafana dashboards for project managers, developers, executives

### Design Principles

1. **Typed Over Prose**: All attributes have explicit types. Agents don't parse natural language.
2. **Audience-Aware**: Every insight declares its intended consumer (`agent`, `human`, `both`).
3. **Evidence-Linked**: Insights reference supporting data (traces, logs, files) for verification.
4. **Supersession**: Insights can explicitly replace earlier insights (`supersedes`).
5. **Expiration**: Time-sensitive insights have explicit expiration (`expires_at`).

### Integration with ContextCore

These conventions extend the existing ContextCore semantic conventions:

| Existing Namespace | New Namespace | Relationship |
|-------------------|---------------|--------------|
| `project.*` | `agent.*` | Agent operates within project context |
| `task.*` | `insight.*` | Insights link to tasks they inform |
| `business.*` | `guidance.*` | Guidance carries business constraints |
| `design.*` | `handoff.*` | Handoffs reference design docs |

### Storage

| Signal Type | Storage Backend | Query Language |
|-------------|-----------------|----------------|
| Insights (spans) | Tempo | TraceQL |
| Insights (logs) | Loki | LogQL |
| Insight metrics | Mimir | PromQL |
| Guidance (CRD) | K8s etcd | kubectl / K8s API |

---

## Anti-Patterns

| Don't | Why | Instead |
|-------|-----|---------|
| Store insights only in chat transcript | Not queryable, lost on session end | Emit as OTel spans to Tempo |
| Use prose descriptions for insight type | Requires NL parsing | Use typed enum values |
| Omit confidence scores | Can't filter by reliability | Always include `insight.confidence` |
| Create insights without evidence | Unverifiable claims | Link to traces, logs, files |
| Ignore audience attribute | Wrong consumers see wrong info | Explicitly set `insight.audience` |
