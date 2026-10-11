"""Card 2: hard dealbreakers (legal bans) apart from soft ones, so nobody self-rejects from a
flexible role (real user feedback, 2026-10-11)."""

import pytest

from backedcv.domain.builders import build_assessments
from backedcv.domain.models import (
    CandidateFacts,
    CVLine,
    JobPosting,
    ParsedCV,
    RecencyCheck,
    Requirement,
    RequirementAssessment,
)
from backedcv.domain.rules.knockout import apply_facts
from backedcv.domain.scoring import compute_score
from backedcv.domain.verdict import compute_verdict
from backedcv.llm.drafts import AssessmentDraft


def req(rid, label, category="hard_skill", **kw) -> Requirement:
    return Requirement(
        id=rid, label=label, quote=label, category=category, importance="required", **kw
    )


def knockout(kind, label, category=None) -> Requirement:
    return req("R09", label, category or kind, knockout_type=kind)


SKILLS = [req("R01", "Python"), req("R02", "SQL"), req("R03", "Docker")]


def verdict_with(gate: Requirement, status="missing", source="cv", recency=None):
    job = JobPosting(location="Austin, TX", requirements=[*SKILLS, gate])
    assessments = {r.id: RequirementAssessment(requirement_id=r.id, status="met") for r in SKILLS}
    assessments[gate.id] = RequirementAssessment(
        requirement_id=gate.id, status=status, source=source
    )
    score = compute_score(job.requirements, assessments)
    return compute_verdict(job, assessments, score, recency=recency)


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        ("work_authorization", "Right to work in the US"),
        ("clearance", "Active security clearance"),
        ("certification_license", "Ohio RN license"),
    ],
)
def test_a_legal_ban_the_cv_shows_missing_is_a_hard_dealbreaker(kind, label):
    verdict = verdict_with(knockout(kind, label))
    assert verdict.label == "likely_screened_out"
    assert verdict.reasons[0].requirement_ids == ["R09"]


@pytest.mark.parametrize(
    ("kind", "label"),
    [("language", "Fluent German"), ("education", "Master's degree in Physics")],
)
def test_a_missing_language_or_degree_is_a_top_risk_capped_at_long_shot(kind, label):
    verdict = verdict_with(knockout(kind, label))
    assert verdict.label == "long_shot"
    assert verdict.reasons[0].text == f"The job asks for {label}; your CV does not show it."
    assert verdict.reasons[0].requirement_ids == ["R09"]


def test_a_years_knockout_ruled_out_by_a_window_is_soft_and_says_why_in_numbers():
    years = knockout("experience_years", "3+ years of Kubernetes")
    said = (
        "Your most recent 3+ years of Kubernetes evidence is from 2017 (9 years ago); "
        "the posting asks for it within the last 5 years."
    )
    check = RecencyCheck(
        requirement_id="R09", original_status="met", effect="downgraded", explanation=said
    )
    verdict = verdict_with(years, recency={"R09": check})
    assert verdict.label == "long_shot"
    assert verdict.reasons[0].text == said


@pytest.mark.parametrize("kind", ["language", "education", "location", "availability"])
def test_an_answered_no_to_any_knockout_question_is_a_hard_dealbreaker(kind):
    verdict = verdict_with(knockout(kind, "Asked point"), source="user_answer")
    assert verdict.label == "likely_screened_out"


@pytest.mark.parametrize("kind", ["location", "availability"])
def test_location_and_availability_are_asked_never_asserted(kind):
    gate = knockout(kind, "On site in Austin three days a week")
    job = JobPosting(location="Austin, TX", requirements=[*SKILLS, gate])
    cv = ParsedCV(lines=[CVLine(id="L001", text="Valencia, Spain")])
    model_says_missing = {
        "R09": AssessmentDraft(
            requirement_id="R09",
            status="missing",
            line_ids=["L001"],
            match_type="exact",
            rationale="The CV shows Valencia, Spain.",
        )
    }

    [assessment] = [
        a for rid, a in build_assessments(job, cv, model_says_missing).items() if rid == "R09"
    ]
    assert assessment.status == "unknown"
    assert assessment.question is not None

    answered = apply_facts(gate, assessment, CandidateFacts(answers={"R09": False}), job)
    assert (answered.status, answered.source) == ("missing", "user_answer")
