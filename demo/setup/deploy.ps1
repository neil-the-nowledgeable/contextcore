# ContextCore Demo Deployment Script for Windows
# Deploys a complete observability stack with microservices-demo
#
# Usage:
#   .\deploy.ps1                    Full deployment
#   .\deploy.ps1 -ClusterOnly       Only create Kind cluster
#   .\deploy.ps1 -ObservabilityOnly Only deploy observability stack
#   .\deploy.ps1 -DemoOnly          Only deploy microservices-demo
#   .\deploy.ps1 -DashboardsOnly    Only import Grafana dashboards

param(
    [switch]$ClusterOnly,
    [switch]$ObservabilityOnly,
    [switch]$DemoOnly,
    [switch]$DashboardsOnly,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$ClusterName = if ($env:CLUSTER_NAME) { $env:CLUSTER_NAME } else { "contextcore-demo" }

function Write-Info  { param([string]$Msg) Write-Host "[INFO] $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "[WARN] $Msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) Write-Host "[ERROR] $Msg" -ForegroundColor Red }

function Test-Prerequisites {
    Write-Info "Checking prerequisites..."
    $missing = @()

    foreach ($cmd in @("kind", "kubectl", "helm")) {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
            $missing += $cmd
        }
    }

    if ($missing.Count -gt 0) {
        Write-Err "Missing required tools: $($missing -join ', ')"
        Write-Host "Please install them before running this script:"
        Write-Host "  - kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
        Write-Host "  - kubectl: https://kubernetes.io/docs/tasks/tools/"
        Write-Host "  - helm: https://helm.sh/docs/intro/install/"
        exit 1
    }

    Write-Info "All prerequisites met"
}

function New-Cluster {
    Write-Info "Creating Kind cluster: $ClusterName"

    $existing = kind get clusters 2>$null
    if ($existing -contains $ClusterName) {
        Write-Warn "Cluster '$ClusterName' already exists"
        $reply = Read-Host "Delete and recreate? [y/N]"
        if ($reply -match "^[Yy]$") {
            kind delete cluster --name $ClusterName
        }
        else {
            Write-Info "Using existing cluster"
            kubectl cluster-info --context "kind-$ClusterName"
            return
        }
    }

    kind create cluster --config (Join-Path $ScriptDir "kind-cluster.yaml")
    Write-Info "Cluster created successfully"
}

function Add-HelmRepos {
    Write-Info "Adding Helm repositories..."
    helm repo add grafana https://grafana.github.io/helm-charts 2>$null
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>$null
    helm repo update
    Write-Info "Helm repositories updated"
}

function Install-Observability {
    Write-Info "Deploying observability stack..."

    # Create namespace
    kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -

    # Deploy Tempo
    Write-Info "  Deploying Tempo..."
    helm upgrade --install tempo grafana/tempo `
        --namespace observability `
        --set 'tempo.receivers.otlp.protocols.grpc.endpoint=0.0.0.0:4317' `
        --set 'tempo.receivers.otlp.protocols.http.endpoint=0.0.0.0:4318' `
        --wait --timeout 5m

    # Deploy Prometheus
    Write-Info "  Deploying Prometheus..."
    helm upgrade --install prometheus prometheus-community/prometheus `
        --namespace observability `
        --set server.service.type=NodePort `
        --set server.service.nodePort=30909 `
        --wait --timeout 5m

    # Deploy Grafana
    Write-Info "  Deploying Grafana..."
    helm upgrade --install grafana grafana/grafana `
        --namespace observability `
        --set service.type=NodePort `
        --set service.nodePort=30090 `
        --set adminPassword=admin `
        --set 'datasources.datasources\.yaml.apiVersion=1' `
        --set 'datasources.datasources\.yaml.datasources[0].name=Prometheus' `
        --set 'datasources.datasources\.yaml.datasources[0].type=prometheus' `
        --set 'datasources.datasources\.yaml.datasources[0].url=http://prometheus-server.observability.svc:80' `
        --set 'datasources.datasources\.yaml.datasources[0].isDefault=true' `
        --set 'datasources.datasources\.yaml.datasources[1].name=Tempo' `
        --set 'datasources.datasources\.yaml.datasources[1].type=tempo' `
        --set 'datasources.datasources\.yaml.datasources[1].url=http://tempo.observability.svc:3100' `
        --wait --timeout 5m

    Write-Info "Observability stack deployed"
}

function Install-CRD {
    Write-Info "Applying ContextCore CRD..."
    $crdPath = Join-Path $ProjectDir "crds" "projectcontext.yaml"
    if (Test-Path $crdPath) {
        kubectl apply -f $crdPath
        Write-Info "ProjectContext CRD applied"
    }
    else {
        Write-Warn "CRD file not found at $crdPath"
    }
}

function Install-MicroservicesDemo {
    Write-Info "Deploying microservices-demo..."

    kubectl create namespace online-boutique --dry-run=client -o yaml | kubectl apply -f -

    $overlayPath = Join-Path $ProjectDir "demo" "manifests" "overlays" "contextcore"
    if (Test-Path $overlayPath) {
        Write-Info "  Using ContextCore Kustomize overlay..."
        kubectl apply -k $overlayPath -n online-boutique
    }
    else {
        Write-Info "  Deploying vanilla microservices-demo..."
        kubectl apply -f "https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/main/release/kubernetes-manifests.yaml" -n online-boutique
    }

    # Apply ProjectContext resources
    Write-Info "  Applying ProjectContext resources..."
    $pcDir = Join-Path $ProjectDir "demo" "projectcontexts"
    if (Test-Path $pcDir) {
        Get-ChildItem -Path $pcDir -Filter "*.yaml" | ForEach-Object {
            try {
                kubectl apply -f $_.FullName -n online-boutique 2>$null
            }
            catch {
                Write-Warn "Failed to apply $($_.Name)"
            }
        }
    }

    Write-Info "microservices-demo deployed"
}

function Import-Dashboards {
    Write-Info "Importing Grafana dashboards..."

    # Wait for Grafana
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=grafana -n observability --timeout=120s

    # Get Grafana pod name
    $grafanaPod = kubectl get pods -n observability -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}'

    # Port forward in background
    $portForward = Start-Process -NoNewWindow -PassThru kubectl -ArgumentList "port-forward -n observability $grafanaPod 3001:3000"
    Start-Sleep -Seconds 3

    try {
        $dashboardDir = Join-Path $ProjectDir "demo" "dashboards"
        if (Test-Path $dashboardDir) {
            $cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:admin"))
            $headers = @{
                Authorization  = "Basic $cred"
                "Content-Type" = "application/json"
            }

            Get-ChildItem -Path $dashboardDir -Filter "*.json" | ForEach-Object {
                Write-Info "  Importing $($_.Name)..."
                try {
                    $content = Get-Content $_.FullName -Raw | ConvertFrom-Json
                    $body = @{ dashboard = $content; overwrite = $true } | ConvertTo-Json -Depth 20
                    Invoke-RestMethod -Uri "http://localhost:3001/api/dashboards/db" -Method Post -Headers $headers -Body $body -TimeoutSec 10 | Out-Null
                }
                catch {
                    Write-Warn "Failed to import $($_.Name)"
                }
            }
        }
    }
    finally {
        # Stop port forward
        if ($portForward -and -not $portForward.HasExited) {
            $portForward.Kill()
        }
    }

    Write-Info "Dashboards imported"
}

function Write-Summary {
    Write-Host ""
    Write-Host "=============================================="
    Write-Host "  ContextCore Demo Deployment Complete!"
    Write-Host "=============================================="
    Write-Host ""
    Write-Host "Access points:"
    Write-Host "  - Online Boutique: http://localhost:8080"
    Write-Host "  - Grafana:         http://localhost:3000 (admin/admin)"
    Write-Host "  - Prometheus:      http://localhost:9090"
    Write-Host "  - OTLP gRPC:       localhost:4317"
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Generate demo data:"
    Write-Host "     contextcore demo generate"
    Write-Host ""
    Write-Host "  2. Load spans to Tempo:"
    Write-Host "     contextcore demo load --file .\demo_output\demo_spans.json"
    Write-Host ""
    Write-Host "  3. View dashboards in Grafana"
    Write-Host ""
    Write-Host "  4. Explore ProjectContext resources:"
    Write-Host "     kubectl get projectcontext -n online-boutique"
}

# === Main ===

if ($Help) {
    Write-Host "Usage: .\deploy.ps1 [option]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  (no option)         Full deployment"
    Write-Host "  -ClusterOnly        Only create Kind cluster"
    Write-Host "  -ObservabilityOnly  Only deploy observability stack"
    Write-Host "  -DemoOnly           Only deploy microservices-demo"
    Write-Host "  -DashboardsOnly     Only import Grafana dashboards"
    Write-Host "  -Help               Show this help"
    exit 0
}

if ($ClusterOnly) {
    Test-Prerequisites
    New-Cluster
}
elseif ($ObservabilityOnly) {
    Test-Prerequisites
    Add-HelmRepos
    Install-Observability
}
elseif ($DemoOnly) {
    Test-Prerequisites
    Install-CRD
    Install-MicroservicesDemo
}
elseif ($DashboardsOnly) {
    Import-Dashboards
}
else {
    # Full deployment
    Write-Host "=============================================="
    Write-Host "  ContextCore Demo Setup"
    Write-Host "=============================================="
    Write-Host ""

    Test-Prerequisites
    New-Cluster
    Add-HelmRepos
    Install-Observability
    Install-CRD
    Install-MicroservicesDemo
    Import-Dashboards
    Write-Summary
}
