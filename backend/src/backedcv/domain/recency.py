"""Recency of evidence: when the CV last shows each requirement, and what the posting's own
recency windows ("within the last 5 years") do to a requirement that looks met."""

import re
from collections.abc import Mapping
from datetime import date
from typing import Literal

from backedcv.domain.keywords import contains_term
from backedcv.domain.models import (
    CVEntry,
    JobPosting,
    ParsedCV,
    RecencyBand,
    RecencyCheck,
    RecencyRule,
    Requirement,
    RequirementAssessment,
)
from backedcv.domain.models.screening import clean_prose
from backedcv.domain.text import fold, fold_lower, locate_quote

RECENT_MAX_YEARS = 3.0
AGING_MAX_YEARS = 6.0

_Effect = Literal["none", "warning", "downgraded"]
_CHECKED_STATUSES = frozenset({"met", "partial"})
# General rules (no requirement named) reach only these required requirements.
_GENERAL_CATEGORIES = frozenset({"hard_skill", "experience_years"})
# Recency is about use: only job and project entries date a line. Degrees and certifications do
# not expire, so requirements of these categories, or shown only by such lines, get no check.
DATED_KINDS = frozenset({"job", "project"})
# A language level does not expire either.
_CREDENTIAL_CATEGORIES = frozenset({"education", "certification_license", "language"})
_CREDENTIAL_SECTIONS = frozenset({"education", "certifications"})
_YEAR_MONTH = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])")
_YEAR_ONLY = re.compile(r"\d{4}")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?;])\s+|[\r\n•]+")
_BULLET = re.compile(r"^[\s\-*>]+")
_NUMBER_WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
_NUMBER = "|".join([r"[1-9]\d?", *_NUMBER_WORDS])
# "in / within / during / over the last | past | previous N years", or "within N years".
_WINDOW = re.compile(
    r"\b(?:(?:within|in|during|over)\s+(?:the\s+)?(?:last|past|previous)|within)"
    rf"\s+({_NUMBER})\s+years?\b"
)
# A window whose clause (the text between commas or semicolons) names a graduation or a degree
# is a graduation window: the graduation barrier handles it, so it is no recency rule.
_CLAUSE_BREAKS = ",;"
_GRADUATION = re.compile(r"\b(?:graduat\w*|degrees?|diplomas?)\b")


def line_last_used(cv: ParsedCV, today: date) -> dict[str, str]:
    """Line ID -> YYYY-MM of the newest dated job or project entry it belongs to. Undated lines
    and lines of education entries are absent: a degree's year says nothing about recent use."""
    last_used: dict[str, str] = {}
    for entry in cv.entries:
        month = _entry_month(entry, today) if entry.kind in DATED_KINDS else None
        if month is None:
            continue
        for line_id in entry.line_ids:
            last_used[line_id] = max(month, last_used.get(line_id, month))
    return last_used


def credential_lines(cv: ParsedCV) -> set[str]:
    """Lines of education entries and of education or certification sections."""
    lines = {i for e in cv.entries if e.kind == "education" for i in e.line_ids}
    lines.update(i for s in cv.sections if s.type in _CREDENTIAL_SECTIONS for i in s.line_ids)
    return lines


def _entry_month(entry: CVEntry, today: date) -> str | None:
    """The entry's date: its end ("present" means today), or its start when it has no end. A date
    that shows only the year counts from its January, the older reading."""
    if entry.end and entry.end.strip().casefold() == "present":
        month = f"{today.year:04d}-{today.month:02d}"
    else:
        month = (entry.end or entry.start or "").strip()
    if _YEAR_ONLY.fullmatch(month):
        month = f"{month}-01"
    return month if _YEAR_MONTH.fullmatch(month) else None


def years_since(ym: str, today: date) -> float:
    """Years from a YYYY-MM month to today, to one decimal. A month after today counts as today."""
    year, month = map(int, ym.split("-"))
    months = (today.year - year) * 12 + (today.month - month)
    return round(max(months, 0) / 12, 1)


def band_for(years: float | None) -> RecencyBand:
    """recent up to RECENT_MAX_YEARS, aging up to AGING_MAX_YEARS, stale beyond. None: undated."""
    if years is None:
        return "undated"
    if years <= RECENT_MAX_YEARS:
        return "recent"
    if years <= AGING_MAX_YEARS:
        return "aging"
    return "stale"


def find_recency_rules(job_text: str, job: JobPosting) -> list[RecencyRule]:
    """Explicit recency windows in the posting: one rule per sentence, quoted verbatim.
    A rule names the requirements its sentence mentions; none named makes it a general rule.
    Windows tied to a graduation or a degree are left out."""
    rules: list[RecencyRule] = []
    quotes: set[str] = set()
    for piece in _SENTENCE_BREAK.split(job_text):
        sentence = _BULLET.sub("", fold(piece))
        folded = fold_lower(sentence)
        windows = [
            _number(m.group(1))
            for m in _WINDOW.finditer(folded)
            if not _tied_to_graduation(folded, m.start(), m.end())
        ]
        quote = locate_quote(sentence, job_text) if windows else None
        if quote is None or quote in quotes:
            continue
        quotes.add(quote)
        rules.append(
            RecencyRule(
                quote=quote,
                window_years=float(min(windows)),
                requirement_ids=_mentioned_ids(sentence, job),
                source="rule",
            )
        )
    return rules


def _number(token: str) -> int:
    return int(token) if token.isdigit() else _NUMBER_WORDS.index(token) + 1


def _tied_to_graduation(folded: str, start: int, end: int) -> bool:
    """True when a graduation or degree word shares the window's clause."""
    left, right = start, end
    while left > 0 and folded[left - 1] not in _CLAUSE_BREAKS:
        left -= 1
    while right < len(folded) and folded[right] not in _CLAUSE_BREAKS:
        right += 1
    return _GRADUATION.search(folded[left:right]) is not None


def _mentioned_ids(sentence: str, job: JobPosting) -> list[str]:
    folded = fold_lower(sentence)
    return [req.id for req in job.requirements if _mentions(req, sentence, folded)]


def _mentions(req: Requirement, sentence: str, folded: str) -> bool:
    quote = fold_lower(req.quote)
    if quote and (quote in folded or folded in quote):
        return True
    return any(contains_term(sentence, term) for term in [req.label, *req.terms])


def check_recency(
    job: JobPosting,
    cv: ParsedCV,
    assessments: Mapping[str, RequirementAssessment],
    rules: list[RecencyRule],
    today: date,
) -> dict[str, RecencyCheck]:
    """When the CV last shows each met or partial requirement, against the posting's windows.
    Requirements whose evidence is not a CV line get no check, and neither do degrees,
    certifications and requirements shown only by education or certification lines."""
    last_used = line_last_used(cv, today)
    credentials = credential_lines(cv)
    requirements = {req.id: req for req in job.requirements}
    checks: dict[str, RecencyCheck] = {}
    for rid, assessment in assessments.items():
        req = requirements.get(rid)
        if req is not None and req.category in _CREDENTIAL_CATEGORIES:
            continue
        refs = [ref for ref in _line_refs(assessment) if ref not in credentials]
        # A minimum-years question (incomplete dates) keeps its lines: a window still applies.
        asked_years = assessment.status == "unknown" and assessment.years_check is not None
        if not (assessment.status in _CHECKED_STATUSES or asked_years) or not refs:
            continue
        rule = _strictest_rule(rules, rid, req)
        newest = max((last_used[ref] for ref in refs if ref in last_used), default=None)
        years = None if newest is None else years_since(newest, today)
        checks[rid] = RecencyCheck(
            requirement_id=rid,
            original_status=assessment.status,
            last_used=newest,
            years_since=years,
            band=band_for(years),
            evidence_refs=refs,
            rule=rule,
            within_rule=None if rule is None or years is None else years <= rule.window_years,
            effect=_effect(rule, years),
            explanation=_explain(clean_prose(req.label) if req else "", newest, years, rule),
        )
    return checks


def _line_refs(assessment: RequirementAssessment) -> list[str]:
    """The CV line IDs (L...) behind an assessment, in order, without repeats."""
    return list(dict.fromkeys(e.ref for e in assessment.evidence if e.ref.startswith("L")))


def _strictest_rule(
    rules: list[RecencyRule], rid: str, req: Requirement | None
) -> RecencyRule | None:
    """The smallest window among the rules that name this requirement, plus the general rules
    when the requirement is a required hard skill or years of experience."""
    general = (
        req is not None and req.importance == "required" and req.category in _GENERAL_CATEGORIES
    )
    applicable = [
        rule
        for rule in rules
        if rid in rule.requirement_ids or (general and not rule.requirement_ids)
    ]
    return min(applicable, key=lambda rule: rule.window_years, default=None)


def _effect(rule: RecencyRule | None, years: float | None) -> _Effect:
    if rule is None:
        return "warning" if band_for(years) == "stale" else "none"
    if years is None:
        return "warning"
    return "none" if years <= rule.window_years else "downgraded"


def _explain(label: str, newest: str | None, years: float | None, rule: RecencyRule | None) -> str:
    """One plain sentence: the requirement, the year of its newest evidence and the window. A
    requirement without a label is named in words, never by its ID."""
    evidence = f"Your {label} evidence" if label else "The evidence for this requirement"
    if newest is None or years is None:
        if rule is None:
            return f"{evidence} has no dates, so its recency cannot be checked."
        return (
            f"{evidence} has no dates, so it cannot be shown to be within the last "
            f"{_years_text(rule.window_years)}."
        )
    recent = f"Your most recent {label} evidence" if label else "The newest evidence for this"
    base = f"{recent} is from {newest[:4]} ({_ago(years)})"
    if rule is not None:
        return f"{base}; the posting asks for it within the last {_years_text(rule.window_years)}."
    if band_for(years) == "stale":
        return f"{base}, which looks outdated."
    return f"{base}."


def _ago(years: float) -> str:
    return "less than a year ago" if years < 1 else f"{_years_text(int(years))} ago"


def _years_text(n: float) -> str:
    return f"{n:g} year" + ("" if n == 1 else "s")


def apply_recency(
    assessments: Mapping[str, RequirementAssessment], checks: Mapping[str, RecencyCheck]
) -> dict[str, RequirementAssessment]:
    """Copies of the assessments. A requirement downgraded by its check becomes missing, with the
    check's sentence as its rationale. The input is never changed."""
    result: dict[str, RequirementAssessment] = {}
    for rid, assessment in assessments.items():
        check = checks.get(rid)
        if check is not None and check.effect == "downgraded":
            # Settled by the posting's window: no question is left to ask.
            update = {"status": "missing", "rationale": check.explanation, "question": None}
            result[rid] = assessment.model_copy(update=update, deep=True)
        else:
            result[rid] = assessment.model_copy(deep=True)
    return result
