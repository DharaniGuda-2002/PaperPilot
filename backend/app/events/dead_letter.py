"""Dead-letter records: messages a consumer could not process.

A record wraps the original message bytes (exactly, base64) plus why it failed,
so it can be inspected and replayed after the cause is fixed. It is not an
EventEnvelope, because the original might not even parse.
"""

import base64
import uuid
from datetime import UTC, datetime
from typing import Literal

from confluent_kafka import Message, Producer
from pydantic import BaseModel, ConfigDict

from app.events.envelope import EventEnvelope

DEAD_LETTER_TOPIC = "investigation-failures"
DEAD_LETTER_SCHEMA_VERSION = 1

FailureKind = Literal["unparseable", "handler_error", "retries_exhausted"]


class DeadLetterRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = DEAD_LETTER_SCHEMA_VERSION
    dead_letter_id: uuid.UUID
    dead_lettered_at: datetime
    consumer_group: str
    failure_kind: FailureKind
    reason: str
    handler_failures: int
    original_topic: str
    original_partition: int
    original_offset: int
    original_key: str | None
    original_value_b64: str
    # Present when the original parsed as an envelope; makes inspection easier.
    event_id: uuid.UUID | None = None
    event_type: str | None = None
    investigation_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None

    def original_value(self) -> bytes:
        return base64.b64decode(self.original_value_b64)

    def original_envelope(self) -> EventEnvelope | None:
        try:
            return EventEnvelope.from_bytes(self.original_value())
        except ValueError:
            return None


def build_record(
    message: Message,
    *,
    consumer_group: str,
    failure_kind: FailureKind,
    reason: str,
    handler_failures: int,
    envelope: EventEnvelope | None,
) -> DeadLetterRecord:
    topic, partition, offset = message.topic(), message.partition(), message.offset()
    assert topic is not None and partition is not None and offset is not None
    key = message.key()
    return DeadLetterRecord(
        dead_letter_id=uuid.uuid4(),
        dead_lettered_at=datetime.now(UTC),
        consumer_group=consumer_group,
        failure_kind=failure_kind,
        reason=reason[:2000],
        handler_failures=handler_failures,
        original_topic=topic,
        original_partition=partition,
        original_offset=offset,
        original_key=key.decode(errors="replace") if isinstance(key, bytes) else key,
        original_value_b64=base64.b64encode(message.value() or b"").decode(),
        event_id=envelope.event_id if envelope else None,
        event_type=envelope.event_type if envelope else None,
        investigation_id=envelope.investigation_id if envelope else None,
        correlation_id=envelope.correlation_id if envelope else None,
    )


class DeadLetterPublishError(RuntimeError):
    pass


def publish_dead_letter(producer: Producer, record: DeadLetterRecord, timeout: float = 10) -> None:
    """Synchronously publish; raise if the broker did not acknowledge, so the
    caller does not commit the original offset and lose the message."""
    errors: list[str] = []
    producer.produce(
        DEAD_LETTER_TOPIC,
        key=(record.original_key or str(record.dead_letter_id)).encode(),
        value=record.model_dump_json().encode(),
        headers={"failure_kind": record.failure_kind, "consumer_group": record.consumer_group},
        on_delivery=lambda err, _msg: errors.append(str(err)) if err else None,
    )
    if producer.flush(timeout) > 0 or errors:
        raise DeadLetterPublishError(errors[0] if errors else "dead-letter delivery timed out")
