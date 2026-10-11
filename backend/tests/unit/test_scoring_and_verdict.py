from datetime import date

from backedcv.domain.models import (
    CandidateFacts,
    JobPosting,
    Requirement,
    RequirementAssessment,
)
from backedcv.domain.rules.absurd import flag_requirements, flags_by_requirement
from backedcv.domain.rules.knockout import apply_facts, likely_question
from backedcv.domain.scoring import compute_score, round_half_up
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


def test_r2_flags_more_years_than_the_technology_has():
    job = _job(
        req(
            "R01",
            category="experience_years",
            min_years=5,
            terms=["LangGraph"],
            quote="5+ years of experience with LangGraph",
        ),
        seniority="Senior",
    )

    flags = flag_requirements(job, today=date(2026, 10, 11))

    assert [(f.rule_id, f.requirement_ids) for f in flags] == [("R2", ["R01"])]
    assert "2024" in flags[0].explanation


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


def test_r2_still_flags_a_requirement_that_r1_already_flags():
    job = _job(
        req(
            "R01",
            category="experience_years",
            min_years=5,
            terms=["LangGraph"],
            quote="5+ years of experience with LangGraph",
            knockout_type="experience_years",
        ),
        req("R02"),
        seniority="Entry level",
    )

    flags = flag_requirements(job, today=date(2026, 10, 11))
    flagged = flags_by_requirement(flags)
    assessments = {"R01": assess("R01", "missing"), "R02": assess("R02", "met")}
    score = compute_score(job.requirements, assessments, flagged=flagged)
    verdict = compute_verdict(job, assessments, score, flagged=flagged)
    reasons = {c.requirement_id: c.excluded_reason for c in score.contributions}

    assert [(f.rule_id, f.requirement_ids) for f in flags] == [("R1", ["R01"]), ("R2", ["R01"])]
    assert "entry-level" in flags[0].explanation and "LangGraph" in flags[1].explanation
    assert flagged == {"R01": "R1+R2"}
    assert reasons == {"R01": "flagged_R1+R2", "R02": None}
    assert score.fit == 100
    assert verdict.label == "apply"
    assert verdict.badges.count("screening_risk") == 1


FIT_LINE = (
    "Your Fit is {fit} out of 100; 55 is needed for a stretch and 75 to apply with confidence."
)


def test_long_shot_explains_the_fit_and_names_the_heaviest_gaps():
    reqs = [
        req("R01", label="Python"),
        req("R02", label="SQL"),
        req("R03", label="Kubernetes"),
        req("R04", importance="preferred", label="Spark"),
        req("R05", category="soft_skill", label="Teamwork"),
        req("R06", category="soft_skill", label="Mentoring"),
    ]
    assessments = {
        "R01": assess("R01", "met"),
        "R02": assess("R02", "partial"),
        "R03": assess("R03", "missing"),
        "R04": assess("R04", "met"),
        "R05": assess("R05", "partial"),
        "R06": assess("R06", "missing"),
    }
    score = compute_score(reqs, assessments)

    verdict = compute_verdict(_job(*reqs), assessments, score)

    assert score.fit == 52
    assert verdict.label == "long_shot"
    assert [r.text for r in verdict.reasons] == [
        FIT_LINE.format(fit="52"),
        "Missing required: Kubernetes, Mentoring.",
    ]
    assert verdict.reasons[1].requirement_ids == ["R03", "R06"]


def test_stretch_names_only_the_missing_required_items():
    reqs = [
        req("R01", label="Python"),
        req("R02", importance="preferred", label="Spark"),
        req("R03", category="soft_skill", label="Teamwork"),
        req("R04", category="soft_skill", label="Mentoring"),
    ]
    assessments = {
        "R01": assess("R01", "met"),
        "R02": assess("R02", "missing"),
        "R03": assess("R03", "met"),
        "R04": assess("R04", "missing"),
    }
    score = compute_score(reqs, assessments)

    verdict = compute_verdict(_job(*reqs), assessments, score)

    assert verdict.label == "stretch"
    assert score.summary == (
        "Fit 62: you meet 2 of 3 required items; biggest losses: Spark (-23), Mentoring (-15)."
    )
    assert [r.text for r in verdict.reasons] == [
        FIT_LINE.format(fit="62"),
        "Missing required: Mentoring.",
    ]
    assert verdict.reasons[1].requirement_ids == ["R04"]


def test_apply_names_the_strongest_matches():
    reqs = [
        req("R01", label="Python"),
        req("R02", label="SQL"),
        req("R03", label="AWS"),
        req("R04", importance="preferred", label="Git"),
        req("R05", category="soft_skill", label="Teamwork"),
    ]
    assessments = {r.id: assess(r.id, "met") for r in reqs}
    score = compute_score(reqs, assessments)

    verdict = compute_verdict(_job(*reqs), assessments, score)

    assert verdict.label == "apply"
    assert [r.text for r in verdict.reasons] == [
        FIT_LINE.format(fit="100"),
        "Strongest matches: Python, SQL, AWS.",
    ]
    assert verdict.reasons[1].requirement_ids == ["R01", "R02", "R03"]


def test_missing_required_items_are_named_at_most_three_heaviest_first():
    reqs = [
        req("R01", category="soft_skill", label="Teamwork"),
        req("R02", category="job_title", label="Data Engineer"),
        req("R03", label="Kubernetes"),
        req("R04", category="education", label="Degree"),
    ]
    assessments = {r.id: assess(r.id, "missing") for r in reqs}
    score = compute_score(reqs, assessments)

    verdict = compute_verdict(_job(*reqs), assessments, score)

    assert verdict.label == "long_shot"
    assert verdict.reasons[1].text == "Missing required: Kubernetes, Data Engineer, Degree."
    assert verdict.reasons[1].requirement_ids == ["R03", "R02", "R04"]


def test_a_long_shot_reached_by_answering_a_knockout_explains_itself():
    years = req(
        "R01",
        category="experience_years",
        min_years=5,
        knockout_type="experience_years",
        label="5+ years",
    )
    job = _job(years, req("R02", label="Python"), req("R03", label="Kubernetes"))
    by_id = {r.id: r for r in job.requirements}
    pending = {
        "R01": RequirementAssessment(
            requirement_id="R01", status="unknown", question=likely_question(years, job)
        ),
        "R02": assess("R02", "missing"),
        "R03": assess("R03", "missing"),
    }

    def verdict_after(facts: CandidateFacts):
        resolved = {rid: apply_facts(by_id[rid], a, facts, job) for rid, a in pending.items()}
        return compute_verdict(job, resolved, compute_score(job.requirements, resolved))

    assert verdict_after(CandidateFacts()).label == "answer_questions"
    answered = verdict_after(CandidateFacts(answers={"R01": True}))

    assert answered.label == "long_shot"
    assert [r.text for r in answered.reasons] == [
        FIT_LINE.format(fit="33"),
        "Missing required: Python, Kubernetes.",
    ]


def test_sentences_round_halves_up_to_whole_numbers():
    # Python's round() would send 52.5 to 52; the sentences must show 53 like the interface.
    assert [round_half_up(x) for x in (51.5, 52.5, 51.8, 0.4, 100.0)] == [52, 53, 52, 0, 100]
