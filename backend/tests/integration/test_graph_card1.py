"""A visa barrier buried in the posting and a recency rule the CV fails, through the graph."""

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backedcv.graph.builder import build_graph, run_config
from backedcv.graph.recompute import recompute
from backedcv.ingestion import read_cv_text
from backedcv.llm.drafts import (
    AssessmentDraft,
    CVStructureDraft,
    EntryDraft,
    JobExtractionDraft,
    MatchChunkDraft,
    RequirementDraft,
    SectionDraft,
)
from backedcv.llm.drafts_screening import BarrierDraft, HiddenBarriersDraft
from backedcv.llm.structured import LLMError
from tests import fakes
from tests.fakes_optimize import FakeOptimizeLLM

pytestmark = pytest.mark.anyio

VISA_SENTENCE = (
    "Please note we are unable to sponsor visas; you must already have the right to work in the "
    "United States."
)
RECENT_SENTENCE = "Recent Kubernetes work matters most to us."  # no number: no code rule
POSTING = (
    "Platform Engineer at Example Cloud (remote, Europe).\n"
    "Requirements:\n"
    "- 3+ years of hands-on Kubernetes experience within the last 5 years.\n"
    f"{RECENT_SENTENCE}\n"
    f"{VISA_SENTENCE}\n"
)
# L006 is the only Kubernetes evidence, and its job is dated 2015 - 2017.
CV_TEXT = (
    "Carlos Ruiz\n"
    "Valencia, Spain · carlos@example.com · +34 611 222 333\n"
    "EXPERIENCE\n"
    "Platform Engineer, Turia Cloud\n"
    "2015 - 2017\n"
    "Deployed microservices on K8s clusters\n"
    "EDUCATION\n"
    "BSc Computer Science, Universitat Politecnica de Valencia, 2014\n"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def cv_structure() -> CVStructureDraft:
    return CVStructureDraft(
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
                title="Platform Engineer",
                organization="Turia Cloud",
                location=None,
                first_line_id="L004",
                last_line_id="L006",
                date_line_id="L005",
            ),
            EntryDraft(
                kind="education",
                title="BSc Computer Science",
                organization="Universitat Politecnica de Valencia",
                location=None,
                first_line_id="L008",
                last_line_id="L008",
                date_line_id=None,
            ),
        ],
    )


def job_draft() -> JobExtractionDraft:
    return JobExtractionDraft(
        title="Platform Engineer",
        company="Example Cloud",
        seniority=None,
        seniority_quote=None,
        location="Remote, Europe",
        remote_policy="remote",
        employment_type=None,
        salary_present=False,
        requirements=[
            RequirementDraft(
                quote="3+ years of hands-on Kubernetes experience within the last 5 years",
                terms=["Kubernetes"],
                label="3+ years of Kubernetes",
                category="experience_years",
                importance="required",
                cue=None,
                knockout_type="experience_years",
                min_years=3,
                aliases=[],
            )
        ],
    )


def match_draft(requirement_ids: list[str]) -> MatchChunkDraft:
    """K8s is Kubernetes, so the model reads L006 as meeting the requirement."""
    kubernetes = AssessmentDraft(
        requirement_id="R01",
        status="met",
        line_ids=["L006"],
        match_type="semantic",
        rationale="K8s is Kubernetes, and L006 shows it.",
    )
    return MatchChunkDraft(assessments=[kubernetes] if "R01" in requirement_ids else [])


@pytest.fixture
def card1(monkeypatch):
    monkeypatch.setattr(fakes, "structure_draft", cv_structure)
    monkeypatch.setattr(fakes, "job_draft", job_draft)
    monkeypatch.setattr(fakes, "match_draft", match_draft)


async def _run_to_report(llm):
    """The analysis up to its first pause, on a fixed day so the recency window is fixed."""
    graph = build_graph(llm, checkpointer=InMemorySaver())
    analysis_id = str(uuid.uuid4())
    config = run_config(analysis_id)
    await graph.ainvoke(
        {
            "analysis_id": analysis_id,
            "created_at": "2026-10-11T05:00:00+00:00",
            "cv_lines": [line.model_dump() for line in read_cv_text(CV_TEXT).lines],
            "job_text": POSTING,
        },
        config,
    )
    return graph, config


def _visa_risks(values: dict) -> list[dict]:
    return [r for r in values["hidden_risks"] if r["kind"] == "work_authorization"]


async def test_a_buried_visa_barrier_and_an_old_job_are_caught(card1):
    graph, config = await _run_to_report(FakeOptimizeLLM())
    report = (await graph.aget_state(config)).values
    assert (await graph.aget_state(config)).next == ("await_optimize",)

    [visa] = _visa_risks(report)
    assert (visa["risk"], visa["quote"]) == ("high", VISA_SENTENCE)  # the CV shows no US place

    assert report["assessments"]["R01"]["status"] == "missing"  # downgraded by recency
    assert report["recency"]["R01"]["effect"] == "downgraded"
    assert "R01" in {f["requirement_id"] for f in report["screening_flags"]}  # looks met, but...

    await graph.ainvoke(Command(resume={"action": "optimize"}), config)
    final = (await graph.aget_state(config)).values

    refused = [(r["requirement_id"], r["gate"]) for r in final["refusals"]]
    assert ("R01", "recent_enough") in refused
    assert not [
        s
        for s in final["suggestions"]
        if "R01" in s["requirement_ids"] and s["verification"]["status"] == "verified"
    ]


async def test_a_model_reading_of_the_same_barrier_is_not_counted_twice(card1):
    barrier = BarrierDraft(
        kind="work_authorization",
        quote="unable to sponsor visas",
        explicit=True,
        place="United States",
        window_years=None,
        requirement_ids=[],
        explanation="The employer will not sponsor a work visa.",
        action="Only apply if you already have the right to work in the United States.",
        question="Do you already have the right to work in the United States?",
    )
    graph, config = await _run_to_report(FakeOptimizeLLM(barriers=[barrier]))
    values = (await graph.aget_state(config)).values

    [item] = [b for b in values["barrier_items"] if b["kind"] == "work_authorization"]
    assert item["source"] == "model"
    assert len(_visa_risks(values)) == 1


async def test_a_failing_barrier_screen_keeps_the_rule_barriers(card1):
    class BrokenBarrierLLM(FakeOptimizeLLM):
        async def run(self, prompt, data, schema, *, node):
            if schema is HiddenBarriersDraft:
                raise LLMError("screen_barriers: invalid structured output")
            return await super().run(prompt, data, schema, node=node)

    graph, config = await _run_to_report(BrokenBarrierLLM())
    values = (await graph.aget_state(config)).values

    assert (await graph.aget_state(config)).next == ("await_optimize",)
    assert [e["node"] for e in values["errors"]] == ["screen_barriers"]
    assert [r["risk"] for r in _visa_risks(values)] == ["high"]


async def test_a_state_from_before_card1_recomputes_to_the_same_result(card1):
    graph, config = await _run_to_report(FakeOptimizeLLM())
    values = (await graph.aget_state(config)).values
    new_keys = ("barrier_items", "recency", "hidden_risks", "screening_flags", "refusals")
    older = {key: value for key, value in values.items() if key not in new_keys}

    assert recompute(older) == recompute(values)


async def test_a_recency_window_the_model_finds_is_checked_too(card1):
    barrier = BarrierDraft(
        kind="recency",
        quote=RECENT_SENTENCE,
        explicit=True,
        place=None,
        window_years=3,
        requirement_ids=["R01"],
        explanation="A screener may drop you if your Kubernetes work is not recent.",
        action="Show when you last used Kubernetes, with dates.",
        question=None,
    )
    graph, config = await _run_to_report(FakeOptimizeLLM(barriers=[barrier]))
    recency = (await graph.aget_state(config)).values["recency"]["R01"]

    # The model's 3 years is stricter than the posting's 5, so it is the window that applies.
    assert (recency["rule"]["source"], recency["rule"]["window_years"]) == ("model", 3)
    assert recency["effect"] == "downgraded"
