"""PDF CVs: words with positions and fonts, grouped into lines in reading order."""

import io
from statistics import median

import pdfplumber

from backedcv.ingestion.errors import IngestionError
from backedcv.ingestion.lines import RawLine

_BOLD_HINTS = ("bold", "black", "heavy", "semibold", "demi")


def read_pdf(data: bytes, max_pages: int) -> list[RawLine]:
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
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(
                keep_blank_chars=False, use_text_flow=False, extra_attrs=["fontname", "size"]
            )
            rows.extend(_group_lines(words, page_number))

    if not rows:
        raise IngestionError(
            "cv_image_only",
            "No text could be read from this PDF.",
            "It looks like a scanned image. Paste the CV text instead.",
        )
    return rows


def _group_lines(words: list[dict], page_number: int) -> list[RawLine]:
    """Words whose vertical positions overlap form one line; lines run top to bottom."""
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

    rows = []
    for group in groups:
        group.sort(key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in group)
        fonts = [str(w.get("fontname", "")).lower() for w in group]
        bold = all(any(h in f for h in _BOLD_HINTS) for f in fonts)
        size = round(median(float(w.get("size") or 0) for w in group), 1)
        rows.append(RawLine(text=text, page=page_number, bold=bold, size=size or None))
    return rows
