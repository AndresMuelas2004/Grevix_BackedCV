import pytest

from backedcv.domain.models import (
    HiddenRisk,
    JobPosting,
    Requirement,
    RequirementAssessment,
    VerdictReason,
)
from backedcv.domain.scoring import compute_score
from backedcv.domain.verdict import compute_verdict

QUESTION = "Are you legally authorized to work in Spain without visa sponsorship?"
NOTE = "Hidden screening risk: A screener may reject this silently."


def req(rid, label):
    return Requirement(
        id=rid,
        label=label,
        quote=f"{label} experience",
        category="hard_skill",
        importance="required",
    )


def knockout(rid, label, knockout_type):
    return Requirement(
        id=rid,
        label=label,
        quote=label,
        category=knockout_type,
        importance="required",
        knockout_type=knockout_type,
    )


def assessed(**statuses):
    return {
        rid: RequirementAssessment(requirement_id=rid, status=status)
        for rid, status in statuses.items()
    }


def risk(kind="work_authorization", *, reqs=(), level="high", rid="H01", **kw):
    return HiddenRisk(
        id=rid,
        kind=kind,
        quote="Not eligible for visa sponsorship",
        explanation="A screener may reject this silently.",
        risk=level,
        requirement_ids=list(reqs),
        **kw,
    )


def verdict_of(job, assessments, risks=None):
    score = compute_score(job.requirements, assessments)
    return compute_verdict(job, assessments, score, hidden_risks=risks)


APPLY_JOB = JobPosting(
    title="Data Engineer",
    requirements=[req("R01", "Python"), req("R02", "SQL"), req("R03", "AWS")],
)
ALL_MET = assessed(R01="met", R02="met", R03="met")


@pytest.mark.parametrize(
    ("knockout_status", "label"),
    [("met", "apply"), ("missing", "likely_screened_out"), ("unknown", "answer_questions")],
)
def test_no_risks_or_an_empty_list_keep_the_verdict(knockout_status, label):
    permit = knockout("R04", "Right to work in Spain", "work_authorization")
    job = JobPosting(requirements=[*APPLY_JOB.requirements, permit])
    assessments = ALL_MET | assessed(R04=knockout_status)
    score = compute_score(job.requirements, assessments)
    base = compute_verdict(job, assessments, score)

    assert base.label == label
    assert compute_verdict(job, assessments, score, hidden_risks=None) == base
    assert compute_verdict(job, assessments, score, hidden_risks=[]) == base


def test_a_confirmed_eligibility_barrier_acts_like_a_failed_knockout():
    answered_no = risk(reqs=("R01",), question=QUESTION, confirmed=True, cv_refs=["L001"])

    verdict = verdict_of(APPLY_JOB, ALL_MET, [answered_no])

    assert verdict.label == "likely_screened_out"
    assert verdict.reasons[0].text == (
        '"Not eligible for visa sponsorship": if the employer asks this as a screening question, '
        "your answer would likely reject the application."
    )
    assert verdict.reasons[0].requirement_ids == ["R01"]


def test_a_risk_that_lists_a_knockout_never_changes_the_verdict():
    permit = knockout("R04", "Right to work in Spain", "work_authorization")
    job = JobPosting(requirements=[*APPLY_JOB.requirements, permit])
    assessments = ALL_MET | assessed(R04="met")
    base = verdict_of(job, assessments)

    listing_knockout = [
        risk(reqs=("R04",), confirmed=True),
        risk(reqs=("R04",), question=QUESTION),
        risk(kind="composite", rid="HC1", reqs=("R04", "R01")),
    ]
    for hidden in listing_knockout:
        assert verdict_of(job, assessments, [hidden]) == base


def test_an_unanswered_high_risk_counts_as_one_more_question():
    barrier = risk(reqs=("R01",), question=QUESTION)

    verdict = verdict_of(APPLY_JOB, ALL_MET, [barrier])

    assert verdict.label == "answer_questions"
    assert verdict.provisional is True
    assert verdict.title == "Answer 1 question first"
    assert verdict.reasons[0] == VerdictReason(text=QUESTION, requirement_ids=["R01"])

    job = JobPosting(
        requirements=[*APPLY_JOB.requirements, knockout("R04", "Onsite in Madrid", "location")]
    )
    with_knockout = verdict_of(job, ALL_MET | assessed(R04="unknown"), [barrier])
    assert with_knockout.title == "Answer 2 questions first"
    assert with_knockout.reasons[1].text == QUESTION


def test_other_high_risks_and_composites_add_one_reason_each():
    base = verdict_of(APPLY_JOB, ALL_MET)

    other = verdict_of(APPLY_JOB, ALL_MET, [risk("other", reqs=("R02",))])
    assert other.label == base.label == "apply"
    assert other.reasons == [*base.reasons, VerdictReason(text=NOTE, requirement_ids=["R02"])]

    composite = verdict_of(
        APPLY_JOB, ALL_MET, [risk(kind="composite", rid="HC1", reqs=("R01", "R02"))]
    )
    assert composite.label == "apply"
    assert composite.reasons == [
        *base.reasons,
        VerdictReason(text=NOTE, requirement_ids=["R01", "R02"]),
    ]


def test_medium_and_answered_risks_do_not_change_the_verdict():
    base = verdict_of(APPLY_JOB, ALL_MET)
    medium = [
        risk("other", level="medium", reqs=("R02",)),
        risk("location", level="medium", reqs=("R02",), question=QUESTION),
    ]
    answered = [
        risk(reqs=("R01",), question=QUESTION, resolved=True),
        risk("other", reqs=("R03",), resolved=True),
    ]

    assert verdict_of(APPLY_JOB, ALL_MET, medium) == base
    assert verdict_of(APPLY_JOB, ALL_MET, answered) == base
