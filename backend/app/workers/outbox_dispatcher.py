"""Outbox dispatcher: publishes committed outbox rows to Kafka.

Each cycle:
1. Claim a batch in a short transaction: rows that are unpublished and not
   leased get `locked_until = now() + lease`. FOR UPDATE SKIP LOCKED lets
   several dispatchers run without claiming the same rows.
2. Publish the batch with no database transaction open.
3. Mark delivered rows published; give failed rows a backoff lease.

Guarantee: at-least-once. A crash between publish and mark leaves the lease
to expire and the row is published again; consumers de-duplicate by event_id.

Run: python -m app.workers.outbox_dispatcher
"""

import logging
import signal
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.core.logging import configure_logging
from app.events.envelope import EventEnvelope
from app.events.kafka import make_producer
from app.events.models import OutboxEvent

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 300


@dataclass(frozen=True)
class ClaimedEvent:
    event_id: uuid.UUID
    topic: str
    partition_key: str
    envelope: dict[str, Any]
    attempts: int


class EventPublisher(Protocol):
    def publish(self, events: list[ClaimedEvent]) -> dict[uuid.UUID, str | None]:
        """Publish events; return event_id -> None on success or an error message."""
        ...


_CLAIM_SQL = text(
    """
    UPDATE outbox_events
       SET locked_until = now() + make_interval(secs => :lease_seconds),
           attempts = attempts + 1
     WHERE event_id IN (
           SELECT event_id FROM outbox_events
            WHERE published_at IS NULL
              AND (locked_until IS NULL OR locked_until < now())
            ORDER BY created_at
            LIMIT :batch_size
            FOR UPDATE SKIP LOCKED)
    RETURNING event_id, topic, partition_key, envelope, attempts, created_at
    """
)


def claim_batch(session: Session, *, batch_size: int, lease_seconds: float) -> list[ClaimedEvent]:
    with session.begin():
        rows = session.execute(
            _CLAIM_SQL, {"batch_size": batch_size, "lease_seconds": lease_seconds}
        ).all()
    ordered = sorted(rows, key=lambda r: r.created_at)  # RETURNING order is not guaranteed
    return [
        ClaimedEvent(r.event_id, r.topic, r.partition_key, r.envelope, r.attempts) for r in ordered
    ]


def record_results(
    session: Session, events: list[ClaimedEvent], results: dict[uuid.UUID, str | None]
) -> tuple[int, int]:
    published = failed = 0
    with session.begin():
        for event in events:
            error = results.get(event.event_id, "no delivery report")
            if error is None:
                session.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.event_id == event.event_id)
                    .values(published_at=func.now(), locked_until=None, last_error=None)
                )
                published += 1
            else:
                backoff = min(2**event.attempts, MAX_BACKOFF_SECONDS)
                session.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.event_id == event.event_id)
                    .values(
                        locked_until=func.now() + timedelta(seconds=backoff),
                        last_error=error[:1000],
                    )
                )
                failed += 1
    return published, failed


def dispatch_once(
    session_factory: sessionmaker[Session],
    publisher: EventPublisher,
    *,
    batch_size: int,
    lease_seconds: float,
) -> tuple[int, int]:
    """One claim-publish-record cycle. Returns (published, failed)."""
    with session_factory() as session:
        events = claim_batch(session, batch_size=batch_size, lease_seconds=lease_seconds)
    if not events:
        return 0, 0
    results = publisher.publish(events)
    with session_factory() as session:
        published, failed = record_results(session, events, results)
    if failed:
        logger.warning("outbox publish failures", extra={"published": published, "failed": failed})
    return published, failed


def outbox_backlog(session: Session) -> tuple[int, float | None]:
    """(unpublished rows, age in seconds of the oldest one)."""
    count, oldest = session.execute(
        select(
            func.count(),
            func.extract("epoch", func.now() - func.min(OutboxEvent.created_at)),
        ).where(OutboxEvent.published_at.is_(None))
    ).one()
    return int(count), float(oldest) if oldest is not None else None


class KafkaPublisher:
    def __init__(self, bootstrap_servers: str, flush_timeout_seconds: float) -> None:
        self._producer = make_producer(bootstrap_servers, client_id="outbox-dispatcher")
        self._flush_timeout = flush_timeout_seconds

    def publish(self, events: list[ClaimedEvent]) -> dict[uuid.UUID, str | None]:
        results: dict[uuid.UUID, str | None] = {}

        def on_delivery(event_id: uuid.UUID) -> Any:
            def callback(err: Any, _msg: Any) -> None:
                results[event_id] = None if err is None else str(err)

            return callback

        for event in events:
            envelope = EventEnvelope.model_validate(event.envelope)
            try:
                self._producer.produce(
                    event.topic,
                    key=event.partition_key.encode(),
                    value=envelope.to_bytes(),
                    headers={
                        "event_type": envelope.event_type,
                        "schema_version": str(envelope.schema_version),
                        "correlation_id": str(envelope.correlation_id),
                    },
                    on_delivery=on_delivery(event.event_id),
                )
            except BufferError as exc:  # local queue full; retry next cycle
                results[event.event_id] = str(exc)
            self._producer.poll(0)
        remaining = self._producer.flush(self._flush_timeout)
        if remaining:
            logger.warning("outbox flush timed out", extra={"undelivered": remaining})
        return results

    def close(self) -> None:
        self._producer.flush(self._flush_timeout)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    session_factory = create_session_factory(create_db_engine(settings))
    publisher = KafkaPublisher(
        settings.kafka_bootstrap_servers,
        flush_timeout_seconds=settings.outbox_lease_seconds / 2,
    )
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    logger.info("outbox dispatcher started")
    last_report = 0.0
    while not stop.is_set():
        published, _ = dispatch_once(
            session_factory,
            publisher,
            batch_size=settings.outbox_batch_size,
            lease_seconds=settings.outbox_lease_seconds,
        )
        if time.monotonic() - last_report > 30:
            with session_factory() as session:
                backlog, oldest = outbox_backlog(session)
            logger.info("outbox backlog", extra={"backlog": backlog, "oldest_seconds": oldest})
            last_report = time.monotonic()
        if not published:
            stop.wait(settings.outbox_poll_seconds)
    publisher.close()
    logger.info("outbox dispatcher stopped")


if __name__ == "__main__":
    main()
