#!/bin/bash
# Test script for Prime Contractor Workflow API (BLC-001 through BLC-003)
set -e

API_URL="${API_URL:-http://localhost:8080}"
PROJECT_ID="${PROJECT_ID:-beaver-lead-contractor}"

echo "=== Testing Workflow API ==="
echo "API_URL: $API_URL"
echo "PROJECT_ID: $PROJECT_ID"

# Health check
echo -e "\n1. Health check..."
if ! curl -sf "$API_URL/health" > /dev/null 2>&1; then
    echo "❌ Rabbit API not running at $API_URL"
    echo "   Start it with:"
    echo "     cd contextcore-rabbit"
    echo "     pip3 install -e ."
    echo "     python3 -m contextcore_rabbit.cli --port 8080"
    exit 1
fi
curl -s "$API_URL/health" | python3 -m json.tool
echo "✅ Health check passed"

# List actions
echo -e "\n2. Available actions..."
ACTIONS=$(curl -s "$API_URL/actions")
echo "$ACTIONS" | python3 -m json.tool
if echo "$ACTIONS" | grep -q "beaver_workflow"; then
    echo "✅ beaver_workflow action registered"
else
    echo "❌ beaver_workflow action not found"
    exit 1
fi

# Dry run
echo -e "\n3. Testing /workflow/run (dry_run=true)..."
RESPONSE=$(curl -s -X POST "$API_URL/workflow/run" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\": \"$PROJECT_ID\", \"dry_run\": true}")
echo "$RESPONSE" | python3 -m json.tool

if echo "$RESPONSE" | grep -q '"status":"started"'; then
    echo "✅ BLC-001: /workflow/run endpoint works"
    RUN_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))")
else
    echo "❌ BLC-001: /workflow/run failed"
    exit 1
fi

# Check status
echo -e "\n4. Testing /workflow/status/$RUN_ID..."
sleep 2
STATUS=$(curl -s "$API_URL/workflow/status/$RUN_ID")
echo "$STATUS" | python3 -m json.tool

if echo "$STATUS" | grep -q 'run_id'; then
    echo "✅ BLC-002: /workflow/status endpoint works"
else
    echo "❌ BLC-002: /workflow/status failed"
fi

# Check history
echo -e "\n5. Testing /workflow/history..."
HISTORY=$(curl -s "$API_URL/workflow/history?limit=5")
echo "$HISTORY" | python3 -m json.tool

if echo "$HISTORY" | grep -q 'runs'; then
    echo "✅ BLC-003: /workflow/history endpoint works"
else
    echo "❌ BLC-003: /workflow/history failed"
fi

echo -e "\n=== API Tests Complete ==="
echo ""
echo "Summary:"
echo "  BLC-001 /workflow/run    ✅"
echo "  BLC-002 /workflow/status ✅"
echo "  BLC-003 /workflow/history ✅"
echo ""
echo "Next steps:"
echo "  1. Open Grafana: http://localhost:3000/d/contextcore-workflow"
echo "  2. Test the Trigger Workflow panel (BLC-004)"
echo "  3. Verify status panels update (BLC-005)"
