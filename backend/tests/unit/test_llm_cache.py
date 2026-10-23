import asyncio
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from backedcv.llm import structured
from backedcv.llm.cache import LLMCache, answer_key
from backedcv.llm.prompt_loader import Prompt
from backedcv.llm.structured import AnthropicStructuredLLM, LLMError
from backedcv.settings import Settings

PROMPT = Prompt(id="verify", version="1", tier="fast", text="Check the claim.")
USAGE = {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150}


class Answer(BaseModel):
    label: str
    score: int


class OtherAnswer(Answer):
    """Same fields as Answer, another name: only the schema name tells them apart in the key."""


class FakeModel:
    """Stands in for ChatAnthropic, so no call reaches the network. It counts the calls and answers
    with `answer`, or with no valid answer when `answer` is None."""

    def __init__(self) -> None:
        self.calls = 0
        self.answer: dict | None = {"label": "supported", "score": 3}

    def chat(self, **kwargs) -> "FakeChat":
        return FakeChat(self, kwargs["model"])


class FakeChat:
    def __init__(self, fake: FakeModel, model: str) -> None:
        self.fake = fake
        self.model_name = model

    def with_structured_output(self, schema, **_options) -> "FakeRunnable":
        return FakeRunnable(self.fake, schema)


class FakeRunnable:
    def __init__(self, fake: FakeModel, schema: type[BaseModel]) -> None:
        self.fake, self.schema = fake, schema

    async def ainvoke(self, messages, config=None) -> dict:
        self.fake.calls += 1
        answer = self.fake.answer
        return {
            "raw": AIMessage(content="{}", usage_metadata=USAGE),
            "parsed": None if answer is None else self.schema.model_validate(answer),
            "parsing_error": None if answer is not None else "no valid answer",
        }


@pytest.fixture
def fake(monkeypatch) -> FakeModel:
    model = FakeModel()
    monkeypatch.setattr(structured, "ChatAnthropic", model.chat)
    return model


def _llm(tmp_path: Path, *, llm_cache: bool = True, cache: bool | None = None):
    settings = Settings(
        data_dir=tmp_path,
        model_fast="claude-haiku-5-5",
        model_strong="claude-sonnet-5-5",
        llm_cache=llm_cache,
    )
    return AnthropicStructuredLLM(settings, cache=cache)


def _run(llm, prompt=PROMPT, data="the posting", schema=Answer):
    return asyncio.run(llm.run(prompt, data, schema, node="verify_batch"))


def _db(tmp_path: Path) -> Path:
    return tmp_path / "llm_cache.sqlite"


def _execute(tmp_path: Path, sql: str, params: tuple = ()) -> list:
    with closing(sqlite3.connect(_db(tmp_path))) as db, db:
        return db.execute(sql, params).fetchall()


def _stored_rows(tmp_path: Path) -> int:
    if not _db(tmp_path).exists():
        return 0
    return _execute(tmp_path, "SELECT COUNT(*) FROM answers")[0][0]


def test_an_identical_call_is_answered_from_the_cache(tmp_path, fake):
    llm = _llm(tmp_path)

    first, first_usage = _run(llm)
    second, second_usage = _run(llm)

    assert fake.calls == 1
    assert second == first == Answer(label="supported", score=3)
    assert first_usage["cached"] is False and first_usage["cost_usd"] > 0
    assert second_usage["cached"] is True
    assert second_usage["cost_usd"] == 0.0
    assert (second_usage["input_tokens"], second_usage["output_tokens"]) == (120, 30)


def test_a_different_input_is_a_miss(tmp_path, fake):
    llm = _llm(tmp_path)

    _run(llm, data="one posting")
    _run(llm, data="another posting")

    assert fake.calls == 2


def test_a_new_prompt_version_is_a_miss(tmp_path, fake):
    llm = _llm(tmp_path)

    _run(llm)
    _run(llm, prompt=replace(PROMPT, version="2"))

    assert fake.calls == 2


def test_another_model_tier_is_a_miss(tmp_path, fake):
    llm = _llm(tmp_path)

    _run(llm)
    _run(llm, prompt=replace(PROMPT, tier="strong"))

    assert fake.calls == 2


def test_a_disabled_cache_asks_the_model_every_time(tmp_path, fake):
    llm = _llm(tmp_path, llm_cache=False)

    _run(llm)
    _, usage = _run(llm)

    assert fake.calls == 2
    assert usage["cached"] is False
    assert not _db(tmp_path).exists()


@pytest.mark.parametrize(("setting", "override", "calls"), [(True, False, 2), (False, True, 1)])
def test_the_cache_argument_overrides_the_setting(tmp_path, fake, setting, override, calls):
    llm = _llm(tmp_path, llm_cache=setting, cache=override)

    _run(llm)
    _run(llm)

    assert fake.calls == calls


@pytest.mark.parametrize("payload", ["not json", '{"label": "supported"}', "[1, 2]"])
def test_a_corrupted_row_is_ignored_and_replaced(tmp_path, fake, payload):
    llm = _llm(tmp_path)
    _run(llm)
    _execute(tmp_path, "UPDATE answers SET answer = ?", (payload,))

    answer, usage = _run(llm)
    _run(llm)

    assert answer == Answer(label="supported", score=3)
    assert usage["cached"] is False
    assert fake.calls == 2  # the broken row was a miss; the fresh answer replaced it


def test_a_cache_file_that_cannot_be_read_does_not_fail_the_call(tmp_path, fake):
    _db(tmp_path).write_bytes(b"this is not a database" * 50)
    llm = _llm(tmp_path)

    answer, _ = _run(llm)

    assert answer == Answer(label="supported", score=3)
    assert fake.calls == 1


def test_a_failed_answer_is_not_stored(tmp_path, fake):
    fake.answer = None
    llm = _llm(tmp_path)

    with pytest.raises(LLMError):
        _run(llm)

    assert _stored_rows(tmp_path) == 0


def _key(**changes) -> str:
    call = {
        "model": "claude-haiku-5-5",
        "effort": "low",
        "prompt": PROMPT,
        "schema": Answer,
        "data": "the posting",
    }
    return answer_key(**{**call, **changes})


def test_the_key_changes_with_each_part_of_the_call():
    base = _key()
    variants = {
        _key(model="claude-sonnet-5-5"),
        _key(effort="high"),
        _key(prompt=replace(PROMPT, id="other")),
        _key(prompt=replace(PROMPT, version="2")),
        _key(prompt=replace(PROMPT, text="Check the claim again.")),
        _key(schema=OtherAnswer),
        _key(data="another posting"),
    }

    assert _key() == base
    assert base not in variants
    assert len(variants) == 7


def test_rows_created_before_the_cutoff_are_purged_and_fresh_rows_stay(tmp_path):
    cache = LLMCache(_db(tmp_path))
    cache.put("old", {"label": "supported", "score": 3}, 120, 30)
    cache.put("fresh", {"label": "supported", "score": 3}, 120, 30)
    now = datetime.now(UTC)
    _execute(
        tmp_path,
        "UPDATE answers SET created_at = ? WHERE key = ?",
        ((now - timedelta(hours=25)).timestamp(), "old"),
    )

    assert cache.purge_created_before(now - timedelta(hours=24)) == 1

    assert cache.get("old") is None
    assert cache.get("fresh") is not None
    assert _stored_rows(tmp_path) == 1


def test_a_cache_from_before_the_timestamp_is_migrated_and_its_rows_count_as_expired(tmp_path):
    with closing(sqlite3.connect(_db(tmp_path))) as db, db:
        db.execute(
            "CREATE TABLE answers (key TEXT PRIMARY KEY, answer TEXT NOT NULL, "
            "input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL)"
        )
        db.execute(
            "INSERT INTO answers VALUES ('legacy', ?, 120, 30)",
            (json.dumps({"label": "supported", "score": 3}),),
        )
    cache = LLMCache(_db(tmp_path))

    assert cache.get("legacy") is None  # no creation time: never served
    columns = {row[1] for row in _execute(tmp_path, "PRAGMA table_info(answers)")}
    assert "created_at" in columns
    assert _stored_rows(tmp_path) == 1  # the migration keeps the rows

    cache.put("new", {"label": "supported", "score": 3}, 120, 30)
    assert cache.purge_created_before(datetime(2000, 1, 1, tzinfo=UTC)) == 1  # the legacy row
    assert cache.get("new") is not None
    assert _stored_rows(tmp_path) == 1


def test_purging_before_any_answer_is_stored_creates_no_file(tmp_path):
    assert LLMCache(_db(tmp_path)).purge_created_before(datetime.now(UTC)) == 0
    assert not _db(tmp_path).exists()
