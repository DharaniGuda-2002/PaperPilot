import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.evidence import DocumentInfo, ValidationCheck
from app.api.evidence import get_document as document_info
from app.core.db import get_session
from app.evidence.models import EvidenceRecord, EvidenceValidation
from app.investigations.models import Investigation
from app.papers.models import Paper
from app.reports.service import latest_report

router = APIRouter(tags=["reports"])
SessionDep = Annotated[Session, Depends(get_session)]


class ReportEnvelope(BaseModel):
    investigation_id: uuid.UUID
    version: int
    created_at: datetime
    content: dict[str, Any]


class EvidenceDetail(BaseModel):
    """Everything the evidence inspector shows for one citation."""

    id: uuid.UUID
    investigation_id: uuid.UUID
    field: str
    finding_status: str
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
    paper_id: uuid.UUID
    paper_title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    paper_url: str | None
    document: DocumentInfo | None


@router.get("/api/v1/investigations/{investigation_id}/report")
def get_report(investigation_id: uuid.UUID, session: SessionDep) -> ReportEnvelope:
    if session.get(Investigation, investigation_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")
    report = latest_report(session, investigation_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not ready")
    return ReportEnvelope(
        investigation_id=investigation_id,
        version=report.version,
        created_at=report.created_at,
        content=report.content,
    )


@router.get("/api/v1/evidence/{evidence_id}")
def get_evidence(evidence_id: uuid.UUID, session: SessionDep) -> EvidenceDetail:
    record = session.get(EvidenceRecord, evidence_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    paper = session.get(Paper, record.paper_id)
    assert paper is not None  # foreign key
    checks = session.scalars(
        select(EvidenceValidation)
        .where(EvidenceValidation.evidence_id == evidence_id)
        .order_by(EvidenceValidation.created_at, EvidenceValidation.rule)
    ).all()
    try:
        document = document_info(record.paper_id, session)
    except HTTPException:
        document = None
    return EvidenceDetail(
        id=record.id,
        investigation_id=record.investigation_id,
        field=record.field,
        finding_status=record.finding_status,
        value=record.value,
        passage=record.passage,
        passage_kind=record.passage_kind,
        page_number=record.page_number,
        extraction_method=record.extraction_method,
        extraction_version=record.extraction_version,
        retrieval_method=record.retrieval_method,
        retrieval_score=record.retrieval_score,
        validation_status=record.validation_status,
        checks=[
            ValidationCheck(
                rule=c.rule,
                outcome=c.outcome,
                details=c.details,
                validator_version=c.validator_version,
            )
            for c in checks
        ],
        created_at=record.created_at,
        paper_id=paper.id,
        paper_title=paper.title,
        authors=paper.authors,
        year=paper.publication_year,
        venue=paper.venue,
        doi=paper.doi,
        paper_url=paper.landing_page_url or paper.pdf_url,
        document=document,
    )
