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
