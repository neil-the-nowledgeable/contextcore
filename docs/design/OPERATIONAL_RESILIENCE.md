# Operational Resilience for ContextCore

## Lessons Learned

### Critical Oversights from Initial Design

| Issue | Impact | Root Cause |
|-------|--------|------------|
| **No data persistence** | Lost all traces, metrics, logs on container restart | Docker Compose used ephemeral volumes |
| **Accidental deletion via Docker Desktop** | Complete infrastructure loss | No safety prompts, no auto-backup |
| **No health validation** | Couldn't verify stack was working | No smoke tests or health endpoints |
| **No preflight checks** | Deployment failures due to port conflicts | No `doctor` command |
| **No backup mechanism** | Couldn't recover from mistakes | No export/import tooling |

### Architectural Patterns from O11yBubo

The O11yBubo/Kind deployment architecture provides proven patterns for resilient local development:

```
Key Patterns:
1. make doctor    → Preflight checks before any operation
2. make up        → Idempotent deployment (auto-runs doctor)
3. make down      → Stop but PRESERVE data
4. make destroy   → Delete but AUTO-BACKUP first
5. make health    → One-line status per component
6. make smoke-test → Full stack validation
7. make verify    → Quick cluster health check
8. make backup    → Export state to timestamped directory
```

---

## Data Persistence Strategy

### Storage Requirements

| Component | Data Type | Persistence Required | Recovery Priority |
|-----------|-----------|---------------------|-------------------|
| **Tempo** | Traces, spans | Critical | High |
| **Mimir** | Metrics | Critical | High |
| **Loki** | Logs | Important | Medium |
| **Grafana** | Dashboards, datasources | Important | Medium (can reprovision) |
| **ContextCore State** | Task spans, project contexts | Critical | High |

### Docker Compose Volumes

```yaml
volumes:
  tempo_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${PWD}/data/tempo
  mimir_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${PWD}/data/mimir
  loki_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${PWD}/data/loki
  grafana_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${PWD}/data/grafana
```

### Directory Structure for Persistent Data

```
contextcore/
├── data/                      # Persistent storage (gitignored)
│   ├── tempo/                 # Trace data
│   ├── mimir/                 # Metrics data
│   ├── loki/                  # Log data
│   └── grafana/               # Dashboards, plugins
├── backups/                   # Timestamped backups (gitignored)
│   └── 20260117-143000/
│       ├── configmaps/
│       ├── dashboards/
│       └── state.json
└── .gitignore                 # Excludes data/ and backups/
```

---

## Operational Commands

### Makefile Targets

```makefile
# Preflight
make doctor          # Check ports, tools, Docker

# Deployment
make up              # Start everything (runs doctor first)
make down            # Stop (preserve data)
make destroy         # Delete (auto-backup first, confirm)

# Health & Validation
make health          # One-line status per component
make smoke-test      # Validate entire stack
make verify          # Quick health check

# Backup & Recovery
make backup          # Export to timestamped directory
make restore         # Restore from backup (interactive)

# Storage
make storage-status  # Show volume sizes and status
make storage-clean   # Delete data (with confirmation)
```

### CLI Commands

```bash
# Preflight checks
contextcore ops doctor

# Health checks
contextcore ops health
contextcore ops smoke-test
contextcore ops verify

# Backup & recovery
contextcore ops backup [--output-dir ./backups]
contextcore ops restore --from ./backups/20260117-143000

# Status
contextcore ops status
contextcore ops storage-status
```

---

## Health Endpoints

### Component Health Checks

| Component | Endpoint | Success Criteria |
|-----------|----------|-----------------|
| Grafana | `GET /api/health` | HTTP 200 |
| Tempo | `GET /ready` | HTTP 200 |
| Mimir | `GET /ready` | HTTP 200 |
| Loki | `GET /ready` | HTTP 200 |
| Alloy | `GET /-/ready` | HTTP 200 |
| ContextCore CLI | `contextcore ops health` | All components green |

### Health Check Implementation

```python
@ops.command("health")
def health():
    """Show one-line health status per component."""
    components = [
        ("Grafana", "http://localhost:3000/api/health"),
        ("Tempo", "http://localhost:3200/ready"),
        ("Mimir", "http://localhost:9009/ready"),
        ("Loki", "http://localhost:3100/ready"),
    ]

    for name, url in components:
        try:
            resp = httpx.get(url, timeout=5)
            status = "✅ Ready" if resp.status_code == 200 else "❌ Not Ready"
        except:
            status = "❌ Not Accessible"
        click.echo(f"{name:12} {status}")
```

---

## Smoke Test Checklist

After every deployment, validate:

```
1. ✅ All containers running (no CrashLoopBackOff)
2. ✅ Grafana accessible at localhost:3000
3. ✅ Datasources configured (Tempo, Mimir, Loki)
4. ✅ Dashboards provisioned
5. ✅ Can emit a test span to Tempo
6. ✅ Can query traces via TraceQL
7. ✅ Can write a test metric to Mimir
8. ✅ Can query metrics via PromQL
```

### Automated Smoke Test

```python
@ops.command("smoke-test")
def smoke_test():
    """Validate entire stack is working after deployment."""
    checks = [
        check_containers_running,
        check_grafana_health,
        check_datasources_configured,
        check_dashboards_provisioned,
        check_can_emit_span,
        check_can_query_traces,
        check_can_write_metric,
        check_can_query_metrics,
    ]

    passed = 0
    for check in checks:
        success, message = check()
        icon = "✅" if success else "❌"
        click.echo(f"{icon} {message}")
        if success:
            passed += 1

    click.echo()
    click.echo(f"Smoke Test: {passed}/{len(checks)} checks passed")
    return passed == len(checks)
```

---

## Safety Mechanisms

### Destructive Operation Protection

1. **Confirmation Prompts**
   ```bash
   $ contextcore ops destroy
   WARNING: This will delete all ContextCore data!

   The following will be destroyed:
     - All spans in Tempo
     - All metrics in Mimir
     - All logs in Loki
     - Grafana dashboards and settings

   Are you sure? Type 'yes' to confirm:
   ```

2. **Auto-Backup Before Destroy**
   ```python
   @ops.command("destroy")
   @click.option("--yes", is_flag=True, help="Skip confirmation")
   def destroy(yes):
       if not yes:
           # Show warning and get confirmation
           if not click.confirm("Delete all data?"):
               return

       # Auto-backup first
       click.echo("Creating backup before destroy...")
       backup_path = create_backup()
       click.echo(f"Backup saved to: {backup_path}")

       # Then destroy
       docker_compose_down_volumes()
   ```

3. **Separate Commands for Data-Preserving vs Data-Destroying**
   - `make down` / `contextcore ops down` → Stops containers, **preserves data**
   - `make destroy` / `contextcore ops destroy` → Removes everything, **auto-backups first**

---

## Backup & Recovery

### Backup Contents

```yaml
backup/
├── manifest.json        # Backup metadata
├── configmaps/          # K8s ConfigMaps / Docker configs
├── dashboards/          # Grafana dashboard JSON
├── datasources/         # Grafana datasource configs
├── state/
│   ├── tasks.json       # ContextCore task state
│   └── projects.json    # ProjectContext definitions
└── telemetry/           # Optional: recent spans/metrics export
    ├── traces.json
    └── metrics.txt
```

### Recovery Procedure

```bash
# 1. List available backups
contextcore ops backup list

# 2. Restore from specific backup
contextcore ops restore --from ./backups/20260117-143000

# 3. Verify restoration
contextcore ops smoke-test
```

---

## Preflight Checks (Doctor)

Before any deployment operation, validate:

```
=== Preflight Check ===

Checking required tools...
✅ docker
✅ docker-compose
✅ python3

Checking Docker daemon...
✅ Docker is running

Checking port availability...
✅ Port 3000 is available (Grafana)
✅ Port 3100 is available (Loki)
✅ Port 3200 is available (Tempo)
✅ Port 9009 is available (Mimir)
✅ Port 4317 is available (OTLP gRPC)
✅ Port 4318 is available (OTLP HTTP)

Checking disk space...
✅ 50GB available (minimum: 10GB)

Checking memory...
✅ 16GB available (recommended: 4GB)

=== Preflight Complete: Ready to deploy ===
```

---

## Implementation Priority

### Phase 1: Critical (Immediate)

1. **Add persistent volumes to Docker Compose**
   - Tempo, Mimir, Loki, Grafana data directories
   - Bind mounts to `./data/` directory

2. **Add `doctor` preflight check**
   - Port availability
   - Docker running
   - Disk space

3. **Add `health` command**
   - One-line status per component

### Phase 2: Important (This Week)

4. **Add `smoke-test` command**
   - Full validation after deployment

5. **Add `backup` command**
   - Export dashboards, configs, state

6. **Add safety prompts**
   - Confirmation for destructive operations
   - Auto-backup before destroy

### Phase 3: Enhancement (Next Sprint)

7. **Add `restore` command**
   - Restore from backup directory

8. **Add `verify` command**
   - Quick cluster health check

9. **Add Makefile**
   - Unified interface for all operations

---

## Files to Create/Modify

| File | Purpose |
|------|---------|
| `docker-compose.yaml` | Add persistent volumes |
| `Makefile` | Operational targets |
| `src/contextcore/ops/__init__.py` | Operations module |
| `src/contextcore/ops/doctor.py` | Preflight checks |
| `src/contextcore/ops/health.py` | Health checks |
| `src/contextcore/ops/smoke_test.py` | Full validation |
| `src/contextcore/ops/backup.py` | Backup/restore |
| `src/contextcore/cli.py` | Add `ops` command group |
| `.gitignore` | Add `data/`, `backups/` |
| `docs/OPERATIONAL_RESILIENCE.md` | This document |

---

## Success Criteria

After implementation, the following workflow should be possible:

```bash
# 1. Preflight check
contextcore ops doctor
# → All checks pass

# 2. Deploy stack
make up  # or: contextcore ops up
# → Automatically runs doctor first
# → Creates persistent volume directories
# → Starts all containers

# 3. Validate deployment
contextcore ops smoke-test
# → All 8 checks pass

# 4. Work with ContextCore
contextcore task start --id PROJ-123 --title "My Task"
# → Span emitted to Tempo

# 5. Accidental Docker Desktop "Clean up"
# → Data persists because volumes are bind-mounted

# 6. Restart after accident
make up
# → All data still present
# → Smoke test passes

# 7. Intentional cleanup
make destroy
# → Auto-backup created first
# → Confirmation required
# → Clean slate for fresh start

# 8. Recovery if needed
contextcore ops restore --from ./backups/latest
# → Dashboards, configs restored
```

This workflow ensures:
- **No accidental data loss** (persistent volumes)
- **Recovery from mistakes** (auto-backup)
- **Confidence in deployments** (smoke tests)
- **Quick troubleshooting** (health checks)
