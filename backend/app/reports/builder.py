"""Deterministic report generation (report-v1).

Every sentence is filled from counts and records already persisted and
validated; there is no free-form generation, so the report cannot state a
finding that the evidence does not contain. Wording reports what papers
*report*; it never asserts that a method is better.
"""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from app.comparison.rules import Claim, ComparableGroup, Comparison, MatrixRow
from app.evidence.rules import methods_in
from app.reports.schemas import (
    Finding,
    FindingKind,
    PaperRef,
    Report,
    Scope,
    Strength,
    StudySupport,
)

MAX_FINDINGS = 5
MIN_FINDINGS = 3

# Method families, so "GCN outperforms XGBoost" and "GAT outperforms LightGBM"
# count as evidence about the same question-level comparison.
FAMILIES = {
    "Graph neural networks": {"GNN", "GCN", "GAT", "GraphSAGE", "GIN", "R-GCN", "HGT", "CARE-GNN", "PC-GNN", "GraphConsis"},
    "Gradient-boosted trees": {"XGBoost", "LightGBM", "CatBoost", "Gradient boosting"},
    "Tree ensembles": {"Random forest", "Decision tree", "Isolation forest"},
    "Linear models": {"Logistic regression", "SVM"},
    "Large language models": {"GPT", "Llama", "T5", "BART"},
    "Retrieval-augmented generation": {"RAG", "FiD"},
    "Neural retrievers": {"DPR", "ColBERT", "Contriever"},
}  # fmt: skip
_FAMILY_OF = {method: name for name, members in FAMILIES.items() for method in members}


def family(method: str) -> str:
    return _FAMILY_OF.get(method, method)


def strength_for(full_text: int, abstract_only: int, conflicting: int) -> tuple[Strength, str]:
    """Apply the published strength definitions (see STRENGTH_DEFINITIONS)."""
    total = full_text + abstract_only
    if total == 0:
        return Strength.INSUFFICIENT, "No paper supports it with a checkable quotation."
    if full_text == 0:
        level, reason = Strength.LIMITED, f"{_n(total, 'paper')}, abstracts only"
    elif full_text >= 3:
        level, reason = Strength.STRONG, f"{_n(full_text, 'paper')} with full text"
    elif total >= 2:
        level, reason = Strength.MODERATE, _n(total, "paper")
    else:
        level, reason = Strength.LIMITED, "1 paper"
    if conflicting:
        order = list(Strength)
        level = order[min(order.index(level) + 1, len(order) - 1)]
        reason += f"; {_n(conflicting, 'paper')} report the opposite"
    return level, reason


@dataclass(frozen=True)
class _ClaimFinding:
    finding: Finding
    better: str
    worse: str


def build_report(
    *,
    question: str,
    papers: list[PaperRef],
    papers_discovered: int,
    comparison: Comparison,
    versions: dict[str, str],
    duplicates_merged: int = 0,
) -> Report:
    rows = {r.paper_id: r for r in comparison.matrix}
    analyzed = sum(r.content_kind != "none" for r in comparison.matrix)
    full = sum(r.content_kind == "full_text" for r in comparison.matrix)
    abstract = sum(r.content_kind == "abstract" for r in comparison.matrix)
    with_evidence = sum(
        bool(r.methods or r.results or r.datasets or r.baselines) for r in comparison.matrix
    )

    claims = _claim_findings(question, comparison, rows)
    comparisons = _comparison_findings(comparison, rows)
    caveats = _caveat_findings(comparison, rows)
    findings = _select([c.finding for c in claims], comparisons, caveats)
    _link_related(findings)

    scored = [f.strength for f in findings if f.strength is not None]
    order = list(Strength)
    overall = min(scored, key=order.index) if scored else Strength.INSUFFICIENT

    return Report(
        generated_at=datetime.now(UTC),
        question=question,
        scope=Scope(
            papers_discovered=papers_discovered,
            full_text=full,
            abstract_only=abstract,
            no_text=len(comparison.matrix) - full - abstract,
            papers_with_evidence=with_evidence,
            duplicates_merged=duplicates_merged,
            selection=(
                f"Top OpenAlex results for the question, by relevance; {papers_discovered} "
                "distinct studies"
                + (
                    f" after merging {duplicates_merged} duplicate listing"
                    f"{'' if duplicates_merged == 1 else 's'} of the same study."
                    if duplicates_merged
                    else "."
                )
            ),
        ),
        bottom_line=_bottom_line(question, claims, comparison, analyzed, abstract),
        overall_strength=overall,
        key_findings=findings,
        limitations=_limitations(comparison, full, abstract, versions),
        missing_information=_missing_information(comparison, full),
        unresolved_questions=_unresolved(comparison, claims),
        comparison=comparison,
        papers=papers,
        versions=versions,
    )


# ---------------------------------------------------------------- findings


def _support(row: MatrixRow, detail: str, evidence_ids: list[uuid.UUID]) -> StudySupport:
    return StudySupport(
        paper_id=row.paper_id,
        title=row.title,
        year=row.year,
        content_kind=row.content_kind,
        detail=detail,
        evidence_ids=list(dict.fromkeys(evidence_ids)),
    )


def _claim_findings(
    question: str, comparison: Comparison, rows: dict[uuid.UUID, MatrixRow]
) -> list[_ClaimFinding]:
    by_pair: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for claim in comparison.claims:
        better, worse = family(claim.better), family(claim.worse)
        if better != worse:
            by_pair[(better, worse)].append(claim)
    question_families = {family(m) for m in methods_in(question)}

    def priority(pair: tuple[str, str]) -> tuple[int, int, str]:
        papers = len({c.paper_id for c in by_pair[pair]})
        involves_question = len(set(pair) & question_families)
        return (-involves_question, -papers, " ".join(pair))

    results: list[_ClaimFinding] = []
    seen: set[frozenset[str]] = set()
    for pair in sorted(by_pair, key=priority):
        if frozenset(pair) in seen:
            continue
        seen.add(frozenset(pair))
        better, worse = pair
        supporting = _supports_for(
            by_pair[pair], rows, f"Authors report {better} outperforming {worse}"
        )
        conflicting = _supports_for(
            by_pair.get((worse, better), []), rows, f"Authors report {worse} outperforming {better}"
        )
        full = sum(s.content_kind == "full_text" for s in supporting)
        level, reason = strength_for(full, len(supporting) - full, len(conflicting))
        summary = f"{_n(len(supporting), 'paper')} report {better} outperforming {worse}."
        if conflicting:
            summary += f" {_n(len(conflicting), 'paper')} report the opposite."
        summary += " These are the authors' own claims, each in its own experimental setting."
        finding = Finding(
            id=f"claim-{len(results) + 1}",
            kind=FindingKind.CLAIM,
            title=f"{better} reported to outperform {worse}",
            summary=summary,
            strength=level,
            strength_reason=reason,
            supporting=supporting,
            conflicting=conflicting,
            warnings=_setting_warnings(supporting + conflicting, rows),
            related=[],
        )
        results.append(_ClaimFinding(finding, better, worse))
    return results


def _supports_for(
    claims: list[Claim], rows: dict[uuid.UUID, MatrixRow], detail: str
) -> list[StudySupport]:
    by_paper: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for claim in claims:
        by_paper[claim.paper_id].append(claim.evidence_id)
    return [_support(rows[pid], detail, ids) for pid, ids in by_paper.items() if pid in rows]


def _setting_warnings(supports: list[StudySupport], rows: dict[uuid.UUID, MatrixRow]) -> list[str]:
    datasets = {d for s in supports for d in rows[s.paper_id].datasets}
    warnings = []
    if len(datasets) > 1:
        warnings.append(f"Papers use different datasets ({', '.join(sorted(datasets)[:5])}).")
    no_protocol = sum(not rows[s.paper_id].protocols for s in supports)
    if no_protocol:
        warnings.append(f"Evaluation protocol not found for {_n(no_protocol, 'paper')}.")
    abstract = sum(s.content_kind != "full_text" for s in supports)
    if abstract:
        warnings.append(f"{_n(abstract, 'paper')} available only as abstracts.")
    return warnings


def _comparison_findings(comparison: Comparison, rows: dict[uuid.UUID, MatrixRow]) -> list[Finding]:
    multi = [g for g in comparison.groups if g.paper_count >= 2]
    ordered = sorted(multi, key=lambda g: (-g.paper_count, g.metric, g.dataset))
    return [_group_finding(group, rows, index) for index, group in enumerate(ordered, start=1)]


def _group_finding(group: ComparableGroup, rows: dict[uuid.UUID, MatrixRow], index: int) -> Finding:
    values = [m.normalized for m in group.members]
    supporting = []
    for member in group.members:
        unit = "%" if member.unit == "%" else ""
        method = f" ({member.method})" if member.method else ""
        detail = f"{group.metric} {member.value:g}{unit}{method}"
        supporting.append(_support(rows[member.paper_id], detail, [member.evidence_id]))
    full = sum(s.content_kind == "full_text" for s in supporting)
    level, reason = strength_for(full, len(supporting) - full, 0)
    return Finding(
        id=f"comparison-{index}",
        kind=FindingKind.COMPARISON,
        title=f"Comparable {group.metric} results on {group.dataset}",
        summary=(
            f"{_n(group.paper_count, 'paper')} report {group.metric} on {group.dataset} under "
            f"{group.protocol}: values range from {min(values):.3g} to {max(values):.3g} "
            "(0-1 scale). Values are as reported by the authors, not reproduced."
        ),
        strength=level,
        strength_reason=reason,
        supporting=supporting,
        conflicting=[],
        warnings=[],
        related=[],
    )


def _caveat(identifier: str, title: str, summary: str, supporting: list[StudySupport]) -> Finding:
    return Finding(
        id=identifier,
        kind=FindingKind.CAVEAT,
        title=title,
        summary=summary,
        strength=None,
        strength_reason=None,
        supporting=supporting,
        conflicting=[],
        warnings=[],
        related=[],
    )


def _caveat_findings(comparison: Comparison, rows: dict[uuid.UUID, MatrixRow]) -> list[Finding]:
    findings: list[Finding] = []
    total = sum(len(r.results) for r in comparison.matrix)
    if comparison.not_comparable:
        reasons = Counter(reason for nc in comparison.not_comparable for reason in nc.reasons)
        top = "; ".join(f"{reason} ({count})" for reason, count in reasons.most_common(3))
        by_paper: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for nc in comparison.not_comparable:
            by_paper[nc.paper_id].append(nc.evidence_id)
        share = "Most" if len(comparison.not_comparable) * 2 > total else "Some"
        findings.append(
            _caveat(
                "caveat-comparability",
                f"{share} reported results cannot be compared directly",
                f"{len(comparison.not_comparable)} of {total} extracted results lack a single "
                f"known dataset, protocol, or unit. Most common reasons: {top}.",
                [
                    _support(rows[pid], "Results not directly comparable", ids)
                    for pid, ids in by_paper.items()
                ],
            )
        )
    elif total == 0:
        findings.append(
            _caveat(
                "caveat-no-results",
                "No numeric results were extracted",
                "None of the analyzed papers yielded a metric value that could be quoted "
                "and checked.",
                [],
            )
        )
    not_full = [r for r in comparison.matrix if r.content_kind != "full_text"]
    if not_full:
        abstract = sum(r.content_kind == "abstract" for r in not_full)
        no_text = len(not_full) - abstract
        findings.append(
            _caveat(
                "caveat-coverage",
                "Part of the literature was read only partially",
                f"{_n(len(not_full), 'paper')} could not be read in full: {abstract} as "
                f"abstracts only and {no_text} with no text at all. Their methods and results "
                "may be missing from this report.",
                [
                    _support(r, "Abstract only" if r.content_kind == "abstract" else "No text", [])
                    for r in not_full
                ],
            )
        )
    stated = [
        r
        for r in comparison.matrix
        if r.content_kind != "none" and "limitation" not in r.missing_fields
    ]
    if stated:
        findings.append(
            _caveat(
                "caveat-author-limitations",
                "Authors state limitations",
                f"{_n(len(stated), 'paper')} state limitations of their own work; "
                "see each paper's evidence.",
                [_support(r, "States limitations", []) for r in stated],
            )
        )
    return findings


def _select(
    claims: list[Finding], comparisons: list[Finding], caveats: list[Finding]
) -> list[Finding]:
    chosen = claims[:2] + comparisons[:2]
    chosen += caveats[: max(MIN_FINDINGS - len(chosen), 1)]
    for extra in claims[2:] + comparisons[2:] + caveats:
        if len(chosen) >= MAX_FINDINGS:
            break
        if extra not in chosen:
            chosen.append(extra)
    return chosen[:MAX_FINDINGS]


def _link_related(findings: list[Finding]) -> None:
    """Findings that share a supporting paper are related."""
    papers = {f.id: {s.paper_id for s in f.supporting + f.conflicting} for f in findings}
    for finding in findings:
        finding.related = [
            other.id
            for other in findings
            if other.id != finding.id and papers[finding.id] & papers[other.id]
        ]


# ------------------------------------------------------------ summary text


def _bottom_line(
    question: str,
    claims: list[_ClaimFinding],
    comparison: Comparison,
    analyzed: int,
    abstract: int,
) -> str:
    parts = []
    named = list(dict.fromkeys(family(m) for m in methods_in(question)))
    relevant = [c for c in claims if not named or {c.better, c.worse} & set(named)]
    if named and claims and not relevant:
        # Lead only with claims about what the question asks; others stay in the findings.
        parts.append(
            f"None of the analyzed papers explicitly compares {' or '.join(named)} with another "
            f"method; {_n(len(claims), 'other comparison')} between methods "
            f"{'is' if len(claims) == 1 else 'are'} listed below."
        )
    elif relevant:
        top = relevant[0]
        opposite = (
            f", while {len(top.finding.conflicting)} report the opposite"
            if top.finding.conflicting
            else ""
        )
        parts.append(
            f"{len(top.finding.supporting)} of {analyzed} analyzed papers report {top.better} "
            f"outperforming {top.worse}{opposite}."
        )
    else:
        parts.append(
            "The analyzed papers contain no explicit claims that one method outperforms another."
        )
    comparable = sum(1 for g in comparison.groups if g.paper_count >= 2)
    total = sum(len(r.results) for r in comparison.matrix)
    parts.append(
        f"{_n(comparable, 'set')} of results can be compared directly across papers; "
        f"{len(comparison.not_comparable)} of {total} extracted results cannot, because their "
        "dataset, protocol, or unit is not known."
    )
    if abstract:
        parts.append(f"{abstract} of {analyzed} papers were available only as abstracts.")
    parts.append("This summarizes reported evidence; it does not establish which method is better.")
    return " ".join(parts)


def _limitations(
    comparison: Comparison, full: int, abstract: int, versions: dict[str, str]
) -> list[str]:
    extraction = versions.get("extraction", "unknown")
    items = [
        f"Facts were extracted by rules ({extraction}); results phrased in unusual ways, "
        "or only in tables and figures, are often missed.",
        "Only open-access PDFs are read in full; other papers contribute their abstracts only.",
        "A result is tied to a dataset only when its paper reports a single dataset.",
    ]
    if abstract:
        items.append(f"{abstract} of {full + abstract} analyzed papers had only an abstract.")
    unattributed = sum(1 for r in comparison.matrix if len(r.datasets) > 1 and r.results)
    if unattributed:
        items.append(
            f"{_n(unattributed, 'paper')} report several datasets, so their values "
            "were not compared."
        )
    return items


_FIELD_LABELS = {
    "split": "Evaluation split or protocol",
    "dataset": "Dataset",
    "baseline": "Baselines",
    "metric_result": "Numeric results",
    "code_availability": "Code availability",
    "limitation": "Stated limitations",
}


def _missing_information(comparison: Comparison, full: int) -> list[str]:
    full_rows = [r for r in comparison.matrix if r.content_kind == "full_text"]
    items = []
    for key, label in _FIELD_LABELS.items():
        missing = sum(key in r.missing_fields for r in full_rows)
        if missing:
            items.append(f"{label} not found in {missing} of {full} full-text papers.")
    return items


def _unresolved(comparison: Comparison, claims: list[_ClaimFinding]) -> list[str]:
    """Disagreements at the family level ("GCN > XGBoost" in one paper, "XGBoost >
    GAT" in another), plus exact method-level conflicts not already covered."""
    pairs = [(c.better, c.worse) for c in claims if c.finding.conflicting]
    covered = {frozenset(pair) for pair in pairs}
    pairs += [
        (a, b) for a, b in comparison.conflicts if frozenset((family(a), family(b))) not in covered
    ]
    items = [
        f"Papers disagree on {a} versus {b}: would they differ under the same dataset and protocol?"
        for a, b in pairs
    ]
    if not any(g.paper_count >= 2 for g in comparison.groups):
        items.append(
            "No two papers report the same metric on the same dataset and protocol; "
            "a controlled comparison would be needed to rank methods."
        )
    return items


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"
