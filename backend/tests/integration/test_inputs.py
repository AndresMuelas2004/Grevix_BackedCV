import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backedcv.graph.builder import run_config
from backedcv.main import create_app
from tests.fakes import CV_TEXT, JOB_TEXT, FakeLLM


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def client(llm):
    with TestClient(create_app(llm=llm, checkpointer=InMemorySaver())) as c:
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


def _patch(client, analysis_id: str, body: dict):
    return client.patch(f"/api/analyses/{analysis_id}/inputs", json=body)


def _contribution(report: dict, label: str) -> dict:
    return next(c for c in report["score"]["contributions"] if c["label"] == label)


def _resume(client, analysis_id: str) -> None:
    """Continues the graph the way the optimize step does: Command(resume=...)."""
    # Not {}: LangGraph reads an empty dict as an empty resume map and nothing resumes.
    # Two pauses: optimize, then the review of suggestions (accept nothing).
    graph, config = client.app.state.graph, run_config(analysis_id)
    asyncio.run(graph.ainvoke(Command(resume=True), config))
    asyncio.run(graph.ainvoke(Command(resume={"accepted": [], "rejected": []}), config))


def test_answering_a_knockout_changes_the_verdict_without_a_model_call(client, llm):
    report = _analysis(client)
    analysis_id = report["analysis_id"]
    assert report["verdict"]["provisional"] is True
    knockout = _contribution(report, "US work authorization")["requirement_id"]
    model_calls = len(llm.calls)

    response = _patch(client, analysis_id, {"facts": {"needs_sponsorship": True}})

    assert response.status_code == 200
    updated = response.json()
    assert updated["verdict"]["label"] == "likely_screened_out"
    assert updated["verdict"]["provisional"] is False
    assert updated["assessments"][knockout]["status"] == "missing"
    assert updated["facts"]["needs_sponsorship"] is True
    assert (updated["status"], updated["stage"]) == ("paused", "report_ready")
    assert len(llm.calls) == model_calls
    assert client.get(f"/api/analyses/{analysis_id}").json() == updated


def test_excluding_a_requirement_takes_it_out_of_fit_and_keeps_earlier_answers(client):
    report = _analysis(client)
    analysis_id = report["analysis_id"]
    python = _contribution(report, "Python")["requirement_id"]
    answered = _patch(client, analysis_id, {"facts": {"needs_sponsorship": True}}).json()

    response = _patch(client, analysis_id, {"excluded_ids": [python]})

    assert response.status_code == 200
    updated = response.json()
    assert _contribution(updated, "Python")["excluded_reason"] == "not_relevant"
    assert updated["score"]["fit"] != answered["score"]["fit"]
    assert updated["facts"]["needs_sponsorship"] is True


def test_including_a_flagged_requirement_counts_it_again(client):
    report = _analysis(client)
    analysis_id = report["analysis_id"]
    kubernetes = _contribution(report, "5+ years of Kubernetes")
    assert kubernetes["excluded_reason"] == "flagged_R1"

    response = _patch(client, analysis_id, {"included_flagged_ids": [kubernetes["requirement_id"]]})

    assert response.status_code == 200
    updated = response.json()
    assert _contribution(updated, "5+ years of Kubernetes")["excluded_reason"] is None
    assert updated["score"]["fit"] != report["score"]["fit"]


def test_one_answer_keeps_the_other_answers_and_the_other_facts(client):
    report = _analysis(client)
    analysis_id = report["analysis_id"]
    work_auth = _contribution(report, "US work authorization")["requirement_id"]
    kubernetes = _contribution(report, "5+ years of Kubernetes")["requirement_id"]
    _patch(client, analysis_id, {"facts": {"answers": {work_auth: True}}})

    response = _patch(client, analysis_id, {"facts": {"answers": {kubernetes: False}}})

    assert response.status_code == 200
    assert response.json()["facts"]["answers"] == {work_auth: True, kubernetes: False}
    kept = _patch(client, analysis_id, {"facts": {"needs_sponsorship": True}}).json()
    assert kept["facts"]["answers"] == {work_auth: True, kubernetes: False}
    assert kept["facts"]["needs_sponsorship"] is True


def test_unknown_requirement_id_is_422_and_changes_nothing(client):
    report = _analysis(client)
    analysis_id = report["analysis_id"]

    response = _patch(client, analysis_id, {"excluded_ids": ["R99"]})

    assert response.status_code == 422
    assert response.json()["code"] == "inputs_invalid"
    assert client.get(f"/api/analyses/{analysis_id}").json() == report


def test_unknown_analysis_is_404(client):
    response = _patch(client, "does-not-exist", {})

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_inputs_are_refused_while_a_run_holds_the_lock(client):
    analysis_id = _analysis(client)["analysis_id"]
    client.app.state.locks.acquire(analysis_id)
    try:
        response = _patch(client, analysis_id, {})
    finally:
        client.app.state.locks.release(analysis_id)

    assert response.status_code == 409
    assert response.json()["code"] == "run_in_progress"


def test_resume_after_an_edit_reaches_the_end(client):
    analysis_id = _analysis(client)["analysis_id"]
    edited = _patch(client, analysis_id, {"facts": {"needs_sponsorship": True}}).json()

    _resume(client, analysis_id)

    finished = client.get(f"/api/analyses/{analysis_id}").json()
    assert finished["status"] == "done"
    assert finished["verdict"] == edited["verdict"]


def test_inputs_are_refused_once_the_analysis_is_finished(client):
    analysis_id = _analysis(client)["analysis_id"]
    _resume(client, analysis_id)

    response = _patch(client, analysis_id, {})

    assert response.status_code == 409
    assert response.json()["code"] == "not_paused"
