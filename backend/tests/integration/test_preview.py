import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.api.routes import preview
from backedcv.main import create_app
from tests.fakes import CV_TEXT, JOB_TEXT
from tests.fakes_optimize import FakeOptimizeLLM

PREVIEW_PATH = "/api/analyses/{analysis_id}/coverage-preview"


def _include_before_frontend(app) -> None:
    """Includes the preview router ahead of the frontend mount at "/", which would answer first."""
    start = len(app.router.routes)
    app.include_router(preview.router, prefix="/api")
    added = app.router.routes[start:]
    del app.router.routes[start:]
    app.router.routes[:0] = added


@pytest.fixture
def client():
    app = create_app(llm=FakeOptimizeLLM(), checkpointer=InMemorySaver())
    if PREVIEW_PATH not in {getattr(route, "path", None) for route in app.routes}:
        _include_before_frontend(app)
    with TestClient(app) as c:
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


def _created(client) -> str:
    response = client.post("/api/analyses", data={"cv_text": CV_TEXT, "job_text": JOB_TEXT})
    return _events(response.text)[-1][1]["analysis_id"]


def _reviewed(client) -> str:
    """An analysis with its suggestions made, waiting for the review."""
    analysis_id = _created(client)
    assert client.post(f"/api/analyses/{analysis_id}/optimize").status_code == 200
    return analysis_id


def _preview(client, analysis_id: str, accepted=()):
    url = PREVIEW_PATH.format(analysis_id=analysis_id)
    return client.post(url, json={"accepted": list(accepted)})


def _build(client, analysis_id: str, accepted=()):
    body = {"accepted": list(accepted), "rejected": []}
    return client.post(f"/api/analyses/{analysis_id}/build", json=body)


def test_accepting_nothing_previews_the_current_coverage(client):
    analysis_id = _reviewed(client)

    response = _preview(client, analysis_id)

    assert response.status_code == 200
    # Python and SQL are in the CV: 12 of 21 weight points.
    assert response.json() == {
        "coverage": 57.1,
        "coverage_now": 57.1,
        "gained_requirement_ids": [],
    }


@pytest.mark.parametrize("accepted", [["S01"], ["S03"]])
def test_a_verified_suggestion_adds_its_requirement_keyword(client, accepted):
    analysis_id = _reviewed(client)

    response = _preview(client, analysis_id, accepted)

    # "agent frameworks" (R03) appears once the suggestion is accepted: 18 of 21.
    assert response.json() == {
        "coverage": 85.7,
        "coverage_now": 57.1,
        "gained_requirement_ids": ["R03"],
    }


def test_an_unverified_suggestion_counts_for_nothing(client):
    analysis_id = _reviewed(client)

    response = _preview(client, analysis_id, ["S02"])

    assert response.json() == {
        "coverage": 57.1,
        "coverage_now": 57.1,
        "gained_requirement_ids": [],
    }


def test_the_preview_matches_the_built_cv_and_calls_no_model(client):
    analysis_id = _reviewed(client)
    calls = list(client.app.state.llm.calls)

    preview_body = _preview(client, analysis_id, ["S01"]).json()

    assert client.app.state.llm.calls == calls
    built = _build(client, analysis_id, accepted=["S01"])
    report = _events(built.text)[-1][1]["build_report"]
    assert report["coverage_before"] == preview_body["coverage_now"]
    assert report["coverage_after"] == preview_body["coverage"]


def test_the_preview_leaves_the_analysis_as_it_was(client):
    analysis_id = _reviewed(client)
    before = client.get(f"/api/analyses/{analysis_id}").json()

    _preview(client, analysis_id, ["S01", "S03"])

    assert client.get(f"/api/analyses/{analysis_id}").json() == before


def test_unknown_suggestion_ids_are_422(client):
    analysis_id = _reviewed(client)

    response = _preview(client, analysis_id, ["S01", "S99"])

    assert response.status_code == 422
    assert (response.json()["code"], response.json()["detail"]) == ("decisions_invalid", "S99")


def test_an_unknown_analysis_is_404(client):
    response = _preview(client, "does-not-exist", ["S01"])

    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_the_preview_waits_for_the_review(client):
    early = _preview(client, _created(client), ["S01"])
    assert (early.status_code, early.json()["code"]) == (409, "wrong_stage")

    analysis_id = _reviewed(client)
    assert _build(client, analysis_id, accepted=["S01"]).status_code == 200
    after = _preview(client, analysis_id, ["S01"])
    assert (after.status_code, after.json()["code"]) == (409, "wrong_stage")
