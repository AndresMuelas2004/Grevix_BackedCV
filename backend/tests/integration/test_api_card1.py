"""Screening keys in the projection, barrier answers in PATCH inputs, and refused suggestions."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.api.projection import project
from backedcv.domain.models import HiddenRisk
from backedcv.graph.builder import run_config
from backedcv.main import create_app
from tests.fakes import CV_TEXT, JOB_TEXT
from tests.fakes_optimize import FakeOptimizeLLM

CARD_1_KEYS = {"hidden_risks", "screening_flags", "recency", "refusals"}
FAITHFUL_EDIT = "Built a support bot with LangGraph, an agent framework"


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


def _reviewed(client) -> str:
    """An analysis with its suggestions made, waiting for the review."""
    analysis_id = _analysis_id(client)
    response = client.post(f"/api/analyses/{analysis_id}/optimize")
    assert _events(response.text)[-1][0] == "suggestions"
    return analysis_id


def _suggestions(projection: dict) -> dict[str, dict]:
    return {s["id"]: s for s in projection["suggestions"]}


def _verify(client, analysis_id: str, suggestion_id: str, after: str):
    url = f"/api/analyses/{analysis_id}/suggestions/{suggestion_id}/verify"
    return client.post(url, json={"after": after})


def _build(client, analysis_id: str, accepted: list[str]):
    return client.post(f"/api/analyses/{analysis_id}/build", json={"accepted": accepted})


def _hide_risk_on(client, analysis_id: str, requirement_id: str) -> None:
    """Stores an unanswered high barrier on one requirement, as the screening step does."""
    risk = HiddenRisk(
        id="H01",
        kind="work_authorization",
        quote="Must be authorized to work in the United States without sponsorship.",
        explanation="The CV shows no work authorization in the United States.",
        risk="high",
        requirement_ids=[requirement_id],
    )
    update = {"hidden_risks": [risk.model_dump()]}
    graph = client.app.state.graph
    asyncio.run(graph.aupdate_state(run_config(analysis_id), update, as_node="gate_barriers"))


def test_the_card_1_keys_default_to_empty_values():
    snapshot = SimpleNamespace(values={}, next=("await_optimize",), interrupts=())

    projected = project("analysis-id", snapshot)

    assert (projected["hidden_risks"], projected["screening_flags"]) == ([], [])
    assert (projected["recency"], projected["refusals"]) == ({}, [])


def test_patch_accepts_a_barrier_id_as_an_answer_and_returns_the_card_1_keys(client):
    analysis_id = _analysis_id(client)

    response = client.patch(
        f"/api/analyses/{analysis_id}/inputs", json={"facts": {"answers": {"H01": True}}}
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["facts"]["answers"] == {"H01": True}
    assert CARD_1_KEYS.issubset(updated)


def test_a_refused_suggestion_cannot_be_accepted_like_an_unsupported_one(client):
    analysis_id = _reviewed(client)
    _hide_risk_on(client, analysis_id, "R03")

    edited = _verify(client, analysis_id, "S01", FAITHFUL_EDIT).json()

    assert _suggestions(edited)["S01"]["verification"]["status"] == "refused"
    assert "S01" in [r["suggestion_id"] for r in edited["refusals"]]
    assert (edited["status"], edited["stage"]) == ("paused", "review_ready")
    refused = _build(client, analysis_id, accepted=["S01"])
    unsupported = _build(client, analysis_id, accepted=["S02"])
    assert (refused.status_code, refused.json()["code"]) == (422, "decisions_invalid")
    assert (unsupported.status_code, unsupported.json()["code"]) == (422, "decisions_invalid")
    assert refused.json()["title"] == unsupported.json()["title"]
    assert (refused.json()["detail"], unsupported.json()["detail"]) == ("S01", "S02")
