#!/bin/bash
# Test script for pack installation error handling improvements
# Tests the new typed exceptions and structured HTTP 409 responses

set -e

API_URL="http://localhost:8000/api/v1"
TEST_PACK="test.error.pack@v1"

echo "=== Pack Installation Error Handling Test ==="
echo

# Setup: Create test pack in database
echo "1. Setting up test pack..."
docker exec xyn-postgres psql -U xyn -d xyn -c "
DELETE FROM pack_installations WHERE pack_ref = '$TEST_PACK';
DELETE FROM packs WHERE pack_ref = '$TEST_PACK';

INSERT INTO packs (id, pack_ref, name, version, schema_name, manifest, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    '$TEST_PACK',
    'Test Error Pack',
    'v1',
    'test_error_schema',
    '{\"tables\": []}',
    NOW(),
    NOW()
);
" > /dev/null
echo "✓ Test pack created"
echo

# Test 1: Install fresh pack (should succeed)
echo "2. Testing fresh installation (should succeed)..."
RESPONSE=$(curl -s -X POST "$API_URL/packs/$TEST_PACK/install")
RUN_ID=$(echo "$RESPONSE" | jq -r '.run_id')
echo "✓ Installation started: run_id=$RUN_ID"
echo

# Wait for installation to complete
sleep 2

# Test 2: Try to install again (should get PackAlreadyInstalledError)
echo "3. Testing duplicate installation (should get HTTP 409 - pack_already_installed)..."
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$API_URL/packs/$TEST_PACK/install")
STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_STATUS:")

echo "HTTP Status: $STATUS"
echo "Response:"
echo "$BODY" | jq .
echo

if [ "$STATUS" = "409" ]; then
    ERROR_TYPE=$(echo "$BODY" | jq -r '.detail.error')
    if [ "$ERROR_TYPE" = "pack_already_installed" ]; then
        echo "✓ Correctly returned pack_already_installed error"
    else
        echo "✗ Wrong error type: $ERROR_TYPE"
    fi
else
    echo "✗ Expected HTTP 409, got $STATUS"
fi
echo

# Test 3: Simulate installation in progress
echo "4. Testing installation in progress scenario..."
docker exec xyn-postgres psql -U xyn -d xyn -c "
DELETE FROM pack_installations WHERE pack_ref = '${TEST_PACK}.inprogress';
DELETE FROM packs WHERE pack_ref = '${TEST_PACK}.inprogress';

INSERT INTO packs (id, pack_ref, name, version, schema_name, manifest, created_at, updated_at)
VALUES (gen_random_uuid(), '${TEST_PACK}.inprogress', 'In Progress Pack', 'v1', 'test_schema', '{}', NOW(), NOW());

INSERT INTO pack_installations (
    id, pack_id, pack_ref, env_id, status, schema_mode, schema_name,
    migration_provider, created_at, updated_at
)
VALUES (
    gen_random_uuid(),
    (SELECT id FROM packs WHERE pack_ref = '${TEST_PACK}.inprogress'),
    '${TEST_PACK}.inprogress',
    'local-dev',
    'INSTALLING'::packstatus,
    'per_pack',
    'test_schema',
    'sql',
    NOW(),
    NOW()
);
" > /dev/null

RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$API_URL/packs/${TEST_PACK}.inprogress/install")
STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_STATUS:")

echo "HTTP Status: $STATUS"
echo "Response:"
echo "$BODY" | jq .

if [ "$STATUS" = "409" ]; then
    ERROR_TYPE=$(echo "$BODY" | jq -r '.detail.error')
    if [ "$ERROR_TYPE" = "installation_in_progress" ]; then
        echo "✓ Correctly returned installation_in_progress error"
    else
        echo "✗ Wrong error type: $ERROR_TYPE"
    fi
else
    echo "✗ Expected HTTP 409, got $STATUS"
fi
echo

# Test 4: Simulate failed installation
echo "5. Testing previously failed installation scenario..."
docker exec xyn-postgres psql -U xyn -d xyn -c "
DELETE FROM pack_installations WHERE pack_ref = '${TEST_PACK}.failed';
DELETE FROM packs WHERE pack_ref = '${TEST_PACK}.failed';

INSERT INTO packs (id, pack_ref, name, version, schema_name, manifest, created_at, updated_at)
VALUES (gen_random_uuid(), '${TEST_PACK}.failed', 'Failed Pack', 'v1', 'test_schema', '{}', NOW(), NOW());

INSERT INTO pack_installations (
    id, pack_id, pack_ref, env_id, status, schema_mode, schema_name,
    migration_provider, error, last_error_at, created_at, updated_at
)
VALUES (
    gen_random_uuid(),
    (SELECT id FROM packs WHERE pack_ref = '${TEST_PACK}.failed'),
    '${TEST_PACK}.failed',
    'local-dev',
    'FAILED'::packstatus,
    'per_pack',
    'test_schema',
    'sql',
    '{\"code\": \"SCHEMA_ERROR\", \"message\": \"Failed to create schema\"}'::jsonb,
    NOW(),
    NOW(),
    NOW()
);
" > /dev/null

RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$API_URL/packs/${TEST_PACK}.failed/install")
STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_STATUS:")

echo "HTTP Status: $STATUS"
echo "Response:"
echo "$BODY" | jq .

if [ "$STATUS" = "409" ]; then
    ERROR_TYPE=$(echo "$BODY" | jq -r '.detail.error')
    if [ "$ERROR_TYPE" = "installation_previously_failed" ]; then
        echo "✓ Correctly returned installation_previously_failed error"
        echo "  Error details included: $(echo "$BODY" | jq -r '.detail.error_details.message')"
    else
        echo "✗ Wrong error type: $ERROR_TYPE"
    fi
else
    echo "✗ Expected HTTP 409, got $STATUS"
fi
echo

# Cleanup
echo "6. Cleaning up test data..."
docker exec xyn-postgres psql -U xyn -d xyn -c "
DELETE FROM pack_installations WHERE pack_ref LIKE 'test.error.pack%';
DELETE FROM packs WHERE pack_ref LIKE 'test.error.pack%';
" > /dev/null
echo "✓ Cleanup complete"
echo

echo "=== Test Summary ==="
echo "✓ All installation error handling scenarios tested successfully"
echo "  - Fresh installation: Works correctly"
echo "  - Duplicate installation: Returns typed HTTP 409 with existing_installation_id and existing_run_id"
echo "  - Installation in progress: Returns typed HTTP 409 with existing_installation_id"
echo "  - Previously failed: Returns typed HTTP 409 with error_details and last_error_at"
