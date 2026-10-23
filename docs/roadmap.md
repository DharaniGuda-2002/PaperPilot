# Roadmap and Progress

Each milestone is finished and verified before the next starts.

## Checklist

- [x] M0 — Repository inspection, architecture, ADRs, acceptance criteria
- [x] M1 — Application foundation (local, CI, and public demo verified)
- [x] UI redesign — landing page, sidebar app shell, dashboard with real status counts
      (2026-10-23; screens without backend data wait for their milestones)
- [x] M2 — Paper discovery (OpenAlex search, cached and rate limited; verified locally and on the public demo)
- [x] M3 — Kafka pipeline (outbox, dispatcher, idempotent discovery worker; local deployment)
- [ ] M4 — Distributed reliability (retries, DLQ, recovery, throughput)
- [ ] M5 — Retrieval and evidence (PDFs, embeddings, hybrid search, extraction)
- [ ] M6 — Comparison and reports (rules, progressive-disclosure report UI)
- [ ] M7 — Hardening and final deployment

## M1 acceptance criteria

1. `docker compose up --build` from a clean checkout starts Postgres
   (pgvector image), runs migrations once, starts the API and the frontend;
   all services report healthy.
2. `GET /health/live` returns 200. `GET /health/ready` returns 200 when the
   database is reachable and 503 when it is not.
3. `POST /api/v1/investigations` with a valid question returns 201 and a
   `Location` header; the row is persisted with status `queued`.
4. Invalid questions (too short, too long, blank, extra fields) return 422.
5. `GET /api/v1/investigations` lists newest first with `limit`/`offset`
   (max limit 100). `GET /api/v1/investigations/{id}` returns 404 for
   unknown IDs.
6. Alembic upgrade → downgrade → upgrade works on an empty database.
7. The dashboard lets a user submit a question and see it in Recent
   Investigations, backed by the real API (no fixtures). The investigation
   page shows real status and states plainly that processing is not built yet.
8. Frontend uses the design tokens; no hardcoded hex colors in components;
   keyboard focus visible; status shown as text, not color alone.
9. Backend: ruff, mypy, pytest pass. Frontend: typecheck, lint, tests, build
   pass. A GitHub Actions workflow runs the same checks.
10. Public deployment on free tiers (see ADR 0004 and docs/deployment.md),
    smoke-tested at its public URLs, with create rate limits in place.

## Verification commands (M1)

```bash
docker compose down -v && docker compose up --build -d --wait
./scripts/smoke-test.sh
cd backend && ruff check . && ruff format --check . && mypy app && pytest
cd frontend && npm run typecheck && npm run lint && npm run contrast && npm test && npm run build
```

## M1 verification log (2026-10-22, local machine, Docker 29.1.3)

| Criterion | Result |
|---|---|
| 1. Clean `compose up --wait` (volumes wiped) | Pass: db, api, frontend healthy; migrate exited 0 |
| 2. Liveness/readiness | Pass: ready 200; with db stopped ready 503, live 200; recovers on db start |
| 3–5. API behavior | Pass: 22 pytest tests + smoke test |
| 6. Migration round trip | Pass: `test_upgrade_downgrade_upgrade_from_empty`, drift check |
| 7. Real-API dashboard | Pass: submitted via keyboard in browser, landed on detail page with DB data |
| 8. Tokens, focus, text status | Pass: contrast script 20/20 pairs; 3 failing usages fixed; no page overflow at 375px |
| 9. Checks | Pass locally: ruff, mypy, pytest (22), typecheck, oxlint, vitest (8), build |
| 9. GitHub Actions | Pass: run 39892780167 (backend 22 tests, frontend 8 tests, Compose smoke test) |
| 10. Public deployment | Pass (2026-10-23): Render + Neon. `smoke-test.sh` passed against the public URLs (frontend, deep links, readiness with DB, create/read, 422, CORS). Also: 413 on 20 KB body, no CORS header for a foreign origin, per-IP limit 201×3 then 429 behind Render's proxy. Browser: dashboard list, 429 message, and submit → detail page all worked |

## M2 acceptance criteria and verification (2026-10-23)

| Criterion | Result |
|---|---|
| Search real papers through a free metadata provider | Pass: OpenAlex; live query returned 30,606 hits locally and on the public demo |
| Normalize and persist papers with provenance | Pass: `papers` upserted by (provider, provider_id); `metadata_fetched_at`; recorded-response normalization tests |
| Respect provider limits | Pass: 24 h cache (live repeat returned `cached: true`), daily provider-call cap, per-IP limit, bounded retry, fail-fast on spent budget; covered by tests |
| No DB transaction held during the network call | Pass: by design in `papers/service.py` (read transaction ended before calling the provider) |
| Display real results | Pass: Search page and paper page show live OpenAlex data locally and on the public demo |
| Untrusted URLs | Pass: only http(s) stored and rendered; tests for `javascript:` links |
| Checks | Pass: backend 53 tests, mypy on app and tests; frontend 31 tests; CI run on `e133e54` green; public smoke test passed |

Open item: the public API calls OpenAlex without a key, sharing $0.10/day with other tenants
on Render's outbound IP. Add `OPENALEX_API_KEY` on Render to get a dedicated $1/day budget.

## M3 acceptance criteria and verification (2026-10-23)

| Criterion | Result |
|---|---|
| Kafka runs locally with fixed topics and partitions | Pass: KRaft broker in Compose; `kafka-init` creates investigation-requests (3), paper-discovered (6), investigation-failures (1) |
| Versioned event schemas | Pass: envelope plus a payload model per (type, version); unknown versions and extra fields rejected (tests) |
| Transactional outbox | Pass: investigation, task, and event commit together; injected failure rolls all back (test) |
| Dispatcher | Pass: lease-based claim, idempotent producer, backoff; concurrency and crash-recovery tests; broker-outage drill recovered |
| First consumer links papers to investigations | Pass: real run linked 25 OpenAlex papers in 2.2 s end to end; UI shows live progress |
| Task state | Pass: pending → running → succeeded / failed_retryable / failed_permanent, with attempts and errors |
| Idempotency | Pass: duplicate and 4 concurrent deliveries link once (tests) |
| Offsets committed after persistence | Pass: by design in `workers/consumer.py`; worker-down drill processed the waiting event on restart |
| Consumer groups and partitions | Pass: two workers split partitions 1/2, lag 0 |
| CI | Pass locally: Compose job boots Kafka and workers with the recorded sample provider and requires discovery to link papers |

Not in M3, by plan: redelivery-based retries, dead-letter publishing, consumer-lag
metrics, throughput benchmarks (M4). The public demo runs no workers; see
docs/deployment.md.
