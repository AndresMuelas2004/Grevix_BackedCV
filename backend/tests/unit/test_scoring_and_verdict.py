from datetime import date

from backedcv.domain.models import JobPosting, Requirement, RequirementAssessment
from backedcv.domain.rules.absurd import flag_requirements, flags_by_requirement
from backedcv.domain.scoring import compute_score
from backedcv.domain.verdict import compute_verdict


def req(rid, category="hard_skill", importance="required", **kw):
    return Requirement(
        id=rid,
        label=kw.pop("label", rid),
        quote=kw.pop("quote", f"quote {rid}"),
        category=category,
        importance=importance,
        **kw,
    )


def assess(rid, status, keyword=False):
    return RequirementAssessment(requirement_id=rid, status=status, keyword_present=keyword)


def test_fit_uses_published_weights():
    # w: required hard skill 3x2=6, preferred hard skill 3x1=3, required soft skill 1x2=2
    reqs = [req("R01"), req("R02", importance="preferred"), req("R03", category="soft_skill")]
    assessments = {
        "R01": assess("R01", "met", keyword=True),
        "R02": assess("R02", "partial"),
        "R03": assess("R03", "missing"),
    }

    score = compute_score(reqs, assessments)

    # Fit = 100 * (6*1 + 3*0.5 + 2*0) / 11
    assert score.fit == round(100 * 7.5 / 11, 1)
    # Coverage counts hard skills only: 6 of 9
    assert score.coverage == round(100 * 6 / 9, 1)
    # Points per requirement add up to the score (each is rounded to one decimal).
    assert abs(sum(c.points_won for c in score.contributions) - score.fit) <= 0.2


def test_gates_and_not_relevant_leave_the_score():
    reqs = [
        req("R01"),
        req("R02", category="work_authorization", knockout_type="work_authorization"),
    ]
    score = compute_score(
        [*reqs, req("R03")],
        {"R01": assess("R01", "met"), "R03": assess("R03", "missing")},
        excluded_ids={"R03"},
    )

    assert score.fit == 100
    reasons = {c.requirement_id: c.excluded_reason for c in score.contributions}
    assert reasons == {"R01": None, "R02": "gate", "R03": "not_relevant"}


def test_unknown_requirements_show_pending_points():
    score = compute_score([req("R01"), req("R02")], {"R01": assess("R01", "met")})

    assert score.fit == 50
    assert score.pending_points == 50


def _job(*requirements, **kw):
    return JobPosting(
        title=kw.get("title", "Data Engineer"),
        requirements=list(requirements),
        **{k: v for k, v in kw.items() if k != "title"},
    )


def test_missing_knockout_means_likely_screened_out():
    job = _job(
        req("R01"),
        req("R02", category="work_authorization", knockout_type="work_authorization"),
    )
    assessments = {"R01": assess("R01", "met"), "R02": assess("R02", "missing")}
    score = compute_score(job.requirements, assessments)

    verdict = compute_verdict(job, assessments, score)

    assert verdict.label == "likely_screened_out"
    assert verdict.reasons[0].requirement_ids == ["R02"]


def test_unknown_knockout_asks_questions_with_a_provisional_band():
    job = _job(
        req("R01"),
        req("R02", category="location", knockout_type="location"),
        location="New York, NY",
    )
    assessments = {"R01": assess("R01", "met")}
    score = compute_score(job.requirements, assessments)

    verdict = compute_verdict(job, assessments, score)

    assert verdict.label == "answer_questions"
    assert verdict.provisional is True
    assert "New York" in verdict.reasons[0].text


def test_apply_needs_high_fit_and_no_missing_heavy_requirement():
    reqs = [req(f"R{i:02d}") for i in range(1, 6)] + [req("R06", category="education")]
    met = {r.id: assess(r.id, "met") for r in reqs[:5]}
    job = _job(*reqs)

    all_met = met | {"R06": assess("R06", "met")}
    assert compute_verdict(job, all_met, compute_score(reqs, all_met)).label == "apply"

    edu_missing = met | {"R06": assess("R06", "missing")}
    score = compute_score(reqs, edu_missing)
    assert score.fit >= 75
    assert compute_verdict(job, edu_missing, score).label == "stretch"


def test_tailor_first_badge_when_coverage_trails_fit():
    reqs = [req("R01"), req("R02")]
    assessments = {"R01": assess("R01", "met"), "R02": assess("R02", "met", keyword=True)}
    score = compute_score(reqs, assessments)

    verdict = compute_verdict(_job(*reqs), assessments, score)

    assert score.fit == 100 and score.coverage == 50
    assert "tailor_first" in verdict.badges


def test_r1_flags_entry_level_years_and_r1_leaves_fit():
    job = _job(
        req("R01", category="experience_years", min_years=5, knockout_type="experience_years"),
        req("R02"),
        seniority="Entry level",
    )

    flags = flag_requirements(job, today=date(2026, 10, 11))
    flagged = flags_by_requirement(flags)
    assessments = {"R01": assess("R01", "missing"), "R02": assess("R02", "met")}
    score = compute_score(job.requirements, assessments, flagged=flagged)
    verdict = compute_verdict(job, assessments, score, flagged=flagged)

    assert flagged == {"R01": "R1"}
    assert score.fit == 100
    assert verdict.label == "apply"
    assert "screening_risk" in verdict.badges
