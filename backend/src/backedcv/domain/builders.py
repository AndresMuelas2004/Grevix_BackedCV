"""Turn the model's drafts into trusted domain objects. Code checks every ID, quote and number."""

import re
from datetime import date

from backedcv.domain.dates import DateRange, parse_date_range, total_months, years_from_months
from backedcv.domain.keywords import contains_term, keyword_hits, keyword_present
from backedcv.domain.models import (
    ComputedFact,
    Contact,
    ContactField,
    CVEntry,
    CVLine,
    CVSection,
    Evidence,
    JobPosting,
    ParsedCV,
    Requirement,
    RequirementAssessment,
)
from backedcv.domain.rules.knockout import is_knockout, likely_question
from backedcv.domain.text import fold_lower, locate_quote
from backedcv.llm.drafts import AssessmentDraft, CVStructureDraft, JobExtractionDraft

GATE_CATEGORIES = {"work_authorization", "location", "clearance", "availability"}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_LINK = re.compile(r"(?:https?://\S+|(?:www\.)?(?:linkedin\.com|github\.com)/\S+)", re.IGNORECASE)


# CV ----------------------------------------------------------------------------------------


def find_contact(lines: list[CVLine], draft: CVStructureDraft | None) -> Contact:
    """Email, phone and links by regex; name and location from the model's line references."""
    contact = Contact()
    by_id = {line.id: line for line in lines}
    for line in lines:
        if contact.email is None and (m := _EMAIL.search(line.text)):
            contact.email = ContactField(value=m.group(0), line_id=line.id)
        if contact.phone is None and (m := _PHONE.search(line.text)):
            digits = re.sub(r"\D", "", m.group(0))
            if 9 <= len(digits) <= 15 and not parse_date_range(m.group(0)):
                contact.phone = ContactField(value=m.group(0).strip(), line_id=line.id)
        for m in _LINK.finditer(line.text):
            contact.links.append(ContactField(value=m.group(0).rstrip(".,;)"), line_id=line.id))
    if draft is not None:
        if draft.name_line_id in by_id:
            contact.name = ContactField(
                value=by_id[draft.name_line_id].text, line_id=draft.name_line_id
            )
        if draft.location_line_id in by_id:
            contact.location = ContactField(
                value=by_id[draft.location_line_id].text, line_id=draft.location_line_id
            )
    return contact


def build_parsed_cv(
    lines: list[CVLine], draft: CVStructureDraft | None, today: date | None = None
) -> ParsedCV:
    today = today or date.today()
    index = {line.id: i for i, line in enumerate(lines)}

    def span(first: str, last: str) -> list[str]:
        if first not in index or last not in index or index[first] > index[last]:
            return []
        return [line.id for line in lines[index[first] : index[last] + 1]]

    sections: list[CVSection] = []
    entries: list[CVEntry] = []
    if draft is not None:
        for i, s in enumerate(draft.sections, start=1):
            ids = span(s.first_line_id, s.last_line_id)
            if ids:
                heading = s.heading_line_id if s.heading_line_id in index else None
                sections.append(
                    CVSection(id=f"S{i:02d}", heading_line_id=heading, type=s.type, line_ids=ids)
                )
        for i, e in enumerate(draft.entries, start=1):
            ids = span(e.first_line_id, e.last_line_id)
            if not ids:
                continue
            section = next((s for s in sections if ids[0] in s.line_ids), None)
            date_range, source = _entry_dates(lines, index, ids, e.date_line_id)
            entries.append(
                CVEntry(
                    id=f"E{i:02d}",
                    section_id=section.id if section else "",
                    kind=e.kind,
                    title=e.title,
                    organization=e.organization,
                    location=e.location,
                    start=date_range.start.iso() if date_range else None,
                    end=date_range.end_iso() if date_range else None,
                    date_source=source,
                    line_ids=ids,
                )
            )

    cv = ParsedCV(
        lines=lines, sections=sections, entries=entries, contact=find_contact(lines, draft)
    )
    _add_experience_fact(cv, lines, index, today)
    return cv


def _entry_dates(lines, index, ids, date_line_id) -> tuple[DateRange | None, str]:
    candidates = ([date_line_id] if date_line_id in index else []) + ids
    for line_id in candidates:
        parsed = parse_date_range(lines[index[line_id]].text)
        if parsed is not None:
            return parsed, "parser"
    return None, "none"


def _add_experience_fact(cv: ParsedCV, lines, index, today: date) -> None:
    ranges, sources = [], []
    for entry in cv.entries:
        if entry.kind != "job":
            continue
        for line_id in entry.line_ids:
            parsed = parse_date_range(lines[index[line_id]].text)
            if parsed is not None and (parsed.end is not None or parsed.end_is_present):
                ranges.append(parsed)
                sources.append(line_id)
                break
    if not ranges:
        return
    years = years_from_months(total_months(ranges, today))
    cv.total_years = years
    cv.facts.append(
        ComputedFact(
            id="F01",
            text=f"Total professional experience: {years:g} years "
            f"(computed from the dates of {len(ranges)} jobs)",
            derived_from=sources,
        )
    )


# Job posting -----------------------------------------------------------------------------


def build_job(posting: str, draft: JobExtractionDraft) -> tuple[JobPosting, list[str]]:
    """Requirements whose quote is not in the posting are dropped, except knockouts."""
    notes: list[str] = []
    requirements: list[Requirement] = []
    for d in draft.requirements:
        located = locate_quote(d.quote, posting)
        knockout = d.knockout_type
        if knockout is None and d.category in GATE_CATEGORIES:
            knockout = d.category
        if located is None and knockout is None:
            notes.append(f"Dropped requirement with a quote not found in the posting: {d.label}")
            continue
        quote = located or d.quote
        terms = [t for t in d.terms if t.strip() and _in_quote(t, quote)][:3]
        aliases = [a for a in d.aliases if a.strip()][:3]
        requirements.append(
            Requirement(
                id=f"R{len(requirements) + 1:02d}",
                label=d.label,
                quote=quote,
                quote_located=located is not None,
                terms=terms,
                category=d.category,
                importance=d.importance,
                cue=d.cue,
                knockout_type=knockout,
                min_years=d.min_years,
                aliases=aliases,
            )
        )
    job = JobPosting(
        title=draft.title,
        company=draft.company,
        seniority=draft.seniority,
        seniority_quote=draft.seniority_quote,
        location=draft.location,
        remote_policy=draft.remote_policy,
        employment_type=draft.employment_type,
        salary_present=draft.salary_present,
        requirements=requirements,
    )
    return job, notes


def _in_quote(term: str, quote: str) -> bool:
    return contains_term(quote, term) or fold_lower(term) in fold_lower(quote)


# Matching ----------------------------------------------------------------------------------


def build_assessments(
    job: JobPosting, cv: ParsedCV, drafts: dict[str, AssessmentDraft]
) -> dict[str, RequirementAssessment]:
    refs = cv.texts_by_ref()
    result: dict[str, RequirementAssessment] = {}
    for req in job.requirements:
        present = keyword_present(req, cv.lines)
        draft = drafts.get(req.id)
        if draft is None:
            result[req.id] = _fallback(req, job, cv, present)
            continue

        ids = list(dict.fromkeys(i for i in draft.line_ids if i in refs))
        status = draft.status
        match_type = draft.match_type or ("exact" if present else "semantic")
        gate_like = is_knockout(req) or req.category in GATE_CATEGORIES

        if status in ("met", "partial") and not ids:
            status = "unknown" if gate_like else "missing"
        if match_type == "inferred" and status == "met":
            status = "partial"
        if req.category in GATE_CATEGORIES and status == "missing" and not ids:
            status = "unknown"  # a gate is missing only from an explicit negative or an answer
        status = _check_years(req, cv, ids, status)

        result[req.id] = RequirementAssessment(
            requirement_id=req.id,
            status=status,
            evidence=[Evidence(ref=i, quote=refs[i], match_type=match_type) for i in ids],
            rationale=draft.rationale.strip(),
            keyword_present=present,
            question=likely_question(req, job) if status == "unknown" and gate_like else None,
        )
    return result


def _check_years(req: Requirement, cv: ParsedCV, ids: list[str], status: str) -> str:
    """Total-experience claims are checked against the computed fact, not the model."""
    if (
        req.category == "experience_years"
        and req.min_years
        and cv.total_years is not None
        and status == "met"
        and ids == ["F01"]
        and cv.total_years < req.min_years
    ):
        return "partial" if cv.total_years >= req.min_years / 2 else "missing"
    return status


def _fallback(req, job, cv, present) -> RequirementAssessment:
    """Used when the model skipped a requirement: literal hits only, never a guess."""
    hits = keyword_hits(req, cv.lines)
    refs = cv.texts_by_ref()
    gate_like = is_knockout(req) or req.category in GATE_CATEGORIES
    if hits and not gate_like:
        return RequirementAssessment(
            requirement_id=req.id,
            status="met",
            evidence=[
                Evidence(ref=h.line_id, quote=refs[h.line_id], match_type=h.match_type)
                for h in hits[:3]
            ],
            rationale="The term appears in your CV.",
            keyword_present=present,
        )
    return RequirementAssessment(
        requirement_id=req.id,
        status="unknown" if gate_like else "missing",
        rationale="Not found in your CV.",
        keyword_present=present,
        question=likely_question(req, job) if gate_like else None,
    )
