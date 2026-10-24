"""Pruning of processed_events."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.ops.maintenance import prune_processed_events


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


def seed(engine: Engine) -> None:
    with engine.begin() as conn:
        for days in (1, 7, 9, 30):
            conn.execute(
                text(
                    "INSERT INTO processed_events (consumer_group, event_id, processed_at) "
                    "VALUES ('g', :id, now() - make_interval(days => :days))"
                ),
                {"id": uuid.uuid4(), "days": days},
            )


def test_prune_deletes_only_rows_older_than_the_cutoff(
    client: object, engine: Engine, sessions: sessionmaker[Session]
) -> None:
    seed(engine)
    with sessions() as session:
        assert prune_processed_events(session, dry_run=True) == 2
        assert prune_processed_events(session) == 2
    with engine.connect() as conn:
        remaining = conn.scalar(text("SELECT count(*) FROM processed_events"))
    assert remaining == 2


def test_prune_refuses_a_cutoff_inside_topic_retention(
    client: object, sessions: sessionmaker[Session]
) -> None:
    with sessions() as session, pytest.raises(ValueError):
        prune_processed_events(session, older_than_days=7)
