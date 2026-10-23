# ADR 0003: Kafka with a transactional outbox and idempotent consumers

- Status: accepted; implemented in M3 (2026-10-23)
- Date: 2026-10-22

## Problem

An investigation fans out into many independent tasks (one per paper per
stage). Tasks fail, retry, and must not be lost or applied twice. If the API
writes to Postgres and then publishes to Kafka, a crash between the two leaves
them inconsistent (the dual-write problem).

## Alternatives

1. **Postgres-only job queue** (`SELECT ... FOR UPDATE SKIP LOCKED`). Simpler
   and a valid choice at this scale. It does not give replayable event history,
   consumer groups, or partition-based parallelism.
2. **Publish directly to Kafka from the API.** Dual-write bug.
3. **Transactional outbox + Kafka.** API writes the state row and an
   `outbox_events` row in one transaction; a dispatcher publishes pending rows
   and marks them sent.

## Decision

Option 3. Kafka earns its place through: consumer groups to scale each stage
independently, partitions keyed by paper to parallelize document work,
retained topics for replay after a bug fix, and a dead-letter topic for failed
events. Option 1 is the documented fallback if Kafka proves unjustified.

Events are JSON envelopes validated by Pydantic, with an integer
`schema_version`. No schema registry (keeps the stack free and small); readers
must accept the current and previous version during migrations.

## Guarantees

At-least-once delivery. Consumers record `(consumer_group, event_id)` in
`processed_events` in the same transaction as their results and commit the
Kafka offset afterward. Duplicates are skipped. No end-to-end exactly-once
claim.

## Trade-offs

- Extra moving parts (dispatcher, broker). Single-node local Kafka shows the
  concepts, not production broker redundancy.
- Outbox polling adds latency (poll interval). Acceptable for minutes-long
  investigations.

## Implementation notes (M3)

- The dispatcher uses a **lease** (`locked_until`) instead of holding row locks
  while talking to Kafka: claim in a short transaction, publish with no
  transaction open, then record results. This follows the rule of never holding
  a database transaction across network I/O.
- Producer: `enable.idempotence=true`, `acks=all`, `delivery.timeout.ms`
  shorter than the lease, so a failed delivery is reported before another
  dispatcher can reclaim the row.
- Consumers: `enable.auto.commit=false`, commit after the handler's transaction,
  `cooperative-sticky` assignment.
- Ordering is guaranteed per partition by Kafka. The outbox may reorder events
  across retries, so consumers rely on idempotency and state checks, not on
  strict global order.

## Verification (M3/M4)

Tests for duplicate delivery, worker crash before offset commit, broker outage
during dispatch, retry exhaustion → dead-letter, and replay.
