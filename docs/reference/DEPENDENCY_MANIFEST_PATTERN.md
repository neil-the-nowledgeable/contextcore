# Dependency Manifest Pattern

## Overview

This document establishes a pattern for tracking external dependencies (Grafana plugins, datasources, external APIs) that are defined during design/development but must be present at deploy time.

**Core Principle**: Dependencies should be explicitly declared, version-pinned, and validated at multiple checkpoints—not discovered at runtime.

## The Anti-Pattern: Implicit Dependencies

```
❌ ANTI-PATTERN: Scattered Implicit Dependencies

dashboard.json:
  "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "rabbit-api"}
  // Nothing tracks that this plugin is required

docker-compose.yaml:
  # GF_INSTALL_PLUGINS not updated
  # Deployment fails silently or with cryptic error

Result: "It works on my machine" → Production failure
```

### Why This Fails

1. **No single source of truth** for what's required
2. **No validation** between design and deploy
3. **Discovery at worst time** (production deployment)
4. **Manual synchronization** across files (error-prone)
5. **No versioning** of plugin requirements

## The Pattern: Explicit Dependency Manifests

### 1. Declare Dependencies Where They're Used

Each component that introduces external dependencies declares them in a manifest:

```yaml
# grafana/provisioning/dashboards/dependencies.yaml
# Auto-generated from dashboard JSON files + manual additions

apiVersion: contextcore.io/v1
kind: DependencyManifest
metadata:
  name: grafana-dashboards
  component: grafana

spec:
  # Grafana plugins required by dashboards
  plugins:
    - id: yesoreyeram-infinity-datasource
      version: ">=2.0.0"
      reason: "REST API queries for Rabbit/Beaver dashboards"
      usedBy:
        - beaver-lead-contractor-progress.json
        - workflow.json

    - id: grafana-polystat-panel
      version: ">=2.0.0"
      reason: "Status grid visualization"
      usedBy:
        - portfolio.json
      optional: true  # Dashboard degrades gracefully without it

  # Datasources that must be configured
  datasources:
    - uid: tempo
      type: tempo
      required: true

    - uid: loki
      type: loki
      required: true

    - uid: mimir
      type: prometheus
      required: true

    - uid: rabbit-api
      type: yesoreyeram-infinity-datasource
      required: false  # Only for Beaver/Fox dashboards
      config:
        # Expected configuration for validation
        url_pattern: "http://*/api/*"

  # External services dashboards expect to query
  services:
    - name: rabbit-api
      endpoint: "http://host.docker.internal:8085/api/"
      healthcheck: "/health"
      required: false
      usedBy:
        - beaver-lead-contractor-progress.json
        - workflow.json
```

### 2. Aggregate at Project Level

The project-level manifest aggregates all component manifests:

```yaml
# .contextcore.yaml (additions)

dependencies:
  # Reference component manifests
  manifests:
    - grafana/provisioning/dashboards/dependencies.yaml
    - k8s/dependencies.yaml

  # Direct declarations for simple cases
  grafana:
    plugins:
      - id: yesoreyeram-infinity-datasource
        version: ">=2.0.0"
        reason: "Rabbit API integration"

  external:
    services:
      - name: rabbit-api
        required: false
        description: "ContextCore Rabbit for workflow management"
```

### 3. Validate at Multiple Checkpoints

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Dependency Validation Checkpoints                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  DESIGN TIME              BUILD TIME              DEPLOY TIME        │
│  ────────────             ──────────              ───────────        │
│                                                                      │
│  Dashboard created  ──►  CI validates    ──►   Runtime check        │
│  with plugin ref        manifest exists       plugins installed     │
│                                                                      │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐       │
│  │ Pre-commit   │      │ CI Pipeline  │      │ Startup      │       │
│  │ hook scans   │      │ validates    │      │ verification │       │
│  │ for new deps │      │ completeness │      │ with telemetry│      │
│  └──────────────┘      └──────────────┘      └──────────────┘       │
│         │                     │                     │                │
│         ▼                     ▼                     ▼                │
│  "New plugin ref      "Missing manifest     "Plugin not found       │
│   detected, update     entry for plugin"     - degraded mode"       │
│   dependencies.yaml"                                                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation

### Checkpoint 1: Design Time (Pre-commit Hook)

```bash
#!/bin/bash
# .claude/hooks/pre-commit/check-dependencies.sh

# Scan dashboard JSON files for datasource types
for dashboard in grafana/provisioning/dashboards/json/*.json; do
  # Extract unique datasource types
  types=$(jq -r '.. | .datasource?.type? // empty' "$dashboard" | sort -u)

  for type in $types; do
    if ! grep -q "id: $type" grafana/provisioning/dashboards/dependencies.yaml; then
      echo "ERROR: Dashboard $(basename $dashboard) uses '$type' but it's not in dependencies.yaml"
      exit 1
    fi
  done
done
```

### Checkpoint 2: Build Time (CI Validation)

```python
# scripts/validate_dependencies.py
"""Validate all dependency manifests are complete and consistent."""

import yaml
import json
from pathlib import Path

def validate_dashboard_dependencies():
    """Ensure all dashboard plugin references are declared."""

    # Load manifest
    manifest_path = Path("grafana/provisioning/dashboards/dependencies.yaml")
    if not manifest_path.exists():
        raise ValueError("Missing dependencies.yaml - run 'contextcore deps generate'")

    manifest = yaml.safe_load(manifest_path.read_text())
    declared_plugins = {p["id"] for p in manifest["spec"].get("plugins", [])}

    # Scan dashboards
    for dashboard_path in Path("grafana/provisioning/dashboards/json").glob("*.json"):
        dashboard = json.loads(dashboard_path.read_text())

        # Find all datasource type references
        used_plugins = extract_datasource_types(dashboard)

        for plugin in used_plugins:
            if plugin not in declared_plugins and plugin not in BUILTIN_TYPES:
                raise ValueError(
                    f"Dashboard {dashboard_path.name} uses undeclared plugin: {plugin}\n"
                    f"Add to grafana/provisioning/dashboards/dependencies.yaml"
                )

BUILTIN_TYPES = {"prometheus", "loki", "tempo", "elasticsearch", "influxdb"}
```

### Checkpoint 3: Deploy Time (Runtime Verification)

```python
# src/contextcore/install/plugin_verifier.py
"""Verify Grafana plugins are installed at runtime."""

from contextcore.install.requirements import Requirement, RequirementCategory

class GrafanaPluginRequirement(Requirement):
    """Verify a Grafana plugin is installed."""

    category = RequirementCategory.INFRASTRUCTURE

    def __init__(self, plugin_id: str, min_version: str = None, optional: bool = False):
        self.plugin_id = plugin_id
        self.min_version = min_version
        self.optional = optional

    @property
    def name(self) -> str:
        return f"grafana-plugin:{self.plugin_id}"

    @property
    def description(self) -> str:
        return f"Grafana plugin '{self.plugin_id}' is installed"

    async def verify(self) -> bool:
        """Check if plugin is installed via Grafana API."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.grafana_url}/api/plugins/{self.plugin_id}/settings",
                    auth=(self.grafana_user, self.grafana_password)
                )

                if resp.status_code == 404:
                    return False

                if self.min_version:
                    data = resp.json()
                    installed = data.get("info", {}).get("version", "0.0.0")
                    return version_gte(installed, self.min_version)

                return resp.status_code == 200

        except Exception as e:
            self.error = str(e)
            return False

def load_plugin_requirements_from_manifest() -> list[GrafanaPluginRequirement]:
    """Load plugin requirements from dependency manifest."""
    manifest_path = Path("grafana/provisioning/dashboards/dependencies.yaml")
    if not manifest_path.exists():
        return []

    manifest = yaml.safe_load(manifest_path.read_text())

    return [
        GrafanaPluginRequirement(
            plugin_id=p["id"],
            min_version=p.get("version"),
            optional=p.get("optional", False)
        )
        for p in manifest["spec"].get("plugins", [])
    ]
```

### CLI Commands

```bash
# Generate/update dependency manifest from dashboard files
contextcore deps generate --component grafana

# Validate all manifests are complete
contextcore deps validate

# Check runtime dependencies
contextcore deps check --environment production

# Show dependency tree
contextcore deps tree
```

## Integration with Build/Deploy

### Docker Compose

```yaml
# docker-compose.yaml
services:
  grafana:
    image: grafana/grafana:latest
    environment:
      # Auto-generated from dependencies.yaml
      GF_INSTALL_PLUGINS: >-
        yesoreyeram-infinity-datasource
    # Or use provisioning
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning
```

### Makefile Integration

```makefile
# Makefile

.PHONY: deps-validate deps-generate build

# Validate dependencies before build
build: deps-validate
	docker-compose build

deps-validate:
	@echo "Validating dependency manifests..."
	python3 scripts/validate_dependencies.py
	@echo "✓ All dependencies declared"

deps-generate:
	@echo "Scanning for dependencies..."
	contextcore deps generate --all
	@echo "Updated dependency manifests"

# Generate GF_INSTALL_PLUGINS from manifest
grafana-plugins:
	@yq '.spec.plugins[].id' grafana/provisioning/dashboards/dependencies.yaml | tr '\n' ','
```

### GitHub Actions

```yaml
# .github/workflows/ci.yaml
jobs:
  validate-dependencies:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Validate dependency manifests
        run: |
          python3 scripts/validate_dependencies.py

      - name: Check for undeclared dependencies
        run: |
          # Scan for new plugin references not in manifest
          ./scripts/scan-new-dependencies.sh
```

## Telemetry Integration

Emit dependency status as part of installation verification:

```python
# Emitted during contextcore install verify
{
    "name": "contextcore.install.dependency",
    "attributes": {
        "dependency.type": "grafana_plugin",
        "dependency.id": "yesoreyeram-infinity-datasource",
        "dependency.version.required": ">=2.0.0",
        "dependency.version.installed": "2.1.0",
        "dependency.status": "satisfied",  # or "missing", "version_mismatch"
        "dependency.optional": false,
        "dependency.used_by": ["beaver-lead-contractor-progress.json"]
    }
}
```

## Summary: Pattern vs Anti-Pattern

| Aspect | Anti-Pattern | Pattern |
|--------|--------------|---------|
| **Declaration** | Implicit in files | Explicit manifest |
| **Location** | Scattered | Centralized + component-level |
| **Validation** | Deploy-time only | Design → Build → Deploy |
| **Versioning** | None | Pinned with ranges |
| **Discovery** | Runtime errors | Pre-commit warnings |
| **Automation** | Manual sync | Generated + validated |
| **Telemetry** | None | Status emitted as spans |

## Migration Path

1. **Immediate**: Create `grafana/provisioning/dashboards/dependencies.yaml`
2. **Short-term**: Add CI validation step
3. **Medium-term**: Add pre-commit hook for new dashboard creation
4. **Long-term**: Auto-generate manifest from dashboard scans

## Related Documents

- [Semantic Conventions](semantic-conventions.md) - Telemetry attribute naming
- [Installation Verification](../src/contextcore/install/README.md) - Runtime verification
- [CLAUDE.md](../CLAUDE.md) - Project conventions
