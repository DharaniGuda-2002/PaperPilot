"""Gather relevant passages for a paper, extract facts, validate them, and store
the results with provenance."""

import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.evidence.models import (
    EvidenceField,
    EvidenceRecord,
    EvidenceValidation,
    FindingStatus,
    ValidationStatus,
)
from app.evidence.rules import (
    EXTRACTION_METHOD,
    EXTRACTION_VERSION,
    FIELD_QUERIES,
    ExtractedFact,
    SourceChunk,
    extract,
)
from app.evidence.validation import VALIDATOR_VERSION, CheckResult, validate
from app.retrieval.embeddings import Embedder
from app.retrieval.hybrid import RetrievalConfig, hybrid_search

PASSAGES_PER_QUERY = 8


@dataclass
class EvidenceBatch:
    records: list[EvidenceRecord] = field(default_factory=list)
    checks: dict[uuid.UUID, list[CheckResult]] = field(default_factory=dict)

    @property
    def reported(self) -> list[EvidenceRecord]:
        return [r for r in self.records if r.finding_status == FindingStatus.REPORTED]

    def count(self, status: ValidationStatus) -> int:
        return sum(r.validation_status == status for r in self.reported)

    def summary(self) -> dict[str, object]:
        reported = self.reported
        return {
            "records": len(reported),
            "verified": self.count(ValidationStatus.VERIFIED),
            "rejected": self.count(ValidationStatus.REJECTED),
            "by_field": dict(Counter(r.field for r in reported)),
            "fields_without_evidence": sorted(
                r.field for r in self.records if r.finding_status != FindingStatus.REPORTED
            ),
        }


def query_texts(question: str) -> list[str]:
    return [question, *FIELD_QUERIES.values()]


def gather_sources(
    session: Session,
    *,
    paper_id: uuid.UUID,
    queries: list[str],
    query_embeddings: list[list[float]],
    model_id: str,
) -> list[SourceChunk]:
    """Union of hybrid-search results for the question and each field query,
    keeping each chunk once with the provenance of its first (best) hit."""
    sources: dict[uuid.UUID, SourceChunk] = {}
    config = RetrievalConfig(limit=PASSAGES_PER_QUERY)
    for query, embedding in zip(queries, query_embeddings, strict=True):
        for candidate in hybrid_search(
            session,
            query=query,
            query_embedding=embedding,
            model_id=model_id,
            paper_ids=[paper_id],
            config=config,
        ):
            sources.setdefault(
                candidate.chunk_id,
                SourceChunk(
                    chunk_id=candidate.chunk_id,
                    page_number=candidate.page_number,
                    text=candidate.text,
                    retrieval_method=candidate.method,
                    retrieval_score=round(candidate.score, 6),
                ),
            )
    return list(sources.values())


def build_evidence(
    *,
    investigation_id: uuid.UUID,
    paper_id: uuid.UUID,
    content_kind: str,
    page_count: int | None,
    sources: list[SourceChunk],
) -> EvidenceBatch:
    batch = EvidenceBatch()
    facts = extract(sources) if content_kind != "none" else []
    for fact in facts:
        _add_fact(batch, investigation_id, paper_id, page_count, fact)

    found = {f.field for f in facts}
    absent_status = (
        FindingStatus.NOT_FOUND if content_kind == "full_text" else FindingStatus.UNAVAILABLE
    )
    for missing in EvidenceField:
        if missing not in found:
            batch.records.append(
                EvidenceRecord(
                    id=uuid.uuid4(),
                    investigation_id=investigation_id,
                    paper_id=paper_id,
                    field=missing,
                    finding_status=absent_status,
                    extraction_method=EXTRACTION_METHOD,
                    extraction_version=EXTRACTION_VERSION,
                    validation_status=ValidationStatus.UNVALIDATED,
                )
            )
    return batch


def _add_fact(
    batch: EvidenceBatch,
    investigation_id: uuid.UUID,
    paper_id: uuid.UUID,
    page_count: int | None,
    fact: ExtractedFact,
) -> None:
    record_id = uuid.uuid4()
    checks = validate(
        passage=fact.passage,
        chunk_text=fact.chunk.text,
        chunk_page=fact.chunk.page_number,
        claimed_page=fact.chunk.page_number,
        document_page_count=page_count,
        value=fact.value,
    )
    batch.checks[record_id] = checks
    batch.records.append(
        EvidenceRecord(
            id=record_id,
            investigation_id=investigation_id,
            paper_id=paper_id,
            chunk_id=fact.chunk.chunk_id,
            field=fact.field,
            finding_status=FindingStatus.REPORTED,
            value=fact.value,
            passage=fact.passage,
            passage_kind="quotation",
            page_number=fact.chunk.page_number,
            extraction_method=EXTRACTION_METHOD,
            extraction_version=EXTRACTION_VERSION,
            retrieval_method=fact.chunk.retrieval_method,
            retrieval_score=fact.chunk.retrieval_score,
            validation_status=(
                ValidationStatus.VERIFIED
                if all(c.passed for c in checks)
                else ValidationStatus.REJECTED
            ),
        )
    )


def save_evidence(
    session: Session, investigation_id: uuid.UUID, paper_id: uuid.UUID, batch: EvidenceBatch
) -> None:
    """Replace this paper's evidence for the investigation (re-extraction is safe)."""
    session.execute(
        delete(EvidenceRecord).where(
            EvidenceRecord.investigation_id == investigation_id,
            EvidenceRecord.paper_id == paper_id,
        )
    )
    session.add_all(batch.records)
    session.flush()
    session.add_all(
        EvidenceValidation(
            evidence_id=record_id,
            rule=check.rule,
            outcome="pass" if check.passed else "fail",
            details=check.details,
            validator_version=VALIDATOR_VERSION,
        )
        for record_id, checks in batch.checks.items()
        for check in checks
    )


def embed_queries(embedder: Embedder, question: str) -> tuple[list[str], list[list[float]]]:
    queries = query_texts(question)
    return queries, embedder.embed(queries)
