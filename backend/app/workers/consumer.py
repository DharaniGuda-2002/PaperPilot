"""Shared Kafka consume loop with commit-after-persist offset discipline.

- Offsets are committed only after the handler returns, i.e. after its
  database transaction committed. A crash in between redelivers the message;
  handlers are idempotent, so that is safe (at-least-once).
- A message that cannot be parsed is logged and skipped (dead-letter topic
  in M4). Retrying an unparseable message would block its partition forever.
- If the handler raises (database down, bug), the offset is not committed and
  the consumer seeks back to the same message after a backoff.
- SIGTERM/SIGINT finish the current message, then close the consumer, which
  leaves the group cleanly so partitions move to other workers at once.
"""

import logging
import signal
import threading
import time
from collections.abc import Callable

from confluent_kafka import KafkaError, KafkaException, Message, TopicPartition
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import correlation_id_var
from app.events.envelope import EventEnvelope, UnknownEventError
from app.events.kafka import make_consumer

logger = logging.getLogger(__name__)

MAX_HANDLER_BACKOFF_SECONDS = 30.0


def run_consumer(
    settings: Settings,
    *,
    group_id: str,
    topic: str,
    handler: Callable[[EventEnvelope], str],
    stop: threading.Event | None = None,
) -> None:
    stop = stop or threading.Event()
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())

    consumer = make_consumer(settings.kafka_bootstrap_servers, group_id)
    consumer.subscribe([topic])
    logger.info("consumer started", extra={"group": group_id, "topic": topic})
    failures = 0
    try:
        while not stop.is_set():
            message = consumer.poll(1.0)
            if message is None:
                continue
            error = message.error()
            if error is not None:
                if error.code() != KafkaError._PARTITION_EOF:
                    logger.error("consumer error", extra={"error": str(error)})
                continue

            envelope = _parse(message)
            if envelope is None:
                consumer.commit(message=message, asynchronous=False)
                continue

            token = correlation_id_var.set(str(envelope.correlation_id))
            started = time.perf_counter()
            try:
                outcome = handler(envelope)
            except Exception:
                failures += 1
                backoff = min(2.0**failures, MAX_HANDLER_BACKOFF_SECONDS)
                logger.exception(
                    "handler failed; will retry", extra={"event_id": str(envelope.event_id)}
                )
                consumer.seek(_position(message))
                stop.wait(backoff)
                continue
            finally:
                correlation_id_var.reset(token)

            consumer.commit(message=message, asynchronous=False)
            failures = 0
            logger.info(
                "event processed",
                extra={
                    "group": group_id,
                    "event_id": str(envelope.event_id),
                    "event_type": envelope.event_type,
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "outcome": outcome,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "correlation_id": str(envelope.correlation_id),
                },
            )
    except KafkaException:
        logger.exception("consumer stopped by Kafka error")
        raise
    finally:
        consumer.close()
        logger.info("consumer stopped", extra={"group": group_id})


def _position(message: Message) -> TopicPartition:
    """Where to resume so the same message is delivered again."""
    topic, partition, offset = message.topic(), message.partition(), message.offset()
    assert topic is not None and partition is not None and offset is not None
    return TopicPartition(topic, partition, offset)


def _parse(message: Message) -> EventEnvelope | None:
    try:
        return EventEnvelope.from_bytes(message.value() or b"")
    except (ValidationError, UnknownEventError, ValueError):
        logger.error(
            "skipping unparseable message",
            extra={
                "topic": message.topic(),
                "partition": message.partition(),
                "offset": message.offset(),
            },
        )
        return None
