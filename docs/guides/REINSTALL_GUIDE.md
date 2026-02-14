# ContextCore Clean Reinstall Guide

This guide walks through a complete teardown and fresh installation of the ContextCore observability stack.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.9+ with ContextCore installed (`pip install -e ".[dev]"`)
- All commands run from the **project root directory**:

```bash
cd <project-root>  # e.g., ~/Documents/dev/ContextCore
```

---

## Environment Notice

**Two environments exist until datasets are merged:**

| Environment | Path | Grafana Password | Purpose |
|-------------|------|------------------|---------|
| **DEV** | `~/Documents/dev/ContextCore` | `admin` | Development, newer code |
| **TEST** | `~/Documents/Deploy` | `adminadminadmin` | Testing, stable deployments |

Both target the `observability` namespace in the `o11y-dev` Kind cluster. Use the Grafana password to identify which environment you're connected to.

---

## Phase 1: Teardown (Clean Slate)

**Directory:** `ContextCore/` (project root)

```bash
# Ensure you're in the project root
pwd
# Should show your ContextCore project root

# 1. Stop any running containers
make down

# 2. Remove all data (this will prompt for confirmation)
make destroy
# Type 'yes' when prompted

# 3. Verify clean state
ls data/                              # Should not exist or be empty
docker ps -a | grep contextcore       # Should show nothing
```

---

## Phase 2: Fresh Install

**Directory:** `ContextCore/` (project root)

### Option A: One-Command Setup (Recommended)

```bash
# Full setup: start stack + wait for ready + seed metrics
make full-setup
```

**What `make full-setup` does:**
1. Runs `make doctor` (preflight checks)
2. Creates `data/` directories for persistence
3. Starts Docker Compose stack (Grafana, Tempo, Mimir, Loki)
4. Waits up to 60s for all services to be healthy
5. Runs `contextcore install verify` to seed dashboard metrics

### Option B: Step-by-Step Setup

```bash
# 1. Preflight check - verify system is ready
make doctor

# 2. Start the stack
make up

# 3. Wait for services to be healthy
make wait-ready

# 4. Seed metrics to populate dashboards
make seed-metrics
```

---

## Phase 3: Verification Checklist

**Directory:** `ContextCore/` (project root)

Run each check and verify expected results:

| Check | Command | Expected |
|-------|---------|----------|
| Services healthy | `make health` | All green checkmarks |
| Smoke test | `make smoke-test` | 6/6 passed |
| Install complete | `contextcore install status` | "Complete" |
| Dashboard has data | Open browser to dashboard URL | Shows 100% completeness |

### Dashboard URL

```
http://localhost:3000/d/contextcore-installation
```

Login: `admin` / `admin`

---

## Phase 4: Manual Verification (Optional)

**Directory:** `ContextCore/` (project root)

### Check metrics exist in Mimir

```bash
curl -s "http://localhost:9009/prometheus/api/v1/query?query=contextcore_install_completeness_percent" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['result'][0]['value'][1] if d['data']['result'] else 'No data')"
```

Expected output: `100` (or current completeness percentage)

### Check traces exist in Tempo

```bash
curl -s "http://localhost:3200/api/search?q=%7Bname%3D%22contextcore.install.verify%22%7D&limit=1" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Found {len(d.get('traces',[]))} traces\")"
```

Expected output: `Found 1 traces` (or more)

### Check all requirement metrics

```bash
curl -s "http://localhost:9009/prometheus/api/v1/query?query=contextcore_install_requirement_status_ratio" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Found {len(d['data']['result'])} requirements\")"
```

Expected output: `Found 25 requirements`

---

## Quick Reference

### URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Dashboards (admin/admin) |
| Installation Dashboard | http://localhost:3000/d/contextcore-installation | Self-monitoring |
| Portfolio Dashboard | http://localhost:3000/d/contextcore-portfolio | Project overview |
| Tempo | http://localhost:3200 | Traces API |
| Mimir | http://localhost:9009 | Metrics API |
| Loki | http://localhost:3100 | Logs API |

### Ports

| Port | Service |
|------|---------|
| 3000 | Grafana |
| 3100 | Loki |
| 3200 | Tempo HTTP |
| 4317 | OTLP gRPC |
| 4318 | OTLP HTTP |
| 9009 | Mimir |

---

## Troubleshooting

**Directory:** `ContextCore/` (project root)

### Dashboard shows no data after `full-setup`

```bash
# Re-seed metrics manually
make seed-metrics

# Or with verbose output
contextcore install verify --endpoint localhost:4317
```

### Services don't start

```bash
# Check container logs
make logs-grafana
make logs-tempo
make logs-mimir
make logs-loki

# Check if ports are available
make doctor
```

### Services unhealthy

```bash
# Check status
make status

# View detailed health
make health

# Restart specific service
docker compose restart tempo
```

### Authentication issues with Grafana API

```bash
# Set credentials explicitly
export GRAFANA_USER=admin
export GRAFANA_PASSWORD=admin

# Then re-run
make seed-metrics
```

---

## Environment Variables

These can be set before running commands:

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAFANA_URL` | `http://localhost:3000` | Grafana base URL |
| `GRAFANA_USER` | `admin` | Grafana username |
| `GRAFANA_PASSWORD` | `admin` | Grafana password |
| `OTLP_ENDPOINT` | `localhost:4317` | OTLP gRPC endpoint |

Example:
```bash
GRAFANA_PASSWORD=mypassword make full-setup
```

---

## Complete Command Sequence

Copy-paste ready sequence for a full reinstall:

```bash
# Navigate to project root
cd <project-root>  # e.g., ~/Documents/dev/ContextCore

# Teardown
make down
make destroy  # Type 'yes' when prompted

# Fresh install
make full-setup

# Verify
make health
make smoke-test
contextcore install status

# Open dashboard
open http://localhost:3000/d/contextcore-installation
```
