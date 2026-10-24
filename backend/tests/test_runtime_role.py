"""The least-privilege runtime role can do the app's work and nothing more."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from app.ops.runtime_role import provision

ROLE = "paperpilot_app_test"
PASSWORD = "role-test-only"  # noqa: S105  (throwaway test role)


@pytest.fixture
def app_engine(engine: Engine) -> Iterator[Engine]:
    provision(engine, ROLE, PASSWORD)
    url = make_url(engine.url.render_as_string(hide_password=False)).set(
        username=ROLE, password=PASSWORD
    )
    restricted = create_engine(url)
    yield restricted
    restricted.dispose()
    with engine.begin() as conn:  # roles are cluster-wide; do not leave this one behind
        conn.execute(text(f"DROP OWNED BY {ROLE}"))
        conn.execute(text(f"DROP ROLE {ROLE}"))


def test_role_reads_and_writes_application_tables(app_engine: Engine, engine: Engine) -> None:
    with app_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO processed_events (consumer_group, event_id) VALUES ('g', :id)"),
            {"id": uuid.uuid4()},
        )
        assert conn.scalar(text("SELECT count(*) FROM processed_events")) == 1
        conn.execute(text("DELETE FROM processed_events"))


@pytest.mark.parametrize(
    "statement",
    [
        "DROP TABLE processed_events",
        "ALTER TABLE processed_events ADD COLUMN x int",
        "CREATE TABLE intruder (id int)",
        "SELECT * FROM alembic_version",
        "CREATE ROLE intruder LOGIN",
        "TRUNCATE processed_events",
    ],
)
def test_role_cannot_change_schema_or_read_migration_state(
    app_engine: Engine, statement: str
) -> None:
    with pytest.raises(ProgrammingError), app_engine.begin() as conn:
        conn.execute(text(statement))


def test_provision_is_idempotent_and_rotates_the_password(
    app_engine: Engine, engine: Engine
) -> None:  # app_engine also removes the role afterwards
    provision(engine, ROLE, PASSWORD)
    provision(engine, ROLE, "another-password")
    url = make_url(engine.url.render_as_string(hide_password=False)).set(
        username=ROLE,
        password="another-password",  # noqa: S106
    )
    other = create_engine(url)
    try:
        with other.connect() as conn:
            assert conn.scalar(text("SELECT 1")) == 1
    finally:
        other.dispose()
