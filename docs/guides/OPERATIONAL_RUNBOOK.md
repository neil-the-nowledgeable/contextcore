# ContextCore Operational Runbook

Quick reference for operating the ContextCore observability stack.

## Quick Reference

```bash
make doctor      # Preflight checks before starting
make up          # Start stack (runs doctor first)
make down        # Stop stack (preserves data)
make health      # One-line health status per component
make smoke-test  # Validate entire stack
make backup      # Create timestamped backup
make destroy     # Delete stack (auto-backup + confirmation)
```

## Environment Notice

**Two environments exist until datasets are merged:**

| Environment | Path | Grafana Password | Purpose |
|-------------|------|------------------|---------|
| **DEV** | `~/Documents/dev/ContextCore` | `admin` | Development, newer code |
| **TEST** | `~/Documents/Deploy` | `adminadminadmin` | Testing, stable deployments |

Both target the `observability` namespace in the `o11y-dev` Kind cluster. Use the Grafana password to identify which environment you're connected to.

## Daily Operations

### Starting the Stack

```bash
# Always run doctor first
make doctor

# Start all services with persistent storage
make up

# Verify everything is working
make health
make smoke-test
```

### Checking Health

```bash
# Quick status check
make health

# Detailed component status
contextcore ops health

# Full validation suite
make smoke-test
```

### Stopping Safely

```bash
# Stop but keep data (safe to restart later)
make down

# Check what data exists
make storage-status
```

## Component URLs

| Component | URL | Purpose |
|-----------|-----|---------|
| Grafana | http://localhost:3000 | Dashboards and visualization |
| Tempo | http://localhost:3200 | Trace backend |
| Mimir | http://localhost:9009 | Metrics backend |
| Loki | http://localhost:3100 | Log aggregation |
| OTLP gRPC | localhost:4317 | Telemetry ingestion (gRPC) |
| OTLP HTTP | localhost:4318 | Telemetry ingestion (HTTP) |

## Backup and Restore

### Creating Backups

```bash
# Create timestamped backup
make backup

# Or via CLI with custom location
contextcore ops backup --output ./my-backups
```

Backups include:
- Grafana dashboards
- Grafana datasources
- ContextCore state

### Listing Backups

```bash
contextcore ops backups
```

### Restoring from Backup

```bash
# Restore specific backup
make restore BACKUP=backups/20260117-120000

# Or via CLI
contextcore ops restore backups/20260117-120000
```

## Troubleshooting

### Port Conflicts

If `make doctor` shows ports in use:

```bash
# Find what's using a port
lsof -i :3000

# Option 1: Stop the conflicting service
# Option 2: Modify docker-compose.yaml ports
```

### Container Won't Start

```bash
# Check container logs
make logs-grafana
make logs-tempo
make logs-mimir
make logs-loki

# Check Docker daemon
docker info

# Verify disk space
df -h
```

### Data Corruption

```bash
# Create backup of current state
make backup

# Stop stack
make down

# Clear corrupted data (specific component)
rm -rf data/tempo/*   # Traces
rm -rf data/mimir/*   # Metrics
rm -rf data/loki/*    # Logs
rm -rf data/grafana/* # Dashboards (restore from backup!)

# Restart
make up

# Restore dashboards
make restore BACKUP=backups/latest
```

### Health Check Failures

```bash
# Component-specific health endpoints
curl http://localhost:3000/api/health        # Grafana
curl http://localhost:3200/ready             # Tempo
curl http://localhost:9009/ready             # Mimir
curl http://localhost:3100/ready             # Loki

# Check container status
docker compose ps
```

## Recovery Procedures

### Complete Stack Recovery

```bash
# 1. Stop everything
make down

# 2. Clear all data (if needed)
make storage-clean

# 3. Start fresh
make up

# 4. Restore dashboards from backup
contextcore ops backups          # List available backups
make restore BACKUP=backups/xxx  # Restore latest
```

### Recovering from Accidental Deletion

If containers or data were accidentally deleted:

```bash
# 1. Check if data directory still exists
ls -la data/

# 2. If data exists, just restart
make up

# 3. If data is gone, restore from backup
make up
contextcore ops backups
make restore BACKUP=backups/latest
```

### Moving to New Machine

```bash
# On old machine
make backup
# Copy backups/ directory to new machine

# On new machine
git clone <repo>
make up
make restore BACKUP=backups/xxx
```

## Data Persistence

All data is stored in `./data/`:

```
data/
├── grafana/     # Dashboards, datasources, preferences
├── tempo/       # Trace data (spans)
├── mimir/       # Metrics data (time series)
└── loki/        # Log data
```

### Data Retention

| Component | Default Retention | Config Location |
|-----------|-------------------|-----------------|
| Tempo | 48 hours | tempo/tempo.yaml |
| Mimir | Unlimited (local) | mimir/mimir.yaml |
| Loki | 7 days | loki/loki.yaml |

### Checking Data Size

```bash
make storage-status
# Or
du -sh data/*
```

## Destructive Operations

### make destroy

This command:
1. Creates automatic backup
2. Prompts for confirmation (type "yes")
3. Stops containers
4. Removes volumes

```bash
make destroy
# Output:
# Creating backup before destroy...
# [backup output]
#
# WARNING: This will destroy all data!
# Type 'yes' to confirm: yes
# [destruction proceeds]
```

### Clearing Storage

```bash
# Show what will be deleted
make storage-status

# Clean (requires confirmation)
make storage-clean
```

## CLI Reference

### Doctor (Preflight)

```bash
contextcore ops doctor              # Full check
contextcore ops doctor --no-ports   # Skip port check
contextcore ops doctor --no-docker  # Skip Docker check
```

### Health

```bash
contextcore ops health              # All components
contextcore ops health --no-otlp    # Skip OTLP check
```

### Smoke Test

```bash
contextcore ops smoke-test          # Full suite
contextcore ops smoke-test --list   # Show available tests
```

### Backup/Restore

```bash
contextcore ops backup                        # Default location
contextcore ops backup --output ./backups     # Custom location
contextcore ops backups                       # List backups
contextcore ops restore ./backups/20260117    # Restore specific
```

## Environment Variables

```bash
# Telemetry export
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Grafana authentication (if changed from defaults)
export GRAFANA_USER=admin
export GRAFANA_PASSWORD=admin
```

## Logs

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
make logs-grafana
make logs-tempo
make logs-mimir
make logs-loki
```

### Common Log Issues

| Pattern | Cause | Fix |
|---------|-------|-----|
| `connection refused` | Service not ready | Wait or restart |
| `permission denied` | Volume permissions | `sudo chown -R $USER data/` |
| `disk full` | Storage exceeded | Clear old data or add disk |
| `port already in use` | Conflict | `make doctor` to identify |
