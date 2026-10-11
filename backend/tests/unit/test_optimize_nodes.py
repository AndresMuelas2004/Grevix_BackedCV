import uuid
from typing import TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import ValidationError

from backedcv.domain.guards import NEW_SKILLS, NEW_SUMMARY
from backedcv.domain.models import (
    CVLine,
    CVSection,
    Evidence,
    JobPosting,
    ParsedCV,
    Requirement,
    RequirementAssessment,
    Suggestion,
    Verification,
)
from backedcv.graph.builder import build_graph, run_config
from backedcv.graph.optimize_nodes import make_optimize_nodes
from backedcv.graph.state import AnalysisState
from backedcv.ingestion import read_cv_text
from backedcv.llm.drafts_optimize import (
    ClaimDraft,
    SuggestionDraft,
    TermJudgementDraft,
    VerificationBatchDraft,
    VerificationDraft,
)
from tests.fakes import CV_TEXT, JOB_TEXT
from tests.fakes_optimize import FakeOptimizeLLM

# The CV of tests/fakes.CV_TEXT as the app reads it: L007 is "Built a support bot with LangGraph".
CV = ParsedCV(lines=read_cv_text(CV_TEXT).lines).model_dump()

# A hand-made CV with one section of each kind; PLAIN has the same lines and no sections.
SECTIONED = ParsedCV(
    lines=[
        CVLine(id="L001", text="Summary"),
        CVLine(id="L002", text="Built a support bot with LangGraph"),
        CVLine(id="L003", text="Skills"),
        CVLine(id="L004", text="Python"),
    ],
    sections=[
        CVSection(id="S01", heading_line_id="L001", type="summary", line_ids=["L001"]),
        CVSection(id="S02", heading_line_id=None, type="experience", line_ids=["L002"]),
        CVSection(id="S03", heading_line_id="L003", type="skills", line_ids=["L003", "L004"]),
    ],
)
PLAIN = ParsedCV(lines=SECTIONED.lines)


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _analysis_state(llm: FakeOptimizeLLM) -> dict:
    """The analysis graph run up to its first pause: the state the optimize nodes start from."""
    graph = build_graph(llm, checkpointer=InMemorySaver())
    analysis_id = str(uuid.uuid4())
    config = run_config(analysis_id)
    lines = read_cv_text(CV_TEXT).lines
    await graph.ainvoke(
        {
            "analysis_id": analysis_id,
            "cv_lines": [line.model_dump() for line in lines],
            "job_text": JOB_TEXT,
        },
        config,
    )
    return (await graph.aget_state(config)).values


def _state_for(cv: ParsedCV) -> dict:
    """Optimize input for a hand-made CV, where R01 is met by L002 but its term is not in the CV."""
    job = JobPosting(
        requirements=[
            Requirement(
                id="R01",
                label="Agent frameworks",
                quote="agent frameworks",
                category="hard_skill",
                importance="required",
                terms=["agent frameworks"],
            )
        ]
    )
    met = RequirementAssessment(
        requirement_id="R01",
        status="met",
        evidence=[
            Evidence(ref="L002", quote="Built a support bot with LangGraph", match_type="semantic")
        ],
    )
    return {
        "cv": cv.model_dump(),
        "job": job.model_dump(),
        "assessments": {"R01": met.model_dump()},
    }


def _suggestion(sid: str, target: str, kind: str = "align_wording", status: str = "pending"):
    return Suggestion(
        id=sid,
        kind=kind,
        target=target,
        after="Built a support bot with agent frameworks",
        cited_refs=["L002"],
        requirement_ids=["R01"],
        verification=Verification(status=status),
    ).model_dump()


class _Answers:
    """Stands in for the model: every call gets the same canned answer, or the same failure."""

    def __init__(self, answer):
        self.answer = answer
        self.calls: list[str] = []

    async def run(self, prompt, data, schema, *, node):
        self.calls.append(node)
        if isinstance(self.answer, Exception):
            raise self.answer
        usage = {"node": node, "model": "fake", "input_tokens": 0, "output_tokens": 0}
        return self.answer, {**usage, "cost_usd": 0.0}


# suggest ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_suggest_asks_only_about_requirements_met_without_their_words():
    llm = FakeOptimizeLLM()
    state = await _analysis_state(llm)
    llm.calls.clear()

    await make_optimize_nodes(llm)["suggest"](state)

    assert llm.calls == ["suggest"]
    node, data = llm.inputs[0]
    assert node == "suggest"
    requirements = data.split("<requirements>\n", 1)[1].split("\n</requirements>", 1)[0]
    assert requirements == 'R03 | terms: "agent frameworks" | evidence: L007'
    assert "<cv_lines>\nL001 | Jane Doe\n" in data
    assert "<facts>\nF01 | Total professional experience" in data


@pytest.mark.anyio
async def test_suggest_maps_ids_and_applies_the_guards():
    llm = FakeOptimizeLLM()
    state = await _analysis_state(llm)

    update = await make_optimize_nodes(llm)["suggest"](state)

    by_id = {s["id"]: s for s in update["suggestions"]}
    assert list(by_id) == ["S01", "S02", "S03"]
    assert by_id["S01"]["target"] == "L007"
    assert by_id["S01"]["before"] == "Built a support bot with LangGraph"
    assert by_id["S01"]["covers_requirement_ids"] == ["R03"]
    assert by_id["S01"]["verification"]["status"] == "pending"
    assert by_id["S02"]["verification"]["status"] == "unsupported"
    assert by_id["S02"]["verification"]["reason"] == "not in the cited lines or the original: 40"
    assert by_id["S03"]["target"] == NEW_SKILLS  # CV_TEXT has no Skills section
    assert by_id["S03"]["verification"]["status"] == "pending"
    assert update["usage"][0]["node"] == "suggest"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("excluded", "status"),
    [(["R03"], "met"), ([], "missing")],
    ids=["excluded", "not-met"],
)
async def test_suggest_makes_no_call_without_an_eligible_requirement(excluded, status):
    llm = FakeOptimizeLLM()
    state = await _analysis_state(llm)
    r03 = {**state["assessments"]["R03"], "status": status}
    state = {
        **state,
        "excluded_ids": excluded,
        "assessments": {**state["assessments"], "R03": r03},
    }
    llm.calls.clear()

    update = await make_optimize_nodes(llm)["suggest"](state)

    assert update == {"suggestions": []}
    assert llm.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("cv", "kind", "target", "expected"),
    [
        (SECTIONED, "add_skill", "L003", "S03"),  # the Skills heading line
        (SECTIONED, "add_skill", "L002", "S03"),  # a line outside Skills: first Skills section
        (SECTIONED, "tailor_summary", "L001", "S01"),  # the Summary heading line
        (PLAIN, "add_skill", "L003", NEW_SKILLS),
        (PLAIN, "tailor_summary", "L001", NEW_SUMMARY),
    ],
)
async def test_suggest_maps_heading_lines_to_section_ids(cv, kind, target, expected):
    draft = SuggestionDraft(
        kind=kind,
        target=target,
        after="agent frameworks",
        cited_refs=["L002"],
        requirement_ids=["R01"],
        rationale="L002 shows LangGraph, which is an agent framework.",
    )
    llm = FakeOptimizeLLM(suggestions=[draft])

    update = await make_optimize_nodes(llm)["suggest"](_state_for(cv))

    assert update["suggestions"][0]["target"] == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "drafted", "shown"),
    [
        ("add_skill", "vector databases", "Vector databases"),
        ("add_skill", "node.js", "Node.js"),
        ("add_skill", "iOS development", "iOS development"),  # a capital already: kept
        (
            "align_wording",  # other kinds keep their wording
            "built a support bot with agent frameworks",
            "built a support bot with agent frameworks",
        ),
    ],
)
async def test_suggest_capitalizes_skill_names_before_they_are_verified(kind, drafted, shown):
    draft = SuggestionDraft(
        kind=kind,
        target="L007",
        after=drafted,
        cited_refs=["L007"],
        requirement_ids=["R03"],
        rationale="L007 shows LangGraph, which is an agent framework.",
    )
    llm = FakeOptimizeLLM(suggestions=[draft])
    state = await _analysis_state(llm)
    nodes = make_optimize_nodes(llm)

    suggested = (await nodes["suggest"](state))["suggestions"]
    assert suggested[0]["after"] == shown

    sends = nodes["route_verification"]({**state, "suggestions": suggested})
    verified = (await nodes["verify_batch"](sends[0].arg))["suggestions"]
    assert [s["verification"]["status"] for s in verified] == ["verified"]
    assert f"after: {shown}" in llm.inputs[-1][1]


@pytest.mark.anyio
async def test_suggest_model_error_leaves_no_suggestions():
    state = await _analysis_state(FakeOptimizeLLM())

    update = await make_optimize_nodes(_Answers(RuntimeError("boom")))["suggest"](state)

    assert update == {
        "suggestions": [],
        "errors": [{"node": "suggest", "error": "RuntimeError", "detail": "boom"}],
    }


# route_verification ----------------------------------------------------------------------------


def test_route_sends_one_verification_per_section_with_pending_suggestions():
    state = {
        "cv": SECTIONED.model_dump(),
        "suggestions": [
            _suggestion("S01", "L002"),  # experience
            _suggestion("S02", "L002"),  # experience
            _suggestion("S03", "S03", kind="add_skill"),  # the skills section
            _suggestion("S04", "S01", kind="tailor_summary"),  # the summary section
            _suggestion("S05", NEW_SKILLS, kind="add_skill"),  # no skills section yet
            _suggestion("S06", "L002", status="unsupported"),  # failed the guards: not sent
        ],
    }

    sends = make_optimize_nodes(FakeOptimizeLLM())["route_verification"](state)

    assert all(send.node == "verify_batch" for send in sends)
    assert all(send.arg["cv"] == state["cv"] for send in sends)
    groups = {tuple(s["id"] for s in send.arg["group"]) for send in sends}
    assert groups == {("S01", "S02"), ("S03",), ("S04",), ("S05",)}


def test_route_goes_to_the_gates_when_nothing_is_pending():
    route = make_optimize_nodes(FakeOptimizeLLM())["route_verification"]
    cv = SECTIONED.model_dump()
    unsupported = _suggestion("S01", "L002", status="unsupported")

    assert route({"cv": cv, "suggestions": [unsupported]}) == "gate_recency"
    assert route({"cv": cv}) == "gate_recency"


@pytest.mark.anyio
async def test_only_suggestions_that_passed_the_guards_reach_the_verifier():
    llm = FakeOptimizeLLM()
    nodes = make_optimize_nodes(llm)
    state = await _analysis_state(llm)
    llm.calls.clear()
    state["suggestions"] = (await nodes["suggest"](state))["suggestions"]

    sends = nodes["route_verification"](state)

    assert sorted(s["id"] for send in sends for s in send.arg["group"]) == ["S01", "S03"]
    results = []
    for send in sends:
        results += (await nodes["verify_batch"](send.arg))["suggestions"]
    statuses = {s["id"]: s["verification"]["status"] for s in results}
    assert statuses == {"S01": "verified", "S03": "verified"}
    assert llm.calls == ["suggest", "verify_batch", "verify_batch"]


def _optimize_graph(llm: FakeOptimizeLLM):
    """The optimize nodes wired as the builder wires them, on the real analysis state."""
    nodes = make_optimize_nodes(llm)
    graph = StateGraph(AnalysisState)
    graph.add_node("suggest", nodes["suggest"])
    graph.add_node("verify_batch", nodes["verify_batch"])
    graph.add_node("gate_recency", nodes["gate_recency"])
    graph.add_node("gate_barriers", nodes["gate_barriers"])
    graph.add_node("await_review", nodes["await_review"])
    graph.add_edge(START, "suggest")
    graph.add_conditional_edges(
        "suggest", nodes["route_verification"], ["verify_batch", "gate_recency"]
    )
    graph.add_edge("verify_batch", "gate_recency")
    graph.add_edge("gate_recency", "gate_barriers")
    graph.add_edge("gate_barriers", "await_review")
    graph.add_edge("await_review", END)
    return graph.compile(checkpointer=InMemorySaver())


@pytest.mark.anyio
async def test_suggest_verify_and_review_run_as_one_langgraph():
    llm = FakeOptimizeLLM()
    values = await _analysis_state(llm)
    graph = _optimize_graph(llm)
    config = {"configurable": {"thread_id": "optimize"}}
    llm.calls.clear()

    await graph.ainvoke({key: values[key] for key in ("cv", "job", "assessments")}, config)

    paused = await graph.aget_state(config)
    assert paused.next == ("await_review",)
    assert llm.calls == ["suggest", "verify_batch", "verify_batch"]
    statuses = {s["id"]: s["verification"]["status"] for s in paused.values["suggestions"]}
    assert statuses == {"S01": "verified", "S02": "unsupported", "S03": "verified"}

    await graph.ainvoke(Command(resume={"accepted": ["S01"], "rejected": ["S03"]}), config)
    done = await graph.aget_state(config)
    assert done.values["decisions"] == {"accepted": ["S01"], "rejected": ["S03"]}


# verify_batch ----------------------------------------------------------------------------------

SUPPORTED = ClaimDraft(text="Built a support bot", supported_by=["L007"], unsupported_reason=None)
UNPROVEN = ClaimDraft(
    text="in production",
    supported_by=[],
    unsupported_reason="the CV does not say it runs in production",
)
ADDS_KUBERNETES = TermJudgementDraft(term="Kubernetes", verdict="adds_claim", line_id=None)


def _verdict_draft(claims=None, terms=None, uncertain=False) -> VerificationBatchDraft:
    draft = VerificationDraft(
        suggestion_id="S01",
        claims=claims or [SUPPORTED],
        term_judgements=terms or [],
        uncertain=uncertain,
    )
    return VerificationBatchDraft(verifications=[draft])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("answer", "status", "reason"),
    [
        pytest.param(_verdict_draft(), "verified", None, id="all-checks-pass"),
        pytest.param(
            _verdict_draft(claims=[UNPROVEN]),
            "unsupported",
            "the CV does not say it runs in production",
            id="unsupported-claim",
        ),
        pytest.param(
            _verdict_draft(terms=[ADDS_KUBERNETES]),
            "unsupported",
            "adds a claim: Kubernetes",
            id="adds-claim",
        ),
        pytest.param(
            _verdict_draft(uncertain=True),
            "unsupported",
            "the verifier was not sure",
            id="uncertain",
        ),
        pytest.param(
            _verdict_draft(claims=[UNPROVEN], terms=[ADDS_KUBERNETES]),
            "unsupported",
            "the CV does not say it runs in production",
            id="first-reason-wins",
        ),
        pytest.param(
            VerificationBatchDraft(verifications=[]),
            "unsupported",
            "not verified",
            id="missing-from-answer",
        ),
    ],
)
async def test_verify_batch_statuses_and_reasons(answer, status, reason):
    llm = _Answers(answer)

    update = await make_optimize_nodes(llm)["verify_batch"](
        {"cv": CV, "group": [_suggestion("S01", "L007")]}
    )

    verification = update["suggestions"][0]["verification"]
    assert (verification["status"], verification["reason"]) == (status, reason)
    assert llm.calls == ["verify_batch"]
    assert update["usage"][0]["node"] == "verify_batch"


@pytest.mark.anyio
async def test_verify_batch_fills_one_claim_check_per_claim():
    claims = [
        ClaimDraft(
            text="Built a support bot", supported_by=["L007", "L404"], unsupported_reason=None
        ),
        ClaimDraft(text="agent frameworks", supported_by=["L007"], unsupported_reason=None),
    ]

    update = await make_optimize_nodes(_Answers(_verdict_draft(claims=claims)))["verify_batch"](
        {"cv": CV, "group": [_suggestion("S01", "L007")]}
    )

    assert update["suggestions"][0]["verification"]["claims"] == [
        {
            "text": "Built a support bot",
            "supported_by": ["L007"],
            "ok": False,
            "reason": "cites IDs that are not in the CV: L404",
        },
        {"text": "agent frameworks", "supported_by": ["L007"], "ok": True, "reason": None},
    ]


@pytest.mark.anyio
async def test_verify_batch_error_marks_the_group_unsupported():
    suggestions = [_suggestion("S01", "L007"), _suggestion("S02", "L007")]

    update = await make_optimize_nodes(_Answers(RuntimeError("boom")))["verify_batch"](
        {"cv": CV, "group": suggestions}
    )

    assert [s["verification"]["status"] for s in update["suggestions"]] == ["unsupported"] * 2
    assert [s["verification"]["reason"] for s in update["suggestions"]] == [
        "verification failed"
    ] * 2
    assert update["errors"] == [{"node": "verify_batch", "error": "RuntimeError", "detail": "boom"}]


# await_review ----------------------------------------------------------------------------------


class _ReviewState(TypedDict, total=False):
    decisions: dict | None


def _review_graph():
    graph = StateGraph(_ReviewState)
    graph.add_node("await_review", make_optimize_nodes(FakeOptimizeLLM())["await_review"])
    graph.add_edge(START, "await_review")
    graph.add_edge("await_review", END)
    return graph.compile(checkpointer=InMemorySaver())


@pytest.mark.anyio
async def test_await_review_pauses_then_resumes_with_the_decisions():
    graph = _review_graph()
    config = {"configurable": {"thread_id": "review"}}

    await graph.ainvoke({}, config)
    paused = await graph.aget_state(config)
    assert paused.next == ("await_review",)
    assert paused.tasks[0].interrupts[0].value == {"stage": "review_ready"}

    await graph.ainvoke(Command(resume={"accepted": ["S01"], "rejected": ["S02"]}), config)
    done = await graph.aget_state(config)
    assert done.values["decisions"] == {"accepted": ["S01"], "rejected": ["S02"]}


@pytest.mark.anyio
async def test_await_review_rejects_a_malformed_resume():
    graph = _review_graph()
    config = {"configurable": {"thread_id": "review-malformed"}}
    await graph.ainvoke({}, config)

    with pytest.raises(ValidationError):
        await graph.ainvoke(Command(resume={"accepted": "S01"}), config)
