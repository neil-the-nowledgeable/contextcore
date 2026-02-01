# ContextCore Setup Script for Windows
# PowerShell equivalent of the Makefile targets
#
# Usage:
#   .\setup.ps1 help          Show available commands
#   .\setup.ps1 doctor        Preflight checks
#   .\setup.ps1 up            Start the stack (runs doctor first)
#   .\setup.ps1 down          Stop (preserve data)
#   .\setup.ps1 destroy       Delete (auto-backup, confirm)
#   .\setup.ps1 health        One-line status per component
#   .\setup.ps1 smoke-test    Validate entire stack
#   .\setup.ps1 full-setup    Complete setup: start, wait, seed metrics

param(
    [Parameter(Position = 0)]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"

# Configuration
$ComposeFile = "docker-compose.yaml"
$RequiredPorts = @(3000, 3100, 3200, 9009, 4317, 4318)
$DataDir = "data"

# Environment configuration (can be overridden)
$GrafanaUrl = if ($env:GRAFANA_URL) { $env:GRAFANA_URL } else { "http://localhost:3000" }
$GrafanaUser = if ($env:GRAFANA_USER) { $env:GRAFANA_USER } else { "admin" }
$GrafanaPassword = if ($env:GRAFANA_PASSWORD) { $env:GRAFANA_PASSWORD } else { "admin" }
$OtlpEndpoint = if ($env:OTLP_ENDPOINT) { $env:OTLP_ENDPOINT } else { "localhost:4317" }

function Write-Status {
    param([string]$Status, [string]$Message)
    switch ($Status) {
        "ok"   { Write-Host "  [OK] $Message" -ForegroundColor Green }
        "fail" { Write-Host "  [FAIL] $Message" -ForegroundColor Red }
        "warn" { Write-Host "  [WARN] $Message" -ForegroundColor Yellow }
        "info" { Write-Host "  [INFO] $Message" -ForegroundColor Cyan }
    }
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-PortInUse {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $connection
}

function Test-UrlReady {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

# === Preflight Checks ===

function Invoke-Doctor {
    Write-Host "=== Preflight Check ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Checking required tools..."

    if (Test-CommandAvailable "docker") { Write-Status "ok" "docker" }
    else { Write-Status "fail" "docker not found" }

    if (Test-CommandAvailable "docker-compose") { Write-Status "ok" "docker-compose" }
    elseif ((Test-CommandAvailable "docker") -and (docker compose version 2>$null)) { Write-Status "ok" "docker compose" }
    else { Write-Status "fail" "docker-compose not found" }

    if (Test-CommandAvailable "python") { Write-Status "ok" "python" }
    elseif (Test-CommandAvailable "python3") { Write-Status "ok" "python3" }
    elseif (Test-CommandAvailable "py") { Write-Status "ok" "py (launcher)" }
    else { Write-Status "fail" "python not found" }

    Write-Host ""
    Write-Host "Checking Docker daemon..."
    try {
        docker info 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Status "ok" "Docker is running" }
        else { Write-Status "fail" "Docker is not running" }
    }
    catch { Write-Status "fail" "Docker is not running" }

    Write-Host ""
    Write-Host "Checking port availability..."
    foreach ($port in $RequiredPorts) {
        if (Test-PortInUse $port) {
            Write-Status "fail" "Port $port is in use"
        }
        else {
            Write-Status "ok" "Port $port is available"
        }
    }

    Write-Host ""
    Write-Host "Checking data directories..."
    foreach ($dir in @("tempo", "mimir", "loki", "grafana")) {
        $path = Join-Path $DataDir $dir
        if (Test-Path $path) {
            Write-Status "ok" "$path exists"
        }
        else {
            Write-Status "warn" "$path will be created"
        }
    }

    Write-Host ""
    Write-Host "=== Preflight Complete ===" -ForegroundColor Cyan
}

# === Stack Management ===

function Invoke-Up {
    Invoke-Doctor
    Write-Host ""
    Write-Host "=== Starting ContextCore Stack ===" -ForegroundColor Cyan

    # Create data directories
    foreach ($dir in @("tempo", "mimir", "loki", "grafana")) {
        $path = Join-Path $DataDir $dir
        if (-not (Test-Path $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }

    if (Test-Path $ComposeFile) {
        docker compose -f $ComposeFile up -d
        Write-Status "ok" "Stack started. Run '.\setup.ps1 health' to verify."
    }
    else {
        Write-Status "warn" "No $ComposeFile found."
        Write-Host "  Stack can be started with: docker compose up -d"
    }
}

function Invoke-Down {
    Write-Host "=== Stopping ContextCore Stack ===" -ForegroundColor Cyan
    if (Test-Path $ComposeFile) {
        docker compose -f $ComposeFile down
        Write-Status "ok" "Stack stopped. Data preserved in $DataDir/."
        Write-Host "  Run '.\setup.ps1 up' to restart."
    }
    else {
        Write-Host "No $ComposeFile found."
    }
}

function Invoke-Destroy {
    Write-Host "=== DESTROY ContextCore Stack ===" -ForegroundColor Red
    Write-Host ""
    Write-Host "WARNING: This will delete all ContextCore data!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The following will be destroyed:"
    Write-Host "  - All spans in Tempo ($DataDir/tempo)"
    Write-Host "  - All metrics in Mimir ($DataDir/mimir)"
    Write-Host "  - All logs in Loki ($DataDir/loki)"
    Write-Host "  - Grafana dashboards and settings ($DataDir/grafana)"
    Write-Host ""

    Write-Host "Creating backup before destroy..."
    try { Invoke-Backup } catch { Write-Status "warn" "Backup may be incomplete" }

    Write-Host ""
    $confirm = Read-Host "Are you sure? Type 'yes' to confirm"
    if ($confirm -ne "yes") {
        Write-Host "Aborted."
        return
    }

    if (Test-Path $ComposeFile) {
        docker compose -f $ComposeFile down -v
    }
    if (Test-Path $DataDir) {
        Remove-Item -Recurse -Force $DataDir
    }
    Write-Status "ok" "Stack destroyed. Run '.\setup.ps1 up' for fresh start."
}

# === Health & Validation ===

function Invoke-Health {
    Write-Host "=== Component Health ===" -ForegroundColor Cyan

    $components = @(
        @{ Name = "Grafana";      Url = "http://localhost:3000/api/health" },
        @{ Name = "Tempo";        Url = "http://localhost:3200/ready" },
        @{ Name = "Mimir";        Url = "http://localhost:9009/ready" },
        @{ Name = "Loki";         Url = "http://localhost:3100/ready" },
        @{ Name = "Alloy";        Url = "http://localhost:12345/ready" }
    )

    foreach ($c in $components) {
        $padded = $c.Name.PadRight(12)
        if (Test-UrlReady $c.Url) {
            Write-Host "  ${padded}: " -NoNewline; Write-Host "Ready" -ForegroundColor Green
        }
        else {
            Write-Host "  ${padded}: " -NoNewline; Write-Host "Not Ready" -ForegroundColor Red
        }
    }

    # Check OTLP ports
    $grpcPad = "OTLP (gRPC)".PadRight(12)
    if (Test-PortInUse 4317) {
        Write-Host "  ${grpcPad}: " -NoNewline; Write-Host "Listening (Alloy)" -ForegroundColor Green
    }
    else {
        Write-Host "  ${grpcPad}: " -NoNewline; Write-Host "Not Listening" -ForegroundColor Red
    }

    $httpPad = "OTLP (HTTP)".PadRight(12)
    if (Test-PortInUse 4318) {
        Write-Host "  ${httpPad}: " -NoNewline; Write-Host "Listening (Alloy)" -ForegroundColor Green
    }
    else {
        Write-Host "  ${httpPad}: " -NoNewline; Write-Host "Not Listening" -ForegroundColor Red
    }
}

function Invoke-SmokeTest {
    Write-Host "=== Smoke Test ===" -ForegroundColor Cyan
    Write-Host ""

    $passed = 0
    $total = 7

    # 1. Grafana
    Write-Host "1. Checking Grafana..."
    if (Test-UrlReady "$GrafanaUrl/api/health") { Write-Status "ok" "Grafana responding"; $passed++ }
    else { Write-Status "fail" "Grafana not accessible" }

    # 2. Tempo
    Write-Host "2. Checking Tempo..."
    if (Test-UrlReady "http://localhost:3200/ready") { Write-Status "ok" "Tempo responding"; $passed++ }
    else { Write-Status "fail" "Tempo not accessible" }

    # 3. Mimir
    Write-Host "3. Checking Mimir..."
    if (Test-UrlReady "http://localhost:9009/ready") { Write-Status "ok" "Mimir responding"; $passed++ }
    else { Write-Status "fail" "Mimir not accessible" }

    # 4. Loki
    Write-Host "4. Checking Loki..."
    if (Test-UrlReady "http://localhost:3100/ready") { Write-Status "ok" "Loki responding"; $passed++ }
    else { Write-Status "fail" "Loki not accessible" }

    # 5. Alloy
    Write-Host "5. Checking Alloy (OTLP collector)..."
    if (Test-UrlReady "http://localhost:12345/ready") { Write-Status "ok" "Alloy responding (OTLP on 4317/4318)"; $passed++ }
    else { Write-Status "fail" "Alloy not accessible" }

    # 6. Datasources
    Write-Host "6. Checking Grafana datasources..."
    try {
        $cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${GrafanaUser}:${GrafanaPassword}"))
        $response = Invoke-WebRequest -Uri "$GrafanaUrl/api/datasources" -Headers @{ Authorization = "Basic $cred" } -UseBasicParsing -TimeoutSec 5
        if ($response.Content -match "tempo|mimir|loki") { Write-Status "ok" "Datasources configured"; $passed++ }
        else { Write-Status "warn" "Datasources may need provisioning" }
    }
    catch { Write-Status "warn" "Datasources may need provisioning" }

    # 7. CLI
    Write-Host "7. Checking ContextCore CLI..."
    $pythonCmd = if (Test-CommandAvailable "python3") { "python3" }
                 elseif (Test-CommandAvailable "python") { "python" }
                 else { "py" }
    try {
        $env:PYTHONPATH = Join-Path (Get-Location) "src"
        & $pythonCmd -c "from contextcore import TaskTracker; print('ok')" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Status "ok" "ContextCore CLI available"; $passed++ }
        else { Write-Status "fail" "ContextCore CLI not installed" }
    }
    catch { Write-Status "fail" "ContextCore CLI not installed" }

    Write-Host ""
    Write-Host "=== Smoke Test Complete: $passed/$total passed ===" -ForegroundColor Cyan
}

function Invoke-WaitReady {
    Write-Host "=== Waiting for Services ===" -ForegroundColor Cyan
    Write-Host ""

    $urls = @(
        "$GrafanaUrl/api/health",
        "http://localhost:3200/ready",
        "http://localhost:9009/ready",
        "http://localhost:3100/ready",
        "http://localhost:12345/ready"
    )

    for ($i = 1; $i -le 30; $i++) {
        $allReady = $true
        foreach ($url in $urls) {
            if (-not (Test-UrlReady $url)) { $allReady = $false; break }
        }

        if ($allReady) {
            Write-Host "All services ready!" -ForegroundColor Green
            return
        }

        Write-Host "  Waiting... ($i/30)"
        Start-Sleep -Seconds 2
    }

    Write-Host "Timeout waiting for services" -ForegroundColor Red
    exit 1
}

function Invoke-SeedMetrics {
    Write-Host "=== Seeding Installation Metrics ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Running installation verification with telemetry export..."

    $pythonCmd = if (Test-CommandAvailable "python3") { "python3" }
                 elseif (Test-CommandAvailable "python") { "python" }
                 else { "py" }

    $env:GRAFANA_URL = $GrafanaUrl
    $env:GRAFANA_USER = $GrafanaUser
    $env:GRAFANA_PASSWORD = $GrafanaPassword
    $env:PYTHONPATH = Join-Path (Get-Location) "src"

    & $pythonCmd -m contextcore.cli install verify --endpoint $OtlpEndpoint

    Write-Host ""
    Write-Status "ok" "Metrics exported to Mimir via $OtlpEndpoint"
    Write-Host "  Dashboard data should now be available at: $GrafanaUrl/d/contextcore-installation"
}

function Invoke-FullSetup {
    Invoke-Up
    Invoke-WaitReady
    Invoke-SeedMetrics

    Write-Host ""
    Write-Host "=== Full Setup Complete ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "ContextCore observability stack is ready!"
    Write-Host ""
    Write-Host "Dashboards available at: $GrafanaUrl"
    Write-Host "  - Installation Status: $GrafanaUrl/d/contextcore-installation"
    Write-Host "  - Project Portfolio:   $GrafanaUrl/d/contextcore-portfolio"
    Write-Host ""
    Write-Host "Quick commands:"
    Write-Host "  .\setup.ps1 health       - Check component health"
    Write-Host "  .\setup.ps1 smoke-test   - Validate entire stack"
    Write-Host "  .\setup.ps1 seed-metrics - Re-export installation metrics"
}

# === Backup & Restore ===

function Invoke-Backup {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = Join-Path "backups" $timestamp

    Write-Host "=== Creating Backup ===" -ForegroundColor Cyan
    New-Item -ItemType Directory -Path (Join-Path $backupDir "dashboards") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $backupDir "datasources") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $backupDir "state") -Force | Out-Null
    Write-Host "Backup directory: $backupDir"

    Write-Host ""
    Write-Host "Exporting Grafana dashboards..."
    try {
        $cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${GrafanaUser}:${GrafanaPassword}"))
        $headers = @{ Authorization = "Basic $cred" }
        $dashboards = Invoke-RestMethod -Uri "$GrafanaUrl/api/search?type=dash-db" -Headers $headers -TimeoutSec 10

        foreach ($db in $dashboards) {
            $uid = $db.uid
            try {
                $detail = Invoke-RestMethod -Uri "$GrafanaUrl/api/dashboards/uid/$uid" -Headers $headers -TimeoutSec 10
                $detail | ConvertTo-Json -Depth 20 | Set-Content (Join-Path $backupDir "dashboards" "$uid.json")
            }
            catch { Write-Status "warn" "Could not export dashboard $uid" }
        }
    }
    catch { Write-Status "warn" "Grafana not accessible, skipping dashboard export" }

    Write-Host "Exporting Grafana datasources..."
    try {
        $ds = Invoke-RestMethod -Uri "$GrafanaUrl/api/datasources" -Headers $headers -TimeoutSec 10
        $ds | ConvertTo-Json -Depth 20 | Set-Content (Join-Path $backupDir "datasources" "datasources.json")
    }
    catch { Write-Status "warn" "Could not export datasources" }

    $manifest = @{ created_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ"); version = "1.0" }
    $manifest | ConvertTo-Json | Set-Content (Join-Path $backupDir "manifest.json")

    Write-Host ""
    Write-Status "ok" "Backup complete: $backupDir"
}

function Invoke-Status {
    Write-Host "=== Container Status ===" -ForegroundColor Cyan
    if (Test-Path $ComposeFile) {
        docker compose -f $ComposeFile ps
    }
    else {
        docker ps --filter "name=contextcore" --filter "name=tempo" --filter "name=mimir" --filter "name=loki" --filter "name=grafana" --filter "name=alloy"
    }
}

# === Development ===

function Invoke-Install {
    $pythonCmd = if (Test-CommandAvailable "pip3") { "pip3" }
                 elseif (Test-CommandAvailable "pip") { "pip" }
                 else { "py -m pip" }
    & $pythonCmd install -e ".[dev]"
}

function Invoke-Test {
    $pythonCmd = if (Test-CommandAvailable "python3") { "python3" }
                 elseif (Test-CommandAvailable "python") { "python" }
                 else { "py" }
    $env:PYTHONPATH = Join-Path (Get-Location) "src"
    & $pythonCmd -m pytest tests/ -v
}

function Invoke-Clean {
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
    Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    Get-ChildItem -Recurse -Filter "*.pyc" | Remove-Item -Force
    Get-ChildItem -Filter "*.egg-info" | Remove-Item -Recurse -Force
    Get-ChildItem -Path "src" -Filter "*.egg-info" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    Write-Status "ok" "Build artifacts cleaned"
}

# === Logs ===

function Invoke-Logs {
    param([string]$Service)
    $container = docker ps --filter "name=$Service" --format "{{.Names}}" 2>$null | Select-Object -First 1
    if ($container) {
        docker logs -f $container
    }
    else {
        Write-Host "$Service container not running"
    }
}

# === Help ===

function Invoke-Help {
    Write-Host "ContextCore Setup (Windows)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Quick Start:" -ForegroundColor Yellow
    Write-Host "  .\setup.ps1 full-setup    Complete setup: start stack, wait, seed metrics"
    Write-Host ""
    Write-Host "Preflight:" -ForegroundColor Yellow
    Write-Host "  .\setup.ps1 doctor        Check system readiness (ports, Docker, tools)"
    Write-Host ""
    Write-Host "Stack Management:" -ForegroundColor Yellow
    Write-Host "  .\setup.ps1 up            Start the stack (runs doctor first)"
    Write-Host "  .\setup.ps1 down          Stop (preserve data)"
    Write-Host "  .\setup.ps1 destroy       Delete (auto-backup, confirm)"
    Write-Host "  .\setup.ps1 status        Show container status"
    Write-Host ""
    Write-Host "Health & Validation:" -ForegroundColor Yellow
    Write-Host "  .\setup.ps1 health        One-line health status per component"
    Write-Host "  .\setup.ps1 smoke-test    Validate entire stack"
    Write-Host "  .\setup.ps1 wait-ready    Wait for all services to be ready"
    Write-Host "  .\setup.ps1 seed-metrics  Export installation metrics"
    Write-Host ""
    Write-Host "Backup:" -ForegroundColor Yellow
    Write-Host "  .\setup.ps1 backup        Export state to timestamped directory"
    Write-Host ""
    Write-Host "Development:" -ForegroundColor Yellow
    Write-Host "  .\setup.ps1 install       Install ContextCore in dev mode"
    Write-Host "  .\setup.ps1 test          Run tests"
    Write-Host "  .\setup.ps1 clean         Clean build artifacts"
    Write-Host ""
    Write-Host "Logs:" -ForegroundColor Yellow
    Write-Host "  .\setup.ps1 logs-tempo    Follow Tempo logs"
    Write-Host "  .\setup.ps1 logs-mimir    Follow Mimir logs"
    Write-Host "  .\setup.ps1 logs-loki     Follow Loki logs"
    Write-Host "  .\setup.ps1 logs-grafana  Follow Grafana logs"
    Write-Host ""
    Write-Host "Environment Variables:" -ForegroundColor Yellow
    Write-Host "  GRAFANA_URL       Grafana URL (default: http://localhost:3000)"
    Write-Host "  GRAFANA_USER      Grafana user (default: admin)"
    Write-Host "  GRAFANA_PASSWORD  Grafana password (default: admin)"
    Write-Host "  OTLP_ENDPOINT     OTLP endpoint (default: localhost:4317)"
}

# === Main dispatch ===

switch ($Command) {
    "help"         { Invoke-Help }
    "doctor"       { Invoke-Doctor }
    "up"           { Invoke-Up }
    "down"         { Invoke-Down }
    "destroy"      { Invoke-Destroy }
    "status"       { Invoke-Status }
    "health"       { Invoke-Health }
    "smoke-test"   { Invoke-SmokeTest }
    "wait-ready"   { Invoke-WaitReady }
    "seed-metrics" { Invoke-SeedMetrics }
    "full-setup"   { Invoke-FullSetup }
    "backup"       { Invoke-Backup }
    "install"      { Invoke-Install }
    "test"         { Invoke-Test }
    "clean"        { Invoke-Clean }
    "logs-tempo"   { Invoke-Logs "tempo" }
    "logs-mimir"   { Invoke-Logs "mimir" }
    "logs-loki"    { Invoke-Logs "loki" }
    "logs-grafana" { Invoke-Logs "grafana" }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host "Run '.\setup.ps1 help' for available commands."
        exit 1
    }
}
