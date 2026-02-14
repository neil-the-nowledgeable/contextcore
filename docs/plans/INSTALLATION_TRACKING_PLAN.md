# Installation Tracking & Resume Plan

## Vision

Transform the ContextCore installation process from a one-shot script into a **resumable, observable, self-healing** system. Installation progress is tracked both locally (for fast resume) and in the observability stack (for visibility), enabling:

- **Resume**: Continue from where a failed installation stopped
- **Repair**: Detect and fix broken components without full reinstall
- **Visibility**: See installation progress in Grafana dashboards in real-time
- **Idempotency**: Safe to run multiple times without side effects

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Installation Flow                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   create-cluster.sh                                                      │
│         │                                                                │
│         ▼                                                                │
│   ┌─────────────┐     ┌──────────────────┐     ┌────────────────────┐  │
│   │ State File  │◄───►│ Step Executor    │────►│ Metric Emitter     │  │
│   │ (local)     │     │ (idempotent)     │     │ (curl to Mimir)    │  │
│   └─────────────┘     └──────────────────┘     └────────────────────┘  │
│         │                     │                         │               │
│         ▼                     ▼                         ▼               │
│   ~/.contextcore/       kubectl/kind              Mimir/Grafana         │
│   install-state.json    (actual work)             (observable)          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Dual-Track State

| Track | Location | Purpose | Speed |
|-------|----------|---------|-------|
| **Local** | `~/.contextcore/install-state.json` | Resume, offline checks | Fast |
| **Observable** | Mimir metrics | Dashboards, historical tracking | Network |

**Why both?**
- Local state enables instant resume without querying Mimir
- Observable state provides visibility and historical tracking
- If local state is lost, can rebuild from observable state
- If Mimir is down, installation still works via local state

---

## What to Implement

### 1. State File Management

**File**: `~/.contextcore/install-state.json`

```json
{
  "version": "1.0",
  "cluster_name": "o11y-dev",
  "started_at": "2024-01-22T15:30:00Z",
  "updated_at": "2024-01-22T15:35:00Z",
  "steps": {
    "preflight": {
      "status": "completed",
      "completed_at": "2024-01-22T15:30:05Z"
    },
    "cluster_create": {
      "status": "completed",
      "completed_at": "2024-01-22T15:32:00Z"
    },
    "manifests_apply": {
      "status": "completed",
      "completed_at": "2024-01-22T15:32:30Z"
    },
    "pods_ready": {
      "status": "in_progress",
      "started_at": "2024-01-22T15:32:31Z",
      "attempts": 1
    },
    "services_verify": {
      "status": "pending"
    },
    "metrics_seed": {
      "status": "pending"
    }
  }
}
```

**Why JSON?**
- Human-readable for debugging
- Easy to parse in bash (with jq) and Python
- Supports nested structure for step metadata

### 2. Installation Steps (Defined)

| Step ID | Description | Idempotency Check | Recovery Action |
|---------|-------------|-------------------|-----------------|
| `preflight` | Check Docker, kind, kubectl | Always re-run (fast) | Install missing tools |
| `cluster_create` | Create Kind cluster | `kind get clusters \| grep o11y-dev` | Skip if exists |
| `manifests_apply` | Apply k8s manifests | Check ConfigMaps exist | Re-apply (idempotent) |
| `pods_ready` | Wait for pods Running | `kubectl get pods` status | Wait/restart pods |
| `services_verify` | Check ports accessible | `nc -z localhost PORT` | Diagnose networking |
| `metrics_seed` | Run contextcore verify | Check metrics in Mimir | Re-run verification |

### 3. Script Flags

| Flag | Behavior |
|------|----------|
| `--resume` | Read state file, skip completed steps, continue from last |
| `--repair` | Re-verify all steps, fix any that fail checks |
| `--reset` | Clear state file, start fresh |
| `--status` | Show current installation state without running |

### 4. Metric Emission (Python-Free)

Emit metrics via curl to Mimir's Prometheus remote write API:

```bash
emit_step_metric() {
    local step=$1
    local status=$2  # 0=pending, 1=in_progress, 2=completed, 3=failed
    local timestamp=$(date +%s)000

    # Only emit if Mimir is accessible
    if curl -sf http://localhost:9009/ready >/dev/null 2>&1; then
        curl -s -X POST "http://localhost:9009/api/v1/push" \
            -H "Content-Type: application/x-protobuf" \
            -H "X-Prometheus-Remote-Write-Version: 0.1.0" \
            --data-binary @- << EOF
# Prometheus text format converted to remote write
contextcore_install_step_status{step="$step",cluster="$CLUSTER_NAME"} $status $timestamp
EOF
    fi
}
```

**Why curl instead of Python?**
- No dependency on Python venv during early install stages
- Works before contextcore package is installed
- Simpler failure modes

**Alternative**: Use Prometheus pushgateway format which Alloy can receive.

### 5. Dashboard Updates

Add new panels to Installation Status dashboard:

| Panel | Query | Visualization |
|-------|-------|---------------|
| Step Progress | `contextcore_install_step_status` | State timeline |
| Current Step | `max(contextcore_install_step_status)` | Stat |
| Installation Duration | `time() - contextcore_install_started_timestamp` | Stat |
| Failure Count | `count(contextcore_install_step_status == 3)` | Stat |

---

## How to Implement

### Phase 1: State File Infrastructure

**File**: `~/Documents/Deploy/scripts/install-state.sh` (sourced by create-cluster.sh)

```bash
#!/bin/bash
# Installation state management functions

STATE_DIR="$HOME/.contextcore"
STATE_FILE="$STATE_DIR/install-state.json"

init_state() {
    mkdir -p "$STATE_DIR"
    if [ ! -f "$STATE_FILE" ]; then
        cat > "$STATE_FILE" << EOF
{
  "version": "1.0",
  "cluster_name": "$CLUSTER_NAME",
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "steps": {}
}
EOF
    fi
}

get_step_status() {
    local step=$1
    jq -r ".steps.${step}.status // \"pending\"" "$STATE_FILE"
}

set_step_status() {
    local step=$1
    local status=$2
    local now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Update state file
    jq ".steps.${step}.status = \"${status}\" |
        .steps.${step}.updated_at = \"${now}\" |
        .updated_at = \"${now}\"" "$STATE_FILE" > "${STATE_FILE}.tmp" && \
        mv "${STATE_FILE}.tmp" "$STATE_FILE"

    # Emit metric if possible
    emit_step_metric "$step" "$status"
}

should_skip_step() {
    local step=$1
    local status=$(get_step_status "$step")

    if [ "$RESUME_MODE" = true ] && [ "$status" = "completed" ]; then
        return 0  # true, should skip
    fi
    return 1  # false, should run
}
```

### Phase 2: Refactor create-cluster.sh

Convert each step to use state management:

```bash
# Source state management
source "$SCRIPT_DIR/install-state.sh"

# Initialize state
init_state

# Step 1: Preflight (always run, fast)
run_step "preflight" preflight_checks

# Step 2: Cluster creation
if should_skip_step "cluster_create"; then
    verbose "Skipping cluster creation (already completed)"
else
    set_step_status "cluster_create" "in_progress"
    if create_cluster; then
        set_step_status "cluster_create" "completed"
    else
        set_step_status "cluster_create" "failed"
        exit 1
    fi
fi

# ... similar pattern for other steps
```

### Phase 3: Add --resume, --repair, --status Flags

```bash
# Parse arguments
RESUME_MODE=false
REPAIR_MODE=false
STATUS_ONLY=false

for arg in "$@"; do
    case $arg in
        --resume)
            RESUME_MODE=true
            ;;
        --repair)
            REPAIR_MODE=true
            ;;
        --status)
            STATUS_ONLY=true
            ;;
        --reset)
            rm -f "$STATE_FILE"
            echo "State reset. Run without --reset to start fresh."
            exit 0
            ;;
    esac
done

# Handle --status
if [ "$STATUS_ONLY" = true ]; then
    show_installation_status
    exit 0
fi
```

### Phase 4: Metric Emission

Create lightweight metric push function:

```bash
emit_step_metric() {
    local step=$1
    local status=$2

    # Map status to numeric value
    case $status in
        pending)     value=0 ;;
        in_progress) value=1 ;;
        completed)   value=2 ;;
        failed)      value=3 ;;
    esac

    # Try to push to Alloy's OTLP endpoint or Mimir directly
    # This is best-effort - don't fail install if metrics fail
    if nc -z localhost 9009 2>/dev/null; then
        # Push to Mimir's remote write endpoint
        # Using prometheus exposition format via pushgateway-style endpoint
        curl -s --max-time 2 -X POST \
            "http://localhost:9009/api/v1/import/prometheus" \
            --data-binary "contextcore_install_step_status{step=\"$step\",cluster=\"$CLUSTER_NAME\"} $value" \
            >/dev/null 2>&1 || true
    fi
}
```

### Phase 5: Repair Mode

```bash
repair_step() {
    local step=$1

    case $step in
        cluster_create)
            if ! kind get clusters | grep -q "$CLUSTER_NAME"; then
                echo "Cluster missing, recreating..."
                create_cluster
            fi
            ;;
        manifests_apply)
            echo "Reapplying manifests..."
            kubectl apply -k "$K8S_MANIFESTS"
            ;;
        pods_ready)
            # Check for crashed pods, restart them
            crashed=$(kubectl get pods -n observability --no-headers | grep -E "CrashLoop|Error" | awk '{print $1}')
            if [ -n "$crashed" ]; then
                echo "Restarting crashed pods: $crashed"
                kubectl delete pods -n observability $crashed
            fi
            wait_for_pods
            ;;
        services_verify)
            # Diagnose and report
            verify_services
            ;;
    esac
}

if [ "$REPAIR_MODE" = true ]; then
    echo "Running in repair mode..."
    for step in preflight cluster_create manifests_apply pods_ready services_verify metrics_seed; do
        repair_step "$step"
    done
fi
```

---

## Why These Decisions

### Why Local State File + Observable Metrics?

| Approach | Pros | Cons |
|----------|------|------|
| Local only | Fast, works offline | No visibility, lost if file deleted |
| Observable only | Visible in Grafana | Slow queries, needs Mimir running |
| **Hybrid** | Best of both | Slightly more complex |

The hybrid approach ensures:
- Installation works even if observability stack isn't ready yet
- Progress is visible in dashboards once stack is up
- Fast resume without network queries

### Why jq for JSON?

- Standard tool, likely already installed
- Handles nested JSON updates atomically
- Alternative: Use simple file flags per step (less elegant but no dependencies)

### Why Curl for Metrics?

- No Python dependency during bash script execution
- Works before venv is activated
- Graceful degradation if Mimir isn't ready

### Why Step-Based (Not Monolithic)?

- Each step is independently verifiable
- Failed step can be retried without redoing everything
- Maps naturally to observability (one span/metric per step)
- Enables parallel execution in future (independent steps)

---

## Implementation Order

1. **Create `install-state.sh`** - State file management functions
2. **Add jq dependency check** - Preflight check for jq
3. **Refactor `create-cluster.sh`** - Use step functions with state tracking
4. **Add `--resume` flag** - Skip completed steps
5. **Add `--status` flag** - Show current state
6. **Add `--repair` flag** - Re-verify and fix
7. **Add metric emission** - Best-effort push to Mimir
8. **Update dashboard** - Add step progress visualization
9. **Update INSTALLATION.md** - Document new flags

---

## Success Criteria

- [ ] `./create-cluster.sh` creates state file and completes all steps
- [ ] `./create-cluster.sh --resume` after interruption continues from last step
- [ ] `./create-cluster.sh --status` shows current installation state
- [ ] `./create-cluster.sh --repair` fixes a manually broken component
- [ ] Installation dashboard shows step-by-step progress
- [ ] State file survives script crash and enables resume
- [ ] Works without Python venv (pure bash until final verification step)

---

## Future Enhancements

1. **Remote state sync** - Backup state to Kubernetes ConfigMap for cluster-aware resume
2. **Multi-cluster support** - Track state per cluster name
3. **Rollback** - Undo steps in reverse order
4. **Parallel steps** - Run independent steps concurrently
5. **Notifications** - Alert on installation failure via Grafana alerting
