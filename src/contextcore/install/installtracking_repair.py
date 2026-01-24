Looking at the requirements and feedback, I need to create a complete, production-ready implementation of the repair system with full diagnostic capabilities and proper error handling.

```bash
#!/bin/bash

set -euo pipefail
IFS=$'\n\t'

# ============================================================================
# ContextCore Installation Repair Library
# Provides functions to verify installation health and repair broken components
# ============================================================================

# Source required dependencies
source "$(dirname "${BASH_SOURCE[0]}")/install-state.sh"
source "$(dirname "${BASH_SOURCE[0]}")/step-executor.sh"

# Environment Configuration
REPAIR_MODE=${REPAIR_MODE:-false}
REPAIR_AGGRESSIVE=${REPAIR_AGGRESSIVE:-false}
DIAGNOSTIC_LEVEL=${DIAGNOSTIC_LEVEL:-normal}
CLUSTER_NAME=${CLUSTER_NAME:-contextcore-local}

# Repair tracking
declare -a REPAIRED_STEPS=()
declare -a FAILED_REPAIRS=()

# ============================================================================
# Main Repair Functions
# ============================================================================

run_repair() {
    echo "[REPAIR] Starting ContextCore installation repair..."
    echo "[REPAIR] Repair mode: $([ "$REPAIR_AGGRESSIVE" = "true" ] && echo "AGGRESSIVE" || echo "CONSERVATIVE")"
    
    # Create diagnostic directory if needed
    mkdir -p ~/.contextcore
    
    # First, run full diagnostics
    echo "[REPAIR] Running initial diagnostics..."
    local unhealthy_steps
    unhealthy_steps=$(verify_all_steps)
    
    if [ -z "$unhealthy_steps" ]; then
        echo "[REPAIR] ✓ All components are healthy - no repairs needed"
        generate_diagnostic_report
        return 0
    fi
    
    echo "[REPAIR] Found unhealthy steps: $unhealthy_steps"
    
    # Repair each unhealthy step
    for step in $unhealthy_steps; do
        echo "[REPAIR] Repairing step: $step"
        if repair_step "$step"; then
            REPAIRED_STEPS+=("$step")
            echo "[REPAIR] ✓ Successfully repaired: $step"
        else
            FAILED_REPAIRS+=("$step")
            echo "[REPAIR] ✗ Failed to repair: $step"
        fi
    done
    
    # Generate final report
    generate_repair_summary
    generate_diagnostic_report
    
    if [ ${#FAILED_REPAIRS[@]} -eq 0 ]; then
        echo "[REPAIR] ✓ All repairs completed successfully"
        return 0
    else
        echo "[REPAIR] ✗ Some repairs failed. Check diagnostic report."
        return 1
    fi
}

verify_all_steps() {
    local unhealthy_steps=()
    
    # Check each step and collect failures
    verify_step "preflight" || unhealthy_steps+=("preflight")
    verify_step "cluster_create" || unhealthy_steps+=("cluster_create")
    verify_step "manifests_apply" || unhealthy_steps+=("manifests_apply")
    verify_step "pods_ready" || unhealthy_steps+=("pods_ready")
    verify_step "services_verify" || unhealthy_steps+=("services_verify")
    verify_step "metrics_seed" || unhealthy_steps+=("metrics_seed")
    
    # Return space-separated list of unhealthy steps
    printf "%s\n" "${unhealthy_steps[*]}"
}

verify_step() {
    local step_id="$1"
    
    case "$step_id" in
        "preflight")
            command -v docker >/dev/null 2>&1 && \
            command -v kubectl >/dev/null 2>&1 && \
            command -v kind >/dev/null 2>&1
            ;;
        "cluster_create")
            kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$" && \
            kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null 2>&1
            ;;
        "manifests_apply")
            kubectl get namespace observability >/dev/null 2>&1 && \
            kubectl get deployments -n observability >/dev/null 2>&1
            ;;
        "pods_ready")
            local not_ready
            not_ready=$(kubectl get pods -n observability --no-headers 2>/dev/null | \
                       grep -v "Running\|Completed" | wc -l || echo "1")
            [ "$not_ready" -eq 0 ]
            ;;
        "services_verify")
            kubectl get services -n observability grafana tempo mimir loki >/dev/null 2>&1
            ;;
        "metrics_seed")
            # Check if metrics endpoint is accessible
            kubectl get pods -n observability -l app=tempo --no-headers | grep -q "Running"
            ;;
        *)
            echo "[ERROR] Unknown step: $step_id" >&2
            return 1
            ;;
    esac
}

repair_step() {
    local step_id="$1"
    
    echo "[REPAIR] Diagnosing step: $step_id"
    
    case "$step_id" in
        "preflight") repair_preflight ;;
        "cluster_create") repair_cluster_create ;;
        "manifests_apply") repair_manifests_apply ;;
        "pods_ready") repair_pods_ready ;;
        "services_verify") repair_services_verify ;;
        "metrics_seed") repair_metrics_seed ;;
        *) 
            echo "[ERROR] Unknown repair step: $step_id" >&2
            return 1
            ;;
    esac
    
    # Verify repair was successful
    if verify_step "$step_id"; then
        echo "[REPAIR] ✓ Step $step_id verified healthy after repair"
        return 0
    else
        echo "[REPAIR] ✗ Step $step_id still unhealthy after repair"
        return 1
    fi
}

# ============================================================================
# Step-Specific Repair Functions
# ============================================================================

repair_preflight() {
    echo "[REPAIR] Checking preflight requirements..."
    
    local missing_tools=()
    command -v docker >/dev/null 2>&1 || missing_tools+=("docker")
    command -v kubectl >/dev/null 2>&1 || missing_tools+=("kubectl")
    command -v kind >/dev/null 2>&1 || missing_tools+=("kind")
    
    if [ ${#missing_tools[@]} -gt 0 ]; then
        echo "[REPAIR] ✗ Missing required tools: ${missing_tools[*]}"
        echo "[REPAIR] Please install missing tools before continuing"
        return 1
    fi
    
    echo "[REPAIR] ✓ All preflight requirements satisfied"
    return 0
}

repair_cluster_create() {
    if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        echo "[REPAIR] Cluster '${CLUSTER_NAME}' not found, creating..."
        
        if [ "$REPAIR_AGGRESSIVE" = "true" ]; then
            # Delete existing cluster if it exists but is broken
            kind delete cluster --name "${CLUSTER_NAME}" 2>/dev/null || true
        fi
        
        # Create new cluster
        kind create cluster --name "${CLUSTER_NAME}" --wait 5m
        echo "[REPAIR] ✓ Created cluster: ${CLUSTER_NAME}"
    else
        echo "[REPAIR] Cluster exists, checking health..."
        if ! kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null 2>&1; then
            if [ "$REPAIR_AGGRESSIVE" = "true" ]; then
                echo "[REPAIR] Cluster unhealthy, recreating..."
                kind delete cluster --name "${CLUSTER_NAME}"
                kind create cluster --name "${CLUSTER_NAME}" --wait 5m
                echo "[REPAIR] ✓ Recreated cluster: ${CLUSTER_NAME}"
            else
                echo "[REPAIR] ✗ Cluster unhealthy (use --aggressive to recreate)"
                return 1
            fi
        else
            echo "[REPAIR] ✓ Cluster is healthy"
        fi
    fi
    
    return 0
}

repair_manifests_apply() {
    echo "[REPAIR] Applying/reapplying Kubernetes manifests..."
    
    # Create namespace if it doesn't exist
    kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -
    
    # Apply manifests (idempotent operation)
    if [ -d "k8s/observability" ]; then
        kubectl apply -k k8s/observability/
    elif [ -d "k8s" ]; then
        kubectl apply -R -f k8s/
    else
        echo "[REPAIR] ✗ No Kubernetes manifests found in expected locations"
        return 1
    fi
    
    echo "[REPAIR] ✓ Manifests applied successfully"
    return 0
}

repair_pods_ready() {
    echo "[REPAIR] Checking pod health in observability namespace..."
    
    # Get unhealthy pods
    local unhealthy_pods
    unhealthy_pods=$(kubectl get pods -n observability --no-headers 2>/dev/null | \
                    grep -v "Running\|Completed" | awk '{print $1}' || echo "")
    
    if [ -n "$unhealthy_pods" ]; then
        echo "[REPAIR] Found unhealthy pods:"
        echo "$unhealthy_pods" | while read -r pod; do
            [ -n "$pod" ] && echo "  - $pod"
        done
        
        if [ "$REPAIR_AGGRESSIVE" = "true" ]; then
            echo "[REPAIR] Deleting unhealthy pods (they will be recreated)..."
            echo "$unhealthy_pods" | while read -r pod; do
                if [ -n "$pod" ]; then
                    kubectl delete pod "$pod" -n observability --grace-period=30
                fi
            done
        fi
        
        # Wait for pods to become ready
        echo "[REPAIR] Waiting for pods to become ready..."
        kubectl wait --for=condition=Ready pods --all -n observability --timeout=300s
    else
        echo "[REPAIR] ✓ All pods are healthy"
    fi
    
    return 0
}

repair_services_verify() {
    echo "[REPAIR] Verifying services in observability namespace..."
    
    local services=("grafana" "tempo" "mimir" "loki")
    local missing_services=()
    
    for svc in "${services[@]}"; do
        if ! kubectl get service "$svc" -n observability >/dev/null 2>&1; then
            missing_services+=("$svc")
        fi
    done
    
    if [ ${#missing_services[@]} -gt 0 ]; then
        echo "[REPAIR] Missing services: ${missing_services[*]}"
        echo "[REPAIR] Re-applying manifests to restore services..."
        repair_manifests_apply
    else
        echo "[REPAIR] ✓ All required services exist"
    fi
    
    return 0
}

repair_metrics_seed() {
    echo "[REPAIR] Checking metrics seeding capability..."
    
    # Verify tempo is running (needed for OTLP endpoint)
    if ! kubectl get pods -n observability -l app=tempo --no-headers | grep -q "Running"; then
        echo "[REPAIR] Tempo not running, ensuring pods are ready..."
        repair_pods_ready
    fi
    
    echo "[REPAIR] ✓ Metrics seeding components are ready"
    return 0
}

# ============================================================================
# Diagnostic Functions
# ============================================================================

diagnose_cluster() {
    echo "[DIAG] Cluster Diagnostics"
    echo "========================"
    
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        echo "✓ Kind cluster '${CLUSTER_NAME}' exists"
        
        if kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null 2>&1; then
            echo "✓ Cluster is accessible"
            
            # Get node information
            echo ""
            echo "Node Status:"
            kubectl get nodes --context "kind-${CLUSTER_NAME}" 2>/dev/null || echo "✗ Could not get node status"
            
            # Check resource usage
            echo ""
            echo "Resource Usage:"
            kubectl top nodes --context "kind-${CLUSTER_NAME}" 2>/dev/null || echo "  Metrics server not available"
        else
            echo "✗ Cluster exists but is not accessible"
        fi
    else
        echo "✗ Kind cluster '${CLUSTER_NAME}' not found"
    fi
    
    echo ""
}

diagnose_pods() {
    echo "[DIAG] Pod Diagnostics"
    echo "===================="
    
    if ! kubectl get namespace observability >/dev/null 2>&1; then
        echo "✗ Observability namespace does not exist"
        return
    fi
    
    echo "Pod Status:"
    kubectl get pods -n observability -o wide 2>/dev/null || echo "✗ Could not get pod status"
    
    echo ""
    echo "Pod Events (last 10):"
    kubectl get events -n observability --sort-by='.lastTimestamp' | tail -10 2>/dev/null || echo "✗ Could not get events"
    
    # Show logs for non-running pods
    local problem_pods
    problem_pods=$(kubectl get pods -n observability --no-headers 2>/dev/null | \
                  grep -v "Running\|Completed" | awk '{print $1}' || echo "")
    
    if [ -n "$problem_pods" ]; then
        echo ""
        echo "Logs for problematic pods:"
        echo "$problem_pods" | while read -r pod; do
            if [ -n "$pod" ]; then
                echo "--- Logs for $pod ---"
                kubectl logs "$pod" -n observability --tail=20 2>/dev/null || echo "Could not get logs for $pod"
                echo ""
            fi
        done
    fi
    
    echo ""
}

diagnose_networking() {
    echo "[DIAG] Networking Diagnostics"
    echo "============================"
    
    echo "Services:"
    kubectl get services -n observability 2>/dev/null || echo "✗ Could not get services"
    
    echo ""
    echo "Endpoints:"
    kubectl get endpoints -n observability 2>/dev/null || echo "✗ Could not get endpoints"
    
    echo ""
    echo "Service Connectivity Tests:"
    local services_ports=(
        "grafana:3000:/api/health"
        "tempo:3200:/ready"
        "mimir:9009:/ready"
        "loki:3100:/ready"
    )
    
    for svc_info in "${services_ports[@]}"; do
        local svc_name="${svc_info%%:*}"
        local port_path="${svc_info#*:}"
        local port="${port_path%%:*}"
        local path="${port_path#*:}"
        
        echo -n "  Testing $svc_name:$port$path ... "
        
        # Use kubectl port-forward in background to test connectivity
        kubectl port-forward -n observability "svc/$svc_name" "$port:$port" >/dev/null 2>&1 &
        local pf_pid=$!
        sleep 2
        
        if curl -sf "http://localhost:$port$path" >/dev/null 2>&1; then
            echo "✓ OK"
        else
            echo "✗ Failed"
        fi
        
        kill $pf_pid 2>/dev/null || true
        wait $pf_pid 2>/dev/null || true
    done
    
    echo ""
}

generate_diagnostic_report() {
    local report_file="$HOME/.contextcore/diagnostic-report.txt"
    
    {
        echo "ContextCore Installation Diagnostic Report"
        echo "=========================================="
        echo "Generated: $(date)"
        echo "Repair Mode: $REPAIR_MODE"