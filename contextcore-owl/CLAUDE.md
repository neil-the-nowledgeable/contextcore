# CLAUDE.md - contextcore-owl

This file provides guidance to Claude Code for the contextcore-owl expansion pack.

## Project Context

**Package**: contextcore-owl (Gookooko'oo - Owl)
**Purpose**: Unified Grafana plugin package for ContextCore
**Status**: Development

## Tech Stack

- **Plugins**: TypeScript, React, @grafana/ui, @grafana/data, @grafana/runtime
- **Build**: npm workspaces, @grafana/create-plugin
- **Python**: Scaffold script using contextcore-beaver for LLM generation
- **Dev Environment**: Docker Compose with Grafana and mock Rabbit API

## Project Structure

```
contextcore-owl/
├── package.json              # Monorepo root (npm workspaces)
├── pyproject.toml            # Python package
├── plugins/
│   ├── contextcore-chat-panel/
│   ├── contextcore-workflow-panel/
│   └── contextcore-datasource/
├── scripts/
│   └── scaffold_plugin.py
├── grafana/plugins/          # Built plugins
├── docker/
│   ├── docker-compose.yml
│   ├── provisioning/
│   └── mock/
└── docs/
```

## Commands

```bash
# Install dependencies
npm install

# Build all plugins
npm run build

# Development with hot reload
npm run dev

# Scaffold new plugin (requires contextcore-beaver)
python scripts/scaffold_plugin.py --type panel --name my-plugin
```

## Kind Deployment

Plugins are deployed via Kind cluster host mounts. After building:

```bash
# Build plugins (output to grafana/plugins/)
npm run build

# Copy to legacy path (Kind mounts from contextcore-grafana/)
cp -r grafana/plugins/* ../contextcore-grafana/grafana/plugins/

# Restart Grafana pod to reload plugins
kubectl -n observability rollout restart deployment/grafana

# View Grafana at http://localhost:3000 (admin/admin)
```

**Kind cluster mounts** (defined in `/Users/neilyashinsky/Documents/Deploy/kind-cluster.yaml`):
- Host: `contextcore-grafana/grafana/plugins/*` → Container: `/plugins/contextcore/*`
- Grafana deployment uses hostPath volumes to mount from `/plugins/contextcore/*`
- **Note**: Kind config still references `contextcore-grafana/` (legacy name before rename to `contextcore-owl`)

### Known Issue: Docker Desktop File Sync

Docker Desktop's file sharing to Kind nodes can become stale. If plugin changes don't appear after rebuild:

**Symptoms:**
- CORS errors or 404s from old API endpoints
- Plugin behavior doesn't match source code
- `kubectl rollout restart` doesn't pick up changes

**Diagnosis:**
```bash
# Check what endpoints the deployed plugin uses
kubectl -n observability exec deployment/grafana -- \
  grep -o 'trigger\|dry-run\|workflow/execute' \
  /var/lib/grafana/plugins/contextcore-workflow-panel/module.js

# Compare to host file
grep -o 'trigger\|dry-run\|workflow/execute' \
  grafana/plugins/contextcore-workflow-panel/module.js
```

**Fix: Manual sync to Kind nodes**
```bash
# Find which node Grafana is running on
kubectl -n observability get pod -l app=grafana -o wide

# Copy updated plugin directly to Kind node (replace PLUGIN_NAME and NODE)
docker cp grafana/plugins/PLUGIN_NAME/module.js NODE:/plugins/contextcore/PLUGIN_NAME/module.js

# Example for workflow panel on worker2:
docker cp grafana/plugins/contextcore-workflow-panel/module.js \
  o11y-dev-worker2:/plugins/contextcore/contextcore-workflow-panel/module.js

# Copy to ALL nodes to prevent issues on pod reschedule
for node in o11y-dev-control-plane o11y-dev-worker o11y-dev-worker2; do
  docker cp grafana/plugins/contextcore-workflow-panel/module.js \
    $node:/plugins/contextcore/contextcore-workflow-panel/module.js 2>/dev/null || true
done

# Restart Grafana
kubectl -n observability delete pod -l app=grafana
```

### Full Plugin Deployment Workflow

```bash
# 1. Build plugin
cd plugins/contextcore-workflow-panel
npm run build

# 2. Copy to grafana/plugins (local dev)
cp -r dist/* ../../grafana/plugins/contextcore-workflow-panel/

# 3. Copy to legacy path (Kind mount source)
cp -r ../../grafana/plugins/contextcore-workflow-panel/* \
  ../../../contextcore-grafana/grafana/plugins/contextcore-workflow-panel/

# 4. Sync to Kind nodes (workaround for Docker Desktop file sync)
for node in o11y-dev-control-plane o11y-dev-worker o11y-dev-worker2; do
  docker cp ../../grafana/plugins/contextcore-workflow-panel/module.js \
    $node:/plugins/contextcore/contextcore-workflow-panel/module.js 2>/dev/null || true
done

# 5. Restart Grafana
kubectl -n observability delete pod -l app=grafana
kubectl -n observability wait --for=condition=ready pod -l app=grafana --timeout=120s

# 6. Verify deployment
kubectl -n observability exec deployment/grafana -- \
  grep -c 'trigger' /var/lib/grafana/plugins/contextcore-workflow-panel/module.js
# Should show: 3 (for workflow panel using /trigger endpoint)
```

## Plugin Development Patterns

### Panel Plugin Structure

```typescript
// module.ts
import { PanelPlugin } from '@grafana/data';
import { MyPanel } from './components/MyPanel';
import { MyPanelOptions } from './types';

export const plugin = new PanelPlugin<MyPanelOptions>(MyPanel)
  .setPanelOptions((builder) => {
    builder.addTextInput({
      path: 'apiUrl',
      name: 'API URL',
      defaultValue: 'http://localhost:8080',
    });
  });
```

### Template Variables

```typescript
import { getTemplateSrv } from '@grafana/runtime';

const templateSrv = getTemplateSrv();
const projectId = templateSrv.replace('${project}');
```

### HTTP Requests

For panel plugins, use direct fetch() with CORS enabled on the API:

```typescript
const response = await fetch(`${options.apiUrl}/endpoint`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
});
```

For datasource plugins, use Grafana's route proxy (CORS-free):

```typescript
// plugin.json routes
"routes": [
  { "path": "api/*", "url": "{{ .JsonData.apiUrl }}" }
]

// datasource.ts
const response = await getBackendSrv().fetch({
  url: '/api/plugins/contextcore-datasource/resources/api/endpoint',
  method: 'POST',
});
```

## Key Files

| File | Purpose |
|------|---------|
| `plugins/*/src/module.ts` | Plugin entry point |
| `plugins/*/src/plugin.json` | Plugin manifest |
| `plugins/*/src/types.ts` | TypeScript interfaces |
| `plugins/*/src/components/*.tsx` | React components |

## Testing

```bash
# Run tests
npm test

# Test with mock API
npm run docker:up
# Open http://localhost:3001 (Grafana dev instance)
```

## Ports

| Service | Port | Description |
|---------|------|-------------|
| Grafana (dev) | 3001 | Plugin development |
| Rabbit Mock | 8080 | Mock Rabbit API |

## Troubleshooting

### CORS Errors from Panel Plugins

**Symptom:** Browser console shows `CORS policy: Response to preflight request doesn't pass access control check`

**Causes:**
1. Backend API doesn't have CORS enabled
2. Plugin is calling wrong endpoint (outdated build)
3. API server isn't running

**Fixes:**
1. Ensure backend has CORS enabled (Rabbit uses `flask_cors`)
2. Rebuild and redeploy plugin (see "Full Plugin Deployment Workflow" above)
3. Verify API is running: `curl http://localhost:8082/health`

### Plugin Changes Not Taking Effect

**Symptom:** Code changes in `.tsx` files don't appear in Grafana

**Checklist:**
1. Did you rebuild? `npm run build`
2. Did you copy to grafana/plugins? `cp -r dist/* ../../grafana/plugins/PLUGIN/`
3. Did you sync to Kind nodes? (See "Manual sync to Kind nodes" above)
4. Did you restart Grafana? `kubectl -n observability delete pod -l app=grafana`

### Workflow Panel Shows Old API Endpoints

The workflow panel was refactored from direct endpoints (`/workflow/dry-run`) to use Rabbit's trigger pattern (`/trigger` with action names). If you see errors calling old endpoints:

```bash
# Verify which endpoints the deployed plugin uses
kubectl -n observability exec deployment/grafana -- \
  grep -o '/trigger\|/workflow/dry-run\|/workflow/execute' \
  /var/lib/grafana/plugins/contextcore-workflow-panel/module.js

# Expected (new): /trigger (appears 3 times)
# Outdated (old): /workflow/dry-run, /workflow/execute
```

If outdated, follow the "Full Plugin Deployment Workflow" to rebuild and sync.

## Related Documentation

- [Grafana Plugin Development](https://grafana.com/developers/plugin-tools/)
- [@grafana/ui Components](https://developers.grafana.com/ui/latest/)
- [ContextCore Expansion Packs](../docs/EXPANSION_PACKS.md)
- [Naming Convention](../docs/NAMING_CONVENTION.md)
