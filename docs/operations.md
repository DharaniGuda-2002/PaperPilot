# Operations Runbook (local pipeline)

Commands assume the Compose stack is running. Backend tools run inside the
backend image, so nothing needs installing on the host:

```bash
alias pp='docker compose run --rm --no-deps api python -m'
```

## Health at a glance

```bash
pp app.ops.metrics --window-minutes 60
```

| Field | Meaning | Worry when |
|---|---|---|
| `outbox.backlog` | events not yet published (includes scheduled retries) | grows while `oldest_due_seconds` grows |
| `outbox.oldest_due_seconds` | how long the oldest *due* event has waited | above a few seconds: dispatcher down or Kafka unreachable |
| `consumer_lag.discovery-workers.{partition}` | messages published but not processed | stays above 0 for long: workers down, stuck, or too few |
| `tasks.window.retry_rate` | finished tasks that needed more than one attempt | sudden rise: provider trouble |
| `tasks.window.failure_rate` | finished tasks that failed permanently | any rise: check dead letters |
| `latency_seconds.end_to_end_p95` | investigation created to discovery finished | above minutes: backlog or retries |

Workers also log `consumer lag` every 30 s, and every handled message logs
`event processed` with its partition, offset, outcome, duration, and
correlation ID:

```bash
docker compose logs -f discovery-worker | grep -E '"consumer lag"|"event processed"|dead-lettered'
```

To follow one request end to end, search the logs of all services for its
`correlation_id`. The API returns it as `X-Request-ID`.

## Retries

A temporary failure (OpenAlex unavailable or its quota spent) never blocks a
partition. The worker records `failed_retryable`, `last_error`, and
`next_attempt_at` on the task. It then writes a new `investigation.requested`
event to the outbox with a delay: 30 s, 60 s, 120 s, ... up to 15 min, with
±20% jitter. The investigation stays `running`. After `DISCOVERY_MAX_ATTEMPTS`
(default 4) the task becomes `failed_permanent`, the investigation `failed`,
and the message is dead-lettered.

A handler that *raises* (a bug, or the database down) is retried in place with
backoff. After `CONSUMER_MAX_HANDLER_FAILURES` (default 5) consecutive failures
on the same message, the message is dead-lettered so later messages can flow.

## Dead letters

Topic `investigation-failures`. Each record holds the exact original bytes and
the failure kind:

| `failure_kind` | Cause | Typical fix |
|---|---|---|
| `unparseable` | not JSON, missing fields, or unknown `(event_type, schema_version)` | deploy a consumer that understands the version, or discard |
| `handler_error` | handler raised repeatedly | fix the bug, then replay |
| `retries_exhausted` | provider failed on every attempt | restore the provider (key, quota), then replay |

```bash
pp app.ops.dead_letters list
pp app.ops.dead_letters show <dead_letter_id>
pp app.ops.dead_letters replay <dead_letter_id> --dry-run
pp app.ops.dead_letters replay <dead_letter_id>
```

Inspection never commits offsets. Replay writes a **new** event (new
`event_id`, `causation_id` = original) through the outbox, because consumers
have already recorded the original ID as processed. For
`investigation.requested` it also resets the task to `pending` with 0 attempts
and the investigation to `queued`. Replaying the same dead letter twice is
safe: the second event finds the task already claimed or finished and does
nothing.

## Replaying a topic (reprocessing history)

Topics keep 7 days. To reprocess, for example after fixing a consumer bug,
rewind the group. Because consumers de-duplicate by `(consumer_group,
event_id)`, events that were already applied are skipped. Only events that
never committed results are applied again.

```bash
docker compose stop discovery-worker            # a group must be inactive to reset
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group discovery-workers \
  --topic investigation-requests --reset-offsets --to-datetime 2026-10-23T00:00:00.000 \
  --dry-run                                     # then repeat with --execute
docker compose start discovery-worker
```

Verified 2026-10-23: rewinding to the earliest offset re-delivered every
historical message. Each one was skipped as a duplicate, and no papers, links,
or events were added (see the M4 log in [roadmap.md](roadmap.md)).

To deliberately re-run discovery for an investigation that already succeeded,
use a new event (dead-letter style replay), not an offset reset.

## Scaling

```bash
docker compose up -d --scale discovery-worker=3
```

Parallelism is capped by partitions: `investigation-requests` has 3, so a
fourth worker idles (measured in [benchmarks.md](benchmarks.md)). Adding
partitions later is possible but changes which partition a key maps to, which
is acceptable here because ordering is only needed per investigation and each
investigation's events are independent.

## Housekeeping

`processed_events` is never pruned automatically. Rows older than the topic
retention (7 days) cannot match any redelivery, so they are safe to delete:

```bash
docker compose exec db psql -U paperpilot -c \
  "DELETE FROM processed_events WHERE processed_at < now() - interval '8 days'"
```

## Recovery behavior

| Failure | What happens | Action |
|---|---|---|
| Kafka down | API keeps accepting; events wait in the outbox with backoff | none; they publish on recovery |
| Dispatcher crashes mid-batch | lease expires after 30 s; rows republished (duplicates are harmless) | none |
| Worker crashes mid-task | message not committed and redelivered; a task left `running` is reclaimed after 10 min | none |
| Postgres down | API not ready (503); workers retry the current message with backoff | restore Postgres |
| OpenAlex down or quota spent | scheduled retries, then dead letter | restore access, replay dead letters |
