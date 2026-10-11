"""SQLite cache of model answers, keyed by everything that decides the answer (`answer_key`).

Rows keep their creation time so the hourly purge in `api/retention.py` can delete old ones.

Pinned answers are real model answers for the built-in samples (`samples/pinned_answers.json`,
written by `scripts/pin_samples.py`). They are loaded at startup, held in memory, never expire
and are never overwritten, so the samples give the same report even after a restart wipes the
disk. Any other input gets a live answer."""

import copy
import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from backedcv.domain.text import normalize_text
from backedcv.llm.prompt_loader import Prompt, load_prompt
from backedcv.settings import get_settings

log = logging.getLogger(__name__)

PINNED_FILE = "pinned_answers.json"  # in the samples folder (`Settings.samples_dir`)
PINNED_FORMAT = 1

Stored = tuple[dict, int, int]  # the answer, its input tokens, its output tokens


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


def pinned_entry(
    key: str,
    *,
    model: str,
    effort: str,
    prompt: Prompt,
    schema: type[BaseModel],
    answer: dict,
    input_tokens: int,
    output_tokens: int,
) -> dict:
    """One entry of the pinned answers file, with the model and prompt version it came from."""
    return {
        "key": key,
        "model": model,
        "effort": effort,
        "prompt_id": prompt.id,
        "prompt_version": prompt.version,
        "schema": schema.__name__,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "answer": answer,
    }


def load_pinned_answers(path: Path, models: Mapping[str, str]) -> dict[str, Stored]:
    """The pinned answers in `path` that still apply, by key. `models` maps each prompt tier to
    its current model. An entry whose prompt version or model changed is ignored, so a change
    brings a live call, never a stale answer. A missing or unreadable file pins nothing."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
    except FileNotFoundError:
        log.info("No pinned answers at %s", path)
        return {}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("Pinned answers not loaded from %s: %s", path, exc)
        return {}
    if not isinstance(entries, list):
        log.warning("Pinned answers not loaded from %s: no list of entries", path)
        return {}
    pinned = {}
    for entry in entries:
        stored = _current_answer(entry, models)
        if stored is not None:
            pinned[entry["key"]] = stored
    log.info(
        "Pinned answers: %d loaded, %d ignored (out of date or unreadable)",
        len(pinned),
        len(entries) - len(pinned),
    )
    return pinned


def sample_answers() -> dict[str, Stored]:
    """Pinned answers of the built-in samples for the current settings. Read once per process."""
    settings = get_settings()
    path = settings.samples_dir / PINNED_FILE
    return _read_pinned(path, settings.model_fast, settings.model_strong)


@lru_cache(maxsize=8)
def _read_pinned(path: Path, model_fast: str, model_strong: str) -> dict[str, Stored]:
    return load_pinned_answers(path, {"fast": model_fast, "strong": model_strong})


def _current_answer(entry: object, models: Mapping[str, str]) -> Stored | None:
    """The answer of one pinned entry, or None if it is unreadable or out of date."""
    try:
        prompt = load_prompt(entry["prompt_id"])
        key, answer = entry["key"], entry["answer"]
        tokens_in, tokens_out = entry["input_tokens"], entry["output_tokens"]
        version, model = entry["prompt_version"], entry["model"]
    except (KeyError, TypeError, ValueError, OSError):
        return None
    current = version == prompt.version and model == models.get(prompt.tier)
    readable = isinstance(key, str) and isinstance(answer, dict)
    if current and readable and type(tokens_in) is int and type(tokens_out) is int:
        return answer, tokens_in, tokens_out
    return None


class LLMCache:
    """Answers by key in one SQLite file, after the pinned ones held in memory. A broken database
    is only a miss: the cache saves money and must never fail an analysis."""

    def __init__(self, path: Path, pinned: Mapping[str, Stored] | None = None) -> None:
        """`pinned` defaults to the pinned answers of the built-in samples (`sample_answers`)."""
        self.path = path
        self.pinned: dict[str, Stored] = dict(sample_answers() if pinned is None else pinned)

    def get(self, key: str) -> tuple[dict, int, int] | None:
        """The stored answer and its token counts, or None. Pinned answers come first; a row with
        no creation time counts as expired."""
        if key in self.pinned:
            answer, tokens_in, tokens_out = self.pinned[key]
            return copy.deepcopy(answer), tokens_in, tokens_out
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
        """Stores a successful answer; a failed write is only logged. A pinned key gets here only
        when its pinned answer no longer fits the schema: the pin is dropped from memory (the
        file is untouched) and the live answer is cached."""
        if self.pinned.pop(key, None) is not None:
            log.warning("A pinned answer no longer fits its schema; using a live answer")
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
        """Deletes rows created before `cutoff` and rows with no creation time. Returns how many.
        Unlike get and put, it raises if the file cannot be read, and it never creates the file.
        Pinned answers are not rows, so they never expire."""
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
        """Opens the file (creating the table on first use) and closes it after. A table without
        `created_at` gets the column; its old rows stay without a creation time."""
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
