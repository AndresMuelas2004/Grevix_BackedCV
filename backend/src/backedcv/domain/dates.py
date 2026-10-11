"""Deterministic date parsing for English and Spanish CVs. Code, not the model, owns dates."""

import re
from dataclasses import dataclass
from datetime import date

from backedcv.domain.text import fold

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

# Text copied from a PDF often glues a date to the word before it ("Bilbao, SpainApr 2026"). Only
# a capitalised month name followed by a year, or a year itself, is split from a lowercase letter
# before it, so names such as "LangGraph" or "GitHub" stay whole.
_CAPITALISED = "|".join(
    sorted({form for name in MONTHS for form in (name.capitalize(), name.upper())}, key=len)[::-1]
)
_GLUED_MONTH = re.compile(rf"(?<=[a-zà-ÿ])(?=(?:{_CAPITALISED})\.?,?\s*(?:de\s+|of\s+)?{_YEAR}\b)")
# A glued year splits only where a date range goes on ("Spain2026 - Present") or the line ends,
# so names such as "ES2015+" stay whole.
_GLUED_YEAR = re.compile(rf"(?<=[^\W\d_])(?={_YEAR}\b(?:\s*-|\s+(?:to|a|hasta)\b|\s*$))")

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
        """YYYY-MM, or YYYY when only the year is known: a month is never invented."""
        if self.month is None:
            return f"{self.year:04d}"
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True)
class DateRange:
    start: YearMonth
    end: YearMonth | None  # None for a single date (e.g. a graduation year)
    end_is_present: bool = False

    def end_iso(self) -> str | None:
        if self.end_is_present:
            return "present"
        return self.end.iso() if self.end else None

    @property
    def is_period(self) -> bool:
        """A start and an end (or "present"), so it covers some months."""
        return self.end is not None or self.end_is_present

    @property
    def month_unknown(self) -> bool:
        """The start or the end shows only the year."""
        return self.start.month is None or (self.end is not None and self.end.month is None)


def unglue_dates(text: str) -> str:
    """Splits a date glued to the word before it: "SpainApr 2026" reads "Spain Apr 2026"."""
    return _GLUED_YEAR.sub(" ", _GLUED_MONTH.sub(" ", text))


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
    """The first date or date range in a line ("Jan 2020 - Present", "03/2019 - 2021"), also when
    glued to the word before it."""
    folded = unglue_dates(fold(text)).casefold()
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


def _interval(r: DateRange, today: date, longest: bool = False) -> tuple[int, int] | None:
    """Half-open month interval [start, end) for a period, months counted inclusively ("Jan 2020 -
    Mar 2020" is three months; the current month counts for "present"). None for single dates.
    A date that shows only the year takes the month that gives the shortest period ("2019 - 2021"
    runs from December 2019 to January 2021), or the longest one with `longest`."""
    if not r.is_period:
        return None
    current = today.year * 12 + today.month - 1
    if r.start.month is not None:
        start = r.start.index()
    else:
        start = min(r.start.year * 12 + (0 if longest else 11), current)
    if r.end_is_present:
        end = current + 1
    elif r.end.month is not None:
        end = r.end.index() + 1
    elif longest:
        end = min(r.end.year * 12 + 12, current + 1)
    else:
        end = r.end.year * 12 + 1
    if end > start:
        return start, end
    if longest or not r.month_unknown:
        return None
    # Shortest reading of a period inside one year ("2020 - 2020", "Mar 2020 - 2020"): one month.
    return (end - 1, end) if r.start.month is None else (start, start + 1)


def months_in(r: DateRange, today: date, longest: bool = False) -> int:
    """The months one period covers, as total_months counts them."""
    interval = _interval(r, today, longest)
    return interval[1] - interval[0] if interval else 0


def total_months(ranges: list[DateRange], today: date, longest: bool = False) -> int:
    """Months covered by the union of ranges, so overlapping jobs are not counted twice. Dates that
    show only the year count at their shortest (or their longest with `longest`)."""
    intervals = sorted(i for r in ranges if (i := _interval(r, today, longest)))
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
