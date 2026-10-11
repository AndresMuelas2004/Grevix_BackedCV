"""Card 2 screening fixes: minimum years, verdict badges, plain text, one question per fact,
no recency for degrees, and dates glued to a city (AI-run test findings, 2026-10-11)."""

import re
from datetime import date

from backedcv.api.projection import cv_view
from backedcv.domain.barriers import assess_risks, barriers_from_draft, merge_barriers
from backedcv.domain.builders import build_assessments, build_parsed_cv
from backedcv.domain.dates import parse_date_range, total_months, unglue_dates
from backedcv.domain.models import (
    BarrierItem,
    CandidateFacts,
    CVLine,
    HiddenRisk,
    JobPosting,
    Requirement,
    RequirementAssessment,
)
from backedcv.domain.models.screening import clean_prose, join_sentences, short_sentence
from backedcv.domain.recency import check_recency, line_last_used
from backedcv.domain.rules.knockout import apply_facts
from backedcv.domain.scoring import compute_score
from backedcv.domain.verdict import compute_verdict
from backedcv.llm.drafts import AssessmentDraft, CVStructureDraft, EntryDraft, SectionDraft
from backedcv.llm.drafts_screening import BarrierDraft, HiddenBarriersDraft

TODAY = date(2026, 10, 11)
RAW_ID = re.compile(r"\b(?:R\d{2}|H\d{2}|HC\d|L\d{3}|F\d{2})\b")


def cv_with(date_line: str):
    """One job dated by `date_line`, then a 2023 degree."""
    texts = [
        "Ana Lopez",
        "Bilbao, Spain",
        "EXPERIENCE",
        "AI Engineer, Acme",
        date_line,
        "Built agents with LangGraph, Python, SQL and Docker",
        "EDUCATION",
        "BSc Computer Science, Universidad Example, 2023",
    ]
    lines = [CVLine(id=f"L{i:03d}", text=t) for i, t in enumerate(texts, start=1)]
    draft = CVStructureDraft(
        name_line_id="L001",
        location_line_id="L002",
        sections=[
            SectionDraft(
                type="contact", heading_line_id=None, first_line_id="L001", last_line_id="L002"
            ),
            SectionDraft(
                type="experience", heading_line_id="L003", first_line_id="L003", last_line_id="L006"
            ),
            SectionDraft(
                type="education", heading_line_id="L007", first_line_id="L007", last_line_id="L008"
            ),
        ],
        entries=[
            EntryDraft(
                kind="job",
                title="AI Engineer",
                organization="Acme",
                location=None,
                first_line_id="L004",
                last_line_id="L006",
                date_line_id="L005",
            ),
            EntryDraft(
                kind="education",
                title="BSc Computer Science",
                organization="Universidad Example",
                location=None,
                first_line_id="L008",
                last_line_id="L008",
                date_line_id="L008",
            ),
        ],
    )
    return build_parsed_cv(lines, draft, today=TODAY)


def req(rid, label, category="hard_skill", **kw) -> Requirement:
    return Requirement(
        id=rid,
        label=label,
        quote=kw.pop("quote", label),
        category=category,
        importance=kw.pop("importance", "required"),
        **kw,
    )


YEARS = req(
    "R04",
    "2+ years of experience",
    "experience_years",
    min_years=2,
    knockout_type="experience_years",
)
JOB = JobPosting(
    title="AI Engineer",
    location="Madrid, Spain",
    requirements=[req("R01", "Python"), req("R02", "SQL"), req("R03", "Docker"), YEARS],
)


def drafts(years_status="partial"):
    met = {
        rid: AssessmentDraft(
            requirement_id=rid,
            status="met",
            line_ids=["L006"],
            match_type="exact",
            rationale="Named in L006.",
        )
        for rid in ("R01", "R02", "R03")
    }
    met["R04"] = AssessmentDraft(
        requirement_id="R04",
        status=years_status,
        line_ids=["L005"],
        match_type="semantic",
        rationale="The job started recently (R04).",
    )
    return met


def verdict_for(cv, facts=None):
    by_id = {r.id: r for r in JOB.requirements}
    assessments = build_assessments(JOB, cv, drafts())
    assessments = {
        rid: apply_facts(by_id[rid], a, facts or CandidateFacts(), JOB)
        for rid, a in assessments.items()
    }
    return assessments, compute_verdict(
        JOB, assessments, compute_score(JOB.requirements, assessments)
    )


# 6. Dates glued to a city, and no invented month ---------------------------------------------


def test_a_month_glued_to_the_city_is_read():
    parsed = parse_date_range("Bilbao, SpainApr 2026 - Present")
    assert (parsed.start.iso(), parsed.end_iso()) == ("2026-04", "present")
    assert parse_date_range("Madrid, SpainSeptember 2024 – May 2025").start.iso() == "2024-09"
    assert parse_date_range("Remote2025 - 2026").start.iso() == "2025"


def test_only_a_month_or_a_year_is_split_never_names():
    assert unglue_dates("LangGraph, GitHub, OpenAI and JavaScript") == (
        "LangGraph, GitHub, OpenAI and JavaScript"
    )
    assert unglue_dates("Dataset 2020") == "Dataset 2020"  # "set" is no month when lowercase
    assert unglue_dates("JavaScript (ES2015+)") == "JavaScript (ES2015+)"
    assert unglue_dates("SpainApr 2026") == "Spain Apr 2026"
    assert unglue_dates("SpainApr2026 - Present") == "Spain Apr 2026 - Present"


def test_a_year_alone_keeps_no_month_and_counts_at_its_shortest():
    parsed = parse_date_range("2019 - 2021")
    assert (parsed.start.iso(), parsed.end_iso(), parsed.month_unknown) == ("2019", "2021", True)
    assert total_months([parsed], TODAY) == 14  # December 2019 to January 2021
    assert total_months([parsed], TODAY, longest=True) == 36


def test_the_glued_date_counts_its_real_months():
    cv = cv_with("Bilbao, SpainDec 2025 - Present")
    [job, degree] = cv.entries
    assert (job.start, job.end, job.month_unknown, job.months_counted) == (
        "2025-12",
        "present",
        False,
        11,
    )
    assert (cv.total_months, cv.total_years, cv.total_is_minimum) == (11, 0.9, False)
    assert cv.dates_note is None
    assert (degree.start, degree.end, degree.months_counted) == ("2023", None, None)


def test_a_year_only_job_is_flagged_and_the_total_says_it_is_a_minimum():
    cv = cv_with("Bilbao, Spain 2025 - Present")
    [job, _] = cv.entries
    assert (job.start, job.month_unknown, job.months_counted) == ("2025", True, 11)
    assert cv.total_is_minimum is True
    assert "only the year" in cv.dates_note
    assert "at least" in cv.facts[0].text


# 7. The projection carries the timeline fields, also for older analyses ----------------------


def test_the_projection_fills_the_timeline_fields_for_older_analyses():
    old = {"lines": [], "entries": [{"id": "E01", "section_id": "S01", "kind": "job"}]}
    view = cv_view(old)
    assert (view["total_months"], view["total_is_minimum"], view["dates_note"]) == (
        None,
        False,
        None,
    )
    assert (view["entries"][0]["month_unknown"], view["entries"][0]["months_counted"]) == (
        False,
        None,
    )
    assert cv_view(None) is None


# 1. Minimum years: a serious risk, first, with the numbers -----------------------------------


def test_fewer_years_than_asked_is_missing_first_and_never_apply_or_screened_out():
    assessments, verdict = verdict_for(cv_with("Bilbao, SpainDec 2025 - Present"))

    years = assessments["R04"]
    assert (years.status, years.source, [e.ref for e in years.evidence]) == (
        "missing",
        "cv",
        ["F01"],
    )
    sentence = "The job asks for 2+ years; your CV's dates add up to about 11 months."
    assert years.rationale == sentence
    assert verdict.reasons[0].text == sentence
    assert verdict.reasons[0].requirement_ids == ["R04"]
    assert verdict.label == "long_shot"  # 11 of 24 months is under 75%


def test_three_quarters_of_the_years_cap_the_verdict_at_stretch():
    _, verdict = verdict_for(cv_with("Bilbao, SpainJan 2025 - Present"))  # 22 months

    assert verdict.label == "stretch"
    assert verdict.reasons[0].text.startswith("The job asks for 2+ years")
    assert "1 year and 10 months" in verdict.reasons[0].text


def test_incomplete_dates_ask_instead_of_asserting():
    cv = cv_with("Bilbao, Spain 2025 - Present")  # the month is unknown
    assessments, verdict = verdict_for(cv)

    assert assessments["R04"].status == "unknown"
    assert assessments["R04"].question.startswith("Do you have 2+ years of experience")
    assert verdict.label == "answer_questions"

    _, no = verdict_for(cv, CandidateFacts(answers={"R04": False}))
    _, yes = verdict_for(cv, CandidateFacts(answers={"R04": True}))
    assert no.label == "likely_screened_out"  # an answered no is a hard cause
    assert yes.label == "apply"


def test_enough_years_keep_the_model_status():
    cv = cv_with("Bilbao, SpainJan 2020 - Present")
    assessments = build_assessments(JOB, cv, drafts(years_status="met"))
    assert assessments["R04"].status == "met"
    assert assessments["R04"].years_check.share >= 1


# 2. Badges follow the verdict ---------------------------------------------------------------


def test_a_screened_out_verdict_never_shows_tailor_first():
    permit = req("R05", "Work permit", "work_authorization", knockout_type="work_authorization")
    job = JobPosting(requirements=[req("R01", "Python"), permit])
    assessments = {
        "R01": RequirementAssessment(requirement_id="R01", status="met"),  # no keyword: low cover
        "R05": RequirementAssessment(requirement_id="R05", status="missing"),
    }
    score = compute_score(job.requirements, assessments)
    assert score.fit - score.coverage >= 15

    verdict = compute_verdict(job, assessments, score)
    assert verdict.label == "likely_screened_out"
    assert "tailor_first" not in verdict.badges


# 3. Plain text: no raw IDs, sentences joined with a space ------------------------------------


def test_raw_ids_leave_the_prose_and_labels_replace_requirement_ids():
    assert clean_prose("It would reject the application (R17).") == (
        "It would reject the application."
    )
    assert clean_prose("This conflicts with R17.", {"R17": "US work authorization"}) == (
        "This conflicts with US work authorization."
    )
    assert clean_prose("Shown on L006 (R02, R03).", keep_citations=True) == "Shown on L006."
    assert join_sentences("It would reject the application", "US work authorization.") == (
        "It would reject the application. US work authorization."
    )
    assert short_sentence("One. Two.") == "One."


def test_model_sentences_lose_ids_and_stay_one_short_sentence():
    posting = "Hybrid: three days a week at our Madrid office."
    job = JobPosting(location="Madrid, Spain", requirements=[req("R01", "Python")])
    draft = HiddenBarriersDraft(
        items=[
            BarrierDraft(
                kind="location",
                quote=posting,
                explicit=True,
                place="Madrid",
                window_years=None,
                requirement_ids=[],
                explanation=(
                    "Your CV says remote (R01), so a screener may drop you for the Madrid "
                    "office. A second sentence the user does not need."
                ),
                action="Say whether you can work from Madrid (H01).",
                question="Can you work from the Madrid office (R01)?",
            )
        ]
    )
    [item] = barriers_from_draft(draft, posting, job)
    for text in (item.explanation, item.action, item.question):
        assert not RAW_ID.search(text)
    assert item.explanation.count(".") == 1
    assert len(item.explanation.split()) <= 25


def test_verdict_notes_never_show_ids():
    risk = HiddenRisk(
        id="H01",
        kind="other",
        explanation="This sentence (R02) may get you dropped. More detail here.",
        risk="high",
    )
    job = JobPosting(requirements=[req("R01", "Python")])
    assessments = {"R01": RequirementAssessment(requirement_id="R01", status="met")}
    verdict = compute_verdict(
        job, assessments, compute_score(job.requirements, assessments), hidden_risks=[risk]
    )
    assert verdict.reasons[-1].text == "Hidden screening risk: This sentence may get you dropped."


# 4. One question per fact -------------------------------------------------------------------

OFFICE = req(
    "R02",
    "Hybrid work",
    "location",
    quote="Hybrid: three days a week in the office.",
    knockout_type="location",
)
OFFICE_JOB = JobPosting(location="Madrid, Spain", requirements=[req("R01", "Python"), OFFICE])


def madrid_barrier(hid="H01", quote="You will join our Madrid team on site."):
    return BarrierItem(
        id=hid,
        kind="location",
        quote=quote,
        place="Madrid",
        explanation="You may be dropped if you cannot work from Madrid.",
        question="Can you work from our Madrid office?",
    )


def test_a_barrier_that_repeats_a_knockout_question_asks_nothing_and_follows_its_answer():
    [barrier] = merge_barriers([madrid_barrier()], [], [], OFFICE_JOB)
    assert barrier.requirement_ids == ["R02"]

    cv = build_parsed_cv([CVLine(id="L001", text="Ana Lopez")], None, today=TODAY)
    open_question = {
        "R02": RequirementAssessment(requirement_id="R02", status="unknown", question="Q?")
    }
    [risk] = assess_risks([barrier], OFFICE_JOB, cv, open_question, CandidateFacts(), {})
    assert risk.question is None  # the knockout asks it once

    answered = {
        "R02": apply_facts(
            OFFICE, open_question["R02"], CandidateFacts(answers={"R02": True}), OFFICE_JOB
        )
    }
    [risk] = assess_risks([barrier], OFFICE_JOB, cv, answered, CandidateFacts(), {})
    assert (risk.resolved, risk.risk) == (True, "low")


def test_two_barriers_about_the_same_place_make_one_question():
    job = JobPosting(location="Madrid, Spain", requirements=[req("R01", "Python")])
    merged = merge_barriers(
        [madrid_barrier(), madrid_barrier("H02", "Relocation to Madrid is required.")],
        [],
        [],
        job,
    )
    assert [b.id for b in merged] == ["H01"]


# 5. Degrees and certifications do not expire -------------------------------------------------


def test_a_degree_gets_no_recency_band():
    cv = cv_with("Bilbao, SpainJan 2016 - Dec 2016")
    degree = req("R05", "Computer Science degree", "education")
    job = JobPosting(requirements=[req("R01", "Python"), degree])
    assessments = {
        "R01": RequirementAssessment(
            requirement_id="R01",
            status="met",
            evidence=[{"ref": "L006", "quote": "x", "match_type": "exact"}],
        ),
        "R05": RequirementAssessment(
            requirement_id="R05",
            status="met",
            evidence=[{"ref": "L008", "quote": "x", "match_type": "exact"}],
        ),
    }
    assert "L008" not in line_last_used(cv, TODAY)

    checks = check_recency(job, cv, assessments, [], TODAY)
    assert "R05" not in checks  # a 2023 degree is never "aging"
    assert checks["R01"].band == "stale"  # job evidence still ages
