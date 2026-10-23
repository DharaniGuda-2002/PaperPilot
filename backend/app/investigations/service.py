"""Investigation use cases. Functions stage changes; the caller owns the commit,
so later milestones can add an outbox event to the same transaction."""

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import correlation_id_var
from app.events.envelope import INVESTIGATION_REQUESTED, InvestigationRequestedV1, new_event
from app.events.outbox import enqueue
from app.investigations.models import (
    Investigation,
    InvestigationStatus,
    InvestigationTask,
    TaskKind,
)
from app.investigations.schemas import InvestigationCreate, InvestigationStats


def create_investigation(session: Session, data: InvestigationCreate) -> Investigation:
    """Stage the investigation, its discovery task, and the event that starts the
    pipeline. All three commit together or not at all (transactional outbox)."""
    investigation = Investigation(question=data.question)
    session.add(investigation)
    session.flush()
    task = InvestigationTask(investigation_id=investigation.id, kind=TaskKind.DISCOVER_PAPERS)
    session.add(task)
    session.flush()

    request_id = correlation_id_var.get()
    event = new_event(
        INVESTIGATION_REQUESTED,
        InvestigationRequestedV1(task_id=task.id, question=investigation.question),
        investigation_id=investigation.id,
        entity_id=task.id,
        correlation_id=uuid.UUID(request_id) if request_id else uuid.uuid4(),
    )
    enqueue(session, event, partition_key=str(investigation.id))
    return investigation


def count_created_in_last(session: Session, window: timedelta) -> int:
    """Uses ix_investigations_created_at."""
    return (
        session.scalar(
            select(func.count())
            .select_from(Investigation)
            .where(Investigation.created_at > func.now() - window)
        )
        or 0
    )


def investigation_stats(session: Session) -> InvestigationStats:
    rows = session.execute(
        select(Investigation.status, func.count()).group_by(Investigation.status)
    ).all()
    counts = {status: 0 for status in InvestigationStatus}
    for status, count in rows:
        counts[InvestigationStatus(status)] = count
    return InvestigationStats(total=sum(counts.values()), by_status=counts)


def get_investigation(session: Session, investigation_id: uuid.UUID) -> Investigation | None:
    return session.get(Investigation, investigation_id)


def list_investigations(
    session: Session, *, limit: int, offset: int
) -> tuple[Sequence[Investigation], int]:
    total = session.scalar(select(func.count()).select_from(Investigation)) or 0
    items = session.scalars(
        select(Investigation)
        .order_by(Investigation.created_at.desc(), Investigation.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return items, total
