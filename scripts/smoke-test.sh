#!/usr/bin/env bash
# Smoke test a running PaperPilot deployment through its public entry point.
# Usage: scripts/smoke-test.sh [base_url]   (default http://localhost:8080)
# Creates one investigation row as a side effect.
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "Smoke testing $BASE_URL"

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/")
[ "$code" = 200 ] || fail "frontend returned $code"
echo "ok   frontend serves index"

body=$(curl -sf "$BASE_URL/health/ready") || fail "readiness check failed"
echo "$body" | grep -q '"database":"ok"' || fail "database not ready: $body"
echo "ok   API ready, database reachable"

created=$(curl -sf -X POST "$BASE_URL/api/v1/investigations" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Smoke test: does the investigation API persist questions?"}') \
  || fail "create investigation failed"
id=$(echo "$created" | sed -E 's/.*"id":"([^"]+)".*/\1/')
echo "ok   created investigation $id"

curl -sf "$BASE_URL/api/v1/investigations/$id" | grep -q '"status":"queued"' \
  || fail "created investigation not readable"
echo "ok   investigation readable with status queued"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/v1/investigations" \
  -H 'Content-Type: application/json' -d '{"question":"short"}')
[ "$code" = 422 ] || fail "invalid input returned $code, expected 422"
echo "ok   invalid input rejected"

echo "PASS"
