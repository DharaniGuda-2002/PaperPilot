"""Document worker: consumes paper.discovered and makes sure the paper has a
stored document (permitted full text, else abstract), then announces
document.processed for this investigation.

- Documents are per paper and shared by investigations: a paper processed for
  one investigation is reused for the next without fetching again.
- Events are keyed by paper id, so one paper's events are handled in order by
  one worker; two workers never fetch the same paper at once.
- Network work (fetch, extract, embed) runs with no transaction open.
- Temporary fetch failures retry with backoff; waiting for a host's
  politeness window is a deferral that does not use up an attempt. On the
  last attempt the worker falls back to the abstract instead of failing.

Run: python -m app.workers.documents
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import create_db_engine, create_session_factory
from app.core.logging import configure_logging
from app.documents.fetch import SafeFetcher
from app.documents.host_schedule import PostgresHostScheduler
from app.documents.models import PaperChunk, PaperDocument
from app.documents.service import (
    TemporaryFetchError,
    get_document,
    prepare_document,
    store_document,
)
from app.events.envelope import (
    DOCUMENT_PROCESSED,
    PAPER_DISCOVERED,
    DocumentProcessedV1,
    EventEnvelope,
    PaperDiscoveredV1,
    new_event,
    parse_payload,
)
from app.events.outbox import enqueue
from app.investigations.models import TaskKind, TaskStatus
from app.papers.models import Paper
from app.retrieval.embeddings import Embedder, make_embedder
from app.workers.consumer import HandlerResult, run_consumer
from app.workers.tasks import (
    already_processed,
    backoff_seconds,
    claim_task,
    ensure_task,
    finish_task,
    mark_processed,
    schedule_redelivery,
)

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "document-workers"
TOPIC = "paper-discovered"


@dataclass(frozen=True)
class DocumentResult:
    outcome: str  # processed | reused | retry_scheduled | deferred | duplicate | busy
    content_kind: str | None = None


def handle_paper_discovered(
    session_factory: sessionmaker[Session],
    fetcher: SafeFetcher,
    embedder: Embedder,
    envelope: EventEnvelope,
    settings: Settings,
) -> DocumentResult:
    payload = parse_payload(envelope, PaperDiscoveredV1)
    subject = str(payload.paper_id)

    with session_factory() as session, session.begin():
        if already_processed(session, CONSUMER_GROUP, envelope.event_id):
            return DocumentResult("duplicate")
        task_id = ensure_task(
            session, envelope.investigation_id, TaskKind.PROCESS_DOCUMENT, subject
        )
        attempt = claim_task(session, task_id)
        if attempt is None:
            return DocumentResult("busy")
        existing = get_document(session, payload.paper_id)
        paper = session.get(Paper, payload.paper_id)
        if paper is not None:
            session.expunge(paper)  # used read-only after the transaction ends

    if existing is None and paper is not None:
        try:
            prepared = prepare_document(
                paper,
                fetcher,
                embedder,
                allow_abstract_fallback_on_temporary_error=attempt
                >= settings.discovery_max_attempts,
            )
        except TemporaryFetchError as exc:
            deferral = exc.retry_after_seconds is not None
            delay = (
                (exc.retry_after_seconds or 0) + 1
                if deferral
                else backoff_seconds(attempt, settings)
            )
            with session_factory() as session, session.begin():
                mark_processed(session, CONSUMER_GROUP, envelope.event_id)
                schedule_redelivery(
                    session,
                    envelope=envelope,
                    spec=PAPER_DISCOVERED,
                    payload=payload,
                    task_id=task_id,
                    partition_key=subject,
                    delay_seconds=delay,
                    reason=str(exc),
                    counts_as_attempt=not deferral,
                )
            return DocumentResult("deferred" if deferral else "retry_scheduled")
    else:
        prepared = None

    try:
        with session_factory() as session, session.begin():
            mark_processed(session, CONSUMER_GROUP, envelope.event_id)
            document: PaperDocument | None
            if prepared is not None:
                document = store_document(session, payload.paper_id, prepared, embedder.model_id)
                outcome = "processed"
            else:
                document = get_document(session, payload.paper_id)
                outcome = "reused"
            if document is None:  # the paper row itself is gone
                finish_task(session, task_id, TaskStatus.FAILED_PERMANENT, error="paper missing")
                return DocumentResult("failed")
            content_kind = document.content_kind
            chunk_count = len(prepared.chunks) if prepared else _chunk_count(session, document.id)
            finish_task(
                session,
                task_id,
                TaskStatus.SUCCEEDED,
                summary={
                    "content_kind": document.content_kind,
                    "chunks": chunk_count,
                    "pages": document.page_count,
                    "full_text_unavailable_reason": document.full_text_unavailable_reason,
                    "reused": outcome == "reused",
                },
            )
            enqueue(
                session,
                new_event(
                    DOCUMENT_PROCESSED,
                    DocumentProcessedV1(
                        paper_id=payload.paper_id,
                        document_id=document.id,
                        content_kind=document.content_kind,
                        chunk_count=chunk_count,
                    ),
                    investigation_id=envelope.investigation_id,
                    entity_id=document.id,
                    correlation_id=envelope.correlation_id,
                    causation_id=envelope.event_id,
                ),
                partition_key=subject,
            )
    except IntegrityError:
        # A concurrent delivery stored the document or processed the event first.
        return DocumentResult("duplicate")
    return DocumentResult(outcome, content_kind)


def _chunk_count(session: Session, document_id: uuid.UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(PaperChunk)
            .where(PaperChunk.document_id == document_id)
        )
        or 0
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    session_factory = create_session_factory(create_db_engine(settings))
    fetcher = SafeFetcher(PostgresHostScheduler(session_factory))
    embedder = make_embedder(settings.embedding_provider)
    logger.info("embedder ready", extra={"model": embedder.model_id})

    def handle(envelope: EventEnvelope) -> HandlerResult:
        result = handle_paper_discovered(session_factory, fetcher, embedder, envelope, settings)
        return HandlerResult(summary=f"{result.outcome} ({result.content_kind or '-'})")

    run_consumer(settings, group_id=CONSUMER_GROUP, topic=TOPIC, handler=handle)
    fetcher.close()


if __name__ == "__main__":
    main()
