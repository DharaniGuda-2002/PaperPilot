"""Task-state helpers shared by pipeline workers.

A task is identified by (investigation, kind, subject_key). Claiming is a
conditional UPDATE so only one worker runs a task at a time; tasks left
`running` by a crashed worker can be reclaimed after STALE_RUNNING_AFTER.
"""

import random
import uuid
from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy import exists, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.events.envelope import EventEnvelope, EventSpec, new_event
from app.events.models import ProcessedEvent
from app.events.outbox import enqueue
from app.investigations.models import InvestigationTask, TaskStatus

STALE_RUNNING_AFTER = timedelta(minutes=10)


def already_processed(session: Session, group: str, event_id: uuid.UUID) -> bool:
    return bool(
        session.scalar(
            select(
                exists().where(
                    ProcessedEvent.consumer_group == group, ProcessedEvent.event_id == event_id
                )
            )
        )
    )


def mark_processed(session: Session, group: str, event_id: uuid.UUID) -> None:
    session.add(ProcessedEvent(consumer_group=group, event_id=event_id))
    session.flush()


def ensure_task(
    session: Session, investigation_id: uuid.UUID, kind: str, subject_key: str
) -> uuid.UUID:
    """Create the task if missing (e.g. investigations from before a stage existed)."""
    session.execute(
        insert(InvestigationTask)
        .values(
            id=uuid.uuid4(),
            investigation_id=investigation_id,
            kind=kind,
            subject_key=subject_key,
            status=TaskStatus.PENDING,
        )
        .on_conflict_do_nothing(constraint="uq_investigation_tasks_subject")
    )
    task_id = session.scalar(
        select(InvestigationTask.id).where(
            InvestigationTask.investigation_id == investigation_id,
            InvestigationTask.kind == kind,
            InvestigationTask.subject_key == subject_key,
        )
    )
    assert task_id is not None
    return task_id


def claim_task(session: Session, task_id: uuid.UUID) -> int | None:
    """Mark running and return the attempt number, or None if not claimable."""
    row = session.execute(
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
    return int(row.attempts) if row else None


def finish_task(
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
        .values(
            status=status,
            finished_at=func.now(),
            result_summary=summary,
            last_error=error,
            next_attempt_at=None,
        )
    )


def backoff_seconds(attempt: int, settings: Settings) -> float:
    base = min(settings.retry_base_seconds * 2 ** (attempt - 1), settings.retry_max_seconds)
    return float(base * random.uniform(0.8, 1.2))  # noqa: S311


def schedule_redelivery(
    session: Session,
    *,
    envelope: EventEnvelope,
    spec: EventSpec,
    payload: BaseModel,
    task_id: uuid.UUID,
    partition_key: str,
    delay_seconds: float,
    reason: str,
    counts_as_attempt: bool,
) -> None:
    """Re-publish this event later through the outbox. A deferral (waiting for a
    rate window) gives the attempt back; a failure keeps it."""
    session.execute(
        update(InvestigationTask)
        .where(InvestigationTask.id == task_id)
        .values(
            status=TaskStatus.FAILED_RETRYABLE if counts_as_attempt else TaskStatus.PENDING,
            attempts=InvestigationTask.attempts - (0 if counts_as_attempt else 1),
            last_error=reason,
            finished_at=func.now(),
            next_attempt_at=func.now() + timedelta(seconds=delay_seconds),
        )
    )
    retry = new_event(
        spec,
        payload,
        investigation_id=envelope.investigation_id,
        entity_id=envelope.entity_id,
        correlation_id=envelope.correlation_id,
        causation_id=envelope.event_id,
    )
    enqueue(
        session, retry, partition_key=partition_key, deliver_after=timedelta(seconds=delay_seconds)
    )
