"""Discovery worker: consumes investigation.requested, finds papers, and links
them to the investigation.

Idempotency: the task is claimed with a conditional UPDATE, and results are
committed together with a processed_events row. A redelivered event finds
that row and is skipped, so duplicates never add links or events twice.

Retries: a temporary provider failure marks the task failed_retryable and
schedules redelivery by writing a new investigation.requested event to the
outbox with a delay (exponential backoff with jitter). The current message is
finished and committed, so a failing investigation never blocks its
partition. After the last attempt the task fails permanently and the
message goes to the dead-letter topic for inspection and replay.

Run: python -m app.workers.discovery
"""

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from sqlalchemy import exists, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import create_db_engine, create_session_factory
from app.core.logging import configure_logging
from app.events.envelope import (
    INVESTIGATION_REQUESTED,
    PAPER_DISCOVERED,
    EventEnvelope,
    InvestigationRequestedV1,
    PaperDiscoveredV1,
    new_event,
    parse_payload,
)
from app.events.models import ProcessedEvent
from app.events.outbox import enqueue
from app.investigations.models import (
    Investigation,
    InvestigationPaper,
    InvestigationStatus,
    InvestigationTask,
    TaskStatus,
)
from app.papers import service as papers_service
from app.papers.openalex import ProviderUnavailableError
from app.papers.providers import make_provider
from app.papers.schemas import FullTextAvailability, PaperRead, PaperSearchParams
from app.papers.service import PaperProvider
from app.workers.consumer import HandlerResult, run_consumer

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "discovery-workers"
TOPIC = "investigation-requests"
RETRIEVAL_METHOD = "openalex_search"
# A task stuck in "running" this long belongs to a crashed worker and may be reclaimed.
STALE_RUNNING_AFTER = timedelta(minutes=10)


class Outcome(StrEnum):
    LINKED = "linked"
    NO_PAPERS = "no_papers"
    RETRY_SCHEDULED = "retry_scheduled"
    RETRIES_EXHAUSTED = "retries_exhausted"
    DUPLICATE = "duplicate"
    BUSY_ELSEWHERE = "busy_elsewhere"
    TASK_MISSING = "task_missing"


@dataclass(frozen=True)
class DiscoveryResult:
    outcome: Outcome
    papers_linked: int = 0
    retry_in_seconds: float | None = None
    failure_reason: str | None = None


def retry_delay_seconds(attempt: int, settings: Settings, jitter: float | None = None) -> float:
    """Exponential backoff for attempt n (1-based), capped, with ±20% jitter so
    many failures at once do not all retry in the same second."""
    base = min(settings.retry_base_seconds * 2 ** (attempt - 1), settings.retry_max_seconds)
    factor = jitter if jitter is not None else random.uniform(0.8, 1.2)  # noqa: S311
    return float(base * factor)


def search_query(question: str, max_length: int = 200) -> str:
    """Use the question itself as the search text, cut at a word boundary."""
    text_ = " ".join(question.split())
    if len(text_) <= max_length:
        return text_
    return text_[:max_length].rsplit(" ", 1)[0]


def handle_investigation_requested(
    session_factory: sessionmaker[Session],
    provider: PaperProvider,
    envelope: EventEnvelope,
    settings: Settings,
) -> DiscoveryResult:
    payload = parse_payload(envelope, InvestigationRequestedV1)

    # 1. Skip duplicates; claim the task.
    with session_factory() as session, session.begin():
        if _already_processed(session, envelope.event_id):
            return DiscoveryResult(Outcome.DUPLICATE)
        if session.get(InvestigationTask, payload.task_id) is None:
            _mark_processed(session, envelope.event_id)
            return DiscoveryResult(Outcome.TASK_MISSING)
        attempt = _claim_task(session, payload.task_id)
        if attempt is None:
            return DiscoveryResult(Outcome.BUSY_ELSEWHERE)
        session.execute(
            update(Investigation)
            .where(
                Investigation.id == envelope.investigation_id,
                Investigation.status == InvestigationStatus.QUEUED,
            )
            .values(status=InvestigationStatus.RUNNING)
        )

    # 2. Call the provider with no transaction open.
    params = PaperSearchParams(
        q=search_query(payload.question), per_page=settings.discovery_papers_per_investigation
    )
    try:
        with session_factory() as session:
            response = papers_service.search_papers(
                session,
                provider,
                params,
                cache_ttl=timedelta(hours=settings.paper_search_cache_hours),
                daily_provider_call_cap=settings.daily_provider_call_cap,
            )
    except (ProviderUnavailableError, papers_service.ProviderQuotaExceededError) as exc:
        reason = str(exc) or "paper search daily limit reached"
        return _handle_temporary_failure(
            session_factory, envelope, payload, attempt, reason, settings
        )

    if not response.results:
        _finish_failed(
            session_factory,
            envelope,
            payload.task_id,
            TaskStatus.FAILED_PERMANENT,
            "No papers found for this question",
        )
        return DiscoveryResult(Outcome.NO_PAPERS)

    # 3. Persist links, follow-up events, task result, and the idempotency record together.
    try:
        with session_factory() as session, session.begin():
            _mark_processed(session, envelope.event_id)
            for rank, item in enumerate(response.results, start=1):
                _link_paper(session, envelope, item.paper, rank, item.relevance_score)
            _finish_task(
                session,
                payload.task_id,
                TaskStatus.SUCCEEDED,
                summary={
                    "papers_linked": len(response.results),
                    "papers_available": response.total,
                    "query": params.q,
                    "provider": response.provider,
                },
            )
    except IntegrityError:
        # Another delivery of the same event committed first.
        return DiscoveryResult(Outcome.DUPLICATE)
    return DiscoveryResult(Outcome.LINKED, papers_linked=len(response.results))


def _already_processed(session: Session, event_id: uuid.UUID) -> bool:
    return bool(
        session.scalar(
            select(
                exists().where(
                    ProcessedEvent.consumer_group == CONSUMER_GROUP,
                    ProcessedEvent.event_id == event_id,
                )
            )
        )
    )


def _mark_processed(session: Session, event_id: uuid.UUID) -> None:
    session.add(ProcessedEvent(consumer_group=CONSUMER_GROUP, event_id=event_id))
    session.flush()


def _claim_task(session: Session, task_id: uuid.UUID) -> int | None:
    """Mark the task running and return its attempt number, or None if another
    worker owns it or it is already finished."""
    claimed = session.execute(
        text(
            """
            UPDATE investigation_tasks
               SET status = 'running', attempts = attempts + 1, started_at = now(),
                   finished_at = NULL, last_error = NULL, next_attempt_at = NULL
             WHERE id = :id
               AND (status IN ('pending', 'failed_retryable')
                    OR (status = 'running' AND started_at < now() - :stale))
            RETURNING attempts
            """
        ),
        {"id": task_id, "stale": STALE_RUNNING_AFTER},
    ).first()
    return int(claimed.attempts) if claimed else None


def _link_paper(
    session: Session,
    envelope: EventEnvelope,
    paper: PaperRead,
    rank: int,
    relevance_score: float | None,
) -> None:
    inserted = session.execute(
        insert(InvestigationPaper)
        .values(
            investigation_id=envelope.investigation_id,
            paper_id=paper.id,
            rank=rank,
            relevance_score=relevance_score,
            retrieval_method=RETRIEVAL_METHOD,
        )
        .on_conflict_do_nothing()
        .returning(InvestigationPaper.paper_id)
    ).first()
    if inserted is None:
        return  # already linked; do not announce it twice
    event = new_event(
        PAPER_DISCOVERED,
        PaperDiscoveredV1(
            paper_id=paper.id,
            rank=rank,
            relevance_score=relevance_score,
            full_text_availability=FullTextAvailability(paper.full_text_availability).value,
        ),
        investigation_id=envelope.investigation_id,
        entity_id=paper.id,
        correlation_id=envelope.correlation_id,
        causation_id=envelope.event_id,
    )
    # Keyed by paper so per-paper work spreads across partitions and workers.
    enqueue(session, event, partition_key=str(paper.id))


def _finish_task(
    session: Session,
    task_id: uuid.UUID,
    status: TaskStatus,
    *,
    summary: dict[str, object] | None = None,
    error: str | None = None,
) -> None:
    session.execute(
        update(InvestigationTask)
        .where(InvestigationTask.id == task_id)
        .values(status=status, finished_at=func.now(), result_summary=summary, last_error=error)
    )


def _handle_temporary_failure(
    session_factory: sessionmaker[Session],
    envelope: EventEnvelope,
    payload: InvestigationRequestedV1,
    attempt: int,
    reason: str,
    settings: Settings,
) -> DiscoveryResult:
    if attempt >= settings.discovery_max_attempts:
        final = f"Gave up after {attempt} attempts: {reason}"
        _finish_failed(
            session_factory, envelope, payload.task_id, TaskStatus.FAILED_PERMANENT, final
        )
        return DiscoveryResult(Outcome.RETRIES_EXHAUSTED, failure_reason=final)

    delay = retry_delay_seconds(attempt, settings)
    retry = new_event(
        INVESTIGATION_REQUESTED,
        payload,
        investigation_id=envelope.investigation_id,
        entity_id=payload.task_id,
        correlation_id=envelope.correlation_id,
        causation_id=envelope.event_id,
    )
    logger.warning(
        "discovery attempt failed; retry scheduled",
        extra={"task_id": str(payload.task_id), "attempt": attempt, "retry_in_s": round(delay)},
    )
    with session_factory() as session, session.begin():
        _mark_processed(session, envelope.event_id)
        session.execute(
            update(InvestigationTask)
            .where(InvestigationTask.id == payload.task_id)
            .values(
                status=TaskStatus.FAILED_RETRYABLE,
                last_error=reason,
                finished_at=func.now(),
                next_attempt_at=func.now() + timedelta(seconds=delay),
            )
        )
        enqueue(
            session,
            retry,
            partition_key=str(envelope.investigation_id),
            deliver_after=timedelta(seconds=delay),
        )
    return DiscoveryResult(Outcome.RETRY_SCHEDULED, retry_in_seconds=delay, failure_reason=reason)


def _finish_failed(
    session_factory: sessionmaker[Session],
    envelope: EventEnvelope,
    task_id: uuid.UUID,
    status: TaskStatus,
    reason: str,
) -> None:
    logger.warning("discovery failed", extra={"task_id": str(task_id), "reason": reason})
    with session_factory() as session, session.begin():
        _mark_processed(session, envelope.event_id)
        _finish_task(session, task_id, status, error=reason)
        session.execute(
            update(Investigation)
            .where(Investigation.id == envelope.investigation_id)
            .values(status=InvestigationStatus.FAILED)
        )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    session_factory = create_session_factory(create_db_engine(settings))
    provider = make_provider(settings)

    def handle(envelope: EventEnvelope) -> HandlerResult:
        result = handle_investigation_requested(session_factory, provider, envelope, settings)
        return HandlerResult(
            summary=f"{result.outcome} ({result.papers_linked} papers)",
            dead_letter_reason=(
                result.failure_reason if result.outcome == Outcome.RETRIES_EXHAUSTED else None
            ),
        )

    run_consumer(settings, group_id=CONSUMER_GROUP, topic=TOPIC, handler=handle)
    provider.close()


if __name__ == "__main__":
    main()
