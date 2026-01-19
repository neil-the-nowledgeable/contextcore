# Dashboard Installation Guide

ContextCore automatically provisions Grafana dashboards during installation. This guide covers installation options and troubleshooting.

## Prerequisites

- Grafana instance (8.0+ recommended)
- Grafana API access (service account or API key)
- Data sources configured:
  - **Tempo** (for task spans) - named `Tempo` or `tempo`
  - **Loki** (for task events) - named `Loki` or `loki`
  - **Prometheus/Mimir** (for metrics) - named `Prometheus`, `Mimir`, or `prometheus`

## Installation Methods

### 1. CLI Installation (Recommended)

```bash
# Auto-detect local Grafana (localhost:3000)
contextcore dashboards provision

# Specify Grafana URL
contextcore dashboards provision --grafana-url http://grafana.example.com:3000

# With authentication
contextcore dashboards provision \
  --grafana-url http://grafana.example.com:3000 \
  --grafana-token "glsa_xxxxx"

# Dry run (preview without applying)
contextcore dashboards provision --dry-run
```

### 2. Helm Chart Installation

When installing via Helm, dashboards are provisioned automatically:

```bash
helm install contextcore contextcore/contextcore \
  --set grafana.enabled=true \
  --set grafana.url=http://grafana:3000 \
  --set grafana.dashboards.enabled=true
```

To skip dashboard provisioning:

```bash
helm install contextcore contextcore/contextcore \
  --set grafana.dashboards.enabled=false
```

### 3. Manual Import

Import dashboard JSON files directly into Grafana:

1. Download dashboard JSON from releases or generate:
   ```bash
   contextcore dashboards export --output ./dashboards/
   ```

2. In Grafana UI: **Dashboards → Import → Upload JSON file**

3. Select data sources when prompted

## Provisioned Dashboards

| Dashboard | UID | Description |
|-----------|-----|-------------|
| Project Portfolio Overview | `contextcore-portfolio` | High-level view of all projects |
| Project Details | `contextcore-project-details` | Drill-down into single project |

## Configuration

### Environment Variables

```bash
# Grafana connection
GRAFANA_URL=http://localhost:3000
GRAFANA_API_KEY=glsa_xxxxx
GRAFANA_ORG_ID=1

# Dashboard options
CONTEXTCORE_DASHBOARD_FOLDER=ContextCore
CONTEXTCORE_DASHBOARD_REFRESH=30s
```

### Data Source Mapping

If your data sources have non-standard names, configure mapping:

```bash
contextcore dashboards provision \
  --tempo-datasource "My Tempo" \
  --loki-datasource "My Loki" \
  --prometheus-datasource "My Prometheus"
```

Or via environment:

```bash
CONTEXTCORE_TEMPO_DATASOURCE="My Tempo"
CONTEXTCORE_LOKI_DATASOURCE="My Loki"
CONTEXTCORE_PROMETHEUS_DATASOURCE="My Prometheus"
```

## Verification

After installation, verify dashboards are working:

```bash
# List provisioned dashboards
contextcore dashboards list

# Expected output:
# UID                        Title                        Folder
# contextcore-portfolio      Project Portfolio Overview   ContextCore
# contextcore-project-details Project Details             ContextCore
```

### Health Check

```bash
# Verify data sources and queries
contextcore dashboards health-check

# Expected output:
# ✓ Tempo datasource connected
# ✓ Loki datasource connected
# ✓ Prometheus datasource connected
# ✓ Portfolio dashboard panels: 12/12 OK
# ✓ Project Details dashboard panels: 18/18 OK
```

## Troubleshooting

### Dashboard Not Appearing

1. Check folder permissions in Grafana
2. Verify API key has dashboard creation permissions
3. Check logs: `contextcore dashboards provision --verbose`

### No Data in Panels

1. Verify data sources are correctly named
2. Ensure ContextCore tasks have been created:
   ```bash
   contextcore task start --id TEST-1 --title "Test task"
   ```
3. Check data source connectivity in Grafana

### Authentication Errors

```bash
# Test Grafana connection
contextcore dashboards test-connection --grafana-url URL --grafana-token TOKEN
```

Required API permissions:
- `dashboards:create`
- `dashboards:write`
- `folders:create` (if using folder)

### Updating Dashboards

Dashboards can be safely re-provisioned (idempotent):

```bash
# Update to latest version
contextcore dashboards provision --force

# This will:
# 1. Check current dashboard version
# 2. Compare with bundled version
# 3. Update if newer version available
# 4. Preserve any user customizations in separate dashboard
```

## Uninstallation

```bash
# Remove ContextCore dashboards
contextcore dashboards delete

# Remove with confirmation
contextcore dashboards delete --yes
```

## Related Documentation

- [PROJECT_PORTFOLIO_OVERVIEW.md](PROJECT_PORTFOLIO_OVERVIEW.md) - Portfolio dashboard specification
- [PROJECT_DETAILS.md](PROJECT_DETAILS.md) - Project details dashboard specification
- [../semantic-conventions.md](../semantic-conventions.md) - Query conventions used by dashboards
