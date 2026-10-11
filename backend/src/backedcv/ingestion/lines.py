"""Turn raw text rows into CVLine objects with stable IDs."""

import re
from dataclasses import dataclass

from backedcv.domain.models import CVLine
from backedcv.domain.models.cv import LineSource
from backedcv.domain.text import fold

BULLET_GLYPHS = "•▪●◦‣⁃■□∙·*>-–"
_BULLET = re.compile(r"^[\s•▪●◦‣⁃■□∙·*>-]+\s*")
_BULLET_START = re.compile(r"^(?:[•▪●◦‣⁃■□∙]|[-–*·>](?:\s|$))")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # tab, newline and CR are kept
_MAX_GAP = 0.5  # widest vertical gap inside one paragraph, in multiples of the font size
_EDGE_SHARE = 0.25  # share of the block width a line may stop short of the block's widest end
_INDENT_TOLERANCE = 3.0  # points
_SIZE_TOLERANCE = 0.5  # points
_CAPS_MAX = 40  # characters: a longer all-caps line is running text, not a heading
_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*$")
_HYPHEN_END = re.compile(r"\w-$")
_OPEN_END = re.compile(r"(?:[,&/-]|\b(?:and|or|of|for|with|in|at|to|the))$", re.IGNORECASE)
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_YEAR = rf"(?:{_MONTH}\s+)?(?:\d{{1,2}}/)?(?:19|20)\d{{2}}"
_RANGE = rf"{_YEAR}\s*(?:-|\bto\b)\s*(?:present|current|now|today|{_YEAR})\b"
_DATE_LINE = re.compile(
    rf"^\s*{_RANGE}(?=[\s,|·]|$)|(?:^|[\s,|·(]){_RANGE}[\s.,)]*$|^\s*{_YEAR}\s*$", re.IGNORECASE
)
_CONTACT = re.compile(
    r"@|https?://|www\.|\b[\w-]+\.(?:com|org|net|io|dev|ai|es|co|me|info)\b"
    r"|\b(?:linkedin|github)\b|\+\d[\d\s().-]{5,}|\b\d{3}[\s.-]\d{3}[\s.-]\d{3,4}\b",
    re.IGNORECASE,
)


@dataclass
class RawLine:
    text: str
    page: int = 1
    source: LineSource = "body"
    bold: bool = False
    size: float | None = None


@dataclass
class Fragment:
    """One physical line of a PDF column, with where it sits on the page."""

    text: str
    page: int
    x0: float
    x1: float
    top: float
    bottom: float
    text_x0: float  # where the words start after a bullet glyph; x0 when there is none
    size: float
    bold: bool
    heading: bool  # bold, or bigger than the running text of its page


def clean(text: str) -> str:
    """Drop control characters, fold spacing and leading bullets; keeps the words as written."""
    text = fold(_CONTROL.sub("", text))
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


def join_fragments(fragments: list[Fragment]) -> list[RawLine]:
    """Rebuild the logical lines of one column block from its physical lines, top to bottom."""
    reach = _reach(fragments)
    groups: list[list[Fragment]] = []
    for fragment in fragments:
        if groups and _continues(groups[-1], fragment, reach):
            groups[-1].append(fragment)
        else:
            groups.append([fragment])
    return [_merge(group) for group in groups]


def _reach(fragments: list[Fragment]) -> float:
    """The x a line must reach to run on into the next one: close to the block's widest line end."""
    if not fragments:
        return 0.0
    right = max(f.x1 for f in fragments)
    return right - _EDGE_SHARE * (right - min(f.x0 for f in fragments))


def _continues(group: list[Fragment], nxt: Fragment, reach: float) -> bool:
    """Whether the next physical line goes on with the logical line that `group` is building."""
    first, last = group[0], group[-1]
    if abs(nxt.size - last.size) > _SIZE_TOLERANCE or nxt.top - last.bottom > _MAX_GAP * nxt.size:
        return False
    # A wrapped title may stop short of the block's edge, so the reach rule does not apply to it.
    if _is_title_wrap(first, last, nxt):
        return True
    if last.x1 < reach:  # a line that stops well short of the block's edge is complete
        return False
    if _is_break(last) or _is_break(nxt) or _is_bullet(nxt.text):
        return False
    unfinished = _SENTENCE_END.search(fold(last.text)) is None
    if _is_bullet(first.text):
        if abs(nxt.x0 - first.text_x0) <= _INDENT_TOLERANCE:  # hangs under the bullet's text
            return True
        # A "•" typed as text wraps to the margin; there, only an unfinished line runs on.
        return unfinished and abs(nxt.x0 - first.x0) <= _INDENT_TOLERANCE
    if abs(nxt.x0 - first.x0) > _INDENT_TOLERANCE:
        return False
    return unfinished or _starts_lower(nxt.text)


def _is_title_wrap(first: Fragment, last: Fragment, nxt: Fragment) -> bool:
    """A bold title that wraps in a narrow column: the next bold line finishes its open line."""
    return (
        last.bold
        and nxt.bold
        and abs(nxt.x0 - first.x0) <= _INDENT_TOLERANCE
        and _OPEN_END.search(fold(last.text)) is not None
        and not _is_bullet(nxt.text)
        and not _stands_alone(last.text)
        and not _stands_alone(nxt.text)
    )


def _is_break(fragment: Fragment) -> bool:
    """Headings, date lines and contact lines always stand alone."""
    return fragment.heading or _stands_alone(fragment.text)


def _stands_alone(text: str) -> bool:
    """Short all-caps, date and contact lines are never run on, whatever their font."""
    return (
        _is_caps_heading(text)
        or _DATE_LINE.search(fold(text)) is not None
        or _CONTACT.search(text) is not None
    )


def _is_caps_heading(text: str) -> bool:
    """A short all-capitals line without a sentence end, such as SKILLS or EXPERIENCE."""
    letters = [char for char in text if char.isalpha()]
    if not letters or any(char.islower() for char in letters):
        return False
    if len(letters) < 4 and len(text.split()) == 1:  # one acronym such as SQL or AWS
        return False
    return len(text) <= _CAPS_MAX and _SENTENCE_END.search(text) is None


def _is_bullet(text: str) -> bool:
    return _BULLET_START.match(text.lstrip()) is not None


def _starts_lower(text: str) -> bool:
    return next((char for char in text if char.isalpha()), "").islower()


def _merge(group: list[Fragment]) -> RawLine:
    text = group[0].text
    for fragment in group[1:]:
        text = _join(text, fragment.text)
    first = group[0]
    return RawLine(text=text, page=first.page, bold=first.bold, size=first.size or None)


def _join(left: str, right: str) -> str:
    """Join with a space; a hyphen that ends a line joins a lowercase word with no space."""
    if _HYPHEN_END.search(fold(left)) and _starts_lower(right):
        return left + right
    return f"{left} {right}"
