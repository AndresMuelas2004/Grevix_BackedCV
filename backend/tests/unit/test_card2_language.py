"""A language knockout is settled by the CEFR level the CV states, e.g. "English (C1)"."""

from datetime import date

import pytest

from backedcv.domain.builders import build_assessments
from backedcv.domain.models import CVLine, JobPosting, ParsedCV, Requirement
from backedcv.domain.recency import check_recency
from backedcv.domain.scoring import compute_score
from backedcv.domain.verdict import compute_verdict
from backedcv.llm.drafts import AssessmentDraft

ENGLISH = Requirement(
    id="R02",
    label="Fluent English",
    quote="Fluent English (C1 or above) is required for client calls.",
    terms=["English"],
    category="language",
    importance="required",
    knockout_type="language",
)
PYTHON = Requirement(
    id="R01", label="Python", quote="Python", category="hard_skill", importance="required"
)
JOB = JobPosting(requirements=[PYTHON, ENGLISH])
UNSURE = {
    "R01": AssessmentDraft(
        requirement_id="R01", status="met", line_ids=["L001"], match_type="exact", rationale="."
    ),
    "R02": AssessmentDraft(
        requirement_id="R02", status="unknown", line_ids=[], match_type=None, rationale="Unsure."
    ),
}


def assess(languages_line: str, job: JobPosting = JOB):
    cv = ParsedCV(
        lines=[
            CVLine(id="L001", text="Built APIs in Python"),
            CVLine(id="L002", text="LANGUAGES"),
            CVLine(id="L003", text=languages_line),
        ]
    )
    return cv, build_assessments(job, cv, UNSURE)


def test_the_stated_level_meets_the_asked_one_with_the_line_as_evidence():
    _, assessments = assess("Spanish (native), English (C1)")
    english = assessments["R02"]

    assert (english.status, english.question) == ("met", None)
    assert [e.ref for e in english.evidence] == ["L003"]
    assert english.rationale == "Your CV states English at C1; the job asks for C1."


@pytest.mark.parametrize("line", ["English: native", "English (C2)", "Inglés (C2), Español"])
def test_a_higher_level_or_native_also_meets_it(line):
    _, assessments = assess(line)
    assert assessments["R02"].status == "met"


def test_a_lower_level_is_missing_with_both_levels_in_the_reason():
    _, assessments = assess("Spanish (native), English (B2)")
    english = assessments["R02"]
    sentence = "The job asks for English at C1; your CV states B2."

    assert (english.status, english.question, english.rationale) == ("missing", None, sentence)
    verdict = compute_verdict(JOB, assessments, compute_score(JOB.requirements, assessments))
    assert verdict.label == "long_shot"  # a soft dealbreaker, not a screen-out
    assert verdict.reasons[0].text == sentence


def test_without_a_stated_level_the_question_stays():
    _, assessments = assess("Spanish, English")
    assert (assessments["R02"].status, assessments["R02"].question is not None) == (
        "unknown",
        True,
    )

    no_level = ENGLISH.model_copy(update={"label": "English", "quote": "English is required."})
    _, assessments = assess("English (C1)", JobPosting(requirements=[PYTHON, no_level]))
    assert assessments["R02"].status == "unknown"  # the posting names no level: still asked


def test_a_met_language_gets_no_recency_band():
    cv, assessments = assess("English (C1)")
    assert "R02" not in check_recency(JOB, cv, assessments, [], date(2026, 10, 11))
