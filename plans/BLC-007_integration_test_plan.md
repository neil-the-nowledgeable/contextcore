# BLC-007: Prime Contractor Workflow Integration Test Plan

## Objective
Verify end-to-end operation of the Prime Contractor workflow triggered via Rabbit API, testing BLC-001 through BLC-009.

## Prerequisites

### 1. Start Observability Stack
```bash
make up
# Or manually:
docker compose up -d prometheus grafana tempo loki
```

### 2. Start Rabbit API Server
```bash
cd contextcore-rabbit
pip install -e .
python -m contextcore_rabbit.cli serve --port 8080
```

### 3. Verify Services Are Running
```bash
# Health check
curl http://localhost:8080/health

# List available actions
curl http://localhost:8080/actions
```

Expected: `beaver_workflow`, `beaver_workflow_status`, `beaver_workflow_history`, `beaver_workflow_dry_run`

---

## Test Cases

### Test 1: API Endpoint Verification (BLC-001, BLC-002, BLC-003)

#### 1.1 Workflow Run Endpoint (BLC-001)
```bash
# Dry run mode
curl -X POST http://localhost:8080/workflow/run \
  -H "Content-Type: application/json" \
  -d '{"project_id": "test-project", "dry_run": true}'
```

Expected response:
```json
{
  "status": "started",
  "run_id": "<uuid>",
  "project_id": "test-project",
  "mode": "dry_run"
}
```

#### 1.2 Workflow Status Endpoint (BLC-002)
```bash
# Replace <run_id> with actual ID from step 1.1
curl http://localhost:8080/workflow/status/<run_id>
```

Expected response:
```json
{
  "run_id": "<run_id>",
  "status": "running" | "completed" | "failed",
  "project_id": "test-project",
  "dry_run": true,
  "started_at": "ISO timestamp",
  "steps_total": 0,
  "steps_completed": 0,
  "progress_percent": 0
}
```

#### 1.3 Workflow History Endpoint (BLC-003)
```bash
curl "http://localhost:8080/workflow/history?limit=10"
```

Expected response:
```json
{
  "runs": [...],
  "total": <number>
}
```

---

### Test 2: Full Workflow Execution

#### 2.1 Create Test Feature
Create a minimal feature for testing in `plans/features/TEST-001_test_feature.md`:
```markdown
# Feature: TEST-001 - Test Feature

## Overview
Minimal test feature for workflow validation.

## Target Files
- `src/contextcore/test_feature.py` (new file)

## Requirements
```python
"""Test feature module."""

def hello_test():
    """Return test greeting."""
    return "Hello from test feature"
```

## Acceptance Criteria
- [ ] File created
- [ ] Function works

## Size Estimate
~5 lines
```

#### 2.2 Execute Workflow
```bash
# Real execution (not dry run)
curl -X POST http://localhost:8080/workflow/run \
  -H "Content-Type: application/json" \
  -d '{"project_id": "beaver-lead-contractor", "dry_run": false, "max_features": 1}'
```

#### 2.3 Poll Status Until Complete
```bash
# Poll every 5 seconds
while true; do
  curl -s http://localhost:8080/workflow/status/<run_id> | jq .
  sleep 5
done
```

---

### Test 3: Dashboard Verification (BLC-004, BLC-005)

#### 3.1 Open Grafana
```
http://localhost:3000/d/contextcore-workflow
```

#### 3.2 Verify Panels
- [ ] **Trigger Workflow panel** - Dry Run and Execute buttons work
- [ ] **Active Workflow Status** - Shows phase during execution
- [ ] **Progress gauge** - Updates during execution
- [ ] **Current Task** - Shows feature being processed

---

### Test 4: Tempo Trace Verification (BLC-007)

#### 4.1 Query Tempo for Workflow Traces
```bash
# Via Grafana Explore or API
curl "http://localhost:3200/api/search?tags=service.name%3Dlead-contractor&limit=10"
```

#### 4.2 Verify Span Attributes
Check that traces include:
- [ ] `resource.service.name` = "lead-contractor"
- [ ] `resource.project.id` = project name
- [ ] `span.workflow.phase` = spec/draft/review/integration
- [ ] `span.task.title` = feature name

---

### Test 5: Insight Emission (BLC-008) - Currently Not Implemented

#### Expected Behavior (when implemented)
Insights should appear in Tempo with:
- `insight.type` = "decision"
- `insight.summary` = workflow decision description
- `insight.confidence` = 0.0-1.0

#### Current Status
⚠️ BLC-008 not yet implemented - insights won't appear until InsightEmitter is integrated.

---

### Test 6: Cost Tracking (BLC-009) - Currently Not Implemented

#### Expected Behavior (when implemented)
Span attributes should include:
- `gen_ai.usage.input_tokens`
- `gen_ai.usage.output_tokens`
- `gen_ai.request.model`
- `contextcore.cost.usd`

#### Current Status
⚠️ BLC-009 not yet implemented - cost attributes won't appear until tracking is added.

---

## Quick Validation Script

Save as `scripts/test_workflow_api.sh`:
```bash
#!/bin/bash
set -e

API_URL="${API_URL:-http://localhost:8080}"
PROJECT_ID="${PROJECT_ID:-test-project}"

echo "=== Testing Workflow API ==="

# Health check
echo -e "\n1. Health check..."
curl -s "$API_URL/health" | jq .

# List actions
echo -e "\n2. Available actions..."
curl -s "$API_URL/actions" | jq '.actions[].name'

# Dry run
echo -e "\n3. Starting dry run..."
RESPONSE=$(curl -s -X POST "$API_URL/workflow/run" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\": \"$PROJECT_ID\", \"dry_run\": true}")
echo "$RESPONSE" | jq .
RUN_ID=$(echo "$RESPONSE" | jq -r '.run_id')

# Check status
echo -e "\n4. Checking status for run_id=$RUN_ID..."
sleep 2
curl -s "$API_URL/workflow/status/$RUN_ID" | jq .

# Check history
echo -e "\n5. Workflow history..."
curl -s "$API_URL/workflow/history?limit=5" | jq .

echo -e "\n=== API Tests Complete ==="
```

---

## Test Results Checklist

| Test | Component | Status |
|------|-----------|--------|
| 1.1 | BLC-001 /workflow/run | ⬜ |
| 1.2 | BLC-002 /workflow/status | ⬜ |
| 1.3 | BLC-003 /workflow/history | ⬜ |
| 2.x | Full workflow execution | ⬜ |
| 3.x | BLC-004 WorkflowPanel | ⬜ |
| 3.x | BLC-005 Status panels | ⬜ |
| 4.x | BLC-007 Tempo traces | ⬜ |
| 5.x | BLC-008 Insights | ⬜ (not implemented) |
| 6.x | BLC-009 Cost tracking | ⬜ (not implemented) |

---

## Known Issues / Gaps

1. **BLC-006 (History Panel)** - Not yet added to dashboard
2. **BLC-008 (Insight Emission)** - InsightEmitter not integrated into workflow
3. **BLC-009 (Cost Tracking)** - Token/cost attributes not being emitted
4. **Prime Contractor dependencies** - Requires `scripts/prime_contractor/` to be functional

## Next Steps After Testing

1. If API tests pass → BLC-001, 002, 003 verified
2. If dashboard works → BLC-004, 005 verified
3. Implement BLC-006 (add history panel to dashboard)
4. Implement BLC-008 (add InsightEmitter to workflow.py)
5. Implement BLC-009 (add cost tracking to runner.py)
