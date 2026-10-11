"""Knockout requirements: the screening question they likely become, and how facts answer it."""

import re

from backedcv.domain.models import (
    CandidateFacts,
    CVLine,
    JobPosting,
    Requirement,
    RequirementAssessment,
)
from backedcv.domain.models.assessment import YearsCheck
from backedcv.domain.text import fold_lower


def is_knockout(requirement: Requirement) -> bool:
    return requirement.importance == "required" and requirement.knockout_type is not None


# Language levels: CEFR A1-C2, with "native" above C2. Words map to the usual CEFR level.
_CEFR = ("A1", "A2", "B1", "B2", "C1", "C2")
_NATIVE_RANK = len(_CEFR) + 1
_LEVEL_WORDS: dict[str, int] = {
    "native": 7, "mother tongue": 7, "bilingual": 7, "nativo": 7, "nativa": 7,
    "lengua materna": 7, "bilingüe": 7, "bilingue": 7,
    "fluent": 5, "fluency": 5, "fluently": 5, "proficient": 5, "proficiency": 5, "advanced": 5,
    "full professional": 5, "fluido": 5, "fluida": 5, "avanzado": 5, "avanzada": 5,
    "upper intermediate": 4, "upper-intermediate": 4, "intermediate": 3, "intermedio": 3,
    "elementary": 2, "basic": 2, "básico": 2, "basico": 2, "beginner": 1,
}  # fmt: skip
_LANGUAGES: dict[str, str] = {
    "english": "English", "inglés": "English", "ingles": "English",
    "spanish": "Spanish", "español": "Spanish", "espanol": "Spanish", "castellano": "Spanish",
    "french": "French", "francés": "French", "frances": "French",
    "german": "German", "alemán": "German", "aleman": "German",
    "italian": "Italian", "italiano": "Italian",
    "portuguese": "Portuguese", "portugués": "Portuguese", "portugues": "Portuguese",
    "dutch": "Dutch", "catalan": "Catalan", "catalán": "Catalan", "basque": "Basque",
    "euskera": "Basque", "chinese": "Chinese", "mandarin": "Chinese", "japanese": "Japanese",
    "korean": "Korean", "arabic": "Arabic", "russian": "Russian", "polish": "Polish",
}  # fmt: skip
_LEVEL_RE = re.compile(
    r"\b(?:(?P<cefr>[abc][12])|(?P<word>"
    + "|".join(re.escape(w) for w in sorted(_LEVEL_WORDS, key=len, reverse=True))
    + r"))\b"
)
_LANGUAGE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(n) for n in sorted(_LANGUAGES, key=len, reverse=True)) + r")\b"
)
_SEGMENT_BREAK = re.compile(r"[,;|·•/]")


def _levels(text: str) -> list[int]:
    """Every level a folded text states: CEFR ranks 1-6, native 7."""
    found = []
    for m in _LEVEL_RE.finditer(text):
        cefr = m.group("cefr")
        found.append(_CEFR.index(cefr.upper()) + 1 if cefr else _LEVEL_WORDS[m.group("word")])
    return found


def _level_name(rank: int) -> str:
    return "native level" if rank >= _NATIVE_RANK else _CEFR[rank - 1]


def language_check(
    requirement: Requirement, lines: list[CVLine]
) -> tuple[str, list[str], str] | None:
    """A language requirement against the level the CV states for that language: ("met" or
    "missing", the CV lines that state it, one plain sentence). None when the requirement names
    no single language or no level, or the CV states no level for it: the model decides then."""
    asked = fold_lower(" ".join([requirement.label, requirement.quote, *requirement.terms]))
    names = {_LANGUAGES[m.group(0)] for m in _LANGUAGE_RE.finditer(asked)}
    needed = _levels(asked)
    if len(names) != 1 or not needed:
        return None
    language, wanted = names.pop(), min(needed)  # "C1 or above": the lowest level accepted
    best, refs = 0, []
    for line in lines:
        for segment in _SEGMENT_BREAK.split(fold_lower(line.text)):
            named = {_LANGUAGES[m.group(0)] for m in _LANGUAGE_RE.finditer(segment)}
            stated = _levels(segment) if named == {language} else []
            if stated and max(stated) >= best:
                if max(stated) > best:
                    refs = []
                best = max(stated)
                refs.append(line.id)
    if not refs:
        return None
    refs = list(dict.fromkeys(refs))
    has, asks = _level_name(best), _level_name(wanted)
    if best >= wanted:
        return "met", refs, f"Your CV states {language} at {has}; the job asks for {asks}."
    return "missing", refs, f"The job asks for {language} at {asks}; your CV states {has}."


def asks_min_years(requirement: Requirement) -> bool:
    """A minimum number of years of experience ("2+ years"), checked against the CV's dates."""
    return bool(requirement.min_years) and "experience_years" in (
        requirement.category,
        requirement.knockout_type,
    )


def duration_text(months: int) -> str:
    """Months in plain words: "11 months", "1 year", "2 years and 3 months"."""
    years, rest = divmod(max(months, 0), 12)
    month_text = f"{rest} month" + ("" if rest == 1 else "s")
    if years == 0:
        return month_text
    year_text = f"{years} year" + ("" if years == 1 else "s")
    return year_text if rest == 0 else f"{year_text} and {month_text}"


def years_sentence(check: YearsCheck) -> str:
    """One short sentence with the exact numbers of a minimum-years check that falls short."""
    asked = f"The job asks for {check.min_years:g}+ years"
    if check.reliable:
        return f"{asked}; your CV's dates add up to about {duration_text(check.cv_months)}."
    return (
        f"{asked}; your CV's dates show at least {duration_text(check.cv_months)}, "
        "but some are incomplete."
    )


def likely_question(requirement: Requirement, job: JobPosting) -> str:
    """The screening question this requirement usually becomes, phrased as a likely question."""
    where = job.location or "this job's location"
    match requirement.knockout_type:
        case "work_authorization":
            return f"Are you legally authorized to work in {where} without visa sponsorship?"
        case "location":
            return f"Are you able to work from {where} (or willing to relocate)?"
        case "language":
            return f"Do you meet this language requirement: {requirement.label}?"
        case "certification_license":
            return f"Do you hold this credential: {requirement.label}?"
        case "experience_years":
            years = f"{requirement.min_years:g}+ years" if requirement.min_years else "the required"
            return f"Do you have {years} of experience as asked ({requirement.label})?"
        case "education":
            return f"Do you meet this education requirement: {requirement.label}?"
        case "clearance":
            return f"Do you hold or can you obtain this clearance: {requirement.label}?"
        case "availability":
            return f"Can you meet this availability requirement: {requirement.label}?"
    return f"Do you meet this requirement: {requirement.label}?"


def apply_facts(
    requirement: Requirement,
    assessment: RequirementAssessment,
    facts: CandidateFacts,
    job: JobPosting,
) -> RequirementAssessment:
    """Resolve an unknown assessment from the user's answers. Never guesses from names or places."""
    if assessment.status != "unknown":
        return assessment

    answer = facts.answers.get(requirement.id)
    # A yes/no answer settles any assessment that asks a question, required or not.
    if answer is not None and (assessment.question is not None or is_knockout(requirement)):
        return assessment.model_copy(
            update={
                "status": "met" if answer else "missing",
                "source": "user_answer",
                "rationale": "You answered yes." if answer else "You answered no.",
            }
        )

    if not is_knockout(requirement):  # typed facts only settle active knockouts
        return assessment

    status = None
    if requirement.knockout_type == "work_authorization":
        if facts.needs_sponsorship is True and _mentions_sponsorship(requirement):
            status = "missing"
        elif facts.work_authorization and job.location:
            covered = any(
                fold_lower(country) in fold_lower(job.location)
                for country in facts.work_authorization
            )
            status = "met" if covered else None
    elif requirement.knockout_type == "location" and facts.willing_to_relocate is not None:
        status = "met" if facts.willing_to_relocate else "missing"
    elif requirement.knockout_type == "language" and facts.languages is not None:
        wanted = fold_lower(requirement.label + " " + requirement.quote)
        status = "met" if any(fold_lower(lang) in wanted for lang in facts.languages) else None
    elif requirement.knockout_type == "certification_license" and facts.licenses is not None:
        wanted = fold_lower(requirement.label + " " + requirement.quote)
        status = "met" if any(fold_lower(lic) in wanted for lic in facts.licenses) else None

    if status is None:
        return assessment
    return assessment.model_copy(
        update={"status": status, "source": "user_answer", "rationale": "From your answers."}
    )


def _mentions_sponsorship(requirement: Requirement) -> bool:
    text = fold_lower(requirement.quote + " " + requirement.label)
    return "sponsor" in text or "visa" in text or "patrocin" in text
