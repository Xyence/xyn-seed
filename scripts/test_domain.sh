#!/bin/bash
# Test script for domain endpoints

API_BASE="http://localhost:8000/api/v1"

echo "=== Testing Domain Endpoints ==="
echo ""

# Create a customer
echo "1. Creating a customer..."
CUSTOMER_RESPONSE=$(curl -s -X POST "$API_BASE/customers" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "email": "contact@acme.example.com",
    "status": "active"
  }')

echo "$CUSTOMER_RESPONSE" | jq '.'
CUSTOMER_ID=$(echo "$CUSTOMER_RESPONSE" | jq -r '.id')
echo "Customer ID: $CUSTOMER_ID"
echo ""

# List customers
echo "2. Listing all customers..."
curl -s "$API_BASE/customers" | jq '.'
echo ""

# Create a site
echo "3. Creating a site for the customer..."
SITE_RESPONSE=$(curl -s -X POST "$API_BASE/sites" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Main Website\",
    \"customer_id\": \"$CUSTOMER_ID\",
    \"url\": \"https://acme.example.com\",
    \"status\": \"active\"
  }")

echo "$SITE_RESPONSE" | jq '.'
SITE_ID=$(echo "$SITE_RESPONSE" | jq -r '.id')
echo "Site ID: $SITE_ID"
echo ""

# List sites
echo "4. Listing all sites..."
curl -s "$API_BASE/sites" | jq '.'
echo ""

echo "=== Test Complete ==="
echo "Visit http://localhost:8000/ui/domain to see the UI"
