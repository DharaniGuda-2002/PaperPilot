import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.comparison.rules import Comparison

REPORT_SCHEMA_VERSION = 1
GENERATOR_VERSION = "report-v1"


class Strength(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


# Shown in the UI next to every strength label. Strength describes how much
# independent, checkable evidence supports a finding. It is not a model's
# confidence and not a judgment that the finding is true.
STRENGTH_DEFINITIONS: dict[Strength, str] = {
    Strength.STRONG: (
        "Supported by 3 or more papers with full text, with no paper reporting the opposite."
    ),
    Strength.MODERATE: (
        "Supported by 2 papers, or by 3 or more full-text papers when some paper reports "
        "the opposite."
    ),
    Strength.LIMITED: (
        "Supported by 1 paper, only by abstracts, or by 2 papers when some paper reports "
        "the opposite."
    ),
    Strength.INSUFFICIENT: "No paper supports it with a checkable quotation.",
}


class FindingKind(StrEnum):
    CLAIM = "claim"  # what authors report about methods
    COMPARISON = "comparison"  # values that can be compared directly
    CAVEAT = "caveat"  # what limits the conclusions


class StudySupport(BaseModel):
    paper_id: uuid.UUID
    title: str
    year: int | None
    content_kind: str
    detail: str
    evidence_ids: list[uuid.UUID]


class Finding(BaseModel):
    id: str
    kind: FindingKind
    title: str
    summary: str
    strength: Strength | None  # None for caveats
    strength_reason: str | None
    supporting: list[StudySupport]
    conflicting: list[StudySupport]
    warnings: list[str]
    related: list[str]


class Scope(BaseModel):
    papers_discovered: int
    full_text: int
    abstract_only: int
    no_text: int
    papers_with_evidence: int
    duplicates_merged: int = 0  # same study listed twice (e.g. preprint and published version)
    selection: str


class PaperRef(BaseModel):
    paper_id: uuid.UUID
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    url: str | None
    content_kind: str


class Report(BaseModel):
    schema_version: int = REPORT_SCHEMA_VERSION
    generator_version: str = GENERATOR_VERSION
    generated_at: datetime
    question: str
    scope: Scope
    bottom_line: str
    overall_strength: Strength
    strength_definitions: dict[Strength, str] = STRENGTH_DEFINITIONS
    key_findings: list[Finding]
    limitations: list[str]
    missing_information: list[str]
    unresolved_questions: list[str]
    comparison: Comparison
    papers: list[PaperRef]
    versions: dict[str, str]
