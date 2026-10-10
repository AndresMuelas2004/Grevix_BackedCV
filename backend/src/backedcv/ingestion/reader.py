"""Validate an upload, pick the right reader and return numbered lines."""

from dataclasses import dataclass
from pathlib import PurePath

from backedcv.domain.models import CVLine
from backedcv.ingestion.docx_reader import read_docx
from backedcv.ingestion.errors import IngestionError
from backedcv.ingestion.lines import RawLine, number_lines
from backedcv.ingestion.pdf_reader import read_pdf

MAX_BYTES = 4 * 1024 * 1024
MAX_PAGES = 6
MAX_CV_CHARS = 30_000


@dataclass
class ReadResult:
    lines: list[CVLine]
    kind: str  # pdf / docx / text
    filename: str | None
    size: int


def read_cv(data: bytes, filename: str | None) -> ReadResult:
    if len(data) > MAX_BYTES:
        raise IngestionError("cv_too_large", "This file is larger than 4 MB.", status=413)
    kind = _detect_kind(data, filename)
    rows = read_pdf(data, MAX_PAGES) if kind == "pdf" else read_docx(data)
    return ReadResult(_finish(rows), kind, filename, len(data))


def read_cv_text(text: str) -> ReadResult:
    rows = [RawLine(text=row) for row in text.splitlines()]
    return ReadResult(_finish(rows), "text", None, len(text.encode()))


def _detect_kind(data: bytes, filename: str | None) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:4] == b"PK\x03\x04":
        return "docx"
    suffix = PurePath(filename or "").suffix.lower()
    if suffix == ".doc":
        raise IngestionError(
            "cv_unsupported_type",
            "Old .doc files are not supported.",
            "Save it as .docx or PDF, or paste the text.",
            status=415,
        )
    raise IngestionError(
        "cv_unsupported_type", "Upload a PDF or DOCX file, or paste the text.", status=415
    )


def _finish(rows: list[RawLine]) -> list[CVLine]:
    lines = number_lines(rows)
    if not lines:
        raise IngestionError("cv_empty", "No text was found in this CV.")
    if sum(len(line.text) for line in lines) > MAX_CV_CHARS:
        raise IngestionError("cv_too_long", f"This CV is longer than {MAX_CV_CHARS:,} characters.")
    return lines
