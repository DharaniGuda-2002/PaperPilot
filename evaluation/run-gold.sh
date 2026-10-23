#!/usr/bin/env bash
# Score retrieval and extraction against a manually reviewed gold set.
# Needs the local stack with the gold papers already processed (full text,
# chunks, embeddings). Read-only: nothing is written to the database.
#
# Usage: evaluation/run-gold.sh [set-name] [--list-unjudged]
set -euo pipefail
cd "$(dirname "$0")/.."

SET="${1:-rag-hallucination-v1}"
shift || true

docker compose run --rm --no-deps \
  -v "$PWD/evaluation:/evaluation" \
  document-worker python -m app.evaluation.run \
  --gold "/evaluation/gold/$SET.json" \
  --out "/evaluation/results/$SET.json" "$@"
