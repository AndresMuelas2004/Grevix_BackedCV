"""Pinned answers for the built-in samples: replayed with no model call and never expired."""

import asyncio
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from backedcv.llm import structured
from backedcv.llm.cache import PINNED_FILE, PINNED_FORMAT, load_pinned_answers, pinned_entry
from backedcv.llm.prompt_loader import load_prompt
from backedcv.llm.structured import OpenAIStructuredLLM
from backedcv.main import create_app
from backedcv.settings import Settings, get_settings

PROMPT = load_prompt("verify")  # a real prompt: the loader compares entries with its version
MODEL = "gpt-6-luna"
MODELS = {"fast": MODEL, "strong": MODEL}
LIVE = {"label": "live", "score": 1}
PINNED = {"label": "pinned", "score": 9}
USAGE = {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150}
COMMITTED = Path(__file__).resolve().parents[2] / "samples" / PINNED_FILE


class Answer(BaseModel):
    label: str
    score: int


class FakeModel:
    """Stands in for ChatOpenAI and its structured runnable: counts the calls, answers LIVE."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, **kwargs) -> "FakeModel":
        self.model_name = kwargs["model"]
        return self

    def with_structured_output(self, schema, **_options) -> "FakeModel":
        self.schema = schema
        return self

    async def ainvoke(self, messages, config=None) -> dict:
        self.calls += 1
        raw = AIMessage(content="{}", usage_metadata=USAGE)
        return {"raw": raw, "parsed": self.schema.model_validate(LIVE), "parsing_error": None}


@pytest.fixture
def fake(monkeypatch) -> FakeModel:
    model = FakeModel()
    monkeypatch.setattr(structured, "ChatOpenAI", model.chat)
    return model


def _llm(data_dir: Path, pinned_file: Path | None = None) -> OpenAIStructuredLLM:
    settings = Settings(data_dir=data_dir, model_fast=MODEL, model_strong=MODEL, llm_cache=True)
    llm = OpenAIStructuredLLM(settings)
    llm.cache.pinned = load_pinned_answers(pinned_file, MODELS) if pinned_file else {}
    return llm


def _run(llm: OpenAIStructuredLLM, data: str = "the sample posting"):
    return asyncio.run(llm.run(PROMPT, data, Answer, node="verify_batch"))


def _recorded_key(tmp_path: Path, fake: FakeModel, data: str = "the sample posting") -> str:
    """The key the cache stores this call under, read back from a throwaway cache (not counted)."""
    scratch = tmp_path / "scratch"
    _run(_llm(scratch), data)
    with closing(sqlite3.connect(scratch / "llm_cache.sqlite")) as db:
        (key,) = db.execute("SELECT key FROM answers").fetchone()
    fake.calls = 0
    return key


def _entry(key: str, *, version: str | None = None, model: str = MODEL, answer=PINNED) -> dict:
    prompt = PROMPT if version is None else replace(PROMPT, version=version)
    return pinned_entry(
        key,
        model=model,
        effort="low",
        prompt=prompt,
        schema=Answer,
        answer=answer,
        input_tokens=120,
        output_tokens=30,
    )


def _write_pinned(path: Path, *entries: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {"format": PINNED_FORMAT, "entries": list(entries)}
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def _rows(data_dir: Path) -> int:
    with closing(sqlite3.connect(data_dir / "llm_cache.sqlite")) as db:
        return db.execute("SELECT COUNT(*) FROM answers").fetchone()[0]


def test_a_pinned_answer_is_served_without_a_model_call(tmp_path, fake):
    pinned = _write_pinned(tmp_path / PINNED_FILE, _entry(_recorded_key(tmp_path, fake)))
    llm = _llm(tmp_path / "data", pinned)

    answer, usage = _run(llm)

    assert fake.calls == 0
    assert answer == Answer(**PINNED)
    assert usage["cached"] is True and usage["cost_usd"] == 0.0
    assert (usage["input_tokens"], usage["output_tokens"]) == (120, 30)
    assert not (tmp_path / "data" / "llm_cache.sqlite").exists()  # the disk cache is not touched


@pytest.mark.parametrize("change", [{"version": "0"}, {"model": "gpt-6.1-sol"}])
def test_a_pinned_answer_from_another_prompt_version_or_model_is_ignored(tmp_path, fake, change):
    entry = _entry(_recorded_key(tmp_path, fake), **change)  # the key itself still matches
    llm = _llm(tmp_path / "data", _write_pinned(tmp_path / PINNED_FILE, entry))

    answer, usage = _run(llm)

    assert llm.cache.pinned == {}
    assert fake.calls == 1
    assert answer == Answer(**LIVE) and usage["cached"] is False


def test_other_inputs_are_cached_as_usual(tmp_path, fake):
    pinned = _write_pinned(tmp_path / PINNED_FILE, _entry(_recorded_key(tmp_path, fake)))
    llm = _llm(tmp_path / "data", pinned)

    first, first_usage = _run(llm, data="a posting that is not a sample")
    second, second_usage = _run(llm, data="a posting that is not a sample")

    assert fake.calls == 1
    assert first == second == Answer(**LIVE)
    assert first_usage["cached"] is False and second_usage["cached"] is True
    assert _rows(tmp_path / "data") == 1  # the live answer, in the 24-hour cache


def test_pinned_answers_never_expire(tmp_path, fake):
    key = _recorded_key(tmp_path, fake)
    llm = _llm(tmp_path / "data", _write_pinned(tmp_path / PINNED_FILE, _entry(key)))
    _run(llm, data="a posting that is not a sample")

    deleted = llm.cache.purge_created_before(datetime.now(UTC) + timedelta(days=365))

    assert deleted == 1  # the normal row
    assert llm.cache.get(key) == (PINNED, 120, 30)
    assert _run(llm)[0] == Answer(**PINNED)
    assert fake.calls == 1


def test_a_pinned_answer_that_no_longer_fits_the_schema_falls_back_to_a_live_call(tmp_path, fake):
    stale = _entry(_recorded_key(tmp_path, fake), answer={"label": "pinned"})  # no score
    path = _write_pinned(tmp_path / PINNED_FILE, stale)
    before = path.read_text(encoding="utf-8")
    llm = _llm(tmp_path / "data", path)

    first, _ = _run(llm)
    second, usage = _run(llm)

    assert first == second == Answer(**LIVE)
    assert fake.calls == 1 and usage["cached"] is True  # the live answer is cached as usual
    assert path.read_text(encoding="utf-8") == before  # the pinned file is never written


@pytest.mark.parametrize(
    "content",
    [
        None,
        "not json",
        '{"entries": 3}',
        '{"no_entries": []}',
        json.dumps(
            {
                "entries": [
                    {"key": "0" * 64},
                    "not an entry",
                    {**_entry("1" * 64), "prompt_id": "no_such_prompt"},
                    {**_entry("2" * 64), "answer": "not an object"},
                ]
            }
        ),
    ],
)
def test_a_missing_or_broken_pinned_file_pins_nothing(tmp_path, content):
    path = tmp_path / PINNED_FILE
    if content is not None:
        path.write_text(content, encoding="utf-8")

    assert load_pinned_answers(path, MODELS) == {}


def test_the_app_loads_the_pinned_answers_at_startup(tmp_path, monkeypatch):
    samples = tmp_path / "samples"
    _write_pinned(samples / PINNED_FILE, _entry("a" * 64), _entry("b" * 64, version="0"))
    monkeypatch.setenv("BACKEDCV_SAMPLES_DIR", str(samples))
    monkeypatch.setenv("BACKEDCV_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BACKEDCV_MODEL_FAST", MODEL)
    monkeypatch.setenv("BACKEDCV_MODEL_STRONG", MODEL)
    monkeypatch.setenv("BACKEDCV_LLM_CACHE", "true")
    get_settings.cache_clear()
    try:
        app = create_app(checkpointer=InMemorySaver())
        with TestClient(app):
            pinned = app.state.llm.cache.pinned
    finally:
        get_settings.cache_clear()

    assert set(pinned) == {"a" * 64}  # the out-of-date entry is ignored


@pytest.mark.skipif(not COMMITTED.exists(), reason="no pinned answers committed yet")
def test_the_committed_pinned_answers_are_well_formed():
    content = json.loads(COMMITTED.read_text(encoding="utf-8"))
    entries = content["entries"]

    assert content["format"] == PINNED_FORMAT
    assert entries and len({e["key"] for e in entries}) == len(entries)
    for entry in entries:
        assert re.fullmatch(r"[0-9a-f]{64}", entry["key"])
        for field in ("model", "effort", "prompt_id", "prompt_version", "schema"):
            assert isinstance(entry[field], str)
        assert type(entry["input_tokens"]) is int and type(entry["output_tokens"]) is int
        assert isinstance(entry["answer"], dict)
