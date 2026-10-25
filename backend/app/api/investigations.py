import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import get_session
from app.core.rate_limit import SlidingWindowLimiter, client_address
from app.investigations import service
from app.investigations.models import Investigation
from app.investigations.schemas import (
    DiscoveredPaperPage,
    InvestigationCreate,
    InvestigationPage,
    InvestigationRead,
    InvestigationStats,
    InvestigationTaskRead,
)

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])

SessionDep = Annotated[Session, Depends(get_session)]


def enforce_create_limits(request: Request, session: SessionDep) -> None:
    """Per-client and global caps so anonymous users cannot flood the demo database."""
    settings: Settings = request.app.state.settings
    limiter: SlidingWindowLimiter = request.app.state.create_limiter
    client_ip = client_address(request, settings.trusted_proxy_hops, settings.client_ip_header)
    if not limiter.allow(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many investigations from this address. Try again in a minute.",
            headers={"Retry-After": "60"},
        )
    if (
        service.count_created_in_last(session, timedelta(days=1))
        >= settings.daily_investigation_cap
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The demo has reached its daily investigation limit. Try again tomorrow.",
            headers={"Retry-After": "3600"},
        )


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(enforce_create_limits)])
def create_investigation(
    body: InvestigationCreate, session: SessionDep, response: Response
) -> InvestigationRead:
    investigation = service.create_investigation(session, body)
    session.commit()
    session.refresh(investigation)  # load server-generated timestamps
    response.headers["Location"] = f"{router.prefix}/{investigation.id}"
    return InvestigationRead.model_validate(investigation)


@router.get("")
def list_investigations(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvestigationPage:
    items, total = service.list_investigations(session, limit=limit, offset=offset)
    return InvestigationPage(
        items=[InvestigationRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/examples")
def list_examples(session: SessionDep) -> list[InvestigationRead]:
    """Finished runs kept on purpose so a visitor can see a real result.
    Declared before /{investigation_id}."""
    rows = session.scalars(
        select(Investigation)
        .where(Investigation.is_example.is_(True))
        .order_by(Investigation.created_at.desc())
        .limit(5)
    )
    return [InvestigationRead.model_validate(row) for row in rows]


@router.get("/stats")
def investigation_stats(session: SessionDep) -> InvestigationStats:
    """Counts by status for the dashboard. Declared before /{investigation_id}."""
    return service.investigation_stats(session)


@router.get("/{investigation_id}")
def get_investigation(investigation_id: uuid.UUID, session: SessionDep) -> InvestigationRead:
    investigation = service.get_investigation(session, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    return InvestigationRead.model_validate(investigation)


def _require_investigation(session: Session, investigation_id: uuid.UUID) -> None:
    if service.get_investigation(session, investigation_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")


@router.get("/{investigation_id}/tasks")
def list_tasks(investigation_id: uuid.UUID, session: SessionDep) -> list[InvestigationTaskRead]:
    _require_investigation(session, investigation_id)
    return [
        InvestigationTaskRead.model_validate(t)
        for t in service.list_tasks(session, investigation_id)
    ]


@router.get("/{investigation_id}/papers")
def list_discovered_papers(
    investigation_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DiscoveredPaperPage:
    _require_investigation(session, investigation_id)
    items, total = service.list_discovered_papers(
        session, investigation_id, limit=limit, offset=offset
    )
    return DiscoveredPaperPage(items=items, total=total, limit=limit, offset=offset)
