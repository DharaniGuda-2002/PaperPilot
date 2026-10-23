"""Hybrid passage retrieval: Postgres full-text search + pgvector similarity,
combined with Reciprocal Rank Fusion (RRF).

RRF score = sum over methods of weight / (rrf_k + rank). It needs no score
calibration between methods, and a passage found by both ranks highest.
Every candidate records which method(s) found it and at what rank, so
evidence can say how its passage was retrieved.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

# Full-text query: OR over the question's stemmed words (AND would require every
# word of a long question to appear in one passage), ranked by cover density.
_FTS_SQL = text(
    """
    WITH q AS (
        SELECT to_tsquery('english', array_to_string(
                   tsvector_to_array(to_tsvector('english', :query)), ' | ')) AS query
    )
    SELECT c.id, ts_rank_cd(c.tsv, q.query) AS score
      FROM paper_chunks c
      JOIN paper_documents d ON d.id = c.document_id, q
     WHERE d.paper_id = ANY(:paper_ids)
       AND q.query IS NOT NULL
       AND c.tsv @@ q.query
     ORDER BY score DESC, c.id
     LIMIT :limit
    """
)

_VECTOR_SQL = text(
    """
    SELECT c.id, 1 - (c.embedding <=> CAST(:embedding AS vector)) AS score
      FROM paper_chunks c
      JOIN paper_documents d ON d.id = c.document_id
     WHERE d.paper_id = ANY(:paper_ids)
       AND c.embedding IS NOT NULL
       AND c.embedding_model = :model_id
     ORDER BY c.embedding <=> CAST(:embedding AS vector), c.id
     LIMIT :limit
    """
)

_CHUNKS_SQL = text(
    """
    SELECT c.id, c.document_id, d.paper_id, c.page_number, c.text
      FROM paper_chunks c JOIN paper_documents d ON d.id = c.document_id
     WHERE c.id = ANY(:ids)
    """
)


@dataclass(frozen=True)
class RetrievalConfig:
    fts_candidates: int = 20
    vector_candidates: int = 20
    limit: int = 12
    rrf_k: int = 60
    fts_weight: float = 1.0
    vector_weight: float = 1.0


@dataclass
class Candidate:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    paper_id: uuid.UUID
    page_number: int | None
    text: str
    score: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)  # method -> 1-based rank

    @property
    def method(self) -> str:
        return "+".join(sorted(self.ranks))  # 'fts', 'vector', or 'fts+vector'


def hybrid_search(
    session: Session,
    *,
    query: str,
    query_embedding: list[float],
    model_id: str,
    paper_ids: list[uuid.UUID],
    config: RetrievalConfig | None = None,
) -> list[Candidate]:
    config = config or RetrievalConfig()
    fts = session.execute(
        _FTS_SQL, {"query": query, "paper_ids": paper_ids, "limit": config.fts_candidates}
    ).all()
    vector = session.execute(
        _VECTOR_SQL,
        {
            "embedding": _vector_literal(query_embedding),
            "model_id": model_id,
            "paper_ids": paper_ids,
            "limit": config.vector_candidates,
        },
    ).all()

    fused: dict[uuid.UUID, tuple[float, dict[str, int]]] = {}
    for method, ranked, weight in (
        ("fts", fts, config.fts_weight),
        ("vector", vector, config.vector_weight),
    ):
        for rank, row in enumerate(ranked, start=1):
            score, ranks = fused.get(row.id, (0.0, {}))
            fused[row.id] = (score + weight / (config.rrf_k + rank), {**ranks, method: rank})

    top = sorted(fused.items(), key=lambda item: (-item[1][0], str(item[0])))[: config.limit]
    chunk_rows = session.execute(_CHUNKS_SQL, {"ids": [cid for cid, _ in top]}).all()
    rows = {r.id: r for r in chunk_rows}
    return [
        Candidate(
            chunk_id=chunk_id,
            document_id=rows[chunk_id].document_id,
            paper_id=rows[chunk_id].paper_id,
            page_number=rows[chunk_id].page_number,
            text=rows[chunk_id].text,
            score=score,
            ranks=ranks,
        )
        for chunk_id, (score, ranks) in top
    ]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in values) + "]"
