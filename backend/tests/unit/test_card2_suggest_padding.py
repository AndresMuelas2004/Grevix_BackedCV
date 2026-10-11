"""A suggestion that only pads its line with posting words is not a better CV."""

import pytest

from backedcv.domain.guards import keyword_only
from backedcv.domain.models import (
    CVLine,
    CVSection,
    Evidence,
    JobPosting,
    ParsedCV,
    Requirement,
    RequirementAssessment,
    Suggestion,
)
from backedcv.graph.optimize_nodes import make_optimize_nodes
from backedcv.llm.drafts_optimize import SuggestionDraft
from tests.fakes_optimize import FakeOptimizeLLM


def _req(rid: str, terms: list[str], aliases: list[str] | None = None) -> Requirement:
    return Requirement(
        id=rid,
        label=terms[0],
        quote=terms[0],
        category="hard_skill",
        importance="required",
        terms=terms,
        aliases=aliases or [],
    )


JOB = JobPosting(
    title="AI Engineer",
    company="Globex",
    requirements=[
        _req("R01", ["AI observability"]),
        _req("R02", ["AI solutions"]),
        _req("R03", ["data pipelines"]),
        _req("R04", ["Kubernetes"], ["K8s"]),
        _req("R05", ["agent frameworks"]),
    ],
)

OBSERVABILITY = "Set up observability for the RAG service with LangSmith"
SUMMARY = "AI engineer who builds RAG pipelines, LLM agents and evaluation harnesses."
ETL = "Wrote ETL jobs in Python that load 2 million rows a day into PostgreSQL."


def _edit(before: str, after: str, kind: str = "align_wording") -> Suggestion:
    target = "S01" if kind == "tailor_summary" else "L002"
    return Suggestion(
        id="S01",
        kind=kind,
        target=target,
        before=before,
        after=after,
        cited_refs=["L002"],
        requirement_ids=["R01"],
    )


@pytest.mark.parametrize(
    ("before", "after", "kind"),
    [
        pytest.param(
            OBSERVABILITY,
            "Set up AI observability for the RAG service with LangSmith",
            "align_wording",
            id="ai-observability",
        ),
        pytest.param(
            SUMMARY,
            "AI engineer who builds AI solutions, including RAG pipelines, LLM agents and "
            "evaluation harnesses.",
            "tailor_summary",
            id="ai-solutions-including",
        ),
        pytest.param(
            OBSERVABILITY,
            "Implemented AI observability for the RAG service with LangSmith",
            "align_wording",
            id="verb-swap-plus-term",
        ),
        pytest.param(
            "Built data pipelines in Python",
            "Built robust, scalable, production-grade data pipelines in Python",
            "align_wording",
            id="adjectives-only",
        ),
        pytest.param(
            "Built a support bot with LangGraph",
            "Built a support bot with agent frameworks (LangGraph)",
            "align_wording",
            id="category-next-to-the-tool",
        ),
        pytest.param(
            ETL,
            "Wrote Python data pipelines (ETL jobs) that load 2 million rows a day into "
            "PostgreSQL.",
            "align_wording",
            id="one-word-moved-for-the-term",
        ),
        pytest.param(OBSERVABILITY, f"{OBSERVABILITY}.", "align_wording", id="unchanged"),
    ],
)
def test_padding_is_caught_with_a_plain_reason(before, after, kind):
    reason = keyword_only(_edit(before, after, kind), JOB)

    assert reason is not None
    assert reason.endswith(".")
    assert "L0" not in reason and "R0" not in reason  # no IDs in the prose


def test_the_reason_names_what_was_added():
    reason = keyword_only(_edit(OBSERVABILITY, OBSERVABILITY.replace("up o", "up AI o")), JOB)

    assert reason == "Only adds the posting's words or filler (AI); nothing else changes."


@pytest.mark.parametrize(
    ("before", "after"),
    [
        pytest.param(
            "Built data pipelines in Python",
            "Built data pipelines in Python for 4 regional teams",
            id="a-number-the-cv-states-elsewhere",
        ),
        pytest.param(
            "Deployed services on K8s",
            "Deployed services on Kubernetes (K8s)",
            id="names-a-tool-the-line-has-by-alias",
        ),
        pytest.param(
            "Deployed services on K8s",
            "Deployed services on Kubernetes",
            id="renames-a-tool-by-alias",
        ),
        pytest.param(
            "Built a churn model in Python that cut churn by 12%",
            "Cut churn by 12% with a churn model built in Python",
            id="leads-with-the-outcome",
        ),
        pytest.param(
            OBSERVABILITY,
            "Set up AI observability with LangSmith for the RAG service that answers support "
            "tickets",
            id="adds-scope-from-another-line",
        ),
        pytest.param(
            "Wrote ETL jobs with Airflow",
            "Built ETL data pipelines with Airflow",
            id="renames-what-the-line-describes",
        ),
    ],
)
def test_a_genuine_rewrite_is_not_caught(before, after):
    assert keyword_only(_edit(before, after), JOB) is None


def test_added_lines_and_new_summaries_are_never_padding():
    skill = Suggestion(id="S01", kind="add_skill", target="S03", after="AI observability")
    new_summary = Suggestion(
        id="S02", kind="tailor_summary", target="new-summary", after="AI engineer."
    )

    assert keyword_only(skill, JOB) is None
    assert keyword_only(new_summary, JOB) is None


# The suggest node

CV = ParsedCV(
    lines=[
        CVLine(id="L001", text="Experience"),
        CVLine(id="L002", text=OBSERVABILITY),
        CVLine(id="L003", text="The RAG service answers 300 support tickets a day"),
    ],
    sections=[
        CVSection(id="S01", heading_line_id="L001", type="experience", line_ids=["L002", "L003"]),
    ],
)


def _state() -> dict:
    met = RequirementAssessment(
        requirement_id="R01",
        status="met",
        evidence=[Evidence(ref="L002", quote=OBSERVABILITY, match_type="semantic")],
    )
    job = JobPosting(requirements=[_req("R01", ["AI observability"])])
    return {
        "cv": CV.model_dump(),
        "job": job.model_dump(),
        "assessments": {"R01": met.model_dump()},
    }


def _draft(after: str, cited: list[str]) -> SuggestionDraft:
    return SuggestionDraft(
        kind="align_wording",
        target="L002",
        after=after,
        cited_refs=cited,
        requirement_ids=["R01"],
        rationale="Shows the tracing work and its scale.",
    )


PADDED = _draft("Set up AI observability for the RAG service with LangSmith", ["L002"])
STRONGER = _draft(
    "Set up AI observability with LangSmith for a RAG service answering 300 support tickets a day",
    ["L002", "L003"],
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_suggest_drops_padding_and_numbers_what_is_left():
    llm = FakeOptimizeLLM(suggestions=[PADDED, STRONGER])

    update = await make_optimize_nodes(llm)["suggest"](_state())

    suggestions = update["suggestions"]
    assert [s["id"] for s in suggestions] == ["S01"]
    assert suggestions[0]["after"] == STRONGER.after
    assert suggestions[0]["before"] == OBSERVABILITY
    assert suggestions[0]["verification"]["status"] == "pending"
    assert llm.calls == ["suggest"]


@pytest.mark.anyio
async def test_only_padding_leaves_no_suggestion_and_nothing_to_verify():
    llm = FakeOptimizeLLM(suggestions=[PADDED])
    nodes = make_optimize_nodes(llm)
    state = _state()

    update = await nodes["suggest"](state)

    assert update["suggestions"] == []
    assert nodes["route_verification"]({**state, **update}) == "gate_recency"
