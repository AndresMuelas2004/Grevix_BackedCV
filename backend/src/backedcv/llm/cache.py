"""A SQLite cache of model answers: the same call with the same input gets the stored answer back,
at no cost. The key covers everything that decides the answer (see `answer_key`). Each row keeps
its creation time, so the hourly purge in `api/retention.py` can delete the old ones."""

import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from backedcv.domain.text import normalize_text
from backedcv.llm.prompt_loader import Prompt

log = logging.getLogger(__name__)


def answer_key(model: str, effort: str, prompt: Prompt, schema: type[BaseModel], data: str) -> str:
    """A SHA-256 over the model, the prompt (ID, version and text), the reasoning effort, the
    schema name and the input in its canonical form (`normalize_text`), which is also what the
    model receives: inputs that differ only in whitespace or invisible characters share a key."""
    fields = {
        "model": model,
        "effort": effort,
        "prompt_id": prompt.id,
        "prompt_version": prompt.version,
        "prompt_text": prompt.text,
        "schema": schema.__name__,
        "input": normalize_text(data),
    }
    text = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLMCache:
    """Answers stored by key in one SQLite file. A row that cannot be read is a miss, and a broken
    database never fails an analysis: the cache only saves money."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, key: str) -> tuple[dict, int, int] | None:
        """The stored answer with its token counts, or None on a miss or an unreadable row. A row
        with no creation time counts as expired and is never returned."""
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT answer, input_tokens, output_tokens FROM answers "
                    "WHERE key = ? AND created_at IS NOT NULL",
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
        """Stores a successful answer, timestamped now. If the write fails, the next identical call
        asks again."""
        stored_at = datetime.now(UTC).timestamp()
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO answers "
                    "(key, answer, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        key,
                        json.dumps(answer, ensure_ascii=False),
                        input_tokens,
                        output_tokens,
                        stored_at,
                    ),
                )
        except (OSError, sqlite3.Error) as exc:
            log.warning("LLM cache write failed: %s", exc)

    def purge_created_before(self, cutoff: datetime) -> int:
        """Deletes the rows created before `cutoff`, and the rows with no creation time (their age
        is unknown, so they count as expired). Returns how many rows were deleted. Unlike get and
        put, this raises when the file cannot be read, so the caller logs it. It creates no file."""
        if not self.path.exists():
            return 0
        with self._connect() as db:
            deleted = db.execute(
                "DELETE FROM answers WHERE created_at IS NULL OR created_at < ?",
                (cutoff.timestamp(),),
            ).rowcount
        return deleted

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Opens the file, creating it with its table on first use, and closes it again. A table
        from before the `created_at` column gets the column; its old rows keep no creation time."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        try:
            with db:  # commits when the block ends well, rolls back when it fails
                db.execute(
                    "CREATE TABLE IF NOT EXISTS answers ("
                    "key TEXT PRIMARY KEY, answer TEXT NOT NULL, "
                    "input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, "
                    "created_at REAL)"
                )
                columns = {row[1] for row in db.execute("PRAGMA table_info(answers)")}
                if "created_at" not in columns:
                    db.execute("ALTER TABLE answers ADD COLUMN created_at REAL")
                yield db
        finally:
            db.close()
