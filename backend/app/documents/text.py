"""PDF text extraction, cleanup, sentence splitting, and page-aware chunking.

PDF text is untrusted data. It is stored and searched, never executed or
interpreted as instructions.
"""

import re
from dataclasses import dataclass

import pymupdf

from app.documents.sentences import split_sentences

EXTRACTOR = "pymupdf"
# Bump the suffix when cleanup or chunking changes, so stored text is traceable.
EXTRACTOR_VERSION = f"{pymupdf.VersionBind}-pp2"
MAX_PAGES = 60
CHUNK_TARGET_CHARS = 900  # about 200 tokens; the embedding model reads at most 256
CHUNK_MAX_CHARS = 1200

_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_SPACES = re.compile(r"[ \t\f\v\u00a0]+")
# "References" alone, or at the start of a paragraph followed by the first citation.
_REFERENCES_HEADING = re.compile(
    r"^\s*(references|bibliography)\s*(?:$|(?=\[\d+\]|\d+\.\s|[A-Z][\w'-]+,))",
    re.IGNORECASE | re.MULTILINE,
)


class ExtractionError(Exception):
    """The PDF could not be read (corrupt, encrypted, or no text layer)."""


@dataclass(frozen=True)
class PageText:
    number: int  # 1-based, as printed by PDF viewers
    text: str


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    page_number: int | None
    text: str


def extract_pages(pdf: bytes, max_pages: int = MAX_PAGES) -> tuple[list[PageText], int]:
    """Return cleaned text per page (up to max_pages) and the document's page count."""
    try:
        document = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several types for bad input
        raise ExtractionError(f"cannot open PDF: {type(exc).__name__}") from exc
    with document:
        if document.needs_pass:
            raise ExtractionError("PDF is encrypted")
        pages = [
            PageText(number=index + 1, text=clean_text(_page_text(document[index])))
            for index in range(min(document.page_count, max_pages))
        ]
        page_count = document.page_count
    if not any(page.text for page in pages):
        raise ExtractionError("no extractable text (scanned PDF without a text layer?)")
    return drop_references(pages), page_count


def _page_text(page: pymupdf.Page) -> str:
    """Text blocks in reading order for one- and two-column layouts: blocks that
    start in the left half come first (top to bottom), then the right column.
    Plain `sort=True` reads straight across both columns and mixes them."""
    middle = page.rect.width / 2
    blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
    blocks.sort(key=lambda b: (0 if b[0] < middle - 10 else 1, b[1], b[0]))
    return "\n\n".join(b[4] for b in blocks)


def clean_text(raw: str) -> str:
    text = raw.replace("\x00", "")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # "detec-\ntion" -> "detection"
    paragraphs = [
        _SPACES.sub(" ", " ".join(line.strip() for line in block.splitlines())).strip()
        for block in re.split(r"\n\s*\n", text)
    ]
    return "\n\n".join(p for p in paragraphs if p)


def drop_references(pages: list[PageText]) -> list[PageText]:
    """Cut text after a References heading in the second half of the document.
    Reference lists name many methods and datasets that the paper did not use."""
    start = len(pages) // 2
    for index in range(start, len(pages)):
        match = _REFERENCES_HEADING.search(pages[index].text)
        if match:
            head = PageText(pages[index].number, pages[index].text[: match.start()].strip())
            return [*pages[:index], head]
    return pages


def chunk_pages(pages: list[PageText]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for text in _pack(page.text):
            chunks.append(Chunk(len(chunks), page.number, text))
    return chunks


def chunk_abstract(abstract: str) -> list[Chunk]:
    return [Chunk(i, None, text) for i, text in enumerate(_pack(clean_text(abstract)))]


def _pack(text: str) -> list[str]:
    """Group paragraphs (or sentences of long paragraphs) into chunks near the target size."""
    units: list[str] = []
    for paragraph in text.split("\n\n"):
        if len(paragraph) <= CHUNK_MAX_CHARS:
            units.append(paragraph)
        else:
            units.extend(_hard_wrap(s) for s in split_sentences(paragraph))
    packed: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + 1 + len(unit) > CHUNK_TARGET_CHARS:
            packed.append(current)
            current = unit
        else:
            current = f"{current} {unit}".strip()
    if current:
        packed.append(current)
    return packed


def _hard_wrap(sentence: str) -> str:
    """A single sentence longer than the max (tables, run-on extraction) is truncated
    at a word boundary rather than split, so passages stay whole sentences."""
    if len(sentence) <= CHUNK_MAX_CHARS:
        return sentence
    return sentence[:CHUNK_MAX_CHARS].rsplit(" ", 1)[0]
