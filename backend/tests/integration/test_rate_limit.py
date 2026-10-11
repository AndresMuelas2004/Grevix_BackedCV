import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.api.errors import ApiError
from backedcv.api.rate_limit import RunLimiter
from backedcv.main import create_app
from backedcv.settings import get_settings
from tests.fakes import CV_TEXT, JOB_TEXT, FakeLLM


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@contextmanager
def _client(monkeypatch, *, per_hour: int = 30, daily: int = 300) -> Iterator[TestClient]:
    """An app whose limits come from the settings, the same way as in production."""
    monkeypatch.setenv("BACKEDCV_RATE_LIMIT_PER_HOUR", str(per_hour))
    monkeypatch.setenv("BACKEDCV_DAILY_MODEL_RUNS", str(daily))
    get_settings.cache_clear()
    with TestClient(create_app(llm=FakeLLM(), checkpointer=InMemorySaver())) as client:
        yield client


def _create(client: TestClient):
    return client.post("/api/analyses", data={"cv_text": CV_TEXT, "job_text": JOB_TEXT})


def _analysis_id(response) -> str:
    """The ID is in the first event of the stream (`created`)."""
    first_data = next(line for line in response.text.splitlines() if line.startswith("data: "))
    return json.loads(first_data.removeprefix("data: "))["analysis_id"]


def test_the_hourly_limit_refuses_the_request_after_the_limit(monkeypatch):
    with _client(monkeypatch, per_hour=2) as client:
        assert _create(client).status_code == 200
        assert _create(client).status_code == 200

        response = _create(client)

    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert set(body) == {"code", "title", "detail"}
    assert body["code"] == "rate_limited"
    assert "2 requests an hour" in body["detail"]
    assert "Try again in" in body["detail"]


def test_the_daily_cap_refuses_runs_once_it_is_reached(monkeypatch):
    with _client(monkeypatch, daily=1) as client:
        assert _create(client).status_code == 200

        response = _create(client)

    assert response.status_code == 429
    assert response.json()["code"] == "daily_limit_reached"
    assert "midnight UTC" in response.json()["detail"]


def test_a_wrong_stage_is_refused_before_a_run_is_counted(monkeypatch):
    # The analysis is at the report stage. Build and verify fail that check, so they use no quota
    # and get a 409. Optimize passes its check, is counted, and gets the 429.
    with _client(monkeypatch, per_hour=1) as client:
        analysis_id = _analysis_id(_create(client))

        build = client.post(
            f"/api/analyses/{analysis_id}/build", json={"accepted": [], "rejected": []}
        )
        verify = client.post(
            f"/api/analyses/{analysis_id}/suggestions/S01/verify", json={"after": "x"}
        )
        optimize = client.post(f"/api/analyses/{analysis_id}/optimize")

    assert (build.status_code, build.json()["code"]) == (409, "wrong_stage")
    assert (verify.status_code, verify.json()["code"]) == (409, "wrong_stage")
    assert (optimize.status_code, optimize.json()["code"]) == (429, "rate_limited")


def test_a_refused_optimize_does_not_leave_the_analysis_running(monkeypatch):
    with _client(monkeypatch, per_hour=1) as client:
        analysis_id = _analysis_id(_create(client))
        assert client.post(f"/api/analyses/{analysis_id}/optimize").status_code == 429

        projection = client.get(f"/api/analyses/{analysis_id}").json()

    assert projection["status"] == "paused"


class Clock:
    """A clock that the test moves by hand."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_the_hourly_limit_counts_each_client_apart_and_rolls_over():
    clock = Clock(datetime(2026, 10, 11, 12, 0, tzinfo=UTC))
    limiter = RunLimiter(per_hour=2, per_day=100, clock=clock)
    limiter.check("198.51.100.1")
    clock.now += timedelta(minutes=10)
    limiter.check("198.51.100.1")

    with pytest.raises(ApiError) as refused:
        limiter.check("198.51.100.1")
    limiter.check("198.51.100.2")  # another client has its own budget

    clock.now += timedelta(minutes=51)  # the first run is now more than an hour old
    limiter.check("198.51.100.1")

    assert refused.value.status == 429
    assert refused.value.code == "rate_limited"
    assert "50 minutes" in refused.value.detail


def test_the_daily_cap_is_shared_and_starts_again_at_midnight_utc():
    clock = Clock(datetime(2026, 10, 11, 10, 0, tzinfo=UTC))
    limiter = RunLimiter(per_hour=30, per_day=2, clock=clock)
    limiter.check("198.51.100.1")
    limiter.check("198.51.100.2")

    with pytest.raises(ApiError) as refused:
        limiter.check("198.51.100.3")

    assert refused.value.code == "daily_limit_reached"
    assert "in 14 hours" in refused.value.detail

    clock.now = datetime(2026, 10, 12, 0, 1, tzinfo=UTC)
    limiter.check("198.51.100.3")
