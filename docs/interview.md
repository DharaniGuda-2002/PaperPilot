# Interview Preparation

How to explain PaperPilot: what it does, why it is built this way, what was
measured, and what went wrong. Every number here comes from a document in
this repository, linked next to it; quote the source if asked.

## 30-second version

PaperPilot takes a research question, finds papers on OpenAlex, reads the
open-access PDFs, and extracts reported evidence: datasets, baselines,
results, limitations. Every fact is an exact quotation with a page number.
It then works out which results can be compared fairly and writes a report
that never ranks methods it cannot compare. Behind it is a FastAPI app with
Postgres as the source of truth and Kafka workers coordinated through a
transactional outbox. It runs for $0: the full pipeline locally in Docker
Compose, and the API and UI publicly on free tiers.

## Two-minute architecture walk

1. **API** (FastAPI): validates the question, then writes the investigation
   and an outbox row in one transaction. No dual write to Kafka.
2. **Outbox dispatcher** publishes due rows to Kafka. It claims rows with a
   lease, so a crashed dispatcher's rows are picked up again.
3. **Workers**, one consumer group per stage, keyed so related events stay in
   order:
   - discovery: searches OpenAlex and links 25 papers;
   - documents: SSRF-safe PDF fetch, page-exact chunks, local embeddings;
   - evidence: hybrid FTS + pgvector retrieval, rule extraction, validation;
   - reports: comparability rules, a templated report, the final status.
4. **Idempotency**: each consumer records the event id in the same transaction
   as its results and commits the Kafka offset only afterwards. Duplicates are
   skipped.
5. **Failures**: retries are scheduled through the outbox with backoff. After
   the last attempt a message goes to a dead-letter topic with its exact bytes
   and the reason, and can be replayed.
6. **UI** (React): progressive disclosure. Level 1 is the bottom line, level 2
   expandable findings, level 3 an evidence inspector showing the quotation,
   page, retrieval method, and validation checks.

Diagrams and contracts: [architecture.md](architecture.md).

## Decisions worth defending

| Decision | Why | Trade-off accepted | Record |
|---|---|---|---|
| Modular monolith + workers, not microservices | One codebase and one database. Workers scale independently where it matters | Module boundaries are enforced by convention, not network calls | [ADR 0001](adr/0001-modular-monolith-with-workers.md) |
| Postgres is the source of truth; Kafka carries only ids | Replay and recovery never depend on Kafka retention | Workers re-read rows (one extra query per event) | [ADR 0002](adr/0002-postgres-source-of-truth.md) |
| Transactional outbox | Fixes the dual-write problem without distributed transactions | At-least-once delivery, so every consumer must be idempotent | [ADR 0003](adr/0003-kafka-transactional-outbox.md) |
| Retries through the outbox, not by blocking the partition | One bad message never stalls its partition | Retries become new events; ordering within an investigation is by design, not by offset | [architecture.md](architecture.md) §6 |
| Hybrid retrieval with RRF | Full-text search finds exact terms, vectors find paraphrases; RRF needs no score calibration | Measured as not better than either method alone per query; see below | [ADR 0006](adr/0006-documents-retrieval-and-evidence.md) |
| Rules, not an LLM, for extraction and reports | $0, deterministic, and it cannot invent a quotation | Low recall (about 10% of key facts) | [ADR 0006](adr/0006-documents-retrieval-and-evidence.md), [ADR 0007](adr/0007-comparison-and-reports.md) |
| Strength labels by counting checkable sources | Explainable; not a fake confidence score | Coarse: four levels | [ADR 0007](adr/0007-comparison-and-reports.md) |
| Free tiers: Render + Neon; Kafka and workers local-only | No free host runs a persistent broker and workers reliably | Public investigations stay queued, and the UI says so | [ADR 0004](adr/0004-zero-cost-deployment.md) |

## Numbers to quote (with their caveats)

- **Worker scaling:** 1 → 3 discovery workers gave 2.22 → 5.77 tasks/s. A
  fourth worker idled, because the topic has 3 partitions. Throughput tracks
  the busiest partition. [benchmarks.md](benchmarks.md)
- **Replay:** rewinding a consumer group re-delivered about 1,125 messages in
  about 6 s. All were skipped as duplicates and row counts did not change.
  [roadmap.md](roadmap.md) (M4)
- **Real run:** 25 papers, 17 read as full text, documented and
  evidence-extracted in 122 s. [evaluation.md](evaluation.md)
- **Retrieval:** Recall@8 is 0.58 for hybrid per field query (vector alone
  0.69, FTS alone 0.62). Across all pipeline queries, 93% of the needed
  passages reach the extractor. n = 84 facts. [evaluation.md](evaluation.md)
- **Extraction:** recall 0.10 and precision 0.47 on 84 gold facts and 17
  records. All 17 quotations were verified in the stored text.
- **The gold set** was annotated by the AI assistant and is pending human
  review. Say so.
- **API reads:** p95 under 5 ms for report reads at concurrency 1; the
  evidence list (273 KB) is the outlier. Hybrid query p95 is 3.4 ms.
  [benchmarks.md](benchmarks.md)

## Bugs that make good stories

Each was found by running the real system, fixed, and covered by a test.

- **Rate limit bypass (M7).** Uvicorn trusted every proxy, so the client IP was
  the leftmost `X-Forwarded-For` entry, which the client controls. Rotating it
  gave 7 of 7 creates against a limit of 5. The first fix (the last entry)
  looked right locally. On Render, 25 searches without any forgery alternated
  200 and 429, which showed that the last entry varies between proxies there.
  Final fix: key on `CF-Connecting-IP`, which Render's edge sets and refuses
  from clients (403). Verified live: 20 × 200, then 429, forged or not.
  Lesson: verify on the real platform; a local proxy is not the platform.
- **Chunked bodies skipped the size limit (M7).** The middleware trusted
  Content-Length, so a chunked upload was read whole before validation. A
  pure ASGI middleware now counts bytes as they arrive. FastAPI turns errors
  raised during body parsing into 400s, so the middleware answers 413 itself.
- **API image crashed on import (M6).** The report worker imported a sentence
  splitter from the PDF module, which pulled in PyMuPDF; that is not in the
  331 MB API image. A test now imports every API entry point with the ML
  packages blocked.
- **Inflated evidence strength (M6).** A preprint and its published version
  counted as two studies and raised the strength to "moderate". Works with the
  same title are now merged.
- **Kafka IPv6 (M4).** `localhost` resolved to IPv6 first, while Docker
  published only IPv4. This caused intermittent transport failures until
  Kafka advertised 127.0.0.1.
- **Evaluation tolerance (M6).** A fixed ±0.051 treated 0.87 and 0.89 as
  equal. A unit test caught it before any number was published.

## Likely questions

**What happens if a worker dies mid-task?** Its database transaction rolls
back, and the offset was never committed, so Kafka re-delivers after the group
rebalances. The idempotency table makes a second delivery a no-op if the first
one did commit.

**Exactly-once?** No. Delivery is at-least-once, and processing is effectively
once per event through idempotency keys in the same transaction as the
results. Kafka transactions would not cover the Postgres writes.

**Why not just call an LLM?** Budget, and because a model can state things no
quotation supports. The design leaves room for one later: a draft that may
cite only stored evidence ids and is checked against them.

**Why is hybrid search not better here?** RRF over two top-20 lists, cut to 8,
drops chunks that only one method ranks highly. On 84 facts the gap is within
noise. The finding that matters is that retrieval is not the bottleneck:
extraction is.

**How would you scale it?** More partitions, a better-spread key, async
provider calls per worker, and paging the evidence list. Then a real job
queue for PDF fetching per host. Measure before each step; the benchmarks
show partitions are the first ceiling.

**What would you do next?**
- A human review of the gold set, then a second, held-out set for improving
  the extraction rules.
- A least-privilege database role.
- Pruning of `processed_events`.
- Paging the evidence endpoint.

**What are you least happy with?** Extraction recall. The system says "not
found" far more than a human reader would. It never fabricates, but the
reports understate what the papers contain.
