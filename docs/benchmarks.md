# Benchmarks

## Discovery throughput: 1 to 4 workers (2026-10-23)

**Question:** how does discovery throughput scale with worker count, and what
limits it?

### Setup

| Item | Value |
|---|---|
| Machine | Apple Silicon Mac (Darwin arm64), 8 CPU, 16 GB; Docker Desktop 29.1.3 |
| Stack | Local Compose: Postgres 17, Kafka 4.2.2 single node, 1 dispatcher, N discovery workers |
| Topic | `investigation-requests`, 3 partitions, keyed by investigation id |
| Provider | Recorded OpenAlex sample (`PAPER_PROVIDER=fixture`) with a fixed **400 ms** simulated latency per search, so runs are repeatable and spend no OpenAlex quota. A live OpenAlex search took about 0.5 s locally. |
| Workload | 90 investigations created back to back through the API's service code (investigation + task + outbox event per transaction); each links 2 papers |
| Runs | 3 per worker count; the table shows the median and each run |
| Script | `evaluation/benchmarks/run.sh 90 3 400`; raw results in `evaluation/benchmarks/results/` |

Definitions: **throughput** = tasks / (last task finished − first investigation
created). **End-to-end** = task finished − investigation created, per
investigation, so it includes queueing behind earlier work. **Processing** =
time a worker spent on one task (provider call + database writes).

### Results

| Workers | Runs | Tasks OK | Throughput (tasks/s), median [runs] | End-to-end p50 (s) | End-to-end p95 (s) | Processing p50 (s) | Busiest partition (msgs of 90) |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 270/270 | 2.22 (1.00x) [2.21, 2.22, 2.26] | 20.1 | 38.6 | 0.421 | 38, 36, 39 |
| 2 | 3 | 270/270 | 3.65 (1.64x) [4.00, 3.54, 3.65] | 10.2 | 22.8 | 0.421 | 38, 34, 39 |
| 3 | 3 | 270/270 | 5.77 (2.60x) [5.77, 5.55, 5.81] | 7.2 | 14.0 | 0.422 | 35, 36, 34 |
| 4 | 3 | 270/270 | 6.59 (2.97x) [6.74, 6.59, 5.91] | 7.0 | 12.6 | 0.421 | 31, 31, 34 |

Maximum consumer lag in every run was 84–90: all 90 events were published
before workers caught up, as intended for a burst workload.

### What the numbers say

1. **One worker is limited by per-task time.** 0.42 s per task gives at most
   about 2.4 tasks/s; measured 2.22.
2. **Throughput tracks the busiest partition, not the worker count.** A
   partition is consumed by one worker, in order. For 3 and 4 workers,
   wall time ÷ messages in the busiest partition was 0.43–0.46 s in every run,
   which is the per-task time. Partition keys are random investigation ids, so
   90 messages split unevenly across runs (from 30/29/31 to 37/39/14).
3. **The fourth worker did nothing.** With 4 workers and 3 partitions, Kafka
   assigned partitions 1/1/1/0 (`kafka-consumer-groups --describe --members`
   showed one member with 0 partitions). The 4-worker runs were faster only
   because their keys happened to split more evenly (busiest partition 31–34
   vs 34–36). They are not evidence of scaling past 3.
4. **Two workers give 1.64x, not 2x**, because one worker owns two partitions
   and finishes last.

**Conclusion:** worker parallelism is capped by the partition count (3), and
skew between partitions costs about 10–30% at this batch size. To go further:
add partitions (more possible consumers), and at real scale prefer a key with
an even spread. A per-worker concurrency limit or async provider calls would
raise per-worker throughput, but the provider's own rate limit (OpenAlex: 10
requests/s without a key, 30 with) is the real ceiling for live searches.

### Limitations

- Simulated provider latency; live OpenAlex latency varies and is
  rate-limited. These numbers measure the pipeline, not OpenAlex.
- One machine, single Kafka broker, 3 runs per setting: medians are indicative,
  not statistically strong.
- 90 tasks per run; skew effects shrink as batches grow.

## API read latency and retrieval query time (2026-10-23)

**Question:** how fast are the read paths the UI uses, and how fast is the
hybrid retrieval query each evidence task runs 7 times per paper?

**Setup:**
- Same machine as above. Local Compose stack: one uvicorn process, no
  `--workers`, sync endpoints on its thread pool.
- Postgres 17 + pgvector with 3,046 chunks in total.
- Requests went directly to the API on port 8000, without nginx.
- Data: the real RAG investigation (25 papers, its report, 273 KB of evidence).

**Method:**
- `python3 evaluation/benchmarks/api_latency.py --investigation <id>`: 10
  warm-up requests, then 200 timed requests per endpoint at concurrency 1 and 8.
  Raw results are in `evaluation/benchmarks/results/*-api-latency.json`.
- Create and search are excluded, because the rate limiter would set their
  numbers.

| Endpoint | Body | c=1 p50 / p95 (ms) | c=8 p50 / p95 (ms) | c=1 → c=8 req/s |
|---|---|---|---|---|
| `GET /health/ready` (DB ping) | 42 B | 1.6 / 2.5 | 8.1 / 13.9 | 587 → 913 |
| `GET /investigations?limit=20` | 4.5 KB | 2.1 / 3.5 | 12.8 / 19.0 | 423 → 605 |
| `GET /investigations/{id}` | 0.3 KB | 1.7 / 2.5 | 9.6 / 14.9 | 550 → 775 |
| `GET /investigations/{id}/papers` (25) | 47 KB | 3.0 / 4.4 | 19.0 / 26.9 | 310 → 400 |
| `GET /investigations/{id}/evidence` (all) | 273 KB | 13.0 / 32.2 | 112.3 / 165.1 | 64 → 69 |
| `GET /investigations/{id}/report` | 34 KB | 2.4 / 4.0 | 15.1 / 26.3 | 370 → 488 |
| `GET /evidence/{id}` (inspector) | 1.9 KB | 2.8 / 3.6 | 17.0 / 22.0 | 341 → 463 |

0 non-200 responses out of 2,800.

Hybrid retrieval: `python -m app.evaluation.retrieval_latency <id>` in the ml
image (embeddings computed beforehand, so this is database time only).

| Calls | p50 | p95 | max |
|---|---|---|---|
| 17 full-text papers (1,333 chunks) × 7 queries × 3 = 357 | 1.3 ms | 3.4 ms | 6.4 ms |

**What the numbers say:**
- Every read the report UI makes is under 5 ms at p95 for a single user.
- With 8 concurrent clients, throughput rises only 1.3–1.6×, and latency grows
  about 6×. One Python process serializes much of the work. Adding
  `uvicorn --workers` would help locally; the free Render instance (0.1 CPU) is
  the real limit on the demo.
- The evidence list is the outlier: 273 KB and every validation check for every
  record in one response. It is the first candidate for paging if
  investigations grow. At 13 ms p50 it does not justify the change yet.
- Retrieval is not a bottleneck. A paper's 7 queries take about 10 ms in
  total, against seconds for PDF download and embedding.

**Limitations:**
- Local machine, warm caches, and one investigation's data. These are not
  numbers for the hosted demo.
- Render free instances sleep, and the first request after idle took about a
  minute in M1.

