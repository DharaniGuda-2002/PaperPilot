"""Shared Kafka consume loop with commit-after-persist offset discipline.

- Offsets are committed only after the handler returns, i.e. after its
  database transaction committed. A crash in between redelivers the message;
  handlers are idempotent, so that is safe (at-least-once).
- Messages that cannot be processed go to the dead-letter topic before their
  offset is committed:
    * unparseable or unknown-version messages, immediately;
    * messages whose handler raised `consumer_max_handler_failures` times in a
      row (a bug or a bad record), so they stop blocking the partition;
    * messages the handler gave up on (retries exhausted).
  If the dead-letter publish itself fails, the offset is not committed and the
  message is retried, so nothing is silently dropped.
- Transient handler errors (for example the database restarting) seek back to
  the same message and retry with exponential backoff.
- Consumer lag per assigned partition is logged every `LAG_REPORT_SECONDS`.
- SIGTERM/SIGINT finish the current message, then close the consumer, which
  leaves the group cleanly so partitions move to other workers at once.
"""

import logging
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from confluent_kafka import (
    Consumer,
    KafkaError,
    KafkaException,
    Message,
    Producer,
    TopicPartition,
)
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import correlation_id_var
from app.events.dead_letter import (
    DeadLetterPublishError,
    FailureKind,
    build_record,
    publish_dead_letter,
)
from app.events.envelope import EventEnvelope, UnknownEventError, spec_for
from app.events.kafka import make_consumer, make_producer

logger = logging.getLogger(__name__)

MAX_HANDLER_BACKOFF_SECONDS = 30.0
LAG_REPORT_SECONDS = 30.0


@dataclass(frozen=True)
class HandlerResult:
    summary: str
    # Set when the handler gave up on this message; it is then dead-lettered.
    dead_letter_reason: str | None = None


Handler = Callable[[EventEnvelope], HandlerResult]


def run_consumer(
    settings: Settings,
    *,
    group_id: str,
    topic: str,
    handler: Handler,
    stop: threading.Event | None = None,
) -> None:
    stop = stop or threading.Event()
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())

    consumer = make_consumer(settings.kafka_bootstrap_servers, group_id)
    dead_letters = make_producer(settings.kafka_bootstrap_servers, client_id=f"{group_id}-dlq")
    consumer.subscribe([topic])
    logger.info("consumer started", extra={"group": group_id, "topic": topic})

    failures = 0  # consecutive handler failures on the current message
    failing_at: tuple[int, int] | None = None
    last_lag_report = time.monotonic()
    try:
        while not stop.is_set():
            if time.monotonic() - last_lag_report > LAG_REPORT_SECONDS:
                report_lag(consumer, group_id)
                last_lag_report = time.monotonic()

            message = consumer.poll(1.0)
            if message is None:
                continue
            error = message.error()
            if error is not None:
                if error.code() != KafkaError._PARTITION_EOF:
                    logger.error("consumer error", extra={"error": str(error)})
                continue

            position = (message.partition() or 0, message.offset() or 0)
            if position != failing_at:
                failures, failing_at = 0, None

            envelope, parse_error = _parse(message)
            if envelope is None:
                if _dead_letter(
                    consumer, dead_letters, stop, message, group_id, "unparseable", parse_error, 0
                ):
                    consumer.commit(message=message, asynchronous=False)
                continue

            token = correlation_id_var.set(str(envelope.correlation_id))
            started = time.perf_counter()
            try:
                result = handler(envelope)
            except Exception as exc:
                failures += 1
                failing_at = position
                if failures >= settings.consumer_max_handler_failures:
                    logger.exception("handler keeps failing; dead-lettering")
                    if _dead_letter(
                        consumer,
                        dead_letters,
                        stop,
                        message,
                        group_id,
                        "handler_error",
                        repr(exc),
                        failures,
                        envelope,
                    ):
                        consumer.commit(message=message, asynchronous=False)
                        failures, failing_at = 0, None
                    continue
                backoff = min(2.0**failures, MAX_HANDLER_BACKOFF_SECONDS)
                logger.exception(
                    "handler failed; will retry",
                    extra={"event_id": str(envelope.event_id), "failures": failures},
                )
                consumer.seek(_position(message))
                stop.wait(backoff)
                continue
            finally:
                correlation_id_var.reset(token)

            if result.dead_letter_reason and not _dead_letter(
                consumer,
                dead_letters,
                stop,
                message,
                group_id,
                "retries_exhausted",
                result.dead_letter_reason,
                failures,
                envelope,
            ):
                continue
            consumer.commit(message=message, asynchronous=False)
            logger.info(
                "event processed",
                extra={
                    "group": group_id,
                    "event_id": str(envelope.event_id),
                    "event_type": envelope.event_type,
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "outcome": result.summary,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "correlation_id": str(envelope.correlation_id),
                },
            )
    except KafkaException:
        logger.exception("consumer stopped by Kafka error")
        raise
    finally:
        consumer.close()
        dead_letters.flush(10)
        logger.info("consumer stopped", extra={"group": group_id})


def _dead_letter(
    consumer: Consumer,
    producer: Producer,
    stop: threading.Event,
    message: Message,
    group_id: str,
    kind: FailureKind,
    reason: str,
    handler_failures: int,
    envelope: EventEnvelope | None = None,
) -> bool:
    """Publish the message to the dead-letter topic. Returns False (and rewinds to
    the message) if the publish failed, so the caller must not commit."""
    record = build_record(
        message,
        consumer_group=group_id,
        failure_kind=kind,
        reason=reason,
        handler_failures=handler_failures,
        envelope=envelope,
    )
    try:
        publish_dead_letter(producer, record)
    except (DeadLetterPublishError, KafkaException, BufferError):
        logger.exception("dead-letter publish failed; will retry the message")
        consumer.seek(_position(message))
        stop.wait(5)
        return False
    logger.error(
        "message dead-lettered",
        extra={
            "group": group_id,
            "failure_kind": kind,
            "dead_letter_id": str(record.dead_letter_id),
            "partition": record.original_partition,
            "offset": record.original_offset,
            "reason": reason,
        },
    )
    return True


def report_lag(consumer: Consumer, group_id: str) -> dict[int, int]:
    """Lag = newest offset in the partition minus this group's committed offset."""
    assignment = consumer.assignment()
    if not assignment:
        return {}
    lag: dict[int, int] = {}
    for committed in consumer.committed(assignment, timeout=5):
        low, high = consumer.get_watermark_offsets(committed, timeout=5, cached=False)
        position = committed.offset if committed.offset >= 0 else low
        lag[committed.partition] = max(high - position, 0)
    logger.info(
        "consumer lag",
        extra={"group": group_id, "lag_by_partition": lag, "total_lag": sum(lag.values())},
    )
    return lag


def _position(message: Message) -> TopicPartition:
    """Where to resume so the same message is delivered again."""
    topic, partition, offset = message.topic(), message.partition(), message.offset()
    assert topic is not None and partition is not None and offset is not None
    return TopicPartition(topic, partition, offset)


def _parse(message: Message) -> tuple[EventEnvelope | None, str]:
    try:
        envelope = EventEnvelope.from_bytes(message.value() or b"")
        spec_for(envelope)  # reject unknown (event_type, schema_version) up front
        return envelope, ""
    except (ValidationError, UnknownEventError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"[:2000]
