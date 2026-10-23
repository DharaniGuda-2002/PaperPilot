"""Investigation use cases. Functions stage changes; the caller owns the commit,
so later milestones can add an outbox event to the same transaction."""

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.investigations.models import Investigation
from app.investigations.schemas import InvestigationCreate


def create_investigation(session: Session, data: InvestigationCreate) -> Investigation:
    investigation = Investigation(question=data.question)
    session.add(investigation)
    session.flush()
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
