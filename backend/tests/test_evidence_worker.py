"""Discovery -> document -> evidence through real Postgres + pgvector, with a fake
fetcher serving a generated PDF of synthetic fixture text (not a real paper)."""

import uuid
from collections.abc import Sequence
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Row, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.documents.fetch import FetchedPdf
from app.events.envelope import EventEnvelope
from app.evidence.rules import EXTRACTION_VERSION
from app.retrieval.embeddings import HashingEmbedder
from app.workers.documents import handle_paper_discovered
from app.workers.evidence import handle_document_processed
from tests.test_documents_worker import discover

FIXTURE_PAGES = [
    "Introduction. We propose a GNN for fraud detection on imbalanced graphs.",
    "Experiments. We evaluate on the YelpChi dataset using 5-fold cross-validation. "
    "Our GNN outperforms XGBoost and logistic regression.",
    "Results. The GNN reaches an AUC of 0.921, while XGBoost reaches an AUC of 0.883. "
    "A limitation is that we test only one dataset.",
]


class FixtureFetcher:
    def fetch_pdf(self, url: str) -> FetchedPdf:
        document = pymupdf.open()
        for body in FIXTURE_PAGES:
            page = document.new_page()
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), body, fontsize=10)
        content: bytes = document.tobytes()
        return FetchedPdf(content, url, url, "0" * 64)


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


@pytest.fixture
def settings(migrated_database: str) -> Settings:
    return Settings(database_url=migrated_database)


def processed_event(engine: Engine, paper_id: str) -> EventEnvelope:
    with engine.connect() as conn:
        raw = conn.scalar(
            text(
                "SELECT envelope FROM outbox_events WHERE event_type = 'document.processed' "
                "AND envelope->'payload'->>'paper_id' = :paper ORDER BY created_at DESC LIMIT 1"
            ),
            {"paper": paper_id},
        )
    return EventEnvelope.model_validate(raw)


def run_pipeline(
    client: TestClient,
    engine: Engine,
    sessions: sessionmaker[Session],
    settings: Settings,
    *,
    open_access: bool = True,
) -> EventEnvelope:
    discovered = discover(client, engine, sessions, settings)[0]
    if not open_access:
        with engine.begin() as conn:
            conn.execute(text("UPDATE papers SET is_open_access = false"))
    embedder = HashingEmbedder()
    handle_paper_discovered(sessions, FixtureFetcher(), embedder, discovered, settings)  # type: ignore[arg-type]
    event = processed_event(engine, discovered.payload["paper_id"])
    result = handle_document_processed(sessions, embedder, event)
    assert result.outcome == "extracted"
    return event


def evidence(engine: Engine) -> Sequence[Row[Any]]:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT field, finding_status, value, passage, page_number, retrieval_method, "
                "validation_status, extraction_version FROM evidence_records ORDER BY field"
            )
        ).all()


def test_extracts_validated_evidence_with_pages_and_provenance(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    run_pipeline(client, engine, sessions, settings)
    rows = evidence(engine)
    reported = [r for r in rows if r.finding_status == "reported"]

    metrics = {
        (r.value["method_hint"], r.value["value"]) for r in reported if r.field == "metric_result"
    }
    assert metrics == {("GNN", 0.921), ("XGBoost", 0.883)}
    gnn_auc = next(r for r in reported if r.field == "metric_result" and r.value["value"] == 0.921)
    assert gnn_auc.page_number == 3
    assert (
        gnn_auc.passage == "The GNN reaches an AUC of 0.921, while XGBoost reaches an AUC of 0.883."
    )
    assert gnn_auc.retrieval_method in {"fts", "vector", "fts+vector"}
    assert gnn_auc.extraction_version == EXTRACTION_VERSION

    fields = {r.field for r in reported}
    assert {"method", "dataset", "split", "baseline", "metric_result", "limitation"} <= fields
    assert {r.value["name"] for r in reported if r.field == "baseline"} == {
        "XGBoost",
        "Logistic regression",
    }
    assert all(r.validation_status == "verified" for r in reported)

    # Nothing about code availability in the fixture: recorded as not found, not as "no code".
    code = [r for r in rows if r.field == "code_availability"]
    assert [(r.finding_status, r.passage) for r in code] == [("not_found", None)]

    with engine.connect() as conn:
        checks = conn.execute(
            text("SELECT rule, outcome FROM evidence_validations WHERE outcome = 'fail'")
        ).all()
        task = conn.execute(
            text(
                "SELECT status, result_summary FROM investigation_tasks "
                "WHERE kind = 'extract_evidence' AND status = 'succeeded'"
            )
        ).one()
        extracted = conn.execute(
            text(
                "SELECT partition_key, envelope FROM outbox_events "
                "WHERE event_type = 'evidence.extracted'"
            )
        ).one()
    assert checks == []
    assert task.result_summary["verified"] == len(reported)
    assert task.result_summary["fields_without_evidence"] == ["code_availability"]
    assert extracted.partition_key == extracted.envelope["investigation_id"]


def test_abstract_only_paper_marks_missing_fields_unavailable(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    run_pipeline(client, engine, sessions, settings, open_access=False)
    rows = evidence(engine)
    absent = {r.finding_status for r in rows if r.finding_status != "reported"}
    assert absent == {"unavailable"}  # no full text to search, so never "not_found"
    assert all(r.page_number is None for r in rows)  # abstracts have no pages


def test_duplicate_delivery_does_not_duplicate_evidence(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    event = run_pipeline(client, engine, sessions, settings)
    before = len(evidence(engine))
    assert handle_document_processed(sessions, HashingEmbedder(), event).outcome == "duplicate"
    assert len(evidence(engine)) == before


def test_api_returns_evidence_with_checks_and_document_info(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    event = run_pipeline(client, engine, sessions, settings)
    items = client.get(f"/api/v1/investigations/{event.investigation_id}/evidence").json()
    metric = next(
        i for i in items if i["field"] == "metric_result" and i["value"]["value"] == 0.921
    )
    assert metric["paper_title"].startswith("Alleviating")
    assert metric["page_number"] == 3
    assert metric["passage_kind"] == "quotation"
    assert {c["rule"] for c in metric["checks"]} == {
        "passage_in_source",
        "page_reference",
        "numbers_in_passage",
        "value_range",
    }
    assert all(c["outcome"] == "pass" for c in metric["checks"])
    only_code = client.get(
        f"/api/v1/investigations/{event.investigation_id}/evidence",
        params={"field": "code_availability"},
    ).json()
    assert [(i["finding_status"], i["checks"]) for i in only_code] == [("not_found", [])]

    document = client.get(f"/api/v1/papers/{event.payload['paper_id']}/document").json()
    assert document["content_kind"] == "full_text"
    assert document["page_count"] == 3
    assert document["chunk_count"] == 3
    assert document["embedding_models"] == ["hashing-bow-v1"]
    missing = client.get(f"/api/v1/investigations/{uuid.uuid4()}/evidence")
    assert missing.status_code == 404


def test_evidence_list_pages_and_reports_the_total(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> None:
    event = run_pipeline(client, engine, sessions, settings)
    url = f"/api/v1/investigations/{event.investigation_id}/evidence"
    everything = client.get(url)
    total = int(everything.headers["X-Total-Count"])
    assert total == len(everything.json()) > 2
    first = client.get(url, params={"limit": 2})
    second = client.get(url, params={"limit": 2, "offset": 2})
    assert first.headers["X-Total-Count"] == second.headers["X-Total-Count"] == str(total)
    ids = [i["id"] for i in everything.json()]
    assert [i["id"] for i in first.json()] == ids[:2]
    assert [i["id"] for i in second.json()] == ids[2:4]
    filtered = client.get(url, params={"field": "code_availability"})
    assert filtered.headers["X-Total-Count"] == str(len(filtered.json()))


def test_unknown_unit_is_recorded_as_uncertain_not_rejected() -> None:
    from app.evidence.rules import SourceChunk
    from app.evidence.service import build_evidence

    chunk = SourceChunk(
        uuid.uuid4(), 2, "The baseline reaches an F1 score of 10.92 here.", "fts", 0.1
    )
    batch = build_evidence(
        investigation_id=uuid.uuid4(),
        paper_id=uuid.uuid4(),
        content_kind="full_text",
        page_count=5,
        sources=[chunk],
    )
    metric = next(r for r in batch.records if r.field == "metric_result")
    assert (metric.finding_status, metric.validation_status) == ("uncertain", "verified")
    assert batch.summary()["uncertain"] == 1
