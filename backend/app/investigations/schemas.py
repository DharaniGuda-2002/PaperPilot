import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.investigations.models import (
    QUESTION_MAX_LENGTH,
    QUESTION_MIN_LENGTH,
    InvestigationStatus,
    TaskStatus,
)
from app.papers.schemas import PaperRead


class InvestigationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=QUESTION_MIN_LENGTH, max_length=QUESTION_MAX_LENGTH)


class InvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question: str
    status: InvestigationStatus
    is_example: bool = False
    created_at: datetime
    updated_at: datetime


class InvestigationStats(BaseModel):
    total: int
    by_status: dict[InvestigationStatus, int]


class InvestigationPage(BaseModel):
    items: list[InvestigationRead]
    total: int
    limit: int
    offset: int


class InvestigationTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    subject_key: str
    status: TaskStatus
    attempts: int
    last_error: str | None
    result_summary: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class DiscoveredPaper(BaseModel):
    rank: int
    relevance_score: float | None
    retrieval_method: str
    discovered_at: datetime
    paper: PaperRead


class DiscoveredPaperPage(BaseModel):
    items: list[DiscoveredPaper]
    total: int
    limit: int
    offset: int
