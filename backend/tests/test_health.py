from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_live_returns_ok(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_ok_when_database_reachable(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"


def test_ready_503_when_database_unreachable() -> None:
    # Port 1 refuses connections immediately; no real database involved.
    settings = Settings(
        database_url="postgresql+psycopg://nobody:nothing@127.0.0.1:1/none",
        db_connect_timeout_seconds=1,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "error"}}


def test_correlation_id_echoed_when_valid_uuid(client: TestClient) -> None:
    request_id = "6f1c2c1e-3a4b-4c5d-9e8f-0a1b2c3d4e5f"
    response = client.get("/health/live", headers={"X-Request-ID": request_id})
    assert response.headers["X-Request-ID"] == request_id


def test_correlation_id_replaced_when_not_uuid(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "<script>"})
    assert response.headers["X-Request-ID"] != "<script>"
