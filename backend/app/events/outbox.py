from sqlalchemy.orm import Session

from app.events.envelope import EventEnvelope, spec_for
from app.events.models import OutboxEvent


def enqueue(session: Session, envelope: EventEnvelope, *, partition_key: str) -> None:
    """Stage an event in the caller's transaction. It is published only if the
    transaction commits, and it is never lost if the broker is down."""
    spec = spec_for(envelope)
    session.add(
        OutboxEvent(
            event_id=envelope.event_id,
            topic=spec.topic,
            partition_key=partition_key,
            event_type=envelope.event_type,
            schema_version=envelope.schema_version,
            envelope=envelope.model_dump(mode="json"),
        )
    )
