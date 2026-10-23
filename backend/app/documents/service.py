"""Turn a paper into a stored document: permitted full text when available,
otherwise the provider abstract, with provenance and embeddings."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents.fetch import (
    FetchDeferredError,
    FetchedPdf,
    FetchFailedError,
    FetchRejectedError,
    SafeFetcher,
)
from app.documents.models import PaperChunk, PaperDocument
from app.documents.text import (
    EXTRACTOR,
    EXTRACTOR_VERSION,
    Chunk,
    ExtractionError,
    chunk_abstract,
    chunk_pages,
    extract_pages,
)
from app.papers.models import Paper
from app.retrieval.embeddings import Embedder

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedDocument:
    """Everything needed to store a document, computed with no transaction open."""

    content_kind: str  # full_text | abstract | none
    chunks: list[Chunk]
    embeddings: list[list[float]]
    unavailable_reason: str | None
    fetched: FetchedPdf | None
    page_count: int | None


class TemporaryFetchError(Exception):
    """Full text is worth retrying later (network error, 5xx, politeness window)."""

    def __init__(self, reason: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(reason)
        self.retry_after_seconds = retry_after_seconds


def full_text_url(paper: Paper) -> tuple[str | None, str | None]:
    """(url, reason it cannot be used). Only open-access PDFs are fetched."""
    if not paper.is_open_access:
        return None, "not open access"
    if not paper.pdf_url:
        return None, "open access, but no PDF link provided by OpenAlex"
    return paper.pdf_url, None


def prepare_document(
    paper: Paper,
    fetcher: SafeFetcher,
    embedder: Embedder,
    *,
    allow_abstract_fallback_on_temporary_error: bool,
) -> PreparedDocument:
    """Fetch, extract, chunk, and embed. Raises TemporaryFetchError when a retry
    is worthwhile and the caller has attempts left."""
    url, reason = full_text_url(paper)
    if url:
        try:
            fetched = fetcher.fetch_pdf(url)
            pages, page_count = extract_pages(fetched.content)
            chunks = chunk_pages(pages)
            return PreparedDocument(
                "full_text", chunks, embedder.embed([c.text for c in chunks]), None, fetched,
                page_count,
            )  # fmt: skip
        except FetchDeferredError as exc:
            if not allow_abstract_fallback_on_temporary_error:
                raise TemporaryFetchError(str(exc), exc.wait_seconds) from exc
            reason = f"fetch deferred too often: {exc}"
        except FetchFailedError as exc:
            if not allow_abstract_fallback_on_temporary_error:
                raise TemporaryFetchError(str(exc)) from exc
            reason = f"fetch failed: {exc}"
        except (FetchRejectedError, ExtractionError) as exc:
            reason = f"full text not usable: {exc}"
    if paper.abstract:
        chunks = chunk_abstract(paper.abstract)
        return PreparedDocument(
            "abstract", chunks, embedder.embed([c.text for c in chunks]), reason, None, None
        )
    return PreparedDocument("none", [], [], f"{reason}; no abstract either", None, None)


def store_document(
    session: Session, paper_id: uuid.UUID, prepared: PreparedDocument, model_id: str
) -> PaperDocument:
    """Insert the document and its chunks in the caller's transaction."""
    fetched = prepared.fetched
    document = PaperDocument(
        paper_id=paper_id,
        content_kind=prepared.content_kind,
        full_text_unavailable_reason=prepared.unavailable_reason,
        source_url=fetched.source_url if fetched else None,
        final_url=fetched.final_url if fetched else None,
        sha256=fetched.sha256 if fetched else None,
        byte_size=len(fetched.content) if fetched else None,
        page_count=prepared.page_count,
        extractor=EXTRACTOR if fetched else "openalex-abstract",
        extractor_version=EXTRACTOR_VERSION if fetched else "pp1",
        fetched_at=datetime.now(UTC),
    )
    session.add(document)
    session.flush()
    session.add_all(
        PaperChunk(
            document_id=document.id,
            ordinal=chunk.ordinal,
            page_number=chunk.page_number,
            text=chunk.text,
            embedding=embedding,
            embedding_model=model_id,
        )
        for chunk, embedding in zip(prepared.chunks, prepared.embeddings, strict=True)
    )
    session.flush()
    return document


def get_document(session: Session, paper_id: uuid.UUID) -> PaperDocument | None:
    return session.scalar(select(PaperDocument).where(PaperDocument.paper_id == paper_id))
