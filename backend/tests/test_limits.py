from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.core.rate_limit import SlidingWindowLimiter
from app.main import create_app
from tests.conftest import reset_tables

QUESTION = "Does contrastive pretraining improve citation recommendation over BM25?"


@pytest.fixture
def limited_client(migrated_database: str, engine: Engine) -> Iterator[TestClient]:
    settings = Settings(
        database_url=migrated_database, create_rate_limit_per_minute=2, daily_investigation_cap=3
    )
    with TestClient(create_app(settings)) as client:
        yield client
    reset_tables(engine)


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


def test_rejects_oversized_chunked_body_without_content_length(client: TestClient) -> None:
    """Regression: the size check trusted Content-Length, so a chunked upload was
    read into memory whole before validation."""

    def chunks() -> Iterator[bytes]:
        for _ in range(20):
            yield b"x" * 1_000

    response = client.post(
        "/api/v1/investigations", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_api_responses_carry_security_headers(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_api_docs_page_still_loads_its_assets(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers  # Swagger UI loads from a CDN


@pytest.fixture
def proxied_client(migrated_database: str, engine: Engine) -> Iterator[TestClient]:
    settings = Settings(
        database_url=migrated_database, create_rate_limit_per_minute=2, trusted_proxy_hops=1
    )
    with TestClient(create_app(settings)) as client:
        yield client
    reset_tables(engine)


def test_forged_forwarded_for_does_not_reset_the_limit(proxied_client: TestClient) -> None:
    """Regression: uvicorn trusted the leftmost (client-supplied) X-Forwarded-For
    entry, so rotating it gave every request a fresh limit."""
    codes = [
        proxied_client.post(
            "/api/v1/investigations",
            json={"question": QUESTION},
            headers={"X-Forwarded-For": f"10.0.0.{n}, 203.0.113.7"},  # forged, then proxy-added
        ).status_code
        for n in range(3)
    ]
    assert codes == [201, 201, 429]


def test_clients_behind_the_proxy_have_separate_limits(proxied_client: TestClient) -> None:
    for address in ("203.0.113.7", "203.0.113.7", "198.51.100.9"):
        response = proxied_client.post(
            "/api/v1/investigations",
            json={"question": QUESTION},
            headers={"X-Forwarded-For": address},
        )
        assert response.status_code == 201


def test_unhandled_errors_return_a_generic_body(migrated_database: str) -> None:
    app = create_app(Settings(database_url=migrated_database))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail: postgresql://user:pass@host/db")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert "secret" not in response.text and "postgresql" not in response.text


def test_edge_client_header_takes_precedence(migrated_database: str, engine: Engine) -> None:
    settings = Settings(
        database_url=migrated_database,
        create_rate_limit_per_minute=2,
        trusted_proxy_hops=1,
        client_ip_header="CF-Connecting-IP",
    )
    with TestClient(create_app(settings)) as client:
        codes = [
            client.post(
                "/api/v1/investigations",
                json={"question": QUESTION},
                # The last X-Forwarded-For entry varies per request (Render's proxies).
                headers={"CF-Connecting-IP": "203.0.113.7", "X-Forwarded-For": f"10.1.1.{n}"},
            ).status_code
            for n in range(3)
        ]
    reset_tables(engine)
    assert codes == [201, 201, 429]
