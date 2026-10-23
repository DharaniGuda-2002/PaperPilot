import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.documents.models import PaperChunk, PaperDocument
from app.evidence.models import EvidenceField, EvidenceRecord, EvidenceValidation, FindingStatus
from app.investigations.models import Investigation
from app.papers.models import Paper

router = APIRouter(tags=["evidence"])
SessionDep = Annotated[Session, Depends(get_session)]


class ValidationCheck(BaseModel):
    rule: str
    outcome: str
    details: str | None
    validator_version: str


class EvidenceItem(BaseModel):
    id: uuid.UUID
    paper_id: uuid.UUID
    paper_title: str
    field: EvidenceField
    finding_status: FindingStatus
    value: dict[str, Any] | None
    passage: str | None
    passage_kind: str | None
    page_number: int | None
    extraction_method: str
    extraction_version: str
    retrieval_method: str | None
    retrieval_score: float | None
    validation_status: str
    checks: list[ValidationCheck]
    created_at: datetime


class DocumentInfo(BaseModel):
    paper_id: uuid.UUID
    content_kind: str
    full_text_unavailable_reason: str | None
    source_url: str | None
    final_url: str | None
    page_count: int | None
    byte_size: int | None
    sha256: str | None
    extractor: str
    extractor_version: str
    fetched_at: datetime | None
    chunk_count: int
    embedding_models: list[str]


@router.get("/api/v1/investigations/{investigation_id}/evidence")
def list_evidence(
    investigation_id: uuid.UUID,
    session: SessionDep,
    paper_id: uuid.UUID | None = None,
    field: EvidenceField | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[EvidenceItem]:
    if session.get(Investigation, investigation_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    query = (
        select(EvidenceRecord, Paper.title)
        .join(Paper, Paper.id == EvidenceRecord.paper_id)
        .where(EvidenceRecord.investigation_id == investigation_id)
        .order_by(Paper.title, EvidenceRecord.field, EvidenceRecord.page_number, EvidenceRecord.id)
        .limit(limit)
    )
    if paper_id:
        query = query.where(EvidenceRecord.paper_id == paper_id)
    if field:
        query = query.where(EvidenceRecord.field == field)
    rows = session.execute(query).all()

    checks: dict[uuid.UUID, list[ValidationCheck]] = {}
    ids = [record.id for record, _ in rows]
    if ids:
        for check in session.scalars(
            select(EvidenceValidation)
            .where(EvidenceValidation.evidence_id.in_(ids))
            .order_by(EvidenceValidation.created_at, EvidenceValidation.rule)
        ):
            checks.setdefault(check.evidence_id, []).append(
                ValidationCheck(
                    rule=check.rule,
                    outcome=check.outcome,
                    details=check.details,
                    validator_version=check.validator_version,
                )
            )
    return [
        EvidenceItem(
            id=record.id,
            paper_id=record.paper_id,
            paper_title=title,
            field=EvidenceField(record.field),
            finding_status=FindingStatus(record.finding_status),
            value=record.value,
            passage=record.passage,
            passage_kind=record.passage_kind,
            page_number=record.page_number,
            extraction_method=record.extraction_method,
            extraction_version=record.extraction_version,
            retrieval_method=record.retrieval_method,
            retrieval_score=record.retrieval_score,
            validation_status=record.validation_status,
            checks=checks.get(record.id, []),
            created_at=record.created_at,
        )
        for record, title in rows
    ]


@router.get("/api/v1/papers/{paper_id}/document")
def get_document(paper_id: uuid.UUID, session: SessionDep) -> DocumentInfo:
    document = session.scalar(select(PaperDocument).where(PaperDocument.paper_id == paper_id))
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not processed")
    count, models = session.execute(
        select(func.count(), func.array_agg(func.distinct(PaperChunk.embedding_model))).where(
            PaperChunk.document_id == document.id
        )
    ).one()
    return DocumentInfo(
        paper_id=paper_id,
        content_kind=document.content_kind,
        full_text_unavailable_reason=document.full_text_unavailable_reason,
        source_url=document.source_url,
        final_url=document.final_url,
        page_count=document.page_count,
        byte_size=document.byte_size,
        sha256=document.sha256,
        extractor=document.extractor,
        extractor_version=document.extractor_version,
        fetched_at=document.fetched_at,
        chunk_count=int(count),
        embedding_models=[m for m in (models or []) if m],
    )
