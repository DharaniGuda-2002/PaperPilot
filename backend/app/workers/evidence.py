"""Evidence worker: consumes document.processed, retrieves the passages of the
paper most relevant to the question and to each evidence field, extracts
structured facts with exact quotations, validates them, and stores the
records and their validation history in one transaction.

Run: python -m app.workers.evidence
"""

import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.core.logging import configure_logging
from app.documents.models import PaperDocument
from app.events.envelope import (
    EVIDENCE_EXTRACTED,
    DocumentProcessedV1,
    EventEnvelope,
    EvidenceExtractedV1,
    new_event,
    parse_payload,
)
from app.events.outbox import enqueue
from app.evidence.models import ValidationStatus
from app.evidence.service import build_evidence, embed_queries, gather_sources, save_evidence
from app.investigations.models import Investigation, TaskKind, TaskStatus
from app.retrieval.embeddings import Embedder, make_embedder
from app.workers.consumer import HandlerResult, run_consumer
from app.workers.tasks import (
    already_processed,
    claim_task,
    ensure_task,
    finish_task,
    mark_processed,
)

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "evidence-workers"
TOPIC = "document-processed"


@dataclass(frozen=True)
class EvidenceResult:
    outcome: str  # extracted | duplicate | busy | missing
    records: int = 0
    verified: int = 0


def handle_document_processed(
    session_factory: sessionmaker[Session], embedder: Embedder, envelope: EventEnvelope
) -> EvidenceResult:
    payload = parse_payload(envelope, DocumentProcessedV1)
    subject = str(payload.paper_id)

    with session_factory() as session, session.begin():
        if already_processed(session, CONSUMER_GROUP, envelope.event_id):
            return EvidenceResult("duplicate")
        task_id = ensure_task(
            session, envelope.investigation_id, TaskKind.EXTRACT_EVIDENCE, subject
        )
        if task_id is None:  # investigation deleted after the event was published
            mark_processed(session, CONSUMER_GROUP, envelope.event_id)
            return EvidenceResult("investigation_missing")
        if claim_task(session, task_id) is None:
            return EvidenceResult("busy")
        investigation = session.get(Investigation, envelope.investigation_id)
        document = session.get(PaperDocument, payload.document_id)
        if investigation is None or document is None:
            mark_processed(session, CONSUMER_GROUP, envelope.event_id)
            finish_task(
                session,
                task_id,
                TaskStatus.FAILED_PERMANENT,
                error="investigation or document missing",
            )
            return EvidenceResult("missing")
        question, content_kind, page_count = (
            investigation.question,
            document.content_kind,
            document.page_count,
        )

    queries, embeddings = embed_queries(embedder, question)  # CPU work, no transaction open
    with session_factory() as session:
        sources = gather_sources(
            session,
            paper_id=payload.paper_id,
            queries=queries,
            query_embeddings=embeddings,
            model_id=embedder.model_id,
        )
    batch = build_evidence(
        investigation_id=envelope.investigation_id,
        paper_id=payload.paper_id,
        content_kind=content_kind,
        page_count=page_count,
        sources=sources,
    )
    summary = batch.summary()
    # Read counts now: the records are attached to (and expired by) the transaction below.
    reported = len(batch.reported)
    verified = batch.count(ValidationStatus.VERIFIED)
    rejected = batch.count(ValidationStatus.REJECTED)

    try:
        with session_factory() as session, session.begin():
            mark_processed(session, CONSUMER_GROUP, envelope.event_id)
            save_evidence(session, envelope.investigation_id, payload.paper_id, batch)
            finish_task(
                session,
                task_id,
                TaskStatus.SUCCEEDED,
                summary={
                    **summary,
                    "content_kind": content_kind,
                    "passages_searched": len(sources),
                },
            )
            enqueue(
                session,
                new_event(
                    EVIDENCE_EXTRACTED,
                    EvidenceExtractedV1(
                        paper_id=payload.paper_id,
                        records=reported,
                        verified=verified,
                        rejected=rejected,
                    ),
                    investigation_id=envelope.investigation_id,
                    entity_id=payload.paper_id,
                    correlation_id=envelope.correlation_id,
                    causation_id=envelope.event_id,
                ),
                # Keyed by investigation so the report stage (M6) sees one investigation in order.
                partition_key=str(envelope.investigation_id),
            )
    except IntegrityError:
        return EvidenceResult("duplicate")
    return EvidenceResult(
        "extracted",
        records=reported,
        verified=verified,
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    session_factory = create_session_factory(create_db_engine(settings))
    embedder = make_embedder(settings.embedding_provider)
    logger.info("embedder ready", extra={"model": embedder.model_id})

    def handle(envelope: EventEnvelope) -> HandlerResult:
        result = handle_document_processed(session_factory, embedder, envelope)
        return HandlerResult(
            summary=f"{result.outcome} ({result.verified}/{result.records} verified)"
        )

    run_consumer(settings, group_id=CONSUMER_GROUP, topic=TOPIC, handler=handle)


if __name__ == "__main__":
    main()
