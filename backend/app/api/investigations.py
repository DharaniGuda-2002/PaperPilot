import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.investigations import service
from app.investigations.schemas import InvestigationCreate, InvestigationPage, InvestigationRead

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", status_code=status.HTTP_201_CREATED)
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


@router.get("/{investigation_id}")
def get_investigation(investigation_id: uuid.UUID, session: SessionDep) -> InvestigationRead:
    investigation = service.get_investigation(session, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    return InvestigationRead.model_validate(investigation)
