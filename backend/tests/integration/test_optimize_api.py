import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.graph import nodes, optimize_nodes
from backedcv.main import create_app
from tests.fakes import CV_TEXT, JOB_TEXT, FakeLLM
from tests.fakes_optimize import FakeOptimizeLLM


@pytest.fixture
def client():
    with TestClient(create_app(llm=FakeOptimizeLLM(), checkpointer=InMemorySaver())) as c:
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


def _analysis_id(client) -> str:
    response = client.post("/api/analyses", data={"cv_text": CV_TEXT, "job_text": JOB_TEXT})
    return _events(response.text)[-1][1]["analysis_id"]


def _optimize(client, analysis_id: str):
    return client.post(f"/api/analyses/{analysis_id}/optimize")


def _build(client, analysis_id: str, accepted=(), rejected=()):
    body = {"accepted": list(accepted), "rejected": list(rejected)}
    return client.post(f"/api/analyses/{analysis_id}/build", json=body)


def _verify(client, analysis_id: str, suggestion_id: str, after: str):
    url = f"/api/analyses/{analysis_id}/suggestions/{suggestion_id}/verify"
    return client.post(url, json={"after": after})


def _reviewed(client) -> str:
    """An analysis with its suggestions made, waiting for the review."""
    analysis_id = _analysis_id(client)
    assert _optimize(client, analysis_id).status_code == 200
    return analysis_id


def _suggestions(projection: dict) -> dict[str, dict]:
    return {s["id"]: s for s in projection["suggestions"]}


def _lines(document: dict) -> list[str]:
    return [
        line["text"]
        for section in document["sections"]
        for item in section["items"]
        for line in item["lines"]
    ]


def test_optimize_streams_progress_then_the_suggestions(client):
    analysis_id = _analysis_id(client)

    response = _optimize(client, analysis_id)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert events[0][0] == "progress"
    assert events[-1][0] == "suggestions"
    projection = events[-1][1]
    assert (projection["status"], projection["stage"]) == ("paused", "review_ready")
    statuses = {sid: s["verification"]["status"] for sid, s in _suggestions(projection).items()}
    assert statuses == {"S01": "verified", "S02": "unsupported", "S03": "verified"}
    s02 = _suggestions(projection)["S02"]["verification"]
    assert s02["reason"] == "not in the cited lines or the original: 40"


def test_the_whole_flow_ends_in_a_built_cv(client):
    analysis_id = _reviewed(client)

    response = _build(client, analysis_id, accepted=["S01", "S03"], rejected=["S02"])

    assert response.status_code == 200
    events = _events(response.text)
    assert events[0][0] == "progress"
    assert events[-1][0] == "built"
    built = events[-1][1]
    assert (built["status"], built["stage"]) == ("done", "built")
    assert built["decisions"] == {"accepted": ["S01", "S03"], "rejected": ["S02"]}
    assert built["build_report"]["roundtrip_ok"] is True
    lines = _lines(built["document"])
    assert "Built a support bot with agent frameworks (LangGraph)" in lines
    assert "agent frameworks" in lines
    invented = "Built a support bot with agent frameworks (LangGraph), cutting tickets by 40%"
    assert invented not in lines
    docx = client.get(f"/api/analyses/{analysis_id}/cv.docx")
    pdf = client.get(f"/api/analyses/{analysis_id}/cv.pdf")
    assert (docx.status_code, docx.content[:2]) == (200, b"PK")
    assert (pdf.status_code, pdf.content[:4]) == (200, b"%PDF")


def test_a_cv_with_no_suggestions_still_reaches_the_build():
    llm = FakeOptimizeLLM(suggestions=[])
    with TestClient(create_app(llm=llm, checkpointer=InMemorySaver())) as client:
        analysis_id = _analysis_id(client)
        optimized = _events(_optimize(client, analysis_id).text)[-1][1]
        assert (optimized["stage"], optimized["suggestions"]) == ("review_ready", [])

        events = _events(_build(client, analysis_id).text)

    assert (events[-1][0], events[-1][1]["stage"]) == ("built", "built")


def test_each_step_is_refused_at_the_wrong_stage(client):
    analysis_id = _analysis_id(client)
    early = [
        _build(client, analysis_id),
        _verify(client, analysis_id, "S01", "Built a support bot"),
    ]
    assert [(r.status_code, r.json()["code"]) for r in early] == [(409, "wrong_stage")] * 2

    again = _optimize(client, _reviewed(client))
    assert (again.status_code, again.json()["code"]) == (409, "wrong_stage")


def test_a_run_in_progress_refuses_the_steps(client):
    analysis_id = _analysis_id(client)
    locks = client.app.state.locks
    locks.acquire(analysis_id)
    try:
        responses = [
            _optimize(client, analysis_id),
            _build(client, analysis_id),
            _verify(client, analysis_id, "S01", "Built a support bot"),
        ]
    finally:
        locks.release(analysis_id)

    assert [(r.status_code, r.json()["code"]) for r in responses] == [(409, "run_in_progress")] * 3


def test_unknown_analysis_is_404_for_each_step(client):
    responses = [
        _optimize(client, "does-not-exist"),
        _build(client, "does-not-exist"),
        _verify(client, "does-not-exist", "S01", "Built a support bot"),
    ]
    assert [(r.status_code, r.json()["code"]) for r in responses] == [(404, "not_found")] * 3


@pytest.mark.parametrize(
    "decisions",
    [
        {"accepted": ["S02"]},  # not verified: the number is not in the CV
        {"accepted": ["S99"]},  # no such suggestion
        {"accepted": ["S01"], "rejected": ["S01"]},  # both at once
    ],
)
def test_decisions_that_cannot_be_applied_are_422(client, decisions):
    analysis_id = _reviewed(client)
    before = client.get(f"/api/analyses/{analysis_id}").json()

    response = client.post(f"/api/analyses/{analysis_id}/build", json=decisions)

    assert response.status_code == 422
    assert response.json()["code"] == "decisions_invalid"
    assert client.get(f"/api/analyses/{analysis_id}").json() == before


def test_an_edit_that_invents_a_number_is_unsupported(client):
    analysis_id = _reviewed(client)
    invented = "Built a support bot with agent frameworks (LangGraph), cutting tickets by 55%"

    response = _verify(client, analysis_id, "S01", invented)

    assert response.status_code == 200
    projection = response.json()
    s01 = _suggestions(projection)["S01"]
    assert (s01["after"], s01["edited_by_user"]) == (invented, True)
    assert s01["verification"]["status"] == "unsupported"
    assert s01["verification"]["reason"] == "not in the cited lines or the original: 55"
    assert (projection["status"], projection["stage"]) == ("paused", "review_ready")
    assert _build(client, analysis_id, accepted=["S01"]).status_code == 422


def test_a_faithful_edit_is_verified_and_the_build_still_works(client):
    analysis_id = _reviewed(client)
    faithful = "Built a support bot with LangGraph, an agent framework"

    response = _verify(client, analysis_id, "S01", faithful)

    projection = response.json()
    s01 = _suggestions(projection)["S01"]
    assert (s01["edited_by_user"], s01["verification"]["status"]) == (True, "verified")
    assert (projection["status"], projection["stage"]) == ("paused", "review_ready")

    events = _events(_build(client, analysis_id, accepted=["S01"]).text)
    assert events[-1][0] == "built"
    assert faithful in _lines(events[-1][1]["document"])


def test_editing_an_unknown_suggestion_is_404(client):
    analysis_id = _reviewed(client)

    response = _verify(client, analysis_id, "S99", "Built a support bot")

    assert (response.status_code, response.json()["code"]) == (404, "suggestion_not_found")


def test_an_invalid_body_gets_the_standard_error_body(client):
    analysis_id = _reviewed(client)

    response = _verify(client, analysis_id, "S01", "   ")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_request"
    assert body["title"] == "The request is not valid."
    assert body["detail"].startswith("body.after: ")


def test_a_failing_optimize_ends_with_a_readable_error_event(client, monkeypatch):
    analysis_id = _analysis_id(client)

    def broken(*_args):
        raise ValueError("the guards broke")

    monkeypatch.setattr(optimize_nodes, "apply_guards", broken)
    events = _events(_optimize(client, analysis_id).text)

    assert events[-1] == (
        "error",
        {
            "code": "optimize_failed",
            "title": "The suggestions could not be made.",
            "detail": "the guards broke",
        },
    )
    assert not client.app.state.locks.is_running(analysis_id)


def test_a_failing_analysis_ends_with_a_readable_error_event(monkeypatch):
    def broken(_state):
        raise ValueError("the score broke")

    monkeypatch.setattr(nodes, "recompute", broken)
    with TestClient(create_app(llm=FakeLLM(), checkpointer=InMemorySaver())) as client:
        response = client.post("/api/analyses", data={"cv_text": CV_TEXT, "job_text": JOB_TEXT})

    assert _events(response.text)[-1] == (
        "error",
        {
            "code": "analysis_failed",
            "title": "The analysis could not finish.",
            "detail": "the score broke",
        },
    )
