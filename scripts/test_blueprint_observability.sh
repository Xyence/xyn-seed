#!/bin/bash
# Test script for blueprint-based pack installation with observability

API_BASE="http://localhost:8000/api/v1"

echo "=== Blueprint-Based Pack Installation Test ==="
echo ""

# List registered blueprints
echo "1. List registered blueprints..."
curl -s "$API_BASE/debug/blueprints" | jq '.'
echo ""

# Clean up existing installation
echo "2. Cleaning up existing installation (if any)..."
docker exec xyn-postgres psql -U xyn -d xyn -c "DROP SCHEMA IF EXISTS pack_core_domain CASCADE;" 2>&1 | grep -v "NOTICE"
docker exec xyn-postgres psql -U xyn -d xyn -c "DELETE FROM pack_installations WHERE pack_id IN (SELECT id FROM packs WHERE pack_ref = 'core.domain@v1');" 2>&1 | grep -v "^$"
echo ""

# Trigger pack installation
echo "3. Triggering pack installation via blueprint runner..."
INSTALL_RESPONSE=$(curl -s -X POST "$API_BASE/packs/core.domain@v1/install")
echo "$INSTALL_RESPONSE" | jq '.'
echo ""

RUN_ID=$(echo "$INSTALL_RESPONSE" | jq -r '.run_id')
CORRELATION_ID=$(echo "$INSTALL_RESPONSE" | jq -r '.correlation_id')

echo "Run ID: $RUN_ID"
echo "Correlation ID: $CORRELATION_ID"
echo ""

# Get run details
echo "4. Fetching run details..."
curl -s "$API_BASE/runs/$RUN_ID" | jq '{
  name,
  status,
  started_at,
  completed_at,
  outputs
}'
echo ""

# Get steps
echo "5. Fetching run steps..."
curl -s "$API_BASE/runs/$RUN_ID/steps" | jq '.[] | {
  name,
  status,
  started_at,
  completed_at,
  outputs
}'
echo ""

# Get events by correlation ID
echo "6. Fetching events (showing lifecycle)..."
curl -s "$API_BASE/events?limit=100" | jq ".items[] | select(.correlation_id == \"$CORRELATION_ID\") | {
  event_name,
  occurred_at,
  step_id: .data.step_id,
  message: .data.message,
  step_name: .data.step_name
}" | jq -s 'reverse | .[]' | head -40
echo ""

# Verify installation status
echo "7. Verifying pack installation status..."
curl -s "$API_BASE/packs/core.domain@v1/status" | jq '.'
echo ""

# Check created schema and tables
echo "8. Verifying database objects..."
echo "Schemas:"
curl -s "$API_BASE/debug/db/schemas" | jq '.'
echo ""
echo "Tables in pack_core_domain:"
curl -s "$API_BASE/debug/db/schema/pack_core_domain/tables" | jq '.[] | {table_name, column_count: (.columns | length)}'
echo ""

echo "=== Test Complete ==="
echo ""
echo "Summary:"
echo "- Blueprints registered: $(curl -s "$API_BASE/debug/blueprints" | jq '. | length')"
echo "- Run status: $(curl -s "$API_BASE/runs/$RUN_ID" | jq -r '.status')"
echo "- Steps executed: $(curl -s "$API_BASE/runs/$RUN_ID/steps" | jq '. | length')"
echo "- Events emitted: $(curl -s "$API_BASE/events?limit=100" | jq ".items[] | select(.correlation_id == \"$CORRELATION_ID\")" | jq -s '. | length')"
echo ""
echo "Visit http://localhost:8000/ui/runs to see the run in the UI"
echo "Visit http://localhost:8000/ui/events to see all events"
