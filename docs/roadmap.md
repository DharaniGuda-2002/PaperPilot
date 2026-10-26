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
- [x] M6 — Comparison and reports (rules, versioned reports, progressive-disclosure UI, gold-set evaluation)
- [x] M7 — Hardening and final deployment (security fixes, audits, clean-checkout run, latency benchmarks, demo guide, interview notes)

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
- `processed_events` grows without bound unless pruned. A prune command exists (post-M7);
  scheduling it is up to the operator.
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

## M6 acceptance criteria and verification (2026-10-23)

| Criterion | Result |
|---|---|
| Deterministic comparability rules | Pass: compare-v2 groups results only on known and equal metric, dataset, protocol, and unit; every excluded result carries its reasons; percentages and ratios on one 0–1 scale; author claims and cross-paper conflicts listed; no cross-group ranking |
| Evidence-backed report generation | Pass: report-v1 from templates over verified evidence ids; published strength rules (counting checkable sources, downgraded by conflicts); limitations, missing information, unresolved questions; immutable versions with all rule versions recorded; `app.ops.reports rebuild` |
| Pipeline end and final status | Pass: report worker (api image) builds once every per-paper task is terminal; `completed` or `partially_completed`; idempotent through the build_report task; backfilled 5 earlier finished investigations on first start |
| Progressive-disclosure UI | Pass: level 1 bottom line, strength, scope, limits; level 2 findings expand in place with their caveat visible while collapsed; level 3 evidence inspector dialog with quotation, page, source, provenance, checks; comparison matrix and sources tabs (`?view=`, arrow keys). Checked in the browser on the real investigation, including a 471 px window |
| Evaluation set with Recall@K and precision/recall | Pass, with caveats: 84 facts from 5 papers, annotated by the AI assistant; reviewed and approved by the project owner on 2026-10-23 (after M7). Hybrid Recall@8 0.583 per field query; pipeline coverage 0.929; extraction recall 0.10 and precision 0.47 overall (n = 17 records) |

Real investigation ("Does retrieval-augmented generation reduce hallucination in
open-domain question answering?", 25 papers; 24 distinct studies after merging 1 duplicate):
- The investigation ended `partially_completed`: 1 paper had no text.
- The report rates the evidence "limited", with 5 key findings.
- 0 of 10 extracted results can be compared directly, because no dataset,
  protocol, or unit is known for any of them.
- No analyzed paper compares RAG against another method in a way the rules
  could read.

Bugs found by the full-stack run, each fixed (most with a regression test):
- The report worker and API crashed with `ModuleNotFoundError: pymupdf`.
  Comparison imported the sentence splitter from the PDF module. The splitter
  now has its own module, and a test runs every api-image entry point with
  PyMuPDF, torch, and sentence-transformers blocked.
- The first real report had 0 claims, because claimants outside the method
  lexicon were dropped. compare-v2 reads name-like claimants.
- A preprint and its published version counted as two studies and raised the
  strength to "moderate". Works with the same title are now merged.
- The bottom line led with a claim unrelated to the question. It now answers
  from claims that involve the question's methods, or says that none do.
- Family-level disagreements were missing from unresolved questions.
- In the UI, the comparison table widened the page at phone width (grid
  `min-width`). A no-text paper was labeled "abstract only". Singular counts
  read "1 paper report".
- In the evaluation, a fixed numeric tolerance treated 0.87 and 0.89 as equal.
  Tolerance now follows the gold value's written precision.

Open items:
- Extraction recall is the limiting factor, not retrieval (see evaluation.md).
  Improving the rules needs a second, held-out gold set, so that the rules are
  not tuned to the one used for measurement.
- ~~The gold set needs a human review pass.~~ Done 2026-10-23: approved as annotated.
- The public demo still has no workers, so reports exist only locally.

## M7 acceptance criteria and verification (2026-10-23)

| Criterion | Result |
|---|---|
| Security checks | Pass, with 2 real fixes (below). `pip-audit` (api + ml) and `npm audit`: no known vulnerabilities. gitleaks over the full history: 49 commits, no leaks. All three now run in a CI `security` job. Notes, controls, and gaps: [security.md](security.md) |
| Full tests | Pass: 263 backend tests (real Postgres + pgvector + Kafka in CI), 41 frontend tests, typecheck, lint, contrast check, Compose end-to-end job |
| Benchmarks | Pass: discovery scaling (M4), plus API read latency and hybrid query time ([benchmarks.md](benchmarks.md)); scripts and raw results committed |
| Documentation | Pass: security notes, demo guide, local troubleshooting, interview notes; README screenshots; stale UI copy ("reports are being built") replaced |
| Clean checkout | Pass: fresh `git clone` of `main`, `cp .env.example .env`, `docker compose up --build -d --wait` with empty volumes (separate project name), then `smoke-test.sh` passed. With `EXPECT_PIPELINE=1`, live OpenAlex and PDF downloads finished 25 papers with a report (`partially_completed`) in about 3.5 min. Image layers came from the local cache; CI's Compose job builds from scratch on every push |
| Deployment verification | Pass: public smoke test (frontend, deep links, readiness, create, read, validation, CORS); new CSP and frame headers served by Render; API security headers present; per-client limit verified live (below) |
| Screenshots and demo instructions | Pass: [demo.md](demo.md), 5 screenshots from the real investigation; the resilience step was run (worker stopped: investigation stays queued; started: 25 papers linked in about 4 s) |
| Interview preparation | Pass: [interview.md](interview.md) |

Security bugs found and fixed:
- **Per-client rate limits could be bypassed** with a forged `X-Forwarded-For`.
  - Cause: uvicorn ran with `--forwarded-allow-ips='*'`, so the leftmost,
    client-controlled entry became the client address. Locally, 7 of 7 creates
    succeeded against a limit of 5.
  - First fix: key on the proxy-appended entry. It worked locally, but on
    Render 25 unforged searches alternated 200/429, because the last entry
    there varies between proxies.
  - Final fix: `CLIENT_IP_HEADER=CF-Connecting-IP` on Render; its edge sets
    the header and rejects client-sent values with 403. Compose keeps the
    nginx hop count.
  - Verified live: 20 × 200, then 429, with and without a forged header.
- **Chunked request bodies skipped the 16 KB limit.** A 20 KB chunked POST got
  422 after being read whole. An ASGI middleware now counts streamed bytes and
  answers 413 (verified through nginx and uvicorn).

Other fixes:
- A "6:2:2" split ratio was shown as percentages (compare-v3).
- The smoke test's pipeline wait is configurable (`PIPELINE_TIMEOUT`).

### Post-M7 hardening (2026-10-24)

- Evidence list takes `offset`; the response carries `X-Total-Count`. The UI reads
  pages of 500 until one is short. Test: `test_evidence_list_pages_and_reports_the_total`.
- `python -m app.ops.maintenance prune-processed-events` (refuses a cutoff within the 7-day
  topic retention). Tests: `test_maintenance.py`.
- Least-privilege runtime role (`app.ops.runtime_role`), wired into Compose: `migrate` owns
  the schema and provisions `paperpilot_app`; services use it. `test_runtime_role.py` shows
  the role does DML and is refused DDL. A full Compose rebuild plus smoke test and a
  pipeline run completed with no permission errors in service logs. Not applied to the
  Render/Neon demo (needs dashboard changes by the owner).
- UI redesign (teal palette from the user's tokens): pipeline stepper on the investigation
  page, four-step evidence strength meter with the published definition, hatched empty cells in
  the comparison matrix, evidence inspector as a right-hand drawer (full sheet under 640 px).
  Link and accent text moved from brand-600 (3.65:1) to brand-700; the contrast script has the
  new pairs and passes. 43 frontend tests, no horizontal overflow at 375 px, screenshots
  retaken from the local stack.
- Services renamed to `paperpilot-research` (web) and `paperpilot-research-api` for cleaner
  URLs; both live and smoke-tested (ready 200, CORS, 422 on bad input, 20 x 200 then 429).
- Plain-language pass: rewritten landing page, glossary tooltips (`InfoTip`) on strength,
  abstract-only, comparable, protocol, quotation and validation terms, a "How to read this
  report" panel, a FAQ page (common and harder questions) and an About page.
- Redesign from the desktop mocks (blue palette `#246BFD` on `#F6F8FB`): top bar with global
  search, left sidebar with help links, white cards with 1 px borders, blue primary buttons,
  sans-serif headings (serif kept only for quotations), FAQ accordion with +/- markers, source
  chips on the new-investigation form. Content stays real; the mocks' sample numbers and names
  were not copied. Link text uses `#1D4ED8` and body-on-page text `#4A5A6E` to keep 4.5:1; the
  contrast script covers the new pairs and passes.
- Example investigation for the public demo: `investigations.is_example` (migration 0008),
  `GET /api/v1/investigations/examples`, and `python -m app.ops.example_data export|import`.
  The committed files in `data/examples/` are four real local runs (no text,
  chunks or embeddings). Tests export, wipe, import, and compare the report and evidence;
  the real file was also imported twice into a scratch database with unchanged row counts.
  The landing page links to it, and it carries an "Example" notice.
- Not done: a second held-out gold set (needs a human reviewer).

### Final definition of done

| Item | Status |
|---|---|
| Runs from a clean checkout | Yes (above) |
| Migrations work on a clean database | Yes: clean-checkout run, plus CI on every push |
| Core UI and API workflow | Yes |
| Kafka coordinates background processing | Yes (local; the public demo has no workers, as documented) |
| Outbox addresses dual writes | Yes (M3) |
| Duplicate delivery does not corrupt data | Yes: tests, plus a replay of about 1,125 messages with unchanged row counts (M4) |
| Failures retried safely | Yes: scheduled retries, dead letters, replay (M4) |
| Partial completion represented | Yes: `partially_completed` and per-task status (M6) |
| Multiple workers process concurrently | Yes, up to the partition count (benchmarks) |
| Evidence traceable to source | Yes: exact quotation, page, chunk, retrieval and validation provenance |
| Reports separate findings, uncertainty, missing information | Yes |
| Progressive disclosure | Yes: three levels |
| Light-theme design system applied | Yes: teal token palette, contrast script passes, redesigned progress, strength meter, inspector drawer (post-M7) |
| Tests and CI pass | Yes |
| Benchmarks are real and reproducible | Yes |
| Deployment instructions match | Yes: updated in M7 |
| Public deployment smoke-tested | Yes |
| No paid dependency | Yes |
| Feature-wise commits | Yes |
| Architecture and trade-offs documented | Yes: 7 ADRs |
| Explainable in an interview | [interview.md](interview.md) |

Open items (none block the definition of done):
- A second, held-out gold set for improving the extraction rules. The first set
  was reviewed and approved as annotated on 2026-10-23.
- The database runtime role is the owner role (see security.md).
- `processed_events` pruning is manual.
- The evidence endpoint is unpaginated.
- The UI redesign from the mockup collage is still pending.
- Local test data: 12 investigations named "spoof test question …" were created
  by the M7 rate-limit experiments in the developer's local database.

