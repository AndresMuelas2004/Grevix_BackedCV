"""The CV's total years apply only to general years requirements, not to years of one skill."""

import pytest

from backedcv.domain.builders import build_assessments
from backedcv.domain.models import ComputedFact, CVLine, JobPosting, ParsedCV, Requirement
from backedcv.domain.rules.knockout import is_general_years
from backedcv.llm.drafts import AssessmentDraft

CV = ParsedCV(
    lines=[CVLine(id="L001", text="Built a support bot with LangGraph")],
    facts=[ComputedFact(id="F01", text="Total professional experience: 3 years")],
    total_months=36,
    total_years=3.0,
)


def years(label: str, terms: list[str], min_years: float = 5) -> Requirement:
    return Requirement(
        id="R01",
        label=label,
        quote=label,
        terms=terms,
        category="experience_years",
        importance="required",
        min_years=min_years,
        knockout_type="experience_years",
    )


@pytest.mark.parametrize(
    ("label", "terms", "general"),
    [
        ("2+ years of experience", [], True),
        ("At least 3 years of professional experience building production software", [], True),
        (
            "4+ years in platform, DevOps or cloud engineering",
            ["DevOps", "cloud engineering"],
            True,
        ),
        ("2+ años de experiencia", [], True),
        ("5+ years of hands-on experience with LangGraph", ["LangGraph"], False),
        ("3+ years of Kubernetes", ["Kubernetes"], False),
        ("3+ years of experience", ["Python"], False),
    ],
)
def test_general_or_skill_years_is_decided_in_code(label, terms, general):
    assert is_general_years(years(label, terms)) is general


def assessed(requirement: Requirement, model_status: str):
    draft = AssessmentDraft(
        requirement_id="R01",
        status=model_status,
        line_ids=["L001"] if model_status != "missing" else [],
        match_type="exact",
        rationale="From the model.",
    )
    job = JobPosting(requirements=[requirement])
    return build_assessments(job, CV, {"R01": draft})["R01"]


def test_a_skill_met_by_evidence_is_capped_at_partial_never_missing():
    langgraph = years("5+ years of hands-on experience with LangGraph", ["LangGraph"])
    capped = assessed(langgraph, "met")

    assert capped.status == "partial"
    assert (
        capped.rationale == "Your CV's dates add up to about 3 years, less than the 5+ years asked."
    )
    assert [e.ref for e in capped.evidence] == ["L001"]
    assert assessed(langgraph, "partial").status == "partial"
    assert assessed(langgraph, "missing").rationale == "From the model."  # the evidence decides


def test_a_skill_within_the_total_keeps_its_status():
    assert (
        assessed(years("2+ years of LangGraph", ["LangGraph"], min_years=2), "met").status == "met"
    )


def test_a_general_requirement_still_compares_the_total_with_numbers():
    general = assessed(years("5+ years of experience", []), "met")
    assert general.status == "missing"
    assert (
        general.rationale == "The job asks for 5+ years; your CV's dates add up to about 3 years."
    )
