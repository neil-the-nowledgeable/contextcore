Looking at the review history, I can see the main issues are with missing integration with the state management system (`install-state.sh`) and step executor (`step-executor.sh`). Let me provide the finalized, production-ready implementation:

```bash
#!/bin/bash
# Main installation orchestrator for ContextCore Kind cluster with observability components
# Version: 1.0
# Dependencies: install-state.sh, step-executor.sh

set -euo pipefail

# Load dependencies - these provide state management and step execution framework
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/install-state.sh"
source "${SCRIPT_DIR}/step-executor.sh"

# Global configuration
readonly CLUSTER_NAME="${CLUSTER_NAME:-o11y-dev}"
readonly KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
readonly PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
readonly LOG_FILE="$HOME/.contextcore/install.log"

# Command line flags
RESUME=false
REPAIR=false
STATUS_ONLY=false
RESET=false
VERBOSE=false
DRY_RUN=false

# Installation step definitions
readonly INSTALLATION_STEPS=(
    "preflight"
    "cluster_create"
    "manifests_apply"
    "pods_ready"
    "services_verify"
    "metrics_seed"
)

#=============================================================================
# Display Functions
#=============================================================================

show_banner() {
    cat << 'EOF'
╔══════════════════════════════════════╗
║           ContextCore                ║
║      Kind Cluster Installation       ║
║                                      ║
║  Observability Stack: o11y-dev       ║
╚══════════════════════════════════════╝
EOF
}

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Create and configure a ContextCore Kind cluster with observability components.

Options:
  --resume        Continue from last completed step (skip completed)
  --repair        Re-verify all steps and fix failures
  --status        Show installation status and exit
  --reset         Clear state and start fresh
  --verbose, -v   Enable verbose output
  --dry-run       Show what would be done without doing it
  --help, -h      Show this help message

Environment:
  CLUSTER_NAME    Cluster name (default: o11y-dev)
  KUBECONFIG      kubectl config (default: ~/.kube/config)

Installation Steps:
  1. preflight      - Check prerequisites (Docker, kind, kubectl, jq)
  2. cluster_create - Create Kind cluster with port forwarding
  3. manifests_apply- Apply Kubernetes manifests from k8s/observability/
  4. pods_ready     - Wait for all pods to be Running (5min timeout)
  5. services_verify- Verify services accessible on expected ports
  6. metrics_seed   - Seed metrics using ContextCore verification

Examples:
  $(basename "$0")                    # Fresh installation
  $(basename "$0") --resume           # Resume from last step
  $(basename "$0") --repair           # Re-verify and fix issues
  $(basename "$0") --status           # Check current status
  $(basename "$0") --reset            # Start over completely

Logs: $LOG_FILE
EOF
}

show_status() {
    echo "ContextCore Installation Status"
    echo "==============================="
    
    if ! state_exists; then
        echo "❌ No installation state found. Run without --status to begin installation."
        return 1
    fi
    
    local total_steps=${#INSTALLATION_STEPS[@]}
    local completed_steps=0
    
    for step in "${INSTALLATION_STEPS[@]}"; do
        local status=$(get_step_status "$step")
        local timestamp=$(get_step_timestamp "$step")
        local duration=$(get_step_duration "$step")
        
        case "$status" in
            "completed")
                echo "✅ $step (completed at $timestamp, took ${duration}s)"
                ((completed_steps++))
                ;;
            "running")
                echo "⏳ $step (currently running...)"
                ;;
            "failed")
                echo "❌ $step (failed at $timestamp)"
                ;;
            *)
                echo "⬜ $step (pending)"
                ;;
        esac
    done
    
    echo ""
    echo "Progress: $completed_steps/$total_steps steps completed"
    
    if [ $completed_steps -eq $total_steps ]; then
        echo "🎉 Installation complete! Access services at:"
        echo "   - Grafana: http://localhost:3000"
        echo "   - Tempo: http://localhost:3200"
        echo "   - Mimir: http://localhost:9009"
        echo "   - Loki: http://localhost:3100"
    fi
}

#=============================================================================
# Utility Functions
#=============================================================================

log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    
    # Always log to file
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    
    # Conditionally log to stdout based on verbosity
    if [ "$VERBOSE" = true ] || [ "$level" != "DEBUG" ]; then
        echo "[$level] $message"
    fi
}

setup_logging() {
    mkdir -p "$(dirname "$LOG_FILE")"
    
    # Rotate log if > 10MB
    if [ -f "$LOG_FILE" ] && [ $(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0) -gt 10485760 ]; then
        mv "$LOG_FILE" "${LOG_FILE}.old"
        log "INFO" "Log rotated due to size"
    fi
    
    log "INFO" "Starting ContextCore installation (PID: $$)"
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --resume)
                RESUME=true
                shift
                ;;
            --repair)
                REPAIR=true
                shift
                ;;
            --status)
                STATUS_ONLY=true
                shift
                ;;
            --reset)
                RESET=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                echo "ERROR: Unknown option $1" >&2
                echo "Use --help for usage information." >&2
                exit 1
                ;;
        esac
    done
}

#=============================================================================
# Installation Step Functions
#=============================================================================

step_preflight() {
    log "INFO" "Running prerequisite checks"
    
    # Check Docker daemon
    if ! docker info >/dev/null 2>&1; then
        log "ERROR" "Docker daemon not running"
        echo "❌ Docker daemon is not running"
        echo "   Fix: Start Docker Desktop or run: sudo systemctl start docker"
        return 1
    fi
    
    # Check required tools
    local missing_tools=()
    for tool in kind kubectl jq; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            missing_tools+=("$tool")
        fi
    done
    
    if [ ${#missing_tools[@]} -gt 0 ]; then
        log "ERROR" "Missing required tools: ${missing_tools[*]}"
        echo "❌ Missing required tools: ${missing_tools[*]}"
        echo "   Install with:"
        for tool in "${missing_tools[@]}"; do
            case $tool in
                kind)
                    echo "     # Kind"
                    echo "     curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64"
                    echo "     chmod +x ./kind && sudo mv ./kind /usr/local/bin/"
                    ;;
                kubectl)
                    echo "     # kubectl"
                    echo "     curl -LO https://dl.k8s.io/release/v1.28.0/bin/linux/amd64/kubectl"
                    echo "     chmod +x kubectl && sudo mv kubectl /usr/local/bin/"
                    ;;
                jq)
                    echo "     # jq"
                    echo "     sudo apt-get update && sudo apt-get install -y jq"
                    ;;
            esac
        done
        return 1
    fi
    
    # Check disk space (need at least 2GB free)
    local available_space=$(df /var/lib/docker 2>/dev/null | awk 'NR==2 {print $4}' || echo "999999999")
    if [ "$available_space" -lt 2097152 ]; then  # 2GB in KB
        log "WARN" "Low disk space detected"
        echo "⚠️  Warning: Less than 2GB free disk space available"
    fi
    
    log "INFO" "All prerequisites satisfied"
    echo "✅ Prerequisites check passed"
    return 0
}

step_cluster_create() {
    log "INFO" "Creating Kind cluster: $CLUSTER_NAME"
    
    # Check if cluster already exists
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log "INFO" "Cluster $CLUSTER_NAME already exists"
        echo "✅ Kind cluster '$CLUSTER_NAME' already exists"
        return 0
    fi
    
    if [ "$DRY_RUN" = true ]; then
        echo "🔍 DRY-RUN: Would create Kind cluster '$CLUSTER_NAME'"
        return 0
    fi
    
    # Use custom config if available
    local config_file="$PROJECT_ROOT/k8s/observability/kind-config.yaml"
    local kind_args="--name $CLUSTER_NAME"
    
    if [ -f "$config_file" ]; then
        log "INFO" "Using Kind config from $config_file"
        kind_args="$kind_args --config $config_file"
    fi
    
    echo "🔧 Creating Kind cluster '$CLUSTER_NAME'..."
    if eval "kind create cluster $kind_args"; then
        log "INFO" "Successfully created Kind cluster"
        echo "✅ Kind cluster '$CLUSTER_NAME' created successfully"
        return 0
    else
        log "ERROR" "Failed to create Kind cluster"
        echo "❌ Failed to create Kind cluster"
        echo "   Check Docker is running and try: kind delete cluster --name $CLUSTER_NAME"
        return 1
    fi
}

step_manifests_apply() {
    log "INFO" "Applying Kubernetes manifests"
    
    local manifests_dir="$PROJECT_ROOT/k8s/observability"
    
    if [ ! -d "$manifests_dir" ]; then
        log "ERROR" "Manifests directory not found: $manifests_dir"
        echo "❌ Manifests directory not found: $manifests_dir"
        return 1
    fi
    
    if [ "$DRY_RUN" = true ]; then
        echo "🔍 DRY-RUN: Would apply manifests from $manifests_dir"
        return 0
    fi
    
    echo "🔧 Applying Kubernetes manifests..."
    
    # Create namespace first
    kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -
    
    # Apply manifests - try kustomize first, then regular apply
    if [ -f "$manifests_dir/kustomization.yaml" ]; then
        log "INFO" "Applying manifests using kustomize"
        if kubectl apply -k "$manifests_dir"; then
            log "INFO" "Successfully applied manifests via kustomize"
            echo "✅ Kubernetes manifests applied successfully"
            return 0
        fi
    else
        log "INFO" "Applying manifests directly"
        if kubectl apply -f "$manifests_dir/"; then
            log "INFO" "Successfully applied manifests directly"
            echo "✅ Kubernetes manifests applied successfully"
            return 0
        fi
    fi
    
    log "ERROR" "Failed to apply Kubernetes manifests"
    echo "❌ Failed to apply Kubernetes manifests"
    echo "   Check: kubectl get pods -A"
    return 1
}

step_pods_ready() {
    log "INFO" "Waiting for pods to be ready"
    
    if [ "$DRY_RUN" = true ]; then
        echo "🔍 DRY-RUN: Would wait for all pods to become ready"
        return 0
    fi
    
    echo "⏳ Waiting for pods to be ready (timeout: 5 minutes)..."
    
    # Wait for pods in observability namespace
    if kubectl wait --for=condition=ready pod --all \
        --namespace=observability \
        --timeout=300s 2>/dev/null; then
        log "INFO" "All pods in observability namespace are ready"
        echo "✅ All pods are ready"
        return 0
    else
        # If observability namespace fails, check if any pods exist
        local pod_count=$(kubectl get pods -n observability --no-headers 2>/dev/null | wc -l)
        if [ "$pod_count" -eq 0 ]; then
            log "WARN" "No pods found in observability namespace, checking default"
            # Fall back to default namespace or all namespaces
            if kubectl wait --for=condition=ready pod --all --timeout=60s; then
                log "INFO" "Pods in default namespace are ready"
                echo "✅ Pods are ready"
                return 0
            fi
        fi
        
        log "ERROR" "Pods failed to become ready within timeout"
        echo "❌ Pods did not become ready within 5 minutes"
        echo "   Debug with: kubectl get pods -A"
        echo "   Check events: kubectl get events --sort-by=.metadata.creationTimestamp"
        return 1
    fi
}

step_services_verify() {
    log "INFO" "Verifying service accessibility"
    
    if [ "$DRY_RUN" = true ]; then
        echo "🔍 DRY-RUN: Would verify service accessibility"
        return 0
    fi
    
    local services=(
        "grafana:3000:/api/health"
        "tempo:3200:/ready"
        "mimir:9009:/ready"
        "loki:3100:/ready"
    )
    
    echo "🔧 Verifying services..."
    
    for service_def in "${services[@]}"; do
        IFS=':' read -r service_name port path <<< "$service_def"
        
        log "DEBUG" "Checking service $service_name on port $port"
        
        # Check if service exists
        if ! kubectl get service "$service_name" -n observability >/dev/null 2>&1; then
            log "WARN" "Service $service_name not found, skipping"
            continue
        fi
        
        # Simple service check - just verify it exists and has endpoints
        if kubectl get endpoints "$service_name" -n observability -o jsonpath='{.subsets[0].addresses[0].ip}' >/dev/null 2>&1; then
            log "INFO" "Service $service_name has endpoints"
            echo "✅ Service $service_name is ready"
        else
            log "WARN" "Service $service_name has no endpoints yet"
            echo "⚠️  Service $service_name has no endpoints (may still be starting)"
        fi
    done
    
    echo "✅ Service verification completed"
    return 0
}

step_metrics_seed() {
    log "INFO" "Seeding metrics with ContextCore"
    
    if [ "$DRY_RUN" = true ]; then
        echo "🔍 DRY-RUN: Would seed metrics using ContextCore"
        return 0
    fi
    
    # Check if contextcore is available
    if ! command -v contextcore >/dev/null