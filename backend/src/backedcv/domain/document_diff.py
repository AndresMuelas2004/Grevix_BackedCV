"""The editable CV document: built from the parsed CV, then changed only by accepted suggestions
and by reordering. Every function returns new objects and never changes its inputs."""

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from itertools import groupby

from backedcv.domain.dates import parse_date_range
from backedcv.domain.models import (
    CVDocument,
    CVEntry,
    CVLine,
    CVSection,
    DiffLine,
    DocContact,
    DocItem,
    DocLine,
    DocSection,
    ParsedCV,
    Suggestion,
)
from backedcv.domain.models.cv import SectionType
from backedcv.domain.models.document import LineKind
from backedcv.domain.text import fold_lower

STANDARD_HEADINGS: dict[SectionType, str] = {
    "summary": "Summary",
    "experience": "Experience",
    "education": "Education",
    "skills": "Skills",
    "projects": "Projects",
    "certifications": "Certifications",
    "languages": "Languages",
    "other": "Other",
}


# Building the document ------------------------------------------------------------------------


def document_from_cv(cv: ParsedCV) -> CVDocument:
    """The parsed CV as an editable document. Every body line appears exactly once."""
    lines = {line.id: line for line in cv.lines}
    placed: set[str] = set()
    sections = [
        _section(cv, section, lines, placed) for section in cv.sections if section.type != "contact"
    ]
    leftovers = [line_id for line_id in _body_ids(cv) if line_id not in placed]
    if leftovers:
        sections.append(_other_section(leftovers, lines))
    return CVDocument(contact=_contact(cv), sections=sections)


def _contact(cv: ParsedCV) -> DocContact:
    contact = cv.contact
    fields = [contact.email, contact.phone, contact.location, *contact.links]
    return DocContact(
        name=contact.name.value if contact.name is not None else None,
        details=[field.value for field in fields if field is not None],
        origins=_contact_origins(cv),
    )


def _section(
    cv: ParsedCV, section: CVSection, lines: dict[str, CVLine], placed: set[str]
) -> DocSection:
    heading = lines.get(section.heading_line_id) if section.heading_line_id else None
    ids = [line_id for line_id in _section_line_ids(cv, section) if line_id not in placed]
    placed.update(ids)
    return DocSection(
        id=section.id,
        type=section.type,
        heading=heading.text if heading is not None else STANDARD_HEADINGS[section.type],
        heading_origin=heading.id if heading is not None else None,
        items=_items(section.id, ids, lines, _entry_map(cv, section.id)),
    )


def _items(
    section_id: str, ids: list[str], lines: dict[str, CVLine], owner: dict[str, CVEntry]
) -> list[DocItem]:
    """One item per entry, in document order. Each run of loose lines becomes one item."""
    items: list[DocItem] = []
    loose = 0
    for entry_id, group in groupby(ids, key=lambda i: owner[i].id if i in owner else None):
        group_ids = list(group)
        if entry_id is None:
            loose += 1
            item_lines = [_doc_line(lines[i], "text") for i in group_ids]
            items.append(DocItem(id=f"{section_id}-i{loose}", lines=item_lines))
        else:
            entry = owner[group_ids[0]]
            item_lines = [_doc_line(lines[i], _entry_kind(lines[i].text, entry)) for i in group_ids]
            items.append(DocItem(id=entry.id, lines=item_lines))
    return items


def _other_section(ids: list[str], lines: dict[str, CVLine]) -> DocSection:
    """Body lines outside every section go to one last section, so none is lost."""
    item = DocItem(id="other-i1", lines=[_doc_line(lines[i], "text") for i in ids])
    return DocSection(id="other", type="other", heading=STANDARD_HEADINGS["other"], items=[item])


def _doc_line(line: CVLine, kind: LineKind) -> DocLine:
    return DocLine(text=line.text, origin=line.id, kind=kind)


def _entry_kind(text: str, entry: CVEntry) -> LineKind:
    """Title, organization and date lines are text; the other entry lines are bullets."""
    holds_text = (
        _has_words(text, entry.title)
        or _has_words(text, entry.organization)
        or _holds_dates(text, entry)
    )
    return "text" if holds_text else "bullet"


def _has_words(text: str, phrase: str | None) -> bool:
    """True when the phrase appears in the text as whole words, ignoring case."""
    words = fold_lower(phrase or "").split()
    if not words:
        return False
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in words) + r"(?!\w)"
    return re.search(pattern, fold_lower(text)) is not None


def _holds_dates(text: str, entry: CVEntry) -> bool:
    """True when the line is the one the entry's start and end dates were read from."""
    parsed = parse_date_range(text)
    if parsed is None or entry.start is None:
        return False
    return (parsed.start.iso(), parsed.end_iso()) == (entry.start, entry.end)


# Applying suggestions -------------------------------------------------------------------------


def apply_suggestions(
    doc: CVDocument,
    cv: ParsedCV,
    suggestions: Sequence[Suggestion],
    accepted_ids: Iterable[str],
) -> CVDocument:
    """Apply the accepted, verified suggestions in the order given. Anything else is ignored."""
    accepted = set(accepted_ids)
    result = doc.model_copy(deep=True)
    for s in suggestions:
        if s.id not in accepted or s.verification.status != "verified":
            continue
        if s.kind == "align_wording":
            _align_wording(result, s)
        elif s.kind == "add_skill":
            _add_skill(result, s)
        else:
            _tailor_summary(result, s)
    return result


def _align_wording(doc: CVDocument, s: Suggestion) -> None:
    """Swap the target line's text, keeping its place and kind. A missing target is skipped."""
    for line in _all_lines(doc):
        if line.origin == s.target:
            line.text, line.origin = s.after, s.id
            return


def _add_skill(doc: CVDocument, s: Suggestion) -> None:
    section = _find_section(doc, s.target)
    if section is None:
        section = _added_section(doc, "added-skills", "skills", "Skills", at_start=False)
    if not section.items:
        section.items.append(DocItem(id=f"{section.id}-i1"))
    section.items[-1].lines.append(DocLine(text=s.after, origin=s.id, kind="text"))


def _tailor_summary(doc: CVDocument, s: Suggestion) -> None:
    section = _find_section(doc, s.target)
    if section is None:
        section = _added_section(doc, "added-summary", "summary", "Summary", at_start=True)
    item_id = section.items[0].id if section.items else f"{section.id}-i1"
    section.items = [DocItem(id=item_id, lines=[DocLine(text=s.after, origin=s.id, kind="text")])]


def _added_section(
    doc: CVDocument, section_id: str, section_type: SectionType, heading: str, at_start: bool
) -> DocSection:
    """The section a suggestion adds. It is reused when it already exists, else created once."""
    existing = _find_section(doc, section_id)
    if existing is not None:
        return existing
    section = DocSection(id=section_id, type=section_type, heading=heading)
    if at_start:
        doc.sections.insert(0, section)
    else:
        doc.sections.append(section)
    return section


# Validation -----------------------------------------------------------------------------------


def validate_document(
    doc: CVDocument,
    cv: ParsedCV,
    suggestions: Sequence[Suggestion],
    accepted_ids: Iterable[str],
) -> list[str]:
    """Reasons the document cannot be trusted. An empty list means the document is valid."""
    accepted = set(accepted_ids)
    usable = {
        s.id: s for s in suggestions if s.id in accepted and s.verification.status == "verified"
    }
    original = {line.id: line.text for line in cv.lines}
    lines = _all_lines(doc)
    present = {line.origin for line in lines}
    headings = [s.heading_origin for s in doc.sections if s.heading_origin is not None]
    counts = Counter([*doc.contact.origins, *headings, *(line.origin for line in lines)])
    section_counts = Counter(section.id for section in doc.sections)

    errors = [f"Origin {origin} appears {n} times" for origin, n in counts.items() if n > 1]
    errors += [f"Section ID {sid} appears {n} times" for sid, n in section_counts.items() if n > 1]
    for section in doc.sections:
        origin = section.heading_origin
        if origin is not None and original.get(origin) != section.heading:
            errors.append(f"Heading of section {section.id} does not match its CV line")
    for line in lines:
        error = _line_error(line, original, usable)
        if error is not None:
            errors.append(error)
    section_of = {line_id: s.id for s in cv.sections for line_id in s.line_ids}
    for line_id in _body_ids(cv):
        if line_id in present:
            continue
        if not _is_replaced(line_id, section_of.get(line_id), usable, present):
            errors.append(f"Original line {line_id} is missing from the document")
    return errors


def _line_error(
    line: DocLine, original: dict[str, str], usable: dict[str, Suggestion]
) -> str | None:
    if line.origin in original:
        if line.text == original[line.origin]:
            return None
        return f"Line {line.origin} was changed; its text must match the CV"
    if line.origin in usable:
        if line.text == usable[line.origin].after:
            return None
        return f"Suggestion {line.origin} does not match its accepted wording"
    return f"Line origin {line.origin} is neither a CV line nor an accepted, verified suggestion"


def _is_replaced(
    line_id: str, section_id: str | None, usable: dict[str, Suggestion], present: set[str]
) -> bool:
    """True when an accepted suggestion that rewrites this line or its section is present."""
    return any(
        s.id in present
        and (
            (s.kind == "align_wording" and s.target == line_id)
            or (s.kind == "tailor_summary" and s.target == section_id)
        )
        for s in usable.values()
    )


# Diff -----------------------------------------------------------------------------------------


def diff_document(
    cv: ParsedCV, doc: CVDocument, suggestions: Sequence[Suggestion] = ()
) -> list[DiffLine]:
    """Every document line as unchanged, changed or added, plus the original lines a tailored
    summary removed. The replaced text is known only from the suggestions, so pass the ones that
    were applied to get "changed" and "removed" right."""
    original = {line.id: line.text for line in cv.lines}
    by_id = {s.id: s for s in suggestions}
    present = {line.origin for line in _all_lines(doc)}
    cv_sections = {section.id: section for section in cv.sections}
    diff: list[DiffLine] = []
    for section in doc.sections:
        summary_replaced = any(
            s.kind == "tailor_summary" and s.target == section.id and s.id in present
            for s in suggestions
        )
        if summary_replaced and section.id in cv_sections:
            for line_id in _section_line_ids(cv, cv_sections[section.id]):
                removed = DiffLine(
                    section_id=section.id,
                    status="removed",
                    before=original[line_id],
                    origin=line_id,
                )
                diff.append(removed)
        for item in section.items:
            for line in item.lines:
                diff.append(_diff_line(section.id, line, original, by_id))
    return diff


def _diff_line(
    section_id: str, line: DocLine, original: dict[str, str], by_id: dict[str, Suggestion]
) -> DiffLine:
    if line.origin in original:
        before = original[line.origin]
        status = "unchanged" if line.text == before else "changed"
        return DiffLine(
            section_id=section_id, status=status, before=before, after=line.text, origin=line.origin
        )
    suggestion = by_id.get(line.origin)
    if suggestion is not None and suggestion.kind == "align_wording":
        before = original.get(suggestion.target, suggestion.before)
        return DiffLine(
            section_id=section_id,
            status="changed",
            before=before,
            after=line.text,
            origin=line.origin,
        )
    return DiffLine(section_id=section_id, status="added", after=line.text, origin=line.origin)


# Tool operations for the build agent ----------------------------------------------------------


def move_section(doc: CVDocument, section_id: str, position: int) -> CVDocument:
    """Move one section so that it sits at `position` (0 is the first section)."""
    result = doc.model_copy(deep=True)
    index = _section_index(result, section_id)
    if not 0 <= position < len(result.sections):
        last = len(result.sections) - 1
        raise ValueError(f"Position {position} is out of range; use 0 to {last}")
    section = result.sections.pop(index)
    result.sections.insert(position, section)
    return result


def reorder_items(doc: CVDocument, section_id: str, ordered_ids: Sequence[str]) -> CVDocument:
    """Put the items of one section in the given order. Each item ID must appear exactly once."""
    result = doc.model_copy(deep=True)
    section = result.sections[_section_index(result, section_id)]
    expected = Counter(item.id for item in section.items)
    given = Counter(ordered_ids)
    if expected != given:
        missing = sorted((expected - given).keys())
        unknown = sorted((given - expected).keys())
        raise ValueError(
            f"ordered_ids must name each item of section {section_id} exactly once; "
            f"missing: {missing}, unknown or repeated: {unknown}"
        )
    remaining = list(section.items)
    reordered: list[DocItem] = []
    for item_id in ordered_ids:
        index = next(i for i, item in enumerate(remaining) if item.id == item_id)
        reordered.append(remaining.pop(index))
    section.items = reordered
    return result


# Shared helpers -------------------------------------------------------------------------------


def _body_ids(cv: ParsedCV) -> list[str]:
    """Every CV line that must appear in the document, in CV order."""
    skipped = _non_body_ids(cv)
    return [line.id for line in cv.lines if line.id not in skipped]


def _non_body_ids(cv: ParsedCV) -> set[str]:
    """Lines that never become document lines: section headings and contact details."""
    headings = {s.heading_line_id for s in cv.sections if s.heading_line_id is not None}
    return headings | set(_contact_origins(cv))


def _contact_origins(cv: ParsedCV) -> list[str]:
    """The line IDs the contact came from, without repeats, name first."""
    contact = cv.contact
    fields = [contact.name, contact.email, contact.phone, contact.location, *contact.links]
    return list(dict.fromkeys(field.line_id for field in fields if field is not None))


def _entry_map(cv: ParsedCV, section_id: str) -> dict[str, CVEntry]:
    """The entry that owns each line of a section."""
    owner: dict[str, CVEntry] = {}
    for entry in cv.entries:
        if entry.section_id == section_id:
            for line_id in entry.line_ids:
                owner.setdefault(line_id, entry)
    return owner


def _section_line_ids(cv: ParsedCV, section: CVSection) -> list[str]:
    """The body lines of a section, its own and its entries', in document order."""
    position = {line.id: i for i, line in enumerate(cv.lines)}
    skipped = _non_body_ids(cv)
    owned = _entry_map(cv, section.id)
    ids = {i for i in [*section.line_ids, *owned] if i in position and i not in skipped}
    return sorted(ids, key=position.__getitem__)


def _all_lines(doc: CVDocument) -> list[DocLine]:
    return [line for section in doc.sections for item in section.items for line in item.lines]


def _find_section(doc: CVDocument, section_id: str) -> DocSection | None:
    return next((section for section in doc.sections if section.id == section_id), None)


def _section_index(doc: CVDocument, section_id: str) -> int:
    for index, section in enumerate(doc.sections):
        if section.id == section_id:
            return index
    raise ValueError(f"Unknown section ID: {section_id}")
