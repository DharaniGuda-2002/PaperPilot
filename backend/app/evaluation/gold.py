"""Gold-set loading, matching, and scoring for the manually reviewed evaluation
set. Pure functions: no database, so the matching rules are unit-tested.

A gold fact is located by short anchors (verbatim phrases), not full passages.
An extracted record matches a fact when:
  - dataset / baseline: same field, page among the fact's pages, and the
    extracted name matches one of the fact's aliases;
  - metric_result: same field, page among the fact's pages, and the same number
    (to the precision the gold value is written with);
  - split / code_availability / limitation: same field and the record's passage
    comes from a chunk that contains one of the fact's anchors.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCORED_FIELDS = (
    "dataset",
    "baseline",
    "split",
    "metric_result",
    "code_availability",
    "limitation",
)
NAME_FIELDS = {"dataset", "baseline"}
_SHORT_ALIAS = 4  # aliases shorter than this must match exactly ("nq", "cnn", "con")
# Curly quotes and dashes -> ASCII, so anchors typed with either form match.
_TYPOGRAPHY = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"}
)


@dataclass(frozen=True)
class GoldFact:
    field: str
    value: Any
    pages: tuple[int, ...]
    anchors: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    metric: str | None = None


@dataclass(frozen=True)
class GoldPaper:
    doi: str
    title: str
    facts: tuple[GoldFact, ...]
    absent: tuple[str, ...]


@dataclass(frozen=True)
class GoldSet:
    name: str
    question: str
    annotator: str
    review_status: str
    papers: tuple[GoldPaper, ...]
    reviewed_by: str | None = None
    reviewed_on: str | None = None


@dataclass(frozen=True)
class Extracted:
    """One extracted record, reduced to what scoring needs."""

    field: str
    value: dict[str, Any]
    page: int | None
    chunk_id: str
    passage: str
    verified: bool


@dataclass
class FieldScore:
    gold: int = 0
    found: int = 0
    extracted: int = 0
    correct: int = 0
    unjudged: int = 0

    @property
    def recall(self) -> float | None:
        return self.found / self.gold if self.gold else None

    @property
    def precision(self) -> float | None:
        judged = self.extracted - self.unjudged
        return self.correct / judged if judged else None


@dataclass
class PaperResult:
    doi: str
    found: list[bool] = field(default_factory=list)  # per gold fact, in order
    verdicts: list[tuple[Extracted, bool | None, str]] = field(default_factory=list)


def load_gold(path: Path) -> GoldSet:
    raw = json.loads(path.read_text())
    papers = []
    for paper in raw["papers"]:
        facts = []
        for fact in paper["facts"]:
            if fact["field"] not in SCORED_FIELDS:
                raise ValueError(f"{paper['doi']}: unknown field {fact['field']!r}")
            if not fact["anchors"] or any(len(a.split()) >= 15 for a in fact["anchors"]):
                raise ValueError(f"{paper['doi']}: anchors must be 1-14 words: {fact}")
            facts.append(
                GoldFact(
                    field=fact["field"],
                    value=fact["value"],
                    pages=tuple(fact["pages"]),
                    anchors=tuple(fact["anchors"]),
                    aliases=tuple(fact.get("aliases", ())),
                    metric=fact.get("metric"),
                )
            )
        papers.append(
            GoldPaper(paper["doi"], paper["title"], tuple(facts), tuple(paper.get("absent", ())))
        )
    return GoldSet(
        raw["set"],
        raw["question"],
        raw["annotator"],
        raw["review_status"],
        tuple(papers),
        reviewed_by=raw.get("reviewed_by"),
        reviewed_on=raw.get("reviewed_on"),
    )


def normalize(text: str) -> str:
    """Case-, whitespace-, and typography-insensitive form for anchor search."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_TYPOGRAPHY)
    return re.sub(r"\s+", " ", text).strip().lower()


def _name_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize(text))


def anchor_chunks(fact: GoldFact, chunks: dict[str, str]) -> set[str]:
    """Ids of the chunks (id -> text) that contain one of the fact's anchors."""
    anchors = [normalize(a) for a in fact.anchors]
    return {cid for cid, text in chunks.items() if any(a in normalize(text) for a in anchors)}


def name_matches(name: str, aliases: tuple[str, ...]) -> bool:
    key = _name_key(name)
    if not key:
        return False
    for alias in aliases:
        alias_key = _name_key(alias)
        if len(alias_key) < _SHORT_ALIAS or len(key) < _SHORT_ALIAS:
            if key == alias_key:
                return True
        elif alias_key in key or key in alias_key:
            return True
    return False


def matches(record: Extracted, fact: GoldFact, fact_chunks: set[str]) -> bool:
    if record.field != fact.field:
        return False
    if fact.field in NAME_FIELDS:
        return record.page in fact.pages and name_matches(
            str(record.value.get("name", "")), fact.aliases
        )
    if fact.field == "metric_result":
        value = record.value.get("value")
        return (
            record.page in fact.pages
            and isinstance(value, int | float)
            and abs(float(value) - float(fact.value)) <= _rounding_tolerance(fact.value)
        )
    return record.chunk_id in fact_chunks


def _rounding_tolerance(gold_value: object) -> float:
    """Half a unit in the gold value's last written decimal: 0.87 accepts
    0.870 but not 0.89; 47.8 accepts 47.80 but not 47.9."""
    text = str(gold_value)
    decimals = len(text.split(".")[1]) if "." in text else 0
    return 0.5 * 10.0**-decimals + 1e-9


def judgement_key(doi: str, record: Extracted) -> str:
    """Stable id for a manual verdict on a record no gold fact explains. It hashes
    the passage so the judgement file needs no copy of the paper's text."""
    digest = hashlib.sha256(normalize(record.passage).encode()).hexdigest()[:10]
    return f"{doi}|{record.field}|p{record.page}|{_value_label(record)}|{digest}"


def _value_label(record: Extracted) -> str:
    value = record.value
    if record.field in NAME_FIELDS:
        return str(value.get("name"))
    if record.field == "metric_result":
        return f"{value.get('metric')}={value.get('value')}{value.get('unit') or ''}"
    return str(value.get("url") or value.get("protocol") or value.get("cue") or "")


def score_paper(
    paper: GoldPaper,
    records: list[Extracted],
    chunk_index: list[set[str]],
    judgements: dict[str, bool],
) -> PaperResult:
    """chunk_index[i] holds the anchor chunks of paper.facts[i]."""
    result = PaperResult(paper.doi)
    for fact, fact_chunks in zip(paper.facts, chunk_index, strict=True):
        result.found.append(any(matches(r, fact, fact_chunks) for r in records))
    for record in records:
        if any(
            matches(record, fact, fact_chunks)
            for fact, fact_chunks in zip(paper.facts, chunk_index, strict=True)
        ):
            result.verdicts.append((record, True, "matches gold"))
        else:
            key = judgement_key(paper.doi, record)
            verdict = judgements.get(key)
            result.verdicts.append((record, verdict, key))
    return result


def field_scores(papers: list[GoldPaper], results: list[PaperResult]) -> dict[str, FieldScore]:
    scores = {name: FieldScore() for name in SCORED_FIELDS}
    for paper, result in zip(papers, results, strict=True):
        for fact, found in zip(paper.facts, result.found, strict=True):
            scores[fact.field].gold += 1
            scores[fact.field].found += found
        for record, verdict, _ in result.verdicts:
            score = scores[record.field]
            score.extracted += 1
            if verdict is None:
                score.unjudged += 1
            elif verdict:
                score.correct += 1
    return scores


def load_judgements(path: Path) -> dict[str, bool]:
    if not path.exists():
        return {}
    return {item["key"]: bool(item["correct"]) for item in json.loads(path.read_text())["items"]}
