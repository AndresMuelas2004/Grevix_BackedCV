"""Turn the model's drafts into trusted domain objects. Code checks every ID, quote and number."""

import re
from datetime import date

from backedcv.domain.dates import (
    DateRange,
    months_in,
    parse_date_range,
    total_months,
    years_from_months,
)
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
from backedcv.domain.models.assessment import YearsCheck
from backedcv.domain.models.screening import clean_prose
from backedcv.domain.rules.knockout import (
    asks_min_years,
    is_general_years,
    is_knockout,
    language_check,
    likely_question,
    years_cap_sentence,
    years_sentence,
)
from backedcv.domain.text import fold_lower, locate_quote
from backedcv.llm.drafts import AssessmentDraft, CVStructureDraft, JobExtractionDraft

GATE_CATEGORIES = {"work_authorization", "location", "clearance", "availability"}
ASKED_KINDS = frozenset({"location", "availability"})  # asked as a question, never asserted
LIST_MARKERS = "-*•·–— \t"  # a quote copied with its bullet keeps only the sentence

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
    periods: list[tuple[DateRange, str]] = []  # each dated job's period and the line it is on
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
            date_range, source, date_line = _entry_dates(lines, index, ids, e.date_line_id)
            counted = e.kind == "job" and date_range is not None and date_range.is_period
            if counted:
                periods.append((date_range, date_line))
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
                    month_unknown=date_range.month_unknown if date_range else False,
                    months_counted=months_in(date_range, today) if counted else None,
                )
            )

    cv = ParsedCV(
        lines=lines, sections=sections, entries=entries, contact=find_contact(lines, draft)
    )
    _add_experience_fact(cv, periods, today)
    return cv


def _entry_dates(lines, index, ids, date_line_id) -> tuple[DateRange | None, str, str | None]:
    """The entry's dates and their line: the first period (a start with an end or "present") on
    the date line or the entry's lines, else the first single date."""
    candidates = list(dict.fromkeys(([date_line_id] if date_line_id in index else []) + ids))
    single: tuple[DateRange, str, str] | None = None
    for line_id in candidates:
        parsed = parse_date_range(lines[index[line_id]].text)
        if parsed is None:
            continue
        if parsed.is_period:
            return parsed, "parser", line_id
        single = single or (parsed, "parser", line_id)
    return single or (None, "none", None)


def _add_experience_fact(cv: ParsedCV, periods: list[tuple[DateRange, str]], today: date) -> None:
    """F01: total experience from the job periods. A date that shows only the year counts at its
    shortest, and an undated job adds nothing, so the total is then a minimum and says so."""
    if not periods:
        return
    ranges = [period for period, _ in periods]
    months = total_months(ranges, today)
    year_only = any(period.month_unknown for period in ranges)
    undated = sum(1 for e in cv.entries if e.kind == "job" and e.months_counted is None)
    cv.total_months = months
    cv.total_years = years_from_months(months)
    cv.total_is_minimum = year_only or undated > 0
    cv.dates_note = _dates_note(year_only, undated)
    jobs = f"{len(ranges)} job" + ("" if len(ranges) == 1 else "s")
    minimum = "; at least this much, as some dates are incomplete" if cv.total_is_minimum else ""
    cv.facts.append(
        ComputedFact(
            id="F01",
            text=f"Total professional experience: {cv.total_years:g} years "
            f"(computed from the dates of {jobs}{minimum})",
            derived_from=[line_id for _, line_id in periods],
        )
    )


def _dates_note(year_only: bool, undated: int) -> str | None:
    """One short sentence on why the total is a minimum, or None when every job date is full."""
    if year_only and undated:
        return "Some dates show only the year and some jobs have none, so the total is a minimum."
    if year_only:
        return "Some dates show only the year, so the total counts the shortest time they allow."
    if undated:
        return "Some jobs have no dates, so they are not counted in the total."
    return None


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
        quote = (located or d.quote).lstrip(LIST_MARKERS)  # "- 3+ years..." reads "3+ years..."
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
    labels = {req.id: req.label for req in job.requirements}
    result: dict[str, RequirementAssessment] = {}
    for req in job.requirements:
        present = keyword_present(req, cv.lines)
        draft = drafts.get(req.id)
        if draft is None:
            fallback = _with_years(req, job, cv, _fallback(req, job, cv, present))
            result[req.id] = _with_language(req, cv, fallback)
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
        if status == "unknown" and not gate_like:
            status = "missing"  # a skill the CV never shows is missing, not a question
        if status == "missing" and gate_like and _asked_never_asserted(req):
            status = "unknown"  # where you live or when you can start: the candidate says

        assessment = RequirementAssessment(
            requirement_id=req.id,
            status=status,
            evidence=[Evidence(ref=i, quote=refs[i], match_type=match_type) for i in ids],
            # The model's sentence may name requirement IDs: labels replace them. L and F IDs stay.
            rationale=clean_prose(draft.rationale, labels, keep_citations=True),
            keyword_present=present,
            question=likely_question(req, job) if status == "unknown" and gate_like else None,
        )
        result[req.id] = _with_language(req, cv, _with_years(req, job, cv, assessment))
    return result


def _with_language(
    req: Requirement, cv: ParsedCV, assessment: RequirementAssessment
) -> RequirementAssessment:
    """A language requirement is settled by the level the CV itself states (CEFR A1-C2, or
    native), never asked: at or above the asked level it is met, below it is missing."""
    if "language" not in (req.category, req.knockout_type):
        return assessment
    found = language_check(req, cv.lines)
    if found is None:
        return assessment
    status, line_ids, sentence = found
    texts = {line.id: line.text for line in cv.lines}
    return assessment.model_copy(
        update={
            "status": status,
            "evidence": [Evidence(ref=i, quote=texts[i], match_type="exact") for i in line_ids],
            "rationale": sentence,
            "question": None,
        }
    )


def _asked_never_asserted(req: Requirement) -> bool:
    """Location and availability knockouts: people move and adapt, so a CV line never settles
    them as missing; a yes/no question does."""
    return bool(ASKED_KINDS & {req.knockout_type, req.category})


def _with_years(
    req: Requirement, job: JobPosting, cv: ParsedCV, assessment: RequirementAssessment
) -> RequirementAssessment:
    """A minimum-years requirement is checked against the CV's own job dates, not the model. When
    the dates add up to less, it is missing; when some dates are incomplete (only the year, or a
    job without dates), the app asks instead of asserting. Enough years keep the model's status:
    the requirement may be about one skill."""
    check = _years_check(req, cv)
    if check is None:
        return assessment
    if not is_general_years(req):
        # Years of one skill: the evidence decides. Fewer total years (complete dates) only cap
        # "met" at "partial": nobody has more years of a skill than years of work.
        short = check.reliable and check.cv_months < check.min_years * 12
        if assessment.status == "met" and short:
            update = {"status": "partial", "rationale": years_cap_sentence(check)}
            return assessment.model_copy(update=update)
        return assessment
    update: dict = {"years_check": check}
    if check.cv_months < check.min_years * 12:
        refs = cv.texts_by_ref()
        cited = (
            [Evidence(ref="F01", quote=refs["F01"], match_type="exact")] if "F01" in refs else []
        )
        if check.reliable:
            update |= {"status": "missing", "evidence": cited, "question": None}
        elif req.importance != "required":
            return assessment.model_copy(update=update)  # a preferred minimum asks nothing
        else:
            # The model's lines stay, so a posting's recency window is still checked on them.
            lines = [e for e in assessment.evidence if e.ref != "F01"]
            update |= {
                "status": "unknown",
                "evidence": lines + cited,
                "question": likely_question(req, job),
            }
        update["rationale"] = years_sentence(check)
    return assessment.model_copy(update=update)


def _years_check(req: Requirement, cv: ParsedCV) -> YearsCheck | None:
    if not asks_min_years(req):
        return None
    if cv.total_months is not None:
        months, reliable = cv.total_months, not cv.total_is_minimum
    elif cv.total_years is not None:  # an analysis saved before months were stored
        months, reliable = round(cv.total_years * 12), True
    else:
        return None
    return YearsCheck(
        min_years=req.min_years,
        cv_months=months,
        reliable=reliable,
        share=round(months / (req.min_years * 12), 2),
    )


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
