import asyncio
import json
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backedcv.api.retention import purge_expired, purge_hourly
from backedcv.llm.cache import LLMCache
from backedcv.main import create_app
from backedcv.settings import get_settings
from tests.fakes import CV_TEXT, JOB_TEXT, FakeLLM


@pytest.fixture
def client():
    with TestClient(create_app(llm=FakeLLM(), checkpointer=InMemorySaver())) as c:
        yield c


def _analysis_id(client) -> str:
    response = client.post("/api/analyses", data={"cv_text": CV_TEXT, "job_text": JOB_TEXT})
    last = [line for line in response.text.splitlines() if line.startswith("data: ")][-1]
    return json.loads(last.removeprefix("data: "))["analysis_id"]


def _in_hours(hours: float) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


def _purge(client, now: datetime, cache: LLMCache | None = None) -> list[str]:
    app = client.app
    return asyncio.run(
        purge_expired(
            app.state.ledger, app.state.checkpointer, app.state.locks, now=now, cache=cache
        )
    )


def test_analyses_younger_than_a_day_are_kept(client):
    analysis_id = _analysis_id(client)

    assert _purge(client, _in_hours(23)) == []
    assert client.get(f"/api/analyses/{analysis_id}").status_code == 200


def test_analyses_older_than_a_day_are_deleted_with_their_checkpoints(client):
    analysis_id = _analysis_id(client)

    assert _purge(client, _in_hours(25)) == [analysis_id]

    gone = client.get(f"/api/analyses/{analysis_id}")
    assert (gone.status_code, gone.json()["code"]) == (404, "not_found")
    assert _purge(client, _in_hours(50)) == []


def test_a_run_in_progress_is_skipped_until_it_ends(client):
    analysis_id = _analysis_id(client)
    locks = client.app.state.locks
    locks.acquire(analysis_id)
    try:
        assert _purge(client, _in_hours(25)) == []
    finally:
        locks.release(analysis_id)

    assert _purge(client, _in_hours(25)) == [analysis_id]


def test_the_hourly_pass_takes_its_time_from_the_clock(client):
    analysis_id = _analysis_id(client)
    app = client.app
    later = _in_hours(25)

    async def run_until_purged() -> None:
        task = asyncio.create_task(
            purge_hourly(app.state.ledger, app.state.checkpointer, app.state.locks, lambda: later)
        )
        for _ in range(500):  # the first pass runs at once; this only waits for it
            if not app.state.ledger.created_before(later):
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run_until_purged())

    assert app.state.ledger.created_before(later) == []
    gone = client.get(f"/api/analyses/{analysis_id}")
    assert gone.status_code == 404


def test_the_purge_task_stops_with_the_app():
    with TestClient(create_app(llm=FakeLLM(), checkpointer=InMemorySaver())) as client:
        task = client.app.state.purge_task
        assert not task.done()

    assert task.done()


def test_llm_cache_rows_follow_the_same_day_limit(client, tmp_path):
    cache = LLMCache(tmp_path / "llm_cache.sqlite")
    cache.put("answer", {"label": "supported", "score": 3}, 120, 30)

    _purge(client, _in_hours(23), cache)
    assert cache.get("answer") is not None

    _purge(client, _in_hours(25), cache)
    assert cache.get("answer") is None


def test_the_app_purges_the_llm_cache_file_in_its_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKEDCV_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    cache = LLMCache(tmp_path / "llm_cache.sqlite")
    cache.put("old", {"label": "supported", "score": 3}, 120, 30)
    cache.put("fresh", {"label": "supported", "score": 3}, 120, 30)
    with closing(sqlite3.connect(tmp_path / "llm_cache.sqlite")) as db, db:
        db.execute(
            "UPDATE answers SET created_at = ? WHERE key = 'old'",
            ((datetime.now(UTC) - timedelta(hours=25)).timestamp(),),
        )

    try:
        with TestClient(create_app(llm=FakeLLM())):
            for _ in range(500):  # the first pass runs at startup; this only waits for it
                if cache.get("old") is None:
                    break
                time.sleep(0.01)
    finally:
        get_settings.cache_clear()

    assert cache.get("old") is None
    assert cache.get("fresh") is not None
