"""Time hybrid retrieval (FTS + pgvector + RRF) as the evidence worker runs it.

For every full-text paper of an investigation, runs each pipeline query
(question + one per field) through hybrid_search and records wall time per
call. Query embeddings are computed once beforehand, so the numbers are the
database side only. Read-only.

    python -m app.evaluation.retrieval_latency <investigation_id> [--repeat 3]
"""

import argparse
import statistics
import sys
import time
import uuid

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.documents.models import PaperChunk, PaperDocument
from app.evidence.service import PASSAGES_PER_QUERY, query_texts
from app.investigations.models import Investigation, InvestigationPaper
from app.retrieval.embeddings import make_embedder
from app.retrieval.hybrid import RetrievalConfig, hybrid_search


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("investigation_id", type=uuid.UUID)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args(argv)

    settings = get_settings()
    sessions = create_session_factory(create_db_engine(settings))
    embedder = make_embedder(settings.embedding_provider)
    with sessions() as session:
        investigation = session.get(Investigation, args.investigation_id)
        if investigation is None:
            raise SystemExit("investigation not found")
        queries = query_texts(investigation.question)
        embeddings = embedder.embed(queries)
        papers = session.scalars(
            select(PaperDocument.paper_id)
            .join(InvestigationPaper, InvestigationPaper.paper_id == PaperDocument.paper_id)
            .where(
                InvestigationPaper.investigation_id == investigation.id,
                PaperDocument.content_kind == "full_text",
            )
        ).all()
        chunks = session.scalar(
            select(func.count(PaperChunk.id))
            .join(PaperDocument, PaperDocument.id == PaperChunk.document_id)
            .where(PaperDocument.paper_id.in_(papers))
        )
        timings: list[float] = []
        config = RetrievalConfig(limit=PASSAGES_PER_QUERY)
        for _ in range(args.repeat):
            for paper_id in papers:
                for query, embedding in zip(queries, embeddings, strict=True):
                    started = time.perf_counter()
                    hybrid_search(
                        session,
                        query=query,
                        query_embedding=embedding,
                        model_id=embedder.model_id,
                        paper_ids=[paper_id],
                        config=config,
                    )
                    timings.append((time.perf_counter() - started) * 1000)
        session.rollback()

    timings.sort()

    def pick(q: float) -> float:
        return timings[min(len(timings) - 1, round(q * (len(timings) - 1)))]

    print(
        f"{len(papers)} papers ({chunks} chunks) x {len(queries)} queries x {args.repeat} = "
        f"{len(timings)} calls: p50 {pick(0.5):.1f} ms, p95 {pick(0.95):.1f} ms, "
        f"max {timings[-1]:.1f} ms, mean {statistics.fmean(timings):.1f} ms"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
