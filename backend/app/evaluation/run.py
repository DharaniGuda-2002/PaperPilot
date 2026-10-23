"""Score retrieval and extraction against the manually reviewed gold set.

Read-only: it re-runs passage retrieval and rule extraction on the stored
papers in memory and writes nothing to the database. Needs the ml image (the
embedding model) and a database holding the gold papers' documents.

    python -m app.evaluation.run --gold /evaluation/gold/rag-hallucination-v1.json \
        --out /evaluation/results/rag-hallucination-v1.json
    python -m app.evaluation.run --gold ... --list-unjudged   # records needing a verdict

Metrics:
  - Retrieval Recall@K: for each gold fact, its field's query (the one the
    pipeline uses) is run against the fact's paper; a hit means a chunk that
    contains the fact's anchor is in the top K. Run for full-text search only,
    vector search only, and the hybrid (RRF) the pipeline uses.
  - Pipeline coverage: the anchor chunk is among the passages the extractor
    actually received (union over all pipeline queries).
  - Extraction recall per field: gold facts matched by an extracted record.
  - Extraction precision per field: extracted records that match gold or were
    judged correct by hand; records nobody judged are reported, not guessed.
  - Passage validity: extracted records whose quotation passed every check.
"""

import argparse
import json
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import create_db_engine, create_session_factory
from app.documents.models import PaperChunk, PaperDocument
from app.evaluation.gold import (
    SCORED_FIELDS,
    Extracted,
    GoldPaper,
    GoldSet,
    PaperResult,
    anchor_chunks,
    field_scores,
    load_gold,
    load_judgements,
    score_paper,
)
from app.evidence.models import ValidationStatus
from app.evidence.rules import EXTRACTION_VERSION, FIELD_QUERIES
from app.evidence.service import PASSAGES_PER_QUERY, build_evidence, gather_sources, query_texts
from app.evidence.validation import VALIDATOR_VERSION
from app.papers.models import Paper
from app.retrieval.embeddings import Embedder, make_embedder
from app.retrieval.hybrid import RetrievalConfig, hybrid_search

K_VALUES = (1, 3, 5, PASSAGES_PER_QUERY)
RETRIEVERS = {
    # Same candidate pools as the pipeline; the single-method runs drop the other list.
    "fts": RetrievalConfig(vector_candidates=0, limit=max(K_VALUES)),
    "vector": RetrievalConfig(fts_candidates=0, limit=max(K_VALUES)),
    "hybrid": RetrievalConfig(limit=max(K_VALUES)),
}


def evaluate(
    session: Session, gold: GoldSet, embedder: Embedder, judgements: dict[str, bool]
) -> dict[str, Any]:
    queries = query_texts(gold.question)
    embeddings = dict(zip(queries, embedder.embed(queries), strict=True))
    field_query = {f.value: FIELD_QUERIES[f] for f in FIELD_QUERIES}

    retrieval_hits = {m: {k: 0 for k in K_VALUES} for m in RETRIEVERS}
    retrieval_by_field: dict[str, dict[str, int]] = {}
    coverage = 0
    facts_total = 0
    results: list[PaperResult] = []
    papers: list[GoldPaper] = []
    missing_anchors: list[str] = []

    for paper in gold.papers:
        row = session.execute(
            select(Paper, PaperDocument)
            .join(PaperDocument, PaperDocument.paper_id == Paper.id)
            .where(Paper.doi == paper.doi)
        ).first()
        if row is None or row[1].content_kind != "full_text":
            raise SystemExit(f"{paper.doi}: no stored full text; process the paper first")
        stored, document = row
        chunks = {
            str(c.id): c.text
            for c in session.scalars(
                select(PaperChunk).where(PaperChunk.document_id == document.id)
            )
        }
        chunk_index = [anchor_chunks(fact, chunks) for fact in paper.facts]
        for fact, found in zip(paper.facts, chunk_index, strict=True):
            if not found:
                missing_anchors.append(f"{paper.doi} {fact.field}: {fact.anchors[0]!r}")
        if missing_anchors:
            continue

        sources = gather_sources(
            session,
            paper_id=stored.id,
            queries=queries,
            query_embeddings=[embeddings[q] for q in queries],
            model_id=embedder.model_id,
        )
        seen = {str(s.chunk_id) for s in sources}

        for fact, gold_chunks in zip(paper.facts, chunk_index, strict=True):
            facts_total += 1
            coverage += bool(gold_chunks & seen)
            per_field = retrieval_by_field.setdefault(fact.field, {"facts": 0, "hybrid@8": 0})
            per_field["facts"] += 1
            query = field_query[fact.field]
            for method, config in RETRIEVERS.items():
                ranked = [
                    str(c.chunk_id)
                    for c in hybrid_search(
                        session,
                        query=query,
                        query_embedding=embeddings[query],
                        model_id=embedder.model_id,
                        paper_ids=[stored.id],
                        config=config,
                    )
                ]
                for k in K_VALUES:
                    if gold_chunks & set(ranked[:k]):
                        retrieval_hits[method][k] += 1
                        if method == "hybrid" and k == max(K_VALUES):
                            per_field["hybrid@8"] += 1

        batch = build_evidence(
            investigation_id=uuid.uuid4(),
            paper_id=stored.id,
            content_kind=document.content_kind,
            page_count=document.page_count,
            sources=sources,
        )
        records = [
            Extracted(
                field=str(r.field),
                value=dict(r.value or {}),
                page=r.page_number,
                chunk_id=str(r.chunk_id),
                passage=r.passage or "",
                verified=r.validation_status == ValidationStatus.VERIFIED,
            )
            for r in batch.reported
            if str(r.field) in SCORED_FIELDS
        ]
        results.append(score_paper(paper, records, chunk_index, judgements))
        papers.append(paper)

    if missing_anchors:
        raise SystemExit("Anchors not found in stored text:\n  " + "\n  ".join(missing_anchors))

    scores = field_scores(papers, results)
    all_records = [v for r in results for v in r.verdicts]
    return {
        "set": gold.name,
        "annotator": gold.annotator,
        "review_status": gold.review_status,
        "reviewed_by": gold.reviewed_by,
        "reviewed_on": gold.reviewed_on,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "versions": {
            "extraction": EXTRACTION_VERSION,
            "validation": VALIDATOR_VERSION,
            "embedding_model": embedder.model_id,
            "retrieval": {m: asdict(c) for m, c in RETRIEVERS.items()},
        },
        "papers": len(papers),
        "gold_facts": facts_total,
        "retrieval_recall_at_k": {
            m: {str(k): round(hits / facts_total, 3) for k, hits in by_k.items()}
            for m, by_k in retrieval_hits.items()
        },
        "retrieval_hybrid_at_8_by_field": retrieval_by_field,
        "pipeline_coverage": round(coverage / facts_total, 3),
        "extraction": {
            name: {
                "gold": s.gold,
                "found": s.found,
                "recall": _round(s.recall),
                "extracted": s.extracted,
                "correct": s.correct,
                "unjudged": s.unjudged,
                "precision": _round(s.precision),
            }
            for name, s in scores.items()
        },
        "passage_validity": {
            "records": len(all_records),
            "verified": sum(rec.verified for rec, _, _ in all_records),
        },
        "unjudged": [
            {"key": key, "page": rec.page, "passage": rec.passage}
            for rec, verdict, key in all_records
            if verdict is None
        ],
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def print_summary(report: dict[str, Any]) -> None:
    print(f"{report['set']}: {report['papers']} papers, {report['gold_facts']} gold facts")
    print("Retrieval Recall@K   " + "  ".join(f"@{k:<5}" for k in K_VALUES))
    for method, by_k in report["retrieval_recall_at_k"].items():
        print(f"  {method:<18} " + "  ".join(f"{v:<6.3f}" for v in by_k.values()))
    print(f"Pipeline coverage: {report['pipeline_coverage']:.3f}")
    print("Field              gold found recall  extracted correct unjudged precision")
    for name, s in report["extraction"].items():
        print(
            f"  {name:<17} {s['gold']:>4} {s['found']:>5} {_fmt(s['recall'])}"
            f"  {s['extracted']:>9} {s['correct']:>7} {s['unjudged']:>8} {_fmt(s['precision'])}"
        )
    validity = report["passage_validity"]
    print(f"Passage validity: {validity['verified']}/{validity['records']} verified")


def _fmt(value: float | None) -> str:
    return "     -" if value is None else f"{value:6.3f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--judgements", type=Path, help="defaults to <gold>.judgements.json")
    parser.add_argument("--out", type=Path, help="write the full result as JSON")
    parser.add_argument("--list-unjudged", action="store_true")
    args = parser.parse_args(argv)

    gold = load_gold(args.gold)
    judgements_path = args.judgements or args.gold.with_suffix(".judgements.json")
    settings = get_settings()
    sessions = create_session_factory(create_db_engine(settings))
    embedder = make_embedder(settings.embedding_provider)
    with sessions() as session:
        try:
            report = evaluate(session, gold, embedder, load_judgements(judgements_path))
        finally:
            session.rollback()  # nothing is written; make that explicit

    if args.list_unjudged:
        for item in report["unjudged"]:
            print(f"\n{item['key']}\n  p{item['page']}: {item['passage']}")
        return 0
    print_summary(report)
    if args.out:
        # Passages stay out of the committed result; keys identify the records.
        public = {**report, "unjudged": [item["key"] for item in report["unjudged"]]}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(public, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
