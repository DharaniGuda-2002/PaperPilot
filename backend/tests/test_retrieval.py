"""Hybrid retrieval against real Postgres + pgvector, using the deterministic
hashing embedder and synthetic fixture passages (not real papers)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.documents.service import PreparedDocument, store_document
from app.documents.text import Chunk
from app.papers.models import Paper
from app.retrieval.embeddings import HashingEmbedder
from app.retrieval.hybrid import Candidate, RetrievalConfig, hybrid_search

PASSAGES = [
    "Introduction: fraud costs banks billions every year.",
    "The graph neural network achieves an AUC of 0.92 on the fixture fraud dataset.",
    "We thank the reviewers for helpful comments.",
    "Gradient boosting baselines reach an AUC of 0.88 under the same split.",
]


def add_paper(session: Session, passages: list[str]) -> uuid.UUID:
    paper = Paper(
        provider="fixture",
        provider_id=uuid.uuid4().hex[:12],
        title="Fixture paper",
        authors=[],
        is_open_access=True,
        metadata_fetched_at=datetime.now(UTC),
    )
    session.add(paper)
    session.flush()
    embedder = HashingEmbedder()
    chunks = [Chunk(i, i + 1, text) for i, text in enumerate(passages)]
    store_document(
        session,
        paper.id,
        PreparedDocument("full_text", chunks, embedder.embed(passages), None, None, len(passages)),
        embedder.model_id,
    )
    return paper.id


def search(
    session: Session, query: str, paper_ids: list[uuid.UUID], **config: float
) -> list[Candidate]:
    embedder = HashingEmbedder()
    return hybrid_search(
        session,
        query=query,
        query_embedding=embedder.embed([query])[0],
        model_id=embedder.model_id,
        paper_ids=paper_ids,
        config=RetrievalConfig(**config),  # type: ignore[arg-type]  # int fields accept floats here
    )


def test_ranks_relevant_passages_first_and_records_methods(engine: Engine) -> None:
    with sessionmaker(bind=engine)() as session:
        paper = add_paper(session, PASSAGES)
        results = search(session, "graph neural network AUC fraud dataset", [paper])
        session.rollback()

    assert results[0].text == PASSAGES[1]
    assert results[0].method == "fts+vector"
    assert results[0].ranks == {"fts": 1, "vector": 1}
    assert results[0].page_number == 2
    assert PASSAGES[2] not in [r.text for r in results[:2]]
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


def test_only_searches_the_given_papers(engine: Engine) -> None:
    with sessionmaker(bind=engine)() as session:
        mine = add_paper(session, ["Fraud detection with graphs."])
        other = add_paper(session, ["Fraud detection with graphs, in another paper."])
        results = search(session, "fraud detection graphs", [mine])
        session.rollback()
    assert {r.paper_id for r in results} == {mine}
    assert other not in {r.paper_id for r in results}


def test_vector_only_candidates_are_labeled(engine: Engine) -> None:
    """A query whose words never appear verbatim can still be found by the
    vector side; its method says so."""
    with sessionmaker(bind=engine)() as session:
        paper = add_paper(session, PASSAGES)
        results = search(session, "zzz unrelated tokens", [paper], limit=4)
        session.rollback()
    assert results
    assert all(r.method == "vector" for r in results)


def test_limit_and_weights_are_configurable(engine: Engine) -> None:
    with sessionmaker(bind=engine)() as session:
        paper = add_paper(session, PASSAGES)
        only_fts = search(session, "AUC split baselines", [paper], vector_weight=0.0, limit=1)
        session.rollback()
    assert len(only_fts) == 1
    assert only_fts[0].text == PASSAGES[3]
