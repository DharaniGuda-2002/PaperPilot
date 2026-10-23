from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.core.rate_limit import SlidingWindowLimiter
from app.main import create_app

QUESTION = "Does contrastive pretraining improve citation recommendation over BM25?"


@pytest.fixture
def limited_client(migrated_database: str, engine: Engine) -> Iterator[TestClient]:
    settings = Settings(
        database_url=migrated_database, create_rate_limit_per_minute=2, daily_investigation_cap=3
    )
    with TestClient(create_app(settings)) as client:
        yield client
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE investigations"))


def test_limiter_allows_up_to_limit_then_recovers_after_window() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    assert limiter.allow("a", now=0)
    assert limiter.allow("a", now=1)
    assert not limiter.allow("a", now=2)
    assert limiter.allow("b", now=2)  # keys are independent
    assert limiter.allow("a", now=61)


def test_create_returns_429_after_per_client_limit(limited_client: TestClient) -> None:
    codes = [
        limited_client.post("/api/v1/investigations", json={"question": QUESTION}).status_code
        for _ in range(3)
    ]
    assert codes == [201, 201, 429]


def test_reads_are_not_rate_limited(limited_client: TestClient) -> None:
    for _ in range(5):
        assert limited_client.get("/api/v1/investigations").status_code == 200


def test_create_returns_429_at_daily_cap(limited_client: TestClient, engine: Engine) -> None:
    with engine.begin() as conn:
        for n in range(3):
            conn.execute(
                text(
                    "INSERT INTO investigations (id, question, status) "
                    "VALUES (gen_random_uuid(), :q, 'queued')"
                ),
                {"q": f"{QUESTION} ({n})"},
            )
    response = limited_client.post("/api/v1/investigations", json={"question": QUESTION})
    assert response.status_code == 429
    assert "daily" in response.json()["detail"]


def test_rejects_oversized_body(client: TestClient) -> None:
    response = client.post(
        "/api/v1/investigations",
        content=b"x" * 20_000,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize(
    "url",
    ["postgres://u:p@host/db?sslmode=require", "postgresql://u:p@host/db?sslmode=require"],
)
def test_database_url_gets_psycopg_driver(url: str) -> None:
    settings = Settings(database_url=url)
    assert settings.database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"
