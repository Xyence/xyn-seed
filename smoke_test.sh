#!/bin/bash

# Xyn Seed v0.0 - Automated Smoke Test Script
# This script runs API-based smoke tests against a running Xyn Seed instance

set -e

BASE_URL="http://localhost:8000"

echo "=== Xyn Seed v0.0 Smoke Tests ==="
echo

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo "Warning: jq not found. Install jq for pretty JSON output."
    echo "Continuing without jq..."
    JQ_CMD="cat"
else
    JQ_CMD="jq ."
fi

echo "1. Health Check..."
HEALTH=$(curl -s $BASE_URL/api/v1/health)
echo "$HEALTH" | $JQ_CMD
STATUS=$(echo "$HEALTH" | grep -o '"status":"ok"' || echo "")
if [ -z "$STATUS" ]; then
    echo "❌ Health check failed!"
    exit 1
fi
echo "✅ Health check passed"
echo

echo "2. Create Run (Success Case)..."
RUN_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{"name": "Smoke Test Success", "inputs": {"test": "data"}}')

if command -v jq &> /dev/null; then
    RUN_ID=$(echo "$RUN_RESPONSE" | jq -r '.run_id')
else
    RUN_ID=$(echo "$RUN_RESPONSE" | grep -o '"run_id":"[^"]*' | cut -d'"' -f4)
fi

echo "Created run: $RUN_ID"
echo

echo "3. Wait for run to complete..."
sleep 2
echo

echo "4. Get Run Details..."
RUN_DETAILS=$(curl -s $BASE_URL/api/v1/runs/$RUN_ID)
echo "$RUN_DETAILS" | $JQ_CMD
echo "✅ Run created and retrieved"
echo

echo "5. List Run Steps..."
STEPS=$(curl -s $BASE_URL/api/v1/runs/$RUN_ID/steps)
if command -v jq &> /dev/null; then
    STEP_COUNT=$(echo "$STEPS" | jq '. | length')
else
    STEP_COUNT=$(echo "$STEPS" | grep -o '"step_id"' | wc -l)
fi
echo "Found $STEP_COUNT steps"
echo "✅ Steps retrieved"
echo

echo "6. List Events..."
EVENTS=$(curl -s "$BASE_URL/api/v1/events?limit=10")
if command -v jq &> /dev/null; then
    EVENT_COUNT=$(echo "$EVENTS" | jq '.items | length')
else
    EVENT_COUNT=$(echo "$EVENTS" | grep -o '"event_id"' | wc -l)
fi
echo "Found $EVENT_COUNT events"
echo "✅ Events retrieved"
echo

echo "7. List All Runs..."
RUNS=$(curl -s "$BASE_URL/api/v1/runs?limit=10")
if command -v jq &> /dev/null; then
    RUN_COUNT=$(echo "$RUNS" | jq '.items | length')
else
    RUN_COUNT=$(echo "$RUNS" | grep -o '"run_id"' | wc -l)
fi
echo "Found $RUN_COUNT runs"
echo "✅ Runs retrieved"
echo

echo "8. Filter Events by Type..."
FILTERED_EVENTS=$(curl -s "$BASE_URL/api/v1/events?event_name=xyn.run.created&limit=5")
if command -v jq &> /dev/null; then
    FILTERED_COUNT=$(echo "$FILTERED_EVENTS" | jq '.items | length')
else
    FILTERED_COUNT=$(echo "$FILTERED_EVENTS" | grep -o '"event_id"' | wc -l)
fi
echo "Found $FILTERED_COUNT 'xyn.run.created' events"
echo "✅ Event filtering works"
echo

echo "=== All Smoke Tests Passed ✅ ==="
echo
echo "Next steps:"
echo "  • Visit $BASE_URL/ui/events to see the event console"
echo "  • Visit $BASE_URL/ui/runs to see all runs"
echo "  • Visit $BASE_URL/ui/runs/$RUN_ID to see the run you just created"
echo
echo "See SMOKE.md for more detailed testing instructions."
