"""Reading order for PDF pages with two columns: header rows, then the left column, then the right.

A page is two-column when an empty vertical band (a gutter at least 12 pt wide, between 25% and
75% of the page width) stays empty for most body rows. The header is every row above the first
row with words on both sides of the gutter.
"""

import math
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

MIN_GUTTER = 12.0  # points
_GUTTER_ZONE = (0.25, 0.75)  # share of the page width where a gutter may sit
_CROSS_SHARE = 0.2  # most rows (share) that may put ink in a candidate band, e.g. header lines
_MIN_BODY_ROWS = 4
_CLEAN_SHARE = 0.8  # share of body rows that must leave the gutter empty
_MIN_SIDE_ROWS = 3  # rows with text needed on each side of the gutter
_DATE_SHARE = 0.6  # a side whose rows are mostly years is a date column, not a text column
_FLUSH_SHARE = 0.6  # share of a side's rows that must start at one shared x (flush text)
_FLUSH_TOLERANCE = 3.0  # points
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


@dataclass
class PageOrder:
    blocks: list[list[dict]]  # word groups, each read as its own flow, in reading order
    multi_column: bool


def page_order(words: list[dict], page_width: float) -> PageOrder:
    """Split one page's words into reading blocks: header, left column, right column.

    Words are pdfplumber-style dicts with x0, x1, top, bottom and text. A page without a gutter
    comes back as a single block, in the order it was given.
    """
    rows = _rows(words)
    for band in _candidate_gutters(rows, page_width):
        start = _body_start(rows, band)
        if start is None:
            continue
        mid = sum(band) / 2
        header = [w for row in rows[:start] for w in row]
        body = rows[start:]
        left = [w for row in body for w in row if _center(w) < mid]
        right = [w for row in body for w in row if _center(w) >= mid]
        blocks = [block for block in (header, left, right) if block]
        return PageOrder(blocks=blocks, multi_column=True)
    return PageOrder(blocks=[words] if words else [], multi_column=False)


def _rows(words: list[dict]) -> list[list[dict]]:
    """Words whose tops line up (within a fraction of their height) form one visual row."""
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and word["top"] - rows[-1][0]["top"] <= _tolerance(rows[-1][0]):
            rows[-1].append(word)
        else:
            rows.append([word])
    return rows


def _tolerance(word: dict) -> float:
    return max(2.0, 0.4 * (word["bottom"] - word["top"]))


def _candidate_gutters(rows: list[list[dict]], width: float) -> Iterator[tuple[int, int]]:
    """Bands to test, tightest first: a run of points that at most `level` rows put ink in."""
    cover = _coverage(rows, width)
    allowed = max(1, math.floor(_CROSS_SHARE * len(rows)))
    lo, hi = math.ceil(_GUTTER_ZONE[0] * width), math.floor(_GUTTER_ZONE[1] * width)
    seen: set[tuple[int, int]] = set()
    for level in range(allowed + 1):
        for band in sorted(_runs(cover, lo, hi, 0, level), key=lambda b: b[0] - b[1]):
            if band[1] - band[0] >= MIN_GUTTER and band not in seen:
                seen.add(band)
                yield band


def _coverage(rows: list[list[dict]], width: float) -> list[int]:
    """How many rows put ink in each whole point of the page width."""
    size = math.ceil(width)
    delta = [0] * (size + 1)
    for row in rows:
        for start, end in _ink(row, size):
            delta[start] += 1
            delta[end] -= 1
    cover: list[int] = []
    total = 0
    for change in delta[:size]:
        total += change
        cover.append(total)
    return cover


def _ink(row: list[dict], size: int) -> list[tuple[int, int]]:
    """Whole-point spans where a row has ink, merged so that overlapping words count once."""
    spans: list[tuple[int, int]] = []
    for word in sorted(row, key=lambda w: w["x0"]):
        start = min(max(math.floor(word["x0"]), 0), size)
        end = min(max(math.ceil(word["x1"]), start), size)
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))
    return spans


def _runs(cover: list[int], start: int, end: int, low: int, high: int) -> list[tuple[int, int]]:
    """Maximal [a, b) runs inside [start, end) whose coverage stays between low and high."""
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for point in range(start, end + 1):
        inside = point < end and low <= cover[point] <= high
        if inside and run_start is None:
            run_start = point
        elif not inside and run_start is not None:
            runs.append((run_start, point))
            run_start = None
    return runs


def _body_start(rows: list[list[dict]], band: tuple[int, int]) -> int | None:
    """Index of the first row with words on both sides of the band, if the band holds below it."""
    g0, g1 = band
    start = next((i for i, row in enumerate(rows) if _two_sided(row, g0, g1)), None)
    if start is None or len(rows) - start < _MIN_BODY_ROWS:
        return None
    body = rows[start:]
    clean = sum(1 for row in body if not any(_crosses(w, g0, g1) for w in row))
    if clean < _CLEAN_SHARE * len(body):
        return None
    mid = (g0 + g1) / 2
    left_ok = _is_text_side(body, lambda w: _center(w) < mid)
    right_ok = _is_text_side(body, lambda w: _center(w) >= mid)
    return start if left_ok and right_ok else None


def _is_text_side(body: list[list[dict]], on_side: Callable[[dict], bool]) -> bool:
    """A column is flush text on enough rows, and its rows are not mostly years (dates)."""
    texts: list[str] = []
    starts: list[float] = []
    for row in body:
        side = [w for w in row if on_side(w)]
        if side:
            texts.append(" ".join(w["text"] for w in side))
            starts.append(min(w["x0"] for w in side))
    years = sum(1 for text in texts if _YEAR.search(text))
    if len(texts) < _MIN_SIDE_ROWS or years >= _DATE_SHARE * len(texts):
        return False
    return _flush_share(starts) >= _FLUSH_SHARE


def _flush_share(starts: list[float]) -> float:
    """Share of rows whose text starts within a few points of the most common start."""
    most = max(sum(1 for s in starts if abs(s - anchor) <= _FLUSH_TOLERANCE) for anchor in starts)
    return most / len(starts)


def _two_sided(row: list[dict], g0: float, g1: float) -> bool:
    return any(w["x1"] <= g0 for w in row) and any(w["x0"] >= g1 for w in row)


def _crosses(word: dict, g0: float, g1: float) -> bool:
    return word["x0"] < g1 and word["x1"] > g0


def _center(word: dict) -> float:
    return (word["x0"] + word["x1"]) / 2
