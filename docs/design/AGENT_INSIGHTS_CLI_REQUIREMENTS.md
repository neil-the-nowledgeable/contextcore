# Agent Insights CLI Requirements

Purpose: define the behavioral requirements for `contextcore insight list` and `contextcore insight search` — the CLI commands that surface agent-generated insights stored in Tempo/local storage without requiring Grafana.

This document is intentionally living guidance. Update it as the commands evolve.

---

## Vision

Agent insights (decisions, recommendations, blockers, discoveries, lessons learned) are already stored as OTel spans in Tempo and queryable via the `InsightQuerier` class (`src/contextcore/agent/insights.py`). A Grafana dashboard for agent insights was completed 2026-02-04 (roadmap item `visibility.agent_insights`, phase 1 of 2). This CLI extension completes phase 2: enabling agents and developers to discover insights from the terminal without opening Grafana.

**Core principle**: Insights should be accessible wherever agents operate — in CI pipelines, in terminal sessions, and in other agents' context windows — not just in a browser dashboard.

---

## Pipeline Placement

These commands are independent of the export pipeline. They read from the observability backend (Tempo) or local storage, not from export output.

| Command | Data source | Use case |
|---------|------------|----------|
| `contextcore insight list` | Tempo or local JSON | Browse recent insights for a project |
| `contextcore insight search` | Tempo or local JSON | Find specific insights by type, agent, confidence |

---

## Existing Infrastructure

The `InsightQuerier` class already provides all query capabilities:

| Capability | Method | Parameters |
|-----------|--------|-----------|
| Query by project | `query(project_id=...)` | Project ID filter |
| Query by type | `query(insight_type=...)` | `InsightType` enum: analysis, recommendation, decision, question, blocker, discovery, risk, progress, lesson |
| Query by agent | `query(agent_id=...)` | Agent ID filter |
| Query by audience | `query(audience=...)` | `InsightAudience` enum: agent, human, both |
| Query by confidence | `query(min_confidence=...)` | Float threshold (0.0–1.0) |
| Query by time range | `query(time_range=...)` | Duration string: "1h", "24h", "7d", "30d" |
| Query by file | `query(applies_to=...)` | File path partial match |
| Query by category | `query(category=...)` | Category string |
| Result limit | `query(limit=...)` | Integer cap |

The querier supports dual backends:
- **Tempo**: TraceQL queries via HTTP API (production)
- **Local JSON**: File-based storage fallback (development, offline)

---

## `contextcore insight list`

### Purpose

List recent insights for a project, ordered by recency. The default "what's new" view for a developer or agent joining a project session.

### Functional Requirements

1. **Default listing**
   - Must list insights for the specified project, ordered by most recent first.
   - Must display: timestamp, type, agent_id, summary (truncated to 120 chars), confidence.
   - Must default to `--time-range 24h` and `--limit 20`.

2. **Filtering**
   - Must support `--type` to filter by insight type (e.g., `--type decision`).
   - Must support `--agent` to filter by agent ID.
   - Must support `--audience` to filter by audience (agent, human, both).
   - Must support `--min-confidence` to filter by minimum confidence score.
   - Must support `--time-range` for time window (e.g., "1h", "7d", "30d").
   - Must support `--limit` to cap result count.

3. **Output formats**
   - Must support `--format text` (default): human-readable table with columns aligned.
   - Must support `--format json`: JSON array of insight objects for machine consumption.
   - Must support `--format detail`: full insight details including evidence, context, and applies_to.

4. **Verbose mode**
   - With `--verbose` / `-v`, must show full summary (not truncated) and evidence items.

### CLI Surface

```
contextcore insight list
  --project / -p        (required)   Project ID to query
  --type / -t           (optional)   Filter by insight type
  --agent / -a          (optional)   Filter by agent ID
  --audience            (optional)   Filter by audience: agent | human | both
  --min-confidence      (optional)   Minimum confidence score (0.0-1.0)
  --time-range          (default: 24h)  Time range: 1h | 24h | 7d | 30d
  --limit / -n          (default: 20)   Maximum results
  --format / -f         (default: text)  Output format: text | json | detail
  --verbose / -v        (flag)       Show full details
```

---

## `contextcore insight search`

### Purpose

Search for specific insights across projects using keyword or structured filters. More targeted than `list` — answers "what did agents decide about X?" or "are there blockers in project Y?"

### Functional Requirements

1. **Keyword search**
   - Must support a positional `query` argument for keyword search in insight summaries.
   - Keyword matching should be case-insensitive substring match.

2. **Cross-project search**
   - Must support `--project` to scope to a single project.
   - When `--project` is omitted, must search across all projects (subject to Tempo query limits).

3. **File-scoped search**
   - Must support `--applies-to` to find insights about a specific file path (partial match).
   - Example: `contextcore insight search --applies-to tracker.py` finds insights mentioning tracker.py.

4. **Category search**
   - Must support `--category` to filter by insight category (e.g., "testing", "architecture").

5. **Output**
   - Must use the same output format options as `insight list` (`text`, `json`, `detail`).
   - Must highlight matching keywords in `text` output mode.

### CLI Surface

```
contextcore insight search [query]
  query                 (optional)   Keyword to search in summaries
  --project / -p        (optional)   Scope to project
  --type / -t           (optional)   Filter by insight type
  --agent / -a          (optional)   Filter by agent ID
  --applies-to          (optional)   Filter by file path (partial match)
  --category            (optional)   Filter by category
  --min-confidence      (optional)   Minimum confidence score
  --time-range          (default: 7d)   Time range
  --limit / -n          (default: 50)   Maximum results
  --format / -f         (default: text)  Output format: text | json | detail
```

---

## Non-Functional Requirements

1. **Offline operation**: Must work without Tempo by falling back to local JSON storage.
2. **Read-only**: Must not modify any stored insights.
3. **Performance**: Must return results in under 3 seconds for typical Tempo queries.
4. **Error handling**: Must display clear error messages when Tempo is unreachable, not fail silently.
5. **Backward compatibility**: Must work with insights emitted by any version of `InsightEmitter`.

---

## Invariants

1. `insight list --format json` output is valid JSON and parseable by `jq`.
2. `insight search` with no filters returns the same results as `insight list` with the same time range.
3. All filters are composable — combining `--type`, `--agent`, and `--min-confidence` applies all three.
4. Result ordering is always by recency (most recent first).

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (results found or empty result set) |
| 1 | Error (Tempo unreachable AND no local fallback, invalid arguments) |

---

## Implementation Notes

- Create `src/contextcore/cli/insight.py` with a Click group registered under the main CLI.
- Instantiate `InsightQuerier` with standard environment variables (`TEMPO_URL`).
- Use `Insight` dataclass fields for column mapping in text output.
- Register the `insight` group in `src/contextcore/cli/core.py`.

---

## Relationship to Other Commands

| Command | Relationship |
|---------|-------------|
| `insight list` / `insight search` | These commands (read insights) |
| Agent `InsightEmitter` | Upstream — writes the insights these commands read |
| Grafana agent insights dashboard | Parallel — same data, different interface |
| `contextcore contract a2a-diagnose` | Complementary — diagnostic may reference agent insights |

---

## Related Docs

- `src/contextcore/agent/insights.py` — `InsightQuerier` and `InsightEmitter` implementation
- `docs/agent-communication-protocol.md` — Agent insight span protocol
- `docs/agent-semantic-conventions.md` — Insight attribute conventions
- `docs/design/contextcore-a2a-comms-design.md` — A2A architecture (Extension 3)
