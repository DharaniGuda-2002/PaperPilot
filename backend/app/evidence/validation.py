"""Deterministic checks for extracted evidence (checks-v1).

Each check returns pass/fail with details; a record is `verified` only if
every check passes, otherwise `rejected` (kept, not deleted, for
transparency). Checks never consult a model.
"""

import re
from dataclasses import dataclass
from typing import Any

VALIDATOR_VERSION = "checks-v1"

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class CheckResult:
    rule: str
    passed: bool
    details: str


def validate(
    *,
    passage: str,
    chunk_text: str,
    chunk_page: int | None,
    claimed_page: int | None,
    document_page_count: int | None,
    value: dict[str, Any],
) -> list[CheckResult]:
    return [
        _passage_in_source(passage, chunk_text),
        _page_consistent(chunk_page, claimed_page, document_page_count),
        _numbers_in_passage(value, passage),
        _value_in_range(value),
    ]


def _passage_in_source(passage: str, chunk_text: str) -> CheckResult:
    ok = bool(passage) and passage in chunk_text
    return CheckResult(
        "passage_in_source",
        ok,
        "exact quotation found in stored text"
        if ok
        else "passage not found verbatim in stored text",
    )


def _page_consistent(
    chunk_page: int | None, claimed: int | None, page_count: int | None
) -> CheckResult:
    if claimed is None:
        ok = chunk_page is None
        return CheckResult(
            "page_reference",
            ok,
            "no page (abstract)" if ok else "chunk has a page but none was cited",
        )
    ok = claimed == chunk_page and page_count is not None and 1 <= claimed <= page_count
    return CheckResult(
        "page_reference",
        ok,
        f"page {claimed} of {page_count}"
        if ok
        else f"page {claimed} does not match chunk page {chunk_page}/{page_count}",
    )


def _numbers_in_passage(value: dict[str, Any], passage: str) -> CheckResult:
    claimed = [
        v for k, v in value.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    present = {float(n) for n in _NUMBER.findall(passage)}
    missing = [v for v in claimed if float(v) not in present]
    return CheckResult(
        "numbers_in_passage",
        not missing,
        "all numbers appear in the passage" if not missing else f"not in passage: {missing}",
    )


def _value_in_range(value: dict[str, Any]) -> CheckResult:
    if "metric" not in value:
        return CheckResult("value_range", True, "not a metric")
    number, unit = value.get("value"), value.get("unit")
    if not isinstance(number, (int, float)):
        return CheckResult("value_range", False, "metric without a numeric value")
    limit = 100 if unit == "%" else 1 if unit == "ratio" else None
    if limit is None:
        # The record is marked `uncertain` instead; the quotation itself is still checked.
        return CheckResult("value_range", True, f"unit not stated for {number}; range not checked")
    ok = 0 <= number <= limit
    return CheckResult(
        "value_range", ok, f"{number} within 0..{limit}" if ok else f"{number} outside 0..{limit}"
    )
