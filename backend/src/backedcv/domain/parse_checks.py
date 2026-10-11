"""Deterministic checks on the parsed CV: what screening software or a recruiter may trip over."""

import re

from backedcv.domain.models import CVEntry, CVLine, ParsedCV, ParseWarning
from backedcv.domain.text import fold_lower

MAX_FILE_BYTES = int(2.5 * 1024 * 1024)
_OUTSIDE_BODY = frozenset({"header", "footer", "textbox"})
_CORE_SECTIONS = frozenset({"experience", "education", "skills"})
_LETTER_SPACED = re.compile(r"(?<!\S)(?:[^\W\d_] ){3}[^\W\d_](?!\S)")
_COMMON_HEADINGS: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "profile", "objective", "about", "resumen", "perfil", "objetivo"),
    "experience": ("experience", "employment", "work history", "experiencia", "empleo"),
    "education": (
        "education",
        "academic",
        "formación",
        "formacion",
        "educación",
        "educacion",
        "estudios",
    ),
    "skills": ("skills", "competencies", "competencias", "habilidades", "conocimientos"),
    "projects": ("projects", "proyectos"),
    "certifications": (
        "certification",
        "certificate",
        "license",
        "licence",
        "training",
        "cursos",
        "certificaci",
        "licencia",
    ),
    "languages": ("language", "idioma"),
}


def run_parse_checks(
    cv: ParsedCV, *, multi_column: bool = False, file_size: int | None = None
) -> list[ParseWarning]:
    """Every parse check that applies to this CV, in the order the report shows them."""
    warnings = [
        *_contact_outside_body(cv),
        *_nonstandard_headings(cv),
        *_missing_sections(cv),
        *_unreadable_dates(cv),
        *_jobs_out_of_order(cv),
    ]
    if multi_column:
        warnings.append(
            ParseWarning(
                code="multi_column",
                severity="warning",
                message=(
                    "This PDF has two columns. Some screening software reads across the page "
                    "and mixes the columns up. We show the order we read; one column is safer."
                ),
            )
        )
    warnings += _table_lines(cv)
    warnings += _letter_spaced(cv)
    if file_size is not None and file_size > MAX_FILE_BYTES:
        warnings.append(
            ParseWarning(
                code="large_file",
                severity="info",
                message=(
                    "This file is larger than 2.5 MB. Some application systems reject files "
                    "that big, so export a smaller PDF."
                ),
            )
        )
    return warnings


def _by_id(cv: ParsedCV) -> dict[str, CVLine]:
    return {line.id: line for line in cv.lines}


def _contact_outside_body(cv: ParsedCV) -> list[ParseWarning]:
    """Contact details that appear only in a header, footer or text box."""
    by_id = _by_id(cv)
    body = fold_lower(" ".join(line.text for line in cv.lines if line.source not in _OUTSIDE_BODY))
    contact = cv.contact
    singles = [contact.name, contact.email, contact.phone, contact.location]
    fields = [field for field in (*singles, *contact.links) if field is not None]
    ids: list[str] = []
    for field in fields:
        line = by_id.get(field.line_id)
        if line is None or line.source not in _OUTSIDE_BODY or fold_lower(field.value) in body:
            continue
        ids.append(line.id)
    if not ids:
        return []
    return [
        ParseWarning(
            code="contact_outside_body",
            severity="warning",
            message=(
                "Some contact details appear only in a header, footer or text box. Many "
                "screening systems skip those areas, so move them into the main body."
            ),
            line_ids=list(dict.fromkeys(ids)),
        )
    ]


def _nonstandard_headings(cv: ParsedCV) -> list[ParseWarning]:
    """Section headings that do not say what the section holds."""
    by_id = _by_id(cv)
    found: list[ParseWarning] = []
    for section in cv.sections:
        phrases = _COMMON_HEADINGS.get(section.type)
        line = by_id.get(section.heading_line_id or "")
        if phrases is None or line is None:
            continue
        if any(phrase in fold_lower(line.text) for phrase in phrases):
            continue
        found.append(
            ParseWarning(
                code="nonstandard_heading",
                severity="info",
                message=(
                    f'The heading "{line.text}" is unusual for this section. Screening software '
                    "may not recognize it; use a plain heading such as "
                    f'"{section.type.capitalize()}".'
                ),
                line_ids=[line.id],
            )
        )
    return found


def _missing_sections(cv: ParsedCV) -> list[ParseWarning]:
    if any(section.type in _CORE_SECTIONS for section in cv.sections):
        return []
    return [
        ParseWarning(
            code="missing_section",
            severity="warning",
            message=(
                "We could not find an Experience, Education or Skills section. Screening "
                "software looks for these headings, so give them a clear title."
            ),
        )
    ]


def _unreadable_dates(cv: ParsedCV) -> list[ParseWarning]:
    found: list[ParseWarning] = []
    for entry in cv.entries:
        if entry.kind != "job" or entry.start is not None:
            continue
        name = entry.title or entry.organization
        where = f' ("{name}")' if name else ""
        found.append(
            ParseWarning(
                code="unreadable_dates",
                severity="warning",
                message=(
                    f"We could not read the start date of a job{where}. Write dates like "
                    "'Jan 2020 - Mar 2022' or '2020 - 2022' so the timeline can be checked."
                ),
                line_ids=list(entry.line_ids),
            )
        )
    return found


def _jobs_out_of_order(cv: ParsedCV) -> list[ParseWarning]:
    dated = [entry for entry in cv.entries if entry.kind == "job" and entry.start is not None]
    late: list[str] = []
    previous: tuple[str, str] | None = None
    for job in dated:
        key = _recency(job)
        if previous is not None and key > previous:
            late.extend(job.line_ids)
        previous = key
    if not late:
        return []
    return [
        ParseWarning(
            code="not_reverse_chronological",
            severity="info",
            message=(
                "Your jobs are not listed newest first. Most recruiters expect the latest job "
                "at the top."
            ),
            line_ids=late,
        )
    ]


def _recency(job: CVEntry) -> tuple[str, str]:
    """Sort key: the end date (an open job counts as the latest), then the start date."""
    end = "9999-12" if job.end == "present" else (job.end or job.start or "")
    return end, job.start or ""


def _table_lines(cv: ParsedCV) -> list[ParseWarning]:
    ids = [line.id for line in cv.lines if line.source == "table"]
    if not ids:
        return []
    return [
        ParseWarning(
            code="tables",
            severity="info",
            message=(
                "Some lines sit inside a table. Some screening software reads tables in the "
                "wrong order, so keep the main content in plain text."
            ),
            line_ids=ids,
        )
    ]


def _letter_spaced(cv: ParsedCV) -> list[ParseWarning]:
    ids = [line.id for line in cv.lines if _LETTER_SPACED.search(line.text)]
    if not ids:
        return []
    return [
        ParseWarning(
            code="letter_spaced",
            severity="warning",
            message=(
                'Some words are spaced out letter by letter (like "E X P E R I E N C E"). '
                "Screening software may read them as single letters, so type them normally."
            ),
            line_ids=ids,
        )
    ]
