"""Deterministic date parsing for English and Spanish CVs. Code, not the model, owns dates."""

import re
from dataclasses import dataclass
from datetime import date

from backedcv.domain.text import fold_lower

MONTHS: dict[str, int] = {
    # English
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    # Spanish
    "ene": 1, "enero": 1, "febrero": 2, "marzo": 3, "abr": 4, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "ago": 8, "agosto": 8, "set": 9,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11,
    "dic": 12, "diciembre": 12,
}  # fmt: skip

_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))
_YEAR = r"(?:19|20)\d{2}"
_PRESENT = (
    r"present|current|currently|now|today|ongoing"
    r"|la actualidad|actualidad|actual|presente|hoy"
)
_SINCE = r"since|desde"

_TOKEN = re.compile(
    rf"(?P<named>\b(?P<mon>{_MONTH_ALT})\.?,?\s+(?:de\s+|of\s+)?(?P<y1>{_YEAR})\b)"
    rf"|(?P<iso>\b(?P<y2>{_YEAR})-(?P<m2>0[1-9]|1[0-2])\b)"
    rf"|(?P<num>\b(?P<m3>0?[1-9]|1[0-2])\s*[/.-]\s*(?P<y3>{_YEAR})\b)"
    rf"|(?P<year>\b(?P<y4>{_YEAR})\b)"
    rf"|(?P<present>\b(?:{_PRESENT})\b)"
)
_SINCE_RE = re.compile(rf"\b(?:{_SINCE})\b")


@dataclass(frozen=True)
class YearMonth:
    year: int
    month: int | None  # None when only the year is known

    def index(self, default_month: int = 1) -> int:
        return self.year * 12 + (self.month or default_month) - 1

    def iso(self) -> str:
        return f"{self.year:04d}-{self.month or 1:02d}"


@dataclass(frozen=True)
class DateRange:
    start: YearMonth
    end: YearMonth | None  # None for a single date (e.g. a graduation year)
    end_is_present: bool = False

    def end_iso(self) -> str | None:
        if self.end_is_present:
            return "present"
        return self.end.iso() if self.end else None


def _tokens(text: str) -> list[YearMonth | str]:
    found: list[YearMonth | str] = []
    for m in _TOKEN.finditer(text):
        if m.group("named"):
            found.append(YearMonth(int(m.group("y1")), MONTHS[m.group("mon")]))
        elif m.group("iso"):
            found.append(YearMonth(int(m.group("y2")), int(m.group("m2"))))
        elif m.group("num"):
            found.append(YearMonth(int(m.group("y3")), int(m.group("m3"))))
        elif m.group("year"):
            found.append(YearMonth(int(m.group("y4")), None))
        elif m.group("present"):
            found.append("present")
    return found


def parse_date_range(text: str) -> DateRange | None:
    """Find the first date or date range in a line ("Jan 2020 - Present", "03/2019 - 2021")."""
    folded = fold_lower(text)
    tokens = _tokens(folded)
    dates = [t for t in tokens if isinstance(t, YearMonth)]
    if not dates:
        return None
    start = dates[0]
    after_start = tokens[tokens.index(start) + 1 :]
    for token in after_start:
        if token == "present":
            return DateRange(start, None, end_is_present=True)
        if isinstance(token, YearMonth):
            if token.index(12) >= start.index(1):
                return DateRange(start, token)
            break
    if _SINCE_RE.search(folded):
        return DateRange(start, None, end_is_present=True)
    return DateRange(start, None)


def _interval(r: DateRange, today: date) -> tuple[int, int] | None:
    """Half-open month interval [start, end) for a range; None for single dates."""
    start = r.start.index(1)
    if r.end_is_present:
        end = today.year * 12 + today.month  # the current month counts
    elif r.end is None:
        return None
    elif r.start.month is not None and r.end.month is not None:
        end = r.end.index() + 1  # "Jan 2020 - Mar 2020" is three months
    else:
        end = r.end.index(1)  # year-only: "2019 - 2021" counts as two years
    return (start, end) if end > start else None


def total_months(ranges: list[DateRange], today: date) -> int:
    """Months covered by the union of ranges, so overlapping jobs are not counted twice."""
    intervals = sorted(i for r in ranges if (i := _interval(r, today)))
    total, current_start, current_end = 0, None, None
    for start, end in intervals:
        if current_end is None or start > current_end:
            if current_end is not None:
                total += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        total += current_end - current_start
    return total


def years_from_months(months: int) -> float:
    return round(months / 12, 1)
