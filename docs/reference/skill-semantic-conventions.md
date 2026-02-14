# Skill Semantic Conventions

This document defines the semantic conventions for storing skill capabilities as OpenTelemetry spans in Tempo.

> **OTel GenAI Alignment (v2.0+)**: ContextCore is migrating to [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). Agent-related attributes are now dual-emitted with both legacy `agent.*` and new `gen_ai.*` equivalents. See [Migration Guide](OTEL_GENAI_MIGRATION_GUIDE.md).

## Overview

Skills are stored as hierarchical spans following the same pattern as tasks:
- **Skill spans**: Parent spans representing skill manifests
- **Capability spans**: Child spans representing individual capabilities
- **Lifecycle spans**: Track capability invocation patterns

This enables TraceQL-based capability discovery and token-efficient agent-to-agent communication.

### Integration with ContextCore Patterns

Skills integrate with the broader ContextCore ecosystem:
- **Agent Attribution**: All spans tagged with `agent.id` and `agent.session_id`
- **Insight System**: Discovery insights emitted when capabilities are found
- **Handoff Protocol**: Capabilities linked via `capability_id` in handoffs
- **Project Linkage**: Skills can be associated with projects

## Span Naming

| Span Type | Name Format | Example |
|-----------|-------------|---------|
| Skill manifest | `skill:{skill_id}` | `skill:llm-formatter` |
| Capability | `capability:{capability_id}` | `capability:transform_document` |
| Lifecycle event | `capability.{event}` | `capability.invoked` |

## Common Attributes (All Spans)

All skill-related spans include agent attribution:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent.id` | string | Yes | Agent that registered/invoked (e.g., "claude-code") |
| `agent.session_id` | string | Yes | Session identifier for grouping |
| `project.id` | string | No | Project context for linking |

**OTel GenAI Equivalents (v2.0+)**:

In dual-emit mode (default), the following OTel GenAI attributes are also emitted:

| Legacy Attribute | OTel GenAI Attribute | Description |
|------------------|---------------------|-------------|
| `agent.id` | `gen_ai.agent.id` | Agent identifier |
| `agent.session_id` | `gen_ai.conversation.id` | Session/conversation context |
| - | `gen_ai.system` | AI provider (e.g., "anthropic") |
| - | `gen_ai.operation.name` | Operation type (e.g., "skill.emit")

## Skill Attributes

Attributes on skill manifest spans:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `skill.id` | string | Yes | Unique skill identifier |
| `skill.type` | enum | Yes | `utility` \| `orchestration` \| `specialist` \| `automation` |
| `skill.version` | string | No | Schema version (default: "2.0") |
| `skill.description` | string | No | Brief skill description |
| `skill.capability_count` | int | No | Number of capabilities |
| `skill.capabilities` | string | No | Comma-separated capability IDs |
| `skill.constraints` | string | No | Comma-separated constraints |
| `skill.source_path` | string | No | Path to skill directory |
| `skill.created_at` | string | No | ISO 8601 timestamp |
| `skill.updated_at` | string | No | ISO 8601 timestamp |
| `skill.project_refs` | string | No | Comma-separated project IDs |

### Token Budget Attributes (Skill)

| Attribute | Type | Description |
|-----------|------|-------------|
| `skill.manifest_tokens` | int | Token cost of manifest alone |
| `skill.index_tokens` | int | Token cost of index |
| `skill.total_tokens` | int | Sum of all capability tokens |
| `skill.compressed_tokens` | int | Token cost after compression |

## Capability Attributes

Attributes on capability spans:

### Core Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `skill.id` | string | Yes | Parent skill identifier |
| `skill.version` | string | No | Skill schema version |
| `skill.type` | enum | No | Skill type (inherited) |
| `capability.id` | string | Yes | Unique capability identifier |
| `capability.name` | string | Yes | Human-readable name |
| `capability.category` | enum | Yes | Operation category |
| `capability.summary` | string | Yes | 1-2 sentence compressed description |
| `capability.triggers` | string | No | Comma-separated routing keywords |
| `capability.token_budget` | int | Yes | Full content token cost |
| `capability.summary_tokens` | int | No | Summary-only token cost |
| `capability.anti_patterns` | string | No | Comma-separated anti-patterns |

### Interoperability Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `capability.interop_human` | int | Human readability score (1-5) |
| `capability.interop_agent` | int | Agent parseability score (1-5) |
| `capability.audience` | enum | `agent` \| `human` \| `both` (derived from scores) |

**Audience Derivation Rules:**
- `interop_agent >= 4 && interop_human < 3` → `agent`
- `interop_human >= 4 && interop_agent < 3` → `human`
- Otherwise → `both`

### Confidence and Reliability Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `capability.confidence` | float | Confidence score (0.0-1.0) |
| `capability.success_rate` | float | Success rate from usage (calculated) |
| `capability.invocation_count` | int | Number of times invoked |

### Timestamp Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `capability.created_at` | string | ISO 8601 creation timestamp |
| `capability.updated_at` | string | ISO 8601 last update timestamp |
| `capability.expires_at` | string | ISO 8601 expiration timestamp (optional) |

### Version Evolution Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `capability.supersedes` | string | ID of capability this replaces |
| `capability.project_refs` | string | Comma-separated project IDs |

### Capability Categories

| Value | Description |
|-------|-------------|
| `transform` | Convert between formats |
| `generate` | Create new artifacts |
| `validate` | Check correctness |
| `audit` | Analyze efficiency/quality |
| `query` | Retrieve information |
| `action` | Execute operations |
| `analyze` | Deep investigation |

## Span Events

### Quick Actions (Skill Spans)

Quick actions are stored as events on skill spans:

```yaml
event:
  name: quick_action
  attributes:
    action.name: format_skill
    action.capability_id: transform_document
    action.description: Convert prose skill doc to agent-optimized format
```

### Evidence (Capability Spans)

Evidence references are stored as events on capability spans:

```yaml
event:
  name: evidence.added
  attributes:
    evidence.type: file | schema | template | protocol | doc | example | trace | capability
    evidence.ref: agent/capabilities/transform.yaml
    evidence.tokens: 400
    evidence.description: Full capability schema
    evidence.query: (optional) TraceQL query that found this
    evidence.timestamp: (optional) ISO 8601 when evidence was collected
```

### Lifecycle Events (Capability Spans)

Lifecycle events track capability registration and usage:

```yaml
# Emitted when capability is first registered
event:
  name: capability.registered
  attributes:
    registered_by: claude-code
    session_id: session-abc123
```

### Lifecycle Events (Lifecycle Spans)

Lifecycle spans track capability invocations:

```yaml
# capability.invoked span
span:
  name: capability.invoked
  attributes:
    skill.id: llm-formatter
    capability.id: transform_document
    lifecycle.event: invoked
    lifecycle.timestamp: 2024-01-14T10:00:00Z
    handoff.id: (optional) Link to triggering handoff
    input.source_document: /path/to/skill.md

# capability.succeeded span
span:
  name: capability.succeeded
  attributes:
    skill.id: llm-formatter
    capability.id: transform_document
    lifecycle.event: succeeded
    lifecycle.timestamp: 2024-01-14T10:00:05Z
    lifecycle.duration_ms: 5000
    output.token_savings: 87%

# capability.failed span
span:
  name: capability.failed
  attributes:
    skill.id: llm-formatter
    capability.id: transform_document
    lifecycle.event: failed
    error.message: Invalid YAML syntax
```

### Inputs (Capability Spans)

Input parameters are stored as events:

```yaml
event:
  name: input.defined
  attributes:
    input.name: source_document
    input.type: string
    input.required: true
    input.description: Path to document to transform
    input.default: (optional)
    input.enum_values: (optional, comma-separated)
```

### Outputs (Capability Spans)

Output fields are stored as events:

```yaml
event:
  name: output.defined
  attributes:
    output.name: manifest
    output.type: object
    output.description: Generated MANIFEST.yaml content
```

## TraceQL Query Examples

### Find All Skills

```traceql
{ name =~ "skill:.*" }
```

### Find Capabilities by Trigger

```traceql
{ capability.triggers =~ ".*format.*" }
```

### Find Capabilities by Category

```traceql
{ capability.category = "transform" }
```

### Find Capabilities Under Token Budget

```traceql
{ capability.token_budget < 500 }
```

### Find All Capabilities for a Skill

```traceql
{ skill.id = "llm-formatter" && name =~ "capability:.*" }
```

### Find Agent-Friendly Capabilities

```traceql
{ capability.interop_agent >= 4 }
```

### Find Utility Skills

```traceql
{ name =~ "skill:.*" && skill.type = "utility" }
```

### Find Agent-Optimized Capabilities (New)

```traceql
{ capability.audience = "agent" }
```

### Find High-Confidence Capabilities (New)

```traceql
{ capability.confidence >= 0.9 }
```

### Find Capabilities by Project (New)

```traceql
{ capability.project_refs =~ ".*checkout.*" }
```

### Find Capabilities Registered by Agent (New)

```traceql
# Legacy attribute
{ agent.id = "claude-code" && name =~ "capability:.*" }

# OTel GenAI attribute (v2.0+)
{ span.gen_ai.agent.id = "claude-code" && name =~ "capability:.*" }
```

### Find Capabilities in Session (New)

```traceql
# Legacy attribute
{ agent.session_id = "session-abc123" }

# OTel GenAI attribute (v2.0+)
{ span.gen_ai.conversation.id = "session-abc123" }
```

### Find Capabilities by AI Provider (v2.0+)

```traceql
{ span.gen_ai.system = "anthropic" && name =~ "capability:.*" }
```

### Find Recently Updated Capabilities (New)

```traceql
{ capability.updated_at > "2024-01-01" }
```

### Trace Handoff to Capability Invocation (New)

```traceql
{ handoff.id = "handoff-123" } >> { name =~ "capability.invoked" }
```

### Find Successful Invocations (New)

```traceql
{ name = "capability.succeeded" && skill.id = "llm-formatter" }
```

### Find Failed Invocations with Errors (New)

```traceql
{ name = "capability.failed" && error.message != "" }
```

## Relationship to Other Conventions

### Insight Conventions

Skills integrate with the insight system in two ways:

**1. Discovery Insights (Automatic)**

When querying capabilities with `SkillCapabilityQuerier`, discovery insights are automatically emitted:

```yaml
insight:
  type: discovery
  summary: "Found 3 capabilities matching trigger 'format': llm-formatter:transform_document, ..."
  confidence: 0.95
  evidence:
    - type: capability
      ref: llm-formatter:transform_document
      description: "Converts prose to progressive-disclosure format..."
      query: "{ capability.triggers =~ \".*format.*\" }"
      timestamp: "2024-01-14T10:00:00Z"
```

**2. Usage Insights (Manual)**

Agents can emit insights about capability usage:

```yaml
insight:
  type: recommendation
  summary: "Use llm-formatter:transform_document for skill formatting tasks"
  confidence: 0.9
  evidence:
    - type: capability
      ref: llm-formatter:transform_document
```

### Handoff Convention

Capabilities are referenced in handoff messages with span linking:

```yaml
handoff_message:
  from_agent: orchestrator
  to_agent: llm-formatter
  capability_id: transform_document  # Matches capability.id attribute
  task: Format skill documentation

# The handoff.id is captured in lifecycle spans:
lifecycle_span:
  name: capability.invoked
  attributes:
    handoff.id: handoff-123  # Links back to handoff
    skill.id: llm-formatter
    capability.id: transform_document
```

This enables TraceQL queries like:
```traceql
{ handoff.id = "handoff-123" } >> { name =~ "capability.*" }
```

## Token Budget Guidelines

| Content Type | Typical Tokens | Max Tokens |
|--------------|----------------|------------|
| Skill manifest | 150 | 300 |
| Capability (full) | 300-500 | 800 |
| Capability (summary) | 30-80 | 150 |
| Routing table | 50-100 | 200 |
| Quick action | 20-30 | 50 |

### Compression Targets

| Metric | Target |
|--------|--------|
| Summary compression ratio | 80-90% |
| Typical skill total | < 5,000 tokens |
| Maximum skill total | 25,000 tokens |

## CLI Commands

```bash
# Emit skill to Tempo (with agent attribution)
contextcore skill emit --path /path/to/skill --agent-id claude-code --session-id session-123

# Query capabilities (with new filters)
contextcore skill query --trigger "format"
contextcore skill query --category transform --budget 500
contextcore skill query --audience agent --min-confidence 0.9
contextcore skill query --project-ref checkout-service

# List all skills
contextcore skill list

# Get routing table
contextcore skill routing --skill-id llm-formatter

# Analyze compression
contextcore skill compress --path /path/to/skill --target-tokens 25000
```

## Derived Metrics (PromQL)

Lifecycle spans enable deriving usage metrics:

```promql
# Most used capabilities
topk(10, sum by (capability_id) (
  trace_span_metrics_calls_total{span_name=~"capability.invoked"}
))

# Capability success rate
sum by (capability_id) (trace_span_metrics_calls_total{span_name="capability.succeeded"})
/
sum by (capability_id) (trace_span_metrics_calls_total{span_name="capability.invoked"})

# Average invocation duration
avg by (capability_id) (
  trace_span_metrics_duration_milliseconds_sum{span_name="capability.succeeded"}
  / trace_span_metrics_duration_milliseconds_count{span_name="capability.succeeded"}
)

# Error rate by skill
sum by (skill_id) (trace_span_metrics_calls_total{span_name="capability.failed"})
/
sum by (skill_id) (trace_span_metrics_calls_total{span_name="capability.invoked"})
```

## Integration with Grafana

### Explore View

Query capabilities in Grafana Explore using TraceQL:

1. Select Tempo data source
2. Enter TraceQL query (e.g., `{ skill.id = "llm-formatter" }`)
3. View capability spans with attributes

### Dashboard Panels

Create panels for:
- Skill inventory (count by type)
- Token budget distribution (histogram)
- Capability categories (pie chart)
- Recent capability emissions (table)

## Best Practices

1. **Use semantic IDs**: Capability IDs should be `snake_case` verbs (e.g., `transform_document`, not `document_transformer`)

2. **Compress aggressively**: Summaries should be 1-2 sentences max

3. **Link, don't embed**: Use evidence references instead of inline content

4. **Track token budgets**: Always annotate files with `# Token budget: ~N tokens`

5. **Test interoperability**: Aim for Human 4/5, Agent 5/5 scores

## Knowledge Document Extension

When using the `contextcore knowledge` commands to convert markdown SKILL.md files into queryable telemetry, additional attributes are set on spans.

### Knowledge-Specific Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `knowledge.category` | enum | Content classification: `infrastructure`, `workflow`, `sdk`, `reference`, `security`, `configuration` |
| `knowledge.source_file` | string | Path to source markdown file |
| `knowledge.total_lines` | int | Total lines in source document |
| `knowledge.section_count` | int | Number of H2 sections |
| `knowledge.subsection_count` | int | Number of H3 subsections extracted as capabilities |
| `knowledge.has_frontmatter` | bool | Document has YAML frontmatter |

### Knowledge Capability Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `capability.source_section` | string | H2 heading from source document |
| `capability.source_subsection` | string | H3 heading if this is a subsection capability |
| `capability.line_range` | string | Start-end lines in source (e.g., "50-120") |
| `capability.has_code` | bool | Contains code examples |
| `capability.has_tables` | bool | Contains tables |
| `capability.code_block_count` | int | Number of code blocks |
| `capability.tools` | string | Comma-separated CLI commands (contextcore, startd8, etc.) |
| `capability.ports` | string | Comma-separated network ports |
| `capability.env_vars` | string | Comma-separated environment variables |
| `capability.paths` | string | Comma-separated file paths |
| `capability.related_skills` | string | Comma-separated skill references |

### Knowledge Category Values

| Category | Description |
|----------|-------------|
| `infrastructure` | Ports, services, observability stack (Harbor Manifest, Grafana, etc.) |
| `workflow` | CI/CD, auto-fix, session management |
| `sdk` | Programmatic APIs (StartD8, ContextCore) |
| `reference` | Quick references, skills catalog, lessons learned |
| `security` | Secrets management, credentials, authentication |
| `configuration` | Settings, hooks, default behaviors |

### TraceQL Query Examples (Knowledge)

```traceql
# All knowledge capabilities for dev-tour-guide
{ skill.id = "dev-tour-guide" && name =~ "capability:.*" }

# Find by knowledge category
{ knowledge.category = "infrastructure" }

# Find capabilities with code examples
{ capability.has_code = true }

# Find capabilities mentioning a specific port
{ capability.ports =~ ".*3000.*" }

# Find by trigger keyword
{ capability.triggers =~ ".*grafana.*" }

# Find SDK documentation with high confidence
{ knowledge.category = "sdk" && capability.confidence >= 0.9 }

# Find capabilities mentioning CLI tools
{ capability.tools =~ ".*contextcore.*task.*" }

# Find capabilities referencing environment variables
{ capability.env_vars =~ ".*PROMETHEUS.*" }
```

### CLI Commands

```bash
# Parse and emit markdown to Tempo
contextcore knowledge emit --path ~/.claude/skills/dev-tour-guide

# Dry run to preview
contextcore knowledge emit --path ~/.claude/skills/dev-tour-guide --dry-run

# Output as JSON
contextcore knowledge emit --path ~/.claude/skills/dev-tour-guide --dry-run --format json

# Query knowledge capabilities
contextcore knowledge query --category infrastructure
contextcore knowledge query --trigger grafana
contextcore knowledge query --has-code
contextcore knowledge query --port 3000
```

### Hybrid Extraction Strategy

The knowledge parser uses a hybrid extraction strategy:

1. **All H2 sections** become capabilities
2. **H3 subsections** become separate capabilities if they meet any criteria:
   - In the subsection whitelist (e.g., "Async Agent Usage", "TUI", "Task Commands")
   - Have >50 lines of content
   - Contain multiple code blocks
   - Contain tables

This provides granular queryability for important content while avoiding over-fragmentation

## Value Capability Extension

The `contextcore value` commands extend knowledge capabilities with value-focused attributes for discovery through value propositions rather than technical features.

### Value-Specific Attributes

Value capabilities add the following span attributes:

#### Value Classification

| Attribute | Type | Description |
|-----------|------|-------------|
| `value.type` | enum | Value classification: `direct`, `indirect`, `ripple` |
| `value.persona` | enum | Primary target persona (use for exact primary match) |
| `value.personas` | string | Comma-separated list of all target personas (use regex for "any" match) |
| `value.channel` | enum | Primary distribution channel (use for exact primary match) |
| `value.channels` | string | Comma-separated list of all channels (use regex for "any" match) |

> **Note**: Use `value.persona` for exact primary persona match. Use `value.personas =~ ".*developer.*"` to find all capabilities targeting developers (even if developer is not the primary persona).

#### Value Messaging

| Attribute | Type | Description |
|-----------|------|-------------|
| `value.pain_point` | string | The problem or pain being solved |
| `value.pain_point_category` | string | Category of pain (time, cognitive_load, errors, coordination) |
| `value.benefit` | string | The benefit provided to the user |
| `value.benefit_metric` | string | Quantifiable metric (e.g., "50% less MTTR") |

#### Value Dimensions

| Attribute | Type | Description |
|-----------|------|-------------|
| `value.time_savings` | string | Time savings estimate (e.g., "2 hours/week") |
| `value.cognitive_load_reduction` | string | How it reduces cognitive load |
| `value.error_prevention` | string | What errors it prevents |

#### Creator Value (Audience of 1)

| Attribute | Type | Description |
|-----------|------|-------------|
| `value.creator_direct` | string | Direct value for creators (time, cognitive load) |
| `value.creator_indirect` | string | Indirect value for creators (skills, confidence) |
| `value.creator_ripple` | string | Ripple effects (family, friends, community) |

#### Cross-Linking

| Attribute | Type | Description |
|-----------|------|-------------|
| `value.related_skills` | string | Comma-separated technical skills this value relates to |
| `value.related_capabilities` | string | Comma-separated capability IDs this value describes |
| `value.keywords` | string | Comma-separated value-focused discovery keywords |

#### Pre-Generated Messaging

| Attribute | Type | Description |
|-----------|------|-------------|
| `value.slack_message` | string | Pre-adapted Slack message |
| `value.email_subject` | string | Pre-adapted email subject |
| `value.one_liner` | string | One-line value proposition |

### Value Type Values

| Value | Description |
|-------|-------------|
| `direct` | Immediate, tangible time/effort savings (time saved, cognitive load reduced) |
| `indirect` | Skills, confidence, portfolio growth over time |
| `ripple` | Benefits that extend to others (team, family, community) |

### Persona Values

| Value | Description |
|-------|-------------|
| `developer` | Software engineers, coders |
| `operator` | DevOps, SRE, platform engineers |
| `architect` | System designers, tech leads |
| `creator` | Content creators, makers |
| `designer` | UX/UI designers |
| `manager` | Engineering managers, team leads |
| `executive` | C-suite, directors |
| `product` | Product managers, owners |
| `security` | Security engineers, analysts |
| `data` | Data engineers, scientists |
| `any` | Universal applicability |

### Channel Values

| Value | Description |
|-------|-------------|
| `slack` | Team chat (concise, informal) |
| `email` | Formal communication |
| `docs` | Technical documentation |
| `in_app` | In-app messaging, tooltips |
| `social` | LinkedIn, Twitter |
| `blog` | Blog posts, articles |
| `press` | Press releases |
| `video` | YouTube, tutorials |
| `alert` | Automated notifications |
| `changelog` | Release notes |
| `meeting` | Presentations, demos |

### Knowledge Category Values (Extended)

The following value-focused categories were added to `knowledge.category`:

| Category | Description |
|----------|-------------|
| `value_proposition` | User benefits, problem-solution pairs |
| `messaging` | Channel-adapted content, templates |
| `persona` | Audience profiles, user contexts |
| `channel` | Distribution channels, format adaptations |

### TraceQL Query Examples (Value)

```traceql
# Find capabilities where developer is the PRIMARY persona
{ .value.persona = "developer" }

# Find ALL capabilities targeting developers (recommended)
{ .value.personas =~ ".*developer.*" }

# Find direct value capabilities
{ .value.type = "direct" }

# Find capabilities that reduce cognitive load
{ .value.cognitive_load_reduction != "" }

# Find capabilities with time savings
{ .value.time_savings != "" }

# Find capabilities related to dev-tour-guide
{ .value.related_skills =~ ".*dev-tour-guide.*" }

# Find capabilities mentioning "time" in pain point
{ .value.pain_point =~ ".*time.*" }

# Cross-linked queries: find value for o11y skill
{ .value.related_skills =~ ".*o11y.*" && .value.type = "direct" }

# Find ALL capabilities for Slack channel (any position in list)
{ .value.channels =~ ".*slack.*" }

# Find creator-focused capabilities (Audience of 1)
{ .value.creator_direct != "" || .value.creator_ripple != "" }
```

### CLI Commands

```bash
# Parse and emit value-focused skill to Tempo
contextcore value emit --path ~/.claude/skills/capability-value-promoter

# Dry run to preview
contextcore value emit --path ~/.claude/skills/capability-value-promoter --dry-run

# Output as JSON
contextcore value emit --path ~/.claude/skills/capability-value-promoter --dry-run --format json

# Query value capabilities
contextcore value query --persona developer
contextcore value query --value-type direct
contextcore value query --channel slack
contextcore value query --related-skill dev-tour-guide
contextcore value query --pain-point time

# List available personas
contextcore value list-personas

# List available channels
contextcore value list-channels
```

### Integration with Knowledge Module

Value capabilities extend knowledge capabilities and integrate through:

1. **Cross-linking**: Value capabilities reference technical capabilities via `value.related_skills` and `value.related_capabilities`

2. **Shared categories**: `KnowledgeCategory` includes both technical categories (infrastructure, workflow, sdk) and value categories (value_proposition, messaging, persona, channel)

3. **Unified querying**: Both knowledge and value capabilities are queryable via TraceQL in Tempo

4. **Discovery flow**:
   ```
   User: "What helps developers save time?"

   TraceQL: { value.persona = "developer" && value.time_savings != "" }

   Result: Value capability with related_skills = "o11y,dev-tour-guide"

   Follow-up: { skill.id = "o11y" && name =~ "capability:.*" }

   Result: Technical capabilities from o11y skill
   ```
