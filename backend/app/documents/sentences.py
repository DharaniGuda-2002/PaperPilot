"""Sentence splitting with no PDF or ML dependencies, so it can be imported by
the API image (reports, comparison) as well as the workers."""

import re

# Abbreviations that end with a period but do not end a sentence.
_ABBREVIATIONS = (
    "e.g", "i.e", "et al", "etc", "fig", "figs", "eq", "eqs", "sec", "tab", "vs",
    "no", "cf", "approx", "resp", "ref", "refs", "al",
)  # fmt: skip
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[\"'])")


def split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation, keeping abbreviations and decimals intact."""
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        before = text[start : match.start()]
        last_word = before.rsplit(" ", 1)[-1].rstrip(".").lower()
        if last_word in _ABBREVIATIONS:
            continue
        sentences.append(before.strip())
        start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return [s for s in sentences if s]
