import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backedcv.api.projection import project
from backedcv.graph.builder import build_graph, run_config
from backedcv.graph.state import merge_items_by_id
from backedcv.ingestion import read_cv_text
from backedcv.llm.drafts import CVStructureDraft
from backedcv.llm.drafts_optimize import PostingReviewDraft
from backedcv.llm.structured import LLMError
from backedcv.main import create_app
from tests import fakes
from tests.fakes import CV_TEXT, JOB_TEXT, FakeLLM


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FailingStructureLLM(FakeLLM):
    async def run(self, prompt, data, schema, *, node):
        if schema is CVStructureDraft:
            self.calls.append(node)
            raise LLMError("prepare_cv: invalid structured output")
        return await super().run(prompt, data, schema, node=node)


class FailingReviewLLM(FakeLLM):
    async def run(self, prompt, data, schema, *, node):
        if schema is PostingReviewDraft:
            self.calls.append(node)
            raise LLMError("review_posting: invalid structured output")
        return await super().run(prompt, data, schema, node=node)


class SlowReviewLLM(FakeLLM):
    """The review answers last, so the badge shows only if the run waits for it."""

    async def run(self, prompt, data, schema, *, node):
        if schema is PostingReviewDraft:
            await asyncio.sleep(0.3)
        return await super().run(prompt, data, schema, node=node)


async def _run(llm, cv_meta=None):
    graph = build_graph(llm, checkpointer=InMemorySaver())
    analysis_id = str(uuid.uuid4())
    config = run_config(analysis_id)
    initial = {
        "analysis_id": analysis_id,
        "cv_meta": cv_meta or {"multi_column": False, "size": len(CV_TEXT.encode())},
        "cv_lines": [line.model_dump() for line in read_cv_text(CV_TEXT).lines],
        "job_text": JOB_TEXT,
    }
    await graph.ainvoke(initial, config)
    return await graph.aget_state(config)


@pytest.mark.anyio
async def test_parse_warnings_use_the_cv_and_its_file_details():
    state = await _run(FakeLLM(), cv_meta={"multi_column": True, "size": 3 * 1024 * 1024})

    warnings = state.values["parse_warnings"]
    assert {"multi_column", "large_file", "tip_word_count"} <= {w["code"] for w in warnings}
    assert all(set(w) == {"code", "severity", "message", "line_ids"} for w in warnings)


@pytest.mark.anyio
async def test_parse_warnings_are_kept_when_structuring_fails():
    state = await _run(FailingStructureLLM())

    codes = {w["code"] for w in state.values["parse_warnings"]}
    assert {"missing_section", "tip_word_count"} <= codes  # no structure, so no section found
    assert state.next == ("await_optimize",)


@pytest.mark.anyio
async def test_posting_review_adds_an_r4_banner_and_the_red_flags_badge():
    state = await _run(FakeLLM())
    values = state.values

    [banner] = values["review_banners"]
    assert banner["rule_id"] == "R4"
    assert banner["severity"] == "info"
    assert '"Work fully remote from anywhere"' in banner["explanation"]
    assert values["banners"] == []  # R4 is kept apart from the R3 banners in state
    assert "posting_red_flags" in values["verdict"]["badges"]


@pytest.mark.anyio
async def test_failed_posting_review_degrades_without_failing_the_run():
    state = await _run(FailingReviewLLM())
    values = state.values

    assert state.next == ("await_optimize",)
    assert values["review_banners"] == []
    assert [e["node"] for e in values["errors"]] == ["review_posting"]
    assert "posting_red_flags" not in values["verdict"]["badges"]
    assert values["score"]


@pytest.mark.anyio
@pytest.mark.parametrize("with_requirements", [True, False])
async def test_score_waits_for_the_posting_review_on_both_routes(monkeypatch, with_requirements):
    if not with_requirements:
        empty = fakes.job_draft().model_copy(update={"requirements": []})
        monkeypatch.setattr(fakes, "job_draft", lambda: empty)
    llm = SlowReviewLLM()

    state = await _run(llm)

    assert ("match_chunk" in llm.calls) is with_requirements
    assert "posting_red_flags" in state.values["verdict"]["badges"]


@pytest.mark.anyio
async def test_tool_sprawl_banner_from_the_posting_reaches_the_badge(monkeypatch):
    # Eleven hard skills across four or more areas. Each reuses a quote that is in the posting.
    template = fakes.job_draft().requirements[0]
    skills = [
        "React",
        "Django",
        "PostgreSQL",
        "Docker",
        "Kubernetes",
        "AWS",
        "PyTorch",
        "Kafka",
        "Selenium",
        "Figma",
        "Salesforce",
    ]
    requirements = [template.model_copy(update={"label": s, "terms": []}) for s in skills]
    sprawl = fakes.job_draft().model_copy(update={"requirements": requirements})
    monkeypatch.setattr(fakes, "job_draft", lambda: sprawl)

    state = await _run(FailingReviewLLM())

    [banner] = state.values["banners"]
    assert (banner["rule_id"], len(banner["requirement_ids"])) == ("R3", len(skills))
    assert "posting_red_flags" in state.values["verdict"]["badges"]


@pytest.fixture
def client():
    with TestClient(create_app(llm=FakeLLM(), checkpointer=InMemorySaver())) as c:
        yield c


def _events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if ": " in line and line[0] != ":"
        )
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def _analysis(client) -> dict:
    response = client.post("/api/analyses", data={"cv_text": CV_TEXT, "job_text": JOB_TEXT})
    return _events(response.text)[-1][1]


def _resume(client, analysis_id: str) -> None:
    # Not {}: LangGraph reads an empty dict as an empty resume map and nothing resumes.
    # Two pauses: optimize, then the review of suggestions (accept nothing).
    graph, config = client.app.state.graph, run_config(analysis_id)
    asyncio.run(graph.ainvoke(Command(resume=True), config))
    asyncio.run(graph.ainvoke(Command(resume={"accepted": [], "rejected": []}), config))


def test_report_carries_the_new_keys_with_their_defaults(client):
    report = _analysis(client)

    assert (report["status"], report["stage"]) == ("paused", "report_ready")
    assert report["cv_meta"]["multi_column"] is False
    assert "tip_word_count" in {w["code"] for w in report["parse_warnings"]}
    assert [b["rule_id"] for b in report["banners"]] == ["R4"]
    assert (report["suggestions"], report["decisions"], report["document"]) == ([], None, None)
    assert report["build_report"] is None
    assert client.get(f"/api/analyses/{report['analysis_id']}").json() == report


def test_finished_run_projects_as_built(client):
    analysis_id = _analysis(client)["analysis_id"]
    _resume(client, analysis_id)

    finished = client.get(f"/api/analyses/{analysis_id}").json()

    assert (finished["status"], finished["stage"]) == ("done", "built")
    assert finished["suggestions"] == []


def test_a_pause_for_the_review_projects_as_review_ready():
    snapshot = SimpleNamespace(values={}, next=("await_review",), interrupts=())

    projected = project("analysis-id", snapshot)

    assert (projected["status"], projected["stage"]) == ("paused", "review_ready")


def test_suggestions_merge_by_id_and_keep_their_order():
    left = [{"id": "S01", "after": "old"}, {"id": "S02", "after": "kept"}]
    right = [{"id": "S01", "after": "new"}, {"id": "S03", "after": "added"}]

    assert merge_items_by_id(left, right) == [
        {"id": "S01", "after": "new"},
        {"id": "S02", "after": "kept"},
        {"id": "S03", "after": "added"},
    ]
