#!/usr/bin/env bash
# Smoke test a running PaperPilot deployment through its public entry point.
# Usage: scripts/smoke-test.sh [frontend_url] [api_url]
#   Defaults: http://localhost:8080 for both (nginx proxies the API locally).
# Creates one investigation row as a side effect.
# Set EXPECT_PIPELINE=1 when workers run (local Compose) to also require that
# discovery links papers to the new investigation.
set -euo pipefail

FRONTEND_URL="${1:-http://localhost:8080}"
BASE_URL="${2:-$FRONTEND_URL}"
# Hosted free tiers can take ~1 minute to wake up.
curl() { command curl --max-time 120 "$@"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "Smoke testing frontend $FRONTEND_URL, API $BASE_URL"

code=$(curl -s -o /dev/null -w '%{http_code}' "$FRONTEND_URL/" || true)
[ "$code" = 200 ] || fail "frontend returned $code"
echo "ok   frontend serves index"

code=$(curl -s -o /dev/null -w '%{http_code}' "$FRONTEND_URL/investigations/deep-link-check" || true)
[ "$code" = 200 ] || fail "SPA deep link returned $code"
echo "ok   frontend serves deep links"

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

if [ "${EXPECT_PIPELINE:-0}" = 1 ]; then
  for _ in $(seq 1 60); do
    tasks=$(curl -sf "$BASE_URL/api/v1/investigations/$id/tasks" || true)
    case "$tasks" in
      *'"status":"succeeded"'*) break ;;
      *'"status":"failed_'*) fail "discovery failed: $tasks" ;;
    esac
    sleep 1
  done
  echo "$tasks" | grep -q '"status":"succeeded"' || fail "discovery did not finish in 60s: $tasks"
  linked=$(curl -sf "$BASE_URL/api/v1/investigations/$id/papers" | sed -E 's/.*"total":([0-9]+).*/\1/')
  [ "${linked:-0}" -gt 0 ] || fail "no papers linked"
  echo "ok   pipeline: outbox -> Kafka -> discovery worker linked $linked papers"

  for _ in $(seq 1 120); do
    tasks=$(curl -sf "$BASE_URL/api/v1/investigations/$id/tasks" || true)
    done_count=$( (echo "$tasks" | grep -o '"kind":"extract_evidence","subject_key":"[^"]*","status":"succeeded"' || true) | wc -l | tr -d ' ')
    [ "$done_count" -ge "$linked" ] && break
    sleep 1
  done
  [ "${done_count:-0}" -ge "$linked" ] || fail "evidence extraction did not finish: $done_count of $linked"
  evidence=$(curl -sf "$BASE_URL/api/v1/investigations/$id/evidence")
  echo "$evidence" | grep -q '"field"' || fail "no evidence records"
  echo "ok   pipeline: document + evidence workers processed $done_count papers"

  report=""
  for _ in $(seq 1 60); do
    report=$(curl -sf "$BASE_URL/api/v1/investigations/$id/report" || true)
    [ -n "$report" ] && break
    sleep 1
  done
  echo "$report" | grep -q '"bottom_line"' || fail "report not built"
  status=$(curl -sf "$BASE_URL/api/v1/investigations/$id" | sed -E 's/.*"status":"([a-z_]+)".*/\1/')
  case "$status" in completed|partially_completed) ;; *) fail "unexpected final status $status" ;; esac
  echo "ok   pipeline: report built; investigation $status"
fi

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/v1/investigations" \
  -H 'Content-Type: application/json' -d '{"question":"short"}')
[ "$code" = 422 ] || fail "invalid input returned $code, expected 422"
echo "ok   invalid input rejected"

if [ "$FRONTEND_URL" != "$BASE_URL" ]; then
  allowed=$(curl -s -D - -o /dev/null -H "Origin: $FRONTEND_URL" "$BASE_URL/health/live" \
    | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')
  [ "$allowed" = "$FRONTEND_URL" ] || fail "CORS does not allow $FRONTEND_URL (got '$allowed')"
  echo "ok   CORS allows the frontend origin"
fi

echo "PASS"
