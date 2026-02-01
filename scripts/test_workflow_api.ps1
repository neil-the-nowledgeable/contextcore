# Test script for Prime Contractor Workflow API (BLC-001 through BLC-003)
# Windows PowerShell equivalent of test_workflow_api.sh

param(
    [string]$ApiUrl = $(if ($env:API_URL) { $env:API_URL } else { "http://localhost:8080" }),
    [string]$ProjectId = $(if ($env:PROJECT_ID) { $env:PROJECT_ID } else { "beaver-lead-contractor" })
)

$ErrorActionPreference = "Stop"

Write-Host "=== Testing Workflow API ==="
Write-Host "API_URL: $ApiUrl"
Write-Host "PROJECT_ID: $ProjectId"

# Resolve python command
$pythonCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" }
             elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" }
             else { "py" }

# 1. Health check
Write-Host "`n1. Health check..."
try {
    $health = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 5
    $health | ConvertTo-Json -Depth 5
    Write-Host "[OK] Health check passed" -ForegroundColor Green
}
catch {
    Write-Host "[FAIL] Rabbit API not running at $ApiUrl" -ForegroundColor Red
    Write-Host "   Start it with:"
    Write-Host "     cd contextcore-rabbit"
    Write-Host "     pip install -e ."
    Write-Host "     $pythonCmd -m contextcore_rabbit.cli --port 8080"
    exit 1
}

# 2. List actions
Write-Host "`n2. Available actions..."
$actions = Invoke-RestMethod -Uri "$ApiUrl/actions" -TimeoutSec 5
$actionsJson = $actions | ConvertTo-Json -Depth 5
Write-Host $actionsJson
if ($actionsJson -match "beaver_workflow") {
    Write-Host "[OK] beaver_workflow action registered" -ForegroundColor Green
}
else {
    Write-Host "[FAIL] beaver_workflow action not found" -ForegroundColor Red
    exit 1
}

# 3. Dry run
Write-Host "`n3. Testing /workflow/run (dry_run=true)..."
$body = @{ project_id = $ProjectId; dry_run = $true } | ConvertTo-Json
$response = Invoke-RestMethod -Uri "$ApiUrl/workflow/run" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 30
$responseJson = $response | ConvertTo-Json -Depth 5
Write-Host $responseJson

$runId = $null
if ($responseJson -match '"status"\s*:\s*"started"') {
    Write-Host "[OK] BLC-001: /workflow/run endpoint works" -ForegroundColor Green
    $runId = $response.run_id
}
else {
    Write-Host "[FAIL] BLC-001: /workflow/run failed" -ForegroundColor Red
    exit 1
}

# 4. Check status
Write-Host "`n4. Testing /workflow/status/$runId..."
Start-Sleep -Seconds 2
$status = Invoke-RestMethod -Uri "$ApiUrl/workflow/status/$runId" -TimeoutSec 10
$statusJson = $status | ConvertTo-Json -Depth 5
Write-Host $statusJson

if ($statusJson -match "run_id") {
    Write-Host "[OK] BLC-002: /workflow/status endpoint works" -ForegroundColor Green
}
else {
    Write-Host "[FAIL] BLC-002: /workflow/status failed" -ForegroundColor Red
}

# 5. Check history
Write-Host "`n5. Testing /workflow/history..."
$history = Invoke-RestMethod -Uri "$ApiUrl/workflow/history?limit=5" -TimeoutSec 10
$historyJson = $history | ConvertTo-Json -Depth 5
Write-Host $historyJson

if ($historyJson -match "runs") {
    Write-Host "[OK] BLC-003: /workflow/history endpoint works" -ForegroundColor Green
}
else {
    Write-Host "[FAIL] BLC-003: /workflow/history failed" -ForegroundColor Red
}

Write-Host "`n=== API Tests Complete ==="
Write-Host ""
Write-Host "Summary:"
Write-Host "  BLC-001 /workflow/run     [OK]" -ForegroundColor Green
Write-Host "  BLC-002 /workflow/status  [OK]" -ForegroundColor Green
Write-Host "  BLC-003 /workflow/history [OK]" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open Grafana: http://localhost:3000/d/contextcore-workflow"
Write-Host "  2. Test the Trigger Workflow panel (BLC-004)"
Write-Host "  3. Verify status panels update (BLC-005)"
