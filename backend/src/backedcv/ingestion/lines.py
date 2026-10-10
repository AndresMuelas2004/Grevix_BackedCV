"""Turn raw text rows into CVLine objects with stable IDs."""

import re
from dataclasses import dataclass

from backedcv.domain.models import CVLine
from backedcv.domain.models.cv import LineSource
from backedcv.domain.text import fold

_BULLET = re.compile(r"^[\s•▪●◦‣⁃■□∙·*>-]+\s*")


@dataclass
class RawLine:
    text: str
    page: int = 1
    source: LineSource = "body"
    bold: bool = False
    size: float | None = None


def clean(text: str) -> str:
    """Fold spacing and drop leading bullet glyphs; keeps the words exactly as written."""
    text = fold(text)
    stripped = _BULLET.sub("", text)
    return stripped if stripped else text


def number_lines(rows: list[RawLine]) -> list[CVLine]:
    lines: list[CVLine] = []
    for row in rows:
        text = clean(row.text)
        if not text or not re.search(r"\w", text):
            continue
        lines.append(
            CVLine(
                id=f"L{len(lines) + 1:03d}",
                text=text,
                page=row.page,
                source=row.source,
                bold=row.bold,
                size=row.size,
            )
        )
    return lines
