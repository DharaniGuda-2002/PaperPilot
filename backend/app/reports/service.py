"""Load persisted, validated evidence for an investigation, compare it, build
the report, and store it as a new immutable version."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.comparison.rules import COMPARISON_VERSION, EvidenceInput, PaperInput, compare
from app.documents.models import PaperDocument
from app.evidence.models import EvidenceRecord, ValidationStatus
from app.evidence.rules import EXTRACTION_VERSION
from app.evidence.validation import VALIDATOR_VERSION
from app.investigations.models import (
    Investigation,
    InvestigationPaper,
    InvestigationStatus,
    InvestigationTask,
    TaskKind,
    TaskStatus,
)
from app.papers.models import Paper
from app.reports.builder import build_report
from app.reports.models import InvestigationReport
from app.reports.schemas import PaperRef, Report

TERMINAL = {TaskStatus.SUCCEEDED, TaskStatus.FAILED_PERMANENT, TaskStatus.SKIPPED}
PER_PAPER_STAGES = (TaskKind.PROCESS_DOCUMENT, TaskKind.EXTRACT_EVIDENCE)


def pipeline_state(session: Session, investigation_id: uuid.UUID) -> tuple[bool, bool]:
    """(every per-paper task is finished, some per-paper task failed permanently)."""
    statuses = session.scalars(
        select(InvestigationTask.status).where(
            InvestigationTask.investigation_id == investigation_id,
            InvestigationTask.kind.in_(PER_PAPER_STAGES),
        )
    ).all()
    finished = bool(statuses) and all(s in TERMINAL for s in statuses)
    failures = any(s == TaskStatus.FAILED_PERMANENT for s in statuses)
    return finished, failures


def assemble_report(session: Session, investigation: Investigation) -> Report:
    rows = session.execute(
        select(Paper, PaperDocument.content_kind)
        .join(InvestigationPaper, InvestigationPaper.paper_id == Paper.id)
        .outerjoin(PaperDocument, PaperDocument.paper_id == Paper.id)
        .where(InvestigationPaper.investigation_id == investigation.id)
        .order_by(InvestigationPaper.rank)
    ).all()
    papers = [
        PaperInput(paper.id, paper.title, paper.publication_year, kind or "none")
        for paper, kind in rows
    ]
    refs = [
        PaperRef(
            paper_id=paper.id,
            title=paper.title,
            authors=paper.authors,
            year=paper.publication_year,
            venue=paper.venue,
            doi=paper.doi,
            url=paper.landing_page_url or paper.pdf_url,
            content_kind=kind or "none",
        )
        for paper, kind in rows
    ]
    # Only checkable evidence feeds the comparison: verified quotations, plus
    # absence records (which say what could not be found).
    records = session.scalars(
        select(EvidenceRecord).where(
            EvidenceRecord.investigation_id == investigation.id,
            (EvidenceRecord.validation_status == ValidationStatus.VERIFIED)
            | EvidenceRecord.passage.is_(None),
        )
    ).all()
    evidence = [
        EvidenceInput(
            evidence_id=r.id,
            paper_id=r.paper_id,
            field=r.field,
            finding_status=r.finding_status,
            value=r.value,
            passage=r.passage,
            page_number=r.page_number,
        )
        for r in records
    ]
    return build_report(
        question=investigation.question,
        papers=refs,
        papers_discovered=len(papers),
        comparison=compare(papers, evidence),
        versions={
            "extraction": EXTRACTION_VERSION,
            "validation": VALIDATOR_VERSION,
            "comparison": COMPARISON_VERSION,
        },
    )


def save_report(session: Session, investigation_id: uuid.UUID, report: Report) -> int:
    version = (
        session.scalar(
            select(func.max(InvestigationReport.version)).where(
                InvestigationReport.investigation_id == investigation_id
            )
        )
        or 0
    ) + 1
    session.add(
        InvestigationReport(
            investigation_id=investigation_id,
            version=version,
            schema_version=report.schema_version,
            generator_version=report.generator_version,
            overall_strength=report.overall_strength,
            content=report.model_dump(mode="json"),
        )
    )
    session.flush()
    return version


def final_status(report: Report, task_failures: bool) -> InvestigationStatus:
    """completed: every paper went through every stage. partially_completed: some
    papers failed or had no text at all. The report states evidence strength
    separately; an 'insufficient' report is still a completed investigation."""
    if task_failures or report.scope.no_text:
        return InvestigationStatus.PARTIALLY_COMPLETED
    return InvestigationStatus.COMPLETED


def latest_report(session: Session, investigation_id: uuid.UUID) -> InvestigationReport | None:
    return session.scalar(
        select(InvestigationReport)
        .where(InvestigationReport.investigation_id == investigation_id)
        .order_by(InvestigationReport.version.desc())
        .limit(1)
    )
