"""Export a finished investigation and import it into an empty database.

The data is the synthetic fixture pipeline used by the other worker tests,
not a real paper."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.ops.example_data import export_investigation, import_investigation
from app.workers.reports import handle_evidence_extracted
from tests.conftest import reset_tables
from tests.test_report_worker import process_papers


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


@pytest.fixture
def settings(migrated_database: str) -> Settings:
    return Settings(database_url=migrated_database)


def finish_investigation(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> uuid.UUID:
    for event in process_papers(client, engine, sessions, settings):
        handle_evidence_extracted(sessions, event)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT status FROM investigations")) == "completed"
        return uuid.UUID(str(conn.scalar(text("SELECT id FROM investigations"))))


def test_export_then_import_reproduces_a_viewable_report(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    investigation_id = finish_investigation(client, engine, sessions, settings)
    before = client.get(f"/api/v1/investigations/{investigation_id}/report").json()
    evidence_before = client.get(f"/api/v1/investigations/{investigation_id}/evidence").json()
    with sessions() as session:
        data = json.loads(json.dumps(export_investigation(session, investigation_id)))
    assert data["tables"]["investigations"][0]["is_example"] is True
    assert all(row["chunk_id"] is None for row in data["tables"]["evidence_records"])

    reset_tables(engine)
    assert client.get(f"/api/v1/investigations/{investigation_id}/report").status_code == 404
    with sessions() as session:
        assert import_investigation(session, data) == investigation_id

    assert client.get(f"/api/v1/investigations/{investigation_id}/report").json() == before
    evidence_after = client.get(f"/api/v1/investigations/{investigation_id}/evidence").json()
    assert [(e["id"], e["passage"], e["checks"]) for e in evidence_after] == [
        (e["id"], e["passage"], e["checks"]) for e in evidence_before
    ]
    detail = client.get(f"/api/v1/evidence/{evidence_after[0]['id']}")
    assert detail.status_code == 200
    examples = client.get("/api/v1/investigations/examples").json()
    assert [e["id"] for e in examples] == [str(investigation_id)]
    assert examples[0]["is_example"] is True
    papers = client.get(f"/api/v1/investigations/{investigation_id}/papers").json()
    assert papers["total"] == len(data["tables"]["investigation_papers"])


def test_import_twice_replaces_instead_of_duplicating(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    investigation_id = finish_investigation(client, engine, sessions, settings)
    with sessions() as session:
        data = json.loads(json.dumps(export_investigation(session, investigation_id)))
    with sessions() as session:
        import_investigation(session, data)
    with sessions() as session:
        import_investigation(session, data)
    tables = data["tables"]
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM investigations")) == 1
        assert conn.scalar(text("SELECT count(*) FROM investigation_reports")) == 1
        assert conn.scalar(text("SELECT count(*) FROM papers")) == len(tables["papers"])
        assert conn.scalar(text("SELECT count(*) FROM evidence_records")) == len(
            tables["evidence_records"]
        )


def test_import_reuses_a_paper_the_target_already_has(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    investigation_id = finish_investigation(client, engine, sessions, settings)
    with sessions() as session:
        data = json.loads(json.dumps(export_investigation(session, investigation_id)))
    reset_tables(engine)
    first = data["tables"]["papers"][0]
    with engine.begin() as conn:  # same paper, different id, already in the target
        conn.execute(
            text(
                "INSERT INTO papers (id, provider, provider_id, title, authors, is_open_access, "
                "metadata_fetched_at) VALUES (:id, :provider, :pid, 'existing', '[]', false, now())"
            ),
            {"id": uuid.uuid4(), "provider": first["provider"], "pid": first["provider_id"]},
        )
    with sessions() as session:
        import_investigation(session, data)
    with engine.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT count(*) FROM papers WHERE provider_id = :p"),
                {"p": first["provider_id"]},
            )
            == 1
        )
        assert (
            conn.scalar(
                text("SELECT title FROM papers WHERE provider_id = :p"), {"p": first["provider_id"]}
            )
            == "existing"
        )


def test_only_finished_investigations_can_be_exported(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    created = client.post(
        "/api/v1/investigations",
        json={"question": "Do graph neural networks beat gradient boosting for fraud detection?"},
    ).json()
    with sessions() as session, pytest.raises(ValueError):
        export_investigation(session, uuid.UUID(created["id"]))
