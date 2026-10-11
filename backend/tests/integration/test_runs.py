"""Runs survive their clients: a closed stream, a failed step that can be retried, and the quota."""

import asyncio
import json
import time
from collections import Counter
from urllib.parse import urlencode

import pytest
from fastapi.sse import ServerSentEvent
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.api.locks import RunLocks
from backedcv.api.rate_limit import RunLimiter
from backedcv.api.runs import Run, RunManager
from backedcv.graph import build_nodes, optimize_nodes
from backedcv.llm.drafts import JobExtractionDraft
from backedcv.llm.drafts_optimize import SuggestionsDraft
from backedcv.llm.structured import LLMError
from backedcv.main import create_app
from tests.fakes import CV_TEXT, JOB_TEXT, FakeLLM
from tests.fakes_optimize import FakeOptimizeLLM

DECISIONS = {"accepted": ["S01", "S03"], "rejected": ["S02"]}
ANALYSIS_FORM = {"cv_text": CV_TEXT, "job_text": JOB_TEXT}


def _events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if ": " in line and line[0] != ":"
        )
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def _analysis_id(client: TestClient) -> str:
    response = client.post("/api/analyses", data=ANALYSIS_FORM)
    return _events(response.text)[-1][1]["analysis_id"]


def _optimize(client: TestClient, analysis_id: str):
    return client.post(f"/api/analyses/{analysis_id}/optimize")


def _build(client: TestClient, analysis_id: str, decisions: dict = DECISIONS):
    return client.post(f"/api/analyses/{analysis_id}/build", json=decisions)


def _settled(client: TestClient, analysis_id: str) -> dict:
    """The projection once the run has ended: a run can outlive the client that started it."""
    for _ in range(500):
        projection = client.get(f"/api/analyses/{analysis_id}").json()
        if projection["status"] != "running":
            return projection
        time.sleep(0.01)
    raise AssertionError("the run did not end")


def _post_and_leave_after_created(client: TestClient, path: str, form: dict) -> tuple[str, str]:
    """Opens an event stream the way a browser does, reads `created`, then disconnects. Returns the
    analysis ID that `created` carried, and the text the stream got before it was cut. The app
    runs on the test client's own event loop."""
    body = urlencode(form).encode()

    async def exchange() -> bytes:
        received: list[bytes] = []
        left = asyncio.Event()
        body_sent = False

        async def receive() -> dict:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await left.wait()  # the client stays connected until `created` has arrived
            return {"type": "http.disconnect"}

        async def send(message: dict) -> None:
            chunk = message.get("body", b"")
            if message["type"] == "http.response.body" and chunk:
                received.append(chunk)
                if b"event: created" in chunk:
                    left.set()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"accept", b"text/event-stream"),
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"content-length", str(len(body)).encode()),
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "state": {},
        }
        await client.app(scope, receive, send)
        return b"".join(received)

    stream = client.portal.call(exchange).decode()
    created = next(block for block in stream.split("\n\n") if block.startswith("event: created"))
    return json.loads(created.split("data: ", 1)[1])["analysis_id"], stream


def test_a_run_goes_on_after_the_client_leaves_at_created():
    with TestClient(create_app(llm=FakeLLM(), checkpointer=InMemorySaver())) as client:
        analysis_id, stream = _post_and_leave_after_created(client, "/api/analyses", ANALYSIS_FORM)
        projection = _settled(client, analysis_id)

    assert "event: report" not in stream  # the client really was gone before the end
    assert (projection["status"], projection["stage"]) == ("paused", "report_ready")
    assert "error" not in projection


def test_a_build_that_fails_once_can_be_retried(monkeypatch):
    applied = build_nodes.apply_suggestions
    attempts = []

    def fails_once(*args):
        attempts.append(args)
        if len(attempts) == 1:
            raise RuntimeError("the build broke")
        return applied(*args)

    monkeypatch.setattr(build_nodes, "apply_suggestions", fails_once)
    with TestClient(create_app(llm=FakeOptimizeLLM(), checkpointer=InMemorySaver())) as client:
        analysis_id = _analysis_id(client)
        assert _events(_optimize(client, analysis_id).text)[-1][0] == "suggestions"

        failed = _events(_build(client, analysis_id).text)[-1]
        stalled = client.get(f"/api/analyses/{analysis_id}").json()
        retried = _events(_build(client, analysis_id).text)[-1]
        done = client.get(f"/api/analyses/{analysis_id}").json()

    assert failed == (
        "error",
        {
            "code": "build_failed",
            "title": "The CV could not be built.",
            "detail": "the build broke",
        },
    )
    assert (stalled["status"], stalled["error"]["code"]) == ("stalled", "build_failed")
    assert (retried[0], retried[1]["status"]) == ("built", "done")
    assert (done["status"], "error" in done) == ("done", False)


@pytest.mark.parametrize("step_function", ["apply_guards", "_verdict"])  # suggest, then verify
def test_an_optimize_that_fails_once_can_be_retried(monkeypatch, step_function):
    original = getattr(optimize_nodes, step_function)
    attempts = []

    def fails_once(*args):
        attempts.append(args)
        if len(attempts) == 1:
            raise ValueError("the step broke")
        return original(*args)

    monkeypatch.setattr(optimize_nodes, step_function, fails_once)
    with TestClient(create_app(llm=FakeOptimizeLLM(), checkpointer=InMemorySaver())) as client:
        analysis_id = _analysis_id(client)

        failed = _events(_optimize(client, analysis_id).text)[-1]
        stalled = client.get(f"/api/analyses/{analysis_id}").json()
        retried = _events(_optimize(client, analysis_id).text)[-1]

    assert (failed[0], failed[1]["code"]) == ("error", "optimize_failed")
    assert (stalled["status"], stalled["error"]["detail"]) == ("stalled", "the step broke")
    assert (retried[0], retried[1]["status"], retried[1]["stage"]) == (
        "suggestions",
        "paused",
        "review_ready",
    )


class FlakySuggestLLM(FakeOptimizeLLM):
    """The first `failures` suggest calls fail, the later ones answer as usual."""

    def __init__(self, failures: int = 1):
        super().__init__()
        self.failures = failures
        self.suggest_calls = 0

    async def run(self, prompt, data, schema, *, node):
        if schema is SuggestionsDraft:
            self.suggest_calls += 1
            if self.suggest_calls <= self.failures:
                raise LLMError("suggest: invalid structured output")
        return await super().run(prompt, data, schema, node=node)


def _progress_steps(events: list[tuple[str, dict]]) -> Counter:
    return Counter((data["step"], data["status"]) for name, data in events if name == "progress")


def test_a_failed_suggest_step_is_run_again_from_the_review():
    # The first suggest call fails and the next ones succeed, so a second analysis run normally.
    with TestClient(create_app(llm=FlakySuggestLLM(), checkpointer=InMemorySaver())) as client:
        analysis_id = _analysis_id(client)
        # The graph does not stop on the error: the run waits at the review, with no suggestions.
        failed = _events(_optimize(client, analysis_id).text)[-1][1]
        assert (failed["stage"], failed["suggestions"]) == ("review_ready", [])
        assert [error["node"] for error in failed["errors"]] == ["suggest"]

        retried = _events(_optimize(client, analysis_id).text)
        normal = _events(_optimize(client, _analysis_id(client)).text)
        built = _events(_build(client, analysis_id, DECISIONS).text)[-1]

    assert retried[0][0] == "progress" and retried[-1][0] == "suggestions"
    assert _progress_steps(retried) == _progress_steps(normal)  # the same steps as a normal run
    projection = retried[-1][1]
    assert (projection["status"], projection["stage"]) == ("paused", "review_ready")
    assert projection["errors"] == []  # the failure is not shown
    statuses = {s["id"]: s["verification"]["status"] for s in projection["suggestions"]}
    assert statuses == {"S01": "verified", "S02": "unsupported", "S03": "verified"}
    assert built[0] == "built"  # the run still waits at the review, so the build goes on


def test_a_suggest_step_that_fails_again_is_shown_once_and_can_be_run_again():
    llm = FlakySuggestLLM(failures=2)
    with TestClient(create_app(llm=llm, checkpointer=InMemorySaver())) as client:
        analysis_id = _analysis_id(client)
        _optimize(client, analysis_id)
        again = _events(_optimize(client, analysis_id).text)[-1][1]
        recovered = _events(_optimize(client, analysis_id).text)[-1][1]

    assert [error["node"] for error in again["errors"]] == ["suggest"]  # one error, not two
    assert (again["suggestions"], again["stage"]) == ([], "review_ready")
    assert (recovered["errors"], len(recovered["suggestions"])) == ([], 3)


def test_an_empty_review_without_a_suggest_failure_is_not_optimized_again():
    llm = FakeOptimizeLLM(suggestions=[])
    with TestClient(create_app(llm=llm, checkpointer=InMemorySaver())) as client:
        analysis_id = _analysis_id(client)
        assert _events(_optimize(client, analysis_id).text)[-1][0] == "suggestions"

        response = _optimize(client, analysis_id)

    assert (response.status_code, response.json()["code"]) == (409, "wrong_stage")


def test_rejected_requests_do_not_use_up_the_quota():
    with TestClient(create_app(llm=FakeOptimizeLLM(), checkpointer=InMemorySaver())) as client:
        client.app.state.limiter = RunLimiter(per_hour=2, per_day=100)
        refused = [
            client.post("/api/analyses", data={"cv_text": CV_TEXT, "job_text": "too short"}),
            client.post("/api/analyses/does-not-exist/optimize"),
        ]
        analysis_id = _analysis_id(client)  # the first of the two counted runs
        refused += [
            _build(client, analysis_id),  # not reviewed yet
            client.post(f"/api/analyses/{analysis_id}/suggestions/S01/verify", json={"after": "x"}),
            client.post(f"/api/analyses/{analysis_id}/suggestions/S01/verify", json={"after": " "}),
        ]
        assert _optimize(client, analysis_id).status_code == 200  # the second counted run
        refused.append(_build(client, analysis_id, {"accepted": ["S99"], "rejected": []}))
        over_quota = client.post("/api/analyses", data=ANALYSIS_FORM)

    assert [(r.status_code, r.json()["code"]) for r in refused] == [
        (422, "job_too_short"),
        (404, "not_found"),
        (409, "wrong_stage"),
        (409, "wrong_stage"),
        (422, "invalid_request"),
        (422, "decisions_invalid"),
    ]
    assert (over_quota.status_code, over_quota.json()["code"]) == (429, "rate_limited")


def test_a_listener_that_starts_late_gets_the_events_so_far():
    async def scenario() -> tuple[list[str], bool]:
        locks = RunLocks()
        runs = RunManager(locks)
        first_sent, release = asyncio.Event(), asyncio.Event()

        async def work(run: Run) -> dict:
            run.emit(ServerSentEvent(event="progress", data={"step": "one"}))
            first_sent.set()
            await release.wait()
            run.emit(ServerSentEvent(event="progress", data={"step": "two"}))
            return {"ok": True}

        locks.acquire("late")
        run = runs.launch("late", work, done="done", failed=("failed", "The run failed."))
        await first_sent.wait()
        listener = run.listen()
        names = [(await anext(listener)).event]  # sent before this listener came: from the buffer
        release.set()
        lock_at_done = None
        async for event in listener:
            names.append(event.event)
            if event.event == "done":
                lock_at_done = locks.is_running("late")
        return names, lock_at_done

    # The lock is given back before the final event reaches a listener.
    assert asyncio.run(scenario()) == (["progress", "progress", "done"], False)


class HangingLLM(FakeLLM):
    """Never answers the posting extraction, so the run stays in progress until it is cancelled."""

    def __init__(self):
        super().__init__()
        self.started = False
        self.cancelled = False

    async def run(self, prompt, data, schema, *, node):
        if schema is JobExtractionDraft:
            self.started = True
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return await super().run(prompt, data, schema, node=node)


def test_shutdown_cancels_a_run_that_is_still_going():
    llm = HangingLLM()
    with TestClient(create_app(llm=llm, checkpointer=InMemorySaver())) as client:
        analysis_id, _ = _post_and_leave_after_created(client, "/api/analyses", ANALYSIS_FORM)
        for _ in range(500):
            if llm.started:
                break
            time.sleep(0.01)
        running = client.get(f"/api/analyses/{analysis_id}").json()["status"]

    assert running == "running"
    assert llm.cancelled
    assert not client.app.state.locks.is_running(analysis_id)
