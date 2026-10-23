"""Creating an investigation must write the investigation, its discovery task,
and the outbox event in one transaction."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.events import outbox
from app.events.envelope import EventEnvelope

QUESTION = "Do graph neural networks beat gradient boosting for fraud detection?"
REQUEST_ID = "6f1c2c1e-3a4b-4c5d-9e8f-0a1b2c3d4e5f"


def test_create_writes_task_and_outbox_event(client: TestClient, engine: Engine) -> None:
    response = client.post(
        "/api/v1/investigations", json={"question": QUESTION}, headers={"X-Request-ID": REQUEST_ID}
    )
    investigation_id = response.json()["id"]

    with engine.connect() as conn:
        task = conn.execute(text("SELECT id, kind, status FROM investigation_tasks")).one()
        row = conn.execute(
            text("SELECT topic, partition_key, published_at, envelope FROM outbox_events")
        ).one()

    assert (task.kind, task.status) == ("discover_papers", "pending")
    assert row.topic == "investigation-requests"
    assert row.partition_key == investigation_id
    assert row.published_at is None
    event = EventEnvelope.model_validate(row.envelope)
    assert str(event.investigation_id) == investigation_id
    assert event.entity_id == task.id
    assert str(event.correlation_id) == REQUEST_ID
    assert event.payload == {"task_id": str(task.id), "question": QUESTION}


def test_failed_outbox_write_rolls_back_everything(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_enqueue(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated outbox failure")

    monkeypatch.setattr("app.investigations.service.enqueue", broken_enqueue)
    with pytest.raises(RuntimeError):
        client.post("/api/v1/investigations", json={"question": QUESTION})

    with engine.connect() as conn:
        for table in ("investigations", "investigation_tasks", "outbox_events"):
            assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0, table  # noqa: S608
    assert outbox.enqueue is not broken_enqueue
