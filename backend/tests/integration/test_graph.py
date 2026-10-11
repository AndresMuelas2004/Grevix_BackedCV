import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.graph.builder import build_graph, run_config
from backedcv.ingestion import read_cv_text
from tests.fakes import CV_TEXT, JOB_TEXT, FakeLLM

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _run(job_text=JOB_TEXT):
    llm = FakeLLM()
    graph = build_graph(llm, checkpointer=InMemorySaver())
    analysis_id = str(uuid.uuid4())
    config = run_config(analysis_id)
    lines = read_cv_text(CV_TEXT).lines
    events = []
    async for mode, chunk in graph.astream(
        {
            "analysis_id": analysis_id,
            "cv_lines": [line.model_dump() for line in lines],
            "job_text": job_text,
        },
        config,
        stream_mode=["custom", "updates"],
    ):
        events.append((mode, chunk))
    state = await graph.aget_state(config)
    return llm, state, events


async def test_full_analysis_pauses_before_optimizing():
    llm, state, events = await _run()
    values = state.values

    assert state.next == ("await_optimize",)
    assert sorted(llm.calls) == [
        "match_chunk",
        "prepare_cv",
        "prepare_job",
        "review_posting",
        "screen_barriers",
    ]
    assert any(m == "custom" and c["step"] == "score" for m, c in events)

    # The requirement whose quote is not in the posting is dropped.
    labels = [r["label"] for r in values["job"]["requirements"]]
    assert "Rust" not in labels

    a = values["assessments"]
    assert a["R03"]["status"] == "met"  # semantic match, with a receipt
    assert a["R03"]["evidence"][0]["quote"] == "Built a support bot with LangGraph"
    assert a["R05"]["status"] == "unknown"  # gates are never "missing" without evidence
    assert a["R06"]["status"] == "missing"  # invented line ID: no evidence, no credit

    # Junior posting asking for 5+ years: flagged R1, out of Fit.
    assert values["flags"][0]["rule_id"] == "R1"
    assert values["verdict"]["label"] == "answer_questions"
    assert values["cv"]["facts"][0]["id"] == "F01"


async def test_posting_without_requirements_still_reaches_the_report(monkeypatch):
    from tests import fakes

    empty = fakes.job_draft().model_copy(update={"requirements": []})
    monkeypatch.setattr(fakes, "job_draft", lambda: empty)

    llm, state, _ = await _run()

    assert state.next == ("await_optimize",)
    assert "match_chunk" not in llm.calls
    assert state.values["score"]["fit"] is None
