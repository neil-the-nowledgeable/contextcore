#!/bin/bash
# ContextCore Demo Deployment Script
# Deploys a complete observability stack with microservices-demo

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
CLUSTER_NAME="${CLUSTER_NAME:-contextcore-demo}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    local missing=()

    for cmd in kind kubectl helm; do
        if ! command -v $cmd &> /dev/null; then
            missing+=($cmd)
        fi
    done

    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing[*]}"
        echo "Please install them before running this script:"
        echo "  - kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
        echo "  - kubectl: https://kubernetes.io/docs/tasks/tools/"
        echo "  - helm: https://helm.sh/docs/intro/install/"
        exit 1
    fi

    log_info "All prerequisites met"
}

create_cluster() {
    log_info "Creating Kind cluster: $CLUSTER_NAME"

    if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
        log_warn "Cluster '$CLUSTER_NAME' already exists"
        read -p "Delete and recreate? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kind delete cluster --name "$CLUSTER_NAME"
        else
            log_info "Using existing cluster"
            kubectl cluster-info --context "kind-${CLUSTER_NAME}"
            return
        fi
    fi

    kind create cluster --config "$SCRIPT_DIR/kind-cluster.yaml"
    log_info "Cluster created successfully"
}

add_helm_repos() {
    log_info "Adding Helm repositories..."

    helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
    helm repo update

    log_info "Helm repositories updated"
}

deploy_observability() {
    log_info "Deploying observability stack..."

    # Create namespace
    kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -

    # Deploy Tempo (traces)
    log_info "  Deploying Tempo..."
    helm upgrade --install tempo grafana/tempo \
        --namespace observability \
        --set tempo.receivers.otlp.protocols.grpc.endpoint="0.0.0.0:4317" \
        --set tempo.receivers.otlp.protocols.http.endpoint="0.0.0.0:4318" \
        --wait --timeout 5m

    # Deploy Prometheus (metrics)
    log_info "  Deploying Prometheus..."
    helm upgrade --install prometheus prometheus-community/prometheus \
        --namespace observability \
        --set server.service.type=NodePort \
        --set server.service.nodePort=30909 \
        --wait --timeout 5m

    # Deploy Grafana
    log_info "  Deploying Grafana..."
    helm upgrade --install grafana grafana/grafana \
        --namespace observability \
        --set service.type=NodePort \
        --set service.nodePort=30090 \
        --set adminPassword=admin \
        --set "datasources.datasources\\.yaml.apiVersion=1" \
        --set "datasources.datasources\\.yaml.datasources[0].name=Prometheus" \
        --set "datasources.datasources\\.yaml.datasources[0].type=prometheus" \
        --set "datasources.datasources\\.yaml.datasources[0].url=http://prometheus-server.observability.svc:80" \
        --set "datasources.datasources\\.yaml.datasources[0].isDefault=true" \
        --set "datasources.datasources\\.yaml.datasources[1].name=Tempo" \
        --set "datasources.datasources\\.yaml.datasources[1].type=tempo" \
        --set "datasources.datasources\\.yaml.datasources[1].url=http://tempo.observability.svc:3100" \
        --wait --timeout 5m

    log_info "Observability stack deployed"
}

apply_crd() {
    log_info "Applying ContextCore CRD..."

    if [ -f "$PROJECT_DIR/crds/projectcontext.yaml" ]; then
        kubectl apply -f "$PROJECT_DIR/crds/projectcontext.yaml"
        log_info "ProjectContext CRD applied"
    else
        log_warn "CRD file not found at $PROJECT_DIR/crds/projectcontext.yaml"
    fi
}

deploy_microservices_demo() {
    log_info "Deploying microservices-demo..."

    # Create namespace
    kubectl create namespace online-boutique --dry-run=client -o yaml | kubectl apply -f -

    # Deploy using Kustomize overlay if available
    if [ -d "$PROJECT_DIR/demo/manifests/overlays/contextcore" ]; then
        log_info "  Using ContextCore Kustomize overlay..."
        kubectl apply -k "$PROJECT_DIR/demo/manifests/overlays/contextcore" -n online-boutique
    else
        log_info "  Deploying vanilla microservices-demo..."
        kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/main/release/kubernetes-manifests.yaml -n online-boutique
    fi

    # Apply ProjectContext resources
    log_info "  Applying ProjectContext resources..."
    for pc in "$PROJECT_DIR/demo/projectcontexts/"*.yaml; do
        if [ -f "$pc" ]; then
            kubectl apply -f "$pc" -n online-boutique 2>/dev/null || log_warn "Failed to apply $(basename "$pc")"
        fi
    done

    log_info "microservices-demo deployed"
}

import_dashboards() {
    log_info "Importing Grafana dashboards..."

    # Wait for Grafana to be ready
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=grafana -n observability --timeout=120s

    # Get Grafana pod name
    GRAFANA_POD=$(kubectl get pods -n observability -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')

    # Port forward in background
    kubectl port-forward -n observability "$GRAFANA_POD" 3001:3000 &
    PF_PID=$!
    sleep 3

    # Import dashboards via Grafana API
    for dashboard in "$PROJECT_DIR/demo/dashboards/"*.json; do
        if [ -f "$dashboard" ]; then
            log_info "  Importing $(basename "$dashboard")..."
            curl -s -X POST \
                -H "Content-Type: application/json" \
                -u admin:admin \
                -d "{\"dashboard\": $(cat "$dashboard"), \"overwrite\": true}" \
                http://localhost:3001/api/dashboards/db > /dev/null 2>&1 || \
                log_warn "Failed to import $(basename "$dashboard")"
        fi
    done

    # Kill port forward
    kill $PF_PID 2>/dev/null || true

    log_info "Dashboards imported"
}

print_summary() {
    echo ""
    echo "=============================================="
    echo "  ContextCore Demo Deployment Complete!"
    echo "=============================================="
    echo ""
    echo "Access points:"
    echo "  - Online Boutique: http://localhost:8080"
    echo "  - Grafana:         http://localhost:3000 (admin/admin)"
    echo "  - Prometheus:      http://localhost:9090"
    echo "  - OTLP gRPC:       localhost:4317"
    echo ""
    echo "Next steps:"
    echo "  1. Generate demo data:"
    echo "     contextcore demo generate"
    echo ""
    echo "  2. Load spans to Tempo:"
    echo "     contextcore demo load --file ./demo_output/demo_spans.json"
    echo ""
    echo "  3. View dashboards in Grafana:"
    echo "     - ContextCore: Project Progress"
    echo "     - ContextCore: Sprint Metrics"
    echo "     - ContextCore: Project-to-Operations"
    echo ""
    echo "  4. Explore ProjectContext resources:"
    echo "     kubectl get projectcontext -n online-boutique"
    echo ""
}

# Main
main() {
    echo "=============================================="
    echo "  ContextCore Demo Setup"
    echo "=============================================="
    echo ""

    check_prerequisites
    create_cluster
    add_helm_repos
    deploy_observability
    apply_crd
    deploy_microservices_demo
    import_dashboards
    print_summary
}

# Parse arguments
case "${1:-}" in
    --cluster-only)
        check_prerequisites
        create_cluster
        ;;
    --observability-only)
        check_prerequisites
        add_helm_repos
        deploy_observability
        ;;
    --demo-only)
        check_prerequisites
        apply_crd
        deploy_microservices_demo
        ;;
    --dashboards-only)
        import_dashboards
        ;;
    --help|-h)
        echo "Usage: $0 [option]"
        echo ""
        echo "Options:"
        echo "  (no option)         Full deployment"
        echo "  --cluster-only      Only create Kind cluster"
        echo "  --observability-only Only deploy observability stack"
        echo "  --demo-only         Only deploy microservices-demo"
        echo "  --dashboards-only   Only import Grafana dashboards"
        echo "  --help              Show this help"
        exit 0
        ;;
    *)
        main
        ;;
esac
