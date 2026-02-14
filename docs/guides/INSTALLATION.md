# ContextCore Installation Guide

Complete installation guide for ContextCore observability stack.

## Quick Navigation

| I want to... | Go to |
|--------------|-------|
| Get started fast (solo dev) | [Docker Compose Quick Start](#option-a-docker-compose) |
| Use Kubernetes patterns | [Kind Cluster Quick Start](#option-b-kind-cluster) |
| Use the interactive TUI | [Terminal User Interface](#terminal-user-interface-tui) |
| Troubleshoot issues | [Troubleshooting](#troubleshooting) |
| Verify my installation | [Verification](#verification) |

---

## Environment Notice

**Two environments exist until datasets are merged:**

| Environment | Path | Grafana Password | Purpose |
|-------------|------|------------------|---------|
| **DEV** | `~/Documents/dev/ContextCore` | `admin` | Development, newer code |
| **TEST** | `~/Documents/Deploy` | `adminadminadmin` | Testing, stable deployments |

Both target the `observability` namespace in the `o11y-dev` Kind cluster. Use the Grafana password to identify which environment you're connected to.

---

## Prerequisites

### Required Tools

| Tool | Version | Check Command | Install (macOS) |
|------|---------|---------------|-----------------|
| Docker | 20.10+ | `docker --version` | `brew install --cask docker` |
| Python | 3.9+ | `python3 --version` | `brew install python@3.11` |
| kubectl | 1.28+ | `kubectl version --client` | `brew install kubectl` |
| Kind | 0.20+ | `kind --version` | `brew install kind` |

### System Requirements

| Configuration | RAM | CPU | Disk |
|--------------|-----|-----|------|
| Docker Compose | 4GB | 2 cores | 10GB |
| Kind Cluster | 8GB | 4 cores | 20GB |

### Install ContextCore CLI

```bash
cd ~/Documents/dev/ContextCore

# Create and activate virtual environment (required on macOS with Homebrew Python)
python3 -m venv .venv
source .venv/bin/activate

# Install ContextCore
pip install -e ".[dev]"

# Verify
contextcore --version
```

**Note:** The virtual environment must be activated in each new terminal session:
```bash
source ~/Documents/dev/ContextCore/.venv/bin/activate
```

---

## Choose Your Deployment

| Option | Best For | Setup Time | Components |
|--------|----------|------------|------------|
| **A: Docker Compose** | Solo development, quick start | ~2 min | Grafana, Tempo, Mimir, Loki, Alloy |
| **B: Kind Cluster** | Team reference, K8s patterns, multi-node | ~5 min | Above + Kubernetes scheduling |

---

## Option A: Docker Compose

> **Best for:** Quick local development without Kubernetes complexity

### Quick Start

```bash
cd ~/Documents/dev/ContextCore

# One command setup (runs doctor, starts stack, waits for ready, seeds metrics)
make full-setup
```

### What `make full-setup` Does

1. **doctor** - Checks ports, Docker, required tools
2. **up** - Starts all containers via Docker Compose
3. **wait-ready** - Polls services until healthy (60s timeout)
4. **seed-metrics** - Runs `contextcore install verify` to populate dashboards

### Step-by-Step Setup (Alternative)

```bash
cd ~/Documents/dev/ContextCore

# 1. Preflight checks
make doctor

# 2. Start the stack
make up

# 3. Wait for services (60s timeout)
make wait-ready

# 4. Seed installation metrics
make seed-metrics

# 5. Verify
make health
```

### Architecture (Docker Compose)

```
Host Machine
│
├─► localhost:4317 ──► Alloy (OTLP Collector)
│                        ├──► Tempo (traces)
│                        ├──► Mimir (metrics via remote_write)
│                        └──► Loki (logs)
│
├─► localhost:3000 ──► Grafana (dashboards)
├─► localhost:3200 ──► Tempo API
├─► localhost:9009 ──► Mimir API
└─► localhost:3100 ──► Loki API
```

### Teardown (Docker Compose)

```bash
# Stop (preserve data)
make down

# Destroy (delete all data - prompts for confirmation)
make destroy
```

---

## Option B: Kind Cluster

> **Best for:** Kubernetes-native development, testing K8s patterns, multi-node scheduling

### Quick Start

```bash
cd ~/Documents/Deploy

# One command setup (creates cluster, deploys stack, waits for pods)
./scripts/create-cluster.sh

# With detailed progress output
./scripts/create-cluster.sh --verbose

# Tutorial mode - explains what each step does and why (great for learning)
./scripts/create-cluster.sh --verbose-tutorial
```

**Script options:**

| Flag | Description |
|------|-------------|
| (none) | Standard setup with progress output |
| `--verbose` | Show detailed progress (commands being run, resource lists) |
| `--verbose-tutorial` | Explain each step - what it does and why (learning mode) |
| `--skip-wait` | Don't wait for pods (faster, for debugging) |
| `--delete` | Delete cluster with confirmation (requires typing cluster name) |

The script will:
1. Run preflight checks (Docker, kind, kubectl)
2. Create a 3-node Kind cluster (`o11y-dev`)
3. Deploy the observability stack to `observability` namespace
4. Wait for all pods to be ready
5. Verify port accessibility
6. Print next steps

### After Cluster Creation

```bash
# Activate ContextCore venv
source ~/Documents/dev/ContextCore/.venv/bin/activate

# Seed metrics to populate dashboards
contextcore install verify --endpoint localhost:4317

# Open the dashboard
open http://localhost:3000/d/contextcore-installation
```

### Step-by-Step Setup (Alternative)

If you prefer manual control or need to debug:

#### 1. Create Kind Cluster

```bash
cd ~/Documents/Deploy

# Create cluster with port mappings
kind create cluster --config kind-cluster.yaml

# Verify nodes (should see 3: control-plane + 2 workers)
kubectl get nodes
```

#### 2. Deploy Observability Stack

```bash
# Apply observability manifests
kubectl apply -k ~/Documents/dev/ContextCore/k8s/observability/

# Wait for all pods (up to 3 minutes for image pulls)
kubectl wait --for=condition=ready pod --all -n observability --timeout=180s

# Verify pods are running
kubectl get pods -n observability
```

Expected output:
```
NAME                       READY   STATUS    RESTARTS   AGE
alloy-xxxxxxxxxx-xxxxx     1/1     Running   0          60s
grafana-xxxxxxxxxx-xxxxx   1/1     Running   0          60s
loki-xxxxxxxxxx-xxxxx      1/1     Running   0          60s
mimir-xxxxxxxxxx-xxxxx     1/1     Running   0          60s
tempo-xxxxxxxxxx-xxxxx     1/1     Running   0          60s
```

#### 3. Verify Port Access

```bash
# All should respond (may take 10-30s after pods are ready)
curl -sf http://localhost:3000/api/health && echo "Grafana: OK"
curl -sf http://localhost:3200/ready && echo "Tempo: OK"
curl -sf http://localhost:9009/ready && echo "Mimir: OK"
curl -sf http://localhost:3100/ready && echo "Loki: OK"
nc -z localhost 4317 && echo "OTLP: OK"
```

#### 4. Seed Metrics

```bash
cd ~/Documents/dev/ContextCore
source .venv/bin/activate

# Run installation verification (sends metrics to Mimir)
contextcore install verify --endpoint localhost:4317
```

### Architecture (Kind Cluster)

```
Kind Cluster (o11y-dev)
│
├── observability namespace
│   ├── Alloy (NodePort 30317/30318) ──► OTLP ingestion
│   │   ├──► Tempo (NodePort 30200)
│   │   ├──► Mimir (NodePort 30009)
│   │   └──► Loki (NodePort 30100)
│   └── Grafana (NodePort 30000)
│
Host Port Mappings (via Kind extraPortMappings)
├── localhost:3000 → 30000 → Grafana
├── localhost:3100 → 30100 → Loki
├── localhost:3200 → 30200 → Tempo
├── localhost:4317 → 30317 → Alloy OTLP gRPC
├── localhost:4318 → 30318 → Alloy OTLP HTTP
└── localhost:9009 → 30009 → Mimir
```

### Teardown (Kind Cluster)

```bash
# Delete cluster with confirmation (like make destroy)
cd ~/Documents/Deploy
./scripts/create-cluster.sh --delete

# Or delete directly without confirmation
kind delete cluster --name o11y-dev

# Or just delete the observability namespace (keeps cluster)
kubectl delete namespace observability
```

---

## Terminal User Interface (TUI)

> **New in v0.1.0:** ContextCore includes an interactive TUI for guided installation and monitoring.

### Launch the TUI

```bash
cd ~/Documents/dev/ContextCore
source .venv/bin/activate

# Launch the welcome screen
contextcore tui launch

# Jump directly to a specific screen
contextcore tui launch --screen install      # Installation wizard
contextcore tui launch --screen status       # Service health dashboard
contextcore tui launch --screen configure    # Environment configuration
contextcore tui launch --screen script_generator  # Generate install scripts
```

### TUI Screens

| Screen | Key | Description |
|--------|-----|-------------|
| Welcome | - | Main menu with navigation cards |
| Install | `I` | 5-step guided installation wizard |
| Status | `S` | Real-time service health monitoring |
| Configure | `C` | Edit environment variables, test endpoints |
| Script Generator | `G` | Generate custom installation scripts |
| Help | `H` | Keyboard shortcuts and documentation |

### Installation Wizard (TUI)

The TUI installation wizard guides you through:

1. **Prerequisites Check** - Verifies Python, Docker, ports, etc.
2. **Deployment Method** - Choose Docker Compose, Kind, or Custom
3. **Configuration** - Set endpoints, credentials
4. **Deployment** - Runs `make full-setup` or creates Kind cluster
5. **Verification** - Confirms services are healthy

```bash
# Launch directly to install wizard
contextcore tui install

# Non-interactive install with defaults
contextcore tui install --method docker --auto
```

### Service Status (TUI)

Monitor service health in real-time:

```bash
# Interactive dashboard with auto-refresh
contextcore tui status

# JSON output for scripting
contextcore tui status --json

# Continuous watch mode
contextcore tui status --watch
```

### Script Generator

Generate custom installation scripts for your environment:

```bash
# Interactive TUI
contextcore tui launch --screen script_generator

# CLI script generation
contextcore tui generate-script --method docker
contextcore tui generate-script --method kind -o install.sh
```

The script generator supports:
- **Docker Compose** - Uses `make full-setup`
- **Kind Cluster** - Creates cluster and deploys stack
- **Custom** - Connects to existing infrastructure

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `?` | Help |
| `Esc` | Go back / Cancel |
| `d` | Toggle dark/light mode |
| `Tab` | Navigate between elements |

---

## Verification

### Health Checks

```bash
# Docker Compose
make health

# Kind Cluster
kubectl get pods -n observability
```

Expected output (all healthy):

| Component | Docker Compose | Kind Cluster |
|-----------|---------------|--------------|
| Grafana | `curl -sf localhost:3000/api/health` | Pod Running |
| Tempo | `curl -sf localhost:3200/ready` | Pod Running |
| Mimir | `curl -sf localhost:9009/ready` | Pod Running |
| Loki | `curl -sf localhost:3100/ready` | Pod Running |
| Alloy | `curl -sf localhost:12345/ready` | Pod Running |
| OTLP gRPC | `nc -z localhost 4317` | Port open |

### Installation Verification

```bash
# Full verification with telemetry
contextcore install verify --endpoint localhost:4317

# Quick status (no telemetry)
contextcore install status

# Debug mode - step through verification with Mimir validation
contextcore install verify --debug

# Debug mode with per-requirement checkpoints (more granular)
contextcore install verify --debug --step-all
```

Expected: **100% completeness, 25/25 requirements passed**

#### Debug Mode

Debug mode (`--debug`) provides step-by-step verification with real-time Mimir validation. At each checkpoint you'll see:

1. **Verification results** - Which requirements passed/failed with timing
2. **Metrics emitted** - What metrics were sent locally
3. **Mimir verification** - Confirms metrics were received correctly by Mimir

| Flag | Behavior |
|------|----------|
| `--debug` | Pause after each category (5 checkpoints) |
| `--debug --step-all` | Pause after each requirement (28 checkpoints) |

This is useful for:
- Debugging OTLP pipeline issues
- Verifying metrics reach Mimir correctly
- Understanding what telemetry is emitted during verification

### Check Metrics in Mimir

```bash
curl -s "http://localhost:9009/prometheus/api/v1/query?query=contextcore_install_completeness_percent" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); r=d['data']['result']; print(f'{r[0][\"value\"][1]}%' if r else 'No data')"
```

Expected: `100%`

### Check Traces in Tempo

```bash
curl -s "http://localhost:3200/api/search" -G --data-urlencode 'q={}' --data-urlencode 'limit=5' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Found {len(d.get(\"traces\",[]))} traces')"
```

Expected: `Found 5 traces` (or more)

### Dashboard Verification

Open in browser:

| Dashboard | URL |
|-----------|-----|
| Installation Status | http://localhost:3000/d/contextcore-installation |
| Project Portfolio | http://localhost:3000/d/contextcore-portfolio |

Login: `admin` / `admin`

---

## Troubleshooting

### Common Issues

#### "Tempo Running" fails in verification

**Cause:** Tempo service is ClusterIP (Kind) or not exposed.

**Fix (Kind):**
```bash
kubectl patch svc tempo -n observability --type='json' -p='[
  {"op": "replace", "path": "/spec/type", "value": "NodePort"},
  {"op": "add", "path": "/spec/ports/0/nodePort", "value": 30200}
]'
```

#### Mimir returns 429 Too Many Requests

**Cause:** Mimir config has `ingestion_rate: 0` or `ingestion_burst_size: 0` (means disabled, not unlimited).

**Fix:** Patch the Mimir ConfigMap:
```bash
kubectl patch configmap mimir-config -n observability --type='json' -p='[
  {"op": "replace", "path": "/data/mimir.yaml", "value": "multitenancy_enabled: false\n\nserver:\n  http_listen_port: 9009\n  grpc_listen_port: 9095\n\ndistributor:\n  ring:\n    instance_addr: 127.0.0.1\n    kvstore:\n      store: inmemory\n\ningester:\n  ring:\n    instance_addr: 127.0.0.1\n    kvstore:\n      store: inmemory\n    replication_factor: 1\n\nblocks_storage:\n  backend: filesystem\n  bucket_store:\n    sync_dir: /data/tsdb-sync\n  filesystem:\n    dir: /data/blocks\n  tsdb:\n    dir: /data/tsdb\n\ncompactor:\n  data_dir: /data/compactor\n  sharding_ring:\n    kvstore:\n      store: inmemory\n\nstore_gateway:\n  sharding_ring:\n    replication_factor: 1\n\nlimits:\n  max_global_series_per_user: 5000000\n  ingestion_rate: 50000\n  ingestion_burst_size: 100000\n"}
]'

# Restart to apply
kubectl rollout restart deployment/mimir -n observability
kubectl rollout restart deployment/alloy -n observability  # Clear retry backlog
```

#### Dashboard shows "No data"

**Cause:** Metrics not reaching Mimir, or not seeded yet.

**Fix:**
```bash
# Re-seed metrics
contextcore install verify --endpoint localhost:4317

# Wait 15 seconds for ingestion
sleep 15

# Verify metrics exist
curl -s "http://localhost:9009/prometheus/api/v1/query?query=contextcore_install_completeness_percent"
```

#### Port already in use

**Cause:** Previous containers or other services using the port.

**Fix:**
```bash
# Find what's using the port
lsof -i :3000

# Docker Compose: stop everything
make down
docker compose down -v

# Kind: check for existing cluster
kind get clusters
kind delete cluster --name o11y-dev
```

#### Pods stuck in Pending or ImagePullBackOff

**Cause:** Image pull issues or resource constraints.

**Fix:**
```bash
# Check pod events
kubectl describe pod -n observability -l app=grafana

# Check node resources
kubectl top nodes

# If image pull issue, check Docker Hub rate limits or network
```

#### Alloy not forwarding metrics

**Check logs:**
```bash
# Docker Compose
docker logs contextcore-alloy --tail 50

# Kind
kubectl logs -n observability -l app=alloy --tail 50
```

**Look for:**
- `429 Too Many Requests` → Fix Mimir limits
- Connection refused → Check service endpoints
- WAL replay taking long → Wait or restart Alloy

### Diagnostic Commands

```bash
# Docker Compose
make health
make smoke-test
make logs-tempo
make logs-mimir
make logs-alloy

# Kind
kubectl get pods -n observability
kubectl get svc -n observability
kubectl logs -n observability -l app=tempo --tail 50
kubectl logs -n observability -l app=mimir --tail 50
kubectl logs -n observability -l app=alloy --tail 50
kubectl describe pod -n observability -l app=mimir
```

---

## Port Reference

| Port | Service | Protocol | Notes |
|------|---------|----------|-------|
| 3000 | Grafana | HTTP | Dashboards UI |
| 3100 | Loki | HTTP | Log queries |
| 3200 | Tempo | HTTP | Trace queries |
| 4317 | Alloy | gRPC | OTLP ingestion (primary) |
| 4318 | Alloy | HTTP | OTLP ingestion (alternative) |
| 9009 | Mimir | HTTP | Metrics queries |
| 12345 | Alloy | HTTP | Alloy UI (debugging) |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAFANA_URL` | `http://localhost:3000` | Grafana base URL |
| `GRAFANA_USER` | `admin` | Grafana username |
| `GRAFANA_PASSWORD` | `admin` | Grafana password |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `localhost:4317` | OTLP endpoint |
| `TEMPO_URL` | `http://localhost:3200` | Tempo base URL |
| `MIMIR_URL` | `http://localhost:9009` | Mimir base URL |
| `LOKI_URL` | `http://localhost:3100` | Loki base URL |

---

## Next Steps

After installation:

1. **Create your first task:**
   ```bash
   contextcore task start --id TASK-1 --title "My first task" --type story
   contextcore task update --id TASK-1 --status in_progress
   contextcore task complete --id TASK-1
   ```

2. **View in dashboards:**
   - Open http://localhost:3000/d/contextcore-portfolio
   - See your task appear in the Project Portfolio

3. **Explore the CLI:**
   ```bash
   contextcore --help
   contextcore task --help
   contextcore install --help
   contextcore tui --help
   ```

4. **Try the TUI:**
   ```bash
   contextcore tui launch           # Interactive welcome screen
   contextcore tui status --json    # Quick health check
   ```

5. **Read the documentation:**
   - [README.md](../README.md) - Vision and concepts
   - [docs/semantic-conventions.md](semantic-conventions.md) - Attribute reference
   - [CLAUDE.md](../CLAUDE.md) - Developer reference

---

## Related Documentation

- [REINSTALL_GUIDE.md](REINSTALL_GUIDE.md) - Quick reinstall for Docker Compose
- [dashboards/INSTALLATION.md](dashboards/INSTALLATION.md) - Dashboard-specific installation
- [OPERATIONAL_RUNBOOK.md](OPERATIONAL_RUNBOOK.md) - Day-to-day operations
- [OPERATIONAL_RESILIENCE.md](OPERATIONAL_RESILIENCE.md) - Backup and recovery
