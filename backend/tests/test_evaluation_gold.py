import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from app.evaluation.gold import (
    Extracted,
    GoldFact,
    GoldPaper,
    anchor_chunks,
    field_scores,
    judgement_key,
    load_gold,
    load_judgements,
    matches,
    name_matches,
    score_paper,
)

GOLD_DIR = Path(__file__).resolve().parents[2] / "evaluation" / "gold"


def record(
    field: str, value: dict[str, Any], page: int = 3, chunk: str = "c1", passage: str = "p"
) -> Extracted:
    return Extracted(
        field=field, value=value, page=page, chunk_id=chunk, passage=passage, verified=True
    )


def fact(
    field: str,
    value: object = "x",
    pages: Sequence[int] = (3,),
    aliases: Sequence[str] = (),
    anchors: Sequence[str] = ("anchor",),
) -> GoldFact:
    return GoldFact(
        field=field, value=value, pages=tuple(pages), anchors=tuple(anchors), aliases=tuple(aliases)
    )


def test_anchor_search_ignores_case_whitespace_and_typography() -> None:
    chunks = {"a": "We  use the model\u2019s\nown \u2013 split.", "b": "unrelated"}
    assert anchor_chunks(fact("split", anchors=["the MODEL'S own - split"]), chunks) == {"a"}


def test_short_aliases_must_match_exactly() -> None:
    assert name_matches("NQ", ("nq",))
    assert not name_matches("NQ-Open variant", ("nq",))
    assert not name_matches("GPT", ("gpt-4",))  # 'GPT' alone does not identify GPT-4
    assert name_matches("Self-RAG 7B", ("self-rag",))
    assert name_matches("TriviaQA", ("triviaqa",))


def test_name_fields_need_page_and_alias() -> None:
    gold = fact("dataset", aliases=["triviaqa"], pages=[6])
    assert matches(record("dataset", {"name": "TriviaQA"}, page=6), gold, set())
    assert not matches(record("dataset", {"name": "TriviaQA"}, page=2), gold, set())
    assert not matches(record("baseline", {"name": "TriviaQA"}, page=6), gold, set())


def test_metric_values_match_within_rounding() -> None:
    gold = fact("metric_result", value=0.87, pages=[2])
    assert matches(record("metric_result", {"value": 0.870}, page=2), gold, set())
    assert not matches(record("metric_result", {"value": 0.89}, page=2), gold, set())
    assert not matches(record("metric_result", {"value": None}, page=2), gold, set())


def test_statement_fields_match_by_anchor_chunk() -> None:
    gold = fact("limitation")
    assert matches(record("limitation", {}, chunk="c9"), gold, {"c9"})
    assert not matches(record("limitation", {}, chunk="c1"), gold, {"c9"})


def test_scores_use_gold_matches_then_judgements_and_report_unjudged() -> None:
    paper = GoldPaper(
        doi="10.1/x",
        title="T",
        facts=(fact("dataset", aliases=["squad"]), fact("baseline", aliases=["bm25"])),
        absent=(),
    )
    hit = record("dataset", {"name": "SQuAD"})
    wrong = record("baseline", {"name": "RAG"}, passage="RAG beats the baseline.")
    unknown = record("baseline", {"name": "CNN"}, passage="CNN/DM subtask.")
    judgements = {judgement_key("10.1/x", wrong): False}

    result = score_paper(paper, [hit, wrong, unknown], [set(), set()], judgements)
    scores = field_scores([paper], [result])

    assert result.found == [True, False]
    assert (scores["dataset"].recall, scores["dataset"].precision) == (1.0, 1.0)
    baseline = scores["baseline"]
    assert (baseline.gold, baseline.found, baseline.extracted) == (1, 0, 2)
    assert baseline.unjudged == 1  # never counted as right or wrong
    assert baseline.precision == 0.0


def test_load_gold_rejects_long_anchors(tmp_path: Path) -> None:
    raw = {
        "set": "s", "question": "q", "annotator": "a", "review_status": "r",
        "papers": [{"doi": "d", "title": "t", "facts": [
            {"field": "split", "value": "v", "pages": [1], "anchors": [" ".join(["word"] * 15)]}
        ]}],
    }  # fmt: skip
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="anchors"):
        load_gold(path)


def test_committed_gold_set_is_well_formed() -> None:
    gold = load_gold(GOLD_DIR / "rag-hallucination-v1.json")
    assert gold.review_status == "pending human review"
    dois = {p.doi for p in gold.papers}
    assert len(dois) == len(gold.papers) == 5
    judgements = load_judgements(GOLD_DIR / "rag-hallucination-v1.judgements.json")
    assert judgements and all(key.split("|")[0] in dois for key in judgements)
