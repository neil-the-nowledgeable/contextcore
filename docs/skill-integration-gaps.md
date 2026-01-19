# Skill Integration Gap Analysis

## Executive Summary

The skill capability framework we built stores capabilities as OTel spans but **fails to integrate with ContextCore's existing agent communication patterns**. This creates two disconnected systems where skills exist in isolation from insights, handoffs, and project context.

---

## Critical Gaps

### Gap 1: No Agent Identity Attribution

**Current State:**
- Skills are emitted without tracking which agent discovered or used them
- No `agent.id` or `agent.session_id` on skill/capability spans

**Impact:**
- Can't trace "who discovered this capability"
- No audit trail for capability usage
- Can't answer "what capabilities did this agent use this session?"

**Fix:**
```python
# SkillCapabilityEmitter should require agent context
emitter = SkillCapabilityEmitter(
    agent_id="claude-code",
    session_id="session-abc123"
)
```

**Span attributes to add:**
```yaml
agent.id: "claude-code"
agent.session_id: "session-abc123"
agent.type: "code_assistant"
```

---

### Gap 2: No Insight Integration

**Current State:**
- When an agent queries capabilities, no insight is emitted
- Capability discoveries are invisible to other agents
- Routing decisions aren't recorded

**Impact:**
- Other agents can't learn from capability usage patterns
- No cross-session memory of "this capability worked well for X"
- Can't query "what capabilities have been used for checkout-service?"

**Fix:** When querying capabilities, emit discovery insights:
```python
# In SkillCapabilityQuerier.query()
def query(self, ...):
    results = self._execute_traceql(query)

    # Emit discovery insight
    if results:
        insight_emitter.emit_discovery(
            summary=f"Found {len(results)} capabilities matching '{trigger}'",
            confidence=0.95,
            evidence=[
                Evidence(type="capability", ref=f"{r.skill_id}:{r.capability_id}")
                for r in results
            ]
        )

    return results
```

---

### Gap 3: Evidence Model Divergence

**ContextCore Evidence:**
```python
@dataclass
class Evidence:
    type: str      # trace, log_query, file, commit, adr, doc
    ref: str
    description: str | None = None
    query: str | None = None      # ← We're missing this
    timestamp: datetime | None = None  # ← We're missing this
```

**Our CapabilityEvidence:**
```python
class CapabilityEvidence(BaseModel):
    type: EvidenceType
    ref: str
    description: Optional[str] = None
    tokens: int = 0  # ← Added this, but lost query/timestamp
```

**Impact:**
- Can't store the TraceQL query that found this capability
- Can't track when evidence was collected
- Inconsistent serialization between systems

**Fix:** Unify evidence models:
```python
class Evidence(BaseModel):
    type: str
    ref: str
    description: Optional[str] = None
    query: Optional[str] = None      # Restore
    timestamp: Optional[datetime] = None  # Restore
    tokens: Optional[int] = None     # Optional extension
```

---

### Gap 4: No Audience Differentiation

**ContextCore Pattern:**
```yaml
insight.audience: agent | human | both
```

**Our Implementation:**
- We track `interop_human` and `interop_agent` scores (1-5)
- But don't use the `audience` enum pattern

**Impact:**
- Can't filter "show only agent-consumable capabilities"
- Scores are harder to query than enums in TraceQL

**Fix:** Add `capability.audience` attribute:
```yaml
capability.audience: agent | human | both

# Derived from scores:
# interop_agent >= 4 && interop_human < 3 → agent
# interop_human >= 4 && interop_agent < 3 → human
# both >= 3 → both
```

---

### Gap 5: No Confidence/Reliability Scoring

**ContextCore Pattern:**
```yaml
insight.confidence: 0.92  # 0.0-1.0
```

**Our Implementation:**
- No confidence score on capabilities
- No way to track reliability or success rates

**Impact:**
- Can't query "high-confidence capabilities only"
- Can't learn which capabilities are reliable
- No feedback loop from usage

**Fix:** Add confidence tracking:
```yaml
capability.confidence: 0.95      # Initial confidence from documentation
capability.success_rate: 0.87    # Calculated from usage (requires usage tracking)
capability.invocation_count: 42  # Times this capability was used
```

---

### Gap 6: No Handoff Integration

**ContextCore Handoff Pattern:**
```yaml
handoff:
  capability_id: "investigate_error"  # References a capability
  task: "Find root cause"
  inputs: {...}
```

**Our Implementation:**
- Handoffs reference `capability_id` but no span link exists
- Can't trace from handoff to capability definition
- Can't answer "which handoffs used this capability?"

**Fix:** Create span links between handoffs and capabilities:
```python
# When processing a handoff
def process_handoff(handoff):
    # Find the capability span
    capability_span_id = query_capability_span(handoff.capability_id)

    # Create handoff span with link
    with tracer.start_span("handoff", links=[
        Link(capability_span_id, attributes={"link.type": "uses_capability"})
    ]) as span:
        # ... process handoff
```

---

### Gap 7: No Lifecycle Events

**ContextCore Task Pattern:**
```yaml
events:
  - task.created
  - task.status_changed
  - task.blocked
  - task.unblocked
  - task.completed
```

**Our Implementation:**
- Skills only have `quick_action` events
- No lifecycle tracking for capabilities

**Impact:**
- Can't track when capability was last used
- Can't detect stale capabilities
- No deprecation workflow

**Fix:** Add capability lifecycle events:
```yaml
events:
  - capability.registered    # When first emitted
  - capability.updated       # Schema changed
  - capability.deprecated    # Marked for removal
  - capability.invoked       # When used via handoff
  - capability.succeeded     # Invocation succeeded
  - capability.failed        # Invocation failed
```

---

### Gap 8: No Staleness/Expiration

**ContextCore Pattern:**
```yaml
insight.expires_at: "2024-03-15T00:00:00Z"
insight.supersedes: "insight-old-123"
```

**Our Implementation:**
- No `expires_at` on capabilities
- No `supersedes` for version evolution
- No `last_updated` timestamp

**Impact:**
- Can't filter out stale capabilities
- Can't track capability version history
- No way to say "this capability replaced the old one"

**Fix:**
```yaml
capability.created_at: "2024-01-14T10:00:00Z"
capability.updated_at: "2024-01-14T15:00:00Z"
capability.expires_at: "2024-06-01T00:00:00Z"  # Optional
capability.supersedes: "old_capability_id"      # Optional
```

---

### Gap 9: No Project Context Linkage

**ContextCore Pattern:**
```yaml
# ProjectContext can declare required skills
spec:
  requiredCapabilities:
    - skill_id: "o11y"
      capability_id: "investigate_error"
    - skill_id: "grafana-dashboards"
      capability_id: "create_dashboard"
```

**Our Implementation:**
- Skills exist in isolation
- No link from project to required skills
- Can't answer "what skills does checkout-service need?"

**Fix:** Add bidirectional linking:
```yaml
# On capability spans
capability.project_refs: ["checkout-service", "payment-service"]

# In ProjectContext CRD
spec:
  requiredCapabilities:
    - skill_id: "o11y"
      capabilities: ["investigate_error", "create_dashboard"]
```

---

### Gap 10: Guidance Integration

**ContextCore agentGuidance:**
```yaml
spec:
  agentGuidance:
    constraints:
      - id: "no-direct-db"
        rule: "Do not modify database schema"
        scope: "src/db/**"
    preferences:
      - id: "use-event-driven"
        preference: "Prefer event-driven over polling"
```

**Our Implementation:**
- We store `constraints` in SkillManifest
- But don't read from `agentGuidance`
- No dynamic constraint inheritance

**Impact:**
- Skills can't adapt to project constraints
- Guidance changes require skill re-emission
- No centralized constraint management

**Fix:** Skills should inherit constraints from ProjectContext:
```python
def get_effective_constraints(skill_id: str, project_id: str) -> list[str]:
    skill_constraints = skill.constraints
    project_constraints = project_context.spec.agent_guidance.constraints
    return skill_constraints + project_constraints
```

---

## Architectural Gaps

### A1: Two Disconnected Systems

**Problem:**
- `InsightEmitter` for agent communication
- `SkillCapabilityEmitter` for skill storage

These share no code, no base classes, no common patterns.

**Impact:**
- Duplicate span emission logic
- Inconsistent attribute naming
- No span linking between systems

**Fix:** Create a unified base:
```python
class BaseContextCoreEmitter:
    def __init__(self, agent_id, session_id, project_id):
        self.agent_id = agent_id
        self.session_id = session_id
        self.project_id = project_id
        self.tracer = trace.get_tracer("contextcore")

    def _set_common_attributes(self, span):
        span.set_attribute("agent.id", self.agent_id)
        span.set_attribute("agent.session_id", self.session_id)
        span.set_attribute("project.id", self.project_id)

class InsightEmitter(BaseContextCoreEmitter): ...
class SkillCapabilityEmitter(BaseContextCoreEmitter): ...
```

### A2: No Usage Metrics

**Problem:**
- Tasks have derived metrics (lead_time, cycle_time, wip)
- Skills have no usage metrics

**Impact:**
- Can't track capability popularity
- Can't identify underused capabilities
- No data for optimization decisions

**Fix:** Derive metrics from capability.invoked events:
```promql
# Most used capabilities
topk(10, sum by (capability_id) (capability_invoked_total))

# Capability success rate
capability_succeeded_total / capability_invoked_total

# Average token cost per invocation
avg by (capability_id) (capability_invocation_tokens)
```

### A3: No Cross-Skill Discovery

**Problem:**
- Skills are emitted independently
- No semantic relationships between capabilities

**Impact:**
- Can't query "capabilities that transform X to Y"
- No "similar capability" suggestions
- No capability graph

**Fix:** Add semantic tags and relationships:
```yaml
capability.input_types: ["markdown", "prose"]
capability.output_types: ["yaml", "structured"]
capability.related_capabilities: ["validate_format", "audit_tokens"]
capability.domain: "documentation"
```

---

## Recommended Actions

### Phase 1: Quick Wins (Unify Patterns)

1. **Add agent attribution** to all skill spans
2. **Unify Evidence model** with query/timestamp fields
3. **Add capability.audience** enum derived from scores
4. **Add timestamps** (created_at, updated_at)

### Phase 2: Integration (Connect Systems)

5. **Emit discovery insights** when querying capabilities
6. **Create span links** from handoffs to capabilities
7. **Inherit constraints** from ProjectContext
8. **Add lifecycle events** for invocation tracking

### Phase 3: Metrics & Intelligence

9. **Derive usage metrics** from invocation events
10. **Add confidence scoring** based on success rates
11. **Build capability graph** with semantic relationships
12. **Cross-project capability recommendations**

---

## TraceQL Queries (After Fixes)

```
# Find capabilities discovered by this agent this session
{ capability.id != "" && agent.session_id = "session-abc123" }

# Find capabilities with high confidence
{ capability.confidence > 0.9 }

# Find capabilities used by checkout-service
{ capability.project_refs =~ ".*checkout.*" }

# Trace from handoff to capability
{ handoff.id = "handoff-123" } >> { capability.id != "" }

# Find capabilities updated recently
{ capability.updated_at > "2024-01-01" }

# Find agent-optimized capabilities for transforms
{ capability.audience = "agent" && capability.category = "transform" }
```

---

## Summary

| Gap Category | Count | Priority |
|--------------|-------|----------|
| Agent Identity | 1 | Critical |
| Insight Integration | 1 | Critical |
| Model Consistency | 2 | High |
| Lifecycle Tracking | 2 | High |
| Project Linkage | 2 | Medium |
| Metrics | 2 | Medium |
| **Total** | **10** | |

The fundamental issue is that we built skill storage **without considering how skills participate in the agent communication ecosystem**. Skills should be:

1. **Discovered** via insights (`insight.type = "discovery"`)
2. **Used** via handoffs (`handoff.capability_id`)
3. **Constrained** by guidance (`agentGuidance.constraints`)
4. **Attributed** to agents (`agent.id`, `agent.session_id`)
5. **Tracked** over time (`capability.invoked`, success rates)

Without these integrations, skills are just static metadata, not living participants in agent collaboration.
