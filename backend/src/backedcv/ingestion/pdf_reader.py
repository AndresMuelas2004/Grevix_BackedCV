"""PDF CVs: words with positions and fonts, grouped into lines in reading order."""

import io
from dataclasses import dataclass
from statistics import median

import pdfplumber

from backedcv.ingestion.columns import page_order
from backedcv.ingestion.errors import IngestionError
from backedcv.ingestion.lines import BULLET_GLYPHS, Fragment, RawLine, join_fragments

_BOLD_HINTS = ("bold", "black", "heavy", "semibold", "demi")
_BIGGER = 1.08  # a line this many times the page's running text size is a heading


@dataclass
class PdfRead:
    rows: list[RawLine]
    multi_column: bool  # at least one page was read as two columns


def read_pdf(data: bytes, max_pages: int) -> PdfRead:
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # pdfminer raises several unrelated types
        raise IngestionError("cv_unreadable", "This PDF could not be opened.", str(exc)) from exc

    with pdf:
        if len(pdf.pages) > max_pages:
            raise IngestionError(
                "cv_too_many_pages",
                f"This CV has {len(pdf.pages)} pages; the limit is {max_pages}.",
            )
        rows: list[RawLine] = []
        multi_column = False
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(
                keep_blank_chars=False,
                use_text_flow=False,
                extra_attrs=["fontname", "size"],
                return_chars=True,
            )
            order = page_order(words, float(page.width))
            multi_column = multi_column or order.multi_column
            body = _body_size(words)
            for block in order.blocks:
                rows.extend(join_fragments(_group_lines(block, page_number, body)))

    if not rows:
        raise IngestionError(
            "cv_image_only",
            "No text could be read from this PDF.",
            "It looks like a scanned image. Paste the CV text instead.",
        )
    return PdfRead(rows=rows, multi_column=multi_column)


def _body_size(words: list[dict]) -> float:
    """Median font size of the page: the size of its running text."""
    sizes = [float(w["size"]) for w in words if w.get("size")]
    return median(sizes) if sizes else 0.0


def _group_lines(words: list[dict], page_number: int, body: float) -> list[Fragment]:
    """Words whose vertical positions overlap form one physical line; lines run top to bottom."""
    words = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    groups: list[list[dict]] = []
    for word in words:
        if groups:
            last = groups[-1]
            ref_top = median(w["top"] for w in last)
            tolerance = max(2.0, 0.4 * float(word.get("size") or 10))
            if abs(word["top"] - ref_top) <= tolerance:
                last.append(word)
                continue
        groups.append([word])

    fragments: list[Fragment] = []
    for group in groups:
        group.sort(key=lambda w: w["x0"])
        fonts = [str(w.get("fontname", "")).lower() for w in group]
        bold = all(any(h in f for h in _BOLD_HINTS) for f in fonts)
        size = round(median(float(w.get("size") or 0) for w in group), 1)
        fragments.append(
            Fragment(
                text=" ".join(w["text"] for w in group),
                page=page_number,
                x0=min(w["x0"] for w in group),
                x1=max(w["x1"] for w in group),
                top=min(w["top"] for w in group),
                bottom=max(w["bottom"] for w in group),
                text_x0=_text_x0(group),
                size=size,
                bold=bold,
                heading=bold or (body > 0 and size >= body * _BIGGER),
            )
        )
    return fragments


def _text_x0(group: list[dict]) -> float:
    """Left edge of the first letter or digit, so a bullet glyph in front of it is skipped."""
    chars = sorted((c for w in group for c in w.get("chars", [])), key=lambda c: c["x0"])
    for char in chars:
        if char["text"].strip() and char["text"] not in BULLET_GLYPHS:
            return float(char["x0"])
    return float(min(w["x0"] for w in group))
