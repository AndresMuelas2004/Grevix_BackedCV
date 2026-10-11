"""Read the rendered PDF back with our own reader and report the lines that did not survive."""

from collections.abc import Iterator

from backedcv.domain.models import CVDocument
from backedcv.domain.text import fold_lower
from backedcv.ingestion import IngestionError, read_cv


def roundtrip_check(pdf: bytes, doc: CVDocument) -> tuple[bool, list[str]]:
    """Return (ok, issues). An issue is a document line whose letters and digits are missing from
    the PDF text. Line breaks, hyphens and punctuation are ignored, so a wrapped link still matches.
    """
    try:
        extracted = read_cv(pdf, "cv.pdf").lines
    except IngestionError as error:
        return False, [f"The PDF could not be read back: {error.title}"]

    stream = _squash(" ".join(line.text for line in extracted))
    issues: list[str] = []
    for text in _document_lines(doc):
        squashed = _squash(text)
        if squashed and squashed not in stream:
            issues.append(text)
    return not issues, issues


def _squash(text: str) -> str:
    """Lowercase letters and digits only, in order. Spaces, breaks and punctuation are dropped."""
    return "".join(char for char in fold_lower(text) if char.isalnum())


def _document_lines(doc: CVDocument) -> Iterator[str]:
    if doc.contact.name:
        yield doc.contact.name
    if doc.contact.headline:
        yield doc.contact.headline
    yield from doc.contact.details
    for section in doc.sections:
        yield section.heading
        for item in section.items:
            for line in item.lines:
                yield line.text
