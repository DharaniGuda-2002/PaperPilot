"""Report stage end to end on real Postgres: discovery -> documents -> evidence ->
report, with a generated PDF of synthetic fixture text (not a real paper)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.events.envelope import EventEnvelope
from app.retrieval.embeddings import HashingEmbedder
from app.workers.documents import handle_paper_discovered
from app.workers.evidence import handle_document_processed
from app.workers.reports import handle_evidence_extracted
from tests.test_documents_worker import discover
from tests.test_evidence_worker import FixtureFetcher


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


@pytest.fixture
def settings(migrated_database: str) -> Settings:
    return Settings(database_url=migrated_database)


def events(engine: Engine, event_type: str) -> list[EventEnvelope]:
    with engine.connect() as conn:
        rows = conn.scalars(
            text("SELECT envelope FROM outbox_events WHERE event_type = :t ORDER BY created_at"),
            {"t": event_type},
        ).all()
    return [EventEnvelope.model_validate(r) for r in rows]


def process_papers(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> list[EventEnvelope]:
    """Run documents + evidence for every discovered paper; return evidence.extracted events."""
    embedder = HashingEmbedder()
    for discovered in discover(client, engine, sessions, settings):
        handle_paper_discovered(sessions, FixtureFetcher(), embedder, discovered, settings)  # type: ignore[arg-type]
    for processed in events(engine, "document.processed"):
        handle_document_processed(sessions, embedder, processed)
    return events(engine, "evidence.extracted")


def investigation_status(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(conn.scalar(text("SELECT status FROM investigations")))


def test_report_waits_for_every_paper_then_builds_once(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    extracted = process_papers(client, engine, sessions, settings)
    assert len(extracted) == 2

    # Pretend the second paper is still being processed when the first event arrives.
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE investigation_tasks SET status = 'running' "
                "WHERE kind = 'extract_evidence' AND subject_key = :p"
            ),
            {"p": extracted[1].payload["paper_id"]},
        )
    assert handle_evidence_extracted(sessions, extracted[0]).outcome == "waiting"
    assert investigation_status(engine) == "running"

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE investigation_tasks SET status = 'succeeded' WHERE status = 'running'")
        )
    built = handle_evidence_extracted(sessions, extracted[1])
    assert (built.outcome, built.version) == ("built", 1)
    assert investigation_status(engine) == "completed"

    # Redelivery and late events never build a second version.
    assert handle_evidence_extracted(sessions, extracted[1]).outcome == "duplicate"
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM processed_events WHERE consumer_group = 'report-workers'"))
    assert handle_evidence_extracted(sessions, extracted[0]).outcome == "already_built"
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM investigation_reports")) == 1


def test_report_api_and_evidence_inspector(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    extracted = process_papers(client, engine, sessions, settings)
    handle_evidence_extracted(sessions, extracted[-1])
    investigation_id = extracted[0].investigation_id

    envelope = client.get(f"/api/v1/investigations/{investigation_id}/report").json()
    report = envelope["content"]
    assert envelope["version"] == 1
    assert report["scope"]["papers_discovered"] == 2
    assert report["scope"]["full_text"] == 2
    assert report["bottom_line"].endswith("it does not establish which method is better.")
    assert 3 <= len(report["key_findings"]) <= 5
    assert report["versions"]["extraction"].startswith("rules-")
    claim = next(f for f in report["key_findings"] if f["kind"] == "claim")
    assert claim["title"] == "Graph neural networks reported to outperform Gradient-boosted trees"
    assert claim["strength"] == "moderate"  # 2 papers with full text

    evidence_id = claim["supporting"][0]["evidence_ids"][0]
    detail = client.get(f"/api/v1/evidence/{evidence_id}").json()
    assert detail["passage_kind"] == "quotation"
    assert detail["page_number"] == 2
    assert detail["validation_status"] == "verified"
    assert len(detail["checks"]) == 4
    assert detail["document"]["content_kind"] == "full_text"
    assert detail["paper_title"]

    assert client.get(f"/api/v1/evidence/{investigation_id}").status_code == 404


def test_report_not_ready_returns_404(client: TestClient) -> None:
    created = client.post(
        "/api/v1/investigations", json={"question": "Does anything happen before reports exist?"}
    ).json()
    response = client.get(f"/api/v1/investigations/{created['id']}/report")
    assert (response.status_code, response.json()["detail"]) == (404, "Report not ready")


def test_permanent_paper_failures_mark_investigation_partially_completed(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    extracted = process_papers(client, engine, sessions, settings)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE investigation_tasks SET status = 'failed_permanent' "
                "WHERE kind = 'extract_evidence' AND subject_key = :p"
            ),
            {"p": extracted[1].payload["paper_id"]},
        )
    assert handle_evidence_extracted(sessions, extracted[0]).outcome == "built"
    assert investigation_status(engine) == "partially_completed"
