"""Comparability rules on synthetic fixture evidence (not real papers)."""

import uuid

from app.comparison.rules import (
    W_ABSTRACT_ONLY,
    W_DATASETS_UNATTRIBUTED,
    W_NO_PROTOCOL,
    EvidenceInput,
    PaperInput,
    compare,
)


def paper(title: str, kind: str = "full_text") -> PaperInput:
    return PaperInput(uuid.uuid4(), title, 2024, kind)


def ev(
    p: PaperInput,
    field: str,
    value: dict[str, object] | None = None,
    passage: str = "x",
    status: str = "reported",
) -> EvidenceInput:
    return EvidenceInput(
        uuid.uuid4(), p.paper_id, field, status, value, passage if value is not None else None, 3
    )


def result(
    p: PaperInput, metric: str, value: float, unit: str | None, method: str
) -> EvidenceInput:
    return ev(
        p, "metric_result", {"metric": metric, "value": value, "unit": unit, "method_hint": method}
    )


def test_same_metric_dataset_and_protocol_form_one_group_on_a_common_scale() -> None:
    a, b = paper("A"), paper("B")
    evidence = [
        ev(a, "dataset", {"name": "YelpChi"}),
        ev(a, "split", {"protocol": "k-fold cross-validation", "k": 5}),
        result(a, "AUC", 0.91, "ratio", "GNN"),
        ev(b, "dataset", {"name": "YelpChi"}),
        ev(b, "split", {"protocol": "k-fold cross-validation", "k": 5}),
        result(b, "AUC", 93.0, "%", "XGBoost"),
    ]
    comparison = compare([a, b], evidence)
    [group] = comparison.groups
    assert (group.metric, group.dataset, group.protocol) == (
        "AUC",
        "YelpChi",
        "5-fold cross-validation",
    )
    assert [(m.method, m.normalized) for m in group.members] == [("XGBoost", 0.93), ("GNN", 0.91)]
    assert group.paper_count == 2
    assert comparison.not_comparable == []


def test_different_datasets_or_protocols_never_share_a_group() -> None:
    a, b, c = paper("A"), paper("B"), paper("C")
    evidence = [
        ev(a, "dataset", {"name": "YelpChi"}),
        ev(a, "split", {"protocol": "temporal split"}),
        result(a, "AUC", 0.9, "ratio", "GNN"),
        ev(b, "dataset", {"name": "Amazon (fraud)"}),
        ev(b, "split", {"protocol": "temporal split"}),
        result(b, "AUC", 0.8, "ratio", "GNN"),
        ev(c, "dataset", {"name": "YelpChi"}),
        ev(c, "split", {"protocol": "k-fold cross-validation", "k": 10}),
        result(c, "AUC", 0.7, "ratio", "GNN"),
    ]
    groups = compare([a, b, c], evidence).groups
    assert len(groups) == 3
    assert all(g.paper_count == 1 for g in groups)


def test_unattributable_or_unitless_results_are_listed_with_reasons() -> None:
    multi, no_protocol, no_unit = paper("Multi"), paper("NoProtocol"), paper("NoUnit")
    evidence = [
        ev(multi, "dataset", {"name": "YelpChi"}),
        ev(multi, "dataset", {"name": "Amazon (fraud)"}),
        ev(multi, "split", {"protocol": "temporal split"}),
        result(multi, "F1", 0.8, "ratio", "GNN"),
        ev(no_protocol, "dataset", {"name": "YelpChi"}),
        result(no_protocol, "F1", 0.7, "ratio", "GNN"),
        ev(no_unit, "dataset", {"name": "YelpChi"}),
        ev(no_unit, "split", {"protocol": "temporal split"}),
        result(no_unit, "F1", 85.3, None, "GNN"),
    ]
    comparison = compare([multi, no_protocol, no_unit], evidence)
    assert comparison.groups == []
    reasons = {nc.paper_id: nc.reasons for nc in comparison.not_comparable}
    assert reasons[multi.paper_id] == ["paper reports several datasets; value not tied to one"]
    assert reasons[no_protocol.paper_id] == ["evaluation protocol not reported"]
    assert reasons[no_unit.paper_id] == ["unit or scale not stated"]
    rows = {r.paper_id: r for r in comparison.matrix}
    assert W_DATASETS_UNATTRIBUTED in rows[multi.paper_id].warnings
    assert W_NO_PROTOCOL in rows[no_protocol.paper_id].warnings


def test_claims_and_conflicts_come_from_author_sentences() -> None:
    a, b = paper("A"), paper("B")
    evidence = [
        ev(
            a,
            "baseline",
            {"name": "XGBoost", "cue": "outperforms"},
            "Our GNN outperforms XGBoost on YelpChi.",
        ),
        ev(
            b,
            "baseline",
            {"name": "GNN", "cue": "outperforms"},
            "XGBoost outperforms the GNN in our setting.",
        ),
        ev(
            b,
            "baseline",
            {"name": "Random forest", "cue": "baselines"},
            "Random forest serves as one of the baselines.",
        ),
    ]
    comparison = compare([a, b], evidence)
    assert {(c.better, c.worse) for c in comparison.claims} == {
        ("GNN", "XGBoost"),
        ("XGBoost", "GNN"),
    }
    assert comparison.conflicts == [("GNN", "XGBoost")]


def test_rows_report_text_availability_and_missing_fields() -> None:
    abstract_only = paper("Abstract", kind="abstract")
    evidence = [
        ev(abstract_only, "method", {"name": "GNN", "role": "proposed"}),
        ev(abstract_only, "split", None, status="unavailable"),
        ev(abstract_only, "dataset", None, status="unavailable"),
    ]
    [row] = compare([abstract_only], evidence).matrix
    assert row.proposed_methods == ["GNN"]
    assert row.missing_fields == ["dataset", "split"]
    assert W_ABSTRACT_ONLY in row.warnings


def test_split_labels_quote_the_paper_instead_of_adding_units() -> None:
    """Regression: a "6:2:2" ratio was shown as "train 6%, valid 2%, test 2%"."""
    a, b = paper("A"), paper("B")
    split = {"protocol": "train/validation/test split", "train": 6, "valid": 2, "test": 2}
    evidence = [
        ev(a, "split", {**split, "raw": "6:2:2 "}),
        ev(b, "split", {**split, "raw": "60%/20%/20%"}),
    ]
    rows = {r.title: r for r in compare([a, b], evidence).matrix}
    assert rows["A"].protocols == ["train/validation/test split (6:2:2)"]
    assert rows["B"].protocols == ["train/validation/test split (60%/20%/20%)"]
