import pytest

from backedcv.domain.models import CandidateFacts, JobPosting, Requirement, RequirementAssessment
from backedcv.domain.rules.knockout import apply_facts, likely_question
from backedcv.domain.scoring import compute_score
from backedcv.domain.verdict import compute_verdict

KNOCKOUT_TYPES = [
    "work_authorization",
    "location",
    "language",
    "certification_license",
    "experience_years",
    "education",
    "clearance",
    "availability",
]


def knockout(rid, knockout_type, label=None, quote=None):
    return Requirement(
        id=rid,
        label=label or f"{knockout_type} requirement",
        quote=quote or f"Requirement: {knockout_type}",
        category=knockout_type,
        importance="required",
        knockout_type=knockout_type,
    )


def unknown(requirement, job):
    return RequirementAssessment(
        requirement_id=requirement.id,
        status="unknown",
        question=likely_question(requirement, job),
    )


def verdict_after(job, assessments, facts):
    by_id = {r.id: r for r in job.requirements}
    resolved = {rid: apply_facts(by_id[rid], a, facts, job) for rid, a in assessments.items()}
    return compute_verdict(job, resolved, compute_score(job.requirements, resolved))


@pytest.mark.parametrize("knockout_type", KNOCKOUT_TYPES)
def test_yes_and_no_answers_settle_every_knockout_type(knockout_type):
    job = JobPosting(location="Madrid, Spain", requirements=[knockout("R01", knockout_type)])
    requirement = job.requirements[0]
    assessment = unknown(requirement, job)

    yes = apply_facts(requirement, assessment, CandidateFacts(answers={"R01": True}), job)
    no = apply_facts(requirement, assessment, CandidateFacts(answers={"R01": False}), job)

    assert (yes.status, yes.source, yes.rationale) == ("met", "user_answer", "You answered yes.")
    assert (no.status, no.source, no.rationale) == ("missing", "user_answer", "You answered no.")


def test_a_no_answer_makes_the_verdict_likely_screened_out():
    python_skill = Requirement(
        id="R01", label="Python", quote="Python", category="hard_skill", importance="required"
    )
    education = knockout("R02", "education", label="Bachelor's degree", quote="Bachelor's degree")
    job = JobPosting(requirements=[python_skill, education])
    assessments = {
        "R01": RequirementAssessment(requirement_id="R01", status="met"),
        "R02": unknown(education, job),
    }

    assert verdict_after(job, assessments, CandidateFacts()).label == "answer_questions"

    no = verdict_after(job, assessments, CandidateFacts(answers={"R02": False}))
    assert no.label == "likely_screened_out"
    assert no.reasons[0].requirement_ids == ["R02"]

    yes = verdict_after(job, assessments, CandidateFacts(answers={"R02": True}))
    assert (yes.label, yes.provisional) == ("apply", False)


def test_an_answer_takes_precedence_over_the_typed_fact():
    sponsorship = knockout("R01", "work_authorization", quote="Must work without sponsorship")
    job = JobPosting(requirements=[sponsorship])
    facts = CandidateFacts(needs_sponsorship=True, answers={"R01": True})

    result = apply_facts(sponsorship, unknown(sponsorship, job), facts, job)

    assert (result.status, result.rationale) == ("met", "You answered yes.")


def test_typed_facts_still_settle_their_knockouts():
    job = JobPosting(
        location="Madrid, Spain",
        requirements=[
            knockout("R01", "work_authorization", quote="Must work in the US without sponsorship"),
            knockout("R02", "work_authorization", quote="Authorized to work in Spain"),
            knockout("R03", "location", quote="Onsite in Madrid"),
            knockout("R04", "language", label="English", quote="Fluent English"),
            knockout("R05", "certification_license", label="CPA", quote="Licensed CPA"),
        ],
    )
    facts = CandidateFacts(
        needs_sponsorship=True,
        work_authorization=["Spain"],
        willing_to_relocate=False,
        languages=["English"],
        licenses=["CPA"],
    )

    resolved = {r.id: apply_facts(r, unknown(r, job), facts, job) for r in job.requirements}

    assert {rid: a.status for rid, a in resolved.items()} == {
        "R01": "missing",
        "R02": "met",
        "R03": "missing",
        "R04": "met",
        "R05": "met",
    }
    assert {a.source for a in resolved.values()} == {"user_answer"}


def test_an_answer_never_overrides_evidence_from_the_cv():
    education = knockout("R01", "education")
    job = JobPosting(requirements=[education])
    from_cv = RequirementAssessment(requirement_id="R01", status="met", rationale="Degree in CS")

    result = apply_facts(education, from_cv, CandidateFacts(answers={"R01": False}), job)

    assert (result.status, result.source) == ("met", "cv")
