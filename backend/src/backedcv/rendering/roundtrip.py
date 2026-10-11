"""Read the rendered PDF back with our own reader and report the lines that did not survive."""

import re
from collections.abc import Iterator

from backedcv.domain.models import CVDocument
from backedcv.domain.text import fold_lower
from backedcv.ingestion import IngestionError, read_cv
from backedcv.ingestion.lines import clean

_BULLET_GLYPHS = re.compile("[•▪●◦‣⁃■□∙·]")


def roundtrip_check(pdf: bytes, doc: CVDocument) -> tuple[bool, list[str]]:
    """Return (ok, issues). An issue is a document line whose words are missing from the PDF."""
    try:
        extracted = read_cv(pdf, "cv.pdf").lines
    except IngestionError as error:
        return False, [f"The PDF could not be read back: {error.title}"]

    stream = " ".join(" ".join(_tokens(line.text)) for line in extracted)
    stream = f" {stream} "
    issues = []
    for text in _document_lines(doc):
        tokens = _tokens(text)
        if tokens and f" {' '.join(tokens)} " not in stream:
            issues.append(text)
    return not issues, issues


def _tokens(text: str) -> list[str]:
    """Lowercase words in order. Spacing and bullet glyphs are dropped on both sides."""
    return _BULLET_GLYPHS.sub(" ", fold_lower(clean(text))).split()


def _document_lines(doc: CVDocument) -> Iterator[str]:
    if doc.contact.name:
        yield doc.contact.name
    yield from doc.contact.details
    for section in doc.sections:
        yield section.heading
        for item in section.items:
            for line in item.lines:
                yield line.text
