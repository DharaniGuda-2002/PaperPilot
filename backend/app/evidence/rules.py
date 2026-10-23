"""Rule-based evidence extraction (rules-v1).

Each fact is tied to the exact sentence it came from: the sentence is taken
verbatim from the stored chunk text, never rewritten. Rules are deliberately
conservative; recall is measured, not assumed (see docs/evaluation).

Untrusted input: paper text is only matched against patterns; it never
changes what the extractor does.
"""

import re
import uuid
from dataclasses import dataclass
from typing import Any

from app.documents.text import split_sentences
from app.evidence.models import EvidenceField

EXTRACTION_METHOD = "rules"
EXTRACTION_VERSION = "rules-v1"

# Field-specific retrieval queries, searched alongside the research question.
FIELD_QUERIES: dict[EvidenceField, str] = {
    EvidenceField.METRIC_RESULT: "results AUC F1 accuracy precision recall outperforms baseline",
    EvidenceField.DATASET: "dataset datasets benchmark data collected experiments",
    EvidenceField.SPLIT: "train test split cross-validation training validation testing protocol",
    EvidenceField.BASELINE: "baselines compared with compared against outperform methods",
    EvidenceField.LIMITATION: "limitation limitations future work fails does not generalize",
    EvidenceField.CODE_AVAILABILITY: "code available github implementation released",
}

_METRICS = {
    "AUC-ROC": r"AUC[- ]?ROC|ROC[- ]?AUC|AUROC",
    "AUC-PR": r"AUC[- ]?PR|PR[- ]?AUC|AUPRC|average precision",
    "AUC": r"AUC",
    "Macro-F1": r"macro[- ]?F1(?:[- ]score)?",
    "Micro-F1": r"micro[- ]?F1(?:[- ]score)?",
    "F1": r"F1(?:[- ]score)?|F-score|F-measure",
    "Precision": r"precision",
    "Recall": r"recall",
    "Accuracy": r"accuracy",
    "G-mean": r"G[- ]mean",
    "MCC": r"MCC|Matthews correlation coefficient",
    "KS": r"KS[- ]statistic",
}
# Order matters: longer/specific names first so "AUC-PR" is not read as "AUC".
_METRIC_ALTERNATION = "|".join(f"(?P<m{i}>{p})" for i, p in enumerate(_METRICS.values()))
_METRIC_NAMES = list(_METRICS)
_NUMBER = r"(?<![\[\d.])(?P<num>\d{1,3}(?:\.\d+)?)(?![\d\]])\s*(?P<pct>%)?"
_METRIC_THEN_NUMBER = re.compile(
    rf"\b(?:{_METRIC_ALTERNATION})\b[^.\d%;]{{0,30}}?{_NUMBER}", re.IGNORECASE
)
_NUMBER_THEN_METRIC = re.compile(
    rf"{_NUMBER}\s*(?:in\s+|of\s+)?(?:{_METRIC_ALTERNATION})\b", re.IGNORECASE
)

_METHODS = {
    "CARE-GNN": r"CARE[- ]GNN",
    "PC-GNN": r"PC[- ]GNN",
    "GraphConsis": r"GraphConsis",
    "GraphSAGE": r"GraphSAGE",
    "GCN": r"GCNs?|graph convolutional networks?",
    "GAT": r"GATs?|graph attention networks?",
    "GIN": r"GIN",
    "R-GCN": r"R-?GCN",
    "HGT": r"HGT",
    "GNN": r"GNNs?|graph neural networks?",
    "XGBoost": r"XGBoost",
    "LightGBM": r"LightGBM",
    "CatBoost": r"CatBoost",
    "Gradient boosting": r"gradient[- ]boost(?:ing|ed)(?: decision trees?)?|GBDT",
    "Random forest": r"random forests?",
    "Logistic regression": r"logistic regression",
    "SVM": r"SVMs?|support vector machines?",
    "Decision tree": r"decision trees?",
    "MLP": r"MLPs?|multi-?layer perceptrons?",
    "LSTM": r"LSTMs?",
    "GRU": r"GRUs?",
    "CNN": r"CNNs?|convolutional neural networks?",
    "Transformer": r"Transformers?",
    "BERT": r"BERT",
    "Autoencoder": r"auto-?encoders?",
    "Isolation forest": r"isolation forests?",
    "k-NN": r"k-?NN|k-nearest neighbou?rs?",
    "Naive Bayes": r"naive Bayes",
}
_METHOD_PATTERNS = [
    (name, re.compile(rf"(?<![\w-])(?:{pattern})(?![\w-])", re.IGNORECASE if name in {
        "Gradient boosting", "Random forest", "Logistic regression", "Decision tree",
        "Autoencoder", "Isolation forest", "Naive Bayes", "k-NN",
    } else 0))
    for name, pattern in _METHODS.items()
]  # fmt: skip
_PROPOSED_CUE = re.compile(
    r"\b(we propose|we present|we introduce|our (?:proposed )?(?:model|method|approach|framework))\b",
    re.IGNORECASE,
)
_BASELINE_CUE = re.compile(
    r"\b(baselines?|compared (?:with|to|against)|outperform(?:s|ed|ing)?|state-of-the-art methods)\b",
    re.IGNORECASE,
)

_KNOWN_DATASETS = {
    "YelpChi": r"YelpChi|Yelp(?:Chi)? review(?:s)? dataset",
    "Amazon (fraud)": r"Amazon (?:review |user )?(?:fraud )?dataset|Amazon\b(?= dataset)",
    "Elliptic": r"Elliptic(?: Bitcoin)?(?: dataset)?",
    "IEEE-CIS": r"IEEE-CIS",
    "PaySim": r"PaySim",
    "T-Finance": r"T-Finance",
    "T-Social": r"T-Social",
    "DGraph": r"DGraph(?:-Fin)?",
    "FDCompCN": r"FDCompCN",
    "Credit Card Fraud (ULB)": r"European cardholders|ULB credit card|Kaggle credit card",
}
_DATASET_PATTERNS = [
    (n, re.compile(rf"\b(?:{p})", re.IGNORECASE)) for n, p in _KNOWN_DATASETS.items()
]
_DATASET_GENERIC = re.compile(
    r"\b([A-Z][A-Za-z0-9-]{2,}(?: [A-Z][A-Za-z0-9-]+)?) (?:dataset|benchmark)\b"
)
_NOT_DATASET_NAMES = {
    "The",
    "This",
    "Our",
    "Each",
    "These",
    "That",
    "Both",
    "All",
    "Real",
    "Public",
    "Large",
}

_SPLIT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?P<k>\d{1,2})[- ]fold cross[- ]validation\b", re.IGNORECASE), "k-fold cross-validation"),
    (re.compile(r"\b(?P<train>\d{1,2})\s*%?\s*[/:]\s*(?P<valid>\d{1,2})\s*%?\s*[/:]\s*(?P<test>\d{1,2})\s*%?", re.IGNORECASE), "train/validation/test split"),
    (re.compile(r"\b(?P<train>\d{1,2})\s*%\s*(?:for |of the data for |as )?training\b[^.]{0,40}?\b(?P<test>\d{1,2})\s*%\s*(?:for |as )?test", re.IGNORECASE), "train/test split"),
    (re.compile(r"\b(?:temporal|chronological|time-based)(?:ly)? split|split (?:the data )?(?:by|according to) time\b", re.IGNORECASE), "temporal split"),
    (re.compile(r"\btraining (?:ratio|percentage|size|data) (?:of |(?:is |was )?(?:set to )?)?(?P<train>\d{1,2})\s*%", re.IGNORECASE), "training ratio"),
]  # fmt: skip

_LIMITATION_CUE = re.compile(
    r"\b(limitations?|limited to|does not generalize|do not generalize|fails? to|"
    r"in future work|future work|we leave [^.]{0,60} (?:for|to) future|not (?:yet )?(?:evaluated|tested))\b",
    re.IGNORECASE,
)
_CODE_URL = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/[\w.-]+/[\w.-]+", re.IGNORECASE
)
_CODE_STATEMENT = re.compile(
    r"\b(?:code|implementation|source code)s?\b[^.]{0,40}\b(is|are|will be|has been|have been) "
    r"(?:made )?(?:publicly |freely |openly )?(?:available|released)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: uuid.UUID
    page_number: int | None
    text: str
    retrieval_method: str
    retrieval_score: float


@dataclass(frozen=True)
class ExtractedFact:
    field: EvidenceField
    value: dict[str, Any]
    passage: str
    chunk: SourceChunk

    def key(self) -> tuple[str, str]:
        identity = {k: v for k, v in self.value.items() if k not in ("raw", "cue", "method_hint")}
        return self.field.value, repr(sorted(identity.items()))


def extract(chunks: list[SourceChunk]) -> list[ExtractedFact]:
    """Facts from every sentence of the given chunks, best-ranked occurrence first,
    duplicates (same field and value) removed."""
    facts: list[ExtractedFact] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        for sentence in split_sentences(chunk.text):
            for fact in _facts_in_sentence(sentence, chunk):
                if fact.key() not in seen:
                    seen.add(fact.key())
                    facts.append(fact)
    return facts


def _facts_in_sentence(sentence: str, chunk: SourceChunk) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    positioned = _methods_in(sentence)
    methods = [name for _, name in positioned]

    def add(field: EvidenceField, value: dict[str, Any]) -> None:
        facts.append(ExtractedFact(field, value, sentence, chunk))

    for position, metric, number, unit, raw in _metric_values(sentence):
        add(
            EvidenceField.METRIC_RESULT,
            {"metric": metric, "value": number, "unit": unit, "raw": raw,
             "method_hint": _nearest_method(positioned, position)},
        )  # fmt: skip

    proposed = bool(_PROPOSED_CUE.search(sentence))
    for method in methods:
        add(EvidenceField.METHOD, {"name": method, "role": "proposed" if proposed else "mentioned"})
    baseline_cue = _BASELINE_CUE.search(sentence)
    if baseline_cue:
        # "X outperforms Y" / "compared with Y": only methods after the cue are baselines.
        # "Y and Z serve as baselines": the word "baseline" names them wherever they are.
        is_baseline_word = baseline_cue.group(0).lower().startswith("baseline")
        for position, method in positioned:
            if is_baseline_word or position > baseline_cue.start():
                add(EvidenceField.BASELINE, {"name": method, "cue": baseline_cue.group(0)})

    for name in _datasets_in(sentence):
        add(EvidenceField.DATASET, name)

    for pattern, protocol in _SPLIT_PATTERNS:
        match = pattern.search(sentence)
        if match:
            details = {k: int(v) for k, v in match.groupdict().items() if v is not None}
            add(EvidenceField.SPLIT, {"protocol": protocol, **details, "raw": match.group(0)})

    limitation = _LIMITATION_CUE.search(sentence)
    if limitation:
        add(
            EvidenceField.LIMITATION,
            {"cue": limitation.group(0).lower(), "statement": "limitation"},
        )

    url = _CODE_URL.search(sentence)
    statement = _CODE_STATEMENT.search(sentence)
    if url or statement:
        add(
            EvidenceField.CODE_AVAILABILITY,
            {"url": url.group(0).rstrip(".") if url else None,
             "statement": "will be available" if statement and "will" in statement.group(1).lower() else "available"},
        )  # fmt: skip
    return facts


def _nearest_method(positioned: list[tuple[int, str]], position: int) -> str | None:
    """The method mentioned closest before a value ("A reaches 0.9, while B reaches
    0.8" credits each value to its own method); else the first one after it."""
    before = [name for start, name in positioned if start < position]
    if before:
        return before[-1]
    return positioned[0][1] if positioned else None


def _metric_values(sentence: str) -> list[tuple[int, str, float, str | None, str]]:
    found: list[tuple[int, str, float, str | None, str]] = []
    spans: list[tuple[int, int]] = []
    for pattern in (_METRIC_THEN_NUMBER, _NUMBER_THEN_METRIC):
        for match in pattern.finditer(sentence):
            if any(match.start() < end and start < match.end() for start, end in spans):
                continue
            metric = next(
                _METRIC_NAMES[i] for i in range(len(_METRIC_NAMES)) if match.group(f"m{i}")
            )
            number = float(match.group("num"))
            unit = "%" if match.group("pct") else ("ratio" if number <= 1 else None)
            if (unit == "%" and number > 100) or (unit is None and number > 100):
                continue
            spans.append((match.start(), match.end()))
            found.append((match.start(), metric, number, unit, match.group(0).strip()))
    return found


def _methods_in(sentence: str) -> list[tuple[int, str]]:
    """(position, canonical name) of each method mentioned, in sentence order."""
    return sorted(
        (m.start(), name) for name, pattern in _METHOD_PATTERNS if (m := pattern.search(sentence))
    )


def _datasets_in(sentence: str) -> list[dict[str, Any]]:
    names = [{"name": n, "source": "lexicon"} for n, p in _DATASET_PATTERNS if p.search(sentence)]
    known = {d["name"].split(" ")[0].lower() for d in names}
    for match in _DATASET_GENERIC.finditer(sentence):
        candidate = match.group(1)
        if (
            candidate.split(" ")[0] in _NOT_DATASET_NAMES
            or candidate.lower().split(" ")[0] in known
        ):
            continue
        names.append({"name": candidate, "source": "pattern"})
    return names
