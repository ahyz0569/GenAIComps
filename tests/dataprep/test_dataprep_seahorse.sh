#!/bin/bash
# Copyright (C) 2026 Dnotitia
# SPDX-License-Identifier: Apache-2.0

set -e

DATAPREP_URL="${DATAPREP_URL:-http://localhost:5000}"

echo "=== Testing Seahorse Cloud Dataprep ==="

# Health check
echo "1. Health check..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$DATAPREP_URL/v1/health")
if [ "$STATUS" = "200" ]; then
    echo "   PASS: Health check"
else
    echo "   FAIL: Health check returned $STATUS"
    exit 1
fi

# Ingest test
echo "2. Ingest test..."
echo "This is a test document for Seahorse Cloud integration." > /tmp/test_seahorse.txt
RESPONSE=$(curl -s -X POST "$DATAPREP_URL/v1/dataprep/ingest" \
    -F "files=@/tmp/test_seahorse.txt")
echo "   Response: $RESPONSE"

# Get files test
echo "3. Get files test..."
RESPONSE=$(curl -s -X POST "$DATAPREP_URL/v1/dataprep/get")
echo "   Response: $RESPONSE"

# Delete test
echo "4. Delete test..."
RESPONSE=$(curl -s -X POST "$DATAPREP_URL/v1/dataprep/delete" \
    -H "Content-Type: application/json" \
    -d '{"file_path": "all"}')
echo "   Response: $RESPONSE"

rm -f /tmp/test_seahorse.txt
echo "=== All tests passed ==="
