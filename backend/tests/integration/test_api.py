import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.main import create_app
from tests.fakes import CV_TEXT, JOB_TEXT, FakeLLM


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


def test_create_streams_progress_then_the_report(client):
    response = client.post("/api/analyses", data={"cv_text": CV_TEXT, "job_text": JOB_TEXT})

    assert response.status_code == 200
    events = _events(response.text)
    names = [name for name, _ in events]
    assert names[0] == "created" and names[-1] == "report"
    assert "progress" in names

    report = events[-1][1]
    assert report["status"] == "paused"
    assert report["stage"] == "report_ready"
    assert report["verdict"]["label"] == "answer_questions"
    assert report["usage"]["calls"] == 3

    again = client.get(f"/api/analyses/{report['analysis_id']}")
    assert again.status_code == 200
    assert again.json()["score"] == report["score"]


def test_bad_input_gets_a_json_error_before_streaming(client):
    response = client.post("/api/analyses", data={"cv_text": CV_TEXT, "job_text": "too short"})

    assert response.status_code == 422
    assert response.json()["code"] == "job_too_short"


def test_unknown_analysis_is_404(client):
    response = client.get("/api/analyses/does-not-exist")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
