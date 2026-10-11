"""Recruiter tips: advice that stays outside the score, drawn from the same parsed CV."""

import re

from backedcv.domain.dates import parse_date_range
from backedcv.domain.models import CVLine, ParsedCV, ParseWarning

MIN_WORDS = 250
MAX_WORDS = 900
SENIOR_YEARS = 10  # longer CVs are fine for people with this much experience
LONG_LINE_WORDS = 40
_NUMBER = re.compile(r"\d")


def recruiter_tips(cv: ParsedCV) -> list[ParseWarning]:
    """Tips on numbers in bullets, CV length and long paragraphs. All are info only."""
    return [*_bullets_without_numbers(cv), *_word_count(cv), *_long_lines(cv)]


def _experience_bullets(cv: ParsedCV) -> list[CVLine]:
    """Description lines of job entries: not the title line, not a date line, not very short."""
    by_id = {line.id: line for line in cv.lines}
    bullets: list[CVLine] = []
    for entry in cv.entries:
        if entry.kind != "job":
            continue
        for line_id in entry.line_ids[1:]:
            line = by_id.get(line_id)
            if line is None or _is_date_line(line.text) or len(line.text.split()) < 4:
                continue
            bullets.append(line)
    return bullets


def _is_date_line(text: str) -> bool:
    parsed = parse_date_range(text)
    return parsed is not None and (parsed.end is not None or parsed.end_is_present)


def _bullets_without_numbers(cv: ParsedCV) -> list[ParseWarning]:
    bullets = _experience_bullets(cv)
    if len(bullets) < 3:
        return []
    numbered = [line for line in bullets if _NUMBER.search(line.text)]
    if len(numbered) * 2 >= len(bullets):
        return []
    missing = [line.id for line in bullets if not _NUMBER.search(line.text)]
    return [
        ParseWarning(
            code="tip_bullets_without_numbers",
            severity="info",
            message=(
                f"Only {len(numbered)} of your {len(bullets)} experience lines have a number; "
                "add figures such as percentages, team sizes or money saved."
            ),
            line_ids=missing,
        )
    ]


def _word_count(cv: ParsedCV) -> list[ParseWarning]:
    words = sum(len(line.text.split()) for line in cv.lines)
    if words < MIN_WORDS:
        return [
            ParseWarning(
                code="tip_word_count",
                severity="info",
                message=(
                    f"Your CV has {words} words; aim for at least {MIN_WORDS} so recruiters "
                    "see enough of your experience."
                ),
            )
        ]
    if words > MAX_WORDS and cv.total_years is not None and cv.total_years < SENIOR_YEARS:
        return [
            ParseWarning(
                code="tip_word_count",
                severity="info",
                message=(
                    f"Your CV has {words} words for about {cv.total_years:g} years of experience; "
                    f"aim for {MAX_WORDS} or fewer."
                ),
            )
        ]
    return []


def _long_lines(cv: ParsedCV) -> list[ParseWarning]:
    ids = [line.id for line in cv.lines if len(line.text.split()) > LONG_LINE_WORDS]
    if not ids:
        return []
    return [
        ParseWarning(
            code="tip_long_paragraph",
            severity="info",
            message=(
                f"Some lines run past {LONG_LINE_WORDS} words; split long paragraphs into short "
                "bullets."
            ),
            line_ids=ids,
        )
    ]
