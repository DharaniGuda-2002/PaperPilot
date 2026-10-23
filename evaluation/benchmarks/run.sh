#!/usr/bin/env bash
# Throughput benchmark: 1..4 discovery workers against the same workload.
# Uses the recorded OpenAlex sample with a fixed simulated provider latency so
# results are repeatable and spend no OpenAlex quota.
#
# Usage: evaluation/benchmarks/run.sh [n_per_run] [runs_per_config] [latency_ms]
set -euo pipefail
cd "$(dirname "$0")/../.."

N="${1:-60}"
RUNS="${2:-3}"
LATENCY_MS="${3:-400}"
export PAPER_PROVIDER=fixture FIXTURE_PROVIDER_LATENCY_MS="$LATENCY_MS" DAILY_PROVIDER_CALL_CAP=100000

for workers in 1 2 3 4; do
  docker compose up -d --wait --scale discovery-worker="$workers" >/dev/null 2>&1
  sleep 10  # let the consumer group finish rebalancing
  for run in $(seq 1 "$RUNS"); do
    (cd backend && PYTHONPATH=. DATABASE_URL=postgresql+psycopg://paperpilot:paperpilot-local-only@127.0.0.1:5433/paperpilot \
      .venv/bin/python ../evaluation/benchmarks/pipeline_throughput.py \
        --n "$N" --workers "$workers" --label "workers-$workers-run-$run")
  done
done

# Restore the normal configuration.
unset PAPER_PROVIDER FIXTURE_PROVIDER_LATENCY_MS DAILY_PROVIDER_CALL_CAP
docker compose up -d --wait --scale discovery-worker=1 >/dev/null 2>&1
