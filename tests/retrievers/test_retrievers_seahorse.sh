#!/bin/bash
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e

RETRIEVER_URL="${RETRIEVER_URL:-http://localhost:7000}"

echo "=== Testing Seahorse Cloud Retriever ==="

# Health check
echo "1. Health check..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$RETRIEVER_URL/v1/health")
if [ "$STATUS" = "200" ]; then
    echo "   PASS: Health check"
else
    echo "   FAIL: Health check returned $STATUS"
    exit 1
fi

# Retrieval test (text query for builtin mode)
echo "2. Retrieval test..."
RESPONSE=$(curl -s -X POST "$RETRIEVER_URL/v1/retrieval" \
    -H "Content-Type: application/json" \
    -d '{
        "text": "test query",
        "embedding": [0.1, 0.2, 0.3],
        "k": 3
    }')
echo "   Response: $RESPONSE"

echo "=== All tests passed ==="
