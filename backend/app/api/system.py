from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.events.outbox import outbox_backlog

router = APIRouter(prefix="/api/v1/system", tags=["system"])


class PipelineStatus(BaseModel):
    outbox_backlog: int
    oldest_pending_seconds: float | None


@router.get("/pipeline")
def pipeline_status(session: Annotated[Session, Depends(get_session)]) -> PipelineStatus:
    """Unpublished outbox events. A growing backlog means no dispatcher is running
    (for example on the public demo, which hosts no background workers)."""
    backlog, oldest = outbox_backlog(session)
    return PipelineStatus(outbox_backlog=backlog, oldest_pending_seconds=oldest)
