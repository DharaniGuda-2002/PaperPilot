# Roadmap and Progress

Each milestone is finished and verified before the next starts.

## Checklist

- [x] M0 — Repository inspection, architecture, ADRs, acceptance criteria
- [x] M1 — Application foundation (local, CI, and public demo verified)
- [x] UI redesign — landing page, sidebar app shell, dashboard with real status counts
      (2026-10-23; screens without backend data wait for their milestones)
- [x] M2 — Paper discovery (OpenAlex search, cached and rate limited; verified locally and on the public demo)
- [x] M3 — Kafka pipeline (outbox, dispatcher, idempotent discovery worker; local deployment)
- [x] M4 — Distributed reliability (scheduled retries, dead letters, replay, lag metrics, benchmarks)
- [x] M5 — Retrieval and evidence (permitted PDFs, SSRF guard, embeddings, hybrid search, rule-based extraction, validation)
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

## M4 acceptance criteria and verification (2026-10-23)

| Criterion | Result |
|---|---|
| Redelivery-based retries with backoff | Pass: retry events scheduled through the outbox (`available_at`); tests for scheduling, success on retry, exhaustion, delay curve. Drill: attempts at +0 s, +2 s, +5 s with base 2 s, then `failed_permanent` |
| Partition never blocked by one bad message | Pass: real-Kafka test sends poison, always-failing, and exhausted messages ahead of a good one; the good one is processed and lag returns to 0 |
| Dead-letter handling and inspection | Pass: three failure kinds dead-lettered with exact bytes and reasons; offset committed only after the DLQ write; `dead_letters list/show` used in the drill |
| Replay | Pass: dead-letter replay test; drill replayed the exhausted investigation after fixing the cause → 25 papers linked. Group rewind to earliest re-delivered about 1,125 messages in about 6 s, all skipped as duplicates, row counts unchanged |
| Consumer lag and throughput metrics | Pass: workers log lag every 30 s; `app.ops.metrics` reports backlog, per-partition lag, retry/failure rates, latency p50/p95, throughput |
| Single vs multi-worker benchmark | Pass: [benchmarks.md](benchmarks.md). 1 → 3 workers: 2.22 → 5.77 tasks/s; a 4th worker idles (3 partitions); throughput tracks the busiest partition |
| Kafka in CI | Pass: backend job runs a real broker (`REQUIRE_KAFKA=1`) |

Findings fixed during M4:
- Kafka advertised `localhost`, which resolved to IPv6 first while Docker published only
  IPv4, causing intermittent transport failures and slow tests. It now advertises 127.0.0.1.

Open items:
- `processed_events` grows without bound. Rows older than topic retention (7 days) can
  never match a redelivery and can be pruned by a scheduled job (not built).
- The benchmark spent the local daily provider-call cap (it counts cache rows), which then
  made a drill fail with "paper search daily limit reached". The benchmark data was
  removed afterwards. The cap behaved as designed; benchmark runs should use a separate
  database or clean up after themselves.

## M5 acceptance criteria and verification (2026-10-23)

| Criterion | Result |
|---|---|
| Permitted PDF retrieval only | Pass: fetch only when OpenAlex marks open access and lists a PDF; robots.txt honored; crawl delay shared across workers (Postgres schedule); abstract fallback with the reason recorded |
| SSRF protection | Pass: 39 fetch tests (schemes, ports, credentials, private/loopback/link-local/CGNAT/IPv4-mapped addresses, redirect hops, connected-peer check, size caps). Live: cloud-metadata IP, localhost port, and `127.0.0.1.nip.io` blocked |
| Text extraction with page references | Pass: page-exact chunks; two-column reading order fixed after a real arXiv paper interleaved columns; 5 of 5 cited pages confirmed against original PDFs |
| Local embeddings | Pass: all-MiniLM-L6-v2 at a pinned revision, baked into a CPU-only ML image (2.2 GB; the api image stays 331 MB) |
| pgvector hybrid retrieval | Pass: FTS + cosine with RRF; per-candidate method and ranks; retrieval tests on real Postgres + pgvector |
| Structured evidence with provenance | Pass: 7 fields; exact quotation, page, chunk, retrieval method, extraction version; reported / uncertain / not_found / unavailable |
| Validation | Pass: 4 deterministic checks per record, stored as history; failures kept as rejected |
| End to end | Pass: real run of 25 papers in 122 s (17 full text); CI pipeline with recorded papers and fetching off checks documents and evidence for every paper |

Quality (details and sample sizes in [evaluation.md](evaluation.md)): metric values
correct 9 of 10 and method credit correct 7 of 10, reviewed by hand (n = 10).

Bugs found by the full-stack run, each fixed with a regression test:
workers missing other modules' tables (`NoReferencedTableError`), events outliving
their investigations, nginx caching the API's old address, the smoke test exiting
silently under pipefail, rules-v1 misreading numbers in names, and duplicate works
from the provider.

Open items:
- A paper's document is shared. If it was stored as abstract-only for a temporary
  reason (fetching disabled, fetch failed), later investigations reuse it instead of
  retrying full text. A re-fetch policy is not built.
- Lexicon coverage is limited to ML-adjacent fields; extraction recall is not
  measured yet (M6 evaluation set).
- The public demo (Render) runs no workers, so documents and evidence are local only.
