"""Deterministic comparability rules (compare-v1).

Input: verified evidence for one investigation. Output: a per-paper matrix,
groups of results that can be compared directly, results that cannot (with
reasons), and author claims of the form "A outperforms B".

Principles:
- A result is comparable with another only when metric, dataset, and evaluation
  protocol are known and equal. Extraction does not tie a value to a dataset,
  so a value is attributed to a dataset only when its paper reports exactly
  one dataset (likewise for protocol). Anything else is "not comparable" with
  the reason, never silently grouped.
- Percentages and ratios are put on one 0-1 scale (noted); values with no unit
  are never normalized or compared.
- Nothing here ranks methods across groups. Within a group, values are listed
  as reported, not reproduced.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.evidence.rules import outperformance_claims

COMPARISON_VERSION = "compare-v2"  # v2: claimants outside the method lexicon


@dataclass(frozen=True)
class EvidenceInput:
    """One verified evidence record, as the comparison needs it."""

    evidence_id: uuid.UUID
    paper_id: uuid.UUID
    field: str
    finding_status: str  # reported | uncertain | not_found | unavailable
    value: dict[str, object] | None
    passage: str | None
    page_number: int | None


@dataclass(frozen=True)
class PaperInput:
    paper_id: uuid.UUID
    title: str
    year: int | None
    content_kind: str  # full_text | abstract | none


class ResultCell(BaseModel):
    evidence_id: uuid.UUID
    metric: str
    value: float
    unit: str | None
    normalized: float | None  # 0-1 scale; None when the unit is unknown
    method: str | None
    page: int | None


class MatrixRow(BaseModel):
    paper_id: uuid.UUID
    title: str
    year: int | None
    content_kind: str
    methods: list[str]
    proposed_methods: list[str]
    datasets: list[str]
    protocols: list[str]
    baselines: list[str]
    results: list[ResultCell]
    missing_fields: list[str]
    warnings: list[str]


class GroupMember(BaseModel):
    paper_id: uuid.UUID
    evidence_id: uuid.UUID
    method: str | None
    value: float
    unit: str | None
    normalized: float


class ComparableGroup(BaseModel):
    metric: str
    dataset: str
    protocol: str
    members: list[GroupMember]

    @property
    def paper_count(self) -> int:
        return len({m.paper_id for m in self.members})


class NotComparable(BaseModel):
    paper_id: uuid.UUID
    evidence_id: uuid.UUID
    metric: str
    reasons: list[str]


class Claim(BaseModel):
    paper_id: uuid.UUID
    evidence_id: uuid.UUID
    better: str
    worse: str


class Comparison(BaseModel):
    version: str = COMPARISON_VERSION
    matrix: list[MatrixRow]
    groups: list[ComparableGroup]
    not_comparable: list[NotComparable]
    claims: list[Claim]
    conflicts: list[tuple[str, str]]  # (A, B) where some papers claim A > B and others B > A


# Row warnings, shown verbatim in the UI.
W_ABSTRACT_ONLY = "Only the abstract was available; most details could not be checked."
W_NO_TEXT = "No text was available for this paper."
W_NO_RESULTS = "No numeric results were found."
W_DATASETS_UNATTRIBUTED = "Several datasets reported; results cannot be tied to one dataset."
W_NO_DATASET = "No dataset found; results cannot be compared."
W_NO_PROTOCOL = "Evaluation split or protocol not found."
W_UNIT_UNCLEAR = "Some values have no stated unit or scale."
W_NO_BASELINES = "No baselines found."


@dataclass
class _Profile:
    paper: PaperInput
    methods: list[str] = field(default_factory=list)
    proposed: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    protocols: list[str] = field(default_factory=list)
    baselines: list[str] = field(default_factory=list)
    results: list[ResultCell] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)


def compare(papers: list[PaperInput], evidence: list[EvidenceInput]) -> Comparison:
    profiles = {p.paper_id: _Profile(p) for p in papers}
    for record in evidence:
        profile = profiles.get(record.paper_id)
        if profile is not None:
            _absorb(profile, record)

    matrix = [_row(p) for p in sorted(profiles.values(), key=lambda p: p.paper.title.lower())]
    groups, not_comparable = _group_results(profiles.values())
    claims = [c for p in profiles.values() for c in p.claims]
    return Comparison(
        matrix=matrix,
        groups=groups,
        not_comparable=not_comparable,
        claims=claims,
        conflicts=_conflicts(claims),
    )


def _absorb(profile: _Profile, record: EvidenceInput) -> None:
    if record.passage is None:
        profile.missing.append(record.field)
        return
    value = record.value or {}
    name = str(value.get("name", ""))
    if record.field == "method" and name:
        _add(profile.methods, name)
        if value.get("role") == "proposed":
            _add(profile.proposed, name)
    elif record.field == "dataset" and name:
        _add(profile.datasets, name)
    elif record.field == "baseline" and name:
        _add(profile.baselines, name)
        for better, worse in outperformance_claims(record.passage):
            if worse == name:
                profile.claims.append(
                    Claim(
                        paper_id=record.paper_id,
                        evidence_id=record.evidence_id,
                        better=better,
                        worse=worse,
                    )
                )
    elif record.field == "split":
        _add(profile.protocols, _protocol_label(value))
    elif record.field == "metric_result":
        number = value.get("value")
        if isinstance(number, (int, float)):
            unit = value.get("unit")
            unit_text = unit if isinstance(unit, str) else None
            profile.results.append(
                ResultCell(
                    evidence_id=record.evidence_id,
                    metric=str(value.get("metric")),
                    value=float(number),
                    unit=unit_text,
                    normalized=_normalize(float(number), unit_text),
                    method=str(value["method_hint"]) if value.get("method_hint") else None,
                    page=record.page_number,
                )
            )


def _add(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)


def _protocol_label(value: dict[str, object]) -> str:
    protocol = str(value.get("protocol", "unknown protocol"))
    if "k" in value:
        return f"{value['k']}-fold cross-validation"
    parts = [f"{key} {value[key]}%" for key in ("train", "valid", "test") if key in value]
    return f"{protocol} ({', '.join(parts)})" if parts else protocol


def _normalize(value: float, unit: str | None) -> float | None:
    if unit == "%":
        return round(value / 100, 6)
    if unit == "ratio":
        return value
    return None


def _row(profile: _Profile) -> MatrixRow:
    warnings: list[str] = []
    kind = profile.paper.content_kind
    if kind == "none":
        warnings.append(W_NO_TEXT)
    elif kind == "abstract":
        warnings.append(W_ABSTRACT_ONLY)
    if not profile.results:
        warnings.append(W_NO_RESULTS)
    if len(profile.datasets) > 1 and profile.results:
        warnings.append(W_DATASETS_UNATTRIBUTED)
    if not profile.datasets and profile.results:
        warnings.append(W_NO_DATASET)
    if not profile.protocols and profile.results:
        warnings.append(W_NO_PROTOCOL)
    if any(r.normalized is None for r in profile.results):
        warnings.append(W_UNIT_UNCLEAR)
    if not profile.baselines and profile.results:
        warnings.append(W_NO_BASELINES)
    return MatrixRow(
        paper_id=profile.paper.paper_id,
        title=profile.paper.title,
        year=profile.paper.year,
        content_kind=kind,
        methods=profile.methods,
        proposed_methods=profile.proposed,
        datasets=profile.datasets,
        protocols=profile.protocols,
        baselines=profile.baselines,
        results=profile.results,
        missing_fields=sorted(set(profile.missing)),
        warnings=warnings,
    )


def _group_results(
    profiles: Iterable[_Profile],
) -> tuple[list[ComparableGroup], list[NotComparable]]:
    grouped: dict[tuple[str, str, str], list[GroupMember]] = defaultdict(list)
    not_comparable: list[NotComparable] = []
    for profile in profiles:
        for result in profile.results:
            reasons = []
            if result.normalized is None:
                reasons.append("unit or scale not stated")
            if not profile.datasets:
                reasons.append("dataset not reported")
            elif len(profile.datasets) > 1:
                reasons.append("paper reports several datasets; value not tied to one")
            if not profile.protocols:
                reasons.append("evaluation protocol not reported")
            elif len(profile.protocols) > 1:
                reasons.append("paper reports several protocols; value not tied to one")
            if reasons:
                not_comparable.append(
                    NotComparable(
                        paper_id=profile.paper.paper_id,
                        evidence_id=result.evidence_id,
                        metric=result.metric,
                        reasons=reasons,
                    )
                )
                continue
            assert result.normalized is not None  # unit-less values were excluded above
            key = (result.metric, profile.datasets[0], profile.protocols[0])
            grouped[key].append(
                GroupMember(
                    paper_id=profile.paper.paper_id,
                    evidence_id=result.evidence_id,
                    method=result.method,
                    value=result.value,
                    unit=result.unit,
                    normalized=result.normalized,
                )
            )
    groups = [
        ComparableGroup(
            metric=metric,
            dataset=dataset,
            protocol=protocol,
            members=sorted(members, key=lambda m: -m.normalized),
        )
        for (metric, dataset, protocol), members in sorted(grouped.items())
    ]
    return groups, not_comparable


def _conflicts(claims: list[Claim]) -> list[tuple[str, str]]:
    directions = {(c.better, c.worse) for c in claims}
    pairs = {(min(a, b), max(a, b)) for a, b in directions if (b, a) in directions}
    return sorted(pairs)
