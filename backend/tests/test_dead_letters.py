"""Dead-letter records and replay, without Kafka."""

import base64
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.events.dead_letter import DeadLetterRecord
from app.events.envelope import EventEnvelope
from app.ops.dead_letters import ReplayError, replay

QUESTION = "Do graph neural networks beat gradient boosting for fraud detection?"


def record_for(value: bytes, envelope: EventEnvelope | None = None) -> DeadLetterRecord:
    return DeadLetterRecord(
        dead_letter_id=uuid.uuid4(),
        dead_lettered_at=datetime.now(UTC),
        consumer_group="discovery-workers",
        failure_kind="retries_exhausted",
        reason="Gave up after 4 attempts: OpenAlex daily usage budget is exhausted",
        handler_failures=0,
        original_topic="investigation-requests",
        original_partition=1,
        original_offset=42,
        original_key=str(envelope.investigation_id) if envelope else None,
        original_value_b64=base64.b64encode(value).decode(),
        event_id=envelope.event_id if envelope else None,
    )


def test_record_preserves_original_bytes_exactly() -> None:
    raw = b"\x00not json\xff"
    record = record_for(raw)
    restored = DeadLetterRecord.model_validate_json(record.model_dump_json())
    assert restored.original_value() == raw
    assert restored.original_envelope() is None


def test_replay_resets_task_and_enqueues_a_new_event(client: TestClient, engine: Engine) -> None:
    investigation_id = client.post("/api/v1/investigations", json={"question": QUESTION}).json()[
        "id"
    ]
    with engine.begin() as conn:
        original = EventEnvelope.model_validate(
            conn.scalar(text("SELECT envelope FROM outbox_events"))
        )
        # Simulate the state after retries were exhausted.
        conn.execute(
            text(
                "UPDATE investigation_tasks SET status = 'failed_permanent', attempts = 4, "
                "last_error = 'Gave up'"
            )
        )
        conn.execute(text("UPDATE investigations SET status = 'failed'"))

    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        replayed = replay(session, record_for(original.to_bytes(), original))
        session.commit()

    assert replayed.event_id != original.event_id
    assert replayed.causation_id == original.event_id
    assert replayed.payload == original.payload
    with engine.connect() as conn:
        task = conn.execute(
            text("SELECT status, attempts, last_error FROM investigation_tasks")
        ).one()
        status = conn.scalar(text("SELECT status FROM investigations"))
        row = conn.execute(
            text("SELECT partition_key FROM outbox_events WHERE event_id = :id"),
            {"id": replayed.event_id},
        ).one()
    assert (task.status, task.attempts) == ("pending", 0)
    assert task.last_error.startswith("Replayed from dead letter")
    assert status == "queued"
    assert row.partition_key == investigation_id


def test_unparseable_dead_letters_cannot_be_replayed(engine: Engine) -> None:
    with sessionmaker(bind=engine)() as session, pytest.raises(ReplayError, match="not a valid"):
        replay(session, record_for(b"garbage"))
