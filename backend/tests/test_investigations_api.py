import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

QUESTION = (
    "Do graph neural networks outperform traditional machine learning "
    "for financial fraud detection on highly imbalanced datasets?"
)


def test_create_persists_queued_investigation(client: TestClient) -> None:
    response = client.post("/api/v1/investigations", json={"question": QUESTION})

    assert response.status_code == 201
    body = response.json()
    assert body["question"] == QUESTION
    assert body["status"] == "queued"
    assert response.headers["Location"] == f"/api/v1/investigations/{body['id']}"

    fetched = client.get(response.headers["Location"])
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_create_strips_surrounding_whitespace(client: TestClient) -> None:
    response = client.post("/api/v1/investigations", json={"question": f"   {QUESTION}  "})
    assert response.status_code == 201
    assert response.json()["question"] == QUESTION


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "short"},
        {"question": "          "},
        {"question": "x" * 501},
        {"question": QUESTION, "status": "completed"},
        {},
    ],
    ids=["too-short", "blank", "too-long", "extra-field", "missing"],
)
def test_create_rejects_invalid_input(client: TestClient, payload: dict[str, object]) -> None:
    response = client.post("/api/v1/investigations", json=payload)
    assert response.status_code == 422


def test_get_unknown_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/investigations/{uuid.uuid4()}")
    assert response.status_code == 404


def test_get_malformed_id_returns_422(client: TestClient) -> None:
    response = client.get("/api/v1/investigations/not-a-uuid")
    assert response.status_code == 422


def test_list_returns_newest_first_with_pagination(client: TestClient) -> None:
    ids = [
        client.post("/api/v1/investigations", json={"question": f"{QUESTION} ({n})"}).json()["id"]
        for n in range(3)
    ]

    first_page = client.get("/api/v1/investigations", params={"limit": 2}).json()
    assert first_page["total"] == 3
    assert [item["id"] for item in first_page["items"]] == [ids[2], ids[1]]

    second_page = client.get("/api/v1/investigations", params={"limit": 2, "offset": 2}).json()
    assert [item["id"] for item in second_page["items"]] == [ids[0]]


def test_stats_counts_every_status(client: TestClient, engine: Engine) -> None:
    empty = client.get("/api/v1/investigations/stats").json()
    assert empty["total"] == 0
    assert set(empty["by_status"]) == {
        "queued",
        "running",
        "completed",
        "partially_completed",
        "failed",
        "cancelled",
    }
    assert all(count == 0 for count in empty["by_status"].values())

    client.post("/api/v1/investigations", json={"question": QUESTION})
    client.post("/api/v1/investigations", json={"question": QUESTION})
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO investigations (id, question, status) "
                "VALUES (gen_random_uuid(), :q, 'failed')"
            ),
            {"q": QUESTION},
        )

    stats = client.get("/api/v1/investigations/stats").json()
    assert stats["total"] == 3
    assert stats["by_status"]["queued"] == 2
    assert stats["by_status"]["failed"] == 1


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_list_rejects_out_of_range_pagination(client: TestClient, params: dict[str, int]) -> None:
    response = client.get("/api/v1/investigations", params=params)
    assert response.status_code == 422


def test_cors_allows_only_configured_origin(client: TestClient) -> None:
    allowed = client.get("/health/live", headers={"Origin": "http://localhost:5173"})
    denied = client.get("/health/live", headers={"Origin": "https://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers
