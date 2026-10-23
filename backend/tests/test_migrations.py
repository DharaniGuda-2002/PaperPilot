import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.db import Base
from tests.conftest import alembic_config


def test_upgrade_downgrade_upgrade_from_empty(database_url: str) -> None:
    config = alembic_config(database_url)
    engine = create_engine(database_url)
    try:
        command.downgrade(config, "base")
        assert "investigations" not in inspect(engine).get_table_names()
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        assert "investigations" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_models_match_migrations(migrated_database: str) -> None:
    """Fails when a model changes without a matching migration."""
    engine = create_engine(migrated_database)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    assert diff == []


def test_database_rejects_invalid_status(migrated_database: str) -> None:
    engine = create_engine(migrated_database)
    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO investigations (id, question, status) "
                    "VALUES (gen_random_uuid(), 'a valid question text', 'bogus')"
                )
            )
    finally:
        engine.dispose()
