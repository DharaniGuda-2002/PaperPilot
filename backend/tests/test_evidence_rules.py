"""Rule extraction and validation on synthetic fixture sentences (not real papers)."""

import uuid
from typing import Any

import pytest

from app.evidence.models import EvidenceField
from app.evidence.rules import SourceChunk, extract
from app.evidence.validation import validate


def facts(text: str, page: int | None = 4) -> list[tuple[str, dict[str, Any]]]:
    chunk = SourceChunk(uuid.uuid4(), page, text, "fts", 0.03)
    return [(f.field.value, f.value) for f in extract([chunk])]


def values(text: str, field: EvidenceField) -> list[dict[str, Any]]:
    return [v for f, v in facts(text) if f == field.value]


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("The model reaches an AUC of 0.921 on the test set.", ("AUC", 0.921, "ratio")),
        ("It obtains 85.3% accuracy overall.", ("Accuracy", 85.3, "%")),
        ("We report F1-score: 0.84 for the fraud class.", ("F1", 0.84, "ratio")),
        ("Our AUC-PR is 0.41 under heavy imbalance.", ("AUC-PR", 0.41, "ratio")),
        ("ROC-AUC = 0.97 was achieved.", ("AUC-ROC", 0.97, "ratio")),
        ("Recall improves to 92.5 % on minority cases.", ("Recall", 92.5, "%")),
    ],
)
def test_metric_values_are_extracted(sentence: str, expected: tuple[str, float, str]) -> None:
    found = values(sentence, EvidenceField.METRIC_RESULT)
    assert [(v["metric"], v["value"], v["unit"]) for v in found] == [expected]


@pytest.mark.parametrize(
    "sentence",
    [
        "AUC was first used for this task in [12].",  # citation number
        "In 2020 the AUC metric became standard.",  # year, not a value
        "The AUC improved on 3000 transactions.",  # out of range without unit
    ],
)
def test_non_values_are_not_reported_as_metrics(sentence: str) -> None:
    assert values(sentence, EvidenceField.METRIC_RESULT) == []


def test_ambiguous_unit_is_extracted_but_fails_range_check() -> None:
    found = values("The F1 reaches 85.3 on the benchmark.", EvidenceField.METRIC_RESULT)
    assert found[0]["unit"] is None
    checks = validate(
        passage="The F1 reaches 85.3 on the benchmark.",
        chunk_text="The F1 reaches 85.3 on the benchmark.",
        chunk_page=1,
        claimed_page=1,
        document_page_count=3,
        value=found[0],
    )
    assert [c.rule for c in checks if not c.passed] == ["value_range"]


def test_baselines_are_the_methods_after_the_comparison_cue() -> None:
    sentence = "GraphConsis outperforms GCN and XGBoost on both datasets."
    assert [v["name"] for v in values(sentence, EvidenceField.BASELINE)] == ["GCN", "XGBoost"]
    named = "Logistic regression and random forest serve as baselines."
    assert [v["name"] for v in values(named, EvidenceField.BASELINE)] == [
        "Logistic regression",
        "Random forest",
    ]


def test_proposed_method_role() -> None:
    found = values("We propose a GNN that weighs neighbors by label.", EvidenceField.METHOD)
    assert found == [{"name": "GNN", "role": "proposed"}]


def test_datasets_from_lexicon_and_pattern() -> None:
    found = values(
        "We evaluate on the YelpChi dataset and the FraudX benchmark. The dataset is skewed.",
        EvidenceField.DATASET,
    )
    assert {"name": "YelpChi", "source": "lexicon"} in found
    assert {"name": "FraudX", "source": "pattern"} in found
    assert all(d["name"] != "The" for d in found)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("We use 5-fold cross-validation.", {"protocol": "k-fold cross-validation", "k": 5}),
        (
            "Data are split 70/10/20 for training.",
            {"protocol": "train/validation/test split", "train": 70, "valid": 10, "test": 20},
        ),
        (
            "We use 80% for training and 20% for testing.",
            {"protocol": "train/test split", "train": 80, "test": 20},
        ),
        ("We adopt a temporal split by month.", {"protocol": "temporal split"}),
        ("The training ratio is set to 40%.", {"protocol": "training ratio", "train": 40}),
    ],
)
def test_splits_and_protocols(sentence: str, expected: dict[str, Any]) -> None:
    found = values(sentence, EvidenceField.SPLIT)
    assert {k: v for k, v in found[0].items() if k != "raw"} == expected


def test_limitations_and_code_availability() -> None:
    text = (
        "A limitation is that we test only two datasets. "
        "Code will be made publicly available. "
        "See https://github.com/example/fixture-repo for details."
    )
    assert values(text, EvidenceField.LIMITATION)[0]["cue"] == "limitation"
    code = values(text, EvidenceField.CODE_AVAILABILITY)
    assert {"url": None, "statement": "will be available"} in code
    assert {"url": "https://github.com/example/fixture-repo", "statement": "available"} in code


def test_passages_are_exact_sentences_and_duplicates_removed() -> None:
    chunk_text = (
        "XGBoost is strong. XGBoost reaches an AUC of 0.88. XGBoost reaches an AUC of 0.88."
    )
    chunk = SourceChunk(uuid.uuid4(), 2, chunk_text, "fts+vector", 0.05)
    extracted = extract([chunk])
    metric = [f for f in extracted if f.field == EvidenceField.METRIC_RESULT]
    assert len(metric) == 1
    assert metric[0].passage == "XGBoost reaches an AUC of 0.88."
    assert metric[0].passage in chunk_text
    assert metric[0].value["method_hint"] == "XGBoost"


def test_validation_rejects_tampered_passage_and_wrong_page() -> None:
    value = {"metric": "AUC", "value": 0.92, "unit": "ratio"}
    good = dict(
        passage="It reaches an AUC of 0.92.",
        chunk_text="Intro. It reaches an AUC of 0.92.",
        chunk_page=3,
        claimed_page=3,
        document_page_count=8,
        value=value,
    )
    assert all(c.passed for c in validate(**good))  # type: ignore[arg-type]
    tampered = validate(**{**good, "passage": "It reaches an AUC of 0.99."})  # type: ignore[arg-type]
    assert {c.rule for c in tampered if not c.passed} == {"passage_in_source", "numbers_in_passage"}
    wrong_page = validate(**{**good, "claimed_page": 9})  # type: ignore[arg-type]
    assert [c.rule for c in wrong_page if not c.passed] == ["page_reference"]


def test_each_value_is_credited_to_the_method_before_it() -> None:
    """Regression: both values were credited to the sentence's first method."""
    sentence = "The GNN reaches an AUC of 0.921, while XGBoost reaches an AUC of 0.883."
    found = values(sentence, EvidenceField.METRIC_RESULT)
    assert [(v["method_hint"], v["value"]) for v in found] == [("GNN", 0.921), ("XGBoost", 0.883)]
