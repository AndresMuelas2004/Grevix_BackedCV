"""Analyses and cached model answers expire after 24 hours: an hourly task deletes the old ones
(and the checkpoints of the analyses)."""

import asyncio
import logging
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver

from backedcv.api.errors import ApiError
from backedcv.api.locks import RunLocks
from backedcv.llm.cache import LLMCache

MAX_AGE = timedelta(hours=24)
PURGE_EVERY = 3600  # seconds between two passes

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class AnalysisLedger:
    """The ID and creation time of every analysis. The checkpointer cannot list its threads
    cheaply, so the purge reads the list from here. In a file, it survives restarts."""

    def __init__(self, path: str | Path) -> None:
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS analyses "
                "(analysis_id TEXT PRIMARY KEY, created_at REAL NOT NULL)"
            )

    def add(self, analysis_id: str, created_at: datetime) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO analyses (analysis_id, created_at) VALUES (?, ?)",
                (analysis_id, created_at.timestamp()),
            )

    def remove(self, analysis_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM analyses WHERE analysis_id = ?", (analysis_id,))

    def created_before(self, cutoff: datetime) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT analysis_id FROM analyses WHERE created_at < ?", (cutoff.timestamp(),)
            ).fetchall()
        return [analysis_id for (analysis_id,) in rows]

    def close(self) -> None:
        self._db.close()


async def purge_expired(
    ledger: AnalysisLedger,
    checkpointer: BaseCheckpointSaver,
    locks: RunLocks,
    now: datetime,
    max_age: timedelta = MAX_AGE,
    cache: LLMCache | None = None,
) -> list[str]:
    """Deletes the analyses created more than `max_age` before `now`, with their checkpoints, and
    the cache rows created that long before it (rows with no creation time count as old).

    An analysis that is running is skipped and the next pass looks at it again. Returns the IDs
    that were deleted. A failure on one analysis is logged and the others still go on. A failure
    on the cache raises, so the hourly pass logs it.
    """
    cutoff = now - max_age
    purged: list[str] = []
    for analysis_id in ledger.created_before(cutoff):
        try:
            locks.acquire(analysis_id)
        except ApiError:
            continue  # a run holds it now: the next pass will look again
        try:
            async with locks.held(analysis_id):
                await checkpointer.adelete_thread(analysis_id)
                ledger.remove(analysis_id)
        except Exception:
            log.exception("could not purge analysis %s", analysis_id)
            continue
        purged.append(analysis_id)
    if cache is not None:
        cache.purge_created_before(cutoff)
    return purged


async def purge_hourly(
    ledger: AnalysisLedger,
    checkpointer: BaseCheckpointSaver,
    locks: RunLocks,
    clock: Callable[[], datetime] = utc_now,
    every: float = PURGE_EVERY,
    cache: LLMCache | None = None,
) -> None:
    """One pass at once, then one every `every` seconds, until the task is cancelled."""
    while True:
        try:
            await purge_expired(ledger, checkpointer, locks, now=clock(), cache=cache)
        except Exception:
            log.exception("retention purge failed; the next pass will try again")
        await asyncio.sleep(every)
