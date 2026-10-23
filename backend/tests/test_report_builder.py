"""Report generation on synthetic fixture evidence (not real papers)."""

import uuid

import pytest

from app.comparison.rules import EvidenceInput, PaperInput, compare
from app.reports.builder import build_report, strength_for
from app.reports.schemas import FindingKind, PaperRef, Strength

QUESTION = "Do graph neural networks outperform gradient boosting for fraud detection?"


@pytest.mark.parametrize(
    ("full", "abstract", "conflicting", "expected"),
    [
        (3, 0, 0, Strength.STRONG),
        (3, 0, 1, Strength.MODERATE),
        (2, 0, 0, Strength.MODERATE),
        (1, 1, 0, Strength.MODERATE),
        (2, 0, 1, Strength.LIMITED),
        (1, 0, 0, Strength.LIMITED),
        (0, 3, 0, Strength.LIMITED),
        (0, 0, 0, Strength.INSUFFICIENT),
        (1, 0, 2, Strength.INSUFFICIENT),
    ],
)
def test_strength_follows_published_definitions(
    full: int, abstract: int, conflicting: int, expected: Strength
) -> None:
    assert strength_for(full, abstract, conflicting)[0] == expected


def paper(title: str, kind: str = "full_text") -> PaperInput:
    return PaperInput(uuid.uuid4(), title, 2024, kind)


def ref(p: PaperInput) -> PaperRef:
    return PaperRef(
        paper_id=p.paper_id, title=p.title, authors=["Fixture Author"], year=p.year,
        venue=None, doi=None, url=None, content_kind=p.content_kind,
    )  # fmt: skip


def ev(
    p: PaperInput, field: str, value: dict[str, object] | None, passage: str | None = "x"
) -> EvidenceInput:
    return EvidenceInput(
        uuid.uuid4(),
        p.paper_id,
        field,
        "reported" if value else "not_found",
        value,
        passage if value else None,
        2,
    )


def claim(p: PaperInput, sentence: str, baseline: str) -> EvidenceInput:
    return ev(p, "baseline", {"name": baseline, "cue": "outperforms"}, sentence)


def build(papers: list[PaperInput], evidence: list[EvidenceInput]):  # type: ignore[no-untyped-def]
    return build_report(
        question=QUESTION,
        papers=[ref(p) for p in papers],
        papers_discovered=len(papers),
        comparison=compare(papers, evidence),
        versions={"extraction": "rules-v2"},
    )


def test_claims_about_question_methods_lead_with_strength_and_conflicts() -> None:
    a, b, c, d = paper("A"), paper("B"), paper("C"), paper("D", kind="abstract")
    evidence = [
        claim(a, "Our GCN outperforms XGBoost on YelpChi.", "XGBoost"),
        claim(b, "GraphSAGE outperforms LightGBM in all settings.", "LightGBM"),
        claim(c, "XGBoost outperforms the GAT model here.", "GAT"),
        claim(d, "The GNN outperforms CatBoost.", "CatBoost"),
        claim(a, "Our GCN outperforms logistic regression.", "Logistic regression"),
    ]
    report = build([a, b, c, d], evidence)
    top = report.key_findings[0]
    assert top.kind == FindingKind.CLAIM
    assert top.title == "Graph neural networks reported to outperform Gradient-boosted trees"
    assert {s.title for s in top.supporting} == {"A", "B", "D"}
    assert [s.title for s in top.conflicting] == ["C"]
    # 2 full-text + 1 abstract supporters, 1 conflicting: moderate, downgraded to limited.
    assert top.strength == Strength.LIMITED
    assert "1 paper reports the opposite" in (top.strength_reason or "")
    assert report.bottom_line.startswith(
        "3 of 4 analyzed papers report Graph neural networks outperforming Gradient-boosted trees, "
        "while 1 reports the opposite."
    )
    assert report.bottom_line.endswith("it does not establish which method is better.")
    assert any("conflict" in q or "disagree" in q for q in report.unresolved_questions)


def test_comparable_groups_become_findings_with_value_ranges() -> None:
    papers = [paper(name) for name in "ABC"]
    evidence = []
    for p, value in zip(papers, (0.91, 0.88, 0.95), strict=True):
        evidence += [
            ev(p, "dataset", {"name": "YelpChi"}),
            ev(p, "split", {"protocol": "temporal split"}),
            ev(
                p,
                "metric_result",
                {"metric": "AUC", "value": value, "unit": "ratio", "method_hint": "GNN"},
            ),
        ]
    report = build(papers, evidence)
    comparison = next(f for f in report.key_findings if f.kind == FindingKind.COMPARISON)
    assert comparison.title == "Comparable AUC results on YelpChi"
    assert "range from 0.88 to 0.95" in comparison.summary
    assert "not reproduced" in comparison.summary
    assert comparison.strength == Strength.STRONG
    assert report.overall_strength == Strength.STRONG


def test_no_evidence_gives_insufficient_report_with_caveats() -> None:
    a = paper("A", kind="abstract")
    report = build([a], [ev(a, "metric_result", None)])
    assert report.overall_strength == Strength.INSUFFICIENT
    assert report.key_findings[0].id == "caveat-no-results"
    assert report.bottom_line.startswith("The analyzed papers contain no explicit claims")
    assert report.scope.abstract_only == 1
    assert any("abstract" in item for item in report.limitations)


def test_findings_are_capped_and_related_by_shared_papers() -> None:
    a, b = paper("A"), paper("B")
    evidence = [
        claim(a, "Our GCN outperforms XGBoost.", "XGBoost"),
        claim(a, "Our GCN outperforms random forest.", "Random forest"),
        claim(b, "BERT outperforms LSTM baselines.", "LSTM"),
        ev(a, "metric_result", {"metric": "F1", "value": 85.3, "unit": None, "method_hint": "GCN"}),
        ev(a, "limitation", {"cue": "limitation", "statement": "limitation"}),
    ]
    report = build([a, b], evidence)
    assert 3 <= len(report.key_findings) <= 5
    ids = {f.id: f for f in report.key_findings}
    assert "caveat-comparability" in ids
    assert "claim-1" in ids["caveat-comparability"].related  # both cite paper A
    assert all(f.strength is None for f in report.key_findings if f.kind == FindingKind.CAVEAT)


def test_partial_text_coverage_is_always_a_visible_caveat() -> None:
    full, abstract, none = paper("Full"), paper("Abs", kind="abstract"), paper("None", kind="none")
    report = build([full, abstract, none], [])
    coverage = next(f for f in report.key_findings if f.id == "caveat-coverage")
    assert coverage.summary.startswith(
        "2 papers could not be read in full: 1 as abstracts only and 1 with no text"
    )
    assert len(report.key_findings) >= 3


def test_preprint_and_published_version_count_as_one_study() -> None:
    """Regression: an arXiv preprint and its conference version (different DOIs,
    same title) were counted as two papers, inflating evidence strength."""
    from datetime import UTC, datetime

    from app.papers.models import Paper
    from app.reports.service import distinct_works

    def make(title: str, doi: str) -> Paper:
        return Paper(
            id=uuid.uuid4(), provider="fixture", provider_id=doi, doi=doi, title=title, authors=[],
            is_open_access=True, metadata_fetched_at=datetime.now(UTC),
        )  # fmt: skip

    published = make("Generation-Augmented Retrieval for Open-Domain QA", "10.1/acl")
    preprint = make("Generation-Augmented Retrieval for Open-domain QA", "10.48550/arxiv.1")
    other = make("A different study", "10.1/other")
    rows: list[tuple[Paper, str | None]] = [
        (published, "abstract"),
        (preprint, "full_text"),
        (other, None),
    ]
    kept, merged = distinct_works(rows)
    assert merged == 1
    assert [p.doi for p, _ in kept] == ["10.48550/arxiv.1", "10.1/other"]  # full-text version kept


def test_bottom_line_does_not_lead_with_claims_unrelated_to_the_question() -> None:
    a = paper("A")
    report = build_report(
        question="Does retrieval-augmented generation reduce hallucination in QA?",
        papers=[ref(a)],
        papers_discovered=1,
        comparison=compare([a], [claim(a, "Again, GAR outperforms BM25 everywhere.", "BM25")]),
        versions={"extraction": "rules-v2"},
    )
    assert report.bottom_line.startswith(
        "None of the analyzed papers explicitly compares Retrieval-augmented generation with "
        "another method; 1 other comparison between methods is listed below."
    )
    assert report.key_findings[0].title == "GAR reported to outperform BM25"  # still reported
