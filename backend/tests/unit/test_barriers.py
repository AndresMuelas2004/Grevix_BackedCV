"""Hidden barriers: model quotes checked against the posting, rule patterns, merge, risks, flags."""

import pytest
from pydantic import BaseModel

from backedcv.domain.barriers import (
    assess_risks,
    barriers_from_draft,
    find_rule_barriers,
    merge_barriers,
    screening_flags,
)
from backedcv.domain.models import (
    ELIGIBILITY_KINDS,
    BarrierItem,
    CandidateFacts,
    Contact,
    ContactField,
    CVLine,
    HiddenRisk,
    JobPosting,
    ParsedCV,
    RecencyCheck,
    RecencyRule,
    Requirement,
    RequirementAssessment,
)
from backedcv.llm.drafts_screening import BarrierDraft, HiddenBarriersDraft
from backedcv.llm.prompt_loader import load_prompt

VISA = (
    "Please note we are unable to sponsor visas; you must already have the right to work in the "
    "United States."
)
K8S = "3+ years of hands-on Kubernetes experience within the last 5 years."
POSTING = f"Platform Engineer at Example Cloud.\n- {K8S}\n- Strong Python skills.\n{VISA}\n"


def req(rid: str, quote: str, knockout: str | None = None) -> Requirement:
    return Requirement(
        id=rid,
        label=quote[:40],
        quote=quote,
        category="hard_skill",
        importance="required",
        knockout_type=knockout,
    )


JOB = JobPosting(requirements=[req("R01", K8S), req("R02", "Strong Python skills.")])
JOB_WITH_DEGREE = JobPosting(
    requirements=[
        req("R01", K8S),
        req("R02", "Strong Python skills."),
        req("R03", "Degree in computing.", knockout="education"),
    ]
)
US_BARRIER = BarrierItem(
    id="H01",
    kind="work_authorization",
    quote=VISA,
    place="United States",
    explicit=True,
    explanation="A screener may drop you.",
    action="Say so in your application.",
    source="model",
)


def draft_item(**changes) -> BarrierDraft:
    fields = {
        "kind": "work_authorization",
        "quote": VISA,
        "explicit": True,
        "place": None,
        "window_years": None,
        "requirement_ids": [],
        "explanation": "",
        "action": "",
        "question": None,
    }
    return BarrierDraft(**(fields | changes))


def cv_in(location: str | None) -> ParsedCV:
    """A CV whose contact line (L002) shows the location, or a CV with no location at all."""
    if location is None:
        return ParsedCV(lines=[CVLine(id="L001", text="Jane Doe")])
    return ParsedCV(
        lines=[CVLine(id="L001", text="Jane Doe"), CVLine(id="L002", text=location)],
        contact=Contact(location=ContactField(value=location, line_id="L002")),
    )


def assess(barriers, *, job=JOB, cv=None, facts=None, assessments=None, recency=None):
    return assess_risks(
        barriers,
        job,
        cv if cv is not None else cv_in("Madrid, Spain"),
        assessments or {},
        facts if facts is not None else CandidateFacts(),
        recency or {},
    )


def check(effect: str, rid: str = "R02", refs=("L004",), within: bool | None = None):
    return RecencyCheck(
        requirement_id=rid,
        original_status="met",
        last_used="2017-12",
        years_since=8.8,
        band="stale",
        evidence_refs=list(refs),
        rule=RecencyRule(quote=K8S, window_years=5, requirement_ids=[rid]),
        within_rule=within,
        effect=effect,
        explanation="Kubernetes was last used in 2017-12, outside the 5-year window.",
    )


# 1. Model items ----------------------------------------------------------------------------


def test_unlocated_quotes_are_dropped_and_located_spans_kept():
    draft = HiddenBarriersDraft(
        items=[
            draft_item(quote=VISA.rstrip("."), place="United States"),
            draft_item(quote="Candidates must hold a PhD in physics."),  # not in the posting
        ]
    )
    [item] = barriers_from_draft(draft, POSTING, JOB)
    assert (item.id, item.quote, item.source) == ("H01", VISA.rstrip("."), "model")
    assert item.place == "United States"
    assert "screener" in item.explanation  # empty text gets the plain default
    assert item.action


def test_unknown_requirement_ids_are_dropped():
    draft = HiddenBarriersDraft(items=[draft_item(requirement_ids=["R02", "R99", "R02"])])
    [item] = barriers_from_draft(draft, POSTING, JOB)
    assert item.requirement_ids == ["R02"]


def test_window_years_only_for_recency_within_one_to_twenty():
    draft = HiddenBarriersDraft(
        items=[
            draft_item(kind="recency", quote=K8S, window_years=5),
            draft_item(kind="recency", quote="Strong Python skills.", window_years=25),
            draft_item(kind="work_authorization", quote=VISA, window_years=5),
        ]
    )
    k8s, python, visa = barriers_from_draft(draft, POSTING, JOB)
    assert [k8s.window_years, python.window_years, visa.window_years] == [5, None, None]


def test_at_most_eight_model_items_are_kept():
    draft = HiddenBarriersDraft(items=[draft_item() for _ in range(10)])
    items = barriers_from_draft(draft, POSTING, JOB)
    assert [item.id for item in items] == [f"H{n:02d}" for n in range(1, 9)]


# 2. Rule items -----------------------------------------------------------------------------


def test_rule_patterns_find_sponsorship_and_the_right_to_work_with_its_place():
    text = (
        "We are unable to sponsor visas.\n"
        "You must already have the right to work in the United States.\n"
        "Citizens only.\n"
        "Visa sponsorship is not available for this role.\n"
        "Experience with visa applications is a plus.\n"
        "Strong Python skills.\n"
    )
    items = find_rule_barriers(text)
    assert [(item.quote, item.place) for item in items] == [
        ("We are unable to sponsor visas.", None),
        ("You must already have the right to work in the United States.", "United States"),
        ("Citizens only.", None),
        ("Visa sponsorship is not available for this role.", None),
    ]
    assert {(item.kind, item.source, item.explicit) for item in items} == {
        ("work_authorization", "rule", True)
    }


# 3. Merge ----------------------------------------------------------------------------------


def test_merge_dedupes_links_requirements_and_renumbers():
    model = [
        BarrierItem(
            id="H09",
            kind="work_authorization",
            quote="unable to sponsor visas",
            place="United States",
            explanation="A screener may drop you.",
            action="Say so.",
            source="model",
        )
    ]
    rules = [
        BarrierItem(id="H01", kind="work_authorization", quote=VISA, source="rule"),
        BarrierItem(id="H02", kind="work_authorization", quote="Citizens only.", source="rule"),
    ]
    job = JobPosting(requirements=[req("R01", VISA), req("R02", K8S)])
    merged = merge_barriers(model, rules, [RecencyRule(quote=K8S, window_years=5)], job)

    assert [(i.id, i.kind, i.quote, i.source, i.requirement_ids) for i in merged] == [
        ("H01", "work_authorization", "unable to sponsor visas", "model", ["R01"]),
        ("H02", "work_authorization", "Citizens only.", "rule", []),
        ("H03", "recency", K8S, "rule", ["R02"]),
    ]
    assert merged[2].window_years == 5
    assert (model[0].id, model[0].requirement_ids) == ("H09", [])  # inputs are not changed


def test_a_model_recency_item_takes_the_window_of_its_rule():
    model = [
        BarrierItem(
            id="H01",
            kind="recency",
            quote="Kubernetes experience within the last 5 years",
            explanation="A screener may drop you.",
            action="Show dates.",
            source="model",
        )
    ]
    rule = RecencyRule(quote=K8S, window_years=5, requirement_ids=["R01"])
    merged = merge_barriers(model, [], [rule], JOB)
    assert [(i.id, i.kind, i.window_years, i.requirement_ids, i.source) for i in merged] == [
        ("H01", "recency", 5, ["R01"], "model")
    ]


# 4. Risks ----------------------------------------------------------------------------------


def test_work_authorization_in_another_country_is_high_and_cites_the_location_line():
    [risk] = assess([US_BARRIER])
    assert (risk.risk, risk.cv_refs, risk.resolved, risk.confirmed) == (
        "high",
        ["L002"],
        False,
        False,
    )
    assert risk.question == (
        "Do you already have the right to work in the United States without visa sponsorship?"
    )


def test_the_candidates_own_answers_resolve_or_confirm_the_barrier():
    [yes] = assess([US_BARRIER], facts=CandidateFacts(answers={"H01": True}))
    assert (yes.risk, yes.resolved, yes.confirmed) == ("low", True, False)
    [no] = assess([US_BARRIER], facts=CandidateFacts(answers={"H01": False}))
    assert (no.risk, no.resolved, no.confirmed) == ("high", False, True)


def test_needs_sponsorship_confirms_a_work_authorization_barrier():
    [risk] = assess([US_BARRIER], facts=CandidateFacts(needs_sponsorship=True))
    assert (risk.risk, risk.confirmed) == ("high", True)


def test_a_place_the_candidate_already_has_is_low():
    by_facts = assess([US_BARRIER], facts=CandidateFacts(work_authorization=["United States"]))
    by_alias = assess([US_BARRIER], cv=cv_in("Austin, TX, USA"))
    by_eu = assess([US_BARRIER.model_copy(update={"place": "EU"})], cv=cv_in("Madrid, Spain"))
    assert [by_facts[0].risk, by_alias[0].risk, by_eu[0].risk] == ["low", "low", "low"]
    assert by_alias[0].resolved is True


def test_unknown_location_is_medium_when_explicit_and_low_when_implied():
    [explicit] = assess([US_BARRIER], cv=cv_in(None))
    [implied] = assess([US_BARRIER.model_copy(update={"explicit": False})], cv=cv_in(None))
    assert (explicit.risk, implied.risk) == ("medium", "low")


@pytest.mark.parametrize("kind", sorted(ELIGIBILITY_KINDS))
def test_eligibility_barriers_get_a_yes_or_no_question(kind):
    barrier = BarrierItem(
        id="H01",
        kind=kind,
        quote="A sentence of the posting.",
        explicit=True,
        explanation="A screener may drop you.",
        action="Say so.",
    )
    [risk] = assess([barrier])
    assert risk.question is not None and risk.question.endswith("?")


def test_a_barrier_tied_to_a_knockout_has_no_question_and_follows_the_knockout():
    job = JobPosting(requirements=[req("R01", VISA, knockout="work_authorization")])
    tied = US_BARRIER.model_copy(update={"requirement_ids": ["R01"]})
    met = {"R01": RequirementAssessment(requirement_id="R01", status="met")}
    [risk] = assess([tied], job=job, assessments=met, facts=CandidateFacts(answers={"H01": False}))
    assert (risk.risk, risk.question, risk.resolved, risk.confirmed) == ("low", None, True, False)

    answered_no = {
        "R01": RequirementAssessment(requirement_id="R01", status="missing", source="user_answer")
    }
    [risk] = assess([tied], job=job, assessments=answered_no)
    assert (risk.risk, risk.question, risk.confirmed) == ("high", None, True)

    from_cv = {"R01": RequirementAssessment(requirement_id="R01", status="missing")}
    [risk] = assess([tied], job=job, assessments=from_cv)
    assert (risk.risk, risk.question, risk.confirmed) == ("medium", None, False)


def test_recency_barrier_takes_its_level_from_the_checks_of_its_requirements():
    barrier = BarrierItem(
        id="H01",
        kind="recency",
        quote=K8S,
        window_years=5,
        requirement_ids=["R02"],
        explicit=True,
        explanation="A screener may drop you.",
        action="Show dates.",
        source="rule",
    )
    [risk] = assess([barrier], recency={"R02": check("downgraded")})
    assert (risk.risk, risk.cv_refs, risk.question) == ("high", ["L004"], None)
    assert "2017-12" in risk.explanation

    [risk] = assess([barrier], recency={"R02": check("warning", refs=())})
    assert risk.risk == "medium"
    [risk] = assess([barrier], recency={"R02": check("none", within=True)})
    assert (risk.risk, risk.resolved) == ("low", True)
    [risk] = assess([barrier], recency={})
    assert risk.risk == "low"


def test_two_open_medium_risks_make_one_high_composite_without_knockout_ties():
    a = BarrierItem(
        id="H01",
        kind="other",
        quote="Strong Python skills.",
        requirement_ids=["R02"],
        explicit=True,
        explanation="A.",
        action="a.",
    )
    b = BarrierItem(
        id="H02",
        kind="other",
        quote=K8S,
        requirement_ids=["R01"],
        explicit=True,
        explanation="B.",
        action="b.",
    )
    tied = BarrierItem(
        id="H03",
        kind="other",
        quote="Degree in computing.",
        requirement_ids=["R03"],
        explicit=True,
        explanation="C.",
        action="c.",
    )
    unknown_knockout = {"R03": RequirementAssessment(requirement_id="R03", status="unknown")}

    risks = assess([a, b, tied], job=JOB_WITH_DEGREE, assessments=unknown_knockout)
    composite = risks[0]
    assert (composite.id, composite.kind, composite.risk) == ("HC1", "composite", "high")
    assert composite.component_ids == ["H01", "H02"]
    assert composite.requirement_ids == ["R02", "R01"]
    assert composite.question is None
    assert [r.id for r in risks] == ["HC1", "H01", "H02", "H03"]

    assert [r.id for r in assess([a])] == ["H01"]  # one medium alone is no composite


def test_risks_are_ordered_composite_then_high_medium_and_low():
    barriers = [
        BarrierItem(
            id="H01",
            kind="other",
            quote="Strong Python skills.",
            explicit=False,
            explanation="A.",
            action="a.",
        ),
        BarrierItem(
            id="H02", kind="clearance", quote=VISA, explicit=True, explanation="B.", action="b."
        ),
        BarrierItem(
            id="H03", kind="other", quote=K8S, explicit=True, explanation="C.", action="c."
        ),
        BarrierItem(
            id="H04",
            kind="availability",
            quote="Start in June.",
            explicit=True,
            explanation="D.",
            action="d.",
        ),
    ]
    risks = assess(barriers, facts=CandidateFacts(answers={"H02": False}))
    assert [(r.id, r.risk) for r in risks] == [
        ("HC1", "high"),
        ("H02", "high"),
        ("H03", "medium"),
        ("H04", "medium"),
        ("H01", "low"),
    ]


# 5. Flags ----------------------------------------------------------------------------------


def test_screening_flags_name_requirements_that_look_met_but_carry_a_risk():
    job = JobPosting(
        requirements=[req("R01", K8S), req("R02", "Strong Python skills."), req("R03", "Go.")]
    )
    original = {
        "R01": RequirementAssessment(requirement_id="R01", status="met"),
        "R02": RequirementAssessment(requirement_id="R02", status="missing", keyword_present=True),
        "R03": RequirementAssessment(requirement_id="R03", status="missing"),
    }
    recency = {"R01": check("downgraded", rid="R01")}
    risks = [
        HiddenRisk(
            id="H01",
            kind="other",
            explanation="A screener may drop you.",
            risk="medium",
            requirement_ids=["R02"],
        ),
        HiddenRisk(
            id="H02",
            kind="other",
            explanation="Settled.",
            risk="medium",
            resolved=True,
            requirement_ids=["R01"],
        ),
        HiddenRisk(
            id="HC1",
            kind="composite",
            explanation="Several.",
            risk="high",
            requirement_ids=["R01", "R02"],
        ),
    ]
    flags = screening_flags(job, original, recency, risks)
    assert [(f.requirement_id, f.risk, f.risk_ids) for f in flags] == [
        ("R01", "high", []),
        ("R02", "medium", ["H01"]),
    ]
    assert flags[0].reasons == [recency["R01"].explanation]
    assert flags[1].reasons == ["A screener may drop you."]


# 6. Schemas and prompt ---------------------------------------------------------------------


def test_barrier_draft_has_the_contract_fields():
    assert list(BarrierDraft.model_fields) == [
        "kind",
        "quote",
        "explicit",
        "place",
        "window_years",
        "requirement_ids",
        "explanation",
        "action",
        "question",
    ]


@pytest.mark.parametrize("model", [BarrierDraft, HiddenBarriersDraft])
def test_schema_is_strict_compatible(model: type[BaseModel]):
    schema = model.model_json_schema()
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if obj.get("type") != "object":
            continue
        properties = obj.get("properties", {})
        assert set(obj.get("required", [])) == set(properties), obj.get("title")
        for name, prop in properties.items():
            assert prop.get("type") != "object" or "properties" in prop, name
            assert "additionalProperties" not in prop, name
            assert prop.get("description"), name


def test_hidden_barriers_prompt_loads_and_names_its_data_blocks():
    prompt = load_prompt("hidden_barriers")
    assert (prompt.id, prompt.version, prompt.tier) == ("hidden_barriers", "1", "fast")
    assert "<job_posting>" in prompt.text and "<requirements>" in prompt.text
