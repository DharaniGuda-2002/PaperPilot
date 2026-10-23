"""Test fixtures. API and migration tests run against a real Postgres database
named by TEST_DATABASE_URL; schema is built with Alembic, never create_all()."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://paperpilot:paperpilot-local-only@localhost:5433/paperpilot_test"
)


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    _ensure_database_exists(url)
    return url


def _ensure_database_exists(url: str) -> None:
    parsed = make_url(url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    admin.dispose()


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return database_url


@pytest.fixture(scope="session")
def engine(migrated_database: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database)
    yield engine
    engine.dispose()


@pytest.fixture
def client(migrated_database: str, engine: Engine) -> Iterator[TestClient]:
    settings = Settings(database_url=migrated_database, cors_origins="http://localhost:5173")
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE investigations"))
