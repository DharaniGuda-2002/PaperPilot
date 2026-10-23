from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.events.envelope import EventEnvelope, spec_for
from app.events.models import OutboxEvent


def enqueue(
    session: Session,
    envelope: EventEnvelope,
    *,
    partition_key: str,
    deliver_after: timedelta | None = None,
) -> None:
    """Stage an event in the caller's transaction. It is published only if the
    transaction commits, and it is never lost if the broker is down.
    `deliver_after` delays publishing (used to schedule retries)."""
    spec = spec_for(envelope)
    extra = {"available_at": func.now() + deliver_after} if deliver_after else {}
    session.add(
        OutboxEvent(
            **extra,
            event_id=envelope.event_id,
            topic=spec.topic,
            partition_key=partition_key,
            event_type=envelope.event_type,
            schema_version=envelope.schema_version,
            envelope=envelope.model_dump(mode="json"),
        )
    )


def outbox_backlog(session: Session) -> tuple[int, float | None]:
    """(unpublished rows, seconds the oldest *due* row has been waiting).

    Rows scheduled for the future (retries) count toward the backlog but not
    toward the waiting time, so a pending retry does not look like a stall."""
    due = OutboxEvent.available_at <= func.now()
    count, oldest = session.execute(
        select(
            func.count(),
            func.extract("epoch", func.now() - func.min(OutboxEvent.available_at).filter(due)),
        ).where(OutboxEvent.published_at.is_(None))
    ).one()
    return int(count), float(oldest) if oldest is not None else None
