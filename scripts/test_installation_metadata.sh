#!/bin/bash
# Test script for pack installation metadata tracking

API_BASE="http://localhost:8000/api/v1"

echo "=== Pack Installation Metadata Tracking Test ==="
echo ""

# Clean up existing installations
echo "1. Cleaning up existing installations..."
docker exec xyn-postgres psql -U xyn -d xyn -c "DROP SCHEMA IF EXISTS pack_core_domain CASCADE;" 2>&1 | grep -v "NOTICE"
docker exec xyn-postgres psql -U xyn -d xyn -c "DELETE FROM pack_installations WHERE pack_ref = 'core.domain@v1';" 2>&1 | grep -v "^$"
echo ""

# Check pack before installation
echo "2. Checking pack status before installation..."
curl -s "$API_BASE/packs/core.domain@v1/status" | jq '.'
echo ""

# Install pack
echo "3. Installing pack..."
INSTALL_RESPONSE=$(curl -s -X POST "$API_BASE/packs/core.domain@v1/install")
echo "$INSTALL_RESPONSE" | jq '.'
RUN_ID=$(echo "$INSTALL_RESPONSE" | jq -r '.run_id')
echo ""

# Check pack status after installation
echo "4. Checking pack status after installation..."
echo "Note the new metadata fields:"
curl -s "$API_BASE/packs/core.domain@v1/status" | jq '.'
echo ""

# View installation record details
echo "5. Viewing installation details via list endpoint..."
curl -s "$API_BASE/packs" | jq '.items[0].installation | {
  pack_ref,
  status,
  schema_mode,
  schema_name,
  installed_version,
  migration_state,
  installed_at,
  installed_by_run_id
}'
echo ""

# Query database directly
echo "6. Querying database directly..."
docker exec xyn-postgres psql -U xyn -d xyn -c "
SELECT
    pack_ref,
    installed_version,
    schema_mode,
    schema_name,
    migration_state,
    installed_at,
    substring(installed_by_run_id::text, 1, 8) || '...' as run_id_prefix
FROM pack_installations
WHERE pack_ref = 'core.domain@v1';
" | head -20
echo ""

# View installation run
echo "7. Viewing installation run details..."
curl -s "$API_BASE/runs/$RUN_ID" | jq '{
  name,
  status,
  started_at,
  completed_at,
  outputs: {
    pack_id: .outputs.pack_id,
    installation_id: .outputs.installation_id,
    schema_name: .outputs.schema_name,
    version: .outputs.version
  }
}'
echo ""

# View installation run steps
echo "8. Viewing installation run steps..."
curl -s "$API_BASE/runs/$RUN_ID/steps" | jq '.[] | {
  name,
  status,
  outputs
}'
echo ""

# Test upgrade detection query
echo "9. Testing upgrade detection query..."
docker exec xyn-postgres psql -U xyn -d xyn -c "
SELECT
    pi.pack_ref,
    pi.installed_version as current_version,
    p.version as available_version,
    CASE
        WHEN pi.installed_version = p.version THEN 'up-to-date'
        ELSE 'upgrade available'
    END as upgrade_status
FROM pack_installations pi
JOIN packs p ON p.id = pi.pack_id
WHERE pi.status::text = 'installed';
"
echo ""

echo "=== Test Complete ==="
echo ""
echo "Summary of Tracked Metadata:"
echo "----------------------------"
echo "✓ pack_ref: Denormalized pack reference (core.domain@v1)"
echo "✓ installed_version: Version installed (1.0.0)"
echo "✓ schema_mode: Schema isolation mode (per_pack)"
echo "✓ schema_name: Actual schema name (pack_core_domain)"
echo "✓ migration_state: Latest migration ID (null for no migrations)"
echo "✓ installed_at: Installation timestamp"
echo "✓ installed_by_run_id: Links to installation run"
echo ""
echo "This metadata supports:"
echo "- Upgrade detection (compare versions)"
echo "- Migration tracking (which migrations applied)"
echo "- Audit trail (who/when/how installed)"
echo "- Multi-environment support (env_id)"
echo "- Schema management (mode + name)"
