# ADR 0001: Modular monolith API with separate worker processes

- Status: accepted
- Date: 2026-10-22

## Problem

PaperPilot has a synchronous part (users create and read investigations) and a
slow, failure-prone part (calling external APIs, downloading PDFs, running
embedding models). The slow part must not block HTTP requests, and it must
survive crashes and retries.

## Alternatives

1. **Everything inside the API process** (FastAPI background tasks). Simple,
   but work is lost when the process restarts and it cannot scale workers
   independently.
2. **Many microservices** (one per stage, each with its own codebase/DB).
   Strong isolation, but heavy operational cost for one developer and no real
   need for independent deployment or separate data ownership.
3. **Modular monolith + worker processes.** One Python package with clear
   module boundaries; the API and each worker are different entry points.

## Decision

Option 3. One `backend/app` package. The API process serves HTTP. Worker
processes (added in M3+) consume Kafka topics and run pipeline stages. All share
the same models and migrations.

## Trade-offs

- Workers and API deploy together (same image, different command). Acceptable:
  they change together.
- Module boundaries are enforced by convention and review, not by network
  calls. Imports flow toward `app.core`; feature modules do not import each
  other's internals.

## Verification

Each module has its own tests; the M3 integration suite runs API + worker
processes against real Postgres and Kafka.
