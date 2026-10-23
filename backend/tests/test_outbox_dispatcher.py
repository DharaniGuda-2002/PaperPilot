"""Dispatcher behavior against real Postgres, with a fake publisher standing in
for Kafka (the Kafka path is covered by the end-to-end compose test)."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.workers.outbox_dispatcher import (
    ClaimedEvent,
    claim_batch,
    dispatch_once,
    outbox_backlog,
)

QUESTION = "Do graph neural networks beat gradient boosting for fraud detection?"


class FakePublisher:
    def __init__(self, fail_ids: set[uuid.UUID] | None = None) -> None:
        self.published: list[ClaimedEvent] = []
        self.fail_ids = fail_ids or set()

    def publish(self, events: list[ClaimedEvent]) -> dict[uuid.UUID, str | None]:
        results: dict[uuid.UUID, str | None] = {}
        for event in events:
            if event.event_id in self.fail_ids:
                results[event.event_id] = "simulated broker outage"
            else:
                self.published.append(event)
                results[event.event_id] = None
        return results


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


@pytest.fixture
def three_events(client: TestClient) -> Iterator[list[str]]:
    ids = [
        client.post("/api/v1/investigations", json={"question": f"{QUESTION} {n}"}).json()["id"]
        for n in range(3)
    ]
    yield ids


def outbox_rows(engine: Engine) -> list[tuple[str, bool, int]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT partition_key, published_at IS NOT NULL, attempts FROM outbox_events "
                "ORDER BY created_at"
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


def test_publishes_pending_events_in_order_and_marks_them(
    three_events: list[str], sessions: sessionmaker[Session], engine: Engine
) -> None:
    publisher = FakePublisher()
    assert dispatch_once(sessions, publisher, batch_size=10, lease_seconds=30) == (3, 0)

    assert [e.partition_key for e in publisher.published] == three_events
    assert all(e.topic == "investigation-requests" for e in publisher.published)
    assert outbox_rows(engine) == [(i, True, 1) for i in three_events]
    with sessions() as session:
        assert outbox_backlog(session) == (0, None)

    # Nothing left: a second cycle publishes nothing.
    assert dispatch_once(sessions, publisher, batch_size=10, lease_seconds=30) == (0, 0)


def test_broker_failure_keeps_event_pending_with_backoff(
    three_events: list[str], sessions: sessionmaker[Session], engine: Engine
) -> None:
    with sessions() as session:
        failing = {
            uuid.UUID(str(session.scalar(text("SELECT event_id FROM outbox_events LIMIT 1"))))
        }
    publisher = FakePublisher(fail_ids=failing)
    assert dispatch_once(sessions, publisher, batch_size=10, lease_seconds=30) == (2, 1)

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT published_at, attempts, last_error, locked_until > now() AS backing_off "
                "FROM outbox_events WHERE event_id = :id"
            ),
            {"id": next(iter(failing))},
        ).one()
    assert row.published_at is None
    assert row.attempts == 1
    assert row.last_error == "simulated broker outage"
    assert row.backing_off

    # Still backing off: not retried immediately.
    assert dispatch_once(sessions, FakePublisher(), batch_size=10, lease_seconds=30) == (0, 0)

    # Once the backoff passes, the broker is back and the event goes out.
    with engine.begin() as conn:
        conn.execute(text("UPDATE outbox_events SET locked_until = now() - interval '1 second'"))
    assert dispatch_once(sessions, FakePublisher(), batch_size=10, lease_seconds=30) == (1, 0)
    with sessions() as session:
        assert outbox_backlog(session)[0] == 0


def test_concurrent_dispatchers_claim_disjoint_rows(
    three_events: list[str], sessions: sessionmaker[Session]
) -> None:
    with sessions() as a, sessions() as b:
        first = claim_batch(a, batch_size=2, lease_seconds=30)
        second = claim_batch(b, batch_size=10, lease_seconds=30)
    assert len(first) == 2
    assert len(second) == 1
    assert {e.event_id for e in first}.isdisjoint({e.event_id for e in second})


def test_crash_after_publish_republishes_after_lease_expires(
    three_events: list[str], sessions: sessionmaker[Session], engine: Engine
) -> None:
    """At-least-once: a dispatcher that dies before recording results leaves the
    rows leased; when the lease expires they are claimed and published again."""
    with sessions() as session:
        claimed = claim_batch(session, batch_size=10, lease_seconds=30)
    assert len(claimed) == 3  # "published", then the process dies before recording

    with sessions() as session:
        assert claim_batch(session, batch_size=10, lease_seconds=30) == []  # still leased

    with engine.begin() as conn:
        conn.execute(text("UPDATE outbox_events SET locked_until = now() - interval '1 second'"))
    publisher = FakePublisher()
    assert dispatch_once(sessions, publisher, batch_size=10, lease_seconds=30) == (3, 0)
    assert {e.event_id for e in publisher.published} == {e.event_id for e in claimed}
    assert all(attempts == 2 for _, _, attempts in outbox_rows(engine))
