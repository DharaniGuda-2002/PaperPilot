import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.investigations.models import (
    QUESTION_MAX_LENGTH,
    QUESTION_MIN_LENGTH,
    InvestigationStatus,
)


class InvestigationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=QUESTION_MIN_LENGTH, max_length=QUESTION_MAX_LENGTH)


class InvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question: str
    status: InvestigationStatus
    created_at: datetime
    updated_at: datetime


class InvestigationPage(BaseModel):
    items: list[InvestigationRead]
    total: int
    limit: int
    offset: int
