"""Extraction and chunking tests. PDFs are generated in-test with PyMuPDF and
contain synthetic fixture text, not real papers."""

import pymupdf
import pytest

from app.documents.text import (
    CHUNK_MAX_CHARS,
    ExtractionError,
    PageText,
    chunk_abstract,
    chunk_pages,
    clean_text,
    drop_references,
    extract_pages,
    split_sentences,
)


def make_pdf(pages: list[str]) -> bytes:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=10)
    data: bytes = document.tobytes()
    document.close()
    return data


def test_extracts_text_per_page_with_page_numbers() -> None:
    pdf = make_pdf(
        [
            "Introduction. Fixture paper about fraud detection.",
            "Results. The GNN achieves an AUC of 0.921 on the fixture dataset.",
        ]
    )
    pages, page_count = extract_pages(pdf)
    assert page_count == 2
    assert [p.number for p in pages] == [1, 2]
    assert "AUC of 0.921" in pages[1].text


def test_page_limit_is_applied() -> None:
    pages, page_count = extract_pages(make_pdf([f"Page {i} text." for i in range(5)]), max_pages=3)
    assert page_count == 5
    assert len(pages) == 3


@pytest.mark.parametrize("data", [b"not a pdf", b"%PDF-1.7 truncated"])
def test_corrupt_pdf_raises(data: bytes) -> None:
    with pytest.raises(ExtractionError):
        extract_pages(data)


def test_pdf_without_text_raises() -> None:
    document = pymupdf.open()
    document.new_page()
    with pytest.raises(ExtractionError, match="no extractable text"):
        extract_pages(document.tobytes())


def test_clean_text_joins_hyphenated_line_breaks_and_lines() -> None:
    raw = "Fraud detec-\ntion with graph\nneural networks.\n\nSecond   paragraph.\x00"
    assert clean_text(raw) == "Fraud detection with graph neural networks.\n\nSecond paragraph."


def test_references_are_dropped_only_in_second_half() -> None:
    pages = [
        PageText(1, "References\n\nThis early heading is part of related work."),
        PageText(2, "Method text."),
        PageText(3, "Conclusion text.\n\nReferences\n\n[1] Some cited paper."),
        PageText(4, "[2] Another cited paper."),
    ]
    result = drop_references(pages)
    assert [p.number for p in result] == [1, 2, 3]
    assert result[2].text == "Conclusion text."


def test_sentence_split_keeps_abbreviations_and_decimals() -> None:
    text = (
        "Liu et al. propose GraphConsis, e.g. for fraud. It reaches 0.92 AUC (Fig. 3). "
        "Results improve. However, splits differ."
    )
    assert split_sentences(text) == [
        "Liu et al. propose GraphConsis, e.g. for fraud.",
        "It reaches 0.92 AUC (Fig. 3).",
        "Results improve.",
        "However, splits differ.",
    ]


def test_chunks_never_cross_pages_and_respect_size() -> None:
    long_paragraph = " ".join(f"Sentence {i} about fraud detection results." for i in range(80))
    pages = [PageText(1, long_paragraph), PageText(2, "Short page.")]
    chunks = chunk_pages(pages)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert {c.page_number for c in chunks} == {1, 2}
    assert chunks[-1].text == "Short page."
    assert all(len(c.text) <= CHUNK_MAX_CHARS for c in chunks)
    # Every sentence is preserved verbatim in some chunk (passages stay quotable).
    joined = " ".join(c.text for c in chunks if c.page_number == 1)
    assert "Sentence 79 about fraud detection results." in joined


def test_abstract_chunks_have_no_page() -> None:
    chunks = chunk_abstract("A short fixture abstract.")
    assert [(c.page_number, c.text) for c in chunks] == [(None, "A short fixture abstract.")]


def test_two_column_pages_are_read_column_by_column() -> None:
    """Regression: plain sorted extraction interleaved the lines of the two columns."""
    document = pymupdf.open()
    page = document.new_page()
    left = "Left column first sentence. Left column second sentence continues here."
    right = "Right column first sentence. Right column second sentence continues here."
    page.insert_textbox(pymupdf.Rect(40, 60, 290, 400), left, fontsize=10)
    page.insert_textbox(pymupdf.Rect(310, 60, 560, 400), right, fontsize=10)
    pages, _ = extract_pages(document.tobytes())
    text = pages[0].text
    assert text.index("Left column second") < text.index("Right column first")


def test_references_heading_followed_by_citation_is_detected() -> None:
    pages = [
        PageText(1, "Intro."),
        PageText(2, "Results.\n\nREFERENCES [1] A. Author. 2020. A cited paper."),
    ]
    assert drop_references(pages)[-1].text == "Results."
