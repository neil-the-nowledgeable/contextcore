# MCP and A2A Tools Documentation Audit

**Date:** 2026-02-18  
**Scope:** `docs/capability-index/mcp-tools.json` and `docs/capability-index/agent-card.json`  
**Source manifest:** `docs/capability-index/contextcore.agent.yaml`

## Summary

Both MCP tools and A2A discoverable tools are **properly documented** in the capability index. The two files share a 1:1 mapping of 34 agent-facing capabilities, with `mcp-tools.json` providing MCP-compatible tool definitions and `agent-card.json` providing A2A Agent Card skills for discovery.

---

## MCP Tools (`mcp-tools.json`)

### MCP Tools Status: Documented

- **34 tools** with full MCP-style definitions
- Each tool includes:
  - `name` (capability ID)
  - `description` (summary + anti-patterns)
  - `inputSchema` (JSON Schema)
  - `outputSchema` (optional)
  - `annotations` (manifest_id, category, maturity, confidence)

### MCP-Specific Tools

- **`contextcore.aos.mcp_emit`** (maturity: development) — Emit AOS-compliant protocols/MCP events for Model Context Protocol interactions (tools_list, tool_call, resource_read, prompt_get)

### Schema Alignment

- Uses JSON Schema 2020-12 (same as MCP, OpenAPI 3.1, OpenAI function calling)
- Schema defined in `src/contextcore/utils/capability_schemas/capability.schema.yaml`

### MCP Generation

- CLI: `contextcore capability-index generate-mcp`
- Output: `docs/capability-index/mcp-tools.json`
- Source: `capability_mcp_generator.py` — converts capabilities with `audiences: ["agent"]` from manifest

---

## A2A Discoverable Tools (`agent-card.json`)

### A2A Tools Status: Documented

- **34 skills** matching the MCP tools
- Each skill includes: `id`, `name`, `description`, `tags`, `maturity`, `inputModes`, `outputModes`

### A2A-Specific Tools

- **`contextcore.a2a.server`** (beta) — Expose ContextCore agent as A2A-compatible server with JSON-RPC and discovery
- **`contextcore.a2a.client`** (beta) — Communicate with remote A2A-compatible agents via JSON-RPC client
- **`contextcore.a2a.task_adapter`** (beta) — Bidirectional translation between A2A Task JSON and ContextCore Handoff
- **`contextcore.a2a.content_model`** (beta) — Unified Part/Message/Artifact content model compatible with A2A message format

### Handoff Tools (A2A-Related)

- **`contextcore.handoff.initiate`** — Start agent-to-agent task delegation with size constraints and expected output
- **`contextcore.handoff.receive`** — Poll for and process incoming handoffs as receiving agent
- **`contextcore.handoff.input_request`** — Request additional input from delegating agent during handoff execution

### A2A Discovery Endpoints

The ContextCore A2A server exposes:

- `GET /.well-known/agent.json` — A2A standard (Agent Card)
- `GET /.well-known/contextcore.json` — ContextCore extended discovery

Implemented in `src/contextcore/agent/a2a_server.py` and `src/contextcore/discovery/endpoint.py`.

### A2A Generation

- CLI: `contextcore capability-index generate-a2a`
- Output: `docs/capability-index/agent-card.json`
- Source: `capability_a2a_generator.py` — converts capabilities with `audiences: ["agent"]` from manifest

---

## Gaps Identified

### 1. Placeholder URL in Agent Card

```json
"url": "https://api.example.com/contextcore.agent"
```

The agent card uses a placeholder URL because `contextcore.agent.yaml` has no `a2a` section with a real URL. The generator defaults to `https://api.example.com/{manifest_id}` when `a2a.url` is absent.

### 2. Discovery Path Not Documented in Agent Card

The agent card itself does not describe that discovery is served at `/.well-known/agent.json`. This is documented in the codebase but not in the capability index artifacts.

### 3. Missing `a2a` Config in Manifest

`contextcore.agent.yaml` does not define an `a2a` section. The manifest schema supports:

```yaml
a2a:
  url: "https://..."           # Agent endpoint URL
  authentication:
    schemes: [bearer]
  provider:
    organization: force-multiplier-labs
    url: https://github.com/Force-Multiplier-Labs/contextcore
```

Without this, the agent card uses defaults and placeholder values.

---

## Recommendations

1. **Add `a2a` section to `contextcore.agent.yaml`** when deploying a real agent endpoint:

   ```yaml
   a2a:
     url: "https://api.example.com/contextcore.agent"  # or deployment URL
     authentication:
       schemes: [bearer]
     provider:
       organization: force-multiplier-labs
       url: https://github.com/Force-Multiplier-Labs/contextcore
   ```

2. **Document discovery path** in capability index or docs: add a short note that discovery is at `/.well-known/agent.json` (and optionally `/.well-known/contextcore.json`).

3. **Document MCP tool usage** in capability index or docs: add a short note on how `mcp-tools.json` is consumed (e.g., MCP server config, CLI tool generation).

---

## Cross-Reference: Tool Count

- **MCP tools** — 34 tools in mcp-tools.json, 34 skills in agent-card.json (1:1 mapping)
- **A2A tools** — 4 tools/skills: server, client, task_adapter, content_model
- **MCP protocol events** — 1 tool/skill: `contextcore.aos.mcp_emit` (development)
- **Discovery URL** — N/A in mcp-tools; placeholder in agent-card (add real URL in manifest `a2a` section)

---

## Related Files

- `src/contextcore/utils/capability_mcp_generator.py` — MCP tool generation
- `src/contextcore/utils/capability_a2a_generator.py` — A2A Agent Card generation
- `src/contextcore/utils/capability_schemas/manifest.schema.yaml` — A2A Agent Card alignment (lines 162–191)
- `src/contextcore/utils/capability_schemas/capability.schema.yaml` — MCP-compatible input/output schemas
- `src/contextcore/cli/capability_index.py` — CLI commands: `generate-mcp`, `generate-a2a`
