"""A SQLite cache of model answers: the same call with the same input gets the stored answer back,
at no cost. The key covers everything that decides the answer (see `answer_key`)."""

import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel

from backedcv.llm.prompt_loader import Prompt

log = logging.getLogger(__name__)


def answer_key(model: str, effort: str, prompt: Prompt, schema: type[BaseModel], data: str) -> str:
    """A SHA-256 over the model, the prompt (ID, version and text), the reasoning effort, the
    schema name and the exact input the model receives."""
    fields = {
        "model": model,
        "effort": effort,
        "prompt_id": prompt.id,
        "prompt_version": prompt.version,
        "prompt_text": prompt.text,
        "schema": schema.__name__,
        "input": data,
    }
    text = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLMCache:
    """Answers stored by key in one SQLite file. A row that cannot be read is a miss, and a broken
    database never fails an analysis: the cache only saves money."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, key: str) -> tuple[dict, int, int] | None:
        """The stored answer with its token counts, or None on a miss or an unreadable row."""
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT answer, input_tokens, output_tokens FROM answers WHERE key = ?",
                    (key,),
                ).fetchone()
        except (OSError, sqlite3.Error) as exc:
            log.warning("LLM cache unavailable, asking the model: %s", exc)
            return None
        if row is None:
            return None
        text, tokens_in, tokens_out = row
        try:
            answer = json.loads(text)
        except (TypeError, ValueError):
            answer = None
        if isinstance(answer, dict) and type(tokens_in) is int and type(tokens_out) is int:
            return answer, tokens_in, tokens_out
        log.warning("Ignoring an unreadable LLM cache row")
        return None

    def put(self, key: str, answer: dict, input_tokens: int, output_tokens: int) -> None:
        """Stores a successful answer. If the write fails, the next identical call asks again."""
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO answers (key, answer, input_tokens, output_tokens) "
                    "VALUES (?, ?, ?, ?)",
                    (key, json.dumps(answer, ensure_ascii=False), input_tokens, output_tokens),
                )
        except (OSError, sqlite3.Error) as exc:
            log.warning("LLM cache write failed: %s", exc)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Opens the file, creating it with its table on first use, and closes it again."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        try:
            with db:  # commits when the block ends well, rolls back when it fails
                db.execute(
                    "CREATE TABLE IF NOT EXISTS answers ("
                    "key TEXT PRIMARY KEY, answer TEXT NOT NULL, "
                    "input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL)"
                )
                yield db
        finally:
            db.close()
