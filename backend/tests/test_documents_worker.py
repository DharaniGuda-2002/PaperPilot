"""Document worker against real Postgres. Fetching is faked; PDFs are generated
in-test with synthetic text; papers come from the recorded OpenAlex sample."""

from collections.abc import Iterator

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.documents.fetch import (
    FetchDeferredError,
    FetchedPdf,
    FetchFailedError,
    FetchRejectedError,
)
from app.events.envelope import EventEnvelope
from app.retrieval.embeddings import HashingEmbedder
from app.workers.discovery import handle_investigation_requested
from app.workers.documents import handle_paper_discovered
from tests.fakes import FakeProvider

QUESTION = "Do graph neural networks beat gradient boosting for fraud detection?"


def synthetic_pdf() -> bytes:
    document = pymupdf.open()
    for body in (
        "Fixture introduction about fraud detection.",
        "Fixture results: the model reaches an AUC of 0.92 on the fixture dataset.",
    ):
        page = document.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), body, fontsize=10)
    data: bytes = document.tobytes()
    return data


class FakeFetcher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.urls: list[str] = []

    def fetch_pdf(self, url: str) -> FetchedPdf:
        self.urls.append(url)
        if self.error:
            raise self.error
        content = synthetic_pdf()
        return FetchedPdf(content, url, url, "0" * 64)


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


@pytest.fixture
def settings(migrated_database: str) -> Settings:
    return Settings(database_url=migrated_database, discovery_max_attempts=3)


def discover(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> list[EventEnvelope]:
    client.post("/api/v1/investigations", json={"question": QUESTION})
    with engine.connect() as conn:
        requested = EventEnvelope.model_validate(
            conn.scalar(
                text(
                    "SELECT envelope FROM outbox_events "
                    "WHERE event_type = 'investigation.requested' ORDER BY created_at DESC LIMIT 1"
                )
            )
        )
    handle_investigation_requested(sessions, FakeProvider(), requested, settings)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT envelope FROM outbox_events WHERE event_type = 'paper.discovered' "
                "AND envelope->>'investigation_id' = :inv ORDER BY envelope->'payload'->>'rank'"
            ),
            {"inv": str(requested.investigation_id)},
        ).all()
    return [EventEnvelope.model_validate(r.envelope) for r in rows]


@pytest.fixture
def discovered(
    client: TestClient, engine: Engine, sessions: sessionmaker[Session], settings: Settings
) -> Iterator[list[EventEnvelope]]:
    yield discover(client, engine, sessions, settings)


def run(
    sessions: sessionmaker[Session], fetcher: FakeFetcher, event: EventEnvelope, settings: Settings
) -> str:
    return handle_paper_discovered(sessions, fetcher, HashingEmbedder(), event, settings).outcome  # type: ignore[arg-type]


def task(
    engine: Engine, event: EventEnvelope
) -> tuple[str, int, str | None, dict[str, object] | None]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status, attempts, last_error, result_summary FROM investigation_tasks "
                "WHERE kind = 'process_document' AND subject_key = :paper "
                "AND investigation_id = :inv"
            ),
            {"paper": event.payload["paper_id"], "inv": str(event.investigation_id)},
        ).one()
    return row.status, row.attempts, row.last_error, row.result_summary


def test_stores_full_text_with_page_numbers_and_embeddings(
    discovered: list[EventEnvelope],
    sessions: sessionmaker[Session],
    settings: Settings,
    engine: Engine,
) -> None:
    event = discovered[0]
    fetcher = FakeFetcher()
    assert run(sessions, fetcher, event, settings) == "processed"
    assert fetcher.urls == ["https://arxiv.org/pdf/2005.00625"]

    with engine.connect() as conn:
        document = conn.execute(text("SELECT * FROM paper_documents")).one()
        chunks = conn.execute(
            text(
                "SELECT page_number, text, embedding IS NOT NULL AS embedded, embedding_model "
                "FROM paper_chunks ORDER BY ordinal"
            )
        ).all()
        processed = conn.execute(
            text(
                "SELECT partition_key, envelope FROM outbox_events "
                "WHERE event_type = 'document.processed'"
            )
        ).one()
    assert document.content_kind == "full_text"
    assert document.page_count == 2
    assert document.extractor == "pymupdf"
    assert [c.page_number for c in chunks] == [1, 2]
    assert "AUC of 0.92" in chunks[1].text
    assert all(c.embedded and c.embedding_model == "hashing-bow-v1" for c in chunks)
    assert processed.partition_key == event.payload["paper_id"]
    assert processed.envelope["causation_id"] == str(event.event_id)
    status, attempts, _, summary = task(engine, event)
    assert (status, attempts) == ("succeeded", 1)
    assert summary == {
        "content_kind": "full_text",
        "chunks": 2,
        "pages": 2,
        "full_text_unavailable_reason": None,
        "reused": False,
    }


def test_document_is_reused_by_another_investigation(
    client: TestClient,
    discovered: list[EventEnvelope],
    sessions: sessionmaker[Session],
    settings: Settings,
    engine: Engine,
) -> None:
    fetcher = FakeFetcher()
    run(sessions, fetcher, discovered[0], settings)
    second = discover(client, engine, sessions, settings)
    assert run(sessions, fetcher, second[0], settings) == "reused"
    assert len(fetcher.urls) == 1  # not fetched again
    assert task(engine, second[0])[3]["reused"] is True  # type: ignore[index]


def test_duplicate_delivery_is_ignored(
    discovered: list[EventEnvelope],
    sessions: sessionmaker[Session],
    settings: Settings,
    engine: Engine,
) -> None:
    fetcher = FakeFetcher()
    run(sessions, fetcher, discovered[0], settings)
    assert run(sessions, fetcher, discovered[0], settings) == "duplicate"
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM paper_documents")) == 1


def test_temporary_failure_schedules_retry_and_counts_attempt(
    discovered: list[EventEnvelope],
    sessions: sessionmaker[Session],
    settings: Settings,
    engine: Engine,
) -> None:
    event = discovered[0]
    assert (
        run(sessions, FakeFetcher(FetchFailedError("HTTP 503")), event, settings)
        == "retry_scheduled"
    )
    status, attempts, error, _ = task(engine, event)
    assert (status, attempts, error) == ("failed_retryable", 1, "HTTP 503")
    with engine.connect() as conn:
        delayed = conn.scalar(
            text(
                "SELECT available_at > now() FROM outbox_events "
                "WHERE event_type = 'paper.discovered' AND envelope->>'causation_id' = :id"
            ),
            {"id": str(event.event_id)},
        )
    assert delayed


def test_politeness_deferral_does_not_use_an_attempt(
    discovered: list[EventEnvelope],
    sessions: sessionmaker[Session],
    settings: Settings,
    engine: Engine,
) -> None:
    event = discovered[0]
    fetcher = FakeFetcher(FetchDeferredError("arxiv.org", 120))
    assert run(sessions, fetcher, event, settings) == "deferred"
    status, attempts, _, _ = task(engine, event)
    assert (status, attempts) == ("pending", 0)
    with engine.connect() as conn:
        wait = conn.scalar(
            text(
                "SELECT extract(epoch FROM available_at - created_at) FROM outbox_events "
                "WHERE envelope->>'causation_id' = :id"
            ),
            {"id": str(event.event_id)},
        )
    assert 120 <= float(wait) <= 122


def test_last_attempt_falls_back_to_abstract(
    discovered: list[EventEnvelope],
    sessions: sessionmaker[Session],
    settings: Settings,
    engine: Engine,
) -> None:
    event = discovered[0]
    with engine.begin() as conn:  # two attempts already used
        conn.execute(
            text("UPDATE investigation_tasks SET attempts = 2 WHERE kind = 'process_document'")
        )
    assert run(sessions, FakeFetcher(FetchFailedError("HTTP 503")), event, settings) == "processed"
    with engine.connect() as conn:
        document = conn.execute(
            text(
                "SELECT content_kind, full_text_unavailable_reason, page_count FROM paper_documents"
            )
        ).one()
        pages = conn.execute(text("SELECT DISTINCT page_number FROM paper_chunks")).scalars().all()
    assert document.content_kind == "abstract"
    assert document.full_text_unavailable_reason == "fetch failed: HTTP 503"
    assert document.page_count is None
    assert pages == [None]  # abstracts have no page numbers to cite


def test_unusable_full_text_falls_back_immediately(
    discovered: list[EventEnvelope],
    sessions: sessionmaker[Session],
    settings: Settings,
    engine: Engine,
) -> None:
    fetcher = FakeFetcher(FetchRejectedError("disallowed by arxiv.org/robots.txt"))
    assert run(sessions, fetcher, discovered[0], settings) == "processed"
    with engine.connect() as conn:
        reason = conn.scalar(text("SELECT full_text_unavailable_reason FROM paper_documents"))
    assert reason == "full text not usable: disallowed by arxiv.org/robots.txt"


def test_closed_access_paper_is_never_fetched(
    discovered: list[EventEnvelope],
    sessions: sessionmaker[Session],
    settings: Settings,
    engine: Engine,
) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE papers SET is_open_access = false"))
    fetcher = FakeFetcher()
    run(sessions, fetcher, discovered[0], settings)
    assert fetcher.urls == []
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT content_kind, full_text_unavailable_reason FROM paper_documents")
        ).one()
    assert (row.content_kind, row.full_text_unavailable_reason) == ("abstract", "not open access")
